"""Issue -1: the endgame opens on eight Mavericks and nothing else.

Vanilla opens Gate's Lab on any of three conditions - all eight Mavericks,
3000 Nightmare Souls, or the High Max route - and they all funnel into one
flag, `a3`, at ROCK+0x0D6710. The client used to write the progress byte shut
and the game wrote it open again on the next hub transition, which is the
cutscene loop testers reported. This switches the two unwanted conditions off
where the decision is actually made.

What these pin, in rough order of what would hurt most if it broke:

  * the patch must NOT be applied under the `sigma` goal, where opening on
    souls is the game's own design;
  * the all-eight test itself must be untouched, or the endgame never opens
    at all and every seed is unwinnable;
  * the edits must leave code shape identical - one immediate each - because
    the whole point of doing it this way was to avoid injected code and
    overlay-relative jump targets;
  * the sites must still hold the vanilla bytes on the disc we ship against.
"""
import os
import struct
import unittest

from .. import disc
from ..options import Goal
from . import MMX6TestBase

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)

# The all-eight test, which must survive untouched:
#   lbu v0, 0x60(a1) / xori v0, v0, 0xFF / sltiu a3, v0, 1
ALL_EIGHT_SITE = 0x0D6718          # the xori (0x0D6714 is the nop)
ALL_EIGHT_WORD = 0x384200FF

# Stores to the progress byte that carry ordinary progression, and must never
# be in the edit list. ROCK+0x0C2594 is the one that writes 3.
DO_NOT_TOUCH = (0x0C24C0,          # writes 2 - reached stage select
                0x0CBE2C)          # save LOAD, copies the byte back in


class TestTheEditList(unittest.TestCase):
    def test_it_is_eight_sites(self) -> None:
        self.assertEqual(len(disc.ENDGAME_GATE_EDITS), 8)

    def test_every_edit_is_one_whole_instruction(self) -> None:
        for label, _w, _r, van, pat in disc.ENDGAME_GATE_EDITS:
            self.assertEqual(len(van), 4, label)
            self.assertEqual(len(pat), 4, label)

    def test_every_edit_only_raises_an_immediate(self) -> None:
        # The opcode and both registers must be identical before and after.
        # Anything else means the code shape changed, which is exactly what
        # this approach exists to avoid.
        for label, _w, _r, van, pat in disc.ENDGAME_GATE_EDITS:
            a = struct.unpack("<I", van)[0]
            b = struct.unpack("<I", pat)[0]
            self.assertEqual(a >> 16, b >> 16, label + ": not just an immediate")
            self.assertEqual(a >> 26, 0x0A, label + ": vanilla is not an slti")
            self.assertGreater(b & 0xFFFF, a & 0xFFFF, label + ": not raised")
            self.assertEqual(b & 0xFFFF, disc.ENDGAME_GATE_UNREACHABLE, label)

    def test_the_souls_sites_compare_against_3000(self) -> None:
        souls = [e for e in disc.ENDGAME_GATE_EDITS if "souls" in e[0]]
        self.assertEqual(len(souls), 7)
        for label, _w, _r, van, _p in souls:
            self.assertEqual(struct.unpack("<I", van)[0] & 0xFFFF,
                             disc.ENDGAME_GATE_SOULS, label)

    def test_it_never_touches_ordinary_progression(self) -> None:
        # The X5 blind-NOP lesson: suppressing a progression write softlocks
        # the endgame. Of nine stores to the progress byte only one writes 3,
        # and none of them is in this list - we act on the flag, not the store.
        where = {w for _l, w, _r, _v, _p in disc.ENDGAME_GATE_EDITS}
        for site in DO_NOT_TOUCH + (0x0C2594,):
            self.assertNotIn(site, where)

    def test_it_does_not_overlap_any_other_edit(self) -> None:
        spans = set()
        for _l, w, r, van, _p in disc.ENDGAME_GATE_EDITS:
            for i in range(len(van)):
                spans.add(disc.addr_to_disc(w + i, r))
        others = list(disc.BASE_EDITS)
        for group in disc.QOL_EDITS.values():
            for _l, w, r, van, _p in group:
                for i in range(len(van)):
                    self.assertNotIn(disc.addr_to_disc(w + i, r), spans)
        for w, payload, r in others:
            for i in range(len(payload)):
                self.assertNotIn(disc.addr_to_disc(w + i, r), spans)


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestAgainstTheDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(ROM, "rb") as fh:
            cls.rom = fh.read()

    def test_every_site_holds_the_recorded_vanilla_bytes(self) -> None:
        for label, w, r, van, _p in disc.ENDGAME_GATE_EDITS:
            off = disc.addr_to_disc(w, r)
            self.assertEqual(self.rom[off:off + len(van)], van, label)

    def test_the_all_eight_test_is_left_alone(self) -> None:
        # If this were ever patched the endgame would never open and every
        # seed would be unwinnable - the worst failure this feature can have.
        off = disc.addr_to_disc(ALL_EIGHT_SITE, disc.REGION_ROCK)
        self.assertEqual(
            struct.unpack("<I", self.rom[off:off + 4])[0], ALL_EIGHT_WORD)
        self.assertNotIn(ALL_EIGHT_SITE,
                         {w for _l, w, _r, _v, _p in disc.ENDGAME_GATE_EDITS})

    def test_the_patched_image_changes_exactly_these_bytes(self) -> None:
        extra = [(w, p, r, v) for _l, w, r, v, p in disc.ENDGAME_GATE_EDITS]
        img = disc.apply_basepatch(self.rom, extra)
        for label, w, r, _v, pat in disc.ENDGAME_GATE_EDITS:
            off = disc.addr_to_disc(w, r)
            self.assertEqual(img[off:off + len(pat)], pat, label)


def _seed_edits(world) -> set:
    """{(addr, region)} the seed's own .apmmx6 would carry.

    Read out of the file patch_rom writes rather than recomputed, so this
    cannot pass while the real emitted list says something else.
    """
    import json

    from ..Rom import MMX6ProcedurePatch, patch_rom

    written = {}

    class _Capture(MMX6ProcedurePatch):
        def write_file(self, name, data):     # noqa: D102
            written[name] = data

    patch_rom(world, _Capture(player=world.player, player_name="P"))
    return {(e["addr"], e["region"])
            for e in json.loads(written["seed_edits.json"].decode("utf-8"))}


class TestAppliedUnderAllMavericks(MMX6TestBase):
    options = {"goal": Goal.option_all_mavericks}

    def test_the_seed_carries_the_gate_edits(self) -> None:
        carried = _seed_edits(self.world)
        for _l, w, r, _v, _p in disc.ENDGAME_GATE_EDITS:
            self.assertIn((w, r), carried)


class TestNotAppliedUnderSigma(MMX6TestBase):
    """Under `sigma`, opening on souls is the game's own design."""
    options = {"goal": Goal.option_sigma}

    def test_the_seed_carries_none_of_them(self) -> None:
        carried = _seed_edits(self.world)
        for _l, w, r, _v, _p in disc.ENDGAME_GATE_EDITS:
            self.assertNotIn((w, r), carried)
