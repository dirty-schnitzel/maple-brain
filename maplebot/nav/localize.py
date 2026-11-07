"""Where we are on the map: our minimap marker -> map coordinates -> the platform (or rope) under us.

The minimap window shows map.json's miniMap canvas 1:1 (one canvas px = 2**magnification map px); where the canvas
sits on screen depends on the map (Perion (6, 72), East Rocky Mountain I (30, 72): narrow minimaps are centred),
so it's found by template matching the canvas once. map = (canvas px + marker offset) * scale - (centerX, centerY);
the marker offset (our yellow dot is drawn ~7 minimap px above our feet) was fitted on 14444 recorded Perion
positions: 95 % land within 12 px of a floor, the rest on ropes (x 470 / -275).

The window doesn't always show the whole canvas. Ant Tunnel IV's canvas is 219x172, the window's picture 219x112, 1:1:
the game scrolls it up and down with the player (rows 0-111 at the top of the map, 60-171 in the lower right), though
East Rocky Mountain I shows all its 128 rows and nothing in map.json tells the two apart. So the window is measured
(find_window), never predicted from the canvas, and on such a map the canvas row at the window's top is followed every
tick (MinimapLocator.follow). `origin` stays the canvas' top-left on screen - above the window while scrolled - so
dot -> map is the same sum either way.
"""
import base64
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..config import Nav
from ..perception import hud

SEARCH = (0, 40, 470, 520)      # x0, y0, x1, y1: where the minimap window can be (Henesys' canvas is 431 px wide)
BRIGHT = 170                    # the window's frame and panels; the picture inside is drawn dimmer
FRAME = 205                     # the frame row itself (~235, its rim 150-190): stops at the rim, not at bright scenery
EDGE = 50                       # a canvas' edge: this much darker than what's just outside it
FRAME_X = 3                     # the frame row runs this many px past the inside of the window on each side
MIN_OPAQUE = 200                # fewer opaque pixels than this can't place a canvas
SCROLL_STEP = 6                 # canvas rows the window can scroll between two ticks (a fall: ~2)


@dataclass
class Where:
    x: float                      # map coordinates of our feet
    y: float
    platform: int | None = None   # the platform we stand on (None: in the air / on a rope)
    rope: float | None = None     # the x of the rope we're on, if any


@dataclass
class Window:
    """The inside of the minimap window, on screen. The canvas sits centred in it, as tall as `h` at most; a narrower
    canvas leaves see-through strips beside it, pale or not depending on the scenery behind (The Rain-Forest East of
    Henesys: 144 px in 232, the long name widens the window), so a canvas' sides can't be measured from here."""
    x: int
    y: int
    w: int
    h: int


def find_window(frame) -> Window | None:
    """Measure the minimap window: the first place in SEARCH with a dim area right under a bright frame row, closed by a
    bright row below. Top: a bright-to-dim step with no panel right under it (the title panel's own lines fail that);
    sides: where the frame row above ends, FRAME_X px outside the inside. None: closed or covered."""
    x0, y0, x1, y1 = SEARCH
    g = cv2.cvtColor(np.ascontiguousarray(frame[y0:y1, x0:x1]), cv2.COLOR_BGR2GRAY).astype(np.float32)
    for y in range(2, g.shape[0] - 20):
        run = np.convolve((g[y - 1] - g[y]) > EDGE, np.ones(24), "same")
        xs = np.nonzero(run >= 20)[0]
        if len(xs) <= 15:
            continue
        mid = (int(xs[0]) + int(xs[-1])) // 2
        dark = np.nonzero(g[y - 2] <= FRAME)[0]                     # the frame row: ~235 across the whole window
        if mid in dark:
            continue
        a = int(dark[dark < mid].max()) + 1 if (dark < mid).any() else 0
        b = int(dark[dark > mid].min()) - 1 if (dark > mid).any() else g.shape[1] - 1
        c = (a + b) // 2                                            # always canvas, whatever strips lie beside it
        if b - a < 50 or (g[y:y + 8, c - 12:c + 12] > BRIGHT).mean() > 0.3:
            continue
        bottom = np.nonzero((g[y + 20:, a + 8:b - 8] > BRIGHT).mean(1) > 0.9)[0]
        if len(bottom):
            return Window(x0 + a + FRAME_X, y0 + y, b - a - 2 * FRAME_X + 1, 20 + int(bottom[0]))
    return None


def scroll_row(gray: np.ndarray, opaque: np.ndarray, view: np.ndarray, rows) -> tuple:
    """Which of `rows` of a canvas sits at the window's top: (correlation, row) of the best one, over the opaque pixels.
    `gray`/`opaque`: the canvas; `view`: the window's picture in gray, as wide as the canvas. (-1.0, 0): none could
    be compared. Markers lower the score but not the peak (Ant Tunnel IV: 0.66 at the right row, 0.54 one row off)."""
    h = view.shape[0]
    best, at = -1.0, 0
    for row in rows:
        m = opaque[row:row + h]
        if m.sum() < MIN_OPAQUE:
            continue
        a, b = gray[row:row + h][m], view[m]
        if a.std() < 1e-6 or b.std() < 1e-6:
            continue
        r = float(np.corrcoef(a, b)[0, 1])
        if r > best:
            best, at = r, row
    return best, at


def _peak(v) -> float:
    """Parabola through three scores around a maximum -> the top's offset from the middle one (-0.5..0.5)."""
    if len(v) != 3:
        return 0.0
    d = v[0] - 2 * v[1] + v[2]
    return 0.0 if d >= 0 else float(np.clip(0.5 * (v[0] - v[2]) / d, -0.5, 0.5))


class MinimapLocator:
    def __init__(self, canvas: np.ndarray, center: tuple, magnification: int, cfg: Nav | None = None, navmap=None):
        self.canvas, self.center, self.scale = canvas, center, 2 ** magnification
        self.cfg, self.navmap = cfg or Nav(), navmap
        self.origin = None                               # canvas top-left on screen, once found
        self.gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY).astype(np.float32)
        self.opaque = np.ones(canvas.shape[:2], bool)    # the canvas' opaque pixels
        self.view = None                                 # Window, when it shows only part of the canvas (else None)
        self.row = 0                                     # scrolled: the canvas row at the window's top
        self.lost = False                                # scrolled: the picture stopped matching, position unknown

    @classmethod
    def from_json(cls, m: dict, cfg: Nav | None = None, navmap=None) -> "MinimapLocator":
        mm = m["miniMap"]
        png = np.frombuffer(base64.b64decode(mm["canvas"]), np.uint8)
        loc = cls(cv2.imdecode(png, cv2.IMREAD_COLOR), (mm["centerX"], mm["centerY"]), mm["magnification"], cfg, navmap)
        raw = cv2.imdecode(png, cv2.IMREAD_UNCHANGED)
        if raw.ndim == 3 and raw.shape[2] == 4:
            loc.opaque = raw[..., 3] > 0
        return loc

    @classmethod
    def for_map(cls, map_id: int, root: Path, cfg: Nav | None = None, navmap=None) -> "MinimapLocator":
        import json
        m = json.loads((root / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        return cls.from_json(m, cfg, navmap)

    def find_canvas(self, frame) -> tuple | None:
        """Screen (x, y) of the canvas' top-left corner, or None if it isn't clearly there (window closed/covered)."""
        x0, y0, x1, y1 = SEARCH
        region = frame[y0:y1, x0:x1]
        h, w = self.canvas.shape[:2]
        win = find_window(frame)
        if win is not None:
            self.view = win if win.h < h else None
        if self.view is not None:
            return self._find_scrolled(frame)
        if region.shape[0] < h or region.shape[1] < w:
            return None
        r = cv2.matchTemplate(region, self.canvas, cv2.TM_CCOEFF_NORMED)
        _, score, _, (lx, ly) = cv2.minMaxLoc(r)
        if score < self.cfg.canvas_score:
            return None
        # sub-pixel: the frame is scaled 3440 -> 1366 (x1.875), so from run to run the whole picture sits a fraction
        # of a px differently (recorded Perion runs: peak ~6.0 or ~6.7) - and 1 minimap px is 16 map px
        return (x0 + lx + _peak(r[ly, lx - 1:lx + 2]), y0 + ly + _peak(r[ly - 1:ly + 2, lx]))

    def _view_gray(self, frame, x: int) -> np.ndarray:
        """The window's picture in gray, as wide as the canvas, from screen column `x`."""
        v, w = self.view, self.canvas.shape[1]
        return cv2.cvtColor(np.ascontiguousarray(frame[v.y:v.y + v.h, x:x + w]), cv2.COLOR_BGR2GRAY).astype(np.float32)

    def _find_scrolled(self, frame) -> tuple | None:
        """The window shows part of the canvas: every row it could start at, then the sub-pixel spot as find_canvas."""
        v = self.view
        h, w = self.canvas.shape[:2]
        x = max(v.x + (v.w - w) // 2, 0)
        view = self._view_gray(frame, x)
        if view.shape[1] < w:
            return None
        score, row = scroll_row(self.gray, self.opaque, view, range(h - v.h + 1))
        if score < self.cfg.canvas_score:
            return None
        self.row = row
        y0, x0 = max(v.y - 2, 0), max(x - 2, 0)
        part = np.ascontiguousarray(self.canvas[row:row + v.h])
        mask = np.ascontiguousarray(np.repeat(self.opaque[row:row + v.h, :, None].astype(np.uint8) * 255, 3, 2))
        r = np.nan_to_num(cv2.matchTemplate(np.ascontiguousarray(frame[y0:v.y + v.h + 2, x0:x + w + 2]), part,
                                            cv2.TM_CCOEFF_NORMED, mask=mask), nan=-1.0, posinf=-1.0, neginf=-1.0)
        _, _, _, (lx, ly) = cv2.minMaxLoc(r)
        return x0 + lx + _peak(r[ly, lx - 1:lx + 2]), y0 + ly + _peak(r[ly - 1:ly + 2, lx]) - row

    def calibrate(self, frame) -> bool:
        """Find the canvas (call until it returns True; afterwards the position is kept). Also after `lost`."""
        if self.origin is None or self.lost:
            found = self.find_canvas(frame)
            if found is not None or not self.lost:
                self.origin = found
            self.lost = self.lost and found is None
        return self.origin is not None and not self.lost

    def follow(self, frame) -> None:
        """Scrolled window, every tick: how far did it move? Only rows near the last one (~1 ms); no match there
        (a portal, the window covered) -> `lost`, no position until calibrate finds it again."""
        if self.view is None or self.origin is None or self.lost:
            return
        h = self.canvas.shape[0] - self.view.h
        rows = range(max(self.row - SCROLL_STEP, 0), min(self.row + SCROLL_STEP, h) + 1)
        score, row = scroll_row(self.gray, self.opaque, self._view_gray(frame, max(round(self.origin[0]), 0)), rows)
        if score < self.cfg.canvas_score:
            self.lost = True
            return
        self.origin = (self.origin[0], self.origin[1] + self.row - row)
        self.row = row

    def dot_box(self) -> tuple:
        """The minimap area to look for our dot in: hud.MINIMAP_BOX's corner (obs.dot stays relative to it), out to
        the canvas' far edges (Perion's canvas is 243 px wide: the right 40 px fell outside the old box). Not past
        them: below Perion's canvas (y > 157) is game world - something yellow there made a second 'dot'."""
        if self.origin is None:
            return hud.MINIMAP_BOX
        h, w = self.canvas.shape[:2]
        bottom = self.origin[1] + h if self.view is None else self.view.y + self.view.h
        return (*hud.MINIMAP_BOX[:2], int(self.origin[0] + w + 2), int(bottom + 2))

    def to_map(self, dot) -> tuple | None:
        """obs.dot (relative to hud.MINIMAP_BOX's corner) -> map (x, y) of our feet."""
        if dot is None or self.origin is None or self.lost:
            return None
        bx, by = hud.MINIMAP_BOX[:2]
        cx = dot[0] + bx - self.origin[0] + self.cfg.marker_dx
        cy = dot[1] + by - self.origin[1] + self.cfg.marker_dy
        return (cx * self.scale - self.center[0], cy * self.scale - self.center[1])

    def where(self, dot) -> Where | None:
        p = self.to_map(dot)
        if p is None:
            return None
        w = Where(*p)
        if self.navmap is not None:
            plat = self.navmap.platform_at(*p)
            if plat is not None:
                w.platform = plat.id
            else:
                r = self.navmap.rope_at(*p)
                w.rope = r.x if r is not None else None
        return w
