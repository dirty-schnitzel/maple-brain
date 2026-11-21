"""Prototype, speed-realistic: what a frame costs on a map with moving scenery once everything is being followed.

  FastMovers.step   every mover's place this frame: its speed's prediction +-R px, the share of N sample pixels
                    (opaque pixels of its picture) showing their own colour - all movers x candidates in ONE batch
  FastScene.expected (fastexp.py)   the expected picture with the movers at their places
  FastClouds.step   every followed cloud's place: prediction +-R px by the exact model on N sample pixels of its
                    picture - all clouds x candidates in one batch
  FastClouds.layer  the clouds as one layer (premultiplied colour P, alpha A) and the frame with them undone:
                    frame' = (frame - P) / (1 - A)
    python fastpipe.py CAP --clouds out/clouds_<tag>.json
Checks itself against the slow reference (proto.MScene.locate; the per-frame cloud detections) and prints ms."""
import argparse
import json
import math
import time

import numpy as np
import torch

import clouds as cl
import fastexp
import msl
import proto
from maplebrain.scene import HOFF

SW, PLAY_H = 1366, 700


class FastMovers:
    def __init__(self, ms, n=4000, r=3, seed=0):
        self.ms, self.dev, self.r = ms, ms.dev, r
        self.idx = sorted(ms.movers)
        g = torch.Generator().manual_seed(seed)
        px, py, col = [], [], []
        for i in self.idx:
            m = ms.movers[i]
            op = (m.pic[..., 3] == 255).cpu()
            yy, xx = op.nonzero(as_tuple=True)
            pick = torch.randperm(len(yy), generator=g)[:n]
            if len(pick) < n:
                pick = torch.cat([pick, pick[torch.randint(len(pick), (n - len(pick),), generator=g)]])
            px.append(xx[pick])
            py.append(yy[pick])
            col.append(m.pic[..., :3].cpu()[yy[pick], xx[pick]])
        self.px = torch.stack(px).to(self.dev)                        # (M, N)
        self.py = torch.stack(py).to(self.dev)
        self.col = torch.stack(col).to(self.dev).short()              # (M, N, 3)
        self.cx = torch.tensor([ms.movers[i].cx for i in self.idx], device=self.dev)
        self.v = torch.tensor([ms.movers[i].v for i in self.idx], device=self.dev, dtype=torch.float64)
        self.off = torch.arange(-r, r + 1, device=self.dev)
        self.X = torch.zeros(len(self.idx), dtype=torch.float64, device=self.dev)
        self.t = None
        self.tile_a = ms.scene.canvas[..., 3]                         # tiles / objects alpha (map canvas)

    def tops(self, C):
        out = []
        u = int(C[1]) + HOFF
        for i in self.idx:
            b = self.ms.movers[i].b
            out.append(b["y"] + HOFF + (1 if u >= 0 else -1) * math.floor(b["ry"] * abs(u) / 100) - b["origin"][1])
        return torch.tensor(out, device=self.dev)

    def step(self, f, C, t, tol=4):
        """-> (X (M,) the movers' places, share (M,), free samples (M,)). `f`: uint8 frame tensor."""
        sc = self.ms.scene
        pred = self.X + self.v * (t - self.t) if self.t is not None else self.X
        cand = pred.round().long()[:, None] + self.off[None, :]                       # (M, K)
        sx = (cand[:, :, None] - int(C[0]) + self.px[:, None, :]) % self.cx[:, None, None]   # (M, K, N)
        sy = (self.tops(C)[:, None] + self.py)[:, None, :].expand_as(sx)
        ok = (sx < SW) & (sy >= 0) & (sy < PLAY_H)
        sxc, syc = sx.clamp(max=SW - 1), sy.clamp(0, PLAY_H - 1)
        got = f[syc, sxc].short()                                                     # (M, K, N, 3)
        mx, my = sxc + int(C[0]) - sc.x0, syc + int(C[1]) - sc.y0
        inside = (mx >= 0) & (mx < self.tile_a.shape[1]) & (my >= 0) & (my < self.tile_a.shape[0])
        free = ok & ~(inside & (self.tile_a[my.clamp(0, self.tile_a.shape[0] - 1), mx.clamp(0, self.tile_a.shape[1] - 1)] > 0))
        hit = free & ((got - self.col[:, None]).abs().amax(dim=3) <= tol)
        n = free.sum(dim=2)
        share = hit.sum(dim=2).float() / n.clamp(min=1)
        hits = hit.sum(dim=2).float()
        best = hits.argmax(dim=1)
        ar = torch.arange(len(self.idx), device=self.dev)
        bs, bn, bh = share[ar, best], n[ar, best], hits[ar, best]
        # found = the best place stands out: the visible samples all show their colour there, a place next to it
        # only by chance (a layer mostly hidden behind later ones still has its visible part: the share is
        # diluted, the peak is not)
        rest = hits.clone()
        rest[ar, best] = -1
        second = rest.amax(dim=1)
        found = (bh >= 30) & (bh >= second + torch.maximum(torch.full_like(second, 15.0), 4 * second.clamp(min=0).sqrt()))
        newX = torch.where(found, cand[ar, best].double(), pred)
        self.X, self.t = newX % self.cx, t
        return self.X, bs, bn, found


class FastClouds:
    def __init__(self, cf: "cl.CloudFinder", n=1500, r=1, seed=0):
        self.cf, self.dev, self.r = cf, cf.dev, r
        g = torch.Generator().manual_seed(seed)
        px, py, aa, col = [], [], [], []
        for s, a in cf.sprites:
            yy, xx = (a.cpu() >= 0.2).nonzero(as_tuple=True)
            pick = torch.randperm(len(yy), generator=g)[:n]
            px.append(xx[pick]); py.append(yy[pick])
            aa.append(a.cpu()[yy[pick], xx[pick]]); col.append(s.cpu()[yy[pick], xx[pick]])
        self.px, self.py = torch.stack(px).to(self.dev), torch.stack(py).to(self.dev)        # (7, N)
        self.a, self.col = torch.stack(aa).to(self.dev), torch.stack(col).to(self.dev)        # (7, N), (7, N, 3)
        d = torch.arange(-r, r + 1, device=self.dev)
        self.dx, self.dy = [t.reshape(-1) for t in torch.meshgrid(d, d, indexing="xy")]        # (K,)

    def step(self, f, E, valid, k, x, y, o, tol=4):
        """Clouds (picture k, predicted top-left x, y on screen, opacity o: tensors (n,)) -> (x, y, share, n_inf)
        by the exact model on the sample pixels, every candidate in one batch. `E`: the expected picture WITHOUT
        clouds; `f` uint8."""
        sx = x[:, None, None] + self.dx[None, :, None] + self.px[k][:, None, :]              # (n, K, N)
        sy = y[:, None, None] + self.dy[None, :, None] + self.py[k][:, None, :]
        ok = (sx >= 0) & (sx < SW) & (sy >= 0) & (sy < PLAY_H)
        sxc, syc = sx.clamp(0, SW - 1), sy.clamp(0, PLAY_H - 1)
        Ff = f[syc, sxc].float()
        Ee = E[syc, sxc].float()
        ok &= valid[syc, sxc]
        q = (o[:, None, None] * self.a[k][:, None, :])[..., None] * (self.col[k][:, None] - Ee)
        inf = ok & (q.abs().amax(dim=3) > 2 * tol)
        hit = inf & ((Ff - Ee - q).abs().amax(dim=3) <= tol)
        n = inf.sum(dim=2)
        share = hit.sum(dim=2).float() / n.clamp(min=1)
        best = share.argmax(dim=1)
        ar = torch.arange(len(k), device=self.dev)
        return x + self.dx[best], y + self.dy[best], share[ar, best], n[ar, best]

    def layer(self, clouds):
        """[(k, x, y, o)] -> (P premultiplied colour (h, w, 3) half, A alpha (h, w) half) of the clouds as one layer."""
        P = torch.zeros((PLAY_H, SW, 3), dtype=torch.half, device=self.dev)
        A = torch.zeros((PLAY_H, SW, 1), dtype=torch.half, device=self.dev)
        for k, x, y, o in clouds:
            if not hasattr(self, "_half"):
                self._half = [(s.half(), a.half()[..., None]) for s, a in self.cf.sprites]
            s, a = self._half[k]
            h, w = a.shape[:2]
            x0, y0, x1, y1 = max(0, x), max(0, y), min(SW, x + w), min(PLAY_H, y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            aa = a[y0 - y:y1 - y, x0 - x:x1 - x] * o
            P[y0:y1, x0:x1].lerp_(s[y0 - y:y1 - y, x0 - x:x1 - x], aa)       # P = P (1 - a) + a s
            A[y0:y1, x0:x1].lerp_(torch.ones((), dtype=torch.half, device=self.dev), aa)
        return P, A

    def undo(self, f, P, A, amax=0.85):
        """The frame with the cloud layer undone (uint8) + the pixels a cloud leaves too little of (A > amax)."""
        und = ((f.half() - P) / (1 - A).clamp(min=0.05)).round_().clamp_(0, 255).to(torch.uint8)
        return torch.where(A > 0.004, und, f), A[..., 0] > amax


def main():
    import cam as camlib
    from maplebrain.perception import hud
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--clouds", default=None)
    a = ap.parse_args()
    msl.guard()
    c = msl.clip(a.cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(a.cap)["rows"] if r[3] is not None]
    ms = proto.MScene(c.map_id)
    fs = fastexp.FastScene(ms)
    fm = FastMovers(ms)
    cf = cl.CloudFinder(ms.dev)
    fc = FastClouds(cf)
    crow = {r["i"]: r for r in json.loads((msl.OUT / a.clouds).read_text())} if a.clouds else {}
    ui = None
    T = {k: [] for k in ("movers", "expected", "clouds", "layer", "undo", "upload")}
    agree, total, cl_same, cl_tot, lost_ref, nfound, coast_err = 0, 0, 0, 0, 0, 0, []
    sync = torch.cuda.synchronize
    first = True
    for r in cams:
        i = r[0]
        n, name, t = fr[i]
        img = c.read(name)
        if ui is None:
            m = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
            ui = torch.from_numpy(np.ascontiguousarray(m[:700])).to(ms.dev)
        C = (r[3], r[4])
        sync(); t0 = time.perf_counter()
        f = proto.frame_tensor(img, ms.dev)
        sync(); t1 = time.perf_counter()
        ms.locate(f, C, t)                                    # the slow reference
        if first:                                             # the fast one starts from the reference's places
            fm.X = torch.tensor([ms.movers[k].X or 0.0 for k in fm.idx], dtype=torch.float64, device=ms.dev)
            fm.t = t
            first = False
        sync(); t2 = time.perf_counter()
        X, share, nfree, found = fm.step(f, C, t)
        sync(); t3 = time.perf_counter()
        Xd = {k: float(X[j]) for j, k in enumerate(fm.idx)}
        E = fs.expected(C, Xd)
        sync(); t4 = time.perf_counter()
        for j, k in enumerate(fm.idx):
            mref = ms.movers[k]
            if mref.found:
                total += 1
                e = ((mref.X - float(X[j]) + mref.cx / 2) % mref.cx) - mref.cx / 2
                if bool(found[j]):
                    nfound += 1
                    agree += abs(e) < 0.5
                else:
                    coast_err.append(abs(e))
                    fm.X[j] = mref.X                          # (at 6 frames a second a blind layer would drift)
            elif bool(found[j]):
                lost_ref += 1
        T["upload"].append(1000 * (t1 - t0)); T["movers"].append(1000 * (t3 - t2)); T["expected"].append(1000 * (t4 - t3))
        dets = (crow.get(i) or {}).get("clouds", [])
        if dets:
            k = torch.tensor([d[0] for d in dets], device=ms.dev)
            x = torch.tensor([d[1] - C[0] for d in dets], device=ms.dev)
            y = torch.tensor([d[2] - C[1] for d in dets], device=ms.dev)
            o = torch.tensor([d[5] for d in dets], device=ms.dev)
            jit = torch.randint(-1, 2, (2, len(dets)), device=ms.dev)          # the prediction is off by up to 1 px
            valid = ui
            sync(); t5 = time.perf_counter()
            bx, by, sh, ninf = fc.step(f, E, valid, k, x + jit[0], y + jit[1], o)
            sync(); t6 = time.perf_counter()
            P, A = fc.layer([(int(k[j]), int(bx[j]), int(by[j]), float(o[j])) for j in range(len(dets))])
            sync(); t7 = time.perf_counter()
            f2, thick = fc.undo(f, P, A)
            sync(); t8 = time.perf_counter()
            T["clouds"].append(1000 * (t6 - t5)); T["layer"].append(1000 * (t7 - t6)); T["undo"].append(1000 * (t8 - t7))
            cl_tot += len(dets)
            cl_same += int(((bx == x) & (by == y)).sum())
    print(f"{a.cap}: {len(cams)} frames, map {c.map_id}: {len(fm.idx)} movers")
    ce = np.array(coast_err) if coast_err else np.zeros(1)
    print(f"  movers: of {total} mover-frames the reference found, the batched look found {nfound} "
          f"({100 * nfound / max(1, total):.1f} %), on the same pixel {agree} ({100 * agree / max(1, nfound):.2f} %); "
          f"where it did not stand out, its prediction was off by p50 {np.median(ce):.1f} / p90 {np.percentile(ce, 90):.1f} / max {ce.max():.1f} px; "
          f"found by the batched look only: {lost_ref}")
    if cl_tot:
        print(f"  clouds: the batched check puts {cl_same} of {cl_tot} clouds back on the detector's pixel "
              f"({100 * cl_same / cl_tot:.1f} %) from a prediction 0-1 px off")
    for k, v in T.items():
        if v:
            v = np.array(v[10:])
            print(f"  ms {k:9s} p50 {np.median(v):.2f}  p90 {np.percentile(v, 90):.2f}")
    tot = sum(np.median(np.array(v[10:])) for k, v in T.items() if v and k != "upload")
    print(f"  per frame, everything followed: {tot:.2f} ms (p50s summed) - against today's Scene.expected alone on this map")


if __name__ == "__main__":
    main()
