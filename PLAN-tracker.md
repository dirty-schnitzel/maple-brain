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
**Step 3 DONE (2026-11-25, accepted by the user on try 2's numbers):** the mob tracker runs in shadow
(`track/mobs.py`); the kept replay's rows, the feet and the live path met (100.000 % equal); L1 stand / air 97.57 %,
L2 13 of 16, L3 19 of 22 and the tracker's ms p50 1.04 accepted as they are. Three carry-overs (under "Step 3, try
2", "The user's decision"): the step rule on steep slopes -> step 4b; L2 re-graded once tags are sorted -> step 4b;
the whole frame's +0.3 ms -> step 9. Fitter.look: no gain, goes in step 9.
**Step 4a DONE (2026-11-25, accepted by the user as it is; merged into `tracker-build`)**: the gate missed 2 rows - 35 pickup hops
without our key down (the pet "Snail" on the 2026-11-18 captures, by eye) and 1 "gone then seen again" (a passing
flight read as a pickup hop; the prototype had it too); every other row met (746 drops, L6 97.4 %, exactly one death
88.5 %, ms p50 0.197). Numbers and the user's decision under the steps ("Step 4a, 2026-11-25").
**Step 4b (2026-11-25): built, in shadow, the port exact; the gate MISSED - stopped, the user decides** (under the
steps: "Step 4b, 2026-11-25"): met - the 2 s cover (29), the stuck cases as tests, L2 on the 16 (93.8 %, carry-over 2);
missed - L5 (found 73.9 %, the prototype's own rules 85.1 %), L1 us 83.5 % (~20 jump frames labelled stand), SelfState
95.81 %, our feet known 97.04 % (the tag list gives 0.36, not 1.1), the ms (live 0.7: one GPU round trip).
**Step 4b, try 2 (2026-11-26): the user's answers built; stopped again, the user decides** ("Step 4b, try 2"): met -
step 3's rows unchanged, the hops gate unchanged, one GPU transfer a frame, L1J (18 jump labels stand -> air, second
look 5 of 5); missed - L5 (found 92.8 %, non-players 5.62 %, pet / player 8.56 %, node 94.0 %), the cover (33: the
pet rule), L1 us 84.62 % (93.41 % without the rope motion test, which breaks 22 rope grabs), the ms (0.7: Python and
torch calls, not the GPU - try 1's reason was wrong). SelfState 95.81 % and our feet 97.04 % accepted by the user.
**Step 4b, try 3 (2026-11-26): design 1 and the rope key built; stopped, the user decides** ("Step 4b, try 3"): met -
pet / player 2.52 % (8.56), the node 96.5 %, step 3's rows (L2 now 16 of 16), the hops gate; missed - players found
85.4 % (95.8 % if "unsure" - under 5 alone body readings - were "not yet known" like "short"), non-players 2.04 %, the
cover 34; L1 us 95.05 % with the key rule (the user's answer 4: accepted at what it reaches); the ms live 0.6.
**Step 4b, try 4 (2026-11-26): the cheaper body check (A: every 4th frame; B: an early settle) built; stopped, the user
decides** ("Step 4b, try 4"): with `unsure` graded apart try 3 meets players found (95.8 %) and the cover as a rate
(9.6 %); A + B misses players found (92.8 %; A alone 93.5, B alone 91.5) and saves little live (us_players mean 0.40 ->
0.37 ms, p90 0.8 both: the body question costs per call, not per tag); met - non-players 1.55 %, pet / player 4.49 %, the
node 96.6 %, the cover 5.8 %, L1 us 95.05 %, step 3's rows, the hops gate.
**Step 4b DONE (2026-11-26, "Step 4b, close"):** the user undid A and B (back to try 3's sampling) and set the ms line;
every row equals try 3 regraded and meets its gate - players found 95.8 %, the cover 9.6 %, pet / player 2.87 %, the
node 96.5 %, step 3's rows, the hops gate, the ms live p50 0.5 / p90 0.8 (<= 0.5 / 1.0); accepted: non-players 2.13 %,
"FreakyRafiki", L1 us 95.05 %. A cheaper body call is left for step 9.
**Step 5a (2026-11-26, "Step 5a, 2026-11-26"): the HP meter measured, then built in shadow; the gate MISSED on 3 rows -
stopped, the user decides.** Measured: one place rule for every kind (30 px over the pose frame's body box, centred on
it), a meter only after our hit (0 on a mob we did not hit), the lost part red fading to black in 2 s. Met: the fill
(83 of 83 within 3 points), 0 meters on a mob not hit, step 3's rows identical, L9's second look 100 %. Missed: found
on 94.1 % of L9's frames (hidden meters), tied 45 of 110 (0 wrong; the overlap guard and unread fills leave the rest),
the reader's ms p50 0.101 (the whole frame +0.00). **The user's answers (2026-11-27):** found 94.1 % and the ms
accepted; the tie: trust perception's candidate among the seen mobs, the guard kept for remembered ones -> **step 5a,
try 2** (its prompt under "Session prompts").
**Step 5a, try 2 (2026-11-27, "Step 5a, try 2"): built; the tie MISSED - stopped, the user decides.** L9's meters whose
fill was read: tied 61 of 83 (73.5 %, >= 99 % asked), 0 wrong; the 22 left are refused by the guard against unseen
tracks (in 17 no hidden mob there has a meter; in 5 one has, drawn at its own place; the candidate right on all 22).
Step 3's rows identical, the bot speed 17.1 ms. The user's choice: (a) drop the guard, (b) refuse only where more
meters than seen mobs, (c) keep. The assassin (report only): the place rule 97.2 %, the window holds at 0-354 px, 0
meters on a mob not hit; found: perception's own-tag picture is the warrior's (another character: no camera without
its own), and a held attack key repeats casts.
**The user's answer (2026-11-27): (a), design 1 relaxed. Step 5a, close (2026-11-27, "Step 5a, close"): the guard
dropped; L9 MET - 83 of 83, 0 wrong; step 3's rows identical, pytest green, bot speed 15.9 ms; STOPPED on a wrong tie
outside L9** (the prompt: "one wrong: stop with the case and its picture"): Cave 7 frame 35601, a hidden Zombie
Mushroom's meter taught to the Evil Eye in front of it; over the 13 captures at most 36 of 15,809 readings carry an
unseen track's fill, a track's HP rose 29 times (try 2: 5). The user decides: keep (a), or a narrower refusal (R1 / R2:
L9 82 of 83 under either), or try 2's guard. **Part 2 (report only):** the meters decide 50 of the 994 fair id errors
(11 against the tracker, ~8 right by eye), 1 of 187 overlapped deaths; a hidden mob placed within 2 px (p50) against
the set's middle 9 px. My reading: no build step before step 5 - the user decides.
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
and the events since the last frame. **Clean sightings teach first, crowded ones may teach too (the user,
2026-11-26; relaxed 2026-11-27: "Lets relax this rule, it is best if possible to classify something when it is
alone, but not mandatory"):** what a thing IS - a player's or pet's class, a body's height, a name's width, a mob's
kind, a death, a mob's HP - is best learned from sightings where it is seen alone and whole; a sighting that overlaps
another thing (tags touching, bodies over each other) may teach too when its own evidence names one thing (the HP
meter's box: step 5a), and a clean sighting's reading is preferred over a crowded one's. Step 4b's players and pets
were built under the strict rule and stay as built (their gates met). Built for players and pets in step 4b;
mobs' overlaps (swapped ids, a death read on the wrong mob) are checked in step 5. Fixed inputs: the graph and the facts registry. A frame without a camera
changes nothing (`cover = blind`).

**2. Evidence: "does this place show the scene?"** One interface, two sources: the kept replay's two bitmaps
(CPU) and the fit's own tensors on the GPU (frame, expected scene, valid: one gather for every place asked
this frame, one transfer back). So the real tracker is graded on the kept replay without re-making it, and the
GPU source is proved equal to the bitmap source on fresh footage.

**3. Placement: the one rule of the model, with motion.** `stand` = the feet within 3 px of a surface and the
step since the last frame within 1 px up or down (+ the foothold's own rise over the sideways step, rounded up to a
whole pixel: "Step 3, the slope fix"; it was + 0.9 x the sideways step); else
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
**The user, 2026-11-27: "Hotkeys should be fully modular, changing values of items should be in config file"** -
no key, skill or item bound in code: which key holds what is set in the config / profile only, so a class or a
moved item is a config edit (the first two: the warrior's `Keys`, the assassin's keys under "Step 5a" answer 4).
**The profile's form (the user, 2026-11-27/28):** one TOML file per CHARACTER in `profiles/`; `config.py` keeps only
the bot's own keys (F7-F12). No item numbers in it for now ("no items in config file for now, start without them"):
a potion's heal comes from the client files or is measured. Every action or item is an object, like the skills:
- `[character]`: name, job, `speed`, `jump`, the name-tag picture perception finds us by, the weapon type.
  **`speed` / `jump` = the character's base values with its items only, no skills** (the user: "the character's
  passive speed without skills, so only affected by items"; today 100 / 100). Passive skills, active skills (Haste),
  consumables and so on add on top, each from its own data (Skill.img, the item files) while it applies; the measured
  walk / jump is checked against them (meowdb: 150 px/s at Speed 100; observed beats the rules). Both characters
  100 / 100 (the user, 2026-11-28); **JenkinsJob's Polearm Mastery is a passive that adds speed** ("slightly
  increased speed due to polearm mastery"; its level: the user, later) - his measured 151.8 px/s walk is that.
- `[[skill]]`: name, key (none for a passive), level, use (`single` / `area` / `mobility` / `buff`; the class's
  attacks differ - the warrior uses a single-target, an area and a mobility skill, the assassin mainly Lucky Seven
  and buffs - and change with level: a level-up is an edit of `level` or a new block), `hold` (a held key keeps
  casting). The skill's numbers per level (mobs hit, reach, MP, cooldown, a buff's time) come from Skill.img.
- `[[basic_action]]`: name, key (attack = the plain attack, jump, loot, ...).
- `[[item]]`: name (or "?": the hotkey reader names what is on the bar), key, use (`hp` / `mp` / ...).
How the character PLAYS (jump shots, Rush to close in, an area skill on a crowd) is the brain's, not the profile's.
Open: per character (the user's answer) against `profiles/yoav.toml`, a per-PLAYER draft another session wrote
2026-11-27 (with a shared `[style]` and a bot-written `measured` part) - to reconcile before step 6 builds the reader.

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
| **3** | **Mobs, in shadow** (`track/kinds.py`, `evidence.py`, `mobs.py`, the mob records of `state.py`; the Perceiver calls it beside `world.py`; the replay tool): design 2-4 | *From the kept replay, 13 sound captures:* measurement 1's table within tolerance - found >= 98.4 %, id kept across a cover >= 93.1 % (by length >= 96.7 / 96.2 / 93.3 / 79.1 / 77.1), one id for life not beside another mob >= 90.6 %, extra ids <= 1,032, "the track changed mob" <= 10, next to its set >= 99.0 %, a death seen noticed p90 <= 0.05 s, no seen track-frame without a truth mob; measurement 3's feet: hops within 1.5 px rms >= 91 %, jolts <= 556 (the prototype's own tracks counted alike; was 500, measured on the truth's tracklets - the user, 2026-11-24). *Labels:* L1 mobs: stand / air >= 99 %, the node >= 99.5 % of standing mobs; L2 >= 90 %, L3 >= 95 %, both counted on the agreed cases only (L2 21, L3 22: `"agreed": true` in the bank's files; step 1, try 3); L8: reported. *Live, on `20261120_235747_1#0` (Line 1, 4.2 min) with a new kept replay of it on today's scene build in its own folder (stop rule 5):* the GPU evidence = the bitmaps' on >= 99.9 % of the places asked; the shadow rows = that capture's replay rows on >= 99.5 % of track-frames; the tracker's ms p50 <= 1.0, p90 <= 2.5 (today's `world` + looks: 0.7 / 2.0), the whole frame's p50 not above today's + 0.3; `gate.py` SAME | - (the GPU, and a speed number) |
| **3b** | **Spawn points as tracked things** (added by the user 2026-11-25; `track/spawns.py`, the spawn point records of `state.py`; "Step 3b" below) | first, measured: do new mobs appear on their spawn point (the faded-in births of the 13 sound captures against map.json's points of their kind) - >= 95 % within 10 px, else stop with the distribution; then from the kept replay: every faded-in birth near a point of its kind is that point's spawn, a 30-case sheet checked by eye >= 29 right; the live path's shadow rows = the replay's; ms p50 <= 0.1 | 4a, 4b (a new file: reads the mob tracker's births) |
| **4a** | **Drops** (`track/drops.py`): design 5; the finder (`perception/drops.py`) is not changed | from the kept replay, measurement 5 within tolerance: 746 drops, 0 lives with two items or over 131 s, 0 "gone" then seen again, pairs of one item within 3 px <= 9 and each looked at, exactly one death for >= 84.4 % of drops, "we took it" with the key down: no hop without it on any of the 13; L6 >= 90 %; PLAN-loot's gates still met; ms p50 <= 0.2 | 4b |
| **4b** | **Other players and us** (`track/players.py`, `us.py`): design 6-7 | L5: players found >= 95 %, non-players called players <= 1 %, a pet called a player or a player called a pet <= 5 %, the node on >= 95 % of standing players; the 2 s players' cover (question 5): the same player back under a new number on <= 29 of the 30-minute capture's 308 tracks (within 1 %); L1 us: >= 99 %; every stuck case `nav/selfstate.py`'s docstring lists is a test; us against `SelfState` on the 30-minute capture: the same place on >= 99 % of frames, every difference listed; our feet known on >= 97.5 % of frames (today 96.7; the tag list gives 1.1 points); ms p50 <= 0.1 | 4a |
| **5a** | **The HP meter** (added by the user 2026-11-26, BEFORE step 5; "Step 5a" below): `perception/` finds the HP meters Classic World draws over mobs WE hit and reads each one's green share; the mob tracker ties each meter to its track; the mob record gets `hp` | first, measured from the recordings only: the meter's picture, its place above the mob across mob sizes (against the sprite box and `mob.json`'s `head` point), when it appears after our hit and goes at the death, whether it ever shows on a mob we did not hit, several meters, two mobs close; a label set L9 by eye (100 meters: its mob, its fill %; 10 % twice, blind, >= 95 % agree); then: meters found on >= 99 % of L9's frames, tied to the right mob >= 99 %, the fill within 3 % of the eye's; 0 meters on a mob we did not hit (the kept replay against our hit windows); ms p50 <= 0.1, **more than 1 ms added a frame: stop and discuss** (the user) | 6, 8 |
| **5** | **Events** (`track/events.py`; needs 3-4 and 5a): design 8, with the meter | 30-minute capture, from the kept replay and its keys: casts 500 / 78 / 10 (q / e / w) within 1 %; every HUD step has a cause; "by us" by chance <= 1 % (windows moved in time); a death's credit `ours` / `shared` / `theirs` / `unknown` against EXP on solo captures (the offline grader, question 8): an `ours` death with no whole EXP step <= 1 %, whole-EXP kills missed <= 2 %, a partial EXP step matched by a `shared` death (reported); L4 >= 95 %; the swing length measured live within 0.03 s of 0.85 / 0.87; corpse tracks: no second death or new mob from a dead body; overlaps: hits and deaths of two mobs overlapping, reported | 6 |
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

### Step 3, 2026-11-24: the mob tracker built, in shadow; the gate MISSED on the feet's jolts and on L1, L2, L3 (stopped before the live path)
Branch `tracker-build` (85547b9, 865f8c7, 83ab207). Built: `track/kinds.py` (proto_mobs' `Kind`), `track/evidence.py` (the
interface; `Bitmaps` = the kept replay's two bitmaps, `Gpu` = the fit's own tensors: dump.py's formula, one gather a
group, one transfer back), `track/mobs.py` (proto_mobs v5 ported: one cost over tracks x readings as arrays, the
remembered tracks' sets tested in one evidence call, placement by `track/graph.py`), `track/state.py` (the mob record;
`x_seen`, `y_seen` = where it was last seen, `x`, `y` = the middle of its possible set while remembered, as graded). The
prototype's Cfg and its inline numbers are in `config.Track`. The Perceiver runs it after the drops (part `track`),
beside world.py; `MapKit.graph` is built in `_load_map`; `Track.shadow` False turns it off. Tool:
`tools/perc/track/replay_mobs.py` (`run`, `pool`, `feet`, `labels`, `live`, `time`); dump.py `--out NAME` (a new kept
replay in its own folder; `--force` on `track` is refused). `tests/test_track_mobs.py`: 15 tests. Outputs:
`F:\dev\maple-corpus\work\track-plan\step3\`.
**The port = the prototype:** on the 4-minute Line 1 capture (navmap's nodes = the graph's) every row of the report is
the prototype's to the digit; over the 13 the counts differ by a few (the graph has no +-8 / 16 px retry and other
nodes on 3 Ant Tunnel maps: step 2).
**Fixed on the way (not in the prototype):** on a blind frame a track seen on the frame before stayed "seen" (the
prototype too): 172 seen track-frames without a truth mob on 5 captures, all blind frames (the exit fades). A record
on a blind frame now keeps its values with `seen` False, cover `blind` (the model: "found on this frame"): 0; no other
number moved. A test fails without it.

| Gate (from the kept replay, 13 sound captures) | track/mobs.py | the prototype (measurement 1) | |
|---|---:|---:|---|
| found (>= 98.4 %) | 98.70 % | 98.7 % | met |
| id kept across a cover (>= 93.1 %) | 93.48 % | 93.4 % | met |
| ... by length (>= 96.7 / 96.2 / 93.3 / 79.1 / 77.1) | 97.0 / 96.5 / 94.1 / 79.4 / 77.4 | 97.0 / 96.5 / 93.6 / 79.4 / 77.4 | met |
| one id for life not beside another mob (>= 90.6 %) | 90.98 % | 90.9 % | met |
| extra ids (<= 1,032) | 1,019 | 1,022 | met |
| "the track changed mob" (<= 10) | 7 | 7 | met |
| next to its set (>= 99.0 %) | 99.35 % of 2,783 | 99.32 % of 2,782 | met |
| a death seen noticed, p90 (<= 0.05 s) | 0.000 s | 0.0 s | met |
| seen track-frames with no truth mob within 40 px (0) | 0 (172 before the blind fix) | 0 | met |
| feet: hops within 1.5 px rms (>= 91 %) | 91.4 % of 919 hops (p50 0.94 px) | 91.6 % of 918 | met |
| feet: jolts of 13 px or more (<= 500) | **550** of 593,073 frame steps | 489 | **MISSED as written** |

**The jolts:** measurement 3's 489 is `proto_feet.settle_series` (its own settle rule: the reading nearest the motion)
on the truth's tracklets; the real code's feet can only be counted on its own tracks (each run of consecutive seen
frames, jumper kinds, 15+ frames: `replay_mobs.py feet`). **The prototype tracker's own tracks counted the same way:
556 jolts** (920 hops, 91.3 %) - the port has 6 fewer. So the 500 is not met, and the port is not the reason.

| Labels (step 1's, by eye) | track/mobs.py | the prototype's own rows (`labels --tag proto`) | Gate |
|---|---:|---:|---|
| L1 mobs: stand / air (>= 99 %) | **715 of 783 = 91.32 %** (+ 46 labelled mobs with no seen track: added by the labellers, the fit missed them) | 707 of 783 = 90.29 % | **MISSED** |
| L1 mobs: the node of standing mobs (>= 99.5 %) | **515 of 518 = 99.42 %** | 516 of 519 = 99.42 % | **MISSED** (by 1 mob) |
| L2, the 21 agreed cases (>= 90 %) | **10 of 21 = 47.6 %** | 10 of 21 (every case the same answer) | **MISSED** |
| L3, the 22 agreed cases (>= 95 %) | **17 of 22 = 77.3 %** | 17 of 22 (every case the same answer) | **MISSED** |
| L8 (reported) | "yes": a track kept over its range on 20 of 20; "no": kept on 5 of 6; "?": kept on 14 | - | - |

**Every miss, by case** (tracker = the prototype on all of them; they are the design's rules against the labellers'):
- **L1 stand / air (68):** 26 Bubblings + 3 Slimes in a `move` pose labelled air, placed standing (a hop's look-alike
  reading on the surface wins); **17 Stirges labelled flying, placed standing** (design 3: any kind within 3 px of a
  surface stands - a flyer too); 20 labelled standing, placed in the air - feet 3.6-4.4 px off a slope (past 3 px), a
  one-frame step up or down while walking, 4 with feet 9-35 px off a surface (Evil Eye -35, Zombie Mushroom -12, a faint
  one -9). **Node (3):** case 113 (`232410_1#12` n 57599) 343 / tracker 351; case 190 (`#2` n 13749) 434 / 454; case 171
  (`#9` n 47090) 398 / 388.
- **L2 (11):** label **none** (a mob in plain view the fit missed) -> tracker mob 4 (cases 34, 29, 24, 36), ui / scenery 1
  (71): the tracker can only name what is over the places it keeps; label **edge** -> tracker effect 2 (7, 8), player 1
  (68), mob 1 (38): the in-view part's cover named, not the edge; label effect -> player (57), us -> player (61): two
  things over the mob, the boxes decide. The 10 right: mob 1, effect 2, us 2, ui 3 (= "ui / scenery"), edge 2 (= "out of
  view").
- **L3 (5):** label uncover / view -> tracker **dying** 3 (cases 47, 45, 48: the first sighting is a die pose, so "how
  born" = dying; the labellers say how it came into sight); uncover -> there at entry 1 (41: born 0.4 s after the
  stay's first camera); uncover -> came into view 1 (26: born within 70 px of the edge, inside the picture).

**Fitter.look - the numbers say it goes** (from the kept replay: its looks, made at world.py's tracks, the fit's rule
says seen, taken as sightings too; `run --hints --tag hints`): found 98.69 % (98.70 without), id kept 93.57 % (93.48), one
id for life not beside another 90.87 % (90.98), extra ids 1,016 (1,019) - no gain; **481 seen track-frames with no truth
mob** (0 without); ~0.6 ms a frame (the bench's `hints`). It stays only for world.py, and goes with it in step 9. (The
live check of looks at the new tracker's own sets was not made: the gate stopped first.)
**Not run (stopped):** the live path (a new kept replay of `20261120_235747_1#0` into `work\...\track_s3`, the GPU
evidence against the bitmaps, the shadow rows against the replay's) and the ms gate (`replay_mobs.py time`). Seen on
the way: the pytest bot speed line 15.4 ms a tick (p90 16.9; `track` 0.4 ms of it on Ant Tunnel IV; step 7 measured
14.5) - its A/B is the ms gate's. The CPU evidence of the replay costs up to ~10-18 ms p90 on the Ant Tunnel captures
(a remembered jumper's set: up to ~250 places x 7 heights x its core); live it is one GPU gather.
**For the user:** (1) the jolts - the like-for-like count (550 against the prototype's 556) or the 500 as written?
(2) L1 - does a flying mob (a Stirge) ever stand on a platform? (if not: a flyer is never `stand`); the 3 px on slopes;
the hop's surface reading. (3) L2 / L3 - the tracker's classes are not the labellers': `none` and `edge` for L2, a
death or an entry at birth for L3. Change the rules, the labels' classes, or the gates? (4) Go on with the live path
and the ms (both independent of these)?

**The user's answers (2026-11-24, to the plan manager):**
1. **Jolts: OK** - the gate is the like-for-like count, **<= 556** (the prototype's own tracks); the port's 550 meets it.
2. **"Stirges never land"**: a flying kind (Mob.img `fly`) is **never `stand`**, whatever its distance to a surface.
   **The walk's bounce is ground:** the client's Slime / Bubbling `move` frames 2-4 draw the body 4-10 px above the
   feet point (400 of the 1,050 ms cycle; the sheet: Slime = mob 7, Bubbling = mob 14 in `assets/mcw/mobs`) - the
   user: "bubblings do bounce like that when walking, it should be labeled as ground". So the 29 L1 cases (26
   Bubblings + 3 Slimes in a `move` pose labelled air) are **relabelled `stand`** in the bank's L1 file (the tracker
   already says stand); only a real jump (the `jump` action, measurement 3's hops) is air. **The slope (feet 3.6-4.4 px
   off a slope, past 3 px): 5 px on slopes only** (the user: "allow 5 px"); flat ground keeps 3 px.
3. **L1's node: 99.42 % (515 of 518) accepted** as met (one case short of 99.5 % on this sample).
4. **L2 / L3: OK** -
   - L2: the 5 cases labelled `none` (a mob in plain view the fit missed) leave L2's count: the tracker can only
     name what it was given (the fit is outside this plan, stop rule 4) - reported apart as fit misses.
   - L2: a mob whose box crosses the screen's edge is `edge` (the edge wins over what covers its in-view part);
     with two things over the mob, either one named is right (the labellers named one of two).
   - L3: "how it came into sight" and "its first pose" are two fields: a mob first seen in its die pose is born by
     how it came into sight (uncover / view / there at entry), with `dying` as its first pose. The born-near-the-edge
     rule (case 26: within 70 px of the edge, inside the picture) and case 41 (0.4 s after the stay's first camera)
     are looked at under the same rule, and reported.

### Step 3, try 2 (2026-11-24): the answers built; the kept replay, the feet and the live path MET; L1, L2, L3 and the ms MISSED (stopped)
Branch `tracker-build` (f97dd4e). **Built** (a test for each rule fails without it: `tests/test_track_graph.py`
`test_stand_within_5px_of_a_slope_3px_of_flat_ground`, `test_a_flyer_never_stands`, the plain reference rule of
`test_place_equals_the_plain_rule_on_real_maps` with both; `tests/test_track_mobs.py`
`test_the_edge_wins_over_what_covers_the_in_view_part`, `test_how_it_came_into_sight_and_its_first_pose_are_two_fields`):
- **Placement** (`track/graph.py`, design 3): stand within `Track.stand_tol_slope` = 5 px of a foothold that is not
  level (3 px on level ground; the foothold at a joint = the one going on, as the table's rows); a kind that flies is
  never `stand`. Step 2's hops gate re-checked (`proto_feet.py --sound`): air frames called standing **124 of 26,811
  (0.46 %, <= 0.8)** (0 with 3 px), standing called air 1,014 (0.183 %, <= 0.2) - unchanged.
- **Cover** (`track/mobs.py`): `edge` (a new name in `state.COVERS`) when the body box at the record's x, y (the middle
  of the places left) crosses the screen's edge (left, right, top; the window's bottom) and some place can be checked;
  its memory is that of a mob drawn over (`hidden`, 4 s since last seen) - only the name changed. With nothing to check
  the covers stay `out of view` / `ui / scenery`.
- **Birth** (`track/mobs.py`, `state.Mob.first_pose`, `docs/state_model.md`): `born_how` = how it came into sight
  (there at entry / faded in / came into view / uncovered), `first_pose` = the pose of the first sighting (a die pose:
  first seen dying). Found on the way and built under the same answer: **a die pose is never "faded in"** - the death
  animation fades the body OUT, so its opacity is under 0.9 (case 45 was born "faded in" by the first build).
- **The labels** (backups of the files changed: `F:\dev\maple-corpus\work\track-plan\step3\labels_before_try2\`):
  **L1: the 29 walk-bounce mobs relabelled `stand`** in the bank's files - `20261119_204522_1#4` cases 53, 110, 192
  (Slimes), `20261120_235747_1#0` cases 1 (x2), 14, 49, 76 (x2), 88, 100 (x2), 125, 162, 175, 188 and
  `20261121_000219_2#0` cases 26 (x2), 77 (x3), 89, 114, 127, 157, 170, 183 (x2), 196 (Bubblings), every one in a
  `move_2` / `move_3` / `move_4` pose (the bounce frames), its labelled feet on the surface (off 0.0 px); its node = the
  surface under the labelled feet (= the tracker's on 29 of 29). Each mob carries `was: air` + `relabel`, each file a
  `relabelled` list with the user's words. **L2: `also`** = the labellers' second thing over the mob (step 1's
  `judged/L2_a.jsonl`, 29 cases; `label_sets.py write` had dropped it) - "either of two covers" is graded against it.
- `replay_mobs.py labels`: L2 leaves out the `none` cases (listed apart), takes the label's cover or its `also`; L3
  prints the first pose. Outputs: `...\track-plan\step3\*_try2.pkl` (try 1's files kept).

| Gate (from the kept replay, 13 sound captures) | try 2 | try 1 | |
|---|---:|---:|---|
| found (>= 98.4 %) | 98.70 % | 98.70 % | met |
| id kept across a cover (>= 93.1 %), by length (>= 96.7 / 96.2 / 93.3 / 79.1 / 77.1) | 93.48 %; 97.0 / 96.5 / 94.1 / 79.4 / 77.4 | the same | met |
| one id for life not beside another mob (>= 90.6 %) | 90.98 % | 90.98 % | met |
| extra ids (<= 1,032); "the track changed mob" (<= 10) | 1,019; 7 | 1,019; 7 | met |
| next to its set (>= 99.0 %); a death seen noticed p90 (<= 0.05 s); seen track-frames without a truth mob (0) | 99.35 % of 2,783; 0.000 s; 0 | the same | met |
| feet: hops within 1.5 px rms (>= 91 %); jolts (<= 556) | 91.4 % of 919; **550** | the same | met |
| **L1 mobs: stand / air (>= 99 %)** | **764 of 783 = 97.57 %** | 715 = 91.32 % | **MISSED** |
| L1 mobs: the node of standing mobs (99.42 % accepted) | 546 of 549 = 99.45 % (the same 3 cases) | 515 of 518 | met (as accepted) |
| **L2, the 16 agreed cases without `none` (>= 90 %)** | **13 of 16 = 81.2 %** | 10 of 21 | **MISSED** |
| **L3, the 22 agreed cases (>= 95 %)** | **19 of 22 = 86.4 %** | 17 of 22 | **MISSED** |
| L8 (reported) | "yes": kept 20 of 20; "no": kept 6 of 6; "?": kept 14 | 20; 5 of 6; 14 | - |
| L2 apart, labelled `none` (fit misses) | 5: cases 34, 29, 24, 36 -> tracker mob; 71 -> ui / scenery | - | reported |

**Every miss, by case** (the rules as the user gave them against the labels):
- **L1 (19 of 783; 99 % allows 7):** the slope fixed 2 of the 20 "standing, placed in the air"; the flyer rule 18 of
  19 "fly, placed standing"; the relabel all 29. Left:
  - **12 within 5 px of the surface, placed in the air by the step rule** (1 px + 0.9 x the sideways step): 5 walk
    slopes steeper than 0.9 - slope 1.8-1.9: cases 2, 15, 195 (Drakes), 50 (Horny Mushroom), 46 (Evil Eye), steps of
    2-3 px up or down for 1 px sideways; 5 take a 2 px step for 1 px sideways on slopes of 0.56-0.86 (cases 37, 17,
    32, 10, 145: whole-pixel feet + camera); 155 (Zombie Mushroom, `stand_0`, a 6 px step), 184 (Evil Eye, `jump_0`,
    -3 / +4 px).
  - **6 with feet 9-35 px off the surface** (the fit's pose / feet): 24 (Evil Eye `jump_0`, -35), 158 (Evil Eye
    `hit1_0`, -15), 29 (Zombie Mushroom, -12), 34 (Zombie Mushroom, -9, a 9 px step up), 35 (Zombie Mushroom, 14 px
    under), 42 (Evil Eye `jump_0`, 18 px under; labelled node 460, under it 388).
  - **1 label:** case 124 (`232410_1#4` n 21529) - a Horny Mushroom (not a flying kind) in its die pose labelled `fly`.
- **L2 (3 of 16):** **case 30** (`#1` n 8163): a Zombie Mushroom behind another mob, its head 20 px over the screen's
  TOP edge - `edge` by the rule as written, labelled mob (also scenery); with the left / right edges only it would be
  right (14 of 16 = 87.5 %). **Cases 57 and 61: the tracker's `player` is not a player** (seen on the sheets and the
  facts): on 61 (`000219_2#0` n 22040) the tag list holds OUR tag merged with the Bubbling's name ((716, 481, 111, 21)
  beside our tag (716, 481, 74, 17)) - only we are over the mob (labelled us); on 57 (`#5` n 25429) it is the Horny
  Mushroom's own name tag ((802, 547, 104, 19)) under it - an effect and we are over it (labelled effect, also us).
  The tracker takes every tag of the list as a player's box (the prototype's rule; sorting the tags into ours / mobs'
  own / pets / players is step 4b's `players.py`). So "either of two" does not save them.
- **L3 (3 of 22):** **26** (`#2` n 11067: a Horny Mushroom walks out from behind the HUD's bars, its feet within 10 px
  of the play area's bottom) and **47** (`#0` n 2236: out from behind a skill effect beside the UI panel, its feet
  within 70 px of the left edge) are uncovered by the picture, "came into view" by `edge_px` (70 / 70 / 10 / 60);
  **41** (`#13` n 58322): the sheet shows the Drake standing in the same place from 0.6 s before its birth - "there at
  entry" by the picture (the tracker's answer), labelled uncover. Case 45 is right now (the die pose's fade).

**The live path** (`20261120_235747_1#0`, a new kept replay on today's scene build into
`F:\dev\maple-corpus\work\20261120_235747_1#0\track_s3\` - code f97dd4e, clean; `track\` untouched; 15,211 frames, 0
without a camera, observe 264 s): **the shadow rows = the bitmap replay's on 79,429 of 79,429 track-frames (100.000 %,
>= 99.5)**; **the GPU evidence = the bitmaps' on 9,865,891 of 9,865,891 places asked (100.000 %, >= 99.9)** over
10,736 frames - met. **`gate.py --base cef6d78`** (the tree before step 3, full set: ant4, ant4b, steam, line1,
transfer, darkcave): **SAME** - world.py's tracks found 100.0 / 100.0 % both ways, sighted 100.0 % on every clip.
**The ms** (`replay_mobs.py time 20261120_235747_1#0`: the live Perceiver, the first 3,000 frames, shadow on / off in
turn x 3, the main folder with `assets/scene`, performance cores, Ultimate Performance; the game was running in the
background, the A/B interleaved in one process):

| Gate | Measured | |
|---|---:|---|
| the tracker's ms p50 (<= 1.0) | **1.042 / 1.047** (`MobTracker.update` timed exactly, two runs; the part `track`, kept to 0.1 ms: 1.0) | **MISSED** by 0.05 |
| the tracker's ms p90 (<= 2.5) | 1.25 / 1.27 (part `track` 1.2; p99 1.5) | met |
| the whole frame's p50, shadow on - off (<= +0.3) | 14.53 - 13.55 = **+0.97 ms** (each of the 3 pairs +0.99 / +1.03 / +0.91) | **MISSED** |
| today's world + looks (beside it, for scale) | p50 0.9-1.0, p90 1.8-1.9 | - |

**The profile** (stop rule 3; cProfile over the same 3,000 frames, its numbers inflated ~30 %): the mean is 0.80 ms -
a frame with every track seen costs ~0.4 ms (the pairing: `_sights` + `_costs` + `_apply` + `place`, ~5 tracks),
a frame with a track to test (58 % of frames: 238 places asked p50, 1,274 p90) ~1.05 ms, of which the GPU evidence
call is ~0.6 ms - `Gpu.count` (0.24 ms of Python a call + the torch gather, its `shows` map made once a frame from the
frame - expected: `.float()`, `.abs().amax()`, and the one transfer back that waits for the GPU); `_test` itself 0.07
ms. So the p50 falls in the testing half. While world.py runs beside it the frame pays both: +0.97 ms; the gate's
+0.3 holds only against a frame without world.py's 0.9-1.0 ms (step 9). Nothing tuned (stop rule 3).

**pytest:** the whole suite green; the bot speed line 14.0 ms a tick (p90 15.6; `track` 0.4 of it) - unchanged (try
1: 15.4, step 7: 14.5; the machine's noise).
**Also found:** 85547b9 (try 1) rewrote `perception/perceiver.py`'s line endings (468 / 444 lines in `git diff
--numstat`; 24 real lines added) - harmless, noise in its diffs.

**For the user (try 3 or accept):** (1) **L1** - the step rule: on slopes steeper than 0.9 mobs walk (Drakes, Evil
Eyes, Horny Mushrooms on 1.8-1.9), and 1 px sideways can show 2 px up or down on any slope: let the step follow the
foothold's own slope (+ 1 px of whole-pixel slack)? The 6 feet 9-35 px off are the fit's (stop rule 4); case 124's
label `fly` -> `stand` / dying? (2) **L2** - the screen's top edge counts for `edge` (case 30 wrong) or only the sides?
The tag list's own tag and mobs' own name tags taken as players (57, 61): sort them now in the mob tracker (a tag at
our tag's place is ours; a tag under a mob is its own) or wait for step 4b and grade L2 on 14? (3) **L3** - a mob
uncovered inside the edge band is "came into view" (26, 47): narrow the band, decide by what hid it, or relabel? Case
41: relabel `entry` (the picture)? (4) **The ms** - is the whole frame's +0.3 meant against today's frame with
world.py (then the shadow cannot meet it while both run: +0.97) or against world + looks replaced (the new 1.04 vs
0.9-1.0)? And the p50 1.04 against 1.0: make the GPU evidence call cheaper (the `shows` map and the gather), or
accept?

**The user's decision (2026-11-25): step 3 accepted as it is, DONE** ("seems good to me ... stop here and continue";
no try 3). What was missed is carried, not dropped:
1. **The step rule on steep slopes (L1's 12 within 5 px):** a mob walking a slope steeper than 0.9 (Drakes, Evil
   Eyes, Horny Mushrooms on 1.8-1.9), or a 2 px whole-pixel step on any slope, is placed in the air on that frame.
   A real tracker mistake (not the labels'): **fixed now, in its own session before step 4b** (the user,
   2026-11-25: "lets fix the slopes"; prompt "Tracker, step 3, the slope fix"): the step follows the foothold's own
   slope + 1 px (us are placed by the same rule), L1 re-run (>= 99 %). Case 124 (a dying Horny Mushroom labelled
   `fly`) is relabelled `stand` with it. The 6 feet 9-35 px off are the fit's (stop rule 4).
2. **L2's cases 57 and 61** (our own tag and a mob's own name taken as players) and **case 30** (the screen's top
   edge): **step 4b** sorts the tag list (ours / a mob's own / pets / players) and uses the sides and the window's
   bottom only for `edge`, then re-grades L2 on the 16 (>= 90 %).
3. **The whole frame's +0.3 ms** cannot hold while world.py runs beside the shadow (both are paid: +0.97):
   **step 9** measures it after world.py goes, against today's frame. The tracker's p50 1.04 ms is accepted.
L3's 26, 47 (uncovered inside the edge band) and 41 (there at entry by the picture) stay as reported.
**Carry-over 2 done in step 4b** (L2 15 of 16 = 93.8 %: "Step 4b, 2026-11-25").

### Step 3, the slope fix (2026-11-25): built; every row MET but L1, MISSED by one case (98.98 %) - ACCEPTED by the user
Branch `tracker-build` (the main folder). **Built:** `track/graph.py`'s step rule = `|dy| <= 1 px + ceil(|the
foothold's own slope| x |dx|)` - the slope of the surface the thing stands on at its x (at a joint the one going
on, at a chain's end its last foothold: a new block of the table's row, `[|own slope|] * K1`); the rise is
**rounded up to a whole pixel**, because read word for word ("slope x the step + 1 px") a 1 px step on a 0.6 slope
allows 1.6 px and the prompt's own test (2 px for 1 px on 0.6) fails; feet and camera are whole pixels. Flat ground
keeps 1 px however far sideways. `config.Track.stand_slope` (0.9) is gone (nothing else read it). Tests:
`test_the_step_follows_the_slopes_own_rise` (a 1.8 slope: 3 px for 1 px, 4 for 2; a 0.6 slope: 2 for 1; flat:
1 px) and the changed `test_moving_up_or_down_is_not_standing` fail on the old rule (checked with HEAD's graph.py);
the plain reference rule of `test_place_equals_the_plain_rule_on_real_maps` has the new step (`step_ok`).
**Case 124 relabelled** `stand` (node 196, the feet 0.1 px off it; pose `die1`), `was: fly`, a `relabelled` note
with the user's words in `20261118_232410_1#4\labels\L1.json`; backup in
`F:\dev\maple-corpus\work\track-plan\step3\labels_before_slope\`. Outputs: `...\track-plan\step3\*_slope.pkl`.

What the tracker gave `place()` at try 2's 19 misses (a diagnostic run over the kept replay; dx, dy = the step since
the track was last seen, px; slope = the foothold under the feet): the 5 steep - 2 (-1, -2, slope 1.90), 15 and 195
(-1, +2, -1.90), 46 (+1, +3, 1.82), 50 (+1, +3, 1.90); the 5 whole-pixel - 37 (-1, -2, 0.79), 17 (+1, -2, -0.64),
32 (-1, +2, -0.64), 10 (+1, +2, 0.56), 145 (-1, +2, -0.86) - every one in the slope's own direction. **Two of the
"12 within 5 px" are not slope steps:** **155** (Zombie Mushroom `stand_0`: +1, **+6** on a 0.40 slope) and **184**
(Evil Eye `jump_0`: -3, **+4** on a 0.09 slope) - no rule of the slope places them `stand`. So the expected 99.2 %
(6 misses) counted them as fixed; with them L1 has 8.

| Gate | slope fix | try 2 | |
|---|---:|---:|---|
| **L1 mobs: stand / air (>= 99 %: 7 misses allowed)** | **775 of 783 = 98.98 %** (8 misses) | 764 = 97.57 % | **MISSED by 1** |
| L1: the node of standing mobs (99.42 % accepted) | 557 of 560 = 99.46 % (the same 3: 113, 190, 171) | 546 of 549 | met (as accepted) |
| step 2's hops: air called standing (<= 0.8 %) | 126 of 26,811 = 0.47 % | 124 (0.46 %) | met |
| step 2's hops: standing called air (<= 0.2 %) | 970 of 555,561 = 0.175 % | 1,014 (0.183 %) | met |
| the 13 captures' rows (found, id kept + by length, one id, extra ids, changed mob, next to its set, death p90, ghosts) | 98.70 %; 93.48 % (97.0 / 96.5 / 94.1 / 79.4 / 77.4); 90.98 %; 1,019; 7; 99.35 % of 2,783; 0.000 s; 0 | the same | met |
| feet: hops within 1.5 px rms (>= 91 %); jolts (<= 556) | 91.4 % of 919; 550 | the same | met |
| pytest `tests/test_track_graph.py`, `tests/test_track_mobs.py` | 43 passed | - | met |

The only other change in the pooled rows: one cover gap of 0.6-1.5 s fewer held (214 / 277, was 215 / 278).
**The 8 L1 misses left:** the 6 feet 9-35 px off (24, 158, 29, 34, 35, 42: the fit's, stop rule 4) + **155**
(6 px down for 1 px sideways, `stand_0`, 2.6 px over a 0.4 slope) and **184** (`jump_0`, 4 px down for 3 px, 2.3
px over a 0.09 slope) - a real step the rule calls a jump (a pose or feet jump of the fit between frames, or a step
measured over more than one frame: the step is since the track was last seen, up to `ballistic_s`).
**Cost:** `place()` of 20 things +1.5-2 us (Line 1 19.8-20.3 -> 21.8-22.1 us best of 7, the largest map 21.0 ->
22.6-23.1; an A/B in one process, idle machine; the extra gather + ceil) - step 2's 20 us line was not part of
this gate.

**For the user:** L1 misses 99 % by one case. (1) Accept at 98.98 % (155 and 184 are not slope steps; the rest is the
fit's), or (2) a rule for 155 / 184 (e.g. the step per frame when the track was last seen frames ago, or a pose
that does not move the feet), which is a new rule, not this fix - or (3) look at 155 / 184 frame by frame first.
**The user's decision (2026-11-25): (1) accepted** ("1. accepted") - L1 stands at 98.98 %; the slope fix is DONE.

### Step 4a, 2026-11-25: the drop tracker built; the gate MISSED on 2 rows (stopped)
Branch `tracker-build-drops` (worktree `.claude\worktrees\drops`, off 7ef68e3). **Built:** `track/drops.py` (proto_drops
ported: its docstring holds the rules; the constants in `config.Track`, the `drop_` / `bob_` / `hop_` / `look_` /
`reach_` / `from_` fields), the drop record `state.Drop` (+ `DROP_COVERS`), `tools/perc/track/replay_drops.py` (`run`,
`numbers` = proto_drops' own `numbers()` on the real tracker + the gate's rows, `port`, `l6`, `sheets pairs|hops`),
`tests/test_track_drops.py` (14 tests). Outputs: `F:\dev\maple-corpus\work\track-plan\step4a\`. perception/drops.py,
the Perceiver and FrameFacts are not changed; nothing calls the drop tracker live yet (the step does not ask it, and
the live frame has no key events: step 4b / 9). Its look asks `track/evidence.py`'s one interface (one call a frame
for every drop looked at), so the GPU source answers it as it answers the mob tracker.
- **"We took it" reads the pickup key's STATE** (the user): the key down at some moment from 0.75 s before the drop's
  last resting frame to 0.02 s after it - pressed in that window or held through it - with our feet in reach then.
  `test_the_key_held_through_the_window_is_we_took_it` fails with the press rule (checked).
- **from_mob reads the real mob tracker** (track/mobs.py's records: a track's first die pose = a death; taken back by
  a live pose = forgotten), not the truth's chains the prototype read.
- **The port (stop rule 2), `port --sound` on a `run --truth` (the truth's deaths, as the prototype):** the 13
  captures give the prototype's 746 lives one for one - item, x, birth frame, end frame, how, from_mob, landed, twin,
  covers equal on 746 of 746, except 1 "how": `232410_1#1` an Orange Potion is "we took it" (the key went down 0.778 s
  before its last resting frame, still down 0.737 s before: in the window by its state, outside it by the press).

| Gate (from the kept replay, 13 sound captures; the real mob tracker's deaths, keys.jsonl) | track/drops.py | the prototype | |
|---|---:|---:|---|
| drops (746, a count within 1 %) | **746** | 746 | met |
| lives with two items; over 131 s (0) | 0; 0 | 0; 0 | met |
| "gone" then seen again (0) | **1** (`232410_1#9`, below) | 0 as counted (1 by the same look: below) | **MISSED** |
| pairs of one item within 3 px, not both sighted on a frame (<= 9, each looked at) | 9, all looked at: 8 two real drops, 1 one drop under two lives | 9 | met |
| exactly one death (>= 84.4 % of those that landed in view) | **88.5 %** (630 of 712; none 6.5 %, several 5.1 %) | 84.7 % (the truth's deaths) | met |
| "we took it" with the key down: no hop without it on any of the 13 | **35 hops without our key down**, on 8 captures of 2026-11-18 (`#1` 9, `#2` 7, `#4` 5, `#5` 4, `#7` 4, `#9` 4, `#3` 1, `#12` 1); 0 on the 30-minute and the 4-minute capture | 36 | **MISSED** |
| L6 (>= 90 %; the 38 answered, 12 "?" left out) | **37 of 38 = 97.4 %** (the truth's deaths: 38 of 38) | - | met |
| PLAN-loot's gates still met | the finder, the Perceiver, FrameFacts unchanged (`git diff`: config.py, track/state.py, proto_drops.py's report only) | - | met |
| ms a frame p50 (<= 0.2; Python, its looks included, the bitmaps' decode apart) | **0.197** (p90 0.505, p99 0.925; the 30-minute capture alone 0.254) | 0.136 (0.192) | met (by 0.003) |

Measurement 5's other rows, the real tracker: ended - we took it 236, 130 s old 180, capture ended 155, gone in view
122, found gone 53 (the prototype 235 / 180 / 155 / 123 / 53: the Orange Potion above); alive at once p50 20, max 43;
of a drop's frames on screen sighted 91.3 %, covered 3.0 %, at the edge 2.1 %, under the UI 3.3 %; "gone" noticed 0.163
s (p50) after its place first shows empty, 0.05 s after the hop's last frame; deaths 981 (the truth: 964), 14 taken
back. The L6 miss (case 24, `232410_1#5` n 25642): two Horny Mushrooms overlapping swap poses; the tracker took track
8's first die pose (426.112 s, the label's death) back for 0.08 s and it died again 0.17 s later at the same place -
from_mob names track 8, the labelled mob, but by a death 0.17 s after the label's (the grade asks 0.1 s).

**The two misses, looked at:**
1. **The 35 hops are the pet's pickups, not a key held.** Measurement 5 read the 36 hops of the older captures as "the
   key was held"; the key log says otherwise: on all 35 the pickup key was UP - released 1-20 s before, or never
   pressed in the stay before it (`#2`, `#4`, `#5`, `#9`, `#12`; `#9` has no pickup press at all). 28 of the 35 drops
   were under 5 s old; our feet were over 32 px away on 29. By eye (`sheets hops`, 5 of the 16 sheets, 15 cases): a
   pet named **"Snail"** (its own name tag) stands at or beside the drop on 13 and the item hops toward it; on 2 the
   item leaves the tile away from us. The 2026-11-18 captures were played with that pet out; the 30-minute capture has
   none and 0 such hops. The 3 on `#7` are a pile of 6+ drops where three presses came with our feet 64-113 px away
   (reach 32) and the pet beside it. The 36th is the Orange Potion above (the key's state). So the rule answers right
   (a pet's pickup is "gone in view", not "we took it"); the row assumed footage without a pet.
2. **The one "gone then seen again" is real: a flight read as a pickup hop.** `232410_1#9`, an Evil Eye Tail at x 189:
   life 45 was declared gone at 811.16 s because a second Evil Eye Tail (from another Evil Eye's death 50 px away) flew
   past 20 px above it - rule (a) takes ONE hop sighting 12+ px up as "it left". The tail stayed (under another player
   and effects, its sightings broken for 1.1 s): its heights go on with the old bob (top ~1880 at 810.9 s, bottom
   ~1885 at 811.9 s; a drop that has just landed starts at its bob's bottom - HeavenClient Drop.cpp: `moved` = 0
   when it lands), and the old bob fits life 55's first 65 sightings to 0.25 px. The prototype has the same two lives
   (the port is exact); its count left this one out because its flight-following (a measurement aid, not ported) took
   the passing tail for life 55's own flight - so its 0 was 1. A fix is a rule change (e.g. "gone by the hop" only
   from 2 hop sightings on - the prototype's own "the hop seen" in its report - or the hop's sightings must start at
   the drop's own height): not made (stop rule 1).
**The 9 pairs:** P01-P03, P05, P09 the second item seen flying in and landing on the first (the sheets); P06-P08 the
older life's bob is 3.3-3.6 px off the newer one's heights (one drop would fit to ~0.3 px): two drops 1-2 px apart;
**P04** (`232410_1#1`, a Horny Mushroom Cap at x 1254, lives 9 and 45) is ONE drop: its place was out of view for 80
s, and when it came back the cap's bob no longer fitted (the client restarted it although we were under 1,700 px
away), so it was born again while life 9 was kept beside it - both ended together when the pet took it.
**The ms:** measured alone on an idle machine, pinned to the performance cores, the 13 one after another in one
process with the mob tracker beside it as live (`run --sound --pin --tag solo`: the same 746 lives). The first
numbers (4 captures at once, each with its mob tracker) were p50 0.205; with the truth's deaths (no mob tracker) 0.150.
Slower than the prototype: a look costs 0.11 ms against its 0.036 - the evidence interface counts every picture x
height of a drop in one gather (`Bitmaps.count`'s indexing) where the prototype counted crops and stopped at the first
fit; on a frame without looks the bob's 3 x 3 solve per sighted drop (`np.linalg.solve`, as the prototype: ~24 drops
on screen on the 30-minute capture) is the largest part, the records ~0.03 ms. Not tuned (the row is met).
**pytest:** the whole suite green (config.py changed); the bot speed line 15.0 ms a tick (p90 17.5) - unchanged (step
3: 14.0-15.4; the drop tracker is not in the live frame).

**For the user:** (1) the hop row on pet footage - accept 35 as the pet's (the rule is right, the row assumed no pet),
or ask a pet-off re-check / a "taken by another" how; (2) the false "gone" by a passing flight (1 of 746) - a try 2
with the hop rule (2 hop sightings, or starting at its own height), or accept; (3) the ms meets 0.2 by 0.003 (the
30-minute capture alone 0.254) - as it is, or a cheaper look before step 9.
**The user's decision (2026-11-25): step 4a DONE as it is** - (1) the 35 hops: accepted as the pet's pickups; (2) the
false "gone" by a passing flight (1 of 746): accepted, the hop rule unchanged; (3) the ms: kept. Merged into
`tracker-build` the same day.
### Step 4b, 2026-11-25: other players and us built, in shadow; the port exact; the gate MISSED on L5, L1 us, SelfState, our feet known and the ms (stopped)
Branch `tracker-build` (the main folder). **Built:**
- `track/players.py` - proto_players ported (its rules and constants in `config.Track`): the tag list sorted per frame
  (`tag_class`: ours / log / mob / npc / text / pattern / pet / player / unsure / short / none), tracks in map
  coordinates by the tag's width, **two tags side by side split by the widths known** (the prototype's `_together`:
  the other track placed inside the box by its own width at the edge that kept its place, both drawn), pets sorted out
  and not tracked (their class kept), the 2 s cover, the feet (the tag's centre x, its top - 1) placed by the graph's
  rule, `state.Player` records for the tracks whose class is player NOW, events `player_new` / `player_left`. Two
  things the prototype did in hindsight are done as the frames come: **the class is the vote so far** (the
  prototype's `cls()` at the track's end), and **mob kinds' own tag boxes are learned while running** (known after 20
  sightings near the mode; the prototype learned them over the whole capture first). What stands on a tag (the body's
  height) comes from the evidence: `Evidence.columns` (the bitmaps: a slice per tag; the GPU: dump.py's formula at the
  asked pixels).
- `track/us.py` - our feet = FrameFacts.tag (exact) or, within 2 s of it, a box of the tag list of **our own width**
  (by its centre) or **a piece of our tag** / a wider box we are in (by the edge that kept its place); placed by the
  graph's rule (we climb) + every stuck case of nav/selfstate.py's docstring (hovering at a rope's height within 16 px
  of it = on it, staying on a rope while not moving sideways, a walk key held 0.4 s without moving next to a ladder =
  hanging on it - not within 0.9 s of another key -, still just past a platform's end = on its end); vx, vy over 0.2 s;
  `facing` = the last left / right key down; `act` = climb / air / walk / stand (swing, hit, dead: with step 5's casts);
  the HUD's numbers held while unreadable; the slots (step 7).
- `track/mobs.py` (step 3's carry-over 2): the covers' us / player boxes from the SORTED tags (`update(..., tags=)`:
  our body around our tag, players and pets at their own widths - not mobs' own name tags, log lines, text); `edge` =
  the screen's sides and the window's bottom (not the top). A pet is named a `player` cover (COVERS has no pet).
- The Perceiver runs us, the players and the mob tracker in shadow (parts `us_players`, `track`; D's patches are read
  before them now); our keys are not handed in live yet (step 9). `graph.npcs`; `state.Player`.
- Tool `tools/perc/track/replay_players.py` (`run [--port]`, `port`, `l5 [--final] [--port]`, `cover`, `us`, `ms`,
  `time`); `replay_mobs.py run` gives the mob tracker the sorted tags as live (`--unsorted`: step 3's runs). Outputs:
  `F:\dev\maple-corpus\work\track-plan\step4b\`, `...\step3\*_s4b.pkl`.
- Tests: `tests/test_track_us.py` (19: every stuck case, our tag from the list, facing, blind, HUD), `test_track_players.py`
  (13: the classes, the split, the cover, ours, columns GPU = bitmaps), `test_track_mobs.py` +2 (the top is no edge, the
  sorted tags); each rule switched off fails its tests (hover tolerance, hover time, the walk hang, the ledge, the
  split, the two mob changes).

**The port = the prototype** (`run --port`: the prototype's own inputs - its hindsight mob-tag boxes and its ours*
rule): **every track equal** (id, final class, first frame, last sighting, how it ended) - **1,095 of 1,095** on the
30-minute capture, **203 of 203** on the 4-minute one; **the body over a tag equal on 235,436 of 235,436 tags** (and
35,541 of 35,541) against the prototype's slim cache. (The step-1 L5 picks ran `proto_players.run` with its DEFAULT
minimap, 215 x 195, not the measured 277 x 152; the by-eye labels do not depend on it.)

| Gate | Measured | |
|---|---|---|
| L5: players found (>= 95 %) | **178 of 241 = 73.9 %** (the class so far; 47 of the misses are `short`: a track under 6 sightings). On the track's final class 85.9 %; **the prototype's own rules and inputs: 85.1 %** | **MISSED** |
| L5: non-players called players (<= 1 %) | **17 of 420 = 4.05 %** (15 pets, 1 none, 1 text); final 4.29 %; the prototype 4.29 % | **MISSED** |
| L5: a pet called a player or a player called a pet (<= 5 %) | **22 of 323 = 6.81 %** (15 + 7); final 8.05 %; the prototype 8.05 % | **MISSED** |
| L5: the node of standing players (>= 95 %) | **147 of 164 = 89.6 %**; final 88.4 %; the prototype 89.3 % | **MISSED** |
| the 2 s cover: the same player back under a new number (<= 29) | **29 of 280 player tracks** (the prototype's inputs: 29 of 279) | met |
| L1 us (>= 99 %) | **152 of 182 = 83.5 %** (the node 128 of 129) | **MISSED** |
| every stuck case of selfstate.py's docstring a test | its 7 cases (a hover at a ladder, staying on a rope 10 px off, under a ladder's top, the walk hang, no hang within 0.9 s of another key, a found hang holds, a platform's end) + 5 guards that they do not reach too far (a jump apex, walking past a ladder top, leaping off, falling / walking off an end): 12 of `test_track_us.py`'s 19; each rule switched off fails them | met |
| us against SelfState, 30-minute capture: the same place (>= 99 %), every difference listed | **101,964 of 106,428 = 95.81 %** (both from our own tag this frame; 3,654 frames without it apart) | **MISSED** |
| our feet known (>= 97.5 %; today 96.7) | **97.04 %** (our own tag 96.68 + the tag list 0.36); the 13 captures 76.3-100 % (list +0.0-14.6) | **MISSED** |
| ms p50 (<= 0.1) | **replay (CPU bitmaps, the decode apart): 0.19** (players 0.145, us 0.04); **live (the Perceiver, 4-minute capture, part `us_players`): 0.7** (us 0.09, players 0.62 - of it the GPU `columns` call 0.45 for one tag at the median) | **MISSED** |
| carry-over 2: L2 on the 16 (>= 90 %) | **15 of 16 = 93.8 %** (`replay_mobs.py labels --tag s4b`): case 30 (the top) and 61 (our tag merged with a Bubbling's name) right now; 57 still `player` - the Horny Mushroom's own tag cut to 104 of its 132 px, the mob not seen that frame (no "mob" vote without a seen mob's feet), the mob standing on it read as a short body: a pet, named a player cover | met |
| the 13 captures' rows with the sorted tags (step 3's gate) | found 98.70 %, id kept 93.48 % (97.0 / 96.5 / 94.1 / 79.4 / 77.4), one id 90.98 %, extra ids 1,019, changed mob 7, next to its set 99.35 % of 2,783, death p90 0.000 s, ghosts 0; L1 98.98 %, node 99.46 %, L3 19 of 22 - **identical to the slope fix's** (only cover names can change) | met |
| pytest (whole suite: config and the Perceiver changed) | green; **bot speed 14.9 ms** a tick (p90 16.8), of it `us_players` 0.8 ms (the slope fix's runs: 14.0-14.5) | - |

**Asked with the prompt: the mob tracker's ms on Ant Tunnel** (`replay_mobs.py time 20261118_232410_1#1` - Ant Tunnel II, the
heaviest remembered jumpers on the replay: CPU evidence p90 15.9 ms; the live Perceiver, 3,000 frames, shadow on / off x
3, performance cores, Ultimate Performance, the drops session idle): the part `track` **p50 0.30, p90 1.30, p99 1.9 ms**
(Line 1, step 3: 1.04 / 1.25 / 1.5); the whole frame 13.84 against 12.50 = **+1.34 ms** with the shadow on (the switch
now holds us + the players + the mobs; Line 1's +0.97 was the mobs alone).

**Why, by case:**
- **L5 (the rules', not the port's: the prototype scores the same):** players called `short` (live only: under 6
  sightings, 3 whole); **pets and players swapped by the body's height** (55 px parts a character from a pet: measurement
  7's by-eye check already had 5 of 20 "pets" be players); mobs' own tags called pet / short before their box is learned
  (live: 16 `mob` against 29 on the final class). **The node, 17 misses:** 16 have the feet more than 3 px off the floor
  - 7 stand still exactly **4 px over it** on a **21 px tag** (a medal over the name; ours is 17) or on a track whose
  commonest box is 21 px: "feet = the tag's top - 1" holds for a 17 px tag only; from the box's bottom (bottom - 18) they
  stand. The other 9 are 7-30 px off (jumps, a wrong box).
- **L1 us, 30 misses** (every one with its motion: our own tag over frames -3..+3): **~20 are jumps labelled stand** -
  our feet rise or fall 3-10 px a frame, 6-36 px off the labelled floor (cases 114, 127, 112, 162, 132, 121, 118, 61,
  124, 137, 116, 129, 150, 42, 130, 24, 110 ...; by eye on a strip of 114 and 127: mid-jump, the floor out of view under
  the tag). L1 try 3 gave strips only to cases near a rope; these were judged on one frame. **6 are a fall or jump past
  a rope labelled air (strip-judged) that the graph's rope rule calls `rope`** (cases 77, 54, 104, 83, 107, 99: within
  7 px of its x between its ends - the rule has no motion test). 3 others: a rope's id -6 / -5 (102), a rope not taken
  while moving right after the tag came back (134), standing still near a platform's end (136).
- **SelfState:** every difference is at a change of place, where the two rules differ by design: we air / SelfState
  ground 2,118 (take-off and landing frames: feet 0-10 px off, moving 2-5 px a frame - its 9 px tolerance and 0.2 s
  speed window), we stand / SelfState air 1,871 (feet exactly on the floor, still: its speed window still over 90 px/s
  after a landing), we stand / SelfState rope 390 (stepped off a ladder: its "stays on the rope"), we rope / SelfState
  ground 74 (climbing at a ladder's end), 11 rope / air either way.
- **Our feet known:** the prototype's 1,179 "ours from the list" frames were its loose rule (any tag overlapping our
  last place within 2 s, no width): by eye, 20 of them - **11 our own tag partly hidden by front scenery** ("Jenk",
  "Jenki", "sJob": a post, a lever), 9 another player standing there, a Bubbling's own tag, a player beside us. On the
  30-minute capture our whole 74 x 17 tag is in the list on 0 of the 3,654 frames our reader misses it. The width / edge
  rule takes the pieces: +0.36 points (393 frames), never another tag.
- **The ms:** live, the body question is one GPU round trip a frame (the gather is tiny; the transfer back waits ~0.4 ms
  on this driver - step 3's evidence call pays the same); D's mask cannot answer it (eroded 3 x 3 and grown 13 x 13, not
  the pixels) and changing D is the scene model (stop rule 4). Without it, us + players are ~0.15-0.25 ms of Python
  (two placement calls ~15 us each, the vote, the records).

**For the user:** (1) **L5** - the targets were never met by the prototype's rules (85.1 / 4.29 / 8.05 / 89.3): accept,
or change rules - feet from the tag's bottom (the node), a pet by its name's width over the stay (proto_players'
`name_vote` option), players before 6 sightings? (2) **L1 us** - relabel the ~20 jump cases on strips (as L1R did for
ropes), and a motion test in the graph's rope rule (a fall past a rope is not on it)? (3) **SelfState 95.81 %** -
accept the listed differences (SelfState's 9 px and its speed window are what the one rule replaced)? (4) **Feet known
97.04 %** - the list gives 0.36, not 1.1: accept, or another source? (5) **The ms** - accept the live 0.7 ms while both
trackers run beside world.py, ask the body one frame late (no wait), or merge it into the mob tracker's one transfer?

**The user's answers (2026-11-25), built in "Step 4b, try 2":**
1. Players seen fewer than 6 times are graded **"not yet known"**, not as misses; the delay (frames until the class
   is known, p50 / p90) is reported beside L5.
2. A player's feet come from the tag's **BOTTOM** (a 21 px medal tag stood 4 px high with "the top - 1").
   **Amended by the user (2026-11-26) on try 2's measurement** (players standing still, whole tags, the 30-minute
   capture: tag bottom - floor = 18 for 17 px tags (14,975), **20 for 19 px (16,903: the box grows DOWN)**, 21 for 20
   px, 23 for 22 px, **18 for 21 px (3,355: the medal grows the box UP)**): **"top, except 21 px"** - feet = the tag's
   top - 1, and for a 21 px tag its bottom - 18.
3. **Pets:** the user - "pets have no discernible difference in name from another player, height rule is ok, but
   don't be pixel perfect on height, give it some slack as slightly larger pets might be introduced (still they will
   always be shorter than players)". So MEASURE first, from L5 and the replay: the body heights of labelled pets and
   of standing players (min / p1 / p5 / p50), and which sightings make players look short (prone, sitting, covered,
   the edge, a jump). The line goes just under the shortest standing players (a margin below their p1), as far above
   the tallest pet as that allows - both gaps reported; a track is judged by its tall sightings over the stay (a high
   percentile of its heights), not per frame. Players and pets overlapping (no gap): stop with the numbers.
4. L1's ~20 "us" jump cases are **relabelled on strips** (as L1R did for ropes; the bank's file, `was` + a note,
   backup first).
5. The graph's rope rule gets a **motion test**: falling or jumping fast past a rope is not on it (cases 77, 54, 104,
   83, 107, 99); what it changes on step 2's hops gate is reported.
6. **One GPU round trip a frame:** the tag list's body question rides in the mob tracker's evidence transfer; the
   live ms before / after (the Perceiver, the 4-minute capture, parts `us_players` and `track`).
7. **Accepted as they are:** us against SelfState 95.81 %, our feet known 97.04 %.

### Step 4b, try 2 (2026-11-26): the answers built; step 3's rows, the hops gate and one transfer a frame MET; L5, the cover, L1 us and the ms MISSED (stopped)
Branch `tracker-build` (the main folder). **Built** (each rule's test fails with the rule switched off - checked):
- **Answer 1** (`replay_players.py l5`): a tag on a track seen under 6 times = "not yet known", left out of the rows;
  `_Track.known_n` = the frame its class first was more than `short`.
- **Answer 2, as amended by the user** (the measurement above): `_Track.feet_y` = top - 1; a 21 px box
  (`Track.tag_medal_h`): bottom - 18. Test `test_feet_from_the_top_or_a_medal_tags_bottom`.
- **Answer 3, measured first** (`replay_players.py heights`, `tools/perc/track/height_sheet.py`; sheets
  `...\track-plan\step4b\heights_*.png`, `short_*.png`): L5's labelled pets and standing players, each through its
  track over the stay. **Per sighting the two overlap** (pets p95 73 px, players p1 9 px); **per track, the 75th
  percentile of its whole, alone sightings, on tracks of the labelled tag's own name: pets 35-41 px (30 tracks) +
  2 at 64 and 95; players 57-120 (p5 64, p50 68; 80 tracks) + 1 at 36.** By eye every crossing track is **two
  characters on one track** (a pet's and its owner's tags merged and parted: "GODxWAR"+"Snail", "CGFzealot",
  "GTH" / "Blac" pieces), not a height. 34 labelled pet tags and 66 player tags sat on a track of another name on
  their frame (left out of the heights). **Players reading short** (2,858 of 31,829 readings under 55 px): a shared or
  joined box 893, the screen's edge / UI 225, in the air or on a rope 441, whole and standing 1,299 - 19 of 20 of
  those by eye one player in a spear attack stance, the column falling **between its legs** (10-22 px); that
  player's tracks read >= 50 px on 79-93 % of sightings, p75 64-68. **Built:** `pet_q` 75, `pet_line` 50 (7 px under
  the shortest clean player track, 57; 9 px over the tallest clean pet track, 41); the class from `hb1` / `hb`, the
  track's height counts (`cls()`), recomputed only for tracks that changed. Test
  `test_pet_or_player_by_the_upper_quartile_of_its_heights` (the prototype's vote calls its first case a pet).
- **Answer 4:** set **L1J** (`label_sets.py jumps`, `jumps-write`; BRIEF.md "Us around a jump or a fall"): every L1
  case where our own tag moves >= 3 px a frame within 0.1 s and L1R had not judged on strips - **43 cases**, one
  strip sheet each; first look (a fresh labeller, all 43): 36 `a`, 7 stand, 0 `?`; **second look (another, blind, 5
  cases): 5 of 5 agree**. Written into the bank (backups `...\step4b\labels_before_l1j\`, each changed label with
  `was` + `relabel: L1J`, each file a `relabelled_us` note): **18 labels stand -> air**, 25 the same.
- **Answer 5:** `graph.place(..., vx, vy)`: a climber faster than `rope_vx` 100 px/s sideways or `rope_vy` 200 px/s up /
  down is not on a rope (measured: 27,105 rope frames of our own feet - sideways p90 27 px/s, climbing 100-150; the
  six cases 148-437 px/s sideways but case 54: the first frame of a jump OFF a rope, 1 px); us passes its 0.2 s speed,
  players their 5-frame vx and last-step vy; us's "stays on a rope" also needs |vy| <= rope_vy, and its loop adds a
  rope only for the stuck cases' wider reach (the plain 7 px case is the graph's, with its test). Tests
  `test_a_climber_moving_fast_past_a_rope_is_not_on_it`, `test_falling_or_jumping_past_a_ladder_is_not_on_it`.
- **Answer 6:** `Players.begin` sorts up to the body question and asks it (`Evidence.ask_columns` -> an `Answer`);
  the GPU queues the gather and **the mob tracker's `count` carries it in its one transfer** (`Gpu._transfer`; no
  count this frame: `end` makes it); the mob tracker takes the sorted boxes as a callable, asked only when it names
  a cover (`update(tags=callable)`); the Perceiver counts the players' `end` in `us_players`. Tests: the GPU columns
  ride in `count` (`trips` 1), the boxes asked only on need.

| Gate | try 1 | **try 2** | |
|---|---:|---:|---|
| L5 players found (>= 95 %; "not yet known" apart: 111 tags, 47 players) | 73.9 % | **180 of 194 = 92.8 %** | **MISSED** |
| L5 non-players called players (<= 1 %) | 4.05 % | **20 of 356 = 5.62 %** (17 pets) | **MISSED** |
| L5 a pet called a player or a player a pet (<= 5 %) | 6.81 % | **22 of 257 = 8.56 %** | **MISSED** |
| L5 the node of standing players (>= 95 %) | 89.6 % | **156 of 166 = 94.0 %** | **MISSED** |
| the delay until a player's / pet's class is known (reported) | - | p50 **9 frames** (0.15 s), p90 42 (0.7 s), p99 106; 496 tracks | - |
| the 2 s cover: back under a new number (<= 29) | 29 of 280 | **33 of 309** | **MISSED** (met in try 1) |
| L1 us (>= 99 %) | 83.5 % | **154 of 182 = 84.62 %** (93.41 % with the rope motion test off) | **MISSED** |
| step 3's rows (`replay_mobs.py --tag t4b2`) | - | found 98.70 %, id kept 93.51 % (97.0 / 96.5 / 94.1 / 79.4 / 77.4), one id 92.33 %, extra ids 994, changed 7, next to its set 99.35 % of 2,786, death p90 0.000, ghosts 0, hops 91.4 %, jolts 524, L1 98.98 %, L2 15 of 16, L3 19 of 22 - **identical to step 3b's (`f3s`)** | met |
| step 2's hops gate (`proto_feet.py --sound`, the real placement) | 126 / 970 | **126 of 26,811 (0.47 %) / 970 of 555,561 (0.175 %)** - unchanged (mobs do not climb) | met |
| one GPU round trip a frame (live, 4-minute capture, 2,970 frames) | two on most frames | **one on 2,669 frames, none on 301** | met |
| the live ms (the Perceiver, the same 3,000 frames, twice each) | us_players p50 0.7 (p90 0.9), track 1.0, frame 15.5 | **us_players 0.7 (p90 1.0), track p50 1.1 / p90 1.4, frame 15.65** | **MISSED** (p50 <= 0.1) |
| pytest (whole suite), bot speed | 14.9 ms | **green; 16.3 ms a tick** (p90 17.6; `us_players` 0.9, `fit` 7.2: step 3b's run 15.6 with `fit` 7.1) | - |

**Why, by row:**
- **L5 and the cover - the pet rule made pets worse:** 113 pet tracks against 142 (29 more players: 309). Of the 13
  labelled pet tracks now called players, **10 are the pet's tag taken by its owner's track** (the owner's box
  takes the pet's "by an edge" when the two merge and part - the track's identity, not its height) and 3 are the
  pet's own track reading tall under its owner (p75 64 / 95; one at 40 is "player" only on the labelled frame).
  The 75th percentile turns a pet that stands under its owner a quarter of the time into a player; the prototype's
  per-sighting vote needed half. The players found rose to 92.8 % and the node to 94.0 % (the medal anchor: 7 of the
  10 node misses left are 7-30 px off - jumps, a wrong box).
- **L1 us:** the 18 relabelled jump cases are right now; **the rope motion test breaks 22 grabs** - frames just after
  we caught a rope from a jump, strip-labelled `r` (the climbing pose shows), whose 0.2 s speed still carries the
  jump (104-257 px/s sideways) - and fixes 5 of the 6 pass-bys (54: a jump's first frame, 1 px). Measured on the
  same labels: **no motion test 93.41 %** (6 pass-bys, 1 rope, 5 stand), this frame's own step (> 1 px sideways or
  > 4 px up / down) 92.86 % (7 grabs), the 0.2 s window as built 84.62 %. The 5 "stand" left: cases 61, 137, 116, 110,
  136 (moving 58-221 px/s sideways; not in L1J: they were judged on rope strips or move under 3 px a frame).
- **The ms - try 1's reason was wrong:** a GPU sync right before the trackers costs **0.03 ms** - the GPU is idle
  there; the transfer does not wait on the driver. Live, p50: `players.begin` 0.39 ms, of it **`ask_columns` 0.37**
  (a 120 x 17 index block per tag built and uploaded, ~15 small torch calls), `players.end` 0.31, the one transfer
  0.17, `us.update` 0.09, the mob tracker 0.42. So one transfer a frame saves nothing; the cost is Python and torch
  calls, and players + us are ~0.8 ms.

**For the user (stopped, stop rule 1):** (1) **Pets** - keep the 75th percentile (pets standing under their owner turn
players), go back to a share (e.g. the prototype's "half"), or first stop a track taking another name's box (the
association: 10 of the 13)? (2) **The cover** fell to 33 with the pet rule - it follows (1). (3) **L1 us** - drop the
rope motion test (93.41 %), take this frame's own step (92.86 %), or keep the window (84.62 %)? 99 % is not reached by
any of them. (4) **The ms** - accept ~0.8 ms for players + us (the 0.1 was the prototype's 0.04 without the body), or a
cheaper body question (the index built on the GPU from the tags' corners; a track whose class is settled not asked
again)?

**The user's answers (2026-11-26, to the plan manager; prompt "Tracker, step 4b, try 3"):**
1. **Pets: classify only when not obstructed** - the user, on the sheet `step4b\heights_pet.png` (track 815 "Snail"
   holding the merged "GODxWAR" + "il" box, body 95; track 82 "Snai" holding "CGFzealot", body 64; the White Bunnies
   41 px on every frame beside their owner's tag): "players and pets should be classified when not obstructed",
   widened into the design rule "clean sightings teach, crowded ones only follow" (design 1). So: a track continues
   only on a box of its own name's width; a merged box is split by the widths known (why the existing split did not
   fire on 815: to find); the class, the height and the width learn only from sightings standing alone. The 75th
   percentile and the 50 px line stay. The cover follows.
2. **Ropes: "They are grabbed by pressing up or down"** (the user). For us: on a rope only when we got onto it with up
   or down pressed (the key down at the grab); staying on it needs no key; a jump or fall past a rope without the key
   is not on it, a grab mid-jump with the key is, whatever the speed. Replaces the speed test (which broke 22 grabs).
   Live, until step 9 hands our keys in, us uses the plain rule (no motion test). Players: no key known - the session
   measures no test / the speed test on L5's nodes and keeps the better.
3. **The ms:** a track whose class is settled is not asked the body question again; accepted against a new line set
   from what it then measures (the 0.1 was the prototype's, without the body).
4. **L1 us:** accepted at what the key rule reaches if 99 % is not (182 cases: 99 % allows 1 miss).

### Step 4b, try 3 (2026-11-26): design 1 and the rope key built; pet / player, the node, step 3's rows and the hops gate MET; players found, non-players, the cover MISSED (stopped)
Branch `tracker-build` (the main folder). Runs `replay_players.py ... --tag t4b3` (try 2's files untagged),
`replay_mobs.py ... --tag t4b3`.

**Measured first (the user's point 1):** sheet `step4b\heights_pet_taken.png` (`height_sheet.py --taken`): the 17
labelled pet tags called players sit on **13 tracks; 10 are a track of another width on the pet's tag** (52 "Snail" on
"Alistia", 195 / 82 on "CGFzealot", 697 on "Snail snorley", 705 "ImThat1Dude" / "Brown Puppy" swapping, 70 / 131
"KingKonGTH" on "Black Kitty", 857 a 150 px merged box learned as a width): the owner's track took its pet's NARROWER
box "by an edge" (try 2's piece rule), or the pet's track the owner's. **Why the split did not fire on 815:** "GODxWAR"
(69) and "Snail" (38) 3 px apart are put together by `_join` (the ladder-rail rule, tag_join 6 px) into ONE cut box
of 104 before the tracks are paired; the young track 815 took it by an edge as its own piece, and `_together`'s split
needs a track left WITHOUT a tag. 3 of the 13 are the pet's own track: 815, 82 (pieces of its owner's tag), 128 (player
only on the labelled frame).

**Built** (each rule's test fails with the rule switched off - checked):
- **Design 1 in `players.py`:** `_alone` - a tag is alone when whole and no other tag (or ours) is within `alone_gap`
  12 px on its rows and no other tag's centre within `alone_dx` 32 px sideways, `alone_dy` -120..+70 px (another
  character in its body column). Only alone sightings teach the width (`wc`, `known`), the tag's height, `clean`
  (tag_confirm) and the body heights of the class (`hb1`; **the fallback to every reading is gone**: fewer than 5
  alone readings = `unsure`); the class's other evidence counts on sightings of its own width (`nfull`), never on a
  shared box; a "piece" absorbed teaches nothing. A track whose width is **sure** (`clean >= tag_confirm`) pairs only
  with a box of its width or a CUT piece (edge / UI / joined / sticking out of ours) - never another name's tag; a
  young track as before. **`_split`:** a box no track took, wider than sure tracks inside it at one of its EDGES: the
  surest at each edge is seen there SHARED (follows, learns nothing); one track and the rest >= `split_rest` 20 px: the
  rest is a cut piece (a young track or a birth); the rest narrower: a wider tag over it, not split. Tests
  `test_two_tags_joined_into_one_box_are_split_too` (815), `test_a_known_track_never_takes_another_names_tag`,
  `test_crowded_sightings_teach_nothing`; the side-by-side test's tags now 20 px apart (10 px is "touching").
- **The rope key (`us.py`):** with our keys known (sticky once any are handed in), a rope the rule puts us on that we
  were not on the frame before is a grab only with up / down down within `grab_s` 0.1 s (key events count, a tap
  between frames too); staying needs no key; keys unknown (live): the plain rule. **The speed test is gone** from
  `graph.place`, us, players and config (`rope_vx`, `rope_vy`). Tests `test_a_rope_is_grabbed_only_with_up_or_down`,
  `test_staying_on_a_rope_needs_no_key` (a grab from a jump: the 0.2 s speed still carries it),
  `test_our_keys_unknown_the_plain_rule`.
- **Players' rope test, measured:** the speed test against none on L5 - **identical** (the node 137 of 145 both; every
  labelled player place the same: stand 204 of 217, air 10 of 10, rope 5 of 6). Kept the simpler: none.
- **The ms:** `_Track.settled` (a pet / player with `body_settled` 30 alone body readings, a mob's / NPC's tag seen 30
  times): its own tag where it would be now is not asked the body question. Test
  `test_a_settled_track_is_not_asked_the_body_question`.
- **Tried and taken out:** sure = one alone sighting (junk 27-31 px pieces became split members of a player's box on
  ~30 % of frames); split members by the sum of widths (wrong on overlapping tags); an alone box with one sure track
  in it re-teaching that track's width (for "FreakyRafiki" seen as "Rafiki", below): found +0.2, the node 96.5 -> 94.5
  %, cover 36.
- `docs/state_model.md`: design 1 and the rope key, in the user's words (after "Every other player").

| Gate | try 2 | **try 3** | |
|---|---:|---:|---|
| L5 players found (>= 95 %; "not yet known" apart: 133 tags, 56 players) | 92.8 % | **158 of 185 = 85.4 %** (20 `unsure`, 3 pet, 2 log, 1 mob, 1 ours) | **MISSED** |
| ... the same with `unsure` (under 5 alone body readings) set apart as "not yet known" - not the gate, for the user | - | 158 of 165 = 95.8 % | - |
| L5 non-players called players (<= 1 %) | 5.62 % | **7 of 343 = 2.04 %** (3 pets, 2 none, 1 mob, 1 text) | **MISSED** |
| L5 a pet called a player or a player a pet (<= 5 %) | 8.56 % | **6 of 238 = 2.52 %** | met |
| L5 the node of standing players (>= 95 %) | 94.0 % | **138 of 143 = 96.5 %** | met |
| the delay until a class is known (reported) | p50 9 / p90 42 frames | p50 12 / p90 77 / p99 251 (564 tracks) | - |
| the 2 s cover: back under a new number (<= 29) | 33 of 309 | **34 of 353** | **MISSED** |
| L1 us (>= 99 %, or accepted at the key rule) | 84.62 % | **173 of 182 = 95.05 %**, the node 99.22 % (the plain rule 93.41 %; grab_s 0 / 0.05 / 0.1 / 0.25 / 0.5: all 95.05) | accepted (answer 4) |
| us against SelfState (accepted 95.81 %) | 95.81 % | 95.70 % (new: 120 frames "no grab" air / SelfState rope) | - |
| our feet known (accepted 97.04 %) | 97.04 % | 97.04 % | - |
| step 3's rows (`replay_mobs.py --tag t4b3`) | t4b2 | **identical to t4b2 on every row** (found 98.70, id kept 93.51, one id 92.33, extra 994, changed 7, set 99.35, death p90 0.000, ghosts 0, hops 91.4, jolts 524, L1 98.98, node 99.46, L3 19 of 22); **L2 16 of 16** (15) | met |
| step 2's hops gate (`proto_feet.py --sound`) | 126 / 970 | **126 of 26,811 / 970 of 555,561** | met |
| the ms, live (the Perceiver, 4-minute capture, 2,970 frames, twice) | us_players 0.7 / p90 1.0, track 1.1 / 1.4, frame 15.65 | **us_players p50 0.6 / p90 0.9 / p99 1.0, track 1.1 / 1.3, frame 15.1** | for the user's line |
| ... its pieces (p50 / mean ms) | - | us 0.09 / 0.09; players.begin 0.35 / 0.24, of it `ask_columns` 0.33 / 0.21; players.end 0.17 / 0.18; 1,036 of 3,453 boxes not asked (settled) over the first 50 s | - |
| replay ms (CPU bitmaps, 13 captures) | 0.19 | p50 0.19 / p90 0.35 (us 0.05) | - |
| pytest (whole suite), bot speed | 16.3 ms | **green; 15.4 ms a tick** (p90 16.9; `us_players` 0.9 on the bench's 40 frames: nothing settles that soon) | - |

**Why, by row:**
- **Players found - the 20 `unsure`:** tracks with fewer than 5 alone body readings when the labelled frame came (try
  2 read them from every sighting): a tag under the minimap window (no column readable, "CGFzealot"); a find_tags box
  stretched over dark scenery ("FunKneel" 107 px: the column over its centre is empty - perception, stop rule 4);
  merged boxes the labeller called `player` (104-150 px) held by a track still under 5; **a name cut by front
  scenery whose piece was taken as the width** ("FreakyRafiki" 77 px seen for 31 frames as "Rafiki" 40 px - the
  other piece is not in the tag list at all, so the piece looks whole and alone; later the whole tag is split as two
  names); tags at the screen's edge. 7 of them are tracks whose final class is player (known later: the delay).
- **Non-players called players (7):** a pet under a light-pillar effect (its column reads 120 px on every alone
  sighting), a pet whose p75 is exactly 50, two 21 px medal-like tags labelled `none`, a mob's own tag not learned
  yet, a text tag reading 120.
- **The cover (34):** more player tracks (353; try 2 309 - pets no longer turn players, and a hidden track is now
  unseen instead of riding its neighbour's box), more of them lost in view (145) and back as a new id.
- **L1 us, 9 misses:** 5 standing frames read as air while we move (cases 61, 137, 116, 110, 136 - as in try 2, not
  ropes); 2 jumps past a rope with up held, labelled air (83, 107 - the key was down: the rule says grabbed); 1 off a
  rope with no key 0.18 s after (54: still "staying"); 1 labelled rope read air with up held (134: the tag came back
  moving right); the node: 102 (rope -6 / -5).

**For the user (stopped, stop rule 1):** (1) **`unsure`** - set a track with under 5 alone body readings apart as "not
yet known" (95.8 % found), or keep it a miss (85.4 %)? (2) **Non-players 2.04 %** - the light pillar and the medal
tags are not crowding: accept, or a rule for them? (3) **The cover 34** - accept, or longer than 2 s for a track hidden
inside another's box? (4) **The ms:** us_players p50 0.6 live (the body question 0.33 of it, asked on most frames of
the first minute) - the line to set. (5) **FreakyRafiki:** a name cut by scenery learned as a narrower width - accept
(rare), or let an alone box with one track in it re-teach the width (tried: the node fell to 94.5 %)?

**The user's answers (2026-11-26, to the plan manager; prompt "Tracker, step 4b, try 4"):**
1. **`unsure` = "not yet known"**: a track with fewer than 5 alone body readings has not learned its class yet
   (design 1), so it is graded apart, like a track seen under 6 times (95.8 % found: met). Also reported: how many
   tracks stay `unsure` their whole life, and why.
2. **Non-players called players 2.04 % (7 of 343): accepted** (none is crowding: the light pillar, two medal-like
   tags, a mob's tag not yet learned, a text tag).
3. **The cover is graded as a rate**: the gate's 29 was counted on 280 player tracks (try 1) = 10.4 %; try 3 has 34
   of 353 = 9.6 % (met). The count grew with the tracks: pets no longer turn players, a hidden track is unseen.
4. **The ms: the body check made cheaper first (A + B), then the line set from what it measures.** A: an unsettled
   track's tag is asked the body question every 4th frame, not every frame (frames 1/60 s apart repeat the reading).
   B: a track settles early when its class is clear - from 8 alone readings, the 75th percentile 10 px or more from
   the 50 px line (under 40 or over 60); a track near the line still needs `body_settled` 30. The plan manager's
   estimate: the body check ~0.33 -> ~0.05-0.1 ms, us + players ~0.6 -> ~0.35 ms p50.
5. **"FreakyRafiki" (a name cut by front scenery learned as its piece's width): accepted** (rare; the re-teach tried in
   try 3 made the node and the cover worse).

### Step 4b, try 4 (2026-11-26): A + B built; the cover, non-players, pet / player, the node, step 3's rows and the hops gate MET; players found MISSED (stopped)
Branch `tracker-build` (the main folder), a46b6d8. Runs `replay_players.py ... --tag t4b4` (A + B), `t4b4A` (A alone:
`--cfg body_early_n=1000000`), `t4b4B` (B alone: `--cfg body_every=1`); `replay_mobs.py ... --tag t4b4`.

**Built** (each rule's test fails with the rule switched off - checked):
- **Grading (answers 1, 3):** `l5` sets `unsure` apart as "not yet known" like `short`; `unsure_why` counts the tracks
  `unsure` their whole life and why; the delay is reported two ways - out of `short` (try 3's) and until the class is
  pet / player (`pp_n`: the 5th alone reading); `cover` prints the rate. `run --cfg k=v` runs a variant.
- **A (`config.Track.body_every` 4):** `_skip_boxes` - a box that is an unsettled track's tag (its width, within its
  gates) asked within the last 3 frames is not asked; a box no track would take is always asked. **What stands on a
  tag (the body and D's blob) counts in the class only on asked frames** (`Det.skipped`): without it a player whose
  blob reads 0 between asks turns `text` (the b0 vote against 1/4 as many body readings). Tests
  `test_an_unsettled_tracks_tag_is_asked_every_4th_frame`, `test_what_stands_on_a_tag_counts_only_on_the_frames_it_was_asked`.
- **B (`body_early_n` 8, `body_early_dist` 10):** `_Track.settled` - a pet / player from 8 alone readings when its
  p75 (`_Track.q`, the class's own percentile) is <= 40 or >= 60 px. Test `test_a_clear_class_settles_early`.
- The older tests run with try 3's sampling (`EVERY`: body_every 1, no early settle): their rules did not change.

| Gate | try 3 (regraded: `unsure` apart) | **try 4 (A + B)** | A alone | B alone | |
|---|---:|---:|---:|---:|---|
| L5 players found (>= 95 %) | 158 of 165 = 95.8 % | **128 of 138 = 92.8 %** (6 pet, 2 log, 1 mob, 1 ours) | 129 of 138 = 93.5 % | 151 of 165 = 91.5 % | **MISSED** |
| ... "not yet known": `short` / `unsure` (players) | 133 (56) / 35 (20) | 133 (56) / **69 (47)** | 69 (47) | 35 (20) | - |
| L5 non-players called players (accepted 2.04 %; must not rise) | 7 of 329 = 2.13 % | **5 of 322 = 1.55 %** | 1.55 % | 4.86 % | met |
| L5 a pet called a player or a player a pet (<= 5 %) | 6 of 209 = 2.87 % | **8 of 178 = 4.49 %** | 3.93 % | 10.53 % | met |
| L5 the node of standing players (>= 95 %) | 138 of 143 = 96.5 % | **112 of 116 = 96.6 %** | 96.6 % | 96.4 % | met |
| the 2 s cover, a rate (<= 10.4 %) | 34 of 353 = 9.6 % | **14 of 241 = 5.8 %** | 16 of 253 = 6.3 % | 34 of 348 = 9.8 % | met |
| the delay, out of `short` (frames p50 / p90 / p99) | 12 / 77 / 251 | **14 / 81 / 252** | 14 / 85 / 252 | 12 / 77 / 251 | reported |
| the delay until pet / player (out of `unsure` too) | 17 / 110 / 294 | **39 / 178 / 463** | 39 / 174 / 463 | 17 / 111 / 294 | reported |
| tracks `unsure` their whole life (L5's 2 captures) | 204 | **397** | 394 | 205 | reported |
| body questions a frame (replay, L5's 2 captures) | 0.80 | **0.65** | 0.69 | 0.72 | - |
| L1 us (accepted 95.05 %) | 95.05 % | **173 of 182 = 95.05 %**, node 99.22 % | | | met |
| us against SelfState / our feet known (accepted) | 95.70 / 97.04 % | 95.70 / 97.04 % | | | - |
| step 3's rows (`replay_mobs.py --tag t4b4`) | t4b3 | **identical to t4b3 on every row** (found 98.70, id kept 93.51, one id 92.33, extra 994, changed 7, set 99.35, death p90 0.000, ghosts 0, hops 91.4, jolts 524, L1 98.98, node 99.46, L2 16 of 16, L3 19 of 22); only the replay ms p90 4.21 -> 4.37 | | | met |
| step 2's hops gate (`proto_feet.py --sound`) | 126 / 970 | **126 of 26,811 / 970 of 555,561** | | | met |
| pytest (whole suite), bot speed | 15.4 ms | **green; 14.8 ms a tick** (p90 16.2; `us_players` 0.8 on the bench's 40 frames) | | | - |

**The ms, live (the Perceiver; try 3's sampling = the same code with body_every 1 and no early settle, run alike):**
| | try 3's sampling | **try 4** |
|---|---:|---:|
| 4-minute capture, 15,181 frames: us_players p50 / p90 / p99 (mean) | 0.5 / 0.8 / 1.0 (0.461) | **0.3 / 0.8 / 1.0 (0.418)** |
| ... track p50 / p90 | 1.0 / 1.2 | 1.0 / 1.2 |
| ... pieces, mean ms: us / players.begin / of it `ask_columns` / players.end | 0.084 / 0.214 / 0.188 / 0.161 | 0.084 / 0.185 / **0.160** / 0.150 |
| ... the body check's share of us_players (mean); frames with a body question | 41 %; 56.1 % | 38 %; 48.3 % |
| 30-minute capture, minutes 5-30 (92,052 frames): us_players p50 / p90 / p99 (mean) | 0.3 / 0.8 / 1.0 (0.403) | **0.2 / 0.8 / 1.0 (0.366)** |
| ... track p50 / p90; observe p50 | 1.0 / 1.3; 14.42 | 1.0 / 1.3; 14.27 |
| ... `ask_columns` mean; the share; frames with a body question | 0.157; 39 %; 46.5 % | **0.133**; 36 %; 40.2 % |

**Why, by row:**
- **The ms - the body question costs per CALL, not per tag:** `ask_columns` is ~0.3 ms on any frame that asks at least
  one tag (~15 small torch calls), whatever the count. A cuts the tags asked by 19 % (0.80 -> 0.65 a frame), but the
  frames that ask at all only from 56 to 48 % (4-minute) and 46.5 to 40 % (30-minute): most asked tags are ones no
  track would take yet (new tags, pieces, `short` tracks, tags whose width changes) - always asked. So the mean falls
  ~0.04 ms and p90 not at all (0.8). The plan manager's estimate (~0.05-0.1 ms for the body check) assumed the cost
  scaled with the tags.
- **Players found - A takes readings, B locks early ones:** A gives a track 1/4 of the alone readings, so 27 more
  labelled player tags are still `unsure` on their frame (20 -> 47, set apart) and the delay until pet / player doubles
  (p50 17 -> 39 frames); the readings it keeps are sparser, so a stance between the legs weighs more (5 players called
  pets with A alone, 3 in try 3). B alone is worse: 8 readings on 8 consecutive frames are one pose - 10 players called
  pets, 12 pets called players. A + B: 6 players called pets - **track 721** (w 38, a pet-width track holding its
  neighbour's joined 77 px box: 3 labelled cases 36, 168, 192; sampled readings 18, 39, 55, 40, 39, 39, 39, 45 -> q 40,
  settled a pet; try 3 read 30 readings, p75 48 - borderline both times) and **track 781** (w 65, a player in a spear
  stance: 18, 57, 56, 27, 27, 9, 9, 9 -> q 27, settled a pet; try 3's p75 48); cases 119 and 187 were pets in try 3
  too (true readings 34-40).
- **Why tracks stay `unsure` their whole life (try 4, 397):** 283 have 1-4 alone readings and lived under 1 s; 67 have
  1-4 over a longer life, most sightings cut or crowded; 47 were alone but the body never read (-1 under the minimap /
  UI / the play area's bottom, or 0). Their sightings: 12,533 crowded, 4,543 cut, 2,508 alone but not asked (A), 863
  alone and read. Try 3: 204 (138 / 27 / 39) - A doubles them.
- **The cover:** fewer player tracks on the 30-minute capture (241 against 353; its `unsure` tracks 180 -> 353: lives
  too short for 5 readings at one in 4), and of them 14 back as a new id.

**For the user (stopped, stop rule 1):** (1) **The body check** - keep try 3's sampling (players found 95.8 %, us_players
live p50 0.3-0.5 / p90 0.8, mean 0.40-0.46 ms), keep A alone (93.5 %: misses; mean -0.04 ms), or A + B as built
(92.8 %)? A cheaper question would have to cut the CALL (one gather for every tag built on the GPU from the tags'
corners - design question, not measured), not the tags. (2) **The ms line** from the numbers above: us + players live
p50 0.2-0.5, p90 0.8, p99 1.0, mean 0.37-0.46 ms. (3) **The delay** with A: a class known p50 0.65 s later (39 frames)
- acceptable if A is kept?

**The user's decision (2026-11-26, to the plan manager): A and B are undone - back to try 3's sampling** (body_every 1,
no early settle); the grading tools stay. Why: the body question costs per CALL, not per tag (A saved ~0.04 ms mean,
p90 unchanged), and readings on consecutive frames are one pose, not independent looks (B locked a spear stance in
as a pet). With the user's answers try 3 meets every gate (found 95.8 %, the cover 9.6 %, pet / player 2.87 %, the
node 96.5 %; non-players 2.13 % and L1 us 95.05 % accepted). **The ms line (the user):** us_players live p50 <= 0.5
ms, p90 <= 1.0 ms on the 4-minute capture. A cheaper call (the tags' index built on the GPU) is left for step 9, if
the frame needs it. Prompt "Tracker, step 4b, close".

### Step 4b, close (2026-11-26): A and B undone, try 3's sampling; every gate MET - step 4b DONE
Branch `tracker-build` (the main folder), 743c600. `players.py`, `config.Track` and `test_track_players.py` are back at
try 3 (1740f87: `body_every`, `body_early_n`, `body_early_dist`, `_skip_boxes`, `Det.skipped`, `_Track.asked_n` / `q`
and their three tests gone); `replay_players.py` keeps try 4's grading (`unsure` apart, `unsure_why`, the cover rate,
`--cfg`) and prints the user's ms line. Runs `replay_players.py ... --tag t4bc`, `replay_mobs.py ... --tag t4bc`.

| Gate | try 3 (regraded) | **close** | |
|---|---:|---:|---|
| L5 players found (>= 95 %; `short` 133 (56 players), `unsure` 35 (20) apart) | 158 of 165 = 95.8 % | **158 of 165 = 95.8 %** | met |
| L5 non-players called players (accepted 2.13 %) | 7 of 329 = 2.13 % | **7 of 329 = 2.13 %** | accepted |
| L5 a pet called a player or a player a pet (<= 5 %) | 6 of 209 = 2.87 % | **6 of 209 = 2.87 %** | met |
| L5 the node of standing players (>= 95 %) | 138 of 143 = 96.5 % | **138 of 143 = 96.5 %** | met |
| the 2 s cover, a rate (<= 10.4 %) | 34 of 353 = 9.6 % | **34 of 353 = 9.6 %** | met |
| the delay, out of `short` / until pet / player (frames p50 / p90 / p99) | 12 / 77 / 251; 17 / 110 / 294 | **12 / 77 / 251; 17 / 110 / 294** | reported |
| tracks `unsure` their whole life (L5's 2 captures) | 204 | **204** (138 seen under 1 s, 39 body never read, 27 cut / crowded) | reported |
| L1 us (accepted 95.05 %) | 173 of 182 = 95.05 %, node 99.22 % | **173 of 182 = 95.05 %, node 128 of 129 = 99.22 %** | accepted |
| us against SelfState / our feet known (accepted) | 95.70 / 97.04 % | **95.70 / 97.04 %** | - |
| step 3's rows (`replay_mobs.py pool` + `labels` + `feet`) | t4b3 | **identical to t4b3 on every line** (found 98.70, id kept 93.51, one id 92.33, extra 994, changed 7, set 99.35, death p90 0.000, ghosts 0, L1 98.98, node 99.46, L2 16 of 16, L3 19 of 22, hops 91.4, jolts 524); only the replay ms p50 / p90 / p99 0.88 / 4.12 / 14.88 (t4b3 0.90 / 4.21 / 14.52) | met |
| step 2's hops gate (`proto_feet.py --sound`) | 126 / 970 | **126 of 26,811 / 970 of 555,561** | met |
| **the ms, live (the user's line: us_players p50 <= 0.5, p90 <= 1.0 ms; the 4-minute capture, all 15,181 frames, twice)** | 0.5 / 0.8 / 1.0 | **p50 0.5 / p90 0.8 / p99 1.0 and 1.1; track 1.1 / 1.3; observe p50 14.7 / 14.6; one transfer back on 13,239 frames, none on 1,942** | met |
| pytest (whole suite), bot speed | 15.4 ms | **green; 15.1 ms a tick** (p90 16.8; `us_players` 0.9 on the bench's 40 frames) | - |

**Step 4b DONE.** Accepted by the user: non-players called players 2.13 %, "FreakyRafiki" (a name cut by scenery learned
as its piece's width), L1 us 95.05 % (the rope key rule). Left for step 9: a cheaper body CALL (the tags' index built on
the GPU), if the frame needs it.

### Step 5a - the HP meter (added by the user, 2026-11-26; one executor session, measure then build; BEFORE step 5)
**The user, 2026-11-26** (asked whether to pause for an HP reader): it is "more for brain decisions" - the brain may
finish a wounded mob first or count the hits a tough mob still needs (Evil Eyes, Drakes, Perion; most Bubblings die
in one). This reverses the choice of 2026-11-23 ("not a mob's HP" - the state model's fields chosen by "how many are
there and how quickly I can get there"). Named 5a and run first so that step 5's events and its EXP grading start
with the meter available. **No v83 references** (the user: "I'm not sure the HP bar was there in the same way. It
should be pretty obvious on any recording"). **The user's observations - the spec:**
- "The only thing we would be tracking from it is current hp %, by looking at how much of the hp meter is full
  (green)".
- "Only mobs that have been hit by us will display the hp meter".
- "The meter appears almost immediately after hitting a mob (full hp mobs have no meter) and disappears immediately
  after death of the mob".
- "Every hit reduces the green bar on the meter (replaced by dark red) until the mob dies, the meter itself is at a
  fixed size".
- "Multiple mobs hit = multiple meters".
- "I'm looking for a very very small performance impact, blocked if it adds more than 1ms to discuss it".
- "Need to determine what range above the monster sprite the meter is, look at different mob sizes".
- **Where it is computed (the user asked; the plan manager's answer, OK'd):** perception FINDS the meters and READS
  each one's green share (pixels, frame by frame, like `slots.py` / `hud.py`: the meter has a fixed size, so green /
  width = HP %); the mob TRACKER ties each meter to its track - it alone knows covered and remembered mobs, their
  ids and which we just hit (design 1: a meter over two overlapping mobs is not taught from).
- **The user's clarifications (2026-11-26):** "meters just appear right after the mob is taking damage" (no
  animation: the meter is there at once); "if it's a fresh mob (no meter yet) we (the player) will not see a meter
  above someone else's mob, however if I already hit a mob and the meter appeared - any further damage by other
  players will show up on MY meter. Similarly if I am not the 'first hitter' on a mob - the meter still shows up
  with the absolute hp value of the mob".
- **Two uses:** the mob's `hp` (0-1, with `hp_t`: when read; None = no meter ever; kept while the track lives -
  memory, no HP guessed, no healing modelled) for the brain; and **a witness of damage for step 5**:
  - a meter appearing in our hit window = our first hit landed;
  - its green share falling in our hit window = our hit; **falling outside our windows = another player's damage**
    on a mob we also hit (it shows on our meter);
  - **the meter shows the mob's absolute HP**, so its first reading also carries damage done BEFORE our first hit:
    a first reading clearly lower than our own first hit leaves on that kind (measured on mobs seen from full HP
    with no other hitter) = another player hit it first;
  - a mob only other players hit has no meter: their damage there is not seen (their hit poses still are).
  So a death's credit and our share of the damage seen. Measurement 6 saw a box under a mob within 1 s after 41 of
  69 of our hits and 1 of 170 of another's: likely this meter's mob name.
- **Measured first:** the meter's picture (size, colours) from footage; its place above the mob for small / mid / big
  / flying kinds (Slime, Bubbling; Horny / Zombie Mushroom; Drake; Stirge) against the sprite box and `mob.json`'s
  `head` point; the delay from our hit to the meter and from the death to its going; whether one ever shows on a mob
  we did not hit (if so: stop - it breaks the witness); several meters, two mobs close, under effects, at the edge.
  The search looks in a band above the mobs, not the whole screen. A perception reader; the fit, the scene model and
  the drop finder are not changed (stop rule 4).
- **Step 6 or 8 may run beside it** (a worktree).

### Step 5a, 2026-11-26: measured, then built in shadow; the gate MISSED on 3 rows (found, tied, the ms by 0.001) - stopped, the user decides
Tools: `tools/perc/track/proto_meter.py` (measuring: `scan`, `place`, `picture`, `new`, `ties`, `when`, `l9 ...`, `sheet
odd`; its docstring holds the picture) and `replay_meters.py` (the real code: `read`, `hit`, `l9`, `time`);
`replay_mobs.py run --meters --tag t5a`. Outputs and sheets: `F:\dev\maple-corpus\work\track-plan\meter\`, L9's
sheets `...\labels\L9\`. Everything from the 13 sound captures and their keys; no v83 reference.

**Measured first** (`scan`: every frame, the whole play area; 22,410 meters with a white end):
- **The picture:** a box 52 x 10 px, opaque, pixel-exact: black / white / black frame lines, inside 46 px. Rows 3-5 of
  the inside: green (0, 255, 0) from the left = the HP left, then the HP lost: **red at the hit (R ~220), fading
  linearly to black in 2.0 s** (-12 a 0.1 s) - so the lost part is red or black; row 6 a darker line. Fixed size:
  whole (all 48 frame columns, both white ends) on 63.5 %; frame columns hidden 35.7 % (drawn over by another mob's
  meter, our character, other players, a rope or front scenery, damage digits: the meter is drawn with the mob),
  cut by the screen's side 0.3 %. Sheet: `meter\sheet_odd.png`.
- **The place: one rule for every size** (Slime, Bubbling, Green / Horny / Zombie Mushroom, Evil Eye, the flying
  Stirge): **the box's top = the pose frame's body box top (mob.json `lt` y) - 30 px, centred on that body box**
  (left = feet + floor((lt x + rb x) / 2) - 26, lt / rb mirrored for a mob facing right). Every kind's mode is -30;
  `head` does not fit (Horny Mushroom -36 / -37 / -41 by pose). With the fit's pose and feet the rule ties **90.1 % of
  20,231 meter-frames** to exactly one seen mob (within 3 px across, 2 up or down); the rest: the mob not seen on that
  frame 6.9 % (behind us, a player, an effect: the tracker holds it remembered), the fit's pose frame one off 2.1 %
  (Horny hit1 +9 px), two mobs at one place 0.8 %, a die frame (no body box) 0.07 %. **No Drake was ever hit in the
  bank** (level 50; the character is 31): "big" rests on Evil Eye (97 x 50 px).
- **When:** a NEW meter (144: followed by its own place, tied to a mob, not a continuation) comes **0.27-0.72 s after
  our `q` key-down** (one press before it: n 42, median ~0.48), `e` 0.35-0.55 (n 17), `w` 0.44 / 0.58 (n 2): earlier
  than measurement 6's hit-pose window (q 0.45-0.72): the stab reaches the mob ~0.15 s after the key-down, the meter
  shows at once (`MWIN`: q / w 0.20-0.80, e 0.15-0.65 hold all 144). Against the hit pose: mostly the same 0-4 frames,
  spread -0.6..+0.4 s. **It goes at the killing hit**, ~0.1 s before the die pose is first seen (142 of 148), its last
  reading not 0. A meter lives on while the mob lives (followed through hops: a Bubbling's move frames move it 27 px).
- **A meter on a mob we did not hit: never.** 144 of 144 new meters have our key-down in a meter window (9 looked at
  by eye: our stab reaching the mob). The real code (`replay_meters.py hit`): 187 tracks got a meter, the first in our
  window on 180; the 7 others were looked at (`meter\sheet_hit_outside.png`): all 7 a meter already on screen 0.2-1 s
  before, taken over by a new track id (two Bubblings merging, an id change after a cover) - continuations.
- **Several meters:** frames with 2 / 3 / 4 meters 2,398 / 616 / 165; 1,189 pairs of meters overlapping (stacked mobs).
- **Our first hit's share** (the first reading within 0.25 s; "clean" = born faded in, no hit pose before ours):
  Bubbling p5 / 50 / 95 0.28 / 0.54 / 0.96 (n 21 - only the survivors: most die of one hit), Horny 0.42 / 0.73 / 0.93
  (6), Zombie 0.18 / 0.50 / 0.95 (7), Evil Eye 0.21 / 0.52 / 0.85 (10), Stirge 0.48 (1). Mobs another player hit
  first: Bubbling 0.77 / 0.95 / 0.96 (6), Horny 0.29 / 0.35 (2), Evil Eye 0.22 / 0.46 / 0.63 (3). **Too few and too
  spread to call "another hit first" from a first reading** (a hit's share varies 0.2-0.96 with the damage range).
- **L9** (by eye, Claude labellers, `judged/BRIEF.md` "L9"; `judged/L9_a.p0-p2.jsonl`, `L9_b.jsonl`; the bank's
  `labels\SESSION#K\labels\L9.json`, read back by `label_eval.py`): 112 frames of 12 captures - 101 with a meter (158
  meters; 117 over a lettered mob, 21 `?`, 20 over a mob with no letter) + 11 picked where no meter was found near a
  hit mob (none by eye either). Cases: drawn over 44, fresh 42, close 35, several 26, late 22, edge 3; Bubbling 35,
  Zombie 15, Horny 15, Evil Eye 13, Stirge 12, Green Mushroom 8, Slime 1. **Second look (10 cases, blind): 35 of 35
  items both answered agree (100 %)**; a `?` against an answer 5 (stacked mobs), both `?` 4.

**Built (in shadow; nothing reads it):** `perception/meters.py` (`MeterReader`: in a band of +-10 px around each fit
mob's expected box - five sample columns first, the band read whole only where they show the frame; a meter cut or
drawn over is read from one white end; the fill known when the last green seen touches the first lost seen; each
meter names the fit mobs whose expected box it is at, within 3 / 2 px), FrameFacts v8 `meters`, `meters_ms`; the
Perceiver reads them after the fit (part `meters`; config `Perception.meters`, `meter_tol`, `meter_tie`); the mob
tracker's `_meters` (track/mobs.py): a meter teaches `hp`, `hp_t` to the one track whose sighting it alone names, its
fill read, no other track overlapping that mob (design 1; config `Track.meter_same_dy`); the Mob record `hp`, `hp_t`;
`docs/state_model.md` "Every mob" (the user's words). Tests `tests/test_meters.py` (17; the overlap and the mirror
rules reverted: their tests fail).

| Row (step 5a) | Gate | Measured | |
|---|---|---|---|
| meters found on L9's frames | >= 99 % | **95 of 101 frames (94.1 %)**; meters 110 of 117. The 7 misses are meters almost wholly hidden: 5 behind another mob's meter (3-27 of 48 frame columns showing, no white end: the box cannot be placed), 2 under damage digits (0-5 columns) | **MISSED** |
| tied to the right mob | >= 99 % | **of the meters the tracker tied: 45 of 45 right, 0 wrong; but 65 of the 110 found were not tied**: 38 by the overlap guard (another track's body meets the mob's), 27 the green's end not seen. Perception's one candidate alone names the right mob on **110 of 110** | **MISSED** as "tied" (40.9 % of the found), met as "right when tied" |
| the fill against the eye's | within 3 % | **83 of 83 within 3 points** (p50 0.0, max 0.1); 15 fills the eye read where the reader did not | met |
| a meter on a mob we did not hit (the kept replay against our windows) | 0 | **0** (187 tracks; the 7 outside a window continuations, by eye) | met |
| the reader's ms, live (`replay_meters.py time`, the 4-minute capture, frames 3000-6000, 140 with a meter, two runs on / off) | p50 <= 0.1; > 1 ms added a frame: stop | **p50 0.101 / p90 0.133 / p99 0.293 / max 0.497**; the whole frame's observe p50 16.03 on / 16.03 off (+0.00). Frames 0-2000 (no meter): part `meters` 0.1 (rounded), observe +0.17 | **MISSED by 0.001 ms**; the frame +0.00 |
| step 3's rows (`replay_mobs.py pool` + `feet` + `labels`, `--meters --tag t5a`) | unchanged | **identical to t4bc on every line** (found 98.7 %, L1 98.98, hops 91.4, jolts 524 ...); the replay's ms p50 0.96 (t4bc 0.88). Over the 13 captures the tracker taught 10,560 meter readings, refused 5,249 (overlap), 2,270 (fill not seen), 1,423 (no track), 125 (two sightings) | met |
| L9's second look | >= 95 % | 35 of 35 (100 %) | met |
| pytest (whole suite), bot speed | - | **green; 17.1 ms a tick** (p90 19.0; part `meters` 0.1). Step 4b's close: 15.1 - the game ran in front this time (the A/B above: +0.00) | - |

**For the user to decide:**
1. **Found 94.1 %:** the misses are meters a mob's meter or damage digits cover almost entirely. Accept, or let the
   reader place a meter with no white end at its mob's expected box (the labellers read 4 of the 7 that way: the
   strip's expected place) - a change of design, then measured again.
2. **The tie:** keep design 1's overlap guard as built (never wrong on L9; teaches 45 of 110 there, 10,560 of 19,627
   meter readings over the 13 captures), or let perception's one candidate decide among the SEEN mobs (110 of 110
   right on L9) and keep the guard only for remembered tracks (not measured: one replay run).
3. **The ms:** 0.101 against 0.1 at the median, +0.00 ms on the whole frame. Accept, or a speed pass (the reader's
   Python per frame: `expected`, two `np.clip`) - measured again live.
Also: this session's CPU jobs (8 decoders, ~20:20-20:35) overlapped the user's `record --label assassin` of 20:07:
check that recording's dropped frames when it is filed.

**The user's answers (2026-11-27; the plan manager re-ran `replay_meters.py l9 --tag t5a` and `test_meters.py`: the
same numbers):**
1. Found 94.1 %: **accepted** ("ok").
2. The tie: **"trust the candidate"** - a meter whose perception candidate is one seen sighting teaches that sighting's
   track, whatever other SEEN track overlaps it (perception's place rule already chose among the seen: 110 of 110 on
   L9); the overlap guard stays only against REMEMBERED tracks (not seen on this frame: a hidden mob under the meter
   could be its owner). Built and measured in **step 5a, try 2**. The tie is graded on the meters whose fill was read
   (83 on L9: a meter with no fill read teaches nothing, unchanged); the 27 unread fills are reported.
3. The ms 0.101: **accepted** ("the speed ok").
4. **A ranged class, report only (the user, 2026-11-27: "to see if adding range changes anything"):** try 2 also runs
   the meter on one assassin capture, `2026-11-26_2008_assassin_farming_idle_7m35s_s00` (Ant Tunnel IV, level 33,
   27,343 frames; it ended 20:16, before try 1's CPU jobs). **The assassin's keys (the user):** shift jump, space
   Lucky Seven (the attack skill), z loot, 1 Haste, 2 Claw Booster, Del HP potion, End and Home MP potions. Not in
   `Keys` (config.py): a class's keys belong in step 6's profile; the tool takes them as an argument. No gate: the
   numbers go under "Step 5a, try 2" for the user.

### Step 5a, try 2 (2026-11-27): "trust the candidate" built; tied 61 of 83, 0 wrong - the gate MISSED (stopped, the user decides); the assassin report beside it
**Built:** `track/mobs.py` `_overlapped` skips every track seen on this frame - the guard stays only against tracks
NOT seen (remembered, hidden, tentative unseen; dying excluded as before); its stat is now "meter: over an unseen
mob"; the config comment and `docs/state_model.md`'s `hp` row say so. Tests (`tests/test_meters.py`, 17): "a meter
over two overlapping seen mobs teaches the one it names" (the old guard test, changed) fails without the seen-skip;
"a remembered mob that can be under it blocks the teaching" fails without the guard. Tools: `replay_meters.py l9`
grades the meters whose fill was read apart and lists the guard's refusals with what blocks them + a sheet;
`meter_ranged.py` (new, report only); `dump.py --self-tag` and `bench.build(self_tag=)` (below, the assassin).

| Row (try 2) | Gate | Measured | |
|---|---|---|---|
| L9's meters whose fill the reader read (83): tied to the right mob | >= 99 %, wrong 0 | **61 of 83 (73.5 %), wrong 0** (try 1: 45). The 22 not tied: all refused by the guard - an unseen track can be under the mob | **MISSED** |
| L9's unread fills (reported) | - | 27, not tied (fill not read), as in try 1 | - |
| over the 13 captures: taught / refused | against try 1 | **taught 12,795** (try 1 10,560: +2,235); refused: over an unseen mob 3,014 (try 1's overlap 5,249), fill not seen 2,270, no track 1,423, two sightings 125 (the last three unchanged) | - |
| step 3's rows (`pool` + `feet` + `labels`, t5a2 against t5a) | identical | **identical** (only the meter counts differ). The replay's ms p50 1.21 pooled was run beside 7 jobs and a GPU dump; alone on a quiet machine (Line 1 4-minute) **0.91** (t5a's file 1.09), the rows equal | met |
| the reader's ms | as in try 1 | the reader not changed (0.101, accepted); the tie does less work (a seen track is skipped first) | met |
| pytest (whole), bot speed | - | **green; 17.1 ms a tick** (p90 18.5; part `meters` 0.1, `track` 0.5) = try 1's 17.1 | - |

**The 22 refused, looked at** (`meter\sheet_guard_t5a2_0.png`, `_1.png`: the seen track cyan, the unseen ones under
it orange with their possible range): the tracks under them are hidden, covered by a mob 26, by us 6, by an effect 2.
Counting the whole-screen finder's meters near each refused meter against the mobs seen there: **in 17 of 22 every
meter near belongs to a seen mob** - the hidden track there has no meter of its own, so it cannot own this one (stale
memory of a mob that left, or a mob we did not hit); **in 5 (case 12 twice, 50, 81, 89) more meters are drawn than
mobs seen** - a hit mob really is hidden there, but its meter is drawn at its own place. In all 22 L9's eye says the
candidate is the right mob (perception's one candidate: 110 of 110 found meters on L9).

**For the user to decide (the tie, a third time):**
- **(a) drop the guard: trust perception's one candidate** (its place rule, 3 px across / 2 up or down): L9 83 of 83.
  The risk left: a hidden mob of the same kind and pose standing within 3 px behind a seen one - its meter on the
  same box (over the 13 captures "two mobs at one place" was 0.8 % of meter-frames, both seen; L9 has no such case).
- (b) refuse only where more meters are drawn near than mobs seen: 78 of 83 (94.0 %) - under 99 %.
- (c) keep try 2 as built: 61 of 83 (73.5 %), never wrong.
My reading: (a) - a meter is drawn over its own mob, so the box decides; a hidden mob is a risk only when it stands
exactly behind the seen one.

**The assassin, report only** (`20261126_200826_2#0` = `2026-11-26_2008_assassin_farming_idle_7m35s_s00`, Ant Tunnel
IV, 27,343 frames; beside it the same map's spearman capture `20261118_232410_1#3`, 4,595 frames - only 1.3 minutes).
- **Dropped frames: 0** (27,343 frames over 455.69 s = 60.0 a second; the longest gap 0.038 s): the overlap with try
  1's CPU jobs did not touch it.
- **Perception found US by a picture of the warrior's own name tag** (`assets/self_tag_gray.npy`, "JenkinsJob"): the
  first kept replay had **no scene camera on any frame** (the camera is seeded by our tag). A "Beeperz" picture was
  made the same way (`meter_ranged.py tag`: the median of 1,585 aligned crops; found on 429 of 456 frames, p50 0.97,
  the best other place <= 0.65 against the 0.66 line - a thinner margin than the warrior's <= 0.59) and kept beside
  the capture (`CORPUS\work\20261126_200826_2#0\self_tag_gray.npy`, not in assets/); `dump.py --self-tag` used it:
  a camera on 27,343 of 27,343 frames. **Every other character's capture needs its own picture** (step 6's profile).
- **The keys (the user, 2026-11-27):** `c` is the basic attack ("attack with throwing star (not lucky seven, still
  throwing a star but costs no mana, animation is expected)"), beside space = Lucky Seven. `ctrl` (pressed once):
  not known. Space was **held** once for 2.76 s: two new meters came inside the hold, 0.8 s apart - **a held attack
  key casts again with no new key-down** (step 5's cast rule counts key-downs: holds must be added).

| (each number beside the spearman's, same map) | assassin | spearman |
|---|---|---|
| attack key-downs | space 341, `c` 1 (+ the 2.76 s hold) | q 23, w 8, e 3 |
| **the place rule**: meter-frames tied to exactly one seen mob (13 captures: 90.1 %) | **6,572 of 6,761 (97.2 %)**; off 2.2 %, no seen mob 0.4 %, two mobs 0.2 % | 671 of 709 (94.6 %) |
| the reader: meters; fill read; one candidate | 7,099; 86.6 %; 95.0 % | 804; 75.0 %; 84.1 % |
| the tracker: taught; refused (fill, no track, unseen under it, two sightings) | 5,841; 751, 340, 154, 13 | 537; 84, 126, 55, 2 |
| **new meters against our attacks** | **39: 37 within 0.20-0.80 s of a key-down, 2 inside the held space; 0 on a mob we did not hit** | 5: 5 within |
| **the delay against the distance** (clean: one key-down in the 1.3 s before, no hold) | n 17, **0.365-0.641 s** (p50 0.568) at 0-354 px; no trend (-0.21 ms a px, r -0.27): **the star's flight does not widen try 1's window** | n 2: 0.271, 0.480 at 84-102 px (try 1's q: 0.27-0.72) |
| **30 random meters by eye** (`meter\ranged\random_<cap>_0..2.png`) | **30 real, 30 found; 25 taught - every one to the mob under it, the fill as drawn (0.00-0.91)**; 5 not taught: no fill read 4 (a ladder, a coin, a client window over it), the guard 1 | 30 real, 29 found (1 almost wholly behind another meter); 24 taught, each to the mob under it (a crowd, partly behind us); 5 not taught: no fill 2, the guard 3 |
| meters cut by the screen's side (`cut_<cap>_0.png`) | 1 (35 frames, the right side): found from its white end, the right mob, fill 0.00 (the inside black) - right | 0 |
| meters under the buffs (1 Haste, 2 Claw Booster) | **none to see**: 17 buff key-downs, no meter on screen within 1.5 s of one (cast on a ladder between fights); the Haste effect (`buffs_look.png`) is drawn over our body and gone by 0.8 s | - |
| Ant Tunnel's scenery read as Zombie Mushroom with a meter | **0**: 23 Zombie tracks named by a meter, every one with hit / die poses and moving | 0 (3 tracks) |
| the reader's ms in `read` (4 processes; not the live number) | p50 0.424 / p90 0.851 | 0.431 / 1.07 |
So range changes nothing the meter rests on: the place rule ties more (97.2 %), the window holds, no meter on a mob we
did not hit. What it adds: our own tag is per character, and a held key repeats casts (both for steps 5-6).

**The user's answers (2026-11-27; the plan manager re-ran `replay_meters.py l9 --tag t5a2`: the same numbers):**
design 1 relaxed - "Lets relax this rule, it is best if possible to classify something when it is alone, but not
mandatory" (design 1 and `docs/state_model.md` say so) - so the tie is **(a): the guard goes**, perception's one
candidate decides; a meter naming two sightings and an unread fill still teach nothing. **The user's idea: "could we
use the meters to help when mobs overlap?"** - measured first, in the close session (report only): ids at
crossings, a hidden hit mob placed by its meter, a death on the right one of two overlapping mobs. A build, if the
numbers call for it, is a step of its own before step 5. -> **"Step 5a, close"** (its prompt under "Session prompts").

### Step 5a, close (2026-11-27): the guard dropped; L9 met (83 of 83) - STOPPED on a wrong tie outside L9 (the user decides); the overlaps measured (report only)
**Built (Part 1):** `track/mobs.py` `_meters`: a meter whose candidate is one seen sighting, its fill read, teaches that
sighting's track; `_overlapped` (a track NOT seen on this frame that could stand under it) is now only COUNTED -
stat "meter: taught, an unseen mob could be under it" - never a refusal. Still refused: two sightings, an unread fill,
no track. Config comment, the module docstring, `docs/state_model.md`'s `hp` row say so. Tests (`tests/test_meters.py`,
19): "a remembered mob that can be under it is counted, not a refusal" (fails without the change: reverted, seen
failing, restored), "a meter with no unseen mob near is not counted as one", the two-sightings refusal (also with an
unseen mob near). Tools: `tools/perc/track/meter_overlaps.py` (new: `ids`, `hidden`, `deaths`, `all`, `ties`; its
docstring holds every rule below). Outputs: `F:\dev\maple-corpus\work\track-plan\meter\` (`overlaps_t5a3.txt`,
`overlaps_t5a3_0..5.png`, `wrong_ties_t5a3.png`, `rises_t5a3_0..2.png`, `overlaps_t5a3_deaths_0..2.png`, `look_c_*.png`).

| Row (the close) | Gate | Measured | |
|---|---|---|---|
| L9's meters whose fill was read: tied to the right mob | >= 99 %, wrong 0 | **83 of 83 (100 %), wrong 0** (try 2: 61); the 27 unread fills not tied, as before | met |
| over the 13 captures: taught / refused | against try 2 | **taught 15,809** = try 2's 12,795 + the 3,014 the guard refused (now the counted stat "an unseen mob could be under it": 3,014); refused: fill not seen 2,270, no track 1,423, two sightings 125 - unchanged | - |
| step 3's rows (`pool` + `feet` + `labels`, t5a3 against t5a2) | identical | **identical**: the three outputs differ only in the meter counts and the replay's ms (p50 1.00 against 1.21); all 952,287 track-frames equal field by field apart from `hp` / `hp_t` (`hp` differs on 7,690) | met |
| pytest (whole), bot speed | - | **green; 15.9 ms a tick** (p90 16.9; `track` 0.4, `meters` 0.1) - a quiet machine (try 2's 17.1: the game in front) | - |
| **a wrong tie (the prompt: "one wrong: stop with the case and its picture")** | 0 | **found outside L9, on the 13 captures** - below | **STOP** |

**The wrong tie** (`meter\wrong_ties_t5a3.png`, row 1): **Cave of Evil Eye 7 (`20261118_232410_1#7`), frame 35601** - two
Zombie Mushrooms (13: 0.83, 11: 0.76) and an Evil Eye (7) in front of them. On that frame the fit misses Zombie 13 (seen
by eye; the Evil Eye steps over it) and sees the Evil Eye; the Zombie's own meter (0.83, box at 509, 400) lies within
3 / 2 px of the Evil Eye's expected box (`move_1`) - perception's one candidate is the Evil Eye, so the Evil Eye's
track 7 is taught a Zombie Mushroom's HP (0.48 -> 0.83). The old guard refused it (13 remembered there). Row 4 of the
same sheet, **Line 1 frames 82658-82661**: two Bubblings stacked exactly, one place's meter reads 0.48 then 0.78
three frames later (HP never rises: two mobs' meters taking turns in front), the one seen track gets both. Rows 2-3
(Cave 9, 47705 and 41858): the meter is the visible mob's own - there the TRACK changed mob, not the tie.
**How often (`meter_overlaps.py ties`; every taught reading against its track's own last reading):**

| taught readings | continue its own (within 3 points) | first | lower | **rise** (a mob's HP never rises) |
|---|---:|---:|---:|---:|
| the old guard would have refused (an unseen track under it; recomputed from the rows: 3,022 ~ the tracker's 3,014) | 2,907 | 45 | 46 (7 to an unseen track's own fill) | **24 (10 to an unseen track's own fill)** |
| no unseen track under it (12,787) | 12,620 | 137 | 25 | 5 |

On try 2's rows (the guard on) a track's HP rose 5 times; here 29 (on 22 tracks; 21 within 2 s of a fair id switch of
that track - the id flicker between stacked mobs the guard hid by not teaching). Two meters naming one sighting: 148
sightings, never with fills > 3 points apart (not the cause). **Two narrower rules, evaluated on the rows (nothing
built):** R1 "the hidden one's fill" (refuse when an unseen track under it holds the meter's fill and the seen track's
own memory does not) refuses 36 of 15,809; R2 "HP never rises" (refuse a reading > 3 points over the track's last)
refuses 29; **both refuse one of L9's right ties** - case 19 (Cave 3, frame 16559, track 2, 0.65: right by eye; its
track's previous reading, 0.61, was the hidden mob's) -> L9 82 of 83 (98.8 %) under either.

**For the user to decide (the tie, a fourth time):**
- **(a) keep the close as built** - L9 83 of 83; over the 13 captures a hidden mob's meter reaches the seen one in
  crowds of stacked mobs: at most 36 readings of 15,809 (0.23 %, R1's count) carry an unseen track's fill, 1 seen by eye
  across kinds (above); step 5 reads "HP rose" as a sign of an id error, not as a refusal.
- (b) R1 or (c) R2 as a refusal (36 / 29 refused; L9 82 of 83 - under 99 %).
- (d) back to try 2's guard (L9 61 of 83, never wrong).
My reading: (a) - the wrong ties are rare and sit where the ids themselves flicker (stacked mobs of one kind, a mob
the fit misses behind another); the meter's place rule is right on L9's every read meter. Step 5a stays NOT DONE until
the user's word.

**PART 2, report only: "could we use the meters to help when mobs overlap?"** (the user, 2026-11-27; t5a3's rows of the
13 captures against the truth's fair counts; `meter_overlaps.py all`; nothing built)

*a. Ids.* Each of the **994 fair id switches** (the pool's extra ids; 172 not beside another mob of its kind) is one
error: the truth's mob A leaves track O for track N. "A meter involved" = a meter the reader tied to A's or the other
mob B's sighting from 1 s before to 1 s after, or a meter memory on O or N; "the meters alone decide" = O's and N's
memories on the frame before differ (one has one, the other not, or > 3 points apart) and A's first meter state after
(a read fill, or "none" on 3+ frames) matches exactly one of them (B's not the same one). Matching O = the meter sides
with the truth (the tracker was wrong); N = with the tracker (the truth's own link was wrong).

| kind of error | n | a meter involved | the meters decide | with the truth / the tracker |
|---|---:|---:|---:|---:|
| crossing: the truth changed mob | 457 | 29 (6.3 %) | 8 | 0 / 8 |
| crossing: cannot say | 273 | 32 (11.7 %) | 18 | 1 / 17 |
| the track changed mob | 7 | 1 | 1 | 0 / 1 |
| a life split (the old track ended) | 54 | 8 (14.8 %) | 6 | 3 / 3 |
| old track remembered / far | 203 | 41 (20.2 %) | 17 | 7 / 10 |
| **all** (at a cover's end 137) | **994** | **111 (11.2 %)** | **50 (5.0 %)** | **11 / 39** |
| not beside another mob of its kind | 172 | 28 (16.3 %) | 14 | 8 / 6 |

By capture (n / involved / decide): the 30-minute Line 1 678 / 55 / 24, Cave 7 34 / 17 / 9, Cave 9 55 / 19 / 9, Line 1
4-minute 65 / 5 / 5, Cave 1 52 / 5 / 2, the rest 0-4. Involved but not decided: both memories none 30, both read alike
15, A's meter after matches neither (a hit between) 12, A's meter not read 4. The user's own rule on the TWO MOBS of a
crossing (their own meters before the switch): B found 736 of 737, both known 732, **told apart 25**. **By eye**
(`overlaps_t5a3_1..5.png`, cases 7-29): of the 11 "with the truth", 8 right (cases 7-9: one Bubbling behind us, its meter
0.46 steady, the tracker made 3 new ids in 10 frames; 10, 11 the same fill across a cover; 14, 16, 17 no meter over the
mob a track with an HP took), 1 two Bubblings stacked exactly (cannot tell), 1 the mob's meter under damage digits (the
"none" doubtful), 1 the old track's HP had already risen (12: it changed mob before). "With the tracker", where it can
be read (20, 22, 23): the meter is over the mob the tracker kept - the truth's own swaps of two of a kind (measurement
1). Also: **a track's taught HP rose by more than 3 points 29 times on 22 tracks, 21 within 2 s of a fair switch of it**
- a free id-error flag. So: the meters would fix about 8-11 of the tracker's 994 fair-count id errors (~1 %); most mobs
at a crossing carry no meter (killed in one hit) or the same.

*b. Hidden hit mobs* (the whole-screen finder's meters followed by place; a meter-frame with no seen mob under it =
`why_untied` "no seen mob"): **482 episodes, 12,912 meter-frames**.
- **A remembered track can be there** (its set within the kind's half body of the meter's implied feet, the feet
  within 20 px of the implied body top): **155 episodes, 1,813 frames**; s p50 0.07 / p90 0.52 / max 2.58 (30 of 0.25 s
  or more); two or more such tracks 55. Afterwards: seen again 132, ended unseen 23. **Seen again (132): |the meter's x
  - where it reappears| p50 2.0 / p90 16.9 / max 136 px, against |the set's middle - there| 9.0 / 32.9 / 174 and the
  set's width 76 / 116 / 364; inside its set 126 of 132; the meter closer by > 4 px 73, farther 12, within 8 px 108;**
  seen again after s p50 0.02 / p90 0.44. Cases 1-6 of the sheet: a Bubbling behind us, the meter within 1-2 px.
- **None can: 327 episodes, 11,099 frames** (s p50 0.05 / p90 1.7 / max 15.1): no track near (the fit missed the mob,
  or its body is off the play area) 249, a seen track whose expected box is > 40 / 60 px off 55, a remembered track not
  where the meter puts it 17, dying 5, tentative 1.

*c. Deaths while two mobs overlap* (a track's final death - its first row of the last dying stretch, `ended` "died" -
with another track's body over it; 16 deaths taken back not counted; the meter that went = a whole-screen meter chain
ending 0.6 s before to 0.1 s after the die pose near the two, no new meter at its place within 1 s; its owner = the
track it was last tied to): **187 deaths: no meter went 130** (killed in one hit: no meter), **agree 45**, the meter never
tied 1, **differ 11**, each looked at (`overlaps_t5a3_deaths_0..2.png`, `look_c_5772.png`, `look_c_35849.png`):
- 8: the meter's owner died too, within 1 s - 5 of them two mobs seen side by side 45-60 frames before (up to 3 die
  poses on one frame: killed together), 3 seen together on 6 frames or fewer (perhaps one body under two ids: step 5's
  corpse-track row). Not a disagreement: the death the tracker put was on a mob with no meter of its own.
- 1 the tracker right: Line 1 frame 73793, two Bubblings stacked, the tie named the wrong one at the meter's last
  frame (the owner lives on with its own meter).
- 1 the measuring tool's artefact: Cave 7 frame 35849 - the Evil Eye's meter was followed onto a neighbour's of the
  same fill (0.28, 13 of 46 columns), and the "meter that went" was a Zombie Mushroom's under the damage digits.
- **1 the tracker wrong, the meter right** (sheet case 0, `look_c_5772.png`): Line 1 frames 5740-5794 - track 70 carried
  the meter (0.57), 78 none; the meter went at 5760, the die pose came to 70 at 5764 (right), a living pose took it
  back at 5770 and the death went to 78; 70 lives on with hp 0.57 over a mob with no meter.

**The picture sheet** (`meter\overlaps_t5a3_0..5.png`, 30 cases, one row of three frames each, meters boxed magenta):
case 0 the death above, 1-6 hidden Bubblings placed by their meter, 7-17 id switches the meter decides against the
tracker, 18-29 for it. **My reading for the user** (the build-step question): not worth a step before step 5 - the
meter decides ~1 % of id errors and 1 of 187 overlapped deaths, and places a hidden mob better than the set mostly for
under 0.1 s; step 5 already takes the meter as a witness of hits and deaths, and can take "HP rose" as an id-error
flag. **The user decides** - with the tie's (a)-(d) above.

**The user's answers (2026-11-27; the plan manager re-ran `meter_overlaps.py ties`: the same numbers):** "drop the
meters overlap completely" - no build step, and none of Part 2 goes into step 5 (no "HP rose" flag, no death by the
meter). "I will provide multi hit per kill footage" - this footage is mostly one-hit Bubblings.

### Step 3b - spawn points as tracked things (added by the user, 2026-11-25; one executor session, measure then build)
**The user, 2026-11-25:** "keeping track of the time since last spawn (on spawn point) is a valid tracking object. It
would not be trying to add predictive abilities to the tracking behavior (my original rule), it is a part of
tracking's memory (which is OK) ... are mobs spawning exactly on the spawn point? If so we can treat spawn points as
objects themselves and keep track on each one since last visible spawn. We are just tracking this, it doesn't have
to be a part of the AI model, it is part of the overall data we collect."
- **What it is:** memory, not prediction. Each spawn point of the map (map.json: kind, x, y, foothold -> the node,
  `mobTime`) is a record: `last_spawn_t` (the last spawn SEEN there; None = none seen this stay), `last_mob` (the
  mob id born there), `spawns` (the count this stay), `in_view` (the point is on screen and not covered now). No
  respawn rule, no timer, no guess about spawns not seen.
- **A spawn seen** = a mob track born `faded in` (step 3's `born_how`) whose first feet are within the measured
  distance of a spawn point of its kind (two points near: the nearer). A mob born another way (came into view,
  uncovered, there at entry) is never a spawn.
- **Why the question comes first:** v83's client puts a new mob at its spawn point's position on its foothold
  (`docs/game_rules.md` E3: HeavenClient), but Classic World may differ, and observed data beats the rule.
- **Not in scope:** the 10 s respawn round, the refill target (E2) - not tracked, not predicted; the brain does
  not read it. `docs/state_model.md` gets the record (section 3, the frame) with the user's words.

### Step 3b, 2026-11-25: measured first; the gate MISSED (77.8 % within 10 px, >= 95 % asked) - stopped, nothing built
`tools/perc/track/proto_spawns.py` (`measure`, `why`, `sheet`, `beat`) over the step-4b replay's rows of the 13 sound
captures (`step3\*_s4b.pkl`: the current code); outputs `F:\dev\maple-corpus\work\track-plan\step3b\`. A birth = the
first row of a track id (its x, y = the first sighting's feet, map px); its point = the nearest of its kind in
map.json (x, y as given; no point is hidden on these 12 maps).
- **Births by how:** came into view 990, faded in 641 (612 confirmed), uncovered 322, there at entry 40.
- **Distance of the 612 confirmed faded-in births to the nearest point of their kind:** p50 **0.0**, p90 56.9, p95
  70.4, p99 130.4, max 239.7 px; within 3 px **64.9 %**, 5 px 68.5 %, **10 px 77.8 %** (gate >= 95 %), 20 px 82.5 %.
  |dx| alone: within 10 px 90.4 %; dy alone: within 10 px 87.6 %. No point of its kind within 20 / 40 / 100 px: 107
  / 91 / 17; no point of its kind on the map: 0. The nearest point of ANY kind gives the same numbers (no other
  kind's point is nearer). By kind (within 10 px): Bubbling 395 79.2 %, Horny Mushroom 66 90.9 %, Evil Eye 52
  78.8 %, Zombie Mushroom 49 85.7 %, **Stirge 28 7.1 %**, Green Mushroom 9 100 %, Slime 8 50 %, Drake 5 100 %.
- **Points near each other:** 0 pairs of the same kind within 20 px on all 12 maps (so "two points near: the
  nearer" never comes up).
- **The 136 births > 10 px, by what the numbers show** (`why`): **53 on the point's level, x off** (|dx| p50 20,
  p90 73, max 105; 48 of them moving away from the point over their first 0.5 s): walked before the fit saw them;
  **50 straight above the point** (x within 3 px, 35-50 px up; 47 in `jump_0`): hopped at once; **27 flyers**: 19
  within 10 px of map.json's **`spriteY`** (a flyer appears at its sprite height, not at `y`, which is the
  foothold), 8 not near either; 6 off in x and y. Their first sighting is later in the fade: the fit's opacity p50
  0.27 (p90 0.77) against 0.18 (p90 0.26) for those within 10 px - the fit sees a mob only from ~0.15 opacity on,
  so a mob that moves at once is first seen past its point. What-ifs, as numbers only: flyers against `spriteY` ->
  495 = 80.9 %; x within 10 px and the feet 0-60 px above the point -> 517 = 84.5 %; on its level within 40 px or
  above it within 60 px -> 549 = 89.7 %. None reaches 95 %.
- **The sheet** (`step3b\sheet_s4b\`: `sheet.png` + a 4-frame strip per case, +0 / 6 / 12 / 20 frames, the point a
  red cross): 30 random births matched within 10 px - **30 of 30 right by eye**: a mob fading in on the drawn point
  (case 19 under a megaphone's text, its cap showing over it; case 29, d 9, fades in 9 px left of the point and
  hops away).
- **Reported, nothing built from it (the user's ask):** the 476 spawns seen within 10 px are on 204 points (101 with
  2+): the time between spawns seen on one point p10 / p50 / p90 7.1 / 120.5 / 655 s (min 0.47 s, not looked
  into). **No 10 s beat** (R at 10.00 s: 0.03-0.71, spread). **The spawns come in rounds every ~7.09
  s**: per capture the best period in 6.5-7.6 s is 7.08-7.20 s with R 0.99-1.00 on 10 of 12 (the phase off p50
  0.04-0.10 s), R 0.81 on 1#1 (9 spawns), 0.76 on the 30-minute capture (7.084 s; the phase off p50 0.41 s: a drift
  or a shift over 30 min, not looked into); the gaps between rounds there fall at 7, 14, 21 s. So Classic World's
  respawn round is ~7.1 s, not E2's 10 s (`docs/game_rules.md` E2 not changed: the user decides).

**For the user (stopped, stop rule 1):** mobs DO appear exactly on their spawn point (p50 0.0 px; the sheet 30 of 30);
what misses the 10 px is when the fit first sees them: a mob that walks or hops off at once is first seen 20-50 px
away, and a flyer at its `spriteY`. Choose: (a) keep the 10 px rule and accept 77.8 % (a spawn the rule misses is
simply not counted: memory, not prediction); (b) a rule by shape, its share measured above (flyers at `spriteY`;
on its level within N px or straight above within 60 px), with its own sheet of the newly matched births; (c)
something else. The 7.1 s round: whether it goes into `docs/game_rules.md` E2 as observed (observed beats the rule).

**The user's answers (2026-11-25):** the 7.1 s round is in `docs/game_rules.md` E2 as measured (done on `dev`,
another session). Checked again by the plan manager, every confirmed faded-in birth, per capture: the best period
in 6.5-7.6 s is 7.01-7.20 s on all 13 captures (12 maps: Line 1, 10 dungeons / caves, Southern Forest III's
dungeon), and 200 sets of random times over the same span never reach its R (p 0.005 on each); the 13 pooled
(each its own phase, Z = n R^2 summed) peak at 7.08 s, Z 448, against 15 at 10 s (median over 4-13 s: 13). The 8
maps with 17+ spawns show it alone; the 5 with 5-11 only agree. No field map yet (not sound).
**The matching: (c), "a spawn traced back to its point"** - a faded-in birth is its point's spawn when a point of
its kind, on the same node, could have put the mob where it is first seen in the time it has existed: that time
from its opacity at the first sighting (the fade's length measured on Classic World first, against v83's 0.32 s:
E3), the distance by its kind's walk speed (kinds.py: 2 x v83) or one hop up; a flyer against the point's
`spriteY`; two candidate points -> no match (never a guess). Estimated ~96 % of the 612 (the plan manager:
476 + ~45 walked + ~47 hopped + 19 flyers + ~3), to be measured before anything is built. `in_view` = the point on
screen and not under the UI or a known cover box, on the CPU from what the trackers hold - no GPU call (a round
trip is ~0.4 ms: step 4b).

### Step 3b, try 2 (2026-11-25): rule (c) measured - the share MET (97.4 %), the sheet MISSED (3 wrong) - stopped, nothing built
`tools/perc/track/proto_spawns.py fade | trace | sheet2` (the step-4b replay's rows, `*_s4b.pkl`; outputs
`...\track-plan\step3b\`: `spawns_s4b.pkl`, `sheet2_s4b\`).
- **1. The fade on Classic World is 0.82 s, not v83's 0.32 s** (`fade`): each faded-in track's opacity (the fit's) on
  every frame of its first 1.5 s; a line o = (t - t0) / L over its sightings with 0.1 <= o <= 0.9 fits 593 of the
  612 with R^2 >= 0.999 (p10); **L p10 / p50 / p90 = 0.803 / 0.816 / 0.827 s** (49 frames at 60 a second; E3's HC
  0.32 s = 19 frames). From a faint first sighting (opacity <= 0.25, 423 tracks) to 0.95: 36 / 39 / 40 frames. So the
  time since appearing = the first opacity x 0.827 s (the p90, the reach's upper side). `docs/game_rules.md` E3 not
  changed (another session's file on `dev`): the user decides. The first sighting's opacity p10 / p50 / p90 0.14 /
  0.18 / 0.35 (the fit sees a fading mob from ~0.14 on: ~0.12 s after it appears).
- **2. Rule (c)** (`trace`; a walker: the point of its kind on the birth's node (the tracker's), |dx| <= its kind's
  `v` (kinds.py, 2 x v83) x the time + 10 px, the feet within 10 px of the node's surface or up to one hop (78 px,
  measurement 3) + 10 px over it when the kind jumps; a flyer: (x, `spriteY`) within `v` x the time + 10 px; two
  candidates -> no match): **596 of 612 = 97.4 % matched** (>= 95 % met); 7 = 1.1 % two candidates; 9 = 1.5 % none.
  The 10 px rule's 476: 475 matched by (c) too, 1 not (a Stirge at its point's `y`, 154 px from its `spriteY`).
  - By group (matched / two / none): within 10 px 476: 475 / 0 / 1; walked 53: 45 / 7 / 1; hopped 50: 48 / 0 / 2;
    flyers 26: 26 / 0 / 0; other 7: 2 / 0 / 5.
  - By kind: Bubbling 385 of 395 (97.5 %), Horny Mushroom 64 of 66, Evil Eye 51 of 52, Zombie Mushroom 47 of 49
    (95.9 %), Stirge 27 of 28, Green Mushroom 9 / 9, Slime 8 / 8, Drake 5 / 5.
  - The 16 left: **7 two candidates** (Bubblings on Line 1 first seen at opacity 0.78-0.89, i.e. 0.65-0.74 s old:
    two points 100-220 px apart on one node both within reach); **5 no point of its kind on its node** (two
    Bubblings first seen over node 285, their point 7 is on node 244; a Zombie Mushroom, an Evil Eye likewise; first
    seen in the air over another platform); **3 farther than the reach** (|dx| 60 / 61 / 106 against 50 / 51 / 61:
    a Horny Mushroom, a Zombie Mushroom, both 2026-11-18); **1 Stirge** 154 px from its point's `spriteY`.
  - Same-kind point pairs within 100 px on one node: 0 on 10 of the 12 maps; 4 on 10005064, 2 on 10005065.
- **3. The sheet** (`sheet2`; 30 random births matched by (c) and not by the 10 px rule, seed 5: 13 hopped, 12
  walked, 5 Stirges; a 4-frame strip each - the frame it appeared on, halfway, its first sighting, +10 - the crop
  fixed on the point in map coordinates, each frame's own camera): **the point is the right one on 29 of 30**
  (case 25: the point stands 25-45 px past the screen's right edge, the mob walks in fading - not checkable by eye,
  nothing against it), **but 3 births are not a new spawn: cases 11, 23, 29 are the SECOND track of a mob already
  credited to the same point** -> 27 of 30 right (>= 29 asked): **MISSED**.
  - Why (the rows): one fading-in mob, two tracks. Of the matched births, **9 pairs on one point come < 1 s apart**
    (0.05 s once, 0.47-0.57 s eight times; the next gap is 3 s+): in the eight, the first track turns `dying` at
    0.47-0.57 s into the fade (opacity ~0.6) while a new track carries on, born `faded in` - the mob tracker takes a
    die pose of the faint mob (the fit's reading) and ends the first track; the 0.05 s one is a knockback in the fade
    (ids 61 / 62 / 63 of `20261120_235747_1#0`, one Bubbling). That is step 3's mob tracker, outside this step
    ("nothing in track/mobs.py changes but the call").
  - The bug found on the way (fixed in the tool before these numbers): a first sighting read as its look-alike pose
    (17 px over) had its opacity taken from a later frame (case 18: 0.98 instead of 0.41); now the birth frame's
    sighting within 20 px, or an error.

**For the user (stopped, stop rule 1):** rule (c) finds the right point (97.4 % matched; the point right on 29 of
30), but 9 of the 596 matched births (1.5 %) double one spawn because the mob tracker splits a fading-in mob in two.
Choose: (a) spawns.py takes E1's / MW's "a point holds at most one living mob": a birth on a point whose last mob is
still in the state (alive or dying) within one fade (0.83 s) of its spawn is the same spawn, not a new one -
measured first, then a new sheet; (b) fix the split in the mob tracker first (a die pose not taken while the
track is fading in: step 3's code, its gates re-run); (c) accept the 1.5 %. And whether E3 gets the measured 0.82 s
fade (observed beats the rule).

**The user's answer (2026-11-25): (b), fix the split in the mob tracker** (prompt "Tracker, step 3b, try 3"). The
plan manager's reading: each split is a **false death** (a mob "dies" untouched), which reaches step 5's kills,
4a's `from_mob` and the id counts - so the cause is fixed, not hidden in spawns.py. A death fades the body OUT, a
spawn fades it IN: a die pose is taken only while the opacity is not rising, never on a track still fading in. The
0.82 s fade into `docs/game_rules.md` E3: not yet asked.
**The user, 2026-11-25, widened it:** "treat the fade direction as a general rule in the mob tracker ('dying needs
falling opacity, a spawn needs rising'), not only as the narrow fix". So: a track turns `dying` only on a die pose
with the opacity falling (or the die pose at full opacity, if the measurement shows deaths start there); a birth is
`faded in` only with the opacity rising over its first sightings - a faint mob whose opacity is flat (seen through
an effect) is neither. Measured first, because the death gate (noticed p90 <= 0.05 s) rests on when the fade-out
starts in a death.

### Step 3b, try 3 (2026-11-25): the fade direction built; step 3's gate MET on every row but the feet's jolts (599, <= 556) - stopped before spawns
`tools/perc/track/fade_dir.py` (`series | splits | deaths | births | strips`; outputs `...\track-plan\step3b\fade\`).
**1. Measured on the step-4b rows (`*_s4b`), nothing changed:**
- **a. A death taken back or a split:** 957 tracks turn `dying` (13 taken back by the same track); 47 are followed
  within 1 s by a new track of their kind within 30 px: **33 while fading in** (born faded in, 0.45-0.65 s old,
  every one in `die1_2`, the opacity rising on all 33 - the strips: a Bubbling landing from its spawn hop, squashed,
  read as `die1_2`), 10 other (real deaths whose die animation the fit then reads as a live pose - a new track on
  the body - and 2 under the UI), 3 overlaps (two Bubblings overlapping as one dies), 1 after a hit.
- **b. Real deaths (899):** the die pose starts at **full opacity** - the first die sighting >= 0.97 on 99.1 %; the
  opacity stays 1.00 for 21 frames (p50; p90 25) and falls from frame ~20 (0.33 s); the first die frame against the
  next: flat 867, falling 5, rising 3 of 875. So "falling" alone would slow the death gate by ~20 frames; the rule's
  "or at full opacity" keeps it at the first die frame - the stop of the prompt's 1b was read as that (the premise "the
  rule would slow the death gate" does not hold with the full-opacity half; the gate's re-run below checks it: p90
  0.000 s).
- **c. Faded-in births (641):** rising 618 (confirmed 604 of 612), flat 8, falling 5, one sighting 10; the flat
  ones sit at 0.49 / 0.50 (2026-11-18 captures: seen half-transparent, the strips); by the 3rd sighting 617 have
  risen > 0.02; one frame's rise while fading p1 / p50 0.007 / 0.023.

**2. Built (`track/mobs.py`, `config.Track`; nothing else changed):** a die pose on a track not dying: the opacity
**risen** more than `fade_eps` (0.005) since its last sighting -> the live mob (at any level: the fade's last frames
reach 0.973); else at **full** (`die_full_o` 0.97) or **fallen** more than 0.005 -> `dying`; flat and faint -> the
live mob. A birth under `fade_o` in a live pose is "faded in" only when its opacity rises more than `fade_rise` (0.02)
within its first `fade_k` (3) sightings; flat or falling -> came into view / uncovered as otherwise; until settled the
record says "faded in" and its `mob_new` waits (stats: 10 faint births settled otherwise, 49 die poses taken as the
live mob). Tests (each fails with its rule switched off): `test_a_fading_in_mob_read_in_a_die_pose_stays_one_live_track`
(+ the fade's last frame at 0.973 - the first build's `>= 0.97 first` left 2 splits: fixed to the user's words, "a die
pose with the opacity rising is the live mob"), `test_a_death_at_full_opacity_or_fading_out_turns_dying_at_once`,
`test_a_faint_birth_is_faded_in_only_with_its_opacity_rising`. pytest all green; bot speed 14.9 ms a tick (track
0.4 ms) - unchanged.

**3. Step 3's gate, from the kept replay (`*_f3c`, the sorted tags as live), against the 4b rows:**

| Row | 4b (`s4b`) | now (`f3c`) | |
|---|---:|---:|---|
| found (>= 98.4 %) | 98.70 % | 98.70 % | met |
| id kept across a cover (>= 93.1 %); by length | 93.48 %; 97.0 / 96.5 / 94.1 / 79.4 / 77.4 | 93.54 %; 97.1 / 96.5 / 94.1 / 79.4 / 77.4 | met |
| one id for life not beside another (>= 90.6 %) | 90.98 % | **92.39 %** | met (up: the splits gone) |
| extra ids (<= 1,032); changed mob (<= 10) | 1,019; 7 | **993**; 7 | met |
| next to its set (>= 99.0 %); a death noticed p90 (<= 0.05 s); ghosts | 99.35 %; 0.000; 0 | 99.35 %; 0.000; 0 | met |
| "died (seen)" ends | 979 | 945 | 34 false deaths fewer |
| hops within 1.5 px (>= 91 %) | 91.4 % | 91.4 % | met |
| **feet jolts (<= 556)** | 550 | **599** | **MISSED** |
| L1 / L2 / L3 (as accepted) | 98.98 % / 15 of 16 / 19 of 22 | the same | - |
| 1a again: splits while fading in (0) | 33 | **0** | met (13 left: 10 real deaths / UI, 3 overlaps) |

**Why the jolts rose (every one of the new 48 on the first build, f3b: 550 -> 597; f3c 599):** each has `die1_2` in
its three frames - the fit names the faint landing squash `die1_2` (the client's `die1_2` is a flat puddle, NOT
`move_5`'s picture: no look-alike) and that reading puts the feet **exactly 18 px over** the `move_5` readings on
either side (e.g. y 198, 180, 198). Before, the track split there (the old track "died", the new one began), so the
step was never inside one track; now the die reading's wrong feet are. The feet everywhere else are unchanged (hops
91.4 %, the same residuals).

**For the user (stopped, stop rule 1; spawns.py not started):** the fade rule removes every fading-in split and 34
false deaths, but the die reading it keeps moves the feet 18 px for one frame. Choose: (a) a die pose taken as the
live mob does not move the feet (its pose is the fit's misreading, so are its feet: the track keeps its last feet
that frame) - the jolts expected back to ~550, re-run; (b) take the die reading as "not seen" that frame (the track
fading in is not checked for `fade_s` anyway); (c) accept 599 (the 49 are the fit's one-frame misreads, counted
now that the tracks hold). Then step 4 (trace + the sheet) and spawns.py as the prompt says.

**The user's answer (2026-11-25): (a)** - built: a die pose taken as the live mob is seen, but its feet, place,
node and speed stay the last ones that frame (`track/mobs.py` `live_die`; the test's die reading 18 px over the
floor on a jumping kind keeps the feet at 500, `stand` - it fails without (a): 482, `air`). pytest all green; bot
speed 15.1 ms a tick (track 0.4) - unchanged. **Step 3's gate again (`*_f3d`):** found 98.70 %, id kept 93.51 %
(97.0 / 96.5 / 94.1 / 79.4 / 77.4), one id 92.33 %, extra ids 994, changed mob 7, next to its set 99.35 % of 2,786,
a death noticed p90 0.000 s, hops 91.4 %, **jolts 524 (<= 556: met**, under 4b's 550), L1 / L2 / L3 as accepted
(98.98 % / 15 of 16 / 19 of 22), splits while fading in 0 (13 left: 10 real deaths / UI, 3 overlaps) - **but seen
track-frames with no truth mob within 40 px: 1 (0): MISSED** - stopped again, step 4 not started.
- **The one frame** (`20261120_235747_1#0` n 14359, track 169, a Bubbling born faded in 3.6 s before, remembered
  for 8+ frames): a REAL death at the screen's left edge - the fit's `die1_0` at opacity **1.00** (feet at map x
  715 = the truth's mob; 4 % of the body on screen) - paired with the remembered track, whose last opacity was a
  little under 1.0: "risen more than 0.005" -> taken as the live mob (the first build's fix: rising wins at any
  level, for the fade's last frames at 0.973), and (a) then put its feet at its last SEEN place, 761 - 46 px from
  the mob. So the two halves of the rule meet: 0.973 at the end of a fade must be "rising", 1.00 at a death must be
  "full".
- **Measured** (the 4b rows): real deaths' first die sighting >= 0.99 on 887 of 896 (99.0 %; one in 0.97-0.99);
  the fading-in false deaths' die readings reach 0.949 on the 4b rows and 0.973 on the first build's (f3b: the two
  left at the fade's very end). A line at **0.99** checked FIRST (full -> dying; under it: rising -> the live mob,
  fallen -> dying, flat -> the live mob) separates them on every case measured.

**For the user (stopped, stop rule 1: "no changed constant"):** choose (a) `die_full_o` 0.97 -> 0.99 and the full
check first again (the first build's order, with the line the measurement gives), re-run; (b) the fade rule only
on a track seen on the last frame (the opacity compared across a gap of 8 frames says little), re-run; (c) accept
the one frame. Then step 4 (trace + the sheet) and spawns.py.

**The user's answer (2026-11-25): (a) and (b) together - built; every gate MET; spawns.py built, in shadow.**
- **The rule** (`track/mobs.py`, `config.Track`): `die_full_o` **0.99, checked first** (full -> dying); under it the
  direction only from two NEIGHBOURING sightings (fallen -> dying, rising or flat -> the live mob, its feet kept);
  a die pose under 0.99 on a track not seen on the frame before is **held** (seen, feet kept) and judged on its next
  sighting (fallen -> dying from the held frame). Tests (each fails with its rule switched off):
  `test_full_opacity_is_checked_first_a_death_even_after_a_faint_sighting`,
  `test_a_die_pose_on_a_remembered_track_is_held_and_judged_on_its_next_sighting` (+ the three of try 3).
  **Die poses on a remembered track: 11** on the 13 sound captures (held; next sighting: 4 not fallen -> alive, 4 a
  live pose, 0 fallen, 3 full or never seen again); 48 die poses taken as the live mob.
- **Step 3's gate (`*_f3e`, = `*_f3s`):** found 98.70 %, id kept 93.51 % (97.0 / 96.5 / 94.1 / 79.4 / 77.4), one id
  92.33 %, extra ids 994, changed mob 7, next to its set 99.35 % of 2,786, a death noticed p90 0.000 s, **ghosts 0**,
  hops 91.4 %, **jolts 524**, L1 98.98 % / L2 15 of 16 / L3 19 of 22 (as accepted), splits while fading in **0** -
  every row met.
- **Step 4, rule (c) (`proto_spawns.py` on `*_f3e`):** 597 confirmed faded-in births (622 in all; 10 faint births now
  settled otherwise by the rise rule); **585 = 98.0 % traced to one point (>= 95 %: met)**, 5 two candidates (Line 1
  Bubblings 0.65-0.74 s old), 7 none; the fade 0.816 s (p10-p90 0.803-0.827). Doubled spawns (a point's two matched
  births < 3 s apart): **1** (ids 60 / 61 at point 27 of `20261120_235747_1#0`: one Bubbling knocked back while it
  faded in, split by the knockback - not the fade).
- **The sheet** (`step3b\sheet2_f3e\`, 30 random births matched by (c) and not by 10 px): **29 of 30 right** - 1 wrong
  (case 11: the doubled spawn above); 27 checked right by eye (case 7: a spawn hopping onto its point as another mob
  dies 48 px away, its opacity rising 0.25 -> 0.77; case 8: first seen faintly on the point as a tentative track that
  never confirmed, then 62 px on); cases 23 and 30: the point 25-45 px past the screen's edge, the mob coming in
  fading straight over it (30) or walking away from it (23) - not checkable by eye, nothing against them, counted
  right as try 2's case 25 was. **Met (>= 29).**
- **Built:** `track/spawns.py` (`Spawns`: first sightings from the mob tracker's records, the spawn on its `mob_new`
  event with how "faded in" - the event waits until that is settled -, rule (c), `in_view` on the CPU from the
  boxes the trackers hold + the UI; event `spawn_seen`), `state.SpawnPoint` (index, kind, x, y, sy, node, mob_time,
  last_spawn_t, last_mob, spawns, in_view), the graph keeps each point's index, spriteY and mobTime, `config.Track`
  spawn_fade_s 0.827 / spawn_slack 10 / spawn_hop 78; the Perceiver calls it after the mob tracker, in shadow (part
  `spawns`); `docs/state_model.md` section 3 item 6 with the user's words. Tests `tests/test_track_spawns.py`, 9 (each
  rule's test fails with the rule removed: the time since it appeared, its node, one hop for jumpers, a flyer at
  spriteY, two candidates -> none, only faded in, in_view's covers, blind). Tools: `replay_mobs.py` runs it (`run`
  stores `sp_ev` / `sp_view`, `spawns` pools it, `live` compares it); `dump.py` keeps the shadow's spawn rows.
- **The real code on the 13 sound captures** (`replay_mobs.py spawns --sound --tag f3s`): 594 faded-in mobs
  (`mob_new`), **585 traced to one point (98.5 %)**, 5 two or more, 4 none - the prototype's 585 of 597 (its kind =
  the last vote; the real code's = the vote at confirmation).
- **The live path** (a new kept replay of `20261120_235747_1#0` on today's build: `work\20261120_235747_1#0\track_s3b\`,
  its own folder - stop rule 5): shadow mob rows = the replay's on **79,109 of 79,109** track-frames, **spawn rows
  (spawns seen + in_view) = the replay's on 15,211 of 15,211 frames**, the GPU evidence = the bitmaps' on 100 % of
  9,866,248 places. **The ms:** the spawns' p50 / p90 / p99 **0.045 / 0.049 / 0.064 ms** live (64 points; the GPU
  path, timed exactly over 2,970 frames; <= 0.1: met), 0.05 / 0.08 / 0.16 on the replay. pytest all green; bot
  speed 15.6 ms a tick (the part list's `spawns` 0.1 rounded; `fit` alone 7.1 against 6.8 earlier: the machine) -
  unchanged within noise.

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
Tracker, step 3, try 2 (mobs, in shadow: the user's answers, then the rest of the gate). Read PLAN-tracker.md -
step 3's row, "Step 3, 2026-11-24" and "The user's answers" under it, design 2-4, the stop rules. Branch
tracker-build (the main folder is on it). Build the answers: stand within 5 px on a slope (3 px on flat ground
stays); a flying kind is never stand; relabel the 29 bounce cases of L1 to stand in the bank's file (a note of which, in the file and the
plan); L2 without the 5 "none" cases (reported apart), edge first, either of two covers right; L3 with "how it came
into sight" and "first pose" as two fields. Tests for each rule (a test fails without it). Re-run the whole gate
from the kept replay (13 sound captures, jolts <= 556, L1-L3, L8 reported), then the live path (a new kept replay
of 20261120_235747_1#0 into its own folder, never over work\SESSION#K\track\ - stop rule 5) and the ms gate (in
the main folder: assets/scene is there). Numbers into the plan under "Step 3, try 2"; a gate missed: stop.
```
```text
Tracker, step 3, the slope fix (the user, 2026-11-25). Read PLAN-tracker.md - design 3, step 2's row, "Step 3,
try 2" with its "The user's decision" (carry-over 1), the stop rules. Branch tracker-build (the main folder). In
track/graph.py the step rule (1 px + 0.9 x the sideways step) becomes: the step follows the foothold's own slope
(its rise over the sideways step) + 1 px of whole-pixel slack; nothing else changes. Relabel L1 case 124
(232410_1#4 n 21529, a dying Horny Mushroom labelled fly) to stand in the bank's file, with `was` + the user's
words, backup first. A test that fails without the fix (a mob walking a 1.8 slope, a 2 px step for 1 px on a 0.6
slope). Gate: L1 stand / air >= 99 % (replay_mobs.py labels); step 2's hops gate still met (proto_feet.py --sound:
air called standing <= 0.8 %, standing called air <= 0.2 %); from the kept replay the 13 captures' rows and the
feet still within step 3's gate (jolts <= 556); pytest of the areas touched. Numbers into the plan under "Step 3,
the slope fix"; a gate missed: stop.
```
```text
Tracker, step 3b (spawn points as tracked things; added by the user 2026-11-25). Read PLAN-tracker.md - "Step 3b"
(the user's words), its row in the steps table, design 2-3, "Step 3, try 2" (born_how), the stop rules -
docs/state_model.md section 3 and docs/game_rules.md E1-E3. Branch tracker-build (the main folder).
FIRST MEASURE, build nothing: over the 13 sound captures of the kept replay (step 3's tracker output, the *_slope
files or a fresh replay_mobs.py run), take every track born "faded in" and its first feet; match it to the spawn
points of its kind on that map (map.json); report the distance (p50 / p95 / max, the share within 3, 5, 10, 20 px),
how many births have no point of their kind near, and how many points stand within 20 px of another of the same
kind. Make a sheet of 30 random matched births (the frame, the point drawn) and check each by eye. If fewer than
95 % fall within 10 px, or the sheet shows them elsewhere: stop with the distribution - the user decides.
If met: build track/spawns.py (reads the mob tracker's births each frame; nothing in track/mobs.py changes but the
call), the SpawnPoint record in state.py (last_spawn_t, last_mob, spawns, in_view), the Perceiver calls it after the
mob tracker, in shadow; add the record to docs/state_model.md section 3 with the user's words. Tests (a test fails
without each rule). Gate: the row in the steps table - the 30-case sheet >= 29 right, the live path's rows (the
kept replay track_s3 of 20261120_235747_1#0) = the replay's, the ms p50 <= 0.1. Also report, as numbers only
(nothing built from them): the time between spawns seen on one point, and whether spawns seen fall on a 10 s beat.
Numbers into the plan under "Step 3b"; a gate missed: stop.
```
```text
Tracker, step 3b, try 2 (spawn points: a spawn traced back to its point - the user's answer (c)). Read
PLAN-tracker.md - "Step 3b" (the user's words), "Step 3b, 2026-11-25" and "The user's answers" under it, step 3b's
row, the stop rules - tools/perc/track/proto_spawns.py, docs/game_rules.md E1-E3. Branch tracker-build (the main
folder). FIRST MEASURE, build nothing (extend proto_spawns.py):
1. The fade's length on Classic World: births seen from their very first faint frame -> frames until full opacity
   (against v83's 0.32 s); the opacity -> time-since-appearing mapping used below comes from this, not from E3.
2. Rule (c) on the 612 confirmed faded-in births: a point of its kind, on the same node, reachable in the time since
   appearing - walk at its kind's speed (kinds.py, the 2 x v83 factor) or one hop up; a flyer against the point's
   spriteY; two candidate points -> no match. Report the share matched (>= 95 % asked), by kind and by the why-groups
   (walked, hopped, flyers, other), the ones left with the reason, and how many births had two candidates; also the
   same-kind point pairs within 100 px on one node, per map.
3. A sheet of 30 random births matched by (c) that the 10 px rule did not match (the 4-frame strips, the point
   drawn): each checked by eye.
If the share is under 95 %, or the sheet has more than 1 wrong: stop with the numbers - the user decides.
If met: build track/spawns.py (reads the mob tracker's births each frame; nothing in track/mobs.py changes but the
call), the SpawnPoint record in state.py (last_spawn_t, last_mob, spawns, in_view), the Perceiver calls it after the
mob tracker, in shadow. in_view = the point on screen and not under the UI or a cover box the trackers already hold,
on the CPU - no GPU call. Add the record to docs/state_model.md section 3 with the user's words. Tests (a test fails
without each rule). Gate: step 3b's row - the share >= 95 %, the sheet >= 29 of 30, the live path's rows (the kept
replay track_s3 of 20261120_235747_1#0) = the replay's, the ms p50 <= 0.1. pytest of the areas touched + the bot
speed line. Numbers into the plan under "Step 3b, try 2"; a gate missed: stop.
```
```text
Tracker, step 3b, try 3 (the fade direction as a general rule of the mob tracker - the user's answer (b), widened by
the user - then spawn points). Read PLAN-tracker.md - "Step 3b, try 2" and "The user's answer" under it (with the
user's widening), step 3's row and gate, design 2-4, the stop rules - track/mobs.py,
tools/perc/track/proto_spawns.py. Branch tracker-build (the main folder).
1. MEASURE FIRST, change nothing, over the 13 sound captures (the *_s4b rows):
   a. every track that turns dying and is followed within 1 s by a new track of its kind within 30 px (a death
      "taken back" or a split): how many, how many while the first track was fading in (born faded in, under
      0.83 s old), what the rest are (overlaps swapping poses, knockback, other) - a few of each on strips;
   b. real deaths (dying, never seen alive again): the opacity over the die pose's first frames - from which frame
      it falls (the first? after N frames at full opacity?), p50 / p90;
   c. faded-in births: the opacity over the first sightings - rising on how many; births whose opacity is flat or
      falling, what they are (through an effect, uncovered, other) on strips.
   If b shows the fade-out starting later than ~2 frames into a death, the general rule would slow the death
   gate: stop and report - the user decides.
2. THE RULE in track/mobs.py (the user's): a track turns dying only on a die pose with the opacity falling (or at
   full opacity on the die pose's first frames, as 1b measured); a die pose with the opacity rising is a sighting
   of the same live mob. A birth is "faded in" only with its opacity rising over its first sightings; a faint mob
   with a flat opacity is born by how it came into sight otherwise. Nothing else changes. Tests that fail without
   each half (a fading-in mob read in a die pose at opacity 0.6 stays one live track; a real death still turns
   dying within the gate; a flat-faint birth is not faded in).
3. Re-run step 3's gate from the kept replay (replay_mobs.py run / pool / feet / labels, the sorted tags as live):
   every row as in the slope fix / 4b (found 98.70 %, id kept 93.48 %, one id 90.98 %, extra ids <= 1,032, changed
   mob <= 10, next to its set >= 99.0 %, a death seen noticed p90 <= 0.05 s, ghosts 0, jolts <= 556, L1-L3 as
   accepted) - report every row that moves and why; a row that falls past its gate: stop. Count 1. again: the
   fading-in splits must be 0.
4. Then step 3b try 2's measure (trace) and a new 30-case sheet of births matched by (c) and not by 10 px: the
   share >= 95 %, the sheet >= 29 of 30 (a doubled spawn counts wrong). If met, build spawns.py exactly as try 2's
   prompt says (in shadow, in_view on the CPU, no GPU call; state_model.md section 3 with the user's words; tests),
   its gate: the live path's rows = the replay's, the ms p50 <= 0.1; pytest of the areas touched + the bot speed
   line. Numbers into the plan under "Step 3b, try 3"; a gate missed: stop.
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
by side are split by the widths already known; pets are sorted out. Also step 3's carry-over 2 ("Step 3, try 2",
"The user's decision"): the mob tracker's covers use the sorted tags, `edge` = the sides and the window's bottom, L2
re-graded on the 16 (>= 90 %). Gate as written; numbers into the plan; a gate missed: stop.
```
```text
Tracker, step 4b, try 3 (players, pets and us: the user's answers of 2026-11-26). Read PLAN-tracker.md - design 1
("clean sightings teach, crowded ones only follow"), step 4b's row, "Step 4b, try 2" and "The user's answers
(2026-11-26)" under it, the stop rules - track/players.py, us.py, graph.py, evidence.py. Branch tracker-build (the
main folder).
1. MEASURE FIRST: a sheet of all 13 labelled pet tracks now called players (as heights_pet.png: the labelled frame +
   the frames where the track holds another name's box); confirm the 10 are a track on another name's box and find
   why the side-by-side split did not fire on track 815's merged "GODxWAR" + "il".
2. Build: a track continues only on a box of its own name's width; a merged box is split by the widths known; the
   class, the body height and the name width learn only from sightings standing alone (no other tag or body
   touching). Keep the 75th percentile and the 50 px line. Add design 1's rule to docs/state_model.md with the
   user's words.
3. Ropes (us): on a rope only after a grab with up or down down; staying needs no key; past a rope without the key
   = not on it, whatever the speed. The speed test goes. Live (no keys until step 9): the plain rule. Players: measure
   no test against the speed test on L5's nodes, keep the better.
4. The ms: a track whose class is settled is not asked the body question again; measure live (the Perceiver, the
   4-minute capture, parts us_players and track) and report - the user sets the line from it.
Tests (each fails without its rule). Gate: L5 as in try 2 (players found >= 95 %, non-players called players <= 1 %,
pet / player mixed <= 5 %, the node >= 95 %, "not yet known" apart), the cover <= 29, L1 us (>= 99 %, or accepted at
what the key rule reaches - report the misses), step 3's rows and step 2's hops gate unchanged, pytest + the bot
speed line. Numbers into the plan under "Step 4b, try 3"; a gate missed: stop.
```
```text
Tracker, step 4b, try 4 (the user's answers to try 3, and a cheaper body check). Read PLAN-tracker.md - design 1,
step 4b's row, "Step 4b, try 3" and "The user's answers (2026-11-26)" under it, the stop rules -
track/players.py, evidence.py. Branch tracker-build (the main folder).
1. Grading (tools only): a track with fewer than 5 alone body readings at the labelled frame is "not yet known",
   set apart like a track seen under 6 times; report how many tracks stay unsure their whole life and why. The 2 s
   cover is graded as a rate: back under a new number <= 10.4 % of player tracks (29 of 280).
2. Build A: an unsettled track's tag is asked the body question every 4th frame, not every frame (the frame it is
   first seen is always asked). Build B: a track settles early when its class is clear - from 8 alone readings, the
   75th percentile at 40 px or less, or 60 px or more (10 px from the 50 px line); near the line it still needs
   body_settled 30. Constants in config.Track. Tests (each fails without its rule).
3. Measure: L5 (players found >= 95 % with unsure apart, non-players called players: 2.04 % accepted - report it,
   must not rise; pet / player mixed <= 5 %; the node >= 95 %), the cover rate, the delay until a class is known
   (p50 / p90 / p99, against try 3's 12 / 77 / 251 frames), L1 us (accepted at 95.05 %: must not fall), step 3's
   rows and step 2's hops gate unchanged. The ms live (the Perceiver): the 4-minute capture (us_players and track,
   p50 / p90, the body check's share) and the steady state on the 30-minute capture, minutes 5-30. Report the
   numbers - the user sets the ms line from them.
4. pytest + the bot speed line. Numbers into the plan under "Step 4b, try 4". A gate missed: stop. If every gate
   is met, write step 4b as DONE (the user's accepted items 2 and 5 named) in the plan's status lines and HANDOFF.
```
```text
Tracker, step 4b, close (the user's decision on try 4). Read PLAN-tracker.md - "Step 4b, try 4" and "The user's
decision" under it, the stop rules. Branch tracker-build (the main folder). The user: A and B go - back to try 3's
sampling (body_every 1, no early settle): take A and B out of track/players.py and config.Track with their tests;
keep the grading tools (unsure apart, unsure_why, the cover rate, --cfg). Re-run L5, the cover, L1 us and step 3's
rows: they must equal try 3 regraded (found 95.8 %, cover 9.6 %, pet / player 2.87 %, the node 96.5 %, non-players
2.13 % accepted, L1 us 95.05 % accepted). The ms line, set by the user: us_players live p50 <= 0.5 ms, p90 <= 1.0 ms
(the 4-minute capture). pytest + the bot speed line. Numbers under "Step 4b, close"; if met, step 4b DONE in the
plan's status lines and HANDOFF (accepted: non-players 2.13 %, FreakyRafiki, L1 us 95.05 %; a cheaper call left for
step 9). A gate missed: stop.
```
```text
Tracker, step 5a (the HP meter; added by the user 2026-11-26, before step 5). Read PLAN-tracker.md - "Step 5a" (the
user's observations are the spec), its row in the steps table, measurement 6, design 1, the stop rules -
docs/state_model.md sections 3-4, perception/slots.py and hud.py (readers of the same kind). Branch tracker-build
(the main folder). No v83 references: everything from the recordings.
FIRST MEASURE, build nothing in maplebrain/, on the 13 sound captures and their keys: the meter's picture (size,
colours: green = HP left, dark red = lost); its place above the mob for small / mid / big / flying kinds against the
sprite box and mob.json's head point (one rule for every size?); the delay from our hit (q / w / e windows,
measurement 6) to the meter appearing and from the death to its going; whether a meter ever shows on a mob we did
not hit; our own first hit's share per mob kind (mobs seen from full HP, no other hitter) and the first readings of
mobs another player hit before us; several meters, two mobs close, under effects, at the screen's edge. Make label set L9 by eye (100 frames
with a meter, every kind of case: its mob, its fill in %; 10 % looked at twice, blind: >= 95 % agree) and a picture
sheet of the odd cases. If a meter shows on a mob we did not hit, or cannot be tied to its mob: stop with the
numbers - the user decides.
Then build: perception finds the meters and reads each one's green share (FrameFacts gets them: box + fill), looking
in a band above the mobs, not the whole screen; the mob tracker ties each meter to its track (the mob record: hp
0-1, hp_t; kept while the track lives; None when never read; a meter over two overlapping mobs teaches nothing -
design 1), in shadow; docs/state_model.md gets the field with the user's words. Tests (each fails without its rule).
Gate: step 5a's row (ms p50 <= 0.1; more than 1 ms added a frame: stop and discuss); step 3's rows unchanged;
pytest + the bot speed line. Numbers into the plan under "Step 5a"; a gate missed: stop.
```
```text
Tracker, step 5a, try 2 (the tie: trust the candidate). Read PLAN-tracker.md - "Step 5a, 2026-11-26" and the user's
answers under it, design 1, the stop rules - and maplebrain/track/mobs.py `_meters` / `_overlapped`,
perception/meters.py, tools/perc/track/replay_meters.py. Branch tracker-build (the main folder).
Change only the tie in track/mobs.py: a meter whose candidate is one seen sighting, its fill read, teaches that
sighting's track even when another SEEN track overlaps it; the overlap guard stays only against tracks NOT seen on
this frame (remembered, hidden, tentative not seen; dying ones excluded as now). The reader, the place rule, the fit
and everything else unchanged. Tests: the seen-overlap case now taught, the remembered-overlap case still refused
(each fails without its rule); the old guard test changed to match.
Run replay_mobs.py run --sound --meters --tag t5a2, replay_meters.py l9 --tag t5a2, replay_mobs.py pool + feet +
labels, the whole pytest.
Gate: on L9's meters whose fill the reader read (83 in try 1): tied to the right mob >= 99 %, wrong 0 (one wrong:
stop with the case and its picture); the not-tied ones by reason; the 27 unread fills reported, not graded. Over the
13 captures: taught / refused by reason against try 1's (10,560 taught; refused 5,249 overlap, 2,270 fill, 1,423 no
track, 125 two sightings). Step 3's rows identical to t5a; the ms row as in try 1 (accepted 0.101, the whole frame
+0.00); the bot speed line. Numbers into the plan under "Step 5a, try 2"; a gate missed: stop.
Then, REPORT ONLY (no gate, nothing in maplebrain/ changed for it; the user's answer 4 under "Step 5a, 2026-11-26"):
does a ranged class change the meter? One assassin capture, 2026-11-26_2008_assassin_farming_idle_7m35s_s00 (Ant
Tunnel IV), its keys from the user: space = Lucky Seven (the attack), shift jump, z loot, 1 Haste, 2 Claw Booster,
Del / End / Home potions - passed to the tools as an argument, not into config.Keys (step 6's profile). Its dropped
frames first (video.json / frames.jsonl). A new kept replay of it (dump.py; the GPU) in its own folder (stop rule 5),
then the meter reader + the tracker with try 2's tie (replay_meters.py read / replay_mobs.py run --meters on it).
Report: the place rule on it (meters tied to exactly one seen mob, the share against the 13 captures' 90.1 %); a
picture sheet of 30 random meters + every meter cut by the screen's side, judged by eye (found, right mob, fill);
the delay from a space key-down to a NEW meter against the distance from us to the mob (does the star's flight
widen try 1's window MWIN 0.20-0.80?); any new meter with no space key-down in a window (look at each: stop rule as
in try 1 - a meter on a mob we did not hit breaks step 5's witness); meters under the buff effects (1, 2); Ant
Tunnel's scenery read as Zombie Mushroom carrying a meter (should be never). Each number beside the same map's
spearman capture, 20261118_232410_1#3 (Ant Tunnel IV, kept replay exists): range against the map. The whole 7.6
minutes (the user, 2026-11-27). When try 2's gate is met: step 5a DONE
in the status lines, the steps table and HANDOFF.md (the handoff skill), the assassin's report beside it.
```
```text
Tracker, step 5a, close (the guard goes) + the meters at overlaps, measured. Read PLAN-tracker.md - design 1 (relaxed
by the user 2026-11-27), "Step 5a, try 2" and the user's answers under it, measurement 1, the stop rules - and
maplebrain/track/mobs.py `_meters` / `_overlapped`, tools/perc/track/replay_meters.py, replay_mobs.py, proto_mobs.py
(the fair counts), oracle.py. Branch tracker-build (the main folder). No GPU needed.
PART 1, build: the tie's guard against unseen tracks goes - a meter whose candidate is one seen sighting, its fill
read, teaches that sighting's track. Still refused: a meter naming two sightings, an unread fill, no track. Keep
"an unseen mob could be under it" as a COUNTED stat (not a refusal), for step 5. Tests: the remembered-overlap case now
taught and counted (fails without the change); the two-sightings case still refused. Run replay_mobs.py run --sound
--meters --tag t5a3, replay_meters.py l9 --tag t5a3, replay_mobs.py pool + feet + labels, the whole pytest.
Gate: L9's meters whose fill was read: tied to the right mob >= 99 % (try 2: 61 of 83; the 22 refused all right by
eye), wrong 0 (one wrong: stop with the case and its picture); over the 13 captures taught / refused against try 2's
(12,795; 3,014 unseen, 2,270 fill, 1,423 no track, 125 two sightings); step 3's rows identical to t5a2; the bot speed
line. Met: step 5a DONE in the status lines and the steps table.
PART 2, REPORT ONLY (nothing built; the user's idea "could we use the meters to help when mobs overlap?"), on the
t5a3 rows of the 13 captures against the truth's fair counts:
 a. ids: of step 3's id errors (an id changed across a cover, a life split in two ids, "the track changed mob", the
    two-of-a-kind swaps at crossings), how many had a meter on at least one of the mobs involved within the error's
    time, and in how many the meters alone (one has one and the other not, or the fills differ by more than 3
    points) would have told the two apart - by kind of error and by capture;
 b. hidden hit mobs: meter-frames with no seen sighting under the meter (try 1's "no track" / "the mob not seen" 6.9 %)
    where a remembered track of that kind can be there: how often, how long, and how far the meter's place (x = the
    box's centre, the body's top = the box's top + 30) is from where the track later reappears, against the
    tracker's own possible range;
 c. deaths while two mobs overlap: the death the tracker put against the mob whose meter went at the killing hit -
    agree / differ, each difference looked at.
A picture sheet of the cases in a-c where the meter would have decided (up to 30). Numbers under "Step 5a, close";
the user decides whether a build step comes before step 5. End with the handoff skill.
```
```text
Tracker, step 5 (events, with the HP meter). Needs steps 3-4, 5a and step 1's labels L4. Read PLAN-tracker.md -
measurement 6, design 1 and 8, "Step 5a", step 5's row, the stop rules - docs/state_model.md section 4,
tools/perc/track/proto_events.py (the reference: re-run it on the tracker's own tracks first and compare with
measurement 6; a difference: report it). Branch tracker-build (the main folder). The user's answers (2026-11-26),
write them under step 5 first: question 8 = (a) - EXP is out of the live rule and is the offline grader on solo
captures; solo only, parties later ("in party exp comes from all sources and it will be more complicated to
track"); a death's credit is ours / shared / theirs / unknown plus our share of the HP the meter saw lost (in our
hit windows against outside them), not "our last hit" (EXP is shared by damage, docs/game_rules.md G) - change
.claude/rules/perception.md's "Kills are counted by our last hit" to match.
Build track/events.py on the tracker's own tracks: cast (a skill key-down with no swing running, confirmed by the MP
step); mob_hit by us (the meter appearing, or its green share falling, in our hit window; the hit pose in our
window and reach as a second witness) and by another (on a mob we hit: the green share falling outside our windows;
a first reading lower than our own first hit leaves on that kind (measured on solo, full-HP cases) = hit by another
before us; on a mob with no meter: a hit pose with no hit of ours - step 5a's clarifications); mob_died
(the die pose under the fade rule, the meter going with it) with its credit and damage share; every HUD step's
cause; drop and player events from 4a / 4b. Checks: corpse tracks (a dead body read as a live pose) give no second
death or new mob; hits and deaths while two mobs overlap (design 1), reported. Gate: step 5's row; step 3's rows
unchanged; pytest + the bot speed line. Numbers into the plan under "Step 5"; a gate missed: stop.
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
pytest, the bench, step 3's carry-over 3 (the whole frame's p50 not above today's + 0.3 ms, world.py gone), then
ask the user for the 3-minute hunt on Line 1. Numbers into the plan; a gate missed: stop.
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
tools\perc\track\replay_mobs.py run --sound --jobs 4; ... pool --sound        # step 3: the real tracker, the gate
tools\perc\track\replay_mobs.py feet --sound; ... labels [--tag proto]        # step 3: measurement 3's feet; L1-L3, L8
tools\perc\track\dump.py CAP --out NAME; replay_mobs.py live CAP --kept NAME  # step 3: a new kept replay, the live path
tools\perc\track\replay_mobs.py time CAP                                      # step 3: the ms, shadow on / off
tools\perc\track\replay_players.py run --sound --jobs 4; ... run CAP --port; ... port CAP   # step 4b: the real code; the port
tools\perc\track\replay_players.py l5 [--final] [--port]; ... cover; ... us; ... ms; ... time CAP   # step 4b: the gate
tools\perc\track\replay_mobs.py run --sound --meters --tag t5a3; tools\perc\track\replay_meters.py l9 --tag t5a3   # step 5a: the tie
tools\perc\track\meter_overlaps.py all|ties [--tag t5a3]       # step 5a, close: the meters at overlaps (a-c), the readings the guard refused
```
Outputs, sheets and reports: `F:\dev\maple-corpus\work\track-plan\` (`mobs\`, `drops\`, `events\`, `players\`, `slots\`).
