"""Disc geometry and the three-track layout.

The geometry tests run anywhere. The rest need the vanilla dump, which is never
committed, so they skip cleanly when it is absent - a silent pass would be
worse than a skip, because the disc is the one thing source cannot check.
"""
import hashlib
import os
import unittest

from .. import disc

DUMP = r"C:\Users\Ivor\Documents\Game Modding\Games\Mega Man 8 (USA)"
TRACK1 = os.path.join(DUMP, "Mega Man 8 (USA) (Track 1).bin")
have_dump = os.path.exists(TRACK1)


def word(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 4], "little")


class TestGeometry(unittest.TestCase):
    def test_exe_maps_past_its_0x800_header(self):
        # The first byte of text is the first byte after the 0x800 header:
        # sector 24 (EXE LBA 23 + 1), user data offset 0.
        self.assertEqual(disc.addr_to_disc(0x800C0000, disc.REGION_EXE),
                         24 * disc.SECTOR_RAW + disc.USER_OFF)

    def test_out_of_range_is_refused(self):
        with self.assertRaises(ValueError):
            disc.addr_to_disc(0x800BFFFC, disc.REGION_EXE)
        with self.assertRaises(ValueError):
            disc.addr_to_disc(0x801D7FFC, "ovl:STAGE03")
        with self.assertRaises(ValueError):
            disc.addr_to_disc(disc.PACKS["LABO.PAC"][1], "pack:LABO.PAC")
        with self.assertRaises(ValueError):
            disc.addr_to_disc(0x801E0000, "ovl:STAGE99")

    def test_tracks_are_whole_sectors(self):
        for size in disc.TRACK_SIZES:
            self.assertEqual(size % disc.SECTOR_RAW, 0)
        self.assertEqual(disc.TRACK_SECTORS, (142096, 19996, 15900))

    def test_merged_cue_lands_audio_on_the_games_own_lbas(self):
        """The game plays Track 2 through END1.DA and Track 3 through
        ZNULL.DAT, by LBA. The merged cue must put each track's INDEX 01
        exactly there, or the music plays from the wrong place."""
        _s1, s2, s3 = disc.track_starts()
        self.assertEqual(s2 + disc.PREGAP_FRAMES, disc.END1_DA_LBA)
        self.assertEqual(s3 + disc.PREGAP_FRAMES, disc.ZNULL_DAT_LBA)
        cue = disc.merged_cue("x.bin")
        self.assertIn(f"INDEX 01 {disc.msf(disc.END1_DA_LBA)}", cue)
        self.assertIn(f"INDEX 01 {disc.msf(disc.ZNULL_DAT_LBA)}", cue)

    def test_msf(self):
        self.assertEqual(disc.msf(0), "00:00:00")
        self.assertEqual(disc.msf(150), "00:02:00")
        self.assertEqual(disc.msf(75 * 60 + 1), "01:00:01")

    def test_split_needs_the_exact_size(self):
        with self.assertRaises(ValueError):
            disc.split_merged(b"\0" * 100)


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestAgainstTheDump(unittest.TestCase):
    track1: bytes

    @classmethod
    def setUpClass(cls):
        with open(TRACK1, "rb") as f:
            cls.track1 = f.read()

    def test_track1_is_the_redump(self):
        self.assertEqual(hashlib.md5(self.track1).hexdigest(), disc.TRACK_MD5[0])

    def test_known_code_lands_where_the_map_says(self):
        """Three words the research read off the disc, each through a
        different region, so a wrong mapping in any one of them fails."""
        # EXE: the stage-clear weapon grant, `sb v1, 0x1EAC(at)`.
        off = disc.addr_to_disc(0x801012C4, disc.REGION_EXE)
        self.assertEqual(word(self.track1, off) >> 16, 0xA023)
        # Overlay: Tengu Man's bolt 14 spawn, `ori v0, zero, 37`.
        off = disc.addr_to_disc(0x801E0E38, "ovl:STAGE03")
        self.assertEqual(word(self.track1, off), 0x34020025)
        # Pack: the Lab's first line of dialogue.
        off = disc.addr_to_disc(0xF034, "pack:LABO.PAC")
        self.assertEqual(self.track1[off:off + 7], b"Welcome")

    def test_regeneration_is_identity_on_untouched_sectors(self):
        """The control: regenerating parity on sectors nobody edited must
        reproduce them byte for byte, or the ECC code is wrong and every
        patch would quietly corrupt what it touches."""
        image = bytearray(self.track1)
        for sector in (24, 25, 26, 126218, 132364 + 30):
            before = bytes(image[sector * disc.SECTOR_RAW:(sector + 1) * disc.SECTOR_RAW])
            disc.regenerate_sector(image, sector)
            after = bytes(image[sector * disc.SECTOR_RAW:(sector + 1) * disc.SECTOR_RAW])
            self.assertEqual(before, after, sector)

    def test_an_edit_is_applied_with_parity_and_refused_on_wrong_bytes(self):
        where = 0x801012C4
        off = disc.addr_to_disc(where, disc.REGION_EXE)
        vanilla = self.track1[off:off + 4]
        patched = disc.apply_edits(self.track1, [("probe", where, disc.REGION_EXE,
                                                  vanilla, b"\0\0\0\0")])
        self.assertEqual(patched[off:off + 4], b"\0\0\0\0")
        # Parity was regenerated: regenerating again changes nothing.
        sector = off // disc.SECTOR_RAW
        again = bytearray(patched)
        disc.regenerate_sector(again, sector)
        self.assertEqual(bytes(again), patched)
        with self.assertRaises(ValueError):
            disc.apply_edits(self.track1, [("wrong", where, disc.REGION_EXE,
                                            b"\1\2\3\4", b"\0\0\0\0")])

    def test_shop_table_matches_the_worlds_prices_and_stock(self):
        """The EXE's shop table (0x801505F0): {part index, price} in shop
        order, a blank at record 5, the start stock before record 10 and the
        post-Duo stock after. The world's price and stock lists came from a
        guide; this holds them to the disc."""
        from .. import names
        off = disc.addr_to_disc(0x801505F0, disc.REGION_EXE)
        records = [(self.track1[off + 2 * i], self.track1[off + 2 * i + 1])
                   for i in range(18)]
        self.assertEqual(records[5], (0xFF, 0xFF))
        by_part = {names.PARTS[p]: price for p, price in records if p != 0xFF}
        self.assertEqual(by_part, names.PART_COST)
        start = {names.PARTS[p] for p, _ in records[:10] if p != 0xFF}
        self.assertEqual(start, set(names.START_STOCK))
        self.assertEqual({names.PARTS[p] for p, _ in records[10:]},
                         set(names.POST_DUO_STOCK))

    def test_base_edits_reprice_the_lab_and_touch_nothing_else(self):
        """After the base patch the shop table holds LAB_PRICE with its part
        column and blank record unchanged, and no user-data byte changed
        except the ones an edit declares."""
        patched = disc.apply_edits(self.track1, disc.BASE_EDITS)
        off = disc.addr_to_disc(disc.SHOP_TABLE, disc.REGION_EXE)
        for record, part in enumerate(disc.SHOP_RECORDS):
            got_part, got_price = patched[off + 2 * record], patched[off + 2 * record + 1]
            if part is None:
                self.assertEqual((got_part, got_price), (0xFF, 0xFF))
                continue
            self.assertEqual(got_part, part - 1, record)
            self.assertEqual(got_price, disc.LAB_PRICE[part], record)
        # P5/P6: each in-place rewrite landed where it names.
        from .. import mips
        for name, where, source, _vanilla in disc.IN_PLACE:
            for i, w in enumerate(mips.assemble(source, where)):
                self.assertEqual(word(patched, disc.addr_to_disc(where + 4 * i, disc.REGION_EXE)), w, name)

        declared = {disc.addr_to_disc(where + i, region)
                    for _l, where, region, vanilla, payload in disc.BASE_EDITS
                    for i in range(len(payload)) if vanilla[i] != payload[i]}
        for s in {o // disc.SECTOR_RAW for o in declared}:
            for i in range(disc.USER_OFF, disc.USER_OFF + disc.USER_LEN):
                o = s * disc.SECTOR_RAW + i
                if self.track1[o] != patched[o]:
                    self.assertIn(o, declared, f"undeclared change at 0x{o:X}")
        changed = {o // disc.SECTOR_RAW for o in declared}
        for s in range(disc.TRACK_SECTORS[0]):
            if s in changed:
                continue
            a = self.track1[s * disc.SECTOR_RAW:(s + 1) * disc.SECTOR_RAW]
            b = patched[s * disc.SECTOR_RAW:(s + 1) * disc.SECTOR_RAW]
            self.assertEqual(a, b, f"sector {s} changed but no edit touches it")

    def _patched(self) -> bytes:
        if not hasattr(type(self), "_base"):
            type(self)._base = disc.apply_edits(self.track1, disc.BASE_EDITS)
        return type(self)._base

    def _word(self, image: bytes, where: int, region: str = disc.REGION_EXE) -> int:
        return word(image, disc.addr_to_disc(where, region))

    def test_a1_moves_only_the_capability_readers(self):
        """P1: every capability reader now reads +1; the kill-record readers
        still read +0 - the grant and its guard, the phase gates, stage
        select, Exit, the save pack. Those untouched words are the control:
        moving one of them would sever progression from the kill record."""
        patched = self._patched()
        for what, where, region, vanilla in disc.A1_CAPABILITY_READERS:
            got = self._word(patched, where, region)
            self.assertEqual(got, vanilla + 1, what)
            self.assertEqual(got >> 26, 0x24, f"{what}: still an lbu")
        for where in (0x801012C4, 0x80101288, 0x801012DC, 0x80101378,   # grant, guard, gates
                      0x800FFD5C, 0x801135B8, 0x80120EB8):               # select, Exit, save
            self.assertEqual(self._word(patched, where), self._word(self.track1, where), hex(where))
        # The spawn refill keys on +1 and no longer clears it.
        self.assertEqual(self._word(patched, 0x8010BE70), 0)
        self.assertEqual(self._word(patched, 0x8010BE74), 0x90820001)

    def test_a1_never_leaves_the_weapon_switch_without_a_usable_slot(self):
        """The weapon switch spins forever with no usable slot. The buster
        is usable from power-on, and every attract demo's loadout - owned
        weapons with +1 = 0 on the vanilla disc - is usable too."""
        patched = self._patched()
        self.assertEqual(patched[disc.addr_to_disc(disc.WEAPONS + 1, disc.REGION_EXE)], 1)
        self.assertEqual(self.track1[disc.addr_to_disc(disc.WEAPONS + 1, disc.REGION_EXE)], 0)
        for pack, loadout in disc.DEMO_LOADOUTS.items():
            for slot in range(10):
                entry = loadout + 4 * slot
                owned = self.track1[disc.addr_to_disc(entry, f"pack:{pack}")]
                self.assertEqual(owned, 1, f"{pack} slot {slot}: not a loadout entry")
                self.assertEqual(patched[disc.addr_to_disc(entry + 1, f"pack:{pack}")], 1)

    def test_the_intro_mega_ball_no_longer_selects_itself(self):
        """Seen live: the pickup's `sb v1, CURWEAPON` handed over a usable
        Mega Ball. Now it selects the buster; the kill-record store beside it
        (+0 of slot 1, the Mega Ball location) is untouched."""
        patched = self._patched()
        self.assertEqual(self._word(self.track1, 0x801E1728, "ovl:STAGE00"), 0xA023DC08)
        self.assertEqual(self._word(patched, 0x801E1728, "ovl:STAGE00"), 0xA020DC08)
        self.assertEqual(self._word(patched, 0x801E1770, "ovl:STAGE00"),
                         self._word(self.track1, 0x801E1770, "ovl:STAGE00"))

    def test_rush_pickups_record_into_the_ap_block(self):
        """P2: the pickup's pointer table and all five stage reads now name
        the AP block's Rush bytes, and the grant store itself is untouched
        (it now writes the check record)."""
        patched = self._patched()
        for k in range(4):
            self.assertEqual(self._word(patched, disc.RUSH_TABLE + 4 * k), disc.AP_RUSH + k)
        for what, where, overlay, reg, k in disc.RUSH_STAGE_READS:
            lui = self._word(patched, where - 4, f"ovl:{overlay}")
            lbu = self._word(patched, where, f"ovl:{overlay}")
            self.assertEqual((lui >> 26, (lui >> 16) & 31), (0x0F, reg), what)
            self.assertEqual((lbu >> 26, (lbu >> 21) & 31, (lbu >> 16) & 31), (0x24, reg, reg), what)
            lo = lbu & 0xFFFF
            target = ((lui & 0xFFFF) << 16) + (lo - 0x10000 if lo & 0x8000 else lo)
            self.assertEqual(target, disc.AP_RUSH + k, what)
        self.assertEqual(self._word(patched, 0x80129B08), 0xA0430000)   # sb v1, 0(v0)

    def test_bolt_pickup_keeps_its_bit_and_drops_its_increment(self):
        patched = self._patched()
        self.assertEqual(self._word(patched, 0x80129788), 0x24420000)
        self.assertEqual(self._word(patched, 0x801297B4), self._word(self.track1, 0x801297B4))

    def test_ap_block_is_free_and_takes_the_header(self):
        """The block is zero on the vanilla disc, and the seed's header lands
        there; a zero stamp is refused (the save extension uses 0 as 'no
        stamp')."""
        start = disc.addr_to_disc(disc.AP_BLOCK, disc.REGION_EXE)
        self.assertEqual(self.track1[start:start + disc.AP_BLOCK_SIZE], bytes(disc.AP_BLOCK_SIZE))
        # pickupsanity's key table follows the block's 0x40 bytes: free too.
        keys = [disc.addr_to_disc(disc.PICKUP_KEYS + i, disc.REGION_EXE)
                for i in range(disc.PICKUP_KEYS_ROOM)]
        self.assertEqual(bytes(self.track1[a] for a in keys), bytes(disc.PICKUP_KEYS_ROOM))
        image = disc.apply_edits(self.track1, disc.ap_block_edits(0x12345678))
        self.assertEqual(image[start:start + 12], b"APM8" + (1).to_bytes(4, "little")
                         + (0x12345678).to_bytes(4, "little"))
        with self.assertRaises(ValueError):
            disc.ap_block_edits(0)
        self.assertNotEqual(disc.seed_stamp("any", 1), 0)
        self.assertNotEqual(disc.seed_stamp("any", 1), disc.seed_stamp("any", 2))

    def test_routines_go_over_the_dead_debug_menu_and_hook_in(self):
        """The routines replace only the dead debug menu, and each hook's
        vanilla words are what the card code has there."""
        from .. import mips
        edits = disc.routine_edits(self.track1)
        patched = disc.apply_edits(self.track1, edits)
        at = disc.routine_addresses()
        for name, source in disc.ROUTINES:
            words = mips.assemble(source, at[name])
            for i, w in enumerate(words):
                self.assertEqual(self._word(patched, at[name] + 4 * i), w, name)
        write, load = at["P11 save extension: write"], at["P11 save extension: load"]
        self.assertEqual(self._word(patched, 0x8011FC40), mips.word(f"jal {write:#x}", 0x8011FC40))
        self.assertEqual(self._word(patched, 0x8011FC44), 0x3C128016)       # delay slot untouched
        self.assertEqual(self._word(patched, 0x8011F850), mips.word(f"jal {load:#x}", 0x8011F850))
        self.assertEqual(self._word(patched, 0x8011F854), 0x34020001)
        # The cave is the debug menu: its entry is where the first routine starts.
        self.assertEqual(self._word(self.track1, disc.CAVE_START), 0x27BDFFE8)   # addiu sp, sp, -0x18
        # And the full set applies together without two edits sharing a byte.
        disc.apply_edits(self.track1, list(disc.BASE_EDITS) + edits + disc.ap_block_edits(1))

    def test_audio_tracks_are_found_beside_track1(self):
        t2, t3 = disc.find_audio_tracks(TRACK1)
        self.assertTrue(t2.endswith("(Track 2).bin"))
        self.assertTrue(t3.endswith("(Track 3).bin"))
