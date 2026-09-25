"""BizHawkClient for Mega Man 8 (PS1, SLUS-00453, NTSC-U).

X5's architecture (v1-design 5a): the client is the ONLY granter. The disc
patch keeps the game's own records where progression needs them - the kill
record (+0 of each weapon entry), the intro's Mega Ball, the bolt field, the
phase byte, the Wily counter - and turns every other grant into an AP check
record in the AP block at 0x801D2A00. So the client reads checks from those
records and writes items into capability that nothing in the game grants.

Policies, each with its reason. Read these before changing anything.

1. ONLY THIS SEED'S DISC. The AP block must carry the patch's signature and
   version and this slot's seed stamp (slot data), or the client does nothing
   at all: a vanilla disc, another patch version or another seed's disc would
   turn its records into false checks and its capability into false grants.

2. THE ATTRACT DEMO IS NOT PLAY. Each demo swaps in its own weapon loadout -
   every Robot Master "beaten" - and clears and collects bolts. The demo runs
   exactly while the timer 0x801B2944 is non-zero (0x800FF4C0), so nothing is
   read or written then; and the weapon capability bytes must read back as
   the client last wrote them, which a demo's whole-entry swap breaks.
   Checks are also only sent once the check-driving bytes repeat across two
   polls (X5's rule: a single poll can land mid-load or mid-swap).

3. GRANTS ARE ABSOLUTE wherever the state allows (X6's policy 2): weapon
   capability (+1 of each entry), Rush, parts and the bolt counter are
   computed from the items received and written whole, so a reconnect or a
   savestate is a no-op. Bolts = bundles received x bundle size - the price
   of every Lab entry the player BOUGHT (AP_LAB, set by the purchase itself),
   which needs no counter at all.

4. CONSUMABLES ARE COUNTED (X5's rule): 1-Ups and energy cannot be absolute,
   so they are applied from a cursor into the received items - AP_PROCESSED,
   which rides the memory card in the save extension (P11) and so survives a
   power-cycle and rewinds with an older save.

5. A Rush pickup whose location the server already has is marked checked in
   the AP block, so the mini-boss does not drop it again - exactly what a
   vanilla revisit does. A Lab entry is NOT: AP_LAB is what the player paid
   for, and the bolt account depends on it.
"""
import logging
import time
from typing import TYPE_CHECKING

from NetUtils import ClientStatus

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from . import disc, names
from .bolts import BOLT_LOCATIONS
from .locations import location_table

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

logger = logging.getLogger("Client")


def _ram(address: int) -> int:
    return address - 0x80000000


def _u32(data: bytes, off: int = 0) -> int:
    return int.from_bytes(data[off:off + 4], "little")


# ---- Addresses (ram-notes; every one [D] or [L]) ------------------------------
GAME_SIG_ADDR = _ram(0x80150848)        # the save file name, in the EXE's data
GAME_SIG = b"BASLUS-00453"
AP_ADDR = _ram(disc.AP_BLOCK)
AP_LEN = 0x20
WEAPONS_ADDR = _ram(disc.WEAPONS)       # 16 entries x 4: +0 kill record, +1 capability,
WEAPONS_LEN = 10 * 4                    # +2..+3 energy (8.8); slots 0-9 matter
LIVE_ADDR = _ram(0x8016D2F0)            # bolts u16, 8 part slots, +0x0A, 40-bit bolt
LIVE_LEN = 0x14                         # field at +0x0B, live Rush at +0x10
PERSIST_RUSH_ADDR = _ram(0x801C3352)    # what the Rush menu reads
MIRROR_ADDR = _ram(0x801C3340)          # part id i's effect flag at +i
PROGRESS_ADDR = _ram(0x801C336C)        # phase, Wily count, stage index, loaded flag, lives
PROGRESS_LEN = 5
DEMO_TIMER_ADDR = _ram(0x801B2944)
OVERLAY_ADDR = _ram(disc.OVL_BASE)      # the resident overlay's id; stages are 6..0x13
HP_ADDR = _ram(0x8015E283)
CUR_WEAPON_ADDR = _ram(0x8016DC08)      # the weapon slot in hand; firing reads only this
REFUSAL_GRACE = 10.0                    # seconds a missing AP block may last before we say so

OFF_BOLTS, OFF_SHOT_SELECT, OFF_BOLT_FIELD, OFF_LIVE_RUSH = 0x00, 0x0A, 0x0B, 0x10
# 0x8016D2FA, the buster mode the pause screen picks: 0 normal, then Laser,
# Arrow, Auto Shoot = part ids 11-13 (R5). Saved with the live block.
SHOT_PART_ID = {1: 11, 2: 12, 3: 13}
MIRROR_LEN = 0x12                       # part ids 1-17's effect flags
AP_OFF_STAMP, AP_OFF_PARTS, AP_OFF_LAB, AP_OFF_RUSH, AP_OFF_PROCESSED = (
    a - disc.AP_BLOCK for a in (disc.AP_STAMP, disc.AP_PARTS, disc.AP_LAB,
                                disc.AP_RUSH, disc.AP_PROCESSED))
STAGE_OVERLAYS = range(6, 0x14)
HP_MAX = 40                             # [L]
LIVES_CAP = 9                           # inference: the lives counter is one digit
ENERGY_FULL = 0x2800                    # 40.0 in the 8.8 energy halfword
WILY_CLEARS_FOR_GOAL = 4                # +1 per Wily stage cleared (0x80101418..24)
PHASE_DUO_CLEARED = 4                   # phase 3 -> 4 on Duo's clear (0x801013EC)
GOAL_WILY, GOAL_ROBOT_MASTERS = 0, 1

# ---- Tables from the world ----------------------------------------------------------
SLOT_TO_BOSS = {names.WEAPON_SLOT[names.BOSS_WEAPON[boss]]: boss for boss in names.ROBOT_MASTERS}
ITEM_WEAPON_SLOT = dict(names.WEAPON_SLOT)            # Mega Ball + the 8 weapons
LAB_PRICE_BY_ID = disc.LAB_PRICE


class MM8Client(BizHawkClient):
    game = "Mega Man 8"
    system = "PSX"
    # Registers ".apmm8" with the Launcher's Open Patch (X5's lesson: without
    # it the player is never asked for their disc image).
    patch_suffix = ".apmm8"

    def __init__(self) -> None:
        super().__init__()
        self._reset()

    def _reset(self) -> None:
        self.sent: set[int] = set()
        self.last_signature: bytes | None = None
        self.refusal: str | None = None       # the reason currently in force
        self.refusal_since: float | None = None
        self.refusal_logged = False
        self.capability_written: bytes | None = None
        self.victory_sent = False

    def _refuse(self, reason: str, grace: float = 0.0) -> None:
        """Do nothing this poll; say why once the reason has lasted `grace`
        seconds. A missing AP block is often a moment, not a verdict: at boot
        the EXE streams in and the block (the image's last page) lands after
        the game's name does, and a savestate from another disc hides it until
        the ramwatch's PATCHGUARD puts the patch back (seen live 2026-09-24:
        four warnings for four harmless moments). A wrong stamp is definite."""
        now = time.monotonic()
        if self.refusal != reason:
            self.refusal, self.refusal_since, self.refusal_logged = reason, now, False
        if not self.refusal_logged and now - self.refusal_since >= grace:
            self.refusal_logged = True
            logger.warning(f"Mega Man 8: {reason} - the client is doing nothing.")

    def _accept(self) -> None:
        if self.refusal_logged:
            logger.info("Mega Man 8: this seed's patched disc is back - the client is running again.")
        self.refusal, self.refusal_since, self.refusal_logged = None, None, False

    # ---- identification ----------------------------------------------------

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        try:
            (sig,) = await bizhawk.read(ctx.bizhawk_ctx, [(GAME_SIG_ADDR, len(GAME_SIG), "MainRAM")])
        except bizhawk.RequestFailedError:
            return False
        if sig != GAME_SIG:
            return False
        ctx.game = self.game
        ctx.items_handling = 0b111     # remote items, own-world items, starting inventory
        ctx.want_slot_data = True
        self._reset()
        return True

    # ---- item accounting ---------------------------------------------------

    @staticmethod
    def _received(ctx: "BizHawkClientContext") -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in ctx.items_received:
            name = ctx.item_names.lookup_in_game(item.item)
            counts[name] = counts.get(name, 0) + 1
        return counts

    @staticmethod
    def capability(received: dict[str, int]) -> bytes:
        """+1 of weapon slots 0-9: the buster always, the rest as received."""
        out = bytearray(10)
        out[0] = 1
        for name, slot in ITEM_WEAPON_SLOT.items():
            if received.get(name):
                out[slot] = 1
        return bytes(out)

    @staticmethod
    def parts_mask(received: dict[str, int]) -> int:
        mask = 0
        for part in names.PARTS:
            if received.get(part):
                mask |= 1 << names.PART_ID[part]
        return mask

    @staticmethod
    def bolt_count(bundles: int, bundle_size: int, lab_bought: int) -> int:
        """Absolute bolt counter: what the player was sent, less what they
        spent in the Lab. u16 in the game; never negative."""
        spent = sum(price for part, price in LAB_PRICE_BY_ID.items() if lab_bought & (1 << part))
        return max(0, min(0xFFFF, bundles * bundle_size - spent))

    # ---- detection ---------------------------------------------------------

    @staticmethod
    def detect(weapons: bytes, live: bytes, progress: bytes, ap: bytes) -> set[str]:
        """Location names the game's records (and the AP block's) say are done."""
        found: set[str] = set()
        for slot, boss in SLOT_TO_BOSS.items():
            if weapons[4 * slot]:
                found.add(names.boss_location(boss))
        if weapons[4 * names.WEAPON_SLOT[names.MEGA_BALL]]:
            found.add(names.MEGA_BALL_LOCATION)
        field = int.from_bytes(live[OFF_BOLT_FIELD:OFF_BOLT_FIELD + 5], "little")
        for sub_id, location in BOLT_LOCATIONS.items():
            if field & (1 << sub_id):
                found.add(location)
        for k, adapter in enumerate(names.RUSH):
            if ap[AP_OFF_RUSH + k]:
                found.add(names.midboss_location(names.RUSH_STAGE[adapter]))
        lab = _u32(ap, AP_OFF_LAB)
        for part in names.PARTS:
            if lab & (1 << names.PART_ID[part]):
                found.add(names.shop_location(part))
        phase, wily = progress[0], progress[1]
        if phase >= PHASE_DUO_CLEARED:
            found.add(names.DUO_CLEAR)
        for n, wily_stage in enumerate(names.WILY_STAGES[:3], start=1):
            if wily >= n:
                found.add(names.WILY_CLEAR[wily_stage])
        return found

    @staticmethod
    def goal_reached(goal: int, weapons: bytes, progress: bytes) -> bool:
        if goal == GOAL_ROBOT_MASTERS:
            return all(weapons[4 * slot] for slot in SLOT_TO_BOSS)
        return progress[1] >= WILY_CLEARS_FOR_GOAL

    # ---- the poll ------------------------------------------------------------

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        if ctx.slot_data is None or ctx.server is None:
            return
        try:
            ap, weapons, live, persist_rush, progress, demo, overlay, hp, mirror, cur_weapon, sig = await bizhawk.read(
                ctx.bizhawk_ctx, [
                    (AP_ADDR, AP_LEN, "MainRAM"),
                    (WEAPONS_ADDR, WEAPONS_LEN, "MainRAM"),
                    (LIVE_ADDR, LIVE_LEN, "MainRAM"),
                    (PERSIST_RUSH_ADDR, 4, "MainRAM"),
                    (PROGRESS_ADDR, PROGRESS_LEN, "MainRAM"),
                    (DEMO_TIMER_ADDR, 4, "MainRAM"),
                    (OVERLAY_ADDR, 4, "MainRAM"),
                    (HP_ADDR, 1, "MainRAM"),
                    (MIRROR_ADDR, MIRROR_LEN, "MainRAM"),
                    (CUR_WEAPON_ADDR, 1, "MainRAM"),
                    (GAME_SIG_ADDR, len(GAME_SIG), "MainRAM"),
                ])
        except bizhawk.RequestFailedError:
            return

        # A reset or power-cycle: RAM is cleared and the EXE is still streaming
        # back in. Nothing here is the game's yet - say nothing, do nothing.
        if sig != GAME_SIG:
            self.last_signature = None
            return
        # Policy 1.
        if ap[:4] != disc.AP_SIGNATURE or _u32(ap, 4) != disc.AP_VERSION:
            self._refuse("this is not a disc patched for this Archipelago version "
                         "(open your .apmm8 to build it)", grace=REFUSAL_GRACE)
            return
        want_stamp = ctx.slot_data.get("seed_stamp")
        if want_stamp is not None and _u32(ap, AP_OFF_STAMP) != want_stamp:
            self._refuse("this disc was patched for a different seed or slot")
            return
        self._accept()

        # Policy 2: the demo.
        if _u32(demo):
            self.last_signature = None
            return
        received = self._received(ctx)
        capability = self.capability(received)
        readback = bytes(weapons[4 * s + 1] for s in range(10))
        trusted = self.capability_written is None or readback == self.capability_written

        # ---- checks ----
        signature = (bytes(weapons[4 * s] for s in range(10)) + live[OFF_BOLT_FIELD:OFF_BOLT_FIELD + 5]
                     + progress[:2] + ap[AP_OFF_LAB:AP_OFF_RUSH + 4])
        stable = trusted and signature == self.last_signature
        self.last_signature = signature if trusted else None
        if stable:
            found = {location_table[name] for name in self.detect(weapons, live, progress, ap)}
            new = found - set(ctx.checked_locations) - self.sent
            if new:
                self.sent |= new
                await ctx.send_msgs([{"cmd": "LocationChecks", "locations": sorted(new)}])
            goal = ctx.slot_data.get("goal", GOAL_WILY)
            if not self.victory_sent and self.goal_reached(goal, weapons, progress):
                self.victory_sent = True
                await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

        # ---- grants (policy 3) ----
        writes: list[tuple[int, bytes, str]] = []
        for slot in range(10):
            if weapons[4 * slot + 1] != capability[slot]:
                writes.append((WEAPONS_ADDR + 4 * slot + 1, bytes([capability[slot]]), "MainRAM"))
        # Firing reads only the current weapon, never capability. Anything that
        # selects a weapon the player was not sent - the boss "weapon get"
        # demo (0x8010F160), an older disc's intro pickup, a savestate - goes
        # back to the buster.
        current = cur_weapon[0]
        if 1 <= current <= 9 and not capability[current]:
            writes.append((CUR_WEAPON_ADDR, bytes([0]), "MainRAM"))
        for k, adapter in enumerate(names.RUSH):
            want = 1 if received.get(adapter) else 0
            if live[OFF_LIVE_RUSH + k] != want:
                # A fresh grant also sets the byte the Rush menu reads, which
                # the game otherwise refreshes only at the next stage start.
                writes.append((LIVE_ADDR + OFF_LIVE_RUSH + k, bytes([want]), "MainRAM"))
                writes.append((PERSIST_RUSH_ADDR + k, bytes([want]), "MainRAM"))
        parts = self.parts_mask(received)
        if _u32(ap, AP_OFF_PARTS) != parts:
            writes.append((AP_ADDR + AP_OFF_PARTS, parts.to_bytes(4, "little"), "MainRAM"))
        # The game builds the effect flags from AP_PARTS at each stage start,
        # section start and purchase (P6); setting a new part's flag now makes
        # it work mid-stage too.
        for part_id in range(1, MIRROR_LEN):
            if parts & (1 << part_id) and not mirror[part_id]:
                writes.append((MIRROR_ADDR + part_id, bytes([1]), "MainRAM"))
        # A buster mode the player does not own (a savestate, a debug write)
        # goes back to the normal shot.
        shot = live[OFF_SHOT_SELECT]
        if shot and not parts & (1 << SHOT_PART_ID.get(shot, 0)):
            writes.append((LIVE_ADDR + OFF_SHOT_SELECT, bytes([0]), "MainRAM"))
        # Policy 5: Rush pickups the server already has.
        checked = set(ctx.checked_locations)
        for k, adapter in enumerate(names.RUSH):
            if not ap[AP_OFF_RUSH + k] and \
                    location_table[names.midboss_location(names.RUSH_STAGE[adapter])] in checked:
                writes.append((AP_ADDR + AP_OFF_RUSH + k, b"\x01", "MainRAM"))
        bolts = self.bolt_count(received.get(names.BOLTS, 0),
                                ctx.slot_data.get("bolt_bundle_size", 5), _u32(ap, AP_OFF_LAB))
        if int.from_bytes(live[OFF_BOLTS:OFF_BOLTS + 2], "little") != bolts:
            writes.append((LIVE_ADDR + OFF_BOLTS, bolts.to_bytes(2, "little"), "MainRAM"))

        # ---- consumables (policy 4), only in a stage ----
        in_stage = _u32(overlay) in STAGE_OVERLAYS
        processed = _u32(ap, AP_OFF_PROCESSED)
        if trusted and in_stage and processed < len(ctx.items_received):
            lives, cur_hp = progress[4], hp[0]
            energy_refill = False
            while processed < len(ctx.items_received):
                name = ctx.item_names.lookup_in_game(ctx.items_received[processed].item)
                if name == names.EXTRA_LIFE:
                    lives = min(LIVES_CAP, lives + 1)
                elif name == names.LIFE_ENERGY:
                    if not cur_hp:
                        break            # mid-death: never revive; wait for the respawn
                    cur_hp = HP_MAX
                elif name == names.WEAPON_ENERGY:
                    energy_refill = True
                processed += 1
            if lives != progress[4]:
                writes.append((PROGRESS_ADDR + 4, bytes([lives]), "MainRAM"))
            if cur_hp != hp[0]:
                writes.append((HP_ADDR, bytes([cur_hp]), "MainRAM"))
            if energy_refill:
                for slot in range(1, 10):
                    if capability[slot]:
                        writes.append((WEAPONS_ADDR + 4 * slot + 2,
                                       ENERGY_FULL.to_bytes(2, "little"), "MainRAM"))
            writes.append((AP_ADDR + AP_OFF_PROCESSED, processed.to_bytes(4, "little"), "MainRAM"))

        if writes:
            # Only while no demo has started and the disc is still this seed's.
            guards = [(DEMO_TIMER_ADDR, bytes(4), "MainRAM"),
                      (AP_ADDR + AP_OFF_STAMP, ap[AP_OFF_STAMP:AP_OFF_STAMP + 4], "MainRAM")]
            if await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards):
                self.capability_written = capability
