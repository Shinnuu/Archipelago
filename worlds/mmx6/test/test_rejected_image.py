"""What the patcher says when it refuses a disc image.

A bare "MD5 mismatch" is unhelpful in the case that actually happens most: the
player pointed the base-image setting at a disc a PREVIOUS seed produced. On
X5 that exact confusion sent a tester deleting every X5 file he had, and the
rejection there learned to name the cause. These pin the X6 equivalent.

The interesting inputs are all failures, so the disc image is only needed for
the one test that builds a real patched image; the rest are synthetic.
"""
import mmap
import os
import unittest

from .. import disc
from ..Rom import diagnose_rejected_image

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)

PROBE = disc.addr_to_disc(0x8003C278, disc.REGION_EXE)
VANILLA = bytes.fromhex("6000a290")
PATCHED = bytes.fromhex("ab00a290")


class TestDiagnosisWithoutTheDisc(unittest.TestCase):
    def test_a_short_file_is_called_out_as_not_a_disc(self) -> None:
        for size in (0, 1024, PROBE):
            detail = diagnose_rejected_image(bytes(size))
            self.assertIsNotNone(detail, f"size {size}")
            self.assertIn("too small", detail)

    def test_an_image_with_our_patch_in_it_is_named_as_ours(self) -> None:
        data = bytearray(PROBE + 64)
        data[PROBE:PROBE + 4] = PATCHED
        detail = diagnose_rejected_image(bytes(data))
        self.assertIsNotNone(detail)
        self.assertIn("ALREADY PATCHED", detail)
        # and it must name the fix, not just the diagnosis
        self.assertIn("mmx6_options", detail)

    def test_an_untested_but_intact_x6_image_says_so(self) -> None:
        data = bytearray(PROBE + 64)
        data[PROBE:PROBE + 4] = VANILLA
        detail = diagnose_rejected_image(bytes(data))
        self.assertIsNotNone(detail)
        self.assertIn("not a dump we have tested", detail)

    def test_an_unrelated_file_gets_no_invented_diagnosis(self) -> None:
        # Saying nothing is correct here. A confident wrong explanation is
        # worse than the bare hash mismatch it replaced.
        data = bytearray(PROBE + 64)
        data[PROBE:PROBE + 4] = b"\xde\xad\xbe\xef"
        self.assertIsNone(diagnose_rejected_image(bytes(data)))

    def test_the_three_diagnoses_are_distinguishable(self) -> None:
        short = diagnose_rejected_image(bytes(16))
        ours = bytearray(PROBE + 64); ours[PROBE:PROBE + 4] = PATCHED
        theirs = bytearray(PROBE + 64); theirs[PROBE:PROBE + 4] = VANILLA
        msgs = [short,
                diagnose_rejected_image(bytes(ours)),
                diagnose_rejected_image(bytes(theirs))]
        self.assertEqual(len(set(msgs)), 3)


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestDiagnosisAgainstRealImages(unittest.TestCase):
    """The synthetic tests above only prove the branch logic. These prove the
    probe site is the right one on a real image, in both directions."""

    def test_the_vanilla_disc_is_recognised_as_intact(self) -> None:
        with open(ROM, "rb") as f, \
                mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            self.assertEqual(bytes(mm[PROBE:PROBE + 4]), VANILLA)
            detail = diagnose_rejected_image(bytes(mm[:PROBE + 4]))
        self.assertIn("not a dump we have tested", detail)

    def test_a_disc_we_patched_is_recognised_as_ours(self) -> None:
        # Build the real thing rather than poking a byte: this is the exact
        # image a player's .apmmx6 produces, so if the probe site ever moved
        # out from under the diagnosis, this is what would catch it.
        with open(ROM, "rb") as f:
            rom = f.read()
        try:
            patched = disc.apply_basepatch(rom)
        except MemoryError:
            self.skipTest("not enough memory to hold two copies of a 600MB "
                          "image; close other large applications")
        detail = diagnose_rejected_image(patched)
        self.assertIsNotNone(detail)
        self.assertIn("ALREADY PATCHED", detail)

    def test_a_qol_patched_disc_is_also_recognised(self) -> None:
        # A1 is applied whatever the QoL options are, which is why one probe
        # site covers every disc this world can produce.
        with open(ROM, "rb") as f:
            rom = f.read()
        extra = [(where, pat, region, van) for _l, where, region, van, pat
                 in disc.qol_edits(sorted(disc.QOL_EDITS))]
        try:
            patched = disc.apply_basepatch(rom, extra)
        except MemoryError:
            self.skipTest("not enough memory to hold two copies of a 600MB "
                          "image; close other large applications")
        detail = diagnose_rejected_image(patched)
        self.assertIsNotNone(detail)
        self.assertIn("ALREADY PATCHED", detail)
