"""Can a long recording be cut into its maps with nobody looking? (PLAN-data.md section 5)

The map recogniser the bot uses at a hunt's start (nav/identify.py: the on-screen minimap vs every map's minimap
in assets/mcw), run on single frames sampled along recordings whose map is known (their log.txt):
how often is the map right / unknown / WRONG, and what does one look cost?

    python tools/data/map_along.py RUN [RUN ...] [--n 60]
"""
import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebrain.nav.identify import MapIdentifier  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    ident = MapIdentifier.load(ROOT / "assets" / "mcw")
    print(f"{len(ident.canvases)} minimaps loaded")
    tot = Counter()
    ms = []
    for run in a.runs:
        m = re.search(r"^.*map (\d+) ", (run / "log.txt").read_text(encoding="utf-8", errors="replace"), re.M)
        want = int(m.group(1)) if m else None
        files = sorted((run / "frames").glob("*.png")) or sorted((run / "frames").glob("*.jpg"))
        pick = files[:: max(1, len(files) // a.n)][: a.n]
        got = Counter()
        low = 9.0
        for f in pick:
            frame = cv2.imread(str(f))
            t = time.perf_counter()
            r = ident.identify([frame])
            ms.append(1000 * (time.perf_counter() - t))
            k = "unknown" if r.map_id is None else "right" if r.map_id == want else f"WRONG {r.map_id}"
            got[k] += 1
            if r.map_id == want:
                low = min(low, r.score)
        tot.update({k.split()[0]: v for k, v in got.items()})
        print(f"{run.name:22s} map {want}: {dict(got)}  lowest right score {low:.2f}")
    ms.sort()
    print(f"\nall: {dict(tot)} of {sum(tot.values())} looks; one look p50 {ms[len(ms) // 2]:.0f} ms, p90 {ms[int(len(ms) * 0.9)]:.0f} ms")


if __name__ == "__main__":
    main()
