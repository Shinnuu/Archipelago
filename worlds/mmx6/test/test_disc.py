"""Disc-patch tests.

These need the vanilla disc image, which is never committed, so they skip
cleanly when it is absent. That is deliberate: the patch is the one part of
this world that cannot be checked from source alone, and a silent pass would
be worse than a skip.
"""
import hashlib
import os
import unittest

from .. import disc
from ..Rom import ACCEPTED_HASHES, HASH_US

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)


class TestGeometry(unittest.TestCase):
    """Address mapping, checkable without the disc."""

    def test_the_exe_and_overlay_regions_do_not_overlap_on_disc(self) -> None:
        exe_last = disc.addr_to_disc(disc.EXE_TEXT_END - 1, disc.REGION_EXE)
        rock_first = disc.addr_to_disc(0, disc.REGION_ROCK)
        self.assertLess(exe_last, rock_first)

    def test_a_ram_address_is_rejected_for_the_overlay_region(self) -> None:
        # Overlays must be addressed by CONTAINER OFFSET: each loads to a
        # different RAM address, so a RAM address alone does not identify
        # overlay code. Passing one must fail rather than silently patch.
        with self.assertRaises(ValueError):
            disc.addr_to_disc(0x800F0000, disc.REGION_ROCK)

    def test_out_of_range_addresses_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            disc.addr_to_disc(0x80000000, disc.REGION_EXE)
        with self.assertRaises(ValueError):
            disc.addr_to_disc(disc.ROCK_SIZE, disc.REGION_ROCK)

    def test_the_ap_byte_fits_a_signed_immediate(self) -> None:
        # The patch changes a 16-bit immediate, so the offset has to fit one.
        self.assertTrue(0 <= disc.AP_WEAPONS_OFF <= 0x7FFF)
        self.assertEqual(disc.AP_WEAPONS_OFF, 0xAB)
        self.assertEqual(disc.BEATEN_OFF, 0x60)

    def test_every_a1_edit_changes_only_the_immediate(self) -> None:
        # Same opcode, same registers - only the 16-bit immediate moves. If an
        # edit ever changes anything else, the patch is wrong.
        for label, _where, _region, van, pat in disc.A1_EDITS:
            v = int.from_bytes(van, "little")
            p = int.from_bytes(pat, "little")
            self.assertEqual(v >> 16, p >> 16, f"{label} changed more than the immediate")
            self.assertEqual(v & 0xFFFF, disc.BEATEN_OFF, label)
            self.assertEqual(p & 0xFFFF, disc.AP_WEAPONS_OFF, label)


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestAgainstTheRealDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(ROM, "rb") as f:
            cls.rom = f.read()

    def test_the_accepted_hash_is_this_image(self) -> None:
        self.assertEqual(hashlib.md5(self.rom).hexdigest(), HASH_US)
        self.assertIn(HASH_US, ACCEPTED_HASHES)

    def test_every_a1_site_holds_the_vanilla_bytes_we_expect(self) -> None:
        for label, where, region, van, _pat in disc.A1_EDITS:
            off = disc.addr_to_disc(where, region)
            self.assertEqual(bytes(self.rom[off:off + len(van)]), van, label)

    def test_the_patch_touches_three_sectors_and_one_byte_in_each(self) -> None:
        out = disc.apply_basepatch(self.rom)
        self.assertEqual(len(out), len(self.rom))
        differing = [i for i in range(len(out)) if out[i] != self.rom[i]]
        sectors = {i // disc.SECTOR_RAW for i in differing}
        self.assertEqual(len(sectors), 3)
        for sec in sectors:
            in_sector = [i for i in differing if i // disc.SECTOR_RAW == sec]
            user = [i for i in in_sector
                    if disc.USER_OFF <= i % disc.SECTOR_RAW
                    < disc.USER_OFF + disc.USER_LEN]
            self.assertEqual(len(user), 1,
                             f"sector {sec} changed {len(user)} user bytes")
            # EDC/ECC must be regenerated too, or the emulator's disc layer
            # error-corrects the edit straight back to vanilla.
            self.assertGreater(len(in_sector) - len(user), 0,
                               f"sector {sec} has no parity change")

    def test_patching_an_already_patched_image_is_refused(self) -> None:
        out = disc.apply_basepatch(self.rom)
        with self.assertRaises(ValueError):
            disc.apply_basepatch(out)

    def test_the_patch_is_deterministic(self) -> None:
        self.assertEqual(disc.apply_basepatch(self.rom),
                         disc.apply_basepatch(self.rom))
