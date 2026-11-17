# maplebrain — session handoff (updated 2026-11-16)
**Read this file top to bottom; it holds only the current state.** NEXT SESSION = "START HERE NEXT SESSION" below:
brain v3 (**PLAN-v3.md**) steps 1-3 are DONE and **Platform mode passed its live test** (2026-11-15, Ant Tunnel IV;
the user: "perfect platform mode test"). NOW = the perception redesign (**PLAN-perception.md**, agreed 2026-11-16,
branch `perception`): steps 0-1 DONE, **step 2 (pipeline) in progress - see "Step 2 state" below** (sub-steps
2.1-2.9 committed: the scene camera is the camera on clean maps, own tag 1:1 + its whole-screen look on the GPU,
Lie Detector native templates + GPU look + watch 1 / s, HUD cache + CPU readers in threads: bench 18.4 ms, step 2's
gate met, live-checked; NOW = step 3, order agreed, see "START HERE NEXT SESSION"); open offer: the
humanness report (below).
Sessions 6-23, the old brain (v1), and superseded plans moved verbatim to **HISTORY.md** on 2026-11-08: grep it for
old runs, numbers and decisions.
Latest: 2026-11-15 Platform mode live (runs below), F9 mark fix; the hybrid BT + imitation-learning proposal reviewed
and declined (below); VM work parked on `vnc-keys`. 2026-11-09 edge ghosts fixed + live-checked (`runs/v2/air1/fix3`), package renamed maplebot -> maplebrain;
`main` = `dev` = 5998a33, pushed. 2026-11-08 attack per press built + live (`runs/v2/press1`; the user: "the most significant change in bot
behavior since start"), speed regression test, brain v3 planned; 2026-11-07 map recognition measures the minimap
window; 2026-11-05 M2 combat live, brain v2 split into parts; M1 movement done.

## Edge ghosts at Ant Tunnel IV's right wall (2026-11-09, DONE: fix e68066e on main + dev; live-checked `runs/v2/air1/fix3`)
**Seen:** `runs/v2/20261109_003124_1` (no frames) 362-382 s: 17 presses + "kill #56" at a "Zombie Mushroom" that isn't
there; `runs/v2/20261109_011503_1` (frames) 56.5-63 s the same ("stuck on the side of the map"). Both: camera at the
map's right wall (vrBounds right 2610 = the screen's right edge), track feet at screen x 1366-1376, y ~468, score
0.57-0.68. Pictures of the third case are in `runs/v2/air1/20261109_014902_1` (ghost_vision.gif / ghost_play.gif /
ghost_live_50.0.png: make_images.py functions, crop 486..1366 x 110..605).
**Cause:** born from the search around a DYING mob at the wall (78 -> 89, 509 -> 512 -> 546 -> 547): a live pose there
became a new track at the follow bar (0.55), past `--mob-score`; tentative -> live on 2 sightings. The visible-only
search compares half a mushroom (37-48 % of its body on screen) with lit stalagmites. (The whole-screen search pads the
frame's right / bottom edge with copies of the last column, too.) `--mob-score 0.70` would NOT have stopped it.
**Third case (live test `runs/v2/air1/20261109_014902_1`, the fix (1)+(2) on):** a REAL mob (track 72, 0.98) walked
to the wall at 46.6 s; at 47.0 its near search matched the wall spot (0.57-0.64) and the track stayed there 17 s
(swings, "stuck"). GIFs + still in that run folder (ghost_vision.gif / ghost_play.gif, 44-60 s).
**Fix (world.py):** (1) a live pose on a dying mob's spot needs `probe_score` (= the mob score), like any new mob;
(2) `new_onscreen` 0.6: a new track needs 60 % of its body box inside the play area (stat `rejected_edge`);
(3) `edge_score` 0.70: ANY sighting (whole-screen or near, known tracks too) with < 60 % of the body on screen counts
only at >= 0.70 (`_weak_edge`). Such sightings in 6 Ant Tunnel runs: ghosts p50 0.62, max 0.68 (0 of 1685 pass);
real mobs 80 % pass, the rest are unseen frames (coasting). Separate from `--mob-score` (still 0.65).
Tests: tests/test_world.py (3), tests/test_world_edge.py (real frames, tests/fixtures/edge_ghost, 4 frames). All green;
bot speed 58.6 ms vs baseline 59.6.
**Replay, old vs new world.py** (live Perceiver on the recorded frames, mob score 0.65; ~6 fps vs 28 live):
011503_1 -6 weak (the ghost too), real 89 -> 89; air1 real 87 -> 87, the real mob's track follows it to its death
(52.1 s) and never sits at the wall (old: 178 frames there); 191848_2 -10 weak, real 103 -> 103; press1 -12 weak,
real 167 -> 163; react1 -6 weak, real 187 -> 186. The real ones lost / later: at the screen edges 460-750 px away or
250-430 px above / below us (never targeted), 2 picked up 0.3-0.5 s later at the edge, and ONE near us (press1
174.5 s): a Horny Mushroom walking in behind a dying one, only seen at 0.575 there, then an off-platform hit: watch
for "late on a mob that steps in where one died" live.
**Live check `runs/v2/air1/fix3`** (2.4 min hunting, mob score 0.65, camera at the right wall 85 % of the time): no
ghost at the wall, every counted sighting < 60 % on screen >= 0.705; the user: "the edge ghost seems resolved". 74
presses: solid 51 (69 %, was 61 % in 003124_1), stale 16, nothing 7. `--mob-score` stays 0.65 (the user may test 0.70).
The remaining air presses -> P2 accuracy, A2 / A4 / A6 below.

## Goal
A **fully automated mob farmer** for **MapleStory Classic World** (official GMS Classic, launched 2026-10-21):
find mobs, fight them like a player, pick up loot, use potions, and **navigate platforms (jump up / drop down,
later ropes/ladders)**. Vision-only: reads the screen, sends key presses; never reads memory or packets.
The user supervises every run at the PC. Botting is against Nexon's ToS (ban risk); the user accepted it.

## START HERE NEXT SESSION: step 3 (the mob matcher), order AGREED 2026-11-16 - see "Step 3 state" below
Step 2 is done and live-checked (below). Step 3's order is in PLAN-perception.md ("Step 3") and "Step 3 state"
(after "Step 2 state"): 3.0a labels -> 3.0b synthetic frames -> 3.1 D in shadow -> 3.2 the fit -> 3.3 FrameFacts v2
in shadow -> 3.4 the switch on clean maps. **3.0a + 3.0b DONE (labels, synthetic frames, "before" numbers on both in
"Step 3 state"); 3.1 (D in shadow) DONE too; 3.2 (the fit) IN PROGRESS: accurate but 12-40x too slow (62 / 116 /
200 ms). 2026-11-17: the speed problem was reviewed and a new search PROPOSED - PLAN-fit-speed.md (exact-colour
voting replaces the least-squares stage 1; prototype tools/perc/redesign/exp_vote.py: candidates in ~2 ms, synth
opaque cases 100 %, labels 94.3 %). OK'd by the user 2026-11-17. Session 1 (S1-S3) DONE 2026-11-17: vote + fit on
votes in maplebrain/ (fit 2.6 / 3.2 ms p50 / p90 on the labels frames, was 119 / 160); every gate met but the labels
one AS WRITTEN (its classes hold fading mobs, S4's); the user ACCEPTED it on the not-fading subset 2026-11-17 (full
classes = S4 / S5's gate). Session 2 S4 (fades) DONE 2026-11-17 and accepted by the user (per-cell alphas, the
1 / o tolerance, fade pass ~1.7 ms p50 kept) - see "3.2 Session 2" in "Step 3 state". S5 (tints) DONE 2026-11-17,
every gate met ("3.2 Session 2, S5"). S6: flyer layers fixed, tracks gate met on all 6 clips, fit p90 5.13-5.47
ms on 4 clips ACCEPTED by the user (option A = fade-pass CUDA graphs noted for later) -> **3.2 CLOSED 2026-11-17.
NEXT = 3.3 (the fit in shadow in the Perceiver): PROPOSED in "Step 3 state" ("3.3 PROPOSED"), the user's OK first.** `watch` was NOT running on 2026-11-17 (no python process): the user's to
restart; never stop it.

### TASK (the user, 2026-11-16): improve the gate test by taking NEW footage
The tests on pre-native footage were deleted (d87e5b4; the Lie Detector ones kept); for now the gate = today's
native clips (tools/perc/replay/gate.py) + the lossless perf fixture. The user can record more. Proposed set
(each ~1-2 min, the user playing, `serve runs\play --observe --gpu --tracker --frames-png`, native window, current
code so ticks.jsonl carries the FrameFacts + scene camera as the "before"):
| # | Map | What to do | Tests |
|---|---|---|---|
| 1 | Ant Tunnel IV | fight hard in a dense spot, pet out | effects over mobs, deaths, fade-ins, speech bubbles; a future bench fixture |
| 2 | Dangerous Steam | walk the whole map, then fight | the ghost gate (83 of its 85 weak tracks were scenery ghosts of one type) |
| 3 | The Rain-Forest East of Henesys (10001070, clean) | hunt Pigs near the grass | mobs behind front scenery |
| 4 | Line 1 <Area 1> | stay near spawns | see-through Bubblings, spawn fade-in |
| 5 | any clean map, busy channel | fight among other players | players / skills / tags over mobs |
| 6 | Dark Cave | fight the flyers, don't move the window | the old clip is cut at 16 s by a window drag |
Reuse: Transfer Area (animated objects); Perion Street Corner at native as the FALLBACK clip instead of fix3 (FHD).
Then: clips into gate.CLIPS, ~40-50 picked frames per clip for labels (pick.py), native unit tests for the HUD /
quickslots / own tag / map id (their old tests are gone: those readers have no tests until then), a real
Lie Detector at native when one comes (watch's PNG). Any clean map works if one isn't practical: 110 maps have a
clean scene (`Scene.clean_meta`).

## Earlier START HERE (after 2026-11-16 night): step 2 DONE (2.9 committed) -> one live check, then step 3
**2.9 DONE (see "DONE 2.9" in "Step 2 state"): bench p50 22.0 -> 18.4 ms, p90 25.7 -> 21.1 (gate 20 / 25 met),
re-baselined; full replay gate: the same tracks on all 7 clips.** Cut by the user to what survives step 3 (HUD
cache + CPU readers in threads); the FFT whole-screen search and a faster `find_near` were DROPPED - step 3
replaces both (rule: memory no-work-step3-replaces).
- **Remind the user: `watch` is OFF - restart it** (`... -m maplebrain watch runs\watch --seconds 14400`: now 1 look
  / s on the CPU by default; `--gpu` exists, but the bench showed no gain from it - see the numbers).
- **DONE: the live check of 2.8 + 2.9** (`runs/play/20261116_193954_1`, Ant Tunnel IV, 132 s, 6889 ticks, serve
  --observe --gpu --tracker, watch running; the user played): **tick p50 19.0 / p90 22.0 / p99 33.4 ms, 52.3 fps**
  (154819_1: 28 / 31 / 54, 34.5 fps). Parts p50: gpu 11.3, world 4.0, scenecam 0.7, upload 0.3, hud 0.1; self /
  scene / grey 0 (hidden); `lie` 3.0 ms p50 (max 5.8) on its 423 look ticks (1 in ~16); self_wide 4.1 ms on 36
  ticks (was 28); locate 2.3 p50 on 434 ticks (1 / s), max 21. HP / MP / EXP read on 100 % of ticks, 62 distinct HP
  readings, EXP never decreasing, max HP / MP constant (1659 / 670), slots read on 100 %; tag 95.7 %; Lie Detector
  best score 0.508 (none on screen). Scene camera on every tick after the first tag (ticks 0-58 = the first 1.4 s,
  no seed until our tag was found), share p50 0.92.
- **NEXT: step 3 (the mob matcher)** - order to agree with the user first; inputs measured for it in "DONE 2.9"
  (the near search's cost by window size).
- The bar back to 0.80? The user's word only. Facts for it: the gold title's best false score on 8641 native frames
  0.496, the sound title 0.434, blue title 0.565, "Question in" 0.522 -> the set's 0.565; the client's own windows
  pasted at native >= 0.970. Old stretched JPEG fixture panel: 0.79 (a non-native window would sit near 0.80).
- Any real Lie Detector at native: its PNG from watch -> check the gold title's score (expected ~0.97+) and cut the
  blue title / "Question in" (font text, no client picture) 1:1 from it.

Read PLAN-perception.md (step 3 row) and "Step 2 state". Branch `perception`, all pushed.
Rules unchanged: agree changes with the user, pytest + the speed line
(baseline 18.4 ms, re-baselined 2026-11-16 at 2.9; BENCH ONLY WITH THE GAME RUNNING - the GPU idles at P3/P5 without
it and everything reads 40 % slow) + `python tools/perc/replay/gate.py --quick` per sub-step, the full gate before a
commit that changes tracking; no live / scripted input without the user's OK; never stop `maplebrain watch`
(**it is OFF since 2026-11-16 for the 2.8 measurements - the user stopped it: restart it or ask**); never optimize
code a later step replaces. The 300 picked frames for by-eye labels are still unlabelled.

## Earlier START HERE (2026-11-16): the perception redesign, PLAN-perception.md step 0
**Read PLAN-perception.md top to bottom** (the scene model: explain the frame with the client's own assets; the
experiments E0-E6 behind it are in tools/perc/redesign/, README there). The user agreed the direction on 2026-11-16:
target **60 fps cap, ~100 % accuracy**, game window at **native 1366x768, windowed, no resize**. Branch
`perception` (off dev a8b9487; 1709ddf = the proposal + experiments).
- **PLAN-perception.md REPLACES ROADMAP phase 1a and 1b below**: S1-S3 (threads, GPU self-tag / camshift / resize,
  slow HUD) = its step 2 (pipeline), S4 = steps 4 / 6; A1 / A3 / A5 / A6 = step 5, A2 / A4 = steps 3-4 (the fit +
  3-valued evidence). "TODO: game window at native 1366x768" below = its step 0. Phases 2-5 of the ROADMAP stand
  (FrameFacts = phase 2's perception record).
- **Bench baseline re-written on purpose 2026-11-16: tick 32.7 ms (p90 51.5), 30.6 fps** = resize 0.0 + perceive
  32.6 [gpu 10.7, world 6.4, hud 6.0, self 2.7, locate 2.4, camshift 2.0, scene 1.2]. Was 59.6 ms (2026-11-08): the
  Windows power plan is *Ultimate Performance* since ~11-13, every CPU part runs ~2x faster (check
  `powercfg /getactivescheme` before judging speed), and the bench no longer resizes (`SCREEN` = 1366x768, -1.8 ms).
  Repeats spread 32.7-37 ms. Re-baselined again the same day on the NATIVE fixture: 30.0 ms (step 0 state below).
- Every step: pytest green + the bot speed line + tracker replay (tools/perc/replay) same or better; the order of
  code changes is agreed with the user first; no live / scripted input without their OK.
- **Step 0 state (2026-11-16):**
  - DONE `tools/perc/replay/` (README there): `run.py RUN [--old REF [--only files]]` = the live Perceiver
    (`bench.build`) over a run's saved frames, the old code served from git by an import hook (nothing checked out);
    `compare.py RUN A B | --live B`. Proven on press1 + air1/fix3: same code twice and working tree vs `--old HEAD`
    = the same tracks on 100 % of the frames, but NOT to the digit (GPU run-to-run noise: scores <= 0.005, a
    position 1 px about once in 5000 track-frames) -> every "replay identical" gate means compare.py's "the same
    tracks"; press1 at 0.65 gives 163 real tracks = the 2026-11-09 replay's number; vs the live tracks on the same
    frames 89-90 % of real track-frames either way (the replay sees every 3rd tick). ~55 s per run.
  - DONE native-window readiness: `capture.normalize` returns a 1366x768 picture untouched; the run log says
    `game picture at x (0, 1366), 1366x768 native (no resize)` or `... WxH -> resized to 1366x768`; bench SCREEN.
    Nothing else assumed a larger window (world / hud / cover / camshift work in normalized coordinates;
    `localize.py`'s sub-pixel canvas offset should read ~0 at native: check on the recording).
  - DONE `--frames-png` (serve / run): lossless frames. **JPEG 92 leaves only 22 % of exactly drawn sprite pixels
    within +-4 levels** (q100: 40 %; +-16: 87 %), so the 1:1 gate and every colour-exact experiment need PNG
    (~1.1 MB, ~40 ms writer thread per frame; 5 min ~3.3 GB). E1's "61-66 % within +-16" was partly JPEG.
  - DONE `tools/perc/native_check.py RUN [--sheet N]`: clear mobs vs their client sprite, share of opaque pixels
    within +-4 / 8 / 16, colour shift, per mob; prints the gate. Before-number (press1, FHD + JPEG): 12 % / 33 % /
    59 %, 155 clear mobs.
  - The game window IS at native already (checked read-only 2026-11-16: client area 1366x768 at (8, 32), display
    scale 100 %, monitor 3440x1440).
  - **DONE: the native reference recording `runs/play/20261116_012059_1`** (the user playing, Ant Tunnel IV, 342 s,
    11,576 ticks = 33.8 fps, tick p50 29 ms / p90 32, 3858 PNG frames, 3.1 GB, keys.jsonl). **The picture IS 1:1:**
    - mobs (`native_check.py`, 300 frames, 445 clear mobs): per-mob median 100.0 % of sprite pixels within +-4,
      325 mobs exact to 100 %, detector score median 1.000, never 1 px off, no colour shift. Pooled 90.2 % because
      pixels are either exact or NOT the sprite (+-4 = 90.2 %, +-16 = 91.7 %): the 329 mobs with score >= 0.9995
      pool 99.7 %; the rest are half-transparent (spawn fade-in / death fade: NCC still 0.99, 15 % of pixels exact)
      or under a translucent effect. Gate >= 95 % on opaque uncovered mobs: PASS. Tolerances can be +-4.
    - scenery (`exp_render.py check`): registers at scale 1 (score 0.92; FHD 0.88) = the same view of the map as
      FHD; 91.8 % of the rendered tile / object pixels are within +-4 of the frame (within 30: 92.6 %: exact or
      covered here too).
    - today's tracker on it: sighted live scores p50 1.00 (FHD observe run 0.90), weak sightings < 0.7: 7 % (28 %);
      replay: 471 real + 11 weak tracks (live: 26 weak).
  - **Found at native (constants and templates measured on stretched windows):**
    - FIXED: the HUD's EXP text sits 1 px left -> `exp_points` read 0 of 11,576 ticks; it now tries both places
      (193 of 193 frames, 14 by-eye checked in tests/fixtures/exp_points_native.npz). HP / MP read 100 %.
      (CAUSE found later that day: not the HUD - THIS RECORDING was captured 1 px off, see "Step 1 on 7 maps".
      The reader stays tolerant; the perf fixture and exp_points_native.npz are from the shifted recording.)
    - OPEN: `assets/self_tag_gray.npy` is a resampled-look template: tag score p50 0.864 at native (found 91.7 % of
      ticks; a 1:1 template would be ~1.0) -> re-cut it from the PNG run (step 2 at the latest).
    - **OPEN, safety: the Lie Detector templates are resampled-look too.** Estimate (HUD text through the old
      stretch + shrink, matched on native pixels): -4..5 % score -> the announcement panel 0.89-0.90 would read
      ~0.85 at native (bar 0.80; best false score on native frames 0.65). Not verifiable without an LD at native:
      the user decides whether `LieDetector.min_score` goes 0.80 -> 0.75 until native templates exist (watch needs
      a restart then: the user's).
      **DECIDED 2026-11-16 (the user): the bar is 0.75** (`LieDetector.__init__`). Best false score on all 3609
      native frames of the 6 new recordings: 0.668 (the panel template, 0.644-0.668 per map). A running `watch`
      keeps 0.80 until the user restarts it.
    - OPEN: the tracker's camera reads +6 px x / +3 px y (p50) off the scenery registration at native (FHD: 0 / +1):
      probably the minimap's sub-pixel handling in `localize.py`. Step 1's registration replaces it; until then
      platform edges are ~6 px off.
  - DONE new perf fixture (tests/fixtures/perf_ant4 = 45 frames of the native run, a fight, t 51.1-54.9 s, JPEG q85,
    SOURCE.txt) + baseline on purpose: **tick 30.0 ms (p90 31.4), 33.3 fps** [gpu 11.1, world 7.5, self 2.8, hud 2.6,
    camshift 2.5, locate 1.5, scene 1.3] (serve --observe + watch were running idle; repeats 29.8-31.5).
  - DONE picked for by-eye labels: `tools/perc/labels/20261116_012059_1_pick.json` (300 frames: 150 even + 150 hard:
    swings near mobs, unseen near us, weak, dying, edge, tentative, rope; `labels/pick.py`). **NOT labelled yet**
    (labels -> RUN/labels.json + a copy in tools/perc/labels/, label_eval.py).
  - Replay noise on the long native run: same code twice differs on 2-5 of 18,170 real track-frames -> the gate is
    "track-frames found >= 99.9 % both ways" (replay README).
- **Step 1 state (2026-11-16): the scene model works on Ant Tunnel IV; Line 1 + Perion need native recordings.**
  - `tools/cwdata/export.ps1` now also exports Map/Back (36 sets, 789 pictures), Npc (233), Pet (35), Effect/BasicEff
    (510 pictures); pixel format 1537 (flat 16x16 colour blocks, e.g. Perion's sky) is decoded in the script.
  - **The backgrounds are exact** (E7, tools/perc/redesign/exp_back.py): the picture's origin is drawn at
    `b + off + trunc(r * (C + off) / 100)`, off = 682 (x) / 468 (y), integer division toward zero, tiled every
    cx / cy; all 65 layer positions fitted on 13 frames match. Backs are 4-bit dithered pictures: 1 px off = half
    the pixels wrong, so nothing but the exact arithmetic works.
  - `maplebrain/scene.py`: `python -m maplebrain assets scene [MAP ...]` -> `assets/scene/<map>/` (NOT in git; all
    206 maps with mobs: 95 s, 310 MB; 95 have moving / animated backs = unknown pixels, 76 animated objects);
    `Scene.load(map)`, `expected(C)` = the picture where nothing moves + which pixels are known,
    `locate(frame, last_C, seed=minimap camera)` = the camera from ~800 tile / object edge landmarks on the GPU
    (a wrong offset matches ~2 % of them, the right one 44-95 %; under 20 % = not found, never a guess).
  - **Measured on the native recording** (`tools/perc/scene_check.py RUN`, 120 frames; pictures with the platforms
    drawn + what is left after subtraction in RUN/scene_check/):
    - camera found on 120 / 120 and it is the best of the 25 cameras within 2 px by whole-picture count on all 120;
      followed through all 3858 saved frames (every 3rd tick) without a loss, 1.7 ms p50 (wide look 32 ms on 8 %:
      camera steps up to 35 / 77 px between SAVED frames; live ticks are 3x closer).
    - explained within +-4: whole play area p50 95.1 %; what is left = mobs, players, pets, tags, damage numbers,
      drops, effects, the cursor, chat, game windows. Outside those blobs the scene explains 99.82 % (p5 99.55 %):
      gate >= 98 % PASS. Register + expected + compare 3.0 ms on the GPU.
    - **today's tracker camera is off by +5 px x / +3.5 px y at the median, > 8 px on 39 % of frames, max 41 px.**
  - Line 1 (old FHD JPEG run, tolerance 30): registers 60 / 60, the 29 background layers sit right (picture in
    runs/play/20261105_000802_1/scene_check/), exact numbers need a native PNG recording; Perion: no frames at all.
  - **NEXT:** the user records 1-2 min native PNG on Line 1 <Area 1> and on Perion (the fog) -> scene_check there
    (step 1's remaining gates); then step 2 (pipeline: FrameFacts, one upload, the scene camera replaces camshift /
    phase correlation / the per-tick minimap; watch at 1 look / s + Lie Detector on the GPU). The 300 picked frames
    are still to label (now with the subtraction picture to check by).
- **Step 1 on 7 maps (2026-11-16, later): the user recorded 6 more native PNG runs** - runs/play/20261116_
  084719_1 Dark Cave (77 s), 084844_2 Dangerous Steam (94 s), 085108_3 Line 1 <Area 1> (56 s), 085215_4 Transfer
  Area (40 s), 085414_5 Perion Street Corner (64 s), 085620_6 Land of Wild Boar (74 s); with Ant Tunnel IV = 7 maps.
  - **FIXED capture bug: `capture.game_columns` cropped (1, 1367) when the game's left edge column was dark** (the
    native window has no bars to measure; now the whole width is taken unmeasured). Ant Tunnel IV (012059_1) and
    Dangerous Steam (084844_2) were recorded 1 px LEFT of their place, the last column from outside the window.
    Those two runs carry `xshift.txt` = 1; `tools/perc/frames.py` (`read`) puts the picture back, and
    `python tools/perc/frames.py RUN..` measures / marks a recording. This was the "EXP text 1 px left", 1 px of
    the "tracker camera off" and the 682.
  - **The background arithmetic is one formula on all 7 maps:** `b + off + trunc(r * (C + off) / 100)`, off **683**
    (half the width) / 468, measured layer by layer (E8, tools/perc/redesign/exp_backfit.py): 736 of 736 positions
    in x (rx -2 .. -80), 587 of 587 in y. With 682 Line 1 (rx -30 / -50 / -80) explained only 81 % of the picture.
  - **FIXED `Scene.locate` on scenery that repeats:** Transfer Area's brick walls let a camera one brick over match
    31 % of the landmarks; following frame to frame it was taken (61 px off for 2 s). Now a look is final only if
    it matches about as well as the last frame did (`last_share` x 0.85), else all looks are made and the best
    wins. "A wrong offset matches ~2 %" holds only on scenery that does not repeat.
  - **`scene_check.py RUN --n 120 --follow`** (new: --follow registers every saved frame from the one before, as
    the bot would; --t1). Camera found on every saved frame of every run and the best of its 25 neighbours on
    120 / 120 everywhere. Explained outside blobs p5 / p50, whole play area p50, unknown p50:
        Ant Tunnel IV        99.58 / 99.87 %   95.2 %   0.0 %
        Dark Cave (0-16 s)   99.86 / 99.95 %   96.8 %   0.0 %
        Dangerous Steam      99.61 / 99.87 %   96.4 %   1.7 %
        Line 1 <Area 1>      99.64 / 99.80 %   94.1 %   0.9 %
        Transfer Area        99.44 / 99.89 %   96.6 %   1.5 % (max 26.7 %: animated objects)
        Perion Street Corner 99.27 / 99.71 %   60.9 %  24.3 %
        Land of Wild Boar    99.54 / 99.85 %   52.1 %  34.8 %
    Register + expected + compare 4-10 ms (Line 1 / Transfer Area 16-22 ms: 29-36 background layers drawn one by
    one -> pre-compose the layers of one parallax in step 2).
  - **DEFERRED (the user, 2026-11-16: "ignore the clouds and focus on clean maps for now") - TASK FOR LATER:
    Perion's moving clouds (type 4 backs, rx 5 .. 35 = a speed, not a parallax).** Until then the two Perion maps
    (and any map with moving backs: 95 of 206) are NOT covered by the scene model; work and gates use the clean
    maps (Ant Tunnel IV, Dark Cave, Dangerous Steam, Line 1, Transfer Area). They drift over
    the background rocks (never over tiles / mobs). Today their place is taken from the fixed formula: the area
    marked unknown is not where they are, and where they are the rocks behind read as "something drawn over the
    scene" (blobs 43-50 % of the play area). To do: measure where / how they move (y, speed), then either mark
    the rows they can reach unknown or - better - find each layer's x per frame (a known picture, 1-D search) and
    explain it.
  - Dark Cave 084719_1: **the game window was moved ~33 px left / 22 px up at 16.4 s** (a mouse drag; no key) and
    the capture kept its old place: from then on the picture is cut (the desktop shows at the right edge). Only
    0-16.3 s is a clean picture. Measured later (HUD strip per saved frame): a DRAG of 1.15 s, 16.37 -> 17.53 s,
    over -46 / -38 to its rest at -30 / -22 px; the focus guard never fired (a title-bar drag keeps focus).
  - **DONE (2026-11-16): the capture re-checks the window - `Screen.check()` + `maplebrain/runtime/window.py`.**
    The user chose the check on EVERY tick (not ~1 / s): before and after each grab, like the two focus checks, so
    a frame is used only if the client box was the aimed one on both sides (1.51 microseconds per check on the
    real window). Not aimed -> `WindowLost` (a `FocusLost`): the pause path, keys released, log `PAUSED: game
    window moved: capture aimed at (x, y) WxH, window now at ...`. `wait_back` ends the pause when the game is
    focused, the client area is 1366x768 and the box read the same on two looks (varied ~0.2 s apart: a window
    still dragged is not aimed at) -> `calibrate()` + `capture re-aimed: game window moved OLD -> NEW`, then
    "resumed" as after a focus loss (brain reset, ~1 s varied settle). **Not 1366x768 (resized, minimized = 0x0,
    window gone): said once, paused, NEVER re-aimed / resized silently** (the user: native windowed always), and
    "game window back" when it is. Covered: `_hunt` (v1 + observe), `hunt_v2`, goto's `_tour`, serve between
    hunts and `watch` (`window.Aim.ok()` per look: a look is skipped while not aimed; watch's Screen is now
    `Screen(hwnd, dxcam=False)`). A running `watch` gets it at its next start (the user's).
    Dark Cave replayed through the guard (tests/test_window.py, the measured drag): paused at 16.41 s (the first
    shifted tick; 0 shifted frames used instead of 60 s of them), re-aimed once at 17.8-17.9 s on the final place,
    back at 18.1-18.2 s (+ the settle). Tests: tests/test_window.py (16). pytest green, bot speed 31.0 ms
    (baseline 30.0; the bench has no window), replay press1 HEAD vs work: 166 real + 11 weak both, 100 % found.
    Left open: the compositor may show a move 1-2 frames before / after the box reports it (not measurable on
    the recording: no box was logged); NOT live-tested yet (drag the window during a `serve --observe`).
  - Sprites 1:1 on the new maps (`native_check.py`, per-mob median 100 % everywhere): Stirge / Horny / Zombie
    Mushroom 95-99 % pooled. Bubbling (Line 1) 50 %: a half-transparent mob (score 0.995) - needs sprite-over-
    scene, not sprite alone (step 3). Wild Boar 74 %, Snail 78 %: some are pale (fading in, to check).
  - Today's tracker on them: Dangerous Steam 85 weak tracks (83 of one mob type: scenery ghosts) beside 173 real;
    Perion Street Corner 31 weak / 96 real. **Tick 61-68 ms on the two Perion maps** (gpu 18-40 ms, world 15-32 ms).
  - **Speed finding: the bench read 42-46 ms today with and without these changes (A/B by stash), 28.8-29.2 ms
    pinned to the performance cores** (affinity 0xFFFF + AboveNormal; baseline 30.0). Windows runs a background
    console process on the efficiency cores while the game is in front - the live bot is such a process.
    **DONE (the user: "pin everything to performance"): `maplebrain/procperf.py`** - run / serve / goto / watch and
    the bench pin their own process to the performance cores (highest efficiency class: 16 of 20 here), priority
    Above Normal, power throttling off; the first console line says what was set. Bench launched unpinned from the
    background: 30.2 ms (was 42-46). A running `watch` gets it at its next start. Live tick not measured yet.
  - pytest green pinned (speed 28.8 ms); replay press1 HEAD vs work: 166 real + 11 weak both, 100 % found.
  - **NEXT:** step 2 on the clean maps (order to agree). Labels still open.
- **Step 2 state (2026-11-16, later): the order AGREED with the user** (each sub-step: pytest + bot speed line +
  replay HEAD vs work on the 5 clean native maps + press1 + fix3, track-frames >= 99.9 % both ways):
  0 live "before" number (the user records `serve runs\play --observe --gpu --tracker --frames-png`, Ant Tunnel IV,
  ~2 min, watch OFF) | 2.1 one upload + one grey | 2.2 FrameFacts | 2.3 minimap window per map | 2.4 pre-composed
  backgrounds | 2.5 scene camera in shadow (logged, unused) | 2.6 scene camera takes over (camshift, phase
  correlation, per-tick minimap -> fallback only; maps without a clean scene keep today's path whole) | 2.7 own
  tag 1:1 (re-cut from PNG, then GPU, wide look off the main path) | 2.8 Lie Detector: watch 1 look / s, the match
  on the GPU, measured watch off / 0.3 s / 1 s / GPU; native templates (client UI files first, else the next real
  LD's PNG from watch; bar back to 0.80 only on the user's word) | 2.9 async GPU + CPU threads + HUD cache + FFT
  search (the plan's gate p50 <= 20 ms, p90 <= 25).
  The user's answers: the bench stays on the JPEG fixture with the scene camera at +-30 (exactness gated by
  scene_check on PNG runs); press1 / fix3 (FHD JPEG) test only the fallback path; the explained gate is the p50
  per map (Transfer Area p5 99.44 % is fine); `watch` was STOPPED by the user for the measurements ("run whatever")
  - remind them to restart it; the capture guard for a moved window is done (f639199).
  - **DONE 2.1 + 2.2 (284ef51):** the frame goes to the GPU once per tick (`GpuSpriteDetector.upload` ->
    `frame_u8`); the half-size picture of the whole-screen search is made there (`_half`: floor((sum + 2) / 4) =
    cv2 INTER_AREA bit for bit, tested) instead of a CPU resize + 2nd upload. Grey once per frame (tag, Lie
    Detector thread - no frame copy any more -, phase correlation, camshift); HSV once in find_tags; the tag's near
    search crops before converting. `perception/facts.py` FrameFacts v1 (own tag, HUD readings, slots, minimap dot /
    position, both shifts, detector hits, players' tags, Lie Detector look; + scene_cam / scene_share with 2.5):
    `Perceiver.facts`, written per tick to ticks.jsonl as "facts" (Recorder.tick(facts=)), FrameFacts.from_dict
    round-trips (tests/test_facts.py, strict JSON). Replay: press1 + fix3 identical, native Ant Tunnel 18165 of
    18170 real track-frames both ways.
  - **Profile (bench fixture, game up): the `gpu` part is 13.6 ms of which the whole-screen NCC convolutions are
    10.75**; resize 0.14, play upload 0.31, full grey 0.24, full HSV 0.55. So 2.1 saves ~1.5 ms; the big cut is the
    FFT search (2.9, E6: 8.5 -> 4.7 ms).
  - **Speed finding: without the game running the GPU idles at P3 / ~1000 MHz and the bench reads 40-43 ms (HEAD
    too); with the game up 2745 MHz and the baseline holds** (code before this session 29.1-29.5 ms). Bench only
    with the game open (or A/B in the same state).
  - **DONE 2.3 (f5b07cb):** the minimap window's real rectangle: `hud.minimap_rect(window)` = (0, 0, x+w+5, y+h+14)
    from the locator's measured inside (`MinimapLocator.window`, set at calibrate); measured on all 7 native runs
    by the border pixels and checked by eye: Line 1 277x152, Ant Tunnel IV 230x198, Dangerous Steam 219x198,
    Transfer Area 175x201, Perion SC 254x171, Wild Boar 181x178 (UI_RECTS' 215x195 was wrong both ways).
    `hud.ui_mask(shape, minimap)` for our tag + players' tags (+ the scene camera's landmarks).
    **The minimap picture is SEE-THROUGH where its canvas is transparent:** a Horny Mushroom walking behind it was
    tracked at 0.90 (Ant Tunnel #448, 012059_1 t 319-321) - mob tracks are NOT masked there. Replay: same tracks
    everywhere (fix3 99.94 %). Bench with the game up: 29.1-29.5 -> 27.3 ms (self 2.7 -> 1.2).
  - **DONE 2.4 (720564d):** `Scene._compose`: consecutive known background layers with the same (rx, ry) are drawn
    once at load into one fp16 plane covering every camera of the rendered area (Line 1: 29 layers -> 4 groups,
    Transfer Area 36 -> 3; 41-126 MB of GPU memory per map); `expected()` crops it (per-layer fallback outside the
    plane, `pre=False` = the reference). Max difference < 0.5 levels, known mask the same (tests). scene_check
    --follow, 5 clean maps: register + expected + compare Line 1 16-22 -> 2.1 ms p50, Transfer Area 1.8, Dangerous
    Steam 2.9, Dark Cave 2.2, Ant Tunnel IV 3.5; explained outside blobs unchanged (99.44-99.86 / 99.80-99.95 %),
    camera on every saved frame.
  - **DONE 2.5 (scene camera in shadow):** `scene.SceneCamera` (locate around the last camera + its last step - a scroll moves
    up to ~26 px a live tick, the near look reaches 12 -; `last_share`; the tracker's camera as the seed; not found
    -> None, the last camera kept as the next guess, nothing guessed). `runner._load_scene` attaches the scene to the
    detector (`sprites.scene`) only when `assets/scene/<map>` exists AND the map has no moving / animated backs
    (`Scene.clean`); the log says which camera the map gets. The Perceiver runs it on `frame_u8` after the detector,
    part `scenecam`, -> obs.scene_cam / facts.scene_cam + scene_share; nothing reads it yet. Config
    `perception.scene_tol` (4; the bench 30 on its JPEG fixture, now unshifted by tests/fixtures/perf_ant4/xshift.txt
    via tools/perc/frames.py). Bench: scenecam 0.7 ms p50 / 1.4 p90 (found on 44 of 45 fixture frames: the first has
    no seed yet), tick 28.2-28.7 ms. The replay (tools/perc/replay/run.py) now reads frames through frames.read (the
    1 px shift of 012059_1 / 084844_2 undone) and writes scene_cam + per-part ms.
    Gate: tracks the same on all 7 runs (>= 99.98 % of track-frames both ways; Ant Tunnel's totals are 18160 now on
    both sides: the unshifted frames). Scene camera on the 5 clean maps: found on every saved frame but each run's
    first (no seed yet - 2.6 seeds it from this frame's minimap), scenecam p50 0.7-0.9 ms, p99 1.6-3.1, max ~20
    (the first wide looks); scene - tracker camera p50 dx -0.5..-4.8, dy -1.2..-3.8 px, p5..p95 up to -20..+14.
    On FHD JPEG (press1 / fix3) at +-4: found on 0 frames - never a wrong camera - but 1.4 ms a tick spent
    looking: 2.6 backs off to ~1 look / s while it keeps failing.
    Lie Detector (for 2.8): the client HAS the windows (UI_000.wz LieDetector.img / AntiMacro.img, pictures in
    UI/_Canvas, BMS key). The small gold "LIE DETECTOR" title (today's panel + game templates) is drawn into
    AntiMacro lieDetectorStandBy/back, lieDetector/back1, soundLieDetector/stanby/backgrnd, on a see-through bar
    (alpha 170): today's panel template scores 0.77-0.81 there (bar 0.75!), the game template 0.91-0.93 on the
    same title - any template counts, so a native one is still caught. The blue title and "Question in" are font
    text (staticText in the img): no picture, those need a real LD.
  - **Live recording with 2.1-2.5 (the user, `runs/play/20261116_154819_1`, Ant Tunnel IV, 102 s, 3522 ticks, PNG,
    serve --observe, watch off): tick p50 28 ms, p90 31, p99 54 (012059_1 before: 29 / 32), 34.5 fps.** Parts p50:
    gpu 11.7, world 5.4, hud 2.6, locate 2.0, camshift 2.0, self 1.3, scene 1.1, scenecam 0.7. The p99 = the
    whole-screen tag look (`self_wide` 28 ms when it runs: 2.7). Scene camera live: found on 3521 of 3522 ticks
    (the first: no seed), share 0.9, 0.7 ms p50 / 1.9 p99; today's camera > 8 px off it on 31 % of ticks; the
    camera moves p50 2 px / p99 13 / max 38 per live tick. facts on every tick (v1).
  - **DONE 2.6: the scene camera takes over** (brain v2 / v3 = `--tracker`; v1 keeps today's camera, the scene camera
    only logged): `Camera.update(exact=)` takes it as it is (no shift, pull, leash or clamp); obs.cam_src "exact".
    While it holds (found on the last tick): no phase correlation, no camshift matching (its reference frame is kept
    for the fallback), the minimap read only every `perception.minimap_every_s` (1 s) and whenever our tag is lost
    (SelfTracker's fallback) - a scrolled minimap window (Ant Tunnel IV) is found anew then (`_locate(fresh=)`).
    First frame: seeded from this frame's minimap (map_pos - our screen feet). Lost: today's path for that tick
    (camshift from the kept reference); 10 misses in a row (no such scenery, FHD frames) -> one look a second.
    obs.scene_dx / dy = the scene camera's step (the v1 target tracker reads them).
    **Evidence (replay HEAD = 2.5 vs work, 8 runs):** mob feet vs their platform's surface, within 2 px: Ant Tunnel
    IV 23-27 % -> 97.5-97.9 % (p5..p95 -3.8..+11.4 -> -0.9..+1.2 px), Line 1 57 % -> 97 %; Dark Cave / Dangerous
    Steam / Transfer Area stay wide either way (flying Stirges: the measure doesn't apply). Sighted track-frames the
    same in both 97.8-99.7 %; the rest = mob TYPE flips (1.6-1.8 % on Ant Tunnel: the two checked by eye - t 7.8
    and 90.4 of 154819_1, Horny Mushrooms - the NEW camera has the right type, the old one said Zombie Mushroom)
    and coasting tracks (predicted in map px: they move with the camera). Real tracks 183/183, 471 -> 478, 63 -> 64,
    125 -> 126, 47 -> 46; weak 2 -> 1, 3 -> 1, 1 -> 3, 13 -> 15: the 2 new weak ones looked at = a 2nd track beside a
    dying Bubbling at the screen edge (Line 1 17.8 s) and a coasting one over a Zombie Mushroom under a hit effect
    (Ant Tunnel 63.6 s, HEAD has its own there) - the A2 / A4 ghost classes, step 3's job. press1 / fix3 (FHD JPEG:
    the scene camera fails, today's path) 99.8-100 % both ways. Tools (tools/perc/replay/): surface_check.py,
    diff_kinds.py, weak_new.py, show_track.py - the camera / type evidence for later gates.
    **Bench (game up): 28.2 -> 24.3 ms (p90 25.9), 41 fps - RE-BASELINED on purpose** (camshift 2.2, scene 1.1,
    locate 1.4 gone; scenecam 0.7).
  - **THE GATE CHANGED (the user, 2026-11-16): `tools/perc/replay/gate.py`** (README there): ~1 min clips of every
    clean native map + 1 FHD clip instead of whole runs ("more ~1m footages of various maps is better than 1 long
    footage"); replays cached by a fingerprint of code + tracked assets + replay tools (the after of one sub-step =
    the before of the next: no double replays); `--quick` (3 clips, ~3 min) per sub-step, the full 7 (~7 min) before
    a commit that changes tracking; nothing to replay when the fingerprint didn't change. Found while building it:
    `run.py --old` serves code from git but assets from disk - the first 2.7 template gate compared the new template
    with itself (void, redone with the cache). The user may record more ~1 min clips on other clean maps.
  - **DONE 2.7a: own tag template 1:1** (`assets/self_tag_gray.npy` = per-pixel median of 488 aligned tags of
    154819_1; same 17x74 frame, thresholds unchanged): whole-frame look on 8 native recordings own p50 0.86-0.88 ->
    0.94-0.95 (Perion 0.91), anything else <= 0.53. A stable-pixel mask was tried: 105 ms and false peaks 0.99, no.
    Gate (full, 7 clips): tracks the same (real / weak counts equal everywhere, sighted 100 %), tag found +0.2..+2.5
    points on every native clip (Dangerous Steam 78.2 -> 80.7 %, Transfer 80.8 -> 82.6 %), FHD clip 90.1 -> 89.6 %.
  - **DONE 2.7b: our tag's whole-screen look on the GPU** (`selfpos.GpuTagLook`: the same high-pass + NCC as
    convolutions on the frame uploaded at the tick's start - `GpuSpriteDetector.prepare`, one-shot, find() reuses it;
    the CPU near search confirms at its best place, so place and score are the CPU's; nothing there + the tag last
    near a screen side -> the old CPU look with its edge search). Wide look 42-44 -> 8-12 ms p50 on the clips; first
    call warmed at load (cudnn timing: 3.5 s, would have stalled the first tag loss). Gate (full): the same tag on
    every clip, tracks the same. Bench 24.0 ms (the fixture rarely loses the tag: the gain is the live p99, 54 ms).
    tests/test_perception.py: GPU look + confirm = CPU look on the perf fixture.
  - **DONE 2.8 (code; the user's live check open - START HERE):**
    - **Native templates** (`tools/perc/ld/cut_native.py`; the client export now has `UI\AntiMacro` +
      `UI\LieDetector`: tools/cwdata/export.ps1's new section). The gold title is the same letters in the panel
      (lieDetectorStandBy/back) and the mini-game (lieDetector/back1), on a see-through bar (alpha 170-187 around
      the letters, letters 204-255), so candidates (crop x backing grey) were graded over real native scenery: each
      client window alpha-blended onto 150 native frames at random places + the false max over all 8641 native PNG
      frames of the 2026-11-16 recordings + the 90 saved real ones (runs/*/lie*.png, all stretched captures).
      **Found: today's templates were weaker at native than estimated** - the old panel template on the client's
      panel min 0.677 / p5 0.762 (would miss at the 0.75 bar), the old game template 0.780 / 0.882 (it alone caught
      it). Chosen `lie_detector_title.npy` (letters + 1-2 px, over grey 96, 8x65): min 0.970 / p5 0.981 (panel),
      0.978 / 0.988 (game), false max 0.496 (old 0.671); `lie_detector_sound.npy` (the sound kind's larger yellow-
      green title, never seen live): 0.995 / false 0.434. They replace panel + game (removed); blue title + "Question
      in" stay (font text: a real one at native needed). Every real frame the old set caught is still caught
      (title 0.83-0.94 on the stretched captures; the stretched JPEG fixture panel 0.79). Tests: the client's
      windows (tests/fixtures/lie_client_*.png) pasted on native frames >= 0.95 anywhere.
    - **The hunt's look on the GPU** (`liedetector.GpuLieLook`, `LieDetector.use_gpu`, config
      `perception.lie_gpu` True; the Perceiver passes the uploaded `frame_u8`): one rfft2 of the frame x the
      templates' spectra (one batched irfft2), window sums from int64 integral images, cv2's rule for flat windows,
      cv2's 15-bit grey bit for bit. Exact: max |cpu - gpu| 1.7e-05, same places (`tools/perc/ld/ld_check.py`, 90
      real + 346 native frames); 3.5 ms vs ~90 ms CPU; warmed at load. On the frame itself: no thread, never late.
      (A plain conv2d version: 1 s and wrong on flat windows - the FFT one is the reusable piece for 2.9.)
    - **watch**: a look every 1 s by default (`--every`), `--gpu` optional (no gain measured, keep CPU).
    - **Speed** (`tools/perc/ld/ld_speed.py`, the bench's tick on the fixture x3 forth and back, a real watch
      process beside it, game up; cycle 1 of 2 - stopped for the session's end): tick p50 / p90 / p99: hunt CPU
      thread + watch off 21.6 / 23.9 / 37.9; + watch 0.3 s 21.8 / 24.0 / 37.0; hunt GPU + watch off 21.6 / 24.0 /
      37.1; + watch 0.3 s 21.6 / 24.7 / 36.9; + watch 1 s CPU 21.5 / 24.0 / 37.0; + watch 1 s GPU 21.8 / 24.9 /
      37.9 -> all in the noise; kept: hunt GPU (never late) + watch 1 s CPU. The `lie` part: <= 3.1 ms on a look tick.
  - **DONE 2.9 (bench 22.0 -> 18.4 ms p50, p90 25.7 -> 21.1; the gate p50 <= 20 / p90 <= 25 met):**
    - Profile before (synchronized timers, fixture, game up): whole-screen search convolutions 7.6, peaks + refine
      2.4, `find_near` 6.3 p50 / **20.0 p90**, players' tags 6.1 (already on a thread), HUD 2.4 (HP / MP text 2.0),
      own tag near 1.3, scene camera 0.7, grey 0.5, upload 0.3.
    - **2.9a HUD cache** (`hud.HudText`): HP / MP / EXP each re-read only when its crop (number row, rows 740-746)
      changed - a reading is a pure function of that crop, so the result is identical by construction. Crops repeat
      on 94-98 % of saved native frames 3 ticks apart (3 recordings). HUD 2.4 -> 0.1 ms; bench 22.0 -> 19.4-19.7.
      Test: tests/test_hud.py (mixed sequence = plain readers on every frame; a pixel inside / outside a crop).
    - **2.9b CPU readers in threads** (`Perceiver.readers`, 3 threads): right after the upload, `_read_self` (the
      grey + own tag near search + the fallback's phase correlation), `_read_hud` (HudText + the potion slots) and
      players' tags start; this thread runs the Lie Detector look + the mob detector on the GPU meanwhile; everything
      with memory (HP / MP pairs, slot votes, EXP history, prev_small, me_near, the wide look) is applied after the
      join. Parts `self` / `hud` / `scene` / grey -> ~0 (hidden); `gray` part renamed `upload`. One order change:
      players' tags get the minimap rectangle from before this tick's minimap read (differs only on a tick that
      re-finds the minimap window). `hud.ui_mask` made thread-safe (returned from the local, not re-read from the
      cache another thread may clear). Bench 18.2-18.4 (p90 20.8-22.4); full gate: SAME tracks on all 7 clips,
      every column identical.
    - **Dropped (the user: "Don't do anything that step3 replaces"):** the FFT whole-screen search and a faster
      `find_near`. Measured for later (tmp scripts, not committed):
      - FFT whole-screen masked NCC (rfft2 of the frame, its square and the centred frame x cached template / mask
        spectra, batched irfft2): **7.7 -> 4.4 ms** on Ant Tunnel IV's 26 poses; the detector's peak set identical
        on 45 of 45 fixture frames (329 peaks); scores above 0.58 within 0.011; BUT the FFT error is absolute
        (relative to the whole image's energy), so near-flat windows differ by up to 1.4 - GpuLieLook's exactness
        came from int64 integral box sums, which a masked search can't use. Worth it only for maps without a clean
        scene, if they keep the dense search after step 3.
      - **`find_near` = the tick's p90 (input for step 3):** always the visible-only path; tracks unseen > 0.12 s get
        pad 32 at ~1.1 ms per spot (pad 24: ~0.5), and a batch is rounded up to 2/4/8/16 spots - 9 spots cost 16
        (17.6 ms on fixture frames 5-20, 9-14 coasting / hidden tracks). Step 3's windows must not scale like that.
- **Step 3 state (2026-11-16): the order AGREED with the user** (PLAN-perception.md "Step 3"; each sub-step: pytest +
  the speed line + `gate.py --quick`, full gate before a commit that changes tracking).
  - Facts behind the order (from the code): (1) the fit needs the scenery split at the mob's layer - scene.png is all
    8 layers merged; a mob on foothold layer L is drawn over layers <= L and under layers > L + front backs; the
    cover masks are binary (alpha >= 128) and miss front backs -> per mob layer "behind" + "front" planes (3.2).
    (2) The perf fixture was JPEG -> DONE d87e5b4: lossless WebP, same 45 frames, shift undone; bench 18.3 ms
    (baseline 18.4, not re-baselined). (3) The documented ghost runs (P2 table) are FHD JPEG: the scene camera never
    registers there, so they only test the fallback -> the ghost gate is native (Dangerous Steam + the clips' weak
    tracks). (4) Ant Tunnel IV: 2 types, 46 poses (all animations x 2 facings), 26 live.
  - Cost input from DONE 2.9: find_near ~1.1 ms per spot at pad 32 because every pose is convolved over every window
    (padded to the largest pose) then masked, batches rounded to 2/4/8/16 (9 spots = 16 ms = the tick's p90) -> the
    new windows: packed by area, each window only its candidate poses, D-pruned positions. The FFT (7.7 -> 4.4 ms
    whole screen) is NOT used in the fit: its error is absolute (up to 1.4 on near-flat windows, where the fit must
    be exact); kept as the option for the fallback if it outlives the clouds task.
  - Decided: COVERED / ABSENT go to today's tracker as None in 3.4 (its timeouts stay until step 4); maps without a
    clean scene keep today's path whole, per tick; labels = the 300 picked frames of 012059_1 (no extra maps until
    the new footage); tests on pre-native footage deleted (d87e5b4: 1200 -> 1074 tests; kept: every Lie Detector
    test + test_runner / test_window, which run the loop on look_snails + tests/fixtures/self_tag_gray.npy).
  - **3.0a DONE (2026-11-16): all 300 picked frames of 012059_1 judged** -> RUN/labels.json v2: 1547 mobs, 102
    recording tracks judged empty, 93 unsure spots; classes (a mob may carry several) clear 917, player 227, effect
    177, fade 133, dying 82, ui 72, edge 60, scenery 51, hit 33. `tools/perc/label_eval.py RUN [--tracks
    replay/X.jsonl] [--list]` reads v2 (v1 too): recall + type per class, false tracks by source (unmatched tracks
    at an unsure spot / dying / hidden not counted). **"Before" = HEAD (926c467) replayed over every saved frame**
    (`replay/run.py RUN --out before`, mob score 0.70, 169 s; RUN/replay/before.jsonl):
    found 1334 / 1547 = 86.2 % (not dying 86.0 % of 1465), wrong type 74; false tracks 145 = 9.8 % (coast 134,
    near 6, acq 5; not counted: unsure 45, dying 58, hidden 5). Recall per class: clear 94.0 %, scenery 90.2,
    dying 90.2, effect 86.4, hit 81.8, player 75.8, edge 71.7, ui 66.7, fade 51.1 (type right on 85-100 % of the
    found; ui 85.4 / edge 88.4 / clear 94.0 lowest). Takeaways: false tracks are almost all COASTING tracks (no
    sighting: the mob moved / died / was a fade) = step 4's evidence; misses are fade-ins, UI over the mob, players
    in front and the screen edge = 3.2 (opacity + per-pixel labels) and step 5 (players as occluders).
    Labelling notes: where two mobs overlap and one track sits between them, the token moves it (@x,y) to the mob
    of its type if one is there, else to the nearer; mobs fully under the quickslots = "?" or not added.
    `tools/perc/labels/patches.py RUN PICK` = the camera followed over every saved
    frame (3858 / 3858, cached RUN/labels/cams.json), D patches per picked frame (p50 13, max 27), one sheet per frame
    in RUN/labels/sheets/ (the frame + the recording's tracks lettered + a 2x tile per track and per untracked patch,
    screen ticks + footholds). Judgments: tools/perc/labels/20261116_012059_1_judged.jsonl (format in
    tools/perc/labels/label.py: a token per track letter + added mobs + unsure spots, classes e/p/s/u/f/d/x/h);
    `label.py RUN JUDGED` -> RUN/labels.json v2. Seen while labelling: many weak / unseen tracks are real
    mobs under the cursor tooltip / quickslots / chat (u), behind players (p), or fading in (f); "n" = tracks on
    nothing (dying tracks after the corpse went, a few ghosts).
  - **3.0b DONE (2026-11-16): synthetic frames with exact truth** (tools/perc/synth/, README = make.py / synth.py
    docstrings; nothing on the live path). Base = the 300 labelled frames of 012059_1 at their followed camera
    (cams.json) with their real mobs ERASED (every D blob that isn't our character's blob or under the UI ->
    the expected scene); what can't be erased (our blob, often with a mob merged into it; the UI) = "dontcare"
    boxes + the labelled mobs there as "unsure". Mobs drawn as the client does: sprite alpha x opacity, feet on a
    foothold, the tiles / objects of the layers above the foothold's re-drawn over it (rendered from the export
    by scene.build_scene on those layers, cached runs/synth/cache/<map>/front_L.png; Ant Tunnel IV: all 497
    footholds on layer 1, no front backs), both facings, every pose (19 Horny: stand 3 / move 4 / hit / die 4;
    21 Zombie: stand 2 / move 4 / jump / hit / die 3). Over them: **Effect/BasicEff WAS exported** (export.ps1,
    2026-11-16) -> the client's red damage digits (NoRed1 first + NoRed0, HeavenClient's advances); our character
    cut from 24 other frames (D blob at obs.me, <= 140x120: body, tag, the pet snail, drops beside it); the UI
    (chat / quickslots: the base's own UI pixels re-drawn, opaque where they differ from the scene; only rects with
    no real mob near: a mob under the UI passes for UI). Not available: weapon hit sparks / skill effects (not in
    BasicEff), speech bubbles (none cut). Dying / hit frames carry a "prime" frame (the mob alive, same feet) shown
    to the tracker first (it turns tracks dying, never starts one so).
    Truth (synth.json = labels.json v2 + per frame case / base / C / dontcare, per mob pose / facing / opacity /
    onscreen / vis / cover {s, e, p, u} / layer / box). `make.py RUN --n 500 --seed 1 --out runs/synth/ant4_500`
    (~2 min, 0.6 GB, + sheet.png = one frame per case), `before.py OUT` (today's Perceiver per frame: fresh
    tracker, scene camera started at C, 2 ticks 0.05 s apart; 61 s), `label_eval.py OUT --labels synth.json
    --tracks before.jsonl --synth` (+ recall per case / opacity / on-screen / visible share, "seen" = sighted on
    that frame, the ghost test). pytest set: tests/fixtures/synth_ant4 (seed 7, 40 frames, stored as the window
    around the mobs, 4.7 MB; tests/test_synth.py: clear mobs 1:1 with the sprite, the fade opacity from the
    regression slope within 0.12, label_eval scores the truth 100 % / 0 false).
    **"Before" on synthetic (HEAD detector + tracker, mob score 0.70, runs/synth/ant4_500, 500 frames, 786 mobs):**
    found 67.4 % (not dying 62.5 %), wrong type 0, **false tracks 0, ghost test 0 on 50 mob-free frames** (half
    with damage digits / our character over bare scenery; not counted: unsure 254 = real mobs kept in our blob,
    dontcare 4). Recall per case (synthetic | labels): clear 100 | 94.0, scenery 93.8 | 90.2, dying 100 (seen, as
    die poses by the near search) | 90.2, hit 100 | 81.8, fade 71.4 | 51.1, ui 40.7 | 66.7, player 31.8 | 75.8,
    effect 31.5 | 86.4, edge 14.0 | 71.7. Fade by opacity: 0.20-0.35 8.7 %, 0.35-0.50 71.9 %, >= 0.5 100 %. Edge
    by on-screen share: 0.3-0.5 0 %, 0.5-0.6 12.5 %, 0.6-0.7 42.9 % (the new-track rule: 60 % on screen, < 60 %
    needs 0.70). By visible share: < 0.5 0 of 111, 0.5-0.7 18 %, 0.7-0.9 85 %, >= 0.9 92.6 %. Why lower than the
    labels on effect / player / edge: the labelled ones are mostly mobs the tracker already followed (it holds a
    track through cover), the synthetic ones are first sightings - the honest number for "can the frame show it";
    synthetic covers are also heavier (visible share p50: effect 0.62, player 0.61, ui 0.60, edge 0.50). Takeaway for 3.2: the misses are all "part of the body is
    something else" (cover, opacity, edge) - exactly the per-pixel fit's job; no ghost to fix on this map.
  - **3.1 DONE (2026-11-16): D in shadow** (nothing reads it; tracking unchanged). `Scene.diff(frame, C, tol, mask)`
    (scene.py) on the frame already uploaded: |frame - expected(C)| > tol (any channel) on known scenery outside
    hud.ui_mask (the minimap's measured rectangle), erode 3x3 + dilate 13x13 as max pools on the GPU (cv2's borders)
    -> the blob mask back (1 MB, 0.15 ms); `scene.patches` = cv2 connected components, >= 60 px -> [x, y, w, h, area]
    biggest first, on a reader thread while the tracker runs. Exact connected components ON the GPU (torch label
    propagation + pointer jumping) were measured: 12 ms p50 / 31 p90 -> no. Perceiver: only on ticks where the scene
    camera was found (config `perception.scene_diff`, tolerance = scene_tol); parts `diff` (main thread) + `patches`
    (the thread's own ms). FrameFacts v2 `patches` (None = no D this tick; v1 records still read), in ticks.jsonl
    and in the replay's jsonl. Exactness: GPU blobs = tools/perc/labels/patches.py's rule on 80 / 80 labelled frames
    and on all 40 fixture frames (test).
    Measured (`tools/perc/dcheck.py synth OUT | labels RUN | clips`; IN = one patch box holds >= 90 % of the mob's
    body box (on screen, outside the UI), TOUCHED = any patch box overlaps it):
    - **synthetic (runs/synth/ant4_500, 783 mobs): touched 100 % in every case / visible-share / opacity bin; in
      99.2 %** (clear / dying / effect / fade / hit / player / scenery 100 %, ui 98.2, edge 91.2: the 6 not "in" =
      5 edge + 1 ui mobs whose box is mostly transparent sprite margin beyond the patch, all touched). Opacity
      0.0-0.3: 16 of 16 in. **Mob-free frames (50): 0 patches away from our blob / the UI / the pasted distractors.**
      Patches per frame p50 4, max 7. (make.py now records the distractors' boxes: synth.json "distractors"; frames
      and every other field regenerated bit-identical, ant4_500 + the fixture.)
    - **labels (012059_1, 300 frames, 1453 judged mobs): touched 99.5 %, in 93.7 %**; per class in / touched: clear
      96.7 / 99.8, player 92.8 / 99.6, effect 94.6 / 100, fade 80.8 / 97.6, dying 78.4 / 100, ui 86.6 / 100, edge 77.4
      / 98.1, scenery 95.9 / 98.0, hit 93.9 / 97.0. The body box here = the type's stand frame at the labelled feet
      (pose / feet approximate: most "not in" are that). The 6 untouched, looked at (frame | D picture): 2 under the
      UI strip (feet y 690 / 728: no world pixel), 3 fade-ins with D max 1 on their spot (nothing drawn yet: n1440 x2,
      n9081), 1 clear Zombie at n6060 (400, 385) with nothing there and a mob ~70 px above (a label to re-check).
    - **gate clips (working-tree replays): patches per frame p50 7-14, p90 11-18, max 27; a patch's box area p50
      1.9-4.2 k px, p90 8.7-15.8 k; all boxes of a frame p50 31-91 k px, p90 50-127 k (3-13 % of the play area)** =
      the fit's work in 3.2. D on every frame of the 6 native clips, never on the FHD clip (no scene camera).
    - **cost, bench A/B in the same state (game up, Ultimate Performance, 3 rounds): D off tick p50 19.8-20.1 / p90
      22.5-23.4, D on 22.7-23.0 / 25.3-25.8 -> D = +2.8 ms p50** (diff 1.75 on the main thread = expected() +
      compare + pools + the mask back; connected components 1.3 on the thread; world +0.8 beside it). The machine
      read 1.6 ms above the 18.4 baseline with D off today; pytest's line: 22.3 ms (D on). Gate "bench <= 18.4 + D's
      cost": met on the A/B. In the replays (no game timing) diff 2.8-4.3 ms, components 2.4-2.5. expected() is most
      of `diff` and 3.2 replaces it with the per-layer planes: not optimized (rule).
    - **full gate: the same real / weak counts, sighted, surface, tag and camera on all 7 clips; verdict CHANGED
      only from ant4 3804 / 3808 = 99.89 % (the working tree's replay had 3-4 more real track-frames). Replayed
      that clip again with D off and D on: 3805 / 3805 both ways, identical -> GPU noise of that replay.**
    Tests: tests/test_scene_diff.py (2; skipped without assets/scene/10005063): GPU blobs = the label tool's rule
    on all 40 fixture frames; every fixture mob in a patch, mob-free frames only at dontcare / distractors.
  - **3.2 proposal (the fit) - OK'd by the user 2026-11-16:**
    (1) Planes (scene.py, at load): per foothold layer L used by the map, BEHIND_L = backs + tiles / objects of
    layers <= L, FRONT_L = tiles / objects of layers > L + front backs, as premultiplied colour + alpha (fp16, like
    _compose); front over behind = today's expected() (test). Ant Tunnel IV: 1 layer -> 2 planes.
    (2) Model per pixel for a pose (sprite colour s, alpha a) at feet p with opacity o:
    I = F + (1 - A) * (B + o * a * (s - B)). Where A < ~0.98: I' = (I - F) / (1 - A), so I' - B = o * a * (s - B):
    o* in closed form (least squares over the sprite's pixels, clamped 0..1) + the residual. All sums expand into
    correlations of the sprite (a, a*s, a*s^2) with fixed images of the window (I', B, I'*B, B^2): exact, no FFT.
    (3) Per-pixel labels at the best few (pose, p): SEEN (residual <= t), COVERED (front plane opaque, UI, or
    neither sprite nor B: something drawn over it - effects, players), ABSENT (the pixel is B where the sprite is
    opaque and differs from B). A mob = SEEN share >= x and ABSENT share <= y; x, y, t fitted on synth, checked on
    labels.
    (4) Windows: D patches (every type x pose x facing of the map; feet y only on footholds crossing the window,
    +-2 px - flyers: free y) + track predictions (voted type + die poses). Cost: positions ~ window widths x ~3 rows,
    not area: clips' p90 ~127 k px of boxes -> ~2 k x positions x 3 y x 46 poses x ~3 k px ~ 0.8 G MAC as batched
    matmuls (target <= 5 ms p90; flyer maps are the risk).
    (5) Deliverables: the planes + test; perception/fit.py (not wired: 3.3 runs it in shadow); tools/perc/fit/
    (offline: thresholds on synth, report on labels). Gate: synth recall >= 99 % per case, 0 false mobs on the 50
    mob-free frames and on Dangerous Steam's ghost spots, every label class >= today's (3.0a's "before"), ms.
  - **3.2 IN PROGRESS (2026-11-16): accuracy gate met on synth + steam, SPEED NOT - stopped for the user's call.**
    - DONE planes: `assets scene` writes `layers/behind_L.png` + `front_L.png` per foothold layer (rebuilt the 5
      clean maps; scene.png bit-identical); `Scene.split(C, L)` -> B, known_B, F, A; expected() refactored onto
      `_backs` / `_anim` (same output). tests/test_scene_layers.py: F + (1 - A) B = expected() within 1.5 levels
      (two rounded uint8 canvases; kept uint8, fp16 of them = the same numbers). Line 1 / Transfer: 8-10 planes, ~250 MB.
    - `perception/fit.py` (not wired; docstring = the method): positions (ground on footholds +-2; jump poses /
      flyers free y but only where a D blob's lower or upper edge meets the pose's lowest / highest row), D-pruned
      (core-box share of D among valid pixels >= 0.3, integral images), stage 1 = the plan's exact Srq / Sqq (+ Srr)
      by gather + fp16 matmul (cudnn's 75x72-kernel conv: ~3 TMAC/s, 220 ms -> dropped), candidates per window and
      type = best 24 (+4 / 4000 px) by gain + best 12 by explained fraction (faint / covered mobs), <= 6 per 6 px;
      stage 2 per pixel, o = mode of per-pixel ratios; greedy pick. UI: minimap + keycaps masked (unmasked keycaps
      broke stage 1's ranking), the chat rect (630-700) is world at native: unmasked in V and in the tool's D.
    - tools/perc/fit/run.py (synth | labels [--tracks] | ghosts RUN --replay HEAD.jsonl --live), sweep.py (grid /
      score / ghosts; --r X Y match radius; label_eval.py got --r too). Loose runs in RUN/fit/*.jsonl.
    - **synth ant4_500 (rule seen >= 0.03, >= 60 px, absent <= 0.1): 99.5 % (782 / 786), 0 false (0 on the 50
      mob-free frames), wrong type 1**; per case clear / fade / dying / hit / scenery / ui / edge 100 %, player 98.2,
      effect 97.8 (misses: 4 mobs 31-40 % visible, ranked 16th-49th in their window, or seen 82 px under
      semi-transparent digits). sweep: any rule from 0.03-0.08 / 10-200 px / 0.1-0.3 gives 0 false. (sweep's
      dontcare now reaches 80 px below a box: the base frames' unerased real mobs under the chat / HUD.)
    - **Dangerous Steam ghost spots (live run's 85 weak tracks, 266 sightings on saved frames): a fit mob at 2 =
      two REAL Zombie Mushrooms behind a steam geyser (looked at: 1548 px exact); 0 at the 264 scenery spots.**
    - labels 012059_1 (per frame, no memory; before = the tracker WITH memory), r 25 | r 40/30: found 92.0 | 93.3 %
      (before 86.2 | 86.9); clear 96.3 (94.0), fade 91.7 (51.1), ui 80.6 (66.7), edge 93.3 (71.7), scenery 96.1
      (90.2), hit 84.8 (81.8), dying 90.2 (90.2), player 77.5 (75.8), **effect 76.3 (86.4: below - the tracker
      coasts through effects; track windows (3.3) not tried yet: `run.py labels --tracks replay/before.jsonl`)**.
      false 236 (die 54): sampled ones are mostly label offsets of 25-60 px / unlabelled real mobs - unjudged.
    - **SPEED (the blocker): fit ms p50 / p90 - synth 62 / 85, labels frames 116 / 154 (16 windows, 34 k kept
      positions), Dangerous Steam 200 / 279 (Stirge flyers: 867 k positions)** vs the target 5 p90. Profile
      (labels frames): stage 1 gathers 49, Python glue ~45, stage 2 11, positions 11, images 5. s1_step=2 (stage-1
      sums on every 2nd row / column; an approximation, stage 2 stays exact): stage 1 49 -> 21 ms, synth 99.5 %.
      No cupy / triton / nvcc in the venv (a custom kernel = an install: the user's call).
      Options put to the user: (a) s1_step 2; (b) GPU-side selection (kill the Python glue); (c) skip thin
      windows (chat line strips, tags); (d) a custom CUDA kernel (install); (e) track windows first, D windows only
      where no track explains the blob (3.3 design); (f) a looser ms target for the fit.
  - **3.2 speed review (2026-11-17, Fable max; PLAN-fit-speed.md, OK'd by the user the same day).** The user's
    answers that day: label matching at 40 / 30 px for both sides OK; the chat box is kept minimized (memory
    chat-minimized). Speed options (b) + (c) + (e) were OK'd, then the user asked for a review first - its result:
    - they cannot reach the target: the cost is the QUESTION stage 1 asks (every feet position x every pose x 54 k
      values; 34 k positions a real frame, 870 k with flyers), estimated 25-40 ms after (b) + (c) + (e).
    - **Measured (E9, tools/perc/redesign/): native frames show sprite colours EXACTLY** (difference 0 on 98.57 % of
      827 k opaque pixels, the rest covered); palettes are tiny (Horny 77 colours, Zombie 134, Stirge 14) and
      sprites dithered (~1350-1900 non-flat 2x2 blocks per pose); real fades are exact (residual 0 on 90 %, one o
      per mob; respawn waves fade in together); **the blue "hit" mobs are FROZEN mobs = sprite x (B 255, G 168, R
      10) / 255 exactly** (the LS fit accepts them at "seen 17 %" by their black outline).
    - **Proposed search = voting:** palette id per pixel (LUT) -> 2x2 id blocks = features -> a table says which
      (pose, feet) cells a feature allows -> votes -> exclusive votes (a feature counts for its best cell) -> ~4-7
      cells a frame -> the existing stage 2 + pick. Fades: un-blend the residue at the alpha that makes its pixel
      pairs sprite colour pairs, then the same vote. Tints: more palette colours. No windows / footholds / air
      case; the opaque vote needs no scene.
    - **Prototype numbers (exp_vote.py candidates -> today's stage 2 + pick, nothing tuned):** synth 99.5 %, 0
      false, every opaque case 100 % (player / effect were 98.2 / 97.8), fade 96.2 (alpha not refined); labels at
      40 / 30: 94.3 % (LS fit 93.3, before 86.9), clear 97.5, player 90.7 (82.8), ui 87.5 (80.6), scenery 98.0,
      edge 96.7; below the LS fit until built: fade 82.7 (93.2), dying 90.2 (93.9), hit 78.8 (84.8: frozen).
      Candidate search 1.7-3.8 ms p50 whole frame (2.1-2.3 on Line 1 / Steam / Transfer), stage-2 candidates 4-7
      (max 27) instead of ~380-720. Other maps vs today's well-sighted tracks: Bubbling 91.9 %, Stirge 94.7-98.0 %.
    - The plan: 2 Opus sessions (S1-S3 the vote + fit on votes + tools; S4-S6 fades, tints, other maps, close 3.2),
      gates and prompts inside. Not built: anything in maplebrain/ (fit.py is still the LS fit of 7744b1d).
  - **3.2 Session 1 (2026-11-17, PLAN-fit-speed.md S1-S3): DONE; the labels gate as written FAILS - the user's call.**
    All ms pinned to the performance cores (procperf; run.py does it now: unpinned from the background the vote read
    ~3 ms instead of 1.5), game up, expected() not counted (D's; 1.8 / 2.3 ms).
    - S1 `perception/vote.py` (`load_poses` follows `_inlink` / mob `link` placeholders; `Voter.ids` / `cells`):
      cells IDENTICAL to E9 on 300 / 300 labels frames. Ant Tunnel IV: 46 poses, 198 colours, int32 mixed-radix keys,
      75.5 k entries / 19.9 k keys; features with D's raw mask (|I - exp| > 4 or unknown) p50 16.7 k (all pixels 71.7
      k); 3 syncs; run lengths by sort + index_add (cummax / cummin were 0.6 ms). **Vote 1.53 / 2.12 ms p50 / p90 on
      the labels frames (gate 2.5 p90: met).** tests/test_vote.py: every opaque fixture mob's cell (or its identical-
      picture alias) >= 24 exclusive votes, no scene.
    - S2 `perception/fit.py` rewritten: candidates = cells >= cand_votes -> stage 2 (B = expected, valid = known & ui &
      the mob layer's front alpha < 0.5 (+ front backs' cover); layer = nearest foothold at / below the feet, flyers
      the lowest spawn layer) -> pick. LS stage 1, positions, windows, s1_step / prune / top / near / margin / fh_dy
      deleted. Stage 2's ~60 GPU ops run as CUDA graphs (buckets 8 / 16 / 32 / 64 candidates, padded): 1.5 -> 0.56 ms
      p50, mobs identical to eager on 300 / 300 frames.
    - S3 tools/perc/fit/run.py (no windows, `clip` mode for timing, --loose seen 0.02 / cand_votes 8) + sweep.py
      (cand_votes in the rule / grid). **Re-fit: seen >= 0.03 / >= 60 px / absent <= 0.1 (as before) + cand_votes 16
      (the plan said 24: on synth 24 loses n446, a Horny Mushroom 39.5 % visible under an effect - D's mask drops its
      pixels equal to the scene, 25 -> 16 votes; 12-48 all 0 false).**
    - **synth ant4_500: every opaque case 100 %** (clear / dying / hit / scenery / ui / edge / player / effect; LS:
      player 98.2, effect 97.8), **0 false, 0 on the mob-free frames**, wrong type 0; fade 0 of 105 (no fade path
      until S4) -> all 86.6 %.
    - **Dangerous Steam ghost spots: 0 at the 264 scenery spots**; 2 = the two real Zombie Mushrooms behind the geyser
      (1548 px exact), as the LS fit.
    - **fit ms p50 / p90: labels frames 2.60 / 3.21 (gate 4: met)** [vote 1.66 / 2.19, stage 2 0.56 / 0.80, pick 0.25 /
      0.43; candidates 6 / 14], synth 2.43 / 3.10, Dangerous Steam whole clip (930 frames, flyers) 2.64 / 3.41, its
      ghost frames 2.63 / 3.15. LS fit re-run on the labels frames: 119 / 160.
    - **labels at 40 / 30 px, vote vs LS (7744b1d re-run with the same rule; RUN/fit/labels_ls.jsonl):** all 82.0 vs
      93.8; clear 92.6 / 96.8, player 80.2 / 85.0, effect 84.2 / 81.4, ui 75.0 / 84.7, edge 85.0 / 96.7, scenery 90.2 /
      96.1, hit 72.7 / 84.8, dying 56.1 / 93.9, fade 1.5 / 93.2 -> **"non-fade classes >= the LS column" FAILS.**
      Why: **191 of the 1547 labelled mobs are FADING** (E9 finds them only by a fade cell: respawn waves at alpha
      156-246, labelled clear / player / ui / edge - by eye a 0.98 mob is clear); the LS fit's opacity search takes
      them, the opaque vote by design not (S4). Misses of the non-fade classes: fade cell 93, no cell on either path
      62, D's mask 0, stage 2 rejected 2. **On the 1356 NOT fading: all 93.5 vs 93.3; clear 97.4 / 96.7, player 89.7 /
      84.2, effect 86.1 / 80.9, ui 85.7 / 85.7, edge 96.2 / 96.2, scenery 97.9 / 97.9, hit 77.4 / 83.9 (= 2 FROZEN
      mobs the LS fit takes by the outline at seen 0.16 / 0.17: S5), dying 85.2 / 92.6 (die frames fade: S4).**
      False (unjudged labels): vote 121, LS 436.
    - pytest green (+ tests/test_vote.py); bot speed 21.8 ms (p90 25.2; baseline 18.4 - the D-on state of 3.1, which
      read 22.3; no live code changed: nothing live imports vote.py / fit.py).
    - ACCEPTED by the user 2026-11-17 ("yes"): the labels gate on the not-fading subset for Session 1; was asked: accept it on the not-fading subset for Session 1 (the full classes are S4 /
      S5's gate), or another call. The comparison: `tools/perc/fit/subset.py` (E9 fade cells cached in
      RUN/fit/fading_e9.json; the LS rows from 7744b1d's fit.py + run.py via git show).
  - **3.2 Session 2, S4 fades (2026-11-17): DONE (b39503a). ACCEPTED by the user the same day: (A) one alpha per
    cell, no cap a frame + the 1 / o tolerance replace "at most 2 alphas a frame"; (B) the fade pass stays at ~1.7 ms
    p50 (no CUDA graphs, no spot restriction): the gate is the whole fit <= 5 ms p90 incl. fades (S6). NEXT = S5.**
    All ms pinned, game up, expected() not counted (D's).
    - **Design point (c) "at most 2 alphas a frame" is wrong on synth:** 34 of the 50 synth fade frames hold 2-3
      fading mobs at different opacities; 18 of the 105 fading mobs are beyond their frame's top 2 alphas -> ceiling
      82.9 % (measured 77.1 % with (c)). Built instead (PROPOSED): ONE alpha per 48 px cell (its own refined o; a
      cell without one takes its 3x3 neighbourhood's best), no cap a frame; the residue un-blended at its cell's
      alpha goes into the SAME id picture as the opaque ids -> one vote (`Voter.fade`, fit.py `me` = our body box
      from obs.me, kept out). Constant cost however many fades are on screen.
    - **The +-2-level un-blend misses faint fades** (o ~0.1-0.27, |I - B| max 32-67: rounding x 1 / o, and step 3
      is coarse at low alpha): labels fade 87.2 / dying 89.0 / edge 95.0 with it; the 9 mobs the LS fit has and the
      vote didn't were all such (E9 misses them too). Fix (tuning of the plan's "+-2"): LUTs at +-2 / 3 / 4 / 6
      levels, picked by o (need 1.5 + 0.5 / o; `Voter.FADE_TOLS`), indexed b + 258 g + 258^2 r with channels clamped
      to -1..256 (the range check is the table's border); 4 x 34 MB GPU.
    - **Gates now:** synth ant4_500 **786 / 786 = 100 %, fade 105 / 105 (o < 0.3: 16 / 16, o >= 0.3: 89 / 89), 0
      false, 0 on the mob-free frames**, wrong type 0; labels at 40 / 30, FULL classes, vote vs LS: all **95.2** /
      93.8, clear 97.6 / 96.8, player 90.3 / 85.0, effect 86.4 / 81.4, ui 87.5 / 84.7, edge **96.7** / 96.7,
      scenery 98.0 / 96.1, **dying 93.9 / 93.9, fade 93.2 / 93.2** (gates met), hit 78.8 / 84.8 (frozen = S5); false
      (unjudged labels) 156 / 436. Dangerous Steam ghost spots: 0 at the 264 scenery spots (2 = the real Zombies
      behind the geyser, as before).
    - **ms: fade pass 1.65 / 1.86 p50 / p90 (synced, labels frames; gate <= 1 / <= 3: p50 MISSED)** = residue 0.15
      + pairs 0.25 + alpha search 0.86 + un-blend 0.38. Launch-bound (~60 small ops at ~15 us; the fused
      un-blend / integer key / cached grids moved it 1.95 -> 1.65 only). Residue on these frames p50 53 k px,
      strong pairs (quarter) p50 4.1 k / p90 12 k. Whole fit incl. fades: labels 4.12 / 4.63, synth 3.99 / 4.87,
      Dangerous Steam clip (930 frames) 4.06 / 4.81 (S6's 5 ms p90: met so far). Plan lever 1 (restrict to dying
      tracks / spawn points) cuts pairs, not launches, and synth draws fades anywhere (its gate would need new synth).
      Options put to the user: (A) CUDA graphs for the alpha search + un-blend (bucketed by pairs / residue, as
      stage 2; est. ~1.0-1.2 ms), (B) accept ~1.7 ms (the fit stays <= 5 ms p90), (C) lever 1 anyway.
    - Tools: run.py passes `me` (ticks.jsonl obs.me; synth: the base frame's), prints fade ms / pairs; `--set
      fade_report=1` lists the cells' alphas; `Voter.prof` = synced per-part ms (fade_ms).
    - pytest green; bot speed 21.1 ms (p90 24.0; Session 1 read 21.8; nothing live imports vote.py / fit.py).
  - **3.2 Session 2, S5 tints (2026-11-17): DONE, every gate met.** All ms pinned, game up, expected() not counted.
    - **Rounding measured** (exp_tint.py now prints it): frame = round(s m / 255) per channel, m = (B 255, G 168, R 10),
      on 8299 / 8299 opaque pixels of the 3 measured mobs (floor 81-93 %, >> 8 67-87 %). `vote.TINTS` + `vote.tinted`.
    - **Built as the plan says:** tinted palette colours = extra LUT entries of the SAME ids. The tint merges colours
      (R x 10 / 255): Ant Tunnel IV 198 -> 158 (40 groups of 2, 38 % of the opaque pixels), Line 1 9 groups,
      Stirge none; a merged colour maps to the group's most frequent id (a block of such pixels may key wrong; a
      frozen mob still gets 800-1700 exclusive votes). Stage 2 tries every candidate with the plain AND the tinted
      sprite, the variant with the most SEEN stays -> `FitMob.tint` ("" / "frozen"); `FitConfig.tints`.
    - **labels at 40 / 30, FULL classes, vote vs LS:** all 95.6 / 93.8, clear 97.6 / 96.8, player 90.3 / 85.0,
      **effect 88.7** / 81.4 (gate 88.7), ui 87.5 / 84.7, edge 96.7 / 96.7, scenery 98.0 / 96.1, **hit 90.9** / 84.8
      (gate 84.8), dying 93.9 / 93.9, fade 93.2 / 93.2; false (unjudged) 158 (S4 156), wrong type 16. 8 frozen mobs
      found (seen 0.91-1.0), the 3 measured ones among them, feet within 1 px.
    - synth ant4_500 786 / 786, 0 false, 0 on the mob-free frames; Dangerous Steam ghost spots 0 at the 264 scenery
      spots (2 = the real Zombies behind the geyser).
    - **ms p50 / p90: labels fit 4.26 / 4.78** (S4 4.12 / 4.63; stage 2 0.65 / 0.89 was 0.56 / 0.80: twice the
      candidates), synth 4.13 / 4.68, steam ghost frames 4.27 / 4.85.
    - **Unknown tints are logged, not guessed:** `tools/perc/fit/tintlog.py` (`run.py ... --tint-log`): residue
      blobs no fit mob explains whose silhouette matches a pose (IoU >= 0.6) -> crop + row (colour-map share, per-
      channel a / b). Check with the tint OFF: 4 of the 8 frozen mobs logged with the exact multiplier (1.00 / 0.659
      / 0.039), 0 of the other 361 blobs look like a colour map (share p90 0.25: players, effects, covered mobs); the
      other 4 merged with neighbours (wrong alignment) or were taken plain at seen 0.13. Tint ON: 0 unknown tints
      on the 297 frames.
    - Tests: test_vote.py (rounding; every pose frozen on a blank frame gets its cell), tests/test_fit.py (S6).
      pytest green; bot speed 23.5 ms (p90 26.4) - WRONG STATE: a stale tool run of mine was still running beside it
      (found later in S6); clean re-run 20.1 ms (p90 23.0).
  - **3.2 Session 2, S6 (2026-11-17): STOPPED at the ms gate - the user's call.** All ms pinned, game up, clean
    state (no other job), expected() not counted (D's).
    - **FIXED (as the plan says, "flyers: their spawn layers"): a flyer was always put on the LOWEST of its spawn
      layers**, so a Stirge flying on a higher layer had all its pixels under that layer's front plane (Transfer
      Area: spawns on layers 5 / 2 / 4, the bricks of layer 5 in front of layer 2; frame 126: 312 votes, SEEN 0 on
      layers 1-4, 645 / 645 on layer 5). Now every spawn layer is a stage-2 variant (with the tints); per cell the
      most SEEN wins, ties -> the lowest layer (SEEN only grows with the layer: this = the lowest layer that leaves
      every matching pixel uncovered). Steam ghost spots still 0 (2 = the real Zombies); labels / synth unchanged.
    - **Fit vs today's well-sighted tracks** (gate replays fp_08bcbe1bd1_*, live / dying, sighted, score >= 0.9;
      `tools/perc/fit/tracks.py`): same type within 20 px | any type:
          ant4 96.1 | 99.9 %   ant4b 96.8 | 99.8   steam 98.2 | 99.7 (was 91.6 before the flyer fix)
          line1 (Bubbling) 99.9 | 99.9   transfer 99.3 | 99.3 (was 93.8)   darkcave 100 | 100      -> gate 95 % MET
      **"Another type there" = the TRACKER's type wrong** in every one looked at (4 / 4: a blue spiky cap tracked as
      Zombie, the game's own "Zombie Mushroom" label over a track typed Horny, a Horny tracked as Stirge with anim
      "move"; steam 1668: the fit has both the Horny and the Stirge the track mixed up).
    - **20 misses by eye** (sheets RUN/fit/misses_clip_<clip>[_other]/): tracker type wrong 6; UI mask 4 (the tool's
      STATIC ui: `UI_RECTS`' top-right rect 1140-1366 x 45-160 masks world where no buff icon is drawn - steam 456,
      transfer 1290 / 1383 (that one has an icon) - and the default minimap rect instead of the measured one -
      transfer 150); flyers over ANIMATED scenery (unknown pixels -> not valid -> SEEN 0: steam 558 / 879 / 993,
      1635 likely) 4; fades the fade path missed 4 (ant4b 6759 at o 0.955, 6873, transfer 687 / 690); dying tracks
      with nothing / a splash under our body box 2 (line1); two overlapping Hornies under name labels beside us 1;
      flyer layer (fixed) 2.
    - **ms p50 / p90 per gate clip (every frame with a scene camera) - GATE <= 5 p90 FAILS on 4 of 6:**
          ant4 4.60 / 5.47   ant4b 4.36 / 5.16   steam 4.25 / 5.13   line1 4.46 / 5.37   transfer 3.86 / 4.76
          darkcave 4.17 / 4.64   (labels frames 4.14-4.26 / 4.78-5.06 run to run; synth 4.13 / 4.68)
      parts p90 on ant4: vote 2.34, fade 2.27, stage 2 1.13, pick 0.43 (candidates p90 15, features p90 25.7 k).
      Levers: (A) CUDA graphs for the fade pass (S4's option, est. -0.6..0.8 ms p90); (B) stage 2's variants: a tint
      flag from the vote instead of trying every candidate tinted (-0.2), flyer layers in one pass; (C) accept ~5.5.
    - Thresholds by sweep (synth loose): 100 % / 0 false on seen 0.03 x min_seen 10-60 x absent 0.1-0.2 x
      cand_votes 12-16: the rule stays.
    - tests/test_fit.py (fixture recall 100 %, 0 false, mob-free clean, clear mobs' pose + feet exact; a frozen mob
      of every 3rd pose found with tint "frozen", pose + feet exact). Dead LS code: none left in the fit;
      `Scene.split` (+ the behind_L planes it reads) is used only by tests/test_scene_layers.py now - scene.py is a
      live module, left for 3.3 to decide.
    - **The user's call 2026-11-17: the ms ACCEPTED as is ("note option A for later if needed, and proceed with
      plan"). 3.2 CLOSED.** Context given: today's bench 20.1 ms (~50 fps, no fit); estimated 3.3 (both matchers)
      ~24.5 ms ~41 fps; 3.4 (the fit replaces search + refine 9.7 + find_near 6.3 p50 / ~20 p90) ~9-11 ms p50 =
      ~90-110 fps uncapped - the 60 fps cap is reached with the fade pass as is.
    - **TODO LATER (only if needed): option A = CUDA graphs for the fade pass** (Voter.fade; bucketed by pairs /
      residue like stage 2's graphs; est. 1.65 -> ~1.0-1.2 ms p50, -0.6..0.8 ms fit p90). Also open: (B) a tint flag
      from the vote instead of trying every candidate tinted (-0.2 ms).
  - **3.3 PROPOSED (2026-11-17, waiting for the user's OK): the fit in shadow in the Perceiver.** Nothing reads it;
    the tracker keeps today's detector; brain / keys unchanged.
    1. Wiring (perceiver.py, where D runs - scene camera found, `scene_diff` on): ONE `expected()` per tick shared by
       D and the fit (`Scene.diff` takes / returns exp + known); `Fitter` built with the Scene at map load (measure
       its build time; a thread if > ~0.5 s); ui = D's mask (the measured minimap) + the chat rect as world (memory
       chat-minimized); `me` = our body box from obs.me; config `perception.fit` (default on).
    2. FrameFacts v3: `fit` = [FitMob dicts] (None = not run this tick) + `fit_ms`; v1 / v2 records still read.
    3. Hints: each live track the fit did not find gets ONE stage-2 look at its predicted feet with its type / last
       pose (+ die poses if dying) -> SEEN / ABSENT / COVERED counts in FrameFacts `fit_hints` (step 4's evidence;
       nothing reads it). Same CUDA-graph buckets.
    4. Measure: bench A/B fit off / on (same state; then the user decides the re-baseline); tick p50 / p90 + the
       fit's part; gate replay of all 7 clips: tracks the SAME (compare.py) + per clip the fit vs the tracker frame
       by frame from the replay's own rows (tools/perc/fit/tracks.py logic: >= 95 % same type, the S6 numbers within
       noise) + hint shares on the tracker's unseen / coasting frames (how many coasting tracks the fit calls ABSENT
       = step 4's input).
    5. Decide at 3.3 (proposals): drop `Scene.split` + stop loading the behind_L planes (only front alpha is used;
       GPU memory on Line 1 / Transfer) - the planes test reads them from disk; `UI_RECTS`' top-right rect (1140-
       1366 x 45-160) masks world where no buff icon is drawn (S6: 3 Stirges) - keep (safe) until step 5's UI work.
    Gate: pytest + the speed line; full gate.py: tracks identical on all 7 clips; fit-vs-tracks per clip as S6; the
    tick +<= ~5 ms p50 over the D-on state (A/B); no live behaviour change. Live: the user's optional short `serve
    --observe` recording to read the fit's ms on live ticks.
- Still open from 2026-11-15: merge `dev` (v3 steps 1-3 + the F9 fix) into `main` (the user merges).

### ROADMAP (agreed 2026-11-15, the user: "lets start with perception improvement (and then data model)")
Main line = the scripted v3 brain, made human by analysis of the user's recordings; a human-vs-bot CLASSIFIER is the
referee that decides whether learned parts are needed. Why: "UPDATE later the same day" + the discussion summary at
the end of this list.
- **Phase 0:** merge `dev` -> `main` (the user). Optional: the 1366x768 window A/B (TODO below).
- **Phases 1a + 1b below are SUPERSEDED by PLAN-perception.md (2026-11-16)**; kept for the reasoning.
- **Phase 1a speed, 16 -> >= 30 fps:** profiling review first (offline on tests/fixtures/perf_ant4 + recorded runs:
  where the ~58 ms tick goes, per part and per line, ranked fixes with expected savings; GPU ~15 ms of it, the rest
  CPU in series) -> S1 CPU parts in threads beside the GPU -> S2 self-tag / camshift / resize on the GPU (GpuNCC
  exists), frame uploaded once -> S3 HUD / LD / minimap at ~4-5 Hz -> S4 tracker re-check at the new fps. Gate:
  bench tick p50 < 33 ms (re-baseline on purpose), tracker replay same or better (rebuild the old-vs-new replay as
  tools/perc/ - it was never committed).
- **Phase 1b accuracy:** A1 mask our body + pet, A2 dying-mob association on the whole-screen path, A6 speech bubbles,
  A3 HP bars, A4 effect-robust scores, A5 hit time per weapon (details in P2 below). Gate: label_eval.py, bot_presses
  solid share 69 % -> >= 85 %, 3-min live check with marked frames.
- **Phase 2 recording data model:** versioned per-tick schema from the v3 World (us: pos, ground/rope/air, facing,
  HP/MP, platform + edge distances, nearest rope dx/dy; N nearest mobs relative + state; goal + task; perception
  quality; frame index) + RAW key events (down/up timestamps, injected flag) + run metadata (map, weapon, attack
  speed, resolution, party, code version). One recorder for bot runs and `serve --observe`; Parquet per run, loader,
  validator; convert the old 27 min where fields allow. Must allow labelling the user's play AFTERWARDS with tasks
  (next mob hit = target, platform arrived on = destination, link used = move). Design together with v3 step 4
  (memory). Gate: round-trip tests, old runs converted, a per-recording sanity report.
- **Phase 3 recordings (the user):** polearm, Ant Tunnel IV, 15-30 min sessions, varied (crowded / quiet, solo /
  party), later 1-2 maps; bot runs of the same setup; ~1-2 h for phase 4; quality check after each session.
- **Phase 4 humanness report + classifier:** per-feature user vs bot with 2-sample tests, ranked (press / hold per
  key, presses per swing, gap rhythm / autocorrelation, reaction in-reach -> press, turns, overlaps, idle gaps,
  breaks). Classifier human vs bot on 1-2 s windows of key events + context: gradient boosting on features, then a
  small GRU on raw events; split BY SESSION; same map / setup on both sides; control = user session A vs B (~50 %
  = the floor). Output: held-out accuracy, features used, most-certain windows drawn as key timelines.
- **Phase 5 loop:** top difference -> rule / sampled distribution / correlated timing process -> sim gate (kills,
  clean kills, stuck unchanged) -> bot run -> classifier again. Plateau above the floor -> learned parts there,
  narrowest first: conditional timing models, then movement BC conditioned on the v3 task (planner + targeting +
  Travel still decide WHAT and WHERE; the model only replaces moves.py's key output), scripted shield + scripted
  brain as DAgger expert. Exit: near the floor, kills / clean kills not worse.
- Alongside: v3 steps 4-6 (memory, Auto, Path), M2 loot / buff.
Discussion summary (2026-11-15): a smart state machine can plausibly fool players, server statistics and simple
timing checks; a dedicated sequence classifier probably still beats it above chance (small per-window gaps add up
over hours - true for BC too); the strongest signals are not behaviour (SendInput's injected flag, the process /
hook / capture: LDs started at `serve --observe` with no keys) and neither approach touches them - no evasion.

**Platform mode live test, 2026-11-15, Ant Tunnel IV, local client (`serve runs\v2 --brain v2 --mob-score 0.70
--frames`) - PASSED ("perfect platform mode test"):**
- `runs/v2/20261115_015200_1` (40 s): marks 364 (y 1560) + 399 (y 1712); moves between them both ways (jump up /
  drop), off the area 2x (on 417, a route crossing) and back after 2-3 s.
- `runs/v2/20261115_015246_2` (3.2 min): marks 168 + 364 + 399; 21 kills by last hit (6.6/min), 3.5 swings / kill,
  962 EXP (18,080/hour); off the area 13x (417 / 373, between the marks), back after 1-8 s every time, the leash
  (36-42 s) never ran out; tick p50 31 ms.
- First try `runs/v2/20261115_013124_1`: only 168 got marked -> **bug, FIXED (uncommitted at writing):** the first
  F9 on a map loads it (17-21 s live: recognition + sprites + GPU warm-up); hotkeys aren't polled meanwhile (a 2nd
  F9 is lost) and the platform was read AFTER the load (where we stood then). Now `_mark_here` grabs the frame at
  the press (`_platform_here(rig, say, frame)`), and a mark taking > 2 s says "an F9 pressed meanwhile was NOT seen
  - press it again". Test: tests/test_runner.py `test_mark_reads_the_platform_from_the_frame_at_the_press...`.
  Usage: on the first F9 per map, stand still until the chirp.

**Direction review, 2026-11-15 (the user brought a proposal from another AI: utility behaviour tree at 15 Hz +
imitation-learning micro policy at 60 Hz with action chunking + "biomechanical" key timing). Outcome: keep v3.**
- Its macro half = what v3 already is: Blackboard = v3/model.py World; utility BT root = Planner + Goals (scored
  terms); survival = Reflexes; anti-stuck = Travel; MemSequence = Task.can_cancel.
- The learned micro layer: declined again (as in sessions 20-21; M5 stays optional, movement only): the tick is ~30-60
  ms (no 60 Hz), one 18.5-min recording of the user (spear, Line 1) vs today's polearm / Ant Tunnel, and it would
  replace per-press combat (the best thing built).
- **The user challenged "the server never sees finger-level timing" - rightly:** movement packets carry per-segment
  durations, attacks carry timing, the server knows reaction times to spawns; the client-side anti-cheat sees every
  key event. Plus: LDs began on `serve --observe` start with no keys sent. So input realism plausibly matters.
- Today only combat gaps use the user's measured deciles (`Humanizer.pick`); everything else is nominal +-25 %
  (triangular) + tempo drift; key overlaps, holds while walking, reaction delays are not modelled or compared.
- **Offered (not answered): humanness report** - tool comparing a bot run's keys.jsonl vs the user's keylog per
  feature (press / hold length per key, attack gaps, reaction from in-reach to first press, overlaps: attack while
  walking, turn while holding the other way, idle gaps, running jumps) with a 2-sample test -> a table of where the
  bot differs; then replace the worst nominal timings with measured distributions (= M4 pulled earlier); record
  1-2 more sessions of the user with the polearm on Ant Tunnel IV.
- Small ideas from the proposal worth taking (logged, not built): softmax + noise on roam / zone choice (a score
  term with a temperature); potion thresholds drifting over a session (Reflexes parameter; today HP 50 % / MP 10 %).
- **UPDATE later the same day (a 2nd proposal: utility AI + GRU behaviour cloning at 30 Hz, relative-geometry state,
  recovery dataset):** the user: "the goal is the knowledge and the software, not the game itself"; mistakes and
  reports are no factor; they will record the data once perception is good and a proper data model stores it. So the
  learned motor layer is now a REAL milestone (not "M5 optional"). Order: perception (speed review first, then
  accuracy) -> recording data model (versioned schema from the v3 World snapshot + goal / task; RAW key events with
  timestamps, not only a 30 Hz held grid; the same schema for bot runs) -> the user records -> humanness report as
  the eval harness -> learned layer conditioned on the v3 task (movement first). Testing a learned policy: seeded
  replayable runs, statistical gates (offline per-key / timing tests vs the user; sim kills, clean kills, stuck,
  falls vs the scripted baseline), a scripted SHIELD that vetoes (no press after a death, progress watchdog ->
  scripted moves) and logs each veto, model probabilities in ticks.jsonl next to the scripted choice, and the
  scripted brain as the DAgger expert in the sim (it labels any state: "what"; the user's data: "how"). Not built:
  no virtual-HID / injected-flag hiding (stays SendInput).

### TODO (later): game window at native 1366x768 (the user, 2026-11-15)
The user plays at FHD now (1920x1080; earlier 2560x1440). The game lays the world out on a 1366x768 logical screen
(client sprites match our normalized frame at file size, minimap canvas 1:1, a fixed 16:9 picture pillarboxed on
3440) and stretches it to the window; `capture.normalize` shrinks it back -> every frame resampled TWICE (blurred
sprite edges vs the 1:1 client templates; ghosts 0.57-0.68 vs real 0.80-0.98 is a narrow gap; the minimap sub-pixel
jitter `localize.py` works around). Speed is NOT the reason: resize 2560x1440 -> 1366 = 1.7 ms, FHD 1.3 ms; live
grab + resize p50 4 ms of a ~58 ms tick (`runs/v2/20261115_015246_2`).
- Setup: WINDOWED, client area exactly 1366x768 (not borderless = stretched; not exclusive fullscreen = mode switch,
  dxcam trouble). Windows display scale 100 % (125 % may DPI-stretch the window). Never below 1366x768.
- Checks: the run log's `game picture at x (a, b)` spans exactly 1366, height 768; the view shows exactly the same
  part of the map as FHD (if not, the "renders 1366x768 and scales" assumption is wrong - stop and look). Not settled:
  whether the game renders a 1366 image and stretches it or draws sprites stretched into the window (its own
  screenshots `C:\Nexon\Library\maplestorycw\appdata\Maple_A_*.jpg` are saved at window size; a blur test on them was
  inconclusive, JPEG).
- A/B: 1-2 min `serve runs\play --observe --gpu --tracker --frames` on Ant Tunnel IV at 1366x768 (no keys) -> detector
  scores of real mobs vs weak hits / ghosts against FHD + 2560x1440 frames of the same map. Better -> the standard setup.
- If adopted: `tools/perf/bench.py` assumes `SCREEN = (2560, 1440)` -> set (1366, 768) and re-baseline on purpose;
  `normalize` could skip the no-op resize.

**2026-11-15: back to the local game process (capture + SendInput as before). The VM experiment is parked on branch
`vnc-keys` only (never on `dev` / `main`). `dev` = `v3` = steps 1-3; `main` NOT updated.**
**2026-11-09 (branch `v3` off dev 02a639a): steps 1 + 2 DONE, gate identical; step 3 (Platform mode) BUILT +
sim-tested, NEXT = its live test** (the user positions the character on a map they OK, F10 -> platform, F9 on 1-3
platforms, F7). Decisions + how it works: PLAN-v3.md "Platform mode as built". New: runtime/marks.py, F9 / F10 in
`Keys`, v3/goals.py HuntArea (fence + fight back + 36-44 s leash), v3/tasks.py Back, Trips.area_goal, Targeting
`area` term, livemap `*` = marked. tests/test_v3_area.py (sim, Line 1). Auto mode still gate-identical.
- **Sim harness bug found (NOT fixed, kept for the gate):** nav/sim.py only knows a key named "jump"; the brain
  presses `shift` (Trips' keymap) -> in tests/test_brain_v2.py `_hunt` (and so the gate seeds) running jumps and
  drop-throughs NEVER happen (jump links time out, get blacklisted; e.g. 244 -> 285 on Line 1). test_v3_area
  translates the key. Fixing `_hunt` = a deliberate gate re-record: ask the user.
- Gate: `python tools/v3/gate.py` (sim seeds 1-8 x 180 s + agree.py on runs/play/20261105_000802_1) vs
  tests/fixtures/v3_gate.json, recorded on dev BEFORE any change (`d4f73f3`); `--quick` = seeds 1-2 x 60 s, also
  tests/test_v3_gate.py on every pytest. Re-record (`--record`) only on purpose. Proven to catch a 0.5 -> 0.45
  keep margin (names the 10 s where it starts).
- Step 1 `9c1957b`: brain/v3/model.py (world model: Mob, Map + Spawn + route seconds, Character = SelfState +
  Facing + HUD + hands, World) - the v2 parts read these. Step 2: brain/v3/planner.py (Goal / Task contracts,
  Planner: goal ~1x/s + on events, own rng seeded without drawing from the brain's), v3/goals.py (Hunt = the old
  chain), v3/tasks.py (Fight / Fight finishing / Goto / Roam / Rest). The goal names its task EVERY tick (combat
  needs it; PLAN-v3.md's sketch said only when due); every task can_cancel at once (as the chain did).
- Bot speed 59.4 ms vs 59.6 (brain 0.1 ms). NOTE: with `serve` + `watch` running it reads ~85 ms (test_perf fails):
  stop them before judging speed.
- Edit-tool gotcha: a new_string ending in a space loses it (`near =lambda`, `Map(line1),Humanizer`): check.
Original task:
Read **PLAN-v3.md** first (layers, contracts, gates). P1 = its migration steps 1-3, in order, on a NEW branch off
`dev` (e.g. `v3`; `main` = last good, the user merges):
1. **Objects:** Map / Platform / Mob / Character wrap today's parts; the brain reads them instead of dicts. Record
   the baseline BEFORE any change; gate: sim 8 seeds x 3 min + `tools/combat/agree.py` match it EXACTLY (as the
   session-23 restructure did).
2. **Planner:** the Goal / Task contracts; one goal `Hunt` = today's chain moved into Fight / Goto / Rest tasks.
   Gate: the same, behaviour identical.
3. **Platform mode (`HuntArea`):** `serve ... --mark-platform`, F7 = a no-keys marking phase; F9 (new key in `Keys`)
   marks / unmarks the platform we stand on (chirp + log line); livemap draws the marks; marks per session only
   (nothing saved); then hunting: targets only on marked platforms, moving between them to the highest-priority
   target, routes may cross unmarked ones, back to the nearest marked platform when knocked / fallen outside. Close
   the roam gaps listed in PLAN-v3.md. Gate: sim on Line 1 with 2-3 marked platforms (never a target outside, always
   back after forced drops), then a live run (the user positions the character and OKs the spot).
**Ask the user at the start of step 3** (PLAN-v3.md open decisions): whole platforms or x-ranges on long ones; marks
kept across F8 -> F7 within one serve; swing at mobs in reach on the way back, or not.
Keep while doing it: per-press combat untouched (Fight = today's Weapon + Footwork); the `bot speed` line after every
pytest must not move (the brain is 0.2 ms of the tick today); each file's header states its layer and step.

## P2 (after Platform mode): accuracy + speed (2026-11-08, after the per-press live run; the user: "the most
## significant change in bot behavior since start, so much more accurate and lethal")
**Branch state (2026-11-09):** `main` = `dev` = 5998a33, pushed. Commits of the per-press session (2026-11-08):
`4f31e36` attack per press (one press per swing, next decided after the swing; swing length from the client,
`--attack-speed`, default weapon poleArm) -> `bda9f6d` live check (`runs/v2/press1`, `probe/bot_presses.py`) ->
`939a189` this plan -> `a375cae` speed regression test. 1107 tests green. Details of the per-press work: the section
"attack per press" below (steps 1-2 DONE, step 3 = A1-A4 here).
**Rules learned this session:** no scripted / probe input in a populated map - check the screen and get the user's OK
for the spot first (memory "no scripted input in public": the Ant Tunnel probe got the user reported). Live tests
of normal hunting on Ant Tunnel IV are fine after the user's OK.

**The speed regression test (S0 below) - how to use it:**
- Every `pytest` run (the venv: `..\auto-maple\.venv\Scripts\python -m pytest`) ends with a `bot speed` section:
  `bot speed (replay, 40 frames): 15.8 fps, tick 63.1 ms (p90 73.6) = resize .. + perceive .. [gpu .., hud .., world
  .., self .., camshift .., locate .., scene ..] + brain .. | baseline 16.8 fps, tick 59.6 ms (2026-11-08)`.
  Look at it after EVERY change: it says "N % slower" past 10 %, "FASTER ... re-baseline" past 15 %.
- `tests/test_perf.py` FAILS when the tick median > baseline x 1.25 + 2 ms, or any part's median > its baseline x 1.5
  + 3 ms (message names the part). A failing first try is measured again (the game may hold the GPU); the faster
  counts. Skipped without CUDA / torch, without the fixture, or on a machine with no baseline (the baseline stores
  `machine` = host + GPU name; another PC needs its own `--baseline`). Takes ~20 s.
- It runs `tools/perf/bench.py --json` in its OWN process (inside pytest, after the other GPU tests, it read ~17 %
  slow). Standalone repeats agree within ~5 % (59.6-64.8 ms seen).
- After a deliberate speed change (S1-S3, or a new perception part worth its cost): `..\auto-maple\.venv\Scripts\python
  tools\perf\bench.py --baseline` (rewrites tests/perf_baseline.json) and commit it with the change.
- Bench any recorded run: `bench.py --frames runs/v2/press1/frames --map 10005063 --n 200`. The fixture
  (tests/fixtures/perf_ant4, 45 JPEG q85 frames, 7.8 MB, SOURCE.txt) is a fight stretch of press1 (t 40.8-49.2 s);
  the first 5 frames are warm-up. NOT measured: the dxcam capture itself, the key driver thread, ticks/frames writing.
- Live: every v2 run's log.txt now ends with `speed: tick p50 .. ms (.. fps), p90 ..; perceive parts p50 [..]`
  (hunt_v2.speed_line) - compare with the replay; live adds the capture and the game's own GPU load (press1: 58 ms).
- Already visible: in the fight frames the HUD read costs 12-13 ms per tick (run average 4) - an S3 candidate.

Where a tick goes (`runs/v2/press1`, median 58 ms = 16 fps, p90 72, p99 119): grab+resize 11, perceive 47 = gpu 15 +
world (tracker) 10 + self tag 7 + camshift 6 + hud 4 + scene 3 + locate 2; brain 0.2. The GPU is a quarter of it; the
rest is CPU work run one after another. 16 fps costs LATENCY (gap after a swing 0.25 s vs the user's 0.09; turn 0.5 vs
0.36) but the biggest error is EVIDENCE: 22 of 59 presses at weak tracks (our own body / pet, a dying mob's spot).
Accuracy (offline first on press1 / react1 frames, `bot_presses.py` + marked frames as the check):
  A1. No mob detections on our own character + pet: mask our box (known from the tag) in the detector.
  A2. A detection on a dying track's spot belongs to that track (association), never a new live track. 2026-11-09:
      the near-search path is done (world.py rule (1): such a hit needs the mob score). STILL OPEN for the
      whole-screen path: `runs/v2/air1/fix3` #154 born at 108.0 s at 0.658 (just over 0.65) on the fading body of
      dying #151 under our swing's blue arc, then followed at 0.55-0.61 onto our polearm blade: 3 presses at nothing
      (`fix3/weak154.png`, `weak154_zoom.png`). Idea: a live-pose hit within the dying track's box during its death
      animation joins it unless >= confirm_score 0.75. Cost to check: press1 174.5 s, a real Horny Mushroom walking
      in right behind a dying one (0.575 there) is then picked up later.
  A3. HP bars on with sprites (find_mob_bars; check the Perion fog case): a bar emptied by our hit = the kill ~0.25 s
      before the death animation - the user's own cue (they stop ~0.3 s into the killing swing).
  A4. Effect-robust sprite scores (ignore bright saturated spark / arc pixels): mobs stay visible under our hits.
  A5. Hit time per weapon from the client (SWING_LAND_S is still 0.45 fixed; live polearm ~0.50-0.56).
  A6. Speech bubbles (pets' "yummy", "FOOD!! FOOD!!") match the Zombie Mushroom's white body at ~0.66 and start
      tracks that live 2-3.5 s (`runs/v2/20261109_011503_1` #23 #35 #37, air1 #33). Not measured yet: reject hits that
      are mostly flat white with a dark text line, or test the white-body share.
  Evidence 2026-11-09 for the user's "a few air hits" (`runs/v2/air1/fix3`): the 16 stale presses were all real
  mobs within ~150 px of us, unseen 0.5-2.9 s (dying / under our effects) = A4; #154 = A2. Weak tracks of the last 3
  runs, each at birth and ~1 s later: `fix3/weak_sheet_1..4.png` (dying body + our arc, speech bubbles, real mobs
  behind the chat box, 3 Horny Mushrooms bunched behind a rope, other players' skills, the minimap window). DROPS
  are NOT matched as mobs (the user suspected it): a pile of talisman + coins + Horny cap scores 0.23-0.29 on the
  detector (`fix3/drops_126.png`); no weak track started on one (drops aren't logged in v2 ticks: frames only).
  Tool for old vs new tracker on recorded frames: the replay used this session (live Perceiver from bench.build with
  a chosen mob score; a module swap for the old world.py) was NOT committed - rebuild it as tools/perc/ if needed.
**Recordings with targeting mistakes (all Ant Tunnel IV 10005063, brain v2 per press; frames = every 3rd tick, JPEG):**
| run | frames | what to look at |
|---|---|---|
| `runs/v2/20261109_003124_1` | none | 6.5 min, the user's "ton of attacking the air" run. Edge ghost #512 (+ #546, #547) 354-382 s: 17 presses + fake "kill #56". 222 presses, 61 at a target not seen well in 0.5 s: 17 ghost, 8 weak tracks near us (A1), 36 stale real mobs (A4) |
| `runs/v2/20261109_011503_1` | 634 | edge ghost #89 56.5-63 s ("stuck on the side"), born from dying #78; speech-bubble tracks #23 #35 #37 (A6); dying body + effect tracks #21 #84 #97. Pictures: ghost_vision.gif / ghost_play.gif (54.5-64.5 s), ghost_live_58.5.png, ghost_live_zoom.png, ghost_spot_on_press1_frame.png, ghost_edge_padding_zoom.png (the whole-screen search's copied edge column) |
| `runs/v2/air1/20261109_014902_1` | 610 | a REAL mob's track (#72) handed over to the wall spot at 47.0 s, followed 17 s (fix rule 3). ghost_vision.gif / ghost_play.gif (44-60 s), ghost_live_50.0.png; weak #22 #25 #33 (bubble) #53 (a player's skill) |
| `runs/v2/air1/fix3` | 866 | AFTER the edge fix (live check). #154 108-110.5 s: born on dying #151's body under our arc, 3 presses at nothing (A2: weak154.png, weak154_zoom.png); 16 stale presses at real mobs next to us (A4; t 30.2, 37.2, 38.3, 41.8, 42.9, 45.2, 50.2, 51.6, 74.8, 95.6, 96.7, 120.4, 128.4, 141.7, 150.2, 153.5, 161.0, 162.3); weak_sheet_1..4.png (26 weak tracks of the 3 runs above), drops_126.png (drops are not mobs), midscore_sheet.png (detector hits 0.5-0.75 off real mobs: mostly UI / quickslots / minimap / portal / players). Paused at 168.9 s (focus lost): use t < 168 |
| `runs/v2/press1` | 970 | marked_presses.png: weak tracks ON OUR BODY / PET (#41 4 presses 58-62 s, #148 at 145 s) and a weak track born on a dying mob (#222 on #213 at 198.5 s; 162.4 s alike) = A1 / A2. late_mob_174.png: 174.5 s a real Horny Mushroom walking in behind a dying one (the case the A2 rule must not lose) |
| `runs/v2` (root) | 1059 | the hold-era 3-min run: marked_049.96.png / marked_184.98.png / marked_199.09.png = swings at dead mobs kept alive under effects (A4) |
| `runs/v2/react1` | 958 | kill_71.png / kill_94.png: clean kills (death animation timing); mobs lost under hit effects (`probe/lost.py` on `runs/v2`) |
| `runs/v2/20261107_191848_2` | 845 | --mob-score 0.80: track #84 t 62-64.5 s keeps a dead mob alive on empty space, then snaps onto another mob (near_score 0.55 follows anything) |
| `runs/v2/20261107_184350_1` | none | 33 of 35 never-strong tracks = Zombie Mushroom template on scenery (memory "weak tracks = air swings") |
Check tools: `tools/combat/probe/bot_presses.py RUN` (solid / stale / nothing per press), `tools/readme/make_images.py`
(overlay + GIF functions; this session's GIF script used them with a crop), `tools/perc/label_eval.py` (by-eye labels).

Speed (target >= 30 fps, frame -> decision < 35 ms; measure tick p50/p90 + the gap after a swing vs the user):
  S0. DONE: speed regression. `tools/perf/bench.py` replays the live v2 tick (resize from 2560x1440 -> perceive ->
      self state -> brain) on tests/fixtures/perf_ant4 (45 fight frames from press1) in its own process;
      tests/test_perf.py fails when the tick median is > 25 % (+2 ms) over tests/perf_baseline.json (this machine:
      59.6 ms = 16.8 fps; repeats within ~5 %) or a part > 50 % (+3 ms) over its own; EVERY pytest run ends with a
      "bot speed" line (conftest.py), FASTER by > 15 % says to re-baseline (`bench.py --baseline`). Live runs end
      with a `speed:` line in log.txt (hunt_v2.speed_line). In the fight frames the HUD costs 12-13 ms (run average 4).
  S1. Overlap: CPU parts (self tag, camshift, hud) in threads while the GPU detector runs -> the tick ~ the longest
      part, not the sum.
  S2. Move self-tag and camshift matching onto the GPU (the GpuNCC machinery already exists); upload the frame once,
      resize there.
  S3. Slow things slower: HUD HP/MP digits, lie detector, minimap at ~4-5 Hz instead of every tick.
  S4. Then re-check what the tracker gains from more frames (fewer lost mobs under effects, ghost time).
Order: A1 + A2 (cheap, offline-testable) -> A6 -> S1-S3 -> A3 -> A4 -> A5. Live check after each pair with bot_presses.py +
turning.py, 3 min with frames, marked frames for the user.

## attack per press - clean kills, instant turns (2026-11-08, branch `dev`; steps 1-2 DONE + live, steps 3-4 = the
## accuracy plan above)
**Goal of the session (the user):** drop the held attack key. Attack with presses, humanized press lengths and
humanized gaps between them, while promising CLEAN KILLS: no swing after the mob's death (other bots on Ant Tunnel IV
"hit exactly and accurately every target, and stop hitting immediately after death"). Also: turn to face mobs
behind us fast, and to the mob attacking us AT ONCE (the user: "facing the mob attacking you should also be
instant"). The user dislikes added logic layers ("no no no 'track must be proven'"): prefer better evidence and
simpler mechanics over new rules. The user can record a new keylogged session (see step 1).

**State of the per-press work:** all committed on `dev` (see the branch state above). The user's game setup now:
polearm with SLOW attack speed, `q` set to the PLAIN attack (saves MP), in a PARTY -> MP drops don't count swings and
EXP rises are party shares, not kills (use `probe/after.py`, `probe/stale.py`, frames). Live runs:
`runs/v2/2026110{7_191504_1,7_191658_1,7_191756_1,7_191848_2}` (--mob-score 0.65/0.70/0.80/0.80, the last with
frames), `runs/v2/` itself (a 3-min `run` with frames, the hold), `runs/v2/react1` (3 min, frames, REACT_S new),
`runs/v2/press1` (per press). Run tests with `run ... --frames-every 3` into a SUBFOLDER.

### Why the bot swings after deaths (measured, Ant Tunnel IV)
1. **The held key races the death animation.** Clean kill, `runs/v2/react1` t=71 (`react1/kill_71.png`): killing
   hit (spark + 810 dmg, mob HP ~420) 71.46 -> death animation 71.69 (~0.23 s later) -> the swing ends ~71.75 and,
   the key still down, the game starts the next (long overhead) swing -> key up 71.85. The death shows ~0.05 s
   before the next swing starts: no reaction to the death animation wins that, human or bot. REACT_S 0.04-0.10
   cut death -> key up from 0.36 to 0.18 s median (p90 0.97 -> 0.55), which removed the SECOND extra swing, not the
   first. (Retracted guess: "the game queues a swing from the key's repeats" - the clean clip shows the next swing
   start before the key-up.)
2. **Mobs vanish under our own hit effects.** Re-running the GPU detector on frames where the tracker lost a proven
   mob next to us (`probe/lost.py`, `runs/v2`): 52 of 60 found NOTHING there even at 0.4 - the mob is there
   (`runs/minimap_check/lost.png`) under the hit spark, our swing's white/blue arc (big with the polearm), damage
   numbers, or in its hit pose. Gaps: median 0.17 s, p90 0.7, up to 1.3 s for live mobs; 0.35 / 1.2 s for dead ones -
   they overlap, so no timeout separates "covered" from "dead" (a 0.3 s cap: -15 of 26 s ghost time but 13 of 53
   live mobs dropped mid-fight). That's why the tracker keeps a mob next to us 1.2 s unseen (fight_s) and the scene
   1.5 s (UNSEEN_MAX) -> swings at the dead (`runs/v2/marked_*.png`, `mark.py`).
3. **Weak matches keep ghosts alive / start false mobs.** The Zombie Mushroom template (mob 21) also matches cave
   scenery, effects, chat, the minimap at 0.51-0.67 (real mobs 0.80-0.98; `runs/minimap_check/det.png`). New-track
   threshold sprite_score 0.65 let 30 such tracks start (fixed by --mob-score 0.70: they peak < 0.70); following
   uses near_score 0.55 and keeps a dead mob's track alive on empty space, our body, effects, then can snap onto
   another mob (`runs/v2/20261107_191848_2` t=62-64.5, track 84). --mob-score 0.65/0.70/0.80 didn't change the share
   of attack time with a real mob in reach (61-69 %).
4. **HP bars are unused.** `hud.find_mob_bars` is OFF whenever sprites are on (perceiver.py:229, a Perion-fog fix),
   so brain v2 never had them. On Ant Tunnel frames a bar sat over a mob in reach in 56 % of real-fight frames vs 3 %
   of ghost frames (JPEG frames need S > 200, live 235). A bar emptying at the killing hit is the ~0.25 s-earlier
   signal a player uses ("sees the bar about to empty").

### The user's own play = the model (keylogged: `runs/play/20261105_000802_1`, 18.5 min, Line 1, normal-speed spear)
`probe/presses.py`, `probe/human.py`, `probe/human_turn.py`:
- Attack presses: 411; 81 % taps (< 0.35 s); press length p10 0.075 / median 0.127 / p90 0.855 s (31 holds > 1 s).
- Gaps between presses in a fight (< 2 s): p10 0.17, p25 0.23, median 0.83, p75 1.04, p90 1.36 s - two groups:
  double taps ~0.17-0.23 s and a rhythm of ~one press per swing ~0.8-1.0 s.
- Clean kills: 117 of 129 kills by last hit had no press at nothing within 1 s after the death; 12 had exactly one.
  Killing press -> death visible p10 0.21 / median 0.59 / p90 0.76 s. Death -> next press median 2.1 s.
- Turns: a mob within 110 px behind -> the user faces it after median 0.21 s (p90 0.45).
- A NEW recording with the slow polearm on Ant Tunnel IV would fit today's setup better (the user offered):
  `..\auto-maple\.venv\Scripts\python -m maplebrain serve runs\play --observe --gpu --tracker --frames` (F7..F8, 10-15
  min; keys.jsonl + ticks + frames). Then re-run the three probes on it.

### NEW ISSUE (analysed, NOT fixed): turning too slowly, hitting with mobs behind (the user, 2026-11-08)
`probe/turning.py` on `runs/v2/react1` and `runs/v2` (3 min each), mobs proven (peak >= 0.8), same level:
- A mob came within 110 px behind 23x / 26x: we turned to it 7x / 3x, after median 0.6 / 1.4 s; mostly it left or
  died first (16 / 23 of them). The user: 0.21 s median.
- Attack held with a mob close behind and nothing in front: 3.6 / 5.0 s per 3 min.
- Hit by a mob within 80 px (HP drop): 17x / 12x, already facing it 11 / 5; otherwise we turned after median 3.5 /
  1.5 s (p90 4.9 / 13.4 s).
- Time with a mob close behind, by state: `ready + brace` (can't turn yet: TURN_GAP 0.6-0.9 s after the last turn,
  SWING_TAIL_S 0.6-0.8 s after the key-up) ~4 s; `pressure + brace` (holding: no turns while the key is held, by
  design) 2-3 s; `pressure + fight, target elsewhere` up to 5.4 s (holding at a mob/ghost in front, targeting LOCKED on
  the engaged mob while another one behind hits us).
- Causes in code: the hold itself (v2/combat.py Footwork rule `fight`: no walk keys while held; Weapon only lets go on
  death / GOT_AWAY_S 0.3-0.5 / DRY), the lock on the engaged mob (targeting), Facing.can_turn (TURN_GAP, swing tail),
  the `close` condition (behind AND <= standoff + 15), and no notion of "who is hitting us" (an HP drop is never tied
  to the mob next to us). Per-press attacks remove the first two; the swing tail is real (the game ignores direction
  keys mid-swing) but should be the real swing length, not 0.6-0.8 s + TURN_GAP on top.

### Plan for the session
1. **Measure the game first** (short live tests with `--frames`, or the user's new recording): (a) a press DURING a
   swing - ignored, or queued as the next swing? (decides whether double taps are safe; the user double-taps
   ~0.2 s apart); (b) a direction key mid-swing - ignored or applied at the swing's end?; (c) real swing lengths per
   stance with the slow polearm (stab vs overhead swing; ~0.4-1 s in the frames) - can also come from the client:
   `Character/Weapon` (attackSpeed, in the cw-data copy, not exported yet) + `Character.wz` stance frame delays;
   (d) shortest press the game takes.
   **STEP 1 DONE (2026-11-08).** Client: body `00002000.img` swingT2/P1/P2 = 300+150+350 = 800 ms, stabT1/T2 =
   300+100+350 = 750 ms; attackSpeed every polearm (0144xxxx) = 8, spears 6-7. Scaled x (10 + speed) / 16: polearm
   0.90 s, spear 0.80 s. **Live probe** `runs/probe/sauna1` (`swing_live.py`, 21 trials, Regular Sauna, 60 fps;
   `swing_read.py`'s automatic reading is unreliable there - steam, other players overlapping - so read by eye with
   zoomed strips + an arc-pixel count; `runs/probe/swing1` is USELESS: on a ladder in a crowded Ant Tunnel, the user
   got reported - see memory "no scripted input in public"):
   - swing ends +0.89..0.92 s after the key-down (all 6 single/short trials); the white slash arc peaks +0.50..0.56
     (the hit), a gold starburst shows the wind-up from ~+0.05;
   - a key-down DURING a swing is IGNORED, not queued (6 double taps, 2nd press +0.23..+0.76: one arc each);
   - the attack fires on key-DOWN EVENTS: holding q 2.5 s with one key-down (no auto-repeat) = ONE swing. A held key
     only keeps swinging through the keyboard's repeats (KeyDriver emulates them) - why "held key = last pressed";
   - 21 ms and 29 ms taps both swing (d: any press length works);
   - a direction tap released BEFORE the swing ends is DROPPED (5 trials, +0.24..+0.72); one still down at the end
     (+0.90..0.97) turns us; a direction tap 0.09-0.16 s before the attack press turns that swing (turn_first x2).
   **The user's polearm play** (`runs/play/20261108_224651_1`, 8.4 min Ant Tunnel IV, party;
   `probe/human_swings.py` rebuilds SWINGS from the keylog with the rule above):
   - MASHING: 893 presses, all taps (deciles 0.074..0.111 s, median 0.083), press -> press median 0.18 s; 626 of them
     ignored mid-swing, 267 swings (32/min). Next swing starts after the last one's end: with a mob in front, deciles
     0, .015, .03, .052, .068, .09 (median), .112, .15, .188, .458, .98 s;
   - clean kills 64 of 71 (90 %; spear recording 140/153); the 7 others had exactly ONE swing at nothing;
   - killing swing start -> death visible p10/50/90 0.62 / 0.78 / 0.93 s (just before the swing's end at 0.90);
   - the user stops mashing BEFORE the death shows: last press of the burst median 0.48 s before it (p90 0.12 after)
     = ~0.3 s into the killing swing - predicting the kill from the HP bar, not reacting to the death;
   - turn to a mob behind: median 0.36 s, p90 1.03 (spear: 0.21). An LD came at 471 s of this MANUAL play.
2. **DONE 2026-11-08 (`4f31e36`, live-tested below):** v2/combat.py Weapon = one press per swing (`ready` ->
   `swing` -> `ready`), Hands / RE-PRESS / GOT_AWAY / REACT_S / SWING_PERIOD / SWING_TAIL_S gone. The next press is
   decided at swing end + a gap drawn from the user's deciles (`Humanizer.pick`, combat.GAP_DECILES, median 0.09 s):
   engaged mob live and in keep reach, or another live mob in reach in front -> press (PRESS_S 0.088, varied by the
   driver); a dying / gone mob gets no press (CLEAN KILL). Turns only once our swing is over (Facing.swung = swing
   end), TURN_SETTLE before the press after a turn. Targeting locked while engaged. Swing length from the CLIENT:
   export.ps1 now writes Character/00002000.img.xml + weapons.json, `assets build` puts stance_ms / speeds / items in
   attacks.json, `Reach.swing_s` = longest swing stance x (10 + attackSpeed) / 16 (polearm 0.90, spear 0.85);
   `Combat.attack_speed` / `--attack-speed` overrides (Booster), default weapon now poleArm. Sim (tests): game rules
   per the probe, deaths show 0.15-0.45 s after the killing hit; 4 x 3 min: ~10 kills/min, 3.5-3.9 swings/kill,
   swings at nothing after a death 7-14 % (the user 10 %). 1106 tests green. Still a fixed number: SWING_LAND_S 0.45
   (reach.py, the prediction horizon; live hit ~0.50-0.56 with the polearm). The probes `after.py` / `stale.py` /
   `turning.py` read held-key time and need a per-press version before step 5.
   **LIVE `runs/v2/press1`** (committed code 4f31e36, 3 min Ant Tunnel IV, party, --mob-score 0.70, started on a
   rope): 59 presses (20/min), 13 kills by last hit (55 deaths not ours: party), 4.5 swings/kill, 9 HP potions.
   `probe/bot_presses.py`: aimed at a mob seen well in front 37, stale tracks only 18, nothing 4; 19 deaths in
   front, 3 presses at no solid mob <= 1 s after one. Gap after the swing p10/50/90 0.09/0.25/1.13 (user
   0.015/0.09/0.46), 0 presses mid-swing. `turning.py` vs `react1` (the hold): mob behind -> turned 16/25 (was
   7/23) median 0.5 s (user 0.36); hit by a mob within 80 px -> turned median 0.36 s (was 3.46), never-turned 0.
   `marked_presses.png`: the stale presses are WEAK TRACKS (0.58-0.60) ON OUR OWN BODY / PET (track 41: 4 presses at
   58-62 s; 148 "hidden" at 145 s) and a weak new track starting ON A DYING MOB (222 on 213 at 198.5; 162.4 alike)
   -> the unclean presses. Next = step 3 evidence (perception, not a brain rule): no mob detections on our own
   character (we know our box from the tag), no new live track on a dying mob's spot, then the HP bars.
   (Original plan text:) **Weapon per press** (replace pressure/hold in v2/combat.py, keep its doc section true - see memory): press when a
   live mob is in reach in front and the last swing is over; press length drawn from the user's taps; next press
   decided at the swing's end on fresh evidence (death animation seen / HP bar empty / mob gone) - by then the death
   animation is up (killing hit + ~0.23 s), so the extra swing can't start. Gaps humanized from the user's rhythm,
   never fixed (memory: no fixed timings).
3. **Evidence for "dead":** turn the HP-bar reader on in v2 (find_mob_bars with sprites; check Perion fog separately),
   a bar emptied at our hit = the kill. Optional, bigger: make sprite scores ignore effect pixels (bright, saturated
   sparks/arcs) so mobs stay visible through hits - test offline on `runs/v2` frames first.
4. **Turning:** with no hold, turn at the next swing's end toward a mob close behind; a mob that just hit us (HP drop,
   the nearest one within ~80 px) wins over the current target. Target the user's 0.21 s.
5. **Check** with the probes against the user's baseline: presses at nothing after a kill (user: 12 of 129 kills),
   death -> next press, mob behind -> turn (user 0.21 s), hits taken from behind, swings per kill. 3-min `run` with
   frames on Ant Tunnel IV; mark frames for the user.

## Map recognition: the window is measured, not predicted (2026-11-07, branch `dev`, NOT live-tested with a hunt)
The user: "new maps are not recognized and we always have to add some kind of fix for every map". Root cause: identify
and the locator both assumed the minimap window = the canvas. It needn't be:
- **Scrolled:** Ant Tunnel IV (canvas 219x172) shows 219x112, 1:1, and scrolls with the player: rows 0-111 at the top,
  60-171 in the lower right; never sideways. East Rocky Mountain I shows all its 128 rows, the minimap was maxed (grey
  "+"), and nothing in map.json predicts it. Only 3 positions seen: centred-on-player is possible, not proven.
- **Widened:** a long name makes the window wider than the canvas (Rain-Forest: 144 px in 232), the canvas centred,
  see-through strips beside it whose brightness follows the scenery. Don't measure a canvas' sides from the strips.
- **Too big:** the old SEARCH (x < 330, y < 330) ruled out Henesys, Lith Harbor, Henesys Market, Ellinia, Forest of
  Patience Step 2, Forest North of Ellinia. How the game shows those is NOT known yet (may scroll sideways -> refused).

`localize.find_window` measures the outer window; `identify.fits` places each canvas at its centre (edge check as the old
frame check), at the best scroll row; `MinimapLocator.follow` tracks the row every tick (~1 ms), `lost` = no position until
calibrate finds it (a portal, a covered window); `origin` stays the canvas' corner, above the window while scrolled.
Failed F7: frame saved to the run folder (`unknown_map_*.png`).
Results: live frame lower right of Ant Tunnel IV: score 0.88, row 60, x 2152 on the rope at 2150 (the user was on that
ladder). Old vs new code on 199 recorded frames: 188 same, 10 both refuse, 1 only new, 0 only old, 0 disagree. All 301
canvases drawn in simulated windows: 254 right, 0 wrong, 43 ties (names off in that test), 4 low scores. Known limit: strips
as dim as the canvas = no edge = refused (not seen live; the old check refused too).
**Discussed, not decided:** read the title (Tesseract or letter templates), then let the picture confirm. Whole-name Arial
templates can't do it (right map first in 7 of 16 frames), real letter reading is untested. `I/II/III/IV` are its hard
case, which the pictures tell apart; the two fail in opposite places. The user: finish and test this first.

## Brain v2 today (`--brain v2`; the old brain v1 is still the CLI default until the A/B)
Each file's header states its step; v2/combat.py's doc holds THE ATTACK LOGIC END TO END and the game's swing rules.
History of how it got here: HISTORY.md "Session 23", "BRAIN-V2: THE PLAN", "M1 steps".
- **Loop** `runtime/hunt_v2.py`: grab -> Perceiver (GPU sprites + tracker; `--gpu` implied) -> SelfTracker ->
  BrainV2 -> KeyDriver. ticks.jsonl: timings.self / held / v2 (mode, target, travel) / parts / gpu_ms. The log ends
  with kills/min, swings per kill, reach check + learned bands, stats, EXP/hour (`exp_meter.py`: HUD points now -
  at the start, every 5 min too) and a `speed:` line.
- **Brain** `brain/brain_v2.py` only wires the parts in `brain/v2/`: reflexes (potions, HP stop, attack vs plain
  key) - ledger (kills by OUR last hit, contested mobs, swing outcomes) - scene (us + live mobs relative to us;
  Facing = a belief from our keys, Weapon DRY corrects it) - breaks (beats 0.25-1.5 s after a fight; every 2-5 min a
  5-20 s break on a rope / safe spot; any HP drop ends it) - targeting (score = named terms: reach or route seconds,
  turn, crowd, others; keep margin 0.5 s; locked on the engaged mob) - combat (Weapon: one press = one swing, the next
  decided at the swing's end + a gap from the user's deciles -> clean kills; Footwork rule table turn / brace / wait
  / fight / approach / stand) - trips (Travel to a target elsewhere; roam = a weighted spawn, placeholder until M3).
- **Reach** from the client (`assets/mcw/attacks.json`, `brain/reach.py`): sure / maybe boxes per weapon vs the
  mob's body; spear and polearm have the same boxes; swing length = longest stance ms x (10 + attackSpeed) / 16
  (polearm 0.90 s, live 0.89-0.92). Default weapon poleArm; `--weapon`, `--attack-speed`, `--mob-score` (new-track
  threshold; 0.70 on Ant Tunnel). Still fixed: SWING_LAND_S 0.45 (live hit ~0.50-0.56 with the polearm).
- **Movement (M1):** `nav/selfstate.py` (exact x/y, ground / rope / air; ladder hover + hang, platform-end `ledge`,
  ATTACK_FREEZE_S fixes), `perception/camshift.py` (camera from platform strips), `brain/moves.py` (one state
  machine per link kind; no back-and-forth), `brain/travel.py` (routes, re-plan, blacklist, stuck), `nav/sim.py` +
  `tools/nav/sim_tour.py`, `goto`. Live 80 % of moves first try (the misses: mob knockback).
- **Best live numbers:** 18.2 kills/min (`runs/v2/20261105_092129_1`, Line 1, spear, the hold); per press on Ant
  Tunnel IV in a party: 13 last-hit kills / 3 min, 4.5 swings/kill, 0 presses mid-swing (`runs/v2/press1`).
- **Known open (movement):** `runs/v2/20261105_120425_5` t=1039: 12.6 s of `up` at a rope top read as rope; "air"
  with no way out: `20261105_124143_7` t=351 (under rope 1's bottom), `20261106_104547_3` t=943; ladder 778's tag
  reads +10 px (cause not looked into); at rest the tag x creeps toward the minimap's value.
- **Kept rules:** kills = last hit by our weapon only (in reach at our swing, dying 0.2-1.0 s later); never fake
  input; no left-right-left-right; a change is a score term / table rule / state / parameter with its data source,
  never a special case in `step`.

## Roadmap
- [x] M0 foundation (key logger, the user's farming example, KeyDriver). `obs.state` never built: it becomes the v3
  world model.
- [x] M1 movement (selfstate, moves, Travel, sim, `goto`).
- [ ] **M2 Hunt skill, IN PROGRESS:** combat per press is live; P2 = the accuracy + speed plan above. Then: the A/B
  vs the old brain (`tools/play/kills.py` needs a bot variant) -> v2 the default, v1 retired; loot (z bursts); buff
  `1`; skill rotation (the user: later; plain attack is the default, MP potions are too expensive).
- [ ] **Brain v3 (PLAN-v3.md): steps 1-3 DONE, Platform mode live-proven 2026-11-15; steps 4-6 later:** world model + planner over today's parts; modes Platform (= Area, `--mark-platform`) /
  Path / Auto. **M3 patrol = v3's Auto mode** (zones = spawns x EXP / respawn, cost = route seconds; the user's Line 1
  loop in the FARMING EXAMPLE is the reference).
- [ ] M4 human timing: tap / hold / pause distributions from the user's recordings (combat gaps already use them);
  record 1-2 more maps.
- [ ] M5 (optional, later): behaviour cloning of movement from the recordings; combat stays scripted.
- Ideas, not built: `Latency` (measure lag every tick for free: frame age, key -> screen; one object every skill
  reads instead of moves.LAG 0.1 / SWING_LAND_S 0.45); map title reading (Tesseract or letter templates, then the
  picture confirms): discussed, undecided.

## FARMING EXAMPLE: the user, lv 23, Line 1 <Area 1> (10003061, Bubbling) - the reference for the new brain
Recording `runs/play/20261105_000802_1` (2026-11-05, 18.5 min, `serve --observe --gpu --tracker --frames`, 2.6 GB:
ticks + keys.jsonl + every 3rd frame; in a party). Tools: `tools/play/analyze.py RUN` (keys, combos, route),
`tools/play/kills.py RUN 1.0` (kills by last hit), `tools/play/route.py RUN` (platform time vs spawns, transitions).
- **Kills by LAST HIT (the user: count it that way; EXP gains are party EXP, not kills): 179 = 9.7/min** (per
  minute 6-19). Our swing -> mob turns `dying` in the tracker: peak 0.5-0.8 s, few after 1.0 s -> window 1.0 s.
  Time between kills median 4.3 s (p10 0.7, p90 15). 2.6 attack presses per kill. Distance at the killing swing:
  median 72 px in front (p10 13, p90 120). Deaths seen near us but not our hit: 68 (others / party). EXP gains
  764 (41/min) = party shares (5-8 EXP vs Bubbling's 28) - NOT kills. Bot `l1a1_5m` "40 kills / 5 min" = the
  bot's own kill stat, not counted the same way: re-count before comparing.
- **Attack = TAPS** (space n 411, median 0.13 s, p90 0.85, max 2.4 - short holds exist, rarely). 219 of 411
  started while walking (space while left 127 / right 92): attacks while moving. `c` 48 taps (MP ran out: min 0 %,
  median 29 %; plain attack). Gap between attacks median 1.0 s.
- **Movement:** left/right held 35 % / 33 % of the time, hold median 0.5-0.6 s (p10 0.15, p90 3.1, max 15);
  direction reversals while still holding the other way (57 left-while-right, 33 right-while-left). Jumps (shift)
  275, hold 0.17 s, almost always running (106 while right, 103 while left). Rope grab = running jump then up
  (up while right+shift 37, left+shift 32); up hold median 0.8 s. Down (drop / down-jump) 67.
- **Never still for long:** no key held 22 % of the time, in short bits: median 0.19 s, p90 0.65 s, max 13 s.
  Attack pauses > 15 s only 6 times (longest 28 s at 238 s: 25 s standing on rope 1267 = a break).
- **Pickup `z`:** 80 taps in bursts (gap median 0.10 s: 2-3 quick taps), hold 0.09 s; not after every kill.
- **Other keys (the user):** `end` = MP potion, 25x (gap median ~46 s; MP still hit 0 %); `1` = armor buff, 6x
  (~every 4-7 min); `home` = pressed by mistake (it was the MP potion key before); `vka1` (vk 0xA1 = right shift?)
  5x; menus (esc 4, i 3, k 2, enter 2). No HP potion used: HP min 39 %, median 54 %.
- **Route: the whole map, every platform, a hub with loops.** Time per platform vs spawns (64 on the map):
  273 (y 198, full width, 13 spawns) 28 % - THE HUB, revisited every ~19 s; 244 (ground y 323, 18 spawns) 20 %,
  every ~34 s; 79 (y 73, 4 spawns) 15 %, every ~35 s; 111 (5) 7 %; 65 (4) 7 %; 56 (3) 5 %; 19 (4) 4 %; 7 (3) 3.5 %;
  33 (2) 3 %; 46 (2) 2.6 %; 25 (3) 1.9 %; 93 (3) 1.4 %; in the air ~8 %. Time follows spawns but favours the centre:
  the far-west platforms 19/25/93 (10 spawns) get 7 % (19 revisited every ~260 s).
  Top transitions: 244<->273 (20/18), 273->79 13, 79->56 10, 65->273 9, 273->111 9, 56->65 8, 33<->79 7/6.
  Loops seen: **east** 273 -rope1626-> 79 -rope1267-> 56 -> 65 -> drop 273; **north-east** 79 -rope1896-> 33 ->
  7 -> 46 -rope2550-> 111 -rope2714-> 273; **west** 65 -rope768-> 19 -> 25 -> 93 -rope269-> 273 (rare); plus
  sweeps of the ground 244 between them. Single stays are short: a few s, max ~20 s.
- Lessons for brain-v2: tap attacks while walking, multi-key executor (walk + jump + up / attack), a hub-and-loops
  zone plan (value ~ spawns, travel cost from the hub), leave a platform after a few s when it's cleared, occasional
  breaks of 15-30 s, quick pickup bursts.

## User & working style
- Senior Python test-automation dev (Windows, infra; cybersecurity QA). Wants evidence (logs, frames, numbers) and
  test-first fixes. Watches every live run and reports what they saw; their game knowledge is gold.
- Loop that works: the user positions the character and says go -> short live run (3 min, frames) -> read log.txt /
  ticks.jsonl / frames (montages, marked frames for the user) -> reproduce offline / as a test -> fix -> pytest
  green -> record here -> next run. Reply with what was found, the fix and the run command; keep it short.
- Game setup (2026-11-08): polearm, SLOW attack speed, Ant Tunnel IV, in a party; `q` = the plain attack. The
  earlier reference map: Line 1 <Area 1> with a spear (FARMING EXAMPLE).
- **Decisions (don't re-litigate):** no fixed timings anywhere (every press / wait randomised); attack every mob, no
  kill-steal avoidance; be decisive like a player; an algorithm (not learning) decides where and what; prefer better
  evidence and simpler mechanics over new rule layers ("no no no 'track must be proven'"); plain attack by default
  (MP potions are too expensive); big changes on a branch, `main` = last good, the user merges; ask before
  committing.
- **Safety rules:** before a live test stop `run` / `serve` only (by command line), NEVER `maplebrain watch`; keep
  `watch` running all session (LDs come between runs too); scripted / probe input only in a spot the user OKs (an Ant
  Tunnel probe got the user reported); never fake keyboard input; no anti-cheat evasion (hiding the injected flag,
  hardware spoofing): Claude declined that; the ban risk is the user's call.

## Environment
- Project `C:\Users\Yoav\dev\maple-work` (package `maplebrain`, tests `tests/`, runs `runs/`, analysis tools
  `tools/`; `tools/hunt*.py`, `experiment1.py`, `bg_input_test.py` are retired). Git: `main` (last good) and `dev`.
- Python venv `C:\Users\Yoav\dev\auto-maple\.venv` (Py 3.12: opencv, numpy, mss, dxcam, torch + CUDA, pytest).
- **The game runs elevated, so the bot must too** (Windows drops SendInput from a lower-integrity process). Check:
  `whoami /groups | Select-String Mandatory` -> "High Mandatory Level".
- The game: WINDOWED, client area exactly 1366x768 (native, since 2026-11-16; before: FHD / 2560x1440 stretched) on
  the 3440x1440 monitor, display scale 100 % -> the log says `game picture at x (0, 1366), 1366x768 native (no
  resize)` (anything else = resampled or a bad crop); nothing may cover the game window. Keys don't reach the game while it is
  unfocused (tested), so no background play.

## Commands (from `C:\Users\Yoav\dev\maple-work`)
```powershell
..\auto-maple\.venv\Scripts\python -m pytest                    # ~1100 tests, no game needed; ends with "bot speed"
Get-Process python | ? Path -like '*auto-maple*'                 # running bot processes (never stop `watch`)
..\auto-maple\.venv\Scripts\python -m maplebrain watch runs\watch --seconds 14400            # LD siren, no hunt
..\auto-maple\.venv\Scripts\python -m maplebrain serve runs\v2 --brain v2 [--mob-score 0.70] [--frames]   # F7 / F8
..\auto-maple\.venv\Scripts\python -m maplebrain run runs\v2\NAME --brain v2 --seconds 180 --frames-every 3
..\auto-maple\.venv\Scripts\python -m maplebrain serve runs\play --observe --gpu --tracker --frames   # record the user
..\auto-maple\.venv\Scripts\python -m maplebrain goto OUT [--to P [X]] [--seconds S]     # movement test
..\auto-maple\.venv\Scripts\python -m maplebrain livemap [runs\v2]                         # console map of the hunt
..\auto-maple\.venv\Scripts\python -m maplebrain assets build                              # client export -> assets/mcw
..\auto-maple\.venv\Scripts\python tools\perf\bench.py [--baseline]                     # tick speed vs the baseline
..\auto-maple\.venv\Scripts\python tools\perc\replay\run.py RUN [--old HEAD]              # tracker replay -> RUN\replay\
..\auto-maple\.venv\Scripts\python tools\perc\replay\compare.py RUN HEAD work             # old vs new tracks (the gate)
..\auto-maple\.venv\Scripts\python tools\perc\native_check.py RUN --sheet 24             # picture 1:1 with the sprites?
```
`--frames-png` (serve / run) saves the frames lossless: reference recordings (JPEG is useless for colour-exact work).
`serve`: loads once, F7 starts a hunt (the map is recognised then; ignored unless the game is focused), F8 stops it
(all keys released, rising / falling chirp), Ctrl+C quits; it still watches for the Lie Detector between hunts. Each
hunt -> `<out>\<date_time>_<n>\` (log.txt, ticks.jsonl, frames/ with --frames). `run`: 3 s countdown, brings the game
to front, pauses + releases keys on focus loss.
Analysis: `tools/combat/probe/` (README: bot_presses, turning, human_swings, after, stale, lost, mark, ...),
`tools/combat/{agree,compare,reach}.py RUN` (PYTHONPATH=.), `tools/play/{analyze,kills,route}.py RUN`,
`tools/nav/live_check.py RUN`, `tools/perc/label_eval.py` (grade detection vs Claude's by-eye labels; never truth.py).

## Game data (`assets/mcw/`, read `assets/README.md`)
- **From the game's own client files only.** `tools/cwdata/export.ps1` (HaRepacker) exports a copy of the client's
  Data folder; `python -m maplebrain assets build` (`maplebrain/gamedata.py`) converts it; the bot reads local files only.
  All 336 maps (301 with a minimap) and 117 mobs.
- `maps/<id>/map.json`: **footholds** (`x1,y1,x2,y2`, `prev/next`, `layerId`, `groupId`), **ladderRopes**
  (`x, y1, y2, isLadder`), mob spawns (`y` = ground, `walkAreaX1/X2`, `mobTime`), npcs, portals, **miniMap**
  (`centerX/Y`, `magnification`, canvas), `vrBounds`, `info`, `name`. `minimap.png`.
- `mobs/<id>/<anim>_<n>.png`: every animation frame, RGBA, facing left; `mob.json`: `info` (all client stats),
  `frames` with each frame's **origin (feet), lt/rb body box, head, delay**.
- `attacks.json`: attack boxes per weapon type and stance (Character Afterimage), stance lengths (body
  `00002000.img`), weapon attack speeds + items (`weapons.json`); skill boxes from `Skill\*.img`.
- Player physics (`Physics.img`, = v83) is in the export (`cw-data\export\Map\Physics.img.xml`); its constants are
  in `config.Nav` (walk 125 px/s, jump 555, gravity 2000, ...).

## Code map
| Where | What |
|---|---|
| `config.py` | every threshold and timing: `Keys` (all game keys + serve hotkeys, the only place keys live), `Combat`, `Perception`, `Nav`, `Humanize` |
| `capture.py`, `keyboard.py`, `humanize.py` | capture (dxcam, mss fallback), SendInput + focus guard, randomised timing |
| `perception/` | `perceiver.py` frame -> Observation; `gpu_sprites.py` / `sprites.py` mobs by their sprites; `world.py` tracker (tracks in map coordinates, Camera); `camshift.py`; `selfpos.py` own name tag; `hud.py` HP/MP/EXP digits, quickslots, mob HP bars; `liedetector.py`; `mapascii.py` |
| `nav/` | `navmap.py` platforms / ropes / links / `route()`; `localize.py` minimap window + our map position; `identify.py` which map; `selfstate.py`; `sim.py` |
| `brain/` | `brain_v2.py` + `v2/` (above), `reach.py`, `moves.py`, `travel.py`; `brain.py` + `actions.py` = the old brain v1 |
| `runtime/` | `runner.py` (run / serve / watch, setup, map init at F7), `hunt_v2.py`, `keys.py` KeyDriver, `keylog.py`, `recorder.py`, `exp_meter.py`, `goto.py` |
| `gamedata.py`, `livemap.py` | `assets build`; the console map |

Measured game facts that still hold (the user's rules): a mob shows its HP bar + name **only after being hit**; loot
**never** has text under it; players **always** have a name under them; knockback throws you either way, but the mob
stays where you were hit; other players' drops are invisible to us (no party loot).

## Lie Detector (the game's anti-bot test) — very important
- pkg_potions1: at **52.4 s** a panel came up bottom right ("LIE DETECTOR — 5 sec until the Lie Detector mini-game
  starts. Please find the beautiful Violetta…"), then the **mini-game window** in the centre (4 numbered pictures,
  answer by clicking/number, timer). The bot walked on through both for 40 s. Frames: `runs/pkg_potions1/frames/
  001197.jpg` (panel), `002907.jpg` (mini-game). Likely trigger: endless wall-to-wall pacing (fixed by the idle stop).
- **Detection** (`perception/liedetector.py`): both windows carry the same small gold "LIE DETECTOR" title;
  grayscale TM_CCOEFF_NORMED over the whole frame with two 74x12 templates (`assets/lie_detector_{panel,game}.npy`).
  Panel 0.89–0.90, mini-game ~1.0; best match on ~14,000 frames of 29 runs without it: 0.67 → threshold 0.8.
  ~13 ms per check, so it runs every 0.3 s (`check`, throttled by obs.t).
- **Reaction**: checked **first** every tick (v2: `hunt_v2` on `obs.lie_detector`, on its own thread since session
  22; v1: `Brain.step`). The runner releases every key, plays a **siren distinct from the HP alarm** (1500/1000 Hz) **until the window is gone**
  (max 120 s; re-checks the screen between beeps), then ends the run. The bot never answers it: the user does.
- Live: manual hunt 5 → siren worked. pkg_sight5 → a **blue-title variant** was missed (template added since).
  Anything new about its windows (other titles, positions) → add a template. Templates live in `assets/` and
  `tests/fixtures/`; `NAMES` in liedetector.py.
- **Not checked while the game is unfocused** (the runner pauses perception) - open safety item.

### Lie Detector triggers - what we know (3 so far)
| When | Where | Profile |
|---|---|---|
| pkg_potions1, 52 s | map 42, nobody else | pacing wall to wall on an empty floor |
| manual hunt 5, 31 min | map 50, crowded | nonstop fighting, Z 82/min |
| pkg_sight5, 55 s | map 50, crowded | 9 targets killed by others + long cross-map runs in 55 s (most of any run; but pkg_sight3 had 8 with none) |
- The user (certain): **not player reports** (hours on maps full of bots) and **not breaks** (AFK ~80 % of the
  time; tests are short). Z count is not it either (pkg_sight5 had 8 Z before it).
- A non-bot friend of the user got one while killing low-level mobs, no skills, for hours, lots of loot - the
  same profile as the bot. Working theory: the server scores the farming *profile* over time (account history),
  and the moment it fires is not tied to one action. Passing probably doesn't wipe the history.
- Detection logic is server-side; the client can't tell us (we don't reverse the client/anti-cheat).
  Measure instead: idea offered - a cross-session record (time, map, kills/min, skill share, pickups, LD yes/no).

## Gotchas when editing
- **`Screen.calibrate()` must run with the game in front** (it finds the pillarbox bars). Each run logs
  `game picture at x (439, 3001)` in fullscreen; **since 2026-11-02 the user plays windowed at full resolution
  (2560x1440 client) on the left of the 3440 monitor -> `(0, 2560)` is correct** (same 1440 height = same scale:
  sprites 0.8-0.97, minimap canvas 1:1). Anything else means a bad crop (pkg_sight6: 3034). Windowed: nothing may
  cover the game window (the capture reads that screen area). serve started from the
  console measured x 0–3440 instead of 439–3001 → whole desktop squeezed into the frame → HP 56 %/EXP 37 % misread,
  no tag, nothing found. Now calibrated on every F7 (serve) and after the focus wait (run).
- Windows default encoding is cp1252: always `encoding="utf-8"`.
- Edit files directly (the Edit tool); no string-patch scripts on code (they half-applied twice), no `sed -i` (it
  strips the CRs: HANDOFF.md and many files are CRLF). Long inline `-c` one-liners break on quoting.
- Editing a file and restoring it within the same second at the same size leaves a stale `__pycache__` .pyc
  (mtime compared to the second): delete `__pycache__` after such tricks.
- To prove a test catches a bug: temporarily revert the fix/value, run the test (must fail), restore.
- `tests/test_humanize.py` imports helpers with `from test_brain import ...` (no relative import).
- Parametrized fixtures (`brain`, `sbrain`) can't be fetched with `request.getfixturevalue`: write two tests sharing
  a helper.
- Don't put `tools/` first on sys.path. Run Python on downloaded/untrusted files with `-I`.
- Other bot repos reviewed for ideas only (none used); jackexyou/maplebrain's `scripts/dev/admin_worker.ps1` is a
  privilege-escalation hole: never run it.

## Backlog (not scheduled)
- Lie Detector check while the game is unfocused + a capture watchdog (no new frame for ~2 s -> re-create dxcam /
  stop with an alarm): offered, not approved yet.
- Telegram alert to the user's phone on a Lie Detector (bot token + chat id from an untracked config / env var, never
  in code); the same channel could carry HP-stop alerts.
- Minimaps too big for the old search (Henesys, Lith Harbor, Henesys Market, Ellinia, ...): how the game shows them
  is not known yet.
- Weak tracks = air swings (Ant Tunnel scenery matches Zombie Mushroom at ~0.6): covered by the plan's A1 / A2 / A4.
- Old brain only: Power Strike pressed with too little MP shows "You don't have enough MP" in chat (a visible tell).

## History
Everything older is in **HISTORY.md** (moved verbatim 2026-11-08, nothing deleted): sessions 6-23 in full, the old
brain v1 (SEEK -> ENGAGE -> LOOT, zones, loot by sight, rests), its run history and open issues, the tracker / GPU /
client-data work, the trained-model brain plan (dropped for an algorithm), and the brain-v2 plan with M0-M5 details.
