"""Tracker plan, data first: what the client files say about the mobs of a map (speed, knockback, anim lengths) and its
spawn points.

    python tools/perc/track/peek_assets.py MAP [MAP ...]
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
A = ROOT / "assets" / "mcw"

for mid in sys.argv[1:]:
    m = json.loads((A / "maps" / mid / "map.json").read_text(encoding="utf-8"))
    print(f"== map {mid} {m.get('name')}: {len(m.get('footholds') or {})} footholds, layers "
          f"{sorted({f['layerId'] for f in m['footholds'].values()})}, vr {m.get('vrBounds')}")
    sp = m.get("mobs") or []
    print(f"  spawns {len(sp)}; keys of one: {sorted(sp[0]) if sp else None}")
    for i, n in Counter(s["id"] for s in sp).items():
        ex = next(s for s in sp if s["id"] == i)
        print(f"   mob {i} x{n}: e.g. {ex}")
    for i in sorted({s["id"] for s in sp}):
        d = json.loads((A / "mobs" / str(i) / "mob.json").read_text(encoding="utf-8"))
        info = d.get("info") or {}
        print(f"  mob {i} {d.get('name')}: info {json.dumps(info)}")
        for anim, fr in (d.get("frames") or {}).items():
            print(f"     {anim:8s} {len(fr)} frames, delays {[f.get('delay') for f in fr]}, "
                  f"a0/a1 {[(f.get('a0'), f.get('a1')) for f in fr if f.get('a0') is not None or f.get('a1') is not None]}"
                  f" keys {sorted(set().union(*[set(f) for f in fr]))}")
