"""The Lie Detector look on the GPU (PLAN-perception.md step 2.8): cv2's TM_CCOEFF_NORMED scores and places."""
from pathlib import Path

import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures"
ASSETS = ROOT / "assets"


def _tpls():
    from maplebrain.perception.liedetector import NAMES
    return [np.load(ASSETS / n) for n in NAMES]


def _cpu(gray, tpls):
    return [cv2.minMaxLoc(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED))[1:4:2] for t in tpls]


def _up(frame):
    return torch.from_numpy(np.ascontiguousarray(frame)).cuda()


def test_gpu_grey_is_cv2s_bit_for_bit():
    from maplebrain.perception.liedetector import GpuLieLook
    look = GpuLieLook(_tpls(), torch.device("cuda"))
    frame = np.random.default_rng(1).integers(0, 256, (768, 1366, 3), dtype=np.uint8)
    assert np.array_equal(look.gray(_up(frame)).cpu().numpy().astype(np.uint8),
                          cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))


@pytest.mark.parametrize("name", ["lie_detector_game.jpg", "lie_detector_panel.jpg", "lie_detector_blue_game.jpg",
                                  "lie_detector_question.jpg", "lie_detector_none.jpg", "perf_ant4/022.webp"])
def test_gpu_scores_and_places_are_cv2s(name):
    from maplebrain.perception.liedetector import GpuLieLook
    tpls = _tpls()
    frame = cv2.imread(str(FX / name))
    if frame.shape[:2] != (768, 1366):
        frame = cv2.resize(frame, (1366, 768), interpolation=cv2.INTER_AREA)
    gpu = {j: (s, loc) for s, loc, j in GpuLieLook(tpls, torch.device("cuda")).looks(_up(frame))}
    for j, (s, loc) in enumerate(_cpu(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), tpls)):
        assert abs(gpu[j][0] - s) < 1e-4
        if s >= 0.75:
            assert gpu[j][1] == loc


def test_flat_and_noisy_frames_follow_cv2s_rule_for_flat_windows():
    """Sky / plain walls: windows with (near) no variance - cv2 gives 0 / +-1 there, not noise over noise."""
    from maplebrain.perception.liedetector import GpuLieLook
    tpls = _tpls()
    rng = np.random.default_rng(3)
    frame = np.full((768, 1366, 3), 90, np.uint8)
    frame[:, 700:] = rng.integers(0, 256, (768, 666, 3), dtype=np.uint8)
    frame[300:400, 100:400] = 200
    t = tpls[1]
    frame[500:500 + t.shape[0], 900:900 + t.shape[1]] = t[..., None]           # a title on noise
    gpu = {j: (s, loc) for s, loc, j in GpuLieLook(tpls, torch.device("cuda")).looks(_up(frame))}
    for j, (s, loc) in enumerate(_cpu(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), tpls)):
        assert abs(gpu[j][0] - s) < 1e-4
    assert gpu[1][1] == (900, 500) and gpu[1][0] > 0.999


def test_check_looks_on_the_gpu_frame_now_and_throttles_like_the_thread():
    from maplebrain.perception.liedetector import LieDetector
    lie = LieDetector(_tpls(), background=True)
    lie.use_gpu(torch.device("cuda"))
    none, game = cv2.imread(str(FX / "lie_detector_none.jpg")), cv2.imread(str(FX / "lie_detector_game.jpg"))
    none, game = (cv2.resize(f, (1366, 768), interpolation=cv2.INTER_AREA) for f in (none, game))
    assert lie.check(none, 0.0, frame_u8=_up(none))[0] is False
    assert lie.check(game, 0.1, frame_u8=_up(game))[0] is False               # not due yet
    seen, s, _ = lie.check(game, 0.1 + lie.every_s, frame_u8=_up(game))       # this frame, no thread
    assert seen and s > 0.9 and lie.pending is None
    assert lie.check(none, 0.0, frame_u8=_up(none))[0] is False               # a new hunt: looks again now
    assert lie.check(game, 5.0)[0] is False                                   # no GPU frame: the thread, a tick late
    lie.pending.result()
    assert lie.check(game, 5.05)[0] is True
