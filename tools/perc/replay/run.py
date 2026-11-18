"""Tracker replay: the live Perceiver (tools/perf/bench.build = runner._load_map) over a recorded
run's saved frames -> the tracks of every frame. The gate of every perception change: old code vs new code on the
same frames (compare.py).

    python tools/perc/replay/run.py RUN                           # the working tree -> RUN/replay/work.jsonl
    python tools/perc/replay/run.py RUN --old HEAD                # maplebrain/ as committed at HEAD -> RUN/replay/HEAD.jsonl
    python tools/perc/replay/run.py RUN --old dev --only perception/world.py,cover.py     # only these files from `dev`
    python tools/perc/replay/run.py RUN [--map ID] [--t0 S --t1 S] [--every K] [--out NAME]
    python tools/perc/replay/run.py RECORDING#K [--holdout]       # a segment of the recording corpus (one map of a
                                                                  # walk) -> CORPUS/work/RECORDING#K/replay/

RUN = a run folder (frames as PNG files or as the lossless video: tools/perc/frames.py reads either) or a corpus
segment (tools/data/corpus.py list --segments; a hold-out segment only with --holdout). The map is read from
RUN/log.txt (`map recognised: ID`) or is the segment's, unless given. (The mob score is gone with the old detector,
2026-11-17: the fit's sightings are 1.0 and no score bar applies.)
`--old REF` swaps modules, not files: an import hook serves maplebrain's sources from `git show REF:...` under the
working tree's file names (so the assets are found as always); nothing is checked out or written. The rig is built
by the working tree's tools/perf/bench.py: a REF whose Rig / _load_map differ too much won't build (then check it
out in a worktree and run its own copy) - every ref before the old perception's deletion (58d266e and older) is
such a ref: its replays are the gate's cache (RUN/replay/fp_*), or a worktree of it.

One line per saved frame: {"n", "frame", "t", "cam", "cam_src", "me", "me_map", "map_pos", "mobs": [Track.as_dict],
"scene_cam", "patches", "fit", "fit_ms", "fit_hints" (FrameFacts v3), "drops", "drops_ms" (v5), "ms"}.
Frames are saved every 3rd tick, so the replay runs at ~1/3 of the live rate: its tracks are close to the live
run's (compare.py --live), not equal; two replays of the same code are equal row by row.
"""
import argparse
import importlib.abc
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class _Loader(importlib.abc.SourceLoader):
    def __init__(self, path: str, data: bytes):
        self.path, self.data = path, data

    def get_filename(self, fullname):
        return self.path

    def get_data(self, path):
        return self.data


class GitSource(importlib.abc.MetaPathFinder):
    """maplebrain's modules from a git ref (all of them, or `only` these files), named like the working tree's."""

    def __init__(self, ref: str, only: list | None = None):
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "maplebrain"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split("\n")
        self.ref = ref
        self.files = {n for n in names if n.endswith(".py")}
        if only:
            pick = {n for n in self.files if any(n == f"maplebrain/{o}" or n.endswith("/" + o) for o in only)}
            missing = [o for o in only if not any(n == f"maplebrain/{o}" or n.endswith("/" + o) for n in pick)]
            if missing:
                raise SystemExit(f"--only: not in {ref}: {missing}")
            self.files = pick
        self.served = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "maplebrain" and not fullname.startswith("maplebrain."):
            return None
        rel = fullname.replace(".", "/")
        for cand, pkg in ((rel + "/__init__.py", True), (rel + ".py", False)):
            if cand in self.files:
                src = subprocess.run(["git", "show", f"{self.ref}:{cand}"], cwd=ROOT, capture_output=True,
                                     check=True).stdout
                self.served.append(cand)
                return importlib.util.spec_from_file_location(
                    fullname, str(ROOT / cand), loader=_Loader(str(ROOT / cand), src),
                    submodule_search_locations=[str(ROOT / rel)] if pkg else None)
        return None


def bench_module():
    spec = importlib.util.spec_from_file_location("perf_bench", ROOT / "tools" / "perf" / "bench.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                      # (puts ROOT on sys.path)
    return mod


def frames_module():
    sys.path.insert(0, str(ROOT / "tools" / "perc"))
    import frames as rec                              # PNG or video; the 1 px capture error of two recordings undone
    return rec


def replay(run: Path, map_id: int, frames: list, out: Path) -> dict:
    """`frames`: [(n, frame name, t)] of the recording in `run`, in order (frames.Clip.frames)."""
    per = bench_module().build(map_id)[0]
    rec = frames_module()
    t_start = time.perf_counter()
    with open(out, "w", encoding="utf-8") as f:
        for n, name, t in frames:
            obs = per.observe(rec.read(run, name), t)
            f.write(json.dumps({"n": n, "frame": name, "t": round(t, 3), "cam": obs.cam, "cam_src": obs.cam_src,
                                "me": obs.me, "me_map": obs.me_map, "map_pos": obs.map_pos, "mobs": obs.mobs,
                                "scene_cam": getattr(obs, "scene_cam", None),
                                "patches": getattr(getattr(per, "facts", None), "patches", None),
                                **{k: getattr(getattr(per, "facts", None), k, None)
                                   for k in ("fit", "fit_ms", "fit_hints", "drops", "drops_ms")},
                                "ms": dict(getattr(per, "parts", None) or {})}) + "\n")
    return {"frames": len(frames), "seconds": round(time.perf_counter() - t_start, 1),
            "stats": dict(getattr(per.world, "stats", {}) or {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="a run folder, or a corpus segment RECORDING#K")
    ap.add_argument("--holdout", action="store_true", help="RUN is a hold-out segment of the corpus: only at gates (the use is logged)")
    ap.add_argument("--old", default=None, metavar="REF", help="maplebrain's code from this git ref (default: the working tree)")
    ap.add_argument("--only", default=None, help="with --old: only these files from REF, comma separated (perception/world.py)")
    ap.add_argument("--map", type=int, default=None)
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float, default=1e9)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--out", default=None, help="name of the output in RUN/replay/ (default: work, or the ref)")
    a = ap.parse_args()
    src = None
    if a.old:
        src = GitSource(a.old, a.only.split(",") if a.only else None)
        sys.meta_path.insert(0, src)
    elif a.only:
        raise SystemExit("--only needs --old REF")
    c = frames_module().clip(a.run, a.holdout, "replay/run.py")
    map_id = a.map or c.map_id
    if map_id is None:
        raise SystemExit("no map in the run's log: --map ID")
    frames = c.frames(a.t0, a.t1, a.every)
    if not frames:
        raise SystemExit(f"no saved frames in {a.run}")
    name = a.out or (re.sub(r"[^\w.-]", "_", a.old) if a.old else "work")
    out = c.out / "replay" / f"{name}.jsonl"
    out.parent.mkdir(exist_ok=True)
    r = replay(c.run, map_id, frames, out)
    code = f"{a.old} ({len(src.served)} modules{' only: ' + a.only if a.only else ''})" if src else "working tree"
    print(f"replay {a.run}: map {map_id}, code {code}; {r['frames']} frames in {r['seconds']} s "
          f"-> {out}")
    print("tracker stats:", r["stats"])


if __name__ == "__main__":
    main()
