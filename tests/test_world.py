import numpy as np

from maplebrain.nav.navmap import NavMap
from maplebrain.perception.sighting import Hit, Pose
from maplebrain.perception.world import Camera, World

MAP = {"footholds": {"1": {"id": 1, "x1": 0, "y1": 500, "x2": 2000, "y2": 500, "prev": 0, "next": 0}},
       "vrBounds": {"left": -500, "top": -500, "right": 3000, "bottom": 1268}, "mobs": [{"id": 8, "x": 500, "y": 500}]}
MOBS = {8: {"name": "Pig", "frames": {"die1": [{"delay": 180}, {"delay": 180}, {"delay": 300}]}},
        10: {"name": "Ribbon Pig", "frames": {}}}


def hit(x, y=500, mob=8, anim="move", score=0.8, facing="left"):
    return Hit(mob, (x - 30, y - 45, 60, 45), (x, y), Pose(anim, 0, facing, 30, 45), score)


def world():
    return World(NavMap.from_json(MAP), MOBS)


ME = (900.0, 500.0)          # our feet on screen
CAM = (0.0, 0.0)             # the scene camera: map = screen


def test_one_id_while_the_mob_walks_and_through_a_short_gap():
    w = world()
    ids = set()
    t = 0.0
    for i in range(10):
        t += 0.05
        trs = w.update(t, [hit(500 - 4 * i)], CAM, ME)
        ids |= {tr.id for tr in trs}
    assert len(trs) == 1 and trs[0].state == "live" and trs[0].vx < -40
    for _ in range(3):                                          # unseen (covered) for 0.15 s: it coasts on
        t += 0.05
        trs = w.update(t, [], CAM, ME)
    assert len(trs) == 1 and trs[0].x < 500 - 4 * 9
    t += 0.05
    trs = w.update(t, [hit(500 - 4 * 13)], CAM, ME)
    ids |= {tr.id for tr in trs}
    assert ids == {1}


def test_a_long_frame_gap_alone_doesnt_end_a_track():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], CAM, ME)
    trs = w.update(0.6, [], CAM, ME)                          # the bot's loop stalled 0.6 s (a key tap)
    assert len(trs) == 1


def test_ends_after_enough_missed_frames_in_view():
    w = world()
    w.update(0.0, [hit(300, score=0.9)], CAM, ME)
    t, trs = 0.0, None
    for _ in range(12):
        t += 0.06
        trs = w.update(t, [], CAM, ME)
    assert trs == []


def test_look_alike_types_are_voted():
    w = world()
    w.update(0.0, [hit(500, mob=10, score=0.66)], CAM, ME)
    for i in range(1, 4):
        trs = w.update(0.05 * i, [hit(500, mob=8, score=0.9)], CAM, ME)
    assert len(trs) == 1 and trs[0].mob_id == 8 and trs[0].id == 1


def test_off_platform_sightings_start_no_track():
    w = world()
    assert w.update(0.0, [hit(500, y=180, score=0.9)], CAM, ME) == []          # 320 px up: no jump


def test_die_pose_then_gone():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], CAM, ME)
    trs = w.update(0.05, [hit(500, anim="die1", score=0.9)], CAM, ME)
    assert trs[0].state == "dying"
    assert w.update(1.0, [], CAM, ME) == []                   # die1 = 0.66 s, + 0.2


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
    w = World(NavMap.from_json(MAP), MOBS, cover=_Cover())
    t = 0.0
    for i in range(6):
        t += 0.05
        trs = w.update(t, [hit(560 + 6 * i, score=0.9)], CAM, ME)
    for _ in range(20):                                         # 1 s unseen, inside the patch
        t += 0.05
        trs = w.update(t, [], CAM, ME)
    assert len(trs) == 1 and trs[0].state == "hidden" and trs[0].id == 1
    for _ in range(30):                                         # 1.5 s more: hidden_s (2 s) is up
        t += 0.05
        trs = w.update(t, [], CAM, ME)
    assert trs == []


def test_a_lone_weak_die_match_doesnt_kill_a_live_mob():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], CAM, ME)
    trs = w.update(0.05, [hit(500, anim="die1", score=0.6)], CAM, ME)       # one weak die match
    assert trs[0].state != "dying"
    trs = w.update(0.10, [hit(500, score=0.9)], CAM, ME)
    trs = w.update(0.15, [hit(500, anim="die1", score=0.6)], CAM, ME)       # the count started over
    assert trs[0].state != "dying"


def test_a_live_mob_where_one_died_is_a_new_track():
    w = world()
    w.update(0.0, [hit(500, score=0.9)], CAM, ME)
    trs = w.update(0.05, [hit(500, anim="die1", score=0.9)], CAM, ME)
    assert trs[0].state == "dying"
    trs = w.update(0.10, [hit(504, score=0.9)], CAM, ME)                    # a new Pig steps in
    live = [tr for tr in trs if tr.state != "dying"]
    assert len(live) == 1 and live[0].id != 1 and any(tr.id == 1 and tr.state == "dying" for tr in trs)


def test_no_new_mob_mostly_past_the_screen_edge_but_a_tracked_one_is_followed_there():
    """Half a sprite at the screen's right edge matched cave scenery at 0.57-0.68 (37-48 % on screen); real mobs
    walking in are found at 78 %+. A track that already exists is still followed out to the edge."""
    w = world()
    for k in range(4):
        w.update(0.05 * k, [hit(1372, score=0.9)], CAM, ME)                    # feet past the edge: 40 % on
    assert not w.tracks and w.stats["rejected_edge"] == 4
    w = world()
    for k in range(4):
        w.update(0.05 * k, [hit(1350, score=0.9)], CAM, ME)                    # 77 % on screen: a mob
    assert len(w.tracks) == 1
    w = world()
    t, x = 0.0, 1336
    while x <= 1372:                                                            # walks out to the edge, 4 px/frame
        trs = w.update(t, [hit(x, score=0.9)], CAM, ME)
        t, x = t + 0.05, x + 4
    assert [tr.id for tr in trs] == [1] and trs[0].sx == 1372


def test_the_camera_is_the_scene_cameras_and_tracks_move_with_it():
    """Since 2026-11-17 nothing but the scene camera moves C (map = screen + C): no shift, minimap pull or clamp."""
    assert Camera().update((-40, 12)) == (-40.0, 12.0)
    w = world()
    w.update(0.0, [hit(500, score=1.0)], CAM, ME)
    trs = w.update(0.05, [], (30.0, 0.0), ME, look=lambda trs: [None] * len(trs))   # the camera scrolled 30 px
    assert trs[0].x == 500 and trs[0].sx == 470
