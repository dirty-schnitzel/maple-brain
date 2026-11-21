"""Prototype: the map's weather clouds (info.cloud = 1: MapHelper.img/weather/cloud/0..6, drawn over the field).

A cloud is a known picture: near-white colour s with a per-pixel alpha a, drawn at its own opacity o over everything
under it (measured on Perion Street Corner: exact to the level, at whole pixels):
    frame = E + o a (s - E)          E = the expected picture without it (proto.MScene.expected)
- the fit's own model of a fading mob. So where the scene is known and not near white, the frame itself says how
thick the cloud is:   a^ = (frame - E) / (s - E)   (the same in the three channels: a mob or a player is not).
CloudFinder.find: the a^ picture matched against the 7 clouds' alpha pictures at every place (masked SSD by FFT),
the best places checked pixel by pixel with the exact model (opacity = the mode of a^ / a, then the share of the
cloud's informative pixels the frame shows within tol) - greedy, each accepted cloud drawn into E before the next
look (clouds overlap). CloudFinder.near: the same check around a predicted place (a tracked cloud: no FFT)."""
import re

import cv2
import numpy as np
import torch

import msl

SW, PLAY_H = 1366, 700
CLOUD_DIR = msl.OUT / "MapHelper" / "weather" / "cloud"


def origins():
    txt = (msl.EXPORT / "Map" / "MapHelper.img.xml").read_text(encoding="utf-8")
    blk = txt[txt.index('<imgdir name="cloud">'):txt.index('<imgdir name="flower">')]
    return [(int(x), int(y)) for x, y in re.findall(r'<vector name="origin" x="(-?\d+)" y="(-?\d+)"/>', blk)]


class CloudFinder:
    def __init__(self, dev, tol=4, white=253.0):
        self.dev, self.tol, self.white = dev, tol, white
        self.org = origins()
        self.sprites = []
        for k in range(7):
            im = cv2.imread(str(CLOUD_DIR / f"{k}.png"), cv2.IMREAD_UNCHANGED)
            t = torch.from_numpy(np.ascontiguousarray(im)).to(dev).float()
            self.sprites.append((t[..., :3], t[..., 3] / 255.0))
        self.mh = max(a.shape[0] for _, a in self.sprites)
        self.mw = max(a.shape[1] for _, a in self.sprites)
        self.PH, self.PW = PLAY_H + 2 * self.mh, SW + 2 * self.mw            # the frame padded by a cloud's size
        self.FH, self.FW = 1250, 2560
        assert self.FH >= self.PH + self.mh and self.FW >= self.PW + self.mw
        self.K = []
        for s, a in self.sprites:
            h, w = a.shape
            ka = torch.zeros((self.FH, self.FW), device=dev)
            ka[:h, :w] = a
            k2 = torch.zeros((self.FH, self.FW), device=dev)
            k2[:h, :w] = a * a
            k1 = torch.zeros((self.FH, self.FW), device=dev)
            k1[:h, :w] = 1
            self.K.append(tuple(torch.fft.rfft2(x).conj() for x in (ka, k2, k1)) + (float((a * a).sum()),))

    def alpha_hat(self, f, E, valid):
        """(a^ (h, w), usable (h, w)): the cloud thickness the frame implies per pixel, where it can be told."""
        den = self.white - E
        ch_ok = den >= 48
        a = (f - E) / den.clamp(min=1)
        n = ch_ok.float().sum(dim=2)
        mean = (a * ch_ok).sum(dim=2) / n.clamp(min=1)
        spread = ((a - mean[..., None]).abs() * ch_ok).amax(dim=2)
        expl = (f - E).abs().amax(dim=2) <= self.tol
        usable = valid & (n >= 1) & ((spread <= 0.06) | expl) & (mean > -0.05) & (mean < 1.05)
        mean = torch.where(expl, torch.zeros_like(mean), mean).clamp(0, 1)
        return mean, usable

    def scores(self, ah, usable):
        """Per cloud picture: (ratio (PH, PW) = unexplained share of the picture's alpha energy at each place,
        visible share of its energy). Place (y, x) of the padded picture = the cloud's top-left on screen + (mh, mw)."""
        pad = lambda x: torch.nn.functional.pad(x, (self.mw, self.FW - SW - self.mw, self.mh, self.FH - PLAY_H - self.mh))
        m = pad(usable.float())
        ma = pad(ah * usable)
        ma2 = pad(ah * ah * usable)
        Fm, Fma, Fma2 = torch.fft.rfft2(m), torch.fft.rfft2(ma), torch.fft.rfft2(ma2)
        out = []
        for ka, k2, k1, e in self.K:
            t1 = torch.fft.irfft2(Fma2 * k1, s=(self.FH, self.FW))
            t2 = torch.fft.irfft2(Fma * ka, s=(self.FH, self.FW))
            t3 = torch.fft.irfft2(Fm * k2, s=(self.FH, self.FW))
            ssd = (t1 - 2 * t2 + t3)[:self.PH, :self.PW]
            vis = t3[:self.PH, :self.PW]
            out.append((ssd / vis.clamp(min=1e-3), vis / e))
        return out

    def _crop(self, k, x, y):
        s, a = self.sprites[k]
        h, w = a.shape
        x0, y0, x1, y1 = max(0, x), max(0, y), min(SW, x + w), min(PLAY_H, y + h)
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1, y1), a[y0 - y:y1 - y, x0 - x:x1 - x], s[y0 - y:y1 - y, x0 - x:x1 - x]

    def check(self, f, E, valid, k, x, y, o=None):
        """The exact model for cloud k with its top-left at screen (x, y): (inlier share, informative px, opacity,
        visible share of the picture). `o` None: the opacity = the mode of the per-pixel a^ / a (128 bins), refined
        by least squares on the mode's pixels."""
        cr = self._crop(k, x, y)
        if cr is None:
            return 0.0, 0, 0.0, 0.0
        (x0, y0, x1, y1), a, s = cr
        Ee, ff, vv = E[y0:y1, x0:x1], f[y0:y1, x0:x1], valid[y0:y1, x0:x1]
        q = a[..., None] * (s - Ee)                                    # the pixel's change at opacity 1
        r = ff - Ee
        qq = (q * q).sum(dim=2)
        rq = (r * q).sum(dim=2)
        use = vv & (q.abs().amax(dim=2) > 16)
        if o is None:
            if int(use.sum()) < 50:
                return 0.0, int(use.sum()), 0.0, 0.0
            ratio = (rq / qq.clamp(min=1e-6))[use]
            b = (ratio * 128).round().clamp(-1, 140).long()
            hist = torch.bincount(b[(b >= 0) & (b <= 136)], minlength=137).float()
            sm = hist.clone()
            sm[1:] += hist[:-1]
            sm[:-1] += hist[1:]
            at = int(sm[26:].argmax()) + 26                            # opacities under 0.2: not looked for
            near = use & ((rq / qq.clamp(min=1e-6)) - at / 128).abs().le(1.5 / 128)
            o = float((rq * near).sum() / (qq * near).sum().clamp(min=1e-6))
            o = min(1.0, max(0.0, o))
        pred = Ee + o * q
        inf = vv & ((o * q).abs().amax(dim=2) > 2 * self.tol)
        ok = inf & ((ff - pred).abs().amax(dim=2) <= self.tol)
        n = int(inf.sum())
        vis = float((a > 0).sum()) / float((self.sprites[k][1] > 0).sum())
        return (float(ok.sum()) / n if n else 0.0), n, o, vis

    def draw(self, E, cov, k, x, y, o):
        """Cloud k drawn at opacity o over E at (x, y), its alpha added to `cov` (both in place)."""
        cr = self._crop(k, x, y)
        if cr is None:
            return
        (x0, y0, x1, y1), a, s = cr
        aa = (o * a)[..., None]
        E[y0:y1, x0:x1] = E[y0:y1, x0:x1] * (1 - aa) + aa * s
        cov[y0:y1, x0:x1] = 1 - (1 - cov[y0:y1, x0:x1]) * (1 - aa[..., 0])

    def near(self, f, E, valid, k, x, y, o=None, r=3):
        """The best place of cloud k within r px of (x, y) by the exact model -> (share, n, o, vis, x, y)."""
        best = None
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                c = self.check(f, E, valid, k, x + dx, y + dy, o)
                if best is None or (c[0], c[1]) > (best[0], best[1]):
                    best = c + (x + dx, y + dy)
        return best

    def find(self, f, E, valid, cov=None, max_clouds=12, ratio_max=0.45, vis_min=0.12, share_min=0.6, n_min=400,
             refine=2):
        """New clouds on the frame -> ([(k, x, y, share, n, o, visible)], E with them drawn in, cloud alpha).
        `E` / `cov`: already holding the tracked clouds (the caller's), changed in place."""
        if cov is None:
            cov = torch.zeros((PLAY_H, SW), device=self.dev)
        found, tried = [], []
        for _ in range(max_clouds + 6):
            if len(found) >= max_clouds:
                break
            ah, usable = self.alpha_hat(f, E, valid)
            sc = self.scores(ah, usable)
            best = None
            for k, (ratio, vis) in enumerate(sc):
                r = torch.where(vis >= vis_min, ratio, torch.full_like(ratio, 9.0))
                for (tk, tx, ty) in tried:
                    if tk == k:                                                    # a place already refused
                        r[max(0, ty + self.mh - 8):ty + self.mh + 9, max(0, tx + self.mw - 8):tx + self.mw + 9] = 9.0
                v, at = r.flatten().min(dim=0)
                if best is None or float(v) < best[0]:
                    best = (float(v), k, int(at) % self.PW - self.mw, int(at) // self.PW - self.mh)
            if best is None or best[0] > ratio_max:
                break
            _, k, x, y = best
            share, n, o, vis, bx, by = self.near(f, E, valid, k, x, y, None, refine)
            if share < share_min or n < n_min:
                tried.append((k, x, y))
                continue
            found.append((k, bx, by, round(share, 3), n, round(o, 4), round(vis, 2)))
            self.draw(E, cov, k, bx, by, o)
        return found, E, cov
