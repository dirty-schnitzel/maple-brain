# PLAN-moving-scenery: perception on maps whose scenery moves

**Status: OK'd by the user 2026-11-21 ("execute moving-scenery plan"); step 1 DONE 2026-11-21 (below the steps
table); step 2 DONE 2026-11-23 (its 2 missed numbers accepted by the user: "all good continue"); step 3 built
2026-11-23 (2 misses + the user's live check owed: under step 3); step 4 built 2026-11-23, its gate missed,
ACCEPTED by the user (under step 4); step 5 built 2026-11-23, gate missed on 2 numbers (ms, the camera on the old
6-a-second captures) - waiting on the user + the Perion live check (under step 5).** Measured and prototyped by the plan session (2026-11-21).
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

### Step 2 - DONE 2026-11-23 (branch `moving-scenery`, def0574): gate missed on 2 numbers, ACCEPTED by the user
Built: `scene.py` - scene.json `mover {v: 5 x rx}` per type 4 back (`assets scene` re-run, 233 maps); `mover_pos` (the
row rule); `Scene.expected(C, X)`: every layer outside the pre-composed groups drawn only in its screen rectangle
(`_Draw`: colour, alpha, 1 - alpha; a tiled axis stored repeated, so a piece is a slice), colour and cover in one
(h, w, 4) buffer, a mover at its place or its rows unknown; `MoverFollow` (fastpipe's FastMovers: +-3 px, one batch,
the peak rule; plus a full look over the period for a mover never found / lost 1 s, one a frame, the same peak
rule). `config.Perception.mover_*`. `clean_meta` unchanged: nothing hunts on these maps. Tests in `test_scene.py`.
Gate tool `tools/perc/scenery/live2.py` (every frame; the live follow on its own, never reset from the reference).
| Gate | HG III | Kerning site | 3-Way | Perion St. Corner |
|---|---|---|---|---|
| expected at the reference's places (<= 0.5 level) | 0.10 | 0.07 | 0.09 | 0.00 |
| follow finds of the reference's mover-frames (>= 85 %) | 100.0 | 88.2 | 90.8 | 87.0 |
| ... on the same pixel (100 %) | 100 | 100 | 100 | 100 |
| frame = expected (>= 95 / 94 / 93 %) | **95.5** | **94.3** | **92.2 MISSED** (reference's places: 93.5) | (83.0; clouds) |
| ms p50 expected (<= 1.2) | 0.53 | 1.01 | 1.08 | 1.00 |
| ms p50 follow (<= 1.0) | 0.94 | 0.93 | 0.90 | **1.76 MISSED** (frames without a full look 0.95) |
The 13 sound captures: `gate.py` (6 clips) **SAME**, 100.0 % on every clip; on 125 clean maps x 14 cameras the
expected picture is bit-identical to step 1's. `expected` on Line 1 0.79 -> 0.55 ms, Transfer Area 0.70 -> 0.46 (A/B,
same moment). pytest green, bot speed 13.7 ms (step 1: 13.9). GPU memory: +70-210 MB per loaded scene (the repeated
pictures; the card has 16 GB).
**The two misses:**
- **3-Way: acquisition.** Mover 6 (`back_vicportTown/back_9`, mostly behind later layers) is found by the reference
  from frame 0, by the live full look only at 12.1 s: 12 s with its rows unknown. Once found, every mover coasts
  within 0.9 px of the reference. The reference's full search scores only the pixels the later layers leave visible
  (share >= 0.5); the live full look scores against the tiles only, and over a whole period (900 places) a mostly
  hidden mover does not stand out. fastpipe never had an acquisition (it started from the reference's places).
- **Perion: full looks at 6 frames a second.** Two of its movers (`back_dryRock/back_2`, `/back_3`) are never
  visible on the capture (the reference never finds them either); each gets a full look (2.5 ms) once a second -
  at 6 frames a second that is 49 % of the frames, at 60 it would be ~3 %.
- Also found: `back_vicportTown/back_6` (3-Way's region) has no opaque pixel (alpha <= 238): neither the live
  follow nor the reference can follow it; its rows stay unknown. `back_vicportTown/back_7` (175 opaque pixels) is
  found by the live follow on 895 frames the reference refuses (its minimum is 300 px): all within 0.5 px of its
  law. Samples are each pixel once (repeated samples false-locked on a synthetic test, 12 of 40 frames).
**Decided (the user, 2026-11-23, "all good continue"):** both numbers accepted as they are; nothing changed.
The two options that were put to the user, kept for a later look: (1) the acquisition - score the full look on the pixels the movers already found and the
static layers after it leave visible (the reference's rule, ~ +1 ms when it runs), or accept 92.2 % on 3-Way; (2) the
follow's ms gate on 6-a-second footage - count it on frames without a full look, or retry a never-seen mover less
often (e.g. only when its rows come on screen).

### Step 3 - built 2026-11-23 (branch `moving-scenery`): gate met on the five captures with a camera; 2 misses
Built: `Scene.clean_meta` - a mover behind the field counts as known; refused stay the cloud maps, type 5-7 /
animated backs and a mover drawn in FRONT (map 80003000's `back_darkMountain/back_4`, found on the way: not in this
plan's design). 174 of 233 scenes clean (125 before). The Perceiver: `MoverFollow` after the camera, its places into
the one `expected` a tick; part `movers`. FrameFacts v6: `movers` [(back, X, found, share)] + `movers_ms`. The kept
replay of the 8 captures (`dump.py` CAPTURES). Gate tool `tools/perc/scenery/live3.py` (live sightings vs
run_fit.py's A / B + the by-eye sheet). `dump.py` / `msl.py`: a folder in incoming/ with a filing log is no longer
taken for a recording (two unfiled recordings of 2026-11-23 01:21 kept every GPU tool waiting).
| Capture | camera (fix to fade) | model | sightings live / B (every 3rd frame) | ms p50 (kept replay) |
|---|---|---|---|---|
| Construction Site N of Kerning | 100.00 % | 99.1 % | 13,187 / 13,214 = 99.8 % | 18.5 |
| A Hill West of Henesys | 100.00 % | **94.4 %** (the open chat: footage) | 3,042 / 3,042 = 100.0 % | 16.3 |
| Henesys Hunting Ground I | 100.00 % | 96.3 % | 5,895 / 5,864 = 100.5 % | 17.1 |
| Henesys Hunting Ground II | 100.00 % | 98.2 % | 3,751 / 3,751 = 100.0 % | 16.6 |
| Henesys Hunting Ground III | 100.00 % | 98.5 % | 11,481 / 11,502 = 99.8 % | 17.1 |
| Kerning City Construction Site / 3-Way Road-Split / The Hill East of Henesys | **0 %** | - | - | - |
- Sightings: 37,356 live vs B 37,373 (100.0 %); today's picture (A) 33,838: +3,518. By eye, 40 random live
  sightings A does not give (`work\scenery\live3_sheet_0..3.png`): 33 real mobs, **0 ghosts**, 7 can't tell (under
  the open chat 2, the minimap 1, only feet at the screen's top edge 2, mostly behind a beam / cloth 2).
- The Perceiver, the same moment (900 frames each, alternated twice): sound Ant Tunnel IV 14.2 / Line 1 14.5 ms;
  HG III 15.5 (+1.1, in the gate); **Construction Site N of Kerning 16.4 (+2.0: missed by ~0.5 ms;** 5 movers,
  `movers` 1.3-1.4 ms in the Perceiver - 0.9 alone - and a heavier D).
- The 13 sound: `gate.py` SAME, 100.0 % on every clip. pytest green; bot speed 15.4 ms on a slower machine moment
  (A/B the same moment: this tree 15.1 / 14.9, step 2's commit 15.2 / 14.8 - unchanged).
- **The three without a camera: the minimap, not the movers.** The scene camera starts from the minimap's seed
  (our map place - our screen place): Kerning City Construction Site reads the dot on 347 frames but the seed never
  registers (off by > 48 px?), 3-Way Road-Split reads the dot on 2,058 frames but the locator gives no map place,
  The Hill East of Henesys no dot at all. `cam.py`'s whole-map search finds the camera on 3-Way on 99 % of the
  frames. = HANDOFF's "wide maps" item (the user, 2026-11-23: its plan runs after the tracker).
- **Owed: the user's live check** - a 3-minute hunt on a Henesys Hunting Ground (HG III: camera, model and ms in
  the gate).

### Step 4 - the re-measurement first (2026-11-23): the design's base HOLDS at 60 a second, today's settings
The new capture `20261123_163821_2#0` (Perion Street Corner, 4.75 min, 60 a second, 0 dropped; the user's labels
clouds + farming): `cam.py` camera on 100.0 % of 17,099 frames; `run_clouds.py --every 6` (CloudFinder alone per
frame, 2,850 frames) -> `tools/perc/scenery/cloudlaw.py` (new: the finds linked into clouds, per cloud the opacity
spread, a straight line through its places, the share the exact model explains; on the old 6-a-second finds it
gives measurement 4's numbers back).
- 70 clouds seen on >= 20 frames (2 s - 67 s each). **Opacity constant:** p5-p95 spread p50 0.0009, <= 0.01 on 69
  (the 70th: 2.4 s at opacity 0.34, share 0.65 - a weak find). **Straight lines:** rms p50 0.41 px; the 9 over 0.6
  px each hold 1-8 finds at share 0.6-0.8 (the finder's minimum: a track's ends, clouds overlapping) - without them
  0.32-0.50. **Whole pixels:** the exact model explains p50 100 % of a cloud's pixels at its whole-pixel place.
  Speeds 17-49 px a second to the right, |vy| < 0.5; one fixed set of values (mostly whole thirds: 17.00, 22.67,
  23.00, 35.00, 36.00, 44.67, 47.33 ...).
- Frame = expected: 87.9 % with the movers, **95.8 %** with each frame's finds drawn (prototype 95.1); 4 clouds a
  frame p50 (max 9), 7.8 % of the play area under a cloud, thicker than 0.8 on 0.02 %.
- **The map's edge (asked by the step):** every cloud drifts right; clouds were seen from beyond the map's left
  bound (top-left x -1,613; vrBounds -1,363..2,533) to x 2,491. Clouds that appear / vanish in full view do so
  mid-map, where the finder loses and finds them again (near-white scenery, overlaps) - not at the edge. Wrap or a
  new cloud at the edge is not settled by this capture; the design's rule covers both (a followed cloud is dropped
  only when the frame shows the scene where it should be; new ones come from the finder).

### Step 4 - built 2026-11-23 (branch `moving-scenery`): gate MISSED, stopped before step 5
Built: `assets scene` -> `assets/scene/clouds/` (the 7 pictures + origins, identical to the prototype's);
`perception/clouds.py` `Clouds` (cloudtrack.py's CloudTracker + fastpipe's FastClouds + CloudFinder.alpha_hat: the
batched follow, the cloud layer, the whitened check, the coarse finder; `undo` ready for step 5); config
`Perception.cloud_*`; `MapKit.perceive` (scene + fit: perception runs, a cloud map too) vs `MapKit.clean` (a hunt
may start: not a cloud map) - the runner loads a cloud map's scene, says why hunts are refused; the Perceiver
follows the clouds after `expected` (nothing undone) -> FrameFacts v6 `clouds` + `clouds_ms`. Tests
`tests/test_clouds.py` (a cloud found on the first frame, followed at its speed, undone to <= 3 levels; no cloud ->
no finder run). Gate tool `tools/perc/scenery/live4.py`; Wild Boar's per-frame finds `clouds_boar_all.json`.
| Gate | new Perion (60 a s) | old Perion (6) | Wild Boar (6) | gate |
|---|---|---|---|---|
| frame = expected with the cloud layer | **95.6** | **94.3** | 92.5 MISSED | >= 93 % (prototype 95.1 / 93.6) |
| the finder's clouds with a followed one within 1 px | 88.8 MISSED | 86.8 MISSED | 86.2 MISSED | >= 95 % |
| opacity vs the finder's, per cloud (>= 20 fixes) | 0.006 | 0.106 (1 of 18) | 0.004 | <= 0.01 |
| fixes on a line, rms per cloud | p50 0.41, 1 of 48 at 11.4 | p50 0.44, 1 at 1.1 | max 0.50 | <= 0.6 |
| ms p50 follow + layer + whitened | **2.32** | 2.60 | **2.49** | <= 2.5 |
| finder runs a second after the first 5 s | 0.44 (10.5 ms p50) | 0.68 | 0.51 | <= 1 |
| Perceiver p99, the same moment | 25.5 ms (p50 18.0) | - | - | <= a clean map's + 3: Line 1 18.4 (miss), Ant Tunnel IV 30.0 |
- **The two gates pull against each other.** With the prototype's cadence (the finder every 0.2 s: 3.4-3.6 runs a
  second) the followed share is 93.2 / 90.6 % and Wild Boar's frame = expected 93.7 % (the prototype's 93.6) -
  still under 95 %. A cloud the follow has not taken on yet (it waits for the next finder run) or lost (one of the
  9 % of the 1-px misses) counts against it; the prototype was never measured on this number.
- The 11.4 px line on the new capture (cloud 20, 714 fixes over 26 s) and the old Perion's 0.106 opacity (cloud 3,
  6 s) are single followed clouds gone wrong: a swap with a cloud of the same picture, or a first opacity read
  badly - not looked into further (stop rule).
- Not built: the finder on its own CUDA stream (design 3) - it runs on the main stream (10.5 ms p50, max 52.6 on
  the new capture), the likely part of the p99.
- The 13 sound: `gate.py` SAME (`MapKit.perceive` changes nothing on clean maps). pytest green.
**For the user / the planner:** what "followed within 1 px" should be measured against (a new cloud's first
second counts now), the finder's cadence (<= 1 a second vs the share), and whether step 5 (undo; Perion hunts) goes
ahead on this follow.
**Decided (the user, 2026-11-23): step 4's misses accepted as they are; step 5 goes ahead on this follow.** What
was missed and how it could be fixed: "Later (low priority)" at the end of this file.

### Step 5 - built 2026-11-23 (branch `moving-scenery`, 016c251): gate missed on 2 numbers, stopped
Built: the Perceiver takes the followed clouds out of the frame (`Clouds.undo`) before D, the fit and the drop finder;
a pixel under a cloud thicker than `Perception.cloud_thick` (0.9, design 4) is not valid. The vote reads an undone
pixel with the fade search's tolerant tables at the level `1 + 0.5 / (1 - A)` asks for (`Voter.ids(cloud=)`, ported
from cloudvote.py). `FitMob.cloud` (mean cloud alpha over its SEEN pixels) + `n_cloud` (informative pixels under a
cloud too thick to undo), the same two in a look's row (FrameFacts v6's `fit` / `fit_hints`). `clean_meta`: cloud maps
count - **the 42 cloud maps hunt** (216 of 233 scenes clean: step 3's 174 + the 42). `tools/perc/synth/under_clouds.py` (mobs under clouds by
construction, maplebrain's code) + `tests/test_under_clouds.py` (40 placements, seed 3, on Perion's expected picture:
40 / 40 found, 0 false; 14 / 40 with the cloud left in, 37 / 40 without the tolerant vote - the test fails then).
`tools/perc/scenery/live5.py` (the live path frame by frame: sightings, sheets). The kept replay of the 3 cloud
captures (`dump.py` CAPTURES).
| Gate | Result |
|---|---|
| synthetic, >= 500 placements: >= 99 % found per thickness class up to 0.8, 0 false | **600 placements** (the new capture, every 3rd frame): **100.0 %** in every class (0-0.1: 5, 0.1-0.3: 128, 0.3-0.5: 297, 0.5-0.6: 96, 0.6-0.7: 53, 0.7-0.8: 21), **0 false**; the cloud left in: 22.2 % (0 % at 0.7-0.8). The found mobs' `cloud` = the truth within 0.002 (p90) |
| the two old captures' sightings >= 1,540 / 940 | **1,560 / 995** (the clouds left in: 1,468 / 855; prototype 1,568 / 979) |
| by eye on the new capture, 40 under a cloud (>= 0.2) + 40 any: 0 ghosts | **0 ghosts** (`work\scenery\live5_20261123_163821_2_0_under_0..1.png`, `_any_0..1.png`): 80 real Stumps / Dark Stumps / Snails / Red Snails; 5 only slivers at the screen's top / left edge (the snail's shell / eye shows), 1 Dark Stump dying behind our character |
| sound: camera >= 99 %, model >= 95 % | new capture **100.00 % / 99.6 %**: sound. **The two old 6-a-second captures MISSED: camera 22.7 % / 13.4 %** (model on the frames with a camera 97.4 / 94.4) - not the clouds: see below |
| our name tag as often as on the Line 1 design capture (within 1 point) | 98.57 % of the frames vs Line 1's 96.68 % (+1.9: more often, not less) |
| Perceiver p50 on Perion <= Line 1's + 3.5 ms | **MISSED: 19.17 vs 13.59 ms = +5.6** (900 frames each, alternated twice, the same moment); p99 24.5 vs 16.6. Over the stop rule's 5 ms: the parts below |
| the 13 sound captures: SAME | `gate.py --base ccfab7a`: **SAME**, 100.0 % on every clip. pytest green; bot speed 15.1 ms (step 3's A/B 15.1 / 14.9: unchanged) |
**The parts' ms (the stop rule; p50, Perion vs Line 1, the same moment):** `clouds` **5.40** vs 0 - of it the clouds' own
work ~3.1 (follow 1.87, layer 0.43, whitened 0.52, undo ~0.23; the finder 9.7 ms when it runs, on 127 of 17,099
frames) and ~2.3 the GPU work queued before it (the expected picture) waited for at its first sync - on Line 1 that
wait falls in `diff` / `patches` (1.50 / 1.80 there, 0.60 / 1.30 on Perion); `movers` **1.30** vs 0; `fit` 6.80 vs
7.00 (the tolerant vote and the cloud numbers cost nothing visible); everything else equal. Step 4 already stood at
p50 18.0 on Perion: step 5 adds ~1.2 ms (the undo, the vote's tolerant lookup, one more gather).
**The old captures' camera: a lost camera never comes back** (HANDOFF's open item, met here first on footage). Old
Perion frame 83 (0.25 s after 82, 6 a second): the camera moves 58 px down (a fall) - beyond the wide look's 48 px -
and is lost; the Perceiver seeds the scene camera from the tracker's camera (`world.cam.C`), which keeps the last
place, so the minimap's seed (within 14 px of the true camera, p90, on 268 of the 283 lost frames) is never used;
the same on Land of Wild Boar (frame 46, a 59 px fall). At 60 a second (the new capture) a fall is ~4 px a frame:
100 %. Nothing step 5 changed is read by the scene camera.
**For the user:** (1) accept the two misses or have them fixed - the ms (the finder off the main stream, the movers'
sync; "Later" below) and the camera on 6-a-second footage (a lost camera seeded from the minimap); (2) **the live
check: a 3-minute hunt on Perion Street Corner** (the code lets the 42 cloud maps hunt now).

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

## Later (low priority): the misses accepted on the way, and the fixes proposed
Nothing here blocks a step; each was accepted by the user as measured. Pick up when a map or a number needs it.
| From | The miss | Proposed fix |
|---|---|---|
| step 2 | 3-Way Road-Split frame = expected 92.2 % (93): a mostly hidden mover (`back_vicportTown/back_9`) found only after 12 s | score the full look on the pixels the found movers and later static layers leave visible (the reference's rule; ~ +1 ms when it runs) |
| step 2 | Perion's follow 1.76 ms p50 at 6 a second (1.0): two never-visible movers get a full look once a second | count the ms on frames without a full look, or retry a never-seen mover only when its rows come on screen |
| step 2 | `back_vicportTown/back_6` has no opaque pixel: never followed, its rows stay unknown | sample pixels with alpha >= ~0.9 and a tolerance that grows with 1 - alpha |
| step 3 | Kerning's Construction Site N: the Perceiver +2.0 ms over a sound map (1.5) | `movers` 1.3-1.4 ms in the Perceiver vs 0.9 alone: one sync less (the pack transfer overlapped with `expected`) |
| step 3 | 3 maps get no camera (Kerning City Construction Site, 3-Way, The Hill East): the minimap seed | the wide-maps plan (HANDOFF, after the tracker); `cam.py`'s whole-map search finds 3-Way's camera on 99 % |
| step 4 | finder's clouds followed within 1 px 86-89 % (95) | measure against clouds older than 1 s (a new cloud waits for the next finder run), and look at the 1-px misses (9 %): a second place check at +-1 px with sub-pixel speed |
| step 4 | the finder at <= 1 a second vs the share (0.2 s cadence: 93.2 / 90.6 %) | run the finder only on the whitened cells' bounding box (cheaper -> more often), or a finder run when a followed cloud's share drops |
| step 4 | Wild Boar frame = expected with clouds 92.5 % (93) | the same cadence fix (0.2 s gives 93.7 %) |
| step 4 | the finder on the main CUDA stream (design 3: its own): 10.5 ms p50, max 52.6 -> Perceiver p99 25.5 ms vs Line 1 18.4 | the finder on its own stream, read back on the next tick (a new cloud one frame later) |
| step 5 | Perion's Perceiver p50 +5.6 ms over Line 1 (gate 3.5): `clouds` 5.4 (own work ~3.1 + ~2.3 waiting for the expected picture), `movers` 1.3 | the finder on its own stream (step 4's row); the clouds' check and the movers' follow in one batch with one sync; the whitened check every 2nd frame |
| step 5 | a lost scene camera is never found again (the 6-a-second captures: 22.7 / 13.4 %): the Perceiver seeds from the tracker's stale camera | on a miss, also look around the minimap's seed (`SceneCamera.update` gets both; `locate` already takes both) - HANDOFF's open item "a lost scene camera" |
| step 4 | single clouds gone wrong (a swap with a cloud of the same picture: an 11.4 px line; a first opacity read badly: 0.106) | re-read the opacity on the first 5 fixes (median); a followed cloud's place checked against its line, a jump > 3 px = a new track |

## Its place beside the tracker
- Perception, one layer under the tracker: it changes each frame's facts on these maps, not how the tracker
  links them. The tracker plan (`docs/prompts/tracker-plan.md`) is designed on the 13 sound captures; from this
  plan it gets, per frame: `movers` (a mover not found = "the scene model does not know these pixels now"),
  `clouds`, and per sighting / look how thick a cloud lies over it. "Covered by cloud" (thickness > 0.9) is a
  fact of its own, expected to be rare: these clouds are never opaque.
- After step 1 the kept replay of the 9 forest captures is re-made (~13 % of the replay) and the tracker can be
  scored on them too; after steps 3 and 5 the replay grows by the newly hunted maps' captures.
