"""The capture's window re-check (runtime/window.py, capture.Screen.check): a moved game window is re-aimed at once
it rests, an unchanged one costs nothing, a client area that is not 1366x768 pauses like 'game not focused'."""
from types import SimpleNamespace

import pytest

import maplebrain.capture as capture
import maplebrain.runtime.runner as runner
from maplebrain.config import Config
from maplebrain.runtime import window
from test_runner import FakeScreen, _run

BOX = {"left": 8, "top": 32, "width": 1366, "height": 768}


def at(dx=0, dy=0, w=1366, h=768):
    return {"left": BOX["left"] + dx, "top": BOX["top"] + dy, "width": w, "height": h}


# ---------------------------------------------------------------- Screen.check
def _screen(monkeypatch, now, alive=True):
    s = object.__new__(capture.Screen)
    s.hwnd, s.box = 1, dict(BOX)
    monkeypatch.setattr(capture, "client_box", lambda hwnd: now)
    monkeypatch.setattr(capture, "user32", SimpleNamespace(IsWindow=lambda hwnd: alive))
    return s


@pytest.mark.parametrize("now, alive, state", [
    (at(), True, "ok"), (at(-30, -22), True, "moved"), (at(w=1280, h=720), True, "size"),
    (at(-32000, -32000, 0, 0), True, "size"), (at(), False, "gone")])
def test_screen_check_states(monkeypatch, now, alive, state):
    assert _screen(monkeypatch, now, alive).check()[0] == state


# ---------------------------------------------------------------- Aim / wait_back on a scripted window
class Win:
    """A screen whose window follows `where(t)` (a box, or None = gone) on a fake clock."""

    def __init__(self, where):
        self.where, self.t, self.box, self.calibrated = where, 0.0, dict(BOX), []

    def check(self):
        b = self.where(self.t)
        if b is None:
            return "gone", None
        if (b["width"], b["height"]) != (1366, 768):
            return "size", b
        return ("ok" if b == self.box else "moved"), b

    def calibrate(self):
        self.box = dict(self.where(self.t))
        self.calibrated.append(self.t)
        self.t += 0.3


def test_unchanged_box_does_nothing():
    s, said = Win(lambda t: at()), []
    window.guard(s)
    aim = window.Aim(s, said.append)
    assert all(aim.ok() for _ in range(50)) and not said and not s.calibrated


def test_moved_box_raises_then_reaims_when_at_rest_and_logs_old_and_new():
    s, said = Win(lambda t: at(-30, -22)), []
    with pytest.raises(window.WindowLost) as e:
        window.guard(s)
    assert "(8, 32) 1366x768" in e.value.why and "(-22, 10) 1366x768" in e.value.why
    aim = window.Aim(s, said.append)
    assert not aim.ok() and not s.calibrated                 # first sight: is it still moving?
    assert aim.ok() and len(s.calibrated) == 1               # same place again: re-aimed
    assert said == ["capture re-aimed: game window moved (8, 32) 1366x768 -> (-22, 10) 1366x768"]
    window.guard(s)                                          # aimed again


def test_a_window_still_being_dragged_is_not_reaimed():
    s = Win(lambda t: at(-10 * (int(t) + 1), 0) if t < 5 else at(-60, 0))
    aim = window.Aim(s, lambda m: None)
    for _ in range(5):
        assert not aim.ok()
        s.t += 1
    assert not s.calibrated
    assert not aim.ok() and aim.ok() and s.box == at(-60, 0)


@pytest.mark.parametrize("bad, word", [(at(w=1280, h=720), "resized: client area 1280x720, not 1366x768"),
                                       (at(-32000, -32000, 0, 0), "minimized"), (None, "gone")])
def test_wrong_size_is_said_once_never_reaimed_and_back_is_said(bad, word):
    s, said = Win(lambda t: bad if t < 3 else at()), []
    aim = window.Aim(s, said.append)
    assert not aim.ok() and not aim.ok() and len(said) == 1 and word in said[0]
    s.t = 3
    assert aim.ok() and "back" in said[1] and not s.calibrated


# ---------------------------------------------------------------- the live loop (run, brain v1, fake screen)
class MovingScreen(FakeScreen):
    """The window is elsewhere (`now`) from grab 20 on; with `back_after`, it returns after that many checks."""
    now, back_after = at(-30, -22), None

    def __init__(self, hwnd):
        super().__init__(hwnd)
        self.box, self.checks_off = dict(BOX), 0

    def _where(self):
        if self.i < 20 or (self.back_after is not None and self.checks_off >= self.back_after):
            return at()
        return self.now

    def check(self):
        b = self._where()
        if b != at():
            self.checks_off += 1
        if (b["width"], b["height"]) != (1366, 768):
            return "size", b
        return ("ok" if b == self.box else "moved"), b

    def calibrate(self):
        self.box = dict(self._where())
        return super().calibrate()


def test_run_moved_window_pauses_releases_reaims_logs_and_resumes(tmp_path, monkeypatch):
    made = []

    class S(MovingScreen):
        def __init__(self, hwnd):
            super().__init__(hwnd)
            made.append(self)
    code, kb, out = _run(tmp_path, monkeypatch, screen=S)
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert "PAUSED: game window moved: capture aimed at (8, 32) 1366x768, window now at (-22, 10) 1366x768" in log
    assert "capture re-aimed: game window moved (8, 32) 1366x768 -> (-22, 10) 1366x768" in log
    assert log.index("capture re-aimed") < log.index("resumed")
    assert made[0].calibrated == 2 and log.count("PAUSED") == 1         # the start + one re-aim, then it holds
    assert ("release_all", None) in kb.events and not kb.held


def test_run_unchanged_window_never_reaims_or_logs(tmp_path, monkeypatch):
    made = []

    class S(MovingScreen):
        now = at()

        def __init__(self, hwnd):
            super().__init__(hwnd)
            made.append(self)
    code, kb, out = _run(tmp_path, monkeypatch, screen=S)
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert code == 0 and made[0].calibrated == 1 and "game window" not in log and "PAUSED" not in log


def test_run_wrong_size_pauses_with_keys_released_and_is_not_reaimed(tmp_path, monkeypatch):
    made = []

    class S(MovingScreen):
        now, back_after = at(w=1280, h=720), 6

        def __init__(self, hwnd):
            super().__init__(hwnd)
            made.append(self)
    code, kb, out = _run(tmp_path, monkeypatch, screen=S)
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert "PAUSED: game window resized: client area 1280x720, not 1366x768 - not re-aimed; keys released" in log
    assert "game window back at (8, 32) 1366x768" in log and "resumed" in log
    assert made[0].calibrated == 1 and "re-aimed:" not in log
    assert ("release_all", None) in kb.events[:-1] and not kb.held      # released at the pause, not only at the end


# ---------------------------------------------------------------- watch: its own loop
def test_watch_reaims_on_a_moved_window_and_skips_looks_while_it_cant_see(tmp_path, monkeypatch):
    import cv2
    from test_runner import FX
    none = cv2.imread(str(FX / "lie_detector_none.jpg"))
    clock = {"t": 0.0}

    class S(Win):
        def __init__(self, hwnd, dxcam=True):
            # 1-3 s dragged to the left, 6-8 s minimized
            super().__init__(lambda t: at(-40, 0) if 1 <= t < 6 else at(-32000, -32000, 0, 0) if t < 8 else at(-40, 0))
            self.where0, self.grabs, self.cols = self.where, [], (0, 1366)
            self.where = lambda t: at() if clock["t"] < 1 else self.where0(clock["t"])
            assert dxcam is False

        def grab(self):
            self.grabs.append(clock["t"])
            return none

        def close(self):
            pass
    made = []
    monkeypatch.setattr(runner, "find_window", lambda: 1)
    monkeypatch.setattr(runner, "Screen", lambda hwnd, dxcam=True: made.append(S(hwnd, dxcam)) or made[0])
    monkeypatch.setattr(runner, "ASSETS", FX)
    monkeypatch.setattr(runner.time, "perf_counter", lambda: clock["t"])
    monkeypatch.setattr(runner.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    assert runner.watch(tmp_path / "w", 10.0) == 0
    log = (tmp_path / "w" / "log.txt").read_text(encoding="utf-8")
    s = made[0]
    assert "capture re-aimed: game window moved (8, 32) 1366x768 -> (-32, 32) 1366x768" in log
    assert log.count("re-aimed") == 1 and log.count("minimized") == 1 and "game window back" in log
    assert not [t for t in s.grabs if 6 <= t < 8]            # no look at a picture that isn't the game
    assert [t for t in s.grabs if t >= 8.5]                  # looking again afterwards


# ---------------------------------------------------------------- the Dark Cave drag (runs/play/20261116_084719_1)
# picture shift per saved frame, measured on the recording (HUD strip vs frame 342): (t s, dx, dy)
DARK_CAVE = [(16.293, 0, 0), (16.397, -8, 0), (16.477, -19, -2), (16.550, -21, -3), (16.648, -23, -4),
             (16.721, -25, -6), (16.794, -28, -13), (16.892, -32, -23), (16.966, -33, -28), (17.035, -36, -31),
             (17.110, -43, -37), (17.209, -46, -38), (17.284, -46, -38), (17.355, -37, -32), (17.457, -31, -23),
             (17.531, -30, -22)]


def _dark_cave(t):
    d = [(dx, dy) for ts, dx, dy in DARK_CAVE if ts <= t]
    return at(*(d[-1] if d else (0, 0)))


def test_dark_cave_drag_is_caught_on_its_first_tick_and_reaimed_once_at_rest(monkeypatch):
    """What the live loop sees with the guard: the tick at 16.40 s (the first with the window off its place) is
    dropped, nothing is re-aimed during the 1.15 s drag (not even at its 0.08 s rest at -46 / -38 ... if a look
    pair lands in it, the next guard catches the move back), and the capture ends on the final place."""
    from maplebrain.humanize import Humanizer
    s, said = Win(_dark_cave), []
    s.t = 16.0
    monkeypatch.setattr(window.time, "sleep", lambda secs: setattr(s, "t", s.t + secs))
    hz = Humanizer(Config().humanize.jitter, 7, Config().humanize.drift)
    paused = None
    while s.t < 20:                                          # ticks ~27 ms apart, as recorded
        try:
            window.guard(s)
            s.t += 0.027
        except window.WindowLost as e:
            paused = paused or s.t
            assert window.wait_back(s, lambda: True, hz, said.append, lambda: s.t < 20, e)
    assert 16.397 <= paused <= 16.397 + 0.027
    assert s.box == at(-30, -22) and s.calibrated[-1] > 17.531 and len(s.calibrated) <= 2
    assert said[-1].endswith("-> (-22, 10) 1366x768")
