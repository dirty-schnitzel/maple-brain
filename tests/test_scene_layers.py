"""The fit's planes (PLAN-perception.md step 3.2, scene.Scene.split): per foothold layer L, the tiles / objects of
layers <= L over the backs (B, what a mob on L is drawn over) and those of layers > L + the front backs (F, A: what is
drawn over it); F over B = expected() - the pre-composed picture - on the real clean maps at cameras over their whole
area. Needs the scene builds with layers (`python -m maplebrain assets scene MAP`, not in git): skipped without."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from maplebrain import scene as sc  # noqa: E402

MAPS = (10005063, 10005065, 10003061, 10003062)     # Ant Tunnel IV (1 layer), Dangerous Steam (2), Line 1 (4), Transfer (5)


@pytest.mark.parametrize("map_id", MAPS)
def test_front_over_behind_is_the_expected_scene(map_id):
    if not sc.Scene.have(map_id):
        pytest.skip(f"needs python -m maplebrain assets scene {map_id}")
    s = sc.Scene.load(map_id)
    if not s.layers:
        pytest.skip("scene built before 3.2 (no layers/)")
    assert sorted(s.layers) == s.meta["layers"]
    rng = np.random.default_rng(map_id)
    m = s.meta
    for _ in range(4):
        C = (int(rng.integers(m["x0"] + 100, m["x0"] + m["w"] - sc.W - 100)),
             int(rng.integers(m["y0"] + 100, max(m["y0"] + 101, m["y0"] + m["h"] - sc.H - 100))))
        exp, known = s.expected(C)
        for L in s.layers:
            B, kB, F, A = s.split(C, L)
            comp = F + (1 - A[..., None]) * B
            show = kB | (A >= 0.98)                     # where the frame is predicted: B known or F opaque
            assert bool((known & ~show).sum() == 0), (C, L)
            d = (comp - exp).abs().amax(dim=2)[known]
            # 2 rounded uint8 canvases instead of 1: colour 0.5 + alpha 0.5 + behind 0.5 at a see-through front pixel
            assert float(d.max()) <= 1.5, (C, L, float(d.max()))
            assert float(d.mean()) < 0.1, (C, L, float(d.mean()))
