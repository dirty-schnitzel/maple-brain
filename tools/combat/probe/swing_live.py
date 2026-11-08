"""LIVE probe: how the game treats our attack presses and direction keys (HANDOFF "attack per press", plan step 1).

Stand still on a FLAT, QUIET spot (no mobs, few players: a town is fine), the game in front. Then (elevated):
    ..\\auto-maple\\.venv\\Scripts\\python tools\\combat\\probe\\swing_live.py runs\\probe\\swing1
It switches to the game, waits 3 s, and runs ~45 short trials (~2.5 min) on the attack key (Keys.attack) and the
arrows, recording a crop around us at the game's frame rate. Hands off the keyboard until it says "done".
Then `swing_read.py runs\\probe\\swing1` reads the poses.

Trials (every offset / press length drawn at random from a range - a test, still no fixed rhythm):
    face        tap right / left / right, rest: standing references for both facings
    single      one attack tap (0.08-0.15 s down)                         -> press -> swing start, swing length
    short       one very short tap (0.016-0.035 s)                        -> the shortest press the game takes
    double      a tap, a second tap 0.12-0.8 s later (mid-swing)          -> ignored, or queued as the next swing?
    hold        attack held 2.5-3 s                                       -> swing period while held
    turn_tap    facing right, attack tap, a LEFT tap 0.1-1.0 s later       -> dropped, or applied at the swing's end?
    turn_hold   facing right, attack tap, LEFT held from 0.1-0.5 s for ~1 s -> when does the turn / walk start?
    turn_first  LEFT tap, attack 0.02-0.10 s after it                      -> does that swing face left?
Writes OUT/crops.npz (JPEG crops + capture times), OUT/events.json (every key event, trial marks), OUT/meta.json.
"""
import json
import random
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from maplebot.capture import Screen, find_window  # noqa: E402
from maplebot.config import Keys  # noqa: E402
from maplebot.keyboard import _send, bring_to_front, user32  # noqa: E402
from maplebot.perception import hud  # noqa: E402
from maplebot.perception.selfpos import find_self  # noqa: E402

HP_STOP = 0.40                           # abort below this share of HP (mobs around: no potions here)
HALF_W, UP, DOWN = 250, 175, 45          # crop around our tag: wide enough for the polearm's reach + a short walk
U = random.uniform


class Abort(Exception):
    pass


class Probe:
    def __init__(self, hwnd, screen, out: Path):
        self.hwnd, self.screen, self.out = hwnd, screen, out
        self.t0 = time.perf_counter()
        self.events, self.held = [], set()
        self.crops, self.times = [], []
        self.box = None
        self.hp = None                    # (cur, max) from the HUD, read every ~0.25 s
        self.stop = threading.Event()

    def now(self):
        return time.perf_counter() - self.t0

    # --- keys: raw events at the planned times, focus-guarded ---------------------------------------------------
    def wait_until(self, t):
        while True:
            left = t - self.now()
            if left <= 0:
                return
            time.sleep(min(left, 0.002) if left < 0.01 else left - 0.008)

    def key(self, k, up):
        if user32.GetForegroundWindow() != self.hwnd:
            self.release()
            raise Abort("the game lost focus")
        if self.hp and self.hp[0] < HP_STOP * self.hp[1]:
            self.release()
            raise Abort(f"HP {self.hp[0]}/{self.hp[1]} - heal and stand somewhere quiet")
        _send(k, up)
        (self.held.discard if up else self.held.add)(k)
        self.events.append({"t": round(self.now(), 4), "key": k, "up": up})

    def release(self):
        for k in list(self.held):
            _send(k, True)
            self.events.append({"t": round(self.now(), 4), "key": k, "up": True})
        self.held.clear()

    def press(self, k, at, secs):
        """k down at `at` (probe time), up `secs` later. Returns the up time."""
        self.wait_until(at)
        self.key(k, False)
        self.wait_until(at + secs)
        self.key(k, True)
        return at + secs

    def mark(self, name, **kw):
        self.events.append({"t": round(self.now(), 4), "trial": name, **kw})

    # --- capture: every new frame, a crop around where we stood at the start -------------------------------------
    def capture(self):
        while not self.stop.is_set():
            f = self.screen.grab()
            t = self.now()
            x0, y0, x1, y1 = self.box
            ok, jpg = cv2.imencode(".jpg", f[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                self.crops.append(jpg.tobytes())
                self.times.append(t)
            if len(self.times) % 15 == 0:
                self.hp = hud.read_pair(f, hud.HP_TEXT) or self.hp

    def locate(self):
        tag = np.load(ROOT / "assets" / "self_tag_gray.npy")
        f = self.screen.grab()
        hit = find_self(f, tag)
        if hit is None:
            raise Abort("own name tag not found - stand where it's visible")
        x, y, w, h, score = hit
        cx = x + w // 2
        self.box = (max(0, cx - HALF_W), max(0, y - UP), min(f.shape[1], cx + HALF_W), min(f.shape[0], y + h + DOWN))
        return hit

    # --- the trials ------------------------------------------------------------------------------------------------
    def rest(self, lo=1.3, hi=2.4):
        t = self.now() + U(lo, hi)
        self.wait_until(t)
        return self.now()

    def face(self, side):
        self.press(side, self.now() + 0.02, U(0.05, 0.08))
        return self.rest(0.9, 1.2)

    def run(self, atk):
        # ~60 s; no turn_hold (it walks: small rooms, other players). The full set: turn_hold x3, more of each.
        trials = (["single"] * 4 + ["short"] * 2 + [("double", r) for r in ((0.12, 0.25), (0.3, 0.5), (0.55, 0.8))
                                                       for _ in range(2)]
                  + [("turn_tap", r) for r in ((0.1, 0.4), (0.4, 0.7), (0.7, 1.0)) for _ in range(2)]
                  + ["turn_first"] * 2)
        random.shuffle(trials)
        trials += ["hold"]
        for side in ("right", "left", "right"):
            self.mark("face", side=side)
            self.face(side)
        for i, tr in enumerate(trials):
            name, rng = (tr if isinstance(tr, tuple) else (tr, None))
            print(f"  {i + 1}/{len(trials)} {name}", flush=True)
            if name.startswith("turn"):
                self.mark("face", side="right")
                self.face("right")
            t = self.now() + 0.05
            self.mark(name, at=round(t, 4))
            if name == "single":
                self.press(atk, t, U(0.08, 0.15))
            elif name == "short":
                self.press(atk, t, U(0.016, 0.035))
            elif name == "double":
                self.press(atk, t, U(0.06, 0.11))
                self.press(atk, t + U(*rng), U(0.06, 0.11))
            elif name == "hold":
                self.press(atk, t, U(2.5, 3.0))
            elif name == "turn_tap":
                self.press(atk, t, U(0.08, 0.13))
                self.press("left", t + U(*rng), U(0.05, 0.08))
            elif name == "turn_hold":
                self.press(atk, t, U(0.08, 0.13))
                at = t + U(0.1, 0.5)
                held = U(0.9, 1.1)
                self.press("left", at, held)
                self.rest(0.6, 0.8)
                self.mark("walk_back")
                self.press("right", self.now() + 0.02, held)
            elif name == "turn_first":
                up = self.press("left", t, U(0.05, 0.08))
                self.press(atk, up + U(0.02, 0.10), U(0.08, 0.13))
            self.rest()
        self.mark("end")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    hwnd = find_window()
    if not hwnd:
        print("MapleStory window not found")
        return 1
    print("switching to the game in 3 s - hands off the keyboard and mouse")
    time.sleep(3)
    if not bring_to_front(hwnd):
        print("couldn't bring the game to front")
        return 1
    time.sleep(0.5)
    screen = Screen(hwnd)
    p = Probe(hwnd, screen, out)
    try:
        hit = p.locate()
        print(f"capture {screen.kind}, tag at {hit[:2]} score {hit[4]:.2f}, crop {p.box}")
        th = threading.Thread(target=p.capture, daemon=True)
        th.start()
        time.sleep(0.5)
        p.run(Keys.attack)
    except Abort as e:
        print("ABORTED:", e)
    finally:
        p.release()
        p.stop.set()
        time.sleep(0.1)
        screen.close()
    n = len(p.times)
    dur = p.times[-1] - p.times[0] if n > 1 else 0
    np.savez(out / "crops.npz", t=np.array(p.times), jpg=np.array(p.crops, dtype=object))
    (out / "events.json").write_text(json.dumps(p.events, indent=0))
    (out / "meta.json").write_text(json.dumps({"box": p.box, "attack": Keys.attack, "frames": n,
                                               "fps": round(n / dur, 1) if dur else None, "capture": screen.kind}))
    print(f"done: {n} frames, {n / dur if dur else 0:.1f} fps -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
