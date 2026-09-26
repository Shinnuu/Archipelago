# Mega Man 8 apworld — changelog

## Unreleased — logic review: soft locks, bolt names

- **Duo's stage is in logic as soon as the first four Robot Masters are
  beaten**, because the game sends you there at that moment whether logic
  likes it or not. It used to wait for the Mega Ball and Thunder Claw, which
  only his two bolts need; those two now sit on the bolts. Duo's stage was
  checked on the disc to be clearable with the Mega Buster alone - its code
  reads none of your inventory, Duo takes buster damage, and the way down to
  him has no hook and no spikes - so being sent in early can never trap you.
- **Sword, Aqua, Astro and Search Man still expect the Mega Ball and Thunder
  Claw**, now stated outright: they used to follow from Duo's rule. The base
  game never lets a player into them without both, and nobody has checked
  whether their stages rely on it.
- **pickupsanity capsules now ask for what their stage's bolts ask for.** They
  had no requirements at all; the stage maps put several right beside bolts
  that need a weapon (Aqua Man's, for one).
- **Bolt locations are numbered in the order you reach them.** "Clown Man -
  Bolt 3" is now the third bolt you come to in Clown Man's stage; the
  numbers used to follow the game's internal order, which is how a
  playtester went looking for a bolt that was somewhere else entirely. The
  order was read from each stage's map on the disc and matches every run
  that was logged. Location IDs are unchanged.
- **New tests pin the soft-lock rules**: 160 generated seeds across every
  stage_unlocks / pickupsanity / rematch_checks / goal combination (never an
  Access Codes item in a Wily stage or in the stage it opens; everything
  reachable), a rule-level check that no stage's codes can be skipped on the
  way to Wily (Mega Man X5's tester deadlock), Duo's forced entry, and two
  Mega Man 8 slots in one multiworld.

## Unreleased — fixes from the first full playtest

- **A weapon received mid-stage arrives full.** The game only fills weapon
  energy when you spawn, so a weapon granted in the middle of a stage used
  to be usable but empty until your next death. The client now fills it as
  it grants it.
- **pickupsanity covers every placed capsule: 42, up from 35.** The intro's
  capsule and Wily Stages 1-3's six (two of them 1-UPs) joined: the intro
  replays from the stage select (the slot below Tengu Man), and a Wily stage
  comes back after an Exit or a save reload. Existing ids are unchanged.
- **New option: max_life** (Mega Man X5's `starting_hp`), 1-127, normal 40.
  Mega Man 8 has no life byte to set - 40 is written into the code that
  fills and caps your life - so the patch moves every one of those places:
  the teleport-in at the start of each life (rewritten to fill any maximum
  in its usual 60 frames), life capsules, full recovery, and the client's
  Life Energy. **The life bar does not grow** (unlike X5's): it stays its
  normal size and shows at most 40, so life above 40 is real but not shown.
- **Life Energy from the multiworld waits until you are in control.** Sent
  during a teleport-in, it could make the flying sections' entry run on and
  wrap round (a race vanilla's 40 already had).
- **New location: "Wily Stage 3 - Bass".** Beating Bass in the middle of
  Wily Stage 3 sends a check. He retreats instead of dying and the game
  keeps no record of it, so the client reads his defeat from the fight
  itself.

## Unreleased — Mega Man X5's options

Every X5 option with a Mega Man 8 equivalent, each built the way X5 (or X6)
builds it wherever the game allows, and differently only where the game's
own structure forces it:

- **text_skip** (default on): story dialogue types instantly and advances by
  itself - X5's two cuts in the message state machine, plus the per-letter
  sound. MM8's dialogue has no choices to protect.
- **skip_intro_videos** (default on): no Capcom logo, opening animation,
  attract demos or post-GAME START movie. All six movie calls in the game
  were enumerated; the story movies stay.
- **exit_stage_anytime** (default on): Exit in every stage but the intro,
  without the Exit part (which then counts as filler). In MM8 an Exit runs
  the stage-CLEAR routine, so opening the gate alone would have handed out
  free boss kills and Wily skips; an Exit is now marked and routed straight
  to the save prompt and stage select.
- **Fixed on every disc:** an Exit part received during the intro (or in
  starting inventory) let the player leave the intro unplayed, skipping its
  Mega Ball and three bolts.
- **weapon_damage**: one multiplier per weapon down its column of all 42
  enemy damage tables (X6's layout). The buster's charge levels, Laser and
  Arrow share one roll; what each weapon can hurt never changes.
- **boss_hp_randomization**: each Robot Master's fill target, shared by his
  Wily 4 rematch and his stage's Rush mini-boss. Grenade Man's fight starts
  only when his HP equals the target, so that gate moves with it.
- **boss_damage**: one multiplier per Robot Master over every place his
  attacks take their damage from - his body, the values his code sets or
  passes, and his projectiles' per-type rows - in his stage and his rematch.
  Two of Sword Man's sword writers are left alone (they set another value in
  the same instruction).
- **stage_unlocks**: X5's client-side slot table, locked with 0xFF (0 is a
  real stage in MM8's table).
- **pickupsanity**: 35 energy capsules in the Robot Master stages; drops,
  the demo and confirmed checks stay vanilla; an unconfirmed capsule keeps
  coming back.
- **rematch_checks**: read from the game's own Wily 4 refight record.
- **death_link**: HP 0 - every death in the game is exactly that write.
- **mega_man_palette**: X5's 18 presets on the buster colours, its 27
  per-stage copies and the charge/power-up flashes.
- **stage_music**: the thirteen stage themes dealt among the fourteen stages,
  X5's rules. MM8 keeps a stage's sound effects in the same bank as its
  music, so the patch rebuilds each stage bank - its own effects, another
  stage's music - and re-lays the SOUND area; with every stage given its own
  music the rebuild is byte-identical to the original disc.
- **randomize_options**.
- The rolls (weapon multipliers, boss HP) are in the spoiler.

## 0.0.1 — unreleased scaffold

**Not playable.** Generation and logic only; there is no disc patch and no
game client yet, so a seed produces no patch file.

- World, items, locations, options and reachability rules, following the
  Mega Man X5 and X6 worlds' structure.
- 74 locations: 40 bolts, 17 Lab entries, 8 Robot Masters, 4 Rush mid-bosses,
  the intro's Mega Ball, Duo's stage and Wily 1-3.
- Every bolt's stage is read off the disc (the stage packs' spawn lists), and
  its location id is `BASE + 100 + subId` - the subId is the bolt's bit in
  the game's own collected field, so detection needs no lookup.
- Bolt requirements come from a web guide; where the guide's numbering is not
  yet matched to the game's, a bolt carries every requirement in its stage.
  One bolt is matched from the disc (Tengu Man's Homing Sniper / Astro Crush
  panel).
- The Lab is gated on holding enough bolts for everything in stock, so no
  purchase order can strand a player.
- The Lab is repriced to 40 bolts in all (was 89), the game's own bolt count:
  each vanilla price scaled by 40/89 and rounded, 2 or 3 bolts a part. The
  first disc edits - 17 bytes of the EXE's shop table at 0x801505F0.
- Full-Lab guard: with every part 2-3 bolts a ninth purchase became
  possible, and vanilla stores it to address 0 when all eight slots are full.
  One instruction (0x8011EF1C) now answers "You already have the part"
  instead, until the shop patch takes purchases off the equip path.
- Capacity is checked in `generate_early`.
- A seed writes an `.apmm8`. Patching builds ONE merged `.bin` (patched Track 1
  + Tracks 2 and 3, found beside Track 1 by size and md5) and a single-FILE
  `.cue` that reproduces the Redump TOC exactly - BizHawk hashes it the same as
  the original set. The .bin is assembled under a temporary name, so an
  interrupted patch never leaves a half-disc behind.
- The Lab's text names each entry's item: just the item when it is yours,
  else whose it is, the item and the game. Mapped onto the game's own font
  (letters, digits, `? ! , . - + ' ( )`), wrapped to its 19-column, six-line
  box, and shortened together when a seed's names are too long for the
  text chunk's 2 KB.
