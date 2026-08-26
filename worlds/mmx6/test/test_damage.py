"""Weapon damage randomization tests.

The dataset is byte-verified against a real disc, so what these pin is the
behaviour around it: that boss weaknesses survive, that a charged shot can
never come out weaker than its uncharged form, and that the three kinds of
entry which must never move (no damage, instant kill, inert state) do not.
"""
import unittest

from .. import damage


class TestVanillaData(unittest.TestCase):
    def test_the_region_is_the_right_size(self) -> None:
        self.assertEqual(len(damage.VANILLA),
                         damage.TABLE_COUNT * damage.TABLE_STRIDE)
        self.assertEqual(damage.TABLE_STRIDE, 0xA0)

    def test_every_weapon_id_is_in_range(self) -> None:
        for group, ids in damage.WEAPON_GROUPS.items():
            for weapon_id in ids:
                self.assertGreaterEqual(weapon_id, 1, group)
                self.assertLessEqual(weapon_id, damage.TABLE_ENTRIES, group)

    def test_no_weapon_id_is_in_two_groups(self) -> None:
        # A shared id would be rolled twice and produce two edits writing one
        # byte, which apply_basepatch refuses outright.
        seen: dict[int, str] = {}
        for group, ids in damage.WEAPON_GROUPS.items():
            for weapon_id in ids:
                self.assertNotIn(weapon_id, seen,
                                 f"{weapon_id} in {group} and {seen.get(weapon_id)}")
                seen[weapon_id] = group


class TestScaling(unittest.TestCase):
    def test_damage_never_reaches_zero(self) -> None:
        for value in range(1, 0x7F):
            self.assertGreaterEqual(damage.scale_damage(value, 0.001), 1)

    def test_scaling_never_produces_the_instant_kill_marker(self) -> None:
        # 0x7F means "instant kill". A big roll landing on it would silently
        # convert an ordinary attack into one.
        for value in range(1, 0x7F):
            self.assertLess(damage.scale_damage(value, 99.0),
                            damage.INSTANT_KILL)

    def test_a_scale_of_one_changes_nothing(self) -> None:
        self.assertEqual(damage.damage_edits(
            {g: 1.0 for g in damage.WEAPON_GROUPS}), [])

    def test_entries_that_must_not_move(self) -> None:
        self.assertFalse(damage.is_scalable(0x00, damage.NO_DAMAGE))
        self.assertFalse(damage.is_scalable(0x00, damage.INSTANT_KILL))
        self.assertFalse(damage.is_scalable(damage.INERT_STATE, 0x04))

    def test_inert_rows_with_real_damage_are_still_skipped(self) -> None:
        # Thirteen entries carry state 0xFF AND a non-zero damage byte, so
        # skipping on the damage byte alone would edit them.
        inert = [(t, w)
                 for t in range(damage.TABLE_COUNT)
                 for w in range(1, damage.TABLE_ENTRIES + 1)
                 if damage.entry(t, w)[0] == damage.INERT_STATE
                 and damage.entry(t, w)[1] != damage.NO_DAMAGE]
        self.assertTrue(inert, "the dataset should still contain these")
        edited = {(int(label.split(" t")[1].split(" w")[0]),
                   int(label.split(" w")[1]))
                  for label, *_ in damage.damage_edits(
                      {g: 2.5 for g in damage.WEAPON_GROUPS})}
        for pair in inert:
            self.assertNotIn(pair, edited)


class TestChargedNeverWeaker(unittest.TestCase):
    """IDs 1-9 are the uncharged weapons and 10-18 their charged twins, in the
    same order. Because a group rolls once, the ordering has to survive."""

    PAIRS = tuple((i, i + 9) for i in range(1, 10))

    def test_the_pairs_share_a_group(self) -> None:
        by_id = {weapon_id: group
                 for group, ids in damage.WEAPON_GROUPS.items()
                 for weapon_id in ids}
        for uncharged, charged in self.PAIRS:
            self.assertEqual(by_id[uncharged], by_id[charged],
                             f"{uncharged}/{charged} rolled separately")

    def test_charged_stays_at_least_as_strong(self) -> None:
        for scale in (0.25, 0.5, 0.9, 1.0, 1.3, 2.0, 2.5):
            scales = {g: scale for g in damage.WEAPON_GROUPS}
            new = {(t, w): v for t, w, v in _applied(scales)}
            for table in range(damage.TABLE_COUNT):
                for uncharged, charged in self.PAIRS:
                    u_state, u_dmg = damage.entry(table, uncharged)
                    c_state, c_dmg = damage.entry(table, charged)
                    if not (damage.is_scalable(u_state, u_dmg)
                            and damage.is_scalable(c_state, c_dmg)):
                        continue
                    if c_dmg < u_dmg:
                        continue        # already weaker in vanilla
                    self.assertGreaterEqual(
                        new.get((table, charged), c_dmg),
                        new.get((table, uncharged), u_dmg),
                        f"table {table} weapon {uncharged}->{charged} "
                        f"at scale {scale}")


class TestWeaknessesSurvive(unittest.TestCase):
    def test_a_weapon_keeps_its_best_and_worst_targets(self) -> None:
        # The whole point of scaling per weapon rather than per entry: which
        # bosses a weapon is good against must not change.
        scales = {g: 1.8 for g in damage.WEAPON_GROUPS}
        new = {(t, w): v for t, w, v in _applied(scales)}
        for group, ids in damage.WEAPON_GROUPS.items():
            for weapon_id in ids:
                before, after = [], []
                for table in range(damage.TABLE_COUNT):
                    state, dmg = damage.entry(table, weapon_id)
                    if not damage.is_scalable(state, dmg):
                        continue
                    before.append((dmg, table))
                    after.append((new.get((table, weapon_id), dmg), table))
                if len(before) < 2:
                    continue
                # Pairwise, so ties cannot make this pass or fail by luck:
                # wherever one target took strictly more damage than another,
                # it must still take at least as much.
                after_by_table = dict((t, d) for d, t in after)
                for dmg_a, table_a in before:
                    for dmg_b, table_b in before:
                        if dmg_a <= dmg_b:
                            continue
                        self.assertGreaterEqual(
                            after_by_table[table_a], after_by_table[table_b],
                            f"{group} id {weapon_id}: table {table_a} "
                            f"({dmg_a}) fell below table {table_b} ({dmg_b})")


def _applied(scales):
    for label, address, _region, _van, patched in damage.damage_edits(scales):
        table = int(label.split(" t")[1].split(" w")[0])
        weapon = int(label.split(" w")[1])
        yield table, weapon, patched[0]


if __name__ == "__main__":
    unittest.main()
