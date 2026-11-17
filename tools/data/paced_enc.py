"""Pipes recorded frames to the lossless GPU encoder at a real-time 60 fps for N seconds (a stand-in for the recorder)."""
import subprocess, sys, time, glob, cv2
src, out, secs = sys.argv[1], sys.argv[2], float(sys.argv[3])
fr = [cv2.imread(f) for f in sorted(glob.glob(src + "/*.png"))[:240]]
h, w = fr[0].shape[:2]
p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                      "-r", "60", "-i", "-", "-c:v", "hevc_nvenc", "-tune", "lossless", "-preset", "p4", "-pix_fmt", "gbrp", "-g", "120", out],
                     stdin=subprocess.PIPE)
print("ready", flush=True)
t0 = time.perf_counter(); n = 0; late = 0
while time.perf_counter() - t0 < secs:
    due = t0 + n / 60
    d = due - time.perf_counter()
    if d > 0: time.sleep(d)
    elif d < -0.016: late += 1
    p.stdin.write(fr[n % len(fr)].tobytes()); n += 1
p.stdin.close(); p.wait()
print(f"paced: {n} frames in {time.perf_counter() - t0:.1f} s = {n / (time.perf_counter() - t0):.1f} fps, late {late}", flush=True)
