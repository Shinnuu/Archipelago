"""pickupsanity: the stub EXECUTED on the R3000, its table and hooks, the
location list against the disc's own spawn lists, and the client."""
import struct
import unittest

from .. import disc, mips, names, pickups
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

    def test_the_last_location_uses_the_high_word(self):
        stage, record, _k, _n = pickups.PICKUPS[-1]
        m = self.run_stub(stage=stage, record=record)
        self.assertEqual(self.outcome(m), (0, 1 << (len(pickups.PICKUPS) - 1), True))

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
                         [(0, 19), (10, 59), (10, 60), (11, 69), (12, 34), (12, 44), (12, 47)])
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
        ours = {(s, r): k for s, r, k, _n in pickups.PICKUPS}
        self.assertEqual(set(placed), set(ours) | set(pickups.NOT_LOCATIONS))
        for where, kind in ours.items():
            self.assertEqual(placed[where], kind, where)

    def test_the_hooks_and_the_table_land_on_what_the_research_read(self):
        edits = disc.pickup_edits(pickups.KEYS)
        for label, where, region, vanilla, _payload in edits:
            got = bytes(self.track1[disc.addr_to_disc(where + i, region)] for i in range(len(vanilla)))
            self.assertEqual(got, vanilla, label)
        disc.apply_edits(self.track1, list(disc.BASE_EDITS) + disc.routine_edits(self.track1)
                         + disc.ap_block_edits(1) + edits)


class TestClient(ClientTest):
    async def test_found_bits_send_their_pickups(self):
        ram = in_stage()
        ram.put(FOUND, (0b101).to_bytes(8, "little"))
        ctx = OptionContext(pickupsanity=1)
        await self.poll(ram, ctx, MM8Client(), 3)
        self.assertEqual({c for c in ctx.checks() if "Energy" in c},
                         {pickups.PICKUPS[0][3], pickups.PICKUPS[2][3]})

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
