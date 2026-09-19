"""DeathLink.

The two primitives are asymmetric and the asymmetry is the whole design:

  kill    write 0x80 (the engine's death sentinel) to the live HP byte. It is
          the ONLY value the death check accepts - `bne $v1,-0x80` at
          0x80039454 - which is exactly why mmx6-external-findings 12.3 saw a
          write of 0 produce a 2,400-frame soft-lock instead of a death. That
          finding disproved 0; it never tested the sentinel.
  detect  player +0x04 == 2. That byte is the top-level state selector and
          entry [2] of jump table 0x80073ABC IS the death state machine, so it
          holds for the whole death animation. The sentinel lasts one frame
          and a ~0.5s poll would never see it. (The 0x11 -> 00 -> 01 -> 03
          sequence in the research notes is +0x05, the SUB-state.)

Proven live on X5, whose client this is ported from, across 5 deaths in a
2-slot multiworld. See ai-docs/plans/2026-09-19_deathlink-x5-x6.md.
"""
import unittest
from unittest import mock

import worlds._bizhawk as bizhawk

from ..client import (CHAR_ZERO, MMX6Client, OFF_CHAR, OFF_P_HP, OFF_P_STATE,
                      PLAYER_HP_ADDR, PLAYER_HP_DEATH_SENTINEL, PLAYER_LEN,
                      PLAYER_STATE_DEAD, SCREEN_INGAME, SCREEN_MISSION_REPORT)
from .test_client import FakeCtx, blank_save

ALIVE = 1


class DeathCtx(FakeCtx):
    """FakeCtx plus the DeathLink surface CommonContext normally provides."""

    def __init__(self, enabled: bool = True) -> None:
        super().__init__()
        self.slot_data = {"death_link": 1 if enabled else 0}
        self.bizhawk_ctx = object()
        self.player_names = {1: "Player1"}
        self.tags: set = set()
        self.last_death_link = 0.0
        self.deaths_sent: list = []

    async def update_death_link(self, enabled: bool) -> None:
        if enabled:
            self.tags.add("DeathLink")
        else:
            self.tags.discard("DeathLink")

    async def send_death(self, death_text: str = "") -> None:
        self.deaths_sent.append(death_text)


def player_block(state: int = ALIVE, hp: int = 0x10) -> bytes:
    block = bytearray(PLAYER_LEN)
    block[OFF_P_STATE] = state
    block[OFF_P_HP] = hp
    return bytes(block)


class DeathLinkCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.client = MMX6Client()
        self.ctx = DeathCtx()
        self.writes: list = []

    async def handle(self, state=ALIVE, screen=SCREEN_INGAME, save=None,
                     player=None):
        async def fake_write(_ctx, writes, *_a, **_kw):
            self.writes.extend(writes)
            return True
        block = player if player is not None else player_block(state)
        with mock.patch.object(bizhawk, "write", fake_write):
            await self.client._handle_death_link(
                self.ctx, screen,
                bytes(save if save is not None else blank_save()), block)

    def bounce(self, source="Someone Else") -> None:
        self.client.on_package(self.ctx, "Bounced", {
            "tags": ["DeathLink"],
            "data": {"time": 1.0, "source": source, "cause": "died"},
        })

    def hp_writes(self) -> list:
        return [w[1][0] for w in self.writes if w[0] == PLAYER_HP_ADDR]


class TestSendingDeaths(DeathLinkCase):

    async def test_death_sends_one_deathlink(self):
        await self.handle(state=ALIVE)          # arms the latch
        await self.handle(state=PLAYER_STATE_DEAD)
        self.assertEqual(len(self.ctx.deaths_sent), 1)

    async def test_does_not_resend_while_still_dead(self):
        """The death state runs the whole animation, so it spans several
        polls. Without the latch that is one DeathLink per poll."""
        await self.handle(state=ALIVE)
        for _ in range(5):
            await self.handle(state=PLAYER_STATE_DEAD)
        self.assertEqual(len(self.ctx.deaths_sent), 1)

    async def test_rearms_after_respawn(self):
        await self.handle(state=ALIVE)
        await self.handle(state=PLAYER_STATE_DEAD)
        await self.handle(state=ALIVE)          # respawned
        await self.handle(state=PLAYER_STATE_DEAD)
        self.assertEqual(len(self.ctx.deaths_sent), 2)

    async def test_fresh_client_attached_to_a_dead_player_stays_quiet(self):
        """`sending_death_link` starts True precisely so a client that
        attaches mid-death does not announce a death it never saw begin."""
        await self.handle(state=PLAYER_STATE_DEAD)
        self.assertEqual(self.ctx.deaths_sent, [])

    async def test_no_send_on_the_mission_report(self):
        """0x0C is trusted for checks but has no live player object, so +0x04
        means nothing there."""
        await self.handle(state=ALIVE)
        await self.handle(state=PLAYER_STATE_DEAD, screen=SCREEN_MISSION_REPORT)
        self.assertEqual(self.ctx.deaths_sent, [])

    async def test_no_send_on_an_empty_player_block(self):
        await self.handle(state=ALIVE)
        await self.handle(player=b"")
        self.assertEqual(self.ctx.deaths_sent, [])

    async def test_cause_names_the_character(self):
        save = blank_save()
        save[OFF_CHAR] = CHAR_ZERO
        await self.handle(state=ALIVE, save=save)
        await self.handle(state=PLAYER_STATE_DEAD, save=save)
        self.assertIn("Zero", self.ctx.deaths_sent[0])


class TestReceivingDeaths(DeathLinkCase):

    async def test_incoming_writes_the_sentinel(self):
        await self.handle(state=ALIVE)
        self.bounce()
        await self.handle(state=ALIVE)
        self.assertIn(PLAYER_HP_DEATH_SENTINEL, self.hp_writes())

    async def test_sentinel_is_0x80_not_zero(self):
        """Writing 0 fails the engine's `bne $v1,-0x80` and soft-locks the
        player at zero HP - the 2,400-frame freeze in external-findings 12.3.
        Guard the value, because 0 is the intuitive thing to write."""
        await self.handle(state=ALIVE)
        self.bounce()
        await self.handle(state=ALIVE)
        self.assertNotIn(0, self.hp_writes())

    async def test_incoming_does_not_bounce_back_out(self):
        """The kill we apply must not read as our own death next poll -
        otherwise two linked players trade deaths forever."""
        await self.handle(state=ALIVE)
        self.bounce()
        await self.handle(state=ALIVE)                  # applies the kill
        await self.handle(state=PLAYER_STATE_DEAD)      # engine shows it
        self.assertEqual(self.ctx.deaths_sent, [])

    async def test_our_own_bounce_is_ignored(self):
        await self.handle(state=ALIVE)
        self.bounce(source="Player1")                   # ctx.player_names[1]
        await self.handle(state=ALIVE)
        self.assertEqual(self.hp_writes(), [])

    async def test_dropped_rather_than_queued_outside_gameplay(self):
        """X1-X3's rule. A kill landing during a transition is how a client
        desyncs; a dropped DeathLink costs the player nothing. Verified live
        on X5: arriving on a menu left nothing to apply on stage re-entry."""
        self.bounce()
        await self.handle(state=ALIVE, screen=SCREEN_MISSION_REPORT)
        self.assertFalse(self.client.pending_death_link)
        await self.handle(state=ALIVE, screen=SCREEN_INGAME)
        self.assertEqual(self.hp_writes(), [])

    async def test_not_killed_twice_while_already_dying(self):
        await self.handle(state=ALIVE)
        self.bounce()
        await self.handle(state=PLAYER_STATE_DEAD)
        self.assertEqual(self.hp_writes(), [])

    async def test_bounce_without_the_tag_is_ignored(self):
        self.client.on_package(self.ctx, "Bounced",
                               {"tags": ["SomethingElse"], "data": {"source": "x"}})
        self.assertFalse(self.client.pending_death_link)

    async def test_non_bounce_packets_are_ignored(self):
        self.client.on_package(self.ctx, "Connected", {"slot_data": {}})
        self.assertFalse(self.client.pending_death_link)


if __name__ == "__main__":
    unittest.main()
