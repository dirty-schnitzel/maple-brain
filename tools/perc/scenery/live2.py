"""PLAN-moving-scenery.md step 2's gate: maplebrain's movers (scene.MoverFollow + Scene.expected(C, X)) against the
prototype (proto.MScene: locate + expected, the slow exact reference), on every frame of a capture with a camera.
    python tools/perc/scenery/live2.py CAP [--exp-every 10] [--shows-every 4] [--max N]
Per capture, printed and written to OUT/live2_<cap>.json:
  expected   every `--exp-every`th frame: Scene.expected at the REFERENCE's places vs MScene.expected - the worst
             difference on pixels both call known (levels), and the share of pixels where the two known masks differ
  follow     of the mover-frames the reference finds, the share the live follow finds too (independently: it starts
             with nothing and is never reset from the reference), and of those, on the same pixel; found by the live
             follow only
  shows      every `--shows-every`th frame: the share of the play area (the UI masked) where the frame equals the
             live expected picture at the LIVE follow's places within 4 levels (run_proto.py's `shows`); today's
             picture (no places: the movers' rows unknown) beside it
  ms         p50 / p90 of MoverFollow.update and of Scene.expected with the places (CUDA synchronised)"""
import argparse
import json
import time

import numpy as np
import torch

import cam as camlib
import msl
import proto
from maplebrain.perception import hud
from maplebrain.scene import MoverFollow, Scene


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--exp-every", type=int, default=10)
    ap.add_argument("--shows-every", type=int, default=4)
    ap.add_argument("--max", type=int, default=10 ** 9)
    a = ap.parse_args()
    msl.guard()
    c = msl.clip(a.cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(a.cap)["rows"] if r[3] is not None][:a.max]
    ms = proto.MScene(c.map_id)
    live = Scene.load(c.map_id)
    fol = MoverFollow(live)
    dev = live.dev
    sync = torch.cuda.synchronize if dev == "cuda" else (lambda: None)
    unfollowed = sorted(set(ms.movers) - set(fol.idx))       # no opaque pixel: never its own colour, never found
    assert set(fol.idx) <= set(ms.movers), (sorted(ms.movers), fol.idx)
    if unfollowed:
        print(f"  movers without an opaque pixel (left unknown): {[live.backs[i][0]['file'] for i in unfollowed]}")
    ui = None
    worst, kdiff, n_exp = 0.0, [], 0
    ref_n = both = same = live_only = 0
    per = {i: [0, 0, 0, 0] for i in fol.idx}                   # ref found, both, same pixel, live only
    ref_unf = 0                                                # frames the reference finds an unfollowed mover
    shows, shows0, t_fol, t_exp, t_exp0, t_nofull = [], [], [], [], [], []
    t0 = time.perf_counter()
    for k, r in enumerate(cams):
        i = r[0]
        _, name, t = fr[i]
        img = c.read(name)
        if ui is None:
            ui = torch.from_numpy(np.ascontiguousarray(hud.ui_mask(img.shape, None)[:msl.PLAY_H] > 0)).to(dev)
            world = int(ui.sum())
        f = proto.frame_tensor(img, dev)
        C = (r[3], r[4])
        ms.locate(f, C, t)                                     # the reference
        n_full = fol.fulls
        sync(); a0 = time.perf_counter()
        X = fol.update(f, C, t)
        sync(); t_fol.append(1000 * (time.perf_counter() - a0))
        if fol.fulls == n_full:
            t_nofull.append(t_fol[-1])
        ref_unf += sum(ms.movers[i].found for i in unfollowed)
        for j, bi in enumerate(fol.idx):
            m = ms.movers[bi]
            if m.found:
                ref_n += 1
                per[bi][0] += 1
                if fol.found[j]:
                    both += 1
                    per[bi][1] += 1
                    e = ((m.X - X[bi] + m.cx / 2) % m.cx) - m.cx / 2
                    if abs(e) < 0.5:
                        same += 1
                        per[bi][2] += 1
            elif fol.found[j]:
                live_only += 1
                per[bi][3] += 1
        if k % a.exp_every == 0:
            Xr = {bi: m.X for bi, m in ms.movers.items()}
            e_ref, k_ref = ms.expected(C)
            e_l, k_l = live.expected(C, X=Xr)
            both_k = k_ref & k_l
            if bool(both_k.any()):
                worst = max(worst, float((e_l - e_ref).abs().amax(dim=2)[both_k].max()))
            kdiff.append(float((k_ref != k_l).float().mean()))
            n_exp += 1
        if k % a.shows_every == 0:
            sync(); a0 = time.perf_counter()
            e, kn = live.expected(C, X=X)
            sync(); t_exp.append(1000 * (time.perf_counter() - a0))
            ok = (((f.float() - e).abs().amax(dim=2) <= 4) & kn & ui)
            shows.append(float(ok.sum()) / world)
            sync(); a0 = time.perf_counter()
            e0, k0 = live.expected(C)
            sync(); t_exp0.append(1000 * (time.perf_counter() - a0))
            shows0.append(float((((f.float() - e0).abs().amax(dim=2) <= 4) & k0 & ui).sum()) / world)
        if (k + 1) % 1000 == 0:
            print(f"  {k + 1} / {len(cams)} frames, {time.perf_counter() - t0:.0f} s", flush=True)
    q = lambda v, p: float(np.percentile(np.array(v[10:] or v), p))
    res = {"cap": a.cap, "map": c.map_id, "frames": len(cams), "movers": len(fol.idx),
           "expected_worst_levels": round(worst, 3), "expected_known_differs_max": max(kdiff) if kdiff else 0,
           "expected_frames": n_exp,
           "ref_mover_frames": ref_n, "follow_found": both, "follow_found_pct": round(100 * both / max(1, ref_n), 2),
           "same_pixel_pct": round(100 * same / max(1, both), 3), "live_only": live_only, "full_looks": fol.fulls,
           "per_mover": {str(bi): v for bi, v in per.items()},
           "shows_pct": round(100 * float(np.mean(shows)), 2), "shows_p10": round(100 * q(shows, 10), 2),
           "shows_today_pct": round(100 * float(np.mean(shows0)), 2),
           "unfollowed": unfollowed, "ref_found_unfollowed": ref_unf,
           "ms_follow_p50": round(q(t_fol, 50), 3), "ms_follow_p90": round(q(t_fol, 90), 3),
           "ms_follow_nofull_p50": round(q(t_nofull, 50), 3), "full_look_frames_pct": round(
               100 * (len(t_fol) - len(t_nofull)) / max(1, len(t_fol)), 1),
           "ms_expected_p50": round(q(t_exp, 50), 3), "ms_expected_p90": round(q(t_exp, 90), 3),
           "ms_expected_noplaces_p50": round(q(t_exp0, 50), 3)}
    (msl.OUT / f"live2_{a.cap.replace('#', '_')}.json").write_text(json.dumps(res, indent=1))
    print(f"{a.cap}: map {c.map_id}, {len(cams)} frames, {len(fol.idx)} movers, {time.perf_counter() - t0:.0f} s")
    print(f"  expected at the reference's places: worst {worst:.3f} levels on known pixels ({n_exp} frames); "
          f"known masks differ on <= {100 * res['expected_known_differs_max']:.4f} % of the pixels")
    print(f"  follow: of {ref_n} mover-frames the reference finds, the live follow finds {both} "
          f"({res['follow_found_pct']} %), on the same pixel {res['same_pixel_pct']} %; live only {live_only}; "
          f"full looks {fol.fulls} (on {res['full_look_frames_pct']} % of the frames)"
          + (f"; the reference finds an unfollowed mover on {ref_unf} mover-frames" if unfollowed else ""))
    for bi, v in per.items():
        b = live.backs[bi][0]
        print(f"    mover {bi} {b['file']} rx {b['rx']}: ref {v[0]}, both {v[1]}, same {v[2]}, live only {v[3]}")
    print(f"  frame = expected: {res['shows_pct']} % of the play area (p10 {res['shows_p10']}); without places "
          f"{res['shows_today_pct']} %")
    print(f"  ms p50 / p90: follow {res['ms_follow_p50']} / {res['ms_follow_p90']} (frames without a full look: p50 "
          f"{res['ms_follow_nofull_p50']}), expected "
          f"{res['ms_expected_p50']} / {res['ms_expected_p90']} (without places {res['ms_expected_noplaces_p50']})")


if __name__ == "__main__":
    main()
