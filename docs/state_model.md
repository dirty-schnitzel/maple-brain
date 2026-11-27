# The state model: the game at one instant

**Status: OK'd by the user 2026-11-23, as a whole (the tracker plan session, Part 1:
`docs/prompts/tracker-plan.md`); its four questions are answered (last section). Nothing of it is built: the
tracker that fills it is planned in `PLAN-tracker.md` (Part 2).**
Every number below was measured in this session; the commands are at the end. Tools: `tools/model/`.

## In short
- **The state has four parts.** (1) The map's graph, fixed, built before play. (2) Facts: the numbers of our
  character, of each mob kind, of the map and of the game, each with its source; some change during play.
  (3) The frame: what the screen shows of the map, us, and every mob, drop and other player - what it is, which
  one it is, where it is on the graph, how it is seen, and what is remembered of it. (4) The events since the last
  frame. Everything else (same floor, in reach, how many mobs are where, seconds to get there) is computed from
  these and never stored.
- **What the fields are chosen by (the user, 2026-11-23):** "how many are there and how quickly I can get there
  -> max exp/hour" - not a mob's HP, facing, spawn time or kind. Besides the mobs: other players, drops by value;
  of ourselves: HP / MP and potions, buffs and cooldowns, EXP and level. Of a platform out of view: nothing ("I
  look again"). So the two derived facts that must be cheap are **mobs per floor** and **seconds to get there**;
  no mob-HP reader is built; memory of things out of view is short.
- **The graph audit (section 1):** nodes keep their unit (the client's foothold chain) but are built wrongly on 39
  maps; placement is rebuilt as one rule for every kind; edges and routes stay as they are for the brain rework,
  with two additions the model needs (floors, a seconds table) and a rebuild that does not stop the hunt.
- **Measured for it:** standing feet sit on the surface to the pixel (mobs 93 % within 1 px, us and other players
  exactly 1 px under it = the name tag's offset); 20 things are placed in one call in 16 us (median map) to 62 us
  (the largest); our walk speed read off our own motion is 152-157 px/s where the config says 125; the whole
  state stored for every frame is 222 bytes a frame, 9 MB an hour packed.
- **Found on the way, for Part 2:** (a) 41 of 128 mob kinds have two poses that are ONE picture under two feet
  points (a jump = a walking picture drawn lower): the fit names either, so a jumping Bubbling's feet read 17 px
  too low; (b) mobs that can jump DO change platform by jumping (2.7 % of Bubbling lives on Line 1, 27-32 % of
  Slime and Evil Eye lives); mobs that cannot jump never leave their chain (0 of 184 lives settled on another).

## Words
- **Foothold:** one straight piece of ground in the client's map file. **Chain:** footholds linked left to right
  by the client's `prev` / `next` = one platform. **Node:** a chain or a rope / ladder. **Floor:** nodes one can
  walk across without a jump (almost always one chain: section 1).
- **Thing:** a mob, a drop, another player, or us. **Feet:** the point a thing's position is given by.
- **View:** the part of the map on screen now. **In view / out of view:** inside or outside it.
- **Seen:** perception found it on this frame. **Covered:** in view, not found, and something is drawn over the
  place it can be. **Remembered:** in the state without being seen now.
- **Fact:** a number that is not read off one frame (walk speed, a mob kind's HP). **Dynamic value:** a fact that
  can change during play. **Derived fact:** computed from the state when asked, never stored.

---

## 1. The graph: fixed per map, built before play

Audit of `maplebrain/nav/navmap.py` on all 364 maps (82,632 footholds: 56,007 walkable, 26,526 walls, 99
ceilings). Timed pinned to the performance cores, `serve` loaded and idle.

| Part | Today | Measured | Verdict |
|---|---|---|---|
| **Nodes** | a chain starts only at a walkable foothold whose `prev` is not walkable; ropes by their index | 11,218 chains (per map p50 20, p90 74, max 311). **483 footholds on 44 maps become one-foothold platforms of their own**: their `prev` is walkable but does not link back (the floor continues behind a wall's foot), so the chain is never started and every piece after it stands alone. Built from the links completely: **10,873 chains, 39 maps change**. No chain has a gap; 825 chains hold a piece steeper than the client's `walkSlant` 0.9 | **keep the unit, change the build** |
| **Placement** (`platform_at`, `surfaces`, `below`) | scans every platform per call; three callers with three tolerances (us 9 px or the minimap's 18, mobs 16, drops their own foothold table), players not placed; `platform_at` retries at x +-8 / +-16 px for the minimap's coarse x | 5.4 us a call p50, 12.8 p90, 42 max (39 us on the largest map: 20 things = 0.8 ms a frame). One array call for 20 things: **16 us on the median map, 62 us on the largest**, the same answer on 72,800 of 72,800 test points. Two surfaces closer than 9 px at one x exist on 127 maps (mostly at joints): position alone cannot always say which | **rebuild**: one rule, every kind, one call a frame (section 2) |
| **Edges** (`_find_links`) | 101,292 links: jump 33,886, drop 20,740, fall 19,381, leap 10,759, grab 8,506, let_go 2,634, exit 2,358, descend 2,358, walk 670; found by sampling every 4 px | build 0.12 s p50, 0.63 p90, 3.0 p99, **4.7 s max**; 77 % of it is the walking-jump arc tried against every platform. Wrong today: 1,079 "fall" links are level joints (priced 0.5 s); of the drop links 2,443 leave a `forbidFallDown` foothold, 8 a `cantThrough` one, 2,351 land 600 px or more lower (game_rules.md A6); a sampled "walk" link is made both ways also where the client's links run one way | **keep for the brain rework**; the model adds floors by geometry + links, and a rebuild on a worker thread (below) |
| **Routes** (`route`) | Dijkstra per question, scanning every link per step | 0.2 ms on a median map, 1.3 ms p50 on Line 1, 9.8 ms on a p90 map, 100 ms on the largest | **keep for the brain**; the model adds a node-to-node seconds table: 2 ms and 7 KB on Line 1, 93 ms and 393 KB on the largest map, built with the edges |

### What the model's graph holds
- **Nodes.** A floor node = one chain, its id = its leftmost foothold's id (as today; unchanged on the 325 maps the
  fix does not touch). A rope node = id `-1 - index` (as today). Per node: its footholds as arrays (x1, y1, x2,
  y2, the client's foothold id, layer, `forbidFallDown`, steeper than 0.9), whether each end is open (a wall or
  the map's edge closes it), and its **floor number**.
- **Floors.** Two chains are one floor only where their ends meet at one point, no wall stands on the joint and
  nothing but the missing link separates them: **19 joints in all 364 maps** (e.g. the Golem's Temple maps). The
  other joints are not floors but steps, kept as links: 122 end-to-end joints with a wall standing on them (the
  floor under a box; the client links them one way), 345 T-joints on 97 maps (a ramp's foot on a floor's middle:
  down the ramp onto the floor, not back) and 81 crossings on 54 maps. So "same floor" is nearly "same node",
  and exact where it is not.
- **Ropes and ladders:** x, top, bottom, ladder or rope, the node at the top.
- **Fixed places:** the spawn points (mob kind, x, y, node), the portals (x, y, node, target map), the NPCs, the
  map's bounds (`vrBounds`).
- **Edges and the seconds table:** navmap's links as they are, and from them `seconds[a][b]` = the cheapest way
  from node a to node b. Both depend on dynamic values (jump height, reach, speeds): **when one changes, they are
  rebuilt on a worker thread and swapped in whole**; readers use the old ones meanwhile (at most 4.7 s on the
  largest map, 0.12 s on a median one). Nodes, floors and placement never depend on a dynamic value.
- **Not in it (waits for the brain rework):** correct drop and fall links, per-move costs, mobs' own moves
  (a jumper's hop), portals as edges between maps.

---

## 2. Things and where they are

### The view
`view` = the map pixel shown at the play area's top-left corner (the scene camera), with the play area's size
(1366 x 700) and the rectangles the UI hides (the minimap window as measured, the keycaps). A thing is **in view**
when its body box meets that rectangle. On a frame where the camera is not found (`view.found` false: a map
entry's first second, a fade) nothing is measured: every thing keeps its last values and says so (`cover = blind`).

### One placement rule, for every kind
In: the feet (x, y) in map pixels, what the kind can do (fly, climb), and the thing's own last frame (its node,
its vertical speed). Out: `place`, `node`, `from_node`, `off`.
1. **rope** (kinds that climb: us, players): the feet within the rope tolerance of a rope's x, between its ends,
   and not standing by rule 2.
2. **stand**: the nearest surface at the feet's x is within **3 px** and the thing is not moving up or down
   (a jump passing a platform's level is not standing on it). Two surfaces within 3 px: the node of the last
   frame wins. `node` = that chain.
3. otherwise **air** - or **fly** for a kind with a fly animation: `node` = the first surface under the feet
   ("over which platform"; none: over nothing), `from_node` = the node it stood or hung on last.
`off` = feet y - the node's surface y at that x (px, y grows down: negative = above it); on a rope, feet x - rope
x. It is the "how sure": a standing thing has |off| <= 3, a thing in the air its height.

**Where the feet come from, and how exact they are** (13 sound captures, `place_footage.py`):
| Kind | Feet | Measured against the nearest surface |
|---|---|---|
| Mob | the pose's feet point (the client's own origin) | walking / standing poses, 607,308 sightings: 88.0 % exactly on it, 93.0 % within 1 px, 93.7 % within 2 (slopes: +-1-2 px on the Ant Tunnel maps); 4.3 % more than 17 px above it = jumps shown under a walking picture ("found on the way" a); the last 2 % are in the air lower than that. Hit poses 97.9 % within 1 px, die poses 96.9 % |
| Us | our name tag: centre x, top y - 1 | 67.4 % of all frames exactly 1 px under a surface (the tag's own offset), the rest in the air or on a rope. The tag is found on 96.7 % of the frames of the 30-minute capture |
| Player | its name tag, the same offset | 44.5 % of the other tags exactly 1 px under a surface: the same offset holds; the tag list also holds mobs' own tags and text that is no player (Part 2 sorts them) |
| Drop | the picture's bottom-centre; y = its foothold's surface | 99.6 % within 4 px: the 5-6 px bob, not an error. x is exact |

### The fields
Changing = per frame unless said. "Truth" = the hindsight twin (`tools/perc/track/oracle.py`, `score.py`);
"labels" = by-eye labels of sampled frames (`tools/perc/label_eval.py`, new small sets where none exist).
Targets are proposals; "today" is `world.py` on the 13 sound captures (REPORT-track-before.md).

**The frame**
| Field | Meaning, unit | Source | Measured by -> target |
|---|---|---|---|
| `n`, `t` | the frame's number in the session; the session clock, s | the capture | by construction |
| `map` | the map's id; fixed for a stay | `nav/identify.py` at entry | - |
| `view.x`, `view.y`, `view.found` | the map px at the play area's top-left; found on this frame | the scene camera | found on the frames from its first fix to the exit fade (`sound.py`) -> >= 99 %; exact px on hand-checked frames (120 of 120 per map today) |
| `view.ui` | the rectangles the UI hides; changes when the minimap window does | measured window + fixed rects | - |

**Us**
| Field | Meaning, unit | Source | Measured by -> target |
|---|---|---|---|
| `x`, `y` | our feet, map px | our tag + the view | tag found -> >= 97 % of frames (today 96.7 %); standing frames with off 0: labels -> >= 99 % |
| `place`, `node`, `from_node`, `off` | the placement rule above | the rule | 200 labelled frames (stand / air / rope, which node) -> >= 99 %; every stuck case SelfState's docstring lists stays a test |
| `vx`, `vy` | speed over the last 0.2 s, px/s | our positions | against the plateau of our own walk (152-157 px/s) -> within 5 % |
| `facing` | -1 left / +1 right / 0 unknown - **a belief**: nothing on screen shows it | our walk keys | no truth on screen; checked by its results (a hit lands on the side we believe) |
| `act`, `act_until` | what the character does: stand, walk, air, climb, swing (with the key), hit (thrown), dead; until when a swing lasts - **a belief** for the swing | place + motion + our key + the MP step that confirms a cast (0.1 s after the key, p50) | swings: an MP step follows the key on casts that cost MP -> >= 99 % |
| `hp`, `hp_max`, `mp`, `mp_max` | the HUD's numbers | HUD digits | read on 100 % of 110,082 frames, 0 misreads (a value that changes and comes straight back) -> 0 per 100,000 |
| `exp`, `level` | EXP points; the level | HUD digits; the level's digits are read today only offline (`corpus.py char_of`) | as HP |
| `slots` | for each of the 8 hotkeys (Shift, Ins, Home, PgUp, Ctrl, Del, End, PgDn): the item on it and its amount, tracked (the user, 2026-11-23: "read every item and it's amount on the hotkeys ... and track them") | **not read today** (only "the slot holds something", two keys): a new reader - the slot's icon against the item pictures, the amount's digits | 100 labelled frames -> item and amount exact; an amount's step fits the key pressed (a potion drunk = -1) |
| `buffs` | [(skill, until)] the buffs running | a cast seen (key + MP step) + the skill's length from the client files. The buff icons are not read (the user, 2026-11-23: "no need for perception") | 20 casts by eye against the icon -> within 1 s |
| `cooldowns` | [(skill, ready at)] | a cast seen + the skill's `cooltime` | as buffs |

**Every mob**
| Field | Meaning, unit | Source | Measured by -> target |
|---|---|---|---|
| `id` | this mob's number, never reused in a stay: the same id = the same mob as on earlier frames | the tracker | truth: one id from birth to death -> >= 90 % of lives (today 64 %); the same id across a cover in view of up to 1.5 s -> >= 95 % (today 31-82 %) |
| `kind` | the client's mob id | the fit, voted over the track | frames with a track of another kind on the mob -> 0 (today 3,428, look-alike mushrooms) |
| `x`, `y` | feet, map px. While not seen: where it was last seen | the fit + the view | present: mob-frames found, truth -> >= 99 % (today 96.4 %; 85 % of the misses are mobs more than 40 % past the screen's edge); ghosts -> <= 0.3 % of mob-frames (today 1.4 %); feet: labels -> within 1 px on >= 99 % standing, >= 95 % in the air (today 17 px off in a Bubbling's jump) |
| `place`, `node`, `from_node`, `off` | the placement rule | the rule | labels: the node -> >= 99.5 % of standing mobs; stand / air -> >= 99 % |
| `vx`, `vy` | px/s | its positions | - |
| `facing`, `pose`, `opacity` | -1 / +1; animation + frame; 0..1 | the fit, look-alike poses settled by the motion | labels (facing, animation) -> >= 99 % of clear mobs |
| `life` | spawning (fading in) / alive / hit / dying | pose + opacity | truth: a death seen is noticed -> p90 <= 0.05 s (today 0.0) |
| `seen`, `vis`, `cover` | found on this frame; the share of its body's pixels seen; what hides the rest or all of it: none, scenery, player, us, mob, drop, effect, ui, cloud, edge, out of view, blind | the fit's per-pixel verdicts against the known boxes and masks | 100 labelled covered mobs: the cover's kind -> >= 90 % |
| `unseen_s` | seconds since it was last seen | the tracker | - |
| `can_lo`, `can_hi` | while not seen: the x range of its node where it can be now | memory (section 3) | truth: when it is seen again, it is inside -> >= 99 % |
| `born_t`, `born_how`, `first_pose` | first seen; how it came into sight: faded in (a spawn seen), came into view, uncovered, there at entry; the pose it was first seen in (a die pose: first seen dying - its own field, the user 2026-11-24) | the tracker | 50 labelled births -> >= 95 % |
| `hits`, `last_hit_t`, `last_hit_by` | hits seen on it; the last one's time and whose: us / another player / unknown | events | 100 labelled hits -> >= 95 % |
| `seen_share` | the share of its life it was seen | the tracker | - |
| `hp`, `hp_t` | its HP meter's green share 0..1 as last read, and when; kept while the track lives (memory: no HP guessed, no healing modelled); None = never read. The user, 2026-11-26: "The only thing we would be tracking from it is current hp %, by looking at how much of the hp meter is full (green)"; "Only mobs that have been hit by us will display the hp meter"; "if I already hit a mob and the meter appeared - any further damage by other players will show up on MY meter" (the meter shows the mob's absolute HP) | perception/meters.py finds the meter in a band above each mob the fit saw (its box 30 px over the pose frame's body box, centred on it) and reads the green; the tracker ties it to the one track whose sighting it names, its fill read - another mob overlapping it, seen or not, does not block (perception's place rule decides; a remembered or hidden one that could be under it is counted for the events: PLAN-tracker step 5a, close); a meter naming two sightings teaches nothing | L9, 100 frames by eye: found >= 99 %, the right mob >= 99 %, the fill within 3 % |

**Every drop**
| Field | Meaning, unit | Source | Measured by -> target |
|---|---|---|---|
| `id` | its number | the tracker | two drops of one item on one spot told apart: the 2 linking mistakes in 537 drops (PLAN-loot.md 13) -> 0 |
| `item`, `class` | the picture class (items.json); meso bronze / gold / bundle / sack, equip, use, etc, setup - the value a reader sorts by | the drop finder | PLAN-loot's gates: resting drops found 99.7 %, 0 wrong identities (met) |
| `x`, `y`, `node` | where it lies: x exact, y its foothold's surface | the finder's foothold | - |
| `born_t`, `from_mob` | its first resting sighting; the mob whose death fits it in time and place (or none) | the tracker | 50 labelled drops -> the right mob on >= 90 % |
| `seen`, `cover`, `unseen_s` | as a mob | the finder | gone noticed -> <= 0.5 s after its place shows without it |

**Every other player**
| Field | Meaning, unit | Source | Measured by -> target |
|---|---|---|---|
| `id` | its number while it is followed | the tracker, on name tags | a new label set (200 frames): players found -> >= 95 %, non-players called players -> <= 1 % |
| `x`, `y`, `place`, `node`, `from_node`, `off`, `vx`, `vy` | as us | its name tag + the rule | labels: the node -> >= 95 % of standing players |
| `seen`, `cover`, `unseen_s` | as a mob | the tracker | - |
Not perceived, so not fields: a player's facing, what it does, its party.

**Clean sightings teach first, crowded ones may teach too** (the user, 2026-11-26, on the sheet of pet tracks holding
their owners' name tags: "players and pets should be classified when not obstructed"; relaxed 2026-11-27: "Lets relax
this rule, it is best if possible to classify something when it is alone, but not mandatory"). What a thing IS - a
player's or a pet's class, a body's height, a name's width, a mob's kind, a death, a mob's HP - is best learned from
sightings where it is seen alone and whole. A sighting that overlaps another thing (name tags touching, bodies over
each other) may teach too when its own evidence names one thing (the HP meter's box), and a clean sighting's reading is
preferred over a crowded one's. For players and pets (built under the strict rule, kept as built) (PLAN-tracker step 4b, try 3): a track whose name's width
is sure continues only on a box of that width; a box where two names run together is split by the widths known; the
class, the body's height and the name's width learn only from tags standing alone (no other tag within 12 px on its
rows, no other character's body in its column). Mobs' overlaps (swapped ids, a death read on the wrong mob) are
checked in PLAN-tracker step 5.

**Ropes are grabbed by pressing up or down** (the user, 2026-11-26). We are on a rope only after a grab with up or
down down; staying on it needs no key; a jump or a fall past a rope without the key is not on it, whatever the speed.
While our keys are not handed to the tracker (live, until PLAN-tracker step 9) and for other players (no keys known),
the placement rule alone decides.

---

## 3. Memory: what the state keeps of things not seen now

No timers on what can be seen. The rules, by why a thing is not seen:
1. **Covered, in view** (behind a player, an effect, front scenery, the minimap, a thick cloud, another mob): it
   stays, for as long as it can be there. `can_lo..can_hi` starts at the last sighting, widens at the kind's top
   speed (a client-file fact, checked against what the tracker measures), stops at its node's ends, and loses
   every stretch where the frame shows the scenery its body would cover. Seen again inside it: the same `id`.
   Nothing left of it: it is gone (event `mob_gone`, how = unseen). A mob that walked behind a cloud is still
   behind it; a mob that died behind it is found gone the moment the cloud, or the mob's whole range, is clear.
2. **Out of view** (the screen scrolled, or it walked off): kept **4 s** (OK'd 2026-11-23; today's `offscreen_s`), so a
   mob at the screen's edge keeps its id when the view swings back - 13 of the 19 gaps the truth could not judge
   were mobs off screen for up to 3.4 s. After that it leaves the state with event `mob_left` (not a death).
   Nothing longer: the user looks again on arrival.
3. **Drops** do not move: a drop stays - covered or out of view - until its place is seen without it, or until
   it is 130 s old (the user's rule, 2026-11-21).
4. **Players**: kept through a cover of up to 1 s (OK'd 2026-11-23: "players move a lot"); out of view = gone
   (`player_left`).
5. **Blind frames** (no camera): everything stays as it was, `cover = blind`; no thing begins or ends.
6. **Spawn points** (PLAN-tracker step 3b; `track/spawns.py`, `state.SpawnPoint`). The user, 2026-11-25: "keeping
   track of the time since last spawn (on spawn point) is a valid tracking object. It would not be trying to add
   predictive abilities to the tracking behavior (my original rule), it is a part of tracking's memory (which is OK)
   ... We are just tracking this, it doesn't have to be a part of the AI model, it is part of the overall data we
   collect." Each point of the map (map.json, not hidden: `index`, `kind`, `x`, `y`, `sy` = spriteY - where a flyer
   appears -, `node`, `mob_time`) is a record with: `last_spawn_t` (the last spawn SEEN there: its mob's first
   sighting; None = none this stay), `last_mob` (that mob's id), `spawns` (seen this stay), `in_view` (the point on
   screen, not under the UI or a box the trackers hold). A spawn seen = a mob born `faded in` (its opacity rising:
   the fade-in is 0.82 s on Classic World) traced back to the one point of its kind that could have put it where it
   was first seen in the time it has existed (its kind's speed, or one hop up; two such points: none; event
   `spawn_seen`: point, mob id). Measured:
   98.0 % of 597 faded-in mobs on the 13 sound captures. No respawn rule, no timer, no guess about spawns not seen.
   Spawns come in rounds every ~7.1 s (`docs/game_rules.md` E2) - not tracked or predicted here.
Each thing's history is in its own fields (section 2: `born_t`, `born_how`, `hits`, `last_hit_*`, `seen_share`,
`unseen_s`, and `x`, `y` = where it was last seen). How it left is in its last event.

---

## 4. Events since the last frame
One row each: the frame, the kind, the things it names, a value, how it is known. They are the training labels
and the scoreboard; a reader never has to compare two frames to find one.

| Event | Says | Known from |
|---|---|---|
| `mob_new` | id, how (faded in / came into view / uncovered / there at entry) | the tracker |
| `mob_hit` | id, by us / another / unknown | the hit pose or the knockback begins; ours when it falls in our swing's landing window with the mob in that skill's reach |
| `mob_died` | id, by us / another / unknown, seen or not | the die pose; unseen: its range came up empty. Ours as `mob_hit`, or an EXP step at that moment |
| `mob_gone`, `mob_left` | id, how: vanished in view with no die pose / unseen / out of view for 4 s | memory |
| `drop_new`, `drop_gone` | id, item, from which mob; how it went: we took it (our pickup key, in reach, at that moment), gone in view, found gone, 130 s old | the tracker + our keys |
| `player_new`, `player_left` | id | the tracker |
| `hp`, `mp`, `exp` | the step's size and its cause: hurt, potion, recovery, a cast (which key), a kill we damaged | the HUD + our keys. On the 30-minute capture: 385 EXP steps of exactly 28 (a Bubbling's EXP), 512 MP steps of 12, 81 of 35, 10 of 13 (three skills), 55 of +150 and 21 HP steps of +198 (potions), 179 of +10 HP and 172 of +3 MP (recovery), 178 HP losses |
| `level_up`, `we_died` | - | the HUD |
| `cast` | the key and the skill, when our swing begins | our key, confirmed by the MP step |
| `fact` | a dynamic value changed: name, old, new, source | section 6 |
| `map`, `view_lost`, `view_found`, `lie_detector` | - | perception |
Our keys (down / up) are their own stream beside the state, as recorded today (`keys.jsonl`): the state + the
keys are one training example. **A kill = `mob_died` by us**; EXP is never a kill count (it is shared by damage).

---

## 5. Facts: one registry, each with its source

Today these sit in `config.py`, the client files and the code. In the model: one table, `name -> value, unit,
source, since when`, read by everything. "File" = `assets/mcw` built from the client export.

| Fact | Today | In the model |
|---|---|---|
| **Us:** walk speed | `Nav.walk_speed` 125 px/s (config) | **measured live**: 152-157 px/s on the capture (section 6) |
| jump: take-off speed, height, sideways speed | `Nav.jump_speed` 555, `jump_height` 70, `jump_vx` 155, `jump_reach` 85 (config, fitted 2026-11-01) | measured live: apex 77-86 px (p25-p50), level hops 0.6 s, 86-90 px far, 150-153 px/s sideways |
| climb speed; rope grab, leap and landing numbers | `Nav.climb_speed` 125 and five more (config) | climb measured live: 121-127 px/s; the rest stay config until the brain rework |
| weapon type, its attack speed | `Combat.weapon`, `attack_speed` (config, `--weapon`) | the profile (section 6) -> `attacks.json` |
| reach per stance | `brain/reach.py` from `attacks.json` (file) | the same boxes, per skill |
| swing length | stance ms x (10 + attackSpeed) / 16 (`reach.py`; not in v83: game_rules.md F1) | measured live from the gaps between casts (Part 2) |
| skills on keys, their numbers (MP, damage, mobs hit, box, length, cooldown, a buff's length) | `Keys.attack` q and `basic_attack` c only; `w`, `e` unknown to the code; Skill.img is exported as XML and not built | the profile names the skill on each key; its numbers from Skill.img, **to be built into `assets/mcw`** |
| HP / MP max, level, EXP, job | the HUD; job and level offline | the HUD |
| what a potion gives | not known | measured live: +198 HP, +150 MP |
| **A mob kind:** speed, can jump, can fly, HP, level, EXP, touch damage, knockback threshold, body box per pose, animation lengths | `mob.json` (file), read in four places | the same file, one reader; the top speed checked against what the tracker measures |
| its look-alike poses (one picture, two feet points) | not known | computed from the file: 41 of 128 kinds |
| **The map:** bounds, spawn points, portals, town, the cloud flag | `map.json` (file) | the graph (section 1) |
| **The game:** gravity, fall cap, drag | `Physics.img` numbers in `nav/sim.py`, `brain/moves.py`, config | one place, source `Physics.img` |
| a drop's life 120-130 s, the bob, a new mob's 0.32 s fade-in, a body's `die1` length | `docs/game_rules.md`, PLAN-loot.md | facts with those sources |

---

## 6. Dynamic values: how each is set while running

**One mechanism.** Every reader asks the registry; nobody keeps a copy. A value's change is an event (`fact`) in
the stream, so a recording replays the same values at the same frames. What is computed from facts (the edges
and the seconds table, the reach boxes) remembers which values it was built from and is rebuilt when one moved -
the edges on a worker thread (section 1). No restart, no code edit.
**The profile:** one small file the user edits (keys -> actions and skills with their levels, the weapon), re-read
when it changes; a recording stores it with the session (today `session.json` stores the whole config). OK'd
2026-11-23 "for now"; later a script fills it: the equipment / stats windows opened in the game, the values read
by perception (not part of this plan).

| Value | Changes when | Set by | Evidence that it works |
|---|---|---|---|
| keys -> actions; the skill on each key and its level | a new key layout, a new skill, a skill point | **the profile** (the user), **checked live** against the HUD step each cast shows. Today: q single-target, w multi-target, e mobility | on the capture the step after each key names the skill: q -12 MP on 505 of 512 such steps (Power Strike at its top level), e -35 MP on 79 of 81 (Rush, level 1), w -13 MP and -15 HP on 10 of 10 (Slash Blast); `end` +150 MP, `delete` +198 HP (the potions) |
| a skill's numbers | with its level | the client files, by (skill, level) | game_rules.md F6 lists them |
| the weapon, its type and attack speed | a new weapon | **the profile** (the weapon's id) -> `attacks.json` | - |
| walk speed, jump height and sideways speed, climb speed | equipment, a buff, a level-up | **measured live** from our own motion, starting from the last session's value: the top plateau of our speed while one walk key is held on a floor | 7,867 quarter-second windows in 30 minutes: p50 151.8, p75 154.8, p95 157.3 px/s; 200 jumps; 479 climb windows |
| swing length (so: attack speed, a Booster) | a weapon, a Booster | **measured live** from the shortest gaps between casts | to be shown in Part 2 |
| buffs running, cooldowns | a cast | **a cast seen** + the skill's length | section 2 |
| HP / MP max, level, EXP | play | **read from the screen** every frame | 0 misreads in 110,082 frames |
| what a potion gives; hits to kill a mob kind with a skill | a new potion; damage | **measured live** from the HUD steps and the events | +198 / +150 seen; hits per kill: Part 2 |
| a mob kind's numbers, a map's graph | a game patch | **the client files**: `assets build`, read at load | `changes.txt` |

---

## 7. Derived facts: defined once, computed, not stored
- **Same floor**(a, b): their nodes have one floor number. Comparing node ids is wrong at the 19 level joints
  and nowhere else; a T-joint or a wall joint is not the same floor.
- **Along the floor**(a, b): |x_a - x_b| when on the same floor (a floor never doubles back), else none.
- **Mobs on a floor / a stretch**: the count of living mobs whose node is on it - "how many are there".
- **Seconds to get there**(thing): from our node to the thing's node by the seconds table, plus the walk along
  its floor at our measured speed - "how quickly I can get there". `NavMap.route` gives the exact way when one
  is wanted (1.3 ms on Line 1; not per mob per frame).
- **In reach**(mob, skill): the skill's box from our feet, on the side we face, against the mob's body box
  (`brain/reach.py`'s sure / maybe, per skill instead of per weapon).
- **Age** of a thing, **time left** of a drop (130 s - age), of a buff, of a cooldown.

---

## 8. Stored, for every frame of hours of play
- **Tables, columns by name:** `frame` (one row a frame: the view, us, the HUD), `mob` (one row per mob per
  frame while it is seen; while it is not, a row only when one of its fields changes), `drop` (one row per drop
  = its life, + a row when how it is seen changes), `player` (as `mob`), `event`, `fact`. A header holds the
  schema's version, the map and the facts at the start. **A new field = a new column**: older recordings read
  with its default.
- **Measured** on the 30-minute capture with stand-in rows of these layouts (`size_proto.py`): 110,082 frames ->
  `mob` 446,337 rows of 37 bytes (4.05 a frame), `frame` 49 bytes, `player` 141,373 rows of 17 bytes: **222 bytes
  a frame raw = 48 MB an hour; packed 42 bytes a frame = 9 MB an hour** (the kept replay of the same frames:
  1,344 MB). Positions are whole pixels (the camera and the fit are exact), so 16-bit numbers hold them.
- **In memory, per frame:** the same records as arrays (every mob in one array), so the placement and the
  derived facts run over all things in one call.
- **Cost to fill:** the placement 16-62 us a frame. The tracker's own cost is Part 2's gate: today `world.py`
  takes 0.7 ms p50 / 1.0 p90 and its looks 0.0 / 1.0 ms a frame on Line 1, of 15.1 / 16.8 ms for the whole frame.

---

## Decided by the user (2026-11-23, the four questions this document ended on)
1. **Mobs out of view: 4 s**, then forgotten ("4s ok").
2. **Players: a 1 s cover, nothing more** ("yes 1s enough players move a lot"). **Changed 2026-11-24 to 2 s**
   (PLAN-tracker.md question 5: 29 of 308 player tracks come back under a new number, against 52 with 1 s).
3. **Buffs: cast seen + length, no perception. The hotkeys: every item and its amount on all 8 keys** (Shift, Ins,
   Home, PgUp, Ctrl, Del, End, PgDn), read and tracked - further than potions alone. A step of PLAN-tracker.md.
4. **The profile file: good for now**; later a script that fills it from the game's equipment / stats windows.
5. **The document as a whole: OK'd 2026-11-23** ("I OK it as a whole").

## Commands (from the repo root, `.venv\Scripts\python`)
```powershell
tools\model\nav_audit.py nodes | place | edges | routes     # section 1's numbers (edges: ~2 minutes)
tools\model\chains_fixed.py                                 # the chains built from complete links, the joints left
tools\model\place_footage.py --sound                        # section 2's offsets per kind (13 sound captures)
tools\model\chain_change.py CAP [CAP ...]                   # does a mob change chain, and how
tools\model\lookalike_poses.py                              # one picture under two feet points, per mob kind
tools\model\self_measure.py "20261121_000219_2#0"           # walk / jump / climb, the HUD's steps
tools\model\size_proto.py "20261121_000219_2#0"             # section 8's sizes
```
