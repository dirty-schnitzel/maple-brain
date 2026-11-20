# Session prompt: one replay of the bank, kept, and today's tracker scored on it

- **Run as:** Opus, high effort, a fresh session. Type: `run docs/prompts/tracker-before.md`.
- **When:** next (HANDOFF.md, START HERE, step 2). About an hour of GPU: best while the user is not recording.
- **Branch:** `tracker` (the prompt resets it to `dev` first; that switches the folder's branch for every
  session working in it).
- **Result:** `REPORT-track-before.md` + the kept replay under `F:\dev\maple-corpus\work\`.
- **Written:** 2026-11-21 in the planning session; the text below is unchanged. Where it says "HANDOFF: one
  paragraph", wrap up with the `handoff` skill instead.

```text
You are the executor of the tracker's preparation: one replay of the bank, kept, and today's tracker scored on
it. Read HANDOFF.md's START HERE first. Nothing in maplebrain/ changes in this session: it measures.
Branch `tracker`: `git branch -f tracker dev` first (it has no commits of its own), then check it out.

Why: the tracker is redesigned next, in a plan session. REWORKS.md's rule: the gate exists before the design.
The planner needs (a) perception's per-frame output on the bank's 60-frames-a-second footage, stored, so tracker
prototypes run in seconds without the GPU; (b) which captures perception is sound on; (c) today's tracker scored
against the hindsight truth - the "before" numbers.

The material
- The bank: F:\dev\maple-corpus (`python tools\data\corpus.py list --stays`). Take every capture of the dev group
  recorded at the full rate (n_frames / (minutes * 60) > 45) on a map with a clean scene model, labels farming or
  traveling; not the two `bot` hunts, not the old every-3rd-frame recordings. NEVER the hold-out group (the tools
  refuse it without --holdout: do not pass it). The long one is the design capture: 20261121_000219_2#0 (Line 1
  <Area 1>, 30.6 minutes, the settings the user keeps); 20261120_235747_1#0 is its 4-minute twin.
- tools/perc/track/ (untracked, written by the plan session that was stopped on 2026-11-17): load.py (a run's
  ticks -> the fit's mobs per tick, tracklets), dump.py (per frame everything a tracker could ask: the fit's mobs,
  today's tracks and looks, the patches, and two bitmaps - where the frame shows the expected scene / where a mob
  could show), oracle.py (the hindsight truth: the fit's own mobs linked, then stitched across their unseen
  moments looking both ways in time = "chains"), score.py (a tracker's tracks against the chains: HELD /
  DEAD-LIVE / GHOST / SWITCHES / FOUND), e10_basics.py, e12_why.py. Read each file's docstring. They were written
  for PNG run folders with a ticks.jsonl (dump.py still calls replay.saved_frames, which is gone).

Steps
1. Port tools/perc/track/ to bank captures: a capture's id SESSION#K through tools/perc/frames.py `clip` (as
   tools/perc/replay/run.py does); a `record` capture has no ticks.jsonl - its "ticks" are a replay of every
   frame. Outputs under F:\dev\maple-corpus\work\SESSION#K\track\ (never in the repo, never on C:). Commit the
   folder.
2. The kept replay: the live Perceiver, unchanged, over EVERY frame of each chosen capture (the live rate),
   written once: per frame the camera, our place, the fit's mobs, the looks at today's tracks, today's tracks,
   the drops, the patches, the two bitmaps. Say per capture: frames, seconds of GPU time, GB written. The game
   may be running and a `record` process is loaded: while the user is recording (a folder in
   F:\dev\maple-corpus\incoming), wait.
3. Per capture, automatic (PLAN-data.md section 6 item 1): the share of frames with the scene camera found, the
   share of the known scenery's pixels the scene explains, mobs tracked, the tick's ms. PLAN-data's stop rules
   become a verdict per capture (camera lost on > 1 % of the frames, or < 95 % explained -> "not sound": listed,
   left out of step 4), not a stop of the session.
4. Today's tracker against the chains (score.py), per sound capture and pooled, at the live rate: HELD by gap
   length, DEAD-LIVE, GHOST, SWITCHES, FOUND; e12_why.py's classes of why a chain is lost.
5. The truth's own check, by eye (the reference is your judgment, never a tool's agreement): 40 stitched gaps and
   20 chain ends picked at random over the sound captures, each as a sheet of frames around it - is it the same
   mob across the gap, did it really die / leave / get covered? Report right / wrong / can't tell.
6. REPORT-track-before.md (repo root): the tables of 3-5 in plain words, each term defined in game terms the
   first time; what the kept replay holds and how to load it; anything that surprised you. HANDOFF: one paragraph.

Rules: no change to perception or the tracker, no threshold tuned, nothing fixed - list what you find. Python =
.venv\Scripts\python.exe; long jobs with run_in_background; never stop `record` / `watch`; nothing pressed into
the game; no sed on repo files (CRLF); pytest + the 'bot speed' line before the commit (it must not move: nothing
on the bot's path changed); commit + push `tracker`, no Claude attribution. A step that cannot work as written:
stop that step with the numbers and go on with the others.
```
