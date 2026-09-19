"""DeathLink.

The two primitives are asymmetric and the asymmetry is the whole design, so
the tests are written around it:

  kill    write 0x80 (the engine's death sentinel) to the live HP byte. It is
          the ONLY value the engine's check accepts - `bne $v1,-0x80` at
          0x80038A88 - which is why writing 0 does nothing but strand the
          player alive at zero HP.
  detect  player +0x04 == 2. That byte is the top-level state selector and
          entry [2] of its jump table IS the death state machine, so it holds
          for the whole death animation. The sentinel itself survives one
          frame and a ~0.5s poll would never see it.

See ai-docs/plans/2026-09-19_deathlink-x5-x6.md and mmx5-ghidra-findings.md 4.1.
"""
import unittest

from .. import client as mmx5_client
from ..client import MMX5Client
from .test_client import FakeContext, make_save, run_watcher

ALIVE = 1
DEAD = mmx5_client.PLAYER_STATE_DEAD          # 2
SENTINEL = mmx5_client.PLAYER_HP_DEATH_SENTINEL   # 0x80


def death_ctx(enabled: bool = True) -> FakeContext:
    ctx = FakeContext()
    ctx.slot_data = {"goal": 0, "boss_difficulty": 1,
                     "death_link": 1 if enabled else 0}
    return ctx


def hp_writes(ctx) -> list:
    """Values written to the live player HP byte, in order."""
    return [w[1][0] for w in ctx.writes
            if w[0] == mmx5_client.PLAYER_HP_ADDR]


async def poll(client, ctx, state=ALIVE, mode=0x0A, save=None, **kw):
    return await run_watcher(save if save is not None else make_save(0x20),
                             mode=mode, client=client, ctx=ctx,
                             player_state=state, **kw)


class TestDeathLinkTag(unittest.IsolatedAsyncioTestCase):

    async def test_tag_set_when_option_on(self):
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx)
        self.assertIn("DeathLink", ctx.tags)

    async def test_tag_absent_when_option_off(self):
        client, ctx = MMX5Client(), death_ctx(False)
        await poll(client, ctx)
        self.assertNotIn("DeathLink", ctx.tags)

    async def test_tag_survives_repeated_polls(self):
        client, ctx = MMX5Client(), death_ctx(True)
        for _ in range(4):
            await poll(client, ctx)
        self.assertIn("DeathLink", ctx.tags)

    async def test_tag_is_reregistered_if_the_tag_set_is_rebuilt(self):
        """A reconnect can hand us a fresh tag set. Keying re-registration on
        the tag itself rather than a local flag is what stops DeathLink
        silently going dead for the rest of the session."""
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx)
        ctx.tags.clear()
        await poll(client, ctx)
        self.assertIn("DeathLink", ctx.tags)


class TestSendingDeaths(unittest.IsolatedAsyncioTestCase):

    async def test_death_sends_one_deathlink(self):
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)      # arms the latch
        await poll(client, ctx, state=DEAD)
        self.assertEqual(len(ctx.deaths_sent), 1)

    async def test_does_not_resend_while_still_dead(self):
        """The death state runs the whole explosion/fade/respawn, so it spans
        several polls. Without the latch that is one DeathLink per poll."""
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        for _ in range(5):
            await poll(client, ctx, state=DEAD)
        self.assertEqual(len(ctx.deaths_sent), 1)

    async def test_rearms_after_respawn(self):
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        await poll(client, ctx, state=DEAD)
        await poll(client, ctx, state=ALIVE)      # respawned
        await poll(client, ctx, state=DEAD)
        self.assertEqual(len(ctx.deaths_sent), 2)

    async def test_fresh_client_attached_to_a_dead_player_stays_quiet(self):
        """`sending_death_link` starts True precisely so a client that
        attaches mid-death does not announce a death it never saw begin."""
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=DEAD)
        self.assertEqual(ctx.deaths_sent, [])

    async def test_no_send_when_option_off(self):
        client, ctx = MMX5Client(), death_ctx(False)
        await poll(client, ctx, state=ALIVE)
        await poll(client, ctx, state=DEAD)
        self.assertEqual(ctx.deaths_sent, [])

    async def test_no_send_outside_gameplay(self):
        """0x0C is the results screen: the save-struct gate trusts it, but
        there is no live player object, so +0x04 means nothing there."""
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        await poll(client, ctx, state=DEAD, mode=0x0C)
        self.assertEqual(ctx.deaths_sent, [])

    async def test_no_send_in_training_mode(self):
        client, ctx = MMX5Client(), death_ctx(True)
        training = bytearray(make_save(0x20))
        training[mmx5_client.OFF_INTRO] = mmx5_client.TRAINING_ACT
        await poll(client, ctx, state=ALIVE, save=bytes(training))
        await poll(client, ctx, state=DEAD, save=bytes(training))
        self.assertEqual(ctx.deaths_sent, [])

    async def test_cause_names_the_character(self):
        client, ctx = MMX5Client(), death_ctx(True)
        zero = bytearray(make_save(0x20))
        zero[mmx5_client.OFF_CHAR] = 1
        await poll(client, ctx, state=ALIVE, save=bytes(zero))
        await poll(client, ctx, state=DEAD, save=bytes(zero))
        self.assertIn("Zero", ctx.deaths_sent[0])


class TestReceivingDeaths(unittest.IsolatedAsyncioTestCase):

    @staticmethod
    def bounce(ctx, client, source="Someone Else"):
        client.on_package(ctx, "Bounced", {
            "tags": ["DeathLink"],
            "data": {"time": 1.0, "source": source, "cause": "died"},
        })

    async def test_incoming_writes_the_sentinel(self):
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        self.bounce(ctx, client)
        await poll(client, ctx, state=ALIVE)
        self.assertIn(SENTINEL, hp_writes(ctx))

    async def test_sentinel_is_0x80_not_zero(self):
        """Writing 0 leaves the player alive at zero HP and the damage handler
        re-running against it - the old 'hit-loop' symptom. Guard the value."""
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        self.bounce(ctx, client)
        await poll(client, ctx, state=ALIVE)
        self.assertNotIn(0, hp_writes(ctx))

    async def test_incoming_does_not_bounce_back_out(self):
        """The kill we apply must not read as our own death next poll."""
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        self.bounce(ctx, client)
        await poll(client, ctx, state=ALIVE)   # applies the kill
        await poll(client, ctx, state=DEAD)    # engine now shows the death
        self.assertEqual(ctx.deaths_sent, [])

    async def test_our_own_bounce_is_ignored(self):
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        self.bounce(ctx, client, source="Player1")   # ctx.player_names[1]
        await poll(client, ctx, state=ALIVE)
        self.assertEqual(hp_writes(ctx), [])

    async def test_dropped_rather_than_queued_outside_gameplay(self):
        """X1-X3's rule. A kill landing during a transition is how a client
        desyncs; a dropped DeathLink costs the player nothing."""
        client, ctx = MMX5Client(), death_ctx(True)
        self.bounce(ctx, client)
        await poll(client, ctx, state=ALIVE, mode=0x0C)   # gate shut
        self.assertFalse(client.pending_death_link)
        ctx.writes.clear()
        await poll(client, ctx, state=ALIVE, mode=0x0A)   # gate open again
        self.assertEqual(hp_writes(ctx), [])

    async def test_not_killed_twice_while_already_dying(self):
        client, ctx = MMX5Client(), death_ctx(True)
        await poll(client, ctx, state=ALIVE)
        self.bounce(ctx, client)
        await poll(client, ctx, state=DEAD)
        self.assertEqual(hp_writes(ctx), [])

    async def test_bounce_without_the_tag_is_ignored(self):
        client, ctx = MMX5Client(), death_ctx(True)
        client.on_package(ctx, "Bounced", {
            "tags": ["SomethingElse"], "data": {"source": "x"}})
        self.assertFalse(client.pending_death_link)

    async def test_bounce_discarded_when_option_off(self):
        client, ctx = MMX5Client(), death_ctx(False)
        self.bounce(ctx, client)
        await poll(client, ctx, state=ALIVE)
        self.assertEqual(hp_writes(ctx), [])
        self.assertFalse(client.pending_death_link)


if __name__ == "__main__":
    unittest.main()
