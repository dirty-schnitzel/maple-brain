"""Experiment 3: minimal find-and-attack loop.

Each tick: stand still and take a 4-frame look -> find self (name-tag template) -> moving blobs that are
not characters/cursor and are on our level -> nearest one: walk toward it, or face it and attack.

Safety: keys only while MapleStory has focus (leaving the game aborts and releases every key);
hard time limit; stays on a leash around the start position (minimap); aborts if it can't find itself
or if the first walk doesn't move the minimap dot (input blocked).

Usage: python -I hunt.py <out_dir> [--seconds 60] [--attack space] [--leash 18]
"""
import argparse
import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path

import cv2
import mss
import numpy as np

sys.path.append(str(Path(__file__).parent))
from experiment1 import Keys, client_box, game_columns, user32  # noqa: E402
from perception import find_self, find_tags, mob_candidates, tag_body  # noqa: E402

class FocusLost(Exception):
    pass


class StrictKeys(Keys):
    """No grace period: a key is only sent while the game has focus, otherwise FocusLost."""

    def _guard(self, grace_s=0.0):
        if not self.focused():
            self.release_all()
            raise FocusLost()


def foreground_title():
    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(fg, buf, 256)
    return buf.value


def fmt(dot):
    return f"({dot[0]:.1f},{dot[1]:.1f})" if dot else "None"


ATTACK_RANGE = 75       # px between our centre and the target's centre to swing
SAME_LEVEL = 35         # px: target's bottom must be this close to our feet
LOOK_FRAMES, LOOK_GAP = 4, 0.12
MIN_ALIGNMENT = 0.15    # below this the look didn't see a steady game picture
SETTLE_S = 0.35         # let the camera stop sliding after a walk


class Screen:
    def __init__(self, hwnd):
        self.box = client_box(hwnd)
        self.sct = mss.MSS()
        self.cols = None

    def grab(self):
        raw = np.asarray(self.sct.grab(self.box))[:, :, :3]
        if self.cols is None:
            self.cols = game_columns(raw)
        return cv2.resize(raw[:, self.cols[0]:self.cols[1]], (1366, 768), interpolation=cv2.INTER_AREA)

    def cursor(self):
        """Mouse position in normalized frame coordinates, or None if outside the game picture."""
        p = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(p))
        s = self.box["height"] / 768
        x = (p.x - self.box["left"] - self.cols[0]) / s
        y = (p.y - self.box["top"]) / s
        return (x, y) if 0 <= x < 1366 and 0 <= y < 768 else None


def minimap_dot(frame):
    mm = frame[66:186, 4:210]
    m = cv2.inRange(cv2.cvtColor(mm, cv2.COLOR_BGR2HSV), np.array((20, 150, 180), np.uint8),
                    np.array((35, 255, 255), np.uint8))
    n, _, st, ce = cv2.connectedComponentsWithStats(m)
    dots = [tuple(ce[i]) for i in range(1, n) if st[i][4] >= 4 and st[i][2] <= 8 and st[i][3] <= 8]
    return dots[0] if len(dots) == 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--attack", default="space")
    ap.add_argument("--leash", type=float, default=18, help="max minimap px from start")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "log.txt", "w", buffering=1, encoding="utf-8")
    t0 = time.perf_counter()

    def say(msg):
        line = f"{time.perf_counter() - t0:6.2f}s {msg}"
        print(line.encode("ascii", "replace").decode())
        logf.write(line + "\n")

    template = np.load(Path(__file__).parent.parent / "assets" / "self_tag.npy")
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

    keys, screen = StrictKeys(hwnd), Screen(hwnd)
    last_fg, no_move_walks = None, 0
    stats = {"ticks": 0, "attacks": 0, "walks": 0, "walks_moved": 0, "no_target": 0, "self_lost": 0,
             "focus_pauses": 0, "low_alignment": 0, "stuck_jumps": 0}
    start_dot, input_verified, patrol_dir = None, False, "left"
    lost, idle_looks, saved = 0, 0, 0
    status = "ok"
    end = time.perf_counter() + a.seconds
    try:
        while time.perf_counter() < end:
          try:
            fg = foreground_title()
            if fg != last_fg:
                say(f"foreground window: '{fg}'")
                last_fg = fg
            if not keys.focused():
                raise FocusLost()
            stats["ticks"] += 1
            frames = []
            for _ in range(LOOK_FRAMES):
                frames.append(screen.grab())
                time.sleep(LOOK_GAP)
            frame = frames[-1]
            dot = minimap_dot(frame)
            if start_dot is None and dot is not None:
                start_dot = dot
            me = find_self(frame, template)
            if me is None:
                lost += 1
                stats["self_lost"] += 1
                say(f"self not found ({lost})")
                if lost >= 3:
                    raise RuntimeError("lost track of own character 3 times in a row")
                continue
            lost = 0
            px, feet = me[0] + me[2] / 2, me[1]
            cands, resp, bodies = mob_candidates(frames, me[:4], screen.cursor())
            if resp < MIN_ALIGNMENT:
                stats["low_alignment"] += 1
                say(f"frame alignment {resp:.2f}: not a steady game picture, skipping")
                cv2.imwrite(str(out / f"t{stats['ticks']:03d}_lowalign.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                continue
            level = [c for c in cands if abs(c[1] + c[3] - feet) <= SAME_LEVEL]
            off_leash = dot is not None and start_dot is not None and abs(dot[0] - start_dot[0]) > a.leash

            def allowed(direction):
                if not off_leash:
                    return True
                return (direction == "right") == (dot[0] < start_dot[0])   # only back toward start

            target, action = None, None
            if level:
                target = min(level, key=lambda c: abs(c[0] + c[2] / 2 - px))
                dx = target[0] + target[2] / 2 - px
                direction = "left" if dx < 0 else "right"
                if abs(dx) <= ATTACK_RANGE:
                    action = f"attack {direction} (dx {dx:+.0f})"
                elif allowed(direction):
                    action = f"walk {direction} (dx {dx:+.0f})"
                else:
                    action = f"skip target {direction} (off leash)"
            if action is None or action.startswith("skip"):
                idle_looks += 1
                stats["no_target"] += 1
                if idle_looks >= 3:
                    if not allowed(patrol_dir):
                        patrol_dir = "right" if patrol_dir == "left" else "left"
                    action = f"patrol {patrol_dir}"
            else:
                idle_looks = 0

            say(f"me@({px:.0f},{feet}) dot={fmt(dot)} align={resp:.2f} "
                f"cands={len(cands)} level={len(level)} -> {action or 'wait'}")
            if saved < 120:
                vis = frame.copy()
                for x, y, w, h in bodies:
                    cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 0, 255), 1)
                for x, y, w, h in cands:
                    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 165, 255), 1)
                if target:
                    x, y, w, h = target
                    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.putText(vis, action or "wait", (230, 225), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.imwrite(str(out / f"t{stats['ticks']:03d}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 80])
                saved += 1

            if action is None:
                continue
            verb, direction = action.split()[:2]
            if verb == "attack":
                keys.tap(direction, down_s=0.04, gap_s=0.05)          # face the target
                keys.tap(a.attack, n=2, down_s=0.08, gap_s=0.45)
                stats["attacks"] += 1
                no_move_walks = 0
            elif verb in ("walk", "patrol"):
                if verb == "walk":
                    secs = min(0.8, max(0.15, (abs(target[0] + target[2] / 2 - px) - ATTACK_RANGE / 2) / 350))
                else:
                    secs, idle_looks = 0.6, 0
                    patrol_dir = "right" if patrol_dir == "left" else "left"
                before = minimap_dot(screen.grab())
                keys.hold(direction, secs)
                stats["walks"] += 1
                time.sleep(SETTLE_S)
                after = minimap_dot(screen.grab())
                moved = after[0] - before[0] if before and after else None
                say(f"   walked {direction} {secs:.2f}s: dot {fmt(before)} -> {fmt(after)}"
                    f" (moved {moved:+.1f})" if moved is not None else f"   walked {direction} {secs:.2f}s: dot unreadable")
                if moved is not None and abs(moved) >= 0.5:
                    stats["walks_moved"] += 1
                    no_move_walks = 0
                    if not input_verified:
                        input_verified = True
                        say("input verified: minimap dot moved")
                elif moved is not None:
                    no_move_walks += 1
                    if no_move_walks >= 3:
                        say("   stuck: 3 walks without moving -> jump toward target")
                        keys.down(direction)
                        keys.tap("shift")
                        time.sleep(0.3)
                        keys.up(direction)
                        stats["stuck_jumps"] += 1
                        no_move_walks = 0
                        time.sleep(SETTLE_S)
          except FocusLost:
            keys.release_all()
            stats["focus_pauses"] += 1
            say(f"PAUSED: game not focused (foreground: '{foreground_title()}'); keys released, waiting...")
            while not keys.focused() and time.perf_counter() < end:
                time.sleep(0.2)
            if keys.focused():
                say("resumed: game focused again")
                last_fg = None
                time.sleep(1.0)
    except Exception as e:                       # noqa: BLE001
        status = f"aborted: {e}"
    finally:
        keys.release_all()
    say(status)
    say(f"stats {json.dumps(stats)}")
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
