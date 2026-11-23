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


def test_build_keeps_a_pictures_blend_and_the_maps_cloud_flag():
    """PLAN-moving-scenery.md step 1: a background picture's `blend` (1 = ADDED to what is under it: Ellinia's light
    rays) and the map's info `cloud` (the client draws its weather clouds over the field) go into scene.json."""
    red = np.zeros((20, 30, 4), np.uint8)
    red[..., 2], red[..., 3] = 200, 255
    nodes = {("Back", "sky", ("back", 0)): {"_size": [30, 20], "origin": [15, 10]},
             ("Back", "sky", ("back", 1)): {"_size": [30, 20], "origin": [15, 10], "blend": 1, "a0": 235}}

    class Parts(sc._Parts):
        def __init__(self):
            pass

        def node(self, kind, name, path):
            return nodes.get((kind, name, tuple(path)))

        def pic(self, kind, name, path):
            return red, None

    m = {"footholds": {"1": {"x1": 0, "y1": 100, "x2": 400, "y2": 100}}}
    back = {"0": {"bS": "sky", "no": 0, "type": 3}, "1": {"bS": "sky", "no": 1, "type": 0}}
    _, _, meta = sc.build_scene({"back": back, "info": {"cloud": 1}}, m, Parts())
    assert [b["blend"] for b in meta["backs"]] == [0, 1] and meta["cloud"] == 1
    assert all(b["known"] for b in meta["backs"])                                # an ADDED layer is known
    _, _, meta = sc.build_scene({"back": back}, m, Parts())
    assert meta["cloud"] == 0


def test_an_added_layer_adds_its_colour_times_alpha_and_covers_nothing():
    """Ellinia's light rays (blend 1, measured: the frame = min(255, under + colour x alpha) on 86-95 % of their
    free pixels within 1 level): the picture under it shows through brightened, an ADDED layer alone over nothing
    leaves the pixel unknown, and it is never pre-composed with the layers laid over (same parallax or not)."""
    sky = np.zeros((60, 80, 4), np.uint8)
    sky[..., :3], sky[..., 3] = (220, 100, 30), 255
    ray = np.zeros((60, 80, 4), np.uint8)
    ray[..., :3], ray[..., 3] = (100, 100, 100), 128                             # + 50 a level, 255 at most
    ray[:, 40:, 3] = 0
    backs = [_back(rx=-10, ry=-10, type=3), _back(rx=-10, ry=-10, type=3, blend=1), _back(rx=-10, ry=-10, type=3)]
    s = sc.Scene({"x0": -100, "y0": -50, "w": 900, "h": 700, "backs": backs[:2]}, np.zeros((700, 900, 4), np.uint8),
                 [sky, ray], device="cpu")
    assert [it[0] for it in s.groups[0]] == ["one", "one"]                       # not grouped with the sky
    C = (0, 0)
    exp, known = s.expected(C, w=400, h=300)
    px, _ = sc.back_pos(backs[0], C)
    cols = (np.arange(400) - px) % 80
    e = exp.numpy()
    assert known.all()
    lit, dark = np.flatnonzero(cols < 40)[0], np.flatnonzero(cols >= 40)[0]
    assert np.allclose(e[10, lit], (255, 150.2, 80.2), atol=0.5)                 # 220 + 100 x 128 / 255 -> 255 at most
    assert np.allclose(e[10, dark], (220, 100, 30), atol=0.5)
    e0, _ = s.expected(C, w=400, h=300, pre=False)
    assert (e0 - exp).abs().max() < 0.5
    alone = sc.Scene({"x0": -100, "y0": -50, "w": 900, "h": 700, "backs": [backs[1]]}, np.zeros((700, 900, 4), np.uint8),
                     [ray], device="cpu")
    assert not alone.expected(C, w=400, h=300)[1].any()                          # nothing under it: not covered
    three = sc.Scene({"x0": -100, "y0": -50, "w": 900, "h": 700, "backs": backs}, np.zeros((700, 900, 4), np.uint8),
                     [sky, ray, sky], device="cpu")
    assert [it[0] for it in three.groups[0]] == ["one", "one", "one"]


def test_the_two_flat_pictures_have_their_real_colours():
    """Pixel format 1537 (RGB565, one pixel per 16x16 block): export.ps1 shifted a byte left by 8 (= 0) until
    2026-11-21 and wrote the Henesys-side forests' sky as (0, 28, 255). The file holds 0x44FF = RGB (66, 158, 255),
    exactly the frame's sky; Perion's sky 0x543D = (82, 134, 239)."""
    import cv2
    for f, bgr in (("back_midForest/back_0.png", (255, 158, 66)), ("back_dryRock/back_0.png", (239, 134, 82))):
        p = sc.ROOT / "backs" / f
        if not p.exists():
            pytest.skip(f"needs python -m maplebrain assets scene ({p})")
        im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        assert (im[..., :3] == bgr).all() and (im[..., 3] == 255).all(), f


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


# ------------------------------------------------------------------ movers (PLAN-moving-scenery.md step 2)
def test_build_gives_a_type_4_back_its_mover_law():
    """scene.json: a type 4 back (sideways-moving) carries `mover` with its speed, 5 x rx px a second (measured,
    4.994-5.012 x rx); other backs none. It stays unknown: no map with one hunts in step 2."""
    red = np.zeros((20, 30, 4), np.uint8)
    red[..., 2], red[..., 3] = 200, 255
    nodes = {("Back", "sky", ("back", 0)): {"_size": [30, 20], "origin": [15, 10]}}

    class Parts(sc._Parts):
        def __init__(self):
            pass

        def node(self, kind, name, path):
            return nodes.get((kind, name, tuple(path)))

        def pic(self, kind, name, path):
            return red, None

    m = {"footholds": {"1": {"x1": 0, "y1": 100, "x2": 400, "y2": 100}}}
    back = {"0": {"bS": "sky", "no": 0, "type": 3, "rx": -20}, "1": {"bS": "sky", "no": 0, "type": 4, "rx": -14},
            "2": {"bS": "sky", "no": 0, "type": 6, "rx": -150}}
    _, _, meta = sc.build_scene({"back": back}, m, Parts())
    assert [b.get("mover") for b in meta["backs"]] == [None, {"v": -70.0}, None]
    assert [b["known"] for b in meta["backs"]] == [1, 0, 0] and not sc.Scene.clean_meta(meta)


def test_a_map_with_movers_behind_the_field_or_clouds_is_clean_but_not_other_kinds_or_a_front_mover():
    """Step 3: a type 4 mover counts as known (MoverFollow finds it); step 5: Perion's weather clouds count (followed
    and undone); type 5-7 / animated backs (step 6) and a mover drawn in front of the mobs (map 80003000) keep a map
    refused."""
    mover = _back(type=4, known=0, mover={"v": -25.0})
    meta = lambda backs, **kw: {"backs": backs, **kw}
    assert sc.Scene.clean_meta(meta([_back(), mover]))
    assert sc.Scene.clean_meta(meta([_back(), mover], cloud=1))
    assert not sc.Scene.clean_meta(meta([_back(), _back(type=6, known=0)]))
    assert not sc.Scene.clean_meta(meta([_back(), _back(type=4, known=0)]))                  # an older build
    assert not sc.Scene.clean_meta(meta([_back(), dict(mover, front=1)]))
    assert sc.Scene.clean_meta(meta([_back()])) and sc.Scene.clean_meta(meta([_back()], cloud=0))


def test_a_movers_row_floors_its_parallax_term_and_its_column_is_its_place_minus_the_camera():
    """Measured on 4 maps (~9,000 layer-frames): sign(u) x floor(ry x |u| / 100), u = Cy + 468 - the static layers
    truncate toward zero instead. x = X - Cx (X = the picture's left edge on the map)."""
    b = _back(y=-100, ry=-15, origin=[0, 20])
    for Cy in (-468, -400, -200, 0, 37, 532, -1000):
        u = Cy + 468
        want = -100 + 468 + (1 if u >= 0 else -1) * int(np.floor(-15 * abs(u) / 100)) - 20
        assert sc.mover_pos(b, (0, Cy), 0)[1] == want
    assert sc.mover_pos(b, (0, -200), 0)[1] == -100 + 468 - 41 - 20             # -15 x 268 / 100 = -40.2 -> -41
    assert sc.back_pos(_back(y=-100, ry=-15, origin=[0, 20]), (0, -200))[1] == -100 + 468 - 40 - 20   # static: -40
    assert sc.mover_pos(_back(ry=4, origin=[0, 0]), (0, -1000), 0)[1] == 468 - 21   # u < 0: -floor(21.28)
    assert sc.mover_pos(b, (350, 0), 1234.4)[0] == 1234 - 350 and sc.mover_pos(b, (350, 0), 1234.6)[0] == 885


def _mover_world(seed=11, X=None):
    """A scene with a tiled opaque sky, a mover (type 4, period 300 px, its own texture, rows 100..219 at C = 0)
    and tiles over part of it; the mover's picture is opaque in its left 240 px."""
    rng = np.random.default_rng(seed)
    canvas = np.zeros((700, 900, 4), np.uint8)
    canvas[300:420, 100:400, :3] = rng.integers(0, 255, (120, 300, 3), dtype=np.uint8)
    canvas[300:420, 100:400, 3] = 255
    sky = np.zeros((60, 80, 4), np.uint8)
    sky[..., :3], sky[..., 3] = rng.integers(0, 16, (60, 80, 3), dtype=np.uint8) * 17, 255
    mov = np.zeros((120, 240, 4), np.uint8)
    mov[..., :3] = rng.integers(0, 255, (120, 240, 3), dtype=np.uint8)
    mov[..., 3] = 255
    mov[:, 200:, 3] = 128                                                         # a see-through edge
    backs = [_back(), _back(type=4, known=0, cx=300, x=0, y=-368, ry=0, rx=-6, origin=[0, 0], size=[240, 120],
                            mover={"v": -30.0})]
    return sc.Scene({"x0": -100, "y0": -50, "w": 900, "h": 700, "backs": backs}, canvas, [sky, mov], device="cpu")


def test_expected_draws_a_mover_at_its_place_and_leaves_its_rows_unknown_without_one():
    s = _mover_world()
    C = (40, 30)
    sy = sc.mover_pos(s.meta["backs"][1], C, 0)[1]
    e, k = s.expected(C, w=500, h=400)
    rows = np.zeros(400, bool)
    rows[max(0, sy):sy + 120] = True
    tiles = s._crop(C, 500, 400)[..., 3].numpy() == 255
    assert (k.numpy() == (~rows[:, None] | tiles)).all()                          # without a place: its rows unknown
    X = 517.0
    e, k = s.expected(C, w=500, h=400, X={1: X})
    assert k.all()                                                                # at its place: known
    pic = s.backs[1][1].numpy()
    for x in (0, 100, 250, 499):
        col = (x - (int(X) - C[0])) % 300
        y = sy + 50
        if col < 200 and not tiles[y, x]:
            assert np.allclose(e.numpy()[y, x], pic[50, col, :3]), x             # its own colours, exactly
    e0, k0 = s.expected(C, w=500, h=400, X={1: X}, pre=False)
    assert (e0 - e).abs().max() < 1e-3 and (k0 == k).all()


def test_the_layer_loop_draws_what_the_whole_screen_draw_draws_movers_and_all():
    """design 1: every layer drawn only where it is on screen must equal the reference (each layer over the whole
    screen) - groups, ADDED layers, unknown kinds, movers at random places or none, cameras in and out of the
    rendered area."""
    rng = np.random.default_rng(4)
    backs = [_back(rx=-30, ry=-100, type=2, cy=90, origin=[10, 20]),
             _back(rx=-30, ry=-100, type=0, x=120, y=-40, a=160),
             _back(rx=-12, ry=-8, type=4, known=0, cx=130, y=-300, mover={"v": -60.0}),
             _back(rx=-50, ry=-50, type=6, known=0),
             _back(rx=20, ry=4, type=4, known=0, cx=0, y=-200, flip=1, mover={"v": 100.0}),
             _back(rx=-80, ry=-100, type=0, x=300, y=80, blend=1),
             _back(rx=-20, ry=-20, type=1, x=-30, y=300, front=1, cx=200)]
    s, _, _ = _world(5, backs)
    for i in range(len(backs)):
        pic = np.zeros((60, 80, 4), np.uint8)
        pic[..., :3] = rng.integers(0, 255, (60, 80, 3))
        pic[..., 3] = np.where(rng.random((60, 80)) < 0.3, 0, rng.integers(60, 256, (60, 80)))
        t = torch.from_numpy(pic).float()
        t[..., 3] *= backs[i]["a"] / 255.0
        t[..., :3] *= t[..., 3:4] / 255.0
        s.backs[i] = (backs[i], t)
    s.groups = {f: s._compose(f) for f in (0, 1)}
    for C in [(-100, -50), (200, 150), (-466, -68), (-2000, 3000), (5000, -900)]:
        for X in (None, {2: float(rng.integers(0, 130)), 4: float(rng.uniform(-500, 500))}, {2: 7.0}):
            e0, k0 = s.expected(C, pre=False, X=X)
            e1, k1 = s.expected(C, X=X)
            assert (e0 - e1).abs().max() < 0.5 and (k0 != k1).float().mean() < 1e-4, (C, X)   # groups: fp16


def _mover_frames(s, X0, v, C0, n, dt=1 / 60, w=640, h=420, hide=()):
    """Frames of `s` with its mover at X0 + v t, the camera scrolling; noise boxes as mobs; frames in `hide`: the
    mover's rows covered by noise (a big effect)."""
    rng = np.random.default_rng(2)
    out = []
    for k in range(n):
        t = k * dt
        C = (C0[0] + k, C0[1])
        X = (X0 + v * t) % 300
        e, _ = s.expected(C, w=w, h=h, X={1: X})
        f = e.numpy().round().astype(np.uint8)
        for _ in range(6):
            x, y = int(rng.integers(0, w - 40)), int(rng.integers(0, h - 40))
            f[y:y + 40, x:x + 40] = rng.integers(0, 255, (40, 40, 3), dtype=np.uint8)
        if k in hide:
            f[:300] = rng.integers(0, 255, (300, w, 3), dtype=np.uint8)
        out.append((t, C, X, torch.from_numpy(f)))
    return out


def test_mover_follow_finds_a_mover_follows_it_to_the_pixel_coasts_when_hidden_and_finds_it_again():
    from maplebrain.config import Perception
    s = _mover_world()
    fol = sc.MoverFollow(s, Perception(mover_samples=1500))
    assert fol.M == 1 and fol.update(torch.zeros((420, 640, 3), dtype=torch.uint8), (0, 0), 0.0) == {1: None}
    fol = sc.MoverFollow(s, Perception(mover_samples=1500))
    frames = _mover_frames(s, 123.0, -30.0, (20, 10), 90, hide=set(range(40, 52)))
    for k, (t, C, X, f) in enumerate(frames):
        got = fol.update(f, C, t)[1]
        err = None if got is None else ((got - X + 150) % 300) - 150
        if k in range(40, 52):
            assert not fol.found[0] and abs(err) < 1                              # hidden: it coasts on its law
        else:
            assert fol.found[0] and abs(err) <= 0.5, (k, got, X)                  # found on the first frame
    assert fol.fulls == 1


def test_a_mover_with_few_opaque_pixels_is_not_found_by_chance_matches():
    """3-Way Road-Split's back_vicportTown/back_7 has 175 opaque pixels: drawn 4,000 times over (each pixel ~23 x),
    every chance match counted ~23 times and the peak rule passed at wrong places (904 frames, p50 75 px off its
    law). Each pixel is one sample: frames without the mover, in the mover's own few colours, find nothing."""
    from maplebrain.config import Perception
    rng = np.random.default_rng(5)
    palette = np.array([[40, 80, 120], [200, 30, 60], [10, 220, 90], [250, 250, 20]], np.uint8)
    canvas = np.zeros((700, 900, 4), np.uint8)
    sky = np.zeros((60, 80, 4), np.uint8)
    sky[..., 3] = 255
    mov = np.zeros((30, 60, 4), np.uint8)
    yy, xx = rng.integers(0, 30, 150), rng.integers(0, 60, 150)
    mov[yy, xx, :3] = palette[rng.integers(0, 4, 150)]
    mov[yy, xx, 3] = 255
    backs = [_back(), _back(type=4, known=0, cx=300, y=-368, ry=0, rx=-6, origin=[0, 0], size=[60, 30],
                            mover={"v": -30.0})]
    s = sc.Scene({"x0": -100, "y0": -50, "w": 900, "h": 700, "backs": backs}, canvas, [sky, mov], device="cpu")
    fol = sc.MoverFollow(s, Perception(mover_lost_s=0.0))                    # a full look every frame
    assert fol.px.shape[1] == len(set(zip(yy.tolist(), xx.tolist())))     # each opaque pixel once
    for k in range(40):
        f = torch.from_numpy(palette[rng.integers(0, 4, (420, 640))])
        fol.update(f, (k, 10), k / 60)
        assert not fol.found[0], k


def test_mover_follow_finds_nothing_where_the_mover_is_not():
    """A frame of another picture: never found, no place - and the full look waits `mover_lost_s` between tries."""
    from maplebrain.config import Perception
    s = _mover_world()
    other = _mover_world(seed=99)
    fol = sc.MoverFollow(s, Perception(mover_samples=1500))
    for k, (t, C, X, f) in enumerate(_mover_frames(other, 50.0, -30.0, (0, 10), 70)):
        assert fol.update(f, C, t) == {1: None}
    assert fol.fulls == 2                                                         # t = 0 and t = 1 s (70 frames)
