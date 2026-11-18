"""E-L13 (PLAN-loot.md): spot checks behind the plan's claims, from runs/loot_plan/rules2_<find>.json
(exp_rules2.py --save): per item of interest the sightings by class and by the rule's kind, with their numbers.

    python tools/loot/exp_claims.py [--find v3] [--items 4000017,4031001] [--cls screen]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, ROOT  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--find", default="v3")
ap.add_argument("--items", default="4000017,4031001")
ap.add_argument("--cls", default="screen")
a = ap.parse_args()
it = Items()
S = json.loads((ROOT / "runs" / "loot_plan" / f"rules2_{a.find}.json").read_text(encoding="utf-8"))


def kind(o):
    if o["u"] > 0.2 or o["mob"] >= 0.5:
        return "weak"
    if o["dy"] is not None and -7 <= o["dy"] <= 5:
        return "REST"
    return "AIR" if o["ring"] is None or o["ring"] >= 0.3 else "weak"


for item in [int(x) for x in a.items.split(",") if x]:
    v = [o for o in S if o["item"] == item]
    print(f"{item} {it.name(item)}: {len(v)} loose sightings; by class x kind: "
          f"{dict(sorted(Counter((o['cls'], kind(o)) for o in v).items()))}")
    for k in ("REST", "AIR"):
        w = [o for o in v if kind(o) == k and o["cls"] not in ("rest",)]
        if not w:
            continue
        s = np.array([o["s"] for o in w])
        m = np.array([o["mob"] for o in w])
        print(f"   {k} outside the rest class: {len(w)}; SEEN p5 {np.percentile(s, 5):.2f} p50 {np.median(s):.2f}; SEEN < 0.9: "
              f"{int((s < 0.9).sum())}; mob share p95 {np.percentile(m, 95):.2f}; by run {dict(Counter(o['run'] for o in w))}")
        for o in sorted(w, key=lambda o: o["s"])[:6]:
            print(f"      {o['run']} {o['frame']} t {o['t']:.2f} box {o['box']} SEEN {o['s']:.2f} u {o['u']:.2f} mob {o['mob']:.2f} "
                  f"ring {o['ring']} dy {o['dy']}")
    m = [o for o in v if o["mob"] >= 0.5]
    print(f"   mob >= 0.5: {len(m)}" + (f" (SEEN p50 {np.median([o['s'] for o in m]):.2f}; by run {dict(Counter(o['run'] for o in m))})"
                                       if m else ""))
v = [o for o in S if o["cls"] == a.cls]
by = defaultdict(list)
for o in v:
    by[(o["run"], o["item"])].append(o)
print(f"class {a.cls}: {len(v)} sightings")
for (run, item), w in sorted(by.items(), key=lambda kv: -len(kv[1]))[:14]:
    k = Counter(kind(o) for o in w)
    print(f"   {run} {it.name(item)[:22] if item < 9000000 else 'meso'}: {len(w)}, kinds {dict(k)}, screen box {w[0]['box']}, "
          f"t {min(o['t'] for o in w):.1f}-{max(o['t'] for o in w):.1f}, frame {w[0]['frame']}")
# worn / window icons the rule keeps
for c in ("worn", "screen"):
    w = [o for o in S if o["cls"] == c and kind(o) != "weak"]
    print(f"{c}: kept by the rule {len(w)}: {[(o['run'], it.name(o['item'])[:16], o['frame'], kind(o)) for o in w[:6]]}")
