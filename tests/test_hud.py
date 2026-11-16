

def test_exp_points_is_none_without_the_hud_text():
    import numpy as np
    from maplebrain.perception import hud
    assert hud.exp_points(np.zeros((768, 1366, 3), np.uint8)) is None


def test_minimap_dot_ignores_a_party_dots_yellowish_rim_in_a_raw_frame():
    """rain2 live (raw frames, not JPEG): the party members' orange dots (hue 18-19) have rims up to hue ~20-22 big
    enough to pass as a 2nd 'dot' -> only 23 of 1903 ticks had a position. Ours is hue 26-28."""
    import cv2
    import numpy as np
    from maplebrain.perception import hud
    hsv = np.zeros((768, 1366, 3), np.uint8)
    hsv[:, :] = (110, 200, 90)                                         # dark blue minimap background
    cv2.circle(hsv, (100, 100), 3, (21, 230, 240), -1)                 # party dot: yellowish rim (raw frame)
    cv2.circle(hsv, (100, 100), 1, (18, 240, 250), -1)                 # ...orange core
    cv2.circle(hsv, (60, 100), 3, (27, 230, 250), -1)                  # us
    frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    dot = hud.minimap_dot(frame)
    assert dot is not None and abs(dot[0] - (60 - hud.MINIMAP_BOX[0])) < 1


def test_exp_points_reads_the_native_1366x768_window():
    """2026-11-16, the game windowed at native size (no resize): the text sits 1 px left of where the stretched
    windows put it; 0 of 11,576 ticks were read. 14 numbers checked by eye, every digit (PNG frames)."""
    import numpy as np
    from pathlib import Path
    from maplebrain.perception import hud
    d = np.load(Path(__file__).parent / "fixtures" / "exp_points_native.npz")
    x0, y0 = hud.EXP_TEXT
    for strip, label in zip(d["strips"], d["labels"]):
        frame = np.zeros((768, 1366, 3), np.uint8)
        frame[y0 - 2:y0 + 9, x0 - 4:x0 + 64] = strip
        assert hud.exp_points(frame) == int(label)


def test_hud_text_cache_reads_what_the_readers_read():
    """2.9a: HudText re-reads HP / MP / EXP only when their crop changed - on every frame of a mixed sequence (the
    perf fixture's fight, repeats, frames with other numbers in between) it returns exactly what read_pair /
    exp_points read, and one changed pixel inside a crop forces a re-read while one outside doesn't."""
    import cv2
    from pathlib import Path
    from maplebrain.perception import hud
    fx = Path(__file__).parent / "fixtures"
    seq = [cv2.imread(str(p)) for p in sorted((fx / "perf_ant4").glob("*.webp"))]
    seq = seq[:10] + seq[30:40] + seq[10:30] + seq[40:][::-1] + seq[:3]           # repeats + jumps between numbers
    seq = [f for f in seq if f is not None and f.shape[:2] == (768, 1366)]
    assert len(seq) >= 30
    ht = hud.HudText()
    for f in seq:
        assert ht.read(f) == (hud.read_pair(f, hud.HP_TEXT), hud.read_pair(f, hud.MP_TEXT), hud.exp_points(f))
    assert ht.hits > 0 and ht.reads > 0
    f = seq[0].copy()
    ht.read(f)
    n = ht.reads
    f[hud.NUM_Y + 3, hud.HP_TEXT[0] + 20] ^= 255                   # inside HP's crop: HP read again, not MP / EXP
    assert ht.read(f) == (hud.read_pair(f, hud.HP_TEXT), hud.read_pair(f, hud.MP_TEXT), hud.exp_points(f))
    assert ht.reads == n + 1
    f[hud.NUM_Y - 1, hud.HP_TEXT[0] + 20] ^= 255                   # a row above: nothing read again
    ht.read(f)
    assert ht.reads == n + 1
