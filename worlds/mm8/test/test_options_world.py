"""Generation with the location/item options: stage_unlocks and
rematch_checks. WorldTestBase also runs its fill and reachability checks on
each of these configurations."""
from . import MM8TestBase
from .. import music, names, pickups


class TestStageUnlocks(MM8TestBase):
    options = {"stage_unlocks": True}

    def test_one_set_1_stage_starts_open(self):
        start = self.world.starting_stage
        self.assertIn(start, names.SET_1)
        precollected = {i.name for i in self.multiworld.precollected_items[self.player]}
        self.assertEqual(precollected & set(names.ACCESS_ITEMS), {names.access_item(start)})
        pooled = [i.name for i in self.multiworld.itempool if i.player == self.player]
        for boss in names.ROBOT_MASTERS:
            self.assertEqual(pooled.count(names.access_item(boss)), 0 if boss == start else 1, boss)

    def test_a_locked_stage_needs_its_codes(self):
        self.multiworld.state.sweep_for_advancements()
        locked = next(b for b in names.SET_1 if b != self.world.starting_stage)
        self.assertTrue(self.can_reach_region(self.world.starting_stage))
        self.assertFalse(self.can_reach_region(locked))
        self.collect_by_name(names.access_item(locked))
        self.assertTrue(self.can_reach_region(locked))

    def test_set_2_needs_duo_as_well_as_its_codes(self):
        self.multiworld.state.sweep_for_advancements()
        self.collect_by_name(names.access_item(names.SWORD))
        self.assertFalse(self.can_reach_region(names.SWORD))


class TestRematchChecks(MM8TestBase):
    options = {"rematch_checks": True}

    def test_eight_rematches_in_wily_4(self):
        for boss in names.ROBOT_MASTERS:
            location = self.multiworld.get_location(names.rematch_location(boss), self.player)
            self.assertEqual(location.parent_region.name, names.WILY_4)


class TestWithoutRematchChecks(MM8TestBase):
    options = {"rematch_checks": False}

    def test_no_rematch_locations(self):
        mine = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertFalse(any("Rematch" in name for name in mine))


class TestPickupsanity(MM8TestBase):
    options = {"pickupsanity": True}

    def test_each_pickup_is_in_its_stage(self):
        for stage, _r, _k, name in pickups.PICKUPS:
            location = self.multiworld.get_location(name, self.player)
            self.assertEqual(location.parent_region.name, pickups.STAGE_OF[stage])

    def test_the_pool_grows_with_filler_only(self):
        mine = [i for i in self.multiworld.itempool if i.player == self.player]
        self.assertEqual(len(mine), 75 + len(pickups.PICKUPS))


class TestWithoutPickupsanity(MM8TestBase):
    options = {"pickupsanity": False}

    def test_no_pickup_locations(self):
        mine = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertFalse(mine & {name for _s, _r, _k, name in pickups.PICKUPS})


class TestRandomizeOptions(MM8TestBase):
    options = {"randomize_options": True}

    def test_it_rolls_and_still_fits(self):
        self.assertLessEqual(self.world.item_count(), self.world.location_count())
        for name in ("goal", "text_skip", "pickupsanity", "weapon_damage",
                     "boss_hp_randomization", "stage_unlocks"):
            self.assertIsNotNone(getattr(self.world.options, name).value, name)


class TestEverythingOn(MM8TestBase):
    options = {"stage_unlocks": True, "rematch_checks": True, "death_link": True,
               "pickupsanity": True, "weapon_damage": "chaotic", "boss_hp_randomization": "chaotic",
               "stage_music": True, "mega_man_palette": "gold"}

    def test_the_music_deal_is_made(self):
        self.assertIsNotNone(self.world.stage_music)
        for place, theme in self.world.stage_music.items():
            self.assertNotEqual(theme, music.VANILLA_MUSIC[place], place)


class TestMaxLife(MM8TestBase):
    options = {"max_life": 80}

    def test_it_rides_the_slot_data_and_the_disc(self):
        from .. import Rom
        self.assertEqual(self.world.fill_slot_data()["max_life"], 80)
        labels = [label for label, *_rest in Rom.seed_edits(self.world)]
        self.assertIn("max life: the teleport-in fill", labels)


class TestMaxLifeVanilla(MM8TestBase):
    def test_the_default_changes_nothing(self):
        from .. import Rom
        self.assertEqual(self.world.fill_slot_data()["max_life"], 40)
        self.assertFalse(any(label.startswith("max life") for label, *_r in Rom.seed_edits(self.world)))
