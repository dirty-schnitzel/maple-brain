"""Pictures of drop_eval's cases: each miss / false / wrong identity as a 3x crop of its frame (+ the item's picture).

    python tools/loot/drop_sheet.py SET [--misses misses_before.json] [--what false,wrong,miss] [--gated] [--out NAME]
        SET = a synth set, or `labels` (S6: runs/loot_labels; frames read from the recordings; what may add `moving`)

Per case: the frame around the box (48 px margin, 3x), the box drawn (green = the truth drop, red = the sighting),
the client's picture beside it, a label (frame, class, item, kind / numbers). -> SET/sheet_<what>_<NAME>.png
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from drop_eval import GATED  # noqa: E402

M, S = 48, 3


def crop(img, box, window, boxes):
    x, y, w, h = box
    ox, oy = (window or [0, 0])[:2]
    x0, y0 = max(0, x - ox - M), max(0, y - oy - M)
    x1, y1 = min(img.shape[1], x - ox + w + M), min(img.shape[0], y - oy + h + M)
    c = cv2.resize(img[y0:y1, x0:x1], None, fx=S, fy=S, interpolation=cv2.INTER_NEAREST)
    for b, col in boxes:
        bx, by = (b[0] - ox - x0) * S, (b[1] - oy - y0) * S
        cv2.rectangle(c, (bx - 1, by - 1), (bx + b[2] * S, by + b[3] * S), col, 1)
    return c


def pic_tile(items, item, f):
    for g in range(len(items)):
        if items.item[g] == item and items.f[g] == f:
            p = items.pics[g]
            a = p[..., 3:4] / 255.0
            t = (p[..., :3] * a + 90 * (1 - a)).astype(np.uint8)
            return cv2.resize(t, None, fx=S, fy=S, interpolation=cv2.INTER_NEAREST)
    return np.zeros((10, 10, 3), np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("--misses", default="misses_before.json")
    ap.add_argument("--what", default="false,wrong,miss")
    ap.add_argument("--gated", action="store_true", help="misses of the gated classes only")
    ap.add_argument("--out", default="before")
    ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args()
    from maplebrain.gamedata import load_items
    items = load_items()
    labels = a.set == "labels"
    if labels:
        from drop_eval import LGATED
        from lootlib import frame as read_frame
        sys.path.insert(0, str(HERE / "labels"))
        from pick import RUNS
        sd = HERE.parents[1] / "runs" / "loot_labels"
        truth = None
    else:
        sd = Path(a.set)
        truth = json.loads((sd / "synth.json").read_text(encoding="utf-8"))["frames"]
    ev = json.loads((sd / a.misses).read_text(encoding="utf-8"))
    for what in a.what.split(","):
        cases = {"false": ev["falses"], "wrong": ev["wrong"], "miss": ev["misses"],
                 "moving": ev.get("moving_rest", [])}[what]
        if what == "miss" and a.gated:
            cases = [m for m in cases if m["class"] in (LGATED if labels else GATED)]
        tiles = []
        for m in cases[:a.max]:
            if labels:
                key, name = m["frame"].split("/")
                f = {"frame": name}
                img = read_frame(HERE.parents[1] / RUNS[key], name)
            else:
                f = truth[m["frame"]]
                img = cv2.imread(str(sd / "frames" / f["frame"]))
            d, s = m.get("drop"), m.get("got")
            boxes = ([(d["box"], (0, 255, 0))] if d else []) + ([(s["box"], (0, 0, 255))] if s else [])
            c = crop(img, (d or s)["box"], f.get("window"), boxes)
            p = pic_tile(items, (d or s)["item"] or 0, (d or s).get("f", 0))
            h = max(c.shape[0], p.shape[0]) + 30
            t = np.zeros((h, c.shape[1] + p.shape[1] + 6, 3), np.uint8)
            t[:c.shape[0], :c.shape[1]] = c
            t[:p.shape[0], c.shape[1] + 6:] = p
            lab = (f"{m['frame'][-14:]} {m.get('class', '')} {items.name((d or s)['item'] or 0)[:18]}" +
                   (f" -> {s['kind']} {s['seen']}/{s['n_op']} dy {s['dy']}" if s else " -> nothing"))
            if what == "wrong":
                lab = f"{m['frame']} {items.name(d['item'])[:18]} -> {items.name(s['item'])[:18]} ({s['kind']})"
            cv2.putText(t, lab[:70], (2, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            tiles.append(t)
        if not tiles:
            continue
        W = max(t.shape[1] for t in tiles)
        cols = max(1, 1800 // W)
        H = max(t.shape[0] for t in tiles)
        rows = -(-len(tiles) // cols)
        sh = np.full((rows * (H + 4), cols * (W + 4), 3), 30, np.uint8)
        for i, t in enumerate(tiles):
            y, x = (i // cols) * (H + 4), (i % cols) * (W + 4)
            sh[y:y + t.shape[0], x:x + t.shape[1]] = t
        p = sd / f"sheet_{what}_{a.out}.png"
        cv2.imwrite(str(p), sh)
        print(f"{p}: {len(tiles)} of {len(cases)}")


if __name__ == "__main__":
    main()
