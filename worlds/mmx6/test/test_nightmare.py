"""`disabled_nightmare_effects` tests.

Eight effects, each one three bytes in the creation table at ROCK +0x0C5EB4.
Zeroing a record stops that effect ever being assigned to a stage.

The dangerous one is **Fire**, and everything below is really about it.
Nightmare Fire is what melts North Pole's ice wall, and NINE locations are
behind that wall - Blizzard Wolfang's Heart Tank, his EX Tank and seven of his
sixteen Reploids. Turning Fire off without opening the wall would strand all
nine, which is the same shape as the bug that made v0.1.1 a seed-breaking
release. So the wall edits live INSIDE the Fire group rather than beside it,
and logic drops the Fire requirement to match.

The other seven are safe, and the sweep that established that is worth
recording: Scaravich's exhibits are room randomisation rather than a Nightmare
effect, every other Another Route is gated by inventory (Shadow, mobility, or
beating Illumina), and the two effects that double as platforms - Ice and Cube
- only matter at Recycle Lab's capsule, where logic already demands Blade
Armor or Zero, which is the stronger requirement.

The data tests run anywhere. The disc-backed ones skip cleanly when the image
is absent, because a check that could not RUN must never report as passed.
"""
import os
import unittest

from .. import disc, names
from ..Rom import nightmare_groups, qol_features
from ..options import DisabledNightmareEffects, MMX6Options
from . import MMX6TestBase

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)

FIRE_GROUP = disc.nightmare_group_name("Fire")


class Namespace:
    """Just enough of an options object for qol_features."""

    def __init__(self, effects=()) -> None:
        self.disabled_nightmare_effects = DisabledNightmareEffects(set(effects))
        for option in ("text_skip", "skip_intro_videos", "exit_stage_anytime",
                       "protect_reploids"):
            setattr(self, option, type("O", (), {"value": 0})())


class TestTheTableDecode(unittest.TestCase):
    """The decode the whole feature rests on, and its two controls."""

    def test_eight_records_of_three_bytes(self) -> None:
        self.assertEqual(len(disc.NIGHTMARE_EFFECTS), 8)
        for effect, (_where, van) in disc.NIGHTMARE_EFFECTS.items():
            self.assertEqual(len(bytes.fromhex(van)), 3, effect)

    def test_the_records_are_contiguous_and_in_id_order(self) -> None:
        # Ids are the ones the save uses at 0x800CD039: 01 Bug .. 08 Dark.
        wheres = [w for w, _v in disc.NIGHTMARE_EFFECTS.values()]
        self.assertEqual(wheres,
                         [disc.NIGHTMARE_TABLE + 3 * i for i in range(8)])

    def _afflicts(self) -> dict:
        out: dict[int, list] = {}
        for effect, (_w, van) in disc.NIGHTMARE_EFFECTS.items():
            for stage in set(bytes.fromhex(van)):
                out.setdefault(stage, []).append(effect)
        return out

    def test_every_stage_is_afflicted_by_exactly_two(self) -> None:
        # Control 1. The research notes say this independently of the table,
        # so a table that stopped matching would mean the records moved.
        afflicts = self._afflicts()
        self.assertEqual(sorted(afflicts), list(range(1, 9)))
        for stage, effects in afflicts.items():
            self.assertEqual(len(effects), 2, f"stage {stage}: {effects}")

    def test_north_pole_is_fire_and_mirror_only(self) -> None:
        # Control 2, and the one that matters: the notes reached "Fire or
        # Mirror, and only Fire opens the wall" from a disassembly, with no
        # reference to this table at all.
        wolfang = names.STAGE_INDEX[names.WOLFANG]
        self.assertEqual(sorted(self._afflicts()[wolfang]),
                         ["Fire", "Mirror"])

    def test_the_option_offers_exactly_these_eight(self) -> None:
        self.assertEqual(sorted(DisabledNightmareEffects.EFFECTS),
                         sorted(disc.NIGHTMARE_EFFECTS))


class TestKeys(unittest.TestCase):
    """How a player is allowed to name them."""

    def _effects(self, *keys) -> set:
        return DisabledNightmareEffects(set(keys)).effects

    def test_nothing_named_is_nothing_disabled(self) -> None:
        self.assertEqual(self._effects(), set())

    def test_effects_can_be_named_individually(self) -> None:
        self.assertEqual(self._effects("Fire"), {"Fire"})
        self.assertEqual(self._effects("Fire", "Dark"), {"Fire", "Dark"})

    def test_all_means_every_one_of_the_eight(self) -> None:
        self.assertEqual(self._effects("all"),
                         set(DisabledNightmareEffects.EFFECTS))
        self.assertEqual(self._effects("all"), self._effects(
            *DisabledNightmareEffects.EFFECTS))

    def test_case_does_not_matter(self) -> None:
        # This option is typed by hand into a YAML, so `fire` has to work.
        self.assertEqual(self._effects("fire"), {"Fire"})
        self.assertEqual(self._effects("FIRE"), {"Fire"})
        self.assertEqual(self._effects("All"),
                         set(DisabledNightmareEffects.EFFECTS))

    def test_every_accepted_key_is_a_real_effect_or_all(self) -> None:
        allowed = set(DisabledNightmareEffects.valid_keys)
        self.assertEqual(
            allowed,
            {DisabledNightmareEffects.ALL}
            | {e.casefold() for e in DisabledNightmareEffects.EFFECTS})

    def test_a_typo_is_refused_rather_than_ignored(self) -> None:
        from Options import OptionError
        opt = DisabledNightmareEffects({"Flame"})
        with self.assertRaises(OptionError):
            opt.verify(None, "Player", None)


class TestGroups(unittest.TestCase):
    def test_vanilla_asks_for_no_nightmare_edits(self) -> None:
        self.assertEqual(nightmare_groups(Namespace()), [])
        self.assertEqual(qol_features(Namespace()), [])

    def test_every_effect_has_a_group_of_its_own(self) -> None:
        for effect in disc.NIGHTMARE_EFFECTS:
            group = disc.nightmare_group_name(effect)
            self.assertIn(group, disc.QOL_EDITS, effect)
            self.assertEqual(nightmare_groups(Namespace([effect])), [group])

    def test_all_eight_selects_all_eight(self) -> None:
        every = list(disc.NIGHTMARE_EFFECTS)
        self.assertEqual(len(nightmare_groups(Namespace(every))), 8)

    def test_the_order_does_not_depend_on_the_yaml(self) -> None:
        # A set has no order, so without sorting into the table's own order
        # two identical seeds could emit different edit lists.
        a = nightmare_groups(Namespace(["Dark", "Bug", "Fire"]))
        b = nightmare_groups(Namespace(["Fire", "Dark", "Bug"]))
        self.assertEqual(a, b)
        self.assertEqual(a, [disc.nightmare_group_name(e)
                             for e in ("Bug", "Fire", "Dark")])

    def test_a_non_fire_group_is_one_edit(self) -> None:
        for effect in disc.NIGHTMARE_EFFECTS:
            if effect == "Fire":
                continue
            self.assertEqual(len(disc.QOL_EDITS[disc.nightmare_group_name(effect)]),
                             1, effect)


class TestTheFireBundle(unittest.TestCase):
    """The seed-stranding case, pinned from several directions."""

    def test_fire_carries_the_wall_edits(self) -> None:
        edits = disc.QOL_EDITS[FIRE_GROUP]
        self.assertEqual(len(edits), 5, "record + four wall sites")

    def test_it_covers_all_four_copies_of_the_check(self) -> None:
        # The Tweaks patcher only covers two of the four. The other two were
        # found by searching ROCK for the instruction itself; if this ever
        # drops back to two, disabling Fire shuts the wall in some overlays
        # and takes nine locations with it.
        record = disc.NIGHTMARE_EFFECTS["Fire"][0]
        sites = {w for _l, w, _r, _v, _p in disc.QOL_EDITS[FIRE_GROUP]
                 if w != record}
        self.assertEqual(sites,
                         {s + 8 for s in disc.NIGHTMARE_WALL_SITES})
        self.assertEqual(len(disc.NIGHTMARE_WALL_SITES), 4)

    def test_the_wall_edit_makes_the_branch_unconditional(self) -> None:
        # beq v1, v0, +24  ->  beq zero, zero, +24. Same offset, so only the
        # condition changes; anything else would move the branch target.
        van = int.from_bytes(bytes.fromhex(disc.NIGHTMARE_WALL_VANILLA), "little")
        new = int.from_bytes(bytes.fromhex(disc.NIGHTMARE_WALL_PATCHED), "little")
        self.assertEqual(van >> 26, 0x04, "vanilla is not a beq")
        self.assertEqual(new >> 26, 0x04, "patched is not a beq")
        self.assertEqual(van & 0xFFFF, new & 0xFFFF, "branch offset moved")
        self.assertEqual((new >> 21) & 0x1F, 0, "rs is not zero")
        self.assertEqual((new >> 16) & 0x1F, 0, "rt is not zero")

    def test_no_other_effect_touches_the_wall(self) -> None:
        for effect in disc.NIGHTMARE_EFFECTS:
            if effect == "Fire":
                continue
            sites = {w for _l, w, _r, _v, _p
                     in disc.QOL_EDITS[disc.nightmare_group_name(effect)]}
            self.assertFalse(sites & {s + 8 for s in disc.NIGHTMARE_WALL_SITES},
                             effect)


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestAgainstTheDisc(unittest.TestCase):
    """The bytes really are what we recorded, on the image we ship against."""

    @classmethod
    def setUpClass(cls) -> None:
        with open(ROM, "rb") as fh:
            cls.rom = fh.read()

    def _at(self, where: int, region: str, n: int) -> bytes:
        off = disc.addr_to_disc(where, region)
        return self.rom[off:off + n]

    def test_every_creation_record_matches(self) -> None:
        for effect, (where, van) in disc.NIGHTMARE_EFFECTS.items():
            self.assertEqual(self._at(where, disc.REGION_ROCK, 3),
                             bytes.fromhex(van), effect)

    def test_every_wall_site_holds_the_expected_branch(self) -> None:
        for site in disc.NIGHTMARE_WALL_SITES:
            self.assertEqual(self._at(site + 8, disc.REGION_ROCK, 4),
                             bytes.fromhex(disc.NIGHTMARE_WALL_VANILLA),
                             hex(site))

    def test_the_wall_check_reads_the_effect_and_compares_to_fire(self) -> None:
        # lb v1, 0x43A(s3) / addiu v0, zero, 3 / beq v1, v0. If the routine
        # around a site ever stops looking like this, the offset is stale and
        # the edit would be landing on something else entirely.
        for site in disc.NIGHTMARE_WALL_SITES:
            lb = int.from_bytes(self._at(site, disc.REGION_ROCK, 4), "little")
            li = int.from_bytes(self._at(site + 4, disc.REGION_ROCK, 4), "little")
            self.assertEqual(lb >> 26, 0x20, hex(site))       # lb
            self.assertEqual(lb & 0xFFFF, 0x043A, hex(site))  # the effect byte
            self.assertEqual(li, 0x24020003, hex(site))       # addiu v0,zero,3


# The nine locations Nightmare Fire gates: the Heart Tank, the EX Tank, and
# seven of Wolfang's sixteen Reploids. Taken from the roster's own
# consequences section, which is also where REPLOID_GATES came from.
FIRE_GATED = ([names.heart_location(names.WOLFANG),
               names.tank_location(names.WOLFANG)]
              + [names.reploid_location(names.WOLFANG, n)
                 for n in (4, 5, 6, 13, 14, 15, 16)])


class _WallBase(MMX6TestBase):
    """Reachability of the nine with Heatnix's Access Codes taken away.

    Under `stage_unlocks` the Fire opener IS Heatnix's codes, so removing them
    is what separates "the wall rule is doing something" from "everything was
    reachable anyway".
    """

    def _reachable(self) -> dict:
        state = self.multiworld.get_all_state()
        for item in list(state.prog_items[1]):
            if item == names.access_item(names.HEATNIX):
                del state.prog_items[1][item]
        state.sweep_for_advancements()
        return {loc: self.multiworld.get_location(loc, 1).can_reach(state)
                for loc in FIRE_GATED}


class TestFireRelaxesTheWallRule(_WallBase):
    options = {"stage_unlocks": True, "reploid_checks": True,
               "disabled_nightmare_effects": ["Fire"]}

    def test_all_nine_stop_needing_heatnix(self) -> None:
        # The wall is patched open on this disc, so requiring the opener would
        # only make fill more conservative than the game it generates for.
        # All NINE, not just the Heart Tank: the seven Reploids ride on the
        # same rule through REPLOID_GATES' "wall" key, and a relaxation that
        # reached the tanks but not them would be invisible here otherwise.
        for loc, ok in self._reachable().items():
            self.assertTrue(ok, f"{loc} still needs Heatnix")


class TestAllAlsoRelaxesTheWallRule(_WallBase):
    """`all` has to mean Fire too - a plain `in` test would miss it."""
    options = {"stage_unlocks": True, "reploid_checks": True,
               "disabled_nightmare_effects": ["all"]}

    def test_all_nine_stop_needing_heatnix(self) -> None:
        for loc, ok in self._reachable().items():
            self.assertTrue(ok, f"{loc} still needs Heatnix under `all`")


class TestFireExcludesWhatIsBehindTheWall(_WallBase):
    """The fail-safe, and the reason the wall edits are not load-bearing.

    Disabling Fire relaxes the wall rule, so logic calls those nine reachable.
    If that promise rested on the wall edits alone and they turned out not to
    work, a seed with progression behind the wall could not be finished. So
    the nine are excluded as well: fill puts only junk there, and whether the
    wall physically opens decides nothing but whether nine filler checks can
    be collected.
    """
    options = {"stage_unlocks": True, "reploid_checks": True,
               "disabled_nightmare_effects": ["Fire"]}

    def test_all_nine_hold_filler_only(self) -> None:
        from BaseClasses import LocationProgressType
        for loc in FIRE_GATED:
            self.assertEqual(
                self.multiworld.get_location(loc, 1).progress_type,
                LocationProgressType.EXCLUDED, loc)

    def test_nothing_else_in_that_stage_is_excluded(self) -> None:
        # Only what the wall gates. Wolfang's boss clear and his other nine
        # Reploids are in front of it and stay usable.
        from BaseClasses import LocationProgressType
        for loc in self.multiworld.get_region(names.WOLFANG, 1).locations:
            if loc.name in FIRE_GATED:
                continue
            self.assertNotEqual(loc.progress_type,
                                LocationProgressType.EXCLUDED, loc.name)


class TestAllExcludesThemToo(_WallBase):
    options = {"stage_unlocks": True, "reploid_checks": True,
               "disabled_nightmare_effects": ["all"]}

    def test_all_nine_hold_filler_only(self) -> None:
        from BaseClasses import LocationProgressType
        for loc in FIRE_GATED:
            self.assertEqual(
                self.multiworld.get_location(loc, 1).progress_type,
                LocationProgressType.EXCLUDED, loc)


class TestFireOnLeavesThemUsable(_WallBase):
    """The control: with Fire live the nine are ordinary progression spots."""
    options = {"stage_unlocks": True, "reploid_checks": True,
               "disabled_nightmare_effects": ["Mirror"]}

    def test_none_of_the_nine_is_excluded(self) -> None:
        from BaseClasses import LocationProgressType
        for loc in FIRE_GATED:
            self.assertNotEqual(
                self.multiworld.get_location(loc, 1).progress_type,
                LocationProgressType.EXCLUDED, loc)


class TestFireOnKeepsTheWallRule(_WallBase):
    """The control. Without this, the two above prove nothing."""
    options = {"stage_unlocks": True, "reploid_checks": True,
               "disabled_nightmare_effects": []}

    def test_all_nine_still_need_heatnix(self) -> None:
        for loc, ok in self._reachable().items():
            self.assertFalse(ok, f"{loc} was reachable without Heatnix")


class TestAnotherEffectDoesNotRelaxIt(_WallBase):
    """Turning off something that is not Fire must not open the wall."""
    options = {"stage_unlocks": True, "reploid_checks": True,
               "disabled_nightmare_effects": ["Mirror", "Dark"]}

    def test_the_nine_still_need_heatnix(self) -> None:
        for loc, ok in self._reachable().items():
            self.assertFalse(ok, f"{loc} was opened by a non-Fire effect")


class TestTheOptionIsReal(unittest.TestCase):
    def test_it_is_in_the_options_dataclass(self) -> None:
        self.assertIn("disabled_nightmare_effects", MMX6Options.type_hints)
