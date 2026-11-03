"""Keyboard output via SendInput with hardware scan codes, guarded by game focus.

The game runs elevated, so the process sending keys must be elevated too (Windows silently drops
simulated input from a lower-integrity process and SendInput still reports success).
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
SCAN = {"shift": 0x2A, "ctrl": 0x1D, "alt": 0x38, "space": 0x39, "enter": 0x1C, "esc": 0x01}
for _i, _c in enumerate("1234567890"):
    SCAN[_c] = 0x02 + _i
for _row, _start in (("qwertyuiop", 0x10), ("asdfghjkl", 0x1E), ("zxcvbnm", 0x2C)):
    for _i, _c in enumerate(_row):
        SCAN[_c] = _start + _i
for _i in range(10):
    SCAN[f"f{_i + 1}"] = 0x3B + _i
EXTENDED = {"left": 0x4B, "right": 0x4D, "up": 0x48, "down": 0x50, "home": 0x47, "end": 0x4F,
            "pageup": 0x49, "pagedown": 0x51, "insert": 0x52, "delete": 0x53}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


class FocusLost(Exception):
    """The game is not the foreground window: nothing may be sent."""


def _send(key: str, up: bool) -> None:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    if key in EXTENDED:
        code, flags = EXTENDED[key], flags | KEYEVENTF_EXTENDEDKEY
    else:
        code = SCAN[key]
    inp = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, code, flags, 0, 0)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def validate(key: str) -> None:
    if key not in SCAN and key not in EXTENDED:
        raise ValueError(f"unknown key {key!r}")


def foreground_title() -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 256)
    return buf.value


class Keyboard:
    """Sends keys only while `hwnd` is the foreground window; tracks held keys so they can always be released.
    Timing is humanized: a short random reaction pause before each new key-down, and every press length and
    after-tap pause is randomized (`hz` = Humanizer, `hcfg` = config.Humanize)."""

    def __init__(self, hwnd, hz=None, hcfg=None):
        from .config import Humanize
        from .humanize import Humanizer
        self.hwnd = hwnd
        self.held: set[str] = set()
        self.hcfg = hcfg or Humanize()
        self.hz = hz or Humanizer(self.hcfg.jitter, self.hcfg.seed)

    def focused(self) -> bool:
        return user32.GetForegroundWindow() == self.hwnd

    def _guard(self):
        if not self.focused():
            self.release_all()
            raise FocusLost()

    def down(self, key: str) -> None:
        self._guard()
        if key not in self.held:                    # a new press (not a hold's repeat): human reaction pause
            time.sleep(self.hz.between(self.hcfg.react_min_s, self.hcfg.react_max_s))
            self._guard()
        _send(key, False)
        self.held.add(key)

    def up(self, key: str) -> None:
        _send(key, True)
        self.held.discard(key)

    def tap(self, key: str, down_s: float = 0.08, gap_s: float | None = None) -> None:
        self.down(key)
        try:
            time.sleep(self.hz.vary(down_s))
        finally:
            self.up(key)
        time.sleep(self.hz.vary(self.hcfg.tap_gap_s if gap_s is None else gap_s))

    def release_all(self) -> None:
        for k in list(self.held) + ["left", "right", "up", "down", "shift", "ctrl", "alt", "space"]:
            try:
                _send(k, True)
            except (OSError, KeyError):
                pass
        self.held.clear()


def bring_to_front(hwnd) -> bool:
    """Make the game the foreground window. Windows only lets the foreground thread do that, so briefly attach
    our input queue to the current foreground window's thread. Returns True if the game is now in front."""
    kernel32 = ctypes.WinDLL("kernel32")
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    me = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(me, fg_thread, True)
    try:
        user32.ShowWindow(hwnd, 9)                      # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        user32.AttachThreadInput(me, fg_thread, False)
    if user32.GetForegroundWindow() != hwnd:
        # Windows refused (foreground lock). A synthetic Alt tap counts as user input and lifts the lock.
        _send("alt", False)
        _send("alt", True)
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd
