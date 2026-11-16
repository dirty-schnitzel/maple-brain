"""Perception regressions on real frames from the live runs (each one broke an earlier version)."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebrain.perception import hud
from maplebrain.perception.selfpos import find_self

FX = Path(__file__).parent / "fixtures"
TAG = np.load(Path(__file__).parents[1] / "assets" / "self_tag_gray.npy")      # the bot's own (1:1 native)


# ---------------------------------------------------------------- own position
# ---------------------------------------------------------------- HUD
# ---------------------------------------------------------------- perceiver + motion look
# ---------------------------------------------------------------- mob library
def test_mobs_a_step_below_us_count_but_not_ones_above():
    """pkg_swing1 start: we stood on a small step; snails on the ground ~60 px below were filtered out as 'not on
    our ground line'. Walking off a step is free; going up needs a jump."""
    from maplebrain.perception.perceiver import reachable_level
    feet = 545
    assert reachable_level((900, 560, 40, 26), feet, 18, 80)               # bottom 586: 41 px below
    assert reachable_level((900, 579, 40, 26), feet, 18, 80)               # 60 px below
    assert not reachable_level((900, 400, 40, 26), feet, 18, 80)           # 119 px above: a ledge / ghost
    assert not reachable_level((900, 640, 40, 26), feet, 18, 80)           # 121 px below: another floor
    assert reachable_level((900, 510, 40, 26), feet, 18, 80)               # on our line


# ---------------------------------------------------------------- own tag cut off by the screen edge
# ---------------------------------------------------------------- potions: HP/MP bars and the quickslots
# ---------------------------------------------------------------- the game's Lie Detector (anti-bot test)
def _lie(background=False):
    from maplebrain.perception.liedetector import LieDetector
    return LieDetector.load(FX, background=background)


def test_lie_detector_announcement_panel_is_seen():
    """pkg_potions1 52.4 s: '5 sec until the Lie Detector mini-game starts' panel, bottom right. A stretched FHD
    capture saved as JPEG: the native 1:1 title (2026-11-16) scores 0.79 here (the old template cut from this very
    frame: 0.89); at native the client's panel scores >= 0.97 (the test below)."""
    s, loc = _lie().score(cv2.imread(str(FX / "lie_detector_panel.jpg")))
    assert s >= 0.78 and loc[0] > 1000


def test_lie_detector_mini_game_window_is_seen():
    s, loc = _lie().score(cv2.imread(str(FX / "lie_detector_game.jpg")))     # stretched JPEG too
    assert s >= 0.93 and 500 < loc[0] < 800


@pytest.mark.parametrize("name", ["lie_client_standby.png", "lie_client_game.png", "lie_client_sound.png"])
def test_the_clients_own_lie_detector_windows_are_seen_at_native(name):
    """The client's windows (AntiMacro.img, tools/perc/ld/cut_native.py) alpha-blended 1:1 onto native frames,
    as the game draws them at 1366x768: the title templates are cut from these pictures (graded over 8641 native
    frames: >= 0.970), at any place on the screen; the plain frames stay far below the bar."""
    win = cv2.imread(str(FX / name), cv2.IMREAD_UNCHANGED)
    a = win[..., 3:4].astype(np.float32) / 255
    for frame_name, (x, y) in (("000.webp", (1080, 480)), ("022.webp", (400, 200)), ("044.webp", (0, 0))):
        frame = cv2.imread(str(FX / "perf_ant4" / frame_name))
        assert _lie().score(frame)[0] < 0.6
        h, w = win.shape[:2]
        x, y = min(x, frame.shape[1] - w), min(y, frame.shape[0] - h)          # the whole window on the screen
        frame[y:y + h, x:x + w] = np.round(win[..., :3] * a + frame[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)
        s, loc = _lie().score(frame)
        assert s >= 0.95 and x <= loc[0] < x + w and y <= loc[1] < y + h


@pytest.mark.parametrize("name", ["lie_detector_blue_panel.jpg", "lie_detector_blue_game.jpg"])
def test_the_blue_lie_detector_is_seen_too(name):
    """pkg_sight5 55.5-82.3 s: a second kind of Lie Detector (blue title bar, 'The Lie Detector Mini-game': a
    panel 'go to a safe place', then a mouse game 'follow the fading figure'). Not recognized: the bot hunted on
    through the whole test while the user did it with the mouse."""
    assert _lie().seen(cv2.imread(str(FX / name)))


def test_the_quiz_lie_detector_is_seen_and_ships_with_the_bot():
    """The user's screenshot 2026-11-02 14:07: a third kind - a translucent blue box in the centre, 'Question in 10
    seconds' / 'Answer within 10 seconds' (a quiz). No window title, so it matches the words 'Question in'."""
    from maplebrain.perception.liedetector import LieDetector
    from maplebrain.runtime.runner import ASSETS
    frame = cv2.imread(str(FX / "lie_detector_question.jpg"))
    s, loc = _lie().score(frame)
    assert s >= 0.9 and 600 < loc[0] < 700
    assert LieDetector.load(ASSETS).seen(frame)


def test_the_blue_lie_detector_template_ships_with_the_bot():
    from maplebrain.perception.liedetector import LieDetector
    from maplebrain.runtime.runner import ASSETS
    assert LieDetector.load(ASSETS).seen(cv2.imread(str(FX / "lie_detector_blue_game.jpg")))


def test_lie_detector_not_seen_on_a_normal_frame():
    assert not _lie().seen(cv2.imread(str(FX / "lie_detector_none.jpg")))
    assert not _lie().seen(cv2.imread(str(FX / "lie_detector_blue_none.jpg")))   # 0.6 s before it appeared
    assert not _lie().seen(cv2.imread(str(FX / "sprites_six_unhit.jpg")))


def test_lie_detector_bar_is_lowered_for_the_native_window_and_native_frames_stay_clear_of_it():
    """2026-11-16 (the user's call): 0.80 -> 0.75 until the templates are re-cut 1:1 at native 1366x768 (they are
    from stretched windows: a real one is expected ~0.85 there). Best false score on native frames of 7 maps: 0.668."""
    lie = _lie()
    assert lie.min_score == 0.75
    for name in ("000.webp", "022.webp", "044.webp"):                   # native fight frames (Ant Tunnel IV)
        s, _ = lie.score(cv2.imread(str(FX / "perf_ant4" / name)))
        assert s < 0.70


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
    from maplebrain.config import Config
    from maplebrain.perception.perceiver import reachable_level
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


def test_a_new_max_needs_two_reads_and_a_covered_hud_keeps_the_last():
    from maplebrain.perception.perceiver import Perceiver
    p = Perceiver.__new__(Perceiver)
    p.new_max = {}
    reads = [(700, 783), (701, 7831), (700, 783), None, (650, 800), (650, 800)]   # FrameFacts.hp per frame
    last = None
    seen = []
    for r in reads:
        last = p._pair(r, "hp", last)
        seen.append(last)
    assert seen == [(700, 783), (700, 783), (700, 783), (700, 783), (700, 783), (650, 800)]


def test_the_ui_mask_takes_the_minimap_window_as_measured():
    """The minimap window's size differs per map (Line 1 <Area 1> 277x152, Transfer Area 175x201; UI_RECTS assumed
    215x195): measured by the locator (find_window = its inside), the frame adds 5 px right and 14 px below."""
    from maplebrain.nav.localize import Window, find_window
    assert hud.minimap_rect(Window(6, 72, 266, 66)) == (0, 0, 277, 152)
    m = hud.ui_mask((768, 1366, 3), (0, 0, 277, 152))
    assert m[151, 276] == 0 and m[152, 276] == 1 and m[100, 277] == 1 and m[740, 1000] == 0
    d = hud.ui_mask((768, 1366, 3))
    assert d[100, 220] == 1 and d[190, 100] == 0                     # the default: UI_RECTS' 215x195
    f = cv2.imread(str(Path(__file__).parent / "fixtures" / "perf_ant4" / sorted(
        p.name for p in (Path(__file__).parent / "fixtures" / "perf_ant4").glob("*.webp"))[0]))
    w = find_window(f)                                                # Ant Tunnel IV
    assert w is not None and hud.minimap_rect(w)[2:] in ((229, 198), (230, 198))


def test_the_gpu_tag_look_finds_what_the_cpu_look_finds():
    """Step 2.7b: selfpos.GpuTagLook (whole frame, on the GPU) + the CPU's near search at its best place = the CPU's
    whole-frame look: same place, score within 0.002 (perf fixture: 45 native frames, our tag on most)."""
    torch = pytest.importorskip("torch")
    from maplebrain.perception.selfpos import GpuTagLook
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    look = GpuTagLook(TAG, dev)
    fx = Path(__file__).parent / "fixtures" / "perf_ant4"
    n = found = 0
    for p in sorted(fx.glob("*.webp"))[::3]:
        f = cv2.imread(str(p))
        cpu = find_self(f, TAG, min_score=0.66, edges=False)
        _, x, y = look.look(torch.from_numpy(f).to(dev), hud.ui_mask(f.shape))
        gpu = find_self(f, TAG, near=(x + TAG.shape[1] / 2, y), radius=40, min_score=0.66, edges=False)
        assert (cpu is None) == (gpu is None), (p.name, cpu, gpu)
        assert cpu is None or (cpu[:4] == gpu[:4] and abs(cpu[4] - gpu[4]) < 0.002), (p.name, cpu, gpu)   # (the near
        # search high-passes a crop: its blur reflects at the crop's edges - 1e-4 off, as today's near search)
        n, found = n + 1, found + (cpu is not None)
    assert found >= n // 2
