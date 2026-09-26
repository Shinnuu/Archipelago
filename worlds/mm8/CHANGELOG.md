# Mega Man 8 apworld — changelog

## 0.1.0 — 2026-09-26

First distributable release.

- **75 locations**: the 40 bolts, Dr. Light's Lab's 17 entries, the eight
  Robot Masters, the four Rush mini-bosses, the intro's Mega Ball, Duo's
  stage, Wily Stages 1-3 and Bass in Wily Stage 3. `pickupsanity` adds the 42
  capsules placed in the stages (the intro's and Wily 1-3's included);
  `rematch_checks` adds the eight Wily Stage 4 rematches.
- **Items**: the eight weapons, the Mega Ball, the four Rush adapters, the 17
  Lab parts — every part you receive works at once, with no limit of eight —
  Bolts bundles to spend in the Lab, and filler. `stage_unlocks` adds seven
  Access Codes.
- **Goals**: `wily` (clear the last Wily stage) and `robot_masters`.
- **Logic** follows the game's own order, keyed on bosses beaten rather than
  weapons held. Duo's forced entry after the fourth Robot Master is allowed
  for — his stage was checked on the disc to be clearable with the Mega Buster
  alone. Bolts are numbered in the order you reach them; capsules ask for what
  their stage's bolts ask for. The Lab survives any order of purchases: the
  nine entries on sale from the start never hold anything required, and the
  eight that appear after Duo wait for 40 bolts, enough for the whole Lab.
- **Disc patch**, Mega Man X5's design, built from a small `.apmm8`: every
  reward in the game is handed to Archipelago — a boss's weapon, the bolt
  counter, the Rush adapters and the Lab's purchases all become check records
  instead — and the client is the only thing that grants. The Lab is repriced
  to 40 bolts in all (the number of bolts in the game), and each entry's
  description names the item it holds, whose it is and from which game. The
  checks the game cannot re-derive ride in the memory card's unused bytes.
  Per-sector EDC/ECC regeneration. Patching builds one merged three-track
  `.bin` and a `.cue` from the Redump dump, reuses a disc it already made for
  the seed, rebuilds an outdated one, and refuses a patch made by an apworld
  whose disc code is laid out differently.
- **Options**: `text_skip`, `skip_intro_videos` and `exit_stage_anytime` (all
  on by default), `weapon_damage`, `boss_hp_randomization`, `boss_damage`,
  `max_life` (the life bar does not grow past 40), `stage_unlocks`,
  `pickupsanity`, `rematch_checks`, `death_link`, `stage_music`,
  `mega_man_palette`, `randomize_options`, and `bolt_bundle_size` (1-20) /
  `bolt_surplus` for the Lab's economy.
- **BizHawkClient**: acts only on this seed's disc; grants are absolute, and
  1-Ups and energy are counted in the save so none is applied twice; checks
  are re-sent until the server has them; rides out BizHawk and server
  disconnects. Requires BizHawk 2.7+ (tested on 2.10).
- **MM8-Unpatcher**, a separate download: drag a patched `.bin` or `.cue` onto
  it to get the three original Redump tracks and their `.cue` back, verified
  against the Redump hashes before anything is written. It also splits a
  clean dump that was merged into one `.bin`.
