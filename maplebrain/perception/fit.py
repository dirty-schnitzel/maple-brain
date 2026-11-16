"""The fit (PLAN-perception.md step 3.2): which mob - type, pose, facing, feet, opacity - explains a window of the
frame, pixel by pixel, with the scene split at the mob's layer. NOT on the live path: 3.3 runs it in shadow.

The client draws a mob on foothold layer L over B = the backs + tiles / objects of layers <= L and under F, A = the
tiles / objects of layers > L + the front backs (Scene.split), with the sprite's colour s, alpha a and an opacity o
(1, or less while it fades in / out):
    I = F + (1 - A) * (B + o * a * (s - B))
Where the front is see-through (A < 0.98): I' = (I - F) / (1 - A), so  r = I' - B = o * q,  q = a * (s - B).
V = the valid pixels: B known, the front see-through, on screen, outside the `ui` mask. Mask only opaque UI (the
minimap, the keycaps): masked pixels keep stage 1's least squares clean (unmasked keycaps over a mob pushed it out of
the top candidates); hud.ui_mask's chat rect (rows 630-700) is world at native and must stay unmasked - a chat line
there is cover like an effect (per pixel below).

Positions: walkers' ground poses on the footholds of layer L crossing the window (+- fh_dy); jump poses and flyers
anywhere in the window (a knocked-back Zombie Mushroom falls far from any foothold). D-pruned: a position is kept
when the pose group's core box (where most of its poses are opaque) holds >= prune of D's pixels (|r| > tol) among
its valid ones - box sums from integral images, O(1) per position.
Stage 1 - every pose of the type at every kept position, exactly (no FFT: its error is absolute, wrong on near-flat
windows, where the fit must be exact):
    least squares o* = Srq / Sqq (clamped 0..1), gain = 2 o* Srq - o*^2 Sqq (how much of the difference from B the
    candidate explains), with
    Srq = sum V r.q = sum (a s).(r V) - sum a (B.r V)
    Sqq = sum V q.q = sum (a^2 |s|^2) V - 2 sum (a^2 s).(B V) + sum a^2 (|B|^2 V)
    = the window's fixed images (r V, B.r V | V, B V, |B|^2 V) gathered at the positions x the sprites' fixed
    images, one fp16 matmul per (layer, type, pose group) (cudnn's large-kernel conv ran at ~3 TMAC/s: 220 ms).
Stage 2 - the best `top` per window and type, per pixel of the sprite where the mob would change the picture
(informative: o |q| > `inf` levels in some channel, on screen):
    SEEN     valid and I' = B + o q within tol (tol / (1 - A) under a see-through front)
    ABSENT   valid, not SEEN and I' = B within tol: the pixel shows the scene where the mob would be
    COVERED  the rest: not valid (front opaque, unknown scenery) or neither - something drawn over it (an effect, a
             player, another mob, the UI)
    o = the mode of the per-pixel ratios r.q / q.q, refined by least squares on its pixels (the stage-1 o* and a
    median are pulled by covered pixels).
A mob = SEEN share >= seen_min and ABSENT share <= absent_max (shares of the informative pixels) and >= min_seen
SEEN pixels; accepted greedily by SEEN count, every accepted mob's SEEN pixels count as COVERED for the others.
"""
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PLAY_H, SW = 700, 1366
PADP = 100                                   # zero border of the window images: off-screen = not valid


@dataclass
class FitConfig:
    tol: float = 4.0            # levels: native pixels are exact or something else (step 0)
    inf: float = 16.0           # a pixel is informative when the mob changes it by more than this
    seen_min: float = 0.3       # SEEN share of the informative pixels
    absent_max: float = 0.1     # ABSENT share
    min_seen: int = 30          # SEEN pixels
    top: int = 24               # stage-2 candidates per window and type (+ 4 per 4000 px of window)
    near: int = 6               # of them at most this many within 6 px of each other (poses of one mob: under
                                # cover the right pose may rank below 3 wrong ones at the same feet)
    margin: int = 8             # a candidate's body overlaps its window by >= this (px)
    fh_dy: int = 2              # feet y within +- this of the foothold
    prune: float = 0.3          # D share in the pose group's core box (of its valid pixels)
    o_bins: int = 128           # the opacity: the mode of the per-pixel ratios, this many bins over 0..1
    chunk: int = 1024           # positions per gather / matmul
    half: bool = True           # stage 1 in fp16 on the GPU
    s1_step: int = 1            # stage 1's sums over every s1_step-th row and column of the sprite box only (an
                                # EXPERIMENT for speed: 1 = every pixel, the plan's exact sums; stage 2 always all)


@dataclass
class Window:
    x: int
    y: int
    w: int
    h: int
    types: tuple | None = None  # None: every type of the map
    src: str = "patch"


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
    gain: float
    layer: int
    window: int

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


class _Bank:
    """One mob type's poses (every animation, both facings) in a common box around the feet (kernel row T / column
    L = the feet), grouped by where the feet may be: "ground" (on a foothold) and "air" (jump poses; a flyer's
    every pose). Per group: the stage-1 matrices and the core box."""

    def __init__(self, mob_id: int, mob_dir: Path, torch, dev, half: bool, step: int = 1):
        import cv2
        info = json.loads((mob_dir / "mob.json").read_text(encoding="utf-8"))
        self.id, self.fly = mob_id, bool((info.get("frames") or {}).get("fly"))
        poses = []
        for anim, fs in (info.get("frames") or {}).items():
            for i, f in enumerate(fs or []):
                im = cv2.imread(str(mob_dir / f["file"]), cv2.IMREAD_UNCHANGED)
                if im is None or im.ndim != 3 or im.shape[2] != 4 or (im[..., 3] > 0).sum() < 60:
                    continue
                h, w = im.shape[:2]
                ox, oy = f.get("origin") or (w // 2, h)
                poses.append((f"{anim}_{i}", "left", im, int(ox), int(oy)))
                poses.append((f"{anim}_{i}", "right", np.ascontiguousarray(im[:, ::-1]), int(w - ox), int(oy)))
        self.poses = [(p, fc) for p, fc, *_ in poses]
        self.L = max(ox for *_, ox, _ in poses)
        self.R = max(im.shape[1] - ox for _, _, im, ox, _ in poses)
        self.T = max(oy for *_, oy in poses)
        self.Bt = max(im.shape[0] - oy for _, _, im, _, oy in poses)
        KH, KW = self.T + self.Bt, self.L + self.R
        self.KH, self.KW = KH, KW
        n = len(poses)
        a = np.zeros((n, KH, KW), np.float32)
        s = np.zeros((n, 3, KH, KW), np.float32)
        for k, (_, _, im, ox, oy) in enumerate(poses):
            y0, x0 = self.T - oy, self.L - ox
            h, w = im.shape[:2]
            a[k, y0:y0 + h, x0:x0 + w] = im[..., 3] / 255.0
            s[k, :, y0:y0 + h, x0:x0 + w] = im[..., :3].transpose(2, 0, 1)
        self.a = torch.from_numpy(a).to(dev)                         # (P, KH, KW) 0..1
        self.s = torch.from_numpy(s).to(dev)                         # (P, 3, KH, KW) 0..255
        s1 = s.transpose(0, 2, 3, 1) / 255.0                         # (P, KH, KW, 3)
        a2 = a * a
        wa = np.concatenate([a[..., None] * s1, -a[..., None]], axis=3)                    # (P, KH, KW, 4)
        z = np.zeros_like(a)[..., None]
        wb = np.concatenate([(a2 * (s1 ** 2).sum(axis=3))[..., None], -2 * a2[..., None] * s1, a2[..., None], z],
                            axis=3)                                                        # (P, KH, KW, 6) -> Sqq
        wr = np.concatenate([np.zeros((n, KH, KW, 5), np.float32), (a > 0.05)[..., None].astype(np.float32)],
                            axis=3)                                                        # -> Srr (footprint)
        dt = torch.float16 if half and dev != "cpu" else torch.float32
        air = [k for k, (p, _) in enumerate(self.poses) if self.fly or p.startswith("jump")]
        ground = [k for k in range(n) if k not in air]
        self.groups = []
        for kind, ks in (("ground", ground), ("air", air)):
            if not ks:
                continue
            frac = (a[ks] > 0.5).mean(axis=0)
            m = frac >= 0.5 if (frac >= 0.5).any() else frac > 0
            ys, xs = np.nonzero(m)
            core = (int(ys.min()) - self.T, int(xs.min()) - self.L, int(ys.max()) + 1 - self.T, int(xs.max()) + 1 - self.L)
            # the lowest opaque row of each pose, relative to the feet (air positions sit on a blob's lower edge)
            low = [int(np.nonzero((a[k] > 0.5).any(axis=1))[0].max()) - self.T for k in ks]
            high = [int(np.nonzero((a[k] > 0.5).any(axis=1))[0].min()) - self.T for k in ks]
            core = core + (min(low), max(low), min(high), max(high))
            sub = lambda w: w[ks][:, ::step, ::step].reshape(len(ks), -1)    # noqa: E731 (stage 1 on every
            Wa = torch.from_numpy(sub(wa).T.copy()).to(dev).to(dt)           # step-th row / column: s1_step)
            Wb = torch.from_numpy(np.concatenate([sub(wb), sub(wr)]).T.copy()
                                  ).to(dev).to(dt)                                          # (KH*KW*6, 2 n_g)
            self.groups.append((kind, ks, Wa, Wb, core))


class Fitter:
    def __init__(self, scene, map_id: int, assets: Path, cfg: FitConfig | None = None, types=None):
        """`scene`: a Scene with layers (scene.split); `assets`: assets/mcw (maps/<id>/map.json, mobs/<id>/)."""
        self.scene, self.torch, self.dev = scene, scene.torch, scene.dev
        self.cfg = cfg or FitConfig()
        m = json.loads((Path(assets) / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in m.get("mobs") or []}) if types is None else list(types)
        self.banks = {i: _Bank(i, Path(assets) / "mobs" / str(i), self.torch, self.dev, self.cfg.half, self.cfg.s1_step)
                      for i in ids}
        fh = {int(k): f for k, f in (m.get("footholds") or {}).items()}
        self.fh = [f for f in fh.values() if f["x1"] != f["x2"]]
        # per layer, the footholds as arrays (x1 < x2)
        self.fh_arr = {}
        for L in sorted({int(f.get("layerId", 0)) for f in self.fh}):
            fs = [f for f in self.fh if int(f.get("layerId", 0)) == L]
            arr = np.array([(f["x1"], f["y1"], f["x2"], f["y2"]) if f["x1"] < f["x2"] else (f["x2"], f["y2"], f["x1"], f["y1"])
                            for f in fs], np.float64)
            self.fh_arr[L] = arr
        # a flyer is drawn on the layer of the foothold it belongs to: the layers of its spawns' footholds
        self.fly_layers = {}
        for sp in m.get("mobs") or []:
            f = fh.get(int(sp.get("footholdId", -1)))
            if f is not None:
                self.fly_layers.setdefault(int(sp["id"]), set()).add(int(f.get("layerId", 0)))
        self.layers = sorted(self.fh_arr)
        self.ms = {}

    # ---- per frame: the window images of each layer
    def _images(self, frame, C, L, ui):
        """Padded (PADP) images of layer L: stage-1 inputs (channels last, /255 units), D's integral images, the
        stage-2 ones."""
        torch = self.torch
        B, kB, F, A = self.scene.split(C, L)
        I = frame[:PLAY_H].float()
        V = kB & (A < 0.98)
        if ui is not None:
            V &= ui
        den = (1 - A).clamp(min=0.02)
        Ip = (I - F) / den[..., None]
        r = torch.where(V[..., None], Ip - B, torch.zeros_like(B))
        tol = self.cfg.tol / den
        Vf = V.float()
        B1, r1 = B / 255.0, r / 255.0
        dt = torch.float16 if self.cfg.half and self.dev != "cpu" else torch.float32
        P = PADP
        padl = lambda t: torch.nn.functional.pad(t, (0, 0, P, P, P, P))   # noqa: E731  (H, W, C)
        pad = lambda t: torch.nn.functional.pad(t, (P, P, P, P))          # noqa: E731  (.., H, W)
        Xa = padl(torch.cat([r1, (B1 * r1).sum(dim=2, keepdim=True)], dim=2).to(dt))       # r1 is 0 where not V
        Xb = padl(torch.cat([Vf[..., None], B1 * Vf[..., None], (B1 * B1).sum(dim=2, keepdim=True) * Vf[..., None],
                             (r1 * r1).sum(dim=2, keepdim=True)], dim=2).to(dt))
        bad = (V & (r.abs().amax(dim=2) > tol)).int()
        ii = lambda t: torch.nn.functional.pad(pad(t).cumsum(0).cumsum(1), (1, 0, 1, 0))  # noqa: E731
        # D's lower edges (bad here, not 1-3 rows below), widened +-6 px in x: where an airborne pose can end
        bp = pad(bad.bool())
        below = torch.zeros_like(bp)
        for dy in (1, 2, 3):
            below[:-dy] |= bp[dy:]
        above = torch.zeros_like(bp)
        for dy in (1, 2, 3):
            above[dy:] |= bp[:-dy]
        wide = lambda e: torch.nn.functional.max_pool2d(e.half()[None, None], (1, 13), 1, (0, 6))[0, 0] > 0  # noqa
        st = {"edge": wide(bp & ~below), "top": wide(bp & ~above), "r": pad(r.permute(2, 0, 1)), "B": pad(B.permute(2, 0, 1)), "V": pad(Vf), "tol": pad(tol),
              "on": pad(torch.ones((PLAY_H, SW), device=self.dev)), "Xa": Xa, "Xb": Xb,
              "Ibad": ii(bad), "IV": ii(V.int())}
        return st

    # ---- positions
    def _positions(self, bank, win, L, kind):
        """Feet (x, y) np arrays of `bank`'s pose group `kind` in `win` on layer L (before pruning)."""
        c = self.cfg
        fx0 = max(win.x - bank.R + c.margin, -bank.R + 10)
        fx1 = min(win.x + win.w + bank.L - c.margin, SW + bank.L - 10)
        fy0 = max(win.y - bank.Bt + c.margin, -bank.Bt + 10)
        fy1 = min(win.y + win.h + bank.T - c.margin, PLAY_H + bank.T - 10)
        if fx1 < fx0 or fy1 < fy0:
            return None
        if kind == "air":
            if bank.fly and L not in self.fly_layers.get(bank.id, {L}):
                return None
            yy, xx = np.mgrid[fy0:fy1 + 1, fx0:fx1 + 1]
            return xx.ravel(), yy.ravel()
        arr = self.fh_arr.get(L)
        if arr is None:
            return None
        C = self._C
        X1, Y1, X2, Y2 = arr[:, 0] - C[0], arr[:, 1] - C[1], arr[:, 2] - C[0], arr[:, 3] - C[1]
        sel = (X2 >= fx0) & (X1 <= fx1) & (np.maximum(Y1, Y2) >= fy0 - c.fh_dy) & (np.minimum(Y1, Y2) <= fy1 + c.fh_dy)
        xs_all, ys_all = [], []
        for x1, y1, x2, y2 in zip(X1[sel], Y1[sel], X2[sel], Y2[sel]):
            xs = np.arange(max(fx0, int(np.ceil(x1))), min(fx1, int(np.floor(x2))) + 1)
            if not len(xs):
                continue
            ys = np.round(y1 + (xs - x1) * (y2 - y1) / (x2 - x1)).astype(int)
            for dy in range(-c.fh_dy, c.fh_dy + 1):
                xs_all.append(xs)
                ys_all.append(ys + dy)
        if not xs_all:
            return None
        xs, ys = np.concatenate(xs_all), np.concatenate(ys_all)
        k = (ys >= fy0) & (ys <= fy1)
        xy = np.unique(np.stack([xs[k], ys[k]], axis=1), axis=0)
        return (xy[:, 0], xy[:, 1]) if len(xy) else None

    # ---- stage 1
    def _stage1(self, bank, g, st, xs, ys):
        """Pose group g at feet (xs, ys) (GPU long tensors) -> (keep mask, gain (N, n_g), o* (N, n_g)) for the
        positions that pass the D prune."""
        torch, c = self.torch, self.cfg
        kind, ks, Wa, Wb, (cy0, cx0, cy1, cx1, lo0, lo1, hi0, hi1) = g
        Y0, X0, Y1, X1 = ys + cy0 + PADP, xs + cx0 + PADP, ys + cy1 + PADP, xs + cx1 + PADP
        box = lambda I: I[Y1, X1] - I[Y0, X1] - I[Y1, X0] + I[Y0, X0]     # noqa: E731
        nb, nv = box(st["Ibad"]), box(st["IV"])
        keep = (nb >= 10) & (nb.float() >= c.prune * nv.float())
        if kind == "air":     # free y: only where one of D's blobs ends at the pose's lowest or highest row (+-2):
            Xe = (xs.clamp(0, SW - 1) + PADP)[:, None]          # (half off screen: the screen's last column)
            edge = torch.zeros_like(keep)
            for E, h0, h1 in ((st["edge"], lo0, lo1), (st["top"], hi0, hi1)):   # an effect / the UI may touch one
                Yb = (ys + PADP)[:, None] + torch.arange(h0 - 2, h1 + 3, device=self.dev)[None]
                edge |= E[Yb.clamp(0, E.shape[0] - 1), Xe].any(dim=1)
            keep &= edge
        idx = keep.nonzero()[:, 0]
        if len(idx) == 0:
            return idx, None, None, None
        ar_h = torch.arange(0, bank.KH, c.s1_step, device=self.dev)
        ar_w = torch.arange(0, bank.KW, c.s1_step, device=self.dev)
        Srq, Sqq = [], []                    # (Sqq: Sqq and Srr = sum footprint |r|^2 V, one matmul)
        for i in range(0, len(idx), c.chunk):
            j = idx[i:i + c.chunk]
            R = (ys[j] - bank.T + PADP)[:, None, None] + ar_h[None, :, None]
            Cc = (xs[j] - bank.L + PADP)[:, None, None] + ar_w[None, None, :]
            Srq.append(st["Xa"][R, Cc].reshape(len(j), -1) @ Wa)
            Sqq.append(st["Xb"][R, Cc].reshape(len(j), -1) @ Wb)
        n = len(ks)
        Sb = torch.cat(Sqq).float()
        Srq, Sqq, Srr = torch.cat(Srq).float(), Sb[:, :n].clamp(min=1e-6), Sb[:, n:].clamp(min=1e-6)
        o = (Srq / Sqq).clamp(0, 1)
        gain = 2 * o * Srq - o * o * Sqq
        return idx, gain, o, gain / Srr

    # ---- stage 2
    def _stage2(self, bank, st, cands, L):
        """Per-pixel labels of the candidates [(gain, o*, pose k, fx, fy, window)] -> dicts (counts + SEEN pixels)."""
        torch = self.torch
        c = self.cfg
        n = len(cands)
        ks = torch.tensor([q[2] for q in cands], device=self.dev)
        fy = torch.tensor([q[4] for q in cands], device=self.dev)
        fx = torch.tensor([q[3] for q in cands], device=self.dev)
        rows = (fy - bank.T + PADP)[:, None] + torch.arange(bank.KH, device=self.dev)[None]     # (n, KH)
        cols = (fx - bank.L + PADP)[:, None] + torch.arange(bank.KW, device=self.dev)[None]     # (n, KW)
        R, Cc = rows[:, :, None], cols[:, None, :]
        r = st["r"][:, R, Cc].permute(1, 0, 2, 3)                   # (n, 3, KH, KW)
        B = st["B"][:, R, Cc].permute(1, 0, 2, 3)
        V = st["V"][R, Cc] > 0
        tol = st["tol"][R, Cc]
        on = st["on"][R, Cc] > 0
        a = bank.a[ks]                                               # (n, KH, KW)
        q = a[:, None] * (bank.s[ks] - B)                            # (n, 3, KH, KW)
        qn = q.abs().amax(dim=1)
        # the opacity: the mode of the per-pixel ratios r.q / q.q where the mob would change the pixel a lot (the
        # median fails once over half the body is covered: 2026-11-16, damage digits over a Zombie Mushroom)
        rq, qq = (r * q).sum(dim=1), (q * q).sum(dim=1).clamp(min=1e-6)
        use = (V & on & (qn > c.inf)).flatten(1)
        nb = c.o_bins
        b = (rq / qq * nb).round().flatten(1).clamp(-1, nb + 1).long()
        ok = use & (b >= 0) & (b <= nb)
        hist = torch.zeros((n, nb + 3), device=self.dev)
        hist.scatter_add_(1, torch.where(ok, b + 1, torch.zeros_like(b)), ok.float())
        hist[:, 0] = 0
        sm = hist[:, :-2] + hist[:, 1:-1] + hist[:, 2:]             # bins 0..nb, each with its 2 neighbours
        mode = sm.argmax(dim=1).float() / nb
        near = use & ((rq / qq).flatten(1) - mode[:, None]).abs().le(1.5 / nb)       # refined: least squares on
        mode = ((rq.flatten(1) * near).sum(1) / (qq.flatten(1) * near).sum(1).clamp(min=1e-6))  # the mode's pixels
        o = torch.tensor([q_[1] for q_ in cands], device=self.dev)
        o = torch.where(sm.amax(dim=1) > 0, mode, o).clamp(0, 1)
        inf = on & (o[:, None, None] * qn > c.inf)
        seen = inf & V & ((r - o[:, None, None, None] * q).abs().amax(dim=1) <= tol)
        absent = inf & V & ~seen & (r.abs().amax(dim=1) <= tol)
        cnt = torch.stack([inf.flatten(1).sum(1), seen.flatten(1).sum(1), absent.flatten(1).sum(1)], 1).cpu().numpy()
        seen_np = seen.cpu().numpy()
        o = o.cpu().numpy()
        out = []
        for j, (g, _, k, x, y, wi) in enumerate(cands):
            out.append({"bank": bank, "k": k, "feet": (x, y), "o": float(o[j]), "gain": g, "window": wi, "layer": L,
                        "n_inf": int(cnt[j, 0]), "n_seen": int(cnt[j, 1]), "n_abs": int(cnt[j, 2]),
                        "seen_px": seen_np[j], "box": (x - bank.L, y - bank.T)})
        return out

    def _pick(self, cands) -> list:
        """Greedy by SEEN count; an accepted mob's SEEN pixels are COVERED for the rest (on the CPU)."""
        c = self.cfg
        taken = np.zeros((PLAY_H + 2 * PADP, SW + 2 * PADP), bool)
        mobs = []
        for d in sorted(cands, key=lambda d: -d["n_seen"]):
            if d["n_inf"] <= 0 or d["n_seen"] < c.min_seen or d["n_seen"] < c.seen_min * d["n_inf"]:
                continue
            if d["n_abs"] > c.absent_max * d["n_inf"]:
                continue
            bx, by = d["box"]
            bank = d["bank"]
            sl = (slice(by + PADP, by + PADP + bank.KH), slice(bx + PADP, bx + PADP + bank.KW))
            px = d["seen_px"] & ~taken[sl]
            ns = int(px.sum())
            if ns < c.min_seen or ns < c.seen_min * d["n_inf"]:
                continue
            taken[sl] |= px
            pose, facing = bank.poses[d["k"]]
            mobs.append(FitMob(bank.id, pose, facing, d["feet"], round(d["o"], 3), round(ns / d["n_inf"], 3),
                               round(d["n_abs"] / d["n_inf"], 3), round(1 - (ns + d["n_abs"]) / d["n_inf"], 3),
                               d["n_inf"], ns, round(d["gain"], 2), d["layer"], d["window"]))
        return mobs

    # ---- the whole frame
    def fit(self, frame, C, windows, ui=None, keep_cands: bool = False):
        """`frame`: uint8 BGR (GPU tensor or array, >= PLAY_H rows); `C`: the scene camera; `windows`: [Window]
        (D patches, track predictions); `ui`: optional bool (PLAY_H, SW) tensor, True = may show a mob (default:
        everything; the UI is cover). -> [FitMob] (+ every stage-2 candidate's counts when keep_cands)."""
        torch, c = self.torch, self.cfg
        if not torch.is_tensor(frame):
            frame = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(self.dev)
        self._C = tuple(int(v) for v in C)
        sync = torch.cuda.synchronize if self.dev != "cpu" else (lambda: None)
        t0 = time.perf_counter()
        # positions per (layer, type, group): [(window, xs, ys)]
        plan = {}
        for wi, win in enumerate(windows):
            for tid in (win.types or self.banks):
                bank = self.banks.get(tid)
                if bank is None:
                    continue
                layers = self.layers if not bank.fly else sorted(self.fly_layers.get(tid, set(self.layers)))
                for L in layers:
                    for gi, g in enumerate(bank.groups):
                        p = self._positions(bank, win, L, g[0])
                        if p is not None:
                            plan.setdefault((L, tid, gi), []).append((wi, *p))
        t1 = time.perf_counter()
        imgs = {L: self._images(frame, self._C, L, ui) for L in sorted({k[0] for k in plan})}
        per = {}                                                     # (window, type) -> [(gain, o*, k, fx, fy, L)]
        n_pos = n_kept = 0
        for (L, tid, gi), items in plan.items():
            bank, g = self.banks[tid], self.banks[tid].groups[gi]
            wis = np.concatenate([np.full(len(x), wi) for wi, x, _ in items])
            xs = torch.from_numpy(np.concatenate([x for _, x, _ in items])).to(self.dev)
            ys = torch.from_numpy(np.concatenate([y for _, _, y in items])).to(self.dev)
            n_pos += len(xs)
            idx, gain, o, frac = self._stage1(bank, g, imgs[L], xs, ys)
            if gain is None:
                continue
            n_kept += len(idx)
            idx = idx.cpu().numpy()
            gain, o, frac = gain.cpu().numpy(), o.cpu().numpy(), frac.cpu().numpy()
            xs_np, ys_np = xs.cpu().numpy()[idx], ys.cpu().numpy()[idx]
            ks = g[1]
            for wi in np.unique(wis[idx]):
                rows = np.nonzero(wis[idx] == wi)[0]
                gw = gain[rows]                                      # (n_rows, n_g)
                nk = 4 * (c.top + 4 * (windows[wi].w * windows[wi].h // 4000))
                lst = per.setdefault((int(wi), tid), {"gain": [], "frac": []})
                for f in np.argsort(-gw, axis=None)[:nk]:
                    rr, p = divmod(int(f), gw.shape[1])
                    if gw[rr, p] <= 0:
                        break
                    j = rows[rr]
                    lst["gain"].append((float(gw[rr, p]), float(o[rows[rr], p]), ks[p], int(xs_np[j]), int(ys_np[j]), L))
                # faint (fading) or mostly covered mobs explain little energy but most of their own footprint's:
                # the best by explained fraction too, among candidates with >= 10 % of the window's best gain
                fw = np.where(gw >= 0.1 * gw.max(), frac[rows], -1.0)
                for f in np.argsort(-fw, axis=None)[:nk // 2]:
                    rr, p = divmod(int(f), fw.shape[1])
                    if fw[rr, p] <= 0:
                        break
                    j = rows[rr]
                    lst["frac"].append((float(fw[rr, p]), float(o[rows[rr], p]), ks[p], int(xs_np[j]), int(ys_np[j]), L,
                                        float(gw[rr, p])))
        t2 = time.perf_counter()
        by_lt = {}
        for (wi, tid), lists in per.items():
            top = c.top + 4 * (windows[wi].w * windows[wi].h // 4000)
            kept, seen = [], set()
            for name, cap in (("gain", top), ("frac", top // 2)):
                lists[name].sort(key=lambda t: -t[0])
                kept_here = []
                for t in lists[name]:
                    oo, k, x, y, L = t[1:6]
                    gn = t[6] if name == "frac" else t[0]
                    if (k, x, y, L) in seen or sum(1 for q in kept_here if abs(q[0] - x) <= 6 and abs(q[1] - y) <= 6) >= c.near:
                        continue
                    seen.add((k, x, y, L))
                    kept_here.append((x, y))
                    by_lt.setdefault((L, tid), []).append((gn, oo, k, x, y, wi))
                    if len(kept_here) >= cap:
                        break
        cands = []
        for (L, tid), lst in by_lt.items():
            for i in range(0, len(lst), 256):
                cands += self._stage2(self.banks[tid], imgs[L], lst[i:i + 256], L)
        t3 = time.perf_counter()
        mobs = self._pick(cands)
        sync()
        t4 = time.perf_counter()
        self.ms = {"fit": (t4 - t0) * 1000, "pos": (t1 - t0) * 1000, "s1": (t2 - t1) * 1000, "s2": (t3 - t2) * 1000,
                   "pick": (t4 - t3) * 1000, "cands": len(cands), "layers": len(imgs), "positions": n_pos,
                   "kept": n_kept}
        if keep_cands:
            return mobs, [{k: v for k, v in d.items() if k not in ("seen_px", "bank")} | {"type": d["bank"].id}
                          for d in cands]
        return mobs


def windows_from_patches(patches, pad: int = 0) -> list:
    """D patches [(x, y, w, h, area)] -> [Window]."""
    return [Window(int(x) - pad, int(y) - pad, int(w) + 2 * pad, int(h) + 2 * pad) for x, y, w, h, *_ in patches]
