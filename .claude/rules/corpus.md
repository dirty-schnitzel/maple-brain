---
paths:
  - "tools/data/**"
  - "tools/perc/frames.py"
  - "maplebrain/runtime/record.py"
  - "maplebrain/runtime/video.py"
  - "maplebrain/runtime/session.py"
---
# The recording bank ("the corpus"): standing rules

How it works is written once, at the top of `tools/data/corpus.py` (the same text is README.txt in the bank).
What to do when new recordings arrive: the `corpus-check` skill.

- **One bank for everything** (the user, 2026-11-18): this is the way data is collected from now on - for
  validating perception, for the live map and tracking, later for AI training. Footage replaces gated checks
  wherever a check only reads the screen; what depends on the bot's own actions stays a live run.
- **It lives at `F:\dev\maple-corpus`** (`config.CORPUS`), never on C:. It stays lean: nothing redundant is
  kept. Sound is not recorded.
- **Words:** "capture" (one stay on one map) and "labels" (words on a capture; farming / traveling are labels,
  not modes - no tool behaves differently for one).
- **Ids for tools, names for people:** a capture's permanent id is `SESSION#K`; by-eye labels hang on the id and
  frame numbers. A capture is filed once, under its map; a use is a list pointing at captures by id, never a copy.
- **Hold-out maps** are opened only with `--holdout`, for milestones - never for tuning, or they stop being an
  honest number. New thresholds and designs are tuned on the dev group only.
- **Human play for training is recorded with `record` only**: with perception running (`serve --observe`) the
  key times are delayed.
- **Never touch a recording that is being written or filed**, never stop `record`; an original leaves
  `incoming\` only after its captures were read back identical.
- A new mob type, background family or failure seen live -> a recording of it joins the bank.
