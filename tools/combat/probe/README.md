# combat probes (2026-11-07/08): quick analysis scripts, run from the repo root

Written while chasing air swings / extra swings after kills on Ant Tunnel IV. Rough on purpose; see HANDOFF.md
"START HERE: attack per press" for what they found.

| script | usage | what |
|---|---|---|
| after.py | `after.py RUN_DIR` | death of the mob we fought -> attack key up (median/p90), per kill |
| turning.py | `turning.py RUN_DIR [...]` | mob close behind -> turn latency; what the bot was doing; hit from behind -> turn |
| human.py | `human.py runs/play/RUN` | OLD (attack key `space` hardcoded, counts presses): use human_swings.py |
| bot_presses.py | `bot_presses.py RUN_DIR [N]` | brain v2 per-press runs: each press aimed at a solid / stale / no mob, presses <= 1 s after a death in front, gap after the swing vs the user; marks the N worst -> marked_presses.png |
| human_swings.py | `human_swings.py runs/play/RUN [SWING_S]` | the user's play by SWINGS (a key-down starts one if none is going on; 0.90 s polearm, 0.80 spear): clean kills, death timing, when the mashing stops, swing rhythm |
| human_turn.py | `human_turn.py runs/play/RUN` | the user's turn latency to a mob close behind |
| presses.py | `presses.py runs/play/RUN ...` | the user's attack press length / gaps (keys.jsonl) |
| stale.py | import `analyse(run)` | attack-key time split: a mob seen well <= 0.5 s ago in reach / only stale tracks / nothing |
| mark.py | `mark.py RUN_DIR [N]` | marks the N worst "attacking nothing" frames (boxes, scores, reach, target) -> RUN_DIR/marked_*.png |
| sheet.py | `sheet.py RUN_DIR T0 T1 STEP OUT.png` | contact sheet of frames around us (needs `--frames`) |
| tl.py | `tl.py RUN_DIR T0 T1 [EVERY]` | tick timeline: mode, weapon, footwork, keys, mobs near us |
| lost.py | (edit the run path) | re-runs the GPU detector where the tracker lost a proven mob near us |
| tracks.py | `tracks.py RUN_NAME` | per-track peak score: weak (never >= 0.8) vs strong tracks, time near us |
| swing_live.py | `swing_live.py runs/probe/NAME` (LIVE, elevated, quiet spot) | ~100 s of scripted attack / arrow presses, a 60 fps crop around us: single, very short, double taps, a hold, direction keys mid-swing |
| swing_read.py | `swing_read.py runs/probe/NAME [--sheets]` | our pose per frame (stand R/L, acting + facing, pose changes) -> per-trial timelines: swing length, double tap queued or not, turn mid-swing dropped or applied |

Paths: some default to `runs/v2` (a `run` written straight into runs/v2) - pass the run folder.
