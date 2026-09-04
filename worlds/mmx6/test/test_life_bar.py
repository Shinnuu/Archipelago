"""The life bar's low end - `disc.life_bar_edits`.

Below a gauge of 32 the bar's frame index drops beneath its own artwork and
picks up other HUD sprites. Reported from live play on 0.3.0 as "wrong sprites
in every stage", and it appeared to heal itself later because received
upgrades raised the gauge back over 32.

The fix floors the index at 0x88, the shortest real frame, through a six-word
hook in free EXE space. What these tests protect is that the hook is what we
think it is - the right instruction replaced, a jump that lands on the hook,
a hook that jumps back to the right place, and arithmetic identical to vanilla
everywhere at or above 32.

They do NOT prove it draws correctly. Only a live look does that.
"""
import unittest

from .. import disc


def _w(payload: bytes, i: int = 0) -> int:
    """Instruction word `i` of a little-endian payload."""
    return int.from_bytes(payload[i * 4:i * 4 + 4], "little")


def _jump_target(word: int, pc: int) -> int:
    """Where a `j` at `pc` actually lands."""
    assert word >> 26 == 0x02, f"{word:08X} is not a `j`"
    return (pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def vanilla_index(gauge: int) -> int:
    """The frame index the unpatched game computes."""
    x = gauge - 32
    half = -((-x) // 2) if x < 0 else x // 2      # rounds toward zero
    return min(half + 0x88, 0x98)


def patched_index(gauge: int) -> int:
    """The frame index with the floor applied."""
    return min((max(gauge - 32, 0) >> 1) + 0x88, 0x98)


class TestWhenItApplies(unittest.TestCase):
    def test_a_vanilla_start_gets_no_edit_at_all(self) -> None:
        # The disc must stay byte-identical for everyone who did not ask for
        # a low starting life.
        self.assertEqual(disc.life_bar_edits(32), [])

    def test_a_start_above_vanilla_gets_no_edit(self) -> None:
        for value in (33, 64, 100, 127):
            self.assertEqual(disc.life_bar_edits(value), [], value)

    def test_a_low_start_gets_the_hook(self) -> None:
        for value in (1, 8, 16, 31):
            self.assertTrue(disc.life_bar_edits(value), value)

    def test_the_gauge_can_never_fall_below_the_start(self) -> None:
        # Which is why 32 is the right threshold: upgrades only ADD, so a seed
        # starting at 32 never reaches the broken range and needs no edit.
        self.assertEqual(disc.life_bar_edits(32), [])
        self.assertNotEqual(disc.life_bar_edits(31), [])


class TestTheEdits(unittest.TestCase):
    def setUp(self) -> None:
        self.edits = disc.life_bar_edits(8)

    def test_there_is_one_jump_and_one_hook_per_site(self) -> None:
        self.assertEqual(len(self.edits), 2 * len(disc.LIFE_BAR_SITES))

    def test_each_site_replaces_the_expected_instruction(self) -> None:
        # `addiu v0, v0, -32`. If a site ever holds something else, the whole
        # hook is built on a wrong assumption - apply_basepatch refuses it,
        # but catching it here is cheaper.
        by_site = {w: van for _l, w, _r, van, _p in self.edits}
        for _label, site, _ret in disc.LIFE_BAR_SITES:
            self.assertEqual(_w(by_site[site]), disc.LIFE_BAR_VANILLA_SUB,
                             f"0x{site:08X}")

    def test_each_site_is_patched_with_a_jump_to_its_own_hook(self) -> None:
        patched = {w: p for _l, w, _r, _v, p in self.edits}
        hooks = [w for _l, w, _r, van, _p in self.edits if van == bytes(24)]
        self.assertEqual(len(hooks), len(disc.LIFE_BAR_SITES))
        for (_label, site, _ret), hook in zip(disc.LIFE_BAR_SITES, hooks):
            self.assertEqual(_jump_target(_w(patched[site]), site), hook,
                             f"0x{site:08X} does not jump to its hook")

    def test_each_hook_jumps_back_to_its_own_return(self) -> None:
        bodies = {w: p for _l, w, _r, van, p in self.edits if van == bytes(24)}
        for (_label, _site, ret), (hook, body) in zip(disc.LIFE_BAR_SITES,
                                                      sorted(bodies.items())):
            self.assertEqual(_jump_target(_w(body, 4), hook + 16), ret,
                             f"hook 0x{hook:08X} returns to the wrong place")

    def test_the_hook_expects_free_space(self) -> None:
        # Declared vanilla of all zeros is what makes apply_basepatch refuse
        # to write the hook over anything that is not actually free.
        for _label, _w_, _r, van, patched in self.edits:
            if len(van) > 4:
                self.assertEqual(van, bytes(len(van)))
                self.assertEqual(len(patched), len(van))

    def test_the_hooks_do_not_overlap_each_other(self) -> None:
        spans = [range(w, w + len(p))
                 for _l, w, _r, van, p in self.edits if van == bytes(24)]
        for i, a in enumerate(spans):
            for b in spans[i + 1:]:
                self.assertFalse(set(a) & set(b))

    def test_it_overlaps_no_other_edit(self) -> None:
        mine = set()
        for _l, where, region, van, _p in self.edits:
            mine |= {disc.addr_to_disc(where + i, region)
                     for i in range(len(van))}
        others = list(disc.A1_EDITS)
        for group in disc.QOL_EDITS.values():
            others += group
        others += disc.starting_life_edits(8)
        for _l, where, region, van, _p in others:
            for i in range(len(van)):
                self.assertNotIn(disc.addr_to_disc(where + i, region), mine)

    def test_the_hook_stays_inside_the_known_free_run(self) -> None:
        # The zero run measured on our dump is 418 bytes from 0x8007699A.
        end = max(w + len(p)
                  for _l, w, _r, van, p in self.edits if van == bytes(24))
        self.assertGreaterEqual(disc.LIFE_BAR_HOOK, 0x8007699A)
        self.assertLessEqual(end, 0x8007699A + 418)


class TestTheArithmetic(unittest.TestCase):
    """The hook must be a NO-OP at and above 32, and a floor below it."""

    def test_it_is_identical_to_vanilla_from_32_up(self) -> None:
        for gauge in range(32, 128):
            self.assertEqual(patched_index(gauge), vanilla_index(gauge), gauge)

    def test_everything_below_32_floors_on_the_shortest_frame(self) -> None:
        for gauge in range(1, 32):
            self.assertEqual(patched_index(gauge), 0x88, gauge)

    def test_vanilla_really_does_go_under_the_artwork(self) -> None:
        # The control. If this passes trivially the fix is fixing nothing.
        # Measured live 2026-09-04: gauge 30 -> 0x87, 16 -> 0x80, 1 -> 0x79.
        self.assertEqual(vanilla_index(30), 0x87)
        self.assertEqual(vanilla_index(16), 0x80)
        self.assertEqual(vanilla_index(1), 0x79)
        self.assertLess(vanilla_index(8), 0x88)

    def test_the_top_clamp_is_untouched(self) -> None:
        # Above 64 the bar is meant to overflow its frame - that is accepted
        # behaviour, not a fault, and this fix must not quietly change it.
        for gauge in (64, 65, 100, 127):
            self.assertEqual(patched_index(gauge), 0x98, gauge)


if __name__ == "__main__":
    unittest.main()
