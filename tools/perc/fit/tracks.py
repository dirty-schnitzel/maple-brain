"""The fit vs today's well-sighted tracks on a clip without labels (PLAN-fit-speed S6: other maps).

    python tools/perc/fit/tracks.py RUN --replay FILE --fit FIT.jsonl [--sheet 20] [--r 20]

A "well-sighted" track on a frame: a gate replay's mob (today's detector + tracker) that is live / dying (not
tentative / offscreen), sighted this frame (src != none), score >= 0.9, feet 20 px inside the screen's sides and
40 px below its top / 10 px above the play area's bottom (E9's run_tracks rule). FOUND = a fit mob of its type within
--r px in x and y. A miss with a fit mob of ANOTHER type there is a type disagreement (counted apart: on Ant Tunnel IV
the ones looked at were the tracker's type wrong - the game's own name label agreed with the fit); the rest =
nothing there. Fit mobs no track is near (the fit's extra: faint / covered mobs the tracker drops, or false) counted
apart. --sheet N: N "nothing there" misses (seeded) as crops (the track's spot = red cross, the fit's mobs = green
boxes at their feet) -> RUN/fit/misses_<FIT stem>/ for a look by eye; --other: the type disagreements instead
(-> misses_<FIT stem>_other/).
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402

PLAY_H, SW = 700, 1366


def well(m) -> bool:
    return (m.get("state") not in ("tentative", "offscreen") and m.get("src", "none") != "none"
            and (m.get("score") or 0) >= 0.9 and 20 <= m["sx"] < SW - 20 and 40 <= m["sy"] < PLAY_H - 10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--replay", type=Path, required=True)
    ap.add_argument("--fit", type=Path, required=True)
    ap.add_argument("--r", type=int, default=20)
    ap.add_argument("--sheet", type=int, default=0)
    ap.add_argument("--other", action="store_true", help="the sheet shows type disagreements instead")
    a = ap.parse_args()
    rep = {json.loads(line)["n"]: json.loads(line) for line in open(a.replay, encoding="utf-8")}
    fits = [json.loads(line) for line in open(a.fit, encoding="utf-8")]
    tot, found, extra, fit_n, other = Counter(), Counter(), Counter(), Counter(), Counter()
    misses = []
    for fr in fits:
        r = rep.get(fr["n"]) or {}
        fm = fr["mobs"]
        used = set()
        for m in r.get("mobs") or []:
            if not well(m):
                continue
            tot[m["mob"]] += 1
            hit = [i for i, f in enumerate(fm) if f["mob"] == m["mob"] and abs(f["sx"] - m["sx"]) <= a.r
                   and abs(f["sy"] - m["sy"]) <= a.r]
            if hit:
                found[m["mob"]] += 1
                used.update(hit)
            elif any(abs(f["sx"] - m["sx"]) <= a.r and abs(f["sy"] - m["sy"]) <= a.r for f in fm):
                other[m["mob"]] += 1                     # a fit mob of ANOTHER type there: a type disagreement
                if a.other:
                    misses.append((fr["n"], r.get("frame"), m, fm))
            elif not a.other:
                misses.append((fr["n"], r.get("frame"), m, fm))
        near_any = lambda f: any(abs(f["sx"] - m["sx"]) <= 40 and abs(f["sy"] - m["sy"]) <= 40  # noqa: E731
                                 for m in r.get("mobs") or [])
        for f in fm:
            fit_n[f["mob"]] += 1
            if not near_any(f):
                extra[f["mob"]] += 1
    ms = np.array([fr["ms"]["fit"] for fr in fits][3:])
    print(f"{a.fit}: {len(fits)} frames; fit ms p50 {np.median(ms):.2f} p90 {np.percentile(ms, 90):.2f} "
          f"max {ms.max():.2f}")
    for t in sorted(tot):
        print(f"  type {t}: well-sighted tracks {tot[t]}, a fit mob of its type within {a.r} px {found[t]} = "
              f"{100 * found[t] / tot[t]:.1f} %, another type there {other[t]}, nothing {tot[t] - found[t] - other[t]}; "
              f"fit mobs {fit_n[t]}, of them no track within 40 px {extra[t]}")
    T, F, O = sum(tot.values()), sum(found.values()), sum(other.values())
    if T:
        print(f"  all: {F} / {T} = {100 * F / T:.1f} %; any type {100 * (F + O) / T:.1f} %; misses: another type "
              f"there {O}, nothing {T - F - O}")
    if a.sheet and misses:
        out = a.run / "fit" / f"misses_{a.fit.stem}{'_other' if a.other else ''}"
        out.mkdir(parents=True, exist_ok=True)
        random.seed(1)
        pick = random.sample(misses, min(a.sheet, len(misses)))
        rows = []
        for n, name, m, fm in sorted(pick, key=lambda x: x[0]):
            frame = rec.read(a.run, name or f"{n:06d}.png")
            if frame is None:
                continue
            x, y = m["sx"], m["sy"]
            x0, y0 = max(x - 110, 0), max(y - 150, 0)
            x1, y1 = min(x + 110, SW), min(y + 50, PLAY_H)
            img = frame.copy()
            for f in fm:
                cv2.rectangle(img, (f["sx"] - 25, f["sy"] - 60), (f["sx"] + 25, f["sy"]), (0, 255, 0), 1)
            cv2.drawMarker(img, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 12, 1)
            crop = np.concatenate([frame[y0:y1, x0:x1], img[y0:y1, x0:x1]], axis=1)
            fn = f"{n:06d}_{m['mob']}_{x}_{y}.png"
            cv2.imwrite(str(out / fn), cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
            rows.append({"n": n, "file": fn, "track": {k: m.get(k) for k in ("id", "mob", "sx", "sy", "score",
                                                                                   "state", "src", "anim")},
                         "fit": [(f["mob"], f["sx"], f["sy"], f["fit"]["seen"], f["fit"]["opacity"]) for f in fm]})
        (out / "misses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        print(f"  {len(rows)} misses -> {out}")


if __name__ == "__main__":
    main()
