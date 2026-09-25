"""Stage music shuffle for Mega Man 8 - X5's feature, rebuilt for MM8's sound banks.

WHY THIS IS NOT X5'S TABLE EDIT
-------------------------------
The stage -> song tables exist and are X5-shaped: section start (0x80100CC0)
plays 0x80137AD4[stage] in a stage's first half and 0x80137AE4[stage] in its
second (midPoint 0x801C3374), through PlaySong 0x800FCB80. But an MM8 "song"
is a whole sound bank, SOUND/PBGMxx.PAC (song id = file number: 0x80137714 =
0x17 + id), and that bank also carries the stage's SOUND EFFECTS. Chunk
types, in file order:

    5      scene-SFX table  -> 0x8016FB34  (4 bytes per sound id; byte 0 =
                                            0x80 | song+1, the tag)
    4      VAB header       -> 0x801BE9AC
    0x201  VAB body         -> SPU 0x54040 as VAB id 1 (id stored to 0x801C3358)
    1      SEQ              -> 0x801B29AC

PlaySound (0x800FCEB4) takes every sound id >= 0x51 from the LOADED song's
table and VAB, and requires the entry's tag to equal song+1 (0x8015E9C4).
Stage overlays request ids that exist only in their own theme's bank (Clown's
0x82-0x8B and 0x1F1 only in song 0x04; Tengu's 0x8D/0x8E/0x91 only in 0x05).
Rewriting the table alone would give every stage another stage's sound
effects. (Track C report, 2026-09-24.)

THE BANK REBUILD
----------------
Inside every stage bank, programs 0-15 are the music and programs 16-17 are
the scene's sound effects: every SEQ uses only programs < 16, every SFX-table
entry only programs >= 16, and no sample (VAG) is referenced from both halves
(asserted over the 15 stage banks when the constants below were baked). The
game already ships the same music with different effect halves - the boss
theme in 11 banks, Sword Man's music in 0x11 and 0x12. So a place gets new
music by rebuilding ITS OWN bank from:

    the SFX table, programs 16-17 and their VAGs   - the place's own bank
    the SEQ, programs 0-15 and their VAGs          - the assigned music's bank

The song ids and the stage tables are untouched, so everything that plays a
stage theme follows (the attract demos, the Wily 4 hub's re-play at
0x801345C0, Wily 3's resume) and every other piece of music - bosses,
mini-bosses, jingles, Lab, stage select, the CD-DA ending - stays vanilla by
construction: X5's guarantee, reached from the other side.

LOSSLESS BY CONSTRUCTION
------------------------
Rebuilding a bank with its own music reproduces it byte for byte; test_music
checks the whole Track 1 image is unchanged under the identity assignment.
That needs:

  * Sample ORDER is kept by slot, not by class. Three banks (0x05, 0x15, 0x2C)
    interleave music and effect samples, so "music first" would reorder them.
    The music bank's music samples fill the place's music slots in order;
    extras follow its last music slot.
  * Dead samples (referenced by no tone; banks 0x06 and 0x16) travel with the
    half of the sample before them - both are music - so nothing is dropped.
  * A bank whose assigned music it ALREADY carries uses its own music half.
    0x01/0x32 (Intro, Duo) carry byte-identical music, but 0x11/0x12 (Sword's
    halves) differ in program-record bytes 2-3 (a per-bank constant) and one
    tone block, so taking Sword's music "from 0x11" for 0x12 would not be
    exact.

WHY THE SOUND REGION IS RE-LAID
-------------------------------
Music sizes differ by up to 5x, so rebuilt banks cannot stay in their sectors.
The 71 files of SOUND/ (LBA 126561..131418, packed, no gaps) are rewritten in
vanilla order, contiguously: subheaders 0x08, 0x89 on each file's last sector
(the vanilla convention, asserted for all 4858 sectors), EDC/ECC regenerated,
the EXE's LBA table rows 0x17..0x5D (the only place the game names these
sectors) and the ISO9660 /SOUND records updated. Sectors left over at the end
of the region get zero data and a zero subheader, as the no-file sectors at
the end of Track 1 have.

The deal only accepts assignments where every rebuilt VAB body stays within
the largest body the game already loads (0x292A0, bank 0x0A: SPU
0x54040..0x7D2E0) and the region does not grow. That rejects a lot: about 1 in
20 X5-style deals survives (a third keep no place's own music; of those 58 %
fit the body bound, 22 % the region, 15 % both). The region is the hard one
and structurally so - in vanilla the two places with the SMALLEST music, Intro
and Duo, share it, and every legal deal gives both of them something bigger.
Hence ATTEMPTS = 500, not X5's 50: 0.95^50 would leave ~8 % of seeds with no
shuffle (85 of 1000 measured); 0.95^500 is ~7e-12. After the budget the answer
is None - no shuffle - never "take the last deal".
"""
import hashlib
import struct

from . import disc

# ---- Places and music -------------------------------------------------------
# A place is a stage; a music is one of the 13 distinct stage themes, named
# after the stage whose theme it is. Intro and Duo share one theme in vanilla
# (banks 0x01 and 0x32 carry byte-identical music) and are split, X5's rule.
# Sword Man is ONE place over both halves' banks, so both halves get the same
# music with their own effects.
PLACES: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("Intro Stage", (0x01,)),
    ("Frost Man", (0x03,)),
    ("Clown Man", (0x04,)),
    ("Tengu Man", (0x05,)),
    ("Grenade Man", (0x06,)),
    ("Sword Man", (0x11, 0x12)),
    ("Aqua Man", (0x15,)),
    ("Astro Man", (0x16,)),
    ("Search Man", (0x17,)),
    ("Duo", (0x32,)),
    ("Wily Stage 1", (0x2B,)),
    ("Wily Stage 2", (0x2C,)),
    ("Wily Stage 3", (0x2D,)),
    ("Wily Stage 4", (0x31,)),
)
# music -> the banks that carry it; the first is where it is taken from.
SOURCES: dict[str, tuple[int, ...]] = {
    "Intro Stage": (0x01, 0x32),
    "Frost Man": (0x03,),
    "Clown Man": (0x04,),
    "Tengu Man": (0x05,),
    "Grenade Man": (0x06,),
    "Sword Man": (0x11, 0x12),
    "Aqua Man": (0x15,),
    "Astro Man": (0x16,),
    "Search Man": (0x17,),
    "Wily Stage 1": (0x2B,),
    "Wily Stage 2": (0x2C,),
    "Wily Stage 3": (0x2D,),
    "Wily Stage 4": (0x31,),
}
VANILLA_MUSIC: dict[str, str] = {place: place for place, _banks in PLACES}
VANILLA_MUSIC["Duo"] = "Intro Stage"

# The game's own stage -> song tables (section start 0x80100CC0), for the tests:
# the places above must be exactly what these rows name.
STAGE_MUSIC_TABLES = (0x80137AD4, 0x80137AE4)      # first half, second half
STAGE_OF_PLACE = {"Intro Stage": 0, "Frost Man": 1, "Clown Man": 2, "Tengu Man": 3,
                  "Grenade Man": 4, "Sword Man": 5, "Aqua Man": 6, "Astro Man": 7,
                  "Search Man": 8, "Duo": 9, "Wily Stage 1": 10, "Wily Stage 2": 11,
                  "Wily Stage 3": 12, "Wily Stage 4": 13}

VAB_BODY_BOUND = 0x292A0      # largest vanilla body (bank 0x0A); SPU 0x54040..0x7D2E0
ATTEMPTS = 500           # see the module docstring: ~5 % of deals are legal

# ---- Baked from the one supported dump (scratch bake.py, 2026-09-24) ------------
SECTOR = disc.USER_LEN        # 0x800
LBA_TABLE = 0x80136F7C        # {u32 lba, u32 size, u32 first word} per asset id
FIRST_ROW = 0x17              # PBGM00; song n is row 0x17 + n; PCOMMON is 0x5D
REGION_FIRST = 126561
REGION_SECTORS = 4858
REGION_MD5 = "cfacf7db55c84b21e6243fa5e1c76c1a"     # raw 2352-byte sectors
SOUND_DIR_LBA = 126558
SOUND_DIR_SECTORS = 3
SOUND_DIR_MD5 = "18a15ee3d7715a1dab8a2b09dd9e18ca"  # user data of the 3 sectors
LBA_ROWS_MD5 = "7805c769620b19983baa129e9c6c24ec"   # the 71 rows, 852 bytes
VANILLA_ROWS: tuple[tuple[int, int, int, int], ...] = (   # (row, lba, size, first word)
    (0x17, 126561, 118784, 4), (0x18, 126619, 129024, 4), (0x19, 126682, 204800, 4),
    (0x1A, 126782, 153600, 4), (0x1B, 126857, 192512, 4), (0x1C, 126951, 143360, 4),
    (0x1D, 127021, 124928, 4), (0x1E, 127082, 167936, 4), (0x1F, 127164, 194560, 4),
    (0x20, 127259, 143360, 4), (0x21, 127329, 196608, 4), (0x22, 127425, 153600, 4),
    (0x23, 127500, 190464, 4), (0x24, 127593, 153600, 4), (0x25, 127668, 184320, 4),
    (0x26, 127758, 129024, 4), (0x27, 127821, 126976, 4), (0x28, 127883, 155648, 4),
    (0x29, 127959, 126976, 4), (0x2A, 128021, 176128, 4), (0x2B, 128107, 77824, 4),
    (0x2C, 128145, 157696, 4), (0x2D, 128222, 147456, 4), (0x2E, 128294, 120832, 4),
    (0x2F, 128353, 182272, 4), (0x30, 128442, 83968, 4), (0x31, 128483, 88064, 4),
    (0x32, 128526, 96256, 4), (0x33, 128573, 96256, 4), (0x34, 128620, 94208, 4),
    (0x35, 128666, 98304, 4), (0x36, 128714, 96256, 4), (0x37, 128761, 96256, 4),
    (0x38, 128808, 98304, 4), (0x39, 128856, 172032, 4), (0x3A, 128940, 182272, 4),
    (0x3B, 129029, 192512, 4), (0x3C, 129123, 147456, 4), (0x3D, 129195, 174080, 4),
    (0x3E, 129280, 178176, 4), (0x3F, 129367, 188416, 4), (0x40, 129459, 124928, 4),
    (0x41, 129520, 176128, 4), (0x42, 129606, 104448, 4), (0x43, 129657, 116736, 4),
    (0x44, 129714, 112640, 4), (0x45, 129769, 161792, 4), (0x46, 129848, 184320, 4),
    (0x47, 129938, 151552, 4), (0x48, 130012, 88064, 4), (0x49, 130055, 86016, 4),
    (0x4A, 130097, 126976, 4), (0x4B, 130159, 124928, 4), (0x4C, 130220, 159744, 4),
    (0x4D, 130298, 65536, 4), (0x4E, 130330, 122880, 4), (0x4F, 130390, 110592, 4),
    (0x50, 130444, 165888, 4), (0x51, 130525, 92160, 4), (0x52, 130570, 147456, 4),
    (0x53, 130642, 67584, 4), (0x54, 130675, 174080, 4), (0x55, 130760, 133120, 4),
    (0x56, 130825, 124928, 4), (0x57, 130886, 184320, 4), (0x58, 130976, 98304, 4),
    (0x59, 131024, 75776, 4), (0x5A, 131061, 133120, 4), (0x5B, 131126, 104448, 4),
    (0x5C, 131177, 155648, 4), (0x5D, 131253, 339968, 3),
)
# bank: (file size, SFX table, VAB header, SEQ, music VAG bytes, SFX VAG bytes).
# Music and SFX bytes include the dead samples that travel with each half.
BANK_SIZES: dict[int, tuple[int, int, int, int, int, int]] = {
    0x01: (0x1F800, 0x63C, 0x2C20, 0x2F41, 0x44D0, 0x13D30),
    0x03: (0x25800, 0x504, 0x2E20, 0x2C87, 0x85D0, 0x16050),
    0x04: (0x2F000, 0x7D4, 0x2E20, 0x1D0F, 0x15EF0, 0x12D40),
    0x05: (0x23000, 0x5F8, 0x2C20, 0x3DFA, 0x6910, 0x145F0),
    0x06: (0x1E800, 0x5AC, 0x2C20, 0x3352, 0xA490, 0xC720),
    0x11: (0x26000, 0x480, 0x2C20, 0x4644, 0x6ED0, 0x165C0),
    0x12: (0x1F000, 0x480, 0x2C20, 0x4644, 0x6ED0, 0xF1E0),
    0x15: (0x26800, 0x44C, 0x2C20, 0x2258, 0x6D50, 0x190C0),
    0x16: (0x24000, 0x47C, 0x2C20, 0x63BC, 0x66A0, 0x12FD0),
    0x17: (0x1D800, 0x7E4, 0x2C20, 0x48DF, 0x5EB0, 0xE250),
    0x2B: (0x19800, 0x500, 0x2C20, 0x1E98, 0x7590, 0xC000),
    0x2C: (0x1C800, 0x5F8, 0x2C20, 0x374E, 0x8AF0, 0xBE20),
    0x2D: (0x1B800, 0x500, 0x2C20, 0x197D, 0x7990, 0xDBB0),
    0x31: (0x15800, 0x480, 0x2C20, 0x2710, 0x65C0, 0x82D0),
    0x32: (0x15000, 0x644, 0x2C20, 0x2F41, 0x44D0, 0x9650),
}

SUBHEADER_DATA = bytes.fromhex("0000080000000800")   # submode 0x08: data
SUBHEADER_LAST = bytes.fromhex("0000890000008900")   # 0x89: data | EOR | EOF
SUBHEADER_FREE = bytes(8)


def _pad(n: int) -> int:
    return (n + SECTOR - 1) // SECTOR * SECTOR


# ---- Generation: the deal ----------------------------------------------------
def music_bank(place_bank: int, music: str) -> int:
    """The bank a place bank takes `music` from: itself when it already carries
    that music (what keeps the identity rebuild exact), else the canonical one."""
    carriers = SOURCES[music]
    return place_bank if place_bank in carriers else carriers[0]


def rebuilt_size(place_bank: int, source_bank: int) -> tuple[int, int]:
    """(file size, VAB body size) of `place_bank` rebuilt with the music of
    `source_bank`. Exact - test_music checks it against every real rebuild."""
    _file, t5, head, _seq, _music, sfx = BANK_SIZES[place_bank]
    _f, _t, _h, seq, music, _s = BANK_SIZES[source_bank]
    body = music + sfx
    return SECTOR + _pad(t5) + _pad(head) + _pad(body) + _pad(seq), body


def fits(assignment: dict[str, str], body_bound: int = VAB_BODY_BOUND) -> bool:
    """Every rebuilt body within the bound, and the SOUND region not grown."""
    new = old = 0
    for place, banks in PLACES:
        for bank in banks:
            size, body = rebuilt_size(bank, music_bank(bank, assignment[place]))
            if body > body_bound:
                return False
            new += size
            old += BANK_SIZES[bank][0]
    return new <= old


def music_assignment(rng, body_bound: int = VAB_BODY_BOUND) -> dict[str, str] | None:
    """Roll a music for every place - X5's bag deal - or None.

    Every music goes in once and `r` more are drawn without replacement, so each
    is used at least once and none more than twice (14 places over 13 musics).
    A deal is rejected when any place keeps its own music (a cosmetic option
    that changes nothing reads as broken - X5) or when it breaks a size bound.
    X5 takes its 50th deal whatever it is; here the bounds are hard, so after
    ATTEMPTS rejections the answer is None, meaning: no shuffle."""
    pool = list(SOURCES)
    places = [place for place, _banks in PLACES]
    k, r = divmod(len(places), len(pool))
    for _attempt in range(ATTEMPTS):
        bag = pool * k + rng.sample(pool, r)
        rng.shuffle(bag)
        out = dict(zip(places, bag))
        if any(out[place] == VANILLA_MUSIC[place] for place in places):
            continue
        if not fits(out, body_bound):
            continue
        return out
    return None


# ---- The bank: parse and rebuild ------------------------------------------------
def pac_chunks(data: bytes) -> list[tuple[int, bytes]]:
    """A PAC's chunks, in file order. Refuses anything not laid out the vanilla
    way (header sector zero-filled, chunks 0x800-aligned and zero-padded)."""
    count, total = struct.unpack_from("<II", data, 0)
    if total != len(data) or any(data[8 + 8 * count:SECTOR]):
        raise ValueError("not a vanilla-shaped PAC")
    out, off = [], SECTOR
    for i in range(count):
        kind, size = struct.unpack_from("<II", data, 8 + 8 * i)
        out.append((kind, data[off:off + size]))
        end = off + _pad(size)
        if any(data[off + size:end]):
            raise ValueError("PAC chunk padding is not zero")
        off = end
    if off != total:
        raise ValueError("PAC chunks do not fill the file")
    return out


def pac_build(chunks: list[tuple[int, bytes]]) -> bytes:
    head = struct.pack("<II", len(chunks), 0)
    for kind, payload in chunks:
        head += struct.pack("<II", kind, len(payload))
    body = b"".join(payload + bytes(_pad(len(payload)) - len(payload)) for _k, payload in chunks)
    head += bytes(SECTOR - len(head))
    data = bytearray(head + body)
    struct.pack_into("<I", data, 4, len(data))
    return bytes(data)


class Vab:
    """A VAB split into what the rebuild moves: the 0x20-byte header, 128
    program records, one 0x200-byte tone block per present program, the size
    table's entry 0, and the samples - each classed music ('m', referenced by
    programs 0-15) or effects ('x', programs 16+). A dead sample takes the
    class of the one before it."""

    def __init__(self, head: bytes, body: bytes):
        self.top = head[:0x20]
        ps, _ts, vs = struct.unpack_from("<HHH", head, 0x12)
        if len(head) != 0x820 + ps * 0x200 + 0x200:
            raise ValueError("VAB header size does not match its program count")
        self.records = [head[0x20 + 16 * p:0x30 + 16 * p] for p in range(128)]
        self.present = [p for p in range(128) if self.records[p][0]]
        if self.present != list(range(ps)):
            raise ValueError("VAB programs are not 0..ps-1")
        self.blocks = {p: head[0x820 + k * 0x200:0x820 + (k + 1) * 0x200]
                       for k, p in enumerate(self.present)}
        table = 0x820 + ps * 0x200
        sizes = [struct.unpack_from("<H", head, table + 2 * i)[0] * 8 for i in range(256)]
        if any(sizes[vs + 1:]) or sum(sizes[1:vs + 1]) != len(body):
            raise ValueError("VAB size table does not describe the body")
        self.size0 = sizes[0]
        self.vags, pos = [], 0
        for g in range(1, vs + 1):
            self.vags.append(body[pos:pos + sizes[g]])
            pos += sizes[g]
        ref: dict[int, str] = {}
        for p in self.present:
            for t in range(self.records[p][0]):
                prog, vag = struct.unpack_from("<hh", self.blocks[p], t * 0x20 + 0x14)
                cls = "m" if p < 16 else "x"
                if prog != p or not 1 <= vag <= vs or ref.setdefault(vag, cls) != cls:
                    raise ValueError(f"VAG {vag} does not belong to one half")
        self.cls, prev = [], "m"
        for g in range(1, vs + 1):
            prev = ref.get(g, prev)
            self.cls.append(prev)
        if not any(p < 16 for p in self.present) or not any(p >= 16 for p in self.present):
            raise ValueError("not a music + effects bank")


def rebuild_vab(place: Vab, music: Vab) -> tuple[bytes, bytes]:
    """(VAB header, VAB body) of `place` with the music half of `music`."""
    wanted = [g for g in range(1, len(music.vags) + 1) if music.cls[g - 1] == "m"]
    slots = [g for g in range(1, len(place.vags) + 1) if place.cls[g - 1] == "m"]
    order: list[tuple[str, int]] = []
    used = 0
    for g in range(1, len(place.vags) + 1):
        if place.cls[g - 1] == "x":
            order.append(("x", g))
        elif g == slots[-1]:
            order += [("m", v) for v in wanted[used:]]
            used = len(wanted)
        elif used < len(wanted):
            order.append(("m", wanted[used]))
            used += 1
    number = {key: i + 1 for i, key in enumerate(order)}
    vags = [music.vags[g - 1] if half == "m" else place.vags[g - 1] for half, g in order]

    records = [music.records[p] if p < 16 else place.records[p] for p in range(128)]
    present = [p for p in range(128) if records[p][0]]
    if present != list(range(len(present))):
        raise ValueError("rebuilt programs are not contiguous")
    blocks = []
    for p in present:
        src, half = (music, "m") if p < 16 else (place, "x")
        block = bytearray(src.blocks[p])
        for t in range(records[p][0]):
            old = struct.unpack_from("<h", block, t * 0x20 + 0x16)[0]
            struct.pack_into("<h", block, t * 0x20 + 0x16, number[(half, old)])
        blocks.append(bytes(block))
    for v in vags:
        if len(v) % 8 or len(v) // 8 > 0xFFFF:
            raise ValueError("a VAG size does not fit the size table")
    table = struct.pack("<256H", place.size0 // 8, *(len(v) // 8 for v in vags),
                        *([0] * (255 - len(vags))))
    body = b"".join(vags)
    top = bytearray(place.top)
    struct.pack_into("<HHH", top, 0x12, len(present), sum(r[0] for r in records), len(vags))
    head = bytes(top) + b"".join(records) + b"".join(blocks) + table
    struct.pack_into("<I", top, 0x0C, len(head) + len(body))
    head = bytes(top) + head[0x20:]
    return head, body


def rebuild_bank(place_data: bytes, music_data: bytes) -> bytes:
    """A PBGM file: the place's SFX table and effect half, the music's SEQ and
    music half. rebuild_bank(x, x) == x for every stage bank."""
    place = dict(pac_chunks(place_data))
    music = dict(pac_chunks(music_data))
    if [k for k, _ in pac_chunks(place_data)] != [5, 4, 0x201, 1]:
        raise ValueError("not a PBGM bank")
    head, body = rebuild_vab(Vab(place[4], place[0x201]), Vab(music[4], music[0x201]))
    return pac_build([(5, place[5]), (4, head), (0x201, body), (1, music[1])])


# ---- Patch time ------------------------------------------------------------------
def _user(image, lba: int, sectors: int) -> bytes:
    return b"".join(image[s * disc.SECTOR_RAW + disc.USER_OFF:
                          s * disc.SECTOR_RAW + disc.USER_OFF + SECTOR]
                    for s in range(lba, lba + sectors))


def _row_offsets(row: int) -> list[int]:
    return [disc.addr_to_disc(LBA_TABLE + 12 * row + i, disc.REGION_EXE) for i in range(12)]


def _verify_vanilla(image) -> None:
    raw = image[REGION_FIRST * disc.SECTOR_RAW:(REGION_FIRST + REGION_SECTORS) * disc.SECTOR_RAW]
    if hashlib.md5(raw).hexdigest() != REGION_MD5:
        raise ValueError("Mega Man 8 music: the SOUND region is not the vanilla one - refusing")
    rows = bytes(image[off] for row, *_r in VANILLA_ROWS for off in _row_offsets(row))
    if hashlib.md5(rows).hexdigest() != LBA_ROWS_MD5:
        raise ValueError("Mega Man 8 music: the EXE's sound LBA table is not vanilla - refusing")
    if hashlib.md5(_user(image, SOUND_DIR_LBA, SOUND_DIR_SECTORS)).hexdigest() != SOUND_DIR_MD5:
        raise ValueError("Mega Man 8 music: the /SOUND directory is not vanilla - refusing")


def _check_assignment(assignment: dict[str, str]) -> None:
    places = {place for place, _banks in PLACES}
    if set(assignment) != places:
        raise ValueError("music assignment must name exactly the places")
    unknown = set(assignment.values()) - set(SOURCES)
    if unknown:
        raise ValueError(f"music assignment names unknown music: {sorted(unknown)}")


def _row_of_dir_name(name: bytes) -> int | None:
    stem = name.split(b";")[0]
    if stem == b"PCOMMON.PAC":
        return 0x5D
    if stem.startswith(b"PBGM") and stem.endswith(b".PAC") and len(stem) == 10:
        return FIRST_ROW + int(stem[4:6], 16)
    return None


def apply_music(image: bytearray, assignment: dict[str, str] | None,
                _force: bool = False) -> set[int]:
    """Rebuild the stage banks for `assignment` and re-lay the SOUND region, in
    place on Track 1. Returns the sectors changed (EDC/ECC already regenerated).

    Refuses (ValueError) unless the SOUND region, the LBA-table rows and the
    /SOUND directory are byte-for-byte vanilla, or if the assignment breaks a
    bound. `None` or an empty assignment changes nothing. `_force` rewrites and
    re-parities every sector even when unchanged (the identity control)."""
    if not assignment:
        return set()
    _check_assignment(assignment)
    if len(image) != disc.TRACK_SIZES[0]:
        raise ValueError(f"Track 1 is {len(image)} bytes, expected {disc.TRACK_SIZES[0]}")
    _verify_vanilla(image)

    files = {row: _user(image, lba, size // SECTOR) for row, lba, size, _first in VANILLA_ROWS}
    new = dict(files)
    for place, banks in PLACES:
        for bank in banks:
            source = music_bank(bank, assignment[place])
            data = rebuild_bank(files[FIRST_ROW + bank], files[FIRST_ROW + source])
            body = dict(pac_chunks(data))[0x201]
            if len(body) > VAB_BODY_BOUND:
                raise ValueError(f"{place}: rebuilt VAB body 0x{len(body):X} is over "
                                 f"0x{VAB_BODY_BOUND:X}")
            new[FIRST_ROW + bank] = data

    # Relay: vanilla order, contiguous from the region's first sector.
    layout, lba = {}, REGION_FIRST
    for row, *_rest in VANILLA_ROWS:
        layout[row] = (lba, len(new[row]))
        lba += len(new[row]) // SECTOR
    if lba > REGION_FIRST + REGION_SECTORS:
        raise ValueError(f"the rebuilt banks need {lba - REGION_FIRST} sectors; the "
                         f"SOUND region has {REGION_SECTORS}")

    touched: set[int] = set()

    def put(sector: int, subheader: bytes, data: bytes) -> None:
        base = sector * disc.SECTOR_RAW
        if _force or image[base + 16:base + disc.USER_OFF + SECTOR] != subheader + data:
            image[base + 16:base + disc.USER_OFF + SECTOR] = subheader + data
            disc.regenerate_sector(image, sector)
            touched.add(sector)

    for row, *_rest in VANILLA_ROWS:
        start, size = layout[row]
        count = size // SECTOR
        for i in range(count):
            put(start + i, SUBHEADER_LAST if i == count - 1 else SUBHEADER_DATA,
                new[row][i * SECTOR:(i + 1) * SECTOR])
    for sector in range(lba, REGION_FIRST + REGION_SECTORS):
        put(sector, SUBHEADER_FREE, bytes(SECTOR))

    # The EXE's LBA table: lba and size move, the first word stays.
    exe_sectors = set()
    for row, *_rest in VANILLA_ROWS:
        start, size = layout[row]
        for off, b in zip(_row_offsets(row)[:8], struct.pack("<II", start, size)):
            if _force or image[off] != b:
                image[off] = b
                exe_sectors.add(off // disc.SECTOR_RAW)
    # The ISO9660 /SOUND records: extent and size, both byte orders.
    directory = bytearray(_user(image, SOUND_DIR_LBA, SOUND_DIR_SECTORS))
    seen = set()
    i = 0
    while i < len(directory):
        length = directory[i]
        if length == 0:
            i = (i // SECTOR + 1) * SECTOR
            continue
        name = bytes(directory[i + 33:i + 33 + directory[i + 32]])
        row = _row_of_dir_name(name)
        if row is not None:
            start, size = layout[row]
            struct.pack_into("<I", directory, i + 2, start)
            struct.pack_into(">I", directory, i + 6, start)
            struct.pack_into("<I", directory, i + 10, size)
            struct.pack_into(">I", directory, i + 14, size)
            seen.add(row)
        i += length
    if seen != {row for row, *_rest in VANILLA_ROWS}:
        raise ValueError("the /SOUND directory does not list the 71 sound files")
    for k in range(SOUND_DIR_SECTORS):
        sector = SOUND_DIR_LBA + k
        base = sector * disc.SECTOR_RAW + disc.USER_OFF
        chunk = bytes(directory[k * SECTOR:(k + 1) * SECTOR])
        if _force or image[base:base + SECTOR] != chunk:
            image[base:base + SECTOR] = chunk
            disc.regenerate_sector(image, sector)
            touched.add(sector)
    for sector in sorted(exe_sectors):
        disc.regenerate_sector(image, sector)
        touched.add(sector)
    return touched
