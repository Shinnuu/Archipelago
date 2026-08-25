from typing import NamedTuple

from BaseClasses import Item, ItemClassification

from . import names

BASE_ID = 5460000  # Mega Man X6 item/location id namespace (X5 owns 5450000)


class MMX6Item(Item):
    game = "Mega Man X6"


class ItemData(NamedTuple):
    code: int | None
    classification: ItemClassification
    count: int = 1  # copies placed in the pool


# Ids are append-only. A block is reserved per category so a later addition
# never has to renumber an existing one - the datapackage is a contract.
item_table: dict[str, ItemData] = {
    # +0..7  weapons, in STAGES bit order. Progression: several locations are
    # gated on mobility/armor rather than weapons today, but weapon-gated
    # access exists in X6 (charged shots against High Max) and boss weaknesses
    # will use them once the rules are fleshed out.
    **{name: ItemData(BASE_ID + i, ItemClassification.progression)
       for i, name in enumerate(names.WEAPONS)},

    # +10..17  armor parts, in ARMOR_PARTS order (Blade x4, then Shadow x4).
    # Progression, and genuinely so: Shadow Armor is the only way past several
    # spike sections, and Blade Armor's Mach Dash reaches items nothing else
    # does. An armor only functions once all four of its parts are held.
    **{name: ItemData(BASE_ID + 10 + i, ItemClassification.progression)
       for i, name in enumerate(names.ARMOR_PARTS)},

    # +20..25  gauge upgrades and tanks.
    names.HEART_TANK: ItemData(BASE_ID + 20, ItemClassification.useful, 8),
    names.SUB_TANK:   ItemData(BASE_ID + 21, ItemClassification.useful, 2),
    names.W_TANK:     ItemData(BASE_ID + 22, ItemClassification.useful),
    names.EX_TANK:    ItemData(BASE_ID + 23, ItemClassification.useful),
    # Life Up / Energy Up are the upgrades a rescued Reploid carries. Count 0
    # here: they only enter the pool when `reploid_checks` is on, because
    # without those 128 locations the seed has nowhere to put 16 more items.
    # See MMX6World._capacity.
    names.LIFE_UP:    ItemData(BASE_ID + 24, ItemClassification.useful, 0),
    names.ENERGY_UP:  ItemData(BASE_ID + 25, ItemClassification.useful, 0),

    # +30..59  equippable Parts, in PART_BIT (bit) order. Option-gated, so
    # count 0 here. `useful`, never progression - seven of the 24 only work
    # for one character, and requiring any of them could strand a run played
    # entirely as the other one. Same rule as X5's DNA Parts.
    **{name: ItemData(BASE_ID + 30 + i, ItemClassification.useful, 0)
       for i, name in enumerate(names.PARTS)},

    # +60..62  character / secret armor unlocks, all option-gated.
    # Zero is progression whenever he exists: the items guide gates six
    # locations on "Zero, or Blade Armor + a dash Part", so he is a real
    # mobility source. Ultimate Armor and Black Zero are cosmetic-tier power
    # spikes tied to one character each, so `useful` like X5's pair.
    names.ZERO:           ItemData(BASE_ID + 60, ItemClassification.progression, 0),
    names.ULTIMATE_ARMOR: ItemData(BASE_ID + 61, ItemClassification.useful, 0),
    names.BLACK_ZERO:     ItemData(BASE_ID + 62, ItemClassification.useful, 0),

    # +70..74  filler, in names.FILLER order.
    **{name: ItemData(BASE_ID + 70 + i, ItemClassification.filler, 0)
       for i, name in enumerate(names.FILLER)},

    # +80..87 reserved for stage access items, if `stage_unlocks` is ever
    # built for X6. Not defined yet: the client-side lock X5 uses (zeroing the
    # hub's slot -> stage-id table) has no X6 equivalent researched, and
    # shipping an option we cannot enforce in-game is worse than not having it.
}

event_table: dict[str, ItemData] = {
    names.VICTORY: ItemData(None, ItemClassification.progression),
}

item_groups = {
    "Weapons": set(names.WEAPONS),
    "Blade Armor": set(names.BLADE_PARTS),
    "Shadow Armor": set(names.SHADOW_PARTS),
    # Hint/item-link alias.
    "Armor": set(names.ARMOR_PARTS),
    "Tanks": {names.SUB_TANK, names.W_TANK, names.EX_TANK},
    "Parts": set(names.PARTS),
    "Upgrades": {names.HEART_TANK, names.LIFE_UP, names.ENERGY_UP},
    "Filler": set(names.FILLER),
}
