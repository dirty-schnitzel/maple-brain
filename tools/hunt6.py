"""Experiment 8: fast loop + mob memory + obstacles first + measured distance zones.

New vs hunt5:
  * capture via DXGI desktop duplication (dxcam, background thread) with mss fallback; one HP-bar pass per frame;
    no fixed per-frame sleep; per-stage timings in the trace.
  * zones from the hunt5c measurements: contact < 50px, hit 50-64px, stop walking at 74px.
  * mob memory: every engaged mob's appearance is kept as a template; each frame the ground band is scanned for
    matches -> finds mobs that stand still (the motion look can't see those).
  * obstacles first: while walking to a target, a nearer mob in the same direction becomes the target.

Usage (elevated): python -I hunt6.py <out_dir> [--seconds 60] [--attack space] [--leash 40]
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
from experiment1 import client_box, game_columns, user32  # noqa: E402
from hunt import FocusLost, Screen, StrictKeys, foreground_title, minimap_dot  # noqa: E402
from hunt2 import alarm  # noqa: E402
from hunt3 import Tracker, candidates, hp_fill  # noqa: E402
from hunt4 import wide_search  # noqa: E402
from hunt5 import exp_fill, mob_like  # noqa: E402
from perception import bar_mob_box, find_mob_bars, find_self_gray as find_self, overlaps  # noqa: E402

CONTACT, HIT_MAX, HOLD_MAX = 42, 66, 92
FRESH_S = 0.25           # only react to the target's distance if we saw it this recently
PROOF_S = 2.0            # hitting this long with no HP bar and no EXP -> it isn't a mob
BLACKLIST_S = 60
WALK_RELEASE = HIT_MAX + 10
STEP_S, WAIT_IN_HOLD_S = 0.10, 0.6
BLIND_MAX_S, LOST_BEFORE_REACH_S, ENGAGE_TIMEOUT_S = 3.0, 1.2, 15.0
SAME_LEVEL, MIN_ALIGN = 35, 0.7
LOOK_FRAMES, LOOK_GAP = 4, 0.1
SELF_MISSING_S = 0.5
LIB_MAX, LIB_SCORE = 6, 0.72


class FastScreen:
    """dxcam (desktop duplication) in video mode; falls back to mss if unavailable or the picture is black."""

    def __init__(self, hwnd):
        self.mss = Screen(hwnd)
        first = self.mss.grab()                       # also finds the pillarbox columns
        self.cols, self.box = self.mss.cols, self.mss.box
        self.cam, self.kind = None, "mss"
        try:
            import dxcam
            region = (self.box["left"] + self.cols[0], self.box["top"],
                      self.box["left"] + self.cols[1], self.box["top"] + self.box["height"])
            self.cam = dxcam.create(output_color="BGR")
            self.cam.start(region=region, target_fps=60, video_mode=True)
            time.sleep(0.3)
            f = self.cam.get_latest_frame()
            if f is None or f.max() < 10:
                raise RuntimeError("dxcam returned an empty/black frame")
            self.kind = "dxcam"
        except Exception as e:                        # noqa: BLE001
            self.close()
            self.cam, self.kind, self.err = None, "mss", str(e)
        self.first = first

    def grab(self):
        if self.cam is None:
            return self.mss.grab()
        f = self.cam.get_latest_frame()
        return cv2.resize(f, (1366, 768), interpolation=cv2.INTER_AREA)

    def cursor(self):
        return self.mss.cursor()

    def close(self):
        if self.cam is not None:
            try:
                self.cam.stop()
            except Exception:                         # noqa: BLE001
                pass


class MobLibrary:
    """Appearances of mobs we've fought; finds still-standing ones by template matching along the ground."""

    def __init__(self):
        self.tpls = deque(maxlen=LIB_MAX)

    def add(self, gray_tpl):
        if gray_tpl.size and gray_tpl.shape[0] >= 16 and gray_tpl.shape[1] >= MOB_W_MIN:
            self.tpls.append(gray_tpl.copy())

    def forget_like(self, gray_tpl):
        """Drop remembered appearances that match a template we now know is not a mob."""
        keep = []
        for t in self.tpls:
            if t.shape == gray_tpl.shape:
                if cv2.matchTemplate(t, gray_tpl, cv2.TM_CCOEFF_NORMED).max() > 0.7:
                    continue
            keep.append(t)
        self.tpls.clear()
        self.tpls.extend(keep)

    def find(self, gray, feet, exclude):
        """Mob boxes on our level matching any known appearance. exclude: boxes to ignore (ourselves, players)."""
        if not self.tpls:
            return []
        y0, y1 = max(0, int(feet) - 75), min(gray.shape[0], int(feet) + 8)
        band = gray[y0:y1]
        hits = []
        for t in self.tpls:
            if band.shape[0] < t.shape[0]:
                continue
            for tt in (t, cv2.flip(t, 1)):
                res = cv2.matchTemplate(band, tt, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(res >= LIB_SCORE)
                for x, y in zip(xs, ys):
                    hits.append((float(res[y, x]), (int(x), int(y + y0), tt.shape[1], tt.shape[0])))
        hits.sort(reverse=True)
        out = []
        for _, b in hits:                             # non-maximum suppression
            if any(overlaps(b, o, pad=-8) for o in out) or any(overlaps(b, e, pad=0) for e in exclude):
                continue
            out.append(b)
        return out


MOB_W_MIN = 30


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--attack", default="space")
    ap.add_argument("--leash", type=float, default=40)
    ap.add_argument("--hp-stop", type=float, default=0.45)
    a = ap.parse_args()
    out = Path(a.out)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    logf = open(out / "log.txt", "w", buffering=1, encoding="utf-8")
    trace = open(out / "trace.csv", "w", buffering=1, encoding="utf-8")
    trace.write("t,state,px,rel_dx,dist,src,held,hp,exp,dot_x,n_bars,n_lib,ms_grab,ms_perc,ms_total" + chr(10))
    t0 = time.perf_counter()

    def say(msg):
        line = f"{time.perf_counter() - t0:6.2f}s {msg}"
        print(line.encode("ascii", "replace").decode())
        logf.write(line + chr(10))

    template = np.load(Path(__file__).parent.parent / "assets" / "self_tag_gray.npy")
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

    keys, screen = StrictKeys(hwnd), FastScreen(hwnd)
    say(f"capture: {screen.kind}" + (f" (dxcam unavailable: {screen.err})" if screen.kind == "mss" else ""))
    lib = MobLibrary()
    stats = {"looks": 0, "engagements": 0, "kills_exp_confirmed": 0, "level_ups": 0, "gave_up": 0,
             "chain_switches": 0, "obstacle_switches": 0, "lib_targets": 0, "rejected_small": 0,
             "rejected_drop_zone": 0, "lost_before_reach": 0, "engage_timeouts": 0, "back_offs": 0,
             "contact_dodges": 0, "short_steps": 0, "attack_s": 0.0, "walk_s": 0.0, "hp_lost_pct": 0.0,
             "focus_pauses": 0, "frames": 0, "fps": 0.0}
    state, held, shots = "SEEK", None, 0
    me_pos, me_seen_at, start_dot, facing = None, time.perf_counter(), None, None
    hp_hist, exp_hist, idle_looks, patrol_dir = [], deque(maxlen=3), 0, "left"
    tracker = rel_dx = seen_at = engaged_at = hit_since = hold_since = exp_at_engage = None
    drop_zones, prev_hp, start_exp, exp = [], None, None, 0.0
    bar_level_now = []
    not_mobs = []                      # (until time, minimap dot x of us, rel_dx) spots proven not to be mobs
    self_lost_logged = False
    last_walk_dir, backouts, last_backout = None, 0, 0.0
    walk_ref = None                    # (time, dot x) when the current walk started making no progress
    blocked = {}                       # direction -> blocked until time
    status = "ok"
    end = time.perf_counter() + a.seconds
    run_start = time.perf_counter()

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

    def record(frame, st, px, rel, dist, src, hp, dot, nb, nl, ms_grab, ms_perc, t_frame):
        t = time.perf_counter() - t0
        trace.write(f"{t:.3f},{st},{px:.0f},{'' if rel is None else f'{rel:.0f}'},"
                    f"{'' if dist is None else f'{dist:.0f}'},{src},{held or ''},{hp:.3f},{exp:.4f},"
                    f"{'' if not dot else f'{dot[0]:.1f}'},{nb},{nl},{ms_grab:.0f},{ms_perc:.0f},"
                    f"{1000 * (time.perf_counter() - t_frame):.0f}" + chr(10))
        if stats["frames"] % 2 == 0:
            small = cv2.resize(frame, (683, 384), interpolation=cv2.INTER_AREA)
            if tracker is not None:
                x, y, w, h = (int(v / 2) for v in tracker.box)
                cv2.rectangle(small, (x, y), (x + w, y + h), (0, 0, 255), 1)
            cv2.putText(small, f"{t:.2f} {st} d={'' if dist is None else int(dist)} {src} {held or ''} "
                        f"hp={hp:.2f}", (110, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
            cv2.imwrite(str(out / "frames" / f"{stats['frames']:05d}.jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 70])

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
            keys.tap(direction, down_s=0.035, gap_s=0.03)
            facing = direction

    def engage(frame, box, px, why, from_lib=False):
        nonlocal tracker, rel_dx, seen_at, engaged_at, hit_since, hold_since, exp_at_engage, state
        tracker = Tracker(frame, box)
        tracker.proven = box in bar_level_now            # an HP-bar mob is a mob
        tracker.learned = False
        rel_dx = box[0] + box[2] / 2 - px
        seen_at = engaged_at = time.perf_counter()
        hit_since = time.perf_counter() if abs(rel_dx) <= HIT_MAX else None
        hold_since, exp_at_engage, state = None, exp, "ENGAGE"
        if from_lib:
            stats["lib_targets"] += 1
        say(f"{why}: target at dx {rel_dx:+.0f}")

    def disengage(why, frame, counter=None):
        nonlocal state, tracker
        if counter:
            stats[counter] += 1
        say(f"ENGAGE -> SEEK: {why}")
        shot(why.split()[0].upper(), frame)
        release()
        state, tracker = "SEEK", None

    try:
        while time.perf_counter() < end:
            try:
                t_frame = time.perf_counter()
                if held == a.attack:
                    stats["attack_s"] += 1
                elif held in ("left", "right"):
                    stats["walk_s"] += 1
                if not keys.focused():
                    raise FocusLost()
                frame = screen.grab()
                if not keys.focused():
                    raise FocusLost()
                ms_grab = 1000 * (time.perf_counter() - t_frame)
                stats["frames"] += 1
                t_perc = time.perf_counter()

                # ---- where am I
                me = find_self(frame, template, near=me_pos, radius=220, min_score=0.55) if me_pos else None
                if me is None:
                    me = find_self(frame, template)
                if me is None:
                    missing = time.perf_counter() - me_seen_at
                    if missing > SELF_MISSING_S:
                        release()
                        # probably walked behind a foreground object: back out the way we came, a step at a time
                        if last_walk_dir and backouts < 3 and time.perf_counter() - last_backout > 0.6:
                            back = "right" if last_walk_dir == "left" else "left"
                            keys.tap(back, down_s=0.25, gap_s=0.05)
                            facing, backouts, last_backout = back, backouts + 1, time.perf_counter()
                            say(f"   hidden? backing out {back} (step {backouts}/3)")
                            stats["backouts"] = stats.get("backouts", 0) + 1
                        if not self_lost_logged:
                            say(f"   can't see own name tag for {missing:.1f}s -> keys released, waiting")
                            cv2.imwrite(str(out / f"SELF_LOST_{stats['frames']:05d}.jpg"), frame)
                            self_lost_logged = True
                            stats["self_lost"] = stats.get("self_lost", 0) + 1
                    continue
                if self_lost_logged:
                    say(f"   found own name tag again after {time.perf_counter() - me_seen_at:.1f}s")
                    self_lost_logged = False
                    if backouts and last_walk_dir:
                        blocked[last_walk_dir] = time.perf_counter() + 15     # don't walk straight back in
                backouts = 0
                if held in ("left", "right"):
                    last_walk_dir = held
                me_pos, me_seen_at = (me[0] + me[2] / 2, me[1]), time.perf_counter()
                px, feet = me_pos
                my_body = (int(px - 30), int(feet - 75), 60, 92)

                # ---- survival + EXP
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
                    if blocked.get(direction, 0) > time.perf_counter():
                        return False
                    return not off_leash or (direction == "right") == (dot[0] < start_dot[0])

                # ---- blocked: holding a walk key but the minimap dot isn't moving
                if held in ("left", "right") and dot is not None:
                    if walk_ref is None or walk_ref[2] != held or abs(dot[0] - walk_ref[1]) >= 0.6:
                        walk_ref = (time.perf_counter(), dot[0], held)
                    elif time.perf_counter() - walk_ref[0] > 1.0:
                        blocked[held] = time.perf_counter() + 15
                        say(f"   blocked walking {held} (minimap x stuck at {dot[0]:.1f} for 1s) -> "
                            f"avoiding {held} for 15s (jumping comes later)")
                        stats["blocked"] = stats.get("blocked", 0) + 1
                        walk_ref = None
                        if state == "ENGAGE":
                            disengage("target is past an obstacle", frame)
                            continue
                else:
                    walk_ref = None

                # ---- every known mob on our level in this one frame: HP-bar mobs + remembered appearances
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                bar_boxes = [bar_mob_box(b) for b in find_mob_bars(frame)]
                bar_level = [b for b in bar_boxes if abs(b[1] + b[3] - feet) <= SAME_LEVEL + 15]
                bar_level_now = bar_level
                lib_level = [b for b in lib.find(gray, feet, [my_body] + bar_level)
                             if abs(b[1] + b[3] - feet) <= SAME_LEVEL]
                known = bar_level + lib_level
                ms_perc = 1000 * (time.perf_counter() - t_perc)

                # ------------------------------------------------------------ SEEK
                if state == "SEEK":
                    release()
                    record(frame, "SEEK", px, None, None, "-", hp, dot, len(bar_level), len(lib_level),
                           ms_grab, ms_perc, t_frame)
                    now_s = time.perf_counter()
                    drop_zones = [z for z in drop_zones if now_s - z[0] < 20 and z[2] is not None and dot
                                  and abs(dot[0] - z[2]) < 1.5]

                    def not_drop(c):
                        return c in bar_level or not any(abs((c[0] + c[2] / 2 - px) - z[1]) < 45 for z in drop_zones)

                    now_s = time.perf_counter()
                    not_mobs[:] = [z for z in not_mobs if z[0] > now_s]

                    def not_blacklisted(c):
                        if c in bar_level or not dot:
                            return True
                        return not any(abs(dot[0] - z[1]) < 1.5 and abs((c[0] + c[2] / 2 - px) - z[2]) < 40
                                       for z in not_mobs)

                    pool = [c for c in known if not_drop(c) and not_blacklisted(c)]
                    if not pool:                              # nothing known in one frame: do the motion look
                        frames = [frame]
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
                        sized = [c for c in on_level if mob_like(c)]
                        stats["rejected_small"] += len(on_level) - len(sized)
                        pool = [c for c in sized if not_drop(c) and not_blacklisted(c)]
                        stats["rejected_drop_zone"] += len(sized) - len(pool)
                        frame = frames[-1]
                    pool.sort(key=lambda c: abs(c[0] + c[2] / 2 - px))
                    pick = next((c for c in pool if allowed("left" if c[0] + c[2] / 2 < px else "right")), None)
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
                    stats["engagements"] += 1
                    engage(frame, pick, px, f"SEEK -> ENGAGE ({len(pool)} on our level, HP {hp:.0%}, "
                                            f"EXP {exp:.1%})", from_lib=pick in lib_level)
                    shot(f"ENGAGE dx {rel_dx:+.0f}", frame)
                    continue

                # ------------------------------------------------------------ ENGAGE
                killed_now = exp > exp_at_engage + 0.008 or exp < exp_at_engage - 0.3
                if killed_now:
                    stats["kills_exp_confirmed"] += 1
                    stats["level_ups"] += exp < exp_at_engage - 0.3
                    say(f"   kill confirmed - EXP {exp_at_engage:.1%} -> {exp:.1%} "
                        f"(#{stats['kills_exp_confirmed']}, HP {hp:.0%})")
                    shot(f"KILL #{stats['kills_exp_confirmed']}", frame)
                    exp_at_engage = exp

                exp_x = px + rel_dx
                near_bar = [b for b in bar_level if abs(b[0] + b[2] / 2 - exp_x) < 70]
                if near_bar:
                    tracker.box, tracker.lost = min(near_bar, key=lambda b: abs(b[0] + b[2] / 2 - exp_x)), 0
                    found, src = True, "bar"
                elif tracker.update(frame, refresh=hit_since is None):
                    found, src = True, "track"
                elif wide_search(tracker, frame):
                    found, src = True, "wide"
                else:
                    found, src = False, "none"
                if found:
                    rel_dx, seen_at = tracker.centre()[0] - px, time.perf_counter()
                if near_bar or killed_now:
                    tracker.proven = True
                if tracker.proven and not tracker.learned:
                    lib.add(tracker.tpl)
                    tracker.learned = True
                if hit_since is not None and not tracker.proven and time.perf_counter() - hit_since > PROOF_S:
                    not_mobs.append((time.perf_counter() + BLACKLIST_S, dot[0] if dot else -99, rel_dx))
                    lib.forget_like(tracker.tpl)
                    stats["not_a_mob"] = stats.get("not_a_mob", 0) + 1
                    disengage(f"not a mob - {PROOF_S:.0f}s of hitting, no HP bar, no EXP (dx {rel_dx:+.0f}) "
                              f"-> blacklisted {BLACKLIST_S}s", frame)
                    continue

                if killed_now and not near_bar:                    # the target is the one that died
                    drop_zones.append((time.perf_counter(), rel_dx, dot[0] if dot else None))
                    others = [k for k in known if abs((k[0] + k[2] / 2) - exp_x) > 25 and
                              abs(k[0] + k[2] / 2 - px) <= HOLD_MAX * 1.5]
                    if others:
                        stats["chain_switches"] += 1
                        nxt = min(others, key=lambda k: abs(k[0] + k[2] / 2 - px))
                        engage(frame, nxt, px, "   target died -> next mob in reach (no pause)")
                    else:
                        disengage("target died, nothing else in reach", frame)
                        continue

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

                # ---- obstacles first: a known mob nearer than the target, on the way to it
                if dist > HIT_MAX:
                    tx = px + rel_dx
                    in_way = [k for k in known if abs(k[0] + k[2] / 2 - tx) > 25 and
                              (k[0] + k[2] / 2 - px) * rel_dx > 0 and abs(k[0] + k[2] / 2 - px) < dist - 25]
                    if in_way:
                        stats["obstacle_switches"] += 1
                        nxt = min(in_way, key=lambda k: abs(k[0] + k[2] / 2 - px))
                        engage(frame, nxt, px, "   mob in the way -> fighting it first")
                        rel_dx = nxt[0] + nxt[2] / 2 - px
                        dist, direction = abs(rel_dx), ("left" if rel_dx < 0 else "right")
                        away = "right" if direction == "left" else "left"

                # ---- any other known mob in contact range: step away from it
                intruder = next((k[0] + k[2] / 2 - px for k in known
                                 if abs(k[0] + k[2] / 2 - px) < CONTACT and
                                 abs((k[0] + k[2] / 2) - (px + rel_dx)) > 25), None)
                if intruder is not None and dist >= CONTACT:
                    release()
                    keys.tap("right" if intruder < 0 else "left", down_s=STEP_S, gap_s=0.03)
                    facing = "right" if intruder < 0 else "left"
                    stats["contact_dodges"] += 1
                    say(f"   another mob in contact range (dx {intruder:+.0f}) -> stepped away")
                    continue

                fresh = unseen <= FRESH_S
                if not fresh:
                    if hit_since is not None and unseen < 1.0:
                        hold(a.attack)                          # mid-fight, lost sight briefly: keep swinging
                    else:
                        release()                               # don't move on an old position
                elif dist < CONTACT:
                    release()
                    keys.tap(away, down_s=STEP_S, gap_s=0.03)
                    facing = away
                    turn(direction)
                    stats["back_offs"] += 1
                    say(f"   too close (dx {rel_dx:+.0f}) -> stepped back")
                elif dist <= HIT_MAX:
                    if hit_since is None:
                        hit_since = time.perf_counter()
                        say(f"   in reach (dx {rel_dx:+.0f}) -> hitting")
                    hold_since = None
                    turn(direction)
                    hold(a.attack)
                elif dist <= HOLD_MAX:
                    if held in ("left", "right"):
                        release()
                    if hold_since is None:
                        hold_since = time.perf_counter()
                    turn(direction)
                    if held == a.attack:
                        release()
                    if time.perf_counter() - hold_since > WAIT_IN_HOLD_S and allowed(direction):
                        keys.tap(direction, down_s=STEP_S, gap_s=0.03)
                        stats["short_steps"] += 1
                        hold_since = time.perf_counter()
                else:
                    hold_since = None
                    if not allowed(direction):
                        disengage("target is past the leash", frame)
                        continue
                    if dist > WALK_RELEASE:
                        hold(direction)
                        facing = direction
                    else:
                        release()
                record(frame, "ENGAGE", px, rel_dx, dist, src, hp, dot, len(bar_level), len(lib_level),
                       ms_grab, ms_perc, t_frame)
                if stats["frames"] % 25 == 0:
                    zone = ("CLOSE" if dist < CONTACT else "HIT" if dist <= HIT_MAX else
                            "HOLD" if dist <= HOLD_MAX else "WALK")
                    shot(f"{zone} dx {rel_dx:+.0f} {src} HP {hp:.0%}", frame)
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
        import traceback
        status = f"aborted: {type(e).__name__}: {e}"
        logf.write(traceback.format_exc())
    finally:
        keys.release_all()
        screen.close()
    elapsed = time.perf_counter() - run_start
    stats["fps"] = round(stats["frames"] / elapsed, 1)
    stats["attack_s"] = round(stats["attack_s"] / max(stats["fps"], 1), 1)
    stats["walk_s"] = round(stats["walk_s"] / max(stats["fps"], 1), 1)
    stats["hp_lost_pct"] = round(stats["hp_lost_pct"], 1)
    stats["exp_gained_pct_of_level"] = round((exp - start_exp) * 100, 1) if start_exp is not None else None
    say(status)
    say(f"stats {json.dumps(stats)}")
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
