"""The fit's candidate search (PLAN-fit-speed.md, step 3.2): the frame's pixels VOTE for (pose, feet) cells. NOT on
the live path (3.3 runs the fit in shadow). Reference: tools/perc/redesign/exp_vote.py (E9).

At native 1366x768 a frame shows a sprite's opaque pixels with exactly the client's colours (difference 0 on 98.6 %
of 827 k opaque pixels; the rest covered), a type's palette is tiny (Horny Mushroom 77 colours, Zombie 134) and
sprites are dithered (most 2x2 blocks are not one flat colour). So:
1. palette id per frame pixel: ONE lookup of its 24-bit colour in a 16 M-entry table (0 = no sprite colour here);
2. FEATURE = a 2x2 block of ids, all sprite colours, not one flat colour; the table built at load lists per feature
   key where it occurs in the map's sprites: (pose g, offset to the feet); keys with > max_entries places dropped;
3. every frame feature VOTES for the cells (g, feet x, feet y) its key allows;
4. EXCLUSIVE votes: a feature counts only for its best-voted cell(s) - the other poses / offsets that share part of a
   mob's picture lose it; ~1 cell per mob stays.
Work ~ the sprite-coloured pixels on screen (no windows, footholds, "air" case: flyers cost nothing extra). With a
scene (expected picture + known mask) features are taken only where the scene does NOT explain the pixel - D's raw
mask, |I - expected| > tol, or unknown scenery - so scenery that shares the palette votes for nothing (Ant Tunnel IV:
~68 k features a frame -> ~12 k). Without a scene every pixel may vote (a lost camera, maps without a clean scene).

Exact by construction: the cells are the prototype's (tests/test_vote.py). GPU, 3 sync points (the feature count,
the vote count, the result), int32 keys (mixed radix: (colours + 1)^4 < 2^31, i.e. <= 214 colours) and cells
where the map allows, else int64.
Fading mobs (`fade`, PLAN S4): the residue (unexplained, no palette colour) un-blended at each 48 px cell's own
alpha -> palette ids into the same picture, so opaque and fading mobs go through ONE vote.
Tints (PLAN S5): a frozen mob is drawn with every channel MULTIPLIED, frame = round(s m / 255) per channel, m = (B 255,
G 168, R 10) (exact on 8299 of 8299 opaque pixels of 3 mobs, tools/perc/redesign/exp_tint.py). The tinted palette
colours are extra LUT entries mapping to the SAME ids, so a frozen mob votes for its own cells; colours the tint
merges (R x 10 / 255: 40 groups of 2 on Ant Tunnel IV, 38 % of its opaque pixels) map to the group's most frequent
id - a block of such pixels may key wrong, the rest still give hundreds of votes. Which cells are tinted: stage 2
(fit.py) tries every candidate with the plain and each tinted sprite.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

PLAY_H, SW = 700, 1366
TINTS = {"frozen": (255, 168, 10)}      # BGR multipliers: frame = round(s m / 255) per channel (exp_tint.py)


def tinted(bgr, m) -> np.ndarray:
    """Sprite colours (..., 3) uint8 BGR under tint m -> uint8 (the client's rounding: round half up; s m / 255 is
    never a tie, 255 is odd)."""
    return np.floor(bgr.astype(np.float64) * np.asarray(m, np.float64) / 255 + 0.5).astype(np.uint8)


@dataclass
class Pose:
    type: int
    pose: str               # "<anim>_<i>" = the sprite file's stem
    facing: str             # "left" (as drawn in the file) | "right" (mirrored)
    ox: int                 # the feet in the picture (x from its left edge, y from its top)
    oy: int
    pic: np.ndarray         # BGRA uint8 (h, w, 4), already mirrored for "right"


def _pic(mob_dir: Path, f: dict, frames: dict, link_dir: Path | None):
    """A frame's picture, following the client's links: a 1x1 placeholder -> its `_inlink` frame ("anim/i") of the
    same mob, then the linked mob's file of that name."""
    import cv2

    def read(d, name):
        im = cv2.imread(str(d / name), cv2.IMREAD_UNCHANGED) if d is not None else None
        return im if im is not None and im.ndim == 3 and im.shape[2] == 4 and min(im.shape[:2]) > 1 else None

    names = [f["file"]]
    if f.get("_inlink"):
        anim, _, i = str(f["_inlink"]).partition("/")
        tgt = (frames.get(anim) or [])
        if i.isdigit() and int(i) < len(tgt):
            names.append(tgt[int(i)]["file"])
    for d in (mob_dir, link_dir):
        for nm in names:
            im = read(d, nm)
            if im is not None:
                return im
    return None


def load_poses(map_id: int, assets: Path, types=None) -> list:
    """Every pose (all animations, both facings) of the map's mob types (or `types`) -> [Pose]. Pictures with
    < 60 drawn pixels are skipped (as the detector does)."""
    assets = Path(assets)
    if types is None:
        m = json.loads((assets / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        types = sorted({int(x["id"]) for x in m.get("mobs") or []})
    out = []
    for t in types:
        d = assets / "mobs" / str(t)
        info = json.loads((d / "mob.json").read_text(encoding="utf-8"))
        link = info.get("link")
        link_dir = assets / "mobs" / str(int(link)) if link not in (None, "") else None
        frames = info.get("frames") or {}
        for anim, fs in frames.items():
            for i, f in enumerate(fs or []):
                im = _pic(d, f, frames, link_dir)
                if im is None or (im[..., 3] > 0).sum() < 60:
                    continue
                h, w = im.shape[:2]
                ox, oy = f.get("origin") or (w // 2, h)
                out.append(Pose(t, f"{anim}_{i}", "left", int(ox), int(oy), im))
                out.append(Pose(t, f"{anim}_{i}", "right", int(w - ox), int(oy), np.ascontiguousarray(im[:, ::-1])))
    return out


def _key24(bgr):
    return bgr[..., 0].astype(np.int64) | (bgr[..., 1].astype(np.int64) << 8) | (bgr[..., 2].astype(np.int64) << 16)


class Voter:
    FADE_TOLS = (2, 3, 4, 6)    # un-blend tolerance levels (one LUT each); opacity o needs >= 1.5 + 0.5 / o

    def __init__(self, poses: list, max_entries: int = 64, device=None, max_cells: int = 512, tints=None,
                 fades: bool = True):
        """`poses`: load_poses(...) (the cell's g = the index in it). `max_cells`: the most cells `cells` returns
        (the best by exclusive votes). `tints`: {name: BGR multiplier} whose colours join the LUT (default TINTS;
        {} = none). `fades` False: no fade tables (`fade` unusable; ~170 MB less GPU memory: the drop finder)."""
        import torch
        self.torch = torch
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.poses, self.G, self.max_cells = poses, len(poses), max_cells
        self.type_g = np.array([p.type for p in poses])
        # palette: every colour of an opaque sprite pixel -> id 1.. (0 = none)
        allk = np.concatenate([_key24(p.pic[..., :3])[p.pic[..., 3] == 255] for p in poses])
        cols, freq = np.unique(allk, return_counts=True)
        assert len(cols) < 32767
        self.n_colors = len(cols)
        lut = np.zeros(1 << 24, np.int16)
        lut[cols] = np.arange(1, len(cols) + 1)
        vote_lut = lut.copy()       # `lut` stays the plain palette (the sprites' own ids below)
        # tints: each tinted colour -> the id of its most frequent source colour; a plain colour keeps its own id
        self.tints = dict(TINTS if tints is None else tints)
        self.tint_merged = {}
        bgr = np.stack([cols & 255, (cols >> 8) & 255, cols >> 16], 1).astype(np.uint8)
        for name, m in self.tints.items():
            tk = _key24(tinted(bgr, m))
            for i in np.argsort(-freq, kind="stable"):
                if vote_lut[tk[i]] == 0:
                    vote_lut[tk[i]] = i + 1
            self.tint_merged[name] = len(cols) - len(np.unique(tk))
        self.lut = torch.from_numpy(vote_lut).to(self.dev)
        # fades: LUTs with +-t levels around every palette colour (an un-blended pixel is off by ~(0.5 + the scene's
        # error) / opacity, and by the alpha grid's step), the nearest colour claiming a shared cell first; one LUT
        # per level of FADE_TOLS (the opacity picks it). Indexed by (b + 1) + 258 (g + 1) + 258^2 (r + 1) with each
        # channel clamped to -1..256: a value out of 0..255 lands on the zero border, so the range check is the
        # table's (one gather, no compares). + the palette (id -> BGR) and the sprites' adjacent colour pairs.
        cb, cg, cr = cols & 255, (cols >> 8) & 255, cols >> 16
        idn = np.arange(1, len(cols) + 1, dtype=np.int16)
        luts = []
        for t in self.FADE_TOLS if fades else ():
            lt = np.zeros((258, 258, 258), np.int16)
            d = np.arange(-t, t + 1)
            offs = np.stack(np.meshgrid(d, d, d, indexing="ij"), -1).reshape(-1, 3)
            for dr, dg, db in offs[np.argsort((offs ** 2).sum(1), kind="stable")]:
                rr, gg, bb = np.clip(cr + dr, 0, 255) + 1, np.clip(cg + dg, 0, 255) + 1, np.clip(cb + db, 0, 255) + 1
                free = lt[rr, gg, bb] == 0
                lt[rr[free], gg[free], bb[free]] = idn[free]
            luts.append(lt.reshape(-1))
        self.lut_tol = torch.from_numpy(np.concatenate(luts)).to(self.dev) if luts else None
        self.k258 = torch.tensor([1, 258, 258 * 258], dtype=torch.int32, device=self.dev)   # integers: the key
                                                                       # passes 2^24 (fp32 would round it)
        pal = np.zeros((len(cols) + 1, 3), np.float32)
        pal[1:] = np.stack([cb, cg, cr], 1)
        self.pal = torch.from_numpy(pal).to(self.dev)
        self.radix = r = self.n_colors + 1                            # key = ((a r + b) r + c) r + d
        kdt = np.int32 if r ** 4 < 2 ** 31 else np.int64
        self.kdt = torch.int32 if kdt is np.int32 else torch.int64
        # the cell space: feet up to PAD px off screen (a sprite's size) -> one integer per (g, feet)
        self.pad = int(max(max(p.pic.shape[:2]) for p in poses)) + 2
        self.WW, self.HH = SW + 2 * self.pad, PLAY_H + 2 * self.pad
        self.CW = self.WW * self.HH
        cdt = np.int32 if self.G * self.CW < 2 ** 31 - 1 else np.int64
        # features: 2x2 blocks of ids, all opaque, not one flat colour
        ks, offs, gs, self.n_feat = [], [], [], []
        pair = np.zeros((r, r) if fades else (1, 1), bool)
        for g, p in enumerate(poses):
            ids = np.where(p.pic[..., 3] == 255, lut[_key24(p.pic[..., :3])], 0).astype(np.int64)
            if fades:
                lp, rp = ids[:, :-1], ids[:, 1:]
                mm = (lp > 0) & (rp > 0) & (lp != rp)
                pair[lp[mm], rp[mm]] = True
            a, bb, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
            ok = (a > 0) & (bb > 0) & (c > 0) & (d > 0) & ~((a == bb) & (a == c) & (a == d))
            yy, xx = np.nonzero(ok)
            ks.append(((a[ok] * r + bb[ok]) * r + c[ok]) * r + d[ok])
            # cell = g * CW + (feet y + pad) * WW + (feet x + pad), feet = block's top-left - (xx - ox, yy - oy):
            # the entry's part of it, so that a vote is ONE add: cell = off[e] + (y * WW + x) of the frame block
            offs.append(g * self.CW + (self.pad - (yy - p.oy)) * self.WW + (self.pad - (xx - p.ox)))
            gs.append(np.full(len(yy), g))
            self.n_feat.append(int(ok.sum()))
        self.pair_ok = torch.from_numpy(pair.reshape(-1)).to(self.dev)    # [left id * radix + right id]
        k, off, gg = np.concatenate(ks), np.concatenate(offs), np.concatenate(gs)
        order = np.argsort(k, kind="stable")
        k, off, gg = k[order], off[order], gg[order]
        uk, count = np.unique(k, return_counts=True)
        self.raw_entries, self.raw_keys = len(k), len(uk)
        sel = np.repeat(count <= max_entries, count)                  # a feature in too many places says little
        self.kept = np.bincount(gg[sel], minlength=self.G)
        k, off = k[sel], off[sel]
        uk, start, count = np.unique(k, return_index=True, return_counts=True)
        T = lambda a, dt: torch.from_numpy(np.ascontiguousarray(a.astype(dt))).to(self.dev)  # noqa: E731
        self.uk, self.start, self.count = T(uk, kdt), T(start, np.int64), T(count, np.int64)
        self.off = T(off, cdt)
        self.entries = len(k)
        for t in sorted(set(self.type_g.tolist())):
            if self.kept[self.type_g == t].sum() == 0:
                log.warning("vote: mob type %s has no feature (no opaque dithered pixels / a link not followed): "
                            "the vote cannot see it", t)
        self.ms = {}

    def stats(self) -> str:
        c = self.count.cpu().numpy()
        return (f"{self.G} poses (both facings), palette {self.n_colors} colours (keys "
                f"{str(self.kdt).split('.')[-1]}), features {self.raw_entries} with {self.raw_keys} keys -> kept "
                f"{self.entries} entries, {len(self.uk)} keys; places per key p50 {np.median(c):.0f} max {c.max()}; "
                f"tints {', '.join(f'{k} (merges {v} colours)' for k, v in self.tint_merged.items()) or 'none'}")

    # ---- per frame
    def ids(self, frame, exp=None, known=None, tol: float = 4.0, resid: bool = False):
        """Palette id per pixel of the play area: (PLAY_H, SW) int16, 0 = no sprite colour. `frame`: uint8 BGR
        tensor (>= PLAY_H rows). With `exp` (float (PLAY_H, SW, 3), the expected scene) and `known` (bool): only
        where the scene does not explain the pixel (|I - exp| > tol in some channel, or unknown). `resid`: also
        return r = I - exp and its max over the channels (the fade search's inputs)."""
        torch = self.torch
        f = frame[:PLAY_H]
        fi = f.int()
        ids = self.lut[fi[..., 0] | (fi[..., 1] << 8) | (fi[..., 2] << 16)]
        if exp is None:
            return ids
        r = f.float() - exp
        mag = r.abs().amax(dim=2)
        d = mag > tol
        if known is not None:
            d |= ~known
        ids = torch.where(d, ids, torch.zeros_like(ids))
        return (ids, r, mag) if resid else ids

    prof = False                # tools: per-part ms of the fade search in fade_ms (synchronized)

    def _mark(self, name):
        if not self.prof:
            return
        import time
        self.torch.cuda.synchronize()
        now = time.perf_counter()
        if name is None:
            self.fade_ms = {}
        else:
            self.fade_ms[name] = (now - self._t0) * 1000
        self._t0 = now

    @staticmethod
    def _key(sp):
        """Clamped (-1..256) BGR (..., 3) float -> b + 258 g + 258^2 r (the LUT index before its offset): the low
        part in float (exact below 2^24), the high part as an integer (the whole key passes 2^24)."""
        return sp[..., 2].long() * (258 * 258) + (sp[..., 0] + 258 * sp[..., 1]).long()

    def _level(self, o, scale: bool):
        """The LUT offset for opacity o (tensor): the first FADE_TOLS level >= 1.5 + 0.5 / o (+ the key's -1 shift);
        scale False: always the first (+-2)."""
        base = 1 + 258 + 258 * 258
        if not scale:
            return self.torch.full_like(o, base, dtype=self.torch.long)
        need = 1.5 + 0.5 / o.clamp(min=1e-3)
        if getattr(self, "_tols", None) is None:
            self._tols = self.torch.tensor(self.FADE_TOLS, dtype=o.dtype, device=o.device)
        li = (need[..., None] > self._tols).sum(dim=-1).clamp_(max=len(self.FADE_TOLS) - 1)
        return li * 258 ** 3 + base

    def fade(self, ids, r, mag, exp, valid, me=None, tol: float = 4.0, strong: float = 24.0, n_min: int = 20,
             cell: int = 48, cell_min: int = 12, lo: int = 38, hi: int = 252, step: int = 3, ratio: float = 0.0,
             scale: bool = True, report: bool = False):
        """Fading mobs (I = B + o (s - B), one o per mob, exact to the level on native frames) INTO `ids` (in place).
        The RESIDUE = valid pixels the scene does not explain (|I - B| > tol) that are no palette colour (ids == 0),
        outside `me` (our body box x0, y0, x1, y1). Un-blended at alpha, s' = B + (I - B) 255 / alpha, a fading mob's
        pixels become its sprite colours, so horizontally adjacent pairs become colour pairs that occur in a sprite.
        1. the strong pairs (both |I - B| >= strong) on a quarter of the positions (even rows, even pair columns);
           none if fewer than n_min;
        2. per 48 px screen cell the alpha lo..hi (step) with the most hitting pairs; a cell with >= cell_min has a
           fade, its o REFINED by least squares over the pairs that hit (o = sum r.q / sum q.q, q = the matched
           palette colour - B); a cell without one takes its 3x3 neighbourhood's best (a mob's edge in the next cell).
           One alpha PER CELL, no cap a frame (each fading mob has its own o; dying mobs fade out one by one);
        3. every residue pixel of a cell with an alpha un-blended at it -> palette id with +-2 levels, written into
           `ids` (the residue's ids are 0): the opaque and the fading mobs go through ONE vote.
        Sparse after one nonzero (the residue list). -> (ids, [(alpha 0..255, pairs)] per fade cell if `report` (one
        more sync: tools) else None, counters). Syncs: 2 (1 without pairs)."""
        torch = self.torch
        self._mark(None)
        res = (mag > tol) & valid & (ids == 0)
        if me is not None:
            x0, y0, x1, y1 = (max(int(v), 0) for v in me)
            res[y0:y1, x0:x1] = False
        yx = res.nonzero()                                            # sync 1: the residue
        info = {"residue": len(yx), "pairs": 0}
        self._mark("residue")
        if len(yx) < 2 * n_min:
            return ids, None, info
        y, x = yx[:, 0], yx[:, 1]
        m = mag[y, x]
        xr = (x + 1).clamp_(max=SW - 1)
        pq = ((y & 1) == 0) & ((x & 1) == 0) & (x < SW - 1) & (m >= strong) & res[y, xr] & (mag[y, xr] >= strong)
        pi = pq.nonzero()[:, 0]                                       # sync 2: the pairs
        info["pairs"] = len(pi)
        self._mark("pairs")
        if len(pi) < n_min:
            return ids, None, info
        py, px = y[pi], x[pi]
        gk = (lo, hi, step, ratio, scale)
        if getattr(self, "_grid", (None,))[0] != gk:                  # the alpha grid, made once
            if ratio > 1:                                             # geometric: the same relative step everywhere
                al = torch.tensor(lo * ratio ** np.arange(int(np.log(hi / lo) / np.log(ratio)) + 1),
                                  dtype=torch.float32, device=self.dev)
            else:
                al = torch.arange(lo, hi + 1, step, device=self.dev, dtype=torch.float32)
            self._grid = (gk, al, (255.0 / al)[None, None, :, None], self._level(al / 255, scale)[None, None, :])
        _, al, k, lv = self._grid
        B = torch.stack([exp[py, px], exp[py, px + 1]], 1)            # (pairs, 2, 3): the pair's two pixels
        R = torch.stack([r[py, px], r[py, px + 1]], 1)
        sp = torch.addcmul(B[:, :, None], R[:, :, None], k).round_().clamp_(-1, 256)   # (pairs, 2, alphas, 3)
        two = self.lut_tol[self._key(sp) + lv]                        # (pairs, 2, alphas) ids, 0 = none
        hit = self.pair_ok[two[:, 0].int() * self.radix + two[:, 1]]  # (pairs, alphas)
        wc, hc = -(-SW // cell), -(-PLAY_H // cell)
        ci = (py // cell) * wc + px // cell
        hist = torch.zeros((hc * wc, len(al)), device=self.dev).index_add_(0, ci, hit.float())
        best, at = hist.max(dim=1)
        # refine every cell at its best alpha: least squares over its hitting pairs' pixels
        a_p = at[ci]
        i_p = torch.arange(len(py), device=self.dev)
        h_p = hit[i_p, a_p].float()
        q = self.pal[two[i_p, :, a_p].int()] - B                      # (pairs, 2, 3)
        rq = torch.zeros(hc * wc, device=self.dev).index_add_(0, ci, (R * q).sum(dim=(1, 2)) * h_p)
        qq = torch.zeros(hc * wc, device=self.dev).index_add_(0, ci, (q * q).sum(dim=(1, 2)) * h_p)
        ok = (best >= cell_min) & (qq > 0)
        o_c = torch.where(ok, rq / qq.clamp(min=1e-6), torch.zeros_like(rq)).clamp_(0, 1)
        cnt = torch.where(ok, best, torch.full_like(best, -1.0)).view(1, 1, hc, wc)
        mp, nb = torch.nn.functional.max_pool2d(cnt, 3, 1, 1, return_indices=True)
        o_c = torch.where(ok, o_c, torch.where(mp.view(-1) > 0, o_c[nb.view(-1)], torch.zeros_like(o_c)))
        self._mark("alpha")
        # the residue un-blended at its cell's alpha (a cell without one: alpha 1e-6 - a residue pixel differs from
        # the scene by > tol in some channel, so that channel leaves -1..256 and the LUT says 0)
        c_r = (y // cell) * wc + x // cell
        lvc = self._level(o_c, scale)
        sp = torch.addcdiv(exp[y, x], r[y, x], torch.where(o_c > 0, o_c, torch.full_like(o_c, 1e-6))[c_r][:, None])
        ids[y, x] = self.lut_tol[self._key(sp.round_().clamp_(-1, 256)) + lvc[c_r]]
        self._mark("unblend")
        alphas = None
        if report:
            c = ok.nonzero()[:, 0]
            alphas = [(round(255 * float(o), 1), int(n)) for o, n in zip(o_c[c].cpu().numpy(), best[c].cpu().numpy())]
        return ids, alphas, info

    def cells(self, ids, tmin: int = 24):
        """Palette-id picture -> the cells with >= tmin EXCLUSIVE votes, best first (at most max_cells):
        numpy (g, feet x, feet y, raw votes, exclusive votes) + counters."""
        torch = self.torch
        i32 = torch.int32
        a, bb, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
        mn = torch.minimum(torch.minimum(a, bb), torch.minimum(c, d))
        mx = torch.maximum(torch.maximum(a, bb), torch.maximum(c, d))
        ok = (mn > 0) & (mx != mn)
        p = ok.view(-1).nonzero()[:, 0]                               # sync 1: the feature count
        n_feat = len(p)
        z = np.zeros(0, int)
        empty = (z, z, z, z, z, {"feat": n_feat, "votes": 0})
        if n_feat == 0:
            return empty
        W1 = ids.shape[1] - 1
        yi, xi = (p // W1).to(i32), (p % W1).to(i32)
        r = self.radix
        key = (((a.to(self.kdt) * r + bb) * r + c) * r + d).view(-1)[p]
        j = torch.searchsorted(self.uk, key).clamp_(max=len(self.uk) - 1)
        cnt = torch.where(self.uk[j] == key, self.count[j], torch.zeros_like(j))
        total = int(cnt.sum())                                        # sync 2: the vote count
        if total == 0:
            return empty
        src = torch.repeat_interleave(torch.arange(n_feat, device=self.dev), cnt, output_size=total)
        first = torch.cumsum(cnt, 0) - cnt
        e = self.start[j][src] + (torch.arange(total, device=self.dev) - first[src])
        pix = (yi * self.WW + xi).to(self.off.dtype)
        cell = self.off[e] + pix[src]
        cs, perm = torch.sort(cell)
        src = src[perm]
        first = torch.ones(total, dtype=torch.long, device=self.dev)
        first[1:] = cs[1:] != cs[:-1]
        rid = torch.cumsum(first, 0) - 1                              # each vote's cell, numbered 0.. (sorted)
        z = torch.zeros(total, dtype=torch.long, device=self.dev)
        n_run = z.index_add(0, rid, torch.ones_like(rid))             # votes per cell
        nv = n_run[rid]                                               # each vote: its cell's total
        best = torch.zeros(n_feat, dtype=nv.dtype, device=self.dev).scatter_reduce_(0, src, nv, "amax",
                                                                                     include_self=False)
        win = (nv == best[src]).long()                                # the feature's best cell(s) keep it
        ex_run = z.index_add(0, rid, win)                             # exclusive votes per cell
        k = min(self.max_cells, total)
        top, at = torch.topk(ex_run, k)
        cell_run = torch.zeros(total, dtype=cs.dtype, device=self.dev).scatter_(0, rid, cs)
        out = torch.stack([cell_run[at].long(), n_run[at], top]).cpu().numpy()   # sync 3: the result
        keep = out[2] >= tmin
        cell, nv, ex = out[0][keep], out[1][keep], out[2][keep]
        g, rem = cell // self.CW, cell % self.CW
        return (g, rem % self.WW - self.pad, rem // self.WW - self.pad, nv, ex,
                {"feat": n_feat, "votes": total, "full": bool(keep.all() and k == self.max_cells)})
