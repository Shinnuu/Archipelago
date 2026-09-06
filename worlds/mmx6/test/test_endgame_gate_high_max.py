"""`all_mavericks_high_max_sigma` - Gate's Lab needs all eight AND High Max.

Vanilla's unlock flag `a3` is an OR: it starts as the all-eight test and the
souls and High Max conditions can only ever force it to 1. So no amount of
raising comparison constants - which is how every other gate edit works -
reaches an AND. This is the one gate edit that rewrites instructions, and these
tests are what stands between that and a gate nobody can open.

The record is the game's own latch, `SAVE+0x43B`, which runs 0 -> 1 -> 2. It
read 1 with Zero Nightmare cleared and High Max alive, and went to 2 the moment
High Max died - measured live 2026-09-06, with one Maverick beaten, which is
also the run that proved condition 3 is the High Max route at all. So the patch
keeps condition 3's consume and removes only its power to unlock.
"""
import mmap
import os
import unittest

from .. import disc
from ..options import Goal, MMX6Options
from ..Rom import patch_rom
from . import MMX6TestBase

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)

EDITS = disc.ENDGAME_GATE_HIGH_MAX_EDITS
AND_SITES = {where for _l, where, _r, _v, _p in EDITS}

CONDITION_3_TEST = 0x0D6768      # slti v0, v0, 19 - must stay alive
CONDITION_3_CONSUME = 0x0D6788   # sb v0, 0x43B(a1) - the record itself


class TestTheOption(unittest.TestCase):
    def test_the_goal_exists_and_is_its_own_value(self) -> None:
        self.assertEqual(Goal.option_all_mavericks_high_max_sigma, 2)
        self.assertEqual(Goal.name_lookup[2], "all_mavericks_high_max_sigma")

    def test_it_does_not_disturb_the_other_two(self) -> None:
        # A goal's value rides in slot_data and the client reads it as a
        # number, so renumbering would silently change what old seeds mean.
        self.assertEqual(Goal.option_sigma, 0)
        self.assertEqual(Goal.option_all_mavericks_sigma, 1)

    def test_the_client_constant_agrees(self) -> None:
        from ..client import (GOAL_ALL_MAVERICKS_HIGH_MAX_SIGMA,
                              GOALS_NEEDING_ALL_MAVERICKS)
        self.assertEqual(GOAL_ALL_MAVERICKS_HIGH_MAX_SIGMA,
                         Goal.option_all_mavericks_high_max_sigma)
        # The ending must not count below 8/8 under this goal either.
        self.assertIn(GOAL_ALL_MAVERICKS_HIGH_MAX_SIGMA,
                      GOALS_NEEDING_ALL_MAVERICKS)


class TestTheEditsSayWhatTheyMean(unittest.TestCase):
    """Decode what we wrote, rather than trusting the hex."""

    def _word(self, where: int) -> int:
        for _l, w, _r, _v, pat in EDITS:
            if w == where:
                return int.from_bytes(pat, "little")
        raise AssertionError("no edit at 0x%06X" % where)

    def test_every_payload_is_a_whole_instruction(self) -> None:
        for label, _w, _r, van, pat in EDITS:
            self.assertEqual(len(van), 4, label)
            self.assertEqual(len(pat), 4, label)

    def test_it_recomputes_the_all_eight_test_itself(self) -> None:
        """THE REGRESSION TEST. The first version leaned on vanilla's a3 at
        0x0D671C and only ever cleared it - and ROCK+0x0D6708 branches straight
        to 0x0D6720, skipping that computation. Vanilla survives because
        condition 3 forces a3=1 further down, which is the very force this
        patch removes, so a3 stayed stale and the gate welded shut. Measured
        live: beaten=FF, latch=2, a3 exported as 0.

        Every one of the three instructions has to be here, in this order, or
        that failure comes back."""
        lbu = self._word(0x0D6720)
        self.assertEqual(lbu >> 26, 0x24, "0x0D6720 is not an lbu")
        self.assertEqual(lbu & 0xFFFF, 0x0060, "not reading the beaten field")

        xori = self._word(0x0D6728)
        self.assertEqual(xori >> 26, 0x0E, "0x0D6728 is not an xori")
        self.assertEqual(xori & 0xFFFF, 0x00FF, "not inverting all eight bits")

        sltiu = self._word(0x0D672C)
        self.assertEqual(sltiu >> 26, 0x0B, "0x0D672C is not an sltiu")
        self.assertEqual((sltiu >> 16) & 0x1F, 7, "destination is not a3")
        self.assertEqual(sltiu & 0xFFFF, 1, "not comparing against 1")

    def test_it_loads_the_latch_not_the_souls(self) -> None:
        ins = self._word(0x0D6730)
        self.assertEqual(ins >> 26, 0x24, "not an lbu")
        self.assertEqual(ins & 0xFFFF, disc.ENDGAME_GATE_HIGH_MAX_LATCH)

    def test_it_compares_against_the_beaten_value(self) -> None:
        ins = self._word(0x0D6734)
        self.assertEqual(ins >> 26, 9, "not an addiu")
        self.assertEqual(ins & 0xFFFF, disc.ENDGAME_GATE_HIGH_MAX_BEATEN)

    def test_the_branch_skips_exactly_the_clear(self) -> None:
        # It must land on 0x0D6744, where vanilla reloads v1 with SAVE_BASE -
        # v1 is read at 0x0D6750 and this block clobbers it with 2.
        ins = self._word(0x0D6738)
        self.assertEqual(ins >> 26, 4, "not a beq")
        target = 0x0D6738 + 4 + (ins & 0xFFFF) * 4
        self.assertEqual(target, 0x0D6744, "branch lands in the wrong place")

    def test_the_load_delay_slot_is_respected(self) -> None:
        # R3000: a loaded value is not available to the NEXT instruction. Both
        # loads here are read at least two instructions later. This project has
        # lost three sessions to this hazard on X5.
        # 0x0D6724 is vanilla's own nop and must stay untouched: it is the
        # delay slot for the lbu at 0x0D6720.
        self.assertNotIn(0x0D6724, AND_SITES)
        # latch loaded at 0x0D6730, consumed by the beq at 0x0D6738.
        self.assertEqual((self._word(0x0D6738) >> 21) & 0x1F,
                         (self._word(0x0D6730) >> 16) & 0x1F,
                         "the beq does not read the register the lbu wrote")

    def test_the_not_beaten_path_clears_a3(self) -> None:
        # addu a3, zero, zero. a3 is the unlock flag; clearing it is the AND.
        ins = self._word(0x0D6740)
        self.assertEqual(ins >> 26, 0, "not a SPECIAL")
        self.assertEqual(ins & 0x3F, 0x21, "not an addu")
        self.assertEqual((ins >> 11) & 0x1F, 7, "destination is not a3")
        self.assertEqual((ins >> 21) & 0x1F, 0)
        self.assertEqual((ins >> 16) & 0x1F, 0)

    def test_the_v1_reload_is_left_alone(self) -> None:
        # 0x0D6744 puts SAVE_BASE back in v1, which 0x0D6750 reads. This block
        # clobbers v1 with 2, so patching over that reload would break the
        # cursor test downstream.
        self.assertNotIn(0x0D6744, AND_SITES)

    def test_nothing_can_still_force_a3_to_one(self) -> None:
        # Both `addiu a3, zero, 1` sites must be gone, or the gate opens on
        # souls or on High Max alone and the AND is decorative.
        for site in (0x0D6748, 0x0D6784):
            self.assertEqual(self._word(site), 0, hex(site))


class TestTheRecordSurvives(unittest.TestCase):
    """The patch must not break the thing it depends on."""

    def test_condition_3_is_left_alive(self) -> None:
        # It is what writes the latch to 2. Neutralising it - which is exactly
        # what all_mavericks_sigma does - would leave the latch at 1 forever
        # and the gate could never open.
        self.assertNotIn(CONDITION_3_TEST, AND_SITES)

    def test_the_consume_is_left_alive(self) -> None:
        self.assertNotIn(CONDITION_3_CONSUME, AND_SITES)

    def test_the_other_goal_does_neutralise_condition_3(self) -> None:
        # The control. Without it the test above proves nothing about whether
        # 0x0D6768 is meaningful to anybody.
        other = {w for _l, w, _r, _v, _p in disc.ENDGAME_GATE_EDITS}
        self.assertIn(CONDITION_3_TEST, other)


class TestTheTwoGoalsNeverCollide(unittest.TestCase):
    def test_each_goal_writes_every_offset_at_most_once(self) -> None:
        for high_max in (False, True):
            sites = [w for _l, w, _r, _v, _p
                     in disc.endgame_gate_edits(high_max)]
            self.assertEqual(len(sites), len(set(sites)), str(high_max))

    def test_the_shared_half_is_taken_by_subtraction(self) -> None:
        # So a site added to ENDGAME_GATE_EDITS later is shared by default
        # rather than silently missing from this goal.
        shared = {w for _l, w, _r, _v, _p in disc.ENDGAME_GATE_SHARED_EDITS}
        every = {w for _l, w, _r, _v, _p in disc.ENDGAME_GATE_EDITS}
        self.assertEqual(every - shared, {0x0D6728, 0x0D673C, 0x0D6768})

    def test_the_and_supersedes_the_souls_compares(self) -> None:
        # 0x0D6728 and 0x0D673C are rewritten by the AND, so the shared list
        # must not also carry them - apply_basepatch would refuse the patch.
        shared = {w for _l, w, _r, _v, _p in disc.ENDGAME_GATE_SHARED_EDITS}
        self.assertFalse(shared & AND_SITES)


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestAgainstTheDisc(unittest.TestCase):
    """Every vanilla word we claim is really there. A wrong offset here is a
    gate that never opens, which is an unfinishable seed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._fh = open(ROM, "rb")
        cls.rom = mmap.mmap(cls._fh.fileno(), 0, access=mmap.ACCESS_READ)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.rom.close()
        cls._fh.close()

    def test_every_vanilla_word_matches(self) -> None:
        for label, where, region, van, _pat in EDITS:
            off = disc.addr_to_disc(where, region)
            self.assertEqual(bytes(self.rom[off:off + len(van)]), van, label)

    def test_the_flag_is_computed_where_we_think(self) -> None:
        # sltiu a3, v0, 1 - the all-eight test whose result the AND preserves.
        off = disc.addr_to_disc(0x0D671C, disc.REGION_ROCK)
        ins = int.from_bytes(self.rom[off:off + 4], "little")
        self.assertEqual(ins >> 26, 0x0B, "not an sltiu")
        self.assertEqual((ins >> 16) & 0x1F, 7, "destination is not a3")


class TestASeedGenerates(MMX6TestBase):
    options = {"goal": Goal.option_all_mavericks_high_max_sigma}

    def test_the_goal_is_reachable(self) -> None:
        # Logic needs nothing new: High Max requires a charged special weapon,
        # and The Gate's entrance rule already requires ALL weapons.
        self.assertTrue(self.multiworld.can_beat_game(
            self.multiworld.get_all_state()))


class TestThePatchCarriesTheEdits(MMX6TestBase):
    options = {"goal": Goal.option_all_mavericks_high_max_sigma}

    def test_the_seed_asks_for_the_and(self) -> None:
        captured = {}

        class _Patch:
            @staticmethod
            def write_file(name, data):
                captured[name] = data

        patch_rom(self.world, _Patch())
        import json
        edits = json.loads(captured["seed_edits.json"].decode("utf-8"))
        sites = {e["addr"] for e in edits}
        self.assertTrue(AND_SITES <= sites, "the AND edits are missing")
        # And the site the other goal would have neutralised is NOT written.
        self.assertNotIn(CONDITION_3_TEST, sites)


class TestTheOtherGoalIsUnchanged(MMX6TestBase):
    """The control: all_mavericks_sigma must still produce its own edits."""
    options = {"goal": Goal.option_all_mavericks_sigma}

    def test_it_still_neutralises_condition_3(self) -> None:
        captured = {}

        class _Patch:
            @staticmethod
            def write_file(name, data):
                captured[name] = data

        patch_rom(self.world, _Patch())
        import json
        sites = {e["addr"] for e
                 in json.loads(captured["seed_edits.json"].decode("utf-8"))}
        self.assertIn(CONDITION_3_TEST, sites)
        self.assertFalse(AND_SITES & sites - {CONDITION_3_TEST}
                         & {0x0D6720, 0x0D6734, 0x0D6784})


class TestTheOptionIsInTheDataclass(unittest.TestCase):
    def test_it_is(self) -> None:
        self.assertIn("goal", MMX6Options.type_hints)
