---
paths:
  - "maplebrain/brain/**"
  - "maplebrain/runtime/keys.py"
  - "maplebrain/runtime/hunt_v2.py"
  - "maplebrain/keyboard.py"
  - "maplebrain/humanize.py"
---
# Brain, combat and input: standing rules

The logic itself is documented in the code and must stay true there: the docstring of `brain/v2/combat.py` holds
THE ATTACK LOGIC END TO END, and every other part's header states its own step. Update them in the same change as
the code; a header describes the logic as a whole, not a history of patches.

- **No fixed timings.** Every press length, pause and wait goes through `Humanizer.vary` (humanize.py, config
  `Humanize`); gaps between attacks follow the user's own recorded play. Tests must allow for the jitter.
- **One press = one swing** (since 2026-11-08; the held attack key is gone). The next press is decided at the
  swing's end. What the game does with keys (measured live): a key-down starts a swing only if none is going on;
  key-downs during a swing are ignored, not queued; a direction key released during a swing is dropped.
- **Only input a real hand could make** (the user, 2026-11-05: input tampering is one way bots are caught).
  Change WHAT keys are pressed rather than how the driver emits them.
- **Our facing is a belief**, built from the walk keys we sent; nothing on screen tells it. The game drops
  direction keys during a swing and in knockback, so the belief can be wrong: when combat looks wrong, check
  facing first (a mob "in front" that never reacts = we face the other way).
- **No left-right-left-right.** Turn round at most once per target, then one or two short taps, and "close
  enough" counts. Ladders are taken like a player: walk at it, press down while passing over.
- **Breaks** (`v2/breaks.py`): short pauses when nothing is near; every few minutes 5-20 s on a rope or a safe
  spot, never between mobs; any HP drop ends a break; never stop with the head above the platform at a ladder's
  top.
- **A change is a score term, a table rule, a state or a parameter with its data source** - never a special
  case in `step`, never a new rule layer ("track must be proven" was rejected).
- Attack every mob; no kill-steal avoidance. Plain attack by default. A kill is ours by the last hit only.
- Other players' drops are invisible in Classic World (outside a party): every drop on screen is ours.
- Our fitted movement values stand over v83's constants (Classic World raised jump and move speed); the swing
  length stays `(10 + attackSpeed) / 16` until the tracker work recalculates it (the user, 2026-11-21).
- The user's own play on Line 1 is the reference for timing and routes: HISTORY.md, "FARMING EXAMPLE".
