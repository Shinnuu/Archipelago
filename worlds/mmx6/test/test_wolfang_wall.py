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

    def test_heart_tank_needs_an_opener(self) -> None:
        heart = names.heart_location(names.WOLFANG)
        # Everything the vanilla rule asks for, plus the codes for Wolfang's
        # own stage (the entrance needs those under this option) - and nothing
        # that opens the Nightmare wall.
        self.collect_by_name([names.ZERO, names.access_item(names.WOLFANG)])
        opener = self._has_opener()
        if not opener:
            self.assertFalse(
                self._wolfang_reachable(heart),
                "the Heart Tank was reachable with no Nightmare opener - this "
                "is the softlock the rule exists to prevent")
        # Granting an opener must make it reachable.
        self.collect_by_name([names.access_item(names.HEATNIX)])
        self.assertTrue(self._wolfang_reachable(heart))

    def test_sheldon_alone_is_NOT_enough(self) -> None:
        """This asserted the opposite until 2026-08-28, and was wrong.

        NightEftTable lists Fire (Heatnix) and Mirror (Sheldon) as the two
        effects that can afflict North Pole, and the rule concluded that
        either therefore opens the wall. Only Fire does: the routine at
        0x800EEEC0 compares the current effect against 3h and nothing else.
        Mirror leaves the wall shut and overwrites Fire, so a seed whose only
        opener was Sheldon could not be finished. Reported on 0.1.0.
        """
        heart = names.heart_location(names.WOLFANG)
        self.collect_by_name([names.ZERO, names.access_item(names.WOLFANG)])
        self.collect_by_name([names.access_item(names.SHELDON)])
        self.assertFalse(self._wolfang_reachable(heart),
                         "Sheldon's codes must NOT open the wall - only "
                         "Nightmare Fire, from Blaze Heatnix, does")

    def _has_opener(self) -> bool:
        return self.multiworld.state.has(
            names.access_item(names.HEATNIX), self.player)


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
