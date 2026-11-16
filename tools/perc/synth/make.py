"""Make a synthetic frame set (PLAN-perception.md step 3.0b; how a frame is built: synth.py).

    python tools/perc/synth/make.py RUN --n 500 --seed 1 --out runs/synth/ant4_500
    python tools/perc/synth/make.py RUN --n 40 --seed 7 --out tests/fixtures/synth_ant4 --webp --crop   (pytest)
    python tools/perc/synth/make.py --sheet runs/synth/ant4_500                                     (one per case)

Bases: the labelled frames of RUN (labels.json v2: they say where the real mobs were, for the spots that can't be
erased). Cases, one per frame, every pasted mob of the frame made for it (1-3 mobs; a mob may still pick up other
classes, e.g. a dying one at the edge):
  clear     stand / move / jump poses, opaque, nothing over it
  scenery   15-80 % of its on-screen body under the layers above its foothold
  fade      opacity 0.2-0.9
  dying     die poses        hit     the hit pose   (both + a "prime" frame: the same mob in its stand pose at
            the same feet, shown to the tracker first - it turns a track dying / hit, never starts one so)
  edge      30-70 % of the body on screen (left / right edge)
  effect    1-2 damage numbers over it (BasicEff), opacity 0.5-1
  player    our character cut from another frame standing in front of it (10-70 % covered)
  ui        under the chat / quickslots (10-70 % covered; only a rect with no real mob near it in the base)
  free      no mob (the ghost test; only bases where no real mob had to be kept); half of them with damage
            numbers / our character pasted over bare scenery
Out: OUT/frames/NNNNNN.png (.webp lossless with --webp) + OUT/synth.json = labels.json v2 ({"v": 2, "frames": {n:
{"mobs", "unsure", "false"}}}) + per frame "case", "base", "C", "dontcare" boxes, per mob the exact extras (pose,
facing, opacity, onscreen, vis, cover, layer, box). Scored by tools/perc/label_eval.py OUT --labels synth.json
--tracks before.jsonl --synth.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synth as S  # noqa: E402

CASES = ["clear", "scenery", "fade", "dying", "hit", "edge", "effect", "player", "ui", "free"]


def poses(syn, mob, case, rng):
    sp = syn.sprites[mob]
    if case == "dying":
        pool = [s for s in sp if s.anim.startswith("die")]
    elif case == "hit":
        pool = [s for s in sp if s.anim.startswith("hit")]
    else:
        pool = [s for s in sp if s.anim in ("stand", "move", "jump", "fly")]
    return pool[rng.integers(len(pool))]


def place(syn, base, case, rng, occupied, ui_rect, mob_type):
    """One mob for `case` that fits, or None."""
    sp = poses(syn, mob_type, case, rng)
    facing = ["left", "right"][rng.integers(2)]
    for _ in range(300):
        if case == "edge":
            side = rng.integers(2)
            w = sp.im[facing].shape[1]
            r = (-w * 0.6, w * 0.6) if side == 0 else (S.SW - w * 0.6, S.SW + w * 0.6)
            pt = syn.foothold_point(base.C, rng, r, (80, S.PLAY_H))
        elif case == "ui":
            rects = [r for r in S.UI_OVER if S.Synth.ui_free(base, r)]
            if not rects:
                return None
            x0, y0, x1, y1 = rects[rng.integers(len(rects))]
            pt = syn.foothold_point(base.C, rng, (x0 - 20, x1 + 20), (y0 + 10, S.PLAY_H))
        else:
            pt = syn.foothold_point(base.C, rng, (40, S.SW - 40), (80, S.PLAY_H))
        if pt is None:
            return None
        x, y, fh = pt
        if sp.anim == "jump":
            y -= int(rng.integers(10, 45))
        op = float(rng.uniform(0.2, 0.9)) if case == "fade" else 1.0
        m = S.Mob(sp, facing, (x - int(base.C[0]), y - int(base.C[1])), op, fh["layerId"])
        foot = m.a > 0
        yy = np.arange(m.y, m.y + m.h)
        if (foot & (yy[:, None] >= S.PLAY_H)).any():
            continue                                        # under the HUD / the unmodelled corner
        on = float((m.a * m.on).sum() / m.a.sum())
        if case == "edge":
            if not 0.3 <= on <= 0.7:
                continue
        elif on < 1.0 or m.x < 2 or m.x + m.w > S.SW - 2:
            continue
        r = S._clip(m.x, m.y, m.w, m.h)
        x0, y0, x1, y1, sx, sy = r
        fp = foot[sy:sy + y1 - y0, sx:sx + x1 - x0]
        fpd = cv2.dilate(fp.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        if (fpd & occupied[y0:y1, x0:x1]).any():
            continue
        aw = m.a[sy:sy + y1 - y0, sx:sx + x1 - x0]
        fa = syn.fa_at(m.layer, base.C, x0, y0, x1 - x0, y1 - y0)[..., 3] / 255.0
        s_cov = float((aw * fa).sum() / aw.sum())
        if case == "scenery":
            if not 0.15 <= s_cov <= 0.8:
                continue
        elif s_cov >= 0.02:
            continue
        u = base.ui_alpha[y0:y1, x0:x1]
        u_cov = float((aw * u).sum() / aw.sum())
        if case == "ui":
            if not 0.1 <= u_cov <= 0.7:
                continue
        elif (fpd & ui_rect[y0:y1, x0:x1]).any():
            continue
        occupied[y0:y1, x0:x1] |= cv2.dilate(fp.astype(np.uint8), np.ones((17, 17), np.uint8)) > 0
        return m
    return None


def cover_of(m, alpha):
    r = S._clip(m.x, m.y, m.w, m.h)
    x0, y0, x1, y1, sx, sy = r
    aw = (m.a * m.on)[sy:sy + y1 - y0, sx:sx + x1 - x0]
    return float((aw * alpha[y0:y1, x0:x1]).sum() / max(aw.sum(), 1e-6))


def overlay_effect(syn, img, mobs, m, rng):
    """1-2 damage numbers over mob m (each must cover >= 5 % of it, the first tries up to 30 places)."""
    k = int(rng.integers(1, 3))
    for j in range(k):
        num = S.damage_number(syn, int(rng.integers(10, 1000)) if rng.random() < 0.8 else int(rng.integers(1, 10)))
        op = float(rng.uniform(0.5, 1.0))
        for _ in range(30):
            cx = m.feet[0] + int(rng.integers(-25, 26))
            by = m.feet[1] - int(rng.uniform(0.2, 1.0) * m.h) + int(rng.integers(0, 30)) + 28 * j
            x, y = cx - num.shape[1] // 2, by - num.shape[0]
            al = np.zeros((S.PLAY_H, S.SW), np.float32)
            r = S._clip(x, y, num.shape[1], num.shape[0])
            if r is None:
                continue
            x0, y0, x1, y1, sx, sy = r
            al[y0:y1, x0:x1] = num[sy:sy + y1 - y0, sx:sx + x1 - x0, 3] / 255.0 * op
            if cover_of(m, al) >= 0.05:
                break
        al = S.paste(img, num, x, y, op)
        for q in mobs:
            q.add_cover("e", al)


def overlay_player(syn, img, mobs, m, rng):
    pl = syn.players()
    if not pl:
        return False
    for _ in range(40):
        im, (ax, ay) = pl[rng.integers(len(pl))]
        dx = int(rng.integers(-55, 56))
        x, y = m.feet[0] + dx - ax, m.feet[1] - ay
        al = np.zeros((S.PLAY_H, S.SW), np.float32)
        r = S._clip(x, y, im.shape[1], im.shape[0])
        if r is None:
            continue
        x0, y0, x1, y1, sx, sy = r
        al[y0:y1, x0:x1] = im[sy:sy + y1 - y0, sx:sx + x1 - x0, 3] / 255.0
        if 0.1 <= cover_of(m, al) <= 0.7:
            al = S.paste(img, im, x, y)
            for q in mobs:
                q.add_cover("p", al)
            return True
    return False


def make_frame(syn, base, case, rng) -> tuple:
    img = base.frame.copy()
    ui_rect = np.zeros((S.PLAY_H, S.SW), bool)
    for x0, y0, x1, y1 in S.UI_RECTS:
        ui_rect[y0:y1, x0:x1] = True
    occupied = cv2.dilate(base.keep.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    for x0, y0, x1, y1 in base.dontcare:
        occupied[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] |= ~ui_rect[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
    mobs = []
    if case != "free":
        n = int(rng.integers(1, 3 if case in ("edge", "ui", "scenery") else 4))
        for _ in range(n):
            m = place(syn, base, case, rng, occupied, ui_rect, syn.types[rng.integers(len(syn.types))])
            if m is not None:
                m.type = m.sp.mob
                mobs.append(m)
        if not mobs:
            return None
        for m in mobs:
            S.draw_mob(img, base, syn, m, under_ui=case == "ui")
        for m in mobs:
            if case == "effect":
                overlay_effect(syn, img, mobs, m, rng)
            elif case == "player":
                if not overlay_player(syn, img, mobs, m, rng):
                    return None
        if case == "ui":
            u = base.ui_alpha > 0
            img[:S.PLAY_H][u] = base.frame[:S.PLAY_H][u]
            for m in mobs:
                m.add_cover("u", base.ui_alpha)
    elif base.unsure:                                        # a real mob kept in our blob: not mob-free
        return None
    elif rng.random() < 0.5:                                 # distractors over bare scenery
        for _ in range(int(rng.integers(1, 4))):
            pt = syn.foothold_point(base.C, rng, (60, S.SW - 60), (120, S.PLAY_H))
            if pt is None:
                continue
            sx, sy = pt[0] - int(base.C[0]), pt[1] - int(base.C[1])
            if rng.random() < 0.6:
                num = S.damage_number(syn, int(rng.integers(10, 1000)))
                S.paste(img, num, sx - num.shape[1] // 2, sy - int(rng.integers(30, 90)) - num.shape[0],
                        float(rng.uniform(0.5, 1)))
            elif syn.players():
                im, (ax, ay) = syn.players()[rng.integers(len(syn.players()))]
                if not occupied[max(0, sy - ay):sy, max(0, sx - ax):sx + im.shape[1] - ax].any():
                    S.paste(img, im, sx - ax, sy - ay)
    prime = None
    if case in ("dying", "hit"):                             # the same mobs alive a moment before (a tracker
        prime = base.frame.copy()                           # turns a track dying / hit; it never starts one so)
        for m in mobs:
            st = next(sp for sp in syn.sprites[m.type] if sp.anim == "stand")
            S.draw_mob(prime, base, syn, S.Mob(st, m.facing, m.feet, 1.0, m.layer))
    truth = [m.truth(m.type) for m in mobs]
    return img, prime, {"mobs": truth, "unsure": base.unsure, "false": [], "dontcare": base.dontcare, "case": case,
                 "base": base.n, "C": list(base.C)}


def generate(run: Path, n: int, seed: int, out: Path, webp: bool = False, crop: bool = False, log=print):
    syn = S.Synth(run)
    rng = np.random.default_rng(seed)
    bases = sorted(syn.labels)
    jobs = [(i, CASES[i % len(CASES)], int(bases[rng.integers(len(bases))])) for i in range(n)]
    jobs.sort(key=lambda j: j[2])
    (out / "frames").mkdir(parents=True, exist_ok=True)
    frames, cur, fails = {}, None, 0
    for i, case, bn in jobs:
        tries = 0
        while True:
            if cur is None or cur.n != bn:
                cur = syn.base(bn)
            r = make_frame(syn, cur, case, rng) if cur is not None else None
            if r is not None:
                break
            tries += 1
            fails += 1
            bn = int(bases[rng.integers(len(bases))])        # this camera can't hold the case: another base
            if tries > 40:
                raise RuntimeError(f"case {case}: no base fits")
        img, prime, rec_ = r
        if crop:                                             # the window around the mobs (the pytest set: small)
            bx = [m["box"] for m in rec_["mobs"]] or [[int(rng.integers(0, S.SW - 640)), int(rng.integers(0, 300)), 640, 400]]
            x0 = max(0, min(b[0] for b in bx) - 64)
            y0 = max(0, min(b[1] for b in bx) - 64)
            x1 = min(S.SW, max(b[0] + b[2] for b in bx) + 64)
            y1 = min(S.PLAY_H, max(b[1] + b[3] for b in bx) + 64)
            rec_["window"] = [x0, y0, x1, y1]
            img = img[y0:y1, x0:x1]
            prime = prime[y0:y1, x0:x1] if prime is not None else None
        name = f"{i:06d}." + ("webp" if webp else "png")
        params = [cv2.IMWRITE_WEBP_QUALITY, 101] if webp else [cv2.IMWRITE_PNG_COMPRESSION, 1]
        cv2.imwrite(str(out / "frames" / name), img, params)
        rec_["frame"] = name
        if prime is not None:
            rec_["prime"] = name.replace(".", "_prime.")
            cv2.imwrite(str(out / "frames" / rec_["prime"]), prime, params)
        frames[str(i)] = rec_
    frames = dict(sorted(frames.items(), key=lambda kv: int(kv[0])))
    meta = {"v": 2, "synth": 1, "run": str(run).replace("\\", "/"), "map": syn.map_id, "seed": seed, "frames": frames}
    (out / "synth.json").write_text(json.dumps(meta, indent=0))
    by = {}
    for f in frames.values():
        by[f["case"]] = by.get(f["case"], 0) + len(f["mobs"])
    log(f"{len(frames)} frames -> {out} (mobs per case {by}; {fails} retries on another base)")


def sheet(out: Path, cases=None, w=420, h=280):
    meta = json.loads((out / "synth.json").read_text())
    picks = []
    want = cases or CASES[:-1] + ["free", "free+"]
    for c in want:
        for k, f in meta["frames"].items():
            if f["case"] == c.rstrip("+") and (c != "free" or k not in [p[0] for p in picks]):
                if c.startswith("free"):
                    if k in [p[0] for p in picks]:
                        continue
                picks.append((k, f, c))
                break
    tiles = []
    for k, f, c in picks:
        img = cv2.imread(str(out / "frames" / f["frame"]))
        if f["mobs"]:
            fx, fy = f["mobs"][0]["feet"]
            cx, cy = fx, fy - 40
        else:
            cx, cy = img.shape[1] // 2, 400
        x0 = int(np.clip(cx - w // 2, 0, img.shape[1] - w))
        y0 = int(np.clip(cy - h // 2, 0, 700 - h))
        t = np.full((h + 22, w, 3), 20, np.uint8)
        t[:h] = img[y0:y0 + h, x0:x0 + w]
        cap = f"#{k} {c}"
        if f["mobs"]:
            m = f["mobs"][0]
            cap += f" {m['type']} {m['pose']} {m['facing'][0]} op{m['opacity']:.2f} vis{m['vis']:.2f} [{m['cls'] or '-'}]"
        cv2.putText(t, cap, (4, h + 16), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), 1)
        tiles.append(t)
    while len(tiles) % 3:
        tiles.append(np.full_like(tiles[0], 20))
    rows = [np.hstack([np.pad(a, ((0, 4), (0, 4), (0, 0))) for a in tiles[i:i + 3]]) for i in range(0, len(tiles), 3)]
    img = np.vstack(rows)
    cv2.imwrite(str(out / "sheet.png"), img)
    print(f"sheet of {len(picks)} frames -> {out / 'sheet.png'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?", type=Path)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--webp", action="store_true")
    ap.add_argument("--crop", action="store_true", help="store only the window around the mobs (\"window\")")
    ap.add_argument("--sheet", type=Path, default=None)
    a = ap.parse_args()
    if a.sheet:
        return sheet(a.sheet)
    generate(a.run, a.n, a.seed, a.out, a.webp, a.crop)
    if not a.crop:
        sheet(a.out)


if __name__ == "__main__":
    main()
