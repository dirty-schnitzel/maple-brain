"""PLAN-loot.md section 7: grade drop sightings against truth - recall per class, false per class, identity, position.

    python tools/loot/drop_eval.py SET --finder finder_before.jsonl [--list] [--misses misses.json]
        SET = a synth_drops.py OUT (synth.json: exact truth) or, later, a run with labels.json (S6, matched by feet)

Truth drops (synth.json `drops`): kind rest / air, cls clear / pile / mob / player / effect / ui / edge / flight, vis
(share of its on-screen opaque pixels the frame shows), front (share under front scenery of its layer). Grading
classes: `front` = any drop with front > 0 (out of its own class), `weak picture` = a picture the finder cannot vote for
(items.json weak: see-through), pile split at vis 0.5. GATED (section 7.3): REST recall >= 99 % on the VISIBLE resting
drops = clear / mob / player with nothing over them + pile >= 50 % visible (front 0, not weak); 0 REST and 0 AIR on the
drop-free frames and on every not-drop (window icons, worn gear, mob parts); identity right on 100 % of the found;
feet exact (0 px) on every found one. Reported, not gated: effect / ui / edge / pile < 50 % / front / flight (AIR).
Matching (synth): a sighting of the drop's picture class (item, meso frame) within 3 px in x and 8 in y of its box ->
found (REST / AIR / weak), offset = position error; else a sighting of another class whose box overlaps >= 50 % ->
WRONG identity (or a TWIN when its picture equals the drop's on every visible pixel). A REST / AIR sighting matched to
no drop = FALSE, classed by the not-drop box it lies on (>= 50 % of its box), the drop-free frame, or "other".
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

GATED = ("clear", "mob", "player", "pile >= 50 %")


def overlap(a, b) -> float:
    """Share of box a covered by box b (x, y, w, h)."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return max(0, x1 - x0) * max(0, y1 - y0) / max(1, a[2] * a[3])


def grade_class(d: dict, weak) -> str:
    if weak[d["g"]]:
        return "weak picture"
    if d["kind"] == "air":
        return "flight"
    if d.get("front", 0) > 0:
        return "front"
    if d["cls"] == "pile":
        return "pile >= 50 %" if d["vis"] >= 0.5 else "pile < 50 %"
    return d["cls"]


def evaluate(truth: dict, rows: dict, items, frames_dir: Path | None = None) -> dict:
    """truth: synth.json; rows: frame name -> finder row. -> {"recall": {cls: Counter}, "false": Counter, "wrong":
    [..], "twins": [..], "pos": Counter, "misses": [..], "falses": [..], "n": Counter}"""
    rec = defaultdict(Counter)
    false, pos, n = Counter(), Counter(), Counter()
    wrong, twins, misses, falses = [], [], [], []
    for name, f in truth["frames"].items():
        r = rows.get(name)
        if r is None:
            n["frames without a finder row"] += 1
            continue
        n["frames"] += 1
        S = r["drops"]
        used = set()
        img = None
        pairs = []                      # pass 1: every drop's own picture class nearby (a pile's top item first)
        for j, d in enumerate(f["drops"]):
            x, y = d["box"][:2]
            for i, s in enumerate(S):
                if (s["item"], s["f"]) == (d["item"], d["f"]):
                    dx, dy = s["box"][0] - x, s["box"][1] - y
                    if abs(dx) <= 3 and abs(dy) <= 8:
                        pairs.append((abs(dx) + abs(dy), j, i, dx, dy))
        got = {}
        for _, j, i, dx, dy in sorted(pairs):
            if j not in got and i not in used:
                got[j] = (i, dx, dy)
                used.add(i)
        for j, d in enumerate(f["drops"]):
            c = grade_class(d, items.weak)
            rec[c]["n"] += 1
            x, y, w, h = d["box"]
            if j in got:
                i, dx, dy = got[j]
                s = S[i]
                rec[c][s["kind"]] += 1
                pos[(dx, dy)] += 1
                if s["kind"] != ("rest" if d["kind"] == "rest" else "air"):
                    misses.append({"frame": name, "class": c, "drop": d, "got": s})
                continue
            meso = [(i, s) for i, s in enumerate(S) if i not in used and d["item"] >= 9000000 and s["item"] == d["item"]
                    and overlap(s["box"], d["box"]) >= 0.5]
            if meso:                    # the right meso size, another animation frame: not a wrong item
                used.add(meso[0][0])
                rec[c]["meso frame"] += 1
                n["meso found as another frame"] += 1
                continue
            other = [(i, s) for i, s in enumerate(S) if i not in used and overlap(s["box"], d["box"]) >= 0.5]
            if other:
                i, s = max(other, key=lambda t: overlap(t[1]["box"], d["box"]))
                used.add(i)
                twin = False
                if frames_dir is not None:          # the visible pixels of both pictures the same?
                    if img is None:
                        img = cv2.imread(str(frames_dir / f["frame"]))
                    ox, oy = (f.get("window") or [0, 0])[:2]
                    p, q = items.pics[d["g"]], None
                    for g in range(len(items)):
                        if items.item[g] == s["item"] and items.f[g] == s["f"]:
                            q = items.pics[g]
                            break
                    if q is not None and q.shape == p.shape and tuple(s["box"]) == tuple(d["box"]):
                        crop = img[y - oy:y - oy + h, x - ox:x - ox + w].astype(np.int16)
                        vis = (p[..., 3] == 255) & (np.abs(crop - p[..., :3]).max(2) <= 4) if crop.shape[:2] == (h, w) \
                            else np.zeros((h, w), bool)
                        twin = bool(vis.any()) and np.array_equal(q[vis], p[vis])
                (twins if twin else wrong).append({"frame": name, "class": c, "drop": d, "got": s})
                rec[c]["twin" if twin else "wrong"] += 1
                continue
            rec[c]["none"] += 1
            misses.append({"frame": name, "class": c, "drop": d, "got": None})
        for i, s in enumerate(S):
            if i in used or s["kind"] == "weak":
                continue
            on = [nd for nd in f["notdrops"] if overlap(s["box"], nd["box"]) >= 0.5]
            cls = on[0]["cls"] if on else ("free" if f["case"] == "free" else "other")
            false[(cls, s["kind"])] += 1
            falses.append({"frame": name, "case": f["case"], "class": cls, "got": s})
        for nd in f["notdrops"]:
            n[f"not-drop {nd['cls']}"] += 1
        n[f"weak sightings"] += sum(1 for i, s in enumerate(S) if i not in used and s["kind"] == "weak")
    return {"recall": rec, "false": false, "wrong": wrong, "twins": twins, "pos": pos, "misses": misses,
            "falses": falses, "n": n}


def report(ev: dict, items, list_all: bool = False, log=print) -> bool:
    rec = ev["recall"]
    log("recall (REST / AIR / weak / wrong identity / twin / not seen), by class:")
    order = ["clear", "mob", "player", "pile >= 50 %", "pile < 50 %", "effect", "ui", "edge", "front", "flight",
             "weak picture"]
    for c in order + sorted(set(rec) - set(order)):
        if c not in rec:
            continue
        r = rec[c]
        tot = r["n"]
        main = r["air"] if c == "flight" else r["rest"]
        log(f"  {c:14s} n {tot:5d} | {'AIR' if c == 'flight' else 'REST'} {main:5d} = {100 * main / max(1, tot):6.2f} % | "
            f"rest {r['rest']} air {r['air']} weak {r['weak']} wrong {r['wrong']} twin {r['twin']} none {r['none']}"
            + ("   [gated]" if c in GATED else ""))
    gn = sum(rec[c]["n"] for c in GATED)
    gr = sum(rec[c]["rest"] for c in GATED)
    found = sum(rec[c][k] for c in rec for k in ("rest", "air", "weak"))
    nw = sum(rec[c]["wrong"] for c in rec)
    log(f"GATED visible resting drops: REST {gr} / {gn} = {100 * gr / max(1, gn):.2f} % (gate >= 99 %)")
    fr = ev["false"]
    nf = sum(fr.values())
    log(f"FALSE REST / AIR: {nf} (gate 0)" + (": " + ", ".join(f"{c} {k} {v}" for (c, k), v in sorted(fr.items()))
                                               if nf else ""))
    log("  not-drops graded: " + ", ".join(f"{k[9:]} {v}" for k, v in sorted(ev["n"].items()) if k.startswith("not-drop"))
        + f"; weak sightings (allowed) {ev['n']['weak sightings']}; frames {ev['n']['frames']}")
    log(f"IDENTITY: wrong {nw} of {found + nw} found (gate 0); twins (same visible pixels, another class) "
        f"{len(ev['twins'])}")
    off = {k: v for k, v in ev["pos"].items() if k != (0, 0)}
    log(f"POSITION: {ev['pos'][(0, 0)]} of {sum(ev['pos'].values())} found exactly at the box (gate: all); off: "
        + (", ".join(f"{k} x{v}" for k, v in sorted(off.items(), key=lambda t: -t[1])[:10]) or "none"))
    ok = gr >= 0.99 * gn and nf == 0 and nw == 0 and not off
    log(f"S4 GATE (section 7.3 on synth): {'MET' if ok else 'NOT MET'}")
    if list_all:
        for m in ev["misses"]:
            d, s = m["drop"], m["got"]
            if m["class"] not in GATED and not list_all == "all":
                continue
            log(f"  miss {m['frame']} {m['class']:13s} {d['item']} {items.name(d['item'])[:28]:28s} box {d['box']} vis "
                f"{d['vis']} -> " + (f"{s['kind']} seen {s['seen']}/{s['n_op']} abs {s['absent']} under {s['under']} "
                                    f"front {s['front']} mob {s['mob']} ring {s['ring']} dy {s['dy']}" if s else "nothing"))
        for m in ev["falses"]:
            s = m["got"]
            log(f"  false {m['frame']} {m['case']:8s} on {m['class']:8s} {s['kind']} {s['item']} "
                f"{items.name(s['item'])[:28]:28s} box {s['box']} seen {s['seen']}/{s['n_op']} dy {s['dy']} ring {s['ring']}")
        for m in ev["wrong"]:
            log(f"  wrong {m['frame']} {m['class']} {m['drop']['item']} {items.name(m['drop']['item'])[:24]} -> "
                f"{m['got']['item']} {items.name(m['got']['item'])[:24]} box {m['got']['box']}")
    return ok


def load_rows(path: Path) -> dict:
    return {r["frame"]: r for r in (json.loads(l) for l in open(path, encoding="utf-8"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("--finder", default="finder_before.jsonl")
    ap.add_argument("--list", nargs="?", const="gated", default=None)
    ap.add_argument("--misses", default="")
    a = ap.parse_args()
    from maplebrain.gamedata import load_items
    items = load_items()
    sd = Path(a.set)
    truth = json.loads((sd / "synth.json").read_text(encoding="utf-8"))
    ev = evaluate(truth, load_rows(sd / a.finder), items, sd / "frames")
    report(ev, items, a.list)
    if a.misses:
        (sd / a.misses).write_text(json.dumps({k: ev[k] for k in ("misses", "falses", "wrong", "twins")}, indent=0),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()
