"""Weapon damage and boss HP randomization for Mega Man 8.

Both are disc edits rolled at generation from the world's random, so a seed
owns its numbers and they land in the spoiler; the patch only writes them.
Research: ram-notes 6b-6d and the parity plan (track A), every site read off
our own disc.

WEAPON DAMAGE. MM8 keeps its damage the other way round from X5: there is no
player attack table. Each ENEMY type owns a 19-byte table indexed by the
hitting weapon's damage id (`0x80107400`), so one weapon's damage is a COLUMN
across all 42 tables - X6's layout, and X6's answer: one multiplier per
weapon, applied down its column in every table. That keeps every weakness
(a weakness is a row) and every "which weapon breaks what" fact the bolt
logic stands on, because only cells that already deal damage are scaled and
none can scale to a non-damage value.

BOSS HP. There is no max-HP byte for a client to hold (X5's way): each boss
zeroes its HP when its bar appears and its own fill loop counts back up to a
hard-coded 40, and the bar just draws min(hp, 40) pixels. So this is X6's
way - rewrite each fill's immediates on the disc - with X6's discipline:
every site is a whole instruction whose vanilla word is asserted, and each
was proven by what consumes it, not by its immediate.
"""
import math

from . import mips  # noqa: F401  (kept beside disc for the tests' loader)
from .disc import REGION_EXE

# ---- Weapon damage -----------------------------------------------------------
# 42 tables of 20 bytes (19 damage ids + a 0 terminator), contiguous, directly
# in front of their own 42-entry pointer table. Only two readers anywhere: the
# lookup and Homing Sniper's target search (which skips an object whose
# column-12 byte has bit 7 set - one more reason nothing may scale to 0x80+).
DAMAGE_TABLES = 0x80139674
DAMAGE_TABLE_COUNT = 42
DAMAGE_TABLE_STRIDE = 20
DAMAGE_IDS = 19
DAMAGE_TABLES_VANILLA = bytes.fromhex(
    "81818181818181818081818181818181818181008181817f81818181808181818181818181818100"
    "0203067f08040101800801040404027f060306008080808080808280828082808080808080808000"
    "02030680080401018008010404040204060306008181818081818181808181818181818181818100"
    "80808280808080828080828080828082808080008080808080828080808080808080808080808000"
    "0203067f080482018008010404040404060306000203068181818080818181818181818108818100"
    "02030401010601010101020101010481040102000102030101810103000003018181038103010200"
    "01020301010104010101010101010381030102000102030101010102010101040101038103010200"
    "01010201010101010101010101810204020102000101030101020101010101010104038103010200"
    "01010301010101010000040101010281030102000101030101010102010101010301038103010100"
    "81818181818181058181058181818105818181000203067f02008101818101040402027f06030600"
    "81818181810381818081818181818181818181008080808080808080808080800280800180808000"
    "818181818181818180817f8181818181818181008181818181818281808181818181818181818100"
    "0102037f030302028002030302020208030102008080808080808080808004808080808080808000"
    "0102037f030402028002010302050203030102008181817f81818181818181818104818181818100"
    "8181817f818181818181818181828181818181000101020101010101010101010101010101010100"
    "01010280060181018080010181010281020202000202048005020202808004020202010404020200"
    "01020380018080018080010501800280020280008181818181008181808181818181818181818100"
    "01010201020180010101020181020202020101000101028181818102818102818101028102818100"
    "01010281010101018181010181010201020101000203048103030302030305050202050203030300"
    "02030481030303028008050502020202030303000203047f04040204010104040201030204020300"
    "01020300020201010000040202810202030102000203040004040303000004040304040304020300")
# What sits on either side, never written - proof the region's bounds are right.
DAMAGE_TABLES_BEFORE = (DAMAGE_TABLES - 4, bytes.fromhex("00800000"))        # tail of a u16 curve
DAMAGE_TABLES_AFTER = (DAMAGE_TABLES + len(DAMAGE_TABLES_VANILLA),         # the pointer table
                       bytes.fromhex("7496138088961380"))

# Damage ids that are one weapon and must share one multiplier. The buster's
# charge levels together, with Laser and Arrow - charge-shot variants, the
# way X5 puts every armor's full charge in the buster family. Every special
# weapon's object sets exactly one damage id, so each is its own family.
WEAPON_FAMILIES: dict[str, tuple[int, ...]] = {
    "Mega Buster": (0, 1, 2, 14, 16),     # plain, half, full charge, Laser, Arrow
    "Mega Ball": (4,),
    "Ice Wave": (5,),
    "Tornado Hold": (6,),
    "Flash Bomb": (7,),
    "flying-section shot": (8, 9),        # STAGE03/0B's helper; 8 for 20 frames after +0x56
    "Flame Sword": (10,),
    "Thunder Claw": (11,),
    "Homing Sniper": (12,),
    "Water Balloon": (13,),
    "Astro Crush": (15,),
    "Rush Bike": (17,),
    "Rush Bomber": (18,),
}
# Id 3 is NOT a player weapon: a hitbox enemies carry. Never scaled.
NEVER_SCALED_IDS = (3,)

# ---- The roll every randomizer here shares (0.2.0) ---------------------------
# NOT X5/X6's bands. Theirs pick a DIRECTION - weak is always below normal,
# strong always above (40-80% boss HP put every bar short, every seed). Ivor,
# 2026-09-29: "make it like the damage ranges that just scale the width of the
# roll" - each setting widens the roll evenly around normal instead, up and
# down by the same factor ("even both ways"): mild x1.25 either way (80-125%),
# moderate x1.5 (67-150%), wild x1.75 (57-175%), extreme x2 (50-200%). The roll
# is even in RATIO terms (log-uniform), so a result is as likely above normal
# as below it; a plain uniform roll over 50-200% lands below only a third of
# the time. The old names load as aliases (options.py).
BAND_WIDTH = {
    1: 1.25,    # mild
    2: 1.50,    # moderate
    3: 1.75,    # wild
    4: 2.00,    # extreme
}


def band(mode: int) -> tuple[float, float]:
    """The lowest and highest factor a setting can roll."""
    width = BAND_WIDTH[mode]
    return 1 / width, width


def roll(mode: int, random) -> float:
    """One factor, even in ratio terms across band(mode)."""
    spread = math.log(BAND_WIDTH[mode])
    return math.exp(random.uniform(-spread, spread))


# 1..0x7E. Floor 1, not 0, because 0 is a REAL value here - a hit that does
# nothing - so rounding a hit to 0 would quietly disarm it. Ceiling 0x7E:
# 0x7F kills anything (object HP is at most 127) and 0x80+ are the no-effect,
# deflect and pass-through codes. Cells outside 1..0x7E are never touched.
DAMAGE_MIN, DAMAGE_MAX = 1, 0x7E


def weapon_damage_tables(mode: int, random, vanilla: bytes = b"") -> tuple[bytes, dict[str, float]]:
    """A scaled copy of the 42 tables, and the multiplier each family got.

    One roll per family, applied to that family's columns in EVERY table.
    Rounding and the clamp are monotonic, so a shared multiplier keeps the
    charged buster at least as strong as the plain shot in every table.
    """
    out = bytearray(vanilla or DAMAGE_TABLES_VANILLA)
    factors = {family: roll(mode, random) for family in WEAPON_FAMILIES}
    for family, ids in WEAPON_FAMILIES.items():
        for table in range(len(out) // DAMAGE_TABLE_STRIDE):
            for dmg_id in ids:
                at = table * DAMAGE_TABLE_STRIDE + dmg_id
                if DAMAGE_MIN <= out[at] <= DAMAGE_MAX:
                    out[at] = max(DAMAGE_MIN, min(DAMAGE_MAX, round(out[at] * factors[family])))
    return bytes(out), factors


def weapon_damage_edits(tables: bytes) -> list[tuple[str, int, str, bytes, bytes]]:
    """One write over the whole region. apply_edits verifies all 840 vanilla
    bytes; the tests pin both neighbours (DAMAGE_TABLES_BEFORE/AFTER) to the
    disc, so a region that ran long or short would be caught."""
    if len(tables) != len(DAMAGE_TABLES_VANILLA):
        raise ValueError(f"weapon damage: {len(tables)} bytes, expected {len(DAMAGE_TABLES_VANILLA)}")
    return [("weapon damage tables", DAMAGE_TABLES, REGION_EXE, DAMAGE_TABLES_VANILLA, tables)]


# ---- Boss HP -------------------------------------------------------------------
# Each boss's fill loop: HP zeroed at registration, +1 every other frame, then
#   cmpN   `sltiu v0, v0, 40`  (Frost)        -> sltiu N
#   cmpN1  `sltiu v0, v0, 41`  (the others)   -> sltiu N + 1
#   store  `ori v0, zero, 40`  -> sb v0, 0x47(boss)   -> ori N
#   gate   `ori v0, zero, 40`  -> bne hp, v0: the fight starts only at hp == 40
#          (Grenade Man and his refight) - rolling a fill WITHOUT its gate means
#          the fight never starts.
# All plain loads or compares (rs = zero for ori, rs = v0 for sltiu); no
# `addiu v0, v0, N` add-on shape exists here (X6's second escape). The Wily 4
# refights are separate code in STAGE0D with their own sites.
_SLTIU_V0_V0 = 0x2C420000
_ORI_V0_ZERO = 0x34020000

BOSS_HP_SITES: dict[str, list[tuple[str, int, str, int]]] = {
    # boss: [(region, RAM, role, vanilla word)]
    "Frost Man": [("ovl:STAGE01", 0x801DED24, "cmpN", 0x2C420028),
                  ("ovl:STAGE01", 0x801DED34, "store", 0x34020028),
                  ("ovl:STAGE0D", 0x801D8E64, "cmpN", 0x2C420028),
                  ("ovl:STAGE0D", 0x801D8E74, "store", 0x34020028)],
    "Clown Man": [("ovl:STAGE02", 0x801DE3A0, "cmpN1", 0x2C420029),
                  ("ovl:STAGE02", 0x801DE3AC, "store", 0x34020028),
                  ("ovl:STAGE0D", 0x801E7854, "cmpN1", 0x2C420029),
                  ("ovl:STAGE0D", 0x801E7860, "store", 0x34020028)],
    "Tengu Man": [("ovl:STAGE03", 0x801E1BE0, "cmpN1", 0x2C420029),
                  ("ovl:STAGE03", 0x801E1BF0, "store", 0x34020028),
                  ("ovl:STAGE0D", 0x801DD320, "cmpN1", 0x2C420029),
                  ("ovl:STAGE0D", 0x801DD330, "store", 0x34020028)],
    "Grenade Man": [("ovl:STAGE04", 0x801E15BC, "cmpN1", 0x2C420029),
                    ("ovl:STAGE04", 0x801E15C4, "store", 0x34020028),
                    ("ovl:STAGE04", 0x801E160C, "gate", 0x34020028),
                    ("ovl:STAGE0D", 0x801E0218, "cmpN1", 0x2C420029),
                    ("ovl:STAGE0D", 0x801E0220, "store", 0x34020028),
                    ("ovl:STAGE0D", 0x801E0268, "gate", 0x34020028)],
    "Sword Man": [("ovl:STAGE05", 0x801E10F4, "cmpN1", 0x2C420029),
                  ("ovl:STAGE05", 0x801E1100, "store", 0x34020028),
                  ("ovl:STAGE0D", 0x801EF390, "cmpN1", 0x2C420029),
                  ("ovl:STAGE0D", 0x801EF39C, "store", 0x34020028)],
    "Aqua Man": [("ovl:STAGE06", 0x801DC088, "cmpN1", 0x2C420029),
                 ("ovl:STAGE06", 0x801DC090, "store", 0x34020028),
                 ("ovl:STAGE0D", 0x801E3D30, "cmpN1", 0x2C420029),
                 ("ovl:STAGE0D", 0x801E3D38, "store", 0x34020028)],
    "Astro Man": [("ovl:STAGE07", 0x801DBBF4, "cmpN1", 0x2C420029),
                  ("ovl:STAGE07", 0x801DBC00, "store", 0x34020028),
                  ("ovl:STAGE0D", 0x801F1BAC, "cmpN1", 0x2C420029),
                  ("ovl:STAGE0D", 0x801F1BB8, "store", 0x34020028)],
    "Search Man": [("ovl:STAGE08", 0x801DC2E4, "cmpN1", 0x2C420029),
                   ("ovl:STAGE08", 0x801DC2F0, "store", 0x34020028),
                   ("ovl:STAGE0D", 0x801EAF04, "cmpN1", 0x2C420029),
                   ("ovl:STAGE0D", 0x801EAF10, "store", 0x34020028)],
}
BOSS_VANILLA_HP = 40

# The four Rush mini-bosses have no bar and no fill: their HP is byte 1 of
# their object descriptor (0x801393B4 + id * 4), read at spawn. Each id is
# live in exactly one overlay, so the byte is theirs alone. Each shares its
# stage's roll, as X5's mid-bosses share the stage's.
MIDBOSS_HP: dict[str, tuple[int, int]] = {
    # stage boss: (descriptor HP byte, vanilla HP)
    "Grenade Man": (0x801393B4 + 42 * 4 + 1, 32),
    "Clown Man": (0x801393B4 + 69 * 4 + 1, 32),
    "Sword Man": (0x801393B4 + 51 * 4 + 1, 40),
    "Aqua Man": (0x801393B4 + 63 * 4 + 1, 40),
}

# Multipliers of each boss's vanilla HP come from roll() (above): 20-80 for a
# Robot Master at the widest setting.
# 1..127. At 0 a boss can never be hit (ContactWeapon returns early on HP 0),
# and above 127 the signed survival test kills it on any hit. There is no
# art floor: the bar is a quad min(hp, 40) pixels tall, so every value draws.
BOSS_HP_MIN, BOSS_HP_MAX = 1, 127


def boss_hp_rolls(mode: int, random) -> dict[str, float]:
    """One multiplier per Robot Master - shared by the stage fight, its Wily 4
    refight and the stage's Rush mini-boss."""
    return {boss: roll(mode, random) for boss in BOSS_HP_SITES}


def scaled_hp(vanilla: int, factor: float) -> int:
    return max(BOSS_HP_MIN, min(BOSS_HP_MAX, round(vanilla * factor)))


def boss_hp_edits(factors: dict[str, float]) -> list[tuple[str, int, str, bytes, bytes]]:
    """Whole-instruction rewrites of every fill site, gate and mini-boss byte."""
    out = []
    for boss, sites in BOSS_HP_SITES.items():
        if boss not in factors:
            continue
        hp = scaled_hp(BOSS_VANILLA_HP, factors[boss])
        for region, where, role, vanilla in sites:
            if role == "cmpN1":
                base, value = _SLTIU_V0_V0, hp + 1
            elif role == "cmpN":
                base, value = _SLTIU_V0_V0, hp
            else:                              # store, gate
                base, value = _ORI_V0_ZERO, hp
            if vanilla & 0xFFFF0000 != base:
                raise ValueError(f"{boss} {where:#x}: {vanilla:#010x} is not the expected shape")
            out.append((f"boss HP {boss} {role}", where, region,
                        vanilla.to_bytes(4, "little"), (base | value).to_bytes(4, "little")))
        if boss in MIDBOSS_HP:
            where, vanilla_hp = MIDBOSS_HP[boss]
            out.append((f"boss HP {boss}'s mini-boss", where, REGION_EXE,
                        bytes([vanilla_hp]), bytes([scaled_hp(vanilla_hp, factors[boss])])))
    return out


# ---- Boss damage -----------------------------------------------------------------
# X5 scales each Maverick's own attack table by one multiplier. MM8 has no
# attack tables: a boss's damage is spread over its body's descriptor byte
# (EXE 0x801393B4 + id * 4 + 2, copied to +0x45 at init), `ori` immediates
# its code stores to +0x45 or passes to the three damage-by-argument routines
# (hit 0x80111D34, drain 0x80111CB4, grab 0x80111EF8), and - for Grenade,
# Sword, Aqua, Astro and Search - an 8-byte-per-subId row table in the
# overlay that each projectile's init reads straight after the descriptor
# (so the projectile's own descriptor byte is dead). So this is X5's rule -
# ONE multiplier per boss, the whole move set moving together - over every
# site that boss's attacks take their damage from, in its stage and its Wily
# 4 rematch (the descriptor is global, so the two must share it).
#
# Research: Reference/research/2026-09-24_parity-A-* and track A's follow-up
# (every row's subIds taken from the spawn sites; every table, immediate and
# descriptor byte shown to be read only by that boss's own objects - no
# projectile id is shared with anything else). Only values in 1..0x7E are
# listed. The exclusions and why:
BOSS_DAMAGE_EXCLUDED = [
    # descriptor bytes that are dead (their +0x45 is always overwritten before any hurt call)
    ("exe", 0x801393B4 + 54 * 4 + 2, "byte", "Grenade projectile: row override at init"),
    ("exe", 0x801393B4 + 77 * 4 + 2, "byte", "Sword projectile: row override at init"),
    ("exe", 0x801393B4 + 59 * 4 + 2, "byte", "Aqua projectile: row override at init"),
    ("exe", 0x801393B4 + 87 * 4 + 2, "byte", "Astro projectile: row override at init"),
    ("exe", 0x801393B4 + 73 * 4 + 2, "byte", "Search projectile: row override at init"),
    ("exe", 0x801393B4 + 76 * 4 + 2, "byte", "Sword Man body: his only ContactMega sets +0x45 first"),
    ("exe", 0x801393B4 + 40 * 4 + 2, "byte", "Tengu projectile: 0, and id 40 never calls ContactMega"),
    ("ovl:STAGE03", 0x801E3C34, "ori", "Tengu projectile +0x45 = 1: never consumed (id 40 hurts only via the drain)"),
    ("ovl:STAGE0D", 0x801DF374, "ori", "same, refight"),
    # shared-register writers of Sword's blade damage (+0x59): the same register also feeds +0x26
    ("ovl:STAGE05", 0x801E0D00, "ori", "init: a2=7 -> +0x26, +0x59 AND the animation argument"),
    ("ovl:STAGE05", 0x801E19EC, "ori", "sub-state 10: v1=7 -> +0x59 AND +0x26"),
    ("ovl:STAGE0D", 0x801EEF9C, "ori", "refight init, same as 0x801E0D00"),
    ("ovl:STAGE0D", 0x801EFC88, "ori", "refight sub-state 10, same as 0x801E19EC"),
]

# (region, RAM address, kind, vanilla): "ori" a whole `ori rt, zero, N` word
# whose N is scaled; "byte" a data byte.
BOSS_DAMAGE_SITES: dict[str, list[tuple[str, int, str, int]]] = {
    "Frost Man": [
        ("exe", 0x80139432, "byte", 5),      # descriptor id 31 contact damage: Frost Man body
        ("exe", 0x80139466, "byte", 2),      # descriptor id 44 contact damage: Frost Man's projectile (id 44)
        ("ovl:STAGE01", 0x801E0CFC, "ori", 0x34020005),  # ori 5: +0x45 self, delay slot of jal ContactMega
        ("ovl:STAGE01", 0x801E15B8, "ori", 0x34040002),  # ori 2: a0 of 0x80111CB4 (drain)
        ("ovl:STAGE01", 0x801E1620, "ori", 0x34040004),  # ori 4: a0 of 0x80111D34 (hit)
        ("ovl:STAGE01", 0x801E2854, "ori", 0x34040003),  # ori 3: id 44: a0 of 0x80111D34
        ("ovl:STAGE01", 0x801E2B4C, "ori", 0x34040003),  # ori 3: id 44: a0 of 0x80111D34
        ("ovl:STAGE0D", 0x801DAE3C, "ori", 0x34020005),  # ori 5: +0x45 self, delay slot of jal ContactMega
        ("ovl:STAGE0D", 0x801DB6F8, "ori", 0x34040002),  # ori 2: a0 of 0x80111CB4 (drain)
        ("ovl:STAGE0D", 0x801DB760, "ori", 0x34040004),  # ori 4: a0 of 0x80111D34 (hit)
        ("ovl:STAGE0D", 0x801DC0A8, "ori", 0x34040003),  # ori 3: id 44: a0 of 0x80111D34
        ("ovl:STAGE0D", 0x801DC3A0, "ori", 0x34040003),  # ori 3: id 44: a0 of 0x80111D34
    ],
    "Clown Man": [
        ("exe", 0x801394B6, "byte", 1),      # descriptor id 64 contact damage: Clown Man body and his id-64 sub-objects
        ("ovl:STAGE02", 0x801DE620, "ori", 0x34030004),  # ori 4: +0x45
        ("ovl:STAGE02", 0x801DEFE4, "ori", 0x34020005),  # ori 5: +0x45
        ("ovl:STAGE02", 0x801DF0B0, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE02", 0x801DF48C, "ori", 0x34030004),  # ori 4: +0x45
        ("ovl:STAGE02", 0x801DF640, "ori", 0x34030004),  # ori 4: +0x45
        ("ovl:STAGE02", 0x801DF9F0, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE02", 0x801DFB64, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE02", 0x801DEC84, "ori", 0x34040001),  # ori 1: a0 of 0x80111CB4 (drain)
        ("ovl:STAGE0D", 0x801E7AD4, "ori", 0x34030004),  # ori 4: +0x45
        ("ovl:STAGE0D", 0x801E8498, "ori", 0x34020005),  # ori 5: +0x45
        ("ovl:STAGE0D", 0x801E8564, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE0D", 0x801E8940, "ori", 0x34030004),  # ori 4: +0x45
        ("ovl:STAGE0D", 0x801E8AF4, "ori", 0x34030004),  # ori 4: +0x45
        ("ovl:STAGE0D", 0x801E8EA4, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE0D", 0x801E9018, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE0D", 0x801E8138, "ori", 0x34040001),  # ori 1: a0 of 0x80111CB4 (drain)
    ],
    "Tengu Man": [
        ("exe", 0x80139452, "byte", 5),      # descriptor id 39 contact damage: Tengu Man body
        ("ovl:STAGE03", 0x801E33EC, "ori", 0x34040003),  # ori 3: a0 of 0x80111EF8 (grab)
        ("ovl:STAGE03", 0x801E3E88, "ori", 0x34040001),  # ori 1: id 40: a0 of 0x80111CB4 (drain)
        ("ovl:STAGE0D", 0x801DEB2C, "ori", 0x34040003),  # ori 3: a0 of 0x80111EF8 (grab)
        ("ovl:STAGE0D", 0x801DF5C8, "ori", 0x34040001),  # ori 1: id 40: a0 of 0x80111CB4 (drain)
    ],
    "Grenade Man": [
        ("exe", 0x8013948A, "byte", 4),      # descriptor id 53 contact damage: Grenade Man body
        ("ovl:STAGE04", 0x801E1BD4, "ori", 0x34020005),  # ori 5: +0x45
        ("ovl:STAGE04", 0x801E1C88, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE04", 0x801E2C30, "ori", 0x34020004),  # ori 4: +0x45 (a0)
        ("ovl:STAGE0D", 0x801E0830, "ori", 0x34020005),  # ori 5: +0x45
        ("ovl:STAGE0D", 0x801E08E4, "ori", 0x34020004),  # ori 4: +0x45
        ("ovl:STAGE0D", 0x801E188C, "ori", 0x34020004),  # ori 4: +0x45 (a0)
        ("ovl:STAGE04", 0x801E7308, "byte", 5),      # projectile row 0 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7310, "byte", 4),      # projectile row 1 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7318, "byte", 3),      # projectile row 2 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7320, "byte", 3),      # projectile row 3 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7328, "byte", 3),      # projectile row 4 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7350, "byte", 3),      # projectile row 9 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7358, "byte", 3),      # projectile row 10 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7360, "byte", 3),      # projectile row 11 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7368, "byte", 3),      # projectile row 12 (+4) of 0x801E7304
        ("ovl:STAGE04", 0x801E7370, "byte", 5),      # projectile row 13 (+4) of 0x801E7304
        ("ovl:STAGE0D", 0x801F8580, "byte", 5),      # projectile row 0 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F8588, "byte", 4),      # projectile row 1 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F8590, "byte", 3),      # projectile row 2 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F8598, "byte", 3),      # projectile row 3 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F85A0, "byte", 3),      # projectile row 4 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F85C8, "byte", 3),      # projectile row 9 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F85D0, "byte", 3),      # projectile row 10 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F85D8, "byte", 3),      # projectile row 11 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F85E0, "byte", 3),      # projectile row 12 (+4) of 0x801F857C
        ("ovl:STAGE0D", 0x801F85E8, "byte", 5),      # projectile row 13 (+4) of 0x801F857C
    ],
    "Sword Man": [
        ("ovl:STAGE05", 0x801E2918, "ori", 0x34020007),  # ori 7: +0x45 hitboxes 0 and 2
        ("ovl:STAGE0D", 0x801F0BB4, "ori", 0x34020007),  # ori 7: +0x45 hitboxes 0 and 2
        ("ovl:STAGE05", 0x801E164C, "ori", 0x34020008),  # ori 8: blade (hitbox 1) damage -> sb +0x59, sub-state 6
        ("ovl:STAGE05", 0x801E1CF4, "ori", 0x34020006),  # ori 6: blade damage -> sb +0x59, sub-sub-state 0x801E1C0C
        ("ovl:STAGE05", 0x801E1DDC, "ori", 0x34020007),  # ori 7: blade damage -> sb +0x59, sub-sub-state 0x801E1D3C
        ("ovl:STAGE0D", 0x801EF8E8, "ori", 0x34020008),  # ori 8: blade damage -> sb +0x59 (refight)
        ("ovl:STAGE0D", 0x801EFF90, "ori", 0x34020006),  # ori 6: blade damage -> sb +0x59 (refight)
        ("ovl:STAGE0D", 0x801F0078, "ori", 0x34020007),  # ori 7: blade damage -> sb +0x59 (refight)
        ("ovl:STAGE05", 0x801EA78A, "byte", 1),      # projectile row 0 (+2) of 0x801EA788
        ("ovl:STAGE05", 0x801EA792, "byte", 10),      # projectile row 1 (+2) of 0x801EA788
        ("ovl:STAGE05", 0x801EA7A2, "byte", 10),      # projectile row 3 (+2) of 0x801EA788
        ("ovl:STAGE05", 0x801EA7AA, "byte", 6),      # projectile row 4 (+2) of 0x801EA788
        ("ovl:STAGE05", 0x801EA7B2, "byte", 4),      # projectile row 5 (+2) of 0x801EA788
        ("ovl:STAGE0D", 0x801F8E2E, "byte", 1),      # projectile row 0 (+2) of 0x801F8E2C
        ("ovl:STAGE0D", 0x801F8E36, "byte", 10),      # projectile row 1 (+2) of 0x801F8E2C
        ("ovl:STAGE0D", 0x801F8E46, "byte", 10),      # projectile row 3 (+2) of 0x801F8E2C
        ("ovl:STAGE0D", 0x801F8E4E, "byte", 6),      # projectile row 4 (+2) of 0x801F8E2C
        ("ovl:STAGE0D", 0x801F8E56, "byte", 4),      # projectile row 5 (+2) of 0x801F8E2C
    ],
    "Aqua Man": [
        ("exe", 0x8013949E, "byte", 6),      # descriptor id 58 contact damage: Aqua Man body
        ("ovl:STAGE06", 0x801E5921, "byte", 6),      # projectile row 0 (+1) of 0x801E5920
        ("ovl:STAGE06", 0x801E5929, "byte", 7),      # projectile row 1 (+1) of 0x801E5920
        ("ovl:STAGE06", 0x801E5931, "byte", 7),      # projectile row 2 (+1) of 0x801E5920
        ("ovl:STAGE06", 0x801E5939, "byte", 8),      # projectile row 3 (+1) of 0x801E5920
        ("ovl:STAGE06", 0x801E5941, "byte", 6),      # projectile row 4 (+1) of 0x801E5920
        ("ovl:STAGE06", 0x801E5949, "byte", 6),      # projectile row 5 (+1) of 0x801E5920
        ("ovl:STAGE06", 0x801E5951, "byte", 1),      # projectile row 6 (+1) of 0x801E5920
        ("ovl:STAGE0D", 0x801F883D, "byte", 6),      # projectile row 0 (+1) of 0x801F883C
        ("ovl:STAGE0D", 0x801F8845, "byte", 7),      # projectile row 1 (+1) of 0x801F883C
        ("ovl:STAGE0D", 0x801F884D, "byte", 7),      # projectile row 2 (+1) of 0x801F883C
        ("ovl:STAGE0D", 0x801F8855, "byte", 8),      # projectile row 3 (+1) of 0x801F883C
        ("ovl:STAGE0D", 0x801F885D, "byte", 6),      # projectile row 4 (+1) of 0x801F883C
        ("ovl:STAGE0D", 0x801F8865, "byte", 6),      # projectile row 5 (+1) of 0x801F883C
        ("ovl:STAGE0D", 0x801F886D, "byte", 1),      # projectile row 6 (+1) of 0x801F883C
    ],
    "Astro Man": [
        ("exe", 0x8013950E, "byte", 6),      # descriptor id 86 contact damage: Astro Man body
        ("ovl:STAGE07", 0x801E0A9E, "byte", 1),      # projectile row 0 (+2) of 0x801E0A9C
        ("ovl:STAGE07", 0x801E0AA6, "byte", 6),      # projectile row 1 (+2) of 0x801E0A9C
        ("ovl:STAGE07", 0x801E0AAE, "byte", 4),      # projectile row 2 (+2) of 0x801E0A9C
        ("ovl:STAGE07", 0x801E0AB6, "byte", 4),      # projectile row 3 (+2) of 0x801E0A9C
        ("ovl:STAGE07", 0x801E0ABE, "byte", 6),      # projectile row 4 (+2) of 0x801E0A9C
        ("ovl:STAGE0D", 0x801F8FBE, "byte", 1),      # projectile row 0 (+2) of 0x801F8FBC
        ("ovl:STAGE0D", 0x801F8FC6, "byte", 6),      # projectile row 1 (+2) of 0x801F8FBC
        ("ovl:STAGE0D", 0x801F8FCE, "byte", 4),      # projectile row 2 (+2) of 0x801F8FBC
        ("ovl:STAGE0D", 0x801F8FD6, "byte", 4),      # projectile row 3 (+2) of 0x801F8FBC
        ("ovl:STAGE0D", 0x801F8FDE, "byte", 6),      # projectile row 4 (+2) of 0x801F8FBC
    ],
    "Search Man": [
        ("exe", 0x801394D6, "byte", 5),      # descriptor id 72 contact damage: Search Man body
        ("ovl:STAGE08", 0x801E1216, "byte", 1),      # projectile row 0 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E121E, "byte", 1),      # projectile row 1 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E1226, "byte", 1),      # projectile row 2 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E122E, "byte", 3),      # projectile row 3 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E1236, "byte", 1),      # projectile row 4 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E123E, "byte", 3),      # projectile row 5 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E1246, "byte", 5),      # projectile row 6 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E124E, "byte", 4),      # projectile row 7 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E1256, "byte", 5),      # projectile row 8 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E125E, "byte", 1),      # projectile row 9 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E1266, "byte", 3),      # projectile row 10 (+2) of 0x801E1214
        ("ovl:STAGE08", 0x801E126E, "byte", 3),      # projectile row 11 (+2) of 0x801E1214
        ("ovl:STAGE0D", 0x801F8BFE, "byte", 1),      # projectile row 0 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C06, "byte", 1),      # projectile row 1 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C0E, "byte", 1),      # projectile row 2 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C16, "byte", 3),      # projectile row 3 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C1E, "byte", 1),      # projectile row 4 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C26, "byte", 3),      # projectile row 5 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C2E, "byte", 5),      # projectile row 6 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C36, "byte", 4),      # projectile row 7 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C3E, "byte", 5),      # projectile row 8 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C46, "byte", 1),      # projectile row 9 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C4E, "byte", 3),      # projectile row 10 (+2) of 0x801F8BFC
        ("ovl:STAGE0D", 0x801F8C56, "byte", 3),      # projectile row 11 (+2) of 0x801F8BFC
    ],
}

_ORI_ZERO_MASK, _ORI_ZERO = 0xFFE00000, 0x34000000     # opcode + rs: `ori rt, zero, ...`


def boss_damage_rolls(mode: int, random) -> dict[str, float]:
    return {boss: roll(mode, random) for boss in BOSS_DAMAGE_SITES}


def scaled_damage(value: int, factor: float) -> int:
    return max(DAMAGE_MIN, min(DAMAGE_MAX, round(value * factor)))


def boss_damage_edits(factors: dict[str, float]) -> list[tuple[str, int, str, bytes, bytes]]:
    out = []
    for boss, sites in BOSS_DAMAGE_SITES.items():
        if boss not in factors:
            continue
        for region, where, kind, vanilla in sites:
            if kind == "ori":
                if vanilla & _ORI_ZERO_MASK != _ORI_ZERO:
                    raise ValueError(f"{boss} {where:#x}: {vanilla:#010x} is not `ori rt, zero, N`")
                new = (vanilla & 0xFFFF0000) | scaled_damage(vanilla & 0xFFFF, factors[boss])
                out.append((f"boss damage {boss} {where:#x}", where, region,
                            vanilla.to_bytes(4, "little"), new.to_bytes(4, "little")))
            else:
                out.append((f"boss damage {boss} {where:#x}", where, region,
                            bytes([vanilla]), bytes([scaled_damage(vanilla, factors[boss])])))
    return out
