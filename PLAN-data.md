# PLAN: the recording corpus - many maps recorded cheaply, then every rework tested on all of it
**Status: PROPOSED 2026-11-17 (by Fable, xhigh: a review of the proposal made in the session "data" the same day).
Not started; needs the user's OK.** Executors: Opus, 3 sessions (prompts at the end) + about 2 hours of the user's
own play. Evidence scripts: `tools/data/` (each file's docstring says what it measures). Nothing in `maplebrain/`
is built yet.

## 1. Why
Every rework so far was designed and tuned on a few minutes of play:
- The native recordings hold **7 maps**. 5 of them are maps perception hunts on; together they show **12 of the 57
  mob types** and **3 of the 13 background sets** those maps have (`tools/data/map_cover.py`).
- The by-eye reference is ~300 labelled frames. 0 misses in 300 only shows an error rate under ~1 %; the targets
  (>= 99 % of mobs found, <= 1 false mob per 1000 frames) cannot be shown on it.
- Thresholds (the 0.75 match score and others) were tuned on the same frames they are graded on.
- Live comparisons are one run against one run on crowded maps (HANDOFF: "not a clean A/B, competition differs").

The designs themselves mostly come from the client files (the scene render, the camera arithmetic, the item
pictures), so they are expected to hold. What is untested is the tuned layer on top and every mob type, background
and situation we never recorded. This plan builds the data to test that, once, and keeps it as the permanent check.

## 2. The review: what stays, what changes
**Approved as proposed:** lossless video instead of PNG; about 5 minutes per map covering the whole map; hold-out
maps we never tune on; a validation pass of perception (not a redo); the loot rework continues and gets the same
pass later; record before the tracker redesign (step 4).

**Edits (each from a measurement in section 3):**
1. **Pick the maps from the game data, not by feel.** 11 more maps add every mob type and background set our
   character can reach (list in section 4). "About 20 maps" is replaced by that list + 5 hold-out maps.
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
6. **One recording of "odd moments".** A hunt never shows a map change, a death, a level-up, or the inventory /
   skill / world-map windows open. Seconds each, one 5-minute recording for all.
7. **Do not convert the existing PNG recordings yet.** The loot worktree reads them through junctions. They are
   copied into the corpus as video; the PNG originals go only after loot part 1 is merged (frees ~12 GB on C:).

## 3. What was measured (2026-11-17)
| # | Question | Result |
|---|---|---|
| D1 | Which format? (`codec_bench.py`, 300 native PNG frames each of an Ant Tunnel IV hunt and an observe run) | **HEVC lossless on the GPU's video encoder** (`hevc_nvenc -tune lossless`, pixel format `gbrp`): 0.17-0.25 MB a frame = 4-6x smaller than PNG, bit-exact back, 3.4 ms of CPU a frame (PNG writer: ~40). CPU lossless H.264 is the same size at 26 ms. FFV1 is larger than PNG. "Near-lossless" moves pixels by up to 66 levels: rejected |
| D2 | A keyframe every 2 s (`-g 120`), and is jumping to a frame exact? (`video_safety.py`, 600 frames) | 5.7x smaller than PNG (5 % cost); OpenCV reads 600 / 600 frames identical; 60 random jumps: 60 exact, 0.25 s each (reading in order: ~400 frames a second) |
| D3 | What if the recording is killed? | The bot (python) killed: ffmpeg finishes the file by itself, 200 / 200 frames. ffmpeg itself killed: the last ~0.5 s is lost (373 of 400 read back, all exact), and jumping in that file is wrong until it is repaired (`ffmpeg -i x.mkv -c copy fixed.mkv`) |
| D4 | Does recording slow the bot? (`paced_enc.py` at a real-time 60 fps beside `tools/perf/bench.py`, the game running, 4 alternating pairs) | tick p50 14.3-14.9 ms alone, 14.5-15.4 while encoding: **+0.3 ms** (2 %), 0 late frames. In-process cost (the copy + the pipe) is Session 1's live gate |
| D5 | Which maps? (`map_cover.py`, from assets/mcw + assets/scene) | 205 maps with mobs: 110 clean, 95 moving backgrounds. 82 mob types (57 on clean maps), 20 background sets (13). Recorded: 12 / 57 and 3 / 13. 11 more clean maps (strongest mob <= lv 45) add 26 of the missing ones; all levels: 20 maps |
| D6 | Disk | C: 60 GB free (runs/: 15.6 GB native PNG + 25.8 GB old JPEG frames). E: Mammoth 3.0 TB free |

**Not measured: the size at 60 fps** (the frames above are every 3rd = 20 fps). Neighbouring frames are closer, so
the estimate is 0.3-0.7 GB a minute; the whole corpus then 40-100 GB. Session 1 reports the real number.

## 4. What to record
**How (every recording):** `serve --observe --video` (the bot presses nothing; your keys are logged as today, which
is also the human-play data the Execution rework wants). The native 1366x768 window, chat minimized. About
5 minutes per map, longer on a big map:
- visit every platform, ladder and rope, both ends of the map, top and bottom;
- hit mobs as they come; use your skills;
- once: stand still at a spawn until mobs reappear; once: let a few drops lie before picking them up, near a
  ladder or post if there is one.
Crowded is welcome (it is the hard case). One line of notes per recording: crowded / quiet, anything odd.

**Group A - dev, the 11 maps that complete the coverage** (`python tools/data/map_cover.py --max-level 45`; a
different level cap gives a different list - the user says what the character survives):

| # | Map | Adds |
|---|---|---|
| 1 | Victoria Road: L Forest II (10003030) | Blue / Green / Orange Mushroom, Lupin, Pig, Ribbon Pig, Shroom, Slime; mid-forest background |
| 2 | Dungeon: Hunting Ground in the Deep Forest (10005011) | Curse Eye, Jr. Necki, Octopus; dark-wood background |
| 3 | Victoria Road: Tree Dungeon, Forest Up North VII (10002081) | Cold Eye, Fairy; shining-wood 2 background |
| 4 | Warning Street: The Swamp of Despair II (10003091) | Ligator; dark-swamp background |
| 5 | Victoria Road: The Forest North of Ellinia (10002070) | Axe Stump; shining-wood background |
| 6 | Kerning City Subway: Line 2 <Area 1> (10003066) | Jr. Wraith |
| 7 | Victoria Road: L Forest I (10003020) | Iron Hog |
| 8 | Dungeon: Deep Ant Tunnel I (10005066) | Evil Eye |
| 9 | Victoria Road: Sunset Sky (10003070) | sunset-city background |
| 10 | Hidden Street: Monkey Swamp III (10003097) | Zombie Lupin |
| 11 | Dungeon: Another Path (10005100) | blue-cave background |

Any map with the same mobs and background set is as good (the tool lists what each map adds); swap freely.
The 5 clean maps already recorded (Ant Tunnel IV, Dark Cave, Dangerous Steam, Line 1 Area 1, Transfer Area) join
the dev group as they are.

**Group B - hold-out, 5 maps:** clean maps the user picks freely, not in group A, at least 3 not in the Ant Tunnel
/ subway family, popular ones welcome. Recorded the same way. Nobody looks at them or tunes on them; they are run
only at gates (section 6).

**Group C - moving backgrounds, 3-5 maps (lower priority):** one per background family that only such maps have:
Excavation Site II (dry rock 2), The Field West of Amherst (grassy soil), Construction Site North of Kerning (metro
city), 3-Way Road-Split (Lith Harbor town), A Look-Out Shed Around the Beach (sand beach, lv 37-38). Dry rock is
covered by the two Perion recordings. Observe records there without mobs, as today.

**Group D - odd moments, one recording:** walk through a portal to another map and back; climb and hang on a
rope; open and close the inventory, the skill window, the world map and the full chat; if it happens: a level-up,
a death. Each once.

**When to record more:** a second 5 minutes on a map only when the validation pass shows a failure there, or a
scenario has too few cases (section 6).

## 5. The recorder and the corpus (Session 1)
- **Recorder:** a new `--video` flag on `run` / `serve`: every frame goes to `RUN/frames.mkv` through one ffmpeg
  process (`-f rawvideo -pix_fmt bgr24 -s 1366x768 -r 60 -i - -c:v hevc_nvenc -tune lossless -preset p4 -pix_fmt
  gbrp -g 120`), fed by the recorder's writer thread (the frame's buffer written straight to the pipe, no extra
  copy). `RUN/frames.idx`: one tick number per video frame, in order. `ticks.jsonl` keeps `"frame": "000123.png"`
  names as today (the name = the tick), so old readers and labels keep working. A full queue drops the frame and
  the tick says `null`, as today: the bot never waits for the encoder. `--frames-png` stays until Session 3 is done.
- **Reader:** `tools/perc/frames.py` `read(run, name)` returns the PNG file if `frames/<name>` exists, else the
  video frame through the index (reads forward when the frame is near, jumps otherwise). Port only the tools the
  validation pass uses (`replay/run.py`, `label_eval.py`, labels, synth); the rest get PNGs on demand from
  `tools/data/unpack.py RUN [names]`.
- **Corpus:** `E:\maple-corpus\{dev,holdout,moving,odd}\<map id>_<name>\<run>` + `manifest.jsonl` (group, map,
  date, minutes, frames, client data build, native check, the user's note). `tools/data/corpus.py add RUN --group
  G` checks the recording (video reads end to end, frames = index = ticks, the map is recognised, the window is
  native) and files it; `list` prints coverage (via map_cover). Tools take recordings from the manifest and refuse
  `holdout` without `--holdout`, logging each use.
- **Existing native PNG recordings:** copied into `dev` / `moving` as video (bit-exact check per recording). The
  originals stay until loot part 1 is merged (edit 7).

**Gates (Session 1):** (a) a recording's video frames are bit-identical to PNGs of the same frames (unit test on
fixture frames + one existing recording converted and compared in full); (b) live, the user's 5-minute observe
recording to E:: 0 dropped frames, tick p50 / p90 within 1 ms of the same run without `--video`, ~60 frames a
second in the file; (c) the measured GB per minute at 60 fps, reported; (d) the bot killed mid-recording leaves a
readable file; (e) pytest green, the bot-speed line unchanged. **Stop rule:** drops or a tick cost over 1 ms ->
stop with numbers (fallbacks to weigh then: the faster preset p1, every 2nd frame, the CPU encoder on spare cores).

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
5. **Report:** per-map table; pooled found / false rates with 95 % intervals; the failure kinds, each with its
   count, its maps and example frames, split into "a threshold or a missing case" and "a structural assumption".
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
1. Session 1 (recorder + corpus tools), then the user records groups A, B, D (C when convenient): about 2 hours.
2. Sessions 2-3 (validation pass + labels), then a review session: the fixes, and **step 4 (the tracker plan) on
   the corpus** - it is about crowds, respawns and mobs hidden under effects, exactly what 7 maps show worst.
3. The loot rework continues in its worktree throughout; its tools get the same pass after its merge. Its
   independent-look tool is reused in Session 2 (merge first, or copy the one file).

## 9. Open decisions (the user)
1. The level cap for group A: which listed maps can the character reach and survive? (changes the list, not the plan)
2. Step 4's plan session: wait for the corpus (recommended), or start now on the 7 maps and re-check later?
3. The old JPEG frames in `runs/` (25.8 GB, from before the native window; the deleted perception's inputs): move
   them to E: or delete them?

## 10. Session prompts
**Session 1 (Opus, high):** "Read PLAN-data.md (sections 3 and 5) and HANDOFF's START HERE. Branch `data` off
`dev`. Build the `--video` recorder, the frame reader in tools/perc/frames.py, tools/data/unpack.py and
tools/data/corpus.py exactly as section 5 says; port only the tools section 5 names. Run gates (a), (d), (e)
yourself; for (b) and (c) give me the exact command for a 5-minute observe recording to E:\maple-corpus\incoming
and wait for my run, then report the numbers. Follow the stop rule. Convert the existing native PNG recordings
into the corpus as copies; delete nothing. Update HANDOFF."

**Session 2 (Opus, high):** "Read PLAN-data.md section 6. The corpus is recorded (`python tools/data/corpus.py
list`). Build tools/data/replay_all.py and run items 1-3 on the dev group only; pick the frames for item 4. Do not
open the hold-out group. No fixes, no threshold changes. Report per map in plain words; follow the stop rules."

**Session 3 (Opus, high):** "Read PLAN-data.md section 6. Label the picked frames by eye (reference = your
labels), run label_eval, and write the report of item 5 as REPORT-data.md. Then run the hold-out group once and
add its numbers. No fixes."
