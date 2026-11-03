"""Experiment 2: can motion / background subtraction find mobs in idle frames?

For each frame (after the first few) compares two detectors:
  A. frame differencing: frame i vs frame i-k, camera shift cancelled by phase correlation
  B. median background: frame i vs the per-pixel median of all frames
Filters: HUD/minimap/chat masked out, blob size limits, damage-number colours dropped,
persistence (blob must overlap a blob in the previous diff).
Writes overlay images (A = red boxes, B = green boxes) and prints counts.

Usage: python -I motion_experiment.py <run_dir> [--k 3]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

# Screen regions (1366x768 space) that are UI, not world: minimap, quest helper, chat, quickslots, status bar
UI_MASKS = [(0, 0, 215, 195), (1140, 45, 1366, 160), (285, 630, 850, 768), (930, 620, 1085, 705),
            (285, 700, 1366, 768)]


def ui_mask(shape):
    m = np.ones(shape[:2], np.uint8)
    for x0, y0, x1, y1 in UI_MASKS:
        m[y0:y1, x0:x1] = 0
    return m


def gray(f):
    return cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)


def aligned_diff(a, b):
    """|b - a| after shifting a by the camera motion measured between them."""
    ga, gb = gray(a), gray(b)
    (dx, dy), resp = cv2.phaseCorrelate(ga, gb)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    ga = cv2.warpAffine(ga, M, (ga.shape[1], ga.shape[0]), borderMode=cv2.BORDER_REPLICATE)
    return np.abs(gb - ga), (dx, dy, resp)


def blobs(diff, mask, thresh=25, min_area=60, max_w=160, max_h=140):
    on = ((diff > thresh) & (mask > 0)).astype(np.uint8)
    on = cv2.morphologyEx(on, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    on = cv2.morphologyEx(on, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(on)
    out = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in st[i])
        if area >= min_area and 8 <= w <= max_w and 8 <= h <= max_h:
            out.append((x, y, w, h))
    return out


def overlaps(a, b, pad=6):
    return not (a[0] + a[2] + pad < b[0] or b[0] + b[2] + pad < a[0] or
                a[1] + a[3] + pad < b[1] or b[1] + b[3] + pad < a[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--k", type=int, default=3, help="frame gap for differencing")
    a = ap.parse_args()
    run = Path(a.run)
    meta = json.loads((run / "meta.json").read_text())
    names = [f["file"] for f in meta["frames"] if f["phase"].startswith("idle")]
    frames = [cv2.imread(str(run / n)) for n in names]
    print(f"{len(frames)} idle frames")
    mask = ui_mask(frames[0].shape)
    median = np.median(np.stack(frames), axis=0).astype(np.uint8)
    cv2.imwrite(str(run / "median_background.png"), median)
    out_dir = run / "analysis"
    out_dir.mkdir(exist_ok=True)

    prev_a = []
    for i in range(a.k, len(frames)):
        d_a, (dx, dy, resp) = aligned_diff(frames[i - a.k], frames[i])
        found_a = blobs(d_a, mask)
        persistent_a = [b for b in found_a if any(overlaps(b, p) for p in prev_a)]
        prev_a = found_a
        d_b, _ = aligned_diff(median, frames[i])
        found_b = blobs(d_b, mask)
        if i in (a.k + 1, len(frames) // 2, len(frames) - 1):
            vis = frames[i].copy()
            for x, y, w, h in persistent_a:
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
            for x, y, w, h in found_b:
                cv2.rectangle(vis, (x - 3, y - 3), (x + w + 3, y + h + 3), (0, 255, 0), 1)
            cv2.imwrite(str(out_dir / f"overlay_{i:03d}.png"), vis)
            heat = cv2.applyColorMap(np.clip(d_a * 4, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
            cv2.imwrite(str(out_dir / f"diff_{i:03d}.png"), heat)
        print(f"frame {i:02d}: camera shift ({dx:+.1f},{dy:+.1f}) resp {resp:.2f} | "
              f"A diff: {len(found_a)} blobs, {len(persistent_a)} persistent {persistent_a[:6]} | "
              f"B median: {len(found_b)} {found_b[:6]}")


if __name__ == "__main__":
    main()
