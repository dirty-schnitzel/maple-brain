"""Tracks of replay B that replay A doesn't have (the ghost check of step 3.4): on the fit path every sighting scores
1.0, so compare.py's WEAK class (best score < 0.80) no longer flags a ghost - every B track whose track-frames A does
not find (same type, feet within --tol px) on more than half its frames is listed and drawn, to be judged by eye.

    python tools/perc/replay/new_tracks.py RUN A B [--tol 20] [--share 0.5] [--out PNG]

Sheet (default RUN/replay/new_<B>.png): per new track two panels - its first sighted frame and its middle frame -
cropped around it: red = B's track (id, type, state, src), blue = A's tracks there, green = the fit's mobs (B's rows,
FrameFacts v3 `fit`). Prints one line per new track: id, type, frames, found in A, sighted share, t0-t1, screen place.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402

NAMES = {19: "Horny", 21: "Zombie", 17: "Stirge", 14: "Bubbling"}
W, H = 260, 200


def load(run: Path, name: str) -> list:
    return [json.loads(line) for line in open(run / "replay" / f"{name}.jsonl", encoding="utf-8")]


def new_tracks(ra: list, rb: list, tol: float, share: float) -> dict:
    """B track id -> {"frames": [(row index, mob)], "found": n found in A, "seen": n sighted}."""
    a_by = {r["n"]: r for r in ra}
    out = {}
    for i, r in enumerate(rb):
        a = a_by.get(r["n"])
        if a is None:
            continue
        pool = [m for m in a["mobs"] if m["state"] not in ("tentative", "offscreen")]
        for m in r["mobs"]:
            if m["state"] in ("tentative", "offscreen"):
                continue
            d = out.setdefault(m["id"], {"frames": [], "found": 0, "seen": 0})
            d["frames"].append((i, m))
            d["found"] += any(p["mob"] == m["mob"] and abs(p["sx"] - m["sx"]) <= tol and abs(p["sy"] - m["sy"]) <= tol
                              for p in pool)
            d["seen"] += m["src"] != "none"
    return {k: d for k, d in out.items() if d["found"] <= share * len(d["frames"])}


def panel(run: Path, row: dict, arow: dict | None, m: dict) -> np.ndarray:
    img = rec.read(run, row["frame"])
    cx, cy = int(m["sx"]), int(m["sy"]) - 40
    x0, y0 = max(0, min(img.shape[1] - W, cx - W // 2)), max(0, min(img.shape[0] - H, cy - H // 2))
    c = img[y0:y0 + H, x0:x0 + W].copy()
    for f in row.get("fit") or []:
        cv2.circle(c, (int(f["feet"][0]) - x0, int(f["feet"][1]) - y0), 6, (0, 220, 0), 1)
    for p in (arow or {}).get("mobs") or []:
        if p["state"] not in ("tentative", "offscreen"):
            cv2.drawMarker(c, (int(p["sx"]) - x0, int(p["sy"]) - y0), (255, 120, 0), cv2.MARKER_TILTED_CROSS, 12, 2)
    cv2.drawMarker(c, (int(m["sx"]) - x0, int(m["sy"]) - y0), (0, 0, 255), cv2.MARKER_CROSS, 14, 2)
    txt = f"{row['t']:.1f} #{m['id']} {NAMES.get(m['mob'], m['mob'])} {m['state']} {m['anim']} {m['src']}"
    cv2.rectangle(c, (0, 0), (W, 14), (0, 0, 0), -1)
    cv2.putText(c, txt, (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1)
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--tol", type=float, default=20.0)
    ap.add_argument("--share", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    ra, rb = load(a.run, a.a), load(a.run, a.b)
    a_by = {r["n"]: r for r in ra}
    nt = new_tracks(ra, rb, a.tol, a.share)
    print(f"{a.run.name}: {len(nt)} tracks of {a.b} that {a.a} doesn't have (found on <= {a.share:.0%} of their frames)")
    tiles = []
    for k, d in sorted(nt.items()):
        fr = d["frames"]
        first = next(((i, m) for i, m in fr if m["src"] != "none"), fr[0])
        mid = fr[len(fr) // 2]
        m0 = first[1]
        print(f"  #{k} {NAMES.get(m0['mob'], m0['mob'])}: {len(fr)} frames, found in A {d['found']}, sighted "
              f"{d['seen']}, t {rb[fr[0][0]]['t']:.1f}-{rb[fr[-1][0]]['t']:.1f}, at ({m0['sx']}, {m0['sy']})")
        for i, m in (first, mid):
            tiles.append(panel(a.run, rb[i], a_by.get(rb[i]["n"]), m))
    if tiles:
        while len(tiles) % 6:
            tiles.append(np.zeros_like(tiles[0]))
        out = a.out or a.run / "replay" / f"new_{a.b}.png"
        cv2.imwrite(str(out), np.vstack([np.hstack(tiles[i:i + 6]) for i in range(0, len(tiles), 6)]))
        print(f"  sheet: {out}")


if __name__ == "__main__":
    main()
