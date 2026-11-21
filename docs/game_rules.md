# Game rules, as v83 code has them

Written 2026-11-21 (branch `rules`). The rulebook for the tracker redesign (how a mob can move, be thrown, die and
respawn between two frames) and for the simulator's engine (how the world advances from our input). Every rule is
taken from a source below; where no source has a rule it says **NOT FOUND** and the question is in table 3. Nothing
here was measured or guessed. No code was changed for it, except one line of `tools/cwdata/export.ps1` (below).

## Sources

| Short | What | Where | Commit |
|---|---|---|---|
| **HC** | HeavenClient, a fan re-implementation of the v83 client (C++). Movement of our character and of mobs, camera, drops in flight, damage numbers | `C:\Users\Yoav\dev\v83-ref\HeavenClient` (github.com/gmh5225/MapleStory-HeavenClient) | `0daa69d718c7e68623ca130d7e65070af8e82848` |
| **CO** | Cosmic, a GMS v83 server emulator (Java). Respawn, controller and aggro, damage checks, EXP, drops, potions | `C:\Users\Yoav\dev\v83-ref\Cosmic` (github.com/P0nk/Cosmic), paths below are under `src/main/java/` | `fec53bc7714dc0f1ae3f50b2986cdf2727e0912a` |
| **RU** | github.com/neeerp/RustMS/issues/295: v83 player physics read out of the original client's movement code (`CVecCtrl`, a MapleLegends client). Read through a fetch that returned a structured account, not the verbatim text | the issue page | - |
| **CW** | Our Classic World client files: `C:\Users\Yoav\dev\cw-data\export\` (XML) and `assets/mcw/` | - | export re-run 2026-11-21 |

Both clones are reading material (AGPL-3.0): nothing was built or run from them. Rules are in my own words.

**How much each source can be trusted.** RU is the original client's code, so for our character's movement it
wins over HC. HC is a re-implementation: its structure is right, several of its numbers are its author's
approximations (it says so itself in places, e.g. `CharStats.cpp:215` "need to find the actual formula"). CO is a
server emulator descended from HeavenMS: packet handling is v83, but some policies are its authors' own design
(the respawn rate by player count, the aggro bookkeeping) and its timers are config values. Each such place is
marked **(source's own design)** and listed in table 3.

**The export was extended (a small job):** `tools/cwdata/export.ps1` now also writes `Skill\130.img.xml` (Spearman)
and `String\Skill.img.xml` (skill names). Re-run clean ("failed: 0", 57 s). `assets build` was not re-run.

## Decided by the user (2026-11-21)

- **Our character's speeds: our values are the rule** (question 1). The user: Classic World raised the base jump
  and move speed, so where our fitted numbers differ from v83's (`Nav.jump_vx` 155 px/s against the source's cap
  at 125, `Nav.jump_reach`, the rope-leap numbers of `config.py:98-115`) ours stand. The v83 formulas of
  section A stay as the shape of the rule; its constants are not to be copied over ours.
- **The swing length: ours for now**, `(10 + attackSpeed) / 16` (question 10) - to be recalculated from the
  tracker once it exists.
- **Server data is parked:** nothing further on Cosmic's side (respawn numbers, aggro, drop lifetime, EXP
  tables: sections D2, E, G, H and their questions) until a job needs it. The questions stay listed, unanswered.

## Units and conversions

- Map pixels = screen pixels (sprites are 1:1). x grows right, **y grows down**. A mob's or character's position is
  its feet.
- **HC's update step ("tick") is 8 ms** (`Constants.h:29` `TIMESTEP = 8`; the loop in `MapleStory.cpp:92-109` runs
  one update per 8 ms of real time and draws in between, interpolated). So: speed in px/tick x 125 = px/s; force or
  acceleration in px/tick^2 x 15,625 = px/s^2; N ticks x 0.008 = seconds.
- `Physics.img` (CW, `Map\Physics.img.xml`) stores forces x 100: RU says the client divides forces by the shoe's
  mass 100. So `walkForce 140000` = 1400 px/s^2. Speeds (`walkSpeed`, `jumpSpeed`, `fallSpeed`) are px/s as stored.
- Terms. **Foothold**: one straight piece of ground (x1,y1)-(x2,y2) with a link to the piece before and after it
  (`prev` / `next`); a platform is a chain of footholds. **Stance**: the animation state of a character or mob
  (stand, move, hit ...). **Controller**: the one player whose client simulates a given mob and reports its
  movement to the server; every other client replays what it is told.
- "Ours" at the end of an entry = what our code does today for the same thing, with one word: **same** (as the
  source named), **differs**, **missing**.

---

## A. Our character's movement

### A1. Walking: force, drag, top speed, the speed stat
- **RU (original client):** holding left or right pushes with `walkForce` 1400 px/s^2 until the top speed
  `walkSpeed` 125 px/s x the speed stat; with no key held the character slows by `walkDrag` 800 px/s^2. The speed
  stat is clamped to 80-140 % (so top speed 100-175 px/s). Reaching 125 px/s takes 0.089 s; stopping from it takes
  0.156 s and 9.8 px. The position advances by the average of the old and new speed in a step.
  Source: RU "What v83 does" (walking `FUN_007f21d2`, shoe `FUN_007a4dec`). Fields: Physics.img `walkForce`,
  `walkSpeed`, `walkDrag`.
- **HC:** force per tick = `0.05 + 0.11 x speed/100` px/tick^2 (0.16 at 100 % = 2,500 px/s^2), against a friction
  of 0.2 x speed per tick on flat ground; the two balance at 5 x force = 0.8 px/tick = **100 px/s** at 100 %. No
  clamp on the stat. With no key the speed shrinks x0.8 per tick and is set to 0 below 0.1 px/tick (12.5 px/s):
  a stop from full speed takes ~0.08 s and ~3 px.
  Source: HC `Character/Player.cpp:465-468` (`get_walkforce`), `Character/PlayerStates.cpp:163-189`,
  `Gameplay/Physics/Physics.cpp:22-28, 66-103`.
- The two disagree (125 vs 100 px/s, constant drag vs proportional friction). RU is the original client and its
  constants are exactly our Physics.img's, so RU is the rule.
- Ours: `nav/sim.py:12` (1400 / 125 / 800), `brain/moves.py:14-15` (WALK 125, DRAG 800), `config.py:102`
  `Nav.walk_speed 125` - **same** as RU. The speed stat is **missing** (top speed is fixed at 125).

### A2. Slopes
- **RU:** walking works on the speed along the foothold; the push is scaled by 1 +/- slant^2 (more downhill, less
  uphill). A foothold steeper than `walkSlant` 0.9 cannot be stood on: the character slides (`slipForce` 600
  px/s^2, `slipSpeed` 120 px/s are the Physics.img fields for it; RU names the 0.9 threshold but not how the slide
  uses those two fields -> the slide's formula is **NOT FOUND**).
- **HC:** friction per tick = `(0.5 + 0.1 x (1 - slope x v/3)) x v/3`, slope = dy/dx of the foothold clamped to
  +/-0.5: slower uphill, faster downhill. Source: `Physics.cpp:82-90`. No sliding.
- Fields: map.json `footholds` (x1,y1,x2,y2); Physics.img `slipForce`, `slipSpeed`.
- Ours: `nav/sim.py:79-80` same force and cap on any slope - **differs** (no slope term).

### A3. The jump: force, the jump stat
- **RU:** take-off speed = `jumpSpeed` 555 px/s x the jump stat, clamped to 80-123 %. At 100 %: peak 77 px after
  0.2775 s, back at the take-off height after 0.555 s. **Holding a direction when jumping adds 80 % of the top
  walking speed to the horizontal speed, capped at the top walking speed** (so a jump is never faster sideways
  than walking). Source: RU jump `FUN_007f1bb0`. Fields: Physics.img `jumpSpeed`, `gravityAcc`.
- **HC:** take-off = `1.0 + 3.5 x jump/100` px/tick = 4.5 px/tick = 562.5 px/s at 100 %; no sideways kick; a jump
  is only possible standing or walking, not mid-attack. Source: `Player.cpp:470-473`, `PlayerStates.cpp:93-104,
  142-152`.
- Ours: `nav/sim.py:13, 65-66` take-off 555 - **same** as RU. Sideways: `sim.py:18-19` multiplies the speed by
  155/125 at take-off (`config.py:105` `Nav.jump_vx 155`, calibrated on footage) - **differs** from RU's cap at the
  walking speed (question 1). The jump stat is **missing**.

### A4. In the air: control, gravity, the fall-speed cap
- **RU:** gravity `gravityAcc` 2000 px/s^2 down, up to `fallSpeed` 670 px/s (reached 0.335 s after the peak, 112
  px below it). A held direction accelerates at 2 x `floatDrag2` = 200 px/s^2 toward
  (`walkSpeed` / `walkForce`) x `floatDrag2` = 8.9 px/s - so from a standing jump a direction key moves us
  almost not at all. Whether a sideways speed already above 8.9 px/s in the held direction is kept or braked is
  **NOT FOUND** in the account I read (question 2). With no key the sideways speed drags at `floatDrag1` x
  `floatCoefficient` = 10 px/s^2, or at `floatDrag2` = 100 px/s^2 once falling at the cap.
  Source: RU falling `FUN_007f2a1c`. Fields: Physics.img `gravityAcc`, `fallSpeed`, `floatDrag1`, `floatDrag2`,
  `floatCoefficient`.
- **HC:** gravity 0.14 px/tick^2 = 2,187.5 px/s^2, **no fall-speed cap**, no sideways drag in the air; holding
  the direction against the motion brakes by 0.025 px/tick^2 = 391 px/s^2, holding along it does nothing.
  Source: `Physics.cpp:22, 93-96`, `PlayerStates.cpp:211-227`.
- Ours: `nav/sim.py:13, 122` gravity 2000, cap 670 - **same** as RU. Air control and air drag: **missing** (the
  sideways speed is frozen at take-off, `sim.py:123`).

### A5. Landing, stopping, turning
- **HC:** we land when the fall crosses the foothold under us (`FootholdTree.cpp:121-138`); on landing the state
  becomes stand, or lying down if down is held with no direction (`PlayerStates.cpp:229-237`). Facing follows the
  direction key at once, **except during an attack: direction and stance are frozen until the attack animation
  ends** (`Player.cpp:206-223`), and the walk key adds no force meanwhile (`PlayerStates.cpp:168-169`).
- RU: nothing beyond A1's drag. Ours: `nav/sim.py:128-130` lands with speed 0 - **differs** (the source keeps
  the sideways speed and drags it). The frozen facing during a swing matches memory "facing is a belief".

### A6. Dropping through a platform (down + jump)
- **HC:** allowed when another foothold lies under the one we stand on and **less than 600 px below it**
  (`FootholdTree.cpp:205-221`, the flag `enablejd`). Pressing jump with down held, while walking or lying down,
  moves the feet 1 px under the platform and starts a fall from speed 0 (`PlayerStates.cpp:154-160, 246-257`).
  Standing with down held first becomes lying down, then the same rule applies.
- RU: not covered. Our map.json marks footholds `forbidFallDown` (17,271 of 82,632) and `cantThrough` (150): by
  their names they bear on this, and **no rule found reads them** - HC has only the 600 px rule (question 3).
- Ours: `nav/sim.py:58-63` drops when any platform is below, no 600 px limit - **differs**.

### A7. Ropes and ladders
- **Grab (HC):** each tick, while not attacking, sitting or already climbing: with **up** held (and not down) the
  ladder is taken if its x is within **10 px** of ours and the point 5 px above our feet is between its y1 and y2;
  with **down** held, if the point 5 px below our feet is. Works in the air too (so jump + up grabs). After
  leaving a rope by a jump or off its end, **no grab for 1 s** (`climb_cooldown`). On the grab our x snaps to the
  rope's x and both speeds become 0. Source: `Gameplay/Stage.cpp:159-168, 235-242`,
  `Gameplay/MapleMap/MapInfo.cpp:126-136`, `Player.cpp:439-463`. Field: map.json `ladderRopes` (x, y1, y2,
  isLadder = the client's `l`).
- **Climbing speed (HC):** speed stat / 100 px/tick = **125 px/s at 100 %**, 0 with no key or both keys
  (`Player.cpp:475-478`, `PlayerStates.cpp:381-394`). RU does not give it.
- **Off the ends (HC):** climbing ends (a fall starts) when our y + 5 is above the rope's top, or, going down, our
  y + 5 is below its bottom (`MapInfo.cpp:138-143`, `PlayerStates.cpp:411-419`).
- **Jumping off:** needs jump + left or right.
  RU (original): up-speed = half the jump speed = 277.5 px/s, sideways 1.3 x the walking speed = 162.5 px/s.
  HC: up 4.5/1.5 = 3 px/tick = 375 px/s, sideways 8 x walk force = 1.28 px/tick = 160 px/s
  (`PlayerStates.cpp:396-408`). RU is the rule.
- No attack on a rope or ladder (`Player.cpp:230-241`).
- Ours: `nav/sim.py:14-17` climb 125 **same**; grab within 10 px **same**; rope jump 300 up / 125 sideways
  **differs** (277.5 / 162.5); the 1 s no-grab time **missing**; `config.py:108-115` (`rope_grab`, `rope_leap` ...)
  are measured numbers with no counterpart in the sources.

### A8. Lying down
- **HC:** down held on the ground with no direction key and not up = lying (prone). Any direction key starts a
  walk, up or releasing down stands up. No skills while lying; a plain attack lying down is the `proneStab`
  stance (box in D/F). The touch box in HC is **not** lowered while lying (B1). Source:
  `PlayerStates.cpp:125-126, 245-279`, `Player.cpp:237, 261-265`.
- Ours: `nav/sim.py:78` (down held = no walking) - **same** as far as it goes.

### A9. Map edges
- **HC:** we cannot walk past x = (leftmost foothold x of the map) + 25 or (rightmost) - 25, and not through a
  wall (a vertical foothold) that overlaps the 50 px above our feet; y is clamped to (top foothold - 300) ..
  (bottom foothold + 100). Source: `Gameplay/Physics/FootholdTree.cpp:91-92, 97-147, 243-277`.
- CO has its own limits for placing drops (`MapleMap.calcDropPos`, H2).
- Ours: `nav/sim.py:93-94, 132-134` (stops at a closed platform end, walls stop us in the air) - **differs**
  (no +/-25 px map walls).

---

## B. Being hit

### B1. Touching a mob
- **HC:** every tick, unless we are invincible (B3), dead, or hidden by Dark Sight: the first living mob whose
  current frame's body box (mob.json frame `lt`/`rb`, at the mob's position) overlaps our box hits us, if the
  mob's `bodyAttack` is 1. Our box = from our x of the last tick to our x now, and from 50 px above our feet to
  our feet. The mob's attack value = a random whole number in [0.8 x `PADamage`, `PADamage`].
  Source: `Stage.cpp:180-190`, `MapMobs.cpp:126-160`, `Mob.cpp:572-582, 596-605`.
  Fields: mob.json info `bodyAttack`, `PADamage`; frames `lt`, `rb`.
- **Damage against our defence: NOT FOUND.** HC's formula (`attack/2 + attack/defence`) is marked by its author
  as a placeholder (`CharStats.cpp:213-224`); CO does not compute it - it takes the damage number our client
  sends (`net/server/channel/handlers/TakeDamageHandler.java:73`).
- **The miss chance (our avoidability): NOT FOUND.** HC calls damage <= 0 a miss and has no avoid roll; CO reads
  damage -1 from the client as a miss (`TakeDamageHandler.java:191`).
- Ours: nothing computes it; we read our HP from the HUD - **missing** (needed by the engine only).

### B2. The knockback
- **HC:** on a hit that did damage, unless we are on a rope / ladder or dead, and unless the Stance chance
  (Iron Will's `prop` in CW) saves us: sideways speed is set to **1.5 px/tick = 187.5 px/s away from the mob**
  (left if the mob's x is greater than ours) and an upward push of 3.5 px/tick = 437.5 px/s is applied. With
  HC's gravity that is a hop 44 px high, 0.4 s long, ~75 px sideways; with RU's gravity (2000) 48 px, 0.44 s,
  ~82 px. Source: `Player.cpp:343-363`. Note HC applies the upward push as a ground force (`vforce`), which its
  physics uses only when we stand on ground: a hit taken in the air changes the sideways speed only.
- RU: knockback is not covered. The original client's numbers: **NOT FOUND** (question 4).
- Ours: `brain/moves.py:125-132` recognises a knockback (thrown against the held key, or up in the air off a
  node); no model of its size - **missing**.

### B3. The time we cannot be hit again
- **HC:** 2 s after any hit shown on us (`Char.cpp:192-201` `invincible.set_for(2000)`), during which the
  character blinks darker; the "alert" pose stays 5 s. Checked before the touch test (`Stage.cpp:180`).
- CO: no timer of its own found for touch damage. Ours: **missing**.

### B4. A mob's own attacks (attack1.., skill1..)
- **HC: not implemented** - its `Mob.cpp` has stand, move, jump, hit, die only; `attack` / `skill` animations are
  never loaded.
- **CO:** per mob, each `attackN` has an MP cost (`info/conMP`), a cooldown (`info/attackAfter`) and a length =
  the sum of its frames' `delay`; the controller's client announces an attack inside its movement report and the
  server only checks MP and cooldown (`server/life/LifeFactory.java:220-229`,
  `net/server/channel/handlers/MoveLifeHandler.java:84-115`). Mob skills likewise (`MoveLifeHandler.java:90-135`).
  The attack's reach, when in the animation it lands, and when a mob chooses to attack: **NOT FOUND** (client
  logic neither source has; question 5).
- Fields: mob.json info `attack` (26 mobs), `skill` (18 mobs); framebooks `attack1-3`, `skill1-2`.
- Ours: **missing**.

---

## C. Mobs' movement

All of it is HC `Gameplay/MapleMap/Mob.cpp` + `Gameplay/Physics/Physics.cpp`. Only the controller's client decides
(C2); every client moves the mob by the same physics from the stance it is in.

### C1. Speed
- **Walkers:** push per tick = (`speed` + 100) x 0.001 px/tick^2 toward the facing, against the ground friction
  0.2 x v. Top speed = 5 x push = **(speed + 100) x 0.625 px/s**: speed 0 -> 62.5 px/s, -65 -> 21.9, -50 -> 31.3,
  +5 -> 65.6. It is reached quickly (63 % after 5 ticks = 0.04 s) and on a slope by the A2 formula.
  Source: `Mob.cpp:45, 77-78, 214-217`, `Physics.cpp:82-90`. Field: mob.json info `speed` (107 of 128 mobs; absent = 0).
- **Flyers** (mobs with a `fly` animation): push = (`flySpeed` + 100) x 0.0005 px/tick^2, friction 0.05 x v on
  both axes: top speed **(flySpeed + 100) x 1.25 px/s** (0 -> 125 px/s), reached slowly (63 % after 20 ticks =
  0.16 s). Source: `Mob.cpp:46, 80-84, 200-213`, `Physics.cpp:27, 105-123`. Field: `flySpeed` (13 mobs).
- Ours: `perception/world.py:24` `vmax 160` px/s as one generous cap for every mob - **differs** (the rule
  gives a cap per mob type: 62.5 px/s at speed 0); `tests/test_brain_v2.py:487` FakeMobs walk at 40 px/s -
  **differs**.

### C2. When a mob decides, and the odds
- A decision is taken only by the controller's client, when **more than 200 ticks (1.6 s) have passed since the
  last decision AND the current animation has just ended** (so: every 1.6 s rounded up to the end of a stand /
  move animation loop). From a hit: after 31 ticks (D1). From a jump: on landing.
- The choice: coming from **stand or hit -> always move**, facing left or right 50 / 50. Coming from **move or
  jump ->** if the mob can jump and is on the ground, 25 % jump; otherwise 1/3 stand, 1/3 move left, 1/3 move
  right. A mob with no `move` (and no `fly`) animation always stands. The decision and the position are reported
  to the server.
- Source: `Mob.cpp:235-260` (the timer), `271-316` (`next_move`). Fields: mob.json framebooks `move`, `jump`,
  `fly`; frames `delay`.
- Ours: `world.py:26` `v_half_s 0.6` ("mobs stop / turn ~every 1.6 s") - **same** rhythm, no odds;
  `test_brain_v2.py:510` FakeMobs turn with 0.2 % per step and never stand - **differs**.

### C3. Platform ends, the walk range, `fs`
- **HC:** a walking mob stops at the end of its foothold chain (where `prev` / `next` is 0, looking up to two
  footholds ahead) or at a wall, and **turns round on the next tick** (if it was in the hit pose it goes to
  stand). It does not walk off a platform. Source: `FootholdTree.cpp:108-118, 279-313` (`TURNATEDGES`),
  `Mob.cpp:185-195`.
- **The walk range `rx0` / `rx1` (our `walkAreaX1/X2`): no rule found reads it.** HC never loads it; CO stores
  it (`server/life/AbstractLoadedLife.java:33-92`) and never uses it (question 6).
- **`fs`: no rule found reads it** in either source (question 6).
- Ours: `test_brain_v2.py:510` turns 10 px inside the platform end - close to **same**; `gamedata.py:140`
  documents walkAreaX1/X2 as "the x range the mob may wander" - not supported by either source.

### C4. Jumpers
- A mob with a `jump` animation, on the ground, jumps on 25 % of its decisions out of move (C2): upward push 5
  px/tick = 625 px/s, i.e. a hop **89 px high and 0.57 s long** with HC's gravity (98 px / 0.625 s with 2000),
  keeping its walking speed sideways (36 px at speed 0). The next decision comes on landing.
  Source: `Mob.cpp:51, 228-230, 246-247, 284-286`. Field: framebooks `jump` (47 mobs).
- Ours: `world.py:29` `jump_h 140` ("Pigs jump ~45-100 px") - **same** order; `gate_y_air 90`.

### C5. Flyers
- No gravity, no footholds: on each move decision a flyer also picks straight / up / down with 1/3 each, and is
  pushed by the same force on y. Its stand animation is its fly animation. Source: `Mob.cpp:55-59, 200-213,
  309-310`.
- Ours: nothing special for flyers - **missing**.

### C6. Which animation plays, and for how long
- stand <-> `stand` frames, move <-> `move` (flyers: `fly` for both), jump <-> `jump`, hit <-> `hit1`, death <->
  `die1`; each frame shows for its `delay` ms (mob.json frames), the loop restarts at the end. A stance change
  restarts its animation at frame 0. The sprite is stored facing left and is mirrored when the mob faces right,
  unless `noFlip`. Source: `Mob.cpp:55-68, 118-139, 338`.
- The stance number sent over the network: move 2, stand 4, jump 6, hit 8, die 10, +1 when facing left
  (`Mob.h:40-69`).
- The name tag and HP bar over a mob show for 2 s after a hit (`Mob.cpp:407-426`).
- Ours: `perception` matches frames by picture; lengths come from mob.json - **same** data.

---

## D. A mob that was hit

### D1. The knockback
- **Rule (HC):** a hit knocks a mob back when **the damage of that hit line >= the mob's `pushed`**, and only on
  the client that controls the mob (others see it through the controller's movement report). The mob turns to
  **face the attacker** and enters the hit stance; while in it a mob that can move is pushed **away** with 0.2
  px/tick^2 on the ground (0.1 in the air). The hit stance lasts **31 ticks = 0.248 s** (the decision counter is
  set to 170 and the next decision comes above 200); then it always starts moving, direction 50 / 50 (C2).
- In numbers: the push balances the friction at 1.0 px/tick = 125 px/s; over the 31 ticks the mob travels
  **~27 px**, then coasts ~4 px more if it stands (speed x0.8 per tick). A second hit during the hit stance
  restarts the 31 ticks. At a platform end it stops (C3).
- Source: `Mob.cpp:44, 220-227, 243-245, 554-570`; `Combat.cpp:260-268` (applied at the hit's landing time, F2).
  Field: mob.json info `pushed`.
- **HC's 0.248 s is not the `hit1` animation's length** (600 ms for many mobs in mob.json): HC ends the stance
  by its counter. Which one the original client uses: **NOT FOUND** (question 7).
- Ours: `brain/v2/combat.py:76` `KNOCK_PX 30` per tick as the sign of a knockback - **same** size;
  `world.py:38` `hit_s 0.6` (the `hit1` animation) - **differs** from HC's 0.248 s; FakeMobs
  (`test_brain_v2.py:501`) hold the hit 0.6 s and do not move the mob - **differs**.

### D2. Turning on the attacker and following (aggro), the controller
- **Who controls (CO):** when a mob spawns, or its controller leaves, the server gives it to the living, visible
  player on the map who controls the **fewest** mobs (`server/life/Monster.java:1834-1871, 1959-1971`). The
  controller's client is told "you control this mob", with or without aggro (`Monster.java:2102-2104`); HC:
  mode 1 = control, 2 = control with aggro (`Mob.cpp:352-356`).
- **When it changes (CO):** on every damaging hit the server adds the damage to that attacker's aggro entry. If
  the attacker is not the controller and is the leading damage dealer on that mob, **control moves to the
  attacker, with aggro**; otherwise the present controller gets aggro (`Monster.java:2074-2100`,
  `net/server/coordinator/world/MonsterAggroCoordinator.java:150-199, 295-325`). When a player leaves the map
  the mob is re-assigned as above.
- **For how long (CO, source's own design):** aggro entries are aged every 5 s (`config.yaml:332`
  `MOB_STATUS_AGGRO_INTERVAL`); an entry's damage instances expire on a schedule that starts from 120 s / 5 s
  rounds and halves with each instance and each expiry; when a non-boss mob's last entry expires its aggro is
  cleared (`MonsterAggroCoordinator.java:110-148, 201-269`). CO's comment says the damage-based leader is its
  own choice over "first come first served" (`Monster.java:2078`).
- **How an aggroed mob moves (chases, turns toward us, picks an attack): NOT FOUND.** HC stores the aggro flag
  and never reads it (`Mob.cpp:355`, as HISTORY.md noted); CO leaves the movement to the client. Question 5.
- `firstAttack` (16 mobs: mobs that attack unprovoked): CO loads it (`LifeFactory.java:155-164`); its use is
  the auto-aggro option, off by default (`config.yaml:333` `USE_AUTOAGGRO_NEARBY: false`).
- Ours: no notion of a controller or aggro - **missing**.

### D3. HP
- **CO:** HP goes down by the damage of each line the attacker's client reports; the server keeps, per attacker,
  the total damage dealt (for EXP and for the drop's owner) and sends the mob's HP as a percentage to the
  attacker (`Monster.java:354-477`). In CO a mob heals only through mob skills (`Monster.java:483`);
  `hpRecovery` / `mpRecovery` (27 / 24 mobs): **no rule found reads them.**
- Field: mob.json info `maxHP`.
- Ours: FakeMobs die after 3 hits (`test_brain_v2.py:487`) - **differs** (HP and damage are not modelled).

### D4. Death
- **CO:** at the killing hit the mob is removed from the server's map at once; EXP is given, drops are created
  (H1), the spawn point is told the death with the `die1` animation's length, and every client is told "killed,
  with animation 1" (`server/maps/MapleMap.java:1345-1444`, `Monster.java:778-851, 927`). The `die1` length =
  the sum of its frames' `delay`, 500 ms when there is none (`server/life/MonsterStats.java:133-139`,
  `LifeFactory.java:173-178`).
- **HC:** animation 1 = the mob stops moving and plays `die1` once; **the body is gone when `die1`'s last
  frame ends**. Animation 2 = fades out over 40 ticks = 0.32 s. Animation 0 = vanishes at once (leaving view).
  A dying mob no longer touches us and cannot be targeted (`Mob.cpp:146-178, 388-405, 584-594`). For our own
  hit the death is shown when the hit lands (F2), not when the key is pressed (`Mob.cpp:558-561`).
- A mob with `revive` spawns its listed mobs at its place after the `die1` length (`Monster.java:782-843`; 2 of
  our mobs).
- Ours: `world.py:39` `die_sure`; FakeMobs dying 0.8 s (`test_brain_v2.py:515`) - **differs** (the rule is the
  mob's own `die1` length).

---

## E. Spawning

All CO. The periods are config values of the emulator (`config.yaml`), so they describe v83 servers of this
family, not necessarily Classic World's (table 3).

### E1. Spawn points and `mobTime`
- Every mob entry of a map (`life`, type m) is a spawn point: mob id, x, y (moved down to the foothold under it,
  -1 px), foothold, facing `f`, `hide`, `mobTime` (`server/maps/MapFactory.java:59-83, 116-129`,
  `MapleMap.java:3013-3021`).
- A spawn point holds **at most one living mob**. It may spawn again when it has none and its time has come
  (`server/life/SpawnPoint.java:69-74`):
  - `mobTime` = 0 (8,268 of our 8,623 spawns): the time is the death + the mob's `die1` length (`SpawnPoint.java:
    89-96`) - i.e. as soon as the body is gone, at the next round (E2).
  - `mobTime` > 0: death + `mobTime` **seconds**.
  - `mobTime` < 0: spawned once when the map loads, never again.
- Fields: map.json mobs `mobTime`, `footholdId`, `flip`, `hidden`, `x`, `y`.

### E2. How often the server refills, how many, which points
- Every **10 s** (`config.yaml:175` `RESPAWN_INTERVAL`; `net/server/task/RespawnTask.java`) each map with at
  least one player runs a round (`MapleMap.java:3541-3574`):
  - the target = ceil((0.70 + 0.05 x min(6, players on the map)) x number of spawn points): 75 % of the spawn
    points with one player, 100 % with six **(source's own design**, `MapleMap.java:3519-3539`; an option spawns
    everything missing instead, `config.yaml:259`, off);
  - to spawn = target - mobs alive; the spawn points are **shuffled** and the first ones that may spawn (E1) are
    used until the number is reached.
- A map with no player on it does not respawn.
- **`mobRate`: no rule found reads it** - CO stores it (`MapleMap.java:134, 198`) and nothing uses it; HC does
  not load it (question 8).
- **The map's mob cap:** `info.fixedMobCapacity`, default 500 (`MapFactory.java:312`, `MapleMap.java:1922`);
  none of our maps has the field. `info.createMobInterval` (default 5000 ms) is the first-spawn delay of a
  `mobTime` 0 point (`MapFactory.java:160`, `SpawnPoint.java:105-107`); none of our maps has it.

### E3. How a new mob appears
- **HC:** a newly spawned mob **fades in over 40 ticks = 0.32 s** (opacity +0.025 per tick); a mob that was
  already there when we arrive is drawn at once (`Mob.cpp:103-112, 162-171`). It starts at the spawn point's
  position on its foothold, in the stance the server sends; if we control it, it decides at once (C2).
- CO sends new spawns with the appear effect -2 and existing ones with -1 (`tools/PacketCreator.java:1432-1442`).
- **`summonType`: no rule found reads it** (question 6).

### E4. The first spawn on an empty map
- When a map is loaded (the first player of the channel enters it), every spawn point that may spawn does so at
  once: the map starts **full** (`MapleMap.java:3013-3021`; `mobTime` -1 points too). After that only E2 applies,
  and E2 is skipped while nobody is on the map, so a map left empty stays as it was left.
- Ours: FakeMobs respawn at their own spawn 6-9 s after death (`test_brain_v2.py:472`) - **differs** (the rule:
  the next 10 s round after the body is gone, at a random free spawn point, up to the target count).

---

## F. Our attacks

### F1. From the key press to the swing
- **HC:** an attack starts only when no attack is running, we are not on a rope / ladder or sitting, and a
  weapon is equipped. Holding the attack key starts the next one on the first tick after the last animation
  ends (`Stage.cpp:159-174`, `Combat.cpp:78-96`, `Player.cpp:230-233`). While it runs we cannot turn, walk-push,
  jump or start another (A5).
- **Which animation:** a plain attack picks at random from the weapon's attack type list. For a **spear**
  (attack type 2): `stabT1` or `swingP1`; lying down: `proneStab` (`Character/Look/CharLook.cpp:450-510`). HC's
  list is shorter than the weapon data: CW's `Afterimage\spear.img` also has `stabT2`, `swingP2`, `swingT2` and
  the finishers `stabTF`, `swingPF`. Which the original client picks, and with what odds: **NOT FOUND**
  (question 9).
- **The swing's length:** the stance's frame delays (CW `Character\00002000.img`: `stabT1` / `stabT2` 300 + 100 +
  350 = **750 ms**, `swingP1` / `swingP2` / `swingT2` 300 + 150 + 350 = **800 ms**, `stabTF` / `swingPF` 100 + 200
  x 3 = 700 ms, `proneStab` 300 + 400 = 700 ms), played faster or slower by the attack speed.
  - **HC's factor:** the animation advances by 8 ms x (1.7 - attackSpeed / 10) per tick, attackSpeed = the
    weapon's `attackSpeed` + the booster's change, i.e. **length = delays / (1.7 - attackSpeed / 10)**
    (`Char.cpp:147-152`, `Player.cpp:191-204`). At attackSpeed 6: / 1.1 -> stab 682 ms, swing 727 ms; at 4: / 1.3
    -> 577 / 615 ms.
  - **`brain/reach.py`'s factor, (10 + attackSpeed) / 16:** at 6: x 1.0 -> 750 / 800 ms; at 4: x 0.875 -> 656 /
    700 ms. **This formula is in neither HC nor CO** (CO never computes a swing length). The two cross near
    attackSpeed 8 (a polearm's usual: 900 ms ours, 889 ms HC - the live swing ends of 0.89-0.92 s fit both) and
    part below it: at a spear's 6 they are 68-73 ms apart (table 3, question 10).
- Fields: `assets/mcw/attacks.json` `stance_ms`, `items` (weapon id -> type, `attackSpeed`); skill 1301002 Spear
  Booster `x` = -2.
- Ours: `brain/reach.py:94` - **differs** from HC, as above.

### F2. When in the swing the hit lands
- **HC:** the targets and their damage are decided **at the press** (from the positions at that tick); the
  result is shown - damage number, hit sound, knockback or death - after a delay = **the sum of the stance's
  frame delays before the frame at which the weapon's trail picture starts**, divided by the speed factor
  (`Char.cpp:154-161`, `CharLook.cpp:589-604`, `Character/Look/Afterimage.cpp:45-54`, `Combat.cpp:356-381`).
  For the spear the trail starts at frame 2 (`stabT1`, `stabT2`, `swingP1`, `swingP2`, `swingT2`), frame 3
  (`stabTF`, `swingPF`), frame 1 (`proneStab`): **400 ms for a stab, 450 ms for a swing, 500 ms for a finisher,
  300 ms lying down** at factor 1; with HC's factor at attackSpeed 6: 364 / 409 / 455 / 273 ms.
- CO: the attack packet carries a per-target delay which the server uses to delay the drop (H1); it does not
  compute it.
- Ours: `brain/reach.py:27` `SWING_LAND_S 0.45` - **same** as a swing at factor 1 (a stab lands 50 ms earlier).
  That the targets are fixed at the press, not at the landing: **missing** in FakeMobs
  (`test_brain_v2.py:490-499` tests reach at the landing time).

### F3. Which mobs an attack hits
- **The box:** the weapon type's box for the stance, from `Afterimage\<type>.img\<weapon level / 10>\<stance>`
  `lt`, `rb`, relative to our feet, mirrored when we face right (`Afterimage.cpp:28-41`, `Combat.cpp:111-132`).
  Spear, level tier 0 (all 11 tiers were not compared here), facing left, (left, top) - (right, bottom):

  | Stance | lt | rb | Reach ahead | Above / below feet |
  |---|---|---|---|---|
  | stabT1 | -130, -33 | -36, -4 | 36..130 px | 33 up .. 4 up |
  | stabT2 | -111, -46 | -24, 0 | 24..111 | 46 up .. 0 |
  | stabTF | -124, -34 | -10, -1 | 10..124 | 34 up .. 1 up |
  | swingP1 | -133, -120 | -51, 24 | 51..133 | 120 up .. 24 down |
  | swingP2 | -116, -122 | -47, 20 | 47..116 | 122 up .. 20 down |
  | swingPF | -144, -123 | -67, 23 | 67..144 | 123 up .. 23 down |
  | swingT2 | -120, -125 | -52, 20 | 52..120 | 125 up .. 20 down |
  | proneStab | -113, -17 | -23, 11 | 23..113 | 17 up .. 11 down |

  Note the box does not start at our body: a mob closer than the box's near edge is outside it unless its own
  body box reaches in.
- **A mob is in reach** when its current frame's body box (`lt` / `rb` at its position) overlaps the attack box,
  and it is alive (not dying) (`Mob.cpp:596-605`).
- **How many:** the mobs in reach are sorted by the distance from our feet to theirs and the closest N are hit;
  N = 1 for a plain attack, the skill's `mobCount` otherwise (`Combat.cpp:168-210`,
  `RegularAttack.cpp:29-39`, `Skill.cpp:176-249`). A skill with its own `lt` / `rb` uses that box instead; a
  skill's `range` (percent) scales the box's **far** edge (`Combat.cpp:113`, `Data/SkillData.cpp:65`).
- CO checks only that the number of mobs is not above the skill's `mobCount` and that each mob is within a
  generous distance (squared distance 200,000 = 447 px for a plain attack) (`AbstractDealDamageHandler.java:
  180-253`).
- Ours: `brain/reach.py:43-70, 99` builds the boxes from the same data against the mob's body box - **same**;
  targeting is "strict closest" (memory, session 8) - **same** as the closest-N rule.

### F4. The damage range, the mob's defence, hit or miss
- **Our range (HC):** max = (STR x 5.0 + DEX) x weapon attack / 100; min = (STR x 5.0 x 0.9 x mastery + DEX) x
  weapon attack / 100, mastery = 0.5 + the mastery skill's `mastery` / 100 (`CharStats.cpp:65-137, 192-195`,
  `Character/PassiveBuffs.cpp:64-65`). 5.0 is HC's multiplier for both spear and polearm. A skill multiplies both
  by its `damage` percent (`Skill.cpp:195-196`).
- **CO's check** of what the client reports: max = ceil((STR x multiplier + DEX) / 100 x weapon attack), the
  multiplier 5.0 for a spear and for a polearm (`client/Character.java:792-809`,
  `client/inventory/WeaponType.java:37-40`, `server/ItemInformationProvider.java:618`). CO's weapon list also has
  3.0 for a spear swing and a polearm stab - the well-known split - but assigns every spear the 5.0 type. So
  **both sources ignore the stab / swing split**; the per-stance multiplier is NOT FOUND as a rule in code
  (question 11).
- **The mob's defence and the level difference (HC):** d = max(0, mob level - our level); min' = min x (1 - 0.01
  x d) - `PDDamage` x 0.6; max' = max x (1 - 0.01 x d) - `PDDamage` x 0.5; each at least 1; the damage of a
  line is uniform between them, x 1.5 on a critical, cut at 999,999 (`Mob.cpp:464-482, 529-552`).
- **Hit or miss (HC):** hit chance = our accuracy / ((1.84 + 0.07 x d) x `eva` + 1), at least 1 %; accuracy =
  DEX x 0.8 + LUK x 0.5 + equipment; a miss shows the "MISS" picture and counts as 0 damage
  (`Mob.cpp:453-462`, `CharStats.cpp:85-91`). With `eva` 0 nothing ever misses.
- CO takes every damage line from the client and only compares it with its maximum (`AbstractDealDamageHandler.
  java:833-870`).
- Fields: mob.json info `PDDamage`, `eva`, `level`; our stats and the weapon's attack are not in our data
  (question 12).
- Ours: nothing computes damage - **missing**.

### F5. The damage digits
- **HC:** one number per damage line, created at the press and shown at the landing time (F2). It appears at
  the mob's head position (the frame's `head` point), each further line of the same attack 30 px higher (36 px
  for a critical). It rises 0.25 px/tick = **31 px/s** and fades: fully opaque for 250 ms, then fading to
  nothing over 500 ms - **750 ms in all**. The digits alternate 2 px up / down; a digit is 20-24 px wide in
  HC's table, the first one drawn in the larger set (`Gameplay/Combat/DamageNumber.cpp:26-80, 129-190`,
  `DamageNumber.h:53`, `Combat.cpp:385-401`). Pictures: `Effect/BasicEff.img` `NoRed0/1` (ours on a mob),
  `NoCri0/1` (critical), `NoViolet0/1` (damage on us, starts 60 px above our feet, 10 px left).
- HC's widths are for the normal digit size; our standard setting is the **small** damage numbers (HANDOFF,
  2026-11-21), which HC does not have (question 13).
- Ours: the scene model treats digits as "off the model" pixels; no digit rule - **missing**.

### F6. Skills in the client files (Classic World)
`Skill\100.img.xml` (Warrior) and `Skill\130.img.xml` (Spearman), names from `String\Skill.img.xml`. **Classic
World's skill list is not v83's** (v83: 1001003 Iron Body, 1001004 Power Strike, 1001005 Slash Blast, 1301004
Iron Will, 1301005 Hyper Body; no active Final Attack, no Rush at second job): ids, names and several effects
differ, so HC's and CO's per-skill code does not apply by id (table 3). Values: level 1 / middle / max.

| Id | Name | Kind | MP (HP) cost | Damage % | Mobs | Box | Timing |
|---|---|---|---|---|---|---|---|
| 1000000 | Improved HP Recovery (15) | passive | - | - | - | - | `y` 20 / 34 / 50 |
| 1000001 | Max HP Increase (15) | passive | - | - | - | - | `mhpR` 10 / 17 / 25 % |
| 1000002 | Precise Strikes (15) | passive | - | - | - | - | `accX` 5 / 12 / 20, `crtX` 1 / 3 / 5 |
| 1001000 | Iron Body (20) | buff | 15 | - | - | - | action `alert2` (3 x 200 = 600 ms); lasts 300 / 450 / 600 s; defence +20 / 30 / 40 % |
| 1001001 | Power Strike (20) | attack | 4 / 7 / 12 | 160 / 210 / 260 | 1 | none of its own: the weapon's box (F3) | no action of its own: the plain attack's stance and length (F1, F2) |
| 1001002 | Slash Blast (20) | attack | 6 / 9 / 14 MP + 8 / 11 / 16 HP | 70 / 100 / 130 | 6 | the weapon's box, far edge x `range` 130 / 150 / 150 % | as Power Strike |
| 1300000 | Spear Mastery (20) | passive, spear | - | - | - | - | `mastery` 1 / 5 / 10, `prop` 1 / 11 / 20 % (ignore defence) |
| 1300001 | Polearm Mastery (20) | passive, polearm | - | - | - | - | `mastery` 1 / 5 / 10, `x` 1 / 11 / 20 (speed) |
| 1301000 | Final Attack: Spear (30) | attack, usable for 60 s after a 25 % roll on attack skills | 8 / 12 / 16 | 260 / 305 / 350 | 1 | none of its own | no action of its own |
| 1301001 | Final Attack: Polearm (30) | same, polearm | 8 / 12 / 16 | 260 / 305 / 350 | 1 | none | none |
| 1301002 | Spear Booster (20) | buff, spear | 30 / 20 / 10 MP + 30 / 20 / 10 HP | - | - | - | action `alert2` 600 ms; lasts 100 / 200 / 300 s; attackSpeed `x` -2 |
| 1301003 | Polearm Booster (20) | buff, polearm | same | - | - | - | same |
| 1301004 | Iron Will (30) | buff | 10 / 17 / 25 | - | - | - | action `alert2` 600 ms; lasts 150 / 225 / 300 s; defence +20 / 35 / 50; `prop` 5 / 20 / 35 % no knockback |
| 1301005 | Rush (20) | attack, moves us | 35 / 25 / 15 | 60 / 69 / 80 | 6 | own: lt (-200, -50) rb (0, 0) at level 1, lt (-220, -50) from level 11; `range` 130 / 150 / 150 % | action `rushT` / `rushO`: 100 + 300 = 400 ms; cooldown `cooltime` 2 s |

- Rush in HC: we slide to the last hit mob's x during the attack's delay, stopping at a platform end
  (`Player.cpp:322-330`, `Combat.cpp:239-247`) - HC has it for the fourth-job Rush ids only.
- MP costs are checked by CO against the skill's `mpCon` (`AbstractDealDamageHandler.java:177`).
- **Which key is which:** in the 30-minute capture `q` was pressed 835 times, `e` 130, `w` 30 (HANDOFF). The
  files cannot say what is on a key (question 14).

---

## G. EXP and levels

- **The EXP of a kill (CO):** on death, each player who damaged the mob gets `exp` x (their damage) / (the
  mob's max HP + anything it healed). **A solo player (no party)** gets exactly that share: x (0.8 x own level /
  own level + 0.2) = x 1.0. Killing a mob alone = the full `exp`. The last hit does not matter; a player who
  left the map still "owns" their share and nobody gets it. Then the server's EXP rate and buffs multiply it.
  Source: `server/life/Monster.java:602-690` (`distributeExperience`), `535-546`, `728-758`.
- **In a party (CO):** the party's damage is pooled: pool = `exp` x party damage / max HP. Each member on the map
  gets pool x (0.8 x member level / sum of the members' levels + 0.2 for the member who did the most damage),
  plus a bonus of 5 % x the number of members on top (members > 1). Options limit sharers to within 5 levels of
  the mob or of a damaging member (`Monster.java:548-600`, `config.yaml:293-297`). CO credits a GMS formula page
  for it (`Monster.java:665`).
- **The level table (CO):** EXP needed to go from level L to L + 1, `constants/game/ExpTable.java:25`:
  1: 15, 2: 34, 3: 57, 4: 92, 5: 135, 6: 372, 7: 560, 8: 840, 9: 1,144, 10: 1,242, 11: 1,573, 12: 2,144, 13:
  2,800, 14: 3,640, 15: 4,700, 16: 5,893, 17: 7,360, 18: 9,144, 19: 11,120, 20: 13,477, 21: 16,268, 22: 19,320,
  23: 22,880, 24: 27,008, 25: 31,477, 26: 36,600, 27: 42,444, 28: 48,720, 29: 55,813, 30: 63,800, **31: 86,784**,
  32: 98,208, 33: 110,932, 34: 124,432, 35: 139,372 (to 200 in the file). Classic World's own table is not in
  our client export (question 15).
- Field: mob.json info `exp` (120 of 128 mobs).
- Ours: memory "EXP is split by damage" - **same**; the HUD's EXP is read, no table - **missing**.

---

## H. Drops

### H1. When a drop appears
- **CO:** the drops are rolled at the killing hit, on the server, and announced with a **delay = the attack's
  per-target delay** that the killer's client sent (so they appear when the killing hit lands, F2)
  (`AbstractDealDamageHandler.java:521, 761`, `MapleMap.java:1275-1301, 1421-1427`). The owner = the player who
  did the most damage, else the killer (`Monster.java:849-850, 978`).
- Each table entry is rolled alone: chance x drop rate out of 1,000,000 (`MapleMap.java:665-669`).

### H2. The flight and where it lands
- **Where (CO):** the k-th drop of a kill (k = 1, 2, 3 ...) lands at the mob's x + 0, +25, -25, +50, -50 ... px
  (40 px steps for an "explosive reward" mob), on the foothold found below the point 85 px above the mob's
  feet, x clamped to the map's limits; if that is outside the map, at the mob's place
  (`MapleMap.java:564-581, 665-698`).
- **The flight (HC):** it starts at the mob's position (4 px up), with 5 px/tick = 625 px/s upward and a
  sideways speed of (landing x - start x) / 48 px/tick, falls by the normal gravity (A4), **spins** 0.2 rad per
  tick, and when it meets the ground it is put exactly on the landing point. On level ground that is ~0.57 s
  (HC's gravity) after it appears. Then it **bobs**: 5 px up and down, one cycle per 251 ticks = 2.0 s
  (`Gameplay/MapleMap/Drop.cpp:22-81`).
- Ours: `perception/drops.py` finds resting and flying drops by picture; no flight model - **missing** (not
  needed by perception; the engine needs it).

### H3. How long it lies
- **CO:** a drop expires **180 s** after it was dropped (`config.yaml:316` `ITEM_EXPIRE_TIME`, "recommended to be
  set up to 3 minutes"), and expired drops are removed by a task that runs **every 10 s** (`config.yaml:322`
  `ITEM_EXPIRE_CHECK`): so each drop goes 180-190 s after it fell, and drops go in rounds 10 s apart
  (`MapleMap.java:865, 920-960`).
- **Next to our footage** (PLAN-loot.md section 13: 40 of 40 drops went 118.5-128.5 s after coming to rest, in
  rounds ~10.1 s apart): the **same mechanism** - a lifetime plus a 10 s sweep - with **120 s** where Cosmic's
  config has 180 s. The 180 is a config value of the emulator, not client code; the user's rule "a drop is
  expected for 2 minutes, at most 130 s" stands.
- **How it goes (HC):** removal type 0 (expired) = fades out in place over 48 ticks = **0.38 s**; type 1 =
  vanishes at once (`Drop.cpp:83-126`). Our footage showed ~1 s (question 16).

### H4. Who may take it, and when that changes
- **CO:** for the first **15 s** only the owner (or the owner's party) may take it; after 15 s anyone. A mob
  with `publicReward` or `explosiveReward` drops free-for-all at once (`server/maps/MapItem.java:123-157`,
  `MapleMap.java:739`). Nobody may take a drop in its **first 400 ms** (`client/Character.java:1983`).
- Classic World (memory "drops are private"): other players' drops are not even shown to us without a party.
  CO has an option in that direction for quest items only (`MapleMap.java:1068-1080`); a fully private drop is
  a Classic World rule v83 code does not have (table 3).

### H5. The pickup: reach, the animation, when a press takes nothing
- **Reach (HC):** with the pickup key held, each tick one drop is taken whose 32 x 32 px box contains our feet:
  the box runs from the drop's position (its top-left; the resting drop is drawn 4 px above its landing point
  and bobs) 32 px right and 32 px down (`Drop.cpp:128-134`, `MapDrops.cpp:109-130`, `Stage.cpp:176-177,
  244-251`). So in HC we must stand **0-32 px to the right of the drop's left edge** - narrower than what our
  footage shows (pickups from within ~50 px). The original client's box: **NOT FOUND** (question 17).
- **The server's side (CO):** refuses when the drop is younger than 400 ms, not ours yet (H4), already taken,
  farther than 800 px sideways or 600 px up / down, or the inventory has no room; a refusal just re-enables our
  actions, nothing shows (`ItemPickupHandler.java:53-61`, `Character.java:1977-2060`).
- **A press that takes nothing** (309 of 679 presses took a drop in the capture): by the rules above = no drop's
  box under our feet at that tick, or one of the server's refusals. Also: no pickup while attacking, climbing or
  sitting (`Stage.cpp:159`).
- **The animation (HC):** removal type 2 (taken by a player) = the drop hops up at 4.5 px/tick = 562 px/s, flies
  toward the taker (sideways speed = half the taker's + (distance - 16) / 48 per tick) and fades over 48 ticks =
  **0.38 s** (`Drop.cpp:83-103, 118-124`). Our footage: a hop toward us ~0.5 s, then a short fade - same shape.
- Ours: `brain` presses the pickup key by sight (`--loot --loot-sight`); no reach rule in code - **missing**.

### H6. A pet's pickup, meso amounts, drop tables
- **Pet (CO):** a summoned pet picks up through the same server checks; mesos need the Meso Magnet equip, items
  the Item Pouch (`net/server/channel/handlers/PetLootHandler.java:44-84`). The removal is shown with type 5
  (flies to the pet). HC has no pet pickup.
- **Meso amount (CO):** a random whole number from the table entry's minimum up to (not including) its maximum,
  x the meso rate (`MapleMap.java:675-688`). **The picture (HC):** below 50 the bronze coin, 50-99 gold, 100-999
  the bundle, 1,000 and more the bag (`MapDrops.cpp:67-72`).
- **Drop tables are server data.** Cosmic keeps them in its database: table `drop_data` (schema
  `src/main/resources/db/tables/009-drop.sql`, rows `src/main/resources/db/data/152-drop-data.sql`, global drops
  `151-global-drop-data.sql`), read by `server/life/MonsterInformationProvider.java`. None copied. They are
  Cosmic's, not Classic World's.

---

## I. Potions and recovery

- **What a potion restores (CO):** from the item's `spec` in `Item.wz`: `hp`, `mp` (points), `hpR`, `mpR`
  (percent of the maximum), `time` for buffs (`server/StatEffect.java:241-245`). **Our export does not hold
  `spec`** (`Item\items.json` has name, kind and picture only), and which potions are on the keys is not in any
  file (question 18). Improved HP Recovery (1000000) "boosts HP recovery from items" by its `y` - the formula is
  NOT FOUND.
- **Natural recovery:** it is computed by the client, which reports "I healed N" to the server; CO only limits
  it: not more often than every 1.5 s, and HP at most 77 x the map's `recovery` x 1.5 per report
  (`net/server/channel/handlers/HealOvertimeHandler.java:46-72`). HC does not implement it. **The amounts and
  the period (standing, sitting, on a rope, with Improved HP Recovery): NOT FOUND** (question 19).
- Field: map.json info `recovery` (2 maps, 2.0).
- Ours: `config.py:62-63` drink at HP < 50 %, MP < 10 % - a policy, not a rule.

---

## J. The camera

- **HC:** the camera's target puts our feet at the centre of the view on both axes. Each tick, per axis, if the
  camera is 5 px or more off its target it moves by (distance) x 12 / (view size in px): a smooth chase with a
  time constant of view / 12 ticks - 1024 px wide: 85 ticks = 0.68 s; **1366 wide: 114 ticks = 0.91 s; 768
  high: 64 ticks = 0.51 s**. Within 5 px it does not move (a dead zone). On entering a map the camera is put on
  the target at once (`Gameplay/Camera.cpp:33-83`, `Stage.cpp:99-108, 157`).
- **Where it stops:** the view never shows beyond the map's `VRLeft / VRTop / VRRight / VRBottom`; a map without
  them uses the foothold limits of A9 (left + 25, right - 25, top - 300, bottom + 100). If the map is narrower
  (or lower) than the view, the camera is pinned to the left (top) bound (`Camera.cpp:56-64, 85-89`,
  `MapInfo.cpp:22-35`).
- So "what the screen shows" = a 1366 x 768 window centred on our feet, clamped to the VR bounds, lagging our
  motion by the chase above. **HC's centring and its 12 / view-size speed are its author's numbers** for an 800 or
  1024 px client; the original client's vertical offset of the character and its follow speed: **NOT FOUND**
  (question 20).
- Fields: map.json `vrBounds` (356 of 364 maps), info `VRLeft/Top/Right/Bottom`.
- Ours: `maplebrain/scene.py` finds the camera from the picture each frame (exact to the pixel) and uses
  `vrBounds` only for the rendered area (`scene.py:35, 98-100`) - the follow rule is **missing** (not needed by
  perception; the engine and the viewer need it).
- **How the scenery is drawn over that view** (for the viewer): **HC** places a background at
  `rx x (centre - view) / 100` (our `scene.py` uses the same formula with the client's integer arithmetic), moves a
  back of type 4-7 along the map by `rx / 16` px per 8 ms step (= 7.8 x rx px a second), and reads the map's
  `cloud` flag without drawing anything (`MapBackgrounds.cpp:54-153`, `MapInfo.cpp:41`). On Classic World footage
  the moving backs go at `5 x rx` px a second, their row is rounded differently from a still back's, the `cloud`
  flag means 7 weather cloud pictures drifting over the field, and a back picture with `blend 1` is added to what
  is under it - **measured, not from a source**: PLAN-moving-scenery.md, "What was measured" 2-4 (added 2026-11-21).

---

## K. Clocks

| Clock | Value | Source |
|---|---|---|
| The client's update step | 8 ms (125 per second), drawing interpolated between steps | HC `Constants.h:29`, `MapleStory.cpp:92-109` |
| A mob's decision | every > 1.6 s, at an animation end | HC `Mob.cpp:244-251` |
| A mob's hit stance | 0.248 s | HC `Mob.cpp:244, 565` |
| A new mob's fade-in | 0.32 s | HC `Mob.cpp:162-171` |
| Our time safe from hits | 2 s | HC `Char.cpp:200` |
| No rope grab after leaving one | 1 s | HC `Player.cpp:455-458` |
| A damage number | 0.75 s | HC `DamageNumber.cpp:79, 181-184` |
| Another player's attack shown | 400 ms after its packet | HC `Combat.cpp:270-273` |
| Respawn round | every 10 s (config) | CO `config.yaml:175` |
| A spawn point free again | the `die1` length (mobTime 0) or mobTime s after the death | CO `SpawnPoint.java:89-96` |
| Drop expiry | 180 s (config; our footage: 120 s), swept every 10 s | CO `config.yaml:316, 322` |
| A drop is the owner's | 15 s; untouchable its first 0.4 s | CO `MapItem.java:131-133`, `Character.java:1983` |
| Aggro bookkeeping | every 5 s (config) | CO `config.yaml:332` |
| Natural recovery report | at most every 1.5 s | CO `HealOvertimeHandler.java:49` |
| Mob status effects | every 200 ms (config) | CO `config.yaml:329` |

---

# Table 1. Every field -> the rule that reads it

### mob.json `info` (128 mobs; count = mobs having the field)

| Field | Count | Rule |
|---|---|---|
| level | 128 | F4 (level difference in damage and hit chance); G (party EXP ranges); HC name tag colour at +/-10 levels (`Mob.cpp:411-416`) |
| maxHP | 128 | D3, G (the EXP share's denominator) |
| maxMP | 128 | B4 (CO: MP for mob skills / attacks) |
| PADamage | 128 | B1 (touch damage 80-100 % of it) |
| PDDamage | 128 | F4 (defence against our hits) |
| MADamage, MDDamage | 128 | HC loads both; MDDamage in the magic damage formula (`Mob.cpp:466-479`); MADamage: no rule found reads it |
| acc | 128 | HC loads it (`Mob.cpp:42`); no rule found uses it (it belongs to the mob's chance to hit us: B1 NOT FOUND) |
| eva | 128 | F4 (our hit chance) |
| pushed | 128 | D1 (knockback when a hit line >= it) |
| bodyAttack | 127 | B1 (touching hurts) |
| summonType | 127 | no rule found reads it |
| fs | 126 | no rule found reads it |
| exp | 120 | G |
| speed | 107 | C1 |
| undead | 102 | HC and CO load it; no rule of this document uses it |
| hideLevel | 101 | no rule found reads it |
| elemAttr | 80 | CO elemental weakness / resistance (`LifeFactory.java:189`): not for a warrior's plain hits |
| link | 45 | our build: frames borrowed from another mob; neither source needs it |
| hpRecovery, mpRecovery | 27, 24 | no rule found reads it |
| attack | 26 | B4 (CO: `conMP`, `attackAfter`, the animation length); the rest NOT FOUND |
| skill | 18 | B4 (CO mob skills) |
| boss | 16 | CO: boss drop rate, aggro never cleared, HP bar |
| firstAttack | 16 | D2 (CO loads it; auto-aggro option, off) |
| mobType | 15 | no rule found reads it |
| flySpeed | 13 | C1 |
| category | 9 | no rule found reads it |
| hideName | 6 | no rule found reads it |
| invincible | 5 | no rule found reads it |
| revive | 2 | D4 |
| notAttack | 1 | HC loads it (`Mob.cpp:50`), never uses it |
| noFlip | 1 | C6 (never mirrored) |
| default | 1 | a picture node, not a stat |
| damagedByMob, PDRate, MDRate, fixedDamage | 1 each | no rule found reads it (post-v83 fields; CO has `removeAfter`, `dropItemPeriod` below) |
| dropItemPeriod | 1 | CO: a mob that drops items on a timer (`LifeFactory.java:165`) |
| removeAfter | 1 | CO: the mob leaves by itself after this many seconds (`LifeFactory.java:129`) |
| (frames) lt, rb | - | B1, F3 (the body box); (frames) head: F5; delay: C6, D4; framebooks move / jump / fly: C2-C5 |

### map.json

| Field | Rule |
|---|---|
| mobs: id, x, y, footholdId, flip (`f`) | E1, E3 |
| mobs: mobTime | E1 |
| mobs: walkAreaX1 / X2 (`rx0` / `rx1`) | no rule found reads it (C3) |
| mobs: hidden (`hide`) | CO loads it (`MapFactory.java:80`); no spawn rule found uses it |
| mobs: spriteY (`cy`), index | CO loads `cy`; no rule |
| mobs: forcedZPage, forcedZMass, limitedname, useDay, useNight | no rule found reads it (not v83 fields) |
| footholds (x1, y1, x2, y2, prev, next, layer) | A1-A6, A9, C3, H2 |
| footholds: forbidFallDown (17,271), cantThrough (150), piece, groupId | no rule found reads it (A6, question 3) |
| ladderRopes (x, y1, y2, isLadder) | A7 |
| vrBounds / info VRLeft, VRTop, VRRight, VRBottom | J; CO: the map area for drop placement (`MapFactory.java:171`) |
| mobRate / info.mobRate | no rule found reads it (E2) |
| info.town, isTown | HC loads it; CO: return-map logic. No movement rule |
| info.swim | HC: swimming physics in place of walking (`MapInfo.cpp:45`, `Physics.cpp:125-146`); 0 of our maps have it set |
| info.fly | no rule found reads it (HC flies only when `swim`) |
| info.recovery | I (CO heal limit) |
| info.returnMap, forcedReturn | CO map changes (death, scrolls) |
| info.fieldLimit | HC loads it, CO: which actions are barred (jump skills, potions ...) |
| info.timeLimit | CO: forced return after N seconds |
| info.cloud, bgm, mapMark, hideMinimap | HC: clouds, music, the minimap. No game rule |
| info.MRLeft / MRTop / MRRight / MRBottom, LBBottom | no rule found reads it (not v83 fields) |
| info.limitSpeedAndJump (33 maps) | no rule found reads it - by its name it bears on A1 / A3 (question 21) |
| info.moveLimit, fieldType, fieldLimit2, fieldLimit_tw, version, standAlone, partyStandAlone, quarterView, noMapCmd, AmbientBGM, AmbientBGMv, fieldScript, onFirstUserEnter, onUserEnter, mapDesc, personalShop, hiredMerchant, genReturnMap, syncEffectObjectOnEnter, miniMapOnOff, housing, reviveCurField, noChair, limitUseShop, limitUseTrunk, offSoulAbsorption, noHekatonEffect, blockScriptItem, vanishPet, vanishAndroid, vanishDragon, limitUserEffectField, limitUI | no rule found reads it (scripts, shops and post-v83 flags; `onUserEnter` / `fieldScript` run server scripts in CO) |
| (absent in all our maps) info.fixedMobCapacity, createMobInterval | E2 defaults: 500 mobs, 5000 ms |
| portals, npcs, miniMap, cover | not rules of this document |

### Physics.img (raw value -> in our units)

| Field | Raw | Ours | Rule |
|---|---|---|---|
| walkForce | 140000 | 1400 px/s^2 | A1 |
| walkSpeed | 125 | 125 px/s | A1, A3 (the jump's sideways cap), A4 |
| walkDrag | 80000 | 800 px/s^2 | A1 |
| slipForce | 60000 | 600 px/s^2 | A2 (named; its use NOT FOUND) |
| slipSpeed | 120 | 120 px/s | A2 (same) |
| floatDrag1 | 100000 | 1000 px/s^2 | A4 (x floatCoefficient = 10 px/s^2 air drag with no key) |
| floatDrag2 | 10000 | 100 px/s^2 | A4 (air control 2 x it; drag at the fall cap) |
| floatCoefficient | 0.01 | 0.01 | A4 |
| swimForce | 120000 | 1200 px/s^2 | no rule found reads it (RU does not cover swimming; HC swims by its own constants) |
| swimSpeed | 140 | 140 px/s | same |
| swimSpeedDec | 0.9 | 0.9 | same |
| flyForce | 120000 | 1200 px/s^2 | no rule found reads it |
| flySpeed | 200 | 200 px/s | no rule found reads it |
| flyJumpDec | 0.35 | 0.35 | no rule found reads it |
| gravityAcc | 2000 | 2000 px/s^2 | A3, A4 |
| fallSpeed | 670 | 670 px/s | A4 |
| jumpSpeed | 555 | 555 px/s | A3, A7 (rope jump = half) |
| maxFriction | 2 | 2 | no rule found reads it (foothold friction; RU sets walkAcc and walkDrag to 1) |
| minFriction | 0.05 | 0.05 | same |

HC reads none of Physics.img (its constants are in `Physics.cpp:22-28` and `Player.cpp:465-483`).

---

# Table 2. Our code against the rules

| Ours | Value | The rule | Verdict |
|---|---|---|---|
| `nav/sim.py:12` WALK_FORCE / SPEED / DRAG | 1400 / 125 / 800 | A1 (RU) | same; the speed stat missing |
| `nav/sim.py:13` GRAVITY / FALL_SPEED / JUMP_SPEED | 2000 / 670 / 555 | A3, A4 (RU) | same; the jump stat missing |
| `nav/sim.py:18-19, 66` JUMP_VX | speed x 155 / 125 at take-off | A3: + 80 % of top speed, capped at the walking speed | differs (question 1) |
| `nav/sim.py:123` air | sideways speed frozen | A4: air control 200 px/s^2 toward 8.9 px/s, drag 10 px/s^2 | differs |
| `nav/sim.py:128-130` landing | speed set to 0 | A5: speed kept, then dragged at 800 | differs |
| `nav/sim.py:58-63` drop through | any platform below | A6: only when the next foothold is < 600 px below | differs |
| `nav/sim.py:14` CLIMB_SPEED | 125 | A7: speed stat / 100 px/tick = 125 px/s | same |
| `nav/sim.py:15` GRAB_DX | 10 | A7: within 10 px | same |
| `nav/sim.py:16-17` ROPE_JUMP_VY / VX | 300 / 125 | A7 (RU): 277.5 / 162.5 | differs |
| `nav/sim.py:117` rope grab in the air | up held, not in the first instant of a jump | A7: any tick with up held; no grab for 1 s after leaving a rope | differs |
| `nav/sim.py:79-80` slopes | flat rule everywhere | A2 | differs |
| `config.py:102-104` Nav.walk_speed / jump_speed / gravity | 125 / 555 / 2000 | A1, A3, A4 | same |
| `config.py:98` Nav.jump_height 70 | measured 60-80 | A3: peak 77 px at 100 % jump | same (within its margin) |
| `config.py:100, 105` Nav.jump_reach 85, jump_vx 155 | measured | A3: 125 px/s x 0.555 s = 69 px on level ground | differs (question 1) |
| `config.py:110` Nav.climb_speed | 125 | A7 | same |
| `config.py:108, 111-115` rope_grab, grab_body, rope_leap, leap_drop, leap_land | measured | A7 gives the take-off speeds (277.5 up, 162.5 sideways) they follow from | not derived from the rule |
| `brain/moves.py:14-15` WALK, DRAG | 125, 800 | A1 | same |
| `brain/moves.py:16` LAG | 0.1 s | our own pipeline's delay: no game rule | - |
| `perception/world.py:21, 24` gate_x 30 + vmax 160 x time | one cap for all mobs | C1: (speed + 100) x 0.625 px/s per mob (62.5 at speed 0), flyers (flySpeed + 100) x 1.25; D1: knockback up to 125 px/s for 0.25 s (~27 px) | differs: far looser than the rule for walkers |
| `world.py:22-23, 29` gate_y 24, gate_y_air 90, jump_h 140 | - | C4: a jump is 89-98 px high, 0.57-0.63 s | same order |
| `world.py:26` v_half_s 0.6 | - | C2: a decision every > 1.6 s; 1/3 stand, 1/3 each way; always moves after a stand or a hit | rhythm same, odds missing |
| `world.py:38` hit_s | 0.6 s | D1: HC 0.248 s; the `hit1` animation 0.6 s | differs (question 7) |
| `world.py:32-37, 45` lose_s, covered_s, fight_s, offscreen_s, hidden_s | timeouts | no game rule (perception limits); E3: a new mob fades in 0.32 s; D4: a body lasts its `die1` length | - |
| `world.py:39` die_sure | - | D4 | - |
| `brain/reach.py:94` swing length | stance ms x (10 + attackSpeed) / 16 | F1: HC stance ms / (1.7 - attackSpeed / 10) | differs; ours is in neither source (question 10) |
| `brain/reach.py:27` SWING_LAND_S | 0.45 s | F2: 450 ms swing, 400 ms stab (factor 1) | same for swings |
| `brain/v2/combat.py:73` SWING_MARGIN_S 0.02 | live 0.89-0.92 vs 0.90 (polearm) | F1: at attackSpeed 8 ours gives 900 ms, HC 889 ms | fits both factors: it does not decide between them |
| `brain/v2/combat.py:76` KNOCK_PX | 30 px in a tick | D1: ~27 px over 0.25 s | same |
| `tests/test_brain_v2.py:487` FakeMobs speed | 40 px/s | C1: Bubbling's `speed` -> (speed + 100) x 0.625 | differs |
| `test_brain_v2.py:510` FakeMobs turning | 0.2 % per step, never stand | C2 | differs |
| `test_brain_v2.py:498-501` FakeMobs hit | reach tested at landing, 0.6 s hit, no push, 3 hits to die | F2 (targets fixed at the press), D1 (pushed ~27 px, 0.25 s), D3 (HP) | differs |
| `test_brain_v2.py:515` FakeMobs dying | 0.8 s | D4: the mob's `die1` length | differs |
| `test_brain_v2.py:472` FakeMobs respawn | own spawn, 6-9 s | E2: the next 10 s round, a random free point, up to 75 % of the points (one player) | differs |
| `config.py:62-63` potions at 50 % / 10 % | policy | I | - |
| the tracker's drop rule (HANDOFF: 2 minutes, 130 s at most) | from footage | H3: lifetime + 10 s sweep (Cosmic 180 s) | same mechanism |
| `gamedata.py:140` "walkAreaX1/X2 = the x range the mob may wander" | a comment | C3: no rule found reads it | unsupported |

---

# Table 3. Questions for the user

**NOT FOUND in any source**
1. **ANSWERED: our values (see "Decided by the user").** The jump's sideways speed. RU: holding a direction adds 80 % of the top walking speed, capped at the
   walking speed (125 px/s at 100 %). Our `Nav.jump_vx` is 155 px/s, fitted on footage. Is the character's speed
   stat above 100 % (shoes, a skill)? If not, the two disagree and the engine needs your call.
2. **Air control:** RU's account says a held direction "accelerates at 200 px/s^2 toward 8.9 px/s". Whether a
   faster speed in the held direction is kept or braked is not in what I could read of the issue.
3. **Dropping through:** which platforms refuse it? Our footholds carry `forbidFallDown` (a fifth of them) and
   `cantThrough`, which no source reads; HC only has "another foothold less than 600 px below".
4. **Our knockback** in the original client (HC: 187.5 px/s away, 437.5 px/s up - its author's numbers?).
5. **Aggro movement and mob attacks:** how a mob that has aggro moves (chases us, turns), when it uses
   `attack1` / a skill, the attack's reach and landing time. HC has the flag and no behaviour (as HISTORY.md
   noted); CO leaves it to the client. This is the largest gap for the engine.
6. **`rx0` / `rx1` (walkAreaX1/X2), `fs`, `summonType`:** no source reads them. HC keeps mobs on their foothold
   chain instead.
7. **The hit pose's length:** HC 0.248 s by a counter vs the `hit1` animation (0.6 s) our tracker uses.
8. **`mobRate`:** stored by CO, read by nothing.
9. **Which attack stance** a spear's plain attack plays and with what odds (HC: `stabT1` or `swingP1`, 50 / 50;
   the data has five more).
10. **ANSWERED: ours for now, recalculated with tracking.** The swing-length factor: HC `/ (1.7 - attackSpeed / 10)` vs our `(10 + attackSpeed) / 16`, which is in
    neither source. The live polearm swing ends (0.89-0.92 s) fit both; with the spear (attackSpeed 6, or 4
    under Booster) they differ by ~70-80 ms. Which is the rule?
11. **Spear / polearm damage:** both sources use x 5.0 for every hit; the stab (x 3.0 polearm, x 5.0 spear) /
    swing split exists only as unused constants in CO. And Classic World's `mastery` values (1-10) are not
    v83's (10-60): HC's `0.5 + mastery / 100` would give 0.51-0.60.
12. **Our own stats** (STR, DEX, weapon attack, accuracy, the speed and jump stats, the weapon's id and
    attackSpeed): needed for F4, A1, A3; not in any file.
13. **Small damage numbers:** HC only has the normal size (digit widths 20-24 px, rows 30 px).
14. **Which key is which skill:** `q` (835 presses), `e` (130), `w` (30) against table F6. And the skill levels.
15. **Classic World's level table** (CO's is v83's).
16. **A drop's fade when it expires:** HC 0.38 s, our footage ~1 s.
17. **The pickup's reach:** HC's box is 0-32 px to the right of the drop's left edge; our footage shows ~50 px
    around.
18. **The potions on your keys** (item ids) - and their `spec` (hp / mp) is not in our export: extending
    `export.ps1` to write it is another small job, if you want it.
19. **Natural HP / MP recovery:** amounts and period (the client computes it; no source has it).
20. **The camera** in the original client: where the character sits vertically, the follow speed (HC: centred,
    12 / view size per tick, 5 px dead zone).
21. **`limitSpeedAndJump`** (33 maps): no source reads it.
- Also NOT FOUND, smaller: touch damage against our defence and our avoid chance (B1); the slope slide's
  formula (A2); Improved HP Recovery's effect on potions (I).

**Where the sources disagree**
- Walking: RU 125 px/s, 1400 / 800 px/s^2 vs HC 100 px/s with proportional friction. Taken: RU (it is the
  original client and equals our Physics.img).
- Jump: RU 555 px/s vs HC 562.5; gravity RU 2000 vs HC 2187.5; fall cap RU 670 vs HC none; rope jump RU 277.5 up
  / 162.5 sideways vs HC 375 / 160. Taken: RU.
- **Mobs move by HC's physics** (gravity 2187.5, friction 0.2 x v): there is no original-client source for mob
  movement, so C and D carry HC's approximations. If mob speeds matter to the pixel, that is where a difference
  would show.
- Drop lifetime: CO 180 s (a config value) vs our footage 120 s.

**The source's own design, not v83 client code** (CO, inherited from HeavenMS)
- The respawn target by player count (75 % of the spawn points with one player .. 100 % with six) and the 10 s
  round are CO's config and heuristics. Real servers of the time are commonly described the same way, but this
  code is not proof for Classic World.
- The aggro bookkeeping (damage-based leader, the expiry schedule).

**Classic World fields and rules v83 code does not know**
- The whole Warrior / Spearman skill list (F6): ids and effects differ from v83 (Precise Strikes, active Final
  Attack, Rush at second job, Iron Will's id), `mastery` on a 1-10 scale.
- Private drops (other players' drops invisible without a party).
- mob.json: `PDRate`, `MDRate`, `fixedDamage`, `damagedByMob`, `hideLevel`, `category`, `mobType`.
- map.json: `MRLeft..MRBottom`, `LBBottom`, `limitSpeedAndJump`, `fieldLimit2`, the `vanish*` / `limit*` flags,
  spawn fields `forcedZPage`, `forcedZMass`, `limitedname`, `useDay`, `useNight`.
- The export run on 2026-11-21 listed 129 mobs; `assets/mcw` has 128 (not looked into).
