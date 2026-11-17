"""Prototype (PLAN-loot.md, plan session; NOT on the live path): drops by the mob fit's exact-colour vote.

The client's item pictures (info/iconRaw of every Etc / Consume / Install item and equip + the meso frames) are the
vote's "poses" (perception/vote.py Voter, unchanged): palette id per frame pixel -> 2x2 id blocks -> votes for (picture,
anchor) cells -> exclusive votes. Then each cell is CHECKED pixel by pixel against the picture:
    SEEN     the frame shows the picture's opaque pixel exactly (|I - s| <= tol)
    ABSENT   not SEEN and the frame shows the expected scene there
    COVERED  the rest (something else drawn over it)
A drop = SEEN >= min_seen px and SEEN share of the picture's on-screen opaque pixels >= seen_min and ABSENT share <=
absent_max; greedy by SEEN count, an accepted drop's pixels are taken (the same picture 1 px off, a meso's frames).

The anchor of a cell here = the picture's bottom-centre (w // 2, h); `pos` = the client's own drawing position
(anchor - (w // 2, h) + file origin): where the client says the drop is.
"""
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, PLAY_H, SW  # noqa: E402
from maplebrain.perception.vote import Pose, Voter  # noqa: E402

EQUIP = ("Accessory", "Cap", "Cape", "Coat", "Glove", "Longcoat", "Pants", "Ring", "Shield", "Shoes", "Weapon")


@dataclass
class Drop:
    item: int
    frame: int              # meso frame (0 for items)
    box: tuple              # x, y, w, h on screen (the picture)
    pos: tuple              # the client's drawing position (box corner + file origin)
    n_op: int               # opaque pixels of the picture on screen
    n_seen: int
    n_abs: int
    votes: int
    n_feat: int = 0         # the picture's features (2x2 blocks) on screen
    n_fseen: int = 0        # ... of them fully SEEN (flat colour matches don't count here)

    extra = None            # {"n_cd": unseen pixels under an accepted drop, "ring_n" / "ring_e": the pixels around
                            #  the picture with known scenery (or a drop) / that show it, "ring": all of them}

    def to_dict(self):
        return {"item": self.item, "f": self.frame, "box": list(self.box), "pos": list(self.pos), "n_op": self.n_op,
                "n_seen": self.n_seen, "n_abs": self.n_abs, "votes": self.votes, "n_feat": self.n_feat,
                "n_fseen": self.n_fseen, **(self.extra or {})}


def item_poses(items: Items, kinds=None, ids=None) -> tuple:
    """-> ([Pose] with the anchor at the picture's bottom-centre, [(item id, meso frame, file origin)], aliases).
    Pictures that are pixel-identical are ONE pose (the first: mesos, then the lowest id); `aliases`: its item id ->
    [the other ids showing the same picture] (a drop of such a picture can't be told apart by sight)."""
    poses, meta, alias, first = [], [], {}, {}

    def add(item, fr, pic, org):
        key = (pic.shape, pic.tobytes())
        if key in first:
            if first[key] != item:
                alias.setdefault(first[key], []).append(item)
            return
        first[key] = item
        poses.append(Pose(item, "raw" if item < 9000000 else f"f{fr}", "left", pic.shape[1] // 2, pic.shape[0], pic))
        meta.append((item, fr, org))

    for n in range(4):
        for k, (pic, org, _) in enumerate(items.meso(n)):
            add(9000000 + n, k, pic, org)
    todo = ids if ids is not None else items.ids(kinds or ("Etc", "Consume", "Install") + EQUIP)
    for i in sorted(todo):
        r = items.raw(i)
        if r is None or r[0] is None or (r[0][..., 3] == 255).sum() < 30:
            continue
        add(int(i), 0, r[0], r[1])
    return poses, meta, alias


def feature_mask(pic) -> np.ndarray:
    """(h - 1, w - 1) bool: the picture's 2x2 blocks that are features (all opaque, not one flat colour)."""
    k = np.where(pic[..., 3] == 255, pic[..., 0].astype(np.int64) | (pic[..., 1].astype(np.int64) << 8)
                 | (pic[..., 2].astype(np.int64) << 16), -1)
    a, b, c, d = k[:-1, :-1], k[:-1, 1:], k[1:, :-1], k[1:, 1:]
    return (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0) & ~((a == b) & (a == c) & (a == d))


class DropFinder:
    def __init__(self, items: Items | None = None, kinds=None, ids=None, device=None, cand_votes: int = 12,
                 tol: int = 4, min_seen: int = 40, seen_min: float = 0.25, absent_max: float = 0.15,
                 max_entries: int = 64):
        self.items = items or Items()
        self.poses, self.meta, self.alias = item_poses(self.items, kinds, ids)
        self.fmask = [feature_mask(p.pic) for p in self.poses]
        t0 = time.perf_counter()
        self.voter = Voter(self.poses, max_entries, device, max_cells=256, tints={})
        self.build_s = time.perf_counter() - t0
        self.torch, self.dev = self.voter.torch, self.voter.dev
        self.cand_votes, self.tol = cand_votes, tol
        self.min_seen, self.seen_min, self.absent_max = min_seen, seen_min, absent_max
        self.ms = {}

    def find(self, frame, exp=None, known=None, mask=None, keep_cands: bool = False, mob_taken=None, chars=None):
        """`frame`: uint8 BGR tensor (>= PLAY_H rows) on the voter's device; `exp`, `known`: Scene.expected(C) (None:
        every pixel may vote, no ABSENT evidence); `mask`: bool (PLAY_H, SW), False = not world (the UI).
        -> [Drop] (+ every checked cell when keep_cands)."""
        torch = self.torch
        t0 = time.perf_counter()
        f = frame[:PLAY_H]
        ids = self.voter.ids(f, exp, known, self.tol)
        if mask is not None:
            ids = torch.where(mask, ids, torch.zeros_like(ids))
        g, fx, fy, nv, ex, vc = self.voter.cells(ids, self.cand_votes)
        if self.dev != "cpu":
            torch.cuda.synchronize()
        t1 = time.perf_counter()
        drops, cands = [], []
        if len(g):
            fnp = f.cpu().numpy()
            enp = exp.cpu().numpy() if exp is not None else None
            knp = known.cpu().numpy() if known is not None else None
            taken = np.zeros((PLAY_H, SW), bool)            # SEEN pixels of the accepted drops
            drawn = np.zeros((PLAY_H, SW), bool)            # every drawn (alpha > 0) pixel of the accepted drops
            M = 2                                           # the ring: this many px around the box
            rows = []
            for i in range(len(g)):
                p = self.poses[int(g[i])]
                h, w = p.pic.shape[:2]
                x0, y0 = int(fx[i]) - p.ox, int(fy[i]) - p.oy
                a0, b0, a1, b1 = max(0, x0), max(0, y0), min(SW, x0 + w), min(PLAY_H, y0 + h)
                if a1 <= a0 or b1 <= b0:
                    continue
                pic = p.pic[b0 - y0:b1 - y0, a0 - x0:a1 - x0]
                op = pic[..., 3] == 255
                I = fnp[b0:b1, a0:a1].astype(np.int16)
                seen = op & (np.abs(I - pic[..., :3].astype(np.int16)).max(axis=2) <= self.tol)
                if enp is not None:
                    absent = op & ~seen & (np.abs(I - enp[b0:b1, a0:a1]).max(axis=2) <= self.tol)
                else:
                    absent = np.zeros_like(seen)
                fm = self.fmask[int(g[i])][b0 - y0:b1 - y0 - 1, a0 - x0:a1 - x0 - 1]
                fs = fm & seen[:-1, :-1] & seen[:-1, 1:] & seen[1:, :-1] & seen[1:, 1:]
                # the ring: the pixels around the picture (its box + M px, minus what it draws): what is behind it
                ra0, rb0, ra1, rb1 = max(0, x0 - M), max(0, y0 - M), min(SW, x0 + w + M), min(PLAY_H, y0 + h + M)
                ring = np.ones((rb1 - rb0, ra1 - ra0), bool)
                ring[b0 - rb0:b1 - rb0, a0 - ra0:a1 - ra0] = pic[..., 3] == 0
                if enp is not None:
                    kn = knp[rb0:rb1, ra0:ra1]
                    ex_ = kn & (np.abs(fnp[rb0:rb1, ra0:ra1].astype(np.int16) - enp[rb0:rb1, ra0:ra1]).max(axis=2) <= self.tol)
                else:
                    kn = ex_ = np.zeros_like(ring)
                rows.append((int(seen.sum()), i, (a0, b0, a1, b1), seen, int(op.sum()), int(absent.sum()), (x0, y0, w, h),
                             int(fm.sum()), int(fs.sum()), op, pic[..., 3] > 0, (ra0, rb0, ra1, rb1), ring, kn, ex_))
            for (ns, i, (a0, b0, a1, b1), seen, n_op, n_abs, box, nf, nfs, op, dr, (ra0, rb0, ra1, rb1), ring, kn,
                 ex_) in sorted(rows, key=lambda r: -r[0]):
                it, fr, org = self.meta[int(g[i])]
                n_cd = int((op & ~seen & drawn[b0:b1, a0:a1]).sum())         # unseen, under an accepted drop
                dk = drawn[rb0:rb1, ra0:ra1]
                ring_n, ring_e = int((ring & (kn | dk)).sum()), int((ring & (ex_ | dk)).sum())
                extra = {"n_cd": n_cd, "ring_n": ring_n, "ring_e": ring_e, "ring": int(ring.sum())}
                if mob_taken is not None:       # SEEN pixels the mob fit's accepted mobs explained (it IS the mob)
                    extra["n_mob"] = int((seen & mob_taken[b0:b1, a0:a1]).sum())
                # the ring again, with what else is known to be drawn there: the fit's mobs, characters' body boxes
                xm = np.zeros_like(ring)
                if mob_taken is not None:
                    xm |= mob_taken[rb0:rb1, ra0:ra1]
                if chars is not None:
                    xm |= chars[rb0:rb1, ra0:ra1]
                extra["ring_n2"] = int((ring & (kn | dk | xm)).sum())
                extra["ring_e2"] = int((ring & (ex_ | dk | xm)).sum())
                if chars is not None:
                    extra["n_char"] = int((seen & chars[b0:b1, a0:a1]).sum())    # SEEN pixels inside a character box
                if keep_cands:
                    cands.append({"item": it, "f": fr, "box": list(box), "n_op": n_op, "n_seen": ns, "n_abs": n_abs,
                                  "votes": int(ex[i]), "n_feat": nf, "n_fseen": nfs, **extra})
                if ns < self.min_seen or ns < self.seen_min * n_op or n_abs > self.absent_max * n_op:
                    continue
                px = seen & ~taken[b0:b1, a0:a1]
                n2 = int(px.sum())
                if n2 < self.min_seen or n2 < self.seen_min * n_op:
                    continue
                taken[b0:b1, a0:a1] |= px
                drawn[b0:b1, a0:a1] |= dr
                d = Drop(it, fr, box, (box[0] + org[0], box[1] + org[1]), n_op, n2, n_abs, int(ex[i]), nf, nfs)
                d.extra = extra
                drops.append(d)
        t2 = time.perf_counter()
        self.ms = {"vote": (t1 - t0) * 1000, "check": (t2 - t1) * 1000, "cands": len(g), "feat": vc["feat"],
                   "votes": vc["votes"]}
        return (drops, cands) if keep_cands else drops
