"""Reploid protection tests - ship plan A2, option (1).

X6 destroys Reploids permanently. A Nightmare carries one off, or it dies in
the crossfire, and its nibble records 3 (death) or 4 (missing) - states that
never clear. With 128 Reploids as the largest check source in the game, that
is items vanishing from a multiworld.

The plan recommended "(1) patch them non-destroyable PLUS (2) fire the check
on any state change - belt and braces". Only (2) ever shipped. This is (1).

Three `addiu a1, zero, N` become `ori a1, zero, 0`, so every routine that
would record a Reploid as lost records it as untouched and the Reploid
reappears. The rescue site is deliberately untouched.

What these pin is mostly the ways it could go wrong quietly:

  * patching the RESCUE site as well, which would stop rescues recording and
    silently destroy the 128 checks this exists to protect;
  * the disc patch and the client's state constants drifting apart, so the
    patch writes a value the client does not read as "untouched";
  * (1) being read as a replacement for (2) rather than an addition.
"""
import struct
import unittest

from .. import disc, reploids
from ..Rom import QOL_OPTIONS
from ..options import MMX6Options

GROUP = "protect_reploids"
RESCUE_SITE = 0x8004EF44          # `addiu a1, zero, 2` - must NOT be patched


def word(payload: bytes) -> int:
    return struct.unpack("<I", payload)[0]


def immediate(payload: bytes) -> int:
    """The 16-bit immediate an addiu/ori encodes."""
    return word(payload) & 0xFFFF


class TestTheEdits(unittest.TestCase):
    def setUp(self) -> None:
        self.edits = disc.QOL_EDITS[GROUP]

    def test_there_are_exactly_three(self) -> None:
        # Nightmare, killed by player, offscreen. A fourth would mean someone
        # added the rescue site.
        self.assertEqual(len(self.edits), 3)

    def test_every_vanilla_writes_a_state_the_client_calls_LOST(self) -> None:
        # THE DRIFT GUARD, and the reason reploids.LOST_STATES exists. If the
        # state numbering is ever revised, the disc patch and the client must
        # not disagree about which values mean "gone".
        for label, _where, _region, van, _patched in self.edits:
            self.assertIn(immediate(van), reploids.LOST_STATES,
                          f"{label} does not write a lost state")

    def test_both_lost_states_are_covered(self) -> None:
        # Patching only DEAD or only MISSING would leave half the problem.
        written = {immediate(van) for _l, _w, _r, van, _p in self.edits}
        self.assertEqual(written, set(reploids.LOST_STATES))

    def test_every_patch_writes_the_untouched_state(self) -> None:
        for label, _where, _region, _van, patched in self.edits:
            self.assertEqual(immediate(patched), reploids.NOT_RESCUED,
                             f"{label} does not reset to untouched")

    def test_the_rescue_site_is_not_touched(self) -> None:
        # THE EXPENSIVE MISTAKE. 0x8004EF44 writes 2 = RESCUED, which is what
        # the client's Reploid checks read. Patching it to 0 would stop every
        # rescue recording and destroy the 128 checks outright - and the seed
        # would still generate, and the disc would still boot.
        for _label, where, _region, _van, _patched in self.edits:
            self.assertNotEqual(where, RESCUE_SITE)

    def test_no_two_edits_write_the_same_address(self) -> None:
        wheres = [w for _l, w, _r, _v, _p in self.edits]
        self.assertEqual(len(set(wheres)), len(wheres))

    def test_every_edit_is_one_instruction_in_the_static_exe(self) -> None:
        for label, where, region, van, patched in self.edits:
            self.assertEqual(region, disc.REGION_EXE, label)
            self.assertEqual(len(van), 4, label)
            self.assertEqual(len(patched), 4, label)
            # Inside the EXE text, or addr_to_disc would refuse it.
            disc.addr_to_disc(where, region)


class TestItIsWiredUp(unittest.TestCase):
    def test_the_option_exists_and_maps_to_the_group(self) -> None:
        self.assertIn("protect_reploids", QOL_OPTIONS)
        self.assertEqual(QOL_OPTIONS["protect_reploids"], GROUP)
        self.assertIn("protect_reploids", MMX6Options.type_hints)

    def test_it_is_on_by_default(self) -> None:
        self.assertTrue(MMX6Options.type_hints["protect_reploids"].default)

    def test_qol_edits_returns_it_only_when_asked(self) -> None:
        self.assertEqual(disc.qol_edits([GROUP]), disc.QOL_EDITS[GROUP])
        self.assertEqual(
            [e for e in disc.qol_edits(["text_skip"])
             if e in disc.QOL_EDITS[GROUP]], [])


class TestTheFallbackIsStillThere(unittest.TestCase):
    """(1) is belt AND braces, not a replacement for (2)."""

    def test_a_lost_state_is_still_not_the_untouched_state(self) -> None:
        # The client sends a check for any nibble != NOT_RESCUED. If a lost
        # state ever became 0, protection would be the only thing standing
        # between a destroyed Reploid and a lost check.
        for state in reploids.LOST_STATES:
            self.assertNotEqual(state, reploids.NOT_RESCUED)

    def test_rescued_is_distinct_from_every_lost_state(self) -> None:
        self.assertNotIn(reploids.RESCUED, reploids.LOST_STATES)


if __name__ == "__main__":
    unittest.main()
