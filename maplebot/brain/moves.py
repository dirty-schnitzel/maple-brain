"""brain-v2 movement: one NavMap link (or a walk to an x) as a small closed-loop state machine.

Each tick: `wish = move.step(now, s)` with s = nav.selfstate.SelfState (our exact position + ground/rope/air);
wish.hold = the logical keys to keep down (left/right/up/down/jump), wish.taps = [(key, secs, after)] new presses
(emitted ONCE, on a phase change). The move ends with status "done" or "failed" (+ reason). Timing is varied
(Humanizer): take-off points random inside the link's [lo, hi], walk keys let go a random few px early (momentum:
walkDrag 800 px/s^2 stops a 125 px/s walk in ~10 px), tap lengths from the user's farming example (jump 0.17 s).
A move slower than ~2x its expected time (from the physics) fails ("timeout").
"""
from dataclasses import dataclass, field

from ..humanize import Humanizer

WALK = 125.0
DRAG = 800.0             # Physics.img walkDrag (px/s^2)
LAG = 0.1                # s from the picture to the key change (perception ~0.05 + a tick)
JUMP_TAP = 0.17          # the user's jump tap, median (farming example)


@dataclass
class Wish:
    hold: set = field(default_factory=set)
    taps: list = field(default_factory=list)            # [(key, secs, after)]


def node_of(s):
    """The navmap node we're on: a platform id (ground), a rope node (< 0), or None (in the air)."""
    if s is None:
        return None
    return s.platform if s.state == "ground" else (s.rope if s.state == "rope" else None)


def _sign(v):
    return (v > 0) - (v < 0)


class Move:
    kind = "move"
    base_s = 0.5                                         # expected time beyond the walking
    grounded = ("approach",)                             # phases in which we should be standing/walking: thrown into
                                                         # the air or pushed against the walk key there = knockback
    max_knocks = 4

    def __init__(self, nav, link, hz: Humanizer | None = None, now: float = 0.0, s=None):
        self.nav, self.link, self.hz = nav, link, hz or Humanizer()
        self.t0, self.status, self.reason, self.phase = now, "run", None, "approach"
        self.t_phase = now
        self.left_ground = False                         # we were seen in the air / off the source since take-off
        self.stop_early = self.hz.between(0, 8)           # varied let-go point (px), on top of the slide
        self.knocks, self.last_hold = 0, set()
        self.dir_since, self.dir_held = now, 0            # when we started holding the current walk direction
        self.now, self.nudge_until, self.settle_until = now, 0.0, 0.0
        self.still_since = None                          # holding a walk key without moving (on a ladder end?)
        self.setup(s)
        walk = abs(self.target_x() - s.x) if s is not None and self.target_x() is not None else 0.0
        self.expected = walk / WALK + self.base_s
        self.timeout = 2 * self.expected + 1.0

    # -- to override
    def setup(self, s):
        pass

    def target_x(self):
        return None

    def tick(self, now, s) -> Wish:
        raise NotImplementedError

    # -- the loop
    def step(self, now, s) -> Wish:
        if self.status != "run":
            return Wish()
        if now - self.t0 > self.timeout:
            return self.fail("timeout")
        n = node_of(s)
        if self.link is not None:
            if n == self.link.dst and n is not None:     # there, whichever way (a ladder instead of a drop...)
                return self.done()
            if n is not None and n != self.link.src:
                return self.fail(f"on {n}")
        if self.phase == "recover":                      # knocked back: let it settle, then start over
            if s.state == "ground" and abs(s.vx) < 30:
                self.go("approach", now)
                self.restart(s)
            return Wish()
        if self.phase in self.grounded and self.knocked(now, s):
            self.knocks += 1
            if self.knocks > self.max_knocks:
                return self.fail("knocked back")
            self.timeout += 1.5
            self.go("recover", now)
            return Wish()
        if s.state == "air" and self.phase == "air":
            self.left_ground = True
        self.now = now
        off = self.off_ladder(now, s)
        if off is not None:
            return off
        w = self.tick(now, s)
        d = (1 if "right" in w.hold else 0) - (1 if "left" in w.hold else 0)
        if d != self.dir_held:
            self.dir_held, self.dir_since = d, now
        self.last_hold = w.hold
        return w

    def off_ladder(self, now, s):
        """Holding a walk key 0.4 s without moving, at a rope's x and one of its ends at our floor: we hang on the
        ladder (its end looks like the floor - runs/g3 177-192 s, stuck holding right). Hop off sideways."""
        d = (1 if "right" in self.last_hold else 0) - (1 if "left" in self.last_hold else 0)
        if d == 0 or abs(s.vx) > 5 or s.state == "air":
            self.still_since = None
            return None
        if self.still_since is None:
            self.still_since = now
            return None
        if now - self.still_since < 0.4:
            return None
        if not any(abs(r.x - s.x) <= 4 and min(abs(r.top - s.y), abs(r.bottom - s.y)) <= 12 for r in self.nav.ropes):
            return None
        self.still_since = None
        return Wish({"right" if d > 0 else "left"}, [("jump", JUMP_TAP, self.hz.between(0.03, 0.1))])

    def knocked(self, now, s) -> bool:
        """A mob's touch: pushed against the walk key we've held for a while (turning round, the old momentum
        points the other way for ~0.2 s: walkForce 1400 px/s^2 + the picture's lag), or thrown up before we took
        off."""
        if self.link is not None and self.nav.is_rope(self.link.src):
            return False
        d = (1 if "right" in self.last_hold else 0) - (1 if "left" in self.last_hold else 0)
        pushed = d != 0 and s.vx * d < -60 and now - self.dir_since > 0.25
        return pushed or (s.state == "air" and node_of(s) is None and s.vy < -60)

    def restart(self, s):
        """After a knockback: pick the take-off again from where we are now."""
        if hasattr(self, "x_t") and hasattr(self, "dir") and self.dir and hasattr(self, "w_lo"):
            self.x_t = self.pick(self.w_lo, self.w_hi, s.x)
            self.x_s = self.runup_point()

    def done(self) -> Wish:
        self.status = "done"
        return Wish()

    def fail(self, why) -> Wish:
        self.status, self.reason = "failed", why
        return Wish()

    def go(self, phase, now):
        self.phase, self.t_phase = phase, now
        if phase == "air":
            self.left_ground = False                     # counted from this take-off on

    def off_ropes(self, lo, hi, gap=24.0):
        """[lo, hi] without the stretches near a rope/ladder hanging from (or standing on) the source platform:
        holding down there climbs onto it instead of dropping (runs/g2 137 s). The widest part nearest the
        middle is kept; nothing left -> [lo, hi]."""
        src = self.nav.platforms.get(self.link.src)
        if src is None:
            return lo, hi
        bad = sorted(r.x for r in self.nav.ropes if lo - gap <= r.x <= hi + gap and src.y_at(src.clamp(r.x))
                     is not None and (abs(r.top - src.y_at(src.clamp(r.x))) <= 25
                                      or abs(r.bottom - src.y_at(src.clamp(r.x))) <= 25))
        parts, a = [], lo
        for x in bad:
            if x - gap > a:
                parts.append((a, min(hi, x - gap)))
            a = max(a, x + gap)
        if a < hi:
            parts.append((a, hi))
        parts = [p for p in parts if p[1] - p[0] >= 4]
        return max(parts, key=lambda p: p[1] - p[0]) if parts else (lo, hi)

    # -- helpers
    def pick(self, lo, hi, x, margin=3.0):
        """A take-off point in [lo, hi]: near where we are (no needless walking), but varied."""
        lo2, hi2 = lo + margin, hi - margin
        if lo2 > hi2:
            return (lo + hi) / 2
        c = min(max(x, lo2), hi2)
        spread = min(30.0, (hi2 - lo2) / 2)
        return min(max(c + self.hz.between(-spread, spread), lo2), hi2)

    def safe(self, lo, hi, edge=14.0):
        """[lo, hi] kept `edge` px from the source platform's OPEN ends (walking in, we slide ~10 px past a
        let-go point), unless that leaves nothing."""
        src = self.nav.platforms.get(self.link.src) if self.link is not None else None
        if src is None:
            return lo, hi
        a = max(lo, src.left + edge) if src.open_left else lo
        b = min(hi, src.right - edge) if src.open_right else hi
        return (a, b) if a <= b else (lo, hi)

    def landing_window(self, lo, hi, inside=10.0):
        """The part of [lo, hi] from which a walking jump (NavMap.arc) lands on dst at least `inside` px from its
        ends (3 px if nothing does)."""
        src, dst = self.nav.platforms[self.link.src], self.nav.platforms[self.link.dst]
        for m in (inside, 3.0):
            ok = []
            x = lo
            while x <= hi + 1e-6:
                hit = self.nav.arc(x, src.y_at(src.clamp(x)), self.link.dir)
                if hit is not None and hit[1] is dst and dst.left + m <= hit[2] <= dst.right - m:
                    ok.append(x)
                x += 3.0
            if ok:
                return min(ok), max(ok)
        return lo, hi

    def runup_point(self):
        """Where a running take-off starts: 10-24 px before x_t (full walking speed takes ~6 px), kept off the
        source platform's open ends."""
        lo, hi = self.safe(self.nav.platforms[self.link.src].left, self.nav.platforms[self.link.src].right)
        return min(max(self.x_t - self.dir * self.hz.between(10, 24), lo), hi)

    def run_up(self, now, s, d) -> Wish:
        """The approach + run phases of a running take-off (Jump, Grab): get behind x_t, run at it, jump when at
        speed and there; past the window's far end without a jump -> back up and run again."""
        if self.phase == "approach":
            if (self.x_t - s.x) * self.dir >= 6 or abs(self.x_s - s.x) < 6:
                self.go("run", now)
                return Wish(d)
            hold, _ = self.walk_to(s, self.x_s, 6)
            return Wish(hold)
        far = self.w_hi if self.dir > 0 else self.w_lo
        if (s.x - far) * self.dir > 0:
            self.go("approach", now)
            return Wish()
        lead = abs(s.vx) * 0.06                           # our reaction + the frame's age
        if (s.x - self.x_t) * self.dir >= -lead and s.vx * self.dir >= 90:
            self.go("air", now)
            return Wish(d, [("jump", JUMP_TAP, 0.0)])
        return Wish(d)

    def walk_to(self, s, x, tol=6.0, lo=None, hi=None):
        """(hold, arrived): hold the walk key toward x and let go where the slide will stop there: our position is
        ~LAG s old by the time a key changes, and walkDrag 800 px/s^2 slides ~10 px from full speed. Arrived =
        within tol of x (or anywhere in [lo, hi] if given) and nearly still. A tight target (a rope's x) is lined
        up the last ~40 px in short taps, stopping in between (live the slide ran ~25 px past: runs/g3 80 s)."""
        lo = x - tol if lo is None else lo
        hi = x + tol if hi is None else hi
        if lo <= s.x <= hi and abs(s.vx) < 60:
            return set(), True
        dx = x - s.x
        now = self.now
        if hi - lo <= 20 and abs(dx) <= 40:
            key = {"right" if dx > 0 else "left"}
            if now < self.nudge_until:
                return key, False
            if abs(s.vx) > 15 or now < self.settle_until:
                return set(), False
            self.nudge_until = now + min(0.15, max(0.04, abs(dx) / WALK * 0.7))
            self.settle_until = self.nudge_until + LAG + self.hz.between(0.05, 0.15)
            return key, False
        stop = s.x + s.vx * LAG + _sign(s.vx) * s.vx * s.vx / (2 * DRAG)   # where we'd stop if we let go now
        if _sign(s.vx) == _sign(dx) and (x - stop) * _sign(dx) <= self.stop_early - 5 + tol:
            return set(), False                           # let go: the slide carries us in
        return {"right" if dx > 0 else "left"}, False

    def landed(self, s, now, min_air=0.12):
        """After take-off: on the ground (or a rope) again -> done if it's the link's dst, else failed."""
        n = node_of(s)
        if n is None or now - self.t_phase < min_air:
            return None
        if n == self.link.dst:
            return self.done()
        if n == self.link.src and not self.left_ground:
            return None                                   # not off yet
        return self.fail(f"landed on {n}")


class WalkTo(Move):
    """Walk to x on the platform we're on (the last leg of a trip, or a take-off point)."""
    kind = "walk_to"
    base_s = 0.3

    def __init__(self, nav, platform, x, hz=None, now=0.0, s=None, tol=8.0):
        self.platform, self.x, self.tol = platform, x, tol
        super().__init__(nav, None, hz, now, s)

    def target_x(self):
        return self.x

    def tick(self, now, s):
        if node_of(s) != self.platform:
            return self.fail(f"off platform {self.platform}") if s.state != "air" else Wish()
        hold, ok = self.walk_to(s, self.x, self.tol)
        return self.done() if ok else Wish(hold)


class Walk(Move):
    """Surfaces meet: walk across onto dst."""
    kind = "walk"
    base_s = 0.3
    grounded = ()

    def setup(self, s):
        dst = self.nav.platforms[self.link.dst]
        src = self.nav.platforms[self.link.src]
        if dst.left >= src.right - 4:
            self.dir = 1
        elif dst.right <= src.left + 4:
            self.dir = -1
        else:
            self.dir = _sign((dst.left + dst.right) / 2 - s.x) or 1
        self.x = self.link.hi if self.dir > 0 else self.link.lo

    def target_x(self):
        return self.x

    def tick(self, now, s):
        n = node_of(s)
        if n == self.link.dst:
            return self.done()
        if n not in (self.link.src, None):
            return self.fail(f"on {n}")
        return Wish({"right" if self.dir > 0 else "left"})


class Jump(Move):
    """A jump: dir 0 = straight up through dst (stand, jump); +-1 = a running jump that way."""
    kind = "jump"
    base_s = 0.7
    grounded = ("approach", "run")

    def setup(self, s):
        k = self.link
        self.dir = k.dir
        lo, hi = self.safe(k.lo, k.hi)
        if self.dir:                                      # only take-offs whose arc comes down well inside dst
            lo, hi = self.landing_window(lo, hi)
        self.w_lo, self.w_hi = lo, hi
        self.x_t = self.pick(lo, hi, s.x)
        self.x_s = self.runup_point()

    def target_x(self):
        return self.x_t

    def tick(self, now, s):
        d = {"right"} if self.dir > 0 else ({"left"} if self.dir < 0 else set())
        if self.phase == "approach":
            if node_of(s) != self.link.src:
                return self.fail(f"left src ({node_of(s)})") if s.state != "air" else Wish()
            if self.dir == 0:
                hold, ok = self.walk_to(s, self.x_t, 5, self.w_lo, self.w_hi)
                if not ok:
                    return Wish(hold)
                self.go("air", now)
                return Wish(set(), [("jump", JUMP_TAP, self.hz.between(0.02, 0.12))])
            return self.run_up(now, s, d)
        if self.phase == "run":
            if node_of(s) != self.link.src:
                return self.fail(f"ran off src ({node_of(s)})") if s.state != "air" else Wish(d)
            return self.run_up(now, s, d)
        w = self.landed(s, now)
        return w if w is not None else Wish(d)


class Drop(Move):
    """down + jump: through the platform, straight down."""
    kind = "drop"
    base_s = 0.8

    def setup(self, s):
        self.w_lo, self.w_hi = self.off_ropes(*self.safe(self.link.lo, self.link.hi))
        self.x_t = self.pick(self.w_lo, self.w_hi, s.x, margin=6)

    def restart(self, s):
        self.x_t = self.pick(self.w_lo, self.w_hi, s.x, margin=6)

    def target_x(self):
        return self.x_t

    def tick(self, now, s):
        if self.phase == "approach":
            hold, ok = self.walk_to(s, self.x_t, 10)
            if not ok:
                return Wish(hold)
            self.go("crouch", now)
            self.jump_after = self.hz.between(0.06, 0.16)
            return Wish({"down"}, [("jump", JUMP_TAP, self.jump_after)])
        if self.phase == "crouch":
            if s.state == "air":
                self.go("air", now)
                self.left_ground = True
                return Wish()
            if now - self.t_phase > 0.8:                  # the jump never came through: once more
                self.go("approach", now)
            # down only until the jump is in: held while falling it catches any ladder we pass (runs/g3 177 s)
            return Wish({"down"} if now - self.t_phase < self.jump_after + self.hz.between(0.1, 0.18) else set())
        w = self.landed(s, now, 0.05)
        return w if w is not None else Wish()


class Fall(Move):
    """Walk off the end of the platform."""
    kind = "fall"
    base_s = 0.6
    grounded = ()

    def setup(self, s):
        self.edge = self.link.lo if self.link.dir < 0 else self.link.hi

    def target_x(self):
        return self.edge

    def tick(self, now, s):
        d = {"right"} if self.link.dir > 0 else {"left"}
        if self.phase == "approach":
            if s.state == "air":
                self.go("air", now)
                return Wish()
            return Wish(d)
        w = self.landed(s, now, 0.05)
        return w if w is not None else Wish()


class Grab(Move):
    """Platform -> rope: jump (running if dir) and hold up in the air (the user: `up while left+shift`)."""
    kind = "grab"
    base_s = 0.7
    grounded = ("approach", "run")

    def setup(self, s):
        k = self.link
        self.dir = k.dir
        self.rope = self.nav.rope(k.dst)
        self.w_lo, self.w_hi = self.safe(k.lo, k.hi)
        self.x_t = self.pick(self.w_lo, self.w_hi, s.x)
        if self.dir:                                      # a running grab: take off a little short of the rope
            self.x_t = min(max(self.x_t, self.rope.x - 70), self.rope.x + 70)
        self.x_s = self.runup_point()
        self.up_after = self.hz.between(0.04, 0.14)

    def target_x(self):
        return self.x_t

    def tick(self, now, s):
        d = {"right"} if self.dir > 0 else ({"left"} if self.dir < 0 else set())
        if node_of(s) == self.link.dst:
            return self.done()
        if self.phase == "approach":
            if node_of(s) != self.link.src:
                return Wish() if s.state == "air" else self.fail(f"left src ({node_of(s)})")
            if self.dir == 0:
                hold, ok = self.walk_to(s, self.rope.x, 4)
                if not ok:
                    return Wish(hold)
                self.go("air", now)
                return Wish(set(), [("jump", JUMP_TAP, self.hz.between(0.02, 0.1))])
            return self.run_up(now, s, d)
        if self.phase == "run":
            if node_of(s) != self.link.src:
                return Wish(d) if s.state == "air" else self.fail(f"ran off src ({node_of(s)})")
            return self.run_up(now, s, d)
        hold = d | ({"up"} if now - self.t_phase >= self.up_after else set())
        w = self.landed(s, now, 0.2)
        return w if w is not None else Wish(hold)


class Descend(Move):
    """Platform -> the rope hanging from it: stand at the rope's x, hold down."""
    kind = "descend"
    base_s = 0.4

    def setup(self, s):
        self.rope = self.nav.rope(self.link.dst)

    def target_x(self):
        return self.rope.x

    def tick(self, now, s):
        if node_of(s) == self.link.dst:
            return self.done()
        if self.phase == "approach":
            hold, ok = self.walk_to(s, self.rope.x, 4)
            if not ok:
                return Wish(hold)
            self.go("down", now)
        return Wish({"down"})


class Exit(Move):
    """Rope -> the platform at its top: climb up out of it."""
    kind = "exit"

    def setup(self, s):
        self.base_s = max(0.3, (s.y - self.nav.rope(self.link.src).top) / 125 + 0.3) if s is not None else 1.0

    def tick(self, now, s):
        n = node_of(s)
        if n == self.link.dst:
            return self.done()
        if n is not None and n != self.link.src:
            return self.fail(f"on {n}")
        return Wish({"up"})


class LetGo(Move):
    """Rope -> what's under its bottom: climb down off it."""
    kind = "let_go"

    def setup(self, s):
        self.base_s = max(0.4, (self.nav.rope(self.link.src).bottom - s.y) / 125 + 0.5) if s is not None else 1.5

    def tick(self, now, s):
        if self.phase == "approach":
            if s.state == "air":
                self.go("air", now)
                return Wish()
            return Wish({"down"})
        w = self.landed(s, now, 0.05)
        return w if w is not None else Wish()


class Leap(Move):
    """Rope -> rope / platform: climb to a y in [lo, hi], jump sideways (+ hold up for a rope)."""
    kind = "leap"
    base_s = 0.8

    def setup(self, s):
        self.y_t = self.pick(self.link.lo, self.link.hi, s.y if s is not None else self.link.lo, margin=4)
        self.to_rope = self.nav.is_rope(self.link.dst)
        self.up_after = self.hz.between(0.08, 0.18)

    def tick(self, now, s):
        d = {"right"} if self.link.dir > 0 else {"left"}
        if node_of(s) == self.link.dst:
            return self.done()
        if self.phase == "approach":
            if s.state != "rope":
                return Wish() if s.state == "air" else self.fail(f"on {node_of(s)}")
            dy = self.y_t - s.y
            if abs(dy) > 6:
                return Wish({"down"} if dy > 0 else {"up"})
            self.go("air", now)
            return Wish(d, [("jump", JUMP_TAP, self.hz.between(0.03, 0.1))])
        hold = d | ({"up"} if self.to_rope and now - self.t_phase >= self.up_after else set())
        w = self.landed(s, now, 0.2)
        return w if w is not None else Wish(hold)


KINDS = {"walk": Walk, "jump": Jump, "drop": Drop, "fall": Fall, "grab": Grab, "descend": Descend, "exit": Exit,
         "let_go": LetGo, "leap": Leap}


def for_link(nav, link, hz=None, now=0.0, s=None) -> Move:
    return KINDS[link.kind](nav, link, hz, now, s)
