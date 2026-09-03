# Mega Man X6

## What does randomization do to this game?

Weapons, armor parts, tanks, Heart Tanks and the upgrades carried by rescued
Reploids are shuffled into the multiworld item pool. You start with the buster
and the Falcon Armor, exactly as vanilla does, and everything else arrives as a
multiworld item — possibly from someone else's game.

All eight investigation sites are open from the start, as in vanilla, so
routing is yours to decide. (`stage_unlocks` changes that if you want it to.)

## What is the goal?

- **all_mavericks** (default) — defeat all 8 Mavericks, then reach and defeat
  Sigma. The randomizer also holds Gate's Lab shut until all eight are down,
  so you cannot reach the ending early; see the notes below.
- **sigma** — defeat Sigma, however you got there. Mega Man X6 does not open
  its endgame on Maverick kills at all: it opens on a Nightmare Soul count of
  3000, and souls drop from Nightmare enemies throughout every stage. So under
  this goal a run can legitimately finish having skipped Mavericks.

## What items and locations get shuffled?

**Items (28 before options):** the 8 special weapons, all 8 armor parts (Blade
and Shadow sets), 8 Heart Tanks, 2 Sub Tanks, the W Tank and the EX Tank.

**Locations (29 before options):** the intro stage, plus per investigation site
— the boss, its Heart Tank, its armor capsule — plus the four tank pickups.

| Option | Effect |
|---|---|
| `reploid_checks` (**on by default**) | **+128 locations** and **+16 items** — every rescuable Reploid becomes a check, and the Life Ups and Energy Ups they carry join the pool |
| `parts_in_pool` (**on by default**) | **+24 items** — the equippable Power-up Parts |
| `zero_unlock` (**on by default**) | **+1 item** — Zero joins the pool instead of being available from the start. Note the game can still unlock him on its own: the first Another Route boss is the Zero Nightmare, and beating it makes him playable with no item involved. Logic never assumes that, because that fight is missable |
| `endgame_checks` (**on by default**) | **+3 locations** — the Gate opening, and clearing Secret Lab 1 and Secret Lab 2. Adds no items, so it can only make room. Clearing Secret Lab 3 is not a check: that is beating Sigma, which is the goal |
| `secret_armors_in_pool` | **+2 items** — Ultimate Armor and Black Zero |
| `stage_unlocks` | **+7 items** — only one investigation site is open at the start, and each of the others needs its own Access Codes |

Every item needs a location, so option sets that ask for more items than the
seed has room for are refused at generation with a message naming what to
change, rather than silently dropping items.

Turning `reploid_checks` off leaves a 29-location seed, which is not really
enough for one player, let alone a multiworld. It is there for completeness.

## Which options change the disc?

**`text_skip`**, **`skip_intro_videos`**, **`exit_stage_anytime`**,
**`protect_reploids`**, **`boss_hp_randomization`**, **`weapon_damage`** and
**`difficulty`** are all applied to the disc image itself rather than by the
client. Patch from the file the seed produced rather than reusing an older
image, and re-patch whenever you change one of them.

With every disc option off, the patched image differs from your clean dump by
exactly **three bytes** — the weapon/kill separation described below.

The first four are **on by default**. The quality-of-life edits are adapted
from acediez's **Mega Man X6 Tweaks**, with every site re-verified against both
supported disc images.

**Player colours are the odd one out.** X, Zero, Shadow, Blade and Ultimate can
each be recoloured, but the choice is not in your YAML — it lives in your own
`host.yaml` and is applied while the patch is opened. Changing your mind costs
nothing (no new seed, no effect on anyone else), but it is not a live toggle:
delete your old `.bin`/`.cue` and open the same `.apmmx6` again. Falcon Armor
and Black Zero are not covered and keep their usual colours. The setup guide
has the details.

## Anything unusual I should know?

- **Special weapons are separated from boss kills.** In the base game, beating
  a Maverick and gaining its weapon are the same fact in the same byte, which
  is why a randomizer cannot hand you a weapon without also claiming you beat
  its boss. The patch separates them, so weapons become real multiworld items
  and can arrive in any order. One consequence you will notice: the game
  latches your weapon list when a stage starts, so a weapon received mid-stage
  is not selectable immediately. **Dying re-latches it**, so you never have to
  leave the stage to pick it up.
- **Shadow Armor still cannot use special weapons.** That is a real Mega Man X6
  rule and it is left alone, so while you are wearing Shadow you have no
  special weapons no matter what Archipelago has sent you. Nothing is lost —
  pick a different armor at the stage select and they come back. Worth knowing
  before you walk into High Max, who only takes damage from a charged special
  weapon.
- **`protect_reploids` stops Reploids being destroyed, and is on by default.**
  In the base game a Reploid you do not reach in time is gone for the rest of
  the playthrough — a Nightmare carries it off, or it is killed in the
  crossfire, and its slot records "death" or "missing" forever. With this on,
  the three routines that record a Reploid as lost record it as untouched
  instead, so it simply reappears next time you enter the stage. Rescuing is
  unchanged.
- **Losing a Reploid never costs you a check, even with that option off.** The
  client counts a Reploid as checked the moment its slot leaves the untouched
  state, and "destroyed" counts exactly as much as "rescued". So a Nightmare
  that beats you to one costs you the rescue, never the item. This is belt and
  braces on purpose: the option is what lets you go back for it, and this is
  what makes sure a multiworld can never lose an item to it.
- **`scaravich_no_progression` answers Central Museum's random rooms.** Ground
  Scaravich's stage is assembled from totem-pole rooms the game picks four of
  at random each time you enter, and its Heart Tank, its Blade Armor Helmet and
  fifteen of its sixteen Reploids are behind that roll — so hunting one
  particular check there can mean walking the stage again and again. With the
  option on, every location in that stage holds junk. The checks are still
  real and still send if you go and get them; they are simply never worth
  re-rolling for. It also stops the client holding your Blade Armor Helmet
  back until you find that capsule, which is the one case where the usual
  hold could wait on a room you never see.
- **The endgame is gated on all 8 Mavericks under `all_mavericks`.** Vanilla
  does not enforce that goal — beating High Max in an Another Route opens
  Gate's Lab early, and there is **no play after the credits**, so reaching the
  ending short would leave you with no way back except a save from before the
  endgame. The client holds the Gate shut until all eight are down and opens it
  itself on the eighth. Under the `sigma` goal nothing is gated.
- **`text_skip` makes dialogue get out of the way.** It removes the in-stage
  Navigator calls, the other in-stage dialogue, the stage-select briefings and
  the Nightmare Souls explanation, and mutes the alert chime. Everything that
  is left — cutscenes, story beats — then types out instantly and advances on
  its own instead of waiting on a button at every box. Mega Man X6 has no
  choice prompts, so nothing is ever answered on your behalf. You will not be
  able to follow the story at this speed; leave it off for a first playthrough.
- **`skip_intro_videos` boots you to the title screen.** It skips the Capcom
  logo and the title-screen opening and stops the attract demos from starting.
  **It does not skip the cutscene that plays when you begin a game** — that
  runs from a different call site, which has not been located. Said plainly
  because an earlier version of this option claimed otherwise and a player
  found out the hard way.
- **`exit_stage_anytime` lets you leave before beating the boss.** A randomized
  run is full of trips into a stage for one check, and of entering stages you
  cannot finish yet. Without this, leaving means dying on purpose.
- **`stage_unlocks` turns the stage select into a progression gate.** Exactly
  one investigation site is open at the start — the seed picks which — and each
  of the other seven needs its own "&lt;Boss&gt; Access Codes" item. A locked
  site greys out and confirming it does nothing until its codes arrive.
- **`difficulty` picks the game's own difficulty setting.** `easy` gives fewer
  and weaker enemies and a slightly larger starting life gauge, `normal` is the
  standard game, `xtreme` is the hardest. Mega Man X6 is famously punishing, so
  `easy` is a real option rather than a joke setting. It only changes how hard
  the game hits — it can never change what is reachable, so it never affects
  logic or your checks.
- **`boss_hp_randomization` rerolls how tough bosses are.** Every boss gets a
  new health bar between 32 and 127, the range the bar can actually draw.
  Bosses that scale with your Hunter Rank keep their vanilla step between
  ranks, so a higher rank never becomes the easier fight. A few bosses —
  Nightmare Mother, Dynamo, and High Max's higher ranks — store health in a
  form this does not yet handle and keep their vanilla values. Rolls are fixed
  for a seed, so dying and retrying gives you the identical fight.
- **`weapon_damage` rerolls how hard your weapons hit.** `weak` is 50–90% of
  normal, `regular` 80–130%, `strong` 120–200%, `chaotic` 25–250%. Each weapon
  rolls **once** and keeps its shape, so a charged shot can never come out
  weaker than the plain shot. **Boss weaknesses are preserved** — a weapon that
  was good against a boss still is, it is just stronger or weaker overall.
  Nothing rolls to zero and instant kills stay instant kills. It stacks with
  `boss_hp_randomization`, and `weak` weapons against randomized boss health is
  a very different game.
- **`randomize_options` lets the seed choose your settings.** It rolls the
  goal, difficulty, `parts_in_pool`, `zero_unlock`, `secret_armors_in_pool`,
  `text_skip`, `stage_unlocks`, `boss_hp_randomization` and `weapon_damage`,
  and ignores what you wrote for them. `reploid_checks` is left alone because
  turning it off would shrink the seed to 29 locations, and
  `protect_reploids` is left alone because rolling it off would hand you a run
  where checks you can see are quietly destroyed as you play. If the roll asks
  for more items than the seed can hold, `reploid_checks` is turned on to make
  room rather than refusing to generate. Since the roll can enable
  disc-changing options, patch your disc from the file the seed produced.
- **Some items wait until you visit the place they belong.** An armor part or a
  tank you receive is not applied to your save until you have checked that
  part's own location, because setting the bit early stops the capsule or tank
  spawning and would make the location impossible to collect. The client tells
  you when it is doing this and which check releases it. The consequence worth
  knowing: **if you skip a stage entirely, an item held against something in it
  stays held** — you can earn a W Tank in the Secret Lab and never see it
  because you decided not to play Shield Sheldon's stage. Everything held is
  released once you complete the goal.
- **Gauge upgrades apply to both X and Zero.** Each character has his own life
  and weapon gauge and the game normally keeps them in step through its own
  pickup routine, which an Archipelago grant does not go through. The client
  writes both, so playing as Zero gets you everything the seed has sent.
- **Checks appear a few seconds after a boss dies**, not instantly — the game
  commits the kill at the Mission Report, a little after gameplay ends.
- **Use a fresh save file, and patch your disc.** The client works out what you
  have done by reading the game's memory, so it has to be sure it is reading
  *your* run. Two things it will refuse: a disc that was never patched, and a
  save that already has progress this seed has never seen — a copied memory
  card, the wrong slot, or a savestate from before you connected. In both cases
  it holds everything back and tells you what to do rather than reporting
  progress you did not make. Starting a new game and clearing the intro before
  you open the client is fine.
- **Filler items** — Small and Large Life Energy, Weapon Energy, and Extra
  Lives — pad the pool when there are more locations than real items. A heal
  arriving between stages waits until you are in one, rather than being thrown
  away.

## What does another world's item look like in Mega Man X6?

Nothing is changed visually. Picking up an item that belongs to someone else
grants nothing locally and sends it to its owner.
