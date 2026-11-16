import numpy as np

from maplebrain.capture import game_columns, normalize, picture


def _screen(w=3440, h=1440):
    raw = np.zeros((h, w, 3), np.uint8)
    gw = round(h * 1366 / 768)                          # 2561: the game, pillarboxed in the middle
    x0 = (w - gw) // 2
    raw[:, x0:x0 + gw] = 90
    return raw, x0, gw


def test_pillarboxed_game_is_found():
    raw, x0, gw = _screen()
    assert game_columns(raw) == (x0, x0 + gw)


def test_cursor_in_the_black_bar_does_not_widen_the_crop():
    """pkg_sight6: something small lit in a bar at startup widened the crop ~34 px -> frame squeezed 1.3 %,
    quickslots read 13 px off, the HP potions looked gone and the bot stopped."""
    raw, x0, gw = _screen()
    raw[700:730, x0 - 34:x0 - 20] = 255                 # a mouse cursor in the left bar
    assert game_columns(raw) == (x0, x0 + gw)


def test_dark_game_edge_still_gives_the_full_width_centred():
    raw, x0, gw = _screen()
    raw[:, x0:x0 + 40] = 0                              # a dark cave wall along the game's left edge
    assert game_columns(raw) == (x0, x0 + gw)


def test_full_width_game_without_bars():
    raw = np.full((768, 1366, 3), 90, np.uint8)
    assert game_columns(raw) == (0, 1366)


def test_a_dark_edge_column_in_the_native_window_does_not_move_the_crop():
    """2026-11-16, Ant Tunnel IV + Dangerous Steam at native: the game's leftmost column was dark, the crop became
    (1, 1367) - the whole picture 1 px left of its place, the last column from outside the window."""
    raw = np.full((768, 1366, 3), 90, np.uint8)
    raw[:, 0] = 0
    assert game_columns(raw) == (0, 1366)
    raw[:, :2] = 0
    raw[:, -1] = 0
    assert game_columns(raw) == (0, 1366)


def test_a_native_1366x768_picture_is_not_resized():
    """The game windowed at 1366x768 (PLAN-perception.md): the frame is the game's own pixels, untouched."""
    rng = np.random.default_rng(0)
    raw = rng.integers(0, 255, (768, 1366, 3), dtype=np.uint8)
    out = normalize(raw)
    assert out is raw                                    # dxcam's frame: contiguous, not even copied
    view = np.dstack([raw, raw[:, :, :1]])[:, :, :3]     # mss: BGRA grab, the first 3 channels = a view
    out = normalize(view)
    assert out.flags["C_CONTIGUOUS"] and out.shape == (768, 1366, 3) and (out == raw).all()


def test_a_larger_picture_is_still_resized_to_1366x768():
    assert normalize(np.full((1080, 1920, 3), 90, np.uint8)).shape == (768, 1366, 3)


def test_the_log_line_says_the_size_and_whether_it_is_resized():
    assert picture((0, 1366), 768, "dxcam") == "game picture at x (0, 1366), 1366x768 native (no resize) (dxcam)"
    assert picture((0, 1920), 1080, "dxcam") == "game picture at x (0, 1920), 1920x1080 -> resized to 1366x768 (dxcam)"
    assert "resized" in picture((0, 1366), 767, "mss")   # one row short = NOT native: say so
    assert picture((0, 1366), None, "mss") == "game picture at x (0, 1366) (mss)"
