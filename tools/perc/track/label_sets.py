"""PLAN-tracker step 1: THE LABEL SETS BY EYE (L1-L8) - the cases picked from the prototypes' output so that every
class is in them, shown as crops for a look, the judgments written into the bank's labels folder, and the second
look's agreement. Nothing here is product code; the reference is the look, never a tool.

    python tools/perc/track/label_sets.py mobs CAP [CAP ...] | --sound    proto_mobs v5 run, its rows kept (L1-3, L8)
    python tools/perc/track/label_sets.py pick SET [SET ...] [--seed 1]   the cases + their sheets (SET = L1 .. L8)
    python tools/perc/track/label_sets.py redo SET [SET ...] [--nb 30]    try 2: the same cases, sheets anew, a new second look
    python tools/perc/track/label_sets.py ropes                           try 3 of L1: the cases near a rope, with strips (L1R)
    python tools/perc/track/label_sets.py write SET [SET ...]             judged/SET_a.jsonl -> CORPUS/labels/CAP/labels/SET.json
    python tools/perc/track/label_sets.py agree [SET ...] [--judged DIR]  the second look (SET_b) against the first
    python tools/perc/track/label_sets.py check [SET ...]                 every set's files read back by label_eval.py

Where things go: the cases and the sheets (re-creatable) in CORPUS/work/track-plan/labels/SET/: cases.json, a_NNN.png
= the sheets of the first look (case numbers 0..), b_NNN.png = 10 % of the cases again in another order, numbered
anew (b_cases.json maps them back: the second look reads only the b sheets). The judgments (by eye, kept in git) in
tools/perc/track/judged/SET_a.jsonl and SET_b.jsonl, one line per case: {"case": k, ...the set's fields, below}. The
labels: CORPUS/labels/SESSION#K/labels/SET.json, labels.json v2 (tools/perc/labels/label.py) - "mobs" / "unsure" /
"false" per frame, the set's own fields beside them - so label_eval.py reads each one:
    label_eval.py SESSION#K --labels labels/SET.json --tracks track/today.jsonl    (`check` writes today.jsonl:
    world.py's tracks of the kept replay on the labelled frames)

THE SETS (PLAN-tracker.md step 1). Places are written as tokens: "s<node>" standing on that node (a chain: its id =
its leftmost foothold's id, drawn cyan with the id at its left end), "a" in the air, "f" flying, "r<node>" on a rope /
ladder (magenta, "r-1" ...), "n" not a mob / no such thing, "?" cannot tell.
  L1  200 frames: us and every mob, the place and the node.  {"e": {"U": "s12", "1": "a", "2": "s45", ...},
      "add": [[sx, sy, "s45"]]}  - every numbered thing judged; "add" = a mob with no number (screen feet).
  L2  100 covered mobs: what covers them.  {"cover": "effect|mob|us|player|drop|ui|scenery|edge|none|gone|?"}
      (none = in plain view, gone = nothing there and nothing over the place)
  L3  50 births: how born.  {"how": "fade|view|uncover|entry|dying|notmob|?"}
  L4  100 hit-pose begins: by us or not.  {"who": "us|other|?", "pose": "hit|die|none|?"}
  L5  200 frames: every name tag's class, each player's node.  {"tags": {"1": "ours", "2": "player s45", "3": "pet",
      "4": "log", "5": "mob", "6": "npc", "7": "text", "8": "none", "9": "?"}}
  L6  50 drops: the mob it came from.  {"from": "A|B|...|none|?"}
  L7  100 frames: the 8 slots' item and amount.  {"slots": {"shift": "JUMP", "insert": "Pet Food 100", "home":
      "empty", ...}}  (names as on the legend sheet, the amount as drawn; "?" unreadable)
  L8  40 remembered mobs: there / not there / cannot tell.  {"there": "yes|no|?"}
"""
import argparse
import json
import math
import pickle
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import cache  # noqa: E402
import dump  # noqa: E402

CORPUS = Path(r"F:\dev\maple-corpus")
WORK = CORPUS / "work" / "track-plan" / "labels"
JUDGED = HERE / "judged"
BY = "Claude, by eye (PLAN-tracker step 1, 2026-11-24)"
SW, PLAY_H = 1366, 700
YELLOW, GREEN, RED, CYAN, MAG, WHITE, ORANGE = (0, 230, 255), (0, 220, 0), (0, 0, 255), (255, 220, 0), (255, 0, 255), \
    (255, 255, 255), (0, 140, 255)
LETTERS = "ABCDEFGHIJ"


def mobs_path(cap) -> Path:
    return WORK / "mobs" / f"{cap.replace('#', '_')}.pkl"


# ------------------------------------------------------------------------------------------------ proto_mobs v5 run
def run_mobs(cap):
    """proto_mobs v5 (Cfg defaults) over the capture; rows kept with what the label sets need: per track its
    born_how, the possible set's ends (map x), the frame it was last seen on. Also the episodes and the ends."""
    import proto_mobs as P

    def rows(self, t, orig=P.Tracker._rows):
        out = orig(self, t)
        by = {tr.id: tr for tr in self.tracks}
        for m in out:
            tr = by[m["id"]]
            m["born_how"], m["born"], m["n_seen_at"], m["pose"] = tr.born_how, round(tr.born, 3), tr.n_seen_at, tr.pose
            m["conf"] = tr.conf
            if tr.poss is not None and not tr.seen and tr.poss.any():
                px = tr.gx[tr.poss]
                m["can"] = [int(px.min()), int(px.max())]
                if tr.poss.ndim == 2:
                    py = tr.gy[tr.poss]
                    m["can_y"] = [int(py.min()), int(py.max())]
        return out
    P.Tracker._rows = rows
    rs, trk, ms = P.run(cap, P.Cfg())
    p = mobs_path(cap)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps({"rows": rs, "episodes": trk.episodes, "ended": trk.ended},
                               protocol=pickle.HIGHEST_PROTOCOL))
    print(cap, len(rs), "rows,", len(trk.episodes), "episodes ->", p, flush=True)


_MOBS = {}


def mobs(cap) -> dict:
    if cap not in _MOBS:
        d = pickle.loads(mobs_path(cap).read_bytes())
        d["by_n"] = {r["n"]: r for r in d["rows"]}
        _MOBS[cap] = d
    return _MOBS[cap]


# ------------------------------------------------------------------------------------------------ shared: a capture
class Cap:
    """One capture's kept replay (rows by frame number), its frames, its map (the fixed chains of tools/model)."""
    _cache = {}

    def __new__(cls, cap):
        if cap not in cls._cache:
            o = super().__new__(cls)
            o._init(cap)
            cls._cache[cap] = o
        return cls._cache[cap]

    def _init(self, cap):
        import frames as rec
        from load import Map, map_of
        self.cap, self.rec = cap, rec
        self.clip = dump.clip_of(cap)
        self.rows = dump.rows(cap)
        self.by_n = {r["n"]: i for i, r in enumerate(self.rows)}
        self.map = Map(map_of(cap))
        self.nav = self.map.nav
        sys.path.insert(0, str(ROOT / "tools" / "model"))
        from chains_fixed import chains
        fh = {int(k): v for k, v in self.map.json["footholds"].items()}
        self.chains = {ch[0]: [(fh[i]["x1"], fh[i]["y1"], fh[i]["x2"], fh[i]["y2"]) for i in ch] for ch in chains(fh)}
        self.ropes = {-1 - i: r for i, r in enumerate(self.nav.ropes)}
        self.T = np.array([r["t"] for r in self.rows])

    def row(self, n):
        return self.rows[self.by_n[n]]

    def at_t(self, t):
        """The row nearest time t."""
        i = int(np.clip(np.searchsorted(self.T, t), 0, len(self.T) - 1))
        if i > 0 and abs(self.T[i - 1] - t) < abs(self.T[i] - t):
            i -= 1
        return self.rows[i]

    def img(self, n):
        return self.rec.read(self.clip.run, self.row(n)["frame"])

    def surface(self, x, y, tol=3.0):
        """(chain id, surface y) of the chain under x whose surface is nearest y within tol, else None."""
        best = None
        for cid, segs in self.chains.items():
            for x1, y1, x2, y2 in segs:
                if x1 <= x <= x2:
                    ys = y1 + (y2 - y1) * (x - x1) / max(1, x2 - x1)
                    if abs(ys - y) <= tol and (best is None or abs(ys - y) < abs(best[1] - y)):
                        best = (cid, ys)
        return best

    def on_rope(self, x, y, tol=6):
        for rid, r in self.ropes.items():
            if abs(r.x - x) <= tol and r.top - tol <= y <= r.bottom + tol:
                return rid
        return None


# ------------------------------------------------------------------------------------------------ drawing
def text(img, s, x, y, col=YELLOW, scale=0.45, th=1):
    import cv2
    cv2.putText(img, s, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), th + 2, cv2.LINE_AA)
    cv2.putText(img, s, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, scale, col, th, cv2.LINE_AA)


def ids_along(cap: Cap, img, p, every):
    """Each chain's id on every visible piece of it: at the start of each stretch of it inside the image, then
    again every `every` px along it; each rope's "r<id>" at the top of its visible part and every `every` px down.
    p = map -> image px. (The sheets of the first try printed a chain's id at its left end only: on a long slope or
    with the left end out of the picture the labeller could not tell which line a mob stood on.)"""
    H, W = img.shape[:2]

    def inside(x, y):
        return 0 <= x < W and 4 <= y < H - 4

    for cid, segs in cap.chains.items():
        last, prev_in = None, False
        for x1, y1, x2, y2 in segs:
            a, b = p(x1, y1), p(x2, y2)
            L = max(1.0, math.hypot(b[0] - a[0], b[1] - a[1]))
            for s in np.arange(0, L + 0.5, 3.0):
                x, y = a[0] + (b[0] - a[0]) * s / L, a[1] + (b[1] - a[1]) * s / L
                if not inside(x, y):
                    prev_in = False
                    continue
                if not prev_in or last is None or math.hypot(x - last[0], y - last[1]) >= every:
                    s_ = str(cid)
                    tx = min(max(2, x + 2), W - 9 * len(s_) - 2)
                    ty = y + 13 if y + 13 < H - 2 else y - 4
                    text(img, s_, tx, ty, CYAN, 0.4)
                    last = (x, y)
                prev_in = True
    for rid, r in cap.ropes.items():
        a, b = p(r.x, r.top), p(r.x, r.bottom)
        if not 0 <= a[0] < W:
            continue
        y0, y1 = max(a[1], 0), min(b[1], H)
        for y in np.arange(y0, y1, every):
            text(img, f"r{rid}", min(a[0] + 4, W - 40), max(14, y + 14), MAG, 0.4)


def draw_graph(cap: Cap, img, C, z=1.0, ox=0.0, oy=0.0, alpha=0.6, ids=True, every=180):
    """The chains (cyan, id at the left end; ids="every": on every visible piece, `ids_along`) and ropes (magenta,
    "r<id>" at the top) on an image whose pixel (0, 0) is map (C[0] + ox, C[1] + oy) scaled by z. Lines 1 px wide,
    drawn after any zoom."""
    import cv2
    ov = img.copy()

    def p(x, y):
        return int(round((x - C[0] - ox) * z)), int(round((y - C[1] - oy) * z))
    H, W = img.shape[:2]
    for cid, segs in cap.chains.items():
        for x1, y1, x2, y2 in segs:
            cv2.line(ov, p(x1, y1), p(x2, y2), CYAN, 1)
    for rid, r in cap.ropes.items():
        cv2.line(ov, p(r.x, r.top), p(r.x, r.bottom), MAG, 1)
    cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, img)
    if ids == "every":
        ids_along(cap, img, p, every)
    elif ids:
        for cid, segs in cap.chains.items():
            (a, b), (c, _) = p(segs[0][0], segs[0][1]), p(segs[-1][2], segs[-1][3])
            if c < 0 or a > W or not -10 < b < H + 10:
                continue
            text(img, str(cid), max(2, a) + 2, b + 13, CYAN, 0.4)
        for rid, r in cap.ropes.items():
            a, b = p(r.x, r.top)
            _, b2 = p(r.x, r.bottom)
            if 0 <= a < W and b2 > 0 and b < H:
                text(img, f"r{rid}", a + 4, max(14, b + 14), MAG, 0.4)


def crop(img, sx, sy, w, h, zoom=1.0, fill=(60, 0, 60)):
    """The w x h box centred on screen (sx, sy), padded where it leaves the frame, scaled by zoom."""
    import cv2
    pad = cv2.copyMakeBorder(img, h, h, w, w, cv2.BORDER_CONSTANT, value=fill)
    x0, y0 = int(sx) + w - w // 2, int(sy) + h - h // 2
    x0, y0 = min(max(0, x0), pad.shape[1] - w), min(max(0, y0), pad.shape[0] - h)
    cr = np.ascontiguousarray(pad[y0:y0 + h, x0:x0 + w])
    if zoom != 1.0:
        cr = cv2.resize(cr, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    return cr


def mark(img, x, y, col=YELLOW, kind="cross", size=12):
    import cv2
    m = {"cross": cv2.MARKER_CROSS, "x": cv2.MARKER_TILTED_CROSS, "tri": cv2.MARKER_TRIANGLE_UP,
         "diamond": cv2.MARKER_DIAMOND}[kind]
    cv2.drawMarker(img, (int(x), int(y)), (0, 0, 0), m, size + 2, 3)
    cv2.drawMarker(img, (int(x), int(y)), col, m, size, 1)


def tick(img, x, y, col=YELLOW, w=12):
    """Two short ticks level with the feet point, a gap over the point itself (the feet stay visible)."""
    import cv2
    cv2.line(img, (int(x - w), int(y)), (int(x - 4), int(y)), col, 1)
    cv2.line(img, (int(x + 4), int(y)), (int(x + w), int(y)), col, 1)


def hstack(tiles, gap=4):
    h = max(t.shape[0] for t in tiles)
    return np.hstack([np.pad(t, ((0, h - t.shape[0]), (0, gap), (0, 0)), constant_values=40) for t in tiles])


def vstack(tiles, gap=6):
    w = max(t.shape[1] for t in tiles)
    return np.vstack([np.pad(t, ((0, gap), (0, w - t.shape[1]), (0, 0)), constant_values=40) for t in tiles])


def grid(tiles, cols, gap=4):
    return vstack([hstack(tiles[i:i + cols], gap) for i in range(0, len(tiles), cols)], gap)


def header(s, w, h=24, col=WHITE):
    import cv2
    im = np.full((h, w, 3), 25, np.uint8)
    cv2.putText(im, s, (6, h - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1, cv2.LINE_AA)
    return im


def write_png(path: Path, img):
    import cv2
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def place_crop(cap: Cap, n, mx, my, w, h, zoom, graph=False):
    """A crop around MAP place (mx, my) on frame n (None: no camera / frame). -> (image, (sx, sy) of the place in it)."""
    r = cap.row(n)
    if r["C"] is None:
        return None, None
    img = cap.img(n)
    if img is None:
        return None, None
    C = r["C"]
    sx, sy = mx - C[0], my - C[1]
    cr = crop(img, sx, sy, w, h, zoom)
    if graph:
        draw_graph(cap, cr, C, zoom, sx - w // 2, sy - h // 2, ids=True)
    return cr, (w // 2 * zoom, h // 2 * zoom)


def blank(w, h, s="no frame"):
    im = np.full((h, w, 3), (60, 0, 60), np.uint8)
    text(im, s, 8, 20, WHITE)
    return im


# ------------------------------------------------------------------------------------------------ the sets
SETS = {}


def a_set(cls):
    SETS[cls.name] = cls
    return cls


def balanced(rnd, pools: dict, quota: dict, key=lambda c: (c["cap"], c["n"])) -> list:
    """quota[class] cases out of pools[class], round robin over the captures, every frame once."""
    out, used = [], set()
    for cls, q in quota.items():
        by = defaultdict(list)
        for c in pools.get(cls, []):
            by[c["cap"]].append(c)
        for v in by.values():
            rnd.shuffle(v)
        order = sorted(by)
        rnd.shuffle(order)
        got = 0
        while got < q and any(by[o] for o in order):
            for o in order:
                while by[o]:
                    c = by[o].pop()
                    if key(c) in used:
                        continue
                    used.add(key(c))
                    c["class"] = cls
                    out.append(c)
                    got += 1
                    break
                if got >= q:
                    break
        if got < q:
            print(f"  {cls}: only {got} of {q}")
    return out


def thin(cands, gap_s=2.0):
    """Cases of one capture at least gap_s apart."""
    out, last = [], {}
    for c in sorted(cands, key=lambda c: (c["cap"], c["t"])):
        if c["t"] - last.get(c["cap"], -1e9) >= gap_s:
            out.append(c)
            last[c["cap"]] = c["t"]
    return out


class LabelSet:
    """A set: its cases (picked; each a dict with "cap", "n", "t", "class" and what its sheet needs), the sheets,
    the labels written from the judgments, the items compared between two looks."""
    name, size, per_sheet = "", 0, 1

    def __init__(self, seed=1):
        self.rnd = random.Random(seed)

    def dir(self) -> Path:
        return WORK / self.name

    def pick(self) -> list:
        raise NotImplementedError

    def tile(self, c: dict, k: int):
        raise NotImplementedError

    def frame_entry(self, c: dict, j: dict) -> dict:
        """The judged case as a labels.json v2 frame entry: {"mobs", "unsure", "false", ...the set's fields}."""
        raise NotImplementedError

    def items(self, c: dict, j: dict) -> dict:
        """{item: value} - one item per thing judged, for the agreement of two looks."""
        raise NotImplementedError

    def sheets(self, cases, prefix):
        import cv2
        for old in self.dir().glob(f"{prefix}_*.png"):
            old.unlink()
        out = []
        for i in range(0, len(cases), self.per_sheet):
            tiles = [self.tile(c, k) for k, c in enumerate(cases[i:i + self.per_sheet], start=i)]
            p = self.dir() / f"{prefix}_{i // self.per_sheet:03d}.png"
            write_png(p, vstack(tiles, 10))
            out.append(p)
        return out


# ---- L1: us and every mob, the place and the node
@a_set
class L1(LabelSet):
    name, size = "L1", 200
    quota = {"mob air": 55, "mob fly": 20, "us rope": 35, "us air": 30, "plain": 60}

    def pick(self):
        pools = defaultdict(list)
        for cap in cache.SOUND:
            cp, mb = Cap(cap), mobs(cap)
            fly = {i for i, m in cp.map.mobs.items() if (m.get("frames") or {}).get("fly")}
            for r in cp.rows[30::7]:
                if r["C"] is None or r["facts"].get("fit") is None:
                    continue
                c = {"cap": cap, "n": r["n"], "t": r["t"]}
                fit = r["facts"]["fit"]
                if any(m["type"] in fly and 0 <= m["feet"][0] < SW and 0 <= m["feet"][1] < PLAY_H for m in fit):
                    pools["mob fly"].append(c)
                pr = mb["by_n"].get(r["n"])
                if pr and any(m["air"] and m["src"] == "acq" and m["state"] == "live" and m["mob"] not in fly
                              and 20 <= m["sx"] < SW - 20 and 40 <= m["sy"] < PLAY_H for m in pr["mobs"]):
                    pools["mob air"].append(c)
                if r["me_map"] is not None:
                    x, y = r["me_map"]
                    on = cp.surface(x, y - 1, 3) or cp.surface(x, y, 3)
                    if on is None and cp.on_rope(x, y) is not None:
                        pools["us rope"].append(c)
                    elif on is None:
                        pools["us air"].append(c)
                pools["plain"].append(c)
        pools = {k: thin(v, 3.0) for k, v in pools.items()}
        print({k: len(v) for k, v in pools.items()})
        cases = balanced(self.rnd, pools, self.quota)
        for c in cases:
            r = Cap(c["cap"]).row(c["n"])
            c["C"] = list(r["C"])
            c["me"] = None if r["me"] is None else [float(r["me"][0]), float(r["me"][1]) - 1]
            c["fit"] = [{"type": m["type"], "pose": m["pose"], "feet": m["feet"], "opacity": m["opacity"],
                         "seen": m["seen"]} for m in r["facts"]["fit"]]
        return cases

    def tile(self, c, k):
        import cv2
        cp = Cap(c["cap"])
        img = cp.img(c["n"])
        C = c["C"]
        full = img[:PLAY_H].copy()
        draw_graph(cp, full, C, ids="every", every=220)
        ents = ([("U", c["me"], GREEN)] if c["me"] else []) + [(str(i + 1), m["feet"], YELLOW) for i, m in enumerate(c["fit"])]
        for name, (x, y), col in ents:
            tick(full, x, y, col)
            text(full, name, x + 13, y + 4, col, 0.5)
        tiles = []
        # 150 x 130 px of the frame at x2.5: 85 px over the feet, 45 under (the try-1 crops showed 13 under, so the
        # platform under a mob was often cut off with its id); every visible piece of a line carries its id
        Z, W, H, UP = 2.5, 150, 130, 20
        for name, (x, y), col in ents:
            cr = crop(img, x, y - UP, W, H, Z)
            draw_graph(cp, cr, C, Z, x - W // 2, y - UP - H // 2, alpha=0.45, ids="every", every=150)
            fx, fy = W // 2 * Z, (H // 2 + UP) * Z
            tick(cr, fx, fy, col, 22)
            text(cr, name, 6, 22, col, 0.7, 2)
            tiles.append(cr)
        head = header(f"{self.name} case {k}   ({c['cap']} n {c['n']})   judge U + every number: s<node> / a / f / r<node> / "
                      f"n / ?; add any mob with no number", full.shape[1])
        parts = [head, full]
        if tiles:
            parts.append(grid(tiles, 4))
        for name, (x, y), col in ents:
            if name in c.get("rope", ()):
                parts.append(self.strip(cp, c, name, x + C[0], y + C[1], col))
        return vstack(parts, 4)

    def strip(self, cp, c, name, mx, my, col):
        """Try 3 (near a rope): the frames 0.2 s before to 0.2 s after the case's frame, every 3rd, around the
        thing's MAP place on the case's frame (the camera's moves taken out); the lines' and ropes' ids drawn along
        them; the case's frame red-bordered with the feet ticked."""
        import cv2
        Z, W, H, UP = 1.25, 150, 130, 20
        i0 = cp.by_n[c["n"]]
        tiles = []
        for i in range(i0 - 12, i0 + 13, 3):
            if not 0 <= i < len(cp.rows):
                continue
            r = cp.rows[i]
            cr, _ = place_crop(cp, r["n"], mx, my - UP, W, H, Z)
            if cr is None:
                tiles.append(blank(int(W * Z), int(H * Z)))
                continue
            Cr = r["C"]
            draw_graph(cp, cr, Cr, Z, mx - Cr[0] - W // 2, my - UP - Cr[1] - H // 2, alpha=0.45, ids="every", every=120)
            if i == i0:
                tick(cr, W // 2 * Z, (H // 2 + UP) * Z, col, 14)
                cv2.rectangle(cr, (0, 0), (cr.shape[1] - 1, cr.shape[0] - 1), RED, 2)
            text(cr, f"{r['t'] - c['t']:+.2f} s", 4, 14, RED if i == i0 else WHITE, 0.42)
            tiles.append(cr)
        return vstack([header(f"{name}: 0.2 s before to 0.2 s after (red = this case's frame, its feet ticked)",
                              len(tiles) * (int(W * Z) + 4), 22, col), hstack(tiles)], 2)

    def frame_entry(self, c, j):
        def tok(v):
            v = (v or "?").split()
            p = v[0]
            cls = v[1] if len(v) > 1 else ""
            if p.startswith("s"):
                return "stand", int(p[1:]), cls
            if p.startswith("r"):
                return "rope", int(p[1:]), cls
            return {"a": "air", "f": "fly", "n": "none", "?": "?"}[p], None, cls
        mobs_, unsure, false = [], [], []
        e = j.get("e") or {}
        for i, m in enumerate(c["fit"]):
            pl, node, cls = tok(e.get(str(i + 1)))
            if pl == "none":
                false.append(m["feet"])
            elif pl == "?":
                unsure.append(m["feet"])
            else:
                mobs_.append({"feet": m["feet"], "type": m["type"], "cls": cls, "place": pl, "node": node})
        for a in j.get("add") or []:
            pl, node, cls = tok(a[2])
            mobs_.append({"feet": [a[0], a[1]], "type": a[3] if len(a) > 3 else None, "cls": cls, "place": pl,
                          "node": node, "added": True})
        us = None
        if c["me"]:
            pl, node, _ = tok(e.get("U"))
            us = {"feet": c["me"], "place": pl, "node": node}
        return {"mobs": mobs_, "unsure": unsure, "false": false, "us": us, "class": c["class"]}

    def items(self, c, j):
        e = j.get("e") or {}
        out = {f"e{key}": (e.get(key) or "?").split()[0] for key in ["U"] * bool(c["me"]) + [str(i + 1) for i in range(len(c["fit"]))]}
        out["adds"] = len(j.get("add") or [])
        return out


@a_set
class L1R(L1):
    """Try 3 of L1 (the user, 2026-11-24): the L1 cases where we or a mob stand within ROPE px of a rope / ladder
    (sideways; between its top and its bottom + ROPE) - labelled again from sheets that add a strip of frames around
    each such thing (a labeller saw one frame; the tracker places by motion). "l1" = the L1 case; "rope" = the
    things near a rope. The second look = these cases among L1's second-look sample. `judged("L1")` takes these
    judgments over try 2's for these cases."""
    name, size = "L1R", 0
    ROPE = 20

    def pick(self):
        L = WORK / "L1"
        cases = json.loads((L / "cases.json").read_text(encoding="utf-8"))
        out = []
        for k, c in enumerate(cases):
            cp, C = Cap(c["cap"]), c["C"]
            ents = ([("U", c["me"])] if c["me"] else []) + [(str(i + 1), m["feet"]) for i, m in enumerate(c["fit"])]
            near = [n for n, (x, y) in ents if any(abs(r.x - x - C[0]) <= self.ROPE and r.top <= y + C[1] <= r.bottom + self.ROPE
                                                  for r in cp.ropes.values())]
            if near:
                out.append(dict(c, l1=k, rope=near))
        return out


def cmd_ropes(seed):
    """L1R: its cases, the a sheets in a new order (numbered anew), the b sheets = its cases in L1's second look."""
    S = SETS["L1R"](seed)
    S.dir().mkdir(parents=True, exist_ok=True)
    cases = S.pick()
    random.Random(seed + 300).shuffle(cases)
    (S.dir() / "cases.json").write_text(json.dumps(cases, indent=0), encoding="utf-8")
    l1b = set(json.loads((WORK / "L1" / "b_cases.json").read_text(encoding="utf-8")))
    bi = [i for i, c in enumerate(cases) if c["l1"] in l1b]
    random.Random(seed + 400).shuffle(bi)
    (S.dir() / "b_cases.json").write_text(json.dumps(bi), encoding="utf-8")
    pa, pb = S.sheets(cases, "a"), S.sheets([cases[i] for i in bi], "b")
    print(f"L1R: {len(cases)} cases ({sum(len(c['rope']) for c in cases)} things near a rope), sheets {len(pa)} a + "
          f"{len(pb)} b ({len(bi)} cases)")


# ---- the possible-set sheets of L2 and L8
def mem_cases(cap, kinds):
    """Remembered track-frames in view of proto_mobs v5, with the episode they belong to. -> [case]."""
    mb = mobs(cap)
    out = []
    eps = {}
    for e in mb["episodes"]:
        eps.setdefault(e[0], []).append(e)
    for r in mb["rows"][::5]:
        for m in r["mobs"]:
            if m["src"] != "none" or m["state"] not in kinds or "can" not in m or m["unseen"] < 0.15:
                continue
            ep = next((e for e in eps.get(m["id"], []) if e[1] is not None and e[1] < r["n"] <= e[2]), None)
            if ep is None:
                continue
            out.append({"cap": cap, "n": r["n"], "t": r["t"], "id": m["id"], "mob": m["mob"], "x": m["x"], "y": m["y"],
                        "can": m["can"], "can_y": m.get("can_y"), "cover": m["cover"], "unseen": m["unseen"],
                        "seen_n": ep[1], "end_n": ep[2], "seen_xy": [ep[3], ep[4]], "end": ep[5],
                        "again_xy": None if ep[8] is None else [ep[8], ep[9]]})
    return out


def mem_tile(self, c, k, what):
    cp = Cap(c["cap"])
    W, H, Z = 300, 200, 1.5
    mx, my = c["x"], c["y"]
    ns = [c["seen_n"], c["n"]]
    later = cp.at_t(c["t"] + 0.4)["n"]
    if what == "L2" and c["again_xy"] is not None:
        ns.append(c["end_n"])
    else:
        ns.append(later)
    tiles = []
    for j, n in enumerate(ns):
        cr, (fx, fy) = place_crop(cp, n, mx, my, W, H, Z)
        if cr is None:
            tiles.append(blank(int(W * Z), int(H * Z)))
            continue
        C = cp.row(n)["C"]
        ox, oy = mx - C[0] - W // 2, my - C[1] - H // 2

        def s(x, y):
            return (x - C[0] - ox) * Z, (y - C[1] - oy) * Z
        if j == 0:
            a = s(*c["seen_xy"])
            tick(cr, *a, GREEN, 22)
            mark(cr, a[0], a[1] - 30 * Z, GREEN, "x", 16)
            text(cr, "last seen (green x over it)", 6, 40, GREEN)
        elif j == 1:
            import cv2
            if c["can_y"]:
                a, b = s(c["can"][0], c["can_y"][0]), s(c["can"][1], c["can_y"][1])
                cv2.rectangle(cr, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), YELLOW, 1)
            else:
                a, b = s(c["can"][0], my + 3), s(c["can"][1], my + 3)
                cv2.line(cr, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), YELLOW, 2)
            text(cr, "THIS FRAME: where it can be (yellow)", 6, 40, YELLOW)
        else:
            if what == "L2" and c["again_xy"] is not None:
                a = s(*c["again_xy"])
                tick(cr, *a, GREEN, 22)
                mark(cr, a[0], a[1] - 30 * Z, GREEN, "x", 16)
                text(cr, "seen again (green x)", 6, 40, GREEN)
            else:
                text(cr, "0.4 s later", 6, 40, WHITE)
        text(cr, f"n {n}", 6, 18, WHITE)
        tiles.append(cr)
    name = cp.map.names.get(c["mob"], c["mob"])
    q = ("what covers it: effect / mob / us / player / drop / ui / scenery / edge / none / gone / ?" if what == "L2"
         else "is it there in the yellow range on the middle frame: yes / no / ?")
    return vstack([header(f"{what} case {k}  {name}  ({c['cap']} n {c['n']})  - {q}", 1370), hstack(tiles)], 2)


@a_set
class L2(LabelSet):
    name, size, per_sheet = "L2", 100, 3
    quota = {"effect": 20, "mob": 20, "us": 15, "player": 15, "ui / scenery": 15, "drop": 5, "out of view": 10}

    def pick(self):
        pools = defaultdict(list)
        for cap in cache.SOUND:
            for c in mem_cases(cap, ("hidden", "offscreen")):
                if c["end"] == "seen again":
                    pools[c["cover"]].append(c)
        pools = {k: thin(v, 1.0) for k, v in pools.items()}
        print({k: len(v) for k, v in pools.items()})
        q = dict(self.quota)
        short = sum(max(0, n - len(pools.get(k, []))) for k, n in q.items())
        q["effect"] += short // 2
        q["mob"] += short - short // 2
        return balanced(self.rnd, pools, q, key=lambda c: (c["cap"], c["n"], c["id"]))

    def tile(self, c, k):
        return mem_tile(self, c, k, "L2")

    def frame_entry(self, c, j):
        return {"mobs": [{"feet": [c["x"] - Cap(c["cap"]).row(c["n"])["C"][0], c["y"] - Cap(c["cap"]).row(c["n"])["C"][1]],
                          "type": c["mob"], "cls": "", "cover": j["cover"], "track": c["id"], "can": c["can"]}],
                "unsure": [], "false": [], "class": c["class"]}

    def items(self, c, j):
        return {"cover": j["cover"]}


@a_set
class L8(LabelSet):
    name, size, per_sheet = "L8", 40, 3
    quota = {"seen again": 16, "found gone": 8, "limit": 16}

    def pick(self):
        pools = defaultdict(list)
        for cap in cache.SOUND:
            for c in mem_cases(cap, ("hidden",)):
                e = c["end"]
                k = ("seen again" if e == "seen again" else "found gone" if e.startswith("gone: its places")
                     else "limit" if e.startswith(("gone: drawn", "left")) and "out of view" not in e else None)
                if k:
                    pools[k].append(c)
        pools = {k: thin(v, 1.5) for k, v in pools.items()}
        print({k: len(v) for k, v in pools.items()})
        return balanced(self.rnd, pools, self.quota, key=lambda c: (c["cap"], c["n"], c["id"]))

    def tile(self, c, k):
        return mem_tile(self, c, k, "L8")

    def frame_entry(self, c, j):
        C = Cap(c["cap"]).row(c["n"])["C"]
        return {"mobs": [{"feet": [c["x"] - C[0], c["y"] - C[1]], "type": c["mob"], "cls": "", "there": j["there"],
                          "track": c["id"], "can": c["can"]}] if j["there"] == "yes" else [],
                "unsure": [[c["x"] - C[0], c["y"] - C[1]]] if j["there"] == "?" else [],
                "false": [[c["x"] - C[0], c["y"] - C[1]]] if j["there"] == "no" else [],
                "remembered": {"track": c["id"], "type": c["mob"], "can": c["can"], "there": j["there"]},
                "class": c["class"]}

    def items(self, c, j):
        return {"there": j["there"]}


# ---- L3: births
@a_set
class L3(LabelSet):
    name, size, per_sheet = "L3", 50, 3
    quota = {"faded in": 14, "came into view": 14, "uncovered": 12, "there at entry": 5, "dying": 5}

    def pick(self):
        pools = defaultdict(list)
        for cap in cache.SOUND:
            mb = mobs(cap)
            first, conf = {}, set()
            for r in mb["rows"]:
                for m in r["mobs"]:
                    if m["id"] not in first:
                        first[m["id"]] = (r, m)
                    if m["conf"]:
                        conf.add(m["id"])
            for tid, (r, m) in first.items():
                if tid in conf:
                    pools[m["born_how"]].append({"cap": cap, "n": r["n"], "t": r["t"], "id": tid, "mob": m["mob"],
                                                 "x": m["x"], "y": m["y"], "how": m["born_how"]})
        print({k: len(v) for k, v in pools.items()})
        return balanced(self.rnd, pools, self.quota, key=lambda c: (c["cap"], c["n"], c["id"]))

    def tile(self, c, k):
        cp = Cap(c["cap"])
        W, H, Z = 220, 170, 1.25
        tiles = []
        for dt in (-0.6, -0.3, -0.1, 0.0, 0.3):
            n = c["n"] if dt == 0 else cp.at_t(c["t"] + dt)["n"]
            cr, f = place_crop(cp, n, c["x"], c["y"], W, H, Z)
            if cr is None:
                tiles.append(blank(int(W * Z), int(H * Z)))
                continue
            if dt == 0:
                tick(cr, f[0], f[1], YELLOW, 18)
            text(cr, f"{dt:+.1f} s" if dt else "BORN", 6, 18, YELLOW if dt == 0 else WHITE)
            tiles.append(cr)
        name = cp.map.names.get(c["mob"], c["mob"])
        return vstack([header(f"L3 case {k}  {name}  ({c['cap']} n {c['n']})  - how born: fade / view / uncover / entry / "
                              f"dying / notmob / ?", 1390), hstack(tiles)], 2)

    def frame_entry(self, c, j):
        C = Cap(c["cap"]).row(c["n"])["C"]
        f = [c["x"] - C[0], c["y"] - C[1]]
        if j["how"] == "notmob":
            return {"mobs": [], "unsure": [], "false": [f], "birth": {"how": "notmob"}, "class": c["class"]}
        return {"mobs": [{"feet": f, "type": c["mob"], "cls": "f" if j["how"] == "fade" else "", "born_how": j["how"],
                          "track": c["id"]}] if j["how"] != "?" else [],
                "unsure": [f] if j["how"] == "?" else [], "false": [],
                "birth": {"how": j["how"], "track": c["id"]}, "class": c["class"]}

    def items(self, c, j):
        return {"how": j["how"]}


# ---- L4: hit-pose begins, by us or not
_WORLDS = {}


def world(cap):
    if cap not in _WORLDS:
        import proto_events as E
        _WORLDS[cap] = E.World(cap)
    return _WORLDS[cap]


@a_set
class L4(LabelSet):
    name, size, per_sheet = "L4", 100, 1          # try 2: one strip of ~60 frames a sheet
    caps = [cache.DESIGN, "20261120_235747_1#0"]
    quota = {"us hit": 25, "us die": 25, "another hit": 15, "another die": 15, "unknown": 20}

    def pick(self):
        pools = defaultdict(list)
        for cap in self.caps:
            w = world(cap)
            for e in w.evs:
                if e.kind == "hit" and not e.blow:
                    continue
                me = w.me_at(e.i)
                if me is None:
                    continue
                cls = "unknown" if e.who == "unknown" else f"{e.who} {e.kind}"
                pools[cls].append({"cap": cap, "n": w.frame_no(e.t), "t": float(e.t), "kind": e.kind, "who": e.who,
                                   "mob": int(e.life.kind), "x": float(e.x), "y": float(e.y), "me": [me[0], me[1]],
                                   "how": e.how})
        pools = {k: thin(v, 1.0) for k, v in pools.items()}
        print({k: len(v) for k, v in pools.items()})
        return balanced(self.rnd, pools, self.quota)

    STRIP = 1.0                      # s of frames from the key-down (the try-2 sheets: every frame)

    def prep(self, cases):
        """Try 2: each case gets the skill key's key-down its strip starts at, that skill's landing window
        (measurement 6: proto_events.LAND after the key-down) and the other key-downs inside the strip; the mob's
        life (its place on every frame). The key-down: the latest cast of ours whose landing window holds the pose's
        begin, else the latest cast in the 1.0 s before it, else the latest key-down of q / w / e in that second
        (a press that cast nothing), else none (the strip then runs from 0.8 s before the begin)."""
        import proto_events as E
        for c in cases:
            w = world(c["cap"])
            e = next(e for e in w.evs if abs(e.t - c["t"]) < 1e-6 and abs(e.x - c["x"]) < 1e-6)
            c["life"] = int(e.life.id)
            before = [x for x in w.casts if x.t <= e.t and e.t - x.t <= self.STRIP - 0.02]
            inw = [x for x in before if E.landing_window(x)[0] <= e.t <= E.landing_window(x)[1]]
            cast = (inw or before or [None])[-1]
            if cast is not None:
                c["kd"] = {"t": float(cast.t), "key": cast.key, "what": "cast" + (" (held key)" if cast.how == "held" else ""),
                           "land": [float(v) for v in E.landing_window(cast)]}
            else:
                pr = [p for p in w.presses if p[1] in E.LAND and p[0] <= e.t and e.t - p[0] <= self.STRIP - 0.02]
                c["kd"] = None if not pr else {"t": float(pr[-1][0]), "key": pr[-1][1], "what": f"no cast ({pr[-1][2]})",
                                               "land": [float(pr[-1][0] + v) for v in E.LAND[pr[-1][1]]]}
            t0 = c["kd"]["t"] if c["kd"] else c["t"] - 0.8
            c["t0"] = t0
            c["others"] = [[float(p[0]), p[1]] for p in w.presses if p[1] in E.LAND and t0 < p[0] <= t0 + self.STRIP
                           and not (c["kd"] and abs(p[0] - c["kd"]["t"]) < 1e-6)]
        return cases

    def tile(self, c, k):
        import cv2
        cp, w = Cap(c["cap"]), world(c["cap"])
        life = next(L for L in w.lives if L.id == c["life"])
        W, H, Z, COLS = 250, 160, 1.0, 6
        dx = c["me"][0] - c["x"]
        mx = c["x"] + dx / 2 if abs(dx) <= 200 else c["x"]
        my = c["y"] - 30
        t0, kd = c["t0"], c["kd"]
        land = kd["land"] if kd else None
        i0, i1 = w.idx(t0), w.idx(t0 + self.STRIP)
        i_pose = w.idx(c["t"])
        tiles = []
        for i in range(i0, i1 + 1):
            n = int(w.fr["n"][i])
            t = float(w.t[i])
            cr, _ = place_crop(cp, n, mx, my, W, H, Z)
            if cr is None:
                tiles.append(blank(W, H))
                continue
            C = cp.row(n)["C"]
            ox, oy = mx - C[0] - W // 2, my - C[1] - H // 2
            p = life.at(i, slack=6)
            if p is not None:
                mark(cr, (p[0] - C[0] - ox) * Z, (p[1] - C[1] - oy) * Z - 44, YELLOW, "x", 12)
            me = cp.row(n)["me_map"]
            if me is not None:
                mark(cr, (me[0] - C[0] - ox) * Z, (me[1] - C[1] - oy) * Z + 8, GREEN, "tri", 10)
            inl = land is not None and land[0] <= t <= land[1]
            lab = f"{t - t0:+.3f}"
            if kd and i == i0:
                lab += f"  KEY {kd['key']} DOWN"
            if i == i_pose:
                lab += "  POSE BEGINS"
            if any(abs(t - o[0]) < 0.0085 for o in c["others"]):
                lab += "  " + ",".join(f"{o[1]} down" for o in c["others"] if abs(t - o[0]) < 0.0085)
            text(cr, lab, 4, 14, RED if i == i_pose else YELLOW if inl else WHITE, 0.42)
            if inl:
                cv2.rectangle(cr, (0, 0), (cr.shape[1] - 1, cr.shape[0] - 1), YELLOW, 2)
            if i == i_pose:
                cv2.rectangle(cr, (2, 2), (cr.shape[1] - 3, cr.shape[0] - 3), RED, 2)
            tiles.append(cr)
        body = grid(tiles, COLS, 4)
        return vstack([header(f"L4 case {k}  ({c['cap']} n {c['n']})  - whose blow made the mob (yellow x) begin its pose: "
                              f"us / other / ?; pose: hit / die / none / ?", body.shape[1]),
                       self.timeline(c, body.shape[1]), body], 2)

    def timeline(self, c, Wd):
        """A bar over the strip: 0 .. 1.0 s from the key-down, the landing window (yellow), the key-down (green),
        other key-downs (grey, their key), the pose's begin (red)."""
        import cv2
        im = np.full((46, Wd, 3), 25, np.uint8)
        t0, kd = c["t0"], c["kd"]
        x0, x1 = 60, Wd - 20

        def X(t):
            return int(x0 + (x1 - x0) * (t - t0) / self.STRIP)
        cv2.line(im, (x0, 30), (x1, 30), WHITE, 1)
        for s in np.arange(0, self.STRIP + 1e-6, 0.1):
            cv2.line(im, (X(t0 + s), 26), (X(t0 + s), 34), WHITE, 1)
            text(im, f"{s:.1f}", X(t0 + s) - 8, 45, WHITE, 0.35)
        if kd:
            a, b = X(max(t0, kd["land"][0])), X(min(t0 + self.STRIP, kd["land"][1]))
            cv2.rectangle(im, (a, 22), (b, 38), YELLOW, -1)
            cv2.line(im, (X(kd["t"]), 14), (X(kd["t"]), 40), GREEN, 3)
            s = f"key {kd['key']} down at 0 ({kd['what']}); yellow = {kd['key']}'s landing window " \
                f"{kd['land'][0] - kd['t']:.2f}-{kd['land'][1] - kd['t']:.2f} s"
        else:
            s = "no skill key down of ours in the 1 s before the pose; the strip starts 0.8 s before it"
        for o in c["others"]:
            cv2.line(im, (X(o[0]), 18), (X(o[0]), 40), (160, 160, 160), 2)
            text(im, o[1], X(o[0]) + 3, 18, (200, 200, 200), 0.4)
        cv2.line(im, (X(c["t"]), 14), (X(c["t"]), 42), RED, 2)
        text(im, s + "; red = the pose begins; grey = other key-downs", x0, 13, WHITE, 0.45)
        return im

    def frame_entry(self, c, j):
        C = Cap(c["cap"]).row(c["n"])["C"]
        return {"mobs": [{"feet": [c["x"] - C[0], c["y"] - C[1]], "type": c["mob"],
                          "cls": "d" if j.get("pose") == "die" else "h", "who": j["who"], "pose": j.get("pose")}],
                "unsure": [], "false": [], "hit_begin": {"t": c["t"], "who": j["who"], "pose": j.get("pose")},
                "class": c["class"]}

    def items(self, c, j):
        return {"who": j["who"]}


# ---- L5: name tags
_PLAYERS = {}


def players(cap):
    if cap not in _PLAYERS:
        import proto_players as PP
        F = PP.frames_of(cap)
        trk, tracks, g, mt, _ = PP.run(F, cover=2.0)
        _PLAYERS[cap] = (F, trk)
    return _PLAYERS[cap]


@a_set
class L5(LabelSet):
    name, size = "L5", 200
    caps = [cache.DESIGN, "20261120_235747_1#0"]
    quota = {"pet": 40, "mob": 25, "log": 25, "short": 20, "text": 15, "players 2+": 35, "player": 40}

    def pick(self):
        import proto_players as PP
        pools = defaultdict(list)
        for cap in self.caps:
            F, trk = players(cap)
            for (n, t, C, own, tags, fit, bodies), rec in zip(F["rows"], trk.frames):
                if rec is None or not tags:
                    continue
                cl = []
                for x in rec:
                    if isinstance(x[0], str):
                        cl.append("log" if x[0] == "log" else "ours")
                    elif x[0] is not None:
                        cl.append(PP.final(x[0]).cls())
                c = {"cap": cap, "n": n, "t": t}
                k = Counter(cl)
                if k["pet"]:
                    pools["pet"].append(c)
                if k["mob"]:
                    pools["mob"].append(c)
                if k["log"]:
                    pools["log"].append(c)
                if k["short"] or k["unsure"]:
                    pools["short"].append(c)
                if k["text"] or k["pattern"] or k["npc"]:
                    pools["text"].append(c)
                if k["player"] >= 2:
                    pools["players 2+"].append(c)
                if k["player"]:
                    pools["player"].append(c)
        pools = {k: thin(v, 2.0) for k, v in pools.items()}
        print({k: len(v) for k, v in pools.items()})
        cases = balanced(self.rnd, pools, self.quota)
        for c in cases:
            r = Cap(c["cap"]).row(c["n"])
            c["C"] = list(r["C"])
            c["tags"] = [list(map(int, t[:4])) for t in r["facts"].get("tags") or []]
        return cases

    def tile(self, c, k):
        import cv2
        cp = Cap(c["cap"])
        img = cp.img(c["n"])
        full = img[:PLAY_H].copy()
        draw_graph(cp, full, c["C"])
        for i, (x, y, w, h) in enumerate(c["tags"]):
            cv2.rectangle(full, (x - 2, y - 2), (x + w + 1, y + h + 1), YELLOW, 1)
            text(full, str(i + 1), x - 16 if x > 20 else x + w + 4, y + h - 3, YELLOW, 0.5)
        tiles = []
        Z = 2
        for i, (x, y, w, h) in enumerate(c["tags"]):
            W, H = max(130, w + 40), 120
            cr = crop(img, x + w / 2, y - 40, W, H, Z)
            draw_graph(cp, cr, c["C"], Z, x + w / 2 - W // 2, y - 40 - H // 2, alpha=0.45)
            text(cr, str(i + 1), 6, 24, YELLOW, 0.8, 2)
            tiles.append(cr)
        head = header(f"L5 case {k}  ({c['cap']} n {c['n']})  - every numbered tag: ours / player <place> / pet / log / mob "
                      f"/ npc / text / none / ?", full.shape[1])
        parts = [head, full]
        if tiles:
            parts.append(grid(tiles, 4))
        return vstack(parts, 4)

    def frame_entry(self, c, j):
        tg = j.get("tags") or {}
        out = []
        for i, b in enumerate(c["tags"]):
            v = (tg.get(str(i + 1)) or "?").split()
            e = {"box": b, "class": v[0]}
            if v[0] == "player":
                p = v[1] if len(v) > 1 else "?"
                e["place"] = ("stand" if p.startswith("s") else "rope" if p.startswith("r") else "air" if p == "a" else "?")
                e["node"] = int(p[1:]) if p[:1] in "sr" and p[1:].lstrip("-").isdigit() else None
            out.append(e)
        return {"mobs": [], "unsure": [], "false": [], "tags": out, "class": c["class"]}

    def items(self, c, j):
        tg = j.get("tags") or {}
        return {f"t{i + 1}": " ".join((tg.get(str(i + 1)) or "?").split()[:2]) for i in range(len(c["tags"]))}


# ---- L6: drops, the mob each came from
@a_set
class L6(LabelSet):
    name, size, per_sheet = "L6", 50, 2
    quota = {"one death": 20, "several": 18, "none": 12}

    def pick(self):
        import proto_drops as D
        pools = defaultdict(list)
        for cap in cache.SOUND:
            try:
                res = D.kept(cap)
            except FileNotFoundError:
                continue
            deaths = res["deaths"]
            for L in res["lives"]:
                if L["born_view"] is False and L["born_n"] == res["N"][0]:
                    continue                                  # there at the capture's start
                bt = L["born_t"]
                cand = [(t, x, y, k) for t, x, y, k in deaths if bt - 3.0 <= t <= bt - 0.2 and abs(x - L["x"]) <= 260
                        and abs(y - L["yf"]) <= 140]
                if len(cand) > len(LETTERS):
                    continue
                cls = "none" if L["from_mob"] is None and not cand else "one death" if len(L["near"] or []) == 1 else \
                    "several" if len(L["near"] or []) > 1 else "none"
                pools[cls].append({"cap": cap, "n": int(L["born_n"]), "t": bt, "item": L["item"], "name": L["name"],
                                   "x": L["x"], "y": L["yf"],
                                   "deaths": [[float(t), float(x), float(y), int(k)] for t, x, y, k in sorted(cand)],
                                   "proto": L["from_mob"]})
        pools = {k: thin(v, 2.0) for k, v in pools.items()}
        print({k: len(v) for k, v in pools.items()})
        return balanced(self.rnd, pools, self.quota)

    def tile(self, c, k):
        cp = Cap(c["cap"])
        W, H, Z = 340, 220, 1.0
        mx = c["x"]
        my = c["y"] - 40
        tiles = []
        for dt in (-2.2, -1.8, -1.5, -1.2, -0.9, -0.6, -0.3, 0.0):
            r = cp.at_t(c["t"] + dt)
            cr, f = place_crop(cp, r["n"], mx, my, W, H, Z)
            if cr is None:
                tiles.append(blank(W, H))
                continue
            C = r["C"]
            ox, oy = mx - C[0] - W // 2, my - C[1] - H // 2
            for L, (t, x, y, _) in zip(LETTERS, c["deaths"]):
                if t <= c["t"] + dt + 0.05:
                    text(cr, L, (x - C[0] - ox) - 4, (y - C[1] - oy) + 16, ORANGE, 0.6, 2)
            if dt == 0:
                mark(cr, c["x"] - C[0] - ox, c["y"] - C[1] - oy - 8, RED, "x", 12)
            text(cr, f"{dt:+.1f} s" if dt else "DROP RESTS (red x)", 6, 16, WHITE)
            tiles.append(cr)
        return vstack([header(f"L6 case {k}  {c['name']}  ({c['cap']} n {c['n']})  - deaths lettered at their place from the "
                              f"moment the die pose starts: which mob did it fly out of: A / B / ... / A|B / none / ?", 1390),
                       grid(tiles, 4, 4)], 2)

    def frame_entry(self, c, j):
        C = Cap(c["cap"]).row(c["n"])["C"]
        fr = j["from"]

        def death(L):
            d = c["deaths"][LETTERS.index(L)] if L in LETTERS[:len(c["deaths"])] else None
            return None if d is None else {"t": d[0], "x": d[1], "y": d[2], "chain": d[3]}
        either = fr.split("|") if "|" in fr else None          # "A|B": two deaths at one place, either one (try 2)
        return {"mobs": [], "unsure": [], "false": [],
                "drop": {"item": c["item"], "x": c["x"], "y": c["y"], "feet": [c["x"] - C[0], c["y"] - C[1]], "from": fr,
                         "from_death": None if either else death(fr),
                         "from_either": [death(L) for L in either] if either else None},
                "class": c["class"]}

    def items(self, c, j):
        f = j["from"]
        return {"from": "|".join(sorted(f.split("|"))) if "|" in f else f}


# ---- L7: the 8 slots
@a_set
class L7(LabelSet):
    name, size, per_sheet = "L7", 100, 9
    quota = {"amount step": 35, "unreadable": 15, "plain": 50}
    BAR = (933, 588, 151, 114)

    def pick(self):
        pools = defaultdict(list)
        sl = CORPUS / "work" / "track-plan" / "slots"
        for d in sorted(sl.iterdir()):
            if not (d / "reads.npz").exists():
                continue
            cap = d.name[::-1].replace("_", "#", 1)[::-1]
            z = np.load(d / "reads.npz")
            ns, ts, ex = z["n"], z["t"], z["exact"]
            ev = json.loads((d / "events.json").read_text(encoding="utf-8"))
            for e in ev.get("events") or []:
                if e.get("d") in (-1, 1):
                    i = int(np.searchsorted(ns, e["n"]))
                    j = min(len(ns) - 1, i + 2)
                    pools["amount step"].append({"cap": cap, "n": int(ns[j]), "t": float(ts[j])})
            bad = np.nonzero(~ex.all(axis=1))[0]
            for i in bad[::7]:
                pools["unreadable"].append({"cap": cap, "n": int(ns[i]), "t": float(ts[i])})
            for i in range(0, len(ns), 600):
                pools["plain"].append({"cap": cap, "n": int(ns[i]), "t": float(ts[i])})
        pools = {k: thin(v, 3.0) for k, v in pools.items()}
        print({k: len(v) for k, v in pools.items()})
        return balanced(self.rnd, pools, self.quota)

    def tile(self, c, k):
        import frames as rec
        cl = rec.clip(c["cap"], False, "label_sets")
        r = None
        try:
            r = Cap(c["cap"]).row(c["n"])["frame"]
        except Exception:
            r = rec.name_of(c["n"])
        img = rec.read(cl.run, r)
        x, y, w, h = self.BAR
        Z = 3
        if img is None:
            return blank(w * Z, h * Z + 24)
        cr = crop(img, x + w // 2, y + h // 2, w, h, Z)
        return vstack([header(f"L7 case {k}", w * Z), cr], 0)

    def sheets(self, cases, prefix):
        for old in self.dir().glob(f"{prefix}_*.png"):
            old.unlink()
        out = []
        for i in range(0, len(cases), self.per_sheet):
            tiles = [self.tile(c, k) for k, c in enumerate(cases[i:i + self.per_sheet], start=i)]
            p = self.dir() / f"{prefix}_{i // self.per_sheet:03d}.png"
            write_png(p, grid(tiles, 3, 8))
            out.append(p)
        return out

    def frame_entry(self, c, j):
        return {"mobs": [], "unsure": [], "false": [], "slots": j["slots"], "class": c["class"]}

    def items(self, c, j):
        return {f"k_{key}": v for key, v in (j.get("slots") or {}).items()}


# ------------------------------------------------------------------------------------------------ commands
def cmd_pick(name, seed):
    S = SETS[name](seed)
    S.dir().mkdir(parents=True, exist_ok=True)
    cases = S.pick()
    print(f"{name}: {len(cases)} cases {dict(Counter(c['class'] for c in cases))}")
    (S.dir() / "cases.json").write_text(json.dumps(cases, indent=0), encoding="utf-8")
    pa = S.sheets(cases, "a")
    rnd = random.Random(seed + 100)
    nb = max(1, math.ceil(len(cases) / 10))
    bi = rnd.sample(range(len(cases)), nb)
    (S.dir() / "b_cases.json").write_text(json.dumps(bi), encoding="utf-8")
    pb = S.sheets([cases[i] for i in bi], "b")
    print(f"  sheets: {len(pa)} a, {len(pb)} b in {S.dir()}")


def judged(name, which="a", rope=True) -> dict:
    """The judgments of one look: SET_a.jsonl, or its parts SET_a.p0.jsonl ... (one labeller each). L1 (rope=True,
    when L1R's judgments exist): the cases near a rope take L1R's (try 3), renumbered to L1's cases."""
    out = _judged(name, which)
    if name == "L1" and rope and list(JUDGED.glob(f"L1R_{which}*.jsonl")):
        rc = json.loads((WORK / "L1R" / "cases.json").read_text(encoding="utf-8"))
        R = _judged("L1R", which)
        if which == "a":
            for k, j in R.items():
                out[rc[k]["l1"]] = dict(j, case=rc[k]["l1"], rope_try3=k)
        else:
            rb = json.loads((WORK / "L1R" / "b_cases.json").read_text(encoding="utf-8"))
            l1b = json.loads((WORK / "L1" / "b_cases.json").read_text(encoding="utf-8"))
            for kb, j in R.items():
                kb1 = l1b.index(rc[rb[kb]]["l1"])
                out[kb1] = dict(j, case=kb1, rope_try3=kb)
    return out


def _judged(name, which="a") -> dict:
    out = {}
    for p in sorted(JUDGED.glob(f"{name}_{which}.jsonl")) + sorted(JUDGED.glob(f"{name}_{which}.p*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                if int(j["case"]) in out:
                    raise SystemExit(f"{p.name}: case {j['case']} judged twice")
                out[int(j["case"])] = j
    return out


def cmd_write(name):
    S = SETS[name]()
    cases = json.loads((S.dir() / "cases.json").read_text(encoding="utf-8"))
    J = judged(name)
    missing = [k for k in range(len(cases)) if k not in J]
    if missing:
        raise SystemExit(f"{name}: cases not judged: {missing[:20]} ({len(missing)})")
    per = defaultdict(dict)
    for k, c in enumerate(cases):
        e = S.frame_entry(c, J[k])
        e["case"] = k
        n = str(c["n"])
        if n in per[c["cap"]]:                       # two cases on one frame (L2 / L3 / L8): one entry, both
            old = per[c["cap"]][n]
            for f in ("mobs", "unsure", "false"):
                old[f] += e[f]
            old.setdefault("more", []).append(e)
        else:
            per[c["cap"]][n] = e
    import corpus
    for cap, frames in per.items():
        p = corpus.labels_dir(cap) / "labels" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"v": 2, "set": name, "run": cap, "by": BY, "frames": frames}, indent=1),
                     encoding="utf-8")
        print(f"  {name}: {len(frames)} frames -> {p}")


def unsure(v) -> bool:
    """No answer: "?" - also as the last word ("player ?": a player, its place not told)."""
    return v is None or str(v).strip() in ("?", "") or str(v).split()[-1] == "?"


def cmd_agree(names, judged_dir=None):
    """The agreement (the user, 2026-11-24): counted on the items BOTH looks answered; a "?" against an answer is
    reported apart with its count, and so are the items both left "?". The gate: >= 95 % on the answered ones."""
    global JUDGED
    if judged_dir:
        JUDGED = Path(judged_dir)
    for name in names:
        S = SETS[name]()
        cases = json.loads((S.dir() / "cases.json").read_text(encoding="utf-8"))
        bi = json.loads((S.dir() / "b_cases.json").read_text(encoding="utf-8"))
        A, B = judged(name, "a"), judged(name, "b")
        same = both = one_q = two_q = 0
        diff, qd = [], []
        for kb, ka in enumerate(bi):
            ia, ib = S.items(cases[ka], A[ka]), S.items(cases[ka], B[kb])
            for key in sorted(set(ia) | set(ib)):
                va, vb = ia.get(key), ib.get(key)
                if unsure(va) and unsure(vb):
                    two_q += 1
                elif unsure(va) or unsure(vb):
                    one_q += 1
                    qd.append((ka, key, va, vb))
                else:
                    both += 1
                    if va == vb:
                        same += 1
                    else:
                        diff.append((ka, key, va, vb))
        nq = sum(unsure(v) for k in range(len(cases)) for v in S.items(cases[k], A[k]).values())
        ni = sum(len(S.items(cases[k], A[k])) for k in range(len(cases)))
        print(f"{name}: {len(bi)} cases looked at twice; answered by both {both} items, agree {same} = "
              f"{100 * same / max(1, both):.1f} %; '?' against an answer {one_q}; '?' in both {two_q}  "
              f"(the first look's '?': {nq} of {ni} items = {100 * nq / max(1, ni):.1f} %)")
        for d in diff:
            print(f"   differ: case {d[0]} {d[1]}: first {d[2]!r}, second {d[3]!r}")
        for d in qd:
            print(f"   '?' vs answer: case {d[0]} {d[1]}: first {d[2]!r}, second {d[3]!r}")


def cmd_redo(name, nb, seed):
    """Try 2 of a set (PLAN-tracker step 1, 2026-11-24): the same cases (cases.json), the sheets drawn anew, a new
    second-look sample of nb cases (all when the set is smaller) in its own order, numbered anew."""
    S = SETS[name](seed)
    cases = json.loads((S.dir() / "cases.json").read_text(encoding="utf-8"))
    if hasattr(S, "prep"):
        cases = S.prep(cases)
        (S.dir() / "cases.json").write_text(json.dumps(cases, indent=0), encoding="utf-8")
    pa = S.sheets(cases, "a")
    rnd = random.Random(seed + 200)
    bi = rnd.sample(range(len(cases)), min(nb, len(cases)))
    (S.dir() / "b_cases.json").write_text(json.dumps(bi), encoding="utf-8")
    pb = S.sheets([cases[i] for i in bi], "b")
    print(f"{name}: {len(cases)} cases, sheets {len(pa)} a + {len(pb)} b ({len(bi)} cases) in {S.dir()}")


def cmd_check(names):
    """Each set's label files read by label_eval.py against world.py's tracks of the kept replay (today.jsonl)."""
    import corpus
    for name in names:
        caps = sorted({c["cap"] for c in json.loads((WORK / name / "cases.json").read_text(encoding="utf-8"))})
        for cap in caps:
            lab = corpus.labels_dir(cap) / "labels" / f"{name}.json"
            ns = {int(n) for n in json.loads(lab.read_text(encoding="utf-8"))["frames"]}
            tp = dump.clip_of(cap).out / "track" / "today.jsonl"
            have = set()
            if tp.exists():
                have = {json.loads(x)["n"] for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()}
            if not ns <= have:
                if (dump.out_dir(cap) / "meta.json").exists():
                    rows = [{"n": r["n"], "mobs": r["mobs"] or []} for r in dump.rows(cap) if r["n"] in ns | have]
                else:                                # no kept replay (L7's other captures): no tracks to grade
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    rows = [{"n": n, "mobs": []} for n in sorted(ns | have)]
                tp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            out = subprocess.run([sys.executable, str(HERE.parent / "label_eval.py"), cap, "--labels",
                                  f"labels/{name}.json", "--tracks", "track/today.jsonl"],
                                 capture_output=True, text=True, encoding="utf-8")
            first = (out.stdout.strip().splitlines() or [out.stderr.strip()[-300:]])[0]
            print(f"{name} {cap}: exit {out.returncode}: {first}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["mobs", "pick", "redo", "ropes", "write", "agree", "check"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--nb", type=int, default=30, help="redo: cases in the second look")
    ap.add_argument("--judged", help="agree: another folder of judgments (judged/try1: the first try's)")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "tools" / "data"))
    names = a.args or sorted(SETS)
    if a.cmd == "mobs":
        for cap in (cache.SOUND if a.sound else a.args):
            run_mobs(cap)
    elif a.cmd == "pick":
        for nm in names:
            cmd_pick(nm, a.seed)
    elif a.cmd == "ropes":
        cmd_ropes(a.seed)
    elif a.cmd == "redo":
        for nm in a.args:
            cmd_redo(nm, a.nb, a.seed)
    elif a.cmd == "write":
        for nm in names:
            cmd_write(nm)
    elif a.cmd == "agree":
        cmd_agree(names, a.judged)
    else:
        cmd_check(names)


if __name__ == "__main__":
    main()
