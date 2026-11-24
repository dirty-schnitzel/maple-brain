"""PLAN-tracker step 7's gate: the REAL hotkey reader (maplebrain/perception/slots.py) and the amounts tracked by
maplebrain/track/us.py, run over recorded footage and against the step 1 labels L7. The checks of a capture are the
prototype's (tools/perc/track/proto_slots.py `report`: the HUD's potion rises against the -1 steps, the presses of
the key log, the flicks), run on this code's reads.

    python tools/perc/track/slots_gate.py selftest                 every client picture drawn into a cell, read back
    python tools/perc/track/slots_gate.py run CAP [CAP ...] | --all [--every N]   every frame -> reads + report
    python tools/perc/track/slots_gate.py stretches [CAP ...]      every stretch of frames with an unreadable cell
                                                                   (+ a sheet: one moment per stretch, by eye)
    python tools/perc/track/slots_gate.py l7                       the reads against the labels L7 (100 frames)
    python tools/perc/track/slots_gate.py bench [CAP]              ms: a full read, an unchanged frame, a sequence
    python tools/perc/track/slots_gate.py sheet OUT.png CAP@n[@note] ...          the bar x4 + what a read says

--all = the 43 captures the prototype read (the folders of CORPUS/work/track-plan/slots) + the quickslot footage
20261124_093410_1#0. Everything goes to CORPUS/work/track-plan/slots7/ (re-creatable): <cap>/reads.npz,
events.json, report.txt; stretches.txt, sheets.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from maplebrain.config import CORPUS  # noqa: E402
from maplebrain.perception import slots as S  # noqa: E402
from maplebrain.track.us import Slots  # noqa: E402

BASE = Path(os.environ.get("MAPLE_CORPUS") or CORPUS) / "work" / "track-plan"
OUT = BASE / "slots7"
PROTO_OUT = BASE / "slots"
NEW = "20261124_093410_1#0"


def cap_dir(cap: str) -> Path:
    return OUT / str(cap).replace("#", "_").replace("\\", "_").replace("/", "_").replace(":", "")


def all_caps() -> list:
    caps = [d.name[::-1].replace("_", "#", 1)[::-1] for d in sorted(PROTO_OUT.iterdir())
            if (d / "reads.npz").exists()]
    return caps + ([NEW] if NEW not in caps else [])


# ---- the self-test --------------------------------------------------------------------------------------------------
def selftest(seed: int = 1, rows_list=(2, 3), log=print) -> dict:
    """Every content picture of the pack drawn into a cell the way the client does (keycap + content + a random
    amount + a key label) and read back; every key label on an empty keycap. -> per rows: counts. `wrong` = read as
    another picture / amount / key, a true look-alike (`alts`: pictures equal under the label or the digits drawn,
    or a label shared by keys) not counted."""
    rng = np.random.default_rng(seed)
    out = {}
    for rows in rows_list:
        p = S.Pack(rows)
        K = len(p.cells)
        usual = [i for i, k in enumerate(p.lab_key) if k in S.DEFAULT_KEYS[2]]
        n = wrong = alts = bad_lab = 0
        for cls in range(len(p.content)):
            k = int(rng.integers(K))
            li = int(rng.choice(usual)) if rng.random() < 0.7 else int(rng.integers(len(p.lab_key)))
            m = p.member(cls)
            amount, digs = None, []
            if m["kind"] == "item" and rng.random() < 0.8:
                amount = int(rng.choice([0, 1, 7, 10, 11, 99, 100, 111, 200, 999, 1000, 1111, 4321,
                                         int(rng.integers(0, 2000))]))
                x = S.DIGITS_AT[0]
                for ch in str(amount):
                    digs.append((int(ch), x))
                    x += p.dg_w[int(ch)]
                if x > S.CELL:
                    amount, digs = None, []
            r, _ = p.read_cell(p.expect(k, cls, digs, li), k)
            n += 1
            alts += bool(r.alts)
            if cls not in (r.cls,) + r.alts or r.amount != amount or r.key != p.lab_key[li]:
                wrong += 1
                log(f"  rows {rows}: class {cls} {m['kind']} {m['id']} '{m.get('name')}' amount {amount} label "
                    f"{p.lab_key[li]} read as {r}")
        for li in range(len(p.lab_key)):
            k = int(rng.integers(K))
            r, _ = p.read_cell(p.expect(k, -1, [], li), k)
            bad_lab += not (r.kind == "empty" and r.key == p.lab_key[li])
        out[rows] = {"pictures": n, "wrong": wrong, "alts": alts, "labels": len(p.lab_key), "labels_wrong": bad_lab,
                     "labels_shared": [[p.lab_key[i]] + a for i, a in enumerate(p.lab_also) if a]}
        log(f"{rows}-row bar: {n} pictures read back: {wrong} wrong, {alts} with a look-alike (`alts`); "
            f"{len(p.lab_key)} key labels: {bad_lab} wrong; one picture for several keys: "
            f"{out[rows]['labels_shared']}")
    return out


# ---- a capture --------------------------------------------------------------------------------------------------------
def run(cap: str, every: int = 1, audit: int = 499) -> None:
    """Every frame through SlotReader -> FrameFacts slots -> us.py's Slots, + the HUD's HP / MP (hud.HudText) ->
    cap_dir/reads.npz + events.json (the prototype's format, so its `report` reads them). Every `audit`-th frame and
    every frame with a slot event is also read from scratch and compared."""
    import frames as rec
    from maplebrain.perception import hud
    c = rec.clip(cap, False, "slots_gate")
    fr = c.frames()[::every]
    p = S.pack()
    rd = S.SlotReader(p)
    us = Slots()
    ht = hud.HudText()
    N, K = len(fr), len(p.cells)
    exact = np.zeros((N, K), bool)
    cls = np.full((N, K), -2, np.int32)
    amount = np.full((N, K), -1, np.int32)
    hp = np.full((N, 2), -1, np.int32)
    mp = np.full((N, 2), -1, np.int32)
    bar = np.ones(N, np.float32)
    whys, events = {}, []
    t_read = t_dec = 0.0
    n_audit = bad_audit = 0
    t0 = time.perf_counter()
    for i, (n, name, t) in enumerate(fr):
        a = time.perf_counter()
        img = rec.read(c.run, name)
        b = time.perf_counter()
        if img is None:
            raise SystemExit(f"{cap}: frame {name} unreadable")
        reads = rd.update(img)
        facts = rd.facts()
        e = time.perf_counter()
        ev = us.update(facts, float(t))
        t_dec += b - a
        t_read += e - b
        cell_of = {rd.key_of(k): k for k in range(K)}
        for x in ev:
            events.append({"t": round(float(t), 4), "n": int(n), "cell": cell_of.get(x["key"], -1), "key": x["key"],
                           "was": x["was"], "now": x["now"], "d": x["d"]})
        for k, r in enumerate(reads):
            exact[i, k] = r.exact
            if r.exact:
                cls[i, k] = r.cls
                amount[i, k] = -1 if r.amount is None else r.amount
            else:
                whys.setdefault((k, r.why), []).append(int(n))
        if not exact[i].all():
            bar[i] = p.bar_share(img)
        if i % audit == 0 or ev:
            n_audit += 1
            for k, r in enumerate(S.read_slots(img, p)):
                o = reads[k]
                if (r.key, r.amount, r.exact) != (o.key, o.amount, o.exact) or o.cls not in (r.cls,) + r.alts:
                    bad_audit += 1
                    print(f"  AUDIT frame {n} cell {k}: from scratch {r} != the reader's {o}")
        h, m, _ = ht.read(img)
        if h:
            hp[i] = h
        if m:
            mp[i] = m
        if i % 20000 == 0 and i:
            print(f"  {cap}: {i} / {N} frames, {time.perf_counter() - t0:.0f} s", flush=True)
    d = cap_dir(cap)
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "reads.npz", n=np.array([f[0] for f in fr]), t=np.array([f[2] for f in fr]), exact=exact,
                        cls=cls, amount=amount, hp=hp, mp=mp, bar=bar)
    info = {"cap": c.name, "map": c.map_id, "frames": N, "every": every, "cells": K,
            "labels": [None if li is None else p.lab_key[li] for li in rd.label],
            "events": events, "reads": rd.reads, "decode_s": round(t_dec, 1), "tracker_s": round(t_read, 3),
            "tracker_us_per_frame": round(1e6 * t_read / max(1, N), 2), "audit": [n_audit, bad_audit],
            "unreadable": [{"cell": k, "why": w, "frames": ns} for (k, w), ns in sorted(whys.items())],
            "state": us.state()}
    (d / "events.json").write_text(json.dumps(info), encoding="utf-8")
    print(f"{cap}: {N} frames; decode {t_dec:.0f} s, the reader {t_read:.2f} s = {1e6 * t_read / max(1, N):.1f} us a "
          f"frame ({rd.reads} cell reads); audit {n_audit} frames, {bad_audit} differences -> {d}")
    report(cap)


def report(cap: str) -> None:
    """The prototype's checks (proto_slots.report) on this code's reads: its pack swapped for the real one."""
    import proto_slots as P
    P.OUT = OUT
    P.Pack = lambda rows=2: S.pack(rows)
    P.report(cap)


# ---- the unreadable stretches ---------------------------------------------------------------------------------------
def stretches(caps: list, sheet_every: int = 1) -> None:
    """Per capture every run of frames with at least one unreadable cell: its frames, seconds, the cells and why, the
    bar's signature share (a fade lowers all of it), the reads on the frames just before / after. -> stretches.txt +
    sheets (stretches_NN.png: the middle frame of each stretch, the bar x4, what a from-scratch read says)."""
    lines, moments = [], []
    for cap in caps:
        d = cap_dir(cap)
        if not (d / "reads.npz").exists():
            lines.append(f"{cap}: not run")
            continue
        z = np.load(d / "reads.npz")
        info = json.loads((d / "events.json").read_text(encoding="utf-8"))
        n, t, ex, bar = z["n"], z["t"], z["exact"], z["bar"]
        bad = np.flatnonzero(~ex.all(axis=1))
        why_of = {}
        for u in info["unreadable"]:
            for f in u["frames"]:
                why_of.setdefault(f, set()).add((u["cell"], u["why"]))
        runs = []
        for i in bad:
            if runs and i == runs[-1][1] + 1:
                runs[-1][1] = i
            else:
                runs.append([i, i])
        lines.append(f"== {cap} ({info['map']}): {len(n)} frames, {len(bad)} with an unreadable cell in {len(runs)} "
                     f"stretches")
        for a, b in runs:
            cells = sorted({c for i in range(a, b + 1) for c, _ in why_of.get(int(n[i]), ())})
            whys = sorted({w for i in range(a, b + 1) for _, w in why_of.get(int(n[i]), ())})
            lines.append(f"   frames {int(n[a])}..{int(n[b])} ({b - a + 1} frames, t {t[a]:.2f}..{t[b]:.2f} s, "
                         f"{t[b] - t[a]:.2f} s): cells {cells}; bar signature min {100 * float(bar[a:b + 1].min()):.0f} "
                         f"%, max {100 * float(bar[a:b + 1].max()):.0f} %; {'; '.join(whys)}")
            moments.append(f"{cap}@{int(n[(a + b) // 2])}@{cap} frames {int(n[a])}..{int(n[b])}")
    text = "\n".join(lines)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stretches.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"{len(moments)} stretches")
    for j in range(0, len(moments), 12):
        sheet(OUT / f"stretches_{j // 12:02d}.png", moments[j:j + 12])


def sheet(out: Path, moments: list) -> Path:
    import proto_slots as P
    import cv2
    import frames as rec
    p = S.pack()
    rows = []
    for mo in moments:
        cap, n, *note = mo.split("@", 2)
        c = rec.clip(cap, False, "slots_gate")
        img = rec.read(c.run, rec.name_of(int(n)))
        if img is None:
            continue
        rows.append(P.sheet_row(p, img, f"{c.name}  frame {n}", note[0] if note else ""))
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack(rows))
    print(f"{len(rows)} moments -> {out}")
    return out


# ---- L7 -------------------------------------------------------------------------------------------------------------
def _said(p, key: str, r) -> str:
    """A Read as the labellers wrote it: "JUMP", "Pet Food 100", "empty", "The Green Relaxer"; "?" unreadable."""
    if r is None or r.kind is None:
        return "?"
    if r.kind == "empty":
        return "empty"
    nm = p.name(r.cls)
    return nm if r.amount is None else f"{nm} {r.amount}"


def _state_said(p, slot) -> str:
    """A tracked key (track/us.py Slot) as the labellers wrote it; "?" never read."""
    if slot is None:
        return "?"
    if slot.kind == "empty":
        return "empty"
    nm = p.info(slot.kind, slot.id).get("name") or f"{slot.kind} {slot.id}"
    return nm if slot.amount is None else f"{nm} {slot.amount}"


def _held(cap: str) -> tuple:
    """The full run's reads of a capture (`run`) -> (frame numbers, per cell its label, per frame and cell the last
    exact (cls, amount) at or before it: what track/us.py holds; cls -2 = never read)."""
    d = cap_dir(cap)
    z = np.load(d / "reads.npz")
    info = json.loads((d / "events.json").read_text(encoding="utf-8"))
    ex, cls, amt = z["exact"], z["cls"], z["amount"]
    N, K = ex.shape
    idx = np.where(ex, np.arange(N)[:, None], -1)
    np.maximum.accumulate(idx, axis=0, out=idx)
    hc = np.where(idx >= 0, np.take_along_axis(cls, np.maximum(idx, 0), 0), -2)
    ha = np.where(idx >= 0, np.take_along_axis(amt, np.maximum(idx, 0), 0), -1)
    return z["n"], info["labels"], hc, ha


def _state_said(p, cl: int, a: int) -> str:
    if cl == -2:
        return "?"
    if cl < 0:
        return "empty"
    return p.name(cl) + ("" if a < 0 else f" {a}")


def l7() -> None:
    """Each L7 frame: the reader on that frame alone (from scratch), and the state's slots on it - the last exact
    reading of each cell from the stay's start (the full `run` of the capture: what track/us.py holds), or, before
    the stay's first exact read, the stay before it in the session (a map change does not change the bar; hold-out
    stays are not opened). Per key-frame one of: `exact` (the frame read exactly, equal to the label), `held` (the
    frame not readable - a fade, the cursor, a window - and the state holds the label's reading), `WRONG` (an exact
    read or the state differs from the label), `never` (not readable, nothing read before it). A "?" label (the
    labeller could not read it) is listed with what the reader says."""
    import frames as rec
    from collections import Counter
    p = S.pack()
    cnt, by_class, per_frame = Counter(), Counter(), {}
    unsure, wrong = [], []
    labs = sorted((Path(os.environ.get("MAPLE_CORPUS") or CORPUS) / "labels").glob("*/labels/L7.json"))
    caps = all_caps()
    for lp in labs:
        cap = lp.parents[1].name
        doc = json.loads(lp.read_text(encoding="utf-8"))
        c = rec.clip(cap, False, "slots_gate")
        names = {int(n): nm for n, nm, _ in c.frames()}
        ns, labels, hc, ha = _held(cap)
        sess, k = cap.rsplit("#", 1)
        prev = f"{sess}#{int(k) - 1}" if f"{sess}#{int(k) - 1}" in caps else None    # (only the stay just before)
        pv = _held(prev) if prev else None
        for n, fr in sorted(doc["frames"].items(), key=lambda kv: int(kv[0])):
            n = int(n)
            img = rec.read(c.run, names[n])
            scratch = S.read_slots(img, p)
            i = int(np.searchsorted(ns, n))
            marks = []
            for cell, key in enumerate(labels):
                want = fr["slots"].get(key)
                if want is None:
                    continue
                got = _said(p, key, scratch[cell])
                cl, a = int(hc[i, cell]), int(ha[i, cell])
                if cl == -2 and pv is not None and key in pv[1]:
                    pc = pv[1].index(key)
                    cl, a = int(pv[2][-1, pc]), int(pv[3][-1, pc])
                st = _state_said(p, cl, a)
                if want == "?":
                    unsure.append(f"{cap} frame {n} {key}: label '?'; the frame '{got}', the state '{st}'")
                    what = "?"
                elif got == want and st == want:
                    what = "exact"
                elif got == "?" and st == want:
                    what = "held"
                elif got == "?" and st == "?":
                    what = "never"
                    wrong.append(f"{cap} frame {n} {key} ({fr.get('class')}): label '{want}', never read")
                else:
                    what = "WRONG"
                    wrong.append(f"{cap} frame {n} {key} ({fr.get('class')}): label '{want}', the frame '{got}', "
                                 f"the state '{st}'")
                cnt[what] += 1
                by_class[(fr.get("class"), what)] += 1
                marks.append(what)
            per_frame[(cap, n)] = Counter(marks)
    print(f"L7: {len(labs)} files, {len(per_frame)} frames, {sum(cnt.values())} key-frames: {dict(cnt)}")
    print("   by the case's class: " + ", ".join(f"{c} {w} {v}" for (c, w), v in sorted(by_class.items())))
    ok = [f for f, m in per_frame.items() if not (m["WRONG"] or m["never"])]
    print(f"   frames with every labelled key exact or held: {len(ok)} of {len(per_frame)}; with a WRONG key: "
          f"{sum(1 for m in per_frame.values() if m['WRONG'])}")
    for (cap, n), m in sorted(per_frame.items()):
        if m["held"] or m["never"] or m["WRONG"]:
            print(f"   {cap} frame {n}: {dict(m)}")
    for x in wrong:
        print("  " + x)
    for x in unsure:
        print("  ? " + x)


# ---- speed -----------------------------------------------------------------------------------------------------------
def bench(cap: str = "20261121_000219_2#0", n_frames: int = 3000, start: int = 0) -> dict:
    """CPU ms of the real reader: the pack's load + table, a full read of 8 cells from scratch, one changed cell, an
    unchanged frame, and `n_frames` consecutive frames of `cap` (SlotReader.update + facts, as the Perceiver calls
    it). Run with nothing else on the machine."""
    import frames as rec
    c = rec.clip(cap, False, "slots_gate")
    imgs = [rec.read(c.run, name) for _, name, _ in c.frames()[start:start + n_frames]]
    t0 = time.perf_counter()
    p = S.Pack()
    p.table(0)
    t_load = time.perf_counter() - t0
    f0 = imgs[0]
    S.read_slots(f0, p)
    reps = 500
    a = time.perf_counter()
    for _ in range(reps):
        S.read_slots(f0, p)
    full = (time.perf_counter() - a) / reps
    rd = S.SlotReader(p)
    rd.update(f0)
    a = time.perf_counter()
    for _ in range(5000):
        rd.update(f0)
        rd.facts()
    same = (time.perf_counter() - a) / 5000
    k = next((k for k in range(len(p.cells)) if rd.now[k].amount is not None), 0)
    x, y = p.cells[k]
    crop = f0[y:y + S.CELL, x:x + S.CELL]
    hint = S.Hint(rd.label[k], rd.cls[k])
    a = time.perf_counter()
    for _ in range(2000):
        p.read_cell(crop, k, hint)
    one = (time.perf_counter() - a) / 2000
    rd = S.SlotReader(p)
    per = []
    for im in imgs:
        a = time.perf_counter()
        rd.update(im)
        rd.facts()
        per.append(time.perf_counter() - a)
    per = np.array(per) * 1000
    r = {"load_ms": 1000 * t_load, "full_ms": 1000 * full, "one_cell_us": 1e6 * one, "unchanged_us": 1e6 * same,
         "seq_ms_mean": float(per.mean()), "seq_ms_p50": float(np.percentile(per, 50)),
         "seq_ms_p99": float(np.percentile(per, 99)), "seq_ms_max": float(per.max()), "frames": len(imgs),
         "cell_reads": rd.reads}
    print(f"the pack loaded + its lookup table: {r['load_ms']:.0f} ms (once, at the Perceiver's start)")
    print(f"a full read of {len(p.cells)} cells from scratch: {r['full_ms']:.3f} ms")
    print(f"one changed cell re-read (hints, digits, lookup, full verify): {r['one_cell_us']:.1f} us")
    print(f"an unchanged frame (update + facts): {r['unchanged_us']:.1f} us")
    print(f"{len(imgs)} consecutive frames of {cap} (update + facts): mean {r['seq_ms_mean']:.4f} ms, p50 "
          f"{r['seq_ms_p50']:.4f}, p99 {r['seq_ms_p99']:.4f}, max {r['seq_ms_max']:.3f} ms; {rd.reads} cell reads")
    return r


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    every = int(a[a.index("--every") + 1]) if "--every" in a else 1
    rest = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and a[i - 1] != "--every"]
    if a[0] == "selftest":
        selftest()
    elif a[0] == "run":
        for cap in (all_caps() if "--all" in a else rest):
            run(cap, every)
    elif a[0] == "report":
        for cap in rest:
            report(cap)
    elif a[0] == "stretches":
        stretches(rest or all_caps())
    elif a[0] == "l7":
        l7()
    elif a[0] == "bench":
        bench(*rest[:1])
    elif a[0] == "sheet":
        sheet(Path(rest[0]), rest[1:])
    else:
        raise SystemExit(f"unknown command {a[0]}")


if __name__ == "__main__":
    main()
