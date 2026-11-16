"""Where do two replays' tracks differ? Per real track-frame of A (live / hit / hidden / dying, confirmed): found in B
(same mob type, screen feet within 20 px), found with ANOTHER mob type, or not at all - split by sighted / coasting.

    python tools/perc/replay/diff_kinds.py RUN A B
"""
import json
import sys
from collections import Counter
from pathlib import Path

run, A, B = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
load = lambda n: [json.loads(l) for l in open(run / "replay" / f"{n}.jsonl", encoding="utf-8")]   # noqa: E731
ra, rb = load(A), load(B)
for x, y, nx, ny in ((ra, rb, A, B), (rb, ra, B, A)):
    c = Counter()
    for ka, kb in zip(x, y):
        for m in ka["mobs"]:
            if m["state"] not in ("live", "hit", "hidden", "dying"):
                continue
            kind = "sighted" if m["src"] != "none" else "coasting"
            near = [n for n in kb["mobs"] if n["state"] != "offscreen" and abs(n["sx"] - m["sx"]) <= 20 and abs(n["sy"] - m["sy"]) <= 20]
            res = "same" if any(n["mob"] == m["mob"] for n in near) else ("other type" if near else "none")
            c[(kind, res)] += 1
    tot = {k: sum(v for (kk, _), v in c.items() if kk == k) for k in ("sighted", "coasting")}
    print(f"{nx} in {ny}: " + "; ".join(f"{k} {tot[k]}: " + ", ".join(f"{r} {100 * c[(k, r)] / max(1, tot[k]):.1f} %"
                                                                   for r in ("same", "other type", "none")) for k in tot))
