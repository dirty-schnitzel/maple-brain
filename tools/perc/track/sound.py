"""Tracker plan, step 2's check (PLAN-data.md section 6 item 1): is perception sound on a capture? From the kept
replay (dump.py) only, no GPU.

    python tools/perc/track/sound.py CAP [CAP ...] [--every K] [--json OUT]

Per capture:
  camera     the share of frames with the scene camera found (the scene model registered on the frame)
  explained  the share of the known scenery's pixels (`world`: scenery the scene model draws, no UI, no front layer)
             where the frame IS the expected scene (`shows`), two ways:
               raw      over every world pixel - things drawn in front of the scenery (mobs, players, us, drops, the
                        chat window when open, skill effects, damage numbers) count as unexplained
               scenery  the same with the boxes of what perception knows is in front taken out first: the fit's mobs
                        and today's tracks (their sprite's box at their pose, both facings), us (around our name tag),
                        other players (around their tags), drops (their box), each grown by GROW px. What is left
                        unexplained is the scene model's own miss, or something nobody tracks (effects, numbers, the
                        open chat). All pixels of the sampled frames pooled.
               model    THE VERDICT'S: the scene model's own miss = map places (CELL x CELL px of the map) that are
                        unexplained on more than half of the sampled frames that show them (and are shown on >= 10):
                        what moves over the scenery (mobs, players, effects, the chat window as the camera moves)
                        is unexplained only now and then; a place the model draws wrong is unexplained nearly
                        always. explained = 1 - (unexplained pixels in such places) / (all world pixels). The per
                        place counts are kept in OUT/track/sound_cells.npz (U, W, F, origin, CELL).
  tracked    confirmed tracks of today's tracker on screen per frame (p50 / max) and distinct track ids
  ms         the Perceiver's observe call per frame, p50 / p90 (on this machine, at replay time)
  lead, fade the camera-less frames at the capture's start until the first fix (after a portal the map is on screen
             ~1 s before our character is drawn, and the camera's seed needs our tag) and at its end when <= FADE_S
             (the exit fade: the screen goes black). `lost_all` = every camera-less frame (the rule read literally).
Verdict (PLAN-data's stop rules as a verdict, not a stop): camera lost on > 1 % of the frames from the first fix to
the exit fade, or the `model` share < 95 % -> "not sound" (left out of the tracker's scoring). `literal` = the same
verdict with every frame counted.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump import PLAY_H, SW, bits, bits_rows, meta, rows      # noqa: E402
from load import ASSETS, name_of                         # noqa: E402

GROW = 6
CELL = 4                  # px of a map place (the `model` share)
MIN_F = 10                # sampled frames a place must be shown on to be judged
FADE_S = 0.5              # a camera-less run this long at the capture's end = the exit fade
BODY = (45, 100)          # a character's box around its name tag: +-45 px from the tag's centre, 100 px above it


class Boxes:
    def __init__(self):
        self.mobs = {}

    def half_w_h(self, typ, pose):
        """(left reach, right reach, top, bottom) of the sprite at `pose` around its feet, both facings."""
        key = (typ, pose)
        if key not in self.mobs:
            d = json.loads((ASSETS / "mobs" / str(typ) / "mob.json").read_text(encoding="utf-8"))
            anim, _, k = (pose or "stand_0").rpartition("_")
            fr = (d.get("frames") or {}).get(anim) or (d.get("frames") or {}).get("stand") or \
                next(iter((d.get("frames") or {}).values()), [{}])
            f = fr[min(int(k) if k.isdigit() else 0, len(fr) - 1)] if fr else {}
            (w, h), (ox, oy) = f.get("size") or (80, 80), f.get("origin") or (40, 80)
            r = max(ox, w - ox)
            self.mobs[key] = (r, r, oy, h - oy)
        return self.mobs[key]

    def mask(self, row) -> np.ndarray:
        m = np.zeros((PLAY_H, SW), bool)
        f = row["facts"]

        def put(x0, y0, x1, y1):
            x0, y0 = max(0, int(x0) - GROW), max(0, int(y0) - GROW)
            x1, y1 = min(SW, int(x1) + GROW), min(PLAY_H, int(y1) + GROW)
            if x1 > x0 and y1 > y0:
                m[y0:y1, x0:x1] = True

        for fm in f.get("fit") or []:
            l, r, t, b = self.half_w_h(fm["type"], fm["pose"])
            put(fm["feet"][0] - l, fm["feet"][1] - t, fm["feet"][0] + r, fm["feet"][1] + b)
        for tr in row["mobs"] or []:
            pose = f"{tr.get('anim') or 'stand'}_0"
            l, r, t, b = self.half_w_h(tr["mob"], pose)
            put(tr["sx"] - l, tr["sy"] - t, tr["sx"] + r, tr["sy"] + b)
        tops = [(x + w / 2, y, h) for x, y, w, h in [t[:4] for t in f.get("tags") or []]]
        if row["me"]:                                   # our tag: (centre x, top y)
            tops.append((row["me"][0], row["me"][1], 18))
        for cx, y, h in tops:
            put(cx - BODY[0], y - BODY[1], cx + BODY[0], y + h)
        for d in f.get("drops") or []:
            x, y, w, h = d["box"]
            put(x, y, x + w, y + h)
        return m


def check(cap, every: int = 3) -> dict:
    rs = rows(cap)
    mt = meta(cap)
    n = len(rs)
    cam = sum(r["C"] is not None for r in rs)
    lead = next((i for i, r in enumerate(rs) if r["C"] is not None), n)
    tail = next((i for i, r in enumerate(reversed(rs)) if r["C"] is not None), n)
    fade = tail if tail and rs[-1]["t"] - rs[n - tail]["t"] <= FADE_S else 0
    body = max(1, n - lead - fade)
    lost_body = body - (cam if n - lead - fade > 0 else body)
    raw = [r["explained"] for r in rs if r["explained"] is not None]
    bx = Boxes()
    sv = wv = 0
    per_frame = []
    by_n = {r["n"]: r for r in rs[::every]}
    Cs = np.array([r["C"] for r in rs if r["C"] is not None])
    hb, wb = PLAY_H // CELL, SW // CELL
    ox, oy = int(Cs[:, 0].min()) // CELL - 1, int(Cs[:, 1].min()) // CELL - 1
    gw = int(Cs[:, 0].max()) // CELL - ox + wb + 2
    gh = int(Cs[:, 1].max()) // CELL - oy + hb + 2
    U, W, F = (np.zeros(gh * gw, np.int64) for _ in range(3))
    by, bxx = np.mgrid[0:hb, 0:wb]
    for nn, s, w in bits_rows(cap, packed=True):
        r = by_n.get(nn)
        if r is None or s is None:
            continue
        s, w = bits(s), bits(w)
        keep = w & ~bx.mask(r)
        a, b = int((s & keep).sum()), int(keep.sum())
        sv, wv = sv + a, wv + b
        per_frame.append(a / max(1, b))
        ws = w[:hb * CELL, :wb * CELL].reshape(hb, CELL, wb, CELL).sum((1, 3))
        us = (w & ~s)[:hb * CELL, :wb * CELL].reshape(hb, CELL, wb, CELL).sum((1, 3))
        idx = ((by + r["C"][1] // CELL - oy) * gw + (bxx + r["C"][0] // CELL - ox)).ravel()
        W += np.bincount(idx, ws.ravel(), gh * gw).astype(np.int64)
        U += np.bincount(idx, us.ravel(), gh * gw).astype(np.int64)
        F += np.bincount(idx, (ws > 0).ravel(), gh * gw).astype(np.int64)
    miss = (F >= MIN_F) & (U > 0.5 * W)
    model = 1 - U[miss].sum() / max(1, W.sum())
    from load import out_path
    np.savez_compressed(out_path(cap) / "track" / "sound_cells.npz", U=U.reshape(gh, gw), W=W.reshape(gh, gw),
                        F=F.reshape(gh, gw), origin=np.array([ox * CELL, oy * CELL]), CELL=CELL)
    conf = [sum(1 for m in r["mobs"] if m["state"] != "tentative" and 0 <= m["sx"] < SW and 0 <= m["sy"] < PLAY_H)
            for r in rs]
    ids = {m["id"] for r in rs for m in r["mobs"] if m["state"] != "tentative"}
    ms = [r["ms"]["observe"] for r in rs[30:]]
    out = {"cap": name_of(cap), "map": mt["map"], "frames": n, "seconds": round(rs[-1]["t"] - rs[0]["t"], 1),
           "camera": 1 - lost_body / body, "lost": lost_body, "lead": lead, "fade": fade, "lost_all": n - cam,
           "lead_s": round(rs[min(lead, n - 1)]["t"] - rs[0]["t"], 2),
           "raw": float(np.mean(raw)) if raw else 0.0, "raw_p10": float(np.percentile(raw, 10)) if raw else 0.0,
           "scenery": sv / max(1, wv), "scenery_p10": float(np.percentile(per_frame, 10)) if per_frame else 0.0,
           "scenery_frames": len(per_frame), "model": float(model), "miss_px": int(miss.sum()) * CELL * CELL,
           "tracked_p50": float(np.median(conf)), "tracked_max": int(max(conf)), "ids": len(ids),
           "ms_p50": float(np.percentile(ms, 50)), "ms_p90": float(np.percentile(ms, 90)),
           "observe_s": mt["observe_s"], "bytes": mt["bytes"]}
    why = []
    if 1 - out["camera"] > 0.01:
        why.append(f"camera lost on {100 * (1 - out['camera']):.1f} % of the frames")
    if out["model"] < 0.95:
        why.append(f"{100 * out['model']:.1f} % of the scenery explained by the model")
    out["verdict"] = "not sound: " + "; ".join(why) if why else "sound"
    lit = (n - cam) / n > 0.01 or out["model"] < 0.95
    out["literal"] = "not sound" if lit else "sound"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    res = []
    for cap in a.caps:
        o = check(cap, a.every)
        res.append(o)
        print(f"{o['cap']:22s} {o['map']} {o['frames']:7d} fr  camera {100 * o['camera']:6.2f} % (lead {o['lead']} fade {o['fade']} all lost {o['lost_all']})  raw "
              f"{100 * o['raw']:5.1f} % (p10 {100 * o['raw_p10']:5.1f})  scenery {100 * o['scenery']:5.1f} % (p10 "
              f"{100 * o['scenery_p10']:5.1f})  model {100 * o['model']:5.1f} %  tracked p50 {o['tracked_p50']:.0f} max {o['tracked_max']} ids {o['ids']}"
              f"  ms {o['ms_p50']:.1f}/{o['ms_p90']:.1f}  -> {o['verdict']} (literal: {o['literal']})", flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
