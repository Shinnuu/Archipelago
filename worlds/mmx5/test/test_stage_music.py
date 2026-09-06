"""Stage music shuffle tests.

The feature is one table: the cue table at 0x800707CC maps a stage id to the
BGM id that stage asks for, and shuffling stage music means rewriting the id
byte of the rows that are stages. The stream table - where a BGM id actually
lives on the disc - is deliberately NOT touched, which is what keeps the hub,
cutscenes and jingles on vanilla music without an exclusion list.

Music is assigned per PLACE, not per track. A row's four (id, volume) pairs
are indexed d*2 + c from two selector bytes, so one row can hold more than one
place - the intro's 02/03/02/03 is a two-part theme picked by c. Assigning per
place is what lets Zero Space 1, Zero Space 2 and the duel differ, where
vanilla had all six Zero Space rows on one track.

There are more places (17) than tracks (13), so unlike a permutation some
track must repeat. What is protected here:

  * every track still reaches somewhere, and none is used more than twice;
  * slots that share a ROW stay distinct, or splitting the intro into two
    parts would be quietly undone by an unlucky roll;
  * volumes survive, because the game mixes stages at four different levels;
  * every (row, pair) belongs to exactly one slot, and each slot is a single
    track in vanilla - if that stops holding, the slot table has drifted from
    the disc;
  * rows that are NOT stages stay out entirely. The sharp one is 0x0B: it is
    the Enigma/shuttle launch CUTSCENE, and it looks exactly like a stage row.
"""
import collections
import random
import unittest

from .. import disc


def _ids(row: bytes) -> tuple[int, ...]:
    return tuple(row[i * 2] for i in range(4))


def _vols(row: bytes) -> tuple[int, ...]:
    return tuple(row[i * 2 + 1] for i in range(4))


def _patched_rows(assignment: dict[str, int]) -> dict[int, bytes]:
    out = dict(disc.MUSIC_STAGE_ROWS)
    for addr, payload, _region in disc.music_edits(assignment):
        out[(addr - disc.MUSIC_CUE_TABLE) // 8] = payload
    return out


class TestTheSlotTable(unittest.TestCase):
    def test_every_row_pair_belongs_to_exactly_one_slot(self) -> None:
        seen = collections.Counter()
        for _name, positions in disc.MUSIC_SLOTS:
            for row, pairs in positions:
                for pair in pairs:
                    seen[(row, pair)] += 1
        expected = {(row, pair) for row in disc.MUSIC_STAGE_ROWS
                    for pair in range(4)}
        self.assertEqual(set(seen), expected)
        self.assertEqual(set(seen.values()), {1})

    def test_each_slot_is_one_track_in_vanilla(self) -> None:
        # A slot that spanned two vanilla tracks would mean the slot table has
        # drifted from the disc - it would be claiming two places are one.
        for name, positions in disc.MUSIC_SLOTS:
            tracks = {disc.MUSIC_STAGE_ROWS[row][pair * 2]
                      for row, pairs in positions for pair in pairs}
            self.assertEqual(len(tracks), 1, f"{name}: {tracks}")

    def test_the_pool_is_exactly_the_tracks_the_stage_rows_use(self) -> None:
        used = {i for row in disc.MUSIC_STAGE_ROWS.values() for i in _ids(row)}
        self.assertEqual(used, set(disc.MUSIC_STAGE_TRACKS))

    def test_the_intro_is_two_slots_because_vanilla_gives_it_two_tracks(self) -> None:
        self.assertEqual(len(set(_ids(disc.MUSIC_STAGE_ROWS[0x00]))), 2)
        names = [n for n, _p in disc.MUSIC_SLOTS if n.startswith("Intro")]
        self.assertEqual(len(names), 2)


class TestTheAssignment(unittest.TestCase):
    def test_it_covers_exactly_the_slots(self) -> None:
        a = disc.music_assignment(random.Random(0))
        self.assertEqual(set(a), {n for n, _p in disc.MUSIC_SLOTS})

    def test_every_track_still_reaches_somewhere(self) -> None:
        for seed in range(200):
            a = disc.music_assignment(random.Random(seed))
            self.assertEqual(set(a.values()), set(disc.MUSIC_STAGE_TRACKS),
                             f"seed {seed}")

    def test_no_track_is_used_more_than_it_has_to_be(self) -> None:
        # ceil(slots / pool): with 17 places and 13 tracks that is 2.
        cap = -(-len(disc.MUSIC_SLOTS) // len(disc.MUSIC_STAGE_TRACKS))
        for seed in range(200):
            counts = collections.Counter(
                disc.music_assignment(random.Random(seed)).values())
            self.assertLessEqual(max(counts.values()), cap, f"seed {seed}")

    def test_slots_sharing_a_row_get_different_tracks(self) -> None:
        for seed in range(200):
            a = disc.music_assignment(random.Random(seed))
            self.assertFalse(disc._shares_a_row_track(a), f"seed {seed}")

    def test_no_place_keeps_the_track_it_already_had(self) -> None:
        # Cosmetic option: a stage still playing its own theme is
        # indistinguishable from the option not working.
        vanilla = disc.slot_vanilla_tracks()
        for seed in range(200):
            a = disc.music_assignment(random.Random(seed))
            for name, was in vanilla.items():
                self.assertNotEqual(a[name], was, f"seed {seed}: {name}")

    def test_slot_vanilla_tracks_matches_the_row_table(self) -> None:
        for name, positions in disc.MUSIC_SLOTS:
            for row, pairs in positions:
                for pair in pairs:
                    self.assertEqual(disc.MUSIC_STAGE_ROWS[row][pair * 2],
                                     disc.slot_vanilla_tracks()[name], name)

    def test_the_same_seed_gives_the_same_music(self) -> None:
        self.assertEqual(disc.music_assignment(random.Random(99)),
                         disc.music_assignment(random.Random(99)))

    def test_different_seeds_give_different_music(self) -> None:
        self.assertNotEqual(disc.music_assignment(random.Random(1)),
                            disc.music_assignment(random.Random(2)))


class TestTheEdits(unittest.TestCase):
    def setUp(self) -> None:
        self.assignment = disc.music_assignment(random.Random(1234))
        self.edits = disc.music_edits(self.assignment)

    def test_every_edit_names_the_exe_region(self) -> None:
        for addr, _payload, region in self.edits:
            self.assertEqual(region, disc.MUSIC_REGION, hex(addr))

    def test_volumes_are_never_touched(self) -> None:
        for addr, payload, _region in self.edits:
            row = (addr - disc.MUSIC_CUE_TABLE) // 8
            self.assertEqual(_vols(payload),
                             _vols(disc.MUSIC_STAGE_ROWS[row]), hex(addr))

    def test_every_written_id_is_a_stage_track(self) -> None:
        for addr, payload, _region in self.edits:
            for track in _ids(payload):
                self.assertIn(track, disc.MUSIC_STAGE_TRACKS, hex(addr))

    def test_edits_land_only_on_stage_rows(self) -> None:
        for addr, _payload, _region in self.edits:
            offset = addr - disc.MUSIC_CUE_TABLE
            self.assertEqual(offset % 8, 0, hex(addr))
            self.assertIn(offset // 8, disc.MUSIC_STAGE_ROWS, hex(addr))

    def test_no_two_edits_overlap(self) -> None:
        seen: set[int] = set()
        for addr, payload, _region in self.edits:
            for i in range(len(payload)):
                self.assertNotIn(addr + i, seen, hex(addr))
                seen.add(addr + i)

    def test_every_edit_maps_to_a_real_disc_offset(self) -> None:
        # The cue table straddles a sector boundary, so this is not a
        # formality - it is the arithmetic a flat byte offset would get wrong.
        for addr, payload, region in self.edits:
            for i in range(len(payload)):
                self.assertIsInstance(disc.addr_to_disc(addr + i, region), int)

    def test_the_edit_sites_do_not_depend_on_the_roll(self) -> None:
        # The unpatcher's manifest is built by running patch_rom once at a
        # fixed seed and recording the sites it emits. A row skipped in that
        # build would have no vanilla bytes recorded, and a player whose seed
        # DID move it could not be unpatched.
        expected = {disc.MUSIC_CUE_TABLE + row * 8
                    for row in disc.MUSIC_STAGE_ROWS}
        for seed in range(25):
            a = disc.music_assignment(random.Random(seed))
            self.assertEqual({addr for addr, _p, _r in disc.music_edits(a)},
                             expected, f"seed {seed}")

    def test_no_assignment_means_no_edits(self) -> None:
        self.assertEqual(disc.music_edits({}), [])

    def test_a_wrong_slot_set_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            disc.music_edits({"Sigma": 0x04})

    def test_a_non_stage_track_is_refused(self) -> None:
        a = dict(self.assignment)
        a["Sigma"] = 0x11          # the launch cutscene's track
        with self.assertRaises(ValueError):
            disc.music_edits(a)

    def test_dropping_a_track_entirely_is_refused(self) -> None:
        a = dict(self.assignment)
        for name in a:
            a[name] = disc.MUSIC_STAGE_TRACKS[0]
        with self.assertRaises(ValueError):
            disc.music_edits(a)


class TestNonStagesAreLeftAlone(unittest.TestCase):
    # 0x0B is the Enigma/shuttle launch cutscene - overlay-findings records
    # that confirming a launch sets mode 0x14 (story cutscene) and stage id
    # 0x0B. 0x0F is the transition screen. 0x0D/0x0E are unidentified and
    # cutscene-shaped. 0x17..0x1C are the hub/menu block.
    NOT_STAGES = (0x0B, 0x0D, 0x0E, 0x0F,
                  0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C)

    def test_they_are_not_in_the_row_table(self) -> None:
        for row in self.NOT_STAGES:
            self.assertNotIn(row, disc.MUSIC_STAGE_ROWS)

    def test_the_launch_cutscene_track_is_never_written(self) -> None:
        # Row 0x0B's track, 0x11, is used by nothing else. If it entered the
        # pool it would mean the cutscene had been treated as a stage.
        self.assertNotIn(0x11, disc.MUSIC_STAGE_TRACKS)

    def test_no_seed_ever_writes_one_of_them(self) -> None:
        forbidden = {disc.MUSIC_CUE_TABLE + row * 8 + i
                     for row in self.NOT_STAGES for i in range(8)}
        for seed in range(25):
            a = disc.music_assignment(random.Random(seed))
            for addr, payload, _region in disc.music_edits(a):
                for i in range(len(payload)):
                    self.assertNotIn(addr + i, forbidden, hex(addr))


class TestWhatSplitAndWhatDidNot(unittest.TestCase):
    def test_zero_space_rooms_can_now_differ(self) -> None:
        # Vanilla put all six Zero Space rows on one track. 1, 2 and the duel
        # are separate slots now, so at least some seed must separate them -
        # a repeat can still coincide, which is why this is "some seed".
        separated = 0
        for seed in range(50):
            a = disc.music_assignment(random.Random(seed))
            if len({a["Zero Space 1"], a["Zero Space 2"],
                    a["X vs Zero duel"]}) == 3:
                separated += 1
        self.assertGreater(separated, 0)

    def test_the_unidentified_zero_space_rooms_stay_together(self) -> None:
        # 0x13..0x15 are ONE slot on purpose: unlabelled, and possibly further
        # rooms of a stage rather than stages, where a split would change the
        # music mid-visit.
        for seed in range(25):
            rows = _patched_rows(disc.music_assignment(random.Random(seed)))
            tracks = {t for r in (0x13, 0x14, 0x15) for t in _ids(rows[r])}
            self.assertEqual(len(tracks), 1, f"seed {seed}")

    def test_training_still_matches_the_intro(self) -> None:
        for seed in range(25):
            rows = _patched_rows(disc.music_assignment(random.Random(seed)))
            self.assertEqual(rows[0x16], rows[0x00], f"seed {seed}")

    def test_the_intro_keeps_two_distinct_parts(self) -> None:
        for seed in range(50):
            rows = _patched_rows(disc.music_assignment(random.Random(seed)))
            self.assertEqual(len(set(_ids(rows[0x00]))), 2, f"seed {seed}")
