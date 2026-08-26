"""Endgame-check tests.

These ride `0x800CCF36`, the game's progression counter. Its endgame values
are code-verified rather than inferred: the stage-select overlay branches on
exactly 3 and 4 at `ROCK+0x0C2798`, choosing which Secret Lab the screen
offers. What makes them safe as checks is that the counter is MONOTONIC and
persistent - a clear cannot be un-earned by dying, quitting, or loading an
older save - so the properties worth pinning here are the threshold ordering
and the fact that nothing fires early.
"""
import unittest

from . import MMX6TestBase
from .. import names
from ..locations import location_table


class TestEndgameThresholds(unittest.TestCase):
    def test_thresholds_are_distinct_and_ascending(self) -> None:
        # If two shared a threshold they would fire together and one of them
        # would be measuring nothing.
        thresholds = [t for _n, t in names.ENDGAME_CHECKS]
        self.assertEqual(thresholds, sorted(set(thresholds)))

    def test_nothing_fires_before_the_endgame_is_open(self) -> None:
        # Progress 0-2 is intro / stage select. An endgame check firing there
        # would release an item for a stage the player has not seen.
        for progress in (0, 1, 2):
            for _name, threshold in names.ENDGAME_CHECKS:
                self.assertGreater(threshold, progress)

    def test_the_gate_opening_matches_the_souls_gate(self) -> None:
        # 0x800CCF36 >= 3 is the same condition the game's own unlock check
        # uses at 0x8001E41C (`slti 3`), so this fires exactly when the Gate
        # really opens.
        self.assertEqual(
            dict(names.ENDGAME_CHECKS)[names.ENDGAME_UNLOCKED], 3)

    def test_sigma_is_not_an_endgame_check(self) -> None:
        # Clearing Secret Lab 3 IS the goal. A location firing at the same
        # instant as victory adds nothing and could race it.
        names_only = [n for n, _t in names.ENDGAME_CHECKS]
        self.assertNotIn(names.VICTORY, names_only)
        self.assertEqual(len(names.ENDGAME_CHECKS), 3)


class TestEndgameIds(unittest.TestCase):
    def test_ids_sit_in_the_reserved_block(self) -> None:
        # The datapackage is a contract: these were reserved as +180..199 and
        # must not drift into the Reploid block at +200.
        from ..items import BASE_ID
        for i, (name, _t) in enumerate(names.ENDGAME_CHECKS):
            self.assertEqual(location_table[name], BASE_ID + 180 + i)

    def test_ids_are_unique(self) -> None:
        self.assertEqual(len(set(location_table.values())),
                         len(location_table))


class TestEndgameOn(MMX6TestBase):
    options = {"endgame_checks": True}

    def test_the_locations_exist_and_live_in_the_gate(self) -> None:
        for name, _t in names.ENDGAME_CHECKS:
            location = self.multiworld.get_location(name, self.player)
            self.assertEqual(location.parent_region.name, "The Gate")

    def test_they_are_reachable_with_everything(self) -> None:
        self.collect_all_but([])
        for name, _t in names.ENDGAME_CHECKS:
            self.assertTrue(
                self.multiworld.get_location(name, self.player)
                    .can_reach(self.multiworld.state),
                f"{name} unreachable with a full inventory")


class TestEndgameOff(MMX6TestBase):
    options = {"endgame_checks": False}

    def test_the_locations_are_absent(self) -> None:
        for name, _t in names.ENDGAME_CHECKS:
            with self.assertRaises(KeyError):
                self.multiworld.get_location(name, self.player)

    def test_the_seed_still_generates(self) -> None:
        # Turning it off removes locations, which is the direction that can
        # make a seed too full - so this is the combination worth generating.
        self.assertTrue(self.multiworld.get_unfilled_locations(self.player)
                        is not None)


if __name__ == "__main__":
    unittest.main()
