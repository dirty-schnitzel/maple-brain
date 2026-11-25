# maplebrain

A MapleStory end-to-end human-emulation project, on MapleStory Classic World (official GMS Classic, launched
2026-10-21). The goal is twofold (the user, 2026-11-21): to create the most realistic software in the world that
automatically plays in a 2D combat game setting, specifically MapleStory; and to assess the viability and
effectiveness of AI models and other software solutions in mimicking human gameplay. The focus is strictly the
software and its performance: the loss of characters, items or play time is secondary.

The current state and the next step are in HANDOFF.md, loaded at the end of this file. Where everything else
lives: the last section.

## Working with the user
- Senior Python test-automation dev (Windows, infra, security QA). Wants evidence - logs, frames, numbers - and
  test-first fixes. Watches every live run and says what they saw. Their game knowledge fixes designs: ask game
  questions directly.
- Reports are short: what was found, the fix, the command.
- Hard problems run as three kinds of session. A planner (Fable, max) measures and prototypes first, then writes
  PLAN-<topic>.md with a gate per step, stop rules and session prompts: PROPOSED until the user's OK, nothing
  built in maplebrain/. An executor (Opus, or Fable at medium) follows the plan's steps and gates exactly and stops with numbers
  when one fails - no workarounds. A plan manager (Opus, medium) runs beside the executors from the plan's
  review to its last step, so that small things never cost an executor's big context: it explains the plan and
  each step's findings, records the user's answers, writes the step prompts and worktrees, re-checks a step's
  numbers, makes small doc fixes and merges on the user's word (claude_architecture.md section 3, "The plan
  manager"). Redoing a whole pillar: REWORKS.md first.
- Discussing a plan session before it runs, Claude helps the user structure it: the goal in the user's words,
  the requirements (what it must output, how good, how fast), what is decided and what is left to the session,
  the user's game knowledge it needs, and what the user supplies first (footage, answers). Claude asks for a
  missing piece rather than filling it in.
- An executor session whose gates Claude can check itself is started with `/goal <condition>`.
- Do no work that a later step of the plan replaces.

## Git
- Code: work on a side branch; commit and push there without asking once its tests are green. The user merges into
  `dev` and `main`. Never commit to or rewrite `main`. A big change starts on a new branch.
- Docs only (HANDOFF.md, CLAUDE.md, `.claude/rules/`, plans, `docs/`): commit and push straight on `dev`, no
  pytest needed.
- Commit subjects stay under 72 characters; the details go in the body.
- No Claude attribution of any kind in commits or PRs. The commit email stays the GitHub no-reply address set in
  .git/config.
- Other sessions may be working in this folder at the same time. Leave files you did not create alone, and do
  not switch the folder's branch under a running session: a second session that edits code works in its own
  worktree (claude_architecture.md, "Parallel work").

## Environment
- Repo `C:\Users\Yoav\dev\maple-work`: package `maplebrain/`, tests `tests/`, analysis tools `tools/`, run output
  `runs/` (not in git). Python is `.venv\Scripts\python.exe` only (3.12, torch + CUDA; the system python has no
  cv2 / torch). cv2 is the headless build: no windows - write a PNG or a local page.
- The game runs elevated, so the bot's console must too (`whoami /groups | Select-String Mandatory` -> High).
- The game window: windowed, client area exactly 1366x768 (native), display scale 100 %, nothing covering it,
  chat minimized, the minimap open in its usual place. The log must say `1366x768 native (no resize)`. Keys do
  not reach the game while it is unfocused: no background play.
- The recording bank ("the corpus") is `F:\dev\maple-corpus` (`config.CORPUS`) - never on C:. Say "capture" and
  "labels". How it works: the docstring of `tools/data/corpus.py`.
- Client export: `C:\Users\Yoav\dev\cw-data\export\`. v83 reference sources (reading only, nothing of them is
  ever run): `C:\Users\Yoav\dev\v83-ref\`.

## Commands (from the repo root)
```powershell
.venv\Scripts\python -m pytest                                        # no game needed; ends with the "bot speed" line
.venv\Scripts\python -m maplebrain watch runs\watch --seconds 14400   # the Lie Detector siren, no hunt
.venv\Scripts\python -m maplebrain serve runs\v2 [--frames-png | --video]   # stays loaded: F7 hunt, F8 stop, Ctrl+C quit
.venv\Scripts\python -m maplebrain run runs\v2\NAME --seconds 180 [--frames-png]
.venv\Scripts\python -m maplebrain record [--label NAME]              # the user plays -> the bank (F7 / F8); no perception, nothing pressed
.venv\Scripts\python -m maplebrain goto OUT [--to P [X]]              # movement test
.venv\Scripts\python -m maplebrain assets build                       # client export -> assets/mcw (assets/README.md)
.venv\Scripts\python -m maplebrain assets scene                       # -> assets/scene, every map (not in git)
.venv\Scripts\python tools\data\corpus.py list [--stays]              # what the bank holds
.venv\Scripts\python tools\data\unpack.py RUN [frames] [--out DIR]    # PNG files out of a video
.venv\Scripts\python tools\perf\bench.py [--baseline]                 # tick speed against the baseline
.venv\Scripts\python tools\perc\replay\gate.py [--quick]              # the perception gate: the same tracks before / after
```
A hunt writes `<out>\<date_time>_<n>\`: log.txt, ticks.jsonl, frames. Analysis tools: `tools/combat/probe/README.md`,
`tools/perc/replay/README.md`, `tools/play/`, `tools/nav/live_check.py`.

## Code map (`maplebrain/`)
| Where | What |
|---|---|
| `config.py` | every threshold, timing and key: `Keys`, `Combat`, `Perception`, `Nav`, `Humanize`, `CORPUS` |
| `capture.py`, `keyboard.py`, `humanize.py`, `runtime/window.py` | the screen grab (dxcam, mss fallback), SendInput + the focus guard, randomised timing, the game window |
| `scene.py`, `perception/` | the scene model + scene camera; `perceiver.py` frame -> Observation; `vote.py` + `fit.py` the mobs; `world.py` the tracker; `drops.py` (in shadow); `facts.py` FrameFacts; `selfpos.py`, `tags.py`, `hud.py`, `liedetector.py`; `../cover.py` |
| `nav/` | `navmap.py` platforms / ropes / routes; `identify.py` which map; `localize.py` the minimap window + our place; `selfstate.py`; `sim.py` |
| `brain/` | `brain_v2.py` wires the parts in `v2/` (reflexes, ledger, scene, breaks, targeting, combat, trips); `v3/` (model, planner, goals, tasks); `reach.py`, `moves.py`, `travel.py` |
| `runtime/` | `runner.py` (run / serve / watch), `hunt_v2.py` (the hunt loop), `keys.py` KeyDriver, `record.py` + `video.py` + `session.py` (the recorder), `recorder.py`, `keylog.py`, `marks.py`, `exp_meter.py`, `goto.py` |
| `gamedata.py`, `livemap.py` | `assets build`; the console map |

## Measuring
- Tests (the user, 2026-11-23): run only the tests of the area changed when that is possible
  (`pytest tests/test_<area>.py`). The whole suite only when there is a real risk: a change to code many parts
  use (config.py, perception, the scene model, the brain, the hunt loop), or one whose reach is unclear. A tool
  or skill change runs its own tests alone.
- Every pytest run ends with a `bot speed` line: report it after any perception or brain change and say whether
  it moved. It depends on the machine (the power plan, the game in front, another session computing): when it is
  far off, A/B with a WIP commit or a worktree, then re-run pinned to the performance cores. Re-baseline
  (`bench.py --baseline`) only for a deliberate speed change, in the same commit. One GPU job at a time while a
  speed number is being measured. Measure it where `assets/scene` exists (the main folder, or a worktree with it
  linked in): without it the bench skips the scene model and the fit, and shows ~3.5-3.7 ms a tick, meaningless.
- A live run shows that a change works; replays of recorded footage decide whether it is better.
- Footage (the user, 2026-11-24): reuse the bank's captures when they serve - a new kept replay on today's build
  goes into its own folder, never over the one a plan's numbers were measured on. When new footage is needed or
  clearly better, ask for it: the user records it easily (say what to record, the label and the actions).
- To prove a test catches a bug: revert the fix, see the test fail, restore.

## Editing gotchas
- Line endings are mixed (CRLF and LF, sometimes inside one file; HISTORY.md is CRLF): never `sed -i`. Use the
  Edit tool or Python on bytes, and check `git diff --numstat` after a bulk edit. No string-patch scripts on code.
- Windows' default encoding is cp1252: always `encoding="utf-8"`.
- Every game key and hotkey lives once, in `Keys` (config.py); thresholds and timings live in config too.
- A file edited and restored within the same second leaves a stale .pyc: delete `__pycache__` after such tricks.
- Tests import helpers from each other by module name (`from test_brain_v2 import ...`), not relatively. Don't
  put `tools/` first on sys.path.
- Run Python on downloaded or untrusted files with `-I`. Never run scripts from other bot repositories.

## Where things live
| What | Where | Loaded |
|---|---|---|
| Rules that stay true | CLAUDE.md (this file, under 200 lines) | every session |
| Rules for one area | `.claude/rules/*.md` | when that area's files are touched |
| The current state and the next step | HANDOFF.md (under 150 lines) | every session (imported below) |
| A plan and its progress | PLAN-<topic>.md | when working on it |
| A prompt for a session that has no plan | `docs/prompts/` | when run |
| The game's rules: our footage > meowdb's Classic World guides > v83 code | `docs/game_rules.md`; what meowdb says: `docs/meowdb.md` | on demand |
| How a tool works | its docstring or README | on demand |
| Finished work, old numbers, old decisions | HISTORY.md | grep it; never read it whole |
| How this layout is meant to work | claude_architecture.md | on demand |

**Ending a session: use the `handoff` skill** (also when the user says "update handoff"). **Raw run logs, tick
records and frames go to the `run-analyst` agent**, not into the main conversation.

@HANDOFF.md
