# maplebot

Vision-only hunting bot for MapleStory Classic World, built to run **while you watch** (it pauses the moment
the game loses focus, stops and beeps on low HP). It only reads the screen and sends key presses.
Botting is against Nexon's ToS; supervising it doesn't change that.

## Run (elevated: the game is elevated, Windows drops keys from a non-admin process)

```powershell
# from C:\Users\Yoav\dev\maple-work, in an admin terminal
..\auto-maple\.venv\Scripts\python -m maplebot run runs\my_run --seconds 60 --attack space --jump shift
```
Switch into the game within 180 s. Alt-Tab out to pause. Output: `log.txt`, `ticks.jsonl` (every tick's
observation + actions), `frames/` (full-res every 3rd tick).

## Test (no game needed)

```powershell
..\auto-maple\.venv\Scripts\python -m pytest
```

## Layout

| | |
|---|---|
| `maplebot/config.py` | every threshold, zone and timing |
| `maplebot/capture.py`, `keyboard.py` | the only Windows I/O |
| `maplebot/perception/` | frame -> `Observation` (self tag, HUD, mob HP bars, motion look, tracker, mob memory) |
| `maplebot/brain/brain.py` | `Brain.step(Observation) -> [actions]`, no I/O, fake-clock testable |
| `maplebot/runtime/` | live loop, safety, executor, recorder |
| `tests/` | regressions on real frames + behaviour scenarios + loop smoke test |
| `tools/` | the original experiment scripts (history; not used by the package) |

## Adding a regression

Live bug -> find the tick in `ticks.jsonl` / the frame in `frames/` -> copy the frame to `tests/fixtures`
(perception bug) or write the observation sequence in `tests/test_brain.py` (decision bug) -> fix -> green.
