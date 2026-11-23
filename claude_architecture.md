# How this project works with Claude Code

Decided with the user on 2026-11-21, after a review of the repo and of 117 past sessions. This file is the plan
and its state: come back to it to see what was decided, what is built, what is still to do, and how to tell
whether it works. Built on branch `claude-arch` (off `rules`) and merged into `dev` on 2026-11-21.

## 1. Why

One file, HANDOFF.md, carried four kinds of content - rules that stay true, the current state, how-to procedures
and finished work - and nothing ever left it. Measured before the change (`tools/claude/session_stats.py`):

| What | Before (2026-11-01 .. 11-20) |
|---|---|
| HANDOFF.md | 2,578 lines, 261 KB (54 KB on 11-09); too big for one read, so each session read slices of it |
| Sessions that opened with "read handoff" | 87 of 117; about 50 requests for a handoff update or a next-session prompt |
| A session's context at its 10th step (after the read-in) | 63k tokens at the median, 120-150k when a session tried to read the whole handoff |
| Context sent per step | 216k tokens on average; 48 % of all steps ran above 200k |
| Share of all tokens that is context above 200k | 26 %; the largest sixth of the sessions holds 59 % of all tokens |
| Subagents / skills used | 1 / 2 times in about 22,000 steps |

"Context" is everything a session has read and said so far; every step re-sends all of it. So what a session
reads at its start is paid again on each of its several hundred steps.

## 2. The layout: content is filed by how long it stays true

| Content | File | Loaded | Kept healthy by |
|---|---|---|---|
| Always true: the goal, how to work with the user, safety rules, git, environment, commands, code map, measuring, gotchas | `CLAUDE.md` | every session; put back after a compaction | under 200 lines; a rule enters only on the user's word |
| True for one area of the code | `.claude/rules/{brain,perception,nav,corpus,gamedata}.md` | when a file of that area is read or edited (the `paths:` line) | thin: the user's rules + pointers to the code's own docs, no architecture descriptions |
| True now and next: START HERE, the order of sessions, what the user decided, open items, branches | `HANDOFF.md` | every session (`@HANDOFF.md` in CLAUDE.md) | under 150 lines; rewritten, never appended to, by the `handoff` skill |
| A plan and its progress | `PLAN-<topic>.md` | when working on it | results and gate numbers go here, not into HANDOFF.md |
| A prompt for a session that has no plan file | `docs/prompts/<name>.md` | when run ("run docs/prompts/x.md") | deleted when its session is done |
| The game's rules (v83) | `docs/game_rules.md` | on demand | - |
| How a tool works | its docstring / README | on demand | - |
| Finished work, old numbers, replaced decisions | `HISTORY.md` | grep only | things are moved in word for word, at the end; nothing is deleted |
| How to do a recurring job | `.claude/skills/<name>/SKILL.md` | only when used | - |
| How Claude should work with the user; ideas for later | Claude's memory (outside the repo, this machine only) | its index every session | section 6 |

What changed on 2026-11-21: the old HANDOFF.md went into HISTORY.md byte for byte (its last block); its START
HERE became the new HANDOFF.md (124 lines); its stable sections became CLAUDE.md (134 lines) and the rules files;
its two pending prompts became `docs/prompts/tracker-before.md` and `tracker-plan.md`; its section on new
recordings became the `corpus-check` skill. The name HANDOFF.md was kept (not "STATE.md"): six plan files, code
comments and the user's own words all say "handoff".

## 3. The session loop

1. **Start.** A new session already has CLAUDE.md and HANDOFF.md. No "read handoff". Say what to do: "go on with
   step 2", "run docs/prompts/tracker-before.md", or any free request - plan and executor sessions stay
   free-form.
2. **Work.** Raw run logs, tick records and frames go to the `run-analyst` agent ("use run-analyst on
   runs\v2\<folder>: the bot swung at nothing around 95 s"); its report comes back, the files it read do not.
3. **End.** "update handoff" (or `/handoff what the next session should do`) runs the `handoff` skill: pytest and
   the bot-speed line if code changed, HANDOFF.md rewritten, finished work moved to HISTORY.md, the plan's status
   updated, commit and push on the side branch, and a ten-line summary with the one line to type next.
4. `/clear`, or a new terminal, and back to 1.

## 4. What was built, what was decided against

| Piece | State | Note |
|---|---|---|
| `handoff` skill | built | the step that keeps HANDOFF.md small; Claude may also start it itself at the end of a session |
| `run-analyst` agent (`.claude/agents/`) | built | Opus, high effort, read-only on code and runs; reports at most ~60 lines with times, numbers, commands, frame paths |
| `corpus-check` skill | built (optional) | the existing "more recordings" procedure needed a home; delete the folder to undo |
| `tools/claude/session_stats.py` | built (optional) | reprints the numbers of section 1 for any date range |
| `.claude/settings.json` | built | one setting: a new worktree starts from the current branch, not from `main` (section 7) |
| `execute` / `plan-rework` skills | **decided against** (the user, 2026-11-21) | plan and executor sessions stay flexible. Nothing is lost: what such a skill would have added - the standing rules, the state, the wrap-up - now comes from CLAUDE.md, HANDOFF.md and the `handoff` skill |
| Hooks | **none** (the user, 2026-11-21) | the three proposed (block stopping `watch`, block `sed -i`, block commits on `main`) were declined. Reconsider when a written rule keeps being broken: a hook is a script Claude Code runs itself, so it can enforce what text only advises |
| `live-test`, `assets-update` skills | not built | optional; build one when its procedure is next retyped |

Decided by the user on 2026-11-21 (both are in CLAUDE.md): commit subjects under 72 characters with the details
in the body (they ran to 1,300 characters, and the last five are loaded into every session); `/goal <condition>`
for executor sessions whose gates Claude can check itself.

## 5. Models, effort and context

- **The model is chosen when a session starts and not changed in it.** A switch re-sends the whole conversation
  uncached (one switch on 2026-11-16 happened at 349k tokens). Planning: Fable. Executing: Opus.
- **Effort can change mid-session** on Opus 5.5 and Fable 5.2: their cache survives it.
- **A side question** that should not stay in the conversation: `/btw <question>`.
- **A dead end:** `/rewind`, then "Summarize from here" - the rest of the conversation stays as it is.
- **A natural break in a long session:** `/compact <what to keep>`. CLAUDE.md and HANDOFF.md are put back from
  disk afterwards, so the state survives; before 2026-11-21 it would not have.
- **To do once the new layout is merged and has worked for a few sessions:** `/autocompact 300k` (a safety net
  for sessions that run long), and `/context` + `/skill-doctor` once (an empty session grew from 36k to 51k
  tokens during November; part of it is claude.ai skills this project never uses).

## 6. Memory: to clean up after the merge

Claude's memory is 57 small files outside the repo, with an index loaded into every session. It grew into a
second copy of the project's rules, some of them superseded (its index still says "attack = HOLD key" on one
line and "the hold is dropped" on another). After the split:

- **Repo rules now live in CLAUDE.md and `.claude/rules/`**, versioned with the code. Their memory twins can go:
  no fixed timings, no back-and-forth, held key / facing / attack per press, keys in config, attack logic in
  code, no sed on CRLF, the venv, commit and attribution rules, bot speed and the pinned bench, by-eye labels,
  kill-before-test, scripted input, the Lie Detector's standing, drops are private, EXP by damage, client data
  export, chat minimized, graphics settings, minimap window, ladder 778, v83 as the rulebook, the corpus routine.
- **History only** (fold into one line or drop): the v1-era feature decisions, session 8 decisions,
  maplestory.io, brain-v2 from scratch, pet A/B, weak tracks before the rework, the finished plans' notes
  (perception, loot part 1, livemap, data), the parked VM notes (keep one).
- **Stays in memory:** who the user is and how they want Claude to work, the goal and the north star, ideas for
  later (the training app, the CPU mode), the two play modes.

**Not done yet, on purpose:** until this branch is merged into every branch in use, a session on an old branch
has no CLAUDE.md and still needs those memory entries - the safety rules above all. Do it in one short session
after the merge, with a copy of the memory folder made first (it is not in git).

## 7. Parallel work: when, and with what

A second session pays off when all three hold:
1. the two jobs touch different files;
2. at most one of them needs the game, or the user at the keyboard;
3. neither measures speed while the other computes (the bot-speed line moves 1.5-2x with the machine's load).

| Situation | Use | Why |
|---|---|---|
| A question, a review, reading logs: nothing is edited | a second session in the same folder | reading conflicts with nothing |
| A side job inside a session that reads a lot and returns a conclusion | the `run-analyst` agent | its reading never enters the main conversation |
| A second job that edits code or docs while another session works | a worktree = its own folder on its own branch | neither session sees the other's half-done files or branch switches |
| A long offline job nobody needs to watch (a replay over the bank, labelling, a gate run) | a background session: `claude --bg "<prompt>"`, watched in `claude agents` | the terminal stays free; the list shows which session needs an answer |
| Anything that presses keys into the game | never in parallel | one game window, one keyboard focus |

**Starting a worktree.** `claude --worktree viewer` makes `.claude/worktrees/viewer` on branch `worktree-viewer`
and starts the session in it (`.claude/settings.json` makes it start from the current branch). To choose the
branch name and the base yourself: `git worktree add .claude/worktrees/viewer -b viewer dev`, then start `claude`
in that folder. When the work is merged: `git worktree remove .claude/worktrees/viewer`. Memory is shared with
the main folder; the session list is the worktree's own.
**What a worktree lacks here:** `runs\` and `.venv\` are not in git. Use the main folder's Python by its full
path (`C:\Users\Yoav\dev\maple-work\.venv\Scripts\python.exe`); the bank is reached by its own path
(`F:\dev\maple-corpus`); a tool that reads `runs\...` needs a link (`cmd /c mklink /J runs
C:\Users\Yoav\dev\maple-work\runs`) - or the documented setting `worktree.symlinkDirectories: ["runs"]`, not
tried on this machine yet. `assets\scene\` is not in git either: link it the same way, or work on the kept replay.

**Two plans at once** (drawn up 2026-11-23 for moving-scenery's executor beside the tracker plan; the user then
chose to finish moving-scenery first, so one scene build sits under the tracker - a plan that rebuilds data
outside git is best finished before the next one starts). Separate folders keep the code apart; these rules keep the rest apart:
- **HANDOFF.md:** while working, a session writes its progress only to its own PLAN-<topic>.md. HANDOFF is
  changed on `dev` only, by one session at a time, `dev` pulled first - in practice at a session's end, by the
  `handoff` skill.
- **Code both touch** (config.py; an interface such as moving-scenery's "covered by a cloud" fact, read by the
  tracker): after each finished step the user merges that branch into `dev`, and the other branch merges `dev`
  in at once - small conflicts early, not one big one at the end.
- **Speed:** accuracy work runs any time; a speed measurement only while the other session is idle - a session
  asks the user before measuring speed.
- **Rebuilt data that is not in git** (`assets\scene\`, which moving-scenery rebuilds): the other session works
  on frozen data (the kept replay on F:) and re-runs perception only after the rebuild is merged.
- **The game:** one session at a time; a recording only while no hunt runs. The bank is shared - each session
  writes to its own `work\` folder.

**What happened in this project** (the real cases the rule above is drawn from):
- **2026-11-17, parallel work that paid off.** Loot Sessions 1-3 ran in a second folder (`maple-loot`, branch
  `loot`) while PLAN-data Session 1 ran in `maple-work` (branch `data`), partly overnight; both merged the next
  day. The friction was the hand-made folder: links for `runs` and `assets\scene` set up by hand, sessions
  started in `maple-work` and told "work in maple-loot, NOT in maple-work", and "wait maple-loot is a copy of
  the repo?". `claude --worktree loot` is the same thing in one command, with the session inside it.
- **2026-11-16 08:08, parallel work that was lucky.** The capture's window re-check and perception step 2
  started a minute apart in the same folder, on the same branch. Their files did not overlap, so nothing broke;
  either one's pytest run or commit could have picked up the other's half-done edits. The smaller job belonged
  in a worktree.
- **2026-11-17 to 11-21, the cost of sharing a folder.** The tracker plan session was stopped; its experiment
  scripts (`tools/perc/track/`) stayed untracked in the shared folder for four days, and every later prompt had
  to say "leave alone tools/perc/track/ (another session's work)". In a worktree they would have stayed on
  their branch.
- **2026-11-21, this change.** While it was being built, another session finished the rules write-up and
  switched the shared folder from `dev` to `rules`. This work sat in `.claude/worktrees/claude-arch` and was not
  touched by it; in the shared folder the half-written files would have followed the switch.
- **Good next candidates:** `docs/prompts/tracker-before.md` (an hour of GPU, no game, nothing to watch) as a
  background session - while no speed number is being measured and the user is not recording; the viewer
  (PLAN-livemap.md Session 1) in a worktree beside the tracker work.

## 8. Merging

1. Done 2026-11-21: `rules` and `claude-arch` are in `dev` (fast-forward; the user: "merge all").
2. A branch that was made before the split and added a paragraph to the old HANDOFF.md will conflict on that
   file. Keep the new HANDOFF.md and file the paragraph with the `handoff` skill (state -> HANDOFF.md, results
   -> the plan or a report, the rest -> HISTORY.md).
3. Old branches (`main` included) have no CLAUDE.md until they receive this one.

## 9. Checklist

- [x] 0. This file.
- [x] 1. The split: CLAUDE.md, HANDOFF.md, `.claude/rules/`, HISTORY.md, `docs/prompts/`.
- [x] 2. The `handoff` skill and the `run-analyst` agent (+ `corpus-check`, `session_stats.py`).
- [x] Merged into `dev` (2026-11-21, section 8).
- [ ] The first session on the new layout skims CLAUDE.md with the user (HANDOFF.md, START HERE: the user asked
      for it as that session's first directive) and settles the open points listed there.
- [ ] First sessions on the new layout: no "read handoff" at the start; "update handoff" at the end; HANDOFF.md
      still under 150 lines afterwards.
- [ ] First live run: its logs and frames go through `run-analyst`.
- [ ] 6. The memory clean-up (after the merge; a copy of the folder first).
- [ ] 5. `/autocompact 300k`; `/context` and `/skill-doctor` once.
- [ ] After about two weeks: `.venv\Scripts\python tools\claude\session_stats.py --since <merge day>` against
      section 1. Expected to move: a session's 10th step well under 63k tokens, no session opening with "read
      handoff", a lower average context per step, HANDOFF.md under 150 lines. If HANDOFF.md is growing again,
      the `handoff` skill is not being used or needs sharpening - fix that, not the file.
