"""Locate our own character by its name tag (high-passed grayscale normalized correlation).

A binary 'white text' mask failed on dim, anti-aliased tags over green grass (letters came out as fragments);
grayscale correlation of the whole tag (dark box + light letters) held up on clear maps but not under drifting
clouds/fog (East Rocky Mountain, manual 20261101_225745_2 286 s): the haze lightens the dark box and the score
fell to 0.38-0.47 with the tag still readable. High-pass first (frame minus its gaussian blur, sigma 2): the haze
is low-frequency, the letters are not -> 0.76-0.86 under that cloud. Validated on 11.5k frames of 30+ runs:
+448 frames found, 2 lost (0.61), 0 at a different spot; own tag median 0.91 (5th pct 0.75), anything else
(other players' tags, scenery) <= 0.59. Flat windows (blanked UI, black screens) score a fake 1.0 after the
high-pass -> windows with almost no texture are excluded. HUD/chat are blanked so chat text can never match.
"""
import cv2
import numpy as np

from .hud import ui_mask

SIGMA = 2.0
MIN_STD = 3.0           # the window's high-passed std: below this it's flat (a real tag: >= ~10)


def _hp(g):
    return g - cv2.GaussianBlur(g, (0, 0), SIGMA)


def _match(h, t):
    """TM_CCOEFF_NORMED of high-passed `t` over high-passed `h`, flat windows set to -1."""
    r = cv2.matchTemplate(h, t, cv2.TM_CCOEFF_NORMED)
    th, tw = t.shape
    m = cv2.boxFilter(h, -1, (tw, th), anchor=(0, 0), borderType=cv2.BORDER_CONSTANT)
    m2 = cv2.boxFilter(h * h, -1, (tw, th), anchor=(0, 0), borderType=cv2.BORDER_CONSTANT)
    sd = np.sqrt(np.maximum(m2 - m * m, 0))[:r.shape[0], :r.shape[1]]
    r[(sd < MIN_STD) | ~np.isfinite(r)] = -1
    return r


def find_self(frame, template, near=None, radius=220, min_score=0.66):
    """Returns (x, y, w, h, score) of the tag, or None. `near` = (x, y) of the last tag centre-top."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g[ui_mask(frame.shape) == 0] = 0
    ox = oy = 0
    if near is not None:
        ry = min(radius, 90)                         # we can't move far vertically between frames
        ox, oy = max(0, int(near[0]) - radius), max(0, int(near[1]) - ry)
        g = g[oy:int(near[1]) + ry, ox:int(near[0]) + radius]
    if g.shape[0] < template.shape[0] or g.shape[1] < template.shape[1]:
        return None
    h, t = _hp(g), _hp(template.astype(np.float32))
    _, score, _, loc = cv2.minMaxLoc(_match(h, t))
    if score < min_score:
        return _at_edges(h, t, ox, oy, frame.shape[1], min_score)
    return (loc[0] + ox, loc[1] + oy, template.shape[1], template.shape[0], float(score))


def _at_edges(h, t, ox, oy, frame_w, min_score, min_visible=44, step=1):
    """The tag partly off the screen (at a map's end the camera stops and we walk on to the edge,
    pkg_sprites3 69-76 s): match the visible part of the template against the frame's edge columns.
    Returns the full tag box, reaching past the edge. `h` = the high-passed (possibly cropped) search area at
    (ox, oy), `t` = the high-passed template."""
    th, tw = t.shape
    best = None
    for k in range(tw - 1, min_visible - 1, -step):
        if ox + h.shape[1] >= frame_w and h.shape[1] >= k:             # right edge: the tag's left part shows
            _, sc, _, loc = cv2.minMaxLoc(_match(h[:, h.shape[1] - k:], t[:, :k]))
            if sc >= min_score and (best is None or sc > best[4]):
                best = (frame_w - k, loc[1] + oy, tw, th, float(sc))
        if ox == 0 and h.shape[1] >= k:                                 # left edge: the tag's right part shows
            _, sc, _, loc = cv2.minMaxLoc(_match(h[:, :k], t[:, tw - k:]))
            if sc >= min_score and (best is None or sc > best[4]):
                best = (k - tw, loc[1] + oy, tw, th, float(sc))
    return best
