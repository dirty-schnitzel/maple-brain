"""The fit (maplebrain/perception/fit.py, PLAN-fit-speed.md) offline, frame by frame (no tracker, no memory).

    python tools/perc/fit/run.py synth OUT [--loose]          synthetic set (synth.json truth) -> OUT/fit/synth.jsonl
    python tools/perc/fit/run.py labels RUN [--loose]         the labelled frames (labels.json v2, cams.json)
    python tools/perc/fit/run.py ghosts RUN --replay FILE [--live]   every frame with a weak track's sighting
                                    (compare.py's "weak": never a strong sighting; --live: the live run's own tracks,
                                    the cameras from FILE's scene_cam) -> the fit over the whole frame; the weak
                                    tracks' spots are kept in the rows ("spots") for sweep.py ghosts
    python tools/perc/fit/run.py clip RUN --replay FILE [--every N]   timing on a clip: every N-th frame with a
                                    scene camera in FILE (a gate replay)

No windows: the vote searches the whole frame. The tool calls Scene.expected() itself (live, D and the fit share one
per tick: 3.3); UI = hud.ui_mask without the chat rect (world at native; the user keeps the chat minimized). The
process is pinned to the performance cores (procperf, as the bench): ms are only meaningful with the game running.
Out rows = label_eval's track format ({"n", "mobs": [{"sx", "sy", "mob", "state", "src", "anim", "score",
"unseen"}]}) + per mob the fit's numbers ("fit") + "ms". --loose: permissive thresholds (seen 0.02, absent 1.0,
min_seen 10, cand_votes 8): the accepted set for tools/perc/fit/sweep.py to fit the rule and cand_votes on.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402

PLAY_H, SW = 700, 1366


def setup(map_id, cfg):
    import torch
    from maplebrain.perception import hud
    from maplebrain.perception.fit import Fitter
    from maplebrain.scene import Scene
    scene = Scene.load(map_id)
    ui = hud.ui_mask((768, SW)) > 0
    ui[630:PLAY_H, 285:850] = True        # the chat rect: world at native unless a chat line is drawn
    ui_t = torch.from_numpy(np.ascontiguousarray(ui[:PLAY_H])).to(scene.dev)
    return scene, ui_t, Fitter(scene, map_id, ROOT / "assets" / "mcw", cfg)


def run_frame(scene, ui_t, fitter, frame, C):
    import torch
    t0 = time.perf_counter()
    f = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(scene.dev)
    C = tuple(int(v) for v in C)
    exp, known = scene.expected(C)
    torch.cuda.synchronize()
    t1 = time.perf_counter()
    mobs = fitter.fit(f, C, exp, known, ui_t)
    rows = [{"sx": m.feet[0], "sy": m.feet[1], "mob": m.type, "state": "live", "src": "fit", "anim": m.pose,
             "score": m.seen, "unseen": 0, "fit": m.to_dict()} for m in mobs]
    return rows, {"exp": (t1 - t0) * 1000, **fitter.ms}


def cfg_of(a):
    from maplebrain.perception.fit import FitConfig
    c = FitConfig()
    if a.loose:
        c.seen_min, c.absent_max, c.min_seen, c.cand_votes = 0.02, 1.0, 10, 8
    for kv in a.set or []:
        k, v = kv.split("=")
        setattr(c, k, type(getattr(c, k))(float(v)) if not isinstance(getattr(c, k), bool) else v == "1")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("synth", "labels", "ghosts", "clip"))
    ap.add_argument("path")
    ap.add_argument("--loose", action="store_true")
    ap.add_argument("--set", nargs="*", help="FitConfig overrides k=v")
    ap.add_argument("--replay", type=Path, help="ghosts / clip: a replay with scene_cam per frame (the cameras; its "
                    "weak tracks are the spots unless --live)")
    ap.add_argument("--live", action="store_true", help="ghosts: the spots = the live run's own weak tracks")
    ap.add_argument("--every", type=int, default=1, help="clip: every N-th frame")
    ap.add_argument("--out")
    ap.add_argument("--n", type=int, default=0, help="only the first N frames")
    a = ap.parse_args()
    from maplebrain import procperf
    print(procperf.prefer_performance())
    cfg = cfg_of(a)
    path = Path(a.path)
    jobs = []                                                    # (n, frame loader, C, spots)
    if a.mode == "synth":
        meta = json.loads((path / "synth.json").read_text())
        map_id = meta["map"]
        for n, fr in meta["frames"].items():
            jobs.append((int(n), lambda fr=fr: cv2.imread(str(path / "frames" / fr["frame"])), fr["C"], ()))
    elif a.mode == "labels":
        map_id = rec.map_of(path)
        lab = json.loads((path / "labels.json").read_text())
        cams = json.loads((path / "labels" / "cams.json").read_text())
        for n in lab["frames"]:
            name = f"{int(n):06d}.png"
            if cams.get(name) is not None:
                jobs.append((int(n), lambda name=name: rec.read(path, name), cams[name], ()))
    elif a.mode == "clip":
        map_id = rec.map_of(path)
        rows = [json.loads(line) for line in open(a.replay, encoding="utf-8")]
        for r in [r for r in rows if r.get("scene_cam")][::a.every]:
            name = r.get("frame") or f"{r['n']:06d}.png"
            jobs.append((r["n"], lambda nm=name: rec.read(path, nm), r["scene_cam"], ()))
    else:
        sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
        from compare import live_rows, tracks
        map_id = rec.map_of(path)
        cams = {json.loads(line)["n"]: json.loads(line).get("scene_cam") for line in open(a.replay, encoding="utf-8")}
        rows = live_rows(path) if a.live else [json.loads(line) for line in open(a.replay, encoding="utf-8")]
        cls = tracks(rows)
        for r in rows:                                           # a weak track's sightings (not its coasting)
            weak = [(m["mob"], m["sx"], m["sy"]) for m in r.get("mobs") or []
                    if m.get("state") not in ("tentative", "offscreen") and m.get("src", "none") != "none"
                    and not cls[m["id"]]["real"]]
            if weak and cams.get(r["n"]):
                name = r.get("frame") or f"{r['n']:06d}.png"
                jobs.append((r["n"], lambda nm=name: rec.read(path, nm), cams[r["n"]], weak))
    if a.n:
        jobs = jobs[:a.n]
    scene, ui_t, fitter = setup(map_id, cfg)
    print(fitter.voter.stats())
    out = Path(a.out) if a.out else path / "fit" / f"{a.mode}{'_loose' if a.loose else ''}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    ms = []
    with open(out, "w", encoding="utf-8") as fo:
        for n, load, C, spots in jobs:
            frame = load()
            if frame is None:
                continue
            rows, m = run_frame(scene, ui_t, fitter, frame, C)
            ms.append(m)
            fo.write(json.dumps({"n": n, "mobs": rows, "ms": m, "spots": [list(s) for s in spots]}) + "\n")
    ms = ms[3:] or ms                                            # the first calls warm up
    pc = lambda k: (round(float(np.median([m[k] for m in ms])), 2),  # noqa: E731
                    round(float(np.percentile([m[k] for m in ms], 90)), 2))
    f = np.array([m["fit"] for m in ms])
    print(f"{len(ms)} frames -> {out}; fit ms p50 {np.median(f):.2f} p90 {np.percentile(f, 90):.2f} max {f.max():.2f}; "
          f"parts p50 / p90: vote {pc('vote')} stage 2 {pc('s2')} pick {pc('pick')} (expected() {pc('exp')}, D's); "
          f"cands {pc('cands')}, features {pc('feat')}")


if __name__ == "__main__":
    main()
