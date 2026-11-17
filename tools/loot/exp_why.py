"""Helper (PLAN-loot.md): why was a drop not sighted? For RUN at time T: every candidate and drop of the find file
(optionally of one item), with its numbers.

    python tools/loot/exp_why.py RUN T [--find v3] [--item ID] [--near X Y]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("t", type=float)
ap.add_argument("--find", default="v3")
ap.add_argument("--item", type=int, default=0)
ap.add_argument("--near", type=int, nargs=2, default=None)
a = ap.parse_args()
it = Items()
rows = [json.loads(l) for l in open(Path(a.run) / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
r = min((r for r in rows if r.get("drops") is not None), key=lambda r: abs(r["t"] - a.t))
print(r["frame"], "t", round(r["t"], 2), "cam", r["cam"], "ms", r.get("ms"))
got = {(d["item"], d["f"], tuple(d["box"])) for d in r["drops"]}
for c in sorted(r.get("cands") or r["drops"], key=lambda c: -c["n_seen"]):
    if a.item and c["item"] != a.item:
        continue
    if a.near and (abs(c["box"][0] - a.near[0]) > 60 or abs(c["box"][1] - a.near[1]) > 60):
        continue
    tag = "DROP" if (c["item"], c["f"], tuple(c["box"])) in got else "    "
    print(f"  {tag} {c['item']} {it.name(c['item'])[:18]:18s} box {c['box']} seen {c['n_seen']}/{c['n_op']} abs {c['n_abs']} "
          f"votes {c['votes']} cd {c.get('n_cd')} mob {c.get('n_mob')} ring {c.get('ring_e2')}/{c.get('ring_n2')}")
