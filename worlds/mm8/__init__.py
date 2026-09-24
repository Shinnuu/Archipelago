"""Archipelago world for Mega Man 8 (PS1, NTSC-U, SLUS-00453).

Scaffold stage: generation and reachability rules only. The disc patch and the
BizHawkClient are not written yet, so a generated seed has no patch output and
cannot be played - `generate_output` is deliberately absent rather than
half-implemented, the way the X6 world was built. Research notes live in the
private `mm8-ap-research` repo; the design is
`ai-docs/plans/2026-09-24_mm8-v1-design.md` there.

The shape follows the Mega Man X5 and X6 worlds, which share this game's
platform, client architecture and most of its problems.
"""
import math
from typing import Any

from BaseClasses import Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from . import bolts, names
from .items import MM8Item, event_table, item_groups, item_table
from .locations import MM8Location, location_groups, location_table
from .options import MM8Options

# What the Lab asks for before logic expects a player to shop. Bolts are not
# renewable - the pool is the only source - so a "the k-th purchase needs the
# k cheapest prices" rule would let a player buy an expensive entry first and
# strand a cheap one holding progression. Instead an entry is in logic only
# once the bolts received cover EVERYTHING in stock at that point, which no
# purchase order can break. v1-design 4.
# The patched prices (names.LAB_PRICE), not the vanilla ones.
START_STOCK_COST = sum(names.LAB_PRICE[p] for p in names.START_STOCK)   # 21
FULL_STOCK_COST = sum(names.LAB_PRICE.values())                         # 40


class MM8Web(WebWorld):
    theme = "partyTime"
    bug_report_page = "https://github.com/Shinnuu/Archipelago/issues"
    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Mega Man 8 with Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Shinnuu"],
    )
    tutorials = [setup_en]


class MM8World(World):
    """
    Mega Man 8 is the eighth entry in Capcom's classic Mega Man series, released
    for the PlayStation in 1997. A meteor carrying a strange energy crashes to
    Earth, Dr. Wily gets there first, and Mega Man sets out across eight Robot
    Master stages - with Duo, a robot from beyond the stars, following the same
    trail.
    """
    game = "Mega Man 8"
    web = MM8Web()

    options_dataclass = MM8Options
    options: MM8Options

    item_name_to_id = {name: data.code for name, data in item_table.items()
                       if data.code is not None}
    location_name_to_id = location_table
    item_name_groups = item_groups
    location_name_groups = location_groups

    # The OLDEST client this world is known to work with - from the newest
    # PUBLISHED Archipelago release (0.6.7), never from the checkout's
    # Utils.__version__, which is unreleased. The server enforces this against
    # every client, so too high a value locks everyone out (X5 v0.1.0).
    required_client_version = (0, 6, 7)

    # 8 weapons + Mega Ball + 4 Rush adapters + 17 parts.
    FIXED_ITEMS = len(names.WEAPON_SLOT) + len(names.RUSH) + len(names.PARTS)

    def bolt_bundles(self) -> int:
        """How many "Bolts" items the pool carries: enough for the whole Lab,
        plus the surplus option, in bundles of the chosen size."""
        wanted = FULL_STOCK_COST * (100 + self.options.bolt_surplus.value) / 100
        return math.ceil(wanted / self.options.bolt_bundle_size.value)

    def generate_early(self) -> None:
        # Checked HERE because Generate.py retries a world that raises later,
        # and overshooting the location count passes silently otherwise and
        # just drops items. Both learned the hard way on X5.
        items = self.FIXED_ITEMS + self.bolt_bundles()
        if items > len(location_table):
            room = len(location_table) - self.FIXED_ITEMS
            raise OptionError(
                f"Mega Man 8 ({self.player_name}): {self.bolt_bundles()} bolt "
                f"bundles do not fit - the pool has room for {room}. Raise "
                f"`bolt_bundle_size` (now {self.options.bolt_bundle_size.value}) "
                f"or lower `bolt_surplus` (now {self.options.bolt_surplus.value}).")

    def create_item(self, name: str) -> MM8Item:
        data = item_table.get(name) or event_table[name]
        return MM8Item(name, data.classification, data.code, self.player)

    def _event(self, region: Region, name: str) -> None:
        """An event location named after the event item it holds."""
        location = MM8Location(self.player, name, None, region)
        location.place_locked_item(self.create_item(name))
        region.locations.append(location)

    def _region(self, name: str, locations: list[str]) -> Region:
        region = Region(name, self.player, self.multiworld)
        region.add_locations({loc: location_table[loc] for loc in locations}, MM8Location)
        self.multiworld.regions.append(region)
        return region

    def _stage_bolts(self, stage: str) -> list[str]:
        return [bolts.BOLT_LOCATIONS[s] for s, st in sorted(bolts.BOLT_STAGE.items())
                if st == stage]

    def create_regions(self) -> None:
        menu = self._region("Menu", [])
        intro = self._region(names.INTRO,
                             self._stage_bolts(names.INTRO) + [names.MEGA_BALL_LOCATION])
        stage_select = self._region("Stage Select", [])
        menu.connect(intro)
        intro.connect(stage_select)

        for boss in names.ROBOT_MASTERS:
            locs = [names.boss_location(boss)] + self._stage_bolts(boss)
            locs += [names.midboss_location(boss) for r in names.RUSH
                     if names.RUSH_STAGE[r] == boss]
            region = self._region(boss, locs)
            self._event(region, names.beaten(boss))
            stage_select.connect(region)

        duo = self._region(names.DUO, self._stage_bolts(names.DUO) + [names.DUO_CLEAR])
        self._event(duo, names.DUO_CLEARED)
        stage_select.connect(duo)

        previous = stage_select
        for i, wily in enumerate(names.WILY_STAGES):
            region = self._region(wily, [names.WILY_CLEAR[wily]] if i < 3 else [])
            previous.connect(region)
            previous = region
        self._event(previous, names.VICTORY)

        lab = self._region(names.LAB, [names.shop_location(p) for p in names.PARTS])
        stage_select.connect(lab)

    def create_items(self) -> None:
        pool = [self.create_item(name) for name in names.WEAPON_SLOT]
        pool += [self.create_item(name) for name in names.RUSH]
        pool += [self.create_item(name) for name in names.PARTS]
        pool += [self.create_item(names.BOLTS) for _ in range(self.bolt_bundles())]

        # Over-full is caught in generate_early; by here it is too late to
        # report cleanly.
        unfilled = len(self.multiworld.get_unfilled_locations(self.player))
        assert len(pool) <= unfilled, "pool overflow should have been caught in generate_early"
        pool += [self.create_item(self.get_filler_item_name())
                 for _ in range(unfilled - len(pool))]
        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        player = self.player
        size = self.options.bolt_bundle_size.value

        def entrance(name: str):
            return self.multiworld.get_entrance(name, player)

        def location(name: str):
            return self.multiworld.get_location(name, player)

        # --- Stage structure: the game's own, keyed on BOSSES not weapons ---
        # In the base game the gates read the weapon array; the disc patch
        # (A1) moves them onto a boss record, because in a randomizer the
        # weapon a boss awards is somebody else's item.
        #
        # Duo additionally needs Mega Ball and Thunder Claw, which are what its
        # two bolts need. Whether Duo's stage can be REPLAYED is not known
        # (v1-design R7); if it cannot, entering without them would lose those
        # checks for good, so logic never sends a player in without them.
        set_1_beaten = [names.beaten(b) for b in names.SET_1]
        entrance(f"Stage Select -> {names.DUO}").access_rule = \
            lambda state: (state.has_all(set_1_beaten, player)
                           and state.has_all((names.MEGA_BALL, names.THUNDER_CLAW), player))
        for boss in names.SET_2:
            entrance(f"Stage Select -> {boss}").access_rule = \
                lambda state: state.has(names.DUO_CLEARED, player)

        # The Wily stages open on all eight bosses. Also asking for all eight
        # WEAPONS is deliberately stricter than the game - nobody has checked
        # what the Wily stages demand, and strict only narrows placement.
        all_beaten = [names.beaten(b) for b in names.ROBOT_MASTERS]
        entrance(f"Stage Select -> {names.WILY_1}").access_rule = \
            lambda state: (state.has_all(all_beaten, player)
                           and state.has_all(names.WEAPONS, player))

        # --- Bolts ---------------------------------------------------------
        for sub_id, name in bolts.BOLT_LOCATIONS.items():
            requirement = bolts.requirement(sub_id)
            if requirement:
                location(name).access_rule = \
                    lambda state, req=requirement: all(state.has_any(clause, player)
                                                       for clause in req)

        # --- The Lab ---------------------------------------------------------
        def bolts_held(state) -> int:
            return state.count(names.BOLTS, player) * size

        for part in names.START_STOCK:
            location(names.shop_location(part)).access_rule = \
                lambda state: bolts_held(state) >= START_STOCK_COST
        for part in names.POST_DUO_STOCK:
            location(names.shop_location(part)).access_rule = \
                lambda state: (state.has(names.DUO_CLEARED, player)
                               and bolts_held(state) >= FULL_STOCK_COST)

        if self.options.goal == self.options.goal.option_robot_masters:
            self.multiworld.completion_condition[player] = \
                lambda state: state.has_all(all_beaten, player)
        else:
            self.multiworld.completion_condition[player] = \
                lambda state: state.has(names.VICTORY, player)

    def get_filler_item_name(self) -> str:
        filler, weights = zip(*names.FILLER_WEIGHTS)
        return self.random.choices(filler, weights=weights, k=1)[0]

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "goal": self.options.goal.value,
            "bolt_bundle_size": self.options.bolt_bundle_size.value,
        }
