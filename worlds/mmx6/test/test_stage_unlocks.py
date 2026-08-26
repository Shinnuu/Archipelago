"""Stage unlock tests.

Two halves, and they fail in different ways, so both are worth pinning:

  * the LOGIC half - if the rules are wrong a seed can strand, and the way X5
    stranded was specifically Access Codes placed behind the endgame those
    same codes were needed to reach;
  * the CLIENT half - the slot table is overlay data at a fixed address, so
    the interesting cases are "not in the hub" and "the table came back from
    disc", not the happy path.
"""
import unittest

from BaseClasses import CollectionState

from .. import names
from ..client import (HUB_STAGE_INDEX, SLOT_ANCHOR_BYTES, SLOT_TO_STAGE_ID,
                      STAGE_ID_TO_NAME, STAGE_SELECT_SCREENS)
from ..items import item_table
from . import MMX6TestBase


class TestSlotTableData(unittest.TestCase):
    """Checkable without a multiworld or an emulator."""

    def test_the_slot_table_is_a_permutation_of_the_eight_stage_ids(self) -> None:
        self.assertEqual(sorted(SLOT_TO_STAGE_ID), list(range(1, 9)))

    def test_stage_ids_match_the_world_stage_order(self) -> None:
        # names.STAGE_INDEX is what everything else keys on; a disagreement
        # here would lock the wrong icon.
        for stage, sid in names.STAGE_INDEX.items():
            self.assertEqual(STAGE_ID_TO_NAME[sid], stage)

    def test_the_anchor_is_the_two_rows_we_never_write(self) -> None:
        # Anchor = rows 2 and 3, which are row 1 re-encoded: row2 = row1 - 1,
        # row3 = inverse(row2). If that relationship ever breaks, the constants
        # were transcribed wrong.
        row2 = tuple(SLOT_ANCHOR_BYTES[:8])
        row3 = tuple(SLOT_ANCHOR_BYTES[8:])
        self.assertEqual(row2, tuple(s - 1 for s in SLOT_TO_STAGE_ID))
        inverse = [0] * 8
        for slot, stage in enumerate(row2):
            inverse[stage] = slot
        self.assertEqual(row3, tuple(inverse))

    def test_the_hub_index_is_not_a_real_stage(self) -> None:
        # 0x0D is the stage select. If it collided with a stage id, restoring
        # it after a blocked confirm would send the player somewhere.
        self.assertNotIn(HUB_STAGE_INDEX, SLOT_TO_STAGE_ID)
        self.assertNotIn(0, SLOT_TO_STAGE_ID)   # 0 must mean "locked", nothing else

    def test_stage_select_screens_exclude_gameplay(self) -> None:
        # The stage-index restore only runs on these; if gameplay crept in it
        # would rewrite a live destination.
        from ..client import SCREEN_INGAME, SCREEN_MISSION_REPORT
        self.assertNotIn(SCREEN_INGAME, STAGE_SELECT_SCREENS)
        self.assertNotIn(SCREEN_MISSION_REPORT, STAGE_SELECT_SCREENS)

    def test_every_stage_has_an_access_item_with_a_distinct_id(self) -> None:
        codes = [names.access_item(s) for s in names.STAGES]
        self.assertEqual(codes, names.ACCESS_ITEMS)
        ids = [item_table[c].code for c in codes]
        self.assertEqual(len(set(ids)), len(ids))
        for c in codes:
            self.assertEqual(item_table[c].count, 0,
                             "access items are created by create_items, not the table")


class TestStageUnlocksOff(MMX6TestBase):
    options = {"stage_unlocks": False}

    def test_no_access_items_exist(self) -> None:
        pool = {i.name for i in self.multiworld.itempool}
        self.assertFalse(pool & set(names.ACCESS_ITEMS))

    def test_every_stage_is_open_from_the_start(self) -> None:
        state = self.multiworld.get_all_state()
        for stage in names.STAGES:
            self.assertTrue(
                self.multiworld.get_entrance(f"Stage Select -> {stage}",
                                             self.player).access_rule(state),
                stage)


class TestStageUnlocksOn(MMX6TestBase):
    options = {"stage_unlocks": True, "reploid_checks": True}

    def _blank(self) -> CollectionState:
        """A state holding nothing at all - not even the precollected codes."""
        state = CollectionState(self.multiworld)
        state.prog_items[self.player].clear()
        return state

    def test_seven_codes_in_the_pool_and_one_precollected(self) -> None:
        pooled = [i for i in self.multiworld.itempool
                  if i.name in names.ACCESS_ITEMS]
        self.assertEqual(len(pooled), len(names.STAGES) - 1)
        pre = [i for i in self.multiworld.precollected_items[self.player]
               if i.name in names.ACCESS_ITEMS]
        self.assertEqual(len(pre), 1)
        # and they are disjoint - the starting stage is never also shuffled
        self.assertNotIn(pre[0].name, {i.name for i in pooled})

    def test_the_starting_stage_is_the_precollected_one(self) -> None:
        world = self.multiworld.worlds[self.player]
        pre = [i for i in self.multiworld.precollected_items[self.player]
               if i.name in names.ACCESS_ITEMS]
        self.assertEqual(pre[0].name, names.access_item(world.starting_stage))

    def test_access_items_are_progression(self) -> None:
        for i in self.multiworld.itempool:
            if i.name in names.ACCESS_ITEMS:
                self.assertTrue(i.advancement, i.name)

    def test_a_stage_needs_its_own_codes(self) -> None:
        for stage in names.STAGES:
            entrance = self.multiworld.get_entrance(
                f"Stage Select -> {stage}", self.player)
            self.assertFalse(entrance.access_rule(self._blank()),
                             f"{stage} was enterable with no items at all")
            state = self._blank()
            # create_item, not get_item_by_name: the starting stage's codes
            # are PRECOLLECTED and so are not in the pool to be found.
            state.collect(self.world.create_item(names.access_item(stage)),
                          prevent_sweep=True)
            self.assertTrue(entrance.access_rule(state), stage)

    def test_the_endgame_also_requires_every_access_item(self) -> None:
        # THE X5 BUG. Without this, fill can place a stage's codes inside the
        # endgame that those codes are needed to reach, and the playthrough
        # checker still calls the seed won.
        entrance = self.multiworld.get_entrance("Stage Select -> The Gate",
                                                self.player)
        state = self._blank()
        for weapon in names.WEAPONS:
            state.collect(self.get_item_by_name(weapon), prevent_sweep=True)
        self.assertFalse(entrance.access_rule(state),
                         "all weapons alone must NOT open the endgame while "
                         "stages are locked")
        for stage in names.STAGES:
            state.collect(self.world.create_item(names.access_item(stage)),
                          prevent_sweep=True)
        self.assertTrue(entrance.access_rule(state))

    def test_the_pool_still_balances_against_the_locations(self) -> None:
        # Adding seven items without seven homes would silently drop them.
        # WorldTestBase does not run fill, so this arithmetic check is the
        # only thing standing between us and X5's silent five-item loss.
        real = [l for l in self.multiworld.get_locations(self.player)
                if l.address is not None]
        self.assertEqual(len(self.multiworld.itempool), len(real))
