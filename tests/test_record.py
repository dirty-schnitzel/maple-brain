"""`python -m maplebrain record` (runtime/record.py) with a fake screen, keyboard and video writer: the start key
starts a recording, the stop key ends it, every grabbed frame is handed to the video with its number / time, never
a key sent; paused while the game is not focused; not started on a window that is not native or a full drive; the
Lie Detector watched on its own thread."""
import threading
import time
from pathlib import Path

import cv2

import maplebrain.runtime.record as record
import maplebrain.runtime.runner as runner
from maplebrain.config import Config

from test_runner import FX, START, STOP, FakeKeyboard, FakeScreen, ScriptedKeys


class FakeVideo:
    """VideoWriter stand-in: remembers what it was handed."""
    last = None

    def __init__(self, out, note=None):
        self.out, self.note, self.frames = Path(out), note, []
        self.written = self.dropped = self.queue_max = 0
        self.error, self.closed = None, False
        FakeVideo.last = self

    def put(self, frame, n, t, cursor=None, wait=False):
        self.frames.append((n, t, cursor, frame))
        self.written += 1
        return True

    def close(self):
        self.closed = True
        return {}

    def summary(self, seconds=None):
        return f"video: {self.written} frames"


class Keys(ScriptedKeys):
    """Scripted hotkeys; Ctrl+C in the console after `quit_after` polls (a session where nothing gets recorded)."""

    def __init__(self, script, quit_after=None):
        super().__init__(script)
        self.quit_after = quit_after

    def __call__(self, vk):
        if self.quit_after is not None and sum(self.n.values()) >= self.quit_after:
            raise KeyboardInterrupt
        return super().__call__(vk)


def _record(tmp_path, monkeypatch, script, focus_script=None, screen=None, max_recordings=1, free=500.0,
            quit_after=None):
    holder = {}

    def make_kb(hwnd, *_):
        holder["kb"] = FakeKeyboard(hwnd, focus_script)
        return holder["kb"]

    monkeypatch.setattr(record, "find_window", lambda: 1)
    monkeypatch.setattr(record, "Keyboard", make_kb)
    monkeypatch.setattr(record, "Screen", screen or FakeScreen)
    monkeypatch.setattr(record, "VideoWriter", FakeVideo)
    monkeypatch.setattr(record, "chirp", lambda up: None)
    monkeypatch.setattr(record, "free_gb", lambda path: free)
    monkeypatch.setattr(record.time, "sleep", lambda s: None)
    monkeypatch.setattr(record, "ASSETS", FX)
    FakeVideo.last = None
    hk = runner.Hotkeys([START, STOP], key_down=Keys(script, quit_after))
    code = record.record(tmp_path / "incoming", Config(), hotkeys=hk, max_recordings=max_recordings)
    return code, holder["kb"], tmp_path / "incoming"


def test_start_key_records_every_frame_until_the_stop_key_and_sends_no_key(tmp_path, monkeypatch):
    script = lambda name, n: (name == START and 3 <= n <= 4) or (name == STOP and 20 <= n <= 21)  # noqa: E731
    code, kb, out = _record(tmp_path, monkeypatch, script)
    assert code == 0 and kb.events == []                                 # never a key, not even a release
    (rec,) = list(out.iterdir())
    v = FakeVideo.last
    assert v.out == rec and v.closed and v.note == {"by": "record"}
    assert len(v.frames) > 10 and [n for n, *_ in v.frames] == list(range(len(v.frames)))      # from 0, in order
    assert all(b[1] > a[1] for a, b in zip(v.frames, v.frames[1:]))      # each with its time
    assert all(f[3].shape == (768, 1366, 3) for f in v.frames)
    log = (rec / "log.txt").read_text(encoding="utf-8")
    assert f"stopped by {STOP.upper()}" in log and f"frames: {len(v.frames)} grabbed" in log and "0 dropped" in log
    assert "time between frames p50" in log and (rec / "keys.jsonl").exists()
    assert not (rec / "ticks.jsonl").exists()                            # no perception ran


def test_start_key_is_ignored_while_the_game_is_not_focused(tmp_path, monkeypatch, capsys):
    script = lambda name, n: (name == START and n in (3, 9)) or (name == STOP and n >= 5)  # noqa: E731
    code, kb, out = _record(tmp_path, monkeypatch, script, focus_script=lambda n: n > 1)
    assert f"{START.upper()} ignored: the game isn't the focused window" in capsys.readouterr().out
    assert len(list(out.iterdir())) == 1                                 # the second press started one


class ScaledScreen(FakeScreen):
    box, cols = {"left": 0, "top": 0, "width": 1920, "height": 1080}, (0, 1920)


def test_no_recording_of_a_window_that_is_not_native(tmp_path, monkeypatch, capsys):
    """The video is the game's own 1366x768 pixels: a scaled picture is useless to the scene model."""
    script = lambda name, n: name == START and n in (3, 6)  # noqa: E731
    code, kb, out = _record(tmp_path, monkeypatch, script, screen=ScaledScreen, quit_after=40)
    said = capsys.readouterr().out
    assert said.count("not started: the game picture is 1920x1080, not the native 1366x768") == 2
    assert code == 0 and FakeVideo.last is None and list(out.iterdir()) == []


def test_no_recording_on_a_nearly_full_drive(tmp_path, monkeypatch, capsys):
    script = lambda name, n: name == START and n == 3  # noqa: E731
    code, kb, out = _record(tmp_path, monkeypatch, script, free=12.0, quit_after=30)
    assert "not started: only 12 GB free" in capsys.readouterr().out and FakeVideo.last is None


def test_recording_pauses_while_the_game_is_not_focused(tmp_path, monkeypatch):
    """Another window in front: its picture never gets into the video; the recording goes on when the game is back."""
    away = lambda n: not 12 <= n <= 16                                   # noqa: E731 - focus checks 12-16 say no
    script = lambda name, n: (name == START and n == 3) or (name == STOP and n == 30)  # noqa: E731
    code, kb, out = _record(tmp_path, monkeypatch, script, focus_script=away)
    (rec,) = list(out.iterdir())
    log = (rec / "log.txt").read_text(encoding="utf-8")
    assert "PAUSED: game not focused" in log and "recording paused" in log and "resumed" in log
    assert "keys released" not in log and kb.events == []
    v = FakeVideo.last
    assert len(v.frames) > 5 and [n for n, *_ in v.frames] == list(range(len(v.frames)))


def test_ctrl_c_ends_the_recording_with_its_numbers_and_quits(tmp_path, monkeypatch):
    script = lambda name, n: name == START and n == 3  # noqa: E731
    code, kb, out = _record(tmp_path, monkeypatch, script, quit_after=25, max_recordings=5)
    (rec,) = list(out.iterdir())
    log = (rec / "log.txt").read_text(encoding="utf-8")
    assert code == 0 and "stopped by Ctrl+C" in log and "frames: " in log and FakeVideo.last.closed


def test_lie_watch_sounds_the_siren_until_the_window_is_gone_and_saves_the_frame(tmp_path):
    from maplebrain.perception.liedetector import LieDetector
    lie = LieDetector.load(FX, background=False)
    game, none = cv2.imread(str(FX / "lie_detector_game.jpg")), cv2.imread(str(FX / "lie_detector_none.jpg"))
    said, sirens, done = [], [], threading.Event()

    def siren(still_there, max_s=120.0):
        while still_there():
            sirens.append(1)
            if len(sirens) == 2:
                watch.offer(none, now=100.0)                             # the user answered it: the next frame
        done.set()

    watch = record.LieWatch(lie, said.append, tmp_path, every_s=1.0, alarm=siren)
    watch.offer(none, now=0.0)
    watch.offer(game, now=0.5)                                           # under a second later: not looked at
    time.sleep(0.3)
    assert watch.seen == 0 and not sirens
    watch.offer(game, now=1.2)
    assert done.wait(10)
    time.sleep(0.05)
    watch.close()
    assert watch.seen == 1 and len(sirens) == 2 and len(list(tmp_path.glob("lie_*.png"))) == 1
    assert "LIE DETECTOR on screen" in said[0] and said[-1] == "lie detector window gone"


def test_gaps_line_counts_late_frames():
    line = record._gaps([1 / 60] * 98 + [0.034, 0.051])
    assert "p50 16.7" in line and "max 51.0 ms" in line and "2 over 25 ms" in line
