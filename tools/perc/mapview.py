"""Picture of one recorded frame in map coordinates (perception rework).

Top: the frame with the map's platforms / ropes / spawns projected onto it (from our own map position), each
reference mob (truth.jsonl) at its feet with its map x/y and platform. Bottom: the whole map seen from the side,
us (white) and the mobs (red / orange) placed on it, the camera's view as a box.

  python tools/perc/mapview.py RUN MAP N OUT.png [--truth truth.jsonl]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebrain.nav.navmap import NavMap  # noqa: E402

COL = {8: (60, 60, 255), 10: (0, 170, 255)}     # Pig red, Ribbon Pig orange (BGR); others yellow


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("map", type=int)
    ap.add_argument("n", type=int, help="tick number")
    ap.add_argument("out")
    ap.add_argument("--truth", default="truth.jsonl")
    a = ap.parse_args()
    run = Path(a.run)
    nav = NavMap.for_map(a.map, ROOT / "assets/mcw")
    names = {}
    for mid in {int(s["id"]) for s in json.loads((ROOT / f"assets/mcw/maps/{a.map}/map.json").read_text())["mobs"]}:
        names[mid] = json.loads((ROOT / f"assets/mcw/mobs/{mid}/mob.json").read_text())["name"]
    tick = next(json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8") if json.loads(l)["n"] == a.n)
    truth = next((json.loads(l) for l in open(run / a.truth, encoding="utf-8") if json.loads(l)["n"] == a.n), None)
    o = tick["obs"]
    frame = cv2.imread(str(run / "frames" / tick["frame"]))
    (sx, sf), (mx, my) = o["me"], o["map_pos"]
    plat = nav.platforms.get(o["platform"]) if o.get("platform") is not None else None
    if plat is not None and plat.y_at(mx) is not None:
        my = plat.y_at(mx)                       # on a platform our feet are exactly its surface
    ox, oy = mx - sx, my - sf                    # screen + (ox, oy) = map

    # ---- top: the frame, map drawn onto it
    top = frame.copy()
    for p in nav.platforms.values():
        pts = [(s.x1, s.y1) for s in p.segs] + [(p.segs[-1].x2, p.segs[-1].y2)]
        pts = np.array([(x - ox, y - oy) for x, y in pts], np.int32)
        cv2.polylines(top, [pts], False, (255, 255, 0), 2)
        lx, ly = pts[0]
        if -50 < lx < frame.shape[1] and 0 < ly < frame.shape[0]:
            cv2.putText(top, f"P{p.id}", (int(max(lx, 2)), int(ly) + 16), 0, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
    for r in nav.ropes:
        cv2.line(top, (int(r.x - ox), int(r.top - oy)), (int(r.x - ox), int(r.bottom - oy)), (0, 255, 255), 2)
    for x, y in nav.spawns:
        cv2.drawMarker(top, (int(x - ox), int(y - oy)), (255, 0, 255), cv2.MARKER_TILTED_CROSS, 12, 2)
    cv2.circle(top, (int(sx), int(sf)), 6, (255, 255, 255), -1)
    cv2.putText(top, f"me  map x {mx:.0f} y {my:.0f}  P{o.get('platform')}", (int(sx) - 60, int(sf) + 34), 0, 0.55,
                (255, 255, 255), 2, cv2.LINE_AA)
    mobs = []
    for m in (truth or {}).get("mobs", []):
        fx, fy = m["feet"]
        wx, wy = fx + ox, fy + oy
        p = nav.platform_at(wx, wy)
        mobs.append((m, wx, wy, p))
        c = COL.get(m["id"], (0, 255, 255))
        x, y, w, h = m["box"]
        cv2.rectangle(top, (x, y), (x + w, y + h), c, 1)
        cv2.circle(top, (int(fx), int(fy)), 5, c, -1)
        lab = f"{names.get(m['id'], m['id'])} {m['anim']} {m['facing'][0]}"
        lab2 = f"x {wx:.0f} y {wy:.0f} " + (f"P{p.id}" if p else "air")
        cv2.putText(top, lab, (x, y - 20), 0, 0.5, c, 2, cv2.LINE_AA)
        cv2.putText(top, lab2, (x, y - 5), 0, 0.5, c, 2, cv2.LINE_AA)

    # ---- bottom: the whole map, side view
    xs = [s.x1 for p in nav.platforms.values() for s in p.segs] + [s.x2 for p in nav.platforms.values() for s in p.segs]
    ys = [s.y1 for p in nav.platforms.values() for s in p.segs] + [r.top for r in nav.ropes]
    x0, x1, y0, y1 = min(xs) - 40, max(xs) + 40, min(ys) - 80, max(ys) + 40
    W = frame.shape[1]
    k = W / (x1 - x0)
    H = int((y1 - y0) * k) + 30
    bot = np.full((H, W, 3), 30, np.uint8)
    P = lambda x, y: (int((x - x0) * k), int((y - y0) * k) + 20)  # noqa: E731
    for p in nav.platforms.values():
        pts = np.array([P(s.x1, s.y1) for s in p.segs] + [P(p.segs[-1].x2, p.segs[-1].y2)], np.int32)
        cv2.polylines(bot, [pts], False, (255, 255, 0), 2)
        cv2.putText(bot, f"P{p.id}", (pts[0][0], pts[0][1] + 14), 0, 0.4, (200, 200, 0), 1, cv2.LINE_AA)
    for r in nav.ropes:
        cv2.line(bot, P(r.x, r.top), P(r.x, r.bottom), (0, 255, 255), 2)
    for x, y in nav.spawns:
        cv2.drawMarker(bot, P(x, y), (255, 0, 255), cv2.MARKER_TILTED_CROSS, 8, 1)
    vx0, vy0 = P(ox, oy)
    vx1, vy1 = P(ox + W, oy + 700)
    cv2.rectangle(bot, (vx0, vy0), (vx1, vy1), (160, 160, 160), 1)
    cv2.putText(bot, "camera view", (vx0 + 4, vy0 + 14), 0, 0.45, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.circle(bot, P(mx, my), 6, (255, 255, 255), -1)
    for m, wx, wy, p in mobs:
        cv2.circle(bot, P(wx, wy), 5, COL.get(m["id"], (0, 255, 255)), -1)
    cv2.putText(bot, f"map {a.map}: {len(nav.platforms)} platforms, {len(nav.ropes)} ropes, "
                f"{len(nav.spawns)} spawns (x); white = us, dots = mobs", (8, H - 8), 0, 0.5, (220, 220, 220), 1,
                cv2.LINE_AA)
    cv2.imwrite(a.out, np.vstack([top[:700], bot]))
    print(f"me screen ({sx:.0f}, {sf:.0f}) map ({mx:.0f}, {my:.0f}); offset ({ox:.0f}, {oy:.0f})")
    for m, wx, wy, p in mobs:
        print(f"  {names.get(m['id'])} {m['anim']}{m['n']} {m['facing']} screen feet {m['feet']} -> map "
              f"({wx:.0f}, {wy:.0f}) {'P' + str(p.id) if p else 'not on a platform'}  score {m['score']}")


if __name__ == "__main__":
    main()
