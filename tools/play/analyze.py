"""Analyse a recording: the player's (or bot's) keys + where they went.
usage: python -I tools/play/analyze.py RUN   (RUN has ticks.jsonl; keys.jsonl from serve --observe)
Bot runs have no keys.jsonl: their keys come from ticks' actions (not handled yet)."""
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else None


def fmt(v):
    if not v:
        return "-"
    return f"n {len(v):3d}  median {st.median(v):5.2f}  p10 {pct(v, .1):5.2f}  p90 {pct(v, .9):5.2f}  max {max(v):5.2f}"


def main(run):
    run = Path(run)
    ticks = [json.loads(x) for x in open(run / "ticks.jsonl", encoding="utf-8")]
    keys = [json.loads(x) for x in open(run / "keys.jsonl", encoding="utf-8")] if (run / "keys.jsonl").exists() else []
    T = ticks[-1]["obs"]["t"]
    print(f"{run.name}: {T:.1f} s, {len(ticks)} ticks, {len(keys)} key events")

    # --- key presses: (key, t_down, t_up)
    open_, presses = {}, []
    for k in keys:
        if k["down"]:
            open_[k["key"]] = k["t"]
        elif k["key"] in open_:
            presses.append((k["key"], open_.pop(k["key"]), k["t"]))
    by = defaultdict(list)
    for key, a, b in presses:
        by[key].append((a, b))
    print("\n== keys: hold time (s) per press")
    for key, ps in sorted(by.items(), key=lambda kv: -len(kv[1])):
        held = sum(b - a for a, b in ps)
        print(f"  {key:7s} {fmt([b - a for a, b in ps])}   held {held:5.1f} s ({100 * held / T:4.1f} %)")
    print("\n== gaps between presses of the same key (s)")
    for key, ps in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(ps) > 2:
            print(f"  {key:7s} {fmt([ps[i + 1][0] - ps[i][1] for i in range(len(ps) - 1)])}")

    # --- what is held at each moment: time per key combination
    ev = sorted([(a, 1, k) for k, a, b in presses] + [(b, -1, k) for k, a, b in presses])
    held, last, combo = set(), 0.0, Counter()
    for t, d, k in ev:
        combo[" + ".join(sorted(held)) or "(nothing)"] += t - last
        last = t
        (held.add if d > 0 else held.discard)(k)
    combo["(nothing)"] += T - last
    print("\n== time per key combination")
    for c, s in combo.most_common(14):
        print(f"  {100 * s / T:5.1f} %  {s:5.1f} s  {c}")

    # --- presses that start while another key is already held
    starts = Counter()
    for k, a, b in presses:
        others = sorted(k2 for k2, a2, b2 in presses if k2 != k and a2 < a < b2)
        if others:
            starts[f"{k} while {'+'.join(others)}"] += 1
    print("\n== presses started while holding another key")
    for c, n in starts.most_common(12):
        print(f"  {n:3d}  {c}")

    # --- idle: stretches with nothing held
    idle, last_up, depth = [], 0.0, 0
    for t, d, k in ev:
        if d > 0 and depth == 0 and t - last_up > 0:
            idle.append(t - last_up)
        depth += d
        if depth == 0:
            last_up = t
    print(f"\n== no key held: {fmt(idle)}")

    # --- where: platforms over time (dwell >= 0.3 s), ropes, air
    seq, cur, t_in = [], None, 0.0
    for r in ticks:
        o = r["obs"]
        p = f"rope{o['rope']}" if o.get("rope") is not None else (o.get("platform") if o.get("platform") is not None else "?")
        if p != cur:
            if cur is not None:
                seq.append((cur, t_in, o["t"]))
            cur, t_in = p, o["t"]
    seq.append((cur, t_in, T))
    merged = []
    for p, a, b in seq:
        if merged and (merged[-1][0] == p or (b - a < 0.3 and p == "?")):
            merged[-1] = (merged[-1][0], merged[-1][1], b)
        elif b - a < 0.3 and merged:
            merged[-1] = (merged[-1][0], merged[-1][1], b)
        else:
            merged.append((p, a, b))
    print("\n== route (platform / rope, dwell >= 0.3 s)")
    xs = defaultdict(list)
    for r in ticks:
        if r["obs"].get("map_pos"):
            xs[r["obs"].get("platform")].append(r["obs"]["map_pos"][0])
    print("  " + "  ".join(f"{p}@{a:.0f}s({b - a:.0f})" for p, a, b in merged))
    tot = Counter()
    for p, a, b in merged:
        tot[p] += b - a
    print("  time per place: " + ", ".join(f"{p} {s:.0f}s" for p, s in tot.most_common(10)))

    # --- kills: EXP increases
    exps = [(r["obs"]["t"], r["obs"]["exp_points"]) for r in ticks if r["obs"].get("exp_points") is not None]
    gains = [t for (t0, e0), (t, e) in zip(exps, exps[1:]) if e > e0]
    print(f"\n== EXP gains: {len(gains)} ({60 * len(gains) / T:.1f}/min)")

    # --- mobs: how many tracked, on our platform vs elsewhere
    same = other = 0
    for r in ticks:
        o = r["obs"]
        live = [m for m in o.get("mobs") or [] if m.get("kind") == "mob" and m["state"] in ("live", "hit", "hidden")]
        same += sum(m.get("platform") == o.get("platform") for m in live)
        other += sum(m.get("platform") != o.get("platform") for m in live)
    print(f"== tracked live mobs per tick: our platform {same / len(ticks):.2f}, others {other / len(ticks):.2f}")


if __name__ == "__main__":
    main(sys.argv[1])
