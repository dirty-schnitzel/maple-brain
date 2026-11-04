"""Which map are we on? The on-screen minimap matched against every map's miniMap canvas (assets/mcw, built from
the game's client files). Run once per hunt (F7), not per frame.

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
3. **The name, only to break a tie** (Line 1 <Area 1> vs <Area 2>: minimaps 0.89 vs 0.88): the window prints the
   map's name above the canvas. Each tied map's name is drawn in Arial Bold 12 px (no smoothing - closest to the
   game's font; others scored near 0), lined up on the part the names share ("Line 1 <Area ") and compared on the
   part that differs. Not OCR: it only chooses among the tied maps.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .localize import SEARCH

NAME_FONT = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf"
NAME_SIZE = 12
NAME_MIN, NAME_LEAD = 0.5, 0.15  # tie broken by the name: best >= 0.5 and 0.15 ahead (Line 1: 0.82 vs 0.54 / 0.43)
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


def _draw_name(text: str, font) -> np.ndarray:
    """White `text` on black, no anti-aliasing, 2 px margin."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (int(font.getlength(text)) + 6, NAME_SIZE + 8), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    d.text((2, 2), text, fill=255, font=font)
    return np.array(im).astype(np.float32)


def name_scores(frame, origin: tuple, names: dict[int, str]) -> dict[int, float]:
    """How well each map's name fits the name line above the canvas at `origin` (screen x, y of its top-left).
    Shared prefix -> where the line is; then each name scored on its differing tail only. {} = can't tell
    (no font, no shared prefix, no room above the canvas)."""
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(str(NAME_FONT), NAME_SIZE)
    except (ImportError, OSError):
        return {}
    pre = os.path.commonprefix(list(names.values()))
    if len(pre) < 3 or len(set(names.values())) < len(names):
        return {}
    x, y = origin
    region = cv2.cvtColor(np.ascontiguousarray(frame[max(y - 50, 0):max(y - 4, 0), max(x - 20, 0):x + 320]),
                          cv2.COLOR_BGR2GRAY).astype(np.float32)
    drawn = {k: _draw_name(n, font) for k, n in names.items()}
    pw = int(font.getlength(pre)) + 2                            # columns of the shared prefix (+ the margin)
    head = next(iter(drawn.values()))[:, :pw]
    if region.shape[0] < head.shape[0] or region.shape[1] < head.shape[1]:
        return {}
    _, _, _, (px, py) = cv2.minMaxLoc(cv2.matchTemplate(region, head, cv2.TM_CCOEFF_NORMED))
    W = max(t.shape[1] for t in drawn.values())
    stack = np.stack([np.pad(t, ((0, 0), (0, W - t.shape[1]))) for t in drawn.values()])
    diff = (stack.max(0) - stack.min(0)).max(0) > 0           # columns where the names differ
    segs, c = [], 0
    while c < W:                                                 # each run of them = one differing glyph (or few)
        if diff[c]:
            e = c
            while e < W and diff[e]:
                e += 1
            segs.append((max(c - 1, 0), min(e + 1, W)))          # +-1 px: the glyphs' edges
            c = e
        c += 1
    h = stack.shape[1]
    out = {}
    for k, t in zip(drawn, stack):
        per = []
        for c0, c1 in segs:                                      # each glyph placed on its own (+-1 px x/y: the
            g, best = t[:, c0:c1], -1.0                          # game's spacing isn't Arial's)
            if g.std() == 0:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    y0, x0 = py + dy, px + c0 + dx
                    patch = region[y0:y0 + h, x0:x0 + (c1 - c0)] if y0 >= 0 and x0 >= 0 else None
                    if patch is not None and patch.shape == g.shape and patch.std() > 0:
                        best = max(best, float(np.corrcoef(g.ravel(), patch.ravel())[0, 1]))
            per.append(best)
        if per:
            out[k] = float(np.mean(per))
    return out


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
                 lead: float = 0.05, min_opaque: int = 200, names: dict[int, str] | None = None):
        """canvases: BGRA (or BGR) pictures by map id. `edge`: a frame edge must be this much brighter outside than
        inside; `min_opaque`: canvases with fewer opaque pixels can't be told apart and are left out. `names`: map
        names (map.json "name") to break ties between look-alike minimaps."""
        self.names = names or {}
        full = {k: _canvas(c) for k, c in canvases.items()}
        self.canvases = {k: c for k, c in full.items() if c.n >= min_opaque}
        self.by_size: dict[tuple, list[int]] = {}
        for k, c in self.canvases.items():
            self.by_size.setdefault((c.bgr.shape[1], c.bgr.shape[0]), []).append(k)
        self.edge, self.min_score, self.lead = edge, min_score, lead

    @classmethod
    def load(cls, root: Path, **kw) -> "MapIdentifier":
        """Every maps/<id>/minimap.png under `root` (assets/mcw)."""
        canvases, names = {}, {}
        for p in (Path(root) / "maps").glob("*/minimap.png"):
            img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_UNCHANGED)
            if img is not None and img.ndim == 3:
                canvases[int(p.parent.name)] = img
                try:
                    names[int(p.parent.name)] = json.loads((p.parent / "map.json").read_text(encoding="utf-8"))["name"]
                except (OSError, ValueError, KeyError):
                    pass
        return cls(canvases, names=kw.pop("names", names), **kw)

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
            return MapMatch(None, why="no minimaps on disk (assets build)")
        if isinstance(frames, np.ndarray):
            frames = [frames]
        found = [(fr, f) for fr, f in ((fr, self.fits(fr)) for fr in frames) if f]
        per = [f for _, f in found]
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
            tied = {kk: self.names.get(kk) for ss, kk in ranked if s - ss < self.lead}
            pick = self._by_name(found, tied) if None not in tied.values() else None
            if pick is None:
                m.map_id, m.why = None, "two maps look alike"
            else:
                m.map_id, m.score = pick, dict((kk, ss) for ss, kk in ranked)[pick]
                m.runner_up, m.runner_score = next((kk, ss) for ss, kk in ranked if kk != pick)
                m.origin = next(f[pick][1:] for f in per if pick in f)
                m.why = "told apart by the name"
        return m

    def _by_name(self, found, tied: dict[int, str]) -> int | None:
        """The tied map whose name the window shows (scores averaged over the frames), or None."""
        tot, n = {}, 0
        for fr, f in found:
            k0 = next((k for k in tied if k in f), None)
            if k0 is None:
                continue
            sc = name_scores(fr, f[k0][1:], tied)
            if not sc:
                continue
            n += 1
            for k, v in sc.items():
                tot[k] = tot.get(k, 0.0) + v
        if not n:
            return None
        ranked = sorted(((v / n, k) for k, v in tot.items()), reverse=True)
        (b, k), b2 = ranked[0], (ranked[1][0] if len(ranked) > 1 else -1.0)
        return k if b >= NAME_MIN and b - b2 >= NAME_LEAD else None
