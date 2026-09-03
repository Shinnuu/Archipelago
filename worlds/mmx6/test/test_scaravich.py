"""`scaravich_no_progression` tests.

Central Museum builds itself out of totem-pole rooms the game picks at
random - four of eight per entry - and its Heart Tank, its Blade Armor Helmet
and fifteen of its sixteen Reploids sit behind that roll. A player hunting one
specific check can be made to walk the stage over and over.

The option marks every location in that stage excluded, so the fill puts only
junk there. Two halves, and they fail differently:

  * the WORLD half - excluding the wrong set, or excluding nothing, is silent:
    a seed still generates, it just quietly keeps progression behind the dice;
  * the CLIENT half - policy 3 normally withholds a granted armor part until
    its own capsule is checked, which under this option would hold the Blade
    Helmet hostage to a room the player may never roll. That is precisely the
    thing the option exists to stop, so the hold is dropped for this stage
    and this stage only.

The client half is the one worth the most care: dropping the hold for every
stage would re-open the bug policy 3 exists for (a part bit set early stops
its own capsule spawning), so the negative cases below matter as much as the
positive one.
"""
import unittest

from BaseClasses import LocationProgressType

from .. import names
from ..client import OFF_ARMOR_PARTS, SAVE_BASE, SAVE_LEN, MMX6Client
from ..locations import location_table
from . import MMX6TestBase


class FakeItem:
    def __init__(self, name: str) -> None:
        self.name = name
        self.item = name


class FakeCtx:
    def __init__(self, items=(), checked=(), slot_data=None) -> None:
        self.items_received = [FakeItem(i) for i in items]
        self.item_names = type(
            "N", (), {"lookup_in_game": staticmethod(lambda i: i)})
        self.checked_locations = {location_table[c] for c in checked}
        self.slot_data = slot_data or {}
        self.finished_game = False


def written(client, ctx) -> dict:
    """{offset: value} for what _grants would write into a blank save."""
    return {addr - SAVE_BASE: data[0]
            for addr, data in client._grants(ctx, bytes(SAVE_LEN))}


class TestExcludedOn(MMX6TestBase):
    options = {"scaravich_no_progression": True}

    def _scaravich_locations(self):
        return self.multiworld.get_region(names.SCARAVICH, 1).locations

    def test_every_location_in_the_stage_is_excluded(self) -> None:
        locs = self._scaravich_locations()
        self.assertTrue(locs, "the stage region has no locations at all")
        for loc in locs:
            self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED,
                             f"{loc.name} was left available to progression")

    def test_it_covers_the_two_the_randomness_actually_hides(self) -> None:
        # The Heart Tank and the Blade Helmet capsule are the named casualties
        # in the placements doc; if a refactor ever moved them out of the
        # region, the blanket assertion above would still pass vacuously.
        names_here = {loc.name for loc in self._scaravich_locations()}
        self.assertIn(names.heart_location(names.SCARAVICH), names_here)
        self.assertIn(names.capsule_location(names.SCARAVICH), names_here)

    def test_the_stage_reploids_are_in_it_too(self) -> None:
        # Fifteen of the sixteen are exhibit-locked. They ride in the same
        # region, so they inherit the exclusion - pin it rather than assume.
        names_here = {loc.name for loc in self._scaravich_locations()}
        self.assertEqual(
            len([n for n in names_here if n.startswith(names.SCARAVICH)
                 and n not in (names.boss_location(names.SCARAVICH),
                               names.heart_location(names.SCARAVICH),
                               names.capsule_location(names.SCARAVICH))]),
            16)

    def test_no_other_stage_is_touched(self) -> None:
        for stage in names.STAGES:
            if stage == names.SCARAVICH:
                continue
            for loc in self.multiworld.get_region(stage, 1).locations:
                self.assertNotEqual(
                    loc.progress_type, LocationProgressType.EXCLUDED,
                    f"{loc.name} was excluded and should not have been")

    def test_the_option_reaches_the_client(self) -> None:
        self.assertEqual(
            self.world.fill_slot_data()["scaravich_no_progression"], 1)


class TestExcludedOff(MMX6TestBase):
    options = {"scaravich_no_progression": False}

    def test_nothing_is_excluded_by_default(self) -> None:
        for loc in self.multiworld.get_region(names.SCARAVICH, 1).locations:
            self.assertNotEqual(loc.progress_type,
                                LocationProgressType.EXCLUDED)

    def test_the_option_is_off_in_slot_data(self) -> None:
        self.assertEqual(
            self.world.fill_slot_data()["scaravich_no_progression"], 0)


class TestCapsuleWithholdingExemption(unittest.TestCase):
    """Policy 3, and the one stage it is dropped for."""

    def setUp(self) -> None:
        self.client = MMX6Client()
        self.helmet = names.STAGE_ARMOR_PART[names.SCARAVICH]
        self.bit = names.ARMOR_PART_BIT[self.helmet]

    def test_the_helmet_is_still_held_when_the_option_is_off(self) -> None:
        ctx = FakeCtx(items=[self.helmet], slot_data={})
        self.assertEqual(written(self.client, ctx).get(OFF_ARMOR_PARTS, 0)
                         & self.bit, 0)

    def test_the_helmet_is_handed_over_when_the_option_is_on(self) -> None:
        ctx = FakeCtx(items=[self.helmet],
                      slot_data={"scaravich_no_progression": 1})
        self.assertEqual(written(self.client, ctx).get(OFF_ARMOR_PARTS, 0)
                         & self.bit, self.bit)

    def test_checking_the_capsule_still_releases_it_either_way(self) -> None:
        for slot in ({}, {"scaravich_no_progression": 1}):
            ctx = FakeCtx(items=[self.helmet],
                          checked=[names.capsule_location(names.SCARAVICH)],
                          slot_data=slot)
            self.assertEqual(written(self.client, ctx).get(OFF_ARMOR_PARTS, 0)
                             & self.bit, self.bit)

    def test_the_exemption_does_not_leak_to_other_stages(self) -> None:
        # The whole point of policy 3 is that setting a part bit early stops
        # that capsule spawning. Exempting every stage would restore that bug,
        # so this is the assertion that keeps the fix narrow.
        for stage, part in names.STAGE_ARMOR_PART.items():
            if stage == names.SCARAVICH:
                continue
            ctx = FakeCtx(items=[part],
                          slot_data={"scaravich_no_progression": 1})
            bit = names.ARMOR_PART_BIT[part]
            self.assertEqual(
                written(self.client, ctx).get(OFF_ARMOR_PARTS, 0) & bit, 0,
                f"{part} was released by the Scaravich exemption")
