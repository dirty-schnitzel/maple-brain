# PLAN-tracker: the tracker that fills the state model

**Status: APPROVED by the user 2026-11-24** (proposed the same day by the tracker plan session, Part 2:
`docs/prompts/tracker-plan.md`). Built in `maplebrain/`: step 2 (`track/graph.py`), step 7 (`perception/slots.py`). **Questions 1-7 answered** (written under
"Questions for the user" and into the design and steps). **The empty-place rule stays at 40 %** (the user: "keep
40%"; 60 % measured on all 13 captures, under measurement 1). **Question 8 (EXP in the kill rule) is postponed to
step 5** (the user): step 5's session puts it to the user before building the events.
**Step 1 DONE (2026-11-24).** Try 1 missed on L1, L2, L3, L4, L6; try 2 (the user's fixes) met on L4, L5, L6,
L7, L8; try 3 (L1's cases near a rope, on strips of frames) **met on L1: 97.2 %**. L2 and L3: no third try, the
user's decision - they keep only the cases both looks agreed on (L2 21, L3 22) for every later gate. The numbers
under the steps ("Step 1, try 2", "Step 1, try 3").
Step 3 needs no new footage (stop rule 5, changed 2026-11-24: a new kept replay of a Line 1 capture instead).
**Step 7 DONE (2026-11-24):** the gate met (L7 reworded by the user), merged into `tracker-build`; numbers under
the steps ("Step 7, 2026-11-24").
**Step 2 (2026-11-24, branch `tracker-build-graph`, 88ff6e8): built, the gate MET** - numbers under the steps ("Step
2 - built 2026-11-24"). Merged into `dev` 2026-11-24 (the user). Its found-on-the-way 3 (the rebuild's worker thread
delays frame work by up to ~20-30 ms while it runs): **the user, 2026-11-24: "keep same thread"**.
The model this tracker fills: `docs/state_model.md` (OK'd by the user 2026-11-23). Every number below was measured
in this session on the kept replay (no GPU); the tools are in `tools/perc/track/` (branch `tracker-plan`).

## In short
- **Today's tracker (`perception/world.py`) covers a small part of the model**: mobs only, by timeouts. No drops,
  no other players, no events, no "where it can be" while unseen, no facts, no hotkey reader; its placement is
  "within 16 px of a surface".
- **Every part of the model has a prototype that ran on recorded footage**, each graded:
  - *mobs* (13 captures, 1,774 lives): found 98.7 % (today 96.3), the id kept across a cover 93.4 % (78.5), half
    as many id changes (1,022 against 2,232), a death seen noticed at once in both. The idea: a mob that is not
    seen keeps the set of places it can be and loses every place where the frame shows the scenery - gone at
    once when none is left, kept 4 s at most when nothing can be checked; a new track is not a mob until seen
    clearly once.
  - *drops* (746): followed by item, place and their own bob; no drop called gone and seen again; the mob it
    came from named for 85 %; "we took it" seen as the pickup hop with the key down.
  - *events* (30 minutes): every step of HP, MP and EXP has a cause; a kill is ours by the swing's landing
    window and reach, 0.4 % by chance, cross-checked by the EXP.
  - *other players* (308 tracks): followed by their name tags; none of 20 checked was a non-player; pets'
    tags are a class of their own.
  - *the hotkey reader*: all 8 keys' item and amount exact on 110,082 of 110,082 frames, 79 of 79 potion uses
    seen as a step of -1, no misread, about 0.01 ms a frame.
- **Found on the way:** every mob kind moves at **twice the speed the v83 rule gives**; the fit makes false
  sightings from slivers of players at the screen's edge; a jump's feet are settled exactly by two rules; of
  835 presses of the attack key only 500 were casts; the truth swaps two mobs of a kind at 457 crossings where
  the prototype does not.
- **The plan:** 9 steps, each one executor session with a gate on footage - label sets by eye, the graph and
  placement, mobs in shadow, drops, players and us, events, the facts registry, the hotkey reader, the stored
  tables, the switch. Three of the model's targets are not met as written (question 1).

## Words
- **Sighting:** one mob the fit found on one frame (kind, pose, feet, how much of it was seen).
- **Track:** the tracker's record of one mob over time (its id). **Tentative:** a track that was never seen
  clearly - not yet a mob in the state. **Remembered:** a track not seen on this frame.
- **Possible set:** the places on its platform a remembered mob can be now.
- **The truth:** the fit's own sightings linked in hindsight into mob lives ("chains", `tools/perc/track/oracle.py`).
  It was checked by eye on 60 cases (REPORT-track-before.md section 5): short gaps right, long gaps mostly off
  screen and unproven, 1 in 7 "ends" not a real end. It cannot say which of two overlapping mobs of one kind is
  which.
- **Fair ids:** the truth's mob keeps its track for as long as that track is within 24 px of it; a change is
  counted only when it is not. (`score.py` takes the nearest track on every frame, so two mobs standing within
  24 px make "changes" on tracks that never changed - both ways of counting are given.)

## Where `world.py` stands against the model
| The model asks for | `world.py` today | Gap |
|---|---|---|
| Mob `id`, one for life | an id per track; ended by timers (0.5 s unseen, 1.2 s near us, 2 s behind cover / our body, 4 s off screen) | 65 % of lives keep one id (fair count); 30 % of covers of 0.6-1.5 s keep it |
| `kind` | voted over the track | kept |
| `x`, `y` | the fit's feet + the camera | a jump's feet 17 px off on look-alike poses; no track for a mob less than 60 % on screen (85 % of today's missed mob-frames) |
| `place`, `node`, `from_node`, `off` | `platform` (within 16 px of a surface) + `air` flag | 24.7 % of a jumper's air frames are called standing; no `from_node`, no `off` |
| `vx`, `vy` | `vx` only | `vy` missing |
| `facing`, `pose`, `opacity` | facing, the animation's name | the frame number and the opacity are dropped |
| `life` (spawning / alive / hit / dying) | live / hit / dying | no spawning |
| `seen`, `vis`, `cover` | `src`, a `vis` share from cover masks, states hidden / offscreen | no cover kind |
| `unseen_s`, `can_lo..can_hi` | `unseen`; no range | timers instead of a range |
| `born_t`, `born_how`, `hits`, `last_hit_*`, `seen_share` | `born` only | missing |
| Drops (id, item, class, place, born, from which mob, seen / cover) | none (the finder's sightings are not tracked) | all |
| Other players (id, place, seen / cover) | none (name tags only mask bodies) | all |
| Us (place by the one rule, `act`, `slots`, `buffs`, `cooldowns`) | `nav/selfstate.py` with its own tolerances; "slot holds something" for two keys | the rule, slots, buffs |
| Events | none (the brain's ledger decides "our kill") | all |
| Facts registry, dynamic values, the profile | config.py + client files + code | all |
| Blind frames (`cover = blind`) | the tracker is not called | to be said in the state |
| Stored tables | `ticks.jsonl` | all |
| The graph: chains from complete links, floors, one array placement, a seconds table | `nav/navmap.py` as audited in Part 1 | all (Part 1's numbers) |

## What was measured
Every tool below is in `tools/perc/track/` and runs from the kept replay (no GPU); outputs and by-eye crops are in
`F:\dev\maple-corpus\work\track-plan\`.

### 1. The mob tracker prototype (`proto_mobs.py`)
Version 5, every frame of the 13 sound captures (175,340 frames, 1,774 truth lives), today's tracker on the same
frames beside it (`proto_mobs.py --sound --today`; kept in `...\mobs\run_v5_sound.txt`):

| | today (`world.py`) | prototype | the model's target |
|---|---:|---:|---|
| mob-frames found (a track of its kind within 24 px) | 96.3 % | **98.7 %** | >= 99 % |
| the id kept across a cover (fair count), all 3,267 covers | 78.5 % | **93.4 %** | |
| ... cover of 0.1 s or less (1,760) | 92.4 % | 97.0 % | >= 95 % up to 1.5 s |
| ... 0.1-0.3 s (574) | 84.8 % | 96.5 % | |
| ... 0.3-0.6 s (390) | 77.5 % | 93.6 % | |
| ... 0.6-1.5 s (282) | 29.9 % | 79.4 % | (the truth is unproven here) |
| ... 1.5-4 s (261) | 24.6 % | 77.4 % | (the truth is unproven here) |
| one id for life (fair count) | 65.0 % | 74.8 % | >= 90 % |
| ... not counting a change beside another mob of its kind (within 60 px) | 81.4 % | **90.9 %** | |
| extra ids, all / not beside another mob | 2,232 / 564 | 1,022 / 200 | |
| the same by `score.py`'s nearest-track count: id kept / one id for life | 83.7 % / 64.5 % | 91.6 % / 71.0 % | |
| a death seen is noticed (p50 / p90) | 0.0 / 0.0 s | 0.0 / 0.0 s | p90 <= 0.05 s |
| seen track-frames with no truth mob within 40 px | - | 0 of ~650,000 | ghosts <= 0.3 % |
| a remembered mob, seen again, is next to its possible set | - | 99.32 % of 2,782 | >= 99 % |
| frames a track is remembered in view | - | 70,935 (0.4 a frame) | |
| ... that ended with the mob seen again / its places empty / the 4 s limit | - | 48.8 % / 6.8 % / 43.2 % | |

On the 30-minute design capture alone: found 98.9 % (today 96.8), id kept across a cover 94.6 % (80.2), one id for
life 73.2 % (66.8) and 91.2 % (84.3) not counting changes beside another mob, next to its set 99.87 %.
- **`score.py`'s "ghost" number does not grade memory**: it counts every remembered frame the truth has no mob
  for, and the truth has none wherever the fit saw none - 3.28 % for the prototype against 1.33 % today. What
  can be said instead is the last two rows: of the frames a track was remembered in view, half ended with the
  mob seen again next to where it could be; 43 % ran into the 4 s limit unchecked (measurement below).
- **How long a real cover lasts, by what was over the mob** (times a remembered mob was seen again, by seconds
  unseen: <= 0.3 / 0.3-1 / 1-2 / 2-4 | found gone | ended by the limit): an effect or anything unnamed 847 / 231 /
  66 / 59 | 50 | 102; another mob 370 / 53 / 32 / 21 | 6 | 37; out of view 228 / 190 / 83 / 89 | 3 | 384; the UI
  or front scenery 110 / 64 / 17 / 12 | 1 | 25; our body 148 / 6 / 0 / 3 | 5 | 9; a player 83 / 10 / 1 / 1 | 5 |
  9; a drop 31 / 13 / 1 / 2 | 0 | 9. Covers of 2-4 s that end with the mob seen again are real (207 in all), so
  the limit stays at 4 s for every kind.
- **One setting changed at a time** (`ablate.py`, the 12 shorter captures; columns: found %, id kept across a
  cover % - all / 0.6-1.5 s / 1.5-4 s, one id for life % - all / not beside another mob, extra ids):

| Setting | found | id kept | 0.6-1.5 s | 1.5-4 s | one id | (not beside) | extra ids |
|---|---:|---:|---:|---:|---:|---:|---:|
| the prototype | 98.4 | 91.7 | 71.2 | 63.0 | 77.3 | 90.4 | 320 |
| `world.py`'s timers instead of the possible set | 96.5 | 80.6 | 12.9 | 9.9 | 69.7 | 81.1 | 434 |
| mob speed as the v83 rule says (x 1) | 98.3 | 90.8 | 68.0 | 58.9 | 75.1 | 88.7 | 357 |
| limits of 2 s instead of 4 | 98.3 | 89.8 | 73.6 | 28.8 | 75.9 | 88.7 | 341 |
| limit of 1 s when drawn over | 98.4 | 88.8 | 60.0 | 28.8 | 74.3 | 87.1 | 353 |
| limit of 8 s when drawn over | 98.4 | 91.7 | 71.2 | 63.5 | 77.3 | 90.4 | 320 |
| a place is empty at 25 % of the body's core showing the scene (prototype: 40 %) | 98.3 | 89.5 | 64.8 | 61.6 | 76.7 | 89.1 | 348 |
| ... at 60 % | 98.4 | 93.1 | 77.6 | 64.4 | 78.6 | 91.7 | 301 |
| every sighting is a mob at once (no tentative stage) | 99.6 | 91.6 | 68.7 | 62.5 | 75.4 | 88.4 | 340 |
| `world.py`'s rule: no track until 60 % of the body is on screen | 96.9 | 91.9 | 71.1 | 64.3 | 77.7 | 90.9 | 309 |
| no look-alike feet / facing not in the pairing cost / first set twice as wide / no cost for a remembered track | 98.3-98.4 | 91.3-91.8 | 69.6-71.2 | 58.9-63.0 | 76.9-77.4 | 90.0-90.6 | 317-327 |

  So: the possible set is the gain (timers: one id for life 69.7 instead of 77.3); the 4 s limit holds the long
  covers; 8 s buys nothing; "empty at 60 %" is better on every identity number with 22 % more remembered frames
  - on all 13 captures (`...\mobs\run_v5_abs60.txt`): id kept across a cover 94.1 % against 93.4, one id for
  life not beside another mob 91.5 % against 90.9, but 244 tracks instead of 148 run unchecked into the 4 s
  limit. **The plan keeps 40 %**: under a point of identity does not pay for 65 % more memory nobody could
  check; the tentative stage costs 1.2 points of found and
  buys ids; the last row's four settings change nothing measurable (the look-alike feet matter for the feet and
  the placement - measurement 3 - not for the ids).

**What each version taught** (each was run, scored and looked at by eye):
1. *Version 1 (no limits, any sighting starts a track):* found 100 %, but tracks died on one-frame blinks of
   jumping mobs (the set was only looked for on the floor) and two "mobs" were remembered for 46 s and 7 s that
   were never mobs: slivers of a player at the screen edge. -> a track gets memory only once seen clearly; a
   jumper is looked for at every height of a hop.
2. *Version 2-3:* `score.py` counted 186 id changes where the fair count has 69: two mobs within 24 px. -> the fair
   count. A mob dropping off a cart was lost: its feet were "settled" onto the cart it fell past. -> the
   settle rules of measurement 3, and "standing" needs no vertical motion.
3. *Version 4:* the mob speed x 2 (measurement 4). By eye (`mem_sheet.py`, 6 "found gone" cases): 4 wrong - a
   mob falling past a platform's level was taken as standing on it, then every later reading was "under its
   floor" and refused, so its track ended while it was in plain view; a spawn fading in was called gone (too
   faint to differ from the scene). 1 was a duplicate: a track remembered 3.5 s "behind" a standing mob after
   its own mob had jumped away unpaired (the standing mob was seen by the fit all along, checked in the
   replay's rows). -> if every reading is under the floor, the floor is wrong: keep them; a mob last seen
   fading in is not checked for 0.4 s; the first frames of a jump must pair (version 5).
4. *Where the prototype and the truth disagree at a crossing of two mobs of one kind* (the 4-minute Line 1
   capture, 53 disagreements): in 31 the truth's mob turned round exactly at the crossing while the prototype's
   track kept walking (the truth took the other mob - it links by nearest place only), in 0 the track turned
   round, 22 cannot be told. Mobs walk through each other; the prototype's tracks keep their speed through the
   crossing (traced frame by frame: tracks 4 and 6, frames 672-693). **All 13 captures, version 5's 1,022 extra
   ids:** the truth changed mob 457, cannot be told 273, the track changed mob 7; the old track was still
   near but remembered while another took the mob 141; old track far away 83; the old track had ended 61 (36
   "its places show the scene", 24 of them in a jump; 11 a flyer whose set outgrew its reach; 12 a death
   seen; 1 the limit). So 565 extra ids are not the truth's own, at most 292 of them provably the prototype's.
5. *What the 4 s limit catches* (by eye, 6 of 12 cases on that capture): a mob that left by the screen edge
   whose possible set creeps back in behind another mob or under the system-message lines at the bottom right
   (text over the world for seconds); a track left "behind" a seen mob. None could be checked by any rule; all
   end after 4 s. Places that never match the scene model are not the cause (`scene_gaps.py`: 0.49 % of Line 1's
   judged area - the portal and a player who stood still all capture; no mob-time on them).
6. *One setting changed at a time* (`ablate.py`, 12 short captures, version 4): timers instead of the possible
   set: the id kept across a 0.6-1.5 s cover falls from 72.8 % to 13.6 %, one id for life from 75.3 to 68.0;
   limits of 2 s instead of 4: covers of 1.5-4 s fall from 64.4 to 28.8; "absent" at 60 % of the body's core
   instead of 40 %: better on every identity number (id kept 93.4 vs 91.9) with 18 % more remembered frames;
   the facing in the pairing cost: no difference; no tentative stage: found 99.8 % instead of 98.5 but 19 more
   extra ids and more remembered frames that never came back.

### 2. What may start a track (`births.py`, 13 sound captures, 1,774 truth lives)
- 129 of the 1,774 "lives" are 1-3 frames long (61 are one frame): mostly false or trivial sightings. Their first
  sighting shows less than 10 % of the kind's full size on 93 %; 62 % of them are fully on screen.
- A real mob's first sighting is as weak: of the 1,528 lives of 30+ frames, 46 % begin with less than 30 % of
  the body on screen and 49 % with less than 10 % of the full size seen (a mob walking into view).
- So one frame cannot tell them apart, but waiting can: a sighting with **>= 25 % of the full size seen and
  >= 30 % of the body on screen** comes at once for 597 lives, within 2 frames for 134, 3-5 for 339, 6-15 for
  297, later for 132, never for 29; only 5 of the 129 short lives ever show one.
- By eye, the two longest "remembered" tracks of the first prototype (46 s and 7 s) were both born from such a
  sliver at the screen edge: a player's helmet, and a player standing in a portal's light.

### 3. Feet and placement of mobs that jump (`proto_feet.py`, 918 hops: Bubbling 717, Evil Eye 125, Zombie Mushroom 57, Slime 19)
- A hop is a parabola: gravity 2,007 px/s^2 (median), apex 78 px, 0.56 s in the air - the same take-off speed as
  our own jump (555 px/s).
- Feet as the fit names them: parabola residual 2.94 px rms at the median, 28.5 % of hops within 1.5 px, 3,524
  jolts of 13 px or more between two frames. **Settled** (a look-alike pose's reading may never be under the
  floor the mob stands on or jumped from; of the readings left, the one that continues its motion wins):
  **0.94 px rms, 91.6 % of hops within 1.5 px, 489 jolts.** A first rule ("the reading nearest the last feet")
  was worse than doing nothing: at take-off a mob moves 9 px a frame, more than half of the 17 px between the
  two readings.
- Stand or air, graded on the hops (26,811 air frames) and on 555,561 standing frames:

| Rule | air frames called standing | standing frames called air |
|---|---:|---:|
| today: within 16 px of a surface | 24.66 % | 0.005 % |
| within 3 px, feet as the fit names them | 5.74 % | 0.088 % |
| within 3 px, settled feet | 1.06 % | 0.000 % |
| within 3 px, settled, 3 frames still before "standing" | 0.65 % | 0.500 % |
| **within 3 px, settled, and not moving up or down on this frame step** | **0.79 %** | **0.072 %** |

  81 air frames today are "standing" on a platform the mob neither left nor landed on (a jump passing the cart).

### 4. Mobs move at twice the v83 rule's speed (`proto_feet.py`, section "speed")
Speed over a quarter second while in a move pose, px/s:

| Kind | the v83 rule ((speed + 100) x 0.625; flyers x 1.25) | seen, median | p95 | p99 |
|---|---:|---:|---:|---:|
| Slime | 50.0 | 98.7 | 108.2 | 120.1 |
| Green Mushroom | 50.0 | 99.1 | 108.0 | 120.0 |
| Horny Mushroom | 50.0 | 98.8 | 113.2 | 120.4 |
| Evil Eye | 56.2 | 111.0 | 124.9 | 136.0 |
| Drake | 56.2 | 110.6 | 129.1 | 137.2 |
| Zombie Mushroom | 62.5 | 124.0 | 141.0 | 150.5 |
| Bubbling | 68.8 | 137.0 | 155.5 | 175.7 |
| Stirge (flies) | 100.0 | 156.2 | 179.6 | 185.6 |

The seven walkers sit at 1.97-1.99 x the rule; the flyer reaches its top slowly, its p99 is 1.86 x. The tracker
uses the kind's speed from the client files times a measured factor (2.0), kept as a fact with its source and
checked against what it sees (state_model.md section 5). `docs/game_rules.md` C1 gets a note.

### 4b. Always drawn over the world and not masked (`static_overlay.py`, the 4-minute Line 1 capture)
885 screen pixels are judged "world" on 90 %+ of frames and never show the scene: all in the play area's bottom
two rows (y 698-699, the HUD's top edge). Nothing else (the minimap window is masked whole). The places where a
remembered track could not be checked for seconds were scene-model gaps (an animated portal, a platform end's
decoration), not the UI.

### 5. The drops tracker (`proto_drops.py`: `run`, `numbers`, `sheets`; its docstring holds the rules)
Run from the kept replay alone (the finder's sightings + the two bitmaps). 13 sound captures, 48.8 minutes: **746
drops**; the 30-minute capture: 491 (268 bronze mesos, 180 etc, 41 use, 2 equip), 24 alive at once at the median,
43 at most.
- **The rules that worked:** a sighting belongs to a drop of the same item at the same map x whose bob says it is
  at that height now (the bob is a cosine of 5 px with a 2.000 s period: fitted per drop, a sighting is off it by
  0.2 px at the median, 1.0 px at p99.99); a drop is born only from a RESTING sighting and confirmed after
  0.25 s of sightings; two of one item at one x are told apart by their bobs.
- **Gone** is known three ways: the pickup hop is seen (the item rises 12 px); its place is looked at in the
  bitmaps and shows the scenery at every resting height; 130 s after its birth. Otherwise it is kept (out of view
  62 % of a drop's frames; on screen it is sighted on 91-92 %, covered 2-3 %, at the edge 2 %, under the UI 3 %).
- **How the 746 ended:** we took it 235, 130 s old 180, gone in view 123 (on the 30-minute capture 71 of 73
  were 118-130 s old: the expiry seen), found gone 53, the capture ended 155.
- **"We took it"** (30-minute capture, 191): the hop was seen on 185; the pickup key went down 0.13 s (p50; p90
  0.43, max 0.64) before the first frame without the drop; our feet were within 26 px sideways (p50 6) and 1 px
  off its foothold's height. No hop without a fitting press there - but 36 on the older captures, where the key
  was held: the rule must read "the key is down", not "pressed in the last 0.75 s".
- **Linking, by self-consistency:** no life with two items, none over 131 s, no drop declared gone and seen again;
  11 pairs of one item overlapping within 3 px (2 are two real drops seen in one frame; 9 of 746 = 1.2 % are
  open - a gate item); 1 life born where another ended under 1 s earlier.
- **Which mob it came from:** the die pose comes 1.39 s (p50; p5 1.09, p95 1.54) before the first resting
  sighting, the drop lands up to 107 px from the death (p50 47). Rule "a death 0.6-1.8 s before, within 110 px,
  on its level": exactly one death for **84.7 %** (87.2 % on the 30-minute capture), none 8.7 %, several 6.6 %.
  The other way: a drop follows 61 % of the deaths near us. By eye, 3 births of 3: right.
- **"Gone" is noticed** 0.05 s after the hop's last frame, 0.16 s after the place first shows empty.
- **Cost:** 0.14 ms a frame p50, 0.40 p90, 0.80 p99 in Python, its looks included (1 known drop a frame at the
  median is not reported by the finder and is looked at).

### 6. Events: casts, hits, kills, the HUD's steps (`proto_events.py`, the 30-minute capture; report kept in `...\track-plan\events\report_design.txt`)
The mob lives are the truth's chains here (the stand-in for tracks); our keys are `keys.jsonl`. (The sub-agent
that wrote the tool was cut off while reworking block 3's matching: the executor re-runs it before relying on a
number.)
- **The HUD's numbers are the client's own.** A cast takes its MP off at once (0.15 s after the key-down at the
  median, 0.04-0.26); what the server decides shows ~0.5 s after its cause: a kill's EXP 0.48 s after the key-down
  (0.33-0.63), a potion 0.46-0.51 s, a hurt 0.5 s after the touch began. A server value landing in between
  shows a cast's cost back and takes it off again (one cast, three steps: 30 such steps).
- **Every step has a cause:** MP 843 steps - casts 600, recovery 172 (+3 every 10.03 s), potions 55, the server's
  echoes 16; HP 381 - recovery 179 (+10 every 10.03 s), hurts 163, potions 22, Slash Blast's cost 13; EXP 396 -
  388 whole kills (28 each; 56 and 84 for two and three at once), 8 parts (a mob another player also hit).
- **`cast`:** of 835 `q` key-downs only **500 were casts** - 286 came while a swing was running, 39 without the
  MP, 4 on a rope, 6 unexplained; `e` 78 of 130 (12 inside its 2 s cooldown), `w` 10 of 30. Every cast has its MP
  step. So a key-down is not a cast: the MP step confirms it.
- **When the hit lands:** 0.50 s after the key-down for a stab, 0.563 s for a swing (two heaps, 110 and 99 casts;
  `attacks.json`'s trail start x 1.125 + ~0.05 s). The next cast starts 0.847 s after a stab's key-down, 0.870 s
  after a swing's - `brain/reach.py` computes 0.844 / 0.900: **the swing length is measured live to 0.03 s**.
- **`mob_hit` by us:** a hit or die pose that begins 0.45-0.72 s after a `q` key-down (`w` 0.45-0.95, `e`
  0.03-0.90) on a mob inside that skill's box in front of us. 467 such begins for `q` (median 0.554 s); per `q`
  cast one mob reacts on 410 of 503, none on 92, two on 1. The facing belief (the last left / right key) puts
  the mob in front on 547 of 550. Windows moved in time catch 2.3 of another's 343 events: **0.4 % of "by us" is
  chance**. A second witness: the mob's own name tag shows within 1 s after 41 of 69 of our hits and 1 of 170 of
  another's.
- **`mob_died` by us against the EXP:** of 579 deaths the window rule says us 398, another 181. Of the 385 EXP
  steps of 28, 361 have exactly one death beginning 0.33 s before to 0.07 s after them. Rule against EXP: "us"
  with no EXP step 1; a whole-EXP kill the window missed 8 (the die pose's begin was covered and counted back, or
  the mob stood outside the box) -> **the rule: by us when in our window and reach, or when it is the only death
  an EXP step of the mob's full EXP can pay for.**
- **Note (2026-11-24, the user): an EXP step's size is not fixed, so the second half of that rule holds only
  solo.** Cosmic's split (`server/life/Monster.java` 535-690; Classic World may differ in the numbers, not in the
  idea): solo, we get the mob's EXP x our share of its damage. In a party, every member on the map within level
  range gets `EXP x the party's damage share x (0.8 x own level / the party's total level, + 0.2 for the party's
  top damager) x (1 + 0.05 x members)` - a different step size, and **EXP for kills we never touched**. Holy
  Symbol, EXP events and coupons also change the step. The measurements here are solo footage. The user proposed
  (open, decided before step 5) to drop EXP from the live rule altogether - a kill seen by its die pose in our
  window, or "died, inferred" when its possible set empties in view right after our hit, else "lost" - and,
  Claude's recommendation, to keep EXP only as the offline grader on solo captures (step 5's gate, and step 9's
  live check against the EXP instead of the ledger, which is a window rule too). The cost, measured above: the 8
  whole-EXP kills the window misses (~2 %).
- **Hits per kill** (a measured-live fact): of 128 Bubblings seen from their fade-in with no one else's hit, 113
  died of one hit, 15 of two; a mob a `q` cast reached died at once on 92 %.
- **Knockback** by our `q` / `w` hit: 19 px after 0.3 s (18-20 middle half), no more after; the mob then faces
  us on 28 of 31. The hit pose lasts 0.55 s (the file's `hit1` length, not v83-HC's 0.248 s). Rush carries mobs
  along up to 145 px.
- **Who hurt us:** a mob's body was over ours within 0.75 s before 165 of 165 HP losses - one mob for 149, two
  or three for 16.
- **What breaks the rules:** 34 lives show a die pose in the middle of a life (the fit's pose noise: a death is
  taken back when a living pose follows); 157 of our 391 killing blows began covered (the begin is counted back
  from the die frame first seen); 14 of 591 casts have two candidate key-downs.

### 7. Other players from name tags (`proto_players.py`, the 30-minute capture; sheets in `...\track-plan\players\`)
- **What the tag list holds** (235,436 tags, 2 a frame at the median, 10 at most): ours 43.4 %, players 28.4 %,
  lines of the message log 14.7 % (fixed on the screen, right-aligned), **other players' pets 8.2 %** ("Brown
  Puppy", "White Bunny", "Snail" - a class Part 1 did not have), mobs' own tags 2.4 % (an 87 x 20 box under the
  feet of a mob we hit), short or cut pieces 2.1 %, the rest 0.7 %. No NPC on this map.
- **The rules:** a tag is followed in map coordinates; its class is voted over its life from what stands on
  it (a mob seen there, a body ~70 px high = a character, ~40 px = a pet, nothing = text). A tag's width is
  constant for one name: after a gap only a tag of the track's own width takes the id back.
- **Player tracks:** 308 in 30 minutes; a life lasts 2.7 s at the median (9 s at p90, 42 s at most): players
  pass through. 0 to 4 in view, at least one on 47.8 % of frames. Inside a life the tag is found on 87.5 % of
  frames (whole, alone and at its own width on 62.5 %); 1,253 gaps, all but one under 1 s.
- **By eye:** 20 random "player" moments: a player's tag on 20 of 20; on 4 the box is two tags side by side read
  as one, or a tag cut by a ladder. 20 random "pet" moments: 14 pets, 5 players, 1 log line. So no non-player
  was called a player, but a player beside its pet can be called a pet, and two tags side by side merge.
- **Identity:** two players within 40 px 46 times, ids swapped 0. With the 1 s cover 52 of the 308 tracks are the
  same width back near the same place within 10 s under a new id (2.1 s later at the median); a 0.3 s cover gives
  400 tracks and 141 such, a 2 s cover 279 and 29.
- **Placement** (47,182 whole sightings; feet = the tag's centre x, its top y - 1): standing 71.1 %, in the air
  10.1 %, on a rope 18.8 %; standing feet exactly on the surface on 97.8 %, within 1 px on 98.8 %; 227 sightings
  within 3 px of a surface while moving up or down (a jump passing it). Walking speed 156 px/s at the median
  (ours 152).
- **Cost:** 0.04 ms a frame p50, 0.09 p99 in Python.
- *Also:* our own tag is in the list on 1,179 frames where `FrameFacts.tag` is empty - 1.1 points of the 3.3 %
  of frames our position is missing today.

### 8. The hotkey reader (`proto_slots.py`: its docstring holds what the client draws on a slot, pixel-exact)
- **How a slot is drawn** (from the client's own pictures, checked against frames): the bar is `UI/QuickSlot.img`'s
  panel at frame (933, 588); a cell is 32 x 32 px; drawn in order: the keycap, the content (an item's `info/icon`,
  a key-binding action's picture such as "JUMP", a skill's icon), the amount in `UI/Basic.img ItemNo` digits from
  the cell's (0, 20), the key's label at (2, 2). The frame equals that composite exactly. Which key a cell is, is
  read from its label, never from its position.
- **The reader:** per cell the label, the digits, then the content looked up by the bytes of five rows no label
  or digit touches, then verified: keycap + content + digits + label must equal all 1,024 pixels. A read is
  exact or nothing; a cell is read again only when its pixels changed.
- **On the 30-minute capture, every frame:** all 8 keys exact on 110,082 of 110,082 frames (two keys on 110,081:
  one frame, 43357, something over the bar). Shift = the JUMP action, Ins = Pet Food x 100, Home and Ctrl empty,
  PgUp = The Green Relaxer (a chair, no amount), Del = Meat 200 -> 178, End = Lemon 130 -> 74, PgDn = Red Potion
  276 -> 287. **91 amount steps: 79 of -1 and 12 of +1** (Red Potions picked up). Each of the HUD's 79
  potion-sized rises (MP +150 x 55, HP +198 x 21, three others) has its -1 step on a key of that stat within
  0.5 s, and each step its rise: **79 of 79 both ways**; the step shows 82 ms after the HUD's rise (p50; p90
  150). Of the 88 potion presses in the key log, the 34 pressed alone each give exactly one step, 554 ms after
  the key-down (p50; p90 684); in 8 of 19 bursts of quick presses the game took fewer potions than presses. No
  amount changed and came straight back (0 misreads); 312 frames re-read from scratch: 0 differences.
- **Over 43 captures (271,811 frames):** an unreadable cell on 3,136 frames (1.15 %): the 10-14 frames of each
  map change's fade, one 14 s stretch on Cave of Evil Eye I (something over the bar), and two 2026-11-16 captures
  where two keys' labels never read (to be looked at by the executor). Seen on keys: JUMP, Red / Orange / Blue
  Potion, Meat, Lemon, Pet Food, The Green Relaxer. **No skill was on a key in any footage** - that path is built
  from the client's pictures only (a footage ask).
- **Cost:** 8 slots read from scratch 0.84 ms; one changed cell 55 us; an unchanged frame 5 us; 8.6 us a frame
  over 600 consecutive frames (8 cell reads).
- **Self-test** (every client picture - 5,059 items, skills and actions - drawn into a cell with an amount and
  a label, read back): 20 wrong, 4 of them pictures that are identical under the label or digits; 1 of 72 key
  labels wrong. The executor's gate is 0 wrong apart from true look-alikes.
- *Also learned:* Meat's file value is HP +160 and the HUD rises 198, a Red Potion 100 -> 124 (x 1.24 on HP
  items; Lemon's MP 150 -> 150): what a potion gives stays a measured fact, as the model says.

### 9. Cost (Python prototypes on the kept replay; one core, other jobs running - upper bounds, not gate numbers)
| Part | ms a frame p50 / p90 / p99 | Note |
|---|---|---|
| today: `world.py` + its looks (Line 1, the kept replay's own clock) | 0.7 / 2.0 / 2.7 | of 15.1 / 16.8 / 19.4 ms for the whole frame |
| mob prototype: sightings + pairing | 0.44 / 1.67 / 3.21 | plain Python loops over tracks x sightings x readings |
| mob prototype: checking the unseen tracks | 0.73 / 2.3 / 5.1 | numpy on the CPU bitmaps; live it is one gather on the GPU |
| drops prototype (its looks included) | 0.14 / 0.40 / 0.80 | |
| players prototype | 0.04 / 0.06 / 0.09 | |
| hotkey reader | 0.009 average; 0.84 for a full read of 8 slots | re-reads a cell only when its pixels changed |
| placement of 20 things (Part 1) | 0.016 (median map) - 0.062 (largest) | one array call |
The parts that are new work every frame (drops, players, slots, placement) sum to ~0.2 ms; the mob part must be
written with arrays, not loops, to stay at today's 0.7 ms.

---

## The design
**1. One tracker, one state, the same code live and from a recording.** A new package `maplebrain/track/`;
nothing in it knows the brain. Per frame it gets perception's facts (`FrameFacts`: the fit's sightings, the drop
finder's, the name tags, our tag, the HUD's numbers, the slots, the camera), our key events since the last frame,
and an *evidence* handle; it returns the state of `docs/state_model.md` (the frame, us, mobs, drops, players)
and the events since the last frame. Fixed inputs: the graph and the facts registry. A frame without a camera
changes nothing (`cover = blind`).

**2. Evidence: "does this place show the scene?"** One interface, two sources: the kept replay's two bitmaps
(CPU) and the fit's own tensors on the GPU (frame, expected scene, valid: one gather for every place asked
this frame, one transfer back). So the real tracker is graded on the kept replay without re-making it, and the
GPU source is proved equal to the bitmap source on fresh footage.

**3. Placement: the one rule of the model, with motion.** `stand` = the feet within 3 px of a surface and the
step since the last frame within 1 px up or down (+ 0.9 x the sideways step, the steepest slope walked); else
`air` (or `fly`; `rope` for us and players). The node changes only on `stand`. Look-alike poses: every reading
of the picture is kept; one under the floor the mob stands on or jumped from is dropped (unless all are), and
of the rest the reading that continues its motion wins (measurement 3).

**4. Mobs** (measurement 1; the prototype's rules and constants are the reference):
- *Pairing* sightings with tracks: one cost over all tracks - the distance to where the track's motion puts it,
  half the vertical distance, 12 px for another kind, 8 px for a turned facing, 3 px for a track not seen on the
  last frame; nearest first. A track seen on the last frame can be off by 6 px + 1.5 x its speed bound x the
  time; a remembered track takes a sighting within half a body + 6 px of its possible set.
- *Tentative until seen clearly:* a new track is a mob (a `mob_new` event, memory) once one sighting shows 25 %
  of its kind's full size with 30 % of its body on screen, or after 0.5 s of sightings; unseen 0.3 s before
  that: dropped without a trace.
- *Memory:* a confirmed track that is not seen keeps its possible set - places every 4 px along its node,
  starting one knockback (35 px) either side, widening at its kind's speed (the files' x 2.0), tested every
  frame: a place is empty when 40 % of the body's core shows the scene (a jumper: at every height of a hop). A
  flyer's set is the same in two directions, within 160 px. The set empty: gone at once. Nothing can be checked
  (out of view, behind the UI, drawn over): kept 4 s since it was last seen, then gone - one limit for all.
  A mob last seen fading in is not checked for 0.4 s. `can_lo..can_hi` = the set's ends; `cover` = what is over
  the nearest place left (us, a player, a mob, a drop, the UI, the edge, an effect).
- *Death:* a die pose = dying, gone when `die1` ends; a living pose within 0.2 s takes it back. *Kind:* voted,
  a clear sighting counts for more.
- *Not kept from today:* `lose_s`, `fight_s`, `covered_s`, `hidden_s`, the cover masks, the 60 %-on-screen rule,
  the duplicate merge. Whether `Fitter.look` stays (a look that sees the mob = a sighting) is decided in step
  3 by its numbers and its milliseconds.

**5. Drops** (measurement 5): same item, same x, on its own bob; born from a resting sighting, confirmed after
0.25 s; gone by the hop seen, by its place shown empty, or at 130 s; "we took it" = the hop or the empty place
with our pickup key down and our feet within reach; `from_mob` = the one death 0.6-1.8 s before within 110 px
on its level.

**6. Other players** (measurement 7): the tag list sorted into ours, log lines, mobs' own tags, pets, players;
a player = a tag followed in map coordinates with its width as its name; two tags side by side are split by the
widths already known; kept through a 2 s cover in view (the user, 2026-11-24, question 5); placed by rule 3.
Pets are sorted out, not tracked (question 4: may be added later).

**7. Us:** the feet from our tag (taken from the tag list when the reader's own tag is missing: 1,179 frames),
placed by rule 3 with the rope; `facing` = the last left / right key; `act` from the place, the keys and the MP
step; the HUD's numbers; the 8 slots from the hotkey reader (measurement 8). `buffs` and `cooldowns` stay in the state, empty: the
warrior has none (the user, 2026-11-24, question 6), so they are not built now; Rush's 2 s (12 presses inside it
did nothing) is its action running, a "swing running" for design 8.

**8. Events** (measurement 6): a cast = a skill key's key-down with no swing running, confirmed by the MP step;
`mob_hit` / `mob_died` by us = the pose begins in that cast's landing window with the mob in the skill's box, a
death also when it is the only one an EXP step of the mob's full EXP can pay for; every HUD step gets its cause;
drop and player events from 5 and 6; a mob's own name tag as a second witness of our hit.

**9. Facts and dynamic values** (state_model.md 5-6): one registry; the profile file (keys -> skills and
levels, the weapon); Skill.img built into `assets/mcw`; measured live: our walk / jump / climb, the swing length
(the gap between casts: 0.85-0.87 s), what a potion gives, hits per kill, each mob kind's speed against the
files' (the factor 2.0 lives here, with its source). **Observed beats the rules** (the user, 2026-11-24,
question 3): where a measured value and the v83 rule clash, the measured one is used and the rule's number is
kept beside it as its source. The HP items' x 1.24 = the warrior's passive healing-bonus skill (question 7).

**10. Stored:** the tables of state_model.md 8, written by the recorder and the hunt, readable with a field
added later.

---

## Steps (one executor session each, Opus; branch `tracker-build` off `dev`, after `tracker-plan` is merged into `dev`)
Every step: its area's pytest green, the `bot speed` line reported, the gate's numbers written under the step in
this file. Nothing reads the new state before step 9: `world.py` and the brain stay as they are until then.
"From the kept replay" = the real `maplebrain/track` code run over a capture's kept replay with the bitmap
evidence (a tool step 3 builds), graded by `score.py` and the fair counts of `proto_mobs.py`. "Within tolerance"
= a percentage within 0.3 points of the prototype's, a count within 1 %, and never below today's. The prototypes
in `tools/perc/track/` are the reference: port their rules and constants, do not redesign them.

| # | What | Gate (on footage) | Could run beside |
|---|---|---|---|
| **0** | **The user:** the footage and the answers of the last two sections | filed in the bank; answers written here | - |
| **1** | **Label sets, by eye** (no code in `maplebrain/`; labels in the bank's `labels\`, picked from the prototypes' output so every class is in them): L1 200 frames - us and every mob: stand / air / rope and the node; L2 100 covered mobs - what covers them; L3 50 births - how born; L4 100 hit-pose begins - by us or not (the swing seen); L5 200 frames - every name tag's class, each player's node; L6 50 drops - the mob it came from; L7 100 frames - the 8 slots' item and amount; L8 40 remembered mobs - there / not there / cannot tell | each set readable by `tools/perc/label_eval.py`; 10 % of each labelled twice: the two agree on >= 95 % | 2, 7 |
| **2** | **The graph and the placement** (`track/graph.py`; `tools/model/` is the reference): chains from complete links, floors, the nodes as arrays, rule 3 as one array call for every thing, the seconds table, the edges and the table rebuilt on a worker thread | 364 maps build; 10,873 chains, 39 maps differ from `navmap`, ids unchanged on the other 325; the 19 level joints are one floor each; the node = `platform_at`'s on 72,800 of 72,800 test points; 20 things placed in <= 20 us (median map), <= 70 us (the largest); on `proto_feet.py`'s hops: air frames called standing <= 0.8 %, standing called air <= 0.2 %; the table = `route()`'s seconds on 1,000 random pairs, built in <= 5 ms on Line 1; a rebuild does not block a frame (a test) | 1, 7 |
| **3** | **Mobs, in shadow** (`track/kinds.py`, `evidence.py`, `mobs.py`, the mob records of `state.py`; the Perceiver calls it beside `world.py`; the replay tool): design 2-4 | *From the kept replay, 13 sound captures:* measurement 1's table within tolerance - found >= 98.4 %, id kept across a cover >= 93.1 % (by length >= 96.7 / 96.2 / 93.3 / 79.1 / 77.1), one id for life not beside another mob >= 90.6 %, extra ids <= 1,032, "the track changed mob" <= 10, next to its set >= 99.0 %, a death seen noticed p90 <= 0.05 s, no seen track-frame without a truth mob; measurement 3's feet: hops within 1.5 px rms >= 91 %, jolts <= 500. *Labels:* L1 mobs: stand / air >= 99 %, the node >= 99.5 % of standing mobs; L2 >= 90 %, L3 >= 95 %, both counted on the agreed cases only (L2 21, L3 22: `"agreed": true` in the bank's files; step 1, try 3); L8: reported. *Live, on `20261120_235747_1#0` (Line 1, 4.2 min) with a new kept replay of it on today's scene build in its own folder (stop rule 5):* the GPU evidence = the bitmaps' on >= 99.9 % of the places asked; the shadow rows = that capture's replay rows on >= 99.5 % of track-frames; the tracker's ms p50 <= 1.0, p90 <= 2.5 (today's `world` + looks: 0.7 / 2.0), the whole frame's p50 not above today's + 0.3; `gate.py` SAME | - (the GPU, and a speed number) |
| **4a** | **Drops** (`track/drops.py`): design 5; the finder (`perception/drops.py`) is not changed | from the kept replay, measurement 5 within tolerance: 746 drops, 0 lives with two items or over 131 s, 0 "gone" then seen again, pairs of one item within 3 px <= 9 and each looked at, exactly one death for >= 84.4 % of drops, "we took it" with the key down: no hop without it on any of the 13; L6 >= 90 %; PLAN-loot's gates still met; ms p50 <= 0.2 | 4b |
| **4b** | **Other players and us** (`track/players.py`, `us.py`): design 6-7 | L5: players found >= 95 %, non-players called players <= 1 %, a pet called a player or a player called a pet <= 5 %, the node on >= 95 % of standing players; the 2 s players' cover (question 5): the same player back under a new number on <= 29 of the 30-minute capture's 308 tracks (within 1 %); L1 us: >= 99 %; every stuck case `nav/selfstate.py`'s docstring lists is a test; us against `SelfState` on the 30-minute capture: the same place on >= 99 % of frames, every difference listed; our feet known on >= 97.5 % of frames (today 96.7; the tag list gives 1.1 points); ms p50 <= 0.1 | 4a |
| **5** | **Events** (`track/events.py`; needs 3-4): design 8 | 30-minute capture, from the kept replay and its keys: casts 500 / 78 / 10 (q / e / w) within 1 %; every HUD step has a cause; "by us" by chance <= 1 % (windows moved in time); kills against EXP: "us" with no EXP step <= 1 %, whole-EXP kills missed <= 2 %; L4 >= 95 %; the swing length measured live within 0.03 s of 0.85 / 0.87 | 6 |
| **6** | **Facts, the profile, Skill.img** (`track/facts.py`, `gamedata.py`, the profile file; `kinds.py` reads the registry): design 9 | every fact of state_model.md 5 is in the registry with its source; a profile edit is read without a restart and gives a `fact` event (a test); measured live on the 30-minute capture: walk 152-157 px/s, climb 121-127, the swing 0.85-0.87 s, potions +150 / +198, each kind's speed factor 1.95-2.05, hits per kill; a changed jump height rebuilds the edges on the worker (a test) | 5, 8 |
| **7** | **The hotkey reader** (`perception/slots.py`, FrameFacts `slots`, the picture pack built by `assets build`; tracked in `us`): design 7, measurement 8 | the self-test: 0 wrong apart from pictures that are identical under the label or digits; the 30-minute capture, every frame: all 8 keys exact on >= 99.99 % of frames, 79 of 79 steps both ways, 0 misreads; the 43 captures: an unreadable cell only in a map change's fade or under a window, each stretch listed; L7: 100 % of frames right where the bar is readable or a reading is held, never a wrong item (the user, 2026-11-24; was "100 of 100"); the new footage (`20261124_093410_1#0`): a skill on a key read, an amount 0 read, a tooltip over a slot "unreadable" or read right, never a wrong item (no window over the bar in it: skipped by the user; the covered-cell case is the 43 captures' fades and "something over the bar"); ms <= 0.02 a frame on average, <= 1 for a full read | 1, 2 (its speed line alone) |
| **8** | **The stored tables** (`state.py`'s writer and reader; the recorder and the hunt write them; a converter from the kept replay) | the 30-minute capture: <= 60 MB an hour raw, <= 12 packed (prototype 48 / 9); written and read back equal; a file without a newer column still reads (a test); <= 0.05 ms a frame | 6 |
| **9** | **The switch** (the brain reads the state through one adapter; `world.py`, its tests and the looks it alone needs go; `gate.py` and the bench re-based in that commit; the viewer of PLAN-livemap reads the state) | pytest green; the bench not slower than the baseline; **the user's live check:** a 3-minute hunt on Line 1 - kills counted by the events within 2 of the brain's ledger, no swing at a mob that is only remembered | - (the game) |

### Step 1, 2026-11-24: the sets made, the gate MISSED on 5 of 8 (stopped)
Tool: `tools/perc/track/label_sets.py` (`mobs`, `pick`, `write`, `agree`, `check`; its docstring holds every set's
fields). Cases picked from proto_mobs v5 (re-run with its rows kept), proto_events, proto_players (2 s cover),
proto_drops, proto_slots, balanced over the classes and the captures; sheets in
`F:\dev\maple-corpus\work\track-plan\labels\L*\`; the judgments (in git) in `tools/perc/track/judged/` (the
labellers' brief: `BRIEF.md`); the labels in `CORPUS\labels\SESSION#K\labels\L*.json`, 111 files. Every label was
made by a Claude labeller looking at the sheets; the second look was another labeller who saw only its own
re-ordered, re-numbered sheets (`b_*.png`), never the first judgments.

| Set | Cases (captures) | Items judged | What they hold | "?" | Second look: items, agree |
|---|---|---|---|---:|---|
| L1 | 200 frames (13) | 1,019 + 48 mobs added | fly 174, air 92, the rest stand / rope by node | 70 | 132, **87.9 %** |
| L2 | 100 (13) | 100 | edge 22, ui 16, none 14, us 14, effect 12, player 8, scenery 4, mob 4, gone 3 | 3 | 10, **90.0 %** |
| L3 | 50 (13) | 50 | view 16, fade 14, uncover 7, entry 4, dying 2, notmob 2 | 5 | 5, **60.0 %** |
| L4 | 100 (2) | 100 | us 49, other 25 | 26 | 10, **90.0 %** |
| L5 | 200 frames (2) | 662 tags | player 236, ours 168, log 108, pet 82, mob 38, none 23, text 1 | 6 | 74, 98.6 % |
| L6 | 50 (12) | 50 | A 31, B 3, none 12 | 4 | 5, **80.0 %** |
| L7 | 100 (43) | 800 slots | | 15 | 80, 97.5 % |
| L8 | 40 (13) | 40 | yes 20, no 6 | 14 | 4, 100 % |

Gate part 1 met: every one of the 111 files is read by `label_eval.py` (exit 0; L1 on the 30-minute capture grades
today's tracker at 92.1 % of 63 mobs). Gate part 2 (agree >= 95 %) missed on L1, L2, L3, L4, L6. Why, from the
disagreements looked at by eye:
- **L1, the sheets:** a platform's id is drawn only at its left end, so on a long slope the two looks read
  different lines (case 119: s266 / s15); the brief did not say where a mob fading in stands (case 112: two
  see-through Bubblings a few px over their platform, "s79" / "a"); 4 of the 16 differences are "?" against an
  answer. Labellers also met platforms whose id was never on the sheet (the left end off screen vertically).
- **L4:** frames 0.2 s apart do not show the swing land; 26 of 100 "who" are "?" - the set is weak as it is.
- **L2 / L3 / L6 / L8: 4-10 items each** - one difference is 10-25 points; 3 of the 5 differences there are "?"
  against an answer, 2 are real (L3 view / uncover, L6 A / B: two deaths at one place).
Found on the way: L2 - 14 of 100 "covered" mobs are in plain view (the fit missed a visible mob), 22 at the screen's
edge; L8 - one remembered mob's range is on the platform under the mob (case 21); L3 - 5 births are a mob already
in plain view picked up late; L7 - the bar is drawn elsewhere on 2 frames (a menu row under it) and the digits 3 / 8
are told apart only at the game's pixel scale; L5 - the tag finder misses tags with a medal ("Killer") and merges a
player's and a pet's tag into one box.

### Step 1, try 2 (2026-11-24): the gate MET on L4, L5, L6, L7, L8; MISSED again on L1, L2, L3 (stopped, no third try)
What changed (the fixes asked by the user; `label_sets.py redo`, commits d889b30 ..): **L1** the same 200 cases on
new sheets - a line's id printed along every piece of it, crops 85 px over the feet and 45 under - labelled again
from nothing (the first try's judgments are in `judged/try1/`, never shown); **L4** the same 100 cases, one sheet
each: every frame from the skill key's key-down to 1.0 s after it, the key-down, the landing window (measurement 6:
`proto_events.LAND`) and the pose's begin drawn on a bar, the mob marked on every frame; labelled again; **L2, L3,
L6, L8** a second look of 30 cases each (new order, new numbers); L3 and L6 also a new first look, because the
brief's rules for them changed (`BRIEF.md`, "The sets' rules": L3 a first-fit order with `view` = the place outside
the picture just before BORN, `uncover` = inside it; L6 `A|B`; L1 a see-through mob placed by its feet like a solid
one); L2 and L8 keep the first try's first look. **The count (the user):** agreement on the items both looks
answered; a "?" against an answer apart. Every look blind: its own sheets, never another look's judgments.

| Set | Try 1 as reported | Try 1, recounted | Try 2: cases twice | **Both answered: agree** | "?" vs an answer | "?" in both | First look's "?" | Gate |
|---|---|---|---:|---|---:|---:|---|---|
| L1 | 87.9 % | 107 / 117 = 91.5 % | 20 | **103 / 109 = 94.5 %** | 2 | 1 | 48 of 1,219 = 3.9 % | **missed** |
| L2 | 90.0 % | 9 / 9 | 30 | **21 / 27 = 77.8 %** | 2 | 1 | 3 of 100 | **missed** |
| L3 | 60.0 % | 3 / 4 | 30 | **22 / 25 = 88.0 %** | 4 | 1 | 6 of 50 = 12 % | **missed** |
| L4 | 90.0 % | 6 / 6 | 10 | **7 / 7 = 100 %** | 2 | 1 | **22 of 100** (try 1: 26) | met |
| L5 (kept) | 98.6 % | 73 / 73 | 20 | 73 / 73 = 100 % | 1 | 0 | 6 of 662 | met |
| L6 | 80.0 % | 4 / 5 | 30 | **21 / 22 = 95.5 %** | 5 | 3 | 12 of 50 = 24 % | met |
| L7 (kept) | 97.5 % | 76 / 76 | 10 | 76 / 76 = 100 % | 2 | 2 | 15 of 800 | met |
| L8 | 100 % | 2 / 2 | 30 | **21 / 21 = 100 %** | 2 | 7 | 14 of 40 = 35 % | met |

("player ?" in L5 counts as a "?": the class told, the place not.) Gate part 1 met again: the new L1, L3, L4, L6
files are read by `label_eval.py` (exit 0 on every capture). The labels: L1 now 661 standing / 174 flying / 91 air /
44 rope / 49 "?" / 54 mobs added; L4 us 47 / other 31 / "?" 22.
**L4 meets the gate on 7 answered items**: 10 cases twice is what the plan's 10 % gives; 3 of the 10 have a "?".
**The disagreements of the missed sets, looked at by eye:**
- **L1 (6; 104 of 109 would have met):** 3 are **us at a rope** on one frame - climbing at the rope's top where it
  meets the platform (case 17, "r2" / "s269"), a jump pose with the rope behind us (83, 107: "a" / "r11", "a" / "r5"):
  a single frame does not tell on the rope from jumping past or stepping off it; 1 is a misread (72: we are ~36 px
  over line 101, "s101" / "a"); 2 are a mob one look added and the other did not (69, 143). The 2 "?" against an
  answer: two marks 3 px apart on a mushroom with a Stirge over it (83). The new sheets removed the try-1 causes (no
  difference is a line read wrong).
- **L2 (6):** 3 are **a mob in plain view with scenery drawn over part of it** - Ellinia's light ray over the cap (13),
  bones (87), a ladder post (88): "scenery" / "none" - the set does not say whether partly hidden counts; 2 are
  **several things over the mob at once** with no rule which one counts (60 a pet + a mob: "player" / "mob"; 17 a
  pet + coins: "player" / "drop"); 1 is **the possible set drawn away from the mob** (91: a Stirge in plain view, its
  yellow range on the platform under it in the padding: "edge" / "none").
- **L3 (3):** 2 are **a hit pose or a death at BORN** - a Bubbling in view from -0.3 s, squashed at BORN (30:
  "uncover" / "dying"), a see-through outline under our skill's effect (39: "dying" / "uncover"); 1 is **which frame
  is "just before BORN"** - the place in the padding at -0.6 / -0.3 s, under the HUD at -0.1 s (3: "fade" /
  "uncover"; rule 5 would say "view"). 2 of the 4 "?" against an answer are births on a capture's first frame (n 0):
  "entry" asks for loading frames such a case cannot have.
**The user's decision on L2 and L3 (2026-11-24): no third try.** They grade descriptive fields (`cover`, `born_how`),
so their truth is the cases both looks agree on: a case the looks disagree on, a "?" against an answer, a "?" in
both, or a case looked at once is left out of every later gate that uses the set (step 3: L2 >= 90 %, L3 >= 95 % on
these only). The user chose the cases looked at twice and agreed, no further second look: **L2 keeps 21 of 100, L3
keeps 22 of 50**, marked `"agreed": true` (and `"looks": 2`) in the bank's L2.json / L3.json; the definition gaps
found are in `BRIEF.md`, "Open definition gaps", for a later set.
Found on the way (no fix here): **L6** - the sheets letter deaths from proto_drops' list, which misses some: 5 "?"
against "none" are drops from a death with no letter (one look said "?", the other "none"); **L4** - the pose's
begin is sometimes 0.1-0.2 s after the mob is seen to change (cases 0, 8 of both looks), and a Rush (`e`) hit shows
the flinch after the push; on several "other" strips we are off the picture; **L8** - a range that lies in the
padding or under the chat is "?" by both looks (7 of 30); **L1** - see-through Bubblings / Zombie Mushrooms float
11-23 px over their line (cases 12, 47, 112: one labeller "a", one "?"), and the finder misses many flying mobs (54
added, many Stirges); **L3** - "no frame" before a birth at n 16361 (a hole in the capture) and a crop that is not
the BORN scene (case 46: the camera lost?).

### Step 1, try 3 (2026-11-24): L1's cases near a rope on strips - the gate MET (L1 97.2 %)
The user: the tracker places us by motion over frames, a labeller saw one frame - so us at a rope's top, or a jump
pose with a rope behind us, was read two ways. `label_sets.py ropes` (set **L1R**): every L1 case where we or a mob
stand within 20 px of a rope / ladder (sideways; between its top and its bottom + 20 px) - **75 of the 200 cases, 85
things** (us on 58 of them, mobs 27) - on its try-2 sheet plus, per such thing, a strip of the frames
0.2 s before to 0.2 s after (every 3rd, 9 frames, the case's frame red, the lines' and ropes' ids along them).
Both looks labelled those cases again, blind, on their own re-ordered, re-numbered sheets (the first look all 75;
the second look the 9 of them in L1's second-look sample of 20); the other 125 cases keep try 2's labels
(`judged("L1")` takes L1R's judgments for the rope cases). BRIEF.md got the rule for a strip.

| L1 | Both answered: agree | "?" vs an answer | "?" in both |
|---|---|---:|---:|
| try 2, all 20 cases | 103 / 109 = 94.5 % | 2 | 1 |
| **try 3, all 20 cases** | **105 / 108 = 97.2 %** (gate >= 95 %: met) | 3 | 1 |
| the 9 rope cases, try 2 | 50 / 55 = 90.9 % | 2 | - |
| the 9 rope cases, try 3 | 52 / 54 = 96.3 % | 3 | - |

The 4 "us" differences of try 2 (cases 17, 72, 83, 107) are all gone. The 3 left are a mob one look added and the
other did not (cases 83, 143, 192: a Stirge over a mushroom, mobs at the edge); the 3 "?" against an answer: two
marks 3 px apart on a mushroom with a Stirge over it (83), us mid-jump over the HUD with no line under us (69).
The labels in the bank rewritten (every file read by `label_eval.py`, exit 0); the labellers kept `a` for a jump onto
or off a rope and `r<id>` once the climbing pose shows.

### Step 7, 2026-11-24: the hotkey reader built; the gate MET (L7's gate reworded by the user)
Branch `tracker-build-slots` (worktree `.claude\worktrees\slots`, off `tracker-build`). Built: `perception/slots.py`
(proto_slots ported, its docstring = what the client draws), `tools/cwdata/export_slots.ps1` (called by
`export.ps1`, writes `export\Slots\`) -> `assets build` -> `assets/mcw/slots` (5,059 pictures: 5,313 items, 300
skill pictures, 47 actions; 71 key labels), FrameFacts v7 `slots` = every key's `[kind, id, amount]` or None (the
Perceiver's HUD thread; the old two-key "holds something" stays only behind `obs.hp_potions`, the brain unchanged),
`track/us.py` = `Us` with its slots part (the last exact reading held while unreadable; a `slot` event per change, `d`
= the amount's step). Gate tool: `tools/perc/track/slots_gate.py` (`selftest`, `run --all`, `stretches`, `l7`,
`bench`); outputs in `F:\dev\maple-corpus\work\track-plan\slots7\`. `tests/test_slots.py`: 10 tests on bar crops.
**Fixed on the way (not in the prototype):** my first port took a cell's label from any read; the cursor over "hift"
leaves "S" fitting the Shift cell, and as the next read's hint that kept 8 cells unreadable to the footage's end. A
label is now taken only from an exact read (the prototype's rule); a test proves it (fails without the fix).

| Gate | Number | |
|---|---|---|
| Self-test, 5,059 pictures with an amount and a label, 2-row and 3-row bar | 0 wrong (4 / 5 with a look-alike under the label or digits); 71 labels on an empty keycap: 0 wrong | met. The prototype's 20 "wrong" were all one thing: "O" (key 24) is drawn with "0"'s picture - one label, two keys (`lab_also`) |
| 30-minute capture, every frame (110,082) | all 8 keys exact on >= 99.9991 % (home and pageup unreadable on 1 frame: the cursor); 79 of 79 rises with their step and 79 of 79 steps with their rise; 0 misreads (no amount back within 2 s, 0 content changes); the 34 lone presses each one step, 554 ms p50; 312 audit frames read from scratch: 0 differences | met - the report equals the prototype's line for line |
| 44 captures (the 43 + the new footage), 289,000 frames | 45 stretches with an unreadable cell, each listed (`slots7\stretches.txt`, sheets `stretches_*.png`): **35 map-change fades** (the whole bar, signature 0 %, 1-18 frames, every one at a stay's first or last frames); **the cursor over a cell** 5 (1-8 frames each, and the new footage's 9 s of cursor + tooltips + an item dragged); **a window over the bar** 3 (Ant Tunnel IV 2026-11-16: the game menu 4 + 21 frames, an item's tooltip with the cursor resting on Ins 58 s - the prototype's "two keys never read"; Cave of Evil Eye I: an NPC dialog's picture 22 s); **not the native window** 1 (Dark Cave 2026-11-16 from frame 357: the game drawn smaller, the desktop around it - the reader rightly finds no bar). Audit 0 differences on all 44; no content change on any; no flick | met - the cursor over a cell counts as "something over the bar" (the user, 2026-11-24); the non-native window is "not the bar" |
| L7, 100 frames (800 keys) | **97 of 100 frames** every labelled key right: 637 read exactly on the frame, 130 held (the frame not readable - a fade, the cursor, a window - and the state holds the label's reading); **0 wrong**; the 15 "?" keys: the reader says unreadable on all 15. The 3 others are not readable and nothing was read before them: Ant Tunnel IV's first frame under the game menu (2 keys); Deep Ant Tunnel II's and L Forest III's first frame, in the fade, after a hold-out stay (not opened) | **met** on the gate as the user reworded it (2026-11-24): 97 of 97 frames right where the bar is readable or a reading is held, + 3 correct "unreadable" answers; never a wrong item ("100 of 100" as first written: 97) |
| The new footage (`20261124_093410_1#0`) | a skill on a key read: Power Strike (1001001) on Ctrl, 36 presses; an amount 0 read: Orange Potion 1 -> 0 on Ins; tooltips and the cursor: unreadable, never another item; 13 steps of -1, each 474-684 ms after its key's press, none outside a press | met |
| ms (quiet machine, Ultimate Performance, the game open; `slots_gate.py bench`, twice) | 3,000 consecutive frames of the 30-minute capture: **0.015 / 0.017 ms a frame on average** (p50 0.009 / 0.021, p99 0.03, max 0.97 - one cell read); **a full read of the 8 keys 0.80 / 0.92 ms** (a third run 0.74); one changed cell 32-62 us; an unchanged frame 6-8 us; the pack's load + table 82-90 ms once. Worst case, the new footage's 15 s of cursor and tooltips (894 frames, 582 cell reads): 0.039 ms on average. **bot speed** (`tools/perf/bench.py` in the main folder after the merge - the full path, fit included; the worktree has no `assets/scene` - A/B in one process, the reader on / off, 3 runs each): tick 14.9 / 14.5 / 14.7 ms on, 15.0 / 14.8 / 14.8 off - no change (hud 0.1 ms); pytest's line: 69.0 fps, 14.5 ms, "21 % faster" than the 2026-11-16 baseline (18.4 ms) - not re-based (not a speed change) | met (<= 0.02, <= 1) |

Not in the gate, noted: the prototype's stored bar signature on frame 43357 of the 30-minute capture (65 %) is 100 % in
this run and in a re-read with either pack - its run read that frame differently; nothing depends on it.

### Step 2 - built 2026-11-24 (branch `tracker-build-graph`): gate MET; one reading for the user (the rebuild)
Built: `maplebrain/track/graph.py` (its docstring holds the rules) + `tests/test_track_graph.py` (23 tests);
`config.Track` (stand_tol 3, stand_step 1, stand_slope 0.9, rope_tol 7 = today's SelfTracker value for our exact
tag). The gate tools: `tools/model/nav_audit.py graph` (new), `tools/perc/track/proto_feet.py` (a row for the real
placement). nav/navmap.py is not changed: the edges are its own `_find_links` run over the graph's nodes, the table
is its own `route()` search.
- **Nodes:** `chains_fixed.py`'s rule; the chain lists equal the reference tool's on all 364 maps (a test).
- **Placement:** the rule of design 3 for n things in one call (stand, rope for climbers, air / fly; `from_node`
  changes only on stand or rope - proto_mobs's track node); no +-8 / 16 px retry at the feet's x (that is for the
  minimap's coarse x). A test checks the fast call against a plain over-every-chain version of the rule on 7,500
  random things on 5 real maps (ends, joints, slopes, ropes, last nodes).
- **The seconds table:** `seconds[a, b]` = route()'s seconds **from the middle of node a** (a choice made here:
  route() needs a start; the middle errs by at most half the node's width), `arrive[a, b]` = where that way lands.
  It is route()'s own search run to the end from each node: route() stops when it pops its goal, and everything
  popped before is the same, so a row holds route()'s answer for every goal exactly.

| Gate | Result |
|---|---|
| 364 maps build | **364 of 364**: with the edges and the table 0.12 s p50, 0.64 p90, 5.2 max (nodes, floors and placement alone 0.01 s p90); the edges are navmap's own (`NavMap.from_json`'s links) on **300 of 300** maps with navmap's nodes; the table 2.4 ms p50, 26 ms p90, 0.65 s max (the largest map, on the worker) |
| 10,873 chains; 39 maps differ from navmap, ids unchanged on the other 325 | **10,873**; other ids on **39** maps; **the same ids on 325** - but on 25 of them a chain holds other footholds (found on the way 1) |
| the 19 level joints are one floor each | **19**, each one floor, nothing else joined (joints at one point: 19 with no wall and no link, 122 with a wall: 59 a->b, 63 b->a) |
| the node = `platform_at`'s on 72,800 of 72,800 | **72,800 of 72,800** (the audit's points; through the foothold under it on the maps whose chains differ) |
| 20 things placed <= 20 us (median map), <= 70 us (largest) | **19.0-19.5 us** on the median map (Kerning City Self-Defence Item Store), **19.0-19.4 us** on the largest (Physical Fitness Test <Normal Level 3>), 4 runs, pinned, nothing else computing; with steps, last nodes and 3 climbers (bare: 14.4-14.9). The prototype's 16 / 62 us was the nearest surface alone. **Thin margin:** a busy machine puts it over 20 |
| `proto_feet.py`'s hops: air called standing <= 0.8 %, standing called air <= 0.2 % | **0 of 26,811 (0.00 %); 1,014 of 555,561 (0.183 %)**; the prototype's rows reproduce measurement 3 exactly |
| the table = route()'s seconds on 1,000 random pairs, built <= 5 ms on Line 1 | **1,000 of 1,000** (exactly equal); **4.18 ms** (best of 7, p50 4.19; 4.2-4.4 in single builds) |
| pytest, bot speed | whole suite green; **bot speed 14.5 ms** a tick (p90 16.1; recent runs 13.9-14.2: graph.py is not on the perception path); measured with nothing else computing, the game open. In a worktree, `assets/scene` (not in git) must be linked in first, or the bench runs without the scene model (3.5 ms, meaningless) |
| a rebuild does not block a frame (a test) | **met as "the frame never waits for the rebuild"**: every read during it answers at once from the old set, whole, then the new one (38,000 calls in Line 1's 0.6 s); but see found on the way 3 |

Found on the way:
1. **25 more maps change than the 39** (counted by chains, not by ids): the same chain ids, other footholds - Perion,
   Perion Street Corner, the Rocky Mountain / Rocky Road / Deep Valley maps, Drake's Meal Table and 13 more
   (`nav_audit.py graph` names them). navmap follows a one-way `next` across a joint where another chain comes in
   (Perion chain 153: foothold 156's next is 157, but 157's prev is 165), so its chain runs on; here it stops.
   300 maps have navmap's nodes exactly (and the same edges: below).
2. **The plan's bold row of measurement 3 (0.79 % / 0.072 %) is the "this step still" rule** (within 3 px of the last
   y + the sideways step), not design 3's "within 1 px + 0.9 x the sideways step" (the prototype: 0.55 % / 0.183 %);
   proto_mobs uses design 3's, and so does graph.py. Its 0 air frames called standing (148 in the prototype) is
   the missing +-8 / 16 px retry: `platform_at` found a surface 8-16 px to the side.
3. **The rebuild's worker thread shares Python's GIL with the frame.** While it runs, a call now and then waits for
   the GIL: on Line 1 (0.6 s rebuild) 28 of 22,600 calls of 20 things waited over 6 ms, the longest 20 ms; a 2 ms
   piece of frame work took 2.2 ms at the median, 31 ms at p99, 37 ms at most. On the largest map (6.9 s) the
   longest call 31 ms, a 2 ms piece up to 171 ms. Not garbage collection (the same with gc off); Windows' timer
   resolution makes it worse (at 1 ms: the longest call 12 ms, the 2 ms piece 25 / 60 ms); a shorter switch
   interval makes every call 4 x slower. A process instead of a thread would remove it (the edges come back as
   arrays; the Link objects are made once, ~5 ms on the largest map) - a change of the design, so not made:
   **the user decides** (it matters when step 6's measured values change often enough to rebuild).
4. Two chains lying on each other (In a Small Forest 29 and 62, y 605): equal distances go to the lower id, as
   `platform_at`; the first count of 72,738 was the audit's own mapping back through the footholds' geometry.

The gate's commands: `tools\model\nav_audit.py graph` (~3 minutes; `--no-edges`: 5 s), `tools\perc\track\proto_feet.py
--sound` (its last stand / air row), `pytest tests\test_track_graph.py`.

## Stop rules
1. A gate missed: stop with the numbers. No workaround, no changed constant, no lowered gate.
2. The real code cannot reproduce a prototype's number from the same kept replay within tolerance: stop - it is
   a porting difference to find, not to tune away.
3. The tracker's ms over its line in step 3 or later: stop with the profile.
4. Anything that needs a change in the fit, the scene model or the drop finder: stop and ask (this plan changes
   none of them).
5. A kept replay may be made again on today's scene build, but **only into its own folder**: the kept replay the
   plan's numbers were measured on (`work\SESSION#K\track\`) is never overwritten. (Changed by the user
   2026-11-24: their "no re-make" of 2026-11-23 meant the old `--frames-png` recordings under `runs\`, not the
   bank's captures.)
6. A field's target in `docs/state_model.md` that cannot be met: report it with the numbers; the user decides.
7. Fresh footage contradicts a measurement this plan rests on (the mob speed factor on another map, the bob's
   period, the landing window): stop with both numbers.

---

## Session prompts (ready to paste; Opus; each ends with the `handoff` skill)
```text
Tracker, step 1 (label sets by eye). Read PLAN-tracker.md - Words, measurements 1-8, step 1 - and
tools/perc/label_eval.py. Build nothing in maplebrain/. Make the eight sets L1-L8 exactly as step 1 lists them:
pick the frames from the prototypes' output (tools/perc/track/proto_*.py, mem_sheet.py) so every class is in
them, look at each case as a crop, write the labels into the bank's labels\ folder. Label 10 % of each set a
second time without looking at the first labels; report the agreement. Gate as written; numbers into the plan.
```
```text
Tracker, step 2 (the graph and the placement). Read PLAN-tracker.md - measurement 3, design 3, step 2, the stop
rules - docs/state_model.md sections 1-2 and tools/model/ (nav_audit.py, chains_fixed.py: the reference).
Branch tracker-build. Build maplebrain/track/graph.py with tests; nav/navmap.py stays as it is (the edges are
read from it). Gate as written (tools/model/nav_audit.py, tools/perc/track/proto_feet.py with the real placement
in place of the prototype's); numbers into the plan; a gate missed: stop.
```
```text
Tracker, step 3 (mobs, in shadow). Needs step 1's labels L1, L2, L3, L8 (L2 / L3: the agreed cases only).
Read PLAN-tracker.md - measurements 1-4 and 9, design 1-4, step 3, the stop rules - and
tools/perc/track/proto_mobs.py, proto_feet.py, births.py, mem_sheet.py (the reference: port the rules and the
constants of Cfg, do not redesign). Branch tracker-build. Build track/kinds.py, evidence.py (two sources),
mobs.py and the mob records; the Perceiver calls the tracker beside world.py, nothing reads it. Write it with
arrays, not loops over pairs. Build the replay tool that runs the real code from a kept replay. Then the gate in
its order: the 13 sound captures from the kept replay, the labels, the live path, the ms. For the live path,
make a new kept replay of 20261120_235747_1#0 (Line 1, 4.2 min) on today's scene build into its own folder -
never over work\SESSION#K\track\ (stop rule 5) - and run the GPU path over the same capture's video.
Decide by the numbers whether Fitter.look stays. Numbers into the plan; a gate missed: stop.
```
```text
Tracker, step 4a (drops). Needs step 1's labels L6. Read PLAN-tracker.md - measurement 5, design 5, step 4a, the
stop rules - PLAN-loot.md sections 10 and 13, and tools/perc/track/proto_drops.py (the reference). Branch
tracker-build. Build track/drops.py; perception/drops.py is not changed. "We took it" reads the pickup key's
state (down), not its last press. Gate as written, from the kept replay; numbers into the plan; a gate missed:
stop.
```
```text
Tracker, step 4b (other players and us). Needs step 1's labels L1 and L5. Read PLAN-tracker.md - measurement 7,
design 6-7, step 4b, the stop rules - tools/perc/track/proto_players.py (the reference) and nav/selfstate.py's
docstring (its stuck cases become tests). Branch tracker-build. Build track/players.py and us.py; two tags side
by side are split by the widths already known; pets are sorted out. Gate as written; numbers into the plan; a
gate missed: stop.
```
```text
Tracker, step 5 (events). Needs steps 3-4 and step 1's labels L4. Read PLAN-tracker.md - measurement 6, design
8, step 5, the stop rules - docs/state_model.md section 4 and tools/perc/track/proto_events.py (the reference:
re-run it first and compare with measurement 6; a difference: stop). Before building, put question 8 (EXP in
the kill rule; the note under measurement 6) to the user and write the answer into the plan. Branch
tracker-build. Build track/events.py on the tracker's own tracks. Gate as written; numbers into the plan; a gate missed: stop.
```
```text
Tracker, step 6 (facts, the profile, Skill.img). Read PLAN-tracker.md - measurements 4 and 6, design 9, step 6,
the stop rules - docs/state_model.md sections 5-6, assets/README.md and tools/model/self_measure.py (the
reference for what is measured live). Branch tracker-build. Build track/facts.py, the profile file, the skills
into assets/mcw (gamedata.py); track/kinds.py reads the registry. No behaviour of the brain changes. Gate as
written; numbers into the plan; a gate missed: stop.
```
```text
Tracker, step 7 (the hotkey reader). Needs the user's quickslot footage and step 1's labels L7. Read
PLAN-tracker.md - measurement 8, design 7, step 7, the stop rules - and tools/perc/track/proto_slots.py (the
reference; its docstring says what the client draws). Branch tracker-build. Build perception/slots.py, the
picture pack in `assets build`, FrameFacts `slots` for all 8 keys, the amounts tracked in track/us.py. Measure
the speed with nothing else running. Gate as written; numbers into the plan; a gate missed: stop.
```
```text
Tracker, step 8 (the stored tables). Needs steps 3-5. Read PLAN-tracker.md - design 10, step 8, the stop rules -
docs/state_model.md section 8 and tools/model/size_proto.py (the reference layouts). Branch tracker-build. Build
the writer and the reader, wire them into the recorder and the hunt, and the converter from a kept replay. Gate
as written; numbers into the plan; a gate missed: stop.
```
```text
Tracker, step 9 (the switch). Needs every step before it, and the user at the game. Read PLAN-tracker.md - step
9, the stop rules - and PLAN-livemap.md. Branch tracker-build. The brain reads the state through one adapter;
world.py, its tests and what only it needed are deleted; gate.py and the bench are re-based in that commit.
pytest, the bench, then ask the user for the 3-minute hunt on Line 1. Numbers into the plan; a gate missed: stop.
```

## Footage asked of the user (`python -m maplebrain record --label farming`, chat minimized, today's settings)
1. ~~**Line 1 <Area 1>, 5 minutes of farming**~~ - **dropped 2026-11-24**: step 3's live check uses the 4.2-minute
   Line 1 capture `20261120_235747_1#0` with a new kept replay of it on today's scene build (stop rule 5).
2. **The quickslot bar, 1-2 minutes** - step 7: a skill on one of the 8 keys and used a few times; an item used
   until its amount shows 0 (or a stack of 1-2 used up); the mouse resting on a slot until its tooltip shows; the
   inventory or another window over part of the bar for a few seconds.
   **DONE 2026-11-24:** `20261124_093410_1#0` (Henesys Hunting Ground I, 1m09s, label `quickslot`): a skill on
   a key used, an amount used to 0, tooltips. **The window over the bar is skipped** (the user: no window covers
   the bar in play), so that case is not in the new footage.
3. *Welcome:* 3 minutes on a map with flying mobs (Stirges) and on one with two kinds that look alike (an Ant
   Tunnel map) - the captures the prototype is weakest on are of the old scene build.
4. ~~*If the character has one:* a buff cast 5 times while recording~~ - dropped: the warrior has no lasting
   skill (the user, 2026-11-24, question 6). (the buffs' gate of state_model.md; without
   it that gate waits).

## Questions for the user
**Answered 2026-11-24 (the user), questions 1-7; question 8 is postponed to step 5:**
1. **OK** - the gates as written (98.4 %, 90.9 % fair count, the prototype's cover numbers).
2. **OK** - one 4 s limit for whatever cannot be checked.
3. **"When server rules and observed data clash - always take the observed data."** A standing rule, not only
   for the mob speed: the measured factor 2.0 (and the hop 555 px/s, knockback 19 px, hit pose 0.55 s) is the
   value the tracker uses; the rule's number is kept beside it as its source (design 9, step 6).
4. **No pet tracking now; it may be added later.** Pets' tags are sorted out and not tracked (design 6); keep
   their class in the tag sorter so a later step can track them without re-sorting.
5. **Players' cover: 2 s** (29 of 308 tracks back under a new number, against 52 with 1 s). Design 6 and step
   4b use 2 s; this replaces state_model.md's 1 s (its "Decided" 2).
6. **No cooldowns and no lasting skills on the warrior: not implemented now.** `buffs` and `cooldowns` stay in
   the model, empty; design 7's "buffs and cooldowns" and footage ask 4 are dropped from steps 4b-6. Rush's 2 s
   (12 presses inside it did nothing) is the skill's own action, not a cooldown: it is a "swing running" for the
   cast rule (design 8).
7. **The HP items' x 1.24 is the warrior's passive healing-bonus skill.** It stays a measured fact (design 9,
   step 6's "potions +150 / +198"), with that skill named as its source in the registry; MP items 1.0 x.

The questions as they were asked:
1. **Three of the model's targets are not met by the prototype as they were written. Are these gates right?**
   (a) Mob-frames found: 98.7 % against 99 % - the missing part is the "not a mob until seen clearly" stage (1.2
   points, all at the screen's edge); the gate is 98.4 %. (b) One id for life: 74.8 % against 90 % by the plain
   count, but 457 of the 1,022 extra ids are the truth swapping two mobs at a crossing (7 are the tracker's); not
   counting a change beside another mob of its kind it is 90.9 %, and that is the gate. (c) The same id across
   a cover up to 1.5 s: 97.0 % and 96.5 % up to 0.3 s, 93.6 % for 0.3-0.6 s, 79.4 % for 0.6-1.5 s (today 29.9 %)
   against 95 % - beyond 0.6 s the truth itself is unproven; the gates are the prototype's numbers.
2. **One limit of 4 s for whatever cannot be checked** - out of view (your answer), and also behind the UI or
   front scenery and "something is drawn over it". The model said a covered mob stays as long as it can be
   there; unchecked, that memory followed other mobs and the message lines around. 8 s buys nothing, 2 s loses
   the covers of 1.5-4 s. OK?
3. **Mobs move at twice the v83 rule's speed** (8 kinds; a Bubbling 137 px/s). Does Classic World's speed-up of
   mobs match what you know? The tracker uses the measured speed either way; game_rules.md C1 gets a note. Also
   measured against the rules: a mob's hop takes off at 555 px/s like ours (the rule: 625), a knockback is
   19 px (27), the hit pose lasts 0.55 s (0.248).
4. **Other players' pets carry name tags** ("Brown Puppy", "White Bunny", "Snail"). The plan sorts them out and
   does not track them. Or do you want pets in the state?
5. **Players' cover:** with 1 s, 52 of 308 player tracks are the same player back under a new number; 2 s gives
   29. Keep 1 s?
6. **Which of your skills have a length or a cooldown** (Rush's 2 s is seen in the footage)? The buffs and
   cooldowns come from the cast + the client files; the gate needs casts to look at.
7. HP items give 1.24 x their file value (Meat 160 -> 198, Red Potion 100 -> 124), MP items 1.0 x. Do you know
   why? It stays a measured fact either way.
8. **EXP in the kill rule** (measurement 6, the note on party EXP): drop it from the live rule and keep it as the
   offline grader on solo captures (Claude's recommendation), or drop it completely (then L4 grows to 200-300
   hit-pose begins over 2-3 maps)? Do you play in parties, and how does the client show one?

## Commands (from the repo root, `.venv\Scripts\python`; everything from the kept replay, no GPU)
```powershell
tools\perc\track\cache.py CAP [...]                      # the truth's chains kept on disk
tools\perc\track\proto_mobs.py --sound --today [--why 0] # measurement 1: the prototype and today, pooled
tools\perc\track\ablate.py                               # one setting changed at a time (12 short captures)
tools\perc\track\mem_sheet.py CAP                        # by-eye sheets of remembered tracks
tools\perc\track\births.py --sound                       # measurement 2
tools\perc\track\proto_feet.py --sound                   # measurements 3 and 4
tools\perc\track\static_overlay.py CAP; tools\perc\track\scene_gaps.py CAP    # what is never the scene
tools\perc\track\proto_drops.py run|numbers|sheets --sound                    # measurement 5
tools\perc\track\proto_events.py                         # measurement 6 (the 30-minute capture)
tools\perc\track\proto_players.py CAP [--covers --time --sheets]              # measurement 7
tools\perc\track\proto_slots.py run|report|bench|selftest [CAP]               # measurement 8
```
Outputs, sheets and reports: `F:\dev\maple-corpus\work\track-plan\` (`mobs\`, `drops\`, `events\`, `players\`, `slots\`).
