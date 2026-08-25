# Mega Man X6 apworld — changelog

## 0.0.1 — unreleased scaffold

**Not playable end-to-end.** No disc patch yet, so a seed produces no patch
file - but generation, logic and the client all work.

- World, items, locations, options and reachability rules, following the
  Mega Man X5 world's structure.
- 28 base items into 29 base locations; `reploid_checks` (on by default) adds
  128 Reploid locations and the 16 gauge upgrades they carry.
- All 128 Reploid locations derived by arithmetic from the confirmed stage
  mapping (stage bit N owns Reploids N*16..N*16+15), which four separately
  observed stages fit.
- Capacity is checked in `generate_early`, so an over-full option set is
  refused with a message naming the fix rather than silently dropping items.
- 66 tests, including an exhaustive check of the item/location arithmetic and
  an assertion that the Blade -> Shadow armor dependency stays acyclic.

### BizHawk client

Detects checks and applies received items. Four policies, each deliberate:

- **Weapons are not granted.** `0x800CCF30` is simultaneously the kill record
  and the weapon list, so writing it would fabricate a boss check. Needs the
  disc patch (ship plan A1). Until then weapons come from beating Mavericks.
- **Grants are absolute.** Gauges are computed from the items received and
  written whole, so re-applying after a reconnect is a no-op. Removes X5's
  need for a memcard-persisted counter rather than guarding it.
- **Bits that hide their own pickup are withheld** until their location is
  checked - otherwise an early grant makes the location uncollectable.
- **Gauge record bits are never written**, so detection off `0x800CCF3C/3D/3F`
  can never read an AP grant back as a pickup.

**Known gap, fix before anyone but the author plays:** no seed/slot stamp, so
the client cannot tell this seed's save from another one. Spare-byte candidates
are listed in `client.py`; none is verified.

### Research corrections made while building this

The Reploid array has **two** 64-byte copies: a live one at `0x800CCFA8` written
one nibble per rescue, and a bulk mirror at `0x800CCFE8` that never changed by
fewer than 6 bytes at once. An earlier pass this same day narrowed the notes to
a single block, which was wrong - the 128-byte span in the original notes was
both copies. The client reads the live one.
