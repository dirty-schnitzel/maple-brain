"""How far the camera moved since the last frame, measured on the PLATFORMS only.

The whole-frame phase correlation (Perceiver: obs.scene_dx) locks onto the parallax background, which scrolls
slower than the camera: on Line 1 <Area 1> it saw only ~2/3 of the real camera motion (median 0.67, p10 0.44),
so `map = screen + C` lagged behind us whenever we walked (our fine x vs the rope we hung on: p10..p90 -23..+27 px).
Platform tiles are drawn 1:1 with the map: small strips just under each visible platform surface are found again in
the next frame (template match, +-`reach` px) and the median displacement is the camera's shift (same test: -3..+6
px, better than the minimap's 16 px steps). Strips by our own body are skipped; mobs/players walking through a
strip are outvoted by the median.
"""
import cv2
import numpy as np

UI_BOTTOM = 610          # chat / HUD below this (screen y)
MINIMAP = (290, 160)     # the minimap window's corner (x < 290 and y < 160 is never scenery)


class PlatformShift:
    def __init__(self, navmap, reach: int = 32, pw: int = 80, ph: int = 36, step: float = 120,
                 min_std: float = 12, min_score: float = 0.8, max_strips: int = 12, w: int = 1366,
                 alias: float = 0.03):
        self.nav, self.reach, self.pw, self.ph, self.min_std = navmap, reach, pw, ph, min_std
        self.min_score, self.max_strips, self.w, self.alias = min_score, max_strips, w, alias
        self.last = None                                  # ((dx, dy), dt) of the last measured shift
        self.t_prev = None
        self.pts = []                                     # (map x, surface y) every `step` px along every platform
        for p in navmap.platforms.values():
            for x in np.arange(p.left + pw / 2, p.right - pw / 2 + 1e-6, step):
                self.pts.append((float(x), p.y_at(float(x))))
        self.prev = None                                  # last frame, grey

    def strips(self, C, me=None) -> list:
        """Top-left corners (screen) of the strips to use with camera C; `me` = our screen (x, y) to stay off."""
        R, out = self.reach, []
        for x, y in self.pts:
            sx, sy = x - C[0], y - C[1]
            x0, y0 = int(sx - self.pw / 2), int(sy - 8)
            if x0 < R or x0 + self.pw > self.w - R or y0 < R or y0 + self.ph > UI_BOTTOM - R:
                continue
            if x0 < MINIMAP[0] and y0 < MINIMAP[1]:
                continue
            if me is not None and abs(sx - me[0]) < 70 and abs(sy - me[1]) < 90:
                continue
            out.append((x0, y0))
        return out

    def update(self, frame, C, me=None, t=None):
        """`frame` BGR (or grey); `C` the camera before this frame (map = screen + C) or None. Returns the scenery's
        (dx, dy) on screen since the previous frame, or None (first frame, no camera, < 2 strips agree). `t` = the
        frame's time (for the prediction that picks between look-alike tile peaks)."""
        g = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        prev, self.prev = self.prev, g
        dt = t - self.t_prev if t is not None and self.t_prev is not None else None
        self.t_prev = t
        if prev is None or C is None or prev.shape != g.shape:
            return None
        R, ds = self.reach, []
        pred = self._predict(dt)
        px, py = int(round(pred[0])), int(round(pred[1]))   # search around where the strip should be now
        H, W = g.shape[:2]
        cand = []
        for x0, y0 in self.strips(C, me):
            if not (0 <= x0 + px - R and x0 + px + self.pw + R <= W and 0 <= y0 + py - R
                    and y0 + py + self.ph + R <= H):
                continue
            tpl = prev[y0:y0 + self.ph, x0:x0 + self.pw]
            s = float(tpl.std())
            if s >= self.min_std:
                cand.append((s, x0, y0, tpl))
        cand.sort(key=lambda c: -c[0])                    # the most textured strips first
        for _, x0, y0, tpl in cand[:self.max_strips]:
            area = g[y0 + py - R:y0 + py + self.ph + R, x0 + px - R:x0 + px + self.pw + R]
            r = cv2.matchTemplate(area, tpl, cv2.TM_CCOEFF_NORMED)
            d = self._pick(r, (pred[0] - px, pred[1] - py))
            if d is not None:
                ds.append((d[0] + px, d[1] + py))
        if len(ds) < 2:
            self.last = None
            return None
        d = np.median(np.array(ds, dtype=np.float32), axis=0)
        d = (float(d[0]), float(d[1]))
        self.last = (d, dt)
        return d

    def _predict(self, dt):
        """The shift expected now: the camera's last shift, scaled to this frame's time step (0, 0 if unknown)."""
        if self.last is None:
            return 0.0, 0.0
        (dx, dy), dt0 = self.last
        if not dt or not dt0:
            return dx, dy
        k = min(3.0, dt / dt0)
        return dx * k, dy * k

    def _pick(self, r, pred):
        """The match to believe: tiles repeat (stripes, girders), so several peaks can score alike one tile period
        apart - and every strip of a platform aliases the same way (the median can't fix that). Of the local peaks
        within `alias` of the best, the one nearest the predicted shift."""
        R = self.reach
        _, best, _, (lx, ly) = cv2.minMaxLoc(r)
        if best < self.min_score:
            return None
        peaks = (r >= best - self.alias) & (r >= cv2.dilate(r, np.ones((5, 5), np.uint8)))
        ys, xs = np.nonzero(peaks)
        if len(xs) <= 1:
            return lx - R, ly - R
        i = int(np.argmin((xs - R - pred[0]) ** 2 + (ys - R - pred[1]) ** 2))
        return int(xs[i]) - R, int(ys[i]) - R
