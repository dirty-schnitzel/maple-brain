# Session prompt: the tracker plan session

- **Run as:** Fable, max effort, a fresh session. Type: `run docs/prompts/tracker-plan.md`.
- **When:** after `docs/prompts/tracker-before.md` (it reads REPORT-track-before.md and the kept replay).
- **Result:** `PLAN-tracker.md`, PROPOSED until the user's OK.
- **Written:** 2026-11-21 in the planning session; the text below is unchanged.

```text
Tracker plan session. Read HANDOFF.md's START HERE, then docs/game_rules.md, REPORT-track-before.md,
PLAN-perception.md step 4, PLAN-loot.md (drops are part of this rework: section 13's result and my rule for
them), REWORKS.md's recipe, tools/perc/track/. Design the tracker from scratch as the state an AI learns from
and is scored by, and the one state description three programs share (the tracker, the simulator's engine, the
viewer). Experiments first, on the kept replay (no GPU needed for prototypes), dev group only. Then
PLAN-tracker.md: PROPOSED, with per-step gates on footage, stop rules and ready-to-paste Opus prompts. Build
nothing in maplebrain/. Ask me game-knowledge questions directly.
```
