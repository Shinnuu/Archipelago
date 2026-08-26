# Mega Man X6 apworld — changelog

## Unreleased

### The goal would almost never have fired, and the constant was not the problem

Victory watched screen `0x10`, the ending/credits screen. That value is
correct. It is also visible for about one frame.

X6's main loop reads the screen byte, indexes a handler table, and calls
through it every frame. Screen `0x10`'s handler rewrites the screen byte to
`0x11` on its third instruction, unconditionally, before doing anything else.
So `0x10` survives a single iteration — roughly 16.7 ms — while the BizHawk
watcher polls twice a second. The odds of ever catching it were about one in
thirty, and the failure was silent: the credits would roll and the seed would
simply never complete.

Victory now also accepts `0x11`, which is the state that *holds*, and which
nothing else in the game writes — `0x10`'s handler is its only source, so this
is exactly as strict as before and can actually be observed.

Found by disassembling the disc, not by playing it. Nobody has reached X6's
credits with the client attached; that is still true, and this changes the
odds that it will work when somebody does.

### The patcher now tells you when it was handed an already-patched disc

Pointing the base-image setting at a disc an earlier seed produced used to get
a bare MD5 mismatch. That is the failure that actually happens, and on the X5
world the same uninformative refusal sent a tester deleting every X5 file he
had. The rejection now probes the offered file at the site the patch changes
and says which of three things went wrong:

- **a disc this world already patched** — names the setting to fix, and says
  the patched disc stays valid for the seed it belongs to;
- **an intact X6 disc we have not tested** — a different rip;
- **too small to be a disc at all** — a `.cue`, `.iso`, `.ecm` or an archive.

An unrecognised file gets no invented explanation, just the hash mismatch. A
confident wrong diagnosis would be worse than the bare error it replaced.

Eight tests, three of them building real patched images rather than poking a
byte, so the probe moving out from under the diagnosis would be caught.

### Reploid checks: the documentation now matches the code

The option claimed a check was collected "the moment you reach the Reploid".
It is not — it is collected when the Reploid's slot leaves the untouched
state. That is still the behaviour the option is really about, because
"destroyed by a Nightmare" counts just as much as "rescued", so losing one
costs you the life and never the check.

The other way a check could vanish was tested rather than assumed, because the
X5 engine gets it wrong: there, rescuing at the nine-life cap consumes the
Reploid and records nothing, making the check uncollectable. **X6 records the
rescue at the cap** — only the extra life is discarded. With 128 Reploid
checks that was worth an hour to be sure of.

### Fixed: neither goal actually required beating Sigma

`sigma` is documented as *"defeat Sigma, however you got there"*. It fired the
moment the Nightmare Soul counter crossed 3000 — mid-stage, in a Maverick
stage, with the endgame not yet unlocked and Sigma never fought. Demonstrated
against the old code: two Mavericks beaten, `0x800CCF36` still 2, victory
FIRES. `all_mavericks` had the same shape, merely with a kill count bolted on.

Victory now fires on the **post-Sigma ending screen** (`0x800CCED0` = `0x10`,
End credits), which is the X5 world's live-validated approach:

- Checked **before** the trust gate. The ending is neither gameplay nor the
  Mission Report, so the gate is False through the whole credits and would
  otherwise swallow the goal.
- The Maverick count comes from a **latch accumulated during trusted play**,
  never a read taken at goal time — the save struct is not sane during the
  ending. Because it latches, the latch itself is gated on trust: X5 shipped
  its equivalent on a weaker gate, where one stale `0xFF` read would score 8
  permanently and hand out a false victory no later good read could undo.
- An **unpatched disc never goals** (a goal releases every remaining location
  in this world), but an **undetermined** probe still does — `None` means
  "retry", never "vanilla", and the credits can clobber the probe region.
- Reaching the ending early under `all_mavericks` **warns instead of
  stranding**: beat the rest and the goal fires when the eighth one dies.

**Nothing tested the goal before this.** That is how a rule keyed on a soul
count shipped under a docstring promising Sigma. There are now 15 goal tests,
and the decision was extracted into a method that can actually be called
without an emulator.

**The credits screen value is from the Tweaks workbook and has not been seen
live** — nobody has reached X6's ending with the client attached.

### Stage unlocks

`stage_unlocks` (off by default) locks the eight investigation sites behind
items. One is open at the start, chosen by the seed and precollected; the other
seven are `<Boss> Access Codes` shuffled into the multiworld. A locked site
greys out on the stage select and confirming it does nothing.

Client-side, so it needs no disc change and works on an already-patched disc.

The mechanism was researched live rather than ported blind. X6's stage-select
overlay holds the same shape X5's hub does - a slot -> stage-id table where a
zero makes the confirm a no-op - at ROCK_X6.BIN +0x0C5B4C, resident at
0x800F0BAC. Three things about it are worth writing down:

- **There are THREE 8-byte rows, and they are one table re-encoded**: the
  second is the first minus 1 (0-based), the third is that one's inverse
  (stage -> slot). Only the first gates entry, established by zeroing each on
  its own and trying the stage. The client writes only the first and uses the
  other two as its residency anchor, since they are constants it never touches.
- **A blocked confirm leaves the stage index at 0000**, because the game stores
  it before testing it for zero. In X6's encoding 0000 is the *intro stage*, and
  an in-hub save would commit it, so the client puts the hub id back.
- **The endgame additionally requires every Access Codes item** under this
  option. That is the bug X5 shipped: without the rule, fill can place a
  stage's codes inside the endgame those codes are needed to reach, and the
  playthrough checker still calls the seed won.

178 tests (up from 132) and a 64-check release gate (up from 58). A real
`Generate.py` seed with the option on fills 157 items into 157 locations and
produces a clean progression chain - `WorldTestBase` does not run fill, so that
generation is the only thing that actually proves capacity.

### Quality-of-life disc options

Three new options, all of which change the disc and none of which touch the
item pool, logic or the client:

All three are **on by default**.

- `exit_stage_anytime` — the pause menu offers Exit Stage before the stage's
  boss is down. (X5's equivalent is also default-on.)
- `text_skip` — in-stage Navigator calls, other in-stage dialogue, stage-select
  briefings and the Nightmare Souls explanation do not play; the alert chime is
  muted; cutscene text types at double speed. Rolled by `randomize_options`,
  exactly as X5 rolls its own `text_skip`. **Confirmed working in a live
  session.**
- `skip_intro_videos` — skips the Capcom logo and the title-screen opening, and
  stops the attract demos. It does **not** skip the cutscene that plays when
  you begin a game: the first build of this option shipped only Tweaks'
  "Skip opening Intro", a player reported the post-GAME-START video still
  played, and that call site is elsewhere and still unlocated. The Capcom pair
  was added so the option removes something it demonstrably can.

The edits are adapted from acediez's **Mega Man X6 Tweaks** patcher (v2.6.1).
Its data is expressed as raw offsets into its own target image, so nothing was
taken on trust: every site was re-derived into this world's (region, address)
form and the vanilla bytes read back from **both** supported images. The
Tweaks project's `DialogueDisable05`/`06` are deliberately absent — its data
file marks both "not solved" and ships no code for them.

Mechanically:

- Per-seed edits now ride in the `.apmmx6` as an explicit list carrying the
  **expected vanilla bytes**, and `apply_basepatch` verifies them with the same
  rigour as A1 — an edit list built for another dump fails loudly instead of
  corrupting code quietly.
- `apply_basepatch` now refuses two edits that write the same disc offset.
  Overlapping writes would make the output depend on edit order, which is the
  kind of bug that appears in one seed out of fifty.
- With every QoL option off, the patched image is **byte-identical** to the
  A1-only disc, so an image patched before this existed stays valid.
- 132 tests (up from 115) and a 58-check release gate (up from 48).

**Live-test status.** All fourteen edits are verified byte-for-byte on both
images, land correctly, and leave valid EDC/ECC on the eleven sectors they
touch. A patched disc boots cleanly, and every site was confirmed *resident in
RAM* against a vanilla control run (8/8 discrimination, with the A1 patch as a
positive control). Behaviourally: `text_skip` is confirmed working in play;
`skip_intro_videos` is partly confirmed and partly disproven (see above);
`exit_stage_anytime` has not yet been exercised in a stage.

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

**Both the Redump dump and the development image are accepted**, and both have
been patched and verified. Ours turned out to be the Redump disc plus eight
trailing zero sectors: `SLUS_013.95` and `ROCK_X6.BIN` are byte-identical
between them, 0 differing sectors across both containers, so every offset
derived on one is valid on the other. Patching the Redump image produces the
same three sectors with valid parity.

This was previously written up as a release blocker, and briefly as evidence
the two discs were different *revisions*. That was wrong. X5 could also accept the
Redump dump because its dev image was proven to be Redump plus one trailing
zero sector. X6 has no such proof, so support is claimed only for the image
actually tested.

### An Extra Life at the cap is no longer eaten

`min(cap, lives + 1)` is a no-op at 9 lives, but the cursor advanced anyway,
so an Extra Life arriving on a full stock silently vanished - somebody else's
item, gone. It is now banked and paid out the moment the player spends a life.

Banked rather than stalled on purpose: the filler cursor is strictly
sequential, so blocking on a full life stock would hold every heal queued
behind it hostage until the player happened to die. Both behaviours are
tested, and the tests were checked against the old code to confirm they
actually catch it.

The cap itself is now evidence rather than assumption: across 38 transitions
of the lives byte in a recorded session it reached 9 eight separate times and
never 10.

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

- Nothing. The Redump dump was obtained and tested 2026-08-25 - see below.
Nothing outstanding blocks the author from playing. What is listed above
blocks *other players*.

Three items that were on this list are now closed. There is **no fourth A1 copy
site**: offset `+0xC9` has exactly 8 stores in the whole game and every one is
accounted for, so the three patched sources are the complete set. And the
**High Max rule needed no change** - Shadow Armor really does zero the weapon
capability, but armor is chosen at the stage select and bare X is always
available, so holding the weapons is all the rule requires. And the **Reploid mirror
needs no write**: the routine at `0x8001E994` copies the live block *to* the
mirror, 16 words, and no reverse copy exists anywhere in the game - so the
live block is authoritative and reading it is correct.

### A note on savestates and patched discs

Savestates carry the full 2MB of RAM, **including code**. A state taken on a
vanilla disc therefore restores vanilla code over a patched EXE, and the patch
appears to have vanished. This is not a general hazard and X5 never hit it,
because X5's states were always made on the disc they belonged to. It only
arises when a state crosses a patch boundary - which is exactly what save
migration enables. Migrate for convenience; when *verifying* a patch, reload
the ROM and load from the memcard.
