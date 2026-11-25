"""PLAN-tracker step 3b, FIRST MEASURE: do new mobs appear on their spawn point? Every track the real mob tracker
(track/mobs.py, replay_mobs.py's output) bore "faded in", its first feet against map.json's spawn points of its kind.

    python tools/perc/track/proto_spawns.py measure [--tag s4b]          the distances, the points near each other
    python tools/perc/track/proto_spawns.py sheet [--tag s4b] [--n 30]   30 random matched births: frame + point drawn
    python tools/perc/track/proto_spawns.py beat [--tag s4b]             the time between spawns seen on one point, the
                                                                         10 s beat (numbers only)

A birth = the first row a track id is in (its x, y = the first sighting's feet, map px). Its kind = the kind on that
row and the final kind (the vote) are both kept. Spawn points: map.json `mobs` (hidden ones apart), x, y as given.
Distances in map px: d = the straight distance; dx, dy kept. Outputs: OUT/spawns_<tag>.pkl, OUT/sheet_<tag>/*.png
(OUT = CORPUS/work/track-plan/step3b).
"""
import argparse
import pickle
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import cache  # noqa: E402
from load import Map, map_of, name_of  # noqa: E402

STEP3 = Path(r"F:\dev\maple-corpus\work\track-plan\step3")
OUT = Path(r"F:\dev\maple-corpus\work\track-plan\step3b")


def rows_of(cap, tag):
    return pickle.loads((STEP3 / f"{cap.replace('#', '_')}_{tag}.pkl").read_bytes())["rows"]


def births(cap, tag) -> list:
    """Every track's first row: {cap, id, n, t, x, y, kind0, kind, how, pose, confirmed, frames}."""
    first, last_kind, conf, nfr = {}, {}, set(), Counter()
    for r in rows_of(cap, tag):
        for m in r["mobs"]:
            i = m["id"]
            nfr[i] += 1
            if i not in first:
                first[i] = {"cap": cap, "id": i, "n": r["n"], "t": r["t"], "x": m["x"], "y": m["y"], "sx": m["sx"],
                            "sy": m["sy"], "kind0": m["mob"], "how": m["born_how"], "pose": m.get("first_pose"),
                            "born": m["born"]}
            last_kind[i] = m["mob"]
            if m["state"] != "tentative":
                conf.add(i)
    out = []
    for i, b in first.items():
        b["kind"], b["confirmed"], b["frames"] = last_kind[i], i in conf, nfr[i]
        out.append(b)
    return out


def points(mp: Map):
    return [(s["index"], int(s["id"]), float(s["x"]), float(s["y"]), bool(s.get("hidden")), s.get("mobTime"))
            for s in mp.spawns]


def nearest(pts, kind, x, y, hidden_ok=False):
    best = (1e9, None, 0.0, 0.0)
    for idx, k, px, py, hid, _ in pts:
        if k != kind or (hid and not hidden_ok):
            continue
        d = float(np.hypot(px - x, py - y))
        if d < best[0]:
            best = (d, idx, px - x, py - y)
    return best


def collect(tag):
    allb, maps = [], {}
    for cap in cache.SOUND:
        mid = map_of(cap)
        if mid not in maps:
            maps[mid] = Map(mid)
        pts = points(maps[mid])
        for b in births(cap, tag):
            b["map"] = mid
            b["d"], b["pt"], b["dx"], b["dy"] = nearest(pts, b["kind"], b["x"], b["y"])
            b["d0"] = nearest(pts, b["kind0"], b["x"], b["y"])[0]
            b["d_any"] = min((float(np.hypot(px - b["x"], py - b["y"])) for _, _, px, py, h, _ in pts if not h),
                             default=1e9)
            allb.append(b)
    return allb, maps


def dist_line(d, label):
    d = np.asarray(d, float)
    if not len(d):
        return f"  {label}: none"
    p = np.percentile(d, [50, 90, 95, 99])
    share = "  ".join(f"<= {k}: {100 * np.mean(d <= k):.1f} %" for k in (3, 5, 10, 20))
    return (f"  {label} (n {len(d)}): p50 {p[0]:.1f}  p90 {p[1]:.1f}  p95 {p[2]:.1f}  p99 {p[3]:.1f}  max {d.max():.1f}"
            f"\n      {share}")


def cmd_measure(tag):
    allb, maps = collect(tag)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"spawns_{tag}.pkl").write_bytes(pickle.dumps(allb))
    print(f"tracks born, by how ({tag}, 13 sound captures):", dict(Counter(b["how"] for b in allb)))
    fi = [b for b in allb if b["how"] == "faded in"]
    fc = [b for b in fi if b["confirmed"]]
    print(f"faded in: {len(fi)} tracks, {len(fc)} confirmed (a mob of the state); kind changed by the vote "
          f"after birth: {sum(b['kind'] != b['kind0'] for b in fi)}")
    print(dist_line([b["d"] for b in fi], "every faded-in track, the nearest point of its (final) kind, px"))
    print(dist_line([b["d"] for b in fc], "confirmed faded-in tracks"))
    print(dist_line([b["d0"] for b in fc], "confirmed, the kind of its first sighting"))
    print(dist_line([abs(b["dx"]) for b in fc if b["pt"] is not None], "confirmed, |dx| alone"))
    print(dist_line([b["dy"] for b in fc if b["pt"] is not None], "confirmed, dy = point y - feet y (signed)"))
    print(dist_line([b["d_any"] for b in fc], "confirmed, the nearest point of ANY kind"))
    for lim in (20, 40, 100):
        nf = [b for b in fc if b["d"] > lim]
        print(f"  confirmed with no point of its kind within {lim} px: {len(nf)}")
    print("  confirmed with no point of its kind at all on the map:", sum(b["pt"] is None for b in fc))
    print("\nby map (confirmed faded in): n, within 10 px, p50, max")
    by = defaultdict(list)
    for b in fc:
        by[(b["map"], b["cap"])].append(b["d"])
    for (mid, cap), d in sorted(by.items()):
        d = np.array(d)
        print(f"  {cap:22s} {mid}: {len(d):4d}  {100 * np.mean(d <= 10):5.1f} %  {np.median(d):6.1f}  {d.max():7.1f}")
    print("\nby kind (confirmed faded in): n, within 10 px, p50, p95")
    byk = defaultdict(list)
    for b in fc:
        byk[maps[b["map"]].names.get(b["kind"], b["kind"])].append(b["d"])
    for k, d in sorted(byk.items(), key=lambda kv: -len(kv[1])):
        d = np.array(d)
        print(f"  {k:16s} {len(d):4d}  {100 * np.mean(d <= 10):5.1f} %  {np.median(d):6.1f}  {np.percentile(d, 95):6.1f}")
    print("\nthe far ones (confirmed, > 10 px), by distance:")
    for b in sorted([b for b in fc if b["d"] > 10], key=lambda b: b["d"])[:60]:
        print(f"  {b['cap']:22s} n {b['n']:6d} id {b['id']:4d} {maps[b['map']].names.get(b['kind'])[:12]:12s} feet "
              f"({b['x']:.0f}, {b['y']:.0f}) screen ({b['sx']}, {b['sy']}) pose {b['pose']}: point {b['pt']} "
              f"d {b['d']:.1f} (dx {b['dx']:.0f}, dy {b['dy']:.0f}); any kind {b['d_any']:.1f}; {b['frames']} frames")
    print("\nspawn points: same-kind pairs within 20 px (and 10 px), per map; hidden points")
    for mid, mp in sorted(maps.items()):
        pts = [p for p in points(mp) if not p[4]]
        n20 = n10 = 0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                if pts[i][1] == pts[j][1]:
                    d = np.hypot(pts[i][2] - pts[j][2], pts[i][3] - pts[j][3])
                    n20 += d <= 20
                    n10 += d <= 10
        hid = sum(p[4] for p in points(mp))
        mt = Counter(p[5] for p in points(mp))
        print(f"  {mid}: {len(pts)} points, pairs <= 20 px: {n20}, <= 10 px: {n10}; hidden {hid}; mobTime {dict(mt)}")


def cmd_sheet(tag, n, seed=3):
    import cv2
    allb = pickle.loads((OUT / f"spawns_{tag}.pkl").read_bytes())
    fc = [b for b in allb if b["how"] == "faded in" and b["confirmed"] and b["d"] <= 10]
    random.Random(seed).shuffle(fc)
    pick = fc[:n]
    d = OUT / f"sheet_{tag}"
    d.mkdir(parents=True, exist_ok=True)
    maps = {}
    tiles = []
    for k, b in enumerate(pick):
        mp = maps.setdefault(b["map"], Map(b["map"]))
        pt = next(p for p in points(mp) if p[0] == b["pt"])
        fr = frame_of(b["cap"], b["n"])
        cx, cy = b["x"] - b["sx"], b["y"] - b["sy"]
        px, py = int(round(pt[2] - cx)), int(round(pt[3] - cy))
        img = fr.copy()
        cv2.drawMarker(img, (px, py), (0, 0, 255), cv2.MARKER_CROSS, 22, 1)
        cv2.circle(img, (px, py), 10, (0, 0, 255), 1)
        cv2.circle(img, (int(b["sx"]), int(b["sy"])), 2, (0, 255, 0), -1)
        x0, y0 = max(0, px - 100), max(0, py - 120)
        crop = img[y0:y0 + 160, x0:x0 + 200]
        crop = cv2.copyMakeBorder(crop, 0, 160 - crop.shape[0], 0, 200 - crop.shape[1], cv2.BORDER_CONSTANT)
        crop = cv2.resize(crop, (400, 320), interpolation=cv2.INTER_NEAREST)
        cv2.putText(crop, f"{k + 1} {b['cap'][-6:]} n{b['n']} id{b['id']} d{b['d']:.0f}", (4, 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        tiles.append(crop)
        # the frames around it (+6, +12, +20): the fade-in shown, the mob there
        strip = []
        for dn in (0, 6, 12, 20):
            f2 = frame_of(b["cap"], b["n"] + dn)
            c2 = f2[y0:y0 + 160, x0:x0 + 200].copy()
            c2 = cv2.copyMakeBorder(c2, 0, 160 - c2.shape[0], 0, 200 - c2.shape[1], cv2.BORDER_CONSTANT)
            cv2.drawMarker(c2, (px - x0, py - y0), (0, 0, 255), cv2.MARKER_CROSS, 22, 1)
            strip.append(cv2.resize(c2, (400, 320), interpolation=cv2.INTER_NEAREST))
        cv2.imwrite(str(d / f"case_{k + 1:02d}.png"), np.hstack(strip))
    rows = [np.hstack(tiles[i:i + 5] + [np.zeros_like(tiles[0])] * (5 - len(tiles[i:i + 5])))
            for i in range(0, len(tiles), 5)]
    cv2.imwrite(str(d / "sheet.png"), np.vstack(rows))
    with open(d / "cases.txt", "w", encoding="utf-8") as f:
        for k, b in enumerate(pick):
            f.write(f"{k + 1} {b['cap']} n {b['n']} id {b['id']} kind {b['kind']} feet ({b['x']:.0f}, {b['y']:.0f}) "
                    f"point {b['pt']} d {b['d']:.1f}\n")
    print(f"{len(pick)} cases -> {d}")


_ROWS = {}


def kept_row(cap, n):
    """The kept replay's row of frame n (its chunk read once)."""
    import dump
    if _ROWS.get("cap") != cap:                         # each chunk's first n (a replay may start past frame 0)
        _ROWS.clear()
        _ROWS["cap"], _ROWS["starts"] = cap, []
        for k in range(dump.meta(cap)["chunks"]):
            rs = pickle.loads((dump.out_dir(cap) / f"rows_{k:03d}.pkl").read_bytes())
            _ROWS["starts"].append(rs[0]["n"])
            _ROWS[k] = {r["n"]: r for r in rs} if k == 0 else None
    k = max(i for i, s in enumerate(_ROWS["starts"]) if s <= n)
    if _ROWS.get(k) is None:
        for j in [j for j in _ROWS if isinstance(j, int)]:
            _ROWS[j] = None
        _ROWS[k] = {r["n"]: r for r in pickle.loads((dump.out_dir(cap) / f"rows_{k:03d}.pkl").read_bytes())}
    return _ROWS[k].get(n)


def frame_of(cap, n):
    """Frame n of a capture (BGR), from the bank's video (frames.read on the kept replay's frame name)."""
    import dump
    import frames as rec
    c = dump.clip_of(cap)
    return rec.read(c.run, kept_row(cap, n)["frame"])


def cmd_why(tag):
    """The faded-in births > 10 px from their point, sorted by what the numbers show: the first sighting's opacity
    (the fit's, from the kept replay), the offset's direction, the first pose, the track's motion over its first 0.5
    s (away from the point or not), flyers against map.json's spriteY."""
    allb = pickle.loads((OUT / f"spawns_{tag}.pkl").read_bytes())
    fc = sorted([b for b in allb if b["how"] == "faded in" and b["confirmed"]], key=lambda b: (b["cap"], b["n"]))
    maps, cls, ops = {}, Counter(), {"near": [], "far": []}
    rows_cache = {}
    for b in fc:
        mp = maps.setdefault(b["map"], Map(b["map"]))
        r = kept_row(b["cap"], b["n"])
        fit = (r["facts"].get("fit") or []) if r else []
        o = min(((abs(f["feet"][0] - b["sx"]) + abs(f["feet"][1] - b["sy"]), f.get("opacity", 1.0)) for f in fit
                 if f.get("type") == b["kind0"]), default=(None, None))[1]
        b["o"] = o
        ops["near" if b["d"] <= 10 else "far"].append(o if o is not None else np.nan)
        if b["d"] <= 10:
            continue
        fly = bool((mp.mobs.get(b["kind"]) or {}).get("fly")) or "fly" in str(b["pose"])
        if fly:
            sp = [s for s in mp.spawns if s["id"] == b["kind"]]
            ds = min(np.hypot(s["x"] - b["x"], s["spriteY"] - b["y"]) for s in sp)
            b["d_sprite"] = ds
            cls["flyer: within 10 px of spriteY" if ds <= 10 else "flyer: not near spriteY either"] += 1
            continue
        # the track's x 0.5 s on (its rows): moving away from the point along x?
        if b["cap"] not in rows_cache:
            rows_cache.clear()
            rows_cache[b["cap"]] = {}
            for rr in rows_of(b["cap"], tag):
                for m in rr["mobs"]:
                    rows_cache[b["cap"]].setdefault(m["id"], []).append((rr["t"], m["x"], m["y"]))
        tr = rows_cache[b["cap"]][b["id"]]
        later = [p for p in tr if p[0] - b["t"] <= 0.5][-1]
        away = (later[1] - b["x"]) * (-b["dx"]) > 0          # dx = point - feet: moving on, away from the point
        if abs(b["dx"]) <= 3 and b["dy"] > 3:
            cls["above the point, x on it (" + ("a jump pose" if "jump" in str(b["pose"]) else "pose " +
                                                 str(b["pose"]).rsplit("_", 1)[0]) + ")"] += 1
        elif abs(b["dy"]) <= 3:
            cls["on the point's level, x off (" + ("moving away from it" if away else "not moving away") + ")"] += 1
        else:
            cls["both off"] += 1
    print(f"faded-in, confirmed: {len(fc)}; > 10 px: {sum(b['d'] > 10 for b in fc)}")
    for k, v in cls.most_common():
        print(f"  {v:4d}  {k}")
    for k in ("near", "far"):
        a = np.array(ops[k], float)
        a = a[~np.isnan(a)]
        print(f"  first sighting's opacity, {k} (<= 10 px / > 10 px): n {len(a)}, p10 / p50 / p90 "
              + " / ".join(f"{v:.2f}" for v in np.percentile(a, [10, 50, 90])))
    lv = [b for b in fc if b["d"] > 10 and abs(b["dy"]) <= 3 and b.get("o") is not None]
    if lv:
        print("  level, x off: |dx| p50 / p90 / max "
              + " / ".join(f"{v:.0f}" for v in np.percentile([abs(b["dx"]) for b in lv], [50, 90, 100]))
              + "; their opacity p50 " + f"{np.median([b['o'] for b in lv]):.2f}")
    fl = [b for b in fc if "d_sprite" in b]
    if fl:
        print("  flyers > 10 px: distance to spriteY p50 / max "
              + " / ".join(f"{v:.1f}" for v in np.percentile([b["d_sprite"] for b in fl], [50, 100])))
    allfly = [b for b in fc if bool((maps[b["map"]].mobs.get(b["kind"]) or {}).get("fly"))
              or "fly" in str(b["pose"])]
    if allfly:
        dd = []
        for b in allfly:
            sp = [s for s in maps[b["map"]].spawns if s["id"] == b["kind"]]
            dd.append(min(np.hypot(s["x"] - b["x"], s["spriteY"] - b["y"]) for s in sp))
        print(dist_line(dd, "every confirmed faded-in flyer against x, spriteY"))
    # the gate's share if each class were taken as on its point
    (OUT / f"spawns_{tag}.pkl").write_bytes(pickle.dumps(allb))


def cmd_beat(tag):
    allb = pickle.loads((OUT / f"spawns_{tag}.pkl").read_bytes())
    fc = [b for b in allb if b["how"] == "faded in" and b["confirmed"] and b["d"] <= 10]
    per = defaultdict(list)
    for b in fc:
        per[(b["cap"], b["pt"])].append(b["t"])
    gaps = []
    for ts in per.values():
        ts.sort()
        gaps += list(np.diff(ts))
    gaps = np.array(gaps)
    print(f"spawns seen (confirmed, within 10 px): {len(fc)} on {len(per)} points; points with 2+ spawns: "
          f"{sum(len(v) > 1 for v in per.values())}")
    if len(gaps):
        print("time between spawns seen on one point, s: p10 / p50 / p90 / min / max",
              " / ".join(f"{v:.1f}" for v in np.percentile(gaps, [10, 50, 90])), f"/ {gaps.min():.2f} / {gaps.max():.1f}")
        print("  gap mod 10 s, histogram (1 s bins):", np.histogram(gaps % 10, bins=10, range=(0, 10))[0].tolist())
    # the 10 s beat: per capture, the spawn times' phase mod 10; a beat = phases bunched (Rayleigh test)
    print("per capture: spawns, phase mod 10 s bunching R (0 = spread, 1 = one phase), p (Rayleigh), the phase "
          "histogram (1 s bins); same-frame pairs")
    for cap in cache.SOUND:
        ts = np.array(sorted(b["t"] for b in fc if b["cap"] == cap))
        if len(ts) < 3:
            print(f"  {cap}: {len(ts)} spawns")
            continue
        ang = 2 * np.pi * (ts % 10) / 10
        R = abs(np.exp(1j * ang).mean())
        z = len(ts) * R * R
        p = np.exp(-z) * (1 + (2 * z - z * z) / (4 * len(ts)))
        h = np.histogram(ts % 10, bins=10, range=(0, 10))[0].tolist()
        dts = np.diff(ts)
        print(f"  {cap:22s} {len(ts):4d}  R {R:.2f}  p {max(p, 0):.2g}  {h}; within 0.5 s of another: "
              f"{int(np.sum(dts <= 0.5))}; best period 9.5-10.5 s R "
              f"{max(abs(np.exp(2j * np.pi * ts / P).mean()) for P in np.arange(9.5, 10.51, 0.01)):.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["measure", "why", "sheet", "beat"])
    ap.add_argument("--tag", default="s4b")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    if a.cmd == "measure":
        cmd_measure(a.tag)
    elif a.cmd == "why":
        cmd_why(a.tag)
    elif a.cmd == "sheet":
        cmd_sheet(a.tag, a.n)
    else:
        cmd_beat(a.tag)


if __name__ == "__main__":
    main()
