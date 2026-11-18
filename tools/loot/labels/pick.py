"""PLAN-loot.md S5: the by-eye labels of resting drops on the native recordings (the reference = Claude's labels).

    python tools/loot/labels/pick.py pick     -> tools/loot/labels/picks.json (~200 frames, even + hard picks)
    python tools/loot/labels/pick.py sheets   -> runs/loot_labels/sheets/<i>.png + tools/loot/labels/patches.json
    python tools/loot/labels/pick.py legend   -> runs/loot_labels/legend.png (the item codes of judgments.txt)
    python tools/loot/labels/pick.py build    -> judgments.txt -> RUN/loot/labels.json + tools/loot/labels/<run>.json
    python tools/loot/labels/pick.py zoom 12:C 12@x,y,w,h ...   -> runs/loot_labels/zoom.png (5x crops, for the eye)
    python tools/loot/labels/pick.py check moved|low|unsure     -> runs/loot_labels/check_*.png (frame -0.3 / 0 / +0.3)

PICK (frames only; the finder's find_v4 sightings are used to FIND hard moments, never as truth): per recording 10
even frames (Dark Cave 4, it ends at 16.3 s) + hard ones: kills (0.8 s after a mob's first dying tick: drops in
flight), pickups (0.2 s after a resting group's last sighting), piles (2+ resting sightings <= 30 px apart), covered
(a resting group's item unseen inside its life: tooltips, digits, chat), players (another name tag on screen),
drop-free (no sighting within 2 s), the open inventory (012059_1 t 84-87).
SHEETS: the scene's residue = |frame - expected| > 4 on known scenery in the world, minus the mob fit's explained
pixels; blobs (5x5 closed) of >= 25 px, lettered; each tile = the blob's box + 6 px at 3x (2x / 1x when large); a
0.45x thumbnail with the letters, unknown scenery tinted (0 % of the world on 6 maps' picks, <= 10 % on Transfer);
pages of 2-3 frames in runs/loot_labels/pages. Never the finder's boxes.
JUDGMENTS (tools/loot/labels/judgments.txt, written by eye): one line a frame `<i>: <letter>=<entry>[+<entry>] ...`
  entry  d:<cls>:<item>   a drop; cls clear / auto (resting or moving: the build measures it) / pile.<visible
                          share> / front.<v> / ui.<v> / cover.<v> / mobover.<v> / effect / edge / flight / pickup;
                          item = a legend code (m0..m3 = meso bronze / gold / bundle / sack), a number = an item id,
                          ? = not readable
         n:<cls>          a not-drop region (the blob's box): worn / window / mobpart / other
  `@x,y=<entry>` = a drop with no blob of its own (screen point, snapped within 20 + 12 px)
  letters not named = nothing drop-like (digits, effects, text, the cursor, characters without a call)
BUILD: a drop with an item is snapped to its exact place inside its blob (+12 px): the position where the most of
the picture's opaque pixels show exactly (+-4; mesos: the best of the 4 frames); a blob's items best-showing first
(a pile's top item), each one's pixels taken from the next; feet = the picture's bottom-centre (as the finder's);
snap = that share of the opaque pixels = the drop's `vis` (the eye's share kept as `vis_eye`).
MOTION (a single frame cannot show it): a resting-class drop is looked for at the same MAP place (box centre x +-1.5,
bottom +-6, >= 0.8 x its own snap) in the saved frames 0.3 / 0.6 s before and after; < 2 of them -> class `unsure`
(not graded; on these recordings: flights 24-252 px above the foothold, landing / pickup instants); `auto` -> clear.
"clear" with snap < 0.5 -> pile (under another labelled drop) / covered. Without an item: feet = the blob's
bottom-centre (`snap` None). tools/loot/labels/adjudicated.json: drops the blind labels missed, found on the first
eval's FALSE sheet (drop_eval adds them as class `added`: not false, never in recall).
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from lootlib import Footholds, frame, map_of, run_ticks, world_mask, PLAY_H, ROOT, SW  # noqa: E402

RUNS = {"154819_1": "runs/play/20261116_154819_1", "084844_2": "runs/play/20261116_084844_2",
        "085108_3": "runs/play/20261116_085108_3", "085215_4": "runs/play/20261116_085215_4",
        "084719_1": "runs/play/20261116_084719_1", "092718_1": "runs/play/20261117_092718_1",
        "094333_1": "runs/v2/20261117_094333_1", "111248_1": "runs/v2/20261117_111248_1",
        "012059_1": "runs/play/20261116_012059_1"}
T1 = {"084719_1": 16.3}
OUT = ROOT / "runs" / "loot_labels"
LEGEND = {"m0": 9000000, "m1": 9000001, "m2": 9000002, "m3": 9000003, "hmc": 4000019, "cu": 4000020,
          "po": 2000001, "pb": 2000003, "pr": 2000000, "pw": 2000002, "pd": 2002003, "ab": 2060000, "ac": 2061000,
          "fm": 4000063, "bo": 4010000, "io": 4010001, "sw": 4000017, "bub": 4000014, "omc": 4000009,
          "ms": 4000003}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def rows_of(key):
    run = ROOT / RUNS[key]
    rows = [json.loads(l) for l in open(run / "loot" / "find_v4.jsonl", encoding="utf-8")]
    return [r for r in rows if r.get("cam") is not None and r.get("drops") is not None and r["t"] <= T1.get(key, 1e9)]


# ------------------------------------------------------------------ pick
def pick():
    picks = []
    for key, rp in RUNS.items():
        run = ROOT / rp
        rows = rows_of(key)
        fh = Footholds(map_of(run))
        ts = np.array([r["t"] for r in rows])
        near = lambda t: int(np.argmin(np.abs(ts - t)))  # noqa: E731
        chosen = {}

        def add(i, why):
            if all(abs(rows[i]["t"] - rows[j]["t"]) >= 0.3 for j in chosen) or i in chosen:
                chosen.setdefault(i, why)

        n_even = 4 if key in T1 else 10
        for i in np.linspace(0, len(rows) - 1, n_even + 2)[1:-1].astype(int):
            add(int(i), "even")
        # resting sightings -> groups (item, map x +-2)
        groups, rest_rows = defaultdict(list), defaultdict(list)
        for i, r in enumerate(rows):
            C = r["cam"]
            for d in r["drops"]:
                x, y, w, h = d["box"]
                u = fh.under(x + w / 2 + C[0], y + h + C[1])
                if u is None or not -7 <= y + h + C[1] - u[0] <= 5:
                    continue
                mx = x + w / 2 + C[0]
                g = next((g for g in groups if g[0] == d["item"] and abs(g[1] - mx) <= 2), None) or (d["item"], mx)
                groups[g].append(i)
                rest_rows[i].append((x + w / 2, y + h))
        big = {g: v for g, v in groups.items() if len(v) >= 20}
        hard = []
        # kills: a mob's first dying tick + 0.8 s
        seen_dead = set()
        for k in run_ticks(run):
            for m in k["mobs"]:
                if m.get("state") == "dying" and m.get("id") not in seen_dead and k["t"] is not None:
                    seen_dead.add(m.get("id"))
                    hard.append(("kill", k["t"] + 0.8))
        # pickups: 0.2 s after a group's last sighting (not at the run's end)
        for g, v in big.items():
            if rows[v[-1]]["t"] < ts[-1] - 1:
                hard.append(("pickup", rows[v[-1]]["t"] + 0.2))
        # piles
        for i, p in rest_rows.items():
            if any(abs(a[0] - b[0]) <= 30 and abs(a[1] - b[1]) <= 8 for j, a in enumerate(p) for b in p[j + 1:]):
                hard.append(("pile", rows[i]["t"]))
        # covered: a group's item unseen inside its life
        for g, v in big.items():
            s = set(v)
            gap = [i for i in range(v[0], v[-1]) if i not in s]
            if gap:
                hard.append(("covered", rows[gap[len(gap) // 2]]["t"]))
        # players: another name tag on screen
        tk ={k["frame"]: k for k in run_ticks(run)}
        for r in rows:
            k = tk.get(r["frame"]) or {}
            if len((k.get("facts") or {}).get("tags") or []) >= 1 or (k["obs"].get("n_tags") or 0) >= 2:
                hard.append(("player", r["t"]))
        # drop-free: no sighting within 2 s
        has = np.array([bool(r["drops"]) for r in rows])
        for i in range(len(rows)):
            lo, hi = np.searchsorted(ts, ts[i] - 2), np.searchsorted(ts, ts[i] + 2)
            if not has[lo:hi].any():
                hard.append(("free", ts[i]))
        if key == "012059_1":
            for t in (84.2, 85.4, 86.6):
                add(near(t), "window")
        rng = np.random.default_rng(17)
        caps = {"kill": 3, "pickup": 3, "pile": 3, "covered": 3, "player": 2, "free": 2}
        for why, cap in caps.items():
            cand = [t for w, t in hard if w == why]
            if not cand:
                continue
            got = 0
            for t in rng.permutation(cand):
                if got >= cap:
                    break
                i = near(t)
                if i not in chosen and all(abs(rows[i]["t"] - rows[j]["t"]) >= 0.3 for j in chosen):
                    chosen[i] = why
                    got += 1
        for i, why in sorted(chosen.items()):
            picks.append({"run": key, "frame": rows[i]["frame"], "t": round(rows[i]["t"], 2), "cam": rows[i]["cam"],
                          "why": why})
    for j, p in enumerate(picks):
        p["i"] = j
    (HERE / "picks.json").write_text(json.dumps(picks, indent=0), encoding="utf-8")
    from collections import Counter
    print(len(picks), "frames;", dict(Counter(p["why"] for p in picks)), dict(Counter(p["run"] for p in picks)))


# ------------------------------------------------------------------ sheets
def sheets(only=None):
    import torch
    from maplebrain.scene import Scene
    from maplebrain.perception.fit import Fitter
    picks = json.loads((HERE / "picks.json").read_text(encoding="utf-8"))
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    pp = HERE / "patches.json"
    patches = json.loads(pp.read_text(encoding="utf-8")) if pp.exists() else {}
    scenes, fitters, worlds, tks = {}, {}, {}, {}
    page = []

    def flush(pg):
        if pg:
            img = np.concatenate([np.pad(o, ((0, 6), (0, 0), (0, 0)), constant_values=90) for _, o in pg])
            cv2.imwrite(str(OUT / "pages" / f"p{pg[0][0]:03d}-{pg[-1][0]:03d}.png"), img)
            pg.clear()
    (OUT / "pages").mkdir(parents=True, exist_ok=True)
    for p in picks:
        if only is not None and p["i"] not in only:
            continue
        run = ROOT / RUNS[p["run"]]
        mid = map_of(run)
        if mid not in scenes:
            scenes[mid] = Scene.load(mid)
            fitters[mid] = Fitter(scenes[mid], mid, ROOT / "assets" / "mcw")
            fitters[mid].warm()
        sc, ft_ = scenes[mid], fitters[mid]
        f = frame(run, p["frame"])
        if mid not in worlds:
            worlds[mid] = world_mask(mid, f.shape)
        world = worlds[mid]
        C = tuple(p["cam"])
        ftt = torch.from_numpy(np.ascontiguousarray(f)).to(sc.dev)
        exp, known = sc.expected(C)
        wt = torch.from_numpy(np.ascontiguousarray(world)).to(sc.dev)
        if p["run"] not in tks:
            tks[p["run"]] = {k["frame"]: k for k in run_ticks(run)}
        m = (tks[p["run"]].get(p["frame"]) or {}).get("me")
        me = None if not m else (m[0] - 40, m[1] - 85, m[0] + 40, m[1] + 30)
        ft_.fit(ftt[:PLAY_H], C, exp, known, wt, me)
        Pd = max(ft_.KH, ft_.KW)
        taken = ft_.taken[Pd:Pd + PLAY_H, Pd:Pd + SW] if ft_.taken is not None else np.zeros((PLAY_H, SW), bool)
        R = (((ftt[:PLAY_H].float() - exp).abs().amax(dim=2) > 4) & known & wt).cpu().numpy() & ~taken
        unk = (~known.cpu().numpy()) & world
        Rc = cv2.morphologyEx(R.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(Rc, connectivity=8)
        blobs = [tuple(int(v) for v in st[i]) for i in range(1, n) if st[i][4] >= 25]
        blobs.sort(key=lambda b: (b[0], b[1]))
        blobs = blobs[:len(LETTERS)]
        # thumbnail
        th = f[:PLAY_H].copy()
        tint = th.copy()
        tint[unk] = (tint[unk] * 0.5 + np.array([120, 40, 0]) * 0.5).astype(np.uint8)
        th = tint
        for j, (x, y, w, h, _) in enumerate(blobs):
            cv2.rectangle(th, (x - 1, y - 1), (x + w, y + h), (0, 255, 255), 1)
            cv2.putText(th, LETTERS[j], (x, max(10, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4)
            cv2.putText(th, LETTERS[j], (x, max(10, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        th = cv2.resize(th, None, fx=0.45, fy=0.45, interpolation=cv2.INTER_AREA)
        tiles = []
        for j, (x, y, w, h, _) in enumerate(blobs):
            x0, y0, x1, y1 = max(0, x - 6), max(0, y - 6), min(SW, x + w + 6), min(PLAY_H, y + h + 6)
            mside = max(x1 - x0, y1 - y0)
            s = 3 if mside <= 50 else 2 if mside <= 90 else 1
            if mside > 300:
                continue
            t = cv2.resize(f[y0:y1, x0:x1], None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
            t = cv2.copyMakeBorder(t, 18, 0, 0, 0, cv2.BORDER_CONSTANT, value=(40, 40, 40))
            cv2.putText(t, f"{LETTERS[j]} {s}x", (2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            tiles.append(t)
        W = 1400
        rows_, cur, cw = [], [], 0
        for t in tiles:
            if cw + t.shape[1] + 4 > W and cur:
                rows_.append(cur)
                cur, cw = [], 0
            cur.append(t)
            cw += t.shape[1] + 4
        if cur:
            rows_.append(cur)
        H = th.shape[0] + 24 + sum(max(t.shape[0] for t in r) + 4 for r in rows_)
        out = np.full((H, W, 3), 25, np.uint8)
        cv2.putText(out, f"#{p['i']} {p['run']} {p['frame']} t {p['t']} ({p['why']}) map {mid}", (4, 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        out[24:24 + th.shape[0], :th.shape[1]] = th
        yy = 24 + th.shape[0]
        for r in rows_:
            xx = 0
            for t in r:
                out[yy:yy + t.shape[0], xx:xx + t.shape[1]] = t
                xx += t.shape[1] + 4
            yy += max(t.shape[0] for t in r) + 4
        cv2.imwrite(str(OUT / "sheets" / f"{p['i']:03d}.png"), out)
        page.append((p["i"], out))
        if sum(o.shape[0] for _, o in page) > 1100:
            flush(page)
        patches[str(p["i"])] = {"run": p["run"], "frame": p["frame"], "cam": p["cam"], "map": mid,
                                "blobs": {LETTERS[j]: list(b[:4]) for j, b in enumerate(blobs)},
                                "unknown_share": round(float(unk.sum()) / max(1, world.sum()), 3)}
        print(p["i"], p["run"], p["frame"], len(blobs), "blobs", flush=True)
    flush(page)
    pp.write_text(json.dumps(patches), encoding="utf-8")


# ------------------------------------------------------------------ legend
def legend():
    from maplebrain.gamedata import load_items
    it = load_items()
    tiles, labels = [], []
    for code, iid in LEGEND.items():
        e = it.meta[str(iid)]
        g = (e.get("frames") or [{"g": e["g"]}])[0]["g"]
        p = it.pics[g]
        t = np.full((p.shape[0] + 4, p.shape[1] + 4, 3), 90, np.uint8)
        a = p[..., 3:4] / 255.0
        t[2:-2, 2:-2] = (p[..., :3] * a + t[2:-2, 2:-2] * (1 - a)).astype(np.uint8)
        tiles.append(t)
        labels.append(code)
    from lootlib import sheet
    OUT.mkdir(exist_ok=True)
    cv2.imwrite(str(OUT / "legend.png"), sheet(tiles, cols=10, labels=labels, scale=3))


# ------------------------------------------------------------------ build
def snap(f, pics, box, taken, pad=12, padx=None):
    """-> (share, x, y, w, h, gi) the best place of any of `pics` [(gi, BGRA)] inside box + pad: the share of the
    picture's opaque pixels the frame shows exactly (+-4), pixels in `taken` (earlier snaps) not counted."""
    from numpy.lib.stride_tricks import sliding_window_view as win
    x, y, w, h = box
    best = (-1.0, 0, 0, 0, 0, None)
    for gi, p in pics:
        ph, pw = p.shape[:2]
        px = pad if padx is None else padx
        y0, x0 = max(0, y - pad), max(0, x + (w - pw) // 2 - px if padx is not None else x - pad)
        y1, x1 = min(PLAY_H, y + h + pad), min(SW, x + (w + pw) // 2 + px + 1 if padx is not None else x + w + pad)
        if y1 - y0 < ph or x1 - x0 < pw:
            continue
        op = p[..., 3] == 255
        F = f[y0:y1, x0:x1].astype(np.int16)
        ok = (np.abs(win(F, (ph, pw), axis=(0, 1)).transpose(0, 1, 3, 4, 2) - p[..., :3]).max(-1) <= 4)
        ok &= op & ~win(taken[y0:y1, x0:x1], (ph, pw), axis=(0, 1))
        sc = ok.sum((2, 3)) / max(1, int(op.sum()))
        j = np.unravel_index(int(np.argmax(sc)), sc.shape)
        if sc[j] > best[0]:
            best = (float(sc[j]), x0 + int(j[1]), y0 + int(j[0]), pw, ph, gi)
    return best


def overlap_(a, b) -> float:
    """Share of box a (x, y, w, h) covered by box b."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return max(0, x1 - x0) * max(0, y1 - y0) / max(1, a[2] * a[3])


def still(it, key, name, d, rows, gs, dts=(-0.6, -0.3, 0.3, 0.6)):
    """Is the drop at the same MAP place (box centre x +-1.5, bottom +-6) in any saved frame ~0.3 / 0.6 s before or
    after? -> (hits, looked). A resting drop stays put (bob 5-6 px); a flight / hop is elsewhere 0.3 s later."""
    r = rows[name]
    i = r["i"]
    ts = rows["_t"]
    same = looked = 0
    for t in (r["t"] + v for v in dts):
        j = int(np.argmin(np.abs(ts - t)))
        if j == i or abs(ts[j] - t) > 0.15:
            continue
        q = rows["_rows"][j]
        g = frame(ROOT / RUNS[key], q["frame"])
        dx, dy = q["cam"][0] - r["cam"][0], q["cam"][1] - r["cam"][1]
        x, y, w, h = d["box"]
        s, xx, yy, pw, ph, _ = snap(g, [(k, it.pics[k]) for k in gs], [x - dx, y - dy, w, h],
                                    np.zeros((PLAY_H, SW), bool), pad=6, padx=2)
        looked += 1                                 # box centres: meso frames differ in width and origin
        if s >= max(0.2, 0.8 * d["snap"]) and abs(xx + pw / 2 + dx - x - w / 2) <= 1.5 and abs(yy + ph + dy - y - h) <= 6:
            same += 1
    return same, looked


def build():
    from maplebrain.gamedata import load_items
    it = load_items()
    patches = json.loads((HERE / "patches.json").read_text(encoding="utf-8"))
    out = defaultdict(dict)
    rowsk = {}
    for line in (HERE / "judgments.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        i, body = line.split(":", 1)
        P = patches[i.strip()]
        run = ROOT / RUNS[P["run"]]
        f = frame(run, P["frame"])
        taken = np.zeros((PLAY_H, SW), bool)
        drops, nots = [], []
        for tok in body.split():
            todo = []
            where, ent = tok.split("=", 1)
            if where.startswith("@"):
                px, py = (int(v) for v in where[1:].split(","))
                box = [px - 20, py - 20, 40, 40]
            else:
                box = P["blobs"][where]
            for e in ent.split("+"):
                parts = e.split(":")
                if parts[0] == "n":
                    nots.append({"cls": parts[1], "box": box, "src": where})
                    continue
                cls, item = parts[1], parts[2] if len(parts) > 2 else "?"
                n = 1
                if "*" in item:
                    item, n = item.split("*")
                    n = int(n)
                vis = None
                if "." in cls:                       # pile.8 / front.7 / ui.4 / cover.8 / mobover.7: visible share
                    cls, v = cls.split(".")
                    vis = float("0." + v)
                iid = LEGEND.get(item) if item in LEGEND else (int(item) if item.isdigit() else None)
                for _ in range(n):
                    todo.append(({"cls": cls, "vis": vis, "item": iid, "src": where}, box))
            # a blob's items: snap the best-showing one first (a pile's top item), its pixels taken, then the next
            while todo:
                best = None
                for k, (d, box) in enumerate(todo):
                    if d["item"] is None:
                        best = (2.0, k, None)
                        break
                    e_ = it.meta[str(d["item"])]
                    gs = [fr["g"] for fr in e_.get("frames") or []] or [e_["g"]]
                    sn = snap(f, [(g, it.pics[g]) for g in gs], box, taken)
                    if best is None or sn[0] > best[0]:
                        best = (sn[0], k, (sn, gs))
                d, box = todo.pop(best[1])
                if d["item"] is None:
                    x, y, w, h = box
                    d.update(box=list(box), feet=[x + w // 2, y + h], snap=None)
                    drops.append(d)
                    continue
                (s, xx, yy, pw, ph, gi), gs = best[2]
                p = it.pics[gi]
                taken[yy:yy + ph, xx:xx + pw] |= p[..., 3] == 255
                d.update(box=[xx, yy, pw, ph], feet=[xx + pw // 2, yy + ph], snap=round(float(s), 2),
                         f=int(it.f[gi]), same=int(it.meta[str(d["item"])]["same"]))
                if d["cls"] in ("auto", "clear", "pile", "front", "ui", "effect", "cover", "mobover", "edge"):
                    if P["run"] not in rowsk:
                        rr = rows_of(P["run"])
                        rowsk[P["run"]] = {**{q["frame"]: {**q, "i": k} for k, q in enumerate(rr)},
                                           "_t": np.array([q["t"] for q in rr]), "_rows": rr}
                    sm, lk = still(it, P["run"], P["frame"], d, rowsk[P["run"]], gs)
                    d["still"] = [sm, lk]
                    if d["cls"] == "auto":
                        d["cls"] = "clear"
                        d["auto"] = True
                    # >= 2 confirmations: a flight can pass one spot twice (up, down), never three times in 1.2 s
                    if d["cls"] in ("clear", "pile") and sm < 2 and lk:
                        d["cls"], d["was"] = "unsure", d["cls"]     # not confirmed resting: not graded as resting
                d["vis_eye"], d["vis"] = d["vis"], d["snap"]        # visible share = measured (my picture, my blob)
                drops.append(d)
        for d in drops:                                    # "clear" by eye but < 50 % shows: under a drop / covered
            if d["cls"] == "clear" and d["snap"] is not None and d["snap"] < 0.5:
                over = any(o is not d and o.get("box") and overlap_(d["box"], o["box"]) >= 0.15 for o in drops)
                d["cls"], d["was"] = ("pile" if over else "covered"), "clear"
        out[P["run"]][P["frame"]] = {"i": int(i), "t": None, "cam": P["cam"], "drops": drops, "notdrops": nots}
    picks = {(p["run"], p["frame"]): p for p in json.loads((HERE / "picks.json").read_text(encoding="utf-8"))}
    for key, fr in out.items():
        for name, L in fr.items():
            L["t"] = picks[(key, name)]["t"]
            L["why"] = picks[(key, name)]["why"]
        doc = {"run": RUNS[key], "by": "Claude, by eye (PLAN-loot.md S5)", "frames": fr}
        s = json.dumps(doc, indent=0)
        (ROOT / RUNS[key] / "loot" / "labels.json").write_text(s, encoding="utf-8")
        (HERE / f"{key}.json").write_text(s, encoding="utf-8")
        low = [(L["i"], d["src"], d["item"], d["snap"]) for name, L in fr.items() for d in L["drops"]
               if d["snap"] is not None and d["snap"] < 0.3]
        moving = [(L["i"], d["src"], d["item"], d["cls"], d["still"]) for L in fr.values() for d in L["drops"]
                  if not d.get("auto") and d.get("still") and d["still"][0] == 0]
        from collections import Counter
        print(key, len(fr), "frames,", sum(len(L["drops"]) for L in fr.values()), "drops",
              dict(Counter(d["cls"] for L in fr.values() for d in L["drops"])), "|",
              sum(len(L["notdrops"]) for L in fr.values()), "not-drops")
        print("   snaps < 0.3:", low)
        print("   judged resting but moved in a neighbour frame:", moving)


def zoom(specs, scale=5, pad=16):
    """`i:L` (a blob) or `i@x,y,w,h` (a screen box) ... -> runs/loot_labels/zoom.png, each crop + pad at `scale`x."""
    from lootlib import sheet
    patches = json.loads((HERE / "patches.json").read_text(encoding="utf-8"))
    tiles, labels = [], []
    for sp in specs:
        i, L = re.split(r"[:@]", sp, maxsplit=1)
        P = patches[i]
        x, y, w, h = P["blobs"][L] if ":" in sp else [int(v) for v in L.split(",")]
        f = frame(ROOT / RUNS[P["run"]], P["frame"])
        x0, y0 = max(0, x - pad), max(0, y - pad)
        tiles.append(f[y0:min(PLAY_H, y + h + pad), x0:min(SW, x + w + pad)])
        labels.append(f"{sp} ({x0},{y0})")
    cv2.imwrite(str(OUT / "zoom.png"), sheet(tiles, cols=max(1, min(len(tiles), 1400 // (max(t.shape[1] for t in tiles) * scale + 8))),
                                             labels=labels, scale=scale))


def check(which="moved"):
    """Pictures of the labels to look at again: per drop its frame (the snapped box drawn) + the frames ~0.3 s before
    / after at the same map place -> runs/loot_labels/check_<n>.png. which = moved (judged resting, moved in a
    neighbour) / low (snap < 0.3)."""
    from lootlib import sheet
    tiles, labels = [], []
    for key in RUNS:
        doc = json.loads((HERE / f"{key}.json").read_text(encoding="utf-8")) if (HERE / f"{key}.json").exists() else None
        if not doc:
            continue
        rr = rows_of(key)
        ts = np.array([q["t"] for q in rr])
        idx = {q["frame"]: k for k, q in enumerate(rr)}
        for name, L in doc["frames"].items():
            for d in L["drops"]:
                pick_ = (which == "moved" and not d.get("auto") and d.get("still") and d["still"][0] == 0) \
                    or (which == "low" and d["snap"] is not None and d["snap"] < 0.3)                    or (which == "unsure" and d["cls"] == "unsure")
                if not pick_:
                    continue
                r = rr[idx[name]]
                x, y, w, h = d["box"]
                for k, t in enumerate((r["t"] - 0.3, r["t"], r["t"] + 0.3)):
                    q = rr[int(np.argmin(np.abs(ts - t)))]
                    dx, dy = q["cam"][0] - r["cam"][0], q["cam"][1] - r["cam"][1]
                    g = frame(ROOT / RUNS[key], q["frame"])[:PLAY_H].copy()
                    if k == 1:
                        cv2.rectangle(g, (x - 1, y - 1), (x + w, y + h), (0, 0, 255), 1)
                    cx, cy = x - dx + w // 2, y - dy + h // 2
                    x0, y0 = max(0, min(SW - 64, cx - 32)), max(0, min(PLAY_H - 64, cy - 32))
                    tiles.append(g[y0:y0 + 64, x0:x0 + 64])
                    labels.append(f"{L['i']}{d['src']} {d['item'] % 100000} {d['snap']}" if k == 1 else ("-0.3" if k == 0 else "+0.3"))
    for j in range(0, len(tiles), 60):
        cv2.imwrite(str(OUT / f"check_{which}_{j // 60}.png"), sheet(tiles[j:j + 60], cols=12, labels=labels[j:j + 60], scale=2))
    print(len(tiles) // 3, "drops ->", OUT)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "pick":
        pick()
    elif cmd == "sheets":
        sheets({int(v) for v in sys.argv[2].split(",")} if len(sys.argv) > 2 else None)
    elif cmd == "legend":
        legend()
    elif cmd == "build":
        build()
    elif cmd == "check":
        check(sys.argv[2])
    elif cmd == "zoom":
        zoom(sys.argv[2:])
