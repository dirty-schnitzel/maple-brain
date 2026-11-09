"""Things that move between frames of a short still look, with camera drift cancelled."""
import cv2
import numpy as np

from ..geometry import overlaps
from .hud import ui_mask


def _gray(f):
    return cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)


def aligned_diff(a, b):
    """|b - a| after shifting a by the camera motion between them; also the alignment confidence."""
    ga, gb = _gray(a), _gray(b)
    (dx, dy), resp = cv2.phaseCorrelate(ga, gb)
    ga = cv2.warpAffine(ga, np.float32([[1, 0, dx], [0, 1, dy]]), (ga.shape[1], ga.shape[0]),
                        borderMode=cv2.BORDER_REPLICATE)
    return np.abs(gb - ga), float(resp)


def _blobs(diff, mask, thresh=25):
    on = ((diff > thresh) & (mask > 0)).astype(np.uint8)
    on = cv2.morphologyEx(on, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    on = cv2.morphologyEx(on, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(on)
    return [tuple(int(v) for v in st[i][:4]) for i in range(1, n)
            if st[i][4] >= 60 and 10 <= st[i][2] <= 160 and 8 <= st[i][3] <= 140]


def moving_blobs(frames) -> tuple[list, float]:
    """Blobs that changed in at least two consecutive frame pairs, and the worst alignment confidence."""
    mask = ui_mask(frames[0].shape)
    per_pair, resps = [], []
    for a, b in zip(frames, frames[1:]):
        d, r = aligned_diff(a, b)
        resps.append(r)
        per_pair.append(_blobs(d, mask))
    if len(per_pair) < 2:
        return [], min(resps, default=0.0)
    keep = [b for b in per_pair[-1] if any(overlaps(b, p) for p in per_pair[-2])]
    if len(per_pair) > 2:
        for b in per_pair[-2]:
            if any(overlaps(b, p) for p in per_pair[-3]) and not any(overlaps(b, k) for k in keep):
                keep.append(b)
    return keep, min(resps)
