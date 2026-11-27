# PLAN-mouse-logger - PROPOSED 2026-11-27

Add event-grained mouse logging to the recorder, so captures carry the full human mouse signal: positions as the
mouse itself reports them (125-1000 Hz), button down / up with their own timestamps, and an `inj` flag on events
sent by a program. First use: the Lie Detector solver for the private-server security challenge (session name:
"my friend's server") - mouse-follow and click LDs cannot be learned from the frame-rate sample alone. Longer
term the data is useful for any humanlike motor layer we build.

Scope: the recorder only. **No change to how the bot sends mouse input today** (the bot does not; this plan does
not start it). **No run against Classic World ever uses the new output for play** - recording is passive, as
today; the private-server work lives in a separate project folder.

## What is already there (verified in `runtime/record.py`, `runtime/keylog.py`)
- **`frames.jsonl` per frame:** `mouse` = `(x, y)` from `screen.cursor()` in the frame's pixels, `buttons` from
  `session.buttons()` - which buttons are held at that frame. One row per grabbed frame, ~60 Hz when the loop
  keeps up.
- **`keylog.py`:** `WH_KEYBOARD_LL` on its own thread with its own `GetMessage` loop; writes transitions only
  (auto-repeats dropped) to `keys.jsonl`, focus-guarded, `inj: true` on injected events, `lag` when the hook ran
  more than 5 ms after the event.

## What is missing
1. **Sub-frame positions.** A gaming mouse at 1000 Hz samples ~16 times per frame; those micro-corrections are
   the exact signal a humanness detector grades. The frame-rate sample smooths them away.
2. **Button transitions between frames.** A short click (< 16 ms) can be missed by the per-frame snapshot: the
   button is up on frame N and up on frame N+1, no click visible.
3. **The `inj` flag** on mouse events. Keys already distinguish our own injected events from the player's; mouse
   will too.
4. **Wheel events.** Not needed for LDs but cheap to log once the hook is in place.

## Approach
A `MouseLogger` next to `KeyLogger`, same shape: low-level hook (`WH_MOUSE_LL`) on its own thread with its own
message loop, one line per event to `mouse.jsonl` next to `keys.jsonl`, the same `t = perf_counter() - t0` clock.
Focus-guarded: moves are logged only while the game is the foreground window, button-ups of a button recorded
down are always logged (symmetric to keylog's rule). Global-screen coordinates from the hook are converted to
the game-window's client pixels before writing (so the data is window-position-independent, and comparable to
the per-frame `cursor()` already in `frames.jsonl`).

**`mouse.jsonl` format** (one JSON object per line):
```
{"t": 12.345, "x": 683, "y": 384}                       # a move, in game-window pixels (0..1366, 0..768)
{"t": 12.350, "btn": "left", "down": true}              # a button transition; btn in left/right/middle/back/forward
{"t": 12.351, "wheel": 120}                             # wheel notches (positive = up); cheap, always logged
{"t": 12.350, "btn": "left", "down": true, "inj": true} # sent by a program (LLMHF_INJECTED)
{"t": 12.360, "lag": 8}                                 # optional, on an event: hook ran 8 ms after the mouse event
```
Moves are **de-duplicated**: two identical (x, y) in a row collapse to one (the hook fires on every poll even when
the position did not change). Out-of-window moves are dropped (negative or >= 1366 / 768) - that part of the path
is not useful and the player often moves off-window between actions.

## Steps and gates

| # | What | Gate | Session |
|---|---|---|---|
| 1 | **Measure** the mouse event rate from the user's actual mouse (prototype: a 60 s script that attaches `WH_MOUSE_LL` and counts move events, bin their inter-arrival times) | Report the median rate and p99 inter-arrival; both over several minutes in the game window and in a browser. **Stop if the rate is < 125 Hz** on the game window (would mean the hook is losing events) | Executor (Opus, low), own worktree, no code in `maplebrain/` yet - prototype under `tools/perc/ld/` |
| 2 | **Prototype the hook**: `WH_MOUSE_LL` on its own thread + GetMessage loop, writes raw events to a temp file, convert screen -> client coords using the `window` helper. 60 s live, chat minimized, game focused | File opens as JSONL; moves are in [0..1366] x [0..768]; a click has a matching down and up; hook latency `lag` p99 < 5 ms; no missed events vs a manual count of 10 deliberate clicks | Same executor (Opus, low), same worktree |
| 3 | **Build `MouseLogger`** in `maplebrain/runtime/mouselog.py`, mirroring `KeyLogger`'s shape (start / stop, own thread, own message loop, error field, lag_max). Unit test by feeding a synthetic event stream through `MouseState.feed`-style logic: button symmetry, de-dup, focus guard, `inj` flag | `pytest tests/test_mouselog.py` green; code structure matches `keylog.py` (same methods, same lifetime); no dependency on the game window being open for the test | Executor (Opus, medium), branch `mouse-logger` off `dev` |
| 4 | **Wire into `record_one`:** start the mouse logger beside the key logger; close it in the `finally`; add a one-line summary in `log.txt` ("mouse: N events recorded, hook lag max M ms"); session.json gets a `mouse_log: true` fact | A fresh `python -m maplebrain record` (5-10 s, chat minimized) writes a `mouse.jsonl` with moves and the clicks the user made; `log.txt` shows the counts; `frames.jsonl` is unchanged | Same executor, same branch |
| 5 | **Validate on a real Lie Detector:** record a mouse-follow LD (the ones we need for the challenge; e.g. a "fading figure" like `lie/2026-11-18_233550_The Cave of Evil Eye I_0m27s_ld1`). A tool `tools/perc/ld/plot_mouse.py` plots the cursor path over the mini-game frames (a sheet of 3 x 3 with path overlaid) | The plot shows a continuous path during the follow phase; no gap > 50 ms while the game stays focused; the per-frame `cursor()` from `frames.jsonl` falls on the path (positions agree within 1 px after accounting for frame time) | Executor (Opus, medium), same branch; user records the LD live |
| 6 | **Filing + corpus check:** `tools/data/corpus.py add` keeps `mouse.jsonl` in the filed capture; its presence and byte count are shown by `corpus.py list --stays`; backward compat for older captures (mouse.jsonl absent is fine). Update the `corpus-check` skill doc only after the user sees step 5's plot | Fresh capture ends up in `maps/.../*_mouse` suffix in its folder name if we decide to tag (optional - user's call); older captures still list without error | Executor (Opus, low), same branch |

## Stop rules
1. **Hook latency** p99 > 15 ms during a live LD run (step 5) - stop, redesign. The hook sits on the OS input
   path, so a slow hook delays the player's own mouse to the game.
2. **Event drops** - if the measured rate in step 1 is well under the mouse's advertised polling rate (e.g. a
   1000 Hz mouse reporting < 500 Hz through the hook) and we cannot explain the gap, stop.
3. **`frames.jsonl` disagrees with `mouse.jsonl`** on cursor position beyond 1 px (after matching timestamps),
   stop: one of the two paths is wrong.
4. **An existing test breaks** - stop, read the test and the change, fix without a workaround.
5. **The hook takes any input that was not aimed at the game window** (e.g. mouse moves while another window is
   focused and the player is in a browser) - stop, the focus guard is broken.

## Questions, answered by the user 2026-11-28
1. **Where to run the private-server bot from?** The user said "a different PC". The mouse logger runs on the
   Classic World PC (recording only); the solver / replayer runs on the other PC. The plan does not build the
   solver yet. **Answer: Windows 11, no Python installed** - the solver plan must ship something that runs
   there without a Python install (a frozen executable, or Python installed as a step of that plan).
2. **Button naming for the side buttons:** **Answer: `btn: "back"` (XBUTTON1) and `btn: "forward"`
   (XBUTTON2)**, no special meaning. Step 2's gate checks the mapping with one press of each.
3. **Wheel:** **Answer: log it.**
4. **The log's `inj` flag:** **Answer: label only** (as keys do); the recorder never refuses to run.

## What this plan does NOT do
- Does not build the Lie Detector solver. That is a separate plan (likely PLAN-ld-solver.md) once the data is in.
- Does not change how the bot sends mouse input. Today it doesn't send any; this stays true.
- Does not touch Classic World policy. Recording is passive and allowed; the private-server bot is a separate
  project folder that never connects to Classic World.
- Does not rename `keys.jsonl` into `inputs.jsonl` or similar. A new file keeps diffs small and older tooling
  intact.

## Footage asked of the user
- Step 1: just play normally for 60 s (chat minimized) - the prototype measures the mouse event rate from the
  hook; nothing is kept.
- Step 5: one mouse-follow Lie Detector (the kind of `lie/2026-11-18_233550_...`), caught live with the recorder
  while this plan's build is on the branch. Any map; chat minimized; the LD happens on its own. We also want
  the click-and-find kind (gold title, "click its number") once this one works - same recording shape.

## Status
PROPOSED. Nothing built yet. The four questions are answered (2026-11-28). Awaiting the user's OK on the
approach, the format and the step order.
