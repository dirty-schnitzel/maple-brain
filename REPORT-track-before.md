# REPORT: the kept replay of the bank, and today's tracker scored on it ("before")

Written 2026-11-21 by the executor of `docs/prompts/tracker-before.md` (HANDOFF step 2). Nothing in `maplebrain/`
changed: this session only measured. Code at `eefbe41` (`dev`), branch `tracker`. All numbers below can be
re-made from the kept replay without the GPU (the commands are at the end).

## In short
- **The kept replay exists:** today's Perceiver, unchanged, over **every frame** of 23 captures = 204,131 frames
  (56.7 minutes of footage at 60 a second), 51.6 minutes of GPU, 2.52 GB on F:. A tracker prototype now runs
  from it in seconds.
- **Perception is sound on 13 of the 23 captures** (175,340 frames: both Line 1 captures, Ant Tunnel I-IV, Dark
  Cave, Dangerous Steam, Deep Ant Tunnel II, Cave of Evil Eye I and IV, Drake Hunting Ground, Dungeon Southern
  Forest III). Not sound: **every Victoria Road forest map** in the bank (9 captures: the sky / moving clouds /
  light rays are not in the scene model: 80-93 % explained) and **Cave of Evil Eye III** (the camera was lost
  after a hole in the recording and never found again: 22 s).
- **Today's tracker, pooled over the 13:** it has a track on the mob on **96.4 %** of the moments the mob is in
  view; across a short blink (<= 0.1 s) it keeps the same identity **96.8 %** of the time, across 0.6-1.5 s only
  **31 %**, past 1.5 s **25 %**. Only **64 %** of mob lives keep ONE identity from start to end (2,442 extra ids
  over 1,775 lives). It notices a death at once (the die pose: p90 0 s), but a mob that goes without a die pose
  stays "alive" in the tracker p50 0.5 s, p90 5.9 s, max 19.6 s. 1.4 % of its live tracks are ghosts.
- **The truth itself, checked by eye (60 random cases):** of 40 stitched gaps 21 are right, 0 wrong, 19 can't be
  told (mostly: the mob was off the screen during the gap). Of 20 chain ends 15 are right, 3 wrong, 2 can't be
  told. So the truth is good where it can be checked, but its long gaps are mostly off-screen guesses - read the
  long-gap HELD numbers with that in mind.

## Words used here (in game terms)
- **Capture:** one stay on one map in the recording bank, id `SESSION#K`.
- **Scene model / camera:** the map drawn from the client files; the camera = where on the map the screen is,
  found by matching the frame against that drawing. **Explained:** a screen pixel looks exactly like the drawing.
- **The fit:** perception's per-frame list of mobs (type, pose, feet, facing, opacity) - what ONE frame shows.
- **Today's tracker:** `world.py`, the tracks the bot hunts with (ids, live / hit / hidden / dying / tentative).
- **Tracklet:** the fit's sightings of one mob on consecutive frames. **Chain** (the hindsight truth,
  `oracle.py`): tracklets of one mob joined across the moments it was not seen, looking both ways in time - one
  mob's life on screen. **Gap:** a moment inside a chain when the mob was alive but not seen (behind a player, an
  effect, the UI, off screen).
- **FOUND:** of the frames a chain shows the mob alive, the share where today's tracker has a confirmed track of
  that type within 24 px. **HELD:** across a gap, the track before it is the same track after it (same id).
  **SWITCHES:** extra track ids during one chain (0 = one identity from birth to death). **DEAD-LIVE:** seconds
  from the first die pose until the track stops saying alive. **VANISHED:** a chain that ends with no die pose
  and not at the screen's edge (covered, or died unseen) - how long its track stayed "alive" after the last
  sighting. **GHOST:** frames of a live track on screen with no chain within 40 px (a mob that isn't there).

## 1. Ported tools (`tools/perc/track/`, committed)
The folder the stopped plan session left (2026-11-17) now works on bank captures (`SESSION#K` through
`tools/perc/frames.py clip`; hold-out captures are refused) and still on run folders with a `ticks.jsonl`.
- `dump.py` - **the kept replay** (below). `dump_all.py` is gone (`dump.py --all` replaces it).
- `load.py` - `ticks(cap)`: a `record` capture has no ticks.jsonl, so its ticks ARE the kept replay's frames.
- `oracle.py`, `score.py` (now several captures + `--pool`), `e12_why.py` (several + pooled), `e10_basics.py`:
  as before, on captures.
- New: `sound.py` (step 3), `sheets.py` (step 5's sheets).

## 2. The kept replay
`F:\dev\maple-corpus\work\SESSION#K\track\`, per capture:
- `meta.json` - map, frames, frames without a camera, chunks, observe / decode seconds, bytes, the code's commit.
- `rows_NNN.pkl` - 6,000 frames per file, one dict per frame: `n`, `frame`, `t`, `C` (the scene camera or None),
  `cam`, `cam_src`, `me` (our name tag: centre x, top y), `me_map`, `map_pos`, `mobs` (today's tracks,
  `Track.as_dict`), `facts` (the whole FrameFacts v5: `fit`, `fit_hints` = the looks at today's tracks the fit did
  not find, `patches`, `drops`, `tags` = other players' name tags, hp / mp / exp, `scene_share`, ...),
  `explained` (shows / world on that frame), `world_px`, `ms` (the Perceiver's parts + `observe`).
- `bits_NNN.pkl` - the same frames' two bitmaps of the play area (1366 x 700): `world` (scenery a mob could stand
  in front of: known, no UI, no front layer) and `shows` (world AND the frame equals the drawing there).
- `sound_cells.npz` - step 3's per-map-place counts.

Loading (from the repo root, `.venv\Scripts\python`):
```python
import sys; sys.path.insert(0, "tools/perc/track")
import dump, load, oracle
rows = dump.rows("20261121_000219_2#0")            # every frame, no bitmaps (~10 s for the 30-minute capture)
for n, shows, world in dump.bits_rows("20261118_232410_1#13"): ...   # (700, 1366) bool arrays
tk = load.ticks("20261121_000219_2#0")             # the tick view score / oracle / e12 use
chains = oracle.chains(tk)                          # the hindsight truth
```
Re-making it: `python tools/perc/track/dump.py --all [--force]` (one process per capture; waits while the user is
recording).

| capture | map | frames | GPU s | GB |
|---|---|---:|---:|---:|
| 20261121_000219_2#0 | Line 1 <Area 1> (the design capture) | 110,082 | 1,678 | 1.34 |
| 20261120_235747_1#0 | Line 1 <Area 1> | 15,211 | 228 | 0.18 |
| 20261119_210307_1#0 | The Field South of Ellinia | 3,026 | 50 | 0.06 |
| 20261118_232410_1#0 / #1 / #2 / #3 | Ant Tunnel I / II / III / IV | 3,440 / 6,788 / 6,025 / 4,581 | 53 / 99 / 84 / 65 | 0.04 / 0.06 / 0.05 / 0.05 |
| 20261118_232410_1#4 / #5 / #7 | Dark Cave / Dangerous Steam / Deep Ant Tunnel II | 3,404 / 4,642 / 3,104 | 50 / 69 / 46 | 0.04 / 0.05 / 0.03 |
| 20261118_232410_1#9 / #11 / #12 / #13 | Cave of Evil Eye I / III / IV, Drake Hunting Ground | 8,923 / 2,695 / 2,012 / 841 | 144 / 31 / 30 / 12 | 0.09 / 0.01 / 0.02 / 0.01 |
| 20261119_123331_2#1 / #3 / #4 / #6 | L Forest I / III, Kerning Middle Forest I, Forest West of Henesys | 2,507 / 4,127 / 1,250 / 2,962 | 40 / 66 / 16 / 45 | 0.04 / 0.07 / 0.01 / 0.05 |
| 20261119_204522_1#1 / #3 / #4 / #5 / #7 | Rain-Forest E of Henesys, Forest S of Ellinia, Dungeon Southern Forest III, Forest S of Ellinia, Field S of Ellinia | 4,127 / 4,964 / 6,287 / 258 / 2,875 | 63 / 86 / 88 / 4 / 48 | 0.08 / 0.09 / 0.08 / 0.00 / 0.06 |
| **total** | 23 captures | **204,131** | **3,097** | **2.52** |

The choice (the prompt's rule): the dev group, full rate (> 45 frames a second), a map with a clean scene model,
labels farming or traveling; not the two `bot` hunts, not the every-3rd-frame recordings, never the hold-out
group. `20261119_204522_1#8` (Ellinia, 1 s) has no scene model. "GPU s" = the Perceiver's `observe` call, wall
clock (~15 ms a frame); decoding the video added ~6 minutes.

## 3. Is perception sound on each capture? (`sound.py`)
PLAN-data's stop rules as a verdict: the camera lost on > 1 % of the frames, or < 95 % of the known scenery
explained -> not sound, left out of section 4.

**How "explained" was measured - my reading, say if you want it otherwise.** The plain share (shows / world over
every pixel, column "raw") counts everything drawn in front of the scenery as unexplained: mobs, players, us,
effects, damage numbers, and the chat window when it is open. Taking out the boxes of what perception knows is in
front (column "scenery") still leaves players' effects and the open chat. So the verdict uses **"model"**: a map
place (4 x 4 px of the map) counts as the scene model's own miss when it is unexplained on more than half of the
frames that show it - what moves over the scenery is unexplained only now and then, a place the drawing gets wrong
is unexplained almost always. **The camera** is counted from its first fix to the exit fade (see the first
surprise below); the rule read literally (every frame) would also mark Ant Tunnel II / IV, Dangerous Steam, Deep
Ant Tunnel II and Cave of Evil Eye IV not sound (1.1-3.5 % lost, all in their first second).

| capture | map | camera % | lost: start / exit fade / other | raw % | scenery % | **model %** | tracks on screen p50 / max | ids | ms p50 / p90 | verdict |
|---|---|---:|---|---:|---:|---:|---|---:|---|---|
| 20261121_000219_2#0 | Line 1 <Area 1> | 100.00 | 0 / 0 / 0 | 96.5 | 98.2 | 99.1 | 4 / 14 | 1605 | 15.1 / 16.8 | sound |
| 20261120_235747_1#0 | Line 1 <Area 1> | 100.00 | 0 / 0 / 0 | 97.3 | 99.0 | 99.5 | 4 / 9 | 211 | 14.8 / 16.5 | sound |
| 20261118_232410_1#0 | Ant Tunnel I | 100.00 | 0 / 13 / 0 | 89.7 | 92.2 | 95.9 | 4 / 10 | 60 | 15.1 / 17.2 | sound |
| 20261118_232410_1#1 | Ant Tunnel II | 100.00 | 60 / 13 / 0 | 92.4 | 93.6 | 98.2 | 2 / 8 | 146 | 14.4 / 16.0 | sound |
| 20261118_232410_1#2 | Ant Tunnel III | 100.00 | 7 / 12 / 0 | 90.7 | 92.0 | 98.1 | 2 / 8 | 90 | 13.8 / 14.8 | sound |
| 20261118_232410_1#3 | Ant Tunnel IV | 100.00 | 61 / 12 / 0 | 90.3 | 92.0 | 95.6 | 3 / 10 | 82 | 13.8 / 15.3 | sound |
| 20261118_232410_1#4 | Dark Cave | 100.00 | 10 / 11 / 0 | 92.1 | 93.7 | 99.0 | 7 / 14 | 123 | 14.7 / 15.8 | sound |
| 20261118_232410_1#5 | Dangerous Steam | 100.00 | 61 / 12 / 0 | 93.0 | 94.0 | 97.8 | 3 / 8 | 69 | 14.4 / 17.0 | sound |
| 20261118_232410_1#7 | Deep Ant Tunnel II | 100.00 | 61 / 13 / 0 | 91.9 | 93.5 | 97.7 | 3 / 10 | 87 | 14.5 / 16.2 | sound |
| 20261118_232410_1#9 | The Cave of Evil Eye I | 100.00 | 0 / 10 / 0 | 87.5 | 88.8 | 96.7 | 4 / 11 | 183 | 15.7 / 18.9 | sound |
| 20261118_232410_1#12 | The Cave of Evil Eye IV | 100.00 | 61 / 10 / 0 | 92.6 | 94.0 | 97.7 | 4 / 10 | 45 | 14.6 / 16.7 | sound |
| 20261118_232410_1#13 | Drake Hunting Ground | 100.00 | 0 / 0 / 0 | 91.2 | 93.5 | 97.7 | 2 / 4 | 11 | 14.5 / 15.9 | sound |
| 20261119_204522_1#4 | Dungeon, Southern Forest III | 100.00 | 0 / 0 / 0 | 97.2 | 99.1 | 99.4 | 4 / 9 | 105 | 13.7 / 15.0 | sound |
| 20261118_232410_1#11 | The Cave of Evil Eye III | **50.86** | 11 / 0 / **1319** | 91.8 | 93.4 | 97.1 | 1 / 8 | 22 | 13.3 / 15.8 | **not sound: camera** |
| 20261119_210307_1#0 | The Field South of Ellinia | 100.00 | 0 / 0 / 0 | 82.9 | 84.1 | **92.0** | 4 / 10 | 53 | 16.1 / 17.8 | **not sound** |
| 20261119_204522_1#7 | The Field South of Ellinia | 100.00 | 0 / 0 / 0 | 80.7 | 82.1 | **90.6** | 7 / 12 | 73 | 16.6 / 18.0 | **not sound** |
| 20261119_204522_1#3 | The Forest South of Ellinia | 100.00 | 0 / 0 / 0 | 79.1 | 79.9 | **93.2** | 4 / 8 | 66 | 17.0 / 19.2 | **not sound** |
| 20261119_204522_1#5 | The Forest South of Ellinia | 100.00 | 0 / 0 / 0 | 81.2 | 81.8 | **82.8** | 1 / 2 | 2 | 15.6 / 16.4 | **not sound** |
| 20261119_204522_1#1 | The Rain-Forest East of Henesys | 100.00 | 0 / 0 / 0 | 77.2 | 77.7 | **79.6** | 3 / 8 | 95 | 15.1 / 16.4 | **not sound** |
| 20261119_123331_2#1 | L Forest I | 100.00 | 4 / 12 / 0 | 71.9 | 72.1 | **80.8** | 3 / 8 | 63 | 16.0 / 17.7 | **not sound** |
| 20261119_123331_2#3 | L Forest III | 100.00 | 13 / 13 / 0 | 71.2 | 71.4 | **83.8** | 4 / 14 | 160 | 15.8 / 18.2 | **not sound** |
| 20261119_123331_2#4 | Kerning City Middle Forest I | 100.00 | 11 / 3 / 0 | 87.3 | 87.6 | **92.4** | 0 / 2 | 4 | 13.1 / 14.2 | **not sound** |
| 20261119_123331_2#6 | Forest West of Henesys | 100.00 | 9 / 13 / 0 | 82.8 | 83.7 | **93.3** | 6 / 17 | 99 | 15.1 / 17.0 | **not sound** |

"tracks on screen" = confirmed tracks of today's tracker inside the screen per frame; "ids" = distinct confirmed
track ids over the capture; "ms" = the Perceiver per frame in this replay (the GPU had nothing else to do).
What the forest maps miss, looked at on three of them: the **sky** - a band of moving clouds above the trees on the
Henesys-side maps (Rain-Forest, L Forest I), the light rays on The Field South of Ellinia (the open item from
before), an animated portal. None of it is where mobs walk, but by the rule these captures are out.

## 4. Today's tracker against the truth (13 sound captures, every frame = the live rate)
| capture | lives (chains) | FOUND % | HELD % (gaps) | HELD <= 0.1 s | 0.1-0.3 | 0.3-0.6 | 0.6-1.5 | > 1.5 s | one track per life % | GHOST % | VANISHED stays live p50 / p90 / max s |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| Line 1, 30 min (`000219_2#0`) | 1,074 | 96.8 | 84.6 (1,913) | 96.9 | 94.7 | 80.8 | 43.3 | 28.2 | 66.1 | 0.75 | 0.73 / 7.1 / 19.6 |
| Line 1, 4 min (`235747_1#0`) | 166 | 96.9 | 87.0 (253) | 99.3 | 97.8 | 73.7 | 36.4 | 36.8 | 73.5 | 0.44 | 1.65 / 3.6 / 5.0 |
| Ant Tunnel I | 54 | 97.1 | 88.3 (60) | 100 | 93.8 | 100 | 0 (4) | 0 (2) | 77.8 | 3.36 | 0.52 / 1.5 / 2.2 |
| Ant Tunnel II | 48 | 91.9 | 76.5 (162) | 89.9 | 78.3 | 75.0 | 0 (6) | 27.3 | 50.0 | 0.86 | 0.41 / 0.5 / 0.5 |
| Ant Tunnel III | 42 | 93.4 | 85.7 (84) | 100 | 80.6 | 100 | 0 (4) | 50.0 | 54.8 | 1.30 | 2.57 (1) |
| Ant Tunnel IV | 64 | 98.0 | 84.6 (65) | 92.9 | 100 | 77.8 | 25.0 | 25.0 | 73.4 | 3.00 | 0.5 / 0.5 / 0.5 |
| Dark Cave | 71 | 96.6 | 81.7 (104) | 97.9 | 88.6 | 85.7 | 11.1 | 0 (5) | 59.2 | 1.90 | 0.52 / 2.1 / 8.6 |
| Dangerous Steam | 40 | 94.8 | 87.0 (69) | 100 | 96.6 | 71.4 | 50.0 | 0 (4) | 52.5 | 3.64 | 0.5 / 1.1 / 2.0 |
| Deep Ant Tunnel II | 29 | 89.4 | 73.1 (108) | 85.2 | 76.5 | 63.6 | 0 (6) | 0 (3) | 41.4 | 1.94 | 0.67 / 3.4 / 4.9 |
| Cave of Evil Eye I | 90 | 97.9 | 79.8 (326) | 98.6 | 97.3 | 86.8 | 13.3 | 0 (16) | 43.3 | 6.23 | 0.52 / 6.5 / 12.8 |
| Cave of Evil Eye IV | 25 | 99.8 | 77.3 (44) | 100 | 100 | 100 | 20.0 | 0 (2) | 48.0 | **12.54** | 0.98 / 1.2 / 1.3 |
| Drake Hunting Ground | 12 | 86.9 | 100 (14) | 100 | 100 | - | - | - | 83.3 | 6.96 | 0.52 (1) |
| Dungeon, Southern Forest III | 60 | 93.6 | 89.7 (97) | 98.1 | 100 | 100 | 0 (3) | 14.3 | 65.0 | 0.16 | 0.52 (1) |
| **POOLED** | **1,775** | **96.4** | **83.7 (3,299)** | **96.8** (1,657) | **92.6** (787) | **81.9** (348) | **31.4** (258) | **24.9** (249) | **64.4** | **1.36** | **0.52 / 5.9 / 19.6** |

Also pooled: HELD for gaps within 220 px of us **90.8 %** (709 / 781); 535 more gaps were of mobs today's tracker
had no track on at all; **DEAD-LIVE** (n 911) p50 / p90 0.0 / 0.0 s, max 5.7 s, > 0.1 s on 3 %; VANISHED n 198;
ghosts come from 383 tracks. Across a gap of 0.3 s or more the mob usually moved > 30 px (62 % of such gaps on
the design capture), and that is where HELD falls.

**Why chains are lost** (`e12_why.py`, pooled): of **2,442 id switches** - 903 "the old track is still there,
near" (two tracks on one mob, or two mobs crossing), 873 "the old track ended while the mob was seen", 528 "the
old track ended during a gap" (today's timeouts), 79 old track far away, 59 "the old track turned dying while the
mob lives". Of **24,216 alive-and-in-view frames without a track** - 20,633 (85 %) the body is < 60 % on the
screen (the new-track rule waits until a mob is mostly in view), 3,428 a track of ANOTHER type is there (none on
the Line 1 captures: the Ant Tunnel / Cave maps, look-alike mushrooms), 141 off any platform, 14 other.

## 5. The truth's own check, by eye
60 cases picked at random over the 13 sound captures (`sheets.py --seed 1`): 40 stitched gaps - 20 among the
3,968 gaps <= 0.5 s and 20 among the 742 longer ones (uniform picks would be almost all 1-3 frame blinks) - and
20 of the 1,738 chain ends that are not the capture's end. Each case is one row of 7 crops around the mob. Sheets
and verdicts: `F:\dev\maple-corpus\work\track-before\sheets\` (`sheet_NN.jpg`, `cases.json`, `verdicts.json`).

| | right | wrong | can't tell |
|---|---:|---:|---:|
| gaps <= 0.5 s (20) | 15 | 0 | 5 |
| gaps > 0.5 s (20) | 6 | 0 | 14 |
| chain ends (20: 9 died, 8 edge, 3 vanished) | 15 | 3 | 2 |

- **Gaps right:** the mob behind a player, our swing, a skill or level-up effect, damage numbers, a drop, the
  minimap window, the keycaps, the open chat (visible through it), see-through while spawning - each time the
  same mob on both sides. Two were gaps where the mob was in plain view and the fit missed it (a flying Stirge
  over 0.65 s; a Bubbling next to another).
- **Can't tell:** 13 of the 19 were the mob **off the screen** during the gap (top, bottom or side edges, up to
  3.4 s, the camera moving) - the truth's stitch is plausible (same type, same place) but no frame shows it. 3 were
  two or three mobs of one type crossing (which is which can't be seen at this size); 3 behind the keycaps / the
  open chat.
- **Ends wrong (3, all on the design capture):** #48 (t 1515.22) ended as "died" on a die pose, yet a whole
  Bubbling stands in that place 0.1-0.3 s later and is hit and dies at +0.7 s; #51 (t 789.40) "vanished" while the
  Bubbling stands plainly in place for the next 1.5 s; #53 (t 758.72) "vanished" while still visible being hit in
  a crowd of Bubblings (it died ~0.5 s later, a meso fell). So a chain can end early when the fit drops a mob it
  can see and the stitch then joins its next tracklet to nothing (or to a neighbour).
- So: the truth's short gaps are trustworthy; its long gaps are mostly off-screen and unproven; ~1 in 7 "ended"
  chains did not really end there.

## What surprised me (listed, nothing fixed)
1. **The camera waits ~1 s on every map entry.** After a portal the new map is fully on screen ~60 frames before
   our character is drawn, and the camera's first seed needs our name tag (plus the minimap). Every capture that
   starts at a portal loses its first ~1 s (7-61 frames). The exit fade (10-13 frames, the screen going black) is
   a real "no map".
2. **A lost camera never came back on Cave of Evil Eye III** (`20261118_232410_1#11`): the recording has a 6.4 s
   hole (no frames between t 923.06 and 929.45 - the capture's rate is 52.8, not 60), after which the camera was
   never found again for the last 22 s although the map and our character are on screen. The seed is the last
   camera, which is 6 s stale; a live hunt after a long freeze would sit there blind the same way (cf. HANDOFF's
   "a lost scene camera" open item).
3. **Every Victoria Road forest map in the bank is "clean" by the map list yet not sound** (80-93 % explained by
   the model): the sky's moving clouds (Henesys side), the light rays (Ellinia's field), an animated portal. That
   is all 7 Victoria Road forest maps recorded so far (9 captures, 26,096 frames = 13 % of the replay); the sound
   set is caves, dungeons and the subway.
4. **The chat window was open** in the 2026-11-18 / 19 exploration captures (seen on Drake Hunting Ground, the
   Cave of Evil Eye maps, Deep Ant Tunnel II); mobs behind it are seen through it or lost. The 2026-11-20 / 21
   Line 1 captures have it minimized.
5. **Cave of Evil Eye IV: 12.5 % ghost track-frames**, Cave of Evil Eye I 6.2 %, Drake Hunting Ground 7.0 % -
   against 0.2-0.8 % on Line 1 and Dungeon Southern Forest III.
6. **A track of the wrong type sits on the mob** on 3,428 frames (Ant Tunnel / Cave maps only).
7. **The truth is ambiguous by construction:** 77-99 % of its stitched gaps had other candidate ends / starts
   competing for them (`amb`); its long gaps are mostly off screen (section 5).
8. Speed: the Perceiver's median per frame was 13.1-17.0 ms (p90 14.2-19.2 ms); only The Forest South of Ellinia
   is over the 16.7 ms of 60 a second at the median, and the p90 is over it on 10 of the 23 captures.

## Commands
```powershell
.venv\Scripts\python tools\perc\track\dump.py --all                      # the kept replay (skips what exists)
.venv\Scripts\python tools\perc\track\sound.py CAP [CAP ...] --json OUT   # section 3
.venv\Scripts\python tools\perc\track\score.py CAP [CAP ...] --pool       # section 4 (--rows FILE: a prototype's tracks)
.venv\Scripts\python tools\perc\track\e12_why.py CAP [CAP ...]            # section 4, why
.venv\Scripts\python tools\perc\track\sheets.py CAP [CAP ...] --out DIR   # section 5
```
The 13 sound captures: `20261121_000219_2#0 20261120_235747_1#0 20261118_232410_1#0 20261118_232410_1#1
20261118_232410_1#2 20261118_232410_1#3 20261118_232410_1#4 20261118_232410_1#5 20261118_232410_1#7
20261118_232410_1#9 20261118_232410_1#12 20261118_232410_1#13 20261119_204522_1#4`. Step 3's per-capture results:
`F:\dev\maple-corpus\work\track-before-sound.json`.
