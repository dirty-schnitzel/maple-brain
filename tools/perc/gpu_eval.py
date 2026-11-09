"""GPU full-screen detector vs the reference (truth.jsonl) and vs what the live bot saw (ticks.jsonl).

  python tools/perc/gpu_eval.py RUN MAP [--truth truth.jsonl] [--draw OUTDIR N...]
Matching: same mob id, feet within 20 px (x) / 20 px (y).
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebrain.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402


def same(a_id, a_feet, b_id, b_feet, tol=20):
    return a_id == b_id and abs(a_feet[0] - b_feet[0]) <= tol and abs(a_feet[1] - b_feet[1]) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("map", type=int)
    ap.add_argument("--truth", default="truth.jsonl")
    ap.add_argument("--min", type=float, default=0.65)
    ap.add_argument("--draw", nargs="*", default=None, help="OUTDIR then tick numbers")
    a = ap.parse_args()
    run = Path(a.run)
    det = GpuSpriteDetector.for_map(a.map, ROOT / "assets/mcw", min_score=a.min)
    print(f"device {det.dev}, {det.K} templates: {det.names}")
    truth = [json.loads(l) for l in open(run / a.truth, encoding="utf-8")]
    ticks = {json.loads(l)["n"]: json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")}
    tp = fn = fp = 0
    live_tp = live_fn = 0
    miss_by, hit_by, near_miss = Counter(), Counter(), Counter()
    extra, times = [], []
    draw = set(int(x) for x in a.draw[1:]) if a.draw else set()
    for row in truth:
        frame = cv2.imread(str(run / "frames" / row["frame"]))
        t0 = time.perf_counter()
        hits = det.find(frame)
        times.append((time.perf_counter() - t0) * 1000)
        live = ticks[row["n"]]["obs"].get("sprite_mobs") or []
        me = row.get("me")
        for m in row["mobs"]:
            key = m["anim"] if m["anim"] in ("stand", "move") else m["anim"] + " (not searched)"
            if any(same(h.mob_id, h.feet, m["id"], m["feet"]) for h in hits):
                tp += 1
                hit_by[key] += 1
            else:
                fn += 1
                miss_by[key] += 1
            if me and abs(m["feet"][0] - me[0]) < 100 and m["anim"] in ("stand", "move"):
                near_miss["near: total"] += 1
                if not any(same(h.mob_id, h.feet, m["id"], m["feet"]) for h in hits):
                    near_miss["near: gpu missed"] += 1
            if m["anim"] in ("stand", "move"):            # what the live CPU detector found of the same mobs
                b = [s[0] for s in live]
                if any(abs(x[0] + x[2] / 2 - (m["box"][0] + m["box"][2] / 2)) < 20 and
                       abs(x[1] + x[3] - m["feet"][1]) < 25 for x in b):
                    live_tp += 1
                else:
                    live_fn += 1
        for h in hits:
            if not any(same(h.mob_id, h.feet, m["id"], m["feet"]) for m in row["mobs"]):
                fp += 1
                extra.append((row["n"], det.names[h.mob_id], h.pose.anim, h.feet, h.score))
        if row["n"] in draw:
            im = frame.copy()
            for m in row["mobs"]:
                x, y, w, h = m["box"]
                cv2.rectangle(im, (x - 3, y - 3), (x + w + 3, y + h + 3), (0, 255, 0), 1)
            for h in hits:
                x, y, w, hh = h.box
                cv2.rectangle(im, (x, y), (x + w, y + hh), (0, 0, 255), 2)
                cv2.circle(im, tuple(map(int, h.feet)), 4, (0, 0, 255), -1)
                cv2.putText(im, f"{det.names[h.mob_id]} {h.pose.anim}{h.pose.n}{h.pose.facing[0]} {h.score:.2f}",
                            (x, y - 5), 0, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
            cv2.imwrite(str(Path(a.draw[0]) / f"gpu_{row['n']}.jpg"), im)
    times.sort()
    n_live = sum(v for k, v in hit_by.items() if "not" not in k) + sum(v for k, v in miss_by.items() if "not" not in k)
    found_live = sum(v for k, v in hit_by.items() if "not" not in k)
    print(f"{len(truth)} frames; find() median {times[len(times) // 2]:.1f} ms, p90 {times[int(len(times) * .9)]:.1f}"
          f" (first call {times[-1]:.0f} incl. warm-up)")
    print(f"reference stand/move mobs: GPU found {found_live}/{n_live}; live CPU bot had {live_tp}/{live_tp + live_fn}")
    print("found by pose:", dict(hit_by), " missed:", dict(miss_by))
    print("within 100 px of us:", dict(near_miss))
    print(f"GPU detections not in the reference: {fp}")
    for e in extra[:15]:
        print("  ", e)


if __name__ == "__main__":
    main()
