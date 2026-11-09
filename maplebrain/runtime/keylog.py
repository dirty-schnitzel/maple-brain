"""Records the player's own keys during an observe recording (keys.jsonl next to ticks.jsonl, same clock).

A low-level keyboard hook (WH_KEYBOARD_LL) on its own thread with its own message loop. Only transitions are
written (Windows' auto-repeat key-downs are dropped): one line per key going down or up,
    {"t": 12.345, "key": "left", "down": true}         (+ "inj": true for keys sent by a program, e.g. the bot)
`t` = perf_counter() - t0, the same t as obs.t in ticks.jsonl. A key-down is only recorded while the game is the
foreground window (`focused()`); the key-up of a key recorded down is always written, so no key stays "held"
in the log. `lag` (ms, only when >= 5) = how late our hook ran after the key event: the GIL is shared with the
perceiver, and while the hook waits the key also waits to reach the game, so this is watched.

Nothing is logged outside a recording: the hook exists only between start() and stop().
"""
import ctypes
import json
import threading
import time
from ctypes import wintypes

from ..keyboard import EXTENDED, SCAN

WH_KEYBOARD_LL, WM_QUIT = 13, 0x0012
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLKHF_EXTENDED, LLKHF_INJECTED, LLKHF_UP = 0x01, 0x10, 0x80

# scan code (+ extended flag) -> the same key names the bot uses (keyboard.SCAN / EXTENDED)
NAMES = {(code, False): name for name, code in SCAN.items()}
NAMES.update({(code, True): name for name, code in EXTENDED.items()})
NAMES.update({(0x36, False): "rshift", (0x1D, True): "rctrl", (0x38, True): "ralt", (0x0F, False): "tab",
              (0x0E, False): "backspace", (0x29, False): "`", (0x0C, False): "-", (0x0D, False): "=",
              (0x1A, False): "[", (0x1B, False): "]", (0x27, False): ";", (0x28, False): "'",
              (0x2B, False): "\\", (0x33, False): ",", (0x34, False): ".", (0x35, False): "/",
              (0x57, False): "f11", (0x58, False): "f12", (0x3A, False): "capslock",
              (0x1C, True): "kp_enter", (0x5B, True): "lwin", (0x5C, True): "rwin", (0x5D, True): "menu"})
for _n, _c in (("kp_7", 0x47), ("kp_8", 0x48), ("kp_9", 0x49), ("kp_4", 0x4B), ("kp_5", 0x4C), ("kp_6", 0x4D),
               ("kp_1", 0x4F), ("kp_2", 0x50), ("kp_3", 0x51), ("kp_0", 0x52), ("kp_.", 0x53)):
    NAMES[(_c, False)] = _n


def key_name(scan: int, extended: bool, vk: int) -> str:
    return NAMES.get((scan, extended)) or f"vk{vk:02x}"


class KeyState:
    """Turns raw hook events into recorded transitions (pure: tested without a hook)."""

    def __init__(self):
        self.down: set = set()

    def feed(self, name: str, up: bool, focused: bool) -> bool:
        """True if this event is a transition to record."""
        if up:
            if name in self.down:
                self.down.discard(name)
                return True
            return False
        if name in self.down or not focused:          # auto-repeat, or a key pressed into another window
            return False
        self.down.add(name)
        return True


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


def _user32():
    u = ctypes.WinDLL("user32", use_last_error=True)       # own instance: argtypes don't leak to keyboard.py
    u.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    u.SetWindowsHookExW.restype = wintypes.HHOOK
    u.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    u.CallNextHookEx.restype = LRESULT
    u.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    u.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    u.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    return u


class KeyLogger:
    def __init__(self, path, t0: float, focused=lambda: True, clock=time.perf_counter):
        self.path, self.t0, self.focused, self.clock = path, t0, focused, clock
        self.state = KeyState()
        self.n, self.lag_max = 0, 0
        self._f = None
        self._thread = None
        self._tid = None
        self._ready = threading.Event()
        self.error = None

    def start(self) -> "KeyLogger":
        self._f = open(self.path, "w", buffering=1, encoding="utf-8")
        self._thread = threading.Thread(target=self._run, name="keylog", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        return self

    def _record(self, name: str, up: bool, injected: bool, lag_ms: int) -> None:
        rec = {"t": round(self.clock() - self.t0, 4), "key": name, "down": not up}
        if injected:
            rec["inj"] = True
        if lag_ms >= 5:
            rec["lag"] = lag_ms
        self.lag_max = max(self.lag_max, lag_ms)
        self.n += 1
        self._f.write(json.dumps(rec) + "\n")

    def _run(self) -> None:
        u = _user32()
        k32 = ctypes.WinDLL("kernel32")
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        self._tid = k32.GetCurrentThreadId()

        def proc(code, wparam, lparam):
            if code == 0 and wparam in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
                try:
                    kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    up = bool(kb.flags & LLKHF_UP)
                    name = key_name(kb.scanCode, bool(kb.flags & LLKHF_EXTENDED), kb.vkCode)
                    if self.state.feed(name, up, up or self.focused()):
                        lag = (k32.GetTickCount() - kb.time) & 0xFFFFFFFF
                        self._record(name, up, bool(kb.flags & LLKHF_INJECTED), lag if lag < 60000 else 0)
                except Exception as e:                       # noqa: BLE001 - never break the player's keyboard
                    self.error = repr(e)
            return u.CallNextHookEx(None, code, wparam, lparam)

        self._proc = HOOKPROC(proc)                          # keep a reference: the hook calls into it
        hook = u.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, k32.GetModuleHandleW(None), 0)
        if not hook:
            self.error = f"SetWindowsHookEx failed ({ctypes.get_last_error()})"
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            u.UnhookWindowsHookEx(hook)

    def stop(self) -> None:
        if self._thread is not None and self._tid is not None:
            _user32().PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(2.0)
        if self._f is not None:
            t = round(self.clock() - self.t0, 4)
            for name in sorted(self.state.down):               # still held at the end: close them in the log
                self._f.write(json.dumps({"t": t, "key": name, "down": False, "end": True}) + "\n")
            self._f.close()
            self._f = None
