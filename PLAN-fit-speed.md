# PLAN: the fit's speed - exact-colour voting replaces the least-squares search
**Status: OK'd by the user 2026-11-17 (proposed by Fable, max effort; review of 3.2's speed blocker).**
Executors: Opus (high), two sessions; prompts at the end. Parent plan: PLAN-perception.md step 3.2; state: HANDOFF
"Step 3 state". Evidence: tools/perc/redesign/exp_vote.py (E9) + exp_exact.py / exp_fade_exact.py / exp_tint.py.

## 1. The review: why the fit is slow and why tuning it will not fix it
The fit at 7744b1d: 62 / 116 / 200 ms p50 (synth / real busy frames / Dangerous Steam) against a 5 ms target; it
replaces ~10 ms (whole-screen search) + 6 / 20 ms (find_near).
- Stage 1 asks, for EVERY candidate feet position x EVERY pose, a least-squares question over the whole sprite box:
  54 k values gathered per position (75x72 px x 10 channels), 34 k positions on a real frame, 870 k with flyers.
  That is 49 ms of gathers + ~45 ms of Python around them; stage 2 then checks ~700 candidates (11 ms) because the
  least-squares ranking is not sharp.
- The options I offered ((b) selection on the GPU, (c) skip thin windows, (e) track windows first) remove the Python
  and some positions: estimated 25-40 ms on real frames, flyers still far off. Approximating the sums (every 2nd
  pixel) gives 2x. Neither reaches 5-10 ms: the cost is in the QUESTION (positions x poses x pixels), not the code.
- The least-squares rank is also the accuracy limit: a mob 16-40 % visible ranks 16th-6576th in its window (the 4
  synthetic misses, player 98.2 % / effect 97.8 %).
- The formulation never used the strongest fact step 0 gave us: at native 1366x768 the picture is EXACT.

## 2. What was measured for this plan (2026-11-17, all on native PNG)
1. **Colours are bit-exact.** 369 clear mobs of 012059_1, 827 k opaque sprite pixels: frame colour = sprite colour
   (difference 0) on 98.57 %; the rest is covered (+-1..8 on 0.03 %). Not "within +-4": equal.
2. **Palettes are tiny, sprites are dithered.** Horny Mushroom 77 colours over all poses, Zombie Mushroom 134, Stirge
   14, Bubbling 60. Most 2x2 pixel blocks are not one flat colour (Horny ~1350 such blocks per pose of ~1970 px,
   Zombie ~1900, Stirge 300-400, Bubbling's opaque part 170-430), and a block's 4 colours occur in 2 places (median)
   over all poses of the map.
3. **Fading is exact too.** 161 real fading mobs: |I - (B + o (s - B))| = 0 on 90.1 % of the pixels, <= 1 on 95.7 %
   (rest covered), ONE o per mob. Respawn waves fade in together (n3642: every mob on screen at o = 0.98).
4. **The blue "hit" mobs are frozen mobs: an exact per-channel multiply** - frame = sprite x (B 255, G 168, R 10) /
   255, 100 % of the opaque pixels follow one colour -> colour map. Neither today's fit nor the vote sees them yet;
   a tint is just more palette colours.
5. Sprite alpha is binary for Horny / Zombie / Stirge (100 % opaque); Bubbling is 40 % opaque + 4 alpha classes.

## 3. The design: let the frame's pixels vote (E9, tools/perc/redesign/exp_vote.py)
Work ~ the sprite-coloured pixels on screen, not positions x poses x sprite pixels. No windows, no footholds, no
"air" case: a flyer or a falling mob costs nothing extra.
1. **Palette id per pixel**: one LUT lookup of the frame's 24-bit colour (0 = not a sprite colour of this map).
2. **Feature** = a 2x2 block of ids, all sprite colours, not one flat colour. A table built at load from the map's
   sprites lists, per feature key, where it occurs: (pose, facing, offset to the feet). Keys with > 64 places dropped.
3. **Vote**: every frame feature votes for the (pose, feet) cells its key allows.
4. **Exclusive votes**: a feature counts only for the best-voted cell it supports. The other poses / offsets that
   share part of a mob's picture lose their votes; ~1 cell per mob stays (p50 4 / max 20 cells a frame on synth,
   7 / 27 on real frames - instead of ~700 stage-2 candidates).
5. **Fading mobs**: the pixels the scene does not explain and that are no palette colour ("residue") are un-blended,
   s' = B + (I - B) x 255 / alpha; the alpha at which many adjacent residue pixel PAIRS of one 48 px screen cell
   become colour pairs that occur in a sprite is a fading mob's alpha -> un-blend the residue with it -> palette ids
   (+-2 levels) -> 2-4. (Per-pixel "some colour at some opacity" was tried: 35-43 % of junk pixels pass - useless;
   one alpha per cell + pairs is sharp: true alpha found on 50 / 50 synthetic fade frames.)
6. **Tints** (frozen): the palette x the tint's multiplier = extra LUT colours mapping to the same ids -> 2-4.
7. **Acceptance stays the fit's stage 2** (per pixel SEEN / ABSENT / COVERED, opacity by the mode, greedy pick,
   rule seen >= 0.03 / >= 60 px / absent <= 0.1) on the few cells with >= 24 exclusive votes. Its inputs shrink
   to what D already computes: B = expected(), valid = known & not opaque UI & the mob layer's front alpha < 0.5
   (front alpha planes exist: Scene.layers). No full-frame per-layer split any more.
The opaque vote needs NO scene (it works when the scene camera is lost and on the 95 maps without a clean scene);
fades and ABSENT need the scene.

## 4. Evidence (prototype: E9 candidates -> the existing stage 2 + pick; nothing tuned)
| | LS fit (7744b1d) | vote prototype |
|---|---|---|
| synth ant4_500, all | 99.5 %, 0 false | **99.5 %, 0 false, 0 wrong type** |
| synth player / effect / ui | 98.2 / 97.8 / 100 | **100 / 100 / 100** (every opaque case 100) |
| synth fade | 100 | 96.2 (4 misses: the alpha is not refined yet; o >= 0.35: 81 of 82) |
| labels 012059_1 (match 40 / 30 px), all | 93.3 % | **94.3 %** (before, tracker with memory: 86.9) |
| clear / player / ui / scenery / edge | 96.8 / 82.8 / 80.6 / 96.1 / 96.7 | **97.5 / 90.7 / 87.5 / 98.0 / 96.7** |
| effect (before 88.7) | 78.5 | 86.4 (the frozen "he" mobs missing: tint) |
| fade / dying (before 51.1 / 91.5) | 93.2 / 93.9 | 82.7 / 90.2 (alpha refinement; die frames fade) |
| hit (before 84.8) | 84.8 | 78.8 (frozen = blue: tint) |
| candidates into stage 2 per frame | ~380-720 | **4-7 (max 27)** |
| candidate search ms p50 (unoptimized) | 49 + ~45 glue | **1.7-3.8** whole frame, any number of types / flyers |
Other maps, candidates vs today's well-sighted tracks (score >= 0.9, a cell within 20 px): Line 1 Bubbling 91.9 %,
Dangerous Steam Stirge 98.0 % / Horny 95.2 % / Zombie 93.8 %, Transfer Area Stirge 94.7 %, Dark Cave Stirge 97.4 %
/ Horny 100 % (the rest: tracker feet > 20 px off, fades - to look at in S6); vote incl. the exclusive pass 2.0 ms
p50 / 2.5 p90 there (Ant Tunnel IV 3.8: its scenery shares the palette, 68 k features a frame - 12 k on D's mask). The frozen (blue) mobs: the LS fit accepts them at "seen 17 %" through their
black outline alone (black x any tint = black); the vote has no feature there until the tint is in the palette (S5).
Prototype ms that are NOT the target yet: fade search 2.4-4.8 (no subsampling, false alphas on ~13 % of frames),
stage 2 + pick 4.9-6.4 for 4-7 candidates (pure per-call overhead: ~80 small GPU ops at ~50 us each), the old
per-layer images 5.7.

## 5. What changes against the agreed 3.2 (the user's OK is needed for these)
- The least-squares stage 1 (Srq / Sqq correlations, D-pruned positions, windows from D patches / tracks, ground /
  air pose groups, the gain + explained-fraction lists) is DELETED. The closed-form opacity stays where it is exact
  and cheap: stage 2 (mode of per-pixel ratios), seeded by the fade alpha.
- D's patches no longer drive the fit (FrameFacts v2 keeps them until 3.3 decides); D's pixel mask + expected() do.
- Track predictions become HINTS: a track the vote did not find gets one stage-2 look at its predicted cell ->
  COVERED / ABSENT evidence (3.3 / step 4), not a search window.
- New knowledge to keep: tints (frozen now; poison / stun / others when met - exp_tint.py finds the multiplier).
- Gate unchanged: synth >= 99 % per case, 0 false on mob-free synth + the steam ghost spots, every label class >=
  before, fit <= 5 ms p90. Labels matched at 40 / 30 px for both sides (agreed 2026-11-17).

## 6. Steps (each: pytest + the 'bot speed' line; nothing live reads the fit until 3.3)
**Session 1 - the vote in the product (opaque path end to end)**
- S1 `maplebrain/perception/vote.py`: palette LUT, feature table (CSR), `ids`, `cells` (exclusive votes) from E9,
  made cheap: int32 / int16 where torch allows, features only on D's raw mask when a scene is given (68 k -> 12 k
  features), <= 3 sync points. tests/test_vote.py on tests/fixtures/synth_ant4: every opaque fixture mob's true
  (pose, feet) cell (or its identical-picture alias: Zombie stand_1 = move_2, 4 px apart) has >= 24 exclusive votes.
  Gate: vote <= 2.5 ms p90 on the labels frames.
- S2 fit.py on votes: candidates = cells >= `cand_votes` (24) -> stage 2 with B = expected, valid from known / UI /
  front alpha of the candidate's layer (layer = the nearest foothold's at / below the feet; flyers: their spawn
  layers) -> pick. Delete `_positions`, `_stage1`, the LS weights, `s1_step`, `prune`, `top`, `near`, `margin`,
  `fh_dy`. Offline the tools call scene.expected() themselves; D and the fit sharing ONE expected() per tick is
  3.3's wiring (no live code changes in this plan's two sessions). Stage 2 + pick <= 1 ms for <= 30 candidates: ONE gather of the candidate boxes from a packed image, then few fused
  ops (or numpy on the CPU: the boxes are tiny) - count torch ops, ~50 us each here.
- S3 tools/perc/fit run.py / sweep.py without windows; re-fit `cand_votes` + the rule on synth; report: synth per
  case (opaque cases >= 99 %, 0 false, 0 on mob-free), labels per class at 40 / 30 (non-fade classes >= the LS
  fit's column above), steam ghost spots, ms p50 / p90 (synth, labels frames, steam). Commit, HANDOFF numbers.
  Session gate: opaque fit (no fades) <= 4 ms p90 on the labels frames. Else stop with the parts' ms.
**Session 2 - fades, tints, other maps, close 3.2**
- S4 fades: `fade_alphas` with (a) the cell's alpha taken from its best-count cell and REFINED by least squares over
  the pairs that hit (o = sum r.q / sum q.q, q = palette colour - B), (b) alphas 38..252, pairs subsampled (1 / 4)
  and step 3 if needed, (c) at most 2 alphas a frame, skipped when the residue has < n_min pairs, our own body box
  excluded. Gate: synth fade >= 99 % (report o < 0.3 apart), labels fade >= 93.2 and dying >= 93.9 (the LS fit's),
  0 false fade mobs on synth, fade pass <= 1 ms p50 / <= 3 ms p90. First lever if the ms gate is missed (the
  user, 2026-11-17: restrict to the likely): search the residue only where a fade can be - around tracked mobs that
  are dying / were just hit (fade-out) and around the map's spawn points (fade-in; measure labelled fades' distance
  to the nearest spawn first) - instead of the whole screen. (Restricting POSES does not speed the vote: its cost
  is sprite-coloured pixels, and the full table is what keeps ~1 candidate per mob.) Fallback if the alpha route misses the gate:
  the LS search from 7744b1d (`_stage1`) ONLY at feet positions inside the cells the pair count flags - tell the
  user first.
- S5 tints: palette x (B 255, G 168, R 10) / 255 (rounding from the measured colour pairs; exp_tint.py) as LUT
  entries of the same ids, stage 2 with the tinted sprite; FitMob gets `tint`. Gate: labels hit >= 84.8, effect >=
  88.7 (before's). Log, don't guess, other tints: a mob-shaped residue blob no cell explains -> saved crop for
  exp_tint.py.
- S6 other maps + close: Line 1 (Bubbling: opaque-part features, stage 2 with its alpha), Dangerous Steam / Transfer
  / Dark Cave (flyers) vs today's well-sighted tracks >= 95 % and by eye on 20 misses; steam ghost spots 0; fit ms
  on every gate clip (target <= 5 ms p90 incl. fades); thresholds by sweep; tests/test_fit.py (fixture: recall,
  0 false on mob-free, pose / feet exact); HANDOFF "Step 3 state" + one line in PLAN-perception.md; delete the dead
  LS code and its config; propose 3.3 briefly and wait.
**Then 3.3** (its own OK): the fit in shadow in the Perceiver (FrameFacts v2 mobs), hints for unfound tracks, bench
A/B; expected tick: D 2.8 + fit ~4-5 in, search ~10 + find_near 6 / 20 out at 3.4.

## 7. Cost budget (targets; today's prototype in brackets)
ids + vote 2.0 ms [1.7-3.8] | fade search 0.5-1.0 [2.4-4.8], +1 per fading alpha on screen | stage 2 + pick 1.0
[4.9-6.4, overhead] | images 0.3 (expected() is D's) [5.7] => ~4 ms p50, <= 6 ms on frames with fades.

## 8. Risks and open points
- Exactness needs the native window and lossless frames (the project's premise since step 0). Non-native / JPEG:
  no vote at all -> today's path, as already planned for maps without a scene camera.
- Unknown tints / effects that recolour a mob: missed until measured (exp_tint.py); the tracker's memory covers the
  gap as it does today.
- A mob type with no opaque pixels (fully see-through sprites): no features. Same un-blend machinery as fades with
  the sprite's alpha classes - not built until a map needs it (list such types at load, warn).
- Scenery sharing colours AND 2x2 patterns with a sprite: measured small (35 cells >= 24 votes on 500 synthetic
  frames, mostly real mobs of the base frames); stage 2 judges; if needed, drop table keys that occur in the map's
  own render at load.
- Identical pictures with different origins (Zombie stand_1 / move_2: 4 px) tie: feet ambiguous by the origin
  difference - report both, the tracker's motion decides.
- A type whose mob.json is a `link` to another mob's frames has no pictures of its own here (1x1 placeholders): the
  table must follow the link (today's detector skips such frames) - check at load, warn when a type has no feature.
- Expected tick after 3.4 (not a promise): 19.0 + D 2.8 + fit ~4.5 - search ~10 - find_near 6 (p90 20) = ~10-11 ms
  p50: the plan's 60 fps cap comes into reach.
- The 148 "false" mobs on the labels are mostly label offsets / unlabelled real mobs (sampled): the labels need a
  pass with the fit's exact mobs beside them before "false" means anything there.

## 9. Prompts
**Session 1 (Opus, high):**
```
Continue the perception redesign on branch `perception`. Read HANDOFF.md top to bottom, then PLAN-fit-speed.md (the
user OK'd it on 2026-11-17): execute its "Session 1" (S1-S3) exactly; E9 = tools/perc/redesign/exp_vote.py is the
reference implementation to productionize, tools/perc/fit/* the tools to adapt. Budget matters: be terse.
Gates as written there (vote <= 2.5 ms p90; opaque fit <= 4 ms p90 on the labels frames; synth opaque cases >= 99 %,
0 false; labels non-fade classes >= the LS fit's column; steam ghost spots 0). If a gate fails or a design point
proves wrong on the data, stop and tell me with numbers - no change of course without my word.
Rules: Python = ../auto-maple/.venv; time only with the game running, A/B in the same state; `watch` is running -
never stop it; nothing live reads the fit and no live code changes (pytest + the 'bot speed' line; no gate
replay); no sed on
files (CRLF: Edit or byte-safe Python; write patch scripts with the Write tool, not shell heredocs); long jobs with
run_in_background; commit + push on this branch; numbers into HANDOFF "Step 3 state".
```
**Session 2 (Opus, high):** the same header with "Session 2 (S4-S6)", + "close 3.2: HANDOFF + one line in
PLAN-perception.md, delete the dead LS code, then propose 3.3 briefly and wait for my OK".
