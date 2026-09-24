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
    "\"": "“", "–": "-", "—": "-", "…": "...",
}


def lab_sanitize(text: str) -> str:
    """Anything onto the Lab font: accents stripped, near-equivalents
    substituted, the rest dropped, runs of spaces collapsed."""
    import unicodedata
    out = []
    for ch in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(ch):
            continue
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
    item_lines = lab_wrap(item) or ["Nothing"]
    if owner is None:
        return _cut(item_lines, (LAB_LINES, LAB_LINES, 2, 1)[brevity])
    head = lab_wrap(f"{owner}'s") or ["Someone's"]
    if brevity >= 3:
        return _cut(head, 1) + _cut(item_lines, 1)
    if brevity >= 2:
        item_lines = _cut(item_lines, 2)
    tail = lab_wrap(f"({game})") if game and brevity == 0 else []
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


# ---- The full-Lab guard --------------------------------------------------------
# The free-slot search 0x8011EED8 returns a slot pointer, -1 if the part is
# already held, or 0 when all eight slots are full. The selection check
# (0x8011E844) only screens out -1, so with the slots full the purchase at
# 0x8011EBDC stores the part id to ADDRESS 0. Vanilla can never get there -
# 40 bolts do not buy nine parts at vanilla prices - but the repriced Lab can.
# Returning -1 for "full" routes it to "You already have the part" instead.
# Its only callers are those two (checked 2026-09-24). An interim guard: the
# shop patch (v1-design P5) takes purchases off the equip path entirely.
LAB_FULL_RETURN = 0x8011EF1C
LAB_FULL_GUARD = ("Lab full-slots guard", LAB_FULL_RETURN, REGION_EXE,
                  (0x00001021).to_bytes(4, "little"),     # addu  v0, zero, zero
                  (0x2402FFFF).to_bytes(4, "little"))     # addiu v0, zero, -1


# ---- Edits -------------------------------------------------------------------
# (label, where, region, expected vanilla, payload). Grows as the patch design
# lands (v1-design section 5); every edit goes through apply_edits.
BASE_EDITS: list[tuple[str, int, str, bytes, bytes]] = price_edits(LAB_PRICE) + [LAB_FULL_GUARD]


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
