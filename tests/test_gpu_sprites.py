"""GPU full-screen sprite detector (perception rework, 2026-11-03). Skipped without torch or the map assets."""
from pathlib import Path

import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")

from maplebrain.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MCW = ROOT / "assets" / "mcw"
FX = Path(__file__).parent / "fixtures"
RAIN = 10001070

pytestmark = pytest.mark.skipif(not (MCW / "maps" / str(RAIN) / "map.json").exists(), reason="needs map 10001070")


@pytest.fixture(scope="module")
def det():
    return GpuSpriteDetector.for_map(RAIN, MCW)


def test_half_size_on_the_gpu_is_opencvs_inter_area_to_the_bit(det):
    """find() halves the uploaded frame on the GPU instead of cv2.resize + a second upload (PLAN-perception.md
    step 2): the picture the whole-screen search sees must stay the same, pixel for pixel."""
    frames = [cv2.imread(str(p)) for p in sorted((FX / "perf_ant4").glob("*.webp"))[::9]]
    rng = np.random.default_rng(1)
    frames.append(rng.integers(0, 256, (768, 1366, 3), dtype=np.uint8))             # every rounding case
    for f in frames:
        play = f[:700]
        ref = cv2.resize(play, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        got = det._half(det.upload(play)).permute(1, 2, 0).byte().cpu().numpy()
        assert np.array_equal(got, ref)


def test_flat_areas_are_not_mobs(det):
    """A plain sky-blue frame: noise over ~zero variance once scored 32 and gave 10k peaks (23 s a frame)."""
    frame = np.full((768, 1366, 3), (235, 170, 90), np.uint8)
    frame += np.random.default_rng(0).integers(0, 2, frame.shape, dtype=np.uint8)
    assert det.find(frame) == []


