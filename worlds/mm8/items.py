from typing import NamedTuple

from BaseClasses import Item, ItemClassification

from . import names

# Mega Man 8 item/location id namespace. X5 owns 5450000, X6 5460000.
BASE_ID = 5480000


class MM8Item(Item):
    game = "Mega Man 8"


class ItemData(NamedTuple):
    code: int | None
    classification: ItemClassification
    count: int = 1  # copies in the base pool; option-driven items are added in create_items


# Ids are append-only - the datapackage is a contract. Blocks are laid out so
# the client can turn an id back into a game address with arithmetic:
#   +1..+9    weapon-array SLOT (Mega Ball 1, the eight boss weapons 2..9)
#   +20..+23  Rush adapter, offset from 0x8016D300
#   +31..+47  Lab part, BASE + 30 + the game's part id (1..17)
#   +50       bolts (one bundle; its size is a slot_data option)
#   +60..     filler
item_table: dict[str, ItemData] = {
    # Mega Ball and the eight weapons are progression: the bolt guide gates
    # bolts on seven of them (every one but Ice Wave and Water Balloon), and
    # the Wily entrance asks for all eight (see set_rules).
    **{name: ItemData(BASE_ID + slot, ItemClassification.progression)
       for name, slot in names.WEAPON_SLOT.items()},

    # Rush Bike reaches a Clown Man bolt; the other three reach nothing the
    # guide names.
    **{name: ItemData(BASE_ID + 20 + i,
                      ItemClassification.progression if name == names.RUSH_BIKE
                      else ItemClassification.useful)
       for i, name in enumerate(names.RUSH)},

    # Parts are never required: nothing in the bolt guide needs one. With the
    # shop randomized they have to live somewhere, so all 17 are items.
    **{name: ItemData(BASE_ID + 30 + names.PART_ID[name], ItemClassification.useful)
       for name in names.PARTS},

    # Bolts fund the shop, and the shop's locations are gated on them, so a
    # bundle is progression. Count 0 here: how many is decided by options.
    names.BOLTS: ItemData(BASE_ID + 50, ItemClassification.progression_skip_balancing, 0),

    **{name: ItemData(BASE_ID + 60 + i, ItemClassification.filler, 0)
       for i, name in enumerate(names.FILLER)},
}

event_table: dict[str, ItemData] = {
    names.VICTORY: ItemData(None, ItemClassification.progression),
    names.DUO_CLEARED: ItemData(None, ItemClassification.progression),
    **{names.beaten(b): ItemData(None, ItemClassification.progression)
       for b in names.ROBOT_MASTERS},
}

item_groups = {
    "Weapons": set(names.WEAPONS),
    "Rush": set(names.RUSH),
    "Parts": set(names.PARTS),
    "Filler": set(names.FILLER),
}
