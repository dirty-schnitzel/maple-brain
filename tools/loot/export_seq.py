"""Save a stretch of a recorded run as a drop-test fixture: the band around our floor of each saved frame (JPEG 95)
+ seq.json [{file, t, me}], rows y0..y1. usage: export_seq.py RUN T0 T1 OUT_DIR"""
import json, sys
from pathlib import Path
import cv2
run, t0, t1, out = Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
F = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
F = [k for k in F if k["frame"] and k["obs"]["me"] and t0 <= k["obs"]["t"] <= t1]
feet = int(F[0]["obs"]["me"][1]); y0, y1 = feet - 150, min(768, feet + 110)
seq = []
for k in F:
    f = cv2.imread(str(run / "frames" / k["frame"]))
    cv2.imwrite(str(out / k["frame"]), f[y0:y1], [cv2.IMWRITE_JPEG_QUALITY, 85])
    seq.append({"file": k["frame"], "t": round(k["obs"]["t"], 3), "me": k["obs"]["me"]})
json.dump({"source": f"{run.name} {t0}-{t1}s", "rows": [y0, y1], "frames": seq}, open(out / "seq.json", "w"), indent=1)
print(out, len(seq), y0, y1)
