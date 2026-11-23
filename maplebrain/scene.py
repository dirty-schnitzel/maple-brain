"""The scene model (PLAN-perception.md step 1): what the frame shows where nothing moves, from the client's files.

A map's picture = background layers (`back`: parallax, mostly tiled) + tiles and objects (8 layers, map
coordinates) + background layers marked `front`. With the game window at native 1366x768 the client draws all of it
1:1 (measured 2026-11-16 on Ant Tunnel IV: 94 % of the play area within +-4 levels, the rest = mobs, players, tags,
effects), so: frame - expected scene = everything dynamic, and the frame registered against the tiles / objects =
the camera, exact to the pixel.

Build (`python -m maplebrain assets scene [MAP ...]`, from the client export; NOT in git: assets/scene/<map>/):
  scene.png   tiles + objects composited in draw order, PREMULTIPLIED BGRA, map coordinates from (x0, y0)
  anim.png    255 where an animated object draws (any frame): its pixels are unknown (only if the map has one)
  scene.json  {x0, y0, w, h, backs: [{file, x, y, rx, ry, cx, cy, type, a, front, flip, origin, blend, known,
              [mover]}], cloud, ...}   blend 1 = an ADDED layer: frame = min(255, under + colour x alpha), it covers
              nothing (Ellinia's light rays; PLAN-moving-scenery.md measurement 2). cloud 1 = the client draws its
              weather clouds (MapHelper.img/weather/cloud) over the field: Perion's region. mover {v} = a type 4 back
              whose place on the map moves v = 5 x rx px a second (measurement 3)
  ../backs/<set>/<back|ani>_<no>.png   the background pictures (shared between maps)
Run time: `Scene.load(map_id)`; `expected(C)` -> the scene for camera C (map = screen + C) + which pixels are
known; `register(frame, C_guess)` -> the camera. Torch tensors (GPU when there is one).

Background position (HeavenClient's MapBackgrounds with the client's own integer arithmetic):
    screen x of the picture's origin = bx + WOFF + trunc(rx * (Cx + WOFF) / 100),  y alike with HOFF
WOFF 683 (half the width), HOFF 468 (768 - 300: the old 800x600 client's centre, kept from the bottom); division
toward zero. Measured layer by layer on 7 maps (tools/perc/redesign/exp_backfit.py, rx -2 .. -80): every position
exact. (First fitted as 682 on Ant Tunnel IV alone: that recording was captured 1 px off, capture.game_columns.)
Tiled types repeat every cx / cy px (0 = the picture's size). Moving types (4-7: clouds) and animated backs have no
fixed place: their pixels are unknown - except a mover (type 4) whose place MoverFollow found on the frame:
`expected(C, X)` draws it there (`mover_pos`: x = X - Cx, the row with a floored parallax term). A map with movers
is still not `clean` (PLAN-moving-scenery.md step 2: nothing hunts there yet).
"""
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "assets" / "scene"
W, H, PLAY_H = 1366, 768, 700
WOFF, HOFF = 683, 468          # the client's "screen centre" in the background formula (measured, see above)
PAD = 200                      # px of map rendered around the footholds / vrBounds
H_TILED, V_TILED, MOVING = (1, 3, 4, 6, 7), (2, 3, 5, 6, 7), (4, 5, 6, 7)
MOVER_SPEED = 5.0              # a type 4 back's place on the map moves 5 x rx px a second (PLAN-moving-scenery.md
                               # measurement 3: fitted 4.994-5.012 x rx on 15 layers of 4 maps)


# ------------------------------------------------------------------ build (from the client export)
class _Parts:
    """Obj / Tile / Back pictures + their xml from the export, cached."""

    def __init__(self, export: Path, load_xml):
        self.export, self.load_xml = Path(export), load_xml
        self.sets, self.pics = {}, {}

    def node(self, kind: str, name: str, path) -> dict | None:
        key = (kind, name)
        if key not in self.sets:
            p = self.export / "Map" / kind / f"{name}.img.xml"
            self.sets[key] = self.load_xml(p) if p.exists() else None
        node = self.sets[key]
        for part in path:
            node = node.get(str(part)) if isinstance(node, dict) else None
        return node if isinstance(node, dict) else None

    def pic(self, kind: str, name: str, path):
        f = self.export / "Map" / kind / "png" / name / Path(*map(str, path[:-1])) / f"{path[-1]}.png"
        if f not in self.pics:
            im = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
            self.pics[f] = im if im is not None and im.ndim == 3 and im.shape[2] == 4 else None
        return self.pics[f], f

    def frames(self, kind: str, name: str, path) -> list:
        """[(bgra, origin, z)] of every frame at `path` (a canvas itself, or a node of numbered canvases)."""
        node = self.node(kind, name, path)
        if node is None:
            return []
        if "_size" in node:
            items = [(list(path), node)]
        else:
            items = [(list(path) + [k], v) for k, v in sorted(((int(k), v) for k, v in node.items() if k.isdigit()
                                                               and isinstance(v, dict) and "_size" in v))]
        out = []
        for pth, c in items:
            im, _ = self.pic(kind, name, pth)
            if im is not None:
                out.append((im, tuple(c.get("origin") or (0, 0)), c.get("z", 0)))
        return out


def _over(canvas: np.ndarray, im: np.ndarray, x: int, y: int) -> None:
    """Draw straight-alpha BGRA `im` at (x, y) over the premultiplied float canvas."""
    h, w = im.shape[:2]
    sx0, sy0, dx0, dy0 = max(0, -x), max(0, -y), max(0, x), max(0, y)
    dx1, dy1 = min(canvas.shape[1], x + w), min(canvas.shape[0], y + h)
    if dx1 <= dx0 or dy1 <= dy0:
        return
    src = im[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0].astype(np.float32)
    a = src[..., 3:4] / 255.0
    dst = canvas[dy0:dy1, dx0:dx1]
    dst[..., :3] = src[..., :3] * a + dst[..., :3] * (1 - a)
    dst[..., 3:4] = src[..., 3:4] + dst[..., 3:4] * (1 - a)


def build_scene(img: dict, m: dict, parts: _Parts) -> tuple:
    """(premultiplied BGRA uint8 canvas, animated mask or None, meta) of a map: `img` = its client xml, `m` = its
    map.json (footholds, vrBounds)."""
    fh = list((m.get("footholds") or {}).values())
    vr = m.get("vrBounds") or {}
    xs = [v for f in fh for v in (f["x1"], f["x2"])] + [vr[k] for k in ("left", "right") if k in vr]
    ys = [v for f in fh for v in (f["y1"], f["y2"])] + [vr[k] for k in ("top", "bottom") if k in vr]
    if not xs or not ys:
        return None, None, None
    x0, y0, x1, y1 = int(min(xs)) - PAD, int(min(ys)) - PAD, int(max(xs)) + PAD, int(max(ys)) + PAD
    canvas = np.zeros((y1 - y0, x1 - x0, 4), np.float32)
    anim = np.zeros(canvas.shape[:2], np.uint8)
    n_obj = n_tile = n_anim = 0
    for layer in range(8):
        lay = img.get(str(layer)) or {}
        objs = []
        for o in (lay.get("obj") or {}).values():
            if isinstance(o, dict) and o.get("oS"):
                fr = parts.frames("Obj", o["oS"], [o.get("l0"), o.get("l1"), o.get("l2")])
                if fr:
                    objs.append((o.get("z", 0), o.get("zM", 0), o, fr))
        objs.sort(key=lambda t: (t[0], t[1]))
        for _, _, o, fr in objs:
            for i, (im, (ox, oy), _) in enumerate(fr):
                if o.get("f", 0):
                    im, ox = im[:, ::-1], im.shape[1] - ox
                px, py = int(o.get("x", 0)) - ox - x0, int(o.get("y", 0)) - oy - y0
                if i == 0:
                    _over(canvas, im, px, py)
                if len(fr) > 1:                                 # animated: every frame's pixels are "unknown"
                    hh, ww = im.shape[:2]
                    a0, b0, a1, b1 = max(0, px), max(0, py), min(anim.shape[1], px + ww), min(anim.shape[0], py + hh)
                    if a1 > a0 and b1 > b0:
                        anim[b0:b1, a0:a1] |= (im[b0 - py:b1 - py, a0 - px:a1 - px, 3] > 0).astype(np.uint8) * 255
            n_obj += 1
            n_anim += len(fr) > 1
        ts = (lay.get("info") or {}).get("tS")
        tiles = []
        for t in (lay.get("tile") or {}).values():
            if isinstance(t, dict) and ts:
                fr = parts.frames("Tile", ts, [t.get("u"), t.get("no")])
                if fr:
                    tiles.append((fr[0][2] if fr[0][2] else t.get("zM", 0), t.get("zM", 0), t, fr[0]))
        tiles.sort(key=lambda t: (t[0], t[1]))
        for _, _, t, (im, (ox, oy), _) in tiles:
            _over(canvas, im, int(t.get("x", 0)) - ox - x0, int(t.get("y", 0)) - oy - y0)
            n_tile += 1
    backs = []
    for k in sorted((img.get("back") or {}), key=lambda s: int(s) if str(s).isdigit() else 10 ** 9):
        b = img["back"][k]
        if not isinstance(b, dict) or not b.get("bS"):
            continue
        kind = "ani" if b.get("ani") else "back"
        fr = parts.frames("Back", b["bS"], [kind, b.get("no", 0)])
        if not fr:
            continue
        im, origin, _ = fr[0]
        typ = int(b.get("type", 0))
        node = parts.node("Back", b["bS"], [kind, b.get("no", 0)]) or {}       # the picture's (an ani: its node's)
        blend = int(node.get("blend", 0) or 0)
        entry = {"set": b["bS"], "kind": kind, "no": int(b.get("no", 0)), "file": f"{b['bS']}/{kind}_{b.get('no', 0)}.png",
                 "x": int(b.get("x", 0)), "y": int(b.get("y", 0)), "rx": int(b.get("rx", 0)), "ry": int(b.get("ry", 0)),
                 "cx": int(b.get("cx", 0)), "cy": int(b.get("cy", 0)), "type": typ, "a": int(b.get("a", 255)),
                 "front": int(b.get("front", 0)), "flip": int(b.get("f", 0)), "origin": [int(origin[0]), int(origin[1])],
                 "size": [im.shape[1], im.shape[0]], "blend": blend,
                 "known": int(kind == "back" and typ not in MOVING)}
        if kind == "back" and typ == 4:                             # a mover: its place on the map moves with time
            entry["mover"] = {"v": MOVER_SPEED * entry["rx"]}
        backs.append(entry)
    out = np.clip(canvas + 0.5, 0, 255).astype(np.uint8)
    meta = {"x0": x0, "y0": y0, "w": x1 - x0, "h": y1 - y0, "objects": n_obj, "tiles": n_tile,
            "animated": int(n_anim), "backs": backs, "cloud": int((img.get("info") or {}).get("cloud", 0) or 0)}
    return out, (anim if n_anim else None), meta


def mob_layers(m: dict) -> list:
    """The foothold layers of a map (map.json): the layers its mobs can be drawn on (a mob is drawn on its
    foothold's layer: over the tiles / objects of layers <= L, under those of layers > L)."""
    return sorted({int(f.get("layerId", 0)) for f in (m.get("footholds") or {}).values()})


def build_layers(img: dict, m: dict, parts: _Parts, layers) -> dict:
    """L -> (behind, front): premultiplied BGRA uint8 canvases (scene.png's coordinates) of the tiles / objects of
    layers <= L and of layers > L (PLAN-perception.md step 3.2: the fit's planes). The bot loads only the front
    planes' alpha (Scene.load, 3.3); tests/test_scene_layers.py checks both from disk (front over behind = scene)."""
    out = {}
    for L in layers:
        sub = [{str(k): img[str(k)] for k in ks if str(k) in img} for ks in (range(0, L + 1), range(L + 1, 8))]
        out[L] = tuple(build_scene(s, m, parts)[0] for s in sub)
    return out


def build_scenes(export: Path, assets: Path, map_ids=None, out: Path = ROOT, log=print) -> int:
    """Render the scenes of `map_ids` (default: every map with mob spawns) into `out`. Returns how many."""
    from .gamedata import load_xml
    export, out = Path(export), Path(out)
    if not (export / "Map" / "Back").exists():
        raise FileNotFoundError(f"{export / 'Map' / 'Back'} missing - run tools/cwdata/export.ps1 (the 2026-11-16 one)")
    man = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    if map_ids is None:
        map_ids = [int(i) for i, e in man["maps"].items() if e.get("mobs")]
    parts, n = _Parts(export, load_xml), 0
    for mid in map_ids:
        src = next((export / "Map").glob(f"Map?/{int(mid):09d}.img.xml"), None)
        mj = assets / "maps" / str(mid) / "map.json"
        if src is None or not mj.exists():
            log(f"map {mid}: not in the export / assets")
            continue
        img = load_xml(src)
        m = json.loads(mj.read_text(encoding="utf-8"))
        canvas, anim, meta = build_scene(img, m, parts)
        if canvas is None:
            log(f"map {mid}: no footholds / bounds")
            continue
        d = out / str(mid)
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / "scene.png"), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        meta["layers"] = mob_layers(m)
        (d / "layers").mkdir(exist_ok=True)
        for L, pair in build_layers(img, m, parts, meta["layers"]).items():
            for name, c in zip(("behind", "front"), pair):
                cv2.imwrite(str(d / "layers" / f"{name}_{L}.png"), c, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        if anim is not None:
            cv2.imwrite(str(d / "anim.png"), anim)
        elif (d / "anim.png").exists():
            (d / "anim.png").unlink()
        for b in meta["backs"]:                                     # always copied: a fixed export replaces it
            dst = out / "backs" / b["file"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            src = export / "Map" / "Back" / "png" / b["set"] / b["kind"]
            src = (src / f"{b['no']}.png" if b["kind"] == "back"    # an animated back: its first frame (ani\<no>\<n>)
                   else min((src / str(b["no"])).glob("*.png"), key=lambda p: int(p.stem)))
            shutil.copyfile(src, dst)
        (d / "scene.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        n += 1
        log(f"map {mid}: {meta['w']}x{meta['h']}, {meta['objects']} objects ({meta['animated']} animated), "
            f"{meta['tiles']} tiles, {len(meta['backs'])} backs ({sum(1 for b in meta['backs'] if not b['known'])} unknown)")
    return n


# ------------------------------------------------------------------ run time
def back_pos(b: dict, C, woff: int = WOFF, hoff: int = HOFF) -> tuple:
    """Screen (x, y) of a background picture's top-left for camera C: the client's integer arithmetic (division
    toward zero)."""
    ox = b["size"][0] - b["origin"][0] if b.get("flip") else b["origin"][0]
    return (b["x"] + woff + int(b["rx"] * (int(C[0]) + woff) / 100) - ox,
            b["y"] + hoff + int(b["ry"] * (int(C[1]) + hoff) / 100) - b["origin"][1])


def mover_pos(b: dict, C, X: float, hoff: int = HOFF) -> tuple:
    """Screen (x, y) of a mover's picture's top-left (its left edge repeats every cx) for camera C, its place on the
    map `X` = where the picture's left edge is (PLAN-moving-scenery.md measurement 3): x = X - Cx; the row is the
    static formula's with another rounding - the parallax term is sign(u) x floor(ry x |u| / 100), u = Cy + HOFF (no
    exception in ~9,000 layer-frames, ry -16..+4, both signs of u)."""
    u = int(C[1]) + hoff
    return (int(round(X)) - int(C[0]),
            b["y"] + hoff + (1 if u >= 0 else -1) * math.floor(b["ry"] * abs(u) / 100) - b["origin"][1])


class _Draw:
    """One background layer, ready to be drawn only where it is on screen (PLAN-moving-scenery.md design 1): its
    premultiplied colour, alpha and 1 - alpha in one (H, W, 5) float tensor, padded with nothing (or cut) to its
    period on a tiled axis, so a camera's piece is a slice (untiled) or one index_select (tiled) per axis. The
    arithmetic is Scene._back_plane's over the whole screen, restricted to the rectangle the layer can touch: the
    same float operations on the same values (outside it the full-screen draw adds 0 x 1)."""

    def __init__(self, b: dict, t, torch):
        ph, pw = t.shape[:2]
        a = t[..., 3:4] / 255.0
        g = torch.cat([t[..., :3], a, 1 - a], dim=2)
        self.px = (b["cx"] or pw) if b["type"] in H_TILED else None
        self.py = (b["cy"] or ph) if b["type"] in V_TILED else None
        H_, W_ = self.py or ph, self.px or pw
        if (H_, W_) != (ph, pw):
            pad = torch.zeros((H_, W_, 5), device=t.device)
            pad[..., 4] = 1
            pad[:min(H_, ph), :min(W_, pw)] = g[:min(H_, ph), :min(W_, pw)]
            g = pad
        # a tiled axis repeated to cover a whole screen + one period: a screen's piece is then a slice, no gather
        g = g.repeat(-(-(H + H_) // H_) if self.py else 1, -(-(W + W_) // W_) if self.px else 1, 1)
        self.g, self.h, self.w = g.contiguous(), H_, W_
        self.rows_any = (t[..., 3] / 255.0 > 0.02).any(dim=1)          # (ph,) a row the picture draws on somewhere

    def piece(self, sx: int, sy: int, w: int, h: int, torch):
        """(y0, y1, x0, x1, (y1-y0, x1-x0, 5) tensor) of the layer on a (h, w) screen with its top-left at (sx, sy),
        or None when it is off screen. Screen row r shows picture row (r - sy) mod period: the repeated picture from
        row (-sy) mod period on (a screen larger than W x H: gathered)."""
        g = self.g
        if self.py is None:
            y0, y1 = max(0, sy), min(h, sy + self.h)
            if y1 <= y0:
                return None
            g = g[y0 - sy:y1 - sy]
        else:
            y0, y1, o = 0, h, (-sy) % self.py
            g = g[o:o + h] if o + h <= g.shape[0] else \
                g[:self.py].index_select(0, (torch.arange(h, device=g.device) - sy) % self.py)
        if self.px is None:
            x0, x1 = max(0, sx), min(w, sx + self.w)
            if x1 <= x0:
                return None
            g = g[:, x0 - sx:x1 - sx]
        else:
            x0, x1, o = 0, w, (-sx) % self.px
            g = g[:, o:o + w] if o + w <= g.shape[1] else \
                g[:, :self.px].index_select(1, (torch.arange(w, device=g.device) - sx) % self.px)
        return y0, y1, x0, x1, g


class Scene:
    def __init__(self, meta: dict, canvas: np.ndarray, back_pics: list, anim: np.ndarray | None = None, device=None,
                 layers: dict | None = None):
        """`canvas`: premultiplied BGRA uint8 (tiles + objects); `back_pics`: straight-alpha BGRA per meta back;
        `layers`: L -> the alpha (h, w) uint8 of its front plane (build_layers: the tiles / objects of the layers
        above L, in `canvas`'s coordinates) - all the fit reads of the planes (step 3.3: behind planes not loaded)."""
        import torch
        self.torch = torch
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.meta, self.x0, self.y0 = meta, meta["x0"], meta["y0"]
        self.woff, self.hoff = WOFF, HOFF                            # (not the build's: a constant of the client)
        self.canvas = torch.from_numpy(np.ascontiguousarray(canvas)).to(self.dev)              # (h, w, 4) uint8
        # the fit's front alphas (step 3.2), kept as the stored uint8
        self.layers = {int(L): torch.from_numpy(np.ascontiguousarray(a)).to(self.dev) for L, a in (layers or {}).items()}
        self.anim = None if anim is None else torch.from_numpy(anim > 0).to(self.dev)
        self.backs = []
        for b, pic in zip(meta["backs"], back_pics):
            if b.get("flip"):
                pic = pic[:, ::-1]
            t = torch.from_numpy(np.ascontiguousarray(pic)).to(self.dev).float()
            t[..., 3] *= b.get("a", 255) / 255.0
            t[..., :3] *= t[..., 3:4] / 255.0                                                   # premultiplied
            self.backs.append((b, t))
        self._marks = {}
        self.groups = {front: self._compose(front) for front in (0, 1)}

    # ---- background layers pre-composed per parallax (PLAN-perception.md step 2)
    def _shift(self, rx: int, ry: int, C) -> tuple:
        """Where a background layer group with parallax (rx, ry) sits on screen for camera C: back_pos without the
        picture's own place (the same for every layer of the group)."""
        return (self.woff + int(rx * (int(C[0]) + self.woff) / 100), self.hoff + int(ry * (int(C[1]) + self.hoff) / 100))

    def _compose(self, front: int) -> list:
        """The known background layers (front or not), in draw order, with runs of the same parallax (rx, ry) drawn
        ONCE at load into one picture over every camera the map allows (the rendered area's: vrBounds are inside it)
        -> [("group", (rx, ry), plane (H', W', 4) premultiplied colour + alpha 0..1, fp16, (U0, V0), [(b, t, i)]) |
        ("one", b, t, i)] (i = the layer's index in `backs`; a "one" gets its _Draw). A group moves as one: its layers keep their places relative to each other, so a camera's
        picture of it is a crop of the plane at -shift - (U0, V0). Unknown layers stay one by one (only their mask
        is used). Line 1 <Area 1>: 29 layers -> 4 groups, Transfer Area 36 -> 3 (16-22 ms -> one crop each)."""
        torch = self.torch
        if not hasattr(self, "_draws"):
            self._draws = {}                                          # back index -> _Draw (the layers drawn alone)
        runs = []
        for i, (b, t) in enumerate(self.backs):
            if bool(b["front"]) != bool(front):
                continue
            key = (b["rx"], b["ry"]) if b["known"] and not b.get("blend") else None    # ADDED layers: one by one
            if key is not None and runs and runs[-1][0] == key:
                runs[-1][1].append((b, t, i))
            else:
                runs.append((key, [(b, t, i)]))
        cams = [(self.x0 + i * (self.meta["w"] - W), self.y0 + j * (self.meta["h"] - H)) for i in (0, 1) for j in (0, 1)]
        out = []
        for key, layers in runs:
            if key is None or len(layers) == 1:
                for b, t, i in layers:
                    self._draws[i] = _Draw(b, t, torch)
                    out.append(("one", b, t, i))
                continue
            sh = [self._shift(*key, c) for c in cams]                 # monotonic in C: the corners bound it
            U0, V0 = -max(s[0] for s in sh), -max(s[1] for s in sh)
            pw, ph = W - min(s[0] for s in sh) - U0, H - min(s[1] for s in sh) - V0
            g = torch.zeros((ph, pw, 4), device=self.dev)
            for b, t, _ in layers:
                bx, by = back_pos(b, (0, 0), self.woff, self.hoff)
                s0 = self._shift(*key, (0, 0))
                plane = self._layer_plane(b, t, bx - s0[0] - U0, by - s0[1] - V0, pw, ph)
                a = plane[..., 3:4] / 255.0
                g[..., :3] = g[..., :3] * (1 - a) + plane[..., :3]
                g[..., 3:4] = g[..., 3:4] * (1 - a) + a
            out.append(("group", key, g.half(), (U0, V0), layers))
        return out

    @classmethod
    def load(cls, map_id: int, root: Path = ROOT, device=None) -> "Scene":
        d = Path(root) / str(map_id)
        meta = json.loads((d / "scene.json").read_text(encoding="utf-8"))
        canvas = cv2.imread(str(d / "scene.png"), cv2.IMREAD_UNCHANGED)
        anim = cv2.imread(str(d / "anim.png"), cv2.IMREAD_GRAYSCALE) if (d / "anim.png").exists() else None
        pics = [cv2.imread(str(Path(root) / "backs" / b["file"]), cv2.IMREAD_UNCHANGED) for b in meta["backs"]]
        layers = {L: cv2.imread(str(d / "layers" / f"front_{L}.png"), cv2.IMREAD_UNCHANGED)[..., 3]
                  for L in meta.get("layers") or [] if (d / "layers" / f"front_{L}.png").exists()}
        return cls(meta, canvas, pics, anim, device, layers)

    @staticmethod
    def have(map_id: int, root: Path = ROOT) -> bool:
        return (Path(root) / str(map_id) / "scene.json").exists()

    @staticmethod
    def clean_meta(meta: dict) -> bool:
        """Every background layer known or a mover behind the field (MoverFollow finds its place:
        PLAN-moving-scenery.md step 3), and no weather clouds (`cloud`: Perion's region, step 5): only such maps are
        hunted. Refused: type 5-7 and animated backs (the subway's deeper lines, the beach: step 6), the cloud maps,
        and a mover drawn in FRONT of the mobs (map 80003000's back_darkMountain/back_4: not in the plan's design)."""
        return (all(b["known"] or (b.get("mover") is not None and not b["front"]) for b in meta["backs"])
                and not meta.get("cloud"))

    @property
    def clean(self) -> bool:
        return self.clean_meta(self.meta)

    # ---- the expected picture
    def _back_plane(self, b: dict, t, C, w: int, h: int):
        """(premultiplied BGRA float (h, w, 4)) of one background layer for camera C."""
        return self._layer_plane(b, t, *back_pos(b, C, self.woff, self.hoff), w, h)

    def _layer_plane(self, b: dict, t, sx: int, sy: int, w: int, h: int):
        """One background layer with its picture's top-left at (sx, sy) of a (h, w) plane, tiled as its type says."""
        torch = self.torch
        ph, pw = t.shape[:2]
        xs = torch.arange(w, device=self.dev) - sx
        ys = torch.arange(h, device=self.dev) - sy
        if b["type"] in H_TILED:
            xs = xs % (b["cx"] or pw)
        if b["type"] in V_TILED:
            ys = ys % (b["cy"] or ph)
        okx, oky = (xs >= 0) & (xs < pw), (ys >= 0) & (ys < ph)
        plane = t[ys.clamp(0, ph - 1)][:, xs.clamp(0, pw - 1)]
        return plane * (oky[:, None] & okx[None, :])[..., None]

    def _crop(self, C, w: int, h: int, canvas=None):
        """The tile / object canvas (default: all layers) for camera C, zero outside the rendered area: (h, w, 4)
        uint8."""
        torch = self.torch
        canvas = self.canvas if canvas is None else canvas
        ax, ay = int(C[0]) - self.x0, int(C[1]) - self.y0
        ch, cw = canvas.shape[:2]
        out = torch.zeros((h, w, 4), dtype=torch.uint8, device=self.dev)
        x0, y0, x1, y1 = max(0, ax), max(0, ay), min(cw, ax + w), min(ch, ay + h)
        if x1 > x0 and y1 > y0:
            out[y0 - ay:y1 - ay, x0 - ax:x1 - ax] = canvas[y0:y1, x0:x1]
        return out

    def _backs(self, C, w: int, h: int, front: int, acc, unknown, pre: bool = True, X: dict | None = None):
        """Draw the background layers (`front` or not) for camera C over `acc` ((h, w, 4) float: the premultiplied
        bgr, and in channel 3 how much known scenery covers the pixel - one blend draws both) and `unknown` ((h, w)
        bool), both changed in place -> the two. `pre`: the pre-composed groups (`_compose`) and every other layer
        only where it is on screen (_Draw); False = layer by layer over the whole screen (the reference). `X`: back
        index -> a mover's place on the map (MoverFollow); a mover without one leaves every row it can draw on
        unknown (it can be anywhere along them)."""
        torch = self.torch

        def draw(b, t, i, full):
            mv = b.get("mover") is not None
            x = X.get(i) if mv and X is not None else None
            if mv and x is None:                                      # a mover never found
                ra = self._draws[i].rows_any
                sy = mover_pos(b, C, 0, self.hoff)[1]
                r0, r1 = max(0, sy), min(h, sy + len(ra))
                if r1 > r0:
                    unknown[r0:r1] |= ra[r0 - sy:r1 - sy, None]
                return
            sx, sy = mover_pos(b, C, x, self.hoff) if mv else back_pos(b, C, self.woff, self.hoff)
            if full:
                pl = self._layer_plane(b, t, sx, sy, w, h)
                a = pl[..., 3:4] / 255.0
                y0, y1, x0, x1, ca, ia = 0, h, 0, w, torch.cat([pl[..., :3], a], dim=2), 1 - a
            else:
                piece = self._draws[i].piece(sx, sy, w, h, torch)
                if piece is None:
                    return
                y0, y1, x0, x1, g = piece
                ca, ia = g[..., :4], g[..., 4:5]
            a = ca[..., 3]
            if not b["known"] and not mv:                             # moving / animated kinds not followed yet
                unknown[y0:y1, x0:x1] |= a > 0.02
                return
            dst = acc[y0:y1, x0:x1]
            if b.get("blend"):                                        # ADDED (Ellinia's light rays): covers nothing
                dst[..., :3].add_(ca[..., :3]).clamp_(max=255)
                return
            dst.mul_(ia).add_(ca)                                     # colour and cover: x (1 - a) + (colour, a)
            if mv:                                                    # an opaque mover hides what is behind it
                unknown[y0:y1, x0:x1] &= a < 0.98

        for item in self.groups[front] if pre else [("one", b, t, i) for i, (b, t) in enumerate(self.backs)
                                                    if bool(b["front"]) == bool(front)]:
            if item[0] == "one":
                draw(*item[1:], full=not pre)
                continue
            _, key, g, (U0, V0), layers = item
            sx, sy = self._shift(*key, C)
            u, v = -sx - U0, -sy - V0                                 # the plane's column / row at screen (0, 0)
            if u < 0 or v < 0 or u + w > g.shape[1] or v + h > g.shape[0]:
                for b, t, i in layers:                                # a camera outside the rendered area
                    draw(b, t, i, full=True)
                continue
            crop = g[v:v + h, u:u + w].float()                        # (colour, alpha) as acc holds them
            acc.mul_(1 - crop[..., 3:4]).add_(crop)
        return acc, unknown

    def _anim(self, C, w: int, h: int):
        """(h, w) bool: where an animated object draws (unknown), or None."""
        if self.anim is None:
            return None
        torch = self.torch
        ax, ay = int(C[0]) - self.x0, int(C[1]) - self.y0
        an = torch.zeros((h, w), dtype=torch.bool, device=self.dev)
        ch, cw = self.anim.shape
        x0, y0, x1, y1 = max(0, ax), max(0, ay), min(cw, ax + w), min(ch, ay + h)
        if x1 > x0 and y1 > y0:
            an[y0 - ay:y1 - ay, x0 - ax:x1 - ax] = self.anim[y0:y1, x0:x1]
        return an

    def expected(self, C, w: int = W, h: int = PLAY_H, pre: bool = True, X: dict | None = None) -> tuple:
        """What the frame's top `h` rows show for camera C: (bgr float tensor (h, w, 3), known bool tensor (h, w)).
        Known = covered by scenery whose place is known (opaque tiles / objects, fixed backgrounds, movers at their
        place `X`: back index -> its place on the map, MoverFollow.places) and not by an animated object, a mover
        without a place, another moving / animated background or a `front` background that isn't fixed.
        `pre`: the pre-composed groups (`_compose`) and every other layer drawn only where it is on screen; False =
        layer by layer over the whole screen (the reference, tests/test_scene.py)."""
        torch = self.torch
        acc = torch.zeros((h, w, 4), device=self.dev)                # bgr + how much known scenery covers the pixel
        unknown = torch.zeros((h, w), dtype=torch.bool, device=self.dev)
        self._backs(C, w, h, 0, acc, unknown, pre, X)
        sc = self._crop(C, w, h).float()
        a = sc[..., 3:4] / 255.0
        acc.mul_(1 - a).add_(torch.cat([sc[..., :3], a], dim=2))
        unknown &= a[..., 0] < 0.98                                  # an unknown back behind opaque scenery: hidden
        an = self._anim(C, w, h)
        if an is not None:
            unknown |= an
        self._backs(C, w, h, 1, acc, unknown, pre, X)
        return acc[..., :3].contiguous(), (acc[..., 3] > 0.98) & ~unknown

    # ---- the camera
    def marks(self, C, w: int = W, h: int = PLAY_H, n: int = 6000, margin: int = 48):
        """Landmarks for registration around camera C: up to `n` opaque tile / object pixels of the view with a
        strong edge (they pin the offset; flat areas don't), spread over the view: (N, 2) screen (x, y) for camera
        C and (N, 3) their colours. Cached per ~margin px of camera."""
        torch = self.torch
        key = (int(C[0]) // margin, int(C[1]) // margin, w, h, n)
        if key in self._marks:
            return self._marks[key]
        base = (key[0] * margin, key[1] * margin)
        big = self._crop((base[0] - margin, base[1] - margin), w + 3 * margin, h + 3 * margin)
        col = big[..., :3].float()
        op = big[..., 3] == 255
        g = col.sum(dim=2)
        edge = torch.zeros_like(g)
        edge[1:-1, 1:-1] = (g[1:-1, 2:] - g[1:-1, :-2]).abs() + (g[2:, 1:-1] - g[:-2, 1:-1]).abs()
        solid = op.clone()                                           # the pixel and its 4 neighbours opaque: no
        solid[1:-1, 1:-1] &= op[1:-1, 2:] & op[1:-1, :-2] & op[2:, 1:-1] & op[:-2, 1:-1]   # blended edge pixels
        edge = torch.where(solid, edge, torch.zeros_like(edge))
        cell = 16                                                    # the strongest edge of every 16x16 cell
        hh, ww = (edge.shape[0] // cell) * cell, (edge.shape[1] // cell) * cell
        e = edge[:hh, :ww].reshape(hh // cell, cell, ww // cell, cell).permute(0, 2, 1, 3).reshape(hh // cell, ww // cell, -1)
        val, idx = e.max(dim=2)
        cy, cx = torch.meshgrid(torch.arange(hh // cell, device=self.dev), torch.arange(ww // cell, device=self.dev),
                                indexing="ij")
        py, px = cy * cell + idx // cell, cx * cell + idx % cell
        keep = val > 30
        py, px, val = py[keep], px[keep], val[keep]
        if len(val) > n:
            top = val.topk(n).indices
            py, px = py[top], px[top]
        pts_map = torch.stack([px + base[0] - margin, py + base[1] - margin], dim=1)             # map coordinates
        out = (pts_map, col[py, px])
        if len(self._marks) > 64:
            self._marks.clear()
        self._marks[key] = out
        return out

    def register(self, frame, C_guess, radius: int = 12, tol: int = 4, h: int = PLAY_H, mask=None) -> tuple:
        """The camera near `C_guess` (within `radius` px on both axes): the offset at which the most landmarks
        (tile / object edge pixels) show their own colour within `tol` levels in `frame` (BGR uint8 array or
        tensor (>= h, w, 3)). `mask`: bool (h, w), False = don't use (the HUD). -> ((Cx, Cy), share of the
        landmarks that match, landmarks used); None when the view holds too few landmarks."""
        torch = self.torch
        f = frame if torch.is_tensor(frame) else torch.from_numpy(np.ascontiguousarray(frame[:h])).to(self.dev)
        f = f[:h]
        w = f.shape[1]
        gx, gy = int(round(C_guess[0])), int(round(C_guess[1]))
        pts, col = self.marks((gx, gy), w, h)
        sx, sy = pts[:, 0] - gx, pts[:, 1] - gy                      # landmark screen positions at the guess
        inside = (sx >= radius) & (sx < w - radius) & (sy >= radius) & (sy < h - radius)
        if mask is not None:
            m = mask if torch.is_tensor(mask) else torch.from_numpy(mask).to(self.dev)
            inside &= m[sy.clamp(0, h - 1), sx.clamp(0, w - 1)]
        sx, sy, col = sx[inside], sy[inside], col[inside]
        if len(sx) < 200:
            return None
        cap = max(400, 3_000_000 // (2 * radius + 1) ** 2)            # a wide look: fewer landmarks (memory)
        if len(sx) > cap:
            pick = torch.linspace(0, len(sx) - 1, cap, device=self.dev).long()
            sx, sy, col = sx[pick], sy[pick], col[pick]
        d = torch.arange(-radius, radius + 1, device=self.dev)
        # a camera shifted by (dx, dy) shows the landmark at screen - (dx, dy)
        yy = (sy[:, None, None] - d[None, :, None]).expand(-1, -1, len(d))
        xx = (sx[:, None, None] - d[None, None, :]).expand(-1, len(d), -1)
        got = f[yy, xx].float()                                       # (N, 2r+1, 2r+1, 3)
        ok = ((got - col[:, None, None, :]).abs().amax(dim=3) <= tol).float().mean(dim=0)
        best = int(ok.argmax())
        iy, ix = divmod(best, len(d))
        return (gx + int(d[ix]), gy + int(d[iy])), float(ok[iy, ix]), int(len(sx))

    def locate(self, frame, C_guess=None, seed=None, tol: int = 4, h: int = PLAY_H, mask=None, wide: int = 48,
               min_share: float = 0.2, last_share: float | None = None):
        """The camera, from the last one (`C_guess`: looked for within 12 px, then `wide`) and / or a rough one
        (`seed`: the minimap's, within `wide`). A wrong offset matches ~2 % of the landmarks on most scenery, the
        right one 40-95 % (40 %: a game window open over the scene): under `min_share` = not found, None (a camera
        that only resembles the last one is worse than none).
        But scenery repeats (Transfer Area's brick walls, 2026-11-16: the camera had moved > 12 px between saved
        frames, a camera one brick over matched 31 % and was taken, 61 px off for 2 s): a look is final only if it
        matches about as well as the last frame did (`last_share`, x 0.85); else every look is made and the best
        match wins."""
        best = None
        for guess, radius in ((C_guess, 12), (C_guess, wide), (seed, wide)):
            if guess is None:
                continue
            r = self.register(frame, guess, radius, tol, h, mask)
            if r is None:
                continue
            if best is None or r[1] > best[1]:
                best = r
            if last_share is not None and r[1] >= max(min_share, 0.85 * last_share):
                break
        return best if best is not None and best[1] >= min_share else None

    # ---- D: what the scene does not explain (PLAN-perception.md step 3.1)
    def diff(self, frame, C, tol: int = 4, mask=None, h: int = PLAY_H, ek=None) -> np.ndarray:
        """D = the frame's known-scenery pixels more than `tol` levels off the expected scene for camera C (any
        channel), outside `mask` (bool tensor, 1 = world: hud.ui_mask), as blobs: 3x3 cores grown 13x13 - the rule
        of tools/perc/labels/patches.py (cv2 erode / dilate, its borders) - on the GPU. `frame`: uint8 BGR, GPU
        tensor or array, >= h rows. `ek`: expected(C) if the caller has it (the Perceiver: one a tick for D and the
        fit, step 3.3). -> (h, w) uint8 array, 1 = blob (`patches` lists them)."""
        torch = self.torch
        F = torch.nn.functional
        f = frame[:h] if torch.is_tensor(frame) else torch.from_numpy(np.ascontiguousarray(frame[:h])).to(self.dev)
        exp, known = ek if ek is not None else self.expected(C, w=f.shape[1], h=h)
        bad = ((f.float() - exp).abs().amax(dim=2) > tol) & known
        if mask is not None:
            bad &= mask
        b = bad[None, None].half()
        core = 1 - F.max_pool2d(1 - b, 3, 1, 1)                     # erode 3x3 (outside the frame counts as set)
        blob = F.max_pool2d(core, 13, 1, 6)[0, 0] > 0               # dilate 13x13 (outside: not set)
        return blob.to(torch.uint8).cpu().numpy()


def patches(blob: np.ndarray, min_area: int = 60) -> list:
    """[(x, y, w, h, area)] of D's blobs (Scene.diff), 8-connected, >= min_area px, biggest first. On the CPU: exact
    connected components on the GPU measured 12 ms p50 (label propagation in torch), cv2 here ~1.3 ms."""
    n, _, st, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
    out = [tuple(int(v) for v in st[i]) for i in range(1, n) if st[i][4] >= min_area]
    return sorted(out, key=lambda b: -b[4])


class SceneCamera:
    """The camera from the scene, frame after frame (PLAN-perception.md step 2): `Scene.locate` around where the
    camera should be now (the last camera + its last step: a scrolling camera moves up to ~26 px per live tick, the
    first look reaches 12), the last match share as `last_share` (repeating scenery, see locate), the minimap's
    camera as the seed that recovers a lost one. Not found -> `C` stays the last camera (the next look starts there)
    and `found` is False: nothing is guessed."""

    def __init__(self, scene: Scene, tol: int = 4, min_share: float = 0.2, h: int = PLAY_H):
        self.scene, self.tol, self.min_share, self.h = scene, tol, min_share, h
        self.C = None                  # the last camera found (map = screen + C)
        self.step = (0, 0)             # its last move
        self.share = None              # landmarks matching at the last camera (None: lost)
        self.found = False             # found on the last frame
        self.misses = 0                # frames in a row it wasn't found
        self.n_marks = 0
        self._mask = (None, None)

    def _mask_t(self, mask):
        if mask is None:
            return None
        if self._mask[0] is not mask:
            self._mask = (mask, self.scene.torch.from_numpy(np.ascontiguousarray(mask[:self.h] > 0)).to(self.scene.dev))
        return self._mask[1]

    def update(self, frame, seed=None, mask=None):
        """`frame`: the frame (uint8 BGR, GPU tensor or array, >= PLAY_H rows); `seed`: a rough camera (the minimap's)
        or None; `mask`: the UI mask (hud.ui_mask, 1 = world). -> (Cx, Cy) or None."""
        guess = None if self.C is None else (self.C[0] + self.step[0], self.C[1] + self.step[1])
        reg = self.scene.locate(frame, C_guess=guess, seed=seed, tol=self.tol, h=self.h, mask=self._mask_t(mask),
                                min_share=self.min_share, last_share=self.share)
        self.found = reg is not None
        self.misses = 0 if self.found else self.misses + 1
        if reg is None:
            self.share, self.step = None, (0, 0)
            return None
        C, self.share, self.n_marks = reg
        self.step = (0, 0) if self.C is None else (C[0] - self.C[0], C[1] - self.C[1])
        self.C = C
        return C


class MoverFollow:
    """Where each mover is on the map, frame after frame (PLAN-moving-scenery.md design 2; ported from the
    prototype tools/perc/scenery/fastpipe.py FastMovers). A mover's opaque pixels show their own colours wherever
    nothing is drawn over them, and its place X (the picture's left edge on the map, mod its period) moves by its law
    (`v` = 5 x rx px a second: scene.json `mover`). Each frame every mover found before is looked for at the law's
    prediction +- `mover_near` px - all movers x places in one batch - on a fixed set of sample pixels (opaque
    pixels of its picture) that no tile / object covers there. Found = the best place stands out against the others
    (a peak rule: a mover mostly hidden behind later layers still shows its visible part, so its share is diluted,
    its peak is not); else it coasts on its law. A mover never found, or lost for `mover_lost_s`, gets the full look:
    every place of its period, one mover a frame, again at most every `mover_lost_s`. Nothing is guessed: `places()`
    gives None for a mover never found (Scene.expected leaves its rows unknown)."""

    def __init__(self, scene: Scene, cfg=None, seed: int = 0):
        from .config import Perception
        cfg = cfg or Perception()
        torch = scene.torch
        self.scene, self.torch, self.dev = scene, torch, scene.dev
        self.tol, self.near, self.peak, self.lost_s = cfg.scene_tol, cfg.mover_near, cfg.mover_peak, cfg.mover_lost_s
        n = cfg.mover_samples
        gen = torch.Generator().manual_seed(seed)
        self.idx, px, py, col, per, v = [], [], [], [], [], []
        for i, (b, t) in enumerate(scene.backs):
            if b.get("mover") is None:
                continue
            tc = t.cpu()
            period = b["cx"] or tc.shape[1]
            op = tc[..., 3] >= 254.5                                   # opaque (the entry's `a` is in t already)
            op[:, period:] = False                                     # cut to its period: never drawn
            yy, xx = op.nonzero(as_tuple=True)
            if len(yy) == 0:                                           # see-through: its colours are never its own
                continue
            pick = torch.randperm(len(yy), generator=gen)[:n]          # each pixel once: a repeated sample would
            self.idx.append(i)                                         # count one chance match many times
            px.append(xx[pick])
            py.append(yy[pick])
            col.append(tc[yy[pick], xx[pick], :3].round().short())
            per.append(period)
            v.append(float(b["mover"]["v"]))
        self.M = M = len(self.idx)
        if not M:
            return
        N = max(len(p) for p in px)                                    # fewer opaque pixels: padded with samples
        for k in range(M):                                             # far above the screen (never on it)
            pad = N - len(px[k])
            px[k] = torch.cat([px[k], torch.zeros(pad, dtype=px[k].dtype)])
            py[k] = torch.cat([py[k], torch.full((pad,), -10 ** 6, dtype=py[k].dtype)])
            col[k] = torch.cat([col[k], torch.zeros((pad, 3), dtype=col[k].dtype)])
        self.px, self.py = torch.stack(px).to(self.dev), torch.stack(py).to(self.dev)             # (M, N)
        self.col = torch.stack(col).to(self.dev)                                                  # (M, N, 3) int16
        self.cx = torch.tensor(per, device=self.dev)
        self.v = torch.tensor(v, dtype=torch.float64, device=self.dev)
        self.off = torch.arange(-self.near, self.near + 1, device=self.dev)
        self.X = torch.zeros(M, dtype=torch.float64, device=self.dev)
        ch, cw = scene.canvas.shape[:2]                # tiles / objects (over every back), padded by a screen: any
        self.tiles = torch.zeros((ch + 2 * H, cw + 2 * W), dtype=torch.bool, device=self.dev)   # camera's = a slice
        self.tiles[H:H + ch, W:W + cw] = scene.canvas[..., 3] > 0
        self.t = None
        self.seen = np.zeros(M, bool)                  # found at least once
        self.found = np.zeros(M, bool)                 # found on the last frame
        self.share = np.zeros(M)                       # of its free samples, the share matching at its place
        self.last_found = np.full(M, -np.inf)
        self.last_full = np.full(M, -np.inf)
        self.fulls = 0                                 # full looks made
        self._Xc = np.zeros(M)                         # X on the CPU (one transfer a frame)
        self._sub, self._tops = {}, {}

    def _subset(self, rows: np.ndarray):
        """(rows tensor, px, py, col, cx) of the movers `rows`, cached per set."""
        key = rows.tobytes()
        if key not in self._sub:
            r = self.torch.from_numpy(rows).to(self.dev)
            self._sub[key] = (r, self.px[r], self.py[r], self.col[r], self.cx[r])
        return self._sub[key]

    def _hits(self, f, C, rows: np.ndarray, cand):
        """Matching and free samples (J, K) of movers `rows` (J,) at places `cand` (J, K) on frame `f` (h, w, 3)."""
        torch, sc = self.torch, self.scene
        h, w = f.shape[:2]
        _, px, py, col, cx = self._subset(rows)
        key = (int(C[1]), rows.tobytes())
        if key not in self._tops:                      # the rows depend on Cy only
            if len(self._tops) > 256:
                self._tops.clear()
            self._tops[key] = torch.tensor([mover_pos(sc.backs[self.idx[j]][0], C, 0, sc.hoff)[1] for j in rows],
                                           device=self.dev)
        tops = self._tops[key]
        sx = (cand[:, :, None] - int(C[0]) + px[:, None, :]) % cx[:, None, None]                 # (J, K, N)
        sy = (tops[:, None] + py)[:, None, :].expand_as(sx)
        ok = (sx < w) & (sy >= 0) & (sy < h)
        sxc, syc = sx.clamp(max=w - 1), sy.clamp(0, h - 1)
        got = f[syc, sxc].short()                                                                 # (J, K, N, 3)
        ax, ay = int(C[0]) - sc.x0 + W, int(C[1]) - sc.y0 + H
        if 0 <= ax <= self.tiles.shape[1] - w and 0 <= ay <= self.tiles.shape[0] - h:
            tiles = self.tiles[ay:ay + h, ax:ax + w]
        else:                                          # a camera far outside the map: nothing there
            tiles = torch.zeros((h, w), dtype=torch.bool, device=self.dev)
        free = ok & ~tiles[syc, sxc]
        hit = free & ((got - col[:, None]).abs().amax(dim=3) <= self.tol)
        return hit.sum(dim=2).float(), free.sum(dim=2).float()

    def _peak(self, hits):
        """(best index (J,), found (J,)) by the peak rule over each row of `hits` (J, K)."""
        torch = self.torch
        ar = torch.arange(hits.shape[0], device=self.dev)
        best = hits.argmax(dim=1)
        bh = hits[ar, best]
        rest = hits.clone()
        rest[ar, best] = -1
        second = rest.amax(dim=1)
        p0, p1, p2 = self.peak
        found = (bh >= p0) & (bh >= second + torch.clamp(p2 * second.clamp(min=0).sqrt(), min=p1))
        return best, found

    def update(self, frame, C, t: float) -> dict:
        """The movers' places on this frame. `frame`: uint8 BGR tensor on the scene's device (>= PLAY_H rows); `C`:
        the scene camera; `t`: the frame's time in seconds. -> places()."""
        if not self.M:
            return {}
        torch = self.torch
        f = frame[:PLAY_H]
        X = (self.X + self.v * (t - self.t)) % self.cx if self.t is not None else self.X.clone()   # the law
        self.t = t
        found = np.zeros(self.M, bool)
        share = np.zeros(self.M)
        seen = np.flatnonzero(self.seen)
        if len(seen):
            rows, _, _, _, cx = self._subset(seen)
            cand = X[rows].round().long()[:, None] + self.off[None, :]
            hits, n = self._hits(f, C, seen, cand)
            best, ok = self._peak(hits)
            ar = torch.arange(len(seen), device=self.dev)
            X[rows] = torch.where(ok, (cand[ar, best] % cx).double(), X[rows])
            sh = hits[ar, best] / n[ar, best].clamp(min=1)
            pack = torch.cat([ok.double(), sh.double(), X]).cpu().numpy()          # the frame's one transfer
            J = len(seen)
            found[seen], share[seen], self._Xc = pack[:J] > 0.5, pack[J:2 * J], pack[2 * J:].copy()
        else:
            self._Xc = X.cpu().numpy().copy()
        lost = ~found & (~self.seen | (t - self.last_found >= self.lost_s)) & (t - self.last_full >= self.lost_s)
        if lost.any():                                 # the full look: the one waiting longest
            j = int(np.flatnonzero(lost)[np.argmin(self.last_full[lost])])
            self.last_full[j] = t
            self.fulls += 1
            one = np.array([j])
            per = int(self.cx[j])
            hs, ns = [], []
            for k in range(0, per, 256):
                h_, n_ = self._hits(f, C, one, torch.arange(k, min(per, k + 256), device=self.dev)[None, :])
                hs.append(h_)
                ns.append(n_)
            hits, n = torch.cat(hs, dim=1), torch.cat(ns, dim=1)
            best, ok = self._peak(hits)
            b = int(best[0])
            sh = float(hits[0, b] / n[0, b].clamp(min=1))
            if bool(ok[0]):
                X[j], self._Xc[j] = float(b), float(b)
                found[j], share[j] = True, sh
        self.X = X
        self.found, self.share = found, share
        self.last_found[found] = t
        self.seen |= found
        return self.places()

    def places(self) -> dict:
        """back index -> the mover's place on the map (float px), None = never found."""
        if not self.M:
            return {}
        return {i: (float(self._Xc[j]) if self.seen[j] else None) for j, i in enumerate(self.idx)}
