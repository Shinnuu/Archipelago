# Mega Man 8 Setup Guide

## Required software

- **Archipelago** 0.6.7 or later
  ([releases](https://github.com/ArchipelagoMW/Archipelago/releases)), and the
  `mm8.apworld` file.
- **BizHawk 2.7 or newer**
  ([releases](https://github.com/TASEmulators/BizHawk/releases)) — 2.7.0 is
  the minimum Archipelago's connector script accepts. This world was tested
  on **2.10**; newer versions print an untested-version warning from the
  connector but are expected to work. The PSX core is **NymaShock** (BizHawk's
  default for PS1).
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
   not Track 2 or 3.
4. This produces **one** patched `.bin` and a `.cue` beside the patch file.
   The `.bin` holds all three tracks; your original dump is never modified.

**Patch a new disc for every seed.** The disc carries a stamp naming its seed,
and the client will not act on a disc patched for another one.

## Mega Man's colour (optional)

`mega_man_palette` recolours Mega Man's normal buster colours and the flashes
that go with them. Purely cosmetic: no items, locations or logic change, and
two players in the same multiworld can pick differently. It accepts `vanilla`,
`random`, or one of:

> crimson · scarlet · amber · gold · olive · forest · emerald · teal · cyan ·
> azure · blue · indigo · violet · magenta · rose · silver · black · white

`random` is rolled when the seed is generated, so it is fixed and in the
spoiler; it can land on vanilla.

To change it without a new seed, name a colour as `mega_man_palette` under
`mm8_options` in Archipelago's `host.yaml`, **delete the `.bin` and `.cue` you
made before** (the patcher skips its work if a disc of that name already
exists), and open the same `.apmm8` again. `vanilla` in `host.yaml` does
nothing — Archipelago writes that value there by itself — so to play in the
original colours, choose `vanilla` in your YAML.

## Playing

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
    seed's states or reset. Nothing is sent from it.
  - **A memory-card save from another seed is taken as THIS seed's.** Loading
    it sends everything that save has done — bosses beaten, Duo, the intro's
    Mega Ball — as this seed's checks, at once. **Start a New Game for each
    new seed**, and save over an old slot.
- **Save your memory card to disk.** BizHawk writes it on a clean close, when
  you press **Flush SaveRAM** (`Ctrl+S` by default), or every few minutes if
  autosave is on under `Config → Customize → Advanced`. An unclean exit loses
  what came after the last write.
- **Bolts you pick up are checks.** They no longer add to your count; your
  bolts come from **Bolts** items. Each Lab entry's description names the item
  it holds and whose it is.
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
  his parting scene play out rather than resetting straight away.
- **With `stage_unlocks`, a locked stage still shows on the stage select**;
  pressing confirm on it simply does nothing. The client log lists your open
  stages each time a new one arrives.

## Troubleshooting

**The client connects to the room but never sees the game.** The connector Lua
is not running in BizHawk, or your BizHawk is older than 2.7.

**The client says "this is not a disc patched for this Archipelago
version".** You loaded the original disc, or a disc from an older version of
the apworld. Open your `.apmm8` and load the `.cue` it makes.

**The client says "this disc was patched for a different seed or slot".** You
loaded another seed's disc or one of its savestates. Load this seed's `.cue`,
or reset.

**The patcher rejects my disc image.** Check Track 1's MD5 against the table
above, and that Tracks 2 and 3 are in the same folder. The usual causes are
pointing it at the `.cue` or at another track, or a dump made in a different
format.

**I no longer have my clean dump.** Download the standalone
**MM8-Unpatcher** from the apworld's release page and drag a patched `.bin`
(or its `.cue`) onto it. It rebuilds the three original track files and their
`.cue` in an "(unpatched)" folder beside the disc, checks all three against the
Redump hashes before it writes anything, and never changes the file you gave
it. Point the Mega Man 8 setting at the Track 1 in that folder.

**The game does not respond to any button.** The controller is set to analog.
Switch BizHawk's PS1 pad to digital.

**I changed a colour and nothing happened.** The patcher did no work because a
`.bin`/`.cue` of that name already existed — delete the old pair and open the
patch again — or an entry under `mm8_options` in `host.yaml` is overriding
your YAML.
