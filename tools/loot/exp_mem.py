"""E-L7d (PLAN-loot.md): GPU memory and build time of the drop finder prototype (dropgraph.GraphFinder).

    python tools/loot/exp_mem.py [--maxp 8] [--nf 49152]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lootlib  # noqa: E402,F401  (puts the repo on sys.path)
import torch  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--maxp", type=int, default=8)
ap.add_argument("--nf", type=int, default=49152)
a = ap.parse_args()
torch.zeros(1, device="cuda")
torch.cuda.synchronize()
m0 = torch.cuda.memory_allocated()
t = time.perf_counter()
from dropgraph import GraphFinder  # noqa: E402

fz = GraphFinder(NF=a.nf, MAXP=a.maxp)
t1 = time.perf_counter()
fz.prepare(side_stream=True)
torch.cuda.synchronize()
t2 = time.perf_counter()
v = fz.voter
mb = lambda x: x.numel() * x.element_size() / 1e6  # noqa: E731
print(f"build {t1 - t:.2f} s (the voter {fz.build_s:.2f}), graph capture {t2 - t1:.2f} s; GPU memory allocated "
      f"{(torch.cuda.memory_allocated() - m0) / 1e6:.0f} MB (peak {torch.cuda.max_memory_allocated() / 1e6:.0f})")
print(f"   LUT {mb(v.lut):.0f} MB, fade LUTs {mb(v.lut_tol):.0f} MB (not needed for drops), pair table {mb(v.pair_ok):.0f} MB (not "
      f"needed), vote table {mb(v.uk) + mb(v.start) + mb(v.count) + mb(v.off):.0f} MB, graph table {mb(fz.g_uk) + mb(fz.g_places):.0f} "
      f"MB, pictures {mb(fz.pics) + mb(fz.col) + mb(fz.op) + mb(fz.dr) + mb(fz.fm) + mb(fz.inbox):.0f} MB")
