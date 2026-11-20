---
name: handoff
description: Wrap up a session - rewrite HANDOFF.md to the current state, move finished work to HISTORY.md, update the plan's status, commit. Use when the user says "update handoff", "handoff", "wrap up", "I will start a new session", "context is getting big" or asks for "the prompt for the next session", and at the end of an executor or plan session.
argument-hint: "[what the next session should do]"
shell: bash
---
# Handoff: leave the repo so that a fresh session can go on

The user's note for this handoff (may be empty): $ARGUMENTS

## Where the repo stands
- Branch and changes: !`git status --short --branch | head -25 || true`
- Last commits: !`git log -5 --format='%h %ad %<(72,trunc)%s' --date=format:%m-%d || true`
- Sizes (lines): !`wc -l HANDOFF.md CLAUDE.md | head -2 || true`

## The one rule
HANDOFF.md is the current state, and it is loaded into every session through CLAUDE.md. **Rewrite it; never
append to it.** A dated story of what this session did does not belong in it - only what is true now and what
comes next. If it grows past 150 lines, something in it belongs elsewhere.

## Where each thing you learned goes
| What it is | Where it goes |
|---|---|
| True until a decision changes: a rule of the user, the environment, a command | CLAUDE.md; a rule about one area -> `.claude/rules/<area>.md`. The user's words and the date. |
| True now, or next: what is done, what is open, who waits for whom | HANDOFF.md |
| A plan's progress: a step's result, a gate's numbers, an amendment | that PLAN-<topic>.md (its status / result section) |
| A rule of the game | `docs/game_rules.md` |
| How a tool works or is used | its docstring / README |
| Finished work, old numbers, a decision that was replaced | HISTORY.md, at the end, moved word for word |
| How the user wants Claude to work | memory |

## Steps
1. **Check before writing.** If code changed: pytest green, and quote its `bot speed` line (say if it moved).
   Name anything left uncommitted or half done. Never report a gate as passed that was not run.
2. **Sort what is new** by the table. Write a stable rule into CLAUDE.md or a rules file only when the user
   stated it or agreed to it; otherwise put it in HANDOFF.md as proposed.
3. **Rewrite HANDOFF.md in place.** Keep its sections (START HERE with the goal, the order table, what the user
   decided, what the next sessions build on; open items; branches; waiting on the user). Replace what changed.
   Each next step names: what, its branch, the model and effort to run it as, and where its prompt is.
4. **Move what is finished to HISTORY.md**: cut the paragraphs that are no longer current and add them at the
   END of HISTORY.md under `## <date> - <topic> (moved from HANDOFF.md)`, word for word. HISTORY.md is CRLF:
   the Edit tool or Python on bytes, never sed. Nothing is ever deleted from HISTORY.md. When unsure whether
   something is still current, keep it in HANDOFF.md under "Open items".
5. **The next session's prompt.** The next session already has CLAUDE.md and HANDOFF.md in its context, so most
   steps need one line in the order table. A step that needs more gets a file: the plan's "Session prompts"
   section when a PLAN exists, else `docs/prompts/<name>.md` - the goal, what to read beyond the loaded files,
   the branch, what "done" means, the stop rules, what to leave alone. Delete a prompt file once its session is
   done (it stays in git).
6. **Commit and push** (CLAUDE.md, "Git"): on a side branch, without asking; never on `main`. No Claude
   attribution.
7. **Tell the user**, in at most ten lines and in plain words: what is done, with its numbers; what is next and
   as which model and effort; what waits for them; the one line to type in the new session.

## Do not
- Do not copy this session's log into HANDOFF.md, and do not leave "Earlier START HERE" sections in it.
- Do not drop a decision of the user: it moves to CLAUDE.md, a rules file, a plan or HISTORY.md, never away.
- Do not edit another branch's or another session's files to make the state look tidy: name them instead.
