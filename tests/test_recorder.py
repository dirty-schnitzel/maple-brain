import json

import cv2
import numpy as np

from maplebrain.perception.perceiver import Observation
from maplebrain.runtime.recorder import Recorder


def _record(tmp_path, **kw):
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (768, 1366, 3), dtype=np.uint8)
    rec = Recorder(tmp_path, every=1, **kw)
    rec.tick(frame, Observation(t=0.0), [], "LOCAL", {})
    rec.close()
    tick = json.loads((tmp_path / "ticks.jsonl").read_text().splitlines()[0])
    return frame, tick, cv2.imread(str(tmp_path / "frames" / tick["frame"]))


def test_png_frames_are_the_captured_pixels_exactly(tmp_path):
    """--frames-png (reference recordings): JPEG 92 moves most sprite pixels by more than 4 levels."""
    frame, tick, saved = _record(tmp_path, png=True)
    assert tick["frame"] == "000001.png" and (saved == frame).all()


def test_frames_are_jpeg_by_default(tmp_path):
    frame, tick, saved = _record(tmp_path)
    assert tick["frame"] == "000001.jpg" and saved.shape == frame.shape
