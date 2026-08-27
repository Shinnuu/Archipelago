"""Goal / victory tests.

Nothing tested the goal before these. That is how a rule which fired on a
SOUL COUNT — endgame merely *unlocked*, Sigma never fought, possibly still
standing in a Maverick stage — shipped under a docstring promising "defeat
Sigma, however you got there".

The X5 world learned the same lesson twice over, and both halves are pinned
here:

  * fire on the post-Sigma ENDING SCREEN, not on a gate being open;
  * take the Maverick count from play-latched state, never from a read at goal
    time, because the save struct is not sane during the ending. X5's
    equivalent counter LATCHES, so one stale read scores 8 permanently and
    hands out a false victory no later good read can undo.
"""
import unittest

from ..client import (ENDING_SCREENS, GOAL_ALL_MAVERICKS, GOAL_SIGMA,
                      SCREEN_END_CREDITS_HELD, TRUSTED_SCREENS,
                      SCREEN_END_CREDITS, SCREEN_INGAME,
                      SCREEN_MISSION_REPORT, MMX6Client)


def client(patched=True, kills=0, warned=False, sent=False) -> MMX6Client:
    c = MMX6Client()
    c.ap_patched = patched
    c.mavericks_defeated = kills
    c.short_ending_warned = warned
    c.victory_sent = sent
    return c


class TestEndingScreens(unittest.TestCase):
    def test_the_credits_screen_is_not_a_gameplay_screen(self) -> None:
        # If it were, the goal would fire during ordinary play.
        self.assertNotIn(SCREEN_INGAME, ENDING_SCREENS)
        self.assertNotIn(SCREEN_MISSION_REPORT, ENDING_SCREENS)
        self.assertIn(SCREEN_END_CREDITS, ENDING_SCREENS)

    def test_the_held_credits_screen_is_watched_too(self) -> None:
        # 0x10 is a ONE-FRAME transition stub: its handler (0x8001ED44)
        # rewrites the screen byte to 0x11 on its third instruction, and the
        # watcher polls at 0.5 s. Watching 0x10 alone would miss the ending
        # ~97% of the time and the goal would never fire. 0x11 is the state
        # that holds, and 0x10's handler is its only writer.
        self.assertIn(SCREEN_END_CREDITS_HELD, ENDING_SCREENS)
        self.assertNotEqual(SCREEN_END_CREDITS, SCREEN_END_CREDITS_HELD)

    def test_the_held_credits_screen_completes_the_sigma_goal(self) -> None:
        self.assertTrue(
            client()._goal_decision(SCREEN_END_CREDITS_HELD, GOAL_SIGMA))

    def test_no_trusted_screen_is_an_ending_screen(self) -> None:
        # The save is only believed on the trusted screens; an ending screen
        # that was also trusted would let a half-written save goal the seed.
        self.assertFalse(ENDING_SCREENS & TRUSTED_SCREENS)


class TestSigmaGoal(unittest.TestCase):
    """`sigma` — "defeat Sigma, however you got there"."""

    def test_does_not_fire_during_play_however_far_along(self) -> None:
        # THE BUG THIS FILE EXISTS FOR. The old rule fired the moment the
        # endgame was merely unlocked, which needed no Sigma and no lab.
        c = client(kills=8)
        for screen in (0x00, 0x02, 0x04, SCREEN_INGAME, SCREEN_MISSION_REPORT,
                       0x07, 0x0B):
            self.assertFalse(c._goal_decision(screen, GOAL_SIGMA),
                             f"fired on screen {screen:#04x}")

    def test_fires_on_the_ending_screen(self) -> None:
        self.assertTrue(client()._goal_decision(SCREEN_END_CREDITS, GOAL_SIGMA))

    def test_fires_even_with_no_mavericks_beaten(self) -> None:
        # That is the whole point of this goal.
        self.assertTrue(
            client(kills=0)._goal_decision(SCREEN_END_CREDITS, GOAL_SIGMA))


class TestAllMavericksGoal(unittest.TestCase):
    def test_does_not_fire_during_play(self) -> None:
        c = client(kills=8)
        self.assertFalse(c._goal_decision(SCREEN_INGAME, GOAL_ALL_MAVERICKS))

    def test_fires_on_the_ending_with_all_eight(self) -> None:
        self.assertTrue(
            client(kills=8)._goal_decision(SCREEN_END_CREDITS,
                                           GOAL_ALL_MAVERICKS))

    def test_a_short_ending_warns_and_does_not_fire(self) -> None:
        c = client(kills=6)
        self.assertFalse(c._goal_decision(SCREEN_END_CREDITS,
                                          GOAL_ALL_MAVERICKS))
        self.assertTrue(c.short_ending_warned)

    def test_the_warning_does_not_tell_the_player_to_keep_playing(self) -> None:
        # Ship plan item 24a. It used to say "Beat the rest and the goal fires
        # as soon as the eighth one is down", which reads as "carry on" - and
        # there IS no carrying on: settled live 2026-08-27, the credits return
        # you to the title. Reloading a save made before Gate's Lab is the
        # only route back, and this warning is the one thing the player is
        # actually reading at that moment.
        with self.assertLogs("Client", level="WARNING") as caught:
            client(kills=6)._goal_decision(SCREEN_END_CREDITS,
                                           GOAL_ALL_MAVERICKS)
        message, = caught.output
        self.assertIn("LOAD A SAVE", message)
        self.assertIn("no play after the credits", message)

    def test_it_completes_once_the_last_mavericks_die(self) -> None:
        # Reaching the credits early must not strand the run - which was the
        # worry that started this. Beat the rest and it completes.
        c = client(kills=6)
        c._goal_decision(SCREEN_END_CREDITS, GOAL_ALL_MAVERICKS)
        c.mavericks_defeated = 8
        self.assertTrue(c._goal_decision(SCREEN_INGAME, GOAL_ALL_MAVERICKS))

    def test_eight_kills_alone_never_completes_without_an_ending(self) -> None:
        # The late-completion path must not become a back door that skips
        # Sigma entirely.
        c = client(kills=8)
        for screen in (SCREEN_INGAME, SCREEN_MISSION_REPORT, 0x02, 0x04):
            self.assertFalse(c._goal_decision(screen, GOAL_ALL_MAVERICKS),
                             f"completed with no ending on {screen:#04x}")
        self.assertFalse(c.short_ending_warned)

    def test_the_warning_fires_once(self) -> None:
        c = client(kills=6)
        c._goal_decision(SCREEN_END_CREDITS, GOAL_ALL_MAVERICKS)
        self.assertTrue(c.short_ending_warned)
        c._goal_decision(SCREEN_END_CREDITS, GOAL_ALL_MAVERICKS)
        self.assertTrue(c.short_ending_warned)   # still latched, not reset


class TestDiscState(unittest.TestCase):
    def test_an_unpatched_disc_never_goals(self) -> None:
        # A goal RELEASES every remaining location in this world - the same
        # blast radius as X5's phantom-check incident.
        c = client(patched=False, kills=8)
        self.assertFalse(c._goal_decision(SCREEN_END_CREDITS, GOAL_SIGMA))
        self.assertFalse(c._goal_decision(SCREEN_END_CREDITS,
                                          GOAL_ALL_MAVERICKS))

    def test_an_undetermined_probe_still_goals(self) -> None:
        # None means "retry", never "vanilla". The credits can clobber the
        # probe region, and swallowing a real ending is its own failure.
        c = client(patched=None, kills=8)
        self.assertTrue(c._goal_decision(SCREEN_END_CREDITS, GOAL_SIGMA))

    def test_victory_is_sent_only_once(self) -> None:
        c = client(kills=8, sent=True)
        self.assertFalse(c._goal_decision(SCREEN_END_CREDITS, GOAL_SIGMA))


class TestKillLatch(unittest.TestCase):
    def test_the_latch_starts_clear_and_only_rises(self) -> None:
        c = MMX6Client()
        self.assertEqual(c.mavericks_defeated, 0)
        c.mavericks_defeated = max(c.mavericks_defeated, 3)
        c.mavericks_defeated = max(c.mavericks_defeated, 1)
        self.assertEqual(c.mavericks_defeated, 3)

    def test_a_reset_clears_it(self) -> None:
        # It latches, so a stale value surviving a reconnect would be
        # unrecoverable for the session.
        c = client(kills=8, warned=True, sent=True)
        c._reset_state()
        self.assertEqual(c.mavericks_defeated, 0)
        self.assertFalse(c.short_ending_warned)
        self.assertFalse(c.victory_sent)
