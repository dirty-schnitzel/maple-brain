# combat probes (2026-11-07/08): quick analysis scripts, run from the repo root

Written while chasing air swings / extra swings after kills on Ant Tunnel IV. Rough on purpose; see HANDOFF.md
"START HERE: attack per press" for what they found.

| script | usage | what |
|---|---|---|
| after.py | `after.py RUN_DIR` | death of the mob we fought -> attack key up (median/p90), per kill |
| turning.py | `turning.py RUN_DIR [...]` | mob close behind -> turn latency; what the bot was doing; hit from behind -> turn |
| human.py | `human.py runs/play/RUN` | the user's kills by last hit: clean (no press at nothing within 1 s) or not; press rhythm |
| human_turn.py | `human_turn.py runs/play/RUN` | the user's turn latency to a mob close behind |
| presses.py | `presses.py runs/play/RUN ...` | the user's attack press length / gaps (keys.jsonl) |
| stale.py | import `analyse(run)` | attack-key time split: a mob seen well <= 0.5 s ago in reach / only stale tracks / nothing |
| mark.py | `mark.py RUN_DIR [N]` | marks the N worst "attacking nothing" frames (boxes, scores, reach, target) -> RUN_DIR/marked_*.png |
| sheet.py | `sheet.py RUN_DIR T0 T1 STEP OUT.png` | contact sheet of frames around us (needs `--frames`) |
| tl.py | `tl.py RUN_DIR T0 T1 [EVERY]` | tick timeline: mode, weapon, footwork, keys, mobs near us |
| lost.py | (edit the run path) | re-runs the GPU detector where the tracker lost a proven mob near us |
| tracks.py | `tracks.py RUN_NAME` | per-track peak score: weak (never >= 0.8) vs strong tracks, time near us |

Paths: some default to `runs/v2` (a `run` written straight into runs/v2) - pass the run folder.
