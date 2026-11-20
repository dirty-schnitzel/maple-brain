---
paths:
  - "maplebrain/nav/**"
  - "maplebrain/brain/moves.py"
  - "maplebrain/brain/travel.py"
  - "tools/nav/**"
---
# Maps and movement: standing rules

- **The minimap window on screen is the source of truth, not the map's canvas.** The window scrolls on maps
  taller or wider than it (Ant Tunnel IV vertically; Kerning City Construction Site sideways) and is wider than
  the canvas when the map's name is long. Measure the window; never predict it from map.json.
- **Validate a recognition change on recorded frames**, old code against new, on the maps in `runs/` and the
  bank: unit tests and the simulation both passed once while a real map broke.
- **Game rules come from v83 code and our client files** (`docs/game_rules.md`), not from guesses. Our fitted
  movement values stand over v83's constants: Classic World raised the base jump and move speed (the user,
  2026-11-21). Physics.img otherwise equals v83.
- **A ladder or rope stop that looks wrong:** compare the raw `me_map` and `map_pos` with `timings.self` in
  ticks.jsonl before theorising. Known: on Line 1 the name tag on ladder x 778 reads x 788, past the rope
  tolerance; a wrong rope / ground read makes every later decision look like a combat bug.
- No left-right-left-right while moving (`.claude/rules/brain.md`).
