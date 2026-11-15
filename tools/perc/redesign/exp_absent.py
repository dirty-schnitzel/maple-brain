"""E5: 3-valued evidence at a track's predicted body box, from the known scenery: is the scenery visible there
(= nothing stands there: ABSENT), or is something drawn over it (mob or effect: no absence evidence)?"""
import sys
import numpy as np
sys.argv = sys.argv[:1]
import exp_bg as E

BODY = {19: ([-27, -52], [29, 0]), 21: ([-27, -58], [36, 0])}


def absent_share(r):
    f = E.frame_of(r)
    reg = E.register(r["run"], r["frame"], f)
    if reg is None:
        return None
    B, op, _ = reg
    lt, rb = BODY[r["mob"]]
    x0, y0, x1, y1 = int(r["sx"] + lt[0]), int(r["sy"] + lt[1]), int(r["sx"] + rb[0]), int(r["sy"] + rb[1])
    if x0 < 0 or y0 < 0 or x1 > 1366 or y1 > 700:
        return None
    known = op[y0:y1, x0:x1]
    if known.mean() < 0.3:
        return None
    same = (np.abs(f[y0:y1, x0:x1].astype(np.int16) - B[y0:y1, x0:x1].astype(np.int16)).max(2) <= 30) & known
    return float(same.sum() / known.sum())


sets = {"REAL seen (ncc >= 0.85)": [r for r in E.rows if r["set"] == "REAL" and r["ncc"] >= 0.85][:300],
        "LOST_ALIVE (covered, alive)": [r for r in E.rows if r["set"] == "LOST_ALIVE"],
        "LOST_ENDED (unseen, never came back)": [r for r in E.rows if r["set"] == "LOST_ENDED"],
        "NEG (empty platform spots)": [r for r in E.rows if r["set"] == "NEG"][:400]}
print("share of the KNOWN scenery pixels inside the predicted body box that show the scenery itself")
for name, sel in sets.items():
    v = [a for a in (absent_share(r) for r in sel) if a is not None]
    print(f"  {name:38s} n {len(v):3d}  p5..p95 {E.pct(v)}   >= 0.6 (ABSENT): {sum(a >= 0.6 for a in v) / max(1, len(v)):.0%}"
          f"   <= 0.3: {sum(a <= 0.3 for a in v) / max(1, len(v)):.0%}")
