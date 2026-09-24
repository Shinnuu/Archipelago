from dataclasses import dataclass

from Options import Choice, PerGameCommonOptions, Range, StartInventoryPool


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
    game. Logic only expects you to shop once you could buy EVERYTHING in
    stock - 21 bolts for the nine entries on sale from the start, 40 once Duo
    is beaten - so buying in any order can never strand you. The surplus is
    how much slack you get on top: at 40 the pool holds 60 bolts (twelve
    bundles of 5), so the Lab opens up in logic after 35% and 67% of them.

    The pool has limited room. If the bundles would not fit, generation stops
    and says so rather than silently dropping items - raise the bundle size.
    """
    display_name = "Bolt Surplus"
    range_start = 0
    range_end = 100
    default = 40


@dataclass
class MM8Options(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    goal: Goal
    bolt_bundle_size: BoltBundleSize
    bolt_surplus: BoltSurplus
