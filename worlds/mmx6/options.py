from dataclasses import dataclass

from Options import (Choice, DefaultOnToggle, OptionSet,
                     PerGameCommonOptions, Range, StartInventoryPool, Toggle)

from . import palettes


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
    """Put Zero in the item pool instead of starting with him.

    This is how the base game works - Zero is unlocked partway through, not
    available from the start - and it makes him a real Archipelago item.
    Several locations can be reached either with Zero or with the Blade Armor
    plus a dash Part, so he genuinely opens up the seed.

    Be aware that the GAME can still unlock him without the item. The first
    Another Route boss you fight is the Zero Nightmare, and beating it makes
    Zero playable exactly as it does in vanilla. This option controls the
    Archipelago item, not that fight, so if you want Zero to be a real unlock
    you have to leave Another Routes alone until his item arrives.

    Logic never assumes that shortcut, deliberately: the Zero Nightmare is
    missable - once Gate's Lab opens it is gone for that file - so a seed that
    counted on it could strand. Locations needing Zero stay out of logic until
    you actually receive him.

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
    stage-select briefings and the Nightmare Souls explanation do not play, and
    the alert chime is muted.

    Everything that is LEFT - cutscenes, story beats, anything the removals
    above do not cover - now types out instantly and advances on its own, so
    it plays through without input instead of waiting on a button at every
    box. Cutscene text also types at twice the speed on the path that still
    types.

    Nothing that decides anything is skipped. This only affects dialogue that
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


class ProtectReploids(DefaultOnToggle):
    """Stop Reploids being permanently destroyed.

    In the base game a Reploid you do not reach in time is gone for the rest
    of the playthrough. A Nightmare carries it off, or it is killed in the
    crossfire, and its slot records "death" or "missing" - states that never
    clear. There are 128 Reploids and they are the largest check source in the
    game, so in a multiworld that is items disappearing for good, possibly
    somebody else's progression.

    With this on the three routines that record a Reploid as lost record it as
    untouched instead, so it simply reappears next time you enter the stage
    and you can still go and get it. Rescuing is unchanged.

    Leaving this off does NOT put your checks at risk. The client counts a
    Reploid as checked the moment its slot leaves the untouched state, and
    "destroyed" counts exactly as much as "rescued", so a lost Reploid costs
    you the rescue and never the check. What this option changes is whether
    you get to go back for it.

    On by default: a randomized run re-enters stages many times, and losing a
    Reploid you meant to collect is pure attrition rather than a decision.

    Changes the disc.
    """
    display_name = "Protect Reploids"


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


class DisabledNightmareEffects(OptionSet):
    """Switch off individual Nightmare Effects.

    List the ones you do not want, in any combination. An empty list is
    vanilla and leaves the disc byte-for-byte unchanged.

    Valid names: Bug, Ice, Fire, Iron, Cube, Rain, Mirror, Dark - or **all**
    on its own, which is the same as naming every one of the eight. Case does
    not matter, so `fire` and `Fire` both work.

        disabled_nightmare_effects:      disabled_nightmare_effects:
          - Fire                           - all
          - Dark

    Each stage can be afflicted by exactly two of the eight, so disabling one
    does not clear a stage on its own - it leaves the other:

        Amazon Area     Rain, Dark          Central Museum  Iron, Rain
        North Pole      Fire, Mirror        Inami Temple    Mirror, Dark
        Magma Area      Bug, Iron           Laser Institute Bug, Cube
        Recycle Lab     Ice, Cube           Weapon Center   Fire, Iron

    **Turning Fire off puts nothing important behind North Pole's ice wall.**
    That wall only opens while Nightmare Fire is on the stage, and nine
    locations sit behind it - Blizzard Wolfang's Heart Tank, his EX Tank and
    seven of his Reploids. With Fire disabled they are marked excluded, the
    same way `scaravich_no_progression` treats Central Museum, so the fill
    puts only junk there and no seed can ever depend on getting through.

    The patch does also try to hold that wall open, so those nine stay
    collectable - but nothing rests on it. If that part failed you would lose
    the chance to pick up nine junk items and nothing else.

    Two knock-on effects worth knowing, neither of which costs you a check:

    * **Nightmare Souls get much harder to farm.** The Nightmare Virus only
      drops a fresh Orb after a stage has been afflicted, so a stage with no
      effects left stops replenishing them. Nothing in this randomizer needs
      Souls - the endgame opens on your eighth Maverick - but the vanilla
      3000-Soul route to Gate's Lab effectively closes.
    * **The endgame gate does not care either way.** Under `all_mavericks`
      the 3000-Soul opening is already switched off on the disc, so the gate
      never depends on how many Souls you can farm.

    Ice blocks and Nightmare Cubes double as platforms in one spot each, most
    obviously the long jump to Recycle Lab's capsule - but logic already
    requires Blade Armor or Zero there, which is the stronger requirement, so
    turning them off changes nothing a seed depends on.
    """
    display_name = "Disabled Nightmare Effects"

    # Declared casefolded because AP compares casefolded input against
    # valid_keys VERBATIM - so the keys themselves have to be lowercase for
    # valid_keys_casefold to match anything. The upshot for a player is that
    # Fire, fire and FIRE are all accepted, which matters for an option people
    # type by hand.
    ALL = "all"
    EFFECTS = ("Bug", "Ice", "Fire", "Iron", "Cube", "Rain", "Mirror", "Dark")
    valid_keys = (ALL,) + tuple(e.casefold() for e in EFFECTS)
    valid_keys_casefold = True

    @property
    def effects(self) -> set:
        """The effect names this selects, with `all` expanded.

        Everything downstream reads THIS rather than `.value`, so `all` and
        the eight-name list cannot diverge - and a plain `in` test on the
        option would miss `all` entirely, which is the trap this exists to
        close.
        """
        chosen = {v.casefold() for v in self.value}
        if self.ALL in chosen:
            return set(self.EFFECTS)
        return {e for e in self.EFFECTS if e.casefold() in chosen}


class ScaravichNoProgression(Toggle):
    """Put nothing important in Ground Scaravich's stage.

    Central Museum is built out of totem-pole rooms the game picks at random,
    and it picks four of the eight each time you enter. Its Heart Tank and its
    Blade Armor Helmet both sit inside those rooms, and fifteen of its sixteen
    Reploids are behind the exhibits, so finding any particular one of them
    can mean walking the stage again and again hoping for the right roll.

    With this on, every location in that stage is marked excluded: the fill
    puts only junk there, and nothing you need to finish the seed can be
    behind the randomness. The checks still exist and still send - you are
    welcome to go and get them - they are simply never worth re-rolling for.

    The boss clear is excluded too, even though it is not behind the random
    rooms, because "nothing in this stage is worth a second visit" is the
    point of the option. You will still have to beat Scaravich if your goal
    needs all eight Mavericks; his clear just will not be holding anything.

    It also stops the client withholding the Blade Armor Helmet. Normally a
    granted armor part is held back until its own capsule is checked, so that
    setting the bit early cannot make the capsule stop spawning - but here
    that would mean an item earned in someone else's world still waiting on a
    room you may never roll. Nothing important is in the stage under this
    option, so nothing is lost by handing the part straight over.

    Costs 19 of the seed's locations as progression spots with Reploid checks
    on, or 3 without them. That is the trade, and it is a stopgap: pinning the
    room order, or being made to see all eight rooms, would be the real fixes
    and both are much larger.
    """
    display_name = "Nothing Important In Central Museum"


class StartingHp(Range):
    """How much life X and Zero start with. Vanilla is 32.

    1 is one hit from anything. 127 is the most the game can hold - it keeps
    life in seven bits - so this stops there. All of it plays; only the bar's
    drawing has limits, checked live: below 32 the bar shrinks to a stub with
    the character emblem sitting on top of it, and above 64 it stays the
    vanilla 64 size, so 100 and 127 look exactly like 64. The number is real,
    the picture is not.

    Heart Tanks and Life Ups still add on top (see `heart_tank_value`), and
    the total is capped at 127. This is a disc edit: a new save starts at the
    value from its first frame. A save you already have is moved to it by the
    client the next time it connects, in either direction.
    """
    display_name = "Starting Life"
    range_start = 1
    range_end = 127
    default = 32


class HeartTankValue(Range):
    """How much life each Heart Tank or Life Up is worth. Vanilla is 2.

    X6 has 8 Heart Tanks and 8 Life Up Reploids, sixteen upgrades in all,
    which at 2 each is what takes a vanilla run from 32 to 64. One setting
    covers both kinds because the game does not tell them apart.

    0 makes them worth nothing - the check still sends, the gauge does not
    move. The total is capped at 127, the most the game can hold, so a large
    value reaches the top sooner rather than going past it.

    The life gauge is what the seed says it is: starting life plus this much
    per upgrade RECEIVED. Walking over a Heart Tank in your own game is a
    check, and its vanilla +2 is taken back if the item behind it went to
    someone else.

    Weapon energy is untouched - Energy Ups keep their vanilla step.
    """
    display_name = "Life Per Upgrade"
    range_start = 0
    range_end = 64
    default = 2


# ---- Player colours ---------------------------------------------------------
# Cosmetic recolouring of the player sprites. Chosen here like every other
# option and baked into the .apmmx6 when the seed is generated, so they appear
# on the website generator, are validated at generation rather than failing
# quietly at patch time, and land in the spoiler.
#
# They started life as host.yaml-only settings, which is where the X5 feature
# began, and player feedback was consistently "why do I have to edit a file I
# have never opened". host.yaml still works, but only as an OVERRIDE - see
# MMX6Settings and palettes.overrides() for why `vanilla` there cannot mean
# "force vanilla".
_PALETTE_DOC = """Recolour {subject}.

    Cosmetic only - no logic, items or locations change, and two players in the
    same multiworld can pick differently.

    `vanilla` leaves it alone. `random` works as it does on any Archipelago
    option: it is rolled when the seed is generated, so your colour is fixed
    and appears in the spoiler rather than shifting under you. It picks from
    the whole list, so it can land on vanilla.

    Every repainted entry keeps its original brightness and takes only the
    preset's hue and saturation, so shading and outlines survive. Faces and
    skin are never repainted.{extra}

    You do not need a new seed to change your mind: name a colour under
    `mmx6_options` in your own host.yaml and re-patch. Anything named there
    wins over this setting.
    """


def _palette_option(class_name: str, display_name: str, subject: str,
                    extra: str = ""):
    """Build one 20-value Choice: vanilla, random, and the eighteen presets.

    Generated rather than hand-written so the option can never offer a preset
    palettes.py does not have, or miss one it does.
    """
    namespace = {
        "__doc__": _PALETTE_DOC.format(subject=subject, extra=extra),
        "__module__": __name__,
        "display_name": display_name,
        "default": 0,
    }
    for value, key in enumerate(palettes.OPTION_KEYS):
        namespace["option_" + key] = value
    return type(class_name, (Choice,), namespace)


XPalette = _palette_option(
    "XPalette", "X Colour", "X's own armour",
    "\n\n    Mega Man X6 starts you in Falcon Armor, which is NOT covered and"
    "\n    keeps its usual colours, so this shows once you are playing as"
    "\n    plain X or have switched armours.")
ZeroPalette = _palette_option(
    "ZeroPalette", "Zero Colour", "Zero",
    "\n\n    Zero keeps his blond hair and his helmet crystal. Black Zero is"
    "\n    not covered and keeps its usual colours.")
ShadowPalette = _palette_option(
    "ShadowPalette", "Shadow Armor Colour", "the Shadow Armor")
BladePalette = _palette_option(
    "BladePalette", "Blade Armor Colour", "the Blade Armor")
UltimatePalette = _palette_option(
    "UltimatePalette", "Ultimate Armor Colour", "the Ultimate Armor")


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

    The intro-stage boss is deliberately left alone. It is the tutorial,
    fought with a bare starting X before any upgrade exists, and a roll that
    tripled its health made a miserable first impression for nothing.

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
# protect_reploids is absent for a related reason: rolling it off would hand
# the player a run where checks they can see are quietly destroyed as they
# play. That is attrition, not a gamble worth taking.
#
# scaravich_no_progression is absent because it is an ACCESSIBILITY setting,
# not a flavour gamble: someone takes it because they do not want to re-roll a
# stage, and rolling it off would hand them exactly the run they were avoiding.
# Rolling it on is no better - it silently moves 19 locations out of the
# progression pool for a player who never asked.
#
# starting_hp and heart_tank_value are absent because they are the player's own
# difficulty dial. Rolling starting life to 127 does not make a seed
# interesting, and rolling it to 1 is a run nobody asked for.
#
# The palettes are absent because they are cosmetic, and `random` is already
# on every one of them for anyone who wants the dice.
#
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
    protect_reploids: ProtectReploids
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
    disabled_nightmare_effects: DisabledNightmareEffects
    scaravich_no_progression: ScaravichNoProgression
    starting_hp: StartingHp
    heart_tank_value: HeartTankValue
    x_palette: XPalette
    zero_palette: ZeroPalette
    shadow_palette: ShadowPalette
    blade_palette: BladePalette
    ultimate_palette: UltimatePalette
