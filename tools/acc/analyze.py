"""Run analysis for accuracy work: python tools/acc/analyze.py runs/NAME
Reads ticks.jsonl + log.txt: EXP gains (true kills), outcome counts, HP hits and what we were doing,
walk->swing transitions (target dx at the swing, mob speed, HP lost in the next 1.2 s)."""
import json, re, sys, collections
from pathlib import Path

run = Path(sys.argv[1])
rows = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
log = open(run / "log.txt", encoding="utf-8").read()
cx = lambda b: b[0] + b[2] / 2

def tdx(o):
    if o["target"] is None or o["me"] is None:
        return None
    return cx(o["target"]) - o["me"][0]

gains = []; prev = None
for r in rows:
    e = r["obs"]["exp_points"]
    if e is not None and prev is not None and e != prev:
        gains.append((round(r["obs"]["t"], 1), e - prev))
    if e is not None:
        prev = e
print("EXP gains:", len(gains), [g for g in gains])
stats = re.findall(r"stats (\{.*\})", log)
if stats:
    s = json.loads(stats[-1])
    print({k: s[k] for k in ("engagements", "kills", "others_kills", "lost", "closer_switches", "back_offs",
                             "short_steps", "self_lost", "fps", "walk_pickups", "loot_pickups")})
outc = collections.Counter(re.sub(r"\(.*?\)|dx [-+]\d+|[-+]?\d+", "", m).strip()
                           for m in re.findall(r"ENGAGE -> \w+: (.*)", log))
print("outcomes:", dict(outc))
modes = collections.Counter(r["mode"] for r in rows)
print("modes:", {k: f"{v / len(rows):.0%}" for k, v in modes.items()})

# HP drops (raw), what we held, target dx
print("\nHP hits (t, hp lost, held, target dx, mode):")
held = None; hits = 0
last_hp = None; last_hit = -9
for r in rows:
    o = r["obs"]
    for a in r["actions"]:
        m = re.match(r"Hold\((\w+)\)", a)
        if m: held = m.group(1)
        if a.startswith("Release"): held = None
    hp = o["hp_raw"]
    if hp is not None:
        hist = [h for h in (last_hp or []) if o["t"] - h[0] <= 0.4] + [(o["t"], hp)]
        top = max(h[1] for h in hist)
        if top - hp >= 0.02 and o["t"] - last_hit > 0.6:
            hits += 1; last_hit = o["t"]
            d = tdx(o)
            print(f"  {o['t']:6.2f} -{top - hp:.2f} held={held} dx={'' if d is None else f'{d:+.0f}'} {r['mode']}")
        last_hp = hist
print("hits:", hits)

# walking -> attack transitions
print("\nwalk->swing (t, dx at swing, dx 0.15s before, closing px/s, hp lost within 1.2 s):")
held = None
for i, r in enumerate(rows):
    o = r["obs"]
    new = held
    for a in r["actions"]:
        m = re.match(r"Hold\((\w+)\)", a)
        if m: new = m.group(1)
        if a.startswith("Release"): new = None
    if held in ("left", "right") and new == "space":
        d = tdx(o)
        back = [x for x in rows[max(0, i - 6):i] if o["t"] - x["obs"]["t"] >= 0.12 and tdx(x["obs"]) is not None]
        v = None
        if back and d is not None:
            b = back[-1]; v = (abs(tdx(b["obs"])) - abs(d)) / (o["t"] - b["obs"]["t"])
        hp0 = o["hp_raw"]; lost = 0
        for x in rows[i:i + 40]:
            if x["obs"]["t"] - o["t"] > 1.2: break
            if x["obs"]["hp_raw"] is not None and hp0 is not None: lost = max(lost, hp0 - x["obs"]["hp_raw"])
        print(f"  {o['t']:6.2f} dx={'' if d is None else f'{d:+.0f}'} closing={'' if v is None else f'{v:.0f}'} lost={lost:.2f}")
    held = new

seek_seen = [r for r in rows if r["mode"] == "SEEK" and r["obs"]["sprite_mobs"]]
print(f"\nSEEK with a mob sprite on screen: {len(seek_seen)} ticks ({len(seek_seen) / len(rows):.1%})")
for m in re.findall(r"\n\s*([\d.]+)s (too close.*|slid short.*|.*step in.*)", log):
    print("  ", m)
