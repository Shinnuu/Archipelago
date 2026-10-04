# Mega Man 8 apworld — changelog

## 0.2.1 — 2026-10-04

From the testers' run of 0.2.0.

**Updating from 0.2.0 mid-seed: just open your `.apmm8` again** (with BizHawk
closed); the patcher rebuilds the disc and memory-card saves carry over. The
logic changes and the new capsule apply to new seeds only; the pause screen's
parts row fills on any seed once the 0.2.1 client is connected. The 0.2.0
apworld refuses a 0.2.1 patch rather than half-applying it. Use
**MM8-Unpatcher v1.2**: v1.1 refuses 0.2.1 discs.

- **Each bolt asks only for what it needs.** Until now every bolt in a stage
  waited on everything any bolt there needed, so all of Frost Man's waited on
  Astro Crush and all of Clown Man's on the Rush Bike, Mega Ball, Flame Sword
  and Tornado Hold. Each bolt now takes its own entry from the bolt guide,
  matched to the bolts in the order you reach them (the game's own data
  confirms the matching where it can). Where the game's data cannot tell two
  bolts apart - Aqua Man's 3 and 4 - each still asks for what either needs.
  Search Man's Bolt 3 asks only for Flame Sword (a tester's account, which the
  guide and the game's data agree with). Clown Man's Bolt 4, at the top of the
  lift room, now asks for the Mega Ball or Tornado Hold (a tester's account;
  the guide asked for nothing), and his Bolt 5 for Tornado Hold and the Mega
  Ball. Duo's second bolt, past the first, asks for the Mega Ball as well as
  Thunder Claw, and Search Man's last bolt for Tornado Hold, as his doors
  stand before it. Logic still expects the Mega Ball and Thunder Claw before
  any of the last four Robot Master stages, so a tracker shows nothing in
  them until you have both.
- **Search Man's Bolt 2 and Bolt 3 swap names**, so that "Bolt 2" is the
  second one you reach, as in the bolt guide. Only the names change.
- **With `pickupsanity`, each capsule asks only for what it needs**: what the
  bolt beside it needs, or nothing out on the stage's route. The Frost Man
  health capsule in plain sight no longer waits on Astro Crush.
- **New check: Frost Man's ice block.** The ice block on the ledge above Frost
  Man's Bolt 6 drops a Large Life Energy when it breaks. With `pickupsanity`
  it is a check, "Frost Man - Large Life Energy 5", and logic expects Astro
  Crush for it.
- **The pause screen's parts row shows your parts** - the first eight you
  received (the row has room for eight). It was always empty: a part is an
  item, so the game never equipped one.

## 0.2.0 — 2026-09-29

From the first testers' run of 0.1.0.

**Updating from 0.1.0 mid-seed: just open your `.apmm8` again** (with BizHawk
closed). The patcher now compares the disc it would make with the one you have
and rebuilds it whenever they differ, so your 0.1.0 disc is replaced by one
with the fixes below; memory-card saves carry over. The logic fixes (Sword
Man, Search Man) apply to new seeds only. Use **MM8-Unpatcher v1.1**: v1.0 refuses 0.2.0
discs.

- **Lab prices show as numbers.** 0.1.0's 2- and 3-bolt prices drew as the
  confirm dialog's NO and CANCEL: the game counts along a strip of pictures
  laid out for its original prices, 4 to 7, and 2 and 3 landed on the
  dialog's labels. The price now uses the bolt counter's digits.
- **Sword Man's trials are in logic.** His stage has four trials, one for each
  of the first four Robot Masters' weapons, and a row of pillars past the
  stage's hub only opens once all four are done. 0.1.0 asked only for Thunder
  Claw (and Flash Bomb for the last bolt), so about one seed in eight put
  Tornado Hold past the trials, where it cannot be reached. Logic now expects
  Tornado Hold, Thunder Claw, Ice Wave and Flash Bomb for everything past the
  pillars: the Rush mini-boss, Sword Man, the stage's last bolt and, with
  `pickupsanity`, the two capsules there.
- **Search Man needs Tornado Hold in logic.** His stage's second half has doors
  only Tornado Hold opens, the last just before his shutter; 0.1.0 asked for
  it for his bolts but not for him, so about one seed in fourteen put Tornado
  Hold on Search Man himself or behind him.
- **A 0.1.0 seed stuck at either needs the host to send the weapon**
  (`/send <player> <item>` in the server console): the logic fixes apply to
  new seeds only.
- **New option `stage_order`**: `vanilla` (default), `open` (all eight Robot
  Master stages open from the start; Duo still comes after Frost, Clown, Tengu
  and Grenade Man) or `open_any_four` (all eight open; Duo after any four).
  Wily still opens once all eight are beaten and Duo is cleared. While the
  BizHawk Client is connected, Duo's stage stays shut on the stage select
  until his turn.
- **The Lab's first nine entries can hold anything**, Access Codes included.
  Logic now expects every entry once you have received 40 bolts, the whole
  Lab's price (0.1.0: 21 for the first nine, which then could hold nothing
  required). No order of purchases can leave you stuck.
- **`weapon_damage`, `boss_hp_randomization` and `boss_damage` roll evenly
  around normal.** The settings are now `mild`, `moderate`, `wild` and
  `extreme`: 80-125%, 67-150%, 57-175% and 50-200%, as likely above normal as
  below. 0.1.0's (Mega Man X5's) settings picked a direction instead - `weak`
  boss HP started every health bar short. The old names still load, as
  mild, moderate, wild and extreme, but no longer mean weaker or stronger.
- **Parts say what they do.** When a Lab part arrives while the client is
  connected, the client log says so in a few words ("Boost Part - faster
  shots"); your own parts' Lab entries describe them; the game page lists all
  17.
- **`bolt_surplus` is explained plainly**, shown as "Extra Bolts (%)".
- **Re-opening a patch always gives the right disc** (above). The client also
  says so if the Lab on screen comes from a disc made before 0.2.0, and the
  0.1.0 apworld now refuses a 0.2.0 patch instead of half-applying it.

## 0.1.0 — 2026-09-28

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
