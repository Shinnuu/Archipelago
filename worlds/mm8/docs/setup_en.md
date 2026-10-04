# Mega Man 8 Setup Guide

## Required software

- **Archipelago** 0.6.7 or later
  ([releases](https://github.com/ArchipelagoMW/Archipelago/releases)), and the
  `mm8.apworld` file from the
  [Mega Man 8 releases](https://github.com/Shinnuu/Archipelago/releases?q=mm8).
- **BizHawk 2.7 or newer**
  ([releases](https://github.com/TASEmulators/BizHawk/releases)) — 2.7.0 is
  the minimum Archipelago's connector script accepts. This world was tested
  on **2.10**; newer versions print an untested-version warning from the
  connector but are expected to work. On first install, run BizHawk's
  prerequisites installer if EmuHawk won't start. The PSX core is
  **NymaShock** (BizHawk's default for PS1).
- A **US-region PS1 BIOS** (e.g. SCPH-5501), dumped from your own console. In
  EmuHawk: **Config → Firmware**, find the PSX (U) entry and point it at your
  BIOS file — or drop the file into BizHawk's `Firmware` folder.
- A **Mega Man 8 (USA) (SLUS-00453) disc image**, dumped from your own copy.
- **A digital controller setting.** Mega Man 8 predates the DualShock and
  ignores an analog pad completely. BizHawk's default PS1 pad is digital; if
  the game ever seems not to respond to any button, check that first.

### The disc image: three tracks

Mega Man 8 is a **three-track disc**: one data track and two audio tracks, plus
a `.cue`. The standard (Redump) dump comes as four files:

```
Mega Man 8 (USA).cue
Mega Man 8 (USA) (Track 1).bin
Mega Man 8 (USA) (Track 2).bin
Mega Man 8 (USA) (Track 3).bin
```

All three tracks are needed. The patcher checks them by MD5:

| Track | MD5 |
|---|---|
| Track 1 | `4e9e6dcf27ea0e15c5f4d1f93c800378` |
| Track 2 | `a75dcbb5c831a966c47563e7ea4150c9` |
| Track 3 | `2d7b5e8e94a91bf5423b2356f6a34863` |

To check a file on Windows:

```
certutil -hashfile "Mega Man 8 (USA) (Track 1).bin" MD5
```

Keep the three `.bin` files together in one folder. Tracks 2 and 3 are found
beside Track 1 by their size and MD5, so their names do not matter.

## Installing the apworld

Put `mm8.apworld` in your Archipelago install's `custom_worlds` folder, then
restart the Archipelago Launcher. "Mega Man 8" should appear in the games list.

**Everyone in a multiworld must use the same `mm8.apworld` version** — the
game edits live in the apworld, so a mismatch between the generator and a
player produces a disc that does not match the seed.

## Generating and patching

1. Generate a game with a Mega Man 8 YAML (produce a template from the
   Launcher's **Generate Template Options**).
2. From the finished seed you will receive an **`.apmm8`** file.
3. Open it via the Launcher's **Open Patch**. The first time, Archipelago asks
   for your disc image: point it at **`(Track 1).bin`** — not the `.cue`, and
   not Track 2 or 3. (It is remembered as `rom_file` under `mm8_options` in
   Archipelago's `host.yaml`.)
4. This produces **one** patched `.bin` and a `.cue` beside the patch file.
   The `.bin` holds all three tracks; your original dump is never modified.

**Patch a new disc for every seed.** The disc carries a stamp naming its seed,
and the client will not act on a disc patched for another one.

**Opening the same `.apmm8` again always gives you the right disc.** The
patcher builds the disc in memory and compares it with the one already beside
the patch: if they match, it leaves the file alone; if anything differs (you
updated the apworld, changed a colour in `host.yaml`, or the file is damaged),
it rebuilds it. So after updating the apworld, just open your patch again. If
it says the disc is in use, close BizHawk first — Windows will not replace a
file BizHawk has open. Your memory-card saves carry over to the rebuilt disc.

## Mega Man's colour (optional)

`mega_man_palette` recolours Mega Man's normal buster colours and the flashes
that go with them. Purely cosmetic: no items, locations or logic change, and
two players in the same multiworld can pick differently. It accepts `vanilla`,
`random`, or one of: crimson, scarlet, amber, gold, olive, forest, emerald,
teal, cyan, azure, blue, indigo, violet, magenta, rose, silver, black, white.

`random` is rolled when the seed is generated, so it is fixed and in the
spoiler; it can land on vanilla.

To change it without a new seed, name a colour as `mega_man_palette` under
`mm8_options` in Archipelago's `host.yaml` and open the same `.apmm8` again
(close BizHawk first): the patcher rebuilds the disc with the new colour. Archipelago writes `unset` there by itself, and
`unset` or `vanilla` there leaves your YAML in charge — so to play in the
original colours, choose `vanilla` in your YAML.

## Playing

By default **Open Patch does the setup for you**: the first time, it also asks
where `EmuHawk.exe` is, and from then on it starts BizHawk with the patched
disc and the connector script already loaded, and opens the **BizHawk
Client**. Connect the client to the room's address with your slot name.

If BizHawk did not start (or you turned that off in `host.yaml`), do it by
hand:

1. Open **BizHawk** and load the patched **`.cue`**.
2. Open **Tools → Lua Console**, then **Script → Open Script**, and load
   `data/lua/connector_bizhawk_generic.lua` from your Archipelago install.
3. From the Archipelago Launcher, start the **BizHawk Client** and connect it
   to the room's address with your slot name.

Once connected, play normally — checks send themselves and items arrive as you
go.

## Things worth knowing

- **Every patched Mega Man 8 disc shares ONE memory card and one set of
  savestate slots** with the original game and with every other seed —
  BizHawk calls them all "Mega Man 8 (USA)", whatever the file is named.
  - **A savestate from another seed is refused.** The client says the disc was
    "patched for a different seed" and does nothing until you load one of this
    seed's states or reset. Nothing is sent from it. **With `stage_music` on,
    reset rather than play on** from such a state: it carries the other disc's
    table of where the music lives, and the next stage's music would load from
    the wrong place.
  - **A memory-card save from another seed — or from the original game — is
    taken as THIS seed's.** Loading it sends what the game itself recorded —
    bosses beaten, bolts collected, Duo's clear, the intro's Mega Ball — as
    this seed's checks, at once. **Start a New Game for each new
    seed**, and save over an old slot.
  - **Savestates carry the memory card too**, so loading an old state rolls
    back any saves you made after it.
  - **Do not load an Archipelago save in the original game.** It gets the
    parts and bolts Archipelago gave you, and with eight parts already held,
    the original Lab's next purchase runs into a bug of the game's own.
- **Save your memory card to disk.** BizHawk writes it on a clean close, when
  you press **Flush SaveRAM** (`Ctrl+S` by default), or every few minutes if
  autosave is on under `Config → Customize → Advanced`. An unclean exit loses
  what came after the last write.
- **Bolts you pick up are checks.** They no longer add to your count; your
  bolts come from **Bolts** items. Each Lab entry's description names the item
  it holds and whose it is — and, for your own parts, what the part does. The
  entry's name and picture above it stay the original part's.
- **Every part you receive works at once, all together.** There is no limit
  of eight and nothing to equip: buying a Lab entry sends its check and equips
  nothing, and a part stays on once you have it. The pause screen's parts
  row (and the Lab's "equipped" panel) shows the first eight parts you
  received - the client fills it - and every part works whether shown or
  not. Laser, Arrow and Auto Shoot are picked on the pause screen as usual.
  (Energy Saver takes effect from your next life.) When a part arrives while
  the client is connected, the client log says in a few words what it does.
- **A Rush mini-boss still drops its adapter**, looking as it always did;
  touching it sends the check. The adapter itself is an item like any other.
- **Weapons work the moment they arrive**, with full energy — even in the
  middle of a stage.
- **Life Energy items wait until you are in control.** One that arrives while
  you are teleporting in, dying or held by a cutscene is applied a moment
  later.
- **The intro stage cannot be exited, but it can be replayed**: its stage is
  the slot below Tengu Man on the stage select.
- **Exit (`exit_stage_anytime`) is only ever leaving.** It never counts as
  beating the stage, and a Wily stage you leave is the one you come back to.
  Duo's stage before you have beaten it puts you straight back in, because the
  game shows no stage select until Duo is cleared.
- **Life bars show at most 40.** That holds for Mega Man with `max_life` above
  40 and for bosses rolled above 40 by `boss_hp_randomization`: the bar stays
  full until the life drops below 40. The extra is real.
- **With `pickupsanity`, a capsule sends its check instead of restoring
  anything**, and it comes back every time the stage section restarts until the
  server has the check. After that it works normally.
- **"Wily Stage 3 - Bass" is sent while Bass retreats** after the fight. Let
  his parting scene play out rather than resetting straight away. It, and the
  `rematch_checks` rematches, are seen only while the client is connected:
  the game keeps no record the client could read later, so one missed while
  disconnected means playing that fight again.
- **With `stage_unlocks`, a locked stage still shows on the stage select**;
  pressing confirm on it simply does nothing. The client log lists your open
  stages each time a new one arrives.
- **With `stage_order` open, the stage select's second page is there from the
  start** — move to the page button at the bottom to flip to it. Duo's stage
  shows on it but does nothing until his turn; that lock is the client's, so
  keep the client connected.

## Troubleshooting

**The client connects to the room but never sees the game.** The connector Lua
is not running in BizHawk, or your BizHawk is older than 2.7.

**The client says "this is not a disc patched by this version of the Mega Man 8
apworld".** Either a savestate from the original game (or an older disc) is
loaded — reset, or load one of this seed's states — or the disc itself is the
original or outdated: close BizHawk, open your `.apmm8` again (it rebuilds an
outdated disc), and load the `.cue` it makes.

**The client says the Lab "comes from a disc made by an older Mega Man 8
apworld", or the Lab prices show NO / CANCEL.** You are playing a disc made
before 0.2.0 (or a savestate taken on one). Close BizHawk and open your
`.apmm8` again: the patcher rebuilds the disc, and your memory-card saves
carry over.

**The patcher says the disc "has to be rebuilt ... but another program has it
open".** BizHawk still has the old disc loaded. Close BizHawk, then open the
`.apmm8` again.

**The patcher says the `.apmm8` "was made by a different version of the Mega
Man 8 apworld".** The seed was generated with another apworld version than the
one you have installed — usually a newer one. Install the version the seed was
generated with (a newer apworld also opens older seeds' patches).

**The client says "this disc was patched for a different seed or slot".** You
loaded another seed's disc or one of its savestates. Load this seed's `.cue`,
or reset.

**The patcher rejects my disc image.** Check Track 1's MD5 against the table
above, and that Tracks 2 and 3 are in the same folder. The usual causes are
pointing it at the `.cue` or at another track, or a dump made in a different
format.

**I no longer have my clean dump.** Download the standalone
**MM8-Unpatcher** from the
[Mega Man 8 releases](https://github.com/Shinnuu/Archipelago/releases?q=mm8)
— the newest one: an older unpatcher refuses a disc made by a newer apworld —
and drag a patched `.bin` (or its `.cue`) onto it. It rebuilds the three
original track files and their `.cue` in an "(unpatched)" folder beside the
disc, checks all three against the Redump hashes before it writes anything,
and never changes the file you gave it. Point `rom_file` under `mm8_options`
in `host.yaml` at the Track 1 in that folder. It also splits a clean dump
that was merged into a single `.bin` back into its three tracks.

**The game does not respond to any button.** The controller is set to analog.
Switch BizHawk's PS1 pad to digital.

**I changed a colour and nothing happened.** Open the `.apmm8` again (with
BizHawk closed) and load the `.cue` it makes — or an entry under
`mm8_options` in `host.yaml` is overriding your YAML.
