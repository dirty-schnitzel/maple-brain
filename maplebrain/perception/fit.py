"""The fit (PLAN-perception.md step 3.2, PLAN-fit-speed.md): which mobs - type, pose, facing, feet, opacity - the frame
shows, pixel by pixel. NOT on the live path: 3.3 runs it in shadow.

1. Candidates = the vote (perception/vote.py): cells (pose, feet) with >= `cand_votes` exclusive votes of the frame's
   2x2 sprite-colour features, taken where the expected scene does not explain the pixel. No windows, no footholds,
   no positions x poses search: ~1 candidate per mob. Fading mobs join the same vote: the residue un-blended at
   each screen cell's fade alpha (Voter.fade; our body box `me` kept out).
2. Stage 2, per pixel of each candidate's sprite (sprite colour s, alpha a, opacity o), the client's model
       I = B + o a (s - B),   r = I - B,   q = a (s - B)
   with B = the expected scene (Scene.expected: tiles / objects of every layer + backs) and the pixel VALID when the
   scenery there is known, it is no opaque UI (`ui`) and the front scenery of the mob's layer (Scene.layers: tiles /
   objects of the layers above the mob's foothold) covers it with alpha < `front_max` (the mob is drawn under it).
   The mob's layer = the nearest foothold's at / below its feet; flyers: the lowest of their spawns' layers (the
   most front = the safe side). Where the mob would change the pixel a lot (o |q| > `inf` levels: informative):
       SEEN     valid and I = B + o q within tol
       ABSENT   valid, not SEEN and I = B within tol: the pixel shows the scene where the mob would be
       COVERED  the rest: not valid, or neither - something drawn over it (an effect, a player, another mob, the UI)
   o = the mode of the per-pixel ratios r.q / q.q over the informative valid pixels, refined by least squares on the
   mode's pixels (1 for the opaque vote's mobs up to rounding; a fading mob's own o).
   Tints (vote.TINTS, frozen): every candidate is tried with its plain sprite and each tinted one (s -> round(s m /
   255)); the variant with the most SEEN pixels stays (FitMob.tint).
3. A mob = SEEN share >= seen_min and ABSENT share <= absent_max (shares of the informative pixels) and >= min_seen
   SEEN pixels; accepted greedily by SEEN count, every accepted mob's SEEN pixels count as COVERED for the others
   (Zombie Mushroom stand_1 = move_2: the same picture 4 px apart - the second one finds its pixels taken).
GPU work per frame: the vote (3 syncs) + one gather per source of all candidate boxes (frame, expected, valid, the
sprites, the front alphas) + ~60 small ops + one transfer back; the pick on the CPU.
"""
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from maplebrain.perception.vote import PLAY_H, SW, TINTS, Voter, load_poses, tinted


@dataclass
class FitConfig:
    tol: float = 4.0            # levels: native pixels are exact or something else (step 0)
    inf: float = 16.0           # a pixel is informative when the mob changes it by more than this
    seen_min: float = 0.03      # SEEN share of the informative pixels (rule fitted on synth, 2026-11-17)
    absent_max: float = 0.1     # ABSENT share
    min_seen: int = 60          # SEEN pixels
    cand_votes: int = 16        # exclusive votes for a stage-2 candidate (24 lost a 40 %-visible mob: D's mask
                                # drops its pixels that equal the scene, 25 -> 16 votes; 12-48: 0 false on synth)
    front_max: float = 0.5      # front scenery at alpha >= this over the mob: not valid
    o_bins: int = 128           # the opacity: the mode of the per-pixel ratios, this many bins over 0..1
    max_entries: int = 64       # vote table: keys in more places are dropped
    fade: bool = True           # the fade search (Voter.fade): the residue un-blended at the frame's fade alphas
    fade_strong: float = 24.0   # a residue pair's pixels differ from the scene by >= this
    fade_n_min: int = 20        # strong pairs (of the quarter sampled) on the frame, else no search
    fade_cell: int = 48         # one alpha per screen cell of this size
    fade_cell_min: int = 12     # hitting pairs for a cell's own alpha
    fade_lo: int = 38           # alphas searched lo..hi in steps
    fade_hi: int = 252
    fade_step: int = 3
    fade_ratio: float = 0.0     # > 1: a geometric alpha grid (this ratio) instead of the step
    fade_scale: bool = True     # the un-blend tolerance grows with 1 / o (Voter.FADE_TOLS), else +-2 (misses the
                                # faint fades o ~0.1-0.27: rounding x 1 / o; labels fade 87.2 -> 93.2 %)
    fade_report: bool = False   # list the cells' alphas in ms["alphas"] (one more sync; tools only)
    tints: bool = True          # vote.TINTS (frozen) in the LUT + every candidate tried tinted in stage 2


@dataclass
class FitMob:
    type: int
    pose: str
    facing: str
    feet: tuple
    opacity: float
    seen: float                 # shares of the informative pixels
    absent: float
    covered: float
    n_inf: int
    n_seen: int
    votes: int                  # exclusive votes of its cell
    layer: int
    tint: str = ""              # "" = drawn plain, else a vote.TINTS name ("frozen")

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


class Fitter:
    def __init__(self, scene, map_id: int, assets: Path, cfg: FitConfig | None = None, types=None):
        """`scene`: a Scene (its layers' front planes, if built); `assets`: assets/mcw (maps/<id>/map.json, mobs/)."""
        torch = scene.torch
        self.scene, self.torch, self.dev = scene, torch, scene.dev
        self.cfg = cfg or FitConfig()
        assets = Path(assets)
        poses = load_poses(map_id, assets, types)
        tints = TINTS if self.cfg.tints else {}
        self.voter = Voter(poses, self.cfg.max_entries, self.dev, tints=tints)
        self.poses, self.G = poses, len(poses)
        self.tint_names = [""] + list(tints)            # variant k: sprite plane k * G + g
        # one common box around the feet for every pose: column L / row T = the feet
        self.L = max(p.ox for p in poses)
        self.T = max(p.oy for p in poses)
        self.KW = self.L + max(p.pic.shape[1] - p.ox for p in poses)
        self.KH = self.T + max(p.pic.shape[0] - p.oy for p in poses)
        sa = np.zeros((len(poses), self.KH, self.KW, 4), np.float32)          # s (BGR 0..255), a (0..1)
        for g, p in enumerate(poses):
            h, w = p.pic.shape[:2]
            y0, x0 = self.T - p.oy, self.L - p.ox
            sa[g, y0:y0 + h, x0:x0 + w, :3] = p.pic[..., :3]
            sa[g, y0:y0 + h, x0:x0 + w, 3] = p.pic[..., 3] / 255.0
        planes = [sa]
        for m in tints.values():                        # the tinted sprites: same alpha, colours round(s m / 255)
            st = sa.copy()
            st[..., :3] = tinted(sa[..., :3].astype(np.uint8), m)
            planes.append(st)
        self.sa = torch.from_numpy(np.concatenate(planes)).to(self.dev)
        # layers: footholds per layer (map coordinates, x1 < x2), flyers' spawn layers, the front alpha planes
        m = json.loads((assets / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        fh = {int(k): f for k, f in (m.get("footholds") or {}).items()}
        rows = [((f["x1"], f["y1"], f["x2"], f["y2"]) if f["x1"] < f["x2"] else (f["x2"], f["y2"], f["x1"], f["y1"]))
                + (int(f.get("layerId", 0)),) for f in fh.values() if f["x1"] != f["x2"]]
        self.fh = np.array(rows, np.float64).reshape(-1, 5)
        fly_layers = {}
        for sp in m.get("mobs") or []:
            f = fh.get(int(sp.get("footholdId", -1)))
            if f is not None:
                fly_layers.setdefault(int(sp["id"]), set()).add(int(f.get("layerId", 0)))
        fly = {t for t in {p.type for p in poses}
               if (json.loads((assets / "mobs" / str(t) / "mob.json").read_text(encoding="utf-8")).get("frames") or {})
               .get("fly")}
        self.layer_ids = sorted(scene.layers) or [0]
        self.low = self.layer_ids[0]
        self.fly_layer = {t: min(fly_layers.get(t) or {self.low}) for t in fly}
        # front alpha per layer, with a zero row / column in front (index 0 = outside the rendered area)
        ch, cw = scene.canvas.shape[:2]
        fa = torch.zeros((len(self.layer_ids), ch + 1, cw + 1), dtype=torch.uint8, device=self.dev)
        for i, L in enumerate(self.layer_ids):
            if L in scene.layers:
                fa[i, 1:, 1:] = scene.layers[L][1][..., 3]
        self.front_a = fa
        self.ch, self.cw = ch, cw
        # front backs are drawn over every layer: their cover joins the valid mask (none on most maps)
        self.front_backs = any(b["front"] and b["known"] for b, _ in scene.backs)
        self.ms = {}

    def _layers(self, g, fx, fy, C) -> np.ndarray:
        """Each candidate's foothold layer (index into layer_ids)."""
        out = np.zeros(len(g), int)
        pos = {L: i for i, L in enumerate(self.layer_ids)}
        X1, Y1, X2, Y2, LY = (self.fh[:, k] for k in range(5))
        for i in range(len(g)):
            t = self.poses[int(g[i])].type
            if t in self.fly_layer:
                out[i] = pos.get(self.fly_layer[t], 0)
                continue
            mx, my = fx[i] + C[0], fy[i] + C[1]
            on = (X1 <= mx) & (X2 >= mx)
            if on.any():
                ya = Y1[on] + (mx - X1[on]) * (Y2[on] - Y1[on]) / (X2[on] - X1[on])
                below = ya >= my - 2
                if below.any():
                    out[i] = pos.get(int(LY[on][below][np.argmin(ya[below])]), 0)
        return out

    def _meta(self, g, fx, fy, li, C) -> np.ndarray:
        """The candidates' gather indices, one int64 row each: box rows / columns on screen (clamped), whether
        each is on screen, the front planes' rows / columns (0 = outside the rendered area), pose, layer index."""
        KH, KW = self.KH, self.KW
        R = fy[:, None] - self.T + np.arange(KH)[None]                   # screen rows / columns of the boxes
        Q = fx[:, None] - self.L + np.arange(KW)[None]
        rok, cok = (R >= 0) & (R < PLAY_H), (Q >= 0) & (Q < SW)
        MY, MX = R + int(C[1]) - self.scene.y0, Q + int(C[0]) - self.scene.x0  # the front planes' (map canvas)
        MY = np.where((MY >= 0) & (MY < self.ch), MY + 1, 0)                     # 0 = the zero border
        MX = np.where((MX >= 0) & (MX < self.cw), MX + 1, 0)
        return np.concatenate([np.clip(R, 0, PLAY_H - 1), np.clip(Q, 0, SW - 1), rok, cok, MY, MX,
                               np.asarray(g)[:, None], li[:, None]], axis=1).astype(np.int64)

    BUCKETS = (8, 16, 32, 64)

    def _graphs(self):
        """Stage 2's GPU part as CUDA graphs, one per candidate bucket (padded with off-screen rows): ~60 small ops
        cost ~0.5 ms of launches each call, a replay one. Static inputs: the frame, expected, valid, the meta."""
        torch = self.torch
        self._sf = torch.zeros((PLAY_H, SW, 3), dtype=torch.uint8, device=self.dev)
        self._se = torch.zeros((PLAY_H, SW, 3), device=self.dev)
        self._sv = torch.zeros((PLAY_H, SW), dtype=torch.bool, device=self.dev)
        self._g = {}
        ncol = 3 * (self.KH + self.KW) + 2
        for n in self.BUCKETS:
            mt = torch.zeros((n, ncol), dtype=torch.long, device=self.dev)
            s = torch.cuda.Stream()
            s.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(s):
                for _ in range(2):
                    self._core(self._sf, self._se, self._sv, mt)
            torch.cuda.current_stream().wait_stream(s)
            gr = torch.cuda.CUDAGraph()
            with torch.cuda.graph(gr):
                out = self._core(self._sf, self._se, self._sv, mt)
            self._g[n] = (gr, mt, out)

    def _stage2(self, frame, exp, valid, meta):
        """Per-pixel labels of candidates (meta rows) -> (inf / seen / absent bits (n, KH, KW) uint8, counts (n, 3)
        int32 = informative / SEEN / ABSENT pixels, o (n,) float32) as numpy."""
        torch = self.torch
        n = nb = len(meta)
        if self.dev == "cpu" or n > self.BUCKETS[-1]:
            out = self._core(frame, exp, valid, torch.from_numpy(meta).to(self.dev)).cpu().numpy()
        else:
            if not hasattr(self, "_g"):
                self._graphs()
            nb = next(k for k in self.BUCKETS if k >= n)
            gr, mt, o_s = self._g[nb]
            self._sf.copy_(frame)
            self._se.copy_(exp)
            self._sv.copy_(valid)
            pad = np.zeros((nb, meta.shape[1]), np.int64)          # padding rows: off screen, no pixel
            pad[:n] = meta
            mt.copy_(torch.from_numpy(pad))
            gr.replay()
            out = o_s.cpu().numpy()
        K = self.KH * self.KW
        bits = out[:nb * K].reshape(nb, self.KH, self.KW)[:n]
        cnt = out[nb * K:nb * K + 12 * nb].view(np.int32).reshape(nb, 3)[:n]
        o = out[nb * K + 12 * nb:].view(np.float32)[:n]
        return bits, cnt, o

    def _core(self, frame, exp, valid, mt):
        """Stage 2 on the GPU, no sync (graph-capturable) -> one uint8 tensor: bits (n*KH*KW), counts (n x 3
        int32), o (n float32)."""
        torch, c = self.torch, self.cfg
        n, KH, KW = mt.shape[0], self.KH, self.KW
        o0 = KH + KW
        Rt, Qt = mt[:, :KH, None], mt[:, KH:o0, None].transpose(1, 2)
        on = (mt[:, o0:o0 + KH, None] > 0) & (mt[:, o0 + KH:2 * o0, None] > 0).transpose(1, 2)
        MYt, MXt = mt[:, 2 * o0:2 * o0 + KH, None], mt[:, 2 * o0 + KH:3 * o0, None].transpose(1, 2)
        gt, lt = mt[:, -2], mt[:, -1]
        I = frame[Rt, Qt].float()                                        # (n, KH, KW, 3)
        B = exp[Rt, Qt]
        V = valid[Rt, Qt] & on & (self.front_a[lt[:, None, None], MYt, MXt] < 255 * c.front_max)
        sa = self.sa[gt]
        r = I - B
        q = sa[..., 3:] * (sa[..., :3] - B)
        qn = q.abs().amax(dim=3)
        rq, qq = (r * q).sum(dim=3), (q * q).sum(dim=3).clamp_(min=1e-6)
        ratio = (rq / qq).flatten(1)
        use = (V & (qn > c.inf)).flatten(1)
        nb = c.o_bins
        b = (ratio * nb).round_().clamp_(-1, nb + 1).long()
        ok = use & (b >= 0)
        ok &= b <= nb
        hist = torch.zeros((n, nb + 3), device=self.dev).scatter_add_(1, (b + 1) * ok, ok.float())
        hist[:, 0] = 0
        sm = hist[:, :-2] + hist[:, 1:-1] + hist[:, 2:]                 # bins 0..nb, each with its 2 neighbours
        mx, at = sm.max(dim=1)
        near = (use & (ratio - at[:, None] / nb).abs().le(1.5 / nb)).float()   # refined: least squares on the
        o = (rq.flatten(1) * near).sum(1) / (qq.flatten(1) * near).sum(1).clamp(min=1e-6)  # mode's pixels
        o = torch.where(mx > 0, o, torch.ones_like(o)).clamp_(0, 1)
        inf = on & (o[:, None, None] * qn > c.inf)
        iv = inf & V
        seen = iv & ((r - o[:, None, None, None] * q).abs().amax(dim=3) <= c.tol)
        absent = iv & ~seen & (r.abs().amax(dim=3) <= c.tol)
        bits = inf.to(torch.uint8) | (seen.to(torch.uint8) << 1) | (absent.to(torch.uint8) << 2)
        cnt = torch.stack([inf.flatten(1).sum(1), seen.flatten(1).sum(1), absent.flatten(1).sum(1)], 1).to(torch.int32)
        return torch.cat([bits.flatten(), cnt.flatten().view(torch.uint8), o.float().contiguous().view(torch.uint8)])

    def _pick(self, bits, cnt, o, g, fx, fy, ex, li) -> list:
        """Greedy by SEEN count; an accepted mob's SEEN pixels are COVERED for the rest (on the CPU)."""
        c = self.cfg
        inf, ns_all, nab = cnt[:, 0], cnt[:, 1], cnt[:, 2]
        P = max(self.KH, self.KW)
        taken = np.zeros((PLAY_H + 2 * P, SW + 2 * P), bool)
        mobs = []
        for i in np.argsort(-ns_all, kind="stable"):
            ni = int(inf[i])
            if ni <= 0 or ns_all[i] < c.min_seen or ns_all[i] < c.seen_min * ni or nab[i] > c.absent_max * ni:
                continue
            y0, x0 = int(fy[i]) - self.T + P, int(fx[i]) - self.L + P
            sl = (slice(y0, y0 + self.KH), slice(x0, x0 + self.KW))
            px = (bits[i] & 2).astype(bool) & ~taken[sl]
            ns = int(px.sum())
            if ns < c.min_seen or ns < c.seen_min * ni:
                continue
            taken[sl] |= px
            p = self.poses[int(g[i]) % self.G]
            mobs.append(FitMob(p.type, p.pose, p.facing, (int(fx[i]), int(fy[i])), round(float(o[i]), 3),
                               round(ns / ni, 3), round(int(nab[i]) / ni, 3), round(1 - (ns + int(nab[i])) / ni, 3),
                               ni, ns, int(ex[i]), self.layer_ids[int(li[i])], self.tint_names[int(g[i]) // self.G]))
        return mobs

    def fit(self, frame, C, exp, known, ui=None, me=None, keep_cands: bool = False):
        """`frame`: uint8 BGR (GPU tensor or array, >= PLAY_H rows); `C`: the scene camera; `exp`, `known`:
        Scene.expected(C) (D's - one per tick); `ui`: optional bool (PLAY_H, SW) tensor, True = may show a mob (the
        minimap / keycaps False; the chat rect is world); `me`: our body box (x0, y0, x1, y1) on screen, kept out of
        the fade search. -> [FitMob] (+ every candidate's counts when keep_cands)."""
        torch, c = self.torch, self.cfg
        if not torch.is_tensor(frame):
            frame = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(self.dev)
        frame = frame[:PLAY_H]
        t0 = time.perf_counter()
        valid = known if ui is None else known & ui
        ids, r, mag = self.voter.ids(frame, exp, known, c.tol, resid=True)
        tf = time.perf_counter()
        alphas, fc = None, {}
        if c.fade:
            ids, alphas, fc = self.voter.fade(ids, r, mag, exp, valid, me, c.tol, c.fade_strong, c.fade_n_min,
                                              c.fade_cell, c.fade_cell_min, c.fade_lo, c.fade_hi, c.fade_step,
                                              c.fade_ratio, c.fade_scale, c.fade_report)
            if self.dev != "cpu":
                torch.cuda.synchronize()            # the vote's first step syncs anyway: the part's ms are honest
        tf = time.perf_counter() - tf
        g, fx, fy, nv, ex, vc = self.voter.cells(ids, c.cand_votes)
        t1 = time.perf_counter()
        mobs, cands = [], []
        if len(g):
            C = (int(C[0]), int(C[1]))
            li = self._layers(g, fx, fy, C)
            if self.front_backs:
                z1 = torch.zeros(valid.shape, device=self.dev)
                _, cov, _ = self.scene._backs(C, SW, PLAY_H, 1, torch.zeros((*valid.shape, 3), device=self.dev), z1,
                                              torch.zeros_like(valid))
                valid = valid & (cov < c.front_max)
            n, K = len(g), len(self.tint_names)
            gv = np.concatenate([np.asarray(g) + k * self.G for k in range(K)])    # every tint variant of each cell
            meta = self._meta(gv, np.tile(fx, K), np.tile(fy, K), np.tile(li, K), C)
            step = self.BUCKETS[-1]
            parts = [self._stage2(frame, exp, valid, meta[i:i + step]) for i in range(0, len(gv), step)]
            bits, cnt, o = (np.concatenate([p[k] for p in parts]) for k in range(3))
            if K > 1:                                   # per cell the variant with the most SEEN pixels (ties: plain)
                kb = np.argmax(cnt[:, 1].reshape(K, n), axis=0)
                sel = kb * n + np.arange(n)
                g, bits, cnt, o = gv[sel], bits[sel], cnt[sel], o[sel]
            t2 = time.perf_counter()
            mobs = self._pick(bits, cnt, o, g, fx, fy, ex, li)
            if keep_cands:
                for i in range(len(g)):
                    p = self.poses[int(g[i]) % self.G]
                    cands.append({"type": p.type, "pose": p.pose, "facing": p.facing, "feet": [int(fx[i]), int(fy[i])],
                                  "votes": int(ex[i]), "raw": int(nv[i]), "o": round(float(o[i]), 3),
                                  "n_inf": int(cnt[i, 0]), "n_seen": int(cnt[i, 1]), "n_abs": int(cnt[i, 2]),
                                  "tint": self.tint_names[int(g[i]) // self.G]})
        else:
            t2 = t1
        t3 = time.perf_counter()
        self.ms = {"fit": (t3 - t0) * 1000, "vote": (t1 - t0 - tf) * 1000, "fade": tf * 1000, "s2": (t2 - t1) * 1000,
                   "pick": (t3 - t2) * 1000, "cands": len(g), "feat": vc["feat"], "votes": vc["votes"],
                   "pairs": fc.get("pairs", 0), "alphas": alphas}
        return (mobs, cands) if keep_cands else mobs
