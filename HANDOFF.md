# maplebrain - handoff: the current state

This file is already in your context: CLAUDE.md imports it, so there is no need to read it again. It holds only
what is true NOW and what comes NEXT. The `handoff` skill rewrites it at the end of a session - it is never
appended to. Everything older is in HISTORY.md (grep it; what left this file on 2026-11-21 is its last
blocks). Rules that stay true: CLAUDE.md and .claude/rules/. Plans and their progress: PLAN-*.md.

## START HERE (2026-11-21): the user's OK on PLAN-moving-scenery.md, then its step 1; the tracker plan

**The user's goal (2026-11-19):** "have a great perception / tracking / data model in order to feed that into an
ai to see how many hours of farming on a specific map with a specific class and style are needed to teach it to
farm a map efficiently and humanlike. Then benchmark different models at the same job". **Priorities
(2026-11-20):** "good tracking ready for ML applications, and a simulator that can 1 - show the current state of
the game live just like livemap but with real assets, 2 - take our input and be used to train AI". **Left open by
the user:** a full FSM or a cloned-behaviour AI. It does not change the order below; both get scored in the
simulator once it exists.

### The order from here
| # | Session | Run as | Status | Prompt |
|---|---|---|---|---|
| 1 | The rules write-up -> `docs/game_rules.md` | Opus, high | DONE 2026-11-21, merged into `dev` | - |
| 2 | One replay of the bank, kept, + today's tracker scored on it -> `REPORT-track-before.md` | Opus, high | DONE 2026-11-21, merged into `dev` | - |
| P0 | The moving-scenery plan session -> `PLAN-moving-scenery.md` | Fable, max | DONE 2026-11-21: the plan is filled, **PROPOSED until the user's OK**; its tools are on branch `moving-scenery` | - |
| **P0.1-5** | **The plan's steps 1-5, one executor session each:** 1 the pictures right (the forest maps sound), 2-3 moving backs drawn and followed (40 maps hunt), 4-5 Perion's clouds followed and undone (42 maps hunt). Steps 4-5 need the user's Perion recording | Opus | **NEXT, after the OK**; branch `moving-scenery` | `PLAN-moving-scenery.md`, "Session prompts" |
| 3 | The tracker plan session -> `PLAN-tracker.md`, PROPOSED until the user's OK | Fable, max | after the user has written the tracker's definition and goals into its prompt (Waiting on the user) | `docs/prompts/tracker-plan.md` |
| 4 | The tracker built in shadow beside today's, switched when it matches or beats it. Beside it, at any time: the viewer (PLAN-livemap.md Session 1 - its prompt says "from the current head of `perception`": use `dev`), then the engine's own plan session (the engine outputs the tracker's state description) | Opus | after 3 | PLAN-tracker.md, PLAN-livemap.md |
| 5 | FSM or clone, decided on what both score in the simulator and live | - | open | - |

### Decided by the user
- **v83 is the rulebook (2026-11-20):** "no guessing or measuring v83 client is more than good enough, the server
  behavior hasn't changed that much over the years and certainly would not affect bot behavior - all the concepts
  are the same". Game rules come from v83 code + our client files, never from guesses, and measuring them from
  footage is not a precondition. Sources: HeavenClient (the movement of our character AND of the mobs - the
  client simulates both) and Cosmic (the server's side - respawn, EXP, drops), cloned to
  `C:\Users\Yoav\dev\v83-ref\` (HeavenClient 0daa69d, Cosmic fec53bc; reading only, both AGPL-3.0).
- **Graphics settings (2026-11-21): small damage numbers, own skill effects 20 %, other players' 0 %.** The
  standard from now on; the tracker is designed on footage at these settings. Captures at them: the two Line 1
  captures below (no label says so; checked by eye against a normal-settings capture: no burst over our character
  at `q`, smaller digits) and `20261119_210307_1#0` (label `new-settings`). Everything older = normal settings.
- **Not wanted now:** the two bot hunts for PLAN-data gate (b)'s tick cost; loot scene 3 of PLAN-loot.md section
  13 (windows over drops: "inventory will come much later down the line and is not a part of tracking").
- **Drops in the tracker:** "expect the loot to be there for 2 mins (max loot decay time) and if it disappears
  then update the model" - a drop stays in the model from its first resting sighting until its place is seen
  without it, or until it is 130 s old when we never look there again.
- **Movement and server data (2026-11-21):** Classic World raised the base jump and move speed, so our fitted
  movement values stand over v83's constants (`Nav.jump_vx` 155 etc.); the swing length stays
  `(10 + attackSpeed) / 16` for now, to be recalculated with the tracker; **no further work on server data
  (Cosmic: respawn, aggro, drop lifetime, EXP) until a job needs it.**
- **PLAN-data's camera stop rule (2026-11-21):** counted from the first fix after a portal to the exit fade (the
  ~1 s blind start and the fade do not count) - OK'd as read in REPORT-track-before.md section 3.
- **Moving scenery = two problems, one plan, P0 (2026-11-21).** (1) Moving backgrounds BEHIND the mobs: they
  should stop bothering perception; (2) Perion's clouds IN FRONT of the mobs: mobs found through them, or
  "covered by cloud" as a fact. The tracker is designed on the 13 sound captures until the plan is built.

### What the next sessions build on
- **`PLAN-moving-scenery.md` (PROPOSED 2026-11-21: measured and prototyped, nothing built in `maplebrain/`).**
  The forest maps hold no moving scenery: one flat picture's colour is exported wrong (the sky) and Ellinia's
  light rays are an ADDED layer - both right, 9 of 9 forest captures are sound. A moving back keeps its exact
  colours and goes `5 x rx` px a second along the map: drawn in and followed each frame, the fit finds what
  stands in front of it (+27 % sightings on Kerning's construction site, none lost). Perion's clouds in front =
  the client's 7 weather cloud pictures (42 maps), each cloud at its own constant opacity and speed, never
  opaque: undone, the fit finds the mobs under them (174 of 174 test mobs). About +3 ms a frame on Perion. After
  steps 1-5, 82 of the 95 refused maps hunt. Tools: `tools/perc/scenery/` on branch `moving-scenery`; results
  and by-eye sheets: `F:\dev\maple-corpus\work\scenery\`.
- **The footage for the tracker:** `20261121_000219_2#0`, Line 1 <Area 1>, 30.6 minutes of the user's farming
  in one stay (110,082 frames at 60 a second, 0 dropped), and `20261120_235747_1#0` (the same map, 4.2 minutes) -
  both at today's graphics settings. Bank: 19 recordings, 50 captures, 93 minutes, 31.9 GB (`corpus.py list`).
- **Loot scenes 1-2 are answered** (PLAN-loot.md section 13's result block): a drop left alone lies 2 minutes
  and fades out in place; our own pickup = a hop up toward us, then a short fade.
- **`docs/game_rules.md`**: the game's rules as v83 code has them, in px and seconds, each with its source line
  and the client-file field it reads (sections A-K, three tables). **Open = its table 3, 21 questions.** The ones
  that shape the next sessions: how a mob with aggro moves and attacks is in no source; mob movement exists only
  in HeavenClient's approximated physics; the walk range `rx0`/`rx1`, `fs`, `summonType`, `mobRate` are read by
  no source; Cosmic's respawn numbers are that emulator's own; Classic World's skill list is not v83's; which
  skills are on `w` / `e`.
- **The kept replay + the "before" numbers (`REPORT-track-before.md`, branch `tracker`).** Today's Perceiver,
  unchanged, over every frame of 23 captures (204,131 frames, 2.5 GB) in `F:\dev\maple-corpus\work\SESSION#K\track\`:
  per frame the camera, us, the fit's mobs, today's tracks and looks, drops, patches and the two bitmaps - a
  prototype runs from it with no GPU (`tools/perc/track/dump.py`, `load.ticks`). Perception is **sound on 13
  captures** (caves, dungeons, both Line 1); not sound on the 9 forest captures (PLAN-moving-scenery.md's step 1
  makes them sound) nor on Cave of Evil Eye III (camera lost). Today's tracker, pooled over the 13: FOUND
  96.4 %, HELD 96.8 % across <= 0.1 s but 31 % across 0.6-1.5 s, **64 % of mob lives on one track**, ghosts 1.4 %,
  an unwitnessed death stays "alive" p90 5.9 s. The truth checked by eye on 60 cases: gaps 21 right / 0 wrong / 19
  can't tell (mostly off screen), ends 15 / 3 / 2. Tools: `tools/perc/track/`.

### Proposed by Claude in the planning sessions (the user works along it; not OK'd as a whole)
- **One description of the game's state, three programs around it:** the tracker (the game's screen -> the
  state), the simulator's engine (the state + our input -> the next state, by the v83 rules), the viewer (the
  state -> a picture with real assets = PLAN-livemap.md, prototype `tools/livemap/proto.py`). The user's use 1 of
  the simulator = tracker + viewer, use 2 = the engine. The rules serve both sides: for the engine they are how
  the world advances, for the tracker how a mob can have moved between two frames.
- **What "ready for ML" asks of the tracker** (input for PLAN-tracker.md): (1) the same tracks live and from a
  replayed recording - inputs = the frame's facts + the key log + map data, nothing from the scripted brain,
  nothing tied to one class (read what happened to the mob, not what our weapon should have done); (2) a
  hindsight twin (looks both ways in time on a recording) = the truth the live tracker is graded on and the
  labeller of the user's play, never an input of the AI - prototyped in `tools/perc/track/oracle.py`, `score.py`;
  (3) facts, not verdicts: seen or not, covered by what, for how long, how see-through - in place of today's
  timeouts (lose_s 0.5, fight_s 1.2, covered_s / hidden_s 2.0); (4) one identity per mob with its history (hits
  taken, age), identity switches per mob life as a gate number; (5) events as outputs (spawned, hit, died by our
  last hit or not, dropped, picked up, we got hurt) = the training labels and the scoreboard, kills counted the
  same way for the user, the scripted bot and any model; (6) the whole map with memory (per platform: last seen
  when, how many, the respawn rule) and a slot for everything that moves: mobs, drops, other players, us (our
  facing is still a belief from the keys); (7) perception one-way (today the tracker calls back for a second
  look), so each frame's facts are computed once and a tracker change re-runs in seconds.
- **Parked until the FSM-or-clone decision:** REWORKS.md's Execution and Brain reworks, v3 steps 4-6 (the FSM
  path); hours of recordings on one map, the dataset builder, the training code (the clone path). Parked without
  a date: wide maps, by-eye validation of every map (PLAN-data Sessions 2-3: only its automatic half runs,
  inside step 2's prompt), the one gate list on the bank, the CPU mode.

## Open items (not scheduled; the detail is in the named file, or in HISTORY.md under the quoted words)
- **A lost scene camera** releases every key until it is found again, even on a 1-tick miss: to be handled as
  cases come up live (HISTORY.md "The deletion (DONE 2026-11-17)").
- **`w` and `e` are skills the code does not know** (not in `Keys`); the bank's farming label counts only
  `q` / `c` until they are.
- **Wide maps:** F7 now recognises maps whose minimap scrolls sideways; whether the locator and perception work
  on them is untested.
- **Left unknown by PLAN-moving-scenery.md:** animated objects (76 maps, under 0.8 % of the play area) and
  portals (its optional step 7); why a few moving backs creep against their law (followed each frame: harmless).
- **The scene camera waits ~1 s on every map entry** (the map is on screen before our character is drawn; the
  first seed needs our tag), and **after a 6.4 s hole in a recording it never came back** (Cave of Evil Eye III,
  `20261118_232410_1#11`: 22 s blind). REPORT-track-before.md, "What surprised me" 1-2.
- **The chat was open** in the 2026-11-18/19 exploration captures (mobs behind it seen through it or lost).
- **PLAN-data.md:** a walk cut in the wrong place has no `refile` command (a fix by hand); "ONE gate list" on
  the bank instead of four lists of `runs/` paths is agreed as a future plan session - until then the PNG
  recordings under `runs/` stay.
- **PLAN-loot.md:** part 1 (perceive drops) is done and merged; part 2 (use them) is inside the tracker rework.
- **Older items, not re-checked since the perception rework of 2026-11-16/17 - they may be moot:** the "P2"
  accuracy + speed plan A1-A6 and "turning too slowly" (2026-11-08); movement: a rope top read as rope, "air"
  with no way out, ladder 778's tag reading +10 px; the Lie Detector is not looked for while the game is
  unfocused, and there is no capture watchdog; a phone alert on a Lie Detector.

## Branches (2026-11-21)
- `dev` holds everything: `rules`, `claude-arch`, `tracker` and `data` are merged into it (2026-11-21, on the
  user's word) and can be deleted. One worktree is registered that is not this layout's: `wt64`, detached at
  64f9713, in another session's scratchpad - leave it to that session.
- `moving-scenery` (e25a820, off `dev`, pushed, not merged): `tools/perc/scenery/` only - the plan session's
  measurements and prototypes. The plan's executor steps continue on it.
- `main` has not moved since 2026-11-09 (02a639a) and has no CLAUDE.md. Parked: `vnc-keys` (the VM attempt).

## Waiting on the user
- **PLAN-moving-scenery.md: the OK** (or changes) and its three questions (its last section). **A recording:
  Perion Street Corner, 5+ minutes of farming at today's settings** (the first ~20 s standing still, the whole
  map crossed once) - needed before the plan's step 4; step 1 can start without it.
- **Define the tracker and its goals explicitly, before step 3 runs.** The user's own words, written into
  `docs/prompts/tracker-plan.md`: what the tracker is, what it must output, how good it must be. Today that
  prompt has no goals of its own - it inherits the 7 points under "Proposed by Claude", never OK'd as a whole.
- The "explained" reading of PLAN-data's stop rule (REPORT-track-before.md section 3), to confirm or change:
  map places the scene model misses on more than half of the frames that show them (what moves over the
  scenery does not count). PLAN-moving-scenery.md assumes it.
- More walks for the bank are welcome (`python -m maplebrain record --label NAME`, chat minimized).
