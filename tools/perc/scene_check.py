"""The scene model against a recording (PLAN-perception.md step 1 gates): is the camera exact, how much of the
picture does the scene explain?

    python tools/perc/scene_check.py RUN [--n 200] [--tol 4] [--pictures 6] [--map ID]

RUN = a recording with frames (PNG at native 1366x768 for --tol 4; old JPEG runs: --tol 30). Needs
`python -m maplebrain assets scene MAP` first. On --n saved frames, evenly spread:
- camera: `Scene.locate` from the tracker's camera (ticks.jsonl); share of landmarks matching; difference to the
  tracker's camera; CHECK: is the registered camera the one that explains the most pixels among the 25 cameras
  within 2 px (counted over the whole play area, not the landmarks)?
- explained: play-area pixels (HUD off) within --tol of the expected scene; the same outside the boxes of dynamic
  things we know of (tracked mobs, name tags + bodies, our body): the gate is >= 98 % there; unknown pixels.
  The boxes miss drops, damage numbers, effects, the cursor, chat lines, so also: what is NOT explained split into
  blobs (anything with a 3x3 core: things drawn over the scene) and thin specks (the render's own errors: edges,
  single pixels) - explained outside the blobs = how exact the scene itself is.
- time per frame on the GPU (register + expected + compare).
--pictures N writes RUN/scene_check/NNNNNN.png: frame with the platforms drawn from map.json at the registered
camera | what is left after subtracting the scene.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def ui_mask(h: int, w: int) -> np.ndarray:
    from maplebrain.perception import hud
    m = np.ones((h, w), bool)
    for x0, y0, x1, y1 in hud.UI_RECTS:
        m[y0:min(y1, h), x0:x1] = False
    return m


def dynamic_mask(obs: dict, tags: list, h: int, w: int, pad: int = 14) -> np.ndarray:
    """True where something dynamic we know of is drawn: tracked mobs, players' tags + bodies, our body."""
    from maplebrain.perception.tags import tag_body
    m = np.zeros((h, w), bool)

    def box(x, y, bw, bh):
        m[max(0, int(y) - pad):max(0, int(y + bh) + pad), max(0, int(x) - pad):max(0, int(x + bw) + pad)] = True

    for t in obs.get("mobs") or []:
        if t["state"] in ("live", "dying", "hidden", "tentative"):
            box(t["sx"] - 45, t["sy"] - 95, 90, 125)                 # sprite + HP bar above + name tag below
    for tg in tags:
        box(*tg[:4])
        box(*tag_body(tg))
    if obs.get("me"):
        box(obs["me"][0] - 60, obs["me"][1] - 110, 120, 150)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--tol", type=int, default=4)
    ap.add_argument("--pictures", type=int, default=0)
    ap.add_argument("--map", type=int, default=None)
    a = ap.parse_args()
    import torch
    from maplebrain.perception.tags import find_tags
    from maplebrain.scene import PLAY_H, Scene
    map_id = a.map
    if map_id is None:
        log = (a.run / "log.txt").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"map recognised: (\d+)", log) or re.search(r"\bmap (\d+) ", log)
        map_id = int(m.group(1))
    scene = Scene.load(map_id)
    mj = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
    ticks = [json.loads(l) for l in open(a.run / "ticks.jsonl", encoding="utf-8")]
    ticks = [k for k in ticks if k.get("frame") and k["obs"].get("cam")]
    ticks = [ticks[int(i * (len(ticks) - 1) / max(1, a.n - 1))] for i in range(min(a.n, len(ticks)))]
    h, w = PLAY_H, 1366
    ui = ui_mask(h, w)
    ui_t = torch.from_numpy(ui).to(scene.dev)
    rows, shown = [], 0
    out_dir = a.run / "scene_check"
    for i, k in enumerate(ticks):
        frame = cv2.imread(str(a.run / "frames" / k["frame"]))
        if frame is None:
            continue
        obs = k["obs"]
        ft = torch.from_numpy(np.ascontiguousarray(frame[:h])).to(scene.dev)
        if scene.dev == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        reg = scene.locate(ft, obs["cam"], tol=a.tol, mask=ui_t)
        if reg is None:
            rows.append({"frame": k["frame"], "reg": None})
            continue
        C, share, n_marks = reg
        exp, known = scene.expected(C)
        d = (ft.float() - exp).abs().amax(dim=2)
        ok = (d <= a.tol) & known
        if scene.dev == "cuda":
            torch.cuda.synchronize()
        ms = 1000 * (time.perf_counter() - t0)
        # the check: among the cameras within 2 px, does this one explain the most pixels?
        best = (int((ok & ui_t).sum()), 0, 0)
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if (dx, dy) != (0, 0):
                    e2, k2 = scene.expected((C[0] + dx, C[1] + dy))
                    n2 = int((((ft.float() - e2).abs().amax(dim=2) <= a.tol) & k2 & ui_t).sum())
                    if n2 > best[0]:
                        best = (n2, dx, dy)
        okn, knownn = ok.cpu().numpy(), known.cpu().numpy()
        dyn = dynamic_mask(obs, find_tags(frame), h, w)
        still = ui & ~dyn
        bad = (~okn & ui).astype(np.uint8)                            # not explained: blobs (dynamic things, by
        blob = cv2.dilate(cv2.erode(bad, np.ones((3, 3), np.uint8)), np.ones((9, 9), np.uint8)) > 0   # their nature) or
        speck = (bad > 0) & ~blob                                     # thin specks (the render's own errors)
        rows.append({"frame": k["frame"], "reg": share, "marks": n_marks, "C": C, "ms": ms,
                     "cam_d": (C[0] - obs["cam"][0], C[1] - obs["cam"][1]), "best_other": best[1:],
                     "all": float(okn[ui].mean()), "still": float(okn[still].mean()), "unknown": float((~knownn)[ui].mean()),
                     "dyn": float(dyn[ui].mean()), "blob": float(blob[ui].mean()),
                     "speck": float(speck[ui].sum() / max(1, (ui & ~blob).sum()))})
        if shown < a.pictures and i % max(1, len(ticks) // max(1, a.pictures)) == 0:
            out_dir.mkdir(exist_ok=True)
            vis = frame[:h].copy()
            for f in mj["footholds"].values():
                cv2.line(vis, (int(f["x1"] - C[0]), int(f["y1"] - C[1])), (int(f["x2"] - C[0]), int(f["y2"] - C[1])),
                         (0, 255, 0), 1)
            for r in mj["ladderRopes"]:
                cv2.line(vis, (int(r["x"] - C[0]), int(r["y1"] - C[1])), (int(r["x"] - C[0]), int(r["y2"] - C[1])),
                         (255, 255, 0), 1)
            left = frame[:h].copy()
            left[okn] = 0
            left[~knownn] = (60, 0, 60)
            cv2.imwrite(str(out_dir / f"{k['frame'][:6]}.png"), np.vstack([vis, left]))
            shown += 1
    good = [r for r in rows if r.get("reg") is not None]
    q = lambda v, p: float(np.percentile(v, p))                       # noqa: E731
    print(f"{a.run}: map {map_id}, {len(rows)} frames, tolerance +-{a.tol}; device {scene.dev}")
    print(f"  registered {len(good)} of {len(rows)}; landmarks matching p5 / p50: {100 * q([r['reg'] for r in good], 5):.1f} % / "
          f"{100 * q([r['reg'] for r in good], 50):.1f} % (of {int(q([r['marks'] for r in good], 50))} landmarks)")
    off = [r for r in good if r["best_other"] != (0, 0)]
    print(f"  CHECK the registered camera explains the most pixels among the 25 within 2 px: {len(good) - len(off)} of "
          f"{len(good)}" + (f"; others: {[(r['frame'], r['best_other']) for r in off[:8]]}" if off else ""))
    dx, dy = [r["cam_d"][0] for r in good], [r["cam_d"][1] for r in good]
    print(f"  registered - tracker's camera px: dx p5/p50/p95 {q(dx, 5):+.0f} {q(dx, 50):+.0f} {q(dx, 95):+.0f}, "
          f"dy {q(dy, 5):+.0f} {q(dy, 50):+.0f} {q(dy, 95):+.0f}")
    print(f"  explained (within +-{a.tol}, HUD off): whole play area p5 / p50 {100 * q([r['all'] for r in good], 5):.1f} % / "
          f"{100 * q([r['all'] for r in good], 50):.1f} %; outside known dynamic boxes p5 / p50 / mean "
          f"{100 * q([r['still'] for r in good], 5):.1f} % / {100 * q([r['still'] for r in good], 50):.1f} % / "
          f"{100 * np.mean([r['still'] for r in good]):.1f} %  (GATE >= 98 %)")
    print(f"  unknown scenery p50 {100 * q([r['unknown'] for r in good], 50):.1f} %, max {100 * max(r['unknown'] for r in good):.1f} %; "
          f"dynamic boxes cover p50 {100 * q([r['dyn'] for r in good], 50):.1f} % of the play area")
    print(f"  not explained = blobs (3x3 cores grown 4 px: things drawn over the scene) p50 {100 * q([r['blob'] for r in good], 50):.1f} % "
          f"of the play area, max {100 * max(r['blob'] for r in good):.1f} %; outside them (thin specks = the render's own "
          f"errors) explained p5 / p50 {100 * (1 - q([r['speck'] for r in good], 95)):.2f} % / "
          f"{100 * (1 - q([r['speck'] for r in good], 50)):.2f} %")
    ms = [r["ms"] for r in good[5:]] or [r["ms"] for r in good]
    print(f"  register + expected + compare: p50 {q(ms, 50):.1f} ms, p90 {q(ms, 90):.1f} ms")
    (a.run / "scene_check.json").write_text(json.dumps(rows))
    if a.pictures:
        print(f"  pictures: {out_dir}")


if __name__ == "__main__":
    main()
