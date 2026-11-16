"""The perception gate (PLAN-perception.md step 2 on): base code vs the working tree, replayed on short clips of
several maps, cached by what the result depends on.

    python tools/perc/replay/gate.py [--quick] [--base REF] [--clips a,b] [--list]

Clips (CLIPS below, the user 2026-11-16: "more ~1 min footages of various maps is better than 1 long one"): about a
minute each of every clean native PNG recording + one FHD JPEG clip where the scene camera fails (today's camera,
the fallback path). `--quick` = QUICK (3 clips, ~3 min): every sub-step; the full set before a commit that changes
tracking. A change that can't touch tracking (docs, tools, code off the live path) needs pytest + the speed line only:
the gate says so itself when the fingerprints are equal.

Cache: a replay depends on maplebrain/, the tracked assets/ (templates! `run.py --old` swaps only the code), the
replay tools (bench.py, run.py, frames.py) - their git tree / blob ids are the FINGERPRINT. Every replay is kept as
RUN/replay/fp_<fingerprint>_<clip>.jsonl (`--base-only`: fill the base's), so the working tree's replay of one sub-step is the base of the next one
(computed once, never twice). A base not in the cache is replayed with `run.py --old REF` - only possible when REF's
assets and replay tools equal the working tree's (else the gate stops and says which files differ).
assets/scene (not in git) is the same for both sides.

Per clip: real / weak tracks, track-frames found both ways (compare.py), sighted track-frames the same, mob feet on
their platform within 2 px (the camera's exactness), our tag found, the camera's source. Verdict: SAME (>= 99.9 % both
ways), or CHANGED - then judge the table (surface, weak tracks, real tracks) and look at frames (show_track.py).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import compare as cmp  # noqa: E402

PY = sys.executable
PLAY = "runs/play/"
# name: (run, t0, t1) - native PNG, 1366x768, clean maps (no moving backgrounds); fix3 = FHD JPEG (fallback camera)
CLIPS = {
    "ant4": (PLAY + "20261116_154819_1", 0, 60),          # Ant Tunnel IV, the user playing, 3 mob types, players
    "ant4b": (PLAY + "20261116_012059_1", 150, 210),      # Ant Tunnel IV, another session (busy: 5-6 tracks a frame)
    "steam": (PLAY + "20261116_084844_2", 0, 60),         # Dangerous Steam (scenery ghosts of one mob type)
    "line1": (PLAY + "20261116_085108_3", 0, 60),         # Line 1 <Area 1> (29 background layers, Bubblings)
    "transfer": (PLAY + "20261116_085215_4", 0, 60),      # Transfer Area (repeating bricks, animated objects)
    "darkcave": (PLAY + "20261116_084719_1", 0, 16.3),    # Dark Cave (only 0-16.3 s clean: the window was dragged)
    "fhd": ("runs/v2/air1/fix3", 0, 60),                  # FHD JPEG: the scene camera fails -> today's camera
}
QUICK = ("ant4", "line1", "transfer")
DEPS_TREES = ("maplebrain", "assets")
DEPS_FILES = ("tools/perf/bench.py", "tools/perc/replay/run.py", "tools/perc/frames.py")


def git(*a, env=None) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True, env=env).stdout.strip()


def fingerprint(ref: str | None) -> str:
    """Short id of what a replay depends on, at git REF or (None) in the working tree (as it would be committed)."""
    if ref is None:
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(d) / "index")}
            git("read-tree", "HEAD", env=env)
            git("add", "-A", "--", *DEPS_TREES, *DEPS_FILES, env=env)
            tree = git("write-tree", env=env)
        ref = tree
    ids = [git("rev-parse", f"{ref}:{p}") for p in (*DEPS_TREES, *DEPS_FILES)]
    import hashlib
    return hashlib.sha1(" ".join(ids).encode()).hexdigest()[:10]


def replay(clip: str, fp: str, old: str | None) -> Path:
    run, t0, t1 = CLIPS[clip]
    out = ROOT / run / "replay" / f"fp_{fp}_{clip}.jsonl"
    if out.exists():
        return out
    cmd = [PY, "tools/perc/replay/run.py", run, "--t0", str(t0), "--t1", str(t1), "--out", out.stem]
    if old:
        cmd += ["--old", old]
    t = time.perf_counter()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"replay failed: {' '.join(cmd)}\n{r.stderr[-1500:]}")
    print(f"  replayed {clip} ({'base ' + old if old else 'working tree'}) in {time.perf_counter() - t:.0f} s", flush=True)
    return out


def surface(run: Path, rows: list) -> float | None:
    """Share of sighted live mob track-frames whose feet are within 2 px of their platform's surface."""
    import frames as rec
    from maplebrain.config import Config
    from maplebrain.nav.navmap import NavMap
    nav = NavMap.for_map(rec.map_of(run), ROOT / "assets" / "mcw", Config().nav)
    plats = nav.platforms if isinstance(nav.platforms, dict) else {p.id: p for p in nav.platforms}
    n = ok = 0
    for k in rows:
        for m in k["mobs"]:
            if m["state"] == "live" and m["src"] != "none" and not m["air"] and m["platform"] in plats:
                yp = plats[m["platform"]].y_at(m["x"])
                if yp is not None:
                    n, ok = n + 1, ok + (abs(m["y"] - yp) <= 2)
    return ok / n if n else None


def sighted_same(a: list, b: list) -> float:
    n = same = 0
    for ka, kb in zip(a, b):
        for m in ka["mobs"]:
            if m["state"] in ("live", "hit", "hidden", "dying") and m["src"] != "none":
                n += 1
                same += any(o["mob"] == m["mob"] and abs(o["sx"] - m["sx"]) <= 20 and abs(o["sy"] - m["sy"]) <= 20
                            for o in kb["mobs"] if o["state"] != "offscreen")
    return same / n if n else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--clips", default=None)
    ap.add_argument("--list", action="store_true", help="the clips and the cache, nothing replayed")
    ap.add_argument("--base-only", action="store_true", help="only replay (cache) the base")
    a = ap.parse_args()
    clips = a.clips.split(",") if a.clips else (list(QUICK) if a.quick else list(CLIPS))
    fb, fw = fingerprint(a.base), fingerprint(None)
    print(f"gate: base {a.base} = fp {fb}, working tree = fp {fw}; clips {', '.join(clips)}")
    if a.list:
        for c in clips:
            run = ROOT / CLIPS[c][0] / "replay"
            print(f"  {c}: {CLIPS[c]}; cached: {sorted(p.stem.split('_')[1] for p in run.glob(f'fp_*_{c}.jsonl'))}")
        return
    if a.base_only:
        for c in clips:
            replay(c, fb, a.base)
        return
    if fb == fw:
        print("SAME CODE AND ASSETS as the base: nothing to replay (pytest + the speed line are the gate)")
        return
    need_base = [c for c in clips if not (ROOT / CLIPS[c][0] / "replay" / f"fp_{fb}_{c}.jsonl").exists()]
    if need_base:
        diff = git("diff", "--name-only", a.base, "--", "assets", *DEPS_FILES)
        if diff:
            raise SystemExit(f"base replays missing for {need_base} and {a.base}'s assets / replay tools differ from the "
                             f"working tree ({diff.split()[:6]}): `run.py --old` can't swap those. Stash them, run the gate "
                             f"(the base gets cached), unstash.")
    rows_out = []
    for c in clips:
        run = ROOT / CLIPS[c][0]
        pb = replay(c, fb, a.base)
        pw = replay(c, fw, None)
        rb, rw = cmp.load(pb), cmp.load(pw)
        r = cmp.compare(rb, rw)
        sb, sw = cmp.summary(rb), cmp.summary(rw)
        fab, fba = r["a_in_b"], r["b_in_a"]
        share = lambda d: d["total"]["real"][1] / max(1, d["total"]["real"][0])   # noqa: E731
        rows_out.append((c, sb, sw, share(fab), share(fba), sighted_same(rb, rw), surface(run, rb), surface(run, rw),
                         sum(1 for k in rb if k["me"]) / len(rb), sum(1 for k in rw if k["me"]) / len(rw), len(rb),
                         {s: sum(1 for k in rw if k.get("cam_src") == s) for s in {k.get("cam_src") for k in rw}}))
    pc = lambda v: "-" if v is None else f"{100 * v:.1f}"   # noqa: E731
    print(f"\n{'clip':9} {'frames':>6}  real b>w   weak b>w   found b/w %      sighted= %  surface<=2px b>w %  tag b>w %   camera (work)")
    worst = 1.0
    for c, sb, sw, f1, f2, ss, s1, s2, t1, t2, n, cams in rows_out:
        worst = min(worst, f1, f2)
        print(f"{c:9} {n:6}  {sb['real']:>3}>{sw['real']:<4}  {sb['weak']:>3}>{sw['weak']:<4}  {pc(f1):>5}/{pc(f2):<6}  "
              f"{pc(ss):>8}    {pc(s1):>5}>{pc(s2):<6}        {pc(t1)}>{pc(t2)}   {cams}")
    print(f"\nVERDICT: {'SAME tracks (>= 99.9 % both ways on every clip)' if worst >= 0.999 else 'CHANGED - judge the table'}")


if __name__ == "__main__":
    main()
