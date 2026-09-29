"""Archipelago world for Mega Man 8 (PS1, NTSC-U, SLUS-00453).

Generation, logic, the disc patch and the BizHawk client. A seed writes an
.apmm8 that builds a merged three-track disc (disc.py: every reward handed to
Archipelago, Mega Man X5's decoupled design, plus the options' edits) and
client.py plays it. Playtested to the goal. Research notes
live in the private `mm8-ap-research` repo; the design is
`ai-docs/plans/2026-09-24_mm8-v1-design.md` there.

The shape follows the Mega Man X5 and X6 worlds, which share this game's
platform, client architecture and most of its problems.
"""
import logging
import math
from typing import Any, ClassVar

from BaseClasses import ItemClassification, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World
from worlds.generic.Rules import add_rule

from . import bolts, damage, music, names, pickups
from .items import MM8Item, event_table, item_groups, item_table
from .locations import MM8Location, location_groups, location_table
from .options import RANDOMIZED_OPTIONS, MM8Options
from .client import MM8Client  # noqa: F401  (import registers the client)
from .disc import seed_stamp
from .Rom import MM8Settings, write_patch

# What the Lab asks for before logic expects a player to shop. Bolts are not
# renewable - the pool is the only source - and the game sells whatever is in
# stock, in logic or not, so the Lab's logic has to survive ANY purchase order.
#
# Every entry is in logic at 40 bolts received, the whole Lab, and any entry
# may hold anything - so logic reaches 40 without buying a thing, and 40 buys
# every entry in whatever order (the post-Duo eight also need Duo, since the
# game only stocks them after him). 0.1.0 put the start stock (nine entries,
# 21 bolts) in logic at 21 instead, which is only safe if it holds nothing
# required: after Duo a player holding 21-39 can spend on the post-Duo stock
# first and be left unable to afford a start-stock entry (pre-release review
# B1, 2026-09-26). 0.2.0 trades that early-but-empty start stock for one that
# can hold Access Codes and the like (Ivor, 2026-09-29: "yes to the lab
# entries as long as it doesnt softlock anything" - TestLabPurchaseOrder is the
# guard). The patched prices (names.LAB_PRICE), not the vanilla ones.
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

    settings: ClassVar[MM8Settings]
    settings_key = "mm8_options"

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

    def item_count(self) -> int:
        """Items the pool must hold before filler."""
        items = self.FIXED_ITEMS + self.bolt_bundles()
        if self.options.stage_unlocks:
            items += len(names.ACCESS_ITEMS) - 1          # one is precollected
        return items

    def location_count(self) -> int:
        """Locations this seed actually has (the table lists every possible one)."""
        count = len(location_table) - len(names.ROBOT_MASTERS) - len(pickups.PICKUPS)
        if self.options.rematch_checks:
            count += len(names.ROBOT_MASTERS)
        if self.options.pickupsanity:
            count += len(pickups.PICKUPS)
        return count

    def _roll_options(self) -> None:
        """randomize_options: pick the gameplay options for the player (X5)."""
        for name in RANDOMIZED_OPTIONS:
            option = getattr(self.options, name)
            # Choice exposes its valid values; Toggle is just 0/1.
            values = sorted(set(type(option).options.values())) \
                if getattr(type(option), "options", None) else [0, 1]
            option.value = self.random.choice(values)
        # Make room rather than refuse: pickupsanity adds 42 locations.
        if self.item_count() > self.location_count() and not self.options.pickupsanity:
            self.options.pickupsanity.value = 1
        logging.info("Mega Man 8 (%s): randomize_options rolled %s", self.player_name,
                     ", ".join(f"{n}={getattr(self.options, n).value}" for n in RANDOMIZED_OPTIONS))

    def generate_early(self) -> None:
        if self.options.randomize_options:
            self._roll_options()
        # Checked HERE because Generate.py retries a world that raises later,
        # and overshooting the location count passes silently otherwise and
        # just drops items. Both learned the hard way on X5.
        items, locations = self.item_count(), self.location_count()
        if items > locations:
            room = locations - (items - self.bolt_bundles())
            raise OptionError(
                f"Mega Man 8 ({self.player_name}): {self.bolt_bundles()} bolt "
                f"bundles do not fit - the pool has room for {room}. Raise "
                f"`bolt_bundle_size` (now {self.options.bolt_bundle_size.value}), "
                f"lower `bolt_surplus` (now {self.options.bolt_surplus.value}) "
                f"or add locations with `pickupsanity` (+{len(pickups.PICKUPS)}) or "
                f"`rematch_checks` (+{len(names.ROBOT_MASTERS)}).")

        # stage_unlocks: the one stage open from the start. Always in set 1 -
        # under the vanilla order set 2 only exists after Duo; under an open
        # one its stages still want the Mega Ball and Thunder Claw, so a set-2
        # start would leave only the intro in reach.
        self.starting_stage = self.random.choice(names.SET_1) if self.options.stage_unlocks else None

        # The disc's randomized numbers, rolled once here so the patch and the
        # spoiler read the same values (the spoiler can be written without
        # generate_output running).
        self.weapon_damage_factors: dict[str, float] = {}
        self.weapon_damage_tables = damage.DAMAGE_TABLES_VANILLA
        if self.options.weapon_damage:
            self.weapon_damage_tables, self.weapon_damage_factors = damage.weapon_damage_tables(
                self.options.weapon_damage.value, self.random)
        self.boss_hp_factors: dict[str, float] = {}
        if self.options.boss_hp_randomization:
            self.boss_hp_factors = damage.boss_hp_rolls(
                self.options.boss_hp_randomization.value, self.random)
        self.boss_damage_factors: dict[str, float] = {}
        if self.options.boss_damage:
            self.boss_damage_factors = damage.boss_damage_rolls(self.options.boss_damage.value, self.random)
        self.stage_music: dict[str, str] | None = None
        if self.options.stage_music:
            self.stage_music = music.music_assignment(self.random)
            if self.stage_music is None:        # ~1e-11 per seed, but never silent
                logging.warning("Mega Man 8 (%s): no stage-music deal fitted the disc's "
                                "sound banks; stage music stays vanilla.", self.player_name)

    def create_item(self, name: str) -> MM8Item:
        data = item_table.get(name) or event_table[name]
        classification = data.classification
        if name == names.EXIT and self.options.exit_stage_anytime:
            # The option opens Exit everywhere without the part, and the part
            # then has no effect at all (disc.exit_edits).
            classification = ItemClassification.filler
        return MM8Item(name, classification, data.code, self.player)

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

    def _stage_pickups(self, stage: str) -> list[str]:
        """pickupsanity's locations in a stage (their rules: set_rules, pickups.py)."""
        if not self.options.pickupsanity:
            return []
        return [name for index, _r, _k, name in pickups.PICKUPS if index == names.STAGE_INDEX[stage]]

    def create_regions(self) -> None:
        menu = self._region("Menu", [])
        intro = self._region(names.INTRO, self._stage_bolts(names.INTRO) + [names.MEGA_BALL_LOCATION]
                             + self._stage_pickups(names.INTRO))
        stage_select = self._region("Stage Select", [])
        menu.connect(intro)
        intro.connect(stage_select)

        for boss in names.ROBOT_MASTERS:
            locs = [names.boss_location(boss)] + self._stage_bolts(boss)
            locs += [names.midboss_location(boss) for r in names.RUSH
                     if names.RUSH_STAGE[r] == boss]
            locs += self._stage_pickups(boss)
            region = self._region(boss, locs)
            self._event(region, names.beaten(boss))
            stage_select.connect(region)

        duo = self._region(names.DUO, self._stage_bolts(names.DUO) + [names.DUO_CLEAR])
        self._event(duo, names.DUO_CLEARED)
        stage_select.connect(duo)

        previous = stage_select
        for i, wily in enumerate(names.WILY_STAGES):
            if i < 3:
                locs = [names.WILY_CLEAR[wily]]
            elif self.options.rematch_checks:
                locs = [names.rematch_location(b) for b in names.ROBOT_MASTERS]
            else:
                locs = []
            if wily == names.WILY_3:
                locs.append(names.WILY_3_BASS)
            region = self._region(wily, locs + self._stage_pickups(wily))
            previous.connect(region)
            previous = region
        self._event(previous, names.VICTORY)

        lab = self._region(names.LAB, [names.shop_location(p) for p in names.PARTS])
        stage_select.connect(lab)

    def create_items(self) -> None:
        pool = [self.create_item(name) for name in names.WEAPON_SLOT]
        pool += [self.create_item(name) for name in names.RUSH]
        pool += [self.create_item(name) for name in names.PARTS]
        # Logic counts bolts only up to the whole Lab (FULL_STOCK_COST), so only
        # the bundles that get there are progression; the surplus is useful -
        # less for fill to place with the Lab in mind (review B2; fill_hook).
        needed = math.ceil(FULL_STOCK_COST / self.options.bolt_bundle_size.value)
        bundles = [self.create_item(names.BOLTS) for _ in range(self.bolt_bundles())]
        for bundle in bundles[needed:]:
            bundle.classification = ItemClassification.useful
        pool += bundles
        if self.options.stage_unlocks:
            for boss in names.ROBOT_MASTERS:
                codes = self.create_item(names.access_item(boss))
                if boss == self.starting_stage:
                    self.multiworld.push_precollected(codes)
                else:
                    pool.append(codes)

        # Over-full is caught in generate_early; by here it is too late to
        # report cleanly.
        unfilled = len(self.multiworld.get_unfilled_locations(self.player))
        assert len(pool) <= unfilled, "pool overflow should have been caught in generate_early"
        pool += [self.create_item(self.get_filler_item_name())
                 for _ in range(unfilled - len(pool))]
        self.multiworld.itempool += pool

    def fill_hook(self, progitempool: list, usefulitempool: list, filleritempool: list,
                  fill_locations: list) -> None:
        """Place this world's Bolts items FIRST. Fill places items one at a
        time with everything unplaced assumed found, and pops each world's
        items from the end of this list. A Lab entry is only reachable while
        enough Bolts are still assumed - 40 of them at bundle size 1 (21 for
        the start stock, before 0.2.0) - so with the bundles placed at random
        points, the Lab's 17 locations
        closed to everything placed after the bundles thinned out, and small
        bundle sizes failed fill now and then (1-11 in 100 at sizes 1-3;
        0 with the Lab's rules removed). With the bundles on the map first,
        the Lab stays open for the rest: 0 in 2,900 fills at sizes 1-3."""
        bundles = [item for item in progitempool
                   if item.player == self.player and item.name == names.BOLTS]
        for item in bundles:
            progitempool.remove(item)
        progitempool.extend(bundles)

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
        # Duo is FORCED: the fourth set-1 kill sets phase 2, and the hub plays
        # ROCK8_2 and puts the player in Duo's stage with no stage select, no
        # Lab and no Exit out until he is cleared (ram-notes 9f). So his
        # entrance is set 1 and nothing else - logic must allow what the game
        # compels - and his clear must need nothing. It needs nothing [D]
        # (ram-notes 10b): STAGE09 reads no inventory, Duo (id 80, fought at
        # phase 3 only) takes the buster through damage table 29, and the
        # route down to him has no hook and no spikes. What the stage does
        # need is on its two bolts (Mega Ball, Thunder Claw - bolts.GUIDE),
        # in an upper branch off the route; the stage replays at phase >= 4
        # (Ivor, 2026-09-25), so they can be collected later.
        # test_soft_locks.ForcedDuo is the guard: nothing may be added to
        # Duo's clear that a player forced in might not hold.
        #
        # stage_order (0.2.0) opens all eight from the start (disc.
        # stage_order_edits). Duo is still forced: by set 1 under `open`, by
        # any four kills under `open_any_four` (the disc's counting gate) -
        # either way his clear still needs nothing, and ForcedDuo guards it.
        set_1_beaten = [names.beaten(b) for b in names.SET_1]
        all_beaten = [names.beaten(b) for b in names.ROBOT_MASTERS]
        order = self.options.stage_order
        if order == order.option_open_any_four:
            entrance(f"Stage Select -> {names.DUO}").access_rule = \
                lambda state: state.has_from_list(all_beaten, player, 4)
        else:
            entrance(f"Stage Select -> {names.DUO}").access_rule = \
                lambda state: state.has_all(set_1_beaten, player)

        # Set 2 opens on Duo's clear (vanilla order) or at once (open), and
        # ALSO needs Mega Ball + Thunder Claw. Until 2026-09-25 those came
        # through Duo's entrance; they stay here explicitly, because in
        # vanilla set 2 is only ever played holding the Mega Ball and all four
        # set-1 weapons, so a set-2 route may assume any of them. Stricter
        # only narrows placement. The other three set-1 weapons turned out to
        # matter in exactly one place, Sword Man's trials (SWORD_TRIALS).
        for boss in names.SET_2:
            if order == order.option_vanilla:
                entrance(f"Stage Select -> {boss}").access_rule = \
                    lambda state: (state.has(names.DUO_CLEARED, player)
                                   and state.has_all((names.MEGA_BALL, names.THUNDER_CLAW), player))
            else:
                entrance(f"Stage Select -> {boss}").access_rule = \
                    lambda state: state.has_all((names.MEGA_BALL, names.THUNDER_CLAW), player)

        # stage_unlocks: each Robot Master stage also needs its codes - on top
        # of the game's own structure, never instead of it.
        if self.options.stage_unlocks:
            for boss in names.ROBOT_MASTERS:
                add_rule(entrance(f"Stage Select -> {boss}"),
                         lambda state, codes=names.access_item(boss): state.has(codes, player))

        # The Wily stages open on all eight bosses. Also asking for all eight
        # WEAPONS is deliberately stricter than the game - nobody has checked
        # what the Wily stages demand, and strict only narrows placement.
        entrance(f"Stage Select -> {names.WILY_1}").access_rule = \
            lambda state: (state.has_all(all_beaten, player)
                           and state.has_all(names.WEAPONS, player))

        # --- Bolts and pickups ----------------------------------------------
        def meets(requirement):
            return lambda state: all(state.has_any(clause, player) for clause in requirement)

        for sub_id, name in bolts.BOLT_LOCATIONS.items():
            requirement = bolts.requirement(sub_id)
            if requirement:
                location(name).access_rule = meets(requirement)
        # Pickups carry what an unpinned bolt of their stage carries - the
        # reasoning, the evidence and the free stages are in pickups.py.
        if self.options.pickupsanity:
            for stage_index, _record, _kind, name in pickups.PICKUPS:
                requirement = bolts.stage_requirement(pickups.STAGE_OF[stage_index])
                if requirement:
                    location(name).access_rule = meets(requirement)

        # Sword Man's four trials (names.SWORD_TRIALS) stand between his
        # stage's hub and everything after it: the pillars past the hub rise
        # only once all four are done (names.py). Past them: the capsule in
        # that corridor (P20), the Rush mini-boss, and the second half - Sword
        # Man himself (and the Beaten event the Wily gate counts), the stage's
        # last bolt (subId 21: after the lava raft, behind a Flash Bomb
        # ceiling) and the capsule in that lava room. Inside the trials, and
        # keeping the stage's own rules: bolt 19 (the Flash Bomb trial's first
        # room), bolt 20 and capsule P21 (the Thunder Claw trial - the stage's
        # only hook tiles, which set 2's entrance already covers). 0.2.0 as
        # first built put the mini-boss and P20 in "the opening" (review B1).
        for name in self.sword_past_trials():
            add_rule(location(name), lambda state: state.has_all(names.SWORD_TRIALS, player))
        # Search Man's doors (names.SEARCH_DOORS): the last stands before his
        # shutter, and only Tornado Hold opens it. His bolts and capsules
        # already ask for it (the stage's requirement, above).
        for name in self.search_past_doors():
            add_rule(location(name), lambda state: state.has(names.SEARCH_DOORS, player))

        # --- The Lab ---------------------------------------------------------
        def bolts_held(state) -> int:
            return state.count(names.BOLTS, player) * size

        # See START_STOCK_COST: every entry at the whole Lab's 40.
        for part in names.START_STOCK:
            location(names.shop_location(part)).access_rule = \
                lambda state: bolts_held(state) >= FULL_STOCK_COST
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

    def sword_past_trials(self) -> list[str]:
        """This seed's locations past Sword Man's trials (set_rules)."""
        past = [names.midboss_location(names.SWORD), names.boss_location(names.SWORD),
                names.beaten(names.SWORD), bolts.BOLT_LOCATIONS[21]]
        if self.options.pickupsanity:
            past += [names.SWORD_HUB_CAPSULE, names.SWORD_LAVA_CAPSULE]
        return past

    @staticmethod
    def search_past_doors() -> list[str]:
        """The locations behind Search Man's Tornado Hold doors that the
        stage's own requirement does not already cover (set_rules)."""
        return [names.boss_location(names.SEARCH), names.beaten(names.SEARCH)]

    def seed_stamp(self) -> int:
        """Names this seed and slot on the disc and in the save (disc.seed_stamp)."""
        return seed_stamp(self.multiworld.seed_name, self.player)

    def generate_output(self, output_directory: str) -> None:
        write_patch(self, output_directory)

    def write_spoiler(self, spoiler_handle) -> None:
        if self.weapon_damage_factors:
            spoiler_handle.write(f"\n\nMega Man 8 weapon damage ({self.player_name}):\n")
            for family, factor in self.weapon_damage_factors.items():
                spoiler_handle.write(f"    {family}: x{factor:.2f}\n")
        if self.boss_hp_factors:
            spoiler_handle.write(f"\n\nMega Man 8 boss HP ({self.player_name}):\n")
            for boss, factor in self.boss_hp_factors.items():
                line = f"    {boss}: {damage.scaled_hp(damage.BOSS_VANILLA_HP, factor)}"
                if boss in damage.MIDBOSS_HP:
                    _where, vanilla = damage.MIDBOSS_HP[boss]
                    line += f" (Rush mini-boss {damage.scaled_hp(vanilla, factor)})"
                spoiler_handle.write(line + "\n")
        if self.boss_damage_factors:
            spoiler_handle.write(f"\n\nMega Man 8 boss damage ({self.player_name}):\n")
            for boss, factor in self.boss_damage_factors.items():
                spoiler_handle.write(f"    {boss}: x{factor:.2f}\n")
        if self.stage_music:
            spoiler_handle.write(f"\n\nMega Man 8 stage music ({self.player_name}):\n")
            for place, theme in self.stage_music.items():
                spoiler_handle.write(f"    {place}: {theme}'s theme\n")

    def get_filler_item_name(self) -> str:
        filler, weights = zip(*names.FILLER_WEIGHTS)
        return self.random.choices(filler, weights=weights, k=1)[0]

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "goal": self.options.goal.value,
            "bolt_bundle_size": self.options.bolt_bundle_size.value,
            "death_link": self.options.death_link.value,
            "stage_unlocks": self.options.stage_unlocks.value,
            "pickupsanity": self.options.pickupsanity.value,
            "rematch_checks": self.options.rematch_checks.value,
            # The Exit part does nothing with it on; the client says so when
            # the part arrives (client._describe_parts).
            "exit_stage_anytime": self.options.exit_stage_anytime.value,
            # An open order: the client keeps Duo's select slot shut until
            # phase 4 (client.select_table).
            "stage_order": self.options.stage_order.value,
            # What the disc's fills and pickups now stop at (disc.max_life_edits);
            # the client's Life Energy fills to it.
            "max_life": self.options.max_life.value,
            # The client checks the disc's AP block carries this before it
            # writes anything (disc.AP_STAMP).
            "seed_stamp": self.seed_stamp(),
        }
