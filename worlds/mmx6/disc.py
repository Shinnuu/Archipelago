"""Disc geometry and the AP base patch for Mega Man X6 (NTSC-U, SLUS-01395).

Mirrors the X5 world's disc.py: the edit list is tiny, so the image is patched
in pure Python with no external xdelta and no separate basepatch file. Every
write funnels through `apply_basepatch`, which regenerates EDC/ECC for each
touched sector - MANDATORY, because emulator disc layers error-correct
un-reparitied edits straight back to vanilla and the patch silently does
nothing.

X6 needs only TWO regions where X5 needed several. Its code overlays are raw
in ROCK_X6.BIN and directly patchable, but each loads to a different RAM
address, so overlay code is addressed by CONTAINER OFFSET, never by RAM.
"""
from typing import Iterable

SECTOR_RAW = 2352
USER_OFF = 24          # Mode2 Form1: 12 sync + 4 header + 8 subheader
USER_LEN = 2048

# From our own ISO parse, which matches the Tweaks workbook's ~LBA-Size table
# on every file.
EXE_LBA, EXE_SIZE = 210930, 522240        # SLUS_013.95
ROCK_LBA, ROCK_SIZE = 211185, 1665024     # ROCK_X6.BIN
EXE_TADDR, EXE_HDR = 0x80010000, 0x800
EXE_TEXT_END = EXE_TADDR + EXE_SIZE - EXE_HDR

REGION_EXE = "exe"
REGION_ROCK = "rock"


def addr_to_disc(where: int, region: str) -> int:
    """(address, region) -> raw .bin byte offset.

    `where` is a RAM address for REGION_EXE and a ROCK_X6.BIN container offset
    for REGION_ROCK.
    """
    if region == REGION_EXE:
        if not EXE_TADDR <= where < EXE_TEXT_END:
            raise ValueError(f"0x{where:08X} is outside the EXE text")
        off = EXE_HDR + where - EXE_TADDR
        sec, within = divmod(off, USER_LEN)
        return (EXE_LBA + sec) * SECTOR_RAW + USER_OFF + within
    if region == REGION_ROCK:
        if not 0 <= where < ROCK_SIZE:
            raise ValueError(f"0x{where:X} is outside ROCK_X6.BIN")
        sec, within = divmod(where, USER_LEN)
        return (ROCK_LBA + sec) * SECTOR_RAW + USER_OFF + within
    raise ValueError(f"unknown region {region!r}")


# ---- the AP-owned save block -------------------------------------------------
# 0x800CCF7B..0x800CCF97 is untouched by ANY of the 1,719 save-struct accesses
# across the EXE and every overlay. It does NOT persist to the memcard - X6
# re-serialises the save field by field - which is fine: the client rewrites it
# every cycle and the game only reads it at stage start.
SAVE_BASE = 0x800CCED0
AP_WEAPONS = 0x800CCF7B
AP_WEAPONS_OFF = AP_WEAPONS - SAVE_BASE          # 0xAB
BEATEN_OFF = 0x800CCF30 - SAVE_BASE              # 0x60

# ---- A1: decouple weapon availability from the kill record -------------------
# 0x800CCF30 is simultaneously "stage beaten" and "weapons available", and is
# never READ as a weapon list anywhere. Three sites copy it into the live
# player object at +0xC9; the weapon checks read that copy. Redirecting those
# three copies leaves the kill record intact, so the souls gate, the Exit Stage
# button and story progression all keep working.
#
# Each edit is one instruction: same opcode, same registers, new immediate.
# Vanilla bytes are declared so a wrong offset or a different dump fails loudly
# instead of corrupting code.
#
# The Shadow Armor rule is deliberately PRESERVED - two of these sites are
# paired with an earlier `sb zero, 0xc9(...)` taken when 0x800CCF2E reads 2,
# which is X6's own "Shadow Armor cannot use special weapons".
A1_EDITS: list[tuple[str, int, str, bytes, bytes]] = [
    ("overlay stage-start copy", 0x0D6A2C, REGION_ROCK,
     bytes.fromhex("60002292"), bytes.fromhex("ab002292")),
    ("EXE copy (armor path)", 0x8003C278, REGION_EXE,
     bytes.fromhex("6000a290"), bytes.fromhex("ab00a290")),
    ("EXE copy (2nd caller)", 0x8003D790, REGION_EXE,
     bytes.fromhex("6000c290"), bytes.fromhex("ab00c290")),
]

BASE_EDITS: list[tuple[int, bytes, str]] = [
    (where, patched, region) for _label, where, region, _van, patched in A1_EDITS
]

# ---- QoL disc edits ----------------------------------------------------------
# Sourced from acediez's "Mega Man X6 Tweaks" patcher v2.6.1, whose data file
# expresses every site as a RAW byte offset into the Redump image. Each one
# below was re-derived into our (region, address) form and then VERIFIED rather
# than trusted: the declared vanilla bytes were read back from BOTH accepted
# images and match byte-for-byte, and no site overlaps A1.
#
# The Tweaks patcher applies an xdelta "base patch" before its own edits. That
# base patch exists to grow the file for the retranslated script and custom
# graphics; NONE of the edits below depend on it. Each either overwrites
# existing instructions in place, or writes into an alignment hole that is
# already zero-filled in the vanilla image. That was measured, not assumed.
#
# Tweaks' own DialogueDisable05 (Investigator descriptions) and 06 (Special
# Weapon descriptions) are absent on purpose: its data file marks both
# "not solved" and ships no offsets for them.
QOL_EDITS: dict[str, list[tuple[str, int, str, bytes, bytes]]] = {
    # Dialogue out of the way. Five separate call sites plus the typing speed.
    "text_skip": [
        ("navigator dialogue and alerts", 0x800530A8, REGION_EXE,
         bytes.fromhex("0200628400000000"), bytes.fromhex("0000023400000000")),
        ("navigator dialogue (overlay)", 0x0009EBF8, REGION_ROCK,
         bytes.fromhex("06004014"), bytes.fromhex("1dc90308")),
        ("other in-stage dialogue", 0x000218C0, REGION_ROCK,
         bytes.fromhex("edce4480"), bytes.fromhex("02000434")),
        ("stage-select briefings", 0x8001E394, REGION_EXE,
         bytes.fromhex("01000224"), bytes.fromhex("02000224")),
        ("stage-select briefings (overlay a)", 0x000C1B14, REGION_ROCK,
         bytes.fromhex("02004014"), bytes.fromhex("d3024014")),
        ("stage-select briefings (overlay b)", 0x000C1AE4, REGION_ROCK,
         bytes.fromhex("010082a0"), bytes.fromhex("7bb50308")),
        ("Nightmare Souls explanation", 0x000D6C10, REGION_ROCK,
         bytes.fromhex("04006010"), bytes.fromhex("21bb0308")),
        ("mute navigator alert", 0x80053164, REGION_EXE,
         bytes.fromhex("125b000c"), bytes.fromhex("00000000")),
        # Cutscene typing speed: addiu v0, zero, 4 -> addiu v0, zero, 2.
        ("cutscene text speed", 0x800226D8, REGION_EXE,
         bytes.fromhex("04000224"), bytes.fromhex("02000224")),
        # ---- instant text and auto-advance, ported from X5 ----------------
        # CONFIRMED LIVE 2026-08-27 on a disc built through apply_basepatch:
        # boxes complete instantly and advance with no input.
        #
        # Everything above REMOVES dialogue. These two make what is left get
        # on with itself, which is what the Tweaks patcher never had: its 144
        # tweaks include DialogueDisable01-07 and nothing that touches typing
        # or advancing. Enumerated, not sampled.
        #
        # Both sites are in the message STATE MACHINE, not the render loop.
        # That distinction is the whole reason this was cheap: X5 burned four
        # attempts on the render loop - one killed the advance button, one
        # broke the box display outright - before finding that the layer the
        # game's own confirm handling uses is the one to cut. We went straight
        # there.
        #
        #   0x80021FD0  beq v1, zero, +2      guards `sb zero, 0xF(s3)`.
        #                                     Zeroing that counter is exactly
        #                                     what pressing confirm does, so
        #                                     NOPping the guard completes
        #                                     every box the frame it opens.
        #   0x8002200C  beq v1, zero, +0xC4   guards the end-of-box "return
        #                                     unless a button is down" wait.
        #
        # `v1` is the low byte of the pad bitfield at 0x800C4570 in both. So
        # this does not fake a button press globally - it makes the message
        # code alone behave as though confirm were held.
        #
        # X5's equivalents sit at 0x80023D48 and 0x80023D84, and BOTH are
        # exactly 0x1D78 above ours. Two independent sites agreeing on one
        # delta is why these were accepted; a single match would have been a
        # coincidence. The first site's vanilla word is byte-identical to
        # X5's, and both games write the same `+0xF` counter on the message
        # struct.
        #
        # X5 had to check that this did not answer Alia's reward prompt for
        # the player. X6 HAS NO CHOICE PROMPTS at all (Ivor, 2026-08-27, from
        # a completed playthrough), so there is nothing here to get wrong -
        # the menus that do ask something are menus, not messages, and never
        # route through this code.
        ("instant text", 0x80021FD0, REGION_EXE,
         bytes.fromhex("02006010"), bytes(4)),
        ("text auto-advance", 0x8002200C, REGION_EXE,
         bytes.fromhex("c4006010"), bytes(4)),
    ],
    # Reploids never expire. Three `addiu a1, zero, N` -> `ori a1, zero, 0`,
    # so every routine that would record a Reploid as lost records it as
    # untouched instead and the Reploid reappears on the next visit.
    #
    #   0x8004EB70  caught by Nightmare        -> 4 Missing
    #   0x8004FBB8  caught, killed by player   -> 3 Death
    #   0x8004FC24  caught, goes offscreen     -> 4 Missing
    #
    # 0x8004EF44 sets 2 (rescued by the player) and is deliberately UNTOUCHED:
    # that is the state a real rescue writes, and the client's Reploid checks
    # read it.
    #
    # Straight out of the Tweaks WORKBOOK's RescReploids sheet, which carries
    # a full annotated disassembly of these routines and an "always reappear"
    # column giving the replacement word. The PATCHER ships no such tweak -
    # all 144 of its names were enumerated - so this exists only because the
    # workbook and the patcher are different artefacts. Every vanilla word was
    # re-verified against our own extracted EXE rather than trusted.
    #
    # This does NOT replace the client-side fallback. The client counts a
    # Reploid as checked once its nibble leaves state 0, "destroyed" included,
    # so a lost Reploid can never cost a check even if one of these sites is
    # ever missed. Ship plan A2 recommended "(1) plus (2), belt and braces";
    # until now only (2) shipped.
    "protect_reploids": [
        ("Reploid caught by Nightmare", 0x8004EB70, REGION_EXE,
         bytes.fromhex("04000524"), bytes.fromhex("00000534")),
        ("Reploid killed by player", 0x8004FBB8, REGION_EXE,
         bytes.fromhex("03000524"), bytes.fromhex("00000534")),
        ("Reploid caught, goes offscreen", 0x8004FC24, REGION_EXE,
         bytes.fromhex("04000524"), bytes.fromhex("00000534")),
    ],
    # Boot straight to the title. Four NOPs, no code moved.
    #
    # PROVEN INSUFFICIENT ON ITS OWN: with only the two sites below marked
    # "opening video" and "attract demos", a player reported the video after
    # GAME START still played. Tweaks' "Skip opening Intro" is a title-path
    # call, not the post-GAME-START one - so the Capcom pair was added to give
    # this option something it demonstrably removes. If the post-GAME-START
    # movie is wanted gone too, that is a separate, still-unlocated call site.
    "skip_intro_videos": [
        # Capcom logo: two jal sites, NOPped. Tweaks ships these as an AHK
        # continuation block (two offsets under one payload), which an earlier
        # parse of its data file silently read as "no offset at all".
        ("capcom logo (a)", 0x8001CB60, REGION_EXE,
         bytes.fromhex("f872000c"), bytes.fromhex("00000000")),
        ("capcom logo (b)", 0x8001CBA8, REGION_EXE,
         bytes.fromhex("7a4f000c"), bytes.fromhex("00000000")),
        # jal <play opening> -> nop
        ("opening video", 0x8001D3F0, REGION_EXE,
         bytes.fromhex("b369000c"), bytes.fromhex("00000000")),
        # addiu v0, v0, -1 (the idle countdown into the attract demo) -> nop
        ("attract demos", 0x8001DF74, REGION_EXE,
         bytes.fromhex("ffff4224"), bytes.fromhex("00000000")),
    ],
    # beqz v1, +3 -> nop, so the pause menu offers Exit Stage before the
    # stage's boss is down. Dropping the branch is safe on R3000: its delay
    # slot instruction simply always executes, which is the intent.
    "exit_stage_anytime": [
        ("exit stage before clear", 0x80033020, REGION_EXE,
         bytes.fromhex("03006010"), bytes.fromhex("00000000")),
    ],
}


def qol_edits(features: Iterable[str]) -> list[tuple[str, int, str, bytes, bytes]]:
    """The declared edits for the named QoL features, in a stable order."""
    # Materialise ONCE. Building the set inside the loop consumed a generator
    # on the first pass and silently dropped every later group - the kind of
    # bug that ships a patch missing half its edits and still passes a build.
    wanted = set(features)
    out: list[tuple[str, int, str, bytes, bytes]] = []
    for name in QOL_EDITS:            # dict order, not caller order
        if name in wanted:
            out.extend(QOL_EDITS[name])
    return out

# ---- Nightmare Effects -------------------------------------------------------
# The effect CREATION TABLE, ROCK_X6.BIN +0x0C5EB4, resident at RAM 0x800F0F14.
# Eight records of three bytes, one per effect, in the id order the save uses
# at 0x800CD039 (01 Bug, 02 Ice, 03 Fire, 04 Iron, 05 Cube, 06 Rain, 07 Mirror,
# 08 Dark).
#
# DECODED 2026-09-02, and the decode is what makes zeroing a record safe to
# reason about: each record is THREE STAGE INDICES this effect can afflict,
# repeated where it can afflict fewer than three. Read out that way:
#
#   Bug    3, 7      Heatnix, Sheldon        Cube   4, 7      Shark, Sheldon
#   Ice    4         Shark                   Rain   1, 5      Yammark, Scaravich
#   Fire   2, 8      Wolfang, Mijinion       Mirror 2, 6      Wolfang, Turtloid
#   Iron   3, 5, 8   Heatnix, Scaravich,     Dark   1, 6      Yammark, Turtloid
#                    Mijinion
#
# Two independent controls agree with that reading, which is why it is not a
# guess:
#   * only Fire and Mirror contain stage 2, and the research notes already say
#     North Pole is afflicted by Fire or Mirror and nothing else;
#   * every stage 1-8 appears in exactly two records, and the notes already say
#     each stage can be afflicted by exactly two of the eight.
#
# Zeroing a record therefore leaves the effect naming stage 0 three times, so
# it is never assigned to a real stage. The offsets and the vanilla bytes below
# were read off BOTH accepted dumps and are identical on each; the BEHAVIOUR -
# that a zeroed record means "this effect never happens" and nothing else - is
# still [W], taken from acediez's Tweaks patcher, and wants one live look.
NIGHTMARE_TABLE = 0x0C5EB4

NIGHTMARE_EFFECTS: dict[str, tuple[int, str]] = {
    "Bug":    (NIGHTMARE_TABLE + 0,  "030707"),
    "Ice":    (NIGHTMARE_TABLE + 3,  "040404"),
    "Fire":   (NIGHTMARE_TABLE + 6,  "020808"),
    "Iron":   (NIGHTMARE_TABLE + 9,  "030508"),
    "Cube":   (NIGHTMARE_TABLE + 12, "040707"),
    "Rain":   (NIGHTMARE_TABLE + 15, "010505"),
    "Mirror": (NIGHTMARE_TABLE + 18, "020606"),
    "Dark":   (NIGHTMARE_TABLE + 21, "010606"),
}

# The North Pole ice wall. Disabling Fire without this shuts NINE locations
# for good - Wolfang's Heart Tank, his EX Tank and seven of his sixteen
# Reploids - which is the same class of bug that made v0.1.1 a seed-breaking
# release. So it is bundled INTO the Fire group rather than offered beside it,
# and cannot be forgotten.
#
# The check, identical at all four sites:
#
#   lb    v1, 0x43A(s3)    the effect currently on this stage
#   addiu v0, zero, 3      Nightmare Fire
#   beq   v1, v0, +24      equal -> skip the call that builds the wall
#   addu  s1, a0, zero     (delay slot, runs either way)
#   jal   0x8002C9B0       not Fire -> the wall exists
#
# We make the branch unconditional: beq v1,v0 -> beq zero,zero, same offset.
# One word, IDENTICAL at every site, and it leaves v1 holding the real effect
# for anything downstream that reads it.
#
# THE TWEAKS PATCHER ONLY COVERS TWO OF THESE FOUR. Its payloads are
# overlay-relative jumps (j 0x800EF0BC and j 0x800ED684), so they are not
# copyable to the other two sites, and the two it skips - ROCK 0x0996F0 and
# 0x1493D4 - are byte-identical routines reading the same field. Since we
# disable Fire outright, a site left vanilla is a wall that never opens, so
# all four are patched. Found by searching ROCK for the instruction rather
# than trusting the tweak's site list.
NIGHTMARE_WALL_SITES = (0x038E60, 0x0996F0, 0x122BDC, 0x1493D4)
NIGHTMARE_WALL_VANILLA = "05006210"      # beq v1, v0, +24
NIGHTMARE_WALL_PATCHED = "05000010"      # beq zero, zero, +24


def _nightmare_group(effect: str) -> list:
    where, vanilla = NIGHTMARE_EFFECTS[effect]
    edits = [(f"Nightmare {effect}: creation record", where, REGION_ROCK,
              bytes.fromhex(vanilla), bytes(3))]
    if effect == "Fire":
        edits += [
            (f"North Pole ice wall, copy {i + 1} of 4", site + 8, REGION_ROCK,
             bytes.fromhex(NIGHTMARE_WALL_VANILLA),
             bytes.fromhex(NIGHTMARE_WALL_PATCHED))
            for i, site in enumerate(NIGHTMARE_WALL_SITES)]
    return edits


def nightmare_group_name(effect: str) -> str:
    return "nightmare_" + effect.lower()


# The only QoL edits that are DATA rather than code. Everything else in
# QOL_EDITS is whole MIPS instructions and is checked as such; a creation
# record is three bytes of table and would fail that check for the right
# reason, so it is named here instead of exempted by group name.
DATA_EDIT_SITES: frozenset = frozenset(
    where for where, _van in NIGHTMARE_EFFECTS.values())


QOL_EDITS.update({nightmare_group_name(e): _nightmare_group(e)
                  for e in NIGHTMARE_EFFECTS})

# ---- Boss HP ----------------------------------------------------------------
# X6 stores a boss's life bar and its HP in the SAME byte, 0x800CCF5C, written
# at boss init from an immediate in that boss's overlay code. That is why this
# is a disc patch and not the client-side write X5 uses: patching the immediate
# keeps the drawn bar and the real HP consistent by construction, so the
# rematch-bar desync X5 hit at any value cannot happen here.
#
# The bar is drawn from fixed pieces that stop at 32 and the container caps at
# 127 - both confirmed in code (base 32 at ROCK+0x018768; the 0x7F caps at
# ROCK+0x045628 and five siblings). Outside that range the bar misdraws.
BOSS_HP_MIN = 0x20      # 32
BOSS_HP_MAX = 0x7F      # 127

# boss -> [(level, vanilla HP, container offsets)]. Most bosses appear TWICE,
# at a fixed 0xBDA0 stride - the X and Zero copies of the overlay - and both
# get the same value so the two characters fight the same boss.
#
# Every offset here was byte-verified against our own disc: the byte at that
# offset equals the vanilla value in the row. Entries the Tweaks patcher lists
# but which did NOT verify are deliberately absent - Nightmare Mother and
# Dynamo store a base plus a per-level delta rather than a plain immediate,
# and the Tweaks offsets for High Max levels 2-4 point at the wrong levels.
# Randomising those needs the encoding handled, so they keep vanilla HP.
BOSS_HP: dict[str, list[tuple[int, int, tuple[int, ...]]]] = {
    "Commander Yammark":    [(1,  32, (0x02A9BC, 0x14B2DC))],
    "Blizzard Wolfang":     [(1,  48, (0x03C36C, 0x153724))],
    "Blaze Heatnix":        [(1,  48, (0x0476E8, 0x158694)),
                             (3,  52, (0x047700, 0x1586AC)),
                             (4,  56, (0x047710, 0x1586BC))],
    "Metal Shark Player":   [(1,  48, (0x061DDC, 0x15F0EC))],
    "Ground Scaravich":     [(1,  40, (0x070B74, 0x165C3C))],
    "Rainy Turtloid":       [(1,  56, (0x07BFAC, 0x167448))],
    "Shield Sheldon":       [(1,  32, (0x08E8C8, 0x16D4D0))],
    "Infinity Mijinion":    [(1,  48, (0x0A2F28, 0x173CB4))],
    "D-1000":               [(1,  32, (0x018768,))],
    # ONE offset, not two. 0x0591E8 was here until 2026-08-28 and is NOT this
    # boss's HP - it is the operand of an exact-match test on an incrementing
    # counter, 0x208 further into the same overlay:
    #
    #   lbu   v0, 0x5C(s0)        counter on the object
    #   addiu v1, zero, 48        <- the byte that was being randomized
    #   addiu v0, v0, 1
    #   sb    v0, 0x5C(s0)
    #   bne   v0, v1, ...         fires two calls only on an EXACT match
    #
    # Roll it and the gated transition never fires, or fires early. A tester
    # on 0.1.0 cleared the boss's parts and could not damage it afterwards.
    # It passed review because the only check was "the byte here equals the
    # vanilla value", and both sites are literally `addiu v1, zero, 48`.
    # The real site below is confirmed by what consumes it: its immediate is
    # stored to 0x8C(save_base) = 0x800CCF5C, the boss life-bar byte.
    "Nightmare Pressure":   [(1,  48, (0x058FE0,))],
    "Illumina":             [(1,  64, (0x09EB4C,))],
    "Nightmare Zero":       [(1,  48, (0x17A1D4,))],
    "High Max (Hidden Area)": [(1, 48, (0x17F39C,))],
    "High Max (Secret Lab)":  [(1, 48, (0x10171C,))],
    "Sigma":                [(1,  48, (0x0B4148,))],
    "Sigma (Second Form)":  [(1, 127, (0x0B7830,))],
}


# Bosses that are never rolled, however the option is set.
#
# D-1000 is the intro-stage boss: the tutorial, fought with a bare starting X
# before any upgrade exists. A roll took it from 32 to 110 in a real playtest -
# three and a half times vanilla - which is a miserable first impression and
# the first thing any player of this world would meet. Randomizing it buys
# nothing the other fifteen bosses do not already provide.
#
# The intro's SECOND boss needs no entry here: its HP is written by a site
# outside the verified table, so it keeps vanilla values already.
BOSS_HP_NEVER_ROLLED = ("D-1000",)


def rollable_bosses() -> list[str]:
    """Bosses `boss_hp_randomization` may roll, in a stable order."""
    return [b for b in BOSS_HP if b not in BOSS_HP_NEVER_ROLLED]


def boss_hp_edits(rolls: dict[str, int]) -> list[tuple[str, int, str, bytes, bytes]]:
    """Disc edits setting each named boss's level-1 HP to `rolls[boss]`.

    Higher difficulty levels keep their VANILLA INCREMENT over level 1, so a
    boss that gained 4 and 8 HP at ranks 3 and 4 still does. Rolling each
    level independently would let level 3 come out below level 1 and quietly
    invert the rank scaling.

    Every edit carries the vanilla byte it expects, so a roll built for one
    dump cannot silently corrupt another.
    """
    out: list[tuple[str, int, str, bytes, bytes]] = []
    for boss, levels in BOSS_HP.items():        # dict order, deterministic
        if boss not in rolls or boss in BOSS_HP_NEVER_ROLLED:
            continue
        base_hp = levels[0][1]
        for level, vanilla, offsets in levels:
            value = rolls[boss] + (vanilla - base_hp)
            value = max(BOSS_HP_MIN, min(BOSS_HP_MAX, value))
            for offset in offsets:
                out.append((f"{boss} L{level} HP", offset, REGION_ROCK,
                            bytes([vanilla]), bytes([value])))
    return out

# ---- Mode2 Form1 EDC/ECC (Corlett ecm-style tables) --------------------------
_ecc_f = [0] * 256
_ecc_b = [0] * 256
_edc = [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if (_i & 0x80) else 0)) & 0xFF
    _ecc_f[_i] = _j
    _ecc_b[_i ^ _j] = _i
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if (_e & 1) else 0)
    _edc[_i] = _e


def _edc_compute(data: bytes) -> int:
    edc = 0
    for b in data:
        edc = (edc >> 8) ^ _edc[(edc ^ b) & 0xFF]
    return edc


def _ecc_block(sec: bytearray, major_count: int, minor_count: int,
               major_mult: int, minor_inc: int, dest: int) -> None:
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        ecc_a = 0
        ecc_b = 0
        for _ in range(minor_count):
            temp = 0 if index < 4 else sec[0xC + index]  # header zeroed (Mode 2)
            index += minor_inc
            if index >= size:
                index -= size
            ecc_a ^= temp
            ecc_b ^= temp
            ecc_a = _ecc_f[ecc_a]
        ecc_a = _ecc_b[_ecc_f[ecc_a] ^ ecc_b]
        sec[dest + major] = ecc_a
        sec[dest + major + major_count] = ecc_a ^ ecc_b


def regenerate_sector(image: bytearray, sector: int) -> None:
    base = sector * SECTOR_RAW
    sec = bytearray(image[base:base + SECTOR_RAW])
    if sec[15] != 2 or (sec[18] & 0x20):
        raise ValueError(f"sector {sector} is not Mode2 Form1")
    edc = _edc_compute(bytes(sec[0x10:0x818]))
    sec[0x818:0x81C] = edc.to_bytes(4, "little")
    _ecc_block(sec, 86, 24, 2, 86, 0x81C)    # P parity
    _ecc_block(sec, 52, 43, 86, 88, 0x8C8)   # Q parity
    image[base:base + SECTOR_RAW] = sec



def apply_basepatch(rom: bytes, extra_edits: Iterable[tuple] = ()) -> bytes:
    """Apply BASE_EDITS (plus any per-seed extras), then regenerate EDC/ECC for
    every touched sector. The single funnel for all image modification.

    Every base edit declares the vanilla bytes it expects and this refuses to
    run if the image does not match, so a wrong offset or an unexpected dump
    fails loudly rather than corrupting code.

    `extra_edits` entries are `(where, payload, region)` or, preferred,
    `(where, payload, region, expected_vanilla)`. A declared vanilla is
    checked with exactly the same rigour as a base edit - a QoL edit landing
    on the wrong bytes is precisely as corrupting as an A1 edit doing so.
    """
    # Validate BEFORE copying. Refusing a wrong image should not first cost a
    # 600MB allocation - on a machine short of memory that turns a clean
    # "this is the wrong disc" into a MemoryError, which says nothing useful.
    extras = [tuple(e) for e in extra_edits]
    checks = [(label, where, region, expect)
              for label, where, region, expect, _p in A1_EDITS]
    checks += [(f"extra edit at {region}:0x{where:X}", where, region, e[3])
               for e in extras
               for where, _payload, region in [(e[0], e[1], e[2])]
               if len(e) > 3 and e[3] is not None]
    for label, where, region, expect in checks:
        base = addr_to_disc(where, region)
        got = bytes(rom[base:base + len(expect)])
        if got != expect:
            raise ValueError(
                f"refusing to patch {label}: expected {expect.hex()}, "
                f"image has {got.hex()}")
    # A QoL edit that lands on top of another edit would make the result
    # depend on ordering, which is exactly the kind of bug that only shows up
    # in one seed out of fifty. Refuse instead.
    seen: dict[int, str] = {}
    for where, payload, region, *_rest in list(
            (w, p, r) for w, p, r in BASE_EDITS) + extras:
        for i in range(len(payload)):
            off = addr_to_disc(where + i, region)
            if off in seen:
                raise ValueError(
                    f"two edits both write disc offset 0x{off:X} "
                    f"({seen[off]} and {region}:0x{where:X})")
            seen[off] = f"{region}:0x{where:X}"
    image = bytearray(rom)
    touched: dict[int, None] = {}
    for where, payload, region, *_rest in list(
            (w, p, r) for w, p, r in BASE_EDITS) + extras:
        for i, b in enumerate(payload):
            off = addr_to_disc(where + i, region)
            image[off] = b
            touched[off // SECTOR_RAW] = None
    for sector in sorted(touched):
        regenerate_sector(image, sector)
    return bytes(image)
