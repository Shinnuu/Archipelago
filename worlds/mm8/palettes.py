"""Mega Man's colours - X5's palettes.py, ported (research: ram-notes 9e).

Cosmetic only. Chosen in the player's YAML, baked into the .apmm8 at
generation, and applied when the patch is opened; host.yaml can override it
there with a real colour, so a colour can change without a new seed.

WHERE MEGA MAN'S COLOURS LIVE [D]
---------------------------------
`STDATA/PLAYER.PAC` chunk 2 holds 16 CLUTs (loaded to 0x8018FC40): CLUT n is
weapon slot n's colours (0 the Mega Buster, 1 Mega Ball, 2-9 the boss
weapons), 10/11 the power-up flash, 12/13 the charge frames (13 == 10),
14/15 the full-charge glow. The weapon switch copies CLUT[current weapon]
into working CLUT 8, which is what Mega Man is drawn with. The buster CLUT
also sits, without its STP bits, in chunk 9 of every stage, demo and
weapon-get pack (27 copies) - the colours in force from a section start until
the player spawns.

WHICH ENTRIES GET REPAINTED
---------------------------
The game's own weapon palettes change entries 1-9 and never 10-15, which is
the game's definition of the recolourable part: 1-4 the light ramp, 5-8 the
dark ramp, 9 the outline; 10 highlight, 11 a red detail, 12-15 the face.
So the ramps are 1-4 and 5-9, as two separate light-to-dark runs (X5's rule).

The power-up flash (10, 11) and the charge frames (12, and 13 == 10) are the
body lightened, so they take the same preset - otherwise a red Mega Man would
flash blue while charging. The full-charge glow (14, 15) and the weapon
colours (1-9) stay: those are how you read the charge and the weapon.
"""
import colorsys
import logging
import struct
from typing import Iterable

logger = logging.getLogger()

VANILLA = "vanilla"
RANDOM = "random"
UNSET = "unset"          # host.yaml only: "no override here" (see overrides())

# X5's presets, unchanged: name -> (hue 0-1, saturation, value scale).
PRESETS: dict[str, tuple[float, float, float]] = {
    "crimson":  (0.995, 0.90, 1.00),
    "scarlet":  (0.030, 0.92, 1.00),
    "amber":    (0.075, 0.95, 1.02),
    "gold":     (0.115, 0.95, 1.05),
    "olive":    (0.180, 0.70, 0.90),
    "forest":   (0.330, 0.72, 0.88),
    "emerald":  (0.400, 0.80, 0.95),
    "teal":     (0.470, 0.75, 0.95),
    "cyan":     (0.520, 0.80, 1.00),
    "azure":    (0.570, 0.85, 1.00),
    "blue":     (0.615, 0.85, 1.00),
    "indigo":   (0.680, 0.80, 0.95),
    "violet":   (0.780, 0.75, 0.95),
    "magenta":  (0.850, 0.85, 1.00),
    "rose":     (0.920, 0.70, 1.00),
    "silver":   (0.600, 0.10, 1.05),
    "black":    (0.720, 0.45, 0.42),
    "white":    (0.600, 0.05, 1.15),
}
CHOICES: tuple[str, ...] = (VANILLA, RANDOM) + tuple(sorted(PRESETS))
# The YAML Choice's values. RANDOM is Archipelago's own on every Choice.
OPTION_KEYS: tuple[str, ...] = (VANILLA,) + tuple(sorted(PRESETS))

RAMPS = (range(1, 5), range(5, 10))       # light ramp, dark ramp + outline

_BUSTER = (0x0000, 0xFF40, 0xEA40, 0xCDA0, 0xB545, 0xFE4A, 0xFD80, 0xE500,
           0xC480, 0xA4A5, 0xEF7B, 0x9816, 0xC27D, 0xA9D8, 0x9D32, 0x98ED)
# target -> [(stock 16-entry CLUT, ramps, copies expected on the disc)]
TARGETS: dict[str, list[tuple[tuple[int, ...], tuple[range, ...], int]]] = {
    "mega_man": [
        (_BUSTER, RAMPS, 1),                                           # PLAYER.PAC CLUT 0
        (tuple(c & 0x7FFF for c in _BUSTER), RAMPS, 27),               # chunk 9 of every pack
        ((0x0000, 0xFFEB, 0xFF09, 0xF223, 0xD9E5, 0xFF4A, 0xFEC7, 0xEE65,
          0xD5A3, 0xD165, 0xFFFF, 0xA4BC, 0xC35D, 0xAABA, 0x9E57, 0x99B2), RAMPS, 2),   # 10 and 13
        ((0x0000, 0xFFFF, 0xF338, 0xE691, 0xD9EB, 0xFFF5, 0xF371, 0xE6ED,
          0xDA69, 0xD1E5, 0xFFFF, 0xC5BF, 0xC39F, 0xBB1D, 0xB2BB, 0xAE59), RAMPS, 1),   # 11
        ((0x0000, 0xFFE4, 0xEB03, 0xCE23, 0xB5E5, 0xFEAA, 0xFE27, 0xE5C5,
          0xC503, 0xA905, 0xF7BD, 0x981B, 0xC31D, 0xAA78, 0x9DD2, 0x996D), RAMPS, 1),   # 12
    ],
}


def _to_rgb(colour: int) -> tuple[float, float, float]:
    colour &= 0x7FFF
    return ((colour & 0x1F) / 31.0,
            ((colour >> 5) & 0x1F) / 31.0,
            ((colour >> 10) & 0x1F) / 31.0)


def _to_bgr555(r: float, g: float, b: float, stp: int) -> int:
    q = lambda v: max(0, min(31, int(round(v * 31))))
    return stp | (q(b) << 10) | (q(g) << 5) | q(r)


def repaint_indices(ramps) -> tuple:
    return tuple(i for ramp in ramps for i in ramp)


def recolour(stock: Iterable[int], preset: str, ramps) -> tuple:
    """One 16-entry CLUT -> recoloured. X5's transform - each entry keeps its
    brightness and takes the preset's hue and a saturation scaled by its own -
    except that each entry KEEPS ITS OWN STP BIT (X5 forced it on; the 27
    stage copies here have it off, and changing it changes how the colour
    blends)."""
    hue, sat, vscale = PRESETS[preset]
    out = list(stock)
    for i in repaint_indices(ramps):
        r, g, b = _to_rgb(out[i])
        _, orig_s, v = colorsys.rgb_to_hsv(r, g, b)
        s = min(1.0, sat * (0.35 + 0.65 * orig_s))
        nr, ng, nb = colorsys.hsv_to_rgb(hue, s, min(1.0, v * vscale))
        out[i] = _to_bgr555(nr, ng, nb, out[i] & 0x8000)
    return tuple(out)


def overrides(value) -> bool:
    """Does this host.yaml value beat the colour baked into the seed? Only a
    real colour (or "random") - never `vanilla`, because Archipelago writes
    every setting's default into host.yaml, and honouring that would silently
    undo every player's YAML choice (X5's reasoning, verbatim in its world)."""
    value = (value or UNSET).strip().lower()
    return value == RANDOM or value in PRESETS


def choose(seed_choice: dict, host_values: dict) -> dict:
    out = {}
    for target in TARGETS:
        local = host_values.get(target)
        out[target] = local if overrides(local) else seed_choice.get(target, VANILLA)
    return out


def resolve(choice: str, rng) -> str:
    """A settings value -> a preset name, or VANILLA for "leave it"."""
    choice = (choice or VANILLA).strip().lower()
    if choice in (VANILLA, UNSET, "", "none", "off"):
        return VANILLA
    if choice == RANDOM:
        return rng.choice(sorted(PRESETS))
    if choice in PRESETS:
        return choice
    logger.warning("Mega Man 8: unknown palette %r, leaving it vanilla. Valid: %s",
                   choice, ", ".join(CHOICES))
    return VANILLA


def palette_edits(choices: dict[str, str], rng) -> list[tuple[bytes, bytes, int, str]]:
    """-> [(stock 32 bytes, replacement 32 bytes, copies expected, label)]."""
    edits = []
    for target, records in TARGETS.items():
        preset = resolve(choices.get(target, VANILLA), rng)
        if preset == VANILLA:
            continue
        for stock, ramps, copies in records:
            new = recolour(stock, preset, ramps)
            if new != stock:
                edits.append((struct.pack("<16H", *stock), struct.pack("<16H", *new),
                              copies, f"{target}={preset}"))
    return edits


def apply(image: bytearray, choices: dict[str, str], rng, expect_counts: bool = True) -> set[int]:
    """Recolour in place, finding every record by CONTENT. Returns the sectors
    touched, for EDC/ECC. A copy count other than expected means this is not
    the disc we think it is - it is logged, as X5 does."""
    from . import disc

    touched: set[int] = set()
    for stock, new, expected, label in palette_edits(choices, rng):
        found, start = 0, 0
        while True:
            at = image.find(stock, start)
            if at == -1:
                break
            image[at:at + 32] = new
            touched.add(at // disc.SECTOR_RAW)
            touched.add((at + 31) // disc.SECTOR_RAW)
            found += 1
            start = at + 2
        if expect_counts and found != expected:
            logger.warning("Mega Man 8 palette %s: patched %d copies, expected %d", label, found, expected)
        else:
            logger.info("Mega Man 8 palette %s: %d copies", label, found)
    return touched
