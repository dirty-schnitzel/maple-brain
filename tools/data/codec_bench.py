"""Lossless video codecs vs the PNG frames: size, encode speed, round-trip exactness.
Frames are loaded once into memory, piped raw (bgr24) to ffmpeg as the recorder would, then decoded back and compared."""
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

src = Path(sys.argv[1])
n = int(sys.argv[2])
out = Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
files = sorted(src.glob("*.png"))[:n]
png_bytes = sum(f.stat().st_size for f in files)
frames = [cv2.imread(str(f), cv2.IMREAD_COLOR) for f in files]
h, w = frames[0].shape[:2]
print(f"{src}: {len(frames)} frames {w}x{h}, PNG {png_bytes / len(frames) / 1e6:.2f} MB/frame", flush=True)

FPS = "20"
CASES = {
    "ffv1": ["-c:v", "ffv1", "-level", "3", "-slices", "16", "-g", "1", "-pix_fmt", "bgr0"],
    "x264rgb_ultrafast": ["-c:v", "libx264rgb", "-qp", "0", "-preset", "ultrafast", "-pix_fmt", "bgr24"],
    "x264rgb_veryfast": ["-c:v", "libx264rgb", "-qp", "0", "-preset", "veryfast", "-pix_fmt", "bgr24"],
    "x264rgb_medium": ["-c:v", "libx264rgb", "-qp", "0", "-preset", "medium", "-pix_fmt", "bgr24"],
    "x265_ultrafast": ["-c:v", "libx265", "-x265-params", "lossless=1:log-level=error", "-preset", "ultrafast", "-pix_fmt", "gbrp"],
    "hevc_nvenc_gbrp": ["-c:v", "hevc_nvenc", "-tune", "lossless", "-preset", "p4", "-pix_fmt", "gbrp"],
    "h264_nvenc_gbrp": ["-c:v", "h264_nvenc", "-tune", "lossless", "-preset", "p4", "-pix_fmt", "gbrp"],
    "x264rgb_veryfast_t2": ["-c:v", "libx264rgb", "-qp", "0", "-preset", "veryfast", "-threads", "2", "-pix_fmt", "bgr24"],
    "x264rgb_superfast_t2": ["-c:v", "libx264rgb", "-qp", "0", "-preset", "superfast", "-threads", "2", "-pix_fmt", "bgr24"],
    "x264rgb_veryfast_g60": ["-c:v", "libx264rgb", "-qp", "0", "-preset", "veryfast", "-g", "60", "-pix_fmt", "bgr24"],
    "hevc_nvenc_p7": ["-c:v", "hevc_nvenc", "-tune", "lossless", "-preset", "p7", "-pix_fmt", "gbrp"],
    "x264rgb_crf4_veryfast": ["-c:v", "libx264rgb", "-crf", "4", "-preset", "veryfast", "-pix_fmt", "bgr24"],
}
only = sys.argv[4].split(",") if len(sys.argv) > 4 else list(CASES)

for name in only:
    args = CASES[name]
    path = out / f"{name}.mkv"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{w}x{h}", "-r", FPS, "-i", "-", *args, str(path)]
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in frames:
            p.stdin.write(f.tobytes())
        p.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    err = p.stderr.read().decode(errors="replace")
    p.wait()
    dt = time.perf_counter() - t0
    import ctypes
    from ctypes import wintypes
    ft = [wintypes.FILETIME() for _ in range(4)]
    ctypes.windll.kernel32.GetProcessTimes(int(p._handle), *[ctypes.byref(x) for x in ft])
    tot = lambda x: (x.dwHighDateTime << 32 | x.dwLowDateTime) / 1e7
    cpu = tot(ft[2]) + tot(ft[3])
    if p.returncode != 0 or not path.exists():
        print(f"{name:24s} FAILED: {err.strip()[:300]}", flush=True)
        continue
    size = path.stat().st_size
    # decode back and compare
    dec = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], capture_output=True)
    buf = np.frombuffer(dec.stdout, np.uint8)
    m = buf.size // (w * h * 3)
    back = buf[: m * w * h * 3].reshape(m, h, w, 3)
    maxd, exact, within4 = 0, 0, 0
    total = 0
    for a, b in zip(frames, back):
        d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
        maxd = max(maxd, int(d.max()))
        exact += int((d == 0).sum())
        within4 += int((d <= 4).sum())
        total += d.size
    print(f"{name:24s} {size / len(frames) / 1e6:6.3f} MB/frame  x{png_bytes / size:5.1f} vs PNG  "
          f"encode {len(frames) / dt:6.1f} fps  cpu {1000 * cpu / len(frames):5.1f} ms/frame  frames back {m}/{len(frames)}  max diff {maxd}  "
          f"exact {100 * exact / total:6.2f} %  within4 {100 * within4 / total:6.2f} %", flush=True)
