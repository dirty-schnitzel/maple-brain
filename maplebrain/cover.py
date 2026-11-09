"""What the game draws in front of mobs (the user, 2026-11-04: "two large grass patches completely hide the Pigs").

A map has 8 layers (0-7), drawn bottom to top; each holds tiles and objects. Mobs (players, NPCs) are drawn on the
layer of the foothold they stand on, after that layer's tiles/objects (HeavenClient Stage::draw: per layer tiles +
objects, then reactors, NPCs, mobs, characters). So every tile/object of a HIGHER layer is painted over them.

Build (`assets build`): per mob layer L (a layer some foothold is on), the union of the opaque pixels (alpha >= 128)
of every tile and object (all frames of animated ones) on layers > L -> maps/<id>/cover_<L>.png in map coordinates
(map.json "cover": x0, y0, w, h, layers). 255 = covered.
Run time: `Cover.visible(layer, C)` = the play area's pixels a mob on that layer can be seen at (screen = map - C).
Background layers drawn in front (back front=1) aren't in the masks yet (counted at build: `front_backs`).
"""
import json
from pathlib import Path

import cv2
import numpy as np

PAD = 200            # px of map around the footholds / vrBounds the mask covers
ALPHA = 128


# ------------------------------------------------------------------ build (from the client export)
class _Parts:
    """Obj / Tile pictures + origins from the export (Map/Obj, Map/Tile: export.ps1), cached."""

    def __init__(self, export: Path, load_xml):
        self.export, self.load_xml = Path(export), load_xml
        self.sets, self.pics = {}, {}

    def _set(self, kind, name):
        key = (kind, name)
        if key not in self.sets:
            p = self.export / "Map" / kind / f"{name}.img.xml"
            self.sets[key] = self.load_xml(p) if p.exists() else None
        return self.sets[key]

    def frames(self, kind, name, path) -> list:
        """[(alpha mask uint8 bool, origin)] of every frame under set `name` at `path` (obj: [l0, l1, l2]; tile:
        [u, no] -> that one canvas)."""
        node = self._set(kind, name)
        for part in path:
            node = node.get(str(part)) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return []
        if "_size" in node:                                   # a canvas itself (tiles)
            items = [(str(path[-1]), node)]
            base = path[:-1]
        else:
            items = [(k, v) for k, v in node.items() if k.isdigit() and isinstance(v, dict) and "_size" in v]
            base = path
        out = []
        for k, c in items:
            f = self.export / "Map" / kind / "png" / name / Path(*map(str, base)) / f"{k}.png"
            if f not in self.pics:
                im = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
                self.pics[f] = None if im is None or im.ndim != 3 or im.shape[2] != 4 else im[..., 3] >= ALPHA
            if self.pics[f] is not None:
                out.append((self.pics[f], tuple(c.get("origin") or (0, 0))))
        return out


def _paste(mask, alpha, x, y, x0, y0):
    h, w = alpha.shape
    ax, ay = int(x) - x0, int(y) - y0
    sx0, sy0 = max(0, -ax), max(0, -ay)
    dx0, dy0 = max(0, ax), max(0, ay)
    dx1, dy1 = min(mask.shape[1], ax + w), min(mask.shape[0], ay + h)
    if dx1 > dx0 and dy1 > dy0:
        mask[dy0:dy1, dx0:dx1] |= alpha[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0]


def build_cover(img: dict, m: dict, parts: _Parts) -> tuple:
    """One exported map image + its map.json -> (meta for map.json["cover"] | None, {layer: mask uint8 0/255})."""
    fh = list((m.get("footholds") or {}).values())
    if not fh:
        return None, {}
    mob_layers = sorted({f["layerId"] for f in fh})
    xs = [v for f in fh for v in (f["x1"], f["x2"])]
    ys = [v for f in fh for v in (f["y1"], f["y2"])]
    vr = m.get("vrBounds") or {}
    x0 = int(min(xs + [vr.get("left", min(xs))])) - PAD
    y0 = int(min(ys + [vr.get("top", min(ys))])) - PAD
    x1 = int(max(xs + [vr.get("right", max(xs))])) + PAD
    y1 = int(max(ys + [vr.get("bottom", max(ys))])) + PAD
    per_layer = {}                                            # layer -> its own drawn pixels
    for L in range(8):
        lay = img.get(str(L)) or {}
        mask = np.zeros((y1 - y0, x1 - x0), bool)
        tS = (lay.get("info") or {}).get("tS")
        for t in (lay.get("tile") or {}).values():
            if not isinstance(t, dict) or not tS:
                continue
            for a, (ox, oy) in parts.frames("Tile", tS, [t.get("u"), t.get("no")]):
                _paste(mask, a, t.get("x", 0) - ox, t.get("y", 0) - oy, x0, y0)
        for o in (lay.get("obj") or {}).values():
            if not isinstance(o, dict) or not o.get("oS"):
                continue
            flip = bool(o.get("f", 0))
            for a, (ox, oy) in parts.frames("Obj", o["oS"], [o.get("l0"), o.get("l1"), o.get("l2")]):
                if flip:
                    a = a[:, ::-1]
                    ox = a.shape[1] - ox
                _paste(mask, a, o.get("x", 0) - ox, o.get("y", 0) - oy, x0, y0)
        if mask.any():
            per_layer[L] = mask
    masks = {}
    for L in mob_layers:
        over = [per_layer[k] for k in per_layer if k > L]
        if over:
            masks[L] = (np.logical_or.reduce(over) * 255).astype(np.uint8)
    front = sum(1 for b in (img.get("back") or {}).values() if isinstance(b, dict) and b.get("front"))
    if not masks and not front:
        return None, {}
    meta = {"x0": x0, "y0": y0, "w": x1 - x0, "h": y1 - y0, "layers": sorted(masks), "front_backs": front,
            "covered": {str(L): round(float((v > 0).mean()), 4) for L, v in masks.items()}}
    return meta, masks


def write_cover(d: Path, masks: dict) -> None:
    for L, v in masks.items():
        cv2.imwrite(str(Path(d) / f"cover_{L}.png"), v, [cv2.IMWRITE_PNG_COMPRESSION, 9])


# ------------------------------------------------------------------ run time
class Cover:
    def __init__(self, meta: dict, masks: dict, footholds: dict):
        self.x0, self.y0 = meta["x0"], meta["y0"]
        self.masks = {int(L): (v == 0) for L, v in masks.items()}   # True = visible
        self.layer_of_fh = {int(k): f["layerId"] for k, f in footholds.items()}
        self._cache = {}

    @classmethod
    def for_map(cls, map_id: int, root: Path) -> "Cover | None":
        d = Path(root) / "maps" / str(map_id)
        m = json.loads((d / "map.json").read_text(encoding="utf-8"))
        meta = m.get("cover")
        if not meta or not meta.get("layers"):
            return None
        masks = {L: cv2.imread(str(d / f"cover_{L}.png"), cv2.IMREAD_GRAYSCALE) for L in meta["layers"]}
        return cls(meta, {L: v for L, v in masks.items() if v is not None}, m["footholds"])

    def layer(self, platform_id) -> int | None:
        """The drawing layer of a platform (navmap platform ids are their first foothold's id)."""
        return self.layer_of_fh.get(int(platform_id)) if platform_id is not None else None

    def visible(self, layer, C, w: int = 1366, h: int = 700) -> np.ndarray | None:
        """(h, w) bool: where on screen a mob on `layer` can be seen (False = something is drawn in front). None: no
        cover for that layer (all visible). Cached per rounded camera offset."""
        m = self.masks.get(layer)
        if m is None or C is None:
            return None
        cx, cy = int(round(C[0])), int(round(C[1]))
        key = (layer, cx, cy, w, h)
        if key not in self._cache:
            if len(self._cache) > 8:
                self._cache.clear()
            out = np.ones((h, w), bool)
            ax, ay = cx - self.x0, cy - self.y0                       # screen (0, 0) in mask pixels
            sx0, sy0 = max(0, ax), max(0, ay)
            sx1, sy1 = min(m.shape[1], ax + w), min(m.shape[0], ay + h)
            if sx1 > sx0 and sy1 > sy0:
                out[sy0 - ay:sy1 - ay, sx0 - ax:sx1 - ax] = m[sy0:sy1, sx0:sx1]
            self._cache[key] = out
        return self._cache[key]

    def visible_share(self, layer, C, box) -> float:
        """Share of the screen box (x, y, w, h) a mob on `layer` can be seen in (1.0 = nothing in front)."""
        v = self.visible(layer, C)
        if v is None:
            return 1.0
        x, y, w, h = (int(round(a)) for a in box)
        x0, y0, x1, y1 = max(0, x), max(0, y), min(v.shape[1], x + w), min(v.shape[0], y + h)
        if x1 <= x0 or y1 <= y0:
            return 1.0
        return float(v[y0:y1, x0:x1].mean())
