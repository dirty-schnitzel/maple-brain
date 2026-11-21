"""Prototype: the weather clouds FOLLOWED over time (what the live path would do), end to end.

Per frame (CloudTracker.step):
 1. every followed cloud that should be on screen: its place = its last place + its speed x dt, checked +-R px by the
    exact model on sample pixels (fastpipe.FastClouds.step, one batch); not confirmed -> it coasts on its speed
    (over near-white scenery or the UI a cloud cannot be checked) and is dropped only when the frame shows the scene
    where it should be;
 2. the clouds as one layer -> the expected picture with clouds;
 3. NEW clouds only when the frame is still whitened somewhere no followed cloud explains (a count of such pixels):
    the COARSE finder - a^ and the 7 pictures at 1/4 size, masked SSD by FFT - names (picture, place +-3 px), the
    exact model at full size around it decides (opacity = the median of the per-sample ratios);
 4. the frame with the clouds undone.
    python cloudtrack.py CAP [--fit]     -> the frame = expected share, clouds followed, finder runs, ms per part"""
import argparse
import json
import time

import numpy as np
import torch

import clouds as cl
import fastexp
import fastpipe
import msl
import proto

SW, PLAY_H = 1366, 700
S = 4                                # the coarse finder's scale


class CoarseFinder:
    def __init__(self, cf):
        self.cf, self.dev = cf, cf.dev
        pool = torch.nn.functional.avg_pool2d
        self.sp = []
        for s, a in cf.sprites:
            h, w = a.shape
            ap = torch.nn.functional.pad(a, (0, (-w) % S, 0, (-h) % S))
            self.sp.append(pool(ap[None, None], S)[0, 0])
        self.mh = max(a.shape[0] for a in self.sp)
        self.mw = max(a.shape[1] for a in self.sp)
        self.h, self.w = PLAY_H // S, (SW + S - 1) // S
        self.PH, self.PW = self.h + 2 * self.mh, self.w + 2 * self.mw
        self.FH, self.FW = 320, 648
        assert self.FH >= self.PH + self.mh and self.FW >= self.PW + self.mw, (self.PH, self.PW, self.mh, self.mw)
        self.K = []
        for a in self.sp:
            h, w = a.shape
            ka, k2, k1 = (torch.zeros((self.FH, self.FW), device=self.dev) for _ in range(3))
            ka[:h, :w], k2[:h, :w], k1[:h, :w] = a, a * a, 1
            self.K.append(tuple(torch.fft.rfft2(x).conj() for x in (ka, k2, k1)) + (float((a * a).sum()),))

    def find(self, ah, usable, vis_min=0.15, ratio_max=0.6, top=3):
        """-> [(ratio, k, x, y)] full-size screen places of the best coarse matches (up to `top` per picture)."""
        pool = torch.nn.functional.avg_pool2d
        pad_w = (-SW) % S
        m = pool(torch.nn.functional.pad(usable.float(), (0, pad_w))[None, None], S)[0, 0]
        ma = pool(torch.nn.functional.pad(ah * usable, (0, pad_w))[None, None], S)[0, 0]
        mean = ma / m.clamp(min=1e-3)                                   # the usable pixels' mean a^ per cell
        w = (m > 0.3).float()
        A, A2 = mean * w, mean * mean * w
        padf = lambda x: torch.nn.functional.pad(x, (self.mw, self.FW - x.shape[1] - self.mw, self.mh, self.FH - x.shape[0] - self.mh))
        Fm, Fa, Fa2 = (torch.fft.rfft2(padf(x)) for x in (w, A, A2))
        out = []
        for k, (ka, k2, k1, e) in enumerate(self.K):
            t1 = torch.fft.irfft2(Fa2 * k1, s=(self.FH, self.FW))
            t2 = torch.fft.irfft2(Fa * ka, s=(self.FH, self.FW))
            t3 = torch.fft.irfft2(Fm * k2, s=(self.FH, self.FW))
            ratio = ((t1 - 2 * t2 + t3) / t3.clamp(min=1e-3))[:self.PH, :self.PW]
            vis = t3[:self.PH, :self.PW] / e
            r = torch.where(vis >= vis_min, ratio, torch.full_like(ratio, 9.0))
            for _ in range(top):
                v, at = r.flatten().min(dim=0)
                if float(v) > ratio_max:
                    break
                y, x = int(at) // self.PW, int(at) % self.PW
                out.append((float(v), k, (x - self.mw) * S, (y - self.mh) * S))
                r[max(0, y - 4):y + 5, max(0, x - 4):x + 5] = 9.0
        return sorted(out)


class CloudTracker:
    def __init__(self, cf, fc, near_new=14, near=2, trig=1200, gap=0.2):
        self.cf, self.fc, self.dev = cf, fc, cf.dev
        self.coarse = CoarseFinder(cf)
        self.tracks = []
        self.near_new, self.near, self.trig, self.gap = near_new, near, trig, gap
        self.last_find = -1e9
        self.ms = {}
        self.n_find = 0
        self.next_id = 0

    def _check(self, f, E, valid, trs, C, t, r):
        """The batched look at tracks `trs` within r px of their predicted places -> [(x, y, share, n)]."""
        fc = self.fc
        d = torch.arange(-r, r + 1, device=self.dev)
        fc.dx, fc.dy = [x.reshape(-1) for x in torch.meshgrid(d, d, indexing="xy")]
        k = torch.tensor([tr["k"] for tr in trs], device=self.dev)
        x = torch.tensor([int(round(tr["mx"] + tr["vx"] * (t - tr["t"]))) - C[0] for tr in trs], device=self.dev)
        y = torch.tensor([int(round(tr["my"] + tr["vy"] * (t - tr["t"]))) - C[1] for tr in trs], device=self.dev)
        o = torch.tensor([tr["o"] for tr in trs], device=self.dev)
        bx, by, sh, n = fc.step(f, E, valid, k, x, y, o)
        return bx.tolist(), by.tolist(), sh.tolist(), n.tolist()

    def _new(self, f, E2, valid, k, x, y, r=5):
        """A coarse candidate checked at full size: the best place within r px with the opacity from the samples'
        ratios -> (share, n, o, x, y)."""
        fc = self.fc
        d = torch.arange(-r, r + 1, device=self.dev)
        dx, dy = [v.reshape(-1) for v in torch.meshgrid(d, d, indexing="xy")]
        sx = x + dx[:, None] + fc.px[k][None, :]                              # (K, N)
        sy = y + dy[:, None] + fc.py[k][None, :]
        ok = (sx >= 0) & (sx < SW) & (sy >= 0) & (sy < PLAY_H)
        sxc, syc = sx.clamp(0, SW - 1), sy.clamp(0, PLAY_H - 1)
        Ff, Ee = f[syc, sxc].float(), E2[syc, sxc].float()
        ok &= valid[syc, sxc]
        q = fc.a[k][None, :, None] * (fc.col[k][None] - Ee)                   # the change at opacity 1
        rr = Ff - Ee
        qq = (q * q).sum(dim=2)
        use = ok & (q.abs().amax(dim=2) > 16)
        ratio = torch.where(use, (rr * q).sum(dim=2) / qq.clamp(min=1e-6), torch.full_like(qq, float("nan")))
        o = torch.nanmedian(ratio, dim=1).values.clamp(0, 1)                  # (K,)
        o = torch.nan_to_num(o, nan=0.0)
        pred = o[:, None, None] * q
        inf = ok & (pred.abs().amax(dim=2) > 8)
        hit = inf & ((rr - pred).abs().amax(dim=2) <= 4)
        n = inf.sum(dim=1)
        share = hit.sum(dim=1).float() / n.clamp(min=1)
        share = torch.where((o >= 0.3) & (n >= 300), share, torch.zeros_like(share))
        b = int(share.argmax())
        return float(share[b]), int(n[b]), float(o[b]), x + int(dx[b]), y + int(dy[b])

    def step(self, f, E, valid, C, t):
        """-> (P, A (the cloud layer), E2 the expected picture with clouds, [tracks on screen])."""
        sync = torch.cuda.synchronize
        fc, cf = self.fc, self.cf
        t0 = time.perf_counter()
        on = []
        for tr in self.tracks:
            h, w = cf.sprites[tr["k"]][1].shape
            px = tr["mx"] + tr["vx"] * (t - tr["t"]) - C[0]
            py = tr["my"] + tr["vy"] * (t - tr["t"]) - C[1]
            if px + w > -20 and px < SW + 20 and py + h > -20 and py < PLAY_H + 20:
                on.append(tr)
        for group, r in (([tr for tr in on if tr["n"] >= 2], self.near), ([tr for tr in on if tr["n"] < 2], self.near_new)):
            if not group:
                continue
            bx, by, sh, n = self._check(f, E, valid, group, C, t, r)
            for tr, x, y, s, nn in zip(group, bx, by, sh, n):
                tr["share"], tr["ninf"] = s, nn
                if s >= 0.5 and nn >= 150:
                    mx, my = x + C[0], y + C[1]
                    if tr["n"] >= 1 and t - tr["t0"] > 0.05:
                        tr["vx"] = (mx - tr["x0"]) / (t - tr["t0"])
                        tr["vy"] = (my - tr["y0"]) / (t - tr["t0"])
                    tr["mx"], tr["my"], tr["t"] = mx, my, t
                    tr["n"] += 1
                    tr["miss"] = 0
                elif nn >= 400 and s < 0.15:
                    tr["miss"] += 1                      # the frame shows something else where it should be
        self.tracks = [tr for tr in self.tracks if tr["miss"] < 3 and t - tr["t"] < 240]
        on = [tr for tr in on if tr["miss"] < 3]
        sync(); t1 = time.perf_counter()

        def lay():
            return fc.layer([(tr["k"], int(round(tr["mx"] + tr["vx"] * (t - tr["t"]))) - C[0],
                              int(round(tr["my"] + tr["vy"] * (t - tr["t"]))) - C[1], tr["o"]) for tr in on])
        P, A = lay()
        E2 = E * (1 - A) + P
        sync(); t2 = time.perf_counter()
        ff = f.float()
        ah, usable = cf.alpha_hat(ff, E2.float(), valid)
        n_res = int(((ah > 0.1) & usable).sum())
        sync(); t3 = time.perf_counter()
        t_find = 0.0
        if n_res > self.trig and t - self.last_find >= self.gap:
            self.last_find = t
            self.n_find += 1
            added = 0
            for ratio, k, x, y in self.coarse.find(ah, usable):
                if any(tr["k"] == k and abs(tr["mx"] + tr["vx"] * (t - tr["t"]) - C[0] - x) < 12 and abs(tr["my"] - C[1] - y) < 12 for tr in on):
                    continue
                share, n, o, bx, by = self._new(f, E2.float(), valid, k, x, y)
                if share >= 0.6 and n >= 300:
                    tr = {"id": self.next_id, "k": k, "mx": bx + C[0], "my": by + C[1], "vx": 0.0, "vy": 0.0, "o": o, "t": t,
                          "t0": t, "x0": bx + C[0], "y0": by + C[1], "n": 1, "miss": 0, "share": share, "ninf": n}
                    self.next_id += 1
                    self.tracks.append(tr)
                    on.append(tr)
                    added += 1
                    P, A = lay()
                    E2 = E * (1 - A) + P
            sync()
            t_find = time.perf_counter() - t3
        t4 = time.perf_counter()
        self.ms = {"follow": 1000 * (t1 - t0), "layer": 1000 * (t2 - t1), "residue": 1000 * (t3 - t2), "find": 1000 * t_find}
        return P, A, E2, on, n_res


def main():
    import cam as camlib
    from maplebrain.perception import hud
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--tolvote", action="store_true")
    ap.add_argument("--show", default="")
    ap.add_argument("--tag", default="ct")
    a = ap.parse_args()
    msl.guard()
    c = msl.clip(a.cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(a.cap)["rows"] if r[3] is not None]
    ms = proto.MScene(c.map_id)
    fs = fastexp.FastScene(ms)
    cf = cl.CloudFinder(ms.dev)
    fc = fastpipe.FastClouds(cf)
    ct = CloudTracker(cf, fc)
    fz = None
    if a.fit:
        from maplebrain.perception.fit import Fitter
        fz = Fitter(ms.scene, c.map_id, msl.ROOT / "assets" / "mcw")
        import cloudvote
        cvote = cloudvote.CloudVote(fz.voter)
        fz.voter.ids = cvote.ids
    ui = None
    show = {int(x) for x in a.show.split(",") if x}
    rows = []
    T = {}
    nmob = 0
    keep = []
    n_new = n_gone = 0
    newk = []
    for r in cams:
        i = r[0]
        n, name, t = fr[i]
        img = c.read(name)
        if ui is None:
            m = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
            m = m.copy()
            x0, y0, x1, y1 = hud.CHAT_WORLD
            m[y0:y1, x0:x1] = True
            ui = torch.from_numpy(np.ascontiguousarray(m[:700])).to(ms.dev)
        f = proto.frame_tensor(img, ms.dev)
        C = (r[3], r[4])
        ms.locate(f, C, t)
        E1, known = ms.expected(C)
        valid = known & ui
        P, A, E2, on, n_res = ct.step(f, E1.half(), valid, C, t)
        for k, v in ct.ms.items():
            T.setdefault(k, []).append(v)
        d1 = (f.float() - E1).abs().amax(dim=2)
        d2 = (f.float() - E2.float()).abs().amax(dim=2)
        world = int(valid.sum())
        row = {"i": i, "t": t, "shows1": float(((d1 <= 4) & valid).sum()) / world, "shows2": float(((d2 <= 4) & valid).sum()) / world,
               "on": len(on), "tracks": len(ct.tracks), "res": n_res, "find": ct.ms["find"] > 0,
               "clouds": [[tr["id"], tr["k"], tr["mx"], tr["my"], tr["o"], tr["share"], tr["n"]] for tr in on]}
        if fz is not None:
            f2, thick = fc.undo(f, P, A)
            plain = fz.fit(f2, C, E1, known & ~thick, ui)
            mobs = plain
            if a.tolvote:
                cvote.A = A[..., 0].float()
                mobs = fz.fit(f2, C, E1, known & ~thick, ui)
                cvote.A = None
                new = [mb for mb in mobs if not any(q.type == mb.type and abs(q.feet[0] - mb.feet[0]) <= 6 and abs(q.feet[1] - mb.feet[1]) <= 6 for q in plain)]
                gone = [q for q in plain if not any(q.type == mb.type and abs(q.feet[0] - mb.feet[0]) <= 6 and abs(q.feet[1] - mb.feet[1]) <= 6 for mb in mobs)]
                n_new += len(new)
                n_gone += len(gone)
                for mb in new:
                    pz = fz.poses[fz.pose_ix[(mb.type, mb.pose, mb.facing)]]
                    hh, ww = pz.pic.shape[:2]
                    bx0, by0 = mb.feet[0] - pz.ox, mb.feet[1] - pz.oy
                    x0, y0 = max(0, min(SW - 200, mb.feet[0] - 100)), max(0, min(PLAY_H - 150, mb.feet[1] - 110))
                    newk.append((float(A[max(0, by0):max(1, by0 + hh), max(0, bx0):max(1, bx0 + ww), 0].float().mean()), i, mb.type, mb.pose, mb.opacity, mb.n_seen,
                                 (bx0 - x0, by0 - y0, ww, hh), img[y0:y0 + 150, x0:x0 + 200].copy(), f2[y0:y0 + 150, x0:x0 + 200].cpu().numpy()))
            row["mobs"] = len(mobs)
            nmob += len(mobs)
            Af = A[..., 0].float()
            for mb in mobs:
                pz = fz.poses[fz.pose_ix[(mb.type, mb.pose, mb.facing)]]
                hh, ww = pz.pic.shape[:2]
                bx0, by0 = mb.feet[0] - pz.ox, mb.feet[1] - pz.oy
                sub = Af[max(0, by0):max(0, by0 + hh), max(0, bx0):max(0, bx0 + ww)]
                u = float(sub.mean()) if sub.numel() else 0.0
                x0, y0 = max(0, min(SW - 200, mb.feet[0] - 100)), max(0, min(PLAY_H - 150, mb.feet[1] - 110))
                keep.append((u, i, mb.type, mb.pose, mb.opacity, mb.n_seen, (bx0 - x0, by0 - y0, ww, hh),
                             img[y0:y0 + 150, x0:x0 + 200].copy(), f2[y0:y0 + 150, x0:x0 + 200].cpu().numpy()))
        rows.append(row)
        if i in show:
            import cv2
            vis = img[:700].copy()
            b = ((d2 > 4) & valid).cpu().numpy()
            kn = valid.cpu().numpy()
            cv_ = A[..., 0].float().cpu().numpy()
            dm = np.zeros_like(vis)
            dm[b] = (0, 0, 255)
            dm[~kn] = (255, 128, 0)
            over = (0.45 * vis + 0.55 * dm).astype(np.uint8)
            over[~b & kn] = (vis[~b & kn] * 0.35).astype(np.uint8)
            g = (cv_ > 0.02) & ~b & kn
            over[g] = (0.6 * over[g] + 0.4 * np.array([0, 160, 0]) * cv_[g][:, None]).astype(np.uint8)
            for tr in on:
                cv2.putText(over, f"#{tr['id']} c{tr['k']} {tr['share']:.2f}", (max(0, int(tr['mx'] - C[0])) + 4, max(12, int(tr['my'] - C[1]) + 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            msl.save(f"{a.tag}_{i}_sheet.png", msl.tile([img[:700], over], cols=1, scale=0.6, labels=["frame", "red = off, green = explained through a cloud, blue = unknown"]))
    g = lambda k: np.array([r[k] for r in rows])
    dur = rows[-1]["t"] - rows[0]["t"]
    print(f"{a.cap}: {len(rows)} frames over {dur:.0f} s")
    print(f"  frame = expected: {100 * g('shows1').mean():.1f} % of the known play area with the movers, {100 * g('shows2').mean():.1f} % with the "
          f"followed clouds (p10 {100 * np.percentile(g('shows2'), 10):.1f}); first 5 s: {100 * np.mean([r['shows2'] for r in rows if r['t'] - rows[0]['t'] < 5]):.1f} %, after: "
          f"{100 * np.mean([r['shows2'] for r in rows if r['t'] - rows[0]['t'] >= 5]):.1f} %")
    print(f"  clouds on screen p50 {np.median(g('on')):.0f} max {g('on').max()}; tracks made {ct.next_id}; finder runs {ct.n_find} "
          f"({ct.n_find / dur:.2f} a second; on {100 * g('find').mean():.0f} % of these frames)")
    for k, v in T.items():
        v = np.array(v)
        nz = v[v > 0]
        print(f"  ms {k:8s} p50 {np.median(v):.2f}  p90 {np.percentile(v, 90):.2f}" + (f"   (when run: p50 {np.median(nz):.1f} p90 {np.percentile(nz, 90):.1f} max {nz.max():.1f}, n {len(nz)})" if k == "find" and len(nz) else ""))
    if fz is not None:
        print(f"  mobs the fit finds with the followed clouds undone: {nmob}")
    (msl.OUT / f"cloudtrack_{a.tag}.json").write_text(json.dumps(rows))
    if a.tolvote:
        print(f"  the tolerant vote under clouds: {n_new} mobs more than the plain undo, {n_gone} fewer")
    if keep:
        import cv2
        import random
        rnd = random.Random(1)
        under = [k for k in keep if k[0] >= 0.2]
        print(f"  mobs under a cloud (mean alpha over their box >= 0.2): {len(under)}; >= 0.4: {sum(k[0] >= 0.4 for k in keep)}; >= 0.6: {sum(k[0] >= 0.6 for k in keep)}")
        for nm, pool in (("under", under), ("any", keep), ("tolnew", newk)):
            if not pool:
                continue
            pick = rnd.sample(pool, min(40, len(pool)))
            tiles = []
            for u, i, typ, pose, op, ns, (bx, by, bw, bh), raw, und in pick:
                for im_ in (raw, und):
                    cv2.rectangle(im_, (bx, by), (bx + bw, by + bh), (0, 255, 0), 1)
                t_ = np.hstack([raw, und])
                cv2.putText(t_, f"fr {i} t{typ} {pose} a{u:.2f} o{op} s{ns}", (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 3)
                cv2.putText(t_, f"fr {i} t{typ} {pose} a{u:.2f} o{op} s{ns}", (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
                tiles.append(t_)
            for s0 in range(0, len(tiles), 20):
                part = tiles[s0:s0 + 20]
                while len(part) % 4:
                    part.append(np.zeros_like(part[0]))
                sheet = np.vstack([np.hstack(part[r_:r_ + 4]) for r_ in range(0, len(part), 4)])
                print("  sheet (frame | clouds undone):", msl.save(f"{a.tag}_mobs_{nm}_{s0 // 20}.png", sheet).name)


if __name__ == "__main__":
    main()
