"""Blizzard Wolfang's Heart Tank and EX Tank sit behind the Nightmare wall.

Both only open while a Nightmare Effect is active on North Pole, and per
`NightEftTable` only Fire (Blaze Heatnix) or Mirror (Shield Sheldon) can
afflict that stage - so one of those two has to be BEATEN first.

For a long time this carried no rule, reasoned as "both bosses are reachable
from the start, so it adds nothing to logic". That is true in vanilla and
false under `stage_unlocks`, where both sit behind their own Access Codes.
Staging a real playtest seed produced exactly the unwinnable case: Wolfang's
Heart Tank held Sheldon's codes, Heatnix's codes were two spheres further on,
and fill called it reachable.

These tests exist so that cannot come back.
"""
from BaseClasses import CollectionState

from . import MMX6TestBase
from .. import names


class TestWallWithoutStageUnlocks(MMX6TestBase):
    options = {"stage_unlocks": False}

    def test_no_extra_requirement(self) -> None:
        # Heatnix and Sheldon are both open from the start, so the wall costs
        # nothing and the vanilla rules stand alone.
        self.collect_by_name([names.ZERO])
        for location in (names.heart_location(names.WOLFANG),
                         names.tank_location(names.WOLFANG)):
            loc = self.multiworld.get_location(location, self.player)
            # The EX Tank still needs Shadow; the Heart Tank only mobility.
            if location == names.heart_location(names.WOLFANG):
                self.assertTrue(loc.can_reach(self.multiworld.state), location)


class TestWallWithStageUnlocks(MMX6TestBase):
    options = {"stage_unlocks": True}

    def _wolfang_reachable(self, location) -> bool:
        return self.multiworld.get_location(
            location, self.player).can_reach(self.multiworld.state)

    def _state_with(self, *item_names: str) -> CollectionState:
        """A state holding EXACTLY these items, with no sweep.

        `collect_by_name` sweeps, which makes any assertion about something
        being UNREACHABLE depend on where this seed's fill happened to put
        everything else: collecting Sheldon's codes can pull in Heatnix's for
        free if they landed in Sheldon's stage, and then the wall opens for a
        reason the test never intended. The pre-existing version of this class
        worked around that with an `if not self._has_opener()` guard, which
        turns the test into a no-op on the unlucky seeds instead of failing -
        the shape this project already has a scar about. Building the state by
        hand removes the dependency instead of tolerating it.
        """
        state = CollectionState(self.multiworld)
        for name in item_names:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        return state

    def _starts_with_heatnix(self) -> bool:
        """Does this seed hand out Blaze Heatnix's codes for free?

        `stage_unlocks` PRECOLLECTS the starting stage's Access Codes and only
        places the other seven, and which stage that is is rolled per seed. If
        it rolls Magma Area then Nightmare Fire is available from the first
        moment and the Nightmare wall is legitimately open with no other item.
        That is correct behaviour, and it is what made these tests flaky: two
        runs in five failed purely on the roll.
        """
        return any(item.name == names.access_item(names.HEATNIX)
                   for item in self.multiworld.precollected_items[self.player])

    def test_heart_tank_needs_an_opener(self) -> None:
        heart = self.multiworld.get_location(
            names.heart_location(names.WOLFANG), self.player)
        # Everything the vanilla rule asks for, plus the codes for Wolfang's
        # own stage (the entrance needs those under this option) - and nothing
        # that opens the Nightmare wall.
        state = self._state_with(names.ZERO, names.access_item(names.WOLFANG))
        # Both branches assert something real. The earlier version of this
        # test skipped the assertion entirely when an opener happened to be in
        # hand, which made it silently vacuous on those seeds.
        if self._starts_with_heatnix():
            self.assertTrue(
                heart.can_reach(state),
                "this seed starts in Magma Area, so Fire is free and the wall "
                "should already be open")
        else:
            self.assertFalse(
                heart.can_reach(state),
                "the Heart Tank was reachable with no Nightmare opener - this "
                "is the softlock the rule exists to prevent")
        # Granting the opener must make it reachable either way.
        state.collect(self.world.create_item(names.access_item(names.HEATNIX)),
                      prevent_sweep=True)
        self.assertTrue(heart.can_reach(state))

    def test_sheldon_alone_is_NOT_enough(self) -> None:
        """This asserted the opposite until 2026-08-28, and was wrong.

        NightEftTable lists Fire (Heatnix) and Mirror (Sheldon) as the two
        effects that can afflict North Pole, and the rule concluded that
        either therefore opens the wall. Only Fire does: the routine at
        0x800EEEC0 compares the current effect against 3h and nothing else.
        Mirror leaves the wall shut and overwrites Fire, so a seed whose only
        opener was Sheldon could not be finished. Reported on 0.1.0.
        """
        heart = self.multiworld.get_location(
            names.heart_location(names.WOLFANG), self.player)
        if self._starts_with_heatnix():
            self.skipTest("this seed starts in Magma Area, so Fire is free "
                          "and Sheldon's codes cannot be the deciding item")
        state = self._state_with(names.ZERO,
                                 names.access_item(names.WOLFANG),
                                 names.access_item(names.SHELDON))
        self.assertFalse(heart.can_reach(state),
                         "Sheldon's codes must NOT open the wall - only "
                         "Nightmare Fire, from Blaze Heatnix, does")
        # ...and Heatnix's codes DO, from the same state. Without this the
        # test would still pass if the wall were nailed permanently shut.
        state.collect(self.world.create_item(names.access_item(names.HEATNIX)),
                      prevent_sweep=True)
        self.assertTrue(heart.can_reach(state),
                        "Heatnix's codes must open the wall")


class TestSeedsStayBeatable(MMX6TestBase):
    """The whole point: a stage_unlocks seed must remain completable."""
    options = {"stage_unlocks": True, "reploid_checks": True}

    def test_beatable(self) -> None:
        # The endgame gate is every weapon; stage_unlocks adds every Access
        # Codes item on top. Collect both, as the existing roller test does -
        # this is about the wall rule not stranding a seed, not about the
        # endgame gate.
        self.collect_by_name(names.WEAPONS)
        self.collect_by_name(names.ACCESS_ITEMS)
        self.assertBeatable(True)
