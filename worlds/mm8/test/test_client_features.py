"""The client's option features - stage_unlocks, rematch_checks, death_link -
against the fake MainRAM of test_client. Each refusal has its control."""
from .. import names
from ..client import MM8Client
from .test_client import ClientTest, FakeContext, patched_ram

SELECT = 0x801379A8
GAMEMODE, GAMEMODE2 = 0x801CF840, 0x801CF844
PLAYER, HP = 0x8015E23C, 0x8015E283
NO_CONTROL, SECTION_END, PAUSED = 0x801B2993, 0x801B2995, 0x80170338
STAGE_INDEX, REFIGHTS, OVERLAY = 0x801C336E, 0x801C3378, 0x801D8000


class OptionContext(FakeContext):
    def __init__(self, items=(), **slot_data) -> None:
        super().__init__(list(items))
        self.slot_data.update(slot_data)
        self.tags: set[str] = set()
        self.slot = 1
        self.player_names = {1: "Tester"}
        self.deaths_sent: list[str] = []

    async def update_death_link(self, on: bool) -> None:
        if on:
            self.tags.add("DeathLink")

    async def send_death(self, text: str = "") -> None:
        self.deaths_sent.append(text)


def in_stage(stage: int = 1, overlay: int = 7):
    """A patched game with the player alive and in control in a stage."""
    ram = patched_ram()
    ram.put(SELECT, names.SELECT_TABLE_VANILLA)
    ram.put(GAMEMODE, bytes([3]))
    ram.put(GAMEMODE2, bytes([1]))
    ram.put(PLAYER, bytes([1, 2]))
    ram.put(STAGE_INDEX, bytes([stage]))
    ram.put(OVERLAY, overlay.to_bytes(4, "little"))
    return ram


class TestStageUnlocks(ClientTest):
    async def test_only_received_codes_open_a_stage(self):
        ram = in_stage()
        ctx = OptionContext([names.access_item(names.FROST)], stage_unlocks=1)
        await self.poll(ram, ctx, MM8Client())
        table = ram.get(SELECT, 12)
        for boss, pos in names.SELECT_POSITION.items():
            self.assertEqual(table[pos], 1 if boss == names.FROST else 0xFF, boss)
        for pos in (2, 3, 8, 9):                      # stage 0, the Lab, Duo, Wily
            self.assertEqual(table[pos], names.SELECT_TABLE_VANILLA[pos], pos)

    async def test_codes_arriving_later_open_the_stage(self):
        ram = in_stage()
        ctx, client = OptionContext([], stage_unlocks=1), MM8Client()
        await self.poll(ram, ctx, client)
        self.assertEqual(ram.get(SELECT + names.SELECT_POSITION[names.AQUA], 1), b"\xff")
        ctx.items_received = OptionContext([names.access_item(names.AQUA)]).items_received
        await self.poll(ram, ctx, client)
        self.assertEqual(ram.get(SELECT + names.SELECT_POSITION[names.AQUA], 1), b"\x06")

    async def test_off_means_untouched(self):
        ram = in_stage()
        await self.poll(ram, OptionContext([], stage_unlocks=0), MM8Client())
        self.assertEqual(ram.get(SELECT, 12), names.SELECT_TABLE_VANILLA)

    async def test_a_table_it_does_not_recognise_is_left_alone(self):
        for garbage, acts in ((b"\x07", False), (b"\xff", True)):
            ram = in_stage()
            ram.put(SELECT + 2, garbage)              # stage 0's position
            await self.poll(ram, OptionContext([], stage_unlocks=1), MM8Client())
            locked = ram.get(SELECT + names.SELECT_POSITION[names.FROST], 1) == b"\xff"
            self.assertEqual(locked, acts, garbage)


class TestRematches(ClientTest):
    async def test_a_won_refight_in_wily_4_sends_its_check(self):
        ram = in_stage(stage=13, overlay=0x13)
        ram.put(REFIGHTS, bytes([1 << names.REMATCH_BIT[names.GRENADE]]))
        ctx = OptionContext(rematch_checks=1)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertIn(names.rematch_location(names.GRENADE), ctx.checks())
        self.assertEqual(sum("Rematch" in c for c in ctx.checks()), 1)

    async def test_the_byte_is_scratch_anywhere_else(self):
        """Sword Man's stage uses 0x801C3378 for its own purposes."""
        ram = in_stage(stage=5, overlay=11)
        ram.put(REFIGHTS, b"\xff")
        ctx = OptionContext(rematch_checks=1)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertFalse(any("Rematch" in c for c in ctx.checks()))

    async def test_not_while_the_player_is_dead(self):
        for alive, acts in ((0, False), (1, True)):
            ram = in_stage(stage=13, overlay=0x13)
            ram.put(REFIGHTS, b"\x01")
            ram.put(PLAYER, bytes([alive, 2]))
            ctx = OptionContext(rematch_checks=1)
            await self.poll(ram, ctx, MM8Client(), 3)
            self.assertEqual(names.rematch_location(names.FROST) in ctx.checks(), acts, alive)

    async def test_off_sends_nothing(self):
        ram = in_stage(stage=13, overlay=0x13)
        ram.put(REFIGHTS, b"\xff")
        ctx = OptionContext(rematch_checks=0)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertFalse(any("Rematch" in c for c in ctx.checks()))


MAIN_ARRAY = 0x8015B174


class TestBass(ClientTest):
    """Wily 3's Bass: his defeat STATE (8 retreat, 10 parting words) is the
    check, since he is never killed and nothing is recorded."""

    def bass(self, top: int, obj_id: int = 0x5D, stage: int = 12, overlay: int = 0x12, slot: int = 3):
        ram = in_stage(stage=stage, overlay=overlay)
        ram.put(MAIN_ARRAY + 0x60 * slot, bytes([1, top, 0, 0, 0, 0, obj_id]))
        return ram

    async def sent(self, ram) -> bool:
        ctx = OptionContext()
        await self.poll(ram, ctx, MM8Client(), 3)
        return names.WILY_3_BASS in ctx.checks()

    async def test_each_defeat_state_sends_it(self):
        for top in (8, 10):
            self.assertTrue(await self.sent(self.bass(top)), top)

    async def test_the_controls_send_nothing(self):
        cases = {
            "still fighting (top state 1)": dict(top=1),
            "his intro (top state 9)": dict(top=9),
            "another object in state 8": dict(top=8, obj_id=0x4E),
            "the same bytes outside Wily 3": dict(top=8, stage=11, overlay=0x11),
        }
        for what, scene in cases.items():
            self.assertFalse(await self.sent(self.bass(**scene)), what)

    async def test_a_dead_slot_is_not_bass(self):
        ram = self.bass(8)
        ram.put(MAIN_ARRAY + 0x60 * 3, b"\x00")                    # the slot is free
        self.assertFalse(await self.sent(ram))


class TestDeathLink(ClientTest):
    @staticmethod
    def die(ram) -> None:
        ram.put(HP, b"\x00")
        ram.put(PLAYER, bytes([0, 3]))
        ram.put(GAMEMODE2, bytes([2]))

    @staticmethod
    def respawn(ram) -> None:
        ram.put(HP, bytes([40]))
        ram.put(PLAYER, bytes([1, 2]))
        ram.put(GAMEMODE2, bytes([1]))

    async def test_one_death_sends_once_and_rearms_only_when_alive(self):
        ram = in_stage()
        ctx, client = OptionContext(death_link=1), MM8Client()
        await self.poll(ram, ctx, client)                 # seen alive: armed
        self.assertIn("DeathLink", ctx.tags)
        self.die(ram)
        await self.poll(ram, ctx, client, 4)
        self.assertEqual(len(ctx.deaths_sent), 1)
        self.respawn(ram)
        await self.poll(ram, ctx, client)
        self.die(ram)
        await self.poll(ram, ctx, client, 2)
        self.assertEqual(len(ctx.deaths_sent), 2)

    async def test_attaching_mid_death_sends_nothing(self):
        ram = in_stage()
        self.die(ram)
        ctx = OptionContext(death_link=1)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertEqual(ctx.deaths_sent, [])

    async def test_a_received_death_kills_and_does_not_bounce(self):
        ram = in_stage()
        ctx, client = OptionContext(death_link=1), MM8Client()
        await self.poll(ram, ctx, client)
        client.on_package(ctx, "Bounced", {"tags": ["DeathLink"], "data": {"source": "Other"}})
        await self.poll(ram, ctx, client)
        self.assertEqual(ram.get(HP, 1), b"\x00")
        self.die(ram)                                     # the game runs the death
        await self.poll(ram, ctx, client, 3)
        self.assertEqual(ctx.deaths_sent, [])

    async def test_its_own_bounce_is_ignored(self):
        ram = in_stage()
        ctx, client = OptionContext(death_link=1), MM8Client()
        client.on_package(ctx, "Bounced", {"tags": ["DeathLink"], "data": {"source": "Tester"}})
        await self.poll(ram, ctx, client)
        self.assertEqual(ram.get(HP, 1), bytes([40]))

    async def test_held_through_transients_then_applied(self):
        """Paused, teleporting in (HP refills), held by a boss intro, not in
        control, a section end pending: each holds the death; clearing it
        lets the kill land. Each case is its own control."""
        for where, value, clear in ((PAUSED, b"\x01", b"\x00"),
                                    (PLAYER, bytes([1, 1]), bytes([1, 2])),
                                    (PLAYER, bytes([1, 4]), bytes([1, 2])),
                                    (NO_CONTROL, b"\x01", b"\x00"),
                                    (SECTION_END, b"\x02", b"\x00")):
            ram = in_stage()
            ctx, client = OptionContext(death_link=1), MM8Client()
            ram.put(where, value)
            client.on_package(ctx, "Bounced", {"tags": ["DeathLink"], "data": {"source": "Other"}})
            await self.poll(ram, ctx, client, 2)
            self.assertEqual(ram.get(HP, 1), bytes([40]), hex(where))
            self.assertTrue(client.pending_death_link, hex(where))
            ram.put(where, clear)
            await self.poll(ram, ctx, client)
            self.assertEqual(ram.get(HP, 1), b"\x00", hex(where))

    async def test_dropped_outside_a_stage(self):
        ram = in_stage()
        ram.put(GAMEMODE, bytes([2]))                     # the stage select
        ctx, client = OptionContext(death_link=1), MM8Client()
        client.on_package(ctx, "Bounced", {"tags": ["DeathLink"], "data": {"source": "Other"}})
        await self.poll(ram, ctx, client)
        self.assertFalse(client.pending_death_link)
        ram.put(GAMEMODE, bytes([3]))
        await self.poll(ram, ctx, client)
        self.assertEqual(ram.get(HP, 1), bytes([40]), "not carried into the next stage")

    async def test_off_means_no_tag_and_no_kill(self):
        ram = in_stage()
        ctx, client = OptionContext(death_link=0), MM8Client()
        client.on_package(ctx, "Bounced", {"tags": ["DeathLink"], "data": {"source": "Other"}})
        await self.poll(ram, ctx, client)
        self.assertNotIn("DeathLink", ctx.tags)
        self.assertEqual(ram.get(HP, 1), bytes([40]))
