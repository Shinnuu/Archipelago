"""The patch's hand-written routines, EXECUTED - not just assembled.

X5's routines cost live sessions each time one was only read: a register
typo, then a load read one instruction too early. Here each routine runs on
test.r3000 (branch and load delay slots modelled) against the game state it
meets at its hook, and its effect is checked.
"""
import unittest

from .. import disc, mips
from .r3000 import R3000

AT = disc.routine_addresses()
STRUCT = 0x80100000            # stands in for the card menu's state struct


def machine() -> R3000:
    m = R3000()
    for name, source in disc.ROUTINES:
        m.load_code(AT[name], mips.assemble(source, AT[name]))
    return m


def set_ap(m: R3000, stamp: int, lab: int, rush: int, processed: int = 0) -> None:
    m.write(disc.AP_STAMP, stamp, 4)
    m.write(disc.AP_LAB, lab, 4)
    m.write(disc.AP_RUSH, rush, 4)
    m.write(disc.AP_PROCESSED, processed, 4)


def ext(m: R3000, offset: int, slot: int) -> tuple[int, ...]:
    base = disc.CARD_BUFFER + offset + disc.EXT_SIZE * slot
    return tuple(m.read(base + 4 * i, 4) for i in range(disc.EXT_SIZE // 4))


def put_ext(m: R3000, offset: int, slot: int, stamp: int, lab: int, rush: int,
            processed: int = 0, check=None) -> None:
    base = disc.CARD_BUFFER + offset + disc.EXT_SIZE * slot
    if check is None:
        check = disc.ext_check(stamp, lab, rush, processed)
    for i, v in enumerate((stamp, lab, rush, processed, 0, check)):
        m.write(base + 4 * i, v, 4)


class TestSaveExtension(unittest.TestCase):
    STAMP = 0x1234ABCD

    def write(self, slot: int, lab: int, rush: int, processed: int = 0) -> R3000:
        """Run the write routine as the card write state meets it: s1 = the
        menu struct (slot at +0xA), s2 already moved on by the delay slot."""
        m = machine()
        set_ap(m, self.STAMP, lab, rush, processed)
        m.write(STRUCT + 0xA, slot, 1)
        m.r[17] = STRUCT                  # s1
        m.r[18] = 0x80160000              # s2 after `lui s2, 0x8016`
        m.run(AT["P11 save extension: write"])
        return m

    def load(self, m: R3000, slot: int) -> R3000:
        m.write(STRUCT + 0xA, slot, 1)
        m.r[16] = STRUCT                  # s0
        m.r[18] = disc.CARD_BUFFER        # s2
        m.run(AT["P11 save extension: load"])
        return m

    def test_write_fills_main_and_backup_for_that_slot_only(self):
        m = self.write(slot=1, lab=0x0002_0006, rush=0x0100_0001, processed=17)
        want = (self.STAMP, 0x0002_0006, 0x0100_0001, 17, 0,
                disc.ext_check(self.STAMP, 0x0002_0006, 0x0100_0001, 17))
        self.assertEqual(ext(m, disc.EXT_MAIN, 1), want)
        self.assertEqual(ext(m, disc.EXT_BACKUP, 1), want)
        for slot in (0, 2):
            self.assertEqual(ext(m, disc.EXT_MAIN, slot), (0,) * 6)
            self.assertEqual(ext(m, disc.EXT_BACKUP, slot), (0,) * 6)
        # Nothing strays outside the file's spare tail.
        touched = [a for a in m.mem if disc.CARD_BUFFER <= a < disc.CARD_BUFFER + 0x400]
        self.assertTrue(all(disc.EXT_MAIN <= a - disc.CARD_BUFFER < 0x400 for a in touched))
        self.assertEqual(m.r[16], 3, "the retry count the hook displaced")

    def test_write_then_load_round_trips(self):
        m = self.write(slot=2, lab=0x3FFFE, rush=0x01010101, processed=42)
        set_ap(m, self.STAMP, 0, 0, 0)    # a power-cycle: the RAM block is empty again
        self.load(m, slot=2)
        self.assertEqual(m.read(disc.AP_LAB, 4), 0x3FFFE)
        self.assertEqual(m.read(disc.AP_RUSH, 4), 0x01010101)
        self.assertEqual(m.read(disc.AP_PROCESSED, 4), 42)
        self.assertEqual((m.r[2], m.read(STRUCT + 7, 1)), (1, 1), "the displaced `sb v0, 7(s0)`")

    def test_load_merges_checks_but_restores_the_processed_count(self):
        """Lab and Rush checks only ever accumulate; the processed count
        follows the save, because loading an older save rewinds the lives
        and energy it counts (X5's rule)."""
        m = machine()
        set_ap(m, self.STAMP, 0b1000, 0x00000100, processed=30)
        put_ext(m, disc.EXT_MAIN, 0, self.STAMP, 0b0110, 0x00000001, processed=12)
        self.load(m, slot=0)
        self.assertEqual(m.read(disc.AP_LAB, 4), 0b1110)
        self.assertEqual(m.read(disc.AP_RUSH, 4), 0x00000101)
        self.assertEqual(m.read(disc.AP_PROCESSED, 4), 12)

    def test_load_falls_back_to_the_backup(self):
        m = machine()
        set_ap(m, self.STAMP, 0, 0)
        put_ext(m, disc.EXT_MAIN, 1, self.STAMP, 0b10, 0, 3, check=0xBAD)
        put_ext(m, disc.EXT_BACKUP, 1, self.STAMP, 0b100, 0x01000000, 7)
        self.load(m, slot=1)
        self.assertEqual(m.read(disc.AP_LAB, 4), 0b100)
        self.assertEqual(m.read(disc.AP_RUSH, 4), 0x01000000)
        self.assertEqual(m.read(disc.AP_PROCESSED, 4), 7)

    def test_load_ignores_other_seeds_vanilla_saves_and_new_files(self):
        """The control for the stamp: nothing from a foreign or empty
        extension may reach the AP block."""
        for stamp_on_card in (0x0BADF00D, 0):      # another seed; a vanilla/new file
            m = machine()
            set_ap(m, self.STAMP, 0b1, 0, processed=5)
            put_ext(m, disc.EXT_MAIN, 0, stamp_on_card, 0x3FFFE, 0x01010101, 99)
            put_ext(m, disc.EXT_BACKUP, 0, stamp_on_card, 0x3FFFE, 0x01010101, 99)
            self.load(m, slot=0)
            self.assertEqual(m.read(disc.AP_LAB, 4), 0b1, hex(stamp_on_card))
            self.assertEqual(m.read(disc.AP_RUSH, 4), 0, hex(stamp_on_card))
            self.assertEqual(m.read(disc.AP_PROCESSED, 4), 5, hex(stamp_on_card))
            self.assertEqual(m.read(STRUCT + 7, 1), 1)

    def test_routines_fit_the_cave(self):
        end = max(AT[n] + 4 * len(mips.assemble(s, AT[n])) for n, s in disc.ROUTINES)
        self.assertLessEqual(end, disc.CAVE_END)
        self.assertGreaterEqual(min(AT.values()), disc.CAVE_START)


def in_place(name: str) -> tuple[int, list[int]]:
    for n, where, source, _vanilla in disc.IN_PLACE:
        if n == name:
            return where, mips.assemble(source, where)
    raise KeyError(name)


# The commit as the patched disc has it: its vanilla head (a0 = the mirror),
# the P6 rewrite, and its vanilla Rush copy (0x80101754..0x80101798), read off
# the disc 2026-09-24.
COMMIT_HEAD = [0x3C04801C, 0x24843340]
COMMIT_RUSH_COPY = [0x3C028017, 0x9042D300, 0x3C038017, 0x9063D301, 0x3C048017, 0x9084D302,
                    0x3C058017, 0x90A5D303, 0x3C01801C, 0xA0223352, 0x3C01801C, 0xA0233353,
                    0x3C01801C, 0xA0243354, 0x3C01801C, 0xA0253355, 0x03E00008, 0x00000000]
MIRROR = 0x801C3340


def with_commit(m: R3000) -> R3000:
    m.load_code(0x80101700, COMMIT_HEAD)
    where, words = in_place("P6 commit: effects from AP_PARTS")
    m.load_code(where, words)
    m.load_code(0x80101754, COMMIT_RUSH_COPY)
    return m


class TestLab(unittest.TestCase):
    def test_the_search_answers_bought_or_not(self):
        where, words = in_place("P5 Lab search: bought?")
        for bought, index, want in ((0b100, 1, 0xFFFFFFFF), (0b100, 2, 0), (0, 1, 0),
                                    (1 << 17, 16, 0xFFFFFFFF)):
            m = R3000()
            m.load_code(where, words)
            m.write(disc.AP_LAB, bought, 4)
            m.r[4] = index                      # a0 = part index (id - 1)
            m.run(where)
            self.assertEqual(m.r[2], want, (bin(bought), index))

    def test_a_purchase_records_equips_nothing_and_commits(self):
        """P5_BUY from the purchase hook: v1 = part id, ra = 0x8011EBE0. It
        sets the bit, stores nothing to any slot, and the commit still runs
        and returns to the caller."""
        m = with_commit(machine())
        m.write(disc.AP_LAB, 1 << 3, 4)
        m.write(disc.AP_PARTS, 1 << 7, 4)
        m.write(0x8016D300, 0x00010001, 4)       # live Rush
        m.r[3] = 11                             # v1 = Laser Shot
        m.r[31] = R3000.RETURN                  # stands in for 0x8011EBE0
        m.run(AT["P5 Lab purchase"])
        self.assertEqual(m.read(disc.AP_LAB, 4), (1 << 3) | (1 << 11))
        self.assertEqual(m.read(0x8016D2F2, 8), 0, "no slot equipped")
        self.assertEqual(m.read(MIRROR + 7, 1), 1, "the commit ran: effects from AP_PARTS")
        self.assertEqual(m.read(MIRROR + 11, 1), 0, "a purchase is a check, not the part")
        self.assertEqual(m.read(0x801C3352, 4), 0x00010001, "and copied Rush as always")

    def test_the_commit_builds_every_effect_from_ap_parts(self):
        m = with_commit(R3000())
        parts = sum(1 << i for i in (1, 2, 8, 11, 12, 13, 17))
        m.write(disc.AP_PARTS, parts, 4)
        for i in range(24):
            m.write(MIRROR + i, 0xAA, 1)        # stale flags: all must be rebuilt
        m.write(0x8016D2F2, 0x0F0F0F0F0F0F0F0F, 8)   # slots: must not matter
        m.run(0x80101700)
        for i in range(0x12):
            self.assertEqual(m.read(MIRROR + i, 1), (parts >> i) & 1, i)
        self.assertEqual(m.read(0x801C3352, 4), 0, "persistent Rush = live (0)")
        self.assertEqual(m.read(MIRROR + 0x16, 2), 0)

    def test_the_shot_icons_show_exactly_the_owned_shot_parts(self):
        where, words = in_place("P6 pause shot icons")
        for k, owned in ((1, True), (2, False), (3, True)):
            m = R3000()
            m.load_code(where, words)
            m.load_code(0x80114418, [mips.word("jr ra", 0x80114418), 0])   # stop at the beq
            m.write(MIRROR + 10 + k, 1 if owned else 0, 1)
            m.r[2] = k                          # v0 = the icon's shot type
            m.run(where)
            self.assertEqual((m.r[5], m.r[2]), (0 if owned else 8, 8), k)


class TestTheInterpreterModelsTheDelaySlots(unittest.TestCase):
    """The control for every routine test above: the interpreter must show
    a hazard the way the console would, or passing tests prove nothing."""

    def test_a_load_lands_one_instruction_late(self):
        m = R3000()
        m.write(0x80001000, 0x55, 4)
        m.r[8], m.r[9] = 0x11, 0x80001000                     # t0 old, t1 = &value
        m.load_code(0x80000000, [
            mips.word("lw t0, 0(t1)", 0x80000000),
            mips.word("addu t2, t0, zero", 0x80000004),       # the hazard: sees the OLD t0
            mips.word("addu t3, t0, zero", 0x80000008),       # sees the loaded t0
            mips.word("jr ra", 0x8000000C), 0])
        m.run(0x80000000)
        self.assertEqual((m.r[10], m.r[11]), (0x11, 0x55))

    def test_the_branch_delay_slot_always_runs(self):
        m = R3000()
        m.load_code(0x80000000, mips.assemble(
            "b out\nori t0, zero, 7\nori t0, zero, 9\nout: jr ra\nnop", 0x80000000))
        m.run(0x80000000)
        self.assertEqual(m.r[8], 7)


class TestAssembler(unittest.TestCase):
    def test_encodings_match_words_read_off_the_disc(self):
        for text, pc, want in [
            ("lbu v0, 0x1EAC(at)", 0, 0x90221EAC), ("sb zero, -1(v1)", 0, 0xA060FFFF),
            ("lui v0, 0x8017", 0, 0x3C028017), ("jal 0x80120dc0", 0x8011FAA0, 0x0C048370),
            ("jr ra", 0, 0x03E00008), ("addiu sp, sp, -0x28", 0, 0x27BDFFD8),
            ("sw ra, 0x20(sp)", 0, 0xAFBF0020), ("lb v0, 0xa(s1)", 0, 0x8222000A),
            ("sll v1, v0, 1", 0, 0x00021840), ("addu v1, v1, s2", 0, 0x00721821),
            ("ori s0, zero, 3", 0, 0x34100003), ("bne v1, v0, 0x8011FC50", 0x8011FC78, 0x1462FFF5),
        ]:
            self.assertEqual(mips.word(text, pc or 0x80000000), want, text)

    def test_hazards_are_refused(self):
        for bad in ("lw t0, 0(t1)\naddu t2, t0, t1\nnop",        # load delay
                    "lbu t0, 0(t1)\nsb t0, 0(t2)\nnop",           # the X5 v3-v6 bug
                    "beq t0, t1, x\nx: j 0x80000000\nnop",        # transfer in a delay slot
                    "nop\njr ra",                                 # no delay slot at the end
                    # a load in a branch's delay slot, read at the target
                    "beqz a0, out\nlbu t0, 0(a1)\nnop\nout: addu v0, t0, zero\njr ra\nnop"):
            with self.assertRaises(ValueError, msg=bad):
                mips.assemble(bad, 0x80000000)
        # The control: the same shape reading another register at the target.
        mips.assemble("beqz a0, out\nlbu t0, 0(a1)\nnop\nout: addu v0, t1, zero\njr ra\nnop",
                      0x80000000)

    def test_signed_fields_refuse_what_would_encode_negative(self):
        """0x8000-0xFFFF in a signed field used to encode as negative."""
        for bad in ("lw t0, 0x8000(t1)", "addiu v0, v0, 0xFFFF", "b 0x80030000"):
            with self.assertRaises(ValueError, msg=bad):
                mips.word(bad, 0x80000000)
        # Zero-extended fields take the whole range.
        self.assertEqual(mips.word("ori v0, zero, 0xFFFF", 0x80000000), 0x3402FFFF)
        self.assertEqual(mips.word("andi v0, v0, 0x8000", 0x80000000), 0x30428000)
