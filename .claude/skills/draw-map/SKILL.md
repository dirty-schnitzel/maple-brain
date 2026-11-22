---
name: draw-map
description: Draw a map's platform graph (navmap) as an abstract directed graph picture - nodes = platforms, edges = moves with their cost in seconds. Use when the user says "draw <map>", "draw the graph of <map>", "show the map as a graph", optionally with a number of platforms ("only 10 platforms") or edge groups to hide ("hide drops", "without jumps").
---
# Draw a map as a platform graph

The tool is `tools/nav/map_graph.py` (its docstring says how the graph is made). Run from the repo root:

```powershell
.venv\Scripts\python tools\nav\map_graph.py MAP [--platforms N] [--seed S] [--hide GROUPS] [--out PNG]
```

- `MAP`: a map id or name; a part of a name works when it names one map (several: the tool lists them - ask
  which, or take the exact one the user meant).
- `num_platforms` -> `--platforms N`: keep N platforms, picked arbitrarily (grown from a random platform along
  the edges, so they hang together). Say the seed it printed in the file name; `--seed S` repeats a pick.
- `hide` -> `--hide`, comma separated, from: `drop` (drop downs and walking off an edge), `jump`, `rope_up`,
  `rope_down`, `rope_leap` (a rope, then a jump off it), `walk`. "hide ropes" = `rope_up,rope_down,rope_leap`.
  Hidden groups lose their edges only; the platforms stay.
- Output: `runs\map_graph\<map id>[_<N>p_s<seed>][_no-<groups>].png` (printed); `--out` elsewhere.

## Steps
1. Run it; look at the PNG yourself (Read) before reporting.
2. Report: the path, platforms shown / reachable, edges, what stands out (one-way links, the hub, platforms left
   out because nothing leads there). Remind once, when a wide floor is in the picture: a cost is counted from
   the MIDDLE of the source platform, so costs out of a wide floor are mostly walking at `Nav.walk_speed`
   (a placeholder, 125 px/s); the bot's routes start from where it stands.
3. Big maps (60+ platforms, e.g. Perion town's stair steps) make a picture too tall to read: suggest
   `--platforms`.
