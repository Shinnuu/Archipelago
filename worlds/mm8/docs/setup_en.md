# Mega Man 8 Setup Guide

> **Not playable yet.** A seed's `.apmm8` builds a patched disc, but the game
> client is not written, so there is nothing to connect. This page exists so
> the world passes Archipelago's documentation checks and so the eventual
> instructions have a home.

## What will be required

- A Mega Man 8 (USA) disc image. You must supply your own; none is
  distributed. Mega Man 8 is a **three-track disc** — one data track and two
  audio tracks, plus a `.cue` — and all of it is needed.
- BizHawk 2.10 or newer, with the Nymashock PlayStation core.
- A PlayStation BIOS in BizHawk's `Firmware/` folder.
- **A digital controller.** Mega Man 8 predates the DualShock and ignores an
  analog pad completely. If the game seems not to respond to any button, switch
  the pad to digital.
- The Archipelago Mega Man 8 Client, launched from the Archipelago Launcher.

## Generating a seed today

Generation works. Add `Mega Man 8` to your YAML with the options described on
the game info page and generate as normal. Your `.apmm8` builds a disc from
Track 1 of your dump - set `mm8_options: rom_file` in `host.yaml` to the
`(Track 1).bin`, with Tracks 2 and 3 beside it. The result is ONE `.bin` and a
`.cue`; load the `.cue` in BizHawk.
