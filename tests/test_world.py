import numpy as np

from maplebrain.nav.navmap import NavMap
from maplebrain.perception.gpu_sprites import Hit
from maplebrain.perception.sprites import Pose
from maplebrain.perception.world import Camera, TrackCfg, World

MAP = {"footholds": {"1": {"id": 1, "x1": 0, "y1": 500, "x2": 2000, "y2": 500, "prev": 0, "next": 0}},
       "vrBounds": {"left": -500, "top": -500, "right": 3000, "bottom": 1268}, "mobs": [{"id": 8, "x": 500, "y": 500}]}
MOBS = {8: {"name": "Pig", "frames": {"die1": [{"delay": 180}, {"delay": 180}, {"delay": 300}]}},
        10: {"name": "Ribbon Pig", "frames": {}}}


def hit(x, y=500, mob=8, anim="move", score=0.8, facing="left"):
    return Hit(mob, (x - 30, y - 45, 60, 45), (x, y), Pose(anim, 0, facing, 30, 45), score)


def world():
    return World(NavMap.from_json(MAP), MAP, MOBS)


ME = (900.0, 500.0)          # our feet on screen; with this map position the camera offset is 0
ME_MAP = (900.0, 500.0)


def test_camera_follows_the_scenery_and_stays_inside_the_map():
    cam = Camera({"left": 0, "top": 0, "right": 2000, "bottom": 768}, pull=0.0)
    assert cam.update(None, (100, 500), (300, 500)) == (200, 0)
    assert cam.update((10, 0), None, None) == (190, 0)          # scenery moved right: the camera went left
    assert cam.update((500, 0), None, None) == (0, 0)           # never past the map's left edge


def test_one_id_while_the_mob_walks_and_through_a_short_gap():
    w = world()
    ids = set()
    t = 0.0
    for i in range(10):
        t += 0.05
        trs = w.update(t, [hit(500 - 4 * i)], ME, ME_MAP)
        ids |= {tr.id for tr in trs}
    assert len(trs) == 1 and trs[0].state == "live" and trs[0].vx < -40
    for _ in range(3):                                          # unseen (covered) for 0.15 s: it coasts on
        t += 0.05
        trs = w.update(t, [], ME, ME_MAP)
    assert len(trs) == 1 and trs[0].x < 500 - 4 * 9
    t += 0.05
    trs = w.update(t, [hit(500 - 4 * 13)], ME, ME_MAP)
    ids |= {tr.id for tr in trs}
    assert ids == {1}


def test_a_long_frame_gap_alone_doesnt_end_a_track():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], ME, ME_MAP)
    trs = w.update(0.6, [], ME, ME_MAP)                          # the bot's loop stalled 0.6 s (a key tap)
    assert len(trs) == 1


def test_ends_after_enough_missed_frames_in_view():
    w = world()
    w.update(0.0, [hit(300, score=0.9)], ME, ME_MAP)
    t, trs = 0.0, None
    for _ in range(12):
        t += 0.06
        trs = w.update(t, [], ME, ME_MAP)
    assert trs == []


def test_look_alike_types_are_voted():
    w = world()
    w.update(0.0, [hit(500, mob=10, score=0.66)], ME, ME_MAP)
    for i in range(1, 4):
        trs = w.update(0.05 * i, [hit(500, mob=8, score=0.9)], ME, ME_MAP)
    assert len(trs) == 1 and trs[0].mob_id == 8 and trs[0].id == 1


def test_off_platform_sightings_start_no_track():
    w = world()
    assert w.update(0.0, [hit(500, y=180, score=0.9)], ME, ME_MAP) == []          # 320 px up: no jump


def test_die_pose_then_gone():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], ME, ME_MAP)
    trs = w.update(0.05, [hit(500, anim="die1", score=0.9)], ME, ME_MAP)
    assert trs[0].state == "dying"
    assert w.update(1.0, [], ME, ME_MAP) == []                   # die1 = 0.66 s, + 0.2


class _Cover:
    """A stand-in cover.Cover: map x 600..700 covered for layer 0."""
    def layer(self, platform_id):
        return 0

    def visible(self, layer, C, w=1366, h=700):
        v = np.ones((h, w), bool)
        v[:, int(600 - C[0]):int(700 - C[0])] = False
        return v

    masks = {}


def test_a_mob_walking_into_cover_is_hidden_not_lost():
    import numpy  # noqa: F401
    w = World(NavMap.from_json(MAP), MAP, MOBS, cover=_Cover())
    t = 0.0
    for i in range(6):
        t += 0.05
        trs = w.update(t, [hit(560 + 6 * i, score=0.9)], ME, ME_MAP)
    for _ in range(20):                                         # 1 s unseen, inside the patch
        t += 0.05
        trs = w.update(t, [], ME, ME_MAP)
    assert len(trs) == 1 and trs[0].state == "hidden" and trs[0].id == 1
    for _ in range(30):                                         # 1.5 s more: hidden_s (2 s) is up
        t += 0.05
        trs = w.update(t, [], ME, ME_MAP)
    assert trs == []


def test_a_lone_weak_die_match_doesnt_kill_a_live_mob():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], ME, ME_MAP)
    trs = w.update(0.05, [hit(500, anim="die1", score=0.6)], ME, ME_MAP)       # one weak die match
    assert trs[0].state != "dying"
    trs = w.update(0.10, [hit(500, score=0.9)], ME, ME_MAP)
    trs = w.update(0.15, [hit(500, anim="die1", score=0.6)], ME, ME_MAP)       # the count started over
    assert trs[0].state != "dying"


def test_a_live_mob_where_one_died_is_a_new_track():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], ME, ME_MAP)
    trs = w.update(0.05, [hit(500, anim="die1", score=0.9)], ME, ME_MAP)
    assert trs[0].state == "dying"
    trs = w.update(0.10, [hit(504, score=0.9)], ME, ME_MAP)                    # a new Pig steps in
    live = [tr for tr in trs if tr.state != "dying"]
    assert len(live) == 1 and live[0].id != 1 and any(tr.id == 1 and tr.state == "dying" for tr in trs)


def test_a_higher_mob_score_raises_what_makes_a_new_mob_not_what_follows_one():
    """--mob-score: probes make new mobs too; a tracked mob stays followed through its near search."""
    base = TrackCfg()
    c = TrackCfg.for_mob_score(0.8)
    assert c.probe_score == 0.8 and c.near_score == base.near_score
    assert TrackCfg.for_mob_score(0.5).probe_score == base.probe_score      # never below the default
