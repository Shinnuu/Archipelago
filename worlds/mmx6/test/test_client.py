"""Tests for the Mega Man X6 BizHawk client.

The client is the half of this world that cannot be checked by generating a
seed, so everything here works on a synthetic save buffer instead of an
emulator. What it pins is the set of things that silently break in the wrong
direction: a check firing off an AP grant, a grant that is not idempotent, and
a bit written early that makes its own location uncollectable.
"""
import unittest

from .. import names, reploids
from ..client import (EXE_SIG, LIFE_GAUGE_BASE, LIFE_GAUGE_MAX, OFF_ARMOR_PARTS,
                      OFF_ARMOR_SELECT, OFF_BEATEN, OFF_CHAR, OFF_HEARTS,
                      OFF_ENERGY_UPS, OFF_LIFE_GAUGE, OFF_LIFE_UPS, OFF_PARTS,
                      OFF_PROGRESS, OFF_REPLOIDS, OFF_TANKS, OFF_WEAPON_GAUGE,
                      SAVE_BASE, SAVE_LEN,
                      WEAPON_GAUGE_BASE, MMX6Client)
from ..locations import location_table


class FakeItem:
    def __init__(self, name: str) -> None:
        self.name = name
        self.item = name          # the fake lookup is the identity


class FakeNames:
    @staticmethod
    def lookup_in_game(item):
        return item


class FakeCtx:
    """Only the four attributes the client actually touches."""
    def __init__(self, items=(), checked=()) -> None:
        self.items_received = [FakeItem(i) for i in items]
        self.item_names = FakeNames()
        self.checked_locations = {location_table[c] for c in checked}
        self.slot_data = {}


def blank_save() -> bytearray:
    save = bytearray(SAVE_LEN)
    save[OFF_LIFE_GAUGE] = LIFE_GAUGE_BASE
    save[OFF_WEAPON_GAUGE] = WEAPON_GAUGE_BASE
    return save


def ids(locations) -> set:
    return {location_table[name] for name in locations}


class TestDetection(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MMX6Client()

    def test_a_blank_save_detects_nothing(self) -> None:
        self.assertEqual(self.client._detect(FakeCtx(), blank_save()), set())

    def test_intro_clear_comes_off_the_progress_counter(self) -> None:
        save = blank_save()
        save[OFF_PROGRESS] = 1
        self.assertEqual(self.client._detect(FakeCtx(), save),
                         ids([names.INTRO_CLEAR]))

    def test_every_stage_bitfield_maps_to_its_own_stage(self) -> None:
        # One stage at a time, so a mis-ordered STAGES list cannot pass by
        # accident - the bit, the stage and the location name all have to line
        # up for each of the eight.
        for stage in names.STAGES:
            bit = names.STAGE_BIT[stage]
            save = blank_save()
            save[OFF_BEATEN] = bit
            save[OFF_HEARTS] = bit
            save[OFF_TANKS] = names.TANK_BIT.get(stage, 0)
            save[OFF_ARMOR_PARTS] = \
                names.ARMOR_PART_BIT[names.STAGE_ARMOR_PART[stage]]
            expected = {names.boss_location(stage), names.heart_location(stage),
                        names.capsule_location(stage)}
            if stage in names.STAGE_TANK:
                expected.add(names.tank_location(stage))
            self.assertEqual(self.client._detect(FakeCtx(), save),
                             ids(expected), f"{stage} mapped wrongly")

    def test_turtloid_rescue_pattern_from_the_live_log(self) -> None:
        # Replays what a real session wrote: 0x800CCFD0 went 0 -> 0x02 -> 0x22
        # (Reploids 80 then 81, hundreds of frames apart), and 0x800CCFD4
        # became 0x20 - Reploid 89 rescued while 88 stayed untouched.
        save = blank_save()
        save[OFF_REPLOIDS + 40] = 0x22      # Reploids 80 and 81
        save[OFF_REPLOIDS + 44] = 0x20      # Reploid 89 only, high nibble
        found = self.client._detect(FakeCtx(), save)
        self.assertEqual(found, ids([
            names.reploid_location(names.TURTLOID, 1),   # index 80
            names.reploid_location(names.TURTLOID, 2),   # index 81
            names.reploid_location(names.TURTLOID, 10),  # index 89
        ]))

    def test_a_destroyed_reploid_still_pays_out(self) -> None:
        # States 3 (dead) and 4 (missing) are PERMANENT. Keying the check on 2
        # alone would let a Nightmare destroy up to 128 checks, and in a
        # multiworld a destroyed check is another player's item gone for good.
        # Reploid 97 really did go straight to 4 in ordinary play.
        for state in (reploids.RESCUED, reploids.DEAD, reploids.MISSING):
            save = blank_save()
            save[OFF_REPLOIDS + 48] = state << 4     # Reploid 97, high nibble
            self.assertEqual(
                self.client._detect(FakeCtx(), save),
                ids([names.reploid_location(names.SHELDON, 2)]),
                f"nibble state {state} did not pay out")

    def test_all_128_reploids_are_reachable_in_the_block(self) -> None:
        save = blank_save()
        for i in range(reploids.REPLOID_BLOCK_LEN):
            save[OFF_REPLOIDS + i] = 0x22
        found = self.client._detect(FakeCtx(), save)
        self.assertEqual(len(found), 128)
        self.assertEqual(found, ids(n for _s, _i, _n2, n in reploids.REPLOIDS))


class TestGrants(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MMX6Client()

    def apply(self, ctx, save):
        """Run the grants and fold them back into the buffer, so a second run
        can be compared against the first (idempotence)."""
        writes = self.client._grants(ctx, bytes(save))
        for addr, data in writes:
            off = addr - SAVE_BASE
            save[off:off + len(data)] = data
        return writes

    def test_gauges_are_absolute_so_regranting_is_a_no_op(self) -> None:
        # The failure this prevents: an incremental "+2 per Heart Tank" grant
        # re-running after a reconnect and inflating the gauge every time. X5
        # needed a memcard-persisted counter to make that safe; computing the
        # target removes the problem instead of guarding it.
        save = blank_save()
        ctx = FakeCtx(items=[names.HEART_TANK] * 3 + [names.LIFE_UP] * 2)
        self.apply(ctx, save)
        self.assertEqual(save[OFF_LIFE_GAUGE], LIFE_GAUGE_BASE + 2 * 5)
        for _ in range(5):
            self.assertEqual(self.apply(ctx, save), [],
                             "re-granting changed the save")
        self.assertEqual(save[OFF_LIFE_GAUGE], LIFE_GAUGE_BASE + 2 * 5)

    def test_the_gauge_never_shrinks_and_never_passes_the_cap(self) -> None:
        # A vanilla pickup raises the gauge too, so a computed target below the
        # live value must not claw it back.
        save = blank_save()
        save[OFF_LIFE_GAUGE] = 50
        self.apply(FakeCtx(items=[names.HEART_TANK]), save)
        self.assertEqual(save[OFF_LIFE_GAUGE], 50)

        save = blank_save()
        self.apply(FakeCtx(items=[names.HEART_TANK] * 20), save)
        self.assertEqual(save[OFF_LIFE_GAUGE], LIFE_GAUGE_MAX)

    def test_gauge_record_bits_are_never_written(self) -> None:
        # Policy 4. If a grant set these, detection would read its own write
        # back as a pickup and fire a check nobody earned.
        save = blank_save()
        self.apply(FakeCtx(items=[names.HEART_TANK] * 8
                                 + [names.LIFE_UP] * 8
                                 + [names.ENERGY_UP] * 8), save)
        self.assertEqual(save[OFF_HEARTS], 0)
        self.assertEqual(save[OFF_LIFE_UPS], 0)
        self.assertEqual(save[OFF_ENERGY_UPS], 0)
        self.assertEqual(self.client._detect(FakeCtx(), save), set())

    def test_weapons_are_never_written(self) -> None:
        # Policy 1: 0x800CCF30 is the kill record AND the weapon list. Writing
        # it to grant a weapon fabricates a boss check and moves the story on.
        save = blank_save()
        self.apply(FakeCtx(items=list(names.WEAPONS)), save)
        self.assertEqual(save[OFF_BEATEN], 0)
        self.assertEqual(self.client._detect(FakeCtx(), save), set())

    def test_an_armor_part_is_withheld_until_its_capsule_is_checked(self) -> None:
        # Policy 3. Setting the bit early stops the capsule spawning, which
        # would make its location permanently uncollectable.
        part = names.STAGE_ARMOR_PART[names.TURTLOID]
        capsule = names.capsule_location(names.TURTLOID)

        save = blank_save()
        self.apply(FakeCtx(items=[part]), save)
        self.assertEqual(save[OFF_ARMOR_PARTS], 0, "granted before the check")

        save = blank_save()
        self.apply(FakeCtx(items=[part], checked=[capsule]), save)
        self.assertEqual(save[OFF_ARMOR_PARTS], names.ARMOR_PART_BIT[part])

    def test_a_tank_is_withheld_until_its_location_is_checked(self) -> None:
        save = blank_save()
        self.apply(FakeCtx(items=[names.EX_TANK]), save)
        self.assertEqual(save[OFF_TANKS], 0)

        save = blank_save()
        self.apply(FakeCtx(items=[names.EX_TANK],
                           checked=[names.tank_location(names.WOLFANG)]), save)
        self.assertEqual(save[OFF_TANKS], names.TANK_BIT[names.WOLFANG])

    def test_two_sub_tanks_fill_yammark_then_heatnix(self) -> None:
        # Sub Tank has two copies and no stage identity of its own, so the
        # order is fixed here rather than left to dict iteration.
        checked = [names.tank_location(names.YAMMARK),
                   names.tank_location(names.HEATNIX)]
        save = blank_save()
        self.apply(FakeCtx(items=[names.SUB_TANK], checked=checked), save)
        self.assertEqual(save[OFF_TANKS], names.TANK_BIT[names.YAMMARK])

        save = blank_save()
        self.apply(FakeCtx(items=[names.SUB_TANK] * 2, checked=checked), save)
        self.assertEqual(save[OFF_TANKS],
                         names.TANK_BIT[names.YAMMARK] | names.TANK_BIT[names.HEATNIX])

    def test_characters_and_secret_armors_need_no_withholding(self) -> None:
        # 0x800CCF2F is a pure capability byte - no location reads it.
        save = blank_save()
        self.apply(FakeCtx(items=[names.ZERO, names.ULTIMATE_ARMOR,
                                  names.BLACK_ZERO]), save)
        self.assertEqual(save[OFF_ARMOR_SELECT], 0x10 | 0x08 | 0x20)

    def test_every_part_lands_on_its_documented_bit(self) -> None:
        for name in names.PARTS:
            save = blank_save()
            self.apply(FakeCtx(items=[name]), save)
            addr, mask = names.PART_BIT[name]
            byte = OFF_PARTS + (addr - 0x800CCF40)
            self.assertEqual(save[byte], mask, f"{name} wrote the wrong bit")
            self.assertEqual(sum(save[OFF_PARTS:OFF_PARTS + 4]), mask,
                             f"{name} touched more than one Part bit")


class TestIdentification(unittest.TestCase):
    def test_exe_signature_matches_the_disc(self) -> None:
        # Read straight off our own disc image: SLUS_013.95 declares t_addr
        # 0x80010000, and the first bytes there are a pointer word followed by
        # the container path. 18 bytes is plenty to identify the game.
        self.assertEqual(len(EXE_SIG), 18)
        self.assertEqual(EXE_SIG[:4], bytes([0x60, 0x98, 0x0E, 0x80]))
        self.assertEqual(EXE_SIG[4:], rb"\ROCK_X6.DAT;1")

    def test_the_save_read_covers_every_offset_the_client_uses(self) -> None:
        highest = max(OFF_REPLOIDS + reploids.REPLOID_BLOCK_LEN, OFF_PARTS + 4,
                      OFF_CHAR, OFF_PROGRESS)
        self.assertLessEqual(highest, SAVE_LEN)

    def test_patch_suffix_is_registered(self) -> None:
        # Without this the Launcher's Open Patch dialog does not list the
        # extension, so a player who double-clicks their patch is never
        # prompted for a disc image. A tester hit exactly that on X5 v0.1.0.
        self.assertEqual(MMX6Client.patch_suffix, ".apmmx6")
        self.assertEqual(MMX6Client.system, "PSX")
