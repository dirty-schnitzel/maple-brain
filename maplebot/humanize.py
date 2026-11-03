"""Human-like timing. Every key-press length, pause and wait goes through `Humanizer.vary`, so no interval
between the bot's actions is ever a fixed number (fixed timings are an easy bot signature).

Shape, like a person's: most actions a little quicker than the nominal value, now and then a slower one (a long
right tail, as reaction times have), and a slow 'tempo' that wanders over a session (fresher / more tired
stretches) so the same action isn't timed alike for half an hour. 31 min of serve on 2026-11-01 ended in a Lie
Detector test; the old shape was a narrow symmetric +-20 % around a fixed centre.
"""
import random


class Humanizer:
    def __init__(self, jitter: float = 0.25, seed: int | None = None, drift: float = 0.08,
                 drift_step: float = 0.004):
        self.jitter = jitter
        self.rng = random.Random(seed)
        self.drift, self.drift_step = drift, drift_step
        self.tempo = 1.0                    # slow multiplier on every wait, a random walk within 1 +- drift

    def _wander(self):
        self.tempo += self.rng.gauss(0.0, self.drift_step)
        self.tempo = min(max(self.tempo, 1 - self.drift), 1 + self.drift)

    def vary(self, secs: float) -> float:
        """`secs` scaled by a random factor in [1 - jitter, 1 + jitter]: skewed (mode below 1, longer tail above)
        and carried by the session's wandering tempo."""
        if secs <= 0 or self.jitter <= 0:
            return secs
        self._wander()
        j = self.jitter
        f = self.tempo * self.rng.triangular(1 - j, 1 + j, 1 - j * 0.35)
        return secs * min(max(f, 1 - j), 1 + j)

    def between(self, lo: float, hi: float) -> float:
        return lo if self.jitter <= 0 else self.rng.uniform(lo, hi)

    def count(self, lo: int, hi: int) -> int:
        """A whole number in [lo, hi] (the middle one when timing isn't randomized)."""
        return (lo + hi) // 2 if self.jitter <= 0 else self.rng.randint(lo, hi)

    def chance(self, p: float) -> bool:
        """True with probability `p` (never when timing isn't randomized: exact tests stay deterministic)."""
        return self.jitter > 0 and self.rng.random() < p
