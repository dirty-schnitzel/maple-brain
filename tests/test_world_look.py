"""World.update's fit path (PLAN-perception.md step 3.4): `look(tracks)` replaces `near`, the probes and the
edge-ghost score rule."""
from test_world import ME, ME_MAP, hit, world


def test_look_is_asked_for_the_unseen_tracks_only_and_its_hit_is_a_near_sighting():
    w = world()
    w.update(0.0, [hit(500, score=1.0), hit(700, score=1.0)], ME, ME_MAP, look=lambda trs: [None] * len(trs))
    asked = []

    def look(trs):
        asked.append([tr.id for tr in trs])
        return [hit(tr.sx + 3, tr.sy, score=1.0) for tr in trs]

    trs = w.update(0.05, [hit(702, score=1.0)], ME, ME_MAP, look=look)
    assert asked == [[1]]                                       # the track at 700 was seen by the fit
    t1 = next(tr for tr in trs if tr.id == 1)
    assert t1.src == "near" and t1.sx == 503


def test_no_probes_and_no_edge_score_rule_on_the_fit_path():
    w = world()
    w._probes = lambda *a: (_ for _ in ()).throw(AssertionError("probes on the fit path"))
    edge = hit(5, score=1.0)                                    # 42 % of its body past the left edge
    w.update(0.0, [edge], ME, ME_MAP, look=lambda trs: [None] * len(trs))
    assert w.stats.get("rejected_edge", 0) == 1                 # a NEW track still needs 60 % on screen
    w2 = world()
    w2.update(0.0, [hit(30, score=1.0)], ME, ME_MAP, look=lambda trs: [None] * len(trs))
    trs = w2.update(0.05, [hit(5, score=0.6)], ME, ME_MAP, look=lambda trs: [None] * len(trs))
    assert trs[0].src == "acq" and trs[0].sx == 5               # a weak edge sighting counts (the rule is off)
    w3 = world()
    w3.update(0.0, [hit(30, score=1.0)], ME, ME_MAP)
    trs = w3.update(0.05, [hit(5, score=0.6)], ME, ME_MAP)
    assert trs[0].src == "none"                                 # ... and is dropped on today's path
