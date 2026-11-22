"""The fit (PLAN-perception.md step 3.2, PLAN-fit-speed.md): which mobs - type, pose, facing, feet, opacity - the frame
shows, pixel by pixel. Since 3.4 the tracker's sightings on clean maps (scene camera found this tick): the Perceiver
runs it before the tracker, each FitMob -> a detector Hit (`hit`, score 1.0: the rule below already decided), and
the tracker's search around the tracks it did not see is `look` (one stage-2 look at each track's predicted feet;
SEEN by the same rule -> a sighting there, ABSENT / COVERED -> none). FrameFacts.fit + fit_hints (the looks).
`hints` = 3.3's shadow form of the looks (tools only since the shadow path went, 2026-11-17).

1. Candidates = the vote (perception/vote.py): cells (pose, feet) with >= `cand_votes` exclusive votes of the frame's
   2x2 sprite-colour features, taken where the expected scene does not explain the pixel. No windows, no footholds,
   no positions x poses search: ~1 candidate per mob. Fading mobs join the same vote: the residue un-blended at
   each screen cell's fade alpha (Voter.fade; our body box `me` kept out).
2. Stage 2, per pixel of each candidate's sprite (sprite colour s, alpha a, opacity o), the client's model
       I = B + o a (s - B),   r = I - B,   q = a (s - B)
   with B = the expected scene (Scene.expected: tiles / objects of every layer + backs) and the pixel VALID when the
   scenery there is known, it is no opaque UI (`ui`) and the front scenery of the mob's layer (Scene.layers: tiles /
   objects of the layers above the mob's foothold) covers it with alpha < `front_max` (the mob is drawn under it).
   The mob's layer = the nearest foothold's at / below its feet; flyers: each layer their type spawns on is tried
   (a variant, like the tints). Where the mob would change the pixel a lot (o |q| > `inf` levels: informative):
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
    hint_o_min: float = 0.3     # hints (3.3): the opacity's floor - where the frame shows the scene instead of the
                                # mob the estimate goes to ~0 and no pixel would be informative (no ABSENT evidence);
                                # fades fainter than this read COVERED


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
        """`scene`: a Scene (its layers' front alphas, if built); `assets`: assets/mcw (maps/<id>/map.json, mobs/).
        ~0.12-0.18 s on the clean maps + `warm` ~0.03-0.06 (2026-11-17): built at map load, no thread."""
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
        pos = {L: i for i, L in enumerate(self.layer_ids)}
        self.fly_layers = {t: sorted({pos.get(L, 0) for L in fly_layers.get(t) or {self.low}}) for t in fly}
        # front alpha per layer, with a zero row / column in front (index 0 = outside the rendered area)
        ch, cw = scene.canvas.shape[:2]
        fa = torch.zeros((len(self.layer_ids), ch + 1, cw + 1), dtype=torch.uint8, device=self.dev)
        for i, L in enumerate(self.layer_ids):
            if L in scene.layers:
                fa[i, 1:, 1:] = scene.layers[L]
        self.front_a = fa
        self.ch, self.cw = ch, cw
        # front backs are drawn over every layer: their cover joins the valid mask (none on most maps)
        self.front_backs = any(b["front"] and b["known"] for b, _ in scene.backs)
        self.ms = {}
        # the hints' poses: (type, anim, facing) -> pose indices; the die poses per (type, facing)
        self.by_anim, self.die, self.pose_ix = {}, {}, {}
        for g, p in enumerate(poses):
            anim = p.pose.rsplit("_", 1)[0]
            self.by_anim.setdefault((p.type, anim, p.facing), []).append(g)
            if anim.startswith("die"):
                self.die.setdefault((p.type, p.facing), []).append(g)
            self.pose_ix[(p.type, p.pose, p.facing)] = g
        self._last = None                               # the last fit's (frame, C, exp, valid) for `hints`
        self.taken = None                               # ... and the pixels its accepted mobs explained

    def warm(self):
        """Capture stage 2's CUDA graphs and run the vote once (at map load: the first live fit would stall)."""
        if self.dev == "cpu":
            return
        self._graphs()
        C = (self.scene.x0, self.scene.y0)
        exp, known = self.scene.expected(C)
        self.fit(self.torch.zeros((PLAY_H, SW, 3), dtype=self.torch.uint8, device=self.dev), C, exp, known)
        self.torch.cuda.synchronize()

    def _layers(self, g, fx, fy, C) -> list:
        """Each candidate's possible foothold layers (indices into layer_ids): a ground mob the nearest foothold's at /
        below its feet; a flyer every layer its type spawns on (stage 2 tries each: a Stirge spawned on Transfer
        Area's layer 5 is drawn over the bricks that layer 2's front plane holds)."""
        out = []
        pos = {L: i for i, L in enumerate(self.layer_ids)}
        X1, Y1, X2, Y2, LY = (self.fh[:, k] for k in range(5))
        for i in range(len(g)):
            t = self.poses[int(g[i])].type
            if t in self.fly_layers:
                out.append(self.fly_layers[t])
                continue
            li = 0
            mx, my = fx[i] + C[0], fy[i] + C[1]
            on = (X1 <= mx) & (X2 >= mx)
            if on.any():
                ya = Y1[on] + (mx - X1[on]) * (Y2[on] - Y1[on]) / (X2[on] - X1[on])
                below = ya >= my - 2
                if below.any():
                    li = pos.get(int(LY[on][below][np.argmin(ya[below])]), 0)
            out.append([li])
        return out

    def _meta(self, g, fx, fy, li, C, o_min: float = 0.0) -> np.ndarray:
        """The candidates' gather indices, one int64 row each: box rows / columns on screen (clamped), whether
        each is on screen, the front planes' rows / columns (0 = outside the rendered area), pose, layer index, the
        opacity's floor in 1/1000 (the fit 0; `hints` FitConfig.hint_o_min)."""
        KH, KW = self.KH, self.KW
        R = fy[:, None] - self.T + np.arange(KH)[None]                   # screen rows / columns of the boxes
        Q = fx[:, None] - self.L + np.arange(KW)[None]
        rok, cok = (R >= 0) & (R < PLAY_H), (Q >= 0) & (Q < SW)
        MY, MX = R + int(C[1]) - self.scene.y0, Q + int(C[0]) - self.scene.x0  # the front planes' (map canvas)
        MY = np.where((MY >= 0) & (MY < self.ch), MY + 1, 0)                     # 0 = the zero border
        MX = np.where((MX >= 0) & (MX < self.cw), MX + 1, 0)
        return np.concatenate([np.clip(R, 0, PLAY_H - 1), np.clip(Q, 0, SW - 1), rok, cok, MY, MX,
                               np.asarray(g)[:, None], li[:, None], np.full((len(g), 1), round(1000 * o_min))],
                              axis=1).astype(np.int64)

    BUCKETS = (8, 16, 32, 64)

    def _graphs(self):
        """Stage 2's GPU part as CUDA graphs, one per candidate bucket (padded with off-screen rows): ~60 small ops
        cost ~0.5 ms of launches each call, a replay one. Static inputs: the frame, expected, valid, the meta."""
        torch = self.torch
        self._sf = torch.zeros((PLAY_H, SW, 3), dtype=torch.uint8, device=self.dev)
        self._se = torch.zeros((PLAY_H, SW, 3), device=self.dev)
        self._sv = torch.zeros((PLAY_H, SW), dtype=torch.bool, device=self.dev)
        self._g = {}
        ncol = 3 * (self.KH + self.KW) + 3
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
        gt, lt = mt[:, -3], mt[:, -2]
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
        o = torch.maximum(o, mt[:, -1].float() / 1000)                 # the hints' floor (the fit: 0)
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
        self.taken = taken
        return mobs

    def _variants(self, g, fx, fy, C, o_min: float = 0.0):
        """Stage-2 rows for candidates (pose g, feet fx, fy): every tint x every possible layer -> (meta, candidate
        index per row, sprite plane per row, layer index per row)."""
        li = self._layers(g, fx, fy, C)
        nt = len(self.tint_names)
        rc = np.array([i for i in range(len(g)) for _ in range(nt) for _ in li[i]], int)
        rg = np.array([g[i] + k * self.G for i in range(len(g)) for k in range(nt) for _ in li[i]], np.int64)
        rl = np.array([L for i in range(len(g)) for _ in range(nt) for L in li[i]], int)
        return self._meta(rg, fx[rc], fy[rc], rl, C, o_min), rc, rg, rl

    def _run(self, frame, exp, valid, meta):
        step = self.BUCKETS[-1]
        parts = [self._stage2(frame, exp, valid, meta[i:i + step]) for i in range(0, len(meta), step)]
        return tuple(np.concatenate([p[k] for p in parts]) for k in range(3))

    def _valid2(self, valid, C):
        """Stage 2's valid mask: + the front backs' cover (drawn over every layer; none on most maps)."""
        if not self.front_backs:
            return valid
        torch = self.torch
        acc, _ = self.scene._backs(C, SW, PLAY_H, 1, torch.zeros((*valid.shape, 4), device=self.dev),
                                   torch.zeros_like(valid))
        return valid & (acc[..., 3] < self.cfg.front_max)

    def hints(self, tracks, mobs, r: int = 20) -> list:
        """Step 4's evidence (3.3, in shadow): each confirmed track on screen (world.Track: live / hit / hidden /
        dying, kind mob) the last `fit` did not find (no fit mob of its type within `r` px in x and y) gets ONE
        stage-2 look at its predicted feet: every frame of its last anim with its facing (+ the type's die poses
        when dying), each with every tint / layer variant, the opacity floored at `hint_o_min`; the frame with the
        most SEEN pixels (ties: the least ABSENT share) -> its counts. Pixels an accepted fit mob explained count as
        COVERED. -> [{"id", "mob", "sx", "sy", "pose", "facing", "n_inf", "n_seen", "n_abs", "o"}] (covered =
        n_inf - n_seen - n_abs)."""
        if self._last is None:
            return []
        todo = []
        for tr in tracks:
            if tr.kind != "mob" or tr.state not in ("live", "hit", "hidden", "dying"):
                continue
            sx, sy = int(round(tr.sx)), int(round(tr.sy))
            if any(m.type == tr.mob_id and abs(m.feet[0] - sx) <= r and abs(m.feet[1] - sy) <= r for m in mobs):
                continue
            todo.append(tr)
        return [x for x in self.look(todo) if x is not None]

    def look(self, tracks) -> list:
        """The tracker's search around tracks (3.4; `hints` in shadow): ONE stage-2 look per track at its predicted
        feet (Track.sx / sy) - every frame of its last anim with its facing (+ the type's die poses when dying), each
        with every tint / layer variant, the opacity floored at `hint_o_min`; the frame with the most SEEN pixels
        (ties: the least ABSENT share) -> its row {"id", "mob", "sx", "sy", "pose", "facing", "n_inf", "n_seen",
        "n_abs", "o"} (covered = n_inf - n_seen - n_abs). Pixels the last `fit`'s accepted mobs explained count as
        COVERED. None per track not looked at: not a mob track, feet outside -40..SW+40 x 0..PLAY_H+68, no pose of its
        anim. Needs this tick's `fit` first (its frame / expected scene / valid mask)."""
        out = [None] * len(tracks)
        if self._last is None:
            return out
        frame, C, exp, valid = self._last
        todo, gs = [], []
        for k, tr in enumerate(tracks):
            if tr.kind != "mob":
                continue
            sx, sy = int(round(tr.sx)), int(round(tr.sy))
            if not (-40 <= sx < SW + 40 and 0 <= sy < PLAY_H + 68):
                continue
            g = list(self.by_anim.get((tr.mob_id, tr.anim, tr.facing)) or [])
            if tr.state == "dying":
                g += [x for x in self.die.get((tr.mob_id, tr.facing), []) if x not in g]
            if not g:
                continue
            todo.append((k, tr, sx, sy))
            gs.append(g)
        if not todo:
            return out
        own = np.array([j for j, g in enumerate(gs) for _ in g], int)
        g = np.array([x for gg in gs for x in gg], np.int64)
        fx = np.array([todo[j][2] for j in own], np.int64)
        fy = np.array([todo[j][3] for j in own], np.int64)
        meta, rc, rg, rl = self._variants(g, fx, fy, C, self.cfg.hint_o_min)
        bits, cnt, o = self._run(frame, exp, valid, meta)
        P = max(self.KH, self.KW)
        taken = self.taken if self.taken is not None else np.zeros((PLAY_H + 2 * P, SW + 2 * P), bool)
        best = {}
        for j in range(len(rc)):
            i = rc[j]
            y0, x0 = int(fy[i]) - self.T + P, int(fx[i]) - self.L + P
            tk = np.zeros((self.KH, self.KW), bool)         # `taken` around the box (a track's feet may be past the
            sub = taken[max(0, y0):max(0, y0 + self.KH), max(0, x0):max(0, x0 + self.KW)]   # screen side / below)
            tk[max(0, -y0):max(0, -y0) + sub.shape[0], max(0, -x0):max(0, -x0) + sub.shape[1]] = sub
            ns = int(((bits[j] & 2).astype(bool) & ~tk).sum())
            key = (ns, -cnt[j, 2] / max(1, cnt[j, 0]))
            k = own[i]
            if k not in best or key > best[k][0]:
                best[k] = (key, j)
        for k, (i, tr, sx, sy) in enumerate(todo):
            (ns, _), j = best[k]
            p = self.poses[int(rg[j]) % self.G]
            out[i] = {"id": tr.id, "mob": tr.mob_id, "sx": sx, "sy": sy, "pose": p.pose, "facing": p.facing,
                      "n_inf": int(cnt[j, 0]), "n_seen": ns, "n_abs": int(cnt[j, 2]), "o": round(float(o[j]), 3)}
        return out

    def seen(self, row) -> bool:
        """A look's row (`look`) is a sighting: the fit's own mob rule (min_seen, seen_min, absent_max)."""
        c, n = self.cfg, row["n_inf"]
        return n > 0 and row["n_seen"] >= c.min_seen and row["n_seen"] >= c.seen_min * n and row["n_abs"] <= c.absent_max * n

    def hit(self, mob_type: int, pose: str, facing: str, feet):
        """A fit mob / a SEEN look as the tracker's sighting (sighting.Hit): the pose's box at the feet, score 1.0
        (the fit's rule decided)."""
        from maplebrain.perception.sighting import Hit, Pose
        p = self.poses[self.pose_ix[(mob_type, pose, facing)]]
        anim, n = pose.rsplit("_", 1)
        fx, fy = int(feet[0]), int(feet[1])
        h, w = p.pic.shape[:2]
        return Hit(mob_type, (fx - p.ox, fy - p.oy, w, h), (fx, fy), Pose(anim, int(n), facing, p.ox, p.oy), 1.0)

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
        C = (int(C[0]), int(C[1]))
        valid = self._valid2(valid, C)
        self._last, self.taken = (frame, C, exp, valid), None
        if len(g):
            # variants: every tint x every possible layer of each cell; per cell the one with the most SEEN pixels
            # stays (ties: the first = plain, the lowest layer)
            meta, rc, rg, rl = self._variants(g, fx, fy, C)
            bits, cnt, o = self._run(frame, exp, valid, meta)
            if len(rc) > len(g):
                best = np.full(len(g), -1)
                for j in range(len(rc)):
                    if best[rc[j]] < 0 or cnt[j, 1] > cnt[best[rc[j]], 1]:
                        best[rc[j]] = j
                g, li, bits, cnt, o = rg[best], rl[best], bits[best], cnt[best], o[best]
            else:
                g, li = rg, rl
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
