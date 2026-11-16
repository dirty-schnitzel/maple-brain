"""The fit (PLAN-perception.md step 3.2): which mob - type, pose, facing, feet, opacity - explains a window of the
frame, pixel by pixel, with the scene split at the mob's layer. NOT on the live path: 3.3 runs it in shadow.

The client draws a mob on foothold layer L over B = the backs + tiles / objects of layers <= L and under F, A = the
tiles / objects of layers > L + the front backs (Scene.split), with the sprite's colour s, alpha a and an opacity o
(1, or less while it fades in / out):
    I = F + (1 - A) * (B + o * a * (s - B))
Where the front is see-through (A < 0.98): I' = (I - F) / (1 - A), so  r = I' - B = o * q,  q = a * (s - B).

Stage 1 - every candidate (type x pose x facing x feet) of a window, V = the valid pixels (B known, the front
see-through, not the UI, on screen):
    least squares o* = Srq / Sqq (clamped 0..1), gain = 2 o* Srq - o*^2 Sqq (how much of the window's difference from
    B it explains), with
    Srq = sum V r.q = sum (a s).(r V) - sum a (B.r V)
    Sqq = sum V q.q = sum (a^2 |s|^2) V - 2 sum (a^2 s).(B V) + sum a^2 (|B|^2 V)
    = exact correlations of fixed sprite images with fixed window images: one grouped conv2d per (window, layer,
    type) - no FFT (its error is absolute: wrong on near-flat windows, where the fit must be exact).
    Feet: walkers only on the footholds of layer L crossing the window (+-fh_dy px), flyers anywhere.
Stage 2 - the best few per window and type, per pixel of the sprite where the mob would change the picture
(informative: o |q| > `inf` levels in some channel, on screen):
    SEEN     valid and I' = B + o q within tol (tol / (1 - A) under a see-through front)
    ABSENT   valid, not SEEN and I' = B within tol: the pixel shows the scene where the mob would be
    COVERED  the rest: not valid (front opaque, UI, unknown scenery) or neither - something drawn over it (an
             effect, a player, another mob)
    o = the median of the per-pixel ratios r.q / q.q (robust to cover; the stage-1 o* is pulled by covered pixels).
A mob = SEEN share >= seen_min and ABSENT share <= absent_max (shares of the informative pixels) and >= min_seen
SEEN pixels; accepted greedily by SEEN count, every accepted mob's SEEN pixels count as COVERED for the others.
"""
import json
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
    top: int = 8                # stage-2 candidates per window and type (+ 4 per 4000 px of window)
    near: int = 3               # of them at most this many within 6 px of each other (poses of one mob)
    margin: int = 8             # a candidate's body overlaps its window by >= this (px)
    fh_dy: int = 2              # feet y within +- this of the foothold
    air: int = 64               # jump poses: feet up to this far above a foothold
    o_bins: int = 128           # the opacity: the mode of the per-pixel ratios, this many bins over 0..1
    half: bool = True           # stage 1 in fp16 on the GPU (fp32 accumulation)


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
    """One mob type's poses (every animation, both facings) in a common box around the feet: kernel row T / column
    L = the feet; + the grouped conv weights of stage 1."""

    def __init__(self, mob_id: int, mob_dir: Path, torch, dev, half: bool):
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
        s1 = s / 255.0
        w = np.zeros((2 * n, 5, KH, KW), np.float32)
        # group 0 (inputs r'V b g r, (B'.r')V, 0) -> Srq; group 1 (inputs V, B'V b g r, |B'|^2 V) -> Sqq
        w[:n, 0:3] = a[:, None] * s1
        w[:n, 3] = -a
        a2 = a * a
        w[n:, 0] = a2 * (s1 ** 2).sum(axis=1)
        w[n:, 1:4] = -2 * a2[:, None] * s1
        w[n:, 4] = a2
        dt = torch.float16 if half and dev != "cpu" else torch.float32
        # pose groups by where the feet may be: "ground" on a foothold, "air" anywhere above one (jumps: the
        # synthetic set lifts them 10-45 px) - a flyer's every pose is "air" with free y
        air = [k for k, (p, _) in enumerate(self.poses) if self.fly or p.startswith("jump")]
        ground = [k for k in range(n) if k not in air]
        self.groups = []
        for kind, ks in (("ground", ground), ("air", air)):
            if ks:
                sel = np.array(ks + [n + k for k in ks])
                self.groups.append((kind, ks, torch.from_numpy(w[sel]).to(dev).to(dt)))


class Fitter:
    def __init__(self, scene, map_id: int, assets: Path, cfg: FitConfig | None = None, types=None):
        """`scene`: a Scene with layers (scene.split); `assets`: assets/mcw (maps/<id>/map.json, mobs/<id>/)."""
        self.scene, self.torch, self.dev = scene, scene.torch, scene.dev
        self.cfg = cfg or FitConfig()
        m = json.loads((Path(assets) / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in m.get("mobs") or []}) if types is None else list(types)
        self.banks = {i: _Bank(i, Path(assets) / "mobs" / str(i), self.torch, self.dev, self.cfg.half) for i in ids}
        fh = {int(k): f for k, f in (m.get("footholds") or {}).items()}
        self.fh = [f for f in fh.values() if f["x1"] != f["x2"]]
        # a flyer is drawn on the layer of the foothold it belongs to: the layers of its spawns' footholds
        self.fly_layers = {}
        for sp in m.get("mobs") or []:
            f = fh.get(int(sp.get("footholdId", -1)))
            if f is not None:
                self.fly_layers.setdefault(int(sp["id"]), set()).add(int(f.get("layerId", 0)))
        self.layers = sorted({int(f.get("layerId", 0)) for f in self.fh})
        self.ms = {}

    # ---- per frame: the window images of each layer
    def _images(self, frame, C, L, ui):
        """Padded (PADP) images for layer L: X (1, 10, H, W) stage-1 inputs (/255 units) and the stage-2 ones."""
        torch = self.torch
        B, kB, F, A = self.scene.split(C, L)
        I = frame[:PLAY_H].float()
        V = kB & (A < 0.98)
        if ui is not None:
            V &= ui
        den = (1 - A).clamp(min=0.02)
        Ip = (I - F) / den[..., None]
        r = torch.where(V[..., None], Ip - B, torch.zeros_like(B))
        Vf = V.float()
        B1, r1 = B / 255.0, r / 255.0
        X = torch.zeros((10, PLAY_H, SW), device=self.dev)
        X[0:3] = (r1 * Vf[..., None]).permute(2, 0, 1)
        X[3] = (B1 * r1).sum(dim=2) * Vf
        X[5] = Vf
        X[6:9] = (B1 * Vf[..., None]).permute(2, 0, 1)
        X[9] = (B1 * B1).sum(dim=2) * Vf
        P = PADP
        Xp = torch.nn.functional.pad(X, (P, P, P, P))[None]
        if self.cfg.half and self.dev != "cpu":
            Xp = Xp.half()
        pad = lambda t: torch.nn.functional.pad(t, (P, P, P, P))      # noqa: E731
        st = {"r": pad(r.permute(2, 0, 1)), "B": pad(B.permute(2, 0, 1)), "V": pad(Vf),
              "tol": pad(self.cfg.tol / den), "on": pad(torch.ones((PLAY_H, SW), device=self.dev))}
        return Xp, st

    # ---- stage 1
    def _positions(self, bank, win, L):
        """Feet positions of `bank` in `win` on layer L -> {"ground" | "air": (fx0, fy0, allowed (Hout, Wout) bool
        np)}: ground = on a foothold of layer L (+- fh_dy), air = up to `air` px above one (a flyer: anywhere)."""
        c = self.cfg
        fx0 = max(win.x - bank.R + c.margin, -bank.R + 10)
        fx1 = min(win.x + win.w + bank.L - c.margin, SW + bank.L - 10)
        fy0 = win.y - bank.Bt + c.margin
        fy1 = win.y + win.h + bank.T - c.margin
        if fx1 < fx0 or fy1 < fy0:
            return {}
        shape = (fy1 - fy0 + 1, fx1 - fx0 + 1)
        if bank.fly:
            if L not in self.fly_layers.get(bank.id, {L}):
                return {}
            return {"air": (fx0, fy0, np.ones(shape, bool))}
        C = self._C
        ok = {"ground": np.zeros(shape, bool), "air": np.zeros(shape, bool)}
        xs = np.arange(fx0, fx1 + 1)
        for f in self.fh:
            if int(f.get("layerId", 0)) != L:
                continue
            ax, bx = sorted((f["x1"] - C[0], f["x2"] - C[0]))
            sel = (xs >= ax) & (xs <= bx)
            if not sel.any():
                continue
            ys = f["y1"] - C[1] + (xs[sel] + C[0] - f["x1"]) * (f["y2"] - f["y1"]) / (f["x2"] - f["x1"])
            yi = np.round(ys).astype(int) - fy0
            ci = np.nonzero(sel)[0]
            for kind, dys in (("ground", range(-c.fh_dy, c.fh_dy + 1)), ("air", range(-c.air, c.fh_dy + 1))):
                for dy in dys:
                    y = yi + dy
                    k = (y >= 0) & (y < shape[0])
                    ok[kind][y[k], ci[k]] = True
        out = {}
        for kind, m in ok.items():
            if m.any():
                rows = np.nonzero(m.any(axis=1))[0]
                out[kind] = (fx0, fy0 + int(rows[0]), m[rows[0]:rows[-1] + 1])
        return out

    def _stage1(self, bank, Xp, pos, wi):
        """Candidates [(gain, o*, pose k, fx, fy, window)] of every pose group at its allowed positions."""
        out = []
        for kind, ks, wt in bank.groups:
            if kind in pos:
                out += self._stage1g(bank, ks, wt, Xp, *pos[kind], wi)
        return out

    def _stage1g(self, bank, ks, wt, Xp, fx0, fy0, ok, wi):
        """One pose group: candidates at `ok` positions (feet (fx0, fy0) = ok[0, 0])."""
        torch = self.torch
        Ho, Wo = ok.shape
        y0, x0 = fy0 - bank.T + PADP, fx0 - bank.L + PADP
        strip = Xp[:, :, y0:y0 + Ho + bank.KH - 1, x0:x0 + Wo + bank.KW - 1]
        out = torch.nn.functional.conv2d(strip, wt, groups=2)[0].float()           # (2P, Ho, Wo)
        n = len(ks)
        Srq, Sqq = out[:n], out[n:].clamp(min=1e-6)
        o = (Srq / Sqq).clamp(0, 1)
        gain = 2 * o * Srq - o * o * Sqq
        okt = torch.from_numpy(ok).to(self.dev)
        gain = torch.where(okt[None], gain, torch.full_like(gain, -1.0))
        r = self.cfg.near
        peak = torch.nn.functional.max_pool2d(gain[None], 2 * r + 1, 1, r)[0]
        gain = torch.where((gain >= peak) & (gain > 0), gain, torch.full_like(gain, -1.0))
        win_area = Ho * Wo
        k = min(int((gain > 0).sum()), 4 * (self.cfg.top + 4 * (win_area // 4000)))
        if k == 0:
            return []
        v, idx = gain.flatten().topk(k)
        idx, v = idx.cpu().numpy(), v.cpu().numpy()
        o = o.flatten()[torch.from_numpy(idx).to(self.dev)].cpu().numpy()
        out, kept = [], []
        top = self.cfg.top + 4 * (win_area // 4000)
        for g, oo, i in zip(v, o, idx):
            p, rem = divmod(int(i), Ho * Wo)
            yy, xx = divmod(rem, Wo)
            fx, fy = fx0 + xx, fy0 + yy
            if sum(1 for q in kept if abs(q[0] - fx) <= 6 and abs(q[1] - fy) <= 6) >= self.cfg.near:
                continue
            kept.append((fx, fy))
            out.append((float(g), float(oo), ks[p], fx, fy, wi))
            if len(out) >= top:
                break
        return out

    # ---- stage 2
    def _stage2(self, bank, st, cands, L):
        """Per-pixel labels of the candidates -> list of dicts (counts + the pixel sets for the greedy pick)."""
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
        out = []
        n_inf = inf.flatten(1).sum(dim=1).cpu().numpy()
        n_seen = seen.flatten(1).sum(dim=1).cpu().numpy()
        n_abs = absent.flatten(1).sum(dim=1).cpu().numpy()
        o = o.cpu().numpy()
        for j, (g, _, k, x, y, wi) in enumerate(cands):
            out.append({"bank": bank, "k": k, "feet": (x, y), "o": float(o[j]), "gain": g, "window": wi, "layer": L,
                        "n_inf": int(n_inf[j]), "n_seen": int(n_seen[j]), "n_abs": int(n_abs[j]),
                        "seen_px": seen[j], "box": (x - bank.L, y - bank.T)})
        return out

    def _pick(self, cands) -> list:
        """Greedy by SEEN count; an accepted mob's SEEN pixels are COVERED for the rest."""
        torch, c = self.torch, self.cfg
        taken = torch.zeros((PLAY_H + 2 * PADP, SW + 2 * PADP), dtype=torch.bool, device=self.dev)
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
        (D patches, track predictions); `ui`: bool (PLAY_H, SW) tensor, True = world (hud.ui_mask). -> [FitMob]
        (+ every stage-2 candidate's counts when keep_cands)."""
        import time
        torch = self.torch
        if not torch.is_tensor(frame):
            frame = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(self.dev)
        self._C = tuple(int(v) for v in C)
        sync = torch.cuda.synchronize if self.dev != "cpu" else (lambda: None)
        t0 = time.perf_counter()
        imgs, cands = {}, []
        for wi, win in enumerate(windows):
            for tid in (win.types or self.banks):
                bank = self.banks.get(tid)
                if bank is None:
                    continue
                layers = self.layers if not bank.fly else sorted(self.fly_layers.get(tid, set(self.layers)))
                per = []
                for L in layers:
                    pos = self._positions(bank, win, L)
                    if not pos:
                        continue
                    if L not in imgs:
                        imgs[L] = self._images(frame, self._C, L, ui)
                    per += [(g, L) for g in self._stage1(bank, imgs[L][0], pos, wi)]
                if not per:
                    continue
                per.sort(key=lambda t: -t[0][0])
                per = per[:self.cfg.top + 4 * ((win.w * win.h) // 4000)]
                for L in {L for _, L in per}:
                    cands += self._stage2(bank, imgs[L][1], [g for g, LL in per if LL == L], L)
        mobs = self._pick(cands)
        sync()
        self.ms = {"fit": (time.perf_counter() - t0) * 1000, "cands": len(cands), "layers": len(imgs)}
        if keep_cands:
            return mobs, [{k: v for k, v in d.items() if k not in ("seen_px", "bank")} | {"type": d["bank"].id}
                          for d in cands]
        return mobs


def windows_from_patches(patches, pad: int = 0) -> list:
    """D patches [(x, y, w, h, area)] -> [Window]."""
    return [Window(int(x) - pad, int(y) - pad, int(w) + 2 * pad, int(h) + 2 * pad) for x, y, w, h, *_ in patches]

