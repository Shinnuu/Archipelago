"""Player-palette recolouring for Mega Man X6.

Cosmetic only: rewrites the 16-colour CLUTs the player sprites are drawn from.
Nothing here touches logic, items or locations, and the colours are read from
the player's LOCAL settings at patch time - not from the seed - so changing
them is a re-patch, never a re-generation. Same design as worlds/mmx5.

HOW THE RECORDS WERE FOUND
--------------------------
0x800CCF2E (armour in use) is applied at STAGE START, so poking it mid-stage
does nothing. Hold it every frame through boot with 0x800CCF2F forced open,
let the stage load, read the CLUT the game streamed into VRAM, match those 32
bytes on disc. Then - and this is the part that makes the mapping trustworthy -
one disc was built painting each candidate a DIFFERENT marker colour and every
form booted: X came out green, Falcon magenta, Shadow cyan, Blade yellow,
Ultimate white. A single-colour test cannot catch a swapped label; this does.

Full account in MMX6/Reference/mmx6-ram-notes.md, "Player palettes / CLUTs".

Zero could NOT be reached that way: `0x800CCF2E = 05` does not select him -
written and booted, the game came up as ordinary blue X, byte-identical to
form 0. His record came from a hand-played save instead, and is byte-for-byte
X5's Zero.

NOT COVERED
-----------
Black Zero. Same problem as Zero had; it needs a save that has him.

Do not reuse X5's offsets: X6 stores its palettes elsewhere, with far fewer
copies (1-6, not 45), and `ROCK_X6.DAT`'s 92 copies of X5's X CLUT are a
different asset entirely - patched and booted, X stayed blue.

WHICH ENTRIES GET REPAINTED
---------------------------
X6 lays each form out differently, so the ramps are per form rather than one
shared range:

    X         1-4 face/skin, 5-6 cyan highlight, 8-10 trim, 12-15 blue body
    Zero      1-3 crystal, 4-7 red armour, 8-11 trim, 12-15 blond hair
    Shadow    1-6 face and accents, 8-15 the dark body ramp
    Blade     1-5 face/skin, 6-9 white trim, 11-12 green, 13-15 blue body
    Ultimate  1-3 and 5-9 greys, 4 red jewel, 11 cyan, 12-15 dark body

Falcon has no line here because he has no record: he draws from X's.

Every repainted entry keeps its ORIGINAL brightness and takes only the preset's
hue and saturation, so the light-to-dark shading inside each ramp survives.
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

# Shared with worlds/mmx5 by value, not by import - the two worlds live on
# separate branches and must not depend on each other.
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

# target -> (stock 16-entry CLUT, ramps to repaint, expected copies on disc)
TARGETS: dict[str, tuple[tuple[int, ...], tuple[range, ...], int]] = {
    "x": ((0x0000, 0x94DD, 0x8CAC, 0xADFA, 0xCEFD, 0xEFE9, 0xC283, 0xAD03,
           0xFB9B, 0xE2D5, 0xB969, 0x9483, 0xF669, 0xEDE7, 0xD924, 0xC4A3),
          (range(8, 11), range(12, 16)), 4),
    # Zero. Byte-for-byte the SAME 32 bytes as X5's Zero, and the same ramp
    # layout: 1-3 crystal, 4-7 red armour, 8-11 trim, 12-15 blond hair. Found
    # from Ivor's own hand-played Zero save - 143 copies, resident in the Zero
    # dump and absent from the Falcon one.
    "zero": ((0x0000, 0xBB08, 0x95E3, 0xFE00, 0xB5BD, 0x805E, 0x8012, 0x800C,
              0xFBDE, 0xE6D5, 0xC1AC, 0xA4A4, 0xCB1E, 0xB219, 0xA173, 0x9F3D),
             (range(4, 8), range(8, 12)), 143),
    # FALCON IS NOT COVERED - his record is still unidentified.
    #
    # Four attempts, all wrong, and each looked convincing:
    #   1. 0x1DB8D0A8 - "unique to the Falcon frame". It was the large enemy
    #      standing beside him.
    #   2. 0x1E06E3A8 - right table, X's skin ramp, gold-on-white. Absent from
    #      a settled Falcon dump entirely.
    #   3. "he draws from X's CLUT" - 516 of his sprite pixels matched X's
    #      record. Disproved by booting a disc with X recoloured emerald:
    #      Falcon came out unchanged. The pixels matched because his palette
    #      SHARES values with X's (skin, trim), not because he uses it.
    # Colour overlap defeats every match-by-colour method here. Only a
    # patch-and-boot that shows Falcon himself changing counts.
    "shadow": ((0x0000, 0x94DD, 0x8CAC, 0x9174, 0x8380, 0xB39E, 0x921C, 0xBD46,
                0xFB9B, 0xEEF2, 0xE2D4, 0xCA0E, 0xB98A, 0xAD27, 0x9CC5, 0x8C63),
               (range(8, 16),), 6),
    "blade": ((0x0000, 0xCBBF, 0xA23D, 0xA195, 0x94DD, 0x8CAC, 0xFF9B, 0xDEB4,
               0xD22F, 0xB969, 0x9063, 0x83E0, 0x8269, 0xEDE7, 0xE124, 0xC4A3),
              (range(6, 10), range(13, 16)), 1),
    "ultimate": ((0x0000, 0xF39D, 0xCE75, 0xAD6E, 0x889E, 0x98C9, 0xE6F7, 0xC1CE,
                  0xA4E7, 0x9CA5, 0x8C21, 0xEBC8, 0xA8E7, 0xA0A5, 0x9884, 0x9042),
                 (range(1, 4), range(5, 10), range(12, 16)), 5),
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
    logger.warning("MMX6: unknown palette %r, leaving it vanilla. Valid: %s",
                   choice, ", ".join(CHOICES))
    return VANILLA


def palette_edits(choices: dict[str, str], rng) -> list[tuple[bytes, bytes, str]]:
    """-> [(stock 32 bytes, replacement 32 bytes, label)] for real changes."""
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

    Records are found by CONTENT, not by hard-coded offsets. The palettes live
    in ROCK_X6.DAT, far from the code the basepatch edits, so the stock bytes
    are always intact when this runs.
    """
    from . import disc

    touched: set[int] = set()
    for stock, new, label in palette_edits(choices, rng):
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
        target = label.split("=")[0]
        expected = TARGETS[target][2]
        if expect_counts and found != expected:
            logger.warning("MMX6 palette %s: patched %d copies, expected %d",
                           label, found, expected)
        else:
            logger.info("MMX6 palette %s: %d copies", label, found)
    return touched
