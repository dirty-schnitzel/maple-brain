"""PLAN-tracker step 5a: THE REAL HP METER READER AND THE TRACKER'S hp FROM THE RECORDINGS - maplebrain/perception/
meters.py over every frame of a capture (its video; the fit's mobs from the kept replay, as the Perceiver hands them),
then the mob tracker over the kept replay with those meters (replay_mobs.py run --meters), graded.

    python tools/perc/track/replay_meters.py read --sound [--jobs 8]   every frame -> the reader's meters + its ms
    python tools/perc/track/replay_meters.py hit [--sound] [--tag t5a] no meter on a mob we did not hit
    python tools/perc/track/replay_meters.py l9 [--tag t5a]            L9: found, tied to the right mob, the fill
    python tools/perc/track/replay_meters.py time CAP [--n 3000] [--runs 3] [--start 0]   the live Perceiver, reader on / off

`read` keeps CORPUS/work/track-plan/meter/read_<SESSION#K>.pkl: {"meters": {frame n: FrameFacts.meters}, "ms": [ms a
frame]}; `read_back(cap)` = its meters (replay_mobs.py run --meters reads them). The tracker's rows (with `hp`, `hp_t`):
CORPUS/work/track-plan/step3/<cap>_<tag>.pkl after `replay_mobs.py run --sound --meters --tag t5a`.
"""
import argparse
import json
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT))
import cache  # noqa: E402
import dump  # noqa: E402
import load  # noqa: E402

MWIN = {"q": (0.20, 0.80), "w": (0.20, 0.80), "e": (0.15, 0.65)}  # key-down -> a NEW meter (proto_meter.py `new`)
SKILLS = tuple(MWIN)
STEP3 = Path(r"F:\dev\maple-corpus\work\track-plan\step3")


def out_dir() -> Path:
    from maplebrain.config import CORPUS
    d = Path(CORPUS) / "work" / "track-plan" / "meter"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pct(v, ps=(50, 90, 99), nd=3) -> str:
    v = np.asarray(v, float)
    return "-" if not len(v) else " / ".join(f"{np.percentile(v, p):.{nd}f}" for p in ps)


# ------------------------------------------------------------------ read: the real reader on every frame
PART = 9000


def _read_part(job):
    cap, a, b = job
    import frames as fr
    from maplebrain.perception.meters import MeterReader
    from maplebrain.config import Perception
    p = Perception()
    rd = MeterReader(load.Map(load.map_of(cap)).mobs, p.meter_tol, p.meter_tie)
    rows = {r["n"]: r for r in dump.rows(cap)}
    run = load.run_path(cap)
    v = fr.video(run)
    shift = fr.xshift(run)
    out, ms = {}, []
    for i in range(a, min(b, len(v))):
        n = v.n[i]
        r = rows.get(n)
        if r is None or r["C"] is None or not (r["facts"].get("fit")):
            continue                                    # no camera / no fit mob: the Perceiver does not read
        f = v.frame(i)
        if f is None:
            continue
        if shift:
            f = fr.unshift(f, shift)
        m = rd.read(f, r["facts"]["fit"])
        ms.append(rd.ms)
        if m:
            out[n] = m
    return cap, a, out, ms


def cmd_read(caps, jobs):
    import frames as fr
    work = []
    for c in caps:
        n = len(fr.video(load.run_path(c)))
        work += [(c, a, a + PART) for a in range(0, n, PART)]
    parts = {c: [] for c in caps}
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        done = ProcessPoolExecutor(jobs).map(_read_part, work)
    else:
        done = map(_read_part, work)
    t0 = time.perf_counter()
    for cap, a, out, ms in done:
        parts[cap].append((a, out, ms))
        if len(parts[cap]) == sum(1 for w in work if w[0] == cap):
            meters, mss = {}, []
            for _, o, m in sorted(parts[cap], key=lambda x: x[0]):
                meters.update(o)
                mss += m
            (out_dir() / f"read_{cap}.pkl").write_bytes(pickle.dumps({"meters": meters, "ms": np.array(mss)}))
            print(f"{cap}: {len(mss)} frames read, {sum(len(v) for v in meters.values())} meters on {len(meters)} "
                  f"frames; ms p50 / p90 / p99 {pct(mss)} ({time.perf_counter() - t0:.0f} s)", flush=True)


def read_back(cap) -> dict:
    return pickle.loads((out_dir() / f"read_{cap}.pkl").read_bytes())["meters"]


# ------------------------------------------------------------------ which track a meter taught
class Run:
    """A capture's reader meters, kept replay rows (the fit) and the tracker's rows of `replay_mobs run --meters`."""

    def __init__(self, cap, tag="t5a"):
        self.cap = cap
        self.meters = read_back(cap)
        self.kept = {r["n"]: r for r in dump.rows(cap)}
        d = pickle.loads((STEP3 / f"{cap.replace('#', '_')}_{tag}.pkl").read_bytes())
        self.rows = {r["n"]: r for r in d["rows"]}
        self.stats = d["stats"]
        run = load.run_path(cap)
        self.keys = [(k["t"], k["key"]) for k in map(json.loads, open(run / "keys.jsonl", encoding="utf-8"))
                     if k.get("down") and k["key"] in SKILLS]

    def track_of(self, n, q):
        """The seen track whose sighting is fit mob q on frame n (its screen feet = the sighting's, a look-alike
        reading settled within 20 px up or down)."""
        fit = self.kept[n]["facts"].get("fit") or []
        if q >= len(fit) or n not in self.rows:
            return None
        fx, fy = fit[q]["feet"]
        best = None
        for m in self.rows[n]["mobs"]:
            if m["src"] != "acq":
                continue
            d = abs(m["sx"] - fx) + abs(m["sy"] - fy) / 4
            if abs(m["sx"] - fx) <= 3 and abs(m["sy"] - fy) <= 20 and (best is None or d < best[0]):
                best = (d, m)
        return None if best is None else best[1]

    def taught(self, n, meter):
        """The track this meter taught on frame n (its hp_t this frame, the meter's one sighting), else None."""
        if len(meter[4]) != 1 or meter[2] is None:
            return None
        m = self.track_of(n, meter[4][0])
        t = self.kept[n]["t"]
        return m if m is not None and m.get("hp_t") is not None and abs(m["hp_t"] - t) < 1e-6 else None

    def in_window(self, t) -> list:
        return [(k, round(t - kt, 3)) for kt, k in self.keys if MWIN[k][0] <= t - kt <= MWIN[k][1]]


# ------------------------------------------------------------------ hit: no meter on a mob we did not hit
def cmd_hit(caps, tag):
    """Per track the first frame a meter names its sighting: our key-down in a meter window before it? Then per meter
    the tracker's verdict (taught / not, why: its stats)."""
    tot, inw, out = 0, 0, []
    stats = Counter()
    for cap in caps:
        R = Run(cap, tag)
        stats.update({k: v for k, v in R.stats.items() if k.startswith("meter")})
        first = {}
        for n in sorted(R.meters):
            for m in R.meters[n]:
                if len(m[4]) != 1:
                    continue
                tr = R.track_of(n, m[4][0])
                if tr is not None and tr["id"] not in first:
                    first[tr["id"]] = (n, R.kept[n]["t"])
        for tid, (n, t) in first.items():
            tot += 1
            w = R.in_window(t)
            if w:
                inw += 1
            else:
                out.append((cap, tid, n, round(t, 3), [(k, round(t - kt, 2)) for kt, k in R.keys if 0 <= t - kt <= 1.5]))
    print(f"tracks a meter named: {tot}; its first meter in one of our skills' meter windows (MWIN): {inw}; "
          f"outside: {len(out)}")
    for o in out:
        print("   OUTSIDE:", o)
    print(f"the tracker on the meters: {dict(stats)}")
    (out_dir() / "hit_outside.json").write_text(json.dumps(out), encoding="utf-8")


# ------------------------------------------------------------------ l9: the gate's label rows
L9_DIR = Path(r"F:\dev\maple-corpus\work\track-plan\labels\L9")
JUDGED = HERE / "judged"


def judged(which="a") -> dict:
    out = {}
    for p in sorted(JUDGED.glob(f"L9_{which}*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                out[int(j["case"])] = j
    return out


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def label_box(case, lab):
    """A labelled meter's box left x (screen px) from its band strip's ruler: L = box column 1, R = box column 50."""
    info = next((m for m in case["mobs"] if m["letter"] == lab.get("mob")), None)
    if info is None or lab.get("band") is False:
        return None, info
    bx = info["band"][0]
    if num(lab.get("L")) is not None:
        return bx + int(num(lab["L"])) - 1, info
    if num(lab.get("R")) is not None:
        return bx + int(num(lab["R"])) - 50, info
    return None, info


def cmd_l9(tag):
    cases = json.loads((L9_DIR / "cases.json").read_text(encoding="utf-8"))
    J = judged("a")
    runs, rep = {}, Counter()
    byfill = {"read": Counter(), "unread": Counter()}             # the found meters over a lettered mob, by fill
    guard = []                                                     # refused by the overlap guard (try 2: unseen only)
    fills, rows_out, frame_found = [], [], []
    for k, case in enumerate(cases):
        j = J.get(k)
        if j is None:
            rep["case not judged"] += 1
            continue
        labs = j.get("meters") or []
        if not labs:
            rep["frames with no meter by eye"] += 1
            continue
        rep["frames with a meter by eye"] += 1
        cap, n = case["cap"], case["n"]
        R = runs.get(cap) or runs.setdefault(cap, Run(cap, tag))
        got = list(R.meters.get(n, []))
        all_found = True
        for lab in labs:
            rep["meters by eye"] += 1
            x0, info = label_box(case, lab)
            # the reader's meter for it: in the letter's band (and at the ruler's x when read)
            cand = []
            for g in got:
                if info is not None:
                    bx, by = info["band"]
                    if not (bx - 4 <= g[0] <= bx + 26 and by - 6 <= g[1] <= by + 12):
                        continue
                    if x0 is not None and abs(g[0] - x0) > 2:
                        continue
                    cand.append(g)
            if info is None:
                rep["meters by eye over no lettered mob (" + str(lab.get("mob")) + ")"] += 1
            if not cand:
                if info is not None:
                    rep["  not found"] += 1
                    all_found = False
                    rows_out.append(("not found", k, cap, n, lab))
                continue
            g = cand[0]
            rep["  found"] += 1
            lf, gf = num(lab.get("fill")), g[2]
            if lf is not None and gf is not None:
                fills.append(abs(100 * gf - lf))
                if abs(100 * gf - lf) > 3:
                    rows_out.append(("fill off", k, cap, n, lab, gf))
            elif lf is not None:
                rep["  fill: the eye read it, the reader not"] += 1
            elif gf is not None:
                rep["  fill: the reader read it, the eye not"] += 1
            if lab.get("mob") in (None, "?", "none"):
                continue
            want = info["track"]
            if len(g[4]) == 1:                  # for the user's decision: perception's one candidate alone
                ct = R.track_of(n, g[4][0])
                rep["  cand alone: " + ("right" if ct is not None and ct["id"] == want else "WRONG" if ct is not None
                                        else "its sighting has no track")] += 1
            else:
                rep["  cand alone: " + ("none" if not g[4] else "two")] += 1
            tt = R.taught(n, g)
            fr_ = "read" if g[2] is not None else "unread"          # try 2's gate: the meters whose fill was read
            if tt is None:
                rep["  mob: not tied (taught no track)"] += 1
                why = ("no mob's expected box within the tie" if not g[4] else "two mobs' expected boxes" if
                       len(g[4]) > 1 else "fill not read" if g[2] is None else
                       "its sighting has no track" if R.track_of(n, g[4][0]) is None else
                       "an unseen track can be under it (the overlap guard)")
                rep["    not tied: " + why] += 1
                byfill[fr_]["not tied: " + why] += 1
                if why.startswith("an unseen track"):
                    guard.append((k, cap, n, g, R.track_of(n, g[4][0]), want, lab.get("fill")))
            elif tt["id"] == want:
                rep["  mob: tied right"] += 1
                byfill[fr_]["tied right"] += 1
            else:
                rep["  mob: tied WRONG"] += 1
                byfill[fr_]["tied WRONG"] += 1
                rows_out.append(("tied wrong", k, cap, n, lab, tt["id"], want))
        frame_found.append(all_found)
    for key in sorted(rep):
        print(f"  {key}: {rep[key]}")
    if frame_found:
        print(f"  frames whose every meter by eye was found: {sum(frame_found)} of {len(frame_found)} "
              f"({100 * sum(frame_found) / len(frame_found):.1f} %)")
    if fills:
        f = np.array(fills)
        print(f"  fill |reader - eye| (points): within 3: {(f <= 3).sum()} of {len(f)} ({100 * (f <= 3).mean():.1f} %); "
              f"p50 / p90 / max {pct(f, (50, 90, 100), 1)}")
    tr = rep["  mob: tied right"]
    tw = rep["  mob: tied WRONG"]
    nt = rep["  mob: not tied (taught no track)"]
    if tr + tw + nt:
        print(f"  tied to the right mob: {tr} of {tr + tw + nt} ({100 * tr / (tr + tw + nt):.1f} %); wrong {tw}, not "
              f"tied {nt}")
    for fr_, c in byfill.items():                 # step 5a, try 2: graded on the meters whose fill the reader read
        tot = sum(c.values())
        if tot:
            print(f"  fill {fr_}: {tot} meters over a lettered mob - tied right {c['tied right']} "
                  f"({100 * c['tied right'] / tot:.1f} %), wrong {c['tied WRONG']}; "
                  + ", ".join(f"{k} {v}" for k, v in sorted(c.items()) if k.startswith("not tied")))
    for r in rows_out:
        print("   ", r)
    if guard:
        guard_report(guard, runs, tag)


def blockers(R, n, tr, same_dy=40.0) -> list:
    """The tracks NOT seen on frame n (not dying) that the tracker's overlap guard finds under the seen track `tr` (its
    rows: a remembered one's `can` range, else its x; half body widths from the first stand / move / fly frame)."""
    out = []
    for u in R.rows[n]["mobs"]:
        if u["id"] == tr["id"] or u["src"] == "acq" or u["state"] == "dying" or abs(u["y"] - tr["y"]) > same_dy:
            continue
        hw, hwt = half_w(R, u["mob"]), half_w(R, tr["mob"])
        lo, hi = (u["can"][0] - hw, u["can"][1] + hw) if u.get("can") else (u["x"] - hw, u["x"] + hw)
        if lo <= tr["x"] + hwt and hi >= tr["x"] - hwt:
            out.append(u)
    return out


def half_w(R, mob) -> float:
    if not hasattr(R, "_hw"):
        R._hw = {}
    if mob not in R._hw:
        fr = (load.Map(load.map_of(R.cap)).mobs.get(mob) or {}).get("frames") or {}
        f = next((fr[a][0] for a in ("stand", "move", "fly") if fr.get(a) and fr[a][0].get("lt")), None)
        R._hw[mob] = 0.0 if f is None else (f["rb"][0] - f["lt"][0]) / 2
    return R._hw[mob]


def guard_report(guard, runs, tag):
    """Try 2: L9's meters the overlap guard refused - per case the seen track, the unseen tracks under it (state,
    cover, s unseen, dx from the seen track, its possible range); and a picture sheet of exactly these cases."""
    import cv2
    import proto_meter as PM
    print(f"\n  REFUSED BY THE GUARD (an unseen track can be under the mob): {len(guard)}")
    kinds = Counter()
    tiles = []
    for k, cap, n, g, tr, want, lf in guard:
        R = runs[cap]
        bl = blockers(R, n, tr)
        desc = [(u["id"], u["state"], u["cover"], u["unseen"], round(u["x"] - tr["x"]), round(u["y"] - tr["y"]),
                 u.get("can")) for u in bl]
        kinds.update(f"{u['state']} / {u['cover']}" for u in bl)
        print(f"    case {k} {cap} n {n}: meter fill {g[2]:.2f} (eye {lf}) over track {tr['id']} (= L9's {want}); "
              f"under it: {desc}")
        img = PM.read_frame(cap, n)
        marks = [(tr["sx"], tr["sy"], f"{tr['id']} seen", (255, 255, 0))]
        C = R.kept[n]["C"]
        for u in bl:
            marks.append((u["sx"], u["sy"], f"{u['id']} {u['state']} {u['unseen']}s", (0, 128, 255)))
        t = PM.tile(img, g[0] + 26, g[1] + 45, 260, 150, 3, marks,
                    f"case {k} n{n}: fill {g[2]:.2f}; guard: {len(bl)} unseen")
        for u in bl:                                    # its possible range (map x) as a line at its feet
            if u.get("can") and C is not None:
                ox, oy = g[0] + 26 - 130, g[1] + 45 - 75
                a, b = int((u["can"][0] - C[0] - ox) * 3), int((u["can"][1] - C[0] - ox) * 3)
                y = int((u["sy"] - oy) * 3) + 22
                cv2.line(t, (a, y), (b, y), (0, 128, 255), 2)
        tiles.append(t)
    print(f"    the unseen tracks under them, by state / cover: {dict(kinds)}")
    for i in range(0, len(tiles), 12):
        p = out_dir() / f"sheet_guard_{tag}_{i // 12}.png"
        cv2.imwrite(str(p), PM.grid(tiles[i:i + 12], 3))
        print(f"    sheet: {p}")


# ------------------------------------------------------------------ time: the live Perceiver
def cmd_time(cap, n, runs, start=0):
    """The live Perceiver over n frames of the capture (its video) from frame index `start`, the meter reader ON and
    OFF in turn: the reader's own ms (FrameFacts.meters_ms; the part `meters` is rounded to 0.1 ms) and the whole
    frame's observe ms."""
    sys.path.insert(0, str(ROOT / "tools" / "perc"))
    sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
    import frames as rec
    import run as replay
    from maplebrain.procperf import prefer_performance
    print(prefer_performance())
    c = dump.clip_of(cap)
    fr = c.frames(0.0, 1e9)[start:start + n]
    imgs = [(rec.read(c.run, name), t) for _, name, t in fr]
    res = {"on": [], "off": []}
    for k in range(2 * runs):
        mode = "on" if k % 2 == 0 else "off"
        per = replay.bench_module().build(c.map_id)[0]
        if mode == "off":
            per.meters = None
        ob, mt, nm = [], [], []
        for j, (img, t) in enumerate(imgs):
            a = time.perf_counter()
            per.observe(img, t)
            if j >= 30:
                ob.append(1000 * (time.perf_counter() - a))
                mt.append(per.facts.meters_ms or 0.0)
                nm.append(len(per.facts.meters or []))
        res[mode].append((np.array(ob), np.array(mt), np.array(nm)))
        print(f"run {k + 1} meters {mode}: observe p50 / p90 {pct(ob, (50, 90), 2)} ms; the reader's ms p50 / p90 / p99 "
              f"{pct(mt, (50, 90, 99), 3)}; frames with a meter {int((np.array(nm) > 0).sum())}", flush=True)
        del per
    on = np.concatenate([x[0] for x in res["on"]])
    off = np.concatenate([x[0] for x in res["off"]])
    mt = np.concatenate([x[1] for x in res["on"]])
    print(f"ALL: the reader's ms p50 {np.median(mt):.3f} (<= 0.1) / p90 {np.percentile(mt, 90):.3f} / p99 "
          f"{np.percentile(mt, 99):.3f} / max {mt.max():.3f}; observe p50 on {np.median(on):.2f} / off {np.median(off):.2f}"
          f" ms ({np.median(on) - np.median(off):+.2f}; more than 1 ms added: stop)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--tag", default="t5a")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--start", type=int, default=0, help="time: the first frame (video index)")
    a = ap.parse_args()
    caps = list(cache.SOUND) if a.sound or not a.caps else a.caps
    if a.cmd == "read":
        cmd_read(caps, a.jobs)
    elif a.cmd == "hit":
        cmd_hit(caps, a.tag)
    elif a.cmd == "l9":
        cmd_l9(a.tag)
    elif a.cmd == "time":
        cmd_time(a.caps[0], a.n, a.runs, a.start)
    else:
        raise SystemExit(f"unknown command {a.cmd}")


if __name__ == "__main__":
    main()
