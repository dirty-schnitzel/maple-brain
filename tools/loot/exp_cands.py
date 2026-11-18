"""E-L2c (PLAN-loot.md): the finder's candidates - how sharp is the vote + check? Per find file: candidates a frame,
their SEEN share split by accepted / rejected, the rejected ones' best shares (what a threshold must hold off), votes.

    python tools/loot/exp_cands.py RUN [--find NAME]      (the find file must have been written with --cands)
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--find", default="all")
a = ap.parse_args()
it = Items()
rows = [json.loads(l) for l in open(Path(a.run) / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("cands") is not None]
nc = np.array([len(r["cands"]) for r in rows])
print(f"{len(rows)} frames; candidates a frame p50 {np.median(nc):.0f} p90 {np.percentile(nc, 90):.0f} max {nc.max()}")
acc = {(d["item"], d["f"], tuple(d["box"])) for r in rows for d in r["drops"]}
sh_a, sh_r, v_a, v_r, rej = [], [], [], [], Counter()
hist = np.zeros(11, int)
for r in rows:
    got = {(d["item"], d["f"], tuple(d["box"])) for d in r["drops"]}
    for c in r["cands"]:
        s = c["n_seen"] / max(1, c["n_op"])
        if (c["item"], c["f"], tuple(c["box"])) in got:
            sh_a.append(s)
            v_a.append(c["votes"])
        else:
            sh_r.append(s)
            v_r.append(c["votes"])
            hist[min(10, int(s * 10))] += 1
            if s >= 0.25:
                rej[c["item"]] += 1
sh_a, sh_r = np.array(sh_a), np.array(sh_r)
print(f"accepted {len(sh_a)}: seen share p1 {np.percentile(sh_a, 1):.2f} p10 {np.percentile(sh_a, 10):.2f} p50 "
      f"{np.median(sh_a):.2f}; votes p1 {np.percentile(v_a, 1):.0f} p10 {np.percentile(v_a, 10):.0f} p50 {np.median(v_a):.0f}")
if len(sh_r):
    print(f"rejected {len(sh_r)}: seen share p50 {np.median(sh_r):.2f} p90 {np.percentile(sh_r, 90):.2f} p99 "
          f"{np.percentile(sh_r, 99):.2f} max {sh_r.max():.2f}; votes p50 {np.median(v_r):.0f} p99 {np.percentile(v_r, 99):.0f}")
    print("rejected by seen share 0.0-0.1 .. 1.0:", hist.tolist())
    print("rejected with share >= 0.25 (taken pixels / absent rule):",
          [(i, it.name(i)[:20], n) for i, n in rej.most_common(12)])
lo = [(c["n_seen"] / c["n_op"], c["item"], c["n_seen"], c["n_op"], c["n_abs"], c["votes"], r["t"])
      for r in rows for c in r["cands"] if (c["item"], c["f"], tuple(c["box"])) in
      {(d["item"], d["f"], tuple(d["box"])) for d in r["drops"]}]
lo.sort()
print("accepted, lowest seen share:")
for s, i, ns, no, na, v, t in lo[:15]:
    print(f"   {s:.2f} {i} {it.name(i)[:24]:24s} seen {ns}/{no} absent {na} votes {v} t {t:.1f}")
