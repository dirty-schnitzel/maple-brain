"""Jumping (the user, 2026-11-02, map 10001070 The Rain-Forest East of Henesys; no platforms/ropes yet):
- jump (shift) when walking at a step our jump clears: the map's two pits have 60 px walls (platform 49 x 39-231
  and 91 x 849-1041 at y 275, the floor around them at y 215);
- a few jumps now and then while standing for a spawn, each moving one way ('moving a certain direction when
  jumping' - the user).
Every jump keeps a direction held: the walk key stays down through the press (Executor: a non-movement Tap keeps it).
"""
from pathlib import Path

import pytest

from maplebot.brain.actions import Hold, Release, Tap
from maplebot.config import Keys
from maplebot.brain.brain import Brain
from maplebot.config import Config
from maplebot.nav.navmap import NavMap
from test_brain import obs

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"
RAIN = NavMap.for_map(10001070, ASSETS)


@pytest.fixture(params=["exact", 1, 2, 3])
def jbrain(request):
    cfg = Config()
    cfg.perception.map_id = 10001070
    if request.param == "exact":
        cfg.humanize.jitter = 0.0
    else:
        cfg.humanize.seed = request.param
    cfg.nav.seek_spawns = False          # jumping alone (test_spawns.py: walking toward the spawns)
    return Brain(cfg, navmap=RAIN)


def jumps(acts, key=Keys.jump):
    return [a for a in acts if isinstance(a, Tap) and a.key == key]


def at(t, platform, x, y=None, dot_x=100.0):
    o = obs(t, dot=(dot_x, 90.0))
    o.platform, o.map_pos = platform, (x, y if y is not None else RAIN.platforms[platform].y_at(x) or 0)
    return o


def test_step_ahead_on_the_rain_forest():
    assert RAIN.step_ahead(49, 100, -1) == (61, 60)           # in the pit, walking left: its 60 px wall at x 39
    assert RAIN.step_ahead(49, 100, 1) == (131, 60)
    assert RAIN.step_ahead(71, 0, 1) is None                   # on the floor walking into the pit: just walk off
    assert RAIN.step_ahead(71, -700, -1)[1] == float("inf")    # the map's left edge: a wall, nothing beyond


def walk_left_in_the_pit(b, x0=180.0, speed=6.0, until=None, n=60):
    """Idle walk left inside pit 49 (patrol_dir left), the minimap dot moving. Returns [(x, actions)]."""
    b.patrol_dir = "left"
    out, x = [], x0
    for i in range(n):
        acts = b.step(at(i * 0.05, 49, x, dot_x=100.0 - i * 0.4))
        out.append((x, acts))
        if until and until(acts):
            break
        x -= speed
    return out


def test_jumps_up_the_pit_wall_while_still_walking_at_it(jbrain):
    ticks = walk_left_in_the_pit(jbrain, until=jumps)
    x, acts = ticks[-1]
    assert jumps(acts), "never jumped"
    dist = x - 39
    assert jbrain.cfg.timing.step_jump_min - 6 <= dist <= jbrain.cfg.timing.step_jump_max + 6
    assert Hold("left") in acts and not any(isinstance(a, Release) for a in acts)   # a running jump, leftwards
    assert jbrain.stats["step_jumps"] == 1


def test_one_press_per_jump(jbrain):
    """Still in the air (no landing seen yet): no second press."""
    ticks = walk_left_in_the_pit(jbrain, speed=1.0, x0=60.0, n=12)   # creeping along right at the wall
    presses = [t for t, (_, acts) in enumerate(ticks) if jumps(acts)]
    assert len(presses) == 1


def test_no_jump_walking_off_into_the_pit(jbrain):
    jbrain.patrol_dir = "right"
    acts = []
    for i in range(30):
        acts += jbrain.step(at(i * 0.05, 71, -100.0 + i * 6, dot_x=100.0 + i * 0.4))
    assert not jumps(acts)


def test_a_step_that_keeps_failing_is_given_up(jbrain):
    """Three jumps at it and we're still in the pit (a monster in the way, a bad take-off...): avoid that way."""
    jbrain.cfg.timing.idle_walk_min_s = jbrain.cfg.timing.idle_walk_max_s = 10.0
    jbrain.patrol_dir = "left"
    t, n = 0.0, 0
    while t < 8.0 and jbrain.stats["blocked"] == 0:
        jbrain.step(at(t, 49, 50.0, dot_x=100.0 + (t * 10 % 2)))   # stays at the wall, the dot jiggling
        t += 0.05
    assert jbrain.stats["step_jumps"] == jbrain.cfg.timing.step_jump_tries
    assert jbrain.stats["blocked"] == 1 and jbrain.blocked["left"] > t


def test_blocked_at_the_map_edge_does_not_jump(jbrain):
    """The map knows the left end is a wall with nothing beyond: no jump attempt, avoid it at once."""
    jbrain.cfg.timing.idle_walk_min_s = jbrain.cfg.timing.idle_walk_max_s = 5.0
    jbrain.patrol_dir = "left"
    t = 0.0
    while t < 3.0 and jbrain.stats["blocked"] == 0:
        jbrain.step(at(t, 71, -740.0))                             # the dot never moves
        t += 0.05
    assert jbrain.stats["blocked"] == 1 and jbrain.stats["block_jumps"] == 0 and jbrain.stats["jumps"] == 0


def test_blocked_somewhere_the_map_has_no_step_jumps_once_first(jbrain):
    jbrain.cfg.timing.idle_walk_min_s = jbrain.cfg.timing.idle_walk_max_s = 5.0
    jbrain.patrol_dir = "left"
    t, acts = 0.0, []
    while t < 4.0 and jbrain.stats["blocked"] == 0:
        acts += jbrain.step(at(t, 71, -400.0))                     # mid-floor, the dot frozen (a player? lag?)
        t += 0.05
    assert jbrain.stats["block_jumps"] == 1 and jbrain.stats["blocked"] == 1
    assert len(jumps(acts)) == 1


# ---------------------------------------------------------------- idle: standing for a spawn
def idle(b, secs, t0=0.0, dt=0.05):
    out, t = [], t0
    while t < t0 + secs:
        out.append((t, b.step(at(t, 71, -400.0, dot_x=100.0 + min(t - t0, 3.0) * 2))))   # standing: dot still
        t += dt
    return out


def test_idle_jumps_come_in_small_bursts_moving_one_way(jbrain):
    tm = jbrain.cfg.timing
    ticks = idle(jbrain, 60.0)
    presses = [(t, acts) for t, acts in ticks if jumps(acts)]
    assert presses, "no idle jumps in a minute of waiting"
    for t, acts in presses:                                          # every jump holds a direction
        assert any(isinstance(a, Hold) and a.key in ("left", "right") for a in acts)
    # bursts: presses closer than the gap max belong together; 1-3 per burst; bursts >= every_min apart
    bursts, cur = [], [presses[0][0]]
    for t, _ in presses[1:]:
        if t - cur[-1] <= (tm.jump_cooldown_s + tm.idle_jump_gap_max_s) * 1.3 + 0.1:
            cur.append(t)
        else:
            bursts.append(cur)
            cur = [t]
    bursts.append(cur)
    assert all(tm.idle_jump_n_min <= len(b) <= tm.idle_jump_n_max for b in bursts)
    assert all(b2[0] - b1[-1] >= tm.idle_jump_every_min_s * 0.75 for b1, b2 in zip(bursts, bursts[1:]))
    first_stand = jbrain.idle_walk_until                            # (sentinel once standing)
    assert first_stand == -1e9


def test_idle_jump_holds_the_way_until_landing_then_stands(jbrain):
    ticks = idle(jbrain, 30.0)
    i = next(i for i, (_, acts) in enumerate(ticks) if jumps(acts))
    t0, acts = ticks[i]
    way = next(a.key for a in acts if isinstance(a, Hold))
    nxt = next((j for j in range(i + 1, len(ticks)) if jumps(ticks[j][1])), len(ticks))
    held = [t for t, a in ticks[i:nxt] if Hold(way) in a]
    assert held[-1] - t0 <= jbrain.cfg.timing.jump_cooldown_s * 1.3 + 0.1  # only through the jump
    after = next(a for t, a in ticks[i:nxt] if t > held[-1])
    assert Release() in after                                       # landed: stand again


def test_idle_bursts_go_back_and_forth(jbrain):
    ticks = idle(jbrain, 90.0)
    ways = []
    for t, acts in ticks:
        if jumps(acts):
            w = next(a.key for a in acts if isinstance(a, Hold))
            if not ways or ways[-1][1] != w or t - ways[-1][0] > (jbrain.cfg.timing.jump_cooldown_s + jbrain.cfg.timing.idle_jump_gap_max_s) * 1.3 + 0.1:
                ways.append((t, w))
            else:
                ways[-1] = (t, w)
    firsts = [w for _, w in ways]
    assert len(firsts) >= 2 and all(a != b for a, b in zip(firsts, firsts[1:]))


def test_no_idle_jumps_when_switched_off(jbrain):
    jbrain.cfg.timing.idle_jumps = False
    assert not any(jumps(acts) for _, acts in idle(jbrain, 40.0))


def test_no_idle_jumps_while_walking_the_idle_walk(jbrain):
    ticks = idle(jbrain, 2.0)                                       # the first 2 s: walking, not standing yet
    assert not any(jumps(acts) for _, acts in ticks)


def test_starting_to_walk_from_the_pit_corner_jumps_at_once(jbrain):
    """rain1 (2026-11-02): 6 of 7 stalls began with us standing in pit 49's left corner (x read ~46, wall at 39)
    after a fight/loot/wait; walking left we pressed into the wall for 1 s before the blocked-jump. The user: other
    bots jump out seamlessly. Now: the first walking tick toward it jumps."""
    jbrain.patrol_dir = "left"
    acts = jbrain.step(at(0.0, 49, 46.0))
    assert Hold("left") in acts and jumps(acts)


def test_a_reading_just_past_the_wall_still_jumps(jbrain):
    """rain1 59.2 s: walking right in the pit, x read 238 - past the wall at 231 (the minimap is 16 px coarse)."""
    jbrain.patrol_dir = "right"
    acts = jbrain.step(at(0.0, 49, 238.0, y=275.0))
    assert jumps(acts)


def test_platform_at_tolerates_one_minimap_px_at_a_wall():
    assert RAIN.platform_at(238, 279).id == 49                     # in the pit at its right wall, read past it
    assert RAIN.platform_at(46, 215).id == 71                      # on the floor at the pit's left edge
    assert RAIN.platform_at(135, 240) is None                      # mid-pit, half way up: really in the air
