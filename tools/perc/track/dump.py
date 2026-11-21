"""Tracker plan: THE KEPT REPLAY - the live Perceiver, unchanged, over EVERY frame of a capture (the live rate),
written once, so tracker prototypes run from it in seconds, no GPU (HANDOFF step 2, docs/prompts/tracker-before.md).

    python tools/perc/track/dump.py SESSION#K [SESSION#K ...] [--t0 S --t1 S] [--force]
    python tools/perc/track/dump.py --all [--force]       every capture of CAPTURES (below), one process each

A capture = a stay of the bank (its id SESSION#K, tools/perc/frames.py `clip`) or a run folder. Hold-out stays are
refused (no --holdout here on purpose). Output: OUT/track/ with OUT = CORPUS/work/SESSION#K (a run folder: itself):
    meta.json          map, frames, rows per chunk, GPU seconds, decode seconds, bytes, the code's commit, when
    rows_NNN.pkl       a list of rows, one per frame (pickle; CHUNK frames a file):
        n, frame, t      the frame's number in the session, its name, the session's clock
        C                the scene camera (map px of the screen's corner; None: not found this frame)
        cam, cam_src     the tracker's camera / where it came from
        me, me_map, map_pos     our tag on screen (x, y, w, h), our feet on the map (tag + camera), the minimap's
        mobs             today's tracker (world.py): Track.as_dict per track - the baseline
        facts            FrameFacts.as_dict (v5): fit (the fit's mobs), fit_hints (the looks at today's tracks the
                         fit did not find), patches (D's blobs), drops, tags (players' name tags), hp / mp / exp,
                         tag, scene_share, ...
        explained        shows / world pixels (below) on this frame (None: no camera)
        world_px         world pixels on this frame
        ms               the Perceiver's parts' ms (Perceiver.parts) + "observe" (the whole call, wall clock)
    bits_NNN.pkl       the same frames' two bitmaps of the play area (1366 x 700), [(n, shows, world)] with each one
                       zlib of np.packbits (None: no camera):
        world   the pixel can show a mob: known scenery, no opaque UI, no front background over it (the fit's `valid`)
        shows   world and the frame equals the expected scene within the fit's tolerance: THE SCENE SHOWS THERE
    So per pixel: shows = nothing is drawn over the scene; world & ~shows = something else is drawn there (a mob, an
    effect, a player, a drop, a number); ~world = can't tell (animated scenery, the UI).

Reading it back: `rows(cap)` (every row, in order), `bits_rows(cap)` (yields (n, shows, world) arrays),
`bits(packed)` -> the (700, 1366) bool array. While the user is recording (a folder in CORPUS/incoming) a capture
does not start: it waits, a look a minute.
"""
import argparse
import json
import pickle
import subprocess
import sys
import time
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
PLAY_H, SW = 700, 1366
CHUNK = 6000                     # frames per rows / bits file (100 s of footage)
# The captures of this replay (docs/prompts/tracker-before.md): the dev group at the full rate (> 45 frames a second)
# on a map with a clean scene model, labels farming or traveling; not the `bot` hunts, not the every-3rd-frame
# recordings, never the hold-out group. 20261119_204522_1#8 (Ellinia, 1 s) has no scene model.
CAPTURES = [
    "20261121_000219_2#0",       # Line 1 <Area 1>, 30.6 min: the design capture (the settings the user keeps)
    "20261120_235747_1#0",       # its 4-minute twin
    "20261119_210307_1#0",       # The Field South of Ellinia, new settings
    "20261118_232410_1#0", "20261118_232410_1#1", "20261118_232410_1#2", "20261118_232410_1#3",
    "20261118_232410_1#4", "20261118_232410_1#5", "20261118_232410_1#7", "20261118_232410_1#9",
    "20261118_232410_1#11", "20261118_232410_1#12", "20261118_232410_1#13",
    "20261119_123331_2#1", "20261119_123331_2#3", "20261119_123331_2#4", "20261119_123331_2#6",
    "20261119_204522_1#1", "20261119_204522_1#3", "20261119_204522_1#4", "20261119_204522_1#5",
    "20261119_204522_1#7",
]


def pack(a) -> bytes:
    return zlib.compress(np.packbits(a).tobytes(), 1)


def bits(packed) -> np.ndarray:
    return np.unpackbits(np.frombuffer(zlib.decompress(packed), np.uint8))[:PLAY_H * SW].reshape(PLAY_H, SW).astype(bool)


def clip_of(cap):
    import frames as rec
    return rec.clip(cap, False, "track/dump.py")


def out_dir(cap) -> Path:
    return clip_of(cap).out / "track"


def meta(cap) -> dict:
    return json.loads((out_dir(cap) / "meta.json").read_text(encoding="utf-8"))


def rows(cap) -> list:
    """Every row of the kept replay of `cap`, in order (no bitmaps)."""
    d, out = out_dir(cap), []
    for k in range(meta(cap)["chunks"]):
        out += pickle.loads((d / f"rows_{k:03d}.pkl").read_bytes())
    return out


def bits_rows(cap, packed: bool = False):
    """(n, shows, world) per frame of the kept replay, in order (None, None when the frame had no camera)."""
    d = out_dir(cap)
    for k in range(meta(cap)["chunks"]):
        for n, s, w in pickle.loads((d / f"bits_{k:03d}.pkl").read_bytes()):
            if packed or s is None:
                yield n, s, w
            else:
                yield n, bits(s), bits(w)


def recording() -> list:
    from maplebrain.config import CORPUS
    inc = Path(CORPUS) / "incoming"
    return [p.name for p in inc.iterdir() if p.is_dir()] if inc.exists() else []


def dump(cap, t0: float, t1: float, force: bool) -> None:
    import frames as rec
    import run as replay
    c = clip_of(cap)
    out = c.out / "track"
    if (out / "meta.json").exists() and not force:
        print(f"{cap}: {out} exists (--force to redo)", flush=True)
        return
    while recording():
        print(f"{cap}: the user is recording ({recording()}) - waiting", flush=True)
        time.sleep(60)
    out.mkdir(parents=True, exist_ok=True)
    for p in list(out.glob("rows_*.pkl")) + list(out.glob("bits_*.pkl")) + [out / "meta.json"]:
        if p.exists():
            p.unlink()
    fr = c.frames(t0, t1)
    per = replay.bench_module().build(c.map_id)[0]
    tol = per.fitter.cfg.tol
    gpu_s = dec_s = 0.0
    rws, bts, k, nbytes, no_cam, n_done = [], [], 0, 0, 0, 0
    t_start = time.perf_counter()

    def flush():
        nonlocal rws, bts, k, nbytes
        for name, obj in ((f"rows_{k:03d}.pkl", rws), (f"bits_{k:03d}.pkl", bts)):
            p = out / name
            p.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
            nbytes += p.stat().st_size
        rws, bts, k = [], [], k + 1

    for n, name, t in fr:
        a = time.perf_counter()
        img = rec.read(c.run, name)
        b = time.perf_counter()
        dec_s += b - a
        if img is None:
            raise SystemExit(f"{cap}: frame {name} unreadable")
        obs = per.observe(img, t)
        f = per.facts
        row = {"n": n, "frame": name, "t": round(t, 4), "C": obs.scene_cam, "cam": obs.cam, "cam_src": obs.cam_src,
               "me": obs.me, "me_map": obs.me_map, "map_pos": obs.map_pos, "mobs": obs.mobs, "facts": f.as_dict(),
               "explained": None, "world_px": None}
        if obs.scene_cam is None or per.fitter._last is None:
            no_cam += obs.scene_cam is None
            bts.append((n, None, None))
        else:
            _frame_t, _C, exp, valid = per.fitter._last
            shows = valid & ((_frame_t.float() - exp).abs().amax(dim=2) <= tol)
            sv, sw = int(shows.sum()), int(valid.sum())
            row["explained"], row["world_px"] = round(sv / max(1, sw), 5), sw
            bts.append((n, pack(shows.cpu().numpy()), pack(valid.cpu().numpy())))
        e = time.perf_counter()
        gpu_s += e - b
        row["ms"] = {**dict(per.parts or {}), "observe": round(1000 * (e - b), 2)}
        rws.append(row)
        n_done += 1
        if len(rws) == CHUNK:
            flush()
            print(f"  {cap}: {n_done} / {len(fr)} frames, {time.perf_counter() - t_start:.0f} s", flush=True)
    if rws:
        flush()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "maplebrain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    m = {"cap": c.name, "map": c.map_id, "frames": n_done, "no_cam": no_cam, "chunk": CHUNK, "chunks": k,
         "t": [fr[0][2], fr[-1][2]] if fr else None, "observe_s": round(gpu_s, 1), "decode_s": round(dec_s, 1),
         "wall_s": round(time.perf_counter() - t_start, 1), "bytes": nbytes, "code": commit,
         "maplebrain_dirty": bool(dirty), "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "tracker_stats": dict(getattr(per.world, "stats", {}) or {})}
    (out / "meta.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(f"{cap}: map {c.map_id}, {n_done} frames ({no_cam} without a camera); observe {gpu_s:.0f} s, decode "
          f"{dec_s:.0f} s, {nbytes / 1e9:.2f} GB -> {out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float, default=1e9)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.all:
        for cap in CAPTURES:
            cmd = [sys.executable, str(Path(__file__)), cap] + (["--force"] if a.force else [])
            if subprocess.run(cmd, cwd=ROOT).returncode != 0:
                print(f"FAILED: {cap}", flush=True)
        return
    for cap in a.caps:
        dump(cap, a.t0, a.t1, a.force)


if __name__ == "__main__":
    main()
