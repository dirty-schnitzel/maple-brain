# maplebrain perception redesign: the scene model (AGREED by the user 2026-11-16; step 0 DONE, see HANDOFF)

Written after the phase 1a speed review (HANDOFF "ROADMAP"). The user's target (2026-11-16): **capped at 60 fps, 100 %
(or close) accuracy for platforms, monsters, the player - everything**; the game window goes to **native 1366x768,
windowed, no resize after capture**; idea to refine: **Frame -> Recognition filter -> Data**, look at the picture once.

## What was measured (offline, Ant Tunnel IV recordings; scripts in tools/perc/redesign/)
| # | Question | Result |
|---|---|---|
| E0 | Where does the tick go? (press1, 300 frames) | 34.8 ms p50 / 54.5 p90. GPU kernels ~17 ms (whole-screen search 8.4, search around tracks 6-7, refine 1.5), CPU ~15 ms in series (HUD 3.3, self tag 2.8, minimap 2.2, camshift 2.0, resize 1.8, scene 1.2); the 27 ms whole-screen tag fallback on ~10 % of frames = the p90. The frame is converted to grey 3-4x, HSV 3x, uploaded twice. Machine note: power plan *Ultimate Performance* since ~11-13 -> every CPU part ~2x faster than the 11-08 baseline (59.6 -> 37 ms bench, live p50 30-34) |
| E1 | Is a colour-exact score better than NCC? | Not on today's frames: a fully visible mob matches only 61-66 % of its pixels within +-16 levels (FHD -> 1366 resampling; contrast 0.8-0.9 of the sprite). Finds 2x more mobs lost under effects (32 % vs 17 % at 1 % false spots) - not a fix alone. **Found:** 9 % of strongly matched real mobs are 50-65 % transparent (spawn fade-in); NCC can't tell, opacity is measurable |
| E2 | Can the scenery be rendered from the client files? | Yes: 127 objects + 1065 tiles of Ant Tunnel IV render and register on recorded frames (score 0.88). It corrects today's camera by -1..+4 px x, -4..+8 px y (p5..p95). 55 % of the play area is tiles / objects, 89 % of those pixels within 30 levels of the frame (the rest = mobs, players, effects on top). The other 45 % = 5 parallax background layers (`back_darkCave`, tiled, rx/ry -5..-20): in the client's Data, not exported yet |
| E3 | Does known scenery expose ghosts? | At today's best match, where >= 30 % of the body is over known scenery: real mobs 0 of 108 "explained by scenery" (opacity p5 0.85); documented ghosts 31 of 47 explained (opacity p50 0.43); empty spots 86 of 96. The 16 ghosts left = speech bubbles, effects, players (not scenery) |
| E4 | Mobs "lost" next to us (203 moments, alive, re-seen within 1.5 s): covered or misplaced? | 79 % truly covered (no good match within 130 px), 13 % stood 25-130 px away (median 78: knocked back past the tracker's +-24..32 px window), 7 % matched inside the window but not associated |
| E5 | Can known scenery tell "covered" from "gone"? | Scenery visible in the predicted body box (>= 60 % of its known pixels): seen mobs 0 %, covered-but-alive 6 %, never-came-back 21 % (at once), empty spots 84 %. So "the spot shows scenery" is safe proof of absence; "something else is drawn there" = covered, keep |
| E6 | GPU cost of matching | fp16: no gain (8.5 vs 9.8 ms). FFT correlation: 4.7 vs 8.5 ms, same scores (max diff 0.003); all 46 poses at half size 9.2 ms; full size, whole screen, all poses 41 ms (conv: 167). Dense full-size search can't run at 60 fps: search only where something can be |
| - | HP bar / mob name tag at lost mobs | 14 % (quick, untuned on JPEG; HANDOFF measured bars in 56 % of real-fight frames): a helper cue, not the fix |

## Diagnosis
Today's perception asks one question in many places: "does this window look like a sprite?" (NCC). It has no idea
what the window should look like when NOTHING is there. That one gap produces most of the open problems:
- scenery / edge ghosts (scenery correlates with a mushroom at 0.57-0.68; real mobs half covered score the same);
- "covered" and "gone" look identical -> timeouts (fight_s 1.2 s, lose_s 0.5 s) that are wrong both ways: swings at
  dead mobs AND live mobs dropped mid-fight;
- the camera is rebuilt from three weak measurements (platform strips, phase correlation, a 16-px minimap dot);
- every recognition part re-reads and re-converts the frame, one after another.
The client files hold exactly that missing knowledge: every tile, object, background, sprite and their positions.

## The design: explain the frame with the game's own assets
```
capture 1366x768 (native, no resize) -> upload once (GPU)
 1 REGISTER   frame vs the map render around the predicted camera -> camera C exact to the pixel
              => platforms, ropes, portals, NPCs, spawn points on screen = map geometry - C (no detection)
 2 SUBTRACT   D = frame - expected scene (tiles + objects + parallax backs; UI regions known) -> what is dynamic
 3 EXPLAIN    windows at (track predictions + spawn points + new foreground blobs + screen edges):
              every pose of the map's mobs fitted as  X = a*sprite + (1-a)*scenery  -> pose, position, opacity a,
              and per pixel: sprite / scenery / something else   => SEEN | ABSENT | COVERED
              same pass: our name tag, players' tags, mob HP bars + name tags, (later) drops, damage numbers
 4 DOWNLOAD   peaks only, one sync                  || CPU meanwhile: HP / MP / EXP digits (cached while the crop
                                                       is unchanged), quickslots, minimap dot ~5 Hz, Lie Detector
 -> FrameFacts (pure, versioned, recordable: no memory inside)
 -> World (the only stateful part): tracks with game physics + 3-valued evidence
```
"Recognition filter" = steps 1-3: one GPU pass over one uploaded frame. The tracker's targeted second look stays
(frame + prior -> data), as a filter on the same GPU frame.

| Thing | Recognised by | Exact by construction? |
|---|---|---|
| Camera | registration against the map render | yes (px) |
| Platforms, ropes, ladders, portals, NPCs, spawn points | map.json - C | yes |
| Our position | name tag (1:1 template) + C; body box from it | tag found or not; position exact when found |
| HP / MP / EXP, potions | HUD digits (as today), cached | yes when readable |
| Mobs | sprite fit over known scenery: pose, facing, opacity, SEEN / COVERED / ABSENT | visible ones; covered ones are tracked, not seen |
| Mob health | HP bar fill + damage numbers vs the client's maxHP (later) | - |
| Other players, our pet | name tags -> body boxes; pet sprites from the client (Item/Pet) | occluders, never mobs |
| Effects, speech bubbles | whatever D shows that no sprite explains = "covered here" | no class needed |
| Drops | item icons from the client (later, with loot) | - |

### Evidence, not timeouts (tracker)
- SEEN -> update. COVERED (something else is drawn over the predicted body) -> hold, position from the motion model;
  no countdown. ABSENT (the scenery shows there and nowhere within reach is it seen) -> ended that frame.
  A die pose -> dying, as today.
- Motion model from the game: walk speed from mob.json, stays on its foothold, turns at ends; **knockback**: when
  our swing lands, the window widens away from us (E4: 13 % of "lost" were just 25-130 px away); jump arcs for jumpers.
- Opacity is a fact, not noise: a = 0.5 rising = spawning (when can it be hit? measure), falling = dying.
- New mobs: at spawn points (map.json, watched every frame: cheap), walking in from an edge, or camera scroll. On Ant
  Tunnel IV spawn points are too dense to gate births (61-81 % of births within 40 px vs 56 % for random spots).

### 60 fps budget (16.6 ms; measured where marked, the rest estimates to be proven per step)
upload 0.3 (measured) + register ~1 + subtract ~0.5 + explain 3-5 (today's batched window search costs 6-7 for the
6-convolution variant; FFT halves dense passes: measured) + download ~1 + tracker + brain ~1; CPU readers in
parallel ~2-4 -> **~8-10 ms**, leaving room for the game's own GPU load. Cost follows the number of dynamic things,
not the screen size or the number of mob types. The loop processes each rendered frame once (no duplicate frames).

### What goes away
camshift.py, the scene phase correlation, the per-tick minimap follow (kept for map identification, start-up and a
~5 Hz cross-check), the coarse / refine / near split, cover probes and edge-ghost rules (the fit handles both), the
whole-screen tag fallback as a blocking call, CPU resize, repeated grey / HSV conversions; after v1 retires: mobs.py,
sprites.py, motion.py.

## "100 %" - what it can mean, and how it is measured
- Exact by construction once the camera is registered: platforms, ropes, portals, NPCs, HUD numbers.
- Mobs: every mob with enough of its body visible (target: >= 99 % recall on labelled frames, <= 1 false mob per
  1000 frames; scenery ghosts impossible by construction). A mob fully behind an opaque effect cannot be seen by
  anything; the answer is tracking it as COVERED and knowing the first frame it is gone.
- Truth: (1) **synthetic frames** from the renderer (mobs, players, effects pasted at known places: exact recall /
  precision, as pytest); (2) ~300 by-eye labelled real frames at native resolution (`label_eval.py`); (3) the tracker
  replay old vs new (`tools/perc/`); (4) live: `bot_presses` solid share 69 % -> >= 95 %.

## Plan (branch `perception` off dev; every step: pytest green, the bot speed line, replay same or better)
| Step | What | Gate |
|---|---|---|
| 0 Ground | Native window check with the user (5 min `serve --observe --frames` on Ant Tunnel IV at 1366x768): is the picture 1:1 with the sprites? New fixture + bench at (1366, 768), re-baseline on purpose. `tools/perc/replay` (old vs new tracker on recorded frames). Label ~300 frames | sprite pixels within +-4 levels >= 95 % on clear mobs (else: stays "resampled", wider tolerances); replay reproduces today's runs |
| 1 Scene model | export.ps1: + Map/Back (+ Npc, Item/Pet, Effect/BasicEff for later); `assets build`: per-map render (tiles, objects, backs with parallax), animated parts flagged unknown; GPU registration -> C | camera within 1 px of hand-checked frames; >= 98 % of non-dynamic pixels explained on Ant Tunnel IV, Line 1, Perion (fog!); platform overlay pictures for the user |
| 2 Pipeline | FrameFacts contract; one upload; GPU launched async, CPU readers in threads; today's detector inside it (FFT search), HUD cache, tag fallback off the main path; watch at 1 look / s + the Lie Detector match on the GPU (section below) | replay identical; bench tick p50 <= 20 ms, p90 <= 25 |
| 3 Mob matcher | residual D; sprite-over-scenery fit (opacity, per-pixel labels) in windows; SEEN / COVERED / ABSENT in FrameFacts; coarse / refine / near removed | synthetic recall >= 99 %, 0 scenery ghosts; labels >= today on every class; the documented ghost tracks (HANDOFF table) gone in replay |
| 4 Tracker | 3-valued evidence replaces fight_s / lose_s / covered_s; knockback + walk model; spawn-point watch; opacity states | replay: lost-alive moments (E4 set) held >= 95 %; time a dead mob stays "live" p90 <= 0.1 s; live 3 min: solid presses >= 85 % |
| 5 Other classes | players + pet as occluders from tags / client sprites (= A1), bubbles = unexplained (= A6), HP bars + mob tags + damage numbers (= A3), hit time per weapon (A5) | labels; live: solid presses >= 95 % |
| 6 60 Hz | frame pacing (one tick per rendered frame), p99 work, thresholds re-measured at 60 fps | live tick p50 <= 12 ms, p99 <= 16.6; gap after a swing vs the user's 0.09 s |
Then ROADMAP phase 2 (recording data model): FrameFacts IS its perception record.

**Step 0 result (2026-11-16, `runs/play/20261116_012059_1`, PNG):** the native picture is 1:1 - opaque uncovered mobs
99.7 % of sprite pixels within +-4 (per-mob median 100.0 %, detector score 1.000), scenery pixels 91.8 % within +-4
(the rest is covered): pixels are exact or something else. Tolerance +-4. JPEG frames are useless for this (22 % of
exact sprite pixels within +-4): reference recordings are PNG (`--frames-png`). Details: HANDOFF "Step 0 state".

**Step 1 result (2026-11-16, Ant Tunnel IV):** `maplebrain/scene.py`. Backgrounds: origin at
`b + off + trunc(r * (C + off) / 100)`, off 682 / 468, integer division (exact on 65 of 65 fitted positions). Camera
by landmark registration: found on 3858 of 3858 frames, the best of its 25 neighbours on 120 of 120; the scene
explains 99.82 % of the pixels outside moving things; 3.0 ms on the GPU. Today's camera is > 8 px off on 39 % of
frames. Open: native recordings of Line 1 and Perion for their gates. Details: HANDOFF "Step 1 state".

**Step 1 on 7 maps (2026-11-16, the user's 6 more native recordings):** the offset is 683 / 468 (682 was a 1 px
capture error on the Ant Tunnel IV recording, fixed in `capture.game_columns`): one arithmetic reproduces 736 of
736 (x) and 587 of 587 (y) measured layer positions. Camera exact on 120 of 120 checked frames of every map and
followed through every saved frame; outside moving things the scene explains 99.71-99.95 % (p50 per map).
**Deferred by the user (2026-11-16): Perion's moving cloud layers** (drawn over the background rocks, today
neither explained nor marked unknown where they really are: 43-50 % of the play area is left over there) - a task
for later in HANDOFF; until then the plan works on the clean maps. Done: the bot's processes pin themselves to the
performance cores (`procperf.py`; in the background they ran on the efficiency cores, 44 ms vs 29 ms). Open: the
capture does not follow a moved game window. Details: HANDOFF "Step 1 on 7 maps".

**Step 2 (in progress, order agreed 2026-11-16; details HANDOFF "Step 2 state"):** 2.1 one upload + one grey, 2.2
FrameFacts (perception/facts.py, in ticks.jsonl), 2.3 the minimap window measured per map (the UI mask; its
picture is see-through, mobs behind it stay tracked), 2.4 background layers pre-composed per parallax (Line 1 /
Transfer Area 16-22 -> ~2 ms) - DONE, replay unchanged, bench with the game up 29.3 -> 27.3 ms. 2.5 the scene camera
in shadow, 2.6 it IS the camera on clean maps (mob feet within 2 px of their platform 23-27 -> 97-98 % on Ant
Tunnel IV; bench 24.3 ms), 2.7 own tag 1:1 + its whole-screen look on the GPU (42 -> 8-12 ms) - DONE. 2.8 Lie
Detector: native 1:1 title templates from the client's own windows (pasted at native >= 0.970, was down to 0.677 /
0.780; false max 0.671 -> 0.496), the hunt's look on the GPU (FFT NCC exact to cv2, ~3.5 ms vs ~90 on the CPU),
watch 1 look / s - code DONE. 2.9 (the user cut it to what survives step 3): HUD text cache (re-read only when its
crop changed: identical by construction) + CPU readers in threads beside the GPU work -> **bench p50 22.0 -> 18.4
ms, p90 25.7 -> 21.1: step 2's gate met**, replay the same tracks on all 7 clips. The FFT whole-screen search
(measured 7.7 -> 4.4 ms, same peaks) and a faster `find_near` were dropped: step 3 replaces both. Open: one live
check of 2.8 + 2.9 by the user. The gate is tools/perc/replay/gate.py (~1 min clips of every clean map, cached); the
bench needs the game running (GPU P-state: 40-43 ms idle vs 27-30 with the game).

### Lie Detector watch (added by the user, 2026-11-16) - part of step 2
- **`maplebrain watch` looks once per second** (today every 0.3 s; the Lie Detector gives 10+ s). Each look = 4
  full-frame template matches on the CPU (~13 ms each) in a second process, beside the hunt.
- **Investigate: the Lie Detector match on the GPU** - does it cut the frame time? In the hunt: on the frame that
  is already uploaded (step 2: one upload), instead of the CPU thread that competes with the HUD / tag readers; in
  watch: its own small GPU job. Measure the hunt's tick p50 / p90 with watch off, watch as today, watch at 1 s, and
  watch on the GPU (bench + a live observe run); keep what is faster and never slower to notice an LD.
- Same work: native 1:1 Lie Detector templates (today's are cut from stretched windows; until then the bar is
  0.75 instead of 0.80, the user's call 2026-11-16; best false score on native frames of 7 maps 0.668).

## Risks and unknowns
- Native 1366x768: "renders 1:1" is assumed, not proven (HANDOFF TODO) - step 0 decides the tolerances. The 72,857
  recorded frames are all resampled: new reference recordings are needed; old ones stay good for tracker logic.
- Parallax backgrounds: the formula is known (HeavenClient), the client's constants get fitted from frames; moving
  clouds / animated objects / fog layers (Perion, front backs with alpha) = "unknown" pixels there, where the fit
  falls back to today's contrast-only score.
- An opaque effect hides what is behind it: accuracy there is the tracker's, bounded by how long effects last.
- `serve --observe` drew Lie Detectors before (memory): the step-0 recording is the user's call.
- Build size: Ant Tunnel IV's render is 3910x3160 (49 MB raw); built per map, loaded at F7 with the sprites.

## Not chosen as the main line: a learned detector
It would learn the same three things implicitly (scenery, occlusion, opacity) from data we would have to render
anyway, and gives scores nobody can read. After steps 0-3 its prerequisites exist for free (renderer = unlimited
labelled data, FrameFacts = the plug, truth sets = the referee): worth one feasibility session only if the fit
plateaus below target on covered mobs.
