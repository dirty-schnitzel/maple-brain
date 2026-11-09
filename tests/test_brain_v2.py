"""brain-v2 M2 (combat): reach from the client's attack boxes, WHEN TO HIT, targets, reflexes, and a hunt in the
movement sim on the real Line 1 map with fake mobs (walk, get hit, die, respawn)."""
import collections
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from maplebrain.brain.brain_v2 import BrainV2
from maplebrain.brain.reach import SWING_LAND_S, Reach, body, boxes_vs
from maplebrain.brain.v2.breaks import Breaks
from maplebrain.brain.v2.scene import Scene
from maplebrain.brain.v3.model import Character, Map, Mob
from maplebrain.config import Config
from maplebrain.humanize import Humanizer
from maplebrain.nav.navmap import NavMap
from maplebrain.nav.selfstate import SelfState
from maplebrain.nav.sim import Sim, SimDriver

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"
BUBBLING = 14
ATTACK = Config().keys.attack
BASIC, PICKUP = Config().keys.basic_attack, Config().keys.pickup
HP_POTION, MP_POTION = Config().keys.hp_potion, Config().keys.mp_potion


@pytest.fixture(scope="module")
def line1():
    return NavMap.for_map(10003061, ASSETS)


def _obs(mobs=(), hp=0.9, mp=0.9, hp_potions=True, mp_potions=True):
    return SimpleNamespace(mobs=list(mobs), me=None, hp=hp, mp=mp, hp_now=int(hp * 1000), mp_now=int(mp * 400),
                           hp_potions=hp_potions, mp_potions=mp_potions)


def _mob(i, x, y, platform, state="live", vx=0.0):
    return {"id": i, "mob": BUBBLING, "kind": "mob", "state": state, "x": x, "y": y, "vx": vx, "platform": platform,
            "unseen": 0.0, "src": "acq"}


def _brain(nav, seed=1):
    return BrainV2(Config(), nav, Humanizer(seed=seed))


def _build(now, mobs, s, facing, **hud):
    """A Scene from track dicts at SelfState s, looking `facing` (spear reach), via the world model's objects."""
    obs = _obs(mobs, **hud)
    return Scene.build(now, [Mob(d) for d in obs.mobs], Character.of(s, facing, obs), Reach("spear"))


class Drv(SimDriver):
    """SimDriver that remembers every tap it took: (time asked, key)."""

    def __init__(self):
        super().__init__()
        self.log = []

    def tap(self, key, secs, after=0.0):
        ok = super().tap(key, secs, after)
        if ok:
            self.log.append((self.now, key))
        return ok


def _presses(drv, key=ATTACK):
    return [t for t, k in drv.log if k == key]


# ---------------------------------------------------------------- reach
def test_spear_and_polearm_reach_vs_bubbling_from_the_client_boxes():
    for w in ("spear", "poleArm"):
        sure, maybe = Reach(w).vs(BUBBLING)
        assert 20 <= sure.lo <= 32 and 130 <= sure.hi <= 142      # stab/swing boxes overlap 52..111 + body +-26
        assert maybe.lo < 5 and 150 <= maybe.hi <= 165
        assert sure.has(72, 0) and not sure.has(170, 0) and not sure.has(80, -60)   # the user's median kill: 72


def test_swing_length_from_the_client_stances_and_attack_speed():
    assert Reach("poleArm").attack_speed == 8 and Reach("poleArm").swing_s == pytest.approx(0.90)   # live 0.89-0.92
    assert Reach("spear").attack_speed == 7 and Reach("spear").swing_s == pytest.approx(0.85)
    assert Reach("poleArm", attack_speed=6).swing_s == pytest.approx(0.80)                         # a Booster: -2
    cfg = Config()
    cfg.combat.attack_speed = 6
    assert BrainV2(cfg, None, Humanizer(seed=1)).weapon.swing_s == pytest.approx(0.80 + 0.02)


def test_a_wider_mob_is_reached_from_further():
    st = Reach("spear").stances
    small, _ = boxes_vs(st, (-20, -40, 20, 0))
    wide, _ = boxes_vs(st, (-40, -60, 40, 0))
    assert wide.hi - small.hi == pytest.approx(20) and wide.lo - small.lo == pytest.approx(-20)


def test_body_box_from_mob_frames():
    b = body({"frames": {"stand": [{"lt": [-27, -43], "rb": [24, 0]}], "move": [{"lt": [-29, -41], "rb": [26, 0]}]}})
    assert b == (-28, -42, 25, 0)


# ---------------------------------------------------------------- WHEN TO HIT
def _tick(br, drv, t, mobs, s, **kw):
    drv.keys(t)
    return br.step(t, _obs(mobs, **kw), s, drv)


def _taps(drv, key):
    return [k for k, t0, t1 in drv.taps if k == key]


def test_swings_at_a_mob_in_reach_in_front(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s)
    assert _presses(drv) == [0.0] and ATTACK not in drv.want and br.stats["swings"] == 1   # a press, never a hold


def test_no_swing_out_of_reach_walks_toward_it_instead(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1700, 198, 273)], s)
    assert not _taps(drv, ATTACK) and drv.want == {"right"}


def test_predicts_a_mob_walking_into_reach(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    hi = br.reach.vs(BUBBLING)[0].hi
    _tick(br, drv, 0.0, [_mob(1, 1400 + hi + 20, 198, 273, vx=-80)], s)    # 20 px out now, 16 px in when it lands
    assert _presses(drv)
    assert -80 * SWING_LAND_S < -20


def test_a_mob_behind_us_turns_us_round_first(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1330, 198, 273)], s)
    assert not _taps(drv, ATTACK) and _taps(drv, "left") and br.facing == -1
    _tick(br, drv, 0.3, [_mob(1, 1330, 198, 273)], s)
    assert _presses(drv) == [0.3]


def test_never_swings_at_nothing_or_at_dying_mobs(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    for i in range(30):
        _tick(br, drv, i * 0.1, [_mob(1, 1460, 198, 273, state="dying"), _mob(2, 1470, 198, 273, state="tentative")], s)
    assert br.stats["swings"] == 0


SWING_END = Reach(Config().combat.weapon).swing_s + 0.02   # + the margin (combat.SWING_MARGIN_S); + the key's way
GAP_MAX = 0.98 * 1.1                                # the user's longest gap after a swing x the tempo's wander


def test_one_press_per_swing_while_the_mob_is_knocked_back_none_after_it_dies(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    t = 0.0
    while t < 4.0:                                    # knocked back and forth inside the maybe reach, reacting
        hit = (t % 1.0) < 0.4
        _tick(br, drv, t, [_mob(1, 1480 + 60 * hit, 198, 273, state="hit" if hit else "live")], s)
        assert ATTACK not in drv.want                 # never held: the game swings only on key-downs
        t += 0.07
    p = _presses(drv)
    assert 3 <= len(p) <= 5, p
    assert all(SWING_END <= b - a <= SWING_END + GAP_MAX + 0.1 for a, b in zip(p, p[1:])), p   # never mid-swing
    while t < 6.5:                                    # it died: not one press more (CLEAN KILL)
        _tick(br, drv, t, [_mob(1, 1480, 198, 273, state="dying")], s)
        t += 0.07
    assert _presses(drv) == p and br.weapon.state == "ready" and br.weapon.engaged is None


def test_turns_to_a_mob_behind_only_once_our_swing_is_over(line1):
    br, drv = _brain(line1), Drv()                # the game drops a direction tap released mid-swing (probe/sauna1)
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273), _mob(2, 1340, 198, 273)], s)
    assert _presses(drv) == [0.0]
    t = 0.07
    while not _taps(drv, "left") and t < 2.0:         # the one in front died at once; the other is behind
        _tick(br, drv, t, [_mob(2, 1340, 198, 273)], s)
        t += 0.07
    turned = t - 0.07
    assert br.weapon.swing_end <= turned <= br.weapon.swing_end + 0.08 and br.facing == -1
    while len(_presses(drv)) < 2 and t < 4.0:         # then at it
        _tick(br, drv, t, [_mob(2, 1340, 198, 273)], s)
        t += 0.07
    assert len(_presses(drv)) == 2 and br.stats["turns"] == 1


def test_no_attack_on_top_of_a_turn(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1330, 198, 273)], s)
    assert _taps(drv, "left")
    _tick(br, drv, 0.07, [_mob(1, 1330, 198, 273)], s)
    assert not _presses(drv)                         # pressed on top of the walk key it can eat the turn
    _tick(br, drv, 0.25, [_mob(1, 1330, 198, 273)], s)
    assert _presses(drv) == [0.25]                    # the turn first, then the swing: it faces the new way


def test_a_dry_fight_means_we_look_the_other_way(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1                                     # we think; the game dropped the turn: the mob never reacts
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    t = 0.0
    while br.stats["dry"] == 0 and t < 4.5:
        _tick(br, drv, t, [_mob(1, 1480, 198, 273)], s)
        t += 0.07
    assert 1.8 <= t <= 4.2 and 2 <= len(_presses(drv)) <= 3
    t0 = t
    while not _taps(drv, "right") and t < t0 + 2:     # a tap toward it, then press again
        _tick(br, drv, t, [_mob(1, 1480, 198, 273)], s)
        t += 0.07
    assert _taps(drv, "right") and br.facing == 1
    n = len(_presses(drv))
    for i in range(6):
        _tick(br, drv, t + i * 0.07, [_mob(1, 1480, 198, 273)], s)
    assert len(_presses(drv)) == n + 1


def test_presses_that_knock_the_mob_back_are_not_dry(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    t = 0.0
    while t < 6.0:                                    # the tracker says "live", but every 0.8 s it jumps 60 px away
        _tick(br, drv, t, [_mob(1, 1460 + 60 * (int(t / 0.8) % 2 == 0 and (t % 0.8) < 0.07), 198, 273)], s)
        t += 0.07
    assert br.stats["dry"] == 0 and len(_presses(drv)) >= 4


# ---------------------------------------------------------------- breaks
def _breaks_scene(mobs, s, now, line1):
    return _build(now, mobs, s, 1)


def test_a_beat_after_a_fight_only_with_nothing_near(line1):
    far, near = _mob(2, 2200, 198, 273), _mob(2, 1500, 198, 273)
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    for mob, want in ((far, True), (near, False)):
        hits = 0
        for seed in range(40):
            b = Breaks(Map(line1), Humanizer(seed=seed), collections.Counter(), lambda m: None)
            b.resting(_breaks_scene([mob], s, 1.0, line1), True)
            hits += b.resting(_breaks_scene([mob], s, 1.1, line1), False)
        assert (0 < hits < 40) if want else hits == 0


def test_no_beat_on_the_way_to_a_target(line1):
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    b = Breaks(Map(line1), Humanizer(seed=1), collections.Counter(), lambda m: None)
    assert not any(b.resting(_breaks_scene([_mob(2, 2200, 198, 273)], s, i * 0.1, line1), False) for i in range(50))


def _rope_spot(nav):
    i, r = max(enumerate(nav.ropes), key=lambda e: e[1].bottom - e[1].top)
    return SelfState(0, r.x, (r.top + r.bottom) / 2, "tag", "rope", rope=nav.rope_id(i))


def test_a_break_stops_on_a_rope_for_5_to_20_s(line1):
    s = _rope_spot(line1)
    b = Breaks(Map(line1), Humanizer(seed=3), collections.Counter(), lambda m: None)
    b.resting(_breaks_scene([], s, 0.0, line1), False)
    t = b.due + 0.1
    assert b.resting(_breaks_scene([], s, t, line1), False) and b.kind == "break"
    start, due = t, b.due
    while b.resting(_breaks_scene([], s, t, line1), False):
        t += 0.1
    assert 5 <= t - start <= 20.2 and b.due > due    # done: the next one 2-5 min on


def test_a_rope_break_keeps_the_head_under_the_platform_and_the_feet_over_the_floor_mobs(line1):
    r = line1.ropes[9]                                # x 2082, 75..181: the short kind, platforms at both ends
    b = Breaks(Map(line1), Humanizer(seed=3), collections.Counter(), lambda m: None)

    def safe(y, vy=0.0):
        s = SelfState(0, r.x, y, "tag", "rope", rope=line1.rope_id(9), vy=vy)
        return b.safe(_breaks_scene([], s, 0.0, line1))

    assert safe(r.top + 69)                           # runs/v2: no hit in 25 s
    assert not safe(r.top + 47)                       # runs/v2 12:25: head above the platform, 5 hits
    assert not safe(r.bottom - 10)                    # in reach of the mobs on the floor
    assert not safe(r.top + 70, vy=-120.0)            # climbing: we'd come to rest 18 px higher
    assert safe(r.top + 85, vy=-120.0)


def test_damage_ends_a_rest_for_good(line1):
    s = _rope_spot(line1)
    say = []
    b = Breaks(Map(line1), Humanizer(seed=3), collections.Counter(), say.append)
    b.resting(_breaks_scene([], s, 0.0, line1), False, 700)
    t = b.due + 0.1
    assert b.resting(_breaks_scene([], s, t, line1), False, 700)
    assert b.resting(_breaks_scene([], s, t + 1, line1), False, 710)      # HP going up (regen, potion): rest on
    assert not b.resting(_breaks_scene([], s, t + 2, line1), False, 660)
    assert b.kind is None and b.due > t + 100 and b.stats["rests_hurt"] == 1
    assert not b.resting(_breaks_scene([], s, t + 2.1, line1), False, 660)  # not due again: no new break on the spot


def test_damage_ends_a_beat(line1):
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    for seed in range(40):
        b = Breaks(Map(line1), Humanizer(seed=seed), collections.Counter(), lambda m: None)
        b.resting(_breaks_scene([], s, 1.0, line1), True, 700)
        if b.resting(_breaks_scene([], s, 1.1, line1), False, 700):
            assert not b.resting(_breaks_scene([], s, 1.2, line1), False, 650) and b.kind is None
            return
    raise AssertionError("no beat in 40 seeds")


def test_a_break_never_starts_between_mobs_or_mid_fight(line1):
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    b = Breaks(Map(line1), Humanizer(seed=3), collections.Counter(), lambda m: None)
    b.resting(_breaks_scene([], s, 0.0, line1), False)
    late = b.ropes_only_until + 1
    assert not b.resting(_breaks_scene([_mob(1, 1200, 198, 273), _mob(2, 1600, 198, 273)], s, late, line1), False)
    assert not b.resting(_breaks_scene([], s, late + 0.1, line1), True)
    assert b.kind is None


def test_a_ground_break_waits_for_the_ropes_first(line1):
    b = Breaks(Map(line1), Humanizer(seed=3), collections.Counter(), lambda m: None)
    p = next(p for p in line1.platforms.values() if not any(
        abs(y - p.y_at((p.left + p.right) / 2)) < 90 and abs(x - (p.left + p.right) / 2) < 160 for x, y in line1.spawns))
    x = (p.left + p.right) / 2
    s = SelfState(0, x, p.y_at(x), "tag", "ground", p.id)
    b.resting(_breaks_scene([], s, 0.0, line1), False)
    assert not b.resting(_breaks_scene([], s, b.due + 0.1, line1), False)
    assert b.resting(_breaks_scene([], s, b.ropes_only_until + 0.1, line1), False)


def test_a_mob_on_top_of_us_ends_a_ground_break_and_it_stays_due(line1):
    b = Breaks(Map(line1), Humanizer(seed=3), collections.Counter(), lambda m: None)
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    b.resting(_breaks_scene([], s, 0.0, line1), False)
    due = b.due
    b.kind, b.until = "break", due + 30
    assert not b.resting(_breaks_scene([_mob(1, 1460, 198, 273)], s, due + 1, line1), False)
    assert b.kind is None and b.due == due


def test_keys_go_up_for_a_break_and_the_hunt_resumes(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = _rope_spot(line1)
    _tick(br, drv, 0.0, [], s)
    drv.hold({"up"})
    _tick(br, drv, br.breaks.due + 0.1, [], s)
    assert br.mode == "BREAK" and not drv.want
    end = br.breaks.until + 0.1
    _tick(br, drv, end, [], s)
    assert br.mode != "BREAK"


def test_swarmed_presses_at_once(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273), _mob(2, 1500, 198, 273)], s)
    assert _presses(drv) == [0.0] and br.stats["presses"] == 1


def test_presses_in_the_air_after_a_knockback_never_on_a_rope(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    mobs = [_mob(1, 1480, 198, 273), _mob(2, 1500, 198, 273), _mob(3, 1530, 198, 273)]
    _tick(br, drv, 0.0, mobs, s)
    assert _presses(drv) == [0.0]
    t = 0.07
    while len(_presses(drv)) < 2 and t < 2.5:        # a touch knocked us up and back: Maple attacks in the air
        _tick(br, drv, t, mobs, SelfState(t, 1392, 185, "tag", "air"))
        t += 0.07
    assert len(_presses(drv)) == 2
    while t < 5.0:                                    # no attacks on a rope
        _tick(br, drv, t, mobs, SelfState(t, 1397, 150, "tag", "rope", rope=-1))
        t += 0.07
    assert len(_presses(drv)) == 2


def test_a_death_shown_before_our_swing_is_over_gets_no_press(line1):
    br, drv = _brain(line1), Drv()                # the user's kills: death visible 0.62 / 0.78 / 0.93 s after the
    br.facing = 1                                     # killing press (p10/50/90); the swing is over at ~0.92
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s)
    t = 0.07
    while t < 3.0:
        _tick(br, drv, t, [_mob(1, 1480, 198, 273, state="live" if t < 0.78 else "dying")], s)
        t += 0.07
    assert _presses(drv) == [0.0] and br.stats["swings"] == 1


def test_after_a_kill_the_next_swing_goes_to_another_mob_in_reach(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273), _mob(2, 1510, 198, 273)], s)
    first = br.weapon.engaged
    other = 2 if first == 1 else 1
    t = 0.07
    while len(_presses(drv)) < 2 and t < 2.5:
        _tick(br, drv, t, [_mob(first, 1480, 198, 273, state="dying"), _mob(other, 1510, 198, 273)], s)
        t += 0.07
    assert len(_presses(drv)) == 2 and br.weapon.engaged == other
    assert _presses(drv)[1] >= br.weapon.swing_end - SWING_END - 0.03 >= SWING_END


def test_no_target_switch_mid_fight(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1520, 198, 273)], s)
    assert br.target == 1 and br.weapon.engaged == 1
    for i in range(1, 15):                            # a cheaper mob turns up right beside us: keep fighting #1
        _tick(br, drv, i * 0.07, [_mob(1, 1520, 198, 273), _mob(2, 1470, 198, 273)], s)
    assert br.target == 1


def test_out_of_mp_without_potions_uses_the_plain_attack(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s, mp=0.01, mp_potions=False)
    assert _presses(drv, BASIC) == [0.0] and not _presses(drv)


# ---------------------------------------------------------------- reflexes
def test_potions_and_hp_stop(line1):
    br, drv = _brain(line1), Drv()
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    assert _tick(br, drv, 0.0, [], s, hp=0.3, mp=0.05) is None
    assert _taps(drv, HP_POTION) and _taps(drv, MP_POTION)
    assert _tick(br, drv, 0.1, [], s, hp=0.3, hp_potions=False) is not None


# ---------------------------------------------------------------- targets
def test_target_on_another_platform_starts_a_trip(line1):
    br, drv = _brain(line1), Drv()
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1700, 73, 79)], s)
    assert br.mode == "TRAVEL" and br.travel is not None and br.travel.dst == 79


def test_prefers_the_mob_on_our_platform_over_a_closer_one_upstairs(line1):
    br, drv = _brain(line1), Drv()
    s = SelfState(0, 1500, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1550, 73, 79), _mob(2, 1800, 198, 273)], s)
    assert br.target == 2


def test_kill_counted_by_last_hit(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273), _mob(2, 2400, 198, 273)], s)
    _tick(br, drv, 0.5, [_mob(1, 1480, 198, 273, "dying"), _mob(2, 2400, 198, 273, "dying")], s)
    assert br.stats["kills"] == 1 and br.stats["deaths_not_ours"] == 1


# ---------------------------------------------------------------- a hunt in the sim
class FakeMobs:
    """Bubblings on spawn points: wander on their platform, take a swing that lands in reach (hit 0.6 s), die after
    3 hits (dying 0.8 s), respawn at their spawn 6-9 s later."""

    def __init__(self, nav, reach, spawns, rng):
        self.nav, self.reach, self.rng = nav, reach, rng
        self.mobs, self.next_id = [], 1
        for x, y in spawns:
            p = nav.platform_at(x, y, tol=12)
            if p is not None:
                self.mobs.append(self._new(p, x))
        self.pending = []                             # (t land, facing, our x, y)
        self.deaths, self.after_death = [], 0         # death shown at; swings landing on nothing <= 1.2 s after one

    def _new(self, p, x, t=0.0):
        self.next_id += 1
        return {"id": self.next_id, "mob": BUBBLING, "kind": "mob", "state": "live", "x": x, "y": p.y_at(x),
                "vx": self.rng.choice((-40.0, 40.0)), "platform": p.id, "unseen": 0.0, "src": "acq", "hp": 3,
                "until": 0.0, "home": (p.id, x), "respawn": None}

    def swing(self, t, facing, x, y):
        self.pending.append((t + SWING_LAND_S, facing, x, y))

    def step(self, t, dt):
        for land in [p for p in self.pending if p[0] <= t]:
            self.pending.remove(land)
            _, f, x, y = land
            sure, _ = self.reach.vs(BUBBLING)
            for m in sorted(self.mobs, key=lambda m: abs(m["x"] - x)):     # Power Strike: 1 mob
                if m["state"] in ("live", "hit") and m["hp"] > 0 and sure.has(f * (m["x"] - x), m["y"] - y):
                    m["hp"] -= 1                    # the killing hit: the death animation shows a moment later
                    m["state"], m["until"] = "hit", t + (self.rng.uniform(0.15, 0.45) if m["hp"] <= 0 else 0.6)
                    break
            else:
                if any(0 <= t - d <= 1.2 for d in self.deaths):
                    self.after_death += 1
        for m in self.mobs:
            p = self.nav.platforms[m["platform"]]
            if m["state"] == "live":
                m["x"] += m["vx"] * dt
                if m["x"] < p.left + 10 or m["x"] > p.right - 10 or self.rng.random() < 0.002:
                    m["vx"] = -m["vx"]
                    m["x"] = p.clamp(m["x"])
                m["y"] = p.y_at(m["x"]) or m["y"]
            elif m["state"] == "hit" and t > m["until"] and m["hp"] <= 0:
                m["state"], m["until"] = "dying", t + 0.8
                self.deaths.append(t)
            elif m["state"] == "hit" and t > m["until"]:
                m["state"] = "live"
            elif m["state"] == "dying" and t > m["until"]:
                m["state"], m["respawn"] = "gone", t + self.rng.uniform(6, 9)
            elif m["state"] == "gone" and t > m["respawn"]:
                pid, x = m["home"]
                m.update(self._new(self.nav.platforms[pid], x, t))

    def visible(self, x, y):                          # the screen: 1366 x ~600 around us
        return [{k: v for k, v in m.items() if k not in ("hp", "until", "home", "respawn")} for m in self.mobs
                if m["state"] != "gone" and abs(m["x"] - x) < 683 and abs(m["y"] - y) < 330]


def _hunt(nav, seconds, seed, start=(273, 1400)):
    rng = random.Random(seed)
    cfg = Config()
    br, drv = BrainV2(cfg, nav, Humanizer(seed=seed)), Drv()
    sim = Sim(nav, *start)
    mobs = FakeMobs(nav, br.reach, nav.spawns, rng)
    t, nxt, hist, facing = 0.0, 0.0, [], 1
    flips, swing_end, prev_keys = [], -9.0, set()
    while t < seconds:                                # the game's rules: runs/probe/sauna1 (see v2/combat.py)
        keys = drv.keys(t)
        d = ("right" in keys) - ("left" in keys)
        if d and d != facing and t >= swing_end:      # a direction key counts only once our swing is over
            flips.append(t)
            facing = d
        if keys - prev_keys & {ATTACK, BASIC} and t >= swing_end:   # a key-DOWN swings; mid-swing ones are ignored
            mobs.swing(t, facing, sim.b.x, sim.b.y)
            swing_end = t + br.reach.swing_s
        prev_keys = keys
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
            nxt = t + 0.07 * rng.uniform(0.7, 1.4)
    return br, flips, mobs


@pytest.mark.parametrize("seed", [1, 2])
def test_hunt_in_the_sim_kills_and_moves_between_platforms(line1, seed):
    br, flips, mobs = _hunt(line1, 90.0, seed)
    st = br.stats
    assert st["kills"] >= 9, dict(st)                 # the user: 9.7 / min on this map (with other players)
    assert st["swings"] / st["kills"] <= 6, dict(st)  # 3 hits to kill here + some whiffs
    assert mobs.after_death <= 0.15 * len(mobs.deaths), (mobs.after_death, len(mobs.deaths))   # CLEAN KILLS
    assert st["trips"] >= 2, dict(st)                 # (the user: 7 of 71 kills had one swing at nothing)
    pendulums = sum(1 for i in range(len(flips) - 2) if flips[i + 2] - flips[i] <= 2.5)
    assert pendulums <= 90 / 60 * 3 * 2, (pendulums, len(flips))   # the user: ~8.5 per 3 min


def test_in_the_air_or_on_a_ladder_with_targets_elsewhere_doesnt_crash(line1):
    br, drv = _brain(line1), Drv()                # runs/v2a: started on a ladder -> None < 0 in is_rope
    mobs = [_mob(1, 1700, 73, 79), _mob(2, 2400, 198, 273)]
    for i, s in enumerate([SelfState(0, 1626, 120, "tag", "air"), SelfState(0, 1626, 120, "tag", "rope", rope=-1),
                           SelfState(0, 1626, 150, "minimap", "air")]):
        assert _tick(br, drv, i * 0.5, mobs, s) is None


# ---------------------------------------------------------------- the parts on their own
def _scene(nav, mobs, x=1400, platform=273, facing=1, now=0.0):
    y = nav.platforms[platform].y_at(x)
    return _build(now, mobs, SelfState(now, x, y, "tag", "ground", platform), facing)


def test_scene_marks_reach_and_platform(line1):
    sc = _scene(line1, [_mob(1, 1480, 198, 273), _mob(2, 1330, 198, 273), _mob(3, 1700, 73, 79),
                        _mob(4, 1460, 198, 273, state="dying")])
    by = {x.id: x for x in sc.mobs}
    assert set(by) == {1, 2, 3}                                   # dying isn't live
    assert sc.in_reach(by[1]) and not sc.in_reach(by[2]) and not sc.in_reach(by[3])
    assert by[1].here and not by[3].here


def test_targeting_score_is_the_sum_of_its_terms(line1):
    br = _brain(line1)
    sc = _scene(line1, [_mob(1, 1700, 198, 273), _mob(2, 1760, 198, 273)])
    x = sc.get(1)
    tg = br.targeting
    assert tg.score(sc, x) == pytest.approx(sum(t(sc, x) for t in tg.terms))
    assert tg.t_crowd(sc, x) == -0.25
    br.ledger.contested[1] = 0.0
    assert tg.t_others(sc, x) == 1.5


def test_footwork_rule_table(line1):
    br, drv = _brain(line1), Drv()
    fw = br.footwork
    br.facing = 1
    for mob_x, want in [(1700, "approach"), (1480, "fight"), (1340, "turn")]:
        br.facing = 1
        fw.step(_scene(line1, [_mob(1, mob_x, 198, 273)]), _scene(line1, [_mob(1, mob_x, 198, 273)]).mobs[0],
                90.0, drv)
        assert fw.state == want, (mob_x, fw.state)
    br.face.last_turn, br.face.gap = 0.0, 0.8                     # just turned: no turn yet
    br.facing = 1
    sc = _scene(line1, [_mob(1, 1340, 198, 273)])
    fw.step(sc, sc.mobs[0], 90.0, drv)
    assert fw.state == "brace"


def test_weapon_states_ready_swing_got_away(line1):
    br, drv = _brain(line1), Drv()
    assert br.weapon.step(_scene(line1, [_mob(1, 1480, 198, 273)]), drv, target=1)
    assert br.weapon.state == "swing" and br.weapon.engaged == 1 and _presses(drv) == [0.0]
    assert br.weapon.swing_end == pytest.approx(SWING_END + 0.02) and br.weapon.next_at >= br.weapon.swing_end
    far = [_mob(1, 1700, 198, 273)]                   # it got away: out of keep reach -> no press, not engaged
    t = 0.07
    while t < br.weapon.next_at + 0.1:
        assert not br.weapon.step(_scene(line1, far, now=t), drv, target=1)
        t += 0.07
    assert br.weapon.state == "ready" and br.weapon.engaged is None and _presses(drv) == [0.0]


def test_a_mob_walking_into_us_is_never_predicted_behind_us(line1):
    sc = _scene(line1, [_mob(1, 1430, 198, 273, vx=-120)])        # 30 px in front, coming at us fast
    x = sc.mobs[0]
    assert x.pdx == 0.0 and sc.in_reach(x)                        # at us, not past us: hit it, don't turn
    br, drv = _brain(line1), Drv()
    br.facing = 1
    br.footwork.step(sc, x, 110.0, drv)
    assert br.footwork.state == "fight"


def test_the_engaged_mob_is_kept_to_the_maybe_reach(line1):
    sc = _scene(line1, [_mob(1, 1400 + 150, 198, 273), _mob(2, 1400 + 170, 198, 273)])
    a, b = sc.mobs
    assert sc.in_reach(a, keep=True) and not sc.in_reach(a) and not sc.in_reach(b, keep=True)


def test_a_potion_mid_fight_doesnt_cost_a_swing(line1):
    br, drv = _brain(line1), Drv()                # one press per swing: nothing held for another key to cut
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    mob = [_mob(1, 1480, 198, 273, state="hit")]
    _tick(br, drv, 0.0, mob, s)
    drv.tap(HP_POTION, 0.08)
    t = 0.07
    while len(_presses(drv)) < 2 and t < 2.5:
        _tick(br, drv, t, mob, s)
        t += 0.07
    assert len(_presses(drv)) == 2 and _presses(drv)[1] <= SWING_END + GAP_MAX + 0.1


def test_no_walk_keys_during_our_swing(line1):
    br, drv = _brain(line1), Drv()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s)
    for i in range(1, 12):                            # knocked back to 150 px: maybe reach, not sure
        _tick(br, drv, i * 0.07, [_mob(1, 1550, 198, 273)], s)
        assert drv.want == set() and br.footwork.state == "fight", i
