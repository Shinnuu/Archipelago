"""The Lab text: each entry naming the AP item it holds.

The layout rules come from the game's text box (0x80104544): a row ends at
0x00 or after 20 characters, and a box always takes 10 rows, reading on into
whatever follows. `rows` below re-implements exactly that, so every string
this world writes is checked the way the game will read it.
"""
import os
import struct
import unittest

from .. import disc, names

TRACK1 = r"C:\Users\Ivor\Documents\Game Modding\Games\Mega Man 8 (USA)\Mega Man 8 (USA) (Track 1).bin"
have_dump = os.path.exists(TRACK1)
DECODE = {v: k for k, v in disc.LAB_CHARSET.items()}


def rows(chunk: bytes, index: int) -> tuple[list[str], int]:
    """(the 10 rows the game shows for string `index`, bytes it consumed)."""
    start = struct.unpack_from("<H", chunk, 2 * index)[0]
    pos, out = start, []
    for _ in range(disc.LAB_ROWS):
        row = ""
        while len(row) < 20:
            b = chunk[pos] if pos < len(chunk) else 0
            pos += 1
            if b == 0:
                break
            row += DECODE.get(b, "?")
        out.append(row)
    return out, pos - start


class TestText(unittest.TestCase):
    def test_sanitize_maps_onto_the_font(self):
        self.assertEqual(disc.lab_sanitize("Café: A&B/C_d  [x]"), "Cafe- A+B-C d (x)")
        self.assertEqual(disc.lab_sanitize("Rock\u2019s"), "Rock's")
        self.assertEqual(disc.lab_sanitize("#1 ★ key"), "1 key")
        for ch in disc.lab_sanitize("Pokémon Émeraude: Ω-Rare #9 100% €"):
            self.assertIn(ch, disc.LAB_CHARSET)

    def test_wrap_fits_columns(self):
        lines = disc.lab_wrap("Supercalifragilisticexpialidocious Stage Access Code")
        self.assertTrue(all(len(line) <= disc.LAB_COLUMNS for line in lines))
        self.assertEqual("".join(lines).replace(" ", ""),
                         "SupercalifragilisticexpialidociousStageAccessCode")

    def test_own_item_is_just_its_name(self):
        self.assertEqual(disc.lab_description("Flame Sword"), ["Flame Sword"])

    def test_own_part_says_what_it_does(self):
        """0.2.0: the player's own part gets its effect under a blank row."""
        self.assertEqual(disc.lab_description("Boost Part", effect=names.PART_EFFECT[names.BOOST_PART]),
                         ["Boost Part", "", "Buster shots fly", "faster."])

    def test_the_effect_goes_first_when_room_is_short(self):
        effect = names.PART_EFFECT[names.BOOST_PART]
        self.assertEqual(disc.lab_description("Boost Part", brevity=2, effect=effect), ["Boost Part"])

    def test_every_part_fits_whole_beside_its_name(self):
        for part in names.PARTS:
            with self.subTest(part=part):
                lines = disc.lab_description(part, effect=names.PART_EFFECT[part])
                self.assertLessEqual(len(lines), disc.LAB_LINES)
                self.assertFalse(lines[-1].endswith("..."), lines)
                self.assertEqual(" ".join(lines[2:]), disc.lab_sanitize(names.PART_EFFECT[part]))
        lines = disc.lab_description(names.EXIT, effect=names.EXIT_EFFECT_WITH_OPTION)
        self.assertFalse(lines[-1].endswith("..."), lines)

    def test_someone_elses_item_says_whose_and_which_game(self):
        self.assertEqual(disc.lab_description("Stage Access Code", "Bob", "Mega Man X5"),
                         ["Bob's", "Stage Access Code", "(Mega Man X5)"])

    def test_a_name_in_another_script_falls_back_rather_than_vanishing(self):
        """Review: a wholly Japanese owner, item and game drew "'s" /
        "Nothing" / "()" - the fallbacks never fired, because "'s" and the
        brackets were added before sanitising."""
        self.assertEqual(disc.lab_description("ゼルダの剣", "たろう", "ゼルダの伝説"),
                         ["Someone's", "Unnamed item"])
        self.assertEqual(disc.lab_description("Master Sword", "たろう", "Zelda"),
                         ["Someone's", "Master Sword", "(Zelda)"])

    def test_letters_without_a_decomposition_get_a_stand_in(self):
        self.assertEqual(disc.lab_sanitize("Łukasz Ætherium Øre Straße"), "Lukasz AEtherium Ore Strasse")
        self.assertEqual(disc.lab_sanitize('the "Key"'), "the “Key”")

    def test_never_more_than_six_lines(self):
        long = "Word " * 40
        for brevity in range(4):
            lines = disc.lab_description(long, "Somebody With A Long Name", long, brevity)
            self.assertLessEqual(len(lines), disc.LAB_LINES, brevity)
            self.assertTrue(all(len(line) <= disc.LAB_COLUMNS for line in lines))
        self.assertTrue(disc.lab_description(long, "P", "G")[-1].endswith("..."))


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestAgainstTheDump(unittest.TestCase):
    track1: bytes
    vanilla: bytes

    @classmethod
    def setUpClass(cls):
        with open(TRACK1, "rb") as f:
            cls.track1 = f.read()
        cls.vanilla = disc.lab_vanilla_chunk(cls.track1)

    def test_rebuilding_with_nothing_changed_is_byte_identical(self):
        """The control: the rebuild must reproduce the vanilla chunk exactly
        before its output can be trusted with new text."""
        self.assertEqual(disc.lab_text_chunk(self.vanilla, {}), self.vanilla)

    def test_the_vanilla_description_decodes(self):
        got, _ = rows(self.vanilla, disc.LAB_FIRST_DESCRIPTION)     # part 1, saver
        self.assertEqual([r for r in got if r][0], "It will save the")
        self.assertEqual([r for r in got if r][-1], "weapon.")

    def test_every_new_description_reads_as_written_and_stops(self):
        entries = {p: (f"Item Number {p} With A Name", f"Player{p}", "Some Game")
                   for p in range(1, 18)}
        lines = disc.lab_fit(entries, self.vanilla)
        chunk = disc.lab_text_chunk(self.vanilla, lines)
        for part in range(1, 18):
            index = disc.LAB_FIRST_DESCRIPTION + part - 1
            got, used = rows(chunk, index)
            self.assertEqual([r for r in got if r], lines[part], part)
            nxt = (struct.unpack_from("<H", chunk, 2 * (index + 1))[0]
                   if index + 1 < disc.LAB_STRINGS else len(chunk))
            start = struct.unpack_from("<H", chunk, 2 * index)[0]
            self.assertLessEqual(start + used, nxt, f"part {part} runs into the next string")
        # Dr. Light's own lines are untouched.
        for index in range(disc.LAB_FIRST_DESCRIPTION):
            self.assertEqual(rows(chunk, index)[0], rows(self.vanilla, index)[0], index)

    def test_a_lab_of_own_parts_keeps_every_description(self):
        """All 17 entries the player's own parts: the most effect text a Lab
        can carry. It must fit at full detail, or every description is lost."""
        entries = {p: (part, None, None) for p, part in enumerate(names.PARTS, start=1)}
        lines = disc.lab_fit(entries, self.vanilla, names.PART_EFFECT)
        chunk = disc.lab_text_chunk(self.vanilla, lines)
        for p, part in enumerate(names.PARTS, start=1):
            got, _ = rows(chunk, disc.LAB_FIRST_DESCRIPTION + p - 1)
            shown = [r for r in got if r]
            self.assertEqual(" ".join(shown[1:]), disc.lab_sanitize(names.PART_EFFECT[part]), part)

    def test_other_players_items_get_no_effect(self):
        # The control: the same part names owned by someone else.
        entries = {p: (part, "Bob", "Mega Man 8") for p, part in enumerate(names.PARTS, start=1)}
        lines = disc.lab_fit(entries, self.vanilla, names.PART_EFFECT)
        for p, part in enumerate(names.PARTS, start=1):
            self.assertNotIn("", lines[p], part)

    def test_descriptions_go_before_any_name_is_cut(self):
        """0.2.0 review m9: the shortening dropped the own parts' descriptions
        and cut every name to two lines in the same step. A Lab that only
        needs the descriptions gone keeps its names whole. (Unreachable with
        real item names - 3,000 random Labs fit at full detail - but cheap.)"""
        foreign = " ".join(["Abcdefghijklmnopqrs"] * 5)            # five full lines
        entries = {p: (foreign, "Bob", "Some Game") if p <= 12 else (part, None, None)
                   for p, part in enumerate(names.PARTS, start=1)}
        lines = disc.lab_fit(entries, self.vanilla, names.PART_EFFECT)
        self.assertEqual(lines[1], ["Bob's"] + ["Abcdefghijklmnopqrs"] * 5, "the name kept whole")
        self.assertEqual(lines[13], [names.PARTS[12]], "the description dropped")
        # The control: with the descriptions kept, it does not fit.
        with self.assertRaises(ValueError):
            disc.lab_text_chunk(self.vanilla, {p: disc.lab_description(i, o, g, 1, names.PART_EFFECT.get(i)
                                                                       if o is None else None)
                                               for p, (i, o, g) in entries.items()})

    def test_the_worst_case_still_fits(self):
        huge = "Extraordinarily Verbose Item Name " * 5
        entries = {p: (huge, "An Unreasonably Long Player Name", huge) for p in range(1, 18)}
        lines = disc.lab_fit(entries, self.vanilla)
        self.assertLessEqual(len(disc.lab_text_chunk(self.vanilla, lines)), disc.LAB_TEXT_ROOM)

    def test_edits_write_the_chunk_and_its_size(self):
        entries = {p: (f"Item {p}", None, None) for p in range(1, 18)}
        patched = disc.apply_edits(self.track1, disc.lab_text_edits(self.track1, entries))
        chunk = disc.lab_vanilla_chunk(patched)    # reads the first 0x650 bytes
        size = int.from_bytes(bytes(patched[disc.addr_to_disc(disc.LAB_TEXT_SIZE_FIELD + i, "pack:LABO.PAC")]
                                    for i in range(4)), "little")
        full = bytes(patched[disc.addr_to_disc(disc.LAB_TEXT_OFFSET + i, "pack:LABO.PAC")]
                     for i in range(size))
        self.assertEqual([r for r in rows(full, disc.LAB_FIRST_DESCRIPTION + 5)[0] if r], ["Item 6"])
        self.assertLessEqual(size, disc.LAB_TEXT_ROOM)
        self.assertEqual(chunk[:2], full[:2])
