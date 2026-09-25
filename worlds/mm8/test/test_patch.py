"""The .apmm8 end to end: patch file -> merged three-track disc.

Needs the vanilla dump (never committed) and skips cleanly without it. Writes
a full ~420 MB disc to a temporary folder, because the merge is exactly the
part a unit test of the pieces cannot see.
"""
import hashlib
import json
import os
import struct
import tempfile
import unittest
from unittest import mock

from .. import Rom, disc

DUMP = r"C:\Users\Ivor\Documents\Game Modding\Games\Mega Man 8 (USA)"
TRACK1 = os.path.join(DUMP, "Mega Man 8 (USA) (Track 1).bin")
have_dump = os.path.exists(TRACK1)


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestPatchFile(unittest.TestCase):
    def test_apmm8_builds_the_merged_disc(self):
        entries = {p: (f"Item {p}", None if p % 2 else "Bob", None if p % 2 else "Mega Man X5")
                   for p in range(1, 18)}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            patch = Rom.MM8ProcedurePatch(player=1, player_name="Tester")
            patch.write_file("lab.json", json.dumps(entries).encode("utf-8"))
            patch.write_file("seed.json", json.dumps({"stamp": 0x0BADCAFE}).encode("utf-8"))
            patch_path = os.path.join(tmp, "seed.apmm8")
            patch.write(patch_path)

            target = os.path.join(tmp, "seed.cue")
            Rom.MM8ProcedurePatch(patch_path).patch(target)

            self.assertEqual(sorted(os.listdir(tmp)), ["seed.apmm8", "seed.bin", "seed.cue"])
            with open(os.path.join(tmp, "seed.bin"), "rb") as f:
                merged = f.read()
            with open(target) as f:
                cue = f.read()

        t1, t2, t3 = disc.split_merged(merged)
        self.assertEqual(hashlib.md5(t2).hexdigest(), disc.TRACK_MD5[1])
        self.assertEqual(hashlib.md5(t3).hexdigest(), disc.TRACK_MD5[2])
        self.assertEqual(cue, disc.merged_cue("seed.bin"))
        # The repriced Lab.
        off = disc.addr_to_disc(disc.SHOP_TABLE, disc.REGION_EXE)
        for record, part in enumerate(disc.SHOP_RECORDS):
            if part is not None:
                self.assertEqual(t1[off + 2 * record + 1], disc.LAB_PRICE[part])
        # The Lab text: Bob's entries name him and his game.
        size = int.from_bytes(bytes(t1[disc.addr_to_disc(disc.LAB_TEXT_SIZE_FIELD + i, "pack:LABO.PAC")]
                                    for i in range(4)), "little")
        chunk = bytes(t1[disc.addr_to_disc(disc.LAB_TEXT_OFFSET + i, "pack:LABO.PAC")]
                      for i in range(size))
        start = struct.unpack_from("<H", chunk, 2 * (disc.LAB_FIRST_DESCRIPTION + 1))[0]
        text = chunk[start:start + 40]
        self.assertIn(bytes(disc.LAB_CHARSET[c] for c in "Bob's"), text)
        self.assertIn(bytes(disc.LAB_CHARSET[c] for c in "Item 2"), text)
        # The seed's AP block header.
        off = disc.addr_to_disc(disc.AP_BLOCK, disc.REGION_EXE)
        self.assertEqual(t1[off:off + 12], b"APM8" + (1).to_bytes(4, "little")
                         + (0x0BADCAFE).to_bytes(4, "little"))
