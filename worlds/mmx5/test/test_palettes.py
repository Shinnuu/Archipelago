"""Player-palette recolouring.

Cosmetic, but it edits the disc image, so the same rules as every other edit
apply: it must not corrupt a CLUT, must not touch anything it was not asked
to, and must leave every modified sector's EDC/ECC valid. The emulator's disc
layer error-corrects un-reparitied edits straight back to vanilla, so a
palette change that skipped regeneration would silently do nothing.

The stock records here were captured from a running game (hold 0x800D1C49
through boot, read the CLUT the game streams into VRAM, match on disc). If one
of them is ever wrong, `test_stock_records_present_on_disc` catches it against
the real image; everything else runs without one.
"""
import os
import random
import struct
import unittest

from worlds.mmx5 import disc, palettes


def _rng():
    return random.Random(1234)


class TestPresets(unittest.TestCase):
    def test_choices_cover_presets_plus_vanilla_and_random(self):
        self.assertEqual(set(palettes.CHOICES),
                         set(palettes.PRESETS) | {palettes.VANILLA, palettes.RANDOM})

    def test_every_preset_produces_a_legal_clut(self):
        for target, (stock, ramps, _n) in palettes.TARGETS.items():
            for name in palettes.PRESETS:
                out = palettes.recolour(stock, name, ramps)
                with self.subTest(target=target, preset=name):
                    self.assertEqual(len(out), 16)
                    self.assertEqual(out[0], 0x0000, "entry 0 must stay transparent")
                    for i, c in enumerate(out[1:], start=1):
                        self.assertTrue(0 <= c <= 0xFFFF)
                        self.assertTrue(c & 0x8000,
                                        f"{target}/{name} entry {i} lost its STP bit")

    def test_untouched_entries_are_bit_identical(self):
        for target, (stock, ramps, _n) in palettes.TARGETS.items():
            painted = set(palettes.repaint_indices(ramps))
            for name in palettes.PRESETS:
                out = palettes.recolour(stock, name, ramps)
                for i in range(16):
                    if i not in painted:
                        with self.subTest(target=target, preset=name, entry=i):
                            self.assertEqual(out[i], stock[i])

    def test_shading_order_survives(self):
        """A ramp must keep its light-to-dark ordering, or the sprite goes flat."""
        def luma(c):
            c &= 0x7FFF
            r, g, b = (c & 0x1F), (c >> 5) & 0x1F, (c >> 10) & 0x1F
            return 0.299 * r + 0.587 * g + 0.114 * b

        for target, (stock, ramps, _n) in palettes.TARGETS.items():
            for name in palettes.PRESETS:
                out = palettes.recolour(stock, name, ramps)
                for ramp in ramps:        # within a ramp only: entry 11 is a lone
                    idx = list(ramp)      # highlight and 12 starts a new ramp
                    for a, b in zip(idx, idx[1:]):
                        if luma(stock[a]) > luma(stock[b]) + 1.0:
                            with self.subTest(target=target, preset=name, pair=(a, b)):
                                self.assertGreaterEqual(
                                    luma(out[a]), luma(out[b]) - 1.0,
                                    "light/dark order inverted inside a ramp")

    def test_presets_are_distinguishable_from_each_other(self):
        """Two presets that render the same body ramp would be a pointless choice."""
        stock, ramps, _n = palettes.TARGETS["x"]
        seen = {}
        for name in palettes.PRESETS:
            body = palettes.recolour(stock, name, ramps)[12:]
            self.assertNotIn(body, seen,
                             f"{name} renders identically to {seen.get(body)}")
            seen[body] = name

    def test_zero_repaints_his_armour_not_his_hair(self):
        stock, ramps, _n = palettes.TARGETS["zero"]
        self.assertEqual(list(palettes.repaint_indices(ramps)), list(range(4, 12)))
        out = palettes.recolour(stock, "violet", ramps)
        self.assertNotEqual(out[4:8], stock[4:8], "Zero's red armour must change")
        self.assertEqual(out[12:], stock[12:], "Zero's hair/skin must not change")
        self.assertEqual(out[1:4], stock[1:4], "Zero's crystal must not change")

    def test_x_family_keeps_the_face_ramp(self):
        for target in ("x", "falcon", "gaea", "ultimate"):
            stock, ramps, _n = palettes.TARGETS[target]
            out = palettes.recolour(stock, "crimson", ramps)
            with self.subTest(target=target):
                self.assertEqual(out[1:6], stock[1:6], "face/skin must not change")
                self.assertNotEqual(out[12:], stock[12:], "body must change")


class TestResolve(unittest.TestCase):
    def test_vanilla_aliases(self):
        for value in ("vanilla", "", "none", "off", None, "  VANILLA  "):
            self.assertEqual(palettes.resolve(value, _rng()), palettes.VANILLA)

    def test_named_preset_passes_through_case_insensitively(self):
        self.assertEqual(palettes.resolve("CrImSoN", _rng()), "crimson")

    def test_unknown_falls_back_to_vanilla_without_raising(self):
        self.assertEqual(palettes.resolve("chartreuse", _rng()), palettes.VANILLA)

    def test_random_is_a_real_preset_and_seed_reproducible(self):
        a = palettes.resolve("random", random.Random(99))
        b = palettes.resolve("random", random.Random(99))
        self.assertIn(a, palettes.PRESETS)
        self.assertEqual(a, b)


class TestApply(unittest.TestCase):
    """apply() against a synthetic image, so no disc is needed."""

    def _image_with(self, targets, copies=3):
        """A Mode2/Form1 image carrying `copies` of each target's stock CLUT."""
        sectors = 40
        image = bytearray(sectors * disc.SECTOR_RAW)
        for s in range(sectors):
            base = s * disc.SECTOR_RAW
            image[base + 15] = 2          # mode 2
            image[base + 18] = 0x08       # form 1
        spots = []
        at = disc.USER_OFF
        for target in targets:
            stock = struct.pack("<16H", *palettes.TARGETS[target][0])
            for c in range(copies):
                sector = 1 + len(spots)
                off = sector * disc.SECTOR_RAW + disc.USER_OFF + 64
                image[off:off + 32] = stock
                spots.append((target, off))
        return image, spots

    def test_replaces_every_copy_and_reports_sectors(self):
        image, spots = self._image_with(["x", "zero"], copies=3)
        touched = palettes.apply(image, {"x": "gold", "zero": "violet"}, _rng(),
                                  expect_counts=False)
        self.assertTrue(touched)
        for target, off in spots:
            stock = struct.pack("<16H", *palettes.TARGETS[target][0])
            self.assertNotEqual(bytes(image[off:off + 32]), stock,
                                f"{target} copy at {off:#x} was not recoloured")
            self.assertIn(off // disc.SECTOR_RAW, touched)

    def test_vanilla_changes_nothing(self):
        image, _ = self._image_with(["x", "zero"])
        before = bytes(image)
        touched = palettes.apply(image, {t: "vanilla" for t in palettes.TARGETS}, _rng(),
                                  expect_counts=False)
        self.assertEqual(touched, set())
        self.assertEqual(bytes(image), before)

    def test_only_the_named_target_moves(self):
        image, spots = self._image_with(["x", "zero"], copies=2)
        palettes.apply(image, {"x": "gold"}, _rng(), expect_counts=False)
        for target, off in spots:
            stock = struct.pack("<16H", *palettes.TARGETS[target][0])
            got = bytes(image[off:off + 32])
            if target == "x":
                self.assertNotEqual(got, stock)
            else:
                self.assertEqual(got, stock, "recoloured a target we did not ask for")

    def test_touched_sectors_regenerate_cleanly(self):
        image, _ = self._image_with(["x"], copies=2)
        touched = palettes.apply(image, {"x": "emerald"}, _rng(), expect_counts=False)
        for sector in touched:
            disc.regenerate_sector(image, sector)      # must not raise
        for sector in touched:
            base = sector * disc.SECTOR_RAW
            before = bytes(image[base:base + disc.SECTOR_RAW])
            disc.regenerate_sector(image, sector)
            self.assertEqual(bytes(image[base:base + disc.SECTOR_RAW]), before,
                             "EDC/ECC not stable - regeneration is not idempotent")

    def test_edits_are_32_bytes_and_never_move_data(self):
        for stock, new, _label in palettes.palette_edits(
                {t: "magenta" for t in palettes.TARGETS}, _rng()):
            self.assertEqual(len(stock), 32)
            self.assertEqual(len(new), 32)


class TestSettingsAreReRead(unittest.TestCase):
    """settings.get_settings() memoises on the function object.

    Without a deliberate re-read, a player who patches, edits host.yaml and
    patches again in the SAME Launcher session gets their previous colours with
    no error - the wrong disc, silently. Caught by the re-patch e2e; guarded
    here so it cannot come back.
    """

    def test_apply_palettes_rereads_and_restores_the_cache(self):
        import settings

        from worlds.mmx5.Rom import MMX5PatchExtension

        sentinel = object()
        previous = getattr(settings.get_settings, "_cache", None)
        settings.get_settings._cache = sentinel
        try:
            reads = []
            real = settings.get_settings

            def spy():
                reads.append(getattr(settings.get_settings, "_cache", "missing"))
                return real()

            spy._cache = sentinel
            settings.get_settings = spy
            try:
                MMX5PatchExtension.apply_palettes(None, b"\x00" * 64)
            finally:
                settings.get_settings = real
            self.assertTrue(reads, "settings were never consulted")
            self.assertIsNone(reads[0],
                              "cache was not cleared before reading - host.yaml "
                              "edits would be ignored until a restart")
            self.assertIs(getattr(settings.get_settings, "_cache", None), sentinel,
                          "the previous settings cache was not put back")
        finally:
            settings.get_settings._cache = previous


class TestAgainstRealDisc(unittest.TestCase):
    """Runs only where the vanilla image is present; skipped in CI."""

    DISC = r"C:\Users\Ivor\Documents\Game Modding\Games\MegamanX5\Megaman X5.bin"

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.DISC):
            raise unittest.SkipTest("vanilla X5 image not present")
        with open(cls.DISC, "rb") as handle:
            cls.image = handle.read()

    def test_stock_records_present_on_disc_in_expected_numbers(self):
        for target, (stock, _ramps, expected) in palettes.TARGETS.items():
            pat = struct.pack("<16H", *stock)
            count, start = 0, 0
            while True:
                at = self.image.find(pat, start)
                if at == -1:
                    break
                count += 1
                start = at + 2
            with self.subTest(target=target):
                self.assertEqual(count, expected,
                                 f"{target}: found {count} copies, expected {expected}")

    def test_palette_sectors_never_collide_with_the_basepatch(self):
        """Palettes live far below the AP edit range; prove it, do not assume."""
        image = bytearray(self.image)
        touched = palettes.apply(image, {t: "gold" for t in palettes.TARGETS}, _rng())
        self.assertTrue(touched)
        self.assertLess(max(touched), 23433,
                        "a palette record shares a sector with the basepatch")


if __name__ == "__main__":
    unittest.main()
