"""Soft locks: what the game can force on a player, and where fill may hide things.

The logic review of 2026-09-25 (research repo,
`ai-docs/plans/2026-09-25_logic-review-scope.md`). These pin the safety
argument before any rule moves, because the failures they guard against are
the ones X5 and X6 only found with real seeds in testers' hands:

* X5 (2026-08-06): two stages' Access Codes placed inside Sigma's stage, which
  needed those stages beaten - a hard deadlock that still "won" the
  playthrough, because the endgame rule only looked at weapons. MM8's Wily
  rule asks for every `<Boss> Beaten` event, and each event sits behind its
  stage's codes, so the deadlock is impossible by construction - but nothing
  pinned that until this file.
* MM8's own: the game FORCES Duo. Beating the fourth set-1 boss sets phase 2,
  and the hub plays ROCK8_2 and puts the player in Duo's stage with no stage
  select, no Lab and no Exit out until he is cleared (ram-notes 9f). Logic
  cannot stop a player walking into that, so Duo's clear must need nothing a
  player might not have at that moment.
"""
import itertools
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from . import MM8TestBase
from .. import MM8World, names

# (stage_unlocks, pickupsanity, rematch_checks) x goal: every combination that
# changes the location graph. The other options only touch the disc.
SWEEP = [dict(zip(("stage_unlocks", "pickupsanity", "rematch_checks", "goal"), combo))
         for combo in itertools.product((False, True), (False, True), (False, True),
                                        ("wily", "robot_masters"))]
SEEDS_PER_COMBINATION = 10     # a fill takes ~10 ms: 160 seeds in a couple of seconds


def generate(seed: int, options: dict, players: int = 1):
    """A filled multiworld, the way Generate.py makes one."""
    multiworld = setup_multiworld([MM8World] * players, seed=seed, options=options)
    distribute_items_restrictive(multiworld)
    call_all(multiworld, "post_fill")
    return multiworld


def stage_of(location) -> str:
    return location.parent_region.name


class SeedChecks:
    """The invariants every generated seed must hold, per MM8 slot."""

    def check_seed(self, multiworld, player: int) -> None:
        state = CollectionState(multiworld)
        state.sweep_for_advancements()
        unreachable = [loc.name for loc in multiworld.get_locations(player)
                       if not loc.can_reach(state)]
        self.assertEqual(unreachable, [], "locations no sweep reaches")
        self.assertTrue(multiworld.has_beaten_game(state, player), "not beatable")

        for location in multiworld.get_locations(player):
            item = location.item
            if item is None or item.name not in names.ACCESS_ITEMS:
                continue
            # Only this slot's own codes lock this slot's stages.
            if item.player != player:
                continue
            stage = item.name.removesuffix(" Access Codes")
            self.assertNotIn(stage_of(location), names.WILY_STAGES,
                             f"{item.name} placed in {location.name}, behind the "
                             "Wily gate that needs that stage beaten")
            self.assertNotEqual(stage_of(location), stage,
                                f"{item.name} placed in {location.name}, inside the "
                                "stage it unlocks")


class TestSeedSweep(SeedChecks, unittest.TestCase):
    """Real fills across every option that shapes the graph, several seeds each."""

    def test_every_combination(self) -> None:
        for options in SWEEP:
            for seed in range(SEEDS_PER_COMBINATION):
                with self.subTest(seed=seed, **options):
                    self.check_seed(generate(seed, options), 1)


class TestTwoSlots(SeedChecks, unittest.TestCase):
    """Two MM8 slots in one multiworld (X5's two-slot control). MM8 has no
    item whose use has passed (X5's launcher parts), so the cross-slot concern
    is only that each slot's own rules still hold with a second copy of every
    item name in the pool, and that the two discs are told apart."""
    options = {"stage_unlocks": True, "pickupsanity": True, "rematch_checks": True}

    def test_both_slots(self) -> None:
        for seed in range(SEEDS_PER_COMBINATION):
            multiworld = generate(seed, self.options, players=2)
            for player in (1, 2):
                with self.subTest(seed=seed, player=player):
                    self.check_seed(multiworld, player)
            with self.subTest(seed=seed, check="seed stamps"):
                stamps = {multiworld.worlds[p].seed_stamp() for p in (1, 2)}
                self.assertEqual(len(stamps), 2, "both slots stamp their discs alike")


class TestCodesStayAheadOfWily(MM8TestBase):
    """The rule-level half of the X5 deadlock: with any one stage's codes
    missing, nothing else in the pool may open Wily. A fill test only catches
    this when fill happens to try the bad placement; this catches the rule."""
    options = {"stage_unlocks": True, "pickupsanity": True}

    def test_wily_needs_every_access_code(self) -> None:
        world = self.multiworld.worlds[self.player]
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        for boss in names.ROBOT_MASTERS:
            if boss == world.starting_stage:
                continue                        # precollected: cannot be withheld
            with self.subTest(withheld=boss):
                state = CollectionState(self.multiworld)
                for item in pool:
                    if item.name != names.access_item(boss):
                        state.collect(item, True)
                state.sweep_for_advancements()
                self.assertFalse(state.can_reach(names.WILY_1, "Region", self.player),
                                 f"Wily opened without {boss}'s codes")
                self.assertFalse(state.has(names.beaten(boss), self.player))

    def test_everything_opens_wily(self) -> None:
        # The control: the same state WITH every code does open it.
        state = CollectionState(self.multiworld)
        for item in self.multiworld.itempool:
            if item.player == self.player:
                state.collect(item, True)
        state.sweep_for_advancements()
        self.assertTrue(state.can_reach(names.WILY_1, "Region", self.player))


LAB = {names.shop_location(part): part for part in names.PARTS}


def play_the_lab(multiworld, player: int, choose) -> tuple[bool, dict]:
    """Play a filled seed buying Lab entries in the order `choose` picks, and
    say whether it still ends with the whole Lab bought, the goal beaten and
    every location reached.

    The player: every non-Lab location logic reaches, plus the items of the
    entries BOUGHT, whatever their rules say (the game does not know logic).
    The Lab sells the start stock always and the post-Duo stock once Duo is
    cleared; a purchase needs the bolts received, less those spent, to cover
    its price. Bolts received count every Bolts item, whatever its
    classification - the client counts them all."""
    size = multiworld.worlds[player].options.bolt_bundle_size.value

    def sweep(bought):
        state, reached, bundles = CollectionState(multiworld), set(), 0
        grew = True
        while grew:
            grew = False
            for loc in multiworld.get_locations():
                if loc in reached or loc.item is None:
                    continue
                if loc.player == player and loc.name in LAB:
                    if LAB[loc.name] not in bought:
                        continue
                elif not loc.can_reach(state):
                    continue
                reached.add(loc)
                state.collect(loc.item, True, loc)
                bundles += loc.item.player == player and loc.item.name == names.BOLTS
                grew = True
        return state, reached, bundles

    bought: list[str] = []
    while True:
        state, reached, bundles = sweep(set(bought))
        left = bundles * size - sum(names.LAB_PRICE[p] for p in bought)
        stock = list(names.START_STOCK)
        if state.has(names.DUO_CLEARED, player):
            stock += names.POST_DUO_STOCK
        affordable = [p for p in stock if p not in bought and names.LAB_PRICE[p] <= left]
        if not affordable:
            break
        bought.append(choose(affordable))
    mine = [loc for loc in multiworld.get_locations(player) if loc.item is not None]
    beaten = multiworld.has_beaten_game(state, player)
    ok = len(bought) == len(names.PARTS) and beaten and all(loc in reached for loc in mine)
    return ok, {"bought": len(bought), "beaten": beaten,
                "unreached": sum(loc not in reached for loc in mine)}


def losing_orders(multiworld, player: int, rng, random_orders: int = 2) -> list:
    """Purchase orders that lose the seed: for every Lab entry holding an
    advancement item, spend on everything else first (non-advancement,
    post-Duo, dearest first); then a few random orders."""
    item_of = {p: multiworld.get_location(names.shop_location(p), player).item for p in names.PARTS}
    losses = []
    for target in names.PARTS:
        if not item_of[target].advancement:
            continue

        def spend_elsewhere(affordable, target=target):
            others = sorted((p for p in affordable if p != target),
                            key=lambda p: (item_of[p].advancement, p in names.START_STOCK,
                                           -names.LAB_PRICE[p]))
            return others[0] if others else target

        ok, info = play_the_lab(multiworld, player, spend_elsewhere)
        if not ok:
            losses.append((target, item_of[target].name, info))
    for _ in range(random_orders):
        ok, info = play_the_lab(multiworld, player, rng.choice)
        if not ok:
            losses.append(("random order", None, info))
    return losses


class TestLabPurchaseOrder(unittest.TestCase):
    """Pre-release review B1 (2026-09-26). Bolts never come back, and the Lab
    sells whatever is in stock, in logic or not - so no order of purchases may
    lose a seed. Reachability tests cannot see this (a sweep never spends), so
    this plays the Lab adversarially on real fills. The start stock had been
    in logic at 21 with anything in it; after Duo the Lab also sells 19 bolts'
    worth more, and spending there first stranded an entry holding progression
    in 117 of 183 seeds."""
    EXTREMES = [dict(bolt_bundle_size=1, bolt_surplus=0), dict(bolt_bundle_size=2, bolt_surplus=40,
                                                               stage_unlocks=True, pickupsanity=True),
                dict(bolt_bundle_size=3, bolt_surplus=100), dict(bolt_bundle_size=20, bolt_surplus=0),
                dict(bolt_bundle_size=5, bolt_surplus=100)]

    def test_no_purchase_order_loses_a_seed(self) -> None:
        import random
        rng = random.Random(8)
        for options in SWEEP + self.EXTREMES:
            for seed in range(2):
                with self.subTest(seed=seed, **options):
                    self.assertEqual(losing_orders(generate(seed, options), 1, rng), [])

    def test_the_old_rule_loses_seeds(self) -> None:
        """The control: with the start stock free to hold anything (the old
        rule), the same search finds losing orders - still, with the bundles
        placed first (fill_hook): 22 of 25 seeds at surplus 0, 6 of 25 at the
        defaults. Not at surplus 100, whose spare bundles now mask it - so the
        item rule is the guarantee, the fill order only makes it rarer."""
        import random
        from unittest import mock
        original = MM8World.set_rules

        def old_rules(world):
            original(world)
            for part in names.START_STOCK:
                world.multiworld.get_location(names.shop_location(part), world.player).item_rule = \
                    lambda item: True

        rng = random.Random(8)
        with mock.patch.object(MM8World, "set_rules", old_rules):
            lost = sum(bool(losing_orders(generate(seed, dict(bolt_surplus=0)), 1, rng))
                       for seed in range(10))
        self.assertGreater(lost, 0)


class TestSmallBundlesFill(unittest.TestCase):
    """Review B2 (2026-09-26). The Lab counts Bolts items - 21, then 40 of
    them at bundle size 1 - and fill closed the Lab to everything placed after
    the bundles thinned out, so sizes 1-3 failed fill now and then. MM8World.
    fill_hook places the bundles first."""
    SMALL = [dict(bolt_bundle_size=1, bolt_surplus=0), dict(bolt_bundle_size=1, bolt_surplus=0, pickupsanity=True),
             dict(bolt_bundle_size=2, bolt_surplus=40, stage_unlocks=True, pickupsanity=True),
             dict(bolt_bundle_size=2, bolt_surplus=0, stage_unlocks=True),
             dict(bolt_bundle_size=3, bolt_surplus=40, stage_unlocks=True)]

    def test_small_bundles_always_fill(self) -> None:
        for options in self.SMALL:
            for seed in range(20):
                with self.subTest(seed=seed, **options):
                    generate(seed, options)

    def test_without_the_hook_they_did_not(self) -> None:
        """The control: bundles placed wherever the shuffle puts them."""
        from unittest import mock
        from Fill import FillError
        failed = 0
        with mock.patch.object(MM8World, "fill_hook", lambda *args: None):
            for seed in range(20):
                try:
                    generate(seed, dict(bolt_bundle_size=1, bolt_surplus=0))
                except FillError:
                    failed += 1
        self.assertGreater(failed, 0)


class ForcedDuo:
    """At the moment the game forces Duo, the player has beaten set 1 and may
    hold NOTHING else - items arrive in any order, and the Lab and the set-1
    stages are out of reach until Duo is cleared. So Duo's clear must be in
    logic from exactly that: the four set-1 Beaten events, no items."""

    def forced_state(self) -> CollectionState:
        state = CollectionState(self.multiworld)
        for boss in names.SET_1:
            state.collect(self.world.create_item(names.beaten(boss)), True)
        return state

    def test_duo_clears_on_set_1_alone(self) -> None:
        state = self.forced_state()
        self.assertTrue(self.multiworld.get_location(names.DUO_CLEAR, self.player).can_reach(state),
                        "the game forces Duo here, and logic says he cannot be cleared")
        self.assertTrue(self.multiworld.get_location(names.DUO_CLEARED, self.player).can_reach(state))

    def test_not_before_set_1(self) -> None:
        # The control: the game does not force Duo before the fourth kill.
        for missing in names.SET_1:
            state = CollectionState(self.multiworld)
            for boss in names.SET_1:
                if boss != missing:
                    state.collect(self.world.create_item(names.beaten(boss)), True)
            with self.subTest(missing=missing):
                self.assertFalse(
                    self.multiworld.get_location(names.DUO_CLEAR, self.player).can_reach(state))


class TestForcedDuo(ForcedDuo, MM8TestBase):
    pass


class TestForcedDuoWithStageUnlocks(ForcedDuo, MM8TestBase):
    options = {"stage_unlocks": True}
