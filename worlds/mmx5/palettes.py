"""Player-palette recolouring for Mega Man X5.

Cosmetic only: rewrites the 16-colour CLUTs the player sprites are drawn from.
Nothing here touches logic, items or locations, and the colours are read from
the player's LOCAL settings at patch time - not from the seed - so changing
them is a re-patch, never a re-generation.

HOW IT WORKS
------------
PS1 sprites are 4bpp textures indexing a 16-entry CLUT of BGR555
(0BBBBBGGGGGRRRRR, bit 15 = STP).  Each character's CLUT is stored raw on the
disc and duplicated (X's 45 times, once per stage bundle), so a recolour is a
find-and-replace of 32 bytes plus the mandatory per-sector EDC/ECC regen.

The stock records below were captured from a running game: hold 0x800D1C49
(the character/armour selector) through boot - the game equips a form at STAGE
LOAD, so poking it mid-stage does nothing - then read the CLUT it streams into
VRAM.  Zero is picked at the character-select screen instead, so his came from
a hand-played save.  Full account in Reference/mmx5-ram-notes.md.

Fourth Armor deliberately has no entry: its sprite is different artwork drawn
from X's own CLUT, verified live (a gold-X disc renders Fourth Armor gold), so
recolouring "x" covers it.

WHICH ENTRIES GET REPAINTED
---------------------------
Not the same range for everyone - the ramps are laid out differently:

    X / Falcon / Gaea / Ultimate   1-5 face, 6-10 trim, 11 highlight,
                                   12-15 body   -> repaint 6-10, 11, 12-15
    Zero                           1-3 crystal, 4-7 red armour,
                                   8-11 trim, 12-15 hair/skin -> repaint 4-7, 8-11

Repainting 6..15 on Zero would leave his armour red and recolour his hair, so
the ramps are per target.  They are listed as separate ramps rather than one
span because each is its own light-to-dark run: entry 11 is a lone highlight
and 12 starts a new ramp, so brightness does not decrease monotonically across
those boundaries and nothing should assume it does.

Every repainted entry keeps its ORIGINAL brightness and takes only the preset's
hue and saturation, so the light-to-dark shading inside each ramp survives.
Saturation scales with how saturated the original was, which keeps near-white
trim near-white with a tint instead of turning it into a slab of colour.
"""
import colorsys
import logging
import struct
from typing import Iterable

logger = logging.getLogger()

VANILLA = "vanilla"
RANDOM = "random"
# host.yaml only. The colour itself is a YAML option; this is the value that
# means "I have not set an override here". See overrides().
UNSET = "unset"

# name -> (hue 0-1, saturation, value scale).  Fifteen hues plus three
# achromatic schemes; closer hue steps stop reading as different colours once
# they are on a 4bpp sprite at PS1 resolution.
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

# What the YAML Choice option offers. RANDOM is deliberately NOT here:
# Archipelago reserves "random" on every Choice and refuses to let a world
# declare it (Options.py asserts on it), rolling it itself at generation
# instead - which is exactly the behaviour wanted, and for free. It picks
# among these values, so it can legitimately roll vanilla.
#
# CHOICES keeps RANDOM because host.yaml is plain text with no such handling,
# so an override naming "random" is resolved by resolve() here.
OPTION_KEYS: tuple[str, ...] = (VANILLA,) + tuple(sorted(PRESETS))

# Each repainted region is its own light-to-dark ramp.
X_RAMPS = (range(6, 11), range(11, 12), range(12, 16))   # trim, highlight, body
ZERO_RAMPS = (range(4, 8), range(8, 12))                 # red armour, trim

# target -> (stock 16-entry CLUT, ramps to repaint, expected copies on disc)
TARGETS: dict[str, tuple[tuple[int, ...], tuple[range, ...], int]] = {
    "x": ((0x0000, 0xCBBF, 0xA23D, 0xA195, 0x94DD, 0x8CAC, 0xFF9B, 0xDEB4,
           0xD22F, 0xB969, 0x9CC4, 0xEBC8, 0xF669, 0xEDE7, 0xE124, 0xC4A3),
          X_RAMPS, 45),
    "zero": ((0x0000, 0xBB08, 0x95E3, 0xFE00, 0xB5BD, 0x805E, 0x8012, 0x800C,
              0xFBDE, 0xE6D5, 0xC1AC, 0xA4A4, 0xCB1E, 0xB219, 0xA173, 0x9F3D),
             ZERO_RAMPS, 29),
    "falcon": ((0x0000, 0xCBBF, 0x865B, 0xA195, 0x94DD, 0x8CAC, 0xF7BD, 0xE272,
                0xC5CD, 0xAD4A, 0x9484, 0x8360, 0xF669, 0xEDE7, 0xE124, 0xC4A3),
               X_RAMPS, 2),
    "gaea": ((0x0000, 0x83BF, 0x829D, 0xEAD4, 0x94DD, 0x8CAC, 0xF7BD, 0xD230,
              0xC5EE, 0xB16B, 0x9484, 0xFB07, 0xF669, 0xEDE7, 0xE124, 0xC4A3),
             X_RAMPS, 2),
    "ultimate": ((0x0000, 0xCBBF, 0xA23D, 0xA195, 0x94DD, 0x8CAC, 0xFF9B, 0xDEB4,
                  0xD22F, 0xB969, 0x9CC4, 0x83E0, 0xF669, 0xEDE7, 0xE124, 0xC4A3),
                 X_RAMPS, 3),
}


def _to_rgb(colour: int) -> tuple[float, float, float]:
    colour &= 0x7FFF
    return ((colour & 0x1F) / 31.0,
            ((colour >> 5) & 0x1F) / 31.0,
            ((colour >> 10) & 0x1F) / 31.0)


def _to_bgr555(r: float, g: float, b: float) -> int:
    q = lambda v: max(0, min(31, int(round(v * 31))))
    return 0x8000 | (q(b) << 10) | (q(g) << 5) | q(r)


def repaint_indices(ramps) -> tuple:
    """Flatten a target's ramps into the entry indices they cover."""
    return tuple(i for ramp in ramps for i in ramp)


def recolour(stock: Iterable[int], preset: str, ramps) -> tuple:
    """One 16-entry CLUT -> recoloured 16-entry CLUT."""
    hue, sat, vscale = PRESETS[preset]
    out = list(stock)
    for i in repaint_indices(ramps):
        r, g, b = _to_rgb(out[i])
        _, orig_s, v = colorsys.rgb_to_hsv(r, g, b)
        s = min(1.0, sat * (0.35 + 0.65 * orig_s))
        nr, ng, nb = colorsys.hsv_to_rgb(hue, s, min(1.0, v * vscale))
        out[i] = _to_bgr555(nr, ng, nb)
    return tuple(out)


def overrides(value) -> bool:
    """Does this host.yaml value beat the colour baked into the seed?

    ONLY a value naming a real colour does. `vanilla` deliberately does NOT,
    and this is the load-bearing detail of the whole override design:
    Archipelago materialises settings defaults into host.yaml, so every
    install that has ever run this world already carries
    `x_palette: "vanilla"` on disk. Honouring that as "force vanilla" would
    silently revert the YAML choice of every existing player.

    The cost, stated plainly because it is a real one: you cannot use
    host.yaml to force vanilla back over a colour chosen in the YAML. Pick
    vanilla in the YAML for that, or name a different colour here.
    """
    value = (value or UNSET).strip().lower()
    return value == RANDOM or value in PRESETS


def choose(seed_choice: dict, host_values: dict) -> dict:
    """The colour to actually use for each target.

    `seed_choice` is what the player's YAML baked into the patch; it is empty
    for a patch generated before the colours were YAML options. `host_values`
    is what their host.yaml holds. host.yaml wins wherever it names a real
    colour - see overrides() for why `vanilla` there does not count.
    """
    out = {}
    for target in TARGETS:
        local = host_values.get(target)
        out[target] = (local if overrides(local)
                       else seed_choice.get(target, VANILLA))
    return out


def resolve(choice: str, rng) -> str:
    """Settings value -> a concrete preset name, or VANILLA for 'leave it'."""
    choice = (choice or VANILLA).strip().lower()
    if choice in (VANILLA, UNSET, "", "none", "off"):
        return VANILLA
    if choice == RANDOM:
        return rng.choice(sorted(PRESETS))
    if choice in PRESETS:
        return choice
    logger.warning("MMX5: unknown palette %r, leaving it vanilla. Valid: %s",
                   choice, ", ".join(CHOICES))
    return VANILLA


def palette_edits(choices: dict[str, str], rng) -> list[tuple[bytes, bytes, str]]:
    """-> [(stock 32 bytes, replacement 32 bytes, target name)] for real changes."""
    edits = []
    for target, (stock, ramps, _copies) in TARGETS.items():
        preset = resolve(choices.get(target, VANILLA), rng)
        if preset == VANILLA:
            continue
        new = recolour(stock, preset, ramps)
        if new == stock:
            continue
        edits.append((struct.pack("<16H", *stock),
                      struct.pack("<16H", *new),
                      f"{target}={preset}"))
    return edits


def apply(image: bytearray, choices: dict[str, str], rng,
          expect_counts: bool = True) -> set[int]:
    """Recolour in place. Returns the sectors touched, for EDC/ECC regen.

    Records are found by CONTENT, not by hard-coded offsets: the AP basepatch
    only touches sectors 23433-24319 and every palette record lives far below
    that, so the stock bytes are always intact when this runs.

    `expect_counts` checks each target was found the expected number of times -
    a real mismatch means the image is not the disc we think it is. Tests that
    build a synthetic image switch it off.
    """
    from . import disc

    touched: set[int] = set()
    for stock, new, label in palette_edits(choices, rng):
        found = 0
        start = 0
        while True:
            at = image.find(stock, start)
            if at == -1:
                break
            image[at:at + 32] = new
            touched.add(at // disc.SECTOR_RAW)
            touched.add((at + 31) // disc.SECTOR_RAW)
            found += 1
            start = at + 2
        target = label.split("=")[0]
        expected = TARGETS[target][2]
        if expect_counts and found != expected:
            logger.warning("MMX5 palette %s: patched %d copies, expected %d",
                           label, found, expected)
        else:
            logger.info("MMX5 palette %s: %d copies", label, found)
    return touched
