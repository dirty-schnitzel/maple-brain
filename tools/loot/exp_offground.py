"""E-L8b (PLAN-loot.md): sightings of ITEMS (not mesos) off the resting height - what are they? Reads
runs/loot_plan/rules_<find>.json (exp_rules.py --save). Per (run, item): the off-ground sightings' height above the
foothold, their group lengths, SEEN share; lists the longest cases with frame times (for exp_strip / exp_crop).

    python tools/loot/exp_offground.py [--find v2] [--cls other] [--item ID]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, ROOT  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--find", default="v2")
ap.add_argument("--cls", default="other")
ap.add_argument("--item", type=int, default=0)
ap.add_argument("--mesos", action="store_true")
a = ap.parse_args()
it = Items()
data = json.loads((ROOT / "runs" / "loot_plan" / f"rules_{a.find}.json").read_text(encoding="utf-8"))
by = defaultdict(list)
for x in data.get(a.cls) or []:
    s, u, ring, fs, run, item, t, box, ns, dyg, glen, fi = x
    if (item >= 9000000) != a.mesos or (a.item and item != a.item):
        continue
    if dyg is None or -7 <= dyg <= 5:
        continue
    by[(run, item)].append(x)
for (run, item), v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    dy = np.array([x[9] for x in v])
    gl = np.array([x[10] for x in v])
    sh = np.array([x[0] for x in v])
    print(f"{run} {item} {it.name(item)[:22]:22s} n {len(v):4d} | height above the foothold p5 {-np.percentile(dy, 95):.0f} p50 "
          f"{-np.median(dy):.0f} p95 {-np.percentile(dy, 5):.0f} | group length p50 {np.median(gl):.0f} max {gl.max()} | "
          f"SEEN share p50 {np.median(sh):.2f}")
    v.sort(key=lambda x: x[6])
    for x in v[:: max(1, len(v) // 6)][:6]:
        print(f"      t {x[6]:.2f} box {x[7]} dy {x[9]:.0f} seen {x[0]:.2f} unexplained {x[1]:.2f} ring {x[2]} group {x[10]}")
