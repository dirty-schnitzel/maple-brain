"""Offline check of tag detection + mob candidates on a recorded run."""
import json, sys
from pathlib import Path
import cv2
sys.path.append(str(Path(__file__).parent))
from perception import find_tags, mob_candidates

run = Path(sys.argv[1]); meta = json.loads((run / "meta.json").read_text())
frames = meta["frames"]
for idx in map(int, sys.argv[2:]):
    imgs = [cv2.imread(str(run / frames[i]["file"])) for i in range(idx - 3, idx + 1)]
    tags = find_tags(imgs[-1])
    mobs, resp, bodies = mob_candidates(imgs, None)
    print(f'frame {idx} ({frames[idx]["phase"]}): resp {resp:.2f}; tags {tags}; mob candidates {mobs}')
    vis = imgs[-1].copy()
    for x, y, w, h in tags:
        cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 255, 0), 1)
    for x, y, w, h in bodies:
        cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 0, 255), 1)
    for x, y, w, h in mobs:
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
    cv2.imwrite(str(run / f"perc_{idx:03d}.png"), vis)
