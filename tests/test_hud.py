

def test_exp_points_reads_every_labelled_hud_number():
    """perion6: the EXP bar moves 1 px per ~15 points (a Stump gives ~3) - 16 EXP gains in 3 min, 5 'kills'.
    The HUD text 'EXP. 885 [51.57%]' is exact: 36 labelled numbers from recorded frames (every digit)."""
    import numpy as np
    from pathlib import Path
    from maplebot.perception import hud
    d = np.load(Path(__file__).parent / "fixtures" / "exp_points.npz")
    x0, y0 = hud.EXP_TEXT
    for strip, label in zip(d["strips"], d["labels"]):
        frame = np.zeros((768, 1366, 3), np.uint8)
        frame[y0 - 2:y0 + 9, x0 - 4:x0 + 50] = strip
        assert hud.exp_points(frame) == int(label)


def test_exp_points_is_none_without_the_hud_text():
    import numpy as np
    from maplebot.perception import hud
    assert hud.exp_points(np.zeros((768, 1366, 3), np.uint8)) is None


def test_exp_points_reads_thousands_with_a_comma():
    """perion7: from 1,000 the HUD writes 'EXP. 1,012 [58.97%]' - the old reader saw nothing past 996, so 14 of
    our kills were logged as 'killed by someone else'. The ',' takes 5 px; labels checked by eye (1,012 / 1,052)."""
    import numpy as np
    from pathlib import Path
    from maplebot.perception import hud
    d = np.load(Path(__file__).parent / "fixtures" / "exp_points_comma.npz")
    x0, y0 = hud.EXP_TEXT
    for strip, label in zip(d["strips"], d["labels"]):
        frame = np.zeros((768, 1366, 3), np.uint8)
        frame[y0 - 2:y0 + 9, x0 - 4:x0 + 64] = strip
        assert hud.exp_points(frame) == int(label)


def test_minimap_dot_with_party_members_on_the_map():
    """rain1 (2026-11-02, in a party): the party members' orange minimap dots leak 2-5 px of 'yellow' - the
    'exactly one dot' rule saw two and the bot had no minimap position for the whole 3-min run. Ours is 16-24 px."""
    import cv2
    import numpy as np
    from pathlib import Path
    from maplebot.perception import hud
    frame = np.zeros((768, 1366, 3), np.uint8)
    frame[40:200, 0:260] = cv2.imread(str(Path(__file__).parent / "fixtures" / "minimap_party_rain.png"))
    dot = hud.minimap_dot(frame)
    assert dot is not None and abs(dot[0] - 94.4) < 1 and abs(dot[1] - 38.4) < 1


def test_minimap_dot_ignores_a_party_dots_yellowish_rim_in_a_raw_frame():
    """rain2 live (raw frames, not JPEG): the party members' orange dots (hue 18-19) have rims up to hue ~20-22 big
    enough to pass as a 2nd 'dot' -> only 23 of 1903 ticks had a position. Ours is hue 26-28."""
    import cv2
    import numpy as np
    from maplebot.perception import hud
    hsv = np.zeros((768, 1366, 3), np.uint8)
    hsv[:, :] = (110, 200, 90)                                         # dark blue minimap background
    cv2.circle(hsv, (100, 100), 3, (21, 230, 240), -1)                 # party dot: yellowish rim (raw frame)
    cv2.circle(hsv, (100, 100), 1, (18, 240, 250), -1)                 # ...orange core
    cv2.circle(hsv, (60, 100), 3, (27, 230, 250), -1)                  # us
    frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    dot = hud.minimap_dot(frame)
    assert dot is not None and abs(dot[0] - (60 - hud.MINIMAP_BOX[0])) < 1
