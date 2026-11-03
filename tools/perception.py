"""Perception for the hunt experiment. All coordinates are in the normalized 1366x768 frame."""
import cv2
import numpy as np

# World-free screen areas: minimap, quest helper, chat, quickslots, status bar
UI_MASKS = [(0, 0, 215, 195), (1140, 45, 1366, 160), (285, 630, 850, 768), (930, 620, 1085, 705),
            (285, 700, 1366, 768)]
_UI = None


def ui_mask(shape):
    global _UI
    if _UI is None or _UI.shape != shape[:2]:
        _UI = np.ones(shape[:2], np.uint8)
        for x0, y0, x1, y1 in UI_MASKS:
            _UI[y0:y1, x0:x1] = 0
    return _UI


# ---------------------------------------------------------------- name tags
def text_mask(frame):
    """Light, unsaturated pixels: the text of name tags."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 2] > 180) & (hsv[:, :, 1] < 50)).astype(np.uint8)


def find_tags(frame):
    """Name tags: a line of light text ~6-13px tall sitting on a darkened box. Returns (x, y, w, h)."""
    text = text_mask(frame) & ui_mask(frame.shape)
    line = cv2.dilate(text, np.ones((3, 7), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(line)
    v = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.float32)
    tags = []
    for i in range(1, n):
        x, y, w, h, _ = (int(c) for c in st[i])
        if not (7 <= h <= 16 and 20 <= w <= 150):
            continue
        density = text[y:y + h, x:x + w].mean()
        if not 0.12 <= density <= 0.6:
            continue
        # a name is a row of separate glyphs; a pale mob body is one or two solid shapes
        g_n, _, g_st, _ = cv2.connectedComponentsWithStats(text[y:y + h, x:x + w])
        glyphs = [g for g in g_st[1:] if g[4] >= 4 and g[3] <= 13 and g[2] <= 12]
        if len(glyphs) < 4:
            continue
        # the box behind the text is darker than the scenery just above/below it
        box = v[y:y + h, x:x + w][text[y:y + h, x:x + w] == 0]
        around = np.concatenate([v[max(0, y - 6):y - 2, x:x + w].ravel(), v[y + h + 2:y + h + 6, x:x + w].ravel()])
        if box.size and around.size and box.mean() < around.mean() - 15:
            tags.append((x - 3, y - 3, w + 6, h + 6))
    return tags


def grab_self_template(frame, tag):
    x, y, w, h = tag
    return text_mask(frame)[y:y + h, x:x + w].astype(np.float32)


def find_self(frame, template, near=None, radius=250, min_score=0.75):
    """Our tag by text-shape match; searches around `near` (x, y) when given. Returns (x, y, w, h, score) or None."""
    t = (text_mask(frame) & ui_mask(frame.shape)).astype(np.float32)   # never match chat / HUD text
    ox = oy = 0
    if near is not None:
        ry = min(radius, 90)                                              # we can't move far vertically per frame
        ox, oy = max(0, int(near[0]) - radius), max(0, int(near[1]) - ry)
        t = t[oy:int(near[1]) + ry, ox:int(near[0]) + radius]
    if t.shape[0] < template.shape[0] or t.shape[1] < template.shape[1]:
        return None
    res = cv2.matchTemplate(t, template, cv2.TM_CCORR_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    if score < min_score:
        return None
    return (loc[0] + ox, loc[1] + oy, template.shape[1], template.shape[0], score)


def tag_body(tag, above=75, pad=18):
    """The character box standing on a name tag."""
    x, y, w, h = tag[:4]
    cx = x + w / 2
    return (int(cx - max(w / 2, 25) - pad), y - above, int(max(w, 50) + 2 * pad), above + h)


# ---------------------------------------------------------------- motion
def _gray(f):
    return cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)


def aligned_diff(a, b):
    ga, gb = _gray(a), _gray(b)
    (dx, dy), resp = cv2.phaseCorrelate(ga, gb)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    ga = cv2.warpAffine(ga, M, (ga.shape[1], ga.shape[0]), borderMode=cv2.BORDER_REPLICATE)
    return np.abs(gb - ga), resp


def _blobs(diff, mask, thresh=25):
    on = ((diff > thresh) & (mask > 0)).astype(np.uint8)
    on = cv2.morphologyEx(on, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    on = cv2.morphologyEx(on, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(on)
    return [tuple(int(v) for v in st[i][:4]) for i in range(1, n)
            if st[i][4] >= 60 and 10 <= st[i][2] <= 160 and 8 <= st[i][3] <= 140]


def overlaps(a, b, pad=6):
    return not (a[0] + a[2] + pad < b[0] or b[0] + b[2] + pad < a[0] or
                a[1] + a[3] + pad < b[1] or b[1] + b[3] + pad < a[1])


def moving_blobs(frames):
    """Blobs that changed in at least 2 consecutive frame pairs. Returns (blobs, min alignment response)."""
    mask = ui_mask(frames[0].shape)
    per_pair, resps = [], []
    for a, b in zip(frames, frames[1:]):
        d, r = aligned_diff(a, b)
        resps.append(r)
        per_pair.append(_blobs(d, mask))
    keep = [b for b in per_pair[-1] if any(overlaps(b, p) for p in per_pair[-2])] if len(per_pair) > 1 else []
    for b in per_pair[-2] if len(per_pair) > 1 else []:
        if any(overlaps(b, p) for p in per_pair[-3]) if len(per_pair) > 2 else False:
            if not any(overlaps(b, k) for k in keep):
                keep.append(b)
    return keep, min(resps) if resps else 0.0


def mob_candidates(frames, self_tag, cursor=None):
    """Moving blobs that are not a character standing on a name tag, nor the mouse cursor."""
    blobs, resp = moving_blobs(frames)
    bodies = [tag_body(t) for t in find_tags(frames[-1])]
    if self_tag:
        bodies.append(tag_body(self_tag))
    out = []
    for b in blobs:
        if any(overlaps(b, body, pad=0) for body in bodies):
            continue
        if cursor and abs(b[0] + b[2] / 2 - cursor[0]) < 40 and abs(b[1] + b[3] / 2 - cursor[1]) < 40:
            continue
        out.append(b)
    return out, resp, bodies


# ---------------------------------------------------------------- mob HP bars
def find_mob_bars(frame):
    """Green HP bars the game draws over mobs that have been hit: pure green, ~3px tall. Returns (x, y, w, h)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    g = ((hsv[:, :, 0] >= 55) & (hsv[:, :, 0] <= 65) & (hsv[:, :, 1] > 235) & (hsv[:, :, 2] > 180)).astype(np.uint8)
    g &= ui_mask(frame.shape)
    n, _, st, _ = cv2.connectedComponentsWithStats(g)
    return [tuple(int(v) for v in st[i][:4]) for i in range(1, n) if 2 <= st[i][3] <= 4 and 3 <= st[i][2] <= 70]


def bar_mob_box(bar):
    """The mob standing under an HP bar (bar's left edge is fixed; the green part shrinks as HP drops)."""
    x, y, w, h = bar
    return (x - 10, y + 8, max(w, 30) + 20, 50)


def find_self_gray(frame, template, near=None, radius=250, min_score=0.62):
    """Our name tag by grayscale normalized correlation (robust to dim / anti-aliased text and bright scenery).
    HUD/chat areas are blanked first. Returns (x, y, w, h, score) or None."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g[ui_mask(frame.shape) == 0] = 0
    ox = oy = 0
    if near is not None:
        ry = min(radius, 90)
        ox, oy = max(0, int(near[0]) - radius), max(0, int(near[1]) - ry)
        g = g[oy:int(near[1]) + ry, ox:int(near[0]) + radius]
    if g.shape[0] < template.shape[0] or g.shape[1] < template.shape[1]:
        return None
    _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(g, template.astype(np.float32), cv2.TM_CCOEFF_NORMED))
    if score < min_score:
        return None
    return (loc[0] + ox, loc[1] + oy, template.shape[1], template.shape[0], score)
