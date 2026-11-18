"""Run exp_residue.py (the independent look for drops the finder does not name) over the native recordings, one
after another; log -> runs/loot_plan/residue_<find>.log. A background job of the plan session.

    python tools/loot/run_residue.py [--find v3] [--only NAME,NAME]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ["runs/play/20261116_084844_2", "runs/play/20261116_085108_3", "runs/play/20261116_085215_4",
        "runs/play/20261117_092718_1", "runs/v2/20261117_094333_1", "runs/v2/20261117_111248_1",
        "runs/play/20261116_154819_1", "runs/play/20261116_012059_1"]
ap = argparse.ArgumentParser()
ap.add_argument("--find", default="v3")
ap.add_argument("--only", default="")
a = ap.parse_args()
with open(ROOT / "runs" / "loot_plan" / f"residue_{a.find}.log", "w", encoding="utf-8") as log:
    for run in RUNS:
        if a.only and not any(x in run for x in a.only.split(",")):
            continue
        t = time.perf_counter()
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "loot" / "exp_residue.py"), run, "--find", a.find,
                            "--no-chat", "--sheet", "30"], cwd=ROOT, capture_output=True, text=True)
        log.write(f"=== {run} ({time.perf_counter() - t:.0f} s, exit {r.returncode})\n{r.stdout}\n{r.stderr[-1500:]}\n")
        log.flush()
print("done")
