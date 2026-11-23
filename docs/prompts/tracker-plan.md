# Session prompt: the tracker plan session

- **Run as:** Fable, max effort, a fresh session. Type: `run docs/prompts/tracker-plan.md`.
- **When:** after PLAN-moving-scenery.md is finished and merged into `dev` (the user, 2026-11-23: one assets
  version under the tracker work), and the user's OK on this draft. Start it from `dev`.
- **Result:** `docs/state_model.md` (the data model, the user's OK), then `PLAN-tracker.md`, PROPOSED until the
  user's OK.
- **Written:** 2026-11-21 in the planning session. **Rewritten 2026-11-21 as a DRAFT** after the data-model
  discussion (no guessing, the data model first, no simulator engine): under discussion, not OK'd. Updated
  2026-11-23 with the user's answers: memory in, what "no guessing" means, the goal, what the user looks at,
  the dynamic values.

```text
Tracker plan session. Read HANDOFF.md's START HERE, then REPORT-track-before.md, PLAN-perception.md step 4,
PLAN-loot.md (drops are part of this rework), REWORKS.md's recipe, tools/perc/track/, maplebrain/nav/navmap.py
and maplebrain/perception/world.py. docs/game_rules.md only where a rule is needed.

The goal: a very fast, very accurate tracker that carries everything perception sees into the model without
lowering the frame rate if possible, or lowering it as little as possible - efficient. Its cost per frame is a
gate number beside its accuracy (pytest's "bot speed" line, tools/perf/bench.py).

The rule: the tracker's inputs are perception + static or calculated data (the map, the client files, navmap).
It may predict where a thing is from what it saw and what covers it (a mob that walked behind a cloud is
still behind it). It never predicts behaviour by assuming the server's rules (respawn, aggro, mob AI).

The tracker needs memory, and designing it is part of this session: what is kept of a thing that is covered or
out of view, for how long, and how a thing that ends unseen is handled - a mob that dies under cover (behind a
cloud, a tree, another mob), a drop that vanishes out of view (picked up or expired). A short cover is a few
seconds, up for debate (today lose_s 0.5 s / covered_s 2.0 s, and today's tracker holds an identity across a
0.6-1.5 s gap only 31 % of the time). A starting point to weigh, not decided: an identity kept through a short
cover, each thing's history (age, hits taken, how it was seen), and for anything that left the view a "last
seen: where, when, how it left (scrolled off / covered / vanished in view)" record. My drops rule (HANDOFF.md,
"Drops in the tracker": a drop kept up to 130 s) is an input to this design.

Part 1 - the data model, before any tracker design. Write docs/state_model.md and stop for my OK:
- the map as a graph, fixed per map: navmap's platforms and ropes (nodes) and links (edges);
- navmap is the model's base and was written early, in one unoptimised session: audit it first. For each of
  its parts - nodes, placement (platform_at / below / surfaces), edges, routes - decide keep / change / rebuild,
  with numbers. The tracker's redesign covers nodes and placement; of the edges and routes only what the
  tracker needs (walk links = same floor; rebuilding the edges when a dynamic value changes) - the rest waits
  for the brain rework (REWORKS.md: Knowledge -> Execution -> Brain). Findings to start from (2026-11-23,
  timed with another job running): (1) a node is a foothold chain, not a floor - one floor can be several
  chains joined by walk links; (2) the footholds' forbidFallDown (17,271 of 82,632) and cantThrough (150) are
  not read and a drop has no distance limit, so drop edges can be wrong (docs/game_rules.md A6, question 3);
  (3) platform_at scans every platform: ~18 us a call on a median map, ~121 us on the largest (311 platforms)
  - ~20 things a frame = up to ~2.5 ms a frame there; (4) building the edges takes 0.1 s on a median map,
  4.5 s on the largest - fine at load, not for a rebuild mid-run; (5) the edges are our character's moves
  only: mobs follow other rules (turn at edges, never walk off), flyers have no node, portals are no edges;
- per frame, everything on screen - mobs, drops, other players, us: what it is, where on the graph, which
  thing of the previous frames it is, how it is seen (clear, or covered by what); and which part of the map is
  in view (the camera's rectangle), so "out of view" and "gone" are told apart;
- where on the graph: the node + the place along it (a platform + x; a rope + height), with the raw map (x, y)
  kept beside it as the measurement the placement is read from. Every kind of thing placed by one rule, from
  its feet, with a type - standing on a platform, in the air (over which platform, and which one it left; not
  "on link k", which is known only once it lands), on a rope, flying - and how sure the placement is (its
  distance to the surface). Other players get feet too (from their name tags). Today each kind is placed by
  its own code and tolerance (selfstate.py, world.py, drops.py; players not at all);
- derived facts, defined once and computed from the state, not stored: same floor (platforms joined by walk
  links are one floor - comparing platform ids is wrong at the joins), distance along the floor, in reach;
- the events since the last frame: spawned, hit, died by our last hit or not, dropped, picked up, we got hurt;
- the attributes and facts of the world state, not only positions: for us the move speed, the jump speed and
  height, the current weapon and its range (the reach boxes per stance, brain/reach.py), the attack speed and
  swing length, the skills on which keys, HP / MP, level / EXP, buffs; for each mob kind its speed, jump, HP,
  level, size, touch damage; for the map its physics (gravity, drag, slopes) - and any other attribute or fact
  about the world state. Today such values are scattered over config.py (Nav.jump_vx, jump_height, ...), the
  client files and the code, hardcoded; the model holds them in one place, each with its source (client file,
  HUD, fitted from footage);
- the dynamic values: many of these are not static. The skills and their keys, our move speed, jump, weapon
  reach, attack speed can change any time (a new skill or key layout, a new weapon, a buff, equipment, a
  level-up). List every value that can change, and decide the best way to handle each: how it is set or
  updated while running (read from the screen, read from the game files, set by me, measured live) and how a
  change reaches every reader, with no restart and no code edit;
- every field with its exact meaning, its unit, and how its accuracy is measured on footage.
Its readers: an AI that learns from recordings of my play (the state + my keys), an FSM, the viewer
(PLAN-livemap.md). There is no simulator engine. Nothing in it comes from the scripted brain or is tied to one
class. What I look at while farming, simply put: concentrations of mobs I can kill quickly (close by or easily
reachable), to make the most EXP per hour. My keys today, subject to change: q a single-target skill, w a
multi-target skill, e a mobility skill. Ask me for more: that list decides the fields.

Part 2 - the tracker that fills the model. Start from what today's world.py already does and what it lacks
against the model. Experiments first, on the kept replay (no GPU needed for prototypes), dev group only; when
fresh footage is needed, ask me for a capture (old captures are not re-made); the hindsight twin (tools/perc/track/oracle.py, score.py) is the truth it is graded on. Then PLAN-tracker.md:
PROPOSED, with per-step gates on footage, stop rules and ready-to-paste Opus prompts. Order the steps in line;
mark each step that could run beside another - it touches different files, needs neither the game nor a speed
measurement, and does not wait on the other's result (claude_architecture.md section 7). Running them in
parallel is my decision, not the plan's. Build nothing in maplebrain/. Ask me game-knowledge questions directly.
```
