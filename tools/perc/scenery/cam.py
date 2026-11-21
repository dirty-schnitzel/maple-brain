"""The scene camera of every frame of a capture, also on flagged maps (the camera registers on tiles / objects only).
    python cam.py CAP [--every K] [--t0 S --t1 S]
-> out/cams/<cap>.json {"map", "rows": [[i, n, t, Cx, Cy, share] | [i, n, t, null, null, 0]]}. The kept replay's
camera is used when the capture has one."""
import argparse
import json

import numpy as np
import torch

import msl


def cams(cap, every=1, force=False, t0=0.0, t1=1e9):
    p = msl.OUT / "cams" / f"{cap.replace('#', '_')}_{every}.json"
    if p.exists() and not force:
        return json.loads(p.read_text())
    c = msl.clip(cap)
    fr = c.frames()
    rows = msl.kept(cap)
    out = []
    if rows is not None and len(rows) == len(fr):
        for i in range(0, len(fr), every):
            C = rows[i]["C"]
            out.append([i, fr[i][0], fr[i][2], C[0] if C else None, C[1] if C else None,
                        rows[i]["facts"].get("scene_share") or 0])
    else:
        msl.guard()
        from maplebrain.perception import hud
        from maplebrain.scene import SceneCamera
        scene = msl.scene_of(c.map_id)
        sc = SceneCamera(scene)
        ui = None
        for i in range(0, len(fr), every):
            n, name, t = fr[i]
            if not t0 <= t <= t1:
                continue
            img = c.read(name)
            f = torch.from_numpy(np.ascontiguousarray(img)).to(scene.dev)
            if ui is None:
                ui = hud.ui_mask(img.shape, None)
            C = sc.update(f, mask=ui) if sc.C is not None else None
            if C is None:                                  # lost / the start: seeds on a grid over the whole map
                best = None
                m = torch.from_numpy(np.ascontiguousarray(ui[:msl.PLAY_H] > 0)).to(scene.dev)
                for gy in range(scene.y0, scene.y0 + max(1, scene.meta["h"] - msl.PLAY_H) + 96, 96):
                    for gx in range(scene.x0, scene.x0 + max(1, scene.meta["w"] - msl.SW) + 96, 96):
                        r = scene.register(f, (gx, gy), 48, 4, msl.PLAY_H, m)
                        if r is not None and (best is None or r[1] > best[1]):
                            best = r
                if best is not None and best[1] >= 0.2:
                    sc.C, sc.share, sc.step, sc.found = best[0], best[1], (0, 0), True
                    C = best[0]
            out.append([i, n, t, C[0] if C else None, C[1] if C else None, round(sc.share or 0, 3) if C else 0])
            if len(out) % 500 == 0:
                print(" ", cap, len(out), "frames", flush=True)
    res = {"cap": cap, "map": c.map_id, "every": every, "rows": out}
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(res))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    for cap in a.caps:
        r = cams(cap, a.every, a.force)
        rows = r["rows"]
        got = [x for x in rows if x[3] is not None]
        sh = np.array([x[5] for x in got]) if got else np.zeros(1)
        print(f"{cap}: map {r['map']}, {len(rows)} frames looked at, camera on {len(got)} "
              f"({100 * len(got) / max(1, len(rows)):.1f} %), share p10 / p50 {np.percentile(sh, 10):.2f} / "
              f"{np.percentile(sh, 50):.2f}; x {min(x[3] for x in got)}..{max(x[3] for x in got)} y "
              f"{min(x[4] for x in got)}..{max(x[4] for x in got)}" if got else f"{cap}: no camera")
