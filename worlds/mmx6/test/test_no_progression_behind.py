"""`no_progression_behind` - nothing you NEED behind a requirement you named.

The option excludes locations rather than changing rules, and that is the
whole safety argument: an excluded location still exists, is still reachable
by exactly the same rules, and still sends its item - it just holds junk. So a
wrong entry here can cost a player a better item placement, and can never
strand a seed the way a wrong access rule can.

Two things these tests pin that nothing else would:

* the CLASSIFICATION matches the RULES. `PICKUP_GATES` and `REPLOID_GATES` say
  which locations are behind Shadow and which behind mobility, and the access
  rules are built from the same tables - but the exclusions are applied from
  the tables while reachability comes from the rules, so a mistake in either
  direction is invisible until someone checks that a location classified
  "spikes" really is the set you cannot reach without the Shadow Armor. That
  is `test_the_spike_set_is_exactly_what_shadow_opens`, done by behaviour.
* the guard refuses an option set that cannot be filled. Archipelago fills
  excluded locations from FILLER alone - `useful` items are not eligible - and
  this world creates filler only as padding, so the junk available is exactly
  `locations - items`. Exclude more than that and generation dies at the end
  of fill with a stack trace. Both sides of that boundary are tested, because
  a guard that is one out either refuses a seed that would have worked or
  admits one that will not.
"""
from BaseClasses import CollectionState, LocationProgressType
from Options import OptionError

from . import MMX6TestBase
from .. import GATE_CLASSES, gated_locations, names


def _excluded(world_test) -> set:
    return {loc.name for loc in
            world_test.multiworld.get_locations(world_test.player)
            if loc.progress_type == LocationProgressType.EXCLUDED}


class TestNothingNamed(MMX6TestBase):
    """The default. An empty list is the base game's deal."""
    options = {"no_progression_behind": []}

    def test_nothing_is_excluded(self) -> None:
        self.assertEqual(_excluded(self), set())


class TestSpikes(MMX6TestBase):
    options = {"no_progression_behind": ["spikes"], "reploid_checks": True}

    def test_it_excludes_exactly_the_shadow_set(self) -> None:
        self.assertEqual(_excluded(self), gated_locations("shadow", True))

    def test_the_named_pickups_are_in_it(self) -> None:
        # Spelled out once, so a table edit that silently emptied the class
        # would fail here rather than pass an equality against itself.
        for location in (names.heart_location(names.TURTLOID),
                         names.heart_location(names.SHELDON),
                         names.tank_location(names.SHELDON),
                         names.tank_location(names.WOLFANG)):
            self.assertIn(location, _excluded(self), location)
        self.assertIn(names.reploid_location(names.SHELDON, 9), _excluded(self))

    def test_the_locations_still_exist_and_are_still_reachable(self) -> None:
        # Excluded is not removed. The check is still there to be collected,
        # and the rules that gate it have not moved.
        state = self.multiworld.get_all_state()
        for name in _excluded(self):
            self.assertTrue(
                self.multiworld.get_location(name, self.player).can_reach(state),
                name)

    def test_the_spike_set_is_exactly_what_shadow_opens(self) -> None:
        # BEHAVIOUR, not the table: hand the player everything except the
        # Shadow parts and assert that the locations which go dark are exactly
        # the ones this class excludes. Catches a row classified into the
        # wrong bucket, and a rule that stopped matching its table entry.
        state = CollectionState(self.multiworld)
        for name in names.WEAPONS + names.BLADE_PARTS + [names.ZERO]:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        dark = {loc.name for loc in self.multiworld.get_locations(self.player)
                if loc.address is not None and not loc.can_reach(state)}
        self.assertEqual(dark, gated_locations("shadow", True))


class TestMovement(MMX6TestBase):
    options = {"no_progression_behind": ["movement"], "reploid_checks": True}

    def test_it_excludes_exactly_the_mobility_set(self) -> None:
        self.assertEqual(_excluded(self), gated_locations("mob", True))

    def test_the_movement_set_is_exactly_what_zero_or_blade_opens(self) -> None:
        state = CollectionState(self.multiworld)
        for name in names.WEAPONS + names.SHADOW_PARTS:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        dark = {loc.name for loc in self.multiworld.get_locations(self.player)
                if loc.address is not None and not loc.can_reach(state)}
        self.assertEqual(dark, gated_locations("mob", True))


class TestAll(MMX6TestBase):
    """`all` on its own, which is what most people who want this will write."""
    options = {"no_progression_behind": ["all"], "reploid_checks": True}

    def test_all_expands_to_every_class(self) -> None:
        expected = set()
        for gate in GATE_CLASSES.values():
            expected |= gated_locations(gate, True)
        self.assertEqual(_excluded(self), expected)

    def test_the_seed_is_still_beatable(self) -> None:
        # The point of the option: a seed nobody has to do any of that for.
        # `test_fill`, which the base class runs for these options, is the
        # other half - it proves fill can place everything with those 53
        # locations off the table.
        self.assertBeatable(False)
        self.collect_by_name(names.WEAPONS)
        self.assertBeatable(True)

    def test_case_does_not_matter(self) -> None:
        option = self.world.options.no_progression_behind
        option.value = {"SPIKES", "Movement"}
        self.assertEqual(option.classes, {"spikes", "movement"})


class TestExactlyEnoughFiller(MMX6TestBase):
    """The accepting edge of the guard, generated for real.

    No Reploid checks, no Parts, no Zero item: 28 items into 32 locations, so
    create_items pads with exactly 4 junk items - and `spikes` excludes
    exactly 4 locations. One fewer and fill would fail. The base class runs a
    full `test_fill` for these options, which is the assertion that matters.
    """
    options = {"reploid_checks": False, "endgame_checks": True,
               "parts_in_pool": False, "zero_unlock": False,
               "stage_unlocks": False, "secret_armors_in_pool": False,
               "no_progression_behind": ["spikes"]}

    def test_the_excluded_count_is_the_filler_count(self) -> None:
        items, locations = self.world._capacity()
        self.assertEqual(len(self.world._excluded_locations()),
                         locations - items)


class TestTheFillerGuard(MMX6TestBase):
    """The refusing edge, and that it names a way out."""
    options = {}

    def _refuses(self, **option_values) -> str:
        world = self.multiworld.worlds[self.player]
        before = {name: getattr(world.options, name).value
                  for name in option_values}
        for name, value in option_values.items():
            getattr(world.options, name).value = value
        try:
            with self.assertRaises(OptionError) as caught:
                world.generate_early()
            return str(caught.exception)
        finally:
            for name, value in before.items():
                getattr(world.options, name).value = value

    def test_a_seed_with_no_junk_to_spare_is_refused(self) -> None:
        # 29 items into 29 locations leaves zero filler, and `all` wants 12
        # excluded. Before this guard existed that combination generated
        # happily and then died inside Fill.py with
        # "Not enough filler items for excluded locations" - a stack trace at
        # the end of generation, naming nothing the player could change.
        message = self._refuses(reploid_checks=0, endgame_checks=0,
                                parts_in_pool=0, zero_unlock=1,
                                no_progression_behind={"all"})
        self.assertIn("exclude 12 locations", message)
        self.assertIn("0 junk items", message)
        # An error that names no fix is a dead end.
        self.assertIn("reploid_checks", message)
        self.assertIn("no_progression_behind", message)

    def test_reploid_checks_is_the_way_out_it_claims_to_be(self) -> None:
        # The message leads with reploid_checks, so it had better work.
        world = self.multiworld.worlds[self.player]
        world.options.reploid_checks.value = 1
        world.options.no_progression_behind.value = {"all"}
        try:
            world.generate_early()      # must not raise
        finally:
            world.options.no_progression_behind.value = set()

    def test_the_default_options_have_junk_to_spare(self) -> None:
        items, locations = self.world._capacity()
        self.assertLessEqual(len(self.world._excluded_locations()),
                             locations - items)
