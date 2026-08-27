"""Archipelago world for Mega Man X6 (PS1, NTSC-U, SLUS-01395).

Generation, reachability rules, the BizHawkClient and the disc patch are all
wired. Research notes live in the private `mmx6-ap-research` repo; the ship
plan is `ai-docs/plans/2026-08-22_mmx6-ship-plan.md` there.

Everything here follows the Mega Man X5 world structure on purpose. That world
is proven, and the two games share a platform, a client architecture and most
of their problems.
"""
import logging
import os
from typing import Any, ClassVar

import settings
from BaseClasses import Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from . import names, reploids
from .client import MMX6Client  # noqa: F401  (import registers the client)
from .items import MMX6Item, event_table, item_groups, item_table
from .locations import MMX6Location, location_groups, location_table
from .options import RANDOMIZED_OPTIONS, MMX6Options
from .Rom import ACCEPTED_HASHES, MMX6ProcedurePatch, patch_rom


class MMX6Settings(settings.Group):
    class RomFile(settings.UserFilePath):
        """File path of the Mega Man X6 (USA) disc image (raw 2352-byte .bin)."""
        description = "Mega Man X6 (USA) disc image"
        copy_to = "Megaman X6.bin"
        md5s = sorted(ACCEPTED_HASHES)

    rom_file: RomFile = RomFile(RomFile.copy_to)


class MMX6Web(WebWorld):
    theme = "ice"
    bug_report_page = "https://github.com/Shinnuu/Archipelago/issues"
    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Mega Man X6 with Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Shinnuu"],
    )
    tutorials = [setup_en]


class MMX6World(World):
    """
    Mega Man X6 is the sixth entry in Capcom's Mega Man X series, released for the
    PlayStation in 2001. Three weeks after the Eurasia colony fell, X and Zero hunt
    the Nightmare phenomenon across eight investigation sites, rescuing the Reploids
    trapped in them before the Nightmare gets there first.
    """
    game = "Mega Man X6"
    web = MMX6Web()

    options_dataclass = MMX6Options
    options: MMX6Options

    settings: ClassVar[MMX6Settings]
    settings_key = "mmx6_options"

    item_name_to_id = {name: data.code for name, data in item_table.items() if data.code is not None}
    location_name_to_id = location_table
    item_name_groups = item_groups
    location_name_groups = location_groups

    # The OLDEST client this world is known to work with - NOT the version it
    # was developed against. The server enforces this against every client, so
    # an over-high value locks everyone out. It must come from the newest
    # PUBLISHED Archipelago release, never from the checkout Utils.__version__,
    # which is an unreleased development version: X5 v0.1.0 shipped 0.6.8 that
    # way and no released client could connect.
    required_client_version = (0, 6, 7)

    # Item/location arithmetic, checked in generate_early. Every item needs a
    # location; overshooting passes SILENTLY in Archipelago and simply drops
    # items, and the check has to live in generate_early because Generate.py
    # RETRIES a world that raises later - an error from create_items spins
    # instead of surfacing. Both facts learned the hard way on X5.
    #
    # 28 = 8 weapons + 8 armor parts + 8 Heart Tanks + 2 Sub + W + EX
    # 29 = intro + 8 bosses + 8 hearts + 8 capsules + 4 tanks
    BASE_ITEMS = 28
    BASE_LOCATIONS = 29

    # Which investigation site is open at the start under stage_unlocks.
    # Chosen in generate_early; None when the option is off.
    starting_stage: str | None = None

    def _capacity(self) -> tuple[int, int]:
        items = self.BASE_ITEMS
        locations = self.BASE_LOCATIONS
        if self.options.reploid_checks:
            locations += len(reploids.REPLOIDS)          # 128
            # The 16 gauge upgrades a rescued Reploid carries only exist when
            # the Reploids themselves are checks.
            items += 2 * len(names.STAGES)               # 8 Life Up + 8 Energy Up
        if self.options.endgame_checks:
            # Locations only, never items - so this can only ever make room.
            locations += len(names.ENDGAME_CHECKS)       # 3
        if self.options.parts_in_pool:
            items += len(names.PARTS)                    # 24
        if self.options.zero_unlock:
            items += 1
        if self.options.secret_armors_in_pool:
            items += 2
        if self.options.stage_unlocks:
            # Eight Access Codes, but the starting stage's are PRECOLLECTED
            # rather than placed, so only seven need a location.
            items += len(names.STAGES) - 1
        return items, locations

    def _roll_options(self) -> None:
        """Pick the gameplay options for the player, then make room if the
        roll asked for more items than the seed can hold."""
        for name in RANDOMIZED_OPTIONS:
            option = getattr(self.options, name)
            # Choice exposes its valid values; Toggle is just 0/1.
            values = sorted(set(type(option).options.values())) \
                if getattr(type(option), "options", None) else [0, 1]
            option.value = self.random.choice(values)

        # Make room rather than refusing. reploid_checks adds 128 locations
        # against at most 16 items, so it covers every combination.
        items, locations = self._capacity()
        if items > locations and not self.options.reploid_checks:
            self.options.reploid_checks.value = 1

        logging.info(
            "Mega Man X6 (%s): randomize_options rolled %s",
            self.player_name,
            ", ".join(f"{n}={getattr(self.options, n).value}"
                      for n in RANDOMIZED_OPTIONS))

    def generate_early(self) -> None:
        if self.options.randomize_options:
            self._roll_options()

        # Which site is open at the start under stage_unlocks. Chosen here,
        # after the roll, so a rolled stage_unlocks still gets one.
        if self.options.stage_unlocks:
            self.starting_stage = self.random.choice(names.STAGES)

        items, locations = self._capacity()
        if items > locations:
            raise OptionError(
                f"Mega Man X6 ({self.player_name}): these options need "
                f"{items} items but the seed only has {locations} locations, "
                f"so {items - locations} would be silently dropped. Turn on "
                f"`reploid_checks` (+{len(reploids.REPLOIDS)} locations), or "
                f"turn off `parts_in_pool` (+{len(names.PARTS)} items), "
                f"`stage_unlocks` (+{len(names.STAGES) - 1}), "
                f"`zero_unlock` (+1) or `secret_armors_in_pool` (+2).")

    def create_item(self, name: str) -> MMX6Item:
        if name in item_table:
            data = item_table[name]
            return MMX6Item(name, data.classification, data.code, self.player)
        data = event_table[name]
        return MMX6Item(name, data.classification, None, self.player)

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        stage_select = Region("Stage Select", self.player, self.multiworld)
        # The X6 endgame is the Gate / Secret Laboratory run that opens on a
        # Nightmare Soul count of 3000. One region: the Secret Lab stages are
        # a fixed sequence with no branching reachability, so splitting them
        # into regions would add rules without adding meaning.
        gate = Region("The Gate", self.player, self.multiworld)
        intro = Region("Intro Stage", self.player, self.multiworld)
        self.multiworld.regions += [menu, stage_select, gate, intro]

        # The intro stage is mandatory before the stage select in-game.
        # Its clear is durably marked by 0x800CCF36 stepping 0 -> 1.
        intro.add_locations({names.INTRO_CLEAR: location_table[names.INTRO_CLEAR]},
                            MMX6Location)
        menu.connect(intro)
        intro.connect(stage_select)

        for stage in names.STAGES:
            region = Region(stage, self.player, self.multiworld)
            self.multiworld.regions.append(region)
            stage_locations = {
                names.boss_location(stage): location_table[names.boss_location(stage)],
                names.heart_location(stage): location_table[names.heart_location(stage)],
                names.capsule_location(stage): location_table[names.capsule_location(stage)],
            }
            if stage in names.STAGE_TANK:
                stage_locations[names.tank_location(stage)] = \
                    location_table[names.tank_location(stage)]
            region.add_locations(stage_locations, MMX6Location)
            # All eight stages are open from the start in X6, same as X5.
            stage_select.connect(region)

        if self.options.reploid_checks:
            # Each Reploid joins its own stage region, so it inherits that
            # stage reachability. No item rules: walking into a Reploid is
            # execution, not inventory.
            for stage in names.STAGES:
                self.multiworld.get_region(stage, self.player).add_locations(
                    {name: location_table[name]
                     for s, _index, _n, name in reploids.REPLOIDS if s == stage},
                    MMX6Location)

        if self.options.endgame_checks:
            # In The Gate, so they inherit its access rule - under
            # stage_unlocks that is "every Access Codes item", which these
            # clears genuinely need.
            gate.add_locations(
                {name: location_table[name]
                 for name, _threshold in names.ENDGAME_CHECKS},
                MMX6Location)

        victory = MMX6Location(self.player, names.VICTORY, None, gate)
        victory.place_locked_item(self.create_item(names.VICTORY))
        gate.locations.append(victory)
        stage_select.connect(gate)

    def create_items(self) -> None:
        pool = []
        for name, data in item_table.items():
            pool += [self.create_item(name) for _ in range(data.count)]

        if self.options.reploid_checks:
            # One Life Up and one Energy Up per stage - the 16 upgrades that
            # take the life gauge 32 -> 64 alongside the Heart Tanks, and the
            # weapon gauge 48 -> 64. Their table count is 0 because without
            # the Reploid locations there is nowhere to put them.
            pool += [self.create_item(names.LIFE_UP) for _ in names.STAGES]
            pool += [self.create_item(names.ENERGY_UP) for _ in names.STAGES]

        if self.options.parts_in_pool:
            pool += [self.create_item(p) for p in names.PARTS]

        if self.options.zero_unlock:
            pool.append(self.create_item(names.ZERO))

        if self.options.secret_armors_in_pool:
            pool.append(self.create_item(names.ULTIMATE_ARMOR))
            pool.append(self.create_item(names.BLACK_ZERO))

        if self.options.stage_unlocks:
            # The starting stage's codes are PRECOLLECTED, not placed: that
            # stage has to be open before any location at all is reachable, so
            # its codes cannot themselves be a check. The other seven shuffle.
            for stage in names.STAGES:
                item = self.create_item(names.access_item(stage))
                if stage == self.starting_stage:
                    self.multiworld.push_precollected(item)
                else:
                    pool.append(item)

        # Top up with filler. The over-full direction is caught in
        # generate_early - by here it is too late to report cleanly, because
        # Generate.py RETRIES a failed world rather than surfacing the error.
        unfilled = len(self.multiworld.get_unfilled_locations(self.player))
        assert len(pool) <= unfilled, "pool overflow should have been caught in generate_early"
        while len(pool) < unfilled:
            pool.append(self.create_item(self.get_filler_item_name()))
        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        player = self.player

        def has_blade(state) -> bool:
            """Blade Armor works only as a complete set of four parts."""
            return state.has_all(names.BLADE_PARTS, player)

        def has_shadow(state) -> bool:
            return state.has_all(names.SHADOW_PARTS, player)

        def has_mobility(state) -> bool:
            """Blade Armor Mach Dash, or Zero.

            The items guide phrases six locations as "Zero, or Blade Armor
            plus Speedster/Hyper Dash". The Part half is deliberately dropped
            from the rule: Parts are never progression here (seven of the 24
            only work for one character), so requiring one could strand a
            single-character run. Blade alone is the looser of the two
            readings and Zero covers the rest.
            """
            return state.has(names.ZERO, player) or has_blade(state)

        def needs(location: str, rule) -> None:
            self.multiworld.get_location(location, player).access_rule = rule

        # Zero is either an item or something the player has from the start.
        # With the option off, precollect him so `has_mobility` is simply true
        # rather than every rule needing a second branch.
        if not self.options.zero_unlock:
            self.multiworld.push_precollected(self.create_item(names.ZERO))

        # --- The endgame ----------------------------------------------------
        # Deliberately STRICTER than the game. X6 opens its endgame on 3000
        # Nightmare Souls, which drop from ordinary enemies in every stage and
        # so cost time rather than items - as a logic rule that is free, and
        # it would let fill hide progression behind a grind with no real gate.
        # Requiring all eight weapons gives the endgame a spine, and it is not
        # arbitrary: High Max only takes damage from a fully charged special
        # weapon.
        #
        # Shadow Armor is NOT a counterexample to that, though it looks like
        # one: the game really does zero the weapon capability while Shadow is
        # equipped, verified in the disassembly as
        #   lbu a0, 0x5e(save)  /  bne a0, 2  /  sb zero, 0xc9(player)
        # so a player in Shadow has no special weapons and cannot damage High
        # Max. It costs nothing here because armor is a CHOICE made at the
        # stage select and applied at stage start, not a permanent state, and
        # bare X is always available. Holding the weapons is what the rule
        # asks for, and a player holding them can always wear something else.
        # Do not weaken this rule on Shadow's account.
        #
        # Stricter is safe - it only narrows placement, it can never strand
        # progression - as long as every boss stays reachable without items.
        # That no longer holds unconditionally: `stage_unlocks` locks stages
        # behind items, so the endgame ALSO requires every Access Codes item.
        #
        # This is the rule X5 got wrong. It shipped stage_unlocks without
        # revisiting the endgame rule, and a tester seed put two stages
        # Access Codes INSIDE the endgame those codes were needed to reach -
        # a hard deadlock that still "won" the playthrough check, because
        # logic only ever looked at the weapon items. Applied for every goal,
        # not just all_mavericks: X6 opens its endgame on a soul count logic
        # does not model, and being stricter than the game only narrows
        # placement while being looser strands seeds.
        endgame_needs = set(names.WEAPONS)
        if self.options.stage_unlocks:
            endgame_needs |= set(names.ACCESS_ITEMS)
        self.multiworld.get_entrance("Stage Select -> The Gate", player).access_rule = \
            lambda state: state.has_all(endgame_needs, player)

        # --- Stage access ----------------------------------------------------
        # Enforced in-game by the client zeroing the stage-select overlay slot
        # -> stage-id table at 0x800F0BAC, which makes confirming a locked icon
        # a no-op; this is only the logic half. Every location in a stage lives
        # in that stage region, so one entrance rule covers the boss, the Heart
        # Tank, the capsule, the tank and all 16 Reploids at once.
        if self.options.stage_unlocks:
            for stage in names.STAGES:
                codes = names.access_item(stage)
                self.multiworld.get_entrance(f"Stage Select -> {stage}",
                                             player).access_rule = \
                    lambda state, codes=codes: state.has(codes, player)

        # --- Armor capsules -------------------------------------------------
        # Every requirement below comes from the third-party items guide [G]
        # and is UNVERIFIED against our own play. Where the guide is vague the
        # stricter reading is taken, because strict only narrows placement
        # while loose strands seeds.
        #
        # Acyclic by construction, and worth saying out loud because it is the
        # thing that would break first: nothing needed for a BLADE part
        # requires Blade or Shadow, so the order is
        #   (no items) -> Blade parts -> Blade Armor -> Shadow parts -> Shadow.
        for stage in (names.WOLFANG, names.SHARK, names.TURTLOID):
            needs(names.capsule_location(stage), has_mobility)
        # The Heatnix Shadow X-Buster sits at the top of the shaft ABOVE that
        # stage Heart Tank, which itself needs mobility - so it needs at least
        # as much. Inferred, not stated by the guide; strict on purpose.
        needs(names.capsule_location(names.HEATNIX), has_mobility)
        # Yammark (Blade Legs), Sheldon (Blade Body) and Mijinion (Blade Arms)
        # need nothing.
        #
        # The Scaravich Blade Helmet sits inside one of that stage randomly
        # chosen totem-pole sub-areas, so reaching it means re-entering until
        # the right area comes up. That is persistence, not inventory, and
        # Archipelago logic cannot model "reroll until" - so no rule. Ship
        # plan A3 intends to pin the room sequence in the patch, which removes
        # the randomness rather than modelling it.

        # --- Heart Tanks ----------------------------------------------------
        for stage in (names.TURTLOID, names.SHELDON):
            needs(names.heart_location(stage), has_shadow)
        for stage in (names.HEATNIX, names.WOLFANG):
            needs(names.heart_location(stage), has_mobility)
        # Yammark, Shark and Mijinion hearts need nothing; the Scaravich one
        # is behind the same randomisation as its Blade Helmet, so no rule.
        #
        # --- Tanks ----------------------------------------------------------
        needs(names.tank_location(names.SHELDON), has_shadow)    # W Tank
        needs(names.tank_location(names.WOLFANG), has_shadow)    # EX Tank
        needs(names.tank_location(names.YAMMARK), has_mobility)  # Sub Tank
        needs(names.tank_location(names.HEATNIX), has_mobility)  # Sub Tank

        # --- The Wolfang wall -----------------------------------------------
        # Wolfang's Heart Tank and EX Tank sit behind a wall that only opens
        # while a Nightmare Effect is active on his stage, and per NightEftTable
        # only Fire (Heatnix) or Mirror (Sheldon) can afflict North Pole. So
        # they need one of those two BEATEN, not merely reachable.
        #
        # This used to carry no rule, on the reasoning that "both bosses are
        # reachable from the start, so it adds nothing to logic". True in
        # vanilla - and FALSE the moment `stage_unlocks` is on, because then
        # both bosses are behind their own Access Codes. Staging a real seed
        # found exactly that: Wolfang's Heart Tank held Sheldon's codes, the
        # only other opener was Heatnix whose codes were two spheres later,
        # and fill had happily called it reachable. Nobody could have finished
        # that seed.
        def wolfang_wall(state) -> bool:
            if not self.options.stage_unlocks:
                return True     # both openers are free, as before
            return (state.has(names.access_item(names.HEATNIX), player)
                    or state.has(names.access_item(names.SHELDON), player))

        def also_needs(location: str, extra) -> None:
            """AND a rule onto whatever this location already requires."""
            loc = self.multiworld.get_location(location, player)
            existing = loc.access_rule
            loc.access_rule = lambda state: existing(state) and extra(state)

        also_needs(names.heart_location(names.WOLFANG), wolfang_wall)
        also_needs(names.tank_location(names.WOLFANG), wolfang_wall)

        # Both goals complete on the VICTORY event in The Gate, which already
        # carries the all-weapons entrance rule. all_mavericks needs no extra
        # rule: every Maverick is reachable from the start and killable with
        # no items, so "defeat all 8" is satisfiable wherever VICTORY is. The
        # difference between the goals is in-game timing, which logic does not
        # model - the client holds the goal until the kill count is 8.
        self.multiworld.completion_condition[player] = \
            lambda state: state.has(names.VICTORY, player)

    def generate_output(self, output_directory: str) -> None:
        patch = MMX6ProcedurePatch(
            player=self.player,
            player_name=self.multiworld.player_name[self.player])
        patch_rom(self, patch)
        patch.write(os.path.join(
            output_directory,
            f"{self.multiworld.get_out_file_name_base(self.player)}"
            f"{patch.patch_file_ending}"))

    def get_filler_item_name(self) -> str:
        filler, weights = zip(*names.FILLER_WEIGHTS)
        return self.random.choices(filler, weights=weights, k=1)[0]

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "goal": self.options.goal.value,
            "difficulty": self.options.difficulty.value,
            "reploid_checks": self.options.reploid_checks.value,
            "parts_in_pool": self.options.parts_in_pool.value,
            "zero_unlock": self.options.zero_unlock.value,
            "secret_armors_in_pool": self.options.secret_armors_in_pool.value,
            "stage_unlocks": self.options.stage_unlocks.value,
        }
