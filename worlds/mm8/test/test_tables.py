"""The id arithmetic and the bolt table - the contracts the client and the
disc patch will read, checked without building a world."""
import unittest

from .. import bolts, names
from ..items import BASE_ID, item_table
from ..locations import location_table


class TestIds(unittest.TestCase):
    def test_location_count(self):
        # 40 bolts + 17 Lab + 8 bosses + 4 mid-bosses + Mega Ball + Duo + Wily 1-3
        # + Wily 3's Bass = 75 in every seed, + 8 Wily 4 rematches
        # (rematch_checks) + 42 placed pickups and the ice block's capsule
        # (pickupsanity), which only their options add.
        self.assertEqual(len(location_table), 75 + 8 + 43)

    def test_the_select_positions_are_the_games(self):
        """0x801379A8 read off the disc: Tengu 0, Frost 1, Clown 4, Grenade 5,
        Astro 6, Sword 7, Search 10, Aqua 11."""
        self.assertEqual(names.SELECT_POSITION, {
            names.TENGU: 0, names.FROST: 1, names.CLOWN: 4, names.GRENADE: 5,
            names.ASTRO: 6, names.SWORD: 7, names.SEARCH: 10, names.AQUA: 11})

    def test_rematch_bits_follow_the_refight_table(self):
        """0x801387EC = 1F 40 27 35 4C 3A 56 48: the boss ids of stages 1-8."""
        self.assertEqual([names.REMATCH_BIT[b] for b in names.ROBOT_MASTERS], list(range(8)))

    def test_ids_unique(self):
        self.assertEqual(len(set(location_table.values())), len(location_table))
        codes = [d.code for d in item_table.values()]
        self.assertEqual(len(set(codes)), len(codes))

    def test_bolt_id_is_its_bit(self):
        """The client turns bit N of 0x8016D2FB straight into BASE + 100 + N."""
        for sub_id, name in bolts.BOLT_LOCATIONS.items():
            self.assertEqual(location_table[name], BASE_ID + 100 + sub_id)

    def test_shop_id_is_the_part_id(self):
        for part in names.PARTS:
            self.assertEqual(location_table[names.shop_location(part)],
                             BASE_ID + 200 + names.PART_ID[part])

    def test_weapon_item_id_is_its_slot(self):
        """The client writes 0x801B1EAC + (id - BASE) * 4."""
        for weapon, slot in names.WEAPON_SLOT.items():
            self.assertEqual(item_table[weapon].code, BASE_ID + slot)

    def test_boss_weapon_slots_match_the_game_table(self):
        """0x80137B2B, stage -> slot, read off the disc: Frost 4, Clown 3,
        Tengu 5, Grenade 2, Sword 7, Aqua 6, Astro 9, Search 8."""
        game_table = {1: 4, 2: 3, 3: 5, 4: 2, 5: 7, 6: 6, 7: 9, 8: 8}
        for boss, weapon in names.BOSS_WEAPON.items():
            self.assertEqual(names.WEAPON_SLOT[weapon],
                             game_table[names.STAGE_INDEX[boss]], boss)


class TestParts(unittest.TestCase):
    def test_seventeen_in_game_order(self):
        self.assertEqual(len(names.PARTS), 17)
        self.assertEqual(names.PART_ID[names.ENERGY_SAVER], 1)
        # The two the internal names get backwards: `charger` is id 6 and
        # `spear` id 14, and the game's own descriptions say which is which.
        self.assertEqual(names.PART_ID[names.HIGH_SPEED_CHARGE], 6)
        self.assertEqual(names.PART_ID[names.SPARE_CHARGER], 14)
        self.assertEqual(names.PART_ID[names.STEP_BOOSTER], 17)

    def test_costs_and_stock(self):
        self.assertEqual(sum(names.PART_COST.values()), 89)
        self.assertEqual(len(names.START_STOCK), 9)
        self.assertEqual(len(names.POST_DUO_STOCK), 8)
        self.assertEqual(sum(names.PART_COST[p] for p in names.START_STOCK), 47)

    def test_lab_prices_total_the_games_bolts(self):
        """Every part buyable with every bolt: the repriced Lab totals 40,
        the bolts in the game."""
        self.assertEqual(sum(names.LAB_PRICE.values()), len(bolts.BOLT_STAGE))
        self.assertEqual(sum(names.LAB_PRICE[p] for p in names.START_STOCK), 21)
        for part in names.PARTS:
            self.assertGreaterEqual(names.LAB_PRICE[part], 1, part)
            self.assertLessEqual(names.LAB_PRICE[part], names.PART_COST[part], part)


class TestBolts(unittest.TestCase):
    def test_forty_distinct(self):
        self.assertEqual(sorted(bolts.BOLT_STAGE), list(range(40)))

    def test_stage_counts_match_the_guide(self):
        """The disc and the guide agree on every stage's count - the check
        that confirmed the stage mapping in the first place."""
        for stage, guide in bolts.GUIDE.items():
            on_disc = sum(1 for s in bolts.BOLT_STAGE.values() if s == stage)
            self.assertEqual(on_disc, len(guide), stage)

    def test_no_bolts_in_wily(self):
        self.assertFalse(set(bolts.BOLT_STAGE.values()) & set(names.WILY_STAGES))

    # Every bolt's whole requirement, as research repo plan
    # 2026-10-03_per-bolt-logic.md section 3 tables it (Search's 37 also waits
    # on the doors, Sword's 21 on the trials: test_soft_locks).
    EXPECTED = {
        "Frost Man - Bolt 1": [], "Frost Man - Bolt 2": [],
        "Frost Man - Bolt 3": [{"Mega Ball"}], "Frost Man - Bolt 4": [{"Mega Ball"}],
        "Frost Man - Bolt 5": [{"Astro Crush"}],
        "Frost Man - Bolt 6": [{"Mega Ball"}, {"Astro Crush", "Flame Sword", "Flash Bomb"}],
        "Clown Man - Bolt 1": [{"Rush Bike"}], "Clown Man - Bolt 2": [],
        "Clown Man - Bolt 3": [{"Mega Ball"}, {"Flame Sword"}],
        "Clown Man - Bolt 4": [{"Mega Ball", "Tornado Hold"}],
        "Clown Man - Bolt 5": [{"Tornado Hold"}, {"Mega Ball"}],
        "Tengu Man - Bolt 1": [], "Tengu Man - Bolt 2": [{"Homing Sniper", "Astro Crush"}],
        "Tengu Man - Bolt 3": [], "Tengu Man - Bolt 4": [],
        "Grenade Man - Bolt 1": [{"Mega Ball"}], "Grenade Man - Bolt 2": [],
        "Grenade Man - Bolt 3": [{"Flame Sword"}], "Grenade Man - Bolt 4": [], "Grenade Man - Bolt 5": [],
        "Sword Man - Bolt 1": [], "Sword Man - Bolt 2": [], "Sword Man - Bolt 3": [{"Flash Bomb"}],
        "Aqua Man - Bolt 1": [{"Astro Crush"}], "Aqua Man - Bolt 2": [{"Tornado Hold"}],
        "Aqua Man - Bolt 3": [{"Astro Crush"}], "Aqua Man - Bolt 4": [{"Astro Crush"}],
        "Astro Man - Bolt 1": [], "Astro Man - Bolt 2": [], "Astro Man - Bolt 3": [],
        "Astro Man - Bolt 4": [{"Mega Ball", "Tornado Hold"}],
        "Search Man - Bolt 1": [],
        "Search Man - Bolt 2": [{"Tornado Hold"}, {"Thunder Claw"}],
        "Search Man - Bolt 3": [{"Flame Sword"}],
        "Search Man - Bolt 4": [{"Thunder Claw"}],
        "Duo - Bolt 1": [{"Mega Ball"}], "Duo - Bolt 2": [{"Thunder Claw"}, {"Mega Ball"}],
        "Intro Stage - Bolt 1": [], "Intro Stage - Bolt 2": [], "Intro Stage - Bolt 3": [],
    }

    def test_every_bolt_s_requirement_is_the_plan_s(self):
        self.assertEqual(set(self.EXPECTED), set(bolts.BOLT_LOCATIONS.values()))
        for sub_id, name in bolts.BOLT_LOCATIONS.items():
            self.assertEqual(sorted(map(sorted, bolts.requirement(sub_id))),
                             sorted(map(sorted, self.EXPECTED[name])), name)

    def test_the_disc_anchors_agree_with_the_play_order(self):
        """The control on pairing a guide number with PLAY_ORDER: every bolt
        the disc itself ties to a guide entry sits at that place."""
        self.assertEqual(set(bolts.ANCHORS), {14, 7, 27, 24, 6, 35})
        for sub_id, (stage, number) in bolts.ANCHORS.items():
            self.assertEqual(bolts.BOLT_STAGE[sub_id], stage, sub_id)
            self.assertEqual(bolts.guide_number(sub_id), number, sub_id)

    def test_an_ungrouped_bolt_takes_its_own_guide_entry_and_no_other(self):
        """Not the stage's conjunction any more (0.2.0): Frost Man's first two
        bolts need nothing though bolts 5 and 6 need Astro Crush."""
        grouped = {s for g in bolts.GROUPS for s in g}
        for sub_id, stage in bolts.BOLT_STAGE.items():
            if sub_id in grouped or sub_id in bolts.OVERRIDE:
                continue
            own = bolts.GUIDE[stage][bolts.guide_number(sub_id) - 1] + bolts.EXTRA.get(sub_id, ())
            self.assertEqual(set(bolts.requirement(sub_id)), set(own), sub_id)
        self.assertEqual(bolts.requirement(2), ())

    def test_a_group_carries_every_member_s_entry(self):
        for group in bolts.GROUPS:
            stage = bolts.BOLT_STAGE[group[0]]
            for sub_id in group:
                self.assertEqual(bolts.BOLT_STAGE[sub_id], stage, group)
                for member in group:
                    entry = bolts.GUIDE[stage][bolts.guide_number(member) - 1]
                    self.assertLessEqual(set(entry), set(bolts.requirement(sub_id)), (sub_id, member))

    def test_corrections_are_never_looser_than_the_guide(self):
        """EXTRA adds to an entry and OVERRIDE replaces one only where it asks
        at least as much: an item set meeting the override meets the guide."""
        for sub_id in bolts.OVERRIDE:
            stage = bolts.BOLT_STAGE[sub_id]
            entry = bolts.GUIDE[stage][bolts.guide_number(sub_id) - 1]
            for clause in entry:
                self.assertTrue(any(c <= clause for c in bolts.requirement(sub_id)), sub_id)
        for sub_id, extra in bolts.EXTRA.items():
            self.assertLessEqual(set(extra), set(bolts.requirement(sub_id)), sub_id)

    def test_location_names_unique(self):
        self.assertEqual(len(set(bolts.BOLT_LOCATIONS.values())), 40)

    def test_play_order_names_every_bolt_once(self):
        listed = [s for order in bolts.PLAY_ORDER.values() for s in order]
        self.assertEqual(sorted(listed), sorted(bolts.BOLT_STAGE))
        for stage, order in bolts.PLAY_ORDER.items():
            self.assertEqual({bolts.BOLT_STAGE[s] for s in order}, {stage})
            self.assertEqual([bolts.BOLT_LOCATIONS[s] for s in order],
                             [f"{stage} - Bolt {k}" for k in range(1, len(order) + 1)])

    def test_play_order_agrees_with_what_was_seen(self):
        """The ramwatch's BOLT events (orders a player really collected
        them in), and the one bolt the disc ties to a guide number."""
        order = bolts.PLAY_ORDER
        self.assertEqual(order[names.CLOWN][:4], [10, 22, 7, 8])
        self.assertLess(order[names.GRENADE].index(32), order[names.GRENADE].index(17))
        self.assertLess(order[names.TENGU].index(11), order[names.TENGU].index(12))
        self.assertEqual(order[names.INTRO][0], 33)
        for sub_id, (stage, number) in bolts.ANCHORS.items():
            self.assertEqual(order[stage].index(sub_id) + 1, number, sub_id)
        # The guide's text: Search's hook-room bolt (36) before the Flame
        # Sword corridor's (35) - the names swapped in 0.2.1.
        self.assertLess(order[names.SEARCH].index(36), order[names.SEARCH].index(35))
        self.assertEqual(bolts.BOLT_LOCATIONS[36], "Search Man - Bolt 2")
