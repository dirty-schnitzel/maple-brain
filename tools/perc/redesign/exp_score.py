"""E1: does an absolute-colour, occlusion-tolerant score separate real mobs from ghosts better than NCC?
Sets (from recorded runs with frames + ticks, Ant Tunnel IV):
  REAL       sightings (src != none) of tracks whose lifetime peak >= 0.9
  LOST_ALIVE unseen moments (src none) of such tracks that were re-seen >= 0.8 within 1.5 s (alive, hidden by effects)
  GHOST      sightings of the documented false tracks (HANDOFF)
  NEG        random platform spots far from every track and from us
Per case: best over (pose of that mob type, +-P px) of: ncc (today's find_near), inl_T (share of the template's
pixels within T grey levels of the frame, all 3 channels), eff_T (same, pixels where the frame is brighter than the
template by > D in every channel don't count: bright effects drawn over the mob).
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(r"C:\Users\Yoav\dev\maple-work")
sys.path.insert(0, str(ROOT))
from maplebrain.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402
from maplebrain.nav.navmap import NavMap  # noqa: E402
from maplebrain.config import Config  # noqa: E402

MAP = 10005063
RUNS = {
    "fix3": ("runs/v2/air1/fix3", {154: (108.1, 1e9)}, 168.0),
    "press1": ("runs/v2/press1", {41: (0, 1e9), 148: (0, 1e9), 222: (0, 1e9)}, 1e9),
    "011503": ("runs/v2/20261109_011503_1", {89: (56.5, 63.5), 23: (0, 1e9), 35: (0, 1e9), 37: (0, 1e9)}, 1e9),
    "air1": ("runs/v2/air1/20261109_014902_1", {72: (47.0, 1e9), 22: (0, 1e9), 25: (0, 1e9), 33: (0, 1e9),
                                                 53: (0, 1e9)}, 1e9),
}
TAUS = (16, 24, 32, 48)
D = 40
P = 24
PY = 12
dev = "cuda"


def load(run):
    path, ghosts, tmax = RUNS[run]
    L = [json.loads(l) for l in open(ROOT / path / "ticks.jsonl", encoding="utf-8")]
    L = [l for l in L if l["obs"]["t"] < tmax]
    peak, sight = defaultdict(float), defaultdict(list)
    for l in L:
        for m in l["obs"].get("mobs", []):
            if m["src"] != "none":
                peak[m["id"]] = max(peak[m["id"]], m.get("score") or 0)
                sight[m["id"]].append((l["obs"]["t"], m.get("score") or 0))
    return path, ghosts, L, peak, sight


def cases(run, nav, rng):
    path, ghosts, L, peak, sight = load(run)
    out = defaultdict(list)
    for l in L:
        o = l["obs"]
        if not l.get("frame") or not o.get("cam"):
            continue
        t, cam, me = o["t"], o["cam"], o.get("me")
        for m in o.get("mobs", []):
            if m["kind"] != "mob" or not (30 < m["sx"] < 1336 and 80 < m["sy"] < 600):
                continue
            c = (run, path, l["frame"], t, m["id"], m["mob"], m["sx"], m["sy"], m.get("score"), m["state"])
            g = ghosts.get(m["id"])
            if g is not None and g[0] <= t <= g[1]:
                if m["src"] != "none":
                    out["GHOST"].append(c)
                continue
            if peak[m["id"]] >= 0.9 and m["state"] in ("live", "hit", "hidden"):
                if m["src"] != "none":
                    out["REAL"].append(c)
                elif me and abs(m["sx"] - me[0]) <= 170 and 0.05 < (m.get("unseen") or 0) <= 1.0:
                    again = any(t < ts <= t + 1.5 and sc >= 0.8 for ts, sc in sight[m["id"]])
                    out["LOST_ALIVE" if again else "LOST_ENDED"].append(c)
        # negatives: platform spots in view, far from tracks and us
        for _ in range(2):
            p = rng.choice(list(nav.platforms.values()))
            x = rng.uniform(p.left, p.right)
            y = p.y_at(x)
            if y is None:
                continue
            sx, sy = x - cam[0], y - cam[1]
            if not (60 < sx < 1300 and 120 < sy < 590):
                continue
            if sx < 300 and sy < 260:
                continue
            if any(abs(m["sx"] - sx) < 110 and abs(m["sy"] - sy) < 90 for m in o.get("mobs", [])):
                continue
            if me and abs(me[0] - sx) < 110 and abs(me[1] - sy) < 110:
                continue
            out["NEG"].append((run, path, l["frame"], t, -1, rng.choice([19, 21]), sx, sy, None, "neg"))
    return out


class Scorer:
    def __init__(self):
        self.g = GpuSpriteDetector.for_map(MAP, ROOT / "assets" / "mcw", min_score=0.4)
        self.bank = {}
        for mid, ks in self.g.near_by_mob.items():
            items = []
            for k in ks:
                _, t, m, pose = self.g.near_items[k]
                T = torch.from_numpy(t.astype(np.float32)).to(dev).permute(2, 0, 1)      # (3, h, w)
                M = torch.from_numpy(m.astype(np.float32)).to(dev)
                items.append((T, M, pose))
            self.bank[mid] = items

    def score(self, frame, mob, sx, sy):
        g = self.g
        res = {}
        h = g.find_near(frame, [((mob,), sx, sy)], pad=P, min_score=-1.0)[0]
        res["ncc"] = h.score if h is not None else -1.0
        h2 = g.find_near(frame, [((mob,), sx, sy)], pad=P, min_score=-1.0, vis=[None])[0]
        res["ncc_vis"] = h2.score if h2 is not None else -1.0
        X = torch.from_numpy(frame[:700].astype(np.float32)).to(dev).permute(2, 0, 1)   # (3, 700, 1366)
        pad = 140
        Xp = torch.nn.functional.pad(X, (pad, pad, pad, pad), value=-1000.0)
        best = defaultdict(lambda: -1.0)
        for T, M, pose in self.bank[mob]:
            hh, ww = M.shape
            x0, y0 = int(sx) - pose.ox - P + pad, int(sy) - pose.oy - PY + pad
            reg = Xp[:, y0:y0 + hh + 2 * PY, x0:x0 + ww + 2 * P]
            wins = reg.unfold(1, hh, 1).unfold(2, ww, 1)                                  # (3, 2PY+1, 2P+1, h, w)
            d = wins - T[:, None, None]
            ad = d.abs().amax(0)
            n = M.sum()
            eff = (d.amin(0) > D).float() * M                                             # frame brighter everywhere
            visn = (n - eff.sum((-1, -2))).clamp_min(0.3 * n)
            for tau in TAUS:
                inl = ((ad <= tau).float() * M).sum((-1, -2))
                best[f"inl{tau}"] = max(best[f"inl{tau}"], float((inl / n).max()))
                best[f"eff{tau}"] = max(best[f"eff{tau}"], float((inl / visn).max()))
        res.update(best)
        return res


def main():
    rng = random.Random(1)
    nav = NavMap.for_map(MAP, ROOT / "assets" / "mcw", Config().nav)
    sc = Scorer()
    allc = defaultdict(list)
    for run in RUNS:
        for k, v in cases(run, nav, rng).items():
            allc[k] += v
    limit = {"REAL": 500, "LOST_ALIVE": 300, "LOST_ENDED": 200, "GHOST": 400, "NEG": 800}
    rows = []
    frames = {}
    for k, v in allc.items():
        print(k, len(v), "cases ->", min(len(v), limit[k]))
        for c in rng.sample(v, min(len(v), limit[k])):
            key = (c[1], c[2])
            if key not in frames:
                if len(frames) > 400:
                    frames.clear()
                frames[key] = cv2.imread(str(ROOT / c[1] / "frames" / c[2]))
            r = sc.score(frames[key], c[5], c[6], c[7])
            rows.append({"set": k, "run": c[0], "frame": c[2], "t": c[3], "id": c[4], "mob": c[5], "sx": c[6],
                         "sy": c[7], "logged": c[8], "state": c[9], **r})
    out = Path(__file__).with_name("exp_score.json")
    out.write_text(json.dumps(rows))
    report(rows)


def report(rows):
    names = ["ncc", "ncc_vis"] + [f"inl{t}" for t in TAUS] + [f"eff{t}" for t in TAUS]
    sets = ["REAL", "LOST_ALIVE", "LOST_ENDED", "GHOST", "NEG"]
    by = {s: [r for r in rows if r["set"] == s] for s in sets}
    print("\npercentiles p5 / p25 / p50 / p75 / p95 per set")
    for n in names:
        print(n)
        for s in sets:
            v = sorted(r[n] for r in by[s])
            if v:
                q = lambda p: v[min(len(v) - 1, int(p * len(v)))]  # noqa: E731
                print(f"   {s:11s} n={len(v):4d}  {q(.05):.2f} {q(.25):.2f} {q(.5):.2f} {q(.75):.2f} {q(.95):.2f}")
    print("\nat the threshold where NEG spots pass <= 1 % (and 0.2 %): share passing")
    for n in names:
        v = sorted(r[n] for r in by["NEG"])
        for fp in (0.01, 0.002):
            thr = v[min(len(v) - 1, int((1 - fp) * len(v)))] + 1e-6
            line = f"{n:8s} fp {fp:.3f} thr {thr:.3f}: "
            for s in sets[:4]:
                w = [r[n] for r in by[s]]
                line += f"{s} {sum(x >= thr for x in w) / max(1, len(w)):.2f}  "
            print(line)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report(json.loads(Path(__file__).with_name("exp_score.json").read_text()))
    else:
        main()
