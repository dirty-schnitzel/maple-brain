"""Replay a recorded run's frames through DropSpotter. usage: replay_drops.py RUN OUT T0 T1 [every]"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from maplebot.perception.drops import DropSpotter

run, out = Path(sys.argv[1]), Path(sys.argv[2]); t0, t1 = float(sys.argv[3]), float(sys.argv[4])
every = int(sys.argv[5]) if len(sys.argv) > 5 else 4
out.mkdir(parents=True, exist_ok=True)
F = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
F = [k for k in F if k["frame"] and k["obs"]["me"] and t0 <= k["obs"]["t"] <= t1]
sp = DropSpotter(); rows, ms, n_rep = [], [], []
for i, k in enumerate(F):
    f = cv2.imread(str(run / "frames" / k["frame"])); px, feet = k["obs"]["me"]
    a = time.perf_counter(); rep = sp.update(f, k["obs"]["t"], feet, px); ms.append((time.perf_counter() - a) * 1000)
    n_rep.append(len(rep))
    if i % every == 0:
        feet = int(feet); v = f[feet - 90:feet + 30].copy()
        for (x, y, w, h), hits in rep:
            cv2.rectangle(v, (x, y - feet + 90), (x + w, y + h - feet + 90), (0, 0, 255), 1)
        cv2.putText(v, f"{k['obs']['t']:.1f} n={len(rep)}", (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        rows.append(v)
print(f"frames {len(F)}  ms median {np.median(ms):.1f} p95 {np.percentile(ms, 95):.1f}  drops/frame mean {np.mean(n_rep):.2f}")
for j in range(0, len(rows), 8):
    cv2.imwrite(str(out / f"{run.name}_{j:03d}.png"), np.vstack(rows[j:j + 8]))
