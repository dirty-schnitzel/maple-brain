"""Side-by-side crops around the player for chosen times: strip.py run out.png t1 t2 ..."""
import json, sys
from pathlib import Path
import cv2, numpy as np
run = Path(sys.argv[1]); meta = json.loads((run / "meta.json").read_text())
tiles = []
for t in map(float, sys.argv[3:]):
    f = min(meta["frames"], key=lambda fr: abs(fr["t"] - t))
    img = cv2.imread(str(run / f["file"]))
    crop = img[430:640, 480:880].copy()
    cv2.putText(crop, f'{f["t"]:.2f}s {f["phase"]}', (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    tiles.append(crop)
cv2.imwrite(sys.argv[2], np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)]))
