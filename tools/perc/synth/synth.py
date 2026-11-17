"""Synthetic test frames with exact truth (PLAN-perception.md step 3.0b). Tools only: nothing on the live path.

A synthetic frame = a real native frame of a recording at its known camera (RUN/labels/cams.json) with
- its real mobs ERASED: every blob of D = frame - expected scene (scene.py) that is not our character (the blob at
  obs.me) and not under the UI is replaced by the expected scene (the scene explains 99.8 % of the pixels outside
  moving things, so the result is the frame as it would look without them). What can't be erased (our blob, the
  UI) is kept and marked: labelled mobs there become "unsure" spots, the blobs "dontcare" boxes;
- mobs drawn as the game draws them: the client sprite (assets/mcw/mobs, facing left; right = mirrored, origin
  x = w - ox), alpha x opacity, its origin (feet) on a foothold, on that foothold's layer: the layers above it
  (tiles / objects, rendered from the client export like scene.py does) drawn again over it. Pasted only where the
  erased frame shows bare scene (D empty), never over our blob or another pasted mob;
- then what lies over mobs in the game: damage digits (the client's Effect/BasicEff NoRed1 first digit + NoRed0),
  our character cut from other frames of the recording (D blob at obs.me: body, name tag, pet when beside it),
  the UI (quickslots / chat: the frame's own UI pixels re-drawn over the mob, opaque where they differ from the
  scene).
Truth per pasted mob (by construction): type, pose, facing, feet (screen px), opacity, onscreen share, visible
share and per-cause cover (s scenery / e effect / p player / u ui), classes as labels.json v2 spells them.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402

TOL = 4                                  # native PNG: scene pixels are exact or something else (step 0)
PLAY_H, SW = 700, 1366
CACHE = ROOT / "runs" / "synth" / "cache"
MOBS = ROOT / "assets" / "mcw" / "mobs"
MAPS = ROOT / "assets" / "mcw" / "maps"
# UI over the play area (hud.UI_RECTS; the minimap measured on Ant Tunnel IV 230x198). The minimap is see-through
# (mobs show through it), so the UI case uses only the chat and the quickslots.
UI_RECTS = [(0, 0, 240, 205), (1140, 45, 1366, 160), (285, 630, 850, 700), (930, 620, 1085, 700)]
UI_OVER = [(285, 630, 850, 700), (930, 620, 1085, 700)]
DIGIT_ADV = [24, 20, 22, 22, 24, 23, 24, 22, 24, 24]        # px per damage digit (HeavenClient's table)


def _clip(x, y, w, h, W=SW, H=PLAY_H):
    """Screen box (x, y, w, h) clipped: (dst x0, y0, x1, y1, src x0, y0) or None."""
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1, x0 - x, y0 - y


class Sprite:
    """One mob frame as the client draws it: straight-alpha BGRA, origin (feet)."""

    def __init__(self, mob: int, anim: str, i: int, im: np.ndarray, origin):
        self.mob, self.anim, self.i = mob, anim, i
        self.im = {"left": im, "right": np.ascontiguousarray(im[:, ::-1])}
        h, w = im.shape[:2]
        self.origin = {"left": (int(origin[0]), int(origin[1])), "right": (int(w - origin[0]), int(origin[1]))}

    @property
    def pose(self) -> str:
        return f"{self.anim}_{self.i}"


def load_sprites(mob: int) -> list:
    info = json.loads((MOBS / str(mob) / "mob.json").read_text(encoding="utf-8"))
    out = []
    for anim, fs in (info.get("frames") or {}).items():
        for i, f in enumerate(fs or []):
            im = cv2.imread(str(MOBS / str(mob) / f["file"]), cv2.IMREAD_UNCHANGED)
            if im is not None and im.ndim == 3 and im.shape[2] == 4 and (im[..., 3] > 0).sum() >= 60:
                out.append(Sprite(mob, anim, i, im, f.get("origin") or (im.shape[1] // 2, im.shape[0])))
    return out


def load_digits(export: Path) -> dict:
    """{"big": [(bgra, origin)] * 10, "small": ...}: the client's red damage digits (NoRed1 = the first, NoRed0)."""
    from maplebrain.gamedata import load_xml
    eff = Path(export) / "Effect"
    x = load_xml(eff / "BasicEff.img.xml")
    out = {}
    for key, node in (("big", "NoRed1"), ("small", "NoRed0")):
        out[key] = []
        for d in range(10):
            im = cv2.imread(str(eff / "png" / "BasicEff" / node / f"{d}.png"), cv2.IMREAD_UNCHANGED)
            o = (x.get(node) or {}).get(str(d), {}).get("origin") or (im.shape[1] // 2, im.shape[0])
            out[key].append((im, (int(o[0]), int(o[1]))))
    return out


def front_planes(map_id: int, layers, export: Path) -> dict:
    """layer L -> premultiplied BGRA uint8 canvas (scene.png's coordinates) of the tiles / objects of layers > L:
    what the game draws over a mob on layer L. Rendered once from the client export (scene.build_scene on the map's
    layers above L), cached in runs/synth/cache/<map>/front_L.png. (Step 3.2 builds its own per-layer planes in
    scene.py; this is the tool's.)"""
    from maplebrain.gamedata import load_xml
    from maplebrain.scene import _Parts, build_scene
    out, img, parts = {}, None, None
    for L in layers:
        f = CACHE / str(map_id) / f"front_{L}.png"
        if not f.exists():
            if img is None:
                src = next((Path(export) / "Map").glob(f"Map?/{int(map_id):09d}.img.xml"))
                img, parts = load_xml(src), _Parts(export, load_xml)
            m = json.loads((MAPS / str(map_id) / "map.json").read_text(encoding="utf-8"))
            canvas, _, meta = build_scene({str(k): img[str(k)] for k in range(L + 1, 8) if str(k) in img}, m, parts)
            f.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(f), canvas)
            (f.parent / f"front_{L}.json").write_text(json.dumps({"x0": meta["x0"], "y0": meta["y0"]}))
        out[L] = (cv2.imread(str(f), cv2.IMREAD_UNCHANGED), json.loads((f.parent / f"front_{L}.json").read_text()))
    return out


class Base:
    """A real frame with its real mobs erased (see the module doc)."""

    def __init__(self, n, frame, C, e, diff, keep, ui_alpha, dontcare, unsure, spots):
        self.n, self.frame, self.C, self.e = n, frame, C, e
        self.spots = spots                # every labelled mob / unsure spot of the real frame (screen feet)
        self.diff = diff                  # (700, 1366) the ORIGINAL frame's D (|frame - e| > TOL on known scenery)
        self.keep = keep                  # (700, 1366) kept blobs (our character; unerasable): never paste under
        self.ui_alpha = ui_alpha          # (700, 1366) float: the UI drawn here (opaque where it differs from e;
                                          # a real mob under the UI differs too: such rects aren't used, ui_free)
        self.dontcare, self.unsure = dontcare, unsure


class Synth:
    def __init__(self, run, export: Path | None = None, tracks: str = "replay/work.jsonl"):
        """`run`: a run folder, a corpus segment RECORDING#K, or a frames.Clip of either (labels.json and
        labels/cams.json are looked for in the clip's work folder, then in the recording's own; our position per
        frame comes from its ticks.jsonl, or - a `record` walk - from the replay `tracks`)."""
        from maplebrain.gamedata import EXPORT
        from maplebrain.scene import Scene
        self.clip = run if isinstance(run, rec.Clip) else rec.clip(run, tool="synth")
        self.run = self.clip.run
        self.export = Path(export or EXPORT)
        self.map_id = self.clip.map_id
        self.scene = Scene.load(self.map_id)
        self.cams = json.loads(self.clip.find("labels/cams.json").read_text())
        lab = json.loads(self.clip.find("labels.json").read_text())
        self.labels = {int(n): f for n, f in lab["frames"].items()}
        self.me = {k["n"]: k["me"] for k in self.clip.sight(tracks) if k["n"] in self.labels}
        self.map = json.loads((MAPS / str(self.map_id) / "map.json").read_text(encoding="utf-8"))
        self.fh = [f for f in self.map["footholds"].values() if f["x1"] != f["x2"]]
        self.types = sorted({s["id"] for s in self.map["mobs"]})
        self.sprites = {t: load_sprites(t) for t in self.types}
        self.front = front_planes(self.map_id, sorted({f["layerId"] for f in self.fh}), self.export)
        self.digits = load_digits(self.export)
        self._players = None

    # ---- the base frame
    def base(self, n: int) -> Base | None:
        import torch
        name = f"{n:06d}.png"
        C = self.cams.get(name)
        frame = rec.read(self.run, name)
        if C is None or frame is None:
            return None
        e, known = self.scene.expected(C)
        e = e.clamp(0, 255).round().to(torch.uint8).cpu().numpy()
        known = known.cpu().numpy()
        diff = (np.abs(frame[:PLAY_H].astype(np.int16) - e).max(axis=2) > TOL) & known
        ui = np.zeros((PLAY_H, SW), bool)
        for x0, y0, x1, y1 in UI_RECTS:
            ui[y0:y1, x0:x1] = True
        bad = diff & ~ui
        core = cv2.erode(bad.astype(np.uint8), np.ones((3, 3), np.uint8))
        blob = cv2.dilate(core, np.ones((13, 13), np.uint8))
        nc, lab, st, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
        me = self.me.get(n)
        pbox = (me[0] - 40, me[1] - 85, me[0] + 40, me[1] + 30) if me else None
        out = frame.copy()
        keep = np.zeros((PLAY_H, SW), bool)
        grow = cv2.dilate(diff.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        dontcare = []
        for i in range(1, nc):
            x, y, w, h, _ = (int(v) for v in st[i])
            comp = lab == i
            ours = pbox is not None and x < pbox[2] and x + w > pbox[0] and y < pbox[3] and y + h > pbox[1]
            low = y + h >= PLAY_H - 2 and x < 285          # continues below the play area where nothing is modelled
            if ours or low:
                keep |= comp
                dontcare.append([x - 10, y - 10, x + w + 10, y + h + 10])
            else:
                m = comp & grow & ~ui
                out[:PLAY_H][m] = e[m]
        ui_alpha = (ui & diff).astype(np.float32)
        dontcare += [[x0, y0, x1, y1] for x0, y0, x1, y1 in UI_RECTS if (ui_alpha[y0:y1, x0:x1] > 0).any()]
        L = self.labels.get(n, {"mobs": [], "unsure": []})
        unsure, spots = [], [m["feet"] for m in L["mobs"]] + list(L.get("unsure") or [])
        for p in spots:
            if any(b[0] <= p[0] <= b[2] and b[1] - 30 <= p[1] <= b[3] + 30 for b in dontcare) or p[1] >= PLAY_H - 10:
                unsure.append([int(p[0]), int(p[1])])
        return Base(n, out, tuple(C), e, diff, keep, ui_alpha, dontcare, unsure, spots)

    @staticmethod
    def ui_free(base: "Base", rect) -> bool:
        """No real mob of the base frame under / at this UI rect (its D there would pass for UI)."""
        x0, y0, x1, y1 = rect
        return not any(x0 - 60 <= p[0] <= x1 + 60 and y0 - 20 <= p[1] <= y1 + 80 for p in base.spots)

    # ---- players cut from the recording
    def players(self) -> list:
        """[(bgra uint8, anchor (x, y) = obs.me inside it)]: our character's D blob in labelled frames with no
        labelled mob / unsure spot within 160 px (nothing but us in it). Cached."""
        if self._players is not None:
            return self._players
        f = CACHE / str(self.map_id) / "players.npz"
        if f.exists():
            z = np.load(f)
            self._players = [(z[f"im{i}"], tuple(z[f"a{i}"])) for i in range(int(z["n"]))]
            return self._players
        out = []
        for n in sorted(self.labels):
            me, L = self.me.get(n), self.labels[n]
            if not me or any(abs(p[0] - me[0]) < 160 and abs(p[1] - me[1]) < 160
                             for p in [m["feet"] for m in L["mobs"]] + list(L.get("unsure") or [])):
                continue
            b = self.base(n)
            if b is None:
                continue
            frame = rec.read(self.run, f"{n:06d}.png")
            m = (b.keep & b.diff).astype(np.uint8)
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
            nc, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(m, np.ones((9, 9), np.uint8)))
            pick = np.zeros_like(m, bool)
            for i in range(1, nc):
                x, y, w, h, _ = st[i]
                if x < me[0] + 40 and x + w > me[0] - 40 and y < me[1] + 30 and y + h > me[1] - 85:
                    pick |= lab == i
            pick &= m > 0
            ys, xs = np.nonzero(pick)
            if len(xs) < 400 or xs.min() <= 0 or xs.max() >= SW - 1 or ys.min() <= 0 or ys.max() >= PLAY_H - 1:
                continue
            x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
            if x1 - x0 > 140 or y1 - y0 > 120:
                continue                                    # another player / a mob's tooltip joined our blob
            im = np.dstack([frame[y0:y1, x0:x1], pick[y0:y1, x0:x1].astype(np.uint8) * 255])
            out.append((im, (int(me[0] - x0), int(me[1] - y0))))
            if len(out) >= 24:
                break
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(f, n=len(out), **{f"im{i}": im for i, (im, _) in enumerate(out)},
                            **{f"a{i}": np.array(a) for i, (_, a) in enumerate(out)})
        self._players = out
        return out

    # ---- footholds
    def foothold_point(self, C, rng, sx_range=(0, SW), sy_range=(40, PLAY_H)):
        """A random point (map x, y) on a foothold, its screen x in `sx_range` and y in `sy_range` (length-weighted
        over what of each foothold lies there), or None."""
        cand, lens = [], []
        for f in self.fh:
            a, b = sorted((f["x1"] - C[0], f["x2"] - C[0]))
            a, b = max(a, sx_range[0]), min(b, sx_range[1])
            ym = (f["y1"] + f["y2"]) / 2 - C[1]
            if b > a and sy_range[0] <= ym < sy_range[1]:
                cand.append((f, a, b))
                lens.append(b - a)
        if not cand:
            return None
        f, a, b = cand[rng.choice(len(cand), p=np.array(lens) / sum(lens))]
        x = rng.uniform(a, b) + C[0]
        y = f["y1"] + (x - f["x1"]) * (f["y2"] - f["y1"]) / (f["x2"] - f["x1"])
        return int(round(x)), int(round(y)), f

    # ---- drawing
    def fa_at(self, layer: int, C, x: int, y: int, w: int, h: int) -> np.ndarray:
        """(h, w) alpha 0..1 of what is drawn over a mob on `layer` at screen box (x, y, w, h)."""
        canvas, o = self.front[layer]
        ax, ay = x + int(C[0]) - o["x0"], y + int(C[1]) - o["y0"]
        out = np.zeros((h, w, 4), np.float32)
        r = _clip(ax, ay, w, h, canvas.shape[1], canvas.shape[0])
        if r is not None:
            x0, y0, x1, y1, sx, sy = r
            out[sy:sy + y1 - y0, sx:sx + x1 - x0] = canvas[y0:y1, x0:x1]
        return out


class Mob:
    """A pasted mob: its sprite's alpha over its box and what covers each pixel (filled while drawing)."""

    def __init__(self, sp: Sprite, facing: str, feet, opacity: float, layer: int):
        self.sp, self.facing, self.feet, self.opacity, self.layer = sp, facing, feet, opacity, layer
        im = sp.im[facing]
        ox, oy = sp.origin[facing]
        self.h, self.w = im.shape[:2]
        self.x, self.y = feet[0] - ox, feet[1] - oy                  # screen top-left
        self.a = im[..., 3].astype(np.float32) / 255.0
        yy, xx = np.mgrid[self.y:self.y + self.h, self.x:self.x + self.w]
        self.on = (xx >= 0) & (xx < SW) & (yy >= 0) & (yy < PLAY_H)
        self.cover = {c: np.zeros((self.h, self.w), np.float32) for c in "sepu"}

    def add_cover(self, cls: str, alpha_screen: np.ndarray):
        """Something of class `cls` drawn over the screen with alpha `alpha_screen` (700, 1366)."""
        r = _clip(self.x, self.y, self.w, self.h)
        if r is None:
            return
        x0, y0, x1, y1, sx, sy = r
        c = self.cover[cls][sy:sy + y1 - y0, sx:sx + x1 - x0]
        a = alpha_screen[y0:y1, x0:x1]
        c[...] = 1 - (1 - c) * (1 - a)

    def truth(self, mob_type: int) -> dict:
        a = self.a
        tot = float(a.sum())
        on = a * self.on
        son = float(on.sum())
        free = np.ones_like(a)
        cov = {}
        for c, m in self.cover.items():
            cov[c] = round(float((on * m).sum()) / max(son, 1e-6), 3)
            free *= 1 - m
        cls = ""
        if self.opacity < 0.95:
            cls += "f"
        if self.sp.anim.startswith("die"):
            cls += "d"
        if self.sp.anim.startswith("hit"):
            cls += "h"
        if son / tot < 0.95:
            cls += "x"
        for c, bar in (("s", 0.05), ("e", 0.03), ("p", 0.03), ("u", 0.03)):
            if cov[c] >= bar:
                cls += c
        return {"feet": [int(self.feet[0]), int(self.feet[1])], "type": int(mob_type), "cls": cls,
                "pose": self.sp.pose, "facing": self.facing, "opacity": round(self.opacity, 3),
                "onscreen": round(son / tot, 3), "vis": round(float((on * free).sum()) / tot, 3), "cover": cov,
                "layer": self.layer, "box": [int(self.x), int(self.y), int(self.w), int(self.h)]}


def draw_mob(img: np.ndarray, base: Base, syn: Synth, mob: Mob, under_ui: bool = False):
    """Draw `mob` into `img` (the frame being built) the way the client does: behind = the frame without what is
    drawn over the mob's layer (recovered: frame = F + (1 - fa) * behind), mob over it with alpha x opacity, the
    layers above re-drawn. `under_ui`: where the UI is drawn the scene behind comes from the expected picture."""
    r = _clip(mob.x, mob.y, mob.w, mob.h)
    if r is None:
        return
    x0, y0, x1, y1, sx, sy = r
    F = syn.fa_at(mob.layer, base.C, x0, y0, x1 - x0, y1 - y0)
    fa = F[..., 3:4] / 255.0
    src = img[y0:y1, x0:x1].astype(np.float32)
    if under_ui:
        u = base.ui_alpha[y0:y1, x0:x1, None] > 0
        src = np.where(u, base.e[y0:y1, x0:x1].astype(np.float32), src)
    behind = np.where(fa < 0.995, (src - F[..., :3]) / np.maximum(1 - fa, 1e-3), src)
    S = mob.sp.im[mob.facing][sy:sy + y1 - y0, sx:sx + x1 - x0].astype(np.float32)
    a = S[..., 3:4] / 255.0 * mob.opacity
    out = F[..., :3] + (1 - fa) * (a * S[..., :3] + (1 - a) * behind)
    img[y0:y1, x0:x1] = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    mob.cover["s"][sy:sy + y1 - y0, sx:sx + x1 - x0] = fa[..., 0]


def paste(img: np.ndarray, rgba: np.ndarray, x: int, y: int, opacity: float = 1.0) -> np.ndarray:
    """Straight-alpha BGRA `rgba` over `img` at screen (x, y) -> its alpha on the screen (700, 1366)."""
    al = np.zeros((PLAY_H, SW), np.float32)
    r = _clip(x, y, rgba.shape[1], rgba.shape[0])
    if r is None:
        return al
    x0, y0, x1, y1, sx, sy = r
    s = rgba[sy:sy + y1 - y0, sx:sx + x1 - x0].astype(np.float32)
    a = s[..., 3:4] / 255.0 * opacity
    img[y0:y1, x0:x1] = np.clip(a * s[..., :3] + (1 - a) * img[y0:y1, x0:x1] + 0.5, 0, 255).astype(np.uint8)
    al[y0:y1, x0:x1] = a[..., 0]
    return al


def damage_number(syn: Synth, value: int) -> np.ndarray:
    """The client's red damage number as one straight-alpha BGRA picture (first digit big, the rest small, every
    second one 2 px lower); anchor = its centre bottom."""
    ds = [int(c) for c in str(value)]
    parts, x = [], 0
    for i, d in enumerate(ds):
        im, (ox, oy) = syn.digits["big" if i == 0 else "small"][d]
        parts.append((im, x - ox, -oy + (2 if i % 2 else 0)))
        x += DIGIT_ADV[d] + (2 if i == 0 else 0)
    x0 = min(p[1] for p in parts)
    y0 = min(p[2] for p in parts)
    x1 = max(p[1] + p[0].shape[1] for p in parts)
    y1 = max(p[2] + p[0].shape[0] for p in parts)
    P = np.zeros((y1 - y0, x1 - x0, 3), np.float32)             # premultiplied colour
    A = np.zeros((y1 - y0, x1 - x0, 1), np.float32)
    for im, px, py in parts:
        h, w = im.shape[:2]
        s = im.astype(np.float32)
        a = s[..., 3:4] / 255.0
        sl = (slice(py - y0, py - y0 + h), slice(px - x0, px - x0 + w))
        P[sl] = s[..., :3] * a + P[sl] * (1 - a)
        A[sl] = a + A[sl] * (1 - a)
    rgb = P / np.maximum(A, 1e-3)
    can = A * 255
    return np.dstack([np.clip(rgb, 0, 255), can[..., 0]]).astype(np.uint8)
