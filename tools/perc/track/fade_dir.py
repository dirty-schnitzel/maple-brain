"""PLAN-tracker step 3b, try 3, MEASURE FIRST: the fade's direction (a spawn fades IN, a death fades OUT) over the
mob tracker's tracks of the 13 sound captures (replay_mobs.py's rows, `--tag`, default s4b) and the fit's own
sightings of the kept replay (opacity, pose).

    python tools/perc/track/fade_dir.py series [--tag s4b]     per track and seen frame: state, feet, the fit's
                                                                opacity + pose (its kind's sighting nearest the
                                                                row's screen feet, within 20 px) -> OUT/series_<tag>.pkl
    python tools/perc/track/fade_dir.py splits [--tag s4b]     1a: a track turns dying, then within 1 s a new track of
                                                                its kind within 30 px - a death taken back or a split
    python tools/perc/track/fade_dir.py deaths [--tag s4b]     1b: real deaths - the opacity over the die pose's frames
    python tools/perc/track/fade_dir.py births [--tag s4b]     1c: faded-in births - rising, flat or falling
    python tools/perc/track/fade_dir.py strips WHAT [--tag s4b] [--n 6]   strips of a few cases (WHAT: split kinds,
                                                                flat births) -> OUT/strips_<what>/

OUT = CORPUS/work/track-plan/step3b/fade. Times on the replay's own clock (row t); "frame k of the die pose" = the
k-th frame with a camera since the first die sighting (0 = the first), whether the mob was seen on it or not.
"""
import argparse
import pickle
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))
import cache  # noqa: E402
import proto_spawns as PS  # noqa: E402

OUT = PS.OUT / "fade"
FADE_L = PS.FADE_L                  # 0.827 s: the fade-in's length (try 2, p90)


def cmd_series(tag, nofit=False):
    """{cap: {id: [(n, t, state, x, y, sx, sy, seen, o, pose, born_how, born)]}}: every row of every track; o, pose
    from the fit when seen (else None; `nofit`: never - the splits' count needs only the rows)."""
    OUT.mkdir(parents=True, exist_ok=True)
    allc = {}
    for cap in cache.SOUND:
        rows = PS.rows_of(cap, tag)
        tr = defaultdict(list)
        for r in rows:
            k = None if nofit else PS.kept_row(cap, r["n"])
            fit = (k["facts"].get("fit") or []) if k else []
            for m in r["mobs"]:
                o = pose = None
                if m["src"] == "acq" and fit:
                    best = min(((abs(f["feet"][0] - m["sx"]) + abs(f["feet"][1] - m["sy"]), f) for f in fit
                                if f.get("type") == m["mob"]), default=(99, None), key=lambda p: p[0])
                    if best[1] is not None and best[0] <= 20:
                        o, pose = float(best[1]["opacity"]), best[1].get("pose")
                tr[m["id"]].append((r["n"], r["t"], m["state"], m["x"], m["y"], m["sx"], m["sy"], m["src"] == "acq",
                                    o, pose, m["born_how"], m["born"], m["mob"]))
        allc[cap] = dict(tr)
        print(cap, len(tr), "tracks", flush=True)
    (OUT / f"series_{tag}.pkl").write_bytes(pickle.dumps(allc, protocol=pickle.HIGHEST_PROTOCOL))


def load(tag):
    return pickle.loads((OUT / f"series_{tag}.pkl").read_bytes())


N, T, ST, X, Y, SX, SY, SEEN, O, POSE, HOW, BORN, KIND = range(13)


def is_die(p):
    return p is not None and str(p).startswith("die")


def splits(allc):
    """Every first `dying` row of a track, with: taken back (the same track alive again), the new tracks of its kind
    born within 1 s after, within 30 px, and the first track's age / how it was born / its opacity then."""
    out = []
    for cap, trs in allc.items():
        births = sorted((s[0][T], i, s[0][X], s[0][Y], s[0][KIND], s[0][HOW]) for i, s in trs.items())
        bt = np.array([b[0] for b in births])
        for i, s in trs.items():
            k = next((j for j, r in enumerate(s) if r[ST] == "dying"), None)
            if k is None:
                continue
            d = s[k]
            back = any(r[ST] != "dying" for r in s[k + 1:])
            lo, hi = np.searchsorted(bt, d[T] - 1e-6), np.searchsorted(bt, d[T] + 1.0)
            new = [b for b in births[lo:hi] if b[1] != i and b[4] == d[KIND]
                   and np.hypot(b[2] - d[X], b[3] - d[Y]) <= 30]
            seen_before = [r for r in s[:k] if r[SEEN] and r[O] is not None]
            o_prev = [r[O] for r in seen_before[-6:]]
            # another mob of its kind near when it turned dying (an overlap)
            near = 0
            for j, s2 in trs.items():
                if j == i:
                    continue
                for r in s2:
                    if r[N] == d[N]:
                        if r[SEEN] and r[KIND] == d[KIND] and abs(r[X] - d[X]) <= 40 and abs(r[Y] - d[Y]) <= 40:
                            near += 1
                        break
            hit = any(str(r[POSE]).startswith("hit") for r in s[max(0, k - 30):k] if r[POSE])
            out.append({"cap": cap, "id": i, "n": d[N], "t": d[T], "x": d[X], "y": d[Y], "kind": d[KIND],
                        "age": d[T] - s[0][T], "how": s[0][HOW], "back": back, "new": new, "o_prev": o_prev,
                        "o_die": next((r[O] for r in s[k:k + 3] if r[O] is not None), None), "near": near,
                        "hit": hit, "pose": next((r[POSE] for r in s[k:k + 3] if r[POSE]), None)})
    return out


def cmd_splits(tag):
    allc = load(tag)
    sp = splits(allc)
    print(f"tracks that turn dying (first die row): {len(sp)}; taken back (the same track alive again): "
          f"{sum(d['back'] for d in sp)}")
    fol = [d for d in sp if d["new"]]
    print(f"followed within 1 s by a new track of its kind within 30 px: {len(fol)} "
          f"(of them taken back too: {sum(d['back'] for d in fol)})")
    cls = Counter()
    for d in fol:
        fading = d["how"] == "faded in" and d["age"] < FADE_L
        rising = len(d["o_prev"]) >= 2 and d["o_prev"][-1] - d["o_prev"][0] > 0.02
        d["cls"] = ("while fading in (born faded in, < 0.83 s old)" if fading else
                    "overlap (another mob of its kind within 40 px)" if d["near"] else
                    "after a hit pose (knockback)" if d["hit"] else "other")
        d["rising"] = rising
        cls[d["cls"]] += 1
    for k, v in cls.most_common():
        print(f"  {v:4d}  {k}")
    fi = [d for d in fol if d["cls"].startswith("while fading")]
    if fi:
        print("  while fading in: age at the false death p50 / max %.2f / %.2f s; opacity at it p50 %.2f; the opacity "
              "rising over its last sightings before it: %d of %d" % (np.median([d["age"] for d in fi]),
                                                                       max(d["age"] for d in fi),
                                                                       np.median([d["o_die"] or np.nan for d in fi]),
                                                                       sum(d["rising"] for d in fi), len(fi)))
    for d in sorted(fol, key=lambda d: (d["cls"], d["cap"], d["n"])):
        print(f"  {d['cls'][:28]:28s} {d['cap']:22s} n {d['n']:6d} id {d['id']:4d} -> "
              f"{[b[1] for b in d['new']]} age {d['age']:.2f} {d['how']:14s} o_prev "
              f"{[round(o, 2) for o in d['o_prev']]} o_die {d['o_die']} pose {d['pose']} back {d['back']}")
    (OUT / f"splits_{tag}.pkl").write_bytes(pickle.dumps(sp))


def cmd_deaths(tag, K=24):
    """Real deaths: a track whose first die row is never followed by its own live row and not by a new track of its
    kind within 30 px in 1 s. Its opacity on frames k = 0..K of the die pose (seen frames with the fit's die pose)."""
    allc = load(tag)
    sp = splits(allc)
    real = [d for d in sp if not d["back"] and not d["new"]]
    byk = defaultdict(list)
    first_fall, n_full = [], []
    for d in real:
        s = allc[d["cap"]][d["id"]]
        k0 = next(j for j, r in enumerate(s) if r[ST] == "dying")
        seq = []
        for j, r in enumerate(s[k0:k0 + K + 1]):
            byk[j].append(r[O] if r[SEEN] and is_die(r[POSE]) else np.nan)
            seq.append(r[O] if r[SEEN] and is_die(r[POSE]) else None)
        o0 = seq[0]
        # the first frame whose opacity is under the die pose's first sighting's by 0.03 (it falls)
        ff = next((j for j, o in enumerate(seq) if o is not None and o0 is not None and o < o0 - 0.03), None)
        if ff is not None:
            first_fall.append(ff)
        nf = 0
        for o in seq:
            if o is not None and o >= 0.97:
                nf += 1
            elif o is not None:
                break
        n_full.append(nf)
        d["seq"] = seq
    print(f"real deaths (dying, never alive again, no new track of its kind near in 1 s): {len(real)}")
    print("the opacity on frame k of the die pose (seen in a die pose), pooled: k: n, p10 / p50 / p90")
    for j in range(K + 1):
        a = np.array(byk[j], float)
        a = a[~np.isnan(a)]
        if len(a):
            print(f"  {j:2d}: {len(a):4d}  " + " / ".join(f"{v:.2f}" for v in np.percentile(a, [10, 50, 90])))
    o0 = np.array([d["seq"][0] for d in real if d["seq"][0] is not None])
    print(f"  the first die sighting's opacity: n {len(o0)}, >= 0.97 on {np.mean(o0 >= 0.97) * 100:.1f} %, p10 / p50 "
          f"{np.percentile(o0, 10):.2f} / {np.median(o0):.2f}")
    ff = np.array(first_fall)
    print(f"  the frame the opacity first falls (0.03 under the first): n {len(ff)}, p50 / p90 / max "
          f"{np.median(ff):.0f} / {np.percentile(ff, 90):.0f} / {ff.max()}; on frame 1: {np.mean(ff <= 1) * 100:.1f} %, "
          f"by frame 2: {np.mean(ff <= 2) * 100:.1f} %, by 3: {np.mean(ff <= 3) * 100:.1f} %")
    nf = np.array(n_full)
    print(f"  frames at full opacity (>= 0.97) at the start of the die pose: p50 / p90 / max {np.median(nf):.0f} / "
          f"{np.percentile(nf, 90):.0f} / {nf.max()}; 0: {np.mean(nf == 0) * 100:.1f} %, <= 1: "
          f"{np.mean(nf <= 1) * 100:.1f} %, <= 2: {np.mean(nf <= 2) * 100:.1f} %")
    # the die pose's first two seen frames: falling? (the rule's test)
    two = [(d["seq"][0], next((o for o in d["seq"][1:4] if o is not None), None)) for d in real]
    two = [(a, b) for a, b in two if a is not None and b is not None]
    fall = sum(b < a - 0.005 for a, b in two)
    rise = sum(b > a + 0.005 for a, b in two)
    print(f"  the die pose's first seen frame against the next seen one (within 3): falling {fall}, flat {len(two) - fall - rise},"
          f" rising {rise} (of {len(two)})")
    (OUT / f"deaths_{tag}.pkl").write_bytes(pickle.dumps(real))


def cmd_births(tag, K=6):
    """Faded-in births (every one, confirmed or not): the opacity over its first K seen sightings - rising (the last
    over the first by more than 0.02), flat, falling."""
    allc = load(tag)
    res, cases = Counter(), defaultdict(list)
    for cap, trs in allc.items():
        for i, s in trs.items():
            if s[0][HOW] != "faded in":
                continue
            os_ = [(r[N], r[O], r[POSE]) for r in s if r[SEEN] and r[O] is not None][:K]
            conf = any(r[ST] != "tentative" for r in s)
            if len(os_) < 2:
                c = "one sighting"
            else:
                dlt = os_[-1][1] - os_[0][1]
                c = "rising" if dlt > 0.02 else "falling" if dlt < -0.02 else "flat"
            res[(c, conf)] += 1
            cases[c].append({"cap": cap, "id": i, "n": s[0][N], "x": s[0][X], "y": s[0][Y], "conf": conf,
                             "os": [(n, round(o, 2), p) for n, o, p in os_], "frames": len(s), "kind": s[0][KIND]})
    tot = sum(res.values())
    print(f"faded-in births: {tot} (confirmed {sum(v for (c, cf), v in res.items() if cf)})")
    for c in ("rising", "flat", "falling", "one sighting"):
        print(f"  {c:12s}: {res[(c, True)] + res[(c, False)]:4d} (confirmed {res[(c, True)]})")
    for c in ("flat", "falling", "one sighting"):
        print(f"  {c}:")
        for d in cases[c][:40]:
            print(f"    {d['cap']:22s} n {d['n']:6d} id {d['id']:4d} conf {d['conf']!s:5s} frames {d['frames']:5d} "
                  f"{d['os']}")
    (OUT / f"births_{tag}.pkl").write_bytes(pickle.dumps(cases))


def strip(cap, n0, x, y, dns, label, ids=()):
    """Frames n0 + dn, each cropped around map (x, y) with that frame's camera; the point a red cross."""
    import cv2
    out = []
    for dn in dns:
        r = PS.kept_row(cap, n0 + dn)
        fr = PS.frame_of(cap, n0 + dn) if r is not None else None
        if fr is None or r["C"] is None:
            out.append(np.zeros((320, 400, 3), np.uint8))
            continue
        C = r["C"]
        qx, qy = int(round(x - C[0])), int(round(y - C[1]))
        img = fr.copy()
        cv2.drawMarker(img, (qx, qy), (0, 0, 255), cv2.MARKER_CROSS, 18, 1)
        pad = cv2.copyMakeBorder(img, 200, 200, 200, 200, cv2.BORDER_CONSTANT)
        crop = pad[qy + 200 - 120:qy + 200 + 40, qx + 200 - 100:qx + 200 + 100]
        crop = cv2.resize(crop, (400, 320), interpolation=cv2.INTER_NEAREST)
        cv2.putText(crop, f"{label} {dn:+d}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        out.append(crop)
    return np.hstack(out)


def cmd_strips(tag, what, n, seed=7):
    import cv2
    d = OUT / f"strips_{what.replace(' ', '_')}"
    d.mkdir(parents=True, exist_ok=True)
    if what.startswith("births"):
        cases = pickle.loads((OUT / f"births_{tag}.pkl").read_bytes())
        pick = [c for k in ("flat", "falling") for c in cases[k]]
        random.Random(seed).shuffle(pick)
        pick = pick[:n]
        for k, c in enumerate(pick):
            cv2.imwrite(str(d / f"{k + 1:02d}.png"), strip(c["cap"], c["n"], c["x"], c["y"], (-20, -6, 0, 6, 20),
                                                          f"{k + 1} id{c['id']}"))
            print(k + 1, c["cap"], c["n"], c["id"], c["os"])
    else:
        sp = pickle.loads((OUT / f"splits_{tag}.pkl").read_bytes())
        fol = [x for x in sp if x["new"]]
        groups = defaultdict(list)
        for x in fol:
            fading = x["how"] == "faded in" and x["age"] < FADE_L
            cl = "fading" if fading else "overlap" if x["near"] else "hit" if x["hit"] else "other"
            groups[cl].append(x)
        k = 0
        for cl, xs in groups.items():
            random.Random(seed).shuffle(xs)
            for x in xs[:n]:
                k += 1
                cv2.imwrite(str(d / f"{cl}_{k:02d}.png"), strip(x["cap"], x["n"], x["x"], x["y"],
                                                                (-12, -3, 0, 3, 12, 30), f"{cl} id{x['id']}"))
                print(cl, k, x["cap"], x["n"], x["id"], "->", [b[1] for b in x["new"]], x["pose"], x["o_prev"])
    print("->", d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["series", "splits", "deaths", "births", "strips"])
    ap.add_argument("what", nargs="?", default="splits")
    ap.add_argument("--tag", default="s4b")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--nofit", action="store_true", help="series: rows only (no opacity / pose)")
    a = ap.parse_args()
    if a.cmd == "series":
        cmd_series(a.tag, a.nofit)
    elif a.cmd == "splits":
        cmd_splits(a.tag)
    elif a.cmd == "deaths":
        cmd_deaths(a.tag)
    elif a.cmd == "births":
        cmd_births(a.tag)
    else:
        cmd_strips(a.tag, a.what, a.n)


if __name__ == "__main__":
    main()
