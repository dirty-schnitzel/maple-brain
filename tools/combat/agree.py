"""WHEN TO HIT vs the user: replay a recording's tracks (ticks.jsonl) + our exact position (selfstate.jsonl, from
tools/nav/selfstate_eval.py) through BrainV2's strike rule, facing = the user's last left/right key. Per user swing:
would the rule have fired within +-0.35 s? Per rule firing (as if each swing's cycle were ~0.9 s): did the user swing
within +-0.35 s?  usage: agree.py RUN [--weapon spear]"""
import bisect
import json
import sys
from types import SimpleNamespace

from maplebrain.brain.brain_v2 import BrainV2
from maplebrain.config import Config
from maplebrain.humanize import Humanizer
from maplebrain.nav.navmap import NavMap
from maplebrain.brain.v2.scene import Scene
from maplebrain.nav.selfstate import SelfState

ASSETS = "assets/mcw"


class Null:
    want = set()

    def tap(self, *a, **k):
        return True

    def hold(self, keys):
        pass

    def busy(self, key=None):
        return False


def rule_fires(run, weapon="spear"):
    """(rule firing times, user swing times, ticks with our exact position, run length s). tools/v3/gate.py
    fingerprints the firing times (brain v3 migration: must stay identical)."""
    ticks = [json.loads(x) for x in open(f"{run}/ticks.jsonl")]
    sst = {r["n"]: r for r in map(json.loads, open(f"{run}/selfstate.jsonl"))}
    kl = [json.loads(x) for x in open(f"{run}/keys.jsonl")]
    att = sorted(k["t"] for k in kl if k["key"] in Config().keys.swing_keys and k["down"])
    turns = [(k["t"], 1 if k["key"] == "right" else -1) for k in kl if k["key"] in ("left", "right") and k["down"]]
    tt = [t for t, _ in turns]
    cfg = Config()
    cfg.combat.weapon = weapon
    nav = NavMap.for_map(10003061, __import__("pathlib").Path(ASSETS))
    br = BrainV2(cfg, nav, Humanizer(seed=1))
    fires, n_ticks = [], 0
    for r in ticks:
        e = sst.get(r["n"])
        if e is None:
            continue
        o = r["obs"]
        t = o["t"]
        i = bisect.bisect_right(tt, t)
        if not i:
            continue
        s = SelfState(t, e["x"], e["y"], e["src"], e["state"], e["platform"], e["rope"], e["vx"], e["vy"])
        obs = SimpleNamespace(me=o.get("me"), mobs=o.get("mobs") or [], mp_now=None, mp_potions=True)
        n_ticks += 1
        br.weapon.next_at = br.weapon.swing_end = -9.0  # the rule alone, every tick (no swing timing)
        br.weapon.engaged = None
        if br.weapon.step(Scene.build(t, obs, s, turns[i - 1][1], br.reach), obs, Null()):
            if not fires or t - fires[-1] >= 0.9:
                fires.append(t)
    return fires, att, n_ticks, ticks[-1]["obs"]["t"]


def report(fires, att, n_ticks, T) -> list:
    near = lambda v, t: (lambda j: any(abs(v[k] - t) <= 0.35 for k in (j - 1, j) if 0 <= k < len(v)))(
        bisect.bisect_left(v, t))
    a_ok = sum(near(fires, t) for t in att)
    f_ok = sum(near(att, t) for t in fires)
    return [f"{n_ticks} ticks with our exact position, {T / 60:.1f} min",
            f"user swings {len(att)}: rule agreed within 0.35 s on {a_ok} ({a_ok / len(att):.0%})",
            f"rule firings {len(fires)} ({60 * len(fires) / T:.0f}/min vs user {60 * len(att) / T:.0f}/min): "
            f"user swung too on {f_ok} ({f_ok / max(1, len(fires)):.0%})"]


def main(run, weapon="spear"):
    print("\n".join(report(*rule_fires(run, weapon))))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[a.index("--weapon") + 1] if "--weapon" in a else "spear")
