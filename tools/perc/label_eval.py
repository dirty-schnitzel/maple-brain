"""Tracker vs mobs labelled by eye (RUN/labels.json, screen feet), recall and false tracks per class.

  python tools/perc/label_eval.py RUN [--tracks replay/before.jsonl] [--list]

labels.json v2 (tools/perc/labels/label.py): {"v": 2, "frames": {n: {"mobs": [{"feet", "type", "cls"}], "unsure",
"false"}}}; v1 ({tick: {"real": [[x, y]], "missed": [[x, y]]}}) is read as mobs without type or class.
Tracks: a replay (tools/perc/replay/run.py, rows {"n", "mobs"}) or a live run's tracks.jsonl (rows {"n", "tracks"}).
A confirmed track (not tentative, on screen) matches a labelled mob within 25 px (x) / 25 px (y), each mob once,
closest first. Unmatched tracks: within 25 px of an "unsure" spot -> not counted; state dying -> corpse gone, not a
mob to fight; hidden -> unverifiable; the rest are false, by how they were seen (acq / near / coast). Recall per
class (a mob with several classes counts in each; "clear" = none) and the share found with the right type.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

CLASSES = {"clear": "", "e": "effect", "p": "player", "s": "scenery", "u": "ui", "f": "fade", "d": "dying",
           "x": "edge", "h": "hit"}


def load_labels(path: Path) -> dict:
    lab = json.loads(path.read_text(encoding="utf-8"))
    if lab.get("v") == 2:
        return {int(n): f for n, f in lab["frames"].items()}
    return {int(n): {"mobs": [{"feet": m, "type": None, "cls": ""} for m in L["real"] + L["missed"]],
                     "unsure": [], "false": []} for n, L in lab.items()}


def near(t, p, r=25):
    return abs(t["sx"] - p[0]) <= r and abs(t["sy"] - p[1]) <= r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--tracks", default="replay/before.jsonl")
    ap.add_argument("--labels", default="labels.json")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    run = Path(a.run)
    lab = load_labels(run / a.labels)
    tr = {}
    for line in open(run / a.tracks, encoding="utf-8"):
        r = json.loads(line)
        if r["n"] in lab:
            tr[r["n"]] = r.get("mobs", r.get("tracks")) or []
    lost = sorted(set(lab) - set(tr))
    n_cls, f_cls, ok_type = Counter(), Counter(), Counter()
    fp, skip, miss, wrong = Counter(), Counter(), [], []
    for n, L in sorted(lab.items()):
        if n not in tr:
            continue
        mobs = L["mobs"]
        ts = [t for t in tr[n] if t["state"] != "tentative" and -40 <= t["sx"] < 1406]
        pairs = sorted((abs(t["sx"] - m["feet"][0]) + abs(t["sy"] - m["feet"][1]), i, j) for i, t in enumerate(ts)
                       for j, m in enumerate(mobs) if near(t, m["feet"]))
        ut, um = {}, {}
        for _, i, j in pairs:
            if i not in ut and j not in um:
                ut[i], um[j] = j, i
        for j, m in enumerate(mobs):
            for c in m["cls"] or "c":
                c = "clear" if c == "c" else c
                n_cls[c] += 1
                if j in um:
                    f_cls[c] += 1
                    ok_type[c] += m["type"] is None or ts[um[j]]["mob"] == m["type"]
            if j not in um:
                miss.append((n, m))
            elif m["type"] is not None and ts[um[j]]["mob"] != m["type"]:
                wrong.append((n, m, ts[um[j]]))
        for i, t in enumerate(ts):
            if i in ut:
                continue
            if any(near(t, u) for u in L["unsure"]):
                skip["unsure"] += 1
            elif t["state"] in ("dying", "hidden"):
                skip[t["state"]] += 1
            else:
                kind = "coast" if t["src"] == "none" else t["src"]
                fp[kind] += 1
                if a.list:
                    print(f"  false n{n} {kind} {t['state']} {t['mob']} {t['anim']} {t['score']} at {t['sx']},{t['sy']}")
    tot, found = sum(len(lab[n]["mobs"]) for n in tr), sum(len(lab[n]["mobs"]) for n in tr) - len(miss)
    fight = [m for n in tr for m in lab[n]["mobs"] if "d" not in m["cls"]]
    fmiss = sum(1 for _, m in miss if "d" not in m["cls"])
    nf = sum(fp.values())
    print(f"{len(tr)} labelled frames ({a.tracks}{'; no tracks for ' + str(len(lost)) if lost else ''}): "
          f"mobs {tot}, found {found} = {100 * found / max(tot, 1):.1f} % (not dying: "
          f"{100 * (len(fight) - fmiss) / max(len(fight), 1):.1f} % of {len(fight)}), wrong type {len(wrong)}")
    print(f"false tracks {nf} = {100 * nf / max(found + nf, 1):.1f} % of matched + false ({dict(fp)}); "
          f"not counted: {dict(skip)}")
    print(f"{'class':<8}{'mobs':>6}{'found':>7}{'recall':>8}{'type ok':>9}")
    for c in sorted(n_cls, key=lambda c: -n_cls[c]):
        print(f"{CLASSES[c] or 'clear':<8}{n_cls[c]:>6}{f_cls[c]:>7}{100 * f_cls[c] / n_cls[c]:>7.1f}%"
              f"{100 * ok_type[c] / max(f_cls[c], 1):>8.1f}%")
    if a.list:
        for n, m in miss:
            print(f"  missed n{n} {m['type']} {m['cls'] or '-'} at {m['feet']}")
        for n, m, t in wrong:
            print(f"  type n{n} label {m['type']} track {t['mob']} at {m['feet']}")


if __name__ == "__main__":
    main()
