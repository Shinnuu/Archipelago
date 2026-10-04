"""Pickupsanity: every freestanding consumable in a stage.

Harvested statically from the stage packs' spawn lists (chunk 0xA of each
STDATA/STAGExx.PAC, 8-byte records {flags, id, subId, type, x, y}; A and B
packs carry identical lists) and cross-checked against the disc: 42 placed
id-0 items in the whole game, and every one is here. Research: ram-notes 9g,
Reference/research/2026-09-24_parity-D-*. Plus one capsule the game spawns
from code, from a block the player breaks (CONTAINERS) - found by a tester,
2026-10-03, and then by a sweep of every item spawn in the overlays (ram-notes
12d): the only one of its kind that is a location.

A consumable is item-array id 0 and its subId is its kind. There is no
"collected" record: a taken pickup's spawn record stays marked until the next
section start re-arms it, so every pickup returns after a death, a midpoint
or a re-entry - which is what lets an unconfirmed one keep coming back (X5's
"respawns until the server confirms").

IDENTITY. Every stage's list loads to the same buffer (0x801C2B3C), so record
addresses repeat across stages; a pickup is (stage index, record index). A
container's capsule is its BLOCK's record, which the disc patch copies into
the capsule (disc.FROST_BLOCK_DROP); its key carries CONTAINER_KEY, so the
stub matches it only against a record that is not a placed consumable.

EVERY STAGE CAN BE GONE BACK TO (playtest 2026-09-25): the intro replays from
the select's slot below Tengu Man, and a Wily stage is played again after an
Exit (the same stage) or a save reload (the Wily counter is not saved, so the
fortress restarts at Wily 1). X5 leaves out only an intro it cannot revisit.

NOT LOCATIONS (Ivor): Clown Man's 1-UP container (id 44, broken by the Mega
Ball, its own grant at STAGE02 0x801E4AD8) and the fixed drops of Grenade
Man's main id 8. Frost's other drop-carrying block (record 148) takes no
weapon at all (damage table 0, ram-notes 12c).

WHAT ONE NEEDS (0.2.1, Ivor 2026-10-03; research repo plan
2026-10-03_per-bolt-logic.md section 4). No guide covers capsules. One that
shares a gated bolt's pocket or stretch of course takes that bolt's rule
(the stage maps: Aqua's Large Life Energy 1 is in bolt 24's small room, his
Large Weapon Energy 2 and Large Life Energy 2 on bolt 25's ledge); one on the
course with no gated bolt in its stretch - stretches bounded by the stages'
checkpoints (0x80138288) - needs nothing; the three the maps cannot settle
keep their stage's 0.2.0 rule. REQUIREMENT lists every capsule that needs
something; Sword Man's also wait on his trials (MM8World.sword_past_trials).
Until 0.2.1 every capsule carried every bolt rule of its stage.
"""
from . import bolts, names
from .bolts import FREE, Requirement, req

SPAWN_LIST = 0x801C2B3C       # where every stage's list is loaded; 8 bytes a record

KIND = {0: "Small Life Energy", 1: "Large Life Energy", 2: "Small Weapon Energy",
        3: "Large Weapon Energy", 4: "1-UP", 5: "Weapon Energy Refill", 6: "Full Recovery"}

# (stage index, record index, subId, location name). Duplicate names are
# numbered in record order, as X5 does. Coordinates are the record's, in
# stage pixels.
PICKUPS: list[tuple[int, int, int, str]] = [
    (1,  14, 1, "Frost Man - Large Life Energy 1"),     # x 5168, y 888
    (1,  40, 1, "Frost Man - Large Life Energy 2"),     # x 2320, y 5256
    (1,  45, 1, "Frost Man - Large Life Energy 3"),     # x 3584, y 5192
    (1,  55, 1, "Frost Man - Large Life Energy 4"),     # x 4944, y 6072
    (1,  56, 3, "Frost Man - Large Weapon Energy 1"),   # x 4976, y 6072
    (1,  60, 0, "Frost Man - Small Life Energy 1"),     # x 3904, y 6688 - a row of 11
    (1,  61, 0, "Frost Man - Small Life Energy 2"),     # x 4160, y 6688
    (1,  62, 0, "Frost Man - Small Life Energy 3"),     # x 4416, y 6688
    (1,  63, 0, "Frost Man - Small Life Energy 4"),     # x 4672, y 6688
    (1,  64, 0, "Frost Man - Small Life Energy 5"),     # x 4928, y 6688
    (1,  65, 0, "Frost Man - Small Life Energy 6"),     # x 5184, y 6688
    (1,  66, 2, "Frost Man - Small Weapon Energy 1"),   # x 4032, y 6688
    (1,  67, 2, "Frost Man - Small Weapon Energy 2"),   # x 4288, y 6688
    (1,  68, 3, "Frost Man - Large Weapon Energy 2"),   # x 4544, y 6688
    (1,  69, 2, "Frost Man - Small Weapon Energy 3"),   # x 4800, y 6688
    (1,  70, 5, "Frost Man - Weapon Energy Refill"),    # x 5056, y 6688
    (3,  62, 1, "Tengu Man - Large Life Energy 1"),     # x 3392, y 6344
    (3,  68, 1, "Tengu Man - Large Life Energy 2"),     # x 4960, y 6312
    (4,  67, 1, "Grenade Man - Large Life Energy 1"),   # x 1688, y 2600
    (4,  91, 1, "Grenade Man - Large Life Energy 2"),   # x 3768, y 2768
    (5,   1, 1, "Sword Man - Large Life Energy 1"),     # x 2512, y 952
    (5,  26, 1, "Sword Man - Large Life Energy 2"),     # x 3752, y 1976
    (5,  49, 1, "Sword Man - Large Life Energy 3"),     # x 2928, y 5816
    (6,  35, 3, "Aqua Man - Large Weapon Energy 1"),    # x 880, y 3688
    (6,  60, 1, "Aqua Man - Large Life Energy 1"),      # x 2262, y 4040
    (6,  84, 3, "Aqua Man - Large Weapon Energy 2"),    # x 4440, y 5240
    (6,  85, 1, "Aqua Man - Large Life Energy 2"),      # x 4416, y 5240
    (6, 127, 1, "Aqua Man - Large Life Energy 3"),      # x 4792, y 4360
    (6, 162, 1, "Aqua Man - Large Life Energy 4"),      # x 4864, y 6472
    (6, 163, 3, "Aqua Man - Large Weapon Energy 3"),    # x 4832, y 6472
    (6, 180, 1, "Aqua Man - Large Life Energy 5"),      # x 5680, y 7080
    (7,  37, 1, "Astro Man - Large Life Energy"),       # x 1456, y 2984
    (7,  38, 3, "Astro Man - Large Weapon Energy"),     # x 1480, y 2984
    (8,  46, 1, "Search Man - Large Life Energy"),      # x 3552, y 1432
    (8,  47, 3, "Search Man - Large Weapon Energy"),    # x 3584, y 1432
    # Appended 2026-09-25 (ids are append-only): the intro's and Wily 1-3's.
    (0,  19, 1, "Intro Stage - Large Life Energy"),     # x 3392, y 456
    (10, 59, 3, "Wily Stage 1 - Large Weapon Energy"),  # x 4080, y 5832
    (10, 60, 4, "Wily Stage 1 - 1-UP"),                 # x 4344, y 5736
    (11, 69, 1, "Wily Stage 2 - Large Life Energy"),    # x 5376, y 4280
    (12, 34, 1, "Wily Stage 3 - Large Life Energy 1"),  # x 3280, y 3160
    (12, 44, 1, "Wily Stage 3 - Large Life Energy 2"),  # x 4464, y 3288
    (12, 47, 4, "Wily Stage 3 - 1-UP"),                 # x 5008, y 3160
    # Appended 2026-10-03: the ice block's capsule (CONTAINERS).
    (1, 158, 1, "Frost Man - Large Life Energy 5"),     # x 3890, y 4704
]
# The placed consumables that are NOT locations (for the tests' completeness
# check): (stage, record). None since 2026-09-25.
NOT_LOCATIONS: list[tuple[int, int]] = []

# Capsules a broken block spawns from code: (stage, the BLOCK's record) ->
# what it is. Frost's ice block (STAGE01 main id 12, ram-notes 12d): its type
# is subId & 0xF, and its death drops 0x801E68C4[type] - a Large Life Energy
# for types 2 and 5. Record 158 is type 5, on the ledge 200 px above bolt
# subId 5 ("Frost Man - Bolt 6"), and takes Flash Bomb, Flame Sword and Astro
# Crush (damage table 18).
CONTAINERS: dict[tuple[int, int], str] = {
    (1, 158): "Frost Man's ice block (main id 12, type 5)",
}
CONTAINER_KEY = 0x8000          # stage << 8 | record never reaches bit 15

STAGE_OF = {index: stage for stage, index in names.STAGE_INDEX.items()}


def key(stage: int, record: int) -> int:
    """The stub's identity for a pickup: stage << 8 | record index, with
    CONTAINER_KEY on a container's."""
    return stage << 8 | record | (CONTAINER_KEY if (stage, record) in CONTAINERS else 0)


# Bit i of the AP block's FOUND / CONFIRMED words is PICKUPS[i].
KEYS = [key(stage, record) for stage, record, _sub, _name in PICKUPS]


# Every capsule that needs something beyond its stage's entrance (the rule in
# the docstring); the rest are free.
REQUIREMENT: dict[str, Requirement] = {
    # Frost: row 5 of the course, between checkpoints 2 and 3, with bolts 3 and 4.
    "Frost Man - Large Life Energy 2": bolts.requirement(3),
    "Frost Man - Large Life Energy 3": bolts.requirement(4),
    # The ice block, beside the ladder the route leaves the shaft by: Astro
    # Crush (Ivor, 2026-10-03; the block also takes Flash Bomb and Flame Sword).
    "Frost Man - Large Life Energy 5": req((names.ASTRO_CRUSH,)),
    # Grenade: 200 px up a shaft over the course - the map cannot say how.
    "Grenade Man - Large Life Energy 1": req((names.MEGA_BALL,), (names.FLAME_SWORD,)),
    # Aqua: bolt 27's chamber, bolt 24's pocket, bolt 25's ledge.
    "Aqua Man - Large Weapon Energy 1": bolts.requirement(27),
    "Aqua Man - Large Life Energy 1": bolts.requirement(24),
    "Aqua Man - Large Weapon Energy 2": bolts.requirement(25),
    "Aqua Man - Large Life Energy 2": bolts.requirement(25),
    # Search: the hook room, beside Flame-Sword-only objects.
    "Search Man - Large Life Energy": req((names.TORNADO_HOLD,), (names.THUNDER_CLAW,), (names.FLAME_SWORD,)),
    "Search Man - Large Weapon Energy": req((names.TORNADO_HOLD,), (names.THUNDER_CLAW,), (names.FLAME_SWORD,)),
}


def requirement(name: str) -> Requirement:
    """What logic demands for capsule `name`, its stage's entrance apart."""
    return REQUIREMENT.get(name, FREE)
