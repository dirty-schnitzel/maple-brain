"""PLAN-tracker step 4b, try 2 (answer 3): by-eye sheets of the L5-labelled pets and standing players whose tracks'
body heights cross into the other class - the lowest player tracks and the highest pet tracks by a high percentile of
their heights over the stay. Per track: its labelled frame and its sightings nearest that percentile, the tag boxed
(yellow) and the column the body is read in (cyan: 17 px over the tag's centre, from its top up the height read).

    python tools/perc/track/height_sheet.py [--q 90] [--k 6] [--per 4]   -> CORPUS/work/track-plan/step4b/heights_*.png
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import replay_players as RP  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", type=int, default=90)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--per", type=int, default=4)
    a = ap.parse_args()
    import cv2
    import frames as rec
    tracks = {"pet": [], "player": []}
    for cap in RP.L5_CAPS:
        res = RP.load(cap)
        by = {f["n"]: f for f in res["frames"]}
        trs = {t["id"]: t for t in res["tracks"]}
        lab = json.loads((RP.LABELS / cap / "labels" / "L5.json").read_text(encoding="utf-8"))
        seen = set()
        for n, fr in lab["frames"].items():
            f = by[int(n)]
            idx = {tuple(b): i for i, b in enumerate(f["tags"])}
            for e in fr["tags"]:
                k = e["class"]
                if k not in ("pet", "player") or (k == "player" and e.get("place") != "stand"):
                    continue
                i = idx.get(tuple(e["box"]))
                tid = None if i is None else f["trk"][i]
                if not tid or tid not in trs or (k, tid) in seen or abs(e["box"][2] - trs[tid]["w"]) > 1:
                    continue                            # (a tag on a track of another name: left out)
                seen.add((k, tid))
                tr = trs[tid]
                hist = tr["hb1"] if tr["hb1"].sum() >= 5 else tr["hb"]
                q = RP.hpct(hist, a.q)
                if q is not None:
                    tracks[k].append((q, cap, tid, int(n), tr, by))
    for k, rev in (("player", False), ("pet", True)):
        pick = sorted(tracks[k], key=lambda x: x[0], reverse=rev)[:a.k]
        cells = []
        for q, cap, tid, n_lab, tr, by in pick:
            c = RP.dump.clip_of(cap)
            rows = {r[0]: r for r in tr["hist"]}
            near = sorted((abs(b - q), n) for n, b, w, cut in tr["bseq"] if b > 0 and w)[:a.per - 1]
            for n in [n_lab] + [m for _, m in near]:
                f = by.get(n)
                img = rec.read(c.run, rec.name_of(n))
                if img is None or f is None:
                    continue
                box = None
                for i, t in enumerate(f["trk"]):
                    if t == tid:
                        box = f["tags"][i]
                if box is None:
                    continue
                x, y, w, h = box
                body = next((b for m, b, ww, cut in tr["bseq"] if m == n), -1)
                cx = x + w // 2
                X0, Y0 = int(min(max(0, cx - 110), img.shape[1] - 220)), int(min(max(0, y - 150), img.shape[0] - 190))
                crop = img[Y0:Y0 + 190, X0:X0 + 220].copy()
                cv2.rectangle(crop, (x - X0 - 1, y - Y0 - 1), (x + w - X0, y + h - Y0), (0, 230, 255), 1)
                if body > 0:
                    cv2.rectangle(crop, (cx - 8 - X0, y - body - Y0), (cx + 8 - X0, y - Y0), (255, 220, 0), 1)
                crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
                for j, line in enumerate((f"{k} {cap[-4:]} id{tid} p{a.q} {q}", f"n{n}{' LABEL' if n == n_lab else ''} body {body}")):
                    cv2.putText(crop, line, (4, 16 + 16 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
                    cv2.putText(crop, line, (4, 16 + 16 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                cells.append(crop)
        while len(cells) % a.per:
            cells.append(np.zeros_like(cells[0]))
        img = np.vstack([np.hstack(cells[i:i + a.per]) for i in range(0, len(cells), a.per)])
        p = RP.OUT / f"heights_{k}.png"
        cv2.imwrite(str(p), img)
        print(p, [(q, cap, tid) for q, cap, tid, *_ in pick])


if __name__ == "__main__":
    main()
