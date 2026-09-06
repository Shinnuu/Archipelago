"""Stage music shuffle tests.

The feature is one table: the cue table at 0x800707CC maps a stage id to the
BGM id that stage asks for, and shuffling stage music means rewriting the id
byte of the rows that are stages. The stream table - where a BGM id actually
lives on the disc - is deliberately NOT touched, which is what keeps the hub,
cutscenes and jingles on vanilla music without an exclusion list.

So what needs protecting is not the byte offsets (those were extracted from
the disc EXE, not typed) but the PROPERTIES that make the shuffle safe:

  * it is a permutation, so no theme vanishes and none is used twice;
  * volumes survive, because the game mixes stages at four different levels
    and a flat 0x7F would make the quiet ones wrong;
  * one global id->id mapping, so rows that shared a track still share it -
    the six Zero Space rooms, the two Dynamo sorties, and the intro's
    two-part theme;
  * rows that are NOT stages stay out of the table entirely. The sharp one is
    0x0B: it is the Enigma/shuttle launch CUTSCENE, and it looks exactly like
    a stage row.
"""
import random
import unittest

from .. import disc


def _ids(row: bytes) -> tuple[int, ...]:
    return tuple(row[i * 2] for i in range(4))


def _vols(row: bytes) -> tuple[int, ...]:
    return tuple(row[i * 2 + 1] for i in range(4))


def _patched_rows(mapping: dict[int, int]) -> dict[int, bytes]:
    out = dict(disc.MUSIC_STAGE_ROWS)
    for addr, payload, _region in disc.music_edits(mapping):
        out[(addr - disc.MUSIC_CUE_TABLE) // 8] = payload
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
        collapsed = {t: disc.MUSIC_STAGE_TRACKS[0]
                     for t in disc.MUSIC_STAGE_TRACKS}
        with self.assertRaises(ValueError):
            disc.music_edits(collapsed)

    def test_a_mapping_over_the_wrong_ids_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            disc.music_edits({0x00: 0x01})

    def test_no_mapping_means_no_edits(self) -> None:
        self.assertEqual(disc.music_edits({}), [])


class TestTheEdits(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = disc.music_permutation(random.Random(1234))
        self.edits = disc.music_edits(self.mapping)

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
        # The cue table straddles a sector boundary, so this is not a formality
        # - it is the arithmetic that a flat byte offset would get wrong.
        for addr, payload, region in self.edits:
            for i in range(len(payload)):
                self.assertIsInstance(disc.addr_to_disc(addr + i, region), int)

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
            sites = {addr for addr, _p, _r in disc.music_edits(mapping)}
            self.assertEqual(sites, expected, f"seed {seed}")

    def test_the_identity_permutation_still_writes_every_row_unchanged(self) -> None:
        identity = {t: t for t in disc.MUSIC_STAGE_TRACKS}
        edits = disc.music_edits(identity)
        self.assertEqual(len(edits), len(disc.MUSIC_STAGE_ROWS))
        for addr, payload, _region in edits:
            row = (addr - disc.MUSIC_CUE_TABLE) // 8
            self.assertEqual(payload, disc.MUSIC_STAGE_ROWS[row])


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
        # Row 0x0B's track, 0x11, is used by nothing else. If it ever entered
        # the pool it would mean the cutscene had been treated as a stage.
        self.assertNotIn(0x11, disc.MUSIC_STAGE_TRACKS)

    def test_no_seed_ever_writes_one_of_them(self) -> None:
        forbidden = {disc.MUSIC_CUE_TABLE + row * 8 + i
                     for row in self.NOT_STAGES for i in range(8)}
        for seed in range(25):
            mapping = disc.music_permutation(random.Random(seed))
            for addr, payload, _region in disc.music_edits(mapping):
                for i in range(len(payload)):
                    self.assertNotIn(addr + i, forbidden, hex(addr))


class TestSharedRowsStayShared(unittest.TestCase):
    # Three groups share a track in vanilla and have to keep sharing one, or
    # the music changes between rooms of the same place.
    GROUPS = {
        "Zero Space": (0x10, 0x11, 0x12, 0x13, 0x14, 0x15),
        "Dynamo sorties": (0x09, 0x0A),
        "intro and training": (0x00, 0x16),
    }

    def test_each_group_shares_its_tracks_in_vanilla(self) -> None:
        for name, rows in self.GROUPS.items():
            rowsets = {_ids(disc.MUSIC_STAGE_ROWS[r]) for r in rows}
            self.assertEqual(len(rowsets), 1, name)

    def test_each_group_still_agrees_after_any_shuffle(self) -> None:
        for seed in range(25):
            rows = _patched_rows(disc.music_permutation(random.Random(seed)))
            for name, group in self.GROUPS.items():
                rowsets = {_ids(rows[r]) for r in group}
                self.assertEqual(len(rowsets), 1, f"{name}, seed {seed}")

    def test_the_intro_keeps_two_distinct_parts(self) -> None:
        # The intro row is 02/03/02/03 - a two-part theme picked by the second
        # selector. A row-fill would flatten it to one track.
        for seed in range(25):
            rows = _patched_rows(disc.music_permutation(random.Random(seed)))
            self.assertEqual(len(set(_ids(rows[0x00]))), 2, f"seed {seed}")
