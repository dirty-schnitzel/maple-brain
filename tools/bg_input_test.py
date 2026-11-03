"""Test: does MapleStory accept keys posted to its window while it is NOT the foreground window?

Waits until another app is in front, then runs labelled phases (walk right, jump, attack) with
different message methods. Watch the character: note which phase number made it move.
Run elevated (the game is elevated; Windows blocks messages from a lower-integrity process).
"""
import ctypes
import random
import sys
import time

sys.path.insert(0, __file__.rsplit("\\tools", 1)[0])
from maplebot.capture import find_window  # noqa: E402
from maplebot.keyboard import EXTENDED, SCAN, foreground_title, user32  # noqa: E402

WM_KEYDOWN, WM_KEYUP, WM_ACTIVATE, WM_SETFOCUS = 0x100, 0x101, 0x006, 0x007
VK = {"right": 0x27, "left": 0x25, "shift": 0x10, "space": 0x20}


def lparam(key, up):
    code = EXTENDED.get(key) or SCAN[key]
    lp = 1 | (code << 16)
    if key in EXTENDED:
        lp |= 1 << 24
    if up:
        lp |= (1 << 30) | (1 << 31)
    return ctypes.c_ssize_t(lp - (1 << 32) if lp >= 1 << 31 else lp)


def send(hwnd, fn, key, up):
    ctypes.set_last_error(0)
    ok = fn(hwnd, WM_KEYUP if up else WM_KEYDOWN, VK[key], lparam(key, up))
    err = ctypes.get_last_error()
    if err:
        print(f"    {fn.__name__}({key}, up={up}) -> {ok}, error {err}")


def press(hwnd, fn, key, hold):
    send(hwnd, fn, key, False)
    end = time.time() + hold
    while time.time() < end:  # repeat keydowns like a held physical key
        time.sleep(random.uniform(0.03, 0.05))
        if key in ("right", "left"):
            send(hwnd, fn, key, False)
    send(hwnd, fn, key, True)
    time.sleep(random.uniform(0.25, 0.45))


def phase(n, name, hwnd, fn, prep=None):
    if user32.GetForegroundWindow() == hwnd:
        print(f"Phase {n} SKIPPED: the game is in front (test invalid) - click another app")
        return
    print(f"\n=== Phase {n}: {name} (foreground: '{foreground_title()}') ===")
    if prep:
        prep()
    press(hwnd, fn, "right", random.uniform(0.9, 1.3))
    press(hwnd, fn, "left", random.uniform(0.9, 1.3))
    press(hwnd, fn, "shift", random.uniform(0.08, 0.14))
    press(hwnd, fn, "space", random.uniform(0.08, 0.14))
    time.sleep(random.uniform(2.5, 3.5))


def main():
    hwnd = find_window()
    if not hwnd:
        sys.exit("MapleStory window not found")
    print(f"Game window {hwnd:#x}. Click into ANOTHER app now (keep the game visible)...")
    deadline = time.time() + 60
    while user32.GetForegroundWindow() == hwnd:
        if time.time() > deadline:
            sys.exit("Game stayed in front for 60 s - aborted")
        time.sleep(0.2)
    time.sleep(random.uniform(9.0, 11.0))
    user32.PostMessageW.argtypes = user32.SendMessageW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]

    phase(1, "PostMessage keys", hwnd, user32.PostMessageW)
    phase(2, "SendMessage keys", hwnd, user32.SendMessageW)
    phase(3, "fake WM_ACTIVATE/WM_SETFOCUS, then PostMessage keys", hwnd, user32.PostMessageW,
          prep=lambda: (user32.SendMessageW(hwnd, WM_ACTIVATE, 1, 0),
                        user32.SendMessageW(hwnd, WM_SETFOCUS, 0, 0)))
    print("\nDone. Which phase (1/2/3) made the character walk/jump/attack, if any?")


if __name__ == "__main__":
    main()
