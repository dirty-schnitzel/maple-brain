"""Weak tracks (confirmed, never sighted >= 0.75 - compare.py's definition is approximated: best score < 0.75) of B
that A doesn't have at the same place: id, type, time, best score, screen place, platform.

    python tools/perc/replay/weak_new.py RUN A B
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

run, A, B = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
load = lambda n: [json.loads(l) for l in open(run / "replay" / f"{n}.jsonl", encoding="utf-8")]   # noqa: E731
ra, rb = load(A), load(B)


def weak(rows):
    best, seen = defaultdict(float), defaultdict(list)
    for i, k in enumerate(rows):
        for m in k["mobs"]:
            if m["state"] in ("live", "hit", "hidden", "dying"):
                if m["src"] != "none":
                    best[m["id"]] = max(best[m["id"]], m["score"] or 0)
                seen[m["id"]].append((i, k["t"], m))
    return {i: v for i, v in seen.items() if best[i] < 0.75}, best


wb, bb = weak(rb)
wa, _ = weak(ra)
for tid, v in wb.items():
    alone = sum(1 for i, t, m in v if not any(abs(n["sx"] - m["sx"]) <= 20 and abs(n["sy"] - m["sy"]) <= 20 and n["mob"] == m["mob"]
                                              for n in ra[i]["mobs"] if n["state"] != "offscreen"))
    m0 = v[0][2]
    print(f"{B} weak #{tid} mob {m0['mob']} t {v[0][1]:.1f}-{v[-1][1]:.1f} frames {len(v)} (not in {A}: {alone}) best {bb[tid]:.3f} "
          f"at screen {m0['sx']},{m0['sy']} platform {m0['platform']} air {m0['air']}")
print(f"{A} weak:", {tid: (v[0][2]['mob'], round(v[0][1], 1), len(v)) for tid, v in wa.items()})
