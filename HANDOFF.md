# maplebrain - handoff: the current state

This file is already in your context: CLAUDE.md imports it, so there is no need to read it again. It holds only
what is true NOW and what comes NEXT. The `handoff` skill rewrites it at the end of a session - it is never
appended to. Everything older is in HISTORY.md (grep it; what left this file on 2026-11-21 is its last
blocks). Rules that stay true: CLAUDE.md and .claude/rules/. Plans and their progress: PLAN-*.md.

## START HERE (2026-11-24): `PLAN-tracker.md` is PROPOSED - the user's OK, answers and footage, then its steps

**The user's goal (2026-11-19):** "have a great perception / tracking / data model in order to feed that into an
ai to see how many hours of farming on a specific map with a specific class and style are needed to teach it to
farm a map efficiently and humanlike. Then benchmark different models at the same job". **Priorities
(2026-11-20):** "good tracking ready for ML applications, and a simulator that can 1 - show the current state of
the game live just like livemap but with real assets, 2 - take our input and be used to train AI". **Left open by
the user:** a full FSM or a cloned-behaviour AI. **OK'd 2026-11-23 with the tracker plan's prompt:** no guessing
in the tracker, the data model first, no simulator engine now (the model: `docs/state_model.md`; the discussion
that led to it: HISTORY.md, the block of 2026-11-24).

### The order from here
| # | Session | Run as | Status | Prompt |
|---|---|---|---|---|
| **P0.1-5** | **The plan's steps 1-5, one executor session each:** 1 the pictures right (the forest maps sound), 2-3 moving backs drawn and followed (40 maps hunt), 4-5 Perion's clouds followed and undone (42 maps hunt). Steps 4-5 need the user's Perion recording | Opus (high) | **steps 1-5 DONE 2026-11-23**, the numbers each missed gate fell short on ACCEPTED by the user (PLAN-moving-scenery.md's status); merged into `dev` 2026-11-23 (9085f5b). Steps 6-7 wait for footage | `PLAN-moving-scenery.md`, "Session prompts" |
| 3 | The tracker plan session, in two parts: (1) the data model -> `docs/state_model.md`, stop for the user's OK; (2) the tracker that fills it -> `PLAN-tracker.md`, PROPOSED until the user's OK. Take along: per mob, on our platform or not (Open items, "Ideas from another bot") | Fable, max | **DONE.** Part 1: `docs/state_model.md`, OK'd by the user 2026-11-23. Part 2: **`PLAN-tracker.md` PROPOSED 2026-11-24** - not OK'd yet; its 7 questions and 4 footage asks are open | done (the prompt, `docs/prompts/tracker-plan.md`, is in git history) |
| 4 | **PLAN-tracker.md's steps, one executor session each** (branch `tracker-build` off `dev`, after `tracker-plan` is merged into `dev`): 1 label sets by eye, 2 the graph and placement, 3 mobs in shadow, 4a drops, 4b other players and us, 5 events, 6 the facts registry + profile + Skill.img, 7 the hotkey reader, 8 the stored tables, 9 the switch (the brain reads the new state, `world.py` goes). Steps 1, 2 and 7 could run beside each other, 4a beside 4b, 5 / 6 / 8 in pairs (the plan's table) - the user decides. Beside it, at any time: the viewer (PLAN-livemap.md Session 1: use `dev`). No engine session | Opus | **waits for the user's OK on the plan**; step 3 also for the fresh Line 1 capture, step 7 for the quickslot footage | `PLAN-tracker.md`, "Session prompts" |
| 4b | Wide maps: plan, then execute, the scrolling minimap placed by several agreeing patches (Open items, "Ideas from another bot") | Fable, max -> Opus | after the tracker (the user, 2026-11-22) | - |
| 5 | FSM or clone, decided on what both score in live runs, counted by the tracker's events | - | open | - |

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
  "covered by cloud" as a fact. The tracker is designed on the 13 sound captures until the plan is built. The
  plan OK'd 2026-11-21 ("execute moving-scenery plan"); its three questions are still open.

### What the next sessions build on
- **`docs/state_model.md` (OK'd) + `PLAN-tracker.md` (PROPOSED 2026-11-24).** The model: the map's graph, the
  facts, per frame us / mobs / drops / players with where each is on the graph and how it is seen, the events.
  The plan: every part has a prototype that ran from the kept replay (`tools/perc/track/proto_*.py`, branch
  `tracker-plan`; outputs in `F:\dev\maple-corpus\work\track-plan\`). Mobs, 13 captures: found 98.7 % (today
  96.3), the id kept across a cover 93.4 % (78.5), 1,022 id changes (2,232) - by keeping the places an unseen
  mob can be and dropping those that show the scenery, 4 s at most when nothing can be checked. Drops 746, none
  lost and found again; every HP / MP / EXP step explained; the 8 hotkeys read exactly on every frame; other
  players by name tag. **Found:** mobs move at 2 x the v83 rule's speed (noted in `docs/game_rules.md` C1); the
  fit makes false sightings from slivers of players at the screen's edge; the truth (`oracle.py`) swaps two
  mobs of a kind at crossings (457 of the prototype's 1,022 "id changes"), so the plan's gates use a fair count.
- **`PLAN-moving-scenery.md` (steps 1-5 DONE 2026-11-23 and merged into `dev`; each step's numbers under its
  heading there; steps 6-7 wait for footage).** The forest
  maps hold no moving scenery: the export decoded the sky's colour wrong and Ellinia's light rays are an ADDED
  layer - both right now (`export.ps1`, `scene.py` on `moving-scenery`): 9 of 9 forest captures sound (model
  96.3-99.7 %, the kept replay re-made), the live fit = the prototype's on Forest S of Ellinia, `gate.py` SAME. A moving back keeps its exact
  colours and goes `5 x rx` px a second along the map: drawn in and followed each frame, the fit finds what
  stands in front of it (+27 % sightings on Kerning's construction site, none lost). Perion's clouds in front =
  the client's 7 weather cloud pictures (42 maps), each cloud at its own constant opacity and speed, never
  opaque: undone, the fit finds the mobs under them (174 of 174 test mobs). About +3 ms a frame on Perion. After
  steps 1-5, 82 of the 95 refused maps hunt. Tools: `tools/perc/scenery/` (its README); results and by-eye
  sheets: `F:\dev\maple-corpus\work\scenery\`.
- **The footage for the tracker:** `20261121_000219_2#0`, Line 1 <Area 1>, 30.6 minutes of the user's farming
  in one stay (110,082 frames at 60 a second, 0 dropped), and `20261120_235747_1#0` (the same map, 4.2 minutes) -
  both at today's graphics settings. Bank: 19 recordings, 50 captures, 93 minutes, 31.9 GB (`corpus.py list`).
- **`docs/game_rules.md`**: the game's rules as v83 code has them, in px and seconds, each with its source line
  and the client-file field it reads (sections A-K, three tables). **Open = its table 3, 21 questions**, among
  them: how a mob with aggro moves and attacks is in no source; the walk range `rx0`/`rx1` is read by no source;
  Classic World's skill list is not v83's; which skills are on `w` / `e`.
- **The kept replay + the "before" numbers (`REPORT-track-before.md`, branch `tracker`).** Today's Perceiver,
  unchanged, over every frame of 23 captures (204,131 frames, 2.5 GB) in `F:\dev\maple-corpus\work\SESSION#K\track\`:
  per frame the camera, us, the fit's mobs, today's tracks and looks, drops, patches and the two bitmaps - a
  prototype runs from it with no GPU (`tools/perc/track/dump.py`, `load.ticks`). Perception is **sound on 13
  captures** (caves, dungeons, both Line 1); not sound on the 9 forest captures (PLAN-moving-scenery.md's step 1
  makes them sound) nor on Cave of Evil Eye III (camera lost). Today's tracker's numbers on the 13 stand beside
  the prototype's in PLAN-tracker.md. The truth checked by eye on 60 cases: gaps 21 right / 0 wrong / 19 can't
  tell (mostly off screen), ends 15 / 3 / 2; its chains are kept on disk (`cache.py`). **Two scene builds in
  it:** re-made on the full build = the 9 forest captures + Ant Tunnel I; the other 8 stay as they are (the user,
  2026-11-23: no re-make, fresh captures as needed).

### Parked
- **No simulator engine now** (the user, 2026-11-22: "there might be an engine down the line, but after
  tracking and at least full fsm behavior"). A clone learns from recordings (the state + the user's keys); FSM
  and clone are benchmarked in live runs counted by the tracker's events. The viewer stays.
- **Parked until the FSM-or-clone decision:** REWORKS.md's Execution and Brain reworks (Execution takes two ideas
  from another bot: Open items), v3 steps 4-6 (the FSM path); hours of recordings on one map, the dataset builder,
  the training code (the clone path). Parked without a date: by-eye validation of every map (PLAN-data Sessions
  2-3: only its automatic half runs, inside step 2's prompt), the one gate list on the bank, the CPU mode.
- **The code no plan reworks** (brain, execution, navmap's edges, the EXP meter, the Lie Detector, the viewers):
  REWORKS.md, "Left to rework".

## Open items (not scheduled; the detail is in the named file, or in HISTORY.md under the quoted words)
- **Ideas from another bot, each for its phase (the user, 2026-11-22; HISTORY.md, "maplestory-automation"):**
  perception, to plan and execute: a scrolling minimap placed by several patches agreeing on one shift (the wide
  maps, below); the Execution rework: key-release locking, and a dead-man release (no tick ended for ~1 s -> every
  key up; today a hung loop keeps our keys held); the tracker / data model: per mob, on our platform or not, from
  foothold heights; perception, lower priority: any client window over the world -> a stop + "covered by a window".
- **The local scenes were stale until 2026-11-21** (PLAN-moving-scenery.md step 1, "Found on the way"): only
  the gate clips' 5 maps had the fit's front planes, so every other map's live hunts and replays ran without them;
  all 233 built now (+7 % sightings on Ant Tunnel I, up to +62 % on the forests).
- **A lost scene camera** releases every key until it is found again, even on a 1-tick miss: to be handled as
  cases come up live (HISTORY.md "The deletion (DONE 2026-11-17)").
- **`w` and `e` are skills the code does not know** (not in `Keys`); the bank's farming label counts only
  `q` / `c` until they are. Seen in the footage: q Power Strike, w Slash Blast, e Rush (PLAN-tracker.md
  measurement 6); the profile file of its step 6 is where they will live.
- **Perception, found by the tracker plan (not in its scope):** the fit sights "mobs" in slivers of players at
  the screen's edge (PLAN-tracker.md measurement 2; the new tracker does not remember them); the play area's
  bottom two rows (y 698-699) are the HUD's edge and are not masked; our own tag is in the tag list on 1,179
  frames of the 30-minute capture where `FrameFacts.tag` is empty.
- **`PLAN-moving-scenery.md` is not valid UTF-8** (the Read tool says so; the Edit tool refuses it): to be
  converted on the user's word.
- **Wide maps:** F7 now recognises maps whose minimap scrolls sideways; whether the locator and perception work
  on them is untested. To plan and execute (the user, 2026-11-22), with the other bot's minimap idea above.
- **The scene camera waits ~1 s on every map entry** (the map is on screen before our character is drawn; the
  first seed needs our tag), and **after a 6.4 s hole in a recording it never came back** (Cave of Evil Eye III,
  `20261118_232410_1#11`: 22 s blind). REPORT-track-before.md, "What surprised me" 1-2.
- **The chat was open** in the 2026-11-18/19 exploration captures (mobs behind it seen through it or lost).
- **PLAN-data.md:** a walk cut in the wrong place has no `refile` command (a fix by hand); "ONE gate list" on
  the bank instead of four lists of `runs/` paths is agreed as a future plan session - until then the PNG
  recordings under `runs/` stay.
- **Older items, not re-checked since the perception rework of 2026-11-16/17 - they may be moot:** the "P2"
  accuracy + speed plan A1-A6 and "turning too slowly" (2026-11-08); movement: a rope top read as rope, "air"
  with no way out, ladder 778's tag reading +10 px; the Lie Detector is not looked for while the game is
  unfocused, and there is no capture watchdog; a phone alert on a Lie Detector.

## Branches (2026-11-24)
- `dev` holds everything: `rules`, `claude-arch`, `tracker` and `data` are merged into it (2026-11-21, on the
  user's word) and can be deleted. One worktree is registered that is not this layout's: `wt64`, detached at
  64f9713, in another session's scratchpad - leave it to that session.
- `moving-scenery`: steps 1-5, merged into `dev` 2026-11-23 (9085f5b); nothing on it is missing from `dev`.
- `tracker-plan` (2026-11-24): the plan session's tools - `tools/model/` (Part 1) and the prototypes in
  `tools/perc/track/` (Part 2) - off `dev`; **the main folder is on it**. Nothing in `maplebrain/` differs from
  `dev`. **To be merged into `dev` by the user before PLAN-tracker's step 2** (the executors port from it).
- `main` has not moved since 2026-11-09 (02a639a) and has no CLAUDE.md. Parked: `vnc-keys` (the VM attempt).

## Waiting on the user
- **`PLAN-tracker.md`: the OK, and its question 8** (EXP in the kill rule; before step 5). Questions 1-7 were
  answered 2026-11-24 and written into the plan: observed data beats server rules, no pets, players' cover 2 s,
  no buffs / cooldowns for the warrior, HP x 1.24 = the warrior's passive.
- **Its footage** ("Footage asked of the user"): 5 minutes of farming on Line 1 (step 3); 1-2 minutes of the
  quickslot bar with a skill on a key, an amount at 0, a tooltip, a window over it (step 7); welcome: a map with
  flying mobs, an Ant Tunnel map; a buff cast 5 times if the character has one. And the merge of `tracker-plan`.
- PLAN-moving-scenery.md's questions (its last section), if any are still open; footage for its steps 6-7.
- The "explained" reading of PLAN-data's stop rule (REPORT-track-before.md section 3), to confirm or change:
  map places the scene model misses on more than half of the frames that show them (what moves over the
  scenery does not count). PLAN-moving-scenery.md assumes it.
- More walks for the bank are welcome (`python -m maplebrain record --label NAME`, chat minimized).
