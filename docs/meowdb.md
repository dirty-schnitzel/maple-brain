# meowdb.com: what its MapleStory Classic guides say

Read 2026-11-25 from https://meowdb.com/msclassic/guides (the user: "a very reputable source"). Every guide read is
by one author, **Nia Meow**; the site calls itself a fan database. Notes in our own words; the numbers and formulas
as the pages give them. What we take from it, and in which order it stands against our footage and v83 code:
`docs/game_rules.md` (source **MW**). Section 9 below: each claim against what we measured.

**How far to trust it.** Some pages say where their numbers come from: weapon reach from the game's own hit
rectangles (and its spear numbers are exactly our client's, section 9), walking from frame-by-frame video, grind
EXP from players' logs. The spawn page and the damage page name no source; the damage page marks some parts
"confirmed" and others "a model". The one spawn number we have measured ourselves disagrees with it (the round,
section 9).

## 1. The guides (42 on 2026-11-25)

Prefix every path with `https://meowdb.com/msclassic/`. **Read** = read for this file (date = the page's "updated").

| Group | Guide (path) | What | Read |
|---|---|---|---|
| Classes | `guides/beginners-guide-first-steps-in-maple-world` | Maple Island, first job, AP, potions, quests to 55 | - |
| | `guides/thief-class-guide`, `warrior-class-guide`, `bowman-class-guide`, `magician-class-guide` | build and levelling 1-30 | - |
| | `guides/fighter-`, `spearman-`, `page-`, `il-wizard-`, `bandit-`, `fp-wizard-`, `cleric-`, `hunter-`, `crossbowman-`, `assassin-class-guide` | second job builds, 30-70 | - |
| Mechanics | `guides/explaining-the-damage-formula` | physical / magic damage, defence, hit chance, timing | 2026-11-18 |
| | `guides/class-dps-rankings` | second-job DPS at 70, one-minute damage | - |
| | `guides/exp-table-level-1-to-100` | EXP per level, cumulative | 2026-11-11 |
| | `guides/hp-mp-gain-explained` | HP / MP per level | - |
| | `guides/attack-speed-and-animation-times` | weapon speed, skill times, Booster | 2026-10-10 |
| | `guides/best-grind-maps-every-level` | grind maps 1-70 by EXP / hour | 2026-11-22 |
| | `guides/spawn-engine-respawn-and-map-capacity` | respawn and map capacity | 2026-11-20 |
| | `npc-shops/item-efficiency`, `crafting/exp-table`, `crafting/efficiency` | shops, crafting | - |
| | `guides/maplestory-classic-glossary` | terms | - |
| | `guides/weapon-reach` | hit distance per weapon and animation | 2026-11-19 |
| | `guides/mob-hit-boxes` | mobs' touch and attack boxes by pose | 2026-11-05 |
| | `guides/guard-mechanic-explained` | shield guard | - |
| | `guides/attacks-you-can-use-mid-jump` | attacks in the air, by class | - |
| | `guides/speed-jump-and-movement` | speed, jump, climbing, Teleport | 2026-11-13 |
| World | `guides/what-is-maplestory-classic-worlds`, `forgotten-hollow-the-new-endgame-area`, `maplestory-classic-worlds-release-date`, `founders-package-outfits`, `mark-of-the-beta-event-guide`, `caretakers-ledger-quest-guide`, `kerning-city-party-quest-kpq-guide`, `jump-quests`, `controls-and-settings`, `moon-bunny-party-quest-guide`, `thanksgiving-event-guide` | the game, events, quests, PQs, key settings | - |

Not read and worth a look when a job needs them: `attacks-you-can-use-mid-jump` (the warrior's skills in the air),
`controls-and-settings` (the default keys), `hp-mp-gain-explained`, `class-dps-rankings`.

## 2. Spawning (`spawn-engine-respawn-and-map-capacity`, 2026-11-20; no source named)

- **One respawn check for the whole server every 7.56 s.** At a check, a map under its capacity gets up to one mob
  from every spawn point that is ready; all of them appear together. After an area attack clears a map it refills in
  one wave at the next check.
- **A spawn point's cooldown** after its mob dies: **5 s** for an ordinary ("wave") point; a timed point uses its
  own timer instead (examples 60, 180, 300, 1800 s). The mob comes at the first check at or after death +
  cooldown, so a 300 s boss averages ~304 s (the half check, ~3.78 s, on top).
- **A wave point also waits while another mob stands within 100 px of it**, and spawns once that mob has walked
  away. The only distance rule on the page (mob to point, nothing about players).
- **Map capacity** = floor(W x (H - 450) x mobRate / 128,000), with W = the map's left-to-right span - 40 px and
  H = its top-to-bottom span + 330 px (walls and floors not counted in the spans), W at least 800, H - 450 at
  least 600, the result held to 1..40. One capacity for all mob kinds of the map. `mobRate` is 0.3-1.9 on the
  maps (1.0 the most common).
- **Never more mobs than ready spawn points** (example: 16 players on Sleepy Dungeon IV would give 18 + 8 = 26;
  its 24 regular points hold it at 24 - the page's table lists 30 points for the map, unexplained).
- **Players:** up to six (a party or not) share one player's capacity; each further player adds 0.75 mob, rounded
  down. (The page says "past five" in one place and "from the seventh" in another.)
- Timed bosses ignore the player count; Mushmom is "about every 60 minutes", players report 60-120.
- Solo capacities it lists:

  | Map | Spawn points | mobRate | Capacity |
  |---|---|---|---|
  | Sleepy Dungeon IV | 30 | 0.7 | 18 |
  | Dangerous Croko I | 54 | 1.0 | 40 |
  | Henesys Hunting Ground I | 39 | 0.9 | 18 |
  | Henesys Hunting Ground II | 47 | 1.3 | 15 |
  | Construction Site North of Kerning City | 54 | 0.5 | 17 |
  | Ant Tunnel III | 99 | 0.5 | 21 |

- Spawns per hour, the ceiling (every mob killed the moment it appears): 3600 / 7.56 = ~476 per point; a 60 s timed
  point ~56.
- Not on the page: where a new mob is placed, what it does first, flyers, players' distance to a point, Classic
  World against older versions.

## 3. Speed, jump, climbing (`speed-jump-and-movement`, 2026-11-13; walking measured frame by frame on video)

- **Walking: px/s = 125 x (Speed + 20) / 100** - Classic World adds 20 to the Speed stat inside. Speed 100 (a fresh
  character) = **150 px/s**; each point 1.25 px/s; the cap 140 = 200 px/s. Before Big Bang (v83) Speed 100 walked
  125 px/s, so Classic World's 100 is the old 120. Speed does not change attack speed.

  | Speed | 100 | 105 | 110 | 115 | 120 | 125 | 130 | 135 | 140 (cap) |
  |---|---|---|---|---|---|---|---|---|---|
  | px/s | 150 | 156.25 | 162.5 | 168.75 | 175 | 181.25 | 187.5 | 193.75 | 200 |

- Speed from: Haste +10..30 (and Jump +1..10), GM's Blessing of Wind +30 / +10, Red Whip +15, Nimble Feet +10
  (10-30 s, 3 min cooldown), Speed Potion +8 (10 min), shoes +1..4 (Jump too), White Napoleon +3, Yellow Icarus
  Cape +2. Shoe scrolls: +1 100 %, +2 60 %, +3 10 %, +4 (Chaos) 10 % and a 50 % chance a failure destroys them.
- **Jumping "works the old way"**, its cap 120 (v83: 123). Jump 100: take-off 555 px/s, 77 px high, top after
  0.278 s, **0.555 s in the air** (landing at the take-off height); each Jump point +5.55 px/s.

  | Jump | Take-off px/s | Height px | To the top s | In the air s |
  |---|---|---|---|---|
  | 100 | 555 | 77.0 | 0.278 | 0.555 |
  | 105 | 582.75 | 84.9 | 0.291 | 0.583 |
  | 110 | 610.5 | 93.2 | 0.305 | 0.611 |
  | 115 | 638.25 | 101.8 | 0.319 | 0.638 |
  | 120 | 666 | 110.9 | 0.333 | 0.666 |

  Ledges ~90 px high need Jump 110-116 (Golem's Temple maps, Kerning Construction Site, Forest Up North I).
- **Ropes and ladders: px/s = Speed + 20** (120 at Speed 100, 160 at the cap); Haste speeds climbing too.
- Fall speed: not given. Teleport: 110 px (level 1) .. 150 px (level 20).
- Walking a whole map at Speed 100: Henesys 6,916 px 46.1 s, Kerning City 5,200 px 34.7 s, **Line 1 <Area 1>
  4,070 px 27.1 s**, Ant Tunnel Park 3,960 px 26.4 s, Perion 3,286 px 21.9 s (ropes, slopes, jumps not counted).

## 4. Attack speed and animation times (`attack-speed-and-animation-times`, 2026-10-10; the damage page's timing section)

- **The timing rule** (the damage page; "confirmed" for the frame lengths and the speed conversion): every frame
  of the attack's action lasts trunc(frame delay x **(10 + speed tier) / 16**), tier = the weapon's speed (+ a
  Booster's change) held to 0..10; the action's length = the sum. The time shown to players = that rounded **up
  to a multiple of 30 ms** ("remains a model").
- A matching weapon Booster = **2 tiers faster** at every skill level (100-300 s); Spell Booster 1 tier at levels
  1-10, 2 from 11 (Fire/Poison and Ice/Lightning only).
- An ordinary attack, by tier: 0 510 ms, 1 570, 2 600, 3 660, 4 720, 5 750, 6 810, 7 870, **8 900**, 9 960,
  10-12 1,020. A spear's stab: tier 4 660, 5 720, 6 750, 7 810, 8 870. A crossbow: 4 720 .. 8 930.
- Weapon tiers by type: dagger 3-4, claw 3-5, 1H sword / axe / mace 4-5, 2H sword / axe 5-6, bow 5-6, 2H mace
  6-7, **spear 6-7**, crossbow 6-7, **polearm 7-8**, wand / staff cast at 6. With Booster: spear 4 at best,
  polearm 5 (Slow 8 polearm -> 6: 900 -> 810 ms).
- Skills (slowest weapon / fastest / fastest + Booster): **Rush 450 (polearm 8) / 360 (tier 4) / 300 ms**; Power
  Strike and Slash Blast on a one-handed weapon 750 / 720 / 600 ms (no number for spear or polearm); magic 810 at
  every weapon (720 with Spell Booster 11+); Heal 600.

## 5. Weapon reach (`weapon-reach`, 2026-11-19; from the game's own hit rectangles)

- Every number is the horizontal distance ahead of us (the box's far edge); each box also has a near edge it
  cannot hit inside, and a height.
- **A plain attack picks swing 60 % / stab 40 %** for sword, axe, blunt, spear, polearm, dagger; a bow always
  swings, a crossbow 50 / 50. Power Strike, Slash Blast and Final Attack's extra hit use the same split and the
  weapon's boxes (no reach of their own).
- **Spear / polearm** (basic): overhead swing 133 (144 tall), side swing 120, short swing 116, thrust 1 130 (29
  tall), thrust 2 111 (46 tall), crouched 113 (28 tall); Final Attack: full sweep 144, deep thrust 124 (33 tall).
  The side swing reaches 125 px above the feet; the thrusts ~30 px.
- Other families' basic maximum: 2H sword 98 (the long set - Scimitar, Blade of Harmony, Lion's Fang, Sparta,
  Doombringer - 127), 2H axe / blunt 99, 1H axe and most 1H swords 102 (Long Sword, Gladius ... 85), 1H blunt 94,
  dagger 85-102, wand / staff 69, bow 92, crossbow 86, bare hands 64. Arrows 300 px (+120 with Eye of Amazon),
  stars 200 px (+200 with Keen Eyes).

## 6. Mobs' hit boxes (`mob-hit-boxes`, 2026-11-05; boxes per frame, measured from the mob's feet; source not named)

- Each pose's frame has its own box; it changes much between poses (75 mobs): knocked back higher on 56, wider on
  24; move higher on 38 of 72; jump higher on 17 of 29; attack higher on 15 of 16.
- Biggest: Zombie Mushmom's attack reaches 220 px up (standing 99); King Slime mid-hop 212 (125); Taurospear's
  attack 2 +73 px further ahead; Shade's skill +70. Jumping bosses lift the whole box (Mushmom 94 px for ~0.2 s).
- Boxes that start above the ground: Jr. Boogie 22 px, **Stirge 19**, Fairy 19, Wraith 16, Jr. Wraith 11, Shade 4.

## 7. Damage, defence, hit chance (`explaining-the-damage-formula`, 2026-11-18; the site's calculator method, no source named)

S = the skill's damage % / 100 (1 for a plain attack); W = the weapon's action multiplier; P / Q = the primary /
secondary stat (sword, axe, blunt, spear, polearm: STR / DEX; bow, crossbow: DEX / STR; dagger, claw: LUK / STR +
DEX); A = Attack Power from buffs (0 without); WATK = all weapon attack worn.

- **Mastery** M = (mastery level / 10 + 0.1) x 0.7, the level held to 0..10: 0.07 with none, 0.77 at level 10.
- **MIN = S x WATK x (0.8 + (P x M x W + Q + 2A) / 100); MAX = S x WATK x (1.0 + (P x W + Q + 2A) / 100).**
  The hit is drawn in two parts: a base uniform in 0.8-1.0 and the primary stat uniform in P x M .. P.
- **W:**

  | Weapon | Swing | Stab | Shoot | Mixed |
  |---|---|---|---|---|
  | 1H sword | 1.8 | 1.8 | 1.8 | 1.8 |
  | 2H sword | 2.5 | 2.5 | 2.5 | 2.5 |
  | 1H axe / blunt | 2.4 | 1.2 | - | 1.8 |
  | 2H axe / blunt | 3.0 | 2.0 | - | 2.5 |
  | **Spear** | **1.5** | **3.5** | - | 2.5 |
  | **Polearm** | **3.5** | **1.5** | - | 2.5 |
  | Dagger | 1.0 | 2.0 | - | 1.5 |
  | Bow / crossbow / claw | 1.0 | 1.0 | 2.5 | 1.0 |
  | Wand / staff hit | 1.8 | 1.8 | 1.8 | 1.8 |

  With the 60 / 40 swing / stab split the expected W: spear 2.30, polearm 2.70. A crouched attack: W 1.0, the stat
  divided by 300 instead of 100, the base 0.2-0.3.
- **Against the mob, in order:** x 100 / (DEF + 100); x the element (0, 0.25, 0.5, 0.75, 1, 1.25, 1.5); x the
  level gap scale (gap = mob level - ours: <= 0 -> 1; 1-9 -> 1 / (1 + gap^2 x 0.005); >= 10 -> 1 / (1 + gap x
  0.05)); x a critical (1 + d); cut to whole 1..99,999. Base critical: chance 5 %, +20 %.
- **Our hit chance:** L = max(0, mob level - ours); a = our ACC x 100 / (10 L + 255); f = 0.15 + 0.20 / (1 +
  exp((a - mob EVA) / 12)); a hit when a x uniform(1 - f, 1 + f) >= mob EVA; always a hit when a - EVA >= 25 + L x
  (0.5 x our level + 15). Warrior ACC = floor((1.2 DEX + 2 level + 0.6 LUK) / 2.5 + 10).
- **A mob's hit on us:** G = max(0, our level - mob level); a = mob ACC x 100 / (5 (G + 51)); e = our EVA / (1 +
  EVA / 80) / (1 + G / 40); the same f and roll give a chance, at least 2-3 % when far behind, then + (1 - it) x
  0.08. Damage = the mob's attack x (1.2 + 0.2 U), then x (1 - DEF / (DEF + 300 + 2 raw)) - (DEF / 25 + our level
  / 10), whole, at least 1. Shield guard: max(0.05, shield WDEF / (shield WDEF + 500)).
- Our stats: WDEF = floor(STR / 4); EVA = floor(LUK / 3) + floor(DEX / 6) + 5.
- Its example: a level-30 warrior, Gladius, 132 STR, 30 DEX, 47 WATK: 59-172 without mastery, 137-172 with it;
  Power Strike (S 2.6) 357-449.
- Magic, Heal, damage over time, the class buffs (Combo, Charges, Shadow Partner ...): on the page, not copied.

## 8. EXP (`exp-table-level-1-to-100`, 2026-11-11) and grinding (`best-grind-maps-every-level`, 2026-11-22)

- **EXP to the next level:** levels 1-5 (floor(L^2 / 2) + 15) x L; levels 6-50 q = floor(L^2 / 3), (q + 19) x q;
  51-89 trunc(the last x 1.0548); 90-99 trunc(the last x 2.1). The page: levels 1-89 as before Big Bang.

  | L | EXP | L | EXP | L | EXP | L | EXP | L | EXP |
  |---|---|---|---|---|---|---|---|---|---|
  | 1 | 15 | 11 | 2,360 | 21 | 24,402 | 31 | 108,480 | 41 | 324,240 |
  | 2 | 34 | 12 | 3,216 | 22 | 28,980 | 32 | 122,760 | 42 | 356,916 |
  | 3 | 57 | 13 | 4,200 | 23 | 34,320 | 33 | 138,666 | 43 | 391,160 |
  | 4 | 92 | 14 | 5,460 | 24 | 40,512 | 34 | 155,540 | 44 | 428,280 |
  | 5 | 135 | 15 | 7,050 | 25 | 47,216 | 35 | 174,216 | 45 | 468,450 |
  | 6 | 372 | 16 | 8,840 | 26 | 54,900 | 36 | 194,832 | 46 | 510,420 |
  | 7 | 560 | 17 | 11,040 | 27 | 63,666 | 37 | 216,600 | 47 | 555,680 |
  | 8 | 840 | 18 | 13,716 | 28 | 73,080 | 38 | 240,500 | 48 | 604,416 |
  | 9 | 1,242 | 19 | 16,680 | 29 | 83,720 | 39 | 266,682 | 49 | 655,200 |
  | 10 | 1,716 | 20 | 20,216 | 30 | 95,700 | 40 | 294,216 | 50 | 709,716 |

  51 748,608; 55 926,689; 60 1,209,994; 65 1,579,913; 70 2,062,925; 80 3,517,093; 89 5,684,790; 90 11,938,059;
  99 9,482,161,548 (100 is the cap; 18,194,778,397 in all). The rows between follow the formula.
- **Grinding EXP / hour** (players' logged ranges from community trackers; "est." = an estimate; at the level shown):

  | Map | Mob | EXP / hour |
  |---|---|---|
  | **Line 1 <Area 1>** | Bubbling 15 | 19K-32K (Lv 27) |
  | Transfer Area | Stirge 20 | 31K-50K (Lv 30) |
  | Ant Tunnel I | Horny Mushroom 22 | 51K-72K (Lv 33) |
  | Ant Tunnel III | Zombie Mushroom 24 | 34K-64K (Lv 32) |
  | Deep Ant Tunnel I | Zombie Mushroom 24 | 51K-81K (Lv 38) |
  | Ant Tunnel Park | Evil Eye 27 | 51K-61K (Lv 35) |
  | The Cave of Evil Eye III | Evil Eye 27 | 68K-85K (Lv 41) |
  | Tree Dungeon, Forest Up North IV / III | Green / Horny Mushroom | 22K-29K (Lv 23) / 25K-42K (Lv 26) |
  | Henesys Hunting Ground I | seven kinds, 2-14 | 12K (Lv 17) |
  | The Burnt Land II / V (Perion) | Fire Boar 32 | 81K-99K (Lv 40) / 63K-104K (Lv 43) |
  | Dangerous Valley (Perion) | Copper Drake 45 | 105K-125K (Lv 50) |
  | Line 1 <Area 2> / <Area 4> | Jr. Wraith 34 / Wraith 48 | 56K-69K (Lv 38) / 95K-146K (Lv 51) |

  Parties split each kill's EXP and add a bonus: six players at one level need ~4-5 x the kills each for the solo
  rate. The full page lists maps to level 70.

## 9. Checked against ours (2026-11-25)

| Claim | Ours | Verdict |
|---|---|---|
| Respawn check every 7.56 s | **observed 7.08-7.20 s** (R 0.99-1.00 on 10 of 12 captures; 7.56 was inside the 6.5-7.6 s searched; PLAN-tracker.md "Step 3b") | **disagrees: observed wins** |
| Walking 150 px/s at Speed 100 | `Nav.walk_speed` 125 (Physics.img); our fitted jump: a level hop 86 px in 0.555 s = 155 px/s sideways (150 x 0.555 = 83 px) | agrees with the fitted jump; `walk_speed` 125 is not a measurement |
| Jump 555 px/s, 77 px, 0.555 s | `Nav.jump_speed` 555, `jump_height` 70 (measured 60-80) | agrees |
| Climbing Speed + 20 = 120 px/s | `Nav.climb_speed` 125 (one rope: 160 px in 1.25 s) | close; ours is one measurement |
| An action's frames x (10 + tier) / 16 | `brain/reach.py` uses (10 + attackSpeed) / 16 (in neither HC nor Cosmic); the live polearm swing 0.89-0.92 s vs MW's 900 ms | **agrees** |
| Spear / polearm reach 133 / 144 / 130 / 124 / 120 / 116 / 113 / 111 px | the client's `Afterimage\spear.img` boxes (game_rules F3): swingP1 133, swingPF 144, stabT1 130, stabTF 124, swingT2 120, swingP2 116, proneStab 113, stabT2 111 | **the same numbers** |
| Mastery on a 0-10 scale | Classic World's Spear / Polearm Mastery `mastery` 1 / 5 / 10 (F6) | agrees (v83's was 10-60) |
| Capacity, the 5 s cooldown, the 100 px block | not measured | open: checkable on the kept replay (most mobs alive at once, the time between two spawns on a point, a mob near a ready point) |

## Appendix: the rest of what was read

**EXP to the next level, 51-99:** 51 748,608; 52 789,631; 53 832,902; 54 878,545; 55 926,689; 56 977,471; 57
1,031,036; 58 1,087,536; 59 1,147,132; 60 1,209,994; 61 1,276,301; 62 1,346,242; 63 1,420,016; 64 1,497,832; 65
1,579,913; 66 1,666,492; 67 1,757,815; 68 1,854,143; 69 1,955,750; 70 2,062,925; 71 2,175,973; 72 2,295,216; 73
2,420,993; 74 2,553,663; 75 2,693,603; 76 2,841,212; 77 2,996,910; 78 3,161,140; 79 3,334,370; 80 3,517,093; 81
3,709,829; 82 3,913,127; 83 4,127,566; 84 4,353,756; 85 4,592,341; 86 4,844,001; 87 5,109,452; 88 5,389,449; 89
5,684,790; 90 11,938,059; 91 25,069,923; 92 52,646,838; 93 110,558,359; 94 232,172,553; 95 487,562,361; 96
1,023,880,958; 97 2,150,150,011; 98 4,515,315,023; 99 9,482,161,548. Cumulative to reach 31: 752,817; 51:
8,309,915; 71: 35,784,253. The page calls 99 the highest level reached in the closed test (COT2) and marks 70 as
third job "for a later update" while saying Ossyria and third job are not in the game yet.

**Grind maps, the rest of the page** (EXP / hour at the level shown; "est." an estimate; the part past level 46 was
read through a summary of the page, not word for word): L Forest I (Ribbon Pig) 9.0K-9.1K est.; Construction
Site North of Kerning City (Dark Stump) 6.0K-6.3K est.; The Tree That Grew II (Slime) 5.1K-5.4K est.; West Rocky
Mountain III (Green Mushroom) 18K (Lv 20); Dangerous Steam (Stirge) 55K-67K (Lv 34); Tree Dungeon, Forest Up North
VIII (Curse Eye) 94K-123K (Lv 45); Line 2 <Area 1> (Jr. Wraith) 65K-75K (Lv 40); Monkey Forest I / II (Lupin /
Zombie Lupin) 112K-129K (Lv 45) / 109K-131K (Lv 48); Lorang Lorang 101K-121K (Lv 45); Forgotten Entrance III
(Glowshroom) 100K (Lv 45); A Look-Out Shed Around the Beach 75K-95K (Lv 43); Tree Dungeon, Monkey Forest II
107K-140K (Lv 52); Another Path (Cold Eye) 89K-111K (Lv 48); Monkey Swamp II 87K-106K (Lv 45); Hanging Gardens of
Rot (Aqumander) 91K est. (Lv 46); Forbidden Entrance (Duskmander) 133K (Lv 52); Line 2 <Area 3> / <Area 2> (Wraith)
96K-142K (Lv 51) / 81K-114K (Lv 50); Precipice of Darkness (Rotten Mushroom) 116K-137K (Lv 59); Lorang and Clang
94K-108K (Lv 51); Dangerous Croko II 83K (Lv 51); Sleepy Dungeon IV / III / V (Dark Stone Golem) 185K (Lv 64) /
145K-168K (Lv 60) / 98K (Lv 57); Another Sanctuary 116K-158K (Lv 65); Camp 3 (Officer Skeleton) 138K-195K (Lv 70);
Dangerous Valley II (Red Drake) 155K (Lv 66); Remains <Tomb> IV 140K-149K (Lv 70). Party picks: The Pig Beach
15K-23K (Lv 21, an Iron Hog hourly); Damp Forest 27K-65K (Lv 31); Land of Wild Boar 67K-82K (Lv 37, Jr. Boogies
every 5-10 min); Drake Hunting Ground 133K-154K (Lv 53); The Entrance of Golem's Temple 109K (Lv 56); 1st
Accompaniment <Bonus> 50K-57K (Lv 33; 24 Horny + 12 Green Mushrooms). Each row also gives the portals to a potion
shop (Line 1 <Area 1>: 3).

**Speed setups** (Speed -> px/s): Speed Potion 108 -> 160; Lv 70 shoes + White Napoleon + potion 115 -> 168.75;
with five +2 shoe scrolls 125; Red Whip + the same 130 -> 187.5 (with scrolls 140 = the cap); max Haste 130, + potion
138, + shoes +2 = 140. Max Haste's +10 Jump: +16 px of height, +0.056 s in the air. KPQ stage 4 barrels: the bottom
row 55 px over the floor, each row 52 px more; floor to the top barrel 159 px (out of reach). Golem's Temple I needs
Jump 110, IV 113, Kerning Construction Site 114, Forest Up North I 116.

**Reach, the other sets** (basic unless noted; FA = Final Attack's): 2H sword standard: swing 1 86, swing 3 78,
swing 2 75, thrusts 98, crouched 92, FA wide swing 92 / deep thrust 123; 2H sword long set: swing 1 100, swing 3 87,
swing 2 86, thrust 2 127, thrust 1 110, crouched 109, FA 116 / 135; 2H axe / blunt: swing 1 99, crouched 86, FA 114
/ 116; 1H axe and most 1H swords: swing 3 102, crouched 74, FA 123 / 110; 1H short set (Long Sword, Gladius, Traus,
Jeweled Katar, umbrellas): swing 1 85, crouched 66, FA 100 / 95; 1H blunt: swing 3 94, crouched 72, FA 118 / 108;
dagger short set: swing 1 85, swing 3 78, swing 2 64, thrust 1 74, thrust 2 70, crouched 66; wand / staff: swing 2
69 (the only plain attack), swing 3 94, swing 1 77, thrusts 82; bow: overhead 86, uppercut 78, crouched 92;
crossbow: overhead 86, thrust 84, crouched 85; bare hands: punch 1 64, punch 2 60, crouched 56.

**Mob boxes, the largest changes from standing:** up - Zombie Mushmom attack +121 (99 -> 220), Mushmom attack +109,
Rotten Mushmom attack +92, King Slime move +87, Jr. Balrog attack +37 (156 -> 193), Iron Hog skill +36, Taurospear
attack +36, Stumpy attack +33, Tauromacis attack +24, Wraith knocked back +24 (74 -> 98); ahead - Taurospear attack 2
+73, Shade skill +70, Tauromacis attack +51, Jr. Balrog attack 3 +47, Red Drake attack +45, Sporewood move +24;
behind (knocked back) - Commander Skeleton +29, Skeleton Soldier +28, Dark Stone Golem / Stone Golem +23. Wild
Kargo knocked back shrinks 159 -> 116 px wide. Stone Golems reach 160 px up knocked back; jumping bosses: Zombie
Mushmom 90 px for 0.2 s, Rotten Mushmom 73 px for 0.1 s, King Slime 72-77 px for 0.3 s. Wraith standing: 70 x 58,
from 16 px up.

**Damage page, the rest:** the expected hit before the cut = S x WATK x (0.9 + (P x (M + 1) / 2 x W + Q) / 100 +
A / 50). A ranged weapon used close: W 1.0, the stat / 300, Attack Power / 150 for a swing (a claw always stabs).
Lucky Seven W 3.0, M 0.5. Defence with a bypass chance g: x ((1 - g) x 100 / (DEF + 100) + g). The element of a
two-element attack: 0.25 x (the two ratings, 0 immune .. 3 weak). Magic: M from the spell mastery the same way;
magic total = floor(INT / 2) + the gear's, scrolls' and buffs' MATK; MIN = S x total x (1 + INT x M / 125), MAX = S
x total x (1 + INT / 125); spells can miss by the same check; weapon speed does not change a spell's time. Heal:
pool = ((INT x uniform(0.1, 1.2) + LUK) / 1000 + 2.5) x magic total x S, shared over max(2, the targets) with x
(1 + 0.5 (t - 1)) / t / 1.5 per undead mob. Damage over time: (its % / 100) x magic total x (INT / 125 + 1), no
defence, the level scale applies. Class buffs: Combo +(5 + floor(level / 2)) % with an orb; the finisher 1 + 5 x
orbs x (orbs - 1) / 100 (orbs 3 / 4 / 5 at levels 1-10 / 11-20 / 21-30); Charges +(level + 1) % to 8, 9 at 9, 5 +
floor(level / 2) from 10; Element Amplification (104 + level) % (135 at 30); Shadow Partner (109 + level) % (140 at
30); Iron Arrow 0.8 per further target; Dragon Roar repeats at max(the animation, its self-stun 4 / 3 / 2 s).
Cycles: one-minute damage = floor(60,000 / max(animation, lockout)) x the hit. ACC by class: beginner floor(c /
2.5 + 5), bowman floor(c / 4.8 + 20), thief floor(c / 4 + 15), magician floor((1.2 INT + 2 level + 0.6 LUK) / 5.1 +
20), c = 1.2 DEX + 2 level + 0.6 LUK. MDEF = floor(INT / 4). Claw Guard 3 / 4 / 5 %. Its timing examples: Magic
Claw 800 ms, Savage Blow 960 ms, Explosion 1,800 ms.

**Attack-speed page, the rest:** the fastest weapons by type (dagger: Fruit Knife, Cass, Korean Fan, Golden River;
claw: Meba the only tier-3; 1H sword: Long Sword, Sabre, Viking Sword; spear: Fish Spear 20, Zeco 40, Holy Spear 60;
polearm: Studded Polearm 20); Booster from: Fighter (swords, axes), Page (swords, blunts), Spearman (spear,
polearm), Hunter, Crossbowman, Assassin, Bandit. Other skill times: Haste 570 / 510 / 420, Double Stab 720 / 660 /
570, Lucky Seven 750 / 660 / 570, Double Shot and Arrow Blow on a bow 810 / 750 / 660, on a crossbow 870 / 840 /
720, Savage Blow 840 / 780 / 660.
