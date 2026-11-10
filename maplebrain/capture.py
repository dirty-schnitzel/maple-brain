"""Game window capture, normalized to the game's native 1366x768.

Classic World renders 1366x768 and scales it to fill the screen (pillarboxed on wide monitors), so every frame
is cropped to the game picture and scaled back to 1366x768: one set of coordinates on any monitor.
The game runs either on this PC (`--window maplestory`, default) or in a VMware guest (`--window vmware`): then the
picture is the guest display inside the VMware window, read off this PC's screen like the game window is.
"""
import ctypes
import time
from ctypes import wintypes

import cv2
import mss
import numpy as np

from .config import WINDOWS

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetProcessDPIAware()
W, H = 1366, 768

# The game in a VMware Workstation guest (`--window vmware`, 2026-11-10, a private server): keys go to the VMware
# frame window (it must be the foreground window, as the game itself must be), the picture is the guest display
# inside it. Measured on the host: VMUIFrame 'Windows 11 x64 - VMware Workstation' -> ... -> MKSEmbedded
# 'MKSWindow#0' = the guest screen 1:1 (2143x1164 = the guest resolution while autofit follows the window).
VMWARE_FRAME, VMWARE_VIEW = "VMUIFrame", "MKSEmbedded"
_ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _class(hwnd) -> str:
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, b, 256)
    return b.value


def find_window(window: str = "maplestory"):
    """The window that must be in front while keys are sent: the game's own, or the VMware frame around the guest."""
    if window == "maplestory":
        return user32.FindWindowW(None, "MapleStory")
    if window == "vmware":
        return user32.FindWindowW(VMWARE_FRAME, None)
    raise ValueError(f"unknown window {window!r} (one of {WINDOWS})")    # config.WINDOWS


def picture_window(hwnd):
    """The window whose client area is the game picture: the game window itself, or for the VMware frame the
    largest visible guest display (MKSEmbedded) inside it. Looked up on every calibrate: VMware recreates it when
    switching views (fullscreen, tabs). 0 = no guest display (the VM is off / on its library page)."""
    if _class(hwnd) != VMWARE_FRAME:
        return hwnd
    found = []

    def each(h, _):
        if _class(h) == VMWARE_VIEW and user32.IsWindowVisible(h):
            r = wintypes.RECT()
            user32.GetClientRect(h, ctypes.byref(r))
            found.append((r.right * r.bottom, h))
        return True
    user32.EnumChildWindows(hwnd, _ENUM(each), 0)
    return max(found)[1] if found else 0


def client_box(hwnd) -> dict:
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return {"left": p.x, "top": p.y, "width": r.right, "height": r.bottom}


def game_columns(raw: np.ndarray) -> tuple[int, int]:
    """x-range of the game picture inside the black pillarbox bars.
    pkg_sight6: 'any lit pixel in the column' let something small in a bar at startup (cursor, popup) widen the
    crop by ~34 px -> the whole frame squeezed 1.3 %, quickslots 13 px off, potions read as gone, bot stopped.
    Now a column belongs to the game only if a good share of its rows is lit, and the width is the game's
    1366:768 shape at this height; if the lit columns don't match that width, the game is centred (pillarboxing
    is symmetric)."""
    h, w = raw.shape[:2]
    want = min(w, round(h * W / H))
    centred = ((w - want) // 2, (w - want) // 2 + want)
    lit = np.where((raw.max(axis=2) > 12).mean(axis=0) > 0.3)[0]
    if len(lit) == 0 or abs((int(lit[-1]) + 1 - int(lit[0])) - want) > 2:
        return centred                      # (a dark game edge, or something tall lit in a bar)
    return int(lit[0]), int(lit[0]) + want


def normalize(raw: np.ndarray) -> np.ndarray:
    return cv2.resize(raw, (W, H), interpolation=cv2.INTER_AREA)


class Screen:
    """Latest game frame as BGR 1366x768. Uses DXGI desktop duplication (dxcam) when available, else mss."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self._mss = mss.MSS()
        self.cam, self.kind, self.note = None, "mss", ""
        self.calibrate()

    def calibrate(self):
        """Find the game picture (inside the pillarbox bars) and capture just that. Must run while the game is in
        front: measured with another window on top, the bars aren't black and the whole desktop gets squeezed
        into the frame (manual serve 2026-11-01: HP/EXP misread, no name tag, nothing found)."""
        view = picture_window(self.hwnd)
        if not view:
            raise RuntimeError("no guest display in the VMware window (is the VM running and shown?)")
        self.box = client_box(view)
        raw = np.asarray(self._mss.grab(self.box))[:, :, :3]
        self.cols = game_columns(raw)
        self.close()
        self.cam = None
        try:
            import dxcam
            region = (self.box["left"] + self.cols[0], self.box["top"],
                      self.box["left"] + self.cols[1], self.box["top"] + self.box["height"])
            self.cam = dxcam.create(output_color="BGR")
            self.cam.start(region=region, target_fps=60, video_mode=True)
            time.sleep(0.3)
            f = self.cam.get_latest_frame()
            if f is None or f.max() < 10:
                raise RuntimeError("dxcam returned an empty frame")
            self.kind, self.note = "dxcam", ""
        except Exception as e:                      # noqa: BLE001 - any failure: fall back to mss
            self.close()
            self.cam, self.kind, self.note = None, "mss", str(e)
        return self.cols

    def grab(self) -> np.ndarray:
        if self.cam is not None:
            return normalize(self.cam.get_latest_frame())
        raw = np.asarray(self._mss.grab(self.box))[:, :, :3]
        return normalize(raw[:, self.cols[0]:self.cols[1]])

    def cursor(self):
        """Mouse position in frame coordinates, or None when outside the game picture."""
        p = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(p))
        s = self.box["height"] / H
        x, y = (p.x - self.box["left"] - self.cols[0]) / s, (p.y - self.box["top"]) / s
        return (x, y) if 0 <= x < W and 0 <= y < H else None

    def close(self):
        if self.cam is not None:
            try:
                self.cam.stop()
            except Exception:                       # noqa: BLE001
                pass
