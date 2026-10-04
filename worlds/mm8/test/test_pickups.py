"""pickupsanity: the stub EXECUTED on the R3000, its table and hooks, the
location list against the disc's own spawn lists, and the client."""
import struct
import unittest

from BaseClasses import CollectionState

from . import MM8TestBase
from .. import bolts, disc, mips, names, pickups
from ..client import MM8Client
from ..locations import location_table
from .r3000 import R3000
from .test_client import ClientTest, patched_ram
from .test_client_features import OptionContext, in_stage
from .test_disc import TRACK1, have_dump

CONTACT = disc.PICKUP_CONTACT
DELETE = 0x80105864
OBJ = 0x801B1EEC                 # an item-array slot
FOUND, CONFIRMED = disc.AP_PICKUP_FOUND, disc.AP_PICKUP_CONFIRMED


def record_address(record: int) -> int:
    return pickups.SPAWN_LIST + 8 * record


class TestStub(unittest.TestCase):
    """Each case sets the scene the stub meets at a pickup's contact call."""

    def run_stub(self, touched: bool = True, record: int | None = 14, stage: int = 1,
                 rec_id: int = 0, rec_type: int = 2, demo: int = 0, confirmed: int = 0) -> R3000:
        at = disc.routine_addresses()["pickupsanity"]
        m = R3000()
        m.load_code(at, mips.assemble(disc.PICKUP_STUB, at))
        # The contact test answers as told; DeleteObject marks that it ran.
        m.load_code(CONTACT, mips.assemble(f"jr ra\nori v0, zero, {int(touched)}", CONTACT))
        m.load_code(DELETE, mips.assemble("jr ra\nori t8, zero, 1", DELETE))
        table = disc.pickup_key_table(pickups.KEYS)
        for i, b in enumerate(table):
            m.write(disc.PICKUP_KEYS + i, b, 1)
        if record is not None:
            m.write(OBJ + 8, record_address(record), 4)
            m.write(record_address(record) + 1, rec_id, 1)
            m.write(record_address(record) + 3, rec_type, 1)
        m.write(0x801C336E, stage, 1)
        m.write(0x801B2944, demo, 4)
        m.write(CONFIRMED, confirmed, 8)
        m.r[4] = OBJ                      # a0 = the pickup
        m.r[29] = 0x801FF000              # sp
        m.r[16] = 0x5AFE                  # s0, which the caller relies on
        m.run(at)
        return m

    def outcome(self, m: R3000) -> tuple[int, int, bool]:
        """(v0 returned, FOUND word, DeleteObject called)."""
        return m.r[2], m.read(FOUND, 8), m.r[24] == 1

    def test_not_touched(self):
        self.assertEqual(self.outcome(self.run_stub(touched=False)), (0, 0, False))

    def test_an_unconfirmed_location_is_consumed_and_recorded(self):
        bit = pickups.KEYS.index(pickups.key(1, 14))
        v0, found, deleted = self.outcome(self.run_stub())
        self.assertEqual((v0, found, deleted), (0, 1 << bit, True))

    def test_the_last_placed_location_uses_the_high_word(self):
        bit = max(i for i, (s, r, _k, _n) in enumerate(pickups.PICKUPS) if (s, r) not in pickups.CONTAINERS)
        stage, record, _k, _n = pickups.PICKUPS[bit]
        m = self.run_stub(stage=stage, record=record)
        self.assertEqual(self.outcome(m), (0, 1 << bit, True))

    def test_the_ice_block_s_capsule_is_recorded_by_the_block_s_record(self):
        """0.2.1: the capsule carries the block's record (FROST_BLOCK_DROP) -
        a main-array record, id 12 (the dump test reads it off the disc)."""
        bit = pickups.KEYS.index(pickups.key(1, 158))
        self.assertEqual(bit, len(pickups.PICKUPS) - 1)
        m = self.run_stub(stage=1, record=158, rec_id=12, rec_type=1)
        self.assertEqual(self.outcome(m), (0, 1 << bit, True))
        self.assertEqual(self.outcome(self.run_stub(stage=1, record=158, rec_id=12, rec_type=1,
                                                    confirmed=1 << bit)), (1, 0, False), "confirmed")

    def test_a_container_key_matches_no_other_record(self):
        """The controls: the flag keeps the two kinds of key apart."""
        cases = {
            "record 158 as a placed consumable": dict(stage=1, record=158),
            "a block record in another stage": dict(stage=2, record=158, rec_id=12, rec_type=1),
            "another Frost block": dict(stage=1, record=148, rec_id=12, rec_type=1),
            "a placed capsule's record seen as not id 0": dict(stage=1, record=14, rec_id=12, rec_type=1),
        }
        for what, scene in cases.items():
            self.assertEqual(self.outcome(self.run_stub(**scene)), (1, 0, False), what)

    def test_the_cases_that_stay_vanilla(self):
        """Each returns the contact test's answer (1) untouched: the caller
        grants as vanilla, nothing recorded, nothing deleted by the stub."""
        bit = pickups.KEYS.index(pickups.key(1, 14))
        cases = {
            "an enemy drop": dict(record=None),
            "the attract demo": dict(demo=300),
            "not an id-0 record": dict(rec_id=37),
            "not an item record": dict(rec_type=0),
            "the same record in a stage where it is not a location": dict(stage=2),
            "confirmed by the server": dict(confirmed=1 << bit),
            "the intro's record index in Duo's stage": dict(stage=9, record=19),
        }
        for what, scene in cases.items():
            self.assertEqual(self.outcome(self.run_stub(**scene)), (1, 0, False), what)

    def test_the_intro_and_the_wily_stages_record_too(self):
        """Appended 2026-09-25: the intro replays and the Wily stages come
        back, so their capsules are locations - high bits included."""
        for stage, record in ((0, 19), (10, 60), (12, 47)):
            bit = pickups.KEYS.index(pickups.key(stage, record))
            self.assertEqual(self.outcome(self.run_stub(stage=stage, record=record)),
                             (0, 1 << bit, True), (stage, record))

    def test_callee_saved_registers_survive(self):
        m = self.run_stub()
        self.assertEqual(m.r[16], 0x5AFE)
        self.assertEqual(m.r[29], 0x801FF000)


class TestTables(unittest.TestCase):
    def test_keys_are_unique_and_fit(self):
        self.assertEqual(len(set(pickups.KEYS)), len(pickups.KEYS))
        self.assertLessEqual(len(pickups.KEYS), 64)          # a u64 of bits
        table = disc.pickup_key_table(pickups.KEYS)
        self.assertEqual(table[-2:], b"\xff\xff")

    def test_location_ids_follow_the_bits(self):
        for bit, (_s, _r, _k, name) in enumerate(pickups.PICKUPS):
            self.assertEqual(location_table[name] - location_table[pickups.PICKUPS[0][3]], bit)

    def test_ids_are_append_only(self):
        """The first 35 bits are the Robot Master stages' capsules, as they
        were when the option first shipped in a build; the intro's and the
        Wily stages' came after them (location ids follow the bits)."""
        rm = {names.STAGE_INDEX[b] for b in names.ROBOT_MASTERS}
        self.assertTrue(all(s in rm for s, _r, _k, _n in pickups.PICKUPS[:35]))
        self.assertEqual([(s, r) for s, r, _k, _n in pickups.PICKUPS[35:]],
                         [(0, 19), (10, 59), (10, 60), (11, 69), (12, 34), (12, 44), (12, 47),
                          (1, 158)])
        self.assertEqual(location_table[pickups.PICKUPS[34][3]] - location_table[pickups.PICKUPS[0][3]], 34)

    def test_the_key_table_stays_beside_the_ap_block(self):
        self.assertEqual(disc.PICKUP_KEYS, disc.AP_BLOCK + disc.AP_BLOCK_SIZE)
        self.assertLessEqual(disc.PICKUP_KEYS + disc.PICKUP_KEYS_ROOM, 0x801D3000)   # the image's end


# Stage packs (LBA, size) from the disc's own ISO directory (mm8_extract.py).
STAGE_PACKS = {
    0x00: [(134608, 581632)], 0x01: [(134892, 854016)],
    0x02: [(135309, 622592), (135613, 770048)], 0x03: [(135989, 561152), (136263, 743424)],
    0x04: [(136626, 667648), (136952, 688128)], 0x05: [(137288, 688128), (137624, 741376)],
    0x06: [(137986, 667648), (138312, 794624)], 0x07: [(138700, 591872), (138989, 694272)],
    0x08: [(139328, 651264), (139646, 757760)], 0x09: [(140016, 595968)],
    0x0A: [(140307, 681984)], 0x0B: [(140640, 649216)], 0x0C: [(140957, 727040)],
    0x0D: [(141312, 751616)],
}


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestAgainstTheDump(unittest.TestCase):
    track1: bytes

    @classmethod
    def setUpClass(cls):
        with open(TRACK1, "rb") as f:
            cls.track1 = f.read()

    def pack(self, lba: int, size: int) -> bytes:
        return b"".join(self.track1[(lba + s) * disc.SECTOR_RAW + disc.USER_OFF:
                                    (lba + s) * disc.SECTOR_RAW + disc.USER_OFF + disc.USER_LEN]
                        for s in range((size + disc.USER_LEN - 1) // disc.USER_LEN))[:size]

    def spawn_list(self, data: bytes) -> list[tuple[int, int, int, int]]:
        """Chunk 0xA: {flags, id, subId, type, x, y}; type 0xFF ends it."""
        count = struct.unpack_from("<I", data, 0)[0]
        off = 0x800
        for i in range(count):
            ctype, size = struct.unpack_from("<II", data, 8 + 8 * i)
            if ctype == 0xA:
                out = []
                for r in range(0, size, 8):
                    _f, oid, sub, typ = data[off + r:off + r + 4]
                    if typ == 0xFF:
                        break
                    out.append((r // 8, oid, sub, typ))
                return out
            off += (size + 0x7FF) & ~0x7FF
        raise AssertionError("no spawn list")

    def test_every_placed_consumable_is_accounted_for(self):
        """The disc's own lists hold exactly PICKUPS + NOT_LOCATIONS, with the
        kinds PICKUPS says - and an A pack and its B pack always agree."""
        placed: dict[tuple[int, int], int] = {}
        for stage, packs in STAGE_PACKS.items():
            lists = [self.spawn_list(self.pack(lba, size)) for lba, size in packs]
            self.assertTrue(all(lst == lists[0] for lst in lists), stage)
            for record, oid, sub, typ in lists[0]:
                if oid == 0 and typ == 2:
                    placed[(stage, record)] = sub
        ours = {(s, r): k for s, r, k, _n in pickups.PICKUPS if (s, r) not in pickups.CONTAINERS}
        self.assertEqual(set(placed), set(ours) | set(pickups.NOT_LOCATIONS))
        for where, kind in ours.items():
            self.assertEqual(placed[where], kind, where)

    def test_the_ice_block_is_what_the_research_read(self):
        """Record 158 of Frost Man's list is main id 12 with subId 5 at
        (3890, 4704); the block's drop table gives type 5 a Large Life Energy
        (1) - the kind PICKUPS gives it - and the drop's code is what
        FROST_BLOCK_DROP was written against (ram-notes 12d)."""
        (lba, size), = STAGE_PACKS[1]
        data = self.pack(lba, size)
        count = struct.unpack_from("<I", data, 0)[0]
        off = 0x800
        for i in range(count):
            ctype, csize = struct.unpack_from("<II", data, 8 + 8 * i)
            if ctype == 0xA:
                break
            off += (csize + 0x7FF) & ~0x7FF
        _f, oid, sub, typ, x, y = struct.unpack_from("<BBBBhh", data, off + 8 * 158)
        self.assertEqual((oid, sub, typ, x, y), (12, 5, 1, 3890, 4704))

        def ovl(address: int, n: int) -> bytes:
            return bytes(self.track1[disc.addr_to_disc(address + i, "ovl:STAGE01")] for i in range(n))
        self.assertEqual(ovl(0x801E68C4, 8)[sub & 0xF], 1)
        self.assertEqual({(s, r): k for s, r, k, _n in pickups.PICKUPS}[(1, 158)], 1)
        self.assertEqual(ovl(0x801DC740, 4), (0x0C0415BD).to_bytes(4, "little"))     # jal ITEMALLOC
        self.assertEqual(ovl(0x801DC768, 4), (0x902268C4).to_bytes(4, "little"))     # lbu v0, table(at)
        self.assertEqual(ovl(0x801DC774, 4), (0x9602000E).to_bytes(4, "little"))     # lhu v0, 14(s0)

    def test_the_hooks_and_the_table_land_on_what_the_research_read(self):
        edits = disc.pickup_edits(pickups.KEYS)
        for label, where, region, vanilla, _payload in edits:
            got = bytes(self.track1[disc.addr_to_disc(where + i, region)] for i in range(len(vanilla)))
            self.assertEqual(got, vanilla, label)
        disc.apply_edits(self.track1, list(disc.BASE_EDITS) + disc.routine_edits(self.track1)
                         + disc.ap_block_edits(1) + edits)


@unittest.skipUnless(have_dump, "vanilla Mega Man 8 dump not present")
class TestIceBlockDropExecuted(unittest.TestCase):
    """The ice block's drop (STAGE01 0x801DC6F4), executed on the test R3000
    as a player's disc has it - built through Rom.seed_edits with pickupsanity
    on and off, so FROST_BLOCK_DROP dropped from pickup_edits fails here. The
    item allocator is stubbed to hand out a freed slot (+8 = 0, as
    DeleteObject leaves it). Only the routine's words and its table are kept,
    not the discs."""
    DROP, DROP_END, TABLE = 0x801DC6F4, 0x801DC7EC, 0x801E68C4
    ALLOC = 0x801056F4
    BLOCK, SLOT = 0x8015B174, 0x801B1EEC          # a main-array object, an item-array slot
    RECORD = pickups.SPAWN_LIST + 8 * 158

    @classmethod
    def setUpClass(cls):
        from .. import Rom
        from .test_options_disc import fake_world
        with open(TRACK1, "rb") as f:
            track1 = f.read()
        cls.code = {}
        for on in (0, 1):
            image = disc.apply_edits(track1, Rom.seed_edits(fake_world(pickupsanity=on)))

            def read(address: int, n: int, image=image) -> bytes:
                return bytes(image[disc.addr_to_disc(address + i, "ovl:STAGE01")] for i in range(n))
            cls.code[on] = ([int.from_bytes(read(a, 4), "little") for a in range(cls.DROP, cls.DROP_END + 4, 4)],
                            read(cls.TABLE, 8))
            del image

    def drop(self, on: int, block_type: int) -> R3000:
        words, table = self.code[on]
        m = R3000()
        m.load_code(self.DROP, words)
        for i, b in enumerate(table):
            m.write(self.TABLE + i, b, 1)
        m.load_code(self.ALLOC, mips.assemble(
            f"lui v0, {self.SLOT >> 16:#x}\njr ra\nori v0, v0, {self.SLOT & 0xFFFF:#x}", self.ALLOC))
        m.write(self.BLOCK + 7, block_type, 1)
        m.write(self.BLOCK + 8, self.RECORD, 4)
        m.write(self.BLOCK + 0x0E, 3890, 2)
        m.write(self.BLOCK + 0x12, 4704, 2)
        m.r[4] = self.BLOCK
        m.r[29] = 0x801FF000
        m.run(self.DROP)
        return m

    def test_with_the_option_the_capsule_carries_the_block_s_record(self):
        m = self.drop(1, 5)
        self.assertEqual((m.read(self.SLOT, 1), m.read(self.SLOT + 6, 1), m.read(self.SLOT + 7, 1)), (1, 0, 1))
        self.assertEqual(m.read(self.SLOT + 8, 4), self.RECORD)
        self.assertEqual((m.read(self.SLOT + 0x0E, 2), m.read(self.SLOT + 0x12, 2)), (3894, 4704))
        self.assertEqual(m.r[29], 0x801FF000)

    def test_without_it_the_drop_is_the_game_s(self):
        """The control: an enemy drop's +8 = 0, falling and timing out."""
        m = self.drop(0, 5)
        self.assertEqual((m.read(self.SLOT, 1), m.read(self.SLOT + 7, 1)), (1, 1))
        self.assertEqual(m.read(self.SLOT + 8, 4), 0)

    def test_a_block_type_with_no_drop_spawns_nothing(self):
        self.assertEqual(self.drop(1, 3).read(self.SLOT, 1), 0)


class TestGates(MM8TestBase):
    """Each capsule's own rule (pickups.REQUIREMENT, 0.2.1), on the
    location's rule apart from its stage's entrance."""
    options = {"pickupsanity": True}

    def rule(self, name: str):
        return self.multiworld.get_location(name, self.player).access_rule

    # Every capsule that needs something, as research repo plan
    # 2026-10-03_per-bolt-logic.md section 4 tables it - a fixed copy, so a
    # rule dropped from pickups.REQUIREMENT fails here (the 0.2.1 review).
    EXPECTED = {
        "Frost Man - Large Life Energy 2": [{"Mega Ball"}],
        "Frost Man - Large Life Energy 3": [{"Mega Ball"}],
        "Frost Man - Large Life Energy 5": [{"Astro Crush"}],
        "Grenade Man - Large Life Energy 1": [{"Mega Ball"}, {"Flame Sword"}],
        "Aqua Man - Large Weapon Energy 1": [{"Astro Crush"}],
        "Aqua Man - Large Life Energy 1": [{"Tornado Hold"}],
        "Aqua Man - Large Weapon Energy 2": [{"Astro Crush"}],
        "Aqua Man - Large Life Energy 2": [{"Astro Crush"}],
        "Search Man - Large Life Energy": [{"Tornado Hold"}, {"Thunder Claw"}, {"Flame Sword"}],
        "Search Man - Large Weapon Energy": [{"Tornado Hold"}, {"Thunder Claw"}, {"Flame Sword"}],
    }

    def test_every_capsule_s_requirement_is_the_plan_s(self):
        for _s, _r, _k, name in pickups.PICKUPS:
            self.assertEqual(sorted(map(sorted, pickups.requirement(name))),
                             sorted(map(sorted, self.EXPECTED.get(name, []))), name)

    def test_every_capsule_carries_its_own_requirement(self):
        everything = self.multiworld.get_all_state()
        for _index, _record, _kind, name in pickups.PICKUPS:
            with self.subTest(name):
                self.assertTrue(self.rule(name)(everything))
                for clause in pickups.requirement(name):
                    state = everything.copy()
                    for item in list(self.multiworld.itempool):
                        if item.player == self.player and item.name in clause:
                            state.remove(item)
                    self.assertFalse(self.rule(name)(state), f"{name} without any of {sorted(clause)}")

    def test_the_rest_need_nothing(self):
        """The Frost capsule in plain sight that waited on Astro Crush (the
        report), and every other capsule REQUIREMENT does not list - but for
        Sword Man's two past his trials, which wait on those (test_soft_locks)."""
        empty = CollectionState(self.multiworld)
        trials = self.world.sword_past_trials()
        self.assertEqual({n for n in trials if n in pickups.REQUIREMENT}, set())
        free = [name for _s, _r, _k, name in pickups.PICKUPS
                if name not in pickups.REQUIREMENT and name not in trials]
        self.assertEqual(len(free), len(pickups.PICKUPS) - len(pickups.REQUIREMENT) - 2)
        self.assertIn("Frost Man - Large Life Energy 1", free)
        for name in free:
            self.assertTrue(self.rule(name)(empty), name)

    def test_the_three_beside_aqua_s_bolts(self):
        """The map evidence: these share bolt 24's room and bolt 25's ledge."""
        self.assertEqual(pickups.requirement("Aqua Man - Large Life Energy 1"), bolts.requirement(24))
        for name in ("Aqua Man - Large Weapon Energy 2", "Aqua Man - Large Life Energy 2"):
            self.assertEqual(pickups.requirement(name), bolts.requirement(25), name)
        state = CollectionState(self.multiworld)
        state.collect(self.world.create_item(names.TORNADO_HOLD), True)
        self.assertTrue(self.rule("Aqua Man - Large Life Energy 1")(state))
        self.assertFalse(self.rule("Aqua Man - Large Weapon Energy 2")(state))

    def test_the_ice_block_needs_astro_crush(self):
        """Ivor, 2026-10-03: "the frost is broken by astro crush" - the block
        is beside the ladder the route leaves the shaft by. Flash Bomb and
        Flame Sword, which the block's table also takes, do not count."""
        name = "Frost Man - Large Life Energy 5"
        for items, reachable in (([names.MEGA_BALL], False), ([names.ASTRO_CRUSH], True),
                                 ([names.MEGA_BALL, names.FLAME_SWORD, names.FLASH_BOMB], False)):
            state = CollectionState(self.multiworld)
            for item in items:
                state.collect(self.world.create_item(item), True)
            self.assertEqual(self.rule(name)(state), reachable, items)

    def test_the_free_stages(self):
        empty = CollectionState(self.multiworld)
        for index, _record, _kind, name in pickups.PICKUPS:
            stage = pickups.STAGE_OF[index]
            if stage in (names.INTRO, names.TENGU) or stage in names.WILY_STAGES:
                self.assertEqual(pickups.requirement(name), (), name)
                self.assertTrue(self.rule(name)(empty), name)


class TestClient(ClientTest):
    async def test_found_bits_send_their_pickups(self):
        ram = in_stage()
        ram.put(FOUND, (0b101).to_bytes(8, "little"))
        ctx = OptionContext(pickupsanity=1)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertEqual({c for c in ctx.checks() if "Energy" in c},
                         {pickups.PICKUPS[0][3], pickups.PICKUPS[2][3]})

    async def test_the_ice_block_s_bit_sends_its_capsule(self):
        ram = in_stage()
        bit = len(pickups.PICKUPS) - 1
        ram.put(FOUND, (1 << bit).to_bytes(8, "little"))
        ctx = OptionContext(pickupsanity=1)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertIn("Frost Man - Large Life Energy 5", ctx.checks())

    async def test_off_sends_none_of_them(self):
        ram = in_stage()
        ram.put(FOUND, (0b101).to_bytes(8, "little"))
        ctx = OptionContext(pickupsanity=0)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertFalse(any("Energy" in c for c in ctx.checks()))

    async def test_the_server_s_checks_become_confirmed(self):
        ram = in_stage()
        ctx = OptionContext(pickupsanity=1)
        ctx.checked_locations = {location_table[pickups.PICKUPS[34][3]], location_table[pickups.PICKUPS[1][3]]}
        await self.poll(ram, ctx, MM8Client())
        self.assertEqual(int.from_bytes(ram.get(CONFIRMED, 8), "little"), (1 << 34) | (1 << 1))
