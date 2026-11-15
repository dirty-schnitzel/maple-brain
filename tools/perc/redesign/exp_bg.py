"""E3: with the scenery known (render from the client), is a detection 'explained by scenery'?  And E4: are the mobs
'lost' next to us really covered, or just somewhere else (knocked back past the tracker's window)?
Uses exp_score.json (cases + scores) and ant4_render.png.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(r"C:\Users\Yoav\dev\maple-work")
sys.path.insert(0, str(ROOT))
from maplebrain.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402

HERE = Path(__file__).parent
RUNS = {"fix3": "runs/v2/air1/fix3", "press1": "runs/v2/press1", "011503": "runs/v2/20261109_011503_1",
        "air1": "runs/v2/air1/20261109_014902_1"}
R = cv2.imread(str(HERE / "ant4_render.png"), cv2.IMREAD_UNCHANGED)
META = json.loads((HERE / "ant4_render.json").read_text())
g = GpuSpriteDetector.for_map(10005063, ROOT / "assets" / "mcw", min_score=0.4)
rows = json.loads((HERE / "exp_score.json").read_text())
cams = {}
for run, p in RUNS.items():
    for l in open(ROOT / p / "ticks.jsonl", encoding="utf-8"):
        l = json.loads(l)
        if l.get("frame") and l["obs"].get("cam"):
            cams[(run, l["frame"])] = (l["obs"]["cam"], l["obs"].get("me"))
_reg = {}


def register(run, frame, f):
    """The scenery render as seen in this frame: (bgr, opaque) 700 x 1366, registered within +-24 px of the logged
    camera on the whole play area's scenery."""
    key = (run, frame)
    if key in _reg:
        return _reg[key]
    (cx, cy), _ = cams[key]
    ax, ay = int(round(cx)) - META["x0"], int(round(cy)) - META["y0"]
    S = 24
    fy0, fy1, fx0, fx1 = 200, 580, 320, 1100
    rt = np.ascontiguousarray(R[ay + fy0:ay + fy1, ax + fx0:ax + fx1])
    out = None
    if rt.shape[:2] == (fy1 - fy0, fx1 - fx0) and (rt[..., 3] > 200).mean() > 0.15:
        mask = np.repeat((rt[..., 3:4] > 200).astype(np.uint8) * 255, 3, 2)
        area = np.ascontiguousarray(f[fy0 - S:fy1 + S, fx0 - S:fx1 + S])
        r = np.nan_to_num(cv2.matchTemplate(area, np.ascontiguousarray(rt[..., :3]), cv2.TM_CCORR_NORMED, mask=mask),
                          nan=-1, posinf=-1, neginf=-1)
        _, sc, _, (lx, ly) = cv2.minMaxLoc(r)
        dx, dy = lx - S, ly - S
        rr = R[ay - dy:ay - dy + 700, ax - dx:ax - dx + 1366]
        if rr.shape[:2] == (700, 1366) and sc > 0.7:
            out = (rr[..., :3], rr[..., 3] > 200, (dx, dy, sc))
    if len(_reg) > 300:
        _reg.clear()
    _reg[key] = out
    return out


def frame_of(r):
    return cv2.imread(str(ROOT / RUNS[r["run"]] / "frames" / r["frame"]))


def scenery_stats(r, f):
    """At today's best match for this case: share of the template's pixels whose scenery is known, and of those the
    share the frame shows the scenery itself (within 30 levels) = nothing is drawn there."""
    reg = register(r["run"], r["frame"], f)
    if reg is None:
        return None
    B, op, _ = reg
    h = g.find_near(f, [((r["mob"],), r["sx"], r["sy"])], pad=24, min_score=-1)[0]
    x, y, w, hh = h.box
    if x < 0 or y < 0 or x + w > 1366 or y + hh > 700:
        return None
    k = next(i for i, it in enumerate(g.near_items) if it[3] is h.pose and it[0] == h.mob_id)
    _, t, m, _ = g.near_items[k]
    m = m > 0
    known = op[y:y + hh, x:x + w] & m
    if m.sum() == 0:
        return None
    X = f[y:y + hh, x:x + w].astype(np.int16)
    Bw = B[y:y + hh, x:x + w].astype(np.int16)
    same = (np.abs(X - Bw).max(2) <= 30) & known
    # opacity of the template over the known scenery: X = a T + (1 - a) B
    tb = (t.astype(np.float32) - Bw)[known]
    xb = (X - Bw).astype(np.float32)[known]
    den = float((tb * tb).sum())
    a = float((xb * tb).sum() / den) if den > 1e3 else None
    return {"known": float(known.sum() / m.sum()), "scenery": float(same.sum() / max(1, known.sum())), "alpha": a,
            "ncc": h.score}


def pct(v, ps=(5, 25, 50, 75, 95)):
    return " ".join(f"{x:.2f}" for x in np.percentile(v, ps)) if len(v) else "-"


def e3():
    sets = {
        "REAL strong (ncc >= 0.85)": [r for r in rows if r["set"] == "REAL" and r["ncc"] >= 0.85],
        "GHOST weak (doc. false tracks, ncc < 0.75)": [r for r in rows if r["set"] == "GHOST" and r["ncc"] < 0.75],
        "NEG (random platform spots, best match there)": [r for r in rows if r["set"] == "NEG"][:300],
    }
    print("E3: scenery under today's best match (known = scenery rendered there; scenery = frame shows that scenery)")
    for name, sel in sets.items():
        st = [s for s in (scenery_stats(r, frame_of(r)) for r in sel[:250]) if s is not None]
        kn = [s for s in st if s["known"] >= 0.3]
        print(f"  {name}: n {len(st)}, with >= 30 % of the body over known scenery: {len(kn)}")
        print(f"     known share p5..p95        {pct([s['known'] for s in st])}")
        print(f"     scenery-visible share      {pct([s['scenery'] for s in kn])}")
        print(f"     opacity a (X = aT+(1-a)B)  {pct([s['alpha'] for s in kn if s['alpha'] is not None])}")
        for thr in (0.5, 0.6):
            print(f"     'explained by scenery' (>= {thr} of the known pixels are scenery): "
                  f"{sum(s['scenery'] >= thr for s in kn)} of {len(kn)}")


def e4():
    la = [r for r in rows if r["set"] == "LOST_ALIVE"]
    c = Counter()
    dist = []
    for r in la:
        f = frame_of(r)
        hits = [h for h in g.find(f) if h.mob_id == r["mob"] and h.score >= 0.75]
        d = [(abs(h.feet[0] - r["sx"]), abs(h.feet[1] - r["sy"]), h) for h in hits]
        near = [x for x in d if x[0] <= 24 and x[1] <= 24]
        mid = [x for x in d if x[0] <= 130 and x[1] <= 40 and x not in near]
        if near:
            c["a strong hit inside the tracker's window (+-24 px)"] += 1
        elif mid:
            c["a strong hit 25-130 px away on the same level (tracker looked in the wrong place)"] += 1
            dist.append(min(x[0] for x in mid))
        else:
            c["no strong hit within 130 px (covered / in another pose)"] += 1
    print(f"\nE4: {len(la)} moments a proven, alive mob next to us was 'unseen' (re-seen >= 0.8 within 1.5 s)")
    for k, v in c.most_common():
        print(f"   {v:4d} ({v / len(la):.0%})  {k}")
    if dist:
        print("   distance of those hits from the prediction, px p10/p50/p90:", np.percentile(dist, [10, 50, 90]).round(0))


if __name__ == "__main__":
    e3()
    e4()
