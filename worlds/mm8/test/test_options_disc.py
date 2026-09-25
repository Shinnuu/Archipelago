"""The option-driven disc edits: text skip, intro videos, exit anytime,
weapon damage and boss HP (parity plan, build step 1).

Offline tests check the shapes and the invariants the research rests on; the
dump-gated ones check every declared vanilla word against the real disc and
apply everything together, so two options can never write the same byte.
"""
import io
import random
import unittest
from types import SimpleNamespace

from BaseClasses import ItemClassification

from . import MM8TestBase
from .. import Rom, damage, disc, mips, names, options
from .r3000 import R3000
from .test_disc import TRACK1, have_dump

ALL_QOL = ("text_skip", "skip_intro_videos", "exit_stage_anytime")


class TestExitGuard(unittest.TestCase):
    """EXIT_GUARD, executed: a real clear continues into the clear routine; an
    Exit returns into its tail, skipping every grant and progression write."""

    LEAF = 0x8010BBB8          # the call the hook displaced
    TAIL = 0x80101438          # stage clear's save prompt + router

    def run_guard(self, how_it_ended: int) -> R3000:
        at = disc.routine_addresses()["exit guard"]
        m = R3000()
        m.load_code(at, mips.assemble(disc.EXIT_GUARD, at))
        # The leaf marks that it ran and returns through ra, as the real one does.
        m.load_code(self.LEAF, mips.assemble("ori t7, zero, 1\njr ra\nnop", self.LEAF))
        # The tail marks that it was reached, then leaves the run.
        m.load_code(self.TAIL, mips.assemble(
            f"lui t9, {R3000.RETURN >> 16:#x}\njr t9\nori t8, zero, 1", self.TAIL))
        m.write(0x801B2995, how_it_ended, 1)
        m.run(at)
        return m

    def test_a_real_clear_is_untouched(self):
        for value in (1, 0x80):
            m = self.run_guard(value)
            self.assertEqual(m.r[15], 1, "the displaced call still runs")    # t7
            self.assertEqual(m.r[24], 0, "the tail is not jumped to")       # t8

    def test_an_exit_skips_to_the_tail(self):
        m = self.run_guard(2)
        self.assertEqual(m.r[15], 1, "the displaced call still runs")
        self.assertEqual(m.r[24], 1, "an Exit returns into the tail")

    def test_the_guard_is_in_the_cave_and_the_hook_calls_it(self):
        at = disc.routine_addresses()["exit guard"]
        self.assertTrue(disc.CAVE_START <= at < disc.CAVE_END)
        hook = [e for e in disc.exit_edits() if e[1] == disc.EXIT_HOOK][0]
        self.assertEqual(int.from_bytes(hook[4], "little"), mips.word(f"jal {at:#x}", disc.EXIT_HOOK))


class TestQolShapes(unittest.TestCase):
    def test_features_are_independent_and_known(self):
        self.assertEqual(disc.qol_edits([]), [])
        with self.assertRaises(ValueError):
            disc.qol_edits(["no_such_option"])
        everything = disc.qol_edits(ALL_QOL)
        self.assertEqual(len(everything), sum(len(disc.qol_edits([f])) for f in ALL_QOL))

    def test_intro_exit_is_denied_on_every_disc(self):
        self.assertIn(disc.INTRO_EXIT_DENIED, disc.BASE_EDITS)
        # `beqz v1, 0x80113628` - the handler's own buzzer.
        self.assertEqual(int.from_bytes(disc.INTRO_EXIT_DENIED[4], "little"),
                         mips.word("beq v1, zero, 0x80113628", disc.INTRO_EXIT_DENIED[1]))


class TestWeaponDamage(unittest.TestCase):
    def tables(self, mode: int, seed: int) -> tuple[bytes, dict[str, float]]:
        return damage.weapon_damage_tables(mode, random.Random(seed))

    def test_region_shape(self):
        self.assertEqual(len(damage.DAMAGE_TABLES_VANILLA),
                         damage.DAMAGE_TABLE_COUNT * damage.DAMAGE_TABLE_STRIDE)
        for t in range(damage.DAMAGE_TABLE_COUNT):
            self.assertEqual(damage.DAMAGE_TABLES_VANILLA[t * 20 + 19], 0, f"table {t} terminator")

    def test_what_each_weapon_can_hurt_never_changes(self):
        """Only cells already in 1..0x7E move, and they stay in 1..0x7E - so
        no-effect, deflect, pass-through, harmless-hit and kill cells are the
        same, and so is every "which weapon breaks what" fact."""
        vanilla = damage.DAMAGE_TABLES_VANILLA
        for mode in damage.DAMAGE_RANGES:
            for seed in range(25):
                scaled, _ = self.tables(mode, seed)
                for i, (v, s) in enumerate(zip(vanilla, scaled)):
                    if damage.DAMAGE_MIN <= v <= damage.DAMAGE_MAX:
                        self.assertTrue(damage.DAMAGE_MIN <= s <= damage.DAMAGE_MAX, (mode, seed, i))
                    else:
                        self.assertEqual(s, v, (mode, seed, i))

    def test_a_family_shares_one_roll_and_keeps_its_order(self):
        for seed in range(25):
            scaled, factors = self.tables(4, seed)
            self.assertEqual(set(factors), set(damage.WEAPON_FAMILIES))
            for t in range(damage.DAMAGE_TABLE_COUNT):
                row, van = scaled[t * 20:t * 20 + 19], damage.DAMAGE_TABLES_VANILLA[t * 20:t * 20 + 19]
                plain, half, full = row[0], row[1], row[2]
                if all(1 <= van[i] <= 0x7E for i in (0, 1, 2)) and van[0] <= van[1] <= van[2]:
                    self.assertLessEqual(plain, half, (seed, t))
                    self.assertLessEqual(half, full, (seed, t))

    def test_the_enemy_hitbox_id_is_never_scaled(self):
        for seed in range(10):
            scaled, _ = self.tables(3, seed)
            for t in range(damage.DAMAGE_TABLE_COUNT):
                for dmg_id in damage.NEVER_SCALED_IDS:
                    self.assertEqual(scaled[t * 20 + dmg_id], damage.DAMAGE_TABLES_VANILLA[t * 20 + dmg_id])

    def test_every_player_damage_id_is_in_exactly_one_family(self):
        ids = [i for family in damage.WEAPON_FAMILIES.values() for i in family]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids + list(damage.NEVER_SCALED_IDS)), list(range(damage.DAMAGE_IDS)))


class TestBossHp(unittest.TestCase):
    def test_each_site_moves_to_the_roll(self):
        factors = {boss: 1.5 for boss in damage.BOSS_HP_SITES}      # 40 -> 60
        edits = {e[1]: int.from_bytes(e[4], "little") for e in damage.boss_hp_edits(factors)}
        for boss, sites in damage.BOSS_HP_SITES.items():
            for region, where, role, vanilla in sites:
                expected = {"cmpN": 60, "cmpN1": 61, "store": 60, "gate": 60}[role]
                self.assertEqual(edits[where] & 0xFFFF, expected, (boss, hex(where)))
                self.assertEqual(edits[where] & 0xFFFF0000, vanilla & 0xFFFF0000, "same instruction")

    def test_a_gate_always_equals_its_fill(self):
        """Grenade Man's fight starts only at hp == the fill target; a gate
        left at 40 under any other roll would never open."""
        for factor in (0.25, 0.7, 1.0, 2.5, 4.0):
            edits = damage.boss_hp_edits({"Grenade Man": factor})
            stores = {int.from_bytes(e[4], "little") & 0xFFFF for e in edits if "store" in e[0] or "gate" in e[0]}
            self.assertEqual(len(stores), 1, factor)

    def test_bounds(self):
        self.assertEqual(damage.scaled_hp(40, 0.001), 1)       # never 0: unhittable
        self.assertEqual(damage.scaled_hp(40, 10), 127)        # the signed survival test
        for mode, (low, high) in damage.BOSS_HP_RANGES.items():
            self.assertGreaterEqual(damage.scaled_hp(32, low), 1)

    def test_each_site_is_declared_once(self):
        wheres = [(region, where) for sites in damage.BOSS_HP_SITES.values() for region, where, _r, _v in sites]
        self.assertEqual(len(wheres), len(set(wheres)))


class TestBossDamage(unittest.TestCase):
    def test_one_multiplier_moves_a_boss_together(self):
        edits = damage.boss_damage_edits({"Grenade Man": 2.0})
        self.assertEqual(len(edits), len(damage.BOSS_DAMAGE_SITES["Grenade Man"]))
        for (_l, _w, _r, vanilla, payload), (_rg, _wh, kind, value) in zip(
                edits, damage.BOSS_DAMAGE_SITES["Grenade Man"]):
            if kind == "ori":
                self.assertEqual(int.from_bytes(payload, "little") & 0xFFFF, min(0x7E, 2 * (value & 0xFFFF)))
                self.assertEqual(payload[2:], vanilla[2:], "same instruction, same register")
            else:
                self.assertEqual(payload[0], min(0x7E, 2 * value))

    def test_never_zero_never_a_kill(self):
        for factor in (0.01, 100.0):
            for _l, _w, _r, _v, payload in damage.boss_damage_edits({b: factor for b in damage.BOSS_DAMAGE_SITES}):
                n = payload[0] if len(payload) == 1 else int.from_bytes(payload, "little") & 0xFFFF
                self.assertTrue(damage.DAMAGE_MIN <= n <= damage.DAMAGE_MAX)

    def test_each_site_once_and_never_an_excluded_one(self):
        sites = [(r, w) for s in damage.BOSS_DAMAGE_SITES.values() for r, w, _k, _v in s]
        self.assertEqual(len(sites), len(set(sites)))
        excluded = {(r, w) for r, w, _k, _why in damage.BOSS_DAMAGE_EXCLUDED}
        self.assertFalse(set(sites) & excluded)

    def test_it_never_touches_the_boss_hp_bytes(self):
        """The descriptor's damage byte (+2) and HP byte (+1) sit side by side."""
        hp = {w for w, _v in damage.MIDBOSS_HP.values()}
        dmg = {w for s in damage.BOSS_DAMAGE_SITES.values() for r, w, _k, _v in s if r == "exe"}
        self.assertFalse(hp & dmg)


MEGA = 0x8015E23C
HP = MEGA + 0x47


def fill_ticks(words: list[int], ticks: int) -> list[int]:
    """Run the teleport-in's fill block `ticks` times from HP 0, as the game
    does once a frame; the call after it (0x8010C0D4) becomes a return."""
    m = R3000()
    m.load_code(disc.MAX_LIFE_FILL, words)
    m.load_code(disc.MAX_LIFE_FILL + 4 * len(words), [mips.word("jr ra", 0x8010C0D4), 0])
    seen = []
    for _ in range(ticks):
        m.r[16], m.r[31] = MEGA, R3000.RETURN
        m.run(disc.MAX_LIFE_FILL)
        seen.append(m.rb(HP))
    return seen


class TestMaxLife(unittest.TestCase):
    """max_life (X5's starting_hp): the teleport-in fill and the five
    immediates, research 2026-09-25_max-life-research.md."""

    def test_vanilla_is_no_edit_and_the_bounds_hold(self):
        self.assertEqual(disc.max_life_edits(disc.PLAYER_MAX_HP), [])
        for bad in (0, 128):
            with self.assertRaises(ValueError):
                disc.max_life_edits(bad)
        lo, hi = disc.MAX_LIFE_RANGE
        self.assertEqual((lo, hi), (options.MaxLife.range_start, options.MaxLife.range_end))

    def test_the_vanilla_fill_stops_at_40_and_is_the_control(self):
        """The unpatched block, executed: +1 a frame to 40 - so it alone
        could never fill past the 60 frames the teleport-in lasts."""
        seen = fill_ticks(list(disc.MAX_LIFE_FILL_VANILLA), 60)
        self.assertEqual(seen[:3] + [seen[38], seen[39], seen[-1]], [1, 2, 3, 39, 40, 40])

    def test_every_max_is_full_by_the_end_of_the_teleport_in(self):
        for n in range(disc.MAX_LIFE_RANGE[0], disc.MAX_LIFE_RANGE[1] + 1):
            words = [int.from_bytes(disc.max_life_edits(n)[0][4][i:i + 4], "little") for i in range(0, 36, 4)] \
                if n != disc.PLAYER_MAX_HP else list(disc.MAX_LIFE_FILL_VANILLA)
            seen = fill_ticks(words, disc.MAX_LIFE_FILL_FRAMES)
            self.assertEqual(seen[-1], n, n)
            self.assertLessEqual(max(seen), n, n)

    def test_up_to_60_it_is_vanilla_s_own_curve(self):
        words = [int.from_bytes(disc.max_life_edits(60)[0][4][i:i + 4], "little") for i in range(0, 36, 4)]
        self.assertEqual(fill_ticks(words, 60), list(range(1, 61)))

    def test_every_immediate_moves_to_the_max(self):
        for n in (1, 39, 41, 80, 127):
            for label, where, _region, vanilla, payload in disc.max_life_edits(n)[1:]:
                v, p = int.from_bytes(vanilla, "little"), int.from_bytes(payload, "little")
                self.assertEqual(v & 0xFFFF0000, p & 0xFFFF0000, label)        # same instruction
                self.assertEqual(p & 0xFFFF, n + (1 if "max+1" in label else 0), label)

    @unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
    def test_the_life_pickup_executed_off_the_disc(self):
        """0x80128FA4(obj, amount) with the patched immediates: it heals up to
        the new max and no further, and at full life it heals nothing. Its
        three calls out (the Exchanger's path, the sounds) are stubbed."""
        with open(TRACK1, "rb") as f:
            track1 = f.read()
        start, end = 0x80128FA4, 0x80129044
        for n, hp, amount, want in ((80, 79, 12, 80), (80, 70, 4, 74), (80, 80, 4, 80),
                                    (20, 19, 12, 20), (20, 20, 12, 20), (40, 39, 12, 40)):
            image = disc.apply_edits(track1, disc.max_life_edits(n))
            code = bytes(image[disc.addr_to_disc(a, disc.REGION_EXE)] for a in range(start, end))
            m = R3000()
            m.load_code(start, [int.from_bytes(code[i:i + 4], "little") for i in range(0, len(code), 4)])
            for stub in (0x80129044, 0x801291B0, 0x80129178):
                m.load_code(stub, [mips.word("jr ra", stub), 0])
            m.wb(HP, hp)
            m.r[5], m.r[29] = amount, 0x801FF000
            m.run(start)
            self.assertEqual(m.rb(HP), want, (n, hp, amount))


def fake_world(**options) -> SimpleNamespace:
    """What Rom.seed_edits reads off a world."""
    opts = {name: 0 for name in ALL_QOL + ("weapon_damage", "boss_hp_randomization", "pickupsanity",
                                           "boss_damage")}
    opts["max_life"] = disc.PLAYER_MAX_HP
    opts.update(options)
    rng = random.Random(8)
    tables, factors = damage.weapon_damage_tables(max(1, opts["weapon_damage"]), rng)
    return SimpleNamespace(
        options=SimpleNamespace(**opts),     # Rom.seed_edits only tests them for truth
        weapon_damage_tables=tables, weapon_damage_factors=factors,
        boss_hp_factors=damage.boss_hp_rolls(max(1, opts["boss_hp_randomization"]), rng),
        boss_damage_factors=damage.boss_damage_rolls(max(1, opts["boss_damage"]), rng))


class TestSeedEdits(unittest.TestCase):
    def test_nothing_on_means_no_edits(self):
        self.assertEqual(Rom.seed_edits(fake_world()), [])

    def test_round_trip(self):
        edits = Rom.seed_edits(fake_world(text_skip=1, skip_intro_videos=1, exit_stage_anytime=1,
                                          weapon_damage=4, boss_hp_randomization=4, boss_damage=4, pickupsanity=1,
                           max_life=80))
        self.assertEqual(Rom.decode_edits(Rom.encode_edits(edits)), edits)


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestOptionsAgainstTheDump(unittest.TestCase):
    track1: bytes

    @classmethod
    def setUpClass(cls):
        with open(TRACK1, "rb") as f:
            cls.track1 = f.read()

    def read(self, where: int, region: str, n: int) -> bytes:
        return bytes(self.track1[disc.addr_to_disc(where + i, region)] for i in range(n))

    def test_every_declared_vanilla_word_is_on_the_disc(self):
        world = fake_world(text_skip=1, skip_intro_videos=1, exit_stage_anytime=1,
                           weapon_damage=4, boss_hp_randomization=4, boss_damage=4, pickupsanity=1,
                           max_life=80)
        for label, where, region, vanilla, _payload in Rom.seed_edits(world) + [disc.INTRO_EXIT_DENIED]:
            self.assertEqual(self.read(where, region, len(vanilla)), vanilla, label)

    def test_the_damage_region_is_bounded_by_what_the_research_found(self):
        for where, expected in (damage.DAMAGE_TABLES_BEFORE, damage.DAMAGE_TABLES_AFTER):
            self.assertEqual(self.read(where, disc.REGION_EXE, len(expected)), expected, hex(where))
        # ...and the pointer table after it points at each table in turn.
        for i in range(damage.DAMAGE_TABLE_COUNT):
            ptr = int.from_bytes(self.read(0x801399BC + 4 * i, disc.REGION_EXE, 4), "little")
            self.assertEqual(ptr, damage.DAMAGE_TABLES + damage.DAMAGE_TABLE_STRIDE * i)

    def test_every_option_applies_together_with_the_base_patch(self):
        """apply_edits refuses overlapping writes and wrong vanilla bytes, so
        this proves the whole set is consistent on the real disc."""
        world = fake_world(text_skip=1, skip_intro_videos=1, exit_stage_anytime=1,
                           weapon_damage=4, boss_hp_randomization=4, boss_damage=4, pickupsanity=1,
                           max_life=80)
        edits = (list(disc.BASE_EDITS) + disc.routine_edits(self.track1)
                 + disc.ap_block_edits(1) + Rom.seed_edits(world))
        patched = disc.apply_edits(self.track1, edits)
        # Spot checks through three regions.
        self.assertEqual(patched[disc.addr_to_disc(0x8010395C, disc.REGION_EXE)], 0)
        off = disc.addr_to_disc(damage.DAMAGE_TABLES, disc.REGION_EXE)
        tables = bytes(patched[disc.addr_to_disc(damage.DAMAGE_TABLES + i, disc.REGION_EXE)]
                       for i in range(len(damage.DAMAGE_TABLES_VANILLA)))
        self.assertEqual(tables, world.weapon_damage_tables)
        self.assertNotEqual(off, 0)
        gate = disc.addr_to_disc(0x801E160C, "ovl:STAGE04")
        hp = damage.scaled_hp(40, world.boss_hp_factors["Grenade Man"])
        self.assertEqual(patched[gate], hp)


class TestExitPartUnderTheOption(MM8TestBase):
    options = {"exit_stage_anytime": True}

    def test_the_part_is_filler(self):
        self.assertEqual(self.world.create_item(names.EXIT).classification, ItemClassification.filler)


class TestExitPartWithoutTheOption(MM8TestBase):
    options = {"exit_stage_anytime": False}

    def test_the_part_keeps_its_class(self):
        self.assertEqual(self.world.create_item(names.EXIT).classification, ItemClassification.useful)


class TestEveryNewOptionAtItsExtreme(MM8TestBase):
    options = {"text_skip": True, "skip_intro_videos": True, "exit_stage_anytime": True,
               "weapon_damage": "chaotic", "boss_hp_randomization": "chaotic"}

    def test_the_rolls_are_made_and_spoiled(self):
        self.assertEqual(set(self.world.weapon_damage_factors), set(damage.WEAPON_FAMILIES))
        self.assertEqual(set(self.world.boss_hp_factors), set(damage.BOSS_HP_SITES))
        out = io.StringIO()
        self.world.write_spoiler(out)
        self.assertIn("Mega Buster: x", out.getvalue())
        self.assertIn("Grenade Man", out.getvalue())


if __name__ == "__main__":
    unittest.main()
