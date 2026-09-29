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

    @staticmethod
    def minimal_patch(path: str, seed: dict) -> None:
        patch = Rom.MM8ProcedurePatch(player=1, player_name="Tester")
        patch.write_file("lab.json", json.dumps({p: (f"Item {p}", None, None)
                                                 for p in range(1, 18)}).encode("utf-8"))
        patch.write_file("seed.json", json.dumps(seed).encode("utf-8"))
        patch.write(path)

    def test_a_patch_from_another_code_layout_is_refused(self):
        """Review M1: the hooks' targets are fixed at generation, the routines
        laid out at patch time - a mismatch would jump into other code. The
        control is the same patch with this apworld's layout."""
        moved = {**disc.code_layout(), "P5 Lab purchase": disc.code_layout()["P5 Lab purchase"] + 8}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            self.minimal_patch(os.path.join(tmp, "old.apmm8"), {"stamp": 0x0BADCAFE, "layout": moved})
            with self.assertRaisesRegex(ValueError, "different version of the Mega Man 8 apworld"):
                Rom.MM8ProcedurePatch(os.path.join(tmp, "old.apmm8")).patch(os.path.join(tmp, "old.cue"))
            self.assertEqual(sorted(os.listdir(tmp)), ["old.apmm8"], "nothing left behind")
            self.minimal_patch(os.path.join(tmp, "new.apmm8"),
                               {"stamp": 0x0BADCAFE, "layout": disc.code_layout()})
            Rom.MM8ProcedurePatch(os.path.join(tmp, "new.apmm8")).patch(os.path.join(tmp, "new.cue"))
            self.assertIn("new.bin", os.listdir(tmp))

    def test_a_player_name_outside_ascii_and_reusing_a_built_disc(self):
        """Review M2: the cue was written in the Windows code page - "ö" became
        a byte no UTF-8 reader resolves, Japanese crashed after the .bin was
        written and left an empty cue that every retry then reused. And a
        disc is reused only when it is exactly the one this patch makes:
        another seed's is rebuilt."""
        name = "AP_1_P1_Ivör ロックマン"
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            patch_path = os.path.join(tmp, name + ".apmm8")
            self.minimal_patch(patch_path, {"stamp": 0x0BADCAFE, "layout": disc.code_layout()})
            target = os.path.join(tmp, name + ".cue")
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            with open(target, "rb") as f:
                self.assertEqual(f.read().decode("utf-8"), disc.merged_cue(name + ".bin"))
            bin_path = os.path.join(tmp, name + ".bin")
            built = os.path.getmtime(bin_path)
            handler = Rom.MM8ProcedurePatch(patch_path)
            handler.patch(target)
            self.assertEqual(os.path.getmtime(bin_path), built, "this seed's disc is reused")
            self.assertEqual(handler.player_name, "Tester", "the client still gets its slot")
            stamp_at = disc.addr_to_disc(disc.AP_STAMP, disc.REGION_EXE)
            with open(bin_path, "r+b") as f:                        # another seed's disc
                f.seek(stamp_at)
                f.write((0x11111111).to_bytes(4, "little"))
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            with open(bin_path, "rb") as f:
                f.seek(stamp_at)
                self.assertEqual(f.read(4), (0x0BADCAFE).to_bytes(4, "little"), "rebuilt")
            self.assertEqual(sorted(os.listdir(tmp)), sorted([name + ".apmm8", name + ".bin", name + ".cue"]))

    def test_an_older_apworlds_disc_is_rebuilt(self):
        """0.2.0 review M1: 0.1.0 reused any disc whose AP header matched - and
        an apworld update does not change the header, so a tester re-opening a
        0.1.0 seed on 0.2.0 kept the 0.1.0 disc and its NO/CANCEL Lab prices.
        Now every byte is compared: a 0.1.0 disc (the price-digit words still
        vanilla, the header identical) is rebuilt; so is a damaged audio
        track. The control is the untouched disc, reused above."""
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            patch_path = os.path.join(tmp, "seed.apmm8")
            self.minimal_patch(patch_path, {"stamp": 0x0BADCAFE, "layout": disc.code_layout()})
            target = os.path.join(tmp, "seed.cue")
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            bin_path = os.path.join(tmp, "seed.bin")
            with open(bin_path, "r+b") as f:                        # what 0.1.0 built
                for _label, where, region, vanilla, _payload in disc.LAB_PRICE_DIGITS:
                    f.seek(disc.addr_to_disc(where, region))
                    f.write(vanilla)
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            with open(bin_path, "rb") as f:
                for _label, where, region, _vanilla, payload in disc.LAB_PRICE_DIGITS:
                    f.seek(disc.addr_to_disc(where, region))
                    self.assertEqual(f.read(len(payload)), payload, "rebuilt with the price fix")
            with open(bin_path, "r+b") as f:                        # a damaged audio track
                f.seek(-1000, os.SEEK_END)
                byte = f.read(1)
                f.seek(-1000, os.SEEK_END)
                f.write(bytes([byte[0] ^ 0xFF]))
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            with open(bin_path, "rb") as f:
                f.seek(-1000, os.SEEK_END)
                self.assertEqual(f.read(1), byte, "rebuilt")

    def test_a_changed_colour_is_rebuilt(self):
        """The same seed's disc with a different colour (a host.yaml override
        changed since, the "I changed a colour and nothing happened" of 0.1.0's
        guide) is rebuilt - every byte is compared, not a header."""
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            patch_path = os.path.join(tmp, "seed.apmm8")
            self.minimal_patch(patch_path, {"stamp": 0x0BADCAFE, "layout": disc.code_layout()})
            target = os.path.join(tmp, "seed.cue")
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            bin_path = os.path.join(tmp, "seed.bin")
            with open(bin_path, "rb") as f:
                vanilla_colour = hashlib.md5(f.read()).hexdigest()
            patch = Rom.MM8ProcedurePatch(patch_path)
            patch.read()
            patch.write_file("palettes.json", json.dumps({t: "crimson" for t in palettes.TARGETS}).encode("utf-8"))
            patch.write(patch_path)
            Rom.MM8ProcedurePatch(patch_path).patch(target)
            with open(bin_path, "rb") as f:
                self.assertNotEqual(hashlib.md5(f.read()).hexdigest(), vanilla_colour)

    def test_a_disc_in_use_says_to_close_bizhawk(self):
        """Windows will not replace a file another program has open - the old
        disc still loaded in BizHawk. The player is told what to do, and no
        half-written file is left behind."""
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            patch_path = os.path.join(tmp, "seed.apmm8")
            self.minimal_patch(patch_path, {"stamp": 0x0BADCAFE, "layout": disc.code_layout()})
            target = os.path.join(tmp, "seed.cue")
            with mock.patch.object(Rom.os, "replace", side_effect=PermissionError(13, "in use")):
                with self.assertRaisesRegex(PermissionError, "Close BizHawk, then open the .apmm8 again"):
                    Rom.MM8ProcedurePatch(patch_path).patch(target)
            self.assertEqual(sorted(os.listdir(tmp)), ["seed.apmm8"], "nothing left behind")

    def test_the_patch_format(self):
        """0.2.0 review m3: 0.1.0 and 0.2.0 lay the code out identically, so
        the layout alone let the released 0.1.0 apworld patch a 0.2.0 seed -
        stage_order's edits on, the price fix and the client's Duo lock
        missing. The format rides inside the layout, which 0.1.0 compares
        whole. This apworld takes a 0.1.0 patch (no format) and its own, and
        refuses a newer one."""
        from test.general import setup_multiworld
        from .. import MM8World
        world = setup_multiworld([MM8World], seed=1).worlds[1]
        entries = {p: (f"Item {p}", None, None) for p in range(1, 18)}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "lab_entries", return_value=entries):
            path = Rom.write_patch(world, tmp)
            patch = Rom.MM8ProcedurePatch(path)
            patch.read()
            layout = json.loads(patch.get_file("seed.json"))["layout"]
        self.assertEqual(layout["format"], Rom.PATCH_FORMAT)
        self.assertNotEqual(layout, disc.code_layout(), "what 0.1.0 compares: refused")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            self.minimal_patch(os.path.join(tmp, "newer.apmm8"),
                               {"stamp": 1, "layout": {**disc.code_layout(), "format": Rom.PATCH_FORMAT + 1}})
            with self.assertRaisesRegex(ValueError, "different version of the Mega Man 8 apworld"):
                Rom.MM8ProcedurePatch(os.path.join(tmp, "newer.apmm8")).patch(os.path.join(tmp, "newer.cue"))
            self.minimal_patch(os.path.join(tmp, "ours.apmm8"),
                               {"stamp": 1, "layout": {**disc.code_layout(), "format": Rom.PATCH_FORMAT}})
            Rom.MM8ProcedurePatch(os.path.join(tmp, "ours.apmm8")).patch(os.path.join(tmp, "ours.cue"))
            self.assertIn("ours.bin", os.listdir(tmp))

    def test_the_options_ride_the_patch_file(self):
        from .test_options_disc import fake_world
        from .. import names
        world = fake_world(text_skip=1, skip_intro_videos=1, exit_stage_anytime=1,
                           weapon_damage=4, boss_hp_randomization=4, boss_damage=4, pickupsanity=1,
                           max_life=80, stage_order=2)
        edits = Rom.seed_edits(world)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(Rom, "get_base_rom_path", return_value=TRACK1):
            patch = Rom.MM8ProcedurePatch(player=1, player_name="Tester")
            # Every entry the player's own part: each describes itself.
            patch.write_file("lab.json", json.dumps({p: (names.PARTS[p - 1], None, None)
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
        for label, where, region, _vanilla, payload in edits + disc.LAB_PRICE_DIGITS:
            at = [disc.addr_to_disc(where + i, region) for i in range(len(payload))]
            self.assertEqual(bytes(t1[a] for a in at), payload, label)
        # The Lab text describes each own part; Exit's line knows the option is on.
        size = int.from_bytes(bytes(t1[disc.addr_to_disc(disc.LAB_TEXT_SIZE_FIELD + i, "pack:LABO.PAC")]
                                    for i in range(4)), "little")
        chunk = bytes(t1[disc.addr_to_disc(disc.LAB_TEXT_OFFSET + i, "pack:LABO.PAC")]
                      for i in range(size))

        def entry(part: str) -> bytes:
            index = disc.LAB_FIRST_DESCRIPTION + names.PART_ID[part] - 1
            start = struct.unpack_from("<H", chunk, 2 * index)[0]
            return chunk[start:start + 200]
        self.assertIn(bytes(disc.LAB_CHARSET[c] for c in "Buster shots fly"), entry(names.BOOST_PART))
        self.assertIn(bytes(disc.LAB_CHARSET[c] for c in "No effect"), entry(names.EXIT))
        self.assertNotIn(bytes(disc.LAB_CHARSET[c] for c in "cleared stage"), entry(names.EXIT))
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
