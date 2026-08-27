"""Per-character gauge tests - ship plan item 22.

X and Zero each own a life and a weapon gauge. The game keeps the pair in step
through its own pickup routine; an AP grant writes the save byte directly and
does not go through it. So writing X's byte alone meant a player who took
`zero_unlock` - a shipped option, and therefore a supported way to play - lost
every gauge upgrade in the seed.

Found live 2026-08-27 in a finished save: X's life gauge read 64, maxed by 16
AP grants, while Zero's still read the base 32, untouched all seed. Raising
0x800CCF2C stopped his life bar drawing past its own frame.

The overfill was the visible half and the lost upgrades were the expensive
half, so both are pinned here. Note the failure was silent in exactly the way
offline tests are blind to: every assertion about "the gauge was written"
passed, because the byte it asserted on was the one being written.
"""
import unittest

from .. import names
from ..client import (CHAR_ZERO, GAUGE_STEP, LARGE_LIFE_HEAL, LIFE_GAUGE_BASE,
                      LIFE_GAUGE_MAX,
                      OFF_CHAR, OFF_LIFE_GAUGE, OFF_LIFE_GAUGE_ZERO,
                      OFF_LIVES, OFF_P_HP, OFF_WEAPON_GAUGE,
                      OFF_WEAPON_GAUGE_ZERO, PLAYER_LEN, SAVE_BASE, SAVE_LEN,
                      WEAPON_GAUGE_BASE, WEAPON_GAUGE_MAX, MMX6Client,
                      _gauge_offsets)


class FakeItem:
    def __init__(self, name: str) -> None:
        self.name = name
        self.item = name


class FakeCtx:
    def __init__(self, items=()) -> None:
        self.items_received = [FakeItem(i) for i in items]
        self.item_names = type(
            "N", (), {"lookup_in_game": staticmethod(lambda i: i)})
        self.checked_locations = set()
        self.slot_data = {}
        # CommonContext always has this; the client reads it to decide when
        # withholding can stop (ship plan item 23).
        self.finished_game = False


def blank_save(char=0) -> bytearray:
    save = bytearray(SAVE_LEN)
    save[OFF_CHAR] = char
    save[OFF_LIFE_GAUGE] = LIFE_GAUGE_BASE
    save[OFF_LIFE_GAUGE_ZERO] = LIFE_GAUGE_BASE
    save[OFF_WEAPON_GAUGE] = WEAPON_GAUGE_BASE
    save[OFF_WEAPON_GAUGE_ZERO] = WEAPON_GAUGE_BASE
    return save


def written(client, ctx, save) -> dict:
    """{offset: value} for what _grants would write."""
    return {addr - SAVE_BASE: data[0]
            for addr, data in client._grants(ctx, bytes(save))}


class TestTheAddressesAreDistinct(unittest.TestCase):
    def test_zero_has_his_own_pair(self) -> None:
        self.assertNotEqual(OFF_LIFE_GAUGE, OFF_LIFE_GAUGE_ZERO)
        self.assertNotEqual(OFF_WEAPON_GAUGE, OFF_WEAPON_GAUGE_ZERO)

    def test_each_sits_one_byte_after_x(self) -> None:
        # 0x800CCF2B/0x800CCF2C and 0x800CCF31/0x800CCF32. If this ever stops
        # holding, one of the four was transcribed wrong.
        self.assertEqual(OFF_LIFE_GAUGE_ZERO, OFF_LIFE_GAUGE + 1)
        self.assertEqual(OFF_WEAPON_GAUGE_ZERO, OFF_WEAPON_GAUGE + 1)

    def test_no_gauge_collides_with_another_mapped_byte(self) -> None:
        from ..client import (OFF_ARMOR_PARTS, OFF_ARMOR_SELECT, OFF_BEATEN,
                              OFF_PROGRESS, OFF_TANKS)
        others = {OFF_ARMOR_SELECT, OFF_BEATEN, OFF_PROGRESS, OFF_ARMOR_PARTS,
                  OFF_TANKS}
        for gauge in (OFF_LIFE_GAUGE, OFF_LIFE_GAUGE_ZERO, OFF_WEAPON_GAUGE,
                      OFF_WEAPON_GAUGE_ZERO):
            self.assertNotIn(gauge, others)


class TestGrantsUpgradeBoth(unittest.TestCase):
    def test_a_heart_tank_raises_zero_as_well_as_x(self) -> None:
        # THE BUG. Before this, only X's byte moved.
        w = written(MMX6Client(), FakeCtx([names.HEART_TANK]), blank_save())
        self.assertEqual(w.get(OFF_LIFE_GAUGE), LIFE_GAUGE_BASE + GAUGE_STEP)
        self.assertEqual(w.get(OFF_LIFE_GAUGE_ZERO),
                         LIFE_GAUGE_BASE + GAUGE_STEP)

    def test_an_energy_up_raises_zeros_weapon_gauge(self) -> None:
        w = written(MMX6Client(), FakeCtx([names.ENERGY_UP]), blank_save())
        self.assertEqual(w.get(OFF_WEAPON_GAUGE),
                         WEAPON_GAUGE_BASE + GAUGE_STEP)
        self.assertEqual(w.get(OFF_WEAPON_GAUGE_ZERO),
                         WEAPON_GAUGE_BASE + GAUGE_STEP)

    def test_a_full_seed_maxes_both_life_gauges(self) -> None:
        items = [names.HEART_TANK] * 8 + [names.LIFE_UP] * 8
        w = written(MMX6Client(), FakeCtx(items), blank_save())
        self.assertEqual(w.get(OFF_LIFE_GAUGE), LIFE_GAUGE_MAX)
        self.assertEqual(w.get(OFF_LIFE_GAUGE_ZERO), LIFE_GAUGE_MAX)

    def test_neither_gauge_ever_goes_backwards(self) -> None:
        # Vanilla pickups raise these too, so the write takes the max. A save
        # where the player earned more locally than AP has sent must not be
        # pulled back down - for either character.
        save = blank_save()
        save[OFF_LIFE_GAUGE] = LIFE_GAUGE_MAX
        save[OFF_LIFE_GAUGE_ZERO] = LIFE_GAUGE_MAX
        w = written(MMX6Client(), FakeCtx([names.HEART_TANK]), save)
        self.assertNotIn(OFF_LIFE_GAUGE, w)
        self.assertNotIn(OFF_LIFE_GAUGE_ZERO, w)

    def test_a_gauge_that_is_already_right_is_not_rewritten(self) -> None:
        # _grants is re-run every poll; writing an unchanged byte would be
        # pure noise on the wire.
        save = blank_save()
        save[OFF_LIFE_GAUGE] = save[OFF_LIFE_GAUGE_ZERO] = \
            LIFE_GAUGE_BASE + GAUGE_STEP
        w = written(MMX6Client(), FakeCtx([names.HEART_TANK]), save)
        self.assertNotIn(OFF_LIFE_GAUGE, w)
        self.assertNotIn(OFF_LIFE_GAUGE_ZERO, w)

    def test_it_catches_up_a_save_that_only_ever_upgraded_x(self) -> None:
        # Every save made before this fix is in exactly this state, so the
        # first poll after updating has to repair it rather than leave Zero
        # behind forever.
        save = blank_save()
        save[OFF_LIFE_GAUGE] = LIFE_GAUGE_MAX          # X maxed by AP grants
        save[OFF_LIFE_GAUGE_ZERO] = LIFE_GAUGE_BASE    # Zero never touched
        items = [names.HEART_TANK] * 8 + [names.LIFE_UP] * 8
        w = written(MMX6Client(), FakeCtx(items), save)
        self.assertEqual(w.get(OFF_LIFE_GAUGE_ZERO), LIFE_GAUGE_MAX)


class TestHealsClampToWhoeverIsPlaying(unittest.TestCase):
    """The visible half: a heal clamped against X's maximum, written into a
    bar sized by Zero's, draws past its own frame."""

    # Close enough to Zero's 32 that one Large Life Energy overshoots it, but
    # not X's 64. A heal from 1 HP would land at 17 under either gauge and
    # the clamp would never engage - the test would pass without testing
    # anything, which is how the bug survived the suite it already had.
    START_HP = 30

    def heal(self, save):
        """Apply one Large Life Energy at START_HP; return the HP written.

        The cursor has to be primed: a fresh client starts it at the end of
        the received list, so filler already in hand at connect is not
        replayed. Without this the heal is silently skipped.
        """
        client = MMX6Client()
        ctx = FakeCtx([names.LARGE_LIFE_ENERGY])
        client.filler_cursor = 0
        player = bytearray(PLAYER_LEN)
        player[OFF_P_HP] = self.START_HP
        writes, _cursor = client._filler_grants(ctx, bytes(save), bytes(player))
        values = [data[0] for _addr, data in writes]
        self.assertTrue(values, "the heal was not applied at all")
        return values

    def test_the_heal_is_big_enough_to_overshoot_zeros_gauge(self) -> None:
        # Guards the guard: if the heal amount ever shrinks, the two tests
        # below stop discriminating and start passing for free.
        self.assertGreater(self.START_HP + LARGE_LIFE_HEAL, LIFE_GAUGE_BASE)
        self.assertLess(self.START_HP + LARGE_LIFE_HEAL, LIFE_GAUGE_MAX)

    def test_the_offsets_follow_the_character_byte(self) -> None:
        self.assertEqual(_gauge_offsets(bytes(blank_save(char=0))),
                         (OFF_LIFE_GAUGE, OFF_WEAPON_GAUGE))
        self.assertEqual(_gauge_offsets(bytes(blank_save(char=CHAR_ZERO))),
                         (OFF_LIFE_GAUGE_ZERO, OFF_WEAPON_GAUGE_ZERO))

    def test_a_heal_as_zero_does_not_overfill_past_his_gauge(self) -> None:
        # X maxed, Zero at base: the exact save this was found in.
        save = blank_save(char=CHAR_ZERO)
        save[OFF_LIFE_GAUGE] = LIFE_GAUGE_MAX
        save[OFF_LIFE_GAUGE_ZERO] = LIFE_GAUGE_BASE
        hp = self.heal(save)
        self.assertLessEqual(max(hp), LIFE_GAUGE_BASE,
                             "healed past Zero's own maximum")

    def test_the_same_heal_as_x_still_uses_x_s_gauge(self) -> None:
        # The control: the fix must not have simply swapped the bug over.
        save = blank_save(char=0)
        save[OFF_LIFE_GAUGE] = LIFE_GAUGE_MAX
        save[OFF_LIFE_GAUGE_ZERO] = LIFE_GAUGE_BASE
        hp = self.heal(save)
        self.assertGreater(max(hp), LIFE_GAUGE_BASE,
                           "X was clamped to Zero's smaller gauge")


if __name__ == "__main__":
    unittest.main()
