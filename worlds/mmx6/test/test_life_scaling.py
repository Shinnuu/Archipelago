"""`starting_hp` and `heart_tank_value` tests.

Both are one number each. The client writes the life gauge ABSOLUTELY:
starting life plus step per upgrade received, in either direction, so the
vanilla "+2 per pickup" never enters into it. A new save starts at the seed's
value through one disc edit - the immediate in the new-game initialiser at
EXE 0x8001E098 - because the client only ever sees a save after the game has
written its own 32 into it.

Things that can go wrong, and each has tests below:

  * the 127 ceiling. The game reads the gauge as a signed byte and keeps
    current HP in seven bits, so 128 and up would go negative. Nothing may
    ever write past 127.
  * the disc edit landing on the wrong word, or on the right word for the
    wrong value.
  * junk slot data falling to the FLOOR rather than the default - with a
    floor of 1 that would be a one-hit-death run nobody asked for.
  * the shared step. `GAUGE_STEP` was used by the life gauge AND the weapon
    gauge, so parameterising it naively would have silently rescaled Energy
    Ups too.
  * slot data from the wrong version. A world older than this client sends no
    value; a newer one could send anything. Both must land on something sane
    rather than writing a nonsense byte into the save.
"""
import os
import unittest

from .. import names
from .. import disc
from ..client import (GAUGE_STEP, LIFE_GAUGE_BASE, LIFE_GAUGE_HARD_MAX,
                      LIFE_GAUGE_MAX, OFF_LIFE_GAUGE, OFF_LIFE_GAUGE_ZERO,
                      OFF_WEAPON_GAUGE, OFF_WEAPON_GAUGE_ZERO, SAVE_BASE,
                      SAVE_LEN, WEAPON_GAUGE_BASE, MMX6Client, _clamp)
from ..options import HeartTankValue, StartingHp
from . import MMX6TestBase

ROM = r"C:\Users\Ivor\Documents\Game Modding\Games\Megaman X6\Megaman X6.bin"
have_rom = os.path.exists(ROM)


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


def life(items=(), slot_data=None, current: int = LIFE_GAUGE_BASE) -> int:
    """The life gauge value _grants would write, for X and Zero alike.

    `current` is what the save already holds - the vanilla 32 unless a test
    is asking what happens to a save that is above or below the target.
    """
    client = MMX6Client()
    save = blank_save()
    save[OFF_LIFE_GAUGE] = save[OFF_LIFE_GAUGE_ZERO] = current
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

    def test_upgrades_carry_past_the_vanilla_maximum(self) -> None:
        # 64 was vanilla's ceiling, not the game's. Starting at 64 with eight
        # tanks is 80, and the game holds it.
        got = life([names.HEART_TANK] * 8, {"starting_hp": 64})
        self.assertEqual(got, 80)

    def test_nothing_is_ever_written_past_the_hard_maximum(self) -> None:
        # Signed byte on every read, seven-bit current HP: 128 goes negative.
        got = life([names.HEART_TANK] * 16, {"starting_hp": 120,
                                               "heart_tank_value": 16})
        self.assertEqual(got, LIFE_GAUGE_HARD_MAX)
        self.assertEqual(life(slot_data={"starting_hp": 127}),
                         LIFE_GAUGE_HARD_MAX)

    def test_below_vanilla_is_written(self) -> None:
        # The whole point. The disc starts a new save here; the client keeps
        # an existing one here.
        self.assertEqual(life(slot_data={"starting_hp": 8}), 8)
        self.assertEqual(life(slot_data={"starting_hp": 1}), 1)

    def test_an_existing_save_is_moved_down_as_well_as_up(self) -> None:
        # A save made at vanilla 32 (or that collected tanks whose items went
        # elsewhere) is brought to what the seed says, not left where it is.
        self.assertEqual(life(slot_data={"starting_hp": 8}, current=40), 8)
        self.assertEqual(life(slot_data={"starting_hp": 100}, current=40), 100)

    def test_a_vanilla_pickups_plus_two_is_taken_back(self) -> None:
        # Walking over a Heart Tank raised the save to 34 locally. No item has
        # arrived, so the gauge is what the seed says: 32.
        self.assertEqual(life(current=LIFE_GAUGE_BASE + 2), LIFE_GAUGE_BASE)


class TestHeartTankValue(unittest.TestCase):
    def test_a_bigger_step_is_worth_more_per_upgrade(self) -> None:
        self.assertEqual(life([names.HEART_TANK], {"heart_tank_value": 8}),
                         LIFE_GAUGE_BASE + 8)

    def test_life_ups_use_the_same_step_as_heart_tanks(self) -> None:
        # The game does not distinguish them and neither does the save, so one
        # setting has to cover both or the two would drift apart.
        self.assertEqual(life([names.LIFE_UP], {"heart_tank_value": 8}),
                         life([names.HEART_TANK], {"heart_tank_value": 8}))

    def test_a_bigger_step_reaches_the_hard_cap_and_stops(self) -> None:
        self.assertEqual(life([names.HEART_TANK] * 4,
                              {"heart_tank_value": 8}), 64)
        self.assertEqual(life([names.HEART_TANK] * 16,
                              {"heart_tank_value": 8}), LIFE_GAUGE_HARD_MAX)

    def test_zero_makes_upgrades_worthless(self) -> None:
        self.assertEqual(life([names.HEART_TANK] * 16,
                              {"heart_tank_value": 0}), LIFE_GAUGE_BASE)

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

    def test_junk_falls_to_the_default_not_the_floor(self) -> None:
        # The floor is 1. A corrupt value must read as vanilla, not as a
        # one-hit-death run.
        self.assertEqual(_clamp("wibble", 1, 127, default=32), 32)
        self.assertEqual(_clamp(None, 0, 127, default=2), 2)

    def test_a_junk_value_never_reaches_the_save(self) -> None:
        got = life([names.HEART_TANK],
                   slot_data={"starting_hp": "wibble",
                              "heart_tank_value": None})
        self.assertEqual(got, LIFE_GAUGE_BASE + GAUGE_STEP)

    def test_out_of_range_is_clamped_to_the_games_limits(self) -> None:
        self.assertEqual(life(slot_data={"starting_hp": 0}), 1)
        self.assertEqual(life(slot_data={"starting_hp": 999}),
                         LIFE_GAUGE_HARD_MAX)


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
                self.assertGreaterEqual(hp, StartingHp.range_start)
                self.assertLessEqual(hp, StartingHp.range_end)
                self.assertGreaterEqual(step, HeartTankValue.range_start)
                self.assertLessEqual(step, HeartTankValue.range_end)
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

    def test_the_ranges_are_the_games(self) -> None:
        self.assertEqual((StartingHp.range_start, StartingHp.range_end),
                         (1, LIFE_GAUGE_HARD_MAX))
        self.assertEqual(HeartTankValue.range_start, 0)


# ---- the disc edit --------------------------------------------------------

def _seed_edits(world) -> dict:
    """{(addr, region): patched hex} the seed's own .apmmx6 would carry."""
    import json

    from ..Rom import MMX6ProcedurePatch, patch_rom

    written = {}

    class _Capture(MMX6ProcedurePatch):
        def write_file(self, name, data):     # noqa: D102
            written[name] = data

    patch_rom(world, _Capture(player=world.player, player_name="P"))
    return {(e["addr"], e["region"]): e["hex"]
            for e in json.loads(written["seed_edits.json"].decode("utf-8"))}


class TestTheDiscEdit(unittest.TestCase):
    def test_vanilla_is_no_edit_at_all(self) -> None:
        self.assertEqual(disc.starting_life_edits(32), [])

    def test_one_word_and_only_the_immediate_changes(self) -> None:
        for value in (1, 8, 64, 100, 127):
            (label, where, region, van, pat), = disc.starting_life_edits(value)
            self.assertEqual(where, disc.STARTING_LIFE_SITE)
            self.assertEqual(region, disc.REGION_EXE)
            self.assertEqual(len(van), 4)
            a = int.from_bytes(van, "little")
            b = int.from_bytes(pat, "little")
            self.assertEqual(a, 0x24030020, "vanilla is addiu v1, zero, 0x20")
            self.assertEqual(a >> 16, b >> 16, "opcode/registers changed")
            self.assertEqual(b & 0xFFFF, value)

    def test_the_games_limits_are_refused(self) -> None:
        for value in (0, 128, 255, -1):
            with self.assertRaises(ValueError):
                disc.starting_life_edits(value)

    def test_it_overlaps_no_other_edit(self) -> None:
        (_l, w, r, van, _p), = disc.starting_life_edits(1)
        span = {disc.addr_to_disc(w + i, r) for i in range(4)}
        for group in disc.QOL_EDITS.values():
            for _l2, w2, r2, v2, _p2 in group:
                for i in range(len(v2)):
                    self.assertNotIn(disc.addr_to_disc(w2 + i, r2), span)
        for _l2, w2, r2, v2, _p2 in disc.ENDGAME_GATE_EDITS:
            for i in range(len(v2)):
                self.assertNotIn(disc.addr_to_disc(w2 + i, r2), span)
        for w2, payload, r2 in disc.BASE_EDITS:
            for i in range(len(payload)):
                self.assertNotIn(disc.addr_to_disc(w2 + i, r2), span)


@unittest.skipUnless(have_rom, "vanilla disc image not present")
class TestTheDiscEditAgainstTheDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(ROM, "rb") as fh:
            cls.rom = fh.read()

    def test_the_site_holds_the_initialiser(self) -> None:
        # addiu v1,zero,0x20 / sb v0,0x39(a1) / addiu v0,zero,0x30 /
        # sb v1,0x5B(a1) / sb v1,0x5C(a1): the word we patch feeds BOTH
        # characters' life bytes, and nothing between reassigns v1.
        off = disc.addr_to_disc(disc.STARTING_LIFE_SITE, disc.REGION_EXE)
        words = [int.from_bytes(self.rom[off + 4 * i:off + 4 * i + 4], "little")
                 for i in range(5)]
        self.assertEqual(words, [0x24030020, 0xA0A20039, 0x24020030,
                                 0xA0A3005B, 0xA0A3005C])

    def test_the_patched_image_changes_exactly_that_word(self) -> None:
        extra = [(w, p, r, v) for _l, w, r, v, p in disc.starting_life_edits(8)]
        img = disc.apply_basepatch(self.rom, extra)
        off = disc.addr_to_disc(disc.STARTING_LIFE_SITE, disc.REGION_EXE)
        self.assertEqual(int.from_bytes(img[off:off + 4], "little"), 0x24030008)
        self.assertEqual(img[off + 4:off + 20], self.rom[off + 4:off + 20])


class TestTheSeedCarriesIt(MMX6TestBase):
    options = {"starting_hp": 8}

    def test_the_apmmx6_has_the_edit(self) -> None:
        carried = _seed_edits(self.world)
        self.assertEqual(
            carried.get((disc.STARTING_LIFE_SITE, disc.REGION_EXE)),
            (0x24030008).to_bytes(4, "little").hex())


class TestTheSeedDoesNotCarryItAtVanilla(MMX6TestBase):
    options = {"starting_hp": 32}

    def test_the_apmmx6_is_untouched(self) -> None:
        carried = _seed_edits(self.world)
        self.assertNotIn((disc.STARTING_LIFE_SITE, disc.REGION_EXE), carried)
