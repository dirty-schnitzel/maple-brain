"""Prototype (PLAN-loot.md, plan session; NOT on the live path): the WHOLE drop pass - vote + check - as ONE GPU
program of fixed sizes, so that it can be captured as a CUDA graph and replayed with one launch (the mob fit's stage 2
went 1.5 -> 0.56 ms that way), and launched without waiting: the tick reads the result when it needs it.

Fixed sizes instead of data-dependent ones (no sync inside):
  NF     feature slots a frame (2x2 blocks of item colours the scene does not explain); more than NF: the first NF in
         scan order (reported: `feat` in the output)
  MAXP   places per feature key; the table keeps only keys in <= MAXP places (items: p50 1 place per key)
  NC     candidate cells checked (the best by exclusive votes)
Steps (= perception/vote.py's vote + dropfast's check, same numbers where the sizes allow):
  ids (LUT) -> feature mask -> compaction into NF slots (cumsum + scatter) -> keys -> table (searchsorted) -> NF x MAXP
  cells (invalid = a sentinel) -> sort -> runs -> votes per run -> exclusive votes -> top NC -> the check's gathers
  and counts -> one uint8 tensor.
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import PLAY_H, SW  # noqa: E402
from dropvote import Drop  # noqa: E402
from dropfast import FastFinder, M  # noqa: E402


class GraphFinder(FastFinder):
    def __init__(self, *a, NF: int = 32768, MAXP: int = 4, NC: int = 64, **k):
        super().__init__(*a, **k)
        torch, v = self.torch, self.voter
        self.NF, self.MAXP, self.NC = NF, MAXP, NC
        cnt = v.count.cpu().numpy()
        start = v.start.cpu().numpy()
        off = v.off.cpu().numpy().astype(np.int64)
        uk = v.uk.cpu().numpy().astype(np.int64)
        keep = cnt <= MAXP
        self.kept_entries = int(cnt[keep].sum())
        self.all_entries = int(cnt.sum())
        self.SENT = SENT = np.int64(1) << 62
        places = np.full((int(keep.sum()), MAXP), SENT, np.int64)
        st, cn = start[keep], cnt[keep]
        for j in range(MAXP):
            m = cn > j
            places[m, j] = off[st[m] + j]
        self.g_uk = torch.from_numpy(uk[keep]).to(self.dev)
        self.g_places = torch.from_numpy(places).to(self.dev)
        self.W1 = SW - 1
        n = (PLAY_H - 1) * self.W1
        self.g_arange = torch.arange(n, device=self.dev)
        self.g_slot = torch.arange(NF, device=self.dev)
        self.NV = NF * MAXP
        self.g_ones = torch.ones(self.NV, dtype=torch.long, device=self.dev)
        # static inputs
        self.s_f = torch.zeros((PLAY_H, SW, 3), dtype=torch.uint8, device=self.dev)
        self.s_vote = torch.zeros((PLAY_H, SW), dtype=torch.bool, device=self.dev)     # may vote
        self.s_expl = torch.zeros((PLAY_H, SW), dtype=torch.bool, device=self.dev)     # the scene explains it
        self.s_known = torch.zeros((PLAY_H, SW), dtype=torch.bool, device=self.dev)
        self.graph = None
        self.dr_np = self.pics_np[..., 3] > 0

    # ---- the program (no sync, fixed shapes)
    def core(self):
        torch = self.torch
        f, NF, MAXP, NC = self.s_f, self.NF, self.MAXP, self.NC
        v = self.voter
        fi = f.int()
        ids = v.lut[fi[..., 0] | (fi[..., 1] << 8) | (fi[..., 2] << 16)]
        ids = torch.where(self.s_vote, ids, torch.zeros_like(ids))
        a, b, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
        mn = torch.minimum(torch.minimum(a, b), torch.minimum(c, d))
        mx = torch.maximum(torch.maximum(a, b), torch.maximum(c, d))
        ok = ((mn > 0) & (mx != mn)).view(-1)
        pos = torch.cumsum(ok.to(torch.int32), 0) - 1
        nfeat = pos[-1] + 1
        tgt = torch.where(ok & (pos < NF), pos, torch.full_like(pos, NF)).long()
        buf = torch.zeros(NF + 1, dtype=torch.long, device=self.dev).scatter_(0, tgt, self.g_arange)
        p = buf[:NF]
        valid = self.g_slot < nfeat
        r = v.radix
        key = ((a.reshape(-1)[p].long() * r + b.reshape(-1)[p]) * r + c.reshape(-1)[p]) * r + d.reshape(-1)[p]
        j = torch.searchsorted(self.g_uk, key).clamp_(max=len(self.g_uk) - 1)
        hit = (self.g_uk[j] == key) & valid
        pix = (p // self.W1) * v.WW + p % self.W1
        cellm = self.g_places[j] + pix[:, None]
        cellm = torch.where(hit[:, None] & (self.g_places[j] < self.SENT), cellm, torch.full_like(cellm, int(self.SENT)))
        cs, perm = torch.sort(cellm.view(-1))
        first = torch.ones_like(cs)
        first[1:] = (cs[1:] != cs[:-1]).long()
        rid = torch.cumsum(first, 0) - 1
        isv = (cs < self.SENT).long()
        zero = torch.zeros(self.NV, dtype=torch.long, device=self.dev)
        n_run = zero.index_add(0, rid, isv)
        nv = n_run[rid] * isv                                            # each vote: its cell's votes
        inv = torch.empty_like(perm).scatter_(0, perm, torch.arange(self.NV, device=self.dev))
        nv_o = nv[inv].view(NF, MAXP)                                    # back in (feature, place) order
        best = nv_o.amax(dim=1, keepdim=True)
        win = ((nv_o == best) & (nv_o > 0)).view(-1).long()
        ex_run = zero.index_add(0, rid[inv], win)
        top, at = torch.topk(ex_run, NC)
        cell_run = zero.scatter(0, rid, cs)
        cells = cell_run[at]
        g = (cells // v.CW).clamp_(0, len(self.poses) - 1)
        rem = cells % v.CW
        fx, fy = rem % v.WW - v.pad, rem // v.WW - v.pad
        # the check (dropfast.check_gpu, tensors in)
        K = self.K
        oxy = self.g_oxy[g]
        x0, y0 = fx - oxy[:, 0] - M, fy - oxy[:, 1] - M
        R, Q = y0[:, None] + self.ar[None], x0[:, None] + self.ar[None]
        okb = ((R >= 0) & (R < PLAY_H))[:, :, None] & ((Q >= 0) & (Q < SW))[:, None, :]
        Rc, Qc = R.clamp(0, PLAY_H - 1)[:, :, None], Q.clamp(0, SW - 1)[:, None, :]
        I = f[Rc, Qc]
        expl = self.s_expl[Rc, Qc] & okb
        kn = self.s_known[Rc, Qc] & okb
        op = self.op[g] & okb
        seen = op & ((I.to(torch.int16) - self.col[g]).abs().amax(dim=3) <= self.tol)
        absent = op & ~seen & expl
        ring = self.inbox[g] & ~self.dr[g] & okb
        fm = self.fm[g]
        fs = fm & seen[:, :-1, :-1] & seen[:, :-1, 1:] & seen[:, 1:, :-1] & seen[:, 1:, 1:]
        fon = fm & okb[:, :-1, :-1] & okb[:, 1:, 1:]
        cnt = torch.stack([op.flatten(1).sum(1), seen.flatten(1).sum(1), absent.flatten(1).sum(1), fon.flatten(1).sum(1),
                           fs.flatten(1).sum(1), (ring & kn).flatten(1).sum(1), (ring & expl).flatten(1).sum(1),
                           ring.flatten(1).sum(1), g, fx, fy, top, nfeat.expand(NC).long()], 1).to(torch.int32)
        bits = seen.to(torch.uint8) | (op.to(torch.uint8) << 1) | ((ring & kn).to(torch.uint8) << 2) | \
            ((ring & expl).to(torch.uint8) << 3) | (okb.to(torch.uint8) << 4)
        return torch.cat([bits.flatten(), cnt.contiguous().view(-1).view(torch.uint8)])

    def prepare(self, side_stream: bool = False):
        """Capture the pass as a CUDA graph. `side_stream`: it replays on its own CUDA stream, so its GPU work runs
        beside the main stream's (the mob fit's small launches leave the GPU idle in between) instead of in front of it."""
        torch = self.torch
        self.g_oxy = torch.from_numpy(self.oxy.astype(np.int64)).to(self.dev)
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3):
                self.core()
        torch.cuda.current_stream().wait_stream(s)
        self.side = torch.cuda.Stream() if side_stream else None
        self.graph = torch.cuda.CUDAGraph()
        if self.side is not None:
            self.side.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(self.side):
                with torch.cuda.graph(self.graph):
                    self.out = self.core()
            torch.cuda.current_stream().wait_stream(self.side)
        else:
            with torch.cuda.graph(self.graph):
                self.out = self.core()

    def launch(self, frame, exp, known, mask, expl=None):
        """Copy the tick's inputs into the static buffers and start the pass (no wait). `expl`: known & the frame
        within tol of the expected scene, if the caller has it (the mob fit computes it)."""
        torch = self.torch
        self.s_f.copy_(frame[:PLAY_H])
        ex = expl if expl is not None else known & ((frame[:PLAY_H].float() - exp).abs().amax(dim=2) <= self.tol)
        self.s_expl.copy_(ex)
        self.s_known.copy_(known)
        self.s_vote.copy_(~ex & mask)
        if self.graph is not None:
            if getattr(self, "side", None) is not None:
                self.side.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(self.side):
                    self.graph.replay()
            else:
                self.graph.replay()
            return self.out
        return self.core()

    def fetch(self, out):
        """The pass' result -> [Drop] (the pick on the CPU, as dropfast.find_fast)."""
        t0 = time.perf_counter()
        if getattr(self, "side", None) is not None and self.graph is not None:
            self.torch.cuda.current_stream().wait_stream(self.side)
        o = out.cpu().numpy()
        t1 = time.perf_counter()
        NC, K = self.NC, self.K
        bits = o[:NC * K * K].reshape(NC, K, K)
        cnt = o[NC * K * K:].view(np.int32).reshape(NC, 13)
        g, fx, fy, votes = cnt[:, 8], cnt[:, 9], cnt[:, 10], cnt[:, 11]
        drops = []
        if getattr(self, "_taken", None) is None:           # kept between frames; only the used boxes are cleared
            self._taken = np.zeros((PLAY_H + 2 * K, SW + 2 * K), bool)
            self._drawn = np.zeros((PLAY_H + 2 * K, SW + 2 * K), bool)
            self._used = []
        taken, drawn = self._taken, self._drawn
        for sl in self._used:
            taken[sl] = False
            drawn[sl] = False
        self._used = used = []
        order = np.argsort(-cnt[:, 1], kind="stable")
        order = order[(votes[order] >= self.cand_votes) & (cnt[order, 1] >= self.min_seen)]
        for i in order:
            if votes[i] < self.cand_votes:
                continue
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
            rk, re = (bits[i] & 4).astype(bool), (bits[i] & 8).astype(bool)
            ringm = self.ring_np[gi] & ((bits[i] & 16) > 0)
            extra = {"n_cd": int((op & ~seen & dk).sum()), "ring_n": int(cnt[i, 5]) + int((ringm & dk & ~rk).sum()),
                     "ring_e": int(cnt[i, 6]) + int((ringm & dk & ~re).sum()), "ring": int(cnt[i, 7])}
            taken[sl] |= px
            drawn[sl] |= self.dr_np[gi]
            used.append(sl)
            it, fr, org = self.meta[gi]
            bx, by = int(fx[i]) - int(self.oxy[gi, 0]), int(fy[i]) - int(self.oxy[gi, 1])
            d = Drop(it, fr, (bx, by, int(self.wh[gi, 0]), int(self.wh[gi, 1])), (bx + org[0], by + org[1]), n_op, n2,
                     n_abs, int(votes[i]), int(cnt[i, 3]), int(cnt[i, 4]))
            d.extra = extra
            drops.append(d)
        self.ms_g = {"fetch": (t1 - t0) * 1000, "pick": (time.perf_counter() - t1) * 1000, "feat": int(cnt[0, 12]),
                     "cands": int((votes >= self.cand_votes).sum())}
        return drops
