"""brain-v2 M2 (combat): reach from the client's attack boxes, WHEN TO HIT, targets, reflexes, and a hunt in the
movement sim on the real Line 1 map with fake mobs (walk, get hit, die, respawn)."""
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from maplebot.brain.brain_v2 import BrainV2
from maplebot.brain.reach import SWING_LAND_S, Reach, body, boxes_vs
from maplebot.config import Config
from maplebot.humanize import Humanizer
from maplebot.nav.navmap import NavMap
from maplebot.nav.selfstate import SelfState
from maplebot.nav.sim import Sim, SimDriver

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"
BUBBLING = 14


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


# ---------------------------------------------------------------- reach
def test_spear_and_polearm_reach_vs_bubbling_from_the_client_boxes():
    for w in ("spear", "poleArm"):
        sure, maybe = Reach(w).vs(BUBBLING)
        assert 20 <= sure.lo <= 32 and 130 <= sure.hi <= 142      # stab/swing boxes overlap 52..111 + body +-26
        assert maybe.lo < 5 and 150 <= maybe.hi <= 165
        assert sure.has(72, 0) and not sure.has(170, 0) and not sure.has(80, -60)   # the user's median kill: 72


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
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s)
    assert "space" in drv.want and br.stats["swings"] == 1


def test_no_swing_out_of_reach_walks_toward_it_instead(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1700, 198, 273)], s)
    assert not _taps(drv, "space") and drv.want == {"right"}


def test_predicts_a_mob_walking_into_reach(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    hi = br.reach.vs(BUBBLING)[0].hi
    _tick(br, drv, 0.0, [_mob(1, 1400 + hi + 20, 198, 273, vx=-80)], s)    # 20 px out now, 16 px in when it lands
    assert "space" in drv.want
    assert -80 * SWING_LAND_S < -20


def test_a_mob_behind_us_turns_us_round_first(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1330, 198, 273)], s)
    assert not _taps(drv, "space") and _taps(drv, "left") and br.facing == -1
    _tick(br, drv, 0.3, [_mob(1, 1330, 198, 273)], s)
    assert "space" in drv.want


def test_never_swings_at_nothing_or_at_dying_mobs(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    for i in range(30):
        _tick(br, drv, i * 0.1, [_mob(1, 1460, 198, 273, state="dying"), _mob(2, 1470, 198, 273, state="tentative")], s)
    assert br.stats["swings"] == 0


def test_holds_while_the_mob_is_knocked_back_and_lets_go_after_it_dies(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s)
    assert "space" in drv.want and not _taps(drv, "space") and br.weapon.state == "pressure"
    for i in range(1, 8):                             # knocked back: moving away fast, still within the maybe reach
        _tick(br, drv, i * 0.07, [_mob(1, 1480 + 8 * i, 198, 273, vx=220)], s)
        assert "space" in drv.want, i
    for i in range(10):                               # it died: let go within ~0.15-0.35 s
        _tick(br, drv, 0.6 + i * 0.07, [], s)
    assert "space" not in drv.want and br.weapon.state == "ready"


def test_no_turning_while_the_attack_is_held(line1):
    br, drv = _brain(line1), SimDriver()                # the game ignores a direction key mid-swing (runs/v2c)
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273), _mob(2, 1340, 198, 273)], s)
    assert "space" in drv.want
    _tick(br, drv, 0.07, [_mob(2, 1340, 198, 273)], s)  # the one in front died; the other is behind
    assert not _taps(drv, "left") and br.facing == 1
    for i in range(2, 12):
        _tick(br, drv, i * 0.07, [_mob(2, 1340, 198, 273)], s)
    assert br.stats["turns"] == 1 and br.facing == -1  # let go, turned, and (now in front) holds at it again


def test_swarmed_holds_at_once(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273), _mob(2, 1500, 198, 273)], s)
    assert "space" in drv.want and not _taps(drv, "space") and br.stats["holds"] == 1


def test_held_attack_survives_walking_and_knockback_into_the_air_but_not_a_rope(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    mobs = [_mob(1, 1480, 198, 273), _mob(2, 1500, 198, 273), _mob(3, 1530, 198, 273)]
    _tick(br, drv, 0.0, mobs, s)
    br.hands.hold({"right"})                          # footwork / Travel holding a walk key keeps the attack held
    assert drv.want == {"right", "space"}
    _tick(br, drv, 0.1, mobs, SelfState(0.1, 1392, 185, "tag", "air"))     # a touch knocked us up and back
    assert "space" in drv.want                        # Maple attacks in the air: keep holding (runs/v2 09:21: 152 cuts)
    _tick(br, drv, 0.2, mobs, SelfState(0.2, 1397, 150, "tag", "rope", rope=-1))
    assert "space" not in drv.want                    # no attacks on a rope


def test_holds_until_the_death_animation_then_lets_go_a_human_reaction_later(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    t = 0.0
    while t < 5.0:                                    # 5 s on one tough mob: never let go
        _tick(br, drv, t, [_mob(1, 1480, 198, 273)], s)
        assert "space" in drv.want, t
        t += 0.07
    died = t
    while "space" in drv.want and t < died + 1.0:     # death animation: let go 0.18-0.32 s later
        _tick(br, drv, t, [_mob(1, 1480, 198, 273, state="dying")], s)
        t += 0.07
    assert 0.18 <= t - died <= 0.32 + 0.15


def test_after_a_kill_another_mob_in_reach_keeps_the_key_held(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273), _mob(2, 1510, 198, 273)], s)
    first = br.weapon.engaged
    other = 2 if first == 1 else 1
    for i in range(1, 12):
        _tick(br, drv, i * 0.07, [_mob(first, 1480, 198, 273, state="dying"), _mob(other, 1510, 198, 273)], s)
        assert "space" in drv.want, i
    assert br.weapon.engaged == other and br.stats["held_on"] == 1


def test_no_target_switch_mid_fight(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1520, 198, 273)], s)
    assert br.target == 1 and br.weapon.engaged == 1
    for i in range(1, 15):                            # a cheaper mob turns up right beside us: keep fighting #1
        _tick(br, drv, i * 0.07, [_mob(1, 1520, 198, 273), _mob(2, 1470, 198, 273)], s)
    assert br.target == 1


def test_out_of_mp_without_potions_uses_the_plain_attack(line1):
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1480, 198, 273)], s, mp=0.01, mp_potions=False)
    assert "c" in drv.want and "space" not in drv.want


# ---------------------------------------------------------------- reflexes
def test_potions_and_hp_stop(line1):
    br, drv = _brain(line1), SimDriver()
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    assert _tick(br, drv, 0.0, [], s, hp=0.3, mp=0.05) is None
    assert _taps(drv, "delete") and _taps(drv, "end")
    assert _tick(br, drv, 0.1, [], s, hp=0.3, hp_potions=False) is not None


# ---------------------------------------------------------------- targets
def test_target_on_another_platform_starts_a_trip(line1):
    br, drv = _brain(line1), SimDriver()
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1700, 73, 79)], s)
    assert br.mode == "TRAVEL" and br.travel is not None and br.travel.dst == 79


def test_prefers_the_mob_on_our_platform_over_a_closer_one_upstairs(line1):
    br, drv = _brain(line1), SimDriver()
    s = SelfState(0, 1500, 198, "tag", "ground", 273)
    _tick(br, drv, 0.0, [_mob(1, 1550, 73, 79), _mob(2, 1800, 198, 273)], s)
    assert br.target == 2


def test_kill_counted_by_last_hit(line1):
    br, drv = _brain(line1), SimDriver()
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
                if m["state"] in ("live", "hit") and sure.has(f * (m["x"] - x), m["y"] - y):
                    m["hp"] -= 1
                    m["state"], m["until"] = ("dying", t + 0.8) if m["hp"] <= 0 else ("hit", t + 0.6)
                    break
        for m in self.mobs:
            p = self.nav.platforms[m["platform"]]
            if m["state"] == "live":
                m["x"] += m["vx"] * dt
                if m["x"] < p.left + 10 or m["x"] > p.right - 10 or self.rng.random() < 0.002:
                    m["vx"] = -m["vx"]
                    m["x"] = p.clamp(m["x"])
                m["y"] = p.y_at(m["x"]) or m["y"]
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
    br, drv = BrainV2(cfg, nav, Humanizer(seed=seed)), SimDriver()
    sim = Sim(nav, *start)
    mobs = FakeMobs(nav, br.reach, nav.spawns, rng)
    t, nxt, hist, facing = 0.0, 0.0, [], 1
    flips, down, next_auto, swing_t = [], False, 0.0, -9.0
    while t < seconds:
        keys = drv.keys(t)
        d = ("right" in keys) - ("left" in keys)
        if d and d != facing and t - swing_t > 0.55:              # the game ignores direction keys mid-swing
            flips.append(t)
            facing = d
        if "space" in keys and (not down or t >= next_auto):      # a press swings; held, it swings again
            mobs.swing(t, facing, sim.b.x, sim.b.y)               # every 0.6 s (the game's repeat)
            next_auto, swing_t = t + 0.6, t
        down = "space" in keys
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
    return br, flips


@pytest.mark.parametrize("seed", [1, 2])
def test_hunt_in_the_sim_kills_and_moves_between_platforms(line1, seed):
    br, flips = _hunt(line1, 90.0, seed)
    st = br.stats
    assert st["kills"] >= 9, dict(st)                 # the user: 9.7 / min on this map (with other players)
    assert st["swings"] / st["kills"] <= 6, dict(st)  # 3 hits to kill here + some whiffs
    assert st["trips"] >= 2, dict(st)
    pendulums = sum(1 for i in range(len(flips) - 2) if flips[i + 2] - flips[i] <= 2.5)
    assert pendulums <= 90 / 60 * 3 * 2, (pendulums, len(flips))   # the user: ~8.5 per 3 min


def test_in_the_air_or_on_a_ladder_with_targets_elsewhere_doesnt_crash(line1):
    br, drv = _brain(line1), SimDriver()                # runs/v2a: started on a ladder -> None < 0 in is_rope
    mobs = [_mob(1, 1700, 73, 79), _mob(2, 2400, 198, 273)]
    for i, s in enumerate([SelfState(0, 1626, 120, "tag", "air"), SelfState(0, 1626, 120, "tag", "rope", rope=-1),
                           SelfState(0, 1626, 150, "minimap", "air")]):
        assert _tick(br, drv, i * 0.5, mobs, s) is None


# ---------------------------------------------------------------- the parts on their own
def _scene(nav, mobs, x=1400, platform=273, facing=1, now=0.0):
    from maplebot.brain.v2.scene import Scene
    y = nav.platforms[platform].y_at(x)
    return Scene.build(now, _obs(mobs), SelfState(now, x, y, "tag", "ground", platform), facing, Reach("spear"))


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
    br, drv = _brain(line1), SimDriver()
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


def test_weapon_states_ready_pressure_got_away(line1):
    from maplebot.brain.v2.combat import Hands
    br, drv = _brain(line1), SimDriver()
    h = Hands(drv)
    assert br.weapon.step(_scene(line1, [_mob(1, 1480, 198, 273)]), _obs(), h, target=1)
    assert br.weapon.state == "pressure" and br.weapon.engaged == 1 and "space" in drv.want
    far = [_mob(1, 1700, 198, 273)]                   # it got away: out of keep reach for 0.3-0.5 s -> let go
    for i in range(1, 10):
        br.weapon.step(_scene(line1, far, now=i * 0.07), _obs(), h, target=1)
    assert br.weapon.state == "ready" and "space" not in drv.want and br.stats["got_away"] == 1


def test_a_mob_walking_into_us_is_never_predicted_behind_us(line1):
    sc = _scene(line1, [_mob(1, 1430, 198, 273, vx=-120)])        # 30 px in front, coming at us fast
    x = sc.mobs[0]
    assert x.pdx == 0.0 and sc.in_reach(x)                        # at us, not past us: hit it, don't turn
    br, drv = _brain(line1), SimDriver()
    br.facing = 1
    br.footwork.step(sc, x, 110.0, drv)
    assert br.footwork.state == "fight"


def test_a_held_attack_is_kept_to_the_maybe_reach(line1):
    sc = _scene(line1, [_mob(1, 1400 + 150, 198, 273), _mob(2, 1400 + 170, 198, 273)])
    a, b = sc.mobs
    assert sc.in_reach(a, keep=True) and not sc.in_reach(a) and not sc.in_reach(b, keep=True)
