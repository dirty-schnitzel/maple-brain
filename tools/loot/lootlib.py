"""Shared helpers of the loot plan session's experiments (PLAN-loot.md; tools only, nothing on the live path).

    run_ticks(RUN)        -> the ticks that saved a frame, each with its camera (obs.scene_cam / facts.scene_cam / cam)
    frame(RUN, name)      -> the frame (BGR uint8), the capture's 1 px column error undone (tools/perc/frames.py)
    Items                 -> the client's item pictures (tools/loot/export_items.ps1 -> cw-data/export/Item)
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as _frames  # noqa: E402  (tools/perc/frames.py)

EXPORT = Path(r"C:\Users\Yoav\dev\cw-data\export\Item")
PLAY_H, SW = 700, 1366


def run_ticks(run) -> list:
    """[{n, t, frame, cam, me, mobs, obs}] of the ticks with a saved frame (cam None when the recording has none)."""
    out = []
    with open(Path(run) / "ticks.jsonl", encoding="utf-8") as f:
        for line in f:
            k = json.loads(line)
            if not k.get("frame"):
                continue
            o = k.get("obs") or {}
            fa = k.get("facts") or {}
            cam = o.get("scene_cam") or fa.get("scene_cam") or (o.get("cam") if o.get("cam_src") == "exact" else None)
            out.append({"n": k.get("n"), "t": o.get("t"), "frame": k["frame"], "cam": cam, "me": o.get("me"),
                        "seed": o.get("cam"),      # any camera of the recording (the old tracker's: up to ~40 px off)
                        "mobs": o.get("mobs") or [], "obs": o, "facts": fa})
    return out


def frame(run, name):
    return _frames.read(Path(run), name)


def map_of(run) -> int:
    return _frames.map_of(Path(run))


# the minimap window's measured rectangle per map (HANDOFF "DONE 2.3": the default 215 x 195 is wrong both ways; the
# live Perceiver takes it from the locator) + 3 px; Dark Cave not measured there: generous
MINIMAP = {10005063: (233, 201), 10003061: (280, 155), 10005065: (222, 201), 10003062: (178, 204), 10005064: (240, 205)}


def world_mask(map_id: int, shape) -> np.ndarray:
    """bool (PLAY_H, SW): True = game world (hud.ui_mask with the map's measured minimap rectangle, the chat rect as
    world: the user keeps the chat minimized)."""
    from maplebrain.perception import hud
    w, h = MINIMAP.get(int(map_id), (240, 205))
    m = hud.ui_mask(shape, (0, 0, w, h))[:PLAY_H] > 0
    x0, y0, x1, y1 = hud.CHAT_WORLD
    m[y0:min(y1, PLAY_H), x0:x1] = True
    return np.ascontiguousarray(m)


class Footholds:
    """A map's footholds (assets/mcw/maps/<id>/map.json): `under(mx, my)` -> (y, layer, id) of the nearest foothold
    at / below map (mx, my - 14) (a drop's bottom bobs a few px around its foothold), or None."""

    def __init__(self, map_id: int):
        mp = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        rows = []
        for k, f in (mp.get("footholds") or {}).items():
            if f["x1"] == f["x2"]:
                continue
            a = (f["x1"], f["y1"], f["x2"], f["y2"]) if f["x1"] < f["x2"] else (f["x2"], f["y2"], f["x1"], f["y1"])
            rows.append(a + (int(f.get("layerId", 0)), int(k)))
        self.fh = np.array(rows, float).reshape(-1, 6)

    def under(self, mx, my):
        F = self.fh
        on = np.flatnonzero((F[:, 0] <= mx) & (F[:, 2] >= mx))
        if not len(on):
            return None
        ya = F[on, 1] + (mx - F[on, 0]) * (F[on, 3] - F[on, 1]) / (F[on, 2] - F[on, 0])
        below = ya >= my - 14
        if not below.any():
            return None
        i = on[below][np.argmin(ya[below])]
        return float(ya[below].min()), int(F[i, 4]), int(F[i, 5])


class Items:
    """id (int) -> the drop pictures. `raw(id)` / `icon(id)` -> (BGRA uint8, (ox, oy)); mesos: `meso(n)` -> [(BGRA,
    (ox, oy), delay)] of size n (0 bronze, 1 gold, 2 bundle, 3 sack)."""

    def __init__(self, root: Path = EXPORT):
        self.root = Path(root)
        self.meta = json.loads((self.root / "items.json").read_text(encoding="utf-8-sig"))
        self._pics = {}

    def ids(self, kinds=None) -> list:
        return [int(i) for i, e in self.meta.items() if kinds is None or e["kind"] in kinds]

    def name(self, i) -> str:
        e = self.meta.get(f"{int(i):08d}") or {}
        return e.get("name") or f"{int(i):08d}"

    def kind(self, i) -> str:
        return (self.meta.get(f"{int(i):08d}") or {}).get("kind", "?")

    def _read(self, fn):
        if fn not in self._pics:
            self._pics[fn] = cv2.imread(str(self.root / "png" / fn), cv2.IMREAD_UNCHANGED)
        return self._pics[fn]

    def raw(self, i):
        e = self.meta.get(f"{int(i):08d}")
        if not e or "raw" not in e:
            return None
        return self._read(f"{int(i):08d}_raw.png"), (e["raw"][2], e["raw"][3])

    def icon(self, i):
        e = self.meta.get(f"{int(i):08d}")
        if not e or "icon" not in e:
            return None
        return self._read(f"{int(i):08d}_icon.png"), (e["icon"][2], e["icon"][3])

    def meso(self, n: int) -> list:
        e = self.meta[f"0900000{n}"]
        return [(self._read(f"0900000{n}_raw_{k}.png"), (fr[2], fr[3]), fr[4]) for k, fr in enumerate(e["frames"])]


def sheet(tiles, cols: int = 8, pad: int = 4, bg=(40, 40, 40), labels=None, scale: int = 1):
    """Tiles (BGR arrays, any sizes) -> one picture, `cols` per row; optional label per tile."""
    if not tiles:
        return np.zeros((10, 10, 3), np.uint8)
    if scale != 1:
        tiles = [cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST) for t in tiles]
    th = max(t.shape[0] for t in tiles) + (14 if labels else 0)
    tw = max(t.shape[1] for t in tiles)
    rows = -(-len(tiles) // cols)
    out = np.full((rows * (th + pad) + pad, cols * (tw + pad) + pad, 3), bg, np.uint8)
    for i, t in enumerate(tiles):
        y, x = pad + (i // cols) * (th + pad), pad + (i % cols) * (tw + pad)
        out[y:y + t.shape[0], x:x + t.shape[1]] = t[..., :3]
        if labels:
            cv2.putText(out, str(labels[i])[:tw // 6], (x, y + th - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
    return out
