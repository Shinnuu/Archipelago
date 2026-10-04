"""Reachability: the stage structure, the Lab's bolt gates, and the bolts."""
from BaseClasses import CollectionState, ItemClassification
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

    def test_duo_opens_on_set_1_alone(self):
        # The game forces Duo after the fourth set-1 kill (test_soft_locks).
        self.multiworld.state.sweep_for_advancements()
        self.assertTrue(self.can_reach_location(names.DUO_CLEAR))
        self.assertTrue(self.multiworld.state.has(names.DUO_CLEARED, self.player))

    def test_duo_bolts_need_mega_ball_and_thunder_claw(self):
        """Bolt 1 the Mega Ball; bolt 2, past bolt 1's ladder, both (0.2.1:
        the guide gives bolt 2 only what it adds)."""
        self.multiworld.state.sweep_for_advancements()
        first, second = bolts.PLAY_ORDER[names.DUO]
        self.assertFalse(self.can_reach_location(bolt(first)))
        for items in ([names.MEGA_BALL], [names.THUNDER_CLAW]):
            collected = self.collect_by_name(items)
            self.assertFalse(self.can_reach_location(bolt(second)), items)
            self.assertEqual(self.can_reach_location(bolt(first)), items == [names.MEGA_BALL], items)
            self.remove(collected)
        self.collect_by_name([names.MEGA_BALL, names.THUNDER_CLAW])
        for sub_id in (first, second):
            self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)

    def test_set_2_needs_duo_mega_ball_and_thunder_claw(self):
        self.multiworld.state.sweep_for_advancements()
        for items in ([], [names.MEGA_BALL], [names.THUNDER_CLAW]):
            collected = self.collect_by_name(items)
            for boss in names.SET_2:
                self.assertFalse(self.can_reach_region(boss), (boss, items))
            self.remove(collected)
        self.collect_by_name([names.MEGA_BALL, names.THUNDER_CLAW])
        for boss in names.SET_2:
            self.assertTrue(self.can_reach_region(boss), boss)
            if boss not in (names.SWORD, names.SEARCH):
                self.assertTrue(self.can_reach_location(names.boss_location(boss)), boss)
        # Sword Man also sits past his stage's four trials, Search Man past
        # doors only Tornado Hold opens (test_soft_locks).
        self.assertFalse(self.can_reach_location(names.boss_location(names.SWORD)))
        self.assertFalse(self.can_reach_location(names.boss_location(names.SEARCH)))
        self.collect_by_name([names.SEARCH_DOORS])
        self.assertTrue(self.can_reach_location(names.boss_location(names.SEARCH)))
        self.collect_by_name([w for w in names.SWORD_TRIALS if w != names.SEARCH_DOORS])
        self.assertTrue(self.can_reach_location(names.boss_location(names.SWORD)))

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

    def test_start_stock_needs_the_whole_lab(self):
        """0.2.0: the start stock is in logic at 40, not its own 21 - the price
        of letting it hold anything (review B1; TestLabPurchaseOrder)."""
        entry = names.shop_location(names.EXIT)
        bundles = self.get_items_by_name(names.BOLTS)
        need = -(-FULL_STOCK_COST // 5)                        # 8 bundles
        self.assertGreater(need, -(-START_STOCK_COST // 5))    # more than 0.1.0's 5
        self.collect(bundles[:need - 1])
        self.assertFalse(self.can_reach_location(entry))
        self.collect(bundles[need - 1])
        self.assertTrue(self.can_reach_location(entry))

    def test_every_entry_may_hold_anything(self):
        """0.2.0 (Ivor, 2026-09-29): the start stock may hold Access Codes and
        other progression, like the post-Duo stock always could."""
        required, spare = self.world.create_item(names.MEGA_BALL), self.world.create_item(names.EXTRA_LIFE)
        for part in names.PARTS:
            entry = self.multiworld.get_location(names.shop_location(part), self.player)
            self.assertTrue(entry.item_rule(required), part)
            self.assertTrue(entry.item_rule(spare), part)

    def test_only_the_bundles_logic_counts_are_progression(self):
        """Review B2: logic counts bolts up to 40 - eight bundles of 5; the
        other four of the twelve are useful, so fill need not place them early."""
        kinds = [item.classification for item in self.get_items_by_name(names.BOLTS)]
        self.assertEqual(sum(bool(k & ItemClassification.progression) for k in kinds), 8)
        self.assertEqual(kinds.count(ItemClassification.useful), 4)

    def test_post_duo_stock_needs_duo_and_40(self):
        # Duo's clear is free once set 1 is (and set 1 is free here), so a
        # sweep would collect it: build the state without one.
        entry = self.multiworld.get_location(names.shop_location(names.HYPER_SLIDER), self.player)
        bundles = self.get_items_by_name(names.BOLTS)
        need = -(-FULL_STOCK_COST // 5)                        # 8 bundles
        state = CollectionState(self.multiworld)
        for bundle in bundles[:need]:
            state.collect(bundle, True)
        self.assertFalse(entry.can_reach(state))               # no Duo yet
        state.collect(self.world.create_item(names.DUO_CLEARED), True)
        self.assertTrue(entry.can_reach(state))
        state.remove(bundles[need - 1])
        self.assertFalse(entry.can_reach(state))


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

    def test_clown_with_the_tester_s_flame_sword_and_tornado_hold(self):
        """The report behind 0.2.1: with Flame Sword + Tornado Hold, 0.2.0
        held every Clown bolt back for the Rush Bike and the Mega Ball. Now
        bolt 2 is free and bolt 4 (the lift room's top) is in on Tornado Hold;
        bolt 3 still wants the guide's Mega Ball, and bolt 5 the Mega Ball the
        0.2.1 review added (its room is walled in on the map)."""
        self.multiworld.state.sweep_for_advancements()
        b1, b2, b3, b4, b5 = bolts.PLAY_ORDER[names.CLOWN]
        self.assertTrue(self.can_reach_location(bolt(b2)))
        for sub_id in (b1, b3, b4, b5):
            self.assertFalse(self.can_reach_location(bolt(sub_id)), sub_id)
        self.collect_by_name([names.FLAME_SWORD, names.TORNADO_HOLD])
        for sub_id in (b2, b4):
            self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)
        for sub_id in (b1, b3, b5):
            self.assertFalse(self.can_reach_location(bolt(sub_id)), sub_id)
        self.collect_by_name(names.MEGA_BALL)
        for sub_id in (b3, b5):
            self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)
        self.assertFalse(self.can_reach_location(bolt(b1)))
        self.collect_by_name(names.RUSH_BIKE)
        self.assertTrue(self.can_reach_location(bolt(b1)))

    def test_clown_bolt_4_on_either_climb(self):
        self.multiworld.state.sweep_for_advancements()
        b4 = bolts.PLAY_ORDER[names.CLOWN][3]
        for item in (names.MEGA_BALL, names.TORNADO_HOLD):
            collected = self.collect_by_name(item)
            self.assertTrue(self.can_reach_location(bolt(b4)), item)
            self.remove(collected)

    def test_frost_without_astro_crush(self):
        """The other report: every Frost bolt waited on Astro Crush. Now
        only bolt 5, under a floor only Astro Crush opens, does; bolt 6's
        block also breaks to Flame Sword or Flash Bomb; the first two need
        nothing and the next two the Mega Ball."""
        self.multiworld.state.sweep_for_advancements()
        b1, b2, b3, b4, b5, b6 = bolts.PLAY_ORDER[names.FROST]
        for sub_id in (b1, b2):
            self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)
        self.collect_by_name(names.MEGA_BALL)
        for sub_id in (b3, b4):
            self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)
        for sub_id in (b5, b6):
            self.assertFalse(self.can_reach_location(bolt(sub_id)), sub_id)
        flame = self.collect_by_name(names.FLAME_SWORD)
        self.assertTrue(self.can_reach_location(bolt(b6)))
        self.assertFalse(self.can_reach_location(bolt(b5)))
        self.remove(flame)
        self.collect_by_name(names.ASTRO_CRUSH)
        for sub_id in (b5, b6):
            self.assertTrue(self.can_reach_location(bolt(sub_id)), sub_id)


class TestRobotMastersGoal(MM8TestBase):
    options = {"goal": "robot_masters"}

    def test_goal_without_wily(self):
        # Set 2 needs Duo (free once set 1 is) plus Mega Ball + Thunder Claw,
        # and Sword Man his four trials' weapons.
        self.assertBeatable(False)
        self.collect_by_name([names.MEGA_BALL, names.THUNDER_CLAW])
        self.assertBeatable(False)
        self.collect_by_name([names.TORNADO_HOLD, names.ICE_WAVE, names.FLASH_BOMB])
        self.assertBeatable(True)


class TestCapacity(MM8TestBase):
    def test_overfull_pool_is_refused(self):
        """80 one-bolt bundles + 30 fixed items cannot fit 75 locations. The
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
            self.assertIn("room for 45", str(caught.exception))
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
