"""Coasting tracks explained in pictures (3.3 hints): examples from a gate replay's own rows, each as two panels - the
track's last sighting and a later frame where the tracker coasts it (src none: it predicts where the mob should be and
did not see it) - with what the fit says there.

    python tools/perc/fit/coast_sheet.py CLIP [--fp FP] [--out PNG]

Panels: red cross + id = the tracker's track (left: where it was SEEN, right: where it PREDICTS the mob while coasting);
green boxes = the fit's mobs on that frame (type, at their feet); the right panel's title = the case: FIT FOUND IT (a fit
mob of the track's type within 20 px), or the hint's reading of the one look at the predicted spot (ABSENT: the scene
shows there / COVERED: something else is drawn there / SEEN). Default out: RUN/fit/coasting_<clip>.png.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
import frames as rec  # noqa: E402
import gate  # noqa: E402
from shadow import near, verdict  # noqa: E402

NAMES = {19: "Horny", 21: "Zombie", 17: "Stirge", 14: "Bubbling"}
W, H = 300, 230


def crop(img, cx, cy):
    x0 = int(min(max(cx - W // 2, 0), img.shape[1] - W))
    y0 = int(min(max(cy - 170, 0), 700 - H))
    return img[y0:y0 + H, x0:x0 + W].copy(), x0, y0


def mark(panel, x0, y0, row, tr, title, colour):
    for f in row.get("fit") or []:
        fx, fy = f["feet"][0] - x0, f["feet"][1] - y0
        cv2.rectangle(panel, (fx - 26, fy - 62), (fx + 26, fy + 2), (0, 220, 0), 1)
        cv2.putText(panel, f"fit {NAMES.get(f['type'], f['type'])}", (fx - 26, fy + 14), cv2.FONT_HERSHEY_PLAIN, 0.9,
                    (0, 220, 0), 1)
    sx, sy = tr["sx"] - x0, tr["sy"] - y0
    cv2.drawMarker(panel, (sx, sy), (0, 0, 255), cv2.MARKER_CROSS, 18, 2)
    cv2.putText(panel, f"#{tr['id']}", (sx + 6, sy - 6), cv2.FONT_HERSHEY_PLAIN, 1.0, (0, 0, 255), 1)
    big = cv2.resize(panel, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    bar = np.full((34, big.shape[1], 3), 32, np.uint8)
    cv2.putText(bar, title, (6, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 1, cv2.LINE_AA)
    return np.concatenate([bar, big])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--fp", default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    run = ROOT / gate.CLIPS[a.clip][0]
    fp = a.fp or gate.fingerprint(None)
    rows = [json.loads(line) for line in open(run / "replay" / f"fp_{fp}_{a.clip}.jsonl", encoding="utf-8")]
    last = {}                                   # track id -> (row, its dict) at its last sighting
    picks = {}
    want = ("found", "absent", "covered", "dying")
    for k in rows:
        hints = {h["id"]: h for h in k.get("fit_hints") or []}
        for m in k["mobs"]:
            if m["src"] != "none":
                last[m["id"]] = (k, m)
                continue
            if m.get("kind", "mob") != "mob" or m["state"] not in ("live", "hidden", "hit", "dying"):
                continue
            if m["id"] not in last or not (0.25 <= m["unseen"] <= 0.6) or not (160 < m["sx"] < 1200 and m["sy"] > 200):
                continue
            if any(near(f, m, 20) for f in k.get("fit") or []):
                case = "found" if m["state"] != "dying" else None
            elif m["id"] in hints:
                v = verdict(hints[m["id"]])
                case = "dying" if m["state"] == "dying" and v == "absent" else (v if m["state"] != "dying" else None)
            else:
                case = None
            if case in want and case not in picks and all(p[2]["id"] != m["id"] for p in picks.values()):
                picks[case] = (last[m["id"]][0], last[m["id"]][1], m, k, hints.get(m["id"]))
    titles = {"found": ("tracker coasting, but the FIT SEES IT (green)", (80, 230, 80)),
              "absent": ("hint: ABSENT - the scene shows where it is predicted", (90, 160, 255)),
              "covered": ("hint: COVERED - something else is drawn there", (0, 200, 255)),
              "dying": ("dying track coasting, hint ABSENT: the corpse is gone", (90, 160, 255)),
              "seen": ("hint: SEEN", (80, 230, 80))}
    sheet = []
    for case in want:
        if case not in picks:
            continue
        k0, m0, m1, k1, h = picks[case]
        f0, f1 = rec.read(run, k0["frame"]), rec.read(run, k1["frame"])
        cx, cy = (m0["sx"] + m1["sx"]) / 2, (m0["sy"] + m1["sy"]) / 2
        p0, x0, y0 = crop(f0, cx, cy)
        p1, _, _ = crop(f1, cx, cy)
        name = NAMES.get(m1["mob"], m1["mob"])
        left = mark(p0, x0, y0, k0, m0, f"t {k0['t']:.2f} s: track #{m0['id']} {name} SEEN ({m0['src']})",
                    (230, 230, 230))
        ht = "" if h is None else f"  [look: {h['n_seen']} seen / {h['n_abs']} absent / {h['n_inf']} px]"
        right = mark(p1, x0, y0, k1, m1, f"t {k1['t']:.2f} s: COASTING {m1['unseen']:.2f} s ({m1['state']})",
                     (230, 230, 230))
        cap = np.full((30, left.shape[1] * 2 + 8, 3), 20, np.uint8)
        cv2.putText(cap, titles[case][0] + ht, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, titles[case][1], 1, cv2.LINE_AA)
        sheet += [cap, np.concatenate([left, np.full((left.shape[0], 8, 3), 20, np.uint8), right], axis=1),
                  np.full((12, left.shape[1] * 2 + 8, 3), 20, np.uint8)]
    out = a.out or run / "fit" / f"coasting_{a.clip}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.concatenate(sheet))
    print(f"{len(picks)} examples ({', '.join(picks)}) -> {out}")


if __name__ == "__main__":
    main()
