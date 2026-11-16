"""How exactly do tracked mobs stand on their platforms? Per replay file: sighted live tracks on a platform, their map
feet y minus the platform's surface y at their x (an exact camera: ~0, a camera off by d: d). Flying
mobs (Stirges) make it meaningless on their maps.

    python tools/perc/replay/surface_check.py RUN NAME [NAME ...]      (RUN/replay/NAME.jsonl)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
from maplebrain.config import Config  # noqa: E402
from maplebrain.nav.navmap import NavMap  # noqa: E402
import frames as rec  # noqa: E402

run = Path(sys.argv[1])
nav = NavMap.for_map(rec.map_of(run), ROOT / "assets" / "mcw", Config().nav)
plats = nav.platforms if isinstance(nav.platforms, dict) else {p.id: p for p in nav.platforms}
for name in sys.argv[2:]:
    dy, cam = [], []
    for line in open(run / "replay" / f"{name}.jsonl", encoding="utf-8"):
        k = json.loads(line)
        for m in k["mobs"]:
            if m["state"] == "live" and m["src"] != "none" and not m["air"] and m["platform"] in plats:
                yp = plats[m["platform"]].y_at(m["x"])
                if yp is not None:
                    dy.append(m["y"] - yp)
        cam.append(k.get("cam_src"))
    dy = np.array(dy)
    q = lambda v, p: round(float(np.percentile(v, p)), 1)   # noqa: E731
    src = {c: cam.count(c) for c in set(cam)}
    print(f"{run.name} {name}: mob feet - surface on {len(dy)} sightings: p5/p50/p95 {q(dy, 5)} {q(dy, 50)} {q(dy, 95)}, "
          f"|.|<=2 px {100 * np.mean(np.abs(dy) <= 2):.1f} %, <=4 {100 * np.mean(np.abs(dy) <= 4):.1f} %; camera {src}")
