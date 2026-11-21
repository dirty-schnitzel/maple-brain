"""Prototype: the expected picture WITH the moving background layers (PLAN-moving-scenery.md, the planner's).

MScene wraps maplebrain.scene.Scene (nothing in maplebrain/ is changed):
  * the two flat-colour pictures the export decodes wrong (pixel format 1537, export.ps1's `-shl` on a byte) get
    their real colour at load (FIX);
  * every moving layer (type 4-7) is a Mover: its picture, its place on the map X (screen x of the picture's left
    edge = X - Cx, mod its period), found on each frame by `locate` - its OPAQUE pixels show their own colour
    whatever is drawn under it - top-most layer first, so that a layer is only looked for where nothing later
    covers it; a layer's row = the static formula's with FLOOR instead of truncation (measured);
  * `expected(C)` = Scene.expected with the movers drawn at their places (known there) instead of "unknown".
Speeds measured on Perion Street Corner: X advances 5 * rx px a second (type 4)."""
import json
import math
from pathlib import Path

import cv2
import numpy as np
import torch

import msl
from maplebrain.scene import H_TILED, MOVING, ROOT as SCENE_ROOT, V_TILED, Scene, back_pos

FIX = {"back_midForest/back_0.png": (255, 158, 66), "back_dryRock/back_0.png": (239, 134, 82)}   # BGR (raw 0x44FF, 0x543D)
SW, PLAY_H = 1366, 700


def load_scene(map_id, fix=True, root=SCENE_ROOT) -> Scene:
    d = Path(root) / str(map_id)
    meta = json.loads((d / "scene.json").read_text(encoding="utf-8"))
    canvas = cv2.imread(str(d / "scene.png"), cv2.IMREAD_UNCHANGED)
    anim = cv2.imread(str(d / "anim.png"), cv2.IMREAD_GRAYSCALE) if (d / "anim.png").exists() else None
    pics = []
    for b in meta["backs"]:
        pic = cv2.imread(str(Path(root) / "backs" / b["file"]), cv2.IMREAD_UNCHANGED)
        if fix and b["file"] in FIX:
            pic = pic.copy()
            pic[..., :3] = FIX[b["file"]]
        pics.append(pic)
    layers = {L: cv2.imread(str(d / "layers" / f"front_{L}.png"), cv2.IMREAD_UNCHANGED)[..., 3]
              for L in meta.get("layers") or [] if (d / "layers" / f"front_{L}.png").exists()}
    return Scene(meta, canvas, pics, anim, None, layers)


def floor_y(b, C, hoff=468) -> int:
    """A moving layer's top row on screen. Measured on 4 maps (Perion Street Corner, Henesys Hunting Ground III,
    Construction Site North of Kerning City, 3-Way Road-Split; ry -16..+4, both signs of u, no exception in
    ~9,000 layer-frames): the parallax term is  sign(u) * floor(ry * |u| / 100),  u = Cy + HOFF  - not the static
    layers' truncation toward zero (ry < 0: 1 px further from zero unless the product is whole; ry > 0: the same)."""
    u = int(C[1]) + hoff
    return b["y"] + hoff + (1 if u >= 0 else -1) * math.floor(b["ry"] * abs(u) / 100) - b["origin"][1]


class Mover:
    def __init__(self, i, b, pic, dev):
        self.i, self.b = i, b
        if b.get("flip"):
            pic = pic[:, ::-1]
        ph, pw = pic.shape[:2]
        self.cx = b["cx"] or pw
        self.cy = (b["cy"] or ph) if b["type"] in V_TILED else None
        buf = np.zeros((ph, self.cx, 4), np.uint8)
        buf[:, :min(self.cx, pw)] = pic[:, :min(self.cx, pw)]
        self.pic = torch.from_numpy(np.ascontiguousarray(buf)).to(dev)            # (ph, cx, 4) straight alpha
        self.v = 5.0 * b["rx"]                                                    # px a second (type 4, measured)
        self.X = None            # the picture's left edge on the MAP (mod cx): screen x = X - Cx
        self.t = None            # when X was measured
        self.share = 0.0
        self.found = False
        self.lost_n = 0

    def rows(self, C, dev, sub=1):
        """(screen rows, picture rows) the layer draws on for camera C."""
        sy = floor_y(self.b, C)
        ph = self.pic.shape[0]
        if self.cy is not None:
            rows = torch.arange(0, PLAY_H, sub, device=dev)
            prow = (rows - sy) % self.cy
            ok = prow < ph
            return rows[ok], prow[ok]
        r0, r1 = max(0, sy), min(PLAY_H, sy + ph)
        rows = torch.arange(r0, max(r0, r1), sub, device=dev)
        return rows, rows - sy

    def plane(self, C, dev):
        """(rows, straight-alpha BGRA (R, SW, 4) uint8) of the layer on screen at its place X."""
        rows, prow = self.rows(C, dev)
        xs = (torch.arange(SW, device=dev) - (int(round(self.X)) - int(C[0]))) % self.cx
        return rows, self.pic[prow][:, xs]


class MScene:
    def __init__(self, map_id, fix=True, tol=4):
        self.scene = load_scene(map_id, fix)
        self.dev, self.tol = self.scene.dev, tol
        self.movers = {}
        for i, (b, _) in enumerate(self.scene.backs):
            if b["type"] in MOVING:
                pic = cv2.imread(str(Path(SCENE_ROOT) / "backs" / b["file"]), cv2.IMREAD_UNCHANGED)
                self.movers[i] = Mover(i, b, pic, self.dev)
        self.stats = {"full": 0, "near": 0, "lost": 0}
        # layers the client ADDS to what is under them (the picture's `blend` 1: Ellinia's light rays; measured:
        # frame = min(255, under + colour x alpha), 86-95 % of their free pixels within 1 level)
        props = json.loads((msl.OUT / "back_props.json").read_text())      # catalog.py writes it
        self.additive = {i for i, (bb, _) in enumerate(self.scene.backs)
                         if (props.get(f"{bb['set']}/{bb['kind']}/{bb['no']}") or {}).get("blend")}

    # ---- where the moving layers are
    def _score(self, m, frame_t, free, C, cands, sub):
        """Share of the layer's opaque visible pixels showing their own colour, per candidate X (tensor of ints):
        (shares, pixels compared)."""
        rows, prow = m.rows(C, self.dev, sub)
        if len(rows) < 4:
            return None, None
        xs = torch.arange(0, SW, sub, device=self.dev)
        S = frame_t[rows][:, xs].int()
        fr = free[rows][:, xs]
        P = m.pic[prow]
        sh, ns = [], []
        for k in range(0, len(cands), 64):
            ps = cands[k:k + 64]
            idx = (xs[None, :] - (ps[:, None] - int(C[0]))) % m.cx                 # (B, X)
            Q = P[:, idx]                                                          # (R, B, X, 4)
            op = (Q[..., 3] == 255) & fr[:, None, :]
            hit = ((Q[..., :3].int() - S[:, None]).abs().amax(dim=3) <= self.tol) & op
            n = op.sum(dim=(0, 2)).float()
            sh.append(hit.sum(dim=(0, 2)).float() / n.clamp(min=1))
            ns.append(n)
        return torch.cat(sh), torch.cat(ns)

    def locate(self, frame_t, C, t, sub=2, near=4, min_share=0.5, min_px=300):
        """Find every mover on this frame, top-most first. A mover found before is looked for within `near` px of
        where its speed puts it now, else over its whole period."""
        sc = self.scene
        C = (int(C[0]), int(C[1]))
        cover = sc._crop(C, SW, PLAY_H)[..., 3] > 0                               # tiles / objects: over every back
        an = sc._anim(C, SW, PLAY_H)
        if an is not None:
            cover = cover | an
        for i in range(len(sc.backs) - 1, -1, -1):
            b, tp = sc.backs[i]
            m = self.movers.get(i)
            if m is None:
                if not b["front"] and i not in self.additive:
                    cover = cover | (sc._back_plane(b, tp, C, SW, PLAY_H)[..., 3] > 0)
                continue
            free = ~cover
            best = None
            if m.X is not None and m.lost_n < 30:
                pred = m.X + m.v * (t - m.t)
                cands = (torch.arange(-near, near + 1, device=self.dev) + int(round(pred))) % m.cx
                sh, ns = self._score(m, frame_t, free, C, cands, sub)
                if sh is not None:
                    k = int(sh.argmax())
                    if float(sh[k]) >= min_share and float(ns[k]) >= min_px:
                        best = (int(cands[k]), float(sh[k]), float(ns[k]))
                        # keep the unwrapped fraction: the measured integer place
                        self.stats["near"] += 1
            if best is None:
                cands = torch.arange(m.cx, device=self.dev)
                sh, ns = self._score(m, frame_t, free, C, cands, sub)
                if sh is not None:
                    k = int(sh.argmax())
                    if float(sh[k]) >= min_share and float(ns[k]) >= min_px:
                        best = (int(cands[k]), float(sh[k]), float(ns[k]))
                        self.stats["full"] += 1
            if best is None:
                m.found, m.lost_n = False, m.lost_n + 1
                m.share = 0.0
                self.stats["lost"] += 1
                if m.X is not None:                                               # coast on its speed
                    rows, pl = self._coast(m, C, t)
                    cover[rows] |= pl[..., 3] > 0
                else:                                                             # never seen: its rows are unknown
                    rows, _ = m.rows(C, self.dev)
                    cover[rows] = True
                continue
            m.X, m.t, m.share, m.found, m.lost_n = float(best[0]), t, best[1], True, 0
            rows, pl = m.plane(C, self.dev)
            cover[rows] |= pl[..., 3] > 0

    def _coast(self, m, C, t):
        X = m.X
        m.X = (m.X + m.v * (t - m.t)) % m.cx
        m.t = t
        out = m.plane(C, self.dev)
        return out

    # ---- the expected picture
    def expected(self, C, w=SW, h=PLAY_H):
        """(bgr float (h, w, 3), known bool (h, w)) for camera C with the movers at their places. A mover that was
        never found leaves its pixels unknown (as Scene.expected does for every mover)."""
        sc = self.scene
        C = (int(C[0]), int(C[1]))
        out = torch.zeros((h, w, 3), device=self.dev)
        cover = torch.zeros((h, w), device=self.dev)
        unknown = torch.zeros((h, w), dtype=torch.bool, device=self.dev)
        for front in (0, 1):
            if front:
                scn = sc._crop(C, w, h).float()
                a = scn[..., 3:4] / 255.0
                out = out * (1 - a) + scn[..., :3]
                cover = cover * (1 - a[..., 0]) + a[..., 0]
                unknown &= a[..., 0] < 0.98
                an = sc._anim(C, w, h)
                if an is not None:
                    unknown |= an
            for i, (b, tp) in enumerate(sc.backs):
                if bool(b["front"]) != bool(front):
                    continue
                m = self.movers.get(i)
                if m is None:
                    plane = sc._back_plane(b, tp, C, w, h)
                    a = plane[..., 3:4] / 255.0
                    if not b["known"]:
                        unknown = unknown | (a[..., 0] > 0.02)
                        continue
                    if i in self.additive:
                        out = (out + plane[..., :3]).clamp(max=255)
                        continue
                    out = out * (1 - a) + plane[..., :3]
                    cover = cover * (1 - a[..., 0]) + a[..., 0]
                    continue
                if m.X is None:
                    rows, prow = m.rows(C, self.dev)
                    unknown[rows] = True
                    continue
                rows, pl = m.plane(C, self.dev)
                pl = pl.float()
                a = pl[..., 3:4] / 255.0 * (b.get("a", 255) / 255.0)
                out[rows] = out[rows] * (1 - a) + pl[..., :3] * a
                cover[rows] = cover[rows] * (1 - a[..., 0]) + a[..., 0]
                unknown[rows] &= a[..., 0] < 0.98                                  # an opaque later layer hides it
        return out, (cover > 0.98) & ~unknown


def frame_tensor(img, dev):
    return torch.from_numpy(np.ascontiguousarray(img[:PLAY_H])).to(dev)
