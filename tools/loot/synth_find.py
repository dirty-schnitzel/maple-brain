"""PLAN-loot.md S4: the prototype finder (dropvote.py: items.npz, the kinds of section 5) over a synthetic set.

    python tools/loot/synth_find.py SET [--out NAME] [--votes 16] [--no-fit]
        SET = an OUT of synth_drops.py (full frames) or tests/fixtures/synth_drops (crops; --fixture is detected)

Per frame, the inputs the live tick would have: the expected scene at the frame's camera (Scene.expected; the
fixture: its stored crop, outside the window frame = expected = 0), the world mask (lootlib.world_mask), the mob
fit's explained pixels (perception/fit.py Fitter on the frame, our body box from obs.me; --no-fit: none), the
characters' body boxes (synth.json `chars`), the front scenery per foothold layer (Scene.layers), the footholds
(assets/mcw map.json) -> SET/finder_<NAME>.jsonl, one row a frame: {frame, drops: [section 8's facts + kind], ms}.
The fixture run also stores the fit's explained pixels in SET/masks_fit.npz (packed bits) so a test can replay it.
Then: python tools/loot/drop_eval.py SET --finder finder_<NAME>.jsonl
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lootlib import Footholds, world_mask, PLAY_H, SW, ROOT  # noqa: E402
from dropvote import DropFinder, facts  # noqa: E402


def frame_inputs(set_dir: Path, name: str, f: dict, fixture: bool, scenes: dict, masks):
    """-> frame (768, SW, 3) uint8, exp (PLAY_H, SW, 3) float32 or None, known, world, front {L: bool plane}."""
    import torch
    if not fixture:
        img = cv2.imread(str(set_dir / "frames" / f["frame"]))
        sc = scenes[f["map"]]
        exp, known = sc.expected(tuple(f["C"]))
        exp, known = exp.float().cpu().numpy(), known.cpu().numpy()
        world = world_mask(f["map"], img.shape)
        front = {}
        ax, ay = int(f["C"][0]) - sc.x0, int(f["C"][1]) - sc.y0
        for L, pl in sc.layers.items():
            m = np.zeros((PLAY_H, SW), bool)
            y0, x0, y1, x1 = max(0, ay), max(0, ax), min(pl.shape[0], ay + PLAY_H), min(pl.shape[1], ax + SW)
            if y1 > y0 and x1 > x0:
                m[y0 - ay:y1 - ay, x0 - ax:x1 - ax] = (pl[y0:y1, x0:x1] >= 128).cpu().numpy()
            front[L] = m
        return img, exp, known, world, front
    x0, y0, x1, y1 = f["window"]
    h, w = y1 - y0, x1 - x0
    img = np.zeros((768, SW, 3), np.uint8)
    img[y0:y1, x0:x1] = cv2.imread(str(set_dir / "frames" / f["frame"]))
    exp = np.zeros((PLAY_H, SW, 3), np.float32)
    exp[y0:y1, x0:x1] = cv2.imread(str(set_dir / "exp" / f["frame"]))
    unpack = lambda k: np.unpackbits(masks[k])[:h * w].reshape(h, w).astype(bool)  # noqa: E731
    known = np.ones((PLAY_H, SW), bool)
    known[y0:y1, x0:x1] = unpack(f"{name}_known")
    world = np.zeros((PLAY_H, SW), bool)
    world[y0:y1, x0:x1] = unpack(f"{name}_world")
    front = {}
    for k in masks.files:
        if k.startswith(f"{name}_front_"):
            m = np.zeros((PLAY_H, SW), bool)
            m[y0:y1, x0:x1] = unpack(k)
            front[int(k.rsplit("_", 1)[1])] = m
    return img, exp, known, world, front


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("--out", default="before")
    ap.add_argument("--votes", type=int, default=16)
    ap.add_argument("--no-fit", action="store_true")
    a = ap.parse_args()
    import torch
    from maplebrain.scene import Scene
    from maplebrain.perception.fit import Fitter
    set_dir = Path(a.set)
    meta = json.loads((set_dir / "synth.json").read_text(encoding="utf-8"))
    fixture = bool(meta.get("fixture"))
    masks = np.load(set_dir / "masks.npz") if fixture else None
    maps = sorted({f["map"] for f in meta["frames"].values()})
    scenes = {m: Scene.load(m) for m in maps}
    fitters = {} if a.no_fit else {m: Fitter(scenes[m], m, ROOT / "assets" / "mcw") for m in maps}
    for ft in fitters.values():
        ft.warm()
    fhs = {m: Footholds(m) for m in maps}
    fz = DropFinder(cand_votes=a.votes)
    print(f"finder: {len(fz.poses)} pictures, built in {fz.build_s:.1f} s; {fz.voter.stats()}")
    dev = fz.dev
    fit_bits, ms_v, ms_c, t0 = {}, [], [], time.time()
    with open(set_dir / f"finder_{a.out}.jsonl", "w", encoding="utf-8") as fo:
        for name, f in meta["frames"].items():
            img, exp, known, world, front = frame_inputs(set_dir, name, f, fixture, scenes, masks)
            C = tuple(f["C"])
            ft = torch.from_numpy(np.ascontiguousarray(img)).to(dev)
            et = torch.from_numpy(exp).to(dev)
            kt = torch.from_numpy(known).to(dev)
            wt = torch.from_numpy(np.ascontiguousarray(world)).to(dev)
            taken = None
            if fitters:
                fitter = fitters[f["map"]]
                me = f.get("me")
                box = None if not me else (me[0] - 40, me[1] - 85, me[0] + 40, me[1] + 30)
                fitter.fit(ft[:PLAY_H], C, et, kt, wt, box)
                Pd = max(fitter.KH, fitter.KW)
                taken = (fitter.taken[Pd:Pd + PLAY_H, Pd:Pd + SW].copy() if fitter.taken is not None
                         else np.zeros((PLAY_H, SW), bool))
                if fixture:
                    x0, y0, x1, y1 = f["window"]
                    fit_bits[f"{name}_taken"] = np.packbits(taken[y0:y1, x0:x1])
            chars = np.zeros((PLAY_H, SW), bool)
            for b in f.get("chars") or []:
                chars[max(0, int(b[1])):max(0, int(b[3])), max(0, int(b[0])):max(0, int(b[2]))] = True
            fh = fhs[f["map"]]

            def layer_of(sx, sy, C=C, fh=fh):
                u = fh.under(sx + C[0], sy + C[1])
                return u[1] if u is not None else None

            drops = fz.find(ft, et, kt, wt, mob_taken=taken, chars=chars, front=front, layer_of=layer_of)
            ms_v.append(fz.ms["vote"])
            ms_c.append(fz.ms["check"])
            fo.write(json.dumps({"frame": name, "drops": [facts(d, C, fh) for d in drops],
                                 "ms": {k: round(v, 2) if isinstance(v, float) else v for k, v in fz.ms.items()}})
                     + "\n")
    if fixture and fit_bits:
        np.savez_compressed(set_dir / "masks_fit.npz", **fit_bits)
    print(f"{set_dir}: {len(meta['frames'])} frames in {time.time() - t0:.0f} s; vote ms p50 {np.median(ms_v):.2f}, "
          f"check p50 {np.median(ms_c):.2f} (unpinned: not a timing gate) -> finder_{a.out}.jsonl")


if __name__ == "__main__":
    main()
