"""Reference mob detections for recorded frames (perception rework, stage 0).

Exhaustive, offline only: every pose of every mob on the map (stand / move / fly / hit1 / die1, both facings) over
the whole play area, coarse at 0.5 scale on the GPU (scores equal OpenCV's, tests/test_gpu_sprites.py), up to 200
peaks, each refined at full size against the mob's 8 best poses (OpenCV). Looser than the live detector (min 0.6),
but hit/die frames need >= 0.75 (faded die frames matched Perion's rock at 0.60-0.67: 68 of 71 "mobs").
(--cpu: the old all-OpenCV path, 2.6-8.7 s a frame.) Writes RUN/truth.jsonl: one line per frame
  {"n": tick, "frame": "000123.jpg", "t": s, "me": [x, feet] | null,
   "mobs": [{"id", "box": [x, y, w, h], "feet": [x, y], "anim", "n", "facing", "score"}]}

  python tools/perc/truth.py RUN MAP [--every K] [--t0 S --t1 S] [--min 0.6]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebot.perception.sprites import load_mob  # noqa: E402
from maplebot.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402

POSE_MIN = {}           # per-pose floors (none: low hit/die sightings are judged by `supported` instead)
SURE = 0.75             # hit/die sightings below this need a live sighting of the same mob nearby (see supported)


def supported(rows):
    """Drop hit/die sightings < SURE that no stand/move sighting of the same mob type backs: within 80 px, in the
    1.5 s before (hit1 also the 0.5 s after). A mob gets hit / dies where it just was alive; Perion's rock matched
    Snail die1_2 / Stump die1_1 at 0.60-0.67 with no mob there (68 of 71 "mobs" in acc3's first frame), while
    real, partly covered hit/die poses score as low (Rain-Forest: 0.64 behind a mushroom / a player)."""
    live = [(r["t"], m["id"], m["feet"]) for r in rows for m in r["mobs"] if m["anim"] not in ("hit1", "die1")]
    dropped = 0
    for r in rows:
        keep = []
        for m in r["mobs"]:
            if m["anim"] in ("hit1", "die1") and m["score"] < SURE:
                after = 0.5 if m["anim"] == "hit1" else 0.0
                if not any(i == m["id"] and r["t"] - 1.5 <= t <= r["t"] + after and abs(f[0] - m["feet"][0]) <= 80
                           and abs(f[1] - m["feet"][1]) <= 30 for t, i, f in live):
                    dropped += 1
                    continue
            keep.append(m)
        r["mobs"] = keep
    return dropped

PLAY_H = 700            # below: chat / HUD
SC = 0.5


class Book:
    """Every pose of one mob: (bgr, mask, small bgr, small mask, Pose)."""

    def __init__(self, mob):
        self.mob = mob
        self.items = []
        for (t, m), pose in list(zip(mob.frames, mob.poses)) + list(zip(mob.die or [], mob.die_poses or [])):
            if m.sum() < 60:
                continue
            ts = cv2.resize(t, None, fx=SC, fy=SC, interpolation=cv2.INTER_AREA)
            ms = (cv2.resize(m * 255, (ts.shape[1], ts.shape[0]), interpolation=cv2.INTER_AREA) > 160).astype(np.uint8)
            self.items.append((t, m, ts, ms, pose))


def match(img, t, m):
    if img.shape[0] < t.shape[0] or img.shape[1] < t.shape[1]:
        return None
    r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED, mask=m)
    r[~np.isfinite(r)] = -1
    return r


def detect(frame, books, min_score):
    play = frame[:PLAY_H]
    small = cv2.resize(play, None, fx=SC, fy=SC, interpolation=cv2.INTER_AREA)
    out = []
    for b in books:
        cand = []
        for j, (t, m, ts, ms, pose) in enumerate(b.items):
            r = match(small, ts, ms)
            if r is None:
                continue
            ys, xs = np.nonzero(r >= min_score - 0.08)          # coarse: a little looser, refined below
            for y, x in zip(ys, xs):
                cand.append((float(r[y, x]), int(x / SC), int(y / SC), j))
        cand.sort(key=lambda c: -c[0])
        kept = []                                               # one per spot: best coarse peak first
        gap = b.mob.max_w * 0.5
        for c in cand:
            if all(abs(c[1] - k[1]) > gap or abs(c[2] - k[2]) > b.mob.max_h * 0.5 for k in kept):
                kept.append(c)
            if len(kept) >= 40:
                break
        for _, x, y, _ in kept:                                 # refine: every pose, full size, small window
            best = None
            for t, m, _, _, pose in b.items:
                h, w = t.shape[:2]
                x0, y0 = max(0, x - 8), max(0, y - 8)
                win = play[y0:y + h + 8, x0:x + w + 8]
                r = match(win, t, m)
                if r is None:
                    continue
                _, s, _, loc = cv2.minMaxLoc(r)
                if best is None or s > best[0]:
                    best = (s, (x0 + loc[0], y0 + loc[1], w, h), pose)
            if best and best[0] >= max(min_score, POSE_MIN.get(best[2].anim, 0)):
                s, box, pose = best
                out.append({"id": b.mob.mob_id, "box": list(map(int, box)),
                            "feet": [int(box[0] + pose.ox), int(box[1] + pose.oy)],
                            "anim": pose.anim, "n": pose.n, "facing": pose.facing, "score": round(float(s), 3)})
    out.sort(key=lambda d: -d["score"])
    final = []                                                  # across mobs too (Stump / Dark Stump look alike)
    for d in out:
        if all(abs(d["feet"][0] - f["feet"][0]) > 20 or abs(d["feet"][1] - f["feet"][1]) > 20 for f in final):
            final.append(d)
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("map", type=int)
    ap.add_argument("--every", type=int, default=1, help="every K-th saved frame")
    ap.add_argument("--t0", type=float, default=0)
    ap.add_argument("--t1", type=float, default=1e9)
    ap.add_argument("--min", type=float, default=0.6)
    ap.add_argument("--out", default="truth.jsonl")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--threads", type=int, default=0, help="OpenCV threads (0 = all; keep low while a bot runs)")
    a = ap.parse_args()
    if a.threads:
        cv2.setNumThreads(a.threads)
    run = Path(a.run)
    mj = json.loads((ROOT / "assets/mcw/maps" / str(a.map) / "map.json").read_text(encoding="utf-8"))
    ids = sorted({int(x["id"]) for x in mj.get("mobs") or []})
    if a.cpu:
        books = [Book(load_mob(ROOT / "assets/mcw/mobs" / str(i))) for i in ids]
        print("mobs:", [(b.mob.name, len(b.items)) for b in books])
        find = lambda fr: detect(fr, books, a.min)                          # noqa: E731
    else:
        # two passes: live poses, then hit/die only where no live mob is. One pass let wrong die-frame matches on
        # Perion's rock claim a spot ("one mob per spot"), get dropped by `supported`, and hide the real mob there
        # (acc3: 47 of 47 checked GPU "extras" were real mobs the one-pass reference had lost)
        dirs = [ROOT / "assets/mcw/mobs" / str(i) for i in ids]
        g = GpuSpriteDetector(dirs, min_score=a.min, coarse_slack=0.08, max_cands=200)
        gp = GpuSpriteDetector(dirs, min_score=a.min, coarse_slack=0.08, max_cands=200, anims=("hit1", "die1"))
        print("mobs:", g.names, g.K, "+", gp.K, "templates on", g.dev)

        def rec(h):
            return {"id": h.mob_id, "box": list(map(int, h.box)), "feet": [int(v) for v in h.feet],
                    "anim": h.pose.anim, "n": h.pose.n, "facing": h.pose.facing, "score": h.score}

        def find(fr):
            out = [rec(h) for h in g.find(fr, top=8)]
            for h in gp.find(fr, top=8):
                if all(abs(h.feet[0] - o["feet"][0]) > 25 or abs(h.feet[1] - o["feet"][1]) > 25 for o in out):
                    out.append(rec(h))
            return out
    ticks = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
    ticks = [k for k in ticks if k.get("frame") and a.t0 <= k["obs"]["t"] <= a.t1][::a.every]
    t_start = time.time()
    rows = []
    for i, k in enumerate(ticks):
        frame = cv2.imread(str(run / "frames" / k["frame"]))
        if frame is None:
            continue
        mobs = find(frame)
        rows.append({"n": k["n"], "frame": k["frame"], "t": round(k["obs"]["t"], 3), "me": k["obs"].get("me"),
                     "mobs": mobs})
        if i % 50 == 0:
            el = time.time() - t_start
            print(f"{i}/{len(ticks)} {el / (i + 1) * 1000:.0f} ms/frame, {len(mobs)} mobs", flush=True)
    dropped = supported(rows)
    with open(run / a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{len(rows)} frames, {sum(len(r['mobs']) for r in rows)} mobs; {dropped} unsupported hit/die dropped")


if __name__ == "__main__":
    main()
