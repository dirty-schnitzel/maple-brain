"""tools/self_tag.py: our tag is found by the HUD's name (same font) - JenkinsJob's recorded frames as reference."""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from self_tag import pick_tag  # noqa: E402

from maplebrain.perception.selfpos import find_self  # noqa: E402

FX = Path(__file__).parent / "fixtures"
OLD = np.load(ROOT / "assets" / "self_tag_gray.npy")


def test_the_hud_name_finds_our_tag_where_the_old_template_does():
    for name in ("look_snails/f087.png", "self_normal.png", "exp_88_24.jpg", "ribbon_pig_hit.jpg"):
        frame = cv2.imread(str(FX / name))
        x, y, w, h = pick_tag(frame)
        s = find_self(frame, OLD)
        assert abs(x - s[0]) <= 4 and abs(y - s[1]) <= 3 and h == 17, name


def test_a_tag_cut_by_it_works_as_the_bots_template():
    frame = cv2.imread(str(FX / "look_snails" / "f087.png"))
    x, y, w, h = pick_tag(frame)
    tag = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[y:y + h, x:x + w]
    other = cv2.imread(str(FX / "look_snails" / "f090.png"))
    hit = find_self(other, tag)
    s = find_self(other, OLD)
    assert hit is not None and hit[4] > 0.8 and abs(hit[0] - s[0]) <= 4
