"""tools/perc/native_check.py: the 1:1 measurement itself (the detector part needs the GPU + a recording)."""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("native_check", ROOT / "tools" / "perc" / "native_check.py")
nc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nc)


def _scene():
    rng = np.random.default_rng(3)
    frame = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
    sprite = rng.integers(0, 255, (50, 60, 3), dtype=np.uint8)
    mask = np.zeros((50, 60), np.uint8)
    mask[5:45, 8:52] = 1
    return frame, sprite, mask


def _draw(frame, sprite, mask, x, y):
    out = frame.copy()
    out[y:y + 50, x:x + 60][mask.astype(bool)] = sprite[mask.astype(bool)]
    return out


def test_a_sprite_drawn_1_to_1_is_fully_within_4_levels_and_found_one_pixel_off():
    frame, sprite, mask = _scene()
    r = nc.measure(_draw(frame, sprite, mask, 100, 120), sprite, mask, 100, 120)
    assert (r["dx"], r["dy"]) == (0, 0) and r["in"][4] == 1.0 and r["inner"][4] == 1.0 and r["shift"] == [0, 0, 0]
    r = nc.measure(_draw(frame, sprite, mask, 101, 119), sprite, mask, 100, 120)     # the detector 1 px off
    assert (r["dx"], r["dy"]) == (1, -1) and r["in"][4] == 1.0


def test_a_brightness_shift_and_a_blur_are_told_apart_from_1_to_1():
    import cv2
    frame, sprite, mask = _scene()
    drawn = _draw(frame, sprite, mask, 100, 120)
    lighter = np.clip(drawn.astype(int) + 10, 0, 255).astype(np.uint8)
    r = nc.measure(lighter, sprite, mask, 100, 120)
    assert r["in"][4] < 0.2 and r["in"][16] > 0.95 and all(abs(s - 10) <= 1 for s in r["shift"])
    r = nc.measure(cv2.GaussianBlur(drawn, (3, 3), 0), sprite, mask, 100, 120)       # resampled: noise sprite blurred
    assert r["in"][4] < 0.5
    assert nc.pooled([{"in": {4: 1.0}, "n": 10}, {"in": {4: 0.0}, "n": 30}], "in", 4) == 0.25
