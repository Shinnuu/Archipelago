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
        for mode in damage.BAND_WIDTH:
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


class TestTheRoll(unittest.TestCase):
    """0.2.0 (Ivor, 2026-09-29): every setting of the three randomizers is a
    WIDTH, centred on normal and even both ways - not X5's direction bands,
    where 'weak' boss HP started every bar short, every seed."""

    def test_bands_are_symmetric_in_ratio(self):
        for mode in damage.BAND_WIDTH:
            low, high = damage.band(mode)
            self.assertAlmostEqual(low * high, 1.0)
        self.assertEqual([round(damage.band(m)[1], 2) for m in (1, 2, 3, 4)], [1.25, 1.5, 1.75, 2.0])

    def test_rolls_stay_in_band_and_split_evenly(self):
        import random
        rng = random.Random(29)
        for mode in damage.BAND_WIDTH:
            low, high = damage.band(mode)
            rolls = [damage.roll(mode, rng) for _ in range(4000)]
            self.assertTrue(all(low <= r <= high for r in rolls), mode)
            above = sum(r > 1 for r in rolls) / len(rolls)
            self.assertAlmostEqual(above, 0.5, delta=0.03, msg=mode)

    def test_a_plain_uniform_roll_would_not(self):
        # The control: uniform over the same band leans low (a third above
        # at the widest), which is why roll() is even in ratio terms.
        import random
        rng = random.Random(29)
        low, high = damage.band(4)
        above = sum(rng.uniform(low, high) > 1 for _ in range(4000)) / 4000
        self.assertAlmostEqual(above, 2 / 3, delta=0.03)

    def test_the_old_names_still_load(self):
        from ..options import BossDamage, BossHPRandomization, WeaponDamage
        for option in (WeaponDamage, BossHPRandomization, BossDamage):
            for old, new in (("weak", "mild"), ("regular", "moderate"), ("strong", "wild"),
                             ("chaotic", "extreme")):
                with self.subTest(option=option.__name__, name=old):
                    self.assertEqual(option.from_any(old).value, option.from_any(new).value)
                    self.assertEqual(option.from_any(old).current_key, new)


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
        for mode in damage.BAND_WIDTH:
            low, high = damage.band(mode)
            self.assertGreaterEqual(damage.scaled_hp(32, low), 1)
            self.assertLessEqual(damage.scaled_hp(40, high), 80)   # the option text's 20-80

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
                                           "boss_damage", "stage_order")}
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
                           max_life=80, stage_order=2))
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
                           max_life=80, stage_order=2)
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
                           max_life=80, stage_order=2)
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


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestStageOrderExecuted(unittest.TestCase):
    """stage_order (0.2.0), executed: the game's OWN code, as the SHIPPED disc
    has it, on the test R3000 - built the way Rom builds a player's disc (the
    base edits, the cave routines, the AP block, and Rom.seed_edits for the
    order, exit_stage_anytime on and off), so a stage_order edit dropped from
    disc.py or from Rom.seed_edits fails here (0.2.0 review M4). The stage-clear
    routine (0x8010123C..0x80101458) runs with its exit hook and the cave's exit
    guard; its calls out - the first call's leaf, the weapon-get demo, ROCK8_3,
    0x801017A4, the save prompt - are stubbed. Only the words run are kept, not
    the discs (0.2.0 review m6: the images held ~1 GB for the whole run)."""
    CLEAR, END = 0x8010123C, 0x80101458
    STUBS = (0x8010BBB8, 0x8011C944, 0x800FD444, 0x801017A4, 0x801218C0)
    PHASE, STAGE, FLAGS, ENDED = 0x801C336C, 0x801C336E, 0x80170555, 0x801B2995
    SELECT_INIT = (0x800FFABC, 0x800FFACC)            # phase < 2 -> +3 "page switch forbidden"
    SELECT_CURSOR = (0x800FFE58, 0x800FFE84)          # phase < 2 -> refuse position 12
    SET_1, SET_2 = names.SET_1, names.SET_2

    @classmethod
    def setUpClass(cls):
        with open(TRACK1, "rb") as f:
            track1 = f.read()
        base = list(disc.BASE_EDITS) + disc.routine_edits(track1) + disc.ap_block_edits(1)
        cls.code = {}
        for mode in disc.STAGE_ORDERS:
            for exit_anytime in (0, 1):
                image = disc.apply_edits(track1, base + Rom.seed_edits(
                    fake_world(stage_order=mode, exit_stage_anytime=exit_anytime)))

                def words(first, last, image=image):
                    return [int.from_bytes(bytes(image[disc.addr_to_disc(a + i, disc.REGION_EXE)]
                                                 for i in range(4)), "little")
                            for a in range(first, last + 4, 4)]
                code = {first: words(first, last) for first, last in
                        ((cls.CLEAR, cls.END), (disc.CAVE_START & ~3, disc.CAVE_END - 4),
                         cls.SELECT_INIT, cls.SELECT_CURSOR)}
                code["table"] = [image[disc.addr_to_disc(0x80137B2B + i, disc.REGION_EXE)] for i in range(16)]
                cls.code[mode, exit_anytime] = code
                del image

    def machine(self, mode: int, exit_anytime: int) -> R3000:
        m = R3000()
        code = self.code[mode, exit_anytime]
        for first, words in code.items():
            if first != "table":
                m.load_code(first, words)
        for i, b in enumerate(code["table"]):                # the stage -> weapon-slot table
            m.wb(0x80137B2B + i, b)
        for stub in self.STUBS:
            m.load_code(stub, [mips.word("jr ra", stub), 0])
        m.r[29] = 0x801FF000
        return m

    def clear(self, mode: int, stage: str, phase: int, beaten: list[str],
              exit_anytime: int = 1, ended: int = 1) -> tuple[int, int]:
        m = self.machine(mode, exit_anytime)
        m.wb(self.PHASE, phase)
        m.wb(self.STAGE, names.STAGE_INDEX[stage])
        m.wb(self.ENDED, ended)                           # 1 a clear, 2 an Exit
        m.wb(self.FLAGS, 2)
        for boss in beaten:
            m.wb(disc.WEAPONS + 4 * names.WEAPON_SLOT[names.BOSS_WEAPON[boss]], 1)
        m.run(self.CLEAR)
        return m.rb(self.PHASE), m.rb(self.FLAGS)

    def test_open_duo_after_set_2_opens_wily(self):
        for exit_anytime in (0, 1):
            with self.subTest(exit_stage_anytime=exit_anytime):
                self.assertEqual(self.clear(1, names.DUO, 3, self.SET_1 + self.SET_2, exit_anytime), (5, 0x0A))
                self.assertEqual(self.clear(1, names.DUO, 3, self.SET_1 + self.SET_2[:3], exit_anytime)[0], 4)
                self.assertEqual(self.clear(1, names.DUO, 3, self.SET_1, exit_anytime)[0], 4)   # vanilla order

    def test_vanilla_strands_wily_there(self):
        # The control: the vanilla order's disc, the same Duo clear with set 2 done.
        self.assertEqual(self.clear(0, names.DUO, 3, self.SET_1 + self.SET_2), (4, 6))

    def test_open_set_2_early_keeps_phase_1(self):
        # Live 2026-09-29: Aqua Man cleared at phase 1, phase stayed 1.
        self.assertEqual(self.clear(1, names.AQUA, 1, [names.FROST, names.CLOWN])[0], 1)
        self.assertEqual(self.clear(1, names.SWORD, 1, self.SET_1[:3] + self.SET_2[1:])[0], 1)
        # ...and set 1's fourth still forces Duo, whatever set 2 holds.
        self.assertEqual(self.clear(1, names.GRENADE, 1, self.SET_1[:3] + [names.SWORD])[0], 2)

    def test_any_four_forces_duo_on_any_fourth_kill(self):
        three_of_set_2 = [names.AQUA, names.ASTRO, names.SWORD]
        self.assertEqual(self.clear(2, names.SWORD, 1, [names.AQUA, names.ASTRO])[0], 1)   # 3 with his
        self.assertEqual(self.clear(2, names.SEARCH, 1, three_of_set_2)[0], 2)             # the 4th
        self.assertEqual(self.clear(2, names.FROST, 1, [names.SEARCH, names.TENGU, names.AQUA])[0], 2)
        # The control: the vanilla gate ignores set 2 and keeps phase 1.
        self.assertEqual(self.clear(0, names.SEARCH, 1, three_of_set_2)[0], 1)

    def test_any_four_opens_wily_only_on_all_eight(self):
        everyone = self.SET_1 + self.SET_2
        seven = [b for b in everyone if b != names.FROST]
        self.assertEqual(self.clear(2, names.FROST, 4, seven[:-1])[0], 4)                 # 7 with his
        self.assertEqual(self.clear(2, names.FROST, 4, seven), (5, 0x0A))                 # the 8th

    def test_any_four_duo_clear_runs_the_count(self):
        # Duo's clear jumps into the gate, which under open_any_four counts.
        everyone = self.SET_1 + self.SET_2
        self.assertEqual(self.clear(2, names.DUO, 3, everyone), (5, 0x0A))
        self.assertEqual(self.clear(2, names.DUO, 3, everyone[:7])[0], 4)
        self.assertEqual(self.clear(2, names.DUO, 3, [names.AQUA, names.ASTRO, names.SWORD, names.FROST])[0], 4)

    def test_an_exit_changes_nothing(self):
        # exit_stage_anytime's hook sends an Exit (2) past the gates, whatever
        # the order; the control is the same stage CLEARED.
        everyone = self.SET_1 + self.SET_2
        for mode in disc.STAGE_ORDERS:
            with self.subTest(mode=mode):
                self.assertEqual(self.clear(mode, names.FROST, 4, everyone, ended=2)[0], 4)
                self.assertEqual(self.clear(mode, names.FROST, 4, everyone, ended=1)[0], 5)

    def select(self, mode: int, slice_: tuple[int, int], cursor: int = 0) -> tuple[int, int]:
        """Run one of the select's phase tests at phase 1 on an object at
        0x80180000 (its +5 = the cursor; s1 = where the cursor came from), and
        return the object's +3 and +5 afterwards."""
        m = self.machine(mode, 1)
        for stop in (slice_[1] + 4, 0x800FFE88, 0x800FFE9C):   # every way out of the two tests
            m.load_code(stop, [mips.word("jr ra", stop), 0])
        obj = 0x80180000
        m.wb(self.PHASE, 1)
        m.wb(obj + 3, 0xAA)
        m.wb(obj + 5, cursor)
        m.r[16], m.r[17] = obj, 7                       # s0 = the object, s1 = the old position
        m.run(slice_[0])
        return m.rb(obj + 3), m.rb(obj + 5)

    def test_page_2_opens_at_phase_1(self):
        # The select init: +3 ("page switch forbidden") = phase < 2.
        self.assertEqual(self.select(0, self.SELECT_INIT)[0], 1)          # vanilla: forbidden
        self.assertEqual(self.select(1, self.SELECT_INIT)[0], 0)
        self.assertEqual(self.select(2, self.SELECT_INIT)[0], 0)
        # The cursor: vanilla sends it back off the page button (12) at phase 1.
        self.assertEqual(self.select(0, self.SELECT_CURSOR, cursor=12)[1], 7)
        self.assertEqual(self.select(1, self.SELECT_CURSOR, cursor=12)[1], 12)
        self.assertEqual(self.select(2, self.SELECT_CURSOR, cursor=12)[1], 12)


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
