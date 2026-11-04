"""brain-v2 executor: a thread owns the keyboard, the brain loop never waits on a key.

Each tick the brain states what it wants:
    driver.hold({"right", "up"})       the SET of keys to keep down (replaces the last set; several at once)
    driver.tap("space", 0.13)          a press of ~0.13 s (varied), queued, returns at once
    driver.tap("z", 0.09, after=0.1)   ... starting ~0.1 s from now (bursts: z z z)
The thread turns that into key-downs / key-ups with human timing (the user's farming example, HANDOFF):
- a new key goes down after a short random reaction pause, a dropped one comes up after its own small pause, so
  two keys changed together never change in the same order / at the same instant (left -> right overlaps or gaps);
- every tap length varied (Humanizer.vary: skewed, wandering tempo); taps of the same key never overlap: the next
  one starts a varied gap after the last one's key-up;
- a held key auto-repeats like a real keyboard: only the most recently pressed key, after a ~0.5 s delay, every
  ~33 ms (what the game gets from the player's own keyboard);
- while the game isn't the foreground window nothing is sent: everything down is released, holds and taps are
  dropped, `lost_focus` is set (the runner pauses the hunt as before).
`pump(now)` does all the work and is what tests drive (a fake clock, no thread)."""
import threading
import time

from ..humanize import Humanizer

MOVE_KEYS = ("left", "right", "up", "down")


class KeyDriver:
    def __init__(self, send, focused, hz: Humanizer | None = None, hcfg=None, clock=time.perf_counter):
        """`send(key, up)` = one key event (keyboard._send); `focused()` = the game is in front."""
        from ..config import Humanize
        self.send, self.focused, self.clock = send, focused, clock
        self.hcfg = hcfg or Humanize()
        self.hz = hz or Humanizer(self.hcfg.jitter, self.hcfg.seed)
        self.lock = threading.RLock()
        self.want: set = set()             # the brain's held set
        self.down: dict = {}               # key -> when it went down (as sent)
        self.due: dict = {}                # key -> when its pending down (+1) / up (-1) is due: (t, +1|-1)
        self.taps: list = []               # [key, t_down, secs] queued, in order
        self.tap_up: dict = {}             # key -> when the tap's key-up is due
        self.tap_free: dict = {}           # key -> earliest time the next tap of it may go down
        self.repeat_key, self.next_repeat = None, None
        self.last_move = 0.0               # last time a movement key went down or up
        self.lost_focus = False
        self.sent = 0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None

    # ---- the brain's side (any thread) -------------------------------------------------------------------
    def hold(self, keys) -> None:
        keys = set(keys)
        with self.lock:
            now = self.clock()
            for k in keys - self.want:
                if k in self.tap_up:                       # mid-tap: the tap's key-up is cancelled, it stays down
                    del self.tap_up[k]
                elif k not in self.down:
                    self.due[k] = (now + self._react(), +1)
                else:
                    self.due.pop(k, None)                  # a pending release of it is cancelled
            for k in self.want - keys:
                if k in self.down:
                    self.due[k] = (now + self._release_pause(), -1)
                else:
                    self.due.pop(k, None)                  # wanted and dropped before it ever went down
            self.want = keys
        self._wake.set()

    def tap(self, key: str, secs: float, after: float = 0.0) -> bool:
        """Queue a press. Ignored (False) if the key is held, or already has a tap waiting (no pile-ups when the
        brain asks again next tick)."""
        with self.lock:
            if key in self.want or any(t[0] == key for t in self.taps):
                return False
            now = self.clock()
            t = max(now + after + self._react(), self.tap_free.get(key, 0.0))
            self.taps.append([key, t, self.hz.vary(secs)])
        self._wake.set()
        return True

    def busy(self, key: str | None = None) -> bool:
        """A tap of `key` (any key if None) is queued or still down."""
        with self.lock:
            if key is None:
                return bool(self.taps or self.tap_up)
            return key in self.tap_up or any(t[0] == key for t in self.taps)

    def held(self) -> set:
        with self.lock:
            return set(self.down)

    def release_all(self) -> None:
        """Everything up NOW (no pauses) and forget all wishes: stops, focus loss, the end of a hunt."""
        with self.lock:
            for k in list(self.down):
                self._up(k, self.clock())
            self.want.clear()
            self.due.clear()
            self.taps.clear()
            self.tap_up.clear()

    # ---- the thread ------------------------------------------------------------------------------------------
    def start(self) -> "KeyDriver":
        self._thread = threading.Thread(target=self._run, name="keys", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(1.0)
        self.release_all()

    def _run(self) -> None:
        while not self._stop.is_set():
            nxt = self.pump(self.clock())
            wait = 0.05 if nxt is None else max(0.0, min(0.05, nxt - self.clock()))
            if wait > 0:
                self._wake.wait(wait)
            self._wake.clear()

    def pump(self, now: float):
        """Send whatever is due at `now`; returns when the next thing is due (None = nothing pending)."""
        with self.lock:
            if not self.focused():
                if self.down or self.want or self.taps:
                    self.release_all()
                self.lost_focus = True
                return None
            self.lost_focus = False
            for k, (t, d) in sorted(self.due.items(), key=lambda kv: kv[1][0]):
                if t <= now:
                    del self.due[k]
                    if d > 0 and k not in self.down:
                        self._down(k, now)
                    elif d < 0 and k in self.down and k not in self.tap_up:
                        self._up(k, now)
            for k, t in list(self.tap_up.items()):
                if t <= now:
                    del self.tap_up[k]
                    if k not in self.want:
                        self._up(k, now)
                        self.tap_free[k] = now + self.hz.vary(self.hcfg.tap_gap_s)
            keep = []
            for item in self.taps:
                k, t, secs = item
                if t <= now and k not in self.down and k not in self.tap_up:
                    self._down(k, now)
                    self.tap_up[k] = now + secs
                else:
                    keep.append(item)
            self.taps = keep
            if self.repeat_key is not None and self.repeat_key in self.down and self.next_repeat <= now:
                self.send(self.repeat_key, False)          # typematic repeat: a key-down again, no key-up
                self.sent += 1
                self.next_repeat = now + self.hz.vary(self.hcfg.repeat_s)
            times = [t for t, _ in self.due.values()] + list(self.tap_up.values()) + [t[1] for t in self.taps]
            if self.repeat_key is not None and self.repeat_key in self.down:
                times.append(self.next_repeat)
            return min(times) if times else None

    def _down(self, k, now):
        self.send(k, False)
        self.sent += 1
        self.down[k] = now
        self.repeat_key, self.next_repeat = k, now + self.hz.vary(self.hcfg.repeat_delay_s)
        if k in MOVE_KEYS:
            self.last_move = now

    def _up(self, k, now):
        self.send(k, True)
        self.sent += 1
        self.down.pop(k, None)
        if self.repeat_key == k:
            self.repeat_key = None
        if k in MOVE_KEYS:
            self.last_move = now

    def _react(self) -> float:
        return self.hz.between(self.hcfg.react_min_s, self.hcfg.react_max_s)

    def _release_pause(self) -> float:
        return self.hz.between(self.hcfg.release_min_s, self.hcfg.release_max_s)


class LegacyExecutor:
    """The old brain's actions (Hold / Release / Tap) on a KeyDriver: same meaning as runtime.executor.Executor
    (one held key; a tap of a move key, or while not walking, lets go of the held key first) but NOTHING blocks:
    a Tap is queued and returns at once. A Tap of a key whose tap is still pending is dropped."""

    def __init__(self, driver: KeyDriver):
        self.d = driver
        self.held: str | None = None

    @property
    def last_move(self) -> float:
        return self.d.last_move

    def run(self, action) -> None:
        from ..brain.actions import Hold, Release, Tap
        if isinstance(action, Hold):
            self.d.hold({action.key})
            self.held = action.key
        elif isinstance(action, Release):
            self.release()
        elif isinstance(action, Tap):
            if action.key in MOVE_KEYS or self.held not in MOVE_KEYS:
                self.release()
            self.d.tap(action.key, action.secs)

    def release(self) -> None:
        self.d.hold(set())
        self.held = None

    def release_all(self) -> None:
        self.held = None
        self.d.release_all()
