"""Mobs anywhere on screen by their sprites, on the GPU (perception rework, 2026-11-03).

Every live frame (stand / move / fly, both facings) of every mob on the map is matched over the whole play area
at once: masked normalised cross-correlation (= OpenCV TM_CCOEFF_NORMED with a mask) as three batched
convolutions at `scale` (0.5: what the CPU detector measured as full recall). Peaks per mob, one per spot, then
each refined at full size on the CPU in a small window (the best pose and its neighbours) -> exact box, pose and
feet (the frame's origin from mob.json).

Needs torch with CUDA (falls back to the CPU device: correct, slow).
"""
from dataclasses import dataclass
from pathlib import Path
import json

import cv2
import numpy as np

from .sprites import Pose, load_mob

LIVE = ("stand", "move", "fly")
NEAR_BATCH = (2, 4, 8, 16)            # find_near batch sizes (more spots: chunks of 16)
NEAR_PADS = (24, 32)                 # the tracker's two window sizes
REFINE_BATCH = (4, 8, 16, 32, 64)    # find's refine step, candidates per frame (max_cands 64)
PLAY_H = 700


@dataclass
class Hit:
    mob_id: int
    box: tuple          # (x, y, w, h) full-size screen pixels
    feet: tuple         # (x, y)
    pose: Pose
    score: float


def _live_frames(mob_dir: Path, anims=LIVE):
    """[(bgr, mask, Pose)] of the mob's `anims` frames (default stand/move/fly), both facings."""
    info = json.loads((mob_dir / "mob.json").read_text(encoding="utf-8"))
    out = []
    books = info.get("frames") or {}
    for anim in (books if anims is None else anims):
        for i, f in enumerate(books.get(anim) or []):
            im = cv2.imread(str(mob_dir / f["file"]), cv2.IMREAD_UNCHANGED)
            if im is None or im.ndim != 3 or im.shape[2] != 4 or min(im.shape[:2]) < 4:
                continue                                   # 1x1 placeholders (links)
            h, w = im.shape[:2]
            ox, oy = f.get("origin") or (w // 2, h)
            for flip in (False, True):
                t = np.ascontiguousarray(im[:, ::-1]) if flip else im
                m = (t[..., 3] > 200).astype(np.uint8)
                if m.sum() < 60:
                    continue
                pose = Pose(anim, i, "right" if flip else "left", int(w - ox if flip else ox), int(oy))
                out.append((np.ascontiguousarray(t[..., :3]), m, pose))
    return info, out


class GpuSpriteDetector:
    def __init__(self, mob_dirs, min_score=0.65, scale=0.5, device=None, coarse_slack=0.07, flat_std=2.0,
                 max_cands=64, anims=LIVE):
        import torch
        self.torch = torch
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.scale, self.min_score, self.slack = scale, min_score, coarse_slack
        self.flat_std, self.max_cands = flat_std, max_cands
        self.items = []            # (mob_id, bgr, mask, Pose) full size
        self.names, self.max_w = {}, {}
        for d in mob_dirs:
            info, frames = _live_frames(Path(d), anims)
            mid = int(info["id"])
            self.names[mid] = info.get("name", str(mid))
            self.max_w[mid] = max((t.shape[1] for t, _, _ in frames), default=40)
            self.items += [(mid, t, m, p) for t, m, p in frames]
        self.mob_ids = sorted(self.names)
        self.items.sort(key=lambda it: self.mob_ids.index(it[0]))      # each mob's poses contiguous
        self.spans, k = [], 0
        for mid in self.mob_ids:
            n = sum(1 for it in self.items if it[0] == mid)
            self.spans.append((k, k + n))
            k += n
        self.rad = max(2, int(min(self.max_w.values()) * scale * 0.3))
        self.k_mob = torch.tensor([self.mob_ids.index(it[0]) for it in self.items], device=self.dev)
        small = []
        for _, t, m, _ in self.items:
            ts = cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            ms = (cv2.resize(m * 255, (ts.shape[1], ts.shape[0]), interpolation=cv2.INTER_AREA) > 160)
            small.append((ts, ms.astype(np.uint8)))
        H, W = max(t.shape[0] for t, _ in small), max(t.shape[1] for t, _ in small)
        K = len(small)
        T = np.zeros((K, 3, H, W), np.float32)
        M = np.zeros((K, 1, H, W), np.float32)
        for k, (t, m) in enumerate(small):
            h, w = m.shape
            tt = t.astype(np.float32).transpose(2, 0, 1) / 255
            mm = m.astype(np.float32)
            mean = (tt * mm).sum(axis=(1, 2), keepdims=True) / mm.sum()
            T[k, :, :h, :w] = (tt - mean) * mm
            M[k, 0, :h, :w] = mm
        self.T = torch.tensor(T, device=self.dev)
        self.M = torch.tensor(M, device=self.dev)
        self.n = self.M.sum(dim=(1, 2, 3)).view(1, K, 1, 1)
        self.tnorm = (self.T ** 2).sum(dim=(1, 2, 3)).view(1, K, 1, 1)
        self.H, self.W, self.K = H, W, K
        # full size, for the refine step (all candidates at once, on the GPU)
        self.Tf, self.Mf, self.nf, self.tnf, self.Hf, self.Wf = self._bank([(t, m) for _, t, m, _ in self.items])
        # every pose (hit / die / attack too), full size, for searching around tracked mobs (`find_near`)
        self.near_items, self.near_by_mob = [], {}
        for d in mob_dirs:
            info, frames = _live_frames(Path(d), anims=None)
            mid = int(info["id"])
            for t, m, p in frames:
                self.near_by_mob.setdefault(mid, []).append(len(self.near_items))
                self.near_items.append((mid, t, m, p))
        self.Tn, self.Mn, self.nn, self.tnn, self.Hn, self.Wn = self._bank([(t, m) for _, t, m, _ in self.near_items])
        # the raw masked templates too, for comparing only the pixels nothing is drawn over (cover masks)
        R = np.zeros((len(self.near_items), 3, self.Hn, self.Wn), np.float32)
        for k, (_, t, m, _) in enumerate(self.near_items):
            h, w = m.shape
            R[k, :, :h, :w] = t.astype(np.float32).transpose(2, 0, 1) / 255 * m
        self.Rn = torch.tensor(R, device=self.dev)
        self.Rn_c = self.Rn.reshape(-1, 1, self.Hn, self.Wn)           # (K*3, 1, H, W): per channel
        self.Rn2 = (self.Rn ** 2).sum(1, keepdim=True)                   # (K, 1, H, W)
        torch.backends.cudnn.benchmark = True

    def _bank(self, tm):
        """Zero-mean masked templates padded to one size -> (T, M, mask sums, |T|^2, H, W) on the device."""
        torch = self.torch
        H, W = max(t.shape[0] for t, _ in tm), max(t.shape[1] for t, _ in tm)
        T = np.zeros((len(tm), 3, H, W), np.float32)
        M = np.zeros((len(tm), 1, H, W), np.float32)
        for k, (t, m) in enumerate(tm):
            h, w = m.shape
            tt = t.astype(np.float32).transpose(2, 0, 1) / 255
            mm = m.astype(np.float32)
            mean = (tt * mm).sum(axis=(1, 2), keepdims=True) / mm.sum()
            T[k, :, :h, :w] = (tt - mean) * mm
            M[k, 0, :h, :w] = mm
        T, M = torch.tensor(T, device=self.dev), torch.tensor(M, device=self.dev)
        return T, M, M.sum(dim=(1, 2, 3)), (T ** 2).sum(dim=(1, 2, 3)), H, W

    @classmethod
    def for_map(cls, map_id: int, root: Path, **kw) -> "GpuSpriteDetector":
        m = json.loads((root / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in m.get("mobs") or []})
        return cls([root / "mobs" / str(i) for i in ids if (root / "mobs" / str(i) / "mob.json").exists()], **kw)

    def _dev_frame(self, play, fresh=False):
        """The play area on the device, zero-mean (3, h, w) float. `find` uploads it (`fresh`) and the refine step and
        find_near calls on that same frame reuse it; anything else is uploaded each time (a buffer can be reused or
        drawn into in place - only `find` marks the start of a new frame)."""
        key = (play.__array_interface__["data"][0], play.shape, play[::61, ::59].tobytes())
        if not fresh and getattr(self, "_frame_key", None) == key:
            return self._frame_dev
        x = self.torch.from_numpy(np.ascontiguousarray(play)).to(self.dev).permute(2, 0, 1).float() / 255
        x = x - x.mean()
        if fresh:
            self._frame_dev, self._frame_key = x, key
        return x

    def scores(self, img_small: np.ndarray):
        """(K, h, w) NCC of every template at every top-left position of the (scaled) image."""
        torch, F = self.torch, self.torch.nn.functional
        x = torch.from_numpy(img_small).to(self.dev).permute(2, 0, 1).unsqueeze(0).float() / 255
        x = F.pad(x, (0, self.W, 0, self.H), mode="replicate")      # templates are padded: keep the edges
        cross = F.conv2d(x, self.T)
        xc = x.transpose(0, 1)
        xc = xc - xc.mean()
        s1 = F.conv2d(xc, self.M)
        s2 = F.conv2d(xc * xc, self.M)
        var = (s2 - s1 * s1 / self.n).sum(0, keepdim=True)
        r = cross / torch.sqrt(var.clamp_min(1e-6) * self.tnorm)
        # flat windows (sky, a plain wall: std < flat_std grey levels) have no shape: noise / ~0 gave scores of 32
        r = torch.where(var < 3 * self.n * (self.flat_std / 255) ** 2, torch.full_like(r, -1.0), r)[0]
        h, w = img_small.shape[:2]
        return r[:, :h, :w]

    def find(self, frame, refine=True, top=3) -> list:
        torch, F = self.torch, self.torch.nn.functional
        sc = self.scale
        play = frame[:PLAY_H]
        self._dev_frame(play, fresh=True)                       # a new frame's work starts here: upload it once
        small = cv2.resize(play, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        r = self.scores(small)                                   # (K, h, w)
        # per mob: best pose per position, local maxima only - all mobs in one go (their poses are contiguous)
        best = torch.stack([r[a:b].max(dim=0).values for a, b in self.spans])          # (n_mobs, h, w)
        pooled = F.max_pool2d(best[:, None], 2 * self.rad + 1, stride=1, padding=self.rad)[:, 0]
        peak = (best >= pooled) & (best >= self.min_score - self.slack)
        mi, ys, xs = peak.nonzero(as_tuple=True)
        if len(mi) == 0:
            return []
        if len(mi) > self.max_cands:                            # best first; a frame never holds this many mobs
            keep = best[mi, ys, xs].topk(self.max_cands).indices
            mi, ys, xs = mi[keep], ys[keep], xs[keep]
        col = r[:, ys, xs]                                       # (K, n): every pose's score at each peak
        col = torch.where(self.k_mob[:, None] == mi[None], col, torch.full_like(col, -2.0))
        topv, topk = col.topk(min(top, self.K), dim=0)          # the peak's mob's best poses
        mi, ys, xs = mi.tolist(), ys.tolist(), xs.tolist()
        topv, topk = topv.T.tolist(), topk.T.tolist()            # one GPU -> CPU copy
        xs_f, ys_f = [int(x / sc) for x in xs], [int(y / sc) for y in ys]
        if refine:
            ks = [[j for j, v in zip(topk[i], topv[i]) if v > -2] or [topk[i][0]] for i in range(len(mi))]
            ref = self._refine(play, ks, xs_f, ys_f)
        else:
            ref = [(topv[i][0], topk[i][0], xs_f[i], ys_f[i]) for i in range(len(mi))]
        cands = sorted(((r_[0], self.mob_ids[mi[i]], r_[1], r_[2], r_[3]) for i, r_ in enumerate(ref)), reverse=True)
        hits = []
        for s, mid, k, x, y in cands:
            if s < self.min_score:
                continue
            _, t, m, pose = self.items[k]
            h, w = t.shape[:2]
            feet = (x + pose.ox, y + pose.oy)
            if any(abs(feet[0] - o.feet[0]) < 0.5 * min(w, self.max_w[o.mob_id]) and abs(feet[1] - o.feet[1]) < 20
                   for o in hits):
                continue                                         # one mob per spot (look-alike mobs too)
            hits.append(Hit(mid, (x, y, w, h), feet, pose, round(float(s), 3)))
        return hits

    def find_near(self, frame, spots, pad=24, min_score=0.55, vis=None, vis_min=0.3) -> list:
        """Around tracked mobs: `spots` = [(mob id or ids, feet x, feet y)] (screen, predicted). Every pose (hit /
        die / attack too) of those mob types (the tracker's voted ones; unknown id: every type on the map) within
        +-`pad` px of the prediction (`pad`: one for all, or one per spot), at full size -> one best `Hit` or None
        per spot (score >= min_score). Spots with the same pad go in one batch: a plain convolution of every pose
        over every window (3x faster than grouped convolutions of only the allowed poses), the rest masked.
        `vis`: per spot, the screen's visibility for that mob's layer ((700, W) bool, cover.Cover.visible) or None
        (all visible) - given (even all None), only the pixels nothing is drawn over are compared, and a pose
        needs >= vis_min of its pixels visible (a Pig in grass scores like a free one)."""
        if not spots:
            return []
        pads = list(pad) if isinstance(pad, (list, tuple)) else [pad] * len(spots)
        out = [None] * len(spots)
        x = self._dev_frame(frame[:PLAY_H])
        for P in sorted(set(pads)):
            idx = [i for i, p in enumerate(pads) if p == P]
            res = []
            for c0 in range(0, len(idx), NEAR_BATCH[-1]):
                chunk = idx[c0:c0 + NEAR_BATCH[-1]]
                res += self._near_batch(x, [spots[i] for i in chunk], P,
                                        None if vis is None else [vis[i] for i in chunk], vis_min)
            for i, (s, k, bx, by) in zip(idx, res):
                if s >= min_score:
                    mid, t, _, pose = self.near_items[k]
                    out[i] = Hit(mid, (bx, by, t.shape[1], t.shape[0]), (bx + pose.ox, by + pose.oy), pose,
                                 round(float(s), 3))
        return out

    def warm_near(self, pads=NEAR_PADS, occluded=False) -> float:
        """cudnn.benchmark times every new convolution shape once (0.4-4.5 s each): do it for every batch size and
        window at map load, not mid-hunt. -> seconds (~9 on the RTX 4070 Ti SUPER)."""
        import time
        t0 = time.perf_counter()
        blank = np.full((PLAY_H, 1366, 3), 90, np.uint8)
        blank[::7] = 200
        for b in NEAR_BATCH:
            for P in pads:
                self.find_near(blank, [(None, 100 + 60 * i, 500) for i in range(b)], pad=P,
                               vis=[None] * b if occluded else None)
        for b in REFINE_BATCH:                                 # and find's refine step
            self._refine(blank, [[0, 0, 0]] * b, [100 + 10 * i for i in range(b)], [300] * b)
        return time.perf_counter() - t0

    def _near_batch(self, x, spots, P, vis=None, vis_min=0.3) -> list:
        torch, F = self.torch, self.torch.nn.functional
        T, M, nb, tnb, Hf, Wf = self.Tn, self.Mn, self.nn, self.tnn, self.Hn, self.Wn
        K = T.shape[0]
        allow = np.zeros((len(spots), K), bool)
        xs, ys = [], []
        H, W = x.shape[1], x.shape[2]
        for i, (mid, fx, fy) in enumerate(spots):
            ids = mid if isinstance(mid, (list, tuple, set)) else (mid,)
            k = [j for m in ids for j in self.near_by_mob.get(m, [])] or list(range(K))
            allow[i, k] = True
            ox = int(np.median([self.near_items[j][3].ox for j in k]))
            oy = int(np.median([self.near_items[j][3].oy for j in k]))
            if vis is None:                                       # plain NCC: windows stay inside the picture
                xs.append(min(max(int(fx) - ox, 0), W - 1))
                ys.append(min(max(int(fy) - oy, 0), H - 1))
            else:                                                 # visible-only NCC: may reach past the edges
                xs.append(min(max(int(fx) - ox, -Wf // 2), W - 1))
                ys.append(min(max(int(fy) - oy, -Hf // 2), H - 1))
        xp = F.pad(x[None], (P + Wf, Wf + P, P + Hf, Hf + P), mode="replicate")[0]
        n = len(spots)
        nb_ = next((b for b in NEAR_BATCH if b >= n), n)            # fixed batch sizes: cudnn.benchmark times
        xs_b, ys_b = xs + [xs[0]] * (nb_ - n), ys + [ys[0]] * (nb_ - n)  # each new shape once (1.3 s stalls)
        wins = torch.stack([xp[:, y + Hf:y + 2 * Hf + 2 * P, x_ + Wf:x_ + 2 * Wf + 2 * P] for x_, y in zip(xs_b, ys_b)])
        allow = np.concatenate([allow, np.repeat(allow[:1], nb_ - n, axis=0)])
        n_real, n = n, nb_
        if vis is not None:
            r = self._occluded(wins, xs_b, ys_b, vis + [vis[0]] * (nb_ - n_real), P, vis_min, (H, W))
        else:
            cross = F.conv2d(wins, T)                              # (n, K, 2P+1, 2P+1)
            w1 = wins.reshape(n * 3, 1, *wins.shape[2:])
            s1 = F.conv2d(w1, M).reshape(n, 3, K, *cross.shape[2:])
            s2 = F.conv2d(w1 * w1, M).reshape(n, 3, K, *cross.shape[2:])
            nk = nb[None, None, :, None, None]
            var = (s2 - s1 * s1 / nk).sum(1)
            r = cross / torch.sqrt(var.clamp_min(1e-6) * tnb[None, :, None, None])
            r = torch.where(var < 3 * nb[None, :, None, None] * (self.flat_std / 255) ** 2, torch.full_like(r, -1.0),
                            r)
        r = torch.where(torch.from_numpy(allow).to(self.dev)[:, :, None, None], r, torch.full_like(r, -2.0))
        v, best = r.reshape(n, -1).max(dim=1)
        v, best = v.tolist(), best.tolist()
        side = 2 * P + 1
        res = []
        for i in range(n_real):
            k, rem = divmod(best[i], side * side)
            dy, dx = divmod(rem, side)
            res.append((v[i], k, xs[i] - P + dx, ys[i] - P + dy))
        return res

    def _occluded(self, wins, xs, ys, vis, P, vis_min, screen):
        """Masked NCC over the pixels that are both the template's and visible (weight w = mask * V): the template's
        mean and spread are taken over the visible part too, so a half-covered mob scores like a whole one."""
        torch, F = self.torch, self.torch.nn.functional
        Hf, Wf, K = self.Hn, self.Wn, self.Tn.shape[0]
        n, hh, ww = wins.shape[0], wins.shape[2], wins.shape[3]
        V = np.zeros((n, 1, hh, ww), np.float32)                   # off screen: not visible
        for i, (v, x0, y0) in enumerate(zip(vis, xs, ys)):
            a, b = x0 - P, y0 - P                                   # window top-left in screen px
            sx0, sy0 = max(0, a), max(0, b)
            sx1, sy1 = min(screen[1], a + ww), min(screen[0], b + hh)
            if sx1 > sx0 and sy1 > sy0:
                V[i, 0, sy0 - b:sy1 - b, sx0 - a:sx1 - a] = 1.0 if v is None else v[sy0:sy1, sx0:sx1]
        V = torch.from_numpy(V).to(self.dev)
        xv = wins * V                                                # (n, 3, h, w)
        cnt = F.conv2d(V, self.Mn)                                   # (n, K, ..): visible template pixels
        sxc = F.conv2d(xv.reshape(n * 3, 1, hh, ww), self.Mn).reshape(n, 3, K, *cnt.shape[2:])
        sxx = F.conv2d((wins * xv).sum(1, keepdim=True), self.Mn)    # sum over channels of x^2 (visible)
        stc = F.conv2d(V, self.Rn_c).reshape(n, K, 3, *cnt.shape[2:]).transpose(1, 2)
        stt = F.conv2d(V, self.Rn2)
        sxt = F.conv2d(xv, self.Rn)
        c = cnt.clamp_min(1.0)
        cov = sxt - (sxc * stc).sum(1) / c
        vx = sxx - (sxc * sxc).sum(1) / c
        vt = stt - (stc * stc).sum(1) / c
        r = cov / torch.sqrt(vx.clamp_min(1e-6) * vt.clamp_min(1e-6))
        nk = self.nn[None, :, None, None]
        r = torch.where(cnt < vis_min * nk, torch.full_like(r, -1.0), r)
        return torch.where(vx < 3 * c * (self.flat_std / 255) ** 2, torch.full_like(r, -1.0), r)

    def _refine(self, play, ks, xs, ys, pad=4, bank="live") -> list:
        """Full size, a small window per candidate (coarse top-left +-pad), its best coarse poses - every candidate in
        one batch of grouped convolutions -> [(score, k, x, y)]. (On the CPU this step was 80 of Perion's 97 ms.)
        `bank` "near": `ks` index every pose (`near_items`) instead of the live ones."""
        torch, F = self.torch, self.torch.nn.functional
        n_real = len(ks)
        n = next((b for b in REFINE_BATCH if b >= n_real), n_real)     # fixed shapes (cudnn.benchmark: see
        top = max(3, max(len(k) for k in ks))                           # NEAR_BATCH): pad with copies
        ks, xs, ys = ks + [ks[0]] * (n - n_real), list(xs) + [xs[0]] * (n - n_real), list(ys) + [ys[0]] * (n - n_real)
        kt = torch.tensor([k + [k[0]] * (top - len(k)) for k in ks], device=self.dev)        # (n, top)
        Tb, Mb, nb, tnb, Hf, Wf = ((self.Tn, self.Mn, self.nn, self.tnn, self.Hn, self.Wn) if bank == "near" else
                                   (self.Tf, self.Mf, self.nf, self.tnf, self.Hf, self.Wf))
        P = pad
        x = self._dev_frame(play)
        xp = F.pad(x[None], (P, Wf + P, P, Hf + P), mode="replicate")[0]
        wins = torch.stack([xp[:, y:y + Hf + 2 * P, x_:x_ + Wf + 2 * P] for x_, y in zip(xs, ys)])  # (n,3,..)
        hw = (2 * P + 1, 2 * P + 1)
        flat = wins.reshape(1, n * 3, Hf + 2 * P, Wf + 2 * P)
        cross = F.conv2d(flat, Tb[kt].reshape(n * top, 3, Hf, Wf), groups=n).reshape(n, top, *hw)
        m3 = Mb[kt][:, None].expand(n, 3, top, 1, Hf, Wf).reshape(n * 3 * top, 1, Hf, Wf)
        s1 = F.conv2d(flat, m3, groups=n * 3).reshape(n, 3, top, *hw)
        s2 = F.conv2d(flat * flat, m3, groups=n * 3).reshape(n, 3, top, *hw)
        nk = nb[kt][:, None, :, None, None]
        var = (s2 - s1 * s1 / nk).sum(1)                                                     # (n, top, ..)
        r = cross / torch.sqrt(var.clamp_min(1e-6) * tnb[kt][:, :, None, None])
        r = torch.where(var < 3 * nk[:, 0] * (self.flat_std / 255) ** 2, torch.full_like(r, -1.0), r)
        v, idx = r.reshape(n, -1).max(dim=1)
        v, idx, ktl = v.tolist(), idx.tolist(), kt.tolist()
        out = []
        per = hw[0] * hw[1]
        for i in range(n_real):
            j, rem = divmod(idx[i], per)
            dy, dx = divmod(rem, hw[1])
            out.append((float(v[i]), ktl[i][j], xs[i] - P + dx, ys[i] - P + dy))
        return out


class GpuBand:
    """Drop-in for `SpriteDetector` in the Perceiver (`--gpu`, 2026-11-04): the GPU finds every mob on the whole
    screen once per frame; `find` hands back only the band the caller asks for (today's brain still works on our
    level only - the tracker will use the rest). `dying`, `mobs`, `max_h` come from the CPU detector."""

    def __init__(self, gpu: GpuSpriteDetector, cpu):
        self.gpu, self.cpu = gpu, cpu
        self._frame, self._hits = None, []
        self.last_ms = 0.0
        self.all_hits = []          # every mob of the last frame (whole screen), for logging

    @property
    def mobs(self):
        return self.cpu.mobs

    @property
    def max_h(self):
        return self.cpu.max_h

    def __len__(self):
        return len(self.cpu)

    def dying(self, *a, **kw):
        return self.cpu.dying(*a, **kw)

    def _all(self, frame):
        if self._frame is not frame:
            import time
            t0 = time.perf_counter()
            self._hits = self.gpu.find(frame)
            self.last_ms = (time.perf_counter() - t0) * 1000
            self._frame, self.all_hits = frame, self._hits
        return self._hits

    def find(self, frame, feet, below=0, above=75, exclude=(), with_pose=False) -> list:
        """Same contract as SpriteDetector.find: mobs whose sprite lies in the band from `above` px over `feet` to
        `below` (+8) px under it, not centred inside an `exclude` box."""
        y0, y1 = int(feet) - above, int(feet) + 8 + int(below)
        out = []
        for h in self._all(frame):
            x, y, w, hh = h.box
            if y < y0 - 4 or y + hh > y1 + 4:
                continue
            c = (x + w / 2, y + hh / 2)
            if any(e[0] <= c[0] <= e[0] + e[2] and e[1] <= c[1] <= e[1] + e[3] for e in exclude):
                continue
            out.append((h.box, h.mob_id, h.score, h.pose) if with_pose else (h.box, h.mob_id, h.score))
        return out
