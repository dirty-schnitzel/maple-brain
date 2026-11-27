"""Brain plan, measurement 1: HOW THE USER FARMS - their keys and the tracker's state over one capture, read side by
side, so the brain plan's targets are the user's own numbers (PLAN-brain.md, "What was measured").

    python tools/brain/proto_play.py CAP [CAP ...] [--keys K=ROLE ...] [--out DIR]

CAP = a stay of the bank (SESSION#K). Its keys.jsonl is read always; its kept replay (CORPUS/work/CAP/track,
tools/perc/track/dump.py) when there is one - without it only the key numbers are printed. Nothing is decoded: no
video, no GPU (safe while the user records).

The roles of the keys are an argument, not config.Keys (a class's keys belong in PLAN-tracker step 6's profile).
Default = the assassin's, from the user (2026-11-27): space attack (Lucky Seven), shift jump, z loot, 1 Haste,
2 Claw Booster, delete HP potion, end + home MP potions; arrows move.

What it reports (each section prints its own numbers; --out writes them as JSON too):
  keys      per key: presses, hold deciles, presses a minute; the attack key's gaps between presses
  casts     an attack press confirmed by an MP drop within CAST_WIN_S: the step's size (the skill's mpCon), the gap
            between two confirmed casts (its plateau = the swing length), casts with no MP step
  potions   per potion key: HP / MP share at the press, the HUD step that followed
  buffs     per buff key: the times, the gaps between casts, the HP / MP the cast cost
  loot      the pickup key: presses, holds, the nearest resting drop at each press (screen px)
  place     where we were: share of frames standing / air / rope, per node (track/graph.py's placement)
  shoot     at each attack press: the nearest live mob in front and behind (map px, by facing = the last walk key),
            |dy|, how many live mobs were within 300 / 600 px; presses with no mob in front
  exp       EXP a minute / an hour over the capture, EXP steps by size, the mob tracker's deaths a minute
  hurt      HP lost to hits a minute, the lowest HP share
  activity  each second: attacking / walking / looting / still - their shares
"""
import argparse
import bisect
import collections
import glob
import json
import pickle
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebrain.config import CORPUS  # noqa: E402

ASSASSIN = {"space": "attack", "shift": "jump", "z": "loot", "1": "buff", "2": "buff",
            "delete": "hp_potion", "end": "mp_potion", "home": "mp_potion",
            "left": "walk", "right": "walk", "up": "updown", "down": "updown"}
CAST_WIN_S = 0.35            # s after an attack key-down in which its MP step shows (the HUD: 0.1 s p50 on the warrior)
STEP_WIN_S = 0.6             # s after a potion / buff key-down in which its HUD step shows


def dec(v, nd=3):
    """Deciles p0..p100 of a list (empty -> [])."""
    if not v:
        return []
    return [round(float(x), nd) for x in np.percentile(np.asarray(v, float), np.arange(0, 101, 10))]


def stay_dir(cap):
    for p in glob.glob(str(Path(CORPUS) / "maps" / "*" / "*" / "stay.json")):
        j = json.loads(Path(p).read_text(encoding="utf-8"))
        if j.get("seg") == cap:
            return Path(p).parent, j
    raise SystemExit(f"{cap}: no stay with that id in {CORPUS}")


def load_keys(d):
    ev = [json.loads(line) for line in (d / "keys.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted(ev, key=lambda e: e["t"])


def presses(keys):
    """key -> [(t_down, hold_s or None)]; a down while already down (auto-repeat) is not a new press."""
    down, out = {}, collections.defaultdict(list)
    for e in keys:
        k = e["key"]
        if e["down"]:
            if k in down:
                continue
            down[k] = e["t"]
            out[k].append([e["t"], None])
        elif k in down:
            out[k][-1][1] = e["t"] - down.pop(k)
    return out


def load_state(cap):
    """The kept replay, compact: per frame (t, me_map, hp, hp_max, mp, mp_max, exp, mobs, drops, me_screen) and the
    shadow tracker's events. mobs: [(id, kind, x, y, node, state)] map px; drops: [(x, y)] screen px, resting."""
    tdir = Path(CORPUS) / "work" / cap / "track"
    files = sorted(tdir.glob("rows_*.pkl"))
    if not files:
        return None
    fr, events = [], []
    for f in files:
        with open(f, "rb") as fh:
            rows = pickle.load(fh)
        for r in rows:
            fa = r.get("facts") or {}
            hp, mp = fa.get("hp") or (None, None), fa.get("mp") or (None, None)
            mobs = [(m["id"], m["mob"], m["x"], m["y"], m.get("node"), m["state"]) for m in (r.get("shadow") or [])]
            drops = [tuple(d["feet"]) for d in (fa.get("drops") or []) if d.get("kind") == "rest"]
            fr.append((r["t"], r.get("me_map"), hp[0], hp[1], mp[0], mp[1], fa.get("exp_points"), mobs, drops,
                       r.get("me")))
            events += [e for e in (r.get("shadow_ev") or []) if isinstance(e, dict)]
            events += [e for e in (r.get("sp_ev") or []) if isinstance(e, dict)]
        del rows
    return fr, events


def _rows(cap):
    for f in sorted((Path(CORPUS) / "work" / cap / "track").glob("rows_*.pkl")):
        with open(f, "rb") as fh:
            rows = pickle.load(fh)
        yield from rows
        del rows


def load_metered(cap):
    """Ids of mob tracks that carried an HP meter reading at some frame (step 5a's `hp`)."""
    return {m["id"] for r in _rows(cap) for m in (r.get("shadow") or []) if m.get("hp") is not None}


def at(ts, t):
    """Index of the last frame at or before t."""
    return max(0, bisect.bisect_right(ts, t) - 1)


def hud_step(fr, ts, t, field, win):
    """The HUD value's change from just before t to its extreme within win s after (field 2 = hp, 4 = mp)."""
    i0 = at(ts, t - 0.02)
    v0 = fr[i0][field]
    if v0 is None:
        return None
    j = i0
    best = 0
    while j + 1 < len(fr) and fr[j + 1][0] <= t + win:
        j += 1
        v = fr[j][field]
        if v is not None and abs(v - v0) > abs(best):
            best = v - v0
    return best


def report(cap, roles, out):
    d, stay = stay_dir(cap)
    keys = load_keys(d)
    pr = presses(keys)
    dur = stay["t"][1] - stay["t"][0]
    res = {"cap": cap, "stay": stay["stay"], "map": stay["name"], "minutes": round(dur / 60, 2),
           "level": stay.get("level")}
    print(f"\n=== {cap}  {stay['stay']}  ({stay['name']}, {dur / 60:.1f} min, level {stay.get('level')})")

    # ---------------------------------------------------------------- keys
    print("\n[keys] key role presses /min hold-deciles(s)")
    kres = {}
    for k, v in sorted(pr.items(), key=lambda kv: -len(kv[1])):
        holds = [h for _, h in v if h is not None]
        kres[k] = {"role": roles.get(k, "?"), "n": len(v), "per_min": round(len(v) / dur * 60, 1),
                   "hold": dec(holds)}
        print(f"  {k:8s} {roles.get(k, '?'):10s} {len(v):5d} {len(v) / dur * 60:6.1f}  {dec(holds, 2)}")
    res["keys"] = kres
    atk = [k for k, r in roles.items() if r == "attack"]
    a_t = sorted(t for k in atk for t, _ in pr.get(k, []))
    gaps = [b - a for a, b in zip(a_t, a_t[1:])]
    res["attack_gaps"] = dec([g for g in gaps if g < 3.0])
    print(f"  attack key-down gaps under 3 s (n {sum(g < 3 for g in gaps)}): {dec([g for g in gaps if g < 3.0], 3)}")

    st = load_state(cap)
    if st is None:
        print("  (no kept replay: key numbers only)")
        return res
    fr, events = st
    ts = [f[0] for f in fr]

    # ---------------------------------------------------------------- casts (attack confirmed by MP)
    cast_t, steps, unconfirmed = [], [], 0
    for t in a_t:
        s = hud_step(fr, ts, t, 4, CAST_WIN_S)
        if s is not None and s < 0:
            cast_t.append(t)
            steps.append(-s)
        else:
            unconfirmed += 1
    cg = [b - a for a, b in zip(cast_t, cast_t[1:])]
    res["casts"] = {"confirmed": len(cast_t), "unconfirmed": unconfirmed,
                    "mp_step": collections.Counter(steps).most_common(6), "gap": dec([g for g in cg if g < 2.0])}
    print(f"\n[casts] attack presses {len(a_t)}: with an MP drop {len(cast_t)}, without {unconfirmed}")
    print(f"  MP step sizes (most common): {collections.Counter(steps).most_common(6)}")
    print(f"  gap between confirmed casts under 2 s: {dec([g for g in cg if g < 2.0], 3)}")
    short = sorted(g for g in cg if g < 2.0)[:max(1, len(cg) // 10)]
    if short:
        print(f"  the shortest 10 % of those gaps: median {statistics.median(short):.3f} s (the swing's plateau)")

    # ---------------------------------------------------------------- potions + buffs
    for role, field_lbl in (("hp_potion", "hp"), ("mp_potion", "mp"), ("buff", "buff")):
        for k in [k for k, r in roles.items() if r == role]:
            v = pr.get(k, [])
            if not v:
                continue
            rows = []
            for t, _ in v:
                i = at(ts, t - 0.02)
                f = fr[i]
                hp_s = f[2] / f[3] if f[2] is not None and f[3] else None
                mp_s = f[4] / f[5] if f[4] is not None and f[5] else None
                rows.append((t, hp_s, mp_s, hud_step(fr, ts, t, 2, STEP_WIN_S), hud_step(fr, ts, t, 4, STEP_WIN_S)))
            kt = [r[0] for r in rows]
            print(f"\n[{role} {k}] presses {len(rows)}")
            print(f"  HP share at the press: {dec([r[1] for r in rows if r[1] is not None], 2)}")
            print(f"  MP share at the press: {dec([r[2] for r in rows if r[2] is not None], 2)}")
            print(f"  HUD step after: HP {collections.Counter(r[3] for r in rows).most_common(4)}  "
                  f"MP {collections.Counter(r[4] for r in rows).most_common(4)}")
            if role == "buff":
                print(f"  times (s): {[round(x, 1) for x in kt]}")
                print(f"  gaps (s): {[round(b - a, 1) for a, b in zip(kt, kt[1:])]}")
            res[f"{role}_{k}"] = {"n": len(rows), "hp_share": dec([r[1] for r in rows if r[1] is not None], 2),
                                  "mp_share": dec([r[2] for r in rows if r[2] is not None], 2),
                                  "times": [round(x, 2) for x in kt]}

    # ---------------------------------------------------------------- loot
    for k in [k for k, r in roles.items() if r == "loot"]:
        v = pr.get(k, [])
        near = []
        for t, _ in v:
            f = fr[at(ts, t)]
            me = f[9]
            if me is None or not f[8]:
                near.append(None)
                continue
            near.append(min(((x - me[0]) ** 2 + (y - me[1]) ** 2) ** 0.5 for x, y in f[8]))
        known = [n for n in near if n is not None]
        print(f"\n[loot {k}] presses {len(v)}; nearest resting drop at the press (screen px): {dec(known, 0)}; "
              f"no drop on screen: {sum(n is None for n in near)}")
        res[f"loot_{k}"] = {"n": len(v), "nearest_drop_px": dec(known, 0), "no_drop": sum(n is None for n in near)}

    # ---------------------------------------------------------------- place (us on the graph)
    from maplebrain.track.graph import Graph, PLACES
    g = Graph.for_map(stay["map"], ROOT / "assets" / "mcw", edges=False)
    xs = np.array([f[1][0] if f[1] else np.nan for f in fr])
    ys = np.array([f[1][1] if f[1] else np.nan for f in fr])
    ok = ~np.isnan(xs)
    pl = g.place(xs[ok], ys[ok], climb=np.ones(ok.sum(), bool))
    names = collections.Counter(PLACES[int(p)] for p in pl.place)
    nodes = collections.Counter(int(n) for n, p in zip(pl.node, pl.place) if PLACES[int(p)] == "stand")
    tot = ok.sum()
    print(f"\n[place] frames with our feet {tot} of {len(fr)}: " +
          ", ".join(f"{k} {v / tot:.1%}" for k, v in names.most_common()))
    print("  standing, by node (share of standing frames): " +
          ", ".join(f"{n}: {c / max(1, sum(nodes.values())):.1%}" for n, c in nodes.most_common(10)))
    res["place"] = {k: round(v / tot, 4) for k, v in names.items()}
    res["nodes"] = {str(n): round(c / max(1, sum(nodes.values())), 4) for n, c in nodes.most_common(15)}
    # visits: consecutive standing frames on one node (air / rope frames between two stands on it do not end a
    # visit); per visit its length, the live mobs on that node at its start and at its end
    idx = np.flatnonzero(ok)
    visits = []                                    # [node, t_start, t_end, i_start, i_end]
    for k, (p, n) in enumerate(zip(pl.place, pl.node)):
        if PLACES[int(p)] != "stand":
            continue
        i = int(idx[k])
        if visits and visits[-1][0] == int(n):
            visits[-1][2], visits[-1][4] = fr[i][0], i
        else:
            visits.append([int(n), fr[i][0], fr[i][0], i, i])

    def live_on(i, node):
        return sum(1 for (_, _, _, _, nd, s) in fr[i][7] if nd == node and s in ("live", "hit", "tentative"))
    long_v = [v for v in visits if v[2] - v[1] >= 1.0]
    dwell = [v[2] - v[1] for v in long_v]
    at_in = [live_on(v[3], v[0]) for v in long_v]
    at_out = [live_on(v[4], v[0]) for v in long_v]
    print(f"  visits of 1 s or more: {len(long_v)}; their length (s): {dec(dwell, 1)}")
    print(f"  live mobs on the node at the visit's start: {dec(at_in, 0)}; at its end: {dec(at_out, 0)} "
          f"(ended with 0 live there: {sum(1 for x in at_out if x == 0)} of {len(at_out)})")
    print("  the sequence (node:seconds): " + " ".join(f"{v[0]}:{v[2] - v[1]:.0f}" for v in long_v[:60]))
    res["visits"] = {"n": len(long_v), "dwell": dec(dwell, 1), "live_in": dec(at_in, 0), "live_out": dec(at_out, 0),
                     "ended_empty": sum(1 for x in at_out if x == 0)}
    walked = np.nansum(np.abs(np.diff(xs)))
    print(f"  walked (sum of |dx| on frames with our feet): {walked:.0f} px = {walked / dur * 60:.0f} px a minute")

    # ---------------------------------------------------------------- shoot (geometry at each attack press)
    walk_ev = sorted((e["t"], e["key"]) for e in keys if e["down"] and e["key"] in ("left", "right"))
    wt = [t for t, _ in walk_ev]
    front, behind, dys, n300, n600, empty = [], [], [], [], [], 0
    for t in a_t:
        i = at(ts, t)
        f = fr[i]
        if f[1] is None:
            continue
        j = bisect.bisect_right(wt, t) - 1
        face = (1 if walk_ev[j][1] == "right" else -1) if j >= 0 else 0
        mx, my = f[1]
        live = [(x - mx, y - my) for (_, _, x, y, _, s) in f[7] if s in ("live", "hit", "tentative")]
        n300.append(sum(abs(dx) <= 300 and abs(dy) <= 80 for dx, dy in live))
        n600.append(sum(abs(dx) <= 600 and abs(dy) <= 80 for dx, dy in live))
        fr_ = [abs(dx) for dx, dy in live if face and dx * face > 0 and abs(dy) <= 80]
        bh_ = [abs(dx) for dx, dy in live if face and dx * face < 0 and abs(dy) <= 80]
        if fr_:
            front.append(min(fr_))
            dys.append(min((abs(dy) for dx, dy in live if face and dx * face > 0 and abs(dy) <= 80)))
        else:
            empty += 1
        if bh_:
            behind.append(min(bh_))
    # where we were at each press (stand / air / rope) and what came just before it
    pl_all = np.full(len(fr), -1)
    pl_all[np.flatnonzero(ok)] = pl.place
    node_all = np.zeros(len(fr), np.int64)
    node_all[np.flatnonzero(ok)] = pl.node
    at_press = collections.Counter(PLACES[pl_all[at(ts, t)]] if pl_all[at(ts, t)] >= 0 else "unknown" for t in a_t)
    jt = sorted(t for t, _ in pr.get("shift", []))
    after_jump = sum(1 for t in a_t if (j := bisect.bisect_right(jt, t) - 1) >= 0 and t - jt[j] <= 0.5)
    print(f"\n[shoot] attack presses by where we were: {dict(at_press)}; within 0.5 s after a jump press: "
          f"{after_jump} of {len(a_t)}")
    res["shoot_place"] = dict(at_press)
    res["shoot_after_jump"] = after_jump
    lag = [t - jt[j] for t in a_t if (j := bisect.bisect_right(jt, t) - 1) >= 0 and t - jt[j] <= 0.5]
    print(f"  jump press -> attack press (s): {dec(lag, 3)}")
    jumps_shot = sum(1 for tj in jt if any(0 <= t - tj <= 0.5 for t in a_t[bisect.bisect_left(a_t, tj):
                                                                            bisect.bisect_left(a_t, tj + 0.6)]))
    print(f"  jumps followed by a shot within 0.5 s: {jumps_shot} of {len(jt)}")
    res["jump_to_shot"] = dec(lag, 3)
    res["jumps_shot"] = [jumps_shot, len(jt)]
    # walking while shooting: a walk key down at the press
    wdown = presses(keys)
    held_at = 0
    for t in a_t:
        for k in ("left", "right"):
            if any(t0 <= t <= t0 + (h if h is not None else 0) for t0, h in wdown.get(k, [])):
                held_at += 1
                break
    print(f"  a walk key held at the attack press: {held_at} of {len(a_t)}")
    res["walk_held_at_shot"] = held_at
    # the mob that reacted: after each confirmed cast, the first mob whose state turns hit / dying in 0.05-1.0 s
    hit_dx, hit_dy, hit_lag, none_hit = [], [], [], 0
    for t in cast_t:
        i0 = at(ts, t)
        f = fr[i0]
        if f[1] is None:
            continue
        j = bisect.bisect_right(wt, t) - 1
        face = (1 if walk_ev[j][1] == "right" else -1) if j >= 0 else 0
        before = {m[0]: m for m in f[7]}
        found = None
        i = i0 + 1
        while i < len(fr) and fr[i][0] <= t + 1.0 and found is None:
            if fr[i][0] >= t + 0.05:
                for m in fr[i][7]:
                    b = before.get(m[0])
                    if b is not None and m[5] in ("hit", "dying") and b[5] in ("live", "tentative"):
                        found = (b, fr[i][0] - t)
                        break
            i += 1
        if found is None:
            none_hit += 1
            continue
        b, lagt = found
        hit_dx.append((b[2] - f[1][0]) * (face or 1))
        hit_dy.append(b[3] - f[1][1])
        hit_lag.append(lagt)
    print(f"\n[range] confirmed casts {len(cast_t)}: a mob turned hit / dying after {len(hit_dx)}, none seen {none_hit}")
    print(f"  that mob's dx at the press, signed by our facing (+ = in front): {dec(hit_dx, 0)}")
    print(f"  its dy (map px, + = below us): {dec(hit_dy, 0)}")
    print(f"  press -> its reaction (s): {dec(hit_lag, 3)}")
    res["range"] = {"hit_dx": dec(hit_dx, 0), "hit_dy": dec(hit_dy, 0), "lag": dec(hit_lag, 3), "none": none_hit,
                    "n": len(hit_dx)}
    print(f"  nearest live mob IN FRONT within |dy| 80 (px): {dec(front, 0)}")
    print(f"  no live mob in front within |dy| 80: {empty} of {len(a_t)}; nearest behind (when one): {dec(behind, 0)}")
    print(f"  live mobs within 300 px / 600 px (|dy| <= 80) at a press: mean {np.mean(n300):.2f} / {np.mean(n600):.2f}")
    res["shoot"] = {"front_px": dec(front, 0), "no_front": empty, "behind_px": dec(behind, 0),
                    "n300": round(float(np.mean(n300)), 2), "n600": round(float(np.mean(n600)), 2)}

    # ---------------------------------------------------------------- exp + deaths
    ex = [(f[0], f[6]) for f in fr if f[6] is not None]
    gain, steps_e = 0, collections.Counter()
    for (t0, a), (t1, b) in zip(ex, ex[1:]):
        if b > a:
            gain += b - a
            steps_e[b - a] += 1
        elif b < a:                     # a level up (EXP starts again) - counted from 0
            gain += b
    died = [e for e in events if e.get("ev") == "mob_died"]
    spawns = [e for e in events if e.get("ev") == "spawn_seen"]
    span = (ex[-1][0] - ex[0][0]) if len(ex) > 1 else dur
    print(f"\n[exp] gained {gain} in {span / 60:.1f} min = {gain / span * 60:.0f} a minute = {gain / span * 3600:.0f} an hour")
    print(f"  EXP steps by size (most common): {steps_e.most_common(8)}")
    print(f"  the mob tracker's deaths: {len(died)} = {len(died) / span * 60:.1f} a minute; spawns seen "
          f"{len(spawns)} = {len(spawns) / span * 60:.1f} a minute")
    # ours or not: a death whose track carried an HP meter reading (only mobs WE hit show one: the user, 2026-11-26)
    hp_ids = load_metered(cap)
    ours = [e for e in died if e["id"] in hp_ids]
    print(f"  of those deaths, the mob carried our HP meter: {len(ours)} = {len(ours) / span * 60:.1f} a minute "
          f"(EXP steps of a whole kill: {sum(c for s, c in steps_e.items() if s >= 40)})")
    # other players: the tracker's player_new / player_left events (the rows hold no player records)
    n_pl, last_t, area, mx = 0, ts[0], 0.0, 0
    for e in sorted((e for e in events if e.get("ev") in ("player_new", "player_left")), key=lambda e: e["t"]):
        area += n_pl * (e["t"] - last_t)
        last_t = e["t"]
        n_pl = max(0, n_pl + (1 if e["ev"] == "player_new" else -1))
        mx = max(mx, n_pl)
    area += n_pl * (ts[-1] - last_t)
    print(f"  other players in view: mean {area / (ts[-1] - ts[0]):.2f}, at most {mx}")
    res["ours_deaths"] = len(ours)
    res["players_mean"] = round(area / (ts[-1] - ts[0]), 2)
    # spawn points per node against where we stood
    m = json.loads((ROOT / "assets" / "mcw" / "maps" / str(stay["map"]) / "map.json").read_text(encoding="utf-8"))
    pts = [s for s in m["mobs"] if not s.get("hidden")]
    pp = g.place(np.array([s["x"] for s in pts], float), np.array([s["y"] for s in pts], float))
    sp_node = collections.Counter(int(n) for n in pp.node)
    print("  spawn points per node (node: points / our standing share): " + ", ".join(
        f"{n}: {c} / {nodes.get(n, 0) / max(1, sum(nodes.values())):.0%}" for n, c in sp_node.most_common(14)))
    res["spawn_points_per_node"] = {str(n): c for n, c in sp_node.items()}
    first_atk = a_t[0] if a_t else None
    res["exp"] = {"gain": gain, "per_min": round(gain / span * 60, 1), "per_hour": round(gain / span * 3600),
                  "steps": steps_e.most_common(8), "deaths": len(died),
                  "deaths_per_min": round(len(died) / span * 60, 2), "first_attack_t": first_atk}

    # ---------------------------------------------------------------- hurt
    lost, low = 0, 1.0
    for f0, f1 in zip(fr, fr[1:]):
        if f0[2] is not None and f1[2] is not None and f1[2] < f0[2]:
            lost += f0[2] - f1[2]
        if f1[2] is not None and f1[3]:
            low = min(low, f1[2] / f1[3])
    print(f"\n[hurt] HP lost (all drops, incl. Claw Booster's cost): {lost} = {lost / span * 60:.0f} a minute; "
          f"lowest HP share {low:.2f}")
    res["hurt"] = {"lost_per_min": round(lost / span * 60), "lowest_share": round(low, 3)}

    # ---------------------------------------------------------------- activity per second
    secs = int(dur)
    act = collections.Counter()
    a_set = np.zeros(secs + 1, bool)
    for t in a_t:
        if 0 <= int(t) <= secs:
            a_set[int(t)] = True
    l_set = np.zeros(secs + 1, bool)
    for k in [k for k, r in roles.items() if r == "loot"]:
        for t, h in pr.get(k, []):
            for s in range(int(t), int(t + (h or 0.1)) + 1):
                if s <= secs:
                    l_set[s] = True
    moved = np.zeros(secs + 1, bool)
    for s in range(secs):
        i0, i1 = at(ts, s), at(ts, s + 1)
        if fr[i0][1] and fr[i1][1]:
            moved[s] = abs(fr[i1][1][0] - fr[i0][1][0]) > 20 or abs(fr[i1][1][1] - fr[i0][1][1]) > 20
    for s in range(secs):
        act["attack+move" if a_set[s] and moved[s] else "attack" if a_set[s] else "loot" if l_set[s]
            else "move" if moved[s] else "still"] += 1
    print("\n[activity] seconds: " + ", ".join(f"{k} {v / secs:.1%}" for k, v in act.most_common()))
    res["activity"] = {k: round(v / secs, 4) for k, v in act.items()}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--keys", nargs="*", default=[], help="KEY=ROLE overrides of the assassin's roles")
    ap.add_argument("--out", default=None, help="a folder: one JSON per capture")
    a = ap.parse_args()
    roles = dict(ASSASSIN)
    for kv in a.keys:
        k, r = kv.split("=")
        roles[k] = r
    for cap in a.caps:
        res = report(cap, roles, a.out)
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / f"{cap.replace('#', '_')}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
