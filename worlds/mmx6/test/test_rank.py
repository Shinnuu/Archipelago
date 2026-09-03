"""`starting_rank` - buying Power-up Part slots with a threshold edit.

Hunter Rank decides how many Parts you may equip, Souls buy Rank, and both
counters are per character. In the base game the first slot costs 500 of that
character's own Souls, so a seed hands you 24 Parts as items long before
either character can wear one - and a run played mostly as X leaves Zero at
rank D with no slots at all. That is what a playtest hit (2026-09-03).

The lever is the threshold table, eight u16 descending at EXE 0x8006D624.
What these tests pin:

  * the vanilla table is what the DISC holds, not what a third-party workbook
    says it holds. Every other edit in this world declares its vanilla bytes
    and is checked against the image; this one is no different, and it is 16
    bytes rather than 2 so that a wrong offset cannot quietly match.
  * one entry changes and the rest do not. The ranks above the floor have to
    keep costing what they cost, or the option stops being "start here" and
    becomes "rank means nothing".
  * the entry zeroed is the RIGHT one. The scan takes the first index from
    the top whose threshold the player has reached, so zeroing index i is
    what makes rank i free - and zeroing a higher index would hand out a
    rank nobody asked for, along with the boss levels that come with it.

What these tests CANNOT show is that the Parts screen reads the rank this
table produces. The scan at ROCK+0x0DEC74 is disassembled and the table is
ours; the slot counts per rank are the player's guides. Live check needed.
"""
import os
import unittest

from .. import disc
from . import MMX6TestBase
from .test_life_scaling import _seed_edits

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)

# The ranks the option offers, and the entry each one has to zero.
EXPECTED_INDEX = {"a": 4, "sa": 3, "ga": 2, "pa": 1, "uh": 0}


class TestTheTable(unittest.TestCase):
    def test_the_thresholds_are_the_ones_the_docs_quote(self) -> None:
        values = [int.from_bytes(disc.RANK_TABLE_VANILLA[i:i + 2], "little")
                  for i in range(0, len(disc.RANK_TABLE_VANILLA), 2)]
        self.assertEqual(values, [9999, 5000, 1200, 800, 500, 300, 200, 0])
        self.assertEqual(len(disc.RANK_ORDER), len(values))
        self.assertEqual(disc.RANK_ORDER[-1], "D",
                         "the last entry is the hard floor the scan lands on")

    def test_off_is_no_edit_at_all(self) -> None:
        self.assertEqual(disc.rank_threshold_edits("off"), [])

    def test_each_rank_zeroes_exactly_its_own_entry(self) -> None:
        for rank, index in EXPECTED_INDEX.items():
            (label, where, region, van, pat), = disc.rank_threshold_edits(rank)
            self.assertEqual(where, disc.RANK_TABLE_ADDR)
            self.assertEqual(region, disc.REGION_EXE)
            self.assertEqual(van, disc.RANK_TABLE_VANILLA)
            self.assertEqual(len(pat), len(van))
            self.assertEqual(len(pat) % 4, 0, "whole instructions' worth")
            self.assertEqual(pat[index * 2:index * 2 + 2], b"\x00\x00",
                             f"{rank} did not zero index {index}")
            for other in range(len(disc.RANK_ORDER)):
                if other == index:
                    continue
                self.assertEqual(
                    pat[other * 2:other * 2 + 2],
                    van[other * 2:other * 2 + 2],
                    f"{rank} also changed index {other} ({disc.RANK_ORDER[other]})")

    def test_the_ranks_above_the_floor_still_cost_what_they_cost(self) -> None:
        # The point of zeroing ONE entry: rank_a must not make SA free too,
        # because SA is where boss fight levels start climbing.
        (_l, _w, _r, _v, pat), = disc.rank_threshold_edits("a")
        self.assertEqual(int.from_bytes(pat[3 * 2:3 * 2 + 2], "little"), 800)
        self.assertEqual(int.from_bytes(pat[2 * 2:2 * 2 + 2], "little"), 1200)

    def test_case_does_not_matter(self) -> None:
        self.assertEqual(disc.rank_threshold_edits("sa"),
                         disc.rank_threshold_edits("SA"))

    def test_rank_d_and_nonsense_are_refused(self) -> None:
        # D is the floor - it already costs nothing, and "zeroing" it would
        # write over the terminator the scan depends on.
        with self.assertRaises(ValueError):
            disc.rank_threshold_edits("D")
        with self.assertRaises(ValueError):
            disc.rank_threshold_edits("SSS")


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestAgainstTheDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(ROM, "rb") as image:
            cls.rom = image.read()

    def test_the_declared_vanilla_is_what_the_disc_holds(self) -> None:
        base = disc.addr_to_disc(disc.RANK_TABLE_ADDR, disc.REGION_EXE)
        self.assertEqual(self.rom[base:base + len(disc.RANK_TABLE_VANILLA)],
                         disc.RANK_TABLE_VANILLA)

    def test_it_survives_a_real_patch(self) -> None:
        edits = disc.rank_threshold_edits("a")
        extra = [(w, p, r, v) for _l, w, r, v, p in edits]
        out = disc.apply_basepatch(self.rom, extra)
        base = disc.addr_to_disc(disc.RANK_TABLE_ADDR, disc.REGION_EXE)
        self.assertEqual(out[base:base + 16],
                         edits[0][4], "the table on the image")


class TestTheSeedCarriesIt(MMX6TestBase):
    options = {"starting_rank": "rank_a"}

    def test_the_apmmx6_has_the_edit(self) -> None:
        carried = _seed_edits(self.world)
        (_l, _w, _r, _v, pat), = disc.rank_threshold_edits("a")
        self.assertEqual(
            carried.get((disc.RANK_TABLE_ADDR, disc.REGION_EXE)), pat.hex())


class TestTheSeedDoesNotCarryItByDefault(MMX6TestBase):
    options = {}

    def test_off_touches_the_disc_not_at_all(self) -> None:
        carried = _seed_edits(self.world)
        self.assertNotIn((disc.RANK_TABLE_ADDR, disc.REGION_EXE), carried)
