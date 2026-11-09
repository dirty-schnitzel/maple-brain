"""brain-v2 Travel skill: go to a platform (and an x on it) along NavMap.route, one link move at a time.

After each move: compare where we are with the link's dst; elsewhere -> re-plan from here (events: replan). A link
that fails twice is avoided for the rest of this trip (event: blacklisted - navmap fixes). In the air we keep the
last move's keys until we land somewhere. Status: run / done / failed (no route, too many re-plans, stuck).
`step(now, s, driver)` presses the keys itself (driver = runtime/keys.KeyDriver or nav/sim.SimDriver).
"""
from ..humanize import Humanizer
from .moves import WalkTo, Wish, for_link, node_of


class Travel:
    def __init__(self, nav, dst: int, dst_x: float | None = None, hz: Humanizer | None = None, keymap=None,
                 tol: float = 10.0, max_replans: int = 8, stuck_s: float = 3.0):
        self.nav, self.dst, self.dst_x, self.hz = nav, dst, dst_x, hz or Humanizer()
        self.keymap = keymap or {}                         # logical -> game key ("jump" -> "shift")
        self.tol, self.max_replans, self.stuck_s = tol, max_replans, stuck_s
        self.move = None
        self.route = []
        self.status, self.reason = "run", None
        self.fails = {}                                    # link -> failures
        self.avoid = set()
        self.replans = 0
        self.events = []                                   # (t, kind, detail) for logs / the tour stats
        self.log = []                                      # per finished move: (kind, ok, secs, expected, reason)
        self.last_wish = Wish()
        self.progress_t, self.progress_key = None, None

    def _event(self, now, kind, detail=""):
        self.events.append((round(now, 2), kind, detail))

    def _plan(self, now, s):
        n = node_of(s)
        pos = s.y if self.nav.is_rope(n) else s.x
        if n == self.dst:
            self.route = []
        else:
            r = self.nav.route(n, pos, self.dst, self.dst_x, avoid=self.avoid)
            if r is None:
                self.status, self.reason = "failed", f"no route {n} -> {self.dst}"
                return
            self.route = list(r)
        self._next(now, s)

    def _next(self, now, s):
        if self.route:
            self.move = for_link(self.nav, self.route.pop(0), self.hz, now, s)
        elif self.dst_x is not None and not self.nav.is_rope(self.dst):
            if abs(s.x - self.dst_x) <= self.tol:
                self.status = "done"
                self.move = None
            else:
                self.move = WalkTo(self.nav, self.dst, self.dst_x, self.hz, now, s, self.tol)
        else:
            self.status = "done"
            self.move = None

    def _apply(self, driver, wish):
        km = self.keymap
        driver.hold({km.get(k, k) for k in wish.hold})
        for key, secs, after in wish.taps:
            driver.tap(km.get(key, key), secs, after)
        self.last_wish = wish

    def step(self, now, s, driver) -> str:
        if self.status != "run" or s is None:
            if self.status != "run":
                driver.hold(set())
            return self.status
        key = (node_of(s), round(s.x / 20), round(s.y / 20))
        if key != self.progress_key:
            self.progress_key, self.progress_t = key, now
        elif now - self.progress_t > self.stuck_s:
            self.status, self.reason = "failed", "stuck"
            self._event(now, "stuck", str(key))
            driver.hold(set())
            return self.status
        if self.move is None:
            if s.state == "air":
                self._apply(driver, Wish())
                return self.status
            self._plan(now, s)
            if self.move is None:
                driver.hold(set())
                return self.status
        wish = self.move.step(now, s)
        m = self.move
        if m.status == "run":
            self._apply(driver, wish)
            return self.status
        self.log.append((m.kind, m.status == "done", round(now - m.t0, 2), round(m.expected, 2), m.reason))
        if hasattr(driver, "cancel_taps"):
            driver.cancel_taps()                           # nothing of this move may fire during the next one
        if m.knocks:
            self._event(now, "knocked", f"{m.kind} x{m.knocks}")
        if m.status == "failed":
            k = m.link
            self._event(now, "failed", f"{m.kind} {m.reason}")
            if k is not None and m.reason != "knocked back":          # mobs, not the link: don't blame it
                self.fails[k] = self.fails.get(k, 0) + 1
                if self.fails[k] >= 2:
                    self.avoid.add(k)
                    self._event(now, "blacklisted", f"{k.kind} {k.src}->{k.dst}")
            self._replan(now, s)
        elif m.link is not None and node_of(s) != m.link.dst:
            self._event(now, "elsewhere", f"{m.kind} -> {node_of(s)}")
            self._replan(now, s)
        else:
            self._next(now, s)
        if self.status == "run" and self.move is not None:
            self._apply(driver, self.move.step(now, s))
        else:
            driver.hold(set())
        return self.status

    def _replan(self, now, s):
        self.replans += 1
        self.move = None
        if self.replans > self.max_replans:
            self.status, self.reason = "failed", "too many re-plans"
            return
        self._event(now, "replan")
        if s.state != "air":
            self._plan(now, s)
