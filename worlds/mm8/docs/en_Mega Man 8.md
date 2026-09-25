# Mega Man 8

> **In development.** A seed builds a patched disc and the BizHawk client
> plays it; not yet released.

## What does randomization do to this game?

Every weapon, Rush adapter and Dr. Light's Lab part is shuffled into the
multiworld, and so are the game's bolts. The Mega Buster is the only thing you
start with.

**Every bolt in a stage is a check.** Picking one up sends whatever item is
there, which may belong to someone else — it no longer adds a bolt to your own
count. Your bolts arrive as **Bolts** items instead.

**Dr. Light's Lab is a shop full of checks.** Each of its 17 entries holds an
item, and its description in the Lab tells you what that item is and whose it
is, so you know what you are buying. Buying an entry spends bolts and sends
the check.

## What is the goal?

- **wily** (default) — clear the last Wily stage.
- **robot_masters** — defeat all eight Robot Masters.

## How do stages open?

As in the base game, but on **bosses beaten** rather than weapons held — in a
randomizer, the weapon a boss would award is somebody else's item.

- Frost Man, Clown Man, Tengu Man and Grenade Man are open after the intro.
- Duo's stage opens once those four are beaten.
- Sword Man, Aqua Man, Astro Man and Search Man open once Duo's stage is clear.
- The Wily stages open once all eight are beaten.

## Items and locations

**75 locations:** 40 bolts, the Lab's 17 entries, the 8 Robot Masters, the 4
mid-bosses that award Rush adapters, the Mega Ball in the intro stage, Duo's
stage, the first three Wily stages and Bass in the third. `pickupsanity` adds
42 and `rematch_checks` 8.

**Items:** 8 weapons, the Mega Ball, 4 Rush adapters, 17 Lab parts, enough
Bolts for the whole Lab plus a surplus, and filler (1-Ups, life energy, weapon
energy). `stage_unlocks` adds seven Access Codes.

| Option | Effect |
|---|---|
| `bolt_bundle_size` (default **5**) | how many bolts one Bolts item is worth |
| `bolt_surplus` (default **40**) | how many bolts the pool holds beyond the Lab's 40, as a percentage |
| `text_skip` (default **on**) | story dialogue appears at once and advances by itself |
| `skip_intro_videos` (default **on**) | boot straight to the title, no attract demos, no movie after GAME START |
| `exit_stage_anytime` (default **on**) | Exit from the pause menu in every stage but the intro, without the Exit part - and it never counts as clearing the stage |
| `weapon_damage` | off / weak / regular / strong / chaotic - each of your weapons rolls a damage multiplier |
| `boss_hp_randomization` | off / weak / regular / strong / chaotic - each Robot Master (and his rematch and Rush mini-boss) rolls his HP |
| `boss_damage` | off / weak / regular / strong / chaotic - each Robot Master rolls how hard his whole move set hits you |
| `max_life` (default **40**) | Mega Man's maximum life, 1-127. **The life bar does not grow**: it stays its normal size and shows at most 40, so life above 40 is real but invisible on the bar |
| `stage_unlocks` | one of the first four Robot Master stages open; each other needs its "Access Codes" item |
| `pickupsanity` | the 42 capsules placed in the stages (energy and 1-UPs) become checks |
| `rematch_checks` | the eight rematches in Wily Stage 4 become checks |
| `death_link` | die when someone else dies, and they die when you do |
| `mega_man_palette` | recolour Mega Man - 18 presets |
| `stage_music` | shuffle the stage themes between stages; everything else keeps its music |
| `randomize_options` | the seed picks the gameplay options for you |

The Lab is repriced: each part costs 2 or 3 bolts, 40 in all — the number of
bolts in the game, where the original prices added up to 89.

Logic only expects you to shop once you could afford everything the Lab has in
stock — 21 bolts for the nine entries on sale from the start, 40 once Duo is
beaten — so no order of purchases can ever leave you stuck.

## Known limits

- Where a bolt needs a particular weapon comes from a player-written guide, and
  for most stages which bolt is which has not yet been matched to the game's
  own numbering. Until it is, logic asks for every weapon any bolt in that
  stage needs. You may find bolts reachable earlier than logic says; you will
  never be asked for one you cannot reach.
