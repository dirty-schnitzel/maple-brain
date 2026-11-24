# PLAN-tracker: the tracker that fills the state model

**Status: DRAFT - the plan session is still running (2026-11-23, `docs/prompts/tracker-plan.md`, Part 2). Not yet
PROPOSED: the experiments are being measured, the steps and prompts are not written. "Session state" at the end
says what is done, what is running and what is left - it is removed when the plan is PROPOSED.**
The model this tracker fills: `docs/state_model.md` (OK'd by the user 2026-11-23). Nothing is built in `maplebrain/`.

## In short (so far)
- **Today's tracker (`perception/world.py`) covers a small part of the model**: mobs only, by timeouts. No drops,
  no other players, no events, no "where it can be" while unseen, no facts, no hotkey reader; its placement is
  "within 16 px of a surface".
- **A prototype of the mob part runs from the kept replay (no GPU) and beats today's tracker on every identity
  number** (13 sound captures, 1,774 mob lives - the table under "What was measured" 1). Its three ideas: a track
  that is not seen keeps the set of places it can be, and loses every place where the frame shows the scenery
  (no timeouts on what can be checked); a new track is not a mob until it was once seen clearly; the mob's
  facing and its real speed are used when sightings are paired with tracks.
- **Found on the way:** (1) **every mob kind moves at twice the speed the v83 rule gives** (8 kinds, 1.97-1.99 x:
  a Bubbling walks 137 px/s, the rule says 68.75); (2) the fit makes **false sightings from slivers at the screen
  edge** (a player's helmet, a player in a portal) - a tracker with memory must not remember those; (3) a jump's
  feet are settled exactly by two rules (never under its own floor; the reading that continues its motion) -
  a hop then is a parabola within 1 px; (4) the bottom two rows of the play area (y 698-699) are the HUD's edge
  and are not masked.

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
  (being run on all 13 captures: `...\mobs\run_v5_abs60.txt`); the tentative stage costs 1.2 points of found and
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

### 5. Always drawn over the world and not masked (`static_overlay.py`, the 4-minute Line 1 capture)
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
widths already known; kept through a 1 s cover in view; placed by rule 3. Pets are sorted out, not tracked.

**7. Us:** the feet from our tag (taken from the tag list when the reader's own tag is missing: 1,179 frames),
placed by rule 3 with the rope; `facing` = the last left / right key; `act` from the place, the keys and the MP
step; the HUD's numbers; the 8 slots from the hotkey reader (measurement 8); buffs and cooldowns = a cast seen +
the skill's length / cooldown from the client files (Rush's 2 s: 12 presses inside it did nothing).

**8. Events** (measurement 6): a cast = a skill key's key-down with no swing running, confirmed by the MP step;
`mob_hit` / `mob_died` by us = the pose begins in that cast's landing window with the mob in the skill's box, a
death also when it is the only one an EXP step of the mob's full EXP can pay for; every HUD step gets its cause;
drop and player events from 5 and 6; a mob's own name tag as a second witness of our hit.

**9. Facts and dynamic values** (state_model.md 5-6): one registry; the profile file (keys -> skills and
levels, the weapon); Skill.img built into `assets/mcw`; measured live: our walk / jump / climb, the swing length
(the gap between casts: 0.85-0.87 s), what a potion gives, hits per kill, each mob kind's speed against the
files' (the factor 2.0 lives here, with its source).

**10. Stored:** the tables of state_model.md 8, written by the recorder and the hunt, readable with a field
added later.

---

## Session state (2026-11-23; removed when the plan is PROPOSED)
**Done:** the user's OK on `docs/state_model.md` registered (dev 7bd0d45). The truth kept on disk for the 13 sound
captures (`cache.py`). The mob prototype through four versions (`proto_mobs.py`), `births.py`, `proto_feet.py`,
`static_overlay.py`, `crops.py` (crops around a map place for a look by eye), `ablate.py`.
**Stopped here 2026-11-23 ~22:30 (usage limit).** Nothing of this session's Part 2 is committed yet: the new
tools in `tools/perc/track/` and this file are in the working folder (branch `tracker-plan`).
**Version 5 of the prototype, the 30-minute design capture (today in brackets):** found 98.9 % (96.8); id kept
across a cover, fair count, 94.6 % (80.2) - 0-0.1 s 97.3 (94.1), 0.1-0.3 s 96.6 (88.6), 0.3-0.6 s 95.2 (76.1),
0.6-1.5 s 86.0 (40.0), 1.5-4 s 83.0 (27.5); one id for life 73.2 % (66.8), not counting a change beside another
mob of its kind 91.2 % (84.3); extra ids 702 (1,307); a mob seen again was next to its possible set 99.87 % of
1,595 times; 0 of 408,563 seen track-frames without a truth mob; 95 tracks ended by the 4 s "drawn over" limit,
21 by "its places show the scene". Python cost on the 4-minute capture: 2.2 ms a frame p50 (pairing 0.44, the
check of unseen tracks 0.73, replay decoding 0.75 - not a live cost).
**Running in the background when this was written (plain processes, their output lands in files):** version 5 on
all 13 captures with today beside it -> `F:\dev\maple-corpus\work\track-plan\mobs\run_v5_sound.txt` (its POOLED
blocks are measurement 1's final table; it also prints "by what was over it when it ended"); the
one-setting-at-a-time table on version 5 -> `...\mobs\ablate_v5_short.txt` (version 4's: `ablate_short.txt`).
**Four sub-agents were still working** (their tools exist, their reports had not arrived): the hotkey reader
(`proto_slots.py`, sheets in `...\track-plan\slots\`), the drops tracker (`proto_drops.py`, `...\drops\`), hits /
kills / casts (`proto_events.py`, `...\events\`), other players from name tags (`proto_players.py`,
`...\players\`). If a report is lost, re-run the tool (its docstring) and read its sheets.
**Decisions reached, to carry into the design:** the possible set + one 4 s limit for whatever cannot be checked
(out of view, behind the UI, drawn over) - this narrows state_model.md's memory rule 1, a question for the user;
tentative until seen clearly once (>= 25 % of the full size, >= 30 % of the body on screen) or sighted 0.5 s;
look-alike feet by "never under its floor (unless every reading is)" + "the reading that continues its motion";
standing = within 3 px of a surface and the step within 1 px (+ 0.9 x the sideways step); mob speed = the files'
x 2.0 (a measured fact; a note for `docs/game_rules.md` C1, a question for the user); the tracker's code takes
its frame evidence through one interface with two sources (the kept replay's bitmaps, the GPU's tensors) so the
real code is graded on the kept replay with no re-make; gates use the fair id count, and at crossings the count
of "the track changed mob" (0 of 53 on the 4-minute capture; the truth changed mob in 31).
**Left:** read the two output files and the four reports into "What was measured" (5 drops, 6 events, 7 players,
8 slots, 9 cost); a by-eye sheet of version 5's remembered tracks (`mem_sheet.py`, the cave captures too:
their remembered frames without a truth mob were 6 % in version 4); then write the design, the steps in line
with gates, stop rules, the Opus prompts, the parallel marks (drafted order: label sets by eye; the graph and
placement; the mob tracker in shadow; drops, players, us; events; facts registry + profile + Skill.img; the
hotkey reader; the stored tables; the switch-over), footage and questions for the user; commit (tools on
`tracker-plan`, this file on `dev`); the `handoff` skill. `PLAN-moving-scenery.md` is not valid UTF-8 (the Read
tool said so) - tell the user.
