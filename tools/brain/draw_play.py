"""Brain plan, picture 1: a map with its spawn points and where the user stood and walked in one capture (the kept
replay's feet), so the plan's questions about platforms are asked on a picture (PLAN-brain.md).

    python tools/brain/draw_play.py CAP [--out PNG] [--scale 0.6]

Drawn: footholds (grey; the nodes the user stood on most in blue, labelled with the node id and its share of
standing frames), ropes (brown), spawn points (dots: one colour per mob kind, with the point's index), the user's
feet over the capture (a yellow trail; brighter = more time), the frames of their attack presses (red ticks).
"""
import argparse
import collections
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "brain"))
from proto_play import ASSASSIN, load_keys, load_state, presses, stay_dir, at  # noqa: E402
from maplebrain.track.graph import Graph, PLACES  # noqa: E402

KIND_COL = [(80, 200, 255), (120, 255, 120), (255, 140, 200), (200, 200, 90)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--out", default=None)
    ap.add_argument("--scale", type=float, default=0.6)
    a = ap.parse_args()
    d, stay = stay_dir(a.cap)
    m = json.loads((ROOT / "assets" / "mcw" / "maps" / str(stay["map"]) / "map.json").read_text(encoding="utf-8"))
    g = Graph.for_map(stay["map"], ROOT / "assets" / "mcw", edges=False)
    fhs = list(m["footholds"].values())
    xs = [f["x1"] for f in fhs] + [f["x2"] for f in fhs]
    ys = [f["y1"] for f in fhs] + [f["y2"] for f in fhs]
    x0, x1, y0, y1 = min(xs) - 60, max(xs) + 60, min(ys) - 160, max(ys) + 60
    s = a.scale
    W, H = int((x1 - x0) * s), int((y1 - y0) * s)
    img = np.full((H, W, 3), 24, np.uint8)

    def P(x, y):
        return int((x - x0) * s), int((y - y0) * s)

    fr, _ = load_state(a.cap)
    ts = [f[0] for f in fr]
    fx = np.array([f[1][0] if f[1] else np.nan for f in fr])
    fy = np.array([f[1][1] if f[1] else np.nan for f in fr])
    ok = ~np.isnan(fx)
    pl = g.place(fx[ok], fy[ok], climb=np.ones(ok.sum(), bool))
    stand = collections.Counter(int(n) for n, p in zip(pl.node, pl.place) if PLACES[int(p)] == "stand")
    tot = max(1, sum(stand.values()))
    top = {n for n, c in stand.items() if c / tot >= 0.02}

    # heat of our feet
    heat = np.zeros((H, W), np.float32)
    for x, y in zip(fx[ok], fy[ok]):
        px, py = P(x, y)
        if 0 <= px < W and 0 <= py < H:
            heat[py, px] += 1
    heat = cv2.GaussianBlur(heat, (0, 0), 6)
    if heat.max() > 0:
        h = (np.sqrt(heat / heat.max()) * 255).astype(np.uint8)
        col = np.zeros_like(img)
        col[..., 1] = h
        col[..., 2] = h
        img = cv2.addWeighted(img, 1.0, col, 0.8, 0)

    # footholds by node
    node_of_fh = {}
    for nid, fhl in getattr(g, "node_footholds", {}).items():
        for f in fhl:
            node_of_fh[f] = nid
    for f in fhs:
        if f["x1"] == f["x2"]:
            continue                       # walls
        mid_x, mid_y = (f["x1"] + f["x2"]) / 2, (f["y1"] + f["y2"]) / 2
        nn = g.place(np.array([mid_x]), np.array([mid_y])).node[0]
        c = (255, 150, 60) if int(nn) in top else (150, 150, 150)
        cv2.line(img, P(f["x1"], f["y1"]), P(f["x2"], f["y2"]), c, 2)
    for r in m["ladderRopes"]:
        cv2.line(img, P(r["x"], r["y1"]), P(r["x"], r["y2"]), (40, 90, 160), 2)
    # node labels
    for n in top:
        sel = [(x, y) for x, y, nd, p in zip(fx[ok], fy[ok], pl.node, pl.place) if int(nd) == n and PLACES[int(p)] == "stand"]
        if sel:
            mx, my = np.median([v[0] for v in sel]), np.median([v[1] for v in sel])
            cv2.putText(img, f"{n}: {stand[n] / tot:.0%}", P(mx - 40, my + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 190, 90), 1, cv2.LINE_AA)
    # spawn points
    kinds = sorted({p["id"] for p in m["mobs"]})
    for p in m["mobs"]:
        if p.get("hidden"):
            continue
        c = KIND_COL[kinds.index(p["id"]) % len(KIND_COL)]
        cv2.circle(img, P(p["x"], p["y"] - 6), 4, c, -1)
    # attack presses
    keys = load_keys(d)
    for t, _ in presses(keys).get("space", []):
        f = fr[at(ts, t)]
        if f[1]:
            px, py = P(*f[1])
            cv2.line(img, (px, py - 6), (px, py - 14), (60, 60, 255), 1)
    cv2.putText(img, f"{stay['name']} - {a.cap}: spawn points (dots: " +
                ", ".join(f"kind {k}" for k in kinds) + "), our feet (yellow), attack presses (red), "
                "nodes stood on >= 2 % (blue, share)", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1,
                cv2.LINE_AA)
    out = a.out or str(Path("F:/dev/maple-corpus/work/brain-plan") / f"map_{a.cap.replace('#', '_')}.png")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out, img)
    print(out, img.shape)


if __name__ == "__main__":
    main()
