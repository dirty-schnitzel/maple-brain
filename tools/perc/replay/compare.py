"""Compare two tracker replays of one run (run.py), or a replay with what the live run tracked.

    python tools/perc/replay/compare.py RUN A B          # RUN/replay/A.jsonl (old / reference) vs RUN/replay/B.jsonl
    python tools/perc/replay/compare.py RUN --live B     # the live run's own tracks (ticks.jsonl) vs a replay
    python tools/perc/replay/compare.py RUN A B [--tol 20] [--list 10] [--json]

Words: a CONFIRMED track left "tentative" at least once; REAL = its best score >= 0.80 (tools/combat/probe/tracks.py:
"strong"), WEAK = never that good (scenery, our body, a dying mob's spot: HANDOFF "weak tracks"). A track-frame is
one confirmed track on one frame, not offscreen; it is FOUND in the other replay when a confirmed track of the same
mob type has its screen feet within --tol px there. Ids are not compared (they shift when one tentative differs).
"The same tracks" on a frame = equal ids, states, poses, positions within 1 px and scores within 0.01: the GPU's
run-to-run noise (two replays of the SAME code differ by scores <= 0.005 on up to half the frames, rarely 1 px).
"Same or better" for a change: no real track-frames lost, weak ones equal or fewer; a change that must not touch the
tracks: the same tracks on 100 % of the frames.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

REAL = 0.80


def load(path: Path) -> list:
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def live_rows(run: Path) -> list:
    out = []
    for l in open(run / "ticks.jsonl", encoding="utf-8"):
        k = json.loads(l)
        if k.get("frame"):
            o = k["obs"]
            out.append({"n": k["n"], "frame": k["frame"], "t": o["t"], "cam": o.get("cam"), "me": o.get("me"),
                        "me_map": o.get("me_map"), "mobs": o.get("mobs") or []})
    return out


def tracks(rows: list) -> dict:
    """id -> {mob, best, frames (confirmed, on screen), seen (of those: sighted that frame), t0, t1, real}."""
    out = {}
    for r in rows:
        for m in r["mobs"]:
            if m["state"] == "tentative":
                continue
            d = out.setdefault(m["id"], {"mob": m["mob"], "best": 0.0, "frames": 0, "seen": 0, "t0": r["t"], "t1": r["t"]})
            d["best"] = max(d["best"], m.get("score") or 0.0)
            d["t1"] = r["t"]
            if m["state"] != "offscreen":
                d["frames"] += 1
                d["seen"] += m.get("src", "none") != "none"
    for d in out.values():
        d["real"] = d["best"] >= REAL
    return out


def summary(rows: list) -> dict:
    tr = tracks(rows)
    real = [d for d in tr.values() if d["real"]]
    weak = [d for d in tr.values() if not d["real"]]
    return {"frames": len(rows), "confirmed": len(tr), "real": len(real), "weak": len(weak),
            "real_frames": sum(d["frames"] for d in real), "weak_frames": sum(d["frames"] for d in weak),
            "seen_share": round(sum(d["seen"] for d in real) / max(1, sum(d["frames"] for d in real)), 3)}


def found(a_rows: list, b_rows: list, tol: float) -> dict:
    """Track-frames of A found in B, by A's track class; per A track: frames, found."""
    b_by = {r["n"]: r for r in b_rows}
    cls = tracks(a_rows)
    per = defaultdict(lambda: [0, 0])
    tot = {"real": [0, 0], "weak": [0, 0]}
    for r in a_rows:
        b = b_by.get(r["n"])
        if b is None:
            continue
        pool = [m for m in b["mobs"] if m["state"] not in ("tentative", "offscreen")]
        for m in r["mobs"]:
            if m["state"] in ("tentative", "offscreen"):
                continue
            hit = any(p["mob"] == m["mob"] and abs(p["sx"] - m["sx"]) <= tol and abs(p["sy"] - m["sy"]) <= tol
                      for p in pool)
            k = "real" if cls[m["id"]]["real"] else "weak"
            tot[k][0] += 1
            tot[k][1] += hit
            per[m["id"]][0] += 1
            per[m["id"]][1] += hit
    return {"total": tot, "per": {i: (n, h, cls[i]) for i, (n, h) in per.items()}}


def camera(a_rows: list, b_rows: list) -> dict:
    b_by = {r["n"]: r for r in b_rows}
    d = sorted(max(abs(r["cam"][0] - b_by[r["n"]]["cam"][0]), abs(r["cam"][1] - b_by[r["n"]]["cam"][1]))
               for r in a_rows if r.get("cam") and b_by.get(r["n"], {}).get("cam"))
    if not d:
        return {}
    return {"n": len(d), "p50": round(d[len(d) // 2], 1), "p95": round(d[int(0.95 * (len(d) - 1))], 1), "max": round(d[-1], 1)}


def _alike(ma: list, mb: list, px: float = 1.0, score: float = 0.01) -> bool:
    """The same tracks up to the GPU's run-to-run noise (measured: scores +-0.005, a position 1 px, about once in
    5000 track-frames): ids, mob, state, pose, source equal; position within `px`, score within `score`."""
    if len(ma) != len(mb):
        return False
    for m, n in zip(ma, mb):
        if any(m[k] != n[k] for k in ("id", "mob", "state", "anim", "facing", "src", "platform")):
            return False
        if abs(m["sx"] - n["sx"]) > px or abs(m["sy"] - n["sy"]) > px or abs((m["score"] or 0) - (n["score"] or 0)) > score:
            return False
    return True


def compare(a_rows: list, b_rows: list, tol: float = 20.0) -> dict:
    common = {r["n"] for r in a_rows} & {r["n"] for r in b_rows}
    a_rows = [r for r in a_rows if r["n"] in common]
    b_rows = [r for r in b_rows if r["n"] in common]
    b_by = {r["n"]: r for r in b_rows}
    same = sum(r["mobs"] == b_by[r["n"]]["mobs"] for r in a_rows)
    alike = sum(_alike(r["mobs"], b_by[r["n"]]["mobs"]) for r in a_rows)
    return {"frames": len(common), "identical_frames": same, "same_frames": alike, "a": summary(a_rows),
            "b": summary(b_rows),
            "a_in_b": found(a_rows, b_rows, tol), "b_in_a": found(b_rows, a_rows, tol), "camera": camera(a_rows, b_rows)}


def _share(p):
    return f"{p[1]}/{p[0]} ({100 * p[1] / max(1, p[0]):.1f} %)"


def report(c: dict, na: str, nb: str, n_list: int = 10) -> str:
    L = [f"{c['frames']} common frames: the same tracks on {c['same_frames']} "
         f"({100 * c['same_frames'] / max(1, c['frames']):.1f} %; up to GPU noise: score 0.01, 1 px), "
         f"identical to the digit on {c['identical_frames']}"]
    for name, s in ((na, c["a"]), (nb, c["b"])):
        L.append(f"  {name:>10}: confirmed tracks {s['confirmed']} = real {s['real']} + weak {s['weak']}; track-frames "
                 f"real {s['real_frames']} (sighted {100 * s['seen_share']:.1f} %), weak {s['weak_frames']}")
    for src, dst, key in ((na, nb, "a_in_b"), (nb, na, "b_in_a")):
        t = c[key]["total"]
        L.append(f"  {src} track-frames found in {dst}: real {_share(t['real'])}, weak {_share(t['weak'])}")
    if c["camera"]:
        cam = c["camera"]
        L.append(f"  camera difference px: p50 {cam['p50']}, p95 {cam['p95']}, max {cam['max']} ({cam['n']} frames)")
    for src, dst, key in ((na, nb, "a_in_b"), (nb, na, "b_in_a")):
        worst = sorted(((n - h, i, n, d) for i, (n, h, d) in c[key]["per"].items() if d["real"] and n - h >= 3),
                       reverse=True)[:n_list]
        if worst:
            L.append(f"  real tracks of {src} missing in {dst} on >= 3 frames:")
            L += [f"    #{i} mob {d['mob']} best {d['best']:.2f} t {d['t0']:.1f}-{d['t1']:.1f}: {miss} of {n} frames"
                  for miss, i, n, d in worst]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("names", nargs="+", help="A B (files in RUN/replay/), or just B with --live")
    ap.add_argument("--live", action="store_true", help="A = the live run's tracks from ticks.jsonl")
    ap.add_argument("--tol", type=float, default=20.0)
    ap.add_argument("--t1", type=float, default=1e9, help="ignore frames after this run time")
    ap.add_argument("--list", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.live:
        na, nb = "live", a.names[0]
        ra = live_rows(a.run)
    else:
        na, nb = a.names
        ra = load(a.run / "replay" / f"{na}.jsonl")
    rb = load(a.run / "replay" / f"{nb}.jsonl")
    ra, rb = [r for r in ra if r["t"] <= a.t1], [r for r in rb if r["t"] <= a.t1]
    c = compare(ra, rb, a.tol)
    if a.json:
        c["a_in_b"].pop("per"), c["b_in_a"].pop("per")
        print(json.dumps(c))
    else:
        print(f"{a.run}: {na} vs {nb}")
        print(report(c, na, nb, a.list))


if __name__ == "__main__":
    main()
