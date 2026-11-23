"""PLAN-moving-scenery.md step 4's gate: maplebrain's clouds (perception/clouds.py, followed over time) against the
per-frame finder (run_clouds.py's OUT/clouds_<tag>.json: CloudFinder alone on each of its frames, the reference).
    python tools/perc/scenery/live4.py CAP --finds TAG
Every frame with a camera (cam.py), as the Perceiver does it: the movers followed, the expected picture, the valid
pixels (known, the UI out, the chat rect in), Clouds.update. Printed + OUT/live4_<cap>.json:
  shows      frame = expected WITH the cloud layer, of the valid pixels (cloudtrack.py's shows2) - and without it
  finds      of the finder's clouds on its frames, the share with a followed cloud of the same picture within 1 px
  per cloud  (followed on >= 20 fixes) its opacity against the finder's on the frames both have it (max |diff|),
             its fixes' places against a straight line (rms)
  ms         p50 of follow + layer + whitened (the per-frame cost), the finder when it runs; its runs a second after
             the stay's first 5 s"""
import argparse
import json
import time

import numpy as np
import torch

import cam as camlib
import msl
import proto
from maplebrain.config import Perception
from maplebrain.perception import hud
from maplebrain.perception.clouds import Clouds
from maplebrain.scene import MoverFollow, Scene


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--finds", required=True)
    a = ap.parse_args()
    msl.guard()
    c = msl.clip(a.cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(a.cap)["rows"] if r[3] is not None]
    finds = {r["i"]: r["clouds"] for r in json.loads((msl.OUT / f"clouds_{a.finds}.json").read_text())}
    sc = Scene.load(c.map_id)
    fol = MoverFollow(sc)
    cl = Clouds(sc.dev, Perception())
    ui = None
    shows, shows0, per, fixes = [], [], [], {}
    match_n = match_ok = 0
    odiff = {}
    find_t = []
    t_first = None
    for r in cams:
        i = r[0]
        _, name, t = fr[i]
        t_first = t if t_first is None else t_first
        img = c.read(name)
        if ui is None:
            m = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
            x0, y0, x1, y1 = hud.CHAT_WORLD
            m = m.copy()
            m[y0:y1, x0:x1] = True
            ui = torch.from_numpy(np.ascontiguousarray(m[:msl.PLAY_H])).to(sc.dev)
        f = proto.frame_tensor(img, sc.dev)
        C = (r[3], r[4])
        X = fol.update(f, C, t)
        E, known = sc.expected(C, X=X)
        valid = known & ui
        n_find = cl.finds
        on = cl.update(f, E, valid, C, t)
        ms = cl.ms
        per.append(ms["follow"] + ms["layer"] + ms["whitened"])
        if cl.finds > n_find:
            find_t.append((t - t_first, ms["find"]))
        world = int(valid.sum())
        ff = f.float()
        shows.append(float((((ff - cl.E2).abs().amax(dim=2) <= 4) & valid).sum()) / world)
        shows0.append(float((((ff - E).abs().amax(dim=2) <= 4) & valid).sum()) / world)
        for tr in on:
            if tr.get("seen") and tr["t"] == t:
                fixes.setdefault(tr["id"], []).append((t, tr["mx"], tr["my"], tr["o"]))
        if i in finds:
            for k, mx, my, sh, nn, o, vis in finds[i]:
                match_n += 1
                hit = [tr for tr in on if tr["k"] == k and abs(cl._screen(tr, C, t)[0] + C[0] - mx) <= 1
                       and abs(cl._screen(tr, C, t)[1] + C[1] - my) <= 1]
                if hit:
                    match_ok += 1
                    odiff.setdefault(hit[0]["id"], []).append(abs(hit[0]["o"] - o))
    rows = []
    for cid, fx in fixes.items():
        if len(fx) < 20:
            continue
        tt, x, y = (np.array([v[j] for v in fx], float) for j in range(3))
        px, py = np.polyfit(tt, x, 1), np.polyfit(tt, y, 1)
        rms = float(np.sqrt(np.mean((x - np.polyval(px, tt)) ** 2 + (y - np.polyval(py, tt)) ** 2)))
        od = max(odiff.get(cid, [0.0]))
        rows.append({"id": cid, "fixes": len(fx), "s": round(float(tt[-1] - tt[0]), 1), "o": fx[0][3], "o_vs_finder_max": round(od, 4),
                     "rms": round(rms, 2), "vx": round(float(px[0]), 2)})
    after = [ft for ft in find_t if ft[0] >= 5]
    dur = max(1e-6, (cams[-1][2] - t_first) - 5)
    res = {"cap": a.cap, "frames": len(cams), "shows_pct": round(100 * float(np.mean(shows)), 2),
           "shows_p10": round(100 * float(np.percentile(shows, 10)), 2), "shows_nocloud_pct": round(100 * float(np.mean(shows0)), 2),
           "finds": match_n, "finds_followed_pct": round(100 * match_ok / max(1, match_n), 2),
           "clouds": len(rows), "o_vs_finder_max": max([r_["o_vs_finder_max"] for r_ in rows] or [0]),
           "rms_max": max([r_["rms"] for r_ in rows] or [0]), "rms_p50": float(np.median([r_["rms"] for r_ in rows] or [0])),
           "ms_frame_p50": round(float(np.median(per[10:])), 3), "ms_frame_p90": round(float(np.percentile(per[10:], 90)), 3),
           "finder_runs": len(find_t), "finder_runs_per_s_after_5s": round(len(after) / dur, 3),
           "finder_ms_p50": round(float(np.median([v for _, v in find_t])) if find_t else 0, 2),
           "finder_ms_max": round(max([v for _, v in find_t] or [0]), 2), "per_cloud": rows}
    (msl.OUT / f"live4_{a.cap.replace('#', '_')}.json").write_text(json.dumps(res, indent=1))
    print(f"{a.cap}: map {c.map_id}, {len(cams)} frames")
    print(f"  frame = expected with the cloud layer: {res['shows_pct']} % (p10 {res['shows_p10']}); without {res['shows_nocloud_pct']} %")
    print(f"  the finder's {match_n} clouds: {res['finds_followed_pct']} % with a followed cloud within 1 px")
    print(f"  {len(rows)} clouds followed on >= 20 fixes: opacity vs the finder's max |diff| {res['o_vs_finder_max']}, line rms p50 "
          f"{res['rms_p50']:.2f} max {res['rms_max']}")
    print(f"  ms follow + layer + whitened p50 {res['ms_frame_p50']} p90 {res['ms_frame_p90']}; finder runs {len(find_t)} "
          f"({res['finder_runs_per_s_after_5s']} a second after 5 s), {res['finder_ms_p50']} ms p50, max {res['finder_ms_max']}")
    bad = [r_ for r_ in rows if r_["o_vs_finder_max"] > 0.01 or r_["rms"] > 0.6]
    for r_ in bad[:12]:
        print("    over a gate:", r_)


if __name__ == "__main__":
    main()
