"""Boss HP randomization tests.

X6 keeps a boss's drawn life bar and its real HP in the SAME byte, written at
boss init from an immediate in overlay code. That is the whole reason this is
a disc patch rather than the client-side write X5 uses, and it is why the
range matters: the bar is drawn from fixed pieces that stop at 32 and its
container caps at 127, so a value outside that misdraws.

Every offset in the table was byte-verified against a real disc. What these
tests protect is the arithmetic around them - the clamp, and the rank scaling
that a naive per-level roll would silently invert.
"""
import unittest

from .. import disc


class TestRange(unittest.TestCase):
    def test_the_bounds_are_the_ones_the_bar_can_draw(self) -> None:
        self.assertEqual((disc.BOSS_HP_MIN, disc.BOSS_HP_MAX), (0x20, 0x7F))

    def test_every_roll_lands_inside_the_bounds(self) -> None:
        # Including rolls at the extremes, where a preserved rank increment
        # would otherwise push a higher level past the cap.
        for roll in (disc.BOSS_HP_MIN, 64, disc.BOSS_HP_MAX):
            rolls = {boss: roll for boss in disc.BOSS_HP}
            for label, _w, _r, _van, patched in disc.boss_hp_edits(rolls):
                self.assertGreaterEqual(patched[0], disc.BOSS_HP_MIN, label)
                self.assertLessEqual(patched[0], disc.BOSS_HP_MAX, label)


class TestRankScaling(unittest.TestCase):
    def test_higher_ranks_keep_their_vanilla_increment(self) -> None:
        # Heatnix is the one boss in the table with more than one level:
        # 48 / 52 / 56 in vanilla, so +4 and +8 over level 1.
        edits = {label: patched[0]
                 for label, _w, _r, _v, patched
                 in disc.boss_hp_edits({"Blaze Heatnix": 100})}
        self.assertEqual(edits["Blaze Heatnix L1 HP"], 100)
        self.assertEqual(edits["Blaze Heatnix L3 HP"], 104)
        self.assertEqual(edits["Blaze Heatnix L4 HP"], 108)

    def test_a_high_roll_never_inverts_the_scaling(self) -> None:
        # Rolling each level independently would let level 3 come out below
        # level 1. Clamped at the cap they may become EQUAL, but never lower.
        for roll in range(disc.BOSS_HP_MIN, disc.BOSS_HP_MAX + 1, 7):
            by_level = {}
            for label, _w, _r, _v, patched in disc.boss_hp_edits(
                    {"Blaze Heatnix": roll}):
                by_level[label] = patched[0]
            self.assertLessEqual(by_level["Blaze Heatnix L1 HP"],
                                 by_level["Blaze Heatnix L3 HP"], roll)
            self.assertLessEqual(by_level["Blaze Heatnix L3 HP"],
                                 by_level["Blaze Heatnix L4 HP"], roll)


class TestEdits(unittest.TestCase):
    def test_unrolled_bosses_are_left_alone(self) -> None:
        # A boss missing from the roll must produce NO edit, not an edit to
        # its vanilla value - the latter would collide with nothing today but
        # would make "did this seed change X?" unanswerable from the patch.
        self.assertEqual(disc.boss_hp_edits({}), [])
        only = disc.boss_hp_edits({"Sigma": 64})
        self.assertTrue(all(label.startswith("Sigma ") for label, *_ in only))

    def test_every_edit_declares_its_expected_vanilla_byte(self) -> None:
        # apply_basepatch verifies these as strictly as A1, which is what
        # stops a roll built for one dump corrupting another.
        rolls = {boss: 64 for boss in disc.BOSS_HP}
        for label, _w, _r, van, patched in disc.boss_hp_edits(rolls):
            self.assertEqual(len(van), 1, label)
            self.assertEqual(len(patched), 1, label)

    def test_the_declared_vanilla_matches_the_table(self) -> None:
        rolls = {boss: 64 for boss in disc.BOSS_HP}
        declared = {}
        for label, where, _r, van, _p in disc.boss_hp_edits(rolls):
            declared[where] = van[0]
        for boss, levels in disc.BOSS_HP.items():
            if boss in disc.BOSS_HP_NEVER_ROLLED:
                continue        # emits no edits at all, by design
            for _level, vanilla, offsets in levels:
                for offset in offsets:
                    self.assertEqual(declared[offset], vanilla)

    def test_no_two_bosses_share_an_offset(self) -> None:
        # Two edits writing one offset makes the result order-dependent, and
        # apply_basepatch refuses it outright - better to catch it here.
        seen = set()
        for _boss, levels in disc.BOSS_HP.items():
            for _level, _vanilla, offsets in levels:
                for offset in offsets:
                    self.assertNotIn(offset, seen)
                    seen.add(offset)

    def test_the_x_and_zero_copies_get_the_same_value(self) -> None:
        # Most bosses appear twice, at a fixed 0xBDA0 stride - the X and Zero
        # overlay copies. Giving them different HP would mean the two
        # characters fight measurably different bosses.
        rolls = {boss: 71 for boss in disc.BOSS_HP}
        by_label: dict[str, set[int]] = {}
        for label, _w, _r, _v, patched in disc.boss_hp_edits(rolls):
            by_label.setdefault(label, set()).add(patched[0])
        for label, values in by_label.items():
            self.assertEqual(len(values), 1, f"{label} got {values}")


class TestTutorialBossIsNeverRolled(unittest.TestCase):
    """The intro boss keeps vanilla health however the option is set.

    A real playtest rolled it 32 -> 110: three and a half times vanilla, on the
    tutorial, fought with a bare starting X. It is the first thing any player
    of this world meets.
    """

    def test_it_is_excluded(self) -> None:
        self.assertIn("D-1000", disc.BOSS_HP_NEVER_ROLLED)
        self.assertNotIn("D-1000", disc.rollable_bosses())

    def test_the_exclusion_list_names_real_bosses(self) -> None:
        for boss in disc.BOSS_HP_NEVER_ROLLED:
            self.assertIn(boss, disc.BOSS_HP,
                          f"{boss} is excluded but is not in the table at all")

    def test_rollable_is_everything_else(self) -> None:
        self.assertEqual(
            set(disc.rollable_bosses()),
            set(disc.BOSS_HP) - set(disc.BOSS_HP_NEVER_ROLLED))

    def test_no_edit_is_emitted_even_if_a_roll_is_forced(self) -> None:
        # A caller passing a stale roll dict must not be able to reintroduce
        # it - the builder refuses, not just the roller.
        self.assertEqual(disc.boss_hp_edits({"D-1000": 120}), [])

    def test_excluding_it_does_not_disturb_the_others(self) -> None:
        rolls = {b: 64 for b in disc.rollable_bosses()}
        edits = disc.boss_hp_edits(rolls)
        self.assertTrue(edits)
        self.assertFalse([e for e in edits if e[0].startswith("D-1000")])


if __name__ == "__main__":
    unittest.main()
