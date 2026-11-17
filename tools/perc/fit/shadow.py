"""The fit in shadow (PLAN-perception.md step 3.3) on the gate clips: the replay's own rows (FrameFacts v3 fit /
fit_ms / fit_hints beside the tracker's tracks of the same frame).

    python tools/perc/fit/shadow.py [--clips a,b] [--fp FINGERPRINT] [--r 20]

Per clip (the working tree's gate replay RUN/replay/fp_<fp>_<clip>.jsonl, tools/perc/replay/gate.py):
- fit vs today's well-sighted tracks (tracks.py's rule `well`): a fit mob of the track's type within --r px in x and
  y = found; another type there = a type disagreement; the S6 numbers came from separate fit runs on the same frames.
- the hints (Fitter.hints): coasting track-frames (confirmed, on screen, src none) and how many the fit found anyway /
  got a look; each look read by the fit's own mob rule: SEEN (n_seen >= 60, >= 3 % of the informative pixels, ABSENT
  <= 10 %), else ABSENT (>= 50 % of the informative pixels show the scene), else COVERED (incl. no informative pixel).
- fit / hints ms from the rows (the replay has no game timing: compare clips, not with the bench).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
import gate  # noqa: E402
from tracks import well  # noqa: E402

LIVE = ("live", "hit", "hidden", "dying")


def verdict(h) -> str:
    n = h["n_inf"]
    if n and h["n_seen"] >= 60 and h["n_seen"] >= 0.03 * n and h["n_abs"] <= 0.1 * n:
        return "seen"
    return "absent" if n and h["n_abs"] >= 0.5 * n else "covered"


def near(f, m, r, same=True):
    return (not same or f["type"] == m["mob"]) and abs(f["feet"][0] - m["sx"]) <= r and abs(f["feet"][1] - m["sy"]) <= r


def clip(rows, r):
    tot = found = other = 0
    coast, coast_found, looked = Counter(), Counter(), Counter()
    v = {s: Counter() for s in ("live", "dying")}
    ms, hms = [], []
    n_fit = 0
    for k in rows:
        fm = k.get("fit")
        if fm is None:
            continue
        n_fit += 1
        ms.append(k["fit_ms"])
        hms.append((k.get("ms") or {}).get("hints", 0.0))
        hints = {h["id"]: h for h in k.get("fit_hints") or []}
        for m in k["mobs"]:
            if well(m):
                tot += 1
                if any(near(f, m, r) for f in fm):
                    found += 1
                elif any(near(f, m, r, False) for f in fm):
                    other += 1
            if m.get("kind", "mob") == "mob" and m["state"] in LIVE and m["src"] == "none":
                s = "dying" if m["state"] == "dying" else "live"
                coast[s] += 1
                if any(near(f, m, r) for f in fm):
                    coast_found[s] += 1
                if m["id"] in hints:
                    looked[s] += 1
                    v[s][verdict(hints[m["id"]])] += 1
    return dict(frames=len(rows), fit_frames=n_fit, tot=tot, found=found, other=other, coast=coast,
                coast_found=coast_found, looked=looked, v=v, ms=ms, hms=hms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default=None)
    ap.add_argument("--fp", default=None, help="the replays' fingerprint (default: the working tree's)")
    ap.add_argument("--r", type=int, default=20)
    a = ap.parse_args()
    fp = a.fp or gate.fingerprint(None)
    clips = a.clips.split(",") if a.clips else list(gate.CLIPS)
    print(f"fit in shadow, replays fp {fp}, r {a.r} px")
    for c in clips:
        p = ROOT / gate.CLIPS[c][0] / "replay" / f"fp_{fp}_{c}.jsonl"
        if not p.exists():
            print(f"  {c}: no replay {p.name}")
            continue
        d = clip([json.loads(line) for line in open(p, encoding="utf-8")], a.r)
        pc = lambda x, n: f"{100 * x / n:.1f}" if n else "-"  # noqa: E731
        ms = np.array(d["ms"]) if d["ms"] else np.zeros(1)
        print(f"  {c}: {d['fit_frames']} / {d['frames']} frames with the fit; well-sighted {d['tot']}: same type "
              f"{pc(d['found'], d['tot'])} %, any type {pc(d['found'] + d['other'], d['tot'])} %; fit ms p50 "
              f"{np.median(ms):.2f} p90 {np.percentile(ms, 90):.2f}, hints ms p50 {np.median(d['hms'] or [0]):.2f} "
              f"p90 {np.percentile(d['hms'] or [0], 90):.2f}")
        for s in ("live", "dying"):
            n, lk, vv = d["coast"][s], d["looked"][s], d["v"][s]
            print(f"      coasting {s}: {n} track-frames, the fit found {pc(d['coast_found'][s], n)} %, looked at "
                  f"{lk}: SEEN {pc(vv['seen'], lk)} %, ABSENT {pc(vv['absent'], lk)} %, COVERED {pc(vv['covered'], lk)} %")


if __name__ == "__main__":
    main()
