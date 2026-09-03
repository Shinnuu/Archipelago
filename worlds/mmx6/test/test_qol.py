"""QoL disc-edit tests.

The QoL options are the first thing this world puts on the disc that is NOT
the same for every seed, so the properties worth pinning are mostly about
edits not treading on each other: A1 and the QoL groups all write the same two
containers, and an overlap would make the result depend on which order the
edits happened to be applied in.

The data-only tests run everywhere. The ones that need the disc image skip
cleanly when it is absent, exactly like test_disc.py - a check that could not
RUN must never be reported as a check that passed.
"""
import mmap
import os
import unittest

from .. import disc
from ..Rom import QOL_OPTIONS, qol_features
from ..options import DisabledNightmareEffects, MMX6Options

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)

REDUMP = (r"C:\Users\Ivor\Documents\Game Modding\Games\redump-rev1"
          r"\Mega Man X6 (USA) (Rev 1)\Mega Man X6 (USA) (Rev 1).bin")
have_redump = os.path.exists(REDUMP)

ALL_GROUPS = sorted(disc.QOL_EDITS)


def _span(where: int, region: str, n: int) -> set[int]:
    return {disc.addr_to_disc(where + i, region) for i in range(n)}


class TestQoLData(unittest.TestCase):
    """Everything checkable without the disc."""

    def test_every_option_maps_to_a_real_edit_group(self) -> None:
        for option, group in QOL_OPTIONS.items():
            self.assertIn(group, disc.QOL_EDITS, f"{option} names no edits")

    def test_every_edit_group_is_reachable_from_an_option(self) -> None:
        # An edit group nothing can turn on is dead weight that still looks
        # supported from the inside.
        #
        # The eight Nightmare groups are reachable from ONE option that picks
        # a subset, so they cannot appear in QOL_OPTIONS' one-to-one map. They
        # are unioned in rather than excused: an orphan is still an orphan.
        nightmare = {disc.nightmare_group_name(e)
                     for e in disc.NIGHTMARE_EFFECTS}
        self.assertEqual(set(QOL_OPTIONS.values()) | nightmare,
                         set(disc.QOL_EDITS))

    def test_every_nightmare_group_is_selectable_by_name(self) -> None:
        # The other half of the same guarantee: a group could be in QOL_EDITS
        # and named by nightmare_group_name while the option refuses the key.
        for effect in disc.NIGHTMARE_EFFECTS:
            self.assertIn(effect, DisabledNightmareEffects.valid_keys)

    def test_every_option_exists_on_the_options_dataclass(self) -> None:
        fields = MMX6Options.type_hints
        for option in QOL_OPTIONS:
            self.assertIn(option, fields, f"{option} is not a YAML option")

    def test_vanilla_and_patched_payloads_are_the_same_length(self) -> None:
        # A shorter patched payload would leave half an instruction behind.
        # This half applies to every edit, data or code.
        for group, edits in disc.QOL_EDITS.items():
            for label, _where, _region, van, pat in edits:
                self.assertEqual(len(van), len(pat), f"{group}/{label}")

    def test_every_code_edit_is_whole_instructions(self) -> None:
        # Scoped rather than relaxed: the Nightmare creation records are three
        # bytes of TABLE, so "whole instructions" was never a claim about
        # them. Everything else in QOL_EDITS is MIPS and still has to be.
        for group, edits in disc.QOL_EDITS.items():
            for label, where, _region, van, _pat in edits:
                if where in disc.DATA_EDIT_SITES:
                    continue
                self.assertEqual(len(van) % 4, 0,
                                 f"{group}/{label} is not whole instructions")

    def test_the_data_edits_are_exactly_the_creation_records(self) -> None:
        # Otherwise the exemption above could quietly grow to cover a code
        # edit somebody got wrong.
        self.assertEqual(
            disc.DATA_EDIT_SITES,
            frozenset(w for w, _v in disc.NIGHTMARE_EFFECTS.values()))
        for where in disc.DATA_EDIT_SITES:
            self.assertEqual(len(disc.NIGHTMARE_EFFECTS["Bug"][1]) // 2, 3)
            self.assertIsInstance(where, int)

    def test_no_qol_edit_overlaps_a1(self) -> None:
        a1 = set()
        for _l, where, region, van, _p in disc.A1_EDITS:
            a1 |= _span(where, region, len(van))
        for group, edits in disc.QOL_EDITS.items():
            for label, where, region, van, _p in edits:
                self.assertFalse(_span(where, region, len(van)) & a1,
                                 f"{group}/{label} overlaps the A1 patch")

    def test_no_two_qol_edits_overlap(self) -> None:
        seen: dict[int, str] = {}
        for group, edits in disc.QOL_EDITS.items():
            for label, where, region, van, _p in edits:
                for off in _span(where, region, len(van)):
                    self.assertNotIn(off, seen,
                                     f"{group}/{label} overlaps {seen.get(off)}")
                    seen[off] = f"{group}/{label}"

    def test_selecting_groups_filters_and_keeps_a_stable_order(self) -> None:
        self.assertEqual(disc.qol_edits([]), [])
        every = disc.qol_edits(ALL_GROUPS)
        self.assertEqual(len(every),
                         sum(len(v) for v in disc.QOL_EDITS.values()))
        # Order comes from QOL_EDITS, never from the caller, so the same
        # options always produce the same patch file.
        self.assertEqual(disc.qol_edits(reversed(ALL_GROUPS)), every)
        one = disc.qol_edits(["exit_stage_anytime"])
        self.assertEqual(one, disc.QOL_EDITS["exit_stage_anytime"])

    def test_qol_features_reads_the_options(self) -> None:
        class _Opt:
            def __init__(self, value):
                self.value = value

        class _Options:
            def __init__(self, nightmare=(), **kw):
                for option in QOL_OPTIONS:
                    setattr(self, option, _Opt(kw.get(option, 0)))
                self.disabled_nightmare_effects = DisabledNightmareEffects(
                    set(nightmare))

        self.assertEqual(qol_features(_Options()), [])
        self.assertEqual(qol_features(_Options(text_skip=1)), ["text_skip"])
        # Every boolean on but no effects named: the Nightmare groups must
        # stay out, or a player who never asked would get a patched disc.
        self.assertEqual(
            sorted(qol_features(_Options(**{o: 1 for o in QOL_OPTIONS}))),
            sorted(set(QOL_OPTIONS.values())))
        # Everything on, including all eight effects.
        self.assertEqual(
            sorted(qol_features(_Options(
                nightmare=DisabledNightmareEffects.valid_keys,
                **{o: 1 for o in QOL_OPTIONS}))),
            sorted(ALL_GROUPS))


class _DiscCase(unittest.TestCase):
    PATH = ROM

    @classmethod
    def setUpClass(cls) -> None:
        cls._fh = open(cls.PATH, "rb")
        cls.rom = mmap.mmap(cls._fh.fileno(), 0, access=mmap.ACCESS_READ)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.rom.close()
        cls._fh.close()

    def build(self, groups):
        """apply_basepatch with the named QoL groups, or skip if the machine
        cannot spare the memory - the same rule test_disc.py uses."""
        extra = [(where, pat, region, van)
                 for _l, where, region, van, pat in disc.qol_edits(groups)]
        try:
            return disc.apply_basepatch(self.rom, extra)
        except MemoryError:
            self.skipTest("not enough memory to hold two copies of a 600MB "
                          "image; close other large applications")


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestQoLAgainstTheRealDisc(_DiscCase):
    def test_every_declared_vanilla_is_what_the_disc_holds(self) -> None:
        # The offsets came from a third-party patcher whose data is expressed
        # against ITS target image. This is the control: read our own bytes.
        for group, edits in disc.QOL_EDITS.items():
            for label, where, region, van, _p in edits:
                base = disc.addr_to_disc(where, region)
                self.assertEqual(bytes(self.rom[base:base + len(van)]), van,
                                 f"{group}/{label}")

    def test_no_qol_edit_targets_blank_space(self) -> None:
        # Some Tweaks edits write injected subroutines into alignment holes.
        # None of the ones shipped here do, and that should stay true: every
        # site must currently hold real code, not padding we are guessing is
        # free.
        for group, edits in disc.QOL_EDITS.items():
            for label, _w, _r, van, _p in edits:
                self.assertNotEqual(van, bytes(len(van)),
                                    f"{group}/{label} targets blank space")

    def test_all_qol_on_lands_every_edit_and_leaves_a1_intact(self) -> None:
        out = self.build(ALL_GROUPS)
        for _l, where, region, _van, pat in disc.A1_EDITS:
            base = disc.addr_to_disc(where, region)
            self.assertEqual(out[base:base + len(pat)], pat)
        for group, edits in disc.QOL_EDITS.items():
            for label, where, region, _van, pat in edits:
                base = disc.addr_to_disc(where, region)
                self.assertEqual(out[base:base + len(pat)], pat,
                                 f"{group}/{label}")

    def test_every_touched_sector_carries_valid_edc_ecc(self) -> None:
        # Without this the emulator's disc layer error-corrects the edits
        # straight back to vanilla and the patch silently does nothing.
        out = self.build(ALL_GROUPS)
        touched = sorted({i // disc.SECTOR_RAW
                          for i in range(len(out)) if out[i] != self.rom[i]})
        self.assertGreater(len(touched), 3)     # more than A1 alone
        again = bytearray(out)
        for sector in touched:
            disc.regenerate_sector(again, sector)
        self.assertEqual(bytes(again), out)

    def test_qol_off_is_byte_identical_to_the_a1_only_patch(self) -> None:
        # Turning every QoL option off must produce exactly the disc players
        # already have, so an image patched before this existed stays valid.
        self.assertEqual(self.build([]), disc.apply_basepatch(self.rom))

    def test_a_wrong_declared_vanilla_is_refused(self) -> None:
        # The whole point of shipping `van` in the patch file: an edit list
        # built for another dump must fail loudly, not corrupt code quietly.
        _label, where, region, van, pat = disc.QOL_EDITS["exit_stage_anytime"][0]
        wrong = bytes((van[0] ^ 0xFF,)) + van[1:]
        with self.assertRaises(ValueError):
            disc.apply_basepatch(self.rom, [(where, pat, region, wrong)])

    def test_an_edit_colliding_with_a1_is_refused(self) -> None:
        # Ordering-dependent output is a bug that shows up in one seed in
        # fifty, so overlapping writes are rejected rather than resolved.
        _l, where, region, van, _p = disc.A1_EDITS[0]
        with self.assertRaises(ValueError):
            disc.apply_basepatch(self.rom, [(where, van, region, van)])


@unittest.skipUnless(have_redump, "Redump image not present")
class TestQoLAgainstTheRedumpImage(_DiscCase):
    """The offsets came from a patcher targeting Redump. Prove they hold there
    too, independently of our development copy."""

    PATH = REDUMP

    def test_every_declared_vanilla_is_what_the_redump_disc_holds(self) -> None:
        for group, edits in disc.QOL_EDITS.items():
            for label, where, region, van, _p in edits:
                base = disc.addr_to_disc(where, region)
                self.assertEqual(bytes(self.rom[base:base + len(van)]), van,
                                 f"{group}/{label}")

    def test_all_qol_on_lands_every_edit(self) -> None:
        out = self.build(ALL_GROUPS)
        for group, edits in disc.QOL_EDITS.items():
            for label, where, region, _van, pat in edits:
                base = disc.addr_to_disc(where, region)
                self.assertEqual(out[base:base + len(pat)], pat,
                                 f"{group}/{label}")
