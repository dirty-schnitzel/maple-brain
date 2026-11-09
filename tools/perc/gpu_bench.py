"""Benchmark: masked NCC of every stand/move/fly frame (both facings) of a map's mobs, on the GPU (torch) and the
CPU (OpenCV), over (a) the whole play area, (b) strips just above every platform, (c) strips above spawn platforms
only, within each spawn's walking range. Also checks the GPU scores equal OpenCV's.

  python tools/perc/gpu_bench.py RUN MAP TICK
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebrain.nav.navmap import NavMap  # noqa: E402

LIVE = ("stand", "move", "fly")
HALF = "--fp32" not in sys.argv


def templates(map_id, scale):
    mj = json.loads((ROOT / f"assets/mcw/maps/{map_id}/map.json").read_text(encoding="utf-8"))
    out, maxh = [], 0
    for mid in sorted({int(s["id"]) for s in mj["mobs"]}):
        d = ROOT / f"assets/mcw/mobs/{mid}"
        info = json.loads((d / "mob.json").read_text(encoding="utf-8"))
        for anim in LIVE:
            for f in info["frames"].get(anim, []):
                im = cv2.imread(str(d / f["file"]), cv2.IMREAD_UNCHANGED)
                if im is None or im.shape[0] < 4 or im.shape[1] < 4:
                    continue                                  # 1x1 placeholders
                for t in (im, im[:, ::-1]):
                    t = np.ascontiguousarray(t)
                    if scale != 1:
                        t = cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                    out.append((t[..., :3].copy(), (t[..., 3] > 160).astype(np.uint8), mid))
                    maxh = max(maxh, t.shape[0])
    return out, maxh


class GpuNCC:
    """All templates padded to one size; 3 convolutions give OpenCV's TM_CCOEFF_NORMED with a mask."""

    def __init__(self, tpls, dev="cuda", half=True):
        self.dev, self.dt = dev, (torch.float16 if half else torch.float32)
        H = max(t.shape[0] for t, _, _ in tpls)
        W = max(t.shape[1] for t, _, _ in tpls)
        K = len(tpls)
        T = np.zeros((K, 3, H, W), np.float32)
        M = np.zeros((K, 1, H, W), np.float32)
        for k, (t, m, _) in enumerate(tpls):
            h, w = m.shape
            tt = t.astype(np.float32).transpose(2, 0, 1) / 255
            mm = m.astype(np.float32)
            n = mm.sum()
            mean = (tt * mm).sum(axis=(1, 2), keepdims=True) / n
            T[k, :, :h, :w] = (tt - mean) * mm
            M[k, 0, :h, :w] = mm
        self.n = torch.tensor(M.sum(axis=(1, 2, 3)), device=dev).view(1, K, 1, 1)
        self.tnorm = torch.tensor((T ** 2).sum(axis=(1, 2, 3)), device=dev).view(1, K, 1, 1)
        self.T = torch.tensor(T, device=dev, dtype=self.dt)
        self.M = torch.tensor(M, device=dev, dtype=torch.float32)   # sums in fp32: var = s2 - s1^2/n cancels
        self.H, self.W, self.K = H, W, K

    def __call__(self, img_u8: np.ndarray) -> torch.Tensor:
        """(K, h-H+1, w-W+1) scores for one BGR image (positions where the padded template fits)."""
        x = torch.from_numpy(img_u8).to(self.dev, non_blocking=True)
        x = x.permute(2, 0, 1).unsqueeze(0).to(self.dt) / 255           # (1,3,h,w)
        cross = F.conv2d(x, self.T)                                     # (1,K,..)
        xc = x.float().transpose(0, 1)                                  # (3,1,h,w): per channel, fp32
        xc = xc - xc.mean()                                             # centred: less cancellation
        s1 = F.conv2d(xc, self.M)                                       # (3,K,..)
        s2 = F.conv2d(xc * xc, self.M)
        var = (s2 - s1 * s1 / self.n).sum(0, keepdim=True)
        return (cross.float() / torch.sqrt(var.clamp_min(1e-6) * self.tnorm))[0]


def strips(nav, ox, oy, shape, maxh, spawn_only, rx=None):
    """Screen rectangles just above each platform's surface (follows slopes segment by segment)."""
    H, W = shape[:2]
    rects = []
    spawns = [(s["x"], s.get("cy", s["y"]), s.get("rx0", s["x"] - 200), s.get("rx1", s["x"] + 200))
              for s in rx] if rx else []
    for p in nav.platforms.values():
        ranges = [(p.left, p.right)]
        if spawn_only:
            ranges = [(max(p.left, a), min(p.right, b)) for x, y, a, b in spawns
                      if p.left - 5 <= x <= p.right + 5 and abs((p.y_at(p.clamp(x)) or 1e9) - y) < 12]
        for lo, hi in ranges:
            for s in p.segs:
                a, b = max(s.x1, lo), min(s.x2, hi)
                if a >= b:
                    continue
                ya, yb = s.y_at(a) - oy, s.y_at(b) - oy
                x0, x1 = int(a - ox - 40), int(b - ox + 40)
                y0, y1 = int(min(ya, yb) - maxh - 50), int(max(ya, yb) + 12)   # +50: jumping mobs
                x0, x1, y0, y1 = max(0, x0), min(W, x1), max(0, y0), min(700, y1)
                if x1 - x0 > 8 and y1 - y0 > 8:
                    rects.append((x0, y0, x1, y1))
    rects.sort()
    merged = []                                       # merge overlapping rectangles
    for r in rects:
        for i, m in enumerate(merged):
            if r[0] <= m[2] and r[2] >= m[0] and abs(r[1] - m[1]) < 20 and abs(r[3] - m[3]) < 20:
                merged[i] = (min(m[0], r[0]), min(m[1], r[1]), max(m[2], r[2]), max(m[3], r[3]))
                break
        else:
            merged.append(r)
    return merged


def timeit(fn, reps=30):
    fn()
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / reps * 1000


def main():
    run, map_id, n = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    tick = next(json.loads(l) for l in open(run / "ticks.jsonl") if json.loads(l)["n"] == n)
    frame = cv2.imread(str(run / "frames" / tick["frame"]))
    o = tick["obs"]
    nav = NavMap.for_map(map_id, ROOT / "assets/mcw")
    mj = json.loads((ROOT / f"assets/mcw/maps/{map_id}/map.json").read_text(encoding="utf-8"))
    (sx, sf), (mx, my) = o["me"], o["map_pos"]
    p = nav.platforms.get(o["platform"])
    my = p.y_at(mx) if p and p.y_at(mx) is not None else my
    ox, oy = mx - sx, my - sf
    torch.backends.cudnn.benchmark = True
    print(torch.cuda.get_device_name(0))
    for scale in (1.0, 0.5):
        tp, maxh = templates(map_id, scale)
        print(f"\n== scale {scale}: {len(tp)} templates (stand/move/fly x 2 facings), tallest {maxh} px")
        g = GpuNCC(tp, half=HALF)
        img = frame[:700] if scale == 1 else cv2.resize(frame[:700], None, fx=scale, fy=scale,
                                                        interpolation=cv2.INTER_AREA)
        all_r = strips(nav, ox, oy, frame.shape, maxh / scale, False)
        sp_r = strips(nav, ox, oy, frame.shape, maxh / scale, True, [m for m in mj["mobs"] if not m.get("hide")])
        sc = lambda rs: [tuple(int(v * scale) for v in r) for r in rs]       # noqa: E731
        area = lambda rs: sum((r[2] - r[0]) * (r[3] - r[1]) for r in rs)    # noqa: E731
        print(f"areas: whole {img.shape[1] * img.shape[0]} px, platform strips {area(sc(all_r))} "
              f"({len(all_r)} rects), spawn strips {area(sc(sp_r))} ({len(sp_r)} rects)")

        def run_rects(rs):
            out = []
            for x0, y0, x1, y1 in rs:
                sub = img[y0:y1, x0:x1]
                if sub.shape[0] >= g.H and sub.shape[1] >= g.W:
                    out.append(g(np.ascontiguousarray(sub)))
            return out
        for name, rs in (("whole", None), ("platform strips", sc(all_r)), ("spawn strips", sc(sp_r))):
            f = (lambda: g(img)) if rs is None else (lambda rs=rs: run_rects(rs))
            gms = timeit(f)
            # CPU OpenCV on the same area
            t0 = time.perf_counter()
            for t, m, _ in tp:
                for x0, y0, x1, y1 in (rs or [(0, 0, img.shape[1], img.shape[0])]):
                    sub = img[y0:y1, x0:x1]
                    if sub.shape[0] >= t.shape[0] and sub.shape[1] >= t.shape[1]:
                        cv2.matchTemplate(sub, t, cv2.TM_CCOEFF_NORMED, mask=m)
            cms = (time.perf_counter() - t0) * 1000
            print(f"  {name:16s} GPU {gms:6.1f} ms   CPU (OpenCV, 1 thread-ish) {cms:7.0f} ms")
        # correctness: GPU vs OpenCV on template 0 over the whole image
        t, m, _ = tp[0]
        ref = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED, mask=m)
        ref[~np.isfinite(ref)] = -1
        got = g(img)[0].cpu().numpy()
        hh, ww = min(ref.shape[0], got.shape[0]), min(ref.shape[1], got.shape[1])
        a, b = ref[:hh, :ww], got[:hh, :ww]
        print(f"  check vs OpenCV (template 0): best at {np.unravel_index(a.argmax(), a.shape)} "
              f"{a.max():.3f} / GPU {np.unravel_index(b.argmax(), b.shape)} {b.max():.3f}")


if __name__ == "__main__":
    main()
