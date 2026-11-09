"""Which map are we on? The on-screen minimap matched against every map's miniMap canvas (assets/mcw, built from
the game's client files). Run once per hunt (F7), not per frame.

What the screen shows is not the raw canvas: the game draws it semi-transparent and slightly blurred over a
backdrop (screen ~ 0.45-0.6 x canvas + offset), and canvases are transparent where the map has nothing (~40-50 %;
Henesys Townstreet is one house on a strip). Plain colour error fails, and correlation alone lets a small canvas
match some patch of any minimap. Two cues together:
1. **The window's frame**: the window is measured on screen (localize.find_window). Its size is never predicted from
   a canvas, because it needn't be the canvas': Ant Tunnel IV shows 112 of its 172 rows and scrolls them with the
   player, and a long name widens it around a narrow map. A map fits if its canvas is at least as tall as the window
   and, centred in it, has edges there: darker than what's just outside, on average over the two sides.
2. **The picture**: each fitting canvas is correlated over its opaque pixels (which shrugs off the blend's
   gain/offset) at the row it fits best when it's taller than the window, then trimmed (see _corr), +-1 px.
A winner needs a minimum correlation and a lead over any other fitting map, averaged over a few frames
(markers move; a frame with the window covered is skipped).
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

from .localize import EDGE, MIN_OPAQUE, Window, find_window, scroll_row

NAME_FONT = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf"
NAME_SIZE = 12
NAME_MIN, NAME_LEAD = 0.5, 0.15  # tie broken by the name: best >= 0.5 and 0.15 ahead (Line 1: 0.82 vs 0.54 / 0.43)
TRIM = 0.03     # share of worst-fitting pixels dropped (markers); offline sweep 0/0.03/0.08/0.15: best margins
WIDTH_TOL = 6   # the measured window vs a canvas: a marker on the frame row narrows it (A Split Road 235 of 239)
CENTRE_TOL = 2  # a canvas' x vs the window's centre, px (measured off by at most 1.5)


@dataclass
class MapMatch:
    map_id: int | None            # None: no clear winner
    score: float = 0.0            # correlation of the winner (or of the best candidate)
    runner_up: int | None = None  # the next fitting map and its score (for the log)
    runner_score: float = 0.0
    origin: tuple | None = None   # screen (x, y) of the canvas' top-left (above the window if it's scrolled down)
    why: str = ""                 # why there's no winner
    fits: list = field(default_factory=list)   # [(score, map_id)] of every map whose size fits the frame


@dataclass
class _Canvas:
    bgr: np.ndarray
    mask: np.ndarray              # 3-channel 0/255, opaque pixels
    n: int                        # opaque pixel count
    gray: np.ndarray              # float32
    opaque: np.ndarray            # bool, one channel

    def rows(self, row: int, h: int) -> "_Canvas":
        """The part of the canvas a window `h` tall shows from `row` on."""
        o = self.opaque[row:row + h]
        return _Canvas(np.ascontiguousarray(self.bgr[row:row + h]), np.ascontiguousarray(self.mask[row:row + h]),
                       int(o.sum()), self.gray[row:row + h], o)


def _canvas(img) -> _Canvas:
    bgr = np.ascontiguousarray(img[..., :3])
    a = img[..., 3] > 0 if img.shape[2] == 4 else np.ones(img.shape[:2], bool)
    return _Canvas(bgr, np.ascontiguousarray(np.repeat(a[..., None].astype(np.uint8) * 255, 3, 2)), int(a.sum()),
                   cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32), a)


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


def _centred_x(gray: np.ndarray, win: Window, cw: int) -> int | None:
    """Screen x of a canvas `cw` wide if one sits in the window: centred, give or take CENTRE_TOL px, with its sides
    darker than what's beside them, on average (a bright marker against one side weakens that one: A Split Road's right
    edge 34 vs ~140 at the top and bottom). None: no such edges, the canvas on screen has another width."""
    x = win.x + (win.w - cw) // 2
    best, at = EDGE, None
    for s in range(max(x - CENTRE_TOL, 1), x + CENTRE_TOL + 1):
        if s + cw >= gray.shape[1]:
            break
        contrast = (gray[:, s - 1].mean() - gray[:, s].mean() + gray[:, s + cw].mean() - gray[:, s + cw - 1].mean()) / 2
        if contrast >= best:
            best, at = contrast, s
    return at


class MapIdentifier:
    def __init__(self, canvases: dict[int, np.ndarray], min_score: float = 0.5, lead: float = 0.05,
                 min_opaque: int = MIN_OPAQUE, names: dict[int, str] | None = None):
        """canvases: BGRA (or BGR) pictures by map id. `min_opaque`: canvases with fewer opaque pixels can't be told
        apart and are left out. `names`: map names (map.json "name") to break ties between look-alike minimaps."""
        self.names = names or {}
        full = {k: _canvas(c) for k, c in canvases.items()}
        self.canvases = {k: c for k, c in full.items() if c.n >= min_opaque}
        self.min_score, self.lead, self.min_opaque = min_score, lead, min_opaque

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

    def fits(self, frame, win: Window) -> dict[int, tuple]:
        """Every map the measured window can be showing: {map id: (score, canvas' screen x, canvas' screen y)}."""
        gray = cv2.cvtColor(np.ascontiguousarray(frame[win.y:win.y + win.h]), cv2.COLOR_BGR2GRAY).astype(np.float32)
        best = {}
        for k, c in self.canvases.items():
            ch, cw = c.bgr.shape[:2]
            if cw > win.w + WIDTH_TOL or ch < win.h - 2:
                continue
            x = _centred_x(gray, win, cw)
            if x is None:
                continue
            h = min(ch, win.h)
            row = scroll_row(c.gray, c.opaque, gray[:h, x:x + cw], range(ch - h + 1))[1] if ch > h else 0
            part = c.rows(row, h)
            if part.n >= self.min_opaque:
                best[k] = (_corr(frame, part, x, win.y), x, win.y - row)
        return best

    def identify(self, frames) -> MapMatch:
        """One frame or a list of them (taken a moment apart): scores averaged over the frames where the window was
        found (a map that doesn't fit in one of them scores 0 there)."""
        if not self.canvases:
            return MapMatch(None, why="no minimaps on disk (assets build)")
        if isinstance(frames, np.ndarray):
            frames = [frames]
        found = []
        for fr in frames:
            win = find_window(fr)
            f = self.fits(fr, win) if win is not None else None
            if f:
                found.append((fr, f, win))
        per = [f for _, f, _ in found]
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
        for fr, f, win in found:
            k0 = next((k for k in tied if k in f), None)
            if k0 is None:
                continue
            sc = name_scores(fr, (f[k0][1], win.y), tied)           # the name sits above the window, scrolled or not
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
