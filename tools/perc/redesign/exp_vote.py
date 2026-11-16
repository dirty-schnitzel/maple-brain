"""E9 (2026-11-17): exact-colour voting as the fit's candidate search - the evidence behind the 3.2 speed plan
(PLAN-fit-speed.md). A prototype: candidates only, no per-pixel acceptance (fit.py stage 2 stays the judge).

Facts it rests on (012059_1, native PNG):
- a frame shows a sprite's opaque pixels with EXACTLY the client's colours: difference 0 on 98.57 % of 827 k opaque
  pixels of 369 clear mobs (the rest are covered; +-1..8 on 0.03 %);
- a mob type's palette is tiny (Horny Mushroom 77 colours over all poses, Zombie Mushroom 134, Stirge 14, Bubbling 60)
  and sprites are dithered: most 2x2 pixel blocks are not one flat colour (Horny ~1350 such blocks per pose of ~1970 px);
- a fading mob follows I = B + o (s - B) with ONE o to the level: residual 0 on 90.1 % of the pixels of 161 real fading
  mobs, <= 1 on 95.7 % (the rest covered). Respawn waves fade in together (n3642: every mob at o = 0.98).

The search (work ~ sprite-coloured pixels on screen, NOT positions x poses x sprite pixels; flyers cost nothing extra):
1. palette id per frame pixel: one LUT lookup of its 24-bit colour (0 = no sprite colour of this map);
2. FEATURE = a 2x2 block of ids, all sprite colours, not one flat colour; a table built from the sprites lists per
   feature key where it occurs: (pose, facing, offset to the feet); keys with > max_entries places are dropped;
3. every frame feature VOTES for the (pose, feet) cells its key allows;
4. EXCLUSIVE votes: a feature counts only for the best-voted cell it supports - the other poses / offsets that share
   part of a mob's picture (aliases) lose their votes; what stays is ~1 cell per mob;
5. fading mobs: the pixels the scene does not explain and that are no palette colour ("residue") are un-blended,
   s' = B + (I - B) * 255 / alpha, for every alpha; where one alpha turns many horizontally adjacent residue pixel
   PAIRS of one 48 px screen cell into colour pairs that occur in a sprite, a mob is fading there at that alpha ->
   un-blend the residue with it -> palette ids (+-2 levels) -> steps 2-4.
The opaque search needs no scene at all (it works where the scene camera is lost and on maps without a clean scene);
only step 5 needs the expected scene.

    python tools/perc/redesign/exp_vote.py table MAP                  table statistics
    python tools/perc/redesign/exp_vote.py synth OUT                  vs synth.json truth, per case; false cells; ms
    python tools/perc/redesign/exp_vote.py labels RUN                 vs labels.json v2 per class (match 40 / 30 px, type)
    python tools/perc/redesign/exp_vote.py tracks RUN REPLAY.jsonl    other maps (no labels): today's well-sighted tracks
"""
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402

PLAY_H, SW, PAD = 700, 1366, 128
MOBS, MAPS = ROOT / "assets" / "mcw" / "mobs", ROOT / "assets" / "mcw" / "maps"
CELLS_W = (SW + 2 * PAD) * (PLAY_H + 2 * PAD)
TS = (8, 16, 24, 32, 48)


def key24(bgr):
    return bgr[..., 0].astype(np.int64) | (bgr[..., 1].astype(np.int64) << 8) | (bgr[..., 2].astype(np.int64) << 16)


class Voter:
    def __init__(self, map_id: int, max_entries: int = 64, dev: str = "cuda"):
        self.dev = dev
        m = json.loads((MAPS / str(map_id) / "map.json").read_text(encoding="utf-8"))
        self.types = sorted({int(x["id"]) for x in m.get("mobs") or []})
        self.poses = []                          # g -> (type, pose, facing, ox, oy, h, w)
        ims = []
        for t in self.types:
            info = json.loads((MOBS / str(t) / "mob.json").read_text(encoding="utf-8"))
            for anim, fs in (info.get("frames") or {}).items():
                for i, f in enumerate(fs or []):
                    im = cv2.imread(str(MOBS / str(t) / f["file"]), cv2.IMREAD_UNCHANGED)
                    if im is None or im.ndim != 3 or im.shape[2] != 4 or (im[..., 3] > 0).sum() < 60:
                        continue
                    h, w = im.shape[:2]
                    ox, oy = f.get("origin") or (w // 2, h)
                    for facing, pic, x0 in (("left", im, int(ox)), ("right", np.ascontiguousarray(im[:, ::-1]), int(w - ox))):
                        self.poses.append((t, f"{anim}_{i}", facing, x0, int(oy), h, w))
                        ims.append(pic)
        # palette: every colour of an opaque sprite pixel -> id 1.. (0 = none)
        cols = np.unique(np.concatenate([key24(im[..., :3])[im[..., 3] == 255] for im in ims]))
        assert len(cols) < 32767
        lut = np.zeros(1 << 24, np.int16)
        lut[cols] = np.arange(1, len(cols) + 1)
        self.n_colors = len(cols)
        self.lut = torch.from_numpy(lut).to(dev)
        # the same with a +-2 cube around every colour (an un-blended fade pixel is off by ~0.5 / opacity)
        lt = lut.reshape(256, 256, 256).copy()                      # [r, g, b]
        b, g_, r = cols & 255, (cols >> 8) & 255, (cols >> 16) & 255
        for dr in range(-2, 3):
            for dg in range(-2, 3):
                for db in range(-2, 3):
                    rr, gg, bb = np.clip(r + dr, 0, 255), np.clip(g_ + dg, 0, 255), np.clip(b + db, 0, 255)
                    free = lt[rr, gg, bb] == 0
                    lt[rr[free], gg[free], bb[free]] = np.arange(1, len(cols) + 1)[free]
        self.lut_tol = torch.from_numpy(lt.reshape(-1)).to(dev)
        # features: 2x2 blocks of ids, all opaque, not one colour; + the colour pairs (left, right) of the sprites
        ks, gs, dxs, dys, self.n_feat = [], [], [], [], []
        pair = np.zeros((len(cols) + 1, len(cols) + 1), bool)
        for g, (im, p) in enumerate(zip(ims, self.poses)):
            ids = np.where(im[..., 3] == 255, lut[key24(im[..., :3])], 0).astype(np.int64)
            a, b, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
            ok = (a > 0) & (b > 0) & (c > 0) & (d > 0) & ~((a == b) & (a == c) & (a == d))
            yy, xx = np.nonzero(ok)
            ks.append(a[ok] | (b[ok] << 16) | (c[ok] << 32) | (d[ok] << 48))
            gs.append(np.full(len(yy), g))
            dxs.append(xx - p[3])                # block's top-left relative to the feet
            dys.append(yy - p[4])
            self.n_feat.append(int(ok.sum()))
            l, r2 = ids[:, :-1], ids[:, 1:]
            mm = (l > 0) & (r2 > 0) & (l != r2)
            pair[l[mm], r2[mm]] = True
        self.pair_ok = torch.from_numpy(pair).to(dev)
        k, g, dx, dy = (np.concatenate(v) for v in (ks, gs, dxs, dys))
        order = np.argsort(k, kind="stable")
        k, g, dx, dy = k[order], g[order], dx[order], dy[order]
        uk, start, count = np.unique(k, return_index=True, return_counts=True)
        self.raw_entries, self.raw_keys = len(k), len(uk)
        sel = np.repeat(count <= max_entries, count)                # a feature in too many places says little
        self.kept = np.zeros(len(self.poses), int)
        np.add.at(self.kept, g[sel], 1)
        k, g, dx, dy = k[sel], g[sel], dx[sel], dy[sel]
        uk, start, count = np.unique(k, return_index=True, return_counts=True)
        t = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(dev).long()  # noqa: E731
        self.uk, self.start, self.count = t(uk), t(start), t(count)
        self.eg, self.edx, self.edy = t(g), t(dx), t(dy)
        self.entries, self.G = len(k), len(self.poses)
        self.g_of = {(p[0], p[1], p[2]): i for i, p in enumerate(self.poses)}
        self.type_g = np.array([p[0] for p in self.poses])

    def stats(self):
        print(f"types {self.types}: {self.G} poses (both facings), palette {self.n_colors} colours, sprite colour pairs "
              f"{int(self.pair_ok.sum())}; features (2x2, not flat) {self.raw_entries} with {self.raw_keys} keys -> kept "
              f"{self.entries} entries, {len(self.uk)} keys")
        for t in self.types:
            gi = [i for i, p in enumerate(self.poses) if p[0] == t and p[2] == "left"]
            print(f"  type {t}: per pose features all / kept: " +
                  ", ".join(f"{self.poses[i][1]} {self.n_feat[i]}/{self.kept[i]}" for i in gi))
        c = self.count.cpu().numpy()
        print(f"  places per kept key: p50 {np.median(c):.0f} p90 {np.percentile(c, 90):.0f} max {c.max()}")

    def ids(self, frame):
        f = frame[:PLAY_H].long()
        return self.lut[f[..., 0] | (f[..., 1] << 8) | (f[..., 2] << 16)].long()

    def cells(self, ids, tmin: int = 8):
        """Palette-id picture -> the cells (pose g, feet x, y) with >= tmin EXCLUSIVE votes: (g, x, y, raw votes,
        exclusive votes) arrays + counters."""
        a, b, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
        ok = (a > 0) & (b > 0) & (c > 0) & (d > 0) & ~((a == b) & (a == c) & (a == d))
        yx = ok.nonzero()
        y0, x0 = yx[:, 0], yx[:, 1]
        key = ids[y0, x0] | (ids[y0, x0 + 1] << 16) | (ids[y0 + 1, x0] << 32) | (ids[y0 + 1, x0 + 1] << 48)
        z = np.zeros(0, int)
        if len(key) == 0:
            return z, z, z, z, z, {"feat": 0, "hit": 0, "votes": 0}
        j = torch.searchsorted(self.uk, key).clamp(max=len(self.uk) - 1)
        hit = (self.uk[j] == key).nonzero()[:, 0]
        j, y0, x0 = j[hit], y0[hit], x0[hit]
        cnt = self.count[j]
        src = torch.repeat_interleave(torch.arange(len(j), device=self.dev), cnt)
        if len(src) == 0:
            return z, z, z, z, z, {"feat": len(key), "hit": 0, "votes": 0}
        first = torch.cumsum(cnt, 0) - cnt                                   # each feature's first vote
        e = self.start[j][src] + (torch.arange(len(src), device=self.dev) - first[src])
        cell = self.eg[e] * CELLS_W + (y0[src] - self.edy[e] + PAD) * (SW + 2 * PAD) + (x0[src] - self.edx[e] + PAD)
        u, inv, n = torch.unique(cell, return_inverse=True, return_counts=True)
        nv = n[inv]                                                          # each vote: its cell's total
        best = torch.zeros(len(j), dtype=nv.dtype, device=self.dev).scatter_reduce(0, src, nv, "amax", include_self=False)
        win = nv == best[src]                                                # the feature's best cell(s) keep it
        excl = torch.zeros(len(u), dtype=torch.long, device=self.dev).index_add_(0, inv[win], win[win].long())
        keep = excl >= tmin
        u, n, excl = u[keep], n[keep], excl[keep]
        return ((u // CELLS_W).cpu().numpy(), (u % (SW + 2 * PAD) - PAD).cpu().numpy(),
                ((u // (SW + 2 * PAD)) % (PLAY_H + 2 * PAD) - PAD).cpu().numpy(), n.cpu().numpy(), excl.cpu().numpy(),
                {"feat": len(key), "hit": len(j), "votes": len(src)})

    def fade_alphas(self, frame, ids, exp, world, n_min: int = 80, cell: int = 48, lo: int = 38, hi: int = 252,
                    step: int = 2, top: int = 3):
        """The opacities (alpha / 255) at which mobs are fading on screen -> [(alpha, pairs)] best first (<= top),
        the residue (yx, I - B, B), counters. `exp`: expected scene, float (H, W, 3); `world`: bool (H, W), the
        scenery is known there and it is no opaque UI."""
        r = frame[:PLAY_H].float() - exp
        mag = r.abs().amax(2)
        resm = (mag > 4) & world & (ids == 0)
        res = resm.nonzero()
        resid = (res, r[res[:, 0], res[:, 1]], exp[res[:, 0], res[:, 1]])
        strong = resm & (mag >= 24)
        yx = (strong[:, :-1] & strong[:, 1:]).nonzero()                      # the left pixel of a residue pair
        info = {"residue": len(res), "pairs": len(yx)}
        if len(yx) < n_min:
            return [], resid, info
        y, x = yx[:, 0], yx[:, 1]
        al = torch.arange(lo, hi + 1, step, device=self.dev)
        wc = SW // cell + 1
        ci = (y // cell) * wc + x // cell
        hist = torch.zeros(((PLAY_H // cell + 1) * wc, len(al)), device=self.dev)
        for i in range(0, len(yx), 16384):
            ys, xs = y[i:i + 16384], x[i:i + 16384]
            two = []
            for dx in (0, 1):
                sp = (exp[ys, xs + dx][:, None] + r[ys, xs + dx][:, None] * (255.0 / al)[None, :, None]).round()
                ok = ((sp >= 0) & (sp <= 255)).all(-1)
                sp = sp.clamp(0, 255).long()
                two.append(torch.where(ok, self.lut_tol[sp[..., 0] | (sp[..., 1] << 8) | (sp[..., 2] << 16)].long(),
                                       torch.zeros_like(sp[..., 0])))
            hist.index_add_(0, ci[i:i + 16384], self.pair_ok[two[0], two[1]].float())
        best, at = hist.max(1)
        out = {}
        for c in (best >= n_min).nonzero()[:, 0].tolist():
            a = int(al[int(at[c])])
            k = next((k for k in out if abs(k - a) <= 2 * step), a)
            out[k] = max(out.get(k, 0), int(best[c]))
        return sorted(out.items(), key=lambda kv: -kv[1])[:top], resid, info

    def fade_ids(self, resid, alpha: int):
        """The palette-id picture of the residue un-blended at `alpha` (0 where that is no palette colour)."""
        res, rI, Bp = resid
        sp = (Bp + rI * (255.0 / alpha)).round()
        ok = ((sp >= 0) & (sp <= 255)).all(-1)
        sp = sp.clamp(0, 255).long()
        ids = torch.zeros((PLAY_H, SW), dtype=torch.long, device=self.dev)
        ids[res[:, 0], res[:, 1]] = torch.where(ok, self.lut_tol[sp[..., 0] | (sp[..., 1] << 8) | (sp[..., 2] << 16)].long(),
                                               torch.zeros_like(sp[..., 0]))
        return ids

    def candidates(self, frame, exp=None, world=None, tmin: int = 8):
        """-> rows (exclusive votes, raw votes, g, x, y, alpha) (alpha 255 = opaque), ms (opaque, fade), counters."""
        sync = torch.cuda.synchronize
        sync()
        t0 = time.perf_counter()
        ids = self.ids(frame)
        g, x, y, n, ex, c = self.cells(ids, tmin)
        rows = [(int(ex[i]), int(n[i]), int(g[i]), int(x[i]), int(y[i]), 255) for i in range(len(g))]
        sync()
        t1 = time.perf_counter()
        c["alphas"] = []
        if exp is not None:
            alphas, resid, info = self.fade_alphas(frame, ids, exp, world)
            c.update(info)
            c["alphas"] = alphas
            for a, _ in alphas:
                g, x, y, n, ex, _ = self.cells(self.fade_ids(resid, a), tmin)
                rows += [(int(ex[i]), int(n[i]), int(g[i]), int(x[i]), int(y[i]), a) for i in range(len(g))]
            sync()
        return rows, ((t1 - t0) * 1000, (time.perf_counter() - t1) * 1000), c


def scene_world(map_id, dev):
    """(Scene, world mask): hud.ui_mask with the chat rect as world (the user keeps the chat minimized)."""
    from maplebrain.perception import hud
    from maplebrain.scene import Scene
    ui = hud.ui_mask((768, SW)) > 0
    ui[630:PLAY_H, 285:850] = True
    return Scene.load(map_id), torch.from_numpy(np.ascontiguousarray(ui[:PLAY_H])).to(dev)


def timing(ms, counters, n_cells):
    o, f = np.array([m[0] for m in ms[3:]]), np.array([m[1] for m in ms[3:]])
    print(f"{len(ms)} frames: opaque vote ms p50 {np.median(o):.2f} p90 {np.percentile(o, 90):.2f}; fade search (+ votes) "
          f"ms p50 {np.median(f):.2f} p90 {np.percentile(f, 90):.2f} (frames with an alpha: "
          f"{sum(1 for c in counters if c['alphas'])}); features / frame p50 {np.median([c['feat'] for c in counters]):.0f}, "
          f"votes {np.median([c['votes'] for c in counters]):.0f}; residue px p50 "
          f"{np.median([c.get('residue', 0) for c in counters]):.0f}")
    print("candidate cells per frame with exclusive votes >= T (p50 / p90 / max): ",
          {t: (int(np.median(c)), int(np.percentile(c, 90)), max(c)) for t, c in n_cells.items()})


def run_synth(out: Path, max_entries: int):
    meta = json.loads((out / "synth.json").read_text())
    v = Voter(meta["map"], max_entries)
    v.stats()
    scene, world = scene_world(meta["map"], v.dev)
    per = defaultdict(lambda: [0] + [0] * len(TS))
    n_cells, false, ms, counters, low = {t: [] for t in TS}, Counter(), [], [], []
    for n, fr in meta["frames"].items():
        img = cv2.imread(str(out / "frames" / fr["frame"]))
        f = torch.from_numpy(np.ascontiguousarray(img[:PLAY_H])).to(v.dev)
        exp, known = scene.expected(tuple(fr["C"]))
        rows, t, c = v.candidates(f, exp, known & world)
        ms.append(t)
        counters.append(c)
        ex = np.array([r[0] for r in rows] or [0])
        gx = np.array([(v.type_g[r[2]], r[3], r[4]) for r in rows] or [(0, -999, -999)])
        for T in TS:
            n_cells[T].append(int((ex >= T).sum()))
        spots = [m["feet"] for m in fr["mobs"]] + list(fr.get("unsure") or [])
        boxes = [(b[0], b[1], b[2], b[3] + 80) for b in fr.get("dontcare") or []]
        for m in fr["mobs"]:
            near = (gx[:, 0] == m["type"]) & (np.abs(gx[:, 1] - m["feet"][0]) <= 5) & (np.abs(gx[:, 2] - m["feet"][1]) <= 3)
            best = int(ex[near].max()) if near.any() else 0
            case = fr["case"] if m["opacity"] >= 0.999 else ("fade o<0.35" if m["opacity"] < 0.35 else "fade o>=0.35")
            per[case][0] += 1
            for i, T in enumerate(TS):
                per[case][1 + i] += best >= T
            if best < 24:
                low.append((n, fr["case"], m["type"], m["pose"], m["feet"], m["opacity"], m["vis"], best, c["alphas"]))
        for r in rows:
            if any(abs(r[3] - s[0]) <= 30 and abs(r[4] - s[1]) <= 30 for s in spots) or \
                    any(b[0] <= r[3] <= b[2] and b[1] <= r[4] <= b[3] for b in boxes):
                continue
            for T in TS:
                if r[0] >= T:
                    false[(T, "fade" if r[5] < 255 else "opaque")] += 1
    timing(ms, counters, n_cells)
    print(f"mobs with a cell of their type within 5 px (x) / 3 px (y) at exclusive votes >= T {TS}")
    for k, row in sorted(per.items()):
        print(f"  {k:<13}{row[0]:>5}  " + "  ".join(f"{100 * c / max(row[0], 1):6.2f} %" for c in row[1:]))
    print("cells not within 30 px of a mob / unsure spot and not in a dontcare box, all frames, by (T, kind):",
          dict(sorted(false.items())))
    for row in low:
        print("  low: n{} {} {} {} feet {} opacity {} vis {} best exclusive {} alphas {}".format(*row))


def run_labels(run: Path, max_entries: int):
    map_id = rec.map_of(run)
    v = Voter(map_id, max_entries)
    scene, world = scene_world(map_id, v.dev)
    lab = json.loads((run / "labels.json").read_text())["frames"]
    cams = json.loads((run / "labels" / "cams.json").read_text())
    names = {"c": "clear", "e": "effect", "p": "player", "s": "scenery", "u": "ui", "d": "dying", "x": "edge", "h": "hit",
             "f": "fade"}
    n_cells, ms, counters = {t: [] for t in TS}, [], []
    tot, found, away = Counter(), {t: Counter() for t in TS}, Counter()
    for n, L in lab.items():
        name = f"{int(n):06d}.png"
        if cams.get(name) is None:
            continue
        frame = rec.read(run, name)
        f = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(v.dev)
        exp, known = scene.expected(tuple(cams[name]))
        rows, t, c = v.candidates(f, exp, known & world)
        ms.append(t)
        counters.append(c)
        ex = np.array([r[0] for r in rows] or [0])
        gx = np.array([(v.type_g[r[2]], r[3], r[4]) for r in rows] or [(0, -999, -999)])
        for T in TS:
            n_cells[T].append(int((ex >= T).sum()))
        for m in L["mobs"]:
            near = (gx[:, 0] == m["type"]) & (np.abs(gx[:, 1] - m["feet"][0]) <= 40) & (np.abs(gx[:, 2] - m["feet"][1]) <= 30)
            best = int(ex[near].max()) if near.any() else 0
            for k in (m["cls"] or "c"):
                tot[k] += 1
                for T in TS:
                    found[T][k] += best >= T
            tot["all"] += 1
            for T in TS:
                found[T]["all"] += best >= T
        spots = [m["feet"] for m in L["mobs"]] + list(L.get("unsure") or [])
        for r in rows:
            if not any(abs(r[3] - s[0]) <= 60 and abs(r[4] - s[1]) <= 40 for s in spots):
                for T in TS:
                    if r[0] >= T:
                        away[(T, "fade" if r[5] < 255 else "opaque")] += 1
    timing(ms, counters, n_cells)
    print(f"labelled mobs with a candidate cell of their type within 40 / 30 px at exclusive votes >= T {TS}")
    for k in sorted(tot, key=lambda k: -tot[k]):
        print(f"  {names.get(k, k):<8}{tot[k]:>5}  " + "  ".join(f"{100 * found[T][k] / tot[k]:6.2f} %" for T in TS))
    print("cells farther than 60 / 40 px from every labelled mob / unsure spot, by (T, kind):", dict(sorted(away.items())))


def run_tracks(run: Path, replay: Path, every: int, max_entries: int):
    v = Voter(rec.map_of(run), max_entries)
    v.stats()
    rows = [json.loads(line) for line in open(replay, encoding="utf-8")][::every]
    found, tot, votes_at, ms = Counter(), Counter(), defaultdict(list), []
    for r in rows:
        frame = rec.read(run, r.get("frame") or f"{r['n']:06d}.png")
        if frame is None:
            continue
        f = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(v.dev)
        cand, t, _ = v.candidates(f)
        ms.append(t[0])
        for m in r.get("mobs") or []:
            if m.get("state") in ("tentative", "offscreen") or m.get("src", "none") == "none" or (m.get("score") or 0) < 0.9 \
                    or not (20 <= m["sx"] < SW - 20 and 40 <= m["sy"] < PLAY_H - 10):
                continue
            tot[m["mob"]] += 1
            hit = [c[0] for c in cand if v.type_g[c[2]] == m["mob"] and abs(c[3] - m["sx"]) <= 20 and abs(c[4] - m["sy"]) <= 20]
            if hit:
                found[m["mob"]] += 1
                votes_at[m["mob"]].append(max(hit))
    print(f"{len(ms)} frames: opaque vote ms p50 {np.median(ms[3:]):.2f} p90 {np.percentile(ms[3:], 90):.2f}")
    for t in sorted(tot):
        va = np.array(votes_at[t] or [0])
        print(f"  type {t}: today's well-sighted tracks (score >= 0.9) {tot[t]}, a cell within 20 px: {found[t]} = "
              f"{100 * found[t] / tot[t]:.1f} %; exclusive votes there p5 {np.percentile(va, 5):.0f} p50 {np.median(va):.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("table", "synth", "labels", "tracks"))
    ap.add_argument("path")
    ap.add_argument("replay", nargs="?")
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--max-entries", type=int, default=64)
    a = ap.parse_args()
    if a.mode == "table":
        Voter(int(a.path), a.max_entries).stats()
    elif a.mode == "synth":
        run_synth(Path(a.path), a.max_entries)
    elif a.mode == "labels":
        run_labels(Path(a.path), a.max_entries)
    else:
        run_tracks(Path(a.path), Path(a.replay), a.every, a.max_entries)


if __name__ == "__main__":
    main()
