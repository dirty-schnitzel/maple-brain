"""PLAN-tracker step 4a: THE REAL DROP TRACKER FROM A KEPT REPLAY - maplebrain/track/drops.py over every frame of a
capture's kept replay (dump.py: the finder's sightings + the two bitmaps; no GPU), beside the real mob tracker
(track/mobs.py: the deaths from_mob is read from), our feet (the row's me_map) and our keys (keys.jsonl) - graded
like the prototype: proto_drops.numbers() reads this tool's results as it reads its own.

    python tools/perc/track/replay_drops.py run CAP [CAP ...] | --sound [--truth] [--jobs N] [--tag T]
    python tools/perc/track/replay_drops.py numbers [--sound | CAP ...] [--truth] [--tag T]   measurement 5 + the gate
    python tools/perc/track/replay_drops.py port [--sound | CAP ...]     the --truth run against the prototype's lives
    python tools/perc/track/replay_drops.py l6 [--truth] [--tag T]       L6: the mob each labelled drop came from
    python tools/perc/track/replay_drops.py sheets pairs|hops [--sound | CAP ...] [--tag T]   by-eye sheets

`run` writes OUT/<cap>[_truth][_<tag>].pkl (OUT = CORPUS/work/track-plan/step4a): the prototype's result layout
(proto_drops.run: lives, ms, alive, looks, T, N, me, deaths, keys, ...). `--truth`: the deaths are the truth's chains'
first die poses (proto_drops.deaths_of, what the prototype read) instead of the mob tracker's - the port check
(`port`: the same lives as the prototype's kept ones; the only allowed difference is "we took it" where our pickup key
was held through the window but not pressed in it: PLAN-tracker measurement 5). `sheets pairs`: two lives of one
item overlapping within 3 px that were not both sighted on one frame (the gate's "each looked at"); `sheets hops`:
the pickup hops seen while our pickup key was not down (the gate's "no hop without it").
"""
import argparse
import json
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
import load  # noqa: E402
import proto_drops as P  # noqa: E402
from replay_mobs import Facts, LazyBits  # noqa: E402

OUT = Path(r"F:\dev\maple-corpus\work\track-plan\step4a")


def out_path(cap, truth=False, tag=None) -> Path:
    return OUT / ("_".join([cap.replace("#", "_")] + (["truth"] if truth else []) + ([tag] if tag else [])) + ".pkl")


def again_of(d, done, cfg) -> list:
    """proto_drops.again_of on the real tracker's drops: the drops of the same item that ended at d's place before
    d was born, each with how well ITS bob predicts d's first 2 s of sightings."""
    out = []
    for o in done:
        if o is d or o.item != d.item or o.x != d.x or abs(o.yf - d.yf) > 2 or o.end["t"] > d.born_t + 0.3 \
                or d.born_t - o.born_t > cfg.drop_life_s + 5:
            continue
        e = [abs(y - o.expect(t, cfg)) for t, y in d.first if o.expect(t, cfg) is not None]
        out.append((o.id, round(d.born_t - o.end["t"], 3), round(d.born_t - o.born_t, 2),
                    round(float(np.mean(e)), 2) if e else None, len(e), o.end["how"]))
    return out


def life_of(d, pics, done, cfg) -> dict:
    return {"id": d.id, "item": d.item, "name": pics.name(d.item), "class": pics.cls(d.item), "x": d.x, "yf": d.yf,
            "fh": d.fh, "layer": d.layer, "node": d.node, "born_t": d.born_t, "born_n": d.born_n, "n_rest": d.n_rest,
            "n_weak": d.n_weak, "y_lo": d.y_lo, "y_hi": d.y_hi, "from_mob": d.from_mob, "n_from": d.n_from,
            "near": d.near or [], "fly": None, "end": d.end, "cover": dict(d.cov_n), "twin": d.twin,
            "again": again_of(d, done, cfg), "born_view": d.landed,
            "first_span": round(d.first[-1][0] - d.first[0][0], 3) if d.first else 0.0}


def run(cap, truth=False, verbose=True) -> dict:
    from maplebrain.config import Config
    from maplebrain.perception.vote import load_poses
    from maplebrain.track.drops import DropTracker, Fronts, Pictures
    from maplebrain.track.graph import Graph
    from maplebrain.track.kinds import kinds
    from maplebrain.track.mobs import MobTracker
    cfg = Config()
    c = cfg.track
    mp = load.Map(load.map_of(cap))
    g = Graph(mp.json, track=c, edges=False)
    pics = Pictures.load()
    trk = DropTracker(pics, Fronts.load(mp.id), g, cfg.keys.pickup, c, keep=True)
    mobs = None
    if truth:
        for t, x, y, k in P.deaths_of(cap):
            trk.add_death(t, x, y, k)
    else:
        mobs = MobTracker(g, kinds(mp.mobs, load_poses(mp.id, load.ASSETS), c.mob_speed_x, c.knock_v), c)
    look_s = [0.0]
    orig = trk._look

    def timed(*a):
        s = time.perf_counter()
        r = orig(*a)
        look_s[0] += time.perf_counter() - s
        return r
    trk._look = timed
    keys = sorted(load.keys(cap), key=lambda k: k["t"])
    ki = 0
    ms, alive, looks, T, N, me_at, cams = [], [], [], [], [], [], []
    n_looks = 0
    t0 = time.perf_counter()
    d = dump.out_dir(cap)
    n = t = None
    for kch in range(dump.meta(cap)["chunks"]):
        rs = pickle.loads((d / f"rows_{kch:03d}.pkl").read_bytes())
        bs = pickle.loads((d / f"bits_{kch:03d}.pkl").read_bytes())
        for r, (nb, sh, wo) in zip(rs, bs):
            assert nb == r["n"]
            n, t = r["n"], r["t"]
            f = Facts(r)
            ev = LazyBits(sh, wo)
            recs = None
            if mobs is not None:
                mobs.update(f, ev, n=n)
                recs = mobs.records
            k0 = ki
            while ki < len(keys) and keys[ki]["t"] <= t:
                ki += 1
            dec0 = ev.dec
            a = time.perf_counter()
            trk.update(f, ev, me=r["me_map"], keys=keys[k0:ki], mobs=recs, n=n)
            dt = time.perf_counter() - a - (ev.dec - dec0)
            look_s[0] -= ev.dec - dec0
            ms.append(1000 * dt)
            alive.append(sum(1 for lst in trk.live.values() for x in lst if x.conf))
            looks.append(trk.looks)
            n_looks += trk.looks
            T.append(t)
            N.append(n)
            me_at.append(r["me_map"])
            cams.append(r["C"])
        del rs, bs
    trk.finish(n, t)
    z = list(trk.presses)
    res = {"cap": str(cap), "map": mp.id, "frames": len(T), "t": [T[0], T[-1]], "truth": truth,
           "lives": [life_of(x, pics, trk.done, c) for x in sorted(trk.done, key=lambda x: x.id)],
           "ms": np.array(ms, np.float32), "alive": np.array(alive, np.int16), "looks": np.array(looks, np.int16),
           "T": np.array(T), "N": np.array(N), "me": me_at, "z": z, "deaths": list(trk.deaths),
           "stats": dict(trk.stats), "eps": [], "look_ms": 1000 * look_s[0], "n_looks": n_looks,
           "wall_s": time.perf_counter() - t0, "blind": trk.stats["blind"], "bob_err": {}, "C": cams,
           "keys": {k: sorted(x["t"] for x in keys if x["key"] == k and x["down"]) for k in ("q", "w", "e", "z")},
           "mob_stats": dict(mobs.stats) if mobs is not None else None}
    if verbose:
        print(f"{cap}: {len(T)} frames in {res['wall_s']:.0f} s; {len(res['lives'])} drops; deaths {len(trk.deaths)} "
              f"({'truth' if truth else 'the mob tracker'}); stats {dict(trk.stats)}", flush=True)
    return res


# ---------------------------------------------------------------------------------------------- the gate
def took_by_press(l, cfg) -> bool:
    """The prototype's rule on a kept life: a press of the pickup key in the last pick_s with our feet in reach then."""
    for dz, dx, dy in l["end"]["z"]:
        if dz <= cfg.pick_s and dx is not None and abs(dx) <= cfg.reach_x and -cfg.reach_up <= dy <= cfg.reach_down:
            return True
    return False


def hops_without_key(r) -> list:
    """In-view ends whose pickup hop was seen (>= 2 hop sightings) that are not "we took it"."""
    return [l for l in r["lives"] if l["end"]["how"] in ("we took it", "gone in view") and l["end"]["hop"] >= 2
            and l["end"]["how"] != "we took it"]


def open_pairs(r) -> list:
    """Two lives of one item overlapping in time within 3 px (12 px in y) not both sighted on one frame."""
    out, by = [], {}
    for l in r["lives"]:
        by.setdefault(l["item"], []).append(l)
    for ls in by.values():
        for i, a in enumerate(ls):
            for b in ls[i + 1:]:
                if abs(a["x"] - b["x"]) <= 3 and abs(a["yf"] - b["yf"]) <= 12:
                    lo, hi = max(a["born_t"], b["born_t"]), min(a["end"]["t"], b["end"]["t"])
                    if hi - lo > 0.05 and not (a["twin"] and b["twin"]):
                        out.append((a, b, hi - lo))
    return out


def gate_lines(rs) -> str:
    from maplebrain.config import Track
    c = Track()
    lives = [l for r in rs for l in r["lives"]]
    born = [l for l in lives if l["born_view"]]
    one = sum(1 for l in born if l["n_from"] == 1)
    over = sum(l["end"]["age"] > 131 for l in lives)
    again = [(l, x) for l in lives for x in l["again"] if x[1] <= 3.0]
    same = [(l, x) for l, x in again if x[3] is not None and x[3] <= 0.8 and x[4] >= 20]
    pairs = [p for r in rs for p in open_pairs(r)]
    hops = {r["cap"]: len(hops_without_key(r)) for r in rs}
    ms = np.concatenate([r["ms"] for r in rs])
    p50 = float(np.percentile(ms, 50))

    def ok(v):
        return "met" if v else "MISSED"
    nd = len(lives)
    L = [f"  drops {nd} (746, within 1 %: 739-753)  {ok(739 <= nd <= 753)}",
         f"  lives with two items 0 (the item is the link's key); over 131 s {over} (0)  {ok(over == 0)}",
         f"  'gone' then seen again (the old bob fits the new life <= 0.8 px over >= 20 sightings, born within 3 s): "
         f"{len(same)} of {len(again)} re-births at one place (0)  {ok(not same)}",
         f"  pairs of one item within 3 px, not twins: {len(pairs)} (<= 9, each looked at: `sheets pairs`)  "
         f"{ok(len(pairs) <= 9)}",
         f"  exactly one death: {one} of {len(born)} landed in view = {100 * one / max(1, len(born)):.1f} % (>= 84.4)  "
         f"{ok(one >= 0.844 * len(born))}",
         f"  pickup hops seen without our key down ('we took it' with the key down: none on any of the {len(rs)}): "
         f"{sum(hops.values())} - " + ", ".join(f"{k} {v}" for k, v in hops.items() if v) + f"  {ok(not any(hops.values()))}",
         f"  ms a frame p50 {p50:.3f} (<= 0.2), p90 {np.percentile(ms, 90):.3f}, p99 {np.percentile(ms, 99):.3f}  "
         f"{ok(p50 <= 0.2)}"]
    how = Counter(l["end"]["how"] for l in lives)
    L.append(f"  how they ended: {dict(how.most_common())} (prototype: we took it 235, 130 s old 180, capture ended 155, "
             f"gone in view 123, found gone 53)")
    took = [l for l in lives if l["end"]["how"] == "we took it"]
    L.append(f"  'we took it' {len(took)}: by a press in the last {c.pick_s} s (the prototype's rule) "
             f"{sum(took_by_press(l, c) for l in took)}, only by the key held through it "
             f"{sum(not took_by_press(l, c) for l in took)}")
    return "\n".join(L)


def load_res(caps, truth=False, tag=None) -> list:
    return [pickle.loads(out_path(cp, truth, tag).read_bytes()) for cp in caps]


def cmd_numbers(caps, truth, tag):
    rs = load_res(caps, truth, tag)
    P.numbers(rs[:1], f"{rs[0]['cap']} [track/drops.py{' + truth deaths' if truth else ''}]")
    if len(rs) > 1:
        P.numbers(rs, f"pooled over {len(rs)} captures [track/drops.py{' + truth deaths' if truth else ''}]")
    print("\nGATE (kept replay):")
    print(gate_lines(rs))
    for r in rs:
        print(f"  {r['cap']}: {len(r['lives'])} drops, deaths {len(r['deaths'])}, stats {r['stats']}")


# ---------------------------------------------------------------------------------------------- the port check
def cmd_port(caps):
    """The --truth run (the deaths the prototype read) against the prototype's kept lives, capture by capture."""
    from maplebrain.config import Track
    c = Track()
    tot = Counter()
    for cap in caps:
        mine = {(l["item"], l["x"], l["born_n"]): l for l in pickle.loads(out_path(cap, True).read_bytes())["lives"]}
        ref = {(l["item"], l["x"], l["born_n"]): l for l in P.kept(cap)["lives"]}
        both = set(mine) & set(ref)
        dif = Counter()
        rows = []
        for k in sorted(both, key=lambda k: k[2]):
            a, b = mine[k], ref[k]
            if a["end"]["n"] != b["end"]["n"]:
                dif["end frame"] += 1
                rows.append(("end frame", k, a["end"]["n"], a["end"]["how"], b["end"]["n"], b["end"]["how"]))
            if a["end"]["how"] != b["end"]["how"]:
                held = a["end"]["how"] == "we took it" and b["end"]["how"] == "gone in view" and not took_by_press(a, c)
                dif["how: the key held (allowed)" if held else "how"] += 1
                if not held:
                    rows.append(("how", k, a["end"]["how"], b["end"]["how"]))
            if a["from_mob"] != b["from_mob"]:
                dif["from_mob"] += 1
                rows.append(("from_mob", k, a["from_mob"], b["from_mob"]))
            if a["born_view"] != b["born_view"] or a["twin"] != b["twin"] or a["cover"] != b["cover"]:
                dif["landed / twin / covers"] += 1
                rows.append(("landed / twin / covers", k))
        only_m, only_r = set(mine) - both, set(ref) - both
        print(f"{cap}: real {len(mine)}, prototype {len(ref)}, the same {len(both)}; only real {len(only_m)}, only "
              f"prototype {len(only_r)}; differences {dict(dif)}")
        for x in rows[:12]:
            print("    ", x)
        for k in sorted(only_m)[:5]:
            print("     only real", k)
        for k in sorted(only_r)[:5]:
            print("     only prototype", k)
        tot.update({"real": len(mine), "prototype": len(ref), "same": len(both), "only real": len(only_m),
                    "only prototype": len(only_r)})
        tot.update(dif)
    print(f"ALL: {dict(tot)}")


# ---------------------------------------------------------------------------------------------- L6
def cmd_l6(truth, tag):
    """L6 (step 1's labels, 50 drops): the mob each came from - the tracker's from_mob against the label's death
    (the death the labeller lettered: its time and place; `none`: no death; `?`: not counted)."""
    import glob
    lab_dir = Path(r"F:\dev\maple-corpus\labels")
    n_ok = n_all = 0
    rows, skip = [], Counter()
    for p in sorted(glob.glob(str(lab_dir / "*" / "labels" / "L6.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        cap = d["run"]
        r = pickle.loads(out_path(cap, truth, tag).read_bytes())
        deaths = {k: (t, x, y) for t, x, y, k in r["deaths"]}
        for n, fr in d["frames"].items():
            n = int(n)
            lab = fr["drop"]
            want = lab["from"]
            if want == "?":
                skip["?"] += 1
                continue
            cs = [l for l in r["lives"] if l["item"] == lab["item"] and l["x"] == lab["x"] and abs(l["born_n"] - n) <= 30]
            cs.sort(key=lambda l: abs(l["born_n"] - n))
            n_all += 1
            if not cs:
                rows.append((fr["case"], cap, n, want, "no tracker drop there"))
                continue
            l = cs[0]
            got = l["from_mob"]
            dth = deaths.get(got) if got is not None else None
            if want == "none":
                hit = got is None
            else:
                ws = [lab["from_death"]] if lab.get("from_death") else (lab.get("from_either") or [])
                hit = dth is not None and any(w is not None and abs(dth[0] - w["t"]) <= 0.1 and abs(dth[1] - w["x"]) <= 30
                                              and abs(dth[2] - w["y"]) <= 30 for w in ws)
            n_ok += hit
            rows.append((fr["case"], cap, n, want, "ok" if hit else "MISS", got,
                         None if dth is None else tuple(round(v, 2) for v in dth), lab.get("from_death")))
    for x in sorted(rows, key=lambda x: x[0]):
        print("   ", x)
    print(f"L6: {n_ok} of {n_all} = {100 * n_ok / max(1, n_all):.1f} % (>= 90); not counted: {dict(skip)}")


# ---------------------------------------------------------------------------------------------- by eye
def cmd_sheets(what, caps, tag, truth=False):
    import frames as rec
    pics = P.Pictures()
    out = OUT / "sheets" / (what + ("_truth" if truth else ""))
    out.mkdir(parents=True, exist_ok=True)
    k = 0
    for cap in caps:
        res = pickle.loads(out_path(cap, truth, tag).read_bytes())
        clip = rec.clip(cap, False, "drops")
        T, N = res["T"], res["N"]

        def n_at(t):
            return int(N[min(len(N) - 1, int(np.searchsorted(T, t)))])
        rows = []
        if what == "pairs":
            for a, b, s in open_pairs(res):
                k += 1
                lo = max(a["born_t"], b["born_t"])
                head = [f"P{k:02d} {cap} {a['name']}  x {a['x']} / {b['x']} yf {a['yf']} / {b['yf']}: id {a['id']} "
                        f"{a['born_t']:.2f}-{a['end']['t']:.2f} ({a['end']['how']}), id {b['id']} {b['born_t']:.2f}-"
                        f"{b['end']['t']:.2f} ({b['end']['how']}); together {s:.1f} s",
                        "     tiles: the second's birth - 0.5 s / its birth / + 1 s / the first's end"]
                fs = [n_at(lo - 0.5), n_at(lo), n_at(lo + 1.0), min(a["end"]["n"], b["end"]["n"])]
                tiles = [P._tile(rec, clip, res, pics, a, nn)[0] for nn in fs]
                rows.append((head, [(tl, f"frame {nn}") for tl, nn in zip(tiles, fs)]))
        else:
            for l in hops_without_key(res):
                k += 1
                e = l["end"]
                head = [f"H{k:02d} {cap} id {l['id']} {l['name']} x {l['x']} yf {l['yf']} age {e['age']:.2f} -> "
                        f"{e['how']}; hop sightings {e['hop']}, hop dx {e['hop_dx']}; our feet at its last sighting "
                        f"{None if e['me'] is None else (e['me'][0] - l['x'], e['me'][1] - l['yf'])}; pickup key last "
                        f"down {e['z_before']} s before",
                        "     tiles: its last sighting - 0.1 s / the last sighting / + 0.15 s / + 0.3 s"]
                fs = [e["last_n"] - 6, e["last_n"], e["last_n"] + 9, e["last_n"] + 18]
                tiles = [P._tile(rec, clip, res, pics, l, nn)[0] for nn in fs]
                rows.append((head, [(tl, f"frame {nn}") for tl, nn in zip(tiles, fs)]))
        for i in range(0, len(rows), 3):
            P._sheet(rows[i:i + 3], out / f"{cap.replace('#', '_')}_{i // 3 + 1:02d}.png")
    print(f"{k} cases -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--truth", action="store_true")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--pin", action="store_true", help="run: pinned to the performance cores (the ms)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.pin:
        from maplebrain.procperf import prefer_performance
        print(prefer_performance(), flush=True)
    if a.cmd == "sheets":
        what, caps = a.caps[0], (cache.SOUND if a.sound else a.caps[1:])
        cmd_sheets(what, caps, a.tag, a.truth)
        return
    caps = cache.SOUND if a.sound else a.caps
    if a.cmd == "run":
        if a.jobs > 1:                          # one process per capture, `jobs` at a time
            procs, todo = [], list(caps)
            while todo or procs:
                while todo and len(procs) < a.jobs:
                    cp = todo.pop(0)
                    cmd = [sys.executable, str(Path(__file__)), "run", cp] + (["--truth"] if a.truth else []) \
                        + (["--tag", a.tag] if a.tag else [])
                    procs.append(subprocess.Popen(cmd, cwd=ROOT))
                procs = [p for p in procs if p.poll() is None]
                time.sleep(1)
            return
        for cp in caps:
            res = run(cp, a.truth)
            out_path(cp, a.truth, a.tag).write_bytes(pickle.dumps(res, protocol=pickle.HIGHEST_PROTOCOL))
    elif a.cmd == "numbers":
        cmd_numbers(caps, a.truth, a.tag)
    elif a.cmd == "port":
        cmd_port(caps)
    elif a.cmd == "l6":
        cmd_l6(a.truth, a.tag)
    else:
        raise SystemExit(f"unknown command {a.cmd}")


if __name__ == "__main__":
    main()
