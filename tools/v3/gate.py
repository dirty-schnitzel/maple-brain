"""brain v3 migration gate (PLAN-v3.md steps 1-2: objects, planner): the brain's behaviour must stay IDENTICAL.

Fingerprints, compared with tests/fixtures/v3_gate.json (recorded on dev 02a639a, before any v3 change):
  sim     the hunt in the movement sim of tests/test_brain_v2.py (`_hunt`: Line 1, fake Bubblings, start 273 x 1400)
          per seed: final stats, ticks, a sha256 over every tick (time, brain.snapshot(), keys held), over every tap
          (key, down, up) and over the brain's log lines - plus a checkpoint hash every 10 s of sim time, so a
          difference names the 10 s where it starts
  agree   tools/combat/agree.py's strike-rule replay of the user's Line 1 recording (runs/play/20261105_000802_1,
          spear): its printout + a sha256 over the firing times (skipped when the recording isn't on this PC)

usage (from the repo root):
  python tools/v3/gate.py             full gate: seeds 1-8 x 180 s + agree (~50 s)
  python tools/v3/gate.py --quick     seeds 1-2 x 60 s (what tests/test_v3_gate.py runs)
  python tools/v3/gate.py --record    (re)write the fixture - only on purpose, never to make a mismatch go away
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "v3_gate.json"
AGREE_RUN = ROOT / "runs" / "play" / "20261105_000802_1"
FULL = (tuple(range(1, 9)), 180.0)
QUICK = ((1, 2), 60.0)
CHECK_S = 10.0

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for sub in ("tests", "tools/combat"):
    if str(ROOT / sub) not in sys.path:
        sys.path.append(str(ROOT / sub))


def _sha(h) -> str:
    return h.hexdigest()[:20]


def sim_print(seed: int, seconds: float) -> dict:
    """One sim hunt's fingerprint (module doc)."""
    import test_brain_v2 as T
    from maplebrain.nav.navmap import NavMap

    ticks, lines, checks = hashlib.sha256(), hashlib.sha256(), []
    state = {"n": 0, "now": 0.0, "next_check": CHECK_S}

    class Rec(T.BrainV2):
        def __init__(self, cfg, nav, hz, reach=None, log=None):
            super().__init__(cfg, nav, hz, reach, log=self._say)

        def _say(self, msg):
            lines.update(f"{state['now']!r} {msg}\n".encode())

        def step(self, now, obs, s, driver):
            state["now"] = now
            r = super().step(now, obs, s, driver)
            ticks.update(json.dumps([repr(now), self.snapshot(), sorted(driver.want)], default=repr).encode())
            state["n"] += 1
            if now >= state["next_check"]:
                checks.append(_sha(ticks.copy()))
                state["next_check"] += CHECK_S
            return r

    drivers = []

    class KeepDrv(T.Drv):                         # _hunt makes its own driver: keep it for its taps
        def __init__(self):
            super().__init__()
            drivers.append(self)

    orig = T.BrainV2, T.Drv
    T.BrainV2, T.Drv = Rec, KeepDrv
    try:
        nav = NavMap.for_map(10003061, ROOT / "assets" / "mcw")
        br, flips, mobs = T._hunt(nav, seconds, seed)
    finally:
        T.BrainV2, T.Drv = orig
    taps = hashlib.sha256(json.dumps([[k, repr(a), repr(b)] for k, a, b in drivers[0].taps]).encode())
    return {"stats": dict(sorted(br.stats.items())), "ticks": state["n"], "tick_sha": _sha(ticks),
            "tap_sha": _sha(taps), "log_sha": _sha(lines), "deaths": len(mobs.deaths),
            "after_death": mobs.after_death, "flips": len(flips), "checks": checks}


def agree_print() -> dict | None:
    if not (AGREE_RUN / "selfstate.jsonl").exists():
        return None
    import agree
    fires, att, n_ticks, T = agree.rule_fires(str(AGREE_RUN), "spear")
    return {"lines": agree.report(fires, att, n_ticks, T), "fires": len(fires),
            "fires_sha": _sha(hashlib.sha256(json.dumps([repr(t) for t in fires]).encode()))}


def fingerprint(seeds, seconds, with_agree=True) -> dict:
    out = {"sim": {f"{seed}x{seconds:g}": sim_print(seed, seconds) for seed in seeds}}
    if with_agree:
        out["agree"] = agree_print()
    return out


def compare(want: dict, got: dict) -> list:
    """Mismatches as readable lines; [] = identical."""
    bad = []
    for key, g in got.get("sim", {}).items():
        w = want.get("sim", {}).get(key)
        if w is None:
            bad.append(f"sim {key}: not in the fixture")
            continue
        diff = [k for k in w if w[k] != g.get(k)]
        if diff:
            at = next((i for i, (a, b) in enumerate(zip(w["checks"], g["checks"])) if a != b), None)
            where = f", first differs in t {at * CHECK_S:g}-{(at + 1) * CHECK_S:g} s" if at is not None else ""
            stats = "" if w["stats"] == g["stats"] else f"\n    stats want {w['stats']}\n    stats got  {g['stats']}"
            bad.append(f"sim {key}: differs in {', '.join(k for k in diff if k != 'checks')}{where}{stats}")
    if "agree" in got:
        w, g = want.get("agree"), got["agree"]
        if g is None:
            print("agree: recording not on this PC, skipped")
        elif w != g:
            bad.append(f"agree: want {w}\n       got  {g}")
    return bad


def main(argv):
    seeds, seconds = QUICK if "--quick" in argv else FULL
    got = fingerprint(seeds, seconds, with_agree="--quick" not in argv)
    if "--record" in argv:
        old = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {"sim": {}}
        old["sim"].update(got["sim"])
        if got.get("agree") is not None:
            old["agree"] = got["agree"]
        FIXTURE.write_text(json.dumps(old, indent=1) + "\n", encoding="utf-8")
        print(f"recorded {', '.join(got['sim'])} -> {FIXTURE.relative_to(ROOT)}")
        return 0
    want = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key, g in got["sim"].items():
        st = g["stats"]
        print(f"sim {key}: kills {st.get('kills', 0)}, presses {st.get('presses', 0)}, trips {st.get('trips', 0)}, "
              f"ticks {g['ticks']}")
    if got.get("agree"):
        print("agree: " + " | ".join(got["agree"]["lines"]))
    bad = compare(want, got)
    print("\n".join(bad) if bad else "GATE OK: identical to the baseline")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
