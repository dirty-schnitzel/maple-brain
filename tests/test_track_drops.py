"""maplebrain/track/drops.py (PLAN-tracker.md step 4a): the drop tracker's rules on synthetic frames - birth from a
resting sighting and the 0.25 s confirmation, the bob, gone by the hop / by the place shown empty / at 130 s, "we
took it" by the pickup key's STATE (held through the window counts, not only a press in it), from_mob by the death
before it, blind frames - and the look against the prototype's own counting. Its numbers on recorded footage:
tools/perc/track/replay_drops.py (PLAN-tracker step 4a's gate)."""
import math
from types import SimpleNamespace

import numpy as np

from maplebrain.config import Track
from maplebrain.track.drops import DropTracker, Fronts, Pictures
from maplebrain.track.evidence import PLAY_H, SW, Bitmaps

DT = 1 / 60
YF = 500                                            # the foothold's y; the camera is (0, 0): screen = map


def pics():
    return Pictures({4000000: [(0, np.ones((12, 10), bool))],
                     9000000: [(0, np.ones((8, 8), bool)), (1, np.ones((8, 4), bool))]},
                    {"4000000": {"name": "Snail Shell", "kind": "Etc"}})


def tracker(**kw):
    return DropTracker(pics(), kw.pop("fronts", None), None, "z", Track(), keep=True)


def sight(x, y, item=4000000, kind="rest", yf=YF):
    return {"item": item, "f": 0, "feet": [x, y], "kind": kind, "dy": y - yf, "fh": 7, "layer": 0, "seen": 120,
            "n_op": 120, "under": 0, "front": 0}


def facts(t, sights=(), C=(0, 0)):
    return SimpleNamespace(t=t, scene_cam=C, drops=list(sights))


def ev(shows: bool, world: bool):
    return Bitmaps(np.full((PLAY_H, SW), shows), np.full((PLAY_H, SW), world))


COVERED = ev(False, True)                           # something drawn over every place
EMPTY = ev(True, True)                              # the scenery shows everywhere


def bob(t, t0=0.0):
    return YF + round(2.5 - 2.5 * math.cos(2 * math.pi * (t - t0) / 2.0))


def lie(trk, x, t0, t1, me=None, keys_at=None, item=4000000):
    """Sightings of one drop at x from t0 to t1 (its bob) -> the events, the last t."""
    out, t = [], t0
    while t < t1 - 1e-9:
        out += trk.update(facts(t, [sight(x, bob(t), item)]), COVERED, me=me,
                          keys=(keys_at(t) if keys_at else ()))
        t += DT
    return out, t - DT


def unseen(trk, t0, seconds, evidence, me=None, keys=()):
    out, t = [], t0
    while t < t0 + seconds:
        t += DT
        out += trk.update(facts(t), evidence, me=me, keys=keys)
        keys = ()
    return out, t


def test_born_from_a_resting_sighting_and_confirmed_after_025_s():
    trk = tracker()
    e, t = lie(trk, 600, 0.0, 0.2)
    assert e == [] and len(trk.records) == 1 and not trk.records[0].confirmed and trk.drops() == []
    e = trk.update(facts(0.26, [sight(600, bob(0.26))]), COVERED)
    assert [x["ev"] for x in e] == ["drop_new"] and e[0]["born_t"] == 0.0
    d = trk.drops()[0]
    assert (d.x, d.y, d.item, d.cls, d.seen, d.cover) == (600, YF, 4000000, "etc", True, "none")


def test_a_tentative_drop_unsighted_01_s_is_forgotten_and_a_weak_sighting_starts_none():
    trk = tracker()
    lie(trk, 600, 0.0, 0.1)
    e, t = unseen(trk, 0.1, 0.15, COVERED)
    assert e == [] and trk.records == [] and trk.stats["tentative dropped"] == 1
    trk.update(facts(t + DT, [sight(700, YF, kind="weak")]), COVERED)
    assert trk.records == []


def test_two_of_one_item_at_one_x_are_two_drops():
    trk = tracker()
    t = 0.0
    while t < 0.4:
        trk.update(facts(t, [sight(600, YF), sight(600, YF + 5)]), COVERED)
        t += DT
    ds = trk.drops()
    assert len(ds) == 2 and len({d.id for d in ds}) == 2
    assert all(x.twin for lst in trk.live.values() for x in lst)


def test_the_bob_keeps_a_drop_its_own():
    """Sightings on its bob for 3 s: one drop, its fit trusted, a sighting off the bob by 3 px is not it."""
    trk = tracker()
    _, t = lie(trk, 600, 0.0, 3.0)
    d = next(x for lst in trk.live.values() for x in lst)
    e = d.expect(t + DT, trk.cfg)
    assert e is not None and abs(e - bob(t + DT)) <= 0.5
    off = bob(t + DT) + 3 if bob(t + DT) + 3 <= YF + 6 else bob(t + DT) - 3
    assert trk._fits(d, t + DT, off) is None and trk._fits(d, t + DT, bob(t + DT)) is not None


def hop(trk, x, t, y0, me=None, keys=()):
    """The pickup hop: the item 6 px higher every game frame (no drop takes those sightings) -> events, last t."""
    out, y = [], y0
    for _ in range(4):
        t += DT
        y -= 6
        out += trk.update(facts(t, [sight(x, y, kind="weak")]), COVERED, me=me, keys=keys)
        keys = ()
    return out, t


def test_the_hop_with_the_key_pressed_and_us_in_reach_is_we_took_it():
    trk = tracker()
    me = (604.0, YF + 1.0)
    _, t = lie(trk, 600, 0.0, 1.0, me=me)
    e, t = hop(trk, 600, t, bob(t), me=me, keys=[(t + 0.001, "z", True), (t + 0.08, "z", False)])
    assert [x["ev"] for x in e] == ["drop_gone"] and e[0]["how"] == "we took it"
    assert trk.drops() == []


def test_the_key_held_through_the_window_is_we_took_it():
    """The user (step 4a): "we took it" reads the pickup key's STATE - held down since 2 s before the hop (no press
    in the last 0.75 s: the prototype's rule said "gone in view")."""
    trk = tracker()
    me = (600.0, YF + 1.0)
    held = [(-1.0 + 0.001, "z", True)]
    _, t = lie(trk, 600, 0.0, 1.0, me=me, keys_at=lambda t: held if t == 0.0 else ())
    assert trk.down and trk.presses == [held[0][0]]
    e, t = hop(trk, 600, t, bob(t), me=me)
    assert e[0]["how"] == "we took it"
    assert trk.done[0].end["z_before"] > trk.cfg.pick_s             # its only press: long before the window


def test_the_key_up_or_us_out_of_reach_is_gone_in_view():
    for me, keys in (((604.0, YF + 1.0), ()), ((700.0, YF + 1.0), "press")):
        trk = tracker()
        _, t = lie(trk, 600, 0.0, 1.0, me=me)
        k = [(t + 0.001, "z", True), (t + 0.05, "z", False)] if keys == "press" else ()
        e, t = hop(trk, 600, t, bob(t), me=me, keys=k)
        assert e[0]["how"] == "gone in view"


def test_gone_when_its_place_shows_the_scenery_for_015_s():
    trk = tracker()
    _, t = lie(trk, 600, 0.0, 1.0)
    e, t2 = unseen(trk, t, 0.12, EMPTY)
    assert e == [] and trk.drops()[0].cover == "empty"
    e, t2 = unseen(trk, t2, 0.06, EMPTY)
    assert [x["ev"] for x in e] == ["drop_gone"] and e[0]["how"] == "gone in view"


def test_found_gone_after_a_long_cover():
    trk = tracker()
    _, t = lie(trk, 600, 0.0, 1.0)
    unseen(trk, t, 2.0, COVERED)
    e, _ = unseen(trk, t + 2.0, 0.2, EMPTY)
    assert e[0]["how"] == "found gone"


def test_kept_while_covered_under_the_ui_or_out_of_view_then_130_s_old():
    trk = tracker()
    _, t = lie(trk, 600, 0.0, 1.0)
    for evidence, cover in ((COVERED, "covered"), (ev(False, False), "ui")):
        e, t = unseen(trk, t, 0.5, evidence)
        assert e == [] and trk.drops()[0].cover == cover and not trk.drops()[0].seen
    trk2 = tracker()
    _, t = lie(trk2, 600, 0.0, 1.0)
    far = (5000, 0)                                # the camera far away: its place off screen
    e, t = [], t
    while t < 129.9:
        t += 0.1
        e += trk2.update(facts(t, C=far), EMPTY)
    assert e == [] and trk2.drops()[0].cover == "out of view"
    while t < 130.05:
        t += 0.1
        e += trk2.update(facts(t, C=far), EMPTY)
    assert [x["how"] for x in e] == ["130 s old"]


def mob(i, life, x, y=YF, seen=True):
    return SimpleNamespace(id=i, life=life, x_seen=x, y_seen=y, seen=seen)


def test_from_mob_is_the_death_before_it_nearest_the_usual_delay():
    trk = tracker()
    trk.update(facts(-1.4), COVERED, mobs=[mob(5, "dying", 640)])     # 1.4 s before: the usual delay
    trk.update(facts(-1.0), COVERED, mobs=[mob(6, "dying", 560)])     # 1.0 s before: fits too, less usual
    trk.update(facts(-0.9), COVERED, mobs=[mob(8, "dying", 800)])     # too far sideways
    trk.update(facts(-0.3), COVERED, mobs=[mob(7, "dying", 600)])     # too late to be its mob
    e, _ = lie(trk, 600, 0.0, 0.3)
    assert e[0]["from_mob"] == 5 and trk.done == [] and trk.live[(4000000, 600)][0].n_from == 2


def test_no_death_no_mob_and_a_death_taken_back_is_forgotten():
    trk = tracker()
    trk.update(facts(-1.4), COVERED, mobs=[mob(5, "dying", 600)])
    trk.update(facts(-1.3), COVERED, mobs=[mob(5, "alive", 600)])     # a live pose right after: it lives
    assert trk.deaths == [] and trk.stats["death taken back"] == 1
    e, _ = lie(trk, 600, 0.0, 0.3)
    assert e[0]["from_mob"] is None


def test_a_blind_frame_changes_nothing():
    trk = tracker()
    _, t = lie(trk, 600, 0.0, 1.0)
    before = trk.drops()[0]
    t += DT
    e = trk.update(SimpleNamespace(t=t, scene_cam=None, drops=None), EMPTY)
    d = trk.drops()[0]
    assert e == [] and d.cover == "blind" and not d.seen and d.id == before.id
    e = trk.update(facts(t + DT, [sight(600, bob(t + DT))]), COVERED)
    assert e == [] and trk.drops()[0].seen


def ref_look(tr, d, C, shows, world, t):
    """The prototype's look (proto_drops.DropTracker._look + counts), one placement at a time, early exit."""
    c = tr.cfg
    lo, hi = d.yf + c.drop_band[0], d.yf + c.drop_band[1]
    e = d.expect(t, c)
    y0 = int(round(e)) if e is not None else d.y
    ys = sorted(range(max(lo + 1, d.y_hi - 7), min(hi - 1, d.y_lo + 7) + 1), key=lambda y: abs(y - y0))
    best, any_on = None, False
    for _f, dx, dy, n_op in tr.pics.cores[d.item]:
        h, w = -int(dy.min()), int(dx.max() - dx.min()) + 1
        mask = np.zeros((h, w), bool)
        mask[dy + h, dx + w // 2] = True
        for y in ys:
            x, yy = d.x - C[0] - w // 2, y - C[1] - h
            x0, y0_, x1, y1 = max(0, x), max(0, yy), min(SW, x + w), min(PLAY_H, yy + h)
            if x1 <= x0 or y1 <= y0_:
                n_on = n_abs = n_front = n_unk = 0
            else:
                mk = mask[y0_ - yy:y1 - yy, x0 - x:x1 - x]
                sh, wo = shows[y0_:y1, x0:x1], world[y0_:y1, x0:x1]
                n_on = int(mk.sum())
                P = tr.fronts.planes.get(d.layer) if tr.fronts is not None else None
                fr = P[y0_ + C[1] - tr.fronts.y0:y1 + C[1] - tr.fronts.y0, x0 + C[0] - tr.fronts.x0:x1 + C[0]
                       - tr.fronts.x0] if P is not None else None
                if fr is not None and fr.any():
                    n_front, n_abs = int((mk & fr & sh).sum()), int((mk & sh & ~fr).sum())
                else:
                    n_front, n_abs = 0, int((mk & sh).sum())
                n_unk = int((mk & ~wo).sum())
            any_on = any_on or n_on > 0
            if n_abs <= c.look_abs * n_op:
                best = (n_op, n_on, n_abs, n_front, n_unk)
                break
        if best is not None:
            break
    if not any_on:
        return "out"
    if best is None:
        return "absent"
    n_op, n_on, n_abs, n_front, n_unk = best
    return "edge" if n_on < 0.7 * n_op else "ui" if n_unk >= 0.3 * n_op else "scenery" if n_front >= 0.3 * n_op \
        else "covered"


def test_the_look_answers_as_the_prototypes_counts():
    """Random bitmaps with blobs of scenery / cover / UI, a front plane, drops on screen and at its edges: the
    batched look (one evidence call for all, the first picture first) = the prototype's placement-by-placement
    look on every drop."""
    rng = np.random.default_rng(3)
    fr = np.zeros((900, 1800), bool)
    fr[530:560, 300:420] = True                     # front scenery over some drops (map x 200-320, y 480-510)
    fronts = Fronts({0: fr}, -100, -50)
    answers = []
    for k in range(40):
        shows = np.zeros((PLAY_H, SW), bool)        # (covered: something drawn everywhere ...)
        world = np.ones((PLAY_H, SW), bool)
        for _ in range(300):                        # ... but blobs of scenery shown / of UI around the drops
            x, y, w, h = rng.integers(0, SW), rng.integers(460, 515), rng.integers(4, 80), rng.integers(4, 40)
            v = rng.integers(0, 3)
            if v == 0:
                shows[y:y + h, x:x + w] = True
            elif v == 1:
                world[y:y + h, x:x + w] = False
                shows[y:y + h, x:x + w] = False
        if k % 2:
            shows[480:510, 200:320] = True          # the scenery shows under the front plane
        trk = DropTracker(pics(), fronts, None, "z", Track())
        drops, t = [], 0.0
        for i in range(25):
            item = 9000000 if i % 2 else 4000000
            x = int(rng.integers(-15, SW + 15))
            t0 = t
            while t < t0 + 0.3:
                trk.update(facts(t, [sight(x, YF + int(rng.integers(-3, 5)), item)]), COVERED)
                t += DT
            drops.append(trk.live[(item, x)][0])
        C = (0, 0)
        got = trk._look(drops, C, Bitmaps(shows, world), t)
        want = [ref_look(trk, d, C, shows, world, t) for d in drops]
        assert got == want
        answers += got
    assert {"absent", "covered", "edge", "ui", "scenery"} <= set(answers)
