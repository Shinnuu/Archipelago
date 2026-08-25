# Mega Man X6 apworld — changelog

## 0.0.1 — unreleased scaffold

**Not playable.** Generation and logic only; there is no disc patch and no
game client yet, so a seed produces no patch file.

- World, items, locations, options and reachability rules, following the
  Mega Man X5 world's structure.
- 28 base items into 29 base locations; `reploid_checks` (on by default) adds
  128 Reploid locations and the 16 gauge upgrades they carry.
- All 128 Reploid locations derived by arithmetic from the confirmed stage
  mapping (stage bit N owns Reploids N*16..N*16+15), which four separately
  observed stages fit.
- Capacity is checked in `generate_early`, so an over-full option set is
  refused with a message naming the fix rather than silently dropping items.
- 48 tests, including an exhaustive check of the item/location arithmetic and
  an assertion that the Blade -> Shadow armor dependency stays acyclic.

Corrected while writing this: the research notes gave the Reploid save block
as `0x800CCFA8..0x800CD027`, a 128-byte range for a 64-byte block. It ends at
`0x800CCFE7`; five live observations agree that byte offset = index // 2.
