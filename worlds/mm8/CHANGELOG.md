# Mega Man 8 apworld — changelog

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
- Capacity is checked in `generate_early`.
