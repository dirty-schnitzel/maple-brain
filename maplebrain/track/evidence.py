"""Evidence for the tracker: "does this place show the scene?" (PLAN-tracker.md design 2). One interface, two sources:

  Bitmaps  the kept replay's two bitmaps of the play area (tools/perc/track/dump.py): `shows` (the pixel can show a mob
           and the frame equals the expected scene there within the fit's tolerance: THE SCENE SHOWS THERE) and
           `world` (the pixel can show a mob: known scenery, no opaque UI, no front background over it - the fit's
           `valid`). CPU arrays; the tracker is graded on recorded footage with them.
  Gpu      the same two, live, from the fit's own tensors of this frame (fit.Fitter._last: the frame, the expected
           scene, valid): shows = valid & max over the colours of |frame - expected| <= tol - dump.py's formula, so the
           two sources answer alike (step 3's gate checks it on fresh footage). One gather a group of places, one
           transfer back.

A question is a GROUP: n places (screen feet fx, fy) x one body core (offsets dx, dy from the feet, track/kinds.py).
`count(groups)` -> per group three int arrays over its places: the core's pixels inside the play area that show the
scene, inside it, and inside it AND world. A source that has nothing for this frame (no camera): `ready` False.
"""
import numpy as np

PLAY_H, SW = 700, 1366


class Evidence:
    """The interface. `ready`: there is a frame to ask about."""
    ready = False

    def count(self, groups: list) -> list:
        """[(fx (n,), fy (n,), dx (k,), dy (k,))] -> [(shows (n,), inside (n,), world (n,))] int64 counts."""
        raise NotImplementedError


class Bitmaps(Evidence):
    """The kept replay's bitmaps of one frame: bool (PLAY_H, SW) arrays (or None on a frame without a camera)."""

    def __init__(self, shows=None, world=None):
        self.shows, self.world = shows, world
        self.ready = shows is not None

    def count(self, groups: list) -> list:
        out = []
        for fx, fy, dx, dy in groups:
            xs = fx[:, None] + dx[None, :]
            ys = fy[:, None] + dy[None, :]
            inside = (xs >= 0) & (xs < SW) & (ys >= 0) & (ys < PLAY_H)
            xc, yc = np.clip(xs, 0, SW - 1), np.clip(ys, 0, PLAY_H - 1)
            out.append(((self.shows[yc, xc] & inside).sum(axis=1), inside.sum(axis=1),
                        (self.world[yc, xc] & inside).sum(axis=1)))
        return out


class Gpu(Evidence):
    """This frame's fit tensors (Fitter._last: frame uint8 (PLAY_H, SW, 3), C, expected float (PLAY_H, SW, 3), valid
    bool (PLAY_H, SW)) on the GPU. `tol` = the fit's (FitConfig.tol). The shows map is made once per frame, on the
    first question; the cores' offsets stay on the GPU between frames."""

    def __init__(self, fitter, tol: float):
        self.fitter, self.tol = fitter, tol
        self.torch = fitter.torch
        self._key = None
        self._shows = self._valid = None
        self._cores = {}                                # id of the offsets array -> (dx, dy) on the GPU
        self.asked = 0                                  # places asked on the last frame (all groups)

    @property
    def ready(self) -> bool:
        return self.fitter._last is not None

    def _frame(self):
        last = self.fitter._last
        if self._key is not last:
            frame, _C, exp, valid = last
            self._shows = (valid & ((frame.float() - exp).abs().amax(dim=2) <= self.tol)).reshape(-1)
            self._valid = valid.reshape(-1)
            self._key = last
        return self._shows, self._valid

    def _core(self, dx, dy):
        k = (id(dx), id(dy))
        c = self._cores.get(k)
        if c is None or c[2] is not dx:
            t = self.torch
            c = (t.from_numpy(np.ascontiguousarray(dx)).to(self.fitter.dev),
                 t.from_numpy(np.ascontiguousarray(dy)).to(self.fitter.dev), dx)
            self._cores[k] = c
        return c[0], c[1]

    def count(self, groups: list) -> list:
        if not groups:
            return []
        t = self.torch
        shows, valid = self._frame()
        sizes, parts = [], []
        feet = np.concatenate([np.stack([fx, fy]) for fx, fy, _, _ in groups], axis=1)
        feet = t.from_numpy(np.ascontiguousarray(feet, dtype=np.int64)).to(self.fitter.dev)
        a = 0
        for fx, _fy, dx, dy in groups:
            n = len(fx)
            cdx, cdy = self._core(dx, dy)
            xs = feet[0, a:a + n, None] + cdx[None, :]
            ys = feet[1, a:a + n, None] + cdy[None, :]
            inside = (xs >= 0) & (xs < SW) & (ys >= 0) & (ys < PLAY_H)
            idx = ys.clamp(0, PLAY_H - 1) * SW + xs.clamp(0, SW - 1)
            parts.append(t.stack([(shows[idx] & inside).sum(1), inside.sum(1), (valid[idx] & inside).sum(1)]))
            sizes.append(n)
            a += n
        self.asked = a
        allc = t.cat(parts, dim=1).cpu().numpy()            # the one transfer back
        out, a = [], 0
        for n in sizes:
            out.append((allc[0, a:a + n], allc[1, a:a + n], allc[2, a:a + n]))
            a += n
        self.last = (self._key, groups, out)            # this frame's questions and answers (a tool's check)
        return out

    last = None
