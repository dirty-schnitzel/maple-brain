"""Log unknown tints (PLAN-fit-speed S5: "log, don't guess"): a MOB-SHAPED residue blob that no fit mob explains ->
a saved crop + a row for tools/perc/redesign/exp_tint.py. Offline (run.py --tint-log); 3.3 decides the live side.

Residue = valid pixels the scene does not explain (|I - expected| > tol), minus our body box and the accepted fit
mobs' own sprite pixels (dilated 2 px). Blobs = connected components (8-way) of it after a 5x5 dilation. Mob-shaped
= a pose of the map whose silhouette (alpha > 0) matches the blob's raw pixels at IoU >= `iou` (aligned by the
silhouettes' bottom centres, +-3 px). At the best pose the frame colours are compared with the sprite's: the share
of opaque pixels whose frame colour is the most common one for their sprite colour ("functional": a tint is a colour
map, 100 % on the frozen mobs) and per channel frame = a sprite + b (least squares on those pixels). The row says
what was seen; nothing is added to vote.TINTS from it."""
import json
from pathlib import Path

import cv2
import numpy as np

PLAY_H, SW = 700, 1366


class TintLog:
    def __init__(self, fitter, out: Path, iou: float = 0.6, tol: float = 4.0):
        self.f, self.out, self.iou, self.tol = fitter, Path(out), iou, tol
        self.out.mkdir(parents=True, exist_ok=True)
        self.rows = []
        self.g_of = {(p.type, p.pose, p.facing): g for g, p in enumerate(fitter.poses)}
        self.sil = []                                       # per pose: silhouette, its bbox in the picture
        for p in fitter.poses:
            m = p.pic[..., 3] > 0
            ys, xs = np.nonzero(m)
            self.sil.append((m, xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        self.min_area = 0.3 * min(int(s[0].sum()) for s in self.sil)

    def frame(self, n, frame, exp, valid, mobs, me):
        """frame uint8 (>= PLAY_H, SW, 3), exp float (PLAY_H, SW, 3), valid bool (PLAY_H, SW) numpy; mobs [FitMob];
        me (x0, y0, x1, y1) or None."""
        fr = frame[:PLAY_H].astype(np.float32)
        raw = (np.abs(fr - exp).max(axis=2) > self.tol) & valid
        if me is not None:
            x0, y0, x1, y1 = (max(int(v), 0) for v in me)
            raw[y0:y1, x0:x1] = False
        cover = np.zeros_like(raw)
        for m in mobs:
            p = self.f.poses[self.g_of[(m.type, m.pose, m.facing)]]
            h, w = p.pic.shape[:2]
            x0, y0 = m.feet[0] - p.ox, m.feet[1] - p.oy
            a, b = max(x0, 0), max(y0, 0)
            c, d = min(x0 + w, SW), min(y0 + h, PLAY_H)
            if c > a and d > b:
                cover[b:d, a:c] |= p.pic[b - y0:d - y0, a - x0:c - x0, 3] > 0
        cover = cv2.dilate(cover.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        raw &= ~cover
        k, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(raw.astype(np.uint8), np.ones((5, 5), np.uint8)), 8)
        for j in range(1, k):
            bx, by, bw, bh, _ = st[j]
            blob = (lab == j) & raw
            if blob.sum() < self.min_area:
                continue
            best = self._shape(blob, bx, by, bw, bh)
            if best is None or best[0] < self.iou:
                continue
            self._log(n, frame, blob, best)

    def _shape(self, blob, bx, by, bw, bh):
        cx, yb = bx + bw / 2, by + bh                       # the blob's bottom centre
        nb = int(blob.sum())
        best = None
        for g, (m, px0, py0, px1, py1) in enumerate(self.sil):
            nm = int(m.sum())
            pw, ph = px1 - px0, py1 - py0
            if not (0.6 * pw <= bw <= 1.4 * pw + 6 and 0.6 * ph <= bh <= 1.4 * ph + 6):
                continue
            h, w = m.shape
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    x0 = int(round(cx - (px0 + px1) / 2)) + dx  # the picture's top-left on screen
                    y0 = yb - py1 + dy
                    a, b = max(x0, 0), max(y0, 0)
                    c, d = min(x0 + w, SW), min(y0 + h, PLAY_H)
                    if c <= a or d <= b:
                        continue
                    mm = m[b - y0:d - y0, a - x0:c - x0]
                    bb = blob[b:d, a:c]
                    inter = int((mm & bb).sum())
                    union = nm + nb - inter
                    iou = inter / max(union, 1)
                    if best is None or iou > best[0]:
                        best = (iou, g, x0, y0)
        return best

    def _log(self, n, frame, blob, best):
        iou, g, x0, y0 = best
        x0, y0 = int(x0), int(y0)
        p = self.f.poses[g]
        h, w = p.pic.shape[:2]
        a, b = max(x0, 0), max(y0, 0)
        c, d = min(x0 + w, SW), min(y0 + h, PLAY_H)
        op = (p.pic[b - y0:d - y0, a - x0:c - x0, 3] == 255) & blob[b:d, a:c]
        s = p.pic[b - y0:d - y0, a - x0:c - x0, :3][op].astype(np.int64)
        f = frame[b:d, a:c][op].astype(np.int64)
        row = {"n": n, "type": p.type, "pose": p.pose, "facing": p.facing, "feet": [x0 + p.ox, y0 + p.oy],
               "iou": round(iou, 3), "opaque": int(op.sum())}
        if len(s) >= 30:
            sk = s[:, 0] | (s[:, 1] << 8) | (s[:, 2] << 16)
            fk = f[:, 0] | (f[:, 1] << 8) | (f[:, 2] << 16)
            u, inv = np.unique(sk, return_inverse=True)
            fun = 0
            for i in range(len(u)):
                _, cnt = np.unique(fk[inv == i], return_counts=True)
                fun += int(cnt.max())
            row["functional"] = round(fun / len(s), 3)
            row["equal"] = round(float((sk == fk).mean()), 3)
            row["fit"] = {}
            for ch, nm in enumerate("bgr"):
                A = np.stack([s[:, ch], np.ones(len(s))], 1).astype(float)
                coef = np.linalg.lstsq(A, f[:, ch].astype(float), rcond=None)[0]
                row["fit"][nm] = [round(float(coef[0]), 4), round(float(coef[1]), 2)]
        name = f"{n:06d}_{p.type}_{x0 + p.ox}_{y0 + p.oy}.png"
        pad = 12
        crop = frame[max(b - pad, 0):min(d + pad, PLAY_H), max(a - pad, 0):min(c + pad, SW)]
        spr = np.zeros((h, w, 3), np.uint8)
        spr[p.pic[..., 3] > 0] = p.pic[..., :3][p.pic[..., 3] > 0]
        hh = max(crop.shape[0], h)
        sheet = np.zeros((hh, crop.shape[1] + 4 + w, 3), np.uint8)
        sheet[:crop.shape[0], :crop.shape[1]] = crop
        sheet[:h, crop.shape[1] + 4:] = spr
        cv2.imwrite(str(self.out / name), cv2.resize(sheet, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
        row["crop"] = name
        self.rows.append(row)

    def close(self) -> str:
        (self.out / "tint_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.rows), encoding="utf-8")
        tinted = [r for r in self.rows if r.get("functional", 0) >= 0.9 and r.get("equal", 1) < 0.5]
        return (f"tint log: {len(self.rows)} mob-shaped unexplained blobs (IoU >= {self.iou}) -> {self.out}; "
                f"colour-map >= 90 % and not plain (equal < 50 %): {len(tinted)}")
