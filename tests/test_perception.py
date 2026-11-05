"""Perception regressions on real frames from the live runs (each one broke an earlier version)."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebot.config import Config
from maplebot.perception import hud
from maplebot.perception.perceiver import Perceiver
from maplebot.perception.selfpos import find_self

FX = Path(__file__).parent / "fixtures"
TAG = np.load(FX / "self_tag_gray.npy")


def img(name):
    f = cv2.imread(str(FX / name))
    assert f is not None, name
    return f


# ---------------------------------------------------------------- own position
@pytest.mark.parametrize("name, xy", [
    ("self_normal.png", (674, 579)),
    ("self_bridge.jpg", (717, 560)),          # tag in front of the bright woven bridge (hunt6: lost for 15s)
    ("self_dim_on_grass.jpg", (1051, 594)),   # dim anti-aliased tag over grass (hunt6d: never found)
    ("self_under_cloud.jpg", (277, 519)),     # drifting cloud over the tag (manual 20261101_225745_2 287 s:
    ("self_under_cloud_swing.jpg", (277, 519)),  # 0.46 before the high-pass, 2 s of 'hidden? backing out')
])
def test_finds_own_name_tag(name, xy):
    me = find_self(img(name), TAG)
    assert me is not None and abs(me[0] - xy[0]) <= 3 and abs(me[1] - xy[1]) <= 3


def test_hidden_behind_foreground_object_is_not_found():
    assert find_self(img("self_hidden_behind_basket.jpg"), TAG) is None


@pytest.mark.parametrize("name", ["self_normal.png", "self_bridge.jpg", "self_dim_on_grass.jpg",
                                  "self_under_cloud.jpg", "hp_30_of_66_two_mob_bars.png", "exp_88_24.jpg"])
def test_searching_near_a_wrong_spot_never_matches_something_else(name):
    f = img(name)
    me = find_self(f, TAG)
    for off in (-250, 250):
        r = find_self(f, TAG, near=(me[0] + 37 + off, me[1]), min_score=0.64)
        assert r is None or abs(r[0] - me[0]) <= 3          # finds us or nothing (once matched chat text)


# ---------------------------------------------------------------- HUD
@pytest.mark.parametrize("name, hp, mp", [
    ("hp_30_of_66_two_mob_bars.png", (30, 66), (17, 17)),   # low HP: the bar turned pale pink (once read as 0%)
    ("hp_60_of_66.jpg", (60, 66), (17, 17)),                  # (JPEG: blurred digits, pale brackets)
    ("hp_0_dead.jpg", (0, 66), (17, 17)),
    ("self_normal.png", (66, 66), (17, 17)),
    ("exp_3_51.jpg", (77, 82), (29, 29)),
    ("exp_24_56.jpg", (43, 82), (29, 29)),
    ("quickslot_tooltip_over_end.jpg", (92, 130), (65, 65)),
])
def test_hp_mp_numbers(name, hp, mp):
    """HP/MP come from the HUD text "HP [cur/max]" only (the user, session 16), not the bar's fill."""
    f = img(name)
    assert hud.read_pair(f, hud.HP_TEXT) == hp and hud.read_pair(f, hud.MP_TEXT) == mp


@pytest.mark.parametrize("name", ["exp_88_24.jpg", "exp_3_51.jpg", "exp_24_56.jpg"])
def test_exp_points_readable_on_older_hud_frames(name):
    assert hud.exp_points(img(name)) is not None                    # (the bar isn't used any more: points only)


def test_mob_hp_bars():
    bars = sorted(hud.find_mob_bars(img("hp_30_of_66_two_mob_bars.png")))
    assert [(b[0], b[1]) for b in bars] == [(626, 517), (692, 526)]


def test_minimap_dot_found():
    assert hud.minimap_dot(img("self_normal.png")) is not None


# ---------------------------------------------------------------- perceiver + motion look
def test_look_finds_snails_on_our_ground_line_and_nothing_else():
    frames = [img(f"look_snails/f{i:03d}.png") for i in (87, 88, 89, 90)]
    p = Perceiver(Config(), TAG)
    obs = p.observe(frames[-1], t=0.0)
    assert obs.me is not None and obs.me[1] == 579
    obs = p.look(frames, obs)
    assert obs.look_align > 0.9
    xs = sorted(int(b[0] + b[2] / 2) for b in obs.moving)
    # three snails walking on our ground line; flowers/foliage/high leaves rejected
    assert len(xs) == 3 and all(abs(a - b) <= 12 for a, b in zip(xs, [252, 318, 437]))


def test_perceiver_observation_fields():
    p = Perceiver(Config(), TAG)
    obs = p.observe(img("hp_30_of_66_two_mob_bars.png"), t=1.0)
    assert obs.me is not None
    assert len(obs.bar_mobs) == 2 and obs.known_mobs[:2] == obs.bar_mobs
    assert obs.hp == pytest.approx(30 / 66, abs=0.04)


# ---------------------------------------------------------------- mob library
def test_library_forgets_a_wrong_entry_even_when_the_tracker_box_is_bigger():
    """pkg_swing1: a grass tuft got into the library (47x40); 'not a mob' asked it to forget the tracker's padded
    55x48 template -> shapes never matched, nothing was forgotten, the bot hit the grass 33 times."""
    from maplebot.perception.mobs import MobLibrary, Tracker, gray
    f = img("library_grass.jpg")
    x, y, w, h = 690, 542, 47, 40
    lib = MobLibrary()
    lib.add(gray(f)[y:y + h, x:x + w])
    assert lib.find(f, 579, [])                                             # it matches the grass
    tracked = Tracker(f, (x, y, w, h))
    assert tracked.box[2:] != (w, h)
    lib.forget_at(f, tracked.box)
    assert len(lib) == 0 and not lib.find(f, 579, [])


def test_library_forget_keeps_entries_that_do_not_match_there():
    from maplebot.perception.mobs import MobLibrary, gray
    f = img("library_grass.jpg")
    lib = MobLibrary()
    lib.add(gray(f)[542:582, 690:737])                                      # the grass
    lib.add(gray(f)[540:580, 100:147])                                      # something elsewhere
    lib.forget_at(f, (686, 538, 55, 48))
    assert len(lib) == 1


def test_mobs_a_step_below_us_count_but_not_ones_above():
    """pkg_swing1 start: we stood on a small step; snails on the ground ~60 px below were filtered out as 'not on
    our ground line'. Walking off a step is free; going up needs a jump."""
    from maplebot.perception.perceiver import reachable_level
    feet = 545
    assert reachable_level((900, 560, 40, 26), feet, 18, 80)               # bottom 586: 41 px below
    assert reachable_level((900, 579, 40, 26), feet, 18, 80)               # 60 px below
    assert not reachable_level((900, 400, 40, 26), feet, 18, 80)           # 119 px above: a ledge / ghost
    assert not reachable_level((900, 640, 40, 26), feet, 18, 80)           # 121 px below: another floor
    assert reachable_level((900, 510, 40, 26), feet, 18, 80)               # on our line


# ---------------------------------------------------------------- own tag cut off by the screen edge
def _shift(frame, dx):
    """The frame moved dx px sideways (what leaves the picture is gone, the rest is black)."""
    return cv2.warpAffine(frame, np.float32([[1, 0, dx], [0, 1, 0]]), (frame.shape[1], frame.shape[0]))


@pytest.mark.parametrize("visible", [70, 56, 46])
def test_finds_own_tag_cut_off_by_the_right_screen_edge(visible):
    """pkg_sprites3 69-76s: at the map's right end the camera stops and our tag ran off the screen ('JenkinsJ').
    Not found for 7 s; 'backing out' walked further right while a Blue Snail hit us 65 -> 51 %."""
    f = img("self_normal.png")                      # tag at x 674..748 (centre 711), top 579
    W = f.shape[1]
    dx = (W - visible) - 674
    me = find_self(_shift(f, dx), TAG)
    assert me is not None
    assert abs((me[0] + me[2] / 2) - (711 + dx)) <= 3 and abs(me[1] - 579) <= 3


@pytest.mark.parametrize("visible", [70, 50])
def test_finds_own_tag_cut_off_by_the_left_screen_edge(visible):
    f = img("self_normal.png")
    dx = -(674 + 74 - visible)
    me = find_self(_shift(f, dx), TAG)
    assert me is not None
    assert abs((me[0] + me[2] / 2) - (711 + dx)) <= 3 and abs(me[1] - 579) <= 3


def test_a_sliver_of_a_tag_at_the_edge_is_not_trusted():
    f = img("self_normal.png")
    dx = (f.shape[1] - 25) - 674                   # only 25 of 74 px left: too little to be sure
    assert find_self(_shift(f, dx), TAG) is None


@pytest.mark.parametrize("name", ["hp_30_of_66_two_mob_bars.png", "exp_88_24.jpg", "library_grass.jpg"])
def test_edge_search_does_not_invent_a_tag(name):
    f = img(name)
    me = find_self(f, TAG)
    if me is not None:                              # the frame's real tag, wherever it is - never at an edge
        assert 0 <= me[0] and me[0] + me[2] <= f.shape[1]


# ---------------------------------------------------------------- potions: HP/MP bars and the quickslots
def test_hp_mp_numbers_in_the_dark_low_hp_flash():
    f = img("quickslot_hp_potions_4.jpg")
    assert f.shape == (768, 1366, 3)
    assert hud.read_pair(f, hud.HP_TEXT) == (60, 130) and hud.read_pair(f, hud.MP_TEXT) == (65, 65)


def test_slot_with_potions_and_empty_slots():
    f = img("quickslot_hp_potions_4.jpg")                                     # 4 red potions on Del, End empty
    assert hud.slot_filled(f, "delete") is True
    assert hud.slot_filled(f, "end") is False
    assert hud.slot_filled(f, "ctrl") is False and hud.slot_filled(f, "pagedown") is False


def test_no_potions_yet_reads_empty():
    assert hud.slot_filled(img("quickslot_no_potions.jpg"), "delete") is False


def test_unknown_key_has_no_slot():
    assert hud.slot_filled(img("quickslot_hp_potions_4.jpg"), "f1") is None


def test_a_tooltip_from_the_cursor_is_not_taken_for_mp_potions():
    """pkg_sprites7b frame 300: the cursor on Del opened the potion's tooltip over End/PgDn."""
    f = img("quickslot_tooltip_over_end.jpg")
    assert hud.slot_filled(f, "end") is True                                  # the raw reading is fooled...
    p = Perceiver(Config(), TAG)
    for i in range(5):
        p.observe(img("quickslot_hp_potions_4.jpg"), i * 0.05)                # End empty before
    obs = p.observe(f, 0.3, cursor=(990, 678))                                # ...cursor over the slots: skipped
    assert obs.mp_potions is False and obs.hp_potions is True


def test_one_odd_slot_reading_does_not_flip_the_answer():
    p = Perceiver(Config(), TAG)
    for i in range(4):
        p.observe(img("quickslot_hp_potions_4.jpg"), i * 0.05)
    obs = p.observe(img("quickslot_tooltip_over_end.jpg"), 0.25)              # no cursor info this time
    assert obs.mp_potions is False


# ---------------------------------------------------------------- the game's Lie Detector (anti-bot test)
def _lie(background=False):
    from maplebot.perception.liedetector import LieDetector
    return LieDetector.load(FX, background=background)


def test_lie_detector_announcement_panel_is_seen():
    """pkg_potions1 52.4 s: '5 sec until the Lie Detector mini-game starts' panel, bottom right."""
    s, loc = _lie().score(cv2.imread(str(FX / "lie_detector_panel.jpg")))
    assert s >= 0.85 and loc[0] > 1000


def test_lie_detector_mini_game_window_is_seen():
    s, loc = _lie().score(cv2.imread(str(FX / "lie_detector_game.jpg")))
    assert s >= 0.95 and 500 < loc[0] < 800


@pytest.mark.parametrize("name", ["lie_detector_blue_panel.jpg", "lie_detector_blue_game.jpg"])
def test_the_blue_lie_detector_is_seen_too(name):
    """pkg_sight5 55.5-82.3 s: a second kind of Lie Detector (blue title bar, 'The Lie Detector Mini-game': a
    panel 'go to a safe place', then a mouse game 'follow the fading figure'). Not recognized: the bot hunted on
    through the whole test while the user did it with the mouse."""
    assert _lie().seen(cv2.imread(str(FX / name)))


def test_the_quiz_lie_detector_is_seen_and_ships_with_the_bot():
    """The user's screenshot 2026-11-02 14:07: a third kind - a translucent blue box in the centre, 'Question in 10
    seconds' / 'Answer within 10 seconds' (a quiz). No window title, so it matches the words 'Question in'."""
    from maplebot.perception.liedetector import LieDetector
    from maplebot.runtime.runner import ASSETS
    frame = cv2.imread(str(FX / "lie_detector_question.jpg"))
    s, loc = _lie().score(frame)
    assert s >= 0.9 and 600 < loc[0] < 700
    assert LieDetector.load(ASSETS).seen(frame)


def test_the_blue_lie_detector_template_ships_with_the_bot():
    from maplebot.perception.liedetector import LieDetector
    from maplebot.runtime.runner import ASSETS
    assert LieDetector.load(ASSETS).seen(cv2.imread(str(FX / "lie_detector_blue_game.jpg")))


def test_lie_detector_not_seen_on_a_normal_frame():
    assert not _lie().seen(cv2.imread(str(FX / "lie_detector_none.jpg")))
    assert not _lie().seen(cv2.imread(str(FX / "lie_detector_blue_none.jpg")))   # 0.6 s before it appeared
    assert not _lie().seen(cv2.imread(str(FX / "sprites_six_unhit.jpg")))


def test_lie_detector_check_is_throttled_but_catches_it_within_the_interval():
    lie = _lie()
    none, game = cv2.imread(str(FX / "lie_detector_none.jpg")), cv2.imread(str(FX / "lie_detector_game.jpg"))
    assert lie.check(none, 0.0)[0] is False
    assert lie.check(game, 0.1)[0] is False                    # not looked again yet
    assert lie.check(game, 0.1 + lie.every_s)[0] is True


def test_a_new_hunt_does_not_inherit_the_last_hunts_lie_detector():
    """serve 2026-11-04: hunt #3 stopped on a Lie Detector at 3283 s; F7 -> hunts #4 and #5 stopped at 0.00 s on
    the cached answer (their clock restarted at 0, < next_t) with nothing on screen."""
    lie = _lie()
    none, game = cv2.imread(str(FX / "lie_detector_none.jpg")), cv2.imread(str(FX / "lie_detector_game.jpg"))
    assert lie.check(game, 3283.0)[0] is True
    assert lie.check(none, 0.0)[0] is False                    # next hunt, clock back at 0: looks again


def test_lie_detector_on_its_thread_answers_a_look_later_and_never_blocks():
    lie = _lie(background=True)
    none, game = cv2.imread(str(FX / "lie_detector_none.jpg")), cv2.imread(str(FX / "lie_detector_game.jpg"))
    assert lie.check(game, 10.0)[0] is False                   # the look started on the thread
    lie.pending.result()
    assert lie.check(none, 10.1)[0] is True                    # its answer (about the frame it looked at)
    lie.check(none, 10.0 + lie.every_s)                        # a new look at a clean frame
    lie.pending.result()
    assert lie.check(none, 10.1 + lie.every_s)[0] is False
    lie.check(game, 20.0)
    lie.pending.result()
    assert lie.check(game, 20.05)[0] is True
    assert lie.check(none, 0.0)[0] is False                    # a new hunt: the old 'on screen' is dropped


def test_a_mob_up_a_gentle_slope_far_away_is_reachable():
    """East Rocky Mountain I (serve 2026-11-01 22:27): Snails / Dark Stumps up the slope at the screen's left edge,
    60-80 px above our feet and 500-900 px away, were never targeted (band 75 px, same level +-35)."""
    from maplebot.config import Config
    from maplebot.perception.perceiver import reachable_level
    z = Config().zones
    feet = 579
    up70 = (100, feet - 70 - 34, 35, 34)                         # bottom 70 px above our feet
    args = (feet, z.same_level, z.step_down)
    assert not reachable_level(up70, *args)                      # the old rule: another platform
    assert reachable_level(up70, *args, -600, z.climb_slope, z.climb_max)      # far: a walkable rise
    assert not reachable_level(up70, *args, -120, z.climb_slope, z.climb_max)  # close: a ledge over us
    up120 = (100, feet - 120 - 34, 35, 34)
    assert not reachable_level(up120, *args, -900, z.climb_slope, z.climb_max)  # too high: needs a jump/rope
    assert reachable_level((100, feet + 50 - 34, 35, 34), *args, -10, z.climb_slope, z.climb_max)  # step down: as before


def test_a_new_max_needs_two_reads_and_a_covered_hud_keeps_the_last(monkeypatch):
    from maplebot.perception.perceiver import Perceiver
    p = Perceiver.__new__(Perceiver)
    p.new_max = {}
    reads = iter([(700, 783), (701, 7831), (700, 783), None, (650, 800), (650, 800)])
    monkeypatch.setattr(hud, "read_pair", lambda frame, span: next(reads))
    last = None
    seen = []
    for _ in range(6):
        last = p._pair(None, "hp", hud.HP_TEXT, last)
        seen.append(last)
    assert seen == [(700, 783), (700, 783), (700, 783), (700, 783), (700, 783), (650, 800)]
