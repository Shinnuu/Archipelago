"""BizHawkClient for Mega Man X6 (PS1, SLUS-01395, NTSC-U).

First cut. What works: the game is identified, checks are detected from the
persistent save struct, and received items are applied by writing it back.
Every address is from the verified map in the private mmx6-ap-research repo.

Four deliberate v0.1 policies, each with its reason. Read these before
changing anything - three of them are the difference between a safe client
and one that sends checks nobody earned.

1. WEAPONS ARE NOT GRANTED. `0x800CCF30` is simultaneously "stage beaten" and
   "weapon available" - one bit, both meanings. Writing it to grant a weapon
   would fabricate a boss-defeat check and advance story progress. That cannot
   be fixed client-side; it needs the disc patch to decouple the READER (ship
   plan A1). Until then you get each Maverick's weapon by beating them,
   vanilla-style, and the AP weapon items arrive but do nothing in-game.

2. GRANTS ARE ABSOLUTE, NEVER INCREMENTAL. The life and weapon gauges are
   computed from the items received and written whole (never decreasing), so
   re-applying after a reconnect is a no-op. X5 needed a memcard-persisted
   counter to make incremental grants safe; computing the target instead
   removes the problem rather than guarding it.

3. BITS THAT HIDE THEIR OWN PICKUP ARE WITHHELD. Setting an armor-part or tank
   bit makes that pickup stop spawning, which would make its location
   permanently uncollectable. So a granted bit is held back until its location
   is checked. Straight from X5, where the same trap needed a disc patch to
   fix properly. The withholding is always a bounded delay: every capsule and
   tank is reachable, so nothing is stranded.

4. GAUGE BITS ARE NEVER WRITTEN. Heart Tanks, Life Ups and Energy Ups are
   granted by writing the GAUGE only (`0x800CCF2B` / `0x800CCF31`), never the
   record bits. That leaves `0x800CCF3C/3D/3F` purely player-collected, so
   detection off them cannot confuse an AP grant for a pickup.

Telling this seed's save from another one, WITHOUT a stamp: X5 writes a
seed/slot stamp into a spare save byte. X6 cannot copy that - its memcard
re-serialises the save rather than copying it, so a byte that looks completely
free in RAM may never reach the card at all. Instead the answer is derived from
what the SERVER already knows: baseline locations are sent only if this slot
has already checked something, which proves the save belongs to a run of this
seed. A progressed save on a slot with no history is held back with an
explanation. Needs no save byte and cannot be defeated by a card layout we do
not fully understand.
"""
import logging
from typing import TYPE_CHECKING

from NetUtils import ClientStatus

logger = logging.getLogger("Client")

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from . import names, reploids
from .locations import location_table

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

# ---- Identification --------------------------------------------------------
# PS1 address 0x80xxxxxx maps to BizHawk "MainRAM" offset addr - 0x80000000.
# The boot EXE loads its text at 0x80010000 (header-declared, and read straight
# off our own disc: PS-X EXE, t_addr 0x80010000, size 0x7F000). The first thing
# there is a pointer word followed by the container path literal - the same
# shape X5 uses, with its own filename.
EXE_SIG_ADDR = 0x010000
# rb"" on purpose: a plain b"\ROCK..." makes Python read \R as an unknown
# escape. It happens to survive as a literal backslash, with a
# SyntaxWarning - and the same escape silently killed an entire research
# script once. Never write this one unraw.
EXE_SIG = bytes([0x60, 0x98, 0x0E, 0x80]) + rb"\ROCK_X6.DAT;1"

# ---- Save struct -----------------------------------------------------------
# One read per cycle covers everything: screen, stage, progress, every item
# bitfield, both gauges, souls, and the live Reploid array.
SAVE_BASE = 0x0CCED0
SAVE_LEN = 0x180                       # through the Nightmare Effects bytes

def _off(addr: int) -> int:
    return (addr - 0x80000000) - SAVE_BASE

OFF_SCREEN = _off(0x800CCED0)          # 00 game start, 02 stage select,
                                       # 0A ingame, 0C mission report
OFF_STAGE_IDX = _off(0x800CCEDC)       # read it, never infer - two encodings
OFF_CHAR = _off(0x800CCF08)            # 00 X, 01 Zero
OFF_LIVES = _off(0x800CCF09)
OFF_LIFE_GAUGE = _off(0x800CCF2B)      # 32 base -> 64 max, +2 per upgrade
OFF_ARMOR_SELECT = _off(0x800CCF2F)    # +1 Falcon +2 Shadow +4 Blade
                                       # +8 Ultimate +10 Zero +20 Black Zero
OFF_BEATEN = _off(0x800CCF30)          # beaten stages AND weapons - see policy 1
OFF_WEAPON_GAUGE = _off(0x800CCF31)    # 48 base -> 64 max
OFF_PROGRESS = _off(0x800CCF36)        # 0 fresh, 1 intro cleared, 2 stage
                                       # select reached, >=3 endgame unlocked
OFF_DIFFICULTY = _off(0x800CCF38)      # 00 easy, 01 normal, 02 xtreme
OFF_ARMOR_PARTS = _off(0x800CCF39)     # Blade helm/arms/body/legs then Shadow
OFF_TANKS = _off(0x800CCF3B)
OFF_HEARTS = _off(0x800CCF3C)
OFF_LIFE_UPS = _off(0x800CCF3D)
OFF_ENERGY_UPS = _off(0x800CCF3F)
OFF_PARTS = _off(0x800CCF40)           # 4 bytes, 24 Parts
OFF_SOULS_X = _off(0x800CCFA2)         # u16, endgame gate at 3000
OFF_SOULS_Z = _off(0x800CCFA4)
OFF_REPLOIDS = _off(0x800CCFA8)        # LIVE array, 64 bytes

SCREEN_INGAME = 0x0A
SCREEN_MISSION_REPORT = 0x0C
# The save is believed only on these two. The beaten bit and every Reploid
# reward commit ~290 frames into the Mission Report, so it has to be trusted
# as well as gameplay - it is where half the checks actually land.
TRUSTED_SCREENS = frozenset({SCREEN_INGAME, SCREEN_MISSION_REPORT})

LIFE_GAUGE_BASE, LIFE_GAUGE_MAX = 32, 64
WEAPON_GAUGE_BASE, WEAPON_GAUGE_MAX = 48, 64
GAUGE_STEP = 2

ARMOR_BIT_ZERO = 0x10
ARMOR_BIT_ULTIMATE = 0x08
ARMOR_BIT_BLACK_ZERO = 0x20

SOULS_GATE = 3000

# ---- Ending detection --------------------------------------------------------
# Victory fires on the post-Sigma ENDING SCREEN, not on the endgame being
# unlocked. The previous rule fired on `endgame open (+ 8 kills for
# all_mavericks)`, which meant neither goal ever required beating Sigma at all -
# the `sigma` goal, documented as "defeat Sigma, however you got there",
# completed the moment the soul counter crossed 3000, mid-stage, in a Maverick
# stage, having never entered a lab.
#
# 0x10 is "End credits" in the Tweaks workbook's screen table [W]. X5's
# equivalent was live-captured as 0A -> 13 -> 14 -> 10 -> 11 after the final
# blow, with 13/14 shared with a non-final cutscene.
#
# 0x10 ALONE IS NOT OBSERVABLE, and watching only for it was a latent bug that
# would have made the goal essentially never fire. Disassembly, 2026-08-26:
# the main loop at 0x8001E700 reads this byte, scales it by 4, indexes the
# screen-handler table at 0x8007112C (entries 0x00-0x18) and calls through it
# every frame. Screen 0x10's handler is 0x8001ED44, and its THIRD instruction
# is an unconditional `sb v0, 0x0(a0)` with v0 = 0x11 - it rewrites the screen
# byte to 0x11 before doing anything else, then returns. So 0x10 survives
# exactly one dispatcher iteration (~16.7 ms) while the BizHawk watcher polls
# at `watcher_timeout` = 0.5 s: roughly a 3% chance of ever seeing it.
#
# 0x11 is the state that HOLDS - X5's live capture recorded "0x11 (credits,
# holds)" - and it is reachable ONLY from 0x10's handler, which is the sole
# writer of 0x11 in the whole EXE. So watching 0x11 is exactly as specific as
# watching 0x10, and unlike 0x10 it can actually be caught. Both are accepted:
# 0x10 still fires on a lucky poll, 0x11 is the one that reliably does.
#
# NOT YET SEEN LIVE. Nobody has reached X6's credits with the client attached.
SCREEN_END_CREDITS = 0x10
SCREEN_END_CREDITS_HELD = 0x11
ENDING_SCREENS = frozenset({SCREEN_END_CREDITS, SCREEN_END_CREDITS_HELD})

# Spare save-struct bytes: bytes that never moved across a full multi-stage
# session and are not in any region we have mapped. NOT used by anything here -
# the baseline gate above removed the need for a stamp - but kept because they
# are the starting point if a stamp is ever wanted for another reason.
# "Did not move once" is not "unused", and none has been tested. Note also that
# the memcard re-serialises, so a free RAM byte may not persist at all.
STAMP_CANDIDATES = (
    (0x800CCF7B, 29),
    (0x800CCF0D, 30),
    (0x800CCF4C, 16),
    (0x800CD02A, 15),
    (0x800CCF6F, 11),
)

# ---- Filler -----------------------------------------------------------------
# Consumables, and they are the one thing here that CANNOT be idempotent: a
# heal has to land once, not be reasserted every poll. So they are the only
# grant driven by a cursor into ctx.items_received rather than by absolute
# state. The cursor is in memory and starts at whatever the list already holds
# on connect, so a reconnect skips filler rather than re-applying it - for a
# consumable that is the right way round to be wrong.
#
# One read of the live player object covers HP, the current weapon index and
# the whole ammo array, so filler needs no extra round trips. The live block is
# only valid in gameplay, so a heal or refill waits for a stage rather than
# being dropped.
PLAYER_BASE = 0x0970A0
PLAYER_LEN = 0xCA                      # through the capability byte (+0xC9)
OFF_P_HP = 0x5C                        # low 7 bits; bit 0x80 is a hit/heal FLAG
OFF_P_WEAPON_IDX = 0x93                # which ammo slot the buster/weapon uses
OFF_P_AMMO = 0xA8                      # 16 x u16, confirmed live
# The live weapon capability. Copied from 0x800CCF30 on a vanilla disc and
# from AP_WEAPONS on a patched one, at stage start. Read-only here - it is the
# single best evidence that the A1 patch is actually taking effect.
OFF_P_CAPABILITY = 0xC9
AMMO_SLOTS = 16
PLAYER_HP_ADDR = PLAYER_BASE + OFF_P_HP
PLAYER_HP_MASK = 0x7F

# Live ammo max = weapon gauge x 6, MEASURED (15 slots at 300 against a gauge
# of 50) and matching X5 exactly (288 = 48 x 6). But the live max is LATCHED AT
# STAGE START and does not follow a mid-stage write, so an Energy Up granted
# now does not raise it until the next stage. Cap against what is actually in
# the array and fall back to the computed value only if the array reads empty -
# that way a refill can never overfill past what the game itself is using.
WEAPON_AMMO_SCALE = 6
SMALL_WEAPON_FRACTION = 8              # 1/8 of the max
LARGE_WEAPON_FRACTION = 2              # 1/2 of the max

# Amounts are GUESSES, tunable - the research notes record that X6 heals
# gradually (~1 HP per 2 frames) but never how much each capsule is worth.
SMALL_LIFE_HEAL = 4
LARGE_LIFE_HEAL = 16
# Observed, not assumed: across 38 transitions of this byte in a recorded
# play session the stock reached 9 eight separate times and never 10.
LIVES_CAP = 9

# ---- AP disc patch ----------------------------------------------------------
# The A1 patch redirects the weapon capability away from 0x800CCF30 (which is
# simultaneously the kill record) to a byte AP owns. Three sites copy the
# capability into the live player object; the patch changes the source
# immediate at each from 0x60 to 0xAB.
#
# One of those sites is in the static EXE and therefore always resident, so it
# doubles as the probe. The overlay site is not reliably in RAM, so it is NOT
# used for detection.
PATCH_PROBE_ADDR = 0x03C278                  # RAM 0x8003C278
PATCH_PROBE_VANILLA = bytes.fromhex("6000a290")   # lbu v0, 0x60(a1)
PATCH_PROBE_PATCHED = bytes.fromhex("ab00a290")   # lbu v0, 0xab(a1)

# The AP-owned save block. Untouched by any of the 1,719 save-struct accesses
# across the EXE and every overlay. It does NOT persist to the memcard - X6
# re-serialises the save field by field, so a byte no serialiser mentions never
# reaches the card - which is why the client rewrites it every cycle rather
# than assuming it survives.
AP_WEAPONS = 0x800CCF7B
OFF_AP_WEAPONS = _off(AP_WEAPONS)

GOAL_SIGMA = 0
GOAL_ALL_MAVERICKS = 1

# ---- Stage unlocks -----------------------------------------------------------
# The stage-select overlay turns a cursor slot into a stage id through an
# 8-byte table and refuses to act on a zero, exactly like X5's hub:
#
#   zero the slot -> confirming that icon does nothing, and the icon greys out
#
# Researched live 2026-08-26. The table is ROCK_X6.BIN +0x0C5B4C, resident at
# 0x800F0BAC (container -> RAM delta 0x8002B060, agreed on by three separate
# rows). Two more rows follow it, and they are the SAME table re-encoded - the
# second 0-based, the third that one's inverse. Only the first gates entry:
# each was zeroed on its own and the stage tried. DO NOT write the other two.
SLOT_TABLE = names.SLOT_TABLE_ADDR - 0x80000000
SLOT_TO_STAGE_ID = names.SLOT_TO_STAGE_ID
STAGE_ID_TO_NAME = {i + 1: stage for i, stage in enumerate(names.STAGES)}

# Residency anchor: the two rows we never write. They are constants, so reading
# their vanilla values proves the stage-select overlay is what is mapped there.
# The table is reloaded from disc on every hub entry, so the lock has to be
# re-asserted every cycle rather than written once - and writing 8 bytes into
# whatever module happens to occupy that address in a stage would be corruption.
SLOT_ANCHOR = names.SLOT_TABLE_ANCHOR_ADDR - 0x80000000
SLOT_ANCHOR_BYTES = names.SLOT_TABLE_ANCHOR

# A blocked confirm stores the stage id BEFORE the game tests it for zero, so
# it leaves 0x800CCEDC reading 0000 with the player still in the hub. In that
# encoding 0000 is the INTRO STAGE and vanilla never writes it there, so an
# in-hub save would commit it. Observed four times in the research session.
HUB_STAGE_INDEX = names.HUB_STAGE_INDEX
STAGE_SELECT_SCREENS = frozenset(names.STAGE_SELECT_SCREENS)

PROGRESS_STAGE_SELECT = names.PROGRESS_STAGE_SELECT
PROGRESS_ENDGAME_OPEN = names.PROGRESS_ENDGAME_OPEN



class MMX6Client(BizHawkClient):
    game = "Mega Man X6"
    system = "PSX"
    # Registers ".apmmx6" with the BizHawk Client launcher component
    # (worlds/_bizhawk/client.py reads this attribute). WITHOUT it the
    # Launcher's Open Patch dialog does not list the extension, so a player
    # who double-clicks their patch is never prompted for their disc image.
    # A tester hit exactly that on the X5 v0.1.0 release.
    patch_suffix = ".apmmx6"

    def __init__(self) -> None:
        super().__init__()
        self._reset_state()

    def _reset_state(self) -> None:
        self.victory_sent = False
        self.sent_locations: set[int] = set()
        # Trust: the save is believed only once the check-driving bytes repeat
        # across two consecutive polls on a trusted screen. Stale RAM never
        # changes, so a signature alone is not enough - the previous poll must
        # also have been trusted, or a single poll landing in a gameplay mode
        # during a stage load would be believed off a signature the title
        # screen established. Straight from X5, where this was the fix for
        # phantom checks.
        self.last_check_sig: bytes | None = None
        self.last_poll_trusted = False
        self.baseline_resolved = False
        # Locations already set in the save that we are deliberately NOT
        # sending, because we cannot yet tell this seed's save from another's.
        self.baseline_held: set[int] = set()
        self.weapons_notice_logged = False
        # None = not yet determined (a probe during boot reads zeros).
        # False specifically means "read the exact vanilla word".
        self.ap_patched: bool | None = None
        self.capability_logged = False
        self.withheld_logged: set[str] = set()
        # How far into ctx.items_received the filler grants have got. None
        # means "not started"; it is set to the list length on the first
        # trusted poll, so filler already in hand at connect is skipped.
        self.filler_cursor: int | None = None
        # Extra Lives that arrived while the stock was already at the cap.
        # Held rather than consumed: the cursor is strictly sequential, so
        # stalling on a full stock would also hold up every heal behind it,
        # and a life the player cannot receive yet is not a life they should
        # lose. Paid out as soon as the stock drops.
        self.pending_lives: int = 0
        # Last slot table written, so the log fires on change rather
        # than every poll. None means "not in the hub as far as we know".
        self.slot_table_written: bytes | None = None
        self.stages_unlocked_logged: set[str] = set()
        # Mavericks beaten, accumulated across TRUSTED polls and never
        # read at goal time: the save struct is not sane during the
        # ending, so a read taken then could score anything. Latching
        # means it must be gated on trust - X5 shipped the equivalent
        # counter on a weaker gate and a single stale 0xFF read would
        # have scored 8 permanently and handed out a false victory.
        self.mavericks_defeated = 0
        self.short_ending_warned = False
        # Endgame gate: whether we are currently holding the Gate shut, and
        # whether we have already said it is too late to. Both are log
        # de-duplication only - the gate itself is recomputed every poll, so
        # losing these to a reconnect costs a repeated line and nothing else.
        self.endgame_gate_held = False
        self.endgame_gate_missed = False

    # ---- identification ----------------------------------------------------

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        try:
            sig, probe = await bizhawk.read(ctx.bizhawk_ctx, [
                (EXE_SIG_ADDR, len(EXE_SIG), "MainRAM"),
                (PATCH_PROBE_ADDR, 4, "MainRAM"),
            ])
        except bizhawk.RequestFailedError:
            return False
        if sig != EXE_SIG:
            return False
        self.ap_patched = self._classify_probe(probe)
        logger.info(
            "MMX6: disc is %s (probe at 0x%08X read %s)",
            {True: "AP-PATCHED - weapons will be granted",
             False: "VANILLA - weapons come from beating Mavericks",
             None: "UNDETERMINED, will re-probe in game"}[self.ap_patched],
            0x80000000 + PATCH_PROBE_ADDR, probe.hex())

        ctx.game = self.game
        ctx.items_handling = 0b111   # remote items, own-world items, start inv
        ctx.want_slot_data = True
        self._reset_state()
        return True

    @staticmethod
    def _classify_probe(probe: bytes) -> bool | None:
        """True = AP-patched, False = known vanilla, None = undetermined.

        None matters: validate_rom can race the EXE still streaming in from
        disc, and a probe of zeros must mean "retry", never "vanilla" - the
        difference decides whether weapons are granted at all.
        """
        if probe == PATCH_PROBE_PATCHED:
            return True
        if probe == PATCH_PROBE_VANILLA:
            return False
        return None

    # ---- item accounting ---------------------------------------------------

    @staticmethod
    def _received(ctx: "BizHawkClientContext") -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in ctx.items_received:
            name = ctx.item_names.lookup_in_game(item.item)
            counts[name] = counts.get(name, 0) + 1
        return counts

    def _checked(self, ctx: "BizHawkClientContext", location: str) -> bool:
        loc_id = location_table.get(location)
        return loc_id is not None and (
            loc_id in ctx.checked_locations or loc_id in self.sent_locations)

    # ---- detection ---------------------------------------------------------

    def _detect(self, ctx: "BizHawkClientContext", save: bytes) -> set[int]:
        """Location ids the save says are collected.

        Reads only fields the client never writes, or writes only after the
        location is already checked - see policies 3 and 4 in the module
        docstring. That is what keeps an AP grant from reading back as a
        pickup.
        """
        found: set[int] = set()

        def add(location: str) -> None:
            loc_id = location_table.get(location)
            if loc_id is not None:
                found.add(loc_id)

        # Intro clear. 0x800CCF36 is monotonic and persistent, and it is the
        # only durable marker for the intro - the beaten-stages byte does not
        # move for it, because the intro is not one of the eight Mavericks.
        progress = save[OFF_PROGRESS]
        if progress >= 1:
            add(names.INTRO_CLEAR)

        # Endgame clears ride the same counter. Its endgame values are
        # code-verified: the stage-select overlay branches on exactly 3 and 4
        # (ROCK+0x0C2798), choosing which Secret Lab the screen offers. Being
        # monotonic is the whole point - a clear cannot be un-earned by dying,
        # quitting or reloading an older save.
        #
        # Detected unconditionally, exactly as the Reploid block already is:
        # the client has no view of the slot's options, and the server ignores
        # location ids that are not in this slot. A seed generated with
        # endgame_checks off therefore just discards these.
        for name, threshold in names.ENDGAME_CHECKS:
            if progress >= threshold:
                add(name)

        beaten = save[OFF_BEATEN]
        hearts = save[OFF_HEARTS]
        armor = save[OFF_ARMOR_PARTS]
        tanks = save[OFF_TANKS]

        for stage in names.STAGES:
            bit = names.STAGE_BIT[stage]
            if beaten & bit:
                add(names.boss_location(stage))
            if hearts & bit:
                add(names.heart_location(stage))
            # Each stage holds exactly one armor part; its bit standing in for
            # the capsule is safe because a granted part bit is withheld until
            # this very location is checked.
            if armor & names.ARMOR_PART_BIT[names.STAGE_ARMOR_PART[stage]]:
                add(names.capsule_location(stage))
            tank_bit = names.TANK_BIT.get(stage)
            if tank_bit is not None and tanks & tank_bit:
                add(names.tank_location(stage))

        # Reploids: a nibble leaving 0 in the LIVE array. Deliberately ANY
        # non-zero state, not just 2 (rescued) - 3 (dead) and 4 (missing) are
        # permanent, so keying on 2 alone would let a Nightmare destroy up to
        # 128 checks, and in a multiworld a destroyed check is somebody else's
        # item gone for good. Paying out on a loss is the only direction that
        # cannot cost anyone anything.
        block = save[OFF_REPLOIDS:OFF_REPLOIDS + reploids.REPLOID_BLOCK_LEN]
        for _stage, index, _n, name in reploids.REPLOIDS:
            byte = block[index // 2]
            nibble = (byte >> 4) if index % 2 else (byte & 0x0F)
            if nibble != reploids.NOT_RESCUED:
                add(name)

        return found

    # ---- grants ------------------------------------------------------------

    def _grants(self, ctx: "BizHawkClientContext", save: bytes) -> list[tuple[int, bytes]]:
        """Writes that bring the save up to the items received.

        Every value is ABSOLUTE and monotonic: computed from the item counts,
        never added to what is there. Re-running this after a reconnect is a
        no-op, which is what removes X5's need for a memcard-persisted
        processed-items counter.
        """
        got = self._received(ctx)
        writes: list[tuple[int, bytes]] = []

        def write(offset: int, value: int, current: int) -> None:
            if value != current:
                writes.append((SAVE_BASE + offset, bytes([value])))

        # --- gauges (policy 4: gauge only, never the record bits) -----------
        # Vanilla pickups also raise these, so take the max rather than the
        # computed target: the player keeps anything they earned locally on
        # top of what AP sent, and the gauge never goes backwards.
        life_steps = got.get(names.HEART_TANK, 0) + got.get(names.LIFE_UP, 0)
        life_target = min(LIFE_GAUGE_MAX,
                          LIFE_GAUGE_BASE + GAUGE_STEP * life_steps)
        write(OFF_LIFE_GAUGE, max(save[OFF_LIFE_GAUGE], life_target),
              save[OFF_LIFE_GAUGE])

        weapon_target = min(WEAPON_GAUGE_MAX,
                            WEAPON_GAUGE_BASE
                            + GAUGE_STEP * got.get(names.ENERGY_UP, 0))
        write(OFF_WEAPON_GAUGE, max(save[OFF_WEAPON_GAUGE], weapon_target),
              save[OFF_WEAPON_GAUGE])

        # --- armor parts (policy 3: withhold until the capsule is checked) --
        armor_bits = save[OFF_ARMOR_PARTS]
        for stage, part in names.STAGE_ARMOR_PART.items():
            if not got.get(part):
                continue
            if not self._checked(ctx, names.capsule_location(stage)):
                self._log_withheld(part, names.capsule_location(stage))
                continue
            armor_bits |= names.ARMOR_PART_BIT[part]
        write(OFF_ARMOR_PARTS, armor_bits, save[OFF_ARMOR_PARTS])

        # --- tanks (same withholding rule) ----------------------------------
        # Sub Tank has two copies and no stage identity of its own, so the
        # first fills Yammark's bit and the second Heatnix's - in that order,
        # matching the bit mapping in the research notes.
        tank_bits = save[OFF_TANKS]
        wanted: list[tuple[str, int]] = []
        sub_stages = [s for s in names.STAGES if names.STAGE_TANK.get(s) == names.SUB_TANK]
        for i in range(got.get(names.SUB_TANK, 0)):
            if i < len(sub_stages):
                wanted.append((sub_stages[i], names.TANK_BIT[sub_stages[i]]))
        for item, stage in ((names.W_TANK, names.SHELDON),
                            (names.EX_TANK, names.WOLFANG)):
            if got.get(item):
                wanted.append((stage, names.TANK_BIT[stage]))
        for stage, bit in wanted:
            if not self._checked(ctx, names.tank_location(stage)):
                self._log_withheld(names.STAGE_TANK[stage],
                                   names.tank_location(stage))
                continue
            tank_bits |= bit
        write(OFF_TANKS, tank_bits, save[OFF_TANKS])

        # --- characters and secret armors ------------------------------------
        # 0x800CCF2F is a capability byte with no location reading off it, so
        # nothing here needs withholding.
        select = save[OFF_ARMOR_SELECT]
        if got.get(names.ZERO):
            select |= ARMOR_BIT_ZERO
        if got.get(names.ULTIMATE_ARMOR):
            select |= ARMOR_BIT_ULTIMATE
        if got.get(names.BLACK_ZERO):
            select |= ARMOR_BIT_BLACK_ZERO
        write(OFF_ARMOR_SELECT, select, save[OFF_ARMOR_SELECT])

        # --- equippable Parts -------------------------------------------------
        # Four bytes, no location reads them, so a plain OR is safe.
        parts = bytearray(save[OFF_PARTS:OFF_PARTS + 4])
        for name in names.PARTS:
            if not got.get(name):
                continue
            addr, mask = names.PART_BIT[name]
            parts[(addr - 0x800CCF40)] |= mask
        if bytes(parts) != save[OFF_PARTS:OFF_PARTS + 4]:
            writes.append((SAVE_BASE + OFF_PARTS, bytes(parts)))

        # --- weapons: only on a patched disc (policy 1) ----------------------
        # On vanilla, 0x800CCF30 is both the kill record and the weapon list,
        # so writing it would fabricate a boss check. The A1 patch redirects
        # the capability to AP_WEAPONS, which nothing else reads or writes -
        # so there it is safe, and it is the ONLY place weapons are granted.
        #
        # Written every cycle rather than once: AP_WEAPONS does not persist to
        # the memcard, and the game latches the capability at stage start, so
        # the byte has to be correct whenever a stage loads.
        if self.ap_patched:
            capability = 0
            for stage in names.STAGES:
                if got.get(names.BOSS_WEAPON[stage]):
                    capability |= names.STAGE_BIT[stage]
            write(OFF_AP_WEAPONS, capability, save[OFF_AP_WEAPONS])
        elif not self.weapons_notice_logged and any(
                got.get(w) for w in names.WEAPONS):
            self.weapons_notice_logged = True
            logger.info(
                "MMX6: this is an unpatched disc, so special weapons are not "
                "granted - the byte that holds them (0x800CCF30) is the same "
                "byte that records which Mavericks you have beaten, and "
                "writing it would fake a boss check. Beat a Maverick to get "
                "its weapon, as in the base game.")

        return writes

    def _filler_grants(self, ctx: "BizHawkClientContext", save: bytes,
                       player: bytes | None) -> tuple[list[tuple[int, bytes]], int]:
        """Apply consumables that have arrived since the cursor.

        `player` is the live player object, or None when there is no valid one
        (between stages, on the Mission Report). Returns (writes, new_cursor).
        Items are consumed strictly in order and the cursor stops at the first
        one that cannot be applied yet - a heal with no live player block waits
        for a stage rather than being thrown away, and nothing after it is
        skipped past.
        """
        lookup = ctx.item_names.lookup_in_game
        cursor = self.filler_cursor if self.filler_cursor is not None             else len(ctx.items_received)
        writes: list[tuple[int, bytes]] = []
        lives = save[OFF_LIVES]
        max_hp = save[OFF_LIFE_GAUGE]
        hp = (player[OFF_P_HP] & PLAYER_HP_MASK) if player else None

        # Ammo: the slot the player is actually using, and the live cap.
        ammo_slot = ammo = ammo_cap = None
        if player:
            index = player[OFF_P_WEAPON_IDX]
            if 0 <= index < AMMO_SLOTS:
                ammo_slot = index
                slots = [int.from_bytes(
                    player[OFF_P_AMMO + i * 2:OFF_P_AMMO + i * 2 + 2], "little")
                    for i in range(AMMO_SLOTS)]
                ammo = slots[index]
                # Cap against the array, not the save byte - the live max is
                # latched at stage start, so a just-granted Energy Up would
                # otherwise overfill until the next stage.
                ammo_cap = max(slots) or (save[OFF_WEAPON_GAUGE]
                                          * WEAPON_AMMO_SCALE)

        while cursor < len(ctx.items_received):
            name = lookup(ctx.items_received[cursor].item)
            if name == names.EXTRA_LIFE:
                if lives >= LIVES_CAP:
                    self.pending_lives += 1     # bank it, do not eat it
                else:
                    lives += 1
            elif name in (names.SMALL_LIFE_ENERGY, names.LARGE_LIFE_ENERGY):
                if hp is None:
                    break          # no live player block - wait for a stage
                amount = (SMALL_LIFE_HEAL if name == names.SMALL_LIFE_ENERGY
                          else LARGE_LIFE_HEAL)
                hp = min(max_hp, hp + amount)
            elif name in (names.SMALL_WEAPON_ENERGY, names.LARGE_WEAPON_ENERGY):
                if ammo is None:
                    break          # no live player block - wait for a stage
                fraction = (SMALL_WEAPON_FRACTION
                            if name == names.SMALL_WEAPON_ENERGY
                            else LARGE_WEAPON_FRACTION)
                ammo = min(ammo_cap, ammo + max(1, ammo_cap // fraction))
            cursor += 1

        # Pay out anything banked earlier, now that there may be room.
        while self.pending_lives and lives < LIVES_CAP:
            lives += 1
            self.pending_lives -= 1

        if lives != save[OFF_LIVES]:
            writes.append((SAVE_BASE + OFF_LIVES, bytes([lives])))
        if player:
            if hp != (player[OFF_P_HP] & PLAYER_HP_MASK):
                writes.append((PLAYER_HP_ADDR, bytes([hp & PLAYER_HP_MASK])))
            if ammo_slot is not None:
                addr = PLAYER_BASE + OFF_P_AMMO + ammo_slot * 2
                current = int.from_bytes(
                    player[OFF_P_AMMO + ammo_slot * 2:][:2], "little")
                if ammo != current:
                    writes.append((addr, ammo.to_bytes(2, "little")))
        return writes, cursor

    def _log_withheld(self, item: str, location: str) -> None:
        key = f"{item}@{location}"
        if key in self.withheld_logged:
            return
        self.withheld_logged.add(key)
        logger.info(
            "MMX6: holding back %s until you have checked '%s'. Setting its "
            "bit early would stop that pickup spawning and make the location "
            "impossible to collect. Go and check it and the item applies.",
            item, location)

    def _sendable(self, ctx: "BizHawkClientContext", found: set[int]) -> set[int]:
        """Which detected locations may actually be sent.

        The question on first contact: is this save one this seed has been
        played on? If the server has ALREADY recorded checks for this slot,
        yes - so anything extra in the save was collected while disconnected
        and should be sent. If the server has recorded NOTHING and yet the
        save is full of progress, a legitimate offline run and a save
        belonging to another seed look identical, and sending would release
        other players' items.

        This replaces the seed/slot stamp X5 writes into a spare save byte.
        X6 cannot copy that: its memcard re-serialises the save rather than
        copying it, so a byte that looks free in RAM may never reach the card
        at all. Deriving the answer from what the server already knows needs
        no save byte and cannot be defeated by a card layout we do not fully
        understand.
        """
        checked = set(ctx.checked_locations)
        if not self.baseline_resolved:
            self.baseline_resolved = True
            fresh = found - checked
            if fresh and not checked:
                self.baseline_held = fresh
                logger.warning(
                    "MMX6: holding back %d location(s) that are already "
                    "collected in this save. The server has no record of this "
                    "slot checking anything, so this could be a save from a "
                    "different seed - sending them would release other "
                    "players' items. If it IS this seed's save, collect any "
                    "one check and reconnect: the server will then have a "
                    "record and these will be sent automatically.",
                    len(fresh))
        return found - self.sent_locations - checked - self.baseline_held

    # ---- goal ----------------------------------------------------------------

    def _goal_decision(self, screen: int, goal: int) -> bool:
        """True when victory should be sent. Mutates only the warning latch.

        Deliberately free of I/O so it can be unit-tested. Nothing tested the
        goal before this - which is exactly how a rule that fired on a SOUL
        COUNT, with Sigma never fought, shipped unnoticed under a docstring
        promising "defeat Sigma".
        """
        if self.victory_sent:
            return False
        # An unpatched disc must not goal: a goal releases every remaining
        # location in this world. But an UNDETERMINED probe must not swallow a
        # real ending either - the credits can clobber the probe region, and
        # None means "retry", never "vanilla".
        if self.ap_patched is False:
            return False

        if screen in ENDING_SCREENS:
            if goal == GOAL_ALL_MAVERICKS and self.mavericks_defeated < 8:
                if not self.short_ending_warned:
                    self.short_ending_warned = True
                    # "Beat the rest" is what this used to say, and it is
                    # impossible: settled live 2026-08-27, the credits return
                    # you to the title and there is NO post-credits play. X6
                    # saves at the stage select, so a save made before Gate's
                    # Lab is the only way back - and this is the moment the
                    # player decides what to do, so the instruction has to be
                    # the one that works.
                    logger.warning(
                        "MMX6: the ending was reached with only %d/8 Mavericks "
                        "beaten, and this seed's goal is all_mavericks - so it "
                        "is NOT complete yet. There is no play after the "
                        "credits: LOAD A SAVE from before Gate's Lab, beat the "
                        "remaining Mavericks, then go back through the endgame. "
                        "The goal fires on the ending at 8/8.",
                        self.mavericks_defeated)
                return False
            return True

        # all_mavericks satisfied AFTER a short ending. Gated on having SEEN
        # the ending, so this can never stand in for beating Sigma.
        return self.short_ending_warned and self.mavericks_defeated >= 8

    # ---- stage unlocks -------------------------------------------------------

    async def _stage_unlocks_apply(self, ctx: "BizHawkClientContext",
                                   screen: int) -> None:
        """Hold locked slots at 0 in the stage-select slot -> stage-id table.

        Re-asserted every cycle: the table is overlay data reloaded from disc
        on every hub entry, and a savestate can swap it under us too. Guarded
        by the anchor so we never write into whatever module occupies that
        address while a stage is loaded.
        """
        if not (ctx.slot_data or {}).get("stage_unlocks", 0):
            return
        try:
            anchor, table = await bizhawk.read(ctx.bizhawk_ctx, [
                (SLOT_ANCHOR, len(SLOT_ANCHOR_BYTES), "MainRAM"),
                (SLOT_TABLE, len(SLOT_TO_STAGE_ID), "MainRAM"),
            ])
        except bizhawk.RequestFailedError:
            return
        if bytes(anchor) != SLOT_ANCHOR_BYTES:
            # Not the stage-select overlay. Forget what we wrote so the next
            # hub entry is treated as fresh - the reload restores vanilla.
            self.slot_table_written = None
            return

        unlocked = {name for name in
                    (ctx.item_names.lookup_in_game(item.item)
                     for item in ctx.items_received)
                    if name in names.ACCESS_ITEMS}
        want = bytes(
            sid if names.access_item(STAGE_ID_TO_NAME[sid]) in unlocked else 0
            for sid in SLOT_TO_STAGE_ID)

        writes = []
        if bytes(table) != want:
            writes.append((SLOT_TABLE, list(want), "MainRAM"))

        # Put the hub id back after a blocked confirm. Only ever 0000 -> 0x0D,
        # and only on a stage-select screen, so this can never overwrite a real
        # destination the game just chose.
        if screen in STAGE_SELECT_SCREENS:
            try:
                (idx,) = await bizhawk.read(
                    ctx.bizhawk_ctx, [(SAVE_BASE + OFF_STAGE_IDX, 2, "MainRAM")])
            except bizhawk.RequestFailedError:
                idx = None
            if idx is not None and idx[0] == 0 and idx[1] == 0:
                writes.append((SAVE_BASE + OFF_STAGE_IDX,
                               [HUB_STAGE_INDEX], "MainRAM"))

        if writes:
            await bizhawk.write(ctx.bizhawk_ctx, writes)

        if self.slot_table_written != want:
            self.slot_table_written = want
            newly = unlocked - self.stages_unlocked_logged
            if newly:
                self.stages_unlocked_logged |= newly
                logger.info(
                    "MMX6: stages unlocked (%d/8): %s", len(unlocked),
                    ", ".join(sorted(n.removesuffix(" Access Codes")
                                     for n in unlocked)))

    # ---- endgame gate ------------------------------------------------------

    async def _endgame_gate_apply(self, ctx: "BizHawkClientContext",
                                  save: bytes, screen: int) -> None:
        """Hold Gate's Lab shut until all eight Mavericks are down.

        Under `all_mavericks` the goal is a conjunction - the ending only
        counts at 8/8 - and vanilla does not enforce it. High Max in an
        Another Route opens the Gate early (ship plan 20; seen live
        2026-08-27 at THREE Mavericks beaten). Reaching the credits short used
        to be recoverable in theory, but there is no post-credits play at all
        (item 24), so the only way back is reloading a save the player may
        never have made. Closing the door beats warning them afterwards.

        **The lock is the progress byte, not a slot table.** The endgame is not
        an entry in the stage-select table: that table holds exactly eight ids
        for slots 0-7 with the next row butted against it at +8, and Secret Lab
        sits on cursor 08 - a special-cased code path with no slot to zero.
        Measured live 2026-08-27: forcing `0x800CCF36` back to 2 on the stage
        select makes the icon unselectable, and 3 restores it.

        Stage-select screens only, and that is not incidental. The progress
        byte is part of `_check_signature`, so writing it during gameplay would
        make the signature disagree with itself between polls and could starve
        the trust gate every check depends on.

        Closes AND re-opens. The game does not recompute this byte, so leaving
        the re-open to it would strand any seed where the write we overwrote
        was its only one - see the comment on the 8/8 branch.
        """
        if (ctx.slot_data or {}).get("goal",
                                     GOAL_ALL_MAVERICKS) != GOAL_ALL_MAVERICKS:
            return
        if screen not in STAGE_SELECT_SCREENS:
            return

        progress = save[OFF_PROGRESS]
        if progress > PROGRESS_ENDGAME_OPEN:
            # The player is INSIDE the endgame sequence, and forcing 2 here
            # would destroy real progress - the same byte is how the Lab 1 and
            # Lab 2 clears are recorded, and it is their only durable record.
            # That can only happen if the Gate opened while no client was
            # watching, so say so rather than silently doing nothing.
            if not self.endgame_gate_missed:
                self.endgame_gate_missed = True
                logger.warning(
                    "MMX6: the endgame was entered before all 8 Mavericks were "
                    "beaten. It cannot be closed again without discarding the "
                    "Lab clears already recorded, so beat the remaining "
                    "Mavericks BEFORE Sigma - under this seed's goal the "
                    "ending does not count at less than 8/8.")
            return

        # Deliberately NOT the trusted latch on its own. `mavericks_defeated`
        # only moves on a trusted poll, so a fresh connect standing at the
        # stage select scores 0 and would hold the Gate shut against a player
        # who has genuinely finished all eight. Taking the better of the two is
        # safe here because BOTH of this gate's failure directions are
        # recoverable: a wrong close reopens on the next poll, and a wrong open
        # is just vanilla behaviour. That is exactly what the goal latch cannot
        # afford - a false victory is irreversible - which is why that one
        # stays trust-only.
        beaten = max(self.mavericks_defeated, bin(save[OFF_BEATEN]).count("1"))

        if beaten >= 8:
            # RE-OPEN IT OURSELVES. Measured live 2026-08-27: a value written
            # into this byte STAYS. The game does not recompute it while the
            # stage select is up - the icon came back only when 3 was written
            # by hand. So the client cannot hold the Gate shut and then leave
            # re-opening to the game: if the only write of 3 was the one we
            # overwrote (High Max dying, say), the Gate would never open again
            # and the seed would be unwinnable BY THIS FEATURE.
            #
            # Writing 3 at 8/8 cannot open it earlier than vanilla would -
            # all eight Mavericks is itself one of the game's own opening
            # conditions - and being stateless it survives a reconnect, which
            # an in-memory "did we hold it?" flag would not.
            if progress == PROGRESS_STAGE_SELECT:
                await bizhawk.write(ctx.bizhawk_ctx, [
                    (SAVE_BASE + OFF_PROGRESS, [PROGRESS_ENDGAME_OPEN],
                     "MainRAM")])
            if self.endgame_gate_held:
                self.endgame_gate_held = False
                logger.info("MMX6: all 8 Mavericks beaten - the Gate is open.")
            return

        if progress == PROGRESS_ENDGAME_OPEN:
            await bizhawk.write(ctx.bizhawk_ctx, [
                (SAVE_BASE + OFF_PROGRESS, [PROGRESS_STAGE_SELECT], "MainRAM")])
            if not self.endgame_gate_held:
                self.endgame_gate_held = True
                logger.info(
                    "MMX6: holding the Gate shut - %d/8 Mavericks beaten, and "
                    "this seed's goal needs all eight. The client re-opens it "
                    "on the eighth.", beaten)

    # ---- the watcher -------------------------------------------------------

    def _check_signature(self, save: bytes) -> bytes:
        """The bytes every check reads. Trust needs these stable across two
        polls, so a half-written or stale struct is never believed."""
        return bytes([save[OFF_PROGRESS], save[OFF_BEATEN], save[OFF_HEARTS],
                      save[OFF_ARMOR_PARTS], save[OFF_TANKS]]) + \
            save[OFF_REPLOIDS:OFF_REPLOIDS + reploids.REPLOID_BLOCK_LEN]

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        if ctx.server is None or ctx.slot is None:
            return

        try:
            save, player = await bizhawk.read(ctx.bizhawk_ctx, [
                (SAVE_BASE, SAVE_LEN, "MainRAM"),
                # Live player object: HP, current weapon index and the whole
                # ammo array in one read. Only valid during gameplay.
                (PLAYER_BASE, PLAYER_LEN, "MainRAM"),
            ])
        except bizhawk.RequestFailedError:
            return

        if self.ap_patched is None:
            # validate_rom can run while the EXE is still streaming in from
            # disc, so an undetermined probe must be retried rather than
            # treated as vanilla - the difference decides whether weapons are
            # granted for the entire session.
            try:
                (probe,) = await bizhawk.read(
                    ctx.bizhawk_ctx, [(PATCH_PROBE_ADDR, 4, "MainRAM")])
            except bizhawk.RequestFailedError:
                return
            self.ap_patched = self._classify_probe(probe)
            if self.ap_patched is not None:
                logger.info("MMX6: disc resolved to %s",
                            "AP-PATCHED" if self.ap_patched else "VANILLA")

        screen = save[OFF_SCREEN]
        on_trusted_screen = screen in TRUSTED_SCREENS
        signature = self._check_signature(save)
        stable = signature == self.last_check_sig
        trusted = on_trusted_screen and stable and self.last_poll_trusted
        self.last_check_sig = signature
        self.last_poll_trusted = on_trusted_screen

        # ---- goal ------------------------------------------------------------
        # BEFORE the trust gate, deliberately. The ending screen is neither
        # gameplay (0x0A) nor the Mission Report (0x0C), so `trusted` is False
        # all the way through the credits and would swallow the goal entirely.
        if self._goal_decision(screen,
                               (ctx.slot_data or {}).get("goal",
                                                         GOAL_ALL_MAVERICKS)):
            self.victory_sent = True
            await ctx.send_msgs([{"cmd": "StatusUpdate",
                                  "status": ClientStatus.CLIENT_GOAL}])
            logger.info("MMX6: goal complete - ending reached, %d/8 Mavericks "
                        "beaten.", self.mavericks_defeated)

        # Stage unlocks run BEFORE the trust gate, and have to: the stage
        # select is not a trusted screen (only gameplay and the Mission Report
        # are), so gating this on `trusted` would mean it never ran at all.
        # Safe to do so - this is the inverse of granting. It writes only
        # overlay data that reloads from disc on the next hub entry, it is
        # guarded by an anchor proving the right module is mapped, and the
        # worst a wrong save could suffer is stages it cannot enter until it
        # leaves the hub.
        await self._stage_unlocks_apply(ctx, screen)

        # Same reasoning, same path: the endgame is entered from the stage
        # select, which is never a trusted screen.
        await self._endgame_gate_apply(ctx, save, screen)

        if not trusted:
            return

        # ---- checks --------------------------------------------------------
        found = self._detect(ctx, save)

        new = self._sendable(ctx, found)
        if new:
            self.sent_locations |= new
            await ctx.send_msgs([{"cmd": "LocationChecks",
                                  "locations": sorted(new)}])

        # ---- grants --------------------------------------------------------
        writes = self._grants(ctx, save)

        # Filler is only applied with a live player block, which exists in
        # gameplay and not on the Mission Report - so a heal or a refill
        # arriving between stages waits rather than being written into a
        # struct that is not there.
        live_player = player if screen == SCREEN_INGAME else None

        # One-time confirmation that the patch is doing what it claims. On a
        # patched disc the live capability must follow AP_WEAPONS; on vanilla
        # it follows the kill record. Logged once per session because it is
        # the only externally visible proof the redirect took.
        if live_player is not None and not self.capability_logged:
            self.capability_logged = True
            logger.info(
                "MMX6: live weapon capability = 0x%02X   "
                "(kill record 0x800CCF30 = 0x%02X, AP byte 0x800CCF7B = 0x%02X, "
                "disc = %s)",
                live_player[OFF_P_CAPABILITY], save[OFF_BEATEN],
                save[OFF_AP_WEAPONS],
                "patched" if self.ap_patched else "vanilla")
        filler_writes, cursor = self._filler_grants(ctx, save, live_player)
        self.filler_cursor = cursor
        writes += filler_writes

        if writes:
            await bizhawk.write(ctx.bizhawk_ctx,
                                [(addr, data, "MainRAM") for addr, data in writes])

        # ---- goal bookkeeping ------------------------------------------------
        # Only the LATCH lives on the trusted path. X5 shipped the equivalent
        # counter on a weaker gate, and because it LATCHES, one stale 0xFF read
        # would have scored 8 permanently and handed out a false victory that
        # no later good read could undo.
        self.mavericks_defeated = max(self.mavericks_defeated,
                                      bin(save[OFF_BEATEN]).count("1"))
