"""Boss HP randomization tests.

X6 keeps a boss's drawn life bar and its real HP in the SAME byte, written at
boss init from an immediate in overlay code. That is the whole reason this is
a disc patch rather than the client-side write X5 uses, and it is why the
range matters: the bar is drawn from fixed pieces that stop at 32 and its
container caps at 127, so a value outside that misdraws.

Every offset in the table was byte-verified against a real disc. What these
tests protect is the arithmetic around them - the clamp, the rank scaling
that a naive per-level roll would silently invert, and the INSTRUCTION SHAPE
that byte-equality alone cannot see (see TestSiteShape).
"""
import unittest

from .. import disc


def _imm(payload: bytes) -> int:
    """The immediate field of a four-byte little-endian MIPS word."""
    return int.from_bytes(payload, "little") & 0xFFFF


def _fields(payload: bytes) -> tuple[int, int, int, int]:
    """(opcode, rs, rt, immediate) of a four-byte little-endian MIPS word."""
    w = int.from_bytes(payload, "little")
    return w >> 26, (w >> 21) & 0x1F, (w >> 16) & 0x1F, w & 0xFFFF


class TestRange(unittest.TestCase):
    def test_the_bounds_are_the_ones_the_bar_can_draw(self) -> None:
        self.assertEqual((disc.BOSS_HP_MIN, disc.BOSS_HP_MAX), (0x20, 0x7F))

    def test_every_roll_lands_inside_the_bounds(self) -> None:
        # Including rolls at the extremes, where a preserved rank increment
        # would otherwise push a higher level past the cap.
        for roll in (disc.BOSS_HP_MIN, 64, disc.BOSS_HP_MAX):
            rolls = {boss: roll for boss in disc.BOSS_HP}
            for label, _w, _r, _van, patched in disc.boss_hp_edits(rolls):
                self.assertGreaterEqual(_imm(patched), disc.BOSS_HP_MIN, label)
                self.assertLessEqual(_imm(patched), disc.BOSS_HP_MAX, label)


class TestRankScaling(unittest.TestCase):
    def test_higher_ranks_keep_their_vanilla_increment(self) -> None:
        # Heatnix is the one boss in the table with more than one level:
        # 48 / 52 / 56 in vanilla, so +4 and +8 over level 1.
        edits = {label: _imm(patched)
                 for label, _w, _r, _v, patched
                 in disc.boss_hp_edits({"Blaze Heatnix": 100})}
        self.assertEqual(edits["Blaze Heatnix L1 HP"], 100)
        self.assertEqual(edits["Blaze Heatnix L3 HP"], 104)
        self.assertEqual(edits["Blaze Heatnix L4 HP"], 108)

    def test_a_high_roll_never_inverts_the_scaling(self) -> None:
        # Rolling each level independently would let level 3 come out below
        # level 1. Clamped at the cap they may become EQUAL, but never lower.
        for roll in range(disc.BOSS_HP_MIN, disc.BOSS_HP_MAX + 1, 7):
            by_level = {}
            for label, _w, _r, _v, patched in disc.boss_hp_edits(
                    {"Blaze Heatnix": roll}):
                by_level[label] = _imm(patched)
            self.assertLessEqual(by_level["Blaze Heatnix L1 HP"],
                                 by_level["Blaze Heatnix L3 HP"], roll)
            self.assertLessEqual(by_level["Blaze Heatnix L3 HP"],
                                 by_level["Blaze Heatnix L4 HP"], roll)


class TestEdits(unittest.TestCase):
    def test_unrolled_bosses_are_left_alone(self) -> None:
        # A boss missing from the roll must produce NO edit, not an edit to
        # its vanilla value - the latter would collide with nothing today but
        # would make "did this seed change X?" unanswerable from the patch.
        self.assertEqual(disc.boss_hp_edits({}), [])
        only = disc.boss_hp_edits({"Sigma": 64})
        self.assertTrue(all(label.startswith("Sigma ") for label, *_ in only))

    def test_every_edit_declares_a_whole_expected_instruction(self) -> None:
        # apply_basepatch verifies these as strictly as A1, which is what
        # stops a roll built for one dump corrupting another. Four bytes, not
        # one: the immediate on its own cannot distinguish a load of a
        # constant from an add onto a runtime value, and eight sites are the
        # latter.
        rolls = {boss: 64 for boss in disc.BOSS_HP}
        for label, _w, _r, van, patched in disc.boss_hp_edits(rolls):
            self.assertEqual(len(van), 4, label)
            self.assertEqual(len(patched), 4, label)

    def test_the_declared_vanilla_matches_the_table(self) -> None:
        rolls = {boss: 64 for boss in disc.BOSS_HP}
        declared = {}
        for label, where, _r, van, _p in disc.boss_hp_edits(rolls):
            declared[where] = _imm(van)
        for boss, levels in disc.BOSS_HP.items():
            if boss in disc.BOSS_HP_NEVER_ROLLED:
                continue        # emits no edits at all, by design
            for _level, vanilla, offsets in levels:
                for offset in offsets:
                    self.assertEqual(declared[offset], vanilla)

    def test_no_two_bosses_share_an_offset(self) -> None:
        # Two edits writing one offset makes the result order-dependent, and
        # apply_basepatch refuses it outright - better to catch it here.
        seen = set()
        for _boss, levels in disc.BOSS_HP.items():
            for _level, _vanilla, offsets in levels:
                for offset in offsets:
                    self.assertNotIn(offset, seen)
                    seen.add(offset)

    def test_the_x_and_zero_copies_get_the_same_value(self) -> None:
        # Most bosses appear twice, at a fixed 0xBDA0 stride - the X and Zero
        # overlay copies. Giving them different HP would mean the two
        # characters fight measurably different bosses.
        rolls = {boss: 71 for boss in disc.BOSS_HP}
        by_label: dict[str, set[int]] = {}
        for label, _w, _r, _v, patched in disc.boss_hp_edits(rolls):
            by_label.setdefault(label, set()).add(_imm(patched))
        for label, values in by_label.items():
            self.assertEqual(len(values), 1, f"{label} got {values}")


class TestSiteShape(unittest.TestCase):
    """The check that byte-equality could never be.

    Twice now a BOSS_HP row has held a byte that equalled the vanilla HP and
    was not a load of it: the retired counter site 0x0591E8 in 0.1.0, and the
    eight `addiu v0, v0, N` sites that wrapped Infinity Mijinion's HP negative
    in 0.3.0. Both passed the only check there was, "the byte here equals the
    vanilla value", which cannot fail for ANY byte holding the right number.

    These tests read the OPCODE and the REGISTERS instead, on both sides of
    the edit. The one that matters most is
    `test_every_patched_site_is_a_plain_load`: whatever a site started as, what
    we write must be `addiu rt, zero, value`, so the byte reaching the life
    gauge is exactly the clamped roll and nothing can be added to it later.
    """

    # The eight sites that are an ADD onto a per-level bonus rather than a
    # load. Pinned by offset so that dropping the fix, or a new row arriving
    # with the same encoding unnoticed, is a test failure and not a playtest
    # report. See BOSS_HP_WORDS in disc.py.
    ADD_SITES = {
        0x03C36C, 0x153724,     # Blizzard Wolfang
        0x061DDC, 0x15F0EC,     # Metal Shark Player
        0x08E8C8, 0x16D4D0,     # Shield Sheldon
        0x0A2F28, 0x173CB4,     # Infinity Mijinion
    }

    def _offsets(self) -> list[int]:
        return [off for _b, levels in disc.BOSS_HP.items()
                for _l, _v, offsets in levels for off in offsets]

    def test_every_site_declares_its_whole_instruction(self) -> None:
        # An offset with no word, or a word with no offset, means the two
        # tables have drifted and one of them is describing a site that is
        # not there.
        self.assertEqual(sorted(self._offsets()),
                         sorted(disc.BOSS_HP_WORDS))

    def test_every_declared_word_is_addiu_of_the_vanilla_hp(self) -> None:
        for boss, levels in disc.BOSS_HP.items():
            for level, vanilla, offsets in levels:
                for off in offsets:
                    word = disc.BOSS_HP_WORDS[off]
                    where = f"{boss} L{level} @ 0x{off:06X}"
                    self.assertEqual(word >> 26, disc.BOSS_HP_ADDIU, where)
                    self.assertEqual(word & 0xFFFF, vanilla, where)

    def test_the_add_sites_are_exactly_the_ones_we_know_about(self) -> None:
        # Derived from the declared words, then compared against the pinned
        # list - so a NEW site with a live source register fails here rather
        # than shipping.
        adds = {off for off, w in disc.BOSS_HP_WORDS.items()
                if (w >> 21) & 0x1F != 0}
        self.assertEqual(adds, self.ADD_SITES)

    def test_every_patched_site_is_a_plain_load(self) -> None:
        # THE assertion. rs == 0 is what makes the stored byte exactly the
        # rolled value, which is what makes the clamp to 32..127 true.
        for roll in (disc.BOSS_HP_MIN, 100, disc.BOSS_HP_MAX):
            rolls = {boss: roll for boss in disc.BOSS_HP}
            for label, where, _r, van, patched in disc.boss_hp_edits(rolls):
                v_op, _v_rs, v_rt, _v_imm = _fields(van)
                p_op, p_rs, p_rt, p_imm = _fields(patched)
                self.assertEqual(p_op, disc.BOSS_HP_ADDIU, label)
                self.assertEqual(p_rs, 0, f"{label}: source register not zero")
                self.assertEqual(p_rt, v_rt, f"{label}: destination changed")
                self.assertEqual(p_op, v_op, f"{label}: opcode changed")
                self.assertGreaterEqual(p_imm, disc.BOSS_HP_MIN, label)
                self.assertLessEqual(p_imm, disc.BOSS_HP_MAX, label)

    def test_an_add_site_would_be_caught_if_the_fix_were_removed(self) -> None:
        # A control: the helper is what clears the register, so feeding it an
        # untouched ADD word must change the word. If this passes trivially,
        # the assertion above is checking nothing.
        for off in sorted(self.ADD_SITES):
            word = disc.BOSS_HP_WORDS[off]
            self.assertNotEqual((word >> 21) & 0x1F, 0)
            self.assertEqual((disc.boss_hp_load(word, 64) >> 21) & 0x1F, 0)
            self.assertNotEqual(disc.boss_hp_load(word, word & 0xFFFF), word,
                                f"0x{off:06X}: the fix is a no-op here")

    def test_a_load_site_keeps_its_encoding(self) -> None:
        # The other twenty must come out byte-identical when the roll happens
        # to equal vanilla - the fix must not disturb sites that were correct.
        for off, word in disc.BOSS_HP_WORDS.items():
            if off in self.ADD_SITES:
                continue
            self.assertEqual(disc.boss_hp_load(word, word & 0xFFFF), word,
                             f"0x{off:06X}")

    def test_no_edit_straddles_a_sector_payload_boundary(self) -> None:
        # apply_basepatch verifies a declared vanilla as a CONTIGUOUS slice of
        # the image, which is only the instruction if all four bytes live in
        # one sector's 2048-byte payload. One-byte edits could never trip
        # this; four-byte ones can.
        for off in self._offsets():
            self.assertLessEqual(off % disc.USER_LEN, disc.USER_LEN - 4,
                                 f"0x{off:06X} straddles a sector edge")
            self.assertEqual(off % 4, 0, f"0x{off:06X} is not word-aligned")


class TestTutorialBossIsNeverRolled(unittest.TestCase):
    """The intro boss keeps vanilla health however the option is set.

    A real playtest rolled it 32 -> 110: three and a half times vanilla, on the
    tutorial, fought with a bare starting X. It is the first thing any player
    of this world meets.
    """

    def test_it_is_excluded(self) -> None:
        self.assertIn("D-1000", disc.BOSS_HP_NEVER_ROLLED)
        self.assertNotIn("D-1000", disc.rollable_bosses())

    def test_the_exclusion_list_names_real_bosses(self) -> None:
        for boss in disc.BOSS_HP_NEVER_ROLLED:
            self.assertIn(boss, disc.BOSS_HP,
                          f"{boss} is excluded but is not in the table at all")

    def test_rollable_is_everything_else(self) -> None:
        self.assertEqual(
            set(disc.rollable_bosses()),
            set(disc.BOSS_HP) - set(disc.BOSS_HP_NEVER_ROLLED))

    def test_no_edit_is_emitted_even_if_a_roll_is_forced(self) -> None:
        # A caller passing a stale roll dict must not be able to reintroduce
        # it - the builder refuses, not just the roller.
        self.assertEqual(disc.boss_hp_edits({"D-1000": 120}), [])

    def test_excluding_it_does_not_disturb_the_others(self) -> None:
        rolls = {b: 64 for b in disc.rollable_bosses()}
        edits = disc.boss_hp_edits(rolls)
        self.assertTrue(edits)
        self.assertFalse([e for e in edits if e[0].startswith("D-1000")])


if __name__ == "__main__":
    unittest.main()
