"""Synthetic drop frames with exact truth (PLAN-loot.md S3, section 7.2). Tools only: nothing on the live path.

    python tools/loot/synth_drops.py OUT [--seed 1] [--cat-n 24] [--per-case 25] [--free 50]      (the full set)
    python tools/loot/synth_drops.py tests/fixtures/synth_drops --fixture [--seed 7]                 (40 frames, pytest)

Base = a saved frame of a native recording at the plan session's registered camera (RUN/loot/find_v4.jsonl `cam`)
with every moving thing ERASED: each blob of D = |frame - expected scene| > 4 that is not our character's (the blob
at obs.me) and lies in the world (lootlib.world_mask: the measured minimap, the chat rect as world) is replaced by the
expected scene - mobs, other players, effects and the real drops go. Frames whose find_v4 row has a drop at our body
are not used (a drop merged into our kept blob would stay). Maps: Ant Tunnel IV, Dangerous Steam, Line 1, Transfer
Area (front scenery on the last three).
Drawn as the client draws it (tools/perc/synth/synth.py): a drop = the item's iconRaw (assets/mcw/items, the picture
class's own picture), straight alpha, integer position, its bottom 1..5 px below the foothold's y at the picture's
centre x minus a bob offset 0..6 (box bottom - foothold in -5..+5), on the foothold's layer: the tiles / objects of
the layers above re-drawn over it; a later drop over an earlier one. Cases (one a frame):
  cat      24 clear drops on footholds, the catalogue in order: every picture that can drop once (not cash-only:
           cash-shop items never drop; weak ones too)
  pile     piles of 2-4 drops 14-30 px apart on one foothold (the later over the earlier)
  mob      drops over mobs of the map (drawn as the mob synth does), player: over players (our character cut from
           other frames of the run, D blob at obs.me)
  effect   damage digits (the client's BasicEff NoRed) over each drop, ui: drops partly under the quickslots /
           minimap (the base's own UI pixels re-drawn), edge: drops at the screen's left / right edge
  flight   mesos and items in the air above a foothold (box bottom 12-100 px above it): truth kind "air" (no AIR
           kind since 2026-11-17: they must not read REST)
  window   NOT drops: item `icon` pictures (cash items too) (tools/loot/export_items.ps1's ItemDraft) on an inventory-like panel (slot
           colours of the real one, 012059_1 t 85.4) anywhere on the play area; count digits not drawn (harder)
  worn     NOT drops: an equip picture on a player's head, a band of 35-70 % of it hidden by the player again
  mobpart  NOT drops: Stirges (their wing = the Stirge Wing item's pixels; Dangerous Steam / Transfer Area only)
  free     no drops: mobs, players, damage digits only
Truth per drop (synth.json, by construction): g (the picture in items.npz), item + f (its class), box, feet (box
bottom-centre: x + w // 2, y + h), kind rest / air, cls, bob, dy (box bottom - foothold y), fh, layer, onscreen, vis
(= share of its on-screen opaque pixels the final frame shows within +-4: SEEN by definition; front = share under
the front scenery of its layer); not-drops: cls, box, item / g. Plus per frame: case, run, map, base frame, C, me,
chars (character body boxes: ours + pasted players), mobs / players drawn, window (fixture: the stored crop).
--fixture: 40 frames (cat 6, free 4, the other 10 cases 3 each), every case inside one window (<= 440 x 300) stored as
crops: frames/NNNNNN.webp (lossless) + exp/NNNNNN.webp (the expected scene, rounded) + masks.npz (known, world, front
per layer, packed bits) so tests need neither the scene build nor the export.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "synth"))
from lootlib import Items as DraftItems, run_ticks, world_mask, PLAY_H, SW  # noqa: E402
import synth as ms  # noqa: E402  (tools/perc/synth/synth.py: the mob synth's drawing)

RUNS = {"ant4": "runs/play/20261116_154819_1", "steam": "runs/play/20261116_084844_2",
        "line1": "runs/play/20261116_085108_3", "transfer": "runs/play/20261116_085215_4"}
STIRGE = 17           # Dangerous Steam / Transfer Area flyer; its wing shares the Stirge Wing item's pixels
TOL = 4
SLOT, GAP, EDGE = (213, 223, 225), (247, 246, 245), (190, 201, 206)     # the inventory's slot colours (BGR)
CASES = ("cat", "pile", "mob", "player", "effect", "ui", "edge", "flight", "window", "worn", "mobpart", "free")
EQUIP = ("Accessory", "Cap", "Cape", "Coat", "Glove", "Longcoat", "Pants", "Ring", "Shield", "Shoes", "Weapon")


class Map:
    """One base recording: scene, footholds, mob sprites, front planes, players cut from it, its usable frames."""

    def __init__(self, key: str):
        from maplebrain.gamedata import EXPORT
        from maplebrain.scene import Scene
        self.key, self.run = key, ROOT / RUNS[key]
        self.map_id = ms.rec.map_of(self.run)
        self.scene = Scene.load(self.map_id)
        self.map = json.loads((ms.MAPS / str(self.map_id) / "map.json").read_text(encoding="utf-8"))
        self.fh = [f for f in self.map["footholds"].values() if f["x1"] != f["x2"]]
        self.types = sorted({s["id"] for s in self.map["mobs"]})
        self.sprites = {t: ms.load_sprites(t) for t in self.types}
        self.front = ms.front_planes(self.map_id, sorted({f["layerId"] for f in self.fh}), EXPORT)
        self.digits = ms.load_digits(EXPORT)
        self.world = world_mask(self.map_id, (768, SW, 3))
        me = {k["frame"]: k["me"] for k in run_ticks(self.run)}
        self.rows = []
        for line in open(self.run / "loot" / "find_v4.jsonl", encoding="utf-8"):
            r = json.loads(line)
            if r.get("cam") is None or r.get("drops") is None:
                continue
            r["me"] = me.get(r["frame"])
            if r["me"] and any(_overlap(d["box"], body_box(r["me"]), 12) for d in r["drops"]):
                continue                                # a real drop at our body would stay in our kept blob
            self.rows.append(r)
        self._players = None

    # synth.Synth's drawing helpers read these
    fa_at = ms.Synth.fa_at

    def base(self, r) -> "ms.Base | None":
        """The row's frame with every world D blob but ours replaced by the expected scene."""
        import torch
        frame = ms.rec.read(self.run, r["frame"])
        if frame is None:
            return None
        C = tuple(r["cam"])
        e, known = self.scene.expected(C)
        e = e.clamp(0, 255).round().to(torch.uint8).cpu().numpy()
        known = known.cpu().numpy()
        diff = (np.abs(frame[:PLAY_H].astype(np.int16) - e).max(axis=2) > TOL) & known
        ui = ~self.world
        core = cv2.erode((diff & ~ui).astype(np.uint8), np.ones((3, 3), np.uint8))
        blob = cv2.dilate(core, np.ones((13, 13), np.uint8))
        nc, lab, st, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
        pb = body_box(r["me"]) if r["me"] else None
        out, keep, dontcare = frame.copy(), np.zeros((PLAY_H, SW), bool), []
        grow = cv2.dilate(diff.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        for i in range(1, nc):
            x, y, w, h, _ = (int(v) for v in st[i])
            comp = lab == i
            if pb is not None and x < pb[2] and x + w > pb[0] and y < pb[3] and y + h > pb[1]:
                keep |= comp
                dontcare.append([x - 10, y - 10, x + w + 10, y + h + 10])
            else:
                m = comp & grow & ~ui
                out[:PLAY_H][m] = e[m]
        # the real frame's drops (the plan session's sightings, find_v4): a blob chain can join one to our kept
        # blob (they lie 60-200 px from us) - erase each box's changed pixels; one on unknown scenery = no base
        raw_diff = np.abs(frame[:PLAY_H].astype(np.int16) - e).max(axis=2) > TOL
        for d in r["drops"]:
            x, y, w, h = d["box"]
            a0, b0, a1, b1 = max(0, x - 2), max(0, y - 2), min(SW, x + w + 2), min(PLAY_H, y + h + 2)
            if a1 <= a0 or b1 <= b0 or not self.world[b0:b1, a0:a1].any():
                continue
            if not known[b0:b1, a0:a1].all():
                return None
            m = raw_diff[b0:b1, a0:a1] & self.world[b0:b1, a0:a1]
            out[b0:b1, a0:a1][m] = e[b0:b1, a0:a1][m]
            keep[b0:b1, a0:a1] &= ~m
        ui_alpha = (ui & diff).astype(np.float32)
        b = ms.Base(r["frame"], out, C, e, diff, keep, ui_alpha, dontcare, [], [])
        b.known, b.me = known, r["me"]
        return b

    def players(self) -> list:
        """[(BGRA, anchor = obs.me inside it)]: our D blob cut from frames with no drop / mob sighting near us."""
        if self._players is not None:
            return self._players
        out = []
        for r in self.rows[::7]:
            me = r["me"]
            if not me or any(abs(d["box"][0] - me[0]) < 140 and abs(d["box"][1] - me[1]) < 140 for d in r["drops"]):
                continue
            b = self.base(r)
            if b is None:
                continue
            frame = ms.rec.read(self.run, r["frame"])
            m = cv2.morphologyEx((b.keep & b.diff).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
            ys, xs = np.nonzero(m)
            if len(xs) < 400 or xs.min() <= 0 or xs.max() >= SW - 1 or ys.min() <= 0 or ys.max() >= PLAY_H - 1:
                continue
            x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
            if x1 - x0 > 140 or y1 - y0 > 120:
                continue
            out.append((np.dstack([frame[y0:y1, x0:x1], m[y0:y1, x0:x1].astype(np.uint8) * 255]),
                        (int(me[0] - x0), int(me[1] - y0))))
            if len(out) >= 16:
                break
        self._players = out
        return out

    def fh_y(self, f, x: float) -> float:
        return f["y1"] + (x - f["x1"]) * (f["y2"] - f["y1"]) / (f["x2"] - f["x1"])

    def point(self, C, rng, sx=(0, SW), sy=(30, PLAY_H), fh=None):
        """(map x, foothold) on a foothold whose screen x lies in sx and screen y in sy, length-weighted."""
        cand, lens = [], []
        for f in ([fh] if fh is not None else self.fh):
            a, b = sorted((f["x1"] - C[0], f["x2"] - C[0]))
            a, b = max(a, sx[0]), min(b, sx[1])
            ym = (f["y1"] + f["y2"]) / 2 - C[1]
            if b - a >= 2 and sy[0] <= ym < sy[1]:
                cand.append((f, a, b))
                lens.append(b - a)
        if not cand:
            return None
        f, a, b = cand[rng.choice(len(cand), p=np.array(lens) / sum(lens))]
        return rng.uniform(a, b) + C[0], f


def body_box(me):
    return (me[0] - 42, me[1] - 90, me[0] + 42, me[1] + 22)


def _overlap(box, b2, m=0) -> bool:
    x, y, w, h = box
    return x < b2[2] + m and x + w > b2[0] - m and y < b2[3] + m and y + h > b2[1] - m


class Frame:
    """The frame being built + its truth."""

    def __init__(self, mp: Map, base, case: str, window=None):
        self.mp, self.base, self.case = mp, base, case
        self.img = base.frame[:PLAY_H].copy()
        self.full = base.frame
        self.window = window            # (x0, y0, x1, y1): everything goes inside (fixture)
        self.drops, self.notdrops, self.mobs, self.players = [], [], [], []
        self.busy = np.zeros((PLAY_H, SW), bool)              # boxes used (+ margin)
        self.busy |= base.keep
        self.busy |= ~mp.world[:PLAY_H]
        self.chars = [list(body_box(base.me))] if base.me else []

    def inside(self, x, y, w, h) -> bool:
        if self.window is None:
            return True
        x0, y0, x1, y1 = self.window
        x0, x1 = (-10 ** 6 if x0 <= 0 else x0), (10 ** 6 if x1 >= SW else x1)    # a window at the screen's side
        return x >= x0 and y >= y0 and x + w <= x1 and y + h <= y1

    def free(self, x, y, w, h, m=4) -> bool:
        a0, b0, a1, b1 = max(0, x - m), max(0, y - m), min(SW, x + w + m), min(PLAY_H, y + h + m)
        return a1 > a0 and b1 > b0 and not self.busy[b0:b1, a0:a1].any()

    def take(self, x, y, w, h, m=4):
        self.busy[max(0, y - m):max(0, y + h + m), max(0, x - m):max(0, x + w + m)] = True

    def draw(self, pic, x: int, y: int, layer=None) -> np.ndarray:
        """`pic` (BGRA straight alpha) at (x, y); on `layer`: the layers above re-drawn over it -> the front alpha
        over its box (h, w)."""
        h, w = pic.shape[:2]
        r = ms._clip(x, y, w, h)
        fa_box = np.zeros((h, w), np.float32)
        if r is None:
            return fa_box
        x0, y0, x1, y1, sx, sy = r
        S = pic[sy:sy + y1 - y0, sx:sx + x1 - x0].astype(np.float32)
        a = S[..., 3:4] / 255.0
        src = self.img[y0:y1, x0:x1].astype(np.float32)
        if layer is not None and layer in self.mp.front:
            F = self.mp.fa_at(layer, self.base.C, x0, y0, x1 - x0, y1 - y0)
            fa = F[..., 3:4] / 255.0
            behind = np.where(fa < 0.995, (src - F[..., :3]) / np.maximum(1 - fa, 1e-3), src)
            out = F[..., :3] + (1 - fa) * (a * S[..., :3] + (1 - a) * behind)
            fa_box[sy:sy + y1 - y0, sx:sx + x1 - x0] = fa[..., 0]
        else:
            out = a * S[..., :3] + (1 - a) * src
        self.img[y0:y1, x0:x1] = np.clip(out + 0.5, 0, 255).astype(np.uint8)
        return fa_box

    def add_drop(self, items, g: int, x: int, y: int, kind: str, cls: str, layer=None, **kw) -> dict:
        pic = items.pics[g]
        fa = self.draw(pic, x, y, layer)
        h, w = pic.shape[:2]
        d = {"g": int(g), "item": int(items.item[g]), "f": int(items.f[g]), "box": [int(x), int(y), int(w), int(h)],
             "feet": [int(x + w // 2), int(y + h)], "kind": kind, "cls": cls, "layer": layer, "_fa": fa, **kw}
        self.drops.append(d)
        return d

    def finish(self, items) -> dict:
        """Measure vis / onscreen / front of every drop on the final picture; truth dict."""
        for d in self.drops + [n for n in self.notdrops if "g" in n]:
            pic = items.pics[d["g"]]
            x, y, w, h = d["box"]
            op = pic[..., 3] == 255
            yy, xx = np.mgrid[y:y + h, x:x + w]
            on = op & (xx >= 0) & (xx < SW) & (yy >= 0) & (yy < PLAY_H)
            seen = np.zeros_like(op)
            r = ms._clip(x, y, w, h)
            if r is not None:
                x0, y0, x1, y1, sx, sy = r
                I = self.img[y0:y1, x0:x1].astype(np.int16)
                seen[sy:sy + y1 - y0, sx:sx + x1 - x0] = np.abs(I - pic[sy:sy + y1 - y0, sx:sx + x1 - x0, :3]).max(2) <= TOL
            seen &= on
            d["onscreen"] = round(float(on.sum() / max(1, op.sum())), 3)
            d["vis"] = round(float(seen.sum() / max(1, on.sum())), 3)
            fa = d.pop("_fa", None)
            if fa is not None:
                d["front"] = round(float(((fa >= 0.5) & on).sum() / max(1, on.sum())), 3)
        return {"case": self.case, "run": self.mp.key, "map": self.mp.map_id, "base": self.base.n,
                "C": [int(self.base.C[0]), int(self.base.C[1])], "me": self.base.me, "chars": self.chars,
                "drops": self.drops, "notdrops": self.notdrops, "mobs": self.mobs, "players": self.players,
                "window": list(self.window) if self.window else None}


# ------------------------------------------------------------------ cases
def rest_drop(fr: Frame, items, g, rng, cls="clear", sx=(0, SW), fh=None, x_at=None, over=False):
    """One resting drop of picture g on a foothold (free spot) -> its truth or None."""
    pic = items.pics[g]
    h, w = pic.shape[:2]
    for _ in range(30):
        if x_at is not None:
            mx, f = x_at
        else:
            p = fr.mp.point(fr.base.C, rng, sx=sx, sy=(h + 20, PLAY_H), fh=fh)
            if p is None:
                return None
            mx, f = p
        dy_low, bob = int(rng.integers(1, 6)), int(rng.integers(0, 7))
        x = int(round(mx - fr.base.C[0])) - w // 2
        fy = fr.mp.fh_y(f, x + fr.base.C[0] + w / 2)
        y = int(round(fy - fr.base.C[1])) + dy_low - bob - h
        if not fr.inside(x, y, w, h) or y < 0 or y + h > PLAY_H:
            if x_at is not None:
                return None
            continue
        if cls != "edge" and (x < 0 or x + w > SW):
            continue
        if not over and not fr.free(x, y, w, h):
            if x_at is not None:
                return None
            continue
        fr.take(x, y, w, h)
        return fr.add_drop(items, g, x, y, "rest", cls, layer=int(f["layerId"]), bob=bob,
                           dy=int(y + h + fr.base.C[1] - round(fy)), fh=int(f["id"]))
    return None


def mob_at(fr: Frame, rng, types=None, air=False):
    """Draw one mob of the map (any pose but die, opaque) on a foothold (flyers: in the air) -> its box or None."""
    mp = fr.mp
    t = int(rng.choice(types or mp.types))
    sps = [s for s in mp.sprites.get(t) or ms.load_sprites(t) if not s.anim.startswith("die")]
    sp = sps[int(rng.integers(len(sps)))]
    facing = "left" if rng.random() < 0.5 else "right"
    h, w = sp.im[facing].shape[:2]
    for _ in range(20):
        p = mp.point(fr.base.C, rng, sx=(w, SW - w), sy=(h + 10, PLAY_H))
        if p is None:
            return None
        mx, f = p
        feet = (int(round(mx - fr.base.C[0])), int(round(mp.fh_y(f, mx) - fr.base.C[1])))
        if air:
            feet = (feet[0], feet[1] - int(rng.integers(40, 160)))
        m = ms.Mob(sp, facing, feet, 1.0, int(f["layerId"]))
        if m.y < 0 or not fr.inside(m.x, m.y, m.w, m.h) or not fr.free(m.x, m.y, m.w, m.h, 2):
            continue
        ms.draw_mob(fr.img, fr.base, mp, m)
        fr.take(m.x, m.y, m.w, m.h, 0)
        fr.mobs.append({"type": t, "pose": sp.pose, "facing": facing, "feet": list(feet),
                        "box": [int(m.x), int(m.y), int(m.w), int(m.h)]})
        return fr.mobs[-1], f
    return None


def player_at(fr: Frame, rng):
    pl = fr.mp.players()
    if not pl:
        return None
    im, (ax, ay) = pl[int(rng.integers(len(pl)))]
    h, w = im.shape[:2]
    for _ in range(20):
        p = fr.mp.point(fr.base.C, rng, sx=(w, SW - w), sy=(h + 10, PLAY_H))
        if p is None:
            return None
        mx, f = p
        fx, fy = int(round(mx - fr.base.C[0])), int(round(fr.mp.fh_y(f, mx) - fr.base.C[1]))
        x, y = fx - ax, fy - ay
        if y < 0 or not fr.inside(x, y, w, h) or not fr.free(x, y, w, h, 2):
            continue
        before = fr.img.copy()
        ms.paste(fr.img, im, x, y)
        fr.take(x, y, w, h, 0)
        fr.chars.append(list(body_box((fx, fy))))
        fr.players.append({"anchor": [fx, fy], "box": [x, y, w, h]})
        return (fx, fy), f, before
    return None


def digits_over(fr: Frame, d, rng) -> None:
    num = ms.damage_number(fr.mp, int(rng.integers(10, 9999)))
    x, y, w, h = d["box"]
    cx, cy = x + w // 2 + int(rng.integers(-w // 2, w // 2 + 1)), y + h // 2 + int(rng.integers(-h // 3, h // 3 + 1))
    ms.paste(fr.img, num, cx - num.shape[1] // 2, cy - num.shape[0] // 2)


def repeat(rng, fn, lo=3, hi=6, tries=40) -> int:
    """Call fn() until it succeeded k times (k in lo..hi) or `tries` calls; -> successes."""
    k, n = int(rng.integers(lo, hi + 1)), 0
    for _ in range(tries):
        if n >= k:
            break
        n += bool(fn())
    return n


UI_OVER = [(930, 620, 1085, 705), (1140, 45, 1366, 160)]      # quickslots, the top-right rect (hud.UI_RECTS)


def case_frame(case: str, fr: Frame, items, cat, rng, draft) -> None:
    W = items
    pick = lambda: int(rng.choice(cat["all"]))                    # noqa: E731  any searchable picture
    if case == "cat":
        for _ in range(cat["n"]):
            if cat["next"] >= len(cat["order"]):
                cat["next"] = 0
                cat["round"] += 1
            g = int(cat["order"][cat["next"]])
            if rest_drop(fr, W, g, rng) is not None:
                cat["next"] += 1
    elif case == "pile":
        for _ in range(int(rng.integers(2, 5))):
            first = rest_drop(fr, W, pick(), rng, cls="pile")
            if first is None:
                continue
            f = next(ff for ff in fr.mp.fh if ff["id"] == first["fh"])
            mx = first["box"][0] + first["box"][2] // 2 + fr.base.C[0]
            for _ in range(int(rng.integers(1, 4))):
                mx += int(rng.integers(14, 31)) * (1 if rng.random() < 0.7 else -1)
                if not min(f["x1"], f["x2"]) < mx < max(f["x1"], f["x2"]):
                    break
                rest_drop(fr, W, pick(), rng, cls="pile", x_at=(mx, f), over=True)
    elif case in ("mob", "player"):
        def one():
            r = mob_at(fr, rng) if case == "mob" else player_at(fr, rng)
            if r is None:
                return False
            if case == "mob":
                (m, f) = r
                mx = m["feet"][0] + int(rng.integers(-15, 16)) + fr.base.C[0]
            else:
                (fx, _), f, _ = r
                mx = fx + int(rng.integers(-20, 21)) + fr.base.C[0]
            return (min(f["x1"], f["x2"]) < mx < max(f["x1"], f["x2"])
                    and rest_drop(fr, W, pick(), rng, cls=case, x_at=(mx, f), over=True) is not None)
        repeat(rng, one, 2, 5)
    elif case == "effect":
        def one():
            d = rest_drop(fr, W, pick(), rng, cls="effect")
            if d is not None:
                digits_over(fr, d, rng)
            return d is not None
        repeat(rng, one)
    elif case == "ui":                  # partly under a UI rect: its pixels re-drawn where they differ from the scene
        ui = fr.base.ui_alpha > 0

        def one():
            rx0, ry0, rx1, ry1 = UI_OVER[int(rng.integers(len(UI_OVER)))]
            g = pick()
            h, w = W.pics[g].shape[:2]
            p = fr.mp.point(fr.base.C, rng, sx=(rx0 - w // 2, rx1 + w // 2), sy=(ry0 + 4, ry1 + h - 4))
            d = None if p is None else rest_drop(fr, W, g, rng, cls="ui", x_at=p, over=True)
            if d is None:
                return False
            x, y, w, h = d["box"]
            a0, b0 = max(0, x), max(0, y)
            m = ui[b0:y + h, a0:x + w]
            fr.img[b0:y + h, a0:x + w][m] = fr.full[b0:y + h, a0:x + w][m]
            return True
        repeat(rng, one, 2, 5, 80)
    elif case == "edge":
        def one():
            g = pick()
            w = W.pics[g].shape[1]
            sx = (-w // 2 - 6, w // 2) if rng.random() < 0.5 else (SW - w // 2, SW + w // 2 + 6)
            return rest_drop(fr, W, g, rng, cls="edge", sx=sx) is not None
        repeat(rng, one, 2, 5)
    elif case == "flight":
        def one():
            g = int(rng.choice(cat["meso"])) if rng.random() < 0.6 else pick()
            pic = W.pics[g]
            h, w = pic.shape[:2]
            p = fr.mp.point(fr.base.C, rng, sx=(w, SW - w), sy=(h + 30, PLAY_H))
            if p is None:
                return False
            mx, f = p
            x = int(round(mx - fr.base.C[0])) - w // 2
            fy = fr.mp.fh_y(f, x + fr.base.C[0] + w / 2)
            up = int(rng.integers(12, 101))
            y = int(round(fy - fr.base.C[1])) - up - h
            if y < 0 or not fr.inside(x, y, w, h) or not fr.free(x, y, w, h):
                return False
            fr.take(x, y, w, h)
            fr.add_drop(W, g, x, y, "air", "flight", dy=-up, fh=int(f["id"]))
            return True
        repeat(rng, one, 3, 6, 60)
    elif case == "window":
        for _ in range(int(rng.integers(1, 3))):
            cols, rows = int(rng.integers(3, 6)), int(rng.integers(2, 5))
            pw, ph = 8 + 36 * cols, 8 + 36 * rows
            for _ in range(20):
                if fr.window is not None:
                    x0, y0, x1, y1 = fr.window
                    px, py = int(rng.integers(x0, max(x0 + 1, x1 - pw))), int(rng.integers(y0, max(y0 + 1, y1 - ph)))
                else:
                    px, py = int(rng.integers(0, SW - pw)), int(rng.integers(20, PLAY_H - ph))
                if fr.inside(px, py, pw, ph) and fr.free(px, py, pw, ph, 0):
                    break
            else:
                continue
            fr.take(px, py, pw, ph, 0)
            fr.img[py:py + ph, px:px + pw] = EDGE
            fr.img[py + 1:py + ph - 1, px + 1:px + pw - 1] = GAP
            for j in range(rows):
                for i in range(cols):
                    sx, sy = px + 6 + 36 * i, py + 6 + 36 * j
                    fr.img[sy:sy + 32, sx:sx + 32] = SLOT
                    if rng.random() < 0.15:
                        continue
                    iid = int(rng.choice(draft["ids"]))
                    ic = draft["items"].icon(iid)
                    if ic is None or ic[0] is None:
                        continue
                    pic, (ox, oy) = ic                  # the origin at the slot's bottom-left (may overflow it)
                    ax, ay = sx - ox, sy + 32 - oy
                    ms.paste(fr.img, pic, ax, ay)
                    fr.notdrops.append({"cls": "window", "item": iid, "box": [int(ax), int(ay), int(pic.shape[1]),
                                                                                int(pic.shape[0])]})
    elif case == "worn":
        for _ in range(int(rng.integers(2, 5))):
            r = player_at(fr, rng)
            if r is None:
                continue
            (fx, fy), _, before = r
            g = int(rng.choice(cat["equip"]))
            pic = W.pics[g]
            h, w = pic.shape[:2]
            x, y = fx - w // 2 + int(rng.integers(-8, 9)), fy - int(rng.integers(45, 75)) - h // 2
            if y < 0 or x < 0 or x + w > SW:
                continue
            under = fr.img.copy()                       # the player there
            fr.draw(pic, x, y)
            op = pic[..., 3] == 255
            share = rng.uniform(0.35, 0.70)
            side = int(rng.integers(0, 4))
            cum = np.cumsum(op.sum(axis=0 if side < 2 else 1)) / max(1, op.sum())
            cut = int(np.searchsorted(cum, share if side % 2 == 0 else 1 - share))
            band = np.zeros((h, w), bool)
            if side == 0:
                band[:, :cut + 1] = True
            elif side == 1:
                band[:, cut:] = True
            elif side == 2:
                band[:cut + 1] = True
            else:
                band[cut:] = True
            hb = min(h, PLAY_H - y)
            reg = fr.img[y:y + hb, x:x + w]
            reg[band[:hb]] = under[y:y + hb, x:x + w][band[:hb]]
            fr.notdrops.append({"cls": "worn", "g": g, "item": int(W.item[g]), "box": [int(x), int(y), int(w), int(h)]})
    elif case == "mobpart":
        for _ in range(int(rng.integers(3, 7))):
            r = mob_at(fr, rng, types=[STIRGE], air=rng.random() < 0.7)
            if r is not None:
                fr.notdrops.append({"cls": "mobpart", "type": STIRGE, "box": r[0]["box"]})
    elif case == "free":
        for _ in range(int(rng.integers(2, 6))):
            mob_at(fr, rng)
        for _ in range(int(rng.integers(0, 3))):
            player_at(fr, rng)
        for _ in range(int(rng.integers(1, 4))):
            num = ms.damage_number(fr.mp, int(rng.integers(10, 9999)))
            x0, y0, x1, y1 = fr.window or (0, 0, SW, PLAY_H)
            ms.paste(fr.img, num, int(rng.integers(x0, max(x0 + 1, x1 - num.shape[1]))),
                     int(rng.integers(y0, max(y0 + 1, y1 - num.shape[0]))))
    if case in ("mob", "player", "effect", "ui", "edge", "flight", "pile") and rng.random() < 0.5:
        mob_at(fr, rng)                                 # some context: a mob that is not under a drop


# ------------------------------------------------------------------ the set
def catalogue(items, rng) -> dict:
    """Drops come from the pictures that can drop (not cash-only; weak ones too: reported); worn gear may be any
    equip (players wear cash items)."""
    nmeso = [g for g in range(len(items)) if items.kind(items.item[g]) == "Meso"]
    allg = [g for g in range(len(items)) if not items.weak[g] and not items.cash[g]]
    equip = [g for g in range(len(items)) if not items.weak[g] and items.kind(items.item[g]) in EQUIP]
    order = rng.permutation(np.flatnonzero(~items.cash))
    return {"order": order, "next": 0, "round": 0, "all": allg, "meso": nmeso, "equip": equip}


def window_for(fr_base, mp: Map, rng, case):
    """A <= 440 x 300 window of the play area with footholds in it (fixture frames)."""
    C = fr_base.C
    for _ in range(50):
        if case == "edge":
            x0 = 0 if rng.random() < 0.5 else SW - 440
        else:
            x0 = int(rng.integers(0, SW - 440))
        y0 = int(rng.integers(30, PLAY_H - 300))
        n = sum(1 for f in mp.fh if min(f["x1"], f["x2"]) - C[0] < x0 + 400 and max(f["x1"], f["x2"]) - C[0] > x0 + 40
                and y0 + 60 < (f["y1"] + f["y2"]) / 2 - C[1] < y0 + 290)
        if case == "ui":
            x0 = int(rng.choice([645, 926]))           # the quickslots (930-1085) / the top-right rect at its side
            y0 = 400 if x0 == 645 else 30
        if n >= 2:
            return (x0, y0, x0 + 440, y0 + 300)
    return None


def generate(out: Path, seed: int, plan: list, fixture: bool, cat_n: int, log=print) -> dict:
    from maplebrain.gamedata import load_items
    import time
    items = load_items()
    rng = np.random.default_rng(seed)
    cat = catalogue(items, rng)
    cat["n"] = cat_n
    draft_items = DraftItems()
    draft = {"items": draft_items, "ids": [i for i in draft_items.ids(("Etc", "Consume", "Install") + EQUIP)
                                          if draft_items.icon(i) is not None]}
    maps = {}
    out = Path(out)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    if fixture:
        (out / "exp").mkdir(exist_ok=True)
    meta, masks = {"v": 1, "seed": seed, "fixture": fixture, "frames": {}}, {}
    t0 = time.time()
    for i, (case, key) in enumerate(plan):
        mp = maps.get(key) or maps.setdefault(key, Map(key))
        for _ in range(40):
            r = mp.rows[int(rng.integers(len(mp.rows)))]
            b = mp.base(r)
            if b is None:
                continue
            win = window_for(b, mp, rng, case) if fixture else None
            if fixture and win is None:
                continue
            fr = Frame(mp, b, case, win)
            case_frame(case, fr, items, cat, rng, draft)
            if case == "free" or (fr.notdrops if case in ("window", "worn", "mobpart") else fr.drops):
                break
        else:
            raise RuntimeError(f"no base frame for {case} on {key}")
        t = fr.finish(items)
        name = f"{i:06d}"
        if fixture:
            x0, y0, x1, y1 = win
            cv2.imwrite(str(out / "frames" / f"{name}.webp"), fr.img[y0:y1, x0:x1], [cv2.IMWRITE_WEBP_QUALITY, 101])
            cv2.imwrite(str(out / "exp" / f"{name}.webp"), b.e[y0:y1, x0:x1], [cv2.IMWRITE_WEBP_QUALITY, 101])
            masks[f"{name}_known"] = np.packbits(b.known[y0:y1, x0:x1])
            masks[f"{name}_world"] = np.packbits(mp.world[:PLAY_H][y0:y1, x0:x1])
            ax, ay = int(b.C[0]) - mp.scene.x0, int(b.C[1]) - mp.scene.y0
            for L, pl in mp.scene.layers.items():
                m = np.zeros((PLAY_H, SW), bool)
                ys0, xs0 = max(0, ay), max(0, ax)
                ys1, xs1 = min(pl.shape[0], ay + PLAY_H), min(pl.shape[1], ax + SW)
                if ys1 > ys0 and xs1 > xs0:
                    m[ys0 - ay:ys1 - ay, xs0 - ax:xs1 - ax] = (pl[ys0:ys1, xs0:xs1] >= 128).cpu().numpy()
                masks[f"{name}_front_{L}"] = np.packbits(m[y0:y1, x0:x1])
            t["frame"] = f"{name}.webp"
        else:
            full = b.frame.copy()
            full[:PLAY_H] = fr.img
            cv2.imwrite(str(out / "frames" / f"{name}.png"), full, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            t["frame"] = f"{name}.png"
        meta["frames"][name] = t
        if (i + 1) % 50 == 0:
            log(f"  {i + 1} / {len(plan)} frames, {time.time() - t0:.0f} s; catalogue at {cat['next']} "
                f"(round {cat['round']})")
    meta["catalogue_rounds"] = cat["round"] + cat["next"] / len(cat["order"])
    if fixture:
        np.savez_compressed(out / "masks.npz", **masks)
    (out / "synth.json").write_text(json.dumps(meta, indent=0), encoding="utf-8")
    return meta


def plan_for(fixture: bool, cat_frames: int, per_case: int, free: int, rng) -> list:
    keys = list(RUNS)
    if fixture:
        counts = {c: 3 for c in CASES}
        counts.update(cat=6, free=4)
    else:
        counts = {c: per_case for c in CASES}
        counts.update(cat=cat_frames, free=free)
    plan = []
    for c in CASES:
        ks = ["steam", "transfer"] if c == "mobpart" else keys
        plan += [(c, ks[j % len(ks)]) for j in range(counts[c])]
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--fixture", action="store_true")
    ap.add_argument("--cat-n", type=int, default=24, help="drops per catalogue frame")
    ap.add_argument("--per-case", type=int, default=25)
    ap.add_argument("--free", type=int, default=50)
    a = ap.parse_args()
    from maplebrain.gamedata import load_items
    n_pics = int((~load_items().cash).sum())        # the pictures that can drop
    cat_frames = -(-n_pics // a.cat_n) + 4          # every picture at least once (a few placements fail)
    plan = plan_for(a.fixture, cat_frames, a.per_case, a.free, np.random.default_rng(a.seed))
    meta = generate(Path(a.out), a.seed, plan, a.fixture, 8 if a.fixture else a.cat_n)
    fr = meta["frames"].values()
    nd = sum(len(f["drops"]) for f in fr)
    print(f"{a.out}: {len(meta['frames'])} frames, {nd} drops ({sum(d['kind'] == 'rest' for f in fr for d in f['drops'])}"
          f" resting), {sum(len(f['notdrops']) for f in fr)} not-drops, distinct pictures "
          f"{len({d['g'] for f in fr for d in f['drops']})} of {n_pics}; catalogue rounds {meta['catalogue_rounds']:.2f}")


if __name__ == "__main__":
    main()
