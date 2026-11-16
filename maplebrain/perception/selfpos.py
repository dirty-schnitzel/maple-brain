"""Locate our own character by its name tag (high-passed grayscale normalized correlation).

A binary 'white text' mask failed on dim, anti-aliased tags over green grass (letters came out as fragments);
grayscale correlation of the whole tag (dark box + light letters) held up on clear maps but not under drifting
clouds/fog (East Rocky Mountain, manual 20261101_225745_2 286 s): the haze lightens the dark box and the score
fell to 0.38-0.47 with the tag still readable. High-pass first (frame minus its gaussian blur, sigma 2): the haze
is low-frequency, the letters are not -> 0.76-0.86 under that cloud. Validated on 11.5k frames of 30+ runs:
+448 frames found, 2 lost (0.61), 0 at a different spot; own tag median 0.91 (5th pct 0.75), anything else
(other players' tags, scenery) <= 0.59. Flat windows (blanked UI, black screens) score a fake 1.0 after the
high-pass -> windows with almost no texture are excluded. HUD/chat are blanked so chat text can never match.

2026-11-16 (PLAN-perception.md step 2.7): assets/self_tag_gray.npy re-cut 1:1 from the native PNG recording
runs/play/20261116_154819_1 - the per-pixel median of 488 aligned tags (the tag's box is see-through: the median drops
the scenery behind it), same 17x74 frame and alignment as before. On 8 native recordings (whole-frame look): own tag
p50 0.86-0.88 -> 0.94-0.95 (Perion fog 0.91), found >= 0.66 on 1-3 points more frames, anything else <= 0.53
(was <= 0.53). A mask of the stable pixels was tried: 105 ms per look and false peaks up to 0.99 - not used.
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


def find_self(frame, template, near=None, radius=220, min_score=0.66, edges=True, gray=None, minimap=None):
    """Returns (x, y, w, h, score) of the tag, or None. `near` = (x, y) of the last tag centre-top. `edges`: also
    look for a tag cut by the screen's side (costs ~50 ms when there's nothing to find). `gray`: the frame's grey
    (cv2 BGR2GRAY) when the caller has it already (the Perceiver converts once per frame). `minimap`: the minimap
    window's measured rectangle (hud.ui_mask)."""
    if gray is None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    ui = ui_mask(frame.shape, minimap)
    ox = oy = 0
    if near is not None:                             # crop first: the same pixels as masking the whole frame
        ry = min(radius, 90)                         # we can't move far vertically between frames
        ox, oy = max(0, int(near[0]) - radius), max(0, int(near[1]) - ry)
        gray, ui = (a[oy:int(near[1]) + ry, ox:int(near[0]) + radius] for a in (gray, ui))
    g = gray.astype(np.float32)
    g[ui == 0] = 0
    if g.shape[0] < template.shape[0] or g.shape[1] < template.shape[1]:
        return None
    h, t = _hp(g), _hp(template.astype(np.float32))
    _, score, _, loc = cv2.minMaxLoc(_match(h, t))
    if score < min_score:
        return _at_edges(h, t, ox, oy, frame.shape[1], min_score) if edges else None
    return (loc[0] + ox, loc[1] + oy, template.shape[1], template.shape[0], float(score))


class GpuTagLook:
    """The whole-frame look for our tag on the GPU (PLAN-perception.md step 2.7): the same high-pass (grey - gaussian
    sigma 2, reflect border) and normalized correlation as `find_self`, as convolutions on the frame already uploaded
    for the mob detector -> the best place. The caller confirms it with `find_self(near=...)` on the CPU, so a found
    tag's place and score are exactly the CPU's. Measured on 306 native frames of 4 maps: the same answer as the CPU
    whole-frame look on every one (score within 0.0006), ~5 ms vs 28-45 ms."""

    def __init__(self, template: np.ndarray, device):
        import torch
        self.torch, self.F, self.dev = torch, torch.nn.functional, device
        k = int(round(SIGMA * 4 * 2 + 1)) | 1                    # cv2's kernel size for float images
        x = np.arange(k) - k // 2
        g = np.exp(-x ** 2 / (2 * SIGMA ** 2))
        self.gk, self.k = torch.tensor(g / g.sum(), dtype=torch.float32, device=device), k
        t = _hp(template.astype(np.float32))
        t = t - t.mean()
        self.t = torch.tensor(t, device=device)[None, None]
        self.tnorm, self.n = float((t ** 2).sum()), t.size
        self.box = torch.ones((1, 1) + t.shape, device=device)
        self.wts = torch.tensor([0.114, 0.587, 0.299], device=device)          # BGR -> grey (cv2's weights)
        self._ui = (None, None)
        # cudnn.benchmark times every new convolution shape once (3.5 s here, measured on the replays): at load, not
        # at the first tag loss mid-hunt
        self.look(torch.zeros((768, 1366, 3), dtype=torch.uint8, device=device), np.ones((768, 1366), np.uint8))

    def _hp(self, g):
        F, p = self.F, self.k // 2
        x = F.conv2d(F.pad(g[None, None], (p, p, 0, 0), mode="reflect"), self.gk.view(1, 1, 1, -1))
        x = F.conv2d(F.pad(x, (0, 0, p, p), mode="reflect"), self.gk.view(1, 1, -1, 1))
        return g - x[0, 0]

    def look(self, frame_u8, ui) -> tuple:
        """`frame_u8`: the frame on the device (h, w, 3) uint8; `ui`: hud.ui_mask (1 = world). -> (score, x, y) of
        the best place (top-left of the tag)."""
        torch, F = self.torch, self.F
        if self._ui[0] is not ui:
            self._ui = (ui, torch.from_numpy(np.ascontiguousarray(ui, dtype=np.float32)).to(self.dev))
        g = torch.round((frame_u8.float() * self.wts).sum(dim=2)) * self._ui[1]   # cv2's grey: rounded to uint8
        h = self._hp(g)[None, None]
        cross = F.conv2d(h, self.t)[0, 0]
        s1 = F.conv2d(h, self.box)[0, 0]
        s2 = F.conv2d(h * h, self.box)[0, 0]
        var = (s2 - s1 * s1 / self.n).clamp_min(1e-6)
        r = cross / torch.sqrt(var * self.tnorm)
        r = torch.where(var / self.n < MIN_STD ** 2, torch.full_like(r, -1.0), r)
        i = int(r.argmax())
        y, x = divmod(i, r.shape[1])
        return float(r[y, x]), x, y


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
