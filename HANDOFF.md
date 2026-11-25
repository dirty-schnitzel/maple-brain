# maplebrain - handoff: the current state

This file is already in your context: CLAUDE.md imports it, so there is no need to read it again. It holds only
what is true NOW and what comes NEXT. The `handoff` skill rewrites it at the end of a session - it is never
appended to. Everything older is in HISTORY.md (grep it; what left this file on 2026-11-21 is its last
blocks). Rules that stay true: CLAUDE.md and .claude/rules/. Plans and their progress: PLAN-*.md.

## START HERE (2026-11-26): `PLAN-tracker.md` is APPROVED - steps 1, 2, 3, 3b, 4a, 7 DONE; 4b try 2 STOPPED (the user decides)

**The user's goal (2026-11-19):** "have a great perception / tracking / data model in order to feed that into an
ai to see how many hours of farming on a specific map with a specific class and style are needed to teach it to
farm a map efficiently and humanlike. Then benchmark different models at the same job". **The benchmark ends in
a research paper (the user, 2026-11-24)** - what it needs and the reviewers' risks to design for (reproducible
release without the frames, live-run ethics, other players' names, small n): the `north-star-learning-curve`
memory; nothing scheduled for it yet. **Priorities
(2026-11-20):** "good tracking ready for ML applications, and a simulator that can 1 - show the current state of
the game live just like livemap but with real assets, 2 - take our input and be used to train AI". **Left open by
the user:** a full FSM or a cloned-behaviour AI. **OK'd 2026-11-23 with the tracker plan's prompt:** no guessing
in the tracker, the data model first, no simulator engine now (the model: `docs/state_model.md`; the discussion
that led to it: HISTORY.md, the block of 2026-11-24).

### The order from here
| # | Session | Run as | Status | Prompt |
|---|---|---|---|---|
| **P0.1-5** | **The plan's steps 1-5, one executor session each:** 1 the pictures right (the forest maps sound), 2-3 moving backs drawn and followed (40 maps hunt), 4-5 Perion's clouds followed and undone (42 maps hunt). Steps 4-5 need the user's Perion recording | Opus (high) | **steps 1-5 DONE 2026-11-23**, the numbers each missed gate fell short on ACCEPTED by the user (PLAN-moving-scenery.md's status); merged into `dev` 2026-11-23 (9085f5b). Steps 6-7 wait for footage | `PLAN-moving-scenery.md`, "Session prompts" |
| 4 | **PLAN-tracker.md's steps, one executor session each** (branch `tracker-build` off `dev`, after `tracker-plan` is merged into `dev`): 1 label sets by eye, 2 the graph and placement, 3 mobs in shadow, 4a drops, 4b other players and us, 5 events, 6 the facts registry + profile + Skill.img, 7 the hotkey reader, 8 the stored tables, 9 the switch (the brain reads the new state, `world.py` goes). Steps 1, 2 and 7 could run beside each other, 4a beside 4b, 5 / 6 / 8 in pairs (the plan's table) - the user decides. Beside it, at any time: the viewer (PLAN-livemap.md Session 1: use `dev`). No engine session | Opus (effort per step: 1 medium, 2 high, 3 xhigh, 4a / 4b high, 5 xhigh, 6-8 medium, 9 high) | **Steps 1, 2, 3 (+ the slope fix: L1 98.98 %, accepted) and 7 DONE** (their plan sections; 2 is in `dev`). **Step 4b, try 2 STOPPED 2026-11-26** (3c437ef, the plan's "Step 4b, try 2"): the user's answers built - "not yet known" under 6 sightings, feet from the tag's top (a 21 px medal tag: its bottom), pets by the 75th percentile of a track's body heights against 50 px (measured first), L1J (18 "us" jump labels stand -> air on strips), a rope motion test, the body question in the mob tracker's one GPU transfer. Met: step 3's rows and the hops gate unchanged, one transfer a frame. Missed: L5 (found 92.8 %), the cover (33), L1 us 84.62 % (93.41 % without the motion test), the ms (0.7) - **the user decides** (Waiting on the user). SelfState 95.81 % and our feet known 97.04 % accepted (try 1). **Step 3b DONE 2026-11-26** (the plan's "Step 3b, try 3" and its answers): the mob tracker takes the fade's direction (a die pose at >= 0.99 = a death, under it fallen = a death, rising / flat = the live mob keeping its feet, on a remembered track held one sighting; a faint birth is "faded in" only while its opacity rises) - 0 fading-in splits, one id 92.33 %, extra ids 994, jolts 524, every step-3 row met; `track/spawns.py` + `state.SpawnPoint` in shadow: 585 of 594 faded-in mobs traced to one point (98.5 %), sheet 29 of 30, live rows = replay rows (15,211 of 15,211), 0.045 ms live. **Step 4a DONE 2026-11-25, accepted by the user as it is, merged into `tracker-build`** (the plan's "Step 4a, 2026-11-25"): `track/drops.py` (proto_drops ported; "we took it" = the pickup key DOWN in the window; from_mob from the mob tracker's deaths), the port exact (746 of 746); 746 drops, L6 97.4 %, exactly one death 88.5 %, ms p50 0.197; accepted misses: 35 pickup hops without our key down (the pet "Snail" on the 2026-11-18 captures) and 1 false "gone" (a passing flight read as a pickup hop). Not in the live frame yet (no key events there). 5 / 6 / 8 follow the plan's table once 4b is settled | `PLAN-tracker.md`, "Session prompts" |
| 4b | Wide maps: plan, then execute, the scrolling minimap placed by several agreeing patches (Open items, "Ideas from another bot") | Fable, max -> Opus | after the tracker (the user, 2026-11-22) | - |
| 5 | FSM or clone, decided on what both score in live runs, counted by the tracker's events | - | open | - |

### Decided by the user (also: the rules' sources - `.claude/rules/gamedata.md`; the graphics settings -
`.claude/rules/perception.md`; earlier ones in HISTORY.md)
- **Not wanted now:** the two bot hunts for PLAN-data gate (b)'s tick cost; loot scene 3 of PLAN-loot.md section
  13 (windows over drops: "inventory will come much later down the line and is not a part of tracking").
- **Drops in the tracker:** "expect the loot to be there for 2 mins (max loot decay time) and if it disappears
  then update the model" - a drop stays in the model from its first resting sighting until its place is seen
  without it, or until it is 130 s old when we never look there again.
- **Game rules (2026-11-25): our footage > meowdb's Classic World guides > v83 code** ("replace cosmic game
  rules with meowdb when possible, observed data still beats server rules"). Done in `docs/game_rules.md`
  (source MW; a replaced rule kept, marked) + `docs/meowdb.md` (what the guides say, checked against ours).
  meowdb's swing formula is ours, `(10 + attackSpeed) / 16`; its 7.56 s respawn round lost to our measured ~7.1 s.
- **Movement and server data (2026-11-21):** Classic World raised the base jump and move speed, so our fitted
  movement values stand over v83's constants (`Nav.jump_vx` 155 etc.; meowdb explains it: walking 150 px/s at
  Speed 100); **no further work on server data (respawn, aggro, drop lifetime, EXP) until a job needs it.**

### What the next sessions build on
- **`docs/state_model.md` (OK'd) + `PLAN-tracker.md` (APPROVED 2026-11-24).** The model: the map's graph, the
  facts, per frame us / mobs / drops / players with where each is on the graph and how it is seen, the events.
  The plan's prototypes (`tools/perc/track/proto_*.py`; outputs in `F:\dev\maple-corpus\work\track-plan\`) are the
  reference; their numbers are its measurements. **Built so far** (`tracker-build`; nothing reads it): the graph and
  placement (`track/graph.py`), the hotkey reader (`perception/slots.py` + `track/us.py`'s slots; pictures by
  `tools/cwdata/export_slots.ps1` -> `assets build`), in the Perceiver's shadow the mobs (`track/mobs.py`, `kinds.py`,
  `evidence.py`, `state.py`), spawn points (`spawns.py`), us and other players (`us.py`, `players.py`), and from the
  kept replay only the drops (`drops.py`); each graded by `tools/perc/track/replay_*.py`. **Found:** mobs move at 2 x the v83 rule's speed (noted in `docs/game_rules.md` C1); the
  fit makes false sightings from slivers of players at the screen's edge; the truth (`oracle.py`) swaps two
  mobs of a kind at crossings (457 of the prototype's 1,022 "id changes"), so the plan's gates use a fair count.
- **The footage for the tracker:** `20261121_000219_2#0`, Line 1 <Area 1>, 30.6 minutes of the user's farming
  in one stay (110,082 frames at 60 a second, 0 dropped), and `20261120_235747_1#0` (the same map, 4.2 minutes) -
  both at today's graphics settings. Bank: 19 recordings, 50 captures, 93 minutes, 31.9 GB (`corpus.py list`).
- **`docs/game_rules.md`**: the game's rules from our footage, meowdb and v83 code, each with its source; **open =
  its table 3** (21 questions, 4 answered by meowdb 2026-11-25: aggro movement, the walk range `rx0`/`rx1` ... stay).
- **The kept replay** (`F:\dev\maple-corpus\work\SESSION#K\track\`, `tools/perc/track/dump.py`): the Perceiver's
  facts + two bitmaps for every frame of 23 captures - the tracker's steps run from it with no GPU; **sound on 13
  captures** (caves, dungeons, both Line 1). A new kept replay goes into its own folder, never over the old one (the
  user, 2026-11-24; PLAN-tracker stop rule 5). Detail: REPORT-track-before.md, HISTORY.md 2026-11-25.

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
- **A lost scene camera** releases every key until it is found again, even on a 1-tick miss: to be handled as
  cases come up live (HISTORY.md "The deletion (DONE 2026-11-17)").
- **Found by meowdb (2026-11-25, `docs/game_rules.md` A1, E1-E2):** `Nav.walk_speed` is 125 (Physics.img) where the
  rule is 150 px/s - measure our own walk from the bank's feet tracks before changing it (route costs); meowdb's map
  capacity, 5 s spawn cooldown and 100 px block are checkable on the kept replay (most mobs alive at once, the time
  between two spawns on a point, a mob near a ready point) - when a job needs spawning.
- **`w` and `e` are skills the code does not know** (not in `Keys`); the bank's farming label counts only
  `q` / `c` until they are. Seen in the footage: q Power Strike, w Slash Blast, e Rush (PLAN-tracker.md
  measurement 6); the profile file of its step 6 is where they will live.
- **Perception, found by the tracker plan (not in its scope):** the fit sights "mobs" in slivers of players at
  the screen's edge (PLAN-tracker.md measurement 2; the new tracker does not remember them); the play area's
  bottom two rows (y 698-699) are the HUD's edge and are not masked; our tag reader misses our tag when front
  scenery (a post, a lever) hides part of it - its piece is in the tag list (step 4b takes it by the edge: +0.36 points).
- **The mob finder's misses, found by tracker step 3 (not in its scope, stop rule 4; cases in PLAN-tracker.md
  "Step 3, 2026-11-24" and "Step 3, try 2"):** 46 L1-labelled mobs no track saw (the labellers added them, the fit
  missed them); 5 L2 mobs in plain view the fit missed (cases 24, 29, 34, 36, 71); 6 mobs with the fit's feet 9-35 px
  off the surface (L1 cases 24, 29, 34, 35, 42, 158: Evil Eye `jump_0` / `hit1_0`, Zombie Mushroom).
- **The bot speed in a worktree:** `tools/perf/bench.py` and pytest's `bot speed` line run the fit only where
  `assets/scene` exists (not in git): in a worktree without it the tick is ~3.7 ms instead of ~14.5 ms (found by
  step 7, 2026-11-24). Measure speed in the main folder or with `assets/scene` linked (proposed for CLAUDE.md
  "Measuring"; not yet agreed by the user).
- **When `tracker-build` merges into `dev`:** CLAUDE.md's code map gets `perception/slots.py` (the hotkey reader)
  and a `track/` row (the new tracker: `graph.py`, `us.py`, `players.py`, `mobs.py`, `drops.py`, `spawns.py`, `kinds.py`, `evidence.py`, `state.py`).
- **Found by step 4b (PLAN-tracker.md "Step 4b, try 2"):** a pet's name tag is often taken by its owner's track (10 of
  13 L5 pets called players: the boxes merge and part); a spear attack stance reads 10-22 px between the legs; try 1's
  "the GPU transfer waits ~0.4 ms" was wrong - the GPU is idle there (a sync costs 0.03 ms), the cost is Python and
  torch calls (`ask_columns` 0.37 ms for one tag).
- **`PLAN-moving-scenery.md` is not valid UTF-8** (the Read tool says so; the Edit tool refuses it): to be
  converted on the user's word.
- **Wide maps:** F7 now recognises maps whose minimap scrolls sideways; whether the locator and perception work
  on them is untested. To plan and execute (the user, 2026-11-22), with the other bot's minimap idea above.
- **The scene camera waits ~1 s on every map entry** (the map is on screen before our character is drawn; the
  first seed needs our tag), and **after a 6.4 s hole in a recording it never came back** (Cave of Evil Eye III,
  `20261118_232410_1#11`: 22 s blind). REPORT-track-before.md, "What surprised me" 1-2.
- **PLAN-data.md:** a walk cut in the wrong place has no `refile` command (a fix by hand); "ONE gate list" on
  the bank instead of four lists of `runs/` paths is agreed as a future plan session - until then the PNG
  recordings under `runs/` stay.
- **Older items, not re-checked since the perception rework of 2026-11-16/17 - they may be moot:** the "P2"
  accuracy + speed plan A1-A6 and "turning too slowly" (2026-11-08); movement: a rope top read as rope, "air"
  with no way out, ladder 778's tag reading +10 px; the Lie Detector is not looked for while the game is
  unfocused, and there is no capture watchdog; a phone alert on a Lie Detector.

## Branches (2026-11-26)
- `dev` holds everything: `rules`, `claude-arch`, `tracker` and `data` are merged into it (2026-11-21, on the
  user's word) and can be deleted. One worktree is registered that is not this layout's: `wt64`, detached at
  64f9713, in another session's scratchpad - leave it to that session.
- `moving-scenery` and `tracker-plan`: merged into `dev` (2026-11-23 / 11-24), nothing missing; can be deleted.
- **`tracker-build`** (2026-11-24, off `dev` at 8f00b8e): PLAN-tracker's steps; **the main folder is on it** (at
  step 4b try 2, 3c437ef, pushed). `dev` is merged into it (steps 2 and 7 are in); a step that runs beside another
  works in its own worktree on `tracker-build-<step>` and is merged back. `tracker-build-drops` (step 4a) is merged into it (2026-11-25) and can be
  deleted with its worktree `.claude/worktrees/drops`. `.claude/worktrees/slots`: an empty leftover, deletable.
- `main` has not moved since 2026-11-09 (02a639a) and has no CLAUDE.md. Parked: `vnc-keys` (the VM attempt).

## Waiting on the user
- **The fade-in measured on Classic World: 0.82 s** (v83 E3: 0.32 s; PLAN-tracker "Step 3b, try 2") - into
  `docs/game_rules.md` E3 as observed? (not asked yet)
- **Step 4b, try 2's four questions** (PLAN-tracker.md "Step 4b, try 2", "For the user"): pets (75th percentile, a
  share, or first the association: an owner's track taking its pet's box) and the cover with them; L1 us (drop the rope
  motion test: 93.41 %, this frame's step: 92.86 %, keep: 84.62 %); the ms (accept ~0.8, or a cheaper body question).
- **`PLAN-tracker.md` (APPROVED 2026-11-24): question 8** (EXP in the kill rule), put to the user by step 5's
  session. Questions 1-7 answered and written into the plan: observed data beats server rules, no pets, players'
  cover 2 s, no buffs / cooldowns for the warrior, HP x 1.24 = the warrior's passive; the empty-place rule 40 %.
- **Its footage** ("Footage asked of the user"): welcome - a map with flying mobs, an Ant Tunnel map.
- PLAN-moving-scenery.md's questions (its last section), if any are still open; footage for its steps 6-7.
- The "explained" reading of PLAN-data's stop rule (REPORT-track-before.md section 3), to confirm or change:
  map places the scene model misses on more than half of the frames that show them (what moves over the
  scenery does not count). PLAN-moving-scenery.md assumes it.
- More walks for the bank are welcome (`python -m maplebrain record --label NAME`, chat minimized).
