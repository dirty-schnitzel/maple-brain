# Reworks: how to redo a pillar from scratch

Written 2026-11-16, while the perception redesign (PLAN-perception.md) was being finished. It records why that rework
worked so well and how to run the same process on the other pillars, in which order.

## The pillars
| Pillar | Job | Today |
|---|---|---|
| Perception & modeling | frame -> our world model: what is where *now*, plus beliefs (facing, covered mobs) | the scene model (PLAN-perception.md), tracks, SelfState |
| Knowledge | what is *always* true: from the client files and from what is learned across sessions, not from frames | gamedata.py, NavMap (footholds, ropes, routes), Physics.img numbers in nav/sim.py + brain/moves.py |
| Brain | decisions from the model by behavioural rules | v2 combat instinct (v2/combat.py), v3 planner / goals / tasks (PLAN-v3.md) |
| Execution | the body: carry out what the brain wants, physically | moves, travel, Weapon, Footwork, KeyDriver |

Two concerns run through all four:
- **Looking human:** no fixed timings, no back-and-forth, attack per press, breaks on safe spots, natural input. Each
  pillar applies the same rules; they shouldn't be re-invented per layer.
- **The lab:** labels, reference recordings, replay gates, the sim, bench speed. The project's goal is knowledge +
  software, so this is how every pillar proves itself, not a side tool.

It's a closed loop, not a pipeline: execution *expects* an outcome, perception confirms it (facing is a belief, held
key = last pressed). The model holds predictions, not only observations.

## Why the perception rework worked
1. **It exploited the game's own structure.** The game draws known assets on a known map. So render the map from
   the client files and subtract it; only what's left (mobs, players, drops, effects) needs searching.
2. **The target was measurable before the design:** labels, ~100 % accuracy, 60 fps, bench p50 / p90.
3. **A heavy model got the full context:** the code, measured numbers (where the tick goes, the failure modes), the
   constraints. It asked experiments (E0-E6) to settle unknowns *before* designing.
4. **The process held:** plan doc agreed with the user, its own branch, steps each with a gate, new code in shadow
   beside the old, the switch at the end.

## The recipe for each future rework
0. **Finish the previous rework first.** Don't redesign on a moving base.
1. **Build the gate first:** metrics + reference data + a replay or sim harness to score against. If it can't be
   measured yet, it isn't ready for a redesign.
2. **Take stock:** what exists (code, PLAN docs, memory rules), what fails, with numbers.
3. **Heavy query:** "redesign this pillar from scratch - what in the game's own structure can we invert?" Give it
   the code, the numbers, the constraints and the house rules. Ask for experiments to settle the open questions
   before any design.
4. Run the experiments offline -> write `PLAN-<pillar>.md` -> agree it with the user.
5. Branch; steps with gates; new in shadow beside old; switch when it matches or beats the old.

## Order: Knowledge -> Execution -> Brain
**2026-11-21, the user's recalibration (HANDOFF "START HERE"): two things come before this order** - the tracker
redone so that it is ready for ML, and a simulator (a viewer of the live state with real assets + an engine that
takes our input and trains an AI). Whether the Execution and Brain reworks below happen at all depends on a question
the user left open: a full FSM or a cloned-behaviour AI. Game rules come from v83 code (HeavenClient, Cosmic), not
from guesses or measurements (the user, 2026-11-20).

Start after perception step 3 is done (through 3.4, the switch on clean maps).

### 1. Knowledge
- **Have:** client data (gamedata.py, `assets build`), NavMap built from map footholds + ropes, Physics.img constants
  (sim.py, moves.py), the scene model rendering whole maps from the client files.
- **Rework question:** one knowledge store that perception, brain and body all read: map geometry + render layers,
  physics, mob data (size, speed, HP, moving only on their own footholds), and what's learned per map and kept
  across sessions (spawn refill times, densest spawns, safe rest spots). Today these pieces are split across modules.
- **Gate:** every hunted map loads with no hand edits; scene model and NavMap agree on geometry (same files);
  learned stats survive a restart.

### 2. Execution
- **Have:** nav/sim.py (our character only, Physics.img numbers), moves.py (expected time from the physics, fail at
  ~2x), travel, Weapon, Footwork, KeyDriver, the human-input rules.
- **The insight to test, same trick as perception:** the game runs known physics -> invert it. Today the physics is
  a test harness plus a timeout. Make it the body's live expectation: every tick predict where we'll be given the
  keys held, compare with perception; the gap flags a failure at once (dropped key, knockback, missed rope, wrong
  facing) instead of after a timeout. Plan moves by forward simulation (a jump that lands, a drop that reaches).
  This is also the baseline and the training signal for the learned motor layer, the long-term goal.
- **Sim gaps to close:** slopes, air control, knockback, and mobs (known speed, bound to their footholds) -> a sim
  of the whole scene, not only us. That sim is what later grades the brain offline, with no input sent in public.
- **Take along (the user, 2026-11-22):** two ideas from another bot (HISTORY.md, "maplestory-automation"): its
  key-release locking as a checklist for the KeyDriver, and a dead-man release - no tick ended for ~1 s -> every
  key up (today the KeyDriver holds and auto-repeats our keys while a hung loop sees nothing).
- **Gate:** per-verb success rate and time to target (sim + recorded live runs); prediction-gap distribution on
  recordings; timing distributions vs the user's own play; bench time.

### 3. Brain
- **Have:** v2 combat; v3 (PLAN-v3.md): world-model objects, planner / goals / tasks, reflexes; steps 1-3 done,
  Platform mode passed live 2026-11-15.
- **Last, because** the brain's vocabulary is the body's verbs: designing it before they exist = designing against a
  guessed API. Likely "finish v3 on the new model and verbs" more than a from-scratch redesign; the heavy query here
  is about what the brain should optimise and how to score it, using the whole-scene sim.
- **Gate:** in the sim: EXP/h, kills/min, deaths, idle time; live: EXP/h, deaths, behaviour rules held (no
  pendulums, breaks only on safe spots).

## Left to rework: code no plan touches (2026-11-24)
The date is the file's last commit; the rework wave (perception, the bank, the data model, the tracker plan) left
these files as they were.

| Pillar | Code | Status |
|---|---|---|
| Brain | `brain_v2.py`, `v2/` (combat, targeting, trips, scene, breaks, reflexes), `v3/` (11-09/10) | parked until FSM or clone |
| Execution | `brain/moves.py`, `travel.py`, `nav/sim.py`, `keyboard.py`, `humanize.py`, `runtime/keylog.py` (11-09) | parked (section 2); no dead-man key release; the sim is us only (no slopes, air control, knockback) |
| Knowledge | `navmap.py`'s edges + routes (11-09); physics split between `sim.py` and `moves.py` | wrong drop / fall links (docs/state_model.md 1); PLAN-tracker's step 2 reads them as they are, its step 6 registry covers part of section 1 |
| Metrics | `runtime/exp_meter.py` (11-09) | EXP an hour; not ours in a party; the user proposed 2026-11-24 to drop EXP as a kill signal (open) |
| Safety | `perception/liedetector.py` (11-16) | not looked for while unfocused; no capture watchdog, no phone alert |
| Viewers | `perception/mapascii.py`, `livemap.py` (11-10/17) | replaced by PLAN-livemap's viewer |

PLAN-tracker retires `world.py`, `cover.py`, `nav/selfstate.py`, navmap's placement and `v2/ledger.py`'s "our kill".

## Not a metric: the Lie Detector
2026-11-16, the user's conclusion: Lie Detectors look like an account / character flag, not a reaction to behaviour
(one came during the user's own manual play; rates stayed random per hunting time whatever was varied). Never use LD
counts to grade a rework or as evidence of wrong behaviour. Reflexes still answer an LD when one appears.
