"""Tracker plan, the truth's own check BY EYE (docs/prompts/tracker-before.md step 5): stitched gaps and chain ends of
the hindsight truth (oracle.chains), picked at random over captures, each as one row of frame crops around the mob -
is it the same mob across the gap, did it really die / leave / get covered? The reference is the look, never a tool.

    python tools/perc/track/sheets.py CAP [CAP ...] --out DIR [--gaps 40] [--ends 20] [--seed 1] [--per 4]

Gaps are picked half among gaps <= LONG s and half among longer ones (uniformly over all gaps nearly every pick
would be a 1-3 frame gap); ends uniformly among chain ends that are not the capture's own end. Each row: the case's
number, capture, time, the mob type, then crops (CROP px, centred on the chain's map place at that moment, put on
screen by that frame's camera): a GAP = 0.25 s before the last sighting, the last sighting (green box), three frames
inside the gap (yellow: where the truth puts it, the line between the two sightings), the first sighting after
(green), 0.25 s after; an END = 0.5 / 0.15 s before the last sighting, the last sighting (green), then 0.1, 0.3, 0.7,
1.5 s after it (red: the last place). DIR/cases.json lists every case (the numbers on the sheets); the verdicts by
eye go into DIR/verdicts.json by hand.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load import Map, anim_of, clip, map_of, name_of, ticks        # noqa: E402
from oracle import POSE, T, X, Y, chains                            # noqa: E402

CROP = (300, 220)
LONG = 0.5
GREEN, YELLOW, RED, WHITE = (0, 220, 0), (0, 220, 255), (0, 0, 255), (255, 255, 255)


def nearest(tk, t) -> int:
    lo, hi = 0, len(tk) - 1
    while lo < hi:
        m = (lo + hi) // 2
        if tk[m]["t"] < t:
            lo = m + 1
        else:
            hi = m
    return lo


def crop(img, C, x, y, color, label):
    w, h = CROP
    if img is None or C is None:
        t = np.zeros((h, w, 3), np.uint8)
        cv2.putText(t, "no frame / camera", (10, h // 2), 0, 0.5, WHITE, 1)
        return t
    sx, sy = int(x - C[0]), int(y - C[1])
    cx, cy = sx, sy - 40
    x0, y0 = cx - w // 2, cy - h // 2                    # the tile's corner on screen
    t = np.zeros((h, w, 3), np.uint8)
    src = img[:700]
    a0, a1 = max(0, x0), min(src.shape[1], x0 + w)
    b0, b1 = max(0, y0), min(src.shape[0], y0 + h)
    if a1 > a0 and b1 > b0:
        t[b0 - y0:b1 - y0, a0 - x0:a1 - x0] = src[b0:b1, a0:a1]
    px, py = sx - x0, sy - y0
    cv2.rectangle(t, (px - 30, py - 70), (px + 30, py + 4), color, 1)
    cv2.circle(t, (px, py), 3, color, -1)
    cv2.putText(t, label, (4, 14), 0, 0.42, WHITE, 1)
    return t


def gap_cases(cap, tk, ch):
    out = []
    for c in ch:
        for k, g in enumerate(c["gaps"]):
            a, b = c["parts"][k]["pts"][-1], c["parts"][k + 1]["pts"][0]
            out.append({"kind": "gap", "cap": cap, "type": c["type"], "a": a, "b": b, "dt": b[T] - a[T],
                        "amb": g[4], "start": c["start"], "end": c["end"]})
    return out


def end_cases(cap, tk, ch):
    return [{"kind": "end", "cap": cap, "type": c["type"], "a": c["parts"][-1]["pts"][-1], "end": c["end"],
             "start": c["start"]} for c in ch if c["end"] != "run end"]


def row(case, tk, cl, names) -> np.ndarray:
    a = case["a"]
    tiles = []
    if case["kind"] == "gap":
        b = case["b"]
        ts = [(a[T] - 0.25, a, GREEN, "-0.25"), (a[T], a, GREEN, "last seen")]
        for f in (0.25, 0.5, 0.75):
            ts.append((a[T] + f * (b[T] - a[T]), None, YELLOW, f"gap {f:.2f}"))
        ts += [(b[T], b, GREEN, "seen again"), (b[T] + 0.25, b, GREEN, "+0.25")]
        for t, p, col, lab in ts:
            i = nearest(tk, t)
            if p is None:
                w = (tk[i]["t"] - a[T]) / max(1e-6, b[T] - a[T])
                x, y = a[X] + w * (b[X] - a[X]), a[Y] + w * (b[Y] - a[Y])
            else:
                x, y = p[X], p[Y]
            tiles.append(crop(cl.read(tk[i]["frame"]), tk[i]["C"], x, y, col, f"{lab} {tk[i]['t'] - a[T]:+.2f}s"))
    else:
        for dt, col, lab in ((-0.5, GREEN, "-0.5"), (-0.15, GREEN, "-0.15"), (0.0, GREEN, "last seen"),
                             (0.1, RED, "+0.1"), (0.3, RED, "+0.3"), (0.7, RED, "+0.7"), (1.5, RED, "+1.5")):
            i = nearest(tk, a[T] + dt)
            tiles.append(crop(cl.read(tk[i]["frame"]), tk[i]["C"], a[X], a[Y], col, f"{lab} {tk[i]['t'] - a[T]:+.2f}s"))
    head = np.zeros((22, CROP[0] * len(tiles), 3), np.uint8)
    desc = (f"#{case['no']} {case['kind'].upper()} {case['cap']} t {a[T]:.2f} {names.get(case['type'], case['type'])} "
            f"pose {a[POSE]}" + (f" gap {case['dt']:.2f}s amb {case['amb']}" if case["kind"] == "gap" else
                                 f" end '{case['end']}'"))
    cv2.putText(head, desc, (4, 16), 0, 0.5, WHITE, 1)
    return np.vstack([head, np.hstack(tiles)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--gaps", type=int, default=40)
    ap.add_argument("--ends", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--per", type=int, default=4, help="cases per sheet")
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    gaps, ends, data = [], [], {}
    for cap in a.caps:
        tk = ticks(cap)
        ch = chains(tk)
        data[cap] = tk
        gaps += gap_cases(cap, tk, ch)
        ends += end_cases(cap, tk, ch)
    short = [g for g in gaps if g["dt"] <= LONG]
    long_ = [g for g in gaps if g["dt"] > LONG]
    pick = rnd.sample(short, min(len(short), a.gaps // 2)) + rnd.sample(long_, min(len(long_), a.gaps - a.gaps // 2))
    pick += rnd.sample(ends, min(len(ends), a.ends))
    for k, c in enumerate(pick):
        c["no"] = k + 1
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"gaps {len(gaps)} ({len(short)} <= {LONG} s, {len(long_)} longer), ends {len(ends)}; picked {len(pick)}")
    names = {}
    for cap in a.caps:
        names.update(Map(map_of(cap)).names)
    rows_, sheet = [], 0
    for c in pick:
        rows_.append(row(c, data[c["cap"]], clip(c["cap"]), names))
        if len(rows_) == a.per or c is pick[-1]:
            wmax = max(r.shape[1] for r in rows_)
            img = np.vstack([cv2.copyMakeBorder(r, 0, 4, 0, wmax - r.shape[1], cv2.BORDER_CONSTANT) for r in rows_])
            cv2.imwrite(str(a.out / f"sheet_{sheet:02d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            sheet, rows_ = sheet + 1, []
    out = [{"no": c["no"], "kind": c["kind"], "cap": c["cap"], "type": c["type"], "t": c["a"][T], "frame_n":
            data[c["cap"]][c["a"][0]]["n"], "pose": c["a"][POSE], "x": c["a"][X], "y": c["a"][Y],
            **({"dt": round(c["dt"], 3), "amb": c["amb"], "t_b": c["b"][T]} if c["kind"] == "gap" else {"end": c["end"]})}
           for c in pick]
    (a.out / "cases.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{sheet} sheets -> {a.out}")
    _ = anim_of, name_of


if __name__ == "__main__":
    main()
