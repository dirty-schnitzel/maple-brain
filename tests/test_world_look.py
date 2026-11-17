"""World.update's look (PLAN-perception.md step 3.4): the fit's look at each track it did not find; no probes
and no edge-ghost score rule (deleted with the old detector 2026-11-17)."""
from test_world import CAM, ME, hit, world


def test_look_is_asked_for_the_unseen_tracks_only_and_its_hit_is_a_near_sighting():
    w = world()
    w.update(0.0, [hit(500, score=1.0), hit(700, score=1.0)], CAM, ME, look=lambda trs: [None] * len(trs))
    asked = []

    def look(trs):
        asked.append([tr.id for tr in trs])
        return [hit(tr.sx + 3, tr.sy, score=1.0) for tr in trs]

    trs = w.update(0.05, [hit(702, score=1.0)], CAM, ME, look=look)
    assert asked == [[1]]                                       # the track at 700 was seen by the fit
    t1 = next(tr for tr in trs if tr.id == 1)
    assert t1.src == "near" and t1.sx == 503


def test_no_edge_score_rule_but_a_new_track_needs_most_of_its_body_on_screen():
    w = world()
    edge = hit(5, score=1.0)                                    # 42 % of its body past the left edge
    w.update(0.0, [edge], CAM, ME, look=lambda trs: [None] * len(trs))
    assert w.stats.get("rejected_edge", 0) == 1                 # a NEW track still needs 60 % on screen
    w2 = world()
    w2.update(0.0, [hit(30, score=1.0)], CAM, ME, look=lambda trs: [None] * len(trs))
    trs = w2.update(0.05, [hit(5, score=0.6)], CAM, ME, look=lambda trs: [None] * len(trs))
    assert trs[0].src == "acq" and trs[0].sx == 5               # a tracked mob is followed out to the edge


def test_a_live_pose_a_look_finds_on_a_dying_mob_is_a_new_mob():
    """The fit's look at a dying track finds a live pose there: another mob stepped in (dead is final)."""
    w = world()
    w.update(0.0, [hit(500, score=1.0)], CAM, ME)
    trs = w.update(0.05, [hit(500, anim="die1", score=1.0)], CAM, ME)
    assert trs[0].state == "dying"
    look = lambda trs: [hit(504, score=1.0) if abs(tr.sx - 504) < 40 else None for tr in trs]   # noqa: E731
    for k in range(2):
        w.update(0.10 + 0.05 * k, [], CAM, ME, look=look)
    assert any(tr.id != 1 and tr.state != "dying" for tr in w.tracks)
