"""Experiment 5: detect once, then track. Walk to the nearest mob without stopping and hit it until it's gone.

States:
  SEEK      stand still for one short look (motion), pick the nearest mob on our level, copy it as a template
  APPROACH  hold the direction key; every frame re-find the mob by template match and stop when in range
  ATTACK    face it and hold attack while tracking it; when it's gone for ~0.4s it's dead -> SEEK

Safety: keys only while the game has focus (otherwise pause + release); HP/positions are trusted only in frames
where our own name tag was found (proves the frame is the game); HP below --hp-stop on 2 frames in a row ->
release, beep, stop; leash around the start position; time limit; screenshots saved on every state change and stop.

Usage (elevated): python -I hunt3.py <out_dir> [--seconds 60] [--attack space] [--leash 40]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.append(str(Path(__file__).parent))
from experiment1 import user32  # noqa: E402
from hunt import FocusLost, Screen, StrictKeys, fmt, foreground_title, minimap_dot  # noqa: E402
from hunt2 import alarm  # noqa: E402
from perception import (bar_mob_box, find_mob_bars, find_self, find_tags, moving_blobs,  # noqa: E402
                        overlaps, tag_body)

ATTACK_DX = 60           # centre-to-centre px to start swinging
RE_APPROACH_DX = 90      # target drifted this far while attacking -> walk again
SAME_LEVEL = 35
MIN_ALIGN = 0.7
LOOK_FRAMES, LOOK_GAP = 4, 0.1
TRACK_MIN_SCORE = 0.68
LOST_FRAMES_DEAD = 6     # target missing this many frames in a row while attacking -> killed
APPROACH_TIMEOUT, ATTACK_TIMEOUT = 4.0, 8.0
REPEAT_S = 0.05          # key-down repeat while holding (real keyboards repeat ~30/s)


HP_BOX = (503, 751, 607, 764)


def hp_fill(frame):
    """Filled share of the HP bar. Filled is red (pale pink when HP is low); empty is grey (saturation ~0)."""
    x0, y0, x1, y1 = HP_BOX
    hsv = cv2.cvtColor(frame[y0:y1 + 1, x0:x1 + 1], cv2.COLOR_BGR2HSV)
    red = (((hsv[:, :, 0] < 10) | (hsv[:, :, 0] > 170)) & (hsv[:, :, 1] > 50) & (hsv[:, :, 2] > 100))
    return float((red.mean(axis=0) > 0.4).mean())


def candidates(frames, me_box, cursor):
    """Moving blobs + mobs under HP bars, minus characters (name tags without a mob bar) and the cursor."""
    frame = frames[-1]
    bars = find_mob_bars(frame)
    bar_mobs = [bar_mob_box(b) for b in bars]
    blobs, resp = moving_blobs(frames) if len(frames) > 1 else ([], 1.0)
    bodies = [tag_body(me_box)]
    for t in find_tags(frame):
        body = tag_body(t)
        if not any(overlaps(body, m, pad=0) for m in bar_mobs):     # a tag under a mob HP bar is a mob's
            bodies.append(body)
    out = list(bar_mobs)
    for b in blobs:
        if any(overlaps(b, body, pad=0) for body in bodies) or any(overlaps(b, m) for m in bar_mobs):
            continue
        if cursor and abs(b[0] + b[2] / 2 - cursor[0]) < 40 and abs(b[1] + b[3] / 2 - cursor[1]) < 40:
            continue
        out.append(b)
    return out, resp, bars


def gray(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


class Tracker:
    """Follows one mob by template matching (plus its mirror image, mobs turn around) in a window around it."""

    def __init__(self, frame, box, pad=4):
        x, y, w, h = box
        x, y = max(0, x - pad), max(0, y - pad)
        self.box = (x, y, w + 2 * pad, h + 2 * pad)
        self.tpl = gray(frame)[y:y + self.box[3], x:x + self.box[2]].copy()
        self.lost, self.frames, self.score = 0, 0, 1.0

    def centre(self):
        x, y, w, h = self.box
        return x + w / 2, y + h

    def update(self, frame, refresh=False):
        g = gray(frame)
        H, W = g.shape
        x, y, w, h = self.box
        x0, y0, x1, y1 = max(0, x - 50), max(0, y - 25), min(W, x + w + 50), min(H, y + h + 25)
        win = g[y0:y1, x0:x1]
        best, best_loc = -1.0, None
        for t in (self.tpl, cv2.flip(self.tpl, 1)):
            if win.shape[0] < t.shape[0] or win.shape[1] < t.shape[1]:
                continue
            _, s, _, loc = cv2.minMaxLoc(cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED))
            if s > best:
                best, best_loc = s, loc
        self.frames += 1
        self.score = best
        if best < TRACK_MIN_SCORE:
            self.lost += 1
            return False
        self.lost = 0
        self.box = (x0 + best_loc[0], y0 + best_loc[1], w, h)
        if refresh and best > 0.8 and self.frames % 6 == 0:      # follow the walk animation
            bx, by = self.box[:2]
            self.tpl = g[by:by + h, bx:bx + w].copy()
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--attack", default="space")
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
    stats = {"looks": 0, "targets": 0, "kills": 0, "approach_timeouts": 0, "attack_timeouts": 0,
             "lost_while_approaching": 0, "off_leash_skips": 0, "focus_pauses": 0, "frames": 0}
    state, tracker, state_t, held = "SEEK", None, time.perf_counter(), None
    me_pos, start_dot, facing, idle_looks, patrol_dir, shots = None, None, None, 0, "left", 0
    hp_hist, bar_gone = [], 0
    status = "ok"
    end = time.perf_counter() + a.seconds

    def shot(tag, frame):
        nonlocal shots
        if shots < 200:
            vis = frame.copy()
            if tracker:
                x, y, w, h = tracker.box
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(vis, tag, (230, 225), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imwrite(str(out / f"{shots:03d}_{tag.split()[0]}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 80])
            shots += 1

    def hold(key):
        """Keep `key` held (re-sending key-down like keyboard auto-repeat); releases any other held key."""
        nonlocal held
        if held and held != key:
            keys.up(held)
        keys.down(key)
        held = key

    def release():
        nonlocal held
        if held:
            keys.up(held)
            held = None

    def go(new_state, why, frame=None):
        nonlocal state, state_t
        release()
        say(f"{state} -> {new_state}: {why}")
        state, state_t = new_state, time.perf_counter()
        if frame is not None:
            shot(f"{new_state} {why}", frame)

    try:
        while time.perf_counter() < end:
            try:
                if not keys.focused():
                    raise FocusLost()
                frame = screen.grab()
                if not keys.focused():                    # don't trust a frame grabbed while leaving the game
                    raise FocusLost()
                stats["frames"] += 1
                me = find_self(frame, template, near=me_pos, radius=220) if me_pos else find_self(frame, template)
                if me is None and me_pos is not None:
                    me = find_self(frame, template)
                if me is None:
                    release()
                    time.sleep(0.05)
                    continue                              # not a trustworthy frame (or we're hidden): don't act
                me_pos = (me[0] + me[2] / 2, me[1])
                px, feet = me_pos

                # ---- survival: only from frames proven to be the game
                hp_hist = (hp_hist + [hp_fill(frame)])[-6:]
                hp = max(hp_hist)                         # robust to the low-HP flashing
                if len(hp_hist) >= 3 and hp < a.hp_stop:
                    keys.release_all()
                    cv2.imwrite(str(out / "STOP.png"), frame)
                    status = f"STOPPED: HP {hp:.0%} (best of last {len(hp_hist)} frames) below {a.hp_stop:.0%}"
                    alarm()
                    break

                dot = minimap_dot(frame)
                if start_dot is None and dot is not None:
                    start_dot = dot
                off_leash = dot is not None and start_dot is not None and abs(dot[0] - start_dot[0]) > a.leash

                def allowed(direction):
                    return not off_leash or (direction == "right") == (dot[0] < start_dot[0])

                # ------------------------------------------------------------ SEEK
                if state == "SEEK":
                    release()
                    frames = [frame]
                    cands, resp, _ = candidates(frames, me[:4], screen.cursor())     # HP-bar mobs, instant
                    if not [c for c in cands if abs(c[1] + c[3] - feet) <= SAME_LEVEL]:
                        for _ in range(LOOK_FRAMES - 1):
                            time.sleep(LOOK_GAP)
                            frames.append(screen.grab())
                        if not keys.focused():
                            raise FocusLost()
                        stats["looks"] += 1
                        cands, resp, _ = candidates(frames, me[:4], screen.cursor())
                    if resp < MIN_ALIGN:
                        say(f"look unsteady (align {resp:.2f}), looking again")
                        continue
                    level = [c for c in cands if abs(c[1] + c[3] - feet) <= SAME_LEVEL]
                    level.sort(key=lambda c: abs(c[0] + c[2] / 2 - px))
                    pick = None
                    for c in level:
                        d = "left" if c[0] + c[2] / 2 < px else "right"
                        if allowed(d):
                            pick = c
                            break
                        stats["off_leash_skips"] += 1
                    if pick is None:
                        idle_looks += 1
                        if idle_looks >= 3:                # nothing around: stroll a little, then look again
                            if not allowed(patrol_dir):
                                patrol_dir = "right" if patrol_dir == "left" else "left"
                            say(f"no mobs for 3 looks -> patrol {patrol_dir}")
                            keys.hold(patrol_dir, 0.6)
                            facing, idle_looks = patrol_dir, 0
                            patrol_dir = "right" if patrol_dir == "left" else "left"
                            time.sleep(0.3)
                        continue
                    idle_looks = 0
                    tracker, bar_gone = Tracker(frames[-1], pick), 0
                    stats["targets"] += 1
                    go("APPROACH", f"target at dx {pick[0] + pick[2] / 2 - px:+.0f} ({len(level)} on our level), "
                                   f"HP {hp:.0%}", frames[-1])
                    continue

                # ------------------------------------------------------------ APPROACH / ATTACK: track target
                found = tracker.update(frame, refresh=(state == "APPROACH"))
                tx0, ty0 = tracker.centre()
                near_bars = [b for b in find_mob_bars(frame)
                             if abs(b[0] + 15 - tx0) < 70 and -80 < b[1] - ty0 < 10]
                if near_bars:                             # the bar doesn't change look when the mob is hit
                    bar = min(near_bars, key=lambda b: abs(b[0] + 15 - tx0))
                    tracker.box, tracker.lost, found, bar_gone = bar_mob_box(bar), 0, True, 0
                else:
                    bar_gone += 1
                tx, _ = tracker.centre()
                dx = tx - px
                direction = "left" if dx < 0 else "right"

                if state == "APPROACH":
                    if not found and tracker.lost >= 4:
                        stats["lost_while_approaching"] += 1
                        go("SEEK", f"lost target while approaching (score {tracker.score:.2f})", frame)
                        continue
                    if time.perf_counter() - state_t > APPROACH_TIMEOUT:
                        stats["approach_timeouts"] += 1
                        go("SEEK", f"approach timed out at dx {dx:+.0f}", frame)
                        continue
                    if abs(dx) <= ATTACK_DX:
                        facing = held if held else facing
                        go("ATTACK", f"in range dx {dx:+.0f}", frame)
                        continue
                    if not allowed(direction):
                        stats["off_leash_skips"] += 1
                        go("SEEK", "target is past the leash", frame)
                        continue
                    hold(direction)
                    facing = direction
                    time.sleep(REPEAT_S)
                    continue

                if state == "ATTACK":
                    if tracker.lost >= LOST_FRAMES_DEAD and bar_gone >= LOST_FRAMES_DEAD:
                        stats["kills"] += 1
                        go("SEEK", f"target gone -> counted as killed (#{stats['kills']}), HP {hp:.0%}", frame)
                        continue
                    if time.perf_counter() - state_t > ATTACK_TIMEOUT:
                        stats["attack_timeouts"] += 1
                        go("SEEK", "attack timed out", frame)
                        continue
                    if found and abs(dx) > RE_APPROACH_DX:
                        go("APPROACH", f"target moved away (dx {dx:+.0f})", frame)
                        continue
                    if found and facing != direction and abs(dx) > 12:
                        release()
                        keys.tap(direction, down_s=0.04, gap_s=0.05)   # turn around
                        facing = direction
                    hold(a.attack)
                    if tracker.frames % 15 == 0:
                        shot(f"ATTACKING dx {dx:+.0f} score {tracker.score:.2f} HP {hp:.0%}", frame)
                    time.sleep(REPEAT_S)
                    continue
            except FocusLost:
                release()
                keys.release_all()
                stats["focus_pauses"] += 1
                say(f"PAUSED: game not focused (foreground: '{foreground_title()}'); keys released, waiting...")
                while not keys.focused() and time.perf_counter() < end:
                    time.sleep(0.2)
                if keys.focused():
                    say("resumed")
                    state, tracker, me_pos = "SEEK", None, None
                    time.sleep(1.0)
    except Exception as e:                       # noqa: BLE001
        status = f"aborted: {type(e).__name__}: {e}"
    finally:
        keys.release_all()
    say(status)
    say(f"stats {json.dumps(stats)}")
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
