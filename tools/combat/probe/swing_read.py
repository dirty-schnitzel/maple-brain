"""Read a swing_live.py recording: our pose per captured frame -> per-trial timelines and the answers.

    python tools/combat/probe/swing_read.py runs/probe/swing1 [--sheets]

Per frame (crop around us, our tag found in it):
    stand R / stand L   close to a standing reference (the `face` rests, plus their mirror images: Maple mirrors
                        sprites, so a right-facing stand flipped = a left-facing stand)
    act                 anything else (swing, walk); its facing = nearest frame of a known-facing swing or its mirror
    pose change         the body patch differs from the previous frame by more than CHANGE: a stance frame boundary.
                        A swing is a few held poses (client: 300/150/350 ms x weapon speed), so the gaps between
                        changes give the real frame delays.
Timeline chars: `.` stand R, `,` stand L, `R`/`L` acting facing right/left, `|` a pose change, `v`/`^` key down/up.
--sheets writes OUT/sheet_<trial>.png (every 2nd frame, time + state on each tile) to check the reading by eye.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from maplebrain.perception.selfpos import _hp, _match  # noqa: E402

PW, PUP, PDN = 150, 160, 0               # pose patch: tag centre +-PW, PUP above the tag top .. PDN below
DS = 3                                    # downsample for distances (blurred first: a px of tag jitter doesn't count)
SHIFT = 0                                 # +- px (downsampled) search when comparing patches
CHANGE = None                             # pose-change threshold: set from the data (stand jitter p99 x 3)


def load(run: Path):
    z = np.load(run / "crops.npz", allow_pickle=True)
    ev = json.loads((run / "events.json").read_text())
    imgs = [cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) for b in z["jpg"]]
    return np.asarray(z["t"]), imgs, ev


def locate(imgs):
    """Tag (x, y, w, h) per crop, None where not found."""
    tag = _hp(np.load(ROOT / "assets" / "self_tag_gray.npy").astype(np.float32))
    out, last = [], None
    for im in imgs:
        g = _hp(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32))
        r = _match(g, tag)
        _, s, _, loc = cv2.minMaxLoc(r)
        out.append((loc[0], loc[1], tag.shape[1], tag.shape[0]) if s >= 0.6 else last)
        last = out[-1]
    return out


def patch(im, tg):
    x, y, w, h = tg
    cx = x + w // 2
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    P = np.zeros((PUP + PDN, 2 * PW), np.float32)
    y0, x0 = y - PUP, cx - PW
    sy0, sx0 = max(0, y0), max(0, x0)
    sy1, sx1 = min(g.shape[0], y + PDN), min(g.shape[1], cx + PW)
    P[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = g[sy0:sy1, sx0:sx1]
    P = cv2.GaussianBlur(P, (0, 0), DS / 2)
    return cv2.resize(P, (2 * PW // DS, (PUP + PDN) // DS), interpolation=cv2.INTER_AREA)


def dists(a, R):
    """Mean abs difference of patch `a` to every patch in the stack R (n, h, w), best over small shifts."""
    best = np.full(len(R), 1e9, np.float32)
    h, w = a.shape
    for dy in range(-SHIFT, SHIFT + 1):
        for dx in range(-SHIFT, SHIFT + 1):
            A = a[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)]
            B = R[:, max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)]
            best = np.minimum(best, np.abs(B - A).mean(axis=(1, 2)))
    return best


def stack(pairs, most):
    """(patches, facings) of at most `most` evenly spread (patch, facing) pairs per facing, plus their mirrors."""
    out = []
    for f in (1, -1):
        mine = [p for p, g in pairs if g == f]
        out += [(mine[i], f) for i in np.linspace(0, len(mine) - 1, min(most, len(mine))).astype(int)] if mine else []
    out += [(np.ascontiguousarray(p[:, ::-1]), -f) for p, f in out]                  # Maple mirrors sprites
    return np.stack([p for p, _ in out]), np.array([f for _, f in out])


def trials(ev):
    """[(name, t_start, t_end, info, keys)] from the marks; keys = key events inside."""
    marks = [e for e in ev if "trial" in e]
    out = []
    for i, m in enumerate(marks):
        t1 = marks[i + 1]["t"] if i + 1 < len(marks) else m["t"] + 3
        keys = [e for e in ev if "key" in e and m["t"] <= e["t"] < t1]
        out.append((m["trial"], m["t"], t1, m, keys))
    return out


def main():
    run = Path(sys.argv[1])
    sheets = "--sheets" in sys.argv
    meta = json.loads((run / "meta.json").read_text())
    T, imgs, ev = load(run)
    print(f"{len(T)} frames, {meta.get('fps')} fps, attack key {meta['attack']}")
    tags = locate(imgs)
    P = [patch(im, tg) if tg else None for im, tg in zip(imgs, tags)]
    TR = trials(ev)
    atk = meta["attack"]

    # standing references: the second half of every `face` rest, facing = the side tapped
    refs = []
    for name, t0, t1, m, keys in TR:
        if name == "face":
            up = max([k["t"] for k in keys if k["up"]] or [t0])
            for i in np.where((T > up + 0.55) & (T < t1 - 0.05))[0]:
                if P[i] is not None:
                    refs.append((P[i], 1 if m["side"] == "right" else -1))
    RS, RF = stack(refs, 25)
    print(f"standing references: {len(RS)} (mirrors included)")

    def stand_d(p):
        d = dists(p, RS)
        return {1: float(d[RF == 1].min()), -1: float(d[RF == -1].min())}

    D = [stand_d(p) if p is not None else None for p in P]
    dmin = np.array([min(d.values()) if d else np.nan for d in D])
    step = np.array([np.nan] + [float(np.abs(P[i] - P[i - 1]).mean()) if P[i] is not None and P[i - 1] is not None
                                else np.nan for i in range(1, len(P))])

    # thresholds from the data: rest frames (>= 0.8 s after any key) vs frames 0.25-0.45 s into a single swing
    keyt = np.array([e["t"] for e in ev if "key" in e])
    quiet = np.array([np.min(np.abs(t - keyt[keyt <= t]), initial=9) >= 0.8 if (keyt <= t).any() else True
                      for t in T])
    swing = np.zeros(len(T), bool)
    for name, t0, t1, m, keys in TR:
        if name == "single":
            dn = next(k["t"] for k in keys if k["key"] == atk and not k["up"])
            swing |= (T > dn + 0.25) & (T < dn + 0.45)
    q, s = dmin[quiet & ~np.isnan(dmin)], dmin[swing & ~np.isnan(dmin)]
    print(f"stand distance: quiet frames p50 {np.percentile(q, 50):.1f} p99 {np.percentile(q, 99):.1f} | "
          f"mid-swing p1 {np.percentile(s, 1):.1f} p50 {np.percentile(s, 50):.1f}")
    thr = (np.percentile(q, 99) + np.percentile(s, 1)) / 2
    qs = step[quiet & ~np.isnan(step)]
    change = max(np.percentile(qs, 99) * 3, 1.0) if CHANGE is None else CHANGE
    print(f"-> stand if < {thr:.1f};  pose change if step > {change:.2f} (quiet step p99 {np.percentile(qs, 99):.2f})")

    # facing of acting frames: nearest known-facing swing frame (single trials: facing = the stand before them)
    def facing_at(i):
        return 1 if D[i][1] <= D[i][-1] else -1

    lib = []
    for name, t0, t1, m, keys in TR:
        if name in ("single", "double", "hold"):
            pre = np.where((T < t0) & (T > t0 - 0.5) & (dmin < thr))[0]
            if len(pre):
                f = facing_at(pre[-1])
                for i in np.where((T > t0) & (T < t1) & (dmin >= thr))[0]:
                    lib.append((P[i], f))
    if lib:
        LS, LF = stack(lib, 150)

    def act_facing(i):
        return int(LF[np.argmin(dists(P[i], LS))])

    state = []
    for i in range(len(T)):
        if D[i] is None:
            state.append("?")
        elif dmin[i] < thr:
            state.append("." if facing_at(i) > 0 else ",")
        else:
            state.append("R" if lib and act_facing(i) > 0 else "L" if lib else "A")

    # per trial
    rows = []
    for name, t0, t1, m, keys in TR:
        idx = np.where((T >= t0) & (T < t1))[0]
        if not len(idx):
            continue
        line, kk = [], list(keys)
        for i in idx:
            while kk and kk[0]["t"] <= T[i]:
                k = kk.pop(0)
                line.append(("^" if k["up"] else "v") + ("q" if k["key"] == atk else k["key"][0].upper()))
            line.append(("|" if step[i] > change else "") + state[i])
        dn = [k["t"] for k in keys if k["key"] == atk and not k["up"]]
        act = [i for i in idx if state[i] in "RLA"]
        segs = []
        for i in act:
            if segs and T[i] - T[segs[-1][1]] < 0.07:
                segs[-1][1] = i
            else:
                segs.append([i, i])
        seg_txt = " ".join(f"[{T[a] - (dn[0] if dn else t0):+.3f}..{T[b] - (dn[0] if dn else t0):+.3f} "
                           f"{T[b] - T[a]:.3f}s]" for a, b in segs)
        ch = [T[i] - (dn[0] if dn else t0) for i in idx if step[i] > change]
        rest = [state[i] for i in idx if T[i] > t1 - 0.3 and state[i] in ".,"]
        end = "R" if rest and rest[-1] == "." else "L" if rest else "?"
        info = {k: v for k, v in m.items() if k not in ("t", "trial", "at")}
        k_txt = " ".join(f"{'up' if k['up'] else 'dn'} {k['key']} {k['t'] - (dn[0] if dn else t0):+.3f}" for k in keys)
        print(f"\n== {name} {info or ''} t={t0:.2f}  keys: {k_txt}")
        print(f"   acting: {seg_txt or 'none'}   ends facing {end}")
        print(f"   pose changes at: {' '.join(f'{c:+.3f}' for c in ch)}")
        print("   " + "".join(line))
        rows.append({"trial": name, "t": t0, "keys": keys, "segs": [(T[a], T[b]) for a, b in segs], "end": end,
                     "changes": ch, "press": dn})
        if sheets and name != "face":
            tiles = []
            for i in idx[::2]:
                down = set()
                for k in keys:
                    if k["t"] <= T[i]:
                        (down.discard if k["up"] else down.add)(k["key"])
                c = cv2.resize(imgs[i], (imgs[i].shape[1] * 2 // 3, imgs[i].shape[0] * 2 // 3))
                txt = f"{T[i] - (dn[0] if dn else t0):+.3f} {state[i]} {','.join(sorted(down))}"
                cv2.rectangle(c, (0, 0), (c.shape[1], 13), (0, 0, 0), -1)
                cv2.putText(c, txt, (2, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1)
                tiles.append(c)
            cols = 6
            while len(tiles) % cols:
                tiles.append(np.zeros_like(tiles[0]))
            g = cv2.vconcat([cv2.hconcat(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
            cv2.imwrite(str(run / f"sheet_{len(rows):02d}_{name}.png"), g)
    (run / "read.json").write_text(json.dumps(rows, default=float, indent=0))


if __name__ == "__main__":
    main()
