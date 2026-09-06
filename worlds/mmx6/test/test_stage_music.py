"""Stage music shuffle tests.

The feature is one table: the cue table at 0x8007093C maps a stage id to the
BGM id that stage asks for, and shuffling stage music means rewriting the id
byte of the rows that are stages. The stream table - where a BGM id actually
lives on the disc - is deliberately NOT touched, which is what keeps menus,
cutscenes and jingles on vanilla music without an exclusion list.

Music is assigned per PLACE, not per track. A row's four (id, volume) pairs
are indexed d*2 + c, so one row can hold two places: rows 0x13..0x16 are the
eight Maverick stages a second time (the revisits, two per row), and row 0x0C
is Secret Lab 3A, the boss rush, alongside 3B, Sigma. Assigning per place is
what lets the three Secret Lab rooms differ, where vanilla had them on one
track.

There are more places (14) than tracks (11), so unlike a permutation some
track must repeat. What is protected here:

  * every track still reaches somewhere, and none is used more than twice;
  * slots that share a ROW stay distinct, or splitting Sigma off from the boss
    rush would be quietly undone by an unlucky roll;
  * a Maverick stage and its revisit are the SAME slot, so a stage cannot
    change music between visits - that is the property that would rot silently;
  * volumes survive, because the game mixes stages at three different levels;
  * every (row, pair) belongs to exactly one slot, and each slot is a single
    track in vanilla - if that stops holding, the slot table has drifted from
    the disc;
  * rows that are NOT stages stay out entirely, 0x0B (a Cutscene) included.
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
    for _label, where, _region, _van, patched in disc.music_edits(assignment):
        out[(where - disc.MUSIC_CUE_TABLE) // 8] = patched
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
        # A slot spanning two vanilla tracks would mean the slot table has
        # drifted from the disc - it would be claiming two places are one.
        for name, positions in disc.MUSIC_SLOTS:
            tracks = {disc.MUSIC_STAGE_ROWS[row][pair * 2]
                      for row, pairs in positions for pair in pairs}
            self.assertEqual(len(tracks), 1, f"{name}: {tracks}")

    def test_the_pool_is_exactly_the_tracks_the_stage_rows_use(self) -> None:
        used = {i for row in disc.MUSIC_STAGE_ROWS.values() for i in _ids(row)}
        self.assertEqual(used, set(disc.MUSIC_STAGE_TRACKS))

    def test_the_revisit_rows_are_folded_into_the_maverick_slots(self) -> None:
        # This is the check that the roster pairing was transcribed right:
        # row 0x13 half d=0 must carry the same vanilla track as the Yammark
        # stage row, and so on for all eight.
        for stage_row, revisit, half in ((0x01, 0x13, (0, 1)), (0x02, 0x13, (2, 3)),
                                         (0x03, 0x14, (0, 1)), (0x04, 0x14, (2, 3)),
                                         (0x05, 0x15, (0, 1)), (0x06, 0x15, (2, 3)),
                                         (0x07, 0x16, (0, 1)), (0x08, 0x16, (2, 3))):
            stage_track = disc.MUSIC_STAGE_ROWS[stage_row][0]
            for pair in half:
                self.assertEqual(disc.MUSIC_STAGE_ROWS[revisit][pair * 2],
                                 stage_track,
                                 f"row 0x{revisit:02X} pair {pair}")

    def test_secret_lab_3_is_two_slots(self) -> None:
        names = [n for n, _p in disc.MUSIC_SLOTS if n.startswith("Secret Lab 3")]
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
        cap = -(-len(disc.MUSIC_SLOTS) // len(disc.MUSIC_STAGE_TRACKS))
        for seed in range(200):
            counts = collections.Counter(
                disc.music_assignment(random.Random(seed)).values())
            self.assertLessEqual(max(counts.values()), cap, f"seed {seed}")

    def test_slots_sharing_a_row_get_different_tracks(self) -> None:
        for seed in range(200):
            a = disc.music_assignment(random.Random(seed))
            self.assertFalse(disc._shares_a_row_track(a), f"seed {seed}")

    def test_the_boss_rush_and_sigma_always_differ(self) -> None:
        # They share row 0x0C, so the same-row rule covers them - stated on its
        # own because it is the reason that rule exists.
        for seed in range(200):
            a = disc.music_assignment(random.Random(seed))
            self.assertNotEqual(a["Secret Lab 3A (boss rush)"],
                                a["Secret Lab 3B (Sigma)"], f"seed {seed}")

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

    def test_the_declared_vanilla_matches_the_row_table(self) -> None:
        for label, where, region, van, _patched in self.edits:
            row = (where - disc.MUSIC_CUE_TABLE) // 8
            self.assertEqual(region, disc.REGION_EXE, label)
            self.assertEqual(van, disc.MUSIC_STAGE_ROWS[row], label)

    def test_volumes_are_never_touched(self) -> None:
        for label, _w, _r, van, patched in self.edits:
            self.assertEqual(_vols(patched), _vols(van), label)

    def test_every_written_id_is_a_stage_track(self) -> None:
        for label, _w, _r, _van, patched in self.edits:
            for track in _ids(patched):
                self.assertIn(track, disc.MUSIC_STAGE_TRACKS, label)

    def test_edits_land_only_on_stage_rows(self) -> None:
        for label, where, _r, _van, _p in self.edits:
            offset = where - disc.MUSIC_CUE_TABLE
            self.assertEqual(offset % 8, 0, label)
            self.assertIn(offset // 8, disc.MUSIC_STAGE_ROWS, label)

    def test_no_two_edits_overlap(self) -> None:
        seen: set[int] = set()
        for label, where, _r, _van, patched in self.edits:
            for i in range(len(patched)):
                self.assertNotIn(where + i, seen, label)
                seen.add(where + i)

    def test_the_edit_sites_do_not_depend_on_the_roll(self) -> None:
        expected = {disc.MUSIC_CUE_TABLE + row * 8
                    for row in disc.MUSIC_STAGE_ROWS}
        for seed in range(25):
            a = disc.music_assignment(random.Random(seed))
            sites = {w for _l, w, _r, _v, _p in disc.music_edits(a)}
            self.assertEqual(sites, expected, f"seed {seed}")

    def test_no_assignment_means_no_edits(self) -> None:
        self.assertEqual(disc.music_edits({}), [])

    def test_a_wrong_slot_set_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            disc.music_edits({"Intro stage": 0x09})

    def test_a_non_stage_track_is_refused(self) -> None:
        a = dict(self.assignment)
        a["Intro stage"] = 0x01          # a menu theme, not a stage track
        with self.assertRaises(ValueError):
            disc.music_edits(a)

    def test_dropping_a_track_entirely_is_refused(self) -> None:
        a = {name: disc.MUSIC_STAGE_TRACKS[0] for name in self.assignment}
        with self.assertRaises(ValueError):
            disc.music_edits(a)


class TestNonStagesAreLeftAlone(unittest.TestCase):
    # From the stage roster in mmx6-ram-notes.md. 0x0B is a Cutscene and
    # 0x0D/0x0E/0x0F are Stage Select / Title Menus / Mission Report - the
    # four that look most like stages and are not.
    NOT_STAGES = (0x09, 0x0A, 0x0B, 0x0D, 0x0E, 0x0F,
                  0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C)

    def test_they_are_not_in_the_row_table(self) -> None:
        for row in self.NOT_STAGES:
            self.assertNotIn(row, disc.MUSIC_STAGE_ROWS)

    def test_no_seed_ever_writes_one_of_them(self) -> None:
        forbidden = {disc.MUSIC_CUE_TABLE + row * 8 + i
                     for row in self.NOT_STAGES for i in range(8)}
        for seed in range(25):
            a = disc.music_assignment(random.Random(seed))
            for label, where, _r, _van, patched in disc.music_edits(a):
                for i in range(len(patched)):
                    self.assertNotIn(where + i, forbidden, label)


class TestWhatSplitAndWhatDidNot(unittest.TestCase):
    SECRET_LAB = (0x10, 0x11, 0x12)
    FIRST_VISIT = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08)
    REVISIT = ((0x13, (0, 1)), (0x13, (2, 3)), (0x14, (0, 1)), (0x14, (2, 3)),
               (0x15, (0, 1)), (0x15, (2, 3)), (0x16, (0, 1)), (0x16, (2, 3)))

    def test_the_secret_lab_rooms_shared_a_track_in_vanilla(self) -> None:
        tracks = {t for row in self.SECRET_LAB
                  for t in _ids(disc.MUSIC_STAGE_ROWS[row])}
        self.assertEqual(len(tracks), 1)

    def test_the_secret_lab_rooms_can_now_differ(self) -> None:
        # A repeat can still make two coincide, which is why this is
        # "some seed" rather than "every seed".
        separated = 0
        for seed in range(50):
            rows = _patched_rows(disc.music_assignment(random.Random(seed)))
            if len({_ids(rows[r])[0] for r in self.SECRET_LAB}) == 3:
                separated += 1
        self.assertGreater(separated, 0)

    def test_a_revisit_always_plays_what_the_first_visit_plays(self) -> None:
        for seed in range(50):
            rows = _patched_rows(disc.music_assignment(random.Random(seed)))
            for stage_row, (revisit, half) in zip(self.FIRST_VISIT,
                                                  self.REVISIT):
                want = _ids(rows[stage_row])[0]
                for pair in half:
                    self.assertEqual(_ids(rows[revisit])[pair], want,
                                     f"seed {seed}, row 0x{revisit:02X}")
