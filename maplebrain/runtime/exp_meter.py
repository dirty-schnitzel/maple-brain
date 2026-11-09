"""EXP per session and per hour, from the HUD's EXP points above the bar (party EXP included: it's the HUD total).

Total = current points - points at the start, never a sum of rises (a misread that comes back cancels out). A level-up
resets the points: what was gained up to the last reading is kept and counting goes on from the new number; the bit
gained between that reading and the level-up is left out. Time = the hunt's, breaks included, focus pauses not.
"""
from collections import deque

WINDOW_S = 300.0                # "last 5 min" rate, and how often it is logged
SAMPLE_S = 1.0                  # the window's history: one (t, total) per second, not per tick
LEVEL_UP_READS = 5              # readings in a row under half the points: a level-up, not a misread


class ExpMeter:
    def __init__(self):
        self.start_t = self.now = None
        self.base = self.last = None            # points when counting (re)started, latest points
        self.banked = 0                         # gained in the levels already finished
        self.level_ups = 0
        self.paused_s = 0.0
        self.low_reads = 0
        self.samples: deque = deque()
        self.next_report = None

    @property
    def total(self) -> int:
        return 0 if self.base is None else self.banked + self.last - self.base

    @property
    def elapsed(self) -> float:
        return 0.0 if self.start_t is None else self.now - self.start_t

    def pause(self, seconds: float) -> None:
        """The hunt stood still this long (game not focused): not part of the session's time."""
        self.paused_s += seconds

    def update(self, t: float, points: int | None) -> str | None:
        """Feed one tick; returns a log line when the next WINDOW_S is over. `points` None = unreadable."""
        t -= self.paused_s
        if points is not None:
            self._read(t, points)
        if self.start_t is None:
            return None
        self.now = t
        if not self.samples or t - self.samples[-1][0] >= SAMPLE_S:
            self.samples.append((t, self.total))
        while len(self.samples) > 1 and self.samples[1][0] <= t - WINDOW_S:
            self.samples.popleft()              # keeps the one sample at or just before the window's start
        if t < self.next_report:
            return None
        self.next_report += WINDOW_S
        return (f"EXP {self.total:,} this session = {self.per_hour():,.0f}/hour; "
                f"last 5 min {self.recent_per_hour():,.0f}/hour")

    def _read(self, t: float, points: int) -> None:
        if self.base is None:
            self.base = self.last = points
            self.start_t, self.next_report = t, t + WINDOW_S
        elif points < self.last / 2:
            self.low_reads += 1
            if self.low_reads >= LEVEL_UP_READS:
                self.banked += self.last - self.base
                self.base = self.last = points
                self.level_ups += 1
                self.low_reads = 0
        else:
            self.last, self.low_reads = points, 0

    def per_hour(self) -> float:
        return 3600 * self.total / max(self.elapsed, 1.0)

    def recent_per_hour(self) -> float:
        if not self.samples:
            return 0.0
        t, total = self.samples[0]
        return 3600 * (self.total - total) / max(self.now - t, 1.0)

    def summary(self) -> str:
        if self.start_t is None:
            return "session EXP: never read"
        return (f"session EXP {self.total:,} in {self.elapsed / 60:.1f} min = {self.per_hour():,.0f}/hour "
                f"({self.level_ups} level-ups)")
