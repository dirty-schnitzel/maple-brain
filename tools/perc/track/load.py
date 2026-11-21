"""Tracker plan (PLAN-tracker.md), shared loaders: a capture's ticks (every frame's FrameFacts: the fit's mobs at
the live rate, no frames needed), tracklets = the fit's mobs linked over consecutive ticks (no memory beyond one
tick: the raw material of the hindsight truth), the map's spawn points / platforms / mob data.

    from load import ticks, tracklets, Map

A capture (`cap`) = a stay of the bank, its id SESSION#K (tools/perc/frames.py `clip`), or a run folder. Its ticks:
a hunt's own ticks.jsonl when it has one (a run folder of the bot), else the kept replay (dump.py: the live
Perceiver over every frame) - a `record` capture ran no perception, so its "ticks" are that replay.
"""
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
ASSETS = ROOT / "assets" / "mcw"


def clip(cap):
    import frames as rec
    return rec.clip(str(cap), False, "track")


def run_path(cap) -> Path:
    """The folder holding the capture's frames (a stay's folder in the bank, or the run folder)."""
    return clip(cap).run


def out_path(cap) -> Path:
    """Where the tools write for this capture: CORPUS/work/SESSION#K (a run folder: itself)."""
    return clip(cap).out


def name_of(cap) -> str:
    return clip(cap).name


def map_of(cap) -> int:
    return clip(cap).map_id


def ticks(cap, refresh: bool = False) -> list:
    """Every tick of a capture, the fields the tracker work needs:
    n, t, frame, C (scene camera or None), fit [FitMob dicts] or None, mobs (today's tracker's tracks), me (our
    tag: x, y, w, h on screen), me_map, self (SelfState dict; None in a replay), swing (the brain's press this tick
    or None), held, exp, tags, patches, hints, mode, target, hp, ms, explained."""
    c = clip(cap)
    if not (c.run / "ticks.jsonl").exists():
        from dump import rows
        out = []
        for r in rows(cap):
            f = r["facts"]
            out.append({"n": r["n"], "t": r["t"], "frame": r["frame"], "C": r["C"], "fit": f.get("fit"),
                        "mobs": r["mobs"] or [], "me": r["me"], "me_map": r["me_map"], "self": None, "swing": None,
                        "held": [], "exp": f.get("exp_points"), "tags": f.get("tags") or [], "patches": f.get("patches"),
                        "hints": f.get("fit_hints"), "mode": None, "target": None, "facing": None, "hp": f.get("hp"),
                        "tag": f.get("tag"), "paused": None, "ms": r["ms"].get("observe"),
                        "explained": r.get("explained"), "drops": f.get("drops")})
        return out
    run = c.run
    cache = c.out / "track" / "ticks.pkl"
    if cache.exists() and not refresh and cache.stat().st_mtime >= (run / "ticks.jsonl").stat().st_mtime:
        return pickle.loads(cache.read_bytes())
    out = []
    with open(run / "ticks.jsonl", encoding="utf-8") as f:
        for line in f:
            k = json.loads(line)
            o, tm, fa = k["obs"], k.get("timings") or {}, k.get("facts") or {}
            v2 = tm.get("v2") or {}
            out.append({"n": k["n"], "t": o["t"], "frame": k.get("frame"), "C": fa.get("scene_cam") or o.get("scene_cam"),
                        "fit": fa.get("fit"), "mobs": o.get("mobs") or [], "me": o.get("me"), "me_map": o.get("me_map"),
                        "self": tm.get("self"), "swing": v2.get("swing"), "held": tm.get("held") or [],
                        "exp": fa.get("exp_points"), "tags": fa.get("tags") or [], "patches": fa.get("patches"),
                        "hints": fa.get("fit_hints"), "mode": v2.get("mode"), "target": v2.get("target"),
                        "facing": v2.get("facing"), "hp": fa.get("hp"), "tag": fa.get("tag"),
                        "paused": tm.get("paused"), "ms": tm.get("total_ms")})
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(pickle.dumps(out))
    return out


def keys(cap) -> list:
    p = run_path(cap) / "keys.jsonl"
    return [json.loads(x) for x in open(p, encoding="utf-8")] if p.exists() else []


class Map:
    def __init__(self, map_id: int):
        from maplebrain.config import Config
        from maplebrain.nav.navmap import NavMap
        self.id = map_id
        self.json = json.loads((ASSETS / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        self.nav = NavMap.for_map(map_id, ASSETS, Config().nav)
        self.spawns = self.json.get("mobs") or []
        self.mobs = {}
        for i in sorted({s["id"] for s in self.spawns}):
            self.mobs[i] = json.loads((ASSETS / "mobs" / str(i) / "mob.json").read_text(encoding="utf-8"))
        self.names = {i: m.get("name", str(i)) for i, m in self.mobs.items()}

    def spawn_dist(self, mob_id, x, y) -> tuple:
        """(distance in x to the nearest spawn point of this type whose ground is within 40 px in y, its index)."""
        best = (1e9, None)
        for s in self.spawns:
            if s["id"] == mob_id and abs(s["y"] - y) <= 40:
                d = abs(s["x"] - x)
                if d < best[0]:
                    best = (d, s["index"])
        return best

    def platform(self, x, y, tol=16):
        return self.nav.platform_at(x, y, tol=tol)


def anim_of(pose: str) -> str:
    return pose.rsplit("_", 1)[0]


def tracklets(tk: list, gate: float = 14.0, gate_v: float = 500.0, max_gap: int = 0) -> list:
    """The fit's mobs linked tick to tick: same type, nearest first, within gate + gate_v * dt px (x and y).
    `max_gap`: ticks a tracklet may go unseen and still continue (0 = strictly consecutive fit ticks).
    -> [{"id", "type", "pts": [(i, t, x, y, pose, facing, o, tint, seen, covered, n_seen, sx, sy)]}] in map
    coordinates (feet + C); i = index into tk. Ticks without a camera / fit break nothing by themselves (they count
    as unseen ticks)."""
    out, act = [], []                                   # act: [tracklet, last index]
    nid = 0
    for i, k in enumerate(tk):
        if k["fit"] is None or k["C"] is None:
            continue
        C, t = k["C"], k["t"]
        det = [(m["type"], m["feet"][0] + C[0], m["feet"][1] + C[1], m) for m in k["fit"]]
        pairs = []
        for a, (tr, li) in enumerate(act):
            lt, lx, ly = tr["pts"][-1][1], tr["pts"][-1][2], tr["pts"][-1][3]
            g = gate + gate_v * max(0.0, t - lt)
            for b, (ty, x, y, m) in enumerate(det):
                if ty == tr["type"] and abs(x - lx) <= g and abs(y - ly) <= g:
                    pairs.append((abs(x - lx) + abs(y - ly), a, b))
        pairs.sort()
        ua, ub = set(), set()
        for _, a, b in pairs:
            if a in ua or b in ub:
                continue
            ua.add(a)
            ub.add(b)
            ty, x, y, m = det[b]
            act[a][0]["pts"].append((i, t, x, y, m["pose"], m["facing"], m["opacity"], m.get("tint", ""), m["seen"],
                                     m["covered"], m["n_seen"], m["feet"][0], m["feet"][1]))
            act[a][1] = i
        for b, (ty, x, y, m) in enumerate(det):
            if b in ub:
                continue
            tr = {"id": nid, "type": ty, "pts": [(i, t, x, y, m["pose"], m["facing"], m["opacity"], m.get("tint", ""),
                                                 m["seen"], m["covered"], m["n_seen"], m["feet"][0], m["feet"][1])]}
            nid += 1
            out.append(tr)
            act.append([tr, i])
        # close the ones unseen too long (counted in fit ticks)
        act = [[tr, li] for tr, li in act if _fit_ticks_between(tk, li, i) <= max_gap]
    return out


def _fit_ticks_between(tk, a, b) -> int:
    return sum(1 for j in range(a + 1, b + 1) if tk[j]["fit"] is not None and tk[j]["C"] is not None)


def pct(v, ps=(5, 50, 95)):
    import numpy as np
    v = np.asarray(v, float)
    return [round(float(np.percentile(v, p)), 2) for p in ps] if len(v) else None
