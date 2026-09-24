"""Reachability: the stage structure, the Lab's bolt gates, and the bolts."""
from Options import OptionError

from . import MM8TestBase
from .. import bolts, names
from .. import START_STOCK_COST, FULL_STOCK_COST


def bolt(sub_id: int) -> str:
    return bolts.BOLT_LOCATIONS[sub_id]


class TestStructure(MM8TestBase):
    def test_intro_and_set_1_open(self):
        self.multiworld.state.sweep_for_advancements()
        for loc in (names.MEGA_BALL_LOCATION, bolt(0), bolt(1), bolt(33)):
            self.assertTrue(self.can_reach_location(loc), loc)
        for boss in names.SET_1:
            self.assertTrue(self.can_reach_location(names.boss_location(boss)), boss)
        for boss in names.SET_2:
            self.assertFalse(self.can_reach_location(names.boss_location(boss)), boss)

    def test_duo_needs_mega_ball_and_thunder_claw(self):
        self.multiworld.state.sweep_for_advancements()
        self.assertFalse(self.can_reach_region(names.DUO))
        self.collect_by_name(names.MEGA_BALL)
        self.assertFalse(self.can_reach_region(names.DUO))
        self.collect_by_name(names.THUNDER_CLAW)
        self.assertTrue(self.can_reach_region(names.DUO))

    def test_set_2_opens_on_duo(self):
        self.collect_by_name([names.MEGA_BALL, names.THUNDER_CLAW])
        for boss in names.SET_2:
            self.assertTrue(self.can_reach_location(names.boss_location(boss)), boss)

    def test_wily_needs_all_eight_weapons(self):
        self.collect_by_name(names.MEGA_BALL)
        weapons = self.collect_by_name(names.WEAPONS)
        self.assertTrue(self.can_reach_region(names.WILY_1))
        self.remove([weapons[-1]])
        self.assertFalse(self.can_reach_region(names.WILY_1))

    def test_wily_chain(self):
        self.collect_by_name([names.MEGA_BALL] + names.WEAPONS)
        for wily in names.WILY_STAGES:
            self.assertTrue(self.can_reach_region(wily), wily)
        self.assertBeatable(True)


class TestLab(MM8TestBase):
    options = {"bolt_bundle_size": 5, "bolt_surplus": 40}

    def test_bundle_count(self):
        # 40 * 1.4 = 56 -> 12 bundles of 5
        self.assertEqual(len(self.get_items_by_name(names.BOLTS)), 12)

    def test_start_stock_needs_21(self):
        entry = names.shop_location(names.EXIT)
        bundles = self.get_items_by_name(names.BOLTS)
        need = -(-START_STOCK_COST // 5)                       # 5 bundles
        self.collect(bundles[:need - 1])
        self.assertFalse(self.can_reach_location(entry))
        self.collect(bundles[need - 1])
        self.assertTrue(self.can_reach_location(entry))

    def test_post_duo_stock_needs_duo_and_40(self):
        entry = names.shop_location(names.HYPER_SLIDER)
        bundles = self.get_items_by_name(names.BOLTS)
        need = -(-FULL_STOCK_COST // 5)                        # 8 bundles
        self.collect(bundles[:need])
        self.assertFalse(self.can_reach_location(entry))       # no Duo yet
        self.collect_by_name([names.MEGA_BALL, names.THUNDER_CLAW])
        self.assertTrue(self.can_reach_location(entry))
        self.remove([bundles[need - 1]])
        self.assertFalse(self.can_reach_location(entry))


class TestBoltRules(MM8TestBase):
    def test_bolt_14_on_either_weapon(self):
        self.multiworld.state.sweep_for_advancements()
        self.assertFalse(self.can_reach_location(bolt(14)))
        for weapon in (names.HOMING_SNIPER, names.ASTRO_CRUSH):
            items = self.collect_by_name(weapon)
            self.assertTrue(self.can_reach_location(bolt(14)), weapon)
            self.remove(items)

    def test_rest_of_tengu_free(self):
        self.multiworld.state.sweep_for_advancements()
        for sub_id in (11, 12, 13):
            self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)

    def test_clown_over_gated_on_rush_bike(self):
        """Which Clown bolt needs the Rush Bike is not known yet, so all of
        them do."""
        everything_else = [names.MEGA_BALL, names.FLAME_SWORD, names.TORNADO_HOLD]
        self.collect_by_name(everything_else)
        for sub_id, stage in bolts.BOLT_STAGE.items():
            if stage == names.CLOWN:
                self.assertFalse(self.can_reach_location(bolt(sub_id)), sub_id)
        self.collect_by_name(names.RUSH_BIKE)
        for sub_id, stage in bolts.BOLT_STAGE.items():
            if stage == names.CLOWN:
                self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)


class TestRobotMastersGoal(MM8TestBase):
    options = {"goal": "robot_masters"}

    def test_goal_without_wily(self):
        # Set 2 needs Duo, and Duo needs Mega Ball + Thunder Claw - nothing else.
        self.collect_by_name([names.MEGA_BALL, names.THUNDER_CLAW])
        self.assertBeatable(True)


class TestCapacity(MM8TestBase):
    def test_overfull_pool_is_refused(self):
        """80 one-bolt bundles + 30 fixed items cannot fit 74 locations. The
        world must refuse in generate_early, naming a fix, rather than let
        Archipelago drop items silently."""
        world = self.multiworld.worlds[self.player]
        size, surplus = world.options.bolt_bundle_size.value, world.options.bolt_surplus.value
        world.options.bolt_bundle_size.value = 1
        world.options.bolt_surplus.value = 100
        try:
            with self.assertRaises(OptionError) as caught:
                world.generate_early()
            self.assertIn("80 bolt bundles", str(caught.exception))
            self.assertIn("room for 44", str(caught.exception))
            self.assertIn("bolt_bundle_size", str(caught.exception))
        finally:
            world.options.bolt_bundle_size.value = size
            world.options.bolt_surplus.value = surplus

    def test_largest_surplus_at_default_size_fits(self):
        world = self.multiworld.worlds[self.player]
        surplus = world.options.bolt_surplus.value
        world.options.bolt_surplus.value = 100      # 80 bolts = 16 bundles of 5
        try:
            world.generate_early()
        finally:
            world.options.bolt_surplus.value = surplus
