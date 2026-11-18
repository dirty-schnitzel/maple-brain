# PLAN: loot, part 1 - PERCEIVE drops
**Status: OK'd by the user 2026-11-17 (proposed the same day by Fable, max effort; plan session: measure +
prototype). NEXT = Session 1. Nothing of it is built in maplebrain/ yet; nothing reads drops until the tracker /
loot-behaviour sessions. The three recordings of section 13 are still to come (the user: soon).**
**Session 1 (2026-11-17): S1-S3 DONE, S4 gate NOT MET on synth (false: 36 window icons; identity: 2 = pictures with
identical opaque pixels) - numbers, pictures and options in HANDOFF "Session 1 state"; the user's call.**
**AMENDED by the user 2026-11-17 (after S4; these override sections 4, 5, 8, 10 where they differ):**
1. **Cash-shop (NX) items are not searched** - they never drop (2,750 of the 3,955 equips; info/cash in the
   export, `cash` in items.npz / items.json): 1,920 pictures searched instead of 4,577. Worn NX gear can no longer
   match at all.
2. **No AIR kind:** kinds are REST / weak. Flights and pickup hops are not needed to perceive loot on the ground (a
   drop is born from REST anyway; gone = the scene shows at its box; who looted = the game's pickup text).
3. **REST needs a ring:** ring >= 0.1 (share of the known pixels around the picture that show scenery / a drop / a
   fit mob / a character box; < 60 known ring px = pass) - a window icon at a foothold's height has the panel
   around it (27 such on synth passed REST without it).
**Session 2 (2026-11-17): S5-S6 DONE, gate MET on Claude's labels (201 frames, 9 recordings): REST 629 / 631 =
99.68 % of the visible resting drops, 0 false REST, 0 wrong identity, 0 of 36 flights / hops REST - HANDOFF
"Session 2 result". NEXT = Session 3.**
**Session 3 (2026-11-17): S7-S9 built (perception/drops.py, FrameFacts v5, in shadow); gates met (tracks SAME, synth,
labels = Session 2's, the 9 recordings = the reference's REST sets on 14,962 / 14,962 frames) and the cost gate
(2026-11-18: perceive p90 on - off +0.41..+0.59 ms on 4 clips, busy +0.46). Section 9's table "keys in <= 8 places" proved wrong (4 pictures unfindable alone): a second
pool for keys in more places, in the same graph - HANDOFF "Session 3 result".**
Executors: Opus (high), three sessions; prompts at the end. Parent plan: PLAN-perception.md (the table's row "Drops:
item icons from the client (later, with loot)"). Branch `loot` off `perception-only`.
Evidence: tools/loot/ (E-L0 .. E-L13, each file's docstring says what it measures) on the 9 native PNG recordings;
raw tables in runs/loot_plan/ (rules2_v4.txt, seen_v4.txt, life_v4.txt, anchor_v4.txt, find_v4.log, residue_v4.log),
per-frame results in RUN/loot/find_v4.jsonl (v4 = the rule of section 5; v3 = before its FRONT term).

## 1. The answer in short
- **A resting drop is pixel-exact**: the client draws the item's `info/iconRaw` 1:1, opaque, at integer positions.
  So the mob fit's exact-colour vote (perception/vote.py, unchanged) finds drops when its "poses" are item pictures.
- **Search every picture, not a per-map list**: 4,597 distinct pictures (every Etc / Use / Setup item, every equip,
  the meso frames) in ONE table built once at start. 0 wrong identities with every picture pasted on real frames;
  it costs ~0.2 ms more than a list of 11 items (the pass has fixed sizes). Drop tables are server-side: nothing to
  maintain per map, a rare equip is seen the first time it drops.
- **Three things look like a drop and are not** - worn equipment (an equip's icon shares pixels with the worn
  sprite), item icons in game windows (inventory, quickslots), an item that is part of a mob (Stirge Wing on a
  Stirge). One rule built from facts of the frame drops all of them (0 of 3,893 such sightings kept) and keeps
  97.9 % of the sightings of resting drops (the rest are covered ones).
- **Scenery in front of a drop must count as cover, not as "no drop"** (a ladder's top post hid two drops for 123
  frames): found by the independent look, now a term of the rule.
- **Cost: +0.6 .. +1.05 ms p90 beside the mob fit** as one fixed-size GPU graph on its own CUDA stream (prototype,
  same drops as the reference on 450 / 450 frames). A plain second vote costs 3.4 ms, a numpy reader thread 3.7 ms.
- Not answered by today's footage: how a drop EXPIRES (the longest one lay 122 s). New footage: section 13.

## 2. What was measured (2026-11-17; 9 recordings, 14,962 saved frames with a scene camera, 5 maps)
Ant Tunnel IV (154819_1, 092718_1, 012059_1 = the user playing; 094333_1, 111248_1 = hunts), Dangerous Steam, Line 1
<Area 1>, Transfer Area, Dark Cave (16 s). The pet (Snail) is out in the Ant Tunnel IV / Line 1 ones.
| # | Question | Result |
|---|---|---|
| E-L1 | The client's item pictures as vote material (exp_palette.py) | 4,771 pictures (358 Etc, 202 Use, 240 Setup, 3,955 equips, 16 meso frames); 29x29 px p50 (max 44x44), 506 opaque px p50, soft-alpha px 5.7 % of the drawn ones; **6,103 colours in all**; 401 two-by-two features a picture p50, 954 k distinct keys, **1 place per key p50** (p99 14). 174 pictures are pixel-identical to another (4,597 distinct); 24 have < 16 usable features (see-through: glasses, nymph wings, Piece of Ice, Arwen's Glass Shoe, "Transparent ..." cash items). `icon` = `iconRaw` + 1-5 shadow rows (545 of 560 Etc + Use differ) |
| E-L2 | Do frames show them exactly? (exp_find.py: the vote + a per-pixel check, every picture) | Yes. Resting drops: SEEN share of the opaque pixels p50 1.00; junk candidates sit at 0.1-0.2. 79,079 loose sightings, 322 resting drops |
| E-L4 | Identity over ALL pictures (exp_synth.py, pasted on real frames) | alone: 5,106 / 5,134 = 99.45 %, **0 wrong identity** (the 28 misses = see-through pictures); piles of 3: 99.13 % of 15,400, >= 97.8 % from 40 % visible; under an unknown cover: >= 97 % from 30 % visible |
| E-L5 | Independent look: what stays in one map place and is NOT named? (exp_residue.py: scene residue minus drops / mobs / characters, joined over time; run on all 9 recordings, sheets looked at for 154819_1, Dangerous Steam, 111248_1, 012059_1) | **One miss class: drops behind front scenery** (a ladder's top post, 111248_1, 123 frames) -> the FRONT term of section 5. One capsule-like object nothing names (154819_1) = another player's NX cosmetic, not loot (the user; section 12). The rest: the game's own text lines, the cursor, a UI icon, the pet, held weapons, damage digits |
| E-L8 | Which facts tell a drop from a look-alike? (exp_rules2.py, classes by behaviour only) | section 6 |
| E-L9 | A drop's life (exp_life.py) | section 3 |
| E-L10 | By eye, whole frames (exp_eye.py) | 3 frames (Ant Tunnel IV hunt, Dangerous Steam, Line 1): 26 drops, all boxed, 0 wrong boxes; the open inventory (012059_1 t 85.4): 17 window icons all dropped, the 11 ground drops kept |
| E-L7 | Cost beside the fit (exp_time*.py; pinned, only `watch` running, A/B in one process) | section 9 |

## 3. What a drop looks like (question 1)
**Picture.** `info/iconRaw` (no shadow), drawn 1:1 and opaque. Mesos: Item/Special/0900.img 09000000..3 (bronze,
gold, bundle, sack), 4 frames each, ~0.1 s a frame (0.4 s a turn; no delay in the file = the client's default),
frame 3 is the coin edge-on (5 px wide). Windows draw `icon` (with the shadow) - the same pixels plus rows below.
**Resting** (141 drops with >= 60 clear sightings; 51,016 sightings of the rest class):
- x never changes. The picture's BOTTOM sits 1..5 px below the foothold's y (at the picture's centre x) at the
  bob's lowest point on all 141; **box bottom - foothold y is within -7..+5 on 99.7 %** of the sightings of
  everything that stays at one x and bobs (38,607 in find_v2, before height was part of the class; the exceptions
  are hats of two idle players, 27 and 42 px up). The file's origin does not place a drop (0..15 px spread): a
  drop's "feet" = the picture's bottom-centre.
- bob: 5-6 px up and down on 173 of 212 drops (7-11 px on the rest: not looked at), **period 2.00 s** (p10 1.95,
  p90 2.05), about a quarter of the frames at each end.
- opaque from the first to the last resting frame (no fade-in).
**Flight in** (191 flights): 0.99 s p50 (p90 1.18) from the first sighting to rest, apex 99 px above the foothold
(p90 104), x travel p50 10 / p90 33 / max 160 px. Mob death (the tracker's first dying tick) -> the drop rests:
**1.25 s p50** (p10 0.78, p90 1.51; 230 drops); landing x - death x: -77 .. +59 px (p5 .. p95). **Items SPIN in
flight** (~0.6 s a turn, by eye): exact only when upright = 1 sighting a flight p50; mesos do not spin: 11 p50.
**Pickup** (188 drops went while in view, 167 showed it): a hop toward the looter at full opacity - last exact
sighting 0.41 s p50 after the last resting one (p90 0.50), 33 px up (p90 51), |dx| 30 px p50 (p90 66) - then a
fade of ~0.15-0.2 s (by eye, one case: 154819_1 t 65.9-66.5). The drops that went while in view had lain 2.5 s
p50 (p10 0.4, p90 37.1).
**Expiry: not seen.** The longest drop lay 122.0 s (a Dexterity Potion, 094333_1 t 27.5-149.5) and went while in
view - a timer or a pickup, the footage cannot say; three drops of 111248_1 aged 112.6 / 112.5 / 74.1 s went
within 0.2 s of each other = a pickup, not a per-drop timer. -> section 13.
**Draw order** (by eye on the frames looked at + the data): a drop is over mobs, players, pets and death effects;
under damage digits, front scenery of its foothold's layer (a ladder's top post), the game's windows / tooltips /
megaphone bars / chat balloons / minimap / quickslots; a later drop is over an earlier one (piles: 2-4 items
14-30 px apart, the lower ones 30-75 % hidden). Name tags: not settled.
**How often is a known resting drop seen?** Between its first and last resting sighting, on the frames where its
box is in view and in the world (71,424 drop-frames): REST 95.5 %, a weak sighting 0.7 %, nothing 3.7 %. Half of
the unseen frames sit in 14 stretches longer than 5 s, and by eye those are my offline joining (two drops of one
item landing at one x: the place is empty in between); counting only stretches under 1 s, REST is 98.4 %. What
hides a drop there (40 random cases by eye): an item tooltip, a megaphone bar, a chat balloon, the pile's top
item, damage digits. A lower bound either way: the labels give the recall on VISIBLE drops.
**Per frame:** loose sightings 5 p50 / 12 p90 / 32 max; candidates 8 / 16 / 38; item-coloured features 13.4 k /
20.8 k / 33.9 k.

## 4. Which icons to search (question 2)
What actually dropped (resting drops by map): Ant Tunnel IV - mesos (bronze, gold), Horny Mushroom Cap, Charm of
the Undead, Orange / Blue / Red / Dexterity Potion, Arrows for Bows / Crossbows, Fragment of Magic, Bronze Ore;
Dangerous Steam - meso, Stirge Wing, Iron Ore, Fragment of Magic (+ the two mushroom items, Orange Potion);
Line 1 - meso, Bubbling's Huge Bubble, Red Potion; Transfer Area / Dark Cave - meso, Stirge Wing. 16 items + 2
meso sizes in 17 min of footage; no equip dropped.
| Option | Verdict |
|---|---|
| **all pictures by exact colour** | **chosen.** One palette LUT (6,103 colours, int16 ids) + one table (1.59 M entries, 953 k keys; built in 1.1 s once per process, not per map). 0 wrong identity. Beside the fit: +1.07 / +1.04 ms p50 / p90 on the busiest stretch |
| a learned set per map | no: it misses the first drop of a kind (the rare ones are the valuable ones), needs upkeep per map, and saves 0.2-0.3 ms (+0.90 / +0.75 with 11 items + mesos, same stretch) |
| mesos + a short list | no: the same, worse |
Pictures that look the same are one class (174 pictures duplicate another; mesos first: "Shumi's Coin" = a gold
meso frame): the finder reports the class's lowest id, `items.json` lists the class. 257 items have no picture of
their own (their icon is a link to another item's: 43 Etc, 214 Use = scroll families): the export must resolve the
link.

## 5. The design
```
at start (once): items.npz + items.json (assets build) -> DropFinder: palette LUT, feature table, pictures on the GPU
per tick (clean map, scene camera found; inputs the tick already has: frame_u8, expected(C), known, the UI mask)
 1 VOTE    palette id per pixel where the scene does not explain it (the fit's own mask) -> 2x2 id blocks ->
           the table's (picture, place) cells -> exclusive votes -> the best NC cells (>= 16 votes)
 2 CHECK   per cell, the picture against the frame, pixel by pixel:
             SEEN    opaque pixel shown exactly (+-4)
             FRONT   not SEEN, under front scenery of the drop's layer (Scene.layers, as the mob fit's valid mask)
             ABSENT  not SEEN, not FRONT, and the scene shows there
             COVERED the rest                                + the picture's 2 px ring: what is around it
 3 PICK    greedy by SEEN; an accepted drop's pixels are taken; a later one's unseen pixels under it = "under a drop"
 4 FACTS   per accepted cell: item, box, feet, the counts, the foothold under it, kind REST / AIR / weak
```
1-2 run as ONE fixed-size GPU program (section 9); 3-4 on the CPU after the mob fit (they use its explained pixels).
(The vote's bar: section 6's data was made with 12 votes, the timed graph with 16 - 16 keeps candidates at 8 p50 /
16 p90 a frame and clears repeated UI lines; S4 re-scores at 16.)
**The loose rule** (a sighting at all): >= 40 SEEN px, SEEN >= 25 % of the opaque pixels on screen, ABSENT <= 15 %.
**The kinds** (what a consumer may trust):
- unexplained cover `u` = 1 - (SEEN + ABSENT + under an accepted drop + FRONT) / opaque; `mob` = share of its SEEN
  pixels the mob fit's accepted mobs explained; `dy` = box bottom - the foothold's y under the box centre; `ring` =
  share of the ring's known pixels that show the scene, a drop, a fit mob or lie in a character's body box (our
  tag, players' tags).
- FRONT was found by the independent look (E-L5): a meso and a Charm lay behind a ladder's top post for 123 frames
  of 111248_1 and were dropped - without the term a pixel hidden by scenery IN FRONT of the drop reads "the scene
  shows here" = ABSENT. The drop's layer = its foothold's (map.json `layerId`), front = the tiles / objects of the
  layers above (the planes the mob fit already loads). **FRONT counts as explained cover only at the resting
  height**: in the air the foothold below says nothing about the thing's layer (counted there too, one worn hat
  passed as AIR for a frame). With it: +2,992 loose sightings, that platform's drops seen on 98.85 % of their
  frames (t 20-45), no gap over 0.4 s.
- **REST**: u <= 0.2, mob < 0.5, dy in -7..+5. A drop lying on the ground: what a tracker starts drops from.
- **AIR**: u <= 0.2, mob < 0.5, not at the resting height, ring >= 0.3 (no ring = pass). Flying in / being picked
  up: hints, never a birth.
- **weak**: the rest (covered by something unknown, worn gear, window icons): only confirms a drop already known.
Why each term (section 6): `u` removes worn gear (its unseen part is the wearer, never a drop), `mob` removes mob
parts, `dy` + `ring` remove window icons; a pile's lower items stay REST because "under an accepted drop" is
explained cover.
**Not in this plan:** drop tracks, looks at known drops, anything that presses a key (section 10).

## 6. Evidence for the rule (exp_rules2.py, find_v4: 14,962 frames, 79,079 loose sightings)
Classes by behaviour only (no eye): rest = a group on >= 20 frames, x fixed, y bobbing 3..8 px, at the resting
height; flight / pickup = the same item's short groups just before / after a rest group; screen = fixed on screen
while the camera moves (UI); worn = an equip not at rest; other = the remainder (91 % of it is at the resting
height: resting drops seen too briefly for "rest").
| class | sightings | SEEN p5 / p50 | u <= 0.2 | at the resting height | ring p5 / p50 | REST | AIR | dropped |
|---|---|---|---|---|---|---|---|---|
| rest (247 drops) | 51,016 | 0.55 / 1.00 | 97.9 % | 100 % (by the class) | 0.51 / 1.00 | **97.9 %** | 0 | 2.1 % |
| flight | 1,215 | 0.40 / 1.00 | 82.4 % | 16.6 % (landing) | 0.40 / 0.99 | 16.6 % | 62.6 % | 20.8 % |
| pickup | 337 | 0.44 / 1.00 | 92.6 % | 3.0 % | 0.53 / 1.00 | 3.0 % | 88.1 % | 8.9 % |
| worn equips | 1,676 | 0.27 / 0.32 | **0.0 %** | 1.7 % | 0.06 / 0.65 | **0** | **0** | 100 % |
| window icons (inventory, a quickslot) | 1,867 | 0.26 / 0.36 | 39.6 % | 1.2 % | 0.00 / 0.00 | **0** | **0** | 100 % |
| mob parts (`mob` >= 0.5; inside "other") | 350 | 0.58 p50 | - | - | - | **0** | **0** | 100 % |
| other | 22,955 | 0.48 / 1.00 | 97.2 % | 91.0 % | 0.41 / 1.00 | 90.2 % | 6.0 % | 3.8 % |
- u bar: 0.15 keeps 97.3 % of rest, 0.20 97.9 %, 0.25 98.2 % but lets 23 worn sightings in, 0.40 lets 224 in.
- Worn gear seen: Red Starry Bandana (SEEN up to 0.63), Bunny Earmuffs, Blue Pajama Hat, Dark Devil Hat, Fish
  Spear, Zard, a face accessory once at 0.64.
- Mob parts: Stirge Wing on flying Stirges, SEEN 0.58 p50 (350 sightings on 3 maps) - `mob` >= 0.5 on all of
  them, all dropped; the 105 other Stirge Wing sightings the rule keeps were looked at by their numbers: wings
  lying under a coin (SEEN 0.52-0.69, the rest under the accepted coin) and their pickup hops. The Charm of the
  Undead shares 18 px with the Zombie Mushroom's talisman (harmless).
- Ring: counting only scene + drops, resting drops in front of a mob / player read p1 0.05 (a bar of 0.3 on that
  ring cost 6 % of them); with fit mobs and character boxes counted p1 0.19, p5 0.51. REST needs no ring bar on
  this data (a bar of 0.1 would cost 0.5 %, 0.3 1.5 %); the fact is recorded for the tracker.
- 13 "screen" sightings kept as REST are real resting mesos of 111248_1 seen at one screen spot at two moments
  (the class's artifact, not UI).
- A flat-colour match exists (Maria's Letter on a white hit burst, SEEN 0.49, 80 sightings): weak on every one;
  the count of fully SEEN features (`n_fseen`) is recorded as the lever if labels show one that is not.

## 7. Truth and gates (question 3)
1. **By-eye labels** (Session 2; reference = Claude's labels, memory "reference-claude-labels"): ~200 frames picked
   from the 9 recordings (tools/loot/labels/pick.py: even + hard - kills in flight, pickups, piles, players wearing
   matched gear, a window / tooltip / chat bar over drops, the open inventory, drop-free stretches of every map).
   Candidates on the sheets = the scene's residue patches (never the finder's boxes); per frame: drops [feet x, y,
   class, item name when readable] with classes clear / pile (visible share by eye: >= 50 %, < 50 %) / effect
   (digits, skill effects over it) / ui (a window, tooltip, chat bar, minimap over it) / flight / pickup / unknown
   picture; and not-drops [worn, window icon, mob part, other]. -> RUN/loot/labels.json + a copy in
   tools/loot/labels/, tools/loot/drop_eval.py (recall per class, false per class, identity).
2. **Synthetic frames** (Session 1; tools/loot/synth_drops.py, as tools/perc/synth/ does for mobs): base = real
   frames with their drops erased to the expected scene; pictures drawn as the client draws them - bottom on a
   foothold at every bob offset, piles (2-4 items 14-30 px apart), in front of mobs and players, under damage
   digits (BasicEff), under a UI rect, at the screen edges, mesos on a flight arc; distractors that are NOT drops:
   window icons (`icon` on a panel), pictures pasted on players' heads at 30-65 % visible, a Stirge with its wing;
   50 drop-free frames; every picture of the catalogue at least once. Truth by construction; a 40-frame fixture in
   pytest.
3. **Gates** (as 3.2's):
   - recall: REST >= 99 % of the labelled and of the synthetic resting drops that are VISIBLE (clear, pile >= 50 %
     visible); pile < 50 % / effect / ui reported, not gated (the tracker's job); see-through pictures listed, not
     gated.
   - false: 0 REST and 0 AIR on the drop-free frames and on every not-drop (worn, window icon, mob part) of labels
     and synth.
   - identity: the item's picture class right on 100 % of the found synthetic drops, on every labelled drop whose
     item is readable.
   - position: feet within 0 px on synth, the bob offset exact.
   - cost: the tick with drops on vs off, bench A/B in one state, pinned, game running, nothing else of ours:
     **+<= 1.0 ms p90**; gate replay: the SAME tracks on all 6 clips.
4. The prototype's own numbers on these gates = Session 1's "before" (tools/loot/dropvote.py is the reference
   implementation; the product must give the same drops on the fixture).

## 8. FrameFacts (question 4): v5 `drops`, in shadow
`drops: list | None` (None = not run this tick: no scene camera / no finder) + `drops_ms`. One dict a sighting,
frame facts only:
| key | what |
|---|---|
| `item` | the picture class's lowest item id (9000000..3 = meso by size); name / kind / the class's other ids in items.json |
| `f` | meso frame 0-3 (0 for items) |
| `box` | x, y, w, h of the picture on screen |
| `feet` | the box's bottom-centre (what rests on the foothold) |
| `kind` | "rest" / "air" / "weak" (section 5) |
| `n_op`, `seen`, `absent`, `under`, `front` | opaque pixels on screen, SEEN, ABSENT, unseen under an accepted drop, unseen under front scenery -> covered share = 1 - seen / n_op, unexplained cover = 1 - (the four) / n_op |
| `mob`, `ring` | SEEN pixels the mob fit explained; [ring pixels explained, known] |
| `dy`, `fh`, `layer` | box bottom - the foothold's y under it, that foothold's id and layer (None: nothing under it) |
| `votes`, `n_fseen` | exclusive votes of its cell; features fully SEEN |
**first-seen is not a frame fact** (FrameFacts hold no memory): it is the first frame a drop's track has a REST
sighting = the tracker's field. If you want it in ticks.jsonl before the tracker exists, say so: a 20-line stamp
by (item, map x, foothold) can sit in the Perceiver beside the facts - it is a track by another name.
v1-v4 records still read; the replay rows carry `drops`; nothing reads it.

## 9. Cost (question 3's target: <= 1 ms p90 beside the fit)
Measured 2026-11-17, pinned to the performance cores, only `watch` running, game up, expected() not counted (D's),
the mob fit alone 3.7-4.1 ms p50 in the same loop (tools/loot/exp_time*.py):
| How the drop pass runs | Busiest stretch (094333_1 t 100-140, 12 drops a frame) | Dangerous Steam / Line 1 |
|---|---|---|
| a second vote + check, eager (dropfast.py; not a clean state) | +3.4 ms (vote 1.55, check 1.02, pick 0.65) | - |
| numpy on a reader thread (dropcpu.py; same drops on 40 / 40 frames; not a clean state) | 8.0 ms in the thread, tick +3.7 | - |
| ONE fixed-size graph, in line on the main stream | +2.0 / +2.0 ms p50 / p90 | +1.6 / +1.7 |
| **the same graph on its own CUDA stream, launched before the fit, read after it** | **+1.01 / +1.05** | **+0.60 / +0.64, +0.62 / +0.69** |
| ... with half the table and fewer slots (4 places a key, 32,768 slots) | +0.91 / +0.85 | +0.56 / +0.61, +0.49 / +0.46 (ant4 clip +0.44 / +0.42) |
The graph (dropgraph.py): fixed sizes replace the vote's data-dependent ones - NF 49,152 feature slots (cumsum +
scatter compaction), the table's keys with <= 8 places (82 % of its entries), a sort of NF x 8 cells, exclusive
votes, the best 64 cells, their check - one CUDA graph, one launch, one small download. Its GPU time is ~1.3 ms;
on its own stream it overlaps the fit's launch-bound gaps, so the tick pays the main thread's part: launch 0.25 ms
(4 copies + the explained mask - the fit already computes that mask), fetch 0.07, pick 0.08-0.48 (numpy, grows
with the drops on screen). **Same drops as the eager reference on 450 / 450 frames** (3 clips); with 4 places / 32 k
slots 14 / 6 / 0 / 10 loose sightings of 150 frames each are lost (pile items) and Dangerous Steam overflowed the
slots once (33,197 features).
Not in the timed graph yet: the FRONT term (per candidate one more gather of 48 x 48 from each foothold layer's
front plane - 1 to 5 planes on these maps - and one count each; the pick takes its layer's) - S7 measures it.
Levers left, in order: the fit hands over its explained mask (-0.1); the pick vectorised or its counting moved
into the graph (-0.3 at 12 drops); 4 places a key where recall allows. Fallback if the gate fails live: the pass on
every 2nd tick (drops rest for seconds; a flight lasts 1.0 s) - the user's call, not a default.
GPU memory: the prototype holds 480 MB (174 MB of it are the Voter's fade tables, which drops never use; the
pictures are stored three ways): expect ~250 MB. Build 1.9 s + graph capture 0.15 s, once per process.

## 10. What the next sessions need (not built here)
**The tracker plan (running in parallel):**
- sightings: `drops` per tick; REST = evidence a drop lies there; weak at a known drop = COVERED; nothing + the
  scene showing at its box = ABSENT (gone). A LOOK at a known drop = the same check at its box x 7 bob offsets
  (rows in the same graph: no new machinery, same pattern as Fitter.look).
- association: picture class + map x (exact) + foothold; identical items lie 14-30 px apart in a pile, sometimes
  2 px (two caps: the lower one 75 % hidden).
- motion model: rest = x fixed, feet y = foothold + 1..5 at the lowest, a 5-6 px bob with a 2.00 s period (the
  phase is readable from 2 frames); flight in ~1.0 s, apex ~100 px, lands within -77..+59 px of the death, 1.25 s
  after the first dying tick; pickup = a hop of ~32 px toward the looter in ~0.4 s, then a 0.15-0.2 s fade - its
  direction says who took it (us, the pet, a party member).
- birth: a REST sighting (or an AIR chain that lands); never AIR alone, never weak. Camera-fixed sightings are UI.
- a drop's facts for consumers: item class + name + kind, meso size (bronze / gold / bundle / sack), map position,
  foothold -> the nav platform, first / last seen, in view, covered / gone, linked kill (time + place fit a death).
- expiry time and look: unknown (section 13); ownership: every drop seen is ours or our party's (the user's fact).
**A later loot-behaviour session:** reach (platform + route seconds to the drop), the pickup key's range (measure:
the user's presses vs the distance at pickup), the pet's radius and delay (with it out a drop near us lives 2.5 s
p50: wait or walk?), pick up vs fight (value: meso size, item class; mobs in reach), a full inventory. The game
itself writes every pickup as text at the right edge ("Stirge Wing x1 earned. (Etc)", "You have gained mesos
(+47)") and shows the meso total in the inventory: a text reader there is the loot account (and the check that a
pickup worked). Out of scope here.

## 11. Steps (each: pytest + the 'bot speed' line; no live behaviour changes in any session)
**Session 1 - data + synthetic truth + the eval tool (no maplebrain/perception code)**
- S1 export: tools/cwdata/export.ps1 gets the item section (tools/loot/export_items.ps1 is the working draft):
  `Item\png\<8-digit id>_raw.png` for every Etc / Consume / Install item and every equip of Character\<slot>
  (Accessory, Cap, Cape, Coat, Glove, Longcoat, Pants, Ring, Shield, Shoes, Weapon), the meso frames
  `0900000<n>_raw_<f>.png`, `Item\items.json` (kind, name from String Etc / Consume / Ins / Eqp, size, origin,
  frame delays); **icon links (WzUOLProperty) resolved** to the target's picture (257 items; the draft skips them).
  `icon` is not exported (windows only).
- S2 `assets build` (gamedata.py): `assets/mcw/items/items.npz` (pictures packed: 2.2 MB) + `items.json` (id ->
  name, kind, w, h; `same` = its picture class's lowest id; `weak` = fewer than 16 usable features); changes.txt
  line; assets/README.md. Gate: 4,771 + 257 linked items, 4,597 distinct pictures (+- the links' new ones: say the
  number), the 24 weak ones listed by name; a test that every picture loads and the classes are stable.
- S3 tools/loot/synth_drops.py + its 40-frame pytest fixture (section 7.2), tools/loot/drop_eval.py.
- S4 "before": the prototype (tools/loot/dropvote.py with the kinds of section 5, reading items.npz) on the synth
  set -> per case recall / false / identity. **Session gate: section 7.3's recall, false and identity gates on
  synth. A gate fails -> stop with the numbers and the misses' pictures.**
**Session 2 - by-eye labels**
- S5 tools/loot/labels/pick.py + sheets (residue patches lettered, 3x tiles), the judgments file, labels.json
  (section 7.1); ~200 frames, every recording.
- S6 drop_eval on the labels with the prototype's find_v4-style output re-made from items.npz: recall per class,
  false per class, identity; every miss and every false looked at (sheets). **Session gate: section 7.3 on labels.
  Fails -> stop with the cases; a rule change is the user's call.**
**Session 3 - the product, in shadow**
- S7 `maplebrain/perception/drops.py`: `DropFinder` (items.npz -> perception/vote.py's Voter with item pictures
  as poses, tints off, no fade tables; the fixed-size pass of tools/loot/dropgraph.py as a CUDA graph on its own
  stream, + the FRONT counts per foothold layer; `launch(frame, expected, known, ui, explained, C)` / `fetch() ->
  [dict]`; the pick + kinds with the fit's taken pixels, character boxes, the map's footholds and layers). tests/test_drops.py on the fixture: the same drops as the
  reference, kinds, feet exact, drop-free frames empty, every catalogue picture found alone.
- S8 wiring (perceiver.py, where the fit runs): one DropFinder per process (built in runner setup, not per map;
  `warm()` captures the graph), launched right after `expected()`, fetched after `_fit_mobs`; FrameFacts v5
  (`drops`, `drops_ms`), part `drops`; config `perception.drops` (default on); the replay rows carry it. Nothing
  reads it.
- S9 gates: full gate.py SAME tracks on 6 clips; bench A/B drops off / on (alternating, 3 rounds, pinned, game
  running, nothing else of ours) **+<= 1.0 ms p90**; drop_eval on synth + labels through the Perceiver's own rows
  (section 7.3); the facts on the 9 recordings = the reference's REST / AIR sets (differences listed). HANDOFF +
  one line in PLAN-perception.md. Then the user's optional live check: one `serve --observe --frames-png` minute.
  **The cost gate fails -> stop with the parts' ms and section 9's levers; cadence is the user's call.**

## 12. Risks and open points
- **The capsule is not loot** (the user, 2026-11-17: "an NX cosmetic item from another player, it's not loot
  100%"): 154819_1 t 54.5-64.2, map (2319, 1594), a white capsule with an Orange-Mushroom face, ~44 px, staying in
  one map place and bobbing like a drop for 10 s (runs/play/20261116_154819_1/loot/strip_capsule.png); no item
  icon matches it, so the finder rightly says nothing. Lesson kept: "stays put and bobs" alone is not a drop -
  other players' cosmetics do it too; a drop is a NAMED picture at the resting height. Session 2 labels such
  things as not-drops; tools/loot/exp_residue.py stays the tool that lists what is unnamed.
- See-through pictures (24 of 4,597) cannot vote: listed at build (`weak`), reported, not searched. If one matters
  (Piece of Ice is a mob drop elsewhere): the fade machinery's un-blend with the picture's alpha - later.
- Drop effects exist (Effect/DropItemEff.img: sparkles in front of / rings behind special drops; the Fragment of
  Magic on Dangerous Steam has one and still reads 404 / 404): a heavy one would read as cover.
- Worn gear that is >= 80 % its own icon would pass `u`; it can only become AIR (hands and heads are not at the
  resting height), never REST. The labels' not-drop class watches it.
- A window icon exactly at a foothold's height with its ring on the scene: not seen in 1,867; the tracker's
  camera test (UI does not move with the map) is the second line.
- The pass' fixed sizes: more than NF features on a frame drops the last ones in scan order (the bottom rows);
  `feat` is in the facts' ms - S9 lists every overflow frame; 49,152 held on all footage (max 33,865).
- A second CUDA stream beside the Lie Detector / tag looks and the game's own rendering: measured offline only.
  S9's bench and the live minute decide.
- Party play: a party member's drops are visible and theirs to take too (the user's fact) - a behaviour question.
- Maps without a clean scene / a lost camera: no drops that tick (as mobs).

## 13. New footage to record (each `serve runs\play --observe --frames-png`, native window, `watch` running)
1. **Expiry, ~5 min, pet OFF:** Ant Tunnel IV on a quiet channel; kill 4-6 mobs on one platform, do NOT pick
   anything up, then stand so the drops stay on screen and wait until every one of them is gone by itself. Say
   afterwards if anyone else was near. (Answers: lifetime, what expiry looks like, whether drops become
   everyone's.)
2. **Our own pickups, ~2 min, pet OFF:** hunt and pick up with the key as you normally do, some drops from a few
   steps away, some from directly on top. (Pickup range and what our own pickup looks like - for the behaviour
   session; also the first pet-off frames with drops left lying.)
3. **Windows over the world, ~1 min, standing in a spot with drops on screen:** open and close in turn - inventory
   (each tab), equipment, the skill window, a shop NPC if one is near, hover an item for its tooltip.
None of the three blocks Session 1 (data + synthetic truth). Session 2 (labels) takes them into its picked frames
when they exist (3 = its window-icon class); 1 and 2 feed the tracker and the loot-behaviour sessions.

## 14. Prompts
**Session 1 (Opus, high):**
```
Loot rework part 1 (perceive drops), Session 1. Work in the git worktree C:\Users\Yoav\dev\maple-loot (branch
`loot`, pushed; its assets\scene and runs are junctions to maple-work's) - NOT in maple-work. Read its HANDOFF.md
top to bottom, then PLAN-loot.md (I OK'd it on 2026-11-17): execute its "Session 1" (S1-S4) exactly.
tools/loot/export_items.ps1, dropvote.py, exp_synth.py, lootlib.py are the working drafts / reference; the memory
cw-client-data-harepacker has the export procedure (BMS key, DOTNET_ReadyToRun=0). No code in
maplebrain/perception, nothing on the live path. Budget matters: be terse.
Gates as written (S2's counts; S4: section 7.3 on synth). A gate fails or a design point proves wrong on the data ->
stop and tell me with numbers; no change of course without my word.
Rules: Python = ../auto-maple/.venv; `watch` is running - never stop it; no live / scripted input; no sed on repo
files (CRLF: Edit, or byte-safe Python); long jobs with run_in_background; pytest + the 'bot speed' line; commit +
push on this branch; numbers into HANDOFF.
```
**Session 2 (Opus, high):** the same header with "Session 2 (S5-S6): the by-eye labels (you judge the sheets; the
reference is your labels, never the finder's output) and drop_eval on them", + "stop at the session gate with every
miss and every false as pictures".
**Session 3 (Opus, high):** the same header with "Session 3 (S7-S9): the product in shadow", + "time only with the
game running, pinned, A/B alternating in one state, nothing else of ours running; full gate.py before the commit;
FrameFacts v5; then HANDOFF + one line in PLAN-perception.md and wait for my live check".
