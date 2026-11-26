"""The HP meter Classic World draws over a mob WE hit (PLAN-tracker step 5a): perception FINDS the meters and READS each
one's green share; the mob tracker (track/mobs.py) ties each meter to its track. Measured on the 13 sound captures by
tools/perc/track/proto_meter.py (PLAN-tracker.md "Step 5a, 2026-11-26"); everything from the recordings.

WHAT THE CLIENT DRAWS (pixel-exact on the frames): a box 52 x 10 px, opaque -
    row 0 black; row 1 white (cols 1..50; col 0 and 51 black); rows 2..7: col 0 black, col 1 white, col 2 black,
    cols 3..48 the INSIDE (46 px), col 49 black, col 50 white, col 51 black; row 8 as row 1; row 9 black.
    The inside: row 2 black; rows 3..5 green (0, 255, 0) from the left = the HP left, then the HP lost: red at the hit
    (R ~220), fading linearly to black (0, 0, 0) in 2.0 s; row 6 a darker line under both; row 7 black.
  - It shows only over a mob we hit (144 of 144 new meters came 0.27-0.72 s after our `q` key-down, `e` 0.35-0.55, `w`
    0.44-0.58), "almost immediately" with the hit, at a fixed size; it goes at the killing hit (~0.1 s before the die
    pose is seen); several mobs hit = several meters (overlapping when the mobs stand close).
  - WHERE (one rule for Slime, Bubbling, Green / Horny / Zombie Mushroom, Evil Eye and the flying Stirge): its box's top
    = the feet y + the pose frame's body box top (mob.json `lt` y) - 30; centred on that body box: its left = the feet x
    + floor((lt x + rb x) / 2) - 26, with lt / rb mirrored for a mob facing right. (mob.json's `head` point does not fit.)
  - It is drawn with the mob: our character, other players, front scenery (a rope) and damage digits can be over it.

THE READER (`MeterReader.read`): for every mob the fit found, a band of the frame around where its meter must be (its
pose frame's box + `tol` px each way: the fit's pose frame one off moves a meter up to ~9 px) - not the whole screen; in it every column where box rows 1, 2, 7, 8 read white,
black, black, white (true whatever the inside shows); such columns of one row grouped into a meter; the all-white
frame column left of the first (box column 1) or right of the last (box column 50) fixes the box, so a meter cut by
the screen's side or partly drawn over is read from its one end. A first look at five columns of each band skips the
bands with no meter (most frames have none). The fill = the green columns / 46; the green runs from
the inside's left, so it is known when the box's place is known and the last green column seen touches the first lost
column seen (the part off the screen or drawn over follows from them; all 46 green / none green alike); else None. Each meter names the fit mobs whose expected box lies within `tie` px of it (`cand`): the tracker decides.
"""
import time

import numpy as np

BOX_W, BOX_H = 52, 10
INSIDE = 46                             # the inside's columns
IN_X = 3                                # the inside's first column in the box
DY = -30                                # the box's top over the pose frame's body box top
DX = -26                                # the box's left from the body box's middle
MIN_COLS = 6                            # frame columns of one row that make a meter
SAMPLE = np.array([6, 16, 26, 36, 46])  # the first look's columns of a band, from the expected box's left (the middle
                                        # three are inside the meter's frame columns wherever it is within 10 px)
PLAY_H = 700
WHITE, BLACK = 235, 24                  # every channel >= WHITE / <= BLACK


def offsets(mobs: dict) -> dict:
    """{(type, "anim_i", facing): (dx, dy)} - the expected box's top-left from the screen feet, for every pose frame
    of the map's mob types (`mobs` = {id: mob.json dict}, MapKit.mobs) that has a body box."""
    out = {}
    for mid, info in mobs.items():
        for anim, fs in (info.get("frames") or {}).items():
            for i, f in enumerate(fs or []):
                lt, rb = f.get("lt"), f.get("rb")
                if not lt or not rb:
                    continue
                for facing, (l, r) in (("left", (lt[0], rb[0])), ("right", (-rb[0], -lt[0]))):
                    out[(int(mid), f"{anim}_{i}", facing)] = ((l + r) // 2 + DX, lt[1] + DY)
    return out


class MeterReader:
    """`read(frame, fit)` -> this frame's meters [(x0, y0, fill, cols, cand)]: the box's top-left (screen px), the green
    share (None: not known), the frame columns seen (48 = all), the indexes into `fit` of the mobs whose expected box is
    within `tie` of it. `tol`: the band searched around a mob's expected box (config.Perception meter_tol / meter_tie).
    `ms`: the last read's milliseconds."""

    def __init__(self, mobs: dict, tol: tuple = (10, 10), tie: tuple = (3, 2)):
        self.off = offsets(mobs)
        self.ms = 0.0
        self.tol, self.tie = tuple(tol), tuple(tie)
        tx, ty = self.tol
        self.bh, self.bw = BOX_H + 2 * ty, BOX_W + 2 * tx
        self._dy = np.arange(self.bh)[None, :, None]
        self._dx = np.arange(self.bw)[None, :]

    def expected(self, fit) -> list:
        """Per fit mob its expected box's top-left (screen px), or None (its pose frame has no body box)."""
        out = []
        for m in fit or []:
            o = self.off.get((m["type"], m["pose"], m["facing"]))
            out.append(None if o is None else (int(m["feet"][0]) + o[0], int(m["feet"][1]) + o[1]))
        return out

    def read(self, frame: np.ndarray, fit) -> list:
        a = time.perf_counter()
        exp = self.expected(fit)
        at = [e for e in exp if e is not None]
        out = self._find(frame, at, exp) if at else []
        self.ms = 1000 * (time.perf_counter() - a)
        return out

    @staticmethod
    def _pattern(px, ok):
        """(..., rows, cols, 3) pixels -> (..., rows - 7, cols): box rows 1, 2, 7, 8 white, black, black, white."""
        mn, mx = px.min(axis=-1), px.max(axis=-1)
        wht, blk = (mn >= WHITE) & ok, (mx <= BLACK) & ok
        return wht[..., :-7, :] & blk[..., 1:-6, :] & blk[..., 6:-1, :] & wht[..., 7:, :], wht

    def _find(self, frame, at, exp) -> list:
        tx, ty = self.tol
        H, W = min(PLAY_H, frame.shape[0]), frame.shape[1]
        oy = np.array([e[1] - ty for e in at])[:, None, None]
        ox = np.array([e[0] - tx for e in at])[:, None, None]
        ys = oy + self._dy                                          # (M, bh, 1)
        oky = (ys >= 0) & (ys < H)
        yc = np.clip(ys, 0, H - 1)
        # a first look: SAMPLE columns of each band (any meter within 10 px covers the middle three); the band is read
        # whole only where one shows the frame's pattern - most frames have no meter
        xs = ox + (tx + SAMPLE)[None, None, :]                      # (M, 1, 5)
        okx = (xs >= 0) & (xs < W)
        p, _ = self._pattern(frame[yc, np.clip(xs, 0, W - 1)], oky & okx)
        hit = np.flatnonzero(p.any(axis=(1, 2)))
        found = {}
        for k in hit.tolist():
            bx, by = int(ox[k, 0, 0]), int(oy[k, 0, 0])
            xk = bx + self._dx[0]                                   # (1, bw)
            ok = oky[k] & (xk >= 0) & (xk < W)
            band = frame[yc[k], np.clip(xk, 0, W - 1)]              # (bh, bw, 3)
            pk, wht = self._pattern(band, ok)
            for r in np.flatnonzero(pk.sum(axis=1) >= MIN_COLS).tolist():
                cols = np.flatnonzero(pk[r])
                i = 0
                while i < len(cols):
                    j = i
                    while j + 1 < len(cols) and cols[j + 1] - cols[i] < BOX_W - 4:
                        j += 1
                    if j - i + 1 >= MIN_COLS:
                        m = self._meter(band, wht, cols[i:j + 1], r, bx, by)
                        key = (m[0], m[1])
                        if key not in found or found[key][3] < m[3]:
                            found[key] = m
                    i = j + 1
        out = []
        for x0, y0, fill, n in found.values():
            cand = tuple(q for q, e in enumerate(exp) if e is not None and abs(e[0] - x0) <= self.tie[0]
                         and abs(e[1] - y0) <= self.tie[1])
            out.append((x0, y0, fill, n, cand))
        return out

    @staticmethod
    def _meter(band, wht, cols, r, bx, by) -> tuple:
        """One group of frame columns (band coords: row r = box row 1) -> (x0, y0, fill, n) in screen px."""
        xa, xb = int(cols[0]), int(cols[-1])
        left = xa >= 1 and bool(wht[r:r + 8, xa - 1].all())
        right = xb + 1 < wht.shape[1] and bool(wht[r:r + 8, xb + 1].all())
        x0 = xa - 2 if left or not right else xb + 1 - (BOX_W - 2)
        fill = None
        if left or right:
            ins = cols[(cols >= x0 + IN_X) & (cols < x0 + IN_X + INSIDE)]
            px = band[r + 2:r + 5, ins]                             # (3, k, 3) BGR: the inside's rows 3..5
            g = ((px[..., 1] >= 230) & (px[..., 0] <= BLACK) & (px[..., 2] <= BLACK)).all(axis=0)
            lost = ((px[..., 1] <= BLACK) & (px[..., 0] <= BLACK)).all(axis=0) & ~g
            idx = ins - x0 - IN_X                                   # the inside's columns seen (0..45)
            gmax = int(idx[g].max()) if g.any() else -1             # green runs from the left: the fill is known
            lmin = int(idx[lost].min()) if lost.any() else INSIDE   # when the last green seen touches the first
            if gmax + 1 == lmin:                                    # lost seen (the hidden rest follows from them)
                fill = round(lmin / INSIDE, 4)
        return bx + x0, by + r - 1, fill, len(cols)
