"""PLAN-loot.md S9: the product's drops (FrameFacts.drops, made by the live Perceiver) on the 9 native recordings vs
the reference (tools/loot/dropvote.py, eager) run on the SAME tick's inputs (the Perceiver's camera, expected scene,
world mask, the fit's explained pixels, our + the players' tag boxes, front planes, footholds).

    python tools/loot/drops_replay.py [--runs 154819_1,...] [--every 1] [--out product]

-> runs/loot_labels/replay_<OUT>/<run key>.jsonl (per saved frame: product drops, reference drops, drops_ms) and
   runs/loot_labels/finder_<OUT>.jsonl (the labelled frames' rows, keyed "<run key>/<frame>": drop_eval.py labels
   --finder finder_<OUT>.jsonl), + a summary: frames with identical facts (votes aside: the graph's tables differ),
   REST sets per frame (item, box) equal / differing (listed), feature / cell overflows.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "labels"))
from lootlib import Footholds, frame, map_of, ROOT, PLAY_H, SW  # noqa: E402
from pick import RUNS, T1  # noqa: E402


def front_planes(scene, C) -> dict:
    out = {}
    ax, ay = int(C[0]) - scene.x0, int(C[1]) - scene.y0
    for L, pl in scene.layers.items():
        m = np.zeros((PLAY_H, SW), bool)
        y0, x0, y1, x1 = max(0, ay), max(0, ax), min(pl.shape[0], ay + PLAY_H), min(pl.shape[1], ax + SW)
        if y1 > y0 and x1 > x0:
            m[y0 - ay:y1 - ay, x0 - ax:x1 - ax] = (pl[y0:y1, x0:x1] >= 128).cpu().numpy()
        out[L] = m
    return out


def strip(rows):
    return sorted(json.dumps({k: v for k, v in d.items() if k != "votes"}, sort_keys=True) for d in rows)


def rest_set(rows):
    return sorted((d["item"], d["f"], tuple(d["box"])) for d in rows if d["kind"] == "rest")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=",".join(RUNS))
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--out", default="product")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
    from run import bench_module, frames_module
    from dropvote import DropFinder as Ref, facts
    from maplebrain.perception.drops import PLAY_H as PH
    bench = bench_module()
    picks = json.loads((HERE / "labels" / "picks.json").read_text(encoding="utf-8"))
    want = {(p["run"], p["frame"]) for p in picks}
    out_dir = ROOT / "runs" / "loot_labels" / f"replay_{a.out}"
    out_dir.mkdir(parents=True, exist_ok=True)
    lab_rows, ref = [], None
    tot = {"frames": 0, "run": 0, "same": 0, "rest_same": 0, "rest_p": 0, "rest_r": 0, "none": 0}
    diffs, over = [], []
    for key in a.runs.split(","):
        run = ROOT / RUNS[key]
        mid = map_of(run)
        per = bench.build(mid)[0]
        fz, fitter, scene = per.drops, per.fitter, per.kit.scene
        if ref is None:
            ref = Ref(items=fz.items, cand_votes=fz.cfg.cand_votes)
        fh = Footholds(mid)
        frames = frames_module().Clip(run, run, mid).frames(0.0, T1.get(key, 1e9), a.every)
        t0 = time.time()
        with open(out_dir / f"{key}.jsonl", "w", encoding="utf-8") as fo:
            for n, name, t in frames:
                img = frame(run, name)
                per.observe(img, t)
                f = per.facts
                tot["frames"] += 1
                row = {"n": n, "frame": name, "t": round(t, 3), "C": f.scene_cam, "drops": f.drops,
                       "drops_ms": f.drops_ms}
                if f.drops is None:
                    tot["none"] += 1
                else:
                    C = tuple(f.scene_cam)
                    exp, known = scene.expected(C)
                    P = max(fitter.KH, fitter.KW)
                    taken = fitter.taken[P:P + PH, P:P + SW] if fitter.taken is not None else np.zeros((PH, SW), bool)
                    me_s = (f.tag[0] + f.tag[2] / 2, f.tag[1]) if f.tag is not None else None
                    feet = ([me_s] if me_s else []) + [(x + w / 2, y) for x, y, w, h in f.tags or []]
                    chars = np.zeros((PH, SW), bool)
                    for cx, fy in feet:
                        b = (cx - 42, fy - 90, cx + 42, fy + 22)
                        chars[max(0, int(b[1])):max(0, int(b[3])), max(0, int(b[0])):max(0, int(b[2]))] = True

                    def layer_of(sx, sy, C=C):
                        u = fh.under(sx + C[0], sy + C[1])
                        return u[1] if u is not None else None

                    r = [facts(d, C, fh) for d in ref.find(per.frame_u8, exp, known, per._world_ui(img.shape),
                                                           mob_taken=taken, chars=chars,
                                                           front=front_planes(scene, C), layer_of=layer_of)]
                    row["ref"] = r
                    tot["run"] += 1
                    tot["same"] += strip(r) == strip(f.drops)
                    rp, rr = rest_set(f.drops), rest_set(r)
                    tot["rest_p"] += len(rp)
                    tot["rest_r"] += len(rr)
                    if rp == rr:
                        tot["rest_same"] += 1
                    else:
                        diffs.append({"run": key, "frame": name, "t": round(t, 2),
                                      "only_product": [x for x in rp if x not in rr],
                                      "only_reference": [x for x in rr if x not in rp]})
                    ms = f.drops_ms or {}
                    if ms.get("feat", 0) > fz.cfg.NF or ms.get("feat2", 0) > fz.cfg.NF2 or ms.get("cands", 0) >= fz.cfg.NC:
                        over.append({"run": key, "frame": name, **ms})
                fo.write(json.dumps(row) + "\n")
                if (key, name) in want:
                    lab_rows.append({"frame": f"{key}/{name}", "drops": f.drops or []})
        print(f"{key}: map {mid}, {len(frames)} frames in {time.time() - t0:.0f} s", flush=True)
    with open(ROOT / "runs" / "loot_labels" / f"finder_{a.out}.jsonl", "w", encoding="utf-8") as fo:
        for r in lab_rows:
            fo.write(json.dumps(r) + "\n")
    (out_dir / "diffs.json").write_text(json.dumps({"tot": tot, "diffs": diffs, "over": over}, indent=1),
                                        encoding="utf-8")
    print(f"frames {tot['frames']}, drops run on {tot['run']} (no camera: {tot['none']}); facts identical (votes aside) "
          f"on {tot['same']}; REST sets equal on {tot['rest_same']} / {tot['run']} frames (REST sightings product "
          f"{tot['rest_p']}, reference {tot['rest_r']}); differing frames {len(diffs)}; overflow frames {len(over)}; "
          f"label rows {len(lab_rows)} / {len(want)}")
    for d in diffs[:40]:
        print("  ", d)
    for o in over[:20]:
        print("   overflow", o)


if __name__ == "__main__":
    main()
