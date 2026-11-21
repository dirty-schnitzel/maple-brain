"""Prototype: a cheap expected picture for maps whose background layers cannot be pre-composed (movers between
static layers of different parallax: Perion 19 layers, 7 of them moving).

FastScene.expected(C, X) draws every background layer only where it is on screen: a slice of its picture (not
tiled), or one / two index_selects (tiled) -> ONE lerp into the picture's screen rectangle. Half floats, straight
colours. The result must equal proto.MScene.expected (checked by `python fastexp.py CAP`), and its ms are the
number the plan quotes."""
import math
import sys
import time

import numpy as np
import torch

import msl
import proto
from maplebrain.scene import H_TILED, HOFF, MOVING, V_TILED, WOFF

SW, PLAY_H = 1366, 700


class Layer:
    def __init__(self, i, b, t, dev, additive, mover):
        """`t`: the Scene's premultiplied float BGRA (alpha 0..255, the entry's `a` applied). A tiled layer's
        picture is padded / cut to its period once, so a copy is one index_select."""
        self.i, self.b, self.additive, self.mover = i, b, additive, mover
        a = (t[..., 3:4] / 255.0)
        col = torch.where(a > 0, t[..., :3] / a.clamp(min=1e-6), torch.zeros_like(t[..., :3]))
        if additive:
            col = t[..., :3]                                          # added as it is (premultiplied)
        ph, pw = t.shape[:2]
        self.cx = (b["cx"] or pw) if b["type"] in H_TILED else None
        self.cy = (b["cy"] or ph) if b["type"] in V_TILED else None
        H_, W_ = self.cy or ph, self.cx or pw
        if (H_, W_) != (ph, pw):
            pc = torch.zeros((H_, W_, 3), device=dev)
            pa = torch.zeros((H_, W_, 1), device=dev)
            pc[:min(H_, ph), :min(W_, pw)] = col[:min(H_, ph), :min(W_, pw)]
            pa[:min(H_, ph), :min(W_, pw)] = a[:min(H_, ph), :min(W_, pw)]
            col, a = pc, pa
        self.col = col.half().contiguous()                            # (H_, W_, 3) straight colour
        self.a = a.half().contiguous()                                # (H_, W_, 1)
        self.ph, self.pw = H_, W_
        self.opaque_full = bool((self.a > 0.999).all()) and self.cx is not None and self.cy is not None
        self.ox = b["size"][0] - b["origin"][0] if b.get("flip") else b["origin"][0]
        self.ar_x = torch.arange(SW, device=dev)
        self.ar_y = torch.arange(PLAY_H, device=dev)

    def place(self, C, X):
        """Screen (x, y) of the picture's top-left."""
        b = self.b
        if self.mover:
            u = int(C[1]) + HOFF
            sy = b["y"] + HOFF + (1 if u >= 0 else -1) * math.floor(b["ry"] * abs(u) / 100) - b["origin"][1]
            return int(round(X)) - int(C[0]), sy
        return (b["x"] + WOFF + int(b["rx"] * (int(C[0]) + WOFF) / 100) - self.ox,
                b["y"] + HOFF + int(b["ry"] * (int(C[1]) + HOFF) / 100) - b["origin"][1])

    def draw(self, out, C, X=None):
        sx, sy = self.place(C, X)
        col, a = self.col, self.a
        if self.cy is None:
            y0, y1 = max(0, sy), min(PLAY_H, sy + self.ph)
            if y1 <= y0:
                return 0
            col, a = col[y0 - sy:y1 - sy], a[y0 - sy:y1 - sy]
        else:
            y0, y1 = 0, PLAY_H
            idx = (self.ar_y - sy) % self.cy
            col, a = col.index_select(0, idx), a.index_select(0, idx)
        if self.cx is None:
            x0, x1 = max(0, sx), min(SW, sx + self.pw)
            if x1 <= x0:
                return 0
            col, a = col[:, x0 - sx:x1 - sx], a[:, x0 - sx:x1 - sx]
        else:
            x0, x1 = 0, SW
            idx = (self.ar_x - sx) % self.cx
            col, a = col.index_select(1, idx), a.index_select(1, idx)
        dst = out[y0:y1, x0:x1]
        if self.additive:
            dst.add_(col).clamp_(max=255)
        elif self.opaque_full:
            dst.copy_(col)
        else:
            dst.lerp_(col, a)
        return (y1 - y0) * (x1 - x0)


class FastScene:
    def __init__(self, ms: "proto.MScene"):
        self.ms, self.sc, self.dev = ms, ms.scene, ms.dev
        self.layers = [Layer(i, b, t, self.dev, i in ms.additive, i in ms.movers) for i, (b, t) in enumerate(self.sc.backs)]
        cv = self.sc.canvas                                            # premultiplied uint8 BGRA
        self.canvas = cv

    def expected(self, C, X: dict):
        """-> bgr half (PLAY_H, SW, 3). `X`: mover index -> its place on the map (None: left out)."""
        out = torch.zeros((PLAY_H, SW, 3), dtype=torch.half, device=self.dev)
        area = 0
        for L in self.layers:
            if L.b["front"]:
                continue
            if L.mover and X.get(L.i) is None:
                continue
            area += L.draw(out, C, X.get(L.i))
        sc = self.sc._crop(C, SW, PLAY_H)                              # tiles / objects (premultiplied uint8)
        scf = sc.half()
        out.mul_(1 - scf[..., 3:4] / 255.0).add_(scf[..., :3])
        for L in self.layers:
            if L.b["front"]:
                area += L.draw(out, C, X.get(L.i))
        self.area = area
        return out


if __name__ == "__main__":
    import cam as camlib
    cap = sys.argv[1]
    msl.guard()
    c = msl.clip(cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(cap)["rows"] if r[3] is not None]
    ms = proto.MScene(c.map_id)
    fs = FastScene(ms)
    n_layers = len(ms.scene.backs)
    # find the movers on a few frames, then compare the two pictures and time both
    step = max(1, len(cams) // 60)
    worst, t_fast, t_ref, t_old, areas = 0.0, [], [], [], []
    for r in cams[::step]:
        i = r[0]
        img = c.read(fr[i][1])
        f = proto.frame_tensor(img, ms.dev)
        C = (r[3], r[4])
        ms.locate(f, C, fr[i][2])
        X = {k: m.X for k, m in ms.movers.items()}
        torch.cuda.synchronize()
        a = time.perf_counter()
        e_ref, known = ms.expected(C)
        torch.cuda.synchronize()
        b = time.perf_counter()
        e_fast = fs.expected(C, X)
        torch.cuda.synchronize()
        d = time.perf_counter()
        e_old, k_old = ms.scene.expected(C)
        torch.cuda.synchronize()
        e = time.perf_counter()
        t_ref.append(1000 * (b - a)); t_fast.append(1000 * (d - b)); t_old.append(1000 * (e - d)); areas.append(fs.area / (SW * PLAY_H))
        diff = (e_fast.float() - e_ref).abs().amax(dim=2)
        worst = max(worst, float(diff[known].max()) if bool(known.any()) else 0.0)
    print(f"{cap}: map {c.map_id}, {n_layers} background layers ({len(ms.movers)} movers, {len(ms.additive)} additive); "
          f"{len(t_fast)} frames")
    print(f"  fast vs reference, worst difference on known pixels: {worst:.2f} levels")
    print(f"  ms p50 / p90: fast {np.median(t_fast[5:]):.2f} / {np.percentile(t_fast[5:], 90):.2f};  layer-by-layer reference "
          f"{np.median(t_ref[5:]):.2f} / {np.percentile(t_ref[5:], 90):.2f};  today's Scene.expected (movers left unknown) "
          f"{np.median(t_old[5:]):.2f} / {np.percentile(t_old[5:], 90):.2f};  drawn area {np.median(areas):.1f} screens")
