# Mega Man X6 apworld — changelog

## 0.0.1 — unreleased scaffold

**Not playable end-to-end.** No disc patch yet, so a seed produces no patch
file - but generation, logic and the client all work.

- World, items, locations, options and reachability rules, following the
  Mega Man X5 world's structure.
- 28 base items into 29 base locations; `reploid_checks` (on by default) adds
  128 Reploid locations and the 16 gauge upgrades they carry.
- All 128 Reploid locations derived by arithmetic from the confirmed stage
  mapping (stage bit N owns Reploids N*16..N*16+15), which four separately
  observed stages fit.
- Capacity is checked in `generate_early`, so an over-full option set is
  refused with a message naming the fix rather than silently dropping items.
- 93 tests, including an exhaustive check of the item/location arithmetic and
  an assertion that the Blade -> Shadow armor dependency stays acyclic.

### BizHawk client

Detects checks and applies received items. Four policies, each deliberate:

- **Weapons are not granted.** `0x800CCF30` is simultaneously the kill record
  and the weapon list, so writing it would fabricate a boss check. Needs the
  disc patch (ship plan A1). Until then weapons come from beating Mavericks.
- **Grants are absolute.** Gauges are computed from the items received and
  written whole, so re-applying after a reconnect is a no-op. Removes X5's
  need for a memcard-persisted counter rather than guarding it.
- **Bits that hide their own pickup are withheld** until their location is
  checked - otherwise an early grant makes the location uncollectable.
- **Gauge record bits are never written**, so detection off `0x800CCF3C/3D/3F`
  can never read an AP grant back as a pickup.

**Telling this seed's save from another one** is handled without a stamp. X5
writes a seed/slot stamp into a spare save byte; X6 cannot, because its memcard
re-serialises the save rather than copying it, so a byte that looks free in RAM
may never reach the card. Instead the answer comes from what the server already
knows: already-collected locations are sent only if this slot has checked
something before, which proves the save belongs to a run of this seed. A
progressed save on a slot with no history is held back with an explanation, and
collecting any one check then reconnecting releases it.

### Proven live

Run against a real save with the full stack (server + client + connector +
EmuHawk): the game is identified from the EXE signature, 30 baseline locations
detected and sent, live checks fired from actual play (an armor capsule and a
Reploid), 4 item-grant writes all bit-exact against the 26 items received,
~4,500 frames with zero repeat writes, and the withholding rule held back an
armor part correctly.

An offline replay of the play-session RAM log predicted that live run
**exactly** — same 30 locations. That replay is now a frozen test fixture, and
mutation testing (7 deliberate breakages) confirms the suite catches them all.

The live run found one thing offline tests could not: **filler items did
nothing**, which is 58% of the items in a default seed. Now fixed for Extra
Life and life energy. Weapon energy is still inert — only its maximum
(`0x800CCF31`) is mapped, not current ammo.

### Weapon ammo — found and implemented

Located by disassembling `consume_ammo()` at `0x8003F740`, then confirmed live:
the ammo array is 16 u16 slots at **`0x80097148`** (player object `+0xA8`),
indexed by the byte at **`0x80097133`** (`+0x93`). The live cap is the weapon
gauge x 6, **latched at stage start** — so a refill is capped against what is
actually in the array, not against the save byte, or a just-granted Energy Up
overfills until the next stage.

All five filler types now do something.

### Research corrections made while building this

The Reploid array has **two** 64-byte copies: a live one at `0x800CCFA8` written
one nibble per rescue, and a bulk mirror at `0x800CCFE8` that never changed by
fewer than 6 bytes at once. An earlier pass this same day narrowed the notes to
a single block, which was wrong - the 128-byte span in the original notes was
both copies. The client reads the live one.
