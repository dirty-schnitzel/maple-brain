"""The facts of one recording, written beside it as `session.json` by the recorder itself - nobody types them.

A recording is kept for years and read by tools that do not exist yet (PLAN-data.md: the one way footage is
collected). Its frames and keys say WHAT happened; this file says what that meant on the day:
  config    every tunable as it was (config.py): which key is the attack, the jump, the potions (`keys`), the
            weapon and its speed (`combat`) - "q went down" means nothing once the keys or the character change
  code      the git commit that recorded (and whether tracked files differed from it)
  client    when assets/mcw was built from the client export: the game data the map / mob names come from
  clock     `epoch` = the wall clock (seconds since 1970, UTC) at t = 0 of frames.jsonl / keys.jsonl
  capture   how the picture was taken (the capture kind, where in the window, the monitor's refresh rate)
  inputs    what each input file holds, in words: the format explains itself
  scene     the name of a staged scene (`record --scene NAME`), else null: ordinary play
"""
import ctypes
import json
import platform
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V = 1
# mouse buttons held, as bits of frames.jsonl's "b" (virtual-key code, bit): the physical buttons
BUTTONS = ((0x01, 1), (0x02, 2), (0x04, 4), (0x05, 8), (0x06, 16))
INPUTS = {
    "keys.jsonl": "one line per key going down or up while the game is focused: t, key, down (runtime/keylog.py)",
    "frames.jsonl": "one line per frame: n = its number, t = when it was grabbed, cur = the mouse in frame pixels "
                    "(absent: outside the game picture), b = mouse buttons held as bits 1 left, 2 right, 4 middle, "
                    "8 / 16 the side buttons (absent: none), drop = not in the video",
}


def buttons() -> int:
    """The mouse buttons held right now (bits: BUTTONS). Asked once per frame: a click is at least a few frames
    long, and asking costs microseconds - no hook sits in the mouse's path."""
    state = ctypes.windll.user32.GetAsyncKeyState
    return sum(bit for vk, bit in BUTTONS if state(vk) & 0x8000)


def code() -> dict:
    """The code that records: commit, branch, and whether a tracked file differs from the commit."""
    def git(*a):
        try:
            r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    dirty = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": None if dirty is None else bool(dirty)}


def client(assets: Path) -> str | None:
    """When the game data in `assets`/mcw was built from the client export (None: no game data there)."""
    try:
        return json.loads((Path(assets) / "mcw" / "manifest.json").read_text(encoding="utf-8")).get("built")
    except (OSError, ValueError):
        return None


def display() -> dict:
    """The main monitor's refresh rate, and whether Windows has the mouse buttons swapped (b = physical)."""
    try:
        from ctypes import wintypes
        u, g = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
        u.GetDC.restype, u.GetDC.argtypes = wintypes.HDC, (wintypes.HWND,)
        u.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
        g.GetDeviceCaps.argtypes = (wintypes.HDC, ctypes.c_int)
        dc = u.GetDC(None)
        try:
            hz = int(g.GetDeviceCaps(dc, 116))                # VREFRESH
        finally:
            u.ReleaseDC(None, dc)
        return {"refresh_hz": hz, "buttons_swapped": bool(u.GetSystemMetrics(23))}
    except Exception:                                         # noqa: BLE001 - a fact less, never a recording less
        return {}


def facts(cfg, by: str, assets: Path, scene: str | None = None, capture: dict | None = None) -> dict:
    """Everything known before a recording starts (asked once: the git calls take a moment). `started` / `epoch`
    are added by `write` at the recording's t = 0."""
    return {"v": V, "by": by, "scene": scene or None,
            "code": code(), "client": client(assets),
            "config": asdict(cfg) if is_dataclass(cfg) else dict(cfg or {}),
            "capture": {**(capture or {}), **display()},
            "inputs": INPUTS,
            "python": sys.version.split()[0], "os": platform.platform()}


def write(out: Path, base: dict | None, epoch: float, **more) -> dict:
    """`out`/session.json = `base` + the clock of this recording (+ `more`: what only this recording knows)."""
    at = datetime.fromtimestamp(epoch, timezone.utc)
    d = {**(base or {"v": V}), "started": at.astimezone().isoformat(timespec="milliseconds"),
         "started_utc": at.isoformat(timespec="milliseconds"), "epoch": round(epoch, 4)}
    for k, v in more.items():
        d[k] = {**d.get(k, {}), **v} if isinstance(v, dict) and isinstance(d.get(k), dict) else v
    Path(out, "session.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
    return d
