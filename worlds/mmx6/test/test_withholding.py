"""Withholding tests - ship plan item 23.

Policy 3 holds a granted armor part or tank back until its own location is
checked, because setting the bit early stops that pickup spawning and makes
the location uncollectable. The justification on record is that the delay is
"always bounded", since every capsule and tank is reachable.

Reachable is not visited. Seen live 2026-08-27: a W Tank earned at
`Secret Lab 2 - Clear` was withheld pending `Shield Sheldon - W Tank`, in a
run where Sheldon's stage was deliberately skipped. The hold was then
permanent and the player lost an item they had earned somewhere else.

After the goal nothing can be stranded, so the reason to withhold is gone.
These pin both halves: that the hold still works before the goal - it is
protecting a real location from becoming uncollectable - and that it stops
after it.
"""
import unittest

from .. import names
from ..client import (OFF_ARMOR_PARTS, OFF_TANKS, SAVE_BASE, SAVE_LEN,
                      MMX6Client)
from ..locations import location_table


class FakeItem:
    def __init__(self, name: str) -> None:
        self.name = name
        self.item = name


class FakeCtx:
    def __init__(self, items=(), checked=(), finished=False) -> None:
        self.items_received = [FakeItem(i) for i in items]
        self.item_names = type(
            "N", (), {"lookup_in_game": staticmethod(lambda i: i)})
        self.checked_locations = {location_table[c] for c in checked}
        self.slot_data = {}
        self.finished_game = finished


def written(client, ctx) -> dict:
    """{offset: value} for what _grants would write into a blank save."""
    return {addr - SAVE_BASE: data[0]
            for addr, data in client._grants(ctx, bytes(SAVE_LEN))}


# A part and a tank whose own locations are easy to name.
PART_STAGE = names.WOLFANG
PART = names.STAGE_ARMOR_PART[PART_STAGE]
PART_BIT = names.ARMOR_PART_BIT[PART]
TANK_STAGE = names.SHELDON
TANK = names.STAGE_TANK[TANK_STAGE]
TANK_BIT = names.TANK_BIT[TANK_STAGE]


class TestTheHoldStillWorksBeforeTheGoal(unittest.TestCase):
    """Do not let the item-23 fix quietly disable policy 3."""

    def test_an_armor_part_is_withheld_until_its_capsule_is_checked(self) -> None:
        w = written(MMX6Client(), FakeCtx([PART]))
        self.assertNotIn(OFF_ARMOR_PARTS, w,
                         "set the bit before the capsule was collected, which "
                         "stops the capsule spawning at all")

    def test_a_tank_is_withheld_until_its_own_location_is_checked(self) -> None:
        w = written(MMX6Client(), FakeCtx([TANK]))
        self.assertNotIn(OFF_TANKS, w)

    def test_checking_the_location_releases_it(self) -> None:
        w = written(MMX6Client(),
                    FakeCtx([PART], checked=[names.capsule_location(PART_STAGE)]))
        self.assertEqual(w.get(OFF_ARMOR_PARTS), PART_BIT)


class TestTheHoldStopsAtTheGoal(unittest.TestCase):
    """THE BUG. A skipped stage made the hold permanent."""

    def test_a_finished_seed_applies_a_withheld_armor_part(self) -> None:
        w = written(MMX6Client(), FakeCtx([PART], finished=True))
        self.assertEqual(w.get(OFF_ARMOR_PARTS), PART_BIT)

    def test_a_finished_seed_applies_a_withheld_tank(self) -> None:
        # The live case: a W Tank earned at Secret Lab 2, held against a
        # stage that was never going to be played.
        w = written(MMX6Client(), FakeCtx([TANK], finished=True))
        self.assertEqual(w.get(OFF_TANKS), TANK_BIT)

    def test_the_clients_own_victory_latch_counts_too(self) -> None:
        # `finished_game` is not restored from the server on a reconnect, so
        # the client's own latch has to be honoured in the session that sent
        # the goal.
        c = MMX6Client()
        c.victory_sent = True
        self.assertEqual(written(c, FakeCtx([TANK])).get(OFF_TANKS), TANK_BIT)

    def test_everything_held_is_released_at_once(self) -> None:
        # A finished seed should not dribble items out one location at a time.
        parts = list(names.STAGE_ARMOR_PART.values())
        w = written(MMX6Client(), FakeCtx(parts, finished=True))
        expected = 0
        for part in parts:
            expected |= names.ARMOR_PART_BIT[part]
        self.assertEqual(w.get(OFF_ARMOR_PARTS), expected)


if __name__ == "__main__":
    unittest.main()
