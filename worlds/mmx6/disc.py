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
    # TWO branches, because the button has two conditions and dropping one
    # leaves the other standing. Read off our own disc (2026-09-03):
    #
    #   80032FF4  lbu   a0, 0x0C(v1)     the current area id
    #   80032FFC  addiu v0, a0, -1
    #   80033000  sltiu v0, v0, 8        one of the eight Maverick stages?
    #   80033004  beq   v0, zero, +11    no  -> no button        <- edit 2
    #   8003300C  lbu   v1, 0x60(v1)     the beaten-stage bitfield, 0x800CCF30
    #   80033018  srav  v1, v1, v0       shift to this area's bit
    #   8003301C  andi  v1, v1, 1
    #   80033020  beqz  v1, +3           not beaten -> no button <- edit 1
    #
    # Edit 1 alone is Tweaks' `ExitButton02`, "always available, but only on
    # the main eight stages" - which is what shipped through 0.2.1, and it is
    # why a player who tried to leave Shield Sheldon's Another Route found
    # nothing there (2026-09-03). Hidden Areas, the Intro Stage and Gate's Lab
    # all fail the range test, so vanilla never offers the button in them and
    # edit 1 never gets that far. Edit 2 is the rest of `ExitButton03`,
    # "always available, even on the Intro Stage" - Ivor's call, taken with
    # the intro risk stated: X5 keeps its own range test for exactly this
    # reason, and leaving X6's intro early is untested.
    #
    # Dropping either branch is safe on R3000: the delay-slot instruction
    # simply always executes, which is the intent in both cases.
    "exit_stage_anytime": [
        ("exit stage before clear", 0x80033020, REGION_EXE,
         bytes.fromhex("03006010"), bytes.fromhex("00000000")),
        ("exit outside the eight main stages", 0x80033004, REGION_EXE,
         bytes.fromhex("0b004010"), bytes.fromhex("00000000")),
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
# release.
#
# These four therefore used to be bundled INSIDE the Fire group, so that
# disabling Fire could not be done without them. That stopped working when
# `nightmare_wall_always_open` arrived and wanted the same four edits with
# Fire left ON: duplicating them into a second group broke the invariant that
# QOL_EDITS groups are DISJOINT and can all be applied at once, and
# test_qol.test_no_two_qol_edits_overlap caught it immediately.
#
# So they live in exactly one group of their own, and the guarantee moves to
# Rom.nightmare_groups, which asks for that group whenever Fire is disabled -
# pinned by test_nightmare.TestDisablingFireAlwaysOpensTheWall. A test is a
# stronger guard than the bundling was anyway: the bundling only made the
# mistake awkward, the test makes it fail.
#
# The check, identical at all four sites:
#
#   +0   8263043A  lb    v1, 0x43A(s3)   the effect currently on this stage
#   +4   24020003  addiu v0, zero, 3     3 = Nightmare Fire
#   +8   10620005  beq   v1, v0, +24     Fire -> jump to +32
#   +12  00808821  addu  s1, a0, zero    (delay slot, runs either way)
#   +16  0C00B26C  jal   0x8002C9B0      \
#   +20  00000000  nop                    |  the NOT-Fire path
#   +24  0803BC51  j     <overlay code>  /
#   +28  00000000  nop
#   +32  24020008  addiu v0, zero, 8     <- the branch lands here
#   +36  82240001  lb    a0, 0x1(s1)
#   +40  24030004  addiu v1, zero, 4
#   +44  A222005C  sb    v0, 0x5C(s1)
#
# It is an if/else on one byte: Fire falls through to +32 and runs inline,
# anything else calls the helper and jumps away into per-overlay code. Fire is
# the OPEN state, so we make the comparison always answer yes:
# beq v1,v0 -> beq zero,zero, same offset. The game then runs the exact path a
# Fire-afflicted stage runs, without Fire being on the stage - and unlike real
# Fire it cannot be overwritten later by Sheldon's Mirror. One word, IDENTICAL
# at every site, and it leaves v1 holding the real effect for anything
# downstream that reads it.
#
# CORRECTION 2026-09-06. This comment used to gloss `jal 0x8002C9B0` as "the
# call that builds the wall". It is not: that address is a seven-instruction
# helper that zeroes eight bytes at a0 and returns. Nothing about the patch
# rests on the gloss - the structural reading (Fire takes one branch,
# everything else takes the other, and Fire is the state where the passage is
# open) is what carries it - but the wrong words were in disc.py and in
# mmx6-ram-notes.md and are corrected in both.
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


# The group the four wall edits live in, and the only one. Reached two ways:
# by disabling Fire (where it is mandatory) and by `nightmare_wall_always_open`
# (where it is the whole point). NOT a Nightmare EFFECT group - it disables no
# effect and zeroes no creation record - so it is deliberately not named
# nightmare_<effect> and nightmare_group_name() can never produce it.
NIGHTMARE_WALL_GROUP = "nightmare_wall_open"


def _nightmare_group(effect: str) -> list:
    where, vanilla = NIGHTMARE_EFFECTS[effect]
    return [(f"Nightmare {effect}: creation record", where, REGION_ROCK,
             bytes.fromhex(vanilla), bytes(3))]


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
QOL_EDITS[NIGHTMARE_WALL_GROUP] = [
    (f"North Pole ice wall, copy {i + 1} of 4", site + 8, REGION_ROCK,
     bytes.fromhex(NIGHTMARE_WALL_VANILLA),
     bytes.fromhex(NIGHTMARE_WALL_PATCHED))
    for i, site in enumerate(NIGHTMARE_WALL_SITES)]

# ---- The endgame gate ---------------------------------------------------------
# Issue -1 of the post-release register, and the durable fix the client-side
# guard was always a stand-in for.
#
# Vanilla opens Gate's Lab on ANY of three conditions, and the decision is one
# flag - a3 - computed at ROCK+0x0D6710:
#
#   lbu   v0, 0x60(a1)     the beaten-stage bitfield, 0x800CCF30
#   xori  v0, v0, 0xFF
#   sltiu a3, v0, 1        a3 = 1 IFF all eight bits set  <- condition 1
#   lh    v0, 0xD2(a1)     Nightmare Souls, X
#   slti  v0, v0, 3000
#   beq   v0, zero, ...    >= 3000 -> force a3 = 1        <- condition 2
#   lh    v0, 0xD4(a1)     Nightmare Souls, Zero
#   slti  v0, v0, 3000
#   ...
#   lb    v0, 0x26(v1)
#   slti  v0, v0, 19       -> force a3 = 1                <- condition 3
#   ...
#   lbu   v0, 0x66(a1)     the progress byte
#   sltiu v0, v0, 3
#   beq   a3, zero, ...    a3 == 0 -> no unlock
#
# Under `all_mavericks_sigma` only condition 1 should count. Conditions 2 and 3 are
# switched off by raising the constant they compare against out of reach: a
# Souls counter is a signed halfword the game caps far below 0x7FFF, so
# `slti v0, v0, 0x7FFF` is always true and the "force a3" path is never taken.
# a3 then falls back to the all-eight test alone.
#
# THIS IS DELIBERATELY NOT AN INJECTED HOOK. Every edit is one immediate, in
# place, leaving the surrounding code shape identical - so there is no
# free-space allocation, no trampoline, and above all no overlay-relative jump
# target (the trap that makes the Tweaks patcher's own Fire payloads
# uncopyable between overlay copies).
#
# What is deliberately NOT touched: the write of `2` at ROCK+0x0C24C0, and the
# two save-LOAD routines at ROCK+0x0CBE2C and EXE+0x00C250. Those carry the
# ordinary 0 -> 1 -> 2 progression and a save being read back; suppressing one
# of them is the X5 blind-NOP mistake that softlocked an endgame. Of the nine
# stores to the progress byte, exactly one writes 3 (ROCK+0x0C2594) and it is
# downstream of the a3 flag, which is why the flag is the right place to act.
#
# CONFIDENCE, stated honestly and differently per site:
#   * the seven Souls sites are CERTAIN - the comparison, the branch and the
#     `addiu a3, zero, 1` it guards were all read off our own dump;
#   * ROCK+0x0D6768 (condition 3, believed to be the High Max route) is
#     INFERRED from control flow. What `save+0x26 >= 19` means is not
#     established; what IS established is that the branch it drives is the
#     third and last writer of a3. Note `slti ?, ?, 19` appears SIXTEEN times
#     in ROCK - 19 is a common scene constant - so only this one may be
#     touched, and a blanket edit would break unrelated code.
ENDGAME_GATE_SOULS = 0x0BB8            # 3000
ENDGAME_GATE_UNREACHABLE = 0x7FFF

ENDGAME_GATE_EDITS: list = [
    # (label, where, region, vanilla, patched)
    ("souls unlock, X (copy A)", 0x0D6728, REGION_ROCK,
     bytes.fromhex("b80b4228"), bytes.fromhex("ff7f4228")),
    ("souls unlock, Zero (copy A)", 0x0D673C, REGION_ROCK,
     bytes.fromhex("b80b4228"), bytes.fromhex("ff7f4228")),
    ("souls unlock, X (copy B)", 0x18E598, REGION_ROCK,
     bytes.fromhex("b80b4228"), bytes.fromhex("ff7f4228")),
    ("souls unlock, Zero (copy B)", 0x18E5AC, REGION_ROCK,
     bytes.fromhex("b80b4228"), bytes.fromhex("ff7f4228")),
    ("High Max unlock path", 0x0D6768, REGION_ROCK,
     bytes.fromhex("13004228"), bytes.fromhex("ff7f4228")),
    # The "Gate revealed" cutscene, which is a SEPARATE trigger from the
    # progress byte - it writes scene 19 straight out of a souls comparison.
    # Left alone, the cutscene would still fire at 3000 souls on a disc whose
    # gate stays shut, which is precisely the replay the bug report described.
    ("gate cutscene on souls (a)", 0x8001E448, REGION_EXE,
     bytes.fromhex("b80b6328"), bytes.fromhex("ff7f6328")),
    ("gate cutscene on souls (b)", 0x8001F194, REGION_EXE,
     bytes.fromhex("b80b6328"), bytes.fromhex("ff7f6328")),
    ("gate cutscene on souls (c)", 0x800347D8, REGION_EXE,
     bytes.fromhex("b80b6328"), bytes.fromhex("ff7f6328")),
]

# ---- The endgame gate, AND High Max -----------------------------------------
# For the `all_mavericks_high_max_sigma` goal: Gate's Lab opens only when all
# eight Mavericks are down AND High Max has been beaten in an Another Route.
#
# Vanilla's a3 is an OR - it starts as the all-eight test and conditions 2 and
# 3 can only ever force it to 1 - so no amount of raising comparison constants
# reaches an AND. This is the one gate edit that changes instructions rather
# than immediates.
#
# THE RECORD IS THE GAME'S OWN LATCH, and this is what makes the whole thing
# cheap. SAVE+0x43B runs 0 -> 1 -> 2:
#
#   0 -> 1  handler 13 of the table at ROCK+0x0C5FD0 (the Zero Nightmare clear)
#   1 -> 2  ROCK+0x0D6788, the gate consuming it when condition 3 fires
#
# CONFIRMED LIVE 2026-09-06: the latch read 1 with Zero Nightmare already
# cleared and High Max alive, and went to 2 the moment High Max died - with one
# Maverick beaten, which is also the control proving condition 3 is the High
# Max route. So `latch == 2` IS "High Max beaten", it is the game's own byte,
# and both save-serialisation routines copy it (ROCK+0x0CBF8C, ROCK+0x0D627C),
# so it survives to the memory card.
#
# The edit keeps condition 3's consume (0x0D6788) and removes only its ability
# to open the gate (0x0D6784), turning it into a pure recorder. The AND itself
# goes in the SOULS block, which this goal neutralises anyway - so it costs no
# free space, no trampoline and no overlay-relative jump:
#
#   0x0D6720  lbu   v0, 0x60(a1)      beaten             (was lh v0, 0xD2(a1))
#   0x0D6724  nop                     (already a nop, load delay)
#   0x0D6728  xori  v0, v0, 0x00FF                       (was slti v0,v0,3000)
#   0x0D672C  sltiu a3, v0, 1         a3 = all eight     (was beq/souls)
#   0x0D6730  lbu   v0, 0x43B(a1)     the latch          (was a nop)
#   0x0D6734  addiu v1, zero, 2       "High Max beaten"  (was lh v0, 0xD4(a1))
#   0x0D6738  beq   v0, v1, +0x0C     -> 0x0D6744, keeping a3   (was a nop)
#   0x0D673C  nop                     (delay slot, runs either way)  (was slti)
#   0x0D6740  addu  a3, zero, zero    NOT beaten -> a3 = 0          (was bne)
#   0x0D6744  addiu v1, t0, -12592    KEPT - v1 = SAVE_BASE, read at 0x0D6750
#   0x0D6748  nop                     the souls force            (was a3 = 1)
#   0x0D674C  addiu v1, t0, -12592    KEPT (vanilla sets v1 twice)
#   ...
#   0x0D6784  nop                     condition 3 no longer opens (was a3 = 1)
#
# Both paths reach 0x0D6744, so v1 is SAVE_BASE either way. a1 is SAVE_BASE
# throughout - proven live, not assumed: the diagnostic build's
# `sb a3, 0xAB(a1)` landed on 0x800CCF7B exactly as predicted. Every load is
# read at least two instructions later, clear of the R3000 load delay slot.
#
# WHY THE BEATEN TEST IS RECOMPUTED HERE. The first version relied on vanilla's
# a3 at 0x0D671C and only ever CLEARED it. That failed live: ROCK+0x0D6708
# branches directly to 0x0D6720, skipping the all-eight computation, so on that
# path a3 was stale and nothing could set it. Vanilla survives the same branch
# because condition 3 forces a3=1 further down - the exact force this patch
# removes. Measured, not deduced: with beaten=FF and the latch at 2, a
# diagnostic build exported a3 as 0.
ENDGAME_GATE_HIGH_MAX_LATCH = 0x043B
ENDGAME_GATE_HIGH_MAX_BEATEN = 2       # the latch value that means "beaten"

ENDGAME_GATE_HIGH_MAX_EDITS: list = [
    # (label, where, region, vanilla, patched)
    #
    # THE ALL-EIGHT TEST IS RECOMPUTED HERE, and that is not redundancy - it is
    # the whole reason this version works. Vanilla computes a3 at 0x0D671C, but
    # ROCK+0x0D6708 branches straight to 0x0D6720 and SKIPS it, leaving a3
    # stale. Vanilla tolerates that because condition 3 could still force a3=1
    # further down - and removing that force is precisely what this patch does.
    # So the first version cleared a3 on that path and could never set it, and
    # the gate was welded shut: measured live 2026-09-06 with beaten=FF and the
    # latch at 2, a3 exported as 0.
    ("High Max AND: reload the beaten field", 0x0D6720, REGION_ROCK,
     bytes.fromhex("d200a284"), bytes.fromhex("6000a290")),
    ("High Max AND: invert it", 0x0D6728, REGION_ROCK,
     bytes.fromhex("b80b4228"), bytes.fromhex("ff004238")),
    ("High Max AND: a3 = all eight", 0x0D672C, REGION_ROCK,
     bytes.fromhex("06004010"), bytes.fromhex("0100472c")),
    ("High Max AND: load the latch", 0x0D6730, REGION_ROCK,
     bytes.fromhex("00000000"), bytes.fromhex("3b04a290")),
    ("High Max AND: the beaten value", 0x0D6734, REGION_ROCK,
     bytes.fromhex("d400a284"), bytes.fromhex("02000324")),
    ("High Max AND: skip the clear when beaten", 0x0D6738, REGION_ROCK,
     bytes.fromhex("00000000"), bytes.fromhex("02004310")),
    ("High Max AND: branch delay slot", 0x0D673C, REGION_ROCK,
     bytes.fromhex("b80b4228"), bytes.fromhex("00000000")),
    ("High Max AND: clear a3 when not beaten", 0x0D6740, REGION_ROCK,
     bytes.fromhex("03004014"), bytes.fromhex("21380000")),
    ("High Max AND: retire the souls unlock", 0x0D6748, REGION_ROCK,
     bytes.fromhex("01000724"), bytes.fromhex("00000000")),
    # Condition 3 keeps its consume at 0x0D6788 - that write is the record -
    # and loses only its power to open the gate on its own.
    ("High Max AND: condition 3 records, does not unlock", 0x0D6784, REGION_ROCK,
     bytes.fromhex("01000724"), bytes.fromhex("00000000")),
]

# The sites in ENDGAME_GATE_EDITS that the AND block OVERWRITES (the copy-A
# souls compares) or deliberately KEEPS ALIVE (the High Max path, which under
# this goal is what writes the record). Everything else in that list is wanted
# by both goals, so it is shared rather than duplicated - and taken by
# subtraction so a site added to ENDGAME_GATE_EDITS later is shared by default
# instead of being silently missed.
_HIGH_MAX_SUPERSEDES = frozenset({0x0D6728, 0x0D673C, 0x0D6768})

ENDGAME_GATE_SHARED_EDITS: list = [
    e for e in ENDGAME_GATE_EDITS if e[1] not in _HIGH_MAX_SUPERSEDES]


def endgame_gate_edits(high_max: bool) -> list:
    """The endgame-gate edits for a goal that closes the gate.

    `high_max` picks the AND: all eight Mavericks AND High Max, rather than all
    eight alone. The two lists share the copy-B souls sites and the three
    "Gate revealed" cutscene sites; they differ on the a3 computation itself,
    and they MUST NOT both be applied - apply_basepatch would refuse the
    duplicate, correctly.
    """
    if high_max:
        return ENDGAME_GATE_HIGH_MAX_EDITS + ENDGAME_GATE_SHARED_EDITS
    return list(ENDGAME_GATE_EDITS)


# ---- Hunter Rank thresholds -------------------------------------------------
# Rank is what buys Power-up Part slots, and it is bought with Nightmare Souls
# - separately for X and for Zero. Below Rank A you can equip NOTHING, which
# is how a playtest ended up with a Zero who could not use any of the Parts
# the multiworld had sent (2026-09-03).
#
# The thresholds are DATA, eight u16 descending, at `0x8006D624` in the EXE.
# Read byte-exact off our own image, not taken from the workbook (which
# exposes the first seven as RankSouls01..07 at the same offsets):
#
#     9999  5000  1200  800  500  300  200  0
#     UH    PA    GA    SA   A    B    C    D
#
# THE SCAN, disassembled from ROCK+0x0DEC74 (X) and ROCK+0x0DECD4 (Zero) -
# both read THIS table, so one edit covers both characters:
#
#     lh    a2, -12382(v0)    souls (0x800CCFA2 X / 0x800CCFA4 Zero)
#     lh    v0, -10716(a1)    table[0]
#     slt   v0, a2, v0        souls < table[0] ?
#     beq   v0, zero, out     no  -> keep index 0
#   loop:
#     slti  v0, s0, 8         eight entries, the last a hard 0
#     beq   v0, zero, out
#     lh    v0, 0(a1)         table[s0]
#     slt   v0, a2, v0
#     bne   v0, zero, loop    souls < threshold -> keep walking down
#
# So the rank is the FIRST index, scanning from UH downwards, whose threshold
# the player's Souls have reached. Two consequences this option depends on:
#
#   * a zero written at index i is reached BEFORE any lower entry, so ties at
#     0 resolve to the HIGHER rank. Zeroing one entry is enough; the entries
#     below it simply become unreachable, and they were worth nothing anyway.
#   * entries ABOVE the zeroed one are untouched, so the ranks past the floor
#     still cost exactly what they cost in the base game.
#
# NOT VERIFIED BY US: that the Parts screen's slot count reads the rank this
# routine computes. The scan above is ours; "Rank A = 1 slot, SA = 2, GA =
# 2+1, PA = 3+1, UH = 4+1" is [G], from the player's guides, and the reader we
# traced is on the Mission Report path. The option is off by default and the
# check is a two-minute one - patch, open the Parts screen - so it is stated
# here rather than assumed away.
RANK_TABLE_ADDR = 0x8006D624
RANK_TABLE_VANILLA = bytes.fromhex("0f278813b0042003f4012c01c8000000")
# Table order, descending. Index 7 is the hard 0 the scan lands on for rank D.
RANK_ORDER = ("UH", "PA", "GA", "SA", "A", "B", "C", "D")


def rank_threshold_edits(rank: str) -> list:
    """Make `rank` free, by zeroing its Souls threshold.

    Emits the WHOLE table with one entry changed rather than a two-byte
    write: the declared vanilla is then the entire table, so a wrong offset
    or a different dump fails on 16 bytes instead of on two, and every edit in
    this world stays a whole number of instructions long.
    """
    key = rank.upper()                      # the YAML key is lower case
    if key == "OFF":
        return []
    index = RANK_ORDER.index(key)           # raises on a name that is not one
    if index >= RANK_ORDER.index("D"):
        raise ValueError("rank D is the floor and already costs nothing")
    table = bytearray(RANK_TABLE_VANILLA)
    table[index * 2:index * 2 + 2] = b"\x00\x00"
    return [(f"Hunter Rank {RANK_ORDER[index]} from zero Souls", RANK_TABLE_ADDR, REGION_EXE,
             RANK_TABLE_VANILLA, bytes(table))]


# ---- Starting life gauge ----------------------------------------------------
# The new-game initialiser, EXE 0x8001E088..: one immediate feeds BOTH
# characters' life bytes -
#
#   addiu v1, zero, 0x20     <- this word
#   sb    v1, 0x5B(a1)       X,    0x800CCF2B
#   sb    v1, 0x5C(a1)       Zero, 0x800CCF2C
#   addiu v0, zero, 0x30 / sb v0, 0x61 / sb v0, 0x62   the weapon gauge, 48
#
# so the starting life is one edit. The Tweaks patcher's LifeUp01 offset
# (1D99661C) is NOT this: that is the free-space block at 0x800769xx it
# injects into, all zeros on a clean disc.
#
# 127 is the hard ceiling and it is the game's, not ours: every reader loads
# the gauge as a SIGNED byte (`lb`, or `lbu` then sll/sra 24), and current HP
# is the low seven bits of player+0x5C with 0x80 as a hit/heal flag. 128 and
# up read as negative.
#
# What the bar DRAWS is a separate question and the full 1..127 is allowed.
# The frame is a SPRITE INDEX, (gauge - 32) / 2 + 0x88 capped at 0x98
# (0x8002497C) - seventeen sizes covering 32..64 - while the FILL is drawn
# separately, one notch per point of CURRENT hp from a fixed anchor
# (0x80024F80). So above 64 the frame stops growing and the fill runs on past
# its end, which is how most games in this genre draw a bar past its vanilla
# maximum and is accepted here. BELOW 32 is the half that genuinely misdraws:
# the index drops beneath the artwork and picks up other HUD sprites. That is
# open - see the issue register, entry 13.
STARTING_LIFE_SITE = 0x8001E098
STARTING_LIFE_VANILLA = 32
LIFE_GAUGE_HARD_MAX = 127                 # the game's ceiling
LIFE_GAUGE_DRAWN_MAX = 64                 # the last size the frame has art for
_STARTING_LIFE_WORD = 0x24030000          # addiu v1, zero, imm


def starting_life_edits(value: int) -> list:
    """The one edit that changes what a new save starts with, or nothing."""
    if not 1 <= value <= LIFE_GAUGE_HARD_MAX:
        raise ValueError(
            f"starting life {value} is outside 1..{LIFE_GAUGE_HARD_MAX}")
    if value == STARTING_LIFE_VANILLA:
        return []
    return [("starting life gauge (new game)", STARTING_LIFE_SITE, REGION_EXE,
             (_STARTING_LIFE_WORD | STARTING_LIFE_VANILLA).to_bytes(4, "little"),
             (_STARTING_LIFE_WORD | value).to_bytes(4, "little"))]


# ---- The life bar's low end -------------------------------------------------
# Below a gauge of 32 the bar draws OTHER HUD SPRITES. The frame is a sprite
# index, `(gauge - 32) / 2 + 0x88` clamped only at the TOP (0x8002497C, second
# copy 0x80024C68), so a gauge under 32 indexes beneath the artwork - and what
# sits there is not shorter bars, it is other HUD elements. Confirmed by
# looking, 2026-09-04: at gauge 30 (index 0x87) a horizontal cyan bar appears
# across the screen, at 16 (0x80) a blue panel with text, at 1 the whole
# top-left group vanishes. There is no frame shorter than the 32 one.
#
# Reported from live play on 0.3.0 as "wrong sprites in every stage". It
# corrects itself as received upgrades raise the gauge over 32, which is why
# the same run later reported the bar as fine.
#
# THE FIX is to floor the index at 0x88 so the shortest real frame is the
# worst case. That cannot be done in place: the block is
#
#   addiu v0, v0, -32      sub, then a signed /2 done as srl/addu/sra, then
#   srl   v1, v0, 31       + 0x88, then the top clamp - nine instructions in
#   addu  v0, v0, v1       nine slots
#   sra   v0, v0, 1
#   addiu s3, v0, 136
#
# and clamping needs FOUR operations (sra/nor/and to floor at zero, then the
# shift) where the rounding trio needs three. One instruction over, at both
# sites. So each site jumps to a six-word hook in the free block at
# 0x800769xx - the same `CodeIndex` space acediez's Tweaks patcher injects
# into, which is why we know it is free code space rather than merely zero.
#
# The delay slot of the outgoing jump is the vanilla `srl v1, v0, 31`, which
# only writes v1 and is harmless; the hook recomputes from v0, still the
# gauge. The return jump's delay slot does the shift, so nothing is wasted.
#
# Above 64 NOTHING CHANGES: the top clamp is untouched and the fill still runs
# past the end of the frame, which is how the genre draws a bar past its
# vanilla maximum and is what players expect.
#
# What this does NOT do: make a low maximum read as FULL. The shortest frame
# holds 32, so a max of 8 draws a 32-capacity bar with 8 in it. Fixing that
# means scaling the FILL as well (0x80024F80 draws `anchor - current`, one
# notch per point, with no divisor to change), which is a second hook.
LIFE_BAR_HOOK = 0x800769E0          # free CodeIndex space; 418 zero bytes here
LIFE_BAR_VANILLA_SUB = 0x2442FFE0   # addiu v0, v0, -32 - the word each site has

# (label, site patched with the jump, address the hook returns to)
LIFE_BAR_SITES: list[tuple[str, int, int]] = [
    ("life bar frame (X/Zero HUD)", 0x80024984, 0x80024994),
    ("life bar frame (second copy)", 0x80024C70, 0x80024C80),
]

_LIFE_BAR_BODY = (
    0x2442FFE0,     # addiu v0, v0, -32     x = gauge - 32
    0x00021FC3,     # sra   v1, v0, 31      -1 if x < 0 else 0
    0x00601827,     # nor   v1, v1, zero    0 if x < 0 else -1
    0x00431024,     # and   v0, v0, v1      max(x, 0)  <- the floor
    None,           # j     <return>        filled in per site
    0x00021043,     # sra   v0, v0, 1       DELAY SLOT: the /2
)


def _life_bar_jump(target: int) -> int:
    """`j target` - the region-relative jump both sites use.

    Named at length because a bare `_j` is CLOBBERED by the ECC table
    builder further down this file, which uses `_j` as a module-level loop
    variable. That shadowing is silent and the failure is a TypeError at
    patch time.
    """
    return (0x02 << 26) | ((target >> 2) & 0x03FFFFFF)


def life_bar_edits(starting_life: int) -> list[tuple[str, int, str, bytes, bytes]]:
    """Floor the life bar's frame index at 0x88, or nothing.

    Only emitted when the seed can actually go below 32. The gauge is
    `starting_hp + step * upgrades received` and upgrades only add, so a seed
    starting at 32 or above never reaches the broken range and gets a
    byte-identical disc.
    """
    if starting_life >= 32:
        return []
    out: list[tuple[str, int, str, bytes, bytes]] = []
    hook = LIFE_BAR_HOOK
    for label, site, ret in LIFE_BAR_SITES:
        out.append((label, site, REGION_EXE,
                    LIFE_BAR_VANILLA_SUB.to_bytes(4, "little"),
                    _life_bar_jump(hook).to_bytes(4, "little")))
        body = b"".join(
            (_life_bar_jump(ret) if w is None else w).to_bytes(4, "little")
            for w in _LIFE_BAR_BODY)
        out.append((f"{label} hook", hook, REGION_EXE,
                    bytes(len(body)), body))          # free space: expect zeros
        hook += len(body)
    return out


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
# The drawing routine says the same thing directly: 0x80024624 computes the
# frame as (hp - 32) / 2 + 0xA3, capped at 0xD3. That is 49 frames covering
# exactly 32..127, so the range below is the artwork's range, not a guess.
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
#
# Byte-equality is NOT enough on its own to say a site is what we think it is,
# and BOSS_HP_WORDS below is what makes the difference - read that comment
# before adding a row here.
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


# The whole vanilla INSTRUCTION at each site, not just its immediate byte.
# Every edit carries this entire word as the bytes it expects, so
# apply_basepatch verifies the opcode and the registers on the player's disc
# and not merely the number sitting in the immediate field.
#
# That distinction is the entire reason this table exists. EIGHT of these
# sites are `addiu v0, v0, N` - an ADD onto a per-level bonus that the boss
# object's level byte indexes out of a table built on the stack - where the
# other twenty are `addiu rt, zero, N`, a plain load of a constant:
#
#   lbu   v1, 0x8F(s0)      the boss object's LEVEL byte
#   addu  v1, s2, v1        index a per-level table, s2 = sp+16
#   lbu   v0, 0x0(v1)       v0 = that level's bonus
#   addiu v0, v0, 48        <- the site
#   sb    v0, 0x8C(s0)      the HP / life-bar byte
#
# A byte-equality check cannot tell the two encodings apart: `addiu v0, v0, 48`
# and `addiu v0, zero, 48` both carry 48 in their immediate. So a high roll,
# met on a boss above level 1, stored bonus + roll, passed 127, and wrapped
# negative through the signed load every reader uses - the boss arrived with
# almost no health. Reported from live play on Infinity Mijinion, 2026-09-03.
# This is the SECOND escape of that shape; the first retired 0x0591E8 below.
#
# Boss level follows Hunter Rank, which climbs with Nightmare Souls, which is
# why it took a real run to see: at level 1 the bonus is 0, so all eight sites
# read exactly their vanilla HP and verified.
#
# `boss_hp_edits` therefore writes `addiu rt, zero, value` at EVERY site,
# clearing the source-register field. The four bosses marked below lose their
# vanilla per-level scaling when they are randomized - which is what the other
# twenty sites already do, and what the clamp to BOSS_HP_MIN..BOSS_HP_MAX
# already claimed to guarantee and could not while a runtime bonus was added
# on afterwards.
BOSS_HP_WORDS: dict[int, int] = {
    # Commander Yammark
    0x02A9BC: 0x24020020,   # addiu v0, zero, 32
    0x14B2DC: 0x24020020,   # addiu v0, zero, 32
    # Blizzard Wolfang
    0x03C36C: 0x24420030,   # addiu v0, v0, 48    <- ADD, not a load
    0x153724: 0x24420030,   # addiu v0, v0, 48    <- ADD, not a load
    # Blaze Heatnix
    0x0476E8: 0x24030030,   # addiu v1, zero, 48
    0x158694: 0x24030030,   # addiu v1, zero, 48
    0x047700: 0x24020034,   # addiu v0, zero, 52
    0x1586AC: 0x24020034,   # addiu v0, zero, 52
    0x047710: 0x24020038,   # addiu v0, zero, 56
    0x1586BC: 0x24020038,   # addiu v0, zero, 56
    # Metal Shark Player
    0x061DDC: 0x24420030,   # addiu v0, v0, 48    <- ADD, not a load
    0x15F0EC: 0x24420030,   # addiu v0, v0, 48    <- ADD, not a load
    # Ground Scaravich
    0x070B74: 0x24020028,   # addiu v0, zero, 40
    0x165C3C: 0x24020028,   # addiu v0, zero, 40
    # Rainy Turtloid
    0x07BFAC: 0x24020038,   # addiu v0, zero, 56
    0x167448: 0x24020038,   # addiu v0, zero, 56
    # Shield Sheldon
    0x08E8C8: 0x24420020,   # addiu v0, v0, 32    <- ADD, not a load
    0x16D4D0: 0x24420020,   # addiu v0, v0, 32    <- ADD, not a load
    # Infinity Mijinion
    0x0A2F28: 0x24420030,   # addiu v0, v0, 48    <- ADD, not a load
    0x173CB4: 0x24420030,   # addiu v0, v0, 48    <- ADD, not a load
    # D-1000
    0x018768: 0x24030020,   # addiu v1, zero, 32
    # Nightmare Pressure
    0x058FE0: 0x24030030,   # addiu v1, zero, 48
    # Illumina
    0x09EB4C: 0x24040040,   # addiu a0, zero, 64
    # Nightmare Zero
    0x17A1D4: 0x24020030,   # addiu v0, zero, 48
    # High Max (Hidden Area)
    0x17F39C: 0x24020030,   # addiu v0, zero, 48
    # High Max (Secret Lab)
    0x10171C: 0x24020030,   # addiu v0, zero, 48
    # Sigma
    0x0B4148: 0x24020030,   # addiu v0, zero, 48
    # Sigma (Second Form)
    0x0B7830: 0x2402007F,   # addiu v0, zero, 127
}

BOSS_HP_ADDIU = 0x09            # the only opcode any of these sites may be
_BOSS_HP_RS = 0x03E00000        # bits 21-25, the source-register field


def boss_hp_load(word: int, value: int) -> int:
    """`word` with its source register cleared and `value` as its immediate.

    Turns `addiu rt, rs, N` into `addiu rt, zero, value`, so the site becomes
    a plain load of a constant whatever it started as, and the byte that
    reaches the life gauge is exactly the clamped roll.
    """
    return (word & ~(_BOSS_HP_RS | 0xFFFF)) | value


def rollable_bosses() -> list[str]:
    """Bosses `boss_hp_randomization` may roll, in a stable order."""
    return [b for b in BOSS_HP if b not in BOSS_HP_NEVER_ROLLED]


def boss_hp_edits(rolls: dict[str, int]) -> list[tuple[str, int, str, bytes, bytes]]:
    """Disc edits setting each named boss's level-1 HP to `rolls[boss]`.

    Higher difficulty levels in the table keep their VANILLA INCREMENT over
    level 1, so a boss that gained 4 and 8 HP at ranks 3 and 4 still does.
    Rolling each level independently would let level 3 come out below level 1
    and quietly invert the rank scaling.

    Each edit is the WHOLE four-byte instruction, patched to
    `addiu rt, zero, value` - see BOSS_HP_WORDS for why writing the immediate
    byte alone was not safe. Both the vanilla and the patched word are
    declared, so apply_basepatch refuses a site whose opcode or registers are
    not what this table says, and a roll built for one dump cannot silently
    corrupt another.
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
                word = BOSS_HP_WORDS[offset]
                out.append((f"{boss} L{level} HP", offset, REGION_ROCK,
                            word.to_bytes(4, "little"),
                            boss_hp_load(word, value).to_bytes(4, "little")))
    return out


# ---- Stage music shuffle -----------------------------------------------------
# All music is CD-XA streamed out of XA/BGM.XA. Two EXE tables sit between the
# game and the audio:
#
#   STREAM TABLE  0x8006E58C, 30 x 16 bytes {start, end, channel, loop}
#                 -> where a BGM id lives on the disc
#   CUE TABLE     0x8007093C, 8 bytes per stage id, four (id, volume) pairs
#                 -> which BGM id a stage asks for
#
# `play_bgm(id, volume)` (0x80018060) is the stream table's only reader;
# `bgm_for_current_stage()` (0x8001854C) indexes the cue table with the stage
# id at 0x800CCEDC - the byte the RAM notes call Current Stage Index.
#
# WE EDIT THE CUE TABLE, NEVER THE STREAM TABLE. Permuting the stream table
# would move a track for every context that plays it; rewriting cue rows moves
# it only for the stages we name, so menus, cutscenes, the Mission Report and
# every jingle keep vanilla music by construction, with nothing to exclude by
# hand. Confirmed live 2026-09-06: two stages traded themes and an untouched
# third stayed vanilla (ai-docs/plans/2026-09-06_music-randomization-feasibility.md).
#
# Rows are chosen against the stage roster in mmx6-ram-notes.md ("Game flow and
# the stage roster"). Deliberately EXCLUDED:
#   0x09, 0x0A  undocumented; they share track 0x14 with a cutscene, so a
#               guess here would move music in a scene nobody asked about
#   0x0B        Cutscene
#   0x0D/0E/0F  Stage Select / Title Menus / Mission Report
#   0x17..0x1C  the rest of the menu block
# INCLUDED and worth naming: 0x0C is Secret Lab 3A (boss rush) and 3B (Sigma),
# 0x10..0x12 are Secret Lab 1 / 2A / 2B, and 0x13..0x16 are the eight Maverick
# stages AGAIN - the revisits, packed two stages per row through the second
# selector. Those revisit rows are why this is a single id->id mapping applied
# everywhere rather than a per-row roll: a stage has to sound the same on the
# second visit as it did on the first.
MUSIC_CUE_TABLE = 0x8007093C

# Vanilla row bytes, extracted from the disc EXE rather than transcribed.
# Each row is four (id, volume) pairs; only the id bytes are ever rewritten -
# the volumes are the game's own mix (0x70/0x75/0x7F) and are left alone.
MUSIC_STAGE_ROWS: dict[int, bytes] = {
    0x00: bytes.fromhex("0975097009750970"),   # Intro stage
    0x01: bytes.fromhex("0b7f0b7f0b7f0b7f"),   # Commander Yammark
    0x02: bytes.fromhex("0d7f0d7f0d7f0d7f"),   # Blizzard Wolfang
    0x03: bytes.fromhex("0e7f0e7f0e7f0e7f"),   # Blaze Heatnix
    0x04: bytes.fromhex("0c7f0c7f0c7f0c7f"),   # Metal Shark Player
    0x05: bytes.fromhex("0f7f0f7f0f7f0f7f"),   # Ground Scaravich
    0x06: bytes.fromhex("107f107f107f107f"),   # Rainy Turtloid
    0x07: bytes.fromhex("117f117f117f117f"),   # Shield Sheldon
    0x08: bytes.fromhex("127f127f127f127f"),   # Infinity Mijinion
    0x0C: bytes.fromhex("147f147f147f147f"),   # Secret Lab 3A rush / 3B Sigma
    0x10: bytes.fromhex("137f137f137f137f"),   # Secret Lab 1
    0x11: bytes.fromhex("137f137f137f137f"),   # Secret Lab 2A
    0x12: bytes.fromhex("137f137f137f137f"),   # Secret Lab 2B
    0x13: bytes.fromhex("0b7f0b7f0d7f0d7f"),   # revisit: Yammark / Wolfang
    0x14: bytes.fromhex("0e7f0e7f0c7f0c7f"),   # revisit: Heatnix / Metal Shark
    0x15: bytes.fromhex("0f7f0f7f107f107f"),   # revisit: Scaravich / Turtloid
    0x16: bytes.fromhex("1175117012751270"),   # revisit: Sheldon / Mijinion
}

# The tracks those rows use - the pool, and nothing outside it. Every one is a
# full-length looping stream (360-416 s), so any of them can stand in for any
# other without a stage falling silent partway through.
MUSIC_STAGE_TRACKS: tuple[int, ...] = (
    0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14)


def music_permutation(rng) -> dict[int, int]:
    """Roll a permutation of the stage tracks. Bijective by construction, so
    every stage theme still exists somewhere and none is used twice."""
    shuffled = list(MUSIC_STAGE_TRACKS)
    rng.shuffle(shuffled)
    return dict(zip(MUSIC_STAGE_TRACKS, shuffled))


def music_edits(mapping: dict[int, int]) -> list:
    """Cue-row rewrites for a stage-track permutation, or nothing.

    EVERY stage row is emitted whenever the option is on, including rows whose
    track happened to map to itself. Skipping the unchanged ones would make
    the set of edit SITES depend on the seed, and the unpatcher's manifest is
    built by running patch_rom once at a fixed seed: a row skipped in that
    build would have no vanilla bytes recorded, and a player whose seed DID
    move that row could not be unpatched. A handful of no-op byte writes is
    the cheap side of that trade.
    """
    if not mapping:
        return []
    if set(mapping) != set(MUSIC_STAGE_TRACKS):
        raise ValueError("music mapping must cover exactly the stage tracks")
    if sorted(mapping.values()) != sorted(MUSIC_STAGE_TRACKS):
        raise ValueError("music mapping must be a permutation, not a mapping "
                         "onto a smaller set - a duplicated track would leave "
                         "another one unreachable")
    out = []
    for row, vanilla in sorted(MUSIC_STAGE_ROWS.items()):
        patched = bytearray(vanilla)
        for pair in range(4):
            patched[pair * 2] = mapping[vanilla[pair * 2]]
        out.append((f"stage music cue row 0x{row:02X}",
                    MUSIC_CUE_TABLE + row * 8, REGION_EXE,
                    bytes(vanilla), bytes(patched)))
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
