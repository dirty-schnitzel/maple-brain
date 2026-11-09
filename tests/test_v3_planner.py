"""brain v3 planner (PLAN-v3.md step 2): the Goal / Task contracts, the Planner, and the goal Hunt naming today's
tasks (Fight / Goto / Roam / Rest). Behaviour identical to brain v2: tests/test_v3_gate.py + tools/v3/gate.py."""
from types import SimpleNamespace

import pytest

from maplebrain.brain.v3.planner import Goal, Planner, Task
from maplebrain.brain.v3.tasks import Fight, Goto, Rest, Roam
from maplebrain.humanize import Humanizer
from maplebrain.nav.navmap import NavMap
from maplebrain.nav.selfstate import SelfState
from test_brain_v2 import ASSETS, Drv, _brain, _mob, _rope_spot, _tick


@pytest.fixture(scope="module")
def line1():
    return NavMap.for_map(10003061, ASSETS)


class Job(Task):
    def __init__(self, tag, cancel=True):
        super().__init__()
        self.tag, self.cancel, self.steps = tag, cancel, 0

    def key(self):
        return ("job", self.tag)

    def step(self, now, world, hands):
        self.steps += 1
        return "run"

    def can_cancel(self, world):
        return self.cancel


class Want(Goal):
    def __init__(self, name, w, tag=None):
        self.name, self.w, self.tag = name, w, tag or name

    def want(self, world):
        return self.w

    def next_task(self, world):
        return Job(self.tag)


HANDS = SimpleNamespace(hold=lambda keys: None)


def test_the_highest_want_wins_none_never_and_a_tie_keeps_the_active_goal():
    a, b, off = Want("a", 1.0), Want("b", 1.0), Want("off", None)
    p = Planner([a, off, b], Humanizer(seed=1))
    p.step(0.0, None, HANDS)
    assert p.goal is a
    p.goal = b
    assert p.pick(None) is b                              # tie: keep the active one
    a.w = 2.0
    assert p.pick(None) is a
    assert Planner([off], Humanizer(seed=1)).step(0.0, None, HANDS) is None


def test_goals_are_re_picked_on_a_timer_or_at_once_on_a_task_event():
    a, b = Want("a", 1.0), Want("b", 0.0)
    p = Planner([a, b], Humanizer(seed=1))
    p.step(0.0, None, HANDS)
    a.w = -1.0
    p.step(0.1, None, HANDS)
    assert p.goal is a                                    # not due yet
    p.task.events.append("arrived")
    p.step(0.2, None, HANDS)
    assert p.goal is b and not p.task.events or p.task.tag == "b"
    assert 0.8 <= p.next_pick - 0.2 <= 1.3


def test_the_planner_never_draws_from_the_brains_random_stream():
    hz = Humanizer(seed=5)
    before = hz.rng.getstate()
    p = Planner([Want("a", 1.0)], hz)
    for i in range(50):
        p.step(i * 0.5, None, HANDS)
    assert hz.rng.getstate() == before


def test_an_equal_task_keeps_the_running_object_and_a_busy_one_is_not_cancelled():
    g = Want("a", 1.0, tag="x")
    p = Planner([g], Humanizer(seed=1))
    p.step(0.0, None, HANDS)
    first = p.task
    p.step(0.1, None, HANDS)
    assert p.task is first and first.steps == 2           # same job: the running object goes on
    first.cancel = False
    g.tag = "y"
    p.step(0.2, None, HANDS)
    assert p.task is first                                # can't cancel now: it goes on
    first.cancel = True
    p.step(0.3, None, HANDS)
    assert p.task.tag == "y"


def test_hunt_names_todays_tasks(line1):
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    br, drv = _brain(line1), Drv()
    br.facing = 1
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s)
    assert isinstance(br.task, Fight) and br.task.tid == 1 and br.mode == "LOCAL"
    br, drv = _brain(line1), Drv()
    _tick(br, drv, 0.0, [_mob(1, 1700, 73, 79)], s)
    assert isinstance(br.task, Goto) and br.task.tid == 1 and br.mode == "TRAVEL"
    br, drv = _brain(line1), Drv()
    _tick(br, drv, 0.0, [], s)
    assert isinstance(br.task, Roam)
    br, drv = _brain(line1), Drv()                        # on a rope when a break falls due, nothing near
    rope = _rope_spot(line1)
    _tick(br, drv, 0.0, [], rope)
    _tick(br, drv, br.breaks.due + 0.1, [], rope)
    assert isinstance(br.task, Rest) and br.mode == "BREAK"


def test_our_swing_still_going_is_a_finishing_fight(line1):
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    br, drv = _brain(line1), Drv()
    br.facing = 1
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s)     # press: our swing runs ~0.9 s
    _tick(br, drv, 0.3, [_mob(1, 1480, 198, 273, state="dying")], s)
    assert isinstance(br.task, Fight) and br.task.finishing and br.mode == "LOCAL"
