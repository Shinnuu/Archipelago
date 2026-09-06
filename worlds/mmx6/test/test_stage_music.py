"""Stage music shuffle tests.

The feature is one table: the cue table at 0x8007093C maps a stage id to the
BGM id that stage asks for, and shuffling stage music means rewriting the id
byte of the rows that are stages. The stream table - where a BGM id actually
lives on the disc - is deliberately NOT touched, which is what keeps menus,
cutscenes and jingles on vanilla music without an exclusion list.

So what needs protecting is not the byte offsets (those were extracted from
the disc EXE, not typed) but the PROPERTIES that make the shuffle safe:

  * it is a permutation, so no theme vanishes and none is used twice;
  * volumes survive, because the game mixes stages at three different levels
    and a flat 0x7F would make the quiet ones wrong;
  * one global id->id mapping, so a stage sounds the same on its revisit as
    it did on the first visit, and rows that shared a track still share it;
  * rows that are NOT stages stay out of the table entirely.

The revisit property is the one that would rot silently. X6 rows 0x13..0x16
are the eight Maverick stages a second time, packed two stages per row, and a
per-row roll would give a stage different music the second time you enter it.
"""
import random
import unittest

from .. import disc


def _ids(row: bytes) -> tuple[int, ...]:
    return tuple(row[i * 2] for i in range(4))


def _vols(row: bytes) -> tuple[int, ...]:
    return tuple(row[i * 2 + 1] for i in range(4))


def _patched_rows(mapping: dict[int, int]) -> dict[int, bytes]:
    """Every stage row after the edit, including rows the edit left alone."""
    out = dict(disc.MUSIC_STAGE_ROWS)
    for _label, where, _region, _van, patched in disc.music_edits(mapping):
        out[(where - disc.MUSIC_CUE_TABLE) // 8] = patched
    return out


class TestThePool(unittest.TestCase):
    def test_the_pool_is_exactly_the_tracks_the_stage_rows_use(self) -> None:
        used = {i for row in disc.MUSIC_STAGE_ROWS.values() for i in _ids(row)}
        self.assertEqual(used, set(disc.MUSIC_STAGE_TRACKS))

    def test_the_permutation_is_a_permutation(self) -> None:
        for seed in range(50):
            mapping = disc.music_permutation(random.Random(seed))
            self.assertEqual(set(mapping), set(disc.MUSIC_STAGE_TRACKS))
            self.assertEqual(sorted(mapping.values()),
                             sorted(disc.MUSIC_STAGE_TRACKS))

    def test_a_mapping_that_loses_a_track_is_refused(self) -> None:
        # Onto a smaller set: one theme would become unreachable.
        collapsed = {t: disc.MUSIC_STAGE_TRACKS[0]
                     for t in disc.MUSIC_STAGE_TRACKS}
        with self.assertRaises(ValueError):
            disc.music_edits(collapsed)

    def test_a_mapping_over_the_wrong_ids_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            disc.music_edits({0x00: 0x01})

    def test_no_mapping_means_no_edits(self) -> None:
        self.assertEqual(disc.music_edits({}), [])

    def test_the_edit_sites_do_not_depend_on_the_roll(self) -> None:
        # The unpatcher's manifest is built by running patch_rom once at a
        # fixed seed and recording the sites it emits. If a row whose track
        # mapped to itself were skipped, that row's vanilla bytes would go
        # unrecorded and a player whose seed DID move it could not be
        # unpatched. So every stage row is written on every seed.
        expected = {disc.MUSIC_CUE_TABLE + row * 8
                    for row in disc.MUSIC_STAGE_ROWS}
        for seed in range(25):
            mapping = disc.music_permutation(random.Random(seed))
            sites = {where for _l, where, _r, _v, _p in disc.music_edits(mapping)}
            self.assertEqual(sites, expected, f"seed {seed}")

    def test_the_identity_permutation_still_writes_every_row_unchanged(self) -> None:
        identity = {t: t for t in disc.MUSIC_STAGE_TRACKS}
        edits = disc.music_edits(identity)
        self.assertEqual(len(edits), len(disc.MUSIC_STAGE_ROWS))
        for label, _w, _r, van, patched in edits:
            self.assertEqual(patched, van, label)


class TestTheEdits(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = disc.music_permutation(random.Random(1234))
        self.edits = disc.music_edits(self.mapping)

    def test_the_declared_vanilla_matches_the_row_table(self) -> None:
        for label, where, region, van, _patched in self.edits:
            row = (where - disc.MUSIC_CUE_TABLE) // 8
            self.assertEqual(region, disc.REGION_EXE, label)
            self.assertEqual(van, disc.MUSIC_STAGE_ROWS[row], label)

    def test_volumes_are_never_touched(self) -> None:
        for label, where, _region, van, patched in self.edits:
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


class TestNonStagesAreLeftAlone(unittest.TestCase):
    # Rows identified from the stage roster in mmx6-ram-notes.md. 0x0B is a
    # cutscene and 0x0D/0x0E/0x0F are Stage Select / Title Menus / Mission
    # Report - the four that look most like stages and are not.
    NOT_STAGES = (0x09, 0x0A, 0x0B, 0x0D, 0x0E, 0x0F,
                  0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C)

    def test_they_are_not_in_the_row_table(self) -> None:
        for row in self.NOT_STAGES:
            self.assertNotIn(row, disc.MUSIC_STAGE_ROWS)

    def test_no_seed_ever_writes_one_of_them(self) -> None:
        forbidden = {disc.MUSIC_CUE_TABLE + row * 8 + i
                     for row in self.NOT_STAGES for i in range(8)}
        for seed in range(25):
            mapping = disc.music_permutation(random.Random(seed))
            for label, where, _r, _van, patched in disc.music_edits(mapping):
                for i in range(len(patched)):
                    self.assertNotIn(where + i, forbidden, label)


class TestAStageSoundsTheSameEveryVisit(unittest.TestCase):
    # X6 rows 0x13..0x16 are the eight Maverick stages again - the revisits,
    # two stages per row. A per-row roll would change a stage's music between
    # visits; one global id->id mapping cannot.
    FIRST_VISIT = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08)
    REVISIT = (0x13, 0x14, 0x15, 0x16)

    def test_the_revisit_rows_reuse_the_first_visit_tracks(self) -> None:
        first = {t for row in self.FIRST_VISIT
                 for t in _ids(disc.MUSIC_STAGE_ROWS[row])}
        again = {t for row in self.REVISIT
                 for t in _ids(disc.MUSIC_STAGE_ROWS[row])}
        self.assertEqual(again, first)

    def test_a_revisit_plays_what_the_first_visit_plays(self) -> None:
        for seed in range(25):
            mapping = disc.music_permutation(random.Random(seed))
            rows = _patched_rows(mapping)
            # vanilla track -> what the Maverick rows now play for it
            became: dict[int, int] = {}
            for row in self.FIRST_VISIT:
                for was, now in zip(_ids(disc.MUSIC_STAGE_ROWS[row]),
                                    _ids(rows[row])):
                    became[was] = now
            for row in self.REVISIT:
                for was, now in zip(_ids(disc.MUSIC_STAGE_ROWS[row]),
                                    _ids(rows[row])):
                    self.assertEqual(now, became[was],
                                     f"seed {seed}, revisit row 0x{row:02X}")


class TestSharedRowsStayShared(unittest.TestCase):
    # Secret Lab 1 / 2A / 2B are three rows on one track in vanilla. They have
    # to stay on ONE track, or the finale changes music between its own rooms.
    SECRET_LAB = (0x10, 0x11, 0x12)

    def test_they_share_a_track_in_vanilla(self) -> None:
        tracks = {t for row in self.SECRET_LAB
                  for t in _ids(disc.MUSIC_STAGE_ROWS[row])}
        self.assertEqual(len(tracks), 1)

    def test_they_still_share_one_after_any_shuffle(self) -> None:
        for seed in range(25):
            rows = _patched_rows(disc.music_permutation(random.Random(seed)))
            tracks = {t for row in self.SECRET_LAB for t in _ids(rows[row])}
            self.assertEqual(len(tracks), 1, f"seed {seed}")
