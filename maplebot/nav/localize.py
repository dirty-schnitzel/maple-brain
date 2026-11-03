"""Where we are on the map: our minimap marker -> map coordinates -> the platform (or rope) under us.

The minimap window shows map.json's miniMap canvas 1:1 (one canvas px = 2**magnification map px); where the canvas
sits on screen depends on the map (Perion (6, 72), East Rocky Mountain I (30, 72): narrow minimaps are centred),
so it's found by template matching the canvas once. map = (canvas px + marker offset) * scale - (centerX, centerY);
the marker offset (our yellow dot is drawn ~7 minimap px above our feet) was fitted on 14444 recorded Perion
positions: 95 % land within 12 px of a floor, the rest on ropes (x 470 / -275).
"""
import base64
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..config import Nav
from ..perception import hud

SEARCH = (0, 40, 330, 330)      # x0, y0, x1, y1: where the minimap window can be


@dataclass
class Where:
    x: float                      # map coordinates of our feet
    y: float
    platform: int | None = None   # the platform we stand on (None: in the air / on a rope)
    rope: float | None = None     # the x of the rope we're on, if any


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

    @classmethod
    def from_json(cls, m: dict, cfg: Nav | None = None, navmap=None) -> "MinimapLocator":
        mm = m["miniMap"]
        png = np.frombuffer(base64.b64decode(mm["canvas"]), np.uint8)
        return cls(cv2.imdecode(png, cv2.IMREAD_COLOR), (mm["centerX"], mm["centerY"]), mm["magnification"],
                   cfg, navmap)

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
        if region.shape[0] < h or region.shape[1] < w:
            return None
        r = cv2.matchTemplate(region, self.canvas, cv2.TM_CCOEFF_NORMED)
        _, score, _, (lx, ly) = cv2.minMaxLoc(r)
        if score < self.cfg.canvas_score:
            return None
        # sub-pixel: the frame is scaled 3440 -> 1366 (x1.875), so from run to run the whole picture sits a fraction
        # of a px differently (recorded Perion runs: peak ~6.0 or ~6.7) - and 1 minimap px is 16 map px
        return (x0 + lx + _peak(r[ly, lx - 1:lx + 2]), y0 + ly + _peak(r[ly - 1:ly + 2, lx]))

    def calibrate(self, frame) -> bool:
        """Find the canvas (call until it returns True; afterwards the position is kept)."""
        if self.origin is None:
            self.origin = self.find_canvas(frame)
        return self.origin is not None

    def dot_box(self) -> tuple:
        """The minimap area to look for our dot in: hud.MINIMAP_BOX's corner (obs.dot stays relative to it), out to
        the canvas' far edges (Perion's canvas is 243 px wide: the right 40 px fell outside the old box). Not past
        them: below Perion's canvas (y > 157) is game world - something yellow there made a second 'dot'."""
        if self.origin is None:
            return hud.MINIMAP_BOX
        h, w = self.canvas.shape[:2]
        return (*hud.MINIMAP_BOX[:2], int(self.origin[0] + w + 2), int(self.origin[1] + h + 2))

    def to_map(self, dot) -> tuple | None:
        """obs.dot (relative to hud.MINIMAP_BOX's corner) -> map (x, y) of our feet."""
        if dot is None or self.origin is None:
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
