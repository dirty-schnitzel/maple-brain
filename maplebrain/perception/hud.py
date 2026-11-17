"""Fixed-position HUD readings and game-drawn markers (all measured on Classic World, 1366x768)."""
from pathlib import Path

import cv2
import numpy as np

# Screen areas that are UI, not world: minimap, quest helper, chat, quickslots, status bar
UI_RECTS = [(0, 0, 215, 195), (1140, 45, 1366, 160), (285, 630, 850, 768), (930, 620, 1085, 705),
            (285, 700, 1366, 768)]
# the 4x2 key layout at the bottom right (its keycaps; an item in a slot covers its keycap)
QUICKSLOT_RECT = (930, 620, 1085, 705)
# the chat rect's part above the status bar (x0, y0, x1, y1): world at native with the chat minimized (the user's
# setup) - the fit (step 3.3) counts it as world; its bottom = the play area's (perception/vote.py PLAY_H)
CHAT_WORLD = (285, 630, 850, 700)
SLOTS = {"shift": (942, 631), "insert": (977, 631), "home": (1012, 631), "pageup": (1047, 631),
         "ctrl": (942, 665), "delete": (977, 665), "end": (1012, 665), "pagedown": (1047, 665)}
SLOT_W, SLOT_H = 28, 25
MINIMAP_BOX = (4, 66, 210, 186)
_ui_cache: dict = {}


def minimap_rect(window) -> tuple:
    """The minimap window's whole rectangle (x0, y0, x1, y1) from its measured inside (nav.localize.find_window:
    x, y, w, h): the frame runs 5 px past the inside on the right and 14 px below it, the title panels fill the rest
    up to the screen's top-left corner. Measured on all 7 native recordings (2026-11-16): Line 1 <Area 1> 277x152,
    Ant Tunnel IV 230x198, Transfer Area 175x201 - UI_RECTS' fixed 215x195 was wrong both ways."""
    return (0, 0, window.x + window.w + 5, window.y + window.h + 14)


def ui_mask(shape, minimap: tuple | None = None) -> np.ndarray:
    """1 where the pixel is game world, 0 where it's UI. `minimap`: the minimap window's measured rectangle
    (minimap_rect) in place of UI_RECTS' default one.
    The CPU readers call it from their threads (2.9b): the mask is returned from the local, never re-read from the
    cache (another thread may clear it in between). Callers only read it."""
    key = (shape[:2], minimap)
    m = _ui_cache.get(key)
    if m is None:
        m = np.ones(shape[:2], np.uint8)
        for i, (x0, y0, x1, y1) in enumerate(UI_RECTS):
            if i == 0 and minimap is not None:
                x0, y0, x1, y1 = minimap
            m[y0:y1, x0:x1] = 0
        if len(_ui_cache) > 32:
            _ui_cache.clear()
        _ui_cache[key] = m
    return m


HP_TEXT = (505, 612)                 # x range of the HUD's "HP [409/783]" (the user, session 16: read the exact
MP_TEXT = (613, 720)                 # numbers, not the bar fill); "MP [10/359]"
NUM_Y = 740                          # the same 6x7 digit font and row as the EXP points
_slash = None


def _green_cols(frame, x0, x1, y=NUM_Y):
    h = cv2.cvtColor(frame[y:y + EXP_ROWS, x0:x1], cv2.COLOR_BGR2HSV)
    return (((h[..., 0] >= 30) & (h[..., 0] <= 75) & (h[..., 1] > 45) & (h[..., 2] > 60)).sum(axis=0) >= 2)


def _glyphs(frame, x, x_end, y=NUM_Y, min_score=0.6) -> tuple[str, float] | None:
    """Read the monospaced HUD text from x to x_end: 6 px digits and '/', 5 px thousands commas (only their
    bottom rows are lit). (text, worst cell score), or None if any cell is unclear."""
    global _exp_digits, _slash
    if _exp_digits is None:
        _exp_digits = np.load(Path(__file__).resolve().parents[2] / "assets" / "exp_digits.npy")
    if _slash is None:
        _slash = np.load(Path(__file__).resolve().parents[2] / "assets" / "hud_slash.npy")
    crop = frame[y:y + EXP_ROWS, x:x_end + 1]
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    green = (hsv[..., 0] >= 30) & (hsv[..., 0] <= 75) & (hsv[..., 1] > 35)   # digits: grey-white, S < 30
    out, i, worst = "", 0, 1.0
    while i + EXP_CELL <= g.shape[1]:
        cell = g[:, i:i + EXP_CELL]
        lit = cell > 120
        if lit.sum() >= 3 and green[:, i:i + EXP_CELL][lit].mean() > 0.5:
            break                                       # green: the closing ']' (JPEG blur hides its edge)
        if (cell[:5] > 120).sum() <= 1:                 # blank on top: a comma, or the end of the text
            if (cell[5:] > 120).sum() == 0:
                break
            i += EXP_COMMA
            continue
        if cell.std() < 1:
            return None
        sc = [float(cv2.matchTemplate(cell, t, cv2.TM_CCOEFF_NORMED)[0, 0]) for t in (*_exp_digits, _slash)]
        k = int(np.argmax(sc))
        if sc[k] < min_score:
            return None
        out += "/" if k == 10 else str(k)
        worst = min(worst, sc[k])
        i += EXP_CELL
    return (out, worst) if out else None


def read_pair(frame, span) -> tuple[int, int] | None:
    """(current, max) from the HUD's "[current/max]" text in x range `span` (HP_TEXT / MP_TEXT): the digits
    between the green brackets (first and last green piece; the text starts 2-4 px after the '[', tried
    each way, best read wins). None if it can't be read (covered, or not the HUD)."""
    x0, x1 = span
    cols = np.nonzero(_green_cols(frame, x0, x1))[0]
    if len(cols) < 2:
        return None
    pieces = [x0 + p[0] for p in np.split(cols, np.nonzero(np.diff(cols) > 1)[0] + 1)]
    best = None                                     # (stray green bits: the 'P' of "HP", the bar's edge)
    for i, left in enumerate(pieces):
        for right in pieces[i + 1:]:
            if right - left < 12:
                continue
            for start in range(left + 3, left + 7):
                r = _glyphs(frame, start, right - 1)
                if r is None or r[0].count("/") != 1:
                    continue
                cur, mx = r[0].split("/")
                if not cur or not mx or int(mx) == 0 or int(cur) > int(mx):
                    continue
                if best is None or r[1] > best[0]:
                    best = (r[1], int(cur), int(mx))
                if best[0] >= 0.9:                  # a clean read: no need to try the other alignments
                    return best[1], best[2]
    return None if best is None else (best[1], best[2])


def slot_filled(frame, key) -> bool | None:
    """Is there an item in the quickslot of `key`? An empty slot is a bare light keycap (0 % coloured pixels on
    every recorded frame); a red potion covers ~25 %. When the last one is used the slot empties.
    None: `key` has no slot in this layout."""
    if key not in SLOTS:
        return None
    x, y = SLOTS[key]
    hsv = cv2.cvtColor(frame[y:y + SLOT_H, x:x + SLOT_W], cv2.COLOR_BGR2HSV)
    return bool(((hsv[..., 1] > 90) & (hsv[..., 2] > 60)).mean() >= 0.08)


def in_quickslots(p) -> bool:
    x0, y0, x1, y1 = QUICKSLOT_RECT
    return p is not None and x0 - 40 <= p[0] <= x1 + 40 and y0 - 60 <= p[1] <= y1 + 20


EXP_TEXT = (749, 740)                # first digit cell of the HUD's "EXP. 885 [51.57%]" points (left-aligned)
EXP_CELL, EXP_ROWS = 6, 7            # the digits are monospaced: 6 px cells, 7 px tall
EXP_COMMA = 5                        # from 1,000 on the HUD groups thousands: "EXP. 1,012 [58.97%]", the "," takes 5 px
_exp_digits = None


def _exp_width(digits: int) -> int:
    return EXP_CELL * digits + EXP_COMMA * ((digits - 1) // 3)


def exp_points(frame) -> int | None:
    """The EXP points number from the HUD text (exact; the bar moves 1 px per ~0.9 % = 3-5 Stumps at lv ~13,
    perion6: most of our kills never moved it). Digits end where the green '[' starts; each 6x7 cell is matched
    against templates of 0-9 (assets/exp_digits.npy, from recorded frames). None if it can't be read.
    The text is tried at EXP_TEXT and 1 px to its left: in the native 1366x768 window it sits there (EXP_TEXT was
    measured on stretched windows, 2026-11-16: 0 of 11,576 ticks read at EXP_TEXT, 193 of 193 frames 1 px left). A
    wrong place reads None, not a wrong number (the cells' scores fall under 0.6)."""
    global _exp_digits
    if _exp_digits is None:
        _exp_digits = np.load(Path(__file__).resolve().parents[2] / "assets" / "exp_digits.npy")
    for dx in (0, -1):
        v = _exp_points_at(frame, EXP_TEXT[0] + dx, EXP_TEXT[1])
        if v is not None:
            return v
    return None


def _exp_points_at(frame, x0: int, y0: int) -> int | None:
    row = cv2.cvtColor(frame[y0:y0 + EXP_ROWS, x0:x0 + EXP_CELL * 7 + EXP_COMMA * 2 + 2], cv2.COLOR_BGR2HSV)
    green = (((row[..., 0] >= 30) & (row[..., 0] <= 75) & (row[..., 1] > 45) & (row[..., 2] > 60)).sum(axis=0) >= 2)
    # (the '[' is green-yellow: H 41-60, S 50-120 - paler on older frames; the bar's background is blue-grey)
    if not green.any():
        return None
    w = int(np.argmax(green))                       # the "[" starts ~-1..2 px after the text: 6 per digit + 5 per ",",'
    n = next((d for d in range(1, 8) if -1 <= w - _exp_width(d) <= 2), None)
    if n is None:
        return None
    starts, x = [], 0
    for i in range(n):
        starts.append(x)
        x += EXP_CELL + (EXP_COMMA if (n - 1 - i) % 3 == 0 and i < n - 1 else 0)
    g = cv2.cvtColor(frame[y0:y0 + EXP_ROWS, x0:x0 + x], cv2.COLOR_BGR2GRAY).astype(np.float32)
    value = 0
    for sx in starts:
        cell = g[:, sx:sx + EXP_CELL]
        if cell.std() < 1:
            return None
        sc = [float(cv2.matchTemplate(cell, t, cv2.TM_CCOEFF_NORMED)[0, 0]) for t in _exp_digits]
        d = int(np.argmax(sc))
        if sc[d] < 0.6:
            return None
        value = value * 10 + d
    return value


class HudText:
    """The HUD's HP / MP "[cur/max]" and EXP points, each read only when its pixels changed (PLAN-perception.md
    step 2.9a). Every reading is a pure function of one small crop of the number row (read_pair: rows NUM_Y..+7 of
    its span; exp_points: the same rows, x 748..803 - both places it tries), so a byte-identical crop gives the
    identical reading: the last one is returned instead (~2.3 ms -> ~0.01). On the native recordings the crops
    repeat on 94-98 % of saved frames 3 ticks apart (2026-11-16). One instance per reader (not thread-safe)."""

    CROPS = {"hp": (NUM_Y, HP_TEXT[0], HP_TEXT[1]), "mp": (NUM_Y, MP_TEXT[0], MP_TEXT[1]),
             "exp": (EXP_TEXT[1], EXP_TEXT[0] - 1, EXP_TEXT[0] + EXP_CELL * 7 + EXP_COMMA * 2 + 2)}

    def __init__(self):
        self._last = {}                                 # name -> (crop, reading)
        self.reads = self.hits = 0

    def _get(self, frame, name, read):
        y, x0, x1 = self.CROPS[name]
        crop = frame[y:y + EXP_ROWS, x0:x1]
        last = self._last.get(name)
        if last is not None and np.array_equal(last[0], crop):
            self.hits += 1
            return last[1]
        self.reads += 1
        v = read()
        self._last[name] = (crop.copy(), v)
        return v

    def read(self, frame) -> tuple:
        """(hp, mp, exp_points) as read_pair(HP_TEXT), read_pair(MP_TEXT), exp_points would read this frame."""
        return (self._get(frame, "hp", lambda: read_pair(frame, HP_TEXT)),
                self._get(frame, "mp", lambda: read_pair(frame, MP_TEXT)),
                self._get(frame, "exp", lambda: exp_points(frame)))


def minimap_dot(frame, box=MINIMAP_BOX):
    """Our yellow minimap marker (x, y) relative to the box's corner, or None if not exactly one round yellow dot.
    A wider box (nav.localize: the whole canvas) keeps the same corner, so readings stay comparable."""
    x0, y0, x1, y1 = box
    m = cv2.inRange(cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV),
                    np.array((23, 150, 180), np.uint8), np.array((35, 255, 255), np.uint8))
    n, _, st, ce = cv2.connectedComponentsWithStats(m)
    # hue >= 23 (was 20) and >= 6 px: a party member's orange dot (hue 18-19, edges 20) made a 2nd 'dot' - no
    # position for whole runs (rain1/rain2, 2026-11-02, in a party); ours is hue 26-28, 16-24 px
    dots = [(float(ce[i][0]), float(ce[i][1])) for i in range(1, n)
            if st[i][4] >= 6 and st[i][2] <= 8 and st[i][3] <= 8]
    return dots[0] if len(dots) == 1 else None


def find_mob_bars(frame) -> list:
    """Green HP bars the game draws over mobs that have been hit: pure green, ~3px tall."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    g = ((hsv[:, :, 0] >= 55) & (hsv[:, :, 0] <= 65) & (hsv[:, :, 1] > 235) & (hsv[:, :, 2] > 180)).astype(np.uint8)
    g &= ui_mask(frame.shape)
    n, _, st, _ = cv2.connectedComponentsWithStats(g)
    return [tuple(int(v) for v in st[i][:4]) for i in range(1, n) if 2 <= st[i][3] <= 4 and 3 <= st[i][2] <= 70]


def bar_mob_box(bar) -> tuple:
    """The mob standing under an HP bar (the bar's left edge is fixed; its green part shrinks with HP)."""
    x, y, w, h = bar
    return (x - 10, y + 8, max(w, 30) + 20, 50)
