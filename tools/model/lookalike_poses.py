"""Poses of one mob that share ONE picture under two origins (the client's `_inlink` frames, e.g. Bubbling's jump =
its move_3 picture drawn 17 px lower): the fit cannot tell them apart by pixels, so the feet it reports are off by
the origin difference whenever it names the wrong one. Which mobs, and by how much?

    python tools/model/lookalike_poses.py

Reads assets/mcw/mobs only.
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / "assets" / "mcw"

from maplebrain.perception.vote import _pic  # noqa: E402


def main():
    rows = []
    n_mobs = 0
    for d in sorted((ASSETS / "mobs").iterdir(), key=lambda p: int(p.name)):
        info = json.loads((d / "mob.json").read_text(encoding="utf-8"))
        link = info.get("link")
        link_dir = ASSETS / "mobs" / str(int(link)) if link not in (None, "") else None
        frames = info.get("frames") or {}
        by = defaultdict(list)
        n_mobs += 1
        for anim, fs in frames.items():
            for i, f in enumerate(fs or []):
                im = _pic(d, f, frames, link_dir)
                if im is None or (im[..., 3] > 0).sum() < 60:
                    continue
                h, w = im.shape[:2]
                ox, oy = f.get("origin") or (w // 2, h)
                by[hashlib.sha1(im.tobytes()).hexdigest()].append((anim, i, int(ox), int(oy)))
        worst = None
        for v in by.values():
            for a in v:
                for b in v:
                    if a < b and (a[2], a[3]) != (b[2], b[3]) and a[0] != b[0]:
                        dy, dx = abs(a[3] - b[3]), abs(a[2] - b[2])
                        if worst is None or dy + dx > worst[0]:
                            worst = (dy + dx, f"{a[0]}_{a[1]} / {b[0]}_{b[1]}", dx, dy)
        if worst is not None:
            rows.append((info["name"], int(d.name), "jump" in info["framebooks"], worst))
    print(f"{len(rows)} of {n_mobs} mobs have two poses of different animations sharing one picture under two origins:")
    for name, i, jumper, w in sorted(rows, key=lambda r: -r[3][0]):
        print(f"   {name:26s} ({i:5d}) {'jumper' if jumper else '      '}  {w[1]:28s} feet differ by dx {w[2]:3d}, dy {w[3]:3d} px")


if __name__ == "__main__":
    main()
