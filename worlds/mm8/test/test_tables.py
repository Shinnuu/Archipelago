"""The id arithmetic and the bolt table - the contracts the client and the
disc patch will read, checked without building a world."""
import unittest

from .. import bolts, names
from ..items import BASE_ID, item_table
from ..locations import location_table


class TestIds(unittest.TestCase):
    def test_location_count(self):
        # 40 bolts + 17 Lab + 8 bosses + 4 mid-bosses + Mega Ball + Duo + Wily 1-3
        self.assertEqual(len(location_table), 74)

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

    def test_bolt_14_is_pinned_to_its_own_requirement(self):
        self.assertEqual(bolts.requirement(14),
                         (frozenset({names.HOMING_SNIPER, names.ASTRO_CRUSH}),))

    def test_rest_of_tengu_is_free(self):
        """Tengu's other three guide bolts need nothing, so pinning 14 frees
        11, 12 and 13 - the point of pinning."""
        for sub_id in (11, 12, 13):
            self.assertEqual(bolts.requirement(sub_id), (), sub_id)

    def test_unpinned_bolts_over_gate(self):
        """Every unpinned bolt carries every clause of every unpinned guide
        bolt in its stage, so whichever guide bolt it really is, logic asks
        for at least that much."""
        for sub_id, stage in bolts.BOLT_STAGE.items():
            if sub_id in bolts.PINNED:
                continue
            taken = {num for s, num in bolts.PINNED.values() if s == stage}
            req = set(bolts.requirement(sub_id))
            for number, guide_req in enumerate(bolts.GUIDE[stage], start=1):
                if number not in taken:
                    self.assertLessEqual(set(guide_req), req, (sub_id, number))

    def test_location_names_unique(self):
        self.assertEqual(len(set(bolts.BOLT_LOCATIONS.values())), 40)
