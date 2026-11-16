"""The game's Lie Detector (an anti-bot test): seen by the title of its windows (two kinds known, see NAMES).

pkg_potions1: 52.4 s an announcement panel (bottom right, "5 sec until the Lie Detector mini-game starts"), then the
mini-game window (centre, "find the ... and click its number"). Both carry the same small gold title. Matched on
grayscale over the whole frame (the windows can sit anywhere): panel 0.89-0.90, mini-game ~1.0; the best match on
~14,000 frames of 29 runs without it was 0.67. A full-frame match costs ~13-22 ms per template on the CPU, so it
runs every ~0.3 s - on its own thread (2026-11-05, runs/kd2: 4 templates beside the GPU / tag threads took 100-500 ms
and were the loop's worst stalls); the answer is at most one look late (~0.3-0.5 s; the Lie Detector gives 10+ s).
With the GPU detector (2026-11-16, PLAN-perception.md step 2.8) the hunt looks on the GPU instead (`GpuLieLook`, on
the frame uploaded at the tick's start, the same scores, ~3.5 ms): on the frame itself, no thread, never late.

The bar is 0.75 since 2026-11-16 (was 0.80; the user's call): the game runs at native 1366x768 now and the old
gold-title templates were cut from stretched windows. Later that day (step 2.8) the gold title is cut 1:1 from the
client's own windows instead (tools/perc/ld/cut_native.py: AntiMacro.img, the see-through title bar graded over real
native scenery): the client's panel / mini-game pasted on native frames score >= 0.970 (the old panel template went
down to 0.677 there, the old game one to 0.780 - the bar was nearly missed); the best false score on all 8641 native
frames of the 2026-11-16 recordings fell 0.671 -> 0.496 for the gold title; every saved real one (stretched captures)
is still caught (0.83-0.94). The bar goes back to 0.80 only on the user's word.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

NAMES = (# the small gold "LIE DETECTOR" of the announcement panel and the mini-game window (the same letters in
         # both), 1:1 from the client (AntiMacro.img lieDetector/back1: the letters + 1-2 px, over grey 96); 8 x 65
         "lie_detector_title.npy",
         # the sound kind (AntiMacro.img soundLieDetector: "N sec from now, the Lie Detector mini-game will begin.
         # Ensure your Normal SFX is loud enough"): a larger yellow-green title, not seen live yet; 1:1 from the
         # client, pasted on native frames >= 0.995, best false score 0.434
         "lie_detector_sound.npy",
         # a second kind (pkg_sight5, 55.5-82.3 s; the bot hunted on through it): a blue title bar with white
         # "The Lie Detector Mini-game" - on the announcement panel ("go to a safe place") and on the mouse game
         # ("follow the fading figure"). Panel 1.00, game 0.96; best on 7311 frames of other runs 0.55.
         "lie_detector_blue_title.npy",
         # a third kind (the user's screenshot, 2026-11-02 14:07, Rain-Forest): no window, a translucent blue box in
         # the centre with white "Question in 10 seconds" / "Answer within 10 seconds" (a quiz). Template = the words
         # "Question in" only (the number counts down). Screenshot 1.00; best on 11,833 frames of other runs 0.52.
         "lie_detector_question.npy")


class GpuLieLook:
    """The title templates matched on the GPU (PLAN-perception.md step 2.8) on the frame already uploaded for the mob
    detector: cv2's TM_CCOEFF_NORMED, the same score to ~2e-5 and the same place (90 saved Lie Detector frames + 346
    native frames, tools/perc/ld/ld_check.py). One FFT of the frame, a product + inverse per template (one batched
    call); the window sums from integral images in int64 (exact), cv2's rule for (near) flat windows. ~3.5 ms for the
    4 templates of 2026-11-16 vs ~90 ms on the CPU."""

    GREY = (3735, 19235, 9798)                            # cv2's BGR -> grey: 15-bit fixed point, bit for bit

    def __init__(self, templates, device):
        import torch
        self.torch, self.F, self.dev = torch, torch.nn.functional, device
        self.templates = [np.asarray(t) for t in templates]
        self.iw = torch.tensor(self.GREY, dtype=torch.int32, device=device)
        self.meta = []
        for t in self.templates:
            t = t.astype(np.float64) - t.mean()
            self.meta.append((float((t ** 2).sum()), t.size) + t.shape)
        self._k = (None, None)                            # (frame shape, the templates' spectra for it)
        # the first FFT of a shape plans it (cuFFT, ~0.3 s): at load, not at the first look mid-hunt
        self.look(torch.zeros((768, 1366, 3), dtype=torch.uint8, device=device))

    def _kernels(self, h, w):
        if self._k[0] != (h, w):
            ks = np.zeros((len(self.templates), h, w), np.float32)
            for k, t in zip(ks, self.templates):
                t = t.astype(np.float64) - t.mean()
                k[:t.shape[0], :t.shape[1]] = t[::-1, ::-1]   # flipped: the product = correlation, valid part at the end
            self._k = ((h, w), self.torch.fft.rfft2(self.torch.from_numpy(ks).to(self.dev)))
        return self._k[1]

    def gray(self, frame_u8):
        """cv2.cvtColor(BGR2GRAY) of an uploaded (h, w, 3) uint8 frame, bit for bit, as int32 (h, w)."""
        return ((frame_u8.int() * self.iw).sum(dim=2) + 16384) >> 15

    def look(self, frame_u8) -> tuple[float, tuple | None]:
        """Best match of any template on the uploaded frame: (score, top-left), as `LieDetector.score`."""
        return self.looks(frame_u8)[0][:2]

    def looks(self, frame_u8) -> list:
        """Every template's best (score, (x, y)), the best first: [(score, loc, template index), ...]."""
        torch, F = self.torch, self.F
        g = self.gray(frame_u8)
        h, w = g.shape
        c = torch.fft.irfft2(torch.fft.rfft2(g.float())[None] * self._kernels(h, w), s=(h, w))
        gl = g.long()
        ii = F.pad(gl.cumsum(0).cumsum(1), (1, 0, 1, 0))
        ii2 = F.pad((gl * gl).cumsum(0).cumsum(1), (1, 0, 1, 0))
        var, best = {}, []
        for j, (tn, n, th, tw) in enumerate(self.meta):
            hh, ww = h - th + 1, w - tw + 1
            if (th, tw) not in var:                        # n^2 x the window's variance, exact in int64
                def box(i):
                    return i[th:th + hh, tw:tw + ww] - i[:hh, tw:tw + ww] - i[th:th + hh, :ww] + i[:hh, :ww]
                s1, s2 = box(ii), box(ii2)
                var[(th, tw)] = (n * s2 - s1 * s1).float()
            den = torch.sqrt(var[(th, tw)] * (tn / n))
            num = c[j, th - 1:, tw - 1:]
            r = torch.where(num.abs() < den, num / den.clamp_min(1e-30),       # cv2: |num| >= den (flat window)
                            torch.where(num.abs() < den * 1.125, num.sign(), torch.zeros_like(num)))   # -> +-1 or 0
            m = r.reshape(-1).max(0)
            best.append(torch.stack([m.values, m.indices.float()]))
        out = torch.stack(best).cpu().numpy()             # one wait for the GPU
        res = []
        for j, (s, i) in enumerate(out):
            ww = w - self.meta[j][3] + 1
            res.append((float(s), (int(i) % ww, int(i) // ww), j))
        return sorted(res, key=lambda r: -r[0])


class LieDetector:
    def __init__(self, templates, min_score: float = 0.75, every_s: float = 0.3, background: bool = True):
        self.templates, self.min_score, self.every_s = list(templates), min_score, every_s
        self.next_t, self.last = -1e9, (False, 0.0, None)
        self.pool = ThreadPoolExecutor(1, thread_name_prefix="lie") if background else None
        self.pending = None                               # the look running on the thread
        self.gpu = None                                   # GpuLieLook (use_gpu): the hunt's looks on the GPU

    @classmethod
    def load(cls, assets: Path, **kw) -> "LieDetector":
        return cls([np.load(assets / n) for n in NAMES], **kw)

    def score(self, frame) -> tuple[float, tuple | None]:
        """Best match of any title template: (score, top-left)."""
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        best, loc = 0.0, None
        for tpl in self.templates:
            _, m, _, at = cv2.minMaxLoc(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED))
            if m > best:
                best, loc = float(m), at
        return best, loc

    def seen(self, frame) -> bool:
        s, _ = self.score(frame)
        return s >= self.min_score

    def use_gpu(self, device) -> None:
        """The hunt's looks on the GPU from now on (the Perceiver with the GPU detector); built once per device."""
        if self.gpu is None or self.gpu.dev != device:
            self.gpu = GpuLieLook(self.templates, device)

    def check(self, frame, t: float, gray=None, frame_u8=None) -> tuple[bool, float, tuple | None]:
        """Throttled: matches at most every `every_s`; in between the last answer stands. `t` is the hunt's clock,
        which restarts at 0 each hunt while this object lives on in `serve`: a clock behind the last look means a
        new hunt -> look now (2026-11-04: the cached 'on screen' from the hunt it stopped ended every restart).
        `gray`: the frame's grey, made fresh for this frame and never written to (the Perceiver's) - the thread
        reads it as it is instead of a copy of the colour frame. `frame_u8`: this frame on the GPU (uploaded for
        the mob detector): with `use_gpu` the look runs there, now, on this frame (~3.5 ms) - no thread."""
        if self.gpu is not None and frame_u8 is not None:
            if self.pending is not None:                   # a CPU look from before: this frame's answer replaces it
                self.pending.result()
                self.pending = None
            if t >= self.next_t or t < self.next_t - self.every_s:     # due, or a new hunt (clock restarted)
                self.next_t = t + self.every_s
                s, loc = self.gpu.look(frame_u8)
                self.last = (s >= self.min_score, s, loc)
            return self.last
        if self.pending is not None and self.pending.done():
            s, loc = self.pending.result()
            self.last, self.pending = (s >= self.min_score, s, loc), None
        new_hunt = t < self.next_t - self.every_s
        if new_hunt and self.pending is not None:          # a look from the last hunt: wait for it, it's this frame's
            self.pending.result()                          # picture no more - look again now
            self.pending = None
        if new_hunt and self.pool is not None:             # never carry 'on screen' into a new hunt; the fresh
            self.last = (False, 0.0, None)                 # look answers a tick later
        if (t >= self.next_t or new_hunt) and self.pending is None:
            self.next_t = t + self.every_s
            if self.pool is None:
                s, loc = self.score(frame if gray is None else gray)
                self.last = (s >= self.min_score, s, loc)
            else:
                self.pending = self.pool.submit(self.score, frame.copy() if gray is None else gray)
        return self.last
