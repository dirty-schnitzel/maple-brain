---
paths:
  - "maplebrain/perception/**"
  - "maplebrain/scene.py"
  - "maplebrain/cover.py"
  - "maplebrain/capture.py"
  - "tools/perc/**"
  - "tools/loot/**"
---
# Perception and tracking: standing rules

- **One perception:** the scene model (the map drawn from the client files), the scene camera, the difference
  to the frame, the fit of mob sprites over the known scenery, the tracker (`world.py`). No fallback path: a map
  without a clean scene model, or a window that is not native 1366x768, does not start a hunt.
- **The targets** (the user, 2026-11-16): capped at 60 frames a second, as close to 100 % accuracy as possible
  for platforms, mobs and the player, the picture looked at once.
- **The reference is a look by eye.** Detection and tracking are graded against labels made by viewing frames
  (`tools/perc/label_eval.py`, labels beside the run or in the bank's `labels\`), never against another tool of
  the same family.
- **Replays decide.** A change to perception is judged by the same recorded frames before and after
  (`tools/perc/replay/gate.py`, `tools/perc/replay/README.md`); a live run only shows that it works. Reference
  recordings are lossless (PNG or the bank's video): JPEG is useless for colour-exact work.
- **Kills are counted by our last hit.** EXP is shared by damage and by party: never a kill count or a quality
  number.
- **Bot speed:** report the `bot speed` line after every change here. When it looks far off, check the machine
  before the code (CLAUDE.md, "Measuring").
- **The chat is minimized** in play and in every recording: its rectangle shows game world, so it is not masked.
  Footage with an open chat gives see-through ghosts there - ask the user to minimize it.
- **Graphics settings, the standard since 2026-11-21:** small damage numbers, own skill effects 20 %, other
  players' 0 %. The recorder cannot read the game's settings: an older capture is at the normal settings.
- **The tracker is about to be redesigned** (HANDOFF.md): don't tune or extend `world.py`'s timeouts for the
  long term. Drops are part of that redesign; `drops.py` runs in shadow and nothing reads it yet.
- Not explained yet: The Field South of Ellinia - about 20 % of the play area is off the scene model (light
  rays) although the map counts as clean. Pixel counts of "unexplained" there need a paired before / after.
- The plan and its measured experiments: PLAN-perception.md; drops: PLAN-loot.md.
