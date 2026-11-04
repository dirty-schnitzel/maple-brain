"""Tracker vs mobs labelled by eye (RUN/labels.json: {tick: {"real": [[x, y]], "missed": [[x, y]]}}, screen feet).

  python tools/perc/label_eval.py RUN [--tracks tracks.jsonl] [--list]

A confirmed track (not tentative, on screen) matches a labelled mob within 25 px (x) / 25 px (y), each mob once.
Reports recall, false tracks by how they were seen (acq / near / coasting / hidden), and the misses.
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--tracks", default="tracks.jsonl")
    ap.add_argument("--labels", default="labels.json")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    run = Path(a.run)
    lab = json.loads((run / a.labels).read_text(encoding="utf-8"))
    tr = {r["n"]: r for r in map(json.loads, open(run / a.tracks, encoding="utf-8"))}
    real = tp = dying = hidden = 0
    fp, miss = Counter(), []
    for n, L in lab.items():
        mobs = [tuple(m) for m in L["real"] + L["missed"]]
        real += len(mobs)
        ts = [t for t in tr[int(n)]["tracks"] if t["state"] != "tentative" and 0 <= t["sx"] < 1366]
        pairs = sorted((abs(t["sx"] - m[0]) + abs(t["sy"] - m[1]), i, j) for i, t in enumerate(ts)
                       for j, m in enumerate(mobs) if abs(t["sx"] - m[0]) <= 25 and abs(t["sy"] - m[1]) <= 25)
        ut, um = set(), set()
        for _, i, j in pairs:
            if i not in ut and j not in um:
                ut.add(i)
                um.add(j)
        tp += len(um)
        for i, t in enumerate(ts):
            if i not in ut:
                if t["state"] == "dying":
                    dying += 1                                  # known dead, corpse gone: not a mob to fight
                    continue
                if t["state"] == "hidden":
                    hidden += 1                                 # behind cover / a player: can't be checked by eye
                    continue
                kind = "coast" if t["src"] == "none" else t["src"]
                fp[kind] += 1
                if a.list:
                    print(f"  false n{n} {kind} {t['anim']} {t['score']} at {t['sx']},{t['sy']} vis {t.get('vis')}")
        miss += [(int(n), mobs[j]) for j in range(len(mobs)) if j not in um]
    nf = sum(fp.values())
    print(f"labelled mobs {real} in {len(lab)} frames: found {tp} = {100 * tp / max(real, 1):.1f} %, "
          f"false {nf} = {100 * nf / max(tp + nf, 1):.1f} % ({dict(fp)}); dying, nothing to see: {dying}; hidden (unverifiable): {hidden}")
    if a.list:
        for n, m in miss:
            print(f"  missed n{n} at {m}")


if __name__ == "__main__":
    main()
