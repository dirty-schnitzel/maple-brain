---
name: draw-map
description: Draw a map's platform graph (navmap) as an abstract directed graph picture - nodes = platforms, edges = moves with their cost in seconds. Use when the user says "draw <map>", "draw the graph of <map>", "show the map as a graph", optionally with a number of platforms ("only 10 platforms"), edge groups to hide ("hide drops", "without jumps"), as 8-bit art ("8bit", "8-bit", "pixel art"), with the platforms where they are on the map ("as on the map", "keep the real places", "map layout"), of N random maps ("10 random maps"), or for the session banner ("add it to the banner", "show it at session start").
---
# Draw a map as a platform graph

The tool is `tools/nav/map_graph.py` (its docstring says how the graph is made). Run from the repo root:

```powershell
.venv\Scripts\python tools\nav\map_graph.py MAP [--platforms N] [--seed S] [--hide GROUPS] [--layout rows|map] [--8bit | --banner] [--out PNG]
.venv\Scripts\python tools
av\map_graph.py --random N [the same options, no --seed / --out]
```

- `MAP`: a map id or name; a part of a name works when it names one map (several: the tool lists them - ask
  which, or take the exact one the user meant).
- `num_platforms` -> `--platforms N`: keep N platforms, picked arbitrarily (grown from a random platform along
  the edges, so they hang together). Say the seed it printed in the file name; `--seed S` repeats a pick.
  `--platforms 4-9` = a random count per map.
- Drops are hidden by default (`--hide drop`); "show drops" / "all moves" -> `--hide none`.
- `hide` -> `--hide`, comma separated (replaces the default), from: `drop` (drop downs and walking off an edge), `jump`, `rope_up`,
  `rope_down`, `rope_leap` (a rope, then a jump off it), `walk`. "hide ropes" = `rope_up,rope_down,rope_leap`.
  Hidden groups lose their edges only; the platforms stay. Plurals work: "hide drops" -> `--hide drops`.
- "N random maps" -> `--random N` in place of MAP: maps with at least 5 platforms (or `--platforms`) and an
  edge left after `--hide`, each with its own seed. With `--8bit` every picture is printed again at the end:
  paste that block. Example: `--random 10 --hide drops --8bit --platforms 5 --layout map`.
- "as on the map" / "real places" -> `--layout map`: each platform at its place on the map, to scale (the same
  height stays level, the order and the distances are kept), a grey bar = its extent; the file ends `_map.png`.
  The default `--layout rows` = rows by height, evenly spaced. `--8bit` follows `--layout` too (the art is then about 40 x 32 pixels).
- `8bit` / "8-bit" / "pixel art" -> `--8bit`: the same pick as one-colour text art (rings = platforms, lines =
  moves, no numbers) instead of the PNG, printed with a caption; the art alone saved as a `.txt`.
- Output: `runs\map_graph\<map id>[_<N>p_s<seed>][_no-<groups>].png` (or `.txt` with `--8bit`; the path is
  printed); `--out` elsewhere.

## The session banner (an option, only when the user asks)
The pipeline: draw the graph (PNG) -> the user picks a drawing -> `--8bit` -> on the user's word, `--banner`.
At each session start the `maple-banner` mod (`~\.claude\mods\maple-banner`, installed for the user) shows one
random picture of `.claude\skills\draw-map\8bit\` under the Claude Code logo, titled `neuromaple · <file name>`.
- The folder today (2026-11-23): 30 random maps, `--random 30 --banner --layout map --platforms 5-9` (drops
  hidden). `--random N --banner` skips a name already drawn in that run.
- `--banner` = `--8bit` saved as `8bit\<short name>.txt`: "Hunting Ground" -> HG, "Construction Site" -> CS,
  "City" dropped, a last Roman numeral -> a digit (`Henesys HG1`, `Kerning CS`, `Ant Tunnel 4`; more in
  `SHORT`), what Windows refuses in a file name dropped. It replaces that map's picture;
  `runs\map_graph\` keeps a copy under the `--8bit` name (with its platforms and seed). Use the same
  `--platforms N --seed S` as the drawing the user liked.
- The folder is in git: commit a new picture like the skill (docs only: straight on `dev`). A checkout
  without the folder shows the Henesys HG1 picture built into the mod.
- To take a map off the banner: delete its file.

## Steps
1. Run it and give the user the printed path, the seed (when `--platforms`) and nothing more. Do NOT open or
   read the picture (the user, 2026-11-23: "no need to look at picture just run the tool"). With `--8bit` or
   `--banner`, also paste the printed art in a code block.
2. Big maps (60+ platforms, e.g. Perion town's stair steps) make a picture too tall to read: suggest
   `--platforms`.
