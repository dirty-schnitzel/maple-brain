"""Find ENGAGE stops in recorded runs: ticks where no key is held and no swing/step is tapped (>= 0.15 s).
Usage: python tools/engage_stops.py runs/NAME [runs/NAME2 ...]"""
import json, sys, re, collections
MOVE = ("left", "right", "up", "down")
def parse(a):
    m = re.match(r"(\w+)\((.*)\)", a)
    return (m.group(1), m.group(2)) if m else (a, "")
for run in sys.argv[1:]:
    ticks = [json.loads(l) for l in open(f"{run}/ticks.jsonl", encoding="utf-8")]
    log = open(f"{run}/log.txt", encoding="utf-8").read().splitlines()
    held = None
    spans, cur = [], None
    for tk in ticks:
        acts = [parse(a) for a in tk["actions"]]
        swing = False
        for k, arg in acts:
            if k == "Hold": held = arg
            elif k == "Release": held = None
            elif k == "Tap":
                key = arg.split(",")[0].strip("'\" ")
                if key in MOVE or held not in MOVE: held = None
                if key in MOVE or key == "space": swing = True   # a step/turn is movement
        o = tk["obs"]; t = o["t"]
        idle = tk["mode"] == "ENGAGE" and held is None and not swing
        if idle:
            d = None
            if o["target"] and o["me"]:
                d = o["target"][0] + o["target"][2] / 2 - o["me"][0]
            if cur is None: cur = {"t0": t, "n0": tk["n"], "d": [], "bar": o["target_has_bar"]}
            cur["t1"] = t; cur["d"].append(d)
        elif cur is not None:
            cur["end_t"] = t; cur["next"] = [a for a in tk["actions"]][:3]; cur["next_mode"] = tk["mode"]
            spans.append(cur); cur = None
    print(f"== {run}: {len(ticks)} ticks, {ticks[-1]['obs']['t']:.0f}s")
    tot = 0
    for s in spans:
        dur = s["end_t"] - s["t0"]
        if dur < 0.15: continue
        tot += dur
        ds = [round(x) for x in s["d"] if x is not None]
        ctx = [l for l in log if (m := re.match(r"\s*([\d.]+)s", l)) and s["t0"] - 0.6 <= float(m.group(1)) <= s["end_t"] + 0.05]
        print(f"{s['t0']:6.2f}-{s['end_t']:6.2f} ({dur:.2f}s) dx {ds[:1]}..{ds[-1:]} bar={s['bar']} -> {s['next_mode']} {s['next']}")
        for c in ctx[-4:]: print("        |", c.strip()[:150])
    print(f"   total idle-in-ENGAGE >=0.15s: {tot:.1f}s")
