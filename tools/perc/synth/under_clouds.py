"""Mobs under the weather clouds, truth by construction (PLAN-moving-scenery.md step 5's synthetic gate). maplebrain's
own code end to end: perception/clouds.py's layer and undo, fit.py with the cloud (the tolerant vote, the cloud
numbers). The reference it ports: tools/perc/scenery/synth_clouds.py (the prototype's, measurement 5).

One placement: where a frame shows only the scene (the expected picture explains >= 97 % of the box, valid) a mob
sprite of the map is pasted standing on a foothold (a stand / move pose, opaque), then ONE cloud picture (random
picture, opacity 0.45-0.88, placed so that a pixel of the given thickness class sits on the mob) is blended over it the
way the client does (frame = under + o a (s - under), rounded). Judged three ways: the mob alone (`none`, the fit's own
recall there), the cloud left in (`raw`), the cloud undone + the fit's cloud handling (`undone` = the live path). A mob
counts as found with its type within 3 px of its feet; `extra` = mobs the fit gives that are neither the pasted one
nor on the base frame (within 6 px; the base = the fit on the frame as it is + the live fit with the frame's own
clouds followed and undone - a real mob under a real cloud is not a false one): false ones. Classes by the mean cloud alpha over the mob's opaque pixels.

    python tools/perc/synth/under_clouds.py CAP [--n 600] [--every 3]     (the gate, real frames of a capture)
pytest (tests/test_under_clouds.py) runs a fixed-seed set on the scene's own expected picture (no footage)."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
BINS = ((0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9))
PLAY_H, SW = 700, 1366


def footholds(map_id: int, assets: Path) -> list:
    m = json.loads((Path(assets) / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
    return [f for f in (m.get("footholds") or {}).values() if f["x1"] != f["x2"]]


def standing(fz) -> list:
    """The fit's stand / move poses (g, Pose)."""
    return [(g, p) for g, p in enumerate(fz.poses) if p.pose.split("_")[0] in ("stand", "move")]


def place(rnd, fz, cl, fhs, poses, f, C, expl, base, tries: int = 6):
    """One mob + one cloud over it on frame `f` (uint8 (>= PLAY_H, SW, 3) tensor) at camera C; `expl`: bool (PLAY_H,
    SW) the frame shows the scene there (explained and valid); `base`: the fit's mobs on `f` (kept away from). -> a
    placement dict (frames `mob` = the mob only, `frame` = + the cloud) or None (no spot in `tries`)."""
    torch = fz.torch
    for _ in range(tries):
        fh = rnd.choice(fhs)
        tt = rnd.random()
        fx = int(round(fh["x1"] + tt * (fh["x2"] - fh["x1"]) - C[0]))
        fy = int(round(fh["y1"] + tt * (fh["y2"] - fh["y1"]) - C[1]))
        g, p = rnd.choice(poses)
        h, w = p.pic.shape[:2]
        bx, by = fx - p.ox, fy - p.oy
        if bx < 10 or by < 10 or bx + w > SW - 10 or by + h > PLAY_H - 10:
            continue
        if float(expl[by:by + h, bx:bx + w].float().mean()) < 0.97:
            continue
        if any(abs(mb.feet[0] - fx) < 80 and abs(mb.feet[1] - fy) < 60 for mb in base):
            continue
        pic = torch.from_numpy(np.ascontiguousarray(p.pic)).to(fz.dev).float()
        pa = pic[..., 3:4] / 255.0
        fm = f[:PLAY_H].clone()
        fm[by:by + h, bx:bx + w] = (fm[by:by + h, bx:bx + w].float() * (1 - pa) + pic[..., :3] * pa).round().byte()
        k = rnd.randrange(len(cl.sprites))
        o = rnd.uniform(0.45, 0.88)
        s, al = cl.sprites[k]
        ys, xs = (al >= rnd.choice([0.2, 0.5, 0.8, 0.95]) * float(al.max())).nonzero(as_tuple=True)
        q = rnd.randrange(len(ys))
        cx, cy = fx - int(xs[q]), by + h // 2 - int(ys[q])
        P, A = cl.layer([(k, cx, cy, o)])
        fcl = (fm.half() * (1 - A) + P).float().round().clamp(0, 255).byte()
        op = pic[..., 3] == 255
        sub = A[by:by + h, bx:bx + w, 0].float()[op]
        return {"type": p.type, "pose": p.pose, "facing": p.facing, "feet": (fx, fy), "k": k, "o": o, "cx": cx,
                "cy": cy, "am": float(sub.mean()), "amx": float(sub.max()), "mob": fm, "frame": fcl, "P": P, "A": A}
    return None


def _found(mobs, pl) -> bool:
    return any(m.type == pl["type"] and abs(m.feet[0] - pl["feet"][0]) <= 3 and abs(m.feet[1] - pl["feet"][1]) <= 3
               for m in mobs)


def _extra(mobs, pl, base) -> list:
    return [m for m in mobs if not (m.type == pl["type"] and abs(m.feet[0] - pl["feet"][0]) <= 3
                                    and abs(m.feet[1] - pl["feet"][1]) <= 3)
            and not any(b.type == m.type and abs(b.feet[0] - m.feet[0]) <= 6 and abs(b.feet[1] - m.feet[1]) <= 6
                        for b in base)]


def judge(fz, cl, pl, C, E, known, ui, base, ways=("none", "raw", "undone")) -> dict:
    """The fit on the placement, each way of `ways` -> {way: found, way + "_extra": false mobs (+ "_false" their
    (type, pose, facing, feet, n_seen, seen, absent)), "mob": the undone fit's mob at the feet (its cloud numbers) or
    None}."""
    out = {}
    for way in ways:
        if way == "none":
            mobs = fz.fit(pl["mob"], C, E, known, ui)
        elif way == "raw":
            mobs = fz.fit(pl["frame"], C, E, known, ui)
        else:
            cl.P, cl.A = pl["P"], pl["A"]
            und, thick = cl.undo(pl["frame"])
            mobs = fz.fit(und, C, E, known & ~thick, ui, cloud=(pl["A"][..., 0].float(), thick))
            out["mob"] = next((m for m in mobs if m.type == pl["type"] and abs(m.feet[0] - pl["feet"][0]) <= 3
                               and abs(m.feet[1] - pl["feet"][1]) <= 3), None)
        ex = _extra(mobs, pl, base)
        out[way], out[way + "_extra"] = _found(mobs, pl), len(ex)
        out[way + "_false"] = [(m.type, m.pose, m.facing, m.feet, m.n_seen, m.seen, m.absent) for m in ex]
    return out


def table(res: list, ways=("none", "raw", "undone")) -> list:
    """Per thickness class (BINS + all): (lo, hi, n, {way: found %}, {way: false mobs})."""
    rows = []
    for lo, hi in BINS + ((0.0, 1.01),):
        sel = [r for r in res if lo <= r["am"] < hi]
        if sel:
            rows.append((lo, hi, len(sel), {w: 100 * sum(r[w] for r in sel) / len(sel) for w in ways},
                         {w: sum(r[w + "_extra"] for r in sel) for w in ways}))
    return rows


def main():
    import argparse
    import random
    sys.path.append(str(ROOT / "tools" / "perc" / "scenery"))
    import torch
    import cam as camlib
    import msl
    import proto
    from maplebrain.config import Perception
    from maplebrain.perception import hud
    from maplebrain.perception.clouds import Clouds
    from maplebrain.perception.fit import Fitter
    from maplebrain.scene import MoverFollow, Scene
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--every", type=int, default=3, help="frames followed (the movers): every K-th")
    ap.add_argument("--try-every", type=int, default=4, help="a placement tried on every K-th followed frame")
    a = ap.parse_args()
    msl.guard()
    rnd = random.Random(7)
    c = msl.clip(a.cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(a.cap)["rows"] if r[3] is not None][::a.every]
    sc = Scene.load(c.map_id)
    fol = MoverFollow(sc) if any(b.get("mover") is not None for b, _ in sc.backs) else None
    cl = Clouds(sc.dev, Perception())             # the placed cloud's layer + undo
    real = Clouds(sc.dev, Perception())           # the frame's own clouds, followed (the base: what the live path sees)
    assets = ROOT / "assets" / "mcw"
    fz = Fitter(sc, c.map_id, assets)
    fz.warm()
    fhs, poses = footholds(c.map_id, assets), standing(fz)
    ui, res, n_try = None, [], 0
    for j, r in enumerate(cams):
        if len(res) >= a.n:
            break
        i = r[0]
        img = c.read(fr[i][1])
        if ui is None:
            mk = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
            mk = mk.copy()
            x0, y0, x1, y1 = hud.CHAT_WORLD
            mk[y0:y1, x0:x1] = True
            ui = torch.from_numpy(np.ascontiguousarray(mk[:PLAY_H])).to(sc.dev)
        f = proto.frame_tensor(img, sc.dev)
        C = (r[3], r[4])
        X = fol.update(f, C, fr[i][2]) if fol is not None else None
        E, known = sc.expected(C, X=X)
        valid = known & ui
        on = real.update(f, E, valid, C, fr[i][2])
        if j % a.try_every:
            continue
        expl = ((f[:PLAY_H].float() - E).abs().amax(dim=2) <= 4) & valid
        base = fz.fit(f, C, E, known, ui)
        if on:                                    # + the mobs the live path finds under the frame's own clouds
            und, thick = real.undo(f)
            base += fz.fit(und, C, E, known & ~thick, ui, cloud=(real.A[..., 0].float(), thick))
        n_try += 1
        pl = place(rnd, fz, cl, fhs, poses, f, C, expl, base)
        if pl is None:
            continue
        out = judge(fz, cl, pl, C, E, known, ui, base)
        m = out.pop("mob")
        res.append({"i": i, **{k: pl[k] for k in ("type", "pose", "facing", "feet", "k", "o", "am", "amx")}, **out,
                    "cloud": None if m is None else m.cloud, "n_cloud": None if m is None else m.n_cloud})
        if len(res) % 100 == 0:
            print(" ", len(res), "placements", flush=True)
    print(f"{a.cap}: {len(res)} placements ({n_try} frames tried)")
    print("  mean cloud alpha over the mob | placements | found: no cloud | cloud left in | undone (live) | false mobs "
          "(none / raw / undone)")
    for lo, hi, n, fd, ex in table(res):
        print(f"   {lo:.1f}-{min(hi, 1.0):.1f}  {n:5d}   {fd['none']:6.1f} %  {fd['raw']:6.1f} %  {fd['undone']:6.1f} %   "
              f"{ex['none']} / {ex['raw']} / {ex['undone']}")
    got = [r for r in res if r["undone"] and r["cloud"] is not None]
    if got:
        d = [abs(r["cloud"] - r["am"]) for r in got]
        print(f"  the found mobs' `cloud` (mean alpha over SEEN pixels) vs the truth over all opaque pixels: |diff| p50 "
              f"{np.median(d):.3f} p90 {np.percentile(d, 90):.3f}; n_cloud > 0 on {sum(r['n_cloud'] > 0 for r in got)}")
    for r in res:
        for w in ("none", "raw", "undone"):
            for x in r[w + "_false"]:
                print(f"  false ({w}): frame {r['i']}, placed {r['type']} {r['pose']} {r['facing']} at {r['feet']} "
                      f"(cloud {r['am']:.2f}); the fit's extra {x}")
    (msl.OUT / f"under_clouds_{a.cap.replace('#', '_')}.json").write_text(json.dumps(res))


if __name__ == "__main__":
    main()
