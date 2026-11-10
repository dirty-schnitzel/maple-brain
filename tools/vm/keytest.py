"""Do SendInput keys from this PC reach a VMware guest? (branch `vm`, 2026-11-10)

Setup (the user): in the guest, open Notepad and click into it, so NOTEPAD is the guest's focused window, not the
game. Then run this on the host; it waits up to --wait s for the VMware window to be in front, then types the
letters of --text (one SendInput key-down/up each, humanly spaced), and stops. It sends nothing unless the VMware
frame window is the foreground window, and stops at once if focus moves away.

    python tools\\vm\\keytest.py [--text vmtest] [--wait 60]

Pass = the letters appear in the guest's Notepad.
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from maplebrain.capture import Screen, find_window  # noqa: E402
from maplebrain.keyboard import SCAN, _send, user32  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="vmtest")
    ap.add_argument("--wait", type=float, default=60)
    a = ap.parse_args()
    if any(c not in SCAN for c in a.text):
        ap.error("letters / digits only")
    hwnd = find_window("vmware")
    if not hwnd:
        print("VMware Workstation window not found")
        return 1
    print(f"waiting up to {a.wait:.0f} s for the VMware window to be in front "
          "(guest: Notepad focused, NOT the game)...", flush=True)
    end = time.perf_counter() + a.wait
    while user32.GetForegroundWindow() != hwnd:
        if time.perf_counter() > end:
            print("VMware never came to front: nothing sent")
            return 1
        time.sleep(0.2)
    time.sleep(random.uniform(1.0, 1.5))
    shot = Screen(hwnd).grab()                          # what the guest shows right now (the bot's own capture)
    out = Path(__file__).resolve().parents[2] / "runs" / "vm"
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "keytest.png"), shot)
    grey = float(((shot.max(axis=2).astype(int) - shot.min(axis=2)) < 12).mean())
    if grey < 0.5:                                      # Notepad is flat white / grey; a game picture is colourful
        print(f"the guest screen isn't mostly flat ({grey:.0%} grey): Notepad not in front? nothing sent "
              f"(see {out / 'keytest.png'})")
        return 1
    for c in a.text:
        if user32.GetForegroundWindow() != hwnd:
            print("focus left VMware: stopped")
            return 1
        _send(c, False)
        time.sleep(random.uniform(0.05, 0.11))
        _send(c, True)
        time.sleep(random.uniform(0.12, 0.25))
    print(f"sent {a.text!r}: does it show in the guest's Notepad?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
