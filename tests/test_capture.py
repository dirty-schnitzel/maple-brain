import numpy as np

from maplebrain.capture import game_columns


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


def test_the_game_window_is_its_own_picture(monkeypatch):
    from maplebrain import capture
    monkeypatch.setattr(capture, "_class", lambda h: "MapleStoryClass")
    assert capture.picture_window(1234) == 1234


def test_unknown_window_kind_is_refused():
    import pytest
    from maplebrain import capture
    with pytest.raises(ValueError):
        capture.find_window("virtualbox")


def test_vmware_picture_is_the_largest_visible_guest_display_on_this_pc():
    """Live check when VMware Workstation runs a VM on this PC (2026-11-10: MKSEmbedded 2143x1164 inside
    VMUIFrame); skipped otherwise."""
    import pytest
    from maplebrain import capture
    frame = capture.find_window("vmware")
    if not frame:
        pytest.skip("no VMware Workstation window")
    view = capture.picture_window(frame)
    if not view:
        pytest.skip("VMware shows no running VM")
    assert capture._class(view) == capture.VMWARE_VIEW
    box = capture.client_box(view)
    assert box["width"] > 600 and box["height"] > 400
