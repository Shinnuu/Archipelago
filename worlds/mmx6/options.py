from dataclasses import dataclass

from Options import (Choice, DefaultOnToggle, PerGameCommonOptions,
                     StartInventoryPool, Toggle)


class Goal(Choice):
    """Victory condition.

    all_mavericks: defeat all 8 Mavericks, then reach and defeat Sigma. The
    default, and the way most people want to play.

    sigma: defeat Sigma, however you got there. Mega Man X6 does not open its
    endgame on Maverick kills at all - it opens on a Nightmare Soul count of
    3000, and souls drop from Nightmare enemies throughout every stage. So
    under this goal a run can legitimately finish having skipped Mavericks.
    """
    display_name = "Goal"
    option_sigma = 0
    option_all_mavericks = 1
    default = 1


class Difficulty(Choice):
    """Which difficulty the game runs at.

    normal: the standard game. The default.

    easy: fewer and weaker enemies, and X starts with a slightly larger life
    gauge. Mega Man X6 is a famously punishing game; this is a real option,
    not a joke setting.

    xtreme: the hardest setting.

    This only changes how hard the game hits. It cannot change what is
    reachable, so it never affects logic or your checks.
    """
    display_name = "Difficulty"
    option_easy = 0
    option_normal = 1
    option_xtreme = 2
    default = 1


class ReploidChecks(DefaultOnToggle):
    """Rescuing an injured Reploid sends a check.

    Adds 128 locations - 16 in every stage - which is by far the largest check
    source in the game, and the reason to play Mega Man X6 in a multiworld at
    all. With this off the seed has only 29 locations, which is not really
    enough for one player, let alone a multiworld.

    It also decides where the Life Ups and Energy Ups come from. In the base
    game those 16 upgrades are carried by specific Reploids, so with this off
    they are not in the pool at all and your gauges stay at their base size.

    IMPORTANT - Reploids can be permanently destroyed in Mega Man X6. A
    Nightmare that reaches one first leaves it dead or missing, and that state
    never clears. In a multiworld that would mean an item lost for good,
    possibly somebody else's progression, so the randomizer does not allow it:
    a Reploid counts as checked once its slot leaves the untouched state, and
    "destroyed" counts just as much as "rescued". Losing one to a Nightmare
    costs you the life it would have given, never the check.

    The other way a check could have gone missing does not happen here either,
    and it was worth confirming rather than assuming, because the Mega Man X5
    engine gets it wrong. There, rescuing at the nine-life cap consumes the
    Reploid and records nothing, so the check becomes uncollectable. Tested
    directly in X6: at nine lives the rescue still records, and only the extra
    life is discarded.
    """
    display_name = "Reploid Checks"


class PartsInPool(DefaultOnToggle):
    """Shuffle the 24 equippable Power-up Parts into the item pool.

    In the base game Parts are found lying in stages and carried by rescued
    Reploids. With this on they become Archipelago items instead, so they can
    end up anywhere in the multiworld.

    Needs `reploid_checks` on - 24 extra items do not fit in a 29-location
    seed. Generation will tell you if you ask for a combination that cannot
    fit rather than silently dropping items.

    Parts are never required by logic. Seven of the 24 only do anything for
    one of the two characters, so a run played entirely as the other one must
    never be stranded behind them.
    """
    display_name = "Parts In Pool"


class ZeroUnlock(DefaultOnToggle):
    """Zero has to be found before you can play as him.

    This is how the base game works - Zero is unlocked partway through, not
    available from the start - and it makes him a real Archipelago item.
    Several locations can be reached either with Zero or with the Blade Armor
    plus a dash Part, so he genuinely opens up the seed.

    Turn this off to start with Zero already available.
    """
    display_name = "Zero Unlock"


class SecretArmorsInPool(Toggle):
    """Add Ultimate Armor and Black Zero to the item pool.

    In the base game these are title-screen button codes rather than things
    you find. With this on they become items; without it, the codes still work
    exactly as they always did, so this is about whether they take up pool
    slots, not about whether you can have them.

    They take filler slots rather than adding locations. Never required by
    logic - each one only benefits a single character.
    """
    display_name = "Secret Armors In Pool"


class TextSkip(DefaultOnToggle):
    """Get dialogue out of the way.

    Mega Man X6 stops constantly: the Navigator calls at fixed points in every
    stage, a briefing plays when you pick a stage, weapons and Nightmare Souls
    are explained the first time you meet them, and each box waits on a button.
    On a first playthrough that is the game. On the tenth trip into a stage for
    one check it is the reason the trip feels long.

    With this on the in-stage Navigator calls, the other in-stage dialogue, the
    stage-select briefings and the Nightmare Souls explanation do not play, the
    alert chime is muted, and cutscene text types at twice the speed.

    Nothing that decides anything is skipped. This only removes dialogue that
    plays AT you - no prompt, menu or choice is answered for you, and the stage
    select itself is untouched.

    Two of the patcher's dialogue options are deliberately absent: the
    Investigator and Special Weapon descriptions. The Tweaks project marks both
    "not solved" and ships no code for them, so neither is skippable yet.

    On by default: a randomized run re-enters the same stages many times, and
    the dialogue is written to be heard once. Turn it off for a first
    playthrough - you will not be able to follow the story at this speed.

    Changes the disc.
    """
    display_name = "Text Skip"


class SkipIntroVideos(DefaultOnToggle):
    """Boot straight to the title screen.

    Skips the opening movie and stops the attract demos from ever starting, so
    a reset lands on the title instead of several minutes of video. The Capcom
    logo is left alone - the Tweaks project replaces the file rather than
    patching code for that one, which is more than this is worth.

    On by default. Purely a convenience for anyone resetting a lot; it affects
    nothing in a run.

    Changes the disc.
    """
    display_name = "Skip Intro Videos"


class ExitStageAnytime(DefaultOnToggle):
    """Let you quit out of a stage you have not cleared yet.

    Normally the pause menu only offers Exit Stage once that stage's boss is
    already down, which is exactly backwards for a randomizer: a run is full of
    trips into a stage for one Reploid you can finally reach, and of entries
    into a stage you cannot finish yet. Without this, leaving means dying on
    purpose or clearing a stage you did not come for.

    The kill record is untouched, so the Nightmare Souls count, the endgame
    gate and story progression all behave exactly as they normally would -
    leaving early simply leaves.

    Changes the disc.
    """
    display_name = "Exit Stage Anytime"


class StageUnlocks(Toggle):
    """Lock the eight investigation sites behind items.

    Normally all eight are open the moment the intro ends. With this on
    exactly ONE of them is open at the start - which one is decided by the
    seed - and each of the others needs its own "<Boss> Access Codes" item,
    shuffled into the multiworld like anything else.

    A locked site still appears on the stage select and the cursor still moves
    onto it; it simply greys out, and pressing confirm does nothing until you
    hold its codes. Nothing else about the screen changes.

    Because a locked stage is unreachable, the endgame additionally requires
    every Access Codes item under this option. That is not belt-and-braces:
    the X5 world shipped this option without that rule and produced seeds
    where a stage's codes were placed behind the endgame those same codes were
    needed to reach.

    Client-side, so it needs no disc change and works on a disc you have
    already patched.
    """
    display_name = "Stage Unlocks"


class EndgameChecks(DefaultOnToggle):
    """Make clearing the Secret Laboratory stages into checks.

    Three extra locations: the Gate opening, and clearing Secret Lab 1 and
    Secret Lab 2. They ride on the game's own progression counter, which is
    monotonic and persistent, so a check cannot be missed by dying, quitting
    or reloading - once it is earned it stays earned.

    Secret Lab 3 is deliberately NOT a check. Clearing it is beating Sigma,
    which is already the goal, and a location firing at the same instant as
    victory adds nothing and risks racing it.

    Only ever adds locations, never items, so it cannot make a seed too full.
    """
    display_name = "Endgame Checks"


class BossHpRandomization(Toggle):
    """Randomize how much health each boss has.

    Every boss gets a new health bar between 32 and 127 - the range the bar
    can actually draw, which is why it stops there rather than at 1 or 255.
    Bosses that scale with your Hunter Rank keep their vanilla step between
    ranks, so a higher rank never accidentally becomes the easier fight.

    Applied to the disc rather than by the client, because X6 keeps the drawn
    bar and the real health in the same byte: patching it means the bar you
    see is always the health the boss has.

    A handful of bosses - Nightmare Mother, Dynamo, and High Max's higher
    ranks - store their health in a form this does not yet handle, and keep
    their vanilla values. Everything else is randomized.
    """
    display_name = "Boss HP Randomization"


class WeaponDamage(Choice):
    """Randomize how much damage YOUR weapons do.

    Each weapon is rolled once and then stays that way for the whole seed, so
    part of a run is finding out which of your weapons turned out to be the
    good one.

    off: unchanged
    weak: 50-90% of normal
    regular: 80-130% of normal
    strong: 120-200% of normal
    chaotic: 25-250% of normal

    A weapon rolls ONCE and the roll covers every form of it, so a charged
    shot can never come out weaker than the plain shot, and X's buster scales
    together across all its charge levels and armors.

    Boss weaknesses are preserved. A boss's weakness is a row in that boss's
    own damage table, and scaling one weapon by the same factor everywhere
    changes how strong the weapon is without flattening which bosses it is
    good against.

    Nothing rolls to zero, and instant kills stay instant kills - a crush or a
    pit is still a crush or a pit. Attacks that do no damage in the first
    place are left alone.

    Worth knowing if you also turn on Boss HP Randomization: the two stack,
    and `weak` weapons against `strong` bosses is a long afternoon.

    Changes the disc.
    """
    display_name = "Weapon Damage"
    option_off = 0
    option_weak = 1
    option_regular = 2
    option_strong = 3
    option_chaotic = 4
    default = 0


class RandomizeOptions(Toggle):
    """Let the seed pick your gameplay options for you.

    Rolls goal, difficulty, and the pool-shaping toggles at generation time.
    Options that only ever ADD checks are left alone, and so is this one.

    If the roll asks for more items than the seed has room for, it turns on
    `reploid_checks` to make room rather than refusing to generate.
    """
    display_name = "Randomize Options"


# Options RandomizeOptions rolls. reploid_checks is deliberately absent - it
# only adds checks, and turning it off would shrink the seed to 29 locations.
# Kept next to the options so the two cannot drift apart.
RANDOMIZED_OPTIONS = (
    "goal", "difficulty", "parts_in_pool", "zero_unlock",
    "secret_armors_in_pool", "text_skip", "stage_unlocks",
    "boss_hp_randomization", "weapon_damage",
)


@dataclass
class MMX6Options(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    exit_stage_anytime: ExitStageAnytime
    text_skip: TextSkip
    skip_intro_videos: SkipIntroVideos
    randomize_options: RandomizeOptions
    goal: Goal
    difficulty: Difficulty
    reploid_checks: ReploidChecks
    endgame_checks: EndgameChecks
    parts_in_pool: PartsInPool
    zero_unlock: ZeroUnlock
    secret_armors_in_pool: SecretArmorsInPool
    stage_unlocks: StageUnlocks
    boss_hp_randomization: BossHpRandomization
    weapon_damage: WeaponDamage
