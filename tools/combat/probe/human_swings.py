"""The user's own play, by SWINGS (not presses): clean kills, how fast the mashing stops, swing rhythm.

    python tools/combat/probe/human_swings.py runs/play/RUN [SWING_S]

The game's rule (swing_live.py in the Regular Sauna, 2026-11-08, polearm speed 8): an attack key-DOWN starts a swing
when none is going on; key-downs during a swing are ignored (not queued); the swing ends ~0.90 s after the key-down
(spear: ~0.80). So the keylog gives our swings: a press starts one if the last one is over. SWING_S default 0.90.

Kills: a tracked mob turns `dying` in front of us (0..165 px, |dy| <= 40) within 1.2 s after one of our swings
started. A swing started after that death with no live mob in front = a swing at nothing (the unclean kill).
"""
import bisect
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from maplebot.config import Keys  # noqa: E402

R = Path(sys.argv[1])
SWING_S = float(sys.argv[2]) if len(sys.argv) > 2 else 0.90
T = [json.loads(x) for x in open(R / "ticks.jsonl", encoding="utf-8")]
K = [json.loads(x) for x in open(R / "keys.jsonl", encoding="utf-8")]
K = [k for k in K if not k.get("inj")]
ATT = set(Keys().swing_keys)
press = [k["t"] for k in K if k["key"] in ATT and k["down"]]
turns = [(k["t"], k["key"]) for k in K if k["key"] in ("left", "right") and k["down"]]
tt = [t for t, _ in turns]
times = [r["obs"]["t"] for r in T]


def face(t):
    i = bisect.bisect_right(tt, t)
    return 0 if not i else (1 if turns[i - 1][1] == "right" else -1)


def tick(t):
    return T[max(0, bisect.bisect_right(times, t) - 1)]


def me(r):
    o = r["obs"]
    return o.get("me_map") or o.get("map_pos")


def pct(v, ps=(0.1, 0.5, 0.9)):
    v = sorted(v)
    return [round(v[min(len(v) - 1, int(p * len(v)))], 2) for p in ps] if v else None


# swings from presses
swings, end = [], -9.0
for t in press:
    if t >= end:
        swings.append(t)
        end = t + SWING_S
ignored = len(press) - len(swings)

# deaths in front of a swing
first_dying = {}
for r in T:
    for m in r["obs"].get("mobs") or []:
        if m.get("kind") == "mob" and m["state"] == "dying" and m["id"] not in first_dying:
            first_dying[m["id"]] = (r["obs"]["t"], m["x"], m["y"])
kills = []
for i, (td, x, y) in sorted(first_dying.items(), key=lambda kv: kv[1][0]):
    j = bisect.bisect_right(swings, td) - 1
    if j < 0 or td - swings[j] > 1.2:
        continue
    p = me(tick(swings[j]))
    if not p:
        continue
    f = face(swings[j])
    if 0 <= (x - p[0]) * f <= 165 and abs(y - p[1]) <= 40:
        kills.append((td, swings[j]))


def live_in_front(t):
    r = tick(t)
    p, f = me(r), face(t)
    if not p:
        return None
    return any(m.get("kind") == "mob" and m["state"] in ("live", "hit") and -10 <= (m["x"] - p[0]) * f <= 165
               and abs(m["y"] - p[1]) <= 40 for m in r["obs"].get("mobs") or [])


clean, dirty, wasted_n = 0, 0, collections.Counter()
stop_after, next_swing, press_after = [], [], []
for td, ts in kills:
    after = [s for s in swings if td < s <= td + 1.0]
    wasted = [s for s in after if live_in_front(s) is False]
    wasted_n[len(wasted)] += 1
    clean += not wasted
    dirty += bool(wasted)
    nxt = [s for s in swings if s > td]
    if nxt:
        next_swing.append(nxt[0] - td)
    ps = [p for p in press if td < p <= td + 1.5]
    press_after.append(len(ps))
    # mashing stopped: last press before a >= 0.5 s pause, relative to the death
    k = bisect.bisect_right(press, ts)
    last = ts
    while k < len(press) and press[k] - last < 0.5:
        last = press[k]
        k += 1
    stop_after.append(last - td)

dur = times[-1] - times[0]
print(f"{R.name}: {dur / 60:.1f} min, swing {SWING_S} s")
print(f"presses {len(press)}, swings {len(swings)} ({len(swings) / dur * 60:.0f}/min), presses ignored mid-swing {ignored}")
g = [b - a for a, b in zip(swings, swings[1:]) if b - a < 2.0]
print(f"swing start -> next swing start (< 2 s) p10/50/90 {pct(g)};  -> next swing after its end: "
      f"p10/50/90 {pct([x - SWING_S for x in g])} s")
print(f"kills by our swing: {len(kills)}; clean (no swing at nothing within 1 s): {clean}; unclean {dirty} "
      f"(swings at nothing per kill: {dict(wasted_n)})")
print(f"killing swing start -> death visible p10/50/90 {pct([td - ts for td, ts in kills])}")
print(f"death -> next swing start p10/50/90 {pct(next_swing)}")
print(f"death -> last press of that burst (mashing stops) p10/50/90 {pct(stop_after)}; presses in 1.5 s after the "
      f"death p50 {pct(press_after, (0.5,))}")
