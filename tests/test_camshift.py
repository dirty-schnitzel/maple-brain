import cv2
import numpy as np

from maplebrain.nav.navmap import NavMap, Platform, Seg
from maplebrain.perception.camshift import PlatformShift


def _nav():
    p = Platform(1, [Seg(-200, 400, 2000, 400)])
    q = Platform(2, [Seg(300, 250, 1200, 250)])
    return NavMap({1: p, 2: q})


def _scene(C, rng_bg, rng_fg):
    """Screen 1366x768 for camera C: a background that scrolls at HALF the camera's speed (parallax) with tile
    strips drawn 1:1 under the two platforms."""
    bx = int(C[0] * 0.5) + 400
    img = rng_bg[100:868, bx:bx + 1366].copy()
    for y, x0, x1 in ((400, -200, 2000), (250, 300, 1200)):
        sy = int(y - C[1])
        for sx in range(1366):
            mx = sx + int(C[0])
            if x0 <= mx <= x1:
                img[sy:sy + 30, sx] = rng_fg[y:y + 30, mx + 400]
    return img


def test_platform_shift_follows_the_tiles_not_the_parallax():
    rng = np.random.default_rng(1)
    bg = cv2.GaussianBlur(rng.integers(0, 255, (1000, 3000), dtype=np.uint8), (0, 0), 6)   # soft, like backdrops
    bg = cv2.normalize(bg, None, 0, 255, cv2.NORM_MINMAX)
    fg = rng.integers(0, 255, (500, 3000), dtype=np.uint8)
    ps = PlatformShift(_nav())
    C0, C1 = (0.0, 0.0), (12.0, 0.0)                    # the camera moved 12 px right: scenery 12 px left
    assert ps.update(_scene(C0, bg, fg), C0) is None    # first frame: nothing to compare with
    d = ps.update(_scene(C1, bg, fg), C0, me=(683, 400))
    assert d is not None
    assert abs(d[0] + 12) <= 0.5 and abs(d[1]) <= 0.5   # the background moved only 6: ignored


def test_no_platform_in_view_gives_none():
    ps = PlatformShift(_nav())
    img = np.zeros((768, 1366), np.uint8)
    far = (5000.0, 0.0)
    ps.update(img, far)
    assert ps.update(img, far) is None
