"""The weather clouds of a map whose info says `cloud` (Perion's region): followed frame by frame, like mobs with a
known picture (PLAN-moving-scenery.md design 3; step 4: in shadow - the frame is not undone yet, the maps are not
hunted). Ported from the prototype tools/perc/scenery/cloudtrack.py (CloudTracker, CoarseFinder) + fastpipe.py
(FastClouds) + clouds.py (CloudFinder.alpha_hat), the reference.

What a cloud is (measurement 4, re-measured at 60 a second in step 4): one of the client's 7 pictures
(assets/scene/clouds/<k>.png: near-white colour s, alpha a), blended over everything under the UI at its own constant
opacity o, at whole pixels, drifting at a constant speed on the MAP:
    frame = E + o a (s - E)          E = the expected picture without clouds (Scene.expected)
Per frame (`update`):
 1. every followed cloud that should be on screen: its place = its last fix + its speed x dt, checked +-cloud_near px
    by the exact blend on its sample pixels (alpha >= 0.2), all clouds x places in one batch; confirmed -> a fix (the
    speed = the line from its first fix); not confirmed -> it coasts (over near-white scenery or the UI a cloud cannot
    be checked) and is dropped only when the frame shows the scene where it should be (`cloud_gone`);
 2. the clouds as one layer: P (premultiplied colour) and A (alpha) -> the expected picture with clouds
    E2 = E (1 - A) + P;
 3. NEW clouds only while the frame is still whitened where no followed cloud explains it (the thickness a^ the
    frame implies, `cloud_whitened_px`), at most every `cloud_find_gap_s`: the coarse finder (a^ and the 7 pictures
    at 1/4 size, masked SSD by FFT) names (picture, place), the exact blend at full size +-5 px decides (opacity =
    the median of the samples' ratios).
`undo(frame)` (step 5) takes the layer out again: frame' = (frame - P) / (1 - A)."""
import json
import time
from pathlib import Path

import cv2
import numpy as np

from ..scene import PLAY_H, ROOT, W as SW

S = 4                                  # the coarse finder's scale
WHITE = 253.0                          # alpha_hat: the clouds' colour (near white) the thickness is read against


class Clouds:
    def __init__(self, dev, cfg=None, root: Path = ROOT, n: int = 1500, seed: int = 0):
        import torch
        from ..config import Perception
        self.torch, self.dev = torch, dev
        self.cfg = cfg or Perception()
        self.tol = self.cfg.scene_tol
        d = Path(root) / "clouds"
        self.origins = json.loads((d / "clouds.json").read_text(encoding="utf-8"))["origins"]
        self.sprites, self.half = [], []
        k = 0
        while (d / f"{k}.png").exists():
            im = cv2.imread(str(d / f"{k}.png"), cv2.IMREAD_UNCHANGED)
            t = torch.from_numpy(np.ascontiguousarray(im)).to(dev).float()
            s, a = t[..., :3], t[..., 3] / 255.0
            self.sprites.append((s, a))
            self.half.append((s.half(), a.half()[..., None]))
            k += 1
        # sample pixels per picture (alpha >= 0.2): the batched check
        g = torch.Generator().manual_seed(seed)
        px, py, aa, col = [], [], [], []
        for s, a in self.sprites:
            yy, xx = (a.cpu() >= 0.2).nonzero(as_tuple=True)
            pick = torch.randperm(len(yy), generator=g)[:n]
            xx, yy, pad = xx[pick], yy[pick], n - len(pick)
            if pad:                                            # padded far off screen: never informative
                xx = torch.cat([xx, torch.zeros(pad, dtype=xx.dtype)])
                yy = torch.cat([yy, torch.full((pad,), -10 ** 6, dtype=yy.dtype)])
            ok = yy >= 0
            px.append(xx)
            py.append(yy)
            aa.append(torch.where(ok, a.cpu()[yy.clamp(min=0), xx], torch.zeros(len(xx))))
            col.append(s.cpu()[yy.clamp(min=0), xx])
        self.px, self.py = torch.stack(px).to(dev), torch.stack(py).to(dev)                    # (7, N)
        self.a, self.col = torch.stack(aa).to(dev), torch.stack(col).to(dev)                   # (7, N), (7, N, 3)
        # the coarse finder: the pictures' alpha at 1/4 size and their FFT kernels
        F = torch.nn.functional
        self.sp = []
        for s, a in self.sprites:
            h, w = a.shape
            ap = F.pad(a, (0, (-w) % S, 0, (-h) % S))
            self.sp.append(F.avg_pool2d(ap[None, None], S)[0, 0])
        self.mh, self.mw = max(a.shape[0] for a in self.sp), max(a.shape[1] for a in self.sp)
        self.ch, self.cw = PLAY_H // S, (SW + S - 1) // S
        self.PH, self.PW = self.ch + 2 * self.mh, self.cw + 2 * self.mw
        self.FH, self.FW = 320, 648
        assert self.FH >= self.PH + self.mh and self.FW >= self.PW + self.mw
        self.K = []
        for a in self.sp:
            h, w = a.shape
            ka, k2, k1 = (torch.zeros((self.FH, self.FW), device=dev) for _ in range(3))
            ka[:h, :w], k2[:h, :w], k1[:h, :w] = a, a * a, 1
            self.K.append(tuple(torch.fft.rfft2(x).conj() for x in (ka, k2, k1)) + (float((a * a).sum()),))
        self.reset()

    def reset(self):
        """A new stay (a map entry): nothing followed."""
        self.tracks, self.next_id = [], 0
        self.t_first, self.last_find, self.gap = None, -1e9, None
        self.ms, self.finds, self.on = {}, 0, []
        self.P = self.A = None

    # ---- the exact blend
    def _check(self, f, E, valid, trs, C, t, r):
        """Followed clouds `trs` checked within r px of their predicted places -> lists (x, y, share, n_inf)."""
        torch = self.torch
        d = torch.arange(-r, r + 1, device=self.dev)
        dx, dy = (v.reshape(-1) for v in torch.meshgrid(d, d, indexing="xy"))
        k = torch.tensor([tr["k"] for tr in trs], device=self.dev)
        x = torch.tensor([int(round(tr["mx"] + tr["vx"] * (t - tr["t"]))) - C[0] for tr in trs], device=self.dev)
        y = torch.tensor([int(round(tr["my"] + tr["vy"] * (t - tr["t"]))) - C[1] for tr in trs], device=self.dev)
        o = torch.tensor([tr["o"] for tr in trs], device=self.dev)
        sx = x[:, None, None] + dx[None, :, None] + self.px[k][:, None, :]                   # (n, K, N)
        sy = y[:, None, None] + dy[None, :, None] + self.py[k][:, None, :]
        ok = (sx >= 0) & (sx < SW) & (sy >= 0) & (sy < PLAY_H)
        sxc, syc = sx.clamp(0, SW - 1), sy.clamp(0, PLAY_H - 1)
        Ff, Ee = f[syc, sxc].float(), E[syc, sxc]
        ok &= valid[syc, sxc]
        q = (o[:, None, None] * self.a[k][:, None, :])[..., None] * (self.col[k][:, None] - Ee)
        inf = ok & (q.abs().amax(dim=3) > 2 * self.tol)
        hit = inf & ((Ff - Ee - q).abs().amax(dim=3) <= self.tol)
        n = inf.sum(dim=2)
        share = hit.sum(dim=2).float() / n.clamp(min=1)
        best = share.argmax(dim=1)
        ar = torch.arange(len(trs), device=self.dev)
        out = torch.stack([(x + dx[best]).double(), (y + dy[best]).double(), share[ar, best].double(),
                           n[ar, best].double()]).cpu().numpy()                                # one transfer
        return out[0].astype(int), out[1].astype(int), out[2], out[3].astype(int)

    def _new(self, f, E2, valid, k, x, y, r=5):
        """A coarse candidate checked at full size: the best place within r px, the opacity = the median of the
        samples' ratios -> (share, n, o, x, y)."""
        torch = self.torch
        d = torch.arange(-r, r + 1, device=self.dev)
        dx, dy = (v.reshape(-1) for v in torch.meshgrid(d, d, indexing="xy"))
        sx = x + dx[:, None] + self.px[k][None, :]                                           # (K, N)
        sy = y + dy[:, None] + self.py[k][None, :]
        ok = (sx >= 0) & (sx < SW) & (sy >= 0) & (sy < PLAY_H)
        sxc, syc = sx.clamp(0, SW - 1), sy.clamp(0, PLAY_H - 1)
        Ff, Ee = f[syc, sxc].float(), E2[syc, sxc]
        ok &= valid[syc, sxc]
        q = self.a[k][None, :, None] * (self.col[k][None] - Ee)                               # the change at opacity 1
        rr = Ff - Ee
        qq = (q * q).sum(dim=2)
        use = ok & (q.abs().amax(dim=2) > 16)
        ratio = torch.where(use, (rr * q).sum(dim=2) / qq.clamp(min=1e-6), torch.full_like(qq, float("nan")))
        o = torch.nan_to_num(torch.nanmedian(ratio, dim=1).values.clamp(0, 1), nan=0.0)        # (K,)
        pred = o[:, None, None] * q
        inf = ok & (pred.abs().amax(dim=2) > 8)
        hit = inf & ((rr - pred).abs().amax(dim=2) <= self.tol)
        n = inf.sum(dim=1)
        share = hit.sum(dim=1).float() / n.clamp(min=1)
        share = torch.where((o >= 0.3) & (n >= self.cfg.cloud_new[1]), share, torch.zeros_like(share))
        b = int(share.argmax())
        return float(share[b]), int(n[b]), float(o[b]), x + int(dx[b]), y + int(dy[b])

    # ---- the cloud layer
    def layer(self, clouds):
        """[(k, x, y, o)] screen places -> (P premultiplied colour (h, w, 3) half, A alpha (h, w, 1) half)."""
        torch = self.torch
        P = torch.zeros((PLAY_H, SW, 3), dtype=torch.half, device=self.dev)
        A = torch.zeros((PLAY_H, SW, 1), dtype=torch.half, device=self.dev)
        one = torch.ones((), dtype=torch.half, device=self.dev)
        for k, x, y, o in clouds:
            s, a = self.half[k]
            h, w = a.shape[:2]
            x0, y0, x1, y1 = max(0, x), max(0, y), min(SW, x + w), min(PLAY_H, y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            aa = a[y0 - y:y1 - y, x0 - x:x1 - x] * o
            P[y0:y1, x0:x1].lerp_(s[y0 - y:y1 - y, x0 - x:x1 - x], aa)                       # P (1 - a) + a s
            A[y0:y1, x0:x1].lerp_(one, aa)
        return P, A

    def undo(self, f, amax: float | None = None):
        """The frame (>= PLAY_H rows) with the cloud layer taken out (uint8 (PLAY_H, SW, 3)) + the pixels a cloud
        leaves too little of (A > amax, default `cloud_thick`: not valid, "covered by cloud")."""
        P, A = self.P, self.A
        amax = self.cfg.cloud_thick if amax is None else amax
        f = f[:PLAY_H]
        und = ((f.half() - P) / (1 - A).clamp(min=0.05)).round_().clamp_(0, 255).to(self.torch.uint8)
        return self.torch.where(A > 0.004, und, f), A[..., 0] > amax

    # ---- new clouds
    def alpha_hat(self, f, E, valid):
        """(a^ (h, w), usable (h, w)): the cloud thickness the frame implies per pixel, where it can be told."""
        den = WHITE - E
        ch_ok = den >= 48
        a = (f - E) / den.clamp(min=1)
        n = ch_ok.float().sum(dim=2)
        mean = (a * ch_ok).sum(dim=2) / n.clamp(min=1)
        spread = ((a - mean[..., None]).abs() * ch_ok).amax(dim=2)
        expl = (f - E).abs().amax(dim=2) <= self.tol
        usable = valid & (n >= 1) & ((spread <= 0.06) | expl) & (mean > -0.05) & (mean < 1.05)
        mean = self.torch.where(expl, self.torch.zeros_like(mean), mean).clamp(0, 1)
        return mean, usable

    def _coarse(self, ah, usable, vis_min=0.15, ratio_max=0.6, top=3):
        """-> [(ratio, k, x, y)] screen places of the best coarse matches (up to `top` a picture), best first."""
        torch = self.torch
        F = torch.nn.functional
        pad_w = (-SW) % S
        m = F.avg_pool2d(F.pad(usable.float(), (0, pad_w))[None, None], S)[0, 0]
        ma = F.avg_pool2d(F.pad(ah * usable, (0, pad_w))[None, None], S)[0, 0]
        mean = ma / m.clamp(min=1e-3)
        w = (m > 0.3).float()
        A, A2 = mean * w, mean * mean * w
        padf = lambda x: F.pad(x, (self.mw, self.FW - x.shape[1] - self.mw, self.mh, self.FH - x.shape[0] - self.mh))
        Fm, Fa, Fa2 = (torch.fft.rfft2(padf(x)) for x in (w, A, A2))
        out = []
        for k, (ka, k2, k1, e) in enumerate(self.K):
            t1 = torch.fft.irfft2(Fa2 * k1, s=(self.FH, self.FW))
            t2 = torch.fft.irfft2(Fa * ka, s=(self.FH, self.FW))
            t3 = torch.fft.irfft2(Fm * k2, s=(self.FH, self.FW))
            ratio = ((t1 - 2 * t2 + t3) / t3.clamp(min=1e-3))[:self.PH, :self.PW]
            vis = t3[:self.PH, :self.PW] / e
            r = torch.where(vis >= vis_min, ratio, torch.full_like(ratio, 9.0))
            for _ in range(top):
                v, at = r.flatten().min(dim=0)
                if float(v) > ratio_max:
                    break
                y, x = int(at) // self.PW, int(at) % self.PW
                out.append((float(v), k, (x - self.mw) * S, (y - self.mh) * S))
                r[max(0, y - 4):y + 5, max(0, x - 4):x + 5] = 9.0
        return sorted(out)

    # ---- one frame
    def _screen(self, tr, C, t):
        return (int(round(tr["mx"] + tr["vx"] * (t - tr["t"]))) - C[0],
                int(round(tr["my"] + tr["vy"] * (t - tr["t"]))) - C[1])

    def update(self, f, E, valid, C, t: float) -> list:
        """`f`: the frame (uint8 (>= PLAY_H, SW, 3) tensor); `E`: the expected picture WITHOUT clouds (float, Scene.
        expected); `valid`: bool (PLAY_H, SW), the pixels that can show the scene (known, not UI); `C`: the camera.
        -> the clouds on screen (dicts: id, k, mx, my map place of the top-left, vx, vy, o, share, n); self.P / self.A
        their layer; self.ms the parts' ms."""
        torch, cfg = self.torch, self.cfg
        sync = torch.cuda.synchronize if self.dev == "cuda" else (lambda: None)
        f = f[:PLAY_H]
        C = (int(C[0]), int(C[1]))
        if self.t_first is None:
            self.t_first, self.gap = t, cfg.cloud_find_gap_s[0]
        t0 = time.perf_counter()
        on = []
        for tr in self.tracks:
            h, w = self.sprites[tr["k"]][1].shape
            x, y = self._screen(tr, C, t)
            if x + w > -20 and x < SW + 20 and y + h > -20 and y < PLAY_H + 20:
                on.append(tr)
        ok_sh, ok_n = cfg.cloud_ok
        gone_sh, gone_n, gone_k = cfg.cloud_gone
        for group, r in (([tr for tr in on if tr["n"] >= 2], cfg.cloud_near),
                         ([tr for tr in on if tr["n"] < 2], cfg.cloud_near_new)):
            if not group:
                continue
            bx, by, sh, nn = self._check(f, E, valid, group, C, t, r)
            for tr, x, y, s, n in zip(group, bx, by, sh, nn):
                tr["share"], tr["ninf"] = float(s), int(n)
                if s >= ok_sh and n >= ok_n:
                    mx, my = int(x) + C[0], int(y) + C[1]
                    if tr["n"] >= 1 and t - tr["t0"] > 0.05:
                        tr["vx"] = (mx - tr["x0"]) / (t - tr["t0"])
                        tr["vy"] = (my - tr["y0"]) / (t - tr["t0"])
                    tr["mx"], tr["my"], tr["t"] = mx, my, t
                    tr["n"] += 1
                    tr["miss"] = 0
                    tr["seen"] = True
                else:
                    tr["seen"] = False
                    if n >= gone_n and s < gone_sh:
                        tr["miss"] += 1                  # the frame shows something else where it should be
        self.tracks = [tr for tr in self.tracks if tr["miss"] < gone_k and t - tr["t"] < 240]
        on = [tr for tr in on if tr["miss"] < gone_k]
        sync()
        t1 = time.perf_counter()

        def lay():
            return self.layer([(tr["k"], *self._screen(tr, C, t), tr["o"]) for tr in on])
        P, A = lay()
        E2 = E * (1 - A.float()) + P.float()
        sync()
        t2 = time.perf_counter()
        ah, usable = self.alpha_hat(f.float(), E2, valid)
        n_res = int(((ah > 0.1) & usable).sum())
        t3 = time.perf_counter()
        find = 0.0
        start, g0, g1, gmax = cfg.cloud_find_gap_s
        if n_res > cfg.cloud_whitened_px and t - self.last_find >= self.gap:
            self.last_find = t
            self.finds += 1
            added = 0
            for ratio, k, x, y in self._coarse(ah, usable):
                if any(tr["k"] == k and abs(self._screen(tr, C, t)[0] - x) < 12 and abs(self._screen(tr, C, t)[1] - y) < 12
                       for tr in on):
                    continue
                share, n, o, bx, by = self._new(f, E2, valid, k, x, y)
                if share >= cfg.cloud_new[0] and n >= cfg.cloud_new[1]:
                    tr = {"id": self.next_id, "k": k, "mx": bx + C[0], "my": by + C[1], "vx": 0.0, "vy": 0.0, "o": o,
                          "t": t, "t0": t, "x0": bx + C[0], "y0": by + C[1], "n": 1, "miss": 0, "share": share,
                          "ninf": n, "seen": True}
                    self.next_id += 1
                    self.tracks.append(tr)
                    on.append(tr)
                    added += 1
                    P, A = lay()
                    E2 = E * (1 - A.float()) + P.float()
            sync()
            find = time.perf_counter() - t3
            if t - self.t_first < start:
                self.gap = g0
            else:
                self.gap = g1 if added else min(gmax, max(g1, 2 * self.gap))
        self.P, self.A, self.E2, self.on = P, A, E2, on
        self.ms = {"follow": round(1000 * (t1 - t0), 2), "layer": round(1000 * (t2 - t1), 2),
                   "whitened": round(1000 * (t3 - t2), 2), "find": round(1000 * find, 2), "residue_px": n_res}
        return on

    def facts(self) -> list:
        """The clouds on screen for FrameFacts: (id, picture, map x, map y of the top-left, vx, vy, opacity, seen on
        this frame, share of its informative pixels explained, informative pixels)."""
        return [(tr["id"], tr["k"], int(tr["mx"]), int(tr["my"]), round(tr["vx"], 2), round(tr["vy"], 2),
                 round(tr["o"], 4), bool(tr.get("seen")), round(tr["share"], 3), int(tr["ninf"])) for tr in self.on]
