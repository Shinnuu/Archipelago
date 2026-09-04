"""AP patch container for Mega Man X5 (PS1, NTSC-U SLUS-01334).

Follows the MMX4 apworld's shape (APProcedurePatch producing a .bin + .cue)
with one deliberate improvement: no external xdelta executable and no
separate basepatch file. The edit list is tiny and lives in disc.py, so
apply_basepatch() patches the vanilla image in pure Python - including the
MANDATORY per-sector EDC/ECC regeneration (emulator disc layers error-correct
un-reparitied edits back to vanilla).

Per-seed data rides inside the .apmmx5 as a JSON file ("seed_edits.json")
rather than APTokenMixin tokens: raw token pokes would bypass parity
regeneration, so every write must funnel through disc.apply_basepatch().
"""
import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING

import settings
import Utils
from worlds.Files import APPatchExtension, APProcedurePatch

from . import disc, palettes

if TYPE_CHECKING:
    from . import MMX5World

logger = logging.getLogger()

# Accepted MD5s for the raw 2352-byte NTSC-U image (SLUS-01334).
#
# REDUMP is the canonical dump and the one players will have. The development
# image differs from it by EXACTLY ONE trailing all-zero 2352-byte sector
# (582,957,312 vs 582,954,960 bytes) - verified 2026-08-02 by trimming that
# sector and reproducing Redump's MD5 byte for byte.
#
# Crucially the padding is at the END, not a leading pregap: 'CD001' sits at
# sector 16 in both, so sector numbering is IDENTICAL and every patch offset
# in disc.py is valid against either image unchanged. Nothing needed rebasing;
# the Redump hash simply has to be accepted. All edits land in sectors
# 23433-24319, nowhere near the tail.
HASH_US_REDUMP = "98c0d278dc4a795a0a7562d950d37cc9"   # Redump, canonical
HASH_US_PADDED = "09e670f6e666211b7fcdbb7d48b716e1"   # dev image, +1 zero sector
ACCEPTED_HASHES = {HASH_US_REDUMP, HASH_US_PADDED}
HASH_US = HASH_US_REDUMP   # kept for callers importing the old name


class MMX5PatchExtension(APPatchExtension):
    game = "Mega Man X5"

    @staticmethod
    def apply_basepatch(caller: APProcedurePatch, rom: bytes) -> bytes:
        extra = []
        try:
            seed_edits = json.loads(caller.get_file("seed_edits.json").decode("utf-8"))
            for entry in seed_edits:
                extra.append((entry["addr"], bytes.fromhex(entry["hex"]), entry["region"]))
        except KeyError:
            pass  # no per-seed edits in this patch
        return disc.apply_basepatch(rom, extra)

    @staticmethod
    def apply_palettes(caller: APProcedurePatch, rom: bytes) -> bytes:
        """Cosmetic recolour: the seed's own choice, or a host.yaml override.

        The colour normally comes from the player's YAML and rides inside the
        patch, so it shows on the website generator, is validated at
        generation rather than failing quietly here, and lands in the spoiler.
        host.yaml remains as an override, which is what still allows a colour
        to be changed without a new seed.

        Runs after apply_basepatch; the two never touch the same sectors
        (palettes sit far below 23433).
        """
        import random

        # The seed's own choice. GUARDED rather than required: a patch built
        # before these were YAML options carries no such file, and must still
        # open - for those, host.yaml is the only source, exactly as before.
        seed_choice: dict = {}
        try:
            seed_choice = json.loads(
                caller.get_file("palettes.json").decode("utf-8"))
        except Exception:
            pass

        # settings.get_settings() memoises on the function object, so a player
        # who patches, edits host.yaml and patches again WITHOUT restarting the
        # Launcher would silently get their previous colours. Re-read from disk
        # for this lookup, then hand the old cache back so nothing else in the
        # process sees a different Settings instance.
        cached = getattr(settings.get_settings, "_cache", None)
        try:
            settings.get_settings._cache = None
            group = settings.get_settings().mmx5_options
        except Exception:
            group = None
        finally:
            settings.get_settings._cache = cached

        host_values = {
            target: (getattr(group, f"{target}_palette", palettes.UNSET)
                     if group is not None else palettes.UNSET)
            for target in palettes.TARGETS
        }
        choices = palettes.choose(seed_choice, host_values)
        for target, value in choices.items():
            if palettes.overrides(host_values.get(target)):
                logger.info("MMX5 palette %s: %s, overridden from host.yaml",
                            target, value)
        if all((c or palettes.VANILLA).strip().lower() == palettes.VANILLA
               for c in choices.values()):
            return rom

        # seeded on the player name so re-patching reproduces the same "random"
        rng = random.Random(getattr(caller, "player_name", "") or None)
        image = bytearray(rom)
        touched = palettes.apply(image, choices, rng)
        for sector in sorted(touched):
            disc.regenerate_sector(image, sector)
        return bytes(image)


class MMX5ProcedurePatch(APProcedurePatch):
    hash = sorted(ACCEPTED_HASHES)
    game = "Mega Man X5"
    patch_file_ending = ".apmmx5"
    result_file_ending = ".cue"
    procedure = [
        ("apply_basepatch", []),
        ("apply_palettes", []),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_bytes()

    def patch(self, target: str) -> None:
        file_name = target[:-4]
        if os.path.exists(file_name + ".bin") and os.path.exists(file_name + ".cue"):
            logger.info("Patched ROM + CUE already exist!")
            return

        super().patch(target)
        os.rename(target, file_name + ".bin")

        rom_name = os.path.basename(file_name)
        cue = (f'FILE "{rom_name}.bin" BINARY\n'
               f'  TRACK 01 MODE2/2352\n'
               f'    INDEX 01 00:00:00\n')
        with open(file_name + ".cue", "w", newline="\n") as f:
            f.write(cue)


# REMOVED 2026-08-04 - do not re-add: the story-chapter shuttle threshold.
#
# 0x800EEFBC held `addiu v0, zero, 6`, the kill count at which the chapter
# ladder advances to the shuttle era, and all_mavericks used to raise it to 8.
# It was disassembled correctly, mapped correctly, and verified live to move
# the chapter transition from 6 kills to 8 - and it still did NOT gate the
# endgame, because the ladder never controlled access in the first place. The
# Enigma/Shuttle menu entries are always present, the shuttle appears once the
# Enigma has been used, and a player at 6 kills reached Zero Space on a disc
# carrying this edit.
#
# All it actually did was delay the story announcement and Dynamo (who is tied
# to chapter 4) by two Mavericks, so it was dropped.
#
# The real gate is ACT 0x800D1C79 >= 5, handled by the client - see
# ENDGAME_ACT in client.py. Full account in mmx5-ram-notes.md.


# Text skip. Both sites are in the message STATE MACHINE in the static EXE -
# NOT the render loop. Four attempts at the render loop failed (one killed the
# advance button, one broke the box display entirely); the working layer is the
# one the game's own Y/advance handling uses. Full account, including the dead
# ends and why each failed, in mmx5-ram-notes.md "Text control".
#
#   0x80023D48  beqz $v1, 0x80023d54   guards `sb $zero, 0xf($s0)` - zeroing
#                                      that flag is exactly what Y does, so
#                                      NOPping the guard completes every box
#   0x80023D84  beqz $v1, 0x80024138   guards the end-of-box "return unless a
#                                      button is down" wait
#
# Both read the pad word 0x800C9320 (bit 0x10 = confirm, live-verified).
# Choice prompts are NOT affected - tested live: Alia's DNA reward prompt
# pauses and waits, and the Enigma/Shuttle launch is a stage-select menu that
# never routes through here.
TEXT_INSTANT_ADDR = 0x80023D48
TEXT_INSTANT_VANILLA = bytes.fromhex("02006010")   # beqz $v1, +2
TEXT_ADVANCE_ADDR = 0x80023D84
TEXT_ADVANCE_VANILLA = bytes.fromhex("ec006010")   # beqz $v1, +0xEC
TEXT_NOP = bytes(4)
TEXT_REGION = "SLUS exe"


# Launch resolution roll (launch overlay, disassembled from the disc):
#   0x800FA0C8  jal  0x8002df78     RNG
#   0x800FA0D0  sra  $v0, $v0, 2
#   0x800FA0D4  andi $v1, $v0, 0xf  roll = (rand>>2) & 0xF -> 0..15
#   0x800FA0D8  slti $v0, $s0, 0x51 s0 = score, then a band ladder:
#     <=0 never | 0x01-0x14 roll==0 6.25% | 0x15-0x28 roll<2 12.5%
#     | 0x29-0x3C roll<6 37.5% | 0x3D-0x50 roll<12 75% | >=0x51 roll<15 93.75%
#
# BASE_EDITS replaces the andi with `li $v1,0` so the roll is always 0 and
# success reduces to score > 0. Under `vanilla` launch odds we put the andi
# BACK - seed edits are applied after BASE_EDITS into the same image, so this
# restore wins - and the client then writes a score that lands in the band
# matching the player's part count instead of a flat 0/1.
LAUNCH_ROLL_ADDR = 0x800FA0D4
LAUNCH_ROLL_VANILLA = bytes.fromhex("0f004330")   # andi $v1, $v0, 0xf
LAUNCH_ROLL_REGION = "launch overlay"

# ---- Exit Stage button ------------------------------------------------------
# Vanilla decides availability in the pause handler at 0x8003322C:
#
#   80033454  lbu   $a0, 0xc($v1)      ; $v1 = 0x800D1C00 -> 0x1C0C stage id
#   8003345C  addiu $v0, $a0, -1
#   80033460  sltiu $v0, $v0, 8        ; (stage-1) < 8  -> a Maverick stage
#   80033464  beqz  $v0, 0x80033494    ; ...otherwise: unavailable
#   8003346C  lbu   $v1, 0x4c($v1)     ; 0x1C4C boss-kill record
#   80033478  srav  $v1, $v1, $v0      ; >> (stage-1)
#   8003347C  andi  $v1, $v1, 1        ; THIS stage's boss beaten?
#   80033480  beqz  $v1, 0x80033490    ; ...otherwise: unavailable
#   80033484  addiu $v0, $zero, 1
#   8003348C  sb    $v0, 0x23($s0)     ; available
#
# So vanilla only lets you leave a Maverick stage you have ALREADY cleared,
# which is exactly backwards for a randomizer: the run is full of revisits for
# a check you can now reach, and of entries into a stage you cannot yet finish.
#
# NOPping the SECOND branch drops the "already beaten it" requirement. Until
# 0.6.2 that was the whole edit, which left the FIRST branch deciding scope -
# and `(stage-1) < 8` is a Maverick-stages-only test, so Exit Stage stayed
# absent from the intro, the Enigma/Shuttle sorties, Sigma's stage and all of
# Zero Space. A playtester hit that in Zero Space 2 and asked for it
# everywhere.
#
# Widening it is one immediate rather than a second NOP, and the choice of
# immediate is the safety argument. `$v0` here is `(stage - 1)` computed on a
# ZERO-EXTENDED byte, so the intro (stage 0) underflows to 0xFFFFFFFF and
# fails ANY unsigned compare. Raising the bound to 0x100 therefore admits
# every real stage id (1..0x12) and keeps the intro out for free - no extra
# test, no extra word. The intro has to stay out: leaving it early strands ACT
# progression, and there is no stage select to come back to yet.
#
# ⚠️ KNOWN, ACCEPTED RISK IN ZERO SPACE - live-check before trusting a seed.
# The EXE's stage-transition function `0x800205AC` carries an ACT ladder keyed
# purely on the stage id you are LEAVING:
#
#   80020690  bne  $v1, 16, +2     ; leaving 0x10 (Zero Space 1)
#   80020698  sb   $v0, 0x79($a2)  ;   -> ACT = 6
#   800206A4  bne  $v0, 17, +4     ; leaving 0x11 (Zero Space 2)
#   800206B0  sb   $v0, 0x79($a2)  ;   -> ACT = 7
#   800206BC  bne  $v0, $a3, +2    ; leaving 0x12 (X vs Zero)
#   800206C4  sb   $v0, 0x79($a2)  ;   -> ACT = 8
#
# and the hub picks the endgame destination from ACT (5 -> 0x10, 6 -> 0x11,
# 7 -> 0x12, else 0x0C). The ladder is reached only when the stage-result byte
# `0x800D1C0F` is positive (`0x800205D4`), and the pause handler never writes
# that byte itself - so whether an ESCAPE reaches the ladder depends on which
# result the escape path stores, which the vanilla game never exercises here
# because vanilla cannot escape Zero Space at all. If it does reach it,
# escaping a Zero Space stage advances past it and its endgame_checks location
# becomes unreachable. Confirm live before this is trusted in a race seed; the
# fix, if needed, is a second edit that suppresses the ladder on an escape.
#
# Derived from our own disassembly of the vanilla EXE. The MMX5 Improvement
# Project Addendum documents a 12-word rewrite of the same routine; we take
# the location, not their code (Reference/mmx5-external-findings.md).
EXIT_STAGE_ADDR = 0x80033480
EXIT_STAGE_VANILLA = bytes.fromhex("03006010")    # beqz $v1, +3
EXIT_STAGE_ALWAYS = bytes(4)                      # nop -> always available
EXIT_STAGE_REGION = "SLUS exe"
# The scope test above it. 8 -> 0x100: every stage id, intro still excluded by
# the 0xFFFFFFFF underflow.
EXIT_STAGE_RANGE_ADDR = 0x80033460
EXIT_STAGE_RANGE_VANILLA = bytes.fromhex("0800422c")   # sltiu $v0, $v0, 8
EXIT_STAGE_RANGE_ALL = bytes.fromhex("0001422c")       # sltiu $v0, $v0, 0x100

# ---- Tidal Whale (Duff McWhalen) autoscroll ---------------------------------
# The horizontal scroll speed of the water chase is a single 16-bit immediate:
#
#   800EEE44  ori $v1, $zero, 0x8000    ; horizontal speed, segment 1
#
# ⚠️ This lives in DUFF McWHALEN'S STAGE OVERLAY, which loads at 0x800EE970 -
# the SAME RAM base as the results and hub overlays we already patch. A RAM
# address alone does not identify it; the edit MUST name its own region (see
# disc.REGIONS). Getting that wrong would rewrite the results screen.
WHALE_SCROLL_ADDR = 0x800EEE44
WHALE_SCROLL_VANILLA = bytes.fromhex("00800334")  # ori $v1, $zero, 0x8000
WHALE_SCROLL_REGION = "whale stage overlay"
# option value -> the immediate. Vanilla 0x8000 is 1.0x.
WHALE_SCROLL_SPEEDS = {
    1: 0xA000,   # 1.25x
    2: 0xC000,   # 1.5x
    3: 0xF000,   # ~1.9x
}


def whale_scroll_word(speed: int) -> bytes:
    """`ori $v1, $zero, imm` with the immediate swapped."""
    imm = WHALE_SCROLL_SPEEDS[speed]
    return (0x34030000 | imm).to_bytes(4, "little")


# ---- Player attack damage table --------------------------------------------
# 80 entries of (STA, DMG) at 0x80074DA0, indexed by attack id * 2. The game
# reaches it as `[entity+0x58] + id*2` (0x80031FA4) - the pointer is per
# ENTITY and this is the player's, installed at init exactly the way each boss
# installs its own. Nothing in RAM references 0x80074DA0 directly.
#
# The table ENDS at 0x80074E40, where a separate all-(00,7F) block begins.
# Writing past that boundary would rewrite a different table, so the length is
# fixed here and asserted in test_disc.py against the real disc.
#
# Verified byte-exact against ramdump_stage_f284694.bin; re-derived from the
# disc by test_disc.py when MMX5_DISC is set. Research: ghidra-findings §9.18,
# external-findings §1.1.
WEAPON_DAMAGE_ADDR = 0x80074DA0
WEAPON_DAMAGE_REGION = "SLUS exe"
WEAPON_DAMAGE_VANILLA = bytes.fromhex(
    "0003000400000004000400040004000400040005000400000007000700070007"
    "00070007000f0004001000020020000400040006000400040004ff0000040004"
    "0003000000060008000800040004000400040004000400040004000400040004"
    "00040004000400040004000400040200000100010004007f007f007f007f0003"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00")
# The block immediately after the table. Never written - only used to prove
# the table length is right (a scaler that ran long would corrupt this).
WEAPON_DAMAGE_NEXT_ADDR = WEAPON_DAMAGE_ADDR + len(WEAPON_DAMAGE_VANILLA)
WEAPON_DAMAGE_NEXT_VANILLA = bytes.fromhex("007f007f0000007f")

# Attack ids that are the SAME weapon at different charge levels, and so must
# share one multiplier. Rolling them separately let a charged shot come out
# weaker than its own uncharged shot.
#
# The table is two parallel 9-entry blocks: entries 0-8 are the uncharged
# forms and 9-17 the charged ones, in the same order. Evidence - X Buster is
# entry 0 uncharged (3) and entry 9 mid-charge (5); the eight special weapons
# are entries 1-8 uncharged (4) and 10-17 charged (7). Labels verified in
# external-findings §1, values re-read from our own dump.
#
# Entries 18-20 are X's FULL-charge buster, one per armor (unarmored 0x0F,
# Falcon 4, Fourth 0x10), so they belong to the buster family too.
#
# Sharing the multiplier preserves vanilla's ordering exactly rather than
# re-rolling it - including vanilla's own oddity that Falcon's charged buster
# (4) is weaker than X's mid-charge (5). We are not in the business of
# "fixing" that; we just never make it worse.
WEAPON_DAMAGE_FAMILIES = (
    (0, 9, 18, 19, 20),                          # X Buster, all charge levels
) + tuple((j, j + 9) for j in range(1, 9))       # each special: uncharged, charged

# Multiplier range per option value. One roll per family, one per loose entry.
WEAPON_DAMAGE_RANGES = {
    1: (0.50, 0.90),    # weak
    2: (0.80, 1.30),    # regular
    3: (1.20, 2.00),    # strong
    4: (0.25, 2.50),    # chaotic
}
# Floor 1: the engine already refuses to deal less (FUN_80031670 returns 1
# rather than 0), so rolling to 0 would silently become 1 anyway.
# Ceiling 0x7E: **0x7F is the instakill sentinel** - the resolver passes it
# through untouched, so a weapon that rolled to 0x7F would one-shot every
# boss in the game. Never emit it, and never scale an entry that already is
# one.
WEAPON_DAMAGE_MIN = 1
WEAPON_DAMAGE_MAX = 0x7E

# Boss attack scaling. Same shape as the weapon ranges but a separate knob:
# these read from the BOSS's side, so "strong" here means the boss hits harder.
BOSS_DAMAGE_RANGES = {
    1: (0.50, 0.90),    # weak
    2: (0.80, 1.30),    # regular
    3: (1.20, 2.00),    # strong
    4: (0.25, 2.50),    # chaotic
}


# ---- Boss attack damage tables ---------------------------------------------
# Each boss's init installs its OWN attack table into `obj+0x58` (the same
# per-entity mechanism the player's 0x80074DA0 table uses). Those eight tables
# turn out to be contiguous and identically sized - 160 bytes each, 0xA0
# stride, 0x80075C00..0x80076100 - so the whole set is one EXE write and needs
# no per-boss disc region.
#
# Installed by (module init site -> table):
#   Grizzly Slash   0x800FA508 -> 0x80075C00     Duff McWhalen 0x800FA118 -> 0x80075CA0
#   Squid Adler     0x800FA064 -> 0x80075D40     Shining Firefly 0x800FABB8 -> 0x80075DE0
#   Dark Necrobat   0x800FA330 -> 0x80075E80     Spiral Pegasus 0x800FA1C0 -> 0x80075F20
#   Burn Dinorex    0x800FA058 -> 0x80075FC0     Spike Rosered  0x800FA5C4 -> 0x80076060
#
# NOT included, deliberately: the tables bosses SHARE with other things -
# 0x80074EE0, 0x800750C0, 0x800767E0, the all-instakill block 0x80074E40, and
# 0x80074DA0 which is the PLAYER's. Scaling any of those would reach past the
# bosses; several boss sub-objects reference the player table directly.
BOSS_DAMAGE_ADDR = 0x80075C00
BOSS_DAMAGE_REGION = "SLUS exe"
BOSS_DAMAGE_STRIDE = 0xA0          # one table per boss, same size as the player's
BOSS_DAMAGE_VANILLA = bytes.fromhex(
    "0001ff0000000002000200020002000500020001ff0000000003000300030003"
    "00080003000300030003ff000008ff0000020002000500040004080000010004"
    "ff00000000030005000500050001000100010001000800080005000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff000001"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"
    "000100050000ff0000020002000200020002000100080000ff03000300030003"
    "00030003000300030003ff000008ff0000020002000500040004080000010004"
    "00080000ff000005000500050001000100010001000800040005000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff000001"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"
    "00010002000000050002ff0000020002000200010003000000080003ff000003"
    "00030003000300030003ff000008ff0000020002000500040004080000010004"
    "0005000000080005ff0000050001000100010001000800040005000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff00ff00"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"
    "000100020000000200020005ff0200020002000100030000000300030008ff00"
    "00030003000300030003ff000008ff0000020002000500040004080000010004"
    "0005000000030005000800050001000100010001ff0000040005000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff000005"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"
    "0001000200000002000200020005000200020001000300000003000300030008"
    "00030003000300030003ff000008ff0000020002000500040004080000010004"
    "0005000000030005000500050001000100010001000a00040005000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff000001"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"
    "00010002000000020002000200020002ff000001000300000003000300030003"
    "0003ff00000300030003ff000008ff0000020002000500040004080000010004"
    "000500000003000500050005000100010001000100080004ff00000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff000001"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"
    "0001000200000002ff0000020002000200050001000300000003ff0000030003"
    "00030008000300030003ff000008ff0000020002000500040004080000010004"
    "000500000003ff00000500050001000100010001000800040008000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff000001"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"
    "0001000200000002000500020002ff0000050001000300000003000800030003"
    "ff030008000300030003ff000008ff0000020002000500040004080000010004"
    "00050000000300080005000500010001000100010008ff000005000200040002"
    "00010004000000000000000000000200ff00ff000002ff00ff00ff00ff000001"
    "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00")
BOSS_DAMAGE_NEXT_ADDR = BOSS_DAMAGE_ADDR + len(BOSS_DAMAGE_VANILLA)
# The ninth table, which begins immediately after ours. Never written - it
# only proves the region length is right. (Read off the disc, not guessed: the
# first version of this constant was a guess and the disc-gated test caught it.)
BOSS_DAMAGE_NEXT_VANILLA = bytes.fromhex("000100020000ff00")


def boss_damage_tables(mode: int, random, vanilla: bytes = b"") -> bytes:
    """A scaled copy of all eight boss attack tables.

    ONE multiplier per boss, so a boss keeps the shape of its own move set -
    the weak pokes stay weak relative to the big attack. Guards are identical
    to the player table: `STA != 0` and `DMG == 0` are not damage, `0x7F` is
    the instakill sentinel and is never scaled or produced, floor of 1.
    """
    out = bytearray(vanilla or BOSS_DAMAGE_VANILLA)
    low, high = BOSS_DAMAGE_RANGES[mode]
    for table in range(len(out) // BOSS_DAMAGE_STRIDE):
        factor = random.uniform(low, high)
        base = table * BOSS_DAMAGE_STRIDE
        for i in range(0, BOSS_DAMAGE_STRIDE, 2):
            sta, dmg = out[base + i], out[base + i + 1]
            if sta != 0 or not (WEAPON_DAMAGE_MIN <= dmg <= WEAPON_DAMAGE_MAX):
                continue
            out[base + i + 1] = max(WEAPON_DAMAGE_MIN,
                                    min(WEAPON_DAMAGE_MAX, round(dmg * factor)))
    return bytes(out)


def weapon_damage_table(mode: int, random, vanilla: bytes = b"") -> bytes:
    """A scaled copy of the player attack table.

    `vanilla` defaults to the real table; it is a parameter so the guards
    below can be tested against entry shapes the shipped table happens not to
    contain (it has no `STA != 0` entry that also carries damage, so that
    guard is unreachable with real data and would otherwise go untested).

    Entries are left EXACTLY as vanilla unless they are ordinary damage:

    * `STA != 0` - not a damage entry. `STA == 2` means "this attack deals no
      damage at all" (`0x80031FC4` returns early on it) and `0xFF` marks
      unused slots; scaling either invents behaviour that does not exist.
    * `DMG == 0` - likewise not a damage entry.
    * `DMG == 0x7F` - the instakill sentinel. Left alone in both directions:
      never scaled down (it is not a quantity) and never produced.
    """
    out = bytearray(vanilla or WEAPON_DAMAGE_VANILLA)
    low, high = WEAPON_DAMAGE_RANGES[mode]
    count = len(out) // 2

    # One multiplier per weapon family first, so every charge level of a
    # weapon scales together. Rounding and the clamp are both monotonic, so a
    # shared multiplier is what actually guarantees charged >= uncharged.
    shared: dict[int, float] = {}
    for family in WEAPON_DAMAGE_FAMILIES:
        if not all(entry < count for entry in family):
            continue        # a shorter table (tests) has no such family
        factor = random.uniform(low, high)
        for entry in family:
            shared[entry] = factor

    for entry in range(count):
        sta, dmg = out[entry * 2], out[entry * 2 + 1]
        if sta != 0 or not (WEAPON_DAMAGE_MIN <= dmg <= WEAPON_DAMAGE_MAX):
            continue
        factor = shared.get(entry)
        if factor is None:
            factor = random.uniform(low, high)
        rolled = round(dmg * factor)
        out[entry * 2 + 1] = max(WEAPON_DAMAGE_MIN,
                                 min(WEAPON_DAMAGE_MAX, rolled))
    return bytes(out)


def patch_rom(world: "MMX5World", patch: MMX5ProcedurePatch) -> None:
    """Collect per-seed edits as {addr, hex, region} rows."""
    seed_edits: list = []

    if world.options.launch_odds == "vanilla":
        seed_edits.append({"addr": LAUNCH_ROLL_ADDR,
                           "hex": LAUNCH_ROLL_VANILLA.hex(),
                           "region": LAUNCH_ROLL_REGION})

    if world.options.text_skip:
        # One toggle drives both: anyone who wants instant text wants it to
        # advance too, and instant-without-advance just moves the waiting.
        for addr in (TEXT_INSTANT_ADDR, TEXT_ADVANCE_ADDR):
            seed_edits.append({"addr": addr, "hex": TEXT_NOP.hex(),
                               "region": TEXT_REGION})

    if world.options.exit_stage_anytime:
        # Two words: a NOP over the "have you already beaten this stage's
        # boss?" branch, and the scope test widened from Maverick-stages-only
        # to every stage but the intro. See the ⚠️ note above the constants
        # for the Zero Space caveat.
        seed_edits.append({"addr": EXIT_STAGE_ADDR,
                           "hex": EXIT_STAGE_ALWAYS.hex(),
                           "region": EXIT_STAGE_REGION})
        seed_edits.append({"addr": EXIT_STAGE_RANGE_ADDR,
                           "hex": EXIT_STAGE_RANGE_ALL.hex(),
                           "region": EXIT_STAGE_REGION})

    if world.options.water_stage_speed:
        # Duff McWhalen's stage overlay - NOT the results/hub overlay that
        # shares its RAM base. The region name is what disambiguates them.
        seed_edits.append({"addr": WHALE_SCROLL_ADDR,
                           "hex": whale_scroll_word(
                               world.options.water_stage_speed.value).hex(),
                           "region": WHALE_SCROLL_REGION})

    if world.options.weapon_damage:
        # One 160-byte write covering the whole player attack table. Rolled
        # from the world's own random so it is fixed for a seed.
        seed_edits.append({
            "addr": WEAPON_DAMAGE_ADDR,
            "hex": weapon_damage_table(world.options.weapon_damage.value,
                                       world.random).hex(),
            "region": WEAPON_DAMAGE_REGION})

    if world.options.boss_damage:
        seed_edits.append({
            "addr": BOSS_DAMAGE_ADDR,
            "hex": boss_damage_tables(world.options.boss_damage.value,
                                      world.random).hex(),
            "region": BOSS_DAMAGE_REGION})

    if world.options.pickupsanity:
        # Consumable-pickup stub + jump-table redirects for kinds 0x02-0x08.
        # Per-seed on purpose: without the option the disc stays byte-identical
        # to the validated base, and consumables keep their vanilla effects.
        for addr, payload, region in disc.pickupsanity_edits():
            seed_edits.append({"addr": addr, "hex": payload.hex(),
                               "region": region})

    # NOTE: all_mavericks emits NO disc edit. Its endgame gate is entirely
    # client-side (ACT 0x800D1C79) - see the removal note above.

    patch.write_file("seed_edits.json", json.dumps(seed_edits).encode("utf-8"))

    # Cosmetic colours. Resolved HERE, at generation, so `random` is rolled
    # once and recorded rather than re-rolled from the player's name every
    # time the patch is opened. host.yaml can still override any of these when
    # the patch is opened - see MMX5PatchExtension.apply_palettes.
    patch.write_file("palettes.json", json.dumps({
        target: palettes.resolve(
            getattr(world.options, f"{target}_palette").current_key,
            world.random)
        for target in palettes.TARGETS
    }).encode("utf-8"))


def get_base_rom_bytes(file_name: str = "") -> bytes:
    base_rom_bytes = getattr(get_base_rom_bytes, "base_rom_bytes", None)
    if not base_rom_bytes:
        file_name = get_base_rom_path(file_name)
        with open(file_name, "rb") as infile:
            base_rom_bytes = bytes(infile.read())

        md5 = hashlib.md5()
        md5.update(base_rom_bytes)
        if md5.hexdigest() not in ACCEPTED_HASHES:
            # Say WHY, not just "wrong hash". The overwhelmingly common case
            # (tester report, 2026-08-09) is pointing the base-image setting
            # at an ALREADY-PATCHED disc from an earlier seed - the refusal
            # is correct, but a bare mismatch error sent people off deleting
            # every X5 file they had instead of fixing the setting. The probe
            # is the first capability retarget's offset byte (0x4C vanilla,
            # 0x4D on every AP disc revision) - same site the client probes
            # in RAM (client.PATCH_PROBE_*), needing no vanilla data.
            probe_off = disc.addr_to_disc(0x8003C324, "SLUS exe")
            if len(base_rom_bytes) > probe_off and base_rom_bytes[probe_off] == 0x4D:
                raise Exception(
                    "The supplied base disc image is an ALREADY AP-PATCHED "
                    "Mega Man X5 disc, not the clean dump. Patching always "
                    "starts from the clean US (SLUS-01334) image: point the "
                    "Mega Man X5 rom_file setting (host.yaml / the file "
                    "prompt) at your original dump. If you no longer have "
                    "it, the standalone MMX5-Unpatcher tool on the apworld's "
                    "release page can restore a verified clean copy from "
                    "this file.")
            raise Exception("Supplied base disc image does not match a known "
                            "MD5 for the US (SLUS-01334) release. Expected the "
                            f"Redump dump ({HASH_US_REDUMP}); a variant with one "
                            "extra trailing zero sector is also accepted. Verify "
                            "your dump (raw 2352-byte .bin, single data track).")
        get_base_rom_bytes.base_rom_bytes = base_rom_bytes
    return base_rom_bytes


def get_base_rom_path(file_name: str = "") -> str:
    options: settings.Settings = settings.get_settings()
    if not file_name:
        file_name = options["mmx5_options"]["rom_file"]
    if not os.path.exists(file_name):
        file_name = Utils.user_path(file_name)
    return file_name
