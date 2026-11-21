"""E12 (tracker plan): WHY today's tracker loses the truth's chains - each id switch and each chain tick without a
track, classified.

    python tools/perc/track/e12_why.py CAP [CAP ...] [--list N]      (several: each, then all of them together)
"""
import argparse
from collections import Counter

from load import Map, anim_of, map_of, ticks
from oracle import O, POSE, SX, SY, T, X, Y, chains
from score import index, match

SW, PLAY_H = 1366, 700


def body_onscreen(mp, typ, sx, sy) -> float:
    fr = (mp.mobs[typ].get("frames") or {})
    f0 = (fr.get("stand") or fr.get("move") or fr.get("fly") or [{}])[0]
    lt, rb = f0.get("lt") or [-30, -50], f0.get("rb") or [30, 0]
    w, h = max(1, rb[0] - lt[0]), max(1, rb[1] - lt[1])
    x0, y0 = sx + lt[0], sy + lt[1]
    return max(0.0, min(x0 + w, SW) - max(x0, 0)) * max(0.0, min(y0 + h, PLAY_H) - max(y0, 0)) / (w * h)


def why(cap, n_ex: int = 400) -> tuple:
    """-> (Counter of why a track switched, Counter of why a live chain tick had no track, examples)."""
    tk = ticks(cap)
    mp = Map(map_of(cap))
    cis = index(tk, chains(tk))
    why_sw, why_miss = Counter(), Counter()
    ex = []
    for ci in cis:
        typ = ci["c"]["type"]
        last = None                                    # (id, tick index)
        for i in sorted(ci["pts"]):
            q = ci["pts"][i]
            if anim_of(q[POSE]).startswith("die"):
                continue
            mobs = tk[i]["mobs"]
            m = match(mobs, typ, q[X], q[Y])
            if m is None:
                anyt = [x for x in mobs if abs(x["x"] - q[X]) <= 24 and abs(x["y"] - q[Y]) <= 24]
                on = body_onscreen(mp, typ, q[SX], q[SY])
                if anyt and all(x["state"] == "dying" for x in anyt):
                    w = "a dying track sits there"
                elif anyt and all(x["state"] == "tentative" for x in anyt if x["mob"] == typ) and any(x["mob"] == typ for x in anyt):
                    w = "only a tentative track there"
                elif anyt:
                    w = "a track of another type there"
                elif on < 0.6:
                    w = "body < 60 % on screen (new-track rule)"
                elif q[O] < 0.9:
                    w = "fading (o < 0.9)"
                elif mp.platform(q[X], q[Y]) is None:
                    w = "off any platform (new-track rule)"
                else:
                    w = "other"
                why_miss[w] += 1
                continue
            if last is not None and last[0] != m["id"]:
                gap_ticks = i - last[1]
                old = next((x for x in mobs if x["id"] == last[0]), None)
                if old is None:
                    w = "old track ended" + (" during a gap" if gap_ticks > 1 else " while the mob was seen")
                elif old["state"] == "dying":
                    w = "old track turned dying, the mob lives"
                else:
                    d = abs(old["x"] - q[X]) + abs(old["y"] - q[Y])
                    w = f"old track still there, {'near' if d <= 40 else 'far'} (two tracks / crossing)"
                why_sw[w] += 1
                if len(ex) < n_ex:
                    ex.append((round(q[T], 2), w, typ, int(q[SX]), int(q[SY]), last[0], m["id"], gap_ticks,
                               None if old is None else (old["state"], old["src"], round(old["x"] - q[X]), old.get("unseen"))))
            last = (m["id"], i)
    return why_sw, why_miss, ex


def show(name, why_sw, why_miss, ex, n_list) -> None:
    print(f"{name}\n  id switches: {sum(why_sw.values())}")
    for w, n in why_sw.most_common():
        print(f"    {n:4d}  {w}")
    print(f"  live chain-ticks without a track: {sum(why_miss.values())}")
    for w, n in why_miss.most_common():
        print(f"    {n:5d}  {w}")
    seen = Counter()
    for e in ex:
        if seen[e[1]] < n_list:
            seen[e[1]] += 1
            print("   ", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--list", type=int, default=12)
    a = ap.parse_args()
    tot_sw, tot_miss = Counter(), Counter()
    for cap in a.caps:
        sw, miss, ex = why(cap)
        show(cap, sw, miss, ex, a.list)
        tot_sw.update(sw)
        tot_miss.update(miss)
    if len(a.caps) > 1:
        show(f"POOLED ({len(a.caps)} captures)", tot_sw, tot_miss, [], 0)


if __name__ == "__main__":
    main()
