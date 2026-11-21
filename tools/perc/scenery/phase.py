"""Measurement 1: where is each moving (type 4-7) background layer on each frame?
    python phase.py CAP [--every K] [--max N]
Per frame, per moving layer: the horizontal phase p (0..cx-1) and the vertical offset dy from the static formula's
place at which the layer's OPAQUE pixels show their own colour in the frame (share within tol), searched over every
phase x DYS. A layer's opaque pixels do not depend on what is drawn under it, so each layer is measured alone.
-> out/phase/<cap>.json rows [i, t, Cx, Cy, [[p, share, n, second-best phase's share, dy, second-best dy's share]]]
Screen x of the picture's left edge = p (mod cx); y = scene.back_pos's + dy."""
import argparse
import json

import cv2
import numpy as np
import torch

import cam as camlib
import msl
from maplebrain.scene import MOVING, back_pos

DYS = (-2, -1, 0, 1, 2)


def layer_pics(scene):
    """[(index, b, pic uint8 (ph, cx, 4) padded / cropped to the tiling period)] of the moving layers."""
    out = []
    for i, (b, t) in enumerate(scene.backs):
        if b["type"] not in MOVING:
            continue
        pic = cv2.imread(str(msl.ROOT / "assets" / "scene" / "backs" / b["file"]), cv2.IMREAD_UNCHANGED)
        if b.get("flip"):
            pic = pic[:, ::-1]
        ph, pw = pic.shape[:2]
        cx = b["cx"] or pw
        buf = np.zeros((ph, cx, 4), np.uint8)
        buf[:, :min(cx, pw)] = pic[:, :min(cx, pw)]
        out.append((i, b, torch.from_numpy(np.ascontiguousarray(buf)).to(scene.dev)))
    return out


def one(scene, b, pic, frame_t, tiles, sy, tol, sub):
    """The best phase of one layer with its picture's top at screen row `sy` -> (phase, share, n, second share)."""
    ph, cx = pic.shape[:2]
    if b["type"] in (6, 7):                                            # tiled vertically too
        rows = torch.arange(0, msl.PLAY_H, sub, device=scene.dev)
        prow = (rows - sy) % (b["cy"] or ph)
        ok_r = prow < ph
        rows, prow = rows[ok_r], prow[ok_r]
    else:
        r0, r1 = max(0, sy), min(msl.PLAY_H, sy + ph)
        if r1 - r0 < 8:
            return None, 0.0, 0, 0.0
        rows = torch.arange(r0, r1, sub, device=scene.dev)
        prow = rows - sy
    xs = torch.arange(0, msl.SW, sub, device=scene.dev)
    S = frame_t[rows][:, xs].int()                                     # (R, X, 3)
    free = ~tiles[rows][:, xs]                                         # (R, X)
    P = pic[prow]                                                      # (R, cx, 4)
    scores = []
    for p0 in range(0, cx, 64):
        ps = torch.arange(p0, min(cx, p0 + 64), device=scene.dev)
        idx = (xs[None, :] - ps[:, None]) % cx                         # (B, X)
        Q = P[:, idx]                                                  # (R, B, X, 4)
        op = (Q[..., 3] == 255) & free[:, None, :]
        hit = ((Q[..., :3].int() - S[:, None]).abs().amax(dim=3) <= tol) & op
        n = op.sum(dim=(0, 2)).float()
        scores.append(torch.stack([hit.sum(dim=(0, 2)).float() / n.clamp(min=1), n]))
    sc = torch.cat(scores, dim=1)
    k = int(sc[0].argmax())
    far = sc[0].clone()
    far[torch.arange(cx, device=scene.dev).sub(k).abs().remainder(cx - 4) <= 4] = 0     # not the peak's neighbours
    return k, round(float(sc[0, k]), 4), int(sc[1, k]), round(float(far.max()), 4)


def measure(scene, layers, frame_t, C, tol=4, sub=2, dys=DYS):
    res = []
    tiles = scene._crop(C, msl.SW, msl.PLAY_H)[..., 3] > 0            # tiles / objects draw over every back
    for i, b, pic in layers:
        _, sy = back_pos(b, C)
        cands = [one(scene, b, pic, frame_t, tiles, sy + dy, tol, sub) + (dy,) for dy in dys]
        best = max(cands, key=lambda x: x[1])
        res.append(list(best) + [sorted(x[1] for x in cands)[-2]])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--max", type=int, default=10 ** 9)
    ap.add_argument("--sub", type=int, default=2)
    a = ap.parse_args()
    msl.guard()
    c = msl.clip(a.cap)
    fr = c.frames()
    cams = {r[0]: r for r in camlib.cams(a.cap)["rows"]}
    scene = msl.scene_of(c.map_id)
    layers = layer_pics(scene)
    print(c.map_id, len(fr), "frames;", len(layers), "moving layers:",
          [(i, b["file"], b["type"], b["rx"], b["cx"] or b["size"][0]) for i, b, _ in layers], flush=True)
    out = []
    for i in range(0, len(fr), a.every):
        if len(out) >= a.max:
            break
        r = cams.get(i)
        if r is None or r[3] is None:
            continue
        n, name, t = fr[i]
        img = c.read(name)
        f = torch.from_numpy(np.ascontiguousarray(img[:msl.PLAY_H])).to(scene.dev)
        res = measure(scene, layers, f, (r[3], r[4]), sub=a.sub)
        out.append([i, t, r[3], r[4], res])
        if len(out) % 25 == 0:
            print(" ", len(out), "frames", [(x[0], x[1], x[4]) for x in res], flush=True)
    p = msl.OUT / "phase" / f"{a.cap.replace('#', '_')}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({"cap": a.cap, "map": c.map_id, "layers": [[i, b] for i, b, _ in layers], "rows": out}))
    print("->", p)


if __name__ == "__main__":
    main()
