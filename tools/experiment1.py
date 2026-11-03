"""Experiment 1: input test + frame recording.

Waits until MapleStory is the foreground window, then records the game (normalized to 1366x768)
while doing: stand still 4s -> left 1s -> right 1s -> jump -> attack x3 -> stand still 2s.

Safety: keys are only sent while MapleStory has focus. If focus leaves the game, every held key
is released and the run aborts. All keys are released on exit, whatever happens.

Usage (must run elevated, the game runs as admin):
    python -I experiment1.py <out_dir> [--jump shift] [--attack space]
"""
import argparse
import ctypes
import json
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import cv2
import mss
import numpy as np

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetProcessDPIAware()

# ---------------------------------------------------------------- input (SendInput, scan codes)
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
SCAN = {"shift": 0x2A, "ctrl": 0x1D, "alt": 0x38, "space": 0x39, "z": 0x2C, "x": 0x2D, "c": 0x2E,
        "a": 0x1E, "s": 0x1F, "d": 0x20, "q": 0x10, "w": 0x11, "e": 0x12}
EXTENDED = {"left": 0x4B, "right": 0x4D, "up": 0x48, "down": 0x50}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send(key, up):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    if key in EXTENDED:
        code, flags = EXTENDED[key], flags | KEYEVENTF_EXTENDEDKEY
    else:
        code = SCAN[key]
    inp = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, code, flags, 0, 0)))
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


class Keys:
    """Every key-down is tracked so release_all() can always clean up."""

    def __init__(self, hwnd):
        self.hwnd, self.held = hwnd, set()

    def focused(self):
        return user32.GetForegroundWindow() == self.hwnd

    def _guard(self, grace_s=0.5):
        """Abort only if the game stays unfocused for more than grace_s (ignores brief flickers)."""
        if self.focused():
            return
        lost_at = time.perf_counter()
        while time.perf_counter() - lost_at < grace_s:
            time.sleep(0.05)
            if self.focused():
                return
        self.release_all()
        fg = user32.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(fg, title, 256)
        cls = ctypes.create_unicode_buffer(256); user32.GetClassNameW(fg, cls, 256)
        raise RuntimeError(f"MapleStory lost focus to '{title.value}' (class {cls.value}) - aborted, all keys released")

    def down(self, key):
        self._guard()
        _send(key, False)
        self.held.add(key)

    def up(self, key):
        _send(key, True)
        self.held.discard(key)

    def hold(self, key, seconds):
        """Hold a key, repeating key-down ~30/s like a real keyboard."""
        end = time.perf_counter() + seconds
        try:
            while time.perf_counter() < end:
                self.down(key)
                time.sleep(1 / 30)
        finally:
            self.up(key)

    def tap(self, key, n=1, down_s=0.08, gap_s=0.25):
        for _ in range(n):
            self.down(key)
            time.sleep(down_s)
            self.up(key)
            time.sleep(gap_s)

    def release_all(self):
        for k in list(self.held) + list(EXTENDED) + ["shift", "ctrl", "alt"]:
            try:
                _send(k, True)
            except OSError:
                pass
        self.held.clear()


# ---------------------------------------------------------------- capture
def client_box(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return {"left": p.x, "top": p.y, "width": r.right, "height": r.bottom}


def game_columns(frame):
    """x-range of the game picture inside the black pillarbox bars."""
    cols = np.where(frame.max(axis=(0, 2)) > 12)[0]
    return int(cols[0]), int(cols[-1]) + 1


class Recorder(threading.Thread):
    def __init__(self, box, fps):
        super().__init__(daemon=True)
        self.box, self.period = box, 1 / fps
        self.frames, self.phase, self.stop_flag = [], "idle", False
        self.cols = None

    def run(self):
        with mss.MSS() as sct:
            t0 = time.perf_counter()
            while not self.stop_flag:
                raw = np.asarray(sct.grab(self.box))[:, :, :3]
                if self.cols is None:
                    self.cols = game_columns(raw)
                g = raw[:, self.cols[0]:self.cols[1]]
                g = cv2.resize(g, (1366, 768), interpolation=cv2.INTER_AREA)
                self.frames.append((time.perf_counter() - t0, self.phase, g))
                time.sleep(max(0.0, self.period - (time.perf_counter() - t0) % self.period))


# ---------------------------------------------------------------- run
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--jump", default="shift")
    ap.add_argument("--attack", default="space")
    ap.add_argument("--fps", type=float, default=8)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "log.txt", "w", buffering=1)

    def say(msg):
        print(msg)
        log.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    hwnd = user32.FindWindowW(None, "MapleStory")
    if not hwnd:
        say("MapleStory window not found")
        return 1
    say("waiting up to 180s for MapleStory to be the foreground window...")
    deadline = time.time() + 180
    while user32.GetForegroundWindow() != hwnd:
        if time.time() > deadline:
            say("timed out")
            return 1
        time.sleep(0.2)
    time.sleep(1.0)

    keys = Keys(hwnd)
    rec = Recorder(client_box(hwnd), a.fps)
    events = []

    def phase(name):
        rec.phase = name
        events.append((round(time.perf_counter() - t0, 3), name))
        say(f"phase: {name}")

    t0 = time.perf_counter()
    rec.start()
    status = "ok"
    try:
        phase("idle_before")
        for _ in range(40):                      # 4s, checking focus as we wait
            keys._guard()
            time.sleep(0.1)
        phase("left_1s");   keys.hold("left", 1.0);  time.sleep(0.4)
        phase("right_1s");  keys.hold("right", 1.0); time.sleep(0.4)
        phase("jump");      keys.tap(a.jump);         time.sleep(0.8)
        phase("attack_x3"); keys.tap(a.attack, n=3, gap_s=0.5)
        phase("idle_after")
        for _ in range(20):
            keys._guard()
            time.sleep(0.1)
    except Exception as e:                       # noqa: BLE001 - report anything, then clean up
        status = f"aborted: {e}"
    finally:
        keys.release_all()
        rec.stop_flag = True
        rec.join(timeout=2)
    say(status)

    meta = {"status": status, "events": events, "keys": {"jump": a.jump, "attack": a.attack},
            "pillarbox_cols": rec.cols, "frames": []}
    for i, (t, ph, img) in enumerate(rec.frames):
        name = f"f{i:03d}.png"
        cv2.imwrite(str(out / name), img, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        meta["frames"].append({"file": name, "t": round(t, 3), "phase": ph})
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    say(f"saved {len(rec.frames)} frames to {out}")
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
