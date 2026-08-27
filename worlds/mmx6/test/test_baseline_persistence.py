"""Baseline persistence tests - ship plan item 21.

The baseline gate withholds locations a save already shows as collected when
the server has no record of this slot checking anything, because a legitimate
offline run and a save belonging to a DIFFERENT seed look identical from RAM.

The old rule armed on `fresh and not checked`, so it could only ever arm while
the server knew nothing at all. Once anything was checked the guard was dead,
and a client restart mid-run sent everything it had been withholding.

Observed 2026-08-27: a restarted client's first act was to send a phantom
check the original had correctly withheld all session. Solo that cost nothing.
In a real multiworld it is somebody else's item, released by a crash - the
exact failure the mechanism exists to prevent.

So the decision now lives in server data storage. These tests drive it through
a context that really simulates the round trip; a stub that just remembered
what was written would not test the thing that was broken.
"""
import asyncio
import unittest

from .. import names
from ..client import (BASELINE_CLEAR, BASELINE_HELD, BASELINE_UNKNOWN,
                      OFF_BEATEN, OFF_HEARTS, OFF_PROGRESS, OFF_TANKS,
                      SAVE_LEN, MMX6Client)
from ..locations import location_table


class FakeServer:
    """One slot's data storage, surviving whatever the client does."""

    def __init__(self, answer=True) -> None:
        self.team, self.slot = 0, 1
        self.stored_data: dict = {}
        self.checked_locations: set = set()
        self.answer = answer        # False = the Get reply has not arrived yet
        self.notified: set = set()
        self.items_received: list = []
        self.slot_data: dict = {}
        self.finished_game = False
        self.item_names = type(
            "N", (), {"lookup_in_game": staticmethod(lambda i: i)})

    def set_notify(self, *keys) -> None:
        for key in keys:
            if key not in self.notified:
                self.notified.add(key)
                if self.answer:
                    self.stored_data[key] = None

    async def send_msgs(self, msgs) -> None:
        for msg in msgs:
            if msg.get("cmd") == "Set":
                for op in msg["operations"]:
                    if op["operation"] == "replace":
                        self.stored_data[msg["key"]] = op["value"]

    @property
    def key(self) -> str:
        return f"mmx6_baseline_{self.team}_{self.slot}"


def progressed_save() -> bytearray:
    """A save with real progress in it - the ambiguous case."""
    save = bytearray(SAVE_LEN)
    save[OFF_PROGRESS] = 2
    save[OFF_BEATEN] = names.STAGE_BIT[names.YAMMARK]
    save[OFF_HEARTS] = names.STAGE_BIT[names.TURTLOID]
    return save


def poll(client, ctx, save):
    """One client poll: resolve the baseline, then ask what may be sent."""
    found = client._detect(ctx, bytes(save))
    asyncio.run(client._baseline_sync(ctx, found))
    return client._sendable(ctx, found)


class TestItSurvivesTheProcess(unittest.TestCase):
    """THE BUG. Every one of these passed before only by accident or not at
    all: the held set lived in memory and died with the client."""

    def test_a_restart_does_not_release_the_baseline(self) -> None:
        ctx, save = FakeServer(), progressed_save()
        self.assertEqual(poll(MMX6Client(), ctx, save), set())

        # The player collects something, so the server now has a record - the
        # exact condition that used to disarm the guard forever.
        ctx.checked_locations = {location_table[names.INTRO_CLEAR]}

        restarted = MMX6Client()
        self.assertEqual(poll(restarted, ctx, save), set(),
                         "a restart released the baseline it should hold")
        self.assertEqual(restarted.baseline_state, BASELINE_HELD)

    def test_a_bizhawk_reconnect_does_not_release_it_either(self) -> None:
        # _reset_state runs from validate_rom, so this fires on every
        # reconnect - a Lua reload or a savestate load is enough.
        ctx, save = FakeServer(), progressed_save()
        client = MMX6Client()
        poll(client, ctx, save)
        self.assertTrue(client.baseline_held)

        client._reset_state()
        self.assertEqual(client.baseline_state, BASELINE_UNKNOWN)
        self.assertEqual(poll(client, ctx, save), set())
        self.assertEqual(client.baseline_state, BASELINE_HELD)

    def test_the_held_set_itself_is_what_comes_back(self) -> None:
        # Not just "something was held" - the same locations, read back from
        # storage rather than re-derived from a save that may have moved on.
        ctx, save = FakeServer(), progressed_save()
        first = MMX6Client()
        poll(first, ctx, save)
        self.assertTrue(first.baseline_held)

        second = MMX6Client()
        poll(second, ctx, save)
        self.assertEqual(second.baseline_held, first.baseline_held)


class TestNothingIsSentBeforeTheAnswerArrives(unittest.TestCase):
    def test_an_unanswered_get_holds_everything(self) -> None:
        # The decision cannot be taken back - a released item is somebody
        # else's - so "we have not heard yet" must not read as "nothing held".
        ctx, save = FakeServer(answer=False), progressed_save()
        client = MMX6Client()
        self.assertEqual(poll(client, ctx, save), set())
        self.assertEqual(client.baseline_state, BASELINE_UNKNOWN)

    def test_it_resolves_once_the_reply_lands(self) -> None:
        ctx, save = FakeServer(answer=False), progressed_save()
        client = MMX6Client()
        poll(client, ctx, save)
        ctx.stored_data[ctx.key] = None          # the Get reply arrives
        poll(client, ctx, save)
        self.assertEqual(client.baseline_state, BASELINE_HELD)

    def test_a_slot_that_is_not_connected_yet_is_not_stored(self) -> None:
        ctx, save = FakeServer(), progressed_save()
        ctx.slot = None
        client = MMX6Client()
        self.assertEqual(poll(client, ctx, save), set())
        self.assertEqual(ctx.stored_data, {})


class TestTheRelease(unittest.TestCase):
    def test_a_check_outside_the_baseline_releases_it(self) -> None:
        ctx, save = FakeServer(), progressed_save()
        client = MMX6Client()
        poll(client, ctx, save)
        held = set(client.baseline_held)     # capture BEFORE the release -
        self.assertTrue(held)                # afterwards it is empty, and
        #                                      "empty <= anything" is no test

        save[OFF_TANKS] = names.TANK_BIT[names.YAMMARK]   # collected live
        sendable = poll(client, ctx, save)
        self.assertTrue(held <= sendable,
                        "the held locations were not sent on release")
        self.assertIn(location_table[names.tank_location(names.YAMMARK)],
                      sendable)
        self.assertEqual(client.baseline_state, BASELINE_CLEAR)
        self.assertFalse(client.baseline_held)

    def test_the_release_is_recorded_server_side(self) -> None:
        # Otherwise the next connect re-derives it and we are back to a
        # decision that only ever lived in one process.
        ctx, save = FakeServer(), progressed_save()
        client = MMX6Client()
        poll(client, ctx, save)
        save[OFF_TANKS] = names.TANK_BIT[names.YAMMARK]
        poll(client, ctx, save)
        self.assertEqual(ctx.stored_data[ctx.key], [])

    def test_a_released_slot_stays_released_across_a_restart(self) -> None:
        ctx, save = FakeServer(), progressed_save()
        client = MMX6Client()
        poll(client, ctx, save)
        save[OFF_TANKS] = names.TANK_BIT[names.YAMMARK]
        poll(client, ctx, save)

        restarted = MMX6Client()
        sendable = poll(restarted, ctx, save)
        self.assertEqual(restarted.baseline_state, BASELINE_CLEAR)
        self.assertTrue(sendable, "a resolved slot stopped sending anything")


class TestTheOrdinaryCase(unittest.TestCase):
    def test_a_fresh_save_holds_nothing_and_says_so(self) -> None:
        # The overwhelmingly common case: new seed, new save. Recording the
        # answer means later connects do not re-litigate it.
        ctx = FakeServer()
        client = MMX6Client()
        poll(client, ctx, bytes(SAVE_LEN))
        self.assertEqual(client.baseline_state, BASELINE_CLEAR)
        self.assertEqual(ctx.stored_data[ctx.key], [])

    def test_first_contact_writes_the_held_list(self) -> None:
        ctx, save = FakeServer(), progressed_save()
        client = MMX6Client()
        poll(client, ctx, save)
        self.assertEqual(sorted(client.baseline_held),
                         ctx.stored_data[ctx.key])
        self.assertTrue(ctx.stored_data[ctx.key])

    def test_a_slot_with_history_holds_nothing(self) -> None:
        # The server already knows this slot checked something, so the save
        # belongs to this seed and anything extra was collected offline.
        ctx, save = FakeServer(), progressed_save()
        ctx.checked_locations = {location_table[names.INTRO_CLEAR]}
        client = MMX6Client()
        sendable = poll(client, ctx, save)
        self.assertEqual(client.baseline_state, BASELINE_CLEAR)
        self.assertIn(location_table[names.boss_location(names.YAMMARK)],
                      sendable)


if __name__ == "__main__":
    unittest.main()
