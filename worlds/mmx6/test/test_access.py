"""Reachability and pool-shape tests for the Mega Man X6 world.

These are the invariants that, on X5, only failed once real seeds existed:
item/location arithmetic that silently drops items, and a logic graph that
looks fine until one rule quietly makes another unreachable.
"""
from . import MMX6TestBase
from .. import names, reploids
from ..items import item_table
from ..locations import location_table

MOBILITY = [[names.ZERO], names.BLADE_PARTS]


class TestDefaultSeed(MMX6TestBase):
    options = {}

    def test_the_goal_needs_the_eight_weapons(self) -> None:
        # Logic gates the endgame on the 8 WEAPONS (items, receivable from any
        # world), while the in-game gate is 3000 Nightmare Souls (local, and
        # free of items). Different requirements - this pins the logical half
        # so the two do not silently drift into one another.
        self.assertBeatable(False)
        self.collect_by_name(names.WEAPONS)
        self.assertBeatable(True)

    def test_pool_fills_every_location(self) -> None:
        # Archipelago drops surplus items SILENTLY, so assert the two counts
        # agree rather than trusting generation to complain.
        real_locations = [loc for loc in self.multiworld.get_locations(self.player)
                          if loc.address is not None]
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(len(pool), len(real_locations))

    def test_reploids_on_by_default(self) -> None:
        reploid_locations = [loc for loc in self.multiworld.get_locations(self.player)
                             if " - Reploid " in loc.name]
        self.assertEqual(len(reploid_locations), 128)

    def test_only_the_roster_reploids_need_items(self) -> None:
        """This asserted that NO Reploid needs items, on the reasoning that
        "walking into a Reploid is execution, not inventory" and that a rule
        would "make 128 checks depend on a guess".

        The first half was never the issue: the question was always whether
        you can REACH the Reploid, not whether you can touch it once there.
        The second half was true only while we had no idea which of a stage's
        sixteen sat where, and `mmx6-reploid-roster.md` ended that. Every gate
        now comes from a landmark this world already gates, so it is not a
        guess about a Reploid, it is the scope of a decision already made.

        Reversed 2026-08-28, after a tester found the Wolfang wall stranding
        seeds: under-gating breaks a run silently, over-gating at worst fails
        generation loudly.
        """
        state = self.multiworld.get_all_state()
        for item in list(state.prog_items[self.player]):
            state.prog_items[self.player][item] = 0
        state.sweep_for_advancements()
        for stage, _index, number, name in reploids.REPLOIDS:
            reachable = self.multiworld.get_location(
                name, self.player).can_reach(state)
            if (stage, number) in reploids.REPLOID_GATES:
                gates = reploids.REPLOID_GATES[(stage, number)]
                # `stage_unlocks` is off in this seed, so "wall" is satisfied
                # (Heatnix is always enterable). Nothing else is: zero_unlock
                # defaults ON, so Zero sits in the POOL rather than being
                # precollected, and with prog_items emptied and no fill run
                # there is no Zero and no armor set. So every row carrying
                # "mob" or "shadow" must be shut, and a wall-only row must
                # still be free - both directions asserted, because an
                # earlier version of this branch asserted nothing for the
                # mob rows and its comment claimed Zero was precollected.
                if set(gates) - {"wall"}:
                    self.assertFalse(
                        reachable, f"{name} is gated on {gates} and should "
                        "not be reachable with an empty inventory")
                else:
                    self.assertTrue(
                        reachable, f"{name} is wall-only, and without "
                        "stage_unlocks the wall is open")
                continue
            self.assertTrue(reachable, f"{name} needs items to reach")

    def test_every_gated_reploid_is_a_real_location(self) -> None:
        # A typo'd stage name or an index outside 1-16 would silently gate
        # nothing at all, which is the failure this whole change exists to
        # prevent. Assert every row lands on a location that exists.
        for (stage, number), gates in reploids.REPLOID_GATES.items():
            self.assertIn(stage, names.STAGES, f"{stage} is not a stage")
            self.assertIn(number, range(1, 17), f"{stage} {number} out of range")
            location = names.reploid_location(stage, number)
            self.multiworld.get_location(location, self.player)
            self.assertTrue(gates, f"{location} has an empty gate tuple")
            for gate in gates:
                self.assertIn(gate, ("wall", "mob", "shadow"))


class TestNoOptions(MMX6TestBase):
    """The minimum seed: 28 items into 29 locations, no Reploids."""
    options = {
        "reploid_checks": False,
        "parts_in_pool": False,
        "zero_unlock": False,
        "secret_armors_in_pool": False,
    }

    def test_beatable(self) -> None:
        self.collect_by_name(names.WEAPONS)
        self.assertBeatable(True)

    def test_no_gauge_upgrades_without_reploids(self) -> None:
        # Life Ups and Energy Ups are carried by Reploids. Without those
        # locations they must not be in the pool at all - otherwise they are
        # 16 items competing for 29 slots.
        pool = {item.name for item in self.multiworld.itempool
                if item.player == self.player}
        self.assertNotIn(names.LIFE_UP, pool)
        self.assertNotIn(names.ENERGY_UP, pool)

    def test_zero_precollected_when_not_an_item(self) -> None:
        precollected = {item.name for item
                        in self.multiworld.precollected_items[self.player]}
        self.assertIn(names.ZERO, precollected)


class TestArmorGating(MMX6TestBase):
    options = {}

    def test_shadow_locations_require_the_full_shadow_set(self) -> None:
        self.assertAccessDependency(
            [names.heart_location(names.TURTLOID),
             names.heart_location(names.SHELDON),
             names.tank_location(names.SHELDON),
             names.tank_location(names.WOLFANG)],
            [names.SHADOW_PARTS], only_check_listed=True)

    def test_mobility_locations_take_zero_or_the_full_blade_set(self) -> None:
        self.assertAccessDependency(
            [names.capsule_location(names.WOLFANG),
             names.capsule_location(names.SHARK),
             names.capsule_location(names.TURTLOID),
             names.capsule_location(names.HEATNIX),
             names.heart_location(names.HEATNIX),
             names.heart_location(names.WOLFANG),
             names.tank_location(names.YAMMARK),
             names.tank_location(names.HEATNIX)],
            MOBILITY, only_check_listed=True)

    def test_the_endgame_requires_all_eight_weapons(self) -> None:
        self.assertAccessDependency([names.VICTORY], [names.WEAPONS],
                                    only_check_listed=True)

    def test_blade_parts_never_need_blade_or_shadow(self) -> None:
        # The one cycle that would break this graph. Blade parts must be
        # obtainable from nothing, or Blade Armor can never be assembled and
        # every Shadow part behind it is stranded with it.
        state = self.multiworld.get_all_state()
        for part in names.ARMOR_PARTS:
            state.remove(self.get_item_by_name(part))
        state.remove(self.get_item_by_name(names.ZERO))
        for stage, part in names.STAGE_ARMOR_PART.items():
            if part not in names.BLADE_PARTS:
                continue
            self.assertTrue(
                self.multiworld.get_location(names.capsule_location(stage),
                                             self.player).can_reach(state),
                f"{part} needs armor to reach, which makes Blade Armor "
                f"unassemblable")


class TestDataIntegrity(MMX6TestBase):
    options = {}

    def test_location_ids_unique(self) -> None:
        self.assertEqual(len(set(location_table.values())), len(location_table))

    def test_item_ids_unique(self) -> None:
        codes = [d.code for d in item_table.values() if d.code is not None]
        self.assertEqual(len(set(codes)), len(codes))

    def test_reploid_stage_blocks(self) -> None:
        # The mapping all 128 locations are derived from: stage bit N owns
        # Reploids N*16 .. N*16+15. Four stages are live-confirmed on it.
        for stage, index, n, _name in reploids.REPLOIDS:
            self.assertIn(index, names.STAGE_REPLOIDS[stage])
            self.assertEqual(index, names.STAGE_REPLOIDS[stage][0] + n - 1)

    def test_reploid_nibble_addressing(self) -> None:
        # Two Reploids per byte, low nibble first - confirmed live by watching
        # 0x800CCFD0 go 0 -> 0x02 -> 0x22 across two rescues.
        self.assertEqual(reploids.reploid_nibble(0), (0x800CCFA8, False))
        self.assertEqual(reploids.reploid_nibble(1), (0x800CCFA8, True))
        self.assertEqual(reploids.reploid_nibble(127), (0x800CCFE7, True))

    def test_every_stage_has_one_armor_part(self) -> None:
        self.assertEqual(sorted(names.STAGE_ARMOR_PART), sorted(names.STAGES))
        self.assertEqual(sorted(names.STAGE_ARMOR_PART.values()),
                         sorted(names.ARMOR_PARTS))


class TestRandomizedOptions(MMX6TestBase):
    """`randomize_options` must never roll a combination that cannot fit.

    On X5 this was a real failure mode: a roll asked for more items than the
    seed had locations and generation dropped the surplus silently. The roller
    turns on the location-adding option instead of refusing.
    """
    options = {"randomize_options": True}

    def test_capacity_holds_after_the_roll(self) -> None:
        world = self.multiworld.worlds[self.player]
        items, locations = world._capacity()
        self.assertLessEqual(items, locations)

    def test_beatable(self) -> None:
        self.collect_by_name(names.WEAPONS)
        # The roll can turn `stage_unlocks` on, and with stages locked the
        # endgame requires every Access Codes item too - deliberately, so
        # fill cannot hide a stage's codes behind the endgame those codes
        # are needed to reach. Collect what this roll actually asked for
        # rather than assuming weapons are the whole gate. Without this the
        # test fails on roughly one run in three, which reads as flake.
        if self.multiworld.worlds[self.player].options.stage_unlocks:
            self.collect_by_name(names.ACCESS_ITEMS)
        self.assertBeatable(True)


class TestCapacityArithmetic(MMX6TestBase):
    """Exhaustive check of the item/location arithmetic.

    Archipelago drops surplus items SILENTLY, so this is the failure that does
    not announce itself - on X5 a working-looking seed quietly lost two items.
    `_capacity` reads nothing but option truthiness, so every combination can
    be checked directly rather than by generating 16 multiworlds.
    """
    options = {}

    def test_every_option_combination_is_either_valid_or_rejected(self) -> None:
        from itertools import product
        from types import SimpleNamespace

        from .. import MMX6World

        for reploid, parts, zero, secret, unlocks, endgame in product(
                (0, 1), repeat=6):
            fake = SimpleNamespace(
                BASE_ITEMS=MMX6World.BASE_ITEMS,
                BASE_LOCATIONS=MMX6World.BASE_LOCATIONS,
                options=SimpleNamespace(reploid_checks=reploid,
                                        parts_in_pool=parts,
                                        zero_unlock=zero,
                                        secret_armors_in_pool=secret,
                                        stage_unlocks=unlocks,
                                        endgame_checks=endgame))
            items, locations = MMX6World._capacity(fake)
            # stage_unlocks adds SEVEN, not eight: the starting stage's codes
            # are precollected rather than placed, so they need no location.
            expected_items = (28 + 16 * reploid + 24 * parts + zero
                              + 2 * secret + 7 * unlocks)
            # endgame_checks adds locations and NO items, so it can only ever
            # make a seed easier to fit - that is why the roller never has to
            # consider turning it off.
            expected_locations = 29 + 128 * reploid + 3 * endgame
            self.assertEqual((items, locations),
                             (expected_items, expected_locations),
                             f"reploid={reploid} parts={parts} zero={zero} "
                             f"secret={secret} unlocks={unlocks} "
                             f"endgame={endgame}")
            if reploid:
                # 157 locations against at most 71 items - always fits, which
                # is why the roller reaches for this option to make room.
                self.assertLessEqual(items, locations)

    def test_the_default_options_fit(self) -> None:
        world = self.multiworld.worlds[self.player]
        items, locations = world._capacity()
        self.assertLessEqual(items, locations)

    def test_an_overfull_option_set_is_refused_not_silently_trimmed(self) -> None:
        # 28 + 24 Parts + Zero + 2 secret armors = 55 items into 29 locations.
        # Archipelago would drop 26 of them without a word; generate_early has
        # to raise instead, and the message has to name a fix that works.
        # endgame_checks is turned off too, so the arithmetic under test is
        # the bare minimum seed rather than one with three bonus locations.
        from Options import OptionError

        world = self.multiworld.worlds[self.player]
        world.options.endgame_checks.value = 0
        world.options.reploid_checks.value = 0
        world.options.parts_in_pool.value = 1
        world.options.zero_unlock.value = 1
        world.options.secret_armors_in_pool.value = 1
        world.options.randomize_options.value = 0
        try:
            with self.assertRaises(OptionError) as caught:
                world.generate_early()
            message = str(caught.exception)
            self.assertIn("55 items", message)
            self.assertIn("29 locations", message)
            self.assertIn("reploid_checks", message)
        finally:
            world.options.reploid_checks.value = 1
            world.options.endgame_checks.value = 1
