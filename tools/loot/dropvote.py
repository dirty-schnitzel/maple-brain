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

Pictures (PLAN-loot.md S4): assets/mcw/items (gamedata.load_items: every distinct picture, its class id) by default,
the `weak` ones (< 16 usable features: see-through) not searched; `pictures="draft"` = the plan session's export
(lootlib.Items, links not followed). With `fhs` (lootlib.Footholds) + the camera, find() also gives each drop the
facts and the KIND (`facts`, `kind_of`): REST / weak (the user, 2026-11-17: no AIR kind, a ring bar on REST, cash
items not searched).
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


def npz_poses(items) -> tuple:
    """assets/mcw/items -> ([Pose] anchored at the bottom-centre, [(class id, meso frame, file origin)], aliases {}).
    The pictures are distinct already; weak ones are left out (they cannot vote), cash-only ones too (cash-shop items
    never drop - the user, 2026-11-17)."""
    poses, meta = [], []
    for g, pic in enumerate(items.pics):
        if items.weak[g] or items.cash[g]:
            continue
        it, fr = int(items.item[g]), int(items.f[g])
        poses.append(Pose(it, "raw" if it < 9000000 else f"f{fr}", "left", pic.shape[1] // 2, pic.shape[0], pic))
        meta.append((it, fr, tuple(int(v) for v in items.org[g])))
    return poses, meta, {}


def kind_of(d: dict, u_max: float = 0.2, mob_max: float = 0.5, ring_min: float = 0.1) -> str:
    """The kinds (section 5 as amended by the user 2026-11-17: no AIR kind, a ring bar on REST): REST = u <= 0.2,
    mob < 0.5, dy in -7..+5 and ring >= 0.1 (what is around the picture shows scenery / a drop / a fit mob / a
    character; fewer than 60 known ring pixels = pass) - a window icon at a foothold's height has the panel around
    it; weak = the rest (only ever confirms a drop already known)."""
    at_rest = d["dy"] is not None and -7 <= d["dy"] <= 5
    if not at_rest:
        return "weak"
    n = max(1, d["n_op"])
    u = 1 - (d["seen"] + d["absent"] + d["under"] + d["front"]) / n
    re, rn = d["ring"]
    if u > u_max or d["mob"] >= mob_max * max(1, d["seen"]) or (rn >= 60 and re / rn < ring_min):
        return "weak"
    return "rest"


def facts(d: "Drop", C, fhs) -> dict:
    """Section 8's per-sighting facts (+ `kind`) of one Drop at camera C (`fhs`: lootlib.Footholds)."""
    x, y, w, h = d.box
    e = d.extra or {}
    u = fhs.under(x + w / 2 + C[0], y + h + C[1]) if fhs is not None else None
    r = {"item": d.item, "f": d.frame, "box": list(d.box), "feet": [x + w // 2, y + h], "n_op": d.n_op,
         "seen": d.n_seen, "absent": d.n_abs, "under": e.get("n_cd", 0), "front": e.get("n_front", 0),
         "mob": e.get("n_mob", 0), "ring": [e.get("ring_e2", 0), e.get("ring_n2", 0)],
         "dy": None if u is None else int(round(y + h + C[1] - u[0])), "fh": None if u is None else u[2],
         "layer": None if u is None else u[1], "votes": d.votes, "n_fseen": d.n_fseen}
    r["kind"] = kind_of(r)
    return r


def feature_mask(pic) -> np.ndarray:
    """(h - 1, w - 1) bool: the picture's 2x2 blocks that are features (all opaque, not one flat colour)."""
    k = np.where(pic[..., 3] == 255, pic[..., 0].astype(np.int64) | (pic[..., 1].astype(np.int64) << 8)
                 | (pic[..., 2].astype(np.int64) << 16), -1)
    a, b, c, d = k[:-1, :-1], k[:-1, 1:], k[1:, :-1], k[1:, 1:]
    return (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0) & ~((a == b) & (a == c) & (a == d))


class DropFinder:
    def __init__(self, items=None, kinds=None, ids=None, device=None, cand_votes: int = 12,
                 tol: int = 4, min_seen: int = 40, seen_min: float = 0.25, absent_max: float = 0.15,
                 max_entries: int = 64, pictures: str = "npz"):
        if pictures == "npz" and kinds is None and ids is None and not isinstance(items, Items):
            from maplebrain.gamedata import load_items
            self.items = items or load_items()
            self.poses, self.meta, self.alias = npz_poses(self.items)
        else:
            self.items = items if isinstance(items, Items) else Items()
            self.poses, self.meta, self.alias = item_poses(self.items, kinds, ids)
        self.fmask = [feature_mask(p.pic) for p in self.poses]
        t0 = time.perf_counter()
        self.voter = Voter(self.poses, max_entries, device, max_cells=256, tints={})
        self.build_s = time.perf_counter() - t0
        self.torch, self.dev = self.voter.torch, self.voter.dev
        self.cand_votes, self.tol = cand_votes, tol
        self.min_seen, self.seen_min, self.absent_max = min_seen, seen_min, absent_max
        self.ms = {}

    def find(self, frame, exp=None, known=None, mask=None, keep_cands: bool = False, mob_taken=None, chars=None,
             front=None, layer_of=None):
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
            rows, keep = [], []
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
                # front scenery of the drop's layer (`front`: layer -> bool plane of this camera, the tiles / objects
                # of the layers above; `layer_of(screen x, y of the box's bottom-centre)`): a picture pixel under it
                # shows the scene because the scene is IN FRONT - explained cover, not ABSENT (a ladder's top post)
                lay = layer_of(x0 + w / 2, y0 + h) if layer_of is not None else None
                fr = front[lay][b0:b1, a0:a1] if front is not None and lay in front else np.zeros_like(seen)
                under_front = op & ~seen & fr
                absent &= ~fr
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
                             int(fm.sum()), int(fs.sum()), op, pic[..., 3] > 0, (ra0, rb0, ra1, rb1), ring, kn, ex_,
                             under_front, lay))
            for (ns, i, (a0, b0, a1, b1), seen, n_op, n_abs, box, nf, nfs, op, dr, (ra0, rb0, ra1, rb1), ring, kn,
                 ex_, under_front, lay) in sorted(rows, key=lambda r: -r[0]):
                it, fr, org = self.meta[int(g[i])]
                n_cd = int((op & ~seen & drawn[b0:b1, a0:a1]).sum())         # unseen, under an accepted drop
                dk = drawn[rb0:rb1, ra0:ra1]
                ring_n, ring_e = int((ring & (kn | dk)).sum()), int((ring & (ex_ | dk)).sum())
                extra = {"n_cd": n_cd, "ring_n": ring_n, "ring_e": ring_e, "ring": int(ring.sum()),
                         "n_front": int((under_front & ~drawn[b0:b1, a0:a1]).sum()), "layer": lay}
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
                keep.append(((a0, b0, a1, b1), seen, op, dr, (ra0, rb0, ra1, rb1), ring, kn, ex_, under_front, xm))
            # the second look (the user, 2026-11-18): under / front / ring again with EVERY other accepted drop - the
            # greedy pass knew only the earlier ones (a Charm under an edge-on coin with fewer SEEN px read weak)
            for j, (d, ((a0, b0, a1, b1), seen, op, dr, (ra0, rb0, ra1, rb1), ring, kn, ex_, under_front, xm)) in \
                    enumerate(zip(drops, keep)):
                def meets(k):
                    (p0, q0, p1, q1) = k[0]
                    return p0 < ra1 and p1 > ra0 and q0 < rb1 and q1 > rb0
                if not any(meets(k) for k in keep[j + 1:]):
                    continue
                dk = np.zeros((rb1 - rb0, ra1 - ra0), bool)    # every other accepted drop's drawn px in the window
                for m, k in enumerate(keep):
                    if m != j and meets(k):
                        (p0, q0, p1, q1), kdr = k[0], k[3]
                        u0, v0, u1, v1 = max(p0, ra0), max(q0, rb0), min(p1, ra1), min(q1, rb1)
                        dk[v0 - rb0:v1 - rb0, u0 - ra0:u1 - ra0] |= kdr[v0 - q0:v1 - q0, u0 - p0:u1 - p0]
                dd = dk[b0 - rb0:b1 - rb0, a0 - ra0:a1 - ra0]
                e = d.extra
                e["n_cd"] = int((op & ~seen & dd).sum())
                e["n_front"] = int((under_front & ~dd).sum())
                e["ring_n"], e["ring_e"] = int((ring & (kn | dk)).sum()), int((ring & (ex_ | dk)).sum())
                e["ring_n2"], e["ring_e2"] = int((ring & (kn | dk | xm)).sum()), int((ring & (ex_ | dk | xm)).sum())
        t2 = time.perf_counter()
        self.ms = {"vote": (t1 - t0) * 1000, "check": (t2 - t1) * 1000, "cands": len(g), "feat": vc["feat"],
                   "votes": vc["votes"]}
        return (drops, cands) if keep_cands else drops
