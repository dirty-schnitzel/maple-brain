"""E-L9 (PLAN-loot.md): a drop's LIFE from the finder's sightings, over every recording (offline; for the plan's
numbers and the tracker session - not the tracker).

    python tools/loot/exp_life.py [--find v2] [--runs a,b] [--list 12]

A DROP = the sightings of one item at one map x (+-2 px) at the resting height (box bottom within -7..+5 px of the
foothold under it), joined while the gaps are < 30 s. For every drop:
  first / last resting sighting, frames it was in view (its box inside the play area, away from the HUD) and frames
  it was sighted; the FLIGHT in = the same item's off-ground sightings within 1.6 s before the first resting one and
  160 px of it; the PICKUP flight = ... within 0.8 s after the last; the nearest mob death (the recording's tracker:
  first 'dying' tick) before the landing; how it ENDS: 'run end' / 'left the screen' / 'gone in view'.
Prints: lifetimes, ends, the flight (duration, apex, x travel, death -> landing), the pickup flight, sighted share
while in view (the per-frame recall against memory) and where the unsighted in-view frames are (covered: the list
gives times for the eye), drops per kill, distance between a kill's drops.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, map_of, run_ticks, PLAY_H, ROOT, SW  # noqa: E402

RUNS = ["runs/play/20261116_154819_1", "runs/play/20261116_084844_2", "runs/play/20261116_085108_3",
        "runs/play/20261116_085215_4", "runs/play/20261116_084719_1", "runs/play/20261117_092718_1",
        "runs/v2/20261117_094333_1", "runs/v2/20261117_111248_1", "runs/play/20261116_012059_1"]
ap = argparse.ArgumentParser()
ap.add_argument("--find", default="v2")
ap.add_argument("--runs", default="")
ap.add_argument("--list", type=int, default=12)
ap.add_argument("--u-max", type=float, default=0.2)
a = ap.parse_args()
it = Items()
S = defaultdict(list)
missed_list, long_list = [], []
for run in [r for r in RUNS if not a.runs or any(x in r for x in a.runs.split(","))]:
    p = ROOT / run / "loot" / f"find_{a.find}.jsonl"
    if not p.exists():
        continue
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    rows = [r for r in rows if r.get("drops") is not None]
    mp = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_of(ROOT / run)) / "map.json").read_text(encoding="utf-8"))
    FH = np.array([[f["x1"], f["y1"], f["x2"], f["y2"]] if f["x1"] < f["x2"] else [f["x2"], f["y2"], f["x1"], f["y1"]]
                   for f in (mp.get("footholds") or {}).values() if f["x1"] != f["x2"]], float)

    def ground(mx, my):
        on = (FH[:, 0] <= mx) & (FH[:, 2] >= mx)
        if not on.any():
            return None
        ya = FH[on, 1] + (mx - FH[on, 0]) * (FH[on, 3] - FH[on, 1]) / (FH[on, 2] - FH[on, 0])
        below = ya >= my - 14
        return float(ya[below].min()) if below.any() else None

    deaths, seen_ids = [], set()
    for k in run_ticks(ROOT / run):
        cam = k["cam"] or k.get("seed")
        if cam is None:
            continue
        for m in k["mobs"]:
            if m.get("state") == "dying" and m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                deaths.append((k["t"], m["sx"] + cam[0], m["sy"] + cam[1]))
    # sightings -> on-ground ones grouped into drops; the rest kept for flights
    drops, air = [], []
    for fi, r in enumerate(rows):
        cam, t = r["cam"], r["t"]
        for d in r["drops"]:
            n = max(1, d["n_op"])
            u = 1 - (d["n_seen"] + d["n_abs"] + d.get("n_cd", 0) + d.get("n_front", 0)) / n
            bx = d["box"][0] + d["box"][2] / 2 + cam[0]
            by = d["box"][1] + d["box"][3] + cam[1]
            mx = d["pos"][0] + cam[0]
            gy = ground(bx, by)
            o = {"fi": fi, "t": t, "mx": mx, "by": by, "u": u, "s": d["n_seen"] / n, "item": d["item"], "w": d["box"][2],
                 "h": d["box"][3], "bx": bx, "gy": gy, "f": d["f"]}
            if gy is None or not -7 <= by - gy <= 5:
                air.append(o)
                continue
            tr = next((x for x in drops if x["item"] == d["item"] and abs(x["mx"] - mx) <= 2 and x["gy"] == gy
                       and t - x["t1"] < 30 and x["last"] != fi), None)
            if tr is None:
                tr = {"item": d["item"], "mx": mx, "bx": bx, "gy": gy, "t0": t, "obs": [], "last": -1, "w": d["box"][2],
                      "h": d["box"][3], "fi0": fi}
                drops.append(tr)
            tr["obs"].append(o)
            tr["last"], tr["t1"] = fi, t
    t_end = rows[-1]["t"]

    def view(tr, cam):
        x, y = tr["bx"] - cam[0], tr["gy"] - cam[1]
        return tr["w"] / 2 + 4 <= x <= SW - tr["w"] / 2 - 4 and 50 <= y - tr["h"] and y + 6 <= PLAY_H

    real = [tr for tr in drops if len(tr["obs"]) >= 3]
    S["short_ground"].append(len(drops) - len(real))
    for tr in real:
        f0, f1 = tr["fi0"], tr["last"]
        vis = [fi for fi in range(f0, f1 + 1) if view(tr, rows[fi]["cam"])]
        got = {o["fi"] for o in tr["obs"]}
        strict = {o["fi"] for o in tr["obs"] if o["u"] <= a.u_max}
        tr["n_view"], tr["n_got"], tr["n_strict"] = len(vis), len(got & set(vis)), len(strict & set(vis))
        S["view"].append(len(vis))
        S["got"].append(tr["n_got"])
        S["strict"].append(tr["n_strict"])
        for fi in vis:
            if fi not in got:
                missed_list.append((run, rows[fi]["t"], tr["item"], tr["bx"] - rows[fi]["cam"][0], tr["gy"] - rows[fi]["cam"][1]))
        after = [fi for fi in range(f1 + 1, min(len(rows), f1 + 60)) if rows[fi]["t"] - tr["t1"] <= 1.5]
        if tr["t1"] >= t_end - 1.5:
            tr["end"] = "run end"
        elif after and sum(view(tr, rows[fi]["cam"]) for fi in after) >= 0.7 * len(after):
            tr["end"] = "gone in view"
        else:
            tr["end"] = "left the screen"
        S["end"].append(tr["end"])
        life = tr["t1"] - tr["t0"]
        S["life_" + tr["end"]].append(life)
        if tr["end"] == "gone in view" and life >= 20:
            long_list.append((run, tr["item"], round(tr["t0"], 1), round(tr["t1"], 1), round(life, 1), tr["bx"], tr["gy"]))
        # the flight in / the pickup flight: the item's off-ground sightings near it in time and place
        fl = [o for o in air if o["item"] == tr["item"] and 0 < tr["t0"] - o["t"] <= 1.6 and abs(o["mx"] - tr["mx"]) <= 160
              and abs(o["by"] - tr["gy"]) <= 170]
        if fl and tr["fi0"] > 5:
            t_first = min(o["t"] for o in fl)
            S["flight_s"].append(tr["t0"] - t_first)
            S["flight_apex"].append(tr["gy"] - min(o["by"] for o in fl))
            S["flight_dx"].append(abs(tr["mx"] - min(fl, key=lambda o: o["t"])["mx"]))
            S["flight_n" + ("_meso" if tr["item"] >= 9000000 else "_item")].append(len(fl))
        pk = [o for o in air if o["item"] == tr["item"] and 0 < o["t"] - tr["t1"] <= 0.8 and abs(o["mx"] - tr["mx"]) <= 80
              and abs(o["by"] - tr["gy"]) <= 90]
        if tr["end"] == "gone in view":
            S["pickup_seen"].append(bool(pk))
            if pk:
                last = max(pk, key=lambda o: o["t"])
                S["pickup_s"].append(last["t"] - tr["t1"])
                S["pickup_up"].append(tr["gy"] - last["by"])
                S["pickup_dx"].append(last["mx"] - tr["mx"])
        dd = [(tr["t0"] - dt, tr["mx"] - dx_, dy_) for dt, dx_, dy_ in deaths
              if 0 <= tr["t0"] - dt <= 2.5 and abs(tr["mx"] - dx_) <= 140 and abs(tr["gy"] - dy_) <= 60]
        if dd and tr["fi0"] > 5:
            best = min(dd, key=lambda x: abs(x[1]))
            S["death_to_land"].append(best[0])
            S["death_dx"].append(best[1])
        S["bob"].append((max(o["by"] for o in tr["obs"]) - min(o["by"] for o in tr["obs"])) if len(tr["obs"]) >= 40 else np.nan)
    by_item = Counter(tr["item"] for tr in real)
    print(f"{run[-17:]}: {len(rows)} frames {rows[-1]['t'] - rows[0]['t']:.0f} s, deaths {len(deaths)}, drops {len(real)} "
          f"(+ {len(drops) - len(real)} seen < 3 frames): "
          + ", ".join(f"{it.name(i)[:14] if i < 9000000 else 'meso' + str(i - 9000000)} {n}" for i, n in by_item.most_common(9)))

P = lambda v, q: float(np.nanpercentile(np.array(v, float), q))  # noqa: E731
print()
ends = Counter(S["end"])
print(f"drops {len(S['end'])}; ends {dict(ends)}")
for e in ("gone in view", "left the screen", "run end"):
    v = S["life_" + e]
    if v:
        print(f"   lifetime, '{e}' (n {len(v)}): p10 {P(v, 10):.1f} p50 {P(v, 50):.1f} p90 {P(v, 90):.1f} max {max(v):.1f} s")
v = S["flight_s"]
print(f"flight in (first off-ground sighting -> first resting one, n {len(v)}): p10 {P(v, 10):.2f} p50 {P(v, 50):.2f} p90 "
      f"{P(v, 90):.2f} s; apex above the foothold p50 {P(S['flight_apex'], 50):.0f} p90 {P(S['flight_apex'], 90):.0f} px; x travel "
      f"p50 {P(S['flight_dx'], 50):.0f} p90 {P(S['flight_dx'], 90):.0f} max {max(S['flight_dx']):.0f} px; sightings per flight: "
      f"mesos p50 {P(S['flight_n_meso'], 50):.0f}, items p50 {P(S['flight_n_item'], 50):.0f} (n {len(S['flight_n_item'])})")
v = S["death_to_land"]
if v:
    print(f"mob death (first dying tick) -> the drop rests (n {len(v)}): p10 {P(v, 10):.2f} p50 {P(v, 50):.2f} p90 {P(v, 90):.2f} s; "
          f"landing x - death x p5 {P(S['death_dx'], 5):.0f} p50 {P(S['death_dx'], 50):.0f} p95 {P(S['death_dx'], 95):.0f} px")
v = S["pickup_seen"]
print(f"gone in view: {len(v)}, with a pickup flight seen after {sum(v)} ({100 * sum(v) / max(1, len(v)):.0f} %)"
      + (f"; last flight sighting {P(S['pickup_s'], 50):.2f} s p50 after (p90 {P(S['pickup_s'], 90):.2f}), {P(S['pickup_up'], 50):.0f} px "
         f"up p50 (p90 {P(S['pickup_up'], 90):.0f}), |dx| p50 {P(np.abs(S['pickup_dx']), 50):.0f} p90 {P(np.abs(S['pickup_dx']), 90):.0f}"
         if S["pickup_s"] else ""))
tv, tg, ts = sum(S["view"]), sum(S["got"]), sum(S["strict"])
print(f"in view between first and last resting sighting: {tv} drop-frames; sighted (loose rule) {tg} = {100 * tg / tv:.2f} %; "
      f"sighted with unexplained cover <= {a.u_max} {ts} = {100 * ts / tv:.2f} %")
b = [x for x in S["bob"] if not np.isnan(x)]
print(f"bob range (drops seen >= 40 frames, n {len(b)}): {dict(sorted(Counter(int(x) for x in b).items()))}")
print(f"unsighted in-view frames: {len(missed_list)}; e.g.")
for run, t, item, sx, sy in missed_list[:: max(1, len(missed_list) // a.list)][:a.list]:
    print(f"   {run[-17:]} t {t:.2f} {it.name(item)[:16] if item < 9000000 else 'meso'} at screen ({sx:.0f}, {sy:.0f})")
print("drops lying >= 20 s that went while in view (expiry?):")
for x in sorted(long_list, key=lambda x: -x[4])[:15]:
    print(f"   {x[0][-17:]} {it.name(x[1])[:16] if x[1] < 9000000 else 'meso'} t {x[2]} -> {x[3]} = {x[4]} s at map ({x[5]:.0f}, {x[6]:.0f})")
