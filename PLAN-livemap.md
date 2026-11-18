# PLAN: livemap v2 - the map as a picture, the data model drawn on it
**Status: PROPOSED 2026-11-17 (by Fable, xhigh; the user's idea the same day). Not started; needs the user's OK.**
Executors: Opus, ONE session for the feature (Session 1) + an optional small one for extras (Session 2); prompts at
the end. Reference implementation, already working: `tools/livemap/proto.py` (+ `player.png` / `player.json`).
**Scope rule (the user): keep it simple - a small fun feature to watch our live data model. Not a pillar, no tuning,
no new perception, nothing the bot depends on. When in doubt, leave it out.**

## 1. What it is
Today `python -m maplebrain livemap` draws the hunt as ASCII in a console. v2 draws the same data as a picture:
the whole map rebuilt from the client's assets (the scene model perception already uses), every tracked mob as its
real sprite at its map position, us as one fixed sprite, the game's screen as a rectangle - and a second view, "the
bot's screen", 1:1 at the camera: it looks like the game, drawn only from what the bot believes.
Same inputs as v1: `ticks.jsonl` as the bot writes it (`obs.mobs`, `obs.cam`, `obs.me_map`; line-buffered, so it can
be followed live) + the run's `log.txt` for the map id. A separate process; the bot never imports it.

## 2. What was measured for this plan (2026-11-17, `tools/livemap/proto.py`, CPU only, no bot running)
1. **The whole map in one call.** `Scene.load(map, device="cpu").expected((x0, y0), meta w, meta h, pre=False)` =
   tiles + objects over the backgrounds as ONE map-sized camera sees them. 7 maps: 0.3-4.7 s each, 2400x2630 ..
   4470x1757 px. Looked at 3: Ant Tunnel IV and Line 1 (clean) look like the game; Perion Street Corner (unclean)
   too, its moving clouds simply missing. No new render code.
2. **Mobs are the sprite files at the tracks' feet.** `assets/mcw/mobs/<id>/<anim>_<n>.png` at the frame's origin,
   mirrored for "right". Whole-map view and the 1:1 view both checked against recorded frames (Ant Tunnel IV n=900 /
   n=2001, Line 1 n=600): mobs stand on their platforms, we stand where the game shows us.
3. **Drawing is free.** 6889 rows of `runs/play/20261116_193954_1`: draw p50 0.7 ms (whole map) / 1.1 (1:1), JPEG
   2.0 ms, max 18 (a first sprite load). numpy + cv2 only: no torch, no GPU at draw time.
4. **No window is possible, and none is wanted.** This venv's cv2 is headless (`cv2.namedWindow`: "not
   implemented"). So the picture is served as a page: stdlib `http.server`, MJPEG (multipart JPEG in an `<img>`).
   Measured through HTTP: 12.8 pictures / s in both views, the view switched by a link. Nothing of ours ever opens
   a window, so nothing can take the keyboard focus from the game (memory no-background-input).
5. **Our character = one cut from a recorded frame**: frame minus the expected scene, the biggest blob in our body
   box (`proto.py cuts` -> a sheet, picked by eye: Transfer Area n=1107, standing, no pet, facing left, 79x67,
   feet at (40, 65)). Kept as `tools/livemap/player.png` + `.json`. The client export has no character pictures
   (only `Character/00002000.img.xml`): composing one from the client is a project of its own - not done.
6. **Data wrinkles found (handled in the prototype):** frame `delay` in mob.json is an int, a string ("200": 45
   frames) or None (67); 221 of 2154 frames are 1x1 placeholders that follow `_inlink` (as `vote._pic` does; 1
   frame has no picture at all); replay rows keep the fields at the top level, ticks.jsonl under `obs` / `facts`.
7. **Other characters are the weak part.** `facts.tags` (name-tag boxes) also holds mob tags, pets' tags, merged
   neighbours and the "You received EXP" lines (frame n=900 of 154819_1: 2 real players, 4 phantoms). Drawn raw,
   ghosts appear at the EXP text. So: not in Session 1; Session 2 tries three rules and decides by eye.

## 3. Design (all of it is in the prototype)
- **Base picture, once per map**: finding 1 on the CPU (`torch.set_num_threads(2)` for that call), cached as
  `assets/scene/<map>/whole.png` (that folder is not in git; rebuilt when `scene.png` is newer). A cached map
  starts without importing torch. No scene for the map -> footholds and ropes as lines on a dark picture
  (`lines_picture`, map.json only).
- **Two views of the same record**, switched by a link on the page:
  - *whole map*: the base cropped to vrBounds + 60 px, scaled once to fit 1500x900; sprites drawn 1.8x the map's
    scale (never over 1:1) so a mob is readable at scale ~0.3; the screen as a white rectangle; a yellow marker
    over us.
  - *the bot's screen*: a 1366x700 crop of the base at `obs.cam`, everything 1:1.
- **Mobs** = `obs.mobs` (the tracker's tracks: the data model, coasting ones included): sprite by `mob` / `anim` /
  `facing` at (`x`, `y`); the animation frame from the VIEWER's clock and the client's frame delays (a track has
  no frame number); `unseen` > 0.3 s -> 45 % opacity + "?"; dying -> 70 %; tentative tracks and pets skipped.
  Drawn over everything (no layer occlusion: we want to see them).
- **Us** = the fixed sprite at `obs.me_map` (else `map_pos`), facing = the sign of our last move of >= 2 px.
- **The page**: `/` (the picture + two links), `/stream` (MJPEG), `/view/map`, `/view/cam`. 127.0.0.1 by default;
  `--host 0.0.0.0` lets another device on the LAN watch (no password: the user's choice). ~15 pictures / s; nothing
  is drawn or encoded while no browser is connected.
- **CLI** (the old command, picture by default):
  `livemap [DIR]` follow the newest hunt | `livemap RUN --replay [--speed --t0]` | `--port 8765 --host --fps 15
  --view map|cam --map ID` | `--ascii` = today's console map, unchanged (`--every`, `--width` apply to it).

## 4. Not in scope (say no, or ask)
Exact parallax in the 1:1 view (tiles / objects are pixel-exact there; background layers sit where the map-sized
camera puts them) | animated objects, moving clouds, NPCs, drops, effects, damage numbers | layer occlusion | a
character composed from the client's files, other players' real looks | a GUI window, installing a GUI cv2 | any
change to the bot, the recorder or FrameFacts | speed work (it is 3 ms a picture).

## 5. Steps
**Session 1 - the feature**
- S1 `maplebrain/mapview.py` (new): from the prototype as is - `base_picture` (+ the `whole.png` cache),
  `lines_picture`, `Sprites` (`picture` follows `_inlink` + the mob's `link`; reuse `vote._pic` only if importing
  it does not import torch), `prep`, `blit`, `norm`, `View` (`draw`, both views). A frame with no picture -> frame
  0 of its animation. No torch import at module level.
- S2 `maplebrain/livemap.py`: v1's `follow` / `replay` loops stay the single source of rows (newest hunt, map from
  the log, a new hunt or map -> a new `View`); what they do with a row becomes a choice: `--ascii` -> today's
  `View.frame` + `_draw` (rename, don't rewrite), default -> `mapview.View.draw` -> `serve_page` (from the
  prototype; port 0 must work for the test). Live: read all new lines, draw only the last complete one. No tracks
  in the run -> the map + us + one line of text on the picture (v1's "start the bot with --gpu").
  `__main__.py`: the flags of section 3.
- S3 assets + tools: `git mv tools/livemap/player.* assets/livemap/`; the prototype's `cut` / `cuts` become
  `tools/livemap/cut_player.py` (how to redo the sprite: 2 lines in its docstring); delete `proto.py` LAST, after
  the gate pictures are compared.
- S4 `tests/test_mapview.py` (no GPU, no scene assets: a tmp scene root -> `lines_picture`): `prep` / `blit`
  (mirrored origin, clipping at every edge, opaque pixel exact, alpha 0 untouched, opacity); `frame_at` on Bubbling
  (mob 14: string delays) cycles through every frame; every frame of mobs 19 / 21 / 14 resolves to a picture; 1:1
  view: a track at a known map point -> its sprite's opaque pixels exactly there, an unseen one differs; whole-map
  view: size <= fit, the screen rectangle at the scaled corner; `norm` on one ticks.jsonl record and one replay row
  (inline dicts); the page on port 0: `/` names `/stream`, the first MJPEG part decodes to the picture's shape,
  `/view/cam` switches; in a subprocess: importing `maplebrain.runtime.runner` does not import `maplebrain.mapview`,
  and drawing from a cached base does not import torch.
- S5 docs: README's livemap lines (commands; the console map = `--ascii`), HANDOFF code map + one "livemap v2"
  line, this plan's status. `tools/readme/make_images.py` builds `livemap.txt` from the ASCII path: still works.
- **Gate (all of it, numbers into HANDOFF):** pytest green + the 'bot speed' line (must be unchanged: nothing on
  the bot's path changed) | on `runs/play/20261116_193954_1`: draw + JPEG <= 5 ms p90 a picture, >= 10 pictures / s
  through HTTP in both views (a script, as the prototype was tested), second start of the map (cached base) <= 1 s
  to the first picture | pictures BY EYE, the product next to the prototype's (`proto.py shot`, then yours, Read
  both PNGs): 193954_1 n=2001 both views, Line 1 replay n=600 whole map, 154819_1 n=900 1:1 over its recorded frame
  - mobs on their platforms, us where the frame shows us, the screen rectangle around us | `livemap RUN --replay
  --ascii` prints what v1 printed (tests/test_mapascii.py green).
- **Then the user's look** (not the session's gate): `serve runs\play --observe --gpu --tracker` + `livemap
  runs\play` in a second console, the page on the second monitor.
- **Stop rules:** a gate number missed by more than noise, or the pictures differ from the prototype's -> stop and
  report, no redesign. Pre-approved fallback if MJPEG does not show in the user's browser: the page polls
  `/frame.jpg` from a 5-line script instead. Anything else beyond section 3 -> ask.

**Session 2 - extras (optional; each stands alone, the user picks; skip all of it without loss)**
- E1 other characters as grey ghosts (the fixed sprite, 60 %): `facts.tags` minus ours, minus tags within 30 px
  of a track's feet (mob tags), minus tags inside `hud.UI_RECTS` or right of x 1140 below y 540 (the EXP lines),
  stacked tags (name + guild) merged. Gate by eye on 154819_1 n=900 / 1500 / 2400 (frames + facts): one ghost per
  visible player, no ghost on text. Phantoms left -> ship it OFF by default (`--players`) and say which.
- E2 a status line on the picture (v1's header: run, t, mode, HP / MP, mob count), a ring on the brain's target,
  Platform mode's marked platforms as lines (v1's `marked_segs`).
- E3 on-screen mobs in the exact pose perception saw: a `facts.fit` row within 20 px of the track -> its `pose`
  / `tint` instead of the clock.
- E4 README: one picture of each view (`docs/img/`, built by make_images.py from a recorded run).

## 6. Risks and notes
- torch on the CPU for a few seconds per NEW map in a second process (not per start: cached). If a live run shows
  a tick bump at that moment, build the cache beforehand: `livemap --map ID` once, or at `assets scene`.
- New files under `maplebrain/` and `assets/` change the replay gate's fingerprint (tools/perc/replay/gate.py): the
  next perception gate run replays its base once. Nothing to judge.
- The page shows the data model, mistakes included (the old tracker's wrong mob type at 154819_1 n=900 is plainly
  visible next to the frame). That is the feature.
- Unclean maps (95): the picture lacks their moving / animated parts; still readable.
- `player.png` is the user's character without its name tag; redo it after a gear change with `cut_player.py`.

## 7. Prompts
**Session 1 (Opus, high):**
```
Build livemap v2 on a NEW branch `livemap` (from the current head of `perception`; never main). Precondition:
`git status` is clean - if another session's uncommitted work is in the tree, stop and tell me (one working tree
cannot hold two branches). Read HANDOFF.md's START HERE + Code map, then PLAN-livemap.md (the user OK'd it):
execute its "Session 1" (S1-S5) exactly.
tools/livemap/proto.py is the working reference - productionize it, do not redesign it. The scope rule at the top of
the plan is the user's: keep it simple; anything beyond the plan's section 3 -> ask first.
Gate as written there (pytest + the 'bot speed' line unchanged; draw + JPEG <= 5 ms p90; >= 10 pictures / s over HTTP
in both views; cached start <= 1 s; the four pictures by eye next to the prototype's; --ascii unchanged). If a gate
fails, stop and tell me with numbers.
Rules: Python = .venv/Scripts/python.exe (maple-work's own, since 2026-11-18); no GPU and no torch at draw time; the viewer never opens a
window and the bot never imports it; no live run, no keys sent; if `watch` is running never stop it; no sed on files
(CRLF: Edit or byte-safe Python); scripts via the Write tool, not shell heredocs; commit + push on the branch, no
Claude attribution.
```
**Session 2 (Opus, high), only if the user wants extras:** the same header with "Session 2: only the items I name
(E1-E4), each with its own by-eye check; report and stop after each".
