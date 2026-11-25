"""maplebrain/track/spawns.py (PLAN-tracker step 3b): spawn points as tracked things - a mob born faded in, traced
back to its point (rule (c): its kind, its node, reachable in the time since it appeared, one hop up, a flyer at
spriteY; two candidates -> none), the record (last_spawn_t, last_mob, spawns, in_view), blind frames. Its numbers on
recorded footage: tools/perc/track/proto_spawns.py (the measure) and replay_mobs.py (the real code)."""
from types import SimpleNamespace

from maplebrain.config import Track
from maplebrain.track.graph import Graph
from maplebrain.track.spawns import Spawns
from test_track_graph import fh, mk
from test_track_mobs import DT, a_kind, ev, facts, mob
from maplebrain.track.mobs import MobTracker

C = (0, 0)
FLOOR, HIGH = 1, 2                                  # node ids = the first foothold's id of each chain


def pt(i, kind, x, y, sprite_y=None):
    return {"index": i, "id": kind, "x": x, "y": y, "spriteY": y if sprite_y is None else sprite_y,
            "footholdId": FLOOR if y == 500 else HIGH, "mobTime": 0, "hidden": False}


def graph(points):
    return Graph(mk([fh(1, 0, 500, 1300, 500), fh(2, 0, 300, 600, 300)], mobs=points), edges=False)


def spawns(points, jump=False, fly=False):
    k = a_kind(jump=jump)                           # v 100 px/s
    k.fly = fly
    return Spawns(graph(points), {1: k}, Track())


def rec(i, x, y, o, node=FLOOR, t=1.0, seen=True, kind=1):
    return SimpleNamespace(id=i, kind=kind, x=x, y=y, sx=x - C[0], sy=y - C[1], from_node=node, opacity=o,
                           born_t=t, seen=seen)


def born(sp, r, how="faded in", t=1.0, **kw):
    """The mob tracker's first sighting of r, then its mob_new event -> the spawns seen."""
    sp.update(t, C, [r], [], **kw)
    return sp.update(t + DT, C, [r], [{"ev": "mob_new", "id": r.id, "kind": r.kind, "how": how}], **kw)


def test_a_faded_in_birth_on_its_point_is_that_points_spawn():
    sp = spawns([pt(0, 1, 600, 500), pt(1, 1, 200, 500)])
    evs = born(sp, rec(7, 600, 500, 0.18))
    p = sp.points[0]
    assert (p.last_spawn_t, p.last_mob, p.spawns) == (1.0, 7, 1) and sp.points[1].spawns == 0
    assert [e["ev"] for e in evs] == ["spawn_seen"]


def test_traced_back_in_the_time_since_it_appeared():
    """Opacity 0.5 = 0.41 s since it appeared: 100 px/s -> 51 px of reach (+ 10); opacity 0.1 = 0.08 s -> 18 px."""
    sp = spawns([pt(0, 1, 600, 500)])
    born(sp, rec(7, 645, 500, 0.5))
    assert sp.points[0].spawns == 1
    sp = spawns([pt(0, 1, 600, 500)])
    born(sp, rec(7, 645, 500, 0.1))
    assert sp.points[0].spawns == 0 and sp.stats["no point"] == 1


def test_one_hop_up_only_for_a_kind_that_jumps_and_only_on_its_node():
    sp = spawns([pt(0, 1, 600, 500)], jump=True)
    born(sp, rec(7, 600, 450, 0.2))                 # 50 px over its node, x on the point
    assert sp.points[0].spawns == 1
    sp = spawns([pt(0, 1, 600, 500)])
    born(sp, rec(7, 600, 450, 0.2))
    assert sp.points[0].spawns == 0
    sp = spawns([pt(0, 1, 300, 300)], jump=True)    # the point on the high platform; the mob seen on the floor
    born(sp, rec(7, 300, 500, 0.2, node=FLOOR))
    assert sp.points[0].spawns == 0


def test_a_flyer_is_traced_to_the_points_sprite_height():
    sp = spawns([pt(0, 1, 600, 500, sprite_y=400)], fly=True)
    born(sp, rec(7, 600, 400, 0.2))
    assert sp.points[0].spawns == 1
    sp = spawns([pt(0, 1, 600, 500, sprite_y=400)], fly=True)
    born(sp, rec(7, 600, 500, 0.2))                 # at the foothold y, 100 px from spriteY: not reachable
    assert sp.points[0].spawns == 0


def test_two_candidate_points_is_no_spawn_never_a_guess():
    sp = spawns([pt(0, 1, 600, 500), pt(1, 1, 650, 500)])
    born(sp, rec(7, 625, 500, 0.5))
    assert [p.spawns for p in sp.points] == [0, 0] and sp.stats["two or more points"] == 1


def test_a_mob_born_another_way_is_never_a_spawn():
    for how in ("came into view", "uncovered", "there at entry"):
        sp = spawns([pt(0, 1, 600, 500)])
        born(sp, rec(7, 600, 500, 0.2), how=how)
        assert sp.points[0].spawns == 0


def test_in_view_on_screen_and_not_covered():
    sp = spawns([pt(0, 1, 600, 500), pt(1, 1, 1300, 500)])
    sp.update(1.0, (400, 0), [], [], tags={"us": [(150, 440, 250, 520)]})      # the point at screen x 200: us over it
    assert [p.in_view for p in sp.points] == [False, True]                       # 1300 - 400 = 900: on screen, clear
    sp.update(1.1, (400, 0), [], [])
    assert [p.in_view for p in sp.points] == [True, True]
    sp.update(1.2, (0, 0), [], [], ui=[(500, 400, 700, 520)])
    assert [p.in_view for p in sp.points] == [False, True]
    sp.update(1.3, (1000, 0), [], [])                                            # 600 - 1000 < 0: off screen
    assert [p.in_view for p in sp.points] == [False, True]


def test_a_blind_frame_changes_nothing():
    sp = spawns([pt(0, 1, 600, 500)])
    sp.update(1.0, C, [], [])
    assert sp.points[0].in_view
    sp.update(1.0 + DT, None, [rec(7, 600, 500, 0.2)], [{"ev": "mob_new", "id": 7, "kind": 1, "how": "faded in"}])
    assert sp.points[0].in_view and sp.points[0].spawns == 0 and sp.first == {}


def test_the_mob_trackers_births_end_to_end():
    """The mob tracker's own records and events: a spawn fading in on its point (its opacity rising) -> that point's
    spawn, once; a faint mob with a flat opacity (born otherwise) is not a spawn."""
    for o_step, n_spawns in ((0.023, 1), (0.0, 0)):
        g = graph([pt(0, 1, 600, 500)])
        k = a_kind()
        trk, sp = MobTracker(g, {1: k}, Track()), Spawns(g, {1: k}, Track())
        trk.update(facts(0.0), ev(False, True))
        for f in range(40):
            t = 1.0 + f * DT
            e = trk.update(facts(t, [mob(600, o=0.3 + o_step * f, n=800)]), ev(False, True))
            sp.update(t, C, trk.records, e)
        assert sp.points[0].spawns == n_spawns, o_step
