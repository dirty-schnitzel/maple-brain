"""Mark what the bot believed on recorded frames, and pick the worst 'attacking nothing' moments.
usage: mark.py RUN_DIR [N]  -> RUN_DIR/marked_*.png"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
KEYS = {"q", "c", "space"}
SOLID, FRESH_S = 0.7, 0.5
REACH = (24, 139, 161)          # spear: sure near / sure far / maybe far, px in front


def body(mob_id, cache={}):
    if mob_id not in cache:
        try:
            m = json.loads((ROOT / "assets/mcw/mobs" / str(mob_id) / "mob.json").read_text(encoding="utf-8"))
            f = m["frames"]["stand"][0]
            cache[mob_id] = (m["info"].get("name") or str(mob_id), f["lt"], f["rb"])
        except Exception:                                   # noqa: BLE001
            cache[mob_id] = (str(mob_id), [-30, -55], [30, 0])
    return cache[mob_id]


def bars(f):
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    g = ((hsv[..., 0] >= 52) & (hsv[..., 0] <= 64) & (hsv[..., 1] > 200) & (hsv[..., 2] > 170)).astype(np.uint8)
    g[640:] = 0
    n, _, st, _ = cv2.connectedComponentsWithStats(g)
    return [tuple(int(v) for v in st[i][:4]) for i in range(1, n) if 2 <= st[i][3] <= 4 and 3 <= st[i][2] <= 40]


def label(img, text, org, color, scale=0.45):
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    x, y = org
    cv2.rectangle(img, (x - 1, y - h - 3), (x + w + 1, y + 2), (0, 0, 0), -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def main(run, n_out=3):
    run = Path(run)
    rows = [json.loads(line) for line in open(run / "ticks.jsonl", encoding="utf-8")]
    last_solid, peak = {}, {}
    marks = []                                              # (tick, problem text, badness)
    streak = {}
    for r in rows:
        o, t = r["obs"], r["obs"]["t"]
        for m in o.get("mobs", []):
            if m["src"] != "none":
                peak[m["id"]] = max(peak.get(m["id"], 0), m.get("score") or 0)
                if (m.get("score") or 0) >= SOLID and not (m.get("anim") or "").startswith("die"):
                    last_solid[m["id"]] = t
        r["_fresh"] = {i: t - s for i, s in last_solid.items()}
        r["_peak"] = dict(peak)
        s, v = r["timings"].get("self") or {}, r["timings"].get("v2") or {}
        f = v.get("facing") or 0
        held = bool(KEYS & set(r["timings"].get("held", [])))
        if not held or s.get("x") is None or not f:
            streak.clear()
            continue
        inr = [m for m in o.get("mobs", []) if m["state"] in ("live", "hit", "hidden")
               and -10 <= (m["x"] - s["x"]) * f <= REACH[2] and abs(m["y"] - s["y"]) <= 60]
        fresh = [m for m in inr if r["_fresh"].get(m["id"], 9) <= FRESH_S]
        if fresh:
            streak.clear()
            continue
        key = "stale" if inr else "nothing"
        streak[key] = streak.get(key, t)
        if r.get("frame"):
            marks.append((r, key, t - streak[key]))
    print(f"{len(rows)} ticks; attack held with no real mob in reach on {len(marks)} saved frames")
    picked, used = [], []
    for r, key, dur in sorted(marks, key=lambda x: -x[2]):
        if all(abs(r["obs"]["t"] - u) > 4 for u in used):
            picked.append((r, key, dur))
            used.append(r["obs"]["t"])
        if len(picked) >= n_out:
            break
    for r, key, dur in picked:
        draw(run, r, key, dur)


def draw(run, r, key, dur):
    o, t = r["obs"], r["obs"]["t"]
    img = cv2.imread(str(run / "frames" / r["frame"]))
    s, v = r["timings"]["self"], r["timings"]["v2"]
    cam, f = o["cam"], v.get("facing") or 0
    me = (int(s["x"] - cam[0]), int(s["y"] - cam[1]))
    # reach zone in front of us
    x_near, x_far = me[0] + f * REACH[0], me[0] + f * REACH[1]
    over = img.copy()
    cv2.rectangle(over, (min(x_near, x_far), me[1] - 60), (max(x_near, x_far), me[1] + 5), (255, 200, 0), -1)
    img = cv2.addWeighted(over, 0.18, img, 0.82, 0)
    cv2.rectangle(img, (min(x_near, x_far), me[1] - 60), (max(x_near, x_far), me[1] + 5), (255, 200, 0), 1)
    cv2.arrowedLine(img, (me[0], me[1] - 85), (me[0] + 40 * f, me[1] - 85), (255, 255, 255), 2, tipLength=0.35)
    label(img, f"US: facing {'right' if f > 0 else 'left'}, key {'+'.join(r['timings'].get('held', []))} held, "
          f"weapon {v.get('weapon')}", (me[0] - 120, me[1] + 28), (255, 255, 255))
    for b in bars(img):
        cv2.rectangle(img, (b[0] - 1, b[1] - 1), (b[0] + b[2] + 1, b[1] + b[3] + 1), (255, 255, 0), 1)
    for m in o.get("mobs", []):
        if m.get("kind") != "mob":
            continue
        name, lt, rb = body(m["mob"])
        fx, fy = int(m["x"] - cam[0]), int(m["y"] - cam[1])
        box = (fx + lt[0], fy + lt[1], fx + rb[0], fy + rb[1])
        age = r["_fresh"].get(m["id"], 9)
        if m["state"] == "dying":
            col, why = (160, 160, 160), "dying"
        elif m["src"] != "none" and (m.get("score") or 0) >= SOLID:
            col, why = (0, 220, 0), f"seen {m['score']:.2f}"
        elif m["src"] != "none":
            col, why = (0, 220, 255), f"WEAK match {m['score']:.2f}"
        else:
            col, why = (0, 0, 255), f"NOT SEEN for {m.get('unseen', 0):.1f}s"
        thick = 3 if m["id"] == v.get("target") else 1
        cv2.rectangle(img, box[:2], box[2:], col, thick)
        tag = f"#{m['id']} {name} {why}" + (" <- TARGET" if m["id"] == v.get("target") else "")
        if age > FRESH_S and m["state"] != "dying":
            tag += f" (last good look {age:.1f}s ago)" if age < 9 else " (never seen well)"
        label(img, tag, (box[0], box[1] - 4), col, 0.4)
    problem = ("ATTACKING NOTHING: the bot holds the attack key; every mob it thinks is in reach was last seen well "
               f"> {FRESH_S}s ago (red/yellow boxes)" if key == "stale"
               else "ATTACKING NOTHING: attack key held, no tracked mob in reach at all")
    cv2.rectangle(img, (0, 0), (1366, 44), (0, 0, 0), -1)
    label(img, f"t={t:.2f}s  {problem}", (6, 18), (0, 80, 255), 0.5)
    label(img, f"going on for {dur:.1f}s.  green = mob seen now (>= {SOLID})  yellow = weak match  red = not seen  "
           f"grey = dying  blue zone = our reach  cyan = HP bars on screen", (6, 38), (255, 255, 255), 0.45)
    out = run / f"marked_{t:06.2f}.png"
    cv2.imwrite(str(out), img)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3)
