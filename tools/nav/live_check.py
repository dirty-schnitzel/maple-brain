"""Quick look at a live run's loop + camera: python tools/nav/live_check.py RUN
Loop stalls (tick gaps), camera source (platform strips vs scene fallback), our tag + camera vs the minimap and
the rope we're on, and the actions sent."""
import collections
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebot.nav.navmap import NavMap  # noqa: E402


def main(run):
    run = Path(run)
    rows = [json.loads(line) for line in (run / "ticks.jsonl").open()]
    o = [r["obs"] for r in rows]
    t = np.array([x["t"] for x in o])
    gaps = np.diff(t)
    print(f"ticks {len(o)} over {t[-1] - t[0]:.0f} s = {len(o) / (t[-1] - t[0]):.1f} fps; gaps > 0.3 s: "
          f"{(gaps > 0.3).sum()} ({gaps[gaps > 0.3].sum():.1f} s), max {gaps.max():.2f}; p99 {np.percentile(gaps, 99):.3f}")
    print("cam_src", collections.Counter(x.get("cam_src") for x in o))
    d = [(x["me_map"][0] - x["map_pos"][0], x["me_map"][1] - x["map_pos"][1]) for x in o
         if x.get("me_map") and x.get("map_pos")]
    if d:
        d = np.array(d)
        print("me_map - minimap x p10/50/90", np.percentile(d[:, 0], [10, 50, 90]).round(1),
              "abs median", np.median(abs(d[:, 0])).round(1), "| at the leash (>= 23.5):", (abs(d[:, 0]) >= 23.5).sum())
    rp = [x["me_map"][0] - x["rope"] for x in o if x.get("me_map") and x.get("rope") is not None]
    if rp:
        print(f"on a rope (minimap) {len(rp)} ticks: me_map x - rope x", np.percentile(rp, [10, 50, 90]).round(1))
    m = re.search(r"map (\d+)", (run / "log.txt").read_text(encoding="utf-8", errors="replace")) if (run / "log.txt").exists() else None
    if m:
        nav = NavMap.for_map(int(m.group(1)), ROOT / "assets" / "mcw")
        ys = [x["me_map"][1] - nav.platforms[x["platform"]].y_at(x["me_map"][0]) for x in o
              if x.get("me_map") and x.get("platform") and nav.platforms[x["platform"]].y_at(x["me_map"][0]) is not None]
        if ys:
            print("on a platform: me_map y - surface p10/50/90", np.percentile(ys, [10, 50, 90]).round(1))
    acts = collections.Counter()
    for r in rows:
        for a in r.get("actions") or []:
            acts[str(a)[:40]] += 1
    print("actions (top 12):", acts.most_common(12))
    print("modes", collections.Counter(r["mode"] for r in rows).most_common())


import re  # noqa: E402

if __name__ == "__main__":
    main(sys.argv[1])
