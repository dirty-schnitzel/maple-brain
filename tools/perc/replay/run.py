"""Tracker replay: the live Perceiver (tools/perf/bench.build = runner._load_map with --gpu --tracker) over a recorded
run's saved frames -> the tracks of every frame. The gate of every perception change: old code vs new code on the
same frames (compare.py).

    python tools/perc/replay/run.py RUN                           # the working tree -> RUN/replay/work.jsonl
    python tools/perc/replay/run.py RUN --old HEAD                # maplebrain/ as committed at HEAD -> RUN/replay/HEAD.jsonl
    python tools/perc/replay/run.py RUN --old dev --only perception/world.py,cover.py     # only these files from `dev`
    python tools/perc/replay/run.py RUN [--map ID] [--mob-score S] [--t0 S --t1 S] [--every K] [--out NAME]

The map and the mob score are read from RUN/log.txt (`map recognised: ID`, `mob score S`) unless given.
`--old REF` swaps modules, not files: an import hook serves maplebrain's sources from `git show REF:...` under the
working tree's file names (so the assets are found as always); nothing is checked out or written. The rig is built
by the working tree's tools/perf/bench.py: a REF whose Rig / _load_map differ too much won't build (then check it
out in a worktree and run its own copy).

One line per saved frame: {"n", "frame", "t", "cam", "cam_src", "me", "me_map", "map_pos", "mobs": [Track.as_dict]}.
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


def from_log(run: Path) -> tuple:
    """(map id, mob score) as the run's log says; None where it doesn't."""
    log = (run / "log.txt").read_text(encoding="utf-8", errors="replace") if (run / "log.txt").exists() else ""
    m = re.search(r"map recognised: (\d+)", log) or re.search(r"\bmap (\d+) ", log)
    s = re.search(r"mob score ([0-9.]+)", log)
    return (int(m.group(1)) if m else None), (float(s.group(1).rstrip(".")) if s else None)


def saved_frames(run: Path, t0: float = 0.0, t1: float = 1e9, every: int = 1) -> list:
    """[(n, frame file, t)] of the ticks whose frame was saved, in order."""
    out = []
    with open(run / "ticks.jsonl", encoding="utf-8") as f:
        for line in f:
            k = json.loads(line)
            if k.get("frame") and t0 <= k["obs"]["t"] <= t1 and (run / "frames" / k["frame"]).exists():
                out.append((k["n"], k["frame"], k["obs"]["t"]))
    return out[::every]


def replay(run: Path, map_id: int, mob_score: float, frames: list, out: Path) -> dict:
    import cv2
    per = bench_module().build(map_id, mob_score)[0]
    t_start = time.perf_counter()
    with open(out, "w", encoding="utf-8") as f:
        for n, name, t in frames:
            obs = per.observe(cv2.imread(str(run / "frames" / name)), t)
            f.write(json.dumps({"n": n, "frame": name, "t": round(t, 3), "cam": obs.cam, "cam_src": obs.cam_src,
                                "me": obs.me, "me_map": obs.me_map, "map_pos": obs.map_pos, "mobs": obs.mobs}) + "\n")
    return {"frames": len(frames), "seconds": round(time.perf_counter() - t_start, 1),
            "stats": dict(getattr(per.world, "stats", {}) or {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--old", default=None, metavar="REF", help="maplebrain's code from this git ref (default: the working tree)")
    ap.add_argument("--only", default=None, help="with --old: only these files from REF, comma separated (perception/world.py)")
    ap.add_argument("--map", type=int, default=None)
    ap.add_argument("--mob-score", type=float, default=None)
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
    log_map, log_score = from_log(a.run)
    map_id = a.map or log_map
    if map_id is None:
        raise SystemExit("no map in the run's log: --map ID")
    score = a.mob_score or log_score or 0.70
    frames = saved_frames(a.run, a.t0, a.t1, a.every)
    if not frames:
        raise SystemExit(f"no saved frames in {a.run}")
    name = a.out or (re.sub(r"[^\w.-]", "_", a.old) if a.old else "work")
    out = a.run / "replay" / f"{name}.jsonl"
    out.parent.mkdir(exist_ok=True)
    r = replay(a.run, map_id, score, frames, out)
    code = f"{a.old} ({len(src.served)} modules{' only: ' + a.only if a.only else ''})" if src else "working tree"
    print(f"replay {a.run}: map {map_id}, mob score {score}, code {code}; {r['frames']} frames in {r['seconds']} s "
          f"-> {out}")
    print("tracker stats:", r["stats"])


if __name__ == "__main__":
    main()
