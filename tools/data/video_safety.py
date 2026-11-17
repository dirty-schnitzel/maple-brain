"""Review checks for the video recorder idea:
 (1) keyframe every 120 frames: size cost + is cv2's seek frame-exact on random indexes?
 (2) the encoder killed mid-recording (taskkill /F, the worst case): how much of the file reads back, exactly?
 (3) the WRITER (python) killed: ffmpeg sees its stdin close - does it finish the file by itself?
"""
import random
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

src = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
files = sorted(src.glob("*.png"))[:600]
frames = [cv2.imread(str(f), cv2.IMREAD_COLOR) for f in files]
h, w = frames[0].shape[:2]
png = sum(f.stat().st_size for f in files)
print(f"{len(frames)} frames, PNG {png / 1e6:.0f} MB", flush=True)


def enc(path, extra=(), fmt="matroska"):
    return subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                             "-s", f"{w}x{h}", "-r", "60", "-i", "-", "-c:v", "hevc_nvenc", "-tune", "lossless",
                             "-preset", "p4", "-pix_fmt", "gbrp", "-g", "120", *extra, "-f", fmt, str(path)],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def readback(path):
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    got, bad = 0, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if got < len(frames) and not np.array_equal(f, frames[got]):
            bad += 1
        got += 1
    return cap, got, bad


# (1) full file, keyframe every 120
p = enc(out / "g120.mkv")
for f in frames:
    p.stdin.write(f.tobytes())
p.stdin.close(); p.wait()
size = (out / "g120.mkv").stat().st_size
cap, got, bad = readback(out / "g120.mkv")
print(f"(1) g120.mkv: {size / 1e6:.0f} MB = x{png / size:.1f} vs PNG; sequential read {got}/{len(frames)} frames, {bad} differ", flush=True)
random.seed(1)
idx = random.sample(range(len(frames)), 60)
wrong, ms = 0, []
for i in idx:
    t = time.perf_counter()
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, f = cap.read()
    ms.append(1000 * (time.perf_counter() - t))
    if not ok or not np.array_equal(f, frames[i]):
        wrong += 1
print(f"    60 random seeks: {wrong} wrong frames; seek+read p50 {np.median(ms):.0f} ms, max {max(ms):.0f} ms", flush=True)

# (2) the encoder itself killed after 400 frames
for name, extra in (("killed_default.mkv", ()), ("killed_flush.mkv", ("-flush_packets", "1", "-cluster_time_limit", "1000"))):
    p = enc(out / name, extra)
    for f in frames[:400]:
        p.stdin.write(f.tobytes())
    time.sleep(1.0)
    subprocess.run(["taskkill", "/F", "/PID", str(p.pid)], capture_output=True)
    p.wait()
    cap, got, bad = readback(out / name)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, got - 30)); ok, f = cap.read()
    seek_ok = ok and np.array_equal(f, frames[max(0, got - 30)])
    print(f"(2) {name}: ffmpeg killed after 400 frames -> {got} read back, {bad} differ; a seek near the end exact: {seek_ok}", flush=True)

# (3) the writer killed: a child python pipes frames forever, we kill only it
child = subprocess.Popen([sys.executable, "-c", f"""
import subprocess, sys, time, cv2, glob
fs = sorted(glob.glob(r'{src}' + '/*.png'))[:200]
fr = [cv2.imread(f) for f in fs]
p = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','bgr24','-s','{w}x{h}','-r','60','-i','-',
  '-c:v','hevc_nvenc','-tune','lossless','-preset','p4','-pix_fmt','gbrp','-g','120', r'{out / "writer_killed.mkv"}'], stdin=subprocess.PIPE)
print('ready', flush=True)
for f in fr:
    p.stdin.write(f.tobytes())
print('written', flush=True)
time.sleep(60)
"""], stdout=subprocess.PIPE, text=True)
child.stdout.readline(); child.stdout.readline()
subprocess.run(["taskkill", "/F", "/PID", str(child.pid)], capture_output=True)      # python only, not the tree
time.sleep(3)
left = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe"], capture_output=True, text=True).stdout
cap, got, bad = readback(out / "writer_killed.mkv")
print(f"(3) writer killed after 200 frames: {got} read back, {bad} differ; ffmpeg still running: {'ffmpeg.exe' in left}", flush=True)
