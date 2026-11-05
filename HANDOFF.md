# maplebot — session handoff (updated 2026-11-05, session 22: M1 step 1 fine own position DONE (camshift + selfstate), next = M1 step 2 link executors; session 21: BRAIN-V2 started - key logger, the user's farming example, KeyDriver executor (default); NEXT = M1 movement skills, see 'BRAIN-V2: THE PLAN'; session 20: look-alike maps by name; session 19: tracker + `--tracker` shim; session 18: GPU detection `--gpu`; session 17: game data from the client files)

## Goal
A **fully automated mob farmer** for **MapleStory Classic World** (official GMS Classic, launched 2026-10-21):
find mobs, fight them like a player, pick up loot, use potions, and **navigate platforms (jump up / drop down,
later ropes/ladders)**. Vision-only: reads the screen, sends key presses; never reads memory or packets.
The user supervises every run at the PC. Botting is against Nexon's ToS (ban risk); the user accepted it.

## BRAIN-V2: THE PLAN - START HERE (written 2026-11-05, end of session 21; next = M1)
Branch **`brain-v2`** (from `main` = the merged `perception` work). `main` stays the last good state; the user
merges. The user is unhappy with the old brain (`brain/brain.py`, 1335 lines of timers tuned on one map/weapon) and
gets constant Lie Detectors; the rewrite should **fight + platform + path like the user** (farming example below).

### Decisions (the user, sessions 20-21)
- **Algorithm, not learning, decides WHERE and WHAT:** hunting is a solvable planning problem - zone value = spawns
  x mob EXP / respawn time, travel cost = `NavMap.route` seconds, kill cost = mob HP / our damage, crowding from other
  players' tags. No recording per map. Learning (later, M5) only for HOW keys are pressed (human feel).
- **A completely new file `maplebot/brain/brain_v2.py`, written from scratch.** Functions may be copied from
  `brain.py`; the old brain is not edited into the new one. Old brain stays selectable until v2 wins an A/B.
- **Emphasis on WHEN TO HIT. Weapon range is variable** (the user now uses a SPEAR; the old zones 42/66/92 px were
  tuned on a sword) -> reach comes from data/measurement, never a constant (see M2).
- Human style = the farming example: tap attacks (~0.13 s) while walking, running jumps, jump+up rope grabs, a hub
  with loops over every platform, a few s per platform, short pauses (median 0.19 s), rare 15-30 s breaks,
  pickup in quick z bursts, MP potion `end`, armor buff `1` every ~4-7 min.
- Safety unchanged: Lie Detector stop + siren, HP stop, potions, focus check; every timing randomised (memory: no
  fixed timings). Kill counting = by LAST HIT (EXP is party-shared).

### Architecture (target)
```
perception (Perceiver + World tracker, --gpu)  ->  obs (+ obs.state, M0)
   -> brain_v2.BrainV2.step(obs) -> Intent {hold: set[str], taps: [(key, secs, after)]}
        reflexes first every tick: LD / HP stop, potions, buff timer, focus
        one active SKILL, an interruptible state machine with a cancel flag:
          Travel(route)   (M1)   walk / jump / drop / fall / grab / climb / exit / leap, re-plan on surprise
          Hunt(target)    (M2)   approach, WHEN TO HIT, tap attacks while moving, loot bursts
          Patrol(zones)   (M3)   the hub-and-loops circuit when nothing worth hunting is tracked
        skills emit events: arrived, failed(link), stuck, target_lost, killed, potions_low
   -> runtime/keys.KeyDriver (thread: hold set + queued taps, human timing; DONE, the default)
```
Runner: `--brain v2` selects BrainV2 (old brain default until the A/B); BrainV2 talks to `KeyDriver` directly
(`hold` / `tap`), not through `LegacyExecutor`.

### M0 - foundation
- [x] key logger for `serve --observe` (keys.jsonl) + `tools/play/{analyze,kills,route}.py`
- [x] the user's farming example recorded + analysed (section below)
- [x] KeyDriver executor, the default (`runtime/keys.py`); the old brain runs on it via LegacyExecutor
- [x] live check of KeyDriver with the old brain (kd1-kd3, 2026-11-05: stalls were perception's, fixed - see M1 step 1)
- [ ] `obs.state`: one fixed per-tick record: us (fine map x/y, platform / rope / air, vx, facing, HP/MP), tracks
  (id, mob, x/y, dx/dy to us, vx, state, unseen, platform), the active skill + its state. Logged in ticks.jsonl.

### M1 step 1 DONE (session 22, 2026-11-05): fine own position - offline on the farming recording
- **Found: the tracker's camera lagged.** `obs.scene_dx` (whole-frame phase correlation) locks onto the parallax
  background: it saw only 0.67 (median, p10 0.44) of the real camera motion -> tag + cam was WORSE than the minimap
  (x vs the rope we hung on p10..p90 -23..+27 px). Mob map positions had the same lag.
- **`perception/camshift.py` `PlatformShift`:** strips under every visible platform surface (tiles are 1:1 with the
  map), matched in the next frame around the PREDICTED shift (last shift x dt ratio: loop stalls of 0.3 s at 150 px/s
  went past a fixed window), of look-alike peaks (repeating tiles) the one nearest the prediction, median. Fallback:
  scene shift (`obs.cam_src` = platforms / scene). ~5.7 ms/frame (12 strips, +-32 px). Config
  `Perception.platform_shift` (on). **`Camera` leash** (`TrackCfg.leash` 24): our feet never > 24 px from the
  minimap's on either axis (bounded error after a missed shift). New `obs.me_map` = tag + cam (exact px).
- **`nav/selfstate.py` `SelfTracker`** -> `SelfState(x, y, src tag/minimap, state ground/rope/air, platform, rope,
  vx, vy)`; on the ground y snaps to the floor; the camera's y may be ~10-15 px off -> the minimap's floor + our exact
  x decides. Tests `test_selfstate.py`, `test_camshift.py`.
- **`tools/nav/selfstate_eval.py RUN`** (replays saved frames; writes RUN/selfstate.jsonl). On
  `runs/play/20261105_000802_1` (7669 frames, every 3rd, 0.13 s apart): x vs rope x -3.2 / +1.9 / +5.4 px (p10/50/90);
  minimap-rope frames we call rope 553/607; ground platform == minimap's 5714/5714; jump-then-up grabs on a rope
  within 1 s 79/94; air episodes 325 (224 after a jump key, 22 drops, 10 off ropes, 69 other = walk-offs, knockback,
  1-frame blips). With +-48 px / 24 strips (8 ms) it was 574/607 - live frames are 3x closer, so +-32 should do.
- **Live (2026-11-05, Line 1, old brain, `run --gpu --tracker`):** `runs/kd1` 3 min: platforms used 1737/1744 frames,
  me_map vs minimap abs median 4.8 px. M0 live check of KeyDriver: no errors, no LD, but still 46 gaps > 0.3 s ->
  NOT the keys: per-part timings (`timings.parts` in ticks, new) in `runs/kd2` showed the Lie Detector check (4
  full-frame matches, 100-500 ms every 0.3 s) and the wide own-tag search (120-155 ms every frame while hidden).
  Fixed: LD on its own thread (answer <= one look late; a new hunt drops the old answer), wide tag search every
  0.25 s while lost (edge search only if last seen near a side). **`runs/kd3` 90 s: 14.4 fps (was 9.5-9.7), gaps >
  0.3 s 3 (1.3 s; was 21 / 10.8 s per 90 s), perceive median 51 / p90 64 ms (was p90 158), me_map vs minimap 3.5
  px.** The user's idea: LD on the GPU - held back (the thread already keeps it off the loop; CPU path works without
  --gpu); do it if CPU contention shows. `tools/nav/live_check.py RUN` = these numbers. M0 KeyDriver check: DONE.
- The user will switch the spear to a POLEARM soon (different reach -> M2 reach from data + learned live).
- Next: step 2, link executors.

### M1 steps 2-4 (session 22, 2026-11-05): moves + Travel + sim + `goto` - first live tours
- `brain/moves.py` (link state machines), `brain/travel.py`, `nav/sim.py` (+ SimDriver), `tools/nav/sim_tour.py`,
  `runtime/goto.py` (`python -m maplebot goto OUT [--to P [X]] [--seconds S] --jump shift`, implies --gpu).
  NavMap.arc: walking-jump landing from the real arc (reach depends on the height), Nav.jump_vx 155 calibrated.
  Sim tour (200 trips, Line 1): 197-198 done, ~96 % of moves first try.
- **Live `runs/g1`:** hub 273 -> 79 in 7.4 s (walk, rope grab, leap, walk_to), all first try.
  **`runs/g2` (3 min tour): 8/10 trips, 50/80 moves first try (62 %).** Causes: (1) Bubblings on the hub knock us
  back (also MISS touches) mid run-up / crouch; (2) a jump tap queued by a failed attempt fired in the next one
  (no up held -> flew past the rope); (3) a drop at a ladder top climbed down the ladder instead (then timeout).
  Fixed (not live-tested yet): knockback -> 'recover' phase + retry, not blamed on the link; Travel cancels queued
  taps between moves (KeyDriver.cancel_taps); drops avoid +-24 px of ropes/ladders at the platform; any move
  reaching its dst by any way = done, an unexpected node fails at once. **The user: "very impressed with
  platforming, looked natural to my eye".** A Lie Detector came at 06:42:34 BETWEEN runs (kd3 ended 06:30, g1
  started 06:44) - again a gap LD.
- **Live `runs/g3` (3 min): 60/76 moves first try (79 %, was 62 %), 8/10 trips.** Left: mob knockback (many
  'knocked' events, HP potions at 46 %); descend pendulum +-25 px around rope x 1960 (the live slide is longer
  than walkDrag says); stuck 15 s ON a ladder top at x -108 (looks like the floor; caught while falling from a drop
  with down still held). Fixed (sim 200/200 trips, 97 %): tight targets lined up in short taps; down released right
  after the drop's jump; holding a walk key 0.4 s without moving at a ladder end -> hop off sideways.
- **The user (g3): "platforming looks very good", BUT "left-right-left-right incidents ... especially above the
  ladder - this looks very botlike".** -> no back-and-forth anywhere: walk_to turns round at most once, then 1-2
  short taps and close enough = arrived; descend like a player: walk at the ladder and press down while passing
  over it (down stops + catches), missed -> a tap or two, down again (max 3). Sim 200/200, descend 10/10.
- Next: re-run the live tour (`goto runs\g4 --seconds 180`); then step 5 gate (>= 90 % first try live); in M2 the
  hunt attacks the mobs in the way (knockback is the main live failure on the hub).

### M1 - movement skills (NEXT): Travel along a NavMap route, live on Line 1 <Area 1> (10003061)
Existing pieces: `nav/navmap.py` (platforms, ropes, links walk/fall/drop/jump/grab/descend/exit/let_go/leap,
`route(src, pos, dst, dst_x)` = Dijkstra in seconds, `landing()`, `step_ahead`, `rope_at`, `platform_at`);
`nav/localize.py` (minimap dot -> map x/y, 16 px coarse -> `obs.map_pos / platform / rope`);
`perception/world.py` `Camera` (map = screen + C every frame -> `obs.cam`); Physics.img constants in `config.Nav`
(walk 125 px/s, jump 555, gravity 2000; jump_height 70, jump_reach 85, rope_grab 80, climb 125 px/s, rope_leap
110). **The old brain never used ropes or `route()`** - Travel is new code. Steps:
1. **Fine own position:** `me_map = obs.me (screen feet from our name tag) + obs.cam` (exact px), the minimap as
   the absolute check; platform via `platform_at`; state ground / air (off every surface, or moving vertically) /
   rope (at a rope's x within top..bottom, no surface under). Watch: our tag is hidden on some ladders (runs/prec1:
   me = None on the ladder platform) -> fall back to the minimap + the rope's x. Verify OFFLINE first on
   `runs/play/20261105_000802_1` (the user's ropes and jumps): error vs the minimap, platform agreeing with
   `obs.platform`, rope/air states where the user was on ropes / jumping (keys.jsonl says when).
2. **Link executors** (a small state machine each, closed loop on the fine position, randomised timing):
   walk_to(x, tol) (hold left/right, let go a random few px early - momentum; overshoot is fine);
   jump (running jump: shift tapped while the walk key is held; take-off point random inside [lo, hi]);
   drop (down held + shift tap); fall (walk off the end); grab (running jump, then hold up once in the air near
   the rope's x - the user's `up while left+shift`); climb (hold up/down to a y); exit (up at the top);
   let_go / leap (jump sideways off the rope: shift + left/right). Expected time per link from the physics;
   slower than ~2x expected = failed.
3. **Travel(route):** `route()` -> links, executed one by one; after each landing compare our platform with the
   link's dst: same -> next link, other -> re-plan from where we are; a link failing twice -> blacklisted for the
   hunt (and logged: navmap fixes). No progress ~1.5 s -> event `stuck`.
4. **Test harness:** `python -m maplebot goto PLATFORM [X]` (or a serve hotkey) = travel there and stop; a "tour"
   of random goals over the map logging per link kind: success rate, time vs expected, re-plans. Unit tests on
   the real Line 1 map.json (a route between every pair of platforms; link state machines on a fake clock with
   scripted positions - like tests/test_keys.py).
5. **Gate:** a 3-min live tour on Line 1: >= 90 % of links succeed first try, never stuck > 3 s, no LD; the user
   watches it once ("looks human?").

### M2 - Hunt skill (WHEN TO HIT first)
- **Reach per weapon / skill, not a constant:** (a) from the client data: the attack skill's `lt/rb` box (Skill.wz:
  Power Strike, the basic attack per weapon type - spear/polearm vs sword) - export it in `assets build`;
  (b) learned live: (dx, dy) of every swing whose target then showed `hit` / `dying` in the tracker -> a reach
  estimate per weapon; disagreement with (a) logged. The user may switch weapons: re-learn when misses pile up.
  (The farming example killed at a median 72 px in front, p90 120 - WITH THE SPEAR, the user confirmed 2026-11-05.)
- **Strike rule:** tap attack when a live (not dying) track's predicted position (its vx x (reaction + swing
  delay)) is inside the reach box in front; face it first; tap again only after the swing landed (hit seen) or
  its time passed; never swing at nothing. Hits-to-kill per mob learned (HP / damage) -> no wasted swings / MP.
- Approach while attacking (taps while walking, like the user); keep enough distance that the mob doesn't touch
  us (Bubblings walk into us: the old "too close -> step back" fired in 38 of 42 fights); platform edges from the
  navmap (never walk off mid-fight unless that's the plan).
- Target choice: nearest by route cost over ALL tracked live mobs (other platforms too); skip dying ones / ones
  being finished by others; prefer platforms with several mobs; switch only with a margin.
- Loot: after our kill, a z burst (2-3 taps ~0.1 s apart) when the drop is within pickup reach; walk-pickup later.
- Reflexes: MP potion `end` at the threshold, HP potion, armor buff `1` on a varied ~4-7 min timer, plain attack
  `c` when out of MP.
- A/B vs the old brain by kills by last hit (`tools/play/kills.py` needs a bot-run variant using ticks' actions).

### M3 - Patrol: the hub-and-loops zone plan (per map, computed at F7)
Zones = platforms (or stretches) with spawns; value = spawns x EXP (x mobRate); cost = `route()` seconds; the loop
= a small orienteering problem over the zones, sized to the respawn time (measure respawn with the tracker: death
-> new mob at that spawn). The user's loop is the Line 1 reference: hub 273, ground 244, east 79-56-65, north-east
33-7-46-111, west 19-25-93 (rare). Live overrides: a tracked mob cheaper than the next zone -> Hunt; other
players in a zone -> lower its value; a bandit over hunts re-weights zones. Vary every lap (order, take-off
points, a skipped zone) - no two laps alike. Breaks of 15-30 s now and then, idle micro-moves. Leash in map
coordinates. Replaces `_spawn_way` (and its ping-pong).

### M4 - human timing from the farming example
Tap / hold / pause distributions from `runs/play/20261105_000802_1` (attack tap 0.13 s median, jump 0.17, z 0.09,
walk holds 0.5-0.6 s median with a long tail, pauses 0.19 s median) sampled by the skills; record the user on
1-2 more maps when useful.

### M5 (later, optional) - learned execution
Behaviour cloning of movement (state + waypoint + recent keys -> keys held) from the user's recordings, with the
M1 scripts as the fallback when it makes no progress; combat stays scripted. Sim / RL only if BC stalls. A local
LLM planner (town trips etc.) = idea level only.

### First steps for the next session (M1)
1. Read this plan + 'brain-v2 executor' + 'FARMING EXAMPLE' below; `git switch brain-v2`; pytest green.
2. Ask the user for the M0 live check (old brain on KeyDriver, 3 min) if not done yet, and whether the farming
   example was with the spear.
3. M1 step 1 (fine own position) offline on the farming recording; then the link executors, Travel, `goto`.

## Older start-here (sessions 11-13, background only): (session 13: loot off + idle LD watch in serve, 884 tests - see 'Session 13'; session 12: map recognised on F7, 806 tests - see 'Session 12'; end of session 11, 774 tests green; session 10: out-of-MP plain attack; **session 11: jump & drop groundwork, see below**)
**The user's goal: TARGETING ACCURACY and KILL RATE** (Perion Street Corner = benchmark, packed with fast bots).
Loot (needs a proper rework, the user's own topic) and the own name tag come after. **2026-11-03: the user removed
their pet (while it was summoned, targeting got drastically worse) and re-added loot-by-sight** - code defaults still
off: runs need `--loot --loot-sight` (`--loot-sight` alone is ignored). See the suspected loot bug below.
**Jumping work continues in its own session: read 'Jumping work: START HERE' below** (live on the Rain-Forest).

## Session 21 (2026-11-04, branch `brain-v2`) - BRAIN REWRITE, step -1: record + analyse the user's play
`perception` merged into `main` (ff, `62cdf35`); `brain-v2` branched from `main`. **Plan agreed:** scripted
navigation (zone loop computed per map from NavMap + spawns, targets by route cost from the tracker) + learned /
statistical human timing for the keys; new executor (a SET of held keys, non-blocking - today's holds ONE key and
Tap blocks the loop); new brain in its own package behind `--brain v2`, old brain stays default until v2 wins an A/B.
Milestones: M0 executor + obs.state + key recording -> M1 movement skills (walk/jump/drop/rope, finer own position)
-> M2 hunt skill -> M3 zone loop + rests -> M4 humanizer from the user's stats, then behaviour cloning.
**Step -1 (the user's call): record the user farming + keys, analyse before designing.**
- Built: `maplebot/runtime/keylog.py` `KeyLogger` (WH_KEYBOARD_LL hook on its own thread) -> `RUN/keys.jsonl`
  `{"t", "key", "down"}` (+`inj` injected, +`lag` ms >= 5), t = the ticks' obs.t clock; transitions only, downs only
  while the game is focused, ups always; started only in `serve --observe` hunts (F7..F8). Tests `test_keylog.py`.
- Done: the user recorded 18.5 min on Line 1 (see 'FARMING EXAMPLE'). Record more with
  `serve runs\play --attack space --jump shift --pickup z --observe --gpu --tracker --frames` (elevated console,
  `watch` running); analyse with `tools/play/analyze.py RUN`, `kills.py RUN 1.0`, `route.py RUN`.

## brain-v2 executor: KeyDriver (session 21, 2026-11-05) + the user's notes for brain-v2
- **Built: `maplebot/runtime/keys.py` `KeyDriver`** - a thread owns the keyboard: `hold(set)` = every key to keep
  down (several at once), `tap(key, secs, after=0)` queued and non-blocking (a 2nd tap of a key still waiting is
  dropped; taps of one key never overlap), random reaction pause per key-down / release pause per key-up (keys
  changed together never flip at the same instant), varied tap lengths, auto-repeat of the last pressed key
  (~0.5 s delay, ~33 ms), focus lost -> everything up, wishes dropped, `lost_focus`. `pump(now)` = all logic
  (tests: fake clock). `LegacyExecutor` = the old brain's Hold/Release/Tap on it, nothing blocks. **THE
  DEFAULT** (the user: no flag; the old blocking `runtime/executor.py` + its test are deleted): run/serve always
  drive keys through it (`Keyboard.send` = raw event; `kb.release_all` still called as a safety net). Config
  `Humanize.release_* repeat_*`. Tests `tests/test_keys.py` (12). **Not live-tested yet:** first live run = check
  loop stalls > 0.3 s are gone, and watch for Tap spam / turns and step-backs that behave differently now that the
  old brain's taps no longer block.
- **The user's notes for brain-v2 (2026-11-05):** (1) **a completely new file `maplebot/brain/brain_v2.py`, from
  scratch** - functions may be copied from brain.py; (2) **emphasis on WHEN TO HIT: the user now uses a SPEAR**
  (longer reach than the sword the old brain's zones 42/66/92 were tuned on); weapons change, range is variable ->
  reach from data (skill/weapon hit boxes in the client files) and/or learned live (distance of swings that hit).

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

## Session 20 (2026-11-04, branch `perception`) - NEXT TASK: the brain navigates Line 1 - START HERE
**Done this session (UNCOMMITTED - ask the user before committing):**
- **Look-alike maps told apart by the name** (`nav/identify.py`, quick fix, no OCR - the user: "quick fix no ocr";
  HP/MP/EXP reading is fine as is, no refactor). Only when the minimap pictures tie (within `lead` 0.05): each tied
  map's map.json `name` is drawn in Arial Bold 12 px without smoothing (closest to the game's title font; Tahoma /
  Verdana / Arial Narrow scored near 0), lined up on the shared prefix, and only the differing glyph runs are compared
  (each +-1 px on its own). Pick if best >= 0.5 and 0.15 ahead, else refuse as before ("two maps look alike").
  Line 1 is a 3-way tie: Line 1 <Area 1> 0.89 / Line 1 <Area 2> 0.87 / **Line 2** <Area 1> 0.85 -> names 0.86 /
  0.59 / 0.60. 18/18 recorded frames right; live: "told apart by the name" (2.5 s at F7). Not tested: standing in
  Area 2 itself (only a synthetic test). Shared names (Mushroom Town x2, Backalley Semi-Basement x2, Shortcut x2,
  Coconut Harvest x3) stay refused. Tests: `tests/test_identify.py` (+ fixtures `10003061_line1_area1_{0,1,2}.png`).
  `--map` is no longer needed on Line 1.
- **5-min live test `runs/l1a1_5m`** (`run --tracker --gpu`, no --map, Line 1 <Area 1>): 40 kills / 300 s (8/min;
  l1a1_trk2 3 min: 16). Time: ENGAGE 118 s (39 %), SEEK 117 s (39 %), LOOT 65 s (22 %).
  - **SEEK with mobs tracked on OTHER platforms: 79 s (26 % of the run)**; the tracker saw mobs on our platform the
    brain didn't use for only 1 s -> perception is fine, the brain fights its own floor only. We spent the run on the
    ground (platform 244, x -305..3185, the whole map); mobs mostly on platforms 273 / 111 (then 46, 79, 33),
    median 260 px above us, 270 px to the side.
  - **Idle-walk ping-pong** (the user's log: "walking right, toward the densest spawns (map x 2737, we're at 2436)" /
    "walking left" every ~1 s): the ground's 18 spawns are spread evenly (-253 .. 3136), so the "densest" x is
    arbitrary, and `_spawn_way` has no hysteresis at `spawn_home` 300 (2436 is 301 away). Why it turns *left*
    rather than walking on right isn't traced yet (a `blocked` right? the 'avoiding ... where we were hidden' rule?).
  - Other: LOOT 22 waits, 10 picked up nothing; 17 kills by others (10 were our target, 19 s); 69 loop stalls
    > 0.3 s = 34 s; "too close -> step back" in 38 of 42 fights (Bubblings walk into us); perceive 53 ms median.

### NEXT TASK (the user, 2026-11-04): design and implement a solution for the brain to navigate Line 1
Goal: on Line 1 <Area 1> (10003061: 25 platforms, 18 ropes/ladders, 358 links) the brain goes where the mobs are,
instead of pacing the ground floor. Design first (short plan to the user), then build, then A/B with 5-min runs
(baseline = `runs/l1a1_5m`: 40 kills, 79 s of SEEK with mobs on other platforms).
Pieces the design has to cover:
1. **Target choice across platforms:** nothing fair on our floor -> nearest tracked live mob by route cost
   (`NavMap.route`: walk / jump / drop / fall / grab / ladder links, cost in seconds), not by straight distance;
   skip dying / about-to-be-taken mobs; prefer platforms with several mobs.
2. **Executing a route:** walk to the take-off point, jump / drop / climb (ropes & ladders: grab, climb, exit at
   the top), re-plan when we land somewhere else; give up + blacklist a link that fails twice. Existing pieces: jump &
   drop groundwork (session 11, 'Jumping work: START HERE'), "target on lower ground -> stepping down to it",
   `step_ahead`, `landing`, `rope_at`. Ladder climbing is the new part (check what exists first).
3. **Fighting on any platform:** engage / reach / edge rules must work on narrow upper platforms (don't walk off an
   edge mid-fight unless that's the plan; edges = platform ends from the navmap).
4. **Idle when nothing is tracked anywhere:** replace "densest spawns" on Line 1 with a patrol between platforms
   (or the platform with the most spawns / recent sightings); fix the `_spawn_way` hysteresis either way (walk until
   well inside, e.g. 150 px; skip when spawns are spread evenly).
5. **Safety:** leash in map coordinates (today minimap px from the start dot), Lie Detector / HP stop unchanged;
   randomised timings everywhere (memory: no fixed timings).
Tools: `livemap` (watch it live), `tools/perc/track_run.py`, ticks.jsonl `obs.mobs` (tracks with `platform`),
`obs.platform` (ours). Then the 'NEXT GOALS' list below still applies (shim confirm, Phase 0 executor).

## Session 19 (2026-11-04, branch `perception`): the tracker
Commits on `perception` (`main` untouched, the user merges): `746649b` session 18 checkpoint, `368931b` tracker +
cover masks + livemap, `9287975` dying fix + edge probes, `a3a9f99` the `--tracker` shim. All committed.
**Built (all live in `serve/run --gpu`, PASSIVE: logs `obs.mobs` / `obs.cam`, the brain still uses `known_mobs`):**
- `perception/world.py` `World`: tracks in map coords (id, voted mob type - Pig/Ribbon Pig look alike, feet x/y,
  vx measured per track, facing, anim, state tentative/live/hit/dying/hidden/offscreen, vis). `Camera`: map = screen
  + C (scenery shift each frame + 5 % pull to the minimap anchor + clamp to vrBounds; Rain-Forest sits at the clamp).
  Ends need time unseen AND >= 4 missed frames (the bot's loop stalls up to 0.5 s during taps: 42 gaps > 0.3 s/3 min).
- `GpuSpriteDetector.find_near`: every pose (hit/die too) around each unseen track, plain batched conv; with `vis`:
  **visible-only NCC** (pixels under cover/players skipped; a Pig in grass 0.53 -> 0.90), windows past the screen
  edges. Fixed batch shapes + `warm_near()` at map load (~14 s once per map per process: cudnn.benchmark times each
  new shape, 0.4-4.5 s; unwarmed = 1.3 s stalls mid-hunt; a lower benchmark_limit picks 10-40x slower kernels).
  Frame uploaded to the GPU once per frame (`_dev_frame`, `find` always uploads fresh).
- **Cover masks** (`maplebot/cover.py`, the user's idea): what the game draws over mobs = tiles/objects of layers
  above the mob's foothold layer (HeavenClient draw order). Exporter now exports Map/Obj.wz + Tile.wz (5967 + 619
  pictures); `assets build` writes `maps/<id>/cover_<L>.png` + map.json `cover` for 300+ maps (build 7 s -> 2.5 min).
  Verified pixel-exact on the Rain-Forest (upper platforms = layer 0 behind the trees; ground = layer 1, covered by
  the 2 grass patches, mushrooms, ladder). Not yet: `back` entries with front=1 (counted as `front_backs`).
- Player bodies (from name tags, `find_tags` on a CPU thread in parallel with the GPU pass; ours too) masked like
  cover; mob tags ("Lv.7 Pig" under a track's feet) skipped. Cover probes: 4 rotating spots/frame along platforms in
  cover (visible-only search -> new tracks). Probes beside players: built, OFF (`probe_players`: +2 mobs, +4 false,
  +10 ms).
- `livemap` (`python -m maplebot livemap [runs\manual] [--map ID] [--width N] [--replay --t0 S]`): whole map in the
  console, redrawn in place every 0.3 s (the user: "amazing"); `perception/mapascii.py`, `tools/perc/mapascii.py MAP`.
  Focusing its window pauses the bot (game not focused) - just look at it. Hunt logs now name their map (from the
  next serve start; until then `--map`).
- Recorder: frames written on a thread; `--frames-every N` (run/serve). Recording `runs/track1b` (3 min, every frame,
  Rain-Forest, 1.6 GB).
- Tools: `tools/perc/track_run.py RUN MAP [--show T0 T1]` (offline tracker -> tracks.jsonl + timings),
  `label_eval.py RUN` (vs labels), `track_draw.py`, `track_eval.py` (vs truth.jsonl - obsolete, see below).
**Reference = Claude's by-eye labels (the user: "always use claude labeling instead of truth.py"):**
`runs/track1b/labels.json` (30 frames, 82 mobs). truth.py found only 51 % of them (blind to covered mobs).
**Result (track1b vs labels): found 87.8 %, false 8.9 %** (+4 dying with no corpse, +9 hidden = unverifiable);
within 150 px of us 20/23. Per frame: whole-screen 13.9 ms, near+probes 8.6 (p90 15.7), world 0.6; live perceive
35 ms median vs 26 before (~+9 ms). Still missed: half behind players (5), daffodil edge (3), left screen edge (2).
Tests: test_world (8), test_cover, test_mapascii, visible-only NCC tests; suite green.
**Later in session 19:**
- **Second map, Line 1 <Area 1> (10003061, Kerning City Subway; Bubbling; 25 platforms, 18 ladders, cover on 4
  layers):** worked first time, no code changes. Map recognition refuses to choose there: Area 1 vs Area 2 minimaps
  look alike (0.88 vs 0.84) -> runs need `--map 10003061` (open issue: look-alike maps). Runs: `runs/l1a1_1` (1 min),
  `runs/l1a1_rec` (3 min, every frame, labelled: 30 frames, 141 mobs). **Tracker vs labels: 92.9 % found, 7.7 %
  false** (Rain-Forest 87.8 % / 10.0 %). Live perceive on this busy map 43 ms median / 99 p90 (tracker ~25 of it;
  the rest = loot-by-sight / HUD / CPU parts - profile later).
- **Labels are in git:** `tools/perc/labels/{track1b,l1a1_rec}.json` (+ README; `runs/` is git-ignored: copy to
  RUN/labels.json, score with `tools/perc/label_eval.py RUN`; it also reports "found but marked dying").
- **Dying fix (`9287975`):** a death needs a die sighting >= 0.75 or two; a lone weak one is undone by a clear live
  pose, or made final when nothing else was seen after it; a dead track never takes live poses (a new mob where one
  died = a new track). l1a1_rec: live mobs marked dying 9 -> 0.
- **Edge probes:** visible-only search at both screen edges on every platform crossing them (own rotation, 2 per
  frame); tracks count as in view up to 40 px past the side edges.
- **The shim (`a3a9f99`), `--tracker` (needs `--gpu`):** the brain's known_mobs / sprite_mobs = confirmed tracks on
  our level (hidden ones while hidden, others unseen <= 0.4 s; boxes from the client's body lt/rb at the feet); the
  target is held by track id (`target_src` "sprite" = seen alive this frame, "track" = coasting/hidden,
  `target_dying` from the track). Live `runs/l1a1_trk2` (3 min) vs `l1a1_rec`: lost targets 3 -> 0, blind swings
  12 -> 3, kills 16 vs 19 (one run each, crowded map, 21 vs 38 kills by others: NOT conclusive). The extra "no mobs
  in sight" were mobs on other platforms / mid-jump (the brain still fights on its own level only).
  `runs/l1a1_trk1` = invalid (the character wasn't on the map: 0 GPU hits in 4307 frames).
  The user's command: `serve runs\manual --attack space --jump shift --pickup z --loot --loot-sight --gpu --tracker`
  (restart serve to load new code; first F7 on a map waits ~17-20 s for the GPU warm-up).

## NEXT GOALS (agreed 2026-11-04, end of session 19) - START HERE
Perception is good enough; **the brain is the bottleneck now.** In order:
1. **Confirm the shim** (needs the user at the PC, ~15 min): back-to-back 3-min runs on one spot, alternating
   old / `--tracker` / old / `--tracker`, MP potions stocked, `watch` running; compare kills/min, lost, blind swings.
   Not worse -> `--tracker` becomes the default.
2. **Brain Phase 0** (Claude, no user needed): (a) non-blocking executor - key timing on its own thread, the loop
   never stalls (today 0.3-0.5 s gaps, dozens per 3 min); (b) `obs.state` - one fixed state format per tick (us:
   map pos, platform/rope/air, HP/MP, facing; tracks: offset, vx, type, state, unseen; nearby platforms/links); (c)
   record the user's keys in `serve --observe` -> then the user records 30-60 min of farming on 2-3 maps.
3. **Rule-brain upgrades the tracks make possible** (the kill-rate gains; A/B each): (a) mobs on other platforms -
   nearest by path, reached with the existing jump/drop/ladder links (most of Line 1's "no mobs in sight"); (b) lead
   a moving target (its measured vx); (c) skip dying mobs / mobs about to be finished by others; (d) keep a target
   hidden in cover or behind a player and wait at the cover's edge.
4. **Later: the trained brain** ('Brain plan' below): sim v0 calibrated on our recordings, model v0 with the user's
   recorded style, live vs the rule brain. The user's own learning sim (note below) can grow into it.
**Not now:** more perception tuning, the pet, own position from the picture, profiling busy-map frames.

## Brain plan (the user, 2026-11-04): a trained model, simulator + a little human play
The user wants to replace the rule brain with a trained model that reads the tracker's state and plays. Agreed:
- **No live RL** (millions of steps; random flailing = bot profile). Train in a **simulator built from our client
  data** (map.json footholds/ropes/spawns, mob.json stats/frames, Physics.img, HeavenClient mob logic), calibrated
  against recorded runs (replay their keys in the sim, compare positions / mob motion / perception noise).
- **Minutes to an hour of the user's own farming** (`serve --observe` + key logging - not built yet) teaches STYLE:
  adversarial imitation (AMP/GAIL-style "looks like the human" reward) + EXP/min reward in the sim; domain
  randomisation (perception misses/ghosts from the labels, physics +-10 %, other players stealing kills).
- **Model:** multi-input - self scalars (MLP) + track list (attention/set transformer) + local map grid around us
  (~8 px cells, small CNN) + ~1 s history (GRU) -> keys + hold time; ~100k params, < 1 ms on the GPU.
- **The user: no shadow mode, no guard rails - go live as soon as it plays sensibly in the sim.** Kept only what
  exists and protects the account: Lie Detector stop + siren, HP stop, potions, focus check.
- **Phase 0 (useful for any brain):** (1) shim - today's brain reads the tracks (known_mobs/target from confirmed
  tracks, target held by track id); (2) `obs.state` - one fixed state format per tick; (3) non-blocking executor (key
  timing on its own thread, the loop never stalls); (4) record the user's keys in `--observe`.
  Then: user records 30-60 min on 2-3 maps; sim v0 (flat Pig map); model v0; live 3-min A/B vs the rule brain;
  grow the sim (platforms, ropes, loot, other players, maps).
- Earlier discovery (still valid): `C:\Users\Yoav\.claude\plans\read-handoff-read-relevant-rustling-castle.md`.

### Note to self (the user): learning AI - not a task
Background: almost-finished CS + EE degree, career in cybersecurity QA automation (ML evaluation = QA work).
- Deep learning basics: Karpathy "Neural Networks: Zero to Hero" (YouTube), fast.ai "Practical Deep Learning",
  pytorch.org tutorials (torch + CUDA already in `..\auto-maple\.venv`).
- RL: Hugging Face Deep RL course, OpenAI "Spinning Up", Sutton & Barto (reference); tools Gymnasium,
  Stable-Baselines3, CleanRL.
- Imitation / sim-to-real: behaviour cloning, DAgger, GAIL, AMP (Adversarial Motion Priors), domain randomisation.
- **Small brain project to learn on:** a tiny Gymnasium env from the Rain-Forest's real map.json + Pig mob.json
  (one flat platform, me + 3 Pigs; actions left/right/attack/idle; reward EXP), PPO via Stable-Baselines3, watched
  with `mapascii.render`; then add platforms, jumps, noise. Claude offered to set up the skeleton (`sim/`).

## PRIORITIES (the user, 2026-11-03) - these two come before everything else below
1. ~~Remove maplestory.io completely~~ **DONE (session 17, 2026-11-03, git branch `client-data`)**: all game data
   comes from our own client files. See 'Priority 1: done' just below.
2. **Now: the perception rework** (mob tracker in map coordinates). Frame origins (feet), body boxes and frame
   delays are now in `assets/mcw/mobs/<id>/mob.json` -> `frames`.
   **Session 18 (2026-11-03/04, branch `perception`, UNCOMMITTED - ask the user before committing/merging):**
   GPU whole-screen mob detection built, wired in as `--gpu`, live-tested once (`runs/gpu1`). Details in
   'Priority 2' below. **NEXT SESSION = THE TRACKER (stage 3) - see 'TASK: the tracker' right below.**

### TASK: the tracker (stage 3) - next session, START HERE (the user, 2026-11-04)
Read 'Priority 2' first (decisions + measurements). Build `perception/world.py` on top of `GpuSpriteDetector`:
- **Tracks** in map coordinates: id, mob id, platform (or "in the air": Ribbon Pigs / Pigs jump, jumps reuse
  move_0 - seen 43 px over pit 49), feet x/y, vx, facing (from the Pose), last pose, last seen, state (unhit /
  fighting us / hit / dying / dead / off screen). Screen -> map: map = screen + (our map pos - our screen pos);
  relative geometry stays in exact screen px (our map pos is 16 px coarse, x ~7-15 px off on Rain-Forest).
- **Acquire / track split (the user's idea, measured):** the whole-screen GPU pass (stand/move/fly) acquires;
  each track then gets a small window every frame with ALL its poses (hit1 / die1 / attack too) and a **lower
  threshold where a track is predicted** - this is what catches the half-hidden mobs (gpu1/Rain-Forest misses
  were real Pigs behind a player / a mushroom at 0.62-0.64 < 0.65) and mobs next to our own body.
- **Map filter (the user's idea, used as a check, not a search mask):** feet on a platform surface near a
  spawn's rx0..rx1 -> plausible; floating in the trees -> reject (unless a flyer or a tracked mob mid-jump).
  Search stays whole-screen (7-10 ms anyway; a mask would depend on our own map position being right).
- Association by predicted x per mob type + platform; motion model from mob `speed` + HeavenClient logic
  (decide ~every 1.6 s, turn at edges, knockback >= `pushed`); frame `delay`s give hit (600 ms) / die lengths.
  Gaps: keep the track; end on die animation / EXP / spot visible and empty for k frames.
- **Own position (stage 2) with it:** the picture (our tag's screen motion + camera shift) is the measurement;
  key-press physics (Physics.img: walk 125 px/s, jump 555, gravity 2000) only as the prediction step and a
  knockback/blocked detector (the user preferred the picture: "the information is in the picture").
- Output `obs.mobs` / `obs.me_map` in ticks.jsonl; a shim derives today's `known_mobs` + target so the current
  brain gains first; then A/B live (CPU vs GPU vs GPU+tracker, 3 min each back to back, same spot, MP potions
  stocked - gpu1 ran out of MP). Gate before brain changes: >= ~95 % recall of mobs within 100 px of us
  (offline, `tools/perc/gpu_eval.py` / `truth.py`).
- Live runs: 3 min, `watch` running.

### Priority 1: done - game data from the client files only (session 17, 2026-11-03)
**Git (new, the user asked for it):** the project is a git repo now (`.gitignore`: runs/, captures/, caches, .idea).
`main` = baseline before the refactor (`b143100`, assets/mcw = the maplestory.io copy); the work is on branch
`client-data`. Back to the old state instantly: `git switch main`. Repo-local identity (the user's name/email),
`core.autocrlf=false` (exact bytes). **Merged into `main` 2026-11-03** (fast-forward, after the live run); old state = `b143100`.
**Pipeline** (full guide: `assets/README.md` 'How it's made' + 'After a game patch'):
`tools/cwdata/export.ps1` (~10 s; every map + minimap PNG, every mob + frame PNG, UOL/_inlink/_outlink resolved,
String names) -> `C:\Users\Yoav\dev\cw-data\export` -> `python -m maplebot assets build` (~7 s;
`maplebot/gamedata.py`, now the converter) -> `assets/mcw` (same layout and field names the bot always read, so no
reader changed) + `changes.txt` (what the build changed vs the previous one). Removed: every download path
(`assets update`, the runner's auto-download on a missing `--map` -> now says "isn't in assets/mcw ... assets build").
**Diffed against the maplestory.io copy before switching** (every map/mob/frame): footholds, ropes, minimap fields
and canvases, mob stats, sprite pixels all equal except where the API was wrong or older:
- the API had dropped **502 portals** (every one with a destination) as null; the client has them all;
- mob spawn `y` 1 px off on slopes on 132 maps: the API recomputed y from the foothold line, we keep the client's
  `cy` (the client's `y` is where the sprite is first drawn: kept as `spriteY`);
- mob 700006 Shade `skill2` frames 3-8: the API followed the client's frame links wrongly;
- older data in the API: maxHP of mobs 40 41 44 45 (e.g. Copper Drake 2595 -> 2379 in the client), the minimap of
  10001021, a few frames of mobs 39 / 700003 / 810004 (1-3 px different sizes); map 10006121 only in the client.
- **Correction:** the API did NOT trim frame PNGs (an earlier note here said so): they are the client's raw
  canvases, pixel-equal. Frame files are numbered 0..count-1 in play order (client numbers can skip: mob 39 stand
  0,1,3,4,5; the client's number is kept as `n`). `pack_ignore.txt` in the Mob pack is not a mob (117 mobs, 2154
  frames).
- Found on the way: `sprites._cover` looped forever on flat one-colour poses (score -1 even on themselves; the
  client has 1x1 placeholder frames) -> fixed + test.
Tests: 959 green (new `test_gamedata.py` = the converter on a tiny fake export + checks on the real assets; 2 runner
tests for the missing-map path). **Live-tested 2026-11-03** `runs/client1` (2 min, Rain-Forest 10001070, no `--map`,
`--loot --loot-sight`): map recognised from the new minimaps (score 0.75, next 0.42), Pig/Ribbon Pig sprites, 9 platforms,
2 ropes, 53 links; 20 kills, 11 jumps, 11.7 fps, no errors, no Lie Detector.
**After a game patch (the user, 2026-11-03):** reading the client doesn't make patches free. Re-copy `Data`,
re-export, rebuild, run pytest, then **read `assets/mcw/changes.txt`** (+ `git diff --stat assets/mcw`) and look
again at whatever the bot is tuned on that changed (footholds/ropes of the farming maps, minimap pictures for map
recognition, mob frames for sprite detection, mob stats), then a short live run before long sessions. The export
can also break on a new client format: HaRepacker may need an update. Steps in `assets/README.md`.

### Priority 2: perception rework - mob tracker in map coordinates (after priority 1)
Replaces the 'HANDOFF TASK: complete refactor of targeting' research below as the next step (that section stays
as background). Today (verified): `Perceiver.observe` makes a plain list of screen boxes per frame (`known_mobs`), keeps
only mobs on our level (`reachable_level`), no IDs/history/velocity/map position; one template `Tracker` on the target
bridges gaps up to 0.6 s. The brain's blind swings / keep-swinging / dead reckoning cover these gaps.
Plan (`perception/world.py`):
- **Own position fused:** minimap (absolute, 16 px steps) + motion predicted from the keys held, using the client's
  real physics (`Physics.img` = v83 exactly: walkForce 1400, walkDrag 800, walk 125 px/s, jump 555 px/s, gravity
  2000, fall 670; 'force/100' units) + camera shift.
- **Mobs on the map:** sprite match -> the frame's **origin** = exact feet -> map x/y -> snap to the platform
  (`NavMap.platform_at`), bounded by the spawn's rx0/rx1. Tracking is 1-D along the platform (jumpers: Pig, Ribbon Pig).
- **Tracks:** id, mob id, platform, x, vx, facing, last seen, state (unhit / fighting us / hit by us / dying / dead /
  off screen). Association by predicted x per mob type and platform. Motion model from mob `speed` % and the
  HeavenClient mob logic (stand/left/right every ~1.6 s, turn at edges, knockback if damage >= `pushed`).
- **Gaps:** keep the track. Expect misses during hit/die poses (frame `delay`s give their length) and next to our
  body: lower threshold there. End on death animation / EXP / spot visible and empty for k frames.
- Detect mobs on all platforms (not only our level), maybe a full scan every Nth frame.
- Output `obs.mobs` / `obs.me_map` in ticks.jsonl. A shim derives today's `known_mobs` + target -> the current brain
  benefits first (live A/B), and a future brain uses the tracks directly.
- Later: reach from real hitboxes (mob `lt/rb` + our attack range from Skill/Character data) instead of the zones
  42/66/76; maybe read damage numbers (digit pictures in the client's Effect data) -> mob HP left -> exact swings.
- Verify offline first on recorded frames (recall of mobs within 100 px of us, ID switches, gaps bridged; hard sets:
  Rain-Forest Ribbon Pigs, Perion crowd, runs/prec2). Gate: >= ~95 % recall near us before any brain change.
- **The user (2026-11-03): rethink the whole computer-vision approach.** The narrow band around our feet is a
  stopgap; "we should have the compute power to recognize all sprites on a given screen very fast - feasible and
  not that hard". Agreed. Facts measured the same day:
  - Hardware: **RTX 4070 Ti SUPER (16 GB) + 20 CPU threads, the GPU unused by the bot**. No torch/onnx in the venv.
  - CPU OpenCV `matchTemplate` over the whole 1366x700 play area, per pose: masked full size 224 ms, unmasked 52,
    masked at 0.5 scale 48, unmasked 0.5 11 (Ribbon Pig = 14 poses) -> the CPU can't do every pose over the whole
    screen every frame; that's why today's detector needs colour blobs + a band.
  - Pixel-exact tricks (hashing sprite pixels) are out: the game picture is rescaled (e.g. windowed 2560x1440 ->
    1366x768 capture) and JPEG'd in recordings.
  Options (Claude's recommendation: A first, B only if A misses the recall gate near our body):
  - **A. GPU template matching** (PyTorch/CUDA): every pose of every mob on the map as one batched masked NCC
    over the full frame (~tens of GFLOP -> a few ms on that GPU). Same maths as today, no training,
    deterministic; also makes `truth.py` ms per frame instead of 2.6 s. Weak spot stays: partial occlusion
    (our body, mobs overlapping, damage numbers) lowers the score.
  - **B. Small learned detector** (YOLO-style, box + mob id + pose + feet point) trained on **synthetic frames**:
    the client gives every sprite + origin, the recordings give thousands of backgrounds -> paste sprites (all
    poses, flips, partly covered, overlapping, our character on top) = unlimited labelled data for free.
    ~3-5 ms per full frame on the GPU, robust to occlusion. Cost: torch dependency + a training pipeline.
  - **The user's idea (2026-11-03): acquire with the main pose, track with all poses.** Scan the untracked screen
    for one key pose per mob (both facings); once a mob is acquired, look for all its poses in a small window
    around it (hit/die only there). Checked on data: mobs are ~90 % in their stand/move loop (20 s Rain-Forest
    sample: 34 of 47 sightings move, 5 stand, 8 hit/die), BUT each loop is 3 frames that differ a lot for Pigs
    and Stumps (best single pose vs the others: mean similarity 0.62, min 0.30; Snails 0.78-0.89, min 0.59-0.65).
    What makes it work anyway: the loops cycle every 0.5 s (Pigs, Stump move 0.72, Snail 0.9; Stump stand is one
    still frame) -> a walking/standing mob shows its key frame at least once per cycle -> **acquisition within
    <= ~0.5-0.9 s with ~2 key frames per mob (one stand, one move) x 2 facings = 4 templates.** Fine for far mobs.
    CPU cost of that full-screen scan: ~4 x 11 ms (unmasked, 0.5 scale) to 4 x 48 ms (masked) -> on CPU rotate
    it (a third of the screen per frame); on the GPU it's free. Plan: build detection as **acquire (cheap,
    whole screen, key frames) + track (all poses, small window, every frame)** whichever backend (A/B) runs it.
  - **Decided (the user, 2026-11-03): GPU masked NCC with stand + move (+ fly) frames only**, searched only in
    **strips just above platforms** (following slopes segment by segment; tallest mob + ~50 px for jumpers) and
    only **on platforms with spawn points, within each spawn's rx0..rx1** (the user's ideas); whole screen only
    for flying mobs, or as a fallback while our own map position is unknown (air / rope / tag lost).
    torch 2.11.0+cu128 installed in the venv. `tools/perc/gpu_bench.py RUN MAP TICK` (GpuNCC = 3 convs, sums in
    fp32 - fp16 sums cancel and gave scores of 86; now equal to OpenCV's TM_CCOEFF_NORMED with mask to 3
    decimals). Rain-Forest tick 396, 24 templates (Pig + Ribbon Pig, 6 frames x 2 facings), per frame incl.
    upload: **0.5 scale (what live uses): whole play area 6-7 ms, all platform strips 2.5-3 ms, spawn strips
    1.2-1.4 ms**; full size 72 / 17-22 / 8 ms. CPU OpenCV on the same: 1100 / 330 / 165 ms (0.5 scale) -> the
    strips cut the work 3-6x but the CPU still can't do it every frame; the GPU need shrinks (a GPU ~10x weaker
    would still do strips in ~15-30 ms), it doesn't disappear. Cost grows ~linearly with templates (Perion: 4-5
    mob types). fp16 vs fp32 conv: same speed here -> fp32.
  - **Built (2026-11-04): `maplebot/perception/gpu_sprites.py` `GpuSpriteDetector`** - whole play area (y < 700),
    every stand/move/fly frame x 2 facings: coarse masked NCC at 0.5 (3 batched convs), flat windows -> -1 (std <
    2 grey levels: sky once scored 32 -> 10k peaks, 23 s a frame), local peaks per mob, <= 64 candidates, then
    **refine on the GPU** (full size, +-4 px, each candidate's 3 best coarse poses, grouped convs, one batch) ->
    `Hit(mob_id, box, feet, Pose, score)`. Refine is needed: coarse-only on Perion = 987 detections vs 161 (rock
    inflates half-size scores). **Wired in as `--gpu` (run/serve, 2026-11-04, the user tests it live):**
    `GpuBand` = drop-in for SpriteDetector in the Perceiver: whole screen once per frame, `find` returns only the
    band the Perceiver asks for (same contract: our level, excludes) -> the brain is unchanged; `dying` / `mobs` /
    `max_h` from the CPU detector. Warm-up at map load (~2 s). ticks.jsonl `timings.gpu_ms` + `gpu_mobs` [[id,
    feet x, feet y, anim, score]] = every mob on screen. `Perception.gpu` flag.
    **Live `runs/gpu1` (2026-11-04, 3 min, Rain-Forest recognised at start, `run ... --loot --loot-sight --gpu`):**
    **fps 23.6 (CPU runs ~11.7), perceive median 25 ms (CPU 66)**, gpu_ms median 10.1 / p90 13.1 (rare spikes to
    118), own tag found 99.2 %, no errors, no LD. 22 kills = 7.3/min (client1 CPU 10.0/min, loot1 CPU 3.4/min -
    not comparable: other players / spawns / 19 % of ticks in LOOT / out of MP -> plain attack). Mobs in our band
    0.59/tick (client1 0.35); 132 ticks had mobs on screen but none in our band (the tracker's to use). "Hit by
    something unseen" 6.7/min and "lost target before reaching it" 2.7/min unchanged vs CPU (expected: the
    next-to-us gaps are the tracker's job). The user's `serve` was stopped for the run (by command line; `watch`
    kept). Command: `..\auto-maple\.venv\Scripts\python -m maplebot serve runs\manual --attack space --jump
    shift --pickup z --loot --loot-sight --frames --gpu`.
    Tests `tests/test_gpu_sprites.py` (equal to OpenCV where scores matter, pasted Pigs anywhere with pose/feet,
    flat frame = nothing). Eval: `tools/perc/gpu_eval.py RUN MAP [--truth F]`.
    **Results:** Rain-Forest (76 frames): 36/38 reference live mobs, 0 false, 9.9 ms median / 12 p90 (the 2
    misses = real Pigs half covered by a player, 0.62-0.63 < 0.65). Perion acc3 (67 frames): 120/121, 20.5 ms
    median / 22 p90 (CPU refine: 97 ms). The live bot had 31/38 and 141/493 of the same (its band = our level only).
    All 12 sampled Perion "GPU-only" detections were real mobs (half hidden behind players/tags) - the
    one-pass reference had lost them (see truth.py below).
  - `tools/perc/truth.py` now: GPU coarse (`--cpu` = old OpenCV path, 2.6-8.7 s/frame), **two passes** (live
    poses; then hit1/die1 only where no live mob - in one pass Perion's rock matched Snail die1_2 / Stump die1_1
    at 0.60-0.67, 68 of 71 "mobs", and claimed real mobs' spots), `supported()`: hit/die < 0.75 kept only with a
    live sighting of the same mob within 80 px in the 1.5 s before (hit: +0.5 s after). Still open: on
    Rain-Forest it also dropped 3 real covered hit/die poses (0.64); two-pass Perion is ~1.3 s/frame (94 hit/die
    candidates a frame) - cut candidates before using it on long runs.
  - Either way the tracker (stage 3) stays: identity, gaps, map coordinates. The band and the colour-blob
    pre-step go away; detection covers the whole screen (all platforms) every frame.
- **Work so far (session 18, branch `perception`, uncommitted):** stage 1 - `sprites.Pose` (anim, n, facing,
  origin) per frame from mob.json, `SpriteDetector.find(..., with_pose=True)` -> (box, id, score, Pose),
  `feet_of(box, pose)`; test `test_find_reports_the_pose_and_the_exact_feet`; suite green. Stage 0 tools:
  `tools/perc/truth.py RUN MAP` (exhaustive offline reference, every pose incl. hit1/die1 over the whole play
  area -> RUN/truth.jsonl; 2.6 s/frame - the refine step re-checks up to 40 spots x all poses at full size) and
  `tools/perc/mapview.py RUN MAP TICK OUT.png` (frame with platforms/ropes/spawns projected from our minimap
  position + mobs at their feet in map x/y, and a side view of the whole map). Tried on
  runs/manual/20261103_103433_2 tick 396: the projected footholds sit exactly on the grass/pits/ladder; a
  Ribbon Pig read 43 px over pit 49's floor = mid-jump (jumps reuse move_0) -> tracks need an "in the air" state.
  Found: mob `jump_0.png` is a 1x1 placeholder with `_inlink: move/0` (not resolved to pixels; harmless, jump
  isn't searched, but check the exporter's inlink handling).
- Wider context (AI / simulator discussion, not scheduled): plan file
  `C:\Users\Yoav\.claude\plans\read-handoff-read-relevant-rustling-castle.md`.

## SUSPECTED LOOT BUG (the user, 2026-11-03): "it's barely looting anything" - investigate first when loot resumes
`perception/drops.py` `DropSpotter.update` (line ~191): a **new** drop whose centre is within `own_reach` 48 px of our
centre is discarded (added in pkg_sight1 because our own axe bobbing while we breathe looked like a drop at dx -28).
But we kill in melee (swings at dx ~47-56, step-backs at edge gap 34-43): **our kills' drops land right in that
dead zone**, and are only kept if first seen from farther away (we're usually standing next to them). Two more masks
make it worse: `_characters` blanks our body box (me_x +-20 px, 72 px tall) out of the diff, and a +-44 px box
(`char_half`) around every other name tag (other players, and maybe pets with tags).
To do: (1) measure on recorded `--loot-sight` runs (pkg_sight*, frames/) how many kills' drops are never spotted vs
spotted, and where they lie relative to us; (2) fixes to weigh: mask only the weapon (its known pose/side, or a
template of our standing weapon) instead of a 48 px circle; let drops within reach through when a kill just
happened at that spot (death position known); or just press Z (randomized) a couple of times after each kill,
since items within pickup range need no walking.
**Live test 2026-11-03, Rain-Forest 10001070, `--loot --loot-sight`:** `runs/loot1` (2 min, 6 kills, `loot_pickups` 0,
1 walk pickup) and `runs/loot2` (killed at ~100 s by the user's stop, not analysed yet). Offline on loot1: **the
bigger cause looks like the look window, not the 48 px zone** - kill #4 (30.68 s): a meso coin lay ~75 px left of us
(outside 48 px) from ~32.1 s (1.4 s after the kill), but the bot had left at 32.40 s "no (more) drops in sight":
`Timing.drop_look_s` 0.7 s after the death animation (~1.4-1.7 s after the kill in total) is shorter than the time a
drop needs to land + bob once (bob test compares a ~0.4 s older frame). Kill #2's drop was spotted only 1.3 s after
the kill (dx ~+120). Kill #3: no drop visible (none dropped). No drop landed within 48 px in loot1, so the dead zone
is still unproven (`_loot_sight` already presses Z where we stand when our mob died next to us with nothing seen).
fps was 5.8 (perceive ~226 ms; normal ~12) - slower spotting too. Next: analyse loot2 the same way, then decide
(longer look window, e.g. ~2-2.5 s after the kill; measure kill -> drop-visible time over all kills first).
Helper: scratch `strip.py RUN OUT y0 y1 x0 x1 frame...` stacked crops (rewrite if needed; frames are every 3rd tick,
named by tick n).

## TASK (2026-11-03): read Classic World's own game data with HaRepacker-resurrected
**Why:** the user is exploring a rewrite (tracker in map coordinates, later maybe a simulator / a model that learns
from their play). That needs the game's *real* rules: player physics, full mob stats, respawn times. maplestory.io
(`assets/mcw`) serves only part of the data: no `Physics.img`, no per-spawn `mobTime`. (Session 17: assets/mcw
is now built from the client - see 'Priority 1: done'.)

**Findings so far (2026-11-03):**
- Install: `C:\Nexon\Library\maplestorycw\appdata\Data\`, the modern layout: per-category folders with split `.wz` files
  (`Data\Map\Map_000.wz` 73 KB + `Map.ini`, 180 `.wz` in all) + encrypted packs `Data\Packs\Mob_00000.ms` (6 MB),
  `Skill_00000.ms` (46 MB). Mob data is inside an `.ms` pack.
- **Tool: HaRepacker-resurrected** (https://github.com/lastbattle/Harepacker-resurrected/releases): `.ms` pack support
  since 9.0.0, `.ms` v4 (ChaCha20) since 10.0.0 (Jul 2026), 64-bit split data. Classic World isn't named in any
  release note: if the `.ms` won't open, report the version/error. WzComparerR2 is the fallback for plain `.wz` only.
- v83 player physics, decompiled from the client's movement code (`CVecCtrl`), source:
  https://github.com/neeerp/RustMS/issues/295. Constants live in `Map.wz/Physics.img`: walkForce 1400, walkDrag 800,
  walk 125 px/s, jump 555 px/s, gravity 2000, fallSpeed 670, jump + direction = +80 % top speed. **They match our live
  measurements** (walk ~120-125, jump peak 64-80 px, ~0.6 s in the air) -> Classic World ~= v83 physics; read
  CW's own values to confirm.
- Mob movement reference (HeavenClient `Gameplay/MapleMap/Mob.cpp`, mirror github.com/gmh5225/MapleStory-HeavenClient):
  decide every ~200 update ticks: 1/3 stand / left / right, 25 % jump for jumpers, turn at edges, force = (speed +
  100) x 0.001, knockback on hit. Server rules (respawn, EXP split): Cosmic (P0nk/Cosmic, v83).
- Decided: **no private server for now** (not needed for the tracker; revisit only if a simulator needs mass testing).

**DONE 2026-11-03 (headless, no GUI, read-only on a copy):** HaRepacker 11.1.0 in `C:\Users\Yoav\dev\harepacker-11.1.0`
(`app\` = the official zip; `lib\` = its single-file bundle unpacked by `tools/cwdata/unbundle.py` -> MapleLib.dll).
Data copied to `C:\Users\Yoav\dev\cw-data\Data` (674 MB). Exporter: `tools/cwdata/load.ps1` + `export.ps1`, run as
`$env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\cwdata\export.ps1` (R2R off: the bundle's composite native
image clashes with pwsh's own Newtonsoft). **Key: `WzMapleVersion.BMS` (zero IV), client version 779**; GMS/EMS
"parse" but give garbage names. `.ms` packs open with `WzMsFile(...).ReadEntries(); LoadAsWzFile()`.
XML in `C:\Users\Yoav\dev\cw-data\export\`: `Map\*.img.xml` (Physics, Effect, MapHelper, UpDownBackInfo), `Map\Map0\`
(42, 10004040, 10004050, 10001070), `Mob\` (all 118 mobs), `String\Mob|Map.img.xml`. Findings:
- **Physics.img = v83 exactly** (raw walkForce 140000, walkDrag 80000, walkSpeed 125, jumpSpeed 555, gravityAcc
  2000, fallSpeed 670, slipForce 60000, maxFriction 2, minFriction 0.05; the RustMS numbers are these / 100).
- Mob info (speed is a % modifier: -65 = 35 % of base): Snail 2 lv1 45 HP spd -65 | Blue Snail 3 lv2 51 HP -50 |
  Red Snail 5 lv4 68 HP -50 | Stump 6 lv5 133 HP -70 | Pig 8 lv7 128 HP 0, jumps | Ribbon Pig 10 lv10 172 HP +5,
  jumps, pushed 25 | Dark Stump 11 lv11 236 HP -70, pushed 25. Also exp, PADamage, acc/eva, elemAttr per mob.
- Spawns: `mobTime` is 0 or absent on every spawn of the 4 maps (= normal pooled regen, no per-spawn timer);
  mobRate 42 1.0, Perion 1.0, East Rocky 0.9, Rain-Forest 1.0 (only 9 mob spawns there). Respawn timing itself is
  server-side (not in the client).
- Next (not done): `docs/game_rules.md` comparing these to the live measurements; other maps: add ids in export.ps1.

**Steps (the user does 1-3, Claude parses):**
1. Download HaRepacker-resurrected from the official GitHub releases only.
2. **Copy** `Data\Map`, `Data\Mob` (if present), `Data\Packs` (or all of `Data`) to e.g. `C:\Users\Yoav\dev\cw-data\`. Open
   ONLY the copy; never save into the game folder (integrity check). Read-only browsing, no Save.
3. Export (XML/JSON, PNG not needed) to `C:\Users\Yoav\dev\cw-data\export\`:
   - `Map\Physics.img` (whole node)
   - Mob entries from `Mob_00000.ms` for the hunted mobs (Snails 2/3/5, Stump 6, Dark Stump 11, Pig 8, Ribbon Pig 10, by
     CW ids): `info` (speed, knockback, flags like jump/fly, mobTime?)
   - Map `.img` for 42, 10004040 (Perion), 10004050, 10001070 (Rain-Forest): the `life` entries (spawns: mobTime?),
     `info` (mobRate)
4. Claude: parse the exports with Python run as `-I` (untrusted data). Write `docs/game_rules.md` (constants +
   formulas + sources) and compare each against "Facts measured live" + Session 11's jump numbers.

## HANDOFF TASK: complete refactor of targeting (the user, 2026-11-02, after session 15) - START HERE
The user: **"a complete refactor of targeting - I want to research this properly and change the behavior
fundamentally."** Not a patch on `Brain._seek/_engage/_fight`; a redesign. **Research and propose first, discuss
with the user, then build** (the user's live verdict decides; "very bad" = revert at once).

**What the user wants from fighting (their words, collected):** precise and lethal - hit exactly the hits needed,
no wasted MP, no hitting the air or dead mobs; HOLD the attack key (human-like) but only at a target that's there;
walk with purpose straight to the target and hit it; no face-tanking; no "thinking all the time" (stops, dithering);
the closest mob first; attack every mob whatever others do (no kill-steal avoidance); decisive like the fast bots
on Perion (benchmark) / Rain-Forest.

**What's wrong today (evidence, all in runs/):**
- runs/manual/20261102_093743_5 (509 s serve, 52 kills): attack held 110 s, only ~11 s on a target in reach;
  69 s blind swings ("hit by something unseen" 33x, often our own HP bar still draining after a kill), 24 s after
  kills. 131 engages, 52 'lost target before reaching it'. `runs/prec/holds.py RUN`, `runs/prec/mpcast.py RUN`.
- runs/prec2 (session 15 try, reverted): without blind/keep-swinging -> 7 kills/3 min, face-tanking. **Root
  issue: perception, not just policy** - the sprite detector loses mobs next to us (hit/knockback poses, Ribbon
  Pig quick-pose misses, a mob behind our own body), so the brain's fallbacks (blind swings, keep-swinging, dead
  reckoning) exist to paper over gaps.
- The brain is one ~1250-line rule pile (zones, cooldowns, switch margins, proofs, back-offs, step-backs ...)
  tuned run by run; behaviour emerges from many interacting timers.

**Research directions to evaluate (propose, don't assume):**
1. **Perception first:** a per-mob tracker (ID, position, velocity, last pose, HP-bar state, alive/dying) that
   keeps mobs through detection gaps (Kalman/IoU tracking, pose-robust matching, masking our body) - measure recall
   of mobs within ~100 px of us on recorded frames before touching policy. Damage numbers / hit effects as "our
   swing connected" evidence.
2. **Policy as an explicit model:** a small state machine or utility/score-based target selection (distance,
   reachability via NavMap, mob HP left, who's fighting it, threat) with few clear states (approach / strike /
   reposition / idle) instead of scattered timers; hits-to-kill learned per mob (damage per swing from the HP
   bar fraction) to stop swings exactly.
3. **Offline evaluation harness:** replay recorded ticks/frames through perception + brain, metrics per run
   (kills/min, held-attack s on target vs air/after kill, approach time, face-tank hits, idle %), so changes are
   measured before a live run. Possibly learn from the user's own play (`serve --observe` records them playing).
4. Consider ML only where it pays: a learned mob detector (small CNN/YOLO on auto-labelled sprite crops) if
   template matching can't reach the recall needed.
Deliverable of the first session: a written proposal + measurements on existing runs, for the user to choose.

**Lie Detectors 2026-11-02 (watch caught 3: 10:24, 11:05, 11:43, each gone in ~25 s; PNGs runs/watch/lie_*.png):**
the 11:43 one ended a 1931 s nonstop serve hunt (runs/manual/20261102_111130_1, 181 kills, out of MP the whole
time -> plain attack `c`, correct). 2nd LD at ~31-32 min of nonstop hunting -> the planned **rests every ~15 min**
(Future tasks) look important. The `watch` process died twice this session (mss BitBlt error, then exit 127):
check it's alive before every hunt.

## NEXT BIG FEATURE (the user, 2026-11-02) - after jumping & platforming work: an overarching 'AI' layer
The user: keep the **'instinctual' fighting** (computer vision + recognition, what we have: SEEK/ENGAGE) as is, and
add **on every hunt an analysis of the map and a calculated path** - "via machine learning / AI / a proposed
algorithm, I'm open to discussion". **Discuss with the user before building.** A starting proposal:
1. **Per-hunt map analysis (deterministic, offline data we already have):** at F7 the map is recognised ->
   `NavMap` (platforms, ropes, links, `route()`) + `spawns` (map.json 'mobs') + mob levels/EXP (assets) ->
   cluster spawns into **hunting zones** per connected platform group; score each zone = expected EXP/min
   (spawn count x mob EXP, `mobRate`) minus travel cost (`route()` time) and crowding.
2. **Plan = a circuit through the best zones** (a small TSP/orienteering over the zone graph, routes via the
   existing links: walk / jump / drop / rope). The fighting brain runs inside a zone; the planner only decides
   *where to be* when nothing is in sight (it replaces today's `_spawn_way`, which is the 1-zone version).
3. **Learning on top (optional, cheap):** log kills/min, others' presence, deaths per zone per hunt -> a bandit
   (UCB/Thompson) re-weights zones across hunts (crowded by bots -> move elsewhere). Real ML (RL on raw pixels)
   is not worth it here: the game state we need is already extracted by vision + map data.
4. Live state needed first: reliable map localization on every floor (minimap dot -> map x/y; see 'Jumping work')
   and executing route() moves (ropes/platform jumps).

## Session 15 (2026-11-02) - precise attacks: tried, live-tested, REVERTED (code back to session 14, 906 tests)
- The user, after a 509 s serve hunt (runs/manual/20261102_093743_5): "too aggressive, hitting the air, hitting
  after enemies are dead ... precise and lethal, no wasted MP"; then "better to hold the key down, it's more human
  like ... but only when target is present".
- Measured there (`runs/prec/holds.py RUN`): attack held 110 s - 69 s with no target (blind swings after "hit by
  something unseen", 33x; often the HP bar still draining from the mob we had just killed), 24 s right after
  kills, 6 s out of reach, 11 s on a target. Holding = a Power Strike at once, then one every ~0.8 s.
- Tried: no hold without `obs.target` (no blind swings, no keep-swinging while the target is unseen) + let go after
  a learned per-mob killing swing. **Live runs/prec2 (3 min): the user "very very bad ... face tanking again,
  thinking all the time, not walking with purpose to target and hitting it"**: 7 kills (vs ~18 per 3 min), held
  only 4.4 s. Cause: the sprite detector often loses a mob right next to us (hit pose, after a knockback, Ribbon
  Pig) - keep-swinging / blind swings were what killed those. (prec2 also ran at half speed: perceive ~110 ms vs
  ~53 ms normally - PC load, not the code.) Patch kept for reference: `runs/prec/patch_attack.py`.
- **Lesson:** don't remove swinging at a mob we just lost sight of until detection of mobs next to us / in hit
  poses is reliable. Safer next steps (discuss first): (1) ignore 'unseen hit' when the HP drop began during the
  fight that just ended (the false trigger after our own kills); (2) shorter blind swings; (3) fix detection
  first (Ribbon Pig poses, mob behind our body - lead #3), then precision.
- runs/prec1 is invalid (the character stood on the ladder platform at x 1118: the ladder hides our name tag ->
  me = None the whole run, no keys sent). The `watch` process crashed once with mss 'BitBlt failed'.

## Session 14 (2026-11-02, 906 tests) - idle walks head for the densest spawns (live-tested, Rain-Forest)
- The user: "the bot is always pulling ... gets stuck to the left of the portal where there is minimal spawn ...
  gravitate towards the most dense spawning area"; "this has to be determined for every map, on every hunt".
- **Cause of the left drift:** `Brain.patrol_dir` defaults to `"left"` and only a wall flipped it, so every "no
  mobs in sight" walk went left. `runs/rain_base` (2 min, start x 1118): 25 walks left / 1 right, 21 % of ticks
  left of the left portal (x < -465).
- **Fix:** `NavMap.spawns` (map.json mobs, not hidden) + `NavMap.spawn_center(y)` = argmax of a gaussian density
  (`Nav.spawn_bw` 300) over spawns within `Nav.spawn_level` 80 of our feet (our floor + its pits), cached.
  `Brain._spawn_way`: nothing in sight and > `Nav.spawn_home` 300 px from it -> walk there (no standing on the
  way; logs "walking X, toward the densest spawns"; stat `spawn_walks`); inside -> the usual 2-3 s walk + stand.
  Idle-jump bursts hop toward the centre when off it and end early before a hop would leave the area.
  `Nav.seek_spawns = False` switches it all off. Computed per map from its own map.json; the runner logs
  `spawns: N points, densest around map x X` at every hunt start (Brain + navmap are new per hunt / F7 map).
  Rain-Forest: centre x 852. Tests: `tests/test_spawns.py`; `test_jump.py`'s fixture turns it off (jump tests
  stand at x -400 on purpose).
- **Live `runs/rain_spawn2`** (2 min, start x -594): crossed right in ~20 s, then median x 942, 91 % of ticks at
  x > 300, 1 % left of the portal (was 21 %); 18 kills (rain_base 21). `runs/rain_spawn1` is invalid: the user's
  old `serve` was hunting at the same time (two bots on the keys -> "blocked walking right" on open floor).
- **Never run `run` while a `serve` is hunting** - check `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`.

## Session 13 (2026-11-02, 884 tests)
- **Looting is OFF by default** (the user will work on loot later down the line; no pet either since 2026-11-03). `Perception.loot = False`: a kill -> a short randomized phase pause -> SEEK (no
  LOOT mode, no Z, no `pending_loot`, no walking pickup, `--loot-sight` ignored). `--loot` (run/serve) turns the
  old code back on; `--loot-sight` needs `--loot` too. Gates: `Brain._go_loot`, `_leave_loot`, `_sight()`.
  Tests: `tests/conftest.py` runs every test with loot ON (they cover the loot code) unless marked
  `@pytest.mark.loot_off` (3 new tests check the off default).
- **`serve` now watches for the Lie Detector while idle between hunts too** (before: only during a hunt, so one
  right after F8 / a stop went unnoticed). Siren until gone + `runs\manual\lie_idle_<time>_<n>.png`; only looks,
  never sends a key. Before the first F7 the screen is measured with the console possibly in front (see
  `Screen.calibrate`) - if that ever misses one, run `watch` alongside as below. Not live-tested yet.

- **A 3rd kind of Lie Detector (2026-11-02 14:07, the user's screenshot, Rain-Forest):** a translucent blue box in
  the centre, white "Question in 10 seconds" / "Answer within 10 seconds" (a quiz, no window). Template
  `assets/lie_detector_question.npy` (the words "Question in"), in `liedetector.NAMES` - so `watch` and `serve`
  see it. 1.00 on the screenshot, best 0.52 on 11,833 other frames. Only one sample: if it's ever missed, grab
  frames of it. Today's Lie Detectors: 10:24, 11:05, 11:43, 13:05 (blue mini-game), 14:07 (quiz).

**Safety first - before ANY live run or series, start the Lie Detector watcher in the background** (session 9: a
Lie Detector came up seconds after a run ended, nothing was watching; the user had to catch it):
```
..\auto-maple\.venv\Scripts\python -m maplebot watch runs\watch --seconds 14400
```
(run_in_background; siren + PNG in runs\watch on detection; the game must be visible - not covered by a window).
When the user reports a missed Lie Detector: check thoroughly (every frame, the LAST frame, tick gaps, focus
pauses) and show evidence - don't brush it off as "between runs" after a quick scan.

**Where we stopped:** the user's 10 x 1-min series (`runs/accN`, analyse + fix after each) was paused after acc3
(acc1 7, acc2 7, **acc3 12 kills/60 s**). Then the user moved to **East Rocky Mountain I (map 10004050)** and
hunted with `serve`; their report there ("far targets at the screen edge are often not acquired") -> slope fix
(session 9 notes below), **not live-tested yet**. Ask the user which map to continue on; resume the series as
acc4..acc10. Commands (always from `C:\Users\Yoav\dev\maple-work`, elevated console - a relative venv path from
`~` fails):
```
..\auto-maple\.venv\Scripts\python -m maplebot run runs\acc4 --seconds 60 --attack space --jump shift --pickup z --map 10004040 --loot-sight
..\auto-maple\.venv\Scripts\python tools\acc\analyze.py runs\acc4
..\auto-maple\.venv\Scripts\python -m maplebot serve runs\manual --map 10004050 --attack space --jump shift --pickup z --loot-sight --frames
```
(game in front; mouse OFF the quickslots; HP potions on Del, MP on End; `space` = Power Strike.)

**Character / setup now:** JenkinsJob, **Warrior (Swordsman) lv ~13-14**, `space` = Power Strike (MP; potions
at 20 % are fine). EXP points are past 1,000 ("EXP. 1,201") - the reader handles the comma since session 9.
Maps: Perion Street Corner `10004040` (Stump 6, Dark Stump 11, Snails); East Rocky Mountain I `10004050` (Blue
Snail 3, Red Snail 5, Stump 6, Dark Stump 11; slopes, many platforms/ropes). Other maps: look up ids with
`(gc assets\mcw\manifest.json | ConvertFrom-Json).maps.PSObject.Properties | ? { $_.Value.name -like '*X*' } | % { $_.Name + ' ' + $_.Value.street + ' / ' + $_.Value.name }`.

**How to measure a run:** `tools/acc/analyze.py runs/X` -> EXP gains (true kills; must equal `kills`), outcomes,
HP hits (drop >= 2 % within 0.4 s) with what we held and the target dx, every walk->swing (dx, closing speed, HP
lost after), "SEEK with a mob sprite on screen" share. `tools/acc/montage.py runs/X t0 t1 out.png` -> crops
around us with target box/src/EXP/actions per frame (write PNGs to the scratchpad with Windows paths for cv2).
Also useful: offline `SpriteDetector.find` on `frames/` vs live `sprite_mobs` (perception misses); replaying
`ticks.jsonl` through a fresh `Brain` (`_pickable`/`_fair`/`_allowed` per seen mob).

**Open leads for targeting accuracy / kill rate (most promising first):**
1. **Live-test the slope fix** on East Rocky Mountain I (mobs up the slope at the left edge should now be
   targeted); watch fps (perceive 47 -> 75 ms there).
2. **Speed** (the bots react faster): fps ~12 on Perion, ~11 expected on East Rocky. The camouflage scan cost grows
   with band height. Ideas: scan the upper (slope) strip only every other frame / only far from us (the slope rule
   needs |dx| >= rise / 0.3); scan every other frame + tracker in between; fewer duplicate poses.
3. **A Stump touching our body is not detected** (acc3 18.64 s: scan 0.51 < 0.65, our sprite covers it) -> it
   hit us while we walked to a farther one. Idea: lower threshold within ~70 px of us, or mask our body out.
4. **Own name tag lost -> "hidden" back-out + ~3 s avoid** also drops targets (acc1: 3 self_lost). Agreed plan
   below ("own name tag"). **Clouds fixed (2026-11-01, separate session):** drifting clouds on East Rocky
   (manual 20261101_225745_2 286 s) washed the tag's dark box -> score 0.38-0.47 with the tag still readable ->
   "hidden? backing out" spam. `selfpos.find_self` now matches **high-passed** gray (frame - GaussianBlur sigma 2)
   with flat windows (std < 3) excluded; thresholds 0.66 full / 0.64 near (own median 0.91, p5 0.75; other
   players' tags <= 0.59 over 11.5k frames of 30+ runs). That run: tag-lost frames 60 -> 2 (real overlaps by a
   mob tag), 0 position changes, +448 frames found overall, ~4 ms. Fixtures `self_under_cloud*.jpg`. Not
   live-tested yet. Remaining tag losses = real occlusion (mob tags, screen edge) -> still the body/minimap plan.
5. Step-backs vs Stumps now fire at centre dx 47-56 (edge gap 34-43, same as snails) - fine so far; watch them.
6. **others_kill_wait_s 0.4 s**: one EXP gain came 0.6 s after "killed by someone else" (perion6 174.7 s).
7. **Damage share metric**: a full Stump ~3-10 points at lv 13-14; log per-kill points to compare with the bots.
8. Real map localization (minimap dot -> map coords + footholds): x fits on map 10004050 (dot origin 26, ~16.5
   map px per minimap px), y was ~108 px off from the canvas match -> needs calibration over several floors. The
   base for jump & drop / ropes; would replace the slope heuristic with "connected walkable ground".
- The user rejected kill-steal avoidance (don't propose avoiding mobs others fight).

## Session 12 (2026-11-02, 806 tests) - the whole game offline + map recognised on F7 (not live-tested)
The user: "init phase on F7: check the map; known -> go; unknown -> download it" -> chose **download everything
upfront, all sprites too**, then recognise the map at runtime.
- **`assets update --all`** (`gamedata.fetch_all`, resumable): 335 maps (12 "Up and Up" event maps 404 on the API)
  + all 118 mobs (also ones no map spawns), 45 MB in `assets/mcw`. (Session 17: gone - `assets build` from the client.)
- **`nav/identify.py` `MapIdentifier`**: the screen minimap is NOT the raw canvas (drawn semi-transparent + blurred:
  screen ~ 0.45-0.6 x canvas + offset; canvases ~40-50 % transparent), so colour error and plain correlation both
  failed (Henesys Townstreet - one house - "matched" every minimap). What works: (1) **window frame fit** - the
  bright window border sits 1 px outside the canvas; every canvas size tried at every spot by box sums; top and
  bottom edges must be > 50 brighter outside, sides on average (A Split Road's portal dots against the right edge
  cut it to 34); (2) masked correlation at that spot, then a **3 % trimmed** correlation (fit gain/offset, drop the
  worst pixels = markers). Look-alikes exist at the same size: East Rocky Mountain I vs IV (lead 0.13), Snail
  Hunting Ground III vs Hot Sand. Decision over 3 frames ~0.25 s apart: score >= 0.5, lead >= 0.05.
  Offline: 200 F7-like trials over 42/50/Perion/East Rocky runs -> **0 wrong**, misses only with the inventory over
  the minimap and the old squeezed-capture run. ~0.3 s per frame (~1 s per F7).
- **Runner**: no `--map` -> each F7 (and `run` start) calibrates, identifies, loads the map (sprites + NavMap +
  locator, cached per process) and logs `map recognised: <id> <street / name>, score, (next: ...)`. Can't tell ->
  **no hunt**, falling chirp, the reason logged (`can't tell which map this is: ...`); F7 again retries. `--map`
  still fixes the map (no recognition).
- Tests: `tests/test_identify.py` (fixtures `tests/fixtures/mapid/`: 3 frames each of 42, crowded 50, Perion, East
  Rocky + inventory-covered; needs the full download), runner tests for F7 init. Suite now ~31 s (was ~11).
- **Live (user, serve, Rain-Forest East of Henesys 10001070, windowed 2560x1440 -> `game picture at x (0, 2560)`):**
  recognised at F7 (score 0.71, 1.3 s), hunt 1 3 kills/40 s. Hunt 2: 0 kills - another player on the same Pigs
  AND **Pigs missed by the sprite quick check**: it tried only the stand_0 pair and cut at 0.45; Pig poses differ a
  lot (stand_0 0.44 where stand_2 0.75). **Fixed (`SpriteDetector` quick_cover 0.5, quick_gray):** representative
  poses by greedy cover of the pose-similarity matrix (Snails 2, Pig 5, Ribbon Pig 6, Stumps 8), tried in gray,
  then in colour the best one's look-alikes first. Offline vs exhaustive (all poses) reference, min_score 0.65:
  Pig hunt 2 22 -> 52/52, hunt 1 47 -> 173/177, 17-24 -> 33-42 ms; Perion 242 -> 245/245 (59 ms), East Rocky,
  42, 50 unchanged in recall and speed; 0 extra detections anywhere. Fixtures `ribbon_pig_{stand2,hit,move}.jpg`.
  Not live-tested. (A parallel session fixed EXP kill credit in brain/config - see its notes.)
- **Next: live check** - `serve runs\manual --attack space --jump shift --pickup z --loot-sight` (no `--map`), F7
  on Perion / East Rocky, then on a map never hunted before; watch the console line. Minimap must be open and
  uncovered at F7.

## Jumping work: START HERE (state 2026-11-02 ~01:35, 871 tests green)
**The user's scope now:** map **10001070 The Rain-Forest East of Henesys** (Pig 8 / Ribbon Pig 10), **ground floor
only - no platforming, no ropes/ladders yet**. Wanted: (1) `shift` = jump; (2) jump at a jumpable step on the floor
(here: the two 60 px-deep pits, platform 49 x 39-231 and 91 x 849-1041, floor y 215); (3) a few jumps when idle;
**(4) every jump moves in a direction** ("important - moving a certain direction when jumping"). The user said they
may revert all jumping and stay grounded: keep it isolated, every change revertable (list below).

**Status - all 4 built, live-tested in rain1-3 (3 min each, `runs/rainN`):**
- **Step jumps work live (rain3): 9 fired early while walking, 0 stalls in the nook** - after the fix of rain1/rain2
  (no minimap position: party dots, see below). The user's complaint "stuck in the nook, other bots jump on it
  seamlessly without stopping" is answered by rain3 - **not yet confirmed by the user's eye** (LD interrupted).
- **Idle jumps: 3 in rain1, 0 in rain2/rain3** - each burst holds one direction until landing. Never yet watched by
  the user: ask whether they look human (burst size 1-3, every 10-30 s, alternate directions).
- Blocked fallback (not moving 1 s -> one running jump, then the old avoid): fired 7/9 times in rain1/rain2 (when
  position was missing), 0 in rain3. Map edges / walls > jump_height: no jump (the map knows).
- **rain3 got a LIE DETECTOR at 165.7 s** (3rd 3-min run there in ~20 min, first runs with jumping, in a party). The
  bot stopped as designed. **The `watch` process was killed at the user's request: start it before any run.**

**How it works (where to look):**
- `maplebot/nav/localize.py` `MinimapLocator`: minimap canvas by template match (sub-pixel origin, `nav.canvas_score`
  0.4 - Rain-Forest scores 0.47-0.62 at (50, 72)), dot -> map (x, y), `NavMap.platform_at` (tries +-8/16 px: x is
  16 px coarse and ~7-15 px right of truth on this map). Perceiver -> `obs.map_pos / platform / rope` (ticks.jsonl).
- `perception/hud.py minimap_dot`: **hue >= 23, area >= 6** - party members' orange dots (hue 18-19, rims ~20-22)
  made a 2nd 'dot' -> no position at all in rain1/rain2. The user plays **in a party** now.
- `nav/navmap.py NavMap.step_ahead(platform, x, dir)` -> (distance to the closed end, rise beyond; inf = map edge).
- `brain/brain.py`: `_step_jump` (end of `_step`: holding left/right, 4 < rise <= `nav.jump_height` 70, distance <=
  random 12-40 px -> Tap(shift) with the walk key still down; 3 failed tries -> avoid that way), `_block_jump` /
  `_block_jump_ok` (in both blocked branches), `_idle_jump` + `_walk_on` (standing phase), `_jump` (cooldown 0.8 s).
  Config `Timing.jump_* step_jump_* block_jumps idle_jump*`, `Nav.*`. Stats `jumps step_jumps block_jumps idle_jumps`.
- Executor: a Tap of a non-movement key keeps a held walk key down -> running jump (no executor change needed).
- Tests: `tests/test_jump.py` (real map 10001070), `test_navmap.py`, `test_localize.py`, `test_hud.py` (2 party-dot
  tests: a rain1 fixture + a synthetic raw-frame one that fails on the old filter).

**Commands** (elevated, from `C:\Users\Yoav\dev\maple-work`; game in front; character on the Rain-Forest floor):
```
..\auto-maple\.venv\Scripts\python -m maplebot watch runs\watch --seconds 14400          # FIRST, in the background
..\auto-maple\.venv\Scripts\python -m maplebot run runs\rain4 --seconds 180 --attack space --basic-attack c --jump shift --pickup z --map 10001070 --loot-sight
```
Analysis helpers (scratch, run with `PYTHONPATH=.`): `runs/jump/tmp/relocate.py RUN MAP [-v]` (re-localize saved
frames offline), `runs/jump/tmp/stuck.py RUN MAP` (position + walk key before each 'blocked' event),
`runs/jump/tmp/check_moves.py` (Perion rope graph vs the user's recorded moves). In the log: grep `jump`.
Check `obs.platform` is non-null in most ticks first - if not, localization broke (save a raw PNG of the minimap:
JPEG frames hide colour problems, rain2's dot failed live but not on its JPEGs).

**Next steps (ask the user which):**
1. A 4th run with the watcher on, the user watching: confirm "seamless" pit exits and idle jumps look human.
2. Jump *into* a target's direction when it's up the step (now only walking triggers it - fine so far).
3. Unify the 16 px x bias per map (Rain-Forest x reads ~7-15 px right; Perion fit was +1.2 minimap px): a per-map
   marker offset, or fit it live from wall contacts.
4. Later (user's call): platforms/ropes - the graph (`route()`, rope nodes: grab/exit/let_go/leap) exists and is
   tested on Perion, no executor/brain use yet (see Session 11 below).
**Not this work (another session owns it):** Rain-Forest targeting ("very bad, walks to map edges, indecisive" -
the user); that session found party-EXP 'kills' at dx 400-1100 (`Timing.kill_credit_s`, `Target.swung_at`,
stat `foreign_exp`) and a Ribbon Pig quick-pose miss in `perception/sprites.py` - **don't edit those**; both
sessions edit brain.py/config.py: only exact string replacements, never whole-file writes.

**Revert (jumping only, keep localization):** in brain.py remove `navmap`, the jump fields, `_idle_jump _jump
_step_jump _block_jump _block_jump_ok`, `+ self._step_jump(obs, acts)` in `_step`, the two `_block_jump` branches,
the idle lines in `_walk_on`; config Timing jump block; `runner.py` Brain(navmap=...); `tests/test_jump.py`; the
test_brain.py edits (search `block_jumps`, `idle_jumps = False`, `2026-11-02`). **Keep the hud.py dot fix** (the
leash/blocked logic needs the dot; in a party it was gone). Full revert of nav: see 'To revert jump & drop entirely'.

## Session 11 (2026-11-01, 774 tests) - jump & drop, steps 1-2 on Perion Street Corner (offline, no live run)
The user chose to build jump & drop on **Perion (10004040)**. Built (no brain changes yet; nothing live-tested):
- **`maplebot/nav/navmap.py` `NavMap`**: platforms = walkable foothold chains (x1 < x2; x1 == x2 wall, x1 > x2
  ceiling), id = leftmost foothold id. Ends open unless a wall rises above the surface or the map ends there (the
  15 px stubs hanging under small platforms don't close them). Links by 4 px sampling: `walk` (surfaces meet),
  `fall` (walk off an open end), `drop` (down+jump, first floor below), `jump` (dir 0 straight up through a
  platform <= `jump_height` above; dir +-1 walking jump landing ~`jump_reach` ahead, never lower than one jump
  height), `rope` (foot platform -> the platform at its top, rope top sits 0-10 px under that surface; both ways).
  `platform_at / below / rope_at / route()` (Dijkstra, seconds). Config `Nav` (jump_height 65, jump_reach 55,
  rope_grab 80, climb_speed 90 - **all guesses until measured live**).
- **Perion facts**: ground floor = platform 54 (x -1373..2543, y 1905-2145, closed both ends). **No jump from the
  ground: every platform is >= 180 px up -> the only ways up are 8 ropes** (x -980, -124, 668, 1808, 2166, 2421;
  + 165->83 x 1732 ladder, 191->128 x -813). Small 136 px platforms form 60 px stairs (jumpable). All 31 platforms
  reachable from the ground. Many ropes hang 170+ px over the ground (ungrabbable; mobs only).
- **`maplebot/nav/localize.py` `MinimapLocator`**: finds the minimap canvas (map.json miniMap) by template match,
  **sub-pixel** (the 3440->1366 scaling puts the whole frame at x 6.05 in some runs and 6.68 in others - 1 minimap
  px = 16 map px), map = (dot + box corner - origin + marker) * 2^mag - (centerX, centerY). Marker offset fitted:
  `marker_dx 1.2` (on the x=470 rope, 173 perion4 frames, median 0.4 px), `marker_dy 7.25` (floors, median 2.4 px).
  All 7054 recorded Perion frames: 95.4 % on a platform, 2.4 % rope, 2.2 % air, 1 no dot.
- **Bug fixed: `MINIMAP_BOX` (x <= 210) cut off Perion's 243 px canvas** -> no dot on the right ~640 map px (828
  of 7054 frames). With a locator the dot box = the canvas (same corner, so `obs.dot` keeps its meaning; not past
  the canvas' bottom: game world there, a yellow pixel made a 2nd dot). Canvas positions: Perion (6, 72), East
  Rocky (30, 72), map 50 (6/28, 104) - always found, never hard-coded.
- Observation now has **`map_pos`, `platform`, `rope`** (in ticks.jsonl) whenever `--map` is given; the locator
  resets per hunt (serve re-measures the screen crop on each F7).
- Tests: `tests/test_navmap.py` (real Perion map.json), `tests/test_localize.py` (fixture
  `minimap_perion.npz`: 6 minimap crops - platform 174, ground, far right, rope 470, air, yellow under canvas).

**Live measurement (same session): `runs/jump/20261101_234718_2`** - the user jumped around Perion for 58 s with the
new **`serve --observe`** (records frames + map position, never presses or releases a key - Keyboard.release_all
would cut the player's jumps). Findings:
- Localization works live: the platform/rope timeline matches every montage frame checked (runs/jump/inspect).
  The minimap dot moves in **16 map px steps** (x and y), updates every tick.
- Jumps: 60/64 px platform jumps always land; ground hops peak 64-80 px; single walking jump 80-112 px ahead,
  ~0.6 s air; climb 128 px/s; ropes grabbed from the ground with their bottom 41-43 px up, 0.3-0.4 s after take-off.
  Config set: jump_height 70, jump_reach 85, climb_speed 125. Walking jumps may now land up to 2 jump heights lower.
- **The user moves rope to rope** (-492 -> -355 -> -275 -> 174 -> -25 -> 151 -> 252 -> 362 -> 470 -> 148; side
  jumps of 80-176 px, losing 16-96 px of height), jumps sideways from a platform onto a rope beside it (174 -> -25,
  162 -> 920, 186 -> 764) and off a rope onto a platform. **NavMap can't express this** (a rope is only "foot ->
  top"). -> **Done (2026-11-02): ropes are graph nodes** (below).
- **Stacked platforms < ~25 px apart are ambiguous** with 16 px steps (130/199 at x -968: 19 px; ledges
  113/121/124/127). Fix idea: continuity - the platform only changes after an air phase / a link's landing zone.

**Ropes as nodes (2026-11-02, 786 tests; the user said they may revert all of jump & drop and stay grounded):**
rope node id = -1 - index in `NavMap.ropes` (`rope_id / rope / is_rope`); a position is x on a platform, y on a
rope. Link kinds now: walk, fall, drop, jump, **grab** (platform -> rope, jump + up, straight or sideways within
jump_reach; rope bottom <= rope_grab over our feet), **descend** (top platform -> rope, down), **exit** (rope -> the
platform at its top), **let_go** (rope -> what's under its bottom), **leap** (rope -> nearest rope <= rope_leap 110
px that way, caught ~leap_drop 40 lower; or rope -> the highest platform 40-80 px out). `route(src, pos, dst,
dst_x)` and `landing(link, t)` handle both. 21 of the user's 23 recorded moves are links (the other 2 were double
leaps, each hop is a link) - `test_rope_moves_seen_live_are_links`. Routes: ground -> 71 = grab -124, leap -25,
exit (was a 1000 px walk to -980); 174 -> 148 = the user's own path over 5 ropes. Config: grab_body 50,
rope_leap 110, leap_drop 40, leap_land 60. Check script: `runs/jump/tmp/check_moves.py` (run with PYTHONPATH=.).

**To revert jump & drop entirely** (the brain never uses any of it): delete `maplebot/nav/`, `tests/test_navmap.py`,
`tests/test_localize.py`, `tests/fixtures/minimap_perion.npz`; remove `class Nav` + `nav:` from `config.py`; in
`perception/perceiver.py` drop `locator` / `_locate` / `map_pos, platform, rope` (back to `obs.dot =
hud.minimap_dot(frame)`) - **but that brings back the clipped-dot bug** (no dot on Perion's right 40 minimap px);
in `runtime/runner.py` drop `Rig.locator` and the NavMap/MinimapLocator setup. `hud.minimap_dot(frame, box=...)`
and `serve --observe` (`_NoKeys`, test in test_runner.py) are harmless to keep.

**Jumping in the brain (2026-11-02, 851 tests, NOT live-tested yet)** - the user: start on **The Rain-Forest East
of Henesys (map 10001070**, Pig 8 / Ribbon Pig 10; floor y 215 across x -759..1569 with two 60 px-deep pits:
platform 49 x 39-231 and 91 x 849-1041; higher platforms only by rope - out of scope), **no platforming, no
ropes**: (1) shift = jump; (2) jump at a jumpable step on the floor; (3) a few jumps when idle; "important -
moving a certain direction when jumping". Built:
- `NavMap.step_ahead(platform, x, dir)` -> (distance, rise) of the closed end ahead (inf = map edge / no floor
  beyond; None = open end, walk off). Brain gets `navmap` (runner passes the locator's).
- `Brain._step_jump`: holding left/right on a known platform, a step with 4 < rise <= nav.jump_height (70) within
  a random 12-40 px (`step_jump_min/max`) -> Tap(shift) with the walk key still down (running jump). One press per
  `jump_cooldown_s` 0.8; after `step_jump_tries` 3 failed tries -> that way is avoided like a wall.
- Blocked (not moving 1 s): first `block_jumps` 1 jump (walk key down), then the old avoid - unless the map says
  the wall ahead is too high / the map edge (no jump). Works without a minimap too.
- Idle (standing for a spawn, `idle_jumps` True): after 2-8 s a burst of 1-3 jumps, **each moving one way** (hold
  the direction, jump, hold until landing ~0.8 s, release); pause 0.15-0.8 s after landing between jumps; next
  burst after 10-30 s in the other direction (stays put; never into an avoided way / off the leash).
- Stats `jumps / step_jumps / block_jumps / idle_jumps`. Tests `tests/test_jump.py` (real map 10001070); old wall
  tests allow one extra blocked period (the jump try); the two idle walk-then-wait tests run with idle_jumps off.
- To revert only this: `Brain.navmap` + jump fields/methods (`_idle_jump _jump _step_jump _block_jump
  _block_jump_ok`), the `_step` dispatch `+ self._step_jump`, the two `_block_jump` branches, `_walk_on`'s idle
  jump lines, Timing `jump_* step_jump_* block_jumps idle_jump*`, tests/test_jump.py, the 5 test edits in
  test_brain.py (search "2026-11-02" / "idle_jumps = False" / "block_jumps").
- **rain1 (3 min, map 10001070): 19 kills; 10 jumps = 7 blocked-jumps + 3 idle, 0 step jumps.** The user: "it got
  stuck in the nook (pit 49), other bots jump on it seamlessly without stopping". Causes, all fixed (861 tests):
  1. **No minimap dot in all 1617 ticks: the character is in a party** - party members' orange dots leak 2-5 px of
     'yellow', 'exactly one dot' failed -> `hud.minimap_dot` needs area >= 10 (ours 16-24). This also disabled the
     leash/blocked-by-minimap logic in any party. Test `test_minimap_dot_with_party_members_on_the_map`.
  2. Canvas match 0.49 < 0.5 (small busy minimap, right spot (50, 72)) -> `nav.canvas_score` 0.4.
  3. x reads ~7-15 px right of truth here; at a wall that's the wrong side -> `platform_at` tries +-8/16 px when
     nothing matches; step jump accepts readings up to 20 px past the wall.
  Replay (`runs/jump/tmp/stuck.py runs/rain1 10001070`): 6 of 7 stalls began standing in pit 49's left corner (x ~46,
  wall 39) then walking left -> now jumps on the first walking tick. Offline relocalization of rain1's frames:
  P49 256 / P71 201 / P48 49 / air 57 (real jumps/falls). Note: the game picture measured x (0, 2560) this run.
- **rain2 (3 min): 25 kills, 9 jumps = all blocked-jumps, 0 step jumps again**; ended HP 27 %, MP potions used up
  (plain attack). Live ticks had a dot in only 23 of 1903 (offline on the JPEG frames: every frame) - in raw frames
  the party members' orange dots leak more 'yellow' than in JPEG, so the area >= 10 filter isn't enough. Measured
  hues: party dots 18-19 (max 20), ours 26 (max 28); the filter started at hue 20 -> **fixed: hue >= 23, area
  >= 6** (same or better on every recorded Perion/Rain frame; synthetic raw-frame test fails on the old filter).
  Raw-vs-JPEG is the likely cause, unproven: if the next live run still lacks dots, save a raw PNG of the minimap.
- **rain3 (2026-11-02 ~01:27-01:30): the minimap fix works live - 9 step jumps fired early, 0 blocked-jumps (no
  stall in the nook); 20 kills. LIE DETECTOR at 165.7 s** -> the bot let go of the keys and stopped (siren until
  the window was gone, 180.1 s). The `watch` process caught it again at 01:30:03; **the user asked to stop the
  siren -> watch (PID 26064) killed: no watcher running now - start one before the next run.** Context: 3rd
  3-min run on this map within ~20 min (rain1 01:0x, rain2, rain3), all with idle/step jumps, in a party.
- **THE USER (2026-11-02): on the Rain-Forest the TARGETING IS VERY BAD - walking constantly to the map edges (seen
  in the recordings rain1/rain2), indecisive in attacking, overall bad.** rain1: 9 "lost target before reaching it",
  rain2: 14; many far targets (dx 400-1000) chosen and switched ("closer mob ... switching"). Not analysed yet -
  needs its own session (Perion's tuning doesn't carry over: Pigs, an open flat map, other players' pets/mobs?).
- **Rain-Forest targeting analysed (2026-11-02, session maple-work-41, 866 tests, not live-tested):**
  1. **FIXED - party EXP = fake kills.** In a party, members' kills raise our EXP every ~2 s (even in SEEK with
     nothing on screen). Every EXP change during an engagement was credited to our target: 11/19 (rain1) and 17/24
     (rain2) 'kills' had the target 100-1170 px away (rain2 144.0 s: engage dx +964, 'kill' 0.18 s later, walked
     964 px to 'loot' it) = the walking to the map edges + the 'hit by something unseen' after each. Now EXP counts
     only if the target is within hold_max or we swung at it in reach within `kill_credit_s` 1.5 s
     (`Target.swung_at`); otherwise log 'not our kill (party share / another mob)', re-base, stat `foreign_exp`.
     Test `test_party_exp_is_not_a_kill_of_a_far_target`; `test_far_loot_is_not_worth_walking_to` now marks the
     target as hit. NB `tools/acc/analyze.py`'s 'EXP gains must equal kills' doesn't hold in a party.
  2. **FIXED by the F7-init session (quick_cover 0.5 default, see Session 12): the quick pose gate dropped walking
     Pigs.** Verified on these 6 frames: Ribbon Pig found 0.80-0.88 in all 6 (was 1). rain2 001143-001158: Ribbon Pig 0.36-0.44 on the stand_0 pair (< quick_score
     0.45 -> rejected before the move poses), 0.80-0.88 with quick_score 0 in every frame, pit included -> 'lost
     target before reaching it' (14 in rain2). Fix: quick set = stand_0 + move_0 pairs (or quick_cover).
  3. Party members' drops are visible to us (not private in a party): SEEK walks to them ('drop seen at dx +414').
     Loot is the user's topic - left alone. The flower 'Snail' with a tag is a pet, not a mob.

**Next (jump & drop), if kept:** 4. Executor actions per link kind (Jump(dir), Drop = down+jump, Grab = jump(+dir)
+ up, Climb up/down, Leap = jump+dir while holding up for a rope) with humanized timing + a NAVIGATE phase following
`route()`, landing checked via `obs.platform` / `obs.rope` (retry once, then avoid the link). First use: back to
the ground when on a platform / route to mobs seen on other platforms. Before that, maybe the continuity fix above.

## Session 10 (2026-11-01, 767 tests) - out of MP: plain attack (live OK), used-up potions
- The user: out of MP **and** out of MP potions -> main attack `c` (plain attack) instead of `space` (Power Strike);
  enough MP again -> `space`, until out of MP again. Built: `Brain._pick_attack` each tick (before potions):
  MP < `safety.basic_below_mp` (now 0.025, see below) and `not obs.mp_potions` -> `attack_key` = `keys.basic_attack` ("c", CLI
  `--basic-attack`); back at MP >= `skill_again_mp` (now 0.045) or MP potions seen again. Log lines "plain attack (c)" /
  "skill attack again (space)", stat `basic_switches`. `_swinging()` treats both keys as a swing. Not live-tested.
  Thresholds are bar fractions (no absolute MP read): tune from the user's max MP / Power Strike cost.
- **Live: it didn't switch at first** - the quickslot keeps the potion icon with a "0" when the last one is used
  (`runs/manual/20261101_233227_1/inspect/slots.png`), so `slot_filled` stays True: the bot pressed End every second
  and the 45 % HP stop could never fire either. Fixed: each potion press must raise its bar by `potion_gain` 0.03
  within `potion_verify_s` 0.7; `potion_fails` 2 misses in a row = used up (`Brain._have`, stat `potions_out`), one
  probe press every 20-40 s (restock). 763 tests (+ test_localize.py from another session, failing, not ours).
  Live `runs/oom1`: used up at 28.4 s -> C; one MP misread 1 % -> 18 % flipped back to space for ~4 s (to check).
  `runs/oom2`: used up at 7.3 s, then **every swing Hold(c)** (39, no space), 3 kills, probe at 42 s.
  **fps 2.7-3.7, perceive median ~258 ms** (normal ~25 ms on Perion) - not this change (brain only); another
  session's scratchpad `val.py` was running at the same time. Recheck fps with nothing else running.
- The user: "didn't come back to space although I had enough MP". oom2 MP was 13-29 of 275 and the back-to-skill
  line was 15 % (41 MP). Measured over past runs: one Power Strike drains 1-2 bar px = ~4-6 MP. Now
  `basic_below_mp` 0.025 (~7 MP), `skill_again_mp` 0.045 (~12 MP). 767 tests. Replay of oom2's MP: space all run.
  `runs/oom3`: MP 28-32 % (regenerated) -> space only, no switch to test; 8 own-tag losses, fps 3.5 (still slow).
- **Live-confirmed `runs/oom4` (the user: "great feature, seems to work")**: MP potions used up at 7.4 s; space
  at MP 5 %; C at 20.9 s (MP 1 %); probe End at 27.7 s; space again at 44.6 s (MP 5 %, a cast landed: 5 % -> 2 %);
  C at 48.1 s; 5 kills / 60 s. Done.
- **OPEN: fps 3.2-3.7 in oom1-4** (acc3 had 12.5): perceive median ~260-294 ms (`timings.perceive_ms`, already in
  ms). Not the attack/potion change (brain only). Suspect: another session wired `nav.localize.MinimapLocator` /
  `NavMap` into the runner + perceiver (`map_pos`, `platform`; runner.py/perceiver.py edited 23:36-23:44 while
  these runs happened) - profile perceive with and without the locator before the next accuracy run.

## Session 9 (2026-11-01, 711 tests) - accuracy series on Perion (stopped after acc3), East Rocky Mountain I
The user asked for 10 x 1-min runs back to back (`runs/accN`, analyse + fix after each). Stopped after acc3:
the user reported a missed Lie Detector (bottom right, the known panel shape). The user said it came "during the
last 1m run"; acc3's last frame (65.2 s) is clear and every frame of acc1-3 scored < 0.8 (also inverted / edge /
multi-scale) -> it came up seconds after the run's limit, when the bot had exited.
- **perion7** (3 min): bot logged 4 kills but the true number was ~18: **the HUD writes "EXP. 1,012" from 1,000
  points on** - the reader read nothing past 996, so every later kill became "killed by someone else".
  Fixed: `hud.exp_points` picks the digit count from the '[' position allowing 5 px commas (`EXP_COMMA`);
  fixture `tests/fixtures/exp_points_comma.npz`; all 788 perion7 frames read, monotonic.
- **Face tanking (the user: "stops too late against a Stump walking at us")**: zones are centre to centre and were
  measured on 35 px snails; Stump boxes are 62 px -> everything ~13 px late. Fixed: `Zones.mob_width` 35, the fight
  measures to the target's edge (`Target.wide`); `anticipate_s` 0.3 -> 0.45 (Power Strike lands ~0.3-0.5 s after
  the press). Test helper `mob()` default width now 35 (real snail width).
- **Hidden in reach**: a target last seen within hit reach may stay unseen `keep_close_s` 1.8 s (was 1.0) before
  "target gone" (acc1 38-39.6 s: our Stump covered by our body + a player, died to our hits 0.5 s after we left).
- Results: acc1 7 kills/60 s (2 hits taken), acc2 7 (1 hit, all swings vs Stumps at 80-112 px, no damage),
  **acc3 12 kills/60 s**, ENGAGE 74 %, 0 lost, 1 hit. Tools: `tools/acc/analyze.py runs/X` (EXP gains, outcomes,
  hits, walk->swing dx), `tools/acc/montage.py runs/X t0 t1 out.png`.
- **Lie Detector miss explained**: it came up seconds after acc3's 60 s limit (last frame 65.2 s clear) - the bot
  had exited. Built `python -m maplebot watch [out] [--seconds]` (mss, LD check every 0.3 s, siren, PNG): run it
  in the background during every series.
- **East Rocky Mountain I = map 10004050** (Blue Snail 3, Red Snail 5, Stump 6, Dark Stump 11; tall
  map 2006x2061, 134 footholds, minimap magnification 4 = 16 map px per minimap px). The user's serve hunt
  `runs/manual/20261101_222747_1`: "targets far away at the screen edge are often not acquired" -> screen x 0-200
  had 7 detections in 261 s: **mobs up the slope at the left, 60-80 px above our feet**, cut off by the 75 px band
  and rejected as 'another level'. Built: `reachable_level(..., dx, climb_slope 0.3, climb_max 75)` + the sprite
  band reaches climb_max + tallest sprite. Offline: +36 real mobs on 314 frames (all checked: Blue/Red Snails,
  Dark Stumps), 0 false; Perion unchanged. Cost: perceive 47 -> 75 ms on this map (21 -> 27 ms on Perion).
  Minimap -> map coords tried: x fits (origin 26 in dot coords), y was ~108 px off from the canvas match - real
  localization needs a per-map calibration over several floors (jump & drop work).
- Found in acc3 18.64 s: a Stump touching our body is not detected (START HERE lead 3).
- perion7's stats were wrong (comma bug): its 28 "others' kills" included ~14 of ours.

## Session 7 state (631 tests)
**State:** loot by sight works live (pkg_sight3/4: "very good results") but is still **opt-in** (`--loot-sight`,
`loot_by_sight=False`); every test since pkg_sight2 ran with it on map 50. Ask the user before making it default.
Live command used: `python -m maplebot run runs\NAME --seconds 300 --attack space --jump shift --pickup z --map 50 --loot-sight`
(game in front, minimap + quickslots uncovered, HP potions ("Egg") in the Delete slot - only 2 left at the end).
**Next live step:** rerun the 5-min test (pkg_sight6 stopped at 131 s, capture bug, now fixed - see below) and
watch for a Lie Detector.
**Open safety items the user was offered (not approved yet):** Lie Detector check while the game is NOT in front
(today paused = no check), a capture watchdog (pkg_sight5's ticks stopped at 106.6 s with no log line, probably
dxcam `get_latest_frame` hanging), Telegram alert (Future tasks).
**The user's plan:** start using skills and change locations/patterns, then see whether Lie Detectors drop
(see "Lie Detector triggers" below). Likely next feature: skill keys (attack skills/buffs, randomized use,
cooldowns) - ask which keys/skills. Roadmap otherwise: jump & drop → rests.
**Don't:** propose avoiding mobs other players fight (kill-steal avoidance - the user rejected it twice); blame
breaks or player reports for Lie Detectors (the user ruled both out).

### Session 8: Perion Street Corner (map 10004040), character is now a Warrior (Swordsman), 651 tests
New map: `--map 10004040` (Victoria Road / Perion Street Corner; mobs Snail 2, Blue 3, Red 5, **Stump 6, Dark
Stump 11** - hues 15-24 / 15-19, loaded fine). 221 footholds, 28 ropes. Find map ids:
`(gc assets\mcw\manifest.json | ConvertFrom-Json).maps.PSObject.Properties | ? { $_.Value.name -like '*X*' } | % { $_.Name + ' ' + $_.Value.street + ' / ' + $_.Value.name }`. Skills: not built yet (the user has them now).
**perion1** (3 min, --loot-sight): 6 kills, 15 killed by others, 7 "lost before reaching", 16.8 fps (perceive
median 44 ms). The user: "bad combat - indecisive targeting, other bots walk straight to the nearest mob";
"barely any loot picked, but picked while moving (minor success)".
- **Built: always the closest mob** (the user's rule, strict): while the target is out of reach, any pickable mob
  (fair, not past a wall/leash) closer than the target by `switch_margin` 20 px takes over, either side;
  `closer_cooldown_s` 0.4 against flip-flop; stat `closer_switches`. `_pickable()` shared with SEEK. A target in
  reach is never dropped for a closer one. Old test "a mob behind us does not distract" inverted on purpose.
- **Own tag lost 5x (up to 4.1 s)**: another player standing on us (tags overlap: "JenkinsJob" + "dfdfsafasf")
  plus drifting fog; even found frames scored only 0.61-0.63. Partial-template matching tried and rejected:
  other tags score up to 0.72 with half a template, ours 0.65-0.75 (`runs/perion1/inspect/tags.png`). Open.
- **hp_potions None for the whole run**: slots read fine offline (50 HP potions on Del, 30 MP on End), so every
  tick was skipped as "cursor over the quickslots" - the mouse was probably parked on them (GetCursorPos after
  the run mapped to (934, 700), inside QUICKSLOT_RECT). With None the 45 % stop fires although potions exist and no
  potion is ever drunk. Keep the mouse off the quickslots; TODO: log the cursor in ticks + warn when unread > 5 s.
- Loot: 1 pickup + 3 walk pickups in 3 min - to analyse next.
**perion2** (closest-target build): 2 kills, 18 others' kills, 9 closer_switches. The user: "back to the initial
problems: very hesitant targeting, missing targets, walking past mobs, face tanking; looting is bad".
**Root cause: the bot was nearly blind on this map** - 0.1-0.16 sprite mobs/frame (map 50: 1.65), 90 % of
frames with none. Stumps (hue 15-24) share the colour of Perion's rock: the hue blob = the whole floor, rejected
by size. **Built (653 tests): camouflaged mobs** (`SpriteDetector.camouflaged`: hue covers > `camo_share` 25 % of
the band; Shroom on map 50 = 18 %, Stumps 27-37 %) are found by shape: every distinct pose (both ways, stand_0 ==
move_0 deduped) slid over our own floor band at half res, peaks ≥ min_score (`_scan`); Stump/Dark Stump share one
scan (same masks, `shape_key`). Offline perion2: 0.16 → 0.57 mobs/frame (0.72 at the live 0.65 threshold, all boxes
checked = real Stumps), +~37 ms/frame on Perion only (maps 42/50 unchanged ~10-13 ms). Lower floors not scanned.
Fixture `tests/fixtures/perion_stumps.png` (both Stumps found). Rejected: stand-only scan (misses poses: a Stump
in move_1 scored 0.95 vs ≤ 0.51 for other frames), quarter-res scan + refine (slower, missed).
**Open: mob HP bars under Perion's fog** are washed out (S ~103 vs required > 235) → "no HP bar for us" quit our
own Stump 6x in perion2 (frames 7.3-8.8 s: bar + our damage numbers visible). Lowering S alone = thousands of
false bars on grass. A frame check (light border rows above/below) looked promising but saved JPEG frames are
unusable to validate (JPEG kills saturation: old detector finds 5 bars in 88 fight frames) → needs raw (PNG)
frames from a live run.
**perion3** (camo scan live): 1 kill; 0.39 sprite mobs/frame live (was 0.16), 14.2 fps, perceive median 56 ms.
8 × "no HP bar for us" (our own Stumps left after ~1.1 s, fog hides the bar) + 19 × killed by someone else
(very crowded). **Built (661 tests):** sprite mode keeps hitting an unproven target while its *sprite* is still
re-found (`Target.sprite_at`, `target_src == "sprite"` within 0.3 s), up to `sprite_proof_s` 6 s; a target only
tracked by template still gives up at `proof_s`. Kill = EXP as before.
**The user's decision (session 8): mobs by sprite only - no HP bar / name dependency (sprite mode).** Built, 665
tests: the perceiver skips `find_mob_bars` when sprites are on (`bar_mobs` = [], `target_has_bar` False); the brain:
proven = sprite matched (at engage + every `target_src == "sprite"`), so "no HP bar for us" can't happen; died =
EXP up and the target's live sprite no longer found (still found = EXP from another mob, fight on); others' kill
= death animation without EXP (unchanged); target gone = we hit it and its sprite is gone > `keep_swinging_s`;
"fighting us" (`_fighting_us`) = we've hit it. The old no-`--map` mode still uses bars. Next (offered, not
approved): own position without the tag - learned body looks + near-last-position search + minimap dot/vrBounds
(camera clamps at map ends: the character can hug a wall, not centred). Player tags stay (player vs mob/drop).
**perion4** (sprite only): 4 kills / 47 targets; 22 killed by others (map packed with fast bots - the user:
"they are faster than us and their targeting is spot on"), 0 "no HP bar", 11 own-tag losses. The user: targeting
much better, faster response, "but still too much thought"; a lone visible Stump missed at the start.
**Built after perion4 (675 tests):**
- The missed Stump: we stood on the slope (feet 511) - (a) the scan was limited to our own floor height, (b) with
  sky in the band the Stump share fell < 25 % → colour path (blind). Now: the scan covers the full band (incl.
  step-down) at `scan_scale` 0.375 (same recall as 0.5, ~40 ms; 0.25 = false hits), and **camouflage is sticky**
  per mob once seen in `camo_frames` 15 frames (one odd frame - a band of sky - flagged Blue Snail in a test).
  Fixture `perion_slope_stump.jpg` (perion4 11.2 s).
- **Mobs before loot** (sight mode): in LOOT any pickable mob in sight ends looting unless a drop is within
  `loot_vs_mob` 60 px (perion4 12-15 s: walked 555 px to a drop past a Stump); SEEK takes drops before mobs only
  within 60 px (was `loot_max` 120; the old mode keeps 120). Drops are private: SEEK collects them when no mob.
- Phase pause 0.15-0.5 → **0.08-0.25 s**.

**perion5**: 80 engagements (47), ENGAGE 56 % of the time (35 %), LOOT 4 %, 34 others' kills, 4 kills, 12.7 fps.
The user: "definitely much better"; **Perion stays the benchmark ("I want to compete here")**; some Stumps not
targeted immediately vs the bots. Found by replaying ticks.jsonl through a fresh Brain and asking `_pickable` per
seen mob (a useful tool; beware: a replayed walk with a recorded still dot = fake wall):
- **Drop zones** (45 px, 6 s, map x quantized to 15 px) rejected live Stumps near another's death spot → in
  sprite mode `_fair` is always True (a shape match is never a drop).
- **Leash** 60 minimap px blocked Stumps at +55 from start (stood 1.6 s; "past the leash") → `leash_minimap_px` 120.
- Remaining: the own-tag "hidden" avoid (~3 s per side) also blocks targets → part of the own-tag work.
- Perception miss seen: 160.8 s a Stump on the flat below the slope, not detected.
683 tests.

**perion6** (drop zones off, leash 120): 77 engagements, ENGAGE 67 %, "mob seen but not engaging" 2.4 % of ticks,
5 "kills", 22 others' kills, **15 "lost target before reaching it" at dx ±60-90**. Cause: **one-hit kills not seen**
- Power Strike one-shots Stumps (147 dmg), the EXP bar is 114 px (1 px = 0.88 % ≈ 15 points at lv ~13, a Stump
≈ 3 points) → EXP bar moved 5 times while the points rose 16 times; our kills ended as "lost before reaching" /
"target gone" (no loot). The 22 others' kills were real (points flat after 20 of them).
**Built (689 tests): `hud.exp_points`** reads the HUD text "EXP. 885 [51.57%]" points: monospaced 6x7 digit cells
from (749, 740), digit count from the green '[' (`(bracket_x - 749 + 1) // 6`), templates `assets/exp_digits.npy`
(36 labelled frames, every digit; '9' needed perion6 samples - with 3 it read 9 as 8). Validated on every 2nd frame
of 9 runs (2- and 3-digit, lv 6-13): 0 unreadable, 0 decreases. Perceiver: `obs.exp_points` = median of the last 3
readings; brain: **the EXP bar is gone** (the user): kill = points changed; points down (e.g. 10000 -> 3) = level-up;
unreadable = no verdict. `hud.exp_fill`/`EXP_BOX`/`obs.exp` removed; test helper `obs(exp=0.25)` → 2500 points.
The '[' colour: H 30-75, S > 45 (older frames are paler). Validated: 11 runs, every 3rd frame, 0 unreadable. Fixture
`tests/fixtures/exp_points.npz`. Note: one EXP rise came 0.6 s after "killed by someone else" (wait 0.4 s) - rare.
**Game rule (the user): EXP is split by damage dealt** - the top damager gets most (and the drop); others hitting
our mob cut our share. So points up = "we did damage to it", not "our kill"; stat `kills` counts mobs we got EXP
from. "Death animation + no points" = we did no damage. After a shared kill the drop may be the other player's
(invisible to us) → loot by sight finds nothing and moves on (no Z without a seen drop).

### LATER (the user): **loot is horrible - the user will work on it and it needs proper attention.** (session 13: OFF by default, nothing picks up; `--loot` re-enables)
Don't patch loot piecemeal before that session (session 9 = targeting/kill rate first). Data: perion1-4 loot_pickups 0-1, walk_pickups 0-3 per 3 min.

### After loot / next: **own name tag lost - "can't continue"** (the user). Plan agreed in principle: tag first;
when lost, learned body looks of us (saved while the tag is clear, several poses, refreshed - gear changes) searched
near the last position; minimap dot (+ `vrBounds`, camera pinned at map ends) for a coarse x; full-frame + dot at
start. perion4: 11 losses, 17 backouts.
- `space` = **Power Strike** now (the user, session 8): uses MP; MP potions on End at 20 % are fine (the user).
- (answered: yes, `space` = Power Strike.) One MP 1 % misread triggered an MP potion at perion2 144 s.

### pkg_sight6 (5 min planned, map 50, --loot-sight) → stopped at 131 s: "no HP potions" with Eggs in the slot
`Screen.calibrate()` measured the game at x 439-**3034** (every earlier run 439-3001): something lit in the right
pillarbox bar at startup counted as game → frame squeezed 1.3 % → HP bar 5 px, quickslots 13 px off → the Delete
slot box sat on the gap between keys → `hp_potions` False all run → HP 43 % < 45 % → safety stop.
**Fixed (`capture.game_columns`):** a column is game only if > 30 % of its rows are lit, and the width is always
the 1366:768 shape at the client height (lit span wrong → centred). `tests/test_capture.py`. The Egg (mostly
white, ~8 % coloured) reads filled when aligned (pkg_sight4) but sits right at `slot_filled`'s 0.08 threshold -
if potions ever misread again, consider counting dark outline/quantity-digit pixels too.
Run itself: 4 kills / 131 s, 8 "killed by someone else", 20 step-backs (very crowded); no Lie Detector.

### pkg_sight5 (3 min, map 50, --loot-sight) → Lie Detector at 55.5 s, siren did NOT sound
A **new blue variant** ("The Lie Detector Mini-game" title in blue, panel 55.54 s, mouse mini-game ~65.9 s, the
user passed it, SUCCESS 82.3 s) that the gold-title templates missed → the bot hunted through it. Fixed:
`lie_detector_blue_title.npy` added to `NAMES` (panel 1.00, game 0.96; best on 7311 other frames 0.55), fixtures
`tests/fixtures/lie_detector_blue_{panel,game,none}.jpg`. Ticks then stopped at 106.6 s without a log line (see
capture watchdog above).

### pkg_sight4 (3 min, --loot-sight, walking pickup) → "very good initial success"
10 kills (3.3/min, best yet), Z 11.7/min (session 6: 39), 0 give-ups, 20.9 fps. **Z while walking DOES pick up**
(frames: shells/spores fly up right after walking bursts at 55, 61.7, 64, 99 s; the old 'walking Z does nothing'
note was wrong). Coins next to items were left (spinning coins are recognized less often).
The user: "the amount of presses is too low, many items were missed" + "when there are no mobs around a player
would prioritize getting loot". Changed (624 tests): bursts 3-5 presses (walking: over 0.3-0.65 s), **+1 per
other drop lying within 30 px**, cap 8; no mob in sight → drops anywhere on screen (`loot_idle_max` 600) are
collected. Next idea for the misses: coin sprites (universal, 4 spin frames, see session 7 notes).
Retargeting to a closer mob → Future tasks.

### pkg_sight3 (3 min, --loot-sight, priority fix) → "Very good results" + walking pickup
9 kills (3.0/min, session-6 level). 18 of 19 give-ups were false drops **below the ground line**: megaphone chat
scrolling up under the floor = vertical-only motion. Fixed: drops only on our own floor (lower platforms wait for
jump & drop); the brain checks the height too; a re-found drop may not drift > 3 px from where it was first seen.
**The user's change (built, 612 tests):** "humans pick up loot while walking at every opportunity, spamming a few
Zs when they pass the item; with a lot of loot in one spot they fully stop". And: "make the bursts humanized:
number of presses, time between presses, total time per attempt".
- `_walk_pickup` (any mode, walking): a seen drop within `pass_reach` 30 px → 2-4 Z over a random 0.25-0.55 s,
  each gap jittered, walk key kept down; a started burst is tapped out even if we stop; swinging cancels it.
- LOOT walks *through* drops (`pass_over` 15-35 px past) instead of stopping; a pile (≥3 within 30 px), a drop
  right under us, or one still there after a walk-by (1 s grace: picked items fly up and are 'seen' a moment)
  → stop + burst + look (as before). Looting that ends mid-walk walks on the same way (no turn-around).
- **Unverified:** one earlier live observation said Z while walking over a coin did NOT pick it up. If walking
  pickups never work live, the fallback (stop on it) still gets the item, but with extra Z. Check the log:
  `walking past a drop` vs `still there after walking past it`.

### pkg_sight2 (3 min, map 50, --loot-sight, minimap visible)
The user: "looks like an improvement, I saw it go straight for loot and grab loot a few times, but quite a few
misses ... completely ignored coins and items". Data: Z 21/min (was 39), LOOT 17 % of the time (as before).
**Misses were priority, not recognition:** 1025 ticks had a seen drop ≤120 px; SEEK always took any mob in sight
first (41.0 s: drop 7 px away, walked ~500 px to a Shroom) → on a crowded map drops were only taken on an empty
screen. Fixed: drops ≤ `loot_max` come before mobs farther than `mob_over_loot` 140 px; a close mob or one
fighting us (HP bar) still first; a mob in reach still interrupts looting. Still open: a coin at our feet not picked
after 2 bursts (93 s, unknown why), a Red Snail mid-fight taken for a drop (135 s), small false boxes near tags.

### pkg_sight1 (3 min, map 50, first live run of loot by sight)
8 kills, 18.4 fps, Z 34/min (was 39). Real pickups seen (93.7 s: a Red Snail Shell flies up to us). Two bugs, both
fixed + regression tests (582 tests):
- **Our own weapon was a 'drop'**: standing still facing left, the axe sticks out ~28 px and bobs with our idle
  breathing ("drop seen at dx -28/+28" over and over; most of the 14 'pickups' and 10 give-ups were the axe).
  → no NEW drop within `own_reach` 48 px of our centre (known ones are still followed in); other characters'
  margin 44 px. Fixture `tests/fixtures/drops/map50_own_axe_none`.
- **No minimap dot in 93 % of ticks**: the user had the inventory (Etc tab) open over the minimap → the wall check
  never fired; held left into a step for 5 s twice. → blocked also by our own movement (odometer < 4 px in
  `blocked_s`) when there's no dot. (The leash is off without the dot too.)

## Session 7 summary (2026-11-01): loot by sight — universal, no item assets
**The user's decisions (don't re-litigate):** must work on **every map with no per-map item work** (drop tables
+ item sprites rejected: the API has no drop tables; thousands of items); **Z: spam 2–4 presses per item, short
humanized gaps** ("humans usually press Z multiple times"); **in Classic World other players' drops are invisible
(no party) → every drop on screen is ours** (no ownership logic needed; the floor of map 50 was full of *our* old
drops the blind sweeps missed).

**Perception — `perception/drops.py` `DropSpotter`** (fed every frame by `Perceiver` → `obs.drops` [boxes]):
- The user: items on the ground "shimmer, float and move slightly vertically". Measured: a red potion bobs y
  549–554 (±3 px) with x fixed; picked up it flies up to us (y 549→500) and vanishes. So: frame vs one ~0.4 s
  older (camera shift from `phaseCorrelate` on a strip around our floor) → changed patches → **the old patch
  re-appears at the same x (±1 px), shifted 1–7 px vertically only (and better than unshifted)** = a drop.
  Scenery doesn't change; players/mobs move sideways / change shape; spinning coins pass often enough.
- Filters: name-tag bodies (`find_tags(rows=...)`, now band-limited), our own body (narrow, ±20 px: drops at
  our feet are in pickup range), UI, tag-text patches (someone climbing a rope = vertical-only motion too),
  on-ground only (bottom feet−12..feet+4, or lower ground ≤ +86), item size 10–44 px; wider blobs split into
  item-wide pieces (a coin touching a spore = two drops); a piece overlapping a bigger drop is merged.
- Memory: each drop keeps up to 4 looks (coin spin phases) and is re-found by template every frame; gone when
  not re-found for 0.8 s while in view and not behind a character (picked up). Hidden behind us = not reported but
  not forgotten.
- Offline (tools/loot/replay_drops.py): map 50 crowd stretches → **no false positives** (7 players, Shrooms,
  swings, berry bushes, fading-in mobs); map 42 snails/flowers → none. Every lying item found within a few
  frames; misses: thin items (a stick/arrow < 10 px wide), coins sometimes (spin), items under our body.
  ~10 ms/frame (tags 2–3, shift ~3, detect ~5).
- Rejected on the way (don't retry): matching API item icons (shell 0.30 behind a rope/grass; per-map lists);
  "new near our kill" frame differencing (players/swings swamp it; and leftovers were there *before* the kill);
  "perfectly still" (items bob). Coin sprites exist (`/api/wz/MCW/1/Item/Special/0900.img/0900000[0-7]/iconRaw/n`,
  4 spin frames, matched 0.84–0.89) — not used; add only if live coin recall is poor.

**Brain (sprite mode, `cfg.perception.loot_by_sight`, default on with --map)** — `_loot_sight`:
- After our kill: LOOT; drops already visible are taken at once, otherwise look for `drop_delay_s` + `drop_look_s`
  (0.7). Nearest seen drop within `loot_max` (not past a wall/leash) → walk onto it (no Z while walking; release
  early by the slide), stop, **burst 2–4 Z** (`drop_taps_min/max`, gaps `pickup_gap_*`), wait `loot_check_s`
  0.35 → gone = picked (`loot_pickups`) → next drop; still there → 2nd burst → give up (`bad_drops` 30 s).
- Standing on a drop hides it, so "gone" may mean "covered": every burst spot is remembered (`drop_bursts`);
  a drop seen again where we burst twice is left alone (no Z loop).
- Our mob died ≤ 40 px from us and no drop in sight → one burst where we stand (drops behind our body).
- No drop seen → **no Z at all** → SEEK. SEEK with no fair mob and drops in sight → collect them (instead of the
  idle walk). Mobs outrank drops; a mob in reach interrupts looting. `pending_loot` (blind) is off in sight mode.
- The old sweep LOOT still runs without --map (tests unchanged).
- **Assets: `run/serve --map <id>` downloads the map and its mobs the first time** (`gamedata.ensure_map`);
  `assets update` still works for refreshes. (Session 17: both gone - a missing map now says `assets build`.)
- Tests: `tests/test_drops.py` (3 recorded sequences in `tests/fixtures/drops/` + synthetic bob/slide/still/
  climber/picked/hidden), `test_brain.py` `test_sight_*` (simulator `_sight_walk`: drops hidden under our body,
  Z picks only standing still within 30 px). Tools: `tools/loot/` (replay_drops, export_seq, probes).

## Session 6 summary (2026-11-01, all live-tested unless noted)
- **Decisive** (pkg_decisive1, "perfect test, very human like"): fight stops 5.0 s → 0.23 s per run. Hold zone
  walks in at once (waits ≤ 0.2 s only to measure if a snail charges); a target missed mid-approach is walked to
  by dead reckoning; a random 0.15–0.5 s beat after looting, never mid-approach.
- **serve / hotkeys** (the user's own testing: "amazing amazing amazing bot behavior", 31 min, 111 kills).
  Bug found: capture must be calibrated with the game in front (`Screen.calibrate()` on every F7).
- **Humanized timing**: skewed ±25 %, wandering session tempo ±8 %; step-backs vary (0.24–0.42 s, a beat before
  turning, 15 % skipped).
- **Other players' kills**: death animation detection (`dying()`), stop swinging at once, no Z on their drops
  (Z/min 84 → 39, kills/min 2.0 → 3.0 on map 50).
- **Lie Detector #2** after 31 min nonstop on crowded map 50; siren worked. Analysis below ("Manual serve
  session" / "5-min analysis run").

**B.** Keep in mind every change must not reintroduce repetitive patterns (lie detector, see below).

0. Idle stop: **done, live-tested in pkg_idle1** ("stop and wait was perfect"). **Lie Detector stop: built, 481
   tests green, not seen live yet** (see "Lie Detector" below).
1. **Live-test potions** (built, never run live; pkg_potions1 never dropped below 95 % HP): `run runs\pkg_potions1 ... --map 42`. Check:
   the log shows `HP xx% -> potion (delete)` below 20 %, the potion count on the Del keycap drops, no 45 % stop while
   potions remain, and the stop *does* happen at 45 % once the slot is empty. Make sure HP is full before the run.
2. **New goal: jump & drop recognition** (see the section below): the next big feature.
3. Smaller open items: see "Open issues".

## User & working style
- Senior Python test-automation dev (Windows, infra). Wants evidence (logs, frames, numbers) and test-first fixes.
  Watches every live run and reports what they saw; their game knowledge is gold.
- Loop that works: **user says "ready" → 90 s live run → read log.txt / ticks.jsonl / frames (crop montages around
  the character) → reproduce as a test → fix → pytest green → record in this file → next run.**
  Reply with what was found, the fix, and the run command; keep it short.
- Character **JenkinsJob**, Beginner (~lv 6), map **42 = Snail Hunting Ground III** (Maple Road), ground floor.
  Other players farm there too. The user moves the character to the spot they want before a run.
- **Keys:** attack `space`, jump `shift`, pickup `z`, HP potion `Del` (the user calls it "DEF"), MP potion `End`.
  HP potions on Del (4 on 2026-11-01); **no MP potions yet** (MP logic built, test later).
- **User decisions (don't re-litigate):**
  - **No fixed intervals between actions** (bot detection): every press/wait through `hz.vary/between/count`.
  - **Attack every mob regardless of other players** — no kill-steal avoidance; don't propose it.
  - **Be decisive like a player**: no stop-and-look pauses; walk to a mob and hit it in one motion.
  - **Nothing to attack → walk a random 2–3 s, then stand still and wait for a spawn.** pkg_potions1 paced
    wall to wall for 57 s on an empty floor and **triggered a lie detector test** (very bad). Never patrol endlessly.
  - **Potions:** drink at 20 % HP (not 60); the 45 % stop applies only when no HP potions are left.
  - **Loot by sight** (session 7): universal, by the bob of lying items, no item assets; 2-4 Z per item.
  - The **bridge** on map 42 (dot x≈156) hides the name tag completely: ignored by choice (user farms elsewhere).
  - LOOT keeps the user's description: burst 3–5 Z on the drop (then 1–2 further across).

## Environment
- Project `C:\Users\Yoav\dev\maple-work` (package `maplebot`, tests `tests/`, run outputs `runs/`, old experiments
  `tools/` unused). Not a git repo.
- Python venv `C:\Users\Yoav\dev\auto-maple\.venv` (Py 3.12: opencv 5, numpy, mss, dxcam, pytest).
- **The game runs elevated, so the bot must too** (Windows drops SendInput from a lower-integrity process).
  Check: `whoami /groups | Select-String Mandatory` → "High Mandatory Level". The sessions so far ran elevated.
- Screen 3440x1440; the game renders 1366x768 pillarboxed; everything is normalized to 1366x768 (`capture.py`).
  **Measured: sprites appear 1:1 in these frames** (no widescreen stretch). Saved frames are 1366x768.

## Commands (from `C:\Users\Yoav\dev\maple-work`)
```powershell
..\auto-maple\.venv\Scripts\python -m pytest                       # 959 tests, ~40 s, no game needed
Get-Process python | ? Path -like '*auto-maple*'                    # make sure no bot is running
..\auto-maple\.venv\Scripts\python -m maplebot watch runs\watch --seconds 14400   # Lie Detector siren, no hunt (keep running)
..\auto-maple\.venv\Scripts\python -m maplebot run runs\NAME --seconds 90 --attack space --jump shift --pickup z --map 42
..\auto-maple\.venv\Scripts\python -m maplebot assets build    # game data from the client export (assets/README.md)
```
**Manual testing (the user's own sessions):** `python -m maplebot serve runs\manual --map 42` (same key options
as `run`, plus `--frames`; loot is off unless `--loot`): loads once, **F7 = start a hunt, F8 = stop** (all keys released; rising/falling chirp),
as often as wanted; Ctrl+C in the console quits. Between hunts it still watches for the Lie Detector (siren). Each hunt → `runs\manual\<date_time>_<n>\` (log + ticks; frames
only with `--frames`). F7 is ignored unless the game is focused. The user finds problems this way, then runs a
captured `run` from Claude to reproduce.
`run`: 3 s countdown, brings the game to front, pauses + releases keys on focus loss, stops on the time limit or
HP < 45 % with no potions (alarm). Output: `log.txt` (decisions), `ticks.jsonl` (every tick: Observation,
actions, timings), `frames/` (JPG every 3rd tick + every Track/Stop/Forget). Run it with a ~200 s timeout and
`| Select-Object -Last 80`. **Always pass `--map 42`** (sprite mode); without it the old motion/library mode runs.

## Game data (`assets/mcw/`, read `assets/README.md`)
- **From the game's own client files only** (session 17; before: a maplestory.io copy). `tools/cwdata/export.ps1`
  exports a copy of the client's Data folder, `python -m maplebot assets build` (`maplebot/gamedata.py`) converts
  it; the bot only reads local files. All 336 maps (301 with a minimap) and 117 mobs. Classic World ids: Snail 2,
  Blue Snail 3, Red Snail 5; maps 40/41/42 = Snail Hunting Ground I/II/III.
- `maps/<id>/map.json`: **footholds** (`x1,y1,x2,y2`, `prev/next`, `layerId`, `groupId`), **ladderRopes**
  (`x, y1, y2, isLadder`), mob spawns (`y` = ground, `walkAreaX1/X2`, `mobTime`), npcs, portals, **miniMap**
  (`centerX/Y`, `magnification`, canvas), `vrBounds`, `info`. `minimap.png`.
- `mobs/<id>/<anim>_<n>.png`: every animation frame, RGBA, facing left; `mob.json`: `info` (all client stats),
  `frames` with each frame's **origin (feet), lt/rb body box, head, delay**.
- Player physics (`Physics.img`, = v83) is in the export (`cw-data\export\Map\Physics.img.xml`), not in assets.

## Architecture
| Module | Role |
|---|---|
| `config.py` | every threshold, zone and timing (`Keys Zones Timing Perception Safety Humanize`) |
| `capture.py` | window lookup, dxcam capture (mss fallback) → BGR 1366x768, cursor position |
| `keyboard.py` | SendInput scan codes, focus-guarded `Keyboard` (humanized press/gap/reaction), `bring_to_front` |
| `humanize.py` | `Humanizer.vary(secs)` ±20 % triangular, `between(lo, hi)`, `count(lo, hi)` |
| `gamedata.py` | client export → `assets/mcw` (+ CLI `assets build`, `changes.txt`) |
| `perception/liedetector.py` | **Lie Detector** (anti-bot test) by its gold window title → `obs.lie_detector` |
| `perception/hud.py` | UI mask; HP/MP/EXP fill; minimap dot; mob HP bars; **quickslots** (`SLOTS`, `slot_filled`) |
| `perception/selfpos.py` | own name tag (template); partial match at the screen edges (`_at_edges`) |
| `perception/sprites.py` | **`SpriteDetector`**: mobs by their game sprites (colour blob → masked match) |
| `perception/drops.py` | **`DropSpotter`**: loot on the ground by its bob (no item pictures) → `obs.drops` |
| `perception/mobs.py` | `Tracker` (template follower); `MobLibrary` (learned looks; off in sprite mode) |
| `perception/tags.py`, `motion.py` | other name tags, motion blobs (only used without `--map`) |
| `perception/perceiver.py` | frame → `Observation` (me, hp, mp, potions, bar/sprite/known mobs, target, scene_dx) |
| `brain/brain.py` | `Brain.step(obs) -> [actions]`: **no I/O, time from obs.t**, fully unit-testable |
| `brain/actions.py` | Hold / Release / Tap / Look / Track / Untrack / Learn / Forget / Stop |
| `runtime/runner.py` | live loop, recording; `runtime/executor.py` actions → keys (a non-movement Tap keeps a held walk key) |

Brain tests run 4× (jitter off + seeds 1–3); sprite-mode tests use the `sbrain` fixture. Assertions must allow
for jitter (`longest()` helper). `_loot_walk` in test_brain simulates walking, slide and odometer gain.

## Perception (sprite mode, `--map 42`)
- **SpriteDetector**: per mob, signature shell hues from its sprite (Snail 80–94, Blue 100–109, Red 165–174);
  blobs of that hue in the ground band, shell-sized (0.3–3× the sprite's); around each, masked TM_CCOEFF_NORMED of
  the stand/move/hit1 frames (both directions) at half resolution; stand pair first (< 0.45 = reject), stop at the
  first frame ≥ 0.85, last matched pose tried first. Hits ≥ 0.65 → `obs.sprite_mobs` → `known_mobs`.
  Offline: ~79 % of HP-bar mobs found (misses: hidden behind us mid-swing, LEVEL UP banner, dying), ~2 mobs/frame
  nobody had hit, **no false positives seen**; ~13 ms/frame.
- **Target**: re-found each frame from the sprite hits (nearest within 70 px of where it should be, camera shift
  applied); then its HP bar; the template tracker only bridges gaps ≤ `unconfirmed_s` 0.6 s and may never report
  a box on our own centre.
- Own tag: full match 0.62 / near 0.55; at the screen edges the visible part (≥ 44 of 74 px) is matched.
- HP: best of last 6 readings; the low-HP flash (pale pink *and* dark) is handled. MP likewise.
- Quickslots: `slot_filled` = ≥ 8 % coloured pixels (empty keycap 0 %, potion ~25 %); frames with the cursor over
  the key layout are skipped (tooltip), majority of the last 5. "Slot empty" = "no potions left".
- `reachable_level`: a mob's bottom within `same_level` 35 of our feet, or up to `step_down` 80 below.

## Brain behaviour (SEEK → ENGAGE → LOOT → SEEK; LOOT only with `--loot` since session 13)
1. **Potions** (every tick, before anything): HP < 20 % and HP potions → Tap Del (cooldown ~1 s varied); MP the
   same on End. **Stop** at HP < 45 % only if no HP potions. **Can't see own tag** → release, back out the way it
   came; afterwards avoid that direction ~3 s (`hidden_avoid_s`).
2. **Blocked** (walking, minimap x frozen 1 s) → avoid that direction 15 s; walls both ways → walk away from the
   last one. **Leash** 60 minimap px around a *steady* start reading; new targets need leash − 6, a fight may run to
   leash + 6 (no edge flip-flop).
3. **SEEK** (sprite mode): nearest fair known mob → ENGAGE; nothing → walk on for a random 2–3 s
   (`idle_walk_min_s/max_s`), then **stand still until a mob shows up** (stat `waits`); each engage resets it.
   Pending loot (left for a fight) is collected first when no bar mob is around.
4. **ENGAGE**: kill = EXP up (target's bar gone now or within 0.5 s). A target that showed its bar and is unseen
   > `keep_swinging_s` 1 s → "target gone" → loot its spot. Target on lower ground (> 35 px below our feet) → walk
   to it (step down). Zones (centre to centre): < 42 contact → one 0.3 s step back (~1.2 s cooldown);
   ≤ 66 hit; walking in → attack at 76 + its approach speed × 0.3 s (the swing stops the walk, the slide carries
   us in); standing 66–92 → walk in, unless it charges at us ≥ 35 px/s (then face it and swing as it arrives;
   with a bar we wait ≤ 0.2 s to measure that). A target missed mid-approach → walk on by dead reckoning.
   After looting: a random 0.15–0.5 s beat before walking to a far target (phase boundary, never mid-route).
   Mob approach speed = `_approach()` from odometer + rel_dx over ≤ 0.5 s. A mob in reach / in our path / hitting
   us outranks a far target (switch margin 20 px + ~1 s cooldown). Proof of mob: hit 1.2 s, no bar → not a mob →
   loot it (single item).
5. **Hit by something unseen**: go back to where we were hit, swing there (≤ 2 s).
6. **LOOT**: wait ~0.9 s for the drop → walk onto it pressing Z → stop (after a ≥ 0.4 s walk let go 22 px early:
   slide) → burst 3–5 Z → 45 px further across (single item: back the near side) → burst 1–2. A mob in reach
   interrupts it (drop → pending).

## Facts measured live (don't re-derive)
- **User's rules:** a mob shows HP bar + name **only after being hit**; loot **never** has text under it; players
  **always** have a name under them. Knockback throws you either way, but **the mob stays where you were hit**.
- Mob HP bar: pure green (H≈60, S 255), 3 px tall. Mob box = (bar.x−10, bar.y+8, max(w,30)+20, 50).
- HP bar x 503–607, MP 611–715, y 751–764; EXP 724–837. Quickslots 4x2 at (942|977|1012|1047, 631|665), 28x25:
  Shift Ins Home PgUp / Ctrl **Del** **End** PgDn.
- ~15 screen px per minimap px (map x ≈ dot_x·15 + rel_dx). Beginner walks ~120–125 px/s; slide after letting go
  ~8 px (short walk) / ~16 px (full speed). Camera shift via `cv2.phaseCorrelate` → `scene_dx`; the odometer sees
  ~85 % of real movement.
- Hits land at dx 56–66. Snails walk at us at ~40–110 px/s once hit. A hit knocks you 50–95 px.
- Drops appear ~0.9 s after the kill, spread ~±60 px. **Pickup range ~±30 px, one item per press. Pressing Z
  while walking over a coin did NOT pick it up**; standing still works.
- A snail can vanish without EXP for us (another player's kill).
- Loop ~17–22 fps with dxcam in sprite mode (perception ~25–40 ms live).

## Run history (90 s each; `runs/`)
| Run | Kills | HP end | Notes |
|---|---|---|---|
| pkg_burst1 | 9 | 70 % | best before sprites (motion + library mode) |
| pkg_sprites1 | 2 | 93 % | first sprite run: "combat quality enormous, much more human"; motion targets wasted time |
| pkg_sprites2 | 3 | 97 % | too many look pauses; stuck 57 s in a dip between ledges (**needs jumping**) |
| pkg_sprites3 | 6 | 51 % | hesitant approach; both directions avoided → stood 10 s; tag cut at the screen edge |
| pkg_sprites4 | 4 | 86 % | bridge hides the tag; tracker on own body → air swings; ran into snails |
| **pkg_sprites5** | **10** | 75 % | **best**: "amazing run"; wanted slightly more aggressive |
| pkg_sprites6 | 6 | 67 % | great until 42 s, then a leash-edge engage/drop loop (fixed) |
| pkg_sprites7b | 5 | 71 % | 14 s swinging at flowers after the target vanished (fixed); stood between two walls (fixed) |
| pkg_sprites8 | 6 | 44 % | 6 kills in 42 s among Blue Snails → safety stop → **potions built** |
| pkg_potions1 | 5 | 95 % | potions never needed (untested); no mobs from 37 s → paced wall to wall → **lie detector test** → idle stop built |
| pkg_idle1 | 4 | 100 % | idle stop works: walked 2.4 s, stood 31 s, engaged the spawn at once; "stop and wait was perfect" |
| **pkg_decisive1** | **9** | 88 % | decisiveness: 1 stop of 0.23 s in fights (was 5.0 s); "perfect test, very human like" |

## Lie Detector (the game's anti-bot test) — very important
- pkg_potions1: at **52.4 s** a panel came up bottom right ("LIE DETECTOR — 5 sec until the Lie Detector mini-game
  starts. Please find the beautiful Violetta…"), then the **mini-game window** in the centre (4 numbered pictures,
  answer by clicking/number, timer). The bot walked on through both for 40 s. Frames: `runs/pkg_potions1/frames/
  001197.jpg` (panel), `002907.jpg` (mini-game). Likely trigger: endless wall-to-wall pacing (fixed by the idle stop).
- **Detection** (`perception/liedetector.py`): both windows carry the same small gold "LIE DETECTOR" title;
  grayscale TM_CCOEFF_NORMED over the whole frame with two 74x12 templates (`assets/lie_detector_{panel,game}.npy`).
  Panel 0.89–0.90, mini-game ~1.0; best match on ~14,000 frames of 29 runs without it: 0.67 → threshold 0.8.
  ~13 ms per check, so it runs every 0.3 s (`check`, throttled by obs.t).
- **Reaction**: `Brain.step` checks it **first** (before potions): Release + `Stop("LIE DETECTOR ...")`. The runner
  releases every key, plays a **siren distinct from the HP alarm** (1500/1000 Hz) **until the window is gone**
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

## Manual serve session 2026-11-01 (map 50 A Split Road, crowded) → Lie Detector #2
The user: "amazing amazing amazing bot behavior … behavior looked perfect"; the siren worked. Hunts 13:30–14:19
with short gaps; **hunt 5 (`runs/manual/20261101_134811_5`) ran 31 min nonstop** (111 kills, 3.5/min) and got the
Lie Detector at 1877 s. Profile (`tools/session_profile.py <hunt>`), what a detector could see:
- **No break in ~45 min** of play, nothing but fighting (no chat/inventory/rest). → rests task below.
- **Z spam: 82 presses/min, 2583 total ≈ 23 per kill**, much of it on empty ground: sweeps after "target gone"
  (71), "not a mob" (52), going back to drops left behind (57). A player presses Z when they *see* an item.
  → loot by sight would cut most of these; meanwhile fewer Z per sweep.
- **Step-backs 256 (8/min)**, always the same shape: 0.3 s step away + 35 ms turn tap back.
- **Swinging at nothing**: 52 × "not a mob" (1.2 s at something with no HP bar) + 86 blind swings (hit by
  something unseen): odd-looking in a crowd where other players watch (reports?).
- Long stretches at 19–40 % HP (15 potions in 31 min).
Unknown what actually triggers it: pkg_potions1's test came 52 s into a run (so not just session length; maybe
random checks, player reports on crowded maps, or behaviour). Both times on maps with other players.

### 5-min analysis run `runs/pkg_human5m` (map 50, crowded; new humanized timing)
10 kills in 5 min; **of 50 engagement outcomes only 10 were our kills**: 18 "not a mob", 13 lost before reaching,
9 target gone. Montage `runs/pkg_human5m/notamob.png`: **the 18 "not a mob" were real Shrooms/Blue Snails**,
nearly all **killed or being hit by another player** (242 s: fgbcas kills our Shroom as our first hit lands; the
death animation, then a respawn, frames 004158–004176). No EXP for us → no HP bar for us → after ~1.1 s "not a mob"
→ **we keep swinging at the spot, then sweep Z over another player's drop**. Z: 420 presses for 10 kills (42/kill).
That is the most bot-like thing seen: run at a mob someone else is fighting, swing at air, Z-spam their loot.
Possible fixes (the user decides; they rejected *avoiding* such mobs before): stop swinging the moment the target's
sprite vanishes / plays its death animation; no Z sweep where the kill wasn't ours (no EXP); fewer "lost target"
(sprite flicker in crowds). Step-backs now vary (26 in 5 min, all different lengths).
**Built (the user said yes), live-tested `runs/pkg_others2m` (2 min, map 50), 534 tests:**
- `SpriteDetector.dying()`: the target's own death frames (`die1_*`), only in a small window where the target was
  (`Perceiver.target_mob` = its mob id). `obs.target_dying` ≥ `die_score` 0.72 (dying Shroom 0.74–0.91; 491 live
  targets max 0.673). Fixtures `tests/fixtures/{dying,live}_shroom.png`.
- Brain: death animation → stop swinging at once; EXP within ~0.4 s (`others_kill_wait_s`) → our kill, loot as
  before; none → "killed by someone else" (stat `others_kills`), no loot, drop zone marked, phase pause.
  Sprite mode: "target gone" without EXP and "no HP bar for us" (was "not a mob" → loot) → no Z sweep.
- Result: Z 84 → **39 presses/min**; kills 2.0 → **3.0/min**; 11 other players' kills recognized (all checked:
  EXP flat after each), 2 "target gone", 4 "no HP bar for us".

## Future tasks
- **Skills** (the user will start using them against Lie Detectors): configurable skill keys, used a randomized
  share of swings / on cooldown, buffs on a timer; ask the user for keys, cooldowns, MP cost.
- **Lie Detector check while unfocused** + **capture watchdog** (no new frame for ~2 s → re-create dxcam / stop
  with an alarm) - offered, not approved yet.
- **Retarget to the closest mob (the user, pkg_sight4):** once a far target is chosen, a mob that spawns much
  closer is ignored - the bot walks the long way to the first one. A player switches to the close one. Today a
  switch only happens for a mob in reach / in our path (`_fight` step 5, `switch_margin`); widen it: while walking
  to an unhit target, any fair mob clearly closer (e.g. < half the distance, margin + cooldown against
  flip-flop) becomes the target.
- **Rests (the user, 2026-11-01): every ~15 min (randomized, e.g. 11–19 min) stop and rest like a player**: walk
  to a ladder/rope or a ledge (`ladderRopes` / footholds from map.json), stand or hang there a random 1–4 min,
  maybe sit; then resume. Needs ladder/ledge navigation (jump & drop work) for the "go there" part; a first
  version can rest where it stands (no mobs in reach) and only move on to ladders once navigation exists.
- **Telegram alert to the user's phone when the Lie Detector shows up** (the user asked, 2026-11-01): a Telegram
  bot message (bot token + chat id from a local, untracked config/env var — never in code) sent from the runner
  alongside the siren, so the user can react when away from the PC. Same channel could later carry HP-stop alerts.

## Goal: jump & drop recognition (next big feature)
The bot only walks on the floor it stands on. Live it got stuck in a dip between two ledges for 57 s
(pkg_sprites2: snails up on the ledges, walls both sides) and could only reach lower ground by walking off a step.
**Goal: recognize when a jump or a drop is needed, and where, then do it like a player:**
- **Jump up** onto a step/ledge in the way or above a target (hold the direction + `shift`; Beginner jump height
  and length to be measured live).
- **Drop down** from a platform to a lower one (`down` + `shift` on a thin platform; walking off an edge works for
  steps — already done for targets on lower ground).
- **Recognize** that a mob or loot is on another level and pick the way to it; recognize "blocked = a step I can
  jump" versus "a wall"; never step back or loot-walk off a ledge by accident.
- Later: ladders/ropes (`up`/`down`), using `ladderRopes`.

Suggested plan (test-first, as before):
1. **Localization:** map our position into map coordinates. `map.json` has the minimap's `centerX/centerY` and
   `magnification`, and `vrBounds`; calibrate dot → map x/y on map 42 (on screen we measured ~15 px per minimap
   px; the minimap window is scaled — verify with a few known spots, e.g. walls at both ends).
2. **Footholds as a graph:** platforms = chains of footholds (`prev/next`, `groupId`); walls = vertical segments.
   From our map position: which platform we're on, where its edges are, what's above/below within jump reach.
3. **Measure the jump** live: height and horizontal distance at walking speed; drop timing. Record frames.
4. **Brain:** when blocked by a step within jump height → jump; target/loot on another platform → path (walk to
   the right edge/spot, jump or drop); ledge awareness for step-backs and loot walks.
5. Tests with map 42's real footholds (no game needed), then live runs.

## Open issues (by priority)
0. **Swing-out step-in fires while hits are landing** (minor, pkg_decisive1 40.19 s, montage
   `runs/pkg_decisive1/inspect/stall_39_41.png`): swinging from 69–72 px, damage numbers 17/19/22 showed the hits
   *landed*, but after 0.3 s the bot stepped in anyway; the swing then locked movement ~0.8 s while it held right.
   7 step-ins in that run, most after hits knocked the snail back to 70–76 (those are fine). Idea: a landed hit
   (bar fill dropped / damage number) = in reach → no step-in. Measured reach on sprite centres: up to ~72 px.
1. **Step-backs**: ~1 per kill; snails keep walking into us while we swing. Idea: measure the Beginner swing timing
   from frames (press → hit lands → can act again) and time the press so the hit lands at ~60 px.
2. **Loot**: items left when a fight interrupts looting or drops bounce beyond the sweep → loot by sight (later).
3. **Far targets lost on the way** ("lost target before reaching it"): re-search near the expected spot.
4. **Bridge** (map 42, dot x≈156) hides the tag: ignored by choice. Idea: keep walking while the dot moves.
5. HP drain in crowds of Blue Snails (expected per the user; potions should cover it).

## Gotchas when editing
- **`Screen.calibrate()` must run with the game in front** (it finds the pillarbox bars). Each run logs
  `game picture at x (439, 3001)` in fullscreen; **since 2026-11-02 the user plays windowed at full resolution
  (2560x1440 client) on the left of the 3440 monitor -> `(0, 2560)` is correct** (same 1440 height = same scale:
  sprites 0.8-0.97, minimap canvas 1:1). Anything else means a bad crop (pkg_sight6: 3034). Windowed: nothing may
  cover the game window (the capture reads that screen area). serve started from the
  console measured x 0–3440 instead of 439–3001 → whole desktop squeezed into the frame → HP 56 %/EXP 37 % misread,
  no tag, nothing found. Now calibrated on every F7 (serve) and after the focus wait (run).
- Windows default encoding is cp1252: always `encoding="utf-8"`.
- Multi-line edits: a small Python script (heredoc into the venv python) with `assert s.count(a) == 1` before
  each replace works well; long inline `-c` one-liners break on quoting.
- Editing a file and restoring it within the same second at the same size leaves a stale `__pycache__` .pyc
  (mtime compared to the second): delete `__pycache__` after such tricks.
- To prove a test catches a bug: temporarily revert the fix/value, run the test (must fail), restore.
- `tests/test_humanize.py` imports helpers with `from test_brain import ...` (no relative import).
- Parametrized fixtures (`brain`, `sbrain`) can't be fetched with `request.getfixturevalue`: write two tests sharing
  a helper.
- Don't put `tools/` first on sys.path. Run Python on downloaded/untrusted files with `-I`.
- Other bot repos reviewed for ideas only (none used); jackexyou/maplebot's `scripts/dev/admin_worker.ps1` is a
  privilege-escalation hole: never run it.

## Session 16 (2026-11-02) - false "no HP potions left" stop with 49 Meat
- `runs/manual/20261102_144214_2`: stopped at 397.9 s "HP 45% below 45% and no HP potions left"; the Del slot read
  filled all run. Meat raises the HP bar +3 % only **0.6-0.8 s** after the press; `potion_verify_s` was 0.7 -> the
  295.2 s press (bar rose at +0.8 s) counted as a miss; the 372.7 s press really did nothing (cause unknown, maybe
  swallowed) -> 2 misses -> "used up" -> stop 25 s later.
- Fixed: `potion_verify_s` 0.7 -> 1.2; `Brain._have` counts a press still being judged as "have"; HP under `hp_stop`
  while "used up" -> one last-chance probe press (`stop_probed`) before stopping. 3 regression tests.

## Session 16 - breaks (Lie Detector suspect: ours never paused; other bots go 'attack x3-4, rest 1-2 s, ... rest 5 s')
- `Brain._rest` (gate before the mode dispatch in `_step`) + `_count_kill_rest` (on each confirmed kill).
  Short rest after every 2-4 kills (redrawn): 0.9-2.2 s, 25 % of them 3.5-6 s. Long break 10-15 s every 48-80 s.
  Only when calm: SEEK, not hit in the last 1 s, no fair mob within hold_max (a chain kill keeps the rest pending).
  Keys up the whole time; potions + Lie Detector check still run; **any HP drop ends a break at once**.
  Log: "short rest X s after the kills" / "long break X s" / "break over" / "hit -> break over"; stats `rests`, `breaks`.
- Config `timing.rests*` / `break_*`; CLI `--no-rests`. Tests: conftest `rests_off` autouse (old scenarios), mark
  `@pytest.mark.rests` for the 5 new tests. **Not live-tested yet: check whether Lie Detectors get rarer.**

### Session 16 live test `runs/rest10m_b` (600 s, Rain-Forest 10001070, crowded with bots, breaks ON)
- (`runs/rest10m` invalid: started on the top shop platform in a crowd, own tag covered -> me=None from 26 s;
  dropped down by hand.) Analysis script: `runs/prec/analyze.py RUN`.
- **No Lie Detector** during the run or after (watch alive; its 2 LDs 17:55/17:59 were the user's serve hunts
  started before the rests code). One clean run is not proof - compare over hours.
- Breaks worked as designed: 17 short + 7 long, 82 s resting (14 %); 10 of 24 ended by a hit (all real 1-px HP
  drops, ~7 HP); long breaks averaged 7.5 s actual of 12.4 planned (mobs walk into us on a crowded floor).
- **50 kills = 5.0/min, but by location:** min 0-6 at dot x ~150 (right side, bot pack): 0-5 kills/min, 49 %
  of engagements 'lost target before reaching it' (median |dx| at loss 132 px, 1.8 s after engage); min 7-9 at dot
  x ~85-105: 10-11 kills/min, mobs on screen ~0.65/tick vs ~0.35. The spawn walk took 6 min to get us out.
- Out of MP almost all run (no MP potions): `c` held 91 s vs Power Strike 28 s -> less damage share vs bots.
- 238 engagements -> 50 kills (21 %); 60 closer-switches + 26 reach-switches; 48 blind swings; walking 44 % of time.

### Session 16 - user's verdict on the improvement list + built
- The user: (1) leave contested zones -> **no, part of the hunt revamp**; (2) MP potions -> **no, they're expensive,
  saving them**; (5) step away before long breaks -> **no**; (6) blind swings -> hunt refactor later.
- **Built (3) no far chases when contested:** `Brain._lost_one` on 'lost target before reaching it' / 'killed by
  someone else' / 'gone, no EXP'; `timing.crowd_losses` 3 within `crowd_window_s` 45 -> `contested`: `_pickable`
  refuses new targets farther than `zones.chase_max` 200 px (unless fighting us). Log "contested: only mobs within
  200 px" / "far mobs are fair game again". Replay of rest10m_b: contested ~95 % of that crowded run.
- **Built (4) fewer switches:** a closer mob takes over only if closer by max(`zones.closer_margin` 40 px,
  `closer_ratio` 0.25 x distance) (was 20 px); `closer_cooldown_s` 0.4 -> 0.8. Reach switches unchanged.
- 4 new tests; all green. **Not live-tested.**

### Session 16 - breaks REMOVED (the user: LD right after the test = fail)
- LD 18:31:43 in the user's serve hunt (with rests, 256 s in). All rest/break code, config, `--no-rests`, tests
  and the conftest fixture removed; tests green. (The contested/closer-switch changes stay.)
- `runs/prec/ld_hunts.py [DATE]`: every hunt on the wall clock vs every LD (watch log). 2026-11-02: ~1 LD per
  35 min hunted, gaps 2-74 min, 25-946 kills between LDs; no link to loot, Z rate, map or hunt length so far.
- Seen on the 18:31 LD screenshot: chat "You don't have enough MP to use this skill" at MP 10/359 - Power Strike
  pressed with too little MP (`basic_below_mp` 0.025 = 9 MP; lv 18 needs more). A visible bot tell; not fixed yet.

### Session 16 - HP/MP from the HUD numbers only (the user) + Power Strike MP fix
- The user: "look ONLY at the numbers above the bar" (HP [409/783], MP [10/359], EXP 2,179 [15.89%]).
  `hud.read_pair(frame, HP_TEXT|MP_TEXT)` reads the digits between the green brackets (6x7 cells, same font as the
  EXP points, `assets/exp_digits.npy` + new `assets/hud_slash.npy`; 5 px commas). Robust to JPEG frames: every
  pair of green pieces tried as brackets, start offsets +3..+6, stop at a green (']') cell. 3000 random recorded
  frames: 99 % read; every disagreement with the old bar fill checked was the bar being wrong (flashing MP bar).
  ~2.3 ms/frame. `hp_fill`/`mp_fill`/`HP_BOX`/`MP_BOX` removed. Observation: `hp_now/hp_max/mp_now/mp_max`;
  `hp = hp_raw = cur/max`. Unreadable -> last good reading; a new max only after 2 reads in a row.
- **Power Strike fix:** `_pick_attack` measures the skill's MP cost (median of the last 5 MP drops while the skill
  is held, `skill_cost_max` 60) -> plain attack when MP < cost, skill again at MP >= cost. Cost unknown: skill
  held `skill_stall_s` 1.5 s under 15 % MP with MP not dropping -> plain attack, skill again from that MP + 1.
  No exact MP -> old share thresholds. Log "space costs N MP (measured)". **Not live-tested.**
