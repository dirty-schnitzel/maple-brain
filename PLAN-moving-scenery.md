# PLAN-moving-scenery: moving backgrounds filtered out of perception

**Status: PROPOSED - goal and starting facts only.** The steps, gates and stop rules are written by the planner
session at the bottom (Fable, max), after it has measured and prototyped. Nothing is built in `maplebrain/` until
the user's OK.

## Scope (the user, 2026-11-21)
Two different problems; this plan is only the first:
1. **Moving backgrounds - drawn BEHIND the mobs** (drifting sky clouds, light rays, animated objects, portals).
   They never cover a mob, so once perception knows them they simply stop bothering it. **This plan.**
2. **Perion's clouds - drawn IN FRONT of the mobs** (they obstruct them). Not this plan: priority 2, after the
   tracker. The user's first idea for it: more sensitive mob detection on those maps, at the price of possibly
   more false positives.

The line between the two is the draw order: behind the mobs or in front of them. The client files probably say
which (a back entry's `front` flag); step 1 checks that against footage. A moving layer in front of the mobs on
any map belongs to problem 2.

## The goal
**Filter moving backgrounds out of perception, on every frame, as cheaply as possible.** Picture the difference
between the frame and the expected map picture: black wherever the map is, bright only where something that is
not the map is drawn - mobs, our character, other players, drops, skill effects, damage numbers, the UI. A
moving background must add nothing bright to that picture:
- best: the layer is predicted (the client files + HeavenClient's drawing say where a moving back is at a given
  time) and drawn into the expected picture -> black, and a mob in front of it is seen against it as anywhere;
- otherwise: its pixels are marked **unknown** (neither map nor not-map), and the planner measures what that
  costs in mobs missed and ghosts there.
A plan step does not count as done because the bright pixels are gone when mobs are lost with them.

Done means:
- the Victoria Road forest maps of the bank become **sound** by PLAN-data's stop rules (camera counted from the
  first fix to the exit fade, OK'd 2026-11-21; "explained" as REPORT-track-before.md section 3 reads it -
  waiting on the user's OK);
- the maps refused today for moving backs that have no moving layer in front of the mobs get a scene camera;
- on the forest maps, ghosts and mobs found are at the level of the sound maps (caves, dungeons, Line 1);
- the 13 sound captures are no worse and no slower (today the Perceiver is 13-17 ms a frame at the median
  against 16.7 ms for 60 a second; the p90 is over 16.7 ms on 10 of 23 captures).

## Its place beside the tracker
- Perception, one layer under the tracker: it changes each frame's facts on the forest maps, not how the tracker
  links them. It runs side by side with the tracker plan (`docs/prompts/tracker-plan.md`), which is designed on
  the 13 sound captures and gives "the scene model does not know this place" its own value in the frame's facts.
- When this plan is done, the kept replay is re-run on the forest captures (~13 % of the replay) and the tracker
  is scored on them too.

## What is known (2026-11-21)
1. **Two kinds of map in the code.**
   - *Flagged:* backgrounds whose type moves (types 4-7; `scene.py` `MOVING`) or animated backs (`ani`) ->
     `Scene.clean_meta` is False -> no scene camera, the hunt refuses to start. 95 of 206 maps, Perion among
     them (type 4 backs, `rx` 5..35 = a drift speed, not a parallax; 43-50 % of the play area left over there:
     PLAN-perception.md, "Deferred by the user (2026-11-16)"). How many of the 95 have a moving layer in front of
     the mobs is not known.
   - *"Clean" but not sound:* every Victoria Road forest map recorded (7 maps, 9 captures, 26,096 frames) has all
     backs "known" and the camera on 100 % of frames, yet only 80-93 % explained (REPORT-track-before.md section
     3). Seen: a band of moving clouds in the sky (Rain-Forest East of Henesys, L Forest I), the diagonal light
     rays (The Field South of Ellinia: 20-22 % of the play area off; mobs are drawn over them), an animated
     portal. Not where mobs walk. Which layer or object draws each is not known yet.
2. **What the scene model does with unknowns today** (`maplebrain/scene.py`): animated map objects -> `anim.png`,
   their pixels "unknown"; unknown back layers are kept one by one (only their mask). The fit falls back to the
   contrast-only score in unknown pixels (PLAN-perception.md, Risks).
3. **The client files describe every background** (`Map.wz` back entries: type, rx/ry, cx/cy, alpha, ani, front)
   and HeavenClient has the drawing code (v83 is the rulebook, the user 2026-11-20).
4. Footage: the 9 forest captures and their kept replay (`F:\dev\maple-corpus\work\SESSION#K\track\`, the two
   bitmaps per frame); `tools\data\corpus.py list` for the rest.

## Questions for the planner (to answer by measurement first)
- Per forest map: which back layer / object / portal draws each unexplained band? Is it in the client files'
  flags (and our build misreads it), or invisible to them?
- Does the `front` flag (or another field) separate "behind the mobs" from "in front" on every map of the bank?
  Which of the 95 flagged maps are background-only?
- Cheapest handling per kind - predict and draw, mask per frame from the predicted place, or a fixed mask per
  map: its ms per frame, mobs missed and ghosts on the forest captures.
- Footage the bank does not have (a flagged background-only map at the 2026-11-21 graphics settings?) - ask the
  user.

## Session prompt: the planner
- **Run as:** Fable, max effort, a fresh session. Type: `run PLAN-moving-scenery.md` (the block below).
- **When:** any time; it does not wait on the tracker plan. Its prototypes use the GPU: not while the user records,
  and not during a speed measurement of another session.

```text
Moving-backgrounds plan session. Read HANDOFF.md's START HERE, this file (PLAN-moving-scenery.md: its scope is
the moving backgrounds drawn BEHIND the mobs; Perion's clouds in front of them are out), REPORT-track-before.md
section 3 and "What surprised me" 3, PLAN-perception.md (step 1, the Perion deferral, Risks), maplebrain/scene.py,
docs/game_rules.md section J (the camera) and HeavenClient's background drawing in C:\Users\Yoav\dev\v83-ref\
(reading only). Goal: on every frame, the difference between the frame and the expected map picture shows only
what is not the map - a moving background adds nothing to it, predicted where possible, marked unknown where
not - as cheaply as possible: the forest maps sound, the background-only flagged maps get a scene camera, the
sound maps no worse and no slower. Measure first: per forest map, which layer / object draws each unexplained
band, and whether the client files tell behind from in front; then prototype the cheapest handling per kind on
the kept replay and the bank's captures (dev group only), with ms per frame and mobs missed / ghosts. Then fill
this file: steps with gates on footage, stop rules, ready-to-paste Opus prompts; status stays PROPOSED until my
OK. Build nothing in maplebrain/. Ask me game-knowledge questions directly.
```
