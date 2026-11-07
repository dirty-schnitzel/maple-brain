"""Offline check of brain-v2's own position (M1 step 1) on a recording with frames (+ keys.jsonl).

    python tools/nav/selfstate_eval.py RUN [MAP_ID] [--max N] [--out selfstate.jsonl]

Replays the saved frames through PlatformShift -> Camera -> SelfTracker (as live, but at the saved frames' rate)
and reports: fine x vs the rope we hang on, vs the minimap; ground platform vs obs.platform; the states over time;
whether "air" follows a jump / drop key or a walk off an edge; whether grabs (jump then up) end on a rope.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebot.config import Keys                            # noqa: E402
from maplebot.nav.navmap import NavMap                      # noqa: E402
from maplebot.nav.selfstate import SelfTracker              # noqa: E402
from maplebot.perception.camshift import PlatformShift      # noqa: E402
from maplebot.perception.world import Camera                # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("map", nargs="?", type=int)
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--out", default="selfstate.jsonl")
    a = ap.parse_args()
    run = Path(a.run)
    map_id = a.map
    if map_id is None:
        m = re.search(r"map (\d+)", (run / "log.txt").read_text(encoding="utf-8", errors="replace"))
        map_id = int(m.group(1))
    assets = ROOT / "assets" / "mcw"
    mj = json.loads((assets / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
    nav = NavMap.from_json(mj)
    rows = {}
    for line in (run / "ticks.jsonl").open():
        r = json.loads(line)
        if r.get("frame"):
            rows[r["n"]] = r
    keys = [json.loads(k) for k in (run / "keys.jsonl").open()] if (run / "keys.jsonl").exists() else []
    ns = sorted(rows)[:a.max or None]
    ps, cam, me_t = PlatformShift(nav), Camera(mj.get("vrBounds"), leash=24.0), SelfTracker(nav, window=0.35)
    out, n_fallback = [], 0
    for n in ns:
        r = rows[n]
        o = r["obs"]
        img = cv2.imread(str(run / "frames" / r["frame"]))
        me = (o["me"][0], o["me"][1]) if o.get("me") else None
        d = ps.update(img, cam.C, me, o["t"])
        if d is None and cam.C is not None:
            n_fallback += 1
        C = cam.update(d, me, o.get("map_pos"))
        me_map = (me[0] + C[0], me[1] + C[1]) if me is not None and C is not None else None
        s = me_t.update(o["t"], me_map, o.get("map_pos"))
        if s is None:
            continue
        out.append({"n": n, "t": o["t"], **s.as_dict(), "mm": o.get("map_pos"), "mm_platform": o.get("platform"),
                    "mm_rope": o.get("rope")})
    with (run / a.out).open("w") as f:
        for e in out:
            f.write(json.dumps(e) + "\n")
    report(out, nav, keys, n_fallback)


def _pct(v, q=(10, 50, 90)):
    return np.percentile(v, q).round(1).tolist() if len(v) else "-"


def report(out, nav, keys, n_fallback):
    tag = [e for e in out if e["src"] == "tag"]
    print(f"frames {len(out)}, tag {len(tag)} ({100 * len(tag) / max(1, len(out)):.1f} %), "
          f"camera by scene fallback {n_fallback}")
    st = {k: sum(e["state"] == k for e in out) for k in ("ground", "rope", "air")}
    print("states", st)
    rope = [e for e in tag if e["state"] == "rope"]
    print("rope: x - rope x (tag)", _pct([e["x"] - nav.rope(e["rope"]).x for e in rope]))
    mmr = [e for e in out if e["mm_rope"] is not None]
    print(f"minimap says rope: {len(mmr)} frames, we say rope {sum(e['state'] == 'rope' for e in mmr)}, "
          f"ground {sum(e['state'] == 'ground' for e in mmr)}, air {sum(e['state'] == 'air' for e in mmr)}")
    print("tag x - minimap x", _pct([e["x"] - e["mm"][0] for e in tag if e["mm"]]),
          "abs median", np.median([abs(e["x"] - e["mm"][0]) for e in tag if e["mm"]]).round(1))
    g = [e for e in tag if e["state"] == "ground"]
    print("ground: y - surface (0 = snapped)", _pct([e["y"] - nav.platforms[e["platform"]].y_at(e["x"]) for e in g]))
    agree = [e for e in g if e["mm_platform"] is not None]
    print(f"ground platform == minimap's: {sum(e['platform'] == e['mm_platform'] for e in agree)} / {len(agree)}")
    # air episodes: what started them
    downs = [(k["t"], k["key"]) for k in keys if k.get("down")]
    eps, cur = [], None
    for e in out:
        if e["state"] == "air":
            cur = cur or [e, e]
            cur[1] = e
        elif cur:
            eps.append((cur[0], cur[1], e))
            cur = None
    cause = {"jump": 0, "drop": 0, "rope_off": 0, "edge/other": 0}
    for a, b, after in eps:
        ks = [k for t, k in downs if a["t"] - 0.6 <= t <= a["t"] + 0.05]
        if Keys.jump in ks and "down" in ks:
            cause["drop"] += 1
        elif Keys.jump in ks:
            cause["jump"] += 1
        elif any(p["state"] == "rope" for p in out if a["t"] - 0.5 <= p["t"] < a["t"]):
            cause["rope_off"] += 1
        else:
            cause["edge/other"] += 1
    lens = [b["t"] - a["t"] for a, b, _ in eps]
    print(f"air episodes {len(eps)}: started by {cause}; length s {_pct(lens)}; ended "
          f"{ {k: sum(x['state'] == k for _, _, x in eps) for k in ('ground', 'rope')} }")
    # grabs: jump then up within 0.5 s -> rope within 1 s?
    grabs = [t for t, k in downs if k == "up" and any(k2 == Keys.jump and 0 <= t - t2 <= 0.5 for t2, k2 in downs)]
    ok = sum(any(e["state"] == "rope" and 0 <= e["t"] - t <= 1.0 for e in out) for t in grabs)
    print(f"grabs (shift then up): {len(grabs)}, on a rope within 1 s: {ok}")


if __name__ == "__main__":
    main()
