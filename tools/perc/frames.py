"""Reading a recording's saved frames - with the capture's column error undone.

2026-11-16: until the fix in `capture.game_columns`, a dark left edge column at calibration made the native crop
(1, 1367): the whole picture 1 px LEFT of its place and the last column from outside the window. Recordings hit
(Ant Tunnel IV 20261116_012059_1, Dangerous Steam 20261116_084844_2) carry a file RUN/xshift.txt holding `1`;
`read` moves their picture back (column 0 is then unknown: a copy of column 1).

    python tools/perc/frames.py RUN [RUN ...]     measure each recording's shift with the scene model (needs
                                                  `assets scene`), write / remove RUN/xshift.txt
"""
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def xshift(run: Path) -> int:
    f = Path(run) / "xshift.txt"
    return int(f.read_text().strip()) if f.exists() else 0


def unshift(frame: np.ndarray, s: int) -> np.ndarray:
    """The picture moved `s` px right (to its place); the first `s` columns repeat the first known one."""
    if not s:
        return frame
    out = np.empty_like(frame)
    out[:, s:] = frame[:, :-s]
    out[:, :s] = frame[:, :1]
    return out


def read(run: Path, name: str, shift: int | None = None) -> np.ndarray | None:
    frame = cv2.imread(str(Path(run) / "frames" / name))
    if frame is None:
        return None
    return unshift(frame, xshift(run) if shift is None else shift)


def map_of(run: Path) -> int:
    log = (Path(run) / "log.txt").read_text(encoding="utf-8", errors="replace")
    return int((re.search(r"map recognised: (\d+)", log) or re.search(r"\bmap (\d+) ", log)).group(1))


def measure(run: Path, n: int = 20) -> int:
    """How many of the frame's last columns are not the game's (0 = the capture was right): per column the share
    of opaque tile / object pixels the scene explains at the registered camera - a column from outside the window
    explains ~0 %."""
    import torch
    from maplebrain.scene import PLAY_H, Scene
    scene = Scene.load(map_of(run))
    ticks = [json.loads(l) for l in open(Path(run) / "ticks.jsonl", encoding="utf-8")]
    ticks = [k for k in ticks if k.get("frame") and k["obs"].get("cam")]
    ticks = [ticks[int(i * (len(ticks) - 1) / max(1, n - 1))] for i in range(min(n, len(ticks)))]
    ok, tot = np.zeros(1366), np.zeros(1366)
    for k in ticks:
        frame = read(run, k["frame"], shift=0)
        ft = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(scene.dev)
        reg = scene.locate(ft, seed=k["obs"]["cam"])
        if reg is None:
            continue
        e, _ = scene.expected(reg[0])
        solid = scene._crop(reg[0], 1366, PLAY_H)[..., 3] > 250
        ok += (((ft.float() - e).abs().amax(dim=2) <= 4) & solid).sum(0).cpu().numpy()
        tot += solid.sum(0).cpu().numpy()
    share = ok / np.maximum(1, tot)
    mid = float(np.median(share[100:1266]))
    s = 0
    while s < 4 and tot[1365 - s] > 200 and share[1365 - s] < 0.3 * mid:
        s += 1
    return s


if __name__ == "__main__":
    for a in sys.argv[1:]:
        run = Path(a)
        s = measure(run)
        f = run / "xshift.txt"
        if s:
            f.write_text(str(s))
        elif f.exists():
            f.unlink()
        print(f"{run}: the picture is {s} px left of its place" + (" -> xshift.txt" if s else " (capture right)"))
