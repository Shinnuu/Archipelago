"""Stage music shuffle: the deal, the bank rebuild and the re-laid SOUND region.

The hard control is the identity: every place given its own music must leave
Track 1 byte-identical - the whole rebuild and relay path, EDC/ECC included,
reproduces the vanilla disc. The seeded deals are then checked with a parser
written HERE, not music.py's own, so the module is not grading itself:
each rebuilt bank's music half is the source's, its effect half the place's,
every file sits where the LBA table and the ISO directory say, and nothing
outside the SOUND region, its directory and the LBA table's sector moved.
"""
import collections
import hashlib
import random
import struct
import unittest

from .. import disc, music
from .test_disc import TRACK1, have_dump

RAW, UOFF, SEC = disc.SECTOR_RAW, disc.USER_OFF, disc.USER_LEN
REGION_END = music.REGION_FIRST + music.REGION_SECTORS
PLACE_BANKS = {place: banks for place, banks in music.PLACES}
ALL_BANKS = [bank for _place, banks in music.PLACES for bank in banks]


# ---- An independent reader ----------------------------------------------------
def _user(image, lba, sectors):
    return b"".join(bytes(image[s * RAW + UOFF:s * RAW + UOFF + SEC]) for s in range(lba, lba + sectors))


def _chunks(data):
    count, total = struct.unpack_from("<II", data, 0)
    assert total == len(data), "PAC total"
    out, off = {}, SEC
    order = []
    for i in range(count):
        kind, size = struct.unpack_from("<II", data, 8 + 8 * i)
        out[kind] = data[off:off + size]
        order.append(kind)
        off += (size + SEC - 1) // SEC * SEC
    assert off == total, "PAC layout"
    return order, out


def _vab(head, body):
    """-> (ps, ts, vs, fsize, records[128], {prog: [(slot bytes, vag bytes)]},
    {prog: unused-slot bytes}) read with nothing but struct."""
    ps, ts, vs = struct.unpack_from("<HHH", head, 0x12)
    fsize = struct.unpack_from("<I", head, 0x0C)[0]
    records = [head[0x20 + 16 * p:0x30 + 16 * p] for p in range(128)]
    table = 0x820 + ps * 0x200
    sizes = [struct.unpack_from("<H", head, table + 2 * i)[0] * 8 for i in range(256)]
    starts, pos = {}, 0
    for g in range(1, vs + 1):
        starts[g] = pos
        pos += sizes[g]
    assert pos == len(body) and len(head) == table + 0x200, "VAB shape"
    used, unused = {}, {}
    for k in range(ps):
        block = head[0x820 + k * 0x200:0x820 + (k + 1) * 0x200]
        n = records[k][0]
        used[k] = []
        for t in range(n):
            slot = block[t * 0x20:(t + 1) * 0x20]
            vag = struct.unpack_from("<h", slot, 0x16)[0]
            used[k].append((slot[:0x16] + slot[0x18:], body[starts[vag]:starts[vag] + sizes[vag]]))
        unused[k] = block[n * 0x20:]
    return ps, ts, vs, fsize, records, used, unused


def _rows(image):
    out = []
    for row, *_rest in music.VANILLA_ROWS:
        raw = bytes(image[disc.addr_to_disc(music.LBA_TABLE + 12 * row + i, disc.REGION_EXE)]
                    for i in range(12))
        out.append((row,) + struct.unpack("<III", raw))
    return out


def _dir(image):
    data = _user(image, music.SOUND_DIR_LBA, music.SOUND_DIR_SECTORS)
    out, i = {}, 0
    while i < len(data):
        n = data[i]
        if n == 0:
            i = (i // SEC + 1) * SEC
            continue
        name = data[i + 33:i + 33 + data[i + 32]]
        if name not in (b"\x00", b"\x01"):
            le, be = struct.unpack_from("<I", data, i + 2)[0], struct.unpack_from(">I", data, i + 6)[0]
            sle, sbe = struct.unpack_from("<I", data, i + 10)[0], struct.unpack_from(">I", data, i + 14)[0]
            out[name.split(b";")[0].decode()] = (le, be, sle, sbe)
        i += n
    return out


def _dir_name(row):
    return "PCOMMON.PAC" if row == 0x5D else f"PBGM{row - music.FIRST_ROW:02X}.PAC"


# ---- The deal (no disc) -----------------------------------------------------------
class TestTheDeal(unittest.TestCase):
    def test_places_and_music_are_consistent(self):
        self.assertEqual(len(music.PLACES), 14)
        self.assertEqual(len(music.SOURCES), 13)
        self.assertEqual(sorted(ALL_BANKS), sorted(music.BANK_SIZES))
        self.assertEqual(len(ALL_BANKS), len(set(ALL_BANKS)), "a bank in two places")
        carried = sorted(b for banks in music.SOURCES.values() for b in banks)
        self.assertEqual(carried, sorted(ALL_BANKS), "every bank carries exactly one music")
        for place, banks in music.PLACES:
            self.assertTrue(set(banks) <= set(music.SOURCES[music.VANILLA_MUSIC[place]]), place)
        self.assertEqual(PLACE_BANKS["Sword Man"], (0x11, 0x12))
        self.assertEqual(music.VANILLA_MUSIC["Duo"], music.VANILLA_MUSIC["Intro Stage"])
        self.assertTrue(set(music.VANILLA_MUSIC.values()) == set(music.SOURCES))

    def test_the_identity_fits_trivially(self):
        for place, banks in music.PLACES:
            for bank in banks:
                src = music.music_bank(bank, music.VANILLA_MUSIC[place])
                self.assertEqual(src, bank, "a place's own music is taken from itself")
                self.assertEqual(music.rebuilt_size(bank, bank)[0], music.BANK_SIZES[bank][0])
        self.assertTrue(music.fits(music.VANILLA_MUSIC))

    def test_x5s_rules_over_1000_seeds(self):
        cap = -(-len(music.PLACES) // len(music.SOURCES))        # 2
        nones = 0
        for seed in range(1000):
            a = music.music_assignment(random.Random(seed))
            if a is None:
                nones += 1
                continue
            self.assertEqual(set(a), set(PLACE_BANKS), seed)
            counts = collections.Counter(a.values())
            self.assertEqual(set(counts), set(music.SOURCES), f"seed {seed}: a music is lost")
            self.assertLessEqual(max(counts.values()), cap, seed)
            for place in a:
                self.assertNotEqual(a[place], music.VANILLA_MUSIC[place], f"seed {seed}: {place}")
            # the bounds, recomputed here rather than trusted
            new = old = 0
            for place, banks in music.PLACES:
                for bank in banks:
                    size, body = music.rebuilt_size(bank, music.music_bank(bank, a[place]))
                    self.assertLessEqual(body, music.VAB_BODY_BOUND, (seed, place))
                    new += size
                    old += music.BANK_SIZES[bank][0]
            self.assertLessEqual(new, old, f"seed {seed}: the region grows")
        self.assertEqual(nones, 0, "a deal that should practically never fail did")

    def test_the_same_seed_gives_the_same_music(self):
        self.assertEqual(music.music_assignment(random.Random(7)),
                         music.music_assignment(random.Random(7)))

    def test_impossible_bounds_give_none_not_the_last_deal(self):
        self.assertIsNone(music.music_assignment(random.Random(3), body_bound=0x1000))

    def test_clowns_music_never_lands_where_it_cannot_fit(self):
        over = {p for p, banks in music.PLACES
                if any(music.rebuilt_size(b, music.music_bank(b, "Clown Man"))[1] > music.VAB_BODY_BOUND
                       for b in banks)}
        self.assertEqual(over, {"Intro Stage", "Frost Man", "Tengu Man", "Sword Man", "Aqua Man"})
        for seed in range(300):
            a = music.music_assignment(random.Random(seed))
            for place in over:
                self.assertNotEqual(a[place], "Clown Man", seed)


# ---- Against the real disc ---------------------------------------------------------
@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestAgainstTheDump(unittest.TestCase):
    track1: bytes

    @classmethod
    def setUpClass(cls):
        with open(TRACK1, "rb") as f:
            cls.track1 = f.read()
        cls.files = {row: _user(cls.track1, lba, size // SEC)
                     for row, lba, size, _first in music.VANILLA_ROWS}

    def bank(self, bank):
        return self.files[music.FIRST_ROW + bank]

    # -- the baked constants are this disc --
    def test_the_baked_rows_and_hashes_are_the_disc(self):
        self.assertEqual([tuple(r) for r in _rows(self.track1)], list(music.VANILLA_ROWS))
        music._verify_vanilla(self.track1)
        d = _dir(self.track1)
        for row, lba, size, _first in music.VANILLA_ROWS:
            self.assertEqual(d[_dir_name(row)], (lba, lba, size, size))

    def test_the_places_are_what_the_stage_tables_name(self):
        for place, banks in music.PLACES:
            stage = music.STAGE_OF_PLACE[place]
            named = {self.track1[disc.addr_to_disc(t + stage, disc.REGION_EXE)]
                     for t in music.STAGE_MUSIC_TABLES}
            self.assertEqual(named, set(banks), place)

    def test_the_baked_sizes_are_the_disc(self):
        for bank, (fsize, t5, head, seq, _m, _x) in music.BANK_SIZES.items():
            order, ch = _chunks(self.bank(bank))
            self.assertEqual(order, [5, 4, 0x201, 1])
            self.assertEqual((len(self.bank(bank)), len(ch[5]), len(ch[4]), len(ch[1])),
                             (fsize, t5, head, seq), hex(bank))
            self.assertEqual(_m + _x, len(ch[0x201]), hex(bank))

    def test_shared_music_really_is_shared(self):
        # The two carriers of a music hold the same SEQ (Intro/Duo are
        # identical in the whole music half; Sword's halves differ only in
        # per-bank constants, which is why a bank uses its own copy).
        for name, carriers in music.SOURCES.items():
            seqs = {_chunks(self.bank(b))[1][1] for b in carriers}
            self.assertEqual(len(seqs), 1, name)

    # -- the rebuild --
    def test_every_bank_rebuilds_to_itself(self):
        for bank in ALL_BANKS:
            self.assertEqual(music.rebuild_bank(self.bank(bank), self.bank(bank)), self.bank(bank), hex(bank))

    def test_the_baked_sizes_predict_every_rebuild(self):
        for place, banks in music.PLACES:
            for bank in banks:
                for name in music.SOURCES:
                    src = music.music_bank(bank, name)
                    data = music.rebuild_bank(self.bank(bank), self.bank(src))
                    body = _chunks(data)[1][0x201]
                    self.assertEqual(music.rebuilt_size(bank, src), (len(data), len(body)),
                                     (place, name))

    # -- the hard control --
    def test_identity_leaves_track1_byte_identical(self):
        image = bytearray(self.track1)
        touched = music.apply_music(image, dict(music.VANILLA_MUSIC), _force=True)
        self.assertGreater(len(touched), music.REGION_SECTORS)      # everything re-written...
        self.assertTrue(image == self.track1, "the identity rebuild changed Track 1")  # ...to the same bytes
        del image
        image = bytearray(self.track1)
        self.assertEqual(music.apply_music(image, dict(music.VANILLA_MUSIC)), set())
        self.assertTrue(image == self.track1)

    def test_nothing_happens_without_an_assignment(self):
        image = bytearray(self.track1[:0])      # never touched: None short-circuits
        self.assertEqual(music.apply_music(image, None), set())

    def test_refuses_a_disc_that_is_not_vanilla_where_it_writes(self):
        image = bytearray(self.track1)
        a = music.music_assignment(random.Random(1))
        for where in (music.REGION_FIRST * RAW + 1000,
                      disc.addr_to_disc(music.LBA_TABLE + 12 * 0x20, disc.REGION_EXE),
                      music.SOUND_DIR_LBA * RAW + UOFF + 40):
            image[where] ^= 0xFF
            with self.assertRaises(ValueError):
                music.apply_music(image, a)
            image[where] ^= 0xFF
        self.assertTrue(image == self.track1, "a refusal wrote something")

    def test_an_over_bound_assignment_is_refused_before_writing(self):
        a = dict(music.VANILLA_MUSIC)
        a["Aqua Man"] = "Clown Man"                   # body 0x2EFB0 > 0x292A0
        image = bytearray(self.track1)
        with self.assertRaises(ValueError):
            music.apply_music(image, a)
        self.assertTrue(image == self.track1)

    # -- seeded deals, checked from the outside --
    def test_seeded_deals(self):
        for seed in (1, 2, 3):
            a = music.music_assignment(random.Random(seed))
            image = bytearray(self.track1)
            touched = music.apply_music(image, a)
            with self.subTest(seed=seed):
                self.check_deal(image, a, touched, full_parity=(seed == 1))
            del image

    def check_deal(self, image, a, touched, full_parity):
        V = self.track1
        rows = _rows(image)
        # 1. the table: contiguous from the region start, first words kept, region not grown
        expect = music.REGION_FIRST
        for (row, lba, size, first), (_r, _l, _s, vfirst) in zip(rows, music.VANILLA_ROWS):
            self.assertEqual(lba, expect, hex(row))
            self.assertEqual(size % SEC, 0)
            self.assertEqual(first, vfirst)
            expect += size // SEC
        self.assertLessEqual(expect, REGION_END)
        # 2. the ISO directory agrees with the table
        d = _dir(image)
        for row, lba, size, _first in rows:
            self.assertEqual(d[_dir_name(row)], (lba, lba, size, size), hex(row))
        # 3. each file is what should be there
        where = {row: (lba, size) for row, lba, size, _f in rows}
        stage_rows = {music.FIRST_ROW + b for b in ALL_BANKS}
        for row, (lba, size) in where.items():
            data = _user(image, lba, size // SEC)
            if row not in stage_rows:
                self.assertEqual(data, self.files[row], f"row {row:#x} moved but changed")
        for place, banks in music.PLACES:
            for bank in banks:
                src = music.music_bank(bank, a[place])
                lba, size = where[music.FIRST_ROW + bank]
                self.check_bank(_user(image, lba, size // SEC), bank, src, place)
        # 4. subheaders: 0x08, 0x89 on the last sector of each file, zero in the free tail
        last = {lba + size // SEC - 1 for _r, lba, size, _f in rows}
        for s in range(music.REGION_FIRST, REGION_END):
            sh = bytes(image[s * RAW + 16:s * RAW + 24])
            if s >= expect:
                self.assertEqual(sh, bytes(8))
                self.assertEqual(bytes(image[s * RAW + UOFF:s * RAW + UOFF + SEC]), bytes(SEC))
            else:
                self.assertEqual(sh, music.SUBHEADER_LAST if s in last else music.SUBHEADER_DATA, s)
        # 5. nothing outside the region, its directory and the LBA table's sector moved
        exe_sector = disc.addr_to_disc(music.LBA_TABLE + 12 * music.FIRST_ROW, disc.REGION_EXE) // RAW
        self.assertEqual(exe_sector,
                         disc.addr_to_disc(music.LBA_TABLE + 12 * 0x5D + 11, disc.REGION_EXE) // RAW)
        for lo, hi in ((0, exe_sector), (exe_sector + 1, music.SOUND_DIR_LBA),
                       (REGION_END, disc.TRACK_SECTORS[0])):
            self.assertTrue(image[lo * RAW:hi * RAW] == V[lo * RAW:hi * RAW], (lo, hi))
        changed = {s for s in [exe_sector] + list(range(music.SOUND_DIR_LBA, REGION_END))
                   if image[s * RAW:(s + 1) * RAW] != V[s * RAW:(s + 1) * RAW]}
        self.assertEqual(touched, changed)
        # 6. every touched sector's EDC/ECC is valid
        check = sorted(touched) if full_parity else sorted(touched)[::97]
        for s in check:
            sector = bytearray(image[s * RAW:(s + 1) * RAW])
            disc.regenerate_sector(sector, 0)
            self.assertEqual(bytes(sector), bytes(image[s * RAW:(s + 1) * RAW]), s)

    def check_bank(self, new, bank, src, place):
        order, n = _chunks(new)
        _o, p = _chunks(self.bank(bank))
        _o, s = _chunks(self.bank(src))
        self.assertEqual(order, [5, 4, 0x201, 1], place)
        self.assertEqual(n[5], p[5], f"{place}: the effect table is not the place's own")
        for k in range(len(n[5]) // 4):
            tag = n[5][4 * k] & 0x7F
            if tag:
                self.assertEqual(tag, bank + 1, f"{place}: entry {k:#x} tagged for another song")
        self.assertEqual(n[1], s[1], f"{place}: the SEQ is not the source's")
        self.assertLessEqual(len(n[0x201]), music.VAB_BODY_BOUND, place)
        nps, nts, nvs, nfs, nrec, nused, nunused = _vab(n[4], n[0x201])
        pps, _pts, _pvs, _pfs, prec, pused, punused = _vab(p[4], p[0x201])
        _sps, _sts, _svs, _sfs, srec, sused, sunused = _vab(s[4], s[0x201])
        self.assertEqual(nps, pps)
        self.assertEqual(nts, sum(r[0] for r in nrec))
        self.assertEqual(nfs, len(n[4]) + len(n[0x201]))
        self.assertEqual(n[4][:0x0C], p[4][:0x0C])
        self.assertEqual(n[4][0x10:0x12] + n[4][0x18:0x20], p[4][0x10:0x12] + p[4][0x18:0x20])
        for prog in range(128):
            want = srec[prog] if prog < 16 else prec[prog]
            self.assertEqual(nrec[prog], want, f"{place}: program {prog} record")
        for prog in range(nps):
            used, unused = (sused, sunused) if prog < 16 else (pused, punused)
            self.assertEqual(nused[prog], used[prog], f"{place}: program {prog} tones or samples")
            self.assertEqual(nunused[prog], unused[prog], f"{place}: program {prog} spare slots")
        # the body is the source's music half plus the place's effect half,
        # dead samples included - nothing dropped, nothing extra (the sizes
        # were checked against the disc in test_the_baked_sizes_are_the_disc)
        self.assertEqual(len(n[0x201]), music.BANK_SIZES[src][4] + music.BANK_SIZES[bank][5], place)


if __name__ == "__main__":
    unittest.main()
