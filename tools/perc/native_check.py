"""Is the captured picture 1:1 with the client's sprites? (PLAN-perception.md step 0, the native 1366x768 window.)

    python tools/perc/native_check.py RUN [--map ID] [--n 300] [--score 0.9] [--sheet 24]

On `--n` saved frames of RUN (evenly spread; record with --frames-png: JPEG alone moves ~4 of 5 sprite pixels by
more than 4 levels): the GPU detector's CLEAR mobs = live poses with score >= --score, whole body in the play area,
no other hit, name tag or HUD part within 12 px. Each is compared pixel by pixel with its client sprite frame at the
detector's position (and +-1 px around it; the closest picture counts): the share of the sprite's opaque pixels whose worst
channel is within +-4 / +-8 / +-16 levels of the frame.
GATE (plan): pooled share within +-4 >= 95 %  ->  "1:1"; else the picture stays "resampled" (wider tolerances).
Also printed: inner pixels only (the mask eroded 1 px: edges apart), the colour shift (median frame - sprite per
channel), how often the best position was not the detector's, per mob type. `--sheet N` writes RUN/native_check.png:
the N worst and N best mobs as frame | sprite | difference x8.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TOLS = (4, 8, 16)


def measure(frame: np.ndarray, sprite: np.ndarray, mask: np.ndarray, x: int, y: int, reach: int = 1) -> dict | None:
    """`sprite` (BGR) with its opaque `mask` drawn at (x, y) of `frame`? The best of the positions within `reach`
    px: {"dx", "dy", "n", "in": {tol: share}, "inner": {tol: share}, "shift": median (frame - sprite) per channel}."""
    h, w = sprite.shape[:2]
    inner = cv2.erode(mask, np.ones((3, 3), np.uint8)).astype(bool)
    m = mask.astype(bool)
    best = None
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            x0, y0 = x + dx, y + dy
            if x0 < 0 or y0 < 0 or x0 + w > frame.shape[1] or y0 + h > frame.shape[0]:
                continue
            d = frame[y0:y0 + h, x0:x0 + w].astype(np.int16) - sprite.astype(np.int16)
            worst = np.abs(d).max(axis=2)
            key = (-float(worst[m].mean()), -(abs(dx) + abs(dy)))      # the closest picture (not the +-4 share:
                                                                       # a uniform brightness shift would pick noise)
            if best is None or key > best[0]:
                best = (key, dx, dy, worst, d)
    if best is None:
        return None
    _, dx, dy, worst, d = best
    return {"dx": dx, "dy": dy, "n": int(m.sum()), "n_inner": int(inner.sum()),
            "in": {t: float((worst[m] <= t).mean()) for t in TOLS},
            "inner": {t: float((worst[inner] <= t).mean()) if inner.any() else 0.0 for t in TOLS},
            "shift": [float(np.median(d[..., c][m])) for c in range(3)], "worst": worst}


def _apart(box, other, pad=12) -> bool:
    return (box[0] - pad >= other[0] + other[2] or other[0] - pad >= box[0] + box[2]
            or box[1] - pad >= other[1] + other[3] or other[1] - pad >= box[1] + box[3])


def clear_hits(hits: list, tags: list, score: float, play_h: int, width: int) -> list:
    from maplebrain.perception import hud
    from maplebrain.perception.tags import tag_body
    ui = [(a, b, c - a, d - b) for a, b, c, d in hud.UI_RECTS]
    bodies = [tag_body(t) for t in tags]
    out = []
    for h in hits:
        x, y, w, hh = h.box
        if h.score < score or x < 0 or y < 0 or x + w > width or y + hh > play_h:
            continue
        if all(_apart(h.box, o.box) for o in hits if o is not h) and all(_apart(h.box, b) for b in bodies + ui):
            out.append(h)
    return out


def pooled(rows: list, key: str, tol: int) -> float:
    n = "n" if key == "in" else "n_inner"
    return sum(r[key][tol] * r[n] for r in rows) / max(1, sum(r[n] for r in rows))


def report(rows: list, frames: int, names: dict) -> str:
    if not rows:
        return f"{frames} frames: no clear mob found"
    L = [f"{frames} frames, {len(rows)} clear mobs, {sum(r['n'] for r in rows)} sprite pixels"]
    for key, what in (("in", "all opaque pixels"), ("inner", "inner pixels (edge 1 px off)")):
        L.append(f"  {what:30s} within " + ", ".join(f"+-{t}: {100 * pooled(rows, key, t):.1f} %" for t in TOLS))
    per = sorted(r["in"][TOLS[0]] for r in rows)
    L.append(f"  per mob, within +-{TOLS[0]}: median {100 * per[len(per) // 2]:.1f} %, p10 {100 * per[len(per) // 10]:.1f} %, "
             f"mobs >= 95 %: {100 * sum(v >= 0.95 for v in per) / len(per):.1f} %")
    sh = np.median(np.array([r["shift"] for r in rows]), axis=0)
    moved = sum(1 for r in rows if (r["dx"], r["dy"]) != (0, 0))
    L.append(f"  colour shift frame - sprite (B, G, R): {sh[0]:+.0f}, {sh[1]:+.0f}, {sh[2]:+.0f}; best position off the "
             f"detector's by 1 px: {moved} of {len(rows)}; detector score median {np.median([r['score'] for r in rows]):.3f}")
    for mob in sorted({r["mob"] for r in rows}):
        g = [r for r in rows if r["mob"] == mob]
        L.append(f"  {names.get(mob, mob)} ({len(g)}): within +-{TOLS[0]} {100 * pooled(g, 'in', TOLS[0]):.1f} %, "
                 f"+-{TOLS[2]} {100 * pooled(g, 'in', TOLS[2]):.1f} %")
    gate = pooled(rows, "in", TOLS[0])
    L.append(f"GATE within +-{TOLS[0]} >= 95 %: {100 * gate:.1f} % -> {'1:1 (PASS)' if gate >= 0.95 else 'NOT 1:1'}")
    return "\n".join(L)


def sheet(rows: list, n: int, path: Path) -> None:
    rows = sorted(rows, key=lambda r: r["in"][TOLS[0]])
    pick = rows[:n] + rows[-n:] if len(rows) > 2 * n else rows
    tiles = []
    for r in pick:
        diff = cv2.cvtColor(np.clip(r["worst"].astype(np.int32) * 8, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        t = np.hstack([r["crop"], r["sprite"], diff])
        t = cv2.resize(t, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        t = cv2.copyMakeBorder(t, 14, 2, 2, 2, cv2.BORDER_CONSTANT, value=(40, 40, 40))
        cv2.putText(t, f"{100 * r['in'][TOLS[0]]:.0f}% {r['frame'][:6]}", (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                    (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(t)
    hmax, wmax = max(t.shape[0] for t in tiles), max(t.shape[1] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, hmax - t.shape[0], 0, wmax - t.shape[1], cv2.BORDER_CONSTANT) for t in tiles]
    per_row = 6
    while len(tiles) % per_row:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(str(path), np.vstack([np.hstack(tiles[i:i + per_row]) for i in range(0, len(tiles), per_row)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--map", type=int, default=None)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--score", type=float, default=0.9)
    ap.add_argument("--sheet", type=int, default=0)
    a = ap.parse_args()
    from maplebrain.perception.gpu_sprites import PLAY_H, GpuSpriteDetector
    from maplebrain.perception.tags import find_tags
    map_id = a.map
    if map_id is None:
        log = (a.run / "log.txt").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"map recognised: (\d+)", log) or re.search(r"\bmap (\d+) ", log)
        if not m:
            raise SystemExit("no map in the run's log: --map ID")
        map_id = int(m.group(1))
    files = sorted(p for p in (a.run / "frames").iterdir() if p.suffix in (".png", ".jpg"))
    if not files:
        raise SystemExit(f"no frames in {a.run}")
    files = [files[int(i * (len(files) - 1) / max(1, a.n - 1))] for i in range(min(a.n, len(files)))]
    kinds = {p.suffix for p in files}
    det = GpuSpriteDetector.for_map(map_id, ROOT / "assets" / "mcw", min_score=0.5)
    items = {(mid, pose): (t, m) for mid, t, m, pose in det.items}
    rows = []
    for p in files:
        frame = cv2.imread(str(p))
        if frame is None:
            continue
        for h in clear_hits(det.find(frame), find_tags(frame), a.score, PLAY_H, frame.shape[1]):
            t, m = items[(h.mob_id, h.pose)]
            r = measure(frame, t, m, h.box[0], h.box[1])
            if r is None:
                continue
            x, y = h.box[0] + r["dx"], h.box[1] + r["dy"]
            r.update(mob=h.mob_id, score=h.score, frame=p.name, sprite=t, crop=frame[y:y + t.shape[0], x:x + t.shape[1]])
            rows.append(r)
    print(f"{a.run}: map {map_id}, frames {'/'.join(sorted(kinds))}, size {frame.shape[1]}x{frame.shape[0]}"
          + ("   (JPEG frames: the +-4 share is NOT meaningful, see the docstring)" if ".jpg" in kinds else ""))
    print(report(rows, len(files), det.names))
    if a.sheet and rows:
        sheet(rows, a.sheet, a.run / "native_check.png")
        print(f"sheet: {a.run / 'native_check.png'}")
    (a.run / "native_check.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k not in ("worst", "sprite", "crop")} for r in rows]))


if __name__ == "__main__":
    main()
