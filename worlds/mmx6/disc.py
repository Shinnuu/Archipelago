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



def apply_basepatch(rom: bytes,
                    extra_edits: Iterable[tuple[int, bytes, str]] = ()) -> bytes:
    """Apply BASE_EDITS (plus any per-seed extras), then regenerate EDC/ECC for
    every touched sector. The single funnel for all image modification.

    Every base edit declares the vanilla bytes it expects and this refuses to
    run if the image does not match, so a wrong offset or an unexpected dump
    fails loudly rather than corrupting code.
    """
    # Validate BEFORE copying. Refusing a wrong image should not first cost a
    # 600MB allocation - on a machine short of memory that turns a clean
    # "this is the wrong disc" into a MemoryError, which says nothing useful.
    for label, where, region, expect, _patched in A1_EDITS:
        base = addr_to_disc(where, region)
        got = bytes(rom[base:base + len(expect)])
        if got != expect:
            raise ValueError(
                f"refusing to patch {label}: expected {expect.hex()}, "
                f"image has {got.hex()}")
    image = bytearray(rom)
    touched: dict[int, None] = {}
    for where, payload, region in list(BASE_EDITS) + list(extra_edits):
        for i, b in enumerate(payload):
            off = addr_to_disc(where + i, region)
            image[off] = b
            touched[off // SECTOR_RAW] = None
    for sector in sorted(touched):
        regenerate_sector(image, sector)
    return bytes(image)
