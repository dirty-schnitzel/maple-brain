# PLAN-moving-scenery: perception that ignores moving backgrounds, cheaply

**Status: PROPOSED - goal and starting facts only.** The steps, gates and stop rules are written by the planner
session at the bottom (Fable, max), after it has measured and prototyped. Nothing is built in `maplebrain/` until
the user's OK.

## The goal (the user, 2026-11-21)
"Effectively ignore moving backgrounds as efficiently as possible." In game terms: on a map whose background
moves (drifting clouds, light rays, animated objects, portals), perception must still find the camera, see the
mobs and not invent ghosts - the moving parts are treated as "we don't know what is here" instead of "something
unexpected is here" - and it must cost as little tick time as possible (today the Perceiver is 13-17 ms a frame
at the median against 16.7 ms for 60 a second; the p90 is over 16.7 ms on 10 of 23 captures).

Done means: the Victoria Road forest maps of the bank become **sound** by PLAN-data's stop rules (as read and
OK'd on 2026-11-21: "explained" = map places the scene model misses on more than half of the frames that show
them; camera counted from the first fix to the exit fade), and the maps refused today for moving backs (95 of
206, Perion first) get a scene camera - without the sound maps getting worse or slower.

## Why now, and its place beside the tracker
- The tracker plan (`docs/prompts/tracker-plan.md`) is designed on the 13 sound captures (caves, dungeons, Line 1
  of the subway). This plan is perception, one layer under the tracker: it changes the quality of each frame's
  facts on the forest maps, not how the tracker links them. The two run side by side; the tracker plan only has
  to give "the scene model does not know this place" its own value in the frame's facts (beside "explained" and
  "unexplained").
- When this plan is done, the kept replay is re-run on the forest captures (~13 % of the replay) and the tracker
  is scored on them too.

## What is known (2026-11-21)
1. **Two kinds of map.**
   - *Flagged:* backgrounds whose type moves (types 4-7 = clouds; `scene.py` `MOVING`) or animated backs (`ani`)
     -> `Scene.clean_meta` is False -> no scene camera, the hunt refuses to start. 95 of 206 maps. Perion's
     clouds: type 4 backs, `rx` 5..35 = a drift speed, not a parallax; 43-50 % of the play area left over there
     (PLAN-perception.md, "Deferred by the user (2026-11-16)").
   - *"Clean" but not sound:* every Victoria Road forest map recorded (7 maps, 9 captures, 26,096 frames) has all
     backs "known", the camera on 100 % of frames, yet only 80-93 % explained
     (REPORT-track-before.md section 3). What was seen: a band of moving clouds in the sky (Rain-Forest East of
     Henesys, L Forest I), the diagonal light rays (The Field South of Ellinia: 20-22 % of the play area off),
     an animated portal. Not where mobs walk. Which layer or object draws each is not known yet.
2. **What the scene model does with unknowns today** (`maplebrain/scene.py`): animated map objects -> `anim.png`,
   their pixels "unknown"; unknown back layers are kept one by one (only their mask). The fit falls back to the
   contrast-only score in unknown pixels (PLAN-perception.md, Risks).
3. **The client files describe every background** (`Map.wz` back entries: type, rx/ry, cx/cy, alpha, ani, front)
   and HeavenClient has the drawing code (v83 is the rulebook, the user 2026-11-20): a moving back's position is
   a function of time, so it may be predictable rather than only maskable.
4. Footage: the 9 forest captures and their kept replay (`F:\dev\maple-corpus\work\SESSION#K\track\`, the two
   bitmaps per frame); Perion has older captures only (check `tools\data\corpus.py list`).

## Questions for the planner (to answer by measurement first)
- Per map: which back layer / object / portal draws each unexplained band? Is it in the client files' flags
  (and our build misreads it), or invisible to them?
- Cheapest handling per kind: mask it once per map (a static "unknown" region), mask it per frame from the layer's
  predicted position, or predict and draw it (exact, so the scene still shows through behind mobs)? What does
  each cost in ms and in mobs missed / ghosts on the forest captures?
- Does the camera still lock when a large share of the screen is unknown (Perion's 43-50 %)?
- Footage needed that the bank does not have (Perion at the 2026-11-21 graphics settings?) - ask the user.

## Session prompt: the planner
- **Run as:** Fable, max effort, a fresh session. Type: `run PLAN-moving-scenery.md` (the block below).
- **When:** any time; it does not wait on the tracker plan. Its prototypes use the GPU: not while the user records,
  and not during a speed measurement of another session.

```text
Moving-scenery plan session. Read HANDOFF.md's START HERE, this file (PLAN-moving-scenery.md), REPORT-track-before.md
section 3 and "What surprised me" 3, PLAN-perception.md (step 1, the Perion deferral, Risks), maplebrain/scene.py,
docs/game_rules.md section J (the camera) and HeavenClient's background drawing in C:\Users\Yoav\dev\v83-ref\
(reading only). Goal: perception that ignores moving backgrounds as cheaply as possible - the forest maps sound,
the maps with moving backs get a scene camera, the sound maps no worse and no slower. Measure first: per forest
map, which layer / object draws each unexplained band; then prototype the cheapest handling per kind on the kept
replay and the bank's captures (dev group only), with ms per frame and mobs missed / ghosts. Then fill this file:
steps with gates on footage, stop rules, ready-to-paste Opus prompts; status stays PROPOSED until my OK. Build
nothing in maplebrain/. Ask me game-knowledge questions directly.
```
