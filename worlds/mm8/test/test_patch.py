"""The .apmm8 end to end: patch file -> merged three-track disc.

Needs the vanilla dump (never committed) and skips cleanly without it. Writes
a full ~420 MB disc to a temporary folder, because the merge is exactly the
part a unit test of the pieces cannot see.
"""
import hashlib
import json
import os
import random
import struct
import tempfile
import unittest
from unittest import mock

from .. import Rom, disc, music, palettes

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
        # A patch from before the options carries no seed_edits.json: its
        # option sites stay vanilla, and the intro fix is there regardless.
        at = disc.addr_to_disc(0x8010395C, disc.REGION_EXE)
        self.assertEqual(t1[at:at + 4], bytes.fromhex("24004010"))
        at = disc.addr_to_disc(disc.INTRO_EXIT_DENIED[1], disc.REGION_EXE)
        self.assertEqual(t1[at:at + 4], disc.INTRO_EXIT_DENIED[4])

    def test_the_options_ride_the_patch_file(self):
        from .test_options_disc import fake_world
        world = fake_world(text_skip=1, skip_intro_videos=1, exit_stage_anytime=1,
                           weapon_damage=4, boss_hp_randomization=4, boss_damage=4, pickupsanity=1,
                           max_life=80)
        edits = Rom.seed_edits(world)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            patch = Rom.MM8ProcedurePatch(player=1, player_name="Tester")
            patch.write_file("lab.json", json.dumps({p: (f"Item {p}", None, None)
                                                     for p in range(1, 18)}).encode("utf-8"))
            patch.write_file("seed.json", json.dumps({"stamp": 0x0BADCAFE}).encode("utf-8"))
            patch.write_file("seed_edits.json", Rom.encode_edits(edits))
            patch.write_file("palettes.json", json.dumps({"mega_man": "crimson"}).encode("utf-8"))
            deal = music.music_assignment(random.Random(8))
            patch.write_file("music.json", json.dumps(deal).encode("utf-8"))
            patch_path = os.path.join(tmp, "seed.apmm8")
            patch.write(patch_path)
            target = os.path.join(tmp, "seed.cue")
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            with open(os.path.join(tmp, "seed.bin"), "rb") as f:
                t1 = f.read(disc.TRACK_SIZES[0])
        for label, where, region, _vanilla, payload in edits:
            at = [disc.addr_to_disc(where + i, region) for i in range(len(payload))]
            self.assertEqual(bytes(t1[a] for a in at), payload, label)
        # The colour rode along: PLAYER.PAC's buster CLUT is crimson now.
        clut0 = struct.unpack_from("<16H", t1, 134317 * disc.SECTOR_RAW + disc.USER_OFF)
        self.assertEqual(clut0, palettes.recolour(palettes.TARGETS["mega_man"][0][0], "crimson",
                                                  palettes.RAMPS))
        # And the music: the SOUND region was re-laid, so the EXE's LBA table
        # moved with it (test_music checks the banks themselves).
        region = t1[music.REGION_FIRST * disc.SECTOR_RAW:
                    (music.REGION_FIRST + music.REGION_SECTORS) * disc.SECTOR_RAW]
        self.assertNotEqual(hashlib.md5(region).hexdigest(), music.REGION_MD5)
        rows = bytes(t1[off] for row, *_r in music.VANILLA_ROWS for off in music._row_offsets(row))
        self.assertNotEqual(hashlib.md5(rows).hexdigest(), music.LBA_ROWS_MD5)
