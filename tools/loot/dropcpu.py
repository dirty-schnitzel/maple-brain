"""Prototype (PLAN-loot.md, plan session; NOT on the live path): the drop finder on the CPU, for a READER THREAD
beside the GPU work (as the Perceiver's tag / HUD readers, step 2.9b) - no GPU launch, no sync.

Input: the frame (numpy, the tick has it from the start) + ONE uint8 mask D's GPU pass already makes and downloads
(scene.Scene.diff): bit 0 = the pixel may vote (the scene does not explain it, or unknown scenery; world only),
bit 1 = the scene explains it (known and within tol), bit 2 = known scenery.
The vote = perception/vote.py's, in numpy, only on the bit-0 pixels (a few % of the frame): palette id per pixel,
2x2 id blocks, the table's cells, exclusive votes. The check + pick = dropvote.DropFinder's (numpy), ABSENT / the
ring read from bits 1 / 2 instead of the expected picture. Same drops as the GPU prototype (exp_time_cpu.py checks).
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import PLAY_H, SW  # noqa: E402
from dropvote import Drop, DropFinder  # noqa: E402

M = 2


class CpuFinder(DropFinder):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        v = self.voter
        self.lut = v.lut.cpu().numpy()                      # (1 << 24) int16
        self.uk = v.uk.cpu().numpy().astype(np.int64)
        self.start = v.start.cpu().numpy()
        self.count = v.count.cpu().numpy()
        self.off = v.off.cpu().numpy().astype(np.int64)
        self.radix, self.WW, self.CW, self.pad = v.radix, v.WW, v.CW, v.pad
        P = self.poses
        self.K = K = max(max(p.pic.shape[:2]) for p in P) + 2 * M
        self.pk = np.zeros((len(P), K, K, 4), np.uint8)     # each picture in a K x K box, its corner at (M, M)
        self.inbox = np.zeros((len(P), K, K), bool)
        self.fm = np.zeros((len(P), K - 1, K - 1), bool)
        self.wh = np.array([[p.pic.shape[1], p.pic.shape[0]] for p in P])
        self.oxy = np.array([[p.ox, p.oy] for p in P])
        for i, p in enumerate(P):
            h, w = p.pic.shape[:2]
            self.pk[i, M:M + h, M:M + w] = p.pic
            self.inbox[i, :h + 2 * M, :w + 2 * M] = True
            self.fm[i, M:M + h - 1, M:M + w - 1] = self.fmask[i]
        self.col = self.pk[..., :3].astype(np.int16)
        self.op = self.pk[..., 3] == 255
        self.dr = self.pk[..., 3] > 0
        self.ring = self.inbox & ~self.dr
        self.ar = np.arange(K)

    def vote(self, frame, dmask, tmin=None):
        """-> (g, feet x, feet y, exclusive votes) of the cells with >= tmin exclusive votes, best first."""
        tmin = self.cand_votes if tmin is None else tmin
        H, W = PLAY_H, SW
        idx = np.flatnonzero(dmask[:H].reshape(-1) & 1)                 # the pixels that may vote
        z = np.zeros(0, np.int64)
        if len(idx) == 0:
            return z, z, z, z, {"px": 0, "feat": 0, "votes": 0}
        px = frame[:H].reshape(-1, 3)[idx]
        k24 = px[:, 0].astype(np.int32) | (px[:, 1].astype(np.int32) << 8) | (px[:, 2].astype(np.int32) << 16)
        ids = np.zeros(H * W + W + 2, np.int16)                         # + a zero row: the last row's neighbours
        ids[idx] = self.lut[k24]
        a = ids[idx]
        keep = a > 0
        idx, a = idx[keep], a[keep]
        b, c, d = ids[idx + 1], ids[idx + W], ids[idx + W + 1]
        ok = (b > 0) & (c > 0) & (d > 0) & ~((a == b) & (a == c) & (a == d)) & (idx % W < W - 1)
        sel = idx[ok]
        r = self.radix
        key = ((a[ok].astype(np.int64) * r + b[ok]) * r + c[ok]) * r + d[ok]
        j = np.searchsorted(self.uk, key)
        j[j == len(self.uk)] = 0
        hit = self.uk[j] == key
        sel, j = sel[hit], j[hit]
        info = {"px": int(len(px)), "feat": int(ok.sum()), "votes": 0}
        if len(sel) == 0:
            return z, z, z, z, info
        cnt = self.count[j]
        total = int(cnt.sum())
        info["votes"] = total
        first = np.cumsum(cnt) - cnt
        src = np.repeat(np.arange(len(sel)), cnt)
        e = self.start[j][src] + (np.arange(total) - first[src])
        pix = (sel // W) * self.WW + sel % W
        cell = self.off[e] + pix[src]
        uc, inv, n_run = np.unique(cell, return_inverse=True, return_counts=True)
        nv = n_run[inv]                                                 # each vote: its cell's votes
        best = np.maximum.reduceat(nv, first)                           # per feature: its best cell's votes
        win = nv == best[src]
        ex = np.bincount(inv[win], minlength=len(uc))
        top = np.flatnonzero(ex >= tmin)
        top = top[np.argsort(-ex[top], kind="stable")][:256]
        cellv = uc[top]
        g, rem = cellv // self.CW, cellv % self.CW
        return g, rem % self.WW - self.pad, rem // self.WW - self.pad, ex[top], info

    def check(self, frame, dmask, g, fx, fy):
        """Per candidate: (SEEN bits (K, K), opaque-on-screen bits, counts) - vectorised over the candidates."""
        K = self.K
        x0 = fx - self.oxy[g, 0] - M
        y0 = fy - self.oxy[g, 1] - M
        R, Q = y0[:, None] + self.ar[None], x0[:, None] + self.ar[None]
        ok = ((R >= 0) & (R < PLAY_H))[:, :, None] & ((Q >= 0) & (Q < SW))[:, None, :]
        Rc, Qc = np.clip(R, 0, PLAY_H - 1)[:, :, None], np.clip(Q, 0, SW - 1)[:, None, :]
        I = frame[Rc, Qc]                                               # (n, K, K, 3)
        dm = dmask[Rc, Qc]
        op = self.op[g] & ok
        seen = op & (np.abs(I.astype(np.int16) - self.col[g]).max(axis=3) <= self.tol)
        expl = ((dm & 2) > 0) & ok
        kn = ((dm & 4) > 0) & ok
        absent = op & ~seen & expl
        ring = self.ring[g] & ok
        fm = self.fm[g]
        fs = fm & seen[:, :-1, :-1] & seen[:, :-1, 1:] & seen[:, 1:, :-1] & seen[:, 1:, 1:]
        fon = fm & ok[:, :-1, :-1] & ok[:, 1:, 1:]
        cnt = np.stack([op.sum((1, 2)), seen.sum((1, 2)), absent.sum((1, 2)), fon.sum((1, 2)), fs.sum((1, 2)),
                        (ring & kn).sum((1, 2)), (ring & expl).sum((1, 2)), ring.sum((1, 2))], 1)
        return seen, op, ring & kn, ring & expl, ring, cnt, x0, y0

    def find_cpu(self, frame, dmask, mob_taken=None):
        t0 = time.perf_counter()
        g, fx, fy, ex, info = self.vote(frame, dmask)
        t1 = time.perf_counter()
        drops = []
        if len(g):
            seen, op, rk, re, rg, cnt, x0, y0 = self.check(frame, dmask, g, fx, fy)
            K = self.K
            taken = np.zeros((PLAY_H + 2 * K, SW + 2 * K), bool)
            drawn = np.zeros((PLAY_H + 2 * K, SW + 2 * K), bool)
            for i in np.argsort(-cnt[:, 1], kind="stable"):
                n_op, ns, n_abs = int(cnt[i, 0]), int(cnt[i, 1]), int(cnt[i, 2])
                if ns < self.min_seen or ns < self.seen_min * n_op or n_abs > self.absent_max * n_op:
                    continue
                gi = int(g[i])
                sl = (slice(int(y0[i]) + K, int(y0[i]) + 2 * K), slice(int(x0[i]) + K, int(x0[i]) + 2 * K))
                px = seen[i] & ~taken[sl]
                n2 = int(px.sum())
                if n2 < self.min_seen or n2 < self.seen_min * n_op:
                    continue
                dk = drawn[sl]
                extra = {"n_cd": int((op[i] & ~seen[i] & dk).sum()),
                         "ring_n": int(cnt[i, 5]) + int((rg[i] & dk & ~rk[i]).sum()),
                         "ring_e": int(cnt[i, 6]) + int((rg[i] & dk & ~re[i]).sum()), "ring": int(cnt[i, 7])}
                taken[sl] |= px
                drawn[sl] |= self.dr[gi]
                it, fr, org = self.meta[gi]
                bx, by = int(fx[i]) - int(self.oxy[gi, 0]), int(fy[i]) - int(self.oxy[gi, 1])
                d = Drop(it, fr, (bx, by, int(self.wh[gi, 0]), int(self.wh[gi, 1])), (bx + org[0], by + org[1]), n_op, n2,
                         n_abs, int(ex[i]), int(cnt[i, 3]), int(cnt[i, 4]))
                d.extra = extra
                drops.append(d)
        t2 = time.perf_counter()
        self.ms_cpu = {"vote": (t1 - t0) * 1000, "check": (t2 - t1) * 1000, "all": (t2 - t0) * 1000, "cands": len(g), **info}
        return drops
