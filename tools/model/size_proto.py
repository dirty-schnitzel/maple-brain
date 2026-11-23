"""How big is the state, stored for every frame? (docs/prompts/tracker-plan.md, Part 1: "small enough to store every
frame of hours of recordings"). A stand-in built from the kept replay: today's tracks play the mobs, the drop
finder's resting sightings the drops, the name tags the players - the SHAPES and COUNTS are what is measured, with
the record layouts docs/state_model.md proposes.

    python tools/model/size_proto.py CAP

Tables: `frame` one row a frame (the view, us, the HUD); `mob` one row per mob per frame while it is seen, and one row
when a field of an unseen one changes; `drop` one row per drop (its life) + one per change of how it is seen;
`player` one row per player per frame while seen; `event` one row each. Reads only, no GPU.
"""
import io
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "track"))

FRAME = np.dtype([("n", "u4"), ("t", "f8"), ("view_x", "i2"), ("view_y", "i2"), ("x", "i2"), ("y", "i2"),
                  ("place", "u1"), ("node", "i2"), ("left", "i2"), ("off", "i1"), ("vx", "i2"), ("vy", "i2"),
                  ("facing", "i1"), ("act", "u1"), ("seen", "u1"), ("hp", "u2"), ("hp_max", "u2"), ("mp", "u2"),
                  ("mp_max", "u2"), ("exp", "u4"), ("keys", "u4")])
MOB = np.dtype([("n", "u4"), ("id", "u4"), ("kind", "u2"), ("x", "i2"), ("y", "i2"), ("place", "u1"), ("node", "i2"),
                ("left", "i2"), ("off", "i1"), ("vx", "i2"), ("vy", "i2"), ("facing", "i1"), ("anim", "u1"),
                ("frame", "u1"), ("opacity", "u1"), ("life", "u1"), ("seen", "u1"), ("vis", "u1"), ("cover", "u1"),
                ("hits", "u1"), ("lo", "i2"), ("hi", "i2")])
DROP = np.dtype([("id", "u4"), ("item", "u4"), ("x", "i2"), ("y", "i2"), ("node", "i2"), ("n0", "u4"), ("n1", "u4"),
                 ("end", "u1"), ("mob", "u4")])
DROP_SEEN = np.dtype([("n", "u4"), ("id", "u4"), ("seen", "u1"), ("cover", "u1")])
PLAYER = np.dtype([("n", "u4"), ("id", "u4"), ("x", "i2"), ("y", "i2"), ("place", "u1"), ("node", "i2"), ("off", "i1"),
                   ("seen", "u1")])
EVENT = np.dtype([("n", "u4"), ("kind", "u1"), ("a", "u4"), ("b", "u4"), ("v", "f4"), ("how", "u1")])


def packed(arrs: dict) -> int:
    b = io.BytesIO()
    np.savez_compressed(b, **arrs)
    return b.tell()


def main():
    cap = sys.argv[1]
    import dump
    t0 = time.perf_counter()
    rows = dump.rows(cap)
    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    fr = np.zeros(len(rows), FRAME)
    mob, players, dseen, events = [], [], [], []
    last = {}                                             # track id -> the fields last written while unseen
    drops, open_d = [], {}                                # a drop's life: key (item, map x, fh) -> [n0, n1]
    last_exp = last_hp = None
    for k, r in enumerate(rows):
        C = r["C"]
        f = r["facts"]
        me = r["me_map"]
        hp, mp = f.get("hp") or (0, 0), f.get("mp") or (0, 0)
        fr[k] = (r["n"], r["t"], *(C if C else (-32768, -32768)), *(me if me else (-32768, -32768)), 0, 0, 0, 0, 0, 0,
                 0, 0, me is not None, hp[0], hp[1], mp[0], mp[1], f.get("exp_points") or 0, 0)
        if f.get("exp_points") is not None:
            if last_exp is not None and f["exp_points"] != last_exp:
                events.append((r["n"], 1, 0, 0, f["exp_points"] - last_exp, 0))
            last_exp = f["exp_points"]
        if f.get("hp"):
            if last_hp is not None and hp[0] != last_hp:
                events.append((r["n"], 2, 0, 0, hp[0] - last_hp, 0))
            last_hp = hp[0]
        ids = set()
        for m in r["mobs"] or []:
            if m["state"] == "tentative":
                continue
            ids.add(m["id"])
            seen = m["src"] != "none"
            row = (r["n"], m["id"], m["mob"] % 65536, int(m["x"]), int(m["y"]), 0 if not m["air"] else 1,
                   m["platform"] or 0, 0, 0, int(m["vx"]), 0, 1 if m["facing"] == "right" else -1, 0, 0, 255, 1, seen,
                   int(255 * m["vis"]), 0, 0, int(m["x"]) - 20, int(m["x"]) + 20)
            if seen:
                mob.append(row)
                last.pop(m["id"], None)
            else:                                         # unseen: a row only when what is stored of it changes
                key = (m["state"], int(m["x"]) // 8, m["platform"])
                if last.get(m["id"]) != key:
                    mob.append(row)
                    last[m["id"]] = key
        for i in [i for i in last if i not in ids]:
            last.pop(i)
            events.append((r["n"], 3, i, 0, 0, 0))        # ended
        if C is not None:
            now = set()
            for d in f.get("drops") or []:
                if d.get("kind") != "rest":
                    continue
                key = (d["item"], d["feet"][0] + C[0], d.get("fh"))
                now.add(key)
                if key not in open_d:
                    open_d[key] = [r["n"], r["n"], d["feet"][1] + C[1]]
                    dseen.append((r["n"], len(drops) + len(open_d), 1, 0))
                open_d[key][1] = r["n"]
            for key in [k2 for k2, v in open_d.items() if r["n"] - v[1] > 180]:
                v = open_d.pop(key)
                drops.append((len(drops), key[0], key[1], v[2], key[2] or 0, v[0], v[1], 0, 0))
                dseen.append((r["n"], len(drops), 0, 0))
        tag = f.get("tag")
        for x, y, w, h in f.get("tags") or []:
            if tag is not None and abs(x - tag[0]) < 12 and abs(y - tag[1]) < 8:
                continue
            if C is not None:
                players.append((r["n"], 0, int(x + w / 2 + C[0]), int(y + C[1]), 0, 0, 0, 1))
    for key, v in open_d.items():
        drops.append((len(drops), key[0], key[1], v[2], key[2] or 0, v[0], v[1], 0, 0))
    arrs = {"frame": fr, "mob": np.array(mob, MOB), "drop": np.array(drops, DROP), "drop_seen": np.array(dseen, DROP_SEEN),
            "player": np.array(players, PLAYER), "event": np.array(events, EVENT)}
    t_build = time.perf_counter() - t0
    secs = rows[-1]["t"] - rows[0]["t"]
    raw = sum(a.nbytes for a in arrs.values())
    t0 = time.perf_counter()
    z = packed(arrs)
    t_pack = time.perf_counter() - t0
    print(f"{cap}: {len(rows)} frames, {secs / 60:.1f} minutes (loading the kept replay {t_load:.0f} s, building the tables "
          f"{t_build:.1f} s, packing {t_pack:.1f} s)")
    for name, a in arrs.items():
        print(f"   {name:10s} {len(a):9d} rows x {a.dtype.itemsize:3d} bytes = {a.nbytes / 1e6:7.2f} MB   "
              f"({len(a) / len(rows):.2f} rows a frame; packed alone {packed({name: a}) / 1e6:.2f} MB)")
    print(f"   total raw {raw / 1e6:.1f} MB = {raw / len(rows):.0f} bytes a frame = {raw / 1e6 / (secs / 3600):.0f} MB an hour; "
          f"packed (npz, zlib) {z / 1e6:.1f} MB = {z / len(rows):.0f} bytes a frame = {z / 1e6 / (secs / 3600):.0f} MB an hour")
    # what the same frames cost today as text (ticks.jsonl-like) and as the kept replay
    m = dump.meta(cap)
    print(f"   beside it: the kept replay of these frames {m['bytes'] / 1e6:.0f} MB (rows + bitmaps)")


if __name__ == "__main__":
    main()
