"""PLAN-tracker step 3: THE REAL MOB TRACKER FROM A KEPT REPLAY - maplebrain/track/mobs.py (with track/graph.py's
placement, track/kinds.py, the bitmap evidence of track/evidence.py) over every frame of a capture's kept replay
(dump.py: the fit's sightings + the two bitmaps; no GPU), graded like the prototype (proto_mobs.py): score.py against
the hindsight truth (cache.chains), the fair counts (`sticky`), the memory's episodes, why ids switched.

    python tools/perc/track/replay_mobs.py run CAP [CAP ...] | --sound [--kept NAME] [--hints] [--jobs N] [--tag T]
    python tools/perc/track/replay_mobs.py pool [--sound | CAP ...] [--kept NAME] [--tag T]    the gate's numbers
    python tools/perc/track/replay_mobs.py feet [--sound | CAP ...] [--tag T]                  measurement 3 on its tracks
    python tools/perc/track/replay_mobs.py labels [--tag T]                                    L1, L2, L3, L8
    python tools/perc/track/replay_mobs.py live CAP --kept NAME                                the shadow rows vs these

`run` writes OUT/<cap>[_<kept>][_<tag>].pkl (OUT = CORPUS/work/track-plan/step3): the rows ({"n", "t", "mobs"}: the
prototype's row layout, so score.py / proto_mobs read them), per seen track-frame the reading used, the tracker's
stats / episodes / ends, the ms a frame (the evidence's decode left out, as the prototype's), and the per-capture
scores (score.py, sticky, why_switch); `pool` adds them up. `--kept NAME`: the kept replay in CORPUS/work/SESSION#K/
NAME (a new one, stop rule 5); `--hints`: the kept replay's looks (fit_hints) the fit's rule calls seen are taken as
sightings too (does Fitter.look pay? PLAN-tracker design 4); `--tag`: a name for the variant's files.
"""
import argparse
import pickle
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import cache  # noqa: E402
import dump  # noqa: E402
import proto_mobs as P  # noqa: E402
import score as S  # noqa: E402
from load import ASSETS, Map, map_of, name_of, ticks  # noqa: E402

OUT = Path(r"F:\dev\maple-corpus\work\track-plan\step3")
FACE = {-1: "left", 1: "right", 0: "?"}


class Facts:
    """The fields of FrameFacts the tracker reads, from a kept replay's row (its `facts` dict)."""
    __slots__ = ("t", "scene_cam", "fit", "tags", "drops", "tag")

    def __init__(self, r, hints: bool = False, seen=None):
        f = r["facts"]
        self.t, self.scene_cam = r["t"], r["C"]
        self.fit = f.get("fit")
        if hints and self.fit is not None:
            self.fit = list(self.fit) + [{"type": h["mob"], "feet": [h["sx"], h["sy"]], "pose": h["pose"],
                                          "facing": h["facing"], "opacity": h["o"], "n_seen": h["n_seen"]}
                                         for h in f.get("fit_hints") or [] if seen(h)]
        self.tags, self.drops, self.tag = f.get("tags"), f.get("drops"), f.get("tag")


class LazyBits:
    """track/evidence.Bitmaps on a kept replay's packed bitmaps, unpacked on the first question (its time apart)."""

    def __init__(self, sh, wo):
        self.sh, self.wo, self.ready, self.dec, self._b = sh, wo, sh is not None, 0.0, None

    def count(self, groups):
        from maplebrain.track.evidence import Bitmaps
        if self._b is None:
            a = time.perf_counter()
            self._b = Bitmaps(dump.bits(self.sh), dump.bits(self.wo))
            self.dec = time.perf_counter() - a
        return self._b.count(groups)


def seen_rule():
    from maplebrain.perception.fit import FitConfig
    c = FitConfig()

    def seen(h):
        n = h["n_inf"]
        return n > 0 and h["n_seen"] >= c.min_seen and h["n_seen"] >= c.seen_min * n and h["n_abs"] <= c.absent_max * n
    return seen


def tracker(mp):
    from maplebrain.config import Track
    from maplebrain.perception.vote import load_poses
    from maplebrain.track.graph import Graph
    from maplebrain.track.kinds import kinds
    from maplebrain.track.mobs import MobTracker
    cfg = Track()
    g = Graph(mp.json, track=cfg, edges=False)
    return MobTracker(g, kinds(mp.mobs, load_poses(mp.id, ASSETS), cfg.mob_speed_x, cfg.knock_v), cfg, keep=True)


def row_of(m) -> dict:
    """A mob record -> the prototype's row layout (proto_mobs.Tracker._rows)."""
    return {"id": m.id, "mob": m.kind, "state": m.state, "x": round(m.x, 1), "y": round(m.y, 1), "sx": round(m.sx),
            "sy": round(m.sy), "src": "acq" if m.seen else "none", "unseen": round(m.unseen_s, 2), "cover": m.cover,
            "node": m.from_node, "air": m.place != "stand", "vis": round(m.vis, 2), "facing": FACE[m.facing],
            "born_how": m.born_how, "born": round(m.born_t, 3), "can": None if m.can_lo is None else [m.can_lo, m.can_hi]}


def out_path(cap, kept=None, tag=None) -> Path:
    return OUT / ("_".join([cap.replace("#", "_")] + ([kept] if kept else []) + ([tag] if tag else [])) + ".pkl")


def run(cap, hints=False) -> dict:
    mp = Map(map_of(cap))
    trk = tracker(mp)
    d = dump.out_dir(cap)
    seen = seen_rule() if hints else None
    rows, feet, ms, asked = [], [], [], []
    for kch in range(dump.meta(cap)["chunks"]):
        rs = pickle.loads((d / f"rows_{kch:03d}.pkl").read_bytes())
        bs = pickle.loads((d / f"bits_{kch:03d}.pkl").read_bytes())
        for r, (n, sh, wo) in zip(rs, bs):
            assert n == r["n"]
            f = Facts(r, hints, seen)
            ev = LazyBits(sh, wo)
            a = time.perf_counter()
            trk.update(f, ev, n=r["n"])
            ms.append(1000 * (time.perf_counter() - a) - 1000 * ev.dec)
            asked.append(trk.asked)
            recs = trk.records
            rows.append({"n": r["n"], "t": r["t"], "mobs": [row_of(m) for m in recs]})
            if r["C"] is not None:
                feet += [(m.id, m.kind, r["n"], r["t"], m.x, m.y, m.pose, m.facing) for m in recs if m.seen]
    return {"rows": rows, "feet": feet, "ms": np.array(ms), "asked": np.array(asked), "stats": trk.stats,
            "rem": trk.rem, "episodes": trk.episodes, "ended": trk.ended, "trk": trk}


class _Ended:
    def __init__(self, ended):
        self.ended = ended


def grade(cap, res) -> dict:
    tk = ticks(cap)
    ch = cache.chains(cap, tk)
    rows = res["rows"]
    s = S.score(tk, ch, rows, S.me_fn(tk))
    f = P.sticky(tk, ch, rows)
    P.why_switch(tk, ch, rows, _Ended(res["ended"]), 0)
    gh = P.ghosts_by_state(tk, ch, rows)
    return {"score": s, "sticky": f, "why": P.why_switch.last, "ghosts": gh}


def cmd_run(caps, kept, hints, tag):
    OUT.mkdir(parents=True, exist_ok=True)
    for cap in caps:
        a = time.perf_counter()
        res = run(cap, hints)
        b = time.perf_counter()
        gr = grade(cap, res)
        res.pop("trk")
        res.update(gr)
        res["cap"], res["kept"], res["hints"] = cap, kept, hints
        p = out_path(cap, kept, tag)
        p.write_bytes(pickle.dumps(res, protocol=pickle.HIGHEST_PROTOCOL))
        print(S.report(gr["score"], f"{name_of(cap)} [track/mobs.py{' + hints' if hints else ''}]"))
        print(P.sticky_report(gr["sticky"]))
        print(gr["ghosts"])
        print(f"  ms a frame p50 / p90 / p99 / max {S.pct(res['ms'], (50, 90, 99, 100))}; run {b - a:.0f} s, grade "
              f"{time.perf_counter() - b:.0f} s -> {p}", flush=True)


def report(rs: list, name: str) -> str:
    L = [S.report(S.merge([r["score"] for r in rs]), name)]
    st = P.merge_sticky([r["sticky"] for r in rs])
    L.append(P.sticky_report(st))
    stats = Counter()
    rems, whys = [], Counter()
    for r in rs:
        stats.update(r["stats"])
        rems += r["rem"]
        whys.update(r["why"])
    L.append("  ended: " + ", ".join(f"{k[5:]} {v}" for k, v in sorted(stats.items()) if k.startswith("end: ")))
    L.append("  other: " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items()) if not k.startswith("end: ")))
    again = [x for x in rems if x[1] == "seen again" and x[2] is not None]
    L.append(f"  remembered {len(rems)} times; seen again {len(again)}, next to its set "
             f"{100 * np.mean([x[2] for x in again]) if again else 0:.2f} %")
    L.append(P.mem_report(rems))
    L.append(f"  FAIR SWITCHES by why, all captures ({sum(whys.values())}):")
    L += [f"    {n:4d}  {w}" for w, n in whys.most_common()]
    for r in rs:
        L.append(f"  {r['cap']}: {r['ghosts'].strip()}")
    ms = np.concatenate([r["ms"] for r in rs])
    L.append(f"  ms a frame (CPU evidence, decode apart) p50 / p90 / p99 {S.pct(ms, (50, 90, 99))}")
    return "\n".join(L)


def gate_lines(rs: list) -> str:
    """The step 3 gate's kept-replay rows (PLAN-tracker step 3), each with its number."""
    s = S.merge([r["score"] for r in rs])
    st = P.merge_sticky([r["sticky"] for r in rs])
    found = 100 * s["found"][1] / max(1, s["found"][0])
    g = st["gaps"]
    held = 100 * np.mean([h for _, h in g])
    by = []
    for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.5), (1.5, 99)):
        b = [h for d, h in g if lo < d <= hi]
        by.append(100 * np.mean(b) if b else float("nan"))
    sc = np.array(st["sw_clear"])
    one = 100 * np.mean(sc == 0)
    extra = int(np.sum(st["sw"]))
    whys = Counter()
    for r in rs:
        whys.update(r["why"])
    changed = sum(n for w, n in whys.items() if "the track changed mob" in w)
    rems = [x for r in rs for x in r["rem"]]
    again = [x[2] for x in rems if x[1] == "seen again" and x[2] is not None]
    nxt = 100 * np.mean(again) if again else 0.0
    d = [x["s"] for x in s["dead"]]
    p90 = float(np.percentile(d, 90)) if d else float("nan")
    gseen = 0
    for r in rs:
        part = r["ghosts"].split("seen ")[1].split(" of")[0]
        gseen += int(part)

    def ok(v):
        return "met" if v else "MISSED"
    L = [f"  found {found:.2f} % (>= 98.4)  {ok(found >= 98.4)}",
         f"  id kept across a cover {held:.2f} % (>= 93.1)  {ok(held >= 93.1)}",
         "  ... by length " + " / ".join(f"{v:.1f}" for v in by) + " (>= 96.7 / 96.2 / 93.3 / 79.1 / 77.1)  "
         + ok(all(v >= t for v, t in zip(by, (96.7, 96.2, 93.3, 79.1, 77.1)))),
         f"  one id for life not beside another mob {one:.2f} % (>= 90.6)  {ok(one >= 90.6)}",
         f"  extra ids {extra} (<= 1,032)  {ok(extra <= 1032)}",
         f"  'the track changed mob' {changed} (<= 10)  {ok(changed <= 10)}",
         f"  next to its set {nxt:.2f} % of {len(again)} (>= 99.0)  {ok(nxt >= 99.0)}",
         f"  a death seen noticed p90 {p90:.3f} s (<= 0.05)  {ok(p90 <= 0.05)}",
         f"  seen track-frames with no truth mob within 40 px: {gseen} (0)  {ok(gseen == 0)}"]
    return "\n".join(L)


def load_res(caps, kept=None, tag=None) -> list:
    return [pickle.loads(out_path(c, kept, tag).read_bytes()) for c in caps]


def cmd_pool(caps, kept, tag):
    rs = load_res(caps, kept, tag)
    print(report(rs, f"POOLED track/mobs.py ({len(rs)} captures{', ' + tag if tag else ''})"))
    print("GATE (kept replay):")
    print(gate_lines(rs))


# ---------------------------------------------------------------------------------------------- measurement 3
def cmd_feet(caps, kept, tag):
    """proto_feet.py's hops and jolts on the REAL tracker's settled feet: per track its runs of consecutive seen
    frames (as the truth's tracklets, max_gap 0), jumper kinds, 15+ frames."""
    from proto_feet import height
    hops, jolt = [], [0, 0]
    for cap in caps:
        res = pickle.loads(out_path(cap, kept, tag).read_bytes())
        mp = Map(map_of(cap))
        nav = mp.nav
        from maplebrain.config import Track
        from maplebrain.perception.vote import load_poses
        from maplebrain.track.kinds import kinds
        c = Track()
        kd = kinds(mp.mobs, load_poses(mp.id, ASSETS), c.mob_speed_x, c.knock_v)
        rows = res["rows"]
        idx = {r["n"]: i for i, r in enumerate(rows)}
        cam = [r for r in rows]
        _ = cam
        by = {}
        for tid, kind, n, t, x, y, pose, facing in res["feet"]:
            by.setdefault(tid, []).append((idx[n], t, x, y, kind))
        for tid, pts in by.items():
            runs, cur = [], [pts[0]]
            for p in pts[1:]:
                if p[0] == cur[-1][0] + 1:
                    cur.append(p)
                else:
                    runs.append(cur)
                    cur = [p]
            runs.append(cur)
            for ser in runs:
                k = kd.get(ser[0][4])
                if k is None or not k.jump or len(ser) < 15:
                    continue
                t = np.array([s[1] for s in ser])
                ys_ = np.array([s[3] for s in ser], float)
                okd = (np.diff(t)[:-1] < 0.03) & (np.diff(t)[1:] < 0.03)
                d2 = np.abs(ys_[2:] - 2 * ys_[1:-1] + ys_[:-2])[okd]
                jolt[0] += int((d2 >= 13).sum())
                jolt[1] += len(d2)
                h = np.array([np.nan if (v := height(nav, s[2], s[3]))[0] is None else v[0] for s in ser])
                i, n = 0, len(ser)
                while i < n:
                    if np.isnan(h[i]) or h[i] <= 3:
                        i += 1
                        continue
                    a = i
                    while i < n and not np.isnan(h[i]) and h[i] > 3:
                        i += 1
                    b = i
                    if a == 0 or b >= n or not (12 <= b - a <= 70) or np.ptp(np.diff(t[a - 1:b + 1])) > 0.012:
                        continue
                    tt = t[a:b] - t[a]
                    ys = ys_[a:b]
                    cs = np.polyfit(tt, ys, 2)
                    rs = float(np.sqrt(np.mean((np.polyval(cs, tt) - ys) ** 2)))
                    hops.append((ser[0][4], rs, float(np.nanmax(h[a:b])), b - a))
    H = np.array([h[1] for h in hops]) if hops else np.zeros(0)
    print(f"hops fitted on the tracker's tracks: {len(hops)} ({dict(Counter(h[0] for h in hops))})")
    if len(H):
        print(f"  parabola residual of the settled feet, px rms p50 / p90 / p99: "
              f"{[round(float(np.percentile(H, p)), 2) for p in (50, 90, 99)]}")
        print(f"  hops within 1.5 px rms: {np.mean(H <= 1.5):.1%} (>= 91 %)   within 2.0: {np.mean(H <= 2):.1%}")
    print(f"  feet jolts of 13 px or more between frames ({jolt[1]} frame steps): {jolt[0]} (<= 500)")


# ---------------------------------------------------------------------------------------------- the labels
def cmd_labels(tag):
    """L1 (mobs: stand / air, the node of standing mobs), L2 (cover, the agreed cases), L3 (how born, the agreed
    cases), L8 (reported): the real tracker's rows on the labelled frames, every miss listed by case."""
    import glob
    import json
    lab_dir = Path(r"F:\dev\maple-corpus\labels")
    res = {}

    def rows_of(cap):
        if cap not in res:
            res[cap] = {r["n"]: r for r in pickle.loads(out_path(cap, None, tag).read_bytes())["rows"]}
        return res[cap]

    def cam(cap):
        if cap not in cams:
            cams[cap] = {r["n"]: r["C"] for r in dump.rows(cap)}
        return cams[cap]
    cams = {}
    # ---- L1
    n_pl, ok_pl, n_nd, ok_nd, miss = 0, 0, 0, 0, []
    for p in sorted(glob.glob(str(lab_dir / "*" / "labels" / "L1.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        cap = d["run"]
        rw = rows_of(cap)
        for n, fr in d["frames"].items():
            n = int(n)
            ms = [m for m in rw[n]["mobs"] if m["state"] != "tentative"]
            for lm in fr["mobs"]:
                if lm["place"] not in ("stand", "air", "fly"):
                    continue
                fx, fy = lm["feet"]
                near = sorted((abs(m["sx"] - fx) + abs(m["sy"] - fy), k) for k, m in enumerate(ms)
                              if abs(m["sx"] - fx) <= 25 and abs(m["sy"] - fy) <= 25 and m["src"] != "none")
                n_pl += 1
                if not near:
                    miss.append((cap, n, fr.get("case"), "no seen track", lm["place"], lm.get("node"), lm["feet"]))
                    continue
                m = ms[near[0][1]]
                lab_st = lm["place"] == "stand"
                trk_st = not m["air"]
                ok_pl += lab_st == trk_st
                if lab_st != trk_st:
                    miss.append((cap, n, fr.get("case"), "stand/air", lm["place"], "track air" if m["air"] else "track stand",
                                 lm["feet"]))
                if lab_st and trk_st:
                    n_nd += 1
                    ok_nd += m["node"] == lm["node"]
                    if m["node"] != lm["node"]:
                        miss.append((cap, n, fr.get("case"), "node", lm["node"], m["node"], lm["feet"]))
    nf = sum(1 for x in miss if x[3] == "no seen track")
    print(f"L1 mobs: stand / air {ok_pl} of {n_pl - nf} matched ({100 * ok_pl / max(1, n_pl - nf):.2f} %, >= 99); "
          f"{nf} labelled mobs with no seen track within 25 px; the node {ok_nd} of {n_nd} standing "
          f"({100 * ok_nd / max(1, n_nd):.2f} %, >= 99.5)")
    for x in miss:
        print("   ", x)
    # ---- L2 (the agreed cases): what covers the remembered mob
    to_lab = {"out of view": "edge", "ui / scenery": ("ui", "scenery"), "us": "us", "player": "player", "mob": "mob",
              "drop": "drop", "effect": "effect", "none": "none", "fading in": "fade"}
    n2, ok2 = 0, 0
    print("L2 (agreed cases):")
    for p in sorted(glob.glob(str(lab_dir / "*" / "labels" / "L2.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        cap = d["run"]
        rw = rows_of(cap)
        for n, fr in d["frames"].items():
            if not fr.get("agreed"):
                continue
            n = int(n)
            lm = fr["mobs"][0]
            C = cam(cap)[n]
            mx, my = lm["feet"][0] + C[0], lm["feet"][1] + C[1]
            cs = [m for m in rw[n]["mobs"] if m["mob"] == lm["type"] and m["state"] != "tentative"
                  and abs(m["x"] - mx) <= 60 and abs(m["y"] - my) <= 60]
            cs.sort(key=lambda m: (m["src"] != "none", abs(m["x"] - mx) + abs(m["y"] - my)))
            n2 += 1
            if not cs:
                print(f"    MISS case {fr['case']} {cap} n {n}: label {lm['cover']} - no track of the kind within 60 px")
                continue
            m = cs[0]
            got = "none" if m["src"] != "none" else m["cover"]
            want = to_lab.get(got, got)
            hit = lm["cover"] in (want if isinstance(want, tuple) else (want,))
            ok2 += hit
            print(f"    {'ok  ' if hit else 'MISS'} case {fr['case']} {cap} n {n}: label {lm['cover']:8s} tracker "
                  f"{got} (track {m['id']}, {m['state']}, unseen {m['unseen']} s; prototype {fr['class']})")
    print(f"L2: {ok2} of {n2} = {100 * ok2 / max(1, n2):.1f} % (>= 90)")
    # ---- L3 (the agreed cases): how born
    how = {"faded in": "fade", "came into view": "view", "uncovered": "uncover", "there at entry": "entry",
           "dying": "dying"}
    n3, ok3 = 0, 0
    print("L3 (agreed cases):")
    for p in sorted(glob.glob(str(lab_dir / "*" / "labels" / "L3.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        cap = d["run"]
        rw = rows_of(cap)
        for n, fr in d["frames"].items():
            if not fr.get("agreed"):
                continue
            n = int(n)
            lm = fr["mobs"][0]
            fx, fy = lm["feet"]
            cs = [m for m in rw[n]["mobs"] if m["mob"] == lm["type"] and abs(m["sx"] - fx) <= 24
                  and abs(m["sy"] - fy) <= 24]
            cs.sort(key=lambda m: (m["src"] == "none", abs(m["sx"] - fx) + abs(m["sy"] - fy)))
            n3 += 1
            if not cs:
                print(f"    MISS case {fr['case']} {cap} n {n}: label {lm['born_how']} - no track there")
                continue
            m = cs[0]
            got = how.get(m["born_how"], m["born_how"])
            hit = got == lm["born_how"]
            ok3 += hit
            print(f"    {'ok  ' if hit else 'MISS'} case {fr['case']} {cap} n {n}: label {lm['born_how']:8s} tracker "
                  f"{got} (track {m['id']} born {m['born']}, {m['state']}; prototype {fr['class']})")
    print(f"L3: {ok3} of {n3} = {100 * ok3 / max(1, n3):.1f} % (>= 95)")
    # ---- L8 (reported): a remembered mob there / not there - does the tracker keep a track there?
    c8 = Counter()
    for p in sorted(glob.glob(str(lab_dir / "*" / "labels" / "L8.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        cap = d["run"]
        rw = rows_of(cap)
        for n, fr in d["frames"].items():
            n = int(n)
            rm = fr["remembered"]
            lo, hi = rm["can"]
            ks = [m for m in rw[n]["mobs"] if m["mob"] == rm["type"] and m["state"] != "tentative"
                  and ((m["can"] and m["can"][0] <= hi + 24 and m["can"][1] >= lo - 24) or lo - 24 <= m["x"] <= hi + 24)]
            c8[(rm["there"], "kept" if ks else "not kept")] += 1
    print("L8 (reported): label there? x the tracker keeps a track of the kind over the range:",
          ", ".join(f"{a} / {b}: {v}" for (a, b), v in sorted(c8.items())))


# ---------------------------------------------------------------------------------------------- the live path
def cmd_live(cap, kept):
    """The new kept replay's shadow rows (the GPU path: the Perceiver's own tracker, dump.py) against the rows of
    this tool over the same kept replay (the bitmap path), and the GPU evidence against the bitmaps."""
    dump.KEPT = kept
    rows = dump.rows(cap)
    rp = pickle.loads(out_path(cap, kept, None).read_bytes())["rows"]
    by = {r["n"]: r for r in rp}
    n, same, diff = 0, 0, []
    keys = ("id", "mob", "state", "x", "y", "src", "cover")
    for r in rows:
        sh = r.get("shadow")
        if sh is None:
            continue
        a = {m["id"]: m for m in sh}
        b = {m["id"]: m for m in by[r["n"]]["mobs"]}
        for i in set(a) | set(b):
            n += 1
            ma, mb = a.get(i), b.get(i)
            eq = ma is not None and mb is not None and all(ma[k] == mb[k] for k in keys)
            same += eq
            if not eq and len(diff) < 20:
                diff.append((r["n"], i, ma and {k: ma[k] for k in keys}, mb and {k: mb[k] for k in keys}))
    print(f"shadow rows = replay rows on {same} of {n} track-frames ({100 * same / max(1, n):.3f} %, >= 99.5)")
    for x in diff:
        print("   ", x)
    ev = [r["ev_check"] for r in rows if r.get("ev_check")]
    asked = sum(e[0] for e in ev)
    agree = sum(e[1] for e in ev)
    print(f"GPU evidence = the bitmaps' on {agree} of {asked} places asked ({100 * agree / max(1, asked):.3f} %, >= 99.9)"
          f" over {len(ev)} frames")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--kept", default=None)
    ap.add_argument("--hints", action="store_true")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    if a.kept:
        dump.KEPT = a.kept
    caps = cache.SOUND if a.sound else a.caps
    if a.cmd == "run":
        if a.jobs > 1:                          # one process per capture, `jobs` at a time
            procs, todo = [], list(caps)
            while todo or procs:
                while todo and len(procs) < a.jobs:
                    cap = todo.pop(0)
                    cmd = [sys.executable, str(Path(__file__)), "run", cap] + (["--kept", a.kept] if a.kept else []) \
                        + (["--hints"] if a.hints else []) + (["--tag", a.tag] if a.tag else [])
                    procs.append(subprocess.Popen(cmd, cwd=ROOT))
                procs = [p for p in procs if p.poll() is None]
                time.sleep(1)
            return
        cmd_run(caps, a.kept, a.hints, a.tag)
    elif a.cmd == "pool":
        cmd_pool(caps, a.kept, a.tag)
    elif a.cmd == "feet":
        cmd_feet(caps, a.kept, a.tag)
    elif a.cmd == "labels":
        cmd_labels(a.tag)
    elif a.cmd == "live":
        cmd_live(caps[0], a.kept)
    else:
        raise SystemExit(f"unknown command {a.cmd}")


if __name__ == "__main__":
    main()
