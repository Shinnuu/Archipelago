"""The 40 bolts: where each one is, and what it takes to reach it.

WHERE is settled, from the disc. A bolt is an item-array object with handler
id 37 whose subId is its bit in the 40-bit collected field at 0x8016D2FB, and
every stage pack's spawn list names its bolts that way (bolt 14 alone is
spawned by Tengu Man's overlay code). `mm8_bolt_harvest.py` in the research
repo reproduces the table below and fails if it stops holding. [D]

WHAT IT TAKES comes from the videochums bolt guide [G], which numbers each
stage's bolts in PLAY order. Which subId is which guide number has NOT been
read for most stages - coordinates alone do not settle it - so a requirement
cannot yet be attached to the right bolt. Until it can, every unpinned bolt in
a stage carries the requirements of EVERY unpinned guide bolt in that stage.
That can only over-gate: it narrows where fill may put things, and it can
never ask a player for a bolt they cannot reach. X6 shipped two unwinnable
seeds by guessing the loose way; this is the other way.

A bolt is PINNED when the disc itself says which guide bolt it is. Bolt 14 is
pinned: its parent object's damage table accepts only Homing Sniper and Astro
Crush, which is exactly the guide's Tengu #2 (ram-notes 6b).
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


def _req(*clauses: tuple[str, ...]) -> Requirement:
    return tuple(frozenset(c) for c in clauses)


FREE: Requirement = ()

# The guide's requirements, per stage, in the guide's own numbering (#1 first).
# Quoted in the research repo's external-findings; "easily" and "or" readings
# are taken strictly (Clown #1 says the Rush Bike makes the jump EASY, which
# is not the same as optional - required here).
GUIDE: dict[str, list[Requirement]] = {
    n.INTRO: [FREE, FREE, FREE],
    n.TENGU: [FREE, _req((n.HOMING_SNIPER, n.ASTRO_CRUSH)), FREE, FREE],
    n.FROST: [FREE, FREE, _req((n.MEGA_BALL,)), _req((n.MEGA_BALL,)),
              _req((n.ASTRO_CRUSH,)),
              _req((n.MEGA_BALL,), (n.ASTRO_CRUSH, n.FLAME_SWORD, n.FLASH_BOMB))],
    n.CLOWN: [_req((n.RUSH_BIKE,)), FREE,
              _req((n.MEGA_BALL,), (n.FLAME_SWORD,)), FREE,
              _req((n.TORNADO_HOLD,))],
    n.GRENADE: [_req((n.MEGA_BALL,)), FREE, _req((n.FLAME_SWORD,)), FREE, FREE],
    n.DUO: [_req((n.MEGA_BALL,)), _req((n.THUNDER_CLAW,))],
    n.ASTRO: [FREE, FREE, FREE, _req((n.MEGA_BALL, n.TORNADO_HOLD))],
    n.SWORD: [FREE, FREE, _req((n.FLASH_BOMB,))],
    n.SEARCH: [FREE, _req((n.TORNADO_HOLD,), (n.THUNDER_CLAW,)),
               _req((n.FLAME_SWORD,)), _req((n.THUNDER_CLAW,))],
    n.AQUA: [_req((n.ASTRO_CRUSH,)), _req((n.TORNADO_HOLD,)),
             _req((n.ASTRO_CRUSH,)), FREE],
}

# subId -> (stage, guide number), only where the DISC identifies the bolt.
PINNED: dict[int, tuple[str, int]] = {
    14: (n.TENGU, 2),
}


def requirement(sub_id: int) -> Requirement:
    """What logic demands for bolt `sub_id`: its own guide requirement when
    pinned, otherwise the conjunction of every unpinned guide bolt it could be."""
    if sub_id in PINNED:
        stage, number = PINNED[sub_id]
        return GUIDE[stage][number - 1]
    stage = BOLT_STAGE[sub_id]
    taken = {number for s, number in PINNED.values() if s == stage}
    clauses: list[Clause] = []
    for number, req in enumerate(GUIDE[stage], start=1):
        if number in taken:
            continue
        for clause in req:
            if clause not in clauses:
                clauses.append(clause)
    return tuple(clauses)


def location_name(sub_id: int) -> str:
    """"Frost Man - Bolt 3" - numbered 1..N within the stage in subId order,
    which is the game's internal order, NOT the guide's play order."""
    stage = BOLT_STAGE[sub_id]
    ordinal = sorted(s for s, st in BOLT_STAGE.items() if st == stage).index(sub_id) + 1
    return f"{stage} - Bolt {ordinal}"


BOLT_LOCATIONS: dict[int, str] = {s: location_name(s) for s in sorted(BOLT_STAGE)}
