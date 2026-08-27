"""Endgame gate tests - holding Gate's Lab shut until all 8 Mavericks are down.

Vanilla does not enforce the `all_mavericks` goal. High Max in an Another
Route opens the Gate early, and that is not theoretical: it happened in the
2026-08-27 playthrough at THREE Mavericks beaten. Because there is no
post-credits play, a player who then walks into the credits has no way back
except a save they may never have made.

What this pins is mostly the ways the gate could do HARM, because the happy
path is one byte:

  * it must never write on a gameplay screen - the progress byte is part of
    `_check_signature`, and a value that disagrees with itself between polls
    would starve the trust gate every check depends on;
  * it must never touch progress >= 4, which is the only durable record that
    Secret Lab 1 and 2 were cleared;
  * it must not fire under the `sigma` goal, which explicitly permits
    finishing with Mavericks skipped;
  * and it must RE-OPEN the Gate itself at 8/8. A value written into the
    progress byte stays - measured live 2026-08-27 - so a client that closes
    the Gate and then leaves re-opening to the game would make the seed
    unwinnable whenever the write it overwrote was the game's only one.

The lock is the PROGRESS BYTE, not a slot table. Secret Lab sits on cursor 08
and the stage-select table holds exactly eight entries for slots 0-7 with the
next row butted against it, so there is no slot to zero - measured live
2026-08-27, along with the fact that forcing 0x800CCF36 to 2 makes the icon
unselectable and 3 restores it.
"""
import asyncio
import unittest

from .. import client as client_module
from .. import names
from ..client import (GOAL_ALL_MAVERICKS, GOAL_SIGMA, OFF_BEATEN, OFF_PROGRESS,
                      PROGRESS_ENDGAME_OPEN, PROGRESS_STAGE_SELECT, SAVE_BASE,
                      SAVE_LEN, STAGE_SELECT_SCREENS, TRUSTED_SCREENS,
                      MMX6Client)
from ..locations import location_table


class FakeCtx:
    def __init__(self, goal=GOAL_ALL_MAVERICKS) -> None:
        self.slot_data = {"goal": goal}
        self.bizhawk_ctx = object()


class DetectCtx:
    """`_detect` only reads these three."""
    def __init__(self) -> None:
        self.slot_data = {}
        self.checked_locations = set()
        self.items_received = []
        self.item_names = type(
            "N", (), {"lookup_in_game": staticmethod(lambda i: i)})


class Recorder:
    """Stands in for worlds._bizhawk, capturing writes instead of making them."""

    class RequestFailedError(Exception):
        pass

    def __init__(self) -> None:
        self.writes = []

    async def write(self, _ctx, writes):
        self.writes.extend(writes)


def run(client, ctx, save, screen):
    """Call the gate with bizhawk swapped out; return what it wrote."""
    rec = Recorder()
    real = client_module.bizhawk
    client_module.bizhawk = rec
    try:
        asyncio.run(client._endgame_gate_apply(ctx, bytes(save), screen))
    finally:
        client_module.bizhawk = real
    return rec.writes


def save_at(progress, beaten=0x00) -> bytearray:
    save = bytearray(SAVE_LEN)
    save[OFF_PROGRESS] = progress
    save[OFF_BEATEN] = beaten
    return save


SELECT = sorted(STAGE_SELECT_SCREENS)[0]


class TestTheGateCloses(unittest.TestCase):
    def test_an_open_gate_is_forced_shut_below_eight(self) -> None:
        writes = run(MMX6Client(), FakeCtx(),
                     save_at(PROGRESS_ENDGAME_OPEN, 0b00000111), SELECT)
        self.assertEqual(
            writes,
            [(SAVE_BASE + OFF_PROGRESS, [PROGRESS_STAGE_SELECT], "MainRAM")])

    def test_it_writes_exactly_one_byte(self) -> None:
        # A wider write would run straight into the neighbouring save bytes.
        (_addr, data, _dom), = run(MMX6Client(), FakeCtx(),
                                   save_at(PROGRESS_ENDGAME_OPEN), SELECT)
        self.assertEqual(len(data), 1)

    def test_it_closes_on_every_stage_select_screen(self) -> None:
        # 0x04 is what the hub actually reads in play; the workbook documents
        # 0x02 and 0x03. All three are treated as the stage select.
        for screen in STAGE_SELECT_SCREENS:
            self.assertTrue(
                run(MMX6Client(), FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN),
                    screen),
                f"did not close on stage-select screen {screen:#04x}")

    def test_seven_of_eight_is_still_short(self) -> None:
        self.assertTrue(run(MMX6Client(), FakeCtx(),
                            save_at(PROGRESS_ENDGAME_OPEN, 0b01111111), SELECT))


class TestTheGateOpens(unittest.TestCase):
    def test_all_eight_beaten_opens_it(self) -> None:
        self.assertEqual(
            run(MMX6Client(), FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0xFF),
                SELECT), [])

    def test_a_cold_connect_does_not_lock_a_finished_save(self) -> None:
        # THE REGRESSION THIS GUARDS. `mavericks_defeated` only moves on a
        # TRUSTED poll, and the stage select is not one, so a client that has
        # just connected scores 0. Reading the save as well is what stops the
        # gate slamming shut on a player who has genuinely beaten all eight.
        c = MMX6Client()
        self.assertEqual(c.mavericks_defeated, 0)
        self.assertEqual(
            run(c, FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0xFF), SELECT), [])

    def test_the_trusted_latch_alone_is_enough(self) -> None:
        # The other direction: the latch was set in play, so a save read that
        # happens to be stale must not re-close a gate already earned.
        c = MMX6Client()
        c.mavericks_defeated = 8
        self.assertEqual(
            run(c, FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0x00), SELECT), [])


class TestTheGateReopens(unittest.TestCase):
    """The stranding bug this feature could have been.

    The progress byte is not recomputed while the stage select is up: writing
    2 sticks, and the icon only returns when 3 is written back. So if the
    client forced 2 over the game's only write of 3 - High Max dying at three
    Mavericks, say - nothing would ever set it again, and the endgame would be
    permanently unreachable in a seed whose goal requires reaching it.
    """

    def test_eight_beaten_with_the_gate_held_shut_re_opens_it(self) -> None:
        writes = run(MMX6Client(), FakeCtx(),
                     save_at(PROGRESS_STAGE_SELECT, 0xFF), SELECT)
        self.assertEqual(
            writes,
            [(SAVE_BASE + OFF_PROGRESS, [PROGRESS_ENDGAME_OPEN], "MainRAM")])

    def test_close_then_re_open_is_a_round_trip(self) -> None:
        c, ctx = MMX6Client(), FakeCtx()
        save = save_at(PROGRESS_ENDGAME_OPEN, 0b01111111)     # seven of eight
        (_a, (held,), _d), = run(c, ctx, save, SELECT)
        self.assertEqual(held, PROGRESS_STAGE_SELECT)

        save[OFF_PROGRESS] = held
        save[OFF_BEATEN] = 0xFF                               # the eighth dies
        (_a, (opened,), _d), = run(c, ctx, save, SELECT)
        self.assertEqual(opened, PROGRESS_ENDGAME_OPEN)

    def test_an_already_open_gate_is_not_rewritten(self) -> None:
        # Nothing to do; a write every poll would be pure noise on the wire.
        self.assertEqual(
            run(MMX6Client(), FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0xFF),
                SELECT), [])

    def test_it_never_leapfrogs_the_intro(self) -> None:
        # progress 0 and 1 are before the stage select exists. Writing 3 there
        # would open the endgame in a game that has not started one.
        for progress in (0, 1):
            self.assertEqual(
                run(MMX6Client(), FakeCtx(), save_at(progress, 0xFF), SELECT),
                [], f"wrote at progress {progress}")

    def test_re_opening_survives_a_reconnect(self) -> None:
        # The decision is taken from the SAVE, not from an in-memory "did we
        # hold it?" flag - which `_reset_state` clears on every BizHawk
        # reconnect, and reconnects are routine.
        c = MMX6Client()
        self.assertFalse(c.endgame_gate_held)
        self.assertTrue(
            run(c, FakeCtx(), save_at(PROGRESS_STAGE_SELECT, 0xFF), SELECT))

    def test_the_sigma_goal_is_not_re_opened_either(self) -> None:
        self.assertEqual(
            run(MMX6Client(), FakeCtx(goal=GOAL_SIGMA),
                save_at(PROGRESS_STAGE_SELECT, 0xFF), SELECT), [])


class TestItNeverDoesHarm(unittest.TestCase):
    def test_it_never_writes_on_a_trusted_screen(self) -> None:
        # The progress byte is part of _check_signature. Writing it during
        # gameplay would make the signature disagree with itself between polls
        # and could starve the trust gate that every check depends on.
        for screen in TRUSTED_SCREENS:
            self.assertEqual(
                run(MMX6Client(), FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN),
                    screen), [],
                f"wrote on trusted screen {screen:#04x}")

    def test_the_progress_byte_really_is_in_the_check_signature(self) -> None:
        # If it ever stops being, the reasoning above goes stale rather than
        # wrong - but silently so, which is worse.
        c = MMX6Client()
        self.assertNotEqual(c._check_signature(bytes(save_at(2))),
                            c._check_signature(bytes(save_at(3))))

    def test_a_lab_clear_is_never_discarded(self) -> None:
        # progress 4 and 5 are the ONLY record that Secret Lab 1 and 2 were
        # cleared. Forcing 2 there would erase them, and the byte is monotonic
        # precisely so that a clear cannot be un-earned.
        for progress in (4, 5):
            self.assertEqual(
                run(MMX6Client(), FakeCtx(), save_at(progress), SELECT), [],
                f"clobbered progress {progress}")

    def test_entering_the_endgame_early_is_reported_once(self) -> None:
        c = MMX6Client()
        with self.assertLogs("Client", level="WARNING") as caught:
            run(c, FakeCtx(), save_at(4), SELECT)
        self.assertTrue(any("before all 8" in m for m in caught.output))
        self.assertTrue(c.endgame_gate_missed)
        # Second time it stays quiet - this is polled twice a second.
        run(c, FakeCtx(), save_at(4), SELECT)

    def test_a_shut_gate_is_left_alone(self) -> None:
        # Nothing to do, and writing anyway would fight the intro sequence.
        for progress in (0, 1, PROGRESS_STAGE_SELECT):
            self.assertEqual(
                run(MMX6Client(), FakeCtx(), save_at(progress), SELECT), [],
                f"wrote at progress {progress}")

    def test_the_sigma_goal_is_untouched(self) -> None:
        # `sigma` is documented as "defeat Sigma, however you got there", so a
        # run may legitimately finish with Mavericks skipped. Gating it would
        # break the option rather than enforce it.
        self.assertEqual(
            run(MMX6Client(), FakeCtx(goal=GOAL_SIGMA),
                save_at(PROGRESS_ENDGAME_OPEN), SELECT), [])

    def test_a_seed_with_no_slot_data_is_still_gated(self) -> None:
        # all_mavericks is the default, and the fallback everywhere else in
        # the client. A missing goal must not silently disable the gate.
        ctx = FakeCtx()
        ctx.slot_data = {}
        self.assertTrue(
            run(MMX6Client(), ctx, save_at(PROGRESS_ENDGAME_OPEN), SELECT))


class TestConstants(unittest.TestCase):
    def test_shut_is_below_open(self) -> None:
        self.assertLess(PROGRESS_STAGE_SELECT, PROGRESS_ENDGAME_OPEN)

    def test_the_held_value_still_proves_the_intro_was_cleared(self) -> None:
        # INTRO_CLEAR fires on progress >= 1. If the held value ever dropped
        # to 0 it would retract a location the player really earned.
        self.assertGreaterEqual(PROGRESS_STAGE_SELECT, 1)
        found = MMX6Client()._detect(DetectCtx(),
                                     bytes(save_at(PROGRESS_STAGE_SELECT)))
        self.assertIn(location_table[names.INTRO_CLEAR], found)

    def test_open_is_the_threshold_the_gate_check_uses(self) -> None:
        # "The Gate - Opened" and the value the client forces back down are
        # two names for one fact; a drift between them would let the gate
        # close while the check still fired.
        self.assertEqual(dict(names.ENDGAME_CHECKS)[names.ENDGAME_UNLOCKED],
                         PROGRESS_ENDGAME_OPEN)


if __name__ == "__main__":
    unittest.main()
