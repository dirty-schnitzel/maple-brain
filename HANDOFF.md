# maplebrain — session handoff (updated 2026-11-09)
**Read this file top to bottom; it holds only the current state.** NEXT SESSION = "START HERE NEXT SESSION (P1)"
below: brain v3 (**PLAN-v3.md**: world model + planner; Platform / Path / Auto modes) up to **Platform mode** (= Area
mode, `--mark-platform`). P2 after it: accuracy + speed.
Sessions 6-23, the old brain (v1), and superseded plans moved verbatim to **HISTORY.md** on 2026-11-08: grep it for
old runs, numbers and decisions.
Latest: 2026-11-09 edge ghosts fixed + live-checked (`runs/v2/air1/fix3`), package renamed maplebot -> maplebrain;
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

## START HERE NEXT SESSION (P1, the user 2026-11-09): brain v3 up to Platform mode (= Area mode, `--mark-platform`)
**2026-11-10: PAUSED for the VMware pivot (the user: perception + keys for a game running in a VMware VM instead of
the local process; memory "VMware VM setup"). Steps 1-3 committed on `v3`, merged into `dev`; `main` NOT updated
(no live run of v3 yet). Resume v3 with step 3's live test after the VM work.**
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
- [ ] **Brain v3 (PLAN-v3.md), P1 = NEXT up to Platform mode:** world model + planner over today's parts; modes Platform (= Area, `--mark-platform`) /
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
- The game: windowed 2560x1440 client on the left of the 3440x1440 monitor -> the log's `game picture at x (0, 2560)`
  is right (anything else = a bad crop); nothing may cover the game window. Keys don't reach the game while it is
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
```
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
