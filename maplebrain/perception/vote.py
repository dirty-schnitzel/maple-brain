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
Fades (un-blended residue, PLAN S4) and tints (more LUT colours, S5) are not here yet.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

PLAY_H, SW = 700, 1366


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
    def __init__(self, poses: list, max_entries: int = 64, device=None, max_cells: int = 512):
        """`poses`: load_poses(...) (the cell's g = the index in it). `max_cells`: the most cells `cells` returns
        (the best by exclusive votes)."""
        import torch
        self.torch = torch
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.poses, self.G, self.max_cells = poses, len(poses), max_cells
        self.type_g = np.array([p.type for p in poses])
        # palette: every colour of an opaque sprite pixel -> id 1.. (0 = none)
        cols = np.unique(np.concatenate([_key24(p.pic[..., :3])[p.pic[..., 3] == 255] for p in poses]))
        assert len(cols) < 32767
        self.n_colors = len(cols)
        lut = np.zeros(1 << 24, np.int16)
        lut[cols] = np.arange(1, len(cols) + 1)
        self.lut = torch.from_numpy(lut).to(self.dev)
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
        for g, p in enumerate(poses):
            ids = np.where(p.pic[..., 3] == 255, lut[_key24(p.pic[..., :3])], 0).astype(np.int64)
            a, bb, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
            ok = (a > 0) & (bb > 0) & (c > 0) & (d > 0) & ~((a == bb) & (a == c) & (a == d))
            yy, xx = np.nonzero(ok)
            ks.append(((a[ok] * r + bb[ok]) * r + c[ok]) * r + d[ok])
            # cell = g * CW + (feet y + pad) * WW + (feet x + pad), feet = block's top-left - (xx - ox, yy - oy):
            # the entry's part of it, so that a vote is ONE add: cell = off[e] + (y * WW + x) of the frame block
            offs.append(g * self.CW + (self.pad - (yy - p.oy)) * self.WW + (self.pad - (xx - p.ox)))
            gs.append(np.full(len(yy), g))
            self.n_feat.append(int(ok.sum()))
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
                f"{self.entries} entries, {len(self.uk)} keys; places per key p50 {np.median(c):.0f} max {c.max()}")

    # ---- per frame
    def ids(self, frame, exp=None, known=None, tol: float = 4.0):
        """Palette id per pixel of the play area: (PLAY_H, SW) int16, 0 = no sprite colour. `frame`: uint8 BGR
        tensor (>= PLAY_H rows). With `exp` (float (PLAY_H, SW, 3), the expected scene) and `known` (bool): only
        where the scene does not explain the pixel (|I - exp| > tol in some channel, or unknown)."""
        torch = self.torch
        f = frame[:PLAY_H].int()
        ids = self.lut[f[..., 0] | (f[..., 1] << 8) | (f[..., 2] << 16)]
        if exp is not None:
            d = (frame[:PLAY_H].float() - exp).abs().amax(dim=2) > tol
            if known is not None:
                d |= ~known
            ids = torch.where(d, ids, torch.zeros_like(ids))
        return ids

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
