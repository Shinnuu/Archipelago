import unittest

from .. import names
from . import MMX5TestBase

FALCON = [names.FALCON_HEAD, names.FALCON_BODY, names.FALCON_ARM, names.FALCON_LEG]
GAEA = [names.GAEA_HEAD, names.GAEA_BODY, names.GAEA_ARM, names.GAEA_LEG]


class TestArmorGating(MMX5TestBase):
    def test_gaea_hearts_require_full_gaea_set(self) -> None:
        hearts = [names.heart_location(s) for s in
                  (names.GRIZZLY, names.KRAKEN, names.FIREFLY, names.ROSERED)]
        self.assertAccessDependency(hearts, [GAEA], only_check_listed=True)

    def test_falcon_gated_locations_require_full_falcon_set(self) -> None:
        locations = [
            names.heart_location(names.WHALE),
            names.capsule_location(names.PEGASUS),
            names.capsule_location(names.DINOREX),
            names.capsule_location(names.ROSERED),
            names.tank_location(names.NECROBAT),
        ]
        self.assertAccessDependency(locations, [FALCON], only_check_listed=True)

    def test_weapon_gated_capsules(self) -> None:
        self.assertAccessDependency([names.capsule_location(names.WHALE)],
                                    [[names.GOO_SHAVER]], only_check_listed=True)
        self.assertAccessDependency([names.capsule_location(names.FIREFLY)],
                                    [[names.CSHOT]], only_check_listed=True)
        self.assertAccessDependency([names.capsule_location(names.NECROBAT)],
                                    [[names.F_LASER]], only_check_listed=True)

    def test_sigma_stages_require_all_weapons(self) -> None:
        weapons = [names.BOSS_WEAPON[s] for s in names.STAGES]
        self.assertAccessDependency([names.VICTORY], [weapons], only_check_listed=True)


class TestLaunchGoal(MMX5TestBase):
    options = {"goal": "launch"}

    def test_launcher_parts_are_progression(self) -> None:
        # Completion requires all 4 Enigma + all 4 Shuttle parts.
        self.collect_all_but([names.ENIGMA_PART])
        self.assertBeatable(False)
        self.collect_by_name(names.ENIGMA_PART)
        self.assertBeatable(True)


class TestGoalSlotData(MMX5TestBase):
    """slot_data is the only channel the goal takes to the client, and the
    client's whole all_mavericks behaviour keys off that one int. Generating
    the option correctly is worthless if the value does not arrive."""
    options = {"goal": "all_mavericks"}

    def test_all_mavericks_reaches_the_client_as_goal_2(self) -> None:
        from ..client import GOAL_ALL_MAVERICKS
        slot_data = self.multiworld.worlds[self.player].fill_slot_data()
        self.assertEqual(slot_data["goal"], GOAL_ALL_MAVERICKS,
                         "the client reads slot_data['goal'] and would fall "
                         "back to the permissive sigma behaviour")

    def test_the_goal_needs_the_eight_weapons_in_logic(self) -> None:
        # Logic gates Sigma on the 8 WEAPONS (items, receivable from any
        # world), while the goal's in-game requirement is 8 KILLS (local only,
        # enforced by the client). Different requirements - this pins the
        # logical half so the two do not silently drift into one another.
        from ..items import item_groups
        self.assertBeatable(False)
        self.collect_by_name(sorted(item_groups["Weapons"]))
        self.assertBeatable(True)


class TestSigmaSlotData(MMX5TestBase):
    options = {"goal": "sigma"}

    def test_sigma_still_reaches_the_client_as_goal_0(self) -> None:
        from ..client import GOAL_SIGMA
        slot_data = self.multiworld.worlds[self.player].fill_slot_data()
        self.assertEqual(slot_data["goal"], GOAL_SIGMA)


class TestLauncherPartsAreNeverInTheEndgame(MMX5TestBase):
    """A part behind Zero Space is a part behind the launch it powers.

    Reported live 2026-09-11 on a sigma-goal seed: the last Shuttle Part sat
    in a Zero Space location, and vanilla fires the shuttle by itself once all
    eight Mavericks are down - so the launch resolved, failed for want of that
    part, and the part stayed on the far side of the endgame it had just
    failed to open. Under this goal the parts are only `useful`, so no
    reachability rule objected and the seed was perfectly winnable; the player
    simply lost the successful-launch route with nothing to tell them why.
    """
    options = {"goal": "sigma", "endgame_checks": True,
               "rematch_checks": True, "pickupsanity": True}

    def endgame_locations(self):
        return self.multiworld.get_region("Sigma Stages", self.player).locations

    def test_the_endgame_actually_holds_locations(self) -> None:
        # Guards every other test in this class: if the region were empty the
        # exclusion below would pass without excluding anything.
        self.assertGreater(len(self.endgame_locations()), 10)

    def test_no_endgame_location_accepts_a_launcher_part(self) -> None:
        for part in (names.ENIGMA_PART, names.SHUTTLE_PART):
            item = self.world.create_item(part)
            for location in self.endgame_locations():
                with self.subTest(part=part, location=location.name):
                    self.assertFalse(location.item_rule(item))

    def test_the_maverick_stages_still_take_them(self) -> None:
        # The rule has to be an endgame exclusion, not a ban - the parts are
        # still items and still want somewhere to go.
        location = self.multiworld.get_location(
            names.boss_location(names.GRIZZLY), self.player)
        for part in (names.ENIGMA_PART, names.SHUTTLE_PART):
            with self.subTest(part=part):
                self.assertTrue(location.item_rule(self.world.create_item(part)))

    def test_another_worlds_item_is_not_caught_by_the_name(self) -> None:
        # item_rule sees every world's items. Another game's "Shuttle Part"
        # (or another MMX5 slot's) has nothing to do with our launch.
        item = self.world.create_item(names.SHUTTLE_PART)
        item.player = self.player + 1
        for location in self.endgame_locations():
            with self.subTest(location=location.name):
                self.assertTrue(location.item_rule(item))

    def test_ordinary_items_still_fit_in_the_endgame(self) -> None:
        item = self.world.create_item(names.SMALL_ENERGY)
        self.assertTrue(any(loc.item_rule(item)
                            for loc in self.endgame_locations()))


class TestLauncherPartsAreExcludedUnderTheLaunchGoalToo(MMX5TestBase):
    """Same rule, the goal where it is a hard error rather than a quiet loss.

    Here the parts are progression, so a part in Sigma Stages is progression
    behind an entrance that needs all eight weapons - and the launch it powers
    happens before the endgame opens at all.
    """
    options = {"goal": "launch", "endgame_checks": True}

    def test_no_endgame_location_accepts_a_launcher_part(self) -> None:
        locations = self.multiworld.get_region("Sigma Stages",
                                               self.player).locations
        for part in (names.ENIGMA_PART, names.SHUTTLE_PART):
            item = self.world.create_item(part)
            for location in locations:
                with self.subTest(part=part, location=location.name):
                    self.assertFalse(location.item_rule(item))


class TestLauncherPartsAreExcludedFromEVERYMMX5Endgame(unittest.TestCase):
    """One X5 slot's parts must not sit behind ANOTHER X5 slot's endgame.

    The constraint belongs to the receiving player's game, not to whose
    locations they are: both slots open Zero Space only after eight kills, and
    both have already fired their own launch by then. Caught by a two-slot
    generation during the 0.7.2 review -
    `Sigma - 1-UP (SecondSlot): Shuttle Part (ClabeMMX5)` - which the
    self-scoped version of the rule allowed through.
    """

    def setUp(self) -> None:
        from test.general import setup_multiworld
        from .. import MMX5World
        self.multiworld = setup_multiworld(
            [MMX5World, MMX5World],
            options={"endgame_checks": True, "rematch_checks": True})

    def endgame_locations(self, player: int):
        return self.multiworld.get_region("Sigma Stages", player).locations

    def test_both_slots_have_an_endgame_to_exclude_from(self) -> None:
        for player in (1, 2):
            with self.subTest(player=player):
                self.assertGreater(len(self.endgame_locations(player)), 10)

    def test_neither_endgame_accepts_either_slots_parts(self) -> None:
        for owner in (1, 2):
            for part in (names.ENIGMA_PART, names.SHUTTLE_PART):
                item = self.multiworld.worlds[owner].create_item(part)
                for host in (1, 2):
                    for location in self.endgame_locations(host):
                        with self.subTest(owner=owner, host=host, part=part,
                                          location=location.name):
                            self.assertFalse(location.item_rule(item))

    def test_a_different_games_item_of_the_same_name_still_fits(self) -> None:
        # The test is SLOT MEMBERSHIP, not the name - another game's
        # "Shuttle Part" has nothing to do with an X5 launch.
        item = self.multiworld.worlds[1].create_item(names.SHUTTLE_PART)
        item.player = 99                      # not an MMX5 slot in this world
        self.assertTrue(any(loc.item_rule(item)
                            for loc in self.endgame_locations(2)))

    def test_the_maverick_stages_still_take_the_other_slots_parts(self) -> None:
        item = self.multiworld.worlds[1].create_item(names.SHUTTLE_PART)
        location = self.multiworld.get_location(
            names.boss_location(names.GRIZZLY), 2)
        self.assertTrue(location.item_rule(item))
