"""brain v2 per-press runs: what each attack press was aimed at, presses after deaths, the rhythm vs the user.

    python tools/combat/probe/bot_presses.py RUN_DIR [N_MARK]

Per press (ticks.jsonl: timings.v2.swing set on the press tick), mobs in front of us (-10..165 px, |dy| <= 60):
    solid    one seen well (score >= 0.7, not a die anim) in the last 0.5 s
    stale    only tracks not seen well lately (a ghost under our effects, a dead mob kept alive, scenery)
    nothing  no track in front at all
A death in front: a track turns `dying` within 165 px in front. A press <= 1.0 s after it with no SOLID mob in front =
a press at nothing after a kill (the user: 7 of 71 kills had one). Gaps: press -> next press (< 2.5 s) minus the swing
length, vs the user's deciles. N_MARK (default 12): the worst presses (nothing / stale, after-death first) drawn into
RUN_DIR/marked_presses.png (frame nearest the press: our feet, front reach, tracks with score / age).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

R = Path(sys.argv[1])
N_MARK = int(sys.argv[2]) if len(sys.argv) > 2 else 12
SWING_S, SOLID, FRESH = 0.92, 0.7, 0.5
USER_GAP = (0.0, 0.015, 0.03, 0.052, 0.068, 0.09, 0.112, 0.15, 0.188, 0.458, 0.98)

L = [json.loads(x) for x in open(R / "ticks.jsonl", encoding="utf-8")]


def pct(v, ps=(0.1, 0.5, 0.9)):
    v = sorted(v)
    return [round(v[min(len(v) - 1, int(p * len(v)))], 2) for p in ps] if v else None


last_good, seen_dying, deaths = {}, set(), []
presses = []
for l in L:
    o, tm = l["obs"], l["timings"]
    t, s, v = o["t"], tm.get("self") or {}, tm.get("v2") or {}
    f = v.get("facing") or 0
    for m in o.get("mobs") or []:
        if m.get("src") != "none" and (m.get("score") or 0) >= SOLID and not (m.get("anim") or "").startswith("die"):
            last_good[m["id"]] = t
    if s.get("x") is None or not f:
        continue
    front = [m for m in o.get("mobs") or [] if m.get("kind") == "mob" and -10 <= (m["x"] - s["x"]) * f <= 165
             and abs(m["y"] - s["y"]) <= 60]
    for m in front:
        if m["state"] == "dying" and m["id"] not in seen_dying:
            seen_dying.add(m["id"])
            deaths.append((t, m["id"]))
    if not v.get("swing"):
        continue
    live = [m for m in front if m["state"] in ("live", "hit", "hidden")]
    solid = [m for m in live if t - last_good.get(m["id"], -9) <= FRESH]
    kind = "solid" if solid else "stale" if live else "nothing"
    presses.append({"t": t, "kind": kind, "l": l, "live": live, "engaged": v["swing"].get("engaged")})

pt = [p["t"] for p in presses]
for p in presses:
    p["after_death"] = next((round(p["t"] - d, 2) for d, _ in reversed(deaths) if 0 <= p["t"] - d <= 1.0), None)
dur = L[-1]["obs"]["t"] - L[0]["obs"]["t"]
c = {k: sum(p["kind"] == k for p in presses) for k in ("solid", "stale", "nothing")}
print(f"{R}: {dur / 60:.1f} min, {len(presses)} presses ({len(presses) / dur * 60:.0f}/min; the user 32/min mashing)")
print(f"  aimed at: solid {c['solid']}, stale track only {c['stale']}, nothing {c['nothing']}")
ad = [p for p in presses if p["after_death"] is not None]
bad = [p for p in ad if p["kind"] != "solid"]
print(f"  deaths in front: {len(deaths)}; presses <= 1 s after one: {len(ad)}, of them at no solid mob: {len(bad)} "
      f"(after the death: {sorted(p['after_death'] for p in bad)})")
g = [b - a - SWING_S for a, b in zip(pt, pt[1:]) if b - a < 2.5]
print(f"  gap after the swing (press -> next press - {SWING_S}) p10/50/90 {pct(g)}; min {min(g, default=None)}; "
      f"the user p10/50/90 {USER_GAP[1]}/{USER_GAP[5]}/{USER_GAP[9]}")
print(f"  presses closer than the swing (would be ignored by the game): {sum(x < -0.02 for x in g)}")

# marked frames: the worst presses
worst = sorted([p for p in presses if p["kind"] != "solid"], key=lambda p: (p["after_death"] is None, p["kind"] != "nothing"))
worst = worst[:N_MARK]
tiles = []
fr = [l for l in L if l.get("frame") is not None]
ft = [l["obs"]["t"] for l in fr]
for p in sorted(worst, key=lambda p: p["t"]):
    i = int(np.argmin(np.abs(np.array(ft) - p["t"])))
    l = fr[i]
    img = cv2.imread(str(R / "frames" / l["frame"]))
    if img is None:
        continue
    o, tm = l["obs"], l["timings"]
    s, v = tm.get("self") or {}, tm.get("v2") or {}
    cam = o.get("cam")
    if o.get("me"):
        cx, cy = int(o["me"][0]), int(o["me"][1])
    elif cam and s.get("x") is not None:
        cx, cy = int(s["x"] - cam[0]), int(s["y"] - cam[1])
    else:
        continue
    f = (p["l"]["timings"].get("v2") or {}).get("facing") or 1
    cv2.line(img, (cx, cy), (cx + 165 * f, cy), (0, 255, 0), 2)                      # our front reach
    cv2.circle(img, (cx, cy), 5, (0, 255, 0), -1)
    if cam:
        for m in o.get("mobs") or []:
            if m.get("kind") != "mob":
                continue
            mx, my = int(m["x"] - cam[0]), int(m["y"] - cam[1])
            age = o["t"] - last_good.get(m["id"], -9)
            col = (0, 0, 255) if m["state"] == "dying" else (0, 255, 255) if age <= FRESH else (255, 0, 255)
            cv2.rectangle(img, (mx - 25, my - 50), (mx + 25, my), col, 2)
            cv2.putText(img, f"{m['id']} {m['state'][:4]} {m.get('score') or 0:.2f} {min(age, 9):.1f}s",
                        (mx - 40, my - 54), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
    x0, y0 = min(max(cx - 210, 0), 1366 - 420), min(max(cy - 170, 0), 768 - 230)
    tile = img[y0:y0 + 230, x0:x0 + 420].copy()
    txt = (f"press {p['t']:.2f} (frame {o['t'] - p['t']:+.2f}) {p['kind']}"
           + (f" {p['after_death']}s after a death" if p["after_death"] is not None else "") + f" eng {p['engaged']}")
    cv2.rectangle(tile, (0, 0), (420, 15), (0, 0, 0), -1)
    cv2.putText(tile, txt, (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
    tiles.append(tile)
if tiles:
    cols = 3
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(str(R / "marked_presses.png"), cv2.vconcat([cv2.hconcat(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))
    print(f"  marked {len(worst)} presses -> {R / 'marked_presses.png'} (green: our front reach; yellow: seen well "
          f"<= {FRESH} s; magenta: stale; red: dying)")
