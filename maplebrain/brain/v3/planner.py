"""brain v3, layer: PLANNER (PLAN-v3.md migration step 2: the Goal / Task contracts).

    Goal   want(world) -> float | None     how much it wants to run now (a sum of named terms); None = not now
           next_task(world) -> Task        the task it wants this tick
    Task   step(now, world, hands) -> str  "run" / "done" / "failed"; moves us a bit each tick, never blocks
           can_cancel(world) -> bool       may another task take over now (never mid-jump, never mid-swing)
           events                          what happened (arrived, ...): the planner re-picks the goal at once

The planner picks WHICH GOAL runs, every GOAL_EVERY_S (varied) and at once on a task event: the highest `want`;
the active goal is kept on a tie. The planner never presses keys; tasks never choose goals.
The active goal names its task EVERY tick (not only when the planner re-picks, as the first sketch in PLAN-v3.md had
it): combat decides in ~70 ms (a mob walks into reach, our swing ends), and today's Hunt chain is per tick. A new task
takes over when the running one can_cancel; an equal one (same kind, same target) keeps the running object.

Step 2: one goal, Hunt (v3/goals.py) = brain v2's decision chain; behaviour identical (tools/v3/gate.py). Today every
task can_cancel at once, as the chain switched at once; the guards that matter (a trip is replaced only on the
ground at a move boundary; no press mid-swing) live inside the tasks' parts. Step 3 adds HuntArea; the keep margin /
minimum stay between competing goals is PLAN-v3.md open decision 5.
"""
import random

GOAL_EVERY_S = (0.8, 1.3)           # s between two goal picks (varied), plus at once on a task event


class Task:
    """One interruptible job (module doc). Subclasses: v3/tasks.py."""
    name = "task"

    def __init__(self):
        self.events = []

    def step(self, now, world, hands) -> str:
        raise NotImplementedError

    def can_cancel(self, world) -> bool:
        return True

    def key(self):
        """Two tasks with the same key are the same job (the running one is kept)."""
        return (self.name,)

    def __eq__(self, other):
        return isinstance(other, Task) and self.key() == other.key()

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        return "/".join(str(k) for k in self.key())


class Goal:
    """What the bot is out to do (module doc). Subclasses: v3/goals.py."""
    name = "goal"

    def want(self, world) -> float | None:
        raise NotImplementedError

    def next_task(self, world) -> Task:
        raise NotImplementedError


class Planner:
    def __init__(self, goals, hz=None, say=None):
        self.goals = list(goals)
        self.say = say or (lambda msg: None)
        # its own random stream, seeded from the brain's without drawing from it: the planner's timer must not
        # shift the draws every other part makes (the step-2 gate is exact)
        state = hz.rng.getstate()[1] if hz is not None else (0,)
        self.rng = random.Random(state[0] ^ 0x5EED)
        self.goal, self.task = None, None
        self.next_pick = 0.0

    def due(self, now) -> bool:
        return self.goal is None or now >= self.next_pick or bool(self.task is not None and self.task.events)

    def pick(self, world):
        """The goal with the highest want; the active one stays on a tie; None = nothing wants to run."""
        best, best_w = None, None
        for g in self.goals:
            w = g.want(world)
            if w is None:
                continue
            if best_w is None or w > best_w or (w == best_w and g is self.goal):
                best, best_w = g, w
        return best

    def step(self, now, world, hands) -> str | None:
        """One tick: re-pick the goal when due, take the goal's task, run it. Returns the task's status (None = no
        goal wants to run: no keys)."""
        if self.due(now):
            g = self.pick(world)
            if g is not self.goal and self.goal is not None:
                self.say(f"goal {self.goal.name} -> {g.name if g else None}")
            self.goal = g
            self.next_pick = now + self.rng.uniform(*GOAL_EVERY_S)
            if self.task is not None:
                self.task.events.clear()
        if self.goal is None:
            self.task = None
            hands.hold(set())
            return None
        nxt = self.goal.next_task(world)
        if self.task is None or (nxt != self.task and self.task.can_cancel(world)):
            self.task = nxt
        return self.task.step(now, world, hands)
