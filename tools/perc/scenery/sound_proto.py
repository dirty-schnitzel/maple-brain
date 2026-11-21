"""Is perception sound with the prototype's expected picture? sound.py's `model` share (PLAN-data's stop rule as
REPORT-track-before.md section 3 reads it), computed the same way for today's Scene.expected and the prototype's.
    python sound_proto.py CAP [CAP ...] [--every K]
Per capture: raw % (frame = expected, of the known world pixels) and model % (1 - the pixels of map places that are
unexplained on more than half of the frames showing them / all world pixels), before -> after; the known share."""
import argparse
import json

import numpy as np
import torch

import cam as camlib
import msl
import proto

CELL, MIN_F = 4, 10
SW, H = 1366, 700


class Cells:
    def __init__(self, Cs):
        self.hb, self.wb = H // CELL, SW // CELL
        self.ox, self.oy = int(Cs[:, 0].min()) // CELL - 1, int(Cs[:, 1].min()) // CELL - 1
        self.gw = int(Cs[:, 0].max()) // CELL - self.ox + self.wb + 2
        self.gh = int(Cs[:, 1].max()) // CELL - self.oy + self.hb + 2
        self.U, self.W, self.F = (torch.zeros(self.gh * self.gw, dtype=torch.float64) for _ in range(3))
        self.raw = []

    def add(self, shows, world, C):
        ws = world[:self.hb * CELL, :self.wb * CELL].reshape(self.hb, CELL, self.wb, CELL).sum((1, 3)).double().cpu()
        us = (world & ~shows)[:self.hb * CELL, :self.wb * CELL].reshape(self.hb, CELL, self.wb, CELL).sum((1, 3)).double().cpu()
        by, bx = torch.meshgrid(torch.arange(self.hb), torch.arange(self.wb), indexing="ij")
        idx = ((by + int(C[1]) // CELL - self.oy) * self.gw + (bx + int(C[0]) // CELL - self.ox)).reshape(-1)
        self.W.index_add_(0, idx, ws.reshape(-1))
        self.U.index_add_(0, idx, us.reshape(-1))
        self.F.index_add_(0, idx, (ws > 0).double().reshape(-1))
        self.raw.append(float(shows.sum()) / max(1, float(world.sum())))

    def model(self):
        miss = (self.F >= MIN_F) & (self.U > 0.5 * self.W)
        return 1 - float(self.U[miss].sum()) / max(1.0, float(self.W.sum())), int(miss.sum()) * CELL * CELL


def run(cap, every=3):
    msl.guard()
    from maplebrain.perception import hud
    c = msl.clip(cap)
    fr = c.frames()
    cams = [r for r in camlib.cams(cap)["rows"] if r[3] is not None]
    Cs = np.array([[r[3], r[4]] for r in cams])
    ms = proto.MScene(c.map_id)
    old = msl.scene_of(c.map_id)
    a, b = Cells(Cs), Cells(Cs)
    ui = None
    kn = []
    todo = cams if ms.movers else cams[::every]            # movers are followed frame by frame
    for j, r in enumerate(todo):
        i = r[0]
        n, name, t = fr[i]
        img = c.read(name)
        if ui is None:
            m = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
            x0, y0, x1, y1 = hud.CHAT_WORLD
            m = m.copy()
            m[y0:y1, x0:x1] = True
            ui = torch.from_numpy(np.ascontiguousarray(m[:H])).to(ms.dev)
        f = proto.frame_tensor(img, ms.dev)
        C = (r[3], r[4])
        if ms.movers:
            ms.locate(f, C, t)
            if j % every:
                continue
        ff = f.float()
        e0, k0 = old.expected(C)
        w0 = k0 & ui
        a.add(w0 & ((ff - e0).abs().amax(dim=2) <= 4), w0, C)
        e1, k1 = ms.expected(C)
        w1 = k1 & ui
        b.add(w1 & ((ff - e1).abs().amax(dim=2) <= 4), w1, C)
        kn.append((float(w0.sum()) / float(ui.sum()), float(w1.sum()) / float(ui.sum())))
    ma, mb = a.model(), b.model()
    kn = np.array(kn)
    out = {"cap": cap, "map": c.map_id, "frames": len(a.raw), "raw0": float(np.mean(a.raw)), "raw1": float(np.mean(b.raw)),
           "model0": ma[0], "model1": mb[0], "miss_px0": ma[1], "miss_px1": mb[1], "known0": float(kn[:, 0].mean()),
           "known1": float(kn[:, 1].mean()), "movers": len(ms.movers), "additive": len(ms.additive)}
    print(f"{cap:22s} map {c.map_id} {out['frames']:5d} fr  known {100 * out['known0']:5.1f} -> {100 * out['known1']:5.1f} %   raw "
          f"{100 * out['raw0']:5.1f} -> {100 * out['raw1']:5.1f} %   model {100 * out['model0']:5.1f} -> {100 * out['model1']:5.1f} %   "
          f"(movers {out['movers']}, additive {out['additive']})  {'SOUND' if out['model1'] >= 0.95 else 'not sound'}", flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    res = [run(cap, a.every) for cap in a.caps]
    if a.json:
        (msl.OUT / a.json).write_text(json.dumps(res, indent=1))
