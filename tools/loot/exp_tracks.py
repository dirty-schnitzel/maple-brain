"""E-L3 (PLAN-loot.md): the finder's sightings joined into DROPS over time (offline, for measuring - not the tracker).

    python tools/loot/exp_tracks.py RUN [--find NAME] [--save]

A drop = sightings of one item at one map x (+-2 px) within +-10 px of y, not unseen for more than `gap` s while its
spot was on screen. Per run it prints:
  - drops by item; drops on screen per frame;
  - the bob: y range per drop, the y values' histogram around the resting y, the period (long drops);
  - the resting position vs the foothold under it (map.json);
  - meso frames: the frame sequence and how long each shows;
  - how a drop is seen while in view: share of in-view frames sighted, the SEEN share (covered by what: see --save);
  - how it ends: left the screen / the run ended / gone while in view (picked up, expired).
--save: RUN/loot/tracks_<NAME>.json (every drop: item, map x, y0, first / last t, frames seen / in view, end).
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, map_of, PLAY_H, SW, ROOT  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--find", default="all")
ap.add_argument("--gap", type=float, default=2.0)
ap.add_argument("--save", action="store_true")
a = ap.parse_args()
run = Path(a.run)
it = Items()
rows = [json.loads(l) for l in open(run / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("drops") is not None]
mp = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_of(run)) / "map.json").read_text(encoding="utf-8"))
FH = np.array([[f["x1"], f["y1"], f["x2"], f["y2"]] if f["x1"] < f["x2"] else [f["x2"], f["y2"], f["x1"], f["y1"]]
               for f in (mp.get("footholds") or {}).values() if f["x1"] != f["x2"]], float)


def ground(mx, my):
    """y of the nearest foothold at / below map (mx, my - 12), or None."""
    on = (FH[:, 0] <= mx) & (FH[:, 2] >= mx)
    if not on.any():
        return None
    ya = FH[on, 1] + (mx - FH[on, 0]) * (FH[on, 3] - FH[on, 1]) / (FH[on, 2] - FH[on, 0])
    below = ya >= my - 12
    return float(ya[below].min()) if below.any() else None


def in_view(tr, cam):
    """The drop's box wholly inside the play area (not under the HUD strip) for camera `cam`."""
    x, y = tr["mx"] - cam[0], tr["y0"] - cam[1]
    return 4 <= x and x + tr["w"] <= SW - 4 and 40 <= y - tr["h"] and y + 6 <= PLAY_H


tracks, open_ = [], []
for fi, r in enumerate(rows):
    cam, t = r["cam"], r["t"]
    for d in r["drops"]:
        mx, my = d["pos"][0] + cam[0], d["pos"][1] + cam[1]
        best = None
        for tr in open_:
            if tr["item"] == d["item"] and abs(tr["mx"] - mx) <= 2 and abs(tr["y0"] - my) <= 10 and tr["last_fi"] != fi:
                if best is None or abs(tr["mx"] - mx) < abs(best["mx"] - mx):
                    best = tr
        if best is None:
            best = {"item": d["item"], "mx": mx, "y0": my, "w": d["box"][2], "h": d["box"][3], "t0": t, "obs": [],
                    "last_fi": -1, "fi0": fi}
            open_.append(best)
            tracks.append(best)
        best["obs"].append((fi, t, my, d["f"], d["n_seen"] / max(1, d["n_op"]), mx))
        best["last_fi"], best["t1"] = fi, t
    # close: unseen for > gap s over frames where it was in view
    keep = []
    for tr in open_:
        if t - tr["t1"] > a.gap:
            continue
        keep.append(tr)
    open_ = keep
# per track: the resting y = the lowest (max) y it shows (the bob's bottom), in-view frames, the end
t_end = rows[-1]["t"]
for tr in tracks:
    ys = np.array([o[2] for o in tr["obs"]])
    tr["ymax"], tr["ymin"] = float(ys.max()), float(ys.min())
    f0, f1 = tr["fi0"], tr["last_fi"]
    tr["y0"] = tr["ymax"]
    view = [fi for fi in range(f0, f1 + 1) if in_view(tr, rows[fi]["cam"])]
    seen = {o[0] for o in tr["obs"]}
    tr["n_view"], tr["n_seen"] = len(view), len(seen & set(view))
    after = [fi for fi in range(f1 + 1, min(len(rows), f1 + 40)) if rows[fi]["t"] - tr["t1"] <= a.gap]
    if tr["t1"] >= t_end - a.gap:
        tr["end"] = "run end"
    elif after and sum(in_view(tr, rows[fi]["cam"]) for fi in after) >= 0.7 * len(after):
        tr["end"] = "gone in view"
    else:
        tr["end"] = "left screen"
    tr["g"] = ground(tr["mx"], tr["ymax"])

long_ = [tr for tr in tracks if len(tr["obs"]) >= 5]
print(f"{run.name}: {len(rows)} frames, {sum(len(r['drops']) for r in rows)} sightings -> {len(tracks)} drops "
      f"({len(long_)} seen on >= 5 frames); on screen per frame p50 {np.median([len(r['drops']) for r in rows]):.0f} "
      f"max {max(len(r['drops']) for r in rows)}")
by = Counter(tr["item"] for tr in long_)
short = Counter(tr["item"] for tr in tracks if len(tr["obs"]) < 5)
print("drops by item (>= 5 frames | < 5 frames):")
for i in sorted(set(by) | set(short), key=lambda i: -by[i]):
    print(f"   {i:8d} {it.name(i)[:30]:30s} {it.kind(i):8s} {by[i]:4d} | {short[i]}")
# the bob
rng = np.array([tr["ymax"] - tr["ymin"] for tr in long_ if len(tr["obs"]) >= 40])
if len(rng):
    print(f"bob: y range of drops seen >= 40 frames (n {len(rng)}): {Counter(rng.astype(int).tolist()).most_common(8)}")
    off = Counter()
    for tr in long_:
        if len(tr["obs"]) >= 40:
            off.update(int(tr["ymax"] - o[2]) for o in tr["obs"])
    tot = sum(off.values())
    print("     px above the lowest y, share of frames:", {k: round(v / tot, 3) for k, v in sorted(off.items())})
    per = []
    for tr in long_:
        o = tr["obs"]
        if len(o) < 80:
            continue
        tt = np.array([x[1] for x in o])
        yy = tr["ymax"] - np.array([x[2] for x in o])
        low = tt[yy == 0]
        # times the drop comes back to its lowest y after having left it by >= 3 px
        marks, armed = [], False
        for ti, yi in zip(tt, yy):
            if yi >= 3:
                armed = True
            elif yi == 0 and armed:
                marks.append(ti)
                armed = False
        if len(marks) >= 3:
            per += np.diff(marks).tolist()
    if per:
        per = np.array(per)
        per = per[per < 4]
        print(f"     period (back at the lowest y after >= 3 px up), n {len(per)}: p10 {np.percentile(per, 10):.2f} p50 "
              f"{np.median(per):.2f} p90 {np.percentile(per, 90):.2f} s")
# the resting position vs the foothold
dg = np.array([tr["ymax"] - tr["g"] for tr in long_ if tr["g"] is not None and len(tr["obs"]) >= 40])
if len(dg):
    print(f"lowest pos y - foothold y (n {len(dg)}): {Counter(np.round(dg).astype(int).tolist()).most_common(8)}")
none_g = sum(1 for tr in long_ if tr["g"] is None)
print(f"     drops with no foothold under them: {none_g}")
dx = Counter()
for tr in long_:
    dx.update(int(round(o[5] - tr["mx"])) for o in tr["obs"])
print("x of the sightings - the drop's first x:", dict(sorted(dx.items())))
# meso frames
seq = defaultdict(list)
for tr in long_:
    if tr["item"] >= 9000000 and len(tr["obs"]) >= 40:
        o = tr["obs"]
        runs_, cur, t0 = [], o[0][3], o[0][1]
        for k in range(1, len(o)):
            if o[k][3] != cur:
                if o[k][1] - o[k - 1][1] < 0.12:
                    runs_.append((cur, o[k][1] - t0))
                cur, t0 = o[k][3], o[k][1]
        for f, dur in runs_[1:]:
            seq[(tr["item"], f)].append(dur)
for (i, f), d in sorted(seq.items()):
    print(f"meso {i} frame {f}: shown {np.median(d):.3f} s p50 (p10 {np.percentile(d, 10):.3f} p90 {np.percentile(d, 90):.3f}, n {len(d)})")
# sighted while in view
sv = np.array([tr["n_seen"] / max(1, tr["n_view"]) for tr in long_ if tr["n_view"] >= 20])
if len(sv):
    print(f"sighted on in-view frames between first and last sighting (drops in view >= 20 frames, n {len(sv)}): p5 "
          f"{np.percentile(sv, 5):.3f} p25 {np.percentile(sv, 25):.3f} p50 {np.median(sv):.3f}; pooled "
          f"{sum(tr['n_seen'] for tr in long_) / max(1, sum(tr['n_view'] for tr in long_)):.4f}")
sh = np.array([o[4] for tr in long_ for o in tr["obs"]])
print(f"SEEN share of the picture per sighting: 1.0 on {100 * (sh >= 0.999).mean():.1f} %, >= 0.9 {100 * (sh >= 0.9).mean():.1f} %, "
      f">= 0.5 {100 * (sh >= 0.5).mean():.1f} %, < 0.5 {100 * (sh < 0.5).mean():.1f} %")
ends = Counter(tr["end"] for tr in long_)
life = np.array([tr["t1"] - tr["t0"] for tr in long_ if tr["end"] == "gone in view"])
print(f"ends: {dict(ends)}" + (f"; 'gone in view' lifetimes p10 {np.percentile(life, 10):.1f} p50 {np.median(life):.1f} "
                               f"p90 {np.percentile(life, 90):.1f} max {life.max():.1f} s" if len(life) else ""))
if a.save:
    out = [{k: (v if k != "obs" else [[o[0], round(o[1], 3), o[2], o[3], round(o[4], 3)] for o in v])
            for k, v in tr.items() if k not in ("last_fi",)} for tr in tracks]
    (run / "loot" / f"tracks_{a.find}.json").write_text(json.dumps(out), encoding="utf-8")
    print("->", run / "loot" / f"tracks_{a.find}.json")
