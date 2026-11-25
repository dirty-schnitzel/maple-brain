"""maplebrain/track/players.py (PLAN-tracker step 4b): the tag list sorted (ours, log lines, mobs' own tags, text, pets,
players), players followed by the tag's width, two tags side by side split by the widths known, the 2 s cover, the
placement; the evidence's `columns` (the body over a tag) from the bitmaps and the GPU alike. Its numbers on recorded
footage: tools/perc/track/replay_players.py (the port against proto_players.py, L5, the cover, us)."""
from types import SimpleNamespace

import numpy as np
import pytest

from maplebrain.config import Track
from maplebrain.track.evidence import PLAY_H, SW, Bitmaps
from maplebrain.track.graph import Graph
from maplebrain.track.players import Players, col_body, sorted_boxes
from test_track_graph import fh, mk

DT = 1 / 60
FLOOR = 500                                     # the floor's y (map = screen: camera (0, 0)); a tag's top = 501


def tracker(**kw):
    g = Graph(mk([fh(1, 0, FLOOR, 1300, FLOOR)]), edges=False)
    return Players(g, Track(), **kw)


def frame(t, tags=(), bodies=(), fit=None, C=(0, 0), patches="bodies"):
    """tags: [(x, y, w, h)]; bodies: [(x0, y0, x1, y1)] drawn over the scene (they do not show it)."""
    shows = np.ones((PLAY_H, SW), bool)
    for x0, y0, x1, y1 in bodies:
        shows[y0:y1, x0:x1] = False
    pt = [(x0, y0, x1 - x0, y1 - y0, (x1 - x0) * (y1 - y0)) for x0, y0, x1, y1 in bodies] if patches == "bodies" \
        else patches
    f = SimpleNamespace(t=t, scene_cam=C, tags=list(tags), fit=fit, patches=pt, tag=None)
    return f, Bitmaps(shows, np.ones((PLAY_H, SW), bool))


def body(x, w, tall=70, top=501):
    """A body standing on a tag at x, width w: `tall` px over its top, 30 px wide around its centre."""
    cx = x + w // 2
    return (cx - 15, top - tall, cx + 15, top)


def run(trk, n, t0, tags, bodies=(), **kw):
    t = t0
    for _ in range(n):
        t += DT
        f, ev = frame(t, tags, bodies, **kw)
        trk.update(f, ev)
    return t


def test_a_player_by_its_tall_body_a_pet_by_its_short_one():
    trk = tracker()
    tags = [(400, 501, 60, 17), (700, 501, 38, 17)]
    events = []
    t = 0.0
    for _ in range(8):
        t += DT
        f, ev = frame(t, tags, [body(400, 60, 70), body(700, 38, 40)])
        events += trk.update(f, ev)
    assert trk.tag_class == ["player", "pet"]
    assert [m.w for m in trk.records] == [60]                    # pets are sorted out, not tracked
    p = trk.records[0]
    assert p.place == "stand" and p.node == 1 and p.x == 430 and p.y == FLOOR and p.seen
    assert [e["ev"] for e in events] == ["player_new"]
    assert [b[0] for b in trk.drawn] == ["player", "pet"]


def test_pet_or_player_by_the_upper_quartile_of_its_heights():
    """Step 4b try 2 (the user's answer 3): a track's class by the 75th percentile of its body heights over the stay
    against pet_line (50 px), not by a vote of sightings: a player whose attack stance reads 15 px between its legs on
    two thirds of its sightings stays a player (the prototype's vote: a pet); a pet that reads tall on a quarter (its
    owner over it) stays a pet; a pet a little larger than today's (46 px) is still a pet."""
    def run_heights(heights):
        trk = tracker()
        t = 0.0
        for k, b in enumerate(heights):
            t += DT
            f, ev = frame(t, [(400, 501, 60, 17)], [body(400, 60, b)])
            trk.update(f, ev)
        return trk.tag_class[0]
    assert run_heights([68, 15, 15] * 6) == "player"          # the prototype's per-sighting vote: pet (12 of 18)
    assert run_heights([40, 40, 40, 70] * 5) == "pet"
    assert run_heights([46] * 10) == "pet"
    assert run_heights([57] * 10) == "player"


def test_feet_from_the_top_or_a_medal_tags_bottom():
    """The user, 2026-11-26: feet = the tag's top - 1; a 21 px tag (a medal grows the box UP): its bottom - 18."""
    for h, top in ((17, 501), (19, 501), (21, 497)):               # every box's feet on the floor (y 500)
        trk = tracker()
        run(trk, 8, 0.0, [(400, top, 60, h)], [body(400, 60, 70, top)])
        p = trk.records[0]
        assert p.y == FLOOR and p.place == "stand" and p.node == 1, (h, p.y, p.place)


def test_when_the_class_is_known():
    trk = tracker()
    t = run(trk, 5, 0.0, [(400, 501, 60, 17)], [body(400, 60)])
    assert trk.live[0].known_n is None
    run(trk, 1, t, [(400, 501, 60, 17)], [body(400, 60)])
    assert trk.live[0].known_n == 6 and trk.tag_class == ["player"]


def test_short_until_seen_six_times():
    trk = tracker()
    run(trk, 5, 0.0, [(400, 501, 60, 17)], [body(400, 60)])
    assert trk.tag_class == ["short"] and trk.records == []


def test_text_with_nothing_standing_on_it():
    trk = tracker()
    run(trk, 8, 0.0, [(400, 501, 60, 17)], (), patches=[])
    assert trk.tag_class == ["text"]


def test_a_line_of_the_message_log():
    trk = tracker()
    f, ev = frame(DT, [(1290, 589, 75, 14)], ())                # row 0's top 588-590, right edge 1365
    trk.update(f, ev)
    assert trk.tag_class == ["log"] and trk.live == []


def test_a_mobs_own_tag_under_its_feet():
    """The kind's own tag box is learned while running (after mob_tag_n sightings); from then on the tag's sightings
    vote "mob" (the ones before it did not: the vote turns when they are half)."""
    trk = tracker()
    fit = [{"type": 7, "feet": [500, 480], "pose": "move_0", "facing": "left", "opacity": 1.0, "n_seen": 500}]
    tags = [(457, 481, 87, 20)]
    t = run(trk, 19, 0.0, tags, [body(457, 87, 40)], fit=fit)
    assert 7 not in trk.mob_tags and trk.tag_class == ["pet"]
    t = run(trk, 1, t, tags, [body(457, 87, 40)], fit=fit)
    assert trk.mob_tags[7] == (87, 20, 0.5, 1)                  # learned: w, h, centre x - feet x, top y - feet y
    t = run(trk, 17, t, tags, [body(457, 87, 40)], fit=fit)    # 19 without, 18 with the box
    assert trk.tag_class == ["pet"]
    t = run(trk, 1, t, tags, [body(457, 87, 40)], fit=fit)     # 19 with: half
    assert trk.tag_class == ["mob"] and trk.records == [] and trk.drawn == []
    trk2 = tracker(mob_tags={7: (87, 20, 0.5, 1)})              # known from the start: mob at once
    run(trk2, 6, 0.0, tags, [body(457, 87, 40)], fit=fit)
    assert trk2.tag_class == ["mob"]


def test_two_tags_side_by_side_are_split_by_the_widths_known():
    """A (60 px) and B (50 px) known apart, then the finder joins them into one box: both stay seen, each placed
    by its own width at the edge that kept its place, both drawn for the mob tracker's covers."""
    trk = tracker()
    a, b = (400, 501, 60, 17), (470, 501, 50, 17)               # 10 px apart: two tags (6 px: one, cut)
    bodies = [body(400, 60), body(470, 50)]
    t = run(trk, 10, 0.0, [a, b], bodies)
    ids = {m.w: m.id for m in trk.records}
    assert set(ids) == {60, 50}
    t = run(trk, 3, t, [(400, 501, 120, 17)], bodies)
    rec = {m.id: m for m in trk.records}
    assert rec[ids[60]].seen and rec[ids[50]].seen
    assert rec[ids[60]].x == 430 and rec[ids[50]].x == 495       # each by its own width: left edge / right edge
    assert sorted(round(b[1] + 24) for b in trk.drawn) == [430, 495]
    assert trk.tag_class == ["player"]


def test_kept_two_seconds_in_view_then_left():
    trk = tracker()
    t = run(trk, 10, 0.0, [(400, 501, 60, 17)], [body(400, 60)])
    pid = trk.records[0].id
    ev = []
    for _ in range(int(1.9 / DT)):
        t += DT
        f, e = frame(t, [], [])
        ev += trk.update(f, e)
    assert [m.id for m in trk.records] == [pid] and trk.records[0].cover == "unseen" and ev == []
    for _ in range(int(0.2 / DT)):
        t += DT
        f, e = frame(t, [], [])
        ev += trk.update(f, e)
    assert trk.records == [] and [(x["ev"], x["how"]) for x in ev] == [("player_left", "lost")]
    t = run(trk, 1, t, [(400, 501, 60, 17)], [body(400, 60)])
    assert trk.tag_class == ["short"]                           # back after 2 s: a new id


def test_out_of_view_ends_at_once():
    trk = tracker()
    t = run(trk, 10, 0.0, [(400, 501, 60, 17)], [body(400, 60)])
    f, e = frame(t + DT, [], [], C=(420, 0))                    # the camera moved: its place is past the screen's edge
    ev = trk.update(f, e)
    assert trk.records == [] and ev[0]["how"] == "edge:screen"


def test_ours_and_what_sticks_out_of_it():
    """Our tag merged with a neighbour's in the list: the box is ours, the part sticking out never starts a track."""
    trk = tracker()
    ours = (400, 501, 74, 17, None)
    for k in range(8):
        f, ev = frame((k + 1) * DT, [(400, 501, 111, 21)], [body(400, 74)])
        trk.update(f, ev, ours=ours)
    assert trk.tag_class == ["ours"] and trk.live == [] and trk.records == []
    trk2 = tracker()                                            # ours taken from the list by track/us.py: that one
    f, ev = frame(DT, [(400, 501, 74, 17), (600, 501, 60, 17)], [])
    trk2.update(f, ev, ours=(400, 501, 74, 17, 0))
    assert trk2.tag_class == ["ours", "short"]


def test_a_blind_frame_changes_nothing():
    trk = tracker()
    t = run(trk, 10, 0.0, [(400, 501, 60, 17)], [body(400, 60)])
    f, ev = frame(t + 5.0, [], [], C=None)
    assert trk.update(f, ev) == []
    assert len(trk.records) == 1 and trk.records[0].cover == "blind" and trk.records[0].x == 430


def test_sorted_boxes():
    c = Track()
    b = sorted_boxes((400, 300, 74, 17, None), [("player", 1, 2, 3, 4), ("pet", 5, 6, 7, 8)], c)
    assert b["us"] == [(437 + c.us_box[0], 300 + c.us_box[1], 437 + c.us_box[2], 300 + c.us_box[3])]
    assert b["player"] == [(1, 2, 3, 4), (5, 6, 7, 8)]


def test_col_body_reads_the_height_over_the_tag():
    c = Track()
    f, ev = frame(0, [], [(380, 431, 420, 501), (600, 461, 640, 501), (800, 401, 840, 451), (800, 445, 840, 501)])
    cx, top = np.array([400, 620, 820]), np.array([501, 501, 501])
    over, world, inside = ev.columns(cx, top, c.body_reach, c.body_half)
    got = [col_body(over[k], world[k], inside[k], 501, c) for k in range(3)]
    assert got == [70, 40, 100]                                  # a gap of 6 rows is bridged (<= 8)
    over, world, inside = ev.columns(np.array([400]), np.array([740]), c.body_reach, c.body_half)
    assert col_body(over[0], world[0], inside[0], 740, c) == -1  # the tag under the play area


def test_gpu_columns_equal_the_bitmaps():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("no CUDA")
    from maplebrain.track.evidence import Gpu
    rng = np.random.default_rng(4)
    frame_ = rng.integers(0, 256, (PLAY_H, SW, 3), dtype=np.uint8)
    exp = frame_.astype(np.float32) + rng.choice([0.0, 3.0, 9.0], (PLAY_H, SW, 1)).astype(np.float32)
    valid = rng.random((PLAY_H, SW)) < 0.8
    dev = "cuda"
    fz = SimpleNamespace(torch=torch, dev=dev, _last=(torch.from_numpy(frame_).to(dev), (0, 0),
                                                      torch.from_numpy(exp).to(dev), torch.from_numpy(valid).to(dev)))
    shows = valid & (np.abs(frame_.astype(np.float32) - exp).max(2) <= 4.0)
    cpu, gpu = Bitmaps(shows, valid), Gpu(fz, 4.0)
    cx, top = rng.integers(-20, SW + 20, 30), rng.integers(-10, PLAY_H + 80, 30)
    a = cpu.columns(cx, top, 120, 8)
    b = gpu.columns(cx, top, 120, 8)                             # the pixels alone (no shows map this frame)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
    gpu.count([(cx, top, np.array([0]), np.array([0]))])         # the frame's shows map made: read from it
    b = gpu.columns(cx, top, 120, 8)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
    # step 4b try 2 (the user's answer 6): asked, then the mob tracker's count -> ONE transfer carries both
    gpu.trips = 0
    ans = gpu.ask_columns(cx, top, 120, 8)
    groups = [(cx, top, np.array([0, 1]), np.array([0, -1]))]
    got = gpu.count(groups)
    assert gpu.trips == 1 and all(np.array_equal(x, y) for x, y in zip(a, ans.get())) and gpu.trips == 1
    assert all(np.array_equal(x, y) for x, y in zip(cpu.count(groups)[0], got[0]))
    gpu.trips = 0
    assert all(np.array_equal(x, y) for x, y in zip(a, gpu.ask_columns(cx, top, 120, 8).get())) and gpu.trips == 1
