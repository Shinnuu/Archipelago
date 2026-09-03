"""`starting_hp` and `heart_tank_value` tests.

Both are one number each, and both work because AP grants are ABSOLUTE: the
client recomputes the life gauge from the items received rather than adding to
whatever is there, so the vanilla "+2 per pickup" never enters into it. No
disc patch is involved.

Three things can go wrong, and each has tests below:

  * the 64 ceiling. The life bar is DRAWN from this byte, and what it does
    above vanilla's maximum has never been tested live. So a larger step must
    reach 64 sooner, never overshoot it.
  * the shared step. `GAUGE_STEP` was used by the life gauge AND the weapon
    gauge, so parameterising it naively would have silently rescaled Energy
    Ups too.
  * slot data from the wrong version. A world older than this client sends no
    value; a newer one could send anything. Both must land on something sane
    rather than writing a nonsense byte into the save.
"""
import unittest

from .. import names
from ..client import (GAUGE_STEP, LIFE_GAUGE_BASE, LIFE_GAUGE_MAX,
                      OFF_LIFE_GAUGE, OFF_LIFE_GAUGE_ZERO, OFF_WEAPON_GAUGE,
                      OFF_WEAPON_GAUGE_ZERO, SAVE_BASE, SAVE_LEN,
                      WEAPON_GAUGE_BASE, MMX6Client, _clamp)
from . import MMX6TestBase


class FakeItem:
    def __init__(self, name: str) -> None:
        self.name = name
        self.item = name


class FakeCtx:
    def __init__(self, items=(), slot_data=None) -> None:
        self.items_received = [FakeItem(i) for i in items]
        self.item_names = type(
            "N", (), {"lookup_in_game": staticmethod(lambda i: i)})
        self.checked_locations = set()
        self.slot_data = slot_data or {}
        self.finished_game = False


def blank_save() -> bytearray:
    save = bytearray(SAVE_LEN)
    save[OFF_LIFE_GAUGE] = LIFE_GAUGE_BASE
    save[OFF_LIFE_GAUGE_ZERO] = LIFE_GAUGE_BASE
    save[OFF_WEAPON_GAUGE] = WEAPON_GAUGE_BASE
    save[OFF_WEAPON_GAUGE_ZERO] = WEAPON_GAUGE_BASE
    return save


def life(items=(), slot_data=None) -> int:
    """The life gauge value _grants would write, for X and Zero alike."""
    client = MMX6Client()
    save = blank_save()
    out = {addr - SAVE_BASE: data[0]
           for addr, data in client._grants(FakeCtx(items, slot_data),
                                            bytes(save))}
    x, zero = out.get(OFF_LIFE_GAUGE), out.get(OFF_LIFE_GAUGE_ZERO)
    assert x == zero, "the two characters' gauges disagree"
    return x if x is not None else save[OFF_LIFE_GAUGE]


class TestDefaultsAreVanilla(unittest.TestCase):
    def test_no_slot_data_is_the_vanilla_floor(self) -> None:
        # An older world sends neither key. It must behave exactly as before.
        self.assertEqual(life(), LIFE_GAUGE_BASE)

    def test_no_slot_data_keeps_the_vanilla_step(self) -> None:
        self.assertEqual(life([names.HEART_TANK]),
                         LIFE_GAUGE_BASE + GAUGE_STEP)

    def test_sixteen_vanilla_upgrades_still_reach_exactly_the_maximum(self) -> None:
        # 8 Heart Tanks + 8 Life Ups at +2 is what takes a vanilla run 32 -> 64.
        items = [names.HEART_TANK] * 8 + [names.LIFE_UP] * 8
        self.assertEqual(life(items), LIFE_GAUGE_MAX)


class TestStartingHp(unittest.TestCase):
    def test_it_moves_the_floor(self) -> None:
        self.assertEqual(life(slot_data={"starting_hp": 48}), 48)

    def test_upgrades_still_stack_on_top_of_it(self) -> None:
        self.assertEqual(life([names.HEART_TANK], {"starting_hp": 48}),
                         48 + GAUGE_STEP)

    def test_it_never_exceeds_the_drawable_maximum(self) -> None:
        got = life([names.HEART_TANK] * 8, {"starting_hp": 64})
        self.assertEqual(got, LIFE_GAUGE_MAX)

    def test_below_vanilla_is_refused_rather_than_written(self) -> None:
        # The client never lowers a gauge, so a value under the game's own
        # starting life could not be enforced anyway - clamping it here means
        # the save never receives a byte the game would immediately beat.
        self.assertEqual(life(slot_data={"starting_hp": 8}), LIFE_GAUGE_BASE)


class TestHeartTankValue(unittest.TestCase):
    def test_a_bigger_step_is_worth_more_per_upgrade(self) -> None:
        self.assertEqual(life([names.HEART_TANK], {"heart_tank_value": 8}),
                         LIFE_GAUGE_BASE + 8)

    def test_life_ups_use_the_same_step_as_heart_tanks(self) -> None:
        # The game does not distinguish them and neither does the save, so one
        # setting has to cover both or the two would drift apart.
        self.assertEqual(life([names.LIFE_UP], {"heart_tank_value": 8}),
                         life([names.HEART_TANK], {"heart_tank_value": 8}))

    def test_a_bigger_step_reaches_the_cap_sooner_and_stops(self) -> None:
        self.assertEqual(life([names.HEART_TANK] * 4,
                              {"heart_tank_value": 8}), LIFE_GAUGE_MAX)
        self.assertEqual(life([names.HEART_TANK] * 16,
                              {"heart_tank_value": 8}), LIFE_GAUGE_MAX)

    def test_below_vanilla_is_refused(self) -> None:
        self.assertEqual(life([names.HEART_TANK], {"heart_tank_value": 0}),
                         LIFE_GAUGE_BASE + GAUGE_STEP)

    def test_the_weapon_gauge_is_left_alone(self) -> None:
        # GAUGE_STEP was shared between the two gauges. If this option ever
        # starts rescaling Energy Ups, this is what catches it.
        client = MMX6Client()
        out = {addr - SAVE_BASE: data[0]
               for addr, data in client._grants(
                   FakeCtx([names.ENERGY_UP], {"heart_tank_value": 16}),
                   bytes(blank_save()))}
        for off in (OFF_WEAPON_GAUGE, OFF_WEAPON_GAUGE_ZERO):
            self.assertEqual(out.get(off, WEAPON_GAUGE_BASE),
                             WEAPON_GAUGE_BASE + GAUGE_STEP)


class TestSlotDataIsNotTrusted(unittest.TestCase):
    """A value can arrive from a world version this client has never seen."""

    def test_clamp_holds_the_range(self) -> None:
        self.assertEqual(_clamp(999, 32, 64), 64)
        self.assertEqual(_clamp(-5, 32, 64), 32)
        self.assertEqual(_clamp(40, 32, 64), 40)

    def test_junk_falls_back_to_the_floor(self) -> None:
        self.assertEqual(_clamp(None, 32, 64), 32)
        self.assertEqual(_clamp("wibble", 32, 64), 32)

    def test_a_junk_value_never_reaches_the_save(self) -> None:
        got = life(slot_data={"starting_hp": "wibble",
                              "heart_tank_value": None})
        self.assertEqual(got, LIFE_GAUGE_BASE)


class TestSlotData(MMX6TestBase):
    options = {"starting_hp": 48, "heart_tank_value": 6}

    def test_both_values_reach_the_client(self) -> None:
        data = self.world.fill_slot_data()
        self.assertEqual(data["starting_hp"], 48)
        self.assertEqual(data["heart_tank_value"], 6)


class TestRollIsRangeSafe(MMX6TestBase):
    """`randomize_options` does not roll these - but it must not corrupt one.

    The roller picked from `type(option).options` for a Choice and fell
    through to [0, 1] for anything else. Toggle has `.options`, so that
    fallback was only ever reachable by a Range - meaning a Range added to
    RANDOMIZED_OPTIONS would have been rolled to 0 or 1, outside its own
    declared range, with only the client's clamp between that and the save.

    These two are the first Range options in this world, so the trap is new.
    Pinned here rather than left for whoever adds the next one.
    """
    options = {}

    def test_a_range_rolls_inside_its_own_declared_range(self) -> None:
        import worlds.mmx6 as world_mod
        original = world_mod.RANDOMIZED_OPTIONS
        world_mod.RANDOMIZED_OPTIONS = ("starting_hp", "heart_tank_value")
        try:
            seen_hp = set()
            for _ in range(60):
                self.world._roll_options()
                hp = self.world.options.starting_hp.value
                step = self.world.options.heart_tank_value.value
                self.assertGreaterEqual(hp, 32)
                self.assertLessEqual(hp, LIFE_GAUGE_MAX)
                self.assertGreaterEqual(step, GAUGE_STEP)
                self.assertLessEqual(step, 16)
                seen_hp.add(hp)
        finally:
            world_mod.RANDOMIZED_OPTIONS = original
        # The old code produced only 0 and 1. Anything in range proves the
        # Range branch is the one being taken, not the toggle fallback.
        self.assertFalse(seen_hp <= {0, 1},
                         "the roller is still using the 0/1 fallback")


class TestSlotDataDefaults(MMX6TestBase):
    options = {}

    def test_the_defaults_are_vanilla(self) -> None:
        data = self.world.fill_slot_data()
        self.assertEqual(data["starting_hp"], LIFE_GAUGE_BASE)
        self.assertEqual(data["heart_tank_value"], GAUGE_STEP)
