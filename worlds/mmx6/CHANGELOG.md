# Mega Man X6 apworld — changelog


## Unreleased

**Shield Sheldon's Reploid 5 needs Zero or the Blade Armor.** It stands on a
ledge beside the Blade Body capsule that X cannot reach with a plain jump, and
logic called it free — so a multiworld put another stage's Access Codes on it
and there was no way to get them. Found in play. **Regenerate to get this**:
it is a logic change, so seeds made before it keep the old rule. Its two
neighbours, Reploid 4 and the Blade Body capsule itself, were checked at the
same time and really are free.

**New: `starting_rank`, because Souls are what let you equip Parts.** Hunter
Rank decides how many Power-up Parts you may wear, Rank is bought with
Nightmare Souls, and **X and Zero each have their own count** — so a run
played mostly as one character leaves the other unable to equip anything at
all. The disc's thresholds are 200 (C), 300 (B), 500 (A), 800 (SA), 1200 (GA),
5000 (PA), 9999 (UH), and **below Rank A there are no slots**: the first one
costs 500 of that character's own Souls, long after a seed has handed you 24
Parts as items. This option makes the rank you name cost nothing, leaving the
ranks above it exactly as they were. `rank_a` is the free one — one slot each
and no other change; SA and above also raise every boss's fight level, which
the option says plainly. Off by default. **Changes the disc.**

**New: `no_progression_behind`.** Name the kinds of place the fill may not
hide anything important in — `spikes` for the Shadow Armor rooms, `movement`
for what needs Zero or the full Blade Armor, `nightmare_wall` for North Pole's
ice wall, or `all`. Those checks still exist, still need exactly what they
always did and still send their item; they simply hold junk, so no seed can
require you to do that kind of thing. The default is an empty list, which is
the game as it has always been here. If you ask for more than a seed has junk
to fill, generation refuses it and names what to change rather than failing
late.

**`exit_stage_anytime` now works everywhere** — Another Routes, Gate's Lab and
the Intro Stage included. It only ever covered the eight Maverick stages,
which is why leaving an Another Route still meant dying on purpose; the base
game does not treat one as part of its stage and offers no way out at all.
**Re-patch for this** — it changes the disc. Leaving the Intro Stage early is
the one case nobody has tested.


## 0.2.1 — 2026-09-03

**Player colours are YAML options now.** They were settings in `host.yaml`,
and the feedback was consistent: people did not want to edit a file they had
never opened, and many never found out the feature existed at all. So the five
colours join every other option in your YAML, where the website generator
lists them and a typo is refused at generation instead of silently falling
back to vanilla.

Nothing breaks, and nothing needs regenerating:

- **A colour already set in `host.yaml` keeps working exactly as before.** It
  is an override now, and it still wins.
- **YAMLs written for 0.2.0 still generate.** The new options default to
  vanilla.
- You only need a new seed if you want your colour to come from the YAML.
  Anyone mid-seed can keep changing colours by re-patching, as now.

Two details worth knowing. `random` is rolled at generation now rather than
from your player name, so it is fixed and appears in the spoiler, and it can
land on vanilla because it picks from the whole list. And **`vanilla` in
`host.yaml` does not override anything** — it means "nothing set here".
Archipelago writes those entries into `host.yaml` by itself with `vanilla` in
them, so honouring it would have quietly overridden the YAML of every existing
player. To play in vanilla colours, pick `vanilla` in your YAML.

## 0.2.0 — 2026-09-03

**REGENERATE your seeds to get the endgame fix.** It is per-seed disc data:
the edits are baked into the `.apmmx6` when the seed is generated, so
re-opening a 0.1.1 patch file cannot deliver them. Seeds generated on 0.1.1
are not broken — they stay winnable and keep the old client-side gate — but
the Gate can still open early on them. Player colours are the exception (see
below): changing one is a re-patch of the same file, never a regeneration.

**If you use player colours, get this release's `MMX6-Unpatcher`.** The 0.1.1
one refuses a recoloured disc.

### The endgame opens on eight Mavericks and nothing else (regenerate)

Under `all_mavericks`, vanilla could still open Gate's Lab early — on 3000
Nightmare Souls, or by beating High Max in an Another Route — and the client
could not hold it shut: it wrote the byte closed and the game wrote it open
again on the next stage exit, which is the replaying unlock cutscene testers
reported. The disc now switches those two conditions off where the game
decides them, in eight one-immediate edits, so the only thing that opens the
Gate is your eighth Maverick. Verified live with a control: on an unpatched
disc, 3500 Souls at 2/8 opened the Gate; on the patched disc the same steps
left it shut, with no cutscene.

Not applied under the `sigma` goal, where opening on Souls is the game's own
design. The client's guard stays as a backstop, and the client still opens
the Gate itself at 8/8.

**One thing to watch for:** the eighth-Maverick unlock itself has not yet
been observed on a patched disc. If your Gate does not appear after the
eighth Maverick, please report it — the client should open it on the next
stage select regardless.

**New: `disabled_nightmare_effects`.** Switch Nightmare Effects off. Name the
ones you do not want in any combination, or just write `all`. Empty is vanilla
and leaves the disc byte-for-byte unchanged. Case does not matter, so `fire`
and `Fire` both work.

    disabled_nightmare_effects:        disabled_nightmare_effects:
      - Fire                             - all
      - Dark

Each stage can be afflicted by exactly two of the eight, so turning one off
does not clear a stage on its own:

| stage | effects | | stage | effects |
|---|---|---|---|---|
| Amazon Area | Rain, Dark | | Central Museum | Iron, Rain |
| North Pole | Fire, Mirror | | Inami Temple | Mirror, Dark |
| Magma Area | Bug, Iron | | Laser Institute | Bug, Cube |
| Recycle Lab | Ice, Cube | | Weapon Center | Fire, Iron |

**Turning Fire off puts nothing important behind North Pole's ice wall.** That
wall only opens while Nightmare Fire is on the stage, and nine locations sit
behind it — Blizzard Wolfang's Heart Tank, his EX Tank and seven of his
Reploids. With Fire off those nine are excluded, exactly the way
`scaravich_no_progression` treats Central Museum, so no seed can depend on
getting through. The patch also tries to hold the wall open so they stay
collectable, but nothing rests on that working.

Two knock-ons worth knowing, neither costing a check. Nightmare Souls become
much harder to farm, since the Virus only drops a fresh Orb after a stage has
been afflicted — nothing in this randomizer needs Souls, the endgame opens on
your eighth Maverick, but the vanilla 3000-Soul route to Gate's Lab
effectively closes. The endgame gate does not care either way: under
`all_mavericks` the Souls opening is switched off on the disc (see above).

**New: `scaravich_no_progression`.** Ground Scaravich's stage is built from
totem-pole rooms the game picks at random — four of eight per entry — and its
Heart Tank, its Blade Armor Helmet and fifteen of its sixteen Reploids sit
behind that roll. Turn this on and every location in that stage holds junk, so
nothing you need can be behind the dice. The checks still exist and still send;
they are just never worth re-rolling for. The client also stops holding your
Blade Armor Helmet back until that capsule is found, which is the one place
the usual hold could wait on a room you never get.

Costs 19 of the seed's locations as places progression can go (3 if you have
Reploid checks off). It is a stopgap rather than a cure — pinning the room
order, or being shown all eight rooms, would be the real fixes.

**New: `starting_hp` and `heart_tank_value`.** Set the life X and Zero start
with (1–127, vanilla 32) and how much each Heart Tank or Life Up is worth
(0–64, vanilla 2). One setting covers Heart Tanks and Life Up Reploids because
the game does not tell them apart. 127 is the game's own ceiling — it keeps
life in seven bits — and every value plays, checked live from 1 to 127; only
the bar's drawing has limits: below 32 it shrinks to a stub with the emblem
on top of it, and above 64 it stays the 64 size, so 100 and 127 look exactly
like 64. The number is real, the picture is not.

The starting value is a disc edit baked into the seed (the game's new-save
initialiser writes 32, so anything else has to be written there); the
per-upgrade value is client-side. The client writes the life gauge
**absolutely**, in both directions, for X and Zero alike — so walking over a
Heart Tank whose item went to someone else does not leave you the vanilla +2.
Weapon energy is untouched.

**New: player colours.** X, Zero, Shadow Armor, Blade Armor and Ultimate Armor
can each be recoloured independently, from 18 presets or `random`. Purely
cosmetic — no logic, items or locations are touched.

The colours are **not seed data**. They live in your own `host.yaml` under
`mmx6_options` and are applied while the patch is opened, so changing one is a
re-patch of the same `.apmmx6`, never a re-generation. Set them before opening
the patch, and delete the previous `.bin`/`.cue` first or the patcher will skip
its work and leave you on the old colours.

**Falcon Armor is not covered**, and neither is **Black Zero** — both keep
their usual colours whatever you set. Note that X6 starts you in Falcon, so
`x_palette` only shows once you are playing as plain X or have switched
armours.

Each preset keeps every colour's original brightness and changes only hue and
saturation, so shading survives; faces and skin are never repainted, and Zero
keeps his hair and helmet crystal.

A recoloured disc can only be restored to a clean dump by the `MMX6-Unpatcher`
from this release or later; the 0.1.1 unpatcher refuses it.
## 0.1.1 — 2026-08-28

**RE-PATCH YOUR DISC.** Two of the fixes below change the disc patch, so
updating the apworld alone is not enough: after installing it, patch a clean
dump again through Open Patch and play the new `.bin`.

**Seeds GENERATED on 0.1.0 should be REGENERATED**, not just re-patched. Two
of the fixes are logic bugs — the generator itself placed items on wrong
assumptions — and a re-patch cannot repair where a 0.1.0 fill already put
things. A `stage_unlocks` seed whose only Nightmare-wall opener is Shield
Sheldon is unwinnable and stays unwinnable until regenerated.

### An unkillable boss under `boss_hp_randomization` (re-patch)

Nightmare Pressure's entry wrote the rolled HP to two disc sites, and only
one of them is HP — the other is the exact-match threshold of the counter
that drives the fight's scripted transition. Rolling it meant the transition
never fired: you could destroy the boss's parts and then nothing could hurt
it. The non-HP site is removed, and the release gate now disassembles every
boss-HP site and requires the life-bar store nearby, so a lookalike byte can
never get in again.

### The Nightmare wall opens on Fire only (regenerate)

Blizzard Wolfang's fire-room wall was treated as opening on either Blaze
Heatnix's or Shield Sheldon's Nightmare Effect, because both can afflict
North Pole. Both afflict it; **only Fire opens the wall** (the game compares
the active effect against exactly one value), and Mirror overwrites Fire on
top of leaving the wall shut. Logic now requires Blaze Heatnix — beaten, and
under `stage_unlocks` therefore his Access Codes.

### Reploids have logic rules now (regenerate)

Reploid rescues carried no requirements at all, because which of a stage's
sixteen sat where was unknown. A full roster ended that: **40 of the 128**
now inherit the rule of the pickup they stand beside — the fire-room seven
in North Pole, the high-ledge and Another Route groups elsewhere — and only
where that pickup was already gated, so nothing is gated on a guess.

### The endgame gate stops fighting the game (client only)

The game opens Gate's Lab on its own at 3000 Nightmare Souls or on beating
High Max in an Another Route. The 0.1.0 client wrote it shut, the game wrote
it open again on the next stage exit, and the result was the unlock cutscene
replaying every stage while the Gate stayed enterable anyway. The client now
acts only on a Maverick count read on a screen it trusts, corrects the byte
at most three times, then stops and tells you plainly **not to fight Sigma
yet**. When the eighth Maverick falls it says the Gate is open, and the
early-entry warning no longer scolds a player who is legitimately inside the
endgame at 8/8.

### Honesty in the options

`zero_unlock`'s description now says what the game does: beating the Zero
Nightmare (the first Another Route boss) makes Zero playable with no item
involved, so the option gates Zero only for players who leave Another Routes
alone. Logic never assumes that shortcut — the fight is missable — so
nothing strands either way.

### What to watch in this release

- The endgame-gate concession is built from one tester's report and unit
  tests; the exact concede threshold has not been watched live. If you see
  the "DO NOT FIGHT SIGMA YET" warning, heed it and tell us.
- The Reploid gating derives from a community roster cross-checked against
  our own captures; individual fine positions are still guide-sourced. A
  Reploid the tracker calls reachable that you provably cannot reach (or the
  reverse) is a wanted report — say which Reploid number and stage.

## 0.1.0 — 2026-08-27

First release. Everything below was in development before it.

### The endgame is gated on all 8 Mavericks

Under the `all_mavericks` goal the Gate stays shut until every Maverick is
down, and the client opens it itself on the eighth. Vanilla does not enforce
that goal: beating High Max in an Another Route opens Gate's Lab early, and it
did, at three Mavericks, in the playthrough this release is built on.

That mattered more than it looks, because **there is no play after the
credits** — the credits return you to the title. A player who reached the
ending short had no way back except a save from before the endgame, which they
may never have made. The warning they used to get told them to keep playing,
which was impossible; it now tells them to reload a save.

### Reploids never expire

`protect_reploids`, on by default. A Reploid a Nightmare reached first used to
be gone for the rest of the playthrough. Now the three routines that record
one as lost record it as untouched instead, so it reappears next time you
enter the stage.

Losing one never cost you a *check* — the client counts a Reploid as checked
the moment its slot leaves the untouched state, destroyed included — but it
cost you the rescue, and that was pure attrition rather than a decision.

### Dialogue actually gets out of the way

`text_skip` removed dialogue but left everything it did not remove typing one
character at a time and waiting on a button. Cutscenes and story beats now
appear instantly and advance themselves. Mega Man X6 has no choice prompts, so
nothing is ever answered on your behalf.

### Fixed: Zero never got any gauge upgrades

X and Zero each own a life and a weapon gauge, and the client only ever wrote
X's. Since `zero_unlock` ships, playing as Zero is a supported path — and a
player who took it lost every Heart Tank, Life Up and Energy Up in the seed
while their life bar drew past its own frame, because heals were clamped
against X's maximum. Both characters' gauges are now written, and heals clamp
to whoever is actually playing.

Saves made before this fix repair themselves on the next connect.

### Fixed: a client restart could release items it was withholding

When a save shows progress the server has no record of, the client holds those
checks back rather than risk releasing another player's items. That decision
only ever lived in memory, so any reconnect — a crash, a Lua reload, a
savestate load — released everything it was holding. It now lives in server
data storage, and the release is a recorded one-time event rather than
something re-derived at every connect.

### Fixed: a withheld item could be held forever

An armor part or tank is held until its own location is checked, so that
setting the bit early cannot make that location uncollectable. The reasoning
was that everything is reachable, so the delay is bounded — but reachable is
not visited, and skipping a stage made the hold permanent. Everything held is
now released once you complete the goal.

### Added: MMX6-Unpatcher

A standalone tool that restores an AP-patched disc to a verified clean dump,
for anyone who patched over their only copy. It verifies the result before
writing anything and never modifies your patched file.

### What to watch in this first release

Stated so nobody has to guess what was and was not seen running:

- **`protect_reploids` is verified at the instruction level, not behaviourally.**
  All three patched routines read back patched in live RAM, but nobody has yet
  watched a Nightmare reach a Reploid and the Reploid survive it. If you lose
  a Reploid with the option on, that is a bug report we want.
- **The eight special-weapon item names came from a written guide** and have
  not all been checked against the in-game weapon-get text, so a name may
  differ slightly from what the game shows.
- **Zero's weapon gauge is written but its bar has not been watched.** X's
  gauges and Zero's life gauge are confirmed live; if Zero's weapon bar draws
  wrong after an upgrade, say so.
- **Reaching the ending early is remembered only until the client restarts.**
  If you see the ending short of eight Mavericks, finish the rest, but the
  client reconnected in between, the goal will not fire until you go through
  the endgame once more. Worst case is a second Sigma fight, not a broken
  seed.

## Development history

### The intro boss is no longer randomized

`boss_hp_randomization` left the tutorial boss alone from now on. A playtest
roll took it from 32 to 110 - three and a half times vanilla, fought with a
bare starting X before any upgrade exists. It is the first thing anyone
playing this world meets, and randomizing it bought nothing the other fifteen
bosses do not already provide.

The intro's second boss needed no change: its health is written by a site
outside the verified table, so it already kept vanilla values.

### Fixed: `stage_unlocks` could produce an unwinnable seed

Blizzard Wolfang's Heart Tank and EX Tank sit behind a wall that only opens
while a Nightmare Effect is active on North Pole, and only Blaze Heatnix or
Shield Sheldon can put one there - so one of them has to be beaten first.

That carried no logic rule, on the reasoning that both bosses are reachable
from the start so it costs nothing. True in vanilla. False the moment
`stage_unlocks` is on, because then both are behind their own Access Codes.

Staging a real seed produced exactly the bad case: Wolfang's Heart Tank held
Shield Sheldon's Access Codes, the only other opener was Blaze Heatnix whose
codes were two spheres further on, and fill had called the Heart Tank
reachable. Nobody could have finished that seed.

Both locations now additionally require Heatnix's or Sheldon's codes when
`stage_unlocks` is on, and nothing at all when it is off.

### Three new options: endgame checks, boss HP, and weapon damage

**`endgame_checks`** (on by default) turns the Gate opening and the Secret Lab
1 and 2 clears into checks. They read the game's own progression counter,
which only ever goes up and is written to the memory card, so a clear cannot
be lost by dying, quitting or reloading. Clearing Secret Lab 3 is deliberately
not a check - that is beating Sigma, which is already the goal. Adds three
locations and no items, so it can only ever make a seed easier to fit.

**`boss_hp_randomization`** gives every boss a new health bar between 32 and
127. Bosses that scale with your Hunter Rank keep their vanilla step between
ranks, so a higher rank never turns out to be the easier fight. This is a disc
edit rather than something the client writes, because X6 keeps the drawn bar
and the real health in the same byte - patching it means the bar you see is
always the health the boss has, which is a desync X5 could never quite close.

**`weapon_damage`** randomizes how much damage your weapons do, in the same
bands the X5 world uses. Each weapon rolls once and the roll covers every form
of it, so a charged shot can never come out weaker than the plain shot.

Boss weaknesses survive it. A boss's weakness is a row in that boss's own
damage table, so scaling one weapon by the same factor across all 46 tables
changes how strong the weapon is without flattening which bosses it is good
against - and there is a test that checks exactly that, pairwise, rather than
trusting the arithmetic.

Nothing rolls to zero, instant kills stay instant kills, and attacks that deal
no damage are left alone. Thirteen table entries are inert but still carry a
non-zero damage byte, so they are skipped on their state byte rather than on
their damage - skipping on damage alone would have edited them.

Both disc options carry the vanilla bytes they expect, verified as strictly as
the base patch, so a patch built for one dump cannot silently corrupt another.
The whole 46-table region is embedded and was checked byte-for-byte against a
real disc.

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
`exit_stage_anytime` was exercised in a stage on 2026-08-27 and works.

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
