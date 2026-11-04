"""Tracker vs the reference (truth.jsonl from tools/perc/truth.py).

  python tools/perc/track_eval.py RUN [--tracks tracks.jsonl] [--truth truth.jsonl] [--near 100] [--list N]

Per reference frame: a reference mob is found if a confirmed track (not tentative) of the same mob type has its
screen feet within 20 px. Reported for mobs near us (|dx| <= --near, |dy| <= 80) and for the whole screen; 'seen' =
the track saw it this frame, 'any' = coasting tracks count. False: confirmed tracks seen this frame with no
reference mob within 25 px; ghosts: coasting tracks with none. Fragments: confirmed tracks born next to (60 px,
1.5 s) where a track of the same mob type ended - one mob, a new id.
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--tracks", default="tracks.jsonl")
    ap.add_argument("--truth", default="truth.jsonl")
    ap.add_argument("--near", type=float, default=100)
    ap.add_argument("--list", type=int, default=0, help="print N missed near mobs")
    ap.add_argument("--any-type", action="store_true", help="a track of any mob type counts (look-alikes)")
    a = ap.parse_args()
    run = Path(a.run)
    tr = {r["n"]: r for r in map(json.loads, open(run / a.tracks, encoding="utf-8"))}
    truth = [json.loads(l) for l in open(run / a.truth, encoding="utf-8")]
    c = dict(near=0, near_seen=0, near_any=0, all=0, all_seen=0, all_any=0, conf_seen=0, false=0, coast=0, ghost=0)
    missed = []
    for row in truth:
        r = tr.get(row["n"])
        if r is None or not row.get("me"):
            continue
        me = row["me"]
        conf = [t for t in r["tracks"] if t["state"] != "tentative"]

        def match(m, pool, tol=20):
            return any((a.any_type or t["mob"] == m["id"]) and abs(t["sx"] - m["feet"][0]) <= tol and abs(t["sy"] - m["feet"][1]) <= tol
                       for t in pool)
        seen = [t for t in conf if t["src"] != "none"]
        for m in row["mobs"]:
            near = abs(m["feet"][0] - me[0]) <= a.near and abs(m["feet"][1] - me[1]) <= 80
            s, an = match(m, seen), match(m, conf)
            c["all"] += 1
            c["all_seen"] += s
            c["all_any"] += an
            if near:
                c["near"] += 1
                c["near_seen"] += s
                c["near_any"] += an
                if not an:
                    missed.append((row["n"], row["t"], m["id"], m["feet"], m["anim"], m["score"]))
        for t in conf:
            ok = any((a.any_type or t["mob"] == m["id"]) and abs(t["sx"] - m["feet"][0]) <= 25 and abs(t["sy"] - m["feet"][1]) <= 25
                     for m in row["mobs"])
            if t["src"] != "none":
                c["conf_seen"] += 1
                c["false"] += not ok
            elif 0 <= t["sx"] < 1366:
                c["coast"] += 1
                c["ghost"] += not ok
    # fragments over the whole run
    rows = sorted(tr.values(), key=lambda r: r["n"])
    alive, ends, frags, births = {}, [], 0, 0
    for r in rows:
        now = {t["id"]: t for t in r["tracks"] if t["state"] != "tentative"}
        for i, t in alive.items():
            if i not in now:
                ends.append((r["t"], t["mob"], t["x"], t["y"]))
        for i, t in now.items():
            if i not in alive:
                births += 1
                if any(m == t["mob"] and 0 <= r["t"] - te <= 1.5 and abs(x - t["x"]) < 60 and abs(y - t["y"]) < 40
                       for te, m, x, y in ends):
                    frags += 1
        alive = now
    pct = lambda x, n: f"{100 * x / max(n, 1):.1f} %"  # noqa: E731
    print(f"reference frames {len(truth)}, mobs {c['all']} (near us {c['near']})")
    print(f"near us : seen {pct(c['near_seen'], c['near'])}   incl. coasting {pct(c['near_any'], c['near'])}")
    print(f"screen  : seen {pct(c['all_seen'], c['all'])}   incl. coasting {pct(c['all_any'], c['all'])}")
    print(f"false   : {c['false']} of {c['conf_seen']} seen tracks ({pct(c['false'], c['conf_seen'])});  "
          f"ghosts {c['ghost']} of {c['coast']} coasting")
    print(f"tracks born {births}, fragments {frags} ({pct(frags, births)})")
    for m in missed[:a.list]:
        print("  missed", m)


if __name__ == "__main__":
    main()
