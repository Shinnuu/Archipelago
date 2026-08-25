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

KNOWN GAP, fix before anyone but the author plays: there is no seed/slot stamp
in the save, so the client cannot tell this seed's save from another one and
will send baseline checks for whatever is already set. X5 stamps a spare byte
for exactly this. Candidate spare regions are listed in STAMP_CANDIDATES
below - none is verified, and writing an unverified save byte is its own risk.
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

# Save-struct bytes that never changed across a full multi-stage play session
# and are not in any region we have mapped. CANDIDATES ONLY - "did not move
# once" is not "unused", and none has been tested. The seed stamp wants one of
# these, verified by writing it, saving, reloading and confirming both that it
# survived and that nothing broke.
#
# Memcard offset for any save byte: mc = 0x3200 - (addr - 0x800CCE00). The
# struct is copied to the card REVERSED; the formula reproduces all three
# documented pairs (CEDC/3124, CF64/309C, CF9C/3064), so a stamp anywhere in
# the struct does persist.
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
# Live player HP is 0x800970FC, low 7 bits, and bit 0x80 is a hit/heal FLAG -
# mask it or every heal reads as a bogus +/-128 swing (that one cost three
# sessions before it was spotted). The live block is only valid in gameplay,
# so a heal waits for a stage rather than being dropped.
# One read of the live player object covers HP, the current weapon index and
# the whole ammo array, so filler needs no extra round trips.
PLAYER_BASE = 0x0970A0
PLAYER_LEN = 0xC8                      # through the last ammo slot (+0xC7)
OFF_P_HP = 0x5C                        # low 7 bits; bit 0x80 is a hit/heal FLAG
OFF_P_WEAPON_IDX = 0x93                # which ammo slot the buster/weapon uses
OFF_P_AMMO = 0xA8                      # 16 x u16, confirmed live
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
LIVES_CAP = 9                          # engine clamp assumed, not verified

GOAL_SIGMA = 0
GOAL_ALL_MAVERICKS = 1


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
        self.baseline_logged = False
        self.weapons_notice_logged = False
        self.withheld_logged: set[str] = set()
        # How far into ctx.items_received the filler grants have got. None
        # means "not started"; it is set to the list length on the first
        # trusted poll, so filler already in hand at connect is skipped.
        self.filler_cursor: int | None = None

    # ---- identification ----------------------------------------------------

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        try:
            (sig,) = await bizhawk.read(
                ctx.bizhawk_ctx, [(EXE_SIG_ADDR, len(EXE_SIG), "MainRAM")])
        except bizhawk.RequestFailedError:
            return False
        if sig != EXE_SIG:
            return False

        ctx.game = self.game
        ctx.items_handling = 0b111   # remote items, own-world items, start inv
        ctx.want_slot_data = True
        self._reset_state()
        return True

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
        if save[OFF_PROGRESS] >= 1:
            add(names.INTRO_CLEAR)

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

        # --- weapons: NOT granted (policy 1) ---------------------------------
        if not self.weapons_notice_logged and any(
                got.get(w) for w in names.WEAPONS):
            self.weapons_notice_logged = True
            logger.info(
                "MMX6: special weapons are not granted yet - the byte that "
                "holds them (0x800CCF30) is the same byte that records which "
                "Mavericks you have beaten, so writing it would fake a boss "
                "check. Beat a Maverick to get its weapon, as in the base "
                "game. The disc patch will separate the two.")

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
                lives = min(LIVES_CAP, lives + 1)
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

        screen = save[OFF_SCREEN]
        on_trusted_screen = screen in TRUSTED_SCREENS
        signature = self._check_signature(save)
        stable = signature == self.last_check_sig
        trusted = on_trusted_screen and stable and self.last_poll_trusted
        self.last_check_sig = signature
        self.last_poll_trusted = on_trusted_screen
        if not trusted:
            return

        # ---- checks --------------------------------------------------------
        found = self._detect(ctx, save)

        if not self.baseline_logged:
            self.baseline_logged = True
            fresh = found - set(ctx.checked_locations)
            if fresh:
                # Loud on purpose. Without a seed stamp the client cannot tell
                # this seed's save from another one, so this is the moment a
                # wrong save would release other players' items. Until the
                # stamp exists, the log is the only thing standing between a
                # mistake and a broken multiworld.
                logger.warning(
                    "MMX6: this save already has %d location(s) collected that "
                    "the server has not seen, and they are about to be sent. "
                    "That is correct if it is this seed's save and you played "
                    "while disconnected. If you have loaded a save from a "
                    "DIFFERENT seed, disconnect now - sending these would "
                    "release other players' items.", len(fresh))

        new = found - self.sent_locations - set(ctx.checked_locations)
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
        filler_writes, cursor = self._filler_grants(ctx, save, live_player)
        self.filler_cursor = cursor
        writes += filler_writes

        if writes:
            await bizhawk.write(ctx.bizhawk_ctx,
                                [(addr, data, "MainRAM") for addr, data in writes])

        # ---- goal ----------------------------------------------------------
        # Provisional. Reaching the endgame is detectable (0x800CCF36 >= 3 plus
        # the souls threshold), but neither the credits sequence nor a Sigma
        # kill has been observed live yet, so this fires on the endgame being
        # unlocked WITH every Maverick down, which is strictly later than the
        # game's own gate and cannot fire early.
        if self.victory_sent:
            return
        goal = (ctx.slot_data or {}).get("goal", GOAL_ALL_MAVERICKS)
        beaten_count = bin(save[OFF_BEATEN]).count("1")
        souls = int.from_bytes(
            save[OFF_SOULS_Z if save[OFF_CHAR] else OFF_SOULS_X:][:2], "little")
        endgame_open = save[OFF_PROGRESS] >= 3 or souls >= SOULS_GATE
        if endgame_open and (goal != GOAL_ALL_MAVERICKS or beaten_count == 8):
            self.victory_sent = True
            await ctx.send_msgs([{"cmd": "StatusUpdate",
                                  "status": ClientStatus.CLIENT_GOAL}])
            logger.info("MMX6: goal complete (%d/8 Mavericks, %d souls).",
                        beaten_count, souls)
