"""String constants for Mega Man X6 items and locations.

Every bit mapping below is quoted from the verified RAM map
(`mmx6-ram-notes.md`), which tags each fact **[L]** live-observed,
**[W]** workbook-sourced, or **[LW]** both. Where a name comes from the
third-party items guide rather than our own bytes it is marked TODO-verify,
exactly as the X5 world did for its weapon list.

The one structural fact that drives this whole file:

    bit index N (0-7) in 0x800CCF30 / 0x800CCF3C / 0x800CCF3D / 0x800CCF3F
      <-> in-stage 0x800CCEDC = N + 1
      <-> Reploid indices N*16 .. N*16+15

Four stages are directly observed on that formula, so one stage ordering
indexes bosses, weapons, hearts, Life Ups, Energy Ups and all 128 Reploids at
once. STAGES order below IS that bit order - never reorder it.
"""

# ---- Stages / bosses ----------------------------------------------------
# Boss names (guide/US) and area names (workbook) are the same eight places
# under two naming schemes, which is why the two sources look like different
# lists. Three pairs are player-confirmed live: Amazon = Yammark (+1),
# Inami Temple = Turtloid (+20), Laser Institute = Sheldon (+40).
YAMMARK = "Commander Yammark"
WOLFANG = "Blizzard Wolfang"
HEATNIX = "Blaze Heatnix"
SHARK = "Metal Shark Player"
SCARAVICH = "Ground Scaravich"
TURTLOID = "Rainy Turtloid"
SHELDON = "Shield Sheldon"
MIJINION = "Infinity Mijinion"

STAGES = [YAMMARK, WOLFANG, HEATNIX, SHARK, SCARAVICH, TURTLOID, SHELDON, MIJINION]

# Area name per stage, for player-facing text (the in-game stage select shows
# these, not the boss names).
STAGE_AREA = {
    YAMMARK:   "Amazon Area",
    WOLFANG:   "Northpole Area",
    HEATNIX:   "Magma Area",
    SHARK:     "Recycle Lab",
    SCARAVICH: "Central Museum",
    TURTLOID:  "Inami Temple",
    SHELDON:   "Laser Institute",
    MIJINION:  "Weapon Center",
}

# Bit value in 0x800CCF30 (beaten stages / weapons available) and, identically,
# in 0x800CCF3C / 3D / 3F. Kept as data rather than computed so the client and
# the patch can both quote it without re-deriving the ordering.
STAGE_BIT = {stage: 1 << i for i, stage in enumerate(STAGES)}

# In-stage value of 0x800CCEDC. Note the workbook also documents a high-byte
# encoding used on some menu screens - ALWAYS read that address, never infer.
STAGE_INDEX = {stage: i + 1 for i, stage in enumerate(STAGES)}

# Reploid index block owned by each stage (16 each, 128 total).
STAGE_REPLOIDS = {stage: range(i * 16, i * 16 + 16) for i, stage in enumerate(STAGES)}

# ---- Weapons ------------------------------------------------------------
# X's weapon names, US localization. TODO-verify each in-game during testing -
# the same status the X5 world shipped its weapon list under. The MAPPING to
# stages is not in doubt (one bit each, in STAGES order); only the strings are.
YAMMAR_OPTION = "Yammar Option"
ICE_BURST = "Ice Burst"
MAGMA_BLADE = "Magma Blade"
METAL_ANCHOR = "Metal Anchor"
GROUND_DASH = "Ground Dash"
METEOR_RAIN = "Meteor Rain"
GUARD_SHELL = "Guard Shell"
RAY_ARROW = "Ray Arrow"

BOSS_WEAPON = {
    YAMMARK:   YAMMAR_OPTION,
    WOLFANG:   ICE_BURST,
    HEATNIX:   MAGMA_BLADE,
    SHARK:     METAL_ANCHOR,
    SCARAVICH: GROUND_DASH,
    TURTLOID:  METEOR_RAIN,
    SHELDON:   GUARD_SHELL,
    MIJINION:  RAY_ARROW,
}
WEAPONS = [BOSS_WEAPON[s] for s in STAGES]

# ---- Armor --------------------------------------------------------------
# 0x800CCF39 armor parts [LW], two live confirmations:
#   Turtloid's capsule wrote 0x00 -> 0x40 (Shadow Body)
#   Wolfang's capsule wrote  0x00 -> 0x80 (Shadow Legs)
BLADE_HELMET = "Blade Armor Helmet"
BLADE_ARMS = "Blade Armor Arms"
BLADE_BODY = "Blade Armor Body"
BLADE_LEGS = "Blade Armor Legs"
SHADOW_HELMET = "Shadow Armor Helmet"
SHADOW_ARMS = "Shadow Armor Arms"
SHADOW_BODY = "Shadow Armor Body"
SHADOW_LEGS = "Shadow Armor Legs"

BLADE_PARTS = [BLADE_HELMET, BLADE_ARMS, BLADE_BODY, BLADE_LEGS]
SHADOW_PARTS = [SHADOW_HELMET, SHADOW_ARMS, SHADOW_BODY, SHADOW_LEGS]
ARMOR_PARTS = BLADE_PARTS + SHADOW_PARTS

# bit value in 0x800CCF39, in ARMOR_PARTS order
ARMOR_PART_BIT = {name: 1 << i for i, name in enumerate(ARMOR_PARTS)}

# Which stage vanilla-holds each part [G] (items guide), one per stage. The
# two marked CONFIRMED were observed live.
STAGE_ARMOR_PART = {
    YAMMARK:   BLADE_LEGS,      # guide calls it "Blade Boots"
    SCARAVICH: BLADE_HELMET,
    SHELDON:   BLADE_BODY,      # guide calls it "Blade Armor"
    MIJINION:  BLADE_ARMS,      # guide calls it "Blade X-Buster"
    HEATNIX:   SHADOW_ARMS,     # guide calls it "Shadow X-Buster"
    WOLFANG:   SHADOW_LEGS,     # CONFIRMED live 2026-08-25: 0x800CCF39 |= 0x80
    SHARK:     SHADOW_HELMET,
    TURTLOID:  SHADOW_BODY,     # CONFIRMED live 2026-08-22: 0x800CCF39 |= 0x40
}

# Whole armors, 0x800CCF2F "armors selectable" [LW]:
#   +1 Falcon  +2 Shadow  +4 Blade  +8 Ultimate  +10 Zero  +20 Black Zero
# Falcon is set from the start (live baseline 0x800CCF2F = 01), so it is not
# an item. Shadow and Blade unlock by completing their four parts, which is
# why the four parts are the items and the armor itself is not.
ULTIMATE_ARMOR = "Ultimate Armor"
BLACK_ZERO = "Black Zero"
ZERO = "Zero"

# ---- Tanks --------------------------------------------------------------
# 0x800CCF3B [LW]. This is the ONE item field that is not stage-indexed, so
# its bits cannot be derived from stage order - see ram-notes "Tank bit
# mapping". +10 Yammark is live-observed; the rest are pinned by elimination
# and by W/EX being one-of-a-kind.
SUB_TANK = "Sub Tank"
W_TANK = "W Tank"
EX_TANK = "EX Tank"

STAGE_TANK = {
    YAMMARK: SUB_TANK,   # bit +0x10, observed live
    HEATNIX: SUB_TANK,   # bit +0x20
    SHELDON: W_TANK,     # bit +0x40
    WOLFANG: EX_TANK,    # bit +0x80
}
TANK_BIT = {YAMMARK: 0x10, HEATNIX: 0x20, SHELDON: 0x40, WOLFANG: 0x80}

# ---- Gauges -------------------------------------------------------------
# Life 32 -> 64 in 16 steps of +2: 8 Heart Tanks (0x800CCF3C) + 8 Reploid
# Life Ups (0x800CCF3D). Weapon 48 -> 64 in 8 steps: 8 Reploid Energy Ups
# (0x800CCF3F). Fully reconciled live.
#
# TRAP, precisely characterised: a natural pickup writes BOTH the bit and the
# gauge on the same frame. Writing the bit alone makes the pickup vanish from
# the stage WITHOUT growing the gauge, so an AP grant must write 0x800CCF2B /
# 0x800CCF31 itself. The client owns that; it is recorded here because it is
# the reason Heart Tank and Life Up are separate items rather than one.
HEART_TANK = "Heart Tank"
LIFE_UP = "Life Up"
ENERGY_UP = "Energy Up"

# The eight Energy-Up Reploids are named in the workbook, one per stage in bit
# order, which is a second independent confirmation of the stage ordering.
ENERGY_UP_REPLOIDS = ["Satton", "Ken", "Higurai", "Wright",
                      "Home", "Mao", "Dai", "Grantsu"]

# ---- Filler -------------------------------------------------------------
# Five kinds rather than one. With `reploid_checks` on the seed has 157
# locations against ~69 real items, so most of what a player finds is filler -
# a single repeated item would make four fifths of the game read as empty.
# These are all things X6 already drops in stages, so the client grants them
# with the game's own mechanics.
SMALL_LIFE_ENERGY = "Small Life Energy"
LARGE_LIFE_ENERGY = "Large Life Energy"
SMALL_WEAPON_ENERGY = "Small Weapon Energy"
LARGE_WEAPON_ENERGY = "Large Weapon Energy"
EXTRA_LIFE = "Extra Life"

# (name, weight) - large refills and lives are rarer than small ones, roughly
# matching how often the game hands each out.
FILLER_WEIGHTS = [
    (SMALL_LIFE_ENERGY, 10),
    (LARGE_LIFE_ENERGY, 5),
    (SMALL_WEAPON_ENERGY, 8),
    (LARGE_WEAPON_ENERGY, 4),
    (EXTRA_LIFE, 3),
]
FILLER = [name for name, _weight in FILLER_WEIGHTS]

# ---- Parts --------------------------------------------------------------
# 24 equippable Parts across 0x800CCF40..43 [W]. PART_BIT carries the real
# (save-struct address, mask) pair so nothing downstream has to re-derive it;
# the workbook's map leaves CF40 bits 0 and 1 unused, which is why that byte
# contributes six Parts rather than eight.
SPEEDSTER = "Speedster"
JUMPER = "Jumper"
HYPER_DASH = "Hyper Dash"
ENERGY_SAVER = "Energy Saver"
SUPER_RECOVER = "Super Recover"
BUSTER_PLUS = "Buster Plus"
SPEED_SHOT = "Speed Shot"
SHOCK_BUFFER = "Shock Buffer"
D_BARRIER = "D.Barrier"
D_CONVERTER = "D-Converter"
HYPERDRIVE = "Hyperdrive"
POWERDRIVE = "Powerdrive"
WEAPON_DRIVE = "Weapon Drive"
LIFE_RECOVER = "Life Recover"
W_RECOVER = "W.Recover"
OVERDRIVE = "Overdrive"
RAPID_5 = "Rapid 5"
U_BUSTER = "U.Buster"
QUICK_CHARGE = "Quick Charge"
WEAPON_PLUS = "Weapon Plus"
SABER_PLUS = "Saber Plus"
SABER_EXTEND = "Saber Extend"
SHOT_ERASER = "Shot Eraser"
MASTER_SABER = "Master Saber"

# name -> (save-struct address, bit mask)
PART_BIT = {
    SPEEDSTER:     (0x800CCF40, 0x04),
    JUMPER:        (0x800CCF40, 0x08),
    HYPER_DASH:    (0x800CCF40, 0x10),
    ENERGY_SAVER:  (0x800CCF40, 0x20),
    SUPER_RECOVER: (0x800CCF40, 0x40),
    BUSTER_PLUS:   (0x800CCF40, 0x80),
    SPEED_SHOT:    (0x800CCF41, 0x01),
    SHOCK_BUFFER:  (0x800CCF41, 0x02),
    D_BARRIER:     (0x800CCF41, 0x04),
    D_CONVERTER:   (0x800CCF41, 0x08),
    HYPERDRIVE:    (0x800CCF41, 0x10),
    POWERDRIVE:    (0x800CCF41, 0x20),
    WEAPON_DRIVE:  (0x800CCF41, 0x40),
    LIFE_RECOVER:  (0x800CCF41, 0x80),
    W_RECOVER:     (0x800CCF42, 0x01),
    OVERDRIVE:     (0x800CCF42, 0x02),
    RAPID_5:       (0x800CCF42, 0x04),
    U_BUSTER:      (0x800CCF42, 0x08),
    QUICK_CHARGE:  (0x800CCF42, 0x10),
    WEAPON_PLUS:   (0x800CCF42, 0x20),
    SABER_PLUS:    (0x800CCF42, 0x40),
    SABER_EXTEND:  (0x800CCF42, 0x80),
    SHOT_ERASER:   (0x800CCF43, 0x01),
    MASTER_SABER:  (0x800CCF43, 0x02),
}
PARTS = list(PART_BIT)

# Parts that only do anything for one character. Never progression: a run
# played entirely as the other character must not be stranded behind one.
# Same rule the X5 world applies to its six character-locked DNA Parts.
ZERO_ONLY_PARTS = {SABER_PLUS, SABER_EXTEND, MASTER_SABER}
X_ONLY_PARTS = {U_BUSTER, BUSTER_PLUS, SPEED_SHOT, SHOT_ERASER}

# ---- Location names -----------------------------------------------------
INTRO_CLEAR = "Intro Stage - Clear"
VICTORY = "Sigma Defeated"


def boss_location(stage: str) -> str:
    return f"{stage} - Boss Defeated"


def heart_location(stage: str) -> str:
    return f"{stage} - Heart Tank"


def capsule_location(stage: str) -> str:
    return f"{stage} - Armor Capsule"


def tank_location(stage: str) -> str:
    return f"{stage} - {STAGE_TANK[stage]}"


def reploid_location(stage: str, n: int) -> str:
    """`n` is 1-16 within the stage; the global index is STAGE_REPLOIDS[stage][n-1]."""
    return f"{stage} - Reploid {n}"
