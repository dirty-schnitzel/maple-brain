"""maplebrain/track/graph.py (PLAN-tracker.md step 2): the nodes, floors, the placement rule, the edges and the seconds
table. Synthetic maps for each rule; real maps (assets/mcw) for the reference tool's chains, a slow plain reference of
the placement rule against the fast one, navmap's own edges and route()'s seconds."""
import importlib.util
import json
import math
import random
import time
from pathlib import Path

import numpy as np
import pytest

from maplebrain.config import Nav, Track
from maplebrain.nav.navmap import NavMap
from maplebrain.track.graph import AIR, EPS, FLY, NONE, ROPE, STAND, Graph, chains, route_table

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "mcw"
LINE1, PERION, SMALL_FOREST, GOLEM, LARGEST = 10003061, 10004000, 1001, 10001102, 90040023


def load(map_id):
    return json.loads((ASSETS / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))


def reference_chains():
    """tools/model/chains_fixed.py, the plan's reference, loaded by path (tools/ stays off sys.path)."""
    spec = importlib.util.spec_from_file_location("chains_fixed", ROOT / "tools" / "model" / "chains_fixed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.chains


# ---------------------------------------------------------------------------------------------------- synthetic
def fh(i, x1, y1, x2, y2, prev=0, nxt=0, **kw):
    return {"id": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "prev": prev, "next": nxt, "piece": 0, "layerId": 0,
            "groupId": 0, **kw}


def mk(fhs, ropes=(), mobs=(), portals=()):
    return {"id": 1, "name": "synthetic", "footholds": {str(f["id"]): f for f in fhs},
            "ladderRopes": [{"x": x, "y1": a, "y2": b, "isLadder": True} for x, a, b in ropes],
            "mobs": list(mobs), "portals": list(portals), "vrBounds": {"left": -500, "top": -500, "right": 900,
                                                                        "bottom": 500}}


def demo():
    """A floor 1 -> 2 (flat 0-100 at y 100, then up a slope to (200, 80)); a platform 10 3 px over the floor's
    left part (50-150 at y 97); a high platform 20 (0-100 at y 0); a rope at x 150 from y 0 to 60; a wall."""
    return mk([fh(1, 0, 100, 100, 100, 0, 2), fh(2, 100, 100, 200, 80, 1, 0),
               fh(10, 50, 97, 150, 97), fh(20, 0, 0, 100, 0), fh(30, -50, 0, -50, 200)],
              ropes=[(150, 0, 60)])


def place1(g, x, y, **kw):
    kw = {k: np.array([v]) for k, v in kw.items()}
    p = g.place(np.array([float(x)]), np.array([float(y)]), **kw)
    return int(p.place[0]), int(p.node[0]), int(p.from_node[0]), float(p.off[0])


def test_stand_air_and_off():
    g = Graph(demo(), edges=False)
    assert place1(g, 20, 101) == (STAND, 1, 1, 1.0)                 # 1 px under the surface (a name tag's offset)
    assert place1(g, 20, 97.5)[:2] == (STAND, 1)                    # 2.5 px over it
    pl, node, frm, off = place1(g, 20, 96)                          # 4 px over: in the air over the floor
    assert (pl, node, frm, off) == (AIR, 1, NONE, -4.0)
    pl, node, _, off = place1(g, 20, 104)                           # 4 px under the floor: over nothing
    assert (pl, node) == (AIR, NONE) and math.isnan(off)
    assert place1(g, 20, -30)[:2] == (AIR, 20)                      # high over the top platform


def test_moving_up_or_down_is_not_standing():
    """A jump passing a platform's level is in the air; walking a slope is not (1 px + the slope's own rise over the
    sideways step, in whole px)."""
    g = Graph(demo(), edges=False)
    assert place1(g, 20, 100, dx=2.0, dy=0.0)[0] == STAND
    assert place1(g, 20, 100, dx=0.0, dy=1.0)[0] == STAND
    assert place1(g, 20, 100, dx=0.0, dy=-1.5)[0] == AIR            # rising through the floor's level
    assert place1(g, 20, 100, dx=5.0, dy=1.5)[0] == AIR             # flat ground: 1 px, however far sideways
    assert place1(g, 150, 90, dx=5.0, dy=-1.0)[0] == STAND           # the slope (0.2): 1 px up in 5 px
    assert place1(g, 150, 90, dx=5.0, dy=2.0)[0] == STAND           # 2 <= 1 + 0.2 * 5
    assert place1(g, 150, 90, dx=5.0, dy=2.5)[0] == AIR
    assert place1(g, 150, 90, dx=-5.0, dy=-2.5)[0] == AIR


def test_the_step_follows_the_slopes_own_rise():
    """The user, 2026-11-25 (PLAN-tracker "Step 3, the slope fix"): mobs walk slopes of 1.8-1.9 (Drakes, Evil Eyes,
    Horny Mushrooms: 2-3 px up or down for 1 px sideways), and whole-pixel feet show 2 px for 1 px on a 0.6 slope -
    the step follows the foothold's own slope + 1 px, rounded up to a whole pixel. Each was in the air with
    1 px + 0.9 x the sideways step."""
    g = Graph(mk([fh(1, 0, 100, 100, 100, 0, 2), fh(2, 100, 100, 200, -80, 1, 3),     # up a 1.8 slope
                  fh(3, 200, -80, 300, -20, 2, 0)]), edges=False)                     # down a 0.6 one
    assert place1(g, 150, 10, dx=1.0, dy=-3.0)[0] == STAND           # 1.8: 3 px up for 1 px (ceil 1.8 + 1)
    assert place1(g, 150, 10, dx=-1.0, dy=2.0)[0] == STAND           # ... 2 px down walking back
    assert place1(g, 150, 10, dx=2.0, dy=-4.0)[0] == STAND           # 2 px sideways: ceil(3.6) + 1 = 5
    assert place1(g, 150, 10, dx=1.0, dy=-3.5)[0] == AIR             # over 3 for 1
    assert place1(g, 250, -50, dx=1.0, dy=2.0)[0] == STAND           # 0.6: 2 px for 1 px (ceil 0.6 + 1)
    assert place1(g, 250, -50, dx=-1.0, dy=-2.0)[0] == STAND
    assert place1(g, 250, -50, dx=1.0, dy=2.5)[0] == AIR
    assert place1(g, 250, -50, dx=0.0, dy=2.0)[0] == AIR             # no sideways step: 1 px, as on flat ground
    assert place1(g, 50, 100, dx=1.0, dy=2.0)[0] == AIR              # the flat part keeps 1 px


def test_two_surfaces_within_3px_the_last_node_wins():
    g = Graph(demo(), edges=False)
    assert place1(g, 60, 98.5)[:2] == (STAND, 1)                    # equal distance: the lower id
    assert place1(g, 60, 98.5, last=10)[:2] == (STAND, 10)          # ... but the last frame's node wins
    assert place1(g, 60, 99.5)[:2] == (STAND, 1)                    # the nearest
    assert place1(g, 60, 99.5, last=10)[:2] == (STAND, 10)
    assert place1(g, 60, 99.5, last=20)[:2] == (STAND, 1)           # the last node is not within 3 px


def test_chain_ends_and_joints_on_whole_pixels():
    g = Graph(demo(), edges=False)
    assert place1(g, 200, 80)[:2] == (STAND, 1)                     # the chain's right end itself
    assert place1(g, 200.5, 80)[:2] == (AIR, NONE)                  # past it
    assert place1(g, 0, 100)[:2] == (STAND, 1)                      # the left end
    assert place1(g, -0.5, 100)[:2] == (AIR, NONE)
    assert place1(g, 100, 100)[:2] == (STAND, 1)                    # the joint of footholds 1 and 2
    assert place1(g, 150, 90) == (STAND, 1, 1, 0.0)                 # on the slope, exact
    assert place1(g, 150.25, 89.95)[3] == pytest.approx(0.0, abs=1e-9)
    assert place1(g, 5000, 0)[:2] == (AIR, NONE) and place1(g, -5000, 0)[:2] == (AIR, NONE)


def test_ropes_for_climbers_only_and_not_over_a_stand():
    g = Graph(demo(), edges=False)
    assert place1(g, 150, 30) [:2] == (AIR, 1)                      # not a climber
    assert place1(g, 150, 30, climb=True) == (ROPE, -1, -1, 0.0)
    assert place1(g, 156, 30, climb=True)[:2] == (ROPE, -1)         # within 7 px of its x
    assert place1(g, 158, 30, climb=True)[:2] == (AIR, 1)
    assert place1(g, 150, -6, climb=True)[:2] == (ROPE, -1)         # within 7 px of its top
    assert place1(g, 150, -8, climb=True)[:2] == (AIR, 1)           # over the floor's slope (y 90 at x 150)
    assert place1(g, 150, 97, climb=True)[:2] == (STAND, 10)        # standing wins over the rope's x


def test_stand_within_5px_of_a_slope_3px_of_flat_ground():
    """The user, 2026-11-24 (PLAN-tracker step 3's answers): mobs' feet sit 3.6-4.4 px off a slope - "allow 5 px" on
    a foothold that is not level; flat ground keeps 3 px."""
    g = Graph(mk([fh(1, 0, 100, 100, 100, 0, 2), fh(2, 100, 100, 200, 80, 1, 0)]), edges=False)
    assert place1(g, 150, 85.5)[:2] == (STAND, 1)                    # 4.5 px over the slope (y 90 at x 150)
    assert place1(g, 150, 94.6)[:2] == (STAND, 1)                    # 4.6 px under it
    assert place1(g, 150, 84.5)[:2] == (AIR, 1)                      # 5.5 px over it
    assert place1(g, 20, 96)[:2] == (AIR, 1)                         # 4 px over the flat part: in the air
    assert place1(g, 20, 97.5)[:2] == (STAND, 1)                     # 2.5 px over it
    assert place1(g, 200, 76)[:2] == (STAND, 1)                      # the slope's right end (the chain's end)
    assert place1(g, 100, 96)[:2] == (STAND, 1)                      # the joint: the foothold going on (the slope)
    assert place1(g, 99.5, 96)[:2] == (AIR, 1)                       # just before it: the flat one
    assert place1(g, 150, 85.5, dx=0.0, dy=-2.0)[0] == AIR           # the step rule still holds


def test_a_flyer_never_stands():
    """The user, 2026-11-24: "Stirges never land" - a kind that flies is never `stand`, whatever its distance to a
    surface; its node is the first surface under it, its from_node is not changed."""
    g = Graph(demo(), edges=False)
    assert place1(g, 20, 100, fly=True) == (FLY, 1, NONE, 0.0)       # exactly on the floor
    assert place1(g, 20, 100, fly=True, last=1, last_from=1)[2] == 1
    p = g.place([20, 20], [100, 100], fly=[True, False])
    assert list(p.place) == [FLY, STAND] and list(p.from_node) == [NONE, 1]


def test_fly_and_from_node():
    g = Graph(demo(), edges=False)
    assert place1(g, 20, 50, fly=True)[0] == FLY
    assert place1(g, 20, 50, last=1, last_from=1)[2] == 1          # in the air: the node stood on is kept
    assert place1(g, 20, 0, last=1, last_from=1)[2] == 20          # landed: the new one
    assert place1(g, 150, 30, climb=True, last_from=1)[2] == -1     # hung on a rope: the rope


def test_many_things_one_call_and_empty():
    g = Graph(demo(), edges=False)
    p = g.place([20, 20, 150, 60], [101, 50, 30, 98.5], climb=[False, False, True, False], last=[0, 0, 0, 10])
    assert list(p.place) == [STAND, AIR, ROPE, STAND] and list(p.node) == [1, 1, -1, 10]
    e = g.place(np.zeros(0), np.zeros(0))
    assert len(e.place) == len(e.node) == len(e.off) == 0


def test_chains_from_complete_links():
    """A floor piece whose prev is walkable but does not link back starts a chain of its own (navmap: every piece
    after it stands alone); a one-way next is not followed (navmap: it runs on across it)."""
    fhs = [fh(40, 0, 0, 10, 0, 0, 41), fh(41, 10, 0, 20, 0, 40, 0),
           fh(42, 20, 0, 30, 0, 99, 43), fh(43, 30, 0, 40, 0, 42, 44), fh(44, 40, 0, 50, 0, 43, 0),
           fh(99, -100, 50, -90, 50, 0, 0),                                     # 42's prev, linking nowhere
           fh(50, 0, 100, 10, 100, 0, 51), fh(51, 10, 100, 20, 100, 60, 0),      # 50 -> 51 one way
           fh(60, 10, 80, 10, 100, 0, 51)]                                      # a wall at x 10
    ch = sorted(chains({f["id"]: f for f in fhs}))
    assert ch == [[40, 41], [42, 43, 44], [50], [51], [99]]
    nm = NavMap.from_json(mk(fhs))
    assert sorted(nm.platforms) == [40, 42, 43, 44, 50, 99]             # today: 43, 44 alone; 50 runs into 51


def test_floors_join_only_level_joints_without_a_wall():
    fhs = [fh(1, 0, 0, 100, 0), fh(2, 100, 0, 200, 0),                   # a level joint, no link either way
           fh(3, 300, 0, 400, 0, 0, 4), fh(4, 400, 0, 500, 0, 5, 0), fh(5, 400, -40, 400, 0, 0, 4),   # a wall on it
           fh(6, 600, 0, 700, 0), fh(7, 650, -50, 700, 0)]                 # a T: 7's foot... no: 7 ends at 6's end
    g = Graph(mk(fhs), edges=False)
    assert g.floor_of([1])[0] == g.floor_of([2])[0]
    assert g.floor_of([3])[0] != g.floor_of([4])[0]
    assert bool(g.same_floor([1], [2])[0]) and not g.same_floor([3], [4])[0] and not g.same_floor([6], [7])[0]
    assert g.n_floors == g.n_chains - 1


def test_real_chains_are_the_reference_tools_on_every_map():
    ref = reference_chains()
    joints_bad = 0
    for d in sorted((ASSETS / "maps").iterdir(), key=lambda p: int(p.name)):
        m = json.loads((d / "map.json").read_text(encoding="utf-8"))
        g = Graph(m, edges=False)
        fhs = {int(k): v for k, v in m["footholds"].items()}
        assert g.chains == sorted(ref(fhs), key=lambda c: c[0]), m["id"]
        walk = sorted(i for i, f in fhs.items() if f["x1"] < f["x2"])
        assert sorted(i for c in g.chains for i in c) == walk
        joints_bad += sum(1 for j in g.floor_joints if j[5] != "none")
        for a, b, *_ in g.floor_joints:
            assert g.same_floor([a], [b])[0]
    assert joints_bad == 0                                               # a floor joint has no link either way


def test_rope_ids_and_tops_match_navmap():
    m = load(LINE1)
    g, nm = Graph(m, edges=False), NavMap.from_json(m)
    assert list(g.ids[g.n_chains:]) == [nm.rope_id(i) for i in range(len(nm.ropes))]
    tops = [(t.id if (t := nm._top_platform(r)) is not None else NONE) for r in nm.ropes]
    assert list(g.rope_top_node) == tops


def test_fixed_places():
    m = load(LINE1)
    g = Graph(m, edges=False)
    sp = [v for v in m["mobs"] if not v.get("hidden")]
    assert len(g.spawn_node) == len(sp) and g.spawn_node[0] == g.chain_of[sp[0]["footholdId"]]
    assert len(g.portal_node) == len(m["portals"])


# ---------------------------------------------------------------------------------------------------- the rule
def tol_at(c, p, x):
    """The stand tolerance of chain p at x: its foothold there (at a joint the one going on, at the chain's right end
    the last) level or not."""
    s = seg_at(p, x)
    return c.stand_tol_slope if s is not None and s.y1 != s.y2 else c.stand_tol


def seg_at(p, x):
    """Chain p's foothold at x: at a joint the one going on, at the chain's right end the last."""
    return next((s for s in p.segs if s.x1 <= x < s.x2), p.segs[-1] if x == p.right else None)


def step_ok(c, p, x, dx, dy):
    """The step since the last frame on chain p at x: within 1 px + its foothold's own rise over the sideways step,
    rounded up to a whole pixel."""
    s = seg_at(p, x)
    slope = abs((s.y2 - s.y1) / (s.x2 - s.x1))
    return abs(dy) <= c.stand_step + EPS + math.ceil(slope * abs(dx) - EPS)


def slow_place(g, x, y, dx, dy, last, last_from, climb, fly):
    """The placement rule written plainly over every chain (Platform.y_at) and rope: the reference."""
    c = g.cfg
    surf = [(p.y_at(x), p.id, tol_at(c, p, x)) for p in g.platforms.values() if p.y_at(x) is not None]
    within = sorted((abs(y - sy), pid) for sy, pid, tol in surf if abs(y - sy) <= tol + EPS)
    surf = [(sy, pid) for sy, pid, _ in surf]
    if within and not fly:
        pid = last if any(pid == last for _, pid in within) else within[0][1]
        if step_ok(c, g.platforms[pid], x, dx, dy):
            return STAND, pid, pid, y - g.platforms[pid].y_at(x)
    if climb:
        rs = [(abs(x - r.x), i) for i, r in enumerate(g.ropes)
              if abs(x - r.x) <= c.rope_tol and r.top - c.rope_tol <= y <= r.bottom + c.rope_tol]
        if rs:
            i = min(rs)[1]
            return ROPE, -1 - i, -1 - i, x - g.ropes[i].x
    under = sorted((abs(sy - y), pid) for sy, pid in surf if sy >= y - EPS)
    node, off = (under[0][1], y - g.platforms[under[0][1]].y_at(x)) if under else (NONE, math.nan)
    return (FLY if fly else AIR), node, last_from, off


@pytest.mark.parametrize("map_id", [LINE1, PERION, SMALL_FOREST, GOLEM, LARGEST])
def test_place_equals_the_plain_rule_on_real_maps(map_id):
    g = Graph(load(map_id), edges=False)
    rnd = random.Random(map_id)
    ps = list(g.platforms.values())
    nodes = [int(v) for v in g.ids] + [NONE]
    xs, ys, ex = [], [], []
    for i in range(1500):
        p = rnd.choice(ps)
        kind = i % 5
        if kind == 0:                                                    # a chain's end or a foothold's joint
            x = float(rnd.choice([p.left, p.right] + [s.x1 for s in p.segs]))
        elif kind == 1:                                                  # a whole pixel
            x = float(rnd.randint(int(p.left) - 3, int(p.right) + 3))
        elif kind == 2 and g.ropes:                                     # by a rope
            r = rnd.choice(g.ropes)
            x = r.x + rnd.uniform(-9, 9)
        else:
            x = rnd.uniform(p.left - 5, p.right + 5)
        sy = p.y_at(min(max(x, p.left), p.right))
        y = sy + rnd.choice([rnd.uniform(-5, 5), rnd.uniform(-80, 80), float(rnd.randint(-4, 4))])
        if kind == 2 and g.ropes:
            y = rnd.uniform(r.top - 10, r.bottom + 10)
        dx = rnd.choice([0.0, rnd.uniform(-6, 6)])
        dy = rnd.choice([0.0, rnd.uniform(-1.2, 1.2), rnd.uniform(-8, 8)])
        xs.append(x)
        ys.append(y)
        ex.append((dx, dy, rnd.choice(nodes), rnd.choice(nodes), rnd.random() < 0.3, rnd.random() < 0.2))
    for k0 in range(0, len(xs), 20):                                     # 20 things a call, as a frame
        sl = slice(k0, k0 + 20)
        e = ex[sl]
        p = g.place(np.array(xs[sl]), np.array(ys[sl]), np.array([v[0] for v in e]), np.array([v[1] for v in e]),
                    np.array([v[2] for v in e]), np.array([v[3] for v in e]), np.array([v[4] for v in e]),
                    np.array([v[5] for v in e]))
        for j, (x, y, v) in enumerate(zip(xs[sl], ys[sl], e)):
            want = slow_place(g, x, y, *v)
            got = (int(p.place[j]), int(p.node[j]), int(p.from_node[j]), float(p.off[j]))
            assert got[:3] == want[:3], (map_id, x, y, v, got, want)
            assert (math.isnan(got[3]) and math.isnan(want[3])) or got[3] == pytest.approx(want[3], abs=1e-6)


def test_nearest_is_platform_at_on_a_map_with_navmaps_nodes():
    m = load(LINE1)
    g, nm = Graph(m, edges=False), NavMap.from_json(m)
    rnd = random.Random(7)
    ps = list(nm.platforms.values())
    for _ in range(500):
        p = rnd.choice(ps)
        x = rnd.uniform(p.left, p.right)
        y = p.y_at(x) + rnd.uniform(-20, 20)
        r = min(((abs(yp - y), q.id) for q, yp in nm.surfaces(x) if abs(yp - y) <= 16), default=(0, NONE))[1]
        assert int(g.nearest([x], [y], 16)[0][0]) == r


def test_surface_y_and_ix():
    m = load(PERION)
    g = Graph(m, edges=False)
    p = g.platforms[int(g.ids[3])]
    xs = np.linspace(p.left, p.right, 50)
    assert np.allclose(g.surface_y(np.full(50, p.id), xs), [p.y_at(x) for x in xs])
    assert np.isnan(g.surface_y([p.id, NONE], [p.right + 1, p.left])).all()
    assert list(g.ix([int(g.ids[5]), -1, 123456789])) == [5, g.n_chains, -1]


# ---------------------------------------------------------------------------------------------------- the edges
def test_edges_are_navmaps_links_and_the_table_is_routes_seconds():
    m = load(LINE1)
    g, nm = Graph(m), NavMap.from_json(m)
    assert sorted(g.edges.nav.links, key=repr) == sorted(nm.links, key=repr)
    rnd = random.Random(11)
    nav = g.edges.nav
    for _ in range(300):
        a, b = rnd.sample(range(len(g.ids)), 2)
        r = nav.route(int(g.ids[a]), float(g.start[a]), int(g.ids[b]), with_cost=True)
        assert g.edges.seconds[a, b] == (np.inf if r is None else r[1])
        if r is not None:
            assert g.seconds(int(g.ids[a]), int(g.ids[b])) == r[1]
    assert (np.diag(g.edges.seconds) == 0).all()


def test_table_on_a_map_whose_nodes_differ_from_navmap():
    """Perion: the chains here are not navmap's; the table is route()'s over the graph's own nodes."""
    g = Graph(load(PERION))
    nav = g.edges.nav
    rnd = random.Random(3)
    for _ in range(150):
        a, b = rnd.sample(range(len(g.ids)), 2)
        r = nav.route(int(g.ids[a]), float(g.start[a]), int(g.ids[b]), with_cost=True)
        assert g.edges.seconds[a, b] == (np.inf if r is None else r[1])
    assert set(l.src for l in nav.links) <= set(int(v) for v in g.ids)


def test_a_rebuild_does_not_block_a_frame():
    """New values -> new edges and table on a worker thread; meanwhile every frame's reads answer at once from the
    old set; the new one is swapped in whole; the newest request wins. The worker shares Python's GIL with the frame:
    a call now and then waits for it (PLAN-tracker step 2's numbers: up to ~20 ms on Line 1), so the tail is not
    asserted, only that the frame never waits for the rebuild itself."""
    m = load(LINE1)
    g = Graph(m)
    old = g.edges
    xs = np.array([p.left + 5.0 for p in g.platforms.values()][:20])
    ys = np.array([p.y_at(p.left + 5.0) for p in g.platforms.values()][:20])
    th = g.rebuild(Nav(jump_height=90))
    t_start = time.perf_counter()
    reads, lat = [], []
    while g.rebuilding:
        t0 = time.perf_counter()
        g.place(xs, ys)
        e = g.edges
        _ = e.seconds[0, 1]
        reads.append("old" if e is old else "new" if e.cfg.jump_height == 90 else "?")
        lat.append(time.perf_counter() - t0)
    th.join()
    took = time.perf_counter() - t_start
    assert "?" not in reads and reads.count("old") >= 20                 # whole sets only, the old one meanwhile
    assert "old" not in reads[reads.index("new"):] if "new" in reads else True
    assert np.percentile(lat, 99) < 1e-3 and max(lat) < took / 4         # answered at once, not after the rebuild
    assert g.edges is not old and g.edges.cfg.jump_height == 90
    assert g.edges.nav.links != old.nav.links
    a, b = g.rebuild(Nav(jump_height=50)), g.rebuild(Nav(jump_height=60))
    a.join()
    b.join()
    assert g.edges.cfg.jump_height == 60


def test_route_table_alone_matches_route_from_any_start():
    """route_table from other starts (the left ends) = route() from there: the search is route()'s own."""
    m = load(LINE1)
    g = Graph(m)
    nav = g.edges.nav
    starts = np.array([nav.platforms[int(i)].left if i > 0 else nav.rope(int(i)).top for i in g.ids], float)
    sec, arr = route_table(nav, g.ids, starts)
    rnd = random.Random(5)
    for _ in range(200):
        a, b = rnd.sample(range(len(g.ids)), 2)
        r = nav.route(int(g.ids[a]), float(starts[a]), int(g.ids[b]), with_cost=True)
        assert sec[a, b] == (np.inf if r is None else r[1])
