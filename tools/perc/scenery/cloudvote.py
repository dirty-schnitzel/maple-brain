"""The vote's palette ids under a cloud (prototype)."""
import torch


class CloudVote:
    """The vote's palette ids under a cloud: an undone pixel is off its sprite colour by up to ~0.5 / (1 - A)
    levels (the frame's rounding, amplified), so there the id comes from the Voter's TOLERANT tables (the fade
    search's, FADE_TOLS = +-2 / 3 / 4 / 6 levels) at the level the pixel's cloud alpha asks for - exact elsewhere."""

    def __init__(self, voter):
        self.v, self.orig = voter, voter.ids
        self.A = None

    def ids(self, frame, exp=None, known=None, tol=4.0, resid=False):
        out = self.orig(frame, exp, known, tol, resid)
        if self.A is None or exp is None:
            return out
        ids = out[0] if resid else out
        v = self.v
        A = self.A
        need = 1.0 + 0.5 / (1 - A).clamp(min=0.05)
        tols = torch.tensor(v.FADE_TOLS, dtype=need.dtype, device=need.device)
        li = (need[..., None] > tols).sum(dim=-1).clamp_(max=len(v.FADE_TOLS) - 1)
        key = v._key(frame[:700].float()) + li * 258 ** 3 + (1 + 258 + 258 * 258)
        unexpl = (frame[:700].float() - exp).abs().amax(dim=2) > tol
        if known is not None:
            unexpl |= ~known
        m = (A > 0.004) & (ids == 0) & unexpl
        ids = torch.where(m, v.lut_tol[key], ids)
        return (ids, out[1], out[2]) if resid else ids
