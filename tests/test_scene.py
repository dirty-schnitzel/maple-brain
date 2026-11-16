"""maplebrain/scene.py: the scene model (PLAN-perception.md step 1) on a small made-up map - the background
arithmetic, the expected picture, the camera from registration, the build from client-style data."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from maplebrain import scene as sc  # noqa: E402


def _back(**kw):
    b = {"file": "x", "x": 0, "y": 0, "rx": -10, "ry": -10, "cx": 0, "cy": 0, "type": 3, "a": 255, "front": 0, "flip": 0,
         "origin": [40, 30], "size": [80, 60], "known": 1}
    b.update(kw)
    return b


def _world(seed=0, backs=None, front=False):
    """A 900x700 map: random tiles / objects over 60 % of it (premultiplied canvas), a tiled opaque background."""
    rng = np.random.default_rng(seed)
    canvas = np.zeros((700, 900, 4), np.uint8)
    for _ in range(40):
        x, y, w, h = int(rng.integers(0, 800)), int(rng.integers(0, 620)), int(rng.integers(40, 120)), int(rng.integers(30, 80))
        canvas[y:y + h, x:x + w, :3] = rng.integers(0, 255, (min(h, 700 - y), min(w, 900 - x), 3), dtype=np.uint8)
        canvas[y:y + h, x:x + w, 3] = 255
    pic = np.zeros((60, 80, 4), np.uint8)
    pic[..., :3] = rng.integers(0, 16, (60, 80, 3), dtype=np.uint8) * 17
    pic[..., 3] = 255
    meta = {"x0": -100, "y0": -50, "w": 900, "h": 700, "backs": backs if backs is not None else [_back(front=int(front))]}
    return sc.Scene(meta, canvas, [pic] * len(meta["backs"]), device="cpu"), canvas, pic


def test_background_position_is_the_clients_integer_arithmetic():
    """Measured on 7 maps (exp_backfit.py): origin at b + off + trunc(r * (C + off) / 100), off 683 / 468, division
    TOWARD ZERO (not floor: they differ for negative products). The cases are measured ones (frame, layer)."""
    b = _back(x=-3, y=-21, rx=-15, ry=-15, origin=[400, 300], size=[800, 600])
    assert sc.back_pos(b, (1119, 824)) == (-3 + 683 + int(-15 * (1119 + 683) / 100) - 400,
                                           -21 + 468 + int(-15 * (824 + 468) / 100) - 300)
    assert sc.back_pos(_back(rx=-5, ry=-5, origin=[0, 0]), (-900, -540)) == (683 + 10, 468 + 3)   # -5 * -217 / 100 = 10.85
    assert sc.back_pos(_back(rx=-5, ry=-5, origin=[0, 0]), (-642, -428)) == (683 - 2, 468 - 2)    # trunc(-2.05) = -2
    assert sc.back_pos(_back(rx=-50, ry=-100, origin=[0, 0]), (-578, -518)) == (683 - 52, 518)    # Line 1: -52.5 -> -52
    assert sc.back_pos(_back(rx=-30, ry=-100, origin=[0, 0]), (93, -348)) == (683 - 232, 348)     # Line 1: -232.8
    assert sc.back_pos(_back(flip=1, rx=0, ry=0, origin=[10, 0]), (0, 0))[0] == 683 - 70          # mirrored origin


def test_expected_is_the_tiles_over_the_tiled_background_and_everything_is_known():
    s, canvas, pic = _world()
    C = (37, 61)
    exp, known = s.expected(C, w=400, h=300)
    exp, known = exp.numpy(), known.numpy()
    assert known.all()
    px, py = sc.back_pos(s.meta["backs"][0], C)
    for (x, y) in ((0, 0), (399, 299), (123, 45), (250, 170)):
        c = canvas[y + C[1] + 50, x + C[0] + 100]
        want = c[:3] if c[3] == 255 else pic[(y - py) % 60, (x - px) % 80, :3]
        assert (exp[y, x] == want).all()


def test_a_moving_background_is_unknown_where_no_tile_hides_it_and_a_front_one_is_drawn_last():
    s, canvas, _ = _world(backs=[_back(type=4, known=0)])
    exp, known = s.expected((0, 0), w=400, h=300)
    opaque = canvas[50:350, 100:500, 3] == 255
    assert (known.numpy() == opaque).all()                       # clouds: unknown, except behind tiles
    s, canvas, pic = _world(front=True)
    exp, _ = s.expected((0, 0), w=400, h=300)
    px, py = sc.back_pos(s.meta["backs"][0], (0, 0))
    assert (exp.numpy()[10, 10] == pic[(10 - py) % 60, (10 - px) % 80, :3]).all()     # over the tiles too


def _frame(s, C, w=640, h=420, clutter=0.25, seed=1):
    exp, _ = s.expected(C, w=w, h=h)
    f = exp.numpy().round().astype(np.uint8)
    rng = np.random.default_rng(seed)
    for _ in range(int(clutter * 40)):                           # mobs, players, effects: rectangles of noise
        x, y = int(rng.integers(0, w - 40)), int(rng.integers(0, h - 40))
        f[y:y + 40, x:x + 40] = rng.integers(0, 255, (40, 40, 3), dtype=np.uint8)
    return f


def test_register_finds_the_camera_to_the_pixel_under_clutter():
    s, _, _ = _world()
    for C, guess in (((37, 61), (30, 66)), ((120, 200), (131, 190)), ((0, 0), (-12, 12))):
        got, share, n = s.register(_frame(s, C), guess, radius=12, h=420)
        assert got == C and share > 0.6 and n > 200
    got, share, _ = s.locate(_frame(s, (150, 150)), (115, 180), h=420)       # 35 px off: the wide look
    assert got == (150, 150)
    assert s.locate(_frame(s, (150, 150)), (20, 20), h=420) is None          # lost: no camera, not a wrong one
    assert s.locate(_frame(s, (150, 150)), (20, 20), seed=(170, 120), h=420)[0] == (150, 150)   # the minimap's rough one


def test_locate_is_not_fooled_by_scenery_that_repeats():
    """Transfer Area 2026-11-16: brick walls. A camera one brick over matches part of the landmarks; when the last
    camera is > 12 px old the near look finds only that one - it must not be final."""
    rng = np.random.default_rng(7)
    canvas = np.zeros((700, 900, 4), np.uint8)
    brick = rng.integers(0, 255, (40, 40, 3), dtype=np.uint8)
    canvas[100:400, :, :3] = np.tile(brick, (8, 23, 1))[:300, :900]           # a wall: repeats every 40 px
    canvas[100:400, :, 3] = 255
    for _ in range(25):                                                       # + things that don't repeat
        x, y, w, h = int(rng.integers(0, 800)), int(rng.integers(400, 640)), int(rng.integers(40, 100)), int(rng.integers(30, 60))
        canvas[y:y + h, x:x + w, :3] = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
        canvas[y:y + h, x:x + w, 3] = 255
    pic = np.zeros((60, 80, 4), np.uint8)
    pic[..., :3], pic[..., 3] = rng.integers(0, 16, (60, 80, 3), dtype=np.uint8) * 17, 255
    s = sc.Scene({"x0": -100, "y0": -50, "w": 900, "h": 700, "backs": [_back()]}, canvas, [pic], device="cpu")
    C = (150, 100)
    f = _frame(s, C, clutter=0)
    old = (C[0] + 32, C[1])                                                   # the last camera, 32 px old
    alias = s.register(f, old, radius=12, h=420)
    assert alias[0] == (C[0] + 40, C[1]) and 0.2 < alias[1] < 0.8             # one brick over: a partial match
    assert s.locate(f, old, h=420, last_share=0.95)[0] == C                   # not final: the wide look, the best wins
    assert s.locate(f, old, h=420)[0] == C                                    # no last share: every look, the best
    assert s.locate(f, (C[0] + 3, C[1] - 2), h=420, last_share=0.95)[0] == C


def test_register_says_how_little_matches_on_another_picture():
    s, _, _ = _world()
    other, _, _ = _world(seed=5)
    r = s.register(_frame(other, (37, 61)), (37, 61), h=420)
    assert r is None or r[1] < 0.2


def test_build_composites_layers_in_draw_order_flags_animated_objects_and_lists_backs():
    red = np.zeros((20, 30, 4), np.uint8)
    red[..., 2], red[..., 3] = 200, 255
    half = np.zeros((20, 30, 4), np.uint8)
    half[..., 0], half[..., 3] = 100, 128
    pics = {("Obj", "o", ("a", "b", "c", 0)): red, ("Obj", "o", ("a", "b", "anim", 0)): red,
            ("Obj", "o", ("a", "b", "anim", 1)): red, ("Tile", "t", ("bsc", 0)): half, ("Back", "sky", ("back", 0)): red}
    nodes = {("Obj", "o", ("a", "b", "c")): {"0": {"_size": [30, 20], "origin": [0, 0]}},
             ("Obj", "o", ("a", "b", "anim")): {"0": {"_size": [30, 20], "origin": [0, 0]}, "1": {"_size": [30, 20], "origin": [0, 0]}},
             ("Tile", "t", ("bsc", 0)): {"_size": [30, 20], "origin": [15, 10], "z": 0},
             ("Back", "sky", ("back", 0)): {"_size": [30, 20], "origin": [15, 10]}}

    class Parts(sc._Parts):
        def __init__(self):
            pass

        def node(self, kind, name, path):
            return nodes.get((kind, name, tuple(path)))

        def pic(self, kind, name, path):
            return pics.get((kind, name, tuple(path))), None

    img = {"0": {"info": {"tS": "t"},
                 "obj": {"0": {"oS": "o", "l0": "a", "l1": "b", "l2": "c", "x": 10, "y": 10, "z": 0},
                         "1": {"oS": "o", "l0": "a", "l1": "b", "l2": "anim", "x": 300, "y": 10, "z": 0}},
                 "tile": {"0": {"u": "bsc", "no": 0, "x": 45, "y": 30}}},
           "back": {"0": {"bS": "sky", "no": 0, "x": 5, "y": 6, "rx": -10, "ry": -20, "type": 3, "a": 255},
                    "1": {"bS": "sky", "no": 0, "type": 4, "front": 1}}}
    m = {"footholds": {"1": {"x1": 0, "y1": 100, "x2": 400, "y2": 100}}, "vrBounds": {"left": 0, "top": 0, "right": 400, "bottom": 200}}
    canvas, anim, meta = sc.build_scene(img, m, Parts())
    x0, y0 = meta["x0"], meta["y0"]
    assert (x0, y0) == (-sc.PAD, -sc.PAD) and meta["objects"] == 2 and meta["tiles"] == 1 and meta["animated"] == 1
    assert tuple(canvas[12 - y0, 11 - x0]) == (0, 0, 200, 255)                    # the object alone
    assert tuple(canvas[25 - y0, 35 - x0]) == (50, 0, 100, 255)                   # the half-clear tile over it
    assert tuple(canvas[35 - y0, 50 - x0]) == (50, 0, 0, 128)                     # the tile alone: premultiplied
    assert anim[15 - y0, 310 - x0] == 255 and anim[15 - y0, 20 - x0] == 0
    assert [(b["rx"], b["ry"], b["known"], b["front"]) for b in meta["backs"]] == [(-10, -20, 1, 0), (0, 0, 0, 1)]


def test_pre_composed_parallax_groups_draw_what_the_layers_draw_one_by_one():
    """Layers of one parallax (same rx / ry) are drawn once at load into one plane (PLAN-perception.md step 2):
    the expected picture must not change - tiled and untiled layers, half-transparent ones, a flipped one, a
    group in front, an unknown layer between two groups, cameras inside and outside the rendered area."""
    rng = np.random.default_rng(3)
    backs = [_back(rx=-30, ry=-100, type=2, cy=90, origin=[10, 20]),
             _back(rx=-30, ry=-100, type=0, x=120, y=-40, a=160),
             _back(rx=-30, ry=-100, type=1, cx=150, x=-60, flip=1),
             _back(rx=-50, ry=-50, type=4, known=0),
             _back(rx=-80, ry=-100, type=3, cx=0, cy=0),
             _back(rx=-80, ry=-100, type=0, x=300, y=80, a=90),
             _back(rx=-20, ry=-20, type=0, x=40, y=10, front=1, a=200),
             _back(rx=-20, ry=-20, type=1, x=-30, y=300, front=1, cx=200)]
    s, _, _ = _world(5, backs)
    for i in range(len(backs)):                                       # every layer its own picture, some see-through
        pic = np.zeros((60, 80, 4), np.uint8)
        pic[..., :3] = rng.integers(0, 255, (60, 80, 3))
        pic[..., 3] = np.where(rng.random((60, 80)) < 0.3, 0, rng.integers(60, 256, (60, 80)))
        t = torch.from_numpy(pic).float()
        t[..., 3] *= backs[i]["a"] / 255.0
        t[..., :3] *= t[..., 3:4] / 255.0
        s.backs[i] = (backs[i], t)
    s.groups = {f: s._compose(f) for f in (0, 1)}
    assert [it[0] for it in s.groups[0]] == ["group", "one", "group"] and [it[0] for it in s.groups[1]] == ["group"]
    for C in [(-100, -50), (-90, -40), (200, 150), (-466, -68), (400, -50), (-2000, 3000), (5000, -900)]:
        e0, k0 = s.expected(C, pre=False)
        e1, k1 = s.expected(C)
        assert (e0 - e1).abs().max() < 0.5 and (k0 != k1).float().mean() < 1e-4, C


def test_pre_composed_backgrounds_on_line1_are_the_same_and_fast():
    """Line 1 <Area 1> (29 layers, rx -30 / -50 / -80 / -100): the real scene, pre-composed vs layer by layer."""
    import time
    if not sc.Scene.have(10003061):
        pytest.skip("needs python -m maplebrain assets scene 10003061")
    s = sc.Scene.load(10003061)
    assert sum(it[0] == "group" for it in s.groups[0]) >= 3
    sync = torch.cuda.synchronize if s.dev == "cuda" else (lambda: None)
    t_one, t_pre = [], []
    for C in [(-585 + 170 * i, -817 + 40 * i) for i in range(16)]:
        sync(); t0 = time.perf_counter()
        e0, k0 = s.expected(C, pre=False)
        sync(); t1 = time.perf_counter()
        e1, k1 = s.expected(C)
        sync(); t2 = time.perf_counter()
        t_one.append(t1 - t0); t_pre.append(t2 - t1)
        assert (e0 - e1).abs().max() < 0.5 and (k0 != k1).float().mean() < 1e-4, C
    if s.dev == "cuda":
        assert np.median(t_pre) < 0.5 * np.median(t_one), (np.median(t_pre), np.median(t_one))


def test_scene_camera_follows_a_scrolling_camera_says_when_lost_and_recovers_from_the_seed():
    """SceneCamera (the bot's camera from step 2 on): a camera scrolling 20 px a frame is followed by the near look
    (the last step predicts it); a frame of another map is 'not found' and the camera is kept, not guessed; the
    minimap's rough camera brings it back."""
    s, _, _ = _world()
    other, _, _ = _world(seed=5)
    cam = sc.SceneCamera(s, h=420)
    assert cam.update(_frame(s, (20, 40)), seed=(30, 30)) == (20, 40)
    for i in range(1, 8):
        C = (20 + 20 * i, 40 + 7 * i)
        assert cam.update(_frame(s, C, seed=i)) == C and cam.found and cam.share > 0.6
    assert cam.update(_frame(other, (60, 60))) is None and not cam.found and cam.C == (160, 89)
    assert cam.update(_frame(s, (230, 150)), seed=(240, 140)) == (230, 150) and cam.found
