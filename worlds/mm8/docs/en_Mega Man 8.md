# Mega Man 8

> **Not playable yet.** Generation works and a seed produces a patch file that
> builds the disc - with the repriced Lab and each Lab entry naming what it
> holds - but there is no game client yet, and the patches that hand weapons,
> bolts and the rest to Archipelago are still being written.

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

**74 locations:** 40 bolts, the Lab's 17 entries, the 8 Robot Masters, the 4
mid-bosses that award Rush adapters, the Mega Ball in the intro stage, Duo's
stage, and the first three Wily stages.

**Items:** 8 weapons, the Mega Ball, 4 Rush adapters, 17 Lab parts, enough
Bolts for the whole Lab plus a surplus, and filler (1-Ups, life energy, weapon
energy).

| Option | Effect |
|---|---|
| `bolt_bundle_size` (default **5**) | how many bolts one Bolts item is worth |
| `bolt_surplus` (default **40**) | how many bolts the pool holds beyond the Lab's 40, as a percentage |

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
