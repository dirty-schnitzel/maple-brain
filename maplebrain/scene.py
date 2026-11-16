"""The scene model (PLAN-perception.md step 1): what the frame shows where nothing moves, from the client's files.

A map's picture = background layers (`back`: parallax, mostly tiled) + tiles and objects (8 layers, map
coordinates) + background layers marked `front`. With the game window at native 1366x768 the client draws all of it
1:1 (measured 2026-11-16 on Ant Tunnel IV: 94 % of the play area within +-4 levels, the rest = mobs, players, tags,
effects), so: frame - expected scene = everything dynamic, and the frame registered against the tiles / objects =
the camera, exact to the pixel.

Build (`python -m maplebrain assets scene [MAP ...]`, from the client export; NOT in git: assets/scene/<map>/):
  scene.png   tiles + objects composited in draw order, PREMULTIPLIED BGRA, map coordinates from (x0, y0)
  anim.png    255 where an animated object draws (any frame): its pixels are unknown (only if the map has one)
  scene.json  {x0, y0, w, h, backs: [{file, x, y, rx, ry, cx, cy, type, a, front, flip, origin, known}], ...}
  ../backs/<set>/<back|ani>_<no>.png   the background pictures (shared between maps)
Run time: `Scene.load(map_id)`; `expected(C)` -> the scene for camera C (map = screen + C) + which pixels are
known; `register(frame, C_guess)` -> the camera. Torch tensors (GPU when there is one).

Background position (HeavenClient's MapBackgrounds with the client's own integer arithmetic; fitted on 65 layer
positions, all exact):  screen x of the picture's origin = bx + WOFF + trunc(rx * (Cx + WOFF) / 100), y alike with
HOFF; tiled types repeat every cx / cy px (0 = the picture's size). Moving types (4-7: clouds) and animated backs
have no fixed place: their pixels are unknown.
"""
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "assets" / "scene"
W, H, PLAY_H = 1366, 768, 700
WOFF, HOFF = 682, 468          # the client's "screen centre" in the background formula (fitted, see above)
PAD = 200                      # px of map rendered around the footholds / vrBounds
H_TILED, V_TILED, MOVING = (1, 3, 4, 6, 7), (2, 3, 5, 6, 7), (4, 5, 6, 7)


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
        backs.append({"set": b["bS"], "kind": kind, "no": int(b.get("no", 0)), "file": f"{b['bS']}/{kind}_{b.get('no', 0)}.png",
                      "x": int(b.get("x", 0)), "y": int(b.get("y", 0)), "rx": int(b.get("rx", 0)), "ry": int(b.get("ry", 0)),
                      "cx": int(b.get("cx", 0)), "cy": int(b.get("cy", 0)), "type": typ, "a": int(b.get("a", 255)),
                      "front": int(b.get("front", 0)), "flip": int(b.get("f", 0)), "origin": [int(origin[0]), int(origin[1])],
                      "size": [im.shape[1], im.shape[0]],
                      "known": int(kind == "back" and typ not in MOVING)})
    out = np.clip(canvas + 0.5, 0, 255).astype(np.uint8)
    meta = {"x0": x0, "y0": y0, "w": x1 - x0, "h": y1 - y0, "woff": WOFF, "hoff": HOFF, "objects": n_obj, "tiles": n_tile,
            "animated": int(n_anim), "backs": backs}
    return out, (anim if n_anim else None), meta


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
        canvas, anim, meta = build_scene(img, json.loads(mj.read_text(encoding="utf-8")), parts)
        if canvas is None:
            log(f"map {mid}: no footholds / bounds")
            continue
        d = out / str(mid)
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / "scene.png"), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        if anim is not None:
            cv2.imwrite(str(d / "anim.png"), anim)
        elif (d / "anim.png").exists():
            (d / "anim.png").unlink()
        for b in meta["backs"]:
            dst = out / "backs" / b["file"]
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(export / "Map" / "Back" / "png" / b["set"] / b["kind"] / f"{b['no']}.png", dst)
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


class Scene:
    def __init__(self, meta: dict, canvas: np.ndarray, back_pics: list, anim: np.ndarray | None = None, device=None):
        """`canvas`: premultiplied BGRA uint8 (tiles + objects); `back_pics`: straight-alpha BGRA per meta back."""
        import torch
        self.torch = torch
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.meta, self.x0, self.y0 = meta, meta["x0"], meta["y0"]
        self.woff, self.hoff = meta.get("woff", WOFF), meta.get("hoff", HOFF)
        self.canvas = torch.from_numpy(np.ascontiguousarray(canvas)).to(self.dev)              # (h, w, 4) uint8
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

    @classmethod
    def load(cls, map_id: int, root: Path = ROOT, device=None) -> "Scene":
        d = Path(root) / str(map_id)
        meta = json.loads((d / "scene.json").read_text(encoding="utf-8"))
        canvas = cv2.imread(str(d / "scene.png"), cv2.IMREAD_UNCHANGED)
        anim = cv2.imread(str(d / "anim.png"), cv2.IMREAD_GRAYSCALE) if (d / "anim.png").exists() else None
        pics = [cv2.imread(str(Path(root) / "backs" / b["file"]), cv2.IMREAD_UNCHANGED) for b in meta["backs"]]
        return cls(meta, canvas, pics, anim, device)

    @staticmethod
    def have(map_id: int, root: Path = ROOT) -> bool:
        return (Path(root) / str(map_id) / "scene.json").exists()

    # ---- the expected picture
    def _back_plane(self, b: dict, t, C, w: int, h: int):
        """(premultiplied BGRA float (h, w, 4)) of one background layer for camera C."""
        torch = self.torch
        ph, pw = t.shape[:2]
        sx, sy = back_pos(b, C, self.woff, self.hoff)
        xs = torch.arange(w, device=self.dev) - sx
        ys = torch.arange(h, device=self.dev) - sy
        if b["type"] in H_TILED:
            xs = xs % (b["cx"] or pw)
        if b["type"] in V_TILED:
            ys = ys % (b["cy"] or ph)
        okx, oky = (xs >= 0) & (xs < pw), (ys >= 0) & (ys < ph)
        plane = t[ys.clamp(0, ph - 1)][:, xs.clamp(0, pw - 1)]
        return plane * (oky[:, None] & okx[None, :])[..., None]

    def _crop(self, C, w: int, h: int):
        """The tile / object canvas for camera C, zero outside the rendered area: (h, w, 4) uint8."""
        torch = self.torch
        ax, ay = int(C[0]) - self.x0, int(C[1]) - self.y0
        ch, cw = self.canvas.shape[:2]
        out = torch.zeros((h, w, 4), dtype=torch.uint8, device=self.dev)
        x0, y0, x1, y1 = max(0, ax), max(0, ay), min(cw, ax + w), min(ch, ay + h)
        if x1 > x0 and y1 > y0:
            out[y0 - ay:y1 - ay, x0 - ax:x1 - ax] = self.canvas[y0:y1, x0:x1]
        return out

    def expected(self, C, w: int = W, h: int = PLAY_H) -> tuple:
        """What the frame's top `h` rows show for camera C where nothing moves: (bgr float tensor (h, w, 3), known
        bool tensor (h, w)). Known = covered by fixed scenery (opaque tiles / objects, or fixed backgrounds) and
        not by an animated object, a moving / animated background or a `front` background that isn't fixed."""
        torch = self.torch
        out = torch.zeros((h, w, 3), device=self.dev)
        cover = torch.zeros((h, w), device=self.dev)                 # how much fixed scenery covers the pixel
        unknown = torch.zeros((h, w), dtype=torch.bool, device=self.dev)

        def draw(b, t):
            nonlocal out, cover, unknown
            plane = self._back_plane(b, t, C, w, h)
            a = plane[..., 3:4] / 255.0
            if not b["known"]:
                unknown |= a[..., 0] > 0.02
                return
            out = out * (1 - a) + plane[..., :3]
            cover = cover * (1 - a[..., 0]) + a[..., 0]

        for b, t in self.backs:
            if not b["front"]:
                draw(b, t)
        sc = self._crop(C, w, h).float()
        a = sc[..., 3:4] / 255.0
        out = out * (1 - a) + sc[..., :3]
        cover = cover * (1 - a[..., 0]) + a[..., 0]
        unknown &= a[..., 0] < 0.98                                  # an unknown back behind opaque scenery: hidden
        if self.anim is not None:
            ax, ay = int(C[0]) - self.x0, int(C[1]) - self.y0
            an = torch.zeros((h, w), dtype=torch.bool, device=self.dev)
            ch, cw = self.anim.shape
            x0, y0, x1, y1 = max(0, ax), max(0, ay), min(cw, ax + w), min(ch, ay + h)
            if x1 > x0 and y1 > y0:
                an[y0 - ay:y1 - ay, x0 - ax:x1 - ax] = self.anim[y0:y1, x0:x1]
            unknown |= an
        for b, t in self.backs:
            if b["front"]:
                draw(b, t)
        return out, (cover > 0.98) & ~unknown

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
               min_share: float = 0.2):
        """The camera, from the last one (`C_guess`: looked for within 12 px, then `wide`) and / or a rough one
        (`seed`: the minimap's, within `wide`). A wrong offset matches ~2 % of the landmarks, the right one 40-95 %
        (40 %: a game window open over the scene), so `min_share` 0.2 tells them apart: None = not found (a camera
        that only resembles the last one is worse than none)."""
        for guess, radius in ((C_guess, 12), (C_guess, wide), (seed, wide)):
            if guess is None:
                continue
            r = self.register(frame, guess, radius, tol, h, mask)
            if r is not None and r[1] >= min_share:
                return r
        return None
