"""The graph audit, nodes: chains built from the client's own prev / next links, completely.

Today's navmap starts a chain only at a walkable foothold whose `prev` is not walkable; a foothold whose `prev` is
walkable but does not point back at it (a fork: e.g. the floor piece behind a wall's foot) is never reached and
becomes a ONE-foothold platform of its own, and so does every foothold after it. Here: a chain starts at every
walkable foothold whose prev is not walkable OR does not name it as its next, and runs along `next` while the next
foothold is walkable and names this one as its prev.

    python tools/model/chains_fixed.py

Prints: nodes today vs fixed, and the joints left between fixed chains whose ends meet (within 1 px): is a wall
standing at the joint, and which way do the client's links run across it. Reads assets/mcw/maps only.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / "assets" / "mcw"


def chains(fh: dict) -> list:
    """[[foothold id, ...]] left to right."""
    floor = {i for i, f in fh.items() if f["x1"] < f["x2"]}

    def linked(a, b):                                    # a -> b is a two-way link
        return b in floor and fh[a]["next"] == b and fh[b]["prev"] == a

    out, seen = [], set()
    for i in sorted(floor):
        p = fh[i]["prev"]
        if p in floor and linked(p, i):
            continue                                     # not a left end
        ch, j = [], i
        while j not in seen:
            seen.add(j)
            ch.append(j)
            n = fh[j]["next"]
            if not linked(j, n):
                break
            j = n
        out.append(ch)
    for i in sorted(floor - seen):                       # a closed loop of two-way links: cut it at its lowest id
        ch, j = [], i
        while j not in seen:
            seen.add(j)
            ch.append(j)
            j = fh[j]["next"]
        out.append(ch)
    return out


def main():
    n_today = n_fixed = n_maps_diff = 0
    joints = Counter()
    ex = {}
    for d in sorted((ASSETS / "maps").iterdir(), key=lambda p: int(p.name)):
        m = json.loads((d / "map.json").read_text(encoding="utf-8"))
        fh = {int(k): v for k, v in m["footholds"].items()}
        floor = {i for i, f in fh.items() if f["x1"] < f["x2"]}
        seen = set()
        today = 0
        for i in sorted(floor):
            if i in seen or fh[i]["prev"] in floor:
                continue
            j = i
            while j in floor and j not in seen:
                seen.add(j)
                j = fh[j]["next"]
            today += 1
        today += len(floor - seen)
        ch = chains(fh)
        assert sum(len(c) for c in ch) == len(floor), (m["id"], sum(len(c) for c in ch), len(floor))
        n_today += today
        n_fixed += len(ch)
        n_maps_diff += today != len(ch)
        walls = [(f["x1"], min(f["y1"], f["y2"]), max(f["y1"], f["y2"])) for f in fh.values() if f["x1"] == f["x2"]]
        ends = {}
        for c in ch:
            a, b = fh[c[0]], fh[c[-1]]
            ends.setdefault(("L", a["x1"], a["y1"]), []).append(c)
            ends.setdefault(("R", b["x2"], b["y2"]), []).append(c)
        for (side, x, y), cs in ends.items():
            if side != "R":
                continue
            for c in cs:
                for c2 in ends.get(("L", x, y), []):
                    a, b = c[-1], c2[0]                  # a's right end = b's left end
                    wall = any(wx == x and y0 < y <= y1 for wx, y0, y1 in walls)      # a wall rising from the joint
                    fwd = fh[a]["next"] == b
                    back = fh[b]["prev"] == a
                    kind = ("a wall stands at the joint" if wall else "no wall") + ", links: " + (
                        "a->b only" if fwd and not back else "b->a only" if back and not fwd else
                        "both (?)" if fwd and back else "none")
                    joints[kind] += 1
                    ex.setdefault(kind, []).append((m["id"], m["name"], a, b, x, y))
    print(f"nodes today {n_today} -> chains by complete links {n_fixed} (maps that change: {n_maps_diff})")
    print("joints between fixed chains whose ends meet at one point:")
    for k, v in joints.most_common():
        print(f"   {v:5d}  {k}    e.g. {ex[k][:3]}")


if __name__ == "__main__":
    main()
