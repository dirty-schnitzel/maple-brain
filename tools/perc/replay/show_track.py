"""Draw the tracks of two replays near time T on the frame: A red, B green, with type and score.

    python tools/perc/replay/show_track.py RUN A B T OUT.png
"""
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402

run, A, B, T, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]
load = lambda n: [json.loads(l) for l in open(run / "replay" / f"{n}.jsonl", encoding="utf-8")]   # noqa: E731
ra, rb = load(A), load(B)
i = min(range(len(ra)), key=lambda j: abs(ra[j]["t"] - T))
f = rec.read(run, ra[i]["frame"])
for rows, col, dy in ((ra, (0, 0, 255), -14), (rb, (0, 255, 0), 0)):
    for m in rows[i]["mobs"]:
        if m["state"] in ("offscreen",):
            continue
        x, y = int(m["sx"]), int(m["sy"])
        cv2.circle(f, (x, y), 4, col, 2)
        cv2.putText(f, f"{m['mob']} {m['state'][:4]} {m['src']} {m['score']}", (x - 40, y + 18 + dy), cv2.FONT_HERSHEY_PLAIN,
                    0.9, col, 1)
print(ra[i]["t"], ra[i]["frame"], "A cam", ra[i]["cam"], "B cam", rb[i]["cam"])
cv2.imwrite(out, f)
