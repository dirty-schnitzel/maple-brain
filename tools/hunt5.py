"""Experiment 7: fight like a player - keep a distance, hit from the edge of reach, kills confirmed by EXP.

Distance zones (centre-to-centre, screen px):
   < TOO_CLOSE          back off one small step (contact range = taking damage), then face it again
   TOO_CLOSE..HIT_MAX   face it and hold attack
   HIT_MAX..HOLD_MAX    it's coming (or was just knocked back toward us)? face it and wait.
                        otherwise take one short step in
   > HOLD_MAX           walk in, releasing the key early so momentum doesn't carry us into it

Kills are confirmed by the EXP bar going up (or resetting on level-up) while engaged. If the target can't be
seen but EXP hasn't moved, keep working toward where it was for up to BLIND_MAX_S before giving up.

Usage (elevated): python -I hunt5.py <out_dir> [--seconds 60] [--attack space] [--leash 40]
"""
import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

sys.path.append(str(Path(__file__).parent))
from experiment1 import user32  # noqa: E402
from hunt import FocusLost, Screen, StrictKeys, foreground_title, minimap_dot  # noqa: E402
from hunt2 import alarm  # noqa: E402
from hunt3 import Tracker, candidates, hp_fill  # noqa: E402
from hunt4 import wide_search  # noqa: E402
from perception import bar_mob_box, find_mob_bars, find_self  # noqa: E402

TOO_CLOSE, HIT_MAX, HOLD_MAX = 32, 62, 90
WALK_RELEASE = HIT_MAX + 14      # stop holding the walk key here; the slide covers the rest
STEP_S = 0.12                    # a short step
WAIT_IN_HOLD_S = 0.6             # wait this long in the hold zone for the mob to come before stepping in
BLIND_MAX_S = 3.0                # target unseen + no EXP change for this long -> give up
LOST_BEFORE_REACH_S = 1.2
ENGAGE_TIMEOUT_S = 15.0
SAME_LEVEL, MIN_ALIGN = 35, 0.7
LOOK_FRAMES, LOOK_GAP = 4, 0.1
SELF_MISSING_S, REPEAT_S = 0.5, 0.04
EXP_BOX = (724, 753, 837, 764)
MOB_MIN_W, MOB_MIN_AREA = 32, 500   # drops (mesos/items), butterflies, grass flicker are ~24-30px wide


def mob_like(c):
    """Size gate for motion blobs: mobs (snails ~40x26) vs spinning drops, butterflies, foliage."""
    return c[2] >= MOB_MIN_W and c[2] * c[3] >= MOB_MIN_AREA


def exp_fill(frame):
    """Filled share of the EXP bar (yellow-green part)."""
    x0, y0, x1, y1 = EXP_BOX
    hsv = cv2.cvtColor(frame[y0:y1 + 1, x0:x1 + 1], cv2.COLOR_BGR2HSV)
    fill = (hsv[:, :, 0] >= 25) & (hsv[:, :, 0] <= 45) & (hsv[:, :, 1] > 150) & (hsv[:, :, 2] > 150)
    return float((fill.mean(axis=0) > 0.4).mean())


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
    stats = {"looks": 0, "engagements": 0, "kills_exp_confirmed": 0, "level_ups": 0, "gave_up": 0,
             "chain_switches": 0, "rejected_small": 0, "contact_dodges": 0,
             "lost_before_reach": 0, "engage_timeouts": 0, "back_offs": 0, "short_steps": 0, "waits": 0,
             "attack_s": 0.0, "walk_s": 0.0, "hp_lost_pct": 0.0, "focus_pauses": 0, "frames": 0}
    state, held, shots = "SEEK", None, 0
    me_pos, me_seen_at, start_dot, facing = None, time.perf_counter(), None, None
    hp_hist, exp_hist, idle_looks, patrol_dir = [], deque(maxlen=3), 0, "left"
    tracker = rel_dx = seen_at = engaged_at = hit_since = hold_since = exp_at_engage = None
    dx_hist = deque(maxlen=6)
    drop_zones = []                    # (time, rel_dx at death, minimap dot x at death)
    (out / "frames").mkdir(exist_ok=True)
    trace = open(out / "trace.csv", "w", buffering=1, encoding="utf-8")
    trace.write("t,state,px,rel_dx,dist,src,held,hp,exp,dot_x,n_bars\n")
    src = "-"
    prev_hp, start_exp = None, None
    status = "ok"
    end = time.perf_counter() + a.seconds

    def shot(tag, frame):
        nonlocal shots
        if shots < 220:
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

    def turn(direction):
        nonlocal facing
        if facing != direction:
            release()
            keys.tap(direction, down_s=0.035, gap_s=0.04)
            facing = direction

    def switch_to_nearby(frame, px, feet, why):
        """Another mob within reach (HP-bar mobs: one frame, no look)? Retarget to it and stay engaged."""
        nonlocal tracker, rel_dx, seen_at, engaged_at, hit_since, hold_since
        near = []
        for b in find_mob_bars(frame):
            box = bar_mob_box(b)
            d = box[0] + box[2] / 2 - px
            if abs(d) <= HOLD_MAX * 1.5 and abs(box[1] + box[3] - feet) <= SAME_LEVEL + 15:
                if tracker is None or abs((box[0] + box[2] / 2) - tracker.centre()[0]) > 20:
                    near.append((abs(d), d, box))
        if not near:
            return False
        _, d, box = min(near)
        tracker = Tracker(frame, box)
        rel_dx, seen_at, engaged_at = d, time.perf_counter(), time.perf_counter()
        hit_since = time.perf_counter() if abs(d) <= HIT_MAX else None
        hold_since = None
        dx_hist.clear()
        stats["chain_switches"] += 1
        say(f"   {why} -> next mob in reach at dx {d:+.0f} (no pause)")
        return True

    def record(frame, st, px, rel, dist, src_, hp, exp, dot):
        t = time.perf_counter() - t0
        trace.write(f"{t:.3f},{st},{px:.0f},{'' if rel is None else f'{rel:.0f}'},"
                    f"{'' if dist is None else f'{dist:.0f}'},{src_},{held or ''},{hp:.3f},{exp:.4f},"
                    f"{'' if not dot else f'{dot[0]:.1f}'},{len(find_mob_bars(frame))}\n")
        small = cv2.resize(frame, (683, 384), interpolation=cv2.INTER_AREA)
        if tracker is not None:
            x, y, w, h = (int(v / 2) for v in tracker.box)
            cv2.rectangle(small, (x, y), (x + w, y + h), (0, 0, 255), 1)
        cv2.putText(small, f"{t:.2f} {st} d={'' if dist is None else int(dist)} {src_} {held or ''} hp={hp:.2f}",
                    (110, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        cv2.imwrite(str(out / "frames" / f"{stats['frames']:05d}.jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 70])

    def disengage(why, frame, counter=None):
        nonlocal state, tracker
        if counter:
            stats[counter] += 1
        say(f"ENGAGE -> SEEK: {why}")
        shot(why.split()[0].upper(), frame)
        release()
        state, tracker = "SEEK", None

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

                # ---- where am I (every frame)
                me = find_self(frame, template, near=me_pos, radius=220) if me_pos else None
                if me is None:
                    me = find_self(frame, template)
                if me is None:
                    if time.perf_counter() - me_seen_at > SELF_MISSING_S:
                        release()
                    time.sleep(REPEAT_S)
                    continue
                me_pos, me_seen_at = (me[0] + me[2] / 2, me[1]), time.perf_counter()
                px, feet = me_pos

                # ---- survival + EXP (only from frames with our name tag)
                hp_hist = (hp_hist + [hp_fill(frame)])[-6:]
                hp = max(hp_hist)
                if prev_hp is not None and hp < prev_hp:
                    stats["hp_lost_pct"] += (prev_hp - hp) * 100
                prev_hp = hp
                if len(hp_hist) >= 3 and hp < a.hp_stop:
                    keys.release_all()
                    cv2.imwrite(str(out / "STOP.png"), frame)
                    status = f"STOPPED: HP {hp:.0%} (best of last {len(hp_hist)} frames) below {a.hp_stop:.0%}"
                    alarm()
                    break
                exp_hist.append(exp_fill(frame))
                exp = float(np.median(exp_hist))
                if start_exp is None:
                    start_exp = exp

                dot = minimap_dot(frame)
                if start_dot is None and dot is not None:
                    start_dot = dot
                off_leash = dot is not None and start_dot is not None and abs(dot[0] - start_dot[0]) > a.leash

                def allowed(direction):
                    return not off_leash or (direction == "right") == (dot[0] < start_dot[0])

                # ------------------------------------------------------------ SEEK
                if state == "SEEK":
                    record(frame, "SEEK", px, None, None, "-", hp, exp, dot)
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
                    on_level = [c for c in cands if abs(c[1] + c[3] - feet) <= SAME_LEVEL]
                    now_s = time.perf_counter()
                    drop_zones = [z for z in drop_zones if now_s - z[0] < 20 and z[2] is not None and dot
                                  and abs(dot[0] - z[2]) < 1.5]
                    bar_boxes = {bar_mob_box(b) for b in find_mob_bars(frames[-1])}
                    in_drops = [c for c in on_level if c not in bar_boxes and
                                any(abs((c[0] + c[2] / 2 - px) - z[1]) < 45 for z in drop_zones)]
                    if in_drops:
                        stats["rejected_drop_zone"] = stats.get("rejected_drop_zone", 0) + len(in_drops)
                        on_level = [c for c in on_level if c not in in_drops]
                    level = sorted((c for c in on_level if mob_like(c)), key=lambda c: abs(c[0] + c[2] / 2 - px))
                    if len(level) < len(on_level):
                        stats["rejected_small"] += len(on_level) - len(level)
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
                    hit_since = hold_since = None
                    exp_at_engage = exp
                    dx_hist.clear()
                    stats["engagements"] += 1
                    state = "ENGAGE"
                    say(f"SEEK -> ENGAGE: target at dx {rel_dx:+.0f} ({len(level)} on our level), "
                        f"HP {hp:.0%}, EXP {exp:.1%}")
                    shot(f"ENGAGE dx {rel_dx:+.0f}", frames[-1])
                    continue

                # ------------------------------------------------------------ ENGAGE
                # kill confirmed by the game: EXP went up, or reset by a level-up
                killed_now = exp > exp_at_engage + 0.008 or exp < exp_at_engage - 0.3
                if killed_now:
                    stats["kills_exp_confirmed"] += 1
                    if exp < exp_at_engage - 0.3:
                        stats["level_ups"] += 1
                    say(f"   kill confirmed - EXP {exp_at_engage:.1%} -> {exp:.1%} "
                        f"(#{stats['kills_exp_confirmed']}, HP {hp:.0%})")
                    shot(f"KILL #{stats['kills_exp_confirmed']}", frame)
                    exp_at_engage = exp

                exp_x = px + rel_dx
                bars = [b for b in find_mob_bars(frame)
                        if abs(b[0] + 15 - exp_x) < 80 and abs((b[1] + 58) - feet) <= SAME_LEVEL + 15]
                if bars:
                    bar = min(bars, key=lambda b: abs(b[0] + 15 - exp_x))
                    tracker.box, tracker.lost = bar_mob_box(bar), 0
                    found, src = True, "bar"
                else:
                    if tracker.update(frame, refresh=hit_since is None):
                        found, src = True, "track"
                    elif wide_search(tracker, frame):
                        found, src = True, "wide"
                    else:
                        found, src = False, "none"
                if found:
                    tx, _ = tracker.centre()
                    rel_dx, seen_at = tx - px, time.perf_counter()
                    dx_hist.append((time.perf_counter(), abs(rel_dx)))
                unseen = time.perf_counter() - seen_at
                if killed_now and not bars:                     # no HP bar at the target = it's the one that died
                    drop_zones.append((time.perf_counter(), rel_dx, dot[0] if dot else None))
                    tracker = None
                    if not switch_to_nearby(frame, px, feet, "target died"):
                        disengage("target died, nothing else in reach", frame)
                        continue
                elif unseen > 0.3 and switch_to_nearby(frame, px, feet, f"target unseen {unseen:.1f}s"):
                    pass
                unseen = time.perf_counter() - seen_at
                dist = abs(rel_dx)
                direction = "left" if rel_dx < 0 else "right"
                away = "right" if direction == "left" else "left"

                if hit_since is not None and unseen > BLIND_MAX_S:
                    disengage(f"gave up - target unseen {unseen:.1f}s and no EXP change", frame, "gave_up")
                    continue
                if hit_since is None and unseen > LOST_BEFORE_REACH_S:
                    disengage(f"lost target before reaching it (last dx {rel_dx:+.0f})", frame, "lost_before_reach")
                    continue
                if time.perf_counter() - engaged_at > ENGAGE_TIMEOUT_S:
                    disengage("timeout on this target", frame, "engage_timeouts")
                    continue

                # is it closing in on us? (distance shrinking over the last ~0.3s)
                closing = False
                if len(dx_hist) >= 3 and dx_hist[-1][0] - dx_hist[0][0] > 0.15:
                    closing = dx_hist[0][1] - dx_hist[-1][1] > 4

                intruder = None
                for b in find_mob_bars(frame):
                    box = bar_mob_box(b)
                    d = box[0] + box[2] / 2 - px
                    if abs(d) < TOO_CLOSE and abs(box[1] + box[3] - feet) <= SAME_LEVEL + 15 and                             abs((box[0] + box[2] / 2) - tracker.centre()[0]) > 20:
                        intruder = d
                if intruder is not None and dist >= TOO_CLOSE:          # another mob walked into us
                    release()
                    keys.tap("right" if intruder < 0 else "left", down_s=STEP_S, gap_s=0.03)
                    facing = "right" if intruder < 0 else "left"
                    stats["contact_dodges"] += 1
                    say(f"   another mob in contact range (dx {intruder:+.0f}) -> stepped away")
                    time.sleep(REPEAT_S)
                    continue
                if dist < TOO_CLOSE:                                   # contact range: back off a step
                    release()
                    keys.tap(away, down_s=STEP_S, gap_s=0.03)
                    facing = away
                    turn(direction)
                    stats["back_offs"] += 1
                    say(f"   too close (dx {rel_dx:+.0f}) -> stepped back")
                elif dist <= HIT_MAX:                                  # hit zone
                    if hit_since is None:
                        hit_since = time.perf_counter()
                        say(f"   in reach (dx {rel_dx:+.0f}) -> hitting")
                    hold_since = None
                    turn(direction)
                    hold(a.attack)
                elif dist <= HOLD_MAX:                                 # just outside reach
                    if held in ("left", "right"):
                        release()                                     # arrived: stop walking here
                    if hold_since is None:
                        hold_since = time.perf_counter()
                    turn(direction)
                    if held == a.attack and not closing:
                        release()
                    if closing:
                        stats["waits"] += 1 if held != a.attack else 0
                        hold(a.attack)                                # it's coming into reach: swing as it arrives
                    elif time.perf_counter() - hold_since > WAIT_IN_HOLD_S and allowed(direction):
                        keys.tap(direction, down_s=STEP_S, gap_s=0.03)
                        stats["short_steps"] += 1
                        hold_since = time.perf_counter()
                else:                                                  # far: walk in, release early
                    hold_since = None
                    if not allowed(direction):
                        disengage("target is past the leash", frame)
                        continue
                    if dist > WALK_RELEASE:
                        hold(direction)
                        facing = direction
                    else:
                        release()
                record(frame, "ENGAGE", px, rel_dx, dist, src, hp, exp, dot)
                if stats["frames"] % 20 == 0:
                    zone = ("CLOSE" if dist < TOO_CLOSE else "HIT" if dist <= HIT_MAX else
                            "HOLD" if dist <= HOLD_MAX else "WALK")
                    shot(f"{zone} dx {rel_dx:+.0f} seen {unseen:.1f}s HP {hp:.0%}", frame)
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
    for k in ("attack_s", "walk_s", "hp_lost_pct"):
        stats[k] = round(stats[k], 1)
    stats["exp_gained_pct_of_level"] = round((exp - start_exp) * 100, 1) if start_exp is not None else None
    say(status)
    say(f"stats {json.dumps(stats)}")
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
