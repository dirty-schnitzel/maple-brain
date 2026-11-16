"""D's patches measured (PLAN-perception.md step 3.1): do the blobs of D = frame - expected scene (scene.Scene.diff +
scene.patches, the live code) hold every mob, and how much work are they for the fit (3.2)?

    python tools/perc/dcheck.py synth OUT             synthetic set (tools/perc/synth/make.py, synth.json truth)
    python tools/perc/dcheck.py labels RUN            by-eye labels (RUN/labels.json v2, cameras RUN/labels/cams.json)
    python tools/perc/dcheck.py clips [CLIP ...]      the gate clips' cached replays of the working tree (gate.py):
                                                      patches per frame, area p50 / p90, D's ms

A mob is IN a patch when one patch's box holds >= 90 % of its body box (on screen, outside the UI) - the window the
fit will search; TOUCHED when any patch box overlaps its body box. Synthetic: the exact box; labels: the type's
stand sprite at the labelled feet (client lt / rb). Mob-free synthetic frames: every patch should lie at our blob /
the UI ("dontcare") or at a pasted distractor; the rest is listed.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
import frames as rec  # noqa: E402

PLAY_H, SW = 700, 1366
CLASSES = {"": "clear", "e": "effect", "p": "player", "s": "scenery", "u": "ui", "f": "fade", "d": "dying",
           "x": "edge", "h": "hit"}


def setup(map_id):
    import torch
    from maplebrain.perception import hud
    from maplebrain.scene import Scene
    scene = Scene.load(map_id)
    ui = hud.ui_mask((768, SW)) > 0
    return scene, ui, torch.from_numpy(np.ascontiguousarray(ui[:PLAY_H])).to(scene.dev)


def d_patches(scene, ui_t, frame, C, tol=4):
    from maplebrain.scene import patches
    return patches(scene.diff(frame, tuple(int(v) for v in C), tol=tol, mask=ui_t))


def inter(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def judge(box, ps, ui):
    """(in, touched) for a body box (x, y, w, h) against patches: share of its world pixels inside one patch box."""
    x0, y0 = max(0, box[0]), max(0, box[1])
    x1, y1 = min(SW, box[0] + box[2]), min(PLAY_H, box[1] + box[3])
    if x1 <= x0 or y1 <= y0:
        return None
    world = ui[y0:y1, x0:x1]
    n = int(world.sum())
    if n == 0:
        return None
    best, touched = 0.0, False
    for p in ps:
        px0, py0 = max(x0, p[0]), max(y0, p[1])
        px1, py1 = min(x1, p[0] + p[2]), min(y1, p[1] + p[3])
        if px1 > px0 and py1 > py0:
            touched = True
            best = max(best, world[py0 - y0:py1 - y0, px0 - x0:px1 - x0].sum() / n)
    return best >= 0.9, touched


def pct(a, b):
    return f"{100 * a / b:5.1f} %" if b else "    -"


def table(name, rows):
    print(f"{name:<14}{'mobs':>6}{'in':>9}{'touched':>10}")
    for k, v in rows:
        print(f"{k:<14}{len(v):>6}{pct(sum(i for i, _ in v), len(v)):>9}{pct(sum(t for _, t in v), len(v)):>10}")


def synth(out: Path, tol: int):
    meta = json.loads((out / "synth.json").read_text())
    scene, ui, ui_t = setup(meta["map"])
    by_case, by_vis, by_op, missed, odd, free_n, n_patch = defaultdict(list), defaultdict(list), defaultdict(list), [], [], 0, []
    bins = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
    for n, fr in meta["frames"].items():
        img = cv2.imread(str(out / "frames" / fr["frame"]))
        C = fr["C"]
        if "window" in fr:                       # a cropped frame (the pytest set): the window's own camera
            x0, y0, x1, y1 = fr["window"]
            exp, _ = scene.expected(tuple(int(v) for v in C))       # outside it: the scene itself (D = 0 there)
            full = exp.round().clamp(0, 255).byte().cpu().numpy()
            full[y0:y1, x0:x1] = img
            img = full
        ps = d_patches(scene, ui_t, img, C, tol)
        n_patch.append(len(ps))
        for m in fr["mobs"]:
            j = judge(m["box"], ps, ui)
            if j is None:
                continue
            by_case[m["cls"] or fr["case"]].append(j)
            by_vis[next(f"{a:.1f}-{b:.1f}" for a, b in bins if a <= m["vis"] < b)].append(j)
            if m["opacity"] < 1:
                by_op[next(f"{a:.1f}-{b:.1f}" for a, b in bins if a <= m["opacity"] < b)].append(j)
            if not j[0]:
                missed.append((n, fr["case"], m["pose"], round(m["vis"], 2), round(m["opacity"], 2), m["box"], j[1]))
        if fr["case"] == "free":
            free_n += 1
            ok = [(b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in fr["dontcare"]] + \
                 [tuple(d[:4]) for d in fr.get("distractors", [])]
            for p in ps:
                if not any(inter(p, b) > 0 for b in ok):
                    odd.append((n, p))
    allm = [j for v in by_case.values() for j in v]
    print(f"{len(meta['frames'])} frames, {len(allm)} mobs; patches per frame p50 {np.median(n_patch):.0f}, "
          f"max {max(n_patch)}")
    table("all", [("all", allm)])
    table("case", sorted(by_case.items()))
    table("visible", sorted(by_vis.items()))
    table("opacity<1", sorted(by_op.items()))
    print(f"not in a patch: {len(missed)}")
    for r in missed:
        print("  n{} {} {} vis {} op {} box {} touched {}".format(*r))
    print(f"mob-free frames {free_n}: patches away from our blob / UI / distractors: {len(odd)}")
    for n, p in odd:
        print(f"  n{n} {p}")


def body(type_id, cache={}):
    """(left, top, w, h) of the type's first stand frame relative to its feet (the client's lt / rb)."""
    if type_id not in cache:
        mj = json.loads((ROOT / "assets" / "mcw" / "mobs" / str(type_id) / "mob.json").read_text(encoding="utf-8"))
        f = mj["frames"]["stand"][0]
        cache[type_id] = (f["lt"][0], f["lt"][1], f["rb"][0] - f["lt"][0], f["rb"][1] - f["lt"][1])
    return cache[type_id]


def labels(run: Path, tol: int):
    sys.path.insert(0, str(ROOT / "tools" / "perc" / "labels"))
    from patches import map_of
    L = json.loads((run / "labels.json").read_text())
    cams = json.loads((run / "labels" / "cams.json").read_text())
    pick = {str(p["n"]): p["frame"] for p in json.loads(
        (ROOT / "tools" / "perc" / "labels" / f"{run.name}_pick.json").read_text())["frames"]}
    scene, ui, ui_t = setup(map_of(run))
    by_cls, missed, n_patch = defaultdict(list), [], []
    for n, fr in L["frames"].items():
        name = pick.get(str(n))
        C = cams.get(name)
        if C is None:
            continue
        img = rec.read(run, name)
        ps = d_patches(scene, ui_t, img, C, tol)
        n_patch.append(len(ps))
        for m in fr["mobs"]:
            l, t, w, h = body(m["type"])
            j = judge((m["feet"][0] + l, m["feet"][1] + t, w, h), ps, ui)
            if j is None:
                continue
            by_cls["all"].append(j)
            for c in m["cls"] or "c":
                by_cls[CLASSES.get(c if c != "c" else "", c)].append(j)
            if not j[0]:
                missed.append((n, m["type"], m["cls"] or "-", m["feet"], j[1]))
    print(f"{len(n_patch)} frames; patches per frame p50 {np.median(n_patch):.0f}, max {max(n_patch)}")
    table("class", sorted(by_cls.items(), key=lambda kv: -len(kv[1])))
    print(f"not in a patch: {len(missed)}")
    for r in missed:
        print("  n{} {} {} feet {} touched {}".format(*r))


def clips(names):
    import gate
    fp = gate.fingerprint(None)
    print(f"working tree fingerprint {fp}")
    print(f"{'clip':<10}{'frames':>7}{'D on':>7}{'patches p50':>12}{'p90':>5}{'max':>5}{'area p50':>9}{'p90':>7}"
          f"{'sum p50':>8}{'p90':>7}{'diff ms p50':>12}{'p90':>5}{'cc ms p50':>10}{'p90':>5}")
    for c in names or list(gate.CLIPS):
        f = ROOT / gate.CLIPS[c][0] / "replay" / f"fp_{fp}_{c}.jsonl"
        if not f.exists():
            print(f"{c:<10} not replayed for this fingerprint (gate.py first)")
            continue
        rows = [json.loads(l) for l in open(f, encoding="utf-8")]
        on = [r for r in rows if r.get("patches") is not None]
        if not on:
            print(f"{c:<10}{len(rows):>7}{0:>7}")
            continue
        npf = [len(r["patches"]) for r in on]
        area = [p[2] * p[3] for r in on for p in r["patches"]]
        tot = [sum(p[2] * p[3] for p in r["patches"]) for r in on]
        dm = [r["ms"].get("diff", 0) for r in on]
        cm = [r["ms"].get("patches", 0) for r in on]
        q = lambda v, p: np.percentile(v, p) if v else 0        # noqa: E731
        print(f"{c:<10}{len(rows):>7}{len(on):>7}{q(npf, 50):>12.0f}{q(npf, 90):>5.0f}{max(npf):>5}"
              f"{q(area, 50):>9.0f}{q(area, 90):>7.0f}{q(tot, 50):>8.0f}{q(tot, 90):>7.0f}"
              f"{q(dm, 50):>12.1f}{q(dm, 90):>5.1f}{q(cm, 50):>10.1f}{q(cm, 90):>5.1f}")
    print("area = a patch's box w x h (the fit's window); sum = all boxes of a frame")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("synth", "labels", "clips"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--tol", type=int, default=4)
    a = ap.parse_args()
    if a.mode == "synth":
        synth(Path(a.args[0]), a.tol)
    elif a.mode == "labels":
        labels(Path(a.args[0]), a.tol)
    else:
        clips(a.args)


if __name__ == "__main__":
    main()
