"""Which map are we on? The on-screen minimap matched against every map's miniMap canvas (assets/mcw, downloaded
once with `assets update --all`). Run once per hunt (F7), not per frame.

What the screen shows is not the raw canvas: the game draws it semi-transparent and slightly blurred over a
backdrop (screen ~ 0.45-0.6 x canvas + offset), and canvases are transparent where the map has nothing (~40-50 %;
Henesys Townstreet is one house on a strip). Plain colour error fails, and correlation alone lets a small canvas
match some patch of any minimap. Two cues together:
1. **The window's frame**: the minimap window wraps the canvas - a bright border 1 px outside it on all four sides
   (~230 vs ~70-110 inside; narrow maps sit centred in a wider window, still with a brighter edge beside them).
   Top and bottom must both be bright; left and right on average (markers can sit against one side).
   Every canvas size is tried at every position (box sums); a size fits only where all four edges are bright.
2. **The picture**: canvases of a fitting size are correlated (TM_CCOEFF_NORMED over their opaque pixels, which
   shrugs off the blend's gain/offset) at that spot, +-1 px.
A winner needs a minimum correlation and a lead over any other fitting map, averaged over a few frames
(markers move; a frame with the window covered is skipped). ~0.3 s per frame with all 335 maps.
"""
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .localize import SEARCH

TRIM = 0.03     # share of worst-fitting pixels dropped (markers); offline sweep 0/0.03/0.08/0.15: best margins


@dataclass
class MapMatch:
    map_id: int | None            # None: no clear winner
    score: float = 0.0            # correlation of the winner (or of the best candidate)
    runner_up: int | None = None  # the next fitting map and its score (for the log)
    runner_score: float = 0.0
    origin: tuple | None = None   # screen (x, y) of the canvas' top-left
    why: str = ""                 # why there's no winner
    fits: list = field(default_factory=list)   # [(score, map_id)] of every map whose size fits the frame


@dataclass
class _Canvas:
    bgr: np.ndarray
    mask: np.ndarray              # 3-channel 0/255, opaque pixels
    n: int                        # opaque pixel count


def _canvas(img) -> _Canvas:
    bgr = np.ascontiguousarray(img[..., :3])
    a = img[..., 3] > 0 if img.shape[2] == 4 else np.ones(img.shape[:2], bool)
    return _Canvas(bgr, np.ascontiguousarray(np.repeat(a[..., None].astype(np.uint8) * 255, 3, 2)), int(a.sum()))


def frame_contrast(gray: np.ndarray, w: int, h: int) -> np.ndarray:
    """For every top-left (y, x) of a w x h rectangle: how well it sits in a bright frame - edge contrast = mean
    brightness 1 px outside minus 1 px inside; the weaker of top and bottom, or the sides' average if lower (bright
    markers - portals, players - against one side weaken it: A Split Road's right edge 34 vs ~140 top/bottom).
    Shape (H - h - 1, W - w - 1); index [y - 1, x - 1]."""
    H, W = gray.shape
    if H < h + 2 or W < w + 2:
        return np.full((0, 0), -255.0)
    g = gray.astype(np.float64)
    rs = np.zeros((H, W + 1)); rs[:, 1:] = np.cumsum(g, 1)          # row segment sums: rs[y, x+w] - rs[y, x]
    cs = np.zeros((H + 1, W)); cs[1:] = np.cumsum(g, 0)             # column segment sums
    hseg = (rs[:, w:] - rs[:, :-w]) / w                             # [y, x]: mean of row y over x..x+w-1
    vseg = (cs[h:] - cs[:-h]) / h                                   # [y, x]: mean of column x over y..y+h-1
    ny, nx = H - h - 1, W - w - 1
    ys, xs = slice(1, 1 + ny), slice(1, 1 + nx)
    top = hseg[0:ny, xs] - hseg[ys, xs]
    bottom = hseg[h + 1:h + 1 + ny, xs] - hseg[h:h + ny, xs]
    left = vseg[ys, 0:nx] - vseg[ys, xs]
    right = vseg[ys, w + 1:w + 1 + nx] - vseg[ys, w:w + nx]
    return np.minimum(np.minimum(top, bottom), (left + right) / 2)


def _corr(region, c: _Canvas, x: int, y: int, trim: float = TRIM) -> float:
    """Correlation of the canvas with the screen, top-left within +-1 px of (x, y) in `region`: the spot by masked
    TM_CCOEFF_NORMED, then a trimmed correlation there - fit screen = gain * canvas + offset over the opaque pixels,
    drop the `trim` share that fits worst (player/portal markers, our dot: A Split Road's crowd of red dots took
    the plain score down to 0.51) and correlate the rest. More trim lifts look-alike maps too (East Rocky Mountain
    I vs IV: margin 0.13 at 3 %, 0.06 at 15 %)."""
    h, w = c.bgr.shape[:2]
    y0, x0 = max(y - 1, 0), max(x - 1, 0)
    patch = region[y0:y + h + 1, x0:x + w + 1]
    if patch.shape[0] < h or patch.shape[1] < w:
        return -1.0
    r = np.nan_to_num(cv2.matchTemplate(np.ascontiguousarray(patch), c.bgr, cv2.TM_CCOEFF_NORMED, mask=c.mask),
                      nan=-1.0, posinf=-1.0, neginf=-1.0)
    _, _, _, (dx, dy) = cv2.minMaxLoc(r)
    opaque = c.mask[..., 0] > 0
    a = c.bgr[opaque].astype(np.float64).ravel()
    b = patch[dy:dy + h, dx:dx + w][opaque].astype(np.float64).ravel()
    if a.std() < 1e-6 or b.std() < 1e-6:
        return -1.0
    gain, off = np.polyfit(a, b, 1)
    keep = np.abs(b - (gain * a + off)) <= np.quantile(np.abs(b - (gain * a + off)), 1 - trim)
    if keep.sum() < 50 or a[keep].std() < 1e-6 or b[keep].std() < 1e-6:
        return -1.0
    return float(np.corrcoef(a[keep], b[keep])[0, 1])


class MapIdentifier:
    def __init__(self, canvases: dict[int, np.ndarray], edge: float = 50.0, min_score: float = 0.5,
                 lead: float = 0.05, min_opaque: int = 200):
        """canvases: BGRA (or BGR) pictures by map id. `edge`: a frame edge must be this much brighter outside than
        inside; `min_opaque`: canvases with fewer opaque pixels can't be told apart and are left out."""
        full = {k: _canvas(c) for k, c in canvases.items()}
        self.canvases = {k: c for k, c in full.items() if c.n >= min_opaque}
        self.by_size: dict[tuple, list[int]] = {}
        for k, c in self.canvases.items():
            self.by_size.setdefault((c.bgr.shape[1], c.bgr.shape[0]), []).append(k)
        self.edge, self.min_score, self.lead = edge, min_score, lead

    @classmethod
    def load(cls, root: Path, **kw) -> "MapIdentifier":
        """Every maps/<id>/minimap.png under `root` (assets/mcw)."""
        canvases = {}
        for p in (Path(root) / "maps").glob("*/minimap.png"):
            img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_UNCHANGED)
            if img is not None and img.ndim == 3:
                canvases[int(p.parent.name)] = img
        return cls(canvases, **kw)

    def fits(self, frame) -> dict[int, tuple]:
        """Every map whose canvas size fits a framed window on screen: {map id: (score, screen x, screen y)}."""
        x0, y0, x1, y1 = SEARCH
        region = np.ascontiguousarray(frame[y0:y1, x0:x1])
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        best = {}
        for (w, h), ids in self.by_size.items():
            fc = frame_contrast(gray, w, h)
            if fc.size == 0 or fc.max() < self.edge:
                continue
            for yy, xx in zip(*np.nonzero(fc >= self.edge)):        # usually exactly one spot
                for k in ids:
                    sc = _corr(region, self.canvases[k], xx + 1, yy + 1)
                    if k not in best or sc > best[k][0]:
                        best[k] = (sc, x0 + xx + 1, y0 + yy + 1)
        return best

    def identify(self, frames) -> MapMatch:
        """One frame or a list of them (taken a moment apart): scores averaged over the frames where the window was
        found (a map that doesn't fit in one of them scores 0 there)."""
        if not self.canvases:
            return MapMatch(None, why="no minimaps on disk (assets update --all)")
        if isinstance(frames, np.ndarray):
            frames = [frames]
        per = [f for f in (self.fits(fr) for fr in frames) if f]
        if not per:
            return MapMatch(None, why="no minimap window of a known size (closed or covered?)")
        ids = {k for f in per for k in f}
        ranked = sorted(((sum(f.get(k, (0.0,))[0] for f in per) / len(per), k) for k in ids), reverse=True)
        (s, k), (s2, k2) = ranked[0], (ranked[1] if len(ranked) > 1 else (0.0, None))
        origin = next(f[k][1:] for f in per if k in f)
        m = MapMatch(k, s, k2, s2, origin, fits=ranked)
        if s < self.min_score:
            m.map_id, m.why = None, "the minimap window fits, but no map's picture matches"
        elif k2 is not None and s - s2 < self.lead:
            m.map_id, m.why = None, "two maps look alike"
        return m
