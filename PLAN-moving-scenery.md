# PLAN-moving-scenery: perception on maps whose scenery moves

**Status: PROPOSED - goal, starting facts and the planner's prompt only.** The design, steps, gates and stop
rules are written by the planner session at the bottom (Fable, max) after it has measured and prototyped.
Nothing is built in `maplebrain/` until the user's OK. Priority: **P0** (HANDOFF, the order), before the tracker
plan session.

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
waiting on the user's OK); the maps refused today for moving backs (95 of 206, Perion among them) get a scene
camera and mobs found / ghosts at the level of the sound maps, or a measured reason why not; the 13 sound
captures no worse and no slower.

## Ideas from the 2026-11-21 conversation - OPTIONAL
The user's wish (2026-11-21): the planner takes a **fresh look** and designs its own solution. What follows is
what came up in the conversation that set this plan; it is input, not a decision - use it, change it or drop
it on the measurements.
- The line between the two problems may be the draw order, and the client files may hold it (a back entry's
  `front` flag) - to be checked against footage.
- For a moving layer, two ways of "ignoring" it: *predict* it (its place at a given time from the client files
  + HeavenClient's drawing, drawn into the expected picture, so a mob in front of it is seen as anywhere) or
  *mask* it as unknown (cheaper, but a mob in front of a masked place loses the "the map shows through around
  it" check; the fit falls back to the contrast-only score there).
- Perion, the user's idea: after the map is subtracted, a see-through cloud is a pale patch with the mob's
  outline under it - run a fallback detector, more sensitive, only on those fuzzy / covered areas, at the price
  of possibly more false positives.
- Perion, Claude's variant: the cloud is a known picture with a known alpha moving at a known speed; once its
  place on the frame is found (the drift phase is not known: fitted per layer, like the camera) it can be
  undone, behind = (frame - cloud x alpha) / (1 - alpha), each pixel's detection threshold set by how thick the
  cloud is there, near-opaque parts = "covered by cloud". The user's fallback for when it cannot be placed.

## Its place beside the tracker
- Perception, one layer under the tracker: it changes each frame's facts on these maps, not how the tracker
  links them. The tracker plan (`docs/prompts/tracker-plan.md`) is designed on the 13 sound captures and should
  give "the scene model does not know this place" and "covered by what" their own values in the frame's facts.
- When this plan is built, the kept replay is re-run on the forest captures (~13 % of the replay) and the
  tracker is scored on them too.

## What is known (2026-11-21)
1. **Two kinds of map in the code.**
   - *Flagged:* backgrounds whose type moves (types 4-7; `scene.py` `MOVING`) or animated backs (`ani`) ->
     `Scene.clean_meta` is False -> no scene camera, the hunt refuses to start. 95 of 206 maps. Perion: type 4
     backs, `rx` 5..35 = a drift speed, not a parallax; 43-50 % of the play area left over
     (PLAN-perception.md, "Deferred by the user (2026-11-16)"). How many of the 95 have a moving layer in front
     of the mobs is not known.
   - *"Clean" but not sound:* every Victoria Road forest map recorded (7 maps, 9 captures, 26,096 frames) has all
     backs "known" and the camera on 100 % of frames, yet only 80-93 % explained (REPORT-track-before.md section
     3). Seen: a band of moving clouds in the sky (Rain-Forest East of Henesys, L Forest I), the diagonal light
     rays (The Field South of Ellinia: 20-22 % of the play area off; mobs are drawn over them), an animated
     portal. Which layer or object draws each is not known.
2. **What the scene model does with unknowns today** (`maplebrain/scene.py`): animated map objects -> `anim.png`,
   their pixels "unknown"; unknown back layers are kept one by one (only their mask). The fit falls back to the
   contrast-only score in unknown pixels (PLAN-perception.md, Risks).
3. **The client files describe every background** (`Map.wz` back entries: type, rx/ry, cx/cy, alpha, ani, front)
   and HeavenClient has the drawing code (v83 is the rulebook, the user 2026-11-20).
4. Footage: the 9 forest captures and their kept replay (`F:\dev\maple-corpus\work\SESSION#K\track\`); Perion
   and other flagged maps: check `tools\data\corpus.py list`; footage the bank lacks (Perion at the 2026-11-21
   graphics settings?) - ask the user, who records it.

## Session prompt: the planner
- **Run as:** Fable, max effort, a fresh session. Type: `run PLAN-moving-scenery.md` (the block below).
- **When:** P0, now. Its prototypes use the GPU: not while the user records, and not during a speed measurement
  of another session.

```text
Moving-scenery plan session. Read HANDOFF.md's START HERE, this file (PLAN-moving-scenery.md), REPORT-track-before.md
section 3 and "What surprised me" 3, PLAN-perception.md (step 1, the Perion deferral, Risks), maplebrain/scene.py
and the fit's use of unknown pixels, docs/game_rules.md section J (the camera) and HeavenClient's background
drawing in C:\Users\Yoav\dev\v83-ref\ (reading only). Design a solution for both problems in this file: moving
backgrounds behind the mobs, and Perion's clouds in front of them. The ideas section is optional - take a fresh
look and design your own. Measure first: per map, which layer / object draws what perception cannot explain, and
behind or in front of the mobs; then prototype on the kept replay and the bank's captures (dev group only), with
ms per frame, mobs found / missed and ghosts. Then fill this file: the design, steps with gates on footage, stop
rules, ready-to-paste Opus prompts; status stays PROPOSED until my OK. Build nothing in maplebrain/. Ask me
game-knowledge questions directly, and for footage the bank lacks.
```
