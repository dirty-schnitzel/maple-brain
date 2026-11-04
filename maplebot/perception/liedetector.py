"""The game's Lie Detector (an anti-bot test): seen by the title of its windows (two kinds known, see NAMES).

pkg_potions1: 52.4 s an announcement panel (bottom right, "5 sec until the Lie Detector mini-game starts"), then the
mini-game window (centre, "find the ... and click its number"). Both carry the same small gold title. Matched on
grayscale over the whole frame (the windows can sit anywhere): panel 0.89-0.90, mini-game ~1.0; the best match on
~14,000 frames of 29 runs without it was 0.67. A full-frame match costs ~13 ms, so it runs every ~0.3 s.
"""
from pathlib import Path

import cv2
import numpy as np

NAMES = ("lie_detector_panel.npy", "lie_detector_game.npy",
         # a second kind (pkg_sight5, 55.5-82.3 s; the bot hunted on through it): a blue title bar with white
         # "The Lie Detector Mini-game" - on the announcement panel ("go to a safe place") and on the mouse game
         # ("follow the fading figure"). Panel 1.00, game 0.96; best on 7311 frames of other runs 0.55.
         "lie_detector_blue_title.npy",
         # a third kind (the user's screenshot, 2026-11-02 14:07, Rain-Forest): no window, a translucent blue box in
         # the centre with white "Question in 10 seconds" / "Answer within 10 seconds" (a quiz). Template = the words
         # "Question in" only (the number counts down). Screenshot 1.00; best on 11,833 frames of other runs 0.52.
         "lie_detector_question.npy")


class LieDetector:
    def __init__(self, templates, min_score: float = 0.8, every_s: float = 0.3):
        self.templates, self.min_score, self.every_s = list(templates), min_score, every_s
        self.next_t, self.last = -1e9, (False, 0.0, None)

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

    def check(self, frame, t: float) -> tuple[bool, float, tuple | None]:
        """Throttled: matches at most every `every_s`; in between the last answer stands. `t` is the hunt's clock,
        which restarts at 0 each hunt while this object lives on in `serve`: a clock behind the last look means a
        new hunt -> look now (2026-11-04: the cached 'on screen' from the hunt it stopped ended every restart)."""
        if t >= self.next_t or t < self.next_t - self.every_s:
            self.next_t = t + self.every_s
            s, loc = self.score(frame)
            self.last = (s >= self.min_score, s, loc)
        return self.last
