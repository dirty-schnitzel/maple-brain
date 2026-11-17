"""Drops (PLAN-loot.md section 5 as AMENDED 2026-11-17; Session 3, in shadow: FrameFacts.drops, nothing reads them).

A resting drop is the item's `info/iconRaw` drawn 1:1 and opaque, so the mob fit's exact-colour vote finds it when its
"poses" are item pictures: every distinct picture of assets/mcw/items that can drop (not see-through = `weak`, not
cash-shop only = `cash`), anchored at its bottom-centre (= the drop's feet), in ONE table built once per process.
Reference: tools/loot/dropvote.py (eager); this is its fixed-size form (tools/loot/dropgraph.py) + the FRONT term.

Per tick (clean map, scene camera found):
  launch  (right after Scene.expected) copies the frame / expected / known / world mask / the front planes of the
          map's foothold layers at this camera into static buffers and replays ONE CUDA graph on its own stream:
            VOTE   palette id per pixel the scene does not explain -> 2x2 id features (first NF in scan order) ->
                   the table's (picture, feet) places: a key in <= MAXP places from the first table, one in more (up
                   to max_entries, as the reference) from the second via its own NF2 slots -> exclusive votes -> the
                   best NC cells
            CHECK  per cell, the picture against the frame: SEEN (|I - s| <= tol), ABSENT (not SEEN, the frame shows
                   the expected scene: one count without front and one per foothold layer's front plane - a pixel
                   under front scenery of the drop's layer is cover, not absence), the 2 px ring (box + 2 px minus
                   what the picture draws: known / explained), features fully SEEN
  fetch   (after the fit and the tracker) waits for that stream, downloads one small tensor and PICKS on the CPU:
          greedy by SEEN; an accepted drop's SEEN pixels are taken; the loose rule (>= min_seen SEEN px, SEEN >=
          seen_min of the opaque px on screen, ABSENT <= absent_max) -> section 8's facts + the kind:
            under   unseen pixels under an accepted drop     front  unseen, under front scenery of its layer
            mob     SEEN pixels the mob fit explained         ring   [explained, known] ring pixels; the fit's mobs
                                                                     and characters' body boxes count as both
            dy, fh, layer  box bottom - the foothold's y under its centre (lootlib's rule: the topmost foothold at /
                           below bottom - 14), its id and layer (None: nothing under it)
          kind REST = dy in -7..+5, u = 1 - (seen + absent + under + front) / n_op <= 0.2, mob < 0.5 seen, ring
          explained >= 0.1 of the known (< 60 known ring px: pass); else weak.
GPU memory ~0.3 GB; build ~1 s + capture once per process (runner._load_map).
"""
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .vote import PLAY_H, SW, Pose, Voter

M = 2                       # the ring: px around the picture's box
NCNT = 12                   # fixed count columns before the per-layer ABSENT counts
NL = 8                      # front-plane slots (foothold layers 0..7 at most)


@dataclass
class DropConfig:
    tol: int = 4                # levels: native pixels are exact (+-4)
    cand_votes: int = 16        # exclusive votes a cell needs to be checked
    min_seen: int = 40          # the loose rule: SEEN px
    seen_min: float = 0.25      # ... SEEN share of the opaque px on screen
    absent_max: float = 0.15    # ... ABSENT share
    max_entries: int = 64       # the Voter's table (as the reference); the graph keeps keys in <= MAXP places
    NF: int = 49152             # feature slots a frame (more: the last ones in scan order are dropped; ms["feat"])
    MAXP: int = 8               # places per feature key in the graph's first table
    NF2: int = 4096             # slots for the features whose key is in more places (all of them: the second table;
                                # more: the last ones in scan order are dropped; ms["feat2"])
    NC: int = 64                # cells checked a frame (the best by exclusive votes)
    u_max: float = 0.2          # REST: unexplained cover
    mob_max: float = 0.5        # REST: SEEN share the mob fit explained
    ring_min: float = 0.1       # REST: explained share of the known ring px (the user, 2026-11-17)
    ring_known_min: int = 60    # ... fewer known ring px: pass
    dy_lo: int = -7             # REST: box bottom - foothold y
    dy_hi: int = 5
    side_stream: bool = True    # the graph on its own CUDA stream (overlaps the fit's launch gaps)


def kind_of(d: dict, c: DropConfig | None = None) -> str:
    """'rest' / 'weak' of one sighting's facts (section 5 as amended: no AIR kind, a ring bar on REST)."""
    c = c or DropConfig()
    if d["dy"] is None or not c.dy_lo <= d["dy"] <= c.dy_hi:
        return "weak"
    u = 1 - (d["seen"] + d["absent"] + d["under"] + d["front"]) / max(1, d["n_op"])
    re, rn = d["ring"]
    if u > c.u_max or d["mob"] >= c.mob_max * max(1, d["seen"]) or (rn >= c.ring_known_min and re / rn < c.ring_min):
        return "weak"
    return "rest"


class Footholds:
    """A map's footholds (map.json): `under(mx, my)` -> (y, layer, id) of the topmost foothold at / below map
    (mx, my - 14) (a drop's bottom bobs a few px around its foothold), or None. Same rule as tools/loot/lootlib.py
    (known: on stairs a step 13 px above can win - Session 1's open point, unchanged)."""

    def __init__(self, map_json: dict):
        rows = []
        for k, f in (map_json.get("footholds") or {}).items():
            if f["x1"] == f["x2"]:
                continue
            a = (f["x1"], f["y1"], f["x2"], f["y2"]) if f["x1"] < f["x2"] else (f["x2"], f["y2"], f["x1"], f["y1"])
            rows.append(a + (int(f.get("layerId", 0)), int(k)))
        self.fh = np.array(rows, float).reshape(-1, 6)

    def under_many(self, mx, my):
        """Vectorised `under`: arrays (y, layer, id, ok)."""
        F = self.fh
        mx, my = np.asarray(mx, float)[:, None], np.asarray(my, float)[:, None]
        on = (F[None, :, 0] <= mx) & (F[None, :, 2] >= mx)
        with np.errstate(invalid="ignore", divide="ignore"):
            ya = F[None, :, 1] + (mx - F[None, :, 0]) * (F[None, :, 3] - F[None, :, 1]) / (F[None, :, 2] - F[None, :, 0])
        below = on & (ya >= my - 14)
        ok = below.any(axis=1)
        ym = np.where(below, ya, np.inf)
        j = ym.argmin(axis=1) if len(F) else np.zeros(len(mx), int)
        y = ym[np.arange(len(mx)), j] if len(F) else np.zeros(len(mx))
        return y, F[j, 4].astype(int) if len(F) else j, F[j, 5].astype(int) if len(F) else j, ok

    def under(self, mx, my):
        y, L, i, ok = self.under_many([mx], [my])
        return (float(y[0]), int(L[0]), int(i[0])) if ok[0] else None


def _rect_win(boxes, y0: int, x0: int, K: int) -> np.ndarray:
    """(K, K) bool: the screen boxes (x0, y0, x1, y1; clipped as a (PLAY_H, SW) plane would) inside the window."""
    out = np.zeros((K, K), bool)
    for b in boxes:
        bx0, by0 = max(0, int(b[0])), max(0, int(b[1]))
        bx1, by1 = min(SW, max(0, int(b[2]))), min(PLAY_H, max(0, int(b[3])))
        a0, a1 = max(bx0, x0), min(bx1, x0 + K)
        r0, r1 = max(by0, y0), min(by1, y0 + K)
        if a1 > a0 and r1 > r0:
            out[r0 - y0:r1 - y0, a0 - x0:a1 - x0] = True
    return out


def _plane_win(plane, y0: int, x0: int, K: int) -> np.ndarray:
    """(K, K) bool window of a (PLAY_H, SW) plane at screen (x0, y0), zero outside."""
    out = np.zeros((K, K), bool)
    a0, a1 = max(0, x0), min(plane.shape[1], x0 + K)
    r0, r1 = max(0, y0), min(plane.shape[0], y0 + K)
    if a1 > a0 and r1 > r0:
        out[r0 - y0:r1 - y0, a0 - x0:a1 - x0] = plane[r0:r1, a0:a1]
    return out


class _MapDrops:
    """What the pick needs of one map: footholds, the front planes (>= 128 alpha) stacked by slot, layer -> slot."""

    def __init__(self, map_id: int, scene, assets: Path, torch):
        mj = json.loads((Path(assets) / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        self.fh = Footholds(mj)
        self.slot_of, self.planes, self.x0, self.y0 = {}, None, 0, 0
        if scene is not None and scene.layers:
            Ls = sorted(scene.layers)[:NL]
            self.slot_of = {L: i for i, L in enumerate(Ls)}
            self.planes = torch.stack([scene.layers[L] >= 128 for L in Ls])     # (nl, canvas h, canvas w) bool
            self.x0, self.y0 = scene.x0, scene.y0


class DropFinder:
    def __init__(self, items=None, device=None, cfg: DropConfig | None = None, assets: Path | None = None):
        """`items`: gamedata.load_items() (default: assets/mcw/items). Built once per process (~1 s); `warm`
        captures the graph (needs CUDA)."""
        import torch
        from .. import gamedata
        self.torch, self.cfg = torch, cfg or DropConfig()
        self.assets = Path(assets or gamedata.ROOT)
        t0 = time.perf_counter()
        self.items = items or gamedata.load_items(self.assets)
        poses, self.meta = [], []
        for g, pic in enumerate(self.items.pics):
            if self.items.weak[g] or self.items.cash[g]:
                continue
            it, fr = int(self.items.item[g]), int(self.items.f[g])
            poses.append(Pose(it, "raw" if it < 9000000 else f"f{fr}", "left", pic.shape[1] // 2, pic.shape[0], pic))
            self.meta.append((it, fr))
        self.poses = poses
        c = self.cfg
        v = self.voter = Voter(poses, c.max_entries, device, max_cells=256, tints={}, fades=False)
        self.dev = v.dev
        dev = self.dev
        # the pictures in K x K boxes (picture at (M, M)): colours, opaque, drawn, features, box + ring
        self.K = K = max(max(p.pic.shape[:2]) for p in poses) + 2 * M
        G = len(poses)
        pics = np.zeros((G, K, K, 4), np.uint8)
        fm = np.zeros((G, K - 1, K - 1), bool)
        inbox = np.zeros((G, K, K), bool)
        for i, p in enumerate(poses):
            h, w = p.pic.shape[:2]
            pics[i, M:M + h, M:M + w] = p.pic
            k = np.where(p.pic[..., 3] == 255, p.pic[..., 0].astype(np.int64) | (p.pic[..., 1].astype(np.int64) << 8)
                         | (p.pic[..., 2].astype(np.int64) << 16), -1)
            a, b, cc, d = k[:-1, :-1], k[:-1, 1:], k[1:, :-1], k[1:, 1:]
            fm[i, M:M + h - 1, M:M + w - 1] = (a >= 0) & (b >= 0) & (cc >= 0) & (d >= 0) & ~((a == b) & (a == cc) & (a == d))
            inbox[i, :h + 2 * M, :w + 2 * M] = True
        self.wh = np.array([[p.pic.shape[1], p.pic.shape[0]] for p in poses])
        self.oxy = np.array([[p.ox, p.oy] for p in poses])
        self.dr_np = pics[..., 3] > 0
        T = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(dev)  # noqa: E731
        self.col = T(pics[..., :3]).to(torch.int16)
        self.op = T(pics[..., 3] == 255)
        self.dr = T(self.dr_np)
        self.fm = T(fm)
        self.inbox = T(inbox)
        self.g_oxy = T(self.oxy.astype(np.int64))
        self.ar = torch.arange(K, device=dev)
        # the graph's tables: every key of the reference's (<= max_entries places), one row of MAXP places each; a key
        # in more places has an empty row there and its full row (MAXP2 = its most places) in a second table, voted
        # by a second, smaller pool of feature slots (NF2). The plan's "keys in <= 8 places only" left Tobi / Mokbi
        # Throwing Stars 3 votable features of 54 / 44 (4 pictures unfindable alone, p1 26 a picture); cutting
        # those keys' rows to 8 places biased near-twin pictures (Black Gomushin ok, a hat read as its twin)
        cnt, start = v.count.cpu().numpy(), v.start.cpu().numpy()
        off, uk = v.off.cpu().numpy().astype(np.int64), v.uk.cpu().numpy().astype(np.int64)
        full = cnt <= c.MAXP
        self.SENT = SENT = np.int64(1) << 62
        places = np.full((len(uk), c.MAXP), SENT, np.int64)
        for j in range(c.MAXP):
            m = full & (cnt > j)
            places[m, j] = off[start[m] + j]
        cut = np.flatnonzero(~full)
        self.MAXP2 = int(cnt[cut].max()) if len(cut) else 1
        places2 = np.full((max(1, len(cut)), self.MAXP2), SENT, np.int64)
        for r, k in enumerate(cut):
            places2[r, :cnt[k]] = off[start[k]:start[k] + cnt[k]]
        cut_row = np.full(len(uk), -1, np.int64)
        cut_row[cut] = np.arange(len(cut))
        self.table = {"entries": int(cnt.sum()), "full": int(cnt[full].sum()), "keys": len(uk),
                      "cut": len(cut), "colours": v.n_colors}
        self.g_uk, self.g_places, self.g_places2, self.g_cut = T(uk), T(places), T(places2), T(cut_row)
        v.off = v.uk = v.start = v.count = None                         # the eager vote's table: not used here
        self.W1 = SW - 1
        self.g_arange = torch.arange((PLAY_H - 1) * self.W1, device=dev)
        self.g_slot = torch.arange(c.NF, device=dev)
        self.g_slot2 = torch.arange(c.NF2, device=dev)
        self.NV = c.NF * c.MAXP + c.NF2 * self.MAXP2
        self.l_w = T((1 << np.arange(NL)).astype(np.uint8))[:, None, None, None]
        # static inputs of the graph
        self.s_f = torch.zeros((PLAY_H, SW, 3), dtype=torch.uint8, device=dev)
        self.s_exp = torch.zeros((PLAY_H, SW, 3), dtype=torch.float32, device=dev)
        self.s_known = torch.zeros((PLAY_H, SW), dtype=torch.bool, device=dev)
        self.s_ui = torch.zeros((PLAY_H, SW), dtype=torch.bool, device=dev)
        self.s_front = torch.zeros((NL, PLAY_H, SW), dtype=torch.bool, device=dev)
        self.graph = self.side = self._out = None
        self.maps, self.map = {}, None
        self.slot_of, self._n_front = {}, 0
        self.build_s = time.perf_counter() - t0
        self.ms = {}

    def describe(self) -> str:
        t = self.table
        return (f"drops: {len(self.poses)} pictures, {t['colours']} colours, {t['keys']} keys / {t['entries']} places "
                f"({t['full']} in rows of <= {self.cfg.MAXP}; {t['cut']} keys in up to {self.MAXP2} places: the second "
                f"pool, {self.cfg.NF2} slots), built in {self.build_s:.1f} s")

    # ---- per map
    def set_map(self, map_id: int, scene=None):
        """The map's footholds and front planes (Scene.layers; None: no front term). Cached per map."""
        if map_id not in self.maps:
            self.maps[map_id] = _MapDrops(map_id, scene, self.assets, self.torch)
        self.map = self.maps[map_id]
        self.map_id = map_id

    # ---- the GPU program (fixed shapes, no sync: graph-capturable)
    def _core(self):
        torch, c, v = self.torch, self.cfg, self.voter
        NF, MAXP, NC, K = c.NF, c.MAXP, c.NC, self.K
        f = self.s_f
        close = (f.float() - self.s_exp).abs().amax(dim=2) <= c.tol    # the frame shows the expected scene
        expl = close & self.s_known
        fi = f.int()
        ids = v.lut[fi[..., 0] | (fi[..., 1] << 8) | (fi[..., 2] << 16)]
        ids = torch.where(~expl & self.s_ui, ids, torch.zeros_like(ids))
        a, b, cc, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
        mn = torch.minimum(torch.minimum(a, b), torch.minimum(cc, d))
        mx = torch.maximum(torch.maximum(a, b), torch.maximum(cc, d))
        ok = ((mn > 0) & (mx != mn)).view(-1)
        pos = torch.cumsum(ok.to(torch.int32), 0) - 1
        nfeat = pos[-1] + 1
        tgt = torch.where(ok & (pos < NF), pos, torch.full_like(pos, NF)).long()
        p = torch.zeros(NF + 1, dtype=torch.long, device=self.dev).scatter_(0, tgt, self.g_arange)[:NF]
        valid = self.g_slot < nfeat
        r = v.radix
        key = ((a.reshape(-1)[p].long() * r + b.reshape(-1)[p]) * r + cc.reshape(-1)[p]) * r + d.reshape(-1)[p]
        j = torch.searchsorted(self.g_uk, key).clamp_(max=len(self.g_uk) - 1)
        hit = (self.g_uk[j] == key) & valid
        pix = (p // self.W1) * v.WW + p % self.W1
        SENT = int(self.SENT)
        pl = self.g_places[j]
        cellm = torch.where(hit[:, None] & (pl < self.SENT), pl + pix[:, None], torch.full_like(pl, SENT))
        # the second pool: the features whose key is in more than MAXP places, with all of its places
        ci = self.g_cut[j]
        okc = hit & (ci >= 0)
        pos2 = torch.cumsum(okc.to(torch.int32), 0) - 1
        ncut = pos2[-1] + 1
        tgt2 = torch.where(okc & (pos2 < c.NF2), pos2, torch.full_like(pos2, c.NF2)).long()
        q = torch.zeros(c.NF2 + 1, dtype=torch.long, device=self.dev).scatter_(0, tgt2, self.g_slot)[:c.NF2]
        pl2 = self.g_places2[ci[q].clamp(min=0)]
        cell2 = torch.where((self.g_slot2 < ncut)[:, None] & (pl2 < self.SENT), pl2 + pix[q][:, None],
                            torch.full_like(pl2, SENT))
        cs, perm = torch.sort(torch.cat([cellm.view(-1), cell2.view(-1)]))
        first = torch.ones_like(cs)
        first[1:] = (cs[1:] != cs[:-1]).long()
        rid = torch.cumsum(first, 0) - 1
        isv = (cs < self.SENT).long()
        zero = torch.zeros(self.NV, dtype=torch.long, device=self.dev)
        nv = zero.index_add(0, rid, isv)[rid] * isv                     # each vote: its cell's votes
        inv = torch.empty_like(perm).scatter_(0, perm, torch.arange(self.NV, device=self.dev))
        nv_o = nv[inv]                                                  # back in (feature, place) order
        n1 = NF * MAXP
        wins = []
        for x in (nv_o[:n1].view(NF, MAXP), nv_o[n1:].view(c.NF2, self.MAXP2)):
            wins.append(((x == x.amax(dim=1, keepdim=True)) & (x > 0)).view(-1))   # exclusive: the feature's best
        ex_run = zero.index_add(0, rid[inv], torch.cat(wins).long())               # cell(s)
        top, at = torch.topk(ex_run, NC)
        cells = zero.scatter(0, rid, cs)[at]
        g = (cells // v.CW).clamp_(0, len(self.poses) - 1)
        rem = cells % v.CW
        fx, fy = rem % v.WW - v.pad, rem // v.WW - v.pad
        # the check: every cell's picture box + ring
        oxy = self.g_oxy[g]
        x0, y0 = fx - oxy[:, 0] - M, fy - oxy[:, 1] - M
        R, Q = y0[:, None] + self.ar[None], x0[:, None] + self.ar[None]
        okb = ((R >= 0) & (R < PLAY_H))[:, :, None] & ((Q >= 0) & (Q < SW))[:, None, :]
        Rc, Qc = R.clamp(0, PLAY_H - 1)[:, :, None], Q.clamp(0, SW - 1)[:, None, :]
        I = f[Rc, Qc]
        cl = close[Rc, Qc] & okb
        kn = self.s_known[Rc, Qc] & okb
        ex = cl & kn
        op = self.op[g] & okb
        seen = op & ((I.to(torch.int16) - self.col[g]).abs().amax(dim=3) <= c.tol)
        uns = op & ~seen
        absent = uns & cl
        fr = self.s_front[:, Rc, Qc]                                    # (NL, NC, K, K): front planes per slot
        abs_l = (absent[None] & ~fr).flatten(2).sum(2)                  # ABSENT if the drop is on that slot's layer
        frn_l = (uns[None] & fr).flatten(2).sum(2)                      # ... unseen under that layer's front
        frb = (fr.to(torch.uint8) * self.l_w).sum(0).to(torch.uint8)
        ring = self.inbox[g] & ~self.dr[g] & okb
        fm = self.fm[g]
        fs = fm & seen[:, :-1, :-1] & seen[:, :-1, 1:] & seen[:, 1:, :-1] & seen[:, 1:, 1:]
        cnt = torch.cat([torch.stack([op.flatten(1).sum(1), seen.flatten(1).sum(1), absent.flatten(1).sum(1),
                                      fs.flatten(1).sum(1), (ring & kn).flatten(1).sum(1),
                                      (ring & ex).flatten(1).sum(1), g, fx, fy, top, nfeat.expand(NC).long(),
                                      ncut.expand(NC).long()], 1),
                         abs_l.t(), frn_l.t()], 1).to(torch.int32)
        bits = seen.to(torch.uint8) | (op.to(torch.uint8) << 1) | ((ring & ~kn).to(torch.uint8) << 2) | \
            ((ring & ~ex).to(torch.uint8) << 3)                         # ring px not known / not explained (the
                                                                        # pick adds those drawn by drops, mobs, chars)
        return torch.cat([bits.flatten(), frb.flatten(), cnt.contiguous().view(-1).view(torch.uint8)])

    def warm(self):
        """Capture the pass as a CUDA graph (on its own stream when cfg.side_stream) and replay it once."""
        torch = self.torch
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3):
                self._core()
        torch.cuda.current_stream().wait_stream(s)
        self.side = torch.cuda.Stream() if self.cfg.side_stream else None
        self.graph = torch.cuda.CUDAGraph()
        st = self.side or torch.cuda.current_stream()
        st.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(st):
            with torch.cuda.graph(self.graph):
                self._out_s = self._core()
        torch.cuda.current_stream().wait_stream(st)
        self.graph.replay()
        torch.cuda.synchronize()

    # ---- per tick
    def _fronts(self, C, front):
        """The front planes at camera C into the slots (`front`: {layer: bool (PLAY_H, SW)} instead: tools)."""
        torch, sf = self.torch, self.s_front
        if front is not None:
            self.slot_of = {L: i for i, L in enumerate(sorted(front)[:NL])}
            sf.zero_()
            for L, i in self.slot_of.items():
                pl = front[L]
                sf[i].copy_(pl if torch.is_tensor(pl) else torch.from_numpy(np.ascontiguousarray(pl)))
            self._n_front = NL
            return
        mp = self.map
        self.slot_of = mp.slot_of if mp is not None else {}
        planes = mp.planes if mp is not None else None
        n = 0 if planes is None else planes.shape[0]
        if self._n_front > n:                                           # slots an earlier map / call filled
            sf[n:].zero_()
        self._n_front = n
        if n == 0:
            return
        ch, cw = planes.shape[1:]
        ax, ay = int(C[0]) - mp.x0, int(C[1]) - mp.y0
        y0, x0, y1, x1 = max(0, ay), max(0, ax), min(ch, ay + PLAY_H), min(cw, ax + SW)
        if y0 != ay or x0 != ax or y1 != ay + PLAY_H or x1 != ax + SW:
            sf[:n].zero_()                                              # the camera shows past the canvas
        if y1 > y0 and x1 > x0:
            sf[:n, y0 - ay:y1 - ay, x0 - ax:x1 - ax].copy_(planes[:, y0:y1, x0:x1])

    def launch(self, frame, C, exp, known, ui, front=None):
        """Start the pass (no wait). `frame`: uint8 BGR GPU tensor (>= PLAY_H rows); `C`: the scene camera; `exp`,
        `known`: Scene.expected(C); `ui`: bool (PLAY_H, SW) tensor, True = world (may show a drop); `front`: None =
        the map's planes (set_map) at C, or {layer: bool (PLAY_H, SW)} (tools / tests)."""
        torch = self.torch
        t0 = time.perf_counter()
        if self.graph is None:
            self.warm()
        main = torch.cuda.current_stream()
        st = self.side or main
        if self.side is not None:
            self.side.wait_stream(main)
        with torch.cuda.stream(st):
            self.s_f.copy_(frame[:PLAY_H])
            self.s_exp.copy_(exp)
            self.s_known.copy_(known)
            self.s_ui.copy_(ui)
            self._fronts(C, front)
            self.graph.replay()
        if self.side is not None:                                       # inputs read on the side stream: not
            for t in (frame, exp, known, ui):                           # reused by the allocator before it ran
                if torch.is_tensor(t) and t.is_cuda:
                    t.record_stream(self.side)
        self._out, self._C = self._out_s, (int(C[0]), int(C[1]))
        self._launch_ms = (time.perf_counter() - t0) * 1000

    def fetch(self, mob_taken=None, chars=(), mob_boxes=None) -> list | None:
        """The pass' result -> [section 8's facts + kind] (None: nothing launched). `mob_taken`: bool (PLAY_H, SW)
        numpy, the pixels the fit's accepted mobs explained (Fitter.taken's screen part); `chars`: characters' body
        boxes [(x0, y0, x1, y1)] on screen (ours + the players' tags); `mob_boxes`: the fit mobs' picture boxes [(x, y,
        w, h)] if known (only windows touching one look at `mob_taken`; None: every window does)."""
        if self._out is None:
            return None
        torch, c = self.torch, self.cfg
        t0 = time.perf_counter()
        if self.side is not None:
            torch.cuda.current_stream().wait_stream(self.side)
        o = self._out.cpu().numpy()
        self._out = None
        t1 = time.perf_counter()
        NC, K, C = c.NC, self.K, self._C
        n = NC * K * K
        bits = o[:n].reshape(NC, K, K)
        frb = o[n:2 * n].reshape(NC, K, K)
        cnt = o[2 * n:].view(np.int32).reshape(NC, NCNT + 2 * NL)
        n_op, ns, ab0, nfs, rkn, rex = (cnt[:, k] for k in range(6))
        g, fx, fy, votes = cnt[:, 6], cnt[:, 7], cnt[:, 8], cnt[:, 9]
        cand = np.flatnonzero((votes >= c.cand_votes) & (ns >= c.min_seen) & (ns >= c.seen_min * n_op))
        order = cand[np.argsort(-ns[cand], kind="stable")]
        # the accepted drops: (window x, y, its taken px or None = all its SEEN px, picture index, bits); an accepted
        # drop's taken / drawn pixels are only laid out for a later candidate whose window overlaps its window
        drops, acc = [], []
        if len(order):
            w, h = self.wh[g[order], 0], self.wh[g[order], 1]
            bx, by = fx[order] - w // 2, fy[order] - h
            uy, ul, uid, uok = self.map.fh.under_many(bx + w / 2 + C[0], by + h + C[1]) if self.map is not None \
                else (None, None, None, np.zeros(len(order), bool))
            for k, i in enumerate(order):
                lay = int(ul[k]) if uok[k] else None
                slot = self.slot_of.get(lay) if lay is not None else None
                n_abs = int(ab0[i]) if slot is None else int(cnt[i, NCNT + slot])
                if n_abs > c.absent_max * n_op[i]:
                    continue
                gi, x, y, ww, hh = int(g[i]), int(bx[k]), int(by[k]), int(w[k]), int(h[k])
                wx, wy = x - M, y - M                                   # the window (box + ring) on screen
                b = bits[i]
                seen = px = None
                # accepted drops whose picture box meets this box + ring: their taken / drawn pixels in the window
                near = [a for a in acc if a[0] < x + ww + M and a[0] + a[2] > wx and a[1] < y + hh + M and a[1] + a[3] > wy]
                if near:
                    tk, dk = np.zeros((K, K), bool), np.zeros((K, K), bool)
                    for ax, ay, _, _, apx, agi, ab in near:
                        dx, dy = ax - x, ay - y                         # both windows start M px before the box
                        r0, r1, c0, c1 = max(0, dy), min(K, K + dy), max(0, dx), min(K, K + dx)
                        src = (slice(r0 - dy, r1 - dy), slice(c0 - dx, c1 - dx))
                        tk[r0:r1, c0:c1] |= (apx if apx is not None else (ab & 1).view(bool))[src]
                        dk[r0:r1, c0:c1] |= self.dr_np[agi][src]
                    seen = (b & 1).view(bool)
                    px = seen & ~tk
                    n2 = int(px.sum())
                else:
                    n2 = int(ns[i])
                if n2 < c.min_seen or n2 < c.seen_min * n_op[i]:
                    continue
                n_cd, n_front = 0, int(cnt[i, NCNT + NL + slot]) if slot is not None else 0
                xm = None                                               # known-drawn in the ring: drops, mobs, chars
                if near:
                    uns = (b & 3) == 2
                    n_cd = int((uns & dk).sum())
                    if n_front:
                        n_front = int((uns & ((frb[i] >> slot) & 1).view(bool) & ~dk).sum())
                    xm = dk
                n_mob = 0
                if mob_taken is not None and (mob_boxes is None or any(
                        mx < wx + K and mx + mw > wx and my < wy + K and my + mh > wy for mx, my, mw, mh in mob_boxes)):
                    if 0 <= wy and wy + K <= mob_taken.shape[0] and 0 <= wx and wx + K <= mob_taken.shape[1]:
                        mt = mob_taken[wy:wy + K, wx:wx + K]
                    else:
                        mt = _plane_win(mob_taken, wy, wx, K)
                    if mt.any():
                        seen = (b & 1).view(bool) if seen is None else seen
                        n_mob = int((seen & mt).sum())
                        xm = mt if xm is None else xm | mt
                if chars and any(b0[0] < wx + K and b0[2] > wx and b0[1] < wy + K and b0[3] > wy for b0 in chars):
                    cw_ = _rect_win(chars, wy, wx, K)
                    xm = cw_ if xm is None else xm | cw_
                ring = [int(rex[i]), int(rkn[i])]
                if xm is not None:
                    ring = [ring[0] + int((((b & 8) > 0) & xm).sum()), ring[1] + int((((b & 4) > 0) & xm).sum())]
                d = {"item": self.meta[gi][0], "f": self.meta[gi][1], "box": [x, y, ww, hh], "feet": [x + ww // 2, y + hh],
                     "n_op": int(n_op[i]), "seen": n2, "absent": n_abs, "under": n_cd, "front": n_front, "mob": n_mob,
                     "ring": ring, "dy": int(round(y + hh + C[1] - uy[k])) if uok[k] else None,
                     "fh": int(uid[k]) if uok[k] else None, "layer": lay, "votes": int(votes[i]), "n_fseen": int(nfs[i])}
                d["kind"] = kind_of(d, c)
                acc.append((x, y, ww, hh, px, gi, b))
                drops.append(d)
        t2 = time.perf_counter()
        self.ms = {"launch": round(self._launch_ms, 3), "fetch": round((t1 - t0) * 1000, 3),
                   "pick": round((t2 - t1) * 1000, 3), "feat": int(cnt[0, 10]), "feat2": int(cnt[0, 11]),
                   "cands": int((votes >= c.cand_votes).sum())}
        return drops
