"""Run exp_find.py over every native PNG recording, one after another (plan session; a background job).

    python tools/loot/run_all.py [--out all] [--only NAME,NAME]

Dark Cave only to 16.3 s (the window was dragged after). Logs to runs/loot_plan/find_<out>.log.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = [("runs/play/20261116_154819_1", None), ("runs/play/20261116_084844_2", None),
        ("runs/play/20261116_085108_3", None), ("runs/play/20261116_085215_4", None),
        ("runs/play/20261116_084719_1", 16.3), ("runs/play/20261117_092718_1", None),
        ("runs/v2/20261117_094333_1", None), ("runs/v2/20261117_111248_1", None),
        ("runs/play/20261116_012059_1", None)]
ap = argparse.ArgumentParser()
ap.add_argument("--out", default="all")
ap.add_argument("--only", default="")
ap.add_argument("--votes", type=int, default=12)
ap.add_argument("--fit", action="store_true")
a = ap.parse_args()
logdir = ROOT / "runs" / "loot_plan"
logdir.mkdir(exist_ok=True)
with open(logdir / f"find_{a.out}.log", "w", encoding="utf-8") as log:
    for run, t1 in RUNS:
        if a.only and not any(x in run for x in a.only.split(",")):
            continue
        cmd = [sys.executable, str(ROOT / "tools" / "loot" / "exp_find.py"), run, "--out", a.out, "--cands",
               "--votes", str(a.votes)] + (["--fit"] if a.fit else [])
        if t1:
            cmd += ["--t1", str(t1)]
        t = time.perf_counter()
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        tail = "\n".join(l for l in r.stdout.splitlines() if not l.startswith("vote: mob type"))
        log.write(f"=== {run} ({time.perf_counter() - t:.0f} s, exit {r.returncode})\n{tail}\n{r.stderr[-2000:]}\n")
        log.flush()
print("done")
