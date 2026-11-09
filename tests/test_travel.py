"""brain-v2 movement (M1): NavMap.arc, the link moves and Travel, in the movement sim on the real Line 1 map."""
import random
from pathlib import Path

import pytest

from maplebrain.brain.moves import Jump, Wish, node_of
from maplebrain.brain.travel import Travel
from maplebrain.humanize import Humanizer
from maplebrain.nav.navmap import NavMap
from maplebrain.nav.selfstate import SelfState
from maplebrain.nav.sim import Sim, SimDriver

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"


@pytest.fixture(scope="module")
def line1():
    return NavMap.for_map(10003061, ASSETS)


def test_a_walking_jump_reaches_less_far_when_landing_higher(line1):
    level = line1.cfg.jump_vx * 2 * line1.cfg.jump_speed / line1.cfg.gravity
    t, p, x = line1.arc(1500, 73, 1)                 # on 79 (y 73), level landing back on it
    assert p.id == 79 and x - 1500 == pytest.approx(level, abs=1)
    t, p, x = line1.arc(2100, 73, 1)                 # 79 -> 114 is 60 px up: comes down after ~0.43 s
    assert p.id == 114 and 2160 <= x <= 2225 and x - 2100 < level - 10
    assert line1.arc(2081, 73, 1)[1].id == 273      # from 2081 it comes down short of 114 (starts 2160): falls


def test_jump_takeoff_is_chosen_where_the_arc_lands_inside_the_target(line1):
    k = next(k for k in line1.links_from(79) if k.kind == "jump" and k.dst == 114 and k.dir == 1)
    s = SelfState(0, 2000, 73, "tag", "ground", 79)
    j = Jump(line1, k, Humanizer(seed=3), 0.0, s)
    t, p, x = line1.arc(j.x_t, 73, 1)
    assert p.id == 114 and p.left + 3 <= x <= p.right - 3


def _run(nav, sim, dst, dst_x, seed, limit=40.0):
    rng, drv = random.Random(seed), SimDriver()
    tr = Travel(nav, dst, dst_x, Humanizer(seed=seed))
    t, nxt, hist = 0.0, 0.0, []
    while t < limit:
        b = sim.step(drv.keys(t), 0.005)
        hist.append((t, b.x, b.y, b.state, b.platform, b.rope, b.vx, b.vy))
        t += 0.005
        if t >= nxt:
            h = [e for e in hist if e[0] <= t - 0.06][-1:] or hist[:1]
            _, x, y, st, pl, rp, vx, vy = h[0]
            hist = hist[-100:]
            if tr.step(t, SelfState(t, x + rng.gauss(0, 2), y, "tag", st, pl, rp, vx, vy), drv) != "run":
                break
            nxt = t + 0.07 * rng.uniform(0.7, 1.4)
    return tr


@pytest.mark.parametrize("dst,dst_x", [(79, 1700), (111, 2600), (19, 150), (244, 2000), (33, 1800)])
def test_travel_from_the_hub_gets_there(line1, dst, dst_x):
    sim = Sim(line1, 273, 1400)
    tr = _run(line1, sim, dst, dst_x, seed=dst)
    assert tr.status == "done", (tr.reason, tr.events, tr.log)
    for _ in range(200):                             # settle
        if sim.b.state == "ground":
            break
        sim.step(set(), 0.005)
    assert sim.b.platform == dst and abs(sim.b.x - dst_x) <= 25


def test_a_link_failing_twice_is_avoided(line1):
    tr = Travel(line1, 79, 1700)
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    tr.step(0.0, s, SimDriver())
    k = tr.move.link
    for i in range(2):                               # the move "fails" twice where it started
        tr.move.status, tr.move.reason = "failed", "test"
        tr.step(0.1 * (i + 1), s, SimDriver())
    assert k in tr.avoid and tr.move.link != k
    assert any(e[1] == "blacklisted" for e in tr.events)


def test_node_of():
    assert node_of(SelfState(0, 0, 0, "tag", "rope", rope=-3)) == -3
    assert node_of(SelfState(0, 0, 0, "tag", "air")) is None
    assert Wish().hold == set()
