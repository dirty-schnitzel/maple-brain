# PLAN: the recording corpus - many maps recorded cheaply, then every rework tested on all of it
**Status: OK'd by the user 2026-11-17** (by Fable, xhigh: a review of the proposal made in the session "data" the
same day; sections 4-5 then redone to the user's three concerns: nobody looks at recordings to file them, no fixed
list of maps, short stops). **Session 1 BUILT 2026-11-17 on branch `data`** (gates a, d, e passed; b, c, f wait
for the user's walk + a `serve --video` hunt; what was decided while building: "Session 1 as built" after section
5, details in HANDOFF's START HERE). Executors: Opus, 3 sessions (prompts at the end) + about 2 hours of the user's
own play. Evidence scripts: `tools/data/` (each file's docstring says what it measures).

## 1. Why
Every rework so far was designed and tuned on a few minutes of play:
- The native recordings hold **7 maps**. 5 of them are maps perception hunts on; together they show **11 of the 51
  mob types** and **3 of the 13 background sets** those maps have (`tools/data/map_cover.py`; a mob type counts
  on a map with 3+ spawn points of it).
- The by-eye reference is ~300 labelled frames. 0 misses in 300 only shows an error rate under ~1 %; the targets
  (>= 99 % of mobs found, <= 1 false mob per 1000 frames) cannot be shown on it.
- Thresholds (the 0.75 match score and others) were tuned on the same frames they are graded on.
- Live comparisons are one run against one run on crowded maps (HANDOFF: "not a clean A/B, competition differs").

The designs themselves mostly come from the client files (the scene render, the camera arithmetic, the item
pictures), so they are expected to hold. What is untested is the tuned layer on top and every mob type, background
and situation we never recorded. This plan builds the data to test that, once, and keeps it as the permanent check.

## 2. The review: what stays, what changes
**Approved as proposed:** lossless video instead of PNG; hold-out maps we never tune on; a validation pass of perception (not a redo); the loot rework continues and gets the same
pass later; record before the tracker redesign (step 4).

**Edits (each from a measurement in section 3):**
1. **Measure coverage from the game data.** The game has 51 mob types and 13 background sets on the maps
   perception hunts on; the corpus is judged by how many it holds, not by a count of maps. (First written as a
   list of 10 maps to record; the user wants no list, so it is a report after each recording: edit 8.)
2. **Record a few maps perception refuses today.** 95 of the 205 maps with mobs (46 %) have moving backgrounds
   (clouds, scrolling layers), and hunts are refused there - Perion Street Corner and Land of Wild Boar among them.
   More data on the other maps says nothing about these. A few recordings now are the data for that later step.
3. **The corpus finds failure kinds; it does not prove a percentage.** 300 separate cases show (95 % sure) every
   failure kind that hits 1 % of cases or more. Proving ">= 99 %" on a detector that is truly 99.5 % needs 1,500+
   cases, so per-scenario percentages are not gates. The headline number is pooled over the whole corpus, with its
   interval. (Correction to the proposal: with 1 miss allowed the count is ~475, with 2 ~630, not "about 500".)
4. **No tracker-agreement as truth.** The tracker is what step 4 redesigns. The scalable miss-finder is the one the
   loot work used: whatever stays in one map place for a while and nothing names (not scenery, mob, character or
   drop) is put on a sheet and looked at by eye. Plus synthetic frames per map and by-eye labels on picked frames.
5. **The corpus lives on E: (Mammoth, 3 TB free), not in `runs/`.** C: has 60 GB free; `runs/` is 49 GB and is
   wiped by habit. The corpus is read-only, has a manifest, and the tools refuse the hold-out part unless asked.
6. **The odd moments, once each somewhere in the walk:** a rope, a pile of drops, the inventory / skill /
   world-map windows open. Fighting alone never shows them.
7. **Do not convert the existing PNG recordings yet.** The loot worktree reads them through junctions. They are
   copied into the corpus as video; the PNG originals go only after loot part 1 is merged (frees ~12 GB on C:).
8. **Record the user's walk, not a list** (the user, 2026-11-17). A map is played two ways - traversal (cross it
   fast) and farming (the most EXP, where the other players let you) - and how one farms differs by class, level
   and build. So this corpus does not try to hold "human play": it holds what is true for every character. The
   user walks the maps and paths they choose, stops briefly where it is worth it, and the tool works out the
   rest: which maps, where the fighting was, what is covered (section 4). The two modes stay the frame for the
   brain later.
9. **Capture now the one thing no later tool can recover: why the player did something** (the user, 2026-11-17).
   Where one farms is not a fixed property of a map. It moves with the other players: sharing a map platform by
   platform, being kill-stolen until one leaves, party members dividing the map ("I take bottom"), kill-stealing
   on purpose. Modelling that is far down the road (after perception, the model and execution). But where the
   other players stand and who kills what stays in the pictures and can be read out whenever perception learns to;
   the player's reason is nowhere in them. So, both optional: a **marker key** during recording (a key the game
   does not use; keys are logged with their times already) with one line per mark in `RUN/notes.txt` afterwards
   ("2:10 kill-stolen by a mage, moved to the bottom"), and real play recorded whenever (group E), because these
   situations cannot be staged. Nothing else of the social layer is built or labelled now.
   **The key log holds whatever is typed while the game is focused, chat included.** It stays on this PC (the
   corpus is never in git). Start a recording only after logging in.

## 3. What was measured (2026-11-17)
| # | Question | Result |
|---|---|---|
| D1 | Which format? (`codec_bench.py`, 300 native PNG frames each of an Ant Tunnel IV hunt and an observe run) | **HEVC lossless on the GPU's video encoder** (`hevc_nvenc -tune lossless`, pixel format `gbrp`): 0.17-0.25 MB a frame = 4-6x smaller than PNG, bit-exact back, 3.4 ms of CPU a frame (PNG writer: ~40). CPU lossless H.264 is the same size at 26 ms. FFV1 is larger than PNG. "Near-lossless" moves pixels by up to 66 levels: rejected |
| D2 | A keyframe every 2 s (`-g 120`), and is jumping to a frame exact? (`video_safety.py`, 600 frames) | 5.7x smaller than PNG (5 % cost); OpenCV reads 600 / 600 frames identical; 60 random jumps: 60 exact, 0.25 s each (reading in order: ~400 frames a second) |
| D3 | What if the recording is killed? | The bot (python) killed: ffmpeg finishes the file by itself, 200 / 200 frames. ffmpeg itself killed: the last ~0.5 s is lost (373 of 400 read back, all exact), and jumping in that file is wrong until it is repaired (`ffmpeg -i x.mkv -c copy fixed.mkv`) |
| D4 | Does recording slow the bot? (`paced_enc.py` at a real-time 60 fps beside `tools/perf/bench.py`, the game running, 4 alternating pairs) | tick p50 14.3-14.9 ms alone, 14.5-15.4 while encoding: **+0.3 ms** (2 %), 0 late frames. In-process cost (the copy + the pipe) is Session 1's live gate |
| D5 | Which maps? (`map_cover.py`, from assets/mcw + assets/scene) | 205 maps with mobs: 110 clean, 95 moving backgrounds. Mob types with 3+ spawn points on some map: 72 (51 on clean maps); background sets 20 (13). Recorded: 11 / 51 and 3 / 13. 10 more clean maps (strongest mob <= lv 45) add 25 of the missing ones; the rest need a stronger character |
| D6 | Disk | C: 60 GB free (runs/: 15.6 GB native PNG + 25.8 GB old JPEG frames). E: Mammoth 3.0 TB free |
| D7 | Can a walk be cut into its maps with nobody looking? (`map_along.py`: the bot's map recogniser on single frames, 60 along each of 10 recordings of 7 maps) | 600 looks: **538 right, 62 "can't tell", 0 wrong**; 48 ms a look (a 2-hour walk at one look a second: ~6 minutes). "Can't tell" = the minimap closed (8), or dragged partly off the screen (51, one recording): never a wrong map. Real map changes (loading frames) are not in today's recordings: gate (f) |
| D8 | A long recording as chunk files? (ffmpeg's segment writer, a chunk every 120 frames, 600 frames) | 5 files of exactly 120 frames, 600 / 600 read back in order bit-identical, the same size as one file |

**Not measured: the size at 60 fps** (the frames above are every 3rd = 20 fps). Neighbouring frames are closer, so
the estimate is 0.3-0.7 GB a minute; the whole corpus then 40-100 GB. Session 1 reports the real number.

## 4. What to record: the user's walk
**No list of maps.** The user walks the popular and iconic maps on the paths they choose, with the recorder on:
one recording per play session, as long as it runs. The native 1366x768 window, chat minimized, **the minimap
open in its usual place** (the tool cuts the walk into maps by it, D7). Nothing is tagged or noted by hand.
- **On a map worth a stop (2-3 minutes):** kill each mob type a few times - about 5 each where the map has
  several of them - and stand on as many platforms as comes naturally, then move on. A death lasts under a
  second, so 5 give a few hundred frames of it; the common mobs come back on other maps anyway.
- **Maps only crossed** are data too: travelling at full speed is the harder picture (fast camera, mobs passed).
- **Somewhere along the walk, once each:** hang on a rope; open and close the inventory, the skill window, the
  world map and the full chat; let a few drops lie before picking them up, once near a ladder or post.
- **Optional, skip it if it distracts:** the marker key (edit 9) when another player changes what you do.
- Crowded is welcome: it is the hard case, and on popular maps it is the normal one.

**What this walk is for:** what is true for every character - what the game draws on each map, where its
platforms are, how the game moves things. More maps beat more minutes. **What it is not for:** how a human
farms (class, level and build decide that) and a human's farming rate; those are recorded later, per character,
when the brain needs them (group E below is the place).

**The to-do list is replaced by a report.** After every `corpus.py add` the tool prints what the corpus holds:
per map its minutes and attack presses, and after Session 2's replay also the deaths seen per mob type, the
platforms stood on out of all, and the share of the map the camera saw; in total the mob types and background
sets covered out of those the game has (map_cover), and for each one not seen yet the maps it lives on. That is
information for the next walk, not a task. For reference, today's corpus (7 maps) holds 11 of the 51 mob types
that clean maps have and 3 of their 13 background sets; 10 well-chosen maps would add the rest a level-45
character can reach (`python tools/data/map_cover.py --max-level 45`).

**Hold-out maps are chosen by the tool, not by anyone:** a map new to the corpus goes to the hold-out group when
`crc32(map id) % 4 == 0` (about every 4th map), with every later recording of it; the 7 maps already used stay
dev. Nobody tunes on hold-out maps; they run only at gates (section 6). `corpus.py add --dev MAP` moves a map to
dev before its first gate, for a map the user wants worked on.

**Group E - real play, open-ended (edit 9):** whenever the user farms for real, the same recorder can stay on.
Sharing a map, kill-stealing and party play get into the corpus this way; they cannot be staged. Estimated
20-40 GB an hour on E: (measured in Session 1). No pass of this plan depends on it.

**When to record more:** the report says what is missing; the validation pass says where perception fails
(section 6). Both are reasons to walk a map again, never obligations.

## 5. The recorder and the corpus (Session 1)
- **`python -m maplebrain record [OUT]`** (default `E:\maple-corpus\incoming`; start / stop keys as `serve`): the
  user plays, nothing is pressed. Every frame the game draws -> video; the player's keys -> keys.jsonl (the
  observe key logger); per frame its number, time and the cursor -> frames.jsonl. **No perception runs**: the
  bot's perception is tied to one map, a walk crosses many, and the corpus replays perception offline anyway.
  One look a second for the Lie Detector stays (the siren, as `watch`).
- **Video:** one ffmpeg process fed by a writer thread (`-f rawvideo -pix_fmt bgr24 -s 1366x768 -r 60 -i - -c:v
  hevc_nvenc -tune lossless -preset p4 -pix_fmt gbrp -g 120 -forced-idr 1 -f segment -segment_time 300
  -reset_timestamps 1 frames_%04d.mkv`): 5-minute chunk files of 18,000 frames (D8), so a crash costs the tail
  of one chunk and a long walk is not one 60 GB file. The frame's buffer goes straight to the pipe; a full queue
  drops the frame (recorded in frames.jsonl), the game loop never waits. The same writer serves `run` / `serve`
  as `--video` (the bot's hunts: `ticks.jsonl` keeps `"frame": "000123.png"` names = the tick, so old readers
  and labels keep working). `--frames-png` stays until Session 3 is done.
- **Reader:** `tools/perc/frames.py` `read(run, name)` returns the PNG file if `frames/<name>` exists, else the
  video frame (chunk = n // 18000; reads forward when the frame is near, jumps otherwise). Port only the tools
  the validation pass uses (`replay/run.py`, `label_eval.py`, labels, synth); the rest get PNGs on demand from
  `tools/data/unpack.py RUN [names]`.
- **`tools/data/corpus.py add RUN`** - nobody looks at a recording to file it:
  1. checks it (every chunk reads, frames = frames.jsonl, the window is native);
  2. **cuts it into maps**: the bot's map recogniser (nav/identify.py) on one frame a second; the map changes
     only when a look names a different map - "can't tell" (minimap closed, covered, moved) keeps the map before
     it; each change is then narrowed frame by frame to the loading frames between the two maps. A stretch never
     named is settled by the portals (the map between two known maps must connect them) or stays "unknown":
     kept, listed in the report, out of the per-map numbers;
  3. per map segment, from keys.jsonl: the attack presses and the time of the first one (a map with none was
     crossed, the others visited), the marks;
  4. writes one line per segment to `E:\maple-corpus\manifest.jsonl` (recording, frame range, map, group dev /
     holdout by the rule of section 4, minutes, attack presses, crossed / visited, date, client data build, marks)
     and moves the recording to `E:\maple-corpus\recordings\`. Nothing is re-encoded.
  `corpus.py list` prints the report of section 4. Tools take segments from the manifest and refuse hold-out
  segments without `--holdout`, logging each use.
- **Existing native PNG recordings:** added as copies in video form (bit-exact check per recording), as dev. The
  originals stay until loot part 1 is merged (edit 7).

**Gates (Session 1):** (a) video frames are bit-identical to PNGs of the same frames (unit test on fixture frames
+ one existing recording converted and compared in full, across a chunk border); (b) live, the user's first
recorded walk of 10+ minutes through 3+ maps to E:: 0 dropped frames, ~60 frames a second in the file, the game
as smooth as without it (the user's word), and a `serve --video` hunt's tick p50 / p90 within 1 ms of one without;
(c) the measured GB per minute at 60 fps, reported; (d) the recorder killed mid-recording leaves readable chunks;
(e) pytest green, the bot-speed line unchanged; (f) that walk is cut at the right frames, every map named right
(the frames before and after each cut looked at by eye, once: the proof that nobody has to look afterwards).
**Stop rules:** drops or a tick cost over 1 ms -> stop with numbers (fallbacks to weigh then: the faster preset
p1, every 2nd frame, the CPU encoder on spare cores). A cut or a map name wrong -> stop with the frames: wrong
names poison everything after; "unknown" stretches are fine.

**Session 1 as built (2026-11-17; the executor's additions, the user's word changes them):**
- The cut keeps the map over frames it can't name only up to 2 s (`KEEP_S`, a guess until a real loading screen
  is measured): 35 of the 336 maps have no minimap (shops, salons, job halls), so "town -> shop -> town" would
  have been filed as the town. A longer unnamed stretch is its own segment: named by the portals only when the
  maps before and after do not connect directly and exactly one no-minimap map connects them, else "unknown".
- A frame where the recogniser finds no minimap window (something drawn over its frame: 77 frames in 3 of the old
  recordings) is the same map when that map is still the clear winner inside the window measured on the nearest
  named frame. It only confirms a map already named beside it.
- A look names a new map only when the next 2 frames and the look a second later name it too.
- Gate (d) found: a killed ENCODER leaves one out-of-order frame at the end of the cut chunk (the picture of 4
  frames later); `corpus.py add` keeps only the frames before a hole in the times. Killing the recorder itself
  loses only the queued frames.
- The marker key is F12 (`Keys.note`); a `record` recording numbers its frames from 0; chunk files sit flat in
  the run folder; an old PNG recording is one segment with the map of its log.

**2026-11-18 (the user): this recorder is the final way data is collected; its bank serves perception, the live
map + tracking and later AI training; its footage replaces the gated checks.** Built for it: the mouse buttons per
frame (`frames.jsonl` `"b"`), `session.json` beside every recording (the config, the code's commit, the client
build, the wall clock), `record --label NAME` (what the player set out to do), and the corpus folder as one parameter
(`config.CORPUS`: `F:\dev\maple-corpus` for now - an SSD; E:, a USB hard disk, later). **And the bank is filed
per map** (the user: "filed per map, build it"), which replaces section 5's "one manifest line per segment of a
recording kept whole": `maps\<map name> (<id>)\<date>_<time>_<labels>_<length>_sK\` holds one stay's frames,
written again losslessly by `add` and proven identical frame by frame (a fingerprint per frame) before the
original leaves `incoming\`; hold-out maps under `holdout\`; `sessions\<recording>\` keeps the session's small
files and its route; a stay's permanent id is `RECORDING#K` (tools, labels, gates), its folder name is for people
(labels = the player's from `record --label NAME`, then the one worked out per stay: farming / traveling / town /
idle / bot - words, nothing more: the user, 2026-11-19); `corpus.py verify` re-checks the files. Detail:
tools/data/corpus.py's docstring, HANDOFF. Decided the same day: **sound is not recorded** (vision only); **one
gate list on the bank** for the perception and loot gates is agreed as a future task, designed once the corpus
has substance (HANDOFF "FUTURE TASK").

**2026-11-19, Session 1b on the user's first walk** (16.4 minutes down the Ant Tunnel: 14 maps, 13 map changes):
gate (b) PASSED in its recording half (59,163 frames, 60.0 a second, 0 dropped, 0.155 ms a frame on the loop) -
**its tick-cost half is open until the user records the two hunts**; gate (c) PASSED (0.38 GB a minute, 23 GB an
hour); gate (f) PASSED (all 13 cut sheets by eye: every cut on the portal's fade, every name = the minimap's
title; loading screens 0.22-0.60 s, so `KEEP_S` = 2 s stays). Filed: 14 captures, every frame read back
identical, ~46 minutes of unattended tool time per recorded hour. The bank: 25 captures on 18 maps, 37 minutes -
**not enough for Session 2**: the walk of section 4 is still to be recorded. Detail: HANDOFF.

## 6. The validation pass (Sessions 2 and 3)
Perception runs **unchanged** over the dev group; this pass measures and lists, it fixes nothing.
1. **Per map, automatic** (`tools/data/replay_all.py`, the live Perceiver on every frame): share of frames with
   the scene camera found; share of the known scenery's pixels the render explains; mobs tracked; tick time.
2. **The independent look** (edit 4): unexplained things that stay in one map place -> one sheet per map, looked
   at by eye, sorted into kinds (a missed mob, a mob part, a player's effect, scenery the render lacks, ...).
3. **Synthetic frames per map** (tools/perc/synth, each map's own mobs pasted at known places on its real frames):
   exact found / false counts per mob type - the check of every mob type's pictures.
4. **By-eye labels:** ~30 picked frames per new map (even + hard), `label_eval.py`. Claude's labels stay the
   reference.
5. **Report:** per-map table, visited and crossed maps apart; pooled found / false rates with 95 % intervals;
   the failure kinds, each with its count, its maps and example frames, split into "a threshold or a missing
   case" and "a structural assumption"; the coverage numbers of section 4 written back to the manifest.
6. Only then the hold-out group runs once (`--holdout`), as the honest number. Fixes are planned in a review
   session after the report, checked on dev, confirmed on the hold-out.

**Stop rules:** the scene camera lost on more than 1 % of a clean map's frames, or under 95 % of its known scenery
explained -> stop that map and report (structural; nothing downstream means anything there). A scenario with fewer
than ~300 separate cases across the corpus is reported as "too few", with the map to record more on.

## 7. Rules that hold from now on
- New thresholds and designs are tuned on `dev` only; every plan's gate names the corpus maps it ran on.
- A live run confirms that a change works; **replays decide whether it is better.** A live difference counts only
  when it is larger than the spread of repeated identical runs (measure that spread once: 3 identical 5-minute
  hunts on one map, when convenient).
- A new mob type, background family or failure seen live -> a recording of it joins the corpus.

## 8. Order
1. Session 1 (the recorder + corpus tools; its gates need one short walk by the user), then the user walks: a few
   hours, in as many sittings as they like; `corpus.py add` after each.
2. Sessions 2-3 (validation pass + labels), then a review session: the fixes, and **step 4 (the tracker plan) on
   the corpus** - it is about crowds, respawns and mobs hidden under effects, exactly what 7 maps show worst.
3. The loot rework continues in its worktree throughout; its tools get the same pass after its merge. Its
   independent-look tool is reused in Session 2 (merge first, or copy the one file).

## 9. Decided (the user, 2026-11-17)
1. Step 4 (the tracker plan) waits for the corpus.
2. The old JPEG frames in `runs/` were deleted the same day (73,871 files, 25.8 GB: lossy, most from before the
   native window, read by nothing). Logs, ticks and saved pictures of those runs stay; the PNG recordings stay.

## 10. Session prompts
**Session 1 (Opus, high):** "You are the executor of PLAN-data.md, Session 1. Read PLAN-data.md top to bottom
(the work is section 5; sections 3 and 4 say what was measured and what the recordings will be) and HANDOFF's
START HERE. Branch `data` off `dev`. Build exactly what section 5 says: `python -m maplebrain record`, the video
writer (also `--video` on run / serve), the frame reader in tools/perc/frames.py, tools/data/unpack.py and
tools/data/corpus.py. Port only the tools section 5 names; build nothing of section 6. Run gates (a), (d), (e)
yourself. For (b), (c) and (f) give me the exact commands for a recorded walk of 10+ minutes through 3+ maps and
for a short `serve --video` hunt, wait for my runs, then report the numbers in plain words. Follow the stop
rules: stop with numbers, no workarounds. Leave alone: the native PNG recordings in runs/ (the loot worktree
reads them; they enter the corpus as copies only), tools/perc/track/ (another session's work), the `loot`
branch. At the end update HANDOFF, commit and push `data`."

**Session 1b (Opus, high; written 2026-11-18, when the first walk was in `incoming\`; run on that walk
2026-11-19 - the same prompt serves every later batch of recordings):**
```
You are the executor of PLAN-data.md, Session 1b: Session 1's live gates on my recordings, then the filing.
Read HANDOFF's START HERE and the docstring of tools/data/corpus.py; PLAN-data.md section 5 has gates (b), (c),
(f) and the stop rules. Branch `data` (checked out). Python = .venv\Scripts\python. The corpus is
F:\dev\maple-corpus - never C:.

My recordings are in F:\dev\maple-corpus\incoming\ (the first walk is 20261118_232410_1; take every folder
there). A `record` or `watch` process may be running: never stop it, and leave alone a recording that is still
being written (video.json says "closed": false while a recorder is loaded).

1. Verify each recording BEFORE anything is filed:
   - the last lines of its log.txt: frames a second, dropped frames, the gaps, GB a minute, the queue, the cost
     per frame;
   - `python tools\data\corpus.py add --dry <folder>`: the check and the cut. Look at EVERY cut sheet in
     work\cuts\<folder>\ by eye: is each map change cut at the right frames, and is every map named right (the
     minimap corner and the map's name on screen against the name the tool gave)? Measure how long the loading
     screens really are (cuts.json) against KEEP_S = 2 s;
   - session.json is there (config, commit), frames.jsonl has the mouse, keys.jsonl has my keys.
2. The gates: (b) 0 dropped frames, ~60 frames a second; and the `speed:` lines of my two hunts - one
   `serve ... --video` in incoming\, one without in runs\v2\ - within 1 ms of each other. If the hunts are not
   there, say so with the two commands and go on with the rest. (c) GB a minute. (f) the cuts and the names.
3. Stop rules, no workarounds: drops, or a tick cost over 1 ms -> stop with the numbers (fallbacks to weigh:
   preset p1, every 2nd frame, the CPU encoder). A cut or a map name wrong -> stop with the frames and do not
   file that recording. "unknown" stretches are fine.
4. If a recording passes: file it with `add --keep`. Then look at what was filed - its route.txt, each
   capture's sheet.jpg, and whether the names fit what the sheets show (farming / traveling / town / idle) - and
   run `python tools\data\corpus.py verify --frames`. Only then remove the kept original from incoming\.
5. Report in plain words: each gate's numbers, each walk's route with its captures, how long filing took per
   recorded hour, what the corpus holds now (`corpus.py list`), which maps went to hold-out, and anything that
   surprised you.
6. Then close Session 1: HANDOFF and PLAN-data say which gates passed with their numbers and whether KEEP_S
   stays; commit and push `data` (I merge). Say whether the corpus is enough to start Session 2 (section 6) or
   what is still missing - do not start Session 2.

Leave alone: runs/ (the PNG recordings: the gates read them), tools/perc/track/, E:\maple-corpus. Nothing is
ever pressed into the game.
```

**Session 2 (Opus, high):** "Read PLAN-data.md section 6. The corpus is recorded (`python tools/data/corpus.py
list`). Build tools/data/replay_all.py and run items 1-3 on the dev group only; pick the frames for item 4. Do not
open the hold-out group. No fixes, no threshold changes. Report per map in plain words; follow the stop rules."

**Session 3 (Opus, high):** "Read PLAN-data.md section 6. Label the picked frames by eye (reference = your
labels), run label_eval, and write the report of item 5 as REPORT-data.md. Then run the hold-out group once and
add its numbers. No fixes."
