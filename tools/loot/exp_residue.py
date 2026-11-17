"""E-L5 (PLAN-loot.md): an INDEPENDENT look for drops - never the finder's own output: what the scene does not
explain, minus what the finder and the mob tracks explain, joined over time. A drop rests at one map x and bobs 5-6 px
every 2 s; anything small that does the same and that the finder did NOT name is a drop it misses (an unknown
picture, a see-through item, a covered one).

    python tools/loot/exp_residue.py RUN [--find NAME] [--every 1] [--t0 S] [--t1 S] [--sheet 40]

Per frame (camera from the find file): R = |frame - expected| > 4 on known scenery, world only; minus the finder's
drop boxes (+2 px), the recording's mob tracks' boxes, our body box, players' tag boxes (body above the tag). Blobs
(3x3 closed) 80..2600 px in a box <= 56 x 56 -> (map x of the box's centre, map y of its bottom).
Joined: same map x (+-2) and bottom y (+-8) on >= `min_frames` frames within 4 s -> a STILL patch; "bobbing" = its
bottom y takes >= 3 values over >= 3 px while x stays. Prints the counts, writes RUN/loot/residue_<NAME>.json and a
sheet of the bobbing / still patches (one tile each, 3x) for the eye.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, map_of, run_ticks, sheet, world_mask, PLAY_H, SW  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--find", default="all")
ap.add_argument("--every", type=int, default=1)
ap.add_argument("--t0", type=float, default=0.0)
ap.add_argument("--t1", type=float, default=1e9)
ap.add_argument("--min-frames", type=int, default=12)
ap.add_argument("--sheet", type=int, default=40)
ap.add_argument("--out", default="")
ap.add_argument("--no-chat", action="store_true", help="leave out the rows from 40 px above the chat rect down (chat text scrolls)")
a = ap.parse_args()

import torch  # noqa: E402
from maplebrain.perception import hud  # noqa: E402
from maplebrain.scene import Scene  # noqa: E402

run = Path(a.run)
scene = Scene.load(map_of(run))
rows = [json.loads(l) for l in open(run / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("drops") is not None and a.t0 <= r["t"] <= a.t1][::a.every]
tk = {k["frame"]: k for k in run_ticks(run)}
ui = None
pats = []          # (row index, t, map x centre, map y bottom, x, y, w, h, area)
kern = np.ones((3, 3), np.uint8)
for ri, r in enumerate(rows):
    f = frame(run, r["frame"])
    ft = torch.from_numpy(np.ascontiguousarray(f[:PLAY_H])).to(scene.dev)
    if ui is None:
        m = world_mask(map_of(run), f.shape)
        m[max(0, hud.CHAT_WORLD[1] - 40):, :] &= False if a.no_chat else True     # --no-chat: the chat lines' rows out
        ui = torch.from_numpy(np.ascontiguousarray(m)).to(scene.dev)
    C = r["cam"]
    exp, known = scene.expected(C)
    R = (((ft.float() - exp).abs().amax(dim=2) > 4) & known & ui).cpu().numpy().astype(np.uint8)
    for d in r["drops"]:
        x, y, w, h = d["box"]
        R[max(0, y - 2):y + h + 2, max(0, x - 2):x + w + 2] = 0
    k = tk.get(r["frame"]) or {}
    for mb in k.get("mobs") or []:
        sx, sy = int(mb.get("sx", -999)), int(mb.get("sy", -999))
        R[max(0, sy - 95):max(0, sy + 12), max(0, sx - 55):max(0, sx + 55)] = 0
    me = k.get("me")
    if me:
        R[max(0, int(me[1]) - 95):int(me[1]) + 32, max(0, int(me[0]) - 48):int(me[0]) + 48] = 0
    for tg in (k.get("facts") or {}).get("tags") or []:
        tx, ty, tw, th = (int(v) for v in tg[:4])
        R[max(0, ty - 95):ty + th + 4, max(0, tx + tw // 2 - 48):tx + tw // 2 + 48] = 0
    R = cv2.morphologyEx(R, cv2.MORPH_CLOSE, kern)
    n, _, st, _ = cv2.connectedComponentsWithStats(R, connectivity=8)
    for i in range(1, n):
        x, y, w, h, ar = (int(v) for v in st[i])
        if 80 <= ar <= 2600 and w <= 56 and h <= 56 and w >= 6 and h >= 6:
            pats.append((ri, r["t"], x + w / 2 + C[0], y + h + C[1], x, y, w, h, ar))
print(f"{run.name}: {len(rows)} frames, {len(pats)} small unexplained patches ({len(pats) / max(1, len(rows)):.1f} a frame)")
# join over time
tracks, open_ = [], []
for p in pats:
    ri, t, mx, my = p[:4]
    best = None
    for tr in open_:
        if abs(tr["mx"] - mx) <= 2 and abs(tr["my"] - my) <= 8 and tr["last"] != ri and t - tr["t1"] <= 4:
            best = tr
            break
    if best is None:
        best = {"mx": mx, "my": my, "obs": [], "last": -1, "t0": t}
        open_.append(best)
        tracks.append(best)
    best["obs"].append(p)
    best["last"], best["t1"] = ri, t
    open_ = [tr for tr in open_ if t - tr["t1"] <= 4]
still = [tr for tr in tracks if len(tr["obs"]) >= a.min_frames]
for tr in still:
    ys = np.array([o[3] for o in tr["obs"]])
    xs = np.array([o[2] for o in tr["obs"]])
    tr["yr"], tr["ny"], tr["xr"] = float(ys.max() - ys.min()), len(set(ys.tolist())), float(xs.max() - xs.min())
    tr["bob"] = tr["yr"] >= 3 and tr["ny"] >= 3 and tr["xr"] <= 3
    tr["w"] = float(np.median([o[6] for o in tr["obs"]]))
    tr["h"] = float(np.median([o[7] for o in tr["obs"]]))
bob = [tr for tr in still if tr["bob"]]
print(f"still patches (>= {a.min_frames} frames at one map place): {len(still)}; of them bobbing like a drop: {len(bob)}")
for tr in sorted(bob, key=lambda tr: -len(tr["obs"]))[:30]:
    print(f"   bob: map ({tr['mx']:.0f}, {tr['my']:.0f}) {tr['w']:.0f}x{tr['h']:.0f} frames {len(tr['obs'])} t {tr['t0']:.1f}-"
          f"{tr['t1']:.1f} y range {tr['yr']:.0f} x range {tr['xr']:.0f}")
out = run / "loot"
(out / f"residue_{a.out or a.find}.json").write_text(json.dumps(
    [{"mx": tr["mx"], "my": tr["my"], "n": len(tr["obs"]), "t0": tr["t0"], "t1": tr["t1"], "bob": bool(tr["bob"]),
      "yr": tr["yr"], "xr": tr["xr"], "w": tr["w"], "h": tr["h"]} for tr in still]), encoding="utf-8")
todo = sorted(bob, key=lambda tr: -len(tr["obs"]))[:a.sheet] + sorted([tr for tr in still if not tr["bob"]],
                                                                      key=lambda tr: -len(tr["obs"]))[:a.sheet // 2]
tiles, labels = [], []
for tr in todo:
    o = tr["obs"][len(tr["obs"]) // 2]
    f = frame(run, rows[o[0]]["frame"])
    cx, cy = int(o[4] + o[6] / 2), int(o[5] + o[7] / 2)
    x0, y0 = max(0, min(SW - 72, cx - 36)), max(0, min(PLAY_H - 72, cy - 36))
    tiles.append(f[y0:y0 + 72, x0:x0 + 72])
    labels.append(f"{'BOB' if tr['bob'] else 'still'} n{len(tr['obs'])} t{o[1]:.0f}")
if tiles:
    p = out / f"residue_{a.out or a.find}.png"
    cv2.imwrite(str(p), sheet(tiles, cols=10, labels=labels, scale=3))
    print("->", p)
