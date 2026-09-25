"""The BizHawk client, driven against a fake 2 MB MainRAM.

Every policy in client.py's docstring has a test here, and every refusal has
its control: the same RAM with the one condition flipped must act.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

import worlds._bizhawk as bizhawk
from NetUtils import ClientStatus
from worlds.LauncherComponents import components

from .. import client as mm8_client
from .. import disc, names
from ..client import MM8Client
from ..items import item_table
from ..locations import location_table

STAMP = 0x2468ACE1
ID_TO_ITEM = {data.code: name for name, data in item_table.items()}


class FakeRAM:
    def __init__(self) -> None:
        self.mem = bytearray(0x200000)

    def put(self, address: int, data: bytes) -> None:
        a = address - 0x80000000
        self.mem[a:a + len(data)] = data

    def get(self, address: int, n: int) -> bytes:
        a = address - 0x80000000
        return bytes(self.mem[a:a + n])

    async def read(self, _ctx, requests):
        return [bytes(self.mem[a:a + n]) for a, n, _domain in requests]

    async def guarded_write(self, _ctx, writes, guards):
        for a, data, _domain in guards:
            if bytes(self.mem[a:a + len(data)]) != bytes(data):
                return False
        for a, data, _domain in writes:
            self.mem[a:a + len(data)] = bytes(data)
        return True


def vanilla_ram() -> FakeRAM:
    """A running game on an UNPATCHED disc: the EXE resident, no AP block."""
    ram = FakeRAM()
    ram.put(0x80150848, b"BASLUS-00453")
    return ram


def patched_ram(stamp: int = STAMP) -> FakeRAM:
    """A running game on this seed's disc: the AP block header in place."""
    ram = FakeRAM()
    ram.put(disc.AP_BLOCK, disc.AP_SIGNATURE + disc.AP_VERSION.to_bytes(4, "little")
            + stamp.to_bytes(4, "little"))
    ram.put(0x80150848, b"BASLUS-00453")
    ram.put(0x8015E283, bytes([40]))              # HP
    ram.put(0x801C3370, bytes([2]))               # lives
    return ram


class FakeContext:
    def __init__(self, items: list[str] = (), checked: set[int] = frozenset(), goal: int = 0) -> None:
        self.server = object()
        self.bizhawk_ctx = object()
        self.slot_data = {"goal": goal, "bolt_bundle_size": 5, "seed_stamp": STAMP}
        self.checked_locations = set(checked)
        self.items_received = [SimpleNamespace(item=item_table[n].code) for n in items]
        self.item_names = SimpleNamespace(lookup_in_game=lambda code: ID_TO_ITEM.get(code, ""))
        self.sent_msgs = []

    async def send_msgs(self, msgs) -> None:
        self.sent_msgs.extend(msgs)

    def checks(self) -> set[str]:
        by_id = {v: k for k, v in location_table.items()}
        return {by_id[i] for m in self.sent_msgs if m["cmd"] == "LocationChecks" for i in m["locations"]}

    def goal_sent(self) -> bool:
        return any(m["cmd"] == "StatusUpdate" and m["status"] == ClientStatus.CLIENT_GOAL
                   for m in self.sent_msgs)


class ClientTest(unittest.IsolatedAsyncioTestCase):
    async def poll(self, ram: FakeRAM, ctx: FakeContext, client: MM8Client, times: int = 1) -> None:
        with mock.patch.object(mm8_client.bizhawk, "read", ram.read), \
                mock.patch.object(mm8_client.bizhawk, "guarded_write", ram.guarded_write):
            for _ in range(times):
                await client.game_watcher(ctx)

    @staticmethod
    def kill(ram: FakeRAM, boss: str) -> None:
        slot = names.WEAPON_SLOT[names.BOSS_WEAPON[boss]]
        ram.put(disc.WEAPONS + 4 * slot, b"\x01")


class TestRefusals(ClientTest):
    async def test_vanilla_disc_gets_nothing(self):
        ram = vanilla_ram()                                 # no AP block header
        self.kill(ram, names.FROST)
        ctx, client = FakeContext(["Ice Wave"]), MM8Client()
        await self.poll(ram, ctx, client, 3)
        self.assertEqual(ctx.sent_msgs, [])
        self.assertEqual([ram.get(disc.WEAPONS + 4 * s + 1, 1) for s in range(10)], [b"\x00"] * 10)

    async def test_another_seeds_disc_gets_nothing_and_the_control_does(self):
        for stamp, acts in ((0x11111111, False), (STAMP, True)):
            ram = patched_ram(stamp)
            self.kill(ram, names.FROST)
            ctx, client = FakeContext(["Ice Wave"]), MM8Client()
            await self.poll(ram, ctx, client, 3)
            self.assertEqual(names.boss_location(names.FROST) in ctx.checks(), acts, hex(stamp))

    async def test_the_attract_demo_is_not_play(self):
        """A demo swaps in its loadout - every boss beaten - so nothing may be
        read while its timer runs; the same RAM with the timer at 0 is the
        control."""
        ram = patched_ram()
        for boss in names.ROBOT_MASTERS:
            self.kill(ram, boss)
        ram.put(0x801B2944, (500).to_bytes(4, "little"))
        ctx, client = FakeContext(goal=1), MM8Client()
        await self.poll(ram, ctx, client, 3)
        self.assertEqual(ctx.sent_msgs, [])
        ram.put(0x801B2944, bytes(4))
        await self.poll(ram, ctx, client, 3)
        self.assertEqual(len(ctx.checks()), 8)
        self.assertTrue(ctx.goal_sent())

    async def test_a_swapped_weapon_array_is_not_trusted(self):
        """If the capability bytes do not read back as written, something
        replaced the whole entries (a demo, a savestate) - no checks that
        poll; the client re-asserts and trusts again once they hold."""
        ram = patched_ram()
        ctx, client = FakeContext(["Ice Wave"]), MM8Client()
        await self.poll(ram, ctx, client, 2)
        for slot in range(10):                              # a whole-entry swap
            ram.put(disc.WEAPONS + 4 * slot, b"\x01\x00\x00\x28")
        await self.poll(ram, ctx, client, 1)
        self.assertEqual(ctx.checks(), set())
        await self.poll(ram, ctx, client, 2)
        self.assertIn(names.boss_location(names.FROST), ctx.checks())


class TestTheRefusalMessage(ClientTest):
    """Seen live: four "not a disc patched" warnings for four harmless moments
    (a reboot's EXE still loading, savestates the ramwatch then repaired)."""

    async def test_a_moment_without_the_block_is_not_announced(self):
        ram, ctx, client = vanilla_ram(), FakeContext(), MM8Client()
        clock = [100.0]
        with mock.patch.object(mm8_client.time, "monotonic", lambda: clock[0]), \
                self.assertNoLogs("Client", level="WARNING"):
            await self.poll(ram, ctx, client, 3)
            clock[0] += mm8_client.REFUSAL_GRACE - 1
            await self.poll(ram, ctx, client, 1)
            ram.put(disc.AP_BLOCK, patched_ram().get(disc.AP_BLOCK, 12))   # the block arrives
            await self.poll(ram, ctx, client, 1)

    async def test_a_lasting_absence_is_announced_and_so_is_the_recovery(self):
        ram, ctx, client = vanilla_ram(), FakeContext(), MM8Client()
        clock = [100.0]
        with mock.patch.object(mm8_client.time, "monotonic", lambda: clock[0]):
            with self.assertLogs("Client", level="WARNING"):
                await self.poll(ram, ctx, client, 1)
                clock[0] += mm8_client.REFUSAL_GRACE + 1
                await self.poll(ram, ctx, client, 1)
            ram.put(disc.AP_BLOCK, patched_ram().get(disc.AP_BLOCK, 12))
            with self.assertLogs("Client", level="INFO") as got:
                await self.poll(ram, ctx, client, 1)
            self.assertIn("running again", got.output[0])

    async def test_a_booting_machine_is_left_alone(self):
        """Seen live: after a reset the ramwatch put the AP block back before
        the EXE had loaded, and the client wrote bolts and Rush into a machine
        still booting. With the game's own name absent, nothing happens -
        and the control: the same RAM with the EXE resident is acted on."""
        for resident in (False, True):
            ram = patched_ram()
            if not resident:
                ram.put(0x80150848, bytes(12))
            ctx, client = FakeContext(["Rush Bike", "Bolts"]), MM8Client()
            with self.assertNoLogs("Client", level="WARNING"):
                await self.poll(ram, ctx, client, 2)
            self.assertEqual(ram.get(0x8016D300, 1), bytes([1 if resident else 0]), resident)

    async def test_a_wrong_stamp_is_announced_at_once(self):
        with self.assertLogs("Client", level="WARNING"):
            await self.poll(patched_ram(0x11111111), FakeContext(), MM8Client(), 1)


class TestChecks(ClientTest):
    async def test_a_check_needs_two_identical_polls(self):
        ram = patched_ram()
        ctx, client = FakeContext(), MM8Client()
        await self.poll(ram, ctx, client, 1)
        self.kill(ram, names.GRENADE)
        await self.poll(ram, ctx, client, 1)
        self.assertEqual(ctx.checks(), set())
        await self.poll(ram, ctx, client, 1)
        self.assertEqual(ctx.checks(), {names.boss_location(names.GRENADE)})

    async def test_every_record_maps_to_its_location(self):
        ram = patched_ram()
        self.kill(ram, names.SEARCH)
        ram.put(disc.WEAPONS + 4 * 1, b"\x01")                        # Mega Ball
        field = (1 << 14) | (1 << 39)
        ram.put(0x8016D2FB, field.to_bytes(5, "little"))
        ram.put(disc.AP_RUSH + 2, b"\x01")                             # Bomber
        ram.put(disc.AP_LAB, (1 << names.PART_ID[names.LASER_SHOT]).to_bytes(4, "little"))
        ram.put(0x801C336C, bytes([4, 2]))                             # phase 4, 2 Wily clears
        ctx, client = FakeContext(), MM8Client()
        await self.poll(ram, ctx, client, 2)
        from ..bolts import BOLT_LOCATIONS
        self.assertEqual(ctx.checks(), {
            names.boss_location(names.SEARCH), names.MEGA_BALL_LOCATION,
            BOLT_LOCATIONS[14], BOLT_LOCATIONS[39],
            names.midboss_location(names.SWORD), names.shop_location(names.LASER_SHOT),
            names.DUO_CLEAR, names.WILY_CLEAR[names.WILY_1], names.WILY_CLEAR[names.WILY_2]})
        self.assertFalse(ctx.goal_sent())

    async def test_the_wily_goal(self):
        ram = patched_ram()
        ram.put(0x801C336C, bytes([5, 3]))
        ctx, client = FakeContext(), MM8Client()
        await self.poll(ram, ctx, client, 2)
        self.assertFalse(ctx.goal_sent())
        ram.put(0x801C336D, bytes([4]))
        await self.poll(ram, ctx, client, 2)
        self.assertTrue(ctx.goal_sent())


class TestGrants(ClientTest):
    async def test_weapons_are_capability_never_the_kill_record(self):
        ram = patched_ram()
        ctx, client = FakeContext(["Ice Wave", "Mega Ball"]), MM8Client()
        await self.poll(ram, ctx, client, 1)
        slot = names.WEAPON_SLOT[names.ICE_WAVE]
        self.assertEqual(ram.get(disc.WEAPONS + 4 * slot, 2), b"\x00\x01")
        self.assertEqual(ram.get(disc.WEAPONS + 4 * 1, 2), b"\x00\x01")
        self.assertEqual(ram.get(disc.WEAPONS, 2), b"\x00\x01")        # the buster
        self.assertEqual(ram.get(disc.WEAPONS + 4 * names.WEAPON_SLOT[names.FLAME_SWORD] + 1, 1), b"\x00")
        await self.poll(ram, ctx, client, 2)
        self.assertEqual(ctx.checks(), set(), "a grant must never read back as a check")

    async def test_bolts_are_what_was_sent_less_what_was_spent(self):
        ram = patched_ram()
        lab = (1 << names.PART_ID[names.POWER_SHIELD]) | (1 << names.PART_ID[names.EXIT])
        ram.put(disc.AP_LAB, lab.to_bytes(4, "little"))
        ctx, client = FakeContext(["Bolts"] * 3), MM8Client()
        await self.poll(ram, ctx, client, 1)
        spent = disc.LAB_PRICE[names.PART_ID[names.POWER_SHIELD]] + disc.LAB_PRICE[names.PART_ID[names.EXIT]]
        self.assertEqual(int.from_bytes(ram.get(0x8016D2F0, 2), "little"), 15 - spent)

    async def test_rush_parts_and_collected_rush(self):
        ram = patched_ram()
        checked = {location_table[names.midboss_location(names.AQUA)]}
        ctx, client = FakeContext(["Rush Bike", "Power Shield"], checked), MM8Client()
        await self.poll(ram, ctx, client, 1)
        self.assertEqual(ram.get(0x8016D300, 4), b"\x01\x00\x00\x00")
        self.assertEqual(ram.get(0x801C3352, 4), b"\x01\x00\x00\x00")
        self.assertEqual(int.from_bytes(ram.get(disc.AP_PARTS, 4), "little"),
                         1 << names.PART_ID[names.POWER_SHIELD])
        self.assertEqual(ram.get(disc.AP_RUSH, 4), b"\x00\x00\x00\x01", "Aqua's pickup: collected")
        # A used-up adapter (persistent 0, live 1) is the game's business.
        ram.put(0x801C3352, b"\x00")
        await self.poll(ram, ctx, client, 1)
        self.assertEqual(ram.get(0x801C3352, 1), b"\x00")

    async def test_a_weapon_in_hand_that_was_not_sent_goes_back_to_the_buster(self):
        """Seen live: the intro's pickup selected Mega Ball, and firing reads
        only the current weapon. The control: a weapon that WAS sent stays."""
        for items, stays in (([], False), (["Mega Ball"], True)):
            ram = patched_ram()
            ram.put(0x8016DC08, bytes([1]))                            # Mega Ball in hand
            ctx, client = FakeContext(items), MM8Client()
            await self.poll(ram, ctx, client, 1)
            self.assertEqual(ram.get(0x8016DC08, 1), bytes([1 if stays else 0]), items)

    async def test_a_part_works_at_once_and_an_unowned_shot_mode_is_reset(self):
        ram = patched_ram()
        ram.put(0x8016D2FA, bytes([2]))                               # Arrow selected...
        ctx, client = FakeContext(["Laser Shot", "Step Booster"]), MM8Client()
        await self.poll(ram, ctx, client, 1)
        self.assertEqual(ram.get(0x801C3340 + names.PART_ID[names.LASER_SHOT], 1), b"\x01")
        self.assertEqual(ram.get(0x801C3340 + names.PART_ID[names.STEP_BOOSTER], 1), b"\x01")
        self.assertEqual(ram.get(0x801C3340 + names.PART_ID[names.ARROW_SHOT], 1), b"\x00")
        self.assertEqual(ram.get(0x8016D2FA, 1), b"\x00", "...but Arrow Shot is not owned")
        ram.put(0x8016D2FA, bytes([1]))                               # Laser: owned
        await self.poll(ram, ctx, client, 1)
        self.assertEqual(ram.get(0x8016D2FA, 1), b"\x01")

    async def test_consumables_apply_once_in_a_stage_and_are_counted(self):
        ram = patched_ram()
        ram.put(0x8015E283, bytes([10]))
        items = ["Ice Wave", "1-Up", "Life Energy", "1-Up"]
        ctx, client = FakeContext(items), MM8Client()
        await self.poll(ram, ctx, client, 2)
        self.assertEqual(ram.get(0x801C3370, 1), bytes([2]), "not in a stage: nothing yet")
        ram.put(disc.OVL_BASE, (6).to_bytes(4, "little"))            # the intro stage
        await self.poll(ram, ctx, client, 3)
        self.assertEqual(ram.get(0x801C3370, 1), bytes([4]))
        self.assertEqual(ram.get(0x8015E283, 1), bytes([40]))
        self.assertEqual(int.from_bytes(ram.get(disc.AP_PROCESSED, 4), "little"), 4)

    async def test_a_heal_waits_out_a_death(self):
        ram = patched_ram()
        ram.put(disc.OVL_BASE, (6).to_bytes(4, "little"))
        ram.put(0x8015E283, bytes([0]))
        ctx, client = FakeContext(["Life Energy", "1-Up"]), MM8Client()
        await self.poll(ram, ctx, client, 2)
        self.assertEqual(ram.get(0x8015E283, 1), bytes([0]))
        self.assertEqual(int.from_bytes(ram.get(disc.AP_PROCESSED, 4), "little"), 0)


class TestRegistration(unittest.TestCase):
    """X5 v0.1.0 never registered its suffix, so Open Patch could not route
    the file and the player was never asked for their disc image."""

    def test_suffix_matches_the_patch_file(self):
        from ..Rom import MM8ProcedurePatch
        self.assertEqual(MM8Client.patch_suffix, MM8ProcedurePatch.patch_file_ending)

    def test_suffix_reaches_the_bizhawk_launcher_component(self):
        bizhawk_components = [c for c in components if c.script_name == "BizHawkClient"]
        self.assertTrue(bizhawk_components)
        self.assertIn(".apmm8", bizhawk_components[0].file_identifier.suffixes)
