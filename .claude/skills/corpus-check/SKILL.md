---
name: corpus-check
description: Check the user's new recordings and what the recording bank (the corpus) holds. Use when the user says "more recordings", "check the recordings", "I did a few more captures", "I recorded", "file the recordings" or asks what is in the bank.
---
# New recordings: what to check and what to report

(Moved here on 2026-11-21 from HANDOFF.md, "HOW THE USER'S RECORDINGS GET INTO THE BANK"; the method is the
user's, 2026-11-19.)

**The recorder files its own recordings.** The user runs `python -m maplebrain record --label NAME` (F7 start,
F8 stop; chat MINIMIZED - the user's rule since 2026-11-19: the bot plays so, and an open chat hides the lowest
strip of the map). While it records it notices every loading screen (a run of black frames: the game always
shows one between two maps) and starts a new video file there. At F8 it starts `tools/data/corpus.py add` on the
recording in the background: every piece between two loading screens is named with ~3 looks at its minimap and
its files are MOVED into `maps\<map> (<id>)\` (hold-out maps: `holdout\`); class + level go into the manifest; a
Lie Detector the recorder saw is copied into `lie\`. The result is printed in the recorder's terminal and kept in
`F:\dev\maple-corpus\work\filing\<recording>.log` (after filing also `sessions\<recording>\filing.log`).

## Steps
1. `ls F:\dev\maple-corpus\incoming` - a folder still there is either being recorded (never touch it, never
   stop `record`), being filed (`F:\dev\maple-corpus\.filing` exists), or NOT FILED: read
   `work\filing\<folder>.log` for why. `incoming\lie_*.png` = Lie Detectors met while no recording ran: leave.
2. Not filed because a stretch has no map name: `corpus.py add --dry <folder>` draws the frames into
   `work\cuts\<folder>\` - look at them. A map whose minimap is on screen but not named = a gap in the
   recogniser (`nav/identify.py`) to close first, then `corpus.py add <folder>`; a shop / a closed minimap =
   `corpus.py add --unknown <folder>`. `class / level NOT READ` = a new digit or class: add its picture to
   `tools/data/hud_glyphs.json` (`corpus.char_glyphs(frame)` prints it), then `corpus.py char`.
3. Report (CLAUDE.md, "Reports"): the maps, the time on each, the labels, hold-out or not, frames a second / dropped
   (log.txt in `sessions\<recording>\`), the bank's totals (`corpus.py list`).

## Other kinds of recording
A recording made by a recorder started before 2026-11-19 (no pieces), a hunt (`--video`) or an old PNG
recording: `corpus.py add <folder>` cuts it by the minimap - a look every 10 s, halving between two looks that
disagree down to the exact frame - and writes every capture again, read back frame by frame. `add` STOPS at a
stretch without a map name (`--unknown` files it).

## Standing words of the user
- **No by-eye look at cut sheets any more** (2026-11-19: "you don't need to verify again ... if the past cuts
  were OK" - 22 were looked at, all right); `--dry` draws them when one is wanted.
- The bank stays lean (nothing redundant kept); it lives on F:, never C:; say "capture" and "labels".
- More walks are welcome, nothing waits for them (2026-11-21).

The tool is described at the top of `tools/data/corpus.py`; `corpus.py list --stays` = what the bank holds,
`verify [--frames]` = are the files what was filed. Ideas not built: drop preview.mp4 (the slowest part of filing);
count `w` / `e` skill presses for the farming label once they are in `Keys`; add a label to a filed capture.
