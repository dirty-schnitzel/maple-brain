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
`columns(cx, top, reach, half)` (the players' tracker, track/players.py: what stands on a name tag) -> per tag the
`reach` rows over its top (row i = top - reach + i), each counted over the 2 half + 1 columns around cx: pixels that
are world and do NOT show the scene (something is drawn there), world, inside the play area.
`ask_columns(...)` -> an Answer whose `get()` is `columns`' result: the bitmaps answer at once; on the GPU the gather
is queued and its result RIDES in the next `count` transfer of this frame (the mob tracker's) - one round trip a frame
(PLAN-tracker step 4b try 2, the user's answer 6); `get()` before any `count` makes the transfer itself.
"""
import numpy as np

PLAY_H, SW = 700, 1366


class Evidence:
    """The interface. `ready`: there is a frame to ask about."""
    ready = False

    def count(self, groups: list) -> list:
        """[(fx (n,), fy (n,), dx (k,), dy (k,))] -> [(shows (n,), inside (n,), world (n,))] int64 counts."""
        raise NotImplementedError

    def columns(self, cx, top, reach: int, half: int):
        """cx, top (n,) screen px -> (over, world, inside): (n, reach) int64 counts (the module's docstring)."""
        raise NotImplementedError

    def ask_columns(self, cx, top, reach: int, half: int) -> "Answer":
        return Answer(self.columns(cx, top, reach, half))


class Answer:
    """A question's answer: `get()`. `owner` (a Gpu) delivers it on its next transfer."""
    __slots__ = ("value", "owner")

    def __init__(self, value=None, owner=None):
        self.value, self.owner = value, owner

    def get(self):
        if self.value is None:
            self.owner.flush()
        return self.value


def _grid(cx, top, reach, half):
    """The pixels of `columns`: xs, ys (n, reach, 2 half + 1) and which are inside the play area."""
    cx, top = np.asarray(cx, np.int64), np.asarray(top, np.int64)
    xs = cx[:, None, None] + np.arange(-half, half + 1)[None, None, :]
    ys = top[:, None, None] + np.arange(-reach, 0)[None, :, None]
    xs, ys = np.broadcast_to(xs, (len(cx), reach, 2 * half + 1)), np.broadcast_to(ys, (len(cx), reach, 2 * half + 1))
    inside = (xs >= 0) & (xs < SW) & (ys >= 0) & (ys < PLAY_H)
    return xs, ys, inside


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

    def columns(self, cx, top, reach: int, half: int):
        """Per tag one slice of the two bitmaps (the rows and columns inside the play area)."""
        n = len(cx)
        over, world, inside = (np.zeros((n, reach), np.int64) for _ in range(3))
        for k in range(n):
            c, t = int(cx[k]), int(top[k])
            x0, x1 = max(0, c - half), min(SW, c + half + 1)
            r0, r1 = max(0, t - reach), min(PLAY_H, t)
            if x1 <= x0 or r1 <= r0:
                continue
            a, b = r0 - (t - reach), r1 - (t - reach)
            wo = self.world[r0:r1, x0:x1]
            world[k, a:b] = wo.sum(1)
            over[k, a:b] = (wo & ~self.shows[r0:r1, x0:x1]).sum(1)
            inside[k, a:b] = x1 - x0
        return over, world, inside


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
        self._waiting = []                              # [(Answer, (2, m) bool tensor, (n, reach, w), inside)]
        self.trips = 0                                  # transfers back (a tool counts them per frame)

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
        allc = self._transfer(parts)                    # the one transfer back (+ any columns waiting)
        out, a = [], 0
        for n in sizes:
            out.append((allc[0, a:a + n], allc[1, a:a + n], allc[2, a:a + n]))
            a += n
        self.last = (self._key, groups, out)            # this frame's questions and answers (a tool's check)
        return out

    def _transfer(self, parts):
        """One transfer back of `parts` ((3, m) int64 tensors) + the columns waiting -> parts' numpy (3, sum m)."""
        t = self.torch
        w = self._waiting
        self._waiting = []
        flat = [x for x in parts] + [x.to(t.int64).reshape(2, -1) for _, x, _, _ in w]
        if not flat:
            return np.zeros((3, 0), np.int64)
        m = sum(x.shape[1] for x in parts)
        z = [x if x.shape[0] == 3 else t.cat([x, t.zeros_like(x[:1])]) for x in flat]
        allc = t.cat(z, dim=1).cpu().numpy()
        self.trips += 1
        a = m
        for ans, x, shape, inside in w:
            k = int(np.prod(shape))
            ov = allc[0, a:a + k].reshape(shape).astype(bool) & inside
            wo = allc[1, a:a + k].reshape(shape).astype(bool) & inside
            ans.value = (ov.sum(2), wo.sum(2), inside.sum(2))
            a += k
        return allc[:, :m]

    def flush(self):
        """Deliver the columns waiting (their own transfer: no `count` came this frame)."""
        if self._waiting:
            self._transfer([])

    last = None

    def columns(self, cx, top, reach: int, half: int):
        """`ask_columns` answered at once (its own transfer)."""
        return self.ask_columns(cx, top, reach, half).get()

    def ask_columns(self, cx, top, reach: int, half: int) -> Answer:
        """The same formula as `count`, at the asked pixels only (the whole frame's shows map only when this frame
        already has it: a few thousand pixels need no full-frame pass); queued for the next transfer."""
        t = self.torch
        xs, ys, inside = _grid(cx, top, reach, half)
        idx = np.clip(ys, 0, PLAY_H - 1) * SW + np.clip(xs, 0, SW - 1)
        dev = self.fitter.dev
        it = t.from_numpy(np.ascontiguousarray(idx.reshape(-1))).to(dev)
        last = self.fitter._last
        frame, _C, exp, valid = last
        v = valid.reshape(-1)[it]
        if self._key is last:
            sh = self._shows[it]
        else:
            sh = (frame.reshape(-1, 3)[it].float() - exp.reshape(-1, 3)[it]).abs().amax(dim=1) <= self.tol
            sh &= v
        ans = Answer(owner=self)
        self._waiting.append((ans, t.stack([v & ~sh, v]), idx.shape, inside))
        return ans
