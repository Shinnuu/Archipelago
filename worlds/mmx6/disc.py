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
