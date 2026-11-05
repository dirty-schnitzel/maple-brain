"""Where WE are, every tick, for brain-v2's movement skills: exact map x/y, ground / air / rope, velocity.

Position: `obs.me_map` (our name tag on screen + the tracker's camera, exact px; the camera moves by the platforms'
shift, perception/camshift.py) when our tag is found, else the minimap's `obs.map_pos` (16 px steps; our tag is
hidden on some ladders). State:
  ground - our feet within `ground_tol` of a platform surface and not moving vertically fast;
  rope   - at a rope's x (within `rope_tol`), between its ends, not on a surface;
  air    - anything else (jumping, falling, knocked back).
  Nothing hovers in this game: off every surface but not moving for HOVER_S at a rope's height within HOVER_TOL of
  its x = on that rope (runs/v2 08:51: hung on ladder 778 for 21 s read as x 785-788, "air" -> the brain waited to
  land forever; our tag's x drifts a few px on ladders).
With only the minimap the tolerances are the minimap's (Nav.surface_tol / rope_tol).
"""
from collections import deque
from dataclasses import dataclass

from ..config import Nav

HOVER_S = 0.25                    # s off every surface without moving = holding on to something
HOVER_V = 30.0                    # px/s: "not moving" on both axes
HOVER_TOL = 16.0                  # px from a rope's x for a hovering body to count as on it


@dataclass
class SelfState:
    t: float
    x: float
    y: float
    src: str                      # "tag" (exact) / "minimap" (coarse)
    state: str                    # ground / rope / air
    platform: int | None = None   # the platform under our feet (ground)
    rope: int | None = None       # the rope node (navmap id < 0) we hang on
    vx: float = 0.0               # px/s (map), from the last ~0.2 s
    vy: float = 0.0               # px/s, > 0 = falling (y down)

    def as_dict(self) -> dict:
        return {"x": round(self.x, 1), "y": round(self.y, 1), "src": self.src, "state": self.state,
                "platform": self.platform, "rope": self.rope, "vx": round(self.vx), "vy": round(self.vy)}


class SelfTracker:
    def __init__(self, navmap, cfg: Nav | None = None, ground_tol: float = 9, rope_tol: float = 7,
                 still_vy: float = 90, window: float = 0.2, mm_ground_tol: float = 18):
        self.nav, self.cfg = navmap, cfg or Nav()
        self.ground_tol, self.rope_tol, self.still_vy, self.window = ground_tol, rope_tol, still_vy, window
        self.mm_ground_tol = mm_ground_tol
        self.hist = deque()                               # (t, x, y, src)
        self.last: SelfState | None = None
        self.hover_since = None

    def _velocity(self, t):
        pts = [(ti, x, y) for ti, x, y, s in self.hist if t - ti <= self.window]
        if len(pts) < 2 or pts[-1][0] - pts[0][0] < 0.05:
            return 0.0, 0.0
        n = len(pts)                                      # least squares slope
        mt = sum(p[0] for p in pts) / n
        den = sum((p[0] - mt) ** 2 for p in pts) or 1e-9
        vx = sum((p[0] - mt) * p[1] for p in pts) / den
        vy = sum((p[0] - mt) * p[2] for p in pts) / den
        return vx, vy

    def update(self, t: float, me_map=None, map_pos=None) -> SelfState | None:
        if me_map is not None:
            x, y, src = me_map[0], me_map[1], "tag"
            gtol, rtol = self.ground_tol, self.rope_tol
        elif map_pos is not None:
            x, y, src = map_pos[0], map_pos[1], "minimap"
            gtol, rtol = self.cfg.surface_tol, self.cfg.rope_tol
        else:
            return self.last
        if self.hist and self.hist[-1][3] != src:          # don't mix exact and coarse in one velocity
            self.hist.clear()
        self.hist.append((t, x, y, src))
        while self.hist and t - self.hist[0][0] > self.window:
            self.hist.popleft()
        vx, vy = self._velocity(t)
        s = SelfState(t, x, y, src, "air", vx=vx, vy=vy)
        if src == "tag":                                   # exact x: no +-16 px search (that's for the minimap's
            plat = min(((abs(yp - y), p.id, p) for p, yp in self.nav.surfaces(x) if abs(yp - y) <= gtol),
                       default=(0, 0, None))[2]             # steps; it would keep us "on" a ledge we walked off)
            if plat is None and map_pos is not None:        # the camera's y can be ~10-15 px off: the minimap's
                mm = self.nav.platform_at(*map_pos)          # floor + our exact x on it, still vertically -> ground
                yp = mm.y_at(x) if mm is not None else None
                if yp is not None and abs(yp - y) <= self.mm_ground_tol:
                    plat = mm
        else:
            plat = self.nav.platform_at(x, y, tol=gtol)
        if plat is not None and abs(vy) < self.still_vy:
            s.state, s.platform = "ground", plat.id
            if src == "tag":
                s.y = plat.y_at(x) if plat.y_at(x) is not None else y      # on the floor: its y is exact
        else:
            still = abs(vx) < HOVER_V and abs(vy) < HOVER_V
            self.hover_since = (self.hover_since if self.hover_since is not None else t) if still else None
            hovering = still and t - self.hover_since >= HOVER_S
            best = None
            for i, r in enumerate(self.nav.ropes):
                tol = max(rtol, HOVER_TOL) if hovering else rtol
                if abs(r.x - x) <= tol and r.top - rtol <= y <= r.bottom + rtol                         and (best is None or abs(r.x - x) < best[0]):
                    best = (abs(r.x - x), i)
            if best is not None:
                s.state, s.rope = "rope", self.nav.rope_id(best[1])
        if s.state == "ground":
            self.hover_since = None
        self.last = s
        return s
