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


# The tests of the other rules ask the body question on every frame and settle only at body_settled (step 4b try 3's
# sampling): rules A (body_every) and B (body_early_n) have their own tests, with the config as it is.
EVERY = dict(body_every=1, body_early_n=10 ** 6)


def tracker(cfg=None, **kw):
    g = Graph(mk([fh(1, 0, FLOOR, 1300, FLOOR)]), edges=False)
    return Players(g, cfg or Track(**EVERY), **kw)


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
    a, b = (400, 501, 60, 17), (480, 501, 50, 17)               # 20 px apart: alone (12 px: touching)
    bodies = [body(400, 60), body(480, 50)]
    t = run(trk, 10, 0.0, [a, b], bodies)
    ids = {m.w: m.id for m in trk.records}
    assert set(ids) == {60, 50}
    t = run(trk, 3, t, [(400, 501, 130, 17)], bodies)
    rec = {m.id: m for m in trk.records}
    assert rec[ids[60]].seen and rec[ids[50]].seen
    assert rec[ids[60]].x == 430 and rec[ids[50]].x == 505       # each by its own width: left edge / right edge
    assert sorted(round(b[1] + 24) for b in trk.drawn) == [430, 505]
    assert trk.tag_class == ["player"]
    assert all(tr.wc[130] == 0 and tr.w in (50, 60) for tr in trk.live)    # the shared box taught no width


def test_two_tags_joined_into_one_box_are_split_too():
    """Track 815 (step 4b try 3, measure 1): "GODxWAR" (69 px) and its pet "Snail" (38 px) 3 px apart are put
    together by the ladder-rail join (tag_join) into one 110 px box - a cut box no known track takes as its own: it is
    split by the widths known, and the pet's track does not take it (try 2: it did, and read the owner's body)."""
    trk = tracker()
    own, pet = (400, 501, 69, 17), (500, 501, 38, 17)
    bodies = [body(400, 69, 70), body(500, 38, 40)]
    t = run(trk, 10, 0.0, [own, pet], bodies)
    ids = {m.w: m.id for m in trk.records}
    assert set(ids) == {69} and trk.tag_class == ["player", "pet"]
    pid = next(tr.id for tr in trk.live if tr.w == 38)
    for k in range(1, 31):                                      # the pet walks up to its owner: 3 px apart, joined
        t += DT
        x = max(472, 500 - k)
        f, ev = frame(t, [own, (x, 501, 38, 17)], [body(400, 69, 70), body(x, 38, 40)])
        trk.update(f, ev)
    assert trk.stats["split"] > 0
    pet_tr = next(tr for tr in trk.live if tr.id == pid)
    assert pet_tr.w == 38 and pet_tr.cls_now == "pet" and pet_tr.n == trk.n
    assert set(pet_tr.wc) == {38} and pet_tr.hb1[55:].sum() == 0  # it learned nothing from the joined box
    assert {tr.id for tr in trk.live if tr.into is None} == {pid, ids[69]}


def test_a_known_track_never_takes_another_names_tag():
    """Step 4b try 3 (10 of the 13 labelled pets called players): an owner's track (82 px) whose tag is hidden does not
    take its pet's tag (66 px) next to it as a piece of its own - the pet's tag is the pet's (a new track); the owner's
    track is kept unseen (the 2 s cover) and takes its own tag back."""
    trk = tracker()
    own = (400, 501, 82, 17)
    t = run(trk, 10, 0.0, [own], [body(400, 82, 70)])
    oid = trk.records[0].id
    pet = (410, 501, 66, 17)                                    # inside the owner's span: try 2 took it "by an edge"
    t = run(trk, 10, t, [pet], [body(410, 66, 40)])
    owner = next(tr for tr in trk.live if tr.id == oid)
    assert owner.n != trk.n and owner.wc[66] == 0 and owner.hb1[:50].sum() == 0
    assert trk.tag_track[0] != oid
    run(trk, 1, t, [own], [body(400, 82, 70)])
    assert trk.tag_track == [oid] and trk.tag_class == ["player"]


def test_crowded_sightings_teach_nothing():
    """Design 1 (the user, 2026-11-26): "clean sightings teach, crowded ones only follow". A pet whose tag touches its
    owner's (within alone_gap) and whose body column reads the owner standing over it is never taught "player": its
    crowded sightings follow it; its alone ones (40 px) make it a pet. Try 2 counted every whole sighting."""
    trk = tracker()
    own, pet = (400, 501, 82, 17), (491, 501, 38, 17)          # 9 px apart: touching (6: one box, joined)
    tall = [body(400, 82, 70), (491, 431, 529, 501)]            # the owner over the pet's column: reads 70
    t = run(trk, 20, 0.0, [own, pet], tall)
    pet_tr = next(tr for tr in trk.live if tr.x > 491)
    assert pet_tr.hb1.sum() == 0 and pet_tr.cls_now != "player"
    t = run(trk, 6, t, [own, (504, 501, 38, 17)], [body(400, 82, 70), body(504, 38, 40)])   # apart: alone, 40 px
    assert trk.tag_class == ["player", "pet"]
    t = run(trk, 20, t, [own, pet], tall)                       # crowded again: it stays a pet
    assert trk.tag_class[1] == "pet"


def test_a_settled_track_is_not_asked_the_body_question():
    """Step 4b try 3 (the ms): a pet / player track with body_settled alone body readings is not asked again; a new
    tag is."""
    c = Track(**EVERY)
    trk = tracker()
    t = run(trk, c.body_settled + 5, 0.0, [(400, 501, 60, 17)], [body(400, 60)])
    asked = trk.stats["body asked"]
    assert trk.live[0].settled(c) and asked == c.body_settled
    t = run(trk, 10, t, [(400, 501, 60, 17)], [body(400, 60)])
    assert trk.stats["body asked"] == asked and trk.tag_class == ["player"]
    run(trk, 1, t, [(400, 501, 60, 17), (800, 501, 50, 17)], [body(400, 60), body(800, 50)])
    assert trk.stats["body asked"] == asked + 1


def test_an_unsettled_tracks_tag_is_asked_every_4th_frame():
    """Step 4b try 4 (the user's answer 4 A): an unsettled track's tag is asked the body question every body_every-th
    frame; a tag no track would take (a new one) is asked on the frame it is first seen. The class comes on the 5th
    alone reading: frame 1 + 4 x body_every."""
    c = Track()
    trk = tracker(c)
    tag, b = (400, 501, 60, 17), body(400, 60, 55)              # 55 px: near the line, not settled early
    t = run(trk, 10, 0.0, [tag], [b])
    assert trk.stats["body asked"] == 3 and trk.stats["body every"] == 7     # frames 1, 5, 9
    t = run(trk, 1, t, [tag, (800, 501, 50, 17)], [b, body(800, 50)])       # frame 11: the new one is asked
    assert trk.stats["body asked"] == 4
    t = run(trk, 1 + 4 * c.body_every - 12, t, [tag], [b])                 # up to frame 16: 4 alone readings
    assert trk.tag_class == ["unsure"]
    run(trk, 1, t, [tag], [b])                                               # frame 17: the 5th
    assert trk.tag_class == ["player"] and int(trk.live[0].hb1.sum()) == 5


def test_what_stands_on_a_tag_counts_only_on_the_frames_it_was_asked():
    """Step 4b try 4: the body and D's blob over a tag count in its class only on the frames the body question was
    asked, so asking every 4th frame does not tilt the vote: a player whose blob reads 0 on the frames between (it
    stepped aside) is not text."""
    c = Track()
    trk = tracker(c)
    tag = (400, 501, 60, 17)
    t = 0.0
    for k in range(40):
        t += DT
        f, ev = frame(t, [tag], [body(400, 60, 55)] if k % c.body_every == 0 else [])
        trk.update(f, ev)
    assert trk.tag_class == ["player"] and trk.live[0].ev["b0"] == 0


def test_a_clear_class_settles_early():
    """Step 4b try 4 (the user's answer 4 B): a pet / player whose 75th percentile is body_early_dist px or more from
    pet_line (<= 40 or >= 60 px) settles from body_early_n alone readings; near the line it needs body_settled."""
    c = Track(body_every=1)
    for tall, settle in ((70, c.body_early_n), (40, c.body_early_n), (55, c.body_settled)):
        trk = tracker(c)
        run(trk, c.body_settled + 10, 0.0, [(400, 501, 60, 17)], [body(400, 60, tall)])
        assert trk.stats["body asked"] == settle, tall
        assert trk.tag_class == ["player" if tall > c.pet_line else "pet"]


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
