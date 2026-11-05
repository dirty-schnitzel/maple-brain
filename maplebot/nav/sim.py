"""A small physics sim of OUR character on a real map (map.json footholds + ropes), for testing movement skills
offline (brain/moves.py, brain/travel.py) on a fake clock. Not a game emulator: just enough to walk, jump, drop
through, fall off edges, grab / climb / leave ropes, with the client's Physics.img numbers (v83 units / 100):
walkForce 1400 px/s^2, walkSpeed 125, walkDrag 800, gravityAcc 2000, fallSpeed 670, jumpSpeed 555.

Keys are the set held this step (+ edges detected from the last step's set): left/right/up/down, "jump".
Simplifications: no slopes' speed change, air control none (vx kept from take-off), rope grab within GRAB_DX of
the rope's x while holding up in the air or on the ground under it; jumping off a rope needs a direction.
"""
from dataclasses import dataclass, field

WALK_FORCE, WALK_SPEED, WALK_DRAG = 1400.0, 125.0, 800.0
GRAVITY, FALL_SPEED, JUMP_SPEED = 2000.0, 670.0, 555.0
CLIMB_SPEED = 125.0
GRAB_DX = 10.0                   # a rope is caught this close to its x
ROPE_JUMP_VY = 300.0             # jumping sideways off a rope: a small hop
ROPE_JUMP_VX = 125.0
JUMP_VX = 155 / 125.0   # a running jump: config Nav.jump_vx (155 px/s at full walk) - measured hops reach 80-112
                         # px in ~0.555 s of air; the plain walk speed would give only ~69


@dataclass
class Body:
    x: float
    y: float
    state: str = "ground"        # ground / air / rope
    platform: int | None = None
    rope: int | None = None      # navmap rope node (< 0)
    vx: float = 0.0
    vy: float = 0.0
    through: int | None = None   # dropping through this platform: don't land on it
    held: set = field(default_factory=set)


class Sim:
    def __init__(self, nav, platform: int, x: float):
        self.nav = nav
        p = nav.platforms[platform]
        self.b = Body(x, p.y_at(x), "ground", p.id)

    # ---------------------------------------------------------------- one step
    def step(self, keys, dt: float) -> Body:
        b, nav = self.b, self.nav
        keys = set(keys)
        new = keys - b.held
        b.held = keys
        d = (1 if "right" in keys else 0) - (1 if "left" in keys else 0)
        if b.state == "ground":
            self._ground(b, keys, new, d, dt)
        elif b.state == "rope":
            self._rope(b, keys, new, d, dt)
        else:
            self._air(b, keys, dt)
        return b

    def _ground(self, b, keys, new, d, dt):
        nav = self.nav
        if "jump" in new:
            if "down" in keys:
                below = nav.below(b.x, b.y + 4)
                if below is not None:                     # drop through
                    b.state, b.through, b.vy, b.vx = "air", b.platform, 0.0, 0.0
                    b.platform = None
                    return
            else:
                b.state, b.vy, b.through, b.platform = "air", -JUMP_SPEED, None, None
                b.vx *= JUMP_VX
                return
        if "up" in keys:
            r = self._rope_near(b.x, b.y - 30)            # a rope over our head (its bottom near our body)
            if r is not None:
                return self._catch(b, r)
        if "down" in keys:
            r = self._rope_near(b.x, b.y + 15)            # a rope hanging from our platform down
            if r is not None and abs(nav.rope(r).top - b.y) <= 20:
                b.y += 15
                return self._catch(b, r)
        if d and "down" not in keys:                      # walking (down held = crouch, no walking)
            b.vx += d * WALK_FORCE * dt
            b.vx = max(-WALK_SPEED, min(WALK_SPEED, b.vx))
        else:
            dec = WALK_DRAG * dt
            b.vx = 0.0 if abs(b.vx) <= dec else b.vx - dec * (1 if b.vx > 0 else -1)
        p = nav.platforms[b.platform]
        nx = b.x + b.vx * dt
        if not p.left <= nx <= p.right:
            end_open = p.open_right if nx > p.right else p.open_left
            nxt = [q for q, yq in nav.surfaces(nx) if q is not p and abs(yq - p.y_at(p.clamp(nx))) <= 4]
            if nxt:                                        # walk across onto the next floor
                b.platform = nxt[0].id
            elif not end_open:
                nx, b.vx = p.clamp(nx), 0.0
            else:                                          # walk off the edge
                b.x, b.state, b.vy, b.platform = nx, "air", 0.0, None
                return
        b.x = nx
        b.y = nav.platforms[b.platform].y_at(b.x)

    def _rope(self, b, keys, new, d, dt):
        r = self.nav.rope(b.rope)
        if "jump" in new and d:                            # jump sideways off
            b.state, b.rope, b.vx, b.vy = "air", None, d * ROPE_JUMP_VX, -ROPE_JUMP_VY
            b.through = None
            return
        v = (-CLIMB_SPEED if "up" in keys else 0) + (CLIMB_SPEED if "down" in keys else 0)
        b.y += v * dt
        if b.y <= r.top:                                   # climbed out at the top
            top = self.nav._top_platform(r)
            if top is not None:
                b.state, b.rope, b.platform, b.y, b.vx = "ground", None, top.id, top.y_at(r.x), 0.0
                return
            b.y = r.top
        if b.y > r.bottom:                                 # off the bottom: fall
            b.state, b.rope, b.vy, b.vx, b.through = "air", None, 0.0, 0.0, None

    def _air(self, b, keys, dt):
        nav = self.nav
        if "up" in keys and b.vy > -JUMP_SPEED * 0.9:      # grab a rope (not in the first instant of a jump)
            r = self._rope_near(b.x, b.y - 30)
            if r is not None:
                return self._catch(b, r)
        b.vy = min(FALL_SPEED, b.vy + GRAVITY * dt)
        ny, nx = b.y + b.vy * dt, b.x + b.vx * dt
        if b.vy > 0:                                       # falling: land on the first surface crossed
            best = None
            for p, yp in nav.surfaces(nx):
                if p.id != b.through and b.y - 1e-6 <= yp <= ny and (best is None or yp < best[1]):
                    best = (p, yp)
            if best is not None:
                b.x, b.y, b.state, b.platform, b.vx, b.vy, b.through = nx, best[1], "ground", best[0].id, 0.0, 0.0, None
                return
        for w in nav.walls:                                # walls stop us sideways
            if min(b.x, nx) < w.x1 < max(b.x, nx) and w.y1 < ny < w.y2:
                nx, b.vx = b.x, 0.0
        b.x, b.y = nx, ny
        if b.y > 5000:
            raise RuntimeError("fell out of the map")

    def _rope_near(self, x, y):
        for i, r in enumerate(self.nav.ropes):
            if abs(r.x - x) <= GRAB_DX and r.top <= y <= r.bottom:
                return self.nav.rope_id(i)
        return None

    def _catch(self, b, rid):
        r = self.nav.rope(rid)
        b.state, b.rope, b.platform, b.x, b.vx, b.vy, b.through = "rope", rid, None, r.x, 0.0, 0.0, None
        b.y = min(max(b.y, r.top), r.bottom)


class SimDriver:
    """KeyDriver's interface (hold / tap / busy / held) on the sim's clock, with a reaction delay per key change."""

    def __init__(self, react: float = 0.02):
        self.want, self.taps, self.react = set(), [], react
        self.now = 0.0

    def hold(self, keys):
        self.want = set(keys)

    def tap(self, key, secs, after=0.0):
        if key in self.want or any(k == key and t1 > self.now for k, t0, t1 in self.taps):
            return False
        t0 = self.now + after + self.react
        self.taps.append((key, t0, t0 + secs))
        return True

    def busy(self, key=None):
        return any(t1 > self.now and (key is None or k == key) for k, t0, t1 in self.taps)

    def keys(self, now) -> set:
        self.now = now
        self.taps = [t for t in self.taps if t[2] > now]
        return self.want | {k for k, t0, t1 in self.taps if t0 <= now}

    def held(self):
        return self.keys(self.now)

    def release_all(self):
        self.want, self.taps = set(), []
