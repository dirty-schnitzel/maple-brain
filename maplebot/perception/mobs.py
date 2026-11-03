"""Following one mob between frames, and remembering what confirmed mobs look like."""
from collections import deque

import cv2
import numpy as np

from ..geometry import overlaps


def gray(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


class Tracker:
    """Template-tracks one mob (and its mirror image: mobs turn around) in a window around its last position."""

    def __init__(self, frame, box, pad=4, min_score=0.68):
        x, y, w, h = box
        x, y = max(0, x - pad), max(0, y - pad)
        self.box = (x, y, w + 2 * pad, h + 2 * pad)
        self.tpl = gray(frame)[y:y + self.box[3], x:x + self.box[2]].copy()
        self.min_score, self.frames, self.score = min_score, 0, 1.0

    def centre_x(self) -> float:
        return self.box[0] + self.box[2] / 2

    def _search(self, g, rx, ry, min_score):
        H, W = g.shape
        x, y, w, h = self.box
        x0, y0, x1, y1 = max(0, x - rx), max(0, y - ry), min(W, x + w + rx), min(H, y + h + ry)
        win = g[y0:y1, x0:x1]
        best, loc = -1.0, None
        for t in (self.tpl, cv2.flip(self.tpl, 1)):
            if win.shape[0] >= t.shape[0] and win.shape[1] >= t.shape[1]:
                _, s, _, l = cv2.minMaxLoc(cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED))
                if s > best:
                    best, loc = s, l
        self.score = best
        if best < min_score:
            return False
        self.box = (x0 + loc[0], y0 + loc[1], w, h)
        return True

    def update(self, frame, refresh=False) -> str | None:
        """Re-find the mob; returns 'track' / 'wide' (re-found after a jump, e.g. knockback) or None."""
        g = gray(frame)
        self.frames += 1
        if self._search(g, 50, 25, self.min_score):
            if refresh and self.score > 0.8 and self.frames % 6 == 0:     # follow the walk animation
                x, y, w, h = self.box
                self.tpl = g[y:y + h, x:x + w].copy()
            return "track"
        if self._search(g, 160, 40, 0.72):
            return "wide"
        return None

    def snap_to(self, box):
        """Re-anchor on an authoritative position (the mob's HP bar)."""
        self.box = (box[0], box[1], self.box[2], self.box[3]) if box[2] == self.box[2] else box


class MobLibrary:
    """Appearances of *confirmed* mobs; finds ones standing still (invisible to motion) along the ground."""

    def __init__(self, size=6, min_score=0.72, min_w=30):
        self.tpls = deque(maxlen=size)
        self.min_score, self.min_w = min_score, min_w

    def __len__(self):
        return len(self.tpls)

    def add(self, tpl):
        if tpl.size and tpl.shape[0] >= 16 and tpl.shape[1] >= self.min_w:
            self.tpls.append(tpl.copy())

    def forget_like(self, tpl):
        keep = [t for t in self.tpls if not (t.shape == tpl.shape and
                                             cv2.matchTemplate(t, tpl, cv2.TM_CCOEFF_NORMED).max() > 0.7)]
        self.tpls.clear()
        self.tpls.extend(keep)

    def forget_at(self, frame, box, pad=10):
        """Drop every entry that matches inside `box` of `frame` (a target proven not to be a mob), whatever the
        sizes: a target found via the library is tracked with a padded box, so its template never equals ours."""
        g = gray(frame)
        x, y, w, h = (int(v) for v in box)
        x0, y0 = max(0, x - pad), max(0, y - pad)
        region = g[y0:y + h + pad, x0:x + w + pad]
        keep = []
        for t in self.tpls:
            hit = False
            if region.shape[0] >= t.shape[0] and region.shape[1] >= t.shape[1]:
                for tt in (t, cv2.flip(t, 1)):
                    hit = hit or cv2.matchTemplate(region, tt, cv2.TM_CCOEFF_NORMED).max() >= self.min_score
            if not hit:
                keep.append(t)
        self.tpls.clear()
        self.tpls.extend(keep)

    def find(self, frame, feet, exclude, below=0) -> list:
        """Boxes on the ground band around `feet` matching a known mob, minus `exclude` boxes."""
        if not self.tpls:
            return []
        g = gray(frame)
        y0, y1 = max(0, int(feet) - 75), min(g.shape[0], int(feet) + 8 + int(below))
        band = g[y0:y1]
        hits = []
        for t in self.tpls:
            if band.shape[0] < t.shape[0]:
                continue
            for tt in (t, cv2.flip(t, 1)):
                res = cv2.matchTemplate(band, tt, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(res >= self.min_score)
                hits.extend((float(res[y, x]), (int(x), int(y + y0), tt.shape[1], tt.shape[0])) for x, y in zip(xs, ys))
        hits.sort(reverse=True)
        out = []
        for _, b in hits:
            if not any(overlaps(b, o, pad=-8) for o in out) and not any(overlaps(b, e, pad=0) for e in exclude):
                out.append(b)
        return out
