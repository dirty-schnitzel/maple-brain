"""maplebrain/track/mobs.py, kinds.py, evidence.py (PLAN-tracker.md step 3): the mob tracker's rules on synthetic
frames - memory by evidence (kept while something is drawn over it, gone at once when its places show the scene, the
4 s limits), the tentative stage, look-alike feet, deaths, blind frames - and the GPU evidence against the bitmaps.
Its numbers on recorded footage: tools/perc/track/replay_mobs.py (PLAN-tracker step 3's gate)."""
from types import SimpleNamespace

import numpy as np
import pytest

from maplebrain.config import Track
from maplebrain.track.evidence import PLAY_H, SW, Bitmaps
from maplebrain.track.graph import Graph
from maplebrain.track.kinds import Kind, kind
from maplebrain.track.mobs import MobTracker
from test_track_graph import fh, mk

DT = 1 / 60


def a_kind(jump=False, alike=None, mob_id=1) -> Kind:
    """A 40 x 40 body over the feet; its core a 20 x 30 block (every pixel)."""
    ys, xs = np.mgrid[-35:-5, -10:10]
    return Kind(mob_id, False, jump, 50.0, 100.0, 250.0, 0.6, (-20, -40), (20, 0), 20.0, 1000.0, ys.size,
                xs.ravel().astype(np.int64), ys.ravel().astype(np.int64), alike or {})


def a_tracker(**kw):
    g = Graph(mk([fh(1, 0, 500, 1300, 500), fh(2, 0, 300, 600, 300)]), edges=False)
    k = kw.pop("kinds", None) or {1: a_kind(**kw)}
    return MobTracker(g, k, Track(), keep=True)


def facts(t, sights=(), C=(0, 0)):
    return SimpleNamespace(t=t, scene_cam=C, tags=[], drops=[], tag=None,
                           fit=[{"type": k, "feet": [x, y], "pose": p, "facing": "left", "opacity": o, "n_seen": n}
                                for k, x, y, p, o, n in sights])


def ev(shows: bool, world: bool):
    return Bitmaps(np.full((PLAY_H, SW), shows), np.full((PLAY_H, SW), world))


def mob(x, y=500, pose="move_0", o=1.0, n=800, k=1):
    return (k, x, y, pose, o, n)


def run_unseen(trk, t0, seconds, shows, world):
    """Frames with no sighting from t0 for `seconds` -> (the events, the last t)."""
    out, t = [], t0
    while t < t0 + seconds:
        t += DT
        out += trk.update(facts(t), ev(shows, world))
    return out, t


def test_covered_mob_keeps_its_id():
    trk = a_tracker()
    e = trk.update(facts(0.0, [mob(600)]), ev(False, True))
    assert [x["ev"] for x in e] == ["mob_new"]
    tid = trk.mobs()[0].id
    evs, t = run_unseen(trk, 0.0, 1.0, shows=False, world=True)     # something drawn over every place
    assert evs == []
    m = trk.mobs()[0]
    assert not m.seen and m.cover == "effect" and m.state == "hidden" and m.can_lo <= 600 <= m.can_hi
    trk.update(facts(t + DT, [mob(630)]), ev(False, True))
    m = trk.mobs()[0]
    assert m.id == tid and m.seen and m.x_seen == 630


def test_gone_at_once_when_its_places_show_the_scene():
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    e = trk.update(facts(DT, []), ev(True, True))
    assert [x["ev"] for x in e] == ["mob_gone"] and e[0]["how"] == "gone: its places show the scene"
    assert trk.mobs() == []


def test_nothing_to_check_kept_4_s_then_left():
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    evs, t = run_unseen(trk, 0.0, 3.9, shows=False, world=False)
    assert evs == [] and trk.mobs()[0].cover == "ui / scenery" and trk.mobs()[0].state == "offscreen"
    evs, _ = run_unseen(trk, t, 0.3, shows=False, world=False)
    assert [x["ev"] for x in evs] == ["mob_left"]


def test_drawn_over_kept_4_s_since_last_seen():
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    evs, t = run_unseen(trk, 0.0, 3.95, shows=False, world=True)
    assert evs == []
    evs, _ = run_unseen(trk, t, 0.2, shows=False, world=True)
    assert [x["ev"] for x in evs] == ["mob_gone"] and evs[0]["how"].startswith("gone: drawn over")


def test_a_faint_sighting_is_tentative_and_dropped_without_a_trace():
    trk = a_tracker()
    assert trk.update(facts(0.0, [mob(600, n=50)]), ev(False, True)) == []       # 5 % of its full size
    assert trk.mobs() == [] and len(trk.records) == 1 and not trk.records[0].confirmed
    evs, _ = run_unseen(trk, 0.0, 0.4, shows=False, world=True)
    assert evs == [] and trk.records == []


def test_faint_sightings_for_half_a_second_confirm():
    trk = a_tracker()
    evs, t = [], 0.0
    while t < 0.55:
        evs += trk.update(facts(t, [mob(600 + 60 * t, n=50)]), ev(False, True))
        t += DT
    assert [x["ev"] for x in evs] == ["mob_new"] and len(trk.mobs()) == 1


def test_far_from_its_set_is_another_mob():
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    _, t = run_unseen(trk, 0.0, 0.2, shows=False, world=True)
    trk.update(facts(t + DT, [mob(1000)]), ev(False, True))
    ids = sorted(m.id for m in trk.records)
    assert len(ids) == 2                                            # the old one remembered, a new one seen


def test_look_alike_pose_takes_the_reading_on_the_surface():
    """The fit names a jump pose 17 px over the floor; the same picture as `move_0` stands on it."""
    trk = a_tracker(jump=True, alike={("jump_0", "left"): [("move_0", 0, 17)]})
    trk.update(facts(0.0, [mob(600, y=483, pose="jump_0")]), ev(False, True))
    m = trk.records[0]
    assert (m.y, m.pose, m.place, m.node) == (500, "move_0", "stand", 1)


def test_a_jump_passing_a_level_is_in_the_air():
    trk = a_tracker(jump=True)
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    trk.update(facts(DT, [mob(600, y=490)]), ev(False, True))
    m = trk.records[0]
    assert m.place == "air" and m.from_node == 1
    trk.update(facts(2 * DT, [mob(600, y=300)]), ev(False, True))   # far up: not the same mob in one frame
    assert len(trk.records) == 2


def test_death_seen_then_gone_when_die1_ends():
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    trk.update(facts(DT, [mob(600, pose="die1_0")]), ev(False, True))
    assert trk.mobs()[0].life == "dying" and trk.mobs()[0].state == "dying"
    evs, _ = run_unseen(trk, DT, 0.6, shows=True, world=True)       # the die animation (0.6 s) + 0.1
    assert evs == []
    evs, _ = run_unseen(trk, DT + 0.6, 0.2, shows=True, world=True)
    assert [x["ev"] for x in evs] == ["mob_died"]


def test_a_live_pose_right_after_one_die_pose_takes_it_back():
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    trk.update(facts(DT, [mob(600, pose="die1_0")]), ev(False, True))
    trk.update(facts(2 * DT, [mob(601)]), ev(False, True))
    assert trk.mobs()[0].life == "alive" and trk.stats["death taken back"] == 1


def test_blind_frame_changes_nothing():
    """No camera: nothing begins or ends, every value is kept - but nothing is found on it: not `seen`."""
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    before = trk.mobs()[0]
    assert before.seen
    assert trk.update(facts(DT, [mob(900)], C=None), ev(True, True)) == []
    m = trk.mobs()[0]
    assert (m.id, m.x, m.state, m.seen, m.cover) == (before.id, before.x, before.state, False, "blind")
    trk.update(facts(2 * DT, [mob(601)]), ev(False, True))           # the camera back: the same mob, seen
    assert trk.mobs()[0].id == before.id and trk.mobs()[0].seen


def test_what_covers_it_is_named_by_the_boxes():
    trk = a_tracker()
    trk.update(facts(0.0, [mob(600)]), ev(False, True))
    f = facts(DT)
    f.tag = (580, 520, 40, 14, 0.9)                                  # our tag under the mob: our body over it
    trk.update(f, ev(False, True))
    assert trk.mobs()[0].cover == "us"


def test_the_edge_wins_over_what_covers_the_in_view_part():
    """The user, 2026-11-24 (L2): a remembered mob whose body box at its place crosses the screen's edge is covered
    by the `edge`, whatever is drawn over its in-view part; its memory is that of a mob drawn over (kept 4 s since
    last seen, `hidden`) - only the name changes. In plain view the cover stays what is drawn over it."""
    g = Graph(mk([fh(1, -400, 500, 1800, 500)]), edges=False)
    for x, want in ((10, "edge"), (1356, "edge"), (600, "effect")):
        trk = MobTracker(g, {1: a_kind()}, Track(), keep=True)
        trk.update(facts(0.0, [mob(x)]), ev(False, True))
        evs, t = run_unseen(trk, 0.0, 0.5, shows=False, world=True)
        m = trk.mobs()[0]
        assert evs == [] and (m.cover, m.state) == (want, "hidden"), (x, m.cover, m.state)
        evs, _ = run_unseen(trk, t, 3.6, shows=False, world=True)
        assert [e["ev"] for e in evs] == ["mob_gone"] and evs[0]["how"].startswith("gone: drawn over")


def test_how_it_came_into_sight_and_its_first_pose_are_two_fields():
    """The user, 2026-11-24 (L3): a mob first seen in its die pose is born by how it came into sight (uncovered,
    came into view or there at entry), with the die pose as its first pose - not born "dying", and not "faded in"
    (its die animation fades it out: L3 case 45)."""
    trk = a_tracker()
    trk.update(facts(0.0), ev(False, True))                          # the stay's first camera
    trk.update(facts(1.0, [mob(600, pose="die1_0"), mob(30, pose="die1_2")]), ev(False, True))
    by_x = {round(m.x): m for m in trk.records}
    assert (by_x[600].born_how, by_x[600].first_pose, by_x[600].life) == ("uncovered", "die1_0", "dying")
    assert (by_x[30].born_how, by_x[30].first_pose) == ("came into view", "die1_2")
    trk.update(facts(1.0 + DT, [mob(600, pose="die1_1")]), ev(False, True))
    assert [m.first_pose for m in trk.records if round(m.x) == 600] == ["die1_0"]
    trk = a_tracker()
    trk.update(facts(0.0), ev(False, True))
    trk.update(facts(1.0, [mob(900, pose="die1_3", o=0.5), mob(300, o=0.5)]), ev(False, True))
    by_x = {round(m.x): m.born_how for m in trk.records}
    assert by_x == {900: "uncovered", 300: "faded in"}               # a death fades the body OUT; a faint live pose
                                                                    # is a spawn fading in


def test_kind_from_poses_core_and_look_alikes():
    from maplebrain.perception.vote import Pose
    pic = np.zeros((40, 30, 4), np.uint8)
    pic[5:40, 5:25, 3] = 255
    poses = [Pose(7, "stand_0", "left", 15, 40, pic), Pose(7, "move_0", "left", 15, 40, pic),
             Pose(7, "jump_0", "left", 15, 23, pic)]
    info = {"frames": {"stand": [{"lt": [-15, -40], "rb": [15, 0]}], "jump": [{}], "die1": [{"delay": 120}] * 5},
            "info": {"speed": -20}}
    k = kind(7, info, poses, 2.0, 125.0)
    assert k.jump and not k.fly and k.v_file == 50.0 and k.v == 100.0 and k.vb == 250.0 and k.die_s == 0.6
    assert k.full == 700 and k.half_w == 15
    assert ("jump_0", "left") in k.alike and ("stand_0", 0, 17) in k.alike[("jump_0", "left")]
    assert k.cdy.max() < 0                                           # the core lies over the feet


def test_gpu_evidence_equals_the_bitmaps():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("no CUDA")
    from maplebrain.track.evidence import Gpu
    rng = np.random.default_rng(3)
    frame = rng.integers(0, 256, (PLAY_H, SW, 3), dtype=np.uint8)
    exp = frame.astype(np.float32) + rng.choice([0.0, 3.0, 9.0], (PLAY_H, SW, 1)).astype(np.float32)
    valid = rng.random((PLAY_H, SW)) < 0.8
    dev = "cuda"
    fz = SimpleNamespace(torch=torch, dev=dev, _last=(torch.from_numpy(frame).to(dev), (0, 0),
                                                      torch.from_numpy(exp).to(dev), torch.from_numpy(valid).to(dev)))
    shows = valid & (np.abs(frame.astype(np.float32) - exp).max(2) <= 4.0)
    cpu, gpu = Bitmaps(shows, valid), Gpu(fz, 4.0)
    ks = [a_kind(), a_kind(mob_id=2)]
    ks[1].cdx, ks[1].cdy = ks[1].cdx[::3].copy(), ks[1].cdy[::3].copy()
    groups = [(rng.integers(-60, SW + 60, 200), rng.integers(-60, PLAY_H + 60, 200), k.cdx, k.cdy) for k in ks]
    for (a1, b1, c1), (a2, b2, c2) in zip(cpu.count(groups), gpu.count(groups)):
        assert np.array_equal(a1, a2) and np.array_equal(b1, b2) and np.array_equal(c1, c2)
    assert gpu.asked == 400
