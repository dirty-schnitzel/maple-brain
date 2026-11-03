"""Finding mobs by their game sprites (assets/mcw, see assets/README.md) - including ones nobody has hit yet.

Two stages, so it fits the ~20 fps loop:
1. colour: each mob's sprite has a few saturated "signature" hues (a snail's shell: teal / blue / red); pixels of
   those hues in the ground band are grouped into blobs (cheap, whole band);
2. shape: around each blob, the mob's sprite frames (both facing directions) are matched with their alpha mask
   (only in that small window, at full resolution).
"""
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..geometry import overlaps

ANIMS = ("stand", "move", "hit1")      # what a live mob looks like (searched for everywhere)
DIE = "die1"                           # its death animation: only checked where our target was


@dataclass
class MobSprites:
    mob_id: int
    name: str
    frames: list            # [(bgr, mask)] both facing directions, stand first
    hues: list              # [(lo, hi)] OpenCV hue ranges (0-179) of the signature colours
    max_w: int
    max_h: int
    sig_px: int = 0         # signature-colour pixels in one sprite frame (median): expected blob size
    die: list = None        # [(bgr, mask)] death animation frames, both facing directions
    scan_idx: tuple = (0, 1)  # distinct frames, slid over the whole band when the mob is camouflaged
    shape_key: bytes = b""  # mobs drawn alike (Stump / Dark Stump: same masks) share one scan


def hue_mask(hsv, hues, sat=120, val=60):
    sv = (hsv[..., 1] > sat) & (hsv[..., 2] > val)
    m = np.zeros(hsv.shape[:2], bool)
    for lo, hi in hues:
        m |= (hsv[..., 0] >= lo) & (hsv[..., 0] <= hi)
    return (m & sv).astype(np.uint8)


def signature_hues(rgba_frames, min_share=0.15, sat=120, val=60) -> list:
    """Hue ranges (5-wide bins, neighbours merged) holding >= min_share of the sprite's saturated pixels."""
    h = np.zeros(36)
    for im in rgba_frames:
        hsv = cv2.cvtColor(np.ascontiguousarray(im[..., :3]), cv2.COLOR_BGR2HSV)
        px = hsv[(im[..., 3] > 200) & (hsv[..., 1] > sat) & (hsv[..., 2] > val)]
        h += np.bincount(px[:, 0] // 5, minlength=36)[:36]
    if h.sum() == 0:
        return []
    keep = [i for i in range(36) if h[i] / h.sum() >= min_share]
    keep = sorted(set(keep) | {j for i in keep for j in (i - 1, i + 1) if 0 <= j < 36 and h[j] / h.sum() >= 0.04})
    ranges, start = [], None
    for i in range(37):
        if i < 36 and i in keep:
            start = i if start is None else start
        elif start is not None:
            ranges.append((start * 5, i * 5 - 1))
            start = None
    return ranges


def load_mob(mob_dir: Path) -> MobSprites:
    info = json.loads((mob_dir / "mob.json").read_text(encoding="utf-8"))
    paths = sorted((p for p in mob_dir.glob("*.png") if p.stem.rsplit("_", 1)[0] in ANIMS),
                   key=lambda p: (ANIMS.index(p.stem.rsplit("_", 1)[0]), p.stem))      # stand first
    rgba = [cv2.imread(str(p), cv2.IMREAD_UNCHANGED) for p in paths]
    rgba = [im for im in rgba if im is not None and im.ndim == 3 and im.shape[2] == 4]
    hues = signature_hues(rgba)
    sig = [int((hue_mask(cv2.cvtColor(np.ascontiguousarray(im[..., :3]), cv2.COLOR_BGR2HSV), hues)
                & (im[..., 3] > 200)).sum()) for im in rgba]
    frames = []
    for im in rgba:
        for t in (im, np.ascontiguousarray(im[:, ::-1])):
            frames.append((np.ascontiguousarray(t[..., :3]), (t[..., 3] > 200).astype(np.uint8)))
    die = []
    for p in sorted(mob_dir.glob(f"{DIE}_*.png"), key=lambda p: int(p.stem.rsplit("_", 1)[1])):
        im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if im is None or im.ndim != 3 or im.shape[2] != 4 or (im[..., 3] > 200).sum() < 60:
            continue                                     # (the last frames fade to almost nothing)
        for t in (im, np.ascontiguousarray(im[:, ::-1])):
            die.append((np.ascontiguousarray(t[..., :3]), (t[..., 3] > 200).astype(np.uint8)))
    scan, seen = [], set()                              # every distinct pose (stand_0 == move_0 for a Stump)
    for j, (t, m) in enumerate(frames):
        h = t.tobytes() + m.tobytes() + bytes(str(t.shape), "ascii")
        if h not in seen:
            seen.add(h)
            scan.append(j)
    key = b"".join(frames[j][1].tobytes() + bytes(str(frames[j][1].shape), "ascii") for j in scan)
    return MobSprites(int(info["id"]), info.get("name", ""), frames, hues,
                      max(im.shape[1] for im in rgba), max(im.shape[0] for im in rgba), int(np.median(sig)), die,
                      tuple(scan), key)


def pose_similarity(small: list) -> np.ndarray:
    """S[i, j]: best masked match of pose i on pose j (drawn on mid-gray, a few px of room to slide)."""
    n = len(small)
    S = np.full((n, n), -1.0)
    for j, (tj, mj) in enumerate(small):
        h, w = tj.shape[:2]
        pad = 6
        img = np.full((h + 2 * pad, w + 2 * pad, 3), 128, np.uint8)
        img[pad:pad + h, pad:pad + w][mj > 0] = tj[mj > 0]
        for i, (ti, mi) in enumerate(small):
            if ti.shape[0] <= img.shape[0] and ti.shape[1] <= img.shape[1]:
                r = cv2.matchTemplate(img, ti, cv2.TM_CCOEFF_NORMED, mask=mi)
                r[~np.isfinite(r)] = -1
                S[i, j] = float(r.max())
    return S


def _cover(S: np.ndarray, cover: float) -> list:
    """Fewest poses (greedy) such that every pose matches one of them >= `cover`; stand poses win ties."""
    left, reps = set(range(len(S))), []
    while left:
        i = max(range(len(S)), key=lambda i: (sum(S[i, j] >= cover for j in left), -i))
        if not any(S[i, j] >= cover for j in left):
            i = min(left)        # a flat picture doesn't even match itself (score -1): take it alone, never loop
        reps.append(i)
        left -= {j for j in left if S[i, j] >= cover} | {i}
    return reps


def _inside(p, box) -> bool:
    return box[0] <= p[0] <= box[0] + box[2] and box[1] <= p[1] <= box[1] + box[3]


class SpriteDetector:
    def __init__(self, mobs: list, min_score=0.7, quick_score=0.45, blob_range=(0.3, 3.0), max_candidates=8,
                 scale=0.5, good_score=0.85, camo_share=0.25, scan_scale=0.375, camo_frames=15,
                 quick_cover=0.5, quick_gray=True):
        self.mobs = [m for m in mobs if m.frames and m.hues]
        self.camo_share, self.scan_scale = camo_share, scan_scale   # see camouflaged() / _scan()
        self.scan_cache, self.camo_ids, self.camo_votes, self.camo_frames = {}, set(), {}, camo_frames
        self.scan_small = {m.mob_id: [self._shrink(*m.frames[k], scale=scan_scale) + (k,) for k in m.scan_idx]
                           for m in self.mobs}
        self.min_score, self.quick_score, self.good_score = min_score, quick_score, good_score
        self.last_frame = {}                    # mob id -> index of the frame that matched last
        self.blob_range, self.max_candidates, self.scale = blob_range, max_candidates, scale
        # everything is matched at `scale` (4x fewer pixels at 0.5; measured: same recall as full size)
        self.small = {m.mob_id: [self._shrink(t, k) for t, k in m.frames] for m in self.mobs}
        self.small_die = {m.mob_id: [self._shrink(t, k) for t, k in (m.die or [])] for m in self.mobs}
        # the quick check, on every candidate before all poses: representative poses - every pose resembles one of
        # them >= quick_cover (_cover; Snails 2, Pig 5, Ribbon Pig 6) - in gray (3x cheaper), then in colour the
        # best one's look-alikes. The old check (quick_cover=None: the stand_0 pair only) missed Pigs, whose stand_0
        # scores 0.36-0.44 on a Pig in another pose (Rain-Forest 2026-11-02: 22 of 52 Pigs found; now 52, 17 -> 33
        # ms/frame; other maps unchanged)
        self.quick_gray = quick_gray
        self.quick, self.groups = {}, {}
        for m in self.mobs:
            if quick_cover is None:
                self.quick[m.mob_id] = [0, 1]
                continue
            S = pose_similarity(self.small[m.mob_id])
            self.quick[m.mob_id] = q = _cover(S, quick_cover)
            # per representative: the poses it stands for, most alike first (tried in colour after a gray hit)
            self.groups[m.mob_id] = {i: sorted((j for j in range(len(S)) if j != i and S[i, j] >= quick_cover),
                                               key=lambda j: -S[i, j]) for i in q}
        self.small_gray = {k: [(cv2.cvtColor(t, cv2.COLOR_BGR2GRAY), m) for t, m in v] for k, v in self.small.items()}

    def _shrink(self, t, m, scale=None):
        scale = self.scale if scale is None else scale
        if scale == 1:
            return t, m
        ts = cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ms = cv2.resize(m * 255, (ts.shape[1], ts.shape[0]), interpolation=cv2.INTER_AREA)
        return ts, (ms > 160).astype(np.uint8)

    @classmethod
    def for_map(cls, map_id: int, root: Path, **kw) -> "SpriteDetector":
        m = json.loads((root / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in m.get("mobs") or []})
        return cls([load_mob(root / "mobs" / str(i)) for i in ids if (root / "mobs" / str(i) / "mob.json").exists()],
                   **kw)

    def dying(self, frame, x, feet, radius=45, mob_id=None) -> float:
        """Best match of a death-animation frame centred within `radius` px of `x` on the ground line at `feet`
        (only `mob_id`'s frames if given). Cheap: one small window. pkg_human5m 242 s: another player killed our
        Shroom just as our first hit landed; we swung at the empty spot for 1 s, then swept its drop with Z."""
        sc, best = self.scale, 0.0
        for mob in self.mobs:
            if mob_id is not None and mob.mob_id != mob_id:
                continue
            frames = self.small_die.get(mob.mob_id) or []
            if not frames:
                continue
            x0 = max(0, int(x - radius - mob.max_w))
            x1 = min(frame.shape[1], int(x + radius + mob.max_w))
            y0, y1 = max(0, int(feet) - mob.max_h - 30), min(frame.shape[0], int(feet) + 10)
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            win = cv2.resize(frame[y0:y1, x0:x1], None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc != 1                 else frame[y0:y1, x0:x1]
            for t, m in frames:
                if win.shape[0] < t.shape[0] or win.shape[1] < t.shape[1]:
                    continue
                r = cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED, mask=m)
                r[~np.isfinite(r)] = -1
                best = max(best, float(r.max()))
        return best

    def __len__(self):
        return len(self.mobs)

    @property
    def max_h(self) -> int:
        """The tallest sprite of this map's mobs (the band over our feet must hold a whole one)."""
        return max((m.max_h for m in self.mobs), default=60)

    def camouflaged(self, hsv, mob: MobSprites) -> bool:
        """The mob's signature colour covers much of the band (perion1/2: Stumps on Perion's brown rock - the blob
        was the whole floor, 0.1 mobs found per frame): find it by shape instead (`_scan`)."""
        if mob.mob_id not in self.camo_ids and hue_mask(hsv, mob.hues).mean() > self.camo_share:
            self.camo_votes[mob.mob_id] = self.camo_votes.get(mob.mob_id, 0) + 1
            if self.camo_votes[mob.mob_id] >= self.camo_frames:      # not one odd frame (a band of blue sky
                self.camo_ids.add(mob.mob_id)                         # once flagged Blue Snail in a test)
        # sticky for the session: on a slope the band is half sky, the share drops below the cut, and the colour
        # path is still blind there (perion4 9-12 s: Stumps down the slope, never seen, stood "waiting for a spawn")
        return mob.mob_id in self.camo_ids

    def candidates(self, hsv, mob: MobSprites) -> list:
        """Centres (x, y) of blobs in the mob's signature colours."""
        mask = cv2.morphologyEx(hue_mask(hsv, mob.hues), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        n, _, stats, cent = cv2.connectedComponentsWithStats(mask, connectivity=8)
        expect = max(mob.sig_px, 1) * self.scale ** 2
        lo, hi = (r * expect for r in self.blob_range)                  # shell-sized blobs (part hidden is fine)
        ok = [i for i in range(1, n) if lo <= stats[i, cv2.CC_STAT_AREA] <= hi]
        ok.sort(key=lambda i: abs(stats[i, cv2.CC_STAT_AREA] - expect))
        return [tuple(cent[i]) for i in ok[:self.max_candidates]]

    def _scan(self, band, mob: MobSprites, y0: int) -> list:
        """[(score, mob_id, box)] of a camouflaged mob: every distinct pose (both ways) slid over the whole band,
        peaks >= min_score one mob-width apart. Each pose matters (perion2: a Stump in its move_1 pose scored 0.95
        and <= 0.51 with every other frame). ~3.5 ms per pose; mobs drawn alike (Stump / Dark Stump) share one
        scan per frame (`scan_cache`)."""
        if mob.shape_key in self.scan_cache:
            return [(s, mob.mob_id, b) for s, _, b in self.scan_cache[mob.shape_key]]
        sc, peaks = self.scan_scale, []
        band = cv2.resize(band, None, fx=sc / self.scale, fy=sc / self.scale, interpolation=cv2.INTER_AREA)
        for t, m, k in self.scan_small[mob.mob_id]:
            if band.shape[0] < t.shape[0] or band.shape[1] < t.shape[1]:
                continue
            r = cv2.matchTemplate(band, t, cv2.TM_CCOEFF_NORMED, mask=m)
            r[~np.isfinite(r)] = -1
            ys, xs = np.nonzero(r >= self.min_score)
            full = mob.frames[k][0].shape
            peaks += [(float(r[y, x]), mob.mob_id, (int(x / sc), int(y0 + y / sc), full[1], full[0]))
                      for y, x in zip(ys, xs)]
        peaks.sort(key=lambda p: -p[0])
        out, gap = [], mob.max_w * 0.6
        for p in peaks:
            if all(abs(p[2][0] - o[2][0]) > gap for o in out):
                out.append(p)
        self.scan_cache[mob.shape_key] = out
        return out

    def find(self, frame, feet, below=0, above=75, exclude=()) -> list:
        """[(box, mob_id, score)] of mobs in the band from `above` px over `feet` to `below` px under it."""
        y0, y1 = max(0, int(feet) - above), min(frame.shape[0], int(feet) + 8 + int(below))
        if y1 - y0 < 8:
            return []
        sc = self.scale
        band = frame[y0:y1] if sc == 1 else cv2.resize(frame[y0:y1], None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        hits = []
        self.scan_cache = {}
        for mob in self.mobs:
            mw, mh = int(mob.max_w * sc) + 1, int(mob.max_h * sc) + 1
            if self.camouflaged(hsv, mob):
                hits += [h for h in self._scan(band, mob, y0)
                         if not any(_inside((h[2][0] + h[2][2] / 2, h[2][1] + h[2][3] / 2), e) for e in exclude)]
                continue
            for cx_, cy_ in self.candidates(hsv, mob):
                if any(_inside((cx_ / sc, y0 + cy_ / sc), e) for e in exclude):
                    continue                        # already known (e.g. under an HP bar)
                wx0, wy0 = max(0, int(cx_) - mw), max(0, int(cy_) - mh)
                win = band[wy0:int(cy_) + mh, wx0:int(cx_) + mw]
                best = None
                frames = self.small[mob.mob_id]
                quick = self.quick[mob.mob_id]
                hint = self.last_frame.get(mob.mob_id)
                if self.quick_gray:                 # quick poses in gray (3x cheaper), then every pose in colour
                    gwin = cv2.cvtColor(win, cv2.COLOR_BGR2GRAY)
                    q, qk = -1.0, quick[0]
                    for k in quick:
                        t, m = self.small_gray[mob.mob_id][k]
                        if gwin.shape[0] >= t.shape[0] and gwin.shape[1] >= t.shape[1]:
                            r = cv2.matchTemplate(gwin, t, cv2.TM_CCOEFF_NORMED, mask=m)
                            r[~np.isfinite(r)] = -1
                            if float(r.max()) > q:
                                q, qk = float(r.max()), k
                    if q < self.quick_score:
                        continue                    # not this mob
                    # colour: the last matched pose, the best gray pose and its look-alikes; the rest only if
                    # those already score like this mob
                    first = list(dict.fromkeys(([hint] if hint is not None else []) + [qk]
                                               + self.groups[mob.mob_id].get(qk, [])))
                    order = first + [k for k in range(len(frames)) if k not in first]
                    nq = len(first)
                else:
                    first = [hint] if hint is not None and hint not in quick else []
                    order = list(quick) + first + [k for k in range(len(frames)) if k not in quick and k not in first]
                    nq = len(quick)
                for n, k in enumerate(order):
                    t, m = frames[k]
                    if n == nq and (best is None or best[0] < self.quick_score):
                        break                       # the quick poses say: not this mob
                    if best is not None and best[0] >= self.good_score:
                        break                       # clearly this mob: no need to try every frame
                    if win.shape[0] < t.shape[0] or win.shape[1] < t.shape[1]:
                        continue
                    r = cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED, mask=m)
                    r[~np.isfinite(r)] = -1
                    _, s, _, loc = cv2.minMaxLoc(r)
                    if best is None or s > best[0]:
                        full = mob.frames[k][0].shape
                        best = (s, (int((wx0 + loc[0]) / sc), int(y0 + (wy0 + loc[1]) / sc), full[1], full[0]), k)
                if best and best[0] >= self.min_score:
                    self.last_frame[mob.mob_id] = best[2]           # mobs walk on: try this pose first next time
                    hits.append((float(best[0]), mob.mob_id, best[1]))
        hits.sort(reverse=True)
        out = []
        for s, mid, b in hits:
            centre = (b[0] + b[2] / 2, b[1] + b[3] / 2)    # a snail pressed against a known mob is still its own
            if not any(overlaps(b, o[0], pad=-8) for o in out) and not any(_inside(centre, e) for e in exclude):
                out.append((b, mid, s))
        return out
