"""Loot on the ground, by sight - on any map, with no item pictures.

Items lying on the ground float and bob up and down a few px in place (a red potion: y 549-554 over ~2 s, x
fixed; pkg_others2m); coins spin in place. Nothing else on the ground line does that: the scenery doesn't move,
players and mobs walk (sideways) and change shape. So, between a frame and one ~0.4 s older (camera shift taken
out), a small patch that changed and whose old picture re-appears at the same x, only shifted up or down, is a drop.
Characters (a name tag under them) are excluded. In Classic World you can't see other players' drops (no party):
every drop on screen is ours.

A drop doesn't bob on every frame pair (same phase -> no change), so drops are remembered: each one keeps its
picture and is re-found by a small template match every frame; one not re-found for `lost_s` while in view is gone
(picked up, or it expired). Positions are kept in 'world' x (screen x minus the camera's total shift).
"""
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from .hud import ui_mask
from .tags import find_tags, text_mask


@dataclass
class Drop:
    wx: float               # world x of the box's left edge (screen x = wx + camera)
    y: int
    w: int
    h: int
    tpls: list              # its pictures (BGR): a coin spins, so a few phases of it
    first: float
    seen: float             # last time it was detected or re-found
    hits: int = 1
    anchor: float | None = None   # world x where it was first seen: items never move sideways


def _shift(a, b):
    """Horizontal camera shift from grey image a to b (px, full resolution) and the correlation response."""
    (sx, _), resp = cv2.phaseCorrelate(a, b)
    return float(sx), float(resp)


class DropSpotter:
    def __init__(self, lag_s=0.4, diff=28, min_wh=(10, 8), max_wh=(44, 46), min_std=18.0, match=0.8,
                 bob=(1, 7), keep_score=0.72, lost_s=0.8, memory_s=20.0, above=48, below=8, history_s=1.0,
                 max_text=0.12, ground=(-12, 4), own_reach=48, char_half=44):
        self.lag_s, self.diff, self.min_wh, self.max_wh = lag_s, diff, min_wh, max_wh
        self.min_std, self.match, self.bob = min_std, match, bob
        self.keep_score, self.lost_s, self.memory_s = keep_score, lost_s, memory_s
        self.above, self.below, self.history_s = above, below, history_s
        self.max_text = max_text        # share of name-tag text pixels: a tag of someone climbing a rope moves
                                        # only vertically too (pkg_others2m 34.4 s)
        self.ground = ground            # our floor: a drop's bottom from feet+ground[0] to feet+ground[1]
        self.own_reach = own_reach      # no NEW drop this close to our centre: standing still, our own weapon
                                        # (an axe ~28 px in front of us) bobs with our breathing (pkg_sight1:
                                        # 'drop at dx -28', walked into a wall at it for 5 s). Drops seen from
                                        # farther are still followed in here (re-found by their picture).
        self.char_half = char_half      # other characters: their weapons stick out as far
                                        # (items float just above the grass line; feet = top of our tag)
        self.hist = deque()             # (t, frame, grey strip, camera, feet)
        self.cam = 0.0                  # total camera shift so far (screen x = world x + cam)
        self.drops: list[Drop] = []

    def reset(self):
        self.hist.clear()
        self.drops = []

    # ------------------------------------------------------------------ helpers
    def _strip(self, frame, feet):
        y0, y1 = max(0, feet - 110), min(frame.shape[0], feet + 26)      # our floor: scenery + grass line
        return cv2.cvtColor(frame[y0:y1], cv2.COLOR_BGR2GRAY).astype(np.float32)

    def _characters(self, frame, me_x, feet):
        """Boxes owned by characters: everyone with a name tag (bodies are above their tags), and our own body.
        Ours is narrow (not our whole tag width): drops lie right at our feet, in pickup range."""
        out = []
        for x, y, w, h in find_tags(frame, rows=(feet - self.above - 20, feet + self.below + 20)):
            if me_x is not None and abs(x + w / 2 - me_x) < 20 and abs(y - feet) < 12:
                continue                                    # our own tag: our body box below instead
            half = max(w / 2, self.char_half)
            c = x + w / 2
            out.append((int(c - half), y - 110, int(2 * half), 110 + h))
        if me_x is not None:
            out.append((int(me_x - 20), feet - 72, 40, 72 + 16))
        return out

    # ------------------------------------------------------------------ detection
    def detect(self, old, new, feet, sx, chars=()) -> list:
        """[(x, y, w, h, score)] bobbing patches in `new` (screen), `old` taken ~lag_s earlier, camera moved `sx`."""
        H, W = new.shape[:2]
        y0, y1 = max(0, feet - self.above), min(H, feet + self.below)
        if y1 - y0 < 10:
            return []
        s = int(round(sx))
        A = cv2.warpAffine(old, np.float32([[1, 0, s], [0, 1, 0]]), (W, H))
        m = (cv2.absdiff(A[y0:y1], new[y0:y1]).max(axis=2) > self.diff).astype(np.uint8)
        m[:, :max(0, s) + 1] = 0                            # the edge the shift left empty
        m[:, W + min(0, s) - 1:] = 0
        m &= ui_mask(new.shape)[y0:y1]
        for bx, by, bw, bh in chars:
            m[max(0, by - y0):max(0, by + bh - y0), max(0, bx):max(0, bx + bw)] = 0
        m = cv2.dilate(m, np.ones((5, 5), np.uint8))
        n, _, st, _ = cv2.connectedComponentsWithStats(m)
        boxes = []
        for i in range(1, n):
            x, y, w, h, _ = (int(v) for v in st[i])
            if not (self.min_wh[0] <= w <= 3 * self.max_wh[0] and self.min_wh[1] <= h <= self.max_wh[1]):
                continue
            k = -(-w // self.max_wh[0])                     # items lying touching (a coin + a spore): one blob,
            for j in range(k):                              # but each bobs on its own -> test item-wide pieces
                boxes.append((x + j * w // k, y + y0, w // k if j < k - 1 else w - j * (w // k), h))
        out = []
        for x, y, w, h in boxes:
            if w < self.min_wh[0]:
                continue
            tpl = A[y:y + h, x:x + w]
            if tpl.std() < self.min_std:                    # flat patch: shading/flicker, not an object
                continue
            if text_mask(new[y:y + h, x:x + w]).mean() > self.max_text:
                continue                                    # a name tag (someone on a rope above us)
            b = self.bob[1]
            wx0 = max(0, x - 3)
            win = new[max(0, y - b):y + h + b, wx0:x + w + 3]
            if win.shape[0] < h or win.shape[1] < w:
                continue
            r = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
            r[~np.isfinite(r)] = -1
            _, sc, _, loc = cv2.minMaxLoc(r)
            dx, dy = loc[0] - (x - wx0), loc[1] - (y - max(0, y - b))
            row, col = y - max(0, y - b), x - wx0
            still = float(r[row, col]) if row < r.shape[0] and col < r.shape[1] else -1.0
            if sc >= self.match and abs(dx) <= 1 and self.bob[0] <= abs(dy) <= self.bob[1] and sc - still > 0.05:
                out.append((x, y + dy, w, h, float(sc)))   # where it is now
        return [b for b in out if self._on_ground(b, feet)]

    def _on_ground(self, b, feet) -> bool:
        """Lying on our floor. Not lower: below our feet is dirt and the chat window (pkg_sight3: megaphone lines
        scrolling up = vertical-only motion -> 'drops' in the dirt under us, 18 Z bursts on nothing). Lower
        platforms wait for jump & drop."""
        d = b[1] + b[3] - feet
        return self.ground[0] <= d <= self.ground[1]

    # ------------------------------------------------------------------ per frame
    def update(self, frame, t, feet, me_x=None) -> list:
        """Feed every frame; returns [(box, score)] of drops seen recently, in this frame's screen coordinates."""
        feet = int(feet)
        grey = self._strip(frame, feet)
        if self.hist:
            pt, _, pg, _, pfeet = self.hist[-1]
            if pg.shape == grey.shape and pfeet == feet:
                sx, resp = _shift(pg, grey)
                if resp > 0.2:
                    self.cam += sx
            else:                                           # we changed level: start over
                self.reset()
        self.hist.append((t, frame, grey, self.cam, feet))
        while self.hist and t - self.hist[0][0] > self.history_s:
            self.hist.popleft()
        chars = self._characters(frame, me_x, feet)

        # 1. re-find the drops we know (cheap: a small window each)
        for d in self.drops:
            x = int(round(d.wx + self.cam))
            if x < 0 or x + d.w > frame.shape[1]:
                continue
            b = self.bob[1] + 2
            win = frame[max(0, d.y - b):d.y + d.h + b, max(0, x - 4):x + d.w + 4]
            if win.shape[0] < d.h or win.shape[1] < d.w:
                continue
            sc, loc = -1.0, (0, 0)
            for tpl in d.tpls:
                if win.shape[0] < tpl.shape[0] or win.shape[1] < tpl.shape[1]:
                    continue
                r = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
                r[~np.isfinite(r)] = -1
                _, s_, _, l_ = cv2.minMaxLoc(r)
                if s_ > sc:
                    sc, loc = s_, l_
            nwx = max(0, x - 4) + loc[0] - self.cam
            anchor = d.wx if d.anchor is None else d.anchor
            if sc >= self.keep_score and abs(nwx - anchor) <= 3:      # (a coin hidden for a moment: the match
                d.seen = t                                            # slid onto the rope next to it, pkg_sight3)
                d.y = max(0, d.y - b) + loc[1]
                d.wx, d.anchor = nwx, anchor

        # 2. new detections from the bob test against a frame ~lag_s old
        old = next((h for h in self.hist if t - h[0] <= self.lag_s + 0.15 and t - h[0] >= self.lag_s - 0.15), None)
        if old is not None and old[4] == feet:
            sx = self.cam - old[3]
            for x, y, w, h, sc in self.detect(old[1], frame, feet, sx, chars):
                if me_x is not None and abs(x + w / 2 - me_x) < self.own_reach:
                    continue
                wx = x - self.cam
                near = [d for d in self.drops if abs((d.wx + d.w / 2) - (wx + w / 2)) < 12 and abs(d.y - y) < 14]
                if near:
                    d = near[0]
                    d.seen, d.hits = t, d.hits + 1
                    if abs(d.w * d.h - w * h) < 0.5 * d.w * d.h:
                        d.wx, d.y, d.w, d.h = wx, y, w, h
                        d.tpls = (d.tpls + [frame[y:y + h, x:x + w].copy()])[-4:]
                else:
                    self.drops.append(Drop(wx, y, w, h, [frame[y:y + h, x:x + w].copy()], t, t))

        # 3. forget: gone from view where we should see it, or too old
        keep = []
        for d in self.drops:
            x = d.wx + self.cam
            in_view = 0 <= x and x + d.w <= frame.shape[1]
            hidden = any(x < cx_ + cw and cx_ < x + d.w and cy < d.y + d.h and d.y < cy + ch
                         for cx_, cy, cw, ch in chars)                  # behind a character (us, too)
            if t - d.seen > self.memory_s or (in_view and not hidden and t - d.seen > self.lost_s):
                continue
            keep.append(d)
        self.drops = keep
        rep = sorted((d for d in self.drops if t - d.seen <= self.lost_s), key=lambda d: -d.w * d.h)
        out = []
        for d in rep:                       # a piece of a bigger drop (a coin's spin edge) is that drop
            b = (int(round(d.wx + self.cam)), d.y, d.w, d.h)
            if not any(abs(b[0] + b[2] / 2 - o[0] - o[2] / 2) < (b[2] + o[2]) / 2 - 2 and abs(b[1] - o[1]) < 16
                       for o, _ in out):
                out.append((b, d.hits))
        return out
