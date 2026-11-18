"""Prototype (PLAN-loot.md, plan session; NOT on the live path): the drop finder's CHECK on the GPU - what the
product's stage 2 for drops would cost. Same rule and numbers as dropvote.DropFinder.find (asserted by exp_time.py).

One gather per source of all candidate boxes (the picture's box + a ring of M px), ~25 small ops, one transfer back:
per candidate the counts (opaque on screen, SEEN, ABSENT, features, features SEEN, ring known / explained / all) and
the SEEN bits; the greedy pick (taken pixels, cover by an accepted drop) on the CPU as in the mob fit.
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import PLAY_H, SW  # noqa: E402
from dropvote import Drop, DropFinder  # noqa: E402

M = 2


class FastFinder(DropFinder):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        torch = self.torch
        P = self.poses
        self.K = K = max(max(p.pic.shape[:2]) for p in P) + 2 * M
        pics = np.zeros((len(P), K, K, 4), np.uint8)
        fm = np.zeros((len(P), K - 1, K - 1), bool)
        inbox = np.zeros((len(P), K, K), bool)              # the picture's box + the ring
        self.wh = np.array([[p.pic.shape[1], p.pic.shape[0]] for p in P])
        self.oxy = np.array([[p.ox, p.oy] for p in P])
        for i, p in enumerate(P):
            h, w = p.pic.shape[:2]
            pics[i, M:M + h, M:M + w] = p.pic
            fm[i, M:M + h - 1, M:M + w - 1] = self.fmask[i]
            inbox[i, :h + 2 * M, :w + 2 * M] = True
        self.pics_np = pics
        self.ring_np = inbox & (pics[..., 3] == 0)          # the ring of each picture, in its K x K box
        self.pics = torch.from_numpy(pics).to(self.dev)
        self.col = self.pics[..., :3].to(torch.int16)
        self.op = self.pics[..., 3] == 255
        self.dr = self.pics[..., 3] > 0
        self.fm = torch.from_numpy(fm).to(self.dev)
        self.inbox = torch.from_numpy(inbox).to(self.dev)
        self.ar = torch.arange(K, device=self.dev)

    def check_gpu(self, f, exp, known, g, fx, fy):
        """-> (bits (n, K, K) uint8: 1 = SEEN, 2 = opaque on screen; counts (n, 8) int32)."""
        torch = self.torch
        gt = torch.from_numpy(np.asarray(g, np.int64)).to(self.dev)
        x0 = torch.from_numpy(np.asarray(fx - self.oxy[g, 0] - M, np.int64)).to(self.dev)
        y0 = torch.from_numpy(np.asarray(fy - self.oxy[g, 1] - M, np.int64)).to(self.dev)
        R, Q = y0[:, None] + self.ar[None], x0[:, None] + self.ar[None]
        ok = ((R >= 0) & (R < PLAY_H))[:, :, None] & ((Q >= 0) & (Q < SW))[:, None, :]
        Rc, Qc = R.clamp(0, PLAY_H - 1)[:, :, None], Q.clamp(0, SW - 1)[:, None, :]
        I = f[Rc, Qc]                                                   # (n, K, K, 3) uint8
        E = exp[Rc, Qc]
        kn = known[Rc, Qc] & ok
        op = self.op[gt] & ok
        seen = op & ((I.to(torch.int16) - self.col[gt]).abs().amax(dim=3) <= self.tol)
        expl = kn & ((I.float() - E).abs().amax(dim=3) <= self.tol)
        absent = op & ~seen & expl
        ring = self.inbox[gt] & ~self.dr[gt] & ok
        fm = self.fm[gt]
        fs = fm & seen[:, :-1, :-1] & seen[:, :-1, 1:] & seen[:, 1:, :-1] & seen[:, 1:, 1:]
        fon = fm & ok[:, :-1, :-1] & ok[:, 1:, 1:]
        cnt = torch.stack([op.flatten(1).sum(1), seen.flatten(1).sum(1), absent.flatten(1).sum(1), fon.flatten(1).sum(1),
                           fs.flatten(1).sum(1), (ring & kn).flatten(1).sum(1), (ring & expl).flatten(1).sum(1),
                           ring.flatten(1).sum(1)], 1).to(torch.int32)
        bits = seen.to(torch.uint8) | (op.to(torch.uint8) << 1) | ((ring & kn).to(torch.uint8) << 2) | \
            ((ring & expl).to(torch.uint8) << 3) | (ok.to(torch.uint8) << 4)
        out = torch.cat([bits.flatten(), cnt.flatten().view(torch.uint8)]).cpu().numpy()      # one transfer
        n, K = len(g), self.K
        return out[:n * K * K].reshape(n, K, K), out[n * K * K:].view(np.int32).reshape(n, 8)

    def find_fast(self, frame, exp, known, mask=None):
        torch = self.torch
        t0 = time.perf_counter()
        f = frame[:PLAY_H]
        ids = self.voter.ids(f, exp, known, self.tol)
        if mask is not None:
            ids = torch.where(mask, ids, torch.zeros_like(ids))
        g, fx, fy, nv, ex, vc = self.voter.cells(ids, self.cand_votes)
        t1 = time.perf_counter()
        drops = []
        t2 = t1
        if len(g):
            bits, cnt = self.check_gpu(f, exp, known, g, fx, fy)
            t2 = time.perf_counter()
            K = self.K
            taken = np.zeros((PLAY_H + 2 * K, SW + 2 * K), bool)
            drawn = np.zeros((PLAY_H + 2 * K, SW + 2 * K), bool)
            for i in np.argsort(-cnt[:, 1], kind="stable"):
                n_op, ns, n_abs = int(cnt[i, 0]), int(cnt[i, 1]), int(cnt[i, 2])
                if ns < self.min_seen or ns < self.seen_min * n_op or n_abs > self.absent_max * n_op:
                    continue
                gi = int(g[i])
                x0, y0 = int(fx[i]) - self.oxy[gi, 0] - M + K, int(fy[i]) - self.oxy[gi, 1] - M + K
                sl = (slice(y0, y0 + K), slice(x0, x0 + K))
                seen, op = (bits[i] & 1).astype(bool), (bits[i] & 2).astype(bool)
                px = seen & ~taken[sl]
                n2 = int(px.sum())
                if n2 < self.min_seen or n2 < self.seen_min * n_op:
                    continue
                dk = drawn[sl]
                n_cd = int((op & ~seen & dk).sum())
                rk, re = (bits[i] & 4).astype(bool), (bits[i] & 8).astype(bool)
                ringm = self.ring_np[gi] & (((bits[i] & 16) > 0))      # the ring's pixels on screen
                extra = {"n_cd": n_cd, "ring_n": int(cnt[i, 5]) + int((ringm & dk & ~rk).sum()),
                         "ring_e": int(cnt[i, 6]) + int((ringm & dk & ~re).sum()), "ring": int(cnt[i, 7])}
                taken[sl] |= px
                drawn[sl] |= self.pics_np[gi, ..., 3] > 0
                it, fr, org = self.meta[gi]
                w, h = self.wh[gi]
                bx, by = int(fx[i]) - self.oxy[gi, 0], int(fy[i]) - self.oxy[gi, 1]
                bx, by = int(bx), int(by)
                d = Drop(it, fr, (bx, by, int(w), int(h)), (bx + org[0], by + org[1]), n_op, n2, n_abs, int(ex[i]),
                         int(cnt[i, 3]), int(cnt[i, 4]))
                d.extra = extra
                drops.append(d)
        t3 = time.perf_counter()
        self.ms = {"vote": (t1 - t0) * 1000, "check": (t2 - t1) * 1000, "pick": (t3 - t2) * 1000,
                   "all": (t3 - t0) * 1000, "cands": len(g), "feat": vc["feat"], "votes": vc["votes"]}
        return drops
