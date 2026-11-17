"""Which maps should the recording corpus hold? (PLAN-data.md section 3)

From the client data only (assets/mcw + assets/scene): every map with mob spawns, its mob types, its background
set(s), and whether its scene is clean (no moving backgrounds: the only maps perception hunts on today).
Prints (1) what the maps already recorded cover, (2) the shortest list of further clean maps that adds every
remaining mob type and background set (greedy; ties -> more spawns), (3) one map per background family that only
moving-background maps have. A map counts for a mob type only with `--min-spawns` (3) spawn points of it: one
spawn point is a mob met a few times in 5 minutes, or never on a crowded map.

    python tools/data/map_cover.py [--have ID ...] [--max-level N]
`--have`: maps already recorded natively (default: the 7 of 2026-11-17). `--max-level`: skip maps whose strongest
mob is above this (what our character survives).
"""
import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCW, SCENE = ROOT / "assets" / "mcw", ROOT / "assets" / "scene"
HAVE = [10003061, 10003062, 10004040, 10004041, 10005063, 10005064, 10005065]


def load(min_spawns: int = 3):
    mobs = {}
    for p in (MCW / "mobs").glob("*/mob.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        mobs[d["id"]] = d
    maps = {}
    for p in SCENE.glob("*/scene.json"):
        mid = int(p.parent.name)
        s = json.loads(p.read_text())
        m = json.loads((MCW / "maps" / str(mid) / "map.json").read_text(encoding="utf-8"))
        count = Counter(int(x["id"]) for x in m.get("mobs") or [])
        ids = sorted(i for i, c in count.items() if c >= min_spawns)
        maps[mid] = dict(id=mid, name=m["name"] or "", street=m["streetName"] or "", mobs=ids,
                         sets=sorted({b["set"] for b in s["backs"]}), clean=all(b["known"] for b in s["backs"]),
                         anim=s["animated"], spawns=len(m.get("mobs") or []), count=dict(count),
                         lv=[mobs[i]["info"]["level"] for i in ids if i in mobs and mobs[i]["info"].get("level")])
    return maps, mobs


def items(m):
    return {("mob", i) for i in m["mobs"]} | {("set", s) for s in m["sets"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--have", type=int, nargs="*", default=HAVE)
    ap.add_argument("--max-level", type=int, default=999)
    ap.add_argument("--min-spawns", type=int, default=3)
    a = ap.parse_args()
    maps, mobs = load(a.min_spawns)
    name = lambda k, i: mobs[i]["name"] if k == "mob" else i
    line = lambda m: f"{m['id']:>9} {m['street'][:20]:20s} | {m['name'][:34]:34s}"
    clean = [m for m in maps.values() if m["clean"]]
    moving = [m for m in maps.values() if not m["clean"]]
    all_clean = set().union(*[items(m) for m in clean])
    n = lambda s, k: len({x for x in s if x[0] == k})
    print(f"{len(maps)} maps with mob spawns: {len(clean)} clean, {len(moving)} with moving backgrounds (hunts refused)")
    print(f"mob types: {n(set().union(*[items(m) for m in maps.values()]), 'mob')} in all, {n(all_clean, 'mob')} on clean "
          f"maps; background sets: {n(set().union(*[items(m) for m in maps.values()]), 'set')} / {n(all_clean, 'set')}")
    got = set().union(*[items(maps[i]) for i in a.have if i in maps]) if a.have else set()
    print(f"\nalready recorded ({len(a.have)} maps): {n(got & all_clean, 'mob')} of {n(all_clean, 'mob')} clean-map mob "
          f"types, {n(got & all_clean, 'set')} of {n(all_clean, 'set')} background sets")
    for i in a.have:
        if i in maps:
            print(f"  {line(maps[i])} {'' if maps[i]['clean'] else 'MOVING BG'}")
    pool = [m for m in clean if m["lv"] and max(m["lv"]) <= a.max_level and m["id"] < 80000000 and m["id"] not in a.have]
    need = set().union(*[items(m) for m in pool]) - got if pool else set()
    print(f"\nclean maps to add (strongest mob <= lv {a.max_level}): {len(need)} new mob types + background sets")
    k = 0
    while need:
        best = max(pool, key=lambda m: (len(items(m) & need), m["spawns"]))
        g = items(best) & need
        if not g:
            break
        need -= g
        k += 1
        print(f"  {k:2d}. {line(best)} lv {min(best['lv'])}-{max(best['lv'])}, {best['spawns']} spawns"
              f"{', animated objects' if best['anim'] else ''}\n        adds: {', '.join(sorted(name(*x) for x in g))}")
        on_map = sorted(best["count"].items(), key=lambda kv: -kv[1])
        print("        its mobs (spawn points): " + ", ".join(f"{mobs[i]['name']} x{c}" for i, c in on_map if i in mobs))
    out_of_reach = all_clean - got - set().union(*[items(m) for m in pool]) if pool else set()
    if out_of_reach:
        print(f"  not reachable under lv {a.max_level}: {', '.join(sorted(name(*x) for x in out_of_reach))}")
    only = {s for m in moving for s in m["sets"]} - {s for m in clean for s in m["sets"]}
    print(f"\nmoving-background maps: one per background family that no clean map has ({len(only)} families)")
    for s in sorted(only):
        c = [m for m in moving if s in m["sets"] and m["lv"] and max(m["lv"]) <= a.max_level]
        if c:
            best = max(c, key=lambda m: m["spawns"])
            print(f"  {s:20s} {line(best)} lv {min(best['lv'])}-{max(best['lv'])}"
                  f"{'  (recorded)' if best['id'] in a.have or any(s in maps[i]['sets'] for i in a.have if i in maps) else ''}")


if __name__ == "__main__":
    main()
