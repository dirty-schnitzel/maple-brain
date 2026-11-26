"""Tracker plan, step 5a, measured first: THE HP METER Classic World draws over a mob (PLAN-tracker.md "Step 5a").
A prototype: nothing here is built into maplebrain/. Everything from the recordings (no v83 reference).

    python tools/perc/track/proto_meter.py scan --sound [--jobs 8]   every frame -> meters (the whole play area)
    python tools/perc/track/proto_meter.py place | picture | new | ties | when | starts --sound    the questions
    python tools/perc/track/proto_meter.py sheet odd | outside | first                            picture sheets
    python tools/perc/track/proto_meter.py l9 pick | more | agree | write                         the label set L9

`scan` reads every frame of a capture's video (the bank) and finds the meters on the WHOLE play area (y < 700), so a
meter the band above the mobs would miss is still seen. Kept in CORPUS/work/track-plan/meter/<SESSION#K>.pkl: per
frame (video index, session frame number, t) the meters found.

THE PICTURE (measured 2026-11-26, The Cave of Evil Eye I frame 1615, Line 1 frame 31991 and checked over every
capture by `scan`): a box 52 x 10 px, drawn opaque, every pixel exact:
    row 0          black (0, 0, 0)
    row 1          col 0 black, cols 1..50 white (255, 255, 255), col 51 black
    rows 2..7      col 0 black, col 1 white, col 2 black, cols 3..48 the INSIDE (46 px), col 49 black, col 50 white,
                   col 51 black
    row 8          as row 1; row 9 black
    the inside:    row 2 black; rows 3..5 the HP left = green (0, 255, 0) from the left, the HP lost = dark red that
                   fades to black: (169, 0, 0) [RGB] at the hit, (133, 0, 0) 0.3 s later, black (0, 0, 0) later; row 6 a
                   darker line: (170, 0, 0) under the green, ~0.7 x the red under the lost part; row 7 black
So the fill = the green columns / 46.

THE FINDER: every column x where box rows 1, 2, 7, 8 read white, black, black, white (`frame columns`: the box's
columns 2..49) - so the pattern holds whatever the inside shows (green, red, black); grouped by row into meters
(columns of one row within the box's width); the all-white frame column left of the first (box column 1) or right of
the last (box column 50) fixes where the box is, so a meter cut by the screen's edge or partly drawn over is read
from its one end. The inside's columns are then green (rows 3..5 green), lost (red or black) or other (drawn over);
the fill is known when the box's place is known and the column after the green is seen lost (or all 46 are green).
"""
import argparse
import json
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT))
import cache  # noqa: E402
import load  # noqa: E402

PLAY_H = 700
INSIDE_W = 46                           # the inside's width, px
BOX_W, BOX_H = 52, 10                   # the whole box
IN_DX, IN_DY = 3, 3                     # the inside's first green row / column inside the box


def meter_dir() -> Path:
    from maplebrain.config import CORPUS
    d = Path(CORPUS) / "work" / "track-plan" / "meter"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ the finder (whole play area)
def find(f: np.ndarray) -> list:
    """The meters on the frame: [(y, x_in, n_cols, green, lost, left_seen, right_seen, place_known, red_v, other,
    fill)] - y = the inside's first row; x_in = the inside's first column (from a white end; else the first frame
    column seen + 1); n_cols = the frame columns seen (48 for a whole meter); green / lost / other = the inside columns
    seen of each kind; left_seen / right_seen = the white end columns found; red_v = the lost part's R value
    (median; 0 = black); fill = the green share, None when not known (see the module's docstring)."""
    F = f[:PLAY_H]
    H, Wd = F.shape[:2]
    wht = (F >= 235).all(axis=2)
    blk = (F <= 24).all(axis=2)
    p = wht[0:H - 7] & blk[1:H - 6] & blk[6:H - 1] & wht[7:H]          # y = box row 1
    ys, xs = np.nonzero(p)
    if not len(ys):
        return []
    out = []
    i, n = 0, len(ys)
    while i < n:
        j = i
        while j + 1 < n and ys[j + 1] == ys[i] and xs[j + 1] - xs[i] < 48:
            j += 1
        y1, xa, xb = int(ys[i]), int(xs[i]), int(xs[j])
        cols = xs[i:j + 1]
        left = xa >= 1 and bool(wht[y1:y1 + 8, xa - 1].all())
        right = xb + 1 < Wd and bool(wht[y1:y1 + 8, xb + 1].all())
        x0 = xa - 2 if left else (xb + 1 - 50 if right else xa - 2)
        xin = x0 + 3
        ins = cols[(cols >= xin) & (cols < xin + INSIDE_W)]
        fill3 = F[y1 + 2:y1 + 5, ins]                                     # (3, k, 3) BGR
        g = ((fill3[..., 1] >= 230) & (fill3[..., 0] <= 24) & (fill3[..., 2] <= 24)).all(axis=0)
        lost = ((fill3[..., 1] <= 24) & (fill3[..., 0] <= 24)).all(axis=0) & ~g
        red_v = int(np.median(fill3[1, lost, 2])) if lost.any() else -1
        fill = None
        if left or right:
            seen = dict(zip((ins - xin).tolist(), np.where(g, 1, np.where(lost, 0, -1)).tolist()))
            k = 0
            while seen.get(k) == 1:
                k += 1
            if k == INSIDE_W or seen.get(k) == 0:
                fill = k / INSIDE_W
        out.append((y1 + 2, xin, j - i + 1, int(g.sum()), int(lost.sum()), left, right, left or right, red_v,
                    int(len(ins) - g.sum() - lost.sum()), fill))
        i = j + 1
    return out


# ------------------------------------------------------------------ scan
PART = 9000                             # video frames a scan job reads (the 30-minute capture: 13 jobs)


def _scan_part(job: tuple) -> tuple:
    cap, a, b = job
    import frames as fr
    run = load.run_path(cap)
    v = fr.video(run)
    shift = fr.xshift(run)
    rows = []
    for i in range(a, min(b, len(v))):
        f = v.frame(i)
        if f is None:
            rows.append((i, v.n[i], v.t[i], None))
            continue
        if shift:
            f = fr.unshift(f, shift)
        rows.append((i, v.n[i], v.t[i], find(f)))
    return cap, a, rows


def scan(caps: list, jobs: int) -> None:
    import frames as fr
    t0 = time.perf_counter()
    work = []
    for c in caps:
        n = len(fr.video(load.run_path(c)))
        work += [(c, a, a + PART) for a in range(0, n, PART)]
    parts: dict = {c: {} for c in caps}
    if jobs <= 1:
        done = map(_scan_part, work)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(jobs)
        done = ex.map(_scan_part, work)
    for cap, a, rows in done:
        parts[cap][a] = rows
        if len(parts[cap]) == sum(1 for w in work if w[0] == cap):
            out = [r for k in sorted(parts[cap]) for r in parts[cap][k]]
            p = meter_dir() / f"{cap}.pkl"
            p.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
            n_m = sum(len(r[3]) for r in out if r[3])
            print(f"{cap}: {len(out)} frames, {n_m} meters, {sum(1 for r in out if r[3])} frames with one "
                  f"({time.perf_counter() - t0:.0f} s) -> {p}", flush=True)


def scanned(cap: str) -> list:
    return pickle.loads((meter_dir() / f"{cap}.pkl").read_bytes())


# ------------------------------------------------------------------ sheets (by eye)
def read_frame(cap: str, n: int):
    """Frame number n (the session's) of the capture's video, the column error undone."""
    import frames as fr
    return fr.read(load.run_path(cap), fr.name_of(n))


def tile(img, cx: int, cy: int, w: int = 220, h: int = 150, zoom: int = 3, marks=(), title: str = "") -> np.ndarray:
    """A crop of `img` centred on (cx, cy), zoomed (nearest), with marks [(sx, sy, text, colour)] drawn at the
    screen points (a cross + its text), the title on a black strip above."""
    H, W = img.shape[:2]
    x0, y0 = int(cx - w // 2), int(cy - h // 2)
    can = np.zeros((h, w, 3), np.uint8)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if sx1 > sx0 and sy1 > sy0:
        can[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = img[sy0:sy1, sx0:sx1]
    z = cv2.resize(can, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    for sx, sy, text, col in marks:
        px, py = int((sx - x0) * zoom), int((sy - y0) * zoom)
        cv2.drawMarker(z, (px, py), col, cv2.MARKER_CROSS, 14, 2)
        cv2.putText(z, text, (px + 6, py + 18), 0, 0.7, (0, 0, 0), 4)
        cv2.putText(z, text, (px + 6, py + 18), 0, 0.7, col, 2)
    strip = np.zeros((22, z.shape[1], 3), np.uint8)
    cv2.putText(strip, title, (4, 16), 0, 0.5, (255, 255, 255), 1)
    return np.vstack([strip, z])


def grid(tiles: list, cols: int = 3) -> np.ndarray:
    h = max(t.shape[0] for t in tiles)
    w = max(t.shape[1] for t in tiles)
    rows = []
    for i in range(0, len(tiles), cols):
        row = [np.pad(t, ((0, h - t.shape[0]), (0, w - t.shape[1]), (0, 0))) for t in tiles[i:i + cols]]
        row += [np.zeros((h, w, 3), np.uint8)] * (cols - len(row))
        rows.append(np.hstack([np.pad(t, ((2, 2), (2, 2), (0, 0)), constant_values=90) for t in row]))
    return np.vstack(rows)


# ------------------------------------------------------------------ measure: what is under a meter
STEP3 = Path(r"F:\dev\maple-corpus\work\track-plan\step3")
TAG = "t4bc"                            # the mob tracker of step 4b's close (the current code) over the kept replay
SKILLS = ("q", "w", "e")
LAND = {"q": (0.45, 0.72), "w": (0.45, 0.95), "e": (0.03, 0.90)}   # measurement 6: key-down -> a hit / die pose
MWIN = {"q": (0.20, 0.80), "w": (0.20, 0.80), "e": (0.15, 0.65)}   # key-down -> a NEW meter (`new`: 144 of 144 in one)


def pct(v, ps=(5, 50, 95), nd=1):
    v = np.asarray(v, float)
    return "-" if not len(v) else " / ".join(f"{np.percentile(v, p):.{nd}f}" for p in ps)


class Geo:
    """Per kind and pose-frame, from mob.json: origin, lt, rb, head (None: the frame has none)."""

    def __init__(self):
        self.k = {}

    def frame(self, kind: int, pose: str):
        if kind not in self.k:
            p = ROOT / "assets" / "mcw" / "mobs" / str(kind) / "mob.json"
            self.k[kind] = json.loads(p.read_text(encoding="utf-8"))
        fr = self.k[kind]["frames"]
        a, _, j = pose.rpartition("_")
        lst = fr.get(a) or []
        return lst[int(j)] if j.isdigit() and int(j) < len(lst) else None

    def name(self, kind: int) -> str:
        self.frame(kind, "stand_0")
        return self.k[kind]["name"]


class Cap:
    """One capture: the meters found by `scan`, the mob tracker's tracks (step 4b close) and our skill keys."""

    def __init__(self, cap: str):
        self.cap = cap
        sc = scanned(cap)
        self.meters = {n: m for _, n, _, m in sc if m}
        self.t_of = {n: t for _, n, t, _ in sc}
        self.ns = [n for _, n, _, _ in sc]
        d = pickle.loads((STEP3 / f"{cap.replace('#', '_')}_{TAG}.pkl").read_bytes())
        self.rows = {r["n"]: r for r in d["rows"]}
        self.pose = {(n, i): (p, fc) for i, _, n, _, _, _, p, fc in d["feet"]}
        self.ended = d["ended"]
        run = load.run_path(cap)
        self.keys = [(k["t"], k["key"]) for k in map(json.loads, open(run / "keys.jsonl", encoding="utf-8"))
                     if k.get("down") and k["key"] in SKILLS]
        self.kt = np.array([t for t, _ in self.keys])

    def seen(self, n: int) -> list:
        r = self.rows.get(n)
        return [m for m in (r["mobs"] if r else []) if m["src"] == "acq" and m["state"] != "tentative"]


def box_of(m: tuple) -> tuple:
    """A meter's box on the screen (x0, y0, x1, y1) from the finder's row."""
    y, xin = m[0], m[1]
    return xin - IN_DX, y - IN_DY, xin - IN_DX + BOX_W, y - IN_DY + BOX_H


def candidates(c: Cap, n: int, m: tuple, dx_max=60, dy_max=260) -> list:
    """Seen tracks under the meter: (|dx|, track) with the meter's centre within dx_max of its feet's x and its top
    above its feet by 0..dy_max."""
    x0, y0, x1, _ = box_of(m)
    cx = (x0 + x1) / 2
    out = []
    for tr in c.seen(n):
        dx, dy = cx - tr["sx"], tr["sy"] - y0
        if abs(dx) <= dx_max and 0 < dy <= dy_max:
            out.append((abs(dx), tr))
    return sorted(out, key=lambda a: a[0])


def measure_place(caps: list) -> None:
    """Where a meter sits against the one seen mob under it: its box's centre x - the feet's x, its top against the
    feet, the sprite's top (feet - origin y), the body box's top (lt) and the head point - per kind, per animation."""
    geo = Geo()
    by = {}
    n_m = n_one = n_none = n_two = 0
    for cap in caps:
        c = Cap(cap)
        for n, ms in c.meters.items():
            for m in ms:
                if not m[7]:                     # no white end seen: where the inside starts is not known
                    continue
                n_m += 1
                cd = candidates(c, n, m)
                if not cd:
                    n_none += 1
                    continue
                if len(cd) > 1:
                    n_two += 1
                    continue
                n_one += 1
                tr = cd[0][1]
                p = c.pose.get((n, tr["id"]))
                if p is None:
                    continue
                pose, fc = p
                f = geo.frame(tr["mob"], pose)
                if f is None:
                    continue
                x0, y0, x1, _ = box_of(m)
                cx = (x0 + x1) / 2
                sx, sy = tr["sx"], tr["sy"]
                head = f.get("head")
                row = {"dx": cx - sx, "feet": y0 - sy, "sprite": y0 - (sy - f["origin"][1]),
                       "lt": None if f.get("lt") is None else y0 - (sy + f["lt"][1]), "head": None if head is None else y0 - (sy + head[1]),
                       "anim": pose.rpartition("_")[0]}
                by.setdefault(tr["mob"], []).append(row)
    print(f"meters with a white end: {n_m}; one seen mob under it {n_one}, two or more {n_two}, none {n_none}")
    _place_report(by, geo)


GEO = Geo()
RULE_DY = -30                           # the box's top over the pose frame's body box top (lt y), measured by `place`
RULE_DX = -26                           # the box's left from the body box's middle (lt..rb, mirrored by facing)


def expect(kind: int, pose: str, facing: int, sx: float, sy: float):
    """Where the meter of a mob seen at screen feet (sx, sy) in `pose` is drawn: its box's (x0, y0), by the rule
    measured with `place`; None when the pose frame has no body box."""
    f = GEO.frame(kind, pose)
    if f is None or not f.get("lt") or not f.get("rb"):
        return None
    lt, rb = f["lt"][0], f["rb"][0]
    if facing == 1:
        lt, rb = -rb, -lt
    return sx + (lt + rb) // 2 + RULE_DX, sy + f["lt"][1] + RULE_DY


def tie(c: Cap, n: int, m: tuple, tol: tuple = (3, 2)):
    """The ONE seen track whose expected meter box is within tol (x, y) px of the meter's, else None (none, or two:
    a meter over two mobs)."""
    x0, y0, _, _ = box_of(m)
    hit = []
    for tr in c.seen(n):
        p = c.pose.get((n, tr["id"]))
        if p is None:
            continue
        e = expect(tr["mob"], p[0], p[1], tr["sx"], tr["sy"])
        if e is not None and abs(e[0] - x0) <= tol[0] and abs(e[1] - y0) <= tol[1]:
            hit.append(tr)
    return hit[0] if len(hit) == 1 else None


def lives(c: Cap) -> dict:
    """Per track id with a meter: [(n, t, meter)] in order."""
    out = {}
    for n in c.ns:
        for m in c.meters.get(n, ()):
            if not m[7]:
                continue
            tr = tie(c, n, m)
            if tr is not None:
                out.setdefault(tr["id"], []).append((n, c.t_of[n], m))
    return out


def runs_of(frames: list) -> list:
    """Sorted frame numbers -> [(first, last)] runs (a gap of one frame joins)."""
    out = []
    for n in frames:
        if out and n - out[-1][1] <= 2:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def fill(m: tuple):
    """The meter's green share as the finder read it (None: its place or the green's end not seen)."""
    return m[10]


def in_window(c: Cap, t: float, slack=(0.0, 0.0), win=None) -> list:
    """Our skill key-downs whose meter window (MWIN; or `win`, widened by slack) holds time t: [(key, lag)]."""
    win = win or MWIN
    out = []
    j = int(np.searchsorted(c.kt, t))
    for k in range(j - 1, -1, -1):
        lag = t - c.kt[k]
        if lag > 1.3:
            break
        key = c.keys[k][1]
        lo, hi = win[key]
        if lo - slack[0] <= lag <= hi + slack[1]:
            out.append((key, round(lag, 3)))
    return out


def life_rows(caps: list) -> list:
    """One dict per mob track that showed a meter (tied by the place rule): when it appeared and went, our key-downs
    around it, the hit / die poses, the first and last whole readings."""
    out = []
    for cap in caps:
        c = Cap(cap)
        lv = lives(c)
        poses = {}
        for (n, i), (p, _) in c.pose.items():
            if i in lv:
                poses.setdefault(i, []).append((n, p))
        born = {}
        for r in c.rows.values():
            for m in r["mobs"]:
                born.setdefault(m["id"], (m["born_how"], m["mob"], m["born"]))
        for tid, pts in lv.items():
            ps = sorted(poses.get(tid, []))
            hitruns = runs_of([n for n, p in ps if p.startswith(("hit", "die"))])
            n0, t0 = pts[0][0], pts[0][1]
            run0 = next((r for r in reversed(hitruns) if r[0] <= n0 + 2), None)
            earlier = [r for r in hitruns if run0 is not None and r[1] < run0[0]]
            die = [n for n, p in ps if p.startswith("die")]
            f0 = next((fill(m) for n, t, m in pts if t - t0 <= 0.25 and fill(m) is not None), None)
            fl = next((fill(m) for n, t, m in reversed(pts) if fill(m) is not None), None)
            gaps = [(a[0], b[0], round(b[1] - a[1], 3)) for a, b in zip(pts, pts[1:]) if b[1] - a[1] > 0.1]
            hb, kind, bt = born.get(tid, ("?", None, None))
            out.append({"cap": cap, "id": tid, "kind": kind, "born_how": hb, "born_t": bt, "n0": n0, "t0": t0,
                        "n1": pts[-1][0], "t1": pts[-1][1], "win": in_window(c, t0),
                        "keys": [(k, round(t0 - kt, 3)) for kt, k in c.keys if 0 <= t0 - kt <= 1.3],
                        "hit0": None if run0 is None else run0[0], "hit0_t": None if run0 is None else c.t_of.get(run0[0]),
                        "earlier_hits": [(r[0], c.t_of.get(r[0])) for r in earlier],
                        "die_n": die[0] if die else None, "die_t": c.t_of.get(die[0]) if die else None,
                        "f0": f0, "f_last": fl, "gaps": gaps, "n_pts": len(pts)})
    return out


def measure_when(caps: list) -> None:
    """When a meter appears (against our skills' landing windows and the hit pose) and goes (the die pose); its
    first reading; the meters that appeared outside our windows."""
    L = life_rows(caps)
    p = meter_dir() / "lives.pkl"
    p.write_bytes(pickle.dumps(L))
    print(f"{len(L)} mob tracks showed a meter (tied by the place rule) -> {p}")
    inw = [x for x in L if x["win"]]
    print(f"  appeared inside one of our skills' meter windows (MWIN): {len(inw)}; outside: "
          f"{len(L) - len(inw)}")
    for x in L:
        if not x["win"]:
            print(f"    OUTSIDE: {x['cap']} track {x['id']} kind {x['kind']} frame {x['n0']} t {x['t0']:.3f}; key-downs "
                  f"in the 1.3 s before {x['keys']}; hit pose began {x['hit0']}; earlier hit runs {x['earlier_hits']}")
    for k in SKILLS:
        lag = [w[1] for x in L for w in x["win"][:1] if w[0] == k]
        print(f"  {k}: key-down -> the meter, s p5/50/95 {pct(lag, nd=3)} (n {len(lag)})")
    lh = [x["t0"] - x["hit0_t"] for x in L if x["hit0_t"] is not None]
    print(f"  the hit pose's first frame -> the meter, s p5/50/95 {pct(lh, nd=3)} (n {len(lh)}); "
          f"frames: {Counter(int(round(v * 60)) for v in lh).most_common(8)}")
    print(f"  no hit / die pose seen at the appearance: {sum(1 for x in L if x['hit0'] is None)}")
    ld = [x["t1"] - x["die_t"] for x in L if x["die_t"] is not None]
    print(f"  the meter's last frame - the first die-pose frame, s p5/50/95 {pct(ld, nd=3)} (n {len(ld)}); "
          f"{sum(1 for v in ld if v < 0)} gone before the die pose was seen")
    print(f"  the last whole reading before it went (deaths seen): "
          f"{Counter(round(x['f_last'] * 46) for x in L if x['die_t'] is not None and x['f_last'] is not None).most_common(8)} (green px)")
    print(f"  gaps over 0.1 s inside a meter's life: {sum(len(x['gaps']) for x in L)} in {sum(1 for x in L if x['gaps'])} lives")
    print("  the first reading (within 0.25 s), per kind; 'clean' = born faded in, no hit / die pose before ours, "
          "appeared in our window:")
    for kind in sorted({x["kind"] for x in L}, key=str):
        xs = [x for x in L if x["kind"] == kind]
        clean = [1 - x["f0"] for x in xs if x["f0"] is not None and x["born_how"] == "faded in" and not x["earlier_hits"]
                 and x["win"]]
        other = [1 - x["f0"] for x in xs if x["f0"] is not None and x["earlier_hits"]]
        rest = [1 - x["f0"] for x in xs if x["f0"] is not None]
        print(f"    {kind} {GEO.name(kind) if kind else '?'}: lives {len(xs)}; our first hit's share, clean "
              f"p5/50/95 {pct(clean, nd=3)} (n {len(clean)}); every first reading {pct(rest, nd=3)} (n {len(rest)}); "
              f"with an earlier hit pose {pct(other, nd=3)} (n {len(other)})")


def mchains(c: Cap, gap: int = 6, d: int = 12) -> list:
    """The meters followed by their own place, no track involved: a meter (a white end seen) continues a chain whose
    last box is at most `gap` frames back and within d + 4 px a frame sideways, 40 + 10 px a frame up or down (the
    meter follows the pose frame's body box: a Bubbling's move frames move it 27 px from one frame to the next). -> [[(n, t, m), ...]] in order of their start."""
    live, done = [], []
    idx = {n: k for k, n in enumerate(c.ns)}
    for n in c.ns:
        ms = [m for m in c.meters.get(n, ()) if m[7]]
        k = idx[n]
        still = []
        for ch in live:
            if k - idx[ch[-1][0]] > gap:
                done.append(ch)
            else:
                still.append(ch)
        live = still
        for m in ms:
            x0, y0, _, _ = box_of(m)
            best, bd = None, None
            for ch in live:
                if ch[-1][0] == n:
                    continue
                px, py, _, _ = box_of(ch[-1][2])
                dd = abs(px - x0) + abs(py - y0)
                g = k - idx[ch[-1][0]]
                if abs(px - x0) <= d + 4 * g and abs(py - y0) <= 40 + 10 * g and (bd is None or dd < bd):
                    best, bd = ch, dd
            if best is None:
                live.append([(n, c.t_of[n], m)])
            else:
                best.append((n, c.t_of[n], m))
    return sorted(done + live, key=lambda ch: ch[0][0])


def at_edge(m: tuple, pad: int = 4) -> bool:
    """The meter's box touches the play area's side, top or bottom (it may have come into view)."""
    x0, y0, x1, y1 = box_of(m)
    return x0 <= pad or x1 >= 1366 - pad or y0 <= pad or y1 >= PLAY_H - pad


def measure_starts(caps: list) -> None:
    """Every meter chain's first frame against our landing windows: inside one; at the screen's edge (came into
    view); after the camera was lost; else listed (to be looked at)."""
    tot, cnt, odd = 0, Counter(), []
    for cap in caps:
        c = Cap(cap)
        for ch in mchains(c):
            if len(ch) < 3 or max(m[2] for _, _, m in ch) < 6:     # a flicker / a few columns: counted apart
                cnt["1-2 frames"] += 1
                continue
            tot += 1
            n0, t0, m0 = ch[0]
            if in_window(c, t0):
                cnt["in our window"] += 1
            elif at_edge(m0):
                cnt["at the screen's edge"] += 1
            elif c.rows.get(n0 - 1) is None or c.rows.get(n0 - 1, {}).get("mobs") is None:
                cnt["after a frame without a row"] += 1
            else:
                cnt["else"] += 1
                odd.append((cap, n0, round(t0, 3), box_of(m0), len(ch),
                            [(k, round(t0 - kt, 2)) for kt, k in c.keys if 0 <= t0 - kt <= 1.5]))
    print(f"meter chains of 3 frames or more: {tot}; {dict(cnt)}")
    p = meter_dir() / "odd_starts.pkl"
    p.write_bytes(pickle.dumps(odd))
    for o in odd:
        print("   ", o)


def new_meters(c: Cap, chains: list) -> list:
    """The chains that are a NEW meter: tied to a seen mob on at least one frame (not UI text), its first box not at
    the play area's edge, and no chain ended within 60 px of it in the 1.5 s before (a meter hidden for a while and
    found again: behind us, another meter, a rope, damage digits). -> [(chain, track id or None at its start)]."""
    out = []
    for k, ch in enumerate(chains):
        if len(ch) < 3 or max(m[2] for _, _, m in ch) < 6:
            continue
        tied = [tie(c, n, m) for n, _, m in ch[:30]]
        if not any(tied):
            continue
        n0, t0, m0 = ch[0]
        if at_edge(m0):
            continue
        bx = box_of(m0)
        before = False
        for o in chains[:k]:
            n1, t1, m1 = o[-1]
            if t0 - 1.5 <= t1 < t0 and abs(box_of(m1)[0] - bx[0]) <= 60 and abs(box_of(m1)[1] - bx[1]) <= 60:
                before = True
                break
        if before:
            continue
        out.append((ch, next((t["id"] for t in tied if t), None)))
    return out


def measure_new(caps: list) -> None:
    """Every NEW meter (new_meters) against our skill key-downs: the delay from the last key-down of each skill
    within 1.3 s; the meter against the tied mob's hit / die pose; the new meters with no key-down of ours in the
    1.3 s before (to be looked at)."""
    lag = {k: [] for k in SKILLS}
    nearest, none, vs_pose = Counter(), [], []
    rows = []
    for cap in caps:
        c = Cap(cap)
        ch = mchains(c)
        for chn, tid in new_meters(c, ch):
            n0, t0, m0 = chn[0]
            ks = [(t0 - kt, k) for kt, k in c.keys if 0.0 <= t0 - kt <= 1.3]
            if not ks:
                none.append((cap, n0, round(t0, 3), box_of(m0), tid))
            else:
                d, k = min(ks)
                nearest[k] += 1
                lag[k].append(d)
            if tid is not None:
                hp = sorted(n for (n, i), (p, _) in c.pose.items() if i == tid and p.startswith(("hit", "die"))
                            and abs(n - n0) <= 60)
                if hp:
                    r = [x for x in runs_of(hp) if x[0] <= n0 + 60]
                    near = min(r, key=lambda x: abs(x[0] - n0))
                    vs_pose.append(near[0] - n0)
            rows.append({"cap": cap, "n0": n0, "t0": t0, "box": box_of(m0), "track": tid,
                         "keys": [(k, round(d, 3)) for d, k in sorted(ks)], "len": len(chn),
                         "fill0": next((m[10] for _, t, m in chn if m[10] is not None and t - t0 <= 0.2), None)})
    (meter_dir() / "new.pkl").write_bytes(pickle.dumps(rows))
    print(f"new meters: {len(rows)}; the nearest key-down before it: {dict(nearest)}; none in 1.3 s: {len(none)}")
    for k in SKILLS:
        v = lag[k]
        print(f"  {k} nearest: key-down -> the meter s p0/5/50/95/100 {pct(v, (0, 5, 50, 95, 100), 3)} (n {len(v)})"
              f"  frames {sorted(Counter(int(round(x * 60)) for x in v).items())}")
    print(f"  the tied mob's nearest hit / die pose begin - the meter's first frame, frames: "
          f"{sorted(Counter(vs_pose).items())} (n {len(vs_pose)})")
    for x in none:
        print("    NO KEY-DOWN:", x)


def why_untied(c: Cap, n: int, m: tuple, tol=(3, 2)) -> str:
    """Why a meter has no one seen track by the place rule: "tied", "two mobs" (two expected boxes match), "no pose"
    (the track under it has no body box in that pose: a die frame), "off" (a seen track under it, its expected box
    further than tol), "no seen mob" (nothing the fit saw under it)."""
    x0, y0, _, _ = box_of(m)
    hit, near, nolt = [], [], []
    for tr in c.seen(n):
        p = c.pose.get((n, tr["id"]))
        if p is None:
            continue
        e = expect(tr["mob"], p[0], p[1], tr["sx"], tr["sy"])
        if e is None:
            if abs(tr["sx"] - (x0 + 26)) < 50 and 0 < tr["sy"] - y0 < 200:
                nolt.append(tr)
            continue
        if abs(e[0] - x0) <= tol[0] and abs(e[1] - y0) <= tol[1]:
            hit.append(tr)
        elif abs(e[0] - x0) <= 40 and abs(e[1] - y0) <= 60:
            near.append((abs(e[0] - x0) + abs(e[1] - y0), tr, e))
    if len(hit) == 1:
        return "tied"
    if len(hit) > 1:
        return "two mobs"
    if nolt:
        return "no pose"
    if near:
        return "off"
    return "no seen mob"


def measure_ties(caps: list) -> None:
    """Over the frames of every REAL meter (a chain tied to a seen mob at least once): is it tied to one seen mob by
    the place rule, and why not."""
    cnt, by_len, offs = Counter(), Counter(), []
    for cap in caps:
        c = Cap(cap)
        for ch in mchains(c):
            if len(ch) < 3 or max(m[2] for _, _, m in ch) < 6:
                continue
            ws = [why_untied(c, n, m) for n, _, m in ch]
            if "tied" not in ws:
                cnt["chains never tied (not a meter, or its mob never seen)"] += 1
                by_len[min(len(ch) // 30, 5)] += 1
                continue
            for w in ws:
                cnt[w] += 1
    tot = sum(v for k, v in cnt.items() if not k.startswith("chains"))
    print(f"meter-frames of chains tied at least once: {tot}")
    for k, v in cnt.most_common():
        print(f"  {k}: {v}" + ("" if k.startswith("chains") else f" ({100 * v / tot:.2f} %)"))
    print(f"  never-tied chains by length (x 30 frames): {dict(sorted(by_len.items()))}")


def measure_picture(caps: list) -> None:
    """The meter's picture over every frame: whole / cut / drawn-over meters, the box's size, the lost part's colour
    against the time since the fill last fell, several meters on a frame, overlapping meters."""
    cnt, red_age, per_frame, overlap, fills = Counter(), {}, Counter(), 0, Counter()
    for cap in caps:
        c = Cap(cap)
        for n, ms in c.meters.items():
            ms = [m for m in ms if m[7] and m[2] >= 6]
            per_frame[len(ms)] += 1
            bs = [box_of(m) for m in ms]
            for i in range(len(bs)):
                for j in range(i + 1, len(bs)):
                    a_, b_ = bs[i], bs[j]
                    if a_[0] < b_[2] and b_[0] < a_[2] and a_[1] < b_[3] and b_[1] < a_[3]:
                        overlap += 1
            for m in ms:
                x0, y0, x1, y1 = box_of(m)
                both = m[5] and m[6]
                if m[2] == 48 and both and m[9] == 0:
                    cnt["whole: 48 frame columns, both white ends, every inside column green or lost"] += 1
                elif x0 < 0 or x1 > 1366:
                    cnt["cut by the screen's side"] += 1
                elif m[2] < 48:
                    cnt["frame columns hidden (drawn over / under the UI)"] += 1
                elif m[9]:
                    cnt["inside columns drawn over"] += 1
                else:
                    cnt["one white end hidden"] += 1
                fills["known" if m[10] is not None else "not known"] += 1
        for ch in mchains(c):
            last_f, last_t = None, None
            for n, t, m in ch:
                if m[10] is None:
                    continue
                if last_f is None or m[10] < last_f - 1e-6:
                    last_t = t
                last_f = m[10]
                if m[4] and m[8] >= 0:
                    red_age.setdefault(min(20, int((t - last_t) / 0.1)), []).append(m[8])
    tot = sum(cnt.values())
    print(f"meters (a white end seen, >= 6 frame columns): {tot}")
    for k, v in cnt.most_common():
        print(f"  {k}: {v} ({100 * v / tot:.1f} %)")
    print(f"  the fill read: {dict(fills)}")
    print(f"  frames by meters on them: {dict(sorted(per_frame.items()))}; pairs of meters overlapping: {overlap}")
    print("  the lost part's red (R, median) by the time since the fill last fell:")
    for b in sorted(red_age):
        v = red_age[b]
        print(f"    {b / 10:.1f}-{(b + 1) / 10:.1f} s: R p5/50/95 {pct(v, nd=0)} (n {len(v)})")


def life_sheet(name: str, cases: list, offsets=(-3, 0, 2, 6, 15, 40)) -> Path:
    """One row per case (a lives.pkl dict): the frames at n0 + each offset, centred on the meter's first box; and the
    last frame of the meter, the frames 1 and 4 after. Marked: the meter's box corners (yellow), the tracks' feet
    (cyan, their id)."""
    tiles = []
    for x in cases:
        c = Cap(x["cap"])
        m0 = next(m for m in c.meters[x["n0"]] if m[7] and tie(c, x["n0"], m) and tie(c, x["n0"], m)["id"] == x["id"])
        bx0, by0, bx1, by1 = box_of(m0)
        cx, cy = (bx0 + bx1) // 2, by0 + 40
        ns = [x["n0"] + o for o in offsets] + [x["n1"], x["n1"] + 1, x["n1"] + 4]
        for k, n in enumerate(ns):
            img = read_frame(x["cap"], n)
            if img is None:
                tiles.append(np.zeros((472, 660, 3), np.uint8))
                continue
            marks = [(tr["sx"], tr["sy"], str(tr["id"]), (255, 255, 0)) for tr in c.seen(n)]
            lab = f"{x['cap'][-4:]} id{x['id']} n{n} ({n - x['n0']:+d})" if k < len(offsets) else                 f"last{'' if n == x['n1'] else f'+{n - x[chr(110) + chr(49)]}'} n{n}"
            tiles.append(tile(img, cx, cy, 220, 150, 3, marks, lab))
    out = meter_dir() / f"sheet_{name}.png"
    cv2.imwrite(str(out), grid(tiles, len(offsets) + 3))
    return out


ODD = [   # (capture, frame, what it shows) - found by `picture`, `ties`, `starts` (2026-11-26)
    ("20261121_000219_2#0", 31991, "the lost part faded to BLACK (3 of 46 green): older damage than 2 s"),
    ("20261118_232410_1#9", 42116, "fresh damage RED (R 169) 0.3 s after our q"),
    ("20261118_232410_1#1", 8478, "two mobs close: their meters overlap (one drawn over the other)"),
    ("20261118_232410_1#1", 8796, "three meters, a rope drawn over them"),
    ("20261118_232410_1#2", 12748, "our character drawn over the meter's left end"),
    ("20261118_232410_1#1", 3832, "damage digits over the meter"),
    ("20261118_232410_1#12", 57015, "a meter over an Evil Eye the fit does not see (hidden): no sighting to tie"),
    ("20261118_232410_1#0", 45, "NOT a meter: the Mesos window's frame (the whole-screen scan only)"),
    ("20261118_232410_1#0", 1698, "NOT a meter: chat lines (the chat open on Ant Tunnel I)"),
]


def odd_sheet() -> Path:
    tiles = []
    edge = None
    for cap in cache.SOUND:                         # one meter cut by the screen's side
        c = Cap(cap)
        for n, ms in sorted(c.meters.items()):
            for m in ms:
                x0, y0, x1, _ = box_of(m)
                if m[7] and m[2] >= 6 and (x0 < 0 or x1 > 1366) and tie(c, n, m):
                    edge = (cap, n, "cut by the screen's side: read from its one white end")
                    break
            if edge:
                break
        if edge:
            break
    for cap, n, what in ODD + ([edge] if edge else []):
        img = read_frame(cap, n)
        c = Cap(cap)
        ms = [m for m in c.meters.get(n, ()) if m[7] and m[2] >= 6]
        if ms:
            x0, y0, x1, _ = box_of(ms[0])
            cx, cy = (x0 + x1) // 2, y0 + 45
        else:
            cx, cy = 683, 350
        cx = min(max(cx, 110), 1366 - 110)
        tiles.append(tile(img, cx, cy, 220, 140, 3, [], f"{cap[-5:]} n{n}: {what}"))
    out = meter_dir() / "sheet_odd.png"
    cv2.imwrite(str(out), grid(tiles, 2))
    return out


def cmd_sheet(what: str, k: int = 6, seed: int = 1):
    import random
    L = pickle.loads((meter_dir() / "lives.pkl").read_bytes())
    if what == "odd":
        print(odd_sheet())
        return
    if what == "outside":
        cases = [x for x in L if not x["win"]]
    elif what == "first":
        random.seed(seed)
        cases = random.sample([x for x in L if x["win"]], k)
    else:
        raise SystemExit(what)
    for i in range(0, len(cases), 5):
        print(life_sheet(f"{what}_{i // 5}", cases[i:i + 5]))


def _place_report(by, geo):
    for kind, rows in sorted(by.items()):
        print(f"\n{kind} {geo.name(kind)}: {len(rows)} meters over one mob")
        for ref in ("dx", "feet", "sprite", "lt", "head"):
            v = [r[ref] for r in rows if r[ref] is not None]
            print(f"  {ref:7s} p5/50/95 {pct(v)}  (n {len(v)})  {Counter(int(round(x)) for x in v).most_common(5)}")
        for anim in sorted({r["anim"] for r in rows}):
            rs = [r for r in rows if r["anim"] == anim]
            print(f"    {anim:6s} n {len(rs):5d}  feet {pct([r['feet'] for r in rs])}  sprite "
                  f"{pct([r['sprite'] for r in rs])}  lt {pct([r['lt'] for r in rs])}")


# ------------------------------------------------------------------ L9: the label set by eye
L9_DIR = Path(r"F:\dev\maple-corpus\work\track-plan\labels\L9")
JUDGED = Path(__file__).resolve().parent / "judged"
LETTERS = "ABCDEFGHIJ"
AREA = (240, 150)                       # the area crop (screen px), shown x3
STRIP = (70, 20)                        # a mob's meter band (screen px) around its expected box, shown x8
QUOTA = {"several": 12, "close": 12, "drawn": 12, "edge": 6, "fresh": 12, "late": 8, "nofind": 12}
KIND_MIN = {7: 1, 13: 6, 17: 8, 19: 8, 21: 8, 23: 10}


def _seen_with_pose(c: Cap, n: int) -> list:
    out = []
    for tr in c.seen(n):
        p = c.pose.get((n, tr["id"]))
        if p is not None:
            out.append((tr, p[0], p[1]))
    return out


def l9_candidates(caps: list) -> list:
    """Frames that may show a meter, each with what kind of case it is (QUOTA's names) and the kind under it."""
    out = []
    for cap in caps:
        c = Cap(cap)
        for ch in mchains(c):
            if len(ch) < 3 or max(m[2] for _, _, m in ch) < 6:
                continue
            if not any(tie(c, n, m) for n, _, m in ch):        # never over a seen mob: UI text, not a meter
                continue
            k = len(ch)
            picks = {0: "fresh", min(3, k - 1): "fresh", k // 2: "", max(0, k - 4): "late"}
            for i, tag in picks.items():
                n, t, m = ch[i]
                ms = [x for x in c.meters.get(n, ()) if x[7] and x[2] >= 6]
                tr = tie(c, n, m)
                x0, y0, x1, y1 = box_of(m)
                tags = {tag} if tag else set()
                if len(ms) >= 2:
                    tags.add("several")
                if x0 < 2 or x1 > 1364 or y0 < 4:
                    tags.add("edge")
                elif m[2] < 48 or m[9] > 0:
                    tags.add("drawn")
                cx = (x0 + x1) / 2
                near = [o for o in c.seen(n) if abs(o["sx"] - cx) < 70 and 0 < o["sy"] - y1 < 160]
                if len(near) >= 2:
                    tags.add("close")
                out.append({"cap": cap, "n": n, "t": t, "anchor": [int(cx), int(y0 + 45)], "tags": sorted(tags),
                            "kind": tr["mob"] if tr else (near[0]["mob"] if near else None), "chain": (cap, ch[0][0])})
        # nofind: 8 frames after a hit pose began (in our window) on a seen mob, no meter found within 80 px of its band
        hits = {}
        for (n, i), (p, _) in c.pose.items():
            if p.startswith("hit"):
                hits.setdefault(i, []).append(n)
        for tid, ns in hits.items():
            for r in runs_of(sorted(ns)):
                n = r[0] + 8
                tr = next((o for o in c.seen(n) if o["id"] == tid), None)
                p = c.pose.get((n, tid))
                if tr is None or p is None or not in_window(c, c.t_of.get(r[0], -9)):
                    continue
                e = expect(tr["mob"], p[0], p[1], tr["sx"], tr["sy"])
                if e is None:
                    continue
                if any(abs(box_of(m)[0] - e[0]) < 80 and abs(box_of(m)[1] - e[1]) < 80 for m in c.meters.get(n, ())
                       if m[2] >= 3):
                    continue
                out.append({"cap": cap, "n": n, "t": c.t_of.get(n), "anchor": [int(e[0] + 26), int(e[1] + 45)],
                            "tags": ["nofind"], "kind": tr["mob"], "chain": (cap, -n)})
    return out


def l9_pick(caps: list, size: int = 100, seed: int = 1) -> list:
    import random
    rnd = random.Random(seed)
    cand = l9_candidates(caps)
    rnd.shuffle(cand)
    chosen, chains = [], set()

    def take(pred, k):
        for x in cand:
            if k <= 0:
                return
            if x["chain"] in chains or not pred(x):
                continue
            chosen.append(x)
            chains.add(x["chain"])
            k -= 1
    for tag, k in QUOTA.items():
        take(lambda x, tag=tag: tag in x["tags"], k - sum(1 for x in chosen if tag in x["tags"]))
    for kind, k in KIND_MIN.items():
        take(lambda x, kind=kind: x["kind"] == kind, k - sum(1 for x in chosen if x["kind"] == kind))
    take(lambda x: True, size - len(chosen))
    chosen.sort(key=lambda x: (x["cap"], x["n"]))
    return chosen


def l9_case_img(case: dict, k: int) -> tuple:
    """The case's picture: the area (x3) with the seen mobs lettered at their feet; per lettered mob its meter band
    (x8) with a ruler (a tick every px, numbers every 10). -> (image, the letters' tracks and bands)."""
    c = Cap(case["cap"])
    img = read_frame(case["cap"], case["n"])
    ax, ay = case["anchor"]
    W, H = AREA
    x0, y0 = ax - W // 2, ay - H // 2
    mobs = []
    for tr, pose, fc in sorted(_seen_with_pose(c, case["n"]), key=lambda a: a[0]["sx"]):
        if x0 - 20 <= tr["sx"] <= x0 + W + 20 and y0 <= tr["sy"] <= y0 + H + 60:
            mobs.append((tr, pose, fc))
    mobs = mobs[:len(LETTERS)]
    marks = [(tr["sx"], tr["sy"], LETTERS[i], (0, 255, 255)) for i, (tr, _, _) in enumerate(mobs)]
    area = tile(img, ax, ay, W, H, 3, marks, f"case {k}: the area x3 - letters at the mobs' feet")
    strips, info = [], []
    for i, (tr, pose, fc) in enumerate(mobs):
        e = expect(tr["mob"], pose, fc, tr["sx"], tr["sy"])
        if e is None:
            continue
        bx, by = int(e[0]) - 9, int(e[1]) - 5
        sw, sh = STRIP
        can = np.zeros((sh, sw, 3), np.uint8)
        sx0, sy0, sx1, sy1 = max(0, bx), max(0, by), min(img.shape[1], bx + sw), min(img.shape[0], by + sh)
        if sx1 > sx0 and sy1 > sy0:
            can[sy0 - by:sy1 - by, sx0 - bx:sx1 - bx] = img[sy0:sy1, sx0:sx1]
        z = cv2.resize(can, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
        ruler = np.full((30, z.shape[1], 3), 40, np.uint8)
        for px in range(sw):
            xx = px * 8 + 4
            ln = 14 if px % 10 == 0 else (9 if px % 5 == 0 else 4)
            cv2.line(ruler, (xx, 29), (xx, 29 - ln), (255, 255, 255), 1)
            if px % 10 == 0:
                cv2.putText(ruler, str(px), (xx + 2, 12), 0, 0.4, (0, 255, 255), 1)
        head = np.zeros((20, z.shape[1], 3), np.uint8)
        cv2.putText(head, f"{LETTERS[i]}: the band over mob {LETTERS[i]} x8 (ticks = 1 screen px)", (4, 14), 0, 0.45,
                    (0, 255, 255), 1)
        strips.append(np.vstack([head, ruler, z]))
        info.append({"letter": LETTERS[i], "track": tr["id"], "kind": tr["mob"], "feet": [tr["sx"], tr["sy"]],
                     "band": [bx, by]})
    right = np.vstack(strips) if strips else np.zeros((10, STRIP[0] * 8, 3), np.uint8)
    h = max(area.shape[0], right.shape[0])

    def pad(a):
        return np.pad(a, ((0, h - a.shape[0]), (0, 0), (0, 0)))
    out = np.hstack([pad(area), np.full((h, 6, 3), 90, np.uint8), pad(right)])
    return out, info


def l9_sheets(cases: list, prefix: str, per: int = 2) -> list:
    for old in L9_DIR.glob(f"{prefix}_*.png"):
        old.unlink()
    imgs, infos = [], []
    for k, case in enumerate(cases):
        im, info = l9_case_img(case, k)
        imgs.append(im)
        infos.append(info)
    for s in range(0, len(imgs), per):
        part = imgs[s:s + per]
        w = max(i.shape[1] for i in part)
        rows = [np.pad(i, ((0, 8), (0, w - i.shape[1]), (0, 0)), constant_values=90) for i in part]
        cv2.imwrite(str(L9_DIR / f"{prefix}_{s // per:03d}.png"), np.vstack(rows))
    return infos


def l9_more(k: int, seed: int = 2) -> None:
    """k more cases with a meter (the 'nofind' picks proved to have none by eye: L9 asks for 100 frames WITH a meter),
    numbered on after the last; their sheets continue a_NNN. Chains already used are not taken again."""
    import random
    cases = json.loads((L9_DIR / "cases.json").read_text(encoding="utf-8"))
    used = {tuple(c["chain"]) for c in cases}
    rnd = random.Random(seed)
    cand = [x for x in l9_candidates(list(cache.SOUND)) if "nofind" not in x["tags"] and
            tuple(x["chain"]) not in used]
    rnd.shuffle(cand)
    have = Counter(c["kind"] for c in cases)
    chosen, chains = [], set()
    for x in sorted(cand, key=lambda x: have[x["kind"]]):         # the kinds L9 holds least first
        if len(chosen) >= k:
            break
        if x["chain"] in chains:
            continue
        chosen.append(x)
        chains.add(x["chain"])
        have[x["kind"]] += 1
    k0 = len(cases)
    if k0 % 2:
        raise SystemExit("an odd number of cases: the sheets pair them")
    imgs, infos = [], []
    for i, x in enumerate(chosen):
        im, info = l9_case_img(x, k0 + i)
        imgs.append(im)
        x["mobs"], x["chain"] = info, list(x["chain"])
    for s_ in range(0, len(imgs), 2):
        part = imgs[s_:s_ + 2]
        w = max(i.shape[1] for i in part)
        rows = [np.pad(i, ((0, 8), (0, w - i.shape[1]), (0, 0)), constant_values=90) for i in part]
        cv2.imwrite(str(L9_DIR / f"a_{(k0 + s_) // 2:03d}.png"), np.vstack(rows))
    cases += chosen
    (L9_DIR / "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
    print(f"L9: {len(chosen)} more cases ({k0}..{len(cases) - 1}), sheets a_{k0 // 2:03d}..a_{(len(cases) - 1) // 2:03d}; "
          f"kinds {dict(Counter(GEO.name(x['kind']) if x['kind'] else '?' for x in chosen))}")


def l9_judged(which: str = "a") -> dict:
    out = {}
    for p in sorted(JUDGED.glob(f"L9_{which}*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                out[int(j["case"])] = j
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _place(lab: dict):
    """A labelled meter's place on its strip: ("L", tick) / ("R", tick - 49) as the box column 1's tick; else None."""
    if _num(lab.get("L")) is not None:
        return _num(lab["L"])
    if _num(lab.get("R")) is not None:
        return _num(lab["R"]) - 49
    return None


def l9_items(j: dict) -> list:
    """The meters of one look as items: (mob, place on its strip or None, fill or None)."""
    return [(str(m.get("mob")), _place(m), _num(m.get("fill"))) for m in j.get("meters") or []]


def l9_agree() -> None:
    """The second look against the first (PLAN-tracker step 1's rule, the user 2026-11-24: counted on the items BOTH
    looks answered; a "?" against an answer is reported apart with its count, and so are the items both left "?"; the
    gate >= 95 % on the answered ones). An item = one meter's mob or one meter's fill. The meters of a case are paired
    by their place on the strip (within 2 px), else by the same mob letter, else - one left in each look - with each
    other. The mob agrees when both name the same (a letter or `none`); the fill when both read it within 3 points."""
    bi = json.loads((L9_DIR / "b_cases.json").read_text(encoding="utf-8"))
    A, B = l9_judged("a"), l9_judged("b")
    cnt = Counter()
    diffs = []

    def q(v):
        return v is None or v == "?"

    for kb, ka in enumerate(bi):
        if ka not in A or kb not in B:
            print(f"  case {ka} (b {kb}) not judged in both looks")
            continue
        ia, ib = l9_items(A[ka]), l9_items(B[kb])
        pairs, ua, ub = [], list(range(len(ia))), list(range(len(ib)))
        for rule in ("place", "mob"):
            for i in list(ua):
                for j in list(ub):
                    ma, mb = ia[i], ib[j]
                    ok = (ma[1] is not None and mb[1] is not None and abs(ma[1] - mb[1]) <= 2) if rule == "place" \
                        else (ma[0] == mb[0] and not q(ma[0]))
                    if ok:
                        pairs.append((ma, mb))
                        ua.remove(i)
                        ub.remove(j)
                        break
        if len(ua) == 1 and len(ub) == 1:
            pairs.append((ia[ua[0]], ib[ub[0]]))
            ua, ub = [], []
        cnt["meters in one look only"] += len(ua) + len(ub)
        diffs += [(ka, "a only", ia[i]) for i in ua] + [(ka, "b only", ib[j]) for j in ub]
        for ma, mb in pairs:
            cnt["meters paired"] += 1
            for what, va, vb in (("mob", ma[0], mb[0]), ("fill", ma[2], mb[2])):
                if q(va) and q(vb):
                    cnt[f"{what}: both '?'"] += 1
                elif q(va) or q(vb):
                    cnt[f"{what}: a '?' against an answer"] += 1
                    diffs.append((ka, f"{what} ? against an answer", ma, mb))
                else:
                    same = va == vb if what == "mob" else abs(va - vb) <= 3
                    cnt[f"{what}: both answered"] += 1
                    cnt[f"{what}: agree"] += same
                    if not same:
                        diffs.append((ka, what, ma, mb))
    both = cnt["mob: both answered"] + cnt["fill: both answered"]
    agree = cnt["mob: agree"] + cnt["fill: agree"]
    print(f"L9 second look: {len(bi)} cases; {dict(sorted(cnt.items()))}")
    print(f"  items both looks answered: {agree} of {both} agree ({100 * agree / max(1, both):.1f} %; the gate >= 95 %)")
    for d in diffs:
        print("   ", d)


def l9_write() -> None:
    """The first look's judgments -> CORPUS/labels/SESSION#K/labels/L9.json (labels.json v2, as label_sets.py writes
    L1-L8: per frame "mobs" (each meter's mob: its screen feet, type, the tracker's track, the meter's fill and its
    place on the strip), "unsure", "false")."""
    import corpus
    cases = json.loads((L9_DIR / "cases.json").read_text(encoding="utf-8"))
    A = l9_judged("a")
    bi = json.loads((L9_DIR / "b_cases.json").read_text(encoding="utf-8"))
    per = {}
    for k, c in enumerate(cases):
        if k not in A:
            raise SystemExit(f"L9: case {k} not judged")
        mobs, unsure = [], []
        info = {m["letter"]: m for m in c["mobs"]}
        for lab in A[k].get("meters") or []:
            m = info.get(lab.get("mob"))
            e = {"meter": {"fill": _num(lab.get("fill")), "L": _num(lab.get("L")), "R": _num(lab.get("R")),
                           "band": lab.get("band", True)}, "mob": lab.get("mob")}
            if m is None:
                unsure.append(e)
            else:
                mobs.append(dict(e, feet=m["feet"], type=m["kind"], cls="", track=m["track"],
                                 band_at=m["band"]))
        per.setdefault(c["cap"], {})[str(c["n"])] = {"mobs": mobs, "unsure": unsure, "false": [], "case": k,
                                                      "looks": 2 if k in bi else 1, "tags": c["tags"]}
    for cap, frames in per.items():
        p = corpus.labels_dir(cap) / "labels" / "L9.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"v": 2, "set": "L9", "run": cap, "by": "Claude labellers, by eye (PLAN-tracker step "
                                 "5a, 2026-11-26)", "frames": frames}, indent=1), encoding="utf-8")
        print(f"  L9: {len(frames)} frames -> {p}")


def cmd_l9(what: str, caps: list) -> None:
    L9_DIR.mkdir(parents=True, exist_ok=True)
    if what == "pick":
        cases = l9_pick(caps)
        infos = l9_sheets(cases, "a")
        for c_, i_ in zip(cases, infos):
            c_["mobs"] = i_
            c_["chain"] = list(c_["chain"])
        (L9_DIR / "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
        import random
        rb = random.Random(7)
        bi = rb.sample(range(len(cases)), max(1, len(cases) // 10))
        rb.shuffle(bi)
        (L9_DIR / "b_cases.json").write_text(json.dumps(bi), encoding="utf-8")
        l9_sheets([cases[k] for k in bi], "b")
        tags = Counter(t for c_ in cases for t in c_["tags"])
        kinds = Counter(GEO.name(c_["kind"]) if c_["kind"] else "?" for c_ in cases)
        print(f"L9: {len(cases)} cases ({len(set(c_['cap'] for c_ in cases))} captures); tags {dict(tags)}; kinds "
              f"{dict(kinds)}; b: {len(bi)} cases -> {L9_DIR}")
    elif what == "agree":
        l9_agree()
    elif what == "more":
        l9_more(12)
    elif what == "write":
        sys.path.insert(0, str(ROOT / "tools" / "data"))
        l9_write()
    else:
        raise SystemExit(what)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what")
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--jobs", type=int, default=1)
    a = ap.parse_args()
    caps = list(cache.SOUND) if a.sound else a.caps
    if a.what == "scan":
        scan(caps, a.jobs)
    elif a.what == "place":
        measure_place(caps)
    elif a.what == "when":
        measure_when(caps)
    elif a.what == "picture":
        measure_picture(caps)
    elif a.what == "ties":
        measure_ties(caps)
    elif a.what == "new":
        measure_new(caps)
    elif a.what == "starts":
        measure_starts(caps)
    elif a.what == "l9":
        cmd_l9(a.caps[0], list(cache.SOUND))
    elif a.what == "sheet":
        cmd_sheet(a.caps[0], int(a.caps[1]) if len(a.caps) > 1 else 6)
    else:
        raise SystemExit(f"unknown: {a.what}")


if __name__ == "__main__":
    main()
