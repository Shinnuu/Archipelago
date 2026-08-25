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
    the check is collected the moment you reach the Reploid rather than when
    the rescue completes, and what happens to it afterwards is cosmetic.
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
    "secret_armors_in_pool",
)


@dataclass
class MMX6Options(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    randomize_options: RandomizeOptions
    goal: Goal
    difficulty: Difficulty
    reploid_checks: ReploidChecks
    parts_in_pool: PartsInPool
    zero_unlock: ZeroUnlock
    secret_armors_in_pool: SecretArmorsInPool
