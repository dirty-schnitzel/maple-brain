"""Drop lives in a replayed capture (PLAN-loot.md section 13, answered 2026-11-21 on the 30-minute Line 1 capture
20261121_000219_2#0): every resting drop linked over time (same item, same map place), how it began (landed in view
or already there), how it ended (its place seen empty in view / while out of view), where we were, was the pickup
key down; then the pickup key press by press.

    python tools/perc/replay/run.py SESSION#K --every 3 --out loot3        # the rows (mobs + drops per frame)
    python tools/loot/life_capture.py ROWS.jsonl KEYS.jsonl [--pick z] [--dump out.json]

Result on that capture: 40 of 40 drops left alone (no pickup key, we were far, landed in view) went 118.5-128.5 s
after coming to rest, in rounds ~10.1 s apart; none went earlier. tools/loot/end_sheet.py draws a drop's last moments.
"""
import argparse
import bisect
import json
from collections import Counter
from pathlib import Path

import numpy as np

SW, PLAY_H = 1366, 700
ROOT = Path(__file__).resolve().parents[2]


def in_view(mx, my, cam):
    """The drop's place (map feet) on screen, clear of the screen edges and the HUD corners."""
    if cam is None:
        return False
    sx, sy = mx - cam[0], my - cam[1]
    if not (60 <= sx <= 1300 and 100 <= sy <= 600):     # clear of the edges, the chat / quickslots / EXP lines
        return False
    if sx < 330 and sy < 230:              # the minimap's corner
        return False
    if sx > 1130 and sy < 170:             # buff icons
        return False
    return True


def on_screen(mx, my, cam):
    """Loose: the place is on screen and no HUD part is over it (the chat is minimized: its rows are world)."""
    if cam is None:
        return False
    sx, sy = mx - cam[0], my - cam[1]
    if not (30 <= sx <= SW - 30 and 60 <= sy <= 692):
        return False
    if sx < 330 and sy < 230:
        return False
    if sx > 1130 and sy < 170:
        return False
    if 915 <= sx <= 1100 and sy >= 610:   # the quickslots
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("keys")
    ap.add_argument("--pick", default="z")
    ap.add_argument("--dump", default=None)
    ap.add_argument("--gone-s", type=float, default=1.5)
    a = ap.parse_args()
    names = {int(k): v.get("name") for k, v in
             json.load(open(ROOT / "assets/mcw/items/items.json", encoding="utf-8"))["items"].items()}
    zs = sorted(json.loads(l)["t"] for l in open(a.keys, encoding="utf-8")
                if l.strip() and json.loads(l).get("key") == a.pick and json.loads(l).get("down"))
    rows = []
    with open(a.rows, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows.append({"t": r["t"], "n": r["n"], "cam": r.get("cam"), "me": r.get("me_map"),
                         "drops": r.get("drops") or [],
                         "dying": [(m["x"], m["y"]) for m in (r.get("mobs") or []) if m.get("state") == "dying"]})
    print(f"{len(rows)} rows, {rows[0]['t']:.1f}..{rows[-1]['t']:.1f} s; camera on {sum(r['cam'] is not None for r in rows)}; "
          f"{len(zs)} presses of {a.pick}")
    kinds = Counter(d.get("kind") for r in rows for d in r["drops"])
    print("sightings by kind:", dict(kinds))
    open_, done = [], []
    prev_t = rows[0]["t"]
    for i, r in enumerate(rows):
        t, cam = r["t"], r["cam"]
        dt = min(0.25, max(0.0, t - prev_t))
        prev_t = t
        if cam is None:
            continue
        seen_now = set()
        for d in r["drops"]:
            mx, my = d["feet"][0] + cam[0], d["feet"][1] + cam[1]
            if d.get("kind") != "rest":
                # a weak sighting of the same item at the place still says "something of it is there"
                for k, o in enumerate(open_):
                    if o["item"] == d["item"] and abs(mx - o["mx"]) <= 3 and abs(my - o["my"]) <= 16:
                        seen_now.add(k)
                continue
            hit = None
            for k, o in enumerate(open_):
                if o["item"] == d["item"] and abs(mx - o["mx"]) <= 2 and abs(my - o["my"]) <= 16:
                    hit = k
                    break
            if hit is None:
                # did it land in view? the place was on screen shortly before, with no drop there
                j, was = i - 1, False
                while j >= 0 and t - rows[j]["t"] <= 1.2:
                    if t - rows[j]["t"] >= 0.15 and in_view(mx, my, rows[j]["cam"]):
                        was = True
                        break
                    j -= 1
                dy_near = any(abs(x - mx) < 170 and abs(y - my) < 120 for rr in rows[max(0, i - 40):i + 1]
                              for x, y in rr["dying"])
                open_.append({"item": d["item"], "mx": mx, "my": my, "fh": d.get("fh"), "t0": t, "t1": t, "n": 1,
                              "born_inview": was, "death_near": dy_near, "unseen": 0.0, "i1": i, "first_unseen_view": None})
                seen_now.add(len(open_) - 1)
            else:
                o = open_[hit]
                o["t1"], o["n"], o["i1"], o["unseen"], o["first_unseen_view"] = t, o["n"] + 1, i, 0.0, None
                o["my"] = 0.8 * o["my"] + 0.2 * my
                seen_now.add(hit)
        keep = []
        for k, o in enumerate(open_):
            if k in seen_now:
                o["unseen"] = 0.0
                keep.append(o)
                continue
            if in_view(o["mx"], o["my"], cam):
                if o["first_unseen_view"] is None:
                    o["first_unseen_view"] = t
                o["unseen"] += dt
                if o["unseen"] >= a.gone_s:
                    o["gone_seen_at"] = o["first_unseen_view"]
                    done.append(o)
                    continue
            keep.append(o)
        open_ = keep
    for o in open_:
        o["gone_seen_at"] = None                       # never seen gone: the recording ended / never came back
        done.append(o)
    # --- classify every end
    ts = [r["t"] for r in rows]
    out = []
    for o in done:
        age = o["t1"] - o["t0"]
        e = {"item": o["item"], "name": names.get(o["item"], "?"), "mx": round(o["mx"]), "my": round(o["my"]), "t0": round(o["t0"], 2),
             "t1": round(o["t1"], 2), "age": round(age, 2), "n": o["n"], "born_inview": o["born_inview"],
             "death_near": o["death_near"], "gone_seen_at": o["gone_seen_at"]}
        if o["gone_seen_at"] is None:
            e["end"] = "open"
        else:
            gap = o["gone_seen_at"] - o["t1"]
            e["gap"] = round(gap, 2)
            e["end"] = "in view" if gap <= 0.35 else "out of view"
        # right after the last resting sighting: was the place on screen (loose) and empty?
        j, emp = o["i1"] + 1, 0
        while j < len(rows) and rows[j]["t"] - o["t1"] <= 1.0:
            emp += on_screen(o["mx"], o["my"], rows[j]["cam"])
            j += 1
        e["went"] = emp >= 5
        # where were we at the last resting sighting, and was the pickup key pressed around it
        me = rows[o["i1"]]["me"]
        if me is not None:
            e["dx"], e["dy"] = round(me[0] - o["mx"]), round(me[1] - o["my"])
        k = bisect.bisect_left(zs, o["t1"] - 0.6)
        near = [z - o["t1"] for z in zs[k:k + 12] if -0.6 <= z - o["t1"] <= 0.45]
        e["z"] = [round(x, 2) for x in near]
        out.append(e)
    by = Counter(e["end"] for e in out)
    print(f"{len(out)} drops; ends: {dict(by)}; landed in view {sum(e['born_inview'] for e in out)}")
    iv = [e for e in out if e["end"] == "in view"]
    ours = [e for e in iv if e["z"] and "dx" in e and abs(e["dx"]) <= 140 and abs(e["dy"]) <= 90]
    rest = [e for e in iv if e not in ours]
    print(f"\nwent while in view: {len(iv)}; with the pickup key down and us near: {len(ours)}; the others: {len(rest)}")
    if ours:
        dx = np.array([abs(e["dx"]) for e in ours]); dy = np.array([e["dy"] for e in ours]); ag = np.array([e["age"] for e in ours])
        print(f"  ours: |dx| p50 {np.median(dx):.0f} p90 {np.percentile(dx, 90):.0f} p99 {np.percentile(dx, 99):.0f} max {dx.max()} px; "
              f"dy (our feet - drop feet) p5 {np.percentile(dy, 5):.0f} p50 {np.median(dy):.0f} p95 {np.percentile(dy, 95):.0f} "
              f"min {dy.min()} max {dy.max()}; lay p50 {np.median(ag):.1f} p90 {np.percentile(ag, 90):.1f} max {ag.max():.1f} s")
    print("  the others (no key / we were far): t1, item, age, dx, dy, key offsets, landed in view")
    for e in sorted(rest, key=lambda e: -e["age"])[:60]:
        print(f"    t {e['t1']:8.2f}  {e['name'][:26]:26s} age {e['age']:7.2f}  dx {e.get('dx')!s:>5} dy {e.get('dy')!s:>5}  z {e['z']}  "
              f"landed {e['born_inview']} n {e['n']}")
    ov = [e for e in out if e["end"] == "out of view"]
    print(f"\nwent while out of view: {len(ov)} (alive at `age`, seen gone `gap` s after the last sighting)")
    for e in sorted(ov, key=lambda e: -e["age"])[:40]:
        print(f"    t0 {e['t0']:8.2f}  {e['name'][:26]:26s} alive at {e['age']:7.2f} s, gone by {e['age'] + e['gap']:7.2f} s  landed {e['born_inview']} n {e['n']}")
    op = [e for e in out if e["end"] == "open"]
    print(f"\nnever seen gone: {len(op)}; oldest alive ages: {sorted((e['age'] for e in op), reverse=True)[:10]}")
    al = sorted((e["age"] for e in out), reverse=True)[:15]
    print("oldest resting ages of all drops:", al)
    far = [e for e in iv if not e["z"] and ("dx" not in e or abs(e["dx"]) > 150 or abs(e["dy"]) > 100) and e["born_inview"] and e["n"] > 100]
    ag = np.array(sorted(e["age"] for e in far))
    print(f"went in view, no pickup key, we were far, landed in view ({len(far)}): ages by 10 s:",
          dict(sorted(Counter(int(x // 10) * 10 for x in ag).items())))
    core = ag[(ag > 110) & (ag < 140)]
    if len(core):
        print(f"  the 110-140 s group: n {len(core)}, min {core.min():.2f} p10 {np.percentile(core, 10):.2f} p50 {np.median(core):.2f} "
              f"p90 {np.percentile(core, 90):.2f} max {core.max():.2f}")
        t1 = np.array(sorted(e["t1"] for e in far if 110 < e["age"] < 140))
        best = min(((np.abs(((t1 - t1[0]) / p) - np.round((t1 - t1[0]) / p)).mean() * p, p) for p in np.arange(5.0, 20.0, 0.01)))
        print(f"  their end times fit a grid of {best[1]:.2f} s (mean distance to the grid {best[0]:.2f} s); "
              f"distinct end instants {len(set(np.round(t1, 0)))}")
    # --- the pickup key, press by press: where was the nearest lying drop, and did a drop go right after
    solid = [e for e in out if e["n"] >= 8]

    def me_at(tz):
        k = min(len(ts) - 1, bisect.bisect_left(ts, tz))
        for j in (k, k - 1, k + 1, k - 2, k + 2):
            if 0 <= j < len(rows) and rows[j]["me"] is not None and abs(rows[j]["t"] - tz) < 0.2:
                return rows[j]["me"]
        return None

    took, miss, nome = [], [], 0
    for q, tz in enumerate(zs):
        me = me_at(tz)
        if me is None:
            nome += 1
            continue
        alive = [e for e in solid if e["t0"] <= tz <= e["t1"] + 0.12]
        gone = [e for e in alive if e["went"] and -0.12 <= e["t1"] - tz <= 0.3]
        if gone:
            e = min(gone, key=lambda e: abs(e["mx"] - me[0]))
            took.append((abs(e["mx"] - me[0]), me[1] - e["my"], tz))
            continue
        if q and tz - zs[q - 1] < 0.6:               # a later tap of a burst: the first one may have used the pickup
            continue
        stay = [e for e in alive if e["t1"] > tz + 0.6 and abs(me[1] - e["my"]) <= 12]
        if stay:
            e = min(stay, key=lambda e: abs(e["mx"] - me[0]))
            miss.append((abs(e["mx"] - me[0]), me[1] - e["my"], tz))
    print(f"\nthe pickup key, press by press ({len(zs)} presses; our place unknown on {nome}): a drop went right after {len(took)}; "
          f"nothing went although a drop lay on our level {len(miss)}")
    if took:
        d = np.array([x[0] for x in took]); y = np.array([x[1] for x in took])
        print(f"  a drop went: |dx| at the press p50 {np.median(d):.0f} p90 {np.percentile(d, 90):.0f} p95 {np.percentile(d, 95):.0f} "
              f"p99 {np.percentile(d, 99):.0f} max {d.max():.0f}; by 10 px: {dict(sorted(Counter(int(v // 10) * 10 for v in d).items()))}")
        print(f"               our feet - the drop's feet (y): p1 {np.percentile(y, 1):.0f} p5 {np.percentile(y, 5):.0f} p50 {np.median(y):.0f} "
              f"p95 {np.percentile(y, 95):.0f} p99 {np.percentile(y, 99):.0f}")
    if miss:
        d = np.array([x[0] for x in miss])
        print(f"  nothing went: the nearest lying drop on our level was |dx| min {d.min():.0f} p5 {np.percentile(d, 5):.0f} p25 {np.percentile(d, 25):.0f} "
              f"p50 {np.median(d):.0f}; by 10 px (to 150): {dict(sorted(Counter(int(v // 10) * 10 for v in d if v < 150).items()))}")
        print("  the 12 nearest misses (|dx|, dy, t):", [(round(a_), round(b_), round(c_, 2)) for a_, b_, c_ in sorted(miss)[:12]])
    if a.dump:
        json.dump(out, open(a.dump, "w", encoding="utf-8"), indent=0)


if __name__ == "__main__":
    main()
