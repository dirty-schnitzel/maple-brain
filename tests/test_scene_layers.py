"""The fit's planes (PLAN-perception.md step 3.2, `assets scene` -> layers/behind_L.png + front_L.png): per foothold
layer L, the tiles / objects of layers <= L over the backs (B, what a mob on L is drawn over) and those of layers > L
+ the front backs (F, A: what is drawn over it); F over B = expected() - the pre-composed picture - on the real clean
maps at cameras over their whole area. The bot loads only the front alphas since 3.3 (Scene.split dropped): the
planes are read from disk here. Needs the scene builds with layers (`python -m maplebrain assets scene MAP`, not in
git): skipped without."""
import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from maplebrain import scene as sc  # noqa: E402

MAPS = (10005063, 10005065, 10003061, 10003062)     # Ant Tunnel IV (1 layer), Dangerous Steam (2), Line 1 (4), Transfer (5)


def split(s, d, C, L, w=sc.W, h=sc.PLAY_H):
    """The scene split at layer L for camera C from the build's planes on disk -> (B, known_B, F, A), as
    Scene.split did until 3.3."""
    behind, front = (torch.from_numpy(cv2.imread(str(d / "layers" / f"{k}_{L}.png"), cv2.IMREAD_UNCHANGED)).to(s.dev)
                     for k in ("behind", "front"))
    unk = torch.zeros((h, w), dtype=torch.bool, device=s.dev)
    acc, unk = s._backs(C, w, h, 0, torch.zeros((h, w, 4), device=s.dev), unk)
    B, cov = acc[..., :3], acc[..., 3]
    bc = s._crop(C, w, h, behind).float()
    a = bc[..., 3] / 255.0
    B = B * (1 - a[..., None]) + bc[..., :3]
    cov = cov * (1 - a) + a
    unk = unk & (a < 0.98)
    fc = s._crop(C, w, h, front).float()
    fc[..., 3] /= 255.0
    facc, unk_f = s._backs(C, w, h, 1, fc, torch.zeros_like(unk))
    F, A = facc[..., :3], facc[..., 3]
    known = (cov > 0.98) & ~unk & ~unk_f
    an = s._anim(C, w, h)
    if an is not None:
        known &= ~an
    return B, known, F, A


@pytest.mark.parametrize("map_id", MAPS)
def test_front_over_behind_is_the_expected_scene(map_id):
    if not sc.Scene.have(map_id):
        pytest.skip(f"needs python -m maplebrain assets scene {map_id}")
    s = sc.Scene.load(map_id)
    if not s.layers:
        pytest.skip("scene built before 3.2 (no layers/)")
    assert sorted(s.layers) == s.meta["layers"]
    d = sc.ROOT / str(map_id)
    for L in s.layers:                                  # what the bot loads = the front plane's alpha on disk
        assert np.array_equal(s.layers[L].cpu().numpy(),
                              cv2.imread(str(d / "layers" / f"front_{L}.png"), cv2.IMREAD_UNCHANGED)[..., 3])
    rng = np.random.default_rng(map_id)
    m = s.meta
    for _ in range(4):
        C = (int(rng.integers(m["x0"] + 100, m["x0"] + m["w"] - sc.W - 100)),
             int(rng.integers(m["y0"] + 100, max(m["y0"] + 101, m["y0"] + m["h"] - sc.H - 100))))
        exp, known = s.expected(C)
        for L in s.layers:
            B, kB, F, A = split(s, d, C, L)
            comp = F + (1 - A[..., None]) * B
            show = kB | (A >= 0.98)                     # where the frame is predicted: B known or F opaque
            assert bool((known & ~show).sum() == 0), (C, L)
            dd = (comp - exp).abs().amax(dim=2)[known]
            # 2 rounded uint8 canvases instead of 1: colour 0.5 + alpha 0.5 + behind 0.5 at a see-through front pixel
            assert float(dd.max()) <= 1.5, (C, L, float(dd.max()))
            assert float(dd.mean()) < 0.1, (C, L, float(dd.mean()))
