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
  * and it must RE-OPEN the Gate itself at 8/8, so that closing it can never
    strand a seed whose only write of 3 was the one we overwrote.

Two guards were added 2026-08-28 after a tester reached 7 Mavericks and got
the EIGHT-Maverick unlock cutscene replaying on every stage exit, with the
Gate icon drawn but not re-selectable:

  * the gate acts ONLY on a Maverick count taken from a TRUSTED screen. It
    used to popcount the save struct on the stage select, which this client
    does not trust, excused as "a wrong open is just vanilla behaviour" - and
    under all_mavericks a wrong open is the whole thing the gate prevents.
    With no trusted count yet, it does nothing at all;
  * it corrects the byte at most ENDGAME_GATE_MAX_CORRECTIONS times, then
    concedes and warns. "A value written into this byte STAYS" was measured
    with the stage select ALREADY UP, where it holds; vanilla can still write
    3 on the way back into the hub if High Max or 3000 souls says so, and
    fighting that every poll is what replays the cutscene.

Refined 2026-08-28 during the 0.1.1 review: the early-entry warning also
speaks only from trusted data - it used to fire on any progress >= 4, which
told a legitimate 8/8 player mid-endgame that they had entered early - and
conceding stops the CLOSE only, never the 8/8 all-clear.

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
    """`_detect` only reads these."""
    def __init__(self) -> None:
        self.slot_data = {}
        self.checked_locations = set()
        self.finished_game = False
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


def after_trusted_poll(beaten_bits: int = 0) -> MMX6Client:
    """A client that has seen one TRUSTED poll showing `beaten_bits` set.

    The gate refuses to act on anything else, so a test that expects it to do
    something has to say what a trusted screen saw. Passing a plain
    `MMX6Client()` instead is the "no trusted poll yet" case, and the gate is
    required to stay silent there.
    """
    client = MMX6Client()
    client.mavericks_trusted = bin(beaten_bits).count("1")
    return client


class TestTheGateCloses(unittest.TestCase):
    def test_an_open_gate_is_forced_shut_below_eight(self) -> None:
        writes = run(after_trusted_poll(0b00000111), FakeCtx(),
                     save_at(PROGRESS_ENDGAME_OPEN, 0b00000111), SELECT)
        self.assertEqual(
            writes,
            [(SAVE_BASE + OFF_PROGRESS, [PROGRESS_STAGE_SELECT], "MainRAM")])

    def test_it_writes_exactly_one_byte(self) -> None:
        # A wider write would run straight into the neighbouring save bytes.
        (_addr, data, _dom), = run(after_trusted_poll(), FakeCtx(),
                                   save_at(PROGRESS_ENDGAME_OPEN), SELECT)
        self.assertEqual(len(data), 1)

    def test_it_closes_on_every_stage_select_screen(self) -> None:
        # 0x04 is what the hub actually reads in play; the workbook documents
        # 0x02 and 0x03. All three are treated as the stage select.
        for screen in STAGE_SELECT_SCREENS:
            self.assertTrue(
                run(after_trusted_poll(), FakeCtx(),
                    save_at(PROGRESS_ENDGAME_OPEN), screen),
                f"did not close on stage-select screen {screen:#04x}")

    def test_seven_of_eight_is_still_short(self) -> None:
        self.assertTrue(run(after_trusted_poll(0b01111111), FakeCtx(),
                            save_at(PROGRESS_ENDGAME_OPEN, 0b01111111), SELECT))

    def test_it_will_not_act_without_a_trusted_count(self) -> None:
        # GUARD 1. The stage select is not a trusted screen, so a save read
        # taken here can be anything. Seven Mavericks and an open Gate is the
        # reported case; with no trusted poll behind it the gate must stay out
        # of the way entirely rather than guess from these bytes.
        client = MMX6Client()
        self.assertIsNone(client.mavericks_trusted)
        self.assertEqual(
            run(client, FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0b01111111),
                SELECT), [])

    def test_it_stops_correcting_and_says_so(self) -> None:
        # GUARD 2. If the game keeps re-opening the Gate, one of ITS conditions
        # is met - High Max, or 3000 souls - and every correction we make costs
        # the player another unlock cutscene. Bail out and warn instead.
        client = after_trusted_poll(0b00000111)
        save = save_at(PROGRESS_ENDGAME_OPEN, 0b00000111)
        for _ in range(client_module.ENDGAME_GATE_MAX_CORRECTIONS):
            self.assertTrue(run(client, FakeCtx(), save, SELECT))
        with self.assertLogs("Client", level="WARNING") as caught:
            self.assertEqual(run(client, FakeCtx(), save, SELECT), [])
        self.assertTrue(any("DO NOT FIGHT SIGMA YET" in m
                            for m in caught.output))
        self.assertTrue(client.endgame_gate_conceded)
        # And it stays quiet afterwards rather than warning twice a second.
        self.assertEqual(run(client, FakeCtx(), save, SELECT), [])

    def test_conceding_never_blocks_the_all_clear(self) -> None:
        # Concede at seven, then the eighth falls on a trusted poll. The
        # concession stops the client CLOSING the Gate; it must not swallow
        # the all-clear (the player was just told not to fight Sigma, and
        # needs to hear when that stops being true) nor the re-open write.
        client = after_trusted_poll(0b00000111)
        save = save_at(PROGRESS_ENDGAME_OPEN, 0b00000111)
        for _ in range(client_module.ENDGAME_GATE_MAX_CORRECTIONS):
            run(client, FakeCtx(), save, SELECT)
        with self.assertLogs("Client", level="WARNING"):
            run(client, FakeCtx(), save, SELECT)
        self.assertTrue(client.endgame_gate_conceded)
        self.assertTrue(client.endgame_gate_held)

        client.mavericks_trusted = 8
        with self.assertLogs("Client", level="INFO") as caught:
            self.assertEqual(
                run(client, FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0xFF),
                    SELECT), [])
        self.assertTrue(any("the Gate is open" in m for m in caught.output))
        self.assertFalse(client.endgame_gate_held)
        # And if the byte somehow read 2 at 8/8, conceded or not, it is
        # re-opened - the stranding case the re-open exists for.
        self.assertEqual(
            run(client, FakeCtx(), save_at(PROGRESS_STAGE_SELECT, 0xFF),
                SELECT),
            [(SAVE_BASE + OFF_PROGRESS, [PROGRESS_ENDGAME_OPEN], "MainRAM")])


class TestTheGateOpens(unittest.TestCase):
    def test_all_eight_beaten_opens_it(self) -> None:
        self.assertEqual(
            run(MMX6Client(), FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0xFF),
                SELECT), [])

    def test_a_cold_connect_does_not_lock_a_finished_save(self) -> None:
        # THE REGRESSION THIS GUARDS. A client that has just connected has no
        # trusted count, and the stage select will never give it one. It must
        # not slam the Gate shut on a player who has genuinely beaten all
        # eight.
        #
        # This used to be answered by ALSO popcounting the save read here,
        # which is what let a bad stage-select read force the Gate open. The
        # answer now is to do nothing without trusted data - safe in both
        # directions rather than trading one failure for the other.
        c = MMX6Client()
        self.assertIsNone(c.mavericks_trusted)
        self.assertEqual(
            run(c, FakeCtx(), save_at(PROGRESS_ENDGAME_OPEN, 0xFF), SELECT), [])

    def test_a_stale_save_read_cannot_re_close_an_earned_gate(self) -> None:
        # The other direction: a trusted poll saw all eight, so a later save
        # read that happens to be stale must not re-close a gate already
        # earned. The gate believes the trusted count, not these bytes.
        self.assertEqual(
            run(after_trusted_poll(0xFF), FakeCtx(),
                save_at(PROGRESS_ENDGAME_OPEN, 0x00), SELECT), [])


class TestTheGateReopens(unittest.TestCase):
    """The stranding bug this feature could have been.

    The progress byte is not recomputed while the stage select is up: writing
    2 sticks, and the icon only returns when 3 is written back. So if the
    client forced 2 over the game's only write of 3 - High Max dying at three
    Mavericks, say - nothing would ever set it again, and the endgame would be
    permanently unreachable in a seed whose goal requires reaching it.
    """

    def test_eight_beaten_with_the_gate_held_shut_re_opens_it(self) -> None:
        writes = run(after_trusted_poll(0xFF), FakeCtx(),
                     save_at(PROGRESS_STAGE_SELECT, 0xFF), SELECT)
        self.assertEqual(
            writes,
            [(SAVE_BASE + OFF_PROGRESS, [PROGRESS_ENDGAME_OPEN], "MainRAM")])

    def test_close_then_re_open_is_a_round_trip(self) -> None:
        c, ctx = after_trusted_poll(0b01111111), FakeCtx()
        save = save_at(PROGRESS_ENDGAME_OPEN, 0b01111111)     # seven of eight
        (_a, (held,), _d), = run(c, ctx, save, SELECT)
        self.assertEqual(held, PROGRESS_STAGE_SELECT)

        save[OFF_PROGRESS] = held
        save[OFF_BEATEN] = 0xFF                               # the eighth dies
        c.mavericks_trusted = 8                               # ...on a trusted poll
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
        c = after_trusted_poll(0xFF)
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
        # A TRUSTED count of seven: the player really is inside short.
        c = after_trusted_poll(0b01111111)
        with self.assertLogs("Client", level="WARNING") as caught:
            run(c, FakeCtx(), save_at(4), SELECT)
        self.assertTrue(any("before all 8" in m for m in caught.output))
        self.assertTrue(c.endgame_gate_missed)
        # Second time it stays quiet - this is polled twice a second.
        run(c, FakeCtx(), save_at(4), SELECT)

    def test_a_legit_endgame_run_is_not_warned(self) -> None:
        # The warning used to fire on ANY progress >= 4, count unseen - so a
        # player who beat all eight, cleared Lab 1 and came back to the hub
        # was told they had "entered before all 8 Mavericks were beaten".
        c = after_trusted_poll(0xFF)
        with self.assertNoLogs("Client", level="WARNING"):
            self.assertEqual(run(c, FakeCtx(), save_at(4), SELECT), [])
        self.assertFalse(c.endgame_gate_missed)

    def test_early_entry_with_no_trusted_count_waits(self) -> None:
        # No trusted poll yet: the client cannot tell a legitimate endgame
        # run from an early entry, so it says nothing - and does not latch,
        # so the warning can still fire once a trusted count arrives. The
        # labs are gameplay, so that count arrives before Sigma.
        c = MMX6Client()
        with self.assertNoLogs("Client", level="WARNING"):
            self.assertEqual(run(c, FakeCtx(), save_at(4), SELECT), [])
        self.assertFalse(c.endgame_gate_missed)
        c.mavericks_trusted = 7
        with self.assertLogs("Client", level="WARNING"):
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
            run(after_trusted_poll(), ctx, save_at(PROGRESS_ENDGAME_OPEN),
                SELECT))


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
