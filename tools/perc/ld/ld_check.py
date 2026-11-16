"""The GPU Lie Detector look vs cv2 on the CPU (PLAN-perception.md step 2.8): every saved Lie Detector frame
(runs/*/lie*.png, FHD ones resized as capture.normalize does) + every n-th native PNG frame of the 2026-11-16
recordings. Prints the largest score difference, the places that differ on matches >= the bar, and the time per look.
2026-11-16, the 4 templates of that day: max difference 1.7e-05 (2.5e-06 on matches >= 0.75), places all the same;
GPU 3.5 ms p50 vs CPU 89 ms.

    python tools/perc/ld/ld_check.py [--step 25]
"""
import argparse
import glob
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=25, help="every n-th native frame")
    a = ap.parse_args()
    import torch
    from maplebrain.perception.liedetector import GpuLieLook, LieDetector
    from maplebrain.runtime.runner import ASSETS
    lie = LieDetector.load(ASSETS, background=False)
    look = GpuLieLook(lie.templates, torch.device("cuda"))
    pos = sorted(glob.glob(str(ROOT / "runs" / "*" / "lie*.png")))
    neg = sorted(glob.glob(str(ROOT / "runs" / "play" / "20261116_*" / "frames" / "*.png")))[::a.step]
    worst, worst_hit, moved, n = 0.0, 0.0, 0, 0
    for p in pos + neg:
        img = cv2.imread(p)
        if img.shape[:2] != (768, 1366):
            img = cv2.resize(img, (1366, 768), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gpu = {j: (s, loc) for s, loc, j in look.looks(torch.from_numpy(img).cuda())}
        for j, t in enumerate(lie.templates):
            _, s, _, loc = cv2.minMaxLoc(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED))
            d = abs(s - gpu[j][0])
            worst = max(worst, d)
            if s >= lie.min_score:
                worst_hit = max(worst_hit, d)
                moved += gpu[j][1] != loc
        n += 1
    print(f"{len(pos)} Lie Detector frames + {len(neg)} native frames: max |cpu - gpu| {worst:.1e}, "
          f"on matches >= {lie.min_score} {worst_hit:.1e}, places differ {moved}")
    img = cv2.imread(neg[0])
    u8, gray = torch.from_numpy(img).cuda(), cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    for name, fn, k in (("gpu", lambda: look.look(u8), 100), ("cpu", lambda: lie.score(gray), 20)):
        ts = []
        for _ in range(k + 3):
            t0 = time.perf_counter()
            fn()
            ts.append(1000 * (time.perf_counter() - t0))
        ts = sorted(ts[3:])
        print(f"{name}: {np.median(ts):.2f} ms p50, p90 {ts[int(0.9 * (len(ts) - 1))]:.2f}")


if __name__ == "__main__":
    main()
