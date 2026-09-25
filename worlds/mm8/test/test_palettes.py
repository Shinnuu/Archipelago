"""Mega Man's colours: the transform, the override rule, and every record
found on the real disc exactly as often as the research counted."""
import random
import struct
import unittest

from .. import disc, palettes
from .test_disc import TRACK1, have_dump

PLAYER_CLUTS = 134317 * disc.SECTOR_RAW + disc.USER_OFF     # PLAYER.PAC chunk 2


class TestTransform(unittest.TestCase):
    def test_only_the_ramps_move_and_stp_is_kept(self):
        for records in palettes.TARGETS.values():
            for stock, ramps, _copies in records:
                for preset in palettes.PRESETS:
                    new = palettes.recolour(stock, preset, ramps)
                    moved = palettes.repaint_indices(ramps)
                    for i in range(16):
                        if i not in moved:
                            self.assertEqual(new[i], stock[i], (preset, i))
                        self.assertEqual(new[i] & 0x8000, stock[i] & 0x8000, (preset, i))

    def test_the_face_and_the_weapons_are_never_touched(self):
        self.assertEqual(palettes.repaint_indices(palettes.RAMPS), tuple(range(1, 10)))

    def test_both_buster_copies_recolour_alike(self):
        with_stp, without, *_ = palettes.TARGETS["mega_man"]
        for preset in palettes.PRESETS:
            a = palettes.recolour(with_stp[0], preset, palettes.RAMPS)
            b = palettes.recolour(without[0], preset, palettes.RAMPS)
            self.assertEqual([c & 0x7FFF for c in a], list(b), preset)

    def test_vanilla_in_host_yaml_never_overrides(self):
        self.assertFalse(palettes.overrides("vanilla"))
        self.assertFalse(palettes.overrides(palettes.UNSET))
        self.assertTrue(palettes.overrides("crimson"))
        self.assertEqual(palettes.choose({"mega_man": "gold"}, {"mega_man": "vanilla"}),
                         {"mega_man": "gold"})
        self.assertEqual(palettes.choose({"mega_man": "gold"}, {"mega_man": "teal"}),
                         {"mega_man": "teal"})

    def test_vanilla_means_no_edits(self):
        self.assertEqual(palettes.palette_edits({"mega_man": "vanilla"}, random.Random(1)), [])


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestAgainstTheDump(unittest.TestCase):
    track1: bytes

    @classmethod
    def setUpClass(cls):
        with open(TRACK1, "rb") as f:
            cls.track1 = f.read()

    def test_the_table_is_where_the_research_read_it(self):
        clut0 = struct.unpack_from("<16H", self.track1, PLAYER_CLUTS)
        self.assertEqual(clut0, palettes.TARGETS["mega_man"][0][0])

    def test_every_record_is_found_as_often_as_counted(self):
        for records in palettes.TARGETS.values():
            for stock, _ramps, copies in records:
                pattern = struct.pack("<16H", *stock)
                found, at = 0, self.track1.find(pattern)
                while at != -1:
                    found += 1
                    at = self.track1.find(pattern, at + 2)
                self.assertEqual(found, copies, [hex(c) for c in stock[:3]])

    def test_a_recolour_lands_on_every_copy(self):
        image = bytearray(self.track1)
        touched = palettes.apply(image, {"mega_man": "crimson"}, random.Random(1))
        self.assertGreaterEqual(len(touched), 28)
        new = struct.unpack_from("<16H", image, PLAYER_CLUTS)
        self.assertEqual(new, palettes.recolour(palettes.TARGETS["mega_man"][0][0], "crimson", palettes.RAMPS))
        # The weapon CLUTs (1-9) and the full-charge glow (14, 15) are untouched.
        for k in list(range(1, 10)) + [14, 15]:
            off = PLAYER_CLUTS + 32 * k
            self.assertEqual(image[off:off + 32], self.track1[off:off + 32], k)
