# PLAN-brain: the goal planner (utility AI) - an assassin's farming loop

**Status: PROPOSED 2026-11-27; questions 2 and 3 answered 2026-11-28** by the brain plan session (branch `brain-plan`, worktree `.claude/worktrees/brain-plan`,
off `tracker-build` at 32cd470). Nothing is built in `maplebrain/`. The measurements and prototypes are in
`tools/brain/` (`proto_play.py`, `proto_where.py`, `draw_play.py`); their outputs are in
`F:\dev\maple-corpus\work\brain-plan\`. **This plan replaces PLAN-tracker's step 9** (the user, 2026-11-27): the new
brain reads the tracker's state directly, and nothing adapts the old brain to it. Its prerequisites are tracker steps 5
and 6 (section "What the tracker must add first").

## The user's goal (2026-11-27, their words, with the decisions of 2026-11-26)
- "research and then create a goal planner plan, to be executed instead of the tracker step 9 (brain compatibility)".
  "This is a very important part of the project - we now have good perception, tracking and data model, the next
  step is the brain itself."
- "The first milestone of the goal planner is combat only, with an assassin, very similar to the assassin
  recordings, an infinite combat loop." "Goals to start with along with combat: Potions, Buffs & Loot, more advanced
  behavior later."
- "The behavior should be very efficient and exp/hour oriented."
- "Restricting platforms (aka platform mode today) should be available from start by restricting what platforms the
  bot should hunt on, default is all platforms available."
- "Humanizer is an option but not necessary - come up with the best solution for humanized input within the goal
  planner."
- Decided in the design talk of 2026-11-26 (memory `utility-ai-design`): P0 a hand-written brain, P1 learning; a
  utility planner for choosing goals, small state machines inside them, tiers for hard priorities; **potions are a
  goal whose urgency rises as HP falls, not a reflex**; **the Lie Detector and the game's focus stay outside the
  model** (the runtime pauses the brain); one planner for every class, with class differences in a class profile and
  the player's habits in a style profile; reaction times are a layer between deciding and pressing, not a goal.

## In short
- **How the user farms as an assassin** (7.6 minutes with the tracker's state, 3 more captures with keys only;
  level 33, Ant Tunnel IV): **64,400 EXP an hour, 24.5 kills a minute, 1.5 casts a kill.** The signature move is the
  **running jump-shot**: 309 of 341 shots come within 0.5 s of a jump press (median 0.037 s apart, a chord), a walk
  key is held at 229 of the 341, 52 jumps a minute. The user **clears a platform and hops to its neighbour**: a visit
  lasts a median 4.8 s, 36 of 51 visits end with no live mob left on the node, and the route is a two-platform rotation
  (477 <-> 468, then 231 <-> 194) inside a chosen area of 6-8 platforms. They loot on the way (50 loot taps a minute,
  median 8 px from a drop), drink HP at a median 29 % HP and MP at a median ~15 % MP, and recast Haste + Claw Booster
  together every 2-2.7 minutes.
- **The design.** Each tick: the tracker's state -> a **Situation** (the derived facts the goals need) -> **goals
  propose actions** (an action, the body **channels** it needs, a **rank** and a **score**) -> an **arbiter** grants
  channels by rank, then score, with commitment against flapping -> a **motor** that plays each action as one of the
  user's own recorded **gestures**, after a reaction delay -> the KeyDriver. Channels are what makes potions and
  looting run *during* combat, as the user does: legs (walk / jump / up / down), cast (attacks and buffs), item
  (potions), pickup (the loot key).
- **Combat is the EXP engine, on two levels.** At each swing's end, shoot what is in the hit box (up to 200 px in
  front + Keen Eyes' up to 200, meowdb: 400 px for the user's Keen Eyes 15; +-50 px), turning for a mob behind - and with a mob inside 65 px always as a
  jump-shot, because a grounded claw attack that close is a weak punch (meowdb; the user: a jump-shot throws even up
  close; 57 of the user's 58 such shots were jump-shots). Between platforms, **where next** is
  chosen like a forager leaving a patch (the marginal value theorem): stay while this platform pays better than the
  area's average, then go to the platform a two-step look-ahead values most (mobs known + spawn points due) per second.
  Open loop on the capture, the two-step look-ahead matches the user's next platform on 59 % of 39 decisions, the
  nearest platform 41 %, a one-step score 38-46 % (its constants tuned on those same decisions: the shape is shown,
  the constants are not).
- **Steps:** 1 the skeleton (state -> planner -> motor -> keys, the decision log, the bot's own keys.jsonl) with the
  shot rule only; 2 combat movement and "where next" in the area; 3 the potion goal; 4 the buff goal; 5 the loot goal;
  6 the long run and the style calibration; 7 the switch (the old brain and `world.py` out). Each step: tests, a sim
  check, an open-loop check on the user's footage, then a live run the user watches.

## Words
- **Goal:** something the bot is out to do (Combat, Potion, Buff, Loot). Each tick it makes zero or more
  **proposals**: an action, the channels it needs, a rank and a score, with the named terms the score came from.
- **Channel:** one part of the body: `legs` (walk keys, jump, up / down), `cast` (attack and buff skills: the
  character's action, one at a time - the game ignores a cast key during a swing), `item` (potion keys: they work
  during a swing, 5 of 5 seen), `pickup` (the loot key). Proposals on different channels run together.
- **Rank and score (dual utility, Dill, Game AI Pro 2, ch. 3):** a higher rank always gets a channel first (3 =
  survival, 2 = urgent upkeep, 1 = normal play, 0 = idle behaviour); inside a rank the higher score wins. Scores are
  0..1, products of considerations through response curves.
- **Commitment:** the goal that holds a channel keeps it unless another beats it by a margin, or until its varied
  minimum stay ends, or a higher rank wants it.
- **Hit box:** where a shot can hit: x up to R px in front of our feet, y about 50 px above to 50 px below (the y
  extent is v83's, HeavenClient `CharStats::get_range`; meowdb gives none for stars). **R = 200 px + Keen Eyes (up to
  +200: 400 px at Keen Eyes 15)** - meowdb's `weapon-reach` and `thief-class-guide`, which replace v83's fixed 400.
  Lucky Seven uses the star range and hits one mob (the nearest in the box, mobCount 1), two stars.
- **Punch zone:** a mob inside 65 px in front makes a grounded claw attack a punch (a stab) instead of a throw -
  "deals almost no damage" (meowdb `thief-class-guide` / `assassin-class-guide`; the damage page: a close-range claw
  hit uses weapon multiplier 1.0 and stat / 300 against Lucky Seven's 3.0 and stat / 100). **A jump-shot throws even
  up close** (the user, 2026-11-27; the footage agrees: 57 of 58 shots with a mob inside 65 px in front were
  jump-shots).
- **Swing:** from a cast key-down to when the next can start: 0.63-0.70 s for the user's claw (p10-p30 of the gaps
  between their confirmed casts; Claw Booster on most of the time).
- **Area:** the platforms (graph nodes) the bot may hunt on: all by default, marked with F9 in platform mode, or
  `--area`. Routes may cross other nodes.
- **Visit:** consecutive standing frames on one node, 1 s or more (air and rope frames in between do not end it).
- **Due spawn point:** a spawn point whose last seen spawn is at least the respawn period (~7.1 s, docs/game_rules.md
  E2) ago and whose mob is no longer held by the tracker (or no spawn was seen there yet).
- **Gesture:** a short key pattern recorded from the user (a jump-shot chord, a lone shot, a loot tap, a buff key
  pressed until it takes), replayed with its own relative timings.
- **Class profile / style profile:** what the class can do (keys, skills and their numbers: PLAN-tracker step 6's
  profile) / how this player plays it (potion lines, buff lead, the gesture library, the where-next constants).
- **Open-loop check:** the brain run over a kept replay of the user's play, with the user's keys as ours; its
  decisions are compared with the user's at the moments the user acted. Nothing it decides changes the footage.

---

## What was measured (2026-11-27)

### 1. How the user farms as an assassin (`proto_play.py`)
Captures, all Ant Tunnel IV, level 33, 2026-11-26, solo: `20261126_200826_2#0` (7.6 min, with a kept replay made
for PLAN-tracker step 5a try 2), `20261126_202434_4#0` (6.5 min, keys only: no kept replay yet), and two short
crossings (`20261126_200709_1#0` 0.9 min, `20261126_201654_3#0` 1.6 min). The bank labels them `idle`: its
attack count knows only the warrior's q / c - the class profile must feed the corpus's attack keys too.

| What | Capture 1 (state + keys) | Capture 2 (keys) | Note |
|---|---|---|---|
| EXP an hour | 64,363 (1,073 a minute) | - | HUD; EXP steps 41 x 122 (Horny Mushroom), 45 x 61 (Zombie Mushroom) |
| kills a minute (EXP steps of a whole kill) | 24.5 (186) | - | the tracker saw 356 deaths: other players' kills too (1.19 players in view on average, 7 at most) |
| casts a kill | 1.54 (286 confirmed casts) | - | a cast = an attack key-down followed by an MP step within 0.35 s |
| attack key-downs a minute | 44.9 | 39.6 | 55 of 341 had no MP step (presses during a swing, or out of MP) |
| gap between confirmed casts (s) | p10 0.63, p30 0.69, p50 0.735, p90 1.32 | - | the swing's plateau 0.63-0.70 |
| Lucky Seven's MP step | 16 on 285 of 286 | - | mpCon 16 = level 20 (Skill 4001003) |
| jumps a minute / shots within 0.5 s of a jump | 51.9 / 309 of 341 | 52.6 / - | jump press -> attack press p50 0.037 s, p90 0.09 s: one chord |
| a walk key held at the shot | 229 of 341 | - | shooting while moving |
| where we were at the press | stand 214, air 99, rope 2, unknown 26 | - | |
| nearest live mob in front at a shot (px, \|dy\| <= 80) | p10 39, p50 139, p90 344 | - | 14 of 341 shots had none in front |
| loot taps a minute / nearest drop at a tap | 49.9 / p50 8 px, p90 39 | 35.0 / - | 5 taps with no drop on screen |
| HP potion (delete, +160): HP share at the press | p10 0.13, p50 0.29, p90 0.47 | 2.1 a minute | 15 of 20 gave a +160 step within 0.6 s |
| MP potion (end, +150 / home, +200): MP share | end p10 0.03, p50 0.17, p90 0.29; home p50 0.09 | end 4.4, home 0.2 a minute | |
| buffs (1 Haste: -15 MP; 2 Claw Booster: -30 HP, -30 MP) | cast together at 40, 162, 323 s (gaps 122, 161 s); 2-5 presses each until it takes | same pattern | durations: Skill/410.img is not exported |
| HP lost a minute / lowest HP share | 325 / 0.11 | - | HP 1,210, MP 1,004 |
| frames standing / air / rope | 56.0 / 36.2 / 7.9 % | - | |
| visits (>= 1 s): length | p10 1.6, p50 4.8, p90 14.2 s (51 visits) | - | live mobs on the node at the visit's start p50 2; at its end 0 on 36 of 51 |
| seconds: attacking + moving / moving / looting / attacking / still | 41.3 / 22.6 / 15.6 / 12.5 / 7.9 % | - | |
| potions on the hotkeys (at 50 s) | delete 200, end 151, home 46 | - | at these rates the end potions last ~40 minutes |

The picture: `F:\dev\maple-corpus\work\brain-plan\map_20261126_200826_2_0.png` (`draw_play.py`): the map, its 64
spawn points, the user's feet and every shot. The user farmed the upper-left cluster - nodes 477 (27 % of standing
frames), 16 (24 %), 468 (18 %), 231 (8 %), 194 (7 %), 330 (5 %), 235 (5 %), 89 (3 %) - and never the lower-right half
of the map.

### 2. The game's rules for the assassin (client files, v83 code, the footage)
- **The hit box.** meowdb (Classic World, 2026-11-27): stars fly 200 px, 400 px with Keen Eyes 15 ("one point gives
  +50 early"; no per-level table); Lucky Seven uses the star range. v83 (HeavenClient `CharStats::get_range`) has a
  fixed 400 px and y -50..+50 around the feet - its y extent is kept, its range replaced (gamedata rules: meowdb over
  v83). The footage: the mob that reacted after a confirmed cast stood p30 50 px .. p90 320 px in front (noisy: other
  players' hits are mixed in; PLAN-tracker step 5's `mob_hit by us` gives the clean number, and with it the user's
  Keen Eyes level is checked).
- **The punch zone** (the user, 2026-11-27, and meowdb): a grounded attack with a mob inside 65 px in front punches
  with the claw - much weaker (meowdb's damage page: multiplier 1.0 and stat / 300, against Lucky Seven's 3.0 and
  stat / 100). A jump-shot always throws. v83's client has no such distance rule (HeavenClient stabs only when prone
  or out of stars), so this is Classic World's. The footage: of the shots with a live mob inside 65 px in front, 57 of
  58 were jump-shots; of the shots without one, 228 of 257 (89 %) - the user jumps almost always when a mob is close.
- **Buffs (meowdb `assassin-class-guide`):** Haste level 1: 15 MP, 100 s; level 20: 35 MP, 300 s. Claw Booster: +2
  attack-speed stages at every level; level 9: 22 HP + 22 MP, 180 s; level 20: 10 + 10, 300 s. The user's casts cost
  Haste 15 MP (level 1) and Claw Booster 30 HP + 30 MP (a low level: meowdb's default build takes Booster 1 at 32).
  Lucky Seven 20/20: two 140 % lines for 16 MP and two stars - the user's 16 MP step.
- **Thief skills in the export** (Skill/400.img): 4001003 Lucky Seven (claw, mpCon 8-16, damage 60-140 %, 2 stars,
  1 mob), 4001002 Double Stab, 4001001 Dark Sight, 4001000 Disorder, 4000001 Keen Eyes (`range` 50-200), 4000000
  Nimble Body. **Assassin (410) is not exported** - String.img names 4100000 Claw Mastery, 4100001 Critical Throw,
  4100002 Critical Recovery, 4101000 Claw Booster, 4101001 Haste ("speed and jump": our walk speed is a dynamic value
  while it runs), 4101002 Drain.
- **Potions work during a swing:** 5 of 5 presses made inside a swing gave their HUD step. The user drinks between
  shots on 50 of 55.
- **The mobs here:** Horny Mushroom (level 22, 403 HP, 41 EXP), Zombie Mushroom (level 24, 436 HP, 45 EXP, jumps);
  41 + 23 spawn points; `mobRate` 0.4; 13 ropes.
- **The graph:** Ant Tunnel IV has 22 chains in `track/graph.py` and 23 platforms in navmap (325 is merged into a
  chain): platform marks must take the graph's node ids.

### 3. Where next (`proto_where.py`, open loop, 39 decisions of capture 1)
At the end of each visit followed by a visit to another node of the user's area (the nodes they stood on >= 2 %), every
candidate was scored from the state of that frame. `known` = mobs the tracker holds there (seen or remembered), `due`
= its due spawn points, `travel` = the graph's seconds table.

| Rule | First choice = the user's | In the first three |
|---|---|---|
| one step: (known + 0.3 due) / (travel + 3 s) | 44 % | 77 % |
| **two steps:** the best (here + next) / (both travels + 2 x 3 s) | **59 %** | 87 % |
| the nearest node | 41 % | 92 % |
| the most mobs known | 44 % | 82 % |
| the most spawn points | 13 % | 36 % |
Over the 9 settings tried (lam 0.3 / 0.5 / 1.0 x tau 1.5 / 3 / 5) the two-step rule beat the one-step rule on 7 and
tied on 2; lam = 1.0 is worse for both (28-36 %). It was
tuned on the same 39 decisions, so it proves the *shape* (look ahead, count what is known and what is due, pay for
travel), not the constants: step 2 fixes them on capture 1 and grades them on another capture. The user's choice from
477 was 468 (2.2 s up) far more often than 235 (0.8 s down, more spawn points): a rotation that keeps the next hop
short, which a one-step score cannot see.

---

## The design

### D1. Where the brain sits (one tick)
```
capture -> Perceiver (+ the tracker: mobs, us, players, spawns, slots, meters, drops; our sent keys handed to it)
        -> state (track/state.py records + events)                        [PLAN-tracker; nothing changed here]
        -> Situation.of(state, facts, profile, our keys, now)             [brain/v4/situation.py]
        -> goals propose -> arbiter grants channels                       [brain/v4/planner.py + goals]
        -> motor: reaction delay + a gesture per granted action           [brain/v4/motor.py]
        -> KeyDriver (hold / tap, focus guard, auto-repeat, dead-man)     [runtime/keys.py]
        -> logs: ticks.jsonl (the Situation's summary + every proposal's score and terms + the grants),
                 keys.jsonl (the keys we sent, the recorder's format with "inj": true)
Outside the model (runtime/hunt_v4.py): the Lie Detector (keys up, siren, stop), the game not focused (keys up,
pause), the window, the scene camera lost (keys up), and the stops listed in D11.
```
The new brain lives in `maplebrain/brain/v4/`; `runtime/hunt_v4.py` is its loop; `serve` / `run` take `--brain v4
--profile assassin`. Brain v2 / v3 stay as they are (the warrior's default) until step 7.

### D2. The Situation: computed once a tick, read by every goal
- **Us:** feet, node, place, floor; **facing** (a belief from the walk keys we sent: rules/brain.md); **the swing
  clock** (our cast key-down + the swing length; confirmed by the MP step, the tracker's `cast` event); HP / MP and
  their shares; potions left per key (the hotkey reader); each buff's time left (cast seen + its length from the
  facts); `stars_doubt` (casts with no MP step while MP was enough).
- **Mobs** (arrays): id, kind, feet, node, life, seen or remembered, the HP meter; per mob: in the hit box in front,
  in the box behind (the profile's box from our feet); per node: mobs known (seen + remembered).
- **Drops:** id, feet, node, age, class; under us (within the pickup reach), on our floor ahead.
- **Players:** per node, how many (for later; logged now).
- **Spawn points:** per node, how many are due now and by a given arrival time.
- **The area:** the allowed nodes; whether we stand on one; seconds from here to each (the graph's table + the walk
  along the floor at our measured speed).
- **Events since the last tick:** our kills and others' (`mob_died` with its credit), hits on us (HP steps with cause
  "hurt"), casts, potion steps, drops taken.
Cost target: the Situation + every goal + the arbiter <= 0.5 ms p50, 1.5 ms p90 a tick on Ant Tunnel IV.

### D3. The planner: ranks, scores, channels, commitment
```
proposals = [p for goal in goals for p in goal.propose(situation)]      # each: goal, action, channels, rank, score, terms
for p in proposals held by their goal now: p.score += COMMIT_MARGIN (varied)
sort by (rank desc, score desc); free = {legs, cast, item, pickup}
for p in proposals:
    if p.score <= 0 or not p.channels <= free: continue
    if a channel of p is held by another goal whose minimum stay is running and p.rank <= that goal's rank: continue
    grant p; free -= p.channels
```
- Ranks: **3 survival** (HP under the critical line), **2 urgent upkeep** (HP or MP under the user's line, MP under one
  cast), **1 normal play** (shooting, moving, buffs, loot), **0 idle** (waiting; later fidget and breaks).
- The arbiter runs every tick (it is cheap); the goals decide per tick too, but a granted action is not cut by a
  slightly better one before its minimum stay (drawn per grant from a range). Events (a kill, a hit on us, a cast
  confirmed, arrival) end a minimum stay at once.
- **Why channels:** the user drinks while shooting, taps loot while running, and stops shooting only to cast a buff.
  One-winner planning would stop the fight to drink; channels make that impossible by construction.
- **One goal, several proposals:** Combat proposes a shot (cast) and a movement (legs) separately, so Loot can take
  the legs for a detour while Combat still shoots from where we stand.
- **Explained by its log:** every tick writes each proposal's goal, action, rank, score and terms, and the grants.
  `tools/brain/scores.py` draws a run's scores over time: when the user says "it left a full platform at 2:10", the
  picture shows why.

### D4. Combat - the shot (cast channel)
At our swing's end (the swing clock), on what is on screen now:
| Case | Action | Score |
|---|---|---|
| a seen live mob in the hit box in front, **inside the punch zone (< 65 px)** | **jump-shot** (cast + legs: the chord; a grounded shot here would punch) - or step back first when a jump cannot land on our floor | 0.9 |
| a seen live mob in the hit box in front, beyond 65 px | **jump-shot** by default (full damage at any range: the user, 2026-11-28); a grounded shot only as the style's share (29 of the user's 257 such shots) and only where no mob is inside 65 px | 0.9 |
| none in front, one in the box behind | **turn and shoot** (cast + legs: a direction tap, then the shot; a jump-shot if it is inside 65 px) | 0.85 |
| none in either box | nothing (the style's rare "air shot": 14 of 341 shots of the user's) | 0 |
The punch zone makes the jump part of Combat's choice, not only style: a grounded shot is never proposed with a mob
inside 65 px in front (the nearest mob is the one hit, so it would take the punch). Whether 65 px is measured from
our feet to the mob's feet or to its body box's near edge is checked in step 1 (the punch is visible: no star flies).
Never at a mob that is only remembered (PLAN-tracker step 9's check, kept). DRY, as in v2: shots with no reaction in
front for two swings and a bit -> doubt our facing, turn. The game's rules kept from v2 (rules/brain.md): one press
= one swing; a key-down during a swing is ignored; a direction key released during a swing is dropped. The style may
add a second press during a swing (the user's mashing: 55 of 341 presses had no MP step) - harmless, the game
ignores it.

### D5. Combat - where (legs): a forager in patches
- **Inside a node:** walk to bring the nearest group into the box (the far edge minus a margin), with jump-shot chords
  at swing ends while walking (the style's share: 91 % of the user's shots are near a jump). A jump is made only where
  its landing stays on the floor (the floor's end farther than a hop, ~86-90 px), unless the route wants the drop.
- **Stay or leave (the marginal value theorem):** stay while the rate here (mobs in reach soon + spawns due here
  within the horizon, per second) is at least the area's best alternative rate; leave when it falls under it - which
  is what the user's 36 of 51 visits that ended empty look like.
- **Where to:** the two-step look-ahead of measurement 3 over the area's nodes: for each next node N and the best node
  M after it, `(value(N) + value(M)) / (travel(here, N) + tau + travel(N, M) + tau)`, `value = known + lam x due by
  arrival`. Then the route (brain/travel.py and moves.py: walk, jump, drop, rope), shooting at whatever enters the box
  in front on the way.
- **Off the area** (knocked, fell, a route through): shoot back at mobs in the box until a leash (36-44 s, as v3's
  HuntArea), then go back to the nearest area node by route seconds.
- **Nothing anywhere:** wait at the node whose spawns are due soonest (rank 0).
- **Constants** (lam, tau, the horizon, the respawn period, the margins) live in the style profile; they are fitted
  on one capture and graded on another (stop rule 6), then on EXP an hour live.

### D6. Potions (item channel)
- **HP:** at each episode (HP falling through the upper part of the user's range) a line theta is drawn from the user's
  distribution of HP shares at their presses (p10 0.13, p50 0.29, p90 0.47). Under theta: rank 2, score rising as HP
  falls. Under the critical line (the profile; proposal 0.15): rank 3. The press, then its HUD step is awaited (+160
  within ~0.6 s); none: one more press after a varied gap.
- **MP:** the same with the user's MP distribution (p50 ~0.15), plus rank 2 when MP is under one cast. Two keys (end
  +150, home +200): end first, home when end's count is 0, or at the user's ratio (8 of 35).
- **Out of potions:** HP under the critical line with no HP potion -> stop (D11). MP potions gone -> keep shooting while
  MP lasts, then stop (an assassin without MP cannot attack).
- It runs during combat: the item channel is its own.

### D7. Buffs (cast channel)
- Per buff in the class profile (Haste on 1, Claw Booster on 2): time left = its length (Skill.img, by level) minus the
  time since the cast seen. The score rises as the time left falls and is highest when it has run out; it is halved
  while a mob is in the box in front (the user recasts in lulls). At the top it beats a shot (0.9).
- **Together:** when one buff wins, another whose time left is under its pairing share gets a bonus (the user casts
  both within a second).
- **Until it takes:** the key is tapped until the cast's MP / HP step shows (the user: 2-5 taps, 0.1-0.4 s apart), at
  most N times, then a varied wait and again.

### D8. Loot (pickup channel; legs for a detour)
- **Under us:** a resting drop within the pickup reach of our feet -> loot taps (pickup channel only: it runs while
  Combat keeps the legs and the cast). The user: 50 taps a minute, median 8 px from a drop.
- **A detour:** a drop on our floor or a node near, no mob in the box -> walk over it (legs, rank 1), score = the
  class weight of the drop / (1 + detour seconds), x a style weight fitted so the share of the user's seconds spent
  looting (15.6 %) is matched.
- **Drops last 130 s** (the user's rule): no hurry while there are mobs.
- **Not taken:** a drop that stays under us after N taps is marked "cannot take" (a full inventory - question 6).

### D9. Humanized input: the motor (the user's question)
Three layers, each from the user's own recordings where they exist, the Humanizer elsewhere; with humanizing off,
every layer gives its median (deterministic tests).
1. **Decisions:** no fixed thresholds - the potion lines, the buff lead, the minimum stays are drawn per episode from
   the user's distributions; small score noise. (Fixed lines are a bot signature: the user's HP at a press spreads
   from 0.13 to 0.47.)
2. **Reaction:** a newly granted action waits a delay before its first key, by stimulus: a mob entering the box while
   ready, a HUD change, a drop landing near, a buff running out. Shape: ex-Gaussian (a normal with an exponential
   tail - the standard shape of human reaction times), fitted to the user's stimulus -> key gaps where the footage
   shows them (step 6), defaults until then. Faster when urgent, never zero.
3. **Gestures:** a library cut from the user's keys.jsonl (`tools/brain/gestures.py` -> the style profile): jump-shot
   chords (shift / space offsets and both holds, with or without a walk key), lone shots, turn taps before a shot, loot
   taps and bursts, potion taps, buff key spam, rope holds. The motor plays a whole recorded instance (its relative
   timings), chosen at random among those of the same context, with a few ms of jitter and the session tempo. A
   per-key distribution would lose what one hand does across keys (the chord's 37 ms, a tap's length after a jump);
   replaying real instances keeps it.
The KeyDriver stays the executor; it gains the **dead-man release** (no brain tick for ~1 s -> every key up: an idea
from another bot, REWORKS.md "Execution") and writes **keys.jsonl** of what it sent, so `play_stats.py` grades the
bot and the user alike.

### D10. The profiles
- **Class profile `assassin`** (PLAN-tracker step 6's profile, with this plan's needs): keys - space Lucky Seven,
  shift jump, z loot, 1 Haste, 2 Claw Booster, delete HP potion, end and home MP potions (the user, 2026-11-27); the
  skills with their levels -> their numbers from Skill.img (400 and 410); the hit box (R = 200 + Keen Eyes, +-50) and the punch zone (65 px); the swing length
  (measured live); what the potions give (+160, +150, +200, measured).
- **Style profile `user_assassin`:** the potion and buff distributions, the gesture library, the jump-shot share, the
  loot weight, the air-shot and mashing shares, the where-next constants, the critical line, the reaction defaults.
  Built from the bank by `tools/brain/style.py`; a new player = a new style profile from their recordings (the
  "Neuromaple" idea: no one-player assumptions).

### D11. Safety and stops (outside the goals)
The Lie Detector, the focus, the window and a lost scene camera: as today (runtime). Stops with a log line and a chirp:
HP under the critical line with no HP potion; we died (HP 0); MP potions gone and MP under one cast; **out of stars**
(K casts in a row with no MP step while MP was enough); the dead-man release fired twice in a minute. A stuck watch:
10 s with no kill, no move and no shot while mobs are known in the area -> logged as `stuck` (step 2's gate counts it).

### D12. What this plan does not do
Restock, portals, channel changes, breaks and rests, fidgeting, fatigue, the chair, avoiding crowded platforms,
parties, other classes (the warrior comes back later as a class profile on this brain), the wide maps, learning (P1).
Each is a later goal or a later plan; the arbiter's ranks 0 and 2 leave room for them.

---

## What the tracker must add first (PLAN-tracker steps 5 and 6; the plan manager carries these into their prompts)
- **Step 5 (events), for a ranged class:** `cast` from our attack key + the MP step; `mob_hit` / `mob_died` by us with
  a ranged box (the profile's box from our feet at the press) and the star's flight (step 5a try 2 measures the delay
  from a key-down to a new meter against the distance); one-shot kills, which show no meter (Lucky Seven kills in 1.5
  casts on average). The kill counts of this plan's gates come from these events.
- **Step 6 (facts, the profile, Skill.img):** export `Skill/410.img` (HaRepacker, `tools/cwdata/export.ps1`) and build
  it with 400 into `assets/mcw`; the assassin's profile (keys above); measured live on the assassin's captures: walk
  speed with and without Haste, the swing with and without Claw Booster, the potions' steps, Lucky Seven's mpCon.
- **Step 9 is replaced by this plan:** its duties move to step 1 (our sent keys handed to the tracker live: the rope
  rule, the drops' "we took it", casts) and step 7 (`world.py` out, `gate.py` and the bench re-based).
- Step 8 (the stored tables) is not needed by this plan and may run beside it.

---

## Steps (one executor session each: Opus; branch `brain-build` off `tracker-build` once tracker steps 5 and 6 are in)
Every step: its area's pytest green and the whole suite when it touches the hunt loop; the `bot speed` line reported;
the numbers written under the step in this file; live runs only with the user watching (they say what they saw); a
gate missed: stop (stop rules). "The user's reference" = the 30-minute assassin recording asked below (until it
exists: capture 1's numbers in measurement 1). "Open loop" = `tools/brain/replay_brain.py` over a kept replay.

| # | What | Gate | Effort |
|---|---|---|---|
| **0** | **Before step 1 (the user, the plan manager, the tracker's sessions):** tracker steps 5 and 6 with the additions above; the 30-minute reference recording, filed, with its kept replay; a kept replay of capture 2 (`20261126_202434_4#0`); the answers to the questions | each in the bank or the plan | - |
| **1** | **The skeleton + the shot.** `brain/v4/`: situation, planner (ranks, channels, commitment, the log), motor (gestures from the 4 assassin captures, reaction defaults), Combat's shot only (D4: shoot, turn, DRY; no walking); `runtime/hunt_v4.py`; `serve` / `run --brain v4 --profile assassin`; platform marks with graph ids (F9 / F10, `--area`); our sent keys -> the tracker live and -> keys.jsonl; the dead-man release; today's potion reflex (HP 50 %, MP 10 %) kept as a **scaffold** until step 3 (question 1); tools `replay_brain.py`, `play_stats.py` (from `proto_play.py`), `scores.py`, `gestures.py` | **Tests:** the arbiter (a higher rank wins a channel; two channels run together; the margin and the minimum stay hold; an event ends a stay), the hit box against hand-made cases both facings, the motor deterministic with humanizing off, the dead-man release, keys.jsonl's format = the recorder's. **Open loop** on capture 1: at the user's 286 confirmed casts the shot rule says shoot or turn-and-shoot on >= 90 %; every case it does not, listed with a picture sheet. **Live** (Ant Tunnel IV, platform mode, node 16 marked, standing): 5 minutes - shots with a reaction from a mob in the box (the events) >= 90 %, 0 shots at a remembered-only mob, 0 keys down for more than 3 s but walk keys, no death; the brain's ms p50 <= 0.5, p90 <= 1.5 | xhigh |
| **2** | **Combat movement and where next** (D5): inside a node, jump-shots, stay-or-leave, the two-step look-ahead, routes, off-area fight-back and leash, wait | **Open loop:** the constants fitted on capture 1, then graded on capture 2 and the reference: the first choice = the user's next node >= the nearest-node rule on each, and >= 50 %. **Sim** (tests, Ant Tunnel IV's graph, fake mobs respawning on spawn points): no target off the area but fight-back; back on the area within leash + route + 15 s after forced drops; no `stuck`. **Live:** 10 minutes in the user's area (question 4) - EXP an hour >= 75 % of the user's reference; visits' length and "ended empty" share reported beside the user's (4.8 s, 36 of 51); jumps and shots a minute reported; 0 `stuck`, 0 deaths | xhigh |
| **3** | **Potions** (D6): the goal replaces the scaffold | **Open loop:** the drawn lines' p10 / p50 / p90 within 0.05 of the user's HP and MP shares at their presses (the reference). **Live** 15 minutes: the HP share at our HP presses p50 within 0.07 of the user's; never under 0.10 with a potion left; MP likewise; a HUD step after >= 80 % of presses; shots a minute >= 95 % of step 2's (the item channel costs no shot); the scaffold gone from the code | high |
| **4** | **Buffs** (D7) | **Live** 15 minutes: Haste and Claw Booster each up >= 97 % of the time; every cast confirmed by its MP / HP step; presses per cast within the user's 1-5; the time left at a recast inside the user's range (from the reference, with the lengths from step 6); EXP an hour >= 95 % of step 3's | high |
| **5** | **Loot** (D8) | **Replay:** the live drop tracker = its kept-replay rows on capture 1 on >= 99.5 % (PLAN-tracker 4a's port check). **Live** 15 minutes: of the drops of mobs we killed inside the area, taken before 130 s >= 90 %; loot taps a minute within 0.8 x / 1.2 x the user's two captures' range (35-50); EXP an hour >= 95 % of step 4's; the "cannot take" rule shown in the sim | high |
| **6** | **The long run and the style** (D9): reaction delays fitted from the reference (stimulus -> key gaps), the gesture library rebuilt from all assassin captures, the where-next constants re-checked | **Live** 60 minutes in the user's area (the user watches the start and the end): no stop but by potions or the user; 0 deaths; **EXP an hour >= 90 % of the user's reference** with the players in view within 0.5 of the reference's mean; in each 5-minute window, shots, jumps, loot taps and potions a minute, the activity shares, the jump -> shot gap and the key holds inside the band of the reference's 5-minute windows (p10-p90) on >= 80 % of windows; the brain's ms. Then the user's look: 2 minutes of the run beside 2 minutes of theirs | high |
| **7** | **The switch:** v4 the default of `run` / `serve`; `world.py` and the looks only it needs, `brain_v2.py`, `v2/`, `v3/` removed or kept as the user says (question 9); `tools/perc/replay/gate.py` and the bench re-based in that commit; CLAUDE.md's code map | pytest green; the bench not slower than the baseline; the user's live check: 5 minutes as step 6's first 5 | high |

Steps 3, 4 and 5 touch different goals and could run beside each other in their own worktrees, but each needs the
game for its live gate: one live run at a time (stop rule 8). The plan manager decides the order with the user.

## Stop rules
1. A gate missed: stop with the numbers. No workaround, no changed constant outside the step's own list, no lowered
   gate.
2. An open-loop agreement under its baseline: stop with the cases on a picture sheet.
3. The brain's ms over its line: stop with the profile.
4. Anything that needs a change in perception or the tracker (a missing field, a wrong death credit, a drop not
   seen): stop and ask - fixes go into PLAN-tracker, not here.
5. A live run with a death, a key stuck down, a shot at a remembered-only mob, or a stop the plan did not list: stop
   with the run folder, read by the `run-analyst` agent.
6. Constants fitted on one capture are graded on another, never on the one they were fitted on.
7. A game rule found otherwise live (potions during a swing, the hit box, the swing length): stop with both numbers.
8. One live run at a time; nothing presses keys while the user records or plays.

---

## Questions for the user
1. **Potions in step 1.** "Combat only" cannot run long without them: the user's MP covers ~62 casts (~1.7 minutes at
   37 casts a minute) and HP ~4 minutes of hits. Recommendation: step 1 keeps today's potion reflex (HP 50 %, MP 10 %)
   as a scaffold that step 3 removes. Or: the Potion goal first, combat second.
2. **The jump-shot - ANSWERED (the user, 2026-11-28):** "when a mob is close, using attack / luck7 without jump results
   in a low damage melee hit, jump shotting guarantees full damage at any range." So the jump-shot is Combat's
   **default shot** (D4); a grounded shot is only a style share, and only with no mob inside 65 px.
3. **The build - ANSWERED (the user, 2026-11-28):** Keen Eyes max (15: R = 400 px), Haste 1 (100 s, 15 MP: meowdb),
   Claw Booster 1 (its length from Skill/410.img or measured; meowdb gives levels 9 and 20 only). "Soon all of this
   will be available in a config file (tracker branch pending)": the class profile of PLAN-tracker step 6 holds it;
   this plan reads it from there and keeps no copy.
4. **The area for the tests:** your cluster on Ant Tunnel IV (nodes 477, 468, 16, 235, 231, 194, maybe 330 and 89 -
   the picture in measurement 1), or all of the map (the default) from the start?
5. **Similar or optimal.** When the where-next score finds a better route than your rotation, which wins?
   Recommendation: EXP an hour decides *where and when*; *how* (the gestures, the jump-shots, the loot taps, the
   potion lines) copies you.
6. **A full inventory:** when a drop stays under us after several loot taps - keep farming without looting that kind,
   or stop?
7. **Out of stars:** stop the hunt (recommended), or switch to something else?
8. **The EXP target:** step 6's 90 % of your EXP an hour (at a similar crowd) - right, higher, or lower?
9. **At the switch (step 7):** may brain v2 / v3 (the warrior's) be deleted, the warrior coming back later as a class
   profile on this brain, or must they stay runnable?
10. **The critical HP line** (rank 3, above any drawn line): 0.15 of max HP? Your lowest in the capture was 0.11.

## Footage asked of the user
- **The reference:** 30 minutes of assassin farming on Ant Tunnel IV in your usual area, solo (no party), chat
  minimized, today's graphics settings: `.venv\Scripts\python -m maplebrain record --label assassin --label farming`.
  Play as you always do; buffs and potions as usual.
- Later (step 6, optional): 10 minutes on a second map you farm, to check the where-next rule away from its map.

## Session prompts (ready to paste; Opus; each ends with the `handoff` skill)
```text
Brain, step 1 (the skeleton + the shot). Needs PLAN-tracker steps 5 and 6 with the additions of PLAN-brain.md
("What the tracker must add first") and the user's answers 1, 3, 4. Read PLAN-brain.md - Words, measurements 1-2,
D1-D4, D9-D11, step 1, the stop rules - docs/state_model.md, .claude/rules/brain.md, brain/v2/combat.py's doc
(the game's rules for a swing), runtime/keys.py and runtime/hunt_v2.py, tools/brain/proto_play.py. Branch brain-build
off tracker-build (a worktree if another session uses the main folder). Build maplebrain/brain/v4/ (situation.py,
planner.py, combat.py with the shot only, motor.py), runtime/hunt_v4.py, `--brain v4 --profile assassin` for serve /
run, platform marks on graph ids, our sent keys to the tracker and to keys.jsonl, the dead-man release, the potion
scaffold; tools/brain/replay_brain.py, play_stats.py, scores.py, gestures.py. Tests first. Then the gate in its
order: tests, open loop on 20261126_200826_2#0, the live 5 minutes with the user watching. Numbers into the plan
under "Step 1"; a gate missed: stop.
```
```text
Brain, step 2 (combat movement and where next). Needs step 1, the kept replays of 20261126_202434_4#0 and the
reference, the user's answers 2, 4, 5. Read PLAN-brain.md - measurement 3, D5, step 2, the stop rules - and
tools/brain/proto_where.py (the reference rule), brain/travel.py, brain/moves.py, brain/v3/goals.py (HuntArea's
leash), tests/test_v3_area.py (the sim). Branch brain-build. Fit lam and tau on 20261126_200826_2#0 only, then grade
on the other captures. Build the movement proposals in brain/v4/combat.py and brain/v4/where.py, the sim test, then
the live 10 minutes. Numbers into the plan under "Step 2"; a gate missed: stop.
```
```text
Brain, step 3 (potions). Read PLAN-brain.md - D6, step 3, the stop rules - and measurement 1's potion rows; the
reference recording's presses (play_stats.py). Branch brain-build. Build brain/v4/potion.py (HP and MP, the drawn
lines, the critical rank, the HUD-step wait), remove the scaffold, extend the style profile. Open loop, then the
live 15 minutes. Numbers into the plan under "Step 3"; a gate missed: stop.
```
```text
Brain, step 4 (buffs). Needs PLAN-tracker step 6's buff lengths from Skill/410.img. Read PLAN-brain.md - D7, step 4,
the stop rules. Branch brain-build. Build brain/v4/buff.py (time left, the lull factor, pairing, tapping until the
cast's step). The live 15 minutes. Numbers into the plan under "Step 4"; a gate missed: stop.
```
```text
Brain, step 5 (loot). Read PLAN-brain.md - D8, step 5, the stop rules - and track/drops.py's docstring (PLAN-tracker
4a). Branch brain-build. Build brain/v4/loot.py (taps under us, detours in lulls, "cannot take"); check the live drop
tracker against its kept-replay rows first. The live 15 minutes. Numbers into the plan under "Step 5"; a gate missed:
stop.
```
```text
Brain, step 6 (the long run and the style). Read PLAN-brain.md - D9, step 6, the stop rules. Branch brain-build.
Fit the reaction delays from the reference (stimulus -> key gaps: a mob entering the box while ready -> the shot, a
drop landing within reach -> the first loot tap), rebuild the gesture library from every assassin capture, re-check
the where-next constants on a capture they were not fitted on. Then the 60-minute live run, the 5-minute windows
against the reference's, the user's look. Numbers into the plan under "Step 6"; a gate missed: stop.
```
```text
Brain, step 7 (the switch). Needs the user's answer 9. Read PLAN-brain.md - step 7 - and PLAN-tracker.md's step 9
row. Branch brain-build. Make v4 the default of run / serve; remove world.py and what only it needs (and v2 / v3 if
the user said so); re-base tools/perc/replay/gate.py and the bench in that commit; update CLAUDE.md's code map. The
whole pytest, the bench, the user's 5-minute live check. Numbers into the plan under "Step 7".
```

## Commands (from the repo root, `.venv\Scripts\python`; no GPU, safe while the user records)
```powershell
tools\brain\proto_play.py "20261126_200826_2#0" [CAP ...] [--out DIR]     # measurement 1 (keys only without a kept replay)
tools\brain\proto_where.py "20261126_200826_2#0" [--area auto|all|N,N] [--lam 0.3] [--tau 3]   # measurement 3
tools\brain\draw_play.py "20261126_200826_2#0" [--out PNG]                 # the picture of measurement 1
```
