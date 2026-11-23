"""maplebrain/perception/clouds.py (PLAN-moving-scenery.md step 4): the weather clouds found, followed and undone on
made-up frames - one of the client's cloud pictures blended over a known picture at its opacity, drifting at a
constant speed. Needs the cloud pictures (`python -m maplebrain assets scene`, assets/scene/clouds): skipped
without."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from maplebrain.config import Perception  # noqa: E402
from maplebrain.scene import PLAY_H, ROOT, W  # noqa: E402

if not (ROOT / "clouds" / "clouds.json").exists():
    pytest.skip("needs python -m maplebrain assets scene (assets/scene/clouds)", allow_module_level=True)
from maplebrain.perception.clouds import Clouds  # noqa: E402


def _scene(seed=0):
    """A known picture (no near-white: the thickness can be read everywhere) and the valid mask."""
    rng = np.random.default_rng(seed)
    base = rng.integers(20, 170, (PLAY_H // 10 + 1, W // 10 + 1, 3)).astype(np.float32)
    E = np.kron(base, np.ones((10, 10, 1), np.float32))[:PLAY_H, :W]
    return torch.from_numpy(E), torch.ones((PLAY_H, W), dtype=torch.bool)


def _frame(cl, E, clouds):
    """E with clouds [(k, x, y, o)] blended in (frame = E + o a (s - E)), as uint8."""
    f = E.clone()
    for k, x, y, o in clouds:
        s, a = cl.sprites[k]
        h, w = a.shape
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(PLAY_H, y + h)
        aa = (o * a[y0 - y:y1 - y, x0 - x:x1 - x])[..., None]
        f[y0:y1, x0:x1] = f[y0:y1, x0:x1] + aa * (s[y0 - y:y1 - y, x0 - x:x1 - x] - f[y0:y1, x0:x1])
    return f.round().clamp(0, 255).to(torch.uint8)


def test_a_cloud_is_found_followed_at_its_speed_and_undone():
    cl = Clouds("cpu", Perception())
    E, valid = _scene()
    C = (100, 50)                                       # the camera: map = screen + C
    v, o, k = 30.0, 0.72, 3
    seen = []
    for n in range(40):
        t = n / 60
        x = int(round(400 + v * t))                     # whole pixels on the screen (the camera stands still)
        f = _frame(cl, E, [(k, x, 200, o)])
        on = cl.update(f, E, valid, C, t)
        if n == 0:
            assert len(on) == 1 and on[0]["k"] == k and abs(on[0]["o"] - o) < 0.02   # found on the first frame
        tr = on[0]
        seen.append((tr["mx"] - C[0], tr["my"] - C[1], x))
        assert len(cl.tracks) == 1                      # one cloud, followed - not found again and again
    assert all(abs(mx - x) <= 1 and my == 200 for mx, my, x in seen[5:])
    assert abs(cl.tracks[0]["vx"] - v) < 2
    und, thick = cl.undo(f)
    sub = (cl.A[..., 0] > 0.05) & ~thick
    assert float((und.float() - E).abs().amax(dim=2)[sub].max()) <= 3        # the cloud taken out again
    assert float(((f.float() - cl.E2).abs().amax(dim=2) > 4).float().mean()) < 0.001   # the layer explains it


def test_no_cloud_no_track_and_the_finder_waits():
    """A frame the scene explains: nothing whitened -> the finder does not run, no cloud is made up."""
    cl = Clouds("cpu", Perception())
    E, valid = _scene(1)
    f = E.round().to(torch.uint8)
    for n in range(20):
        assert cl.update(f, E, valid, (0, 0), n / 60) == []
    assert cl.finds == 0 and cl.tracks == []
