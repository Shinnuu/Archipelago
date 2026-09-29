# Mega Man 8

## What does randomization do to this game?

Every weapon, Rush adapter and Dr. Light's Lab part is shuffled into the
multiworld, and so are the game's bolts. The Mega Buster is the only thing you
start with (and, with `stage_unlocks`, one stage's Access Codes).

**Every bolt in a stage is a check.** Picking one up sends whatever item is
there, which may belong to someone else — it no longer adds a bolt to your own
count. Your bolts arrive as **Bolts** items instead. A stage's bolts are
numbered in the order you reach them: "Clown Man - Bolt 3" is the third one
you come to.

**Dr. Light's Lab is a shop full of checks.** Each of its 17 entries holds an
item, and its description in the Lab tells you what that item is and whose it
is, so you know what you are buying — the entry's name and picture stay the
original part's. When the item is one of your own parts, the description also
says what it does. Buying an entry spends bolts and sends the check.

**Parts are items, and every one you receive works at once** (Energy Saver
from your next life). There is no limit of eight and nothing to equip; a part
stays on once you have it. When a part arrives while the BizHawk Client is
connected, the client says in a few words what it does.

**The Rush mini-bosses still drop their adapters**, which look as they always
did; touching one sends its check.

## What is the goal?

- **wily** (default) — clear the last Wily stage.
- **robot_masters** — defeat all eight Robot Masters.

## How do stages open?

As in the base game, but on **bosses beaten** rather than weapons held — in a
randomizer, the weapon a boss would award is somebody else's item. With the
default `stage_order: vanilla`:

- Frost Man, Clown Man, Tengu Man and Grenade Man are open after the intro.
- Duo's stage opens once those four are beaten — and, as in the base game,
  the fourth of them sends you **straight into it**: no stage select, no Lab,
  no way out until Duo is beaten. That is always safe: Duo's stage can be
  cleared with the Mega Buster alone, so logic never asks for anything there
  except for its two bolts, each of which needs both the Mega Ball and Thunder
  Claw — you can come back for them, as the stage stays on the select
  afterwards.
- Sword Man, Aqua Man, Astro Man and Search Man open once Duo's stage is clear.
  Logic also expects the **Mega Ball and Thunder Claw** before sending you
  into them: the base game never lets anyone reach these four without both.
- The Wily stages open once all eight are beaten. Logic also expects all eight
  weapons.

`stage_order: open` opens all eight Robot Master stages from the start. The
game still sends you to Duo once Frost, Clown, Tengu and Grenade Man are
beaten, whatever else you have done. `stage_order: open_any_four` sends you to
Duo after **any** four. Either way the second four still want the Mega Ball
and Thunder Claw in logic, and Wily opens once all eight are beaten and Duo is
cleared. Duo's stage stays shut on the stage select until his turn **while the
BizHawk Client is connected** — the client applies that lock.

**Sword Man's stage has four trials** (whatever the stage order), one for each
of the first four Robot Masters' weapons. A row of pillars past the stage's
hub only opens once all four are done, and everything after it is behind
them: the Rush mini-boss, Sword Man and the stage's last bolt, and with
`pickupsanity` the capsules in the pillars' corridor and in the lava room.
Logic expects **Tornado Hold, Thunder Claw, Ice Wave and Flash Bomb** for all
of those.

**Search Man's stage has doors only Tornado Hold opens** — the last one just
before his shutter — so logic expects **Tornado Hold** for Search Man as well
as for his bolts.

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
| `bolt_bundle_size` (default **5**) | how many bolts one Bolts item is worth, 1-20 |
| `bolt_surplus` (default **40**) | extra bolts on top of the Lab's 40, as a percentage, rounded up to whole Bolts items: with bundles of 5, 0 gives 40, 40 gives 60 (twelve items), 100 gives 80 |
| `text_skip` (default **on**) | story dialogue appears at once and advances by itself |
| `skip_intro_videos` (default **on**) | boot straight to the title, no attract demos, no movie after GAME START |
| `exit_stage_anytime` (default **on**) | Exit from the pause menu in every stage but the intro, without the Exit part - and it never counts as clearing the stage |
| `weapon_damage` | off / mild / moderate / wild / extreme - each of your weapons rolls a damage multiplier |
| `boss_hp_randomization` | off / mild / moderate / wild / extreme - each Robot Master (and his rematch and Rush mini-boss) rolls his HP |
| `boss_damage` | off / mild / moderate / wild / extreme - each Robot Master rolls how hard his whole move set hits you |
| `max_life` (default **40**) | Mega Man's maximum life, 1-127. **The life bar does not grow**: it stays its normal size and shows at most 40, so life above 40 is real but invisible on the bar |
| `stage_order` (default **vanilla**) | vanilla / open / open_any_four - which Robot Master stages are open from the start, and when the game sends you to Duo (above) |
| `stage_unlocks` | one of the first four Robot Master stages open; each other needs its "Access Codes" item |
| `pickupsanity` | the 42 capsules placed in the stages (energy and 1-UPs) become checks |
| `rematch_checks` | the eight rematches in Wily Stage 4 become checks |
| `death_link` | die when someone else dies, and they die when you do |
| `mega_man_palette` | recolour Mega Man - 18 presets |
| `stage_music` | shuffle the stage themes between stages; everything else keeps its music |
| `randomize_options` | the seed picks the gameplay options for you |

The three randomizers above share their settings, and each setting is a
**width**, centred on normal — a roll is as likely to land above normal as
below it: mild 80-125%, moderate 67-150%, wild 57-175%, extreme 50-200%. Boss
HP therefore spans 20-80 at its widest (normal is 40; the 32-HP Rush
mini-bosses 16-64). Mega Man X5's settings pick a direction instead: its
`weak` is always below normal and its `strong` always above. The old names
(`weak`, `regular`, `strong`, `chaotic`) still work and mean mild, moderate,
wild and extreme. Damage is a whole number, so small hits move in steps: a
1-damage hit can go up but never down.

The Lab is repriced: each part costs 2 or 3 bolts, 40 in all — the number of
bolts in the game, where the original prices added up to 89.

Bolts never come back once spent, and the Lab sells whatever is in stock, so
logic is built so that no order of purchases can leave you stuck: any of the
17 entries can hold anything, and logic waits until you have received 40
bolts — enough for the whole Lab — before expecting any of them. The eight
that appear after Duo also need Duo cleared.

## The Lab parts

| Part | What it does |
|---|---|
| Energy Saver | Special weapons use about a third less energy. |
| Power Shield | No knockback when hit, and you stay invincible longer after. |
| Energy Balancer | Energy you pick up with the Buster out (or while the weapon in hand is full) fills your emptiest weapon. |
| Exit | Leave a cleared stage from the pause menu (with `exit_stage_anytime` on, it does nothing — every stage but the intro already allows it). |
| Super Recover | Health and weapon energy pickups restore more. |
| High Speed Charge | The charge shot charges faster. |
| Shooting Part | Up to 5 Buster shots on screen at once, not 3. |
| Spare Extra | A Game Over or a loaded save gives you at least 4 lives, not 2 (and Spare Charger refills to 4). |
| Boost Part | Buster shots fly faster. |
| Rapid Part | Each press fires three Buster shots. |
| Laser Shot | Charge shot becomes a piercing laser. Pick it in the pause menu. |
| Arrow Shot | Charge shot becomes a powerful arrow. Pick it in the pause menu. |
| Auto Shoot | Once charged, holding fire keeps firing, instead of a charge shot. Pick it in the pause menu. |
| Spare Charger | Entering a stage refills your lives to 2 (4 with Spare Extra). |
| Hyper Slider | You slide faster. |
| Exchanger | At full life, health pickups refill the special weapon you hold (with Energy Balancer, your emptiest weapon, even with the Buster out). |
| Step Booster | You climb ladders faster. |

## Known limits

- Where a bolt needs a particular weapon comes from a player-written guide, and
  for most stages which bolt is which has not yet been matched to the game's
  own numbering. Until it is, logic asks for every weapon any bolt in that
  stage needs. You may find bolts reachable earlier than logic says; you will
  never be asked for one you cannot reach.
- With `pickupsanity`, a capsule asks for the same weapons as the bolts of its
  stage — no guide covers the capsules, and several sit right beside bolts
  that need something. Again: sometimes earlier than logic says, never later.
