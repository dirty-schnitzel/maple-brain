"""Helper (PLAN-loot.md): where on which frame is a residue patch / a drop? Prints frame names + screen boxes.

    python tools/loot/exp_where.py RUN residue MX MY [--find all]     a still patch at map (MX, MY): frames + screen x, y
"""
import json
import sys
from pathlib import Path

run, kind, mx, my = Path(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
find = sys.argv[sys.argv.index("--find") + 1] if "--find" in sys.argv else "all"
rows = [json.loads(l) for l in open(run / "loot" / f"find_{find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("cam")]
n = 0
for r in rows:
    sx, sy = mx - r["cam"][0], my - r["cam"][1]
    if 0 <= sx < 1366 and 0 <= sy < 700:
        n += 1
        if n % 40 == 1:
            print(r["frame"], f"t {r['t']:.2f} screen ({sx:.0f}, {sy:.0f})")
print(n, "frames show that map place")
