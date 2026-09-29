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
   every Robot Master "beaten" - and clears the bolt field. The demo runs
   exactly while the timer 0x801B2944 is non-zero (0x800FF4C0), so nothing is
   read or written then; and the weapon capability bytes must read back as
   the client last wrote them, which a demo's whole-entry swap breaks.
   Checks are also only sent once the check-driving bytes repeat across two
   polls (X5's rule: a single poll can land mid-load or mid-swap).

3. GRANTS ARE ABSOLUTE wherever the state allows (X6's policy 2): weapon
   capability (+1 of each entry), Rush, parts and the bolt counter are
   computed from the items received and written whole, so a reconnect or a
   savestate is a no-op. A weapon's capability arriving also fills its energy
   (the game fills only at a spawn). Bolts = bundles received x bundle size - the price
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

6. OPTIONS THAT LIVE HERE (parity plan). stage_unlocks writes 0xFF over a
   locked Robot Master's slot in the select's position table (0x801379A8,
   EXE data) - never 0, which is stage 0 and is accepted - and only over a
   table it recognises. An open stage_order locks Duo's slot the same way
   until phase 4 (the disc opens page 2 at phase 1; vanilla never shows
   Duo's slot before his turn). rematch_checks reads the game's own Wily 4 refight
   record 0x801C3378, only in Wily 4 with the player alive (the byte is
   other stages' scratch, and the game revokes a win if the player dies
   before the warp). death_link is X5's shape with MM8's kill: HP 0, which
   is what every death route in the game writes; a received death waits
   through pause, teleport-in and script holds, and is dropped outside a
   stage.

7. WILY 3'S BASS leaves no record: he is never killed, and nothing is
   written when he gives up. His check is his defeat STATE (top state 8 or
   10, several seconds of retreat and dialogue), read from the object array only while STAGE0C is
   resident. A win the client misses is replayed by playing Wily 3 again.
"""
import asyncio
import logging
import time
from typing import TYPE_CHECKING

from NetUtils import ClientStatus

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from . import disc, names
from .bolts import BOLT_LOCATIONS
from .locations import location_table
from .pickups import PICKUPS

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
AP_LEN = 0x30                           # through pickupsanity's FOUND / CONFIRMED
WEAPONS_ADDR = _ram(disc.WEAPONS)       # 16 entries x 4: +0 kill record, +1 capability,
WEAPONS_LEN = 10 * 4                    # +2..+3 energy (8.8); slots 0-9 matter
LIVE_ADDR = _ram(0x8016D2F0)            # bolts u16, 8 part slots, +0x0A, 40-bit bolt
LIVE_LEN = 0x14                         # field at +0x0B, live Rush at +0x10
PERSIST_RUSH_ADDR = _ram(0x801C3352)    # what the Rush menu reads
MIRROR_ADDR = _ram(0x801C3340)          # part id i's effect flag at +i
PROGRESS_ADDR = _ram(0x801C336C)        # phase, Wily count, stage index, loaded flag, lives,
PROGRESS_LEN = 0x0D                     # ... and at +0x0C the Wily 4 refight record 0x801C3378
OFF_REFIGHTS = 0x0C
DEMO_TIMER_ADDR = _ram(0x801B2944)
OVERLAY_ADDR = _ram(disc.OVL_BASE)      # the resident overlay's id; stages are 6..0x13
HP_ADDR = _ram(0x8015E283)
CUR_WEAPON_ADDR = _ram(0x8016DC08)      # the weapon slot in hand; firing reads only this
REFUSAL_GRACE = 10.0                    # seconds a missing AP block may last before we say so

# Game state (ram-notes 9f, 9i) [D]. gameMode indexes the game loop (3 = in a
# stage); gameMode2 the stage's sub-modes (0 section start, 1 play, 2 the
# death sequence, 3 section end).
GAMEMODE_ADDR = _ram(0x801CF840)        # + 4 = gameMode2
GAMEMODE_LEN = 5
GAMEMODE_STAGE = 3
MODE2_PLAY, MODE2_DEATH = 1, 2
# The player object's first two bytes: +0 alive, +1 the top state - 0 spawn,
# 1 teleport-in (HP refills to 40: a kill there is undone), 2 play, 3 dying,
# 4 held by a script (boss intro, after a boss dies).
PLAYER_ADDR = _ram(0x8015E23C)
TOP_PLAY, TOP_DYING = 2, 3
# 0x801B2993: the game's own "not in control" (section start, death, a boss's
# setup, Wily 4's warps); 0x801B2995: a section end, clear or Exit is pending.
CONTROL_ADDR = _ram(0x801B2993)         # + 2 = 0x801B2995
CONTROL_LEN = 3
PAUSED_ADDR = _ram(0x80170338)          # non-zero while the pause menu is open

# stage_unlocks: the select's position -> stage table, EXE data with a single
# reader. 0xFF at a position makes its confirm do nothing (0 would load stage 0).
SELECT_TABLE_ADDR = _ram(0x801379A8)
SELECT_LOCKED = 0xFF

# A disc from an older apworld (0.2.0 review M1): the Lab's price code, in the
# DEMO overlay (resident at the Lab and the stage select, at the stage
# overlays' base), still adding vanilla's 20 - 0.1.0's prices drew as NO /
# CANCEL. DEMO is known by two words no stage overlay has there: the price
# read `lbu a2, 0x2859(a2)` and its state table's first entry, the init.
LAB_PRICE_CODE_ADDR = _ram(0x801DAD6C)  # the price read; +8 = disc.LAB_PRICE_DIGITS' addiu
LAB_PRICE_READ = 0x90C62859
LAB_STATES_ADDR = _ram(0x801DC050)
LAB_STATES_FIRST = 0x801DA48C

# rematch_checks: 0x801C3378 is also scratch in Sword Man's and Wily 3's
# stages, so it is read only in Wily 4 with its overlay resident.
WILY_4_STAGE, WILY_4_OVERLAY = 13, 0x13

# Wily Stage 3's Bass (names.WILY_3_BASS). No record survives his fight, so
# the check is the game's own defeat STATE: his dispatcher (STAGE0C
# 0x801E5BC4, table 0x801EAFD8 by top state obj+1) moves him to 8 when his hit
# handler reports "defeated" (0x801E5C1C) - a retreat - and 8 hands over to 10
# (0x801E65C0): the parting dialogue, the bar cleared, the object deleted.
# Several seconds in all (state 10's dialogue alone ran ~170 frames live,
# 2026-09-25), read only with STAGE0C resident.
MAIN_ARRAY_ADDR = _ram(0x8015B174)      # 64 objects x 0x60: +0 alive, +1 top state, +6 id
MAIN_ARRAY_LEN = 64 * 0x60
WILY_3_STAGE, WILY_3_OVERLAY = 12, 0x12
BASS_ID = 0x5D
BASS_DEFEATED_STATES = (8, 10)

OFF_BOLTS, OFF_SHOT_SELECT, OFF_BOLT_FIELD, OFF_LIVE_RUSH = 0x00, 0x0A, 0x0B, 0x10
# 0x8016D2FA, the buster mode the pause screen picks: 0 normal, then Laser,
# Arrow, Auto Shoot = part ids 11-13 (R5). Saved with the live block.
SHOT_PART_ID = {1: 11, 2: 12, 3: 13}
MIRROR_LEN = 0x12                       # part ids 1-17's effect flags
AP_OFF_STAMP, AP_OFF_PARTS, AP_OFF_LAB, AP_OFF_RUSH, AP_OFF_PROCESSED = (
    a - disc.AP_BLOCK for a in (disc.AP_STAMP, disc.AP_PARTS, disc.AP_LAB,
                                disc.AP_RUSH, disc.AP_PROCESSED))
AP_OFF_FOUND = disc.AP_PICKUP_FOUND - disc.AP_BLOCK
AP_OFF_CONFIRMED = disc.AP_PICKUP_CONFIRMED - disc.AP_BLOCK
PICKUP_NAMES = [name for _s, _r, _k, name in PICKUPS]      # bit i = PICKUPS[i]
STAGE_OVERLAYS = range(6, 0x14)
HP_MAX = 40                             # [L] vanilla; a seed's max_life (slot data) replaces it
LIVES_CAP = 9                           # the game's own: the 1-UP pickup clamps at 9 (0x80128D10)
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
        # _describe_parts: the Lab parts already accounted for, None while a
        # login's reply is being read (its items become the baseline). Kept
        # here, not in _reset: a disc reload re-validates the ROM, and that
        # must not make every owned part "new".
        self.parts_known: frozenset[str] | None = None
        self._reset()

    def _reset(self) -> None:
        self.last_signature: bytes | None = None
        self.refusal: str | None = None       # the reason currently in force
        self.refusal_since: float | None = None
        self.refusal_logged = False
        self.capability_written: bytes | None = None
        self.victory_sent = False
        # DeathLink (X5's latches). `sending_death_link` STARTS True - "a
        # death is already accounted for" - so a client attaching mid-death
        # does not send one; it re-arms only once the player is seen alive.
        self.pending_death_link = False
        self.sending_death_link = True
        self.unlocked_logged: frozenset[str] = frozenset()
        self.stale_disc_logged = False       # _warn_stale_disc says it once

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

    def _warn_stale_disc(self, lab_code: bytes, lab_states: bytes) -> None:
        """Say once, while the Lab or the stage select is up, that this disc
        was made by an older apworld (LAB_PRICE_CODE_ADDR) - 0.1.0 and 0.2.0
        share the AP block's format, so nothing else tells the two apart.
        Opening the .apmm8 again rebuilds it (Rom.patch compares every byte)."""
        if self.stale_disc_logged or _u32(lab_code) != LAB_PRICE_READ or _u32(lab_states) != LAB_STATES_FIRST:
            return
        if lab_code[8:12] == disc.LAB_PRICE_DIGITS[1][3]:           # vanilla's `addiu a2, a2, 20`
            self.stale_disc_logged = True
            logger.warning("Mega Man 8: this Lab comes from a disc made by an older Mega Man 8 apworld (or a "
                           "savestate taken on one), so its prices show as NO / CANCEL. Close BizHawk and open "
                           "your .apmm8 again - that rebuilds the disc.")

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

    def on_package(self, ctx: "BizHawkClientContext", cmd: str, args: dict) -> None:
        if cmd == "Connected":
            # A fresh login. The goal is latched per session, and a
            # StatusUpdate lost with the old socket would otherwise never go
            # out again; the server ignores a repeat.
            self.victory_sent = False
            # The login's reply is ONE websocket frame, [Connected,
            # ReceivedItems?] - the ReceivedItems only if the slot has items
            # (MultiServer's Connect). CommonClient reads a frame with no
            # await between the two on_package calls, so a callback queued
            # now runs only once the frame is done: whatever the login
            # brought is the baseline, and an empty login leaves it empty.
            self.parts_known = None
            try:
                asyncio.get_running_loop().call_soon(self._end_login_frame)
            except RuntimeError:
                pass           # no loop (called directly): the next batch is the baseline
            return
        if cmd == "ReceivedItems":
            self._describe_parts(ctx)
            return
        if cmd != "Bounced" or "DeathLink" not in args.get("tags", []):
            return
        # Our own bounce comes back to us; core's timestamp filter does not
        # cover this hook, so match on source (X5, after mm3).
        if (args.get("data") or {}).get("source") == ctx.player_names.get(ctx.slot):
            return
        self.pending_death_link = True

    def _end_login_frame(self) -> None:
        if self.parts_known is None:
            self.parts_known = frozenset()      # the login brought no items

    def _describe_parts(self, ctx: "BizHawkClientContext") -> None:
        """One short line per Lab part as it arrives, beside the server's
        "found their ..." (names.PART_EFFECT_SHORT) - the only place a player
        learns what a part does. New arrivals only (Ivor: "not important for
        reconnects"): the parts a login brings are the baseline, and after
        that every part not yet known gets its line once, from
        ctx.items_received (which core has already updated).

        Not from the batch's index: 0.2.0 as first built stayed silent on an
        index-0 batch, taking it for a login's or a Sync's resend - but the
        server also numbers a slot's very FIRST items from 0 when the login
        brought none (send_index starts at 0), which is every fresh default
        seed (0.2.0 review m1)."""
        owned = [(item, ctx.item_names.lookup_in_game(item.item)) for item in ctx.items_received]
        parts = frozenset(name for _item, name in owned if name in names.PART_EFFECT_SHORT)
        if self.parts_known is None:
            self.parts_known = parts            # a login's items: silent
            return
        known = set(self.parts_known or ())
        for item, name in owned:
            if name not in names.PART_EFFECT_SHORT or name in known:
                continue
            known.add(name)
            effect = names.PART_EFFECT_SHORT[name]
            if name == names.EXIT and self._exit_moot(ctx, item.flags):
                effect = names.EXIT_EFFECT_WITH_OPTION_SHORT
            logger.info(f"Mega Man 8: {name} - {effect}")
        self.parts_known = frozenset(known)

    @staticmethod
    def _exit_moot(ctx: "BizHawkClientContext", flags: int) -> bool:
        """Whether exit_stage_anytime is on, so the Exit part does nothing. A
        0.1.0 seed's slot data does not say (0.2.0 review m2); its Exit item
        does - the option makes it filler (create_item), else it is useful."""
        option = (ctx.slot_data or {}).get("exit_stage_anytime")
        if option is not None:
            return bool(option)
        return not flags & 0b011

    def _drop_death_link(self, why: str) -> None:
        """A received death that can no longer land where it was meant to -
        outside a stage, in a demo, on another disc - is dropped, never
        carried into the next stage (X5: a mistimed kill costs more than a
        dropped one)."""
        if self.pending_death_link:
            self.pending_death_link = False
            logger.info(f"Mega Man 8: DeathLink arrived {why} - dropped")

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
    def select_table(received: dict[str, int], stage_unlocks: bool = True,
                     duo_locked: bool = False) -> bytes:
        """The stage select's position -> stage table. stage_unlocks: a Robot
        Master whose codes have not arrived confirms to nothing. `duo_locked`
        (an open stage_order before phase 4): Duo's page-2 slot, which the
        vanilla order never shows before his turn, confirms to nothing either.
        Everything else (stage 0, the Lab, Wily) stays vanilla."""
        table = bytearray(names.SELECT_TABLE_VANILLA)
        if stage_unlocks:
            for boss, position in names.SELECT_POSITION.items():
                if not received.get(names.access_item(boss)):
                    table[position] = SELECT_LOCKED
        if duo_locked:
            table[names.SELECT_DUO_POSITION] = SELECT_LOCKED
        return bytes(table)

    @staticmethod
    def rematches(progress: bytes, overlay: bytes, mode: bytes, player: bytes) -> int:
        """The Wily 4 refight record, or 0 when it cannot be trusted: outside
        Wily 4 (the byte is other stages' scratch) or with the player not
        alive in play (the game revokes a bit when the player dies before
        the warp back)."""
        if (progress[2] == WILY_4_STAGE and _u32(overlay) == WILY_4_OVERLAY
                and mode[0] == GAMEMODE_STAGE and mode[4] == MODE2_PLAY and player[0]):
            return progress[OFF_REFIGHTS]
        return 0

    @staticmethod
    def in_wily_3(progress: bytes, overlay: bytes, mode: bytes) -> bool:
        return (progress[2] == WILY_3_STAGE and _u32(overlay) == WILY_3_OVERLAY
                and mode[0] == GAMEMODE_STAGE)

    @staticmethod
    def bass_defeated(objects: bytes) -> bool:
        """Bass in his defeat states anywhere in the main object array (the
        array read only in Wily 3: ids are global, but only STAGE0C spawns him)."""
        return any(objects[o] and objects[o + 6] == BASS_ID and objects[o + 1] in BASS_DEFEATED_STATES
                   for o in range(0, len(objects), 0x60))

    @staticmethod
    def pickups_confirmed(checked: set[int]) -> int:
        """The CONFIRMED word: pickups the server already has, which the stub
        then lets heal as vanilla."""
        return sum(1 << bit for bit, name in enumerate(PICKUP_NAMES) if location_table[name] in checked)

    @staticmethod
    def detect(weapons: bytes, live: bytes, progress: bytes, ap: bytes,
               rematches: int = 0, pickups: bool = False, bass: bool = False) -> set[str]:
        """Location names the game's records (and the AP block's) say are done."""
        found: set[str] = set()
        if bass:
            found.add(names.WILY_3_BASS)
        for boss, bit in names.REMATCH_BIT.items():
            if rematches & (1 << bit):
                found.add(names.rematch_location(boss))
        if pickups:
            found_bits = int.from_bytes(ap[AP_OFF_FOUND:AP_OFF_FOUND + 8], "little")
            found.update(name for bit, name in enumerate(PICKUP_NAMES) if found_bits & (1 << bit))
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

    # ---- DeathLink ---------------------------------------------------------------

    async def _death_link(self, ctx: "BizHawkClientContext", mode: bytes, player: bytes,
                          hp: int, control: bytes, paused: int, ap: bytes) -> None:
        """One death out per death, one death in per DeathLink (X5's shape).

        DETECT by the stage's death sequence (gameMode2 2, ~184 frames, so a
        poll cannot miss it) or the player's top state 3. KILL by writing HP 0:
        unlike X5, that IS the engine's own kill - every death route in the
        game (enemy contact, pits, grabs, the instant kills) writes HP 0 and
        leaves the one check at 0x8010C1E4 to do the rest, and a player at HP 0
        cannot be re-hit (ContactMega returns first).

        A received death waits through the moments a kill cannot land - the
        pause menu, the teleport-in (which refills HP), a boss intro's hold, a
        section end - and is dropped only when the player leaves the stage.
        """
        if mode[0] != GAMEMODE_STAGE:
            self._drop_death_link("outside a stage")
            return
        dying = mode[4] == MODE2_DEATH or player[1] == TOP_DYING
        in_play = (mode[4] == MODE2_PLAY and player[0] and player[1] == TOP_PLAY and hp > 0)

        if self.pending_death_link:
            if dying:
                self.pending_death_link = False      # its intent is already met
                return
            if in_play and not control[0] and not control[2] and not paused:
                guards = [(DEMO_TIMER_ADDR, bytes(4), "MainRAM"),
                          (GAMEMODE_ADDR, bytes([GAMEMODE_STAGE]), "MainRAM"),
                          (GAMEMODE_ADDR + 4, bytes([MODE2_PLAY]), "MainRAM"),
                          (PLAYER_ADDR + 1, bytes([TOP_PLAY]), "MainRAM"),
                          (CONTROL_ADDR, bytes(1), "MainRAM"),
                          (CONTROL_ADDR + 2, bytes(1), "MainRAM"),
                          (PAUSED_ADDR, bytes(1), "MainRAM"),
                          (AP_ADDR + AP_OFF_STAMP, ap[AP_OFF_STAMP:AP_OFF_STAMP + 4], "MainRAM")]
                if await bizhawk.guarded_write(ctx.bizhawk_ctx, [(HP_ADDR, bytes(1), "MainRAM")], guards):
                    # Latch BEFORE the game can show the death, so the death
                    # we caused cannot go straight back out.
                    self.sending_death_link = True
                    self.pending_death_link = False
                    logger.info("Mega Man 8: DeathLink received - killed the player")
            return                                   # otherwise hold it

        if dying:
            if not self.sending_death_link:
                self.sending_death_link = True
                await ctx.send_death("Mega Man was destroyed.")
        elif in_play:
            # The only honest re-arm: seen alive, so the next death is new.
            self.sending_death_link = False

    # ---- the poll ------------------------------------------------------------

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        # `ctx.slot`, not just slot_data (X5): a reconnect leaves slot_data
        # from the last login and sets ctx.server as soon as the socket
        # opens, so until Connected arrives items_received is EMPTY - a poll
        # then stripped every grant (and re-granted them as fresh, refilling
        # spent energy), and sent checks to a server that drops them from an
        # unauthenticated client (pre-release review B4).
        if ctx.server is None or ctx.slot is None or ctx.slot_data is None:
            return
        try:
            await self._poll(ctx)
        except (bizhawk.RequestFailedError, bizhawk.NotConnectedError):
            # BizHawk went away mid-poll (closed, ROM unloaded, a timeout).
            # _bizhawk/context.py calls game_watcher outside its own try, so an
            # escape here ended the watcher for the rest of the session with
            # the window still looking alive (review B3). X5 catches it too.
            self.last_signature = None

    async def _poll(self, ctx: "BizHawkClientContext") -> None:
        try:
            (ap, weapons, live, persist_rush, progress, demo, overlay, hp, mirror, cur_weapon, sig,
             mode, player, control, paused, select, lab_code, lab_states) = await bizhawk.read(
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
                    (GAMEMODE_ADDR, GAMEMODE_LEN, "MainRAM"),
                    (PLAYER_ADDR, 2, "MainRAM"),
                    (CONTROL_ADDR, CONTROL_LEN, "MainRAM"),
                    (PAUSED_ADDR, 1, "MainRAM"),
                    (SELECT_TABLE_ADDR, len(names.SELECT_TABLE_VANILLA), "MainRAM"),
                    (LAB_PRICE_CODE_ADDR, 12, "MainRAM"),
                    (LAB_STATES_ADDR, 4, "MainRAM"),
                ])
        except bizhawk.RequestFailedError:
            return

        # A reset or power-cycle: RAM is cleared and the EXE is still streaming
        # back in. Nothing here is the game's yet - say nothing, do nothing.
        if sig != GAME_SIG:
            self.last_signature = None
            self._drop_death_link("during a reset")
            return
        # Policy 1.
        if ap[:4] != disc.AP_SIGNATURE or _u32(ap, 4) != disc.AP_VERSION:
            self._refuse("this is not a disc patched by this version of the Mega Man 8 apworld "
                         "(a savestate from another disc: reset; otherwise open your .apmm8 "
                         "again, which rebuilds an outdated disc)", grace=REFUSAL_GRACE)
            self._drop_death_link("with no patched disc running")
            return
        want_stamp = ctx.slot_data.get("seed_stamp")
        if want_stamp is not None and _u32(ap, AP_OFF_STAMP) != want_stamp:
            self._refuse("this disc was patched for a different seed or slot")
            self._drop_death_link("with another seed's disc running")
            return
        self._accept()
        self._warn_stale_disc(lab_code, lab_states)

        # Policy 2: the demo.
        if _u32(demo):
            self.last_signature = None
            self._drop_death_link("during the attract demo")
            return
        received = self._received(ctx)
        capability = self.capability(received)
        readback = bytes(weapons[4 * s + 1] for s in range(10))
        trusted = self.capability_written is None or readback == self.capability_written

        # ---- checks ----
        rematches = (self.rematches(progress, overlay, mode, player)
                     if ctx.slot_data.get("rematch_checks") else 0)
        pickupsanity = bool(ctx.slot_data.get("pickupsanity"))
        bass = False
        if self.in_wily_3(progress, overlay, mode):
            try:
                (objects,) = await bizhawk.read(ctx.bizhawk_ctx, [(MAIN_ARRAY_ADDR, MAIN_ARRAY_LEN, "MainRAM")])
            except bizhawk.RequestFailedError:
                return
            bass = self.bass_defeated(objects)
        signature = (bytes(weapons[4 * s] for s in range(10)) + live[OFF_BOLT_FIELD:OFF_BOLT_FIELD + 5]
                     + progress[:2] + ap[AP_OFF_LAB:AP_OFF_RUSH + 4] + bytes([rematches, bass])
                     + ap[AP_OFF_FOUND:AP_OFF_FOUND + 8])
        stable = trusted and signature == self.last_signature
        self.last_signature = signature if trusted else None
        if stable:
            found = {location_table[name]
                     for name in self.detect(weapons, live, progress, ap, rematches, pickupsanity, bass)}
            # Re-sent every stable poll until the server has it (X5): a send
            # can be lost with a dropping socket, and nothing else retries.
            new = found - set(ctx.checked_locations)
            if new:
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
                # A weapon arrives FULL, as vanilla's does: the game fills
                # energy only at the spawn refill (0x8010BE50, usable weapons
                # only), so one granted mid-stage stayed empty until the next
                # death or section start (playtest record 9, Wily 3).
                if capability[slot]:
                    writes.append((WEAPONS_ADDR + 4 * slot + 2, ENERGY_FULL.to_bytes(2, "little"), "MainRAM"))
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
        # pickupsanity: tell the stub which pickups the server already has
        # (checked here, a collect, or a previous session).
        if pickupsanity:
            confirmed = self.pickups_confirmed(checked)
            if int.from_bytes(ap[AP_OFF_CONFIRMED:AP_OFF_CONFIRMED + 8], "little") != confirmed:
                writes.append((AP_ADDR + AP_OFF_CONFIRMED, confirmed.to_bytes(8, "little"), "MainRAM"))
        # stage_unlocks: re-asserted every poll (a savestate can carry another
        # table), and only over bytes that are vanilla or locked - anything
        # else means this is not the table we think it is.
        # stage_order: an open order shows Duo's slot from phase 1; it stays
        # shut until the game's own turn for him (phase 4, his clear) - then
        # it opens for revisits, as vanilla's does.
        stage_unlocks = bool(ctx.slot_data.get("stage_unlocks"))
        open_order = bool(ctx.slot_data.get("stage_order"))
        if stage_unlocks or open_order:
            table = self.select_table(received, stage_unlocks,
                                      duo_locked=open_order and progress[0] < PHASE_DUO_CLEARED)
            if select != table and all(b in (v, SELECT_LOCKED)
                                       for b, v in zip(select, names.SELECT_TABLE_VANILLA)):
                writes.append((SELECT_TABLE_ADDR, table, "MainRAM"))
        if stage_unlocks:
            unlocked = frozenset(b for b in names.ROBOT_MASTERS if received.get(names.access_item(b)))
            if unlocked != self.unlocked_logged:
                self.unlocked_logged = unlocked
                logger.info(f"Mega Man 8: stages unlocked ({len(unlocked)}/8): "
                            + ", ".join(b for b in names.ROBOT_MASTERS if b in unlocked))

        # Only while no demo has started and the disc is still this seed's.
        base_guards = [(DEMO_TIMER_ADDR, bytes(4), "MainRAM"),
                       (AP_ADDR + AP_OFF_STAMP, ap[AP_OFF_STAMP:AP_OFF_STAMP + 4], "MainRAM")]
        if writes:
            if await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, base_guards):
                self.capability_written = capability

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
                    if not cur_hp or player[1] != TOP_PLAY:
                        # Mid-death: never revive. Teleporting in: the fill is
                        # still counting, and the flying sections' fill adds
                        # BEFORE it compares with the max (0x8010C138), so a
                        # write of the max there runs it past and round
                        # through 0 (research 2026-09-25, 6). Wait for play.
                        break
                    cur_hp = ctx.slot_data.get("max_life", HP_MAX)
                elif name == names.WEAPON_ENERGY:
                    energy_refill = True
                processed += 1
            batch: list[tuple[int, bytes, str]] = []
            if lives != progress[4]:
                batch.append((PROGRESS_ADDR + 4, bytes([lives]), "MainRAM"))
            if cur_hp != hp[0]:
                batch.append((HP_ADDR, bytes([cur_hp]), "MainRAM"))
            if energy_refill:
                for slot in range(1, 10):
                    if capability[slot]:
                        batch.append((WEAPONS_ADDR + 4 * slot + 2,
                                      ENERGY_FULL.to_bytes(2, "little"), "MainRAM"))
            batch.append((AP_ADDR + AP_OFF_PROCESSED, processed.to_bytes(4, "little"), "MainRAM"))
            # Its own write, guarded on everything it was computed from (X5):
            # a death, a 1-Up picked up, a stage change or a same-seed
            # savestate between the read and the write would otherwise have
            # a heal land on a dying player, a lives change undone, or the
            # processed count rewound or advanced - items applied twice or
            # skipped (review M3). A refused batch is simply retried.
            guards = base_guards + [
                (AP_ADDR + AP_OFF_PROCESSED, ap[AP_OFF_PROCESSED:AP_OFF_PROCESSED + 4], "MainRAM"),
                (PROGRESS_ADDR + 4, progress[4:5], "MainRAM"),
                (OVERLAY_ADDR, overlay, "MainRAM")]
            if cur_hp != hp[0]:
                guards += [(HP_ADDR, hp, "MainRAM"),
                           (PLAYER_ADDR + 1, bytes([TOP_PLAY]), "MainRAM")]
            await bizhawk.guarded_write(ctx.bizhawk_ctx, batch, guards)

        # ---- DeathLink ----
        if ctx.slot_data.get("death_link"):
            # Keyed on the TAG (X5): update_death_link is a no-op once it is
            # present, and a reconnect that rebuilt the tags re-registers us.
            if "DeathLink" not in ctx.tags:
                await ctx.update_death_link(True)
            await self._death_link(ctx, mode, player, hp[0], control, paused[0], ap)
        else:
            self.pending_death_link = False
