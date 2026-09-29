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

# Sword Man's stage: after its opening, a hub of four teleporters, one trial
# per set-1 weapon (any order). Four pillars block the hub's corridor on
# (STAGE05 item 24, subIds 128-131, x 2328-2460, y 936): pillar k stays down
# until k + 1 trials are done - the count is 0x801C3378's low nibble, +1 at
# each trial's end switch (0x801E3DD8), tested by the pillar at 0x801E3FC0.
# So ALL FOUR trials stand before everything past the hub: the capsule in that
# corridor, the Rush mini-boss (his drop is the only way on, 0x801DF1E8) and
# the whole second half. Thunder Claw's pole swing and Tornado Hold's second
# room have no way round; Ice Wave's magma (a precise damage boost) and Flash
# Bomb's colour order (guessing) do, but logic takes no tricks. What lies past
# them is MM8World.sword_past_trials(). Which trial wants which weapon is
# walkthroughs + the disc map; the pillars are the disc (research repo:
# tester-feedback record item 8, and the 0.2.0 review's B1, which found them).
# Vanilla always reaches this stage holding all four, so nothing marked it.
SWORD_TRIALS = (TORNADO_HOLD, THUNDER_CLAW, ICE_WAVE, FLASH_BOMB)
# pickupsanity's two capsules past them (pickups.PICKUPS): record 1 at x 2512,
# y 952, in the pillars' corridor; record 49 at x 2928, y 5816, in the lava room
# of the stage's last bolt.
SWORD_HUB_CAPSULE = f"{SWORD} - Large Life Energy 1"
SWORD_LAVA_CAPSULE = f"{SWORD} - Large Life Energy 3"

# Search Man's second half: three doors only Tornado Hold opens (STAGE08 item
# 48, spawn records 105-107; the last at x 5888, just before his shutter).
# Shut, each is solid (0x80107BF4 at 0x801E0984) and fills its corridor's
# 64-px gap; it opens only on a hit 0x80109804 reports as 3 - weapon object 5,
# Tornado Hold (0x80109864; object ids by weapon slot at 0x80138900). The
# stage's bolts and capsules already carry Tornado Hold (bolts.
# stage_requirement); Search Man himself and his Beaten event did not, and ~1
# seed in 14 put Tornado Hold behind the doors. The audit that followed the
# 0.2.0 review's B1, same class; MM8World.search_past_doors().
SEARCH_DOORS = TORNADO_HOLD

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

# What each part does, because a player never sees it otherwise: the Lab's own
# description is replaced by the AP item's name, and the pause parts row stays
# empty. Worded from the game's text (the pause menu's part descriptions, plain
# ASCII in every STAGExx.PAC, e.g. STAGE00.PAC 0x26006), corrected where the
# EXE says the words mislead in a randomizer (research repo, tester-feedback
# record items 5-6; checked part by part against the EXE in the 0.2.0 review):
# Energy Saver swaps in a cost table ~2/3 of normal (0x8010BE20), read at
# spawn, so from the next life; Spare Extra is a lives FLOOR of 4 instead of 2 -
# at the Game Over restart (0x801213C4, called by the death handler at
# 0x80100FF4 with no lives left), in the save's pack and unpack (0x80120ED8,
# 0x80120FF4) and in Spare Charger's refill at stage entry (0x80100B80..BE0) -
# not a one-off gift at the start of a game. Power Shield also lengthens the
# post-hit invincibility, 90 -> 120 frames (0x8010CFC8). Energy Balancer only
# redirects energy with the Buster out or the weapon in hand full (0x8012908C),
# and with the Buster out and no Balancer a weapon capsule is not even taken.
# Exchanger hands full-life health to that same routine (0x80128FFC ->
# 0x80129044), so with the Buster out and no Balancer it does nothing - and
# the capsule is used up anyway. Auto Shoot fires only once fully charged,
# every 4th frame (0x8010FA10..2C), and gives up the charge shot (0x8010F880).
# PART_EFFECT_SHORT is the client's line when a part arrives (Ivor: "a couple
# words if possible"); PART_EFFECT is for the Lab text and the game page.
PART_EFFECT_SHORT = {
    ENERGY_SAVER: "weapons cost less",
    POWER_SHIELD: "no knockback",
    ENERGY_BALANCER: "refills lowest weapon",
    EXIT: "exit cleared stages",
    SUPER_RECOVER: "stronger pickups",
    HIGH_SPEED_CHARGE: "faster charging",
    SHOOTING_PART: "5 shots on screen",
    SPARE_EXTRA: "4-life restarts",
    BOOST_PART: "faster shots",
    RAPID_PART: "3-shot bursts",
    LASER_SHOT: "laser charge shot",
    ARROW_SHOT: "arrow charge shot",
    AUTO_SHOOT: "auto-fire once charged",
    SPARE_CHARGER: "lives refill",
    HYPER_SLIDER: "faster sliding",
    EXCHANGER: "full-life health to weapon",
    STEP_BOOSTER: "faster ladders",
}
PART_EFFECT = {
    ENERGY_SAVER: "Special weapons use about a third less energy.",
    POWER_SHIELD: "No knockback when hit, and you stay invincible longer after.",
    ENERGY_BALANCER: "Energy you pick up with the Buster out fills your emptiest weapon.",
    EXIT: "Leave a cleared stage from the pause menu.",
    SUPER_RECOVER: "Health and weapon energy pickups restore more.",
    HIGH_SPEED_CHARGE: "The charge shot charges faster.",
    SHOOTING_PART: "Up to 5 Buster shots on screen at once, not 3.",
    SPARE_EXTRA: "A Game Over or a loaded save gives you at least 4 lives, not 2.",
    BOOST_PART: "Buster shots fly faster.",
    RAPID_PART: "Each press fires three Buster shots.",
    LASER_SHOT: "Charge shot becomes a piercing laser. Pick it in the pause menu.",
    ARROW_SHOT: "Charge shot becomes a powerful arrow. Pick it in the pause menu.",
    AUTO_SHOOT: "Once charged, holding fire keeps firing. Pick it in the pause menu.",
    SPARE_CHARGER: "Entering a stage refills your lives to 2 (4 with Spare Extra).",
    HYPER_SLIDER: "You slide faster.",
    EXCHANGER: "At full life, health pickups refill the special weapon you hold.",
    STEP_BOOSTER: "You climb ladders faster.",
}
# With exit_stage_anytime on, every stage but the intro has Exit and the part does
# nothing (create_item makes it filler), so it says so instead.
EXIT_EFFECT_WITH_OPTION_SHORT = "no effect (Exit Stage Anytime is on)"
EXIT_EFFECT_WITH_OPTION = "No effect. Exit Stage Anytime lets you leave all but the intro."


def part_effects(exit_stage_anytime: bool) -> dict[str, str]:
    """PART_EFFECT for the Lab text, with Exit's line matching the seed."""
    effects = dict(PART_EFFECT)
    if exit_stage_anytime:
        effects[EXIT] = EXIT_EFFECT_WITH_OPTION
    return effects


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
SELECT_DUO_POSITION = SELECT_TABLE_VANILLA.index(STAGE_INDEX[DUO])     # 8, on page 2


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
