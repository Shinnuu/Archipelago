"""`starting_hp` and `heart_tank_value` — the life gauge and the bar that draws it.

Three things are under test and they fail in different ways, so they are kept
apart:

  * the DISC hook that floors the life bar's frame index, which is what makes a
    maximum below 32 legal to ship at all;
  * the CLIENT's grant arithmetic, where the danger is drift and lost life;
  * the residency gate, where the danger is silence - a client that decides no
    save is resident stops sending checks and says nothing about it.

The site addresses and instruction words here were read out of
`Games/MegamanX5/Megaman X5.bin` on 2026-09-06 by extracting the SLUS region
and disassembling it. They are not inferred from X6, whose equivalent code is
identical but whose addresses are not.
"""
import os
import unittest
from types import SimpleNamespace

from .. import Rom, client as mmx5_client, disc
from ..client import (BASE_MAX_HP, HP_PER_HEART, LIFE_HARD_MAX,
                      LIFE_UNINITIALISED, MMX5Client, OFF_CHAR,
                      OFF_MAX_HP_X, OFF_MAX_HP_Z, OFF_STAMP, PLAYER_HP_ADDR,
                      SAVE_BASE, TRAINING_ACT, life_settings)
from .. import names
from .test_client import (FakeContext, TEST_SEED_STAMP, make_save, run_watcher,
                          seed_edits_for)

VANILLA_SUB = 0x2442FFE0        # addiu v0, v0, -32
FRAME_BASE = 0x88               # the shortest real bar
FRAME_TOP = 0x98                # the longest; the game's own clamp


def vanilla_frame(max_hp: int) -> int:
    """What the unpatched game computes, sign-extension included.

    `lb` is signed, and the rounding trio (srl/addu/sra) divides toward zero,
    so this is not a plain floor division for negative inputs.
    """
    x = max_hp - 32
    halved = -((-x) // 2) if x < 0 else x // 2
    return min(FRAME_BASE + halved, FRAME_TOP)


def patched_frame(max_hp: int) -> int:
    """What the hook computes: the same thing, floored at zero first."""
    return min(FRAME_BASE + max(max_hp - 32, 0) // 2, FRAME_TOP)


def life_rows(edits) -> list:
    """The life-bar rows out of a patch_rom seed-edit list."""
    sites = {site for _l, site, _r in disc.LIFE_BAR_SITES}
    hooks = {disc.LIFE_BAR_HOOK_ADDR + i * 4 * disc.LIFE_BAR_HOOK_WORDS
             for i in range(len(disc.LIFE_BAR_SITES))}
    return [e for e in edits if e["addr"] in sites | hooks]


class TestTheBarIsWhyThisNeedsADiscEdit(unittest.TestCase):
    """The frame index is the whole reason a low maximum is not just a number.

    Vanilla clamps this value at the TOP and nowhere else, so it is the LOW
    end that walks off the artwork. Both halves are pinned here because X6
    shipped a fix for the wrong one (capped at 64, reverted a day later).
    """

    def test_vanilla_has_no_lower_clamp(self):
        # The defect, stated as a test: below 32 the index drops beneath the
        # shortest real frame and keeps going.
        self.assertLess(vanilla_frame(30), FRAME_BASE)
        self.assertLess(vanilla_frame(1), vanilla_frame(30))

    def test_the_hook_is_identical_to_vanilla_from_32_up(self):
        # The half that must not move. Includes the overflow range: above 64
        # both clamp at FRAME_TOP and the fill runs on past the frame, which
        # is intended and is the reason there is no cap in this feature.
        for max_hp in range(32, LIFE_HARD_MAX + 1):
            self.assertEqual(patched_frame(max_hp), vanilla_frame(max_hp),
                             f"the hook changed a legal vanilla value ({max_hp})")

    def test_the_hook_floors_the_broken_range(self):
        for max_hp in range(1, 32):
            self.assertEqual(patched_frame(max_hp), FRAME_BASE,
                             f"max {max_hp} still indexes off the artwork")

    def test_nothing_can_index_outside_the_bar_artwork(self):
        for max_hp in range(1, LIFE_HARD_MAX + 1):
            self.assertTrue(FRAME_BASE <= patched_frame(max_hp) <= FRAME_TOP,
                            f"max {max_hp} drew frame {patched_frame(max_hp):#x}")


class TestLifeBarEdits(unittest.TestCase):
    def test_vanilla_and_above_emit_nothing(self):
        # The disc must stay byte-identical for every seed that cannot reach
        # the broken range. Nothing in X5 takes life away, so 32 is the line.
        for value in (32, 33, 64, 100, LIFE_HARD_MAX):
            self.assertEqual(disc.life_bar_edits(value), [],
                             f"starting_hp {value} should not touch the disc")

    def test_below_32_patches_both_sites(self):
        rows = disc.life_bar_edits(31)
        addrs = [addr for addr, _payload, _region in rows]
        for _label, site, _ret in disc.LIFE_BAR_SITES:
            self.assertIn(site, addrs, "a life bar site was left unpatched")
        self.assertEqual(len(rows), 2 * len(disc.LIFE_BAR_SITES),
                         "expected one jump and one hook body per site")

    def test_each_site_gets_a_jump_to_its_own_hook(self):
        rows = {addr: payload for addr, payload, _r in disc.life_bar_edits(1)}
        for index, (_label, site, ret) in enumerate(disc.LIFE_BAR_SITES):
            hook = disc.LIFE_BAR_HOOK_ADDR + index * 4 * disc.LIFE_BAR_HOOK_WORDS
            self.assertEqual(int.from_bytes(rows[site], "little"),
                             disc._life_bar_jump(hook))
            body = rows[hook]
            self.assertEqual(len(body), 4 * disc.LIFE_BAR_HOOK_WORDS)
            # The jump home sits in word 4, with the /2 in its delay slot.
            self.assertEqual(int.from_bytes(body[16:20], "little"),
                             disc._life_bar_jump(ret),
                             "the hook does not return to its own site")
            self.assertEqual(int.from_bytes(body[20:24], "little"), 0x00021043,
                             "the delay slot must still do the /2")

    def test_the_site_word_it_replaces_is_the_one_we_expect(self):
        # The hook body opens by REDOING the instruction the jump displaced.
        # If that word were ever wrong the bar would be silently rescaled, so
        # it is pinned to the disassembly rather than left implicit.
        self.assertEqual(disc.LIFE_BAR_VANILLA_SUB, VANILLA_SUB)
        body = dict((a, p) for a, p, _r in disc.life_bar_edits(1))[
            disc.LIFE_BAR_HOOK_ADDR]
        self.assertEqual(int.from_bytes(body[0:4], "little"), VANILLA_SUB)

    def test_the_hooks_fit_the_validated_free_space(self):
        # Being zero in the file is not enough; this run is the one the
        # project has canaried at runtime. Overrunning it would land the hook
        # on live code, which is not something a unit test could otherwise see.
        end = (disc.LIFE_BAR_HOOK_ADDR
               + len(disc.LIFE_BAR_SITES) * 4 * disc.LIFE_BAR_HOOK_WORDS)
        self.assertLessEqual(end, disc.LIFE_BAR_RUN_END)
        self.assertGreaterEqual(disc.LIFE_BAR_HOOK_ADDR, 0x800776A0)

    def test_the_hooks_do_not_collide_with_the_other_stubs(self):
        occupied = set()
        for start, length in (
                (disc.PICKUP_STUB_ADDR, len(disc.PICKUP_STUB)),
                (disc.CAPSULE_STUB_ADDR, len(disc.CAPSULE_STUB)),
                (disc.PICKUPSANITY_STUB_ADDR, len(disc.PICKUPSANITY_STUB)),
                (disc.PICKUPSANITY_CHECKED_TABLE_ADDR,
                 4 * (disc.PICKUPSANITY_CHECKED_SLOTS + 1))):
            occupied.update(range(start, start + length))
        hooks = range(disc.LIFE_BAR_HOOK_ADDR,
                      disc.LIFE_BAR_HOOK_ADDR
                      + len(disc.LIFE_BAR_SITES) * 4 * disc.LIFE_BAR_HOOK_WORDS)
        self.assertEqual(occupied & set(hooks), set(),
                         "the life bar hook overlaps another stub")

    def test_hooks_are_word_aligned(self):
        self.assertEqual(disc.LIFE_BAR_HOOK_ADDR % 4, 0)
        for _label, site, ret in disc.LIFE_BAR_SITES:
            self.assertEqual(site % 4, 0)
            self.assertEqual(ret % 4, 0)

    def test_the_return_is_four_instructions_past_the_site(self):
        # The block the hook stands in for is sub / srl / addu / sra: four
        # words. A return anywhere else would either re-run the subtraction or
        # skip the frame-base add.
        for _label, site, ret in disc.LIFE_BAR_SITES:
            self.assertEqual(ret - site, 0x10)


class TestPatchRomWiring(unittest.TestCase):
    def test_default_seed_gets_no_life_bar_edits(self):
        self.assertEqual(life_rows(seed_edits_for()), [])

    def test_a_low_seed_gets_them(self):
        self.assertEqual(len(life_rows(seed_edits_for(starting_hp=8))),
                         2 * len(disc.LIFE_BAR_SITES))

    def test_boundary_is_32(self):
        self.assertEqual(life_rows(seed_edits_for(starting_hp=32)), [])
        self.assertNotEqual(life_rows(seed_edits_for(starting_hp=31)), [])

    def test_heart_tank_value_never_touches_the_disc(self):
        # It is delivered entirely by the client. If this ever starts emitting
        # rows, the unpatcher manifest needs regenerating.
        self.assertEqual(seed_edits_for(heart_tank_value=8),
                         seed_edits_for(heart_tank_value=2))


class TestLifeSettings(unittest.TestCase):
    """Slot data comes off the wire, and every value here drives a WRITE."""

    def _ctx(self, **slot_data):
        return SimpleNamespace(slot_data=slot_data)

    def test_defaults_are_vanilla_when_the_seed_predates_the_options(self):
        self.assertEqual(life_settings(self._ctx()), (BASE_MAX_HP, HP_PER_HEART))

    def test_missing_slot_data_entirely(self):
        self.assertEqual(life_settings(SimpleNamespace(slot_data=None)),
                         (BASE_MAX_HP, HP_PER_HEART))

    def test_values_are_passed_through(self):
        self.assertEqual(life_settings(self._ctx(starting_hp=8,
                                                 heart_tank_value=16)), (8, 16))

    def test_nonsense_falls_back_rather_than_propagating(self):
        for bad in ("", None, "lots", [], {}):
            self.assertEqual(life_settings(self._ctx(starting_hp=bad))[0],
                             BASE_MAX_HP, f"{bad!r} did not fall back")

    def test_out_of_range_is_clamped_not_rejected(self):
        # A corrupt starting maximum must never read as "one hit from death",
        # and must never exceed the signed-byte ceiling.
        self.assertEqual(life_settings(self._ctx(starting_hp=0))[0], 1)
        self.assertEqual(life_settings(self._ctx(starting_hp=999))[0],
                         LIFE_HARD_MAX)
        self.assertEqual(life_settings(self._ctx(heart_tank_value=-5))[1], 0)

    def test_zero_hearts_is_legal_and_is_not_the_default(self):
        # 0 is a real choice ("the check sends, the gauge does not move") and
        # must survive the falsy-value trap that would send it to the default.
        self.assertEqual(life_settings(self._ctx(heart_tank_value=0))[1], 0)


class TestResidencyGateMovesWithTheSeed(unittest.IsolatedAsyncioTestCase):
    """The failure this guards is SILENCE.

    Max HP is how the client decides a save struct is resident. If a legal
    `starting_hp` falls outside the window, checks stop being sent and nothing
    in the game looks wrong.
    """

    async def _sends_checks(self, max_hp, **slot_data):
        client = MMX5Client()
        client.ap_patched = True
        client.stub_present = True
        ctx = FakeContext()
        ctx.slot_data = {"goal": 0, "boss_difficulty": 1, **slot_data}
        save = bytearray(make_save(max_hp, intro=1))
        save[OFF_MAX_HP_Z] = max_hp
        ctx = await run_watcher(bytes(save), client=client, ctx=ctx)
        return bool(ctx.checked_location_ids())

    async def test_a_high_starting_maximum_still_reports(self):
        # 100 is outside the old 0x10..0x40 window. Before the gate moved,
        # this seed would have gone quiet.
        self.assertTrue(await self._sends_checks(100, starting_hp=100))

    async def test_a_low_starting_maximum_still_reports(self):
        self.assertTrue(await self._sends_checks(8, starting_hp=8))

    async def test_a_brand_new_save_at_vanilla_32_is_still_resident(self):
        # The window has to admit 0x20 whatever the seed says, because that is
        # what a save holds in the moment BEFORE the baseline is applied to it.
        # Getting this wrong would deadlock adoption: never sane, so never
        # adopted, so never corrected.
        self.assertTrue(await self._sends_checks(BASE_MAX_HP, starting_hp=100))

    async def test_a_default_seed_is_unchanged(self):
        self.assertTrue(await self._sends_checks(BASE_MAX_HP))

    async def test_garbage_is_still_rejected(self):
        # The gate is weaker than it was at the bottom for a low seed; it must
        # still reject an empty struct, which is the state RAM is in before any
        # save exists.
        self.assertFalse(await self._sends_checks(0, starting_hp=1))
        self.assertFalse(await self._sends_checks(0xFF, starting_hp=1))


class TestStartingHpIsAppliedOnce(unittest.IsolatedAsyncioTestCase):
    """The stamp is the flag, so these two behaviours are one mechanism."""

    async def _adopt(self, save_bytes, **slot_data):
        client = MMX5Client()
        client.ap_patched = True
        client.stub_present = True
        ctx = FakeContext()
        ctx.slot_data = {"goal": 0, "boss_difficulty": 1, **slot_data}
        return await run_watcher(save_bytes, client=client, ctx=ctx)

    @staticmethod
    def _life_writes(ctx):
        addr = SAVE_BASE + OFF_MAX_HP_X
        return [list(w[1]) for w in ctx.writes if w[0] == addr]

    @staticmethod
    def _fresh(max_hp=BASE_MAX_HP, zero=None, stamp=0):
        """A save as the game really leaves it: BOTH maximum bytes set."""
        save = bytearray(make_save(max_hp, stamp=stamp))
        save[OFF_MAX_HP_Z] = max_hp if zero is None else zero
        return bytes(save)

    async def test_a_fresh_save_gets_the_seed_value_for_both_characters(self):
        ctx = await self._adopt(self._fresh(), starting_hp=8)
        self.assertEqual(self._life_writes(ctx), [[8, 8]])

    async def test_an_already_adopted_save_is_left_alone(self):
        # The whole point of riding the stamp: a save mid-run must not have its
        # maximum rewritten, or every Heart Tank earned so far would be undone.
        ctx = await self._adopt(self._fresh(0x30, stamp=TEST_SEED_STAMP),
                                starting_hp=8)
        self.assertEqual(self._life_writes(ctx), [])

    async def test_a_default_seed_writes_nothing(self):
        ctx = await self._adopt(self._fresh())
        self.assertEqual(self._life_writes(ctx), [])

    async def test_an_uninitialised_zero_byte_cannot_cripple_the_save(self):
        # Only X's maximum passes the residency gate; Zero's is never
        # validated. Shifting from a byte that is still 0 would compute
        # `start - 32` and write a permanently crippled maximum, so the delta
        # is floored at zero. This is the disproving case for that floor: with
        # it, Zero gets the seed's value; without it, Zero gets 1.
        ctx = await self._adopt(self._fresh(zero=0), starting_hp=8)
        self.assertEqual(self._life_writes(ctx), [[8, 8]])

    async def test_life_already_earned_before_connecting_is_kept(self):
        # Alia's Life Up reward is +2, is not an AP item, and does not count as
        # `progressed` (it sets bits 8-15 of the u32 at 0x1C80, while that test
        # reads byte 0x1C80). So a save can legitimately arrive at 34. The
        # baseline SHIFTS rather than assigns, or those points vanish.
        save = bytearray(make_save(BASE_MAX_HP + 2, stamp=0))
        save[OFF_MAX_HP_Z] = BASE_MAX_HP + 2
        ctx = await self._adopt(bytes(save), starting_hp=64)
        self.assertEqual(self._life_writes(ctx), [[66, 66]])

    async def test_the_two_characters_keep_their_separate_totals(self):
        # X5 grants a vanilla Life Up to the SELECTED character only, so the
        # two bytes can legitimately differ before adoption.
        save = bytearray(make_save(BASE_MAX_HP + 2, stamp=0))
        save[OFF_MAX_HP_Z] = BASE_MAX_HP
        ctx = await self._adopt(bytes(save), starting_hp=40)
        self.assertEqual(self._life_writes(ctx), [[42, 40]])

    async def test_the_result_never_leaves_the_engine_range(self):
        save = bytearray(make_save(BASE_MAX_HP + 16, stamp=0))
        save[OFF_MAX_HP_Z] = BASE_MAX_HP + 16
        ctx = await self._adopt(bytes(save), starting_hp=LIFE_HARD_MAX)
        for written in self._life_writes(ctx):
            for value in written:
                self.assertTrue(1 <= value <= LIFE_HARD_MAX,
                                f"wrote {value}, outside the signed-byte range")


class TestHeartTankValue(unittest.IsolatedAsyncioTestCase):
    async def _grant(self, hearts, max_hp=BASE_MAX_HP, **slot_data):
        client = MMX5Client()
        client.ap_patched = True
        client.stub_present = True
        ctx = FakeContext()
        ctx.slot_data = {"goal": 0, "boss_difficulty": 1, **slot_data}
        ctx.items_received = [SimpleNamespace(item=i) for i in range(hearts)]
        ctx.item_names = SimpleNamespace(
            lookup_in_game=lambda code: names.HEART_TANK)
        save = bytearray(make_save(max_hp, intro=1))
        save[OFF_MAX_HP_Z] = max_hp
        ctx = await run_watcher(bytes(save), client=client, ctx=ctx)
        addr = SAVE_BASE + OFF_MAX_HP_X
        writes = [list(w[1]) for w in ctx.writes if w[0] == addr]
        return writes[-1] if writes else None

    async def test_vanilla_step_is_unchanged(self):
        self.assertEqual(await self._grant(1), [0x22, 0x22])

    async def test_the_step_comes_from_the_seed(self):
        self.assertEqual(await self._grant(1, heart_tank_value=8),
                         [BASE_MAX_HP + 8, BASE_MAX_HP + 8])

    async def test_zero_grants_no_life(self):
        # The check still sends; the gauge does not move. A write of the same
        # value is acceptable, a CHANGED value is not.
        written = await self._grant(2, heart_tank_value=0)
        self.assertIn(written, (None, [BASE_MAX_HP, BASE_MAX_HP]))

    async def test_several_hearts_in_one_batch_all_count(self):
        self.assertEqual(await self._grant(3, heart_tank_value=4),
                         [BASE_MAX_HP + 12, BASE_MAX_HP + 12])

    async def test_both_characters_are_raised(self):
        written = await self._grant(1, heart_tank_value=6)
        self.assertEqual(written[0], written[1],
                         "an AP heart must not shortchange the benched character")

    async def test_the_cap_is_the_engine_ceiling_not_vanillas_maximum(self):
        # The old cap was 0x40 - vanilla's maximum, not the engine's. Under it
        # every Heart Tank past 64 was silently worth nothing, which
        # heart_tank_value makes trivial to reach.
        written = await self._grant(1, max_hp=0x40, heart_tank_value=8)
        self.assertEqual(written, [0x48, 0x48])

    async def test_nothing_can_exceed_the_signed_byte_ceiling(self):
        # Past 0x7F the game's `lb` would read the maximum as negative.
        written = await self._grant(4, max_hp=0x70, heart_tank_value=64)
        self.assertEqual(written, [LIFE_HARD_MAX, LIFE_HARD_MAX])


class TestGrantsStayIncremental(unittest.IsolatedAsyncioTestCase):
    """Why this is not X6's absolute write.

    X6 rebuilds the maximum from its own items every cycle, because it has no
    exactly-once record of what it has applied. X5 does (OFF_PROCESSED, written
    in the same guarded batch as the grants), and adding to what is already in
    the byte is what keeps the life the GAME granted - Alia's Life Up rewards,
    which are not Archipelago items and which an absolute write would erase.
    """

    async def test_life_the_game_granted_survives_a_heart_tank(self):
        client = MMX5Client()
        client.ap_patched = True
        client.stub_present = True
        ctx = FakeContext()
        ctx.slot_data = {"goal": 0, "boss_difficulty": 1, "starting_hp": 32,
                         "heart_tank_value": 2}
        ctx.items_received = [SimpleNamespace(item=0)]
        ctx.item_names = SimpleNamespace(
            lookup_in_game=lambda code: names.HEART_TANK)
        # 32 + two Life Up rewards the client never saw.
        save = bytearray(make_save(36, intro=1))
        save[OFF_MAX_HP_Z] = 36
        ctx = await run_watcher(bytes(save), client=client, ctx=ctx)
        addr = SAVE_BASE + OFF_MAX_HP_X
        written = [list(w[1]) for w in ctx.writes if w[0] == addr][-1]
        self.assertEqual(written, [38, 38],
                         "an absolute rebuild would have thrown away the "
                         "4 points Alia's rewards granted")


@unittest.skipUnless(os.environ.get("MMX5_DISC"),
                     "set MMX5_DISC to a Megaman X5 .bin to verify against one")
class TestLifeBarAgainstDisc(unittest.TestCase):
    """The premise every other test in this file rests on.

    `addiu v0, v0, -32` occurs 223 TIMES in this executable. Matching that one
    word proves nothing at all, so each site is confirmed by the whole block
    around it: the signed `lb` of max HP two instructions earlier, the
    rounding trio, the frame base, and the top clamp. A mis-derived address
    cannot survive that, and a mis-derived address here would corrupt the HUD
    of every seed that starts below 32.
    """

    SUB, SRL, ADDU, SRA = 0x2442FFE0, 0x00021FC2, 0x00431021, 0x00021043

    @classmethod
    def setUpClass(cls) -> None:
        sector, payload, poff = 2352, 2048, 0x18
        with open(os.environ["MMX5_DISC"], "rb") as f:
            f.seek(23433 * sector)
            raw = f.read(260 * sector)
        cls.exe = b"".join(raw[i * sector + poff: i * sector + poff + payload]
                           for i in range(260))
        cls.base = 0x80010000

    def word(self, addr: int) -> int:
        off = addr - self.base
        return int.from_bytes(self.exe[off:off + 4], "little")

    def test_both_sites_hold_the_whole_vanilla_block(self):
        for label, site, ret in disc.LIFE_BAR_SITES:
            with self.subTest(label):
                # The four words the hook stands in for.
                self.assertEqual(
                    [self.word(site + i * 4) for i in range(4)],
                    [self.SUB, self.SRL, self.ADDU, self.SRA],
                    f"{label}: not the rounding block we disassembled")
                # `lb v0, 0x47(rX)` - a SIGNED load of max HP out of the save
                # struct. This is what identifies the block as the PLAYER bar
                # rather than one of the 221 other subtractions.
                self.assertEqual(self.word(site - 8) & 0xFC1FFFFF, 0x80020047,
                                 f"{label}: does not read max HP at 0x47")
                # `addiu rD, v0, 136` - the frame base the hook returns to.
                self.assertEqual(self.word(ret) & 0xFFE0FFFF, 0x24400088,
                                 f"{label}: return is not the frame base add")
                # `slti v1, rD, 153` - the top clamp, and the proof there is
                # no lower one.
                self.assertEqual(self.word(ret + 4) & 0xFC1FFFFF, 0x28030099,
                                 f"{label}: top clamp is not where we think")

    def test_there_are_exactly_two_such_sites(self):
        # The control for "did we miss a copy". A third block reading max HP
        # into the same frame maths would be left unpatched and would draw the
        # broken bar in whatever context it serves.
        found = []
        for off in range(0, len(self.exe) - 20, 4):
            addr = self.base + off
            if [self.word(addr + i * 4) for i in range(4)] != \
                    [self.SUB, self.SRL, self.ADDU, self.SRA]:
                continue
            if self.word(addr - 8) & 0xFC1FFFFF != 0x80020047:
                continue
            if self.word(addr + 16) & 0xFFE0FFFF != 0x24400088:
                continue
            found.append(addr)
        self.assertEqual(found, [site for _l, site, _r in disc.LIFE_BAR_SITES],
                         "the set of player life-bar sites is not what we patch")

    def test_the_hook_lands_on_free_space(self):
        # X6 got this proof for free: its patcher declares the vanilla bytes
        # and refuses a mismatch, so a hook accepted onto zeros IS the
        # evidence. X5's apply_basepatch does not verify, so the check has to
        # be made explicitly here or not at all.
        need = len(disc.LIFE_BAR_SITES) * 4 * disc.LIFE_BAR_HOOK_WORDS
        off = disc.LIFE_BAR_HOOK_ADDR - self.base
        self.assertEqual(self.exe[off:off + need], bytes(need),
                         "the life bar hook would overwrite real code")

    def test_the_jump_encodings_point_where_we_think(self):
        # `j` keeps only the low 26 bits of the target, so an address in the
        # wrong 256 MB segment would encode silently and jump into nowhere.
        for index, (_label, site, ret) in enumerate(disc.LIFE_BAR_SITES):
            hook = disc.LIFE_BAR_HOOK_ADDR + index * 4 * disc.LIFE_BAR_HOOK_WORDS
            for target in (hook, ret):
                decoded = ((site & 0xF0000000)
                           | ((disc._life_bar_jump(target) & 0x03FFFFFF) << 2))
                self.assertEqual(decoded, target,
                                 f"j 0x{target:08X} does not encode to itself")


if __name__ == "__main__":
    unittest.main()


class TestTheEngineCanOverflowTheMaximum(unittest.IsolatedAsyncioTestCase):
    """Reported off a live seed 2026-09-08: frozen at the spawn point in Zero
    Space, HUD tiles painted across the screen, the other character fine.

    Every write this client makes is clamped. The GAME's own +2 grants are
    not - the vanilla Heart Tank handler at 0x800540A0 is `lbu`/`+2`/`sb` with
    no bounds check - and they land on top of our clamp. Past 0x7F the byte
    reads NEGATIVE through the life bar's signed load, and it simultaneously
    fails the residency test, so the client goes silent and cannot repair
    itself. Both halves are pinned here.
    """

    async def _poll(self, x_max, z_max=LIFE_HARD_MAX, *, stamp=None,
                    player_hp=BASE_MAX_HP, char=0, intro=1, mode=0x0A,
                    **slot_data):
        client = MMX5Client()
        client.ap_patched = True
        client.stub_present = True
        ctx = FakeContext()
        ctx.slot_data = {"goal": 0, "boss_difficulty": 1, **slot_data}
        save = bytearray(make_save(x_max, intro=intro, stamp=stamp))
        save[OFF_MAX_HP_Z] = z_max
        save[OFF_CHAR] = char
        return await run_watcher(bytes(save), client=client, ctx=ctx,
                                 mode=mode, player_hp=player_hp)

    @staticmethod
    def _life_writes(ctx):
        return [list(w[1]) for w in ctx.writes
                if w[0] == SAVE_BASE + OFF_MAX_HP_X]

    @staticmethod
    def _hp_writes(ctx):
        return [list(w[1]) for w in ctx.writes if w[0] == PLAYER_HP_ADDR]

    async def test_the_overflowed_maximum_is_clamped_back(self):
        ctx = await self._poll(LIFE_HARD_MAX + 2)
        self.assertEqual(self._life_writes(ctx),
                         [[LIFE_HARD_MAX, LIFE_HARD_MAX]])

    async def test_checks_still_flow_in_the_very_poll_it_is_found(self):
        # The silent half. Without the repair this save fails save_sane and
        # the client says nothing while sending nothing.
        ctx = await self._poll(LIFE_HARD_MAX + 2)
        self.assertTrue(ctx.checked_location_ids())

    async def test_zero_overflows_on_its_own(self):
        # The grants raise only the CURRENT character, which is exactly why
        # the reporter could swap to Zero and keep playing.
        ctx = await self._poll(LIFE_HARD_MAX, z_max=LIFE_HARD_MAX + 2)
        self.assertEqual(self._life_writes(ctx),
                         [[LIFE_HARD_MAX, LIFE_HARD_MAX]])

    async def test_a_legal_maximum_is_never_written(self):
        for legal in (BASE_MAX_HP, 64, LIFE_HARD_MAX):
            with self.subTest(max_hp=legal):
                ctx = await self._poll(legal, z_max=legal)
                self.assertEqual(self._life_writes(ctx), [])

    async def test_every_illegal_maximum_is_repaired_not_just_a_plausible_one(self):
        # 0.7.1 stopped at 0x7F + 32 - "eight Life Ups and eight Heart Tanks"
        # - and called anything past that garbage. Nothing counts those
        # grants and nothing limits them to eight, so that bound only
        # guaranteed that a save which drifted further could never be
        # rescued. Every value above the ceiling is illegal for a stamped
        # save, and every one of them is now put back.
        for illegal in (LIFE_HARD_MAX + 1, LIFE_HARD_MAX + 32,
                        LIFE_HARD_MAX + 33, LIFE_UNINITIALISED - 1):
            with self.subTest(max_hp=illegal):
                ctx = await self._poll(illegal)
                self.assertEqual(self._life_writes(ctx),
                                 [[LIFE_HARD_MAX, LIFE_HARD_MAX]])

    async def test_the_repair_is_not_gated_on_gameplay(self):
        # THE 0.7.1 DEFECT, from BizHawkClient_2026_09_11_01_57_56.txt: the
        # byte went to 0x81 within 0.6s of a Zero Space 1 clear, and endgame
        # stages never route through the 0x0C results screen. The walk from
        # there is cutscene -> hub 0x04 -> stage entry 0x07-0x09 -> frozen at
        # the spawn, so a repair gated on `mode in (0x0A, 0x0C)` got no
        # eligible poll between the overflow and the freeze. Every mode on
        # that path has to be able to put the byte back, because the mode the
        # old gate waited for is the one the bug prevents.
        for mode in (0x04, 0x07, 0x08, 0x09, 0x13, 0x14):
            with self.subTest(mode=mode):
                ctx = await self._poll(LIFE_HARD_MAX + 2, mode=mode)
                self.assertEqual(self._life_writes(ctx),
                                 [[LIFE_HARD_MAX, LIFE_HARD_MAX]])

    async def test_the_live_hp_byte_is_only_touched_in_gameplay(self):
        # The save byte is repairable from anywhere; P+0x5C is not. Outside
        # gameplay there is no player object behind that address, and
        # ram-notes already flags client writes there as unreliable - so the
        # rescue stays where it means something and prevention does the work.
        ctx = await self._poll(LIFE_HARD_MAX + 2, mode=0x04,
                               player_hp=LIFE_HARD_MAX + 2)
        self.assertEqual(self._life_writes(ctx),
                         [[LIFE_HARD_MAX, LIFE_HARD_MAX]])
        self.assertEqual(self._hp_writes(ctx), [])

    async def test_uninitialised_bytes_are_still_garbage(self):
        # The pre-existing residency test rejected 0xFF and must keep doing so:
        # a repair that swallowed it would hand the client a "resident" save
        # built out of whatever RAM happened to hold.
        ctx = await self._poll(0xFF, z_max=0xFF)
        self.assertEqual(self._life_writes(ctx), [])
        self.assertFalse(ctx.checked_location_ids())

    async def test_a_save_that_is_not_ours_is_left_alone(self):
        # Unstamped and carrying progress: the A3b hold. Repairing it would be
        # writing into a save this seed has never adopted.
        ctx = await self._poll(LIFE_HARD_MAX + 2, stamp=0)
        self.assertEqual(self._life_writes(ctx), [])

    async def test_training_is_left_alone(self):
        ctx = await self._poll(LIFE_HARD_MAX + 2, intro=TRAINING_ACT)
        self.assertEqual(self._life_writes(ctx), [])

    async def test_the_live_hp_byte_is_restored_when_it_copied_the_bad_max(self):
        # The spawn full heal copies the maximum verbatim, so 0x81 arrives in
        # a byte whose bit 7 means "just damaged" - 1 HP, and hurt.
        ctx = await self._poll(LIFE_HARD_MAX + 2, player_hp=LIFE_HARD_MAX + 2)
        self.assertEqual(self._hp_writes(ctx), [[LIFE_HARD_MAX]])

    async def test_the_restore_follows_the_selected_character(self):
        ctx = await self._poll(LIFE_HARD_MAX, z_max=LIFE_HARD_MAX + 2,
                               char=1, player_hp=LIFE_HARD_MAX + 2)
        self.assertEqual(self._hp_writes(ctx), [[LIFE_HARD_MAX]])

    async def test_a_damaged_player_keeps_the_damage_flag(self):
        # 0x90: sixteen HP with bit 7 set. It is not a copy of the maximum, so
        # it is a real hit and none of our business - clearing bit 7 wholesale
        # would erase it.
        ctx = await self._poll(LIFE_HARD_MAX + 2, player_hp=0x90)
        self.assertEqual(self._hp_writes(ctx), [])
