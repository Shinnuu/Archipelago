from dataclasses import dataclass

from Options import (Choice, DeathLink, DefaultOnToggle, PerGameCommonOptions, Range,
                     StartInventoryPool, Toggle)

from . import palettes


def _palette_option(class_name: str, display_name: str, doc: str):
    """A 19-value Choice - vanilla plus the eighteen presets - generated from
    palettes.OPTION_KEYS so it can never offer a preset palettes.py lacks
    (X5's factory)."""
    namespace = {"__doc__": doc, "__module__": __name__,
                 "display_name": display_name, "default": 0}
    for value, key in enumerate(palettes.OPTION_KEYS):
        namespace["option_" + key] = value
    return type(class_name, (Choice,), namespace)


MegaManPalette = _palette_option("MegaManPalette", "Mega Man Colour", """Recolour Mega Man.

    Cosmetic only - no logic, items or locations change, and two players in
    the same multiworld can pick differently.

    Recolours his normal Mega Buster colours, and the flashes that go with
    them when he powers up or charges a shot. Each weapon's own colours are
    left alone, so you can still tell at a glance what you have equipped, and
    so is the glow of a fully charged shot. His face is never repainted.

    Every repainted colour keeps its original brightness and takes only the
    preset's hue and saturation, so his shading survives.

    `vanilla` leaves him alone. `random` is rolled when the seed is generated,
    so it is fixed and in the spoiler; it can land on vanilla.

    You do not need a new seed to change your mind: name a colour (or
    `random`) as `mega_man_palette` under `mm8_options` in your own host.yaml,
    delete the patched .bin and .cue, and open your .apmm8 again. A colour
    named there wins over this setting; `unset` (what Archipelago writes there
    by itself) and `vanilla` leave this setting in charge.
    """)


class Goal(Choice):
    """Victory condition.

    wily: clear the last Wily stage. The default.

    robot_masters: defeat all eight Robot Masters. Duo's stage and the Wily
    stages still hold checks under this goal.
    """
    display_name = "Goal"
    option_wily = 0
    option_robot_masters = 1
    default = 0


class BoltBundleSize(Range):
    """How many bolts one "Bolts" item is worth.

    Every bolt you pick up in a stage is a check, like any other - it no
    longer adds to your own bolt count. Your bolts come from "Bolts" items
    found in the multiworld instead, and Dr. Light spends them in the Lab.
    At 1, every Bolts item is one bolt, as in the base game.
    """
    display_name = "Bolt Bundle Size"
    range_start = 1
    range_end = 20
    default = 5


class BoltSurplus(Range):
    """How many bolts the item pool holds beyond what the Lab costs, as a
    percentage.

    Every one of the Lab's 17 entries is a check, and the randomizer prices
    them so that together they cost 40 bolts - the number of bolts in the
    game. Bolts never come back once spent, and the Lab sells whatever is in
    stock whether logic expects you there or not, so logic is built to
    survive buying in ANY order: the nine entries on sale from the start never
    hold anything required, and logic expects them once you have received 21
    bolts; the eight that appear after Duo can hold anything, and logic waits
    until you have received 40 - the whole Lab - before expecting those.

    The surplus is how much slack you get on top: at 40 the pool holds 60
    bolts (twelve bundles of 5). Logic counts the first 40; the other bundles
    are extra spending money.

    The pool has limited room. With small bundles and a big surplus the
    Bolts items may not fit; generation then stops and says so rather than
    silently dropping items - raise the bundle size, lower the surplus, or
    turn on Pickupsanity.
    """
    display_name = "Bolt Surplus"
    range_start = 0
    range_end = 100
    default = 40


class TextSkip(DefaultOnToggle):
    """Make dialogue get out of the way.

    Story scenes type their text out a letter at a time and stop at every
    page until you press a button. With this on, each page appears at once
    and moves on by itself, so the intro, Duo's stage, the Bass scene and
    Wily's castle play through without input. The pages still scroll and the
    windows still slide at their normal pace, so scenes get much quicker
    rather than vanishing.

    Nothing gets answered for you: Mega Man 8's dialogue never asks a
    question. The Lab's purchase prompt, the save prompt and the continue
    screen are menus, and they wait for you exactly as before.

    You will not be able to read the story at this speed. Turn it off for a
    first playthrough.

    Changes the disc.
    """
    display_name = "Text Skip"


class SkipIntroVideos(DefaultOnToggle):
    """Boot straight to the title screen, and start a new game without the
    opening movie.

    Skips the Capcom logo, the opening animation (which also replays every
    time the title screen's demo loop comes round), the attract-mode demos,
    and the movie that plays after GAME START. The story movies before and
    after Duo and the ending are untouched - each of those is already one
    button press to skip.

    Changes the disc.
    """
    display_name = "Skip Intro Videos"


class ExitStageAnytime(DefaultOnToggle):
    """Let you leave any stage from the pause menu.

    Normally Exit needs the Exit part from Dr. Light's Lab, and even then
    only works in a stage whose boss you have already beaten. A randomized
    run is full of trips into a stage for one check, and of stages you cannot
    finish yet, so this opens Exit everywhere - the eight Robot Masters,
    Duo's stage and all four Wily stages - without the part.

    Leaving is only ever leaving. It never counts as beating the stage: no
    boss check, no weapon, no story progress, and a Wily stage you leave is
    the one you return to. You get the save prompt, then the stage select.
    The one place that differs is Duo's stage before you have beaten it: the
    game will not show the stage select until Duo is cleared, so leaving puts
    you straight back into his stage.

    The intro stage is the one exception, as it is in Mega Man X5: it cannot
    be left early, with or without this option.

    With this on the Exit part itself does nothing, and it counts as filler.

    Changes the disc.
    """
    display_name = "Exit Stage Anytime"


class WeaponDamage(Choice):
    """Randomize how much damage YOUR weapons do.

    Each weapon is rolled once and keeps that roll for the whole seed, so
    part of the run is finding out which of your weapons came out strong.

    off: unchanged
    weak: 50-90% of normal
    regular: 80-130% of normal
    strong: 120-200% of normal
    chaotic: 25-250% of normal

    The Mega Buster rolls ONCE for all its shots - plain, half charge, full
    charge, and the Laser and Arrow charge shots - so a charged shot never
    comes out weaker than a plain one. Rush's Bike and Bomber shots roll as
    weapons of their own, and so does the shot of the flying sections (Tengu
    Man's stage and Wily Stage 2).

    What each weapon can hurt does not change: a weapon that could not damage
    something still cannot, and one that could still can - so every bolt
    behind a breakable wall needs the same weapons as before. Nothing rolls
    to zero.

    Stacks with Boss HP Randomization.

    Changes the disc.
    """
    display_name = "Weapon Damage"
    option_off = 0
    option_weak = 1
    option_regular = 2
    option_strong = 3
    option_chaotic = 4
    default = 0


class BossHPRandomization(Choice):
    """Randomize how much HP the eight Robot Masters have.

    Only the Robot Masters and their Rush mini-bosses, unlike Mega Man X5's,
    which also rolls its other mid-bosses and endgame fights: the intro
    stage's boss, Duo and the Wily stages' own bosses keep their normal HP.

    Each Robot Master rolls once for the seed, and the roll covers his own
    stage, his rematch in Wily's fourth stage, and the Rush mini-boss in his
    stage where there is one. Normal is 40 (the mini-bosses 32 or 40).

    off: unchanged
    weak: 40-80% of normal
    regular: 70-130% of normal
    strong: 120-200% of normal
    chaotic: 25-250% of normal

    The health bar shows at most 40. A boss rolled above that fills the bar,
    and the bar only starts to fall once his health drops to 40 - the extra
    is real, the bar just cannot show it. The most any roll gives is 100.

    A boss with little HP can start below the point where he changes tactics,
    so a low roll may open straight into his late-fight behaviour.

    Changes the disc.
    """
    display_name = "Boss HP Randomization"
    option_off = 0
    option_weak = 1
    option_regular = 2
    option_strong = 3
    option_chaotic = 4
    default = 0


class BossDamage(Choice):
    """Randomize how much damage the eight Robot Masters do to YOU.

    The mirror of Weapon Damage. Each Robot Master rolls once and keeps the
    shape of his own move set, so his light attacks stay light next to his
    big one - the whole fight gets more or less dangerous together. The roll
    covers his rematch in Wily's fourth stage too.

    off: unchanged
    weak: 50-90% of normal
    regular: 80-130% of normal
    strong: 120-200% of normal
    chaotic: 25-250% of normal

    Nothing rolls to zero. Separate from Boss HP Randomization: that one
    changes how long a fight lasts, this one how badly it hurts.

    One exception, to be exact about it: some of Sword Man's sword swings keep
    their normal strength. The game sets that number together with another
    value in the same instruction, so those swings cannot be changed alone.

    Changes the disc.
    """
    display_name = "Boss Damage"
    option_off = 0
    option_weak = 1
    option_regular = 2
    option_strong = 3
    option_chaotic = 4
    default = 0


class MaxLife(Range):
    """How much life Mega Man has. Normal is 40. THE LIFE BAR DOES NOT GROW:
    unlike Mega Man X5's Starting Life, where a bigger maximum draws a longer
    bar, Mega Man 8's bar stays its normal size and shows at most 40.

    Above 40 the bar stays full until your life drops below 40 - the extra
    life is real and it protects you, but you cannot see it on the bar. Below
    40 a full bar is only that tall, so it looks partly empty even at full
    life.

    Mega Man 8 has no Heart Tanks - his life never grows - so this sets it
    for the whole run. Everything that fills it respects the new maximum:
    teleporting in at the start of every life, life capsules, full recovery,
    and the Life Energy the multiworld sends you.

    1 is one hit from anything. 127 is the most: the game's instant-kill
    hazards do 127 damage, and above that they would stop killing. Two
    attacks that normally kill from full life become heavy hits instead once
    you have more: one in Aqua Man's stage (40 damage) and, above 64, one in
    Sword Man's.

    Changes the disc.
    """
    display_name = "Max Life"
    range_start = 1
    range_end = 127
    default = 40


class StageUnlocks(Toggle):
    """Lock the eight Robot Master stages behind items.

    Normally the first four Robot Masters are all open once the intro is
    done. With this on, exactly ONE Robot Master stage is open at the start -
    always one of those first four, chosen by the seed - and each of the
    other seven needs its own "<Boss> Access Codes" item.

    The game's own structure stays: the second four still only appear after
    Duo, so each of those needs Duo beaten AND its codes. Duo's stage, the
    Lab and the Wily stages are never locked.

    A locked stage still shows on the stage select and the cursor still moves
    onto it; pressing confirm simply does nothing until you hold its codes.

    Client-side: the lock is applied by the client, not written into the
    disc.
    """
    display_name = "Stage Unlocks"


class PickupSanity(Toggle):
    """Freestanding pickups become checks - the intro stage's capsule
    included, unlike Mega Man X5's, because Mega Man 8's intro can be
    replayed.

    Every Life Energy, Weapon Energy, Weapon Energy Refill and 1-UP capsule
    placed in a stage becomes a location - 42 in all: 35 in the Robot Master
    stages (16 of them in Frost Man's), one in the intro stage and six in
    Wily Stages 1-3. Energy dropped by defeated enemies is not affected.

    Touching one sends its check instead of restoring anything; the energy is
    in the item pool as filler. Until the server has the check, the capsule
    comes back every time the stage section restarts (a death, the midpoint,
    or coming back to the stage), so nothing is lost to a disconnect. Once it
    is confirmed, the capsule works normally again.

    Every stage can be gone back to: the intro replays from the stage select
    (the slot below Tengu Man), and a Wily stage is played again after an
    Exit, or after reloading a save, which restarts Wily's fortress at its
    first stage.

    Not included: the 1-UP in Clown Man's stage that only the Mega Ball can
    break open.

    Changes the disc.
    """
    display_name = "Pickupsanity"


class RematchChecks(Toggle):
    """The Robot Master rematches in Wily's fourth stage send checks.

    Adds eight locations, one per Robot Master, for beating his rematch in
    the teleporter room of Wily Stage 4. The game keeps its own record of
    which rematches you have won, so each check is exact.

    If you die after winning a rematch but before the teleporter takes you
    back, the game makes you fight that boss again - but the check has
    already been sent, so nothing is lost.

    Client-side: needs no disc change.
    """
    display_name = "Rematch Checks"


class StageMusic(Toggle):
    """Shuffle the music between stages.

    Every stage keeps a real stage theme - the thirteen themes the stages
    already use are dealt back out among them. Frost Man's stage might get
    Aqua Man's music, a Wily stage a Robot Master's, and no stage keeps the
    theme it started with. There are fourteen stages and thirteen themes, so
    one theme turns up twice; the intro and Duo's stage, which share a theme
    in the original game, each get their own.

    ONLY stage themes change. Boss and mini-boss music, the stage select, the
    Lab, the weapon-get screen, cutscenes and the ending keep their original
    music, and every stage keeps its own sound effects.

    A stage sounds the same every time you enter it. Purely cosmetic - it
    moves no checks and changes no logic.

    Changes the disc: in Mega Man 8 a stage's music and its sound effects
    live in one sound bank, so the patch rebuilds the stage banks rather than
    just pointing a stage at another song.
    """
    display_name = "Stage Music"


class RandomizeOptions(Toggle):
    """Let the seed pick your gameplay options for you.

    Rolls `goal`, `text_skip`, `pickupsanity`, `weapon_damage`,
    `boss_hp_randomization`, `boss_damage` and `stage_unlocks`. Whatever you wrote for those
    in your YAML is ignored. `rematch_checks` is left alone - it only ever
    adds checks, so there is nothing to gamble on - and so are the colours,
    DeathLink and the other conveniences.

    If the roll ever asks for more items than the seed has locations,
    `pickupsanity` is switched on to make room rather than failing.

    The result is in the spoiler log. This can turn on options that change
    the disc, so patch your disc from the file this seed generates.
    """
    display_name = "Randomize Options"


# Options RandomizeOptions rolls, kept beside it so the two cannot drift.
RANDOMIZED_OPTIONS = ("goal", "text_skip", "pickupsanity", "weapon_damage",
                      "boss_hp_randomization", "boss_damage", "stage_unlocks")


@dataclass
class MM8Options(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    randomize_options: RandomizeOptions
    goal: Goal
    bolt_bundle_size: BoltBundleSize
    bolt_surplus: BoltSurplus
    text_skip: TextSkip
    skip_intro_videos: SkipIntroVideos
    exit_stage_anytime: ExitStageAnytime
    weapon_damage: WeaponDamage
    boss_hp_randomization: BossHPRandomization
    boss_damage: BossDamage
    max_life: MaxLife
    stage_unlocks: StageUnlocks
    pickupsanity: PickupSanity
    rematch_checks: RematchChecks
    death_link: DeathLink
    stage_music: StageMusic
    mega_man_palette: MegaManPalette
