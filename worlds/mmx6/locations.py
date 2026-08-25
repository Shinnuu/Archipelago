from BaseClasses import Location

from . import names
from .items import BASE_ID
from .reploids import REPLOIDS


class MMX6Location(Location):
    game = "Mega Man X6"


# Location id layout. Append only, never reorder - the datapackage is a
# contract and a moved id silently mis-credits checks on existing seeds.
#
#   +0          intro clear
#   +100..179   per-stage blocks of 10, in names.STAGES order
#   +180..199   reserved: endgame stage clears (Gate / Secret Lab), once the
#               endgame's stage list and its progress byte are verified.
#   +200..327   the 128 Reploids, in reploids.REPLOIDS order
#   +400..      reserved: pickupsanity. X6's placement table lives in
#               per-stage streamed overlay space, so the freestanding-pickup
#               inventory is still being harvested; the block is reserved now
#               so the harvest does not have to renumber anything later.
location_table: dict[str, int] = {names.INTRO_CLEAR: BASE_ID + 0}

for i, stage in enumerate(names.STAGES):
    base = BASE_ID + 100 + i * 10
    # Checked at the MISSION REPORT, not at the kill: 0x800CCF30's beaten bit
    # commits ~290 frames into screen 0C. Same hook covers the Reploid rewards.
    location_table[names.boss_location(stage)] = base + 0
    location_table[names.heart_location(stage)] = base + 1
    # Every stage holds exactly one armor part - four Blade, four Shadow.
    location_table[names.capsule_location(stage)] = base + 2
    if stage in names.STAGE_TANK:
        location_table[names.tank_location(stage)] = base + 3
    # +4.. reserved

# Reploid rescues, ids +200 in REPLOIDS order (stage order, then 1-16 within
# the stage). Always in the id map - the datapackage carries every location the
# game can define - but only created as real locations when the option is on.
for _stage, index, _n, name in REPLOIDS:
    location_table[name] = BASE_ID + 200 + index

event_location_table: dict[str, int | None] = {
    names.VICTORY: None,
}

location_groups = {
    "Bosses": {names.boss_location(s) for s in names.STAGES},
    "Heart Tanks": {names.heart_location(s) for s in names.STAGES},
    "Armor Capsules": {names.capsule_location(s) for s in names.STAGES},
    "Tanks": {names.tank_location(s) for s in names.STAGE_TANK},
    "Reploids": {name for _s, _i, _n, name in REPLOIDS},
    **{f"{stage} Reploids": {name for s, _i, _n, name in REPLOIDS if s == stage}
       for stage in names.STAGES},
}
