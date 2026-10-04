"""The 40 bolts: where each one is, and what it takes to reach it.

WHERE is settled, from the disc. A bolt is an item-array object with handler
id 37 whose subId is its bit in the 40-bit collected field at 0x8016D2FB, and
every stage pack's spawn list names its bolts that way (bolt 14 alone is
spawned by Tengu Man's overlay code). `mm8_bolt_harvest.py` in the research
repo reproduces the table below and fails if it stops holding. [D]

WHAT IT TAKES comes from the videochums bolt guide [G], which numbers each
stage's bolts in PLAY order. Since 0.2.1 each bolt carries its OWN entry
(Ivor, 2026-10-03; research repo `ai-docs/plans/2026-10-03_per-bolt-logic.md`):
a bolt's guide number is its place in PLAY_ORDER, read from the disc's maps.
Everything on file agrees with that pairing - the disc ANCHORS below, the
stages' checkpoint tables (0x80138288, ram-notes 12a), every order the
ramwatch logged and, for Search Man's 36 before 35, the guide's own text
(the 0.2.1 review).
Until 0.2.1 every bolt in a stage carried every guide entry of the stage,
which made a whole stage wait on its hardest bolt (all of Frost Man's on
Astro Crush, a tester's report).

The guide is read strictly, as X6 learned to (two unwinnable seeds from a
loose reading), and corrected in three ways, each only ever stricter:
- GROUPS: where two bolts' entries cannot be told apart on the disc, each
  carries both.
- EXTRA: the guide gives what a bolt ADDS on the way from the one before, not
  everything it needs. Duo's second bolt is past his first one's ladder.
  Also where the disc cannot show the way in (Clown Man's last bolt).
  (Search Man's last bolt is behind his Tornado Hold doors and Sword Man's
  behind his trials: MM8World.search_past_doors / sword_past_trials.)
- OVERRIDE: a tester's first-hand account where it asks for more.
"""
from . import names as n

# subId -> stage. The subId is the location's identity (ids +100..+139).
BOLT_STAGE: dict[int, str] = {
    **{s: n.INTRO for s in (0, 1, 33)},
    **{s: n.FROST for s in (2, 3, 4, 5, 6, 23)},
    **{s: n.CLOWN for s in (7, 8, 9, 10, 22)},
    **{s: n.TENGU for s in (11, 12, 13, 14)},
    **{s: n.GRENADE for s in (15, 16, 17, 18, 32)},
    **{s: n.SWORD for s in (19, 20, 21)},
    **{s: n.AQUA for s in (24, 25, 26, 27)},
    **{s: n.ASTRO for s in (28, 29, 30, 31)},
    **{s: n.SEARCH for s in (34, 35, 36, 37)},
    **{s: n.DUO for s in (38, 39)},
}

# A requirement is CNF: a tuple of clauses, each satisfied by ANY one of its
# items; the bolt needs every clause. () needs nothing.
Clause = frozenset[str]
Requirement = tuple[Clause, ...]


def req(*clauses: tuple[str, ...]) -> Requirement:
    return tuple(frozenset(c) for c in clauses)


FREE: Requirement = ()

# The guide's requirements, per stage, in the guide's own numbering (#1 first).
# Quoted in the research repo's external-findings; "easily" and "or" readings
# are taken strictly (Clown #1 says the Rush Bike makes the jump EASY, which
# is not the same as optional - required here).
GUIDE: dict[str, list[Requirement]] = {
    n.INTRO: [FREE, FREE, FREE],
    n.TENGU: [FREE, req((n.HOMING_SNIPER, n.ASTRO_CRUSH)), FREE, FREE],
    n.FROST: [FREE, FREE, req((n.MEGA_BALL,)), req((n.MEGA_BALL,)),
              req((n.ASTRO_CRUSH,)),
              req((n.MEGA_BALL,), (n.ASTRO_CRUSH, n.FLAME_SWORD, n.FLASH_BOMB))],
    n.CLOWN: [req((n.RUSH_BIKE,)), FREE,
              req((n.MEGA_BALL,), (n.FLAME_SWORD,)), FREE,
              req((n.TORNADO_HOLD,))],
    n.GRENADE: [req((n.MEGA_BALL,)), FREE, req((n.FLAME_SWORD,)), FREE, FREE],
    n.DUO: [req((n.MEGA_BALL,)), req((n.THUNDER_CLAW,))],
    n.ASTRO: [FREE, FREE, FREE, req((n.MEGA_BALL, n.TORNADO_HOLD))],
    n.SWORD: [FREE, FREE, req((n.FLASH_BOMB,))],
    n.SEARCH: [FREE, req((n.TORNADO_HOLD,), (n.THUNDER_CLAW,)),
               req((n.FLAME_SWORD,)), req((n.THUNDER_CLAW,))],
    n.AQUA: [req((n.ASTRO_CRUSH,)), req((n.TORNADO_HOLD,)),
             req((n.ASTRO_CRUSH,)), FREE],
}

# subId -> (stage, guide number), where the DISC ties a bolt to a guide entry.
# Each must agree with PLAY_ORDER - the control on the pairing (test_tables).
ANCHORS: dict[int, tuple[str, int]] = {
    14: (n.TENGU, 2),     # its parent's damage table takes Homing Sniper / Astro Crush only (ram-notes 6b)
    7: (n.CLOWN, 3),      # spawned inside id 61, which only Flame Sword damages (10c)
    27: (n.AQUA, 1),      # behind the Astro-Crush-only trigger, main 48 (11e)
    24: (n.AQUA, 2),      # sealed in by the mines only Tornado Hold clears, id 66 (11e)
    6: (n.FROST, 5),      # under STAGE01 main id 20, a floor only Astro Crush opens (12f)
    35: (n.SEARCH, 3),    # shut in by id 84, which only Flame Sword damages (12b); a tester
                          # took it with Flame Sword and no Thunder Claw (2026-10-04)
}

# Bolts whose entries the disc cannot tell apart: each carries every
# member's guide entry.
GROUPS: list[tuple[int, ...]] = [
    (25, 26),   # Aqua: the route climbs the left sub-shaft and descends the right; 25 is a detour (12a)
]

# What a bolt needs beyond its own guide entry.
EXTRA: dict[int, Requirement] = {
    39: req((n.MEGA_BALL,)),    # Duo #2 is past #1's hanging ladder (10b)
    # Clown #5: the guide hovers up on Tornado Hold, but the map shows its room
    # walled in (the 0.2.1 review, 12f); the Mega Ball in case the way in also
    # takes the "Mega Ball jumps" a tester used in this stage (Ivor, 2026-10-03).
    9: req((n.MEGA_BALL,)),
}

# A tester's account where it asks for more than the guide.
OVERRIDE: dict[int, Requirement] = {
    # Clown Bolt 4, at the top of the lift room: the guide asks nothing; the
    # tester (2026-10-03) gets up there with Mega Ball jumps or Tornado Hold.
    # Clown Bolt 3 beside it keeps the guide's Mega Ball + Flame Sword.
    8: req((n.MEGA_BALL, n.TORNADO_HOLD)),
}


def guide_number(sub_id: int) -> int:
    """The guide's number for a bolt: its place in its stage's PLAY_ORDER."""
    return PLAY_ORDER[BOLT_STAGE[sub_id]].index(sub_id) + 1


def requirement(sub_id: int) -> Requirement:
    """Everything logic demands for bolt `sub_id` (the stage's entrance
    apart): its own guide entry, or its group's, plus EXTRA - or OVERRIDE."""
    if sub_id in OVERRIDE:
        return OVERRIDE[sub_id]
    stage = BOLT_STAGE[sub_id]
    group = next((g for g in GROUPS if sub_id in g), (sub_id,))
    clauses: list[Clause] = []
    for member in group:
        for clause in GUIDE[stage][guide_number(member) - 1] + EXTRA.get(member, FREE):
            if clause not in clauses:
                clauses.append(clause)
    return tuple(clauses)


# The order a player meets each stage's bolts - what the location names
# number, so "Clown Man - Bolt 3" is the third bolt you come to (Ivor could
# not find one named in subId order, 2026-09-24). Read from the disc
# (2026-09-25, research repo ram-notes 10d): each stage's route off its
# collision map (Scripts/mm8_stage_map.py), with the spawn list's own order
# as the starting guess - the two agree except in the intro, whose route
# drops in beside bolt 33, and in Tengu Man, whose bolt 14 is spawned by an
# object listed late but met second (and pinned as the guide's #2). Every
# play order the ramwatch logged agrees: Clown 10, 22, 7, 8; Grenade 32
# before 17; Tengu 11 before 12; the intro's 33 first. Frost Man's 6 then 5:
# 6 under the Astro Crush floor at the shaft's foot, 5 on the climb (12f).
# Search Man's 36 then 35, as the guide's text has them (0.2.1, Ivor; the
# names were the other way round until then).
# Since 0.2.1 this order is also each bolt's guide number (guide_number).
PLAY_ORDER: dict[str, list[int]] = {
    n.INTRO: [33, 1, 0],
    n.FROST: [2, 23, 3, 4, 6, 5],
    n.CLOWN: [10, 22, 7, 8, 9],
    n.TENGU: [11, 14, 12, 13],
    n.GRENADE: [15, 32, 16, 17, 18],
    n.SWORD: [19, 20, 21],
    n.AQUA: [27, 24, 25, 26],
    n.ASTRO: [28, 29, 30, 31],
    n.SEARCH: [34, 36, 35, 37],
    n.DUO: [38, 39],
}


def location_name(sub_id: int) -> str:
    """"Frost Man - Bolt 3" - the third bolt a player meets in Frost Man's
    stage (PLAY_ORDER). The location's ID is still its subId."""
    stage = BOLT_STAGE[sub_id]
    return f"{stage} - Bolt {PLAY_ORDER[stage].index(sub_id) + 1}"


BOLT_LOCATIONS: dict[int, str] = {s: location_name(s) for s in sorted(BOLT_STAGE)}
