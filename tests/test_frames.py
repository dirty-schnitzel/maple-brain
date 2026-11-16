"""tools/perc/frames.py: a recording's frames with the capture's column error undone (RUN/xshift.txt)."""
import importlib.util
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("frames", ROOT / "tools" / "perc" / "frames.py")
fr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fr)


def test_a_marked_recording_is_read_with_its_picture_moved_back(tmp_path):
    """2026-11-16: Ant Tunnel IV + Dangerous Steam were captured at columns (1, 1367): every pixel 1 px left of its
    place. xshift.txt = 1 -> `read` puts client column j back at frame column j; column 0 repeats column 1."""
    rng = np.random.default_rng(0)
    game = rng.integers(0, 255, (40, 60, 3), dtype=np.uint8)            # the client area's own pixels
    captured = np.concatenate([game[:, 1:], np.full((40, 1, 3), 7, np.uint8)], axis=1)   # + a column from outside
    (tmp_path / "frames").mkdir()
    cv2.imwrite(str(tmp_path / "frames" / "000003.png"), captured)
    assert fr.xshift(tmp_path) == 0 and (fr.read(tmp_path, "000003.png") == captured).all()
    (tmp_path / "xshift.txt").write_text("1\n")
    got = fr.read(tmp_path, "000003.png")
    assert fr.xshift(tmp_path) == 1 and got.shape == game.shape
    assert (got[:, 1:] == game[:, 1:]).all() and (got[:, 0] == game[:, 1]).all()
    assert fr.read(tmp_path, "nope.png") is None
