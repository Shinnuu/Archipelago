"""Disc-patch tests.

These need the vanilla disc image, which is never committed, so they skip
cleanly when it is absent. That is deliberate: the patch is the one part of
this world that cannot be checked from source alone, and a silent pass would
be worse than a skip.
"""
import hashlib
import mmap
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
        # Memory-mapped rather than read. The image is 600MB and patching it
        # needs two more copies; reading a third into the fixture pushed peak
        # use past what this machine can COMMIT (not past its physical RAM)
        # whenever other large applications are open, and the tests then died
        # with MemoryError - which reads as a patch regression when nothing is
        # wrong. A mapping is file-backed and costs no commit, and bytes(...)
        # of a slice behaves identically for every assertion here.
        cls._fh = open(ROM, "rb")
        cls.rom = mmap.mmap(cls._fh.fileno(), 0, access=mmap.ACCESS_READ)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.rom.close()
        cls._fh.close()

    def patch(self):
        """apply_basepatch, or skip if the machine cannot spare the memory.

        A check that could not RUN must not be reported as a check that
        FAILED - that is how a release gate learns to cry wolf.
        """
        try:
            return disc.apply_basepatch(self.rom)
        except MemoryError:
            self.skipTest("not enough memory to hold two copies of a 600MB "
                          "image; close other large applications")

    def test_the_accepted_hash_is_this_image(self) -> None:
        self.assertEqual(hashlib.md5(self.rom).hexdigest(), HASH_US)
        self.assertIn(HASH_US, ACCEPTED_HASHES)

    def test_every_a1_site_holds_the_vanilla_bytes_we_expect(self) -> None:
        for label, where, region, van, _pat in disc.A1_EDITS:
            off = disc.addr_to_disc(where, region)
            self.assertEqual(bytes(self.rom[off:off + len(van)]), van, label)

    def test_the_patch_touches_three_sectors_and_one_byte_in_each(self) -> None:
        out = self.patch()
        self.assertEqual(len(out), len(self.rom))

        # Compare sector by sector rather than byte by byte. The obvious
        # version - a list comprehension over range(len(out)) - is a 600
        # MILLION iteration Python loop that also allocates a list of every
        # differing index, and it really did fail with MemoryError under load.
        # Slicing hands the comparison to C and keeps memory flat, while still
        # proving the whole image was checked, which is the point of the test.
        sectors = [n for n in range(len(out) // disc.SECTOR_RAW)
                   if out[n * disc.SECTOR_RAW:(n + 1) * disc.SECTOR_RAW]
                   != self.rom[n * disc.SECTOR_RAW:(n + 1) * disc.SECTOR_RAW]]
        self.assertEqual(len(sectors), 3, "patch changed the wrong sector count")

        for sec in sectors:
            base = sec * disc.SECTOR_RAW
            differing = [i for i in range(disc.SECTOR_RAW)
                         if out[base + i] != self.rom[base + i]]
            user = [i for i in differing
                    if disc.USER_OFF <= i < disc.USER_OFF + disc.USER_LEN]
            self.assertEqual(len(user), 1,
                             f"sector {sec} changed {len(user)} user bytes")
            # EDC/ECC must be regenerated too, or the emulator's disc layer
            # error-corrects the edit straight back to vanilla.
            self.assertGreater(len(differing) - len(user), 0,
                               f"sector {sec} has no parity change")

    def test_patching_an_already_patched_image_is_refused(self) -> None:
        out = self.patch()
        with self.assertRaises(ValueError):
            disc.apply_basepatch(out)

    def test_the_patch_is_deterministic(self) -> None:
        # Hash rather than compare: two 600MB results plus the source held at
        # once is 1.8GB for an assertion that a 32-byte digest settles.
        first = hashlib.md5(self.patch()).hexdigest()
        second = hashlib.md5(self.patch()).hexdigest()
        self.assertEqual(first, second)
