"""Montage of crops around our kills (where the drop should land), frames after each kill.
usage: kill_montage.py RUN OUT_DIR [max_kills]"""
import json, re, sys
from pathlib import Path
import cv2, numpy as np

run, out = Path(sys.argv[1]), Path(sys.argv[2])
maxk = int(sys.argv[3]) if len(sys.argv) > 3 else 6
out.mkdir(parents=True, exist_ok=True)
ticks = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
kills = []
for line in open(run / "log.txt", encoding="utf-8"):
    m = re.match(r"\s*([\d.]+)s loot at dx ([+-]\d+) -> waiting", line)
    if m:
        kills.append((float(m.group(1)), int(m.group(2))))
for i, (kt, dx) in enumerate(kills[:maxk]):
    k0 = next(k for k in ticks if k["obs"]["t"] >= kt)
    px, feet = k0["obs"]["me"]; dot0 = k0["obs"]["dot"]
    rows = []
    for k in ticks:
        t = k["obs"]["t"]
        if not (kt + 0.3 <= t <= kt + 4.0) or not k["frame"]:
            continue
        f = cv2.imread(str(run / "frames" / k["frame"]))
        # keep the drop's world spot: camera moves with us; use scene shift via our screen x vs dot
        me = k["obs"]["me"]
        cxw = px + dx
        if me and k["obs"]["dot"] and dot0:
            cxw = me[0] + dx - (k["obs"]["dot"][0] - dot0[0]) * 15
        x0 = int(max(0, min(1366 - 300, cxw - 150))); y0 = int(max(0, feet - 110))
        c = f[y0:y0 + 160, x0:x0 + 300].copy()
        cv2.putText(c, f"{t - kt:.2f} {k['frame']}", (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        rows.append(c)
    if rows:
        rows = rows[::max(1, len(rows) // 12)][:12]
        while len(rows) % 3:
            rows.append(np.zeros_like(rows[0]))
        g = np.vstack([np.hstack(rows[j:j + 3]) for j in range(0, len(rows), 3)])
        cv2.imwrite(str(out / f"kill{i}_{kt:.0f}s.png"), g)
        print(out / f"kill{i}_{kt:.0f}s.png", len(rows))
