"""PLAN-moving-scenery.md step 5's gate on footage: maplebrain's live path on a weather-cloud map, frame by frame as the
Perceiver runs it - the movers followed (scene.MoverFollow), the expected picture, the clouds followed
(perception/clouds.py), the frame undone, the fit with the cloud (the tolerant vote, the cloud numbers).
    python tools/perc/scenery/live5.py CAP [--every K] [--compare] [--sheets]
Printed + OUT/live5_<cap>.json:
  sightings      the fit's mobs over the frames (the gate: the two old captures >= 1,540 / 940; cloudtrack.py --fit
                 --tolvote, the prototype, 1,568 / 979)
  --compare      + the fit on the frame with the clouds left in (B: step 4's picture), the same frames
  per class      sightings by `cloud` (the mean cloud alpha over their SEEN pixels); n_cloud > 0 (covered by cloud)
  --sheets       40 random sightings under a cloud (cloud >= 0.2) + 40 any, frame | undone with the box ->
                 OUT/live5_<cap>_under_N.png / _any_N.png, for the look by eye (0 ghosts)
  ms             p50 of the undo and the fit (with the cloud) per frame"""
import argparse
import json
import random
import time

import cv2
import numpy as np
import torch

import cam as camlib
import msl
import proto
from maplebrain.config import Perception
from maplebrain.perception import hud
from maplebrain.perception.clouds import Clouds
from maplebrain.perception.fit import Fitter
from maplebrain.scene import MoverFollow, Scene

SW, PLAY_H = 1366, 700


class Pool:
    """A random sample of `n` (reservoir), fixed seed."""

    def __init__(self, n, seed):
        self.n, self.rnd, self.seen, self.items = n, random.Random(seed), 0, []

    def want(self) -> int | None:
        """The slot a new item goes to, or None (not kept)."""
        self.seen += 1
        if len(self.items) < self.n:
            self.items.append(None)
            return len(self.items) - 1
        j = self.rnd.randrange(self.seen)
        return j if j < self.n else None


def crop(img, und, fz, m):
    p = fz.poses[fz.pose_ix[(m.type, m.pose, m.facing)]]
    h, w = p.pic.shape[:2]
    bx, by = m.feet[0] - p.ox, m.feet[1] - p.oy
    x0, y0 = max(0, min(SW - 200, m.feet[0] - 100)), max(0, min(PLAY_H - 150, m.feet[1] - 110))
    a, b = img[y0:y0 + 150, x0:x0 + 200].copy(), und[y0:y0 + 150, x0:x0 + 200].copy()
    for im_ in (a, b):
        cv2.rectangle(im_, (bx - x0, by - y0), (bx - x0 + w, by - y0 + h), (0, 255, 0), 1)
    return np.hstack([a, b])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--sheets", action="store_true")
    a = ap.parse_args()
    msl.guard()
    c = msl.clip(a.cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(a.cap)["rows"] if r[3] is not None][::a.every]
    sc = Scene.load(c.map_id)
    fol = MoverFollow(sc) if any(b.get("mover") is not None for b, _ in sc.backs) else None
    cl = Clouds(sc.dev, Perception())
    fz = Fitter(sc, c.map_id, msl.ROOT / "assets" / "mcw")
    fz.warm()
    names = {p.type: json.loads((msl.ROOT / "assets" / "mcw" / "mobs" / str(p.type) / "mob.json")
                                .read_text(encoding="utf-8")).get("name") for p in fz.poses}
    ui = None
    n_mob = n_B = 0
    under = {}
    n_cov = 0
    ms_undo, ms_fit = [], []
    pools = {"under": Pool(40, 1), "any": Pool(40, 2)}
    for r in cams:
        i = r[0]
        _, name, t = fr[i]
        img = c.read(name)
        if ui is None:
            mk = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
            x0, y0, x1, y1 = hud.CHAT_WORLD
            mk = mk.copy()
            mk[y0:y1, x0:x1] = True
            ui = torch.from_numpy(np.ascontiguousarray(mk[:PLAY_H])).to(sc.dev)
        f = proto.frame_tensor(img, sc.dev)
        C = (r[3], r[4])
        X = fol.update(f, C, t) if fol is not None else None
        E, known = sc.expected(C, X=X)
        on = cl.update(f, E, known & ui, C, t)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        fu, k2, cloud = f, known, None
        if on:
            fu, thick = cl.undo(f)
            k2 = known & ~thick
            cloud = (cl.A[..., 0].float(), thick)
        torch.cuda.synchronize()
        t1 = time.perf_counter()
        mobs = fz.fit(fu, C, E, k2, ui, cloud=cloud)
        t2 = time.perf_counter()
        ms_undo.append(1000 * (t1 - t0))
        ms_fit.append(1000 * (t2 - t1))
        n_mob += len(mobs)
        if a.compare:
            n_B += len(fz.fit(f, C, E, known, ui))
        und = None
        for m in mobs:
            b = min(int(m.cloud * 10), 9)
            under[b] = under.get(b, 0) + 1
            n_cov += m.n_cloud > 0
            if not a.sheets:
                continue
            for nm in (("under", "any") if m.cloud >= 0.2 else ("any",)):
                j = pools[nm].want()
                if j is None:
                    continue
                und = fu.cpu().numpy() if und is None else und
                tile = crop(img[:PLAY_H], und, fz, m)
                lab = f"fr {i} {names.get(m.type)} {m.pose} cloud {m.cloud:.2f} seen {m.n_seen}"
                for col, th in (((0, 0, 0), 3), ((255, 255, 255), 1)):
                    cv2.putText(tile, lab, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, th)
                pools[nm].items[j] = tile
    res = {"cap": a.cap, "frames": len(cams), "every": a.every, "sightings": n_mob, "sightings_clouds_left_in": n_B if a.compare else None,
           "by_cloud_tenth": {f"{k / 10:.1f}": v for k, v in sorted(under.items())}, "covered_by_cloud": n_cov,
           "ms_undo_p50": round(float(np.median(ms_undo[10:])), 3), "ms_fit_p50": round(float(np.median(ms_fit[10:])), 3),
           "ms_fit_p90": round(float(np.percentile(ms_fit[10:], 90)), 3), "finder_runs": cl.finds}
    (msl.OUT / f"live5_{a.cap.replace('#', '_')}.json").write_text(json.dumps(res, indent=1))
    print(f"{a.cap}: map {c.map_id}, {len(cams)} frames (every {a.every})")
    print(f"  sightings with the clouds undone: {n_mob}" + (f"; the clouds left in: {n_B}" if a.compare else ""))
    print(f"  by the mean cloud alpha over their SEEN pixels: {res['by_cloud_tenth']}; with pixels covered by cloud: {n_cov}")
    print(f"  ms p50 undo {res['ms_undo_p50']}, fit {res['ms_fit_p50']} (p90 {res['ms_fit_p90']})")
    for nm, pool in pools.items():
        tiles = [x for x in pool.items if x is not None]
        for s0 in range(0, len(tiles), 20):
            part = tiles[s0:s0 + 20]
            while len(part) % 4:
                part.append(np.zeros_like(part[0]))
            sheet = np.vstack([np.hstack(part[k:k + 4]) for k in range(0, len(part), 4)])
            print(f"  sheet ({nm}, frame | undone):", msl.save(f"live5_{a.cap.replace('#', '_')}_{nm}_{s0 // 20}.png", sheet))


if __name__ == "__main__":
    main()
