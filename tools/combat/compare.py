"""Compare brain-v2 runs on the numbers a pet (or anything else on screen) could change: speed of the loop,
perception, what the tracker saw (mobs / pets / tentative), combat (attack held in fights, pauses with the target in
reach, target switches), result (kills by our last hit).  usage: compare.py RUN [RUN ...]"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # run as a plain script too
from maplebot.config import Keys

SWING_KEYS = Keys().swing_keys


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))] if v else None


def one(run):
    T, perc, tot, kinds, states, tracks = [], [], [], collections.Counter(), collections.Counter(), set()
    local = atk = 0
    gaps, cur, last_t, stalls = [], None, None, 0
    tgt_changes, prev_tgt = 0, None
    for l in open(f"{run}/ticks.jsonl"):
        r = json.loads(l)
        tm, o = r["timings"], r["obs"]
        v = tm.get("v2") or {}
        t = o["t"]
        T.append(t)
        if last_t is not None and t - last_t > 0.3:
            stalls += 1
        last_t = t
        perc.append(tm.get("perceive_ms", 0))
        tot.append(tm.get("total_ms", 0))
        for m in o.get("mobs") or []:
            kinds[m.get("kind")] += 1
            states[m["state"]] += 1
            tracks.add((m["id"], m.get("kind")))
        if v.get("target") != prev_tgt:
            tgt_changes += 1
            prev_tgt = v.get("target")
        held = tm.get("held") or []
        a = any(k in held for k in SWING_KEYS)
        if v.get("mode") == "LOCAL" and o.get("me"):
            m = next((m for m in o.get("mobs") or [] if m["id"] == v.get("target")), None)
            if m and m.get("src") != "none":
                dx = (v.get("facing") or 1) * (m["sx"] - o["me"][0])
                if 26 <= dx <= 136:
                    local += 1
                    atk += a
                bad = 26 <= dx <= 136 and not a
                if bad and cur is None:
                    cur = t
                if not bad and cur is not None:
                    gaps.append(t - cur)
                    cur = None
    dur = T[-1] - T[0]
    log = open(f"{run}/log.txt", encoding="utf-8").read()
    k = re.search(r"kills \(last hit\) (\d+)", log)
    kills = int(k.group(1)) if k else None
    n = len(T)
    return {"run": run.split("/")[-1], "min": round(dur / 60, 1), "kills/min": round(kills / dur * 60, 1) if kills else None,
            "fps": round(n / dur, 1), "perceive p50/p90": (q(perc, .5), q(perc, .9)), "tick p90": q(tot, .9),
            "stalls>0.3s/min": round(stalls / dur * 60, 1),
            "tracks/frame mob/pet": (round(kinds["mob"] / n, 2), round(kinds["pet"] / n, 2)),
            "tentative share": round(states["tentative"] / max(1, sum(states.values())), 2),
            "distinct tracks/min": round(len(tracks) / dur * 60),
            "attack held w/ target in sure reach": f"{100 * atk / max(1, local):.0f}%",
            "pauses in reach s/min": round(sum(gaps) / dur * 60, 1),
            "target changes/min": round(tgt_changes / dur * 60)}


if __name__ == "__main__":
    rows = [one(r.rstrip("/\\").replace("\\", "/")) for r in sys.argv[1:]]
    for key in rows[0]:
        print(f"{key:38s}" + "".join(f"{str(r[key]):>20s}" for r in rows))
