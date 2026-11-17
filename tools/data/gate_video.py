"""Session 1's gates on the video writer / reader, run without the game (PLAN-data.md section 5, gates a and d).
The frames come from an existing native PNG recording: its first K frames, repeated, each repeat moved 2 px more
to the right (so every frame differs from its neighbours and frame i is known exactly: `source`).

    python tools/data/gate_video.py border RUN OUT [--frames 18240]
        gate (a), the real chunk size: the frames through the recorder's writer with the recorder's settings
        (chunks of 18,000 frames), then: chunk 0 holds exactly 18,000 frames, every frame from 300 before the
        border to the end is identical to what went in, 200 random jumps on both sides of the border are exact.
    python tools/data/gate_video.py kill python|ffmpeg RUN OUT [--frames 30000]
        gate (d): a child process records (as fast as the encoder takes frames) until a second chunk file exists,
        then it is killed (taskkill /F: the recorder's python, or its ffmpeg). Then tools/data/corpus.py's check
        (repairs the cut chunk without re-encoding) and every frame the files hold is compared with what went in.
    python tools/data/gate_video.py feed RUN OUT --frames N     (the child of `kill`)
"""
import argparse
import random
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(Path(__file__).parent))
import frames as fr  # noqa: E402
from maplebrain.runtime.video import VideoWriter  # noqa: E402

K = 240


def load(run: Path) -> list:
    files = sorted((run / "frames").glob("*.png"))[:K]
    return [cv2.imread(str(f)) for f in files]


def source(base: list, i: int) -> np.ndarray:
    return np.ascontiguousarray(np.roll(base[i % len(base)], 2 * (i // len(base)), axis=1))


def same(v, base: list, ids) -> list:
    """The video frames of `ids` that differ from what went in."""
    return [i for i in ids if not np.array_equal(v.frame(i), source(base, i))]


def border(run: Path, out: Path, n: int) -> int:
    base = load(run)
    vw = VideoWriter(out, note={"by": "gate"})
    t = time.perf_counter()
    for i in range(n):
        vw.put(source(base, i), i, i / 60, wait=True)
    meta = vw.close()
    dt = time.perf_counter() - t
    print(f"{n} frames written in {dt:.0f} s ({n / dt:.0f} a second): {meta['chunks']} chunk files, "
          f"{meta['bytes'] / 1e9:.2f} GB, dropped {meta['dropped']}, error {meta['error']}")
    import corpus
    corpus.check(out, full=True)
    v = fr.video(out)
    chunk = v.chunk
    t = time.perf_counter()
    bad = same(v, base, range(chunk - 300, n))
    print(f"frames {chunk - 300}..{n - 1} in order (across the border at {chunk}): {len(bad)} differ; "
          f"{(n - chunk + 300) / (time.perf_counter() - t):.0f} frames a second")
    random.seed(7)
    ids = [random.randrange(chunk - 2000, n) for _ in range(200)]
    t = time.perf_counter()
    bad2 = same(v, base, ids)
    print(f"200 random jumps in {chunk - 2000}..{n - 1}: {len(bad2)} wrong; {1000 * (time.perf_counter() - t) / 200:.0f} ms each")
    edge = same(v, base, [chunk - 1, chunk, chunk - 1, chunk + 1, chunk - 2, 0, n - 1, chunk])
    print(f"back and forth over the border: {len(edge)} wrong")
    v.close()
    return 1 if bad or bad2 or edge or meta["error"] else 0


def feed(run: Path, out: Path, n: int) -> int:
    base = load(run)
    vw = VideoWriter(out, note={"by": "gate"})
    print(f"ffmpeg {vw.proc.pid}", flush=True)
    for i in range(n):
        if not vw.put(source(base, i), i, i / 60, wait=True) or vw.error:
            break
    vw.close()
    print(f"child: closed, {vw.written} handed to the encoder, error {vw.error}", flush=True)
    return 0


def kill(what: str, run: Path, out: Path, n: int) -> int:
    child = subprocess.Popen([sys.executable, __file__, "feed", str(run), str(out), "--frames", str(n)],
                             stdout=subprocess.PIPE, text=True)
    ffmpeg = int(child.stdout.readline().split()[1])
    while not (out / "frames_0001.mkv").exists():
        time.sleep(0.2)
        if child.poll() is not None:
            raise SystemExit("the child ended before a second chunk existed: more --frames")
    time.sleep(3.0)                                          # (well into the second chunk)
    pid = child.pid if what == "python" else ffmpeg
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    print(f"killed {what} (pid {pid}) mid-recording")
    if what == "python":                                     # ffmpeg sees its stdin close and finishes by itself
        t = time.perf_counter()
        while str(ffmpeg) in subprocess.run(["tasklist", "/FI", f"PID eq {ffmpeg}", "/NH"], capture_output=True,
                                            text=True).stdout:
            time.sleep(0.2)
            if time.perf_counter() - t > 60:
                raise SystemExit("ffmpeg did not end by itself")
        print(f"ffmpeg ended by itself {time.perf_counter() - t:.1f} s later")
    else:
        print("the recorder said:", (child.stdout.read() or "").strip())
    child.wait()
    import corpus
    listed = sum(1 for _ in open(out / "frames.jsonl"))
    meta = corpus.check(out, full=True)
    base = load(run)
    v = fr.video(out)
    t = time.perf_counter()
    bad = same(v, base, range(len(v)))
    print(f"{listed} frames listed, {len(v)} in the files ({listed - len(v)} lost at the end = "
          f"{(listed - len(v)) / 60:.2f} s at 60 fps); every frame of the files read: {len(bad)} differ "
          f"({len(v) / (time.perf_counter() - t):.0f} a second); chunks {meta['chunks']}")
    random.seed(3)
    last = range(max(0, len(v) - 600), len(v))
    bad2 = same(v, base, [random.choice(last) for _ in range(60)])
    print(f"60 random jumps in the last (cut) chunk's final 10 s: {len(bad2)} wrong")
    v.close()
    return 1 if bad or bad2 else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["border", "kill", "feed"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--frames", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "border":
        sys.exit(border(Path(a.args[0]), Path(a.args[1]), a.frames or 18240))
    if a.cmd == "feed":
        sys.exit(feed(Path(a.args[0]), Path(a.args[1]), a.frames))
    sys.exit(kill(a.args[0], Path(a.args[1]), Path(a.args[2]), a.frames or 30000))
