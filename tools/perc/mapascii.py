"""Print a whole map as text: python tools/perc/mapascii.py MAP [--width 160]"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebrain.perception.mapascii import header, render  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("map", type=int)
ap.add_argument("--width", type=int, default=160)
a = ap.parse_args()
m = json.loads((ROOT / "assets" / "mcw" / "maps" / str(a.map) / "map.json").read_text(encoding="utf-8"))
print(header(m))
print(render(m, width=a.width))
