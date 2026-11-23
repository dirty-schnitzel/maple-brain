---
name: draw-map
description: Draw a map's platform graph (navmap) as an abstract directed graph picture - nodes = platforms, edges = moves with their cost in seconds. Use when the user says "draw <map>", "draw the graph of <map>", "show the map as a graph", optionally with a number of platforms ("only 10 platforms"), edge groups to hide ("hide drops", "without jumps"), as 8-bit art ("8bit", "8-bit", "pixel art"), or for the session banner ("add it to the banner", "show it at session start").
---
# Draw a map as a platform graph

The tool is `tools/nav/map_graph.py` (its docstring says how the graph is made). Run from the repo root:

```powershell
.venv\Scripts\python tools\nav\map_graph.py MAP [--platforms N] [--seed S] [--hide GROUPS] [--8bit | --banner] [--out PNG]
```

- `MAP`: a map id or name; a part of a name works when it names one map (several: the tool lists them - ask
  which, or take the exact one the user meant).
- `num_platforms` -> `--platforms N`: keep N platforms, picked arbitrarily (grown from a random platform along
  the edges, so they hang together). Say the seed it printed in the file name; `--seed S` repeats a pick.
- `hide` -> `--hide`, comma separated, from: `drop` (drop downs and walking off an edge), `jump`, `rope_up`,
  `rope_down`, `rope_leap` (a rope, then a jump off it), `walk`. "hide ropes" = `rope_up,rope_down,rope_leap`.
  Hidden groups lose their edges only; the platforms stay.
- `8bit` / "8-bit" / "pixel art" -> `--8bit`: the same pick as one-colour text art (rings = platforms, lines =
  moves, no numbers) instead of the PNG, printed with a caption; the art alone saved as a `.txt`.
- Output: `runs\map_graph\<map id>[_<N>p_s<seed>][_no-<groups>].png` (or `.txt` with `--8bit`; the path is
  printed); `--out` elsewhere.

## The session banner (an option, only when the user asks)
The pipeline: draw the graph (PNG) -> the user picks a drawing -> `--8bit` -> on the user's word, `--banner`.
At each session start the `maple-banner` mod (`~\.claude\mods\maple-banner`, installed for the user) shows one
random picture of `.claude\skills\draw-map\8bit\` under the Claude Code logo, titled `neuromaple · <file name>`.
- `--banner` = `--8bit` saved as `8bit\<short name>.txt`: "Hunting Ground" -> HG, "Construction Site" -> CS,
  "City" dropped, a last Roman numeral -> a digit (`Henesys HG1`, `Kerning CS`, `Ant Tunnel 4`; more in
  `SHORT`), what Windows refuses in a file name dropped. It replaces that map's picture. Use the same
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
