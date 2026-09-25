"""String constants and game tables for Mega Man 8.

Every table here is keyed to something the binary itself defines, so the
client and the disc patch can quote it without re-deriving an ordering. The
research record is the private `mm8-ap-research` repo, `Reference/mm8-ram-notes.md`;
its provenance tags are repeated where a fact is not ours:

    [D]  derived from our own disassembly of the disc
    [G]  a web guide - no byte behind it
    [L]  seen in a running game

Stage indices are the game's own (`0x801C336E`, the stage table at
`0x80137A5C`): the index of a stage IS the number of its STAGExx pack, and
the per-stage bolt counts in bolts.py match the web guide's exactly, which
independently confirms the mapping. [D]
"""
from . import disc

# ---- Stages ----------------------------------------------------------------
INTRO = "Intro Stage"
FROST = "Frost Man"
CLOWN = "Clown Man"
TENGU = "Tengu Man"
GRENADE = "Grenade Man"
SWORD = "Sword Man"
AQUA = "Aqua Man"
ASTRO = "Astro Man"
SEARCH = "Search Man"
DUO = "Duo"
WILY_1 = "Wily Stage 1"
WILY_2 = "Wily Stage 2"
WILY_3 = "Wily Stage 3"
WILY_4 = "Wily Stage 4"

# Game stage index -> stage. Never reorder: the index is the game's.
STAGE_INDEX = {
    INTRO: 0, FROST: 1, CLOWN: 2, TENGU: 3, GRENADE: 4,
    SWORD: 5, AQUA: 6, ASTRO: 7, SEARCH: 8, DUO: 9,
    WILY_1: 10, WILY_2: 11, WILY_3: 12, WILY_4: 13,
}

# The two halves of the Robot Master select. The game's own progression gate
# (the stage-clear routine, 0x801012D8..0x80101380) tests exactly these four
# and these four. [D]
SET_1 = [FROST, CLOWN, TENGU, GRENADE]
SET_2 = [SWORD, AQUA, ASTRO, SEARCH]
ROBOT_MASTERS = SET_1 + SET_2
WILY_STAGES = [WILY_1, WILY_2, WILY_3, WILY_4]

# ---- Weapons -----------------------------------------------------------------
# Keyed by the weapon-array slot (0x801B1EAC + slot*4). Slot 0 is the Mega
# Buster, always held. The boss -> slot pairs are the game's own table at
# 0x80137B2B, and the names follow the fire-routine / damage-id map
# (ram-notes 6b). [D]
MEGA_BALL = "Mega Ball"
FLASH_BOMB = "Flash Bomb"
THUNDER_CLAW = "Thunder Claw"
ICE_WAVE = "Ice Wave"
TORNADO_HOLD = "Tornado Hold"
WATER_BALLOON = "Water Balloon"
FLAME_SWORD = "Flame Sword"
HOMING_SNIPER = "Homing Sniper"
ASTRO_CRUSH = "Astro Crush"

WEAPON_SLOT = {
    MEGA_BALL: 1,
    FLASH_BOMB: 2, THUNDER_CLAW: 3, ICE_WAVE: 4, TORNADO_HOLD: 5,
    WATER_BALLOON: 6, FLAME_SWORD: 7, HOMING_SNIPER: 8, ASTRO_CRUSH: 9,
}

# The weapon each Robot Master awards in the base game (and whose slot the
# stage-clear routine writes).
BOSS_WEAPON = {
    FROST: ICE_WAVE, CLOWN: THUNDER_CLAW, TENGU: TORNADO_HOLD,
    GRENADE: FLASH_BOMB, SWORD: FLAME_SWORD, AQUA: WATER_BALLOON,
    ASTRO: ASTRO_CRUSH, SEARCH: HOMING_SNIPER,
}
WEAPONS = [BOSS_WEAPON[b] for b in ROBOT_MASTERS]

# ---- Rush --------------------------------------------------------------------
# Index = byte offset from the live adapter block 0x8016D300 (persistent copy
# at 0x801C3352). Each is awarded by one Robot Master stage's mid-boss: the
# stage overlays read exactly the byte their mid-boss grants. [D] Names [G].
RUSH_BIKE = "Rush Bike"
RUSH_ITEM = "Rush Item"
RUSH_BOMBER = "Rush Bomber"
RUSH_HEALTH = "Rush Health"
RUSH = [RUSH_BIKE, RUSH_ITEM, RUSH_BOMBER, RUSH_HEALTH]
RUSH_STAGE = {RUSH_BIKE: GRENADE, RUSH_ITEM: CLOWN,
              RUSH_BOMBER: SWORD, RUSH_HEALTH: AQUA}

# ---- Dr. Light's Lab parts ---------------------------------------------------
# In the game's own id order: the name table at 0x80152924, index 1..17. The
# guide names are matched by the game's OWN description of each part (the Lab
# text in LABO.PAC, which is in this same order), never by spelling - the
# internal names `charger` and `spear` are High Speed Charge and Spare Charger,
# the reverse of what their spelling suggests. [D] order, [G] names.
ENERGY_SAVER = "Energy Saver"
POWER_SHIELD = "Power Shield"
ENERGY_BALANCER = "Energy Balancer"
EXIT = "Exit"
SUPER_RECOVER = "Super Recover"
HIGH_SPEED_CHARGE = "High Speed Charge"
SHOOTING_PART = "Shooting Part"
SPARE_EXTRA = "Spare Extra"
BOOST_PART = "Boost Part"
RAPID_PART = "Rapid Part"
LASER_SHOT = "Laser Shot"
ARROW_SHOT = "Arrow Shot"
AUTO_SHOOT = "Auto Shoot"
SPARE_CHARGER = "Spare Charger"
HYPER_SLIDER = "Hyper Slider"
EXCHANGER = "Exchanger"
STEP_BOOSTER = "Step Booster"

PARTS = [
    ENERGY_SAVER, POWER_SHIELD, ENERGY_BALANCER, EXIT, SUPER_RECOVER,
    HIGH_SPEED_CHARGE, SHOOTING_PART, SPARE_EXTRA, BOOST_PART, RAPID_PART,
    LASER_SHOT, ARROW_SHOT, AUTO_SHOOT, SPARE_CHARGER, HYPER_SLIDER,
    EXCHANGER, STEP_BOOSTER,
]
PART_ID = {name: i + 1 for i, name in enumerate(PARTS)}

# VANILLA price in bolts and when the Lab stocks it. [D]: the shop table in the
# EXE at 0x801505F0 holds {part index, price} in shop order - records 0-9 the
# start stock (one blank), 10-17 the post-Duo stock. test_disc pins these to it.
# The patched Lab charges LAB_PRICE instead; logic uses that.
PART_COST = {
    ENERGY_SAVER: 6, POWER_SHIELD: 6, ENERGY_BALANCER: 5, EXIT: 4,
    SUPER_RECOVER: 5, HIGH_SPEED_CHARGE: 7, SHOOTING_PART: 6, SPARE_EXTRA: 6,
    BOOST_PART: 5, RAPID_PART: 6, LASER_SHOT: 5, ARROW_SHOT: 5,
    AUTO_SHOOT: 5, SPARE_CHARGER: 4, HYPER_SLIDER: 5, EXCHANGER: 4,
    STEP_BOOSTER: 5,
}
# What the PATCHED Lab charges - disc.LAB_PRICE, the vanilla prices scaled to
# total exactly 40, the game's own bolt count.
LAB_PRICE = {name: disc.LAB_PRICE[PART_ID[name]] for name in PARTS}

# The nine the Lab sells from the start; the other eight appear after Duo.
START_STOCK = [
    POWER_SHIELD, SPARE_EXTRA, SHOOTING_PART, ENERGY_BALANCER, EXIT,
    LASER_SHOT, ARROW_SHOT, AUTO_SHOOT, STEP_BOOSTER,
]
POST_DUO_STOCK = [p for p in PARTS if p not in START_STOCK]

# ---- Other items -------------------------------------------------------------
BOLTS = "Bolts"
EXTRA_LIFE = "1-Up"
LIFE_ENERGY = "Life Energy"
WEAPON_ENERGY = "Weapon Energy"
FILLER = [EXTRA_LIFE, LIFE_ENERGY, WEAPON_ENERGY]
FILLER_WEIGHTS = [(EXTRA_LIFE, 2), (LIFE_ENERGY, 3), (WEAPON_ENERGY, 3)]

# ---- Stage unlocks (option) ----------------------------------------------------
# The stage select turns a cursor POSITION into a stage index through EXE data
# at 0x801379A8 (one reader, 0x800FFF44), read off our disc [D]:
#   pos  0 Tengu  1 Frost  2 stage 0  3 Lab  4 Clown  5 Grenade
#        6 Astro  7 Sword  8 Duo      9 Wily 10 Search 11 Aqua   (12, 13: page switch)
# A position holding 0xFF confirms to nothing; 0 would load stage 0 (ram-notes 9f).
SELECT_TABLE_VANILLA = bytes.fromhex("0301000e02040705090a0806")
SELECT_POSITION = {boss: SELECT_TABLE_VANILLA.index(STAGE_INDEX[boss]) for boss in ROBOT_MASTERS}


def access_item(boss: str) -> str:
    return f"{boss} Access Codes"


ACCESS_ITEMS = [access_item(b) for b in ROBOT_MASTERS]

# ---- Events ------------------------------------------------------------------
VICTORY = "Victory"
DUO_CLEARED = "Duo Cleared"


def beaten(boss: str) -> str:
    """Event: a Robot Master is beaten. Separate from the boss's LOCATION,
    which holds a randomized item; this is what the stage gates test."""
    return f"{boss} Beaten"


# ---- Location names ----------------------------------------------------------
LAB = "Dr. Light's Lab"
MEGA_BALL_LOCATION = f"{INTRO} - Mega Ball"
DUO_CLEAR = f"{DUO} - Stage Clear"
WILY_CLEAR = {w: f"{w} - Clear" for w in WILY_STAGES}
# The one mid-stage boss in the Wily stages (every other boss bar there is a
# stage's end, whose clear is already a check): Bass, object id 0x5D in
# STAGE0C, fought at the first checkpoint [L 2026-09-25]. He is never killed -
# a hit that leaves him below 2 HP sets 1 and "defeated" (0x801E87F4) - so the
# check is his defeat state, not a death (client.bass_defeated).
WILY_3_BASS = f"{WILY_3} - Bass"


def boss_location(boss: str) -> str:
    return f"{boss} - Defeated"


def midboss_location(stage: str) -> str:
    return f"{stage} - Mid-boss"


def shop_location(part: str) -> str:
    """A Lab entry, named after the part the base game sells there."""
    return f"{LAB} - {part}"


def rematch_location(boss: str) -> str:
    """A Robot Master's refight in Wily Stage 4 (the rematch_checks option)."""
    return f"{WILY_4} - {boss} Rematch"


# The game's own refight record, 0x801C3378: bit k is the boss of stage k + 1
# (matched through 0x801387EC, ram-notes 9h) [D].
REMATCH_BIT = {boss: STAGE_INDEX[boss] - 1 for boss in ROBOT_MASTERS}
