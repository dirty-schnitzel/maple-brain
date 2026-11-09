# maplebrain brain v3: layers, world model, modes (P1 = NEXT: migration steps 1-3, up to Platform mode)

Written 2026-11-08 with the user. Direction agreed ("overall excellent design and plan"). **2026-11-09, the user: P1
priority = get to Platform mode** (= Area mode, `--mark-platform`): migration steps 1-3 below, before the accuracy +
speed plan (HANDOFF "P2"). **2026-11-09: steps 1 (objects) + 2 (planner) DONE on branch `v3`, gate identical
(tools/v3/gate.py); step 3 next.** Design page with the diagrams (private to the user):
https://claude.ai/artifact/RVUYFFktHVpu3EbSBCR4Mh

## Why
Brain v2 is instinct: every tick it asks "what's best right now, given what's on screen?" That is right for combat
(swing timing, knockback, potions, the Lie Detector: ~70 ms reactions) and stays. Above one fight it limits us:
- **No world memory.** A mob off screen is forgotten; nothing knows when a platform was cleared, how fast a spawn
  refills, where other players have been. The Ledger keeps 3 s, for kill counting only. M3 (patrol) needs this.
- **No goals or sequences.** Targeting = cheapest mob now; roam = a random weighted spawn. "Clear this platform, then
  the next", "town for potions and back", "buff every 5 min", "change channel when crowded" can't be expressed.
- **The order decides.** `BrainV2.step` is a fixed first-match chain (BREAK -> LOCAL -> finishing -> TRAVEL -> ROAM);
  every new behaviour = a new branch with a hand-picked place. That's how brain.py reached 1335 lines.

The user's own earlier idea (2026-11-02, HISTORY.md "NEXT BIG FEATURE"): keep the instinctual fighting, add a per-map
analysis + calculated path on top. The trained-model brain (2026-11-04) was dropped for "algorithm decides WHERE and
WHAT" (sessions 20-21). v3 is that idea with a structure.

## The layers
```
perception (unchanged) --update every tick--> WORLD MODEL (Map, Platform, Spawn, Mob, Player, Character; memory)
                                                  ^ reads                     ^ reads
PLANNER  ~1x/s + at once on a task event:  goals score want(world); highest wins (keep margin + varied min stay)
   | start / cancel task                ^ events: arrived, failed, killed, hurt, target lost
TASKS    every tick, interruptible at safe points: Fight(mob), Goto(platform, x), Rest(spot), Loot(drop)
   | keys the task wants
REFLEXES every tick, FIRST, may override: Lie Detector, HP stop, potions, focus
   |
Character.hands -> KeyDriver
```
As built (step 2): the planner re-picks the GOAL ~1x/s + on events, but the active goal names its TASK every tick
(combat decides in ~70 ms; brain v2's chain was per tick). The planner never presses keys; tasks never choose goals.
Nothing blocks: `character.goto(p)` means "the active
goal returns Goto(p, x)" and the task moves us a bit each tick (Travel already works that way).

| Layer | Runs | Owns | Today's code |
|---|---|---|---|
| World model | every tick | what is where, and what happened there over minutes | NavMap, Platform, Track, SelfState, Ledger (raw parts) |
| Planner | ~1x/s + events | which goal is active, which task it wants now | NEW (the if-chain in BrainV2.step is its crude stand-in) |
| Tasks | every tick | one interruptible job | Weapon + Footwork + Targeting, Trips/Travel, Breaks |
| Reflexes | every tick, first | safety | Reflexes, the LD check in hunt_v2 |

## The two contracts
```python
class Goal:                                   # planner layer
    def want(self, world) -> float | None     # sum of named terms (like targeting's); None = not now
    def next_task(self, world) -> Task

class Task:                                   # task layer
    def step(self, now, world, hands) -> str  # "run" | "done" | "failed"
    def can_cancel(self, world) -> bool       # never mid-jump, never mid-swing
    events: list                              # arrived, killed, hurt, failed, target_lost

def step(now, obs, s, driver):                # BrainV2.step in v3
    if stop := reflexes.step(now, obs, hands): return stop
    world.update(now, obs, s)
    if planner.due(now) or task.events:
        goal = planner.pick(world)
        nxt = goal.next_task(world)
        if nxt != task and task.can_cancel(world): task = nxt
    task.step(now, world, character.hands)
```
Scores decide, not the order: a new behaviour = one more goal whose terms say when it matters. House rule kept: a
change is a score term, a table rule, a state, or a parameter with its data source - never a special case.

## World model: one object per thing in the game (thin wrappers, not rewrites)
| Object | Holds | Today | Added |
|---|---|---|---|
| Map | platforms, ropes, links, routes (s), spawns | NavMap | marks (this session only); mobs_on(platforms), best_mob(..., among=), nearest_spot(area) |
| Platform | ends, footholds, y at x, open ends | Platform | marked, last_cleared, live mobs + players on it |
| Spawn | x, y, platform | tuples in nav.spawns | respawn time learned live (death -> new mob there), last seen alive |
| Mob | id, type, x/y, vx, state, platform, reach vs us | world.Track as a dict inside Seen | typed: .dying, .contested, our swings on it, time off screen |
| Player | other characters | Obs.n_tags (count only) | positions over time -> "crowded" |
| Character | x/y, ground/rope/air, platform, facing, HP/MP, keys held | SelfState + Facing + Hands + Obs HUD | one object: .platform, .in_area(area), .hands |

## Goals
| Goal | Wants to run when | Tasks | Needs first |
|---|---|---|---|
| Hunt | always (baseline) | Fight, Goto (roam) | nothing: today's behaviour ported as-is |
| HuntArea (Area mode) | platforms are marked this session | Fight the highest-priority target on any marked platform (moving between them), Goto back when outside, Goto a spawn in the area when quiet | marks + marking phase |
| FollowPath (Path mode) | an ordered path is marked (later) | Goto the next waypoint (platform, rope or ladder); fight mobs along the way first, then resume | ordered marks incl. ropes/ladders |
| Rest | 2-5 min since the last break, nothing near | Goto(safe spot), Rest | today's Breaks as a goal |
| Patrol (Auto mode, M3) | no marks: the default | an area or path computed per map, run like Area / Path | spawns x EXP / respawn; respawn times learned live |
| Buff | varied 4-7 min timer | tap the buff key (ground, between fights) | buff key in Keys |
| Restock | potions low | Goto portal -> town -> shop -> back | map-to-map travel, shop UI (large) |
| ChangeChannel | our area crowded | menu sequence | Player memory, menu reading (later) |

## Modes
| Mode | You mark | The bot | Goal | When |
|---|---|---|---|---|
| Area (Platform mode, P1) | a set of platforms (F9 on each) | fights the highest-priority target on any marked platform, moves between them, comes back when knocked out | HuntArea | first, with the layers |
| Path | platforms + ropes/ladders, in order | walks the waypoints in order and loops; mobs along the way first, then the next waypoint | FollowPath | later |
| Auto | nothing | computes an area or path per map (spawns x EXP / respawn), runs it like Area or Path | Patrol | M3; today's roam until then |
All three are goals over the same world model and tasks; Auto can hand its result to the Path goal. Marking a
rope/ladder uses `SelfState.rope` (already tracked).

### --mark-platform (Area mode) in detail
- `serve ... --mark-platform`, F7: the map is recognised and a hunt starts that perceives but presses NO keys
  (like `--observe`). The SelfTracker knows our platform every tick (livemap shows the same data).
- F9 (new key in `Keys`) = `map.mark(character.platform)`: chirp + log line ("marked 273, y 198, x -305..3185");
  F9 again on the same platform unmarks it. Livemap draws marked platforms in their own colour.
- Marks live in memory only: nothing saved, every session starts fresh (assets built ahead are fine).
- A key starts hunting: the planner gets HuntArea(map.marked).
- Targets only on marked platforms (`fence`: a mob off the area scores None); routes may cross unmarked platforms;
  off the area (fell / knocked) -> no target -> Goto(nearest marked). Mid-fight knockback: the engaged mob stays the
  target while in keep reach (as today).
- Gaps to close in today's code (also needed without v3): roam_goal excludes our own platform (one marked platform
  = never roams inside it) and needs spawns (a marked platform with none = IDLE forever) -> any x on a marked
  platform as fallback; all marked platforms "unreachable" (5-8 s after failed trips) needs a fallback too; a mob
  with no platform counts as "here" within 40 px (scene.py) -> allowed only while we stand on a marked platform.

## Unchanged
The attack logic end to end (v2/combat.py's doc) = the inside of Fight(mob); Travel, moves, the sim (Goto = Travel);
KeyDriver + real presses, never faked input; safety first every tick; every timing randomised; keys only in `Keys`.

## Migration (own branch; main = last good, the user merges; each step gated)
| Step | What | Gate | Size |
|---|---|---|---|
| 1 Objects | Map / Platform / Mob / Character wrap today's parts; the brain reads them instead of dicts | sim 8 seeds x 3 min + agree.py match the baseline exactly (as the session-23 restructure) | ~2 sessions with step 2 |
| 2 Planner | Goal/Task contracts; one goal Hunt = today's chain moved into Fight / Goto / Rest tasks | same: behaviour identical | |
| 3 HuntArea | marking phase, F9, livemap marks, the goal | sim on Line 1 with 2-3 marked platforms: no target outside, always back after forced drops; then live | ~1/2 session |
| 4 Memory | respawn per spawn, last_cleared per platform, players over time; logged, not acted on | numbers vs a recorded run | = M3 |
| 5 Auto mode | Patrol: area / path from spawns x EXP / respawn, using that memory | live A/B vs Hunt, kills (last hit) / min | = M3 |
| 6 Path mode | ordered marks (platforms, ropes, ladders), FollowPath, fights along the way | sim: waypoints in order, back on the path after every fight; live | ~1/2-1 session |
| Later | Buff, Loot, Restock, ChangeChannel | one goal at a time | per goal |

## Risks
- Goals flapping between close scores (botlike) -> keep margin + varied minimum stay (targeting's KEEP_MARGIN pattern).
- Cancelling at a bad moment -> can_cancel (Trips already replaces a trip only on the ground at a move boundary).
- Drift during the port -> steps 1-2 numerically identical before anything new.
- More indirection -> each file's header states its layer and step, like combat.py today.

## Decided (2026-11-08, the user)
- Marks are per session: nothing saved, every session starts fresh; assets built ahead are fine.
- With marks the bot follows platform logic: moves between marked platforms to the highest-priority targets.
- Three modes: Area now, Path later, Auto (M3) the default.
- The layered design + gated migration = the direction.
- 2026-11-09: P1 = steps 1-3 (objects -> planner -> Platform mode), in that order, before accuracy + speed (P2).
  "Platform mode" = the user's name for Area mode.

## Open decisions (ask at the start of step 3)
1. ~~Order of work~~ decided 2026-11-09: layers first (steps 1-2), then Platform mode (step 3); accuracy + speed after.
2. Mark granularity: whole platforms, or an x-range on long ones (Line 1's ground 244 is ~3500 px)? x-range = two
   presses per mark, ~double the marking work.
3. Marks across F8 -> F7 within one serve: kept or cleared?
4. Off-area: swing at mobs in reach on the way back (today's trip behaviour) or ignore them?
5. Goals compete by score with a keep margin (recommended, like targeting) or a fixed priority list?
6. Path-mode detours: how far may the bot leave the path to fight a nearby mob before the next waypoint?
