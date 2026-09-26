"""Disc geometry, EDC/ECC, and the three-track layout of Mega Man 8 (SLUS-00453).

Mega Man 8 is the first of these worlds that is not a single image. It is a
Redump THREE-track disc: Track 1 is MODE2/2352 data, Tracks 2 and 3 are Red
Book audio, and the game plays that audio by LBA through the ISO9660 records
END1.DA (LBA 142246) and ZNULL.DAT (LBA 162242). So the audio tracks cannot be
dropped or re-laid out - but only Track 1 is ever edited.

The patched disc is written as ONE file: patched Track 1, then Tracks 2 and 3
byte for byte, with a single-FILE cue whose INDEX times are offset by the
lengths before them. That keeps the X5/X6 shape (one .bin, one .cue), and it
reproduces the original layout exactly - the Redump files carry their own
2-second pregaps, so Track 2's INDEX 01 lands at 142096 + 150 = 142246 and
Track 3's at 162092 + 150 = 162242, the two LBAs the game asks for.
`merged_cue` states that arithmetic; the tests pin it to those two records.

As on X5/X6 every edit goes through one funnel that regenerates EDC/ECC for
each touched sector - MANDATORY, because emulator disc layers error-correct
un-reparitied edits back to vanilla and the patch silently does nothing.
"""
import hashlib
import os
from typing import Iterable

SECTOR_RAW = 2352
USER_OFF = 24          # Mode2 Form1: 12 sync + 4 header + 8 subheader
USER_LEN = 2048
FRAMES_PER_SECOND = 75
PREGAP_FRAMES = 150    # the 2-second pregap each Redump audio file begins with

# ---- The three tracks ------------------------------------------------------
# Redump "Mega Man 8 (USA)", hashed from our copy 2026-09-12 and byte-identical
# to the reference dump the MegaMan8Recomp project publishes.
TRACK_SIZES = (334_209_792, 47_030_592, 37_396_800)
TRACK_MD5 = (
    "4e9e6dcf27ea0e15c5f4d1f93c800378",
    "a75dcbb5c831a966c47563e7ea4150c9",
    "2d7b5e8e94a91bf5423b2356f6a34863",
)
CUE_MD5 = "0ee27bb92ce2cd8ccd69ca46e80234f7"
TRACK_SECTORS = tuple(size // SECTOR_RAW for size in TRACK_SIZES)   # 142096, 19996, 15900

# The CD-DA records the game plays audio through. [D] from the ISO directory.
END1_DA_LBA = 142246
ZNULL_DAT_LBA = 162242

# ---- Files in Track 1 --------------------------------------------------------
# (LBA, size) from the disc's own ISO9660 directory.
EXE_LBA, EXE_SIZE = 23, 1_128_448          # SLUS_004.53
EXE_TADDR, EXE_HDR = 0x800C0000, 0x800     # load address; header is 0x800, not 0x8
EXE_TEXT_END = EXE_TADDR + EXE_SIZE - EXE_HDR

OVL_BASE = 0x801D8000                      # every code overlay loads here [L]
OVERLAYS = {
    "DEMO": (126122, 16840),
    "STAGE00": (126131, 43440), "STAGE01": (126153, 61724),
    "STAGE02": (126184, 69064), "STAGE03": (126218, 74032),
    "STAGE04": (126255, 62844), "STAGE05": (126286, 77328),
    "STAGE06": (126324, 56524), "STAGE07": (126352, 36016),
    "STAGE08": (126370, 37780), "STAGE09": (126389, 15172),
    "STAGE0A": (126397, 41424), "STAGE0B": (126418, 67716),
    "STAGE0C": (126452, 78044), "STAGE0D": (126491, 135740),
}
PACKS = {
    "LABO.PAC": (132364, 483328),          # Dr. Light's Lab - its text is the shop
    # The five attract demos; each swaps in its own weapon loadout (P1).
    "PDEMO00.PAC": (132656, 563200), "PDEMO01.PAC": (132931, 753664),
    "PDEMO02.PAC": (133299, 632832), "PDEMO03.PAC": (133608, 577536),
    "PDEMO04.PAC": (133890, 677888),
}

REGION_EXE = "exe"          # `where` is a RAM address in the EXE
# "ovl:STAGE03"             - `where` is a RAM address inside that overlay
# "pack:LABO.PAC"           - `where` is an offset into that pack file


def _file_offset(lba: int, offset: int) -> int:
    sec, within = divmod(offset, USER_LEN)
    return (lba + sec) * SECTOR_RAW + USER_OFF + within


def addr_to_disc(where: int, region: str) -> int:
    """(address, region) -> byte offset into Track 1."""
    if region == REGION_EXE:
        if not EXE_TADDR <= where < EXE_TEXT_END:
            raise ValueError(f"0x{where:08X} is outside the EXE text")
        return _file_offset(EXE_LBA, EXE_HDR + where - EXE_TADDR)
    kind, _, name = region.partition(":")
    if kind == "ovl" and name in OVERLAYS:
        lba, size = OVERLAYS[name]
        if not OVL_BASE <= where < OVL_BASE + size:
            raise ValueError(f"0x{where:08X} is outside overlay {name}")
        return _file_offset(lba, where - OVL_BASE)
    if kind == "pack" and name in PACKS:
        lba, size = PACKS[name]
        if not 0 <= where < size:
            raise ValueError(f"0x{where:X} is outside {name}")
        return _file_offset(lba, where)
    raise ValueError(f"unknown region {region!r}")


# ---- EDC / ECC (Mode 2 Form 1) -------------------------------------------------
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


# ---- The Lab's shop table ------------------------------------------------------
# 0x801505F0 in the EXE: 18 two-byte records {part index (0-based), price} in
# SHOP order - records 0-9 the start stock (5 is a blank grid cell, FF FF),
# 10-17 the post-Duo stock. Read off the disc 2026-09-24. [D]
SHOP_TABLE = 0x801505F0
# Record -> part id (1-based, the name-table order); None is the blank cell.
SHOP_RECORDS = (2, 8, 7, 3, 4, None, 11, 12, 13, 17, 1, 5, 14, 15, 6, 10, 9, 16)
# Vanilla price by part id: 89 bolts in all, for a game holding 40.
VANILLA_PRICE = {1: 6, 2: 6, 3: 5, 4: 4, 5: 5, 6: 7, 7: 6, 8: 6, 9: 5,
                 10: 6, 11: 5, 12: 5, 13: 5, 14: 4, 15: 5, 16: 4, 17: 5}
# What the patched Lab charges: each vanilla price scaled by 40/89 and rounded,
# which lands on EXACTLY 40 - every part buyable with every bolt (Ivor,
# 2026-09-24). Start stock 21, post-Duo stock 19. Order and relative expense
# are kept: the vanilla 6s and the 7 cost 3, everything else 2.
LAB_PRICE = {1: 3, 2: 3, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 2,
             10: 3, 11: 2, 12: 2, 13: 2, 14: 2, 15: 2, 16: 2, 17: 2}


def price_edits(prices: dict[int, int]) -> list[tuple[str, int, str, bytes, bytes]]:
    """One edit per price byte whose value changes."""
    edits = []
    for record, part in enumerate(SHOP_RECORDS):
        if part is None or prices[part] == VANILLA_PRICE[part]:
            continue
        edits.append((f"Lab price, part {part}", SHOP_TABLE + 2 * record + 1,
                      REGION_EXE, bytes([VANILLA_PRICE[part]]), bytes([prices[part]])))
    return edits


# ---- The Lab's text: each entry names the AP item it holds -------------------
# LABO.PAC chunk 0x12 at pack offset 0xF000: 25 u16 offsets (relative to the
# chunk), then the strings - 8 of Dr. Light's lines, then the 17 part
# descriptions in part-id order. The game lays text into a 20x10 grid: 0x00
# ends a row, a row also ends at 20 characters, and the box always takes 10
# rows, reading on into whatever follows. The chunk is declared 0x650 bytes and
# padded to 0x800 on disc, so a rebuilt chunk may grow to 0x800 without moving
# any other chunk; its size field is the u32 at pack offset 0x5C (entry 10 of
# the PAC header). ram-notes 4a.
LAB_TEXT_OFFSET = 0xF000
LAB_TEXT_ROOM = 0x800
LAB_TEXT_SIZE_FIELD = 0x5C
LAB_TEXT_VANILLA_SIZE = 0x650
LAB_STRINGS = 25
LAB_FIRST_DESCRIPTION = 8
LAB_COLUMNS = 19          # the originals never use the 20th; a full row would
LAB_LINES = 6             # swallow its own 0x00 as a blank row
LAB_ROWS = 10

# The small font (char - 0x41, 32 per row). Everything a Lab line can show.
LAB_CHARSET: dict[str, int] = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{chr(c): c for c in range(ord("a"), ord("z") + 1)},
    **{str(d): 0x81 + d for d in range(5)},
    **{str(d): 0xA1 + d - 5 for d in range(5, 10)},
    "?": 0x5E, "!": 0x5F, ",": 0x60, "+": 0x7C, "-": 0x7D, " ": 0x7E,
    ".": 0x7F, "'": 0x86, "(": 0x89, ")": 0x8A, "“": 0x5C, "”": 0x5D,
}
# What the font lacks, onto the nearest thing it has.
_LAB_SUBSTITUTES = {
    ":": "-", ";": ",", "/": "-", "\\": "-", "|": "-", "_": " ", "=": "-",
    "&": "+", "[": "(", "{": "(", "<": "(", "]": ")", "}": ")", ">": ")",
    "’": "'", "‘": "'", "`": "'", "´": "'",
    "–": "-", "—": "-", "…": "...", "×": "x", "·": "-",
    # Letters NFKD does not decompose, which would otherwise vanish
    # ("Łukasz" came out "ukasz").
    "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "Ø": "O", "ø": "o", "Ł": "L", "ł": "l",
    "ß": "ss", "ı": "i", "Đ": "D", "đ": "d", "Þ": "Th", "þ": "th",
}


def lab_sanitize(text: str) -> str:
    """Anything onto the Lab font: accents stripped, near-equivalents
    substituted, the rest dropped, runs of spaces collapsed. Straight double
    quotes alternate open and close, as the font's curly pair do."""
    import unicodedata
    out, quote_open = [], False
    for ch in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(ch):
            continue
        if ch == "\"":
            ch, quote_open = ("”" if quote_open else "“"), not quote_open
        ch = _LAB_SUBSTITUTES.get(ch, ch)
        out.append("".join(c for c in ch if c in LAB_CHARSET))
    return " ".join("".join(out).split())


def lab_wrap(text: str, width: int = LAB_COLUMNS) -> list[str]:
    """Word-wrap onto `width` columns, splitting a word only if it is longer
    than a whole line."""
    lines: list[str] = []
    line = ""
    for word in lab_sanitize(text).split(" "):
        while len(word) > width:
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:width])
            word = word[width:]
        if not word:
            continue
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        lines.append(line)
    return lines


def _cut(lines: list[str], n: int) -> list[str]:
    """At most `n` lines, the last marked "..." when anything was cut."""
    if len(lines) <= n:
        return lines
    lines = lines[:n]
    lines[-1] = lines[-1][:LAB_COLUMNS - 3].rstrip() + "..."
    return lines


def lab_description(item: str, owner: str | None = None, game: str | None = None,
                    brevity: int = 0) -> list[str]:
    """The lines a Lab entry shows for the item it holds: the item alone when
    it is the player's own, else whose it is, the item, and the game.

    `brevity` trades detail for room: 0 as much as six lines allow, 1 no game,
    2 the item on at most two lines, 3 one line each for owner and item."""
    # Each name is checked for anything drawable BEFORE "'s" or the brackets
    # join it: a name wholly in another script sanitises to nothing, and
    # "'s" / "()" alone used to stand in for it.
    item_lines = lab_wrap(item) or ["Unnamed item"]
    if owner is None:
        return _cut(item_lines, (LAB_LINES, LAB_LINES, 2, 1)[brevity])
    head = lab_wrap(f"{owner}'s") if lab_sanitize(owner) else ["Someone's"]
    if brevity >= 3:
        return _cut(head, 1) + _cut(item_lines, 1)
    if brevity >= 2:
        item_lines = _cut(item_lines, 2)
    tail = lab_wrap(f"({game})") if game and lab_sanitize(game) and brevity == 0 else []
    if len(head + item_lines + tail) > LAB_LINES:
        tail = []
    return _cut(head + item_lines, LAB_LINES - len(tail)) + tail


def lab_fit(entries: dict[int, tuple[str, str | None, str | None]],
            vanilla_chunk: bytes) -> dict[int, list[str]]:
    """Descriptions for `entries` ({part id: (item, owner or None, game)}) at
    the most detail that still fits the chunk - every entry shortened
    together, so the Lab reads consistently."""
    for brevity in range(4):
        lines = {p: lab_description(*e, brevity=brevity) for p, e in entries.items()}
        try:
            lab_text_chunk(vanilla_chunk, lines)
            return lines
        except ValueError:
            continue
    raise ValueError("Lab text cannot fit even at its shortest")


def _lab_string(lines: list[str]) -> bytes:
    """One description as the game reads it: a blank row or two to sit it in
    the box the way the originals do, a row per line, then blank rows to make
    ten, so it never runs on into the next string."""
    if not 1 <= len(lines) <= LAB_LINES:
        raise ValueError(f"a Lab description takes 1-{LAB_LINES} lines, got {len(lines)}")
    lead = 1 if len(lines) == LAB_LINES else 2
    out = b"\x00" * lead
    for line in lines:
        if len(line) > LAB_COLUMNS:
            raise ValueError(f"Lab line longer than {LAB_COLUMNS}: {line!r}")
        out += bytes(LAB_CHARSET[c] for c in line) + b"\x00"
    return out + b"\x00" * (LAB_ROWS - lead - len(lines))


def lab_text_chunk(vanilla_chunk: bytes, descriptions: dict[int, list[str]]) -> bytes:
    """The rebuilt text chunk: Dr. Light's eight lines byte for byte, then a
    new description for every part id in `descriptions` (the rest keep their
    vanilla text). Refuses rather than overflow the chunk's 0x800 bytes."""
    import struct
    offsets = list(struct.unpack_from(f"<{LAB_STRINGS}H", vanilla_chunk, 0))
    strings: list[bytes] = []
    for i in range(LAB_STRINGS):
        end = offsets[i + 1] if i + 1 < LAB_STRINGS else len(vanilla_chunk)
        strings.append(vanilla_chunk[offsets[i]:end])
    for part, lines in descriptions.items():
        strings[LAB_FIRST_DESCRIPTION + part - 1] = _lab_string(lines)
    body = bytearray(2 * LAB_STRINGS)
    for i, s in enumerate(strings):
        struct.pack_into("<H", body, 2 * i, len(body))
        body += s
    if len(body) > LAB_TEXT_ROOM:
        raise ValueError(f"Lab text is {len(body)} bytes; the chunk holds {LAB_TEXT_ROOM}")
    return bytes(body)


def lab_vanilla_chunk(track1: bytes) -> bytes:
    """The vanilla text chunk, read out of Track 1."""
    return bytes(track1[addr_to_disc(LAB_TEXT_OFFSET + i, "pack:LABO.PAC")]
                 for i in range(LAB_TEXT_VANILLA_SIZE))


def lab_text_edits(track1: bytes, entries: dict[int, tuple[str, str | None, str | None]]) -> list[tuple[str, int, str, bytes, bytes]]:
    """Edits writing the rebuilt text chunk and its size into LABO.PAC, for
    `entries` ({part id: (item, owner or None, game)}). The vanilla bytes are
    read from `track1`, whose md5 is checked before any patch runs;
    everything past the new chunk up to 0x800 is zeroed."""
    def read(where: int, n: int) -> bytes:
        return bytes(track1[addr_to_disc(where + i, "pack:LABO.PAC")] for i in range(n))
    vanilla = read(LAB_TEXT_OFFSET, LAB_TEXT_ROOM)
    descriptions = lab_fit(entries, vanilla[:LAB_TEXT_VANILLA_SIZE])
    chunk = lab_text_chunk(vanilla[:LAB_TEXT_VANILLA_SIZE], descriptions)
    payload = chunk + bytes(LAB_TEXT_ROOM - len(chunk))
    size_vanilla = read(LAB_TEXT_SIZE_FIELD, 4)
    if int.from_bytes(size_vanilla, "little") != LAB_TEXT_VANILLA_SIZE:
        raise ValueError("LABO.PAC's text chunk is not where it should be")
    return [
        ("Lab text", LAB_TEXT_OFFSET, "pack:LABO.PAC", vanilla, payload),
        ("Lab text size", LAB_TEXT_SIZE_FIELD, "pack:LABO.PAC", size_vanilla,
         len(chunk).to_bytes(4, "little")),
    ]


# ---- The architecture: X5's, fully decoupled (v1-design 5a) -----------------
# The client is the only granter. Where the game's progression depends on its
# own record (boss kills, Mega Ball, the bolt field) that record stays
# vanilla-written and IS the check record, with capability decoupled from it;
# every other grant is suppressed and writes an AP check record instead. AP
# item state and check records live in one block the client re-initialises
# from server state.

def _w(value: int) -> bytes:
    return value.to_bytes(4, "little")


# ---- The AP block ----------------------------------------------------------------
# Zero padding at the end of the EXE image (0x801D29A4..0x801D3000), which no
# code in the EXE or any overlay touches (ram-notes 7, R11). Being inside the
# image, it is on the disc: the patch writes the signature, version and seed
# stamp there, so a patched game is recognisable from power-on.
AP_BLOCK = 0x801D2A00
AP_SIGNATURE = b"APM8"
AP_VERSION = 1
AP_STAMP = AP_BLOCK + 0x08        # u32, per seed, never 0
AP_PARTS = AP_BLOCK + 0x0C        # u32, part ids 1-17 owned (item state, client)
AP_LAB = AP_BLOCK + 0x10          # u32, Lab entries bought, bit = part id (P5)
AP_RUSH = AP_BLOCK + 0x14         # 4 bytes, Rush pickups checked - BYTES, because
                                  # the pickup's own store writes a byte (P2)
AP_PROCESSED = AP_BLOCK + 0x18    # u32, items the client has applied to THIS game
                                  # (X5's processed count; saved via P11)
AP_BLOCK_SIZE = 0x40


def ap_block_edits(stamp: int) -> list[tuple[str, int, str, bytes, bytes]]:
    """The AP block's on-disc header: signature, version, this seed's stamp."""
    if not 0 < stamp <= 0xFFFFFFFF:
        raise ValueError(f"seed stamp must be a non-zero u32, got {stamp:#x}")
    header = AP_SIGNATURE + _w(AP_VERSION) + _w(stamp)
    return [("AP block header", AP_BLOCK, REGION_EXE, bytes(len(header)), header)]


def seed_stamp(seed_name: str, player: int) -> int:
    """A non-zero u32 naming this seed and slot. The save extension (P11)
    ignores saves carrying a different one."""
    digest = hashlib.md5(f"{seed_name}:{player}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little") or 1


# ---- P1: A1 - weapon capability decoupled from the kill record ---------------
# `+0` of each weapon entry (0x801B1EAC + 4*slot) is BOTH "boss beaten" and
# "weapon usable" - X5's trap. The kill-record readers (the grant and its
# guard, the phase gates, stage select, the pause menu's Exit, the boss rooms,
# the intro's Mega Ball, the save) keep reading +0; the CAPABILITY readers
# move to the unused byte +1 by one immediate each - X5's 0x4C -> 0x4D. Every
# reader was classified by reading its code (ram-notes 6).
WEAPONS = 0x801B1EAC
A1_CAPABILITY_READERS: list[tuple[str, int, str, int]] = [
    # (what, RAM address, region, vanilla word) - `lbu rt, 0x1EAC(rs)` or,
    # for Astro's Homing Sniper check, `lbu rt, 0x1ECC(rs)`; each gains +1.
    ("energy-bar loop", 0x800FA3F4, REGION_EXE, 0x90221EAC),
    ("weapon switch: current still owned?", 0x801104D4, REGION_EXE, 0x90221EAC),
    ("weapon switch: next", 0x80110518, REGION_EXE, 0x90221EAC),
    ("weapon switch: previous", 0x801105A4, REGION_EXE, 0x90221EAC),
    ("pause cursor", 0x80112E7C, REGION_EXE, 0x90221EAC),
    ("pause cursor", 0x80112F1C, REGION_EXE, 0x90221EAC),
    ("pause cursor", 0x80113F08, REGION_EXE, 0x90231EAC),
    ("pause icon", 0x801141A4, REGION_EXE, 0x90221EAC),
    ("pause icon", 0x80114224, REGION_EXE, 0x90221EAC),
    ("pause icon", 0x801144B0, REGION_EXE, 0x90221EAC),
    ("refill item (all weapons)", 0x80128D74, REGION_EXE, 0x90221EAC),
    ("full-recovery item", 0x80128E0C, REGION_EXE, 0x90221EAC),
    ("weapon-energy pickup", 0x801290C4, REGION_EXE, 0x90221EAC),
    ("Astro: Homing Sniper usable?", 0x801DBE4C, "ovl:STAGE07", 0x90421ECC),
    ("Wily 4 Astro refight: Homing Sniper usable?", 0x801F1E04, "ovl:STAGE0D", 0x90421ECC),
]
# The spawn refill (0x8010BE50..8C, the player's spawn state): for each entry
# it zeroes +1, then refills energy if +0. Key the refill on +1 and stop it
# clearing +1 - its only writer anywhere.
A1_SPAWN_REFILL = [
    ("spawn refill: its +1 clear", 0x8010BE70, REGION_EXE, 0xA060FFFF, 0x00000000),  # sb zero,-1(v1) -> nop
    ("spawn refill: owned?", 0x8010BE74, REGION_EXE, 0x90820000, 0x90820001),        # lbu v0,0(a0) -> 1(a0)
]
# The weapon switch steps (cur +- 1) & 0xF until it finds a usable slot - with
# none it spins forever. So the buster is usable from power-on (the EXE load
# puts this byte in RAM and nothing ever clears +1 once the refill's clear is
# gone), and the five attract demos - which swap in their own loadout, every
# +1 = 0, and USE weapons - get +1 = 1 in all ten entries.
A1_BUSTER_SEED = ("buster usable from power-on", WEAPONS + 1, REGION_EXE, b"\x00", b"\x01")
# The intro's Mega Ball pickup also SELECTS it: `sb v1(=1), 0x8016DC08` (the
# current weapon) at STAGE00 0x801E1728. Firing reads only the current
# weapon, so the pickup handed over a usable Mega Ball until the player
# switched away (seen live 2026-09-24). Select the buster instead.
A1_INTRO_SELECT = ("A1 intro Mega Ball: select the buster, not Mega Ball", 0x801E1728,
                   "ovl:STAGE00", (0xA023DC08).to_bytes(4, "little"), (0xA020DC08).to_bytes(4, "little"))
DEMO_LOADOUTS = {"PDEMO00.PAC": 0x21744, "PDEMO01.PAC": 0x36F44, "PDEMO02.PAC": 0x20F44,
                 "PDEMO03.PAC": 0x20F44, "PDEMO04.PAC": 0x24744}


def a1_edits() -> list[tuple[str, int, str, bytes, bytes]]:
    edits = [(f"A1 {what}", where, region, _w(vanilla), _w(vanilla + 1))
             for what, where, region, vanilla in A1_CAPABILITY_READERS]
    edits += [(f"A1 {what}", where, region, _w(vanilla), _w(patched))
              for what, where, region, vanilla, patched in A1_SPAWN_REFILL]
    edits.append(A1_BUSTER_SEED)
    edits.append(A1_INTRO_SELECT)
    for pack, loadout in DEMO_LOADOUTS.items():
        for slot in range(10):
            edits.append((f"A1 {pack} demo loadout slot {slot} usable",
                          loadout + 4 * slot + 1, f"pack:{pack}", b"\x00", b"\x01"))
    return edits


# ---- P2: the Rush pickups record a check instead of granting ------------------
# The adapter is granted by ONE store, `sb 1, 0(ptr)` at 0x80129B08 in the
# pickup object (item id 38), whose pointer comes from this table - which the
# pickup also reads for "already collected" (ram-notes 5, R3). Point the table
# at the AP block's Rush bytes and the store becomes the check record; point
# the five stage reads (drop the pickup or not) at the same bytes, so "owned"
# means "already checked" - exactly what a vanilla revisit does. The client
# grants adapters by writing the live and persistent bytes.
RUSH_TABLE = 0x80150D14
RUSH_LIVE = 0x8016D300
RUSH_STAGE_READS = [
    # (what, RAM of the lbu, overlay, register, adapter) - each read is
    # `lui r, 0x8017` immediately followed by `lbu r, 0xD30k(r)`.
    ("Grenade: Bike drop", 0x801E0C78, "STAGE04", 2, 0),
    ("Grenade: Bike at the mini-boss's spawn", 0x801DED90, "STAGE04", 3, 0),
    ("Clown: Item drop", 0x801E8164, "STAGE02", 2, 1),
    ("Sword: Bomber drop", 0x801DF184, "STAGE05", 2, 2),
    ("Aqua: Health drop", 0x801E1000, "STAGE06", 2, 3),
]


def _lui(rt: int, imm: int) -> int:
    return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)


def _lbu(rt: int, rs: int, imm: int) -> int:
    return (0x24 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _hi_lo(address: int) -> tuple[int, int]:
    """lui/offset halves for a signed 16-bit offset."""
    lo = address & 0xFFFF
    hi = (address >> 16) + (1 if lo & 0x8000 else 0)
    return hi & 0xFFFF, lo


def rush_edits() -> list[tuple[str, int, str, bytes, bytes]]:
    table_vanilla = b"".join(_w(RUSH_LIVE + k) for k in range(4))
    table_patched = b"".join(_w(AP_RUSH + k) for k in range(4))
    edits = [("P2 Rush pickup pointers", RUSH_TABLE, REGION_EXE, table_vanilla, table_patched)]
    for what, where, overlay, reg, k in RUSH_STAGE_READS:
        vhi, vlo = _hi_lo(RUSH_LIVE + k)
        phi, plo = _hi_lo(AP_RUSH + k)
        vanilla = _w(_lui(reg, vhi)) + _w(_lbu(reg, reg, vlo))
        patched = _w(_lui(reg, phi)) + _w(_lbu(reg, reg, plo))
        edits.append((f"P2 {what}", where - 4, f"ovl:{overlay}", vanilla, patched))
    return edits


# ---- P4: a bolt pickup records its bit and grants nothing -----------------------
# 0x80129788 `addiu v0, v0, 1` is the +1 to the counter 0x8016D2F0; the bit
# store at 0x801297B4 - the check record, saved - stays. Bolts come only from
# the bundles the client sends.
BOLT_GRANT = ("P4 bolt pickup: no +1", 0x80129788, REGION_EXE, _w(0x24420001), _w(0x24420000))


# ---- The intro can never be exited ------------------------------------------------
# The pause Exit handler (0x80113550) ALLOWS the intro - `beqz stage` at
# 0x8011358C jumps straight to the exit - whenever the Exit part is in
# effect. Vanilla cannot hold the part during the intro. An AP disc can: the
# client sets a received part's effect flag at once, so an Exit part arriving
# during the intro (or in starting inventory) would let the player leave it -
# and an Exit IS a stage clear (0x801B2995 = 1 -> 0x8010123C), which sets
# phase 1: the intro skipped unplayed, its Mega Ball and bolts 0, 1 and 33
# left behind until the player thinks to replay it. (It CAN be replayed: the
# select's position 2, the slot below Tengu Man, maps to stage 0 and the
# confirm accepts it - 0x801379A8, 0x800FFC50 - seen live 2026-09-25.) Stage 0
# goes to the buzzer instead (0x80113628, the handler's own "denied"); the
# delay slot `sltiu v0, v1, 9` is harmless. X5 keeps its intro out of Exit too.
INTRO_EXIT_DENIED = ("the intro can never be exited", 0x8011358C, REGION_EXE,
                     _w(0x10600017), _w(0x10600026))   # beqz v1 -> 0x801135EC ; -> 0x80113628


# ---- QoL disc options (X5/X6's, ported) ------------------------------------------
# Each is a list of (label, where, region, vanilla, payload), emitted only when
# its option is on - so a seed without it runs vanilla code there. Research
# and the rejected alternatives: the parity plan
# (ai-docs/plans/2026-09-24_mm8-x5-feature-parity.md) and ram-notes 9.
#
# text_skip - typed dialogue (task 0x80103830; the Lab/pause text is a
# separate instant box with nothing to skip). X5's two sites, in the message
# STATE MACHINE, not the renderer:
#   0x8010395C `beqz v0, 0x801039F0` - "no face button held -> yield a frame".
#       NOPped, the task always takes the held path: it keeps typing without
#       yielding, so the whole page appears the frame it opens - exactly what
#       holding a button does in vanilla. (Delay slot `andi v0, s1, 0xff` is
#       what the held path runs anyway.)
#   0x801039A0 `beqz v0, 0x801039C0` - at a page break, "not pressed -> wait".
#       NOPped, every page advances by itself.
# and a third X5 did not need: the typer plays each character's blip only
# when NO button is held (0x80103C70 `bnez v0` skips it), so with site 1 a
# whole page's blips would fire in one frame. `b` makes it always skip - the
# held behaviour again. The engine has no choice code at all (control codes,
# ram-notes 9a) and every choice in the game is its own menu, so nothing can
# be answered for the player; it reads no audio state, so no voice can gate it.
#
# skip_intro_videos - X6's option. The movie players (0x800FD30C the Capcom
# logo, 0x800FD444 ROCK8_n) have exactly six call sites, all direct `jal`s in
# the EXE; the three on the boot -> title -> new game path go, and a fourth
# edit stops the title's idle countdown so no attract demo starts. Each `jal`'s
# delay slot is its argument load - harmless without the call. The movie code
# writes nothing but its own state, and every progression write is in the
# caller after the call, so skipping leaves the game where playing would.
# The story movies (pre-Duo 0x80100AA4, post-Duo 0x801013D8, ending
# 0x80101468) are NOT skipped: each is one button press in vanilla.
QOL_EDITS: dict[str, list[tuple[str, int, str, bytes, bytes]]] = {
    "text_skip": [
        ("text skip: whole page at once", 0x8010395C, REGION_EXE, _w(0x10400024), _w(0)),
        ("text skip: pages advance themselves", 0x801039A0, REGION_EXE, _w(0x10400007), _w(0)),
        ("text skip: no per-character blip", 0x80103C70, REGION_EXE, _w(0x14400007), _w(0x10000007)),
    ],
    "skip_intro_videos": [
        ("skip the Capcom logo", 0x800F7C14, REGION_EXE, _w(0x0C03F4C3), _w(0)),
        # Title-loop mode 0: cold boot AND after every attract demo that times out.
        ("skip the opening movie", 0x800FEB18, REGION_EXE, _w(0x0C03F511), _w(0)),
        # 0x801B2938 counts 0x708 frames down on PRESS START; at 0 an attract demo starts.
        ("no attract demos", 0x800FEE9C, REGION_EXE, _w(0x2442FFFF), _w(0)),
        # The new-game reset 0x80100954 plays ROCK8_1 first (X6 missed its equivalent).
        ("skip the movie after GAME START", 0x80100974, REGION_EXE, _w(0x0C03F511), _w(0)),
    ],
}

# exit_stage_anytime - NOT X5's two-word edit, because MM8 has no separate
# result byte: a pause Exit writes 0x801B2995 = 1, the same value as the
# victory beam-up, and the stage-end handler sends both to the stage-clear
# routine 0x8010123C, which never asks how the stage ended (ram-notes 3a, 5).
# Opening the gate alone would make Exit a free boss kill, a free Duo clear
# and a Wily stage skip. So an Exit is marked with 2 - a value no writer in
# the game stores - and EXIT_GUARD, hooked on the clear routine's first call,
# sends a 2 straight to the routine's own tail: the save prompt (vanilla's
# Exit shows it too) and the phase router. Nothing in between runs: no grant,
# no weapon-get demo, no phase, no Wily counter, no ending. Every other reader
# of the byte tests `!= 0` or `& 0x80`, so 2 behaves as 1 everywhere else.
EXIT_GUARD = """
    lui   v0, 0x801B
    lbu   v0, 0x2995(v0)          ; how the stage ended
    ori   at, zero, 2
    bne   v0, at, clear           ; a real clear (1): exactly as vanilla
    nop
    lui   ra, 0x8010
    addiu ra, ra, 0x1438          ; an Exit: return into the clear's tail -
clear:                            ;   the save prompt, then the router
    j     0x8010BBB8              ; the call the hook displaced (a leaf)
    nop
"""
EXIT_HOOK = 0x80101244            # stage clear's `jal 0x8010BBB8`; delay slot `sw s0, 16(sp)` stays


def exit_edits() -> list[tuple[str, int, str, bytes, bytes]]:
    """exit_stage_anytime: the pause Exit offered in every stage but the
    intro (INTRO_EXIT_DENIED, always on), without the Exit part, marked as an
    exit rather than a clear. Needs EXIT_GUARD, which is always in the cave."""
    from . import mips
    guard = routine_addresses()["exit guard"]
    return [
        # The Exit PART gate: pause +0x0B (the part's effect flag) -> buzzer.
        # The option supersedes the part; with it on, the part does nothing.
        ("exit anytime: no Exit part needed", 0x80113560, REGION_EXE, _w(0x1040002B), _w(0)),
        # `beqz v0(stage < 9)` -> `b 0x801135EC`: every stage from 1 reaches the
        # store (the delay slot's `ori v0, zero, 9` is overwritten there). The
        # intro was already turned away above it.
        ("exit anytime: every stage", 0x80113594, REGION_EXE, _w(0x1040000D), _w(0x10000015)),
        ("exit anytime: mark it an exit (2)", 0x801135EC, REGION_EXE, _w(0x34020001), _w(0x34020002)),
        # The pause close recognises the Exit by value: 1 -> 2, so it closes the
        # way vanilla's Exit does (gameMode2 3, no fade step, music stopped).
        ("exit anytime: pause close knows it", 0x80113AA4, REGION_EXE, _w(0x34020001), _w(0x34020002)),
        ("exit anytime: hook the stage clear", EXIT_HOOK, REGION_EXE, _w(0x0C042EEE),
         _w(mips.word(f"jal {guard:#x}", EXIT_HOOK))),
    ]


# ---- pickupsanity (X5's design, MM8's facts; ram-notes 9g) ---------------------
# Every consumable kind's state function asks one routine, 0x801291E8, "has
# Mega Man touched me?" - seven calls, nothing else calls it. The hooks point
# those seven calls at PICKUP_STUB, which asks the same question and then:
#   * an enemy DROP (obj+8 == 0: the spawner alone stores the record pointer
#     there, and the game itself branches on it) -> vanilla;
#   * the attract demo -> vanilla (its pickups must not set bits);
#   * a record that is not an item-array id 0 (a stale +8) -> vanilla;
#   * a placed pickup that is not a location, or whose location the server
#     has CONFIRMED (the client mirrors checked locations) -> vanilla;
#   * otherwise: set its FOUND bit, delete it, and report "not touched" so
#     its state function grants nothing. Its spawn record stays marked until
#     the next section start, so it keeps coming back until confirmed.
# The stub is always in the cave (inert without the hooks); the hooks and the
# key table go on only with the option, so other seeds run vanilla code.
AP_PICKUP_FOUND = AP_BLOCK + 0x20        # u64, set by the stub, read by the client
AP_PICKUP_CONFIRMED = AP_BLOCK + 0x28    # u64, written by the client
PICKUP_KEYS = AP_BLOCK + 0x40            # u16 stage << 8 | record, 0xFFFF-terminated;
                                         # on disc beside the block, in the same
                                         # unreferenced image padding (R11)
PICKUP_KEYS_ROOM = 0x100
PICKUP_CONTACT = 0x801291E8
PICKUP_HOOKS = (0x80128B28, 0x80128B90, 0x80128BF8, 0x80128C70, 0x80128CE0, 0x80128D58, 0x80128DE4)
PICKUP_STUB = f"""
    addiu sp, sp, -24
    sw    ra, 16(sp)
    jal   {PICKUP_CONTACT:#x}          ; the vanilla contact test, a0 = the pickup
    sw    a0, 20(sp)
    beqz  v0, out                 ; not touched: return 0
    lw    a0, 20(sp)
    nop
    lw    t0, 8(a0)               ; the spawn-record pointer; 0 = an enemy drop
    nop
    beqz  t0, out                 ; a drop: vanilla
    lui   t9, 0x801B
    lw    t9, 0x2944(t9)          ; the attract-demo timer
    nop
    bnez  t9, out                 ; the demo's pickups stay vanilla
    nop
    lbu   t1, 1(t0)               ; the record's id - 0, the consumable
    lbu   t2, 3(t0)               ; the record's type - 2, the item array
    bnez  t1, out
    addiu t2, t2, -2
    bnez  t2, out
    lui   t3, 0x801C
    addiu t3, t3, 0x2B3C          ; the spawn list
    subu  t3, t0, t3
    srl   t3, t3, 3               ; record index
    lui   t4, 0x801C
    lbu   t4, 0x336E(t4)          ; stage index
    lui   t5, 0x801D
    sll   t4, t4, 8
    or    t3, t3, t4              ; key = stage << 8 | record
    addiu t5, t5, {PICKUP_KEYS & 0xFFFF:#x}
    or    t6, zero, zero          ; its bit
scan:
    lhu   t7, 0(t5)
    ori   t8, zero, 0xFFFF
    beq   t7, t8, out             ; not a location: vanilla
    nop
    beq   t7, t3, found
    nop
    addiu t5, t5, 2
    b     scan
    addiu t6, t6, 1
found:
    lui   t0, 0x801D
    addiu t0, t0, 0x2A00          ; the AP block
    srl   t1, t6, 5
    sll   t1, t1, 2
    addu  t0, t0, t1              ; this bit's word
    andi  t2, t6, 31
    ori   t3, zero, 1
    sllv  t3, t3, t2
    lw    t4, {AP_PICKUP_CONFIRMED - AP_BLOCK:#x}(t0)
    lw    t5, {AP_PICKUP_FOUND - AP_BLOCK:#x}(t0)
    and   t4, t4, t3
    bnez  t4, out                 ; confirmed: vanilla
    or    t5, t5, t3
    sw    t5, {AP_PICKUP_FOUND - AP_BLOCK:#x}(t0)          ; FOUND
    jal   0x80105864              ; DeleteObject - what a vanilla collection does
    nop
    or    v0, zero, zero          ; "not touched": the caller grants nothing
out:
    lw    ra, 16(sp)
    nop
    jr    ra
    addiu sp, sp, 24
"""


def pickup_key_table(keys: list[int]) -> bytes:
    table = b"".join(k.to_bytes(2, "little") for k in keys) + b"\xff\xff"
    if len(keys) > 64 or len(table) > PICKUP_KEYS_ROOM:
        raise ValueError(f"{len(keys)} pickup keys do not fit")
    if any(not 0 <= k < 0xFFFF for k in keys):
        raise ValueError("a pickup key collides with the terminator")
    return table


def pickup_edits(keys: list[int]) -> list[tuple[str, int, str, bytes, bytes]]:
    """pickupsanity: the key table and the seven hooks. Needs PICKUP_STUB,
    which is always in the cave."""
    from . import mips
    stub = routine_addresses()["pickupsanity"]
    table = pickup_key_table(keys)
    edits = [("pickupsanity key table", PICKUP_KEYS, REGION_EXE, bytes(len(table)), table)]
    for site in PICKUP_HOOKS:
        edits.append((f"pickupsanity hook {site:#x}", site, REGION_EXE,
                      _w(mips.word(f"jal {PICKUP_CONTACT:#x}", site)),
                      _w(mips.word(f"jal {stub:#x}", site))))
    return edits


# ---- max_life (X5's starting_hp; research 2026-09-25_max-life-research.md) ------
# X5 keeps the maximum in a save byte the client writes. MM8 has none: 40 is
# an immediate in the code that fills or caps the player's HP, so this is
# X6's disc discipline - whole instructions, register fields kept, the vanilla
# word asserted. Every life starts at HP 0 (the object clear 0x801058F0) and
# is filled by the teleport-in; every writer of the player's HP was
# enumerated, and these are all the places 40 is its MAXIMUM (all in the EXE):
PLAYER_MAX_HP = 40
MAX_LIFE_RANGE = (1, 127)      # 0 kills every life on its first frame; above
                               # 127 the game's 127-damage instant kills stop killing
MAX_LIFE_SITES: list[tuple[str, int, int, int, int]] = [
    # (what, where, vanilla word, word with the immediate cleared, N + this)
    ("teleport-in (flying sections): exits at HP == max", 0x8010C144, 0x34020028, 0x34020000, 0),
    ("full recovery: HP = max", 0x80128DF0, 0x34020028, 0x34020000, 0),
    ("life pickup: heals only below max", 0x80128FC0, 0x2C420028, 0x2C420000, 0),
    ("life pickup: over max? (sltiu max+1)", 0x80128FE4, 0x2C420029, 0x2C420000, 1),
    ("life pickup: clamp to max", 0x80128FEC, 0x34020028, 0x34020000, 0),
]
# The normal teleport-in (top state 1, sub 2, 0x8010C0A0) adds 1 HP a frame
# while HP < 40, but hands over control when its ANIMATION ends (+0x2E &
# 0x8000, 0x8010C0DC) - 60 frames - so the immediate alone tops out at 60.
# Rewritten in place, same 9 words: HP = min(HP + k, max), k = ceil(max/60),
# so every life still starts full. k = 1 is vanilla's own curve.
MAX_LIFE_FILL = 0x8010C0B0
MAX_LIFE_FILL_VANILLA = (0x92020047, 0x00000000, 0x2C420028, 0x10400005, 0x00000000,
                         0x92020047, 0x00000000, 0x24420001, 0xA2020047)
MAX_LIFE_FILL_FRAMES = 60


def max_life_fill(max_life: int) -> str:
    step = -(-max_life // MAX_LIFE_FILL_FRAMES)
    return f"""
    lbu   v0, 0x47(s0)            ; the player's HP
    nop
    addiu v0, v0, {step}
    sltiu at, v0, {max_life + 1}
    bnez  at, store               ; not past the max: keep the sum
    nop
    ori   v0, zero, {max_life}    ; past it: the max
store:
    sb    v0, 0x47(s0)
    nop                           ; falls through to 0x8010C0D4, as vanilla
"""


def max_life_edits(max_life: int) -> list[tuple[str, int, str, bytes, bytes]]:
    """max_life: nothing at vanilla's 40; otherwise the fill and the five
    immediates. The life bar's clamps (0x800FA6EC/F8, pause 0x800FA30C/18)
    stay at 40, as the boss bar does: above 40 it reads full until HP falls
    to 40."""
    from . import mips
    lo, hi = MAX_LIFE_RANGE
    if not lo <= max_life <= hi:
        raise ValueError(f"max life {max_life} outside {lo}..{hi}")
    if max_life == PLAYER_MAX_HP:
        return []
    fill = mips.assemble(max_life_fill(max_life), MAX_LIFE_FILL)
    assert len(fill) == len(MAX_LIFE_FILL_VANILLA)
    edits = [("max life: the teleport-in fill", MAX_LIFE_FILL, REGION_EXE,
              mips.to_bytes(list(MAX_LIFE_FILL_VANILLA)), mips.to_bytes(fill))]
    for what, where, vanilla, cleared, plus in MAX_LIFE_SITES:
        edits.append((f"max life: {what}", where, REGION_EXE, _w(vanilla), _w(cleared | (max_life + plus))))
    return edits


def qol_edits(features: Iterable[str]) -> list[tuple[str, int, str, bytes, bytes]]:
    """The edits for the named QoL options, in a stable order."""
    features = set(features)
    unknown = features - set(QOL_EDITS) - {"exit_stage_anytime"}
    if unknown:
        raise ValueError(f"unknown QoL features: {sorted(unknown)}")
    out = [edit for name, edits in QOL_EDITS.items() if name in features for edit in edits]
    if "exit_stage_anytime" in features:
        out += exit_edits()
    return out


# ---- Routines: hand-written code in the dead debug menu -----------------------
# 0x80134E7C..0x80136DAC (7,984 bytes) is the unused debug menu (MAINMENU,
# FLAGCHANGE, ...): nothing calls it - no jal, j or data word points at it, in
# the EXE or any overlay (ram-notes 7, R11). Routines are assembly text,
# encoded and load-delay audited by mips.assemble (X5's ground rule).
CAVE_START, CAVE_END = 0x80134E7C, 0x80136DAC
CARD_BUFFER = 0x80060000          # the save's 1 KB file image (descriptor 0x801585BC)
EXT_SIZE = 24
EXT_MAIN, EXT_BACKUP = 0x338, 0x380   # + EXT_SIZE*slot: the file's unused tail (R2)
EXT_CHECK_KEY = int.from_bytes(AP_SIGNATURE, "little")   # "APM8" as a u32

# P11, the save extension (v1-design 5c). Each record copy in the card file
# gets 24 bytes in the tail the game carries but never reads (0x338..0x3C7 of
# 0x338..0x3FF):
#   +0x00 seed stamp        +0x04 Lab bought      +0x08 Rush checked (4 bytes)
#   +0x0C items processed   +0x10 spare (0)       +0x14 check word
# check = XOR of the five words before it and "APM8". A new file zeroes the
# whole tail, which fails the stamp test - as does a save from another seed
# or a vanilla game. On load the Lab and Rush bits MERGE into the AP block
# (checks are permanent), while the processed count is RESTORED as saved -
# loading an older save rewinds the lives and energy it counts (X5's rule).
_EXT_FIELDS = (("stamp", 0x08), ("lab", 0x10), ("rush", 0x14),
               ("processed", 0x18), ("spare", 0x1C))   # (field, AP block offset)
P11_WRITE = f"""
    lui   t0, 0x801D
    addiu t0, t0, 0x2A00          ; the AP block
    lb    t2, 0xA(s1)             ; the slot being saved, 0-2
    lw    t3, 0x08(t0)            ; seed stamp
    lw    t4, 0x10(t0)            ; Lab bought
    lw    t5, 0x14(t0)            ; Rush checked
    lw    t6, 0x18(t0)            ; items processed
    lw    t8, 0x1C(t0)            ; spare
    sll   t9, t2, 1
    addu  t9, t9, t2              ; slot * 3
    sll   t9, t9, 3               ; slot * 24
    lui   t1, 0x8006              ; the card buffer (the delay slot moved s2 on)
    addu  t9, t1, t9
    lui   t7, 0x384D
    ori   t7, t7, 0x5041          ; "APM8"
    xor   t7, t7, t3
    xor   t7, t7, t4
    xor   t7, t7, t5
    xor   t7, t7, t6
    xor   t7, t7, t8              ; check word
    sw    t3, {EXT_MAIN + 0x00}(t9)
    sw    t4, {EXT_MAIN + 0x04}(t9)
    sw    t5, {EXT_MAIN + 0x08}(t9)
    sw    t6, {EXT_MAIN + 0x0C}(t9)
    sw    t8, {EXT_MAIN + 0x10}(t9)
    sw    t7, {EXT_MAIN + 0x14}(t9)
    sw    t3, {EXT_BACKUP + 0x00}(t9)
    sw    t4, {EXT_BACKUP + 0x04}(t9)
    sw    t5, {EXT_BACKUP + 0x08}(t9)
    sw    t6, {EXT_BACKUP + 0x0C}(t9)
    sw    t8, {EXT_BACKUP + 0x10}(t9)
    sw    t7, {EXT_BACKUP + 0x14}(t9)
    jr    ra
    ori   s0, zero, 3             ; the retry count the hook displaced
"""
P11_LOAD = f"""
    lb    t2, 0xA(s0)             ; the slot being loaded
    lui   t0, 0x801D
    addiu t0, t0, 0x2A00          ; the AP block
    sll   t9, t2, 1
    addu  t9, t9, t2
    sll   t9, t9, 3               ; slot * 24
    addu  t9, s2, t9              ; s2 = the card buffer here
    lw    t3, 0x08(t0)            ; this disc's stamp
    addiu t4, t9, {EXT_MAIN}      ; the main copy first
    ori   t9, zero, 2
try:
    lw    t5, 0x00(t4)            ; stamp
    lw    t6, 0x04(t4)            ; Lab
    lw    t7, 0x08(t4)            ; Rush
    lw    t8, 0x0C(t4)            ; processed
    bne   t5, t3, next            ; another seed, a vanilla save, or empty
    lw    t2, 0x10(t4)            ; spare
    lw    t1, 0x14(t4)            ; check
    xor   t5, t5, t6
    xor   t5, t5, t7
    xor   t5, t5, t8
    xor   t5, t5, t2
    lui   t2, 0x384D
    ori   t2, t2, 0x5041          ; "APM8"
    xor   t5, t5, t2
    bne   t5, t1, next            ; damaged
    nop
    lw    t1, 0x10(t0)            ; merge Lab and Rush - OR, never clear
    lw    t5, 0x14(t0)
    or    t6, t6, t1
    or    t7, t7, t5
    sw    t6, 0x10(t0)
    sw    t7, 0x14(t0)
    b     done
    sw    t8, 0x18(t0)            ; the processed count, as saved
next:
    addiu t9, t9, -1
    bnez  t9, try
    addiu t4, t4, {EXT_BACKUP - EXT_MAIN}   ; then the backup copy
done:
    ori   v0, zero, 1
    jr    ra
    sb    v0, 7(s0)               ; the store the hook displaced
"""

# P5, the Lab purchase: record, do not equip (v1-design 5, R5 research). At
# 0x8011EBD8 the purchase calls the commit with `sb v1, 0(v0)` in the delay
# slot - v1 the part id, v0 the free slot the search returned - and deducts
# the price after it returns (0x8011EBE0..EBF8). The hook calls P5_BUY
# instead and drops the store: the bit is set, nothing is equipped, the
# commit still runs (as a tail call, so it returns to 0x8011EBE0) and the
# price is still deducted.
P5_BUY = """
    lui   t0, 0x801D
    lw    t1, 0x2A10(t0)          ; AP_LAB
    ori   t2, zero, 1
    sllv  t2, t2, v1              ; 1 << part id
    or    t1, t1, t2
    j     0x80101700              ; the commit - returns to 0x8011EBE0
    sw    t1, 0x2A10(t0)
"""

# Where each routine lives, in cave order.
ROUTINES: list[tuple[str, str]] = [
    ("P11 save extension: write", P11_WRITE),
    ("P11 save extension: load", P11_LOAD),
    ("P5 Lab purchase", P5_BUY),
    # Unreachable unless exit_stage_anytime hooks it; kept on every disc so
    # the cave layout never depends on the options.
    ("exit guard", EXIT_GUARD),
    ("pickupsanity", PICKUP_STUB),    # inert unless pickup_edits hooks it
]

# ---- In-place rewrites: whole instruction runs replaced where they stand --------
# (name, address, source, the vanilla words it replaces). Each keeps the host
# function's registers and exits the way the original did; the words after a
# rewrite's end, where it branches past them, are left as they were (dead).
IN_PLACE: list[tuple[str, int, str, list[int]]] = [
    # P5: the Lab's free-slot search (callers 0x8011E848 selection, 0x8011EBC4
    # purchase - no others). Now: -1 ("You already have the part") iff the
    # entry's AP_LAB bit is set, else 0. Nothing stores through the result
    # any more (the purchase hook drops the store), so 0 is safe - and the
    # interim full-Lab guard at 0x8011EF1C is dead code.
    ("P5 Lab search: bought?", 0x8011EED8, """
    lui   v1, 0x801D
    lw    v1, 0x2A10(v1)          ; AP_LAB
    andi  a0, a0, 0xFF
    addiu a0, a0, 1               ; part index -> part id
    srlv  v0, v1, a0
    andi  v0, v0, 1
    jr    ra
    subu  v0, zero, v0            ; -1 bought, 0 not
""", [0x3C038017, 0x2463D2F2, 0x00002821, 0x308400FF, 0x24840001, 0x90620000,
      0x00000000, 0x14400003]),
    # P6: the commit (0x80101700) builds the 24-byte mirror from AP_PARTS -
    # mirror[i] = bit i - instead of wiping it and setting one byte per
    # equipped slot; then the unchanged Rush copy at 0x80101754. Same
    # registers as vanilla (a0 = the mirror, from 0x80101700/04). AP_PARTS
    # bits 0 and 18-31 stay 0 (the client's contract); +0x12..+0x15 are the
    # persistent Rush bytes, rewritten by the copy right after, as in vanilla.
    ("P6 commit: effects from AP_PARTS", 0x80101708, """
    lui   a2, 0x801D
    lw    a2, 0x2A0C(a2)          ; AP_PARTS
    addu  v1, zero, zero
loop:
    srlv  v0, a2, v1
    andi  v0, v0, 1
    addu  a1, a0, v1
    sb    v0, 0(a1)               ; mirror[i] = owned?
    addiu v1, v1, 1
    sltiu v0, v1, 0x18
    bnez  v0, loop
    nop
    b     0x80101754              ; the Rush copy, unchanged
    nop
""", [0x00001821, 0xA0800000, 0x24630001, 0x2C620018, 0x1440FFFC, 0x24840001,
      0x3C04801C, 0x24843340, 0x34060001, 0x3C038017, 0x2463D2F2, 0x24650008,
      0x90620000]),
    # P6b: the pause screen's Laser / Arrow / Auto Shoot icons searched the 8
    # slots for their part id; with parts off the slots they would all hide
    # while the selection (0x8016D2FA, cycled from the MIRROR at 0x8011287C)
    # still worked - invisible options. Now each asks mirror[10 + k]; a1 = 0
    # shows it, 8 hides it, at the untouched `beq a1, 8` (0x80114418).
    ("P6 pause shot icons", 0x801143EC, """
    lui   at, 0x801C
    addu  at, at, v0              ; v0 = k, 1..3
    lbu   a1, 0x334A(at)          ; mirror[10 + k]
    ori   v0, zero, 8
    sltiu a1, a1, 1
    sll   a1, a1, 3               ; 0 if owned, 8 if not
    b     0x80114418
    nop
""", [0x2443000A, 0x00A71021, 0x90420002, 0x00000000, 0x10430006, 0x34020008,
      0x24A50001, 0x2CA20008]),
]


def routine_addresses() -> dict[str, int]:
    """Each routine's address in the cave, laid out in order, word-aligned."""
    from . import mips
    out, pc = {}, (CAVE_START + 3) & ~3
    for name, source in ROUTINES:
        out[name] = pc
        pc += 4 * len(mips.assemble(source, pc))
    if pc > CAVE_END:
        raise ValueError(f"routines overrun the cave by {pc - CAVE_END} bytes")
    return out


def code_layout() -> dict[str, int]:
    """Where this apworld puts the code a seed's stored hooks jump to: the
    cave routines and pickupsanity's key table. seed_edits.json bakes these
    addresses into `jal`s and a `lui` at GENERATION, while the routines are
    laid out by whichever apworld PATCHES - so a seed made by one version and
    patched by another whose routines changed size would jump into the middle
    of other code on every stage clear. The patch records this layout and
    refuses to apply against a different one (pre-release review M1)."""
    return {**routine_addresses(), "pickup keys": PICKUP_KEYS}


def routine_edits(track1: bytes) -> list[tuple[str, int, str, bytes, bytes]]:
    """The routines written over the dead debug menu, and the hooks that call
    them. The cave's vanilla bytes are read from `track1`, whose md5 is
    checked before any patch runs."""
    from . import mips
    at = routine_addresses()
    edits = []
    for name, source in ROUTINES:
        code = mips.to_bytes(mips.assemble(source, at[name]))
        vanilla = bytes(track1[addr_to_disc(at[name] + i, REGION_EXE)] for i in range(len(code)))
        edits.append((f"{name} (routine)", at[name], REGION_EXE, vanilla, code))
    write, load = at["P11 save extension: write"], at["P11 save extension: load"]
    buy = at["P5 Lab purchase"]
    edits += [
        # Card write state, after the record's main and backup copies and
        # before the 1 KB write; the delay slot `lui s2, 0x8016` stays.
        ("P11 hook: save", 0x8011FC40, REGION_EXE, _w(0x34100003),
         _w(mips.word(f"jal {write:#x}", 0x8011FC40))),
        # Load confirm, after the slot's main record reaches 0x801507E0.
        ("P11 hook: load", 0x8011F850, REGION_EXE, _w(0x34020001) + _w(0xA2020007),
         _w(mips.word(f"jal {load:#x}", 0x8011F850)) + _w(0x34020001)),
        # The Lab purchase: `jal commit` / `sb v1, 0(v0)` -> `jal P5_BUY` / nop.
        ("P5 hook: purchase", 0x8011EBD8, REGION_EXE, _w(0x0C0405C0) + _w(0xA0430000),
         _w(mips.word(f"jal {buy:#x}", 0x8011EBD8)) + _w(0)),
    ]
    return edits


def in_place_edits() -> list[tuple[str, int, str, bytes, bytes]]:
    from . import mips
    edits = []
    for name, where, source, vanilla in IN_PLACE:
        words = mips.assemble(source, where)
        if len(words) != len(vanilla):
            raise ValueError(f"{name}: {len(words)} words over {len(vanilla)} vanilla")
        edits.append((name, where, REGION_EXE, b"".join(_w(v) for v in vanilla),
                      mips.to_bytes(words)))
    return edits


def ext_check(stamp: int, lab: int, rush: int, processed: int, spare: int = 0) -> int:
    """The save extension's check word, as the routines compute it."""
    return stamp ^ lab ^ rush ^ processed ^ spare ^ EXT_CHECK_KEY


# ---- Edits -------------------------------------------------------------------
# (label, where, region, expected vanilla, payload). Every edit goes through
# apply_edits. BASE_EDITS are the same for every seed and need no disc to
# build; the routines (whose vanilla bytes are read off the disc) and the
# seed's own edits (the AP block header, the Lab text) are added at patch time.
# (The interim full-Lab guard at 0x8011EF1C is gone: P5's search never returns
# a slot to store through.)
BASE_EDITS: list[tuple[str, int, str, bytes, bytes]] = (
    price_edits(LAB_PRICE) + a1_edits() + rush_edits() + [BOLT_GRANT, INTRO_EXIT_DENIED]
    + in_place_edits())


def apply_edits(track1: bytes, edits: Iterable[tuple[str, int, str, bytes, bytes]]) -> bytes:
    """Apply `edits` to Track 1 and regenerate every touched sector's parity.

    Every edit declares the bytes it expects and nothing is written unless all
    of them match, so a wrong offset or an unexpected dump fails loudly rather
    than corrupting code. Two edits writing the same byte are refused too -
    the result would depend on their order, which is the kind of bug that
    shows in one seed out of fifty.
    """
    edits = list(edits)
    if len(track1) != TRACK_SIZES[0]:
        raise ValueError(f"Track 1 is {len(track1)} bytes, expected {TRACK_SIZES[0]}")
    seen: dict[int, str] = {}
    for label, where, region, vanilla, payload in edits:
        if len(vanilla) != len(payload):
            raise ValueError(f"{label}: vanilla and payload differ in length")
        for i in range(len(payload)):
            off = addr_to_disc(where + i, region)
            if off in seen:
                raise ValueError(f"{label} and {seen[off]} both write 0x{off:X}")
            seen[off] = label
            if track1[off] != vanilla[i]:
                raise ValueError(
                    f"refusing to patch {label}: expected {vanilla.hex()} at "
                    f"{region}:0x{where:X}")
    image = bytearray(track1)
    touched: set[int] = set()
    for label, where, region, _vanilla, payload in edits:
        for i, b in enumerate(payload):
            off = addr_to_disc(where + i, region)
            image[off] = b
            touched.add(off // SECTOR_RAW)
    for sector in sorted(touched):
        regenerate_sector(image, sector)
    return bytes(image)


# ---- The merged image and its cue --------------------------------------------
def msf(frames: int) -> str:
    """Frames (sectors) -> cue MM:SS:FF."""
    minutes, rest = divmod(frames, 60 * FRAMES_PER_SECOND)
    seconds, frame = divmod(rest, FRAMES_PER_SECOND)
    return f"{minutes:02d}:{seconds:02d}:{frame:02d}"


def track_starts() -> tuple[int, int, int]:
    """Sector at which each track's FILE data begins in the merged image."""
    t1, t2, _t3 = TRACK_SECTORS
    return 0, t1, t1 + t2


def merged_cue(bin_name: str) -> str:
    """A single-FILE cue for the merged image, reproducing the Redump TOC."""
    _s1, s2, s3 = track_starts()
    return (
        f'FILE "{bin_name}" BINARY\n'
        f'  TRACK 01 MODE2/2352\n'
        f'    INDEX 01 00:00:00\n'
        f'  TRACK 02 AUDIO\n'
        f'    INDEX 00 {msf(s2)}\n'
        f'    INDEX 01 {msf(s2 + PREGAP_FRAMES)}\n'
        f'  TRACK 03 AUDIO\n'
        f'    INDEX 00 {msf(s3)}\n'
        f'    INDEX 01 {msf(s3 + PREGAP_FRAMES)}\n'
    )


def split_merged(merged: bytes) -> tuple[bytes, bytes, bytes]:
    """The three Redump tracks back out of a merged image (the unpatcher's job)."""
    if len(merged) != sum(TRACK_SIZES):
        raise ValueError(f"merged image is {len(merged)} bytes, expected {sum(TRACK_SIZES)}")
    a, b, _c = TRACK_SIZES
    return merged[:a], merged[a:a + b], merged[a + b:]


def _md5_file(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_audio_tracks(track1_path: str) -> tuple[str, str]:
    """Tracks 2 and 3, found beside Track 1 by SIZE then MD5 - never by name,
    because players rename dumps. Raises with a message a player can act on."""
    folder = os.path.dirname(os.path.abspath(track1_path))
    found: dict[int, str] = {}
    for entry in sorted(os.listdir(folder)):
        path = os.path.join(folder, entry)
        if not os.path.isfile(path):
            continue
        size = os.path.getsize(path)
        for track in (1, 2):
            if track not in found and size == TRACK_SIZES[track] \
                    and _md5_file(path) == TRACK_MD5[track]:
                found[track] = path
    missing = [f"Track {t + 1}" for t in (1, 2) if t not in found]
    if missing:
        raise FileNotFoundError(
            f"Mega Man 8 is a three-track disc, and {' and '.join(missing)} "
            f"could not be found next to {os.path.basename(track1_path)} in "
            f"{folder}. Keep all three .bin files of your dump in one folder.")
    return found[1], found[2]
