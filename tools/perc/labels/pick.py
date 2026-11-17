"""Pick the frames of a recording to label by eye (PLAN-perception.md step 0: ~300 at native resolution).

    python tools/perc/labels/pick.py RUN [--n 300] [--out tools/perc/labels/NAME_pick.json]

RUN = a run folder or a corpus segment RECORDING#K (tools/perc/frames.py `clip`). What perception saw comes from
the recording's ticks.jsonl; a `record` walk has none: from a replay of the segment (--tracks, default
replay/work.jsonl: tools/perc/replay/run.py first).

Half spread evenly over the run (what perception sees on average), half the hard moments, most wanted first:
a swing of ours in the last 0.4 s with a mob within 200 px (effects, damage numbers over mobs), a live track near
us not sighted this frame (covered or lost), a weak sighting (score < 0.8), a dying track, a track at the screen's
edge, a tentative track, us on a rope. Hard frames keep >= 0.5 s apart. Output: {"run", "frames": [{"n", "frame",
"t", "why"}]}; the labels go to RUN/labels.json v2 (labels/label.py, label_eval.py).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402


def reasons(o: dict, swing_ago: float) -> list:
    me = o.get("me")
    mobs = o.get("mobs") or []
    near = [m for m in mobs if me and abs(m["sx"] - me[0]) <= 200 and abs(m["sy"] - (me[1] + 17)) <= 90]
    why = []
    if swing_ago <= 0.4 and any(m["state"] in ("live", "hidden", "dying") for m in near):
        why.append("swing")
    if any(m["state"] in ("live", "hidden") and m["src"] == "none" for m in near):
        why.append("unseen_near")
    if any(m["state"] == "live" and m["src"] != "none" and (m["score"] or 0) < 0.8 for m in mobs):
        why.append("weak")
    if any(m["state"] == "dying" for m in mobs):
        why.append("dying")
    if any(m["state"] == "live" and not 40 <= m["sx"] <= 1326 for m in mobs):
        why.append("edge")
    if any(m["state"] == "tentative" for m in mobs):
        why.append("tentative")
    if o.get("rope") is not None:
        why.append("rope")
    return why


def main():
    from maplebrain.config import Keys
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--tracks", default="replay/work.jsonl", help="a recording without ticks.jsonl: this replay of it")
    ap.add_argument("--holdout", action="store_true", help="RUN is a hold-out segment of the corpus: only at gates (the use is logged)")
    a = ap.parse_args()
    c = rec.clip(a.run, a.holdout, "labels/pick.py")
    saved = c.sight(a.tracks)
    swings = []
    if (c.run / "keys.jsonl").exists():
        attack = {Keys.attack, Keys.basic_attack}
        swings = [k["t"] for k in map(json.loads, open(c.run / "keys.jsonl", encoding="utf-8"))
                  if k.get("down") and k.get("key") in attack]
    rows, j = [], 0
    for k in saved:
        t = k["t"]
        while j < len(swings) and swings[j] <= t:
            j += 1
        ago = t - swings[j - 1] if j else 1e9
        rows.append({"n": k["n"], "frame": k["frame"], "t": round(t, 2), "why": reasons(k, ago)})
    even = [rows[int(i * (len(rows) - 1) / (a.n // 2 - 1))] for i in range(a.n // 2)]
    for r in even:
        r["why"] = ["even"] + r["why"]
    taken = {r["n"] for r in even}
    order = ["swing", "unseen_near", "weak", "dying", "edge", "tentative", "rope"]
    hard, quota = [], (a.n - len(even)) // len(order) + 1
    for kind in order:                                     # each kind its share, spread over the run
        cand = [r for r in rows if kind in r["why"] and r["n"] not in taken]
        step = max(1, len(cand) // quota)
        for r in cand[::step]:
            if len(hard) >= a.n - len(even):
                break
            if all(abs(r["t"] - h["t"]) >= 0.5 for h in hard) and r["n"] not in taken:
                hard.append(r)
                taken.add(r["n"])
    left = [r for r in rows if r["why"] and r["n"] not in taken]           # fill up with any hard frame
    for r in left[::max(1, len(left) // max(1, a.n - len(even) - len(hard)))]:
        if len(even) + len(hard) >= a.n:
            break
        hard.append(r)
    frames = sorted(even + hard, key=lambda r: r["n"])
    out = a.out or ROOT / "tools" / "perc" / "labels" / f"{c.name}_pick.json"
    out.write_text(json.dumps({"run": str(a.run).replace("\\", "/"), "frames": frames}, indent=0), encoding="utf-8")
    from collections import Counter
    c = Counter(w for r in frames for w in r["why"])
    print(f"{len(frames)} frames of {len(rows)} saved -> {out}")
    print("  reasons (a frame can have several):", dict(c.most_common()))


if __name__ == "__main__":
    main()
