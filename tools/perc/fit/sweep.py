"""Fit the fit's acceptance rule (seen_min, min_seen, absent_max) on a --loose run (tools/perc/fit/run.py), and score
any run against its truth.

    python tools/perc/fit/sweep.py synth OUT [--fit fit/synth_loose.jsonl]      grid on the synthetic set
    python tools/perc/fit/sweep.py labels RUN [--fit fit/labels_loose.jsonl]    the same rule on the labels
    python tools/perc/fit/sweep.py score OUT|RUN --fit FILE [--labels synth.json] [--list]
    python tools/perc/fit/sweep.py ghosts RUN --fit fit/ghosts.jsonl           fit mobs at the weak tracks' spots

Matching = label_eval's: a fit mob within 25 px (x and y) of a labelled mob's feet, each once, closest first.
Unmatched fit mobs: at an "unsure" spot / in a "dontcare" box (synthetic: our blob, the UI of the base frame) not
counted; the rest are FALSE (die poses listed apart: a corpse the labels may not hold). A loose run's mobs filtered
by a stricter rule approximate a run with that rule (a rejected mob would have left its pixels to others): the chosen
rule is re-run for the reported numbers.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

CLS = {"": "clear", "e": "effect", "p": "player", "s": "scenery", "u": "ui", "f": "fade", "d": "dying", "x": "edge",
       "h": "hit"}


R = [25, 25]                     # match radius x / y (--r X Y)


def near(a, b):
    return abs(a[0] - b[0]) <= R[0] and abs(a[1] - b[1]) <= R[1]


def load(path):
    return {json.loads(line)["n"]: json.loads(line) for line in open(path, encoding="utf-8")}


def keep(m, rule):
    f = m["fit"]
    return f["seen"] >= rule[0] and f["n_seen"] >= rule[1] and f["absent"] <= rule[2]


def score(truth, fits, rule, synth, listing=False):
    """-> (per-key [mobs, found], false Counter, false list, wrong type)"""
    per, fp, fl, wrong = defaultdict(lambda: [0, 0]), Counter(), [], 0
    for n, L in truth.items():
        if n not in fits:
            continue
        ms = [m for m in fits[n]["mobs"] if keep(m, rule)]
        mobs = L["mobs"]
        pairs = sorted((abs(t["sx"] - m["feet"][0]) + abs(t["sy"] - m["feet"][1]), i, j)
                       for i, t in enumerate(ms) for j, m in enumerate(mobs) if near((t["sx"], t["sy"]), m["feet"]))
        ut, um = {}, {}
        for _, i, j in pairs:
            if i not in ut and j not in um:
                ut[i], um[j] = j, i
        for j, m in enumerate(mobs):
            keys = ["all"] + [CLS[c] for c in (m["cls"] or "")] + ([] if m["cls"] else ["clear"])
            if synth:
                keys.append("case:" + L["case"])
            for k in keys:
                per[k][0] += 1
                per[k][1] += j in um
            if j in um and ms[um[j]]["mob"] != m["type"]:
                wrong += 1
            if listing and j not in um:
                print(f"  missed n{n} {m['type']} {m['cls'] or '-'} {m.get('pose', '')} at {m['feet']} vis {m.get('vis')}")
        for i, t in enumerate(ms):
            if i in ut:
                continue
            p = (t["sx"], t["sy"])
            if any(near(p, u) for u in L.get("unsure") or []):
                continue
            # dontcare = what the synthetic base could not erase (our blob, the UI rects): a mob there, or with
            # its body there (feet up to 80 px below), may be a real one of the base frame (e.g. a Zombie's cap
            # above the chat bar, its feet under the HUD)
            if synth and any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] + 80 for b in L.get("dontcare") or []):
                continue
            kind = "die" if t["anim"].startswith("die") else "live"
            fp[kind] += 1
            if synth and L.get("case") == "free":
                fp["free"] += 1
            fl.append((n, t))
            if listing:
                f = t["fit"]
                print(f"  false n{n} {kind} {t['mob']} {t['anim']} {f['facing']} at {p} seen {f['seen']} ({f['n_seen']} px) "
                      f"absent {f['absent']} o {f['opacity']}")
    return per, fp, fl, wrong


def truth_of(path: Path, labels: str):
    lab = json.loads((path / labels).read_text())
    return {int(n): f for n, f in lab["frames"].items()}


def grid(truth, fits, synth):
    rows = []
    for s in (0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.25, 0.3):
        for px in (10, 30, 60, 100, 150, 200, 300):
            for ab in (0.02, 0.05, 0.1, 0.15, 0.2, 0.3):
                per, fp, _, wrong = score(truth, fits, (s, px, ab), synth)
                cases = {k: v[1] / v[0] for k, v in per.items() if k.startswith("case:") or not synth}
                worst = min(cases.values()) if cases else 0
                rows.append(((s, px, ab), per["all"][1] / max(per["all"][0], 1), worst, sum(fp.values()), fp, wrong))
    return rows


def show(per, fp, wrong, synth):
    a = per["all"]
    print(f"mobs {a[0]}, found {a[1]} = {100 * a[1] / max(a[0], 1):.1f} %, wrong type {wrong}, false {sum(fp.values())} "
          f"{dict(fp)}")
    for k in sorted(per, key=lambda k: (not k.startswith("case:"), -per[k][0])):
        if k != "all":
            v = per[k]
            print(f"  {k:<14}{v[0]:>6}{v[1]:>6}{100 * v[1] / v[0]:>7.1f} %")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("synth", "labels", "score", "ghosts"))
    ap.add_argument("path")
    ap.add_argument("--fit")
    ap.add_argument("--labels")
    ap.add_argument("--rule", nargs=3, type=float, help="seen_min min_seen absent_max (score mode: filter)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--r", nargs=2, type=int, help="match radius x y (default 25 25 = label_eval's)")
    a = ap.parse_args()
    if a.r:
        R[:] = a.r
    path = Path(a.path)
    if a.mode == "ghosts":
        fits = load(path / (a.fit or "fit/ghosts.jsonl"))
        rule = tuple(a.rule) if a.rule else (0, 0, 1)
        spots = bad = 0
        kinds = Counter()
        for n, r in sorted(fits.items()):
            for s in r["spots"]:
                spots += 1
                hit = [m for m in r["mobs"] if keep(m, rule) and near((m["sx"], m["sy"]), s[1:])]
                if hit:
                    bad += 1
                    kinds[(s[0], hit[0]["mob"])] += 1
                    if a.list:
                        f = hit[0]["fit"]
                        print(f"  n{n} weak {s} -> fit {hit[0]['mob']} {hit[0]['anim']} at {hit[0]['sx']},{hit[0]['sy']} "
                              f"seen {f['seen']} ({f['n_seen']} px) absent {f['absent']}")
        print(f"{len(fits)} frames, {spots} weak-track sightings: a fit mob within 25 px at {bad} "
              f"(weak type, fit type: {dict(kinds)})")
        return
    synth = a.mode == "synth" or (path / "synth.json").exists()
    truth = truth_of(path, a.labels or ("synth.json" if synth else "labels.json"))
    fits = load(path / (a.fit or f"fit/{'synth' if a.mode == 'score' and synth else a.mode}_loose.jsonl"))
    if a.mode == "score":
        per, fp, _, wrong = score(truth, fits, tuple(a.rule) if a.rule else (0, 0, 1), synth, a.list)
        show(per, fp, wrong, synth)
        return
    rows = grid(truth, fits, synth)
    print("rule (seen_min, min_seen, absent_max): recall all, worst case, false")
    zero = [r for r in rows if r[3] == 0]
    for r in sorted(zero, key=lambda r: (-r[2], -r[1]))[:12]:
        print(f"  {r[0]}  {100 * r[1]:.2f} %  worst {100 * r[2]:.2f} %  false 0")
    print("best recall with any false:")
    for r in sorted(rows, key=lambda r: (-r[2], r[3]))[:8]:
        print(f"  {r[0]}  {100 * r[1]:.2f} %  worst {100 * r[2]:.2f} %  false {r[3]} {dict(r[4])}")


if __name__ == "__main__":
    main()
