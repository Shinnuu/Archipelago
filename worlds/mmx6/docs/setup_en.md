# Mega Man X6 Setup Guide

> **Testing release.** Everything works end to end — a seed emits a patch, the
> patch builds a playable disc, and the client connects and plays.

## What you need

- **Mega Man X6 (USA)**, as a raw `.bin`/`.cue` pair with 2352-byte sectors —
  the same format the Mega Man X5 world wants. You must supply your own; none
  is distributed here.
- **BizHawk 2.10**, with the **Nymashock** PlayStation core. The connector
  requires 2.7.0 or newer and merely warns on later versions, but 2.10 is what
  it is tested against.
- A **PlayStation BIOS** in BizHawk's `Firmware/` folder. BizHawk will tell you
  which file it wants the first time you open a PSX disc.
- The **Archipelago Mega Man X6 Client**, from the Archipelago Launcher.

## Which disc

You want the standard **Redump** dump, `Mega Man X6 (USA) (Rev 1)`. That is
what almost everybody has.

| accepted image | MD5 |
|---|---|
| `Mega Man X6 (USA) (Rev 1)` — Redump | `237b6feddd1a88e86ab1cddc8822f03f` |
| the same disc with 8 trailing blank sectors | `ae1f630f686edb48f84f8d69346bc8a8` |

Both are accepted because both have been patched and checked. The second is
the development copy this world was built on; it is byte-for-byte the Redump
disc with eight empty sectors on the end, and the game's actual code
(`SLUS_013.95` and `ROCK_X6.BIN`) is identical in the two.

Patching verifies the image before touching it and refuses anything else, so
an unexpected disc fails loudly instead of producing a subtly broken game.

## Setup

1. Generate a seed with `Mega Man X6` in your YAML. You get a **`.apmmx6`**
   file.
2. Open the **Archipelago Launcher** and choose **Open Patch**, then select
   your `.apmmx6`. The first time, it asks for your Mega Man X6 disc image and
   remembers it afterwards.
3. It writes a patched `.bin`/`.cue` next to the patch file. This is the disc
   you play — keep your original untouched.
4. The **Mega Man X6 Client** opens automatically. Enter your slot name and
   connect it to the room.
5. Open **BizHawk 2.10**, load the **patched** `.cue`, then open
   **Tools → Lua Console** and load Archipelago's `connector_bizhawk_generic.lua`
   from your Archipelago folder's `data/lua/`.
6. The client reports the game once the connector attaches, and play begins.

## Things worth knowing

**A newly granted weapon appears after the next stage load.** The game latches
your weapon list when a stage starts, so an item that arrives mid-stage will
not be selectable straight away. **Dying is enough** to pick it up — you do not
have to leave the stage.

**Save in-game normally.** Archipelago re-applies everything you have received
whenever you connect, so a reload never loses granted items. BizHawk does not
flush its memory card automatically, though: press **Ctrl+S** (Flush SaveRAM)
after saving in-game, or close the ROM cleanly, or the save exists only in
emulated RAM.

**Savestates belong to the disc they were made on.** A state taken on your
unpatched disc restores that disc's code, which undoes the patch until you
reload the ROM. Keep states made on the patched disc, and when in doubt reload
the ROM and load your in-game save instead.

**Connecting a save that has progress but no checks** is held back on purpose,
with an explanation in the client. Archipelago works out whether a save belongs
to this seed by asking whether the slot has ever checked anything; a save that
has progressed on a slot with no history is ambiguous, so it waits rather than
guessing and sending checks you did not earn. **Collect any one check that is
not one of the held ones and the rest are sent** — you no longer need to
reconnect for it, and restarting the client will not release them by itself.

**Some items wait until you visit the place they belong.** An armor part or a
tank you receive from someone else is not applied to your save until you have
checked that part's own location, because setting the bit early stops the
capsule or tank from spawning and would make the location impossible to
collect. The client tells you when it is doing this and which check releases
it.

The consequence is worth knowing before it happens: **if you skip a stage
entirely, an item held against something in it stays held.** You can earn a
W Tank in the Secret Lab and never see it because Shield Sheldon's stage was
one you decided not to play. Nothing is lost permanently — everything releases
once you complete the goal — but during the run, skipping content can cost you
items you won somewhere else.
