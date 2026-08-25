"""Rescuable Reploid dataset - all 128, derived by arithmetic.

X5 had to harvest its 14 Reploids out of disc placement records one stage at a
time. X6 does not: the save block is a fixed 64 bytes at
`0x800CCFA8..0x800CD027`, two Reploids per byte (low nibble first), and the
stage that owns each one falls straight out of the confirmed mapping

    stage bit index N  <->  Reploid indices N*16 .. N*16+15

which four separately-observed stages fit exactly (Yammark N=0, Wolfang N=1,
Turtloid N=5, Sheldon N=6 - see `mmx6-ram-notes.md`). So the full set is
generated here rather than transcribed, and there is no per-Reploid evidence
gap to disclose: the arithmetic is the evidence.

Nibble states, confirmed live: `0` not rescued, `2` rescued, `3` death,
`4` missing. **States 3 and 4 are permanent** - this is the A2 missability
problem, and it is routine rather than exotic: Reploid 97 went straight to
`4` in ordinary play while its neighbour was rescued on the same byte.

What is NOT known yet, and why there are no coordinates here: which of a
stage's 16 sits where. X6's placement table lives in per-stage streamed
overlay space with no stable pointer, so positions come from the empirical
harvest rather than an offline dump. The client does not need them to detect a
rescue (it watches the nibble), only to detect *proximity* - which is what
check-on-contact will eventually want. Add an `x, y` column then; the ordering
below is fixed and append-only, so ids will not move.
"""
from . import names

# (stage, global Reploid index 0-127, index within its stage 1-16, location name)
REPLOIDS: list[tuple[str, int, int, str]] = [
    (stage, base + i, i + 1, names.reploid_location(stage, i + 1))
    for stage, base in ((s, names.STAGE_REPLOIDS[s][0]) for s in names.STAGES)
    for i in range(16)
]

assert len(REPLOIDS) == 128
assert [r[1] for r in REPLOIDS] == list(range(128))

# Save-struct address and nibble for a global Reploid index.
REPLOID_BLOCK = 0x800CCFA8


def reploid_nibble(index: int) -> tuple[int, bool]:
    """(address, is_high_nibble) for global Reploid `index` (0-127)."""
    return REPLOID_BLOCK + index // 2, bool(index % 2)


# Nibble state values, live-confirmed.
NOT_RESCUED = 0
RESCUED = 2
DEAD = 3
MISSING = 4
LOST_STATES = (DEAD, MISSING)
