"""Experiment 6: SEEK -> ENGAGE. Stay on one mob and keep hitting it until it's really dead.

ENGAGE runs every frame (~15 fps):
  1. re-find ourselves first (name tag), so knockback doesn't confuse the target maths
  2. re-find the target: its HP bar -> template tracker -> wide re-search; remember its offset from us
  3. in range: face it and HOLD attack; out of range: walk toward it (no state change, no pause)
  4. target briefly unseen: keep attacking/walking toward where it last was
  5. counted dead only after KILL_CONFIRM_S unseen while we were in range hitting it

Safety as before: keys only while the game has focus; HP/positions only from frames with our name tag;
HP below --hp-stop (best of last 6 frames) -> release, beep, stop; leash; time limit; screenshots.

Usage (elevated): python -I hunt4.py <out_dir> [--seconds 60] [--attack space] [--leash 40]
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
from hunt import FocusLost, Screen, StrictKeys, foreground_title, minimap_dot  # noqa: E402
from hunt2 import alarm  # noqa: E402
from hunt3 import Tracker, candidates, gray, hp_fill  # noqa: E402
from perception import bar_mob_box, find_mob_bars, find_self  # noqa: E402

ATTACK_DX = 60            # centre-to-centre px to swing
SAME_LEVEL = 35
MIN_ALIGN = 0.7
LOOK_FRAMES, LOOK_GAP = 4, 0.1
KILL_CONFIRM_S = 1.0      # target unseen this long after we were hitting it -> dead
LOST_GIVE_UP_S = 1.2      # target unseen this long while we were still walking to it -> give up
ENGAGE_TIMEOUT_S = 12.0
SELF_MISSING_S = 0.5      # can't see ourselves this long -> release keys until we can
REPEAT_S = 0.04


def wide_search(tracker, frame, radius=160):
    """Re-find a lost target in a wider window (after knockback the camera jumps)."""
    g = gray(frame)
    H, W = g.shape
    x, y, w, h = tracker.box
    x0, y0, x1, y1 = max(0, x - radius), max(0, y - 40), min(W, x + w + radius), min(H, y + h + 40)
    win = g[y0:y1, x0:x1]
    best, loc = -1.0, None
    for t in (tracker.tpl, cv2.flip(tracker.tpl, 1)):
        if win.shape[0] >= t.shape[0] and win.shape[1] >= t.shape[1]:
            _, s, _, l = cv2.minMaxLoc(cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED))
            if s > best:
                best, loc = s, l
    if best >= 0.72:
        tracker.box, tracker.lost = (x0 + loc[0], y0 + loc[1], w, h), 0
        return True
    return False


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
    stats = {"looks": 0, "engagements": 0, "kills": 0, "gave_up_lost": 0, "engage_timeouts": 0,
             "knockbacks": 0, "attack_s": 0.0, "walk_s": 0.0, "focus_pauses": 0, "frames": 0}
    state, held, shots = "SEEK", None, 0
    me_pos, me_seen_at, start_dot, facing = None, time.perf_counter(), None, None
    hp_hist, idle_looks, patrol_dir = [], 0, "left"
    tracker = rel_dx = None
    seen_at = engaged_at = hit_since = None
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

    try:
        last_tick = time.perf_counter()
        while time.perf_counter() < end:
            try:
                now = time.perf_counter()
                dt, last_tick = now - last_tick, now
                if held == a.attack:
                    stats["attack_s"] += dt
                elif held in ("left", "right"):
                    stats["walk_s"] += dt
                if not keys.focused():
                    raise FocusLost()
                frame = screen.grab()
                if not keys.focused():
                    raise FocusLost()
                stats["frames"] += 1

                # ---- 1. where am I (every frame; knockback moves us)
                me = find_self(frame, template, near=me_pos, radius=220) if me_pos else None
                if me is None:
                    me = find_self(frame, template)
                if me is None:
                    if time.perf_counter() - me_seen_at > SELF_MISSING_S:
                        release()                       # can't see ourselves: stop pressing until we can
                    time.sleep(REPEAT_S)
                    continue
                new_pos = (me[0] + me[2] / 2, me[1])
                if me_pos and abs(new_pos[0] - me_pos[0]) > 25 and held != "left" and held != "right":
                    stats["knockbacks"] += 1
                me_pos, me_seen_at = new_pos, time.perf_counter()
                px, feet = me_pos

                # ---- survival
                hp_hist = (hp_hist + [hp_fill(frame)])[-6:]
                hp = max(hp_hist)
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
                    cands, resp, _ = candidates(frames, me[:4], screen.cursor())
                    if not [c for c in cands if abs(c[1] + c[3] - feet) <= SAME_LEVEL]:
                        for _ in range(LOOK_FRAMES - 1):
                            time.sleep(LOOK_GAP)
                            frames.append(screen.grab())
                        if not keys.focused():
                            raise FocusLost()
                        stats["looks"] += 1
                        cands, resp, _ = candidates(frames, me[:4], screen.cursor())
                    if resp < MIN_ALIGN:
                        continue
                    level = sorted((c for c in cands if abs(c[1] + c[3] - feet) <= SAME_LEVEL),
                                   key=lambda c: abs(c[0] + c[2] / 2 - px))
                    pick = next((c for c in level if allowed("left" if c[0] + c[2] / 2 < px else "right")), None)
                    if pick is None:
                        idle_looks += 1
                        if idle_looks >= 3:
                            if not allowed(patrol_dir):
                                patrol_dir = "right" if patrol_dir == "left" else "left"
                            say(f"no mobs for 3 looks -> patrol {patrol_dir}")
                            keys.hold(patrol_dir, 0.6)
                            facing, idle_looks = patrol_dir, 0
                            patrol_dir = "right" if patrol_dir == "left" else "left"
                        continue
                    idle_looks = 0
                    tracker = Tracker(frames[-1], pick)
                    rel_dx = pick[0] + pick[2] / 2 - px
                    seen_at = engaged_at = time.perf_counter()
                    hit_since = None
                    stats["engagements"] += 1
                    state = "ENGAGE"
                    say(f"SEEK -> ENGAGE: target at dx {rel_dx:+.0f} ({len(level)} on our level), HP {hp:.0%}")
                    shot(f"ENGAGE start dx {rel_dx:+.0f}", frames[-1])
                    continue

                # ------------------------------------------------------------ ENGAGE
                # ---- 2. where is the target: HP bar near where we expect it, else tracker, else wide search
                exp_x = px + rel_dx
                bars = [b for b in find_mob_bars(frame)
                        if abs(b[0] + 15 - exp_x) < 80 and abs((b[1] + 58) - feet) <= SAME_LEVEL + 15]
                if bars:
                    bar = min(bars, key=lambda b: abs(b[0] + 15 - exp_x))
                    tracker.box, tracker.lost = bar_mob_box(bar), 0
                    found = True
                else:
                    found = tracker.update(frame, refresh=hit_since is None) or wide_search(tracker, frame)
                if found:
                    tx, _ = tracker.centre()
                    rel_dx, seen_at = tx - px, time.perf_counter()
                unseen = time.perf_counter() - seen_at
                in_range = abs(rel_dx) <= ATTACK_DX
                direction = "left" if rel_dx < 0 else "right"

                # ---- 5. done with this target?
                if hit_since is not None and unseen > KILL_CONFIRM_S:
                    stats["kills"] += 1
                    say(f"ENGAGE -> SEEK: target gone after {time.perf_counter() - hit_since:.1f}s of hitting "
                        f"-> killed (#{stats['kills']}), HP {hp:.0%}")
                    shot(f"KILLED #{stats['kills']}", frame)
                    release()
                    state, tracker = "SEEK", None
                    continue
                if hit_since is None and unseen > LOST_GIVE_UP_S:
                    stats["gave_up_lost"] += 1
                    say(f"ENGAGE -> SEEK: lost target before reaching it (last dx {rel_dx:+.0f})")
                    shot("LOST", frame)
                    release()
                    state, tracker = "SEEK", None
                    continue
                if time.perf_counter() - engaged_at > ENGAGE_TIMEOUT_S:
                    stats["engage_timeouts"] += 1
                    say("ENGAGE -> SEEK: timed out on this target")
                    release()
                    state, tracker = "SEEK", None
                    continue

                # ---- 3/4. hit it, or close the gap - without leaving ENGAGE
                if in_range:
                    if hit_since is None:
                        hit_since = time.perf_counter()
                        say(f"   in range (dx {rel_dx:+.0f}) -> attacking")
                    if facing != direction and abs(rel_dx) > 12:
                        release()
                        keys.tap(direction, down_s=0.04, gap_s=0.04)
                        facing = direction
                    hold(a.attack)
                else:
                    if not allowed(direction):
                        say("ENGAGE -> SEEK: target is past the leash")
                        release()
                        state, tracker = "SEEK", None
                        continue
                    if held == a.attack:
                        say(f"   knocked out of range (dx {rel_dx:+.0f}) -> stepping back in")
                    hold(direction)
                    facing = direction
                if stats["frames"] % 20 == 0:
                    shot(f"{'HIT' if in_range else 'WALK'} dx {rel_dx:+.0f} seen {unseen:.1f}s HP {hp:.0%}", frame)
                time.sleep(REPEAT_S)
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
                last_tick = time.perf_counter()
    except Exception as e:                       # noqa: BLE001
        status = f"aborted: {type(e).__name__}: {e}"
    finally:
        keys.release_all()
    stats["attack_s"], stats["walk_s"] = round(stats["attack_s"], 1), round(stats["walk_s"], 1)
    say(status)
    say(f"stats {json.dumps(stats)}")
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
