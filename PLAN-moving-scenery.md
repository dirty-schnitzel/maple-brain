# PLAN-moving-scenery: perception on maps whose scenery moves

**Status: OK'd by the user 2026-11-21 ("execute moving-scenery plan"); step 1 DONE 2026-11-21 (below the steps
table), step 2 next.** Measured and prototyped by the plan session (2026-11-21).
Waiting on the user's OK, and on footage for steps 4-6 (the last section). Priority: **P0**, before the tracker
plan session. Tools and their README: `tools/perc/scenery/` (merged into `dev` 2026-11-21; the steps below work
on branch `moving-scenery`); results, sheets and cached cameras: `F:\dev\maple-corpus\work\scenery\`.

## In short
- **The Victoria Road forest maps have no moving scenery.** Two things were drawn wrong: the export decodes one
  flat picture's colour wrong (the sky), and Ellinia's light rays are ADDED to the picture, not laid over it. With
  both right, 9 of 9 forest captures are sound (model share 79.6-93.3 % -> 96.3-99.7 %). No run-time cost.
- **A moving background keeps its exact colours and follows a simple law** - `5 x rx` px a second along the map -
  so it can be drawn into the expected picture. Followed frame by frame it is exact to the pixel on 4 maps, and
  the fit then finds the mobs standing in front of it: +27 % sightings on Kerning's construction site, none lost.
  It never covers a mob (no moving back is drawn in front, on any map).
- **Perion's clouds in front are not backgrounds at all:** 42 maps carry the flag `cloud`, and the client then
  draws its 7 weather cloud pictures over the field - each cloud with its own constant opacity and speed, at whole
  pixels, over mobs and name tags, under the UI. Located, they can be undone exactly, and the fit sees the mobs
  under them: all 174 test mobs at every thickness up to 0.8 (clouds left in: 28 %), no false ones. A cloud is
  never opaque (thickest pixel ~0.88), so "covered by cloud" will be a fact that almost never fires.
- **Cost:** the expected picture with every layer where it is takes under 1 ms on these maps (today's takes
  2-6 ms there); following the layers 0.8 ms; clouds ~2 ms. Perion: about +3 ms over a clean map.
- **After steps 1-5: 82 of the 95 refused maps hunt** (the 42 of Perion's region, 40 with moving backs only).
  The other 13 (7 subway maps, 6 beach maps) hold kinds the bank has no footage of: step 6.

## The two problems (the user, 2026-11-21) - the plan designs a solution for both
1. **Moving backgrounds drawn BEHIND the mobs** (drifting sky clouds, light rays, animated objects, portals).
   They never cover a mob: once perception knows them they should simply stop bothering it.
2. **Perion's clouds drawn IN FRONT of the mobs.** They obstruct the mobs: perception has to find mobs through
   them, or know that a mob there cannot be seen.

## The goal
Picture the difference between the frame and the expected map picture: dark wherever the map is, bright only
where something that is not the map is drawn - mobs, our character, other players, drops, skill effects, damage
numbers, the UI. On every frame of a map with moving scenery:
- a moving background adds nothing to that picture, and mobs in front of it are found as well as anywhere;
- under a cloud in front, mobs are found wherever the cloud lets them be seen, and where it does not, perception
  says so as a fact ("covered by cloud") for the tracker instead of guessing;
- as cheap as possible in tick time: today the Perceiver is 13-17 ms a frame at the median against 16.7 ms for
  60 a second (the p90 is over 16.7 ms on 10 of 23 captures).
A solution does not count when the bright pixels are gone and mobs are lost with them.

Done means: the Victoria Road forest maps of the bank become **sound** by PLAN-data's stop rules (camera counted
from the first fix to the exit fade, OK'd 2026-11-21; "explained" as REPORT-track-before.md section 3 reads it -
waiting on the user's OK); the maps refused today for moving backs (95 of 205 with a scene, Perion among them)
get a scene camera and mobs found / ghosts at the level of the sound maps, or a measured reason why not; the 13
sound captures no worse and no slower.

## Words (in game terms)
- **Expected picture:** the map drawn from the client files for one camera. **Explained:** a screen pixel equals
  it. **Model share:** `sound.py`'s verdict number - 100 % minus the map places that stay unexplained on more than
  half of the frames showing them.
- **Static layer:** a background, tile or object whose place depends on the camera only (all of today's model).
- **Mover:** a background layer the client moves with time (back type 4 or 6). Its place on the map, `X`, is one
  number that changes.
- **Weather cloud:** one of 7 see-through white pictures the client lets drift over the whole field on a map whose
  info says `cloud`. **Thickness** (alpha): how much of the pixel is cloud, 0..1. **Undone:** the frame with the
  clouds taken out again.
- **Sighting:** one mob the fit reports on one frame.

## What was measured (2026-11-21)
**1. What the client files say moves** (`catalog.py`, the 205 maps with a scene; 110 hunt today, 95 are refused):
| Maps | Kind | Where |
|---:|---|---|
| 42 | weather clouds + backs moving sideways (type 4) | Perion's region (`back_dryRock` 34, `back_dryRock2` 8) |
| 40 | backs moving sideways only | Henesys side 28 (`back_grassySoil`), Lith Harbor's roads 7 (`back_vicportTown`), Kerning's construction sites 5 (`back_metroCity`) |
| 7 | backs moving sideways, tiled both ways (type 6), `rx` -150 / -300 | the subway's deeper lines (Line 1 Area 3 / 4, Line 2 Area 2 / 3, Line 3 B1 Area 1 / 2, B3 Area 1) |
| 6 | type 4 + backs that bob up and down (the picture's `moveType`) | Florina Road (the beach) |
A moving or animated back drawn in FRONT: **0 maps**. An animated back: 0. Also, on maps of any kind: ADDED backs
(the picture's `blend`) 14 maps, all hunted today; the mis-decoded flat picture 50 maps (16 hunted today);
animated objects 76 maps (unknown pixels today: under 0.8 % of the play area on the forest captures); objects that
move 4 maps (a jump quest's traps, lasers).

**2. The forest maps** (`look.py`, `sound_proto.py`). The sky of the Henesys-side forests is one flat picture
(`back_midForest/back/0`). Its file holds the colour 0x44FF = RGB (66, 158, 255) - exactly the frame's sky - but
`export.ps1` shifts a PowerShell byte left by 8, which gives 0, and writes (0, 28, 255): every sky pixel and every
cloud edge blended over it is off. The same bug hits Perion's sky (`back_dryRock/back/0`, really (82, 134, 239));
those are the only 2 pictures of that pixel format among 7,431. Ellinia's light rays (`back_shineWood/back/16..20`)
carry `blend 1`: the frame is `min(255, under + colour x alpha)` on 86-95 % of their uncovered pixels within 1
level (laid over as today: under 1 %; their `a0 235` plays no part). Nothing moves on these maps.
| Capture | Model share today -> both fixed | | Capture | today -> fixed |
|---|---|---|---|---|
| Field S of Ellinia `20261119_210307_1#0` | 91.9 -> **99.5 %** | | L Forest I `20261119_123331_2#1` | 80.8 -> **97.7 %** |
| Field S of Ellinia `20261119_204522_1#7` | 90.6 -> **99.4 %** | | L Forest III `..._2#3` | 83.8 -> **98.5 %** |
| Forest S of Ellinia `..._1#3` / `#5` | 93.2 -> **99.7** / 82.7 -> **98.5 %** | | Kerning Middle Forest I `..._2#4` | 92.4 -> **96.3 %** |
| Rain-Forest E of Henesys `..._1#1` | 79.9 -> **98.4 %** | | Forest W of Henesys `..._2#6` | 93.3 -> **97.9 %** |
The fit finds the same mobs either way, with one difference: on The Forest South of Ellinia 61 sightings named
"Axe Stump" are plain Stumps standing in front of the rays (with the rays wrong the fit cannot see that the axe
is not there). Its ms drop a little (Rain-Forest 5.3 -> 3.5: the wrong sky fed the fade search).

**3. Moving backs** (`phase.py`, `proto.py`, `run_proto.py`; 15 layers on 4 maps, `rx` -18..+35):
- A mover's opaque pixels show their own colours exactly: it is laid over what is behind it like any back, and
  tiles, objects and mobs are drawn over it.
- Sideways it sits on the MAP, not the screen: screen x of its left edge = `X - Cx` (repeating every `cx`, or the
  picture's width), and `X` grows by **`5 x rx` px a second** (fitted 4.994-5.012 x rx). Followed by that law alone
  from one fix it is off by p50 0.04-0.5 px after 34-174 s at 60 a second - but a few layers creep (Kerning's
  `rx` -12 / -14 / -18: up to 0.03 px a second; Perion's two fastest: 0.15), not explained: so one cheap look
  every frame, not the law alone.
- Its row is the static formula with another rounding: the parallax term is `sign(u) x floor(ry x |u| / 100)`,
  `u = Cy + 468` (static layers: truncation toward zero). No exception in ~9,000 layer-frames (`ry` -16..+4, both
  signs of `u`).
| Capture (frames a second) | Movers | Frame = expected, of the play area: today -> movers drawn | Sightings: today's picture -> movers drawn |
|---|---:|---|---|
| Henesys Hunting Ground III `20261119_125726_3#2` (60) | 1 | 56.0 -> **95.5 %** | 8,052 -> **8,280** (every 4th frame) |
| Construction Site N of Kerning `20261119_122901_1#0` (60) | 5 | 73.9 -> **94.1 %** | 3,496 -> **4,446** (every 6th) |
| 3-Way Road-Split `20261119_123331_2#5` (60) | 9 | 81.0 -> **93.6 %** | - |
| Perion Street Corner `20261116_085414_5#0` (6) | 7 | 61.4 -> 83.8 % (the rest: clouds) | 1,375 -> 1,469 |
| Land of Wild Boar `20261116_085620_6#0` (6) | 7 | - -> 80.4 % | 631 -> 825 |
No sighting lost anywhere; 48 random extra ones looked at: all real mobs in front of a moving back. "Today's
picture" = what the fit would get if the hunt were not refused: a mover's pixels unknown, so nothing in front of
them can be SEEN.

**4. Perion's clouds in front** (`clouds.py`, `cloudtrack.py`; Perion Street Corner + Land of Wild Boar):
- They are not in the map's layers. The map's info has `cloud = 1` and the client draws
  `MapHelper.img/weather/cloud/0..6`: 7 white pictures, 95 x 63 to 397 x 182 px, mean thickness 0.37-0.61, almost
  no opaque pixel. HeavenClient reads the flag and draws nothing, so no v83 source has their behaviour.
- A cloud is blended as `frame = under + o x a x (cloud - under)` with its own opacity `o` (0.59-0.86, different
  per cloud): 92 % of a cloud's pixels within 1 level, the rest covered by a player; one pixel beside its place:
  40 %. Whole pixels, no smoothing.
- Each cloud keeps its opacity (0.830-0.832 over 44 s) and its speed (17-49 px a second to the right, almost
  level) on the map: a straight line fits its places to 0.3-0.5 px, and three clouds were found again after
  40 s within 3 px of where their speed put them.
- Drawn over tiles, mobs and name tags; under the UI (the minimap is not whitened).
- 5-8 on screen (max 13), covering 8.7 % of the play area (p90 13 %); thicker than 0.8 on 0.07 %; thickest ~0.88.
- Followed over time: frame = expected 84.1 -> **95.1 %** (Perion Street Corner), 80.4 -> **93.6 %** (Wild Boar).

**5. Mobs under the clouds** (`run_fit.py`, `cloudtrack.py --fit --tolvote`, `synth_clouds.py`):
| | Perion Street Corner | Land of Wild Boar |
|---|---:|---:|
| Sightings with today's picture | 1,375 | 631 |
| movers drawn | 1,469 | 825 |
| + clouds undone, the fit unchanged | 1,547 | 948 |
| + the vote tolerant under a cloud | **1,568** | **979** |
| of them under a cloud of mean thickness >= 0.2 | 104 (clouds left in: 5) | 139 |
By eye: 24 of 24 "only with the clouds undone" are real mobs; 40 random sightings on Land of Wild Boar (20 of
them under clouds) real; 40 "only with the tolerant vote" real (a few are legs at the screen's edge). Truth by construction (a mob sprite pasted on a
foothold, a cloud blended over it, 174 placements): found with the cloud left in 27.6 %, undone 93.1 %, undone +
tolerant vote **100 %** in every thickness class up to 0.8; no false mob.

**6. Cost** (ms p50, this machine; `fastexp.py`, `fastpipe.py`, `cloudtrack.py`):
| Part | Prototype | Today |
|---|---|---|
| The expected picture: Perion / Kerning site / Hunting Ground III / 3-Way | 0.84 / 0.94 / 0.65 / 0.88 | 4.3 / 5.8 / 2.2 / 3.4 (movers left unknown) |
| ... on maps hunted today: Ant Tunnel IV / Field S of Ellinia / Line 1 / Transfer Area | 0.62 / 1.51 / 2.59 / 1.84 | 1.15 / 2.57 / **1.52 / 0.70** (pre-composed groups win there) |
| Following 5-9 movers (all in one batch) | 0.8 | - |
| Clouds: follow / the cloud layer / is the frame still whitened? / undo | 0.6-1.1 / 0.5 / 0.5 / 0.15 | - |
| Looking for new clouds, when it runs | 6-10 (p90 20, max 94) | - |
| The fit | ~4, unchanged | ~4 |
The batched follow agrees with the slow reference on 100 % of 32,372 mover-frames (Kerning, 60 a second).

**Not measured:** Perion at 60 frames a second and at the 2026-11-21 graphics settings (every cloud number is from
the two 6-a-second PNG recordings of 2026-11-16); what a cloud does at the map's edge and how many a map has; type
6 backs, bobbing backs and `back_dryRock2` (no footage); animated objects and portals.

## The design
**1. The expected picture gets every layer it can know.** Three kinds, in the client's draw order:
- *static* (today's), now with the right colours and with ADDED layers added;
- *movers*, drawn at their place `X` when it is known; a mover never found yet leaves its pixels unknown, as today;
- on top, per frame, the *clouds*: not part of the expected picture the fit uses, but a layer of their own (colour
  `P`, thickness `A`) that is taken out of the FRAME: `frame' = (frame - P) / (1 - A)`.
The layer loop draws each item only where it is on screen, one blend each (`fastexp.py`); runs of static layers with
one parallax stay pre-composed as today (Line 1, Transfer Area).

**2. Movers are followed, like the camera.** Per mover a fixed set of sample pixels (opaque pixels of its
picture). Each frame: its law's prediction +-3 px, all movers in one batch; the place where the samples show their
colours stands out against its neighbours (a peak rule: a layer mostly hidden behind later ones still has its
visible part) -> found; else it coasts on its law. Never found, or lost for long: every place of its period is
tried (once, one mover a frame). The frame's facts get `movers`: place, found, share.

**3. Clouds are followed, like mobs with a known picture.** A followed cloud = picture, place on the map, speed,
opacity. Each frame: its place predicted, +-2 px checked with the exact blend on sample pixels (one batch for all);
not confirmed, it coasts (over near-white scenery or the UI a cloud cannot be checked) and is dropped only when
the frame shows the scene where it should be. New clouds are looked for only while the frame is still whitened
somewhere no followed cloud explains: the thickness the frame implies, at quarter size, matched against the 7
pictures (FFT), the exact blend at full size deciding - on its own stream, backing off when it finds nothing. The
facts get `clouds`.

**4. The fit works on the frame with the clouds undone,** against the cloud-free expected picture - so does the
difference picture and the drop finder. Two changes inside the fit: a pixel under a cloud thicker than 0.9 is not
valid, counted apart as "covered by cloud"; and under a cloud the vote reads a pixel's colour with a tolerance
that grows with the thickness (the fade search's tables: an undone pixel is off by up to `0.5 / (1 - A)` levels).
Each sighting carries the mean thickness over its seen pixels, each look at a track the count of its pixels a
cloud is too thick over: the tracker's "seen through what, covered by what".

**5. What does not change:** the scene camera (tiles and objects; found on 100 % of both Perion captures, clouds
and all), our own name tag (its high-pass was made for Perion's haze: 0.91 there), `world.py`, every map without
movers or clouds apart from the layer loop.

**What became of the ideas of 2026-11-21.** The draw order does separate the two problems, but not through the
`front` flag: no moving back has it; the clouds in front are the weather clouds. *Predict or mask:* predict - it is
exact and cheaper than today's masking. *A more sensitive detector in the fuzzy areas:* not needed - the exact
blend is known, and a looser detector would cost ghosts. *The cloud as a known picture with a known alpha at a
known speed, undone, the threshold by thickness:* this is the design, with two corrections - the clouds are 7
pictures with an opacity each, not a background layer, and none is near-opaque.

## Steps (branch `moving-scenery`; one executor session each, Opus)
Every step: pytest green, the `bot speed` line reported, and its gate's numbers written into this file under the
step. "SAME" = `tools/perc/replay/gate.py` on the clean clips. The prototype tools stay as the reference: where a
gate names one, the executor gives it a `--live` switch (maplebrain's code in place of the prototype's).

| # | What | Gate (on footage) |
|---|---|---|
| **0** | **The user records** (last section): Perion Street Corner, 5+ minutes, 60 a second, today's settings | filed in the bank; needed before step 4 |
| **1** | **The pictures right.** `export.ps1`: the byte shift in `Get-BlockBitmap` (`[int]` first); `MapHelper.img`'s pictures exported (weather clouds, portals). Re-export, `assets scene` for every map. `scene.py`: a back entry's `blend` (the picture's) and the map's `cloud` flag into scene.json; an ADDED layer in `_compose` / `_backs` (`min(255, under + colour x alpha)`, no cover, never grouped with laid-over layers). Tests: the two pictures' colours; an ADDED layer | The kept replay re-made for the 9 forest captures: **all 9 sound** (model >= 95 %; prototype 96.3-99.7). Forest S of Ellinia: no "Axe Stump" where `run_fit.py` says Stump (61 today). The 13 sound captures: SAME, bench not slower |
| **2** | **Movers in the scene model, nothing allowed yet.** scene.json: `mover` per type 4 back (speed `5 x rx`). `Scene.expected(C, X)` with the layer loop of design 1 and the movers' row rule; the follow of design 2. A mover without a place: unknown, so `clean_meta` and every hunt stay as they are | On the 4 captures of measurement 3: expected = `proto.MScene.expected` within 0.5 level (every 10th frame); the follow finds >= 85 % of the mover-frames the reference finds and never another pixel (prototype 88.4-88.6 %, 100 %); frame = expected >= 95 / 94 / 93 % on the three 60-a-second captures; ms p50: expected <= 1.2, follow <= 1.0. The 13 sound captures: SAME; `expected` on Line 1 and Transfer Area not slower than today |
| **3** | **Maps with movers only hunt** (40 maps). `clean_meta`: a type 4 mover counts as known. The Perceiver: follow, then expected. FrameFacts v6: `movers`. The kept replay made for the bank's 8 captures on such maps (Henesys Hunting Ground I-III, the two hills, 3-Way Road-Split, Kerning's two sites) | Each: camera >= 99 % (first fix to exit fade), model >= 95 %. Sightings >= 99 % of `run_fit.py`'s B on the same frames. By eye, 40 random sightings today's picture does not give: 0 ghosts. Perceiver p50 <= the sound captures' + 1.5 ms. The 13 sound: SAME. **The user's live check:** a 3-minute hunt on a Henesys Hunting Ground |
| **4** | **Clouds followed, in shadow** (needs step 0). The 7 pictures + origins built into `assets/scene/clouds/`. `perception/clouds.py`: follow, the cloud layer, the finder of design 3. On maps with `cloud`: FrameFacts v6 `clouds` + their ms; nothing undone, the maps still refused (observe / replay only) | New capture + the two old: frame = expected with the cloud layer >= 93 % (prototype 95.1 / 93.6). Of the clouds `clouds.py` finds alone on every 10th frame, >= 95 % have a followed cloud within 1 px. Per cloud over its life: opacity within 0.01, places on a line within 0.6 px rms. ms p50 follow + layer + whitened-check <= 2.5; the finder at most once a second after a stay's first 5 s; frame time p99 <= a clean map's + 3 ms. Written down from the capture: what a cloud does at the map's edge |
| **5** | **Clouds undone; Perion hunts** (42 maps). The Perceiver: the frame undone before the difference picture, the fit and the drop finder; design 4's two changes in the fit; sightings and looks carry the cloud numbers. `clean_meta`: `cloud` maps count. `tools/perc/synth/`: mobs under clouds, a fixed-seed set in pytest. The kept replay made for the Perion captures | Synthetic, >= 500 placements: found >= 99 % in every thickness class up to 0.8, 0 false. The two old captures: sightings >= 1,540 / 940 (prototype 1,568 / 979; today's picture 1,375 / 631). By eye on the new capture: 40 random sightings under a cloud (thickness >= 0.2) + 40 any: 0 ghosts. Sound: camera >= 99 %, model >= 95 %. Our name tag found as often as on the Line 1 design capture (within 1 point). Perceiver p50 on Perion <= Line 1's + 3.5 ms. **The user's live check:** a 3-minute hunt on Perion Street Corner |
| **6** | **The kinds without footage** (13 maps; after the user records them): type 6 backs (subway), bobbing backs (beach), `back_dryRock2`. First `phase.py` on the new footage: the same law? Then scene.json + the follow for them | As steps 2-3, on the new captures |
| **7** | *Optional, measured first:* animated objects (one of N known frames, in step with each other) and portals as known layers. Measure on the kept replay how many of the fit's informative pixels are unknown because animated, and where a mob was lost by eye | Done only if some capture loses > 2 % of those pixels or a mob; else left |

### Step 1 - DONE 2026-11-21 (branch `moving-scenery`, e6f8554): gate MET
Built: `export.ps1` (`[int]` before the shift; `Map\MapHelper\png\weather\cloud\0..6` + `portal\...`, 85 pictures,
the clouds identical to `export_helper.ps1`'s), `scene.py` (`blend` per back, `cloud` per map, the ADDED layer in
`_backs` / `_compose`; `build_scenes` now always copies the back pictures - it skipped existing files, so a re-export
never replaced the wrong sky - and an animated back's first frame), tests in `test_scene.py`. `assets scene` for every
map: 233 scenes (205 before: the 2026-11-18 patch's 28 maps had never been built; 15 of them clean); on the 205 the
back lists and the clean verdict are unchanged, the back pictures differ in the 2 fixed ones only.
| Gate | Result |
|---|---|
| 9 forest captures sound (model >= 95 %) | **all 9**: Field S of Ellinia 99.5 / 99.4, Forest S of Ellinia 99.7 / 98.7, Rain-Forest 98.6, L Forest I 97.7, L Forest III 98.5, Kerning Middle Forest I 96.3, Forest W of Henesys 97.9 % (the prototype's within 0.2); camera 100 % first fix to exit fade on all |
| Forest S of Ellinia: no Axe Stump where `run_fit.py` says Stump | **0**: on its 1,655 frames (every 3rd) the live picture and the prototype give the same 6,789 sightings, 0 different either way |
| The 13 sound captures: SAME | `gate.py` (6 clips): **SAME**, 100.0 / 100.0 % on every clip |
| bench not slower | A/B same moment: 14.2 ms before, 13.9-14.1 after (pytest green, bot speed 13.9 ms) |
Found on the way (not a gate):
- **The local scenes were a stale build:** only the 5 maps of the gate's clips (Line 1, Transfer Area, Ant Tunnel IV,
  Dark Cave, Dangerous Steam) had the fit's front planes (`layers/`, step 3.2 of PLAN-perception); every other map
  was an older build without them - the live bot and the kept replay ran so there. Built now. Effect: the forest
  captures' sightings +1 % (Field S of Ellinia) to +62 % (Rain-Forest: 9,115 -> 14,779); Ant Tunnel I re-made as a
  sample: +7 % sightings (11,705 -> 12,535), 58 track ids (60), still sound (95.9 %). **The kept replay of 7 of the 13
  sound captures** (Ant Tunnel II / III, Deep Ant Tunnel II, Evil Eye I / IV, Drake Hunting Ground, Dungeon Southern
  Forest III) **and Evil Eye III is still the stale build's**, so REPORT-track-before.md's pooled numbers mix two
  builds. Old replays kept beside the new: `track_before_step1\` (the 9 forest), `track_stale_scene\` (Ant Tunnel I).
- ms: the expected picture on the two Ellinia maps +0.6-0.75 ms (2.44 -> 3.03, 3.31 -> 4.06: their 5 ADDED layers are
  drawn one by one and split a group); the other forest maps unchanged (1.10 -> 1.10). Step 2's layer loop replaces
  this. The Perceiver on the forest captures: 15.6-20.1 ms p50 (the replay's whole call, this machine).

**Stop rules** - the executor stops with the numbers, no workaround, when:
- a gate's number is missed, or any of the 13 sound captures' tracks come out CHANGED;
- a mover does not follow the law on new footage (its place off by more than 1 px on more than 1 % of the frames
  it is visible): measure with `phase.py` first, do not tune;
- on 60-a-second footage a cloud's opacity or speed is not constant, or a cloud is not at whole pixels: the
  design's base is gone;
- Perion's Perceiver p50 is more than 5 ms over Line 1's after step 5: report the parts' ms.
Not in this plan: `world.py` (the tracker plan replaces it - the cloud numbers are made for the new tracker),
tuning on a hold-out capture, the old path for refused maps.

## Session prompts (ready to paste; each ends with the `handoff` skill)
```text
Moving scenery, step 1 (the pictures right). Read PLAN-moving-scenery.md - In short, measurement 2, design 1,
step 1, the stop rules - and tools/perc/scenery/README.md. Branch moving-scenery. Do step 1 exactly: the export fix
and the MapHelper pictures (assets/README.md's steps; DOTNET_ReadyToRun=0), `assets scene` for every map, the ADDED
layers in scene.py with tests. Then its gate: the kept replay re-made for the 9 forest captures and sound.py on
them, run_fit.py on The Forest South of Ellinia, gate.py and the bench. Write the gate's numbers under step 1 in
the plan. A gate missed: stop with the numbers, no workaround.
```
```text
Moving scenery, step 2 (movers in the scene model). Read PLAN-moving-scenery.md - measurements 3 and 6, designs 1
and 2, step 2, the stop rules - and tools/perc/scenery/ (proto.py, fastexp.py, fastpipe.py are the reference: port
them, do not redesign). Branch moving-scenery. Nothing becomes huntable in this step. Gate as written, on the four
captures of measurement 3 and the 13 sound captures; numbers into the plan; a gate missed: stop.
```
```text
Moving scenery, step 3 (maps with movers only hunt). Read PLAN-moving-scenery.md - step 3 and what steps 1-2 wrote
under theirs - and tools/perc/track/README or dump.py's docstring for the kept replay. Branch moving-scenery. Do
step 3; its gate on the bank's 8 captures of such maps and the 13 sound ones, the by-eye sheet of 40; then ask the
user for the live check on a Henesys Hunting Ground. Numbers into the plan; a gate missed: stop.
```
```text
Moving scenery, step 4 (clouds followed, in shadow). Needs the user's new Perion capture (corpus.py list). Read
PLAN-moving-scenery.md - measurements 4 and 6, design 3, step 4, the stop rules - and tools/perc/scenery/clouds.py,
cloudtrack.py, fastpipe.py (the reference). Branch moving-scenery. Nothing is undone and Perion stays refused in
this step. First re-measure on the new capture what the design rests on (constant opacity and speed, whole
pixels): if not, stop. Gate as written; numbers into the plan.
```
```text
Moving scenery, step 5 (clouds undone, Perion hunts). Read PLAN-moving-scenery.md - measurement 5, design 4, step 5,
the stop rules - and tools/perc/scenery/cloudvote.py, synth_clouds.py, run_fit.py. Branch moving-scenery. Do step
5; its gate (synthetic in pytest, the two old captures' sightings, the by-eye sheets on the new capture, sound,
the name tag, the ms); then ask the user for the live check on Perion Street Corner. Numbers into the plan; a gate
missed: stop.
```
Steps 6 and 7 get their prompts when their footage / measurement exists.

## Footage asked of the user (`python -m maplebrain record --label farming`, chat minimized)
1. **Perion Street Corner, 5 minutes or more of farming** at today's graphics settings. Stand still for the first
   ~20 s, and cross the whole map at least once. Needed before step 4 (the old captures are 6 a second, at the
   normal settings).
2. *Welcome:* 2 minutes on Land of Wild Boar (the second cloud map with other mobs).
3. *For step 6, when convenient:* 2 minutes on one subway map with moving walls (Line 1 <Area 3> or deeper) and on
   one Florina Road beach map - only if the character gets there.

## Questions for the user
1. Which refused map do you want hunted first after Perion Street Corner - a Henesys Hunting Ground? It sets step
   3's live check.
2. The subway's deeper lines and the beach (13 maps): worth step 6 soon, or parked until you farm there?
3. Perion's clouds: when one leaves at the map's right side, does it come round on the left, or do new ones
   appear? (Step 4 reads it off the 5-minute capture either way.)

## Its place beside the tracker
- Perception, one layer under the tracker: it changes each frame's facts on these maps, not how the tracker
  links them. The tracker plan (`docs/prompts/tracker-plan.md`) is designed on the 13 sound captures; from this
  plan it gets, per frame: `movers` (a mover not found = "the scene model does not know these pixels now"),
  `clouds`, and per sighting / look how thick a cloud lies over it. "Covered by cloud" (thickness > 0.9) is a
  fact of its own, expected to be rare: these clouds are never opaque.
- After step 1 the kept replay of the 9 forest captures is re-made (~13 % of the replay) and the tracker can be
  scored on them too; after steps 3 and 5 the replay grows by the newly hunted maps' captures.
