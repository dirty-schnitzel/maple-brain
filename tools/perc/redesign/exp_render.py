"""E2: render a map's static scenery (tiles + objects, every layer) from the client export and compare with recorded
frames at the logged camera: how exactly does it register, how much of the frame does it explain?
    python exp_render.py build            -> scratchpad/ant4_render.png (+ alpha), map coordinates
    python exp_render.py check RUN [N]    -> registration offsets + explained share on N frames of RUN
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(r"C:\Users\Yoav\dev\maple-work")
sys.path.insert(0, str(ROOT))
from maplebrain.gamedata import EXPORT, load_xml  # noqa: E402

HERE = Path(__file__).parent
MAP = 10005063
PAD = 200


class Parts:
    def __init__(self):
        self.sets, self.pics = {}, {}

    def _set(self, kind, name):
        key = (kind, name)
        if key not in self.sets:
            p = EXPORT / "Map" / kind / f"{name}.img.xml"
            self.sets[key] = load_xml(p) if p.exists() else None
        return self.sets[key]

    def frame0(self, kind, name, path):
        """(bgra, origin, z) of the first frame at `path`."""
        node = self._set(kind, name)
        for part in path:
            node = node.get(str(part)) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return None
        if "_size" in node:
            k, c, base = str(path[-1]), node, path[:-1]
        else:
            items = sorted((int(k), v) for k, v in node.items() if k.isdigit() and isinstance(v, dict) and "_size" in v)
            if not items:
                return None
            k, c, base = str(items[0][0]), items[0][1], path
        f = EXPORT / "Map" / kind / "png" / name / Path(*map(str, base)) / f"{k}.png"
        if f not in self.pics:
            self.pics[f] = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        im = self.pics[f]
        if im is None or im.ndim != 3 or im.shape[2] != 4:
            return None
        return im, tuple(c.get("origin") or (0, 0)), c.get("z", 0), len([1 for kk in node if str(kk).isdigit()]) if "_size" not in node else 1


def paste(canvas, im, x, y, x0, y0):
    h, w = im.shape[:2]
    ax, ay = int(x) - x0, int(y) - y0
    sx0, sy0 = max(0, -ax), max(0, -ay)
    dx0, dy0 = max(0, ax), max(0, ay)
    dx1, dy1 = min(canvas.shape[1], ax + w), min(canvas.shape[0], ay + h)
    if dx1 <= dx0 or dy1 <= dy0:
        return
    src = im[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0].astype(np.float32)
    a = src[..., 3:4] / 255
    dst = canvas[dy0:dy1, dx0:dx1]
    dst[..., :3] = src[..., :3] * a + dst[..., :3] * (1 - a)
    dst[..., 3:4] = np.maximum(dst[..., 3:4], src[..., 3:4])


def build():
    img = load_xml(EXPORT / "Map" / "Map0" / f"{MAP:09d}.img.xml")
    m = json.loads((ROOT / "assets" / "mcw" / "maps" / str(MAP) / "map.json").read_text(encoding="utf-8"))
    fh = list(m["footholds"].values())
    xs = [v for f in fh for v in (f["x1"], f["x2"])]
    ys = [v for f in fh for v in (f["y1"], f["y2"])]
    vr = m["vrBounds"]
    x0, y0 = int(min(xs + [vr["left"]])) - PAD, int(min(ys + [vr["top"]])) - PAD
    x1, y1 = int(max(xs + [vr["right"]])) + PAD, int(max(ys + [vr["bottom"]])) + PAD
    canvas = np.zeros((y1 - y0, x1 - x0, 4), np.float32)
    parts = Parts()
    n_obj = n_tile = n_anim = 0
    for L in range(8):
        lay = img.get(str(L)) or {}
        objs = []
        for o in (lay.get("obj") or {}).values():
            if isinstance(o, dict) and o.get("oS"):
                fr = parts.frame0("Obj", o["oS"], [o.get("l0"), o.get("l1"), o.get("l2")])
                if fr is not None:
                    objs.append((o.get("z", 0), o.get("zM", 0), o, fr))
        objs.sort(key=lambda t: (t[0], t[1]))
        for _, _, o, (im, (ox, oy), _, nfr) in objs:
            if o.get("f", 0):
                im, ox = im[:, ::-1], im.shape[1] - ox
            paste(canvas, im, o.get("x", 0) - ox, o.get("y", 0) - oy, x0, y0)
            n_obj += 1
            n_anim += nfr > 1
        tS = (lay.get("info") or {}).get("tS")
        tiles = []
        for t in (lay.get("tile") or {}).values():
            if isinstance(t, dict) and tS:
                fr = parts.frame0("Tile", tS, [t.get("u"), t.get("no")])
                if fr is not None:
                    tiles.append((fr[2] if fr[2] else t.get("zM", 0), t.get("zM", 0), t, fr))
        tiles.sort(key=lambda t: (t[0], t[1]))
        for _, _, t, (im, (ox, oy), _, _) in tiles:
            paste(canvas, im, t.get("x", 0) - ox, t.get("y", 0) - oy, x0, y0)
            n_tile += 1
    backs = [(k, b.get("bS"), b.get("no"), b.get("type"), b.get("rx"), b.get("ry"), b.get("front"), b.get("ani"))
             for k, b in (img.get("back") or {}).items() if isinstance(b, dict)]
    print(f"render {canvas.shape[1]}x{canvas.shape[0]} at ({x0},{y0}): {n_obj} objects ({n_anim} animated), {n_tile} tiles; "
          f"opaque {float((canvas[..., 3] > 128).mean()):.2%}")
    print("backs:", backs)
    cv2.imwrite(str(HERE / "ant4_render.png"), canvas.astype(np.uint8))
    (HERE / "ant4_render.json").write_text(json.dumps({"x0": x0, "y0": y0}))


def check(run, n=40):
    R = cv2.imread(str(HERE / "ant4_render.png"), cv2.IMREAD_UNCHANGED)
    meta = json.loads((HERE / "ant4_render.json").read_text())
    L = [json.loads(l) for l in open(ROOT / run / "ticks.jsonl", encoding="utf-8")]
    L = [l for l in L if l.get("frame") and l["obs"].get("cam")]
    step = max(1, len(L) // n)
    offs, expl = [], []
    for l in L[::step][:n]:
        f = cv2.imread(str(ROOT / run / "frames" / l["frame"]))
        cx, cy = l["obs"]["cam"]
        ax, ay = int(round(cx)) - meta["x0"], int(round(cy)) - meta["y0"]
        S = 40                                                    # search +-S px around the logged camera
        ref = R[ay - S:ay + 600 + S, ax - S:ax + 1366 + S]
        if ref.shape[0] != 600 + 2 * S or ref.shape[1] != 1366 + 2 * S:
            continue
        # register on a central window: masked match of the frame part against the render
        fy0, fy1, fx0, fx1 = 200, 560, 300, 1100
        tpl = f[fy0:fy1, fx0:fx1]
        # template = the frame crop; search image = render (alpha as weight is not supported for the search image,
        # so match the other way round: render crop as the template with its alpha as the mask)
        rt = np.ascontiguousarray(ref[S + fy0:S + fy1, S + fx0:S + fx1])
        mask = np.repeat((rt[..., 3:4] > 200).astype(np.uint8) * 255, 3, 2)
        if mask[..., 0].mean() < 20:
            continue
        area = np.ascontiguousarray(f[fy0 - S:fy1 + S, fx0 - S:fx1 + S])
        r = cv2.matchTemplate(area, np.ascontiguousarray(rt[..., :3]), cv2.TM_CCORR_NORMED, mask=mask)
        r = np.nan_to_num(r, nan=-1, posinf=-1, neginf=-1)
        _, sc, _, (lx, ly) = cv2.minMaxLoc(r)
        dx, dy = lx - S, ly - S                                    # the frame is at +(dx, dy) of where the cam says
        # explained share at the registered offset: render pixels (opaque) within 30 grey levels of the frame
        rr = R[ay - dy:ay - dy + 600, ax - dx:ax - dx + 1366]
        op = rr[..., 3] > 200
        diff = np.abs(rr[..., :3].astype(np.int16) - f[:600].astype(np.int16)).max(2)
        ok = (diff <= 30) & op
        offs.append((dx, dy, sc))
        expl.append((float(op.mean()), float(ok.sum() / max(1, op.sum())),
                     float(((diff <= 4) & op).sum() / max(1, op.sum()))))
        if len(offs) == 5:
            vis = f[:600].copy()
            vis[ok] = (0, 0, 0)                                    # explained pixels blacked out: what's left?
            cv2.imwrite(str(HERE / "render_residual.png"), np.hstack([f[:600], rr[..., :3], vis])[:, ::1])
    offs, expl = np.array(offs), np.array(expl)
    print(f"{run}: {len(offs)} frames")
    print("  offset frame vs logged camera, px: dx p5/p50/p95", np.percentile(offs[:, 0], [5, 50, 95]),
          "dy", np.percentile(offs[:, 1], [5, 50, 95]), "score p5/p50", np.percentile(offs[:, 2], [5, 50]).round(3))
    print("  scenery (opaque render) share of the play area p50", np.median(expl[:, 0]).round(3),
          "; of it, within 30 grey levels of the frame p5/p50/p95", np.percentile(expl[:, 1], [5, 50, 95]).round(3),
          "; within 4 (1:1 picture, PNG frames only)", np.percentile(expl[:, 2], [5, 50, 95]).round(3))


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        check(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 40)
