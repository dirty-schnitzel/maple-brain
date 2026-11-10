"""brain v3 step 3, Platform mode (goal HuntArea) in the movement sim on Line 1 (PLAN-v3.md gate): with platforms 79 +
56 marked, never a target off them except FIGHT BACK (a mob on our platform within FIGHT_BACK_PX, until the leash),
and always back on them after forced drops onto the busy floors 273 / 244 (fake mobs everywhere, respawning)."""
import random

import pytest

from maplebrain.brain.brain_v2 import BrainV2
from maplebrain.brain.v2.targeting import FIGHT_BACK_PX
from maplebrain.brain.v3.goals import LEASH_S, HuntArea
from maplebrain.brain.v3.tasks import Back
from maplebrain.config import Config
from maplebrain.humanize import Humanizer
from maplebrain.nav.navmap import NavMap
from maplebrain.nav.selfstate import SelfState
from maplebrain.nav.sim import Body, Sim
from test_brain_v2 import ASSETS, ATTACK, BASIC, Drv, FakeMobs, _obs

JUMP = Config().keys.jump      # the brain presses this; nav/sim.py only knows "jump" (test_brain_v2._hunt doesn't
                                # translate it: no running jumps / drop-throughs there - kept as is for the v3 gate)
AREA = {79, 56}
FLOORS = (273, 244)             # unmarked, full width, 13 + 18 spawns: the worst place to be knocked onto
SETTLE_S = 5.0                  # a drop comes only after this long back on the area (as the brain sees it)
BACK_SLACK_S = 15.0             # s on top of the leash + the route's seconds from the landing spot (the fight that's
                                # going on when the leash runs out, swings, the sim's re-plans)


@pytest.fixture(scope="module")
def line1():
    return NavMap.for_map(10003061, ASSETS)


def area_hunt(nav, seconds, seed, area=AREA, start=(79, 1700), drop_every=(25.0, 40.0), spawns=None, trace=None):
    """The sim hunt of tests/test_brain_v2.py with marks, plus forced drops: every drop_every s (when on the area)
    we land on a random floor at a random x - a knockback off the area. Returns (brain, picks, drops, ticks):
    picks = (t, target platform, our ground platform, |dx|) at every new target, drops = drop times, ticks =
    (t, our ground platform or None)."""
    rng = random.Random(seed)
    br, drv = BrainV2(Config(), nav, Humanizer(seed=seed), area=area), Drv()
    sim = Sim(nav, *start)
    mobs = FakeMobs(nav, br.reach, nav.spawns if spawns is None else spawns, rng)
    t, nxt, hist, facing, swing_end, prev_keys = 0.0, 0.0, [], 1, -9.0, set()
    next_drop = rng.uniform(*drop_every)
    picks, drops, ticks, last_target, on_since = [], [], [], None, None
    while t < seconds:
        keys = {"jump" if k == JUMP else k for k in drv.keys(t)}   # the sim's own name for the jump key
        d = ("right" in keys) - ("left" in keys)
        if d and d != facing and t >= swing_end:
            facing = d
        if keys - prev_keys & {ATTACK, BASIC} and t >= swing_end:
            mobs.swing(t, facing, sim.b.x, sim.b.y)
            swing_end = t + br.reach.swing_s
        prev_keys = keys
        settled = on_since is not None and t - on_since >= SETTLE_S
        if t >= next_drop and settled and sim.b.state == "ground" and sim.b.platform in area:
            p = nav.platforms[rng.choice(FLOORS)]
            x = rng.uniform(p.left + 100, p.right - 100)
            sim.b = Body(x, p.y_at(x), "ground", p.id)
            r = nav.route(p.id, x, *min(((pid, nav.platforms[pid].clamp(x)) for pid in area),
                                        key=lambda q: nav.route(p.id, x, q[0], q[1], with_cost=True)[1]),
                          with_cost=True)
            drops.append((t, r[1]))
            hist = []
            next_drop = t + rng.uniform(*drop_every)
        b = sim.step(keys, 0.005)
        mobs.step(t, 0.005)
        hist.append((t, b.x, b.y, b.state, b.platform, b.rope, b.vx, b.vy))
        t += 0.005
        if t >= nxt:
            h = [e for e in hist if e[0] <= t - 0.06][-1:] or hist[:1]
            _, x, y, st, pl, rp, vx, vy = h[0]
            hist = hist[-100:]
            s = SelfState(t, x + rng.gauss(0, 2), y, "tag", st, pl, rp, vx, vy)
            assert br.step(t, _obs(mobs.visible(x, y)), s, drv) is None
            ticks.append((t, pl if st == "ground" else None))
            if st == "ground" and pl in area:
                on_since = t if on_since is None else on_since
            elif st == "ground":
                on_since = None
            if trace is not None:
                trace.append((round(t, 2), st, pl, rp, round(x), br.mode, repr(br.task), br.target,
                              br.hunt.trip_swings, sorted(drv.want)))
            if br.target is not None and br.target != last_target:
                m = next(m for m in mobs.mobs if m["id"] == br.target)
                picks.append((t, m["platform"], pl if st == "ground" else None, abs(m["x"] - x)))
            last_target = br.target
            nxt = t + 0.07 * rng.uniform(0.7, 1.4)
    return br, picks, drops, ticks


def _back_after(drops, ticks, area):
    """(seconds from the drop to standing on a marked platform again or None = not yet, the allowed seconds)."""
    return [(next((t - d for t, pl in ticks if t > d + 0.5 and pl in area), None), LEASH_S[1] + route + BACK_SLACK_S)
            for d, route in drops]


@pytest.mark.parametrize("seed", [1, 2])
def test_platform_mode_targets_only_the_area_and_always_comes_back(line1, seed):
    br, picks, drops, ticks = area_hunt(line1, 180.0, seed)
    assert isinstance(br.hunt, HuntArea)
    off = [p for p in picks if p[1] not in AREA]
    for t, mob_pl, our_pl, dx in off:                    # off the area: only fight back (on our platform, close)
        assert mob_pl == our_pl and dx <= FIGHT_BACK_PX + 40, (t, mob_pl, our_pl, dx)
    assert drops, "no forced drop happened"
    end = ticks[-1][0]
    for (d, _), (took, limit) in zip(drops, _back_after(drops, ticks, AREA)):
        if took is None:
            assert end - d < limit, (d, limit)            # not back yet only when the run ended first
        else:
            assert took <= limit, (d, took, limit)
    assert any(took is not None for took, _ in _back_after(drops, ticks, AREA))
    assert br.stats["kills"] >= 5, dict(br.stats)


def test_one_marked_platform_is_roamed_end_to_end(line1):
    """A single marked platform and no mobs anywhere: roam stays on it and walks it (the old roam_goal excluded our
    own platform = IDLE forever)."""
    tr = []
    br, picks, drops, ticks = area_hunt(line1, 60.0, 3, area={79}, drop_every=(999.0, 999.0), spawns=[], trace=tr)
    assert not drops and not picks
    assert all(pl == 79 for _, pl in ticks if pl is not None)
    xs = [e[4] for e in tr]
    assert br.stats["trips"] >= 3 and max(xs) - min(xs) >= 300, (dict(br.stats), min(xs), max(xs))


def test_off_the_area_with_nothing_near_goes_back_to_the_nearest_marked_platform(line1):
    br = BrainV2(Config(), line1, Humanizer(seed=1), area=AREA)
    drv = Drv()
    s = SelfState(0, 1700, line1.platforms[273].y_at(1700), "tag", "ground", 273)
    drv.keys(0.0)
    br.step(0.0, _obs([]), s, drv)
    assert isinstance(br.task, Back) and br.task.pid == 79 and br.mode == "BACK"
    assert br.hunt.outside_since == 0.0


def test_the_leash_cuts_fights_off_the_area(line1):
    from test_brain_v2 import _mob
    br = BrainV2(Config(), line1, Humanizer(seed=1), area=AREA)
    drv = Drv()
    br.facing = 1
    s = SelfState(0, 1700, line1.platforms[273].y_at(1700), "tag", "ground", 273)
    mob = _mob(1, 1780, s.y, 273)
    drv.keys(0.0)
    br.step(0.0, _obs([mob]), s, drv)
    assert br.target == 1                                 # fight back: on our platform, 80 px
    t = br.hunt.leash + 1.0
    drv.keys(t)
    br.step(t, _obs([mob]), s, drv)
    assert br.target is None and isinstance(br.task, Back) and not br.hunt.trip_swings
