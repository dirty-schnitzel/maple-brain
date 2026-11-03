"""Experiment 4: find-and-attack loop, v2.

Changes from v1 (hunt.py):
  * HP read every tick from the HP bar; below --hp-stop (default 45%) -> release keys, beep, stop. 0 HP = dead.
  * Acts only on steady looks (camera alignment >= 0.8); otherwise looks again.
  * Commits to a target and tracks it between ticks by its expected position.
  * Walks to ~45px from the target and attacks from <= 60px; keeps swinging while the target is still there.
  * Walking speed (screen px/s) is learned from how much closer each walk brought us to the target.
  * Leash of 40 minimap px around the start.

Usage (elevated): python -I hunt2.py <out_dir> [--seconds 60] [--attack space] [--jump shift] [--leash 40]
"""
import argparse
import json
import sys
import time
import winsound
from pathlib import Path

import cv2
import numpy as np

sys.path.append(str(Path(__file__).parent))
from experiment1 import user32  # noqa: E402
from hunt import FocusLost, Screen, StrictKeys, fmt, foreground_title, minimap_dot  # noqa: E402
from perception import find_self, mob_candidates  # noqa: E402

ATTACK_DX = 60          # centre-to-centre px: close enough to swing
APPROACH_STOP = 45      # walk until about this far away
SAME_LEVEL = 35         # target's bottom within this many px of our feet
MIN_ALIGN = 0.8         # only act on looks where the camera was steady
TRACK_PX = 50           # a candidate this close to where we expected the target is the same target
LOOK_FRAMES, LOOK_GAP, SETTLE_S = 4, 0.12, 0.35
HP_BOX = (503, 751, 607, 764)


def hp_fill(frame):
    """Fraction of the HP bar's columns that are red. ~1.0 full, 0.0 empty/dead."""
    x0, y0, x1, y1 = HP_BOX
    hsv = cv2.cvtColor(frame[y0:y1 + 1, x0:x1 + 1], cv2.COLOR_BGR2HSV)
    red = (((hsv[:, :, 0] < 8) | (hsv[:, :, 0] > 170)) & (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 120))
    return float((red.mean(axis=0) > 0.4).mean())


def alarm():
    for _ in range(3):
        winsound.Beep(1200, 250)
        winsound.Beep(800, 250)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--attack", default="space")
    ap.add_argument("--jump", default="shift")
    ap.add_argument("--leash", type=float, default=40)
    ap.add_argument("--hp-stop", type=float, default=0.45)
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
    stats = {"ticks": 0, "unsteady": 0, "attack_rounds": 0, "walks": 0, "walks_moved": 0, "no_target": 0,
             "target_switches": 0, "focus_pauses": 0, "speed_px_s": None}
    speed = 125.0                    # screen px/s, refined while walking
    start_dot, facing, patrol_dir = None, None, "left"
    expected_dx, last_walk, idle, lost, unsteady_streak, saved = None, None, 0, 0, 0, 0
    hp_seen = None
    status = "ok"
    end = time.perf_counter() + a.seconds
    try:
        while time.perf_counter() < end:
            try:
                if not keys.focused():
                    raise FocusLost()
                stats["ticks"] += 1
                frames = []
                for _ in range(LOOK_FRAMES):
                    frames.append(screen.grab())
                    time.sleep(LOOK_GAP)
                frame = frames[-1]

                # ---- survival first
                hp = hp_fill(frame)
                if hp_seen is None:
                    hp_seen = hp
                    say(f"starting HP bar fill {hp:.0%}")
                if hp < a.hp_stop:
                    keys.release_all()
                    status = f"STOPPED: HP at {hp:.0%} (threshold {a.hp_stop:.0%})" + (" - character is dead" if hp == 0 else "")
                    for i, f in enumerate(frames):
                        cv2.imwrite(str(out / f"STOP_{i}.png"), f)
                    alarm()
                    break

                dot = minimap_dot(frame)
                if start_dot is None and dot is not None:
                    start_dot = dot
                me = find_self(frame, template)
                if me is None:
                    lost += 1
                    say(f"self not found ({lost})")
                    if lost >= 3:
                        raise RuntimeError("lost track of own character 3 times in a row")
                    continue
                lost = 0
                px, feet = me[0] + me[2] / 2, me[1]
                cands, resp, bodies = mob_candidates(frames, me[:4], screen.cursor())
                if resp < MIN_ALIGN:
                    stats["unsteady"] += 1
                    say(f"unsteady look (align {resp:.2f}) dot={fmt(dot)} HP {hp:.0%}")
                    if saved < 150:
                        cv2.imwrite(str(out / f"t{stats['ticks']:03d}_unsteady.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        saved += 1
                    unsteady_streak += 1
                    if unsteady_streak >= 3:
                        time.sleep(0.3)
                    continue
                unsteady_streak = 0
                level = [c for c in cands if abs(c[1] + c[3] - feet) <= SAME_LEVEL]
                rels = [(c[0] + c[2] / 2 - px, c) for c in level]

                # ---- pick target: keep the one we were tracking if it's where we expected
                target = None
                if expected_dx is not None and rels:
                    dx_c, c = min(rels, key=lambda r: abs(r[0] - expected_dx))
                    if abs(dx_c - expected_dx) <= TRACK_PX:
                        target = (dx_c, c)
                        if last_walk:                # learn walking speed from the progress we made
                            secs, before = last_walk
                            progress = abs(before) - abs(dx_c)
                            if progress > 5:
                                speed = float(np.clip(0.6 * speed + 0.4 * progress / secs, 60, 300))
                if target is None and rels:
                    if expected_dx is not None:
                        stats["target_switches"] += 1
                    target = min(rels, key=lambda r: abs(r[0]))
                last_walk = None

                off_leash = dot is not None and start_dot is not None and abs(dot[0] - start_dot[0]) > a.leash

                def allowed(direction):
                    return not off_leash or (direction == "right") == (dot[0] < start_dot[0])

                action = "wait"
                if target:
                    dx = target[0]
                    direction = "left" if dx < 0 else "right"
                    if abs(dx) <= ATTACK_DX:
                        action = f"attack {direction}"
                    elif allowed(direction):
                        action = f"walk {direction}"
                    else:
                        action, target = "skip (off leash)", None
                if target is None:
                    expected_dx = None
                    idle += 1
                    stats["no_target"] += 1
                    if idle >= 3:
                        if not allowed(patrol_dir):
                            patrol_dir = "right" if patrol_dir == "left" else "left"
                        action = f"patrol {patrol_dir}"
                else:
                    idle = 0

                say(f"HP {hp:.0%} me@({px:.0f},{feet}) dot={fmt(dot)} align={resp:.2f} level={len(level)} "
                    f"target_dx={target[0]:+.0f} " if target else
                    f"HP {hp:.0%} me@({px:.0f},{feet}) dot={fmt(dot)} align={resp:.2f} level={len(level)} no target ")
                say(f"   -> {action} (speed {speed:.0f}px/s)")
                if saved < 150:
                    vis = frame.copy()
                    for x, y, w, h in bodies:
                        cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 0, 255), 1)
                    for x, y, w, h in level:
                        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 165, 255), 1)
                    if target:
                        x, y, w, h = target[1]
                        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
                    cv2.putText(vis, f"{action}  HP {hp:.0%}", (230, 225), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.imwrite(str(out / f"t{stats['ticks']:03d}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    saved += 1

                verb = action.split()[0]
                if verb == "attack":
                    direction = action.split()[1]
                    if facing != direction:
                        keys.tap(direction, down_s=0.04, gap_s=0.08)
                        facing = direction
                    keys.tap(a.attack, n=3, down_s=0.08, gap_s=0.42)
                    stats["attack_rounds"] += 1
                    expected_dx = target[0]
                elif verb in ("walk", "patrol"):
                    direction = action.split()[1]
                    if verb == "walk":
                        secs = float(np.clip((abs(target[0]) - APPROACH_STOP) / speed, 0.08, 0.8))
                    else:
                        secs, idle = 0.6, 0
                        patrol_dir = "right" if patrol_dir == "left" else "left"
                    before = minimap_dot(screen.grab())
                    keys.hold(direction, secs)
                    facing = direction
                    stats["walks"] += 1
                    time.sleep(SETTLE_S)
                    after = minimap_dot(screen.grab())
                    if before and after and abs(after[0] - before[0]) >= 0.5:
                        stats["walks_moved"] += 1
                    say(f"   walked {direction} {secs:.2f}s: dot {fmt(before)} -> {fmt(after)}")
                    if verb == "walk":
                        sign = -1 if direction == "left" else 1
                        expected_dx = target[0] - sign * speed * secs
                        last_walk = (secs, target[0])
                    else:
                        expected_dx = None
            except FocusLost:
                keys.release_all()
                stats["focus_pauses"] += 1
                say(f"PAUSED: game not focused (foreground: '{foreground_title()}'); keys released, waiting...")
                while not keys.focused() and time.perf_counter() < end:
                    time.sleep(0.2)
                if keys.focused():
                    say("resumed: game focused again")
                    expected_dx = None
                    time.sleep(1.0)
    except Exception as e:                       # noqa: BLE001
        status = f"aborted: {e}"
    finally:
        keys.release_all()
    stats["speed_px_s"] = round(speed)
    say(status)
    say(f"stats {json.dumps(stats)}")
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
