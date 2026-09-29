"""The part descriptions (client._describe_parts) through the REAL pipeline:
MultiServer's own Connect / register_location_checks / send_new_items / Sync /
ConnectUpdate, every message JSON-encoded as it goes over the wire, and the
real CommonClient.process_server_cmd -> BizHawkClientContext.on_package ->
MM8Client, one websocket frame at a time. No sockets, no processes.

Why the real pipeline: 0.2.0 as first built stayed silent on any batch
numbered from 0, taking it for a login's resend - and a unit test fed that same
assumption agreed with it. The server also numbers a slot's first-ever items
from 0 when the login brought none, which is every fresh default seed (0.2.0
review m1; this harness is the reviewer's, which found it).
"""
import asyncio
import copy
import logging
import unittest
from types import SimpleNamespace
from unittest import mock

import CommonClient
import MultiServer
import NetUtils
import worlds
from NetUtils import NetworkSlot, SlotType
from worlds._bizhawk.context import BizHawkClientContext

from .. import names
from ..client import MM8Client
from ..items import item_table
from ..locations import location_table

GAME = "Mega Man 8"
PROGRESSION, USEFUL, FILLER = 0b001, 0b010, 0
LOCS = sorted(location_table.values())
# MultiServer.Context deletes the groups from the data package it loads, so each
# one gets its own copy of the untouched package.
PRISTINE_PACKAGE = copy.deepcopy(worlds.network_data_package)


def code(name: str) -> int:
    return item_table[name].code


class ServerSocket:
    """The server's end of one client's websocket: each send is one frame."""
    def __init__(self) -> None:
        self.open, self.closed, self.extensions = True, False, []
        self.inbox: list[list[dict]] = []

    async def send(self, text) -> None:
        self.inbox.append(list(NetUtils.decode(text)))


class ClientSocket:
    def __init__(self) -> None:
        self.open, self.closed = True, False
        self.outbox: list[dict] = []

    async def send(self, text) -> None:
        self.outbox.extend(NetUtils.decode(text))


def broadcast(sockets, msg) -> None:
    for sock in sockets:
        sock.inbox.append(list(NetUtils.decode(msg)))


class Rig:
    """One real server Context (a hand-built one-player multidata), one
    BizHawk client context, one MM8Client."""

    def __init__(self, placements: dict[int, tuple[str, int]], precollected=(), slot_data=None) -> None:
        with mock.patch.object(worlds, "network_data_package", copy.deepcopy(PRISTINE_PACKAGE)):
            self.server = MultiServer.Context("localhost", 0, None, None, 1, 10, False)
        self.server.logger = logging.getLogger("mm8-test-server")
        self.server.logger.setLevel(logging.CRITICAL)
        self.server._load({
            "minimum_versions": {"server": (0, 0, 0), "clients": {1: (0, 5, 0)}},
            "version": (0, 6, 3),
            "slot_info": {1: NetworkSlot("P1", GAME, SlotType.player)},
            "seed_name": "mm8test",
            "connect_names": {"P1": (0, 1)},
            "locations": {1: {loc: (code(item), 1, flags) for loc, (item, flags) in placements.items()}},
            "slot_data": {1: slot_data if slot_data is not None else {"seed_stamp": 1}},
            "er_hint_data": {},
            "precollected_items": {1: [code(n) for n in precollected]},
            "precollected_hints": {1: set()},
            "datapackage": {},
        }, {}, False)
        self.handler = MM8Client()
        self.ctx = BizHawkClientContext(None, None)
        self.ctx.server_address = "localhost:38281"
        self.ctx.game = GAME
        self.ctx.items_handling = 0b111
        self.ctx.client_handler = self.handler

    async def connect(self) -> None:
        """A fresh websocket and a Connect, as CommonClient sends it."""
        self.ctx.reset_server_state()
        self.ssock, self.csock = ServerSocket(), ClientSocket()
        self.ctx.server = SimpleNamespace(socket=self.csock)
        self.sclient = MultiServer.Client(self.ssock, self.server)
        await MultiServer.process_client_cmd(self.server, self.sclient, {
            "cmd": "Connect", "password": None, "name": "P1", "version": NetUtils.Version(0, 6, 3),
            "tags": ["AP"], "items_handling": 0b111, "uuid": 1, "game": GAME, "slot_data": True})
        await self.pump()

    async def pump(self) -> None:
        """Deliver what the server sent, frame by frame, the way
        CommonClient.server_loop does; send the client's replies back."""
        for _ in range(5):
            await asyncio.sleep(0)
        while self.ssock.inbox:
            for msg in self.ssock.inbox.pop(0):
                await CommonClient.process_server_cmd(self.ctx, msg)
            for _ in range(3):
                await asyncio.sleep(0)
            while self.csock.outbox:
                out = self.csock.outbox.pop(0)
                if out["cmd"] in ("Sync", "ConnectUpdate", "LocationChecks"):
                    await MultiServer.process_client_cmd(self.server, self.sclient, out)
                for _ in range(5):
                    await asyncio.sleep(0)

    async def check(self, *locations: int) -> None:
        MultiServer.register_location_checks(self.server, 0, 1, list(locations))
        await self.pump()

    def check_offline(self, *locations: int) -> None:
        MultiServer.register_location_checks(self.server, 0, 1, list(locations))


class TestPartDescriptions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.patches = [mock.patch.object(CommonClient.Utils, "persistent_store", lambda *a, **k: None),
                        mock.patch.object(MultiServer.websockets, "broadcast", broadcast)]
        for patch in self.patches:
            patch.start()

    async def asyncTearDown(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()

    async def described(self, coroutine) -> list[str]:
        """The part lines logged while `coroutine` runs."""
        with self.assertLogs(None, level="INFO") as logs:
            logging.getLogger("Client").info("-- start --")
            await coroutine
        return [line.split("Client:", 1)[1] for line in logs.output if "Client:Mega Man 8:" in line]

    async def test_the_first_part_after_an_empty_login(self):
        """The defect: nothing received before, so the login brings no batch
        and the part arrives as index 0. It is described."""
        rig = Rig({LOCS[0]: (names.BOOST_PART, USEFUL)})
        await rig.connect()
        self.assertEqual(await self.described(rig.check(LOCS[0])), ["Mega Man 8: Boost Part - faster shots"])

    async def test_a_first_batch_of_several_parts(self):
        rig = Rig({LOCS[0]: (names.BOOST_PART, USEFUL), LOCS[1]: (names.EXIT, USEFUL),
                   LOCS[2]: (names.RAPID_PART, USEFUL)}, slot_data={"seed_stamp": 1, "exit_stage_anytime": 0})
        await rig.connect()
        self.assertEqual(sorted(await self.described(rig.check(*LOCS[:3]))),
                         ["Mega Man 8: Boost Part - faster shots",
                          f"Mega Man 8: Exit - {names.PART_EFFECT_SHORT[names.EXIT]}",
                          "Mega Man 8: Rapid Part - 3-shot bursts"])

    async def test_after_a_login_that_brought_items(self):
        rig = Rig({LOCS[0]: (names.BOLTS, PROGRESSION), LOCS[1]: (names.BOOST_PART, USEFUL)})
        rig.check_offline(LOCS[0])
        await rig.connect()
        self.assertEqual(await self.described(rig.check(LOCS[1])), ["Mega Man 8: Boost Part - faster shots"])

    async def test_a_reconnect_says_nothing(self):
        # The control for all of the above: the same parts, owned at a login.
        rig = Rig({LOCS[0]: (names.BOLTS, PROGRESSION), LOCS[1]: (names.BOOST_PART, USEFUL)})
        rig.check_offline(LOCS[0])
        await rig.connect()
        await rig.check(LOCS[1])
        self.assertEqual(await self.described(rig.connect()), [])

    async def test_a_login_holding_only_parts_says_nothing(self):
        rig = Rig({LOCS[0]: (names.BOOST_PART, USEFUL)})
        rig.check_offline(LOCS[0])
        self.assertEqual(await self.described(rig.connect()), [])

    async def test_a_sync_and_an_items_handling_change_say_nothing(self):
        rig = Rig({LOCS[0]: (names.BOLTS, PROGRESSION), LOCS[1]: (names.BOOST_PART, USEFUL)})
        rig.check_offline(LOCS[0])
        await rig.connect()
        await rig.check(LOCS[1])

        async def resends():
            await MultiServer.process_client_cmd(rig.server, rig.sclient, {"cmd": "Sync"})
            await rig.pump()
            await MultiServer.process_client_cmd(rig.server, rig.sclient,
                                                 {"cmd": "ConnectUpdate", "items_handling": 0b011})
            await rig.pump()
        self.assertEqual(await self.described(resends()), [])

    async def test_a_starting_part_says_nothing(self):
        rig = Rig({LOCS[0]: (names.BOLTS, PROGRESSION)}, precollected=[names.EXIT])
        self.assertEqual(await self.described(rig.connect()), [])

    async def test_a_duplicate_batch_is_not_described_twice(self):
        rig = Rig({LOCS[0]: (names.BOLTS, PROGRESSION), LOCS[1]: (names.BOOST_PART, USEFUL)})
        rig.check_offline(LOCS[0])
        await rig.connect()
        await rig.check(LOCS[1])
        rig.ssock.inbox.append([{"cmd": "ReceivedItems", "index": 1,
                                 "items": [NetUtils.NetworkItem(code(names.BOOST_PART), LOCS[1], 1, USEFUL)]}])
        self.assertEqual(await self.described(rig.pump()), [])

    async def test_a_disc_reload_does_not_make_owned_parts_new(self):
        """validate_rom resets the game-side state on every disc (re)load;
        the parts baseline is the server session's, not the disc's."""
        rig = Rig({LOCS[0]: (names.BOLTS, PROGRESSION), LOCS[1]: (names.BOOST_PART, USEFUL),
                   LOCS[2]: (names.RAPID_PART, USEFUL)})
        rig.check_offline(LOCS[0], LOCS[1])
        await rig.connect()
        rig.handler._reset()
        self.assertEqual(await self.described(rig.check(LOCS[2])), ["Mega Man 8: Rapid Part - 3-shot bursts"])

    async def test_only_parts_are_described(self):
        rig = Rig({LOCS[0]: (names.FLAME_SWORD, PROGRESSION), LOCS[1]: (names.RUSH_BIKE, PROGRESSION),
                   LOCS[2]: (names.BOLTS, PROGRESSION), LOCS[3]: (names.EXTRA_LIFE, FILLER)})
        await rig.connect()
        self.assertEqual(await self.described(rig.check(*LOCS[:4])), [])

    async def test_exit_says_when_the_option_makes_it_moot(self):
        for option, flags, line in ((0, USEFUL, names.PART_EFFECT_SHORT[names.EXIT]),
                                    (1, FILLER, names.EXIT_EFFECT_WITH_OPTION_SHORT),
                                    # A 0.1.0 seed's slot data has no key (review m2):
                                    # the item's classification says it - the option
                                    # makes Exit filler.
                                    (None, FILLER, names.EXIT_EFFECT_WITH_OPTION_SHORT),
                                    (None, USEFUL, names.PART_EFFECT_SHORT[names.EXIT])):
            slot_data = {"seed_stamp": 1} if option is None else {"seed_stamp": 1, "exit_stage_anytime": option}
            rig = Rig({LOCS[0]: (names.EXIT, flags)}, slot_data=slot_data)
            await rig.connect()
            with self.subTest(option=option, flags=flags):
                self.assertEqual(await self.described(rig.check(LOCS[0])), [f"Mega Man 8: Exit - {line}"])


class TestPartLines(unittest.TestCase):
    def test_every_part_has_both_lines_and_the_short_one_is_short(self):
        for part in names.PARTS:
            self.assertIn(part, names.PART_EFFECT)
            self.assertLessEqual(len(names.PART_EFFECT_SHORT[part].split()), 4, part)
