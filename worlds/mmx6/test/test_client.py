"""Tests for the Mega Man X6 BizHawk client.

The client is the half of this world that cannot be checked by generating a
seed, so everything here works on a synthetic save buffer instead of an
emulator. What it pins is the set of things that silently break in the wrong
direction: a check firing off an AP grant, a grant that is not idempotent, and
a bit written early that makes its own location uncollectable.
"""
import asyncio
import unittest

from .. import names, reploids
from ..client import (EXE_SIG, LIFE_GAUGE_BASE, LIFE_GAUGE_MAX, OFF_ARMOR_PARTS,
                      OFF_ARMOR_SELECT, OFF_BEATEN, OFF_CHAR, OFF_HEARTS,
                      OFF_ENERGY_UPS, OFF_LIFE_GAUGE, OFF_LIFE_UPS, OFF_PARTS,
                      OFF_PROGRESS, OFF_REPLOIDS, OFF_TANKS, OFF_WEAPON_GAUGE,
                      AMMO_SLOTS, LIVES_CAP, OFF_LIVES, OFF_P_AMMO, OFF_P_HP,
                      OFF_P_WEAPON_IDX, PLAYER_BASE, PLAYER_HP_ADDR, PLAYER_LEN,
                      OFF_WEAPON_GAUGE, SAVE_BASE, SAVE_LEN, SMALL_LIFE_HEAL,
                      SMALL_WEAPON_FRACTION, WEAPON_AMMO_SCALE,
                      WEAPON_GAUGE_BASE, AP_WEAPONS, OFF_AP_WEAPONS,
                      PATCH_PROBE_PATCHED, PATCH_PROBE_VANILLA, MMX6Client)
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
        # CommonContext always has this; the client reads it to decide when
        # withholding can stop (ship plan item 23).
        self.finished_game = False
        # Data storage, simulated end to end rather than stubbed: the baseline
        # gate's whole point is that its decision survives a round trip, and a
        # stub that just remembers what was written would not test that.
        self.team, self.slot = 0, 1
        self.stored_data: dict = {}
        self.notified: set = set()
        self.sent: list = []

    def set_notify(self, *keys) -> None:
        for key in keys:
            if key not in self.notified:
                self.notified.add(key)
                self.stored_data[key] = None      # server replies "unset"

    async def send_msgs(self, msgs) -> None:
        self.sent.extend(msgs)
        for msg in msgs:
            if msg.get("cmd") == "Set":
                for op in msg["operations"]:
                    if op["operation"] == "replace":
                        self.stored_data[msg["key"]] = op["value"]


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

    def test_the_gauge_is_absolute_in_both_directions(self) -> None:
        # Until 0.2.1 this asserted the opposite - "never shrinks" - because a
        # vanilla pickup raises the gauge too and the write took the max. That
        # made the game's own 32 unbeatable by a lower starting_hp, so the
        # write is absolute now: a Heart Tank walked over is a check, and its
        # +2 belongs to whoever received the item.
        save = blank_save()
        save[OFF_LIFE_GAUGE] = 50
        self.apply(FakeCtx(items=[names.HEART_TANK]), save)
        self.assertEqual(save[OFF_LIFE_GAUGE], LIFE_GAUGE_BASE + 2)

        # The cap is vanilla's 64 - the last gauge the life bar has a frame
        # for. The gauge itself holds 127 and used to be allowed to, until
        # 0.3.0 play showed the fill running off the end of the frame above
        # 64. More upgrades than the seed needs simply saturate.
        save = blank_save()
        self.apply(FakeCtx(items=[names.HEART_TANK] * 20), save)
        self.assertEqual(save[OFF_LIFE_GAUGE], LIFE_GAUGE_MAX)
        save = blank_save()
        self.apply(FakeCtx(items=[names.HEART_TANK] * 60), save)
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

    def test_suffix_reaches_the_bizhawk_launcher_component(self) -> None:
        # The class attribute alone proves nothing about the Launcher: the
        # suffix has to arrive in the BizHawk Client component's
        # file_identifier, which is what Open Patch actually consults.
        # Patch.create_rom_file() bypasses that path entirely, so no
        # patch-flow test can stand in for this one (X5's gate learned that
        # the hard way; this is X5's TestLauncherRegistration, ported).
        from worlds.LauncherComponents import components
        bizhawk = [c for c in components if c.script_name == "BizHawkClient"]
        self.assertTrue(bizhawk, "BizHawk Client component missing")
        self.assertIn(".apmmx6", bizhawk[0].file_identifier.suffixes,
                      "Open Patch will not offer .apmmx6 to players")

    def test_suffix_matches_the_patch_file_ending(self) -> None:
        from ..Rom import MMX6ProcedurePatch
        self.assertEqual(MMX6Client.patch_suffix,
                         MMX6ProcedurePatch.patch_file_ending)


# A REAL save state, rebuilt by replaying the 2026-08-25 play-session RAM diff
# log forward (every `old -> new` in observation order). This is the closest
# thing to a live capture that needs no emulator, and it is ground truth: the
# session is the one the research notes were written from, so what the client
# reads out of it can be checked against what the player actually did.
#
# Regenerate with scratch script replay_detect.py if the log is ever replaced.
REPLAYED_SAVE = bytes.fromhex(
    "0a0000000000000000000000020000000000000000000000000000000002010148ef"
    "08800000000000000000000000000000000000000200000900000000000000000000"
    "00000000000000000000000000000000000000000000002620000101213230910000"
    "02000140001020210020408001000000000000000000000000000000000000000000"
    "00000000200507000000000002000000260000000500010000000000000000000000"
    "04000000000000000000000000000000000000000000000000000000000040180000"
    "fc1a00000000d4010000d40122200222202202202002000000000000000000000000"
    "00000000000000000000000000000000000022220222222200000000000000000000"
    "00000000000000002220022220220220000000000000000000000000000000000000"
    "00000000000000000000000000002222022222220000000000000000000000000000"
    "00000000ffff00000000000000000000000000000006000102060001000000000000"
    "00000100000000000000"
)


class TestAgainstRealPlay(unittest.TestCase):
    """Detection run against a real recorded session.

    Every assertion below is cross-checked against something independently
    recorded in the research notes, not against the client's own output.
    """

    def setUp(self) -> None:
        self.client = MMX6Client()
        self.found = self.client._detect(FakeCtx(), REPLAYED_SAVE)

    def named(self, kind: str) -> set:
        return {n for i, n in
                ((location_table[k], k) for k in location_table)
                if i in self.found and n.endswith(kind)}

    def test_the_two_stages_that_were_cleared(self) -> None:
        # beaten byte read 0x21 = bits 0 and 5. The player cleared Commander
        # Yammark and Rainy Turtloid in that session and no others.
        self.assertEqual(self.named("Boss Defeated"),
                         {names.boss_location(names.YAMMARK),
                          names.boss_location(names.TURTLOID)})

    def test_the_turtloid_pickups_the_notes_recorded(self) -> None:
        # Notes, all live-confirmed: the Inami Temple heart wrote
        # 0x800CCF3C |= 0x20, and the Shadow Armor capsule wrote
        # 0x800CCF39 |= 0x40 (Shadow Body).
        self.assertIn(location_table[names.heart_location(names.TURTLOID)],
                      self.found)
        self.assertIn(location_table[names.capsule_location(names.TURTLOID)],
                      self.found)
        self.assertEqual(REPLAYED_SAVE[OFF_ARMOR_PARTS],
                         names.ARMOR_PART_BIT[names.SHADOW_BODY])

    def test_the_yammark_sub_tank(self) -> None:
        # Notes: 0x800CCF3B |= 0x10, the one tank bit observed live. It is
        # what pins Yammark to +0x10 rather than Heatnix.
        self.assertIn(location_table[names.tank_location(names.YAMMARK)],
                      self.found)
        self.assertEqual(REPLAYED_SAVE[OFF_TANKS], names.TANK_BIT[names.YAMMARK])

    def test_the_gauges_match_the_upgrade_arithmetic_exactly(self) -> None:
        # The strongest check here, because it is arithmetic against three
        # separate bitfields rather than a single byte comparison:
        #   life   = 32 + 2 * (heart tanks + life ups)
        #   weapon = 48 + 2 * energy ups
        # The session ended with 1 heart, 2 life ups and 1 energy up.
        hearts = bin(REPLAYED_SAVE[OFF_HEARTS]).count("1")
        life_ups = bin(REPLAYED_SAVE[OFF_LIFE_UPS]).count("1")
        energy_ups = bin(REPLAYED_SAVE[OFF_ENERGY_UPS]).count("1")
        self.assertEqual((hearts, life_ups, energy_ups), (1, 2, 1))
        self.assertEqual(REPLAYED_SAVE[OFF_LIFE_GAUGE],
                         LIFE_GAUGE_BASE + 2 * (hearts + life_ups))
        self.assertEqual(REPLAYED_SAVE[OFF_WEAPON_GAUGE],
                         WEAPON_GAUGE_BASE + 2 * energy_ups)

    def test_the_exact_reploids_the_session_rescued(self) -> None:
        # Pinned EXACTLY, not as a subset. A subset check passed even when the
        # block base was moved to the mirror at 0x800CCFE8, because the mirror
        # holds a lagging copy of the same stages - the two Wolfang rescues
        # that happened after the last save are the only difference. Anything
        # looser than an exact set cannot tell the live array from its own
        # snapshot.
        expected = {
            names.YAMMARK: [1, 2, 4, 5, 7, 8, 10, 11, 12, 13, 16],
            names.WOLFANG: [2, 3],
            names.TURTLOID: [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12],
        }
        want = {location_table[names.reploid_location(stage, n)]
                for stage, ns in expected.items() for n in ns}
        got = {i for i, n in ((location_table[k], k) for k in location_table)
               if i in self.found and " - Reploid " in n}
        self.assertEqual(got, want)

    def test_the_client_reads_the_live_array_not_the_mirror(self) -> None:
        # There are two 64-byte copies of the Reploid array, 0x40 apart. The
        # mirror only ever updates in bulk, so a client reading it would miss
        # every rescue made since the last save.
        self.assertEqual(SAVE_BASE + OFF_REPLOIDS,
                         reploids.REPLOID_BLOCK - 0x80000000)
        self.assertEqual(reploids.REPLOID_MIRROR - reploids.REPLOID_BLOCK, 0x40)

    def test_intro_is_marked_and_the_endgame_is_not(self) -> None:
        self.assertIn(location_table[names.INTRO_CLEAR], self.found)
        self.assertLess(REPLAYED_SAVE[OFF_PROGRESS], 3)


class TestFiller(unittest.TestCase):
    """Consumables - the one grant that is deliberately NOT idempotent.

    Everything else here is safe to reassert every poll. A heal is not, so it
    rides a cursor into items_received instead, and these tests pin the two
    ways that goes wrong: applying the same heal twice, and losing an item
    because it arrived at a moment it could not be applied.
    """
    def setUp(self) -> None:
        self.client = MMX6Client()
        self.save = blank_save()
        self.save[OFF_LIVES] = 2
        self.save[OFF_LIFE_GAUGE] = 40

    @staticmethod
    def player_block(hp=20, weapon=1, ammo=300, cap=300):
        """A live player object, shaped like the one a real peek produced:
        every ammo slot at the cap except the selected one."""
        p = bytearray(PLAYER_LEN)
        p[OFF_P_HP] = hp
        p[OFF_P_WEAPON_IDX] = weapon
        for i in range(AMMO_SLOTS):
            v = ammo if i == weapon else cap
            p[OFF_P_AMMO + i * 2:OFF_P_AMMO + i * 2 + 2] = v.to_bytes(2, "little")
        return bytes(p)

    def run_filler(self, ctx, player):
        writes, cursor = self.client._filler_grants(ctx, bytes(self.save), player)
        self.client.filler_cursor = cursor
        for addr, data in writes:
            if addr >= PLAYER_BASE and addr < PLAYER_BASE + PLAYER_LEN:
                continue
            off = addr - SAVE_BASE
            self.save[off:off + len(data)] = data
        return writes

    def test_filler_already_in_hand_at_connect_is_skipped(self) -> None:
        # The cursor starts at the length of the list, so reconnecting does
        # not re-heal. For a consumable, losing one is better than duplicating
        # one - and a reconnect mid-run is exactly when duplication would hit.
        ctx = FakeCtx(items=[names.EXTRA_LIFE] * 3)
        self.assertEqual(self.run_filler(ctx, self.player_block()), [])
        self.assertEqual(self.save[OFF_LIVES], 2)

    def test_an_extra_life_arriving_later_is_applied_once(self) -> None:
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, self.player_block())                    # establishes the cursor
        ctx.items_received.append(FakeItem(names.EXTRA_LIFE))
        self.assertTrue(self.run_filler(ctx, self.player_block()))
        self.assertEqual(self.save[OFF_LIVES], 3)
        for _ in range(5):
            self.assertEqual(self.run_filler(ctx, self.player_block()), [],
                             "the same Extra Life was applied twice")
        self.assertEqual(self.save[OFF_LIVES], 3)

    def test_lives_stop_at_the_cap(self) -> None:
        self.save[OFF_LIVES] = LIVES_CAP
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, self.player_block())
        ctx.items_received.append(FakeItem(names.EXTRA_LIFE))
        self.run_filler(ctx, self.player_block())
        self.assertEqual(self.save[OFF_LIVES], LIVES_CAP)

    def test_a_life_received_at_the_cap_is_banked_not_eaten(self) -> None:
        # The old behaviour silently absorbed it: min(cap, lives+1) is a no-op
        # at the cap, but the cursor advanced anyway, so somebody's item just
        # vanished. It must be paid out once the player spends a life.
        self.save[OFF_LIVES] = LIVES_CAP
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, self.player_block())
        ctx.items_received.append(FakeItem(names.EXTRA_LIFE))
        self.run_filler(ctx, self.player_block())
        self.assertEqual(self.save[OFF_LIVES], LIVES_CAP, "cap was exceeded")

        self.save[OFF_LIVES] = LIVES_CAP - 2          # the player died twice
        self.run_filler(ctx, self.player_block())
        self.assertEqual(self.save[OFF_LIVES], LIVES_CAP - 1,
                         "the banked life was never paid out")

        for _ in range(4):                            # and only once
            self.run_filler(ctx, self.player_block())
        self.assertEqual(self.save[OFF_LIVES], LIVES_CAP - 1)

    def test_a_life_at_the_cap_does_not_stall_later_filler(self) -> None:
        # The cursor is strictly sequential, so if a full life stock blocked
        # it, every heal queued behind the life would be held hostage until
        # the player happened to die. Banking is what avoids that.
        self.save[OFF_LIVES] = LIVES_CAP
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, self.player_block())
        ctx.items_received.append(FakeItem(names.EXTRA_LIFE))
        ctx.items_received.append(FakeItem(names.LARGE_LIFE_ENERGY))
        writes = self.run_filler(ctx, self.player_block(hp=1))
        self.assertTrue([w for w in writes if w[0] == PLAYER_HP_ADDR],
                        "the heal behind a capped Extra Life never landed")

    def test_a_heal_waits_for_a_stage_instead_of_being_lost(self) -> None:
        # player_hp None means there is no live player block - between stages,
        # or on the Mission Report. The item must not be consumed there.
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, None)
        ctx.items_received.append(FakeItem(names.SMALL_LIFE_ENERGY))

        writes = self.run_filler(ctx, None)
        self.assertEqual(writes, [], "healed with no live player block")
        cursor_held = self.client.filler_cursor

        writes = self.run_filler(ctx, self.player_block(hp=10))
        self.assertEqual(writes, [(PLAYER_HP_ADDR,
                                   bytes([10 + SMALL_LIFE_HEAL]))])
        self.assertGreater(self.client.filler_cursor, cursor_held)

    def test_a_stalled_heal_does_not_swallow_the_items_behind_it(self) -> None:
        # Order matters: the cursor stops AT the heal, so the Extra Life
        # behind it is applied on the next pass rather than skipped past.
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, None)
        ctx.items_received += [FakeItem(names.SMALL_LIFE_ENERGY),
                               FakeItem(names.EXTRA_LIFE)]
        self.run_filler(ctx, None)
        self.assertEqual(self.save[OFF_LIVES], 2, "consumed out of order")
        self.run_filler(ctx, self.player_block(hp=10))
        self.assertEqual(self.save[OFF_LIVES], 3)

    def test_healing_never_passes_the_life_gauge(self) -> None:
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, None)
        ctx.items_received.append(FakeItem(names.LARGE_LIFE_ENERGY))
        writes = self.run_filler(ctx, self.player_block(hp=self.save[OFF_LIFE_GAUGE] - 1))
        self.assertEqual(writes, [(PLAYER_HP_ADDR,
                                   bytes([self.save[OFF_LIFE_GAUGE]]))])

    def test_weapon_energy_refills_the_selected_slot(self) -> None:
        # Values are the ones a real peek produced: 16 u16 slots, fifteen at
        # 300 and the selected one part-used, with the index byte reading 1.
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, self.player_block())
        ctx.items_received.append(FakeItem(names.SMALL_WEAPON_ENERGY))
        writes = self.run_filler(ctx, self.player_block(weapon=1, ammo=220))
        expected_addr = PLAYER_BASE + OFF_P_AMMO + 1 * 2
        self.assertEqual(len(writes), 1)
        addr, data = writes[0]
        self.assertEqual(addr, expected_addr, "refilled the wrong slot")
        self.assertEqual(int.from_bytes(data, "little"),
                         220 + 300 // SMALL_WEAPON_FRACTION)

    def test_a_refill_never_passes_the_live_cap(self) -> None:
        # The cap comes from the ARRAY, not the save byte: the live max is
        # latched at stage start, so an Energy Up granted mid-stage has not
        # raised it yet and capping on the save byte would overfill.
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, self.player_block())
        ctx.items_received.append(FakeItem(names.LARGE_WEAPON_ENERGY))
        self.save[OFF_WEAPON_GAUGE] = 64          # a just-granted Energy Up
        writes = self.run_filler(ctx, self.player_block(weapon=1, ammo=290))
        self.assertEqual(int.from_bytes(writes[0][1], "little"), 300,
                         "capped on the save gauge instead of the array")

    def test_a_refill_waits_for_a_stage_like_a_heal(self) -> None:
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, None)
        ctx.items_received += [FakeItem(names.SMALL_WEAPON_ENERGY),
                               FakeItem(names.EXTRA_LIFE)]
        self.run_filler(ctx, None)
        self.assertEqual(self.save[OFF_LIVES], 2, "consumed out of order")
        self.run_filler(ctx, self.player_block(weapon=1, ammo=100))
        self.assertEqual(self.save[OFF_LIVES], 3)

    def test_the_buster_slot_is_still_a_valid_target(self) -> None:
        # Index 0 was 300 in the real dump too, so an index of 0 is a slot
        # like any other rather than a "no weapon" sentinel to skip.
        ctx = FakeCtx(items=[])
        self.run_filler(ctx, self.player_block())
        ctx.items_received.append(FakeItem(names.SMALL_WEAPON_ENERGY))
        writes = self.run_filler(ctx, self.player_block(weapon=0, ammo=100))
        self.assertEqual(writes[0][0], PLAYER_BASE + OFF_P_AMMO)


# The two real `peek(0x097130, 0x40)` dumps, verbatim from the play session.
# These pin the ammo CONSTANTS, which the synthetic player_block() above
# cannot: it builds its block from the same offsets the client reads, so it
# stays self-consistent even when those offsets are wrong. Mutation testing
# caught exactly that - four offset breakages passed until this fixture
# existed.
PEEK_ADDR = 0x097130
PEEK_BEFORE = bytes.fromhex(
    "00000001010000ff01000002000000000000000000000000"
    "2c01fc002c012c012c012c012c012c012c012c012c012c01"
    "2c012c012c012c01002100000000000000"[:128])
PEEK_AFTER = bytes.fromhex(
    "00000001010000ff01010100000000000100000000000000"
    "2c01dc002c012c012c012c012c012c012c012c012c012c01"
    "2c012c012c012c01002100000000000000"[:128])


def player_from_peek(dump: bytes) -> bytes:
    """Splice a real peek dump into a player block at its true offset."""
    block = bytearray(PLAYER_LEN)
    start = PEEK_ADDR - PLAYER_BASE
    block[start:start + len(dump)] = dump[:PLAYER_LEN - start]
    return bytes(block)


class TestAmmoAgainstRealDump(unittest.TestCase):
    """The ammo constants, checked against bytes the game actually produced.

    Ground truth from the session: the index byte read 1, slot 1 fell 252 ->
    220 across firing, and the other fifteen slots sat at 300 throughout.
    """

    def test_the_weapon_index_byte_reads_one(self) -> None:
        self.assertEqual(player_from_peek(PEEK_BEFORE)[OFF_P_WEAPON_IDX], 1)

    def test_the_selected_slot_is_the_one_that_moved(self) -> None:
        before, after = (player_from_peek(PEEK_BEFORE),
                         player_from_peek(PEEK_AFTER))
        index = before[OFF_P_WEAPON_IDX]

        def slots(p):
            return [int.from_bytes(p[OFF_P_AMMO + i * 2:OFF_P_AMMO + i * 2 + 2],
                                   "little") for i in range(AMMO_SLOTS)]

        b, a = slots(before), slots(after)
        self.assertEqual((b[index], a[index]), (252, 220))
        moved = [i for i in range(AMMO_SLOTS) if b[i] != a[i]]
        self.assertEqual(moved, [index],
                         "a slot other than the selected one changed")
        self.assertEqual({b[i] for i in range(AMMO_SLOTS) if i != index}, {300})

    def test_the_cap_is_the_weapon_gauge_times_six(self) -> None:
        # 15 slots at 300 against a save-struct weapon gauge of 50 when the
        # stage was entered. Matches X5 independently (288 = 48 * 6).
        self.assertEqual(50 * WEAPON_AMMO_SCALE, 300)

    def test_the_client_refills_the_slot_the_dump_says_is_selected(self) -> None:
        client = MMX6Client()
        save = blank_save()
        ctx = FakeCtx(items=[])
        _, cursor = client._filler_grants(ctx, bytes(save),
                                          player_from_peek(PEEK_AFTER))
        client.filler_cursor = cursor
        ctx.items_received.append(FakeItem(names.SMALL_WEAPON_ENERGY))
        writes, _ = client._filler_grants(ctx, bytes(save),
                                          player_from_peek(PEEK_AFTER))
        self.assertEqual(len(writes), 1)
        addr, data = writes[0]
        self.assertEqual(addr, 0x097148 + 1 * 2,
                         "did not write the real slot-1 address")
        self.assertEqual(int.from_bytes(data, "little"),
                         220 + 300 // SMALL_WEAPON_FRACTION)

    def test_the_array_is_exactly_sixteen_slots(self) -> None:
        # The dump shows sixteen consecutive 2C 01 at 0x097148..0x097167 and
        # then 00 21 at 0x097168 - a different value, so the array ends there.
        # Behaviour alone cannot pin this: a client using 8 slots reads slot 1
        # identically. X5's map independently records 16 (X's 8 + Zero's 8).
        block = player_from_peek(PEEK_BEFORE)
        end = OFF_P_AMMO + AMMO_SLOTS * 2
        self.assertEqual(PLAYER_BASE + OFF_P_AMMO, 0x097148)
        self.assertEqual(PLAYER_BASE + end, 0x097168)
        self.assertEqual(AMMO_SLOTS, 16)
        self.assertNotEqual(int.from_bytes(block[end:end + 2], "little"), 300,
                            "the byte after the array looks like another slot")

    def test_offsets_match_the_disassembly(self) -> None:
        # Pinned directly because the dump cannot distinguish them: the bytes
        # at +0x93 and +0x94 both read 01 in the real capture, so only the
        # code settles it. consume_ammo() at 0x8003F740 reads
        #   lb    v1, 0x93(s0)     <- current weapon index
        #   addiu a1, s0, 0xa8     <- &ammo[0]
        # and the HP offset is from the live player map (mask 0x7F, bit 0x80
        # is a hit/heal flag).
        self.assertEqual(OFF_P_WEAPON_IDX, 0x93)
        self.assertEqual(OFF_P_AMMO, 0xA8)
        self.assertEqual(OFF_P_HP, 0x5C)
        self.assertEqual(PLAYER_BASE, 0x0970A0)


class TestBaselineGate(unittest.TestCase):
    """Whether a save's already-collected locations may be sent.

    This replaces the seed/slot stamp X5 writes into a spare save byte. X6
    cannot copy that approach: its memcard re-serialises the save rather than
    copying it, so a byte that looks free in RAM may never reach the card.
    Deriving the answer from what the SERVER already knows needs no save byte
    at all.

    The rule: send the baseline only when the server has already recorded a
    check for this slot, which proves the save belongs to a run of this seed.
    """

    def setUp(self) -> None:
        self.client = MMX6Client()
        self.ctx = FakeCtx()
        self.save = blank_save()
        self.save[OFF_PROGRESS] = 2
        self.save[OFF_BEATEN] = names.STAGE_BIT[names.YAMMARK]
        self.save[OFF_HEARTS] = names.STAGE_BIT[names.TURTLOID]

    def resolve(self, checked=(), ctx=None):
        # Calls the CLIENT's own gate. An earlier version of this helper
        # reimplemented the rule here, which made it self-consistent: a
        # mutation disabling the gate entirely still passed.
        #
        # The context is reused across calls by default so that data storage
        # persists between polls, which is the thing under test.
        ctx = ctx if ctx is not None else self.ctx
        ctx.checked_locations = {location_table[c] for c in checked}
        found = self.client._detect(ctx, bytes(self.save))
        asyncio.run(self.client._baseline_sync(ctx, found))
        return self.client._sendable(ctx, found)

    def test_a_progressed_save_on_a_virgin_slot_is_held(self) -> None:
        # The dangerous case: a save from another seed. The server has no
        # record for this slot, so nothing may be sent.
        self.assertEqual(self.resolve(checked=()), set())
        self.assertTrue(self.client.baseline_held)

    def test_a_slot_with_history_gets_its_baseline_sent(self) -> None:
        # The server already knows this slot checked something, so the save
        # belongs to this seed and anything extra was collected offline.
        sendable = self.resolve(checked=[names.INTRO_CLEAR])
        self.assertIn(location_table[names.boss_location(names.YAMMARK)], sendable)
        self.assertFalse(self.client.baseline_held)

    def test_a_fresh_game_holds_nothing(self) -> None:
        # The overwhelmingly common case: new seed, new save. Nothing is
        # already collected, so there is nothing to hold and no warning.
        self.save = blank_save()
        self.assertEqual(self.resolve(checked=()), set())
        self.assertFalse(self.client.baseline_held)

    def test_a_live_check_releases_the_held_baseline(self) -> None:
        # Holding must never stop a check the player earns while watching -
        # that is what lets them prove the save. Collecting one that is NOT
        # part of the disputed baseline now releases the rest immediately,
        # where it used to need a reconnect.
        self.resolve(checked=())
        held = set(self.client.baseline_held)
        self.assertTrue(held)
        self.save[OFF_TANKS] = names.TANK_BIT[names.YAMMARK]   # collected live
        sendable = self.resolve(checked=())
        self.assertIn(location_table[names.tank_location(names.YAMMARK)],
                      sendable)
        self.assertTrue(held <= sendable,
                        "the baseline was not released by the live check")
        self.assertFalse(self.client.baseline_held)


class TestWeaponGrants(unittest.TestCase):
    """Weapons may only be granted on a disc carrying the A1 patch.

    On vanilla, 0x800CCF30 is simultaneously the kill record and the weapon
    list, so granting a weapon there would fabricate a boss check. The patch
    redirects the capability to AP_WEAPONS, which nothing else in the game
    reads or writes.
    """

    def setUp(self) -> None:
        self.client = MMX6Client()
        self.save = blank_save()

    def apply(self, ctx):
        writes = self.client._grants(ctx, bytes(self.save))
        for addr, data in writes:
            off = addr - SAVE_BASE
            self.save[off:off + len(data)] = data
        return writes

    def test_the_probe_distinguishes_the_three_states(self) -> None:
        # None is not a nicety: validate_rom can race the EXE still streaming
        # in from disc, and a probe of zeros must mean "retry", never
        # "vanilla" - that difference decides whether weapons are granted.
        self.assertIs(MMX6Client._classify_probe(PATCH_PROBE_PATCHED), True)
        self.assertIs(MMX6Client._classify_probe(PATCH_PROBE_VANILLA), False)
        self.assertIsNone(MMX6Client._classify_probe(b"\x00\x00\x00\x00"))

    def test_the_probe_words_differ_only_in_the_immediate(self) -> None:
        # Both are `lbu v0, <imm>(a1)`; the patch changes 0x60 to 0xAB and
        # nothing else. If these ever differ elsewhere, the patch is wrong.
        van = int.from_bytes(PATCH_PROBE_VANILLA, "little")
        pat = int.from_bytes(PATCH_PROBE_PATCHED, "little")
        self.assertEqual(van >> 16, pat >> 16, "opcode or registers changed")
        self.assertEqual(van & 0xFFFF, 0x60)
        self.assertEqual(pat & 0xFFFF, AP_WEAPONS - 0x800CCED0)

    def test_no_weapon_bits_are_written_on_vanilla(self) -> None:
        self.client.ap_patched = False
        self.apply(FakeCtx(items=list(names.WEAPONS)))
        self.assertEqual(self.save[OFF_BEATEN], 0)
        self.assertEqual(self.save[OFF_AP_WEAPONS], 0)

    def test_nothing_is_written_while_the_probe_is_undetermined(self) -> None:
        self.client.ap_patched = None
        self.apply(FakeCtx(items=list(names.WEAPONS)))
        self.assertEqual(self.save[OFF_AP_WEAPONS], 0)
        self.assertEqual(self.save[OFF_BEATEN], 0)

    def test_a_patched_disc_gets_the_capability_and_not_the_kill_record(self) -> None:
        self.client.ap_patched = True
        self.apply(FakeCtx(items=[names.BOSS_WEAPON[names.YAMMARK],
                                  names.BOSS_WEAPON[names.TURTLOID]]))
        self.assertEqual(self.save[OFF_AP_WEAPONS],
                         names.STAGE_BIT[names.YAMMARK]
                         | names.STAGE_BIT[names.TURTLOID])
        self.assertEqual(self.save[OFF_BEATEN], 0,
                         "the kill record must never be written")

    def test_the_capability_follows_the_items_exactly(self) -> None:
        # Absolute, like every other grant: losing an item would clear its
        # bit. Also confirms the bit order matches the stage order the rest
        # of the world uses.
        self.client.ap_patched = True
        for stage in names.STAGES:
            self.save = blank_save()
            self.apply(FakeCtx(items=[names.BOSS_WEAPON[stage]]))
            self.assertEqual(self.save[OFF_AP_WEAPONS], names.STAGE_BIT[stage],
                             f"{stage} wrote the wrong capability bit")

    def test_boss_detection_still_works_on_a_patched_disc(self) -> None:
        # The whole point of A1: kills keep recording, so the boss check and
        # the endgame gate are unaffected by granting weapons.
        self.client.ap_patched = True
        self.apply(FakeCtx(items=list(names.WEAPONS)))
        self.assertEqual(self.client._detect(FakeCtx(), bytes(self.save)), set())
        self.save[OFF_BEATEN] = names.STAGE_BIT[names.YAMMARK]
        self.assertIn(location_table[names.boss_location(names.YAMMARK)],
                      self.client._detect(FakeCtx(), bytes(self.save)))
