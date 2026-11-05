"""Tour of random goals in the movement sim (nav/sim.py) with brain-v2's Travel (M1 step 3-4, offline).

    python tools/nav/sim_tour.py [MAP_ID] [--trips N] [--seed S] [--lag 0.06] [--noise 2] [-v]

Physics at 200 Hz; the brain sees our state every ~`--tick` s (varied), `--lag` s old, x/y +- `--noise` px.
Reports per link kind: tries, first-try success, time vs expected; trips done / failed and why.
"""
import argparse
import collections
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebot.brain.travel import Travel            # noqa: E402
from maplebot.humanize import Humanizer             # noqa: E402
from maplebot.nav.navmap import NavMap              # noqa: E402
from maplebot.nav.selfstate import SelfState        # noqa: E402
from maplebot.nav.sim import Sim, SimDriver         # noqa: E402


def seen(b, t, rng, noise):
    return SelfState(t, b.x + rng.gauss(0, noise), b.y + rng.gauss(0, noise), "tag", b.state, b.platform, b.rope,
                     b.vx, b.vy)


def trip(nav, sim, dst, dst_x, rng, hz, a, verbose=False):
    drv = SimDriver(react=a.react)
    tr = Travel(nav, dst, dst_x, hz)
    t, next_obs, hist = 0.0, 0.0, []
    dt = 0.005
    while t < a.limit:
        b = sim.step(drv.keys(t), dt)
        hist.append((t, b.x, b.y, b.state, b.platform, b.rope, b.vx, b.vy))
        t += dt
        if t >= next_obs:
            old = [h for h in hist if h[0] <= t - a.lag] or hist[:1]
            h = old[-1]
            hist = hist[-200:]

            class B:                                                    # the body as it was `lag` s ago
                x, y, state, platform, rope, vx, vy = h[1:]
            st = tr.step(t, seen(B, t, rng, a.noise), drv)
            next_obs = t + a.tick * rng.uniform(0.7, 1.4)
            if st != "run":
                break
    if verbose:
        print(f"  -> {tr.status} {tr.reason or ''} in {t:.1f} s; moves {tr.log}; events {tr.events}")
    return tr, t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map", nargs="?", type=int, default=10003061)
    ap.add_argument("--trips", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tick", type=float, default=0.07)
    ap.add_argument("--lag", type=float, default=0.06)
    ap.add_argument("--noise", type=float, default=2.0)
    ap.add_argument("--react", type=float, default=0.02)
    ap.add_argument("--limit", type=float, default=60.0)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    nav = NavMap.for_map(a.map, ROOT / "assets" / "mcw")
    rng = random.Random(a.seed)
    hz = Humanizer(seed=a.seed)
    big = [p for p in nav.platforms.values() if p.right - p.left >= 40]
    start0 = max(big, key=lambda p: p.right - p.left)
    big = [p for p in big if p is start0 or nav.route(start0.id, start0.left + 20, p.id) is not None]  # reachable
    start = max(big, key=lambda p: p.right - p.left)
    sim = Sim(nav, start.id, (start.left + start.right) / 2)
    kinds = collections.defaultdict(lambda: [0, 0, [], []])     # kind -> [tries, ok, secs, expected]
    out = collections.Counter()
    reasons = collections.Counter()
    for i in range(a.trips):
        if sim.b.state != "ground":
            break
        for _ in range(50):                                     # a goal we can get to from here
            dst = rng.choice(big)
            dst_x = rng.uniform(dst.left + 10, dst.right - 10)
            if dst.id != sim.b.platform and nav.route(sim.b.platform, sim.b.x, dst.id, dst_x) is not None:
                break
        if a.v:
            print(f"trip {i}: {sim.b.platform} x {sim.b.x:.0f} -> {dst.id} x {dst_x:.0f}")
        try:
            tr, secs = trip(nav, sim, dst.id, dst_x, rng, hz, a, a.v)
        except RuntimeError as e:
            print("sim:", e)
            break
        out[tr.status] += 1
        if tr.status != "done":
            reasons[tr.reason] += 1
        for kind, ok, s, exp, why in tr.log:
            k = kinds[kind]
            k[0] += 1
            k[1] += ok
            k[2].append(s)
            k[3].append(exp)
            if not ok:
                reasons[f"{kind}: {why}"] += 1
        # let the sim settle on the ground
        for _ in range(400):
            if sim.b.state == "ground":
                break
            sim.step(set(), 0.005)
    print(f"trips {dict(out)}")
    for kind, (n, ok, s, e) in sorted(kinds.items()):
        s.sort()
        print(f"  {kind:8s} {ok:4d}/{n:<4d} ok  median {s[len(s) // 2]:.2f} s (expected {sorted(e)[len(e) // 2]:.2f})")
    print("failures:", reasons.most_common(12))


if __name__ == "__main__":
    main()
