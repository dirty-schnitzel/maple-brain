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
            first[i]["how"] = m["born_how"]          # settled (try 3: a faint birth is "faded in" until its
            #                                           opacity rose, else how it came into sight otherwise)
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


FADE_L = 0.827                  # s: the fade's length on Classic World, its p90 (cmd_fade: p50 0.816; v83 0.32 s)
SLACK = 10.0                    # px: the fit's feet against the point (the first try's 10 px)
HOP = 78.0                      # px: a hop's apex (PLAN-tracker measurement 3)


def graph_of(mid, cache_={}):
    if mid not in cache_:
        from maplebrain.config import Track
        from maplebrain.perception.vote import load_poses
        from maplebrain.track.graph import Graph
        from maplebrain.track.kinds import kinds
        from load import ASSETS
        mp = Map(mid)
        cfg = Track()
        g = Graph(mp.json, track=cfg, edges=False)
        ks = kinds(mp.mobs, load_poses(mp.id, ASSETS), cfg.mob_speed_x, cfg.knock_v)
        sp = [v for v in mp.json.get("mobs") or [] if not v.get("hidden")]
        cache_[mid] = (mp, g, {k.id: k for k in (ks.values() if isinstance(ks, dict) else ks)}, sp)
    return cache_[mid]


def group_of(b, k):
    """The first try's why-groups: within 10 px / walked / hopped / flyer / other."""
    if b["d"] <= 10:
        return "within 10 px"
    if k.fly:
        return "flyer"
    if abs(b["dx"]) <= 3 and b["dy"] > 3:
        return "hopped (straight above)"
    if abs(b["dy"]) <= 3:
        return "walked (on the level)"
    return "other"


def trace(b, g, k, sp, L=FADE_L, slack=SLACK, hop=HOP):
    """Rule (c): the points of b's kind that could have put it where it is first seen, in the time since it appeared
    (its first opacity x L). A walker: the point's node = the birth's node, |dx| <= v t + slack, the feet within
    slack of the node's surface or up to one hop over it. A flyer: (x, spriteY) within v t + slack. -> (point indices
    in `sp`, t)."""
    s0 = b.get("series") or []
    if not s0 or s0[0][0] != b["n"]:                    # the first sighting must be the birth frame
        raise ValueError(f"no opacity on the birth frame: {b['cap']} id {b['id']} n {b['n']}")
    o = s0[0][2]
    t = o * L
    reach = k.v * t + slack
    out = []
    for i, s in enumerate(sp):
        if int(s["id"]) != b["kind"]:
            continue
        if k.fly:
            if np.hypot(s["x"] - b["x"], s["spriteY"] - b["y"]) <= reach:
                out.append(i)
            continue
        if int(g.spawn_node[i]) != int(b["node"]) or abs(s["x"] - b["x"]) > reach:
            continue
        surf = float(g.surface_y([b["node"]], [b["x"]])[0])
        up = (surf if np.isfinite(surf) else s["y"]) - b["y"]          # feet above the surface (px)
        if -slack <= up <= (hop + slack if k.jump else slack):
            out.append(i)
    return out, t


def cmd_trace(tag):
    allb = pickle.loads((OUT / f"spawns_{tag}.pkl").read_bytes())
    fc = [b for b in allb if b["how"] == "faded in" and b["confirmed"]]
    node_of = {}
    for cap in {b["cap"] for b in fc}:                  # the birth's node: its first row's (the tracker's)
        ids = {b["id"] for b in fc if b["cap"] == cap}
        for r in rows_of(cap, tag):
            for m in r["mobs"]:
                if m["id"] in ids and (cap, m["id"]) not in node_of:
                    node_of[(cap, m["id"])] = m["node"]
    res = Counter()
    by_g, by_k = defaultdict(Counter), defaultdict(Counter)
    left = []
    for b in fc:
        mp, g, ks, sp = graph_of(b["map"])
        k = ks[b["kind"]]
        b["node"] = node_of[(b["cap"], b["id"])]
        cand, t = trace(b, g, k, sp)
        b["t_since"], b["cand"] = t, [sp[i]["index"] for i in cand]
        v = "matched" if len(cand) == 1 else "two or more candidates" if cand else "no candidate"
        b["traced"] = v == "matched"
        res[v] += 1
        grp = group_of(b, k)
        b["group"] = grp
        by_g[grp][v] += 1
        by_k[mp.names.get(b["kind"], b["kind"])][v] += 1
        if v != "matched":
            left.append((b, k, mp, g, sp))
        if v == "matched" and b["d"] <= 10 and sp[cand[0]]["index"] != b["pt"]:
            res["matched another point than the nearest"] += 1
    (OUT / f"spawns_{tag}.pkl").write_bytes(pickle.dumps(allb))
    n = len(fc)
    print(f"rule (c) on the {n} confirmed faded-in births (L {FADE_L} s, slack {SLACK} px, hop {HOP} px, speeds "
          f"kinds.py):")
    for kk, v in res.most_common():
        print(f"  {kk}: {v} = {100 * v / n:.1f} %")
    t10 = sum(b["d"] <= 10 for b in fc)
    both = sum(b["d"] <= 10 and b["traced"] for b in fc)
    print(f"  the 10 px rule: {t10}; matched by both: {both}; by (c) only: {res['matched'] - both}; by 10 px only: "
          f"{t10 - both}")
    print("by group: matched / two+ / none")
    for grp, c in sorted(by_g.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {grp:26s} {sum(c.values()):4d}: {c['matched']:4d} / {c['two or more candidates']:3d} / "
              f"{c['no candidate']:3d}")
    print("by kind: matched / two+ / none")
    for kk, c in sorted(by_k.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {kk:16s} {sum(c.values()):4d}: {c['matched']:4d} ({100 * c['matched'] / sum(c.values()):5.1f} %)"
              f" / {c['two or more candidates']:3d} / {c['no candidate']:3d}")
    print("the ones left, with the reason:")
    why = Counter()
    for b, k, mp, g, sp in left:
        same = [s for s in sp if int(s["id"]) == b["kind"]]
        if b["cand"]:
            r = f"{len(b['cand'])} candidates {b['cand']}"
        else:
            on = [i for i, s in enumerate(sp) if int(s["id"]) == b["kind"] and int(g.spawn_node[i]) == int(b["node"])]
            if k.fly:
                dd = min(np.hypot(s["x"] - b["x"], s["spriteY"] - b["y"]) for s in same)
                r = f"flyer: nearest (x, spriteY) {dd:.0f} px > reach {k.v * b['t_since'] + SLACK:.0f}"
            elif not on:
                r = f"no point of its kind on its node {b['node']} (nearest point {b['pt']} on node " \
                    f"{int(g.spawn_node[[s['index'] for s in sp].index(b['pt'])])})"
            else:
                dx = min(abs(sp[i]["x"] - b["x"]) for i in on)
                surf = float(g.surface_y([b["node"]], [b["x"]])[0])
                r = (f"on its node: nearest |dx| {dx:.0f} > reach {k.v * b['t_since'] + SLACK:.0f}"
                     if dx > k.v * b["t_since"] + SLACK else f"height: feet {surf - b['y']:.0f} px over the surface")
        why[r.split(":")[0].split(" (")[0] if not r[0].isdigit() else "two+ candidates"] += 1
        print(f"  {b['cap']:22s} n {b['n']:6d} id {b['id']:4d} {mp.names.get(b['kind'], '')[:12]:12s} {b['group']:24s}"
              f" o {b['series'][0][2] if b.get('series') else b.get('o')!s:.4} t {b['t_since']:.2f} s: {r}")
    print("  reasons:", dict(why))
    print("same-kind point pairs within 100 px on one node, per map:")
    seen = set()
    for b in fc:
        if b["map"] in seen:
            continue
        seen.add(b["map"])
        mp, g, ks, sp = graph_of(b["map"])
        c = 0
        for i in range(len(sp)):
            for j in range(i + 1, len(sp)):
                if sp[i]["id"] == sp[j]["id"] and g.spawn_node[i] == g.spawn_node[j] \
                        and abs(sp[i]["x"] - sp[j]["x"]) <= 100:
                    c += 1
        print(f"  {b['map']}: {c} (of {len(sp)} points)")


def cmd_sheet2(tag, n, seed=5):
    """30 random births matched by (c) that the 10 px rule did not match: a 4-frame strip each - the frame it
    appeared on (its first sighting - t_since), halfway, its first sighting, +10 frames - the crop fixed on the point
    in map coordinates (each frame's own camera), the point a red cross (a flyer's at spriteY), the first feet a
    green dot on the third."""
    import cv2
    allb = pickle.loads((OUT / f"spawns_{tag}.pkl").read_bytes())
    fc = [b for b in allb if b["how"] == "faded in" and b["confirmed"] and b.get("traced") and b["d"] > 10]
    random.Random(seed).shuffle(fc)
    pick = sorted(fc[:n], key=lambda b: (b["cap"], b["n"]))
    d = OUT / f"sheet2_{tag}"
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, b in enumerate(pick):
        mp, g, ks, sp = graph_of(b["map"])
        s = next(v for v in sp if v["index"] == b["cand"][0])
        fly = ks[b["kind"]].fly
        px, py = float(s["x"]), float(s["spriteY"] if fly else s["y"])
        dn0 = int(round(b["t_since"] * 60))
        strip = []
        for j, nn in enumerate((b["n"] - dn0, b["n"] - dn0 // 2, b["n"], b["n"] + 10)):
            r = kept_row(b["cap"], nn)
            fr = frame_of(b["cap"], nn) if r is not None else None
            if fr is None or r["C"] is None:
                strip.append(np.zeros((320, 400, 3), np.uint8))
                continue
            C = r["C"]
            qx, qy = int(round(px - C[0])), int(round(py - C[1]))
            img = fr.copy()
            cv2.drawMarker(img, (qx, qy), (0, 0, 255), cv2.MARKER_CROSS, 22, 1)
            if j == 2:
                cv2.circle(img, (int(round(b["x"] - C[0])), int(round(b["y"] - C[1]))), 3, (0, 255, 0), -1)
            x0, y0 = qx - 100, qy - 120
            pad = cv2.copyMakeBorder(img, 200, 200, 200, 200, cv2.BORDER_CONSTANT)
            crop = pad[y0 + 200:y0 + 360, x0 + 200:x0 + 400]
            crop = cv2.resize(crop, (400, 320), interpolation=cv2.INTER_NEAREST)
            cv2.putText(crop, f"{k + 1} {['appeared', 'half', 'first seen', '+10'][j]} n{nn}", (4, 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            strip.append(crop)
        cv2.imwrite(str(d / f"case_{k + 1:02d}.png"), np.hstack(strip))
        lines.append(f"{k + 1} {b['cap']} n {b['n']} id {b['id']} {mp.names.get(b['kind'])} {b['group']} point "
                     f"{b['cand'][0]} (nearest {b['pt']}, d {b['d']:.0f}, dx {b['dx']:.0f}, dy {b['dy']:.0f}) t "
                     f"{b['t_since']:.2f} s")
    (d / "cases.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"{len(pick)} cases -> {d}")


FADE_N = 90                     # frames of a faded-in track followed for its opacity (1.5 s at 60 a second)


def cmd_fade(tag):
    """Try 2, measurement 1: the fade's length on Classic World. Per confirmed faded-in track, its opacity on every
    frame it is seen in its first FADE_N frames (the fit's sighting of its kind nearest its row's screen feet, within
    20 px - a look-alike reading is 17 px off - from the kept replay). Per track: the first sighting's opacity o0; the frames until the opacity first reaches
    0.95; the line o = (t - t0) / L fitted over its sightings with 0.1 <= o <= 0.9 (L = the fade's length, t0 = when
    it appeared). Saved into each birth (`series`, `L`, `t0`, `r2`)."""
    allb = pickle.loads((OUT / f"spawns_{tag}.pkl").read_bytes())
    fc = [b for b in allb if b["how"] == "faded in" and b["confirmed"]]
    for cap in cache.SOUND:
        mine = {b["id"]: b for b in fc if b["cap"] == cap}
        if not mine:
            continue
        want = defaultdict(list)                        # n -> [(birth, sx, sy)]
        for r in rows_of(cap, tag):
            for m in r["mobs"]:
                b = mine.get(m["id"])
                if b is not None and r["n"] - b["n"] < FADE_N and m["src"] == "acq":
                    want[r["n"]].append((b, m["sx"], m["sy"], r["t"]))
        for b in mine.values():
            b["series"] = []
        for n in sorted(want):
            r = kept_row(cap, n)
            fit = (r["facts"].get("fit") or []) if r else []
            for b, sx, sy, t in want[n]:
                best = min(((abs(f["feet"][0] - sx) + abs(f["feet"][1] - sy), f) for f in fit
                            if f.get("type") == b["kind0"]), default=(99, None), key=lambda p: p[0])
                if best[1] is not None and best[0] <= 20:     # 20: a look-alike reading is 17 px off
                    b["series"].append((n, t, float(best[1]["opacity"]), best[1].get("pose")))
    Ls, firsts, to95, r2s = [], [], [], []
    for b in fc:
        s = b.get("series") or []
        b["L"] = b["t0"] = b["r2"] = b["n95"] = None
        if not s:
            continue
        firsts.append(s[0][2])
        k95 = next((i for i, p in enumerate(s) if p[2] >= 0.95), None)
        if k95 is not None:
            b["n95"] = s[k95][0] - s[0][0]
        pts = [(p[1], p[2]) for p in s if 0.1 <= p[2] <= 0.9 and (k95 is None or p[0] <= s[k95][0])]
        if len(pts) >= 4:
            t, o = np.array(pts).T
            a, c = np.polyfit(t, o, 1)
            if a > 0:
                res = o - (a * t + c)
                b["L"], b["t0"] = 1.0 / a, -c / a
                b["r2"] = 1 - res.var() / max(o.var(), 1e-9)
                Ls.append(b["L"])
                r2s.append(b["r2"])
                if s[0][2] <= 0.25 and b["n95"] is not None:
                    to95.append(b["n95"])
    (OUT / f"spawns_{tag}.pkl").write_bytes(pickle.dumps(allb))
    Ls, r2s = np.array(Ls), np.array(r2s)
    print(f"confirmed faded-in births: {len(fc)}; with their opacity followed: {len(firsts)}; a line fitted (4+ "
          f"sightings in 0.1-0.9): {len(Ls)}")
    print("  the first sighting's opacity p10 / p50 / p90: " + " / ".join(f"{v:.2f}" for v in np.percentile(firsts, [10, 50, 90])))
    print(f"  the fade's length L (s) from the line: p10 / p25 / p50 / p75 / p90 "
          + " / ".join(f"{v:.3f}" for v in np.percentile(Ls, [10, 25, 50, 75, 90]))
          + f"  (= {60 * np.median(Ls):.1f} frames at the median; v83: 0.32 s = 19.2 frames)")
    print("  the line's R^2 p10 / p50: " + " / ".join(f"{v:.3f}" for v in np.percentile(r2s, [10, 50])))
    good = np.array([b["L"] for b in fc if b.get("L") and b["r2"] >= 0.95])
    print(f"  L where R^2 >= 0.95 (n {len(good)}): p10 / p50 / p90 "
          + " / ".join(f"{v:.3f}" for v in np.percentile(good, [10, 50, 90])))
    if to95:
        print(f"  seen from a faint frame (first opacity <= 0.25, n {len(to95)}): frames from it to opacity >= 0.95 "
              "p10 / p50 / p90 " + " / ".join(f"{v:.0f}" for v in np.percentile(to95, [10, 50, 90])))
    # the opacity curve pooled: o against the time since t0 (each track's own appearance), 1/60 s bins
    pool = defaultdict(list)
    for b in fc:
        if b.get("L") and b["r2"] >= 0.95:
            for n, t, o, _ in b["series"]:
                k = int(round((t - b["t0"]) * 60))
                if 0 <= k <= 40:
                    pool[k].append(o)
    print("  the opacity by frames since appearing (pooled, median): "
          + ", ".join(f"{k}:{np.median(pool[k]):.2f}" for k in sorted(pool) if k % 3 == 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["measure", "why", "sheet", "beat", "fade", "trace", "sheet2"])
    ap.add_argument("--tag", default="s4b")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    if a.cmd == "measure":
        cmd_measure(a.tag)
    elif a.cmd == "fade":
        cmd_fade(a.tag)
    elif a.cmd == "trace":
        cmd_trace(a.tag)
    elif a.cmd == "sheet2":
        cmd_sheet2(a.tag, a.n)
    elif a.cmd == "why":
        cmd_why(a.tag)
    elif a.cmd == "sheet":
        cmd_sheet(a.tag, a.n)
    else:
        cmd_beat(a.tag)


if __name__ == "__main__":
    main()
