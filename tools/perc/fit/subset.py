"""Labels per class at 40 / 30 px, the LS fit (7744b1d) vs the vote fit, on all labelled mobs and on those NOT fading
(fading = E9 finds the mob only through a fade cell: an alpha < 255 cell of its type within 40 / 30 px with >= 16
exclusive votes, and no opaque cell with >= 16; cached in RUN/fit/fading_e9.json). The PLAN-fit-speed Session 1
comparison (HANDOFF "3.2 Session 1").

    python tools/perc/fit/subset.py [RUN]     (default runs/play/20261116_012059_1) needs RUN/fit/labels.jsonl (run.py
        labels) and RUN/fit/labels_ls.jsonl (7744b1d's fit.py + run.py via git show, --set seen_min=0.03 min_seen=60
        absent_max=0.1)
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "redesign"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "fit"))
import frames as rec  # noqa: E402
import exp_vote  # noqa: E402
import sweep  # noqa: E402


def fading_of(run: Path, lab: dict, cams: dict) -> dict:
    cache = run / "fit" / "fading_e9.json"
    if cache.exists():
        return {k: set(v) for k, v in json.loads(cache.read_text()).items()}
    map_id = rec.map_of(run)
    ref = exp_vote.Voter(map_id)
    scene, world = exp_vote.scene_world(map_id, "cuda")
    fading = {}
    for n, L in lab.items():
        name = f"{int(n):06d}.png"
        if cams.get(name) is None:
            continue
        f = torch.from_numpy(np.ascontiguousarray(rec.read(run, name)[:700])).cuda()
        exp, known = scene.expected(tuple(cams[name]))
        rows, _, _ = ref.candidates(f, exp, known & world, tmin=16)
        fl = []
        for j, m in enumerate(L["mobs"]):
            fx, fy = m["feet"]
            near = [r for r in rows if abs(r[3] - fx) <= 40 and abs(r[4] - fy) <= 30 and ref.type_g[r[2]] == m["type"]]
            if any(r[5] < 255 for r in near) and not any(r[5] == 255 for r in near):
                fl.append(j)
        fading[n] = set(fl)
    cache.write_text(json.dumps({k: sorted(v) for k, v in fading.items()}))
    return fading


def main():
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs" / "play" / "20261116_012059_1"
    lab = json.loads((run / "labels.json").read_text())["frames"]
    cams = json.loads((run / "labels" / "cams.json").read_text())
    fading = fading_of(run, lab, cams)
    sweep.R[:] = [40, 30]
    truth = {int(n): f for n, f in lab.items()}
    opaque = {n: dict(f, mobs=[m for j, m in enumerate(f["mobs"]) if j not in fading.get(str(n), set())])
              for n, f in truth.items()}
    print(f"labelled mobs {sum(len(f['mobs']) for f in truth.values())}, fading by E9 "
          f"{sum(len(v) for v in fading.values())}")
    res = {}
    for name, fn in (("LS", "labels_ls.jsonl"), ("vote", "labels.jsonl")):
        fits = sweep.load(run / "fit" / fn)
        for sub, tr in (("all", truth), ("not fading", opaque)):
            per, fp, _, wrong = sweep.score(tr, fits, (0, 0, 1), False)
            res[(name, sub)] = (per, sum(fp.values()), wrong)
    for sub in ("all", "not fading"):
        print(f"== {sub}: class, mobs, LS %, vote %")
        for k in ("all", "clear", "player", "effect", "ui", "edge", "scenery", "hit", "dying", "fade"):
            a, b = res[("LS", sub)][0].get(k), res[("vote", sub)][0].get(k)
            if a and a[0]:
                print(f"  {k:<8}{a[0]:>6}  {100 * a[1] / a[0]:6.1f}  {100 * b[1] / b[0]:6.1f}")
        print(f"  false LS {res[('LS', sub)][1]}, vote {res[('vote', sub)][1]} (on the subset a removed fading mob's "
              f"match counts as false); wrong type LS {res[('LS', sub)][2]}, vote {res[('vote', sub)][2]}")


if __name__ == "__main__":
    main()
