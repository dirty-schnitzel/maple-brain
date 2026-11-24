# Labelling by eye - the brief every labeller of PLAN-tracker step 1 follows

You look at sheet images (PNG) of MapleStory footage and write one judgment per case. The reference is your look:
judge only by what the pictures show. Do NOT read or run anything else of the project for answers: not
cases.json, b_cases.json, any other *.jsonl in tools/perc/track/judged/, the prototypes' outputs or code. You may
make enlarged crops of a sheet to look closer: `C:\Users\Yoav\dev\maple-work\.venv\Scripts\python.exe` with cv2
(headless: write a PNG into your own scratch folder, then Read it). Never write anywhere but your output file
(and your scratch folder).

The game: MapleStory (2D side view). Our character is a warrior with a polearm, name tag "JenkinsJob" (helmet,
dark armour). Other characters carry their own name tags; pets carry small name tags too ("Brown Puppy", "White
Bunny", "Snail" ...). Mobs: Bubbling (blue drop, Kerning subway "Line 1"), Horny Mushroom (blue-spotted cap), Zombie
Mushroom (grey cap, talisman), Stirge (flying bat), Evil Eye (yellow one-eyed lizard), Jr. Boogie (small ghost),
Drake (dragon), Slime (green jelly), Green Mushroom. A hit mob flinches (hit pose), a dying mob plays its death
animation and fades. Damage numbers are coloured digits over mobs; skill effects are bright arcs / sparks.
Purple padding on a crop = outside the game frame.

Output: one JSON object per line, `{"case": K, ...fields}` - K = the case number printed in the sheet's header.
Write every case of your range, in order, nothing else in the file. Use "?" whenever you cannot tell: a wrong
guess is worse than "?". When done, reply with: the number of cases written, how many "?" you gave, and anything
odd you saw on the sheets (a sheet that is broken, a question that did not fit a case) - short.

## The sets' rules (try 2, 2026-11-24: the sets whose two looks disagreed)
Each sheet's header asks its question; these rules settle the cases the first try's looks read two ways. When a
case fits none of them, answer "?".

**Places (L1, and a player's place in L5).** Cyan lines are the platforms; the number printed along a line is
its id, on every piece of it - read the id printed on the piece right under the feet (when two lines run close,
the one the feet touch). Magenta lines are ropes / ladders, "r-<id>".
- `s<id>` - its feet are on that line (within a few px). **A fading-in or see-through mob is placed by the same
  rule as a solid one: its feet against the surface.** Being faint does not make it "in the air".
- `a` - its feet are clear above every line: jumping, knocked up, falling. `f` - a flying kind (Stirge ...) in
  the air. `r<id>` - on a rope / ladder. `n` - the mark is on no mob (scenery, a player, an effect). `?`.
- **Near a rope (L1R: a strip of frames from 0.2 s before to 0.2 s after, the case's frame red):** judge the case's
  frame, using the motion the strip shows. `r<id>` - it holds the rope / ladder on that frame (climbing or hanging:
  on the rope's line, moving only along it, or still). `a` - it jumps onto it, jumps off it or passes in front of
  it without holding it. `s<id>` - its feet are on a line, also at a rope's top or bottom when it has stepped off.

**L3 - how a mob was born.** Take the first rule from the top that fits:
1. `notmob` - at BORN the yellow mark is on no mob.
2. `entry` - the frames before BORN are the map's loading (black, a fade in): it was there when we came.
3. `dying` - at BORN it is already playing its death animation.
4. `fade` - it appears see-through and grows solid in place (a spawn).
5. `view` - on the frames before BORN its place was **outside the game picture** (in the purple padding, or
   past the screen's edge, so the mob was cut by the edge): it came in through the edge or the camera moved.
6. `uncover` - on the frames before BORN its place was **inside the picture**: something drawn over it hid it
   (an effect, a mob, a player, us, damage digits, a window) - or nothing visible did and it was simply picked
   up late. The deciding question between `view` and `uncover` is only "was the place inside the picture just
   before BORN?" - never what hid it.

**L4 - whose blow (the strip: every frame from our skill key's key-down to 1.0 s after it).** The bar on top
shows the key-down (green, at 0), that skill's landing window (yellow: when a mob it hits shows its pose), our
other key-downs (grey) and when the pose begins (red). Frames inside the landing window have a yellow border, the
pose's first frame a red one. The mob is the yellow x (over it on every frame), we are the green triangle.
- `us` - our attack is seen reaching the mob (the weapon's stab / swing or our skill's effect over it) and its
  pose begins in the landing window as our blow lands.
- `other` - its pose begins without our attack reaching it: another player's attack or effect on it, ours
  aimed the other way or short of it, or no key-down of ours on the strip.
- `?` - you cannot tell: another player's attack lands on it at the same time as ours, or the mob is covered
  when it begins. The window alone never makes it ours: our attack must be seen reaching it.
- pose: `hit` (it flinches) / `die` (its death animation) / `none` (no pose begins) / `?`.

**L6 - which mob the drop flew out of.** `A`, `B` ... (the letters stand where a mob began to die), `none`, `?`.
When two deaths happen at one place within the window and the drop could have come out of either, answer the
two letters joined by "|", in order (`A|B`): that is an answer of its own, not a "?".

## Open definition gaps (found in try 2, 2026-11-24; for a later set - nothing waits on them)
- **L2, partly behind scenery:** a mob in plain view with part of the map drawn over it (Ellinia's light ray,
  bones, a ladder post): `scenery` or `none`?
- **L2, two things over a mob:** a pet and another mob, or a pet and coins, over it at once: which one is the cover?
- **L3, a hit or a death at BORN:** a squashed Bubbling, or a see-through outline under our skill's effect, at
  BORN: the hit pose (`uncover`, picked up late) or the death (`dying`)? One frame does not tell them apart.
