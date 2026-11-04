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
    for anim in anims:
        for i, f in enumerate((info.get("frames") or {}).get(anim) or []):
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
        Hf, Wf = max(t.shape[0] for _, t, _, _ in self.items), max(t.shape[1] for _, t, _, _ in self.items)
        Tf = np.zeros((K, 3, Hf, Wf), np.float32)
        Mf = np.zeros((K, 1, Hf, Wf), np.float32)
        for k, (_, t, m, _) in enumerate(self.items):
            h, w = m.shape
            tt = t.astype(np.float32).transpose(2, 0, 1) / 255
            mm = m.astype(np.float32)
            mean = (tt * mm).sum(axis=(1, 2), keepdims=True) / mm.sum()
            Tf[k, :, :h, :w] = (tt - mean) * mm
            Mf[k, 0, :h, :w] = mm
        self.Tf = torch.tensor(Tf, device=self.dev)
        self.Mf = torch.tensor(Mf, device=self.dev)
        self.nf = self.Mf.sum(dim=(1, 2, 3))
        self.tnf = (self.Tf ** 2).sum(dim=(1, 2, 3))
        self.Hf, self.Wf = Hf, Wf
        torch.backends.cudnn.benchmark = True

    @classmethod
    def for_map(cls, map_id: int, root: Path, **kw) -> "GpuSpriteDetector":
        m = json.loads((root / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in m.get("mobs") or []})
        return cls([root / "mobs" / str(i) for i in ids if (root / "mobs" / str(i) / "mob.json").exists()], **kw)

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

    def _refine(self, play, ks, xs, ys, pad=4) -> list:
        """Full size, a small window per candidate (coarse top-left +-pad), its best coarse poses - every candidate in
        one batch of grouped convolutions -> [(score, k, x, y)]. (On the CPU this step was 80 of Perion's 97 ms.)"""
        torch, F = self.torch, self.torch.nn.functional
        n, top = len(ks), max(len(k) for k in ks)
        kt = torch.tensor([k + [k[0]] * (top - len(k)) for k in ks], device=self.dev)        # (n, top)
        Hf, Wf, P = self.Hf, self.Wf, pad
        x = torch.from_numpy(np.ascontiguousarray(play)).to(self.dev).permute(2, 0, 1).float() / 255
        x = x - x.mean()
        xp = F.pad(x[None], (P, Wf + P, P, Hf + P), mode="replicate")[0]
        wins = torch.stack([xp[:, y:y + Hf + 2 * P, x_:x_ + Wf + 2 * P] for x_, y in zip(xs, ys)])  # (n,3,..)
        hw = (2 * P + 1, 2 * P + 1)
        flat = wins.reshape(1, n * 3, Hf + 2 * P, Wf + 2 * P)
        cross = F.conv2d(flat, self.Tf[kt].reshape(n * top, 3, Hf, Wf), groups=n).reshape(n, top, *hw)
        m3 = self.Mf[kt][:, None].expand(n, 3, top, 1, Hf, Wf).reshape(n * 3 * top, 1, Hf, Wf)
        s1 = F.conv2d(flat, m3, groups=n * 3).reshape(n, 3, top, *hw)
        s2 = F.conv2d(flat * flat, m3, groups=n * 3).reshape(n, 3, top, *hw)
        nk = self.nf[kt][:, None, :, None, None]
        var = (s2 - s1 * s1 / nk).sum(1)                                                     # (n, top, ..)
        r = cross / torch.sqrt(var.clamp_min(1e-6) * self.tnf[kt][:, :, None, None])
        r = torch.where(var < 3 * nk[:, 0] * (self.flat_std / 255) ** 2, torch.full_like(r, -1.0), r)
        v, idx = r.reshape(n, -1).max(dim=1)
        v, idx, ktl = v.tolist(), idx.tolist(), kt.tolist()
        out = []
        per = hw[0] * hw[1]
        for i in range(n):
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
