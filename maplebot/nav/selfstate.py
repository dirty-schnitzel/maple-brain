"""Where WE are, every tick, for brain-v2's movement skills: exact map x/y, ground / air / rope, velocity.

Position: `obs.me_map` (our name tag on screen + the tracker's camera, exact px; the camera moves by the platforms'
shift, perception/camshift.py) when our tag is found, else the minimap's `obs.map_pos` (16 px steps; our tag is
hidden on some ladders). State:
  ground - our feet within `ground_tol` of a platform surface and not moving vertically fast;
  rope   - at a rope's x (within `rope_tol`), between its ends, not on a surface;
  air    - anything else (jumping, falling, knocked back).
  Nothing hovers in this game: off every surface but not moving for HOVER_S at a rope's height within HOVER_TOL of
  its x = on that rope (runs/v2 08:51: hung on ladder 778 for 21 s read as x 785-788, "air" -> the brain waited to
  land forever; our tag's x drifts a few px on ladders). Once on a rope we stay on it within HOVER_TOL while not moving
  sideways: ladder 778 reads +10 px, past rope_tol, so every climb flipped rope / air and Travel let go of `up`.
  Tag and minimap both below the floor next to a ladder = under its top, not on the floor (runs/v2 19:13: stopped at
  y 26, 13 px under platform 65's floor, read as standing on it: attacks did nothing, head above the platform, hit).
  Holding a walk key STUCK_S without moving, next to a ladder (within HOVER_TOL, spanning our height) = hanging on
  it, whatever the height says (runs/v2 09:21: hung under the top of ladder 778, read as standing on platform 65
  via the minimap's floor; walk keys did nothing for 14 s). `update(..., held=keys we hold)`. Only a walk key on its
  own counts, from ATTACK_FREEZE_S after any other key (an attack freezes us in place, its swing goes on after the
  key came up: runs/v2 10:44 t=792, read as hanging at a ladder's top, 3.3 s pressing up on the floor until the trip
  failed); once found, the hang holds until we move (HANG_MOVE px).
  Off every surface + still HOVER_S with no rope, at surface height just past a platform's end (within HOVER_TOL) = on
  that platform's end: we stand a few px past where the footholds stop, or our x reads a few px off at rest (runs/v2
  20261106_162027_12 t=798: on cart 275, right end 382, read as x 388 = "air": the bot waited to land for 24 s; same at
  the ends of 7, 19, 46, 56). s.x is clamped onto the platform; it holds until we move (HANG_MOVE px).
With only the minimap the tolerances are the minimap's (Nav.surface_tol / rope_tol).
"""
from collections import deque
from dataclasses import dataclass

from ..config import Nav

HOVER_S = 0.25                    # s off every surface without moving = holding on to something
HOVER_V = 30.0                    # px/s: "not moving" on both axes
HOVER_TOL = 16.0                  # px from a rope's x for a hovering body to count as on it
STUCK_S = 0.4                     # s a walk key is held without moving: we aren't on a floor
STUCK_V = 5.0                     # px/s
HANG_MOVE = 4.0                   # px: a detected hang lasts until we move this far
ATTACK_FREEZE_S = 0.9             # s after the attack key came up in which standing still proves nothing (swing ~0.8 s)


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
        self.walk_since = None                            # a walk key held on its own continuously since
        self.frozen_until = -9.0                          # standing still proves nothing until then (a swing)
        self.hang = None                                  # (rope index, x, y): found hanging there
        self.ledge = None                                 # (platform id, x, y): found standing past its end

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

    def _ladder_near(self, x, y, tol=HOVER_TOL, reach=20):
        """The rope / ladder we may be hanging on: within tol of its x, our height within reach of its span."""
        best = None
        for i, r in enumerate(self.nav.ropes):
            if abs(r.x - x) <= tol and r.top - reach <= y <= r.bottom + reach                     and (best is None or abs(r.x - x) < best[0]):
                best = (abs(r.x - x), i)
        return None if best is None else best[1]

    def _ledge_under(self, x, y, tol):
        """The platform whose end we stand just past: x within HOVER_TOL beyond it, feet at its surface (within tol)."""
        best = None
        for p in self.nav.platforms.values():
            cx = p.clamp(x)
            yp = p.y_at(cx)
            if cx != x and abs(cx - x) <= HOVER_TOL and yp is not None and abs(yp - y) <= tol                     and (best is None or abs(yp - y) < best[0]):
                best = (abs(yp - y), p)
        return None if best is None else best[1]

    def _under_ladder_top(self, x, y, floor_y, map_pos) -> bool:
        """Tag AND minimap both below the floor, next to a ladder: we hang under its top, the camera isn't off."""
        return y - floor_y > self.ground_tol and map_pos[1] - floor_y > self.ground_tol \
            and self._ladder_near(x, y) is not None

    def update(self, t: float, me_map=None, map_pos=None, held=None) -> SelfState | None:
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
                if yp is not None and abs(yp - y) <= self.mm_ground_tol and not self._under_ladder_top(x, y, yp, map_pos):
                    plat = mm
        else:
            plat = self.nav.platform_at(x, y, tol=gtol)
        if self.ledge is not None and (abs(x - self.ledge[1]) > HANG_MOVE or abs(y - self.ledge[2]) > HANG_MOVE):
            self.ledge = None
        if plat is None and self.ledge is not None:
            plat = self.nav.platforms[self.ledge[0]]
        keys = set(held or ())
        if keys - {"left", "right", "up", "down"}:
            self.frozen_until = t + ATTACK_FREEZE_S
        walking = bool({"left", "right"} & keys) and t >= self.frozen_until
        self.walk_since = (self.walk_since if self.walk_since is not None else t) if walking else None
        if self.hang is not None and (abs(x - self.hang[1]) > HANG_MOVE or abs(y - self.hang[2]) > HANG_MOVE):
            self.hang = None
        if self.hang is None and plat is not None and walking and abs(vx) < STUCK_V                 and t - self.walk_since >= STUCK_S:
            i = self._ladder_near(x, y)
            if i is not None:                               # walking does nothing: we hang on the ladder
                self.hang = (i, x, y)
        if self.hang is not None:
            plat = None
            s.state, s.rope = "rope", self.nav.rope_id(self.hang[0])
        if s.state == "rope":
            pass
        elif plat is not None and abs(vy) < self.still_vy:
            s.state, s.platform = "ground", plat.id
            if src == "tag":
                s.x = plat.clamp(x)                                        # past its end: on its end
                yp = plat.y_at(s.x)
                s.y = yp if yp is not None else y                          # on the floor: its y is exact
        else:
            still = abs(vx) < HOVER_V and abs(vy) < HOVER_V
            self.hover_since = (self.hover_since if self.hover_since is not None else t) if still else None
            hovering = still and t - self.hover_since >= HOVER_S
            best = None
            was_on = self.last.rope if self.last is not None and self.last.state == "rope" else None
            for i, r in enumerate(self.nav.ropes):
                stays = was_on == self.nav.rope_id(i) and abs(vx) < HOVER_V       # climbing on, not leaving sideways
                tol = max(rtol, HOVER_TOL) if hovering or stays else rtol
                if abs(r.x - x) <= tol and r.top - rtol <= y <= r.bottom + rtol                         and (best is None or abs(r.x - x) < best[0]):
                    best = (abs(r.x - x), i)
            if best is not None:
                s.state, s.rope = "rope", self.nav.rope_id(best[1])
            elif hovering:
                p = self._ledge_under(x, y, gtol)
                if p is not None:                           # nothing hovers: we stand on its end
                    self.ledge = (p.id, x, y)
                    s.state, s.platform, s.x, s.y = "ground", p.id, p.clamp(x), p.y_at(p.clamp(x))
        if s.state == "ground":
            self.hover_since = None
        self.last = s
        return s
