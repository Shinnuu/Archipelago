# Mega Man X6

> **Testing release.** Generation, the disc patch and the game client all work,
> and the whole stack has been played. You need the standard Redump dump of
> Mega Man X6 (USA) (Rev 1) — see the setup guide.

## What does randomization do to this game?

Weapons, armor parts, tanks, Heart Tanks and the upgrades carried by rescued
Reploids are shuffled into the multiworld item pool. You start with the buster
and the Falcon Armor, exactly as vanilla does, and everything else arrives as a
multiworld item — possibly from someone else's game.

All eight investigation sites are open from the start, as in vanilla, so
routing is yours to decide.

## What is the goal?

- **all_mavericks** (default) — defeat all 8 Mavericks, then reach and defeat
  Sigma.
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
| `zero_unlock` (**on by default**) | **+1 item** — Zero has to be found before you can play as him, which is how the base game works |
| `secret_armors_in_pool` | **+2 items** — Ultimate Armor and Black Zero |
| `stage_unlocks` | **+7 items** — only one investigation site is open at the start, and each of the others needs its own Access Codes. A locked site greys out on the stage select and confirming it does nothing |

Every item needs a location, so option sets that ask for more items than the
seed has room for are refused at generation with a message naming what to
change, rather than silently dropping items.

### Quality-of-life

These change the disc rather than the pool, so they add no items and no
locations — but they do mean your patched disc depends on the options you
generated with. Patch from the file the seed produced rather than reusing an
older image.

| Option | Effect |
|---|---|
All three are **on by default**.

| Option | Effect |
|---|---|
| `exit_stage_anytime` | The pause menu offers Exit Stage before you have beaten that stage's boss. A randomized run is full of trips into a stage for one check and entries into a stage you cannot finish yet; without this, leaving means dying on purpose |
| `text_skip` | Skips the in-stage Navigator calls, the other in-stage dialogue, the stage-select briefings and the Nightmare Souls explanation, mutes the alert chime, and doubles cutscene text speed. No prompt, menu or choice is answered for you |
| `skip_intro_videos` | Skips the Capcom logo and the title-screen opening, and stops the attract demos from starting. **It does not skip the cutscene that plays when you begin a game** — that runs from a different call site, which has not been located |

The quality-of-life edits are adapted from acediez's **Mega Man X6 Tweaks**,
with each site re-verified against both supported disc images.

Turning `reploid_checks` off leaves a 29-location seed, which is not really
enough for one player, let alone a multiworld. It is there for completeness.

## Reploids can be destroyed — and the randomizer does not let that cost you

Mega Man X6's defining hazard is that a Nightmare reaching an injured Reploid
before you do leaves it dead or missing, permanently. In a multiworld that
would mean an item lost for good, possibly somebody else's progression.

So the check is collected the moment you reach the Reploid rather than when the
rescue completes. What happens to it afterwards is cosmetic as far as
Archipelago is concerned.

## What does another world's item look like?

Nothing is changed visually yet. Picking up an item that belongs to someone
else grants nothing locally and sends it to its owner.

## Special weapons work differently here

In the base game, beating a Maverick and gaining its weapon are the same fact
in the same byte, which is why a randomizer cannot simply hand you a weapon
without also claiming you beat its boss. The patch separates them, so weapons
become real multiworld items and can arrive in any order.

One consequence you will notice: the game latches your weapon list when a stage
starts, so a weapon received mid-stage is not selectable immediately. Dying
re-latches it, so you never have to leave the stage to pick it up.

**Shadow Armor still cannot use special weapons.** That is a real Mega Man X6
rule and it is left alone, so if you are wearing Shadow you have no special
weapons no matter what Archipelago has sent you. Nothing is lost — pick a
different armor at the stage select and they come back. It is worth knowing
before you walk into High Max, who only takes damage from a charged special
weapon.
