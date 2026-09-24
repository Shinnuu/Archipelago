from BaseClasses import Location

from . import names
from .bolts import BOLT_LOCATIONS, BOLT_STAGE
from .items import BASE_ID


class MM8Location(Location):
    game = "Mega Man 8"


# Location id layout. Append only, never reorder - a moved id silently
# mis-credits checks on existing seeds.
#
#   +0..+7      Robot Master defeats, in names.ROBOT_MASTERS order
#   +10..+13    Rush mid-bosses, in names.RUSH order (the adapter each awards)
#   +20         the intro stage's Mega Ball
#   +21         Duo's stage cleared
#   +22..+24    Wily stages 1-3 cleared (Wily 4 is the goal event, not a check)
#   +100..+139  bolts, BASE + 100 + subId - the subId IS the bit in 0x8016D2FB
#   +200..+217  Lab entries, BASE + 200 + the part id the base game sells there
location_table: dict[str, int] = {}

for i, boss in enumerate(names.ROBOT_MASTERS):
    location_table[names.boss_location(boss)] = BASE_ID + i

for i, adapter in enumerate(names.RUSH):
    location_table[names.midboss_location(names.RUSH_STAGE[adapter])] = BASE_ID + 10 + i

location_table[names.MEGA_BALL_LOCATION] = BASE_ID + 20
location_table[names.DUO_CLEAR] = BASE_ID + 21
for i, wily in enumerate(names.WILY_STAGES[:3]):
    location_table[names.WILY_CLEAR[wily]] = BASE_ID + 22 + i

for sub_id, name in BOLT_LOCATIONS.items():
    location_table[name] = BASE_ID + 100 + sub_id

for part in names.PARTS:
    location_table[names.shop_location(part)] = BASE_ID + 200 + names.PART_ID[part]


location_groups = {
    "Robot Masters": {names.boss_location(b) for b in names.ROBOT_MASTERS},
    "Mid-bosses": {names.midboss_location(names.RUSH_STAGE[r]) for r in names.RUSH},
    "Bolts": set(BOLT_LOCATIONS.values()),
    "Dr. Light's Lab": {names.shop_location(p) for p in names.PARTS},
    **{f"{stage} Bolts": {name for s, name in BOLT_LOCATIONS.items()
                          if BOLT_STAGE[s] == stage}
       for stage in sorted(set(BOLT_STAGE.values()))},
}
