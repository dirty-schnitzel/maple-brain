"""The fit (maplebrain/perception/fit.py, PLAN-perception.md step 3.2) offline, frame by frame (no tracker, no memory).

    python tools/perc/fit/run.py synth OUT [--loose]          synthetic set (synth.json truth) -> OUT/fit/fit.jsonl
    python tools/perc/fit/run.py labels RUN [--loose]         the labelled frames (labels.json v2, cams.json)
    python tools/perc/fit/run.py ghosts RUN --replay FILE [--live]   every frame with a weak track's sighting
                                    (compare.py's "weak": never a strong sighting; --live: the live run's own tracks,
                                    the cameras from FILE's scene_cam) -> fit at D + a window at each weak track's spot
                                    (its type: as a track prediction)

Windows = D's patches (Scene.diff + patches, the live code) at the frame's camera; --tracks FILE adds a window
around every confirmed track of a replay on that frame (its type) - the "track prediction" windows.
Out rows = label_eval's track format ({"n", "mobs": [{"sx", "sy", "mob", "state", "src", "anim", "score",
"unseen"}]}) + per mob the fit's numbers ("fit") + "ms". --loose: permissive thresholds (seen 0.05, absent 1.0,
min_seen 10): the accepted set for tools/perc/fit/sweep.py to fit seen_min / absent_max on.
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
    ui_t = torch.from_numpy(np.ascontiguousarray(ui[:PLAY_H])).to(scene.dev)
    return scene, ui_t, Fitter(scene, map_id, ROOT / "assets" / "mcw", cfg)


def body_box(fitter, tid, fx, fy, pad=16):
    b = fitter.banks[tid]
    return fx - b.L - pad, fy - b.T - pad, b.KW + 2 * pad, b.KH + 2 * pad


def run_frame(scene, ui_t, fitter, frame, C, extra=()):
    import torch
    from maplebrain.perception.fit import Window, windows_from_patches
    from maplebrain.scene import patches
    t0 = time.perf_counter()
    f = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(scene.dev)
    ps = patches(scene.diff(f, tuple(int(v) for v in C), tol=4, mask=ui_t))
    torch.cuda.synchronize()
    t1 = time.perf_counter()
    wins = windows_from_patches(ps) + [Window(*body_box(fitter, tid, x, y), types=(tid,), src="track")
                                       for tid, x, y in extra if tid in fitter.banks]
    mobs = fitter.fit(f, C, wins, ui_t)
    rows = [{"sx": m.feet[0], "sy": m.feet[1], "mob": m.type, "state": "live", "src": "fit", "anim": m.pose,
             "score": m.seen, "unseen": 0, "fit": m.to_dict()} for m in mobs]
    return rows, {"d": (t1 - t0) * 1000, **fitter.ms, "windows": len(wins), "patches": len(ps)}


def cfg_of(a):
    from maplebrain.perception.fit import FitConfig
    c = FitConfig()
    if a.loose:
        c.seen_min, c.absent_max, c.min_seen = 0.05, 1.0, 10
    for kv in a.set or []:
        k, v = kv.split("=")
        setattr(c, k, type(getattr(c, k))(float(v)) if not isinstance(getattr(c, k), bool) else v == "1")
    return c


def tracks_of(path: Path) -> dict:
    out = {}
    if path is None:
        return out
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        out[r["n"]] = [(t["mob"], t["sx"], t["sy"]) for t in r.get("mobs", r.get("tracks")) or []
                       if t.get("state") != "tentative"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("synth", "labels", "ghosts"))
    ap.add_argument("path")
    ap.add_argument("--loose", action="store_true")
    ap.add_argument("--set", nargs="*", help="FitConfig overrides k=v")
    ap.add_argument("--tracks", type=Path, help="a replay's jsonl: windows at its confirmed tracks")
    ap.add_argument("--replay", type=Path, help="ghosts: a replay with scene_cam per frame (the cameras; its weak "
                    "tracks are the spots unless --live)")
    ap.add_argument("--live", action="store_true", help="ghosts: the spots = the live run's own weak tracks")
    ap.add_argument("--out")
    ap.add_argument("--n", type=int, default=0, help="only the first N frames")
    a = ap.parse_args()
    cfg = cfg_of(a)
    path = Path(a.path)
    extra = tracks_of(a.tracks)
    jobs = []                                                    # (n, frame loader, C, extra spots)
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
                jobs.append((int(n), lambda name=name: rec.read(path, name), cams[name], extra.get(int(n), ())))
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
    out = Path(a.out) if a.out else path / "fit" / f"{a.mode}{'_loose' if a.loose else ''}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    ms = []
    with open(out, "w", encoding="utf-8") as fo:
        for n, load, C, spots in jobs:
            frame = load()
            if frame is None:
                continue
            rows, m = run_frame(scene, ui_t, fitter, frame, C, spots)
            ms.append(m)
            fo.write(json.dumps({"n": n, "mobs": rows, "ms": m, "spots": [list(s) for s in spots]}) + "\n")
    f = np.array([m["fit"] for m in ms[3:] or ms])
    d = np.array([m["d"] for m in ms[3:] or ms])
    print(f"{len(ms)} frames -> {out}; fit ms p50 {np.median(f):.1f} p90 {np.percentile(f, 90):.1f} max {f.max():.1f}; "
          f"D ms p50 {np.median(d):.1f}; windows p50 {np.median([m['windows'] for m in ms]):.0f}, "
          f"cands p50 {np.median([m['cands'] for m in ms]):.0f}")


if __name__ == "__main__":
    main()
