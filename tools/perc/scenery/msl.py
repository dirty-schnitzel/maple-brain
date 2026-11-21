"""Shared helpers of the moving-scenery prototypes (PLAN-moving-scenery.md; tools/perc/scenery/README.md).

Everything these tools write goes to OUT = CORPUS/work/scenery (the bank's work folder: safe to delete, made again
by the tools). Run them from the repo root with the venv python: `python tools/perc/scenery/<tool>.py ...`."""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
for p in (ROOT, ROOT / "tools" / "perc", ROOT / "tools" / "perc" / "track", ROOT / "tools" / "perc" / "replay"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from maplebrain.config import corpus_root                      # noqa: E402
from maplebrain.gamedata import EXPORT                         # noqa: E402

OUT = Path(corpus_root()) / "work" / "scenery"
OUT.mkdir(parents=True, exist_ok=True)
PLAY_H, SW = 700, 1366


def recording() -> list:
    inc = Path(corpus_root()) / "incoming"
    return [p.name for p in inc.iterdir() if p.is_dir()] if inc.exists() else []


def guard():
    """GPU prototypes: not while the user records."""
    r = recording()
    if r:
        raise SystemExit(f"the user is recording ({r}): not now")


def clip(cap):
    import frames as rec
    return rec.clip(cap, False, "moving-scenery plan")


def kept(cap):
    """The kept replay's rows of `cap` (camera per frame etc.), or None when it has none."""
    import dump
    try:
        return dump.rows(cap)
    except (FileNotFoundError, SystemExit):
        return None


def scene_of(map_id):
    from maplebrain.scene import Scene
    return Scene.load(int(map_id))


def save(name, img):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(p), img)
    return p


def tile(imgs, cols=2, scale=1.0, pad=4, labels=None):
    """A sheet of same-size BGR images."""
    h, w = imgs[0].shape[:2]
    if scale != 1.0:
        imgs = [cv2.resize(i, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) for i in imgs]
        h, w = imgs[0].shape[:2]
    rows = -(-len(imgs) // cols)
    sheet = np.full((rows * (h + pad) + pad, cols * (w + pad) + pad, 3), 40, np.uint8)
    for k, im in enumerate(imgs):
        r, c = divmod(k, cols)
        y, x = pad + r * (h + pad), pad + c * (w + pad)
        sheet[y:y + h, x:x + w] = im
        if labels:
            cv2.putText(sheet, labels[k], (x + 6, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
            cv2.putText(sheet, labels[k], (x + 6, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return sheet
