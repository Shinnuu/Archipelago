# Mega Man X6 apworld — changelog

## 0.0.1 — unreleased scaffold

Generation, logic, the BizHawkClient and the disc patch are all wired. A seed
emits a `.apmmx6` patch which produces a playable disc.

**The patched disc has been booted and the patch proven in a running game.**
See "proven live" below. What remains is support for discs other than the one
tested - see "still to verify" at the end.

- World, items, locations, options and reachability rules, following the
  Mega Man X5 world's structure.
- 28 base items into 29 base locations; `reploid_checks` (on by default) adds
  128 Reploid locations and the 16 gauge upgrades they carry.
- All 128 Reploid locations derived by arithmetic from the confirmed stage
  mapping (stage bit N owns Reploids N*16..N*16+15), which four separately
  observed stages fit.
- Capacity is checked in `generate_early`, so an over-full option set is
  refused with a message naming the fix rather than silently dropping items.
- 110 tests, including an exhaustive check of the item/location arithmetic and
  an assertion that the Blade -> Shadow armor dependency stays acyclic.

### BizHawk client

Detects checks and applies received items. Four policies, each deliberate:

- **Weapons are granted only on a patched disc.** On vanilla `0x800CCF30` is
  simultaneously the kill record and the weapon list, so writing it would
  fabricate a boss check. The A1 disc patch redirects the capability to a byte
  AP owns (`0x800CCF7B`), and there it is safe. The client probes an EXE
  instruction to tell the two discs apart, and treats an unreadable probe as
  "retry" rather than "vanilla".
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


### Disc patch

A seed emits a `.apmmx6` which patches the vanilla image in pure Python - no
external xdelta, no separate basepatch file - and regenerates EDC/ECC for every
touched sector. Without that regeneration emulator disc layers error-correct
the edits back to vanilla and the patch silently does nothing.

The patch is the A1 decoupling: three instructions, one 16-bit immediate each,
redirecting the weapon capability from `0x800CCF30` (which is simultaneously
the kill record) to `0x800CCF7B`. Result is 3 sectors, exactly one user-data
byte changed in each. Every edit declares the vanilla bytes it expects and the
patcher refuses to run if the image does not match.

**Only one disc hash is accepted**, deliberately. X5 could also accept the
Redump dump because its dev image was proven to be Redump plus one trailing
zero sector. X6 has no such proof, so support is claimed only for the image
actually tested.

### The A1 patch, proven live

The one thing the offline tests could never establish is whether the patch
does in a running game what the disassembly says it does. It does.

Sequence: patched disc booted, save loaded with **no stages cleared**, a stage
entered, and `Ray Arrow` sent from the server. The client wrote `0x80` to
`0x800CCF7B`. The live capability then read:

```
disc is AP-PATCHED (probe at 0x8003C278 read ab00a290)
live weapon capability = 0x80
  kill record 0x800CCF30 = 0x00, AP byte 0x800CCF7B = 0x80
```

The capability followed **AP's byte, not the kill record** - a usable special
weapon at zero Mavericks beaten, which vanilla X6 structurally cannot produce,
because there the two facts are the same byte.

Also established: the capability is **latched at stage start**, so a freshly
granted weapon does not appear until the stage reloads - and **dying is enough**
to re-latch it, which is a far gentler requirement than leaving the stage.

### Still to verify

- **The Redump hash, before anyone else can use this.** Offsets are confirmed
  against the tested image only, and X6's image is *not* Redump plus trailing
  padding the way X5's was, so the equivalence cannot be argued - it has to be
  checked against a real dump.
- Whether the client must also write the Reploid mirror at `0x800CCFE8`.

Two items that were on this list are now closed. There is **no fourth A1 copy
site**: offset `+0xC9` has exactly 8 stores in the whole game and every one is
accounted for, so the three patched sources are the complete set. And the
**High Max rule needed no change** - Shadow Armor really does zero the weapon
capability, but armor is chosen at the stage select and bare X is always
available, so holding the weapons is all the rule requires.

### A note on savestates and patched discs

Savestates carry the full 2MB of RAM, **including code**. A state taken on a
vanilla disc therefore restores vanilla code over a patched EXE, and the patch
appears to have vanished. This is not a general hazard and X5 never hit it,
because X5's states were always made on the disc they belonged to. It only
arises when a state crosses a patch boundary - which is exactly what save
migration enables. Migrate for convenience; when *verifying* a patch, reload
the ROM and load from the memcard.
