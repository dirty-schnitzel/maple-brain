"""Print the player's minimap dot position for every frame of a run."""
import json, sys
from pathlib import Path
import cv2, numpy as np
run = Path(sys.argv[1]); meta = json.loads((run / "meta.json").read_text())
for f in meta["frames"]:
    img = cv2.imread(str(run / f["file"])); mm = img[66:186, 4:210]
    m = cv2.inRange(cv2.cvtColor(mm, cv2.COLOR_BGR2HSV), np.array((20, 150, 180), np.uint8), np.array((35, 255, 255), np.uint8))
    n, _, st, ce = cv2.connectedComponentsWithStats(m)
    dots = [(round(ce[i][0], 1), round(ce[i][1], 1)) for i in range(1, n) if st[i][4] >= 4 and st[i][2] <= 8 and st[i][3] <= 8]
    print(f'{f["t"]:6.2f}s {f["phase"]:12s} dot={dots}')
