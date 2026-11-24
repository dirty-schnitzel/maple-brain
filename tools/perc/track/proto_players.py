"""Tracker plan, Part 2, an experiment: OTHER PLAYERS from the name tags, on the kept replay (no GPU; the frames are
read only for the by-eye sheets). A prototype for PLAN-tracker.md: nothing of the product reads it.

    python tools/perc/track/proto_players.py CAP [CAP ...]      the numbers for each capture
    python tools/perc/track/proto_players.py --sound            every capture of cache.SOUND
        --cover S        the cover a player is kept through, seconds (default 1.0; docs/state_model.md section 3 rule 4)
        --covers         also: the capture at cover 0.3 / 1 / 2 s (tracks, id changes at re-appearance)
        --no-width       associate by position alone (what the tag's width buys)
        --sheets         the by-eye sheets -> CORPUS/work/track-plan/players/ (reads the frames)
        --tracks         print every track
        --time           ms per frame (pinned to the performance cores)

What it does, per frame, from FrameFacts.tags (tags.find_tags: a row of light glyphs on a darkened box), our own tag
(FrameFacts.tag), the scene camera, the fit's mobs and D's blobs (FrameFacts.patches):
  1. each tag -> ours / a line of the message log (fixed on SCREEN, right-aligned) / a candidate; the candidates'
     pieces on one row are put together (a ladder's rail in front cuts a tag in two) and each gets its evidence:
     under a seen mob's feet (the mob's own "Lv. N name" tag), near an NPC of map.json, over another tag (a pattern
     on a player's clothes), and the BODY standing on it (how far D's blob reaches over the tag: a character ~70 px,
     a pet ~40, text drawn over the world 0);
  2. the candidates are followed frame to frame in MAP coordinates (map = screen + camera): a track = one tag's
     life = an id; its class is voted over its life (mob / npc / text / pet / pattern / player);
  3. a track not found on a frame is kept (covered) up to `cover` seconds while its place is in view, and ends at
     once when its place is out of view (at the screen's edge or under the UI); a blind frame changes nothing;
  4. a player's feet = the tag's centre x, its top y - 1; placed by the one placement rule (stand / air / rope).
The tag's width (constant for one name) keeps two tags apart: after a gap only a tag of the track's own width takes
its id back; a narrower or wider box is taken as a piece of it / a box it shares only by the edge that kept its place.
"""
import argparse
import json
import pickle
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "track"))
sys.path.insert(0, str(ROOT / "tools" / "model"))

SW, SH, PLAY_H = 1366, 768, 700
# what the tag finder cannot see (hud.UI_RECTS; the minimap's rectangle is measured per capture)
UI_FIXED = [(1140, 45, 1366, 160), (285, 630, 850, 768), (930, 620, 1085, 705), (285, 700, 1366, 768)]
MINIMAP_DEFAULT = (0, 0, 215, 195)
# the message log (bottom right, drawn over the world, fixed on screen): its lines' tag boxes
LOG_ROW0, LOG_PITCH, LOG_ROWS, LOG_RIGHT, LOG_X0 = 602, 14, 6, (1363, 1369), 1000
G0 = 16.0                       # px: how far a tag seen on the last frame may have moved
VX, VY = 260.0, 800.0           # px/s: the gate's growth while a track is not seen
W_TOL = 1                       # px: "the same width" (78 % of a track's whole sightings are its width exactly, 1 %
                                # within 1-2 px; a pet's tag can be 2 px off its owner's: 83 / 85)
JOIN = 6                        # px: two boxes on one row this close are pieces of one tag
CONFIRM = 3                     # whole sightings before a track's width counts
MIN_SEEN = 6                    # sightings before a track gets a class
EDGE = 6                        # px: a tag box this close to the border of what the finder sees = cut / at the edge
BODY_TALL = 55                  # px: D's blob reaches at least this far over the tag = a character stands on it
STAND_TOL = 3.0                 # px: the placement rule's stand tolerance
ROPE_TOL = 12.0                 # px: Nav.rope_tol
CLASSES = ("ours", "log", "mob", "npc", "text", "pet", "pattern", "player", "unsure", "short", "none")
N, T, X, Y, W, H, KIND, OFF, SX, SY, BODY = range(11)       # a track's sighting (Track.hist)


def corpus() -> Path:
    from maplebrain.config import corpus_root
    return corpus_root()


def out_dir() -> Path:
    p = corpus() / "work" / "track-plan" / "players"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pct(v, ps=(50, 90, 99, 100)):
    v = np.asarray(v, float)
    return [round(float(np.percentile(v, p)), 2) for p in ps] if len(v) else None


# ------------------------------------------------------------------------------------------------ the frames
def blob_over(tag, patches, ui=()) -> int:
    """Is anything standing on the tag at all? How far over the tag's top the tallest of D's blobs (FrameFacts.
    patches: what the scene does not explain) reaches that lies over the tag's centre and comes down to the tag.
    0: nothing (text drawn over the world has no body). -1: cannot be told - D covers the play area only (rows <
    700, no UI): the tag lies under it, or the place over the tag is UI / off the screen. NOT a body's height: a
    pet beside its owner is one blob with the owner (that is `col_body`)."""
    x, y, w, h = tag
    cx, best = x + w / 2.0, 0
    for px, py, pw, ph, _area in patches or ():
        if px <= cx <= px + pw and py < y <= py + ph + 12 and y - py > best:
            best = y - py
    if best < BODY_TALL:                                    # short, or none: was all of it in D's reach?
        if patches is None or y > PLAY_H + 12 or y < 85:
            return -1
        for a, b, c, d in ui:
            if cx - 10 < c and cx + 10 > a and y - 85 < d and y > b:
                return -1
    return int(best)


def col_body(over, world, tag, half=8, reach=120, gap=8) -> int:
    """The height of the body standing on the tag: in the 17 columns over the tag's centre, the rows that hold
    something drawn over the scene (`over` = world & ~shows of the kept replay's bitmaps), read upward from the tag's
    top until a break of more than `gap` rows. A character is 65-80 px, a pet 35-45. 0: nothing over the centre.
    -1: cannot be told (the tag lies under the play area, or less than 60 % of that column is `world`)."""
    x, y, w, h = tag
    cx = x + w // 2
    x0, x1 = max(0, cx - half), min(SW, cx + half + 1)
    r0, r1 = max(0, y - reach), min(PLAY_H, y)
    if r1 - r0 < 20 or x1 - x0 < 8 or y > PLAY_H + 6 or world[r0:r1, x0:x1].mean() < 0.6:
        return -1
    has = over[r0:r1, x0:x1].sum(1) >= 4
    top, miss = None, 0
    for i in range(len(has) - 1, -1, -1):
        if has[i]:
            top, miss = i, 0
        else:
            miss += 1
            if miss > gap:
                break
    return 0 if top is None else int(y - (r0 + top))


def frames_of(cap, force: bool = False) -> dict:
    """The capture's frames, slim: {"cap", "map", "minimap", "rows": [(n, t, C, own tag, [tags], [(type, anim, fx,
    fy, opacity)] or None, [(col_body, blob_over) per tag])]} - read from the kept replay (rows + bitmaps) one chunk
    file at a time, kept in out_dir()/slim (the design capture: ~3 minutes the first time)."""
    import dump
    p = out_dir() / "slim" / f"{cap}.pkl"
    if p.exists() and not force:
        return pickle.loads(p.read_bytes())
    d, meta = dump.out_dir(cap), dump.meta(cap)
    mm = minimap_rect(cap)
    ui = [mm] + UI_FIXED
    rows = []
    for k in range(meta["chunks"]):
        bts = pickle.loads((d / f"bits_{k:03d}.pkl").read_bytes())
        for r, (bn, s, w) in zip(pickle.loads((d / f"rows_{k:03d}.pkl").read_bytes()), bts):
            f = r["facts"]
            fit = f.get("fit")
            tags = [tuple(x) for x in f.get("tags") or []]
            cols = [-1] * len(tags)
            if tags and s is not None and bn == r["n"]:
                world = dump.bits(w)
                over = world & ~dump.bits(s)
                cols = [col_body(over, world, tg) for tg in tags]
            rows.append((r["n"], r["t"], r["C"], f.get("tag"), tags,
                         None if fit is None else [(m["type"], m["pose"].rsplit("_", 1)[0], m["feet"][0], m["feet"][1],
                                                    m["opacity"]) for m in fit],
                         [(c, blob_over(tg, f.get("patches"), ui)) for c, tg in zip(cols, tags)]))
        del bts
    out = {"cap": cap, "map": meta["map"], "minimap": mm, "rows": rows}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    return out


def minimap_rect(cap) -> tuple:
    """The minimap window's rectangle on this capture (what the Perceiver hands the tag finder), measured on one
    frame; hud's default when it cannot be measured."""
    try:
        import frames as rec
        from maplebrain.nav.localize import find_window
        from maplebrain.perception.hud import minimap_rect as rect
        c = rec.clip(str(cap), False, "proto_players")
        fr = c.frames()
        for i in (len(fr) // 2, len(fr) // 4, 3 * len(fr) // 4):
            w = find_window(rec.read(c.run, fr[i][1]))
            if w is not None:
                return tuple(int(v) for v in rect(w))
    except Exception as e:                                  # noqa: BLE001
        print(f"   (minimap not measured: {e})")
    return MINIMAP_DEFAULT


# ------------------------------------------------------------------------------------------------ the map
class Ground:
    """Every walkable foothold as arrays (tools/model/nav_audit.Index' layout) + the ropes: the placement rule."""

    def __init__(self, map_id: int):
        from maplebrain.config import Config
        from nav_audit import Index, nav_nolinks
        self.json = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        nm = nav_nolinks(self.json, Config().nav)
        ix = Index(nm)
        self.x1, self.y1, self.x2, self.slope, self.pid = ix.x1, ix.y1, ix.x2, ix.slope, ix.pid.astype(int)
        self.ropes = np.array([(r.x, r.top, r.bottom) for r in nm.ropes], float).reshape(-1, 3)
        self.npcs = [(n["x"], n["y"]) for n in self.json.get("npcs") or []]
        self.portals = [(p["x"], p["y"], p.get("portalName", "")) for p in self.json.get("portals") or []]
        self.name = self.json.get("name", str(map_id))

    def place(self, xs, ys):
        """Feet (map px) -> per point: the nearest surface's node and off = feet y - its y (nan: none at that x),
        the first surface under the feet (node or -1), the rope whose x is within ROPE_TOL between its ends (index
        or -1) and feet x - its x."""
        xs, ys = np.asarray(xs, float)[:, None], np.asarray(ys, float)[:, None]
        on = (self.x1[None] <= xs) & (xs <= self.x2[None])
        y = self.y1[None] + (xs - self.x1[None]) * self.slope[None]
        d = np.where(on, y - ys, np.inf)                    # + = the surface is under the feet
        k = np.abs(d).argmin(1)
        r = np.arange(len(k))
        ok = np.isfinite(d[r, k])
        node = np.where(ok, self.pid[k], -1)
        off = np.where(ok, -d[r, k], np.nan)
        dn = np.where(d >= -STAND_TOL, d, np.inf)
        kb = dn.argmin(1)
        under = np.where(np.isfinite(dn[r, kb]), self.pid[kb], -1)
        if len(self.ropes):
            dx = xs - self.ropes[None, :, 0]
            inr = (np.abs(dx) <= ROPE_TOL) & (ys >= self.ropes[None, :, 1] - ROPE_TOL) & (ys <= self.ropes[None, :, 2] + ROPE_TOL)
            kr = np.where(inr, np.abs(dx), np.inf).argmin(1)
            has = inr[r, kr]
            rope, rdx = np.where(has, kr, -1), np.where(has, dx[r, kr], np.nan)
        else:
            rope, rdx = np.full(len(k), -1), np.full(len(k), np.nan)
        return node, off, under, rope, rdx


# ------------------------------------------------------------------------------------------------ the view
class View:
    """What the tag finder sees: the screen without the UI rectangles."""

    def __init__(self, minimap=MINIMAP_DEFAULT):
        self.ui = [tuple(minimap)] + UI_FIXED

    def why(self, x0, y0, x1, y1, m=EDGE) -> str:
        """"screen" / "ui" when the screen box is within m px of the screen's border / of a UI rectangle (or past
        it), else ""."""
        if x0 < m or y0 < m or x1 > SW - m or y1 > SH - m:
            return "screen"
        for a, b, c, d in self.ui:
            if x0 < c + m and x1 > a - m and y0 < d + m and y1 > b - m:
                return "ui"
        return ""


def log_row(y) -> int | None:
    """The message log's row a tag box with top y sits on (0 = the newest, lowest), or None."""
    k, r = divmod(LOG_ROW0 + 1 - y, LOG_PITCH)
    return int(k) if 0 <= k < LOG_ROWS and r <= 2 else None


# ------------------------------------------------------------------------------------------------ mobs' own tags
def learn_mob_tags(rows) -> dict:
    """mob kind -> (w, h, dx, dy, n, share): the box of the kind's own tag ("Lv. N name") and where it sits against
    the fit's feet (dx = the box's centre x - feet x, dy = its top y - feet y), learned as the commonest (w, h, dx,
    dy) among the tags within 60 px of a seen mob's feet and 0..4 px under them. share = that mode's share of the
    kind's pairs: a player's tag beside a mob has no such mode."""
    c = defaultdict(Counter)
    for row in rows:
        tags, fit = row[4], row[5]
        if not fit or not tags:
            continue
        for x, y, w, h in tags:
            cx2 = 2 * x + w                                 # twice the centre x (whole numbers)
            for ty, anim, fx, fy, op in fit:
                if abs(cx2 - 2 * fx) <= 120 and 0 <= y - fy <= 4:
                    c[ty][(w, h, cx2 - 2 * fx, y - fy)] += 1
    out = {}
    for ty, cc in c.items():
        (w, h, dx2, dy), n = cc.most_common(1)[0]
        near = sum(v for (w2, h2, d2, y2), v in cc.items() if abs(w2 - w) <= 1 and abs(h2 - h) <= 1
                   and abs(d2 - dx2) <= 4 and abs(y2 - dy) <= 1)
        if near >= 20:
            out[ty] = (w, h, dx2 / 2.0, dy, near, round(near / sum(cc.values()), 3))
    return out


# ------------------------------------------------------------------------------------------------ the tracker
class Det:
    """One tag of a frame (pieces on one row put together): its box on screen and on the map, its evidence."""
    __slots__ = ("x", "y", "w", "h", "L", "R", "T", "cx", "cut", "joined", "nobirth", "logrow", "off", "mob", "npc",
                 "above", "tr", "raw", "body", "blob", "mobbox")

    def __init__(self, x, y, w, h, body=(-1, -1)):
        self.x, self.y, self.w, self.h, self.raw = x, y, w, h, 1
        self.body, self.blob = body                      # col_body, blob_over
        self.cut = self.joined = self.nobirth = self.logrow = self.mob = self.npc = self.above = self.mobbox = False
        self.off, self.tr = None, None

    def to_map(self, cx0, cy0):
        self.L, self.R, self.T, self.cx = self.x + cx0, self.x + self.w + cx0, self.y + cy0, self.x + self.w / 2.0 + cx0


def join_rows(boxes) -> list:
    """Boxes (x, y, w, h, body) on one row (tops or bottoms within 2 px) whose gap is at most JOIN px -> one Det."""
    out = []
    for x, y, w, h, body in sorted(boxes):
        for d in out:
            if x - (d.x + d.w) <= JOIN and x + w >= d.x - JOIN and (abs(y - d.y) <= 2 or abs(y + h - d.y - d.h) <= 2):
                x1, y1 = max(d.x + d.w, x + w), max(d.y + d.h, y + h)
                d.x, d.y = min(d.x, x), min(d.y, y)
                d.w, d.h = x1 - d.x, y1 - d.y
                d.raw += 1
                d.body, d.blob = -1, max(d.blob, body[1])   # the pieces' centres are not the tag's
                d.joined = True
                break
        else:
            out.append(Det(x, y, w, h, body))
    return out


class Track:
    __slots__ = ("id", "x", "y", "w", "h", "wc", "hc", "t", "n", "t0", "n0", "unseen", "seen", "ev", "rest",
                 "hist", "born", "end", "sx", "sy", "scr", "mapst", "merged", "wlast", "clean", "into", "vx", "px",
                 "known", "shared", "end_n", "end_xy")

    def __init__(self, tid, d, t, n):
        self.id = tid
        self.x, self.y, self.w, self.h = d.cx, d.T, d.w, d.h
        self.vx, self.px = 0.0, d.cx
        self.wc, self.hc = Counter(), Counter()
        self.known = False               # its own width was seen (a whole sighting); until then w = the widest piece
        self.t = self.t0 = t
        self.n = self.n0 = n
        self.unseen = 0.0                # seconds of frames with a camera since it was last seen
        self.seen = 0
        self.clean = 0                   # sightings whole, alone and of its own width
        self.shared = 0                  # sightings inside a box another track took
        self.ev = Counter()              # evidence counts: mob, npc, above, logrow, b0 / bs / bt (no / small / tall body)
        self.rest = Counter()            # off (tag top - surface) on frames it did not move vertically
        self.hist = []                   # (N, T, X, Y, W, H, KIND, OFF, SX, SY, BODY); KIND 0 whole, 1 piece / merged / cut
        self.born = self.end = ""
        self.end_n, self.end_xy = None, None
        self.sx = self.sy = None         # its last box corner on screen
        self.scr = [0, 0]                # frames the camera moved: [its screen place stayed, all]
        self.mapst = [0, 0]              # frames the camera moved: [its map place stayed, all]
        self.merged = False              # its last sighting was inside a box shared with another track
        self.wlast = d.w
        self.into = None                 # the track this one turned out to be a piece / the re-appearance of

    def cls(self) -> str:
        """The track's class by what was seen of it so far."""
        s, e = self.seen, self.ev
        if s < MIN_SEEN or self.clean < CONFIRM:
            return "short"
        if 2 * e["mob"] >= s or (e["mob"] >= 3 and 2 * e["mobbox"] >= s):
            return "mob"                                     # under a seen mob's feet / a mob tag's box, seen so 3 times
        if 2 * e["above"] >= s:
            return "pattern"
        if 2 * e["npc"] >= s:
            return "npc"
        if (e["b0"] >= 3 and e["b0"] >= e["bs"] + e["bt"]) or (self.scr[1] >= 5 and self.scr[0] >= 0.8 * self.scr[1]):
            return "text"                                    # no body over it / it stays put on the screen
        one, body = e["bs1"] + e["bt1"], e["bs"] + e["bt"]   # the body's height: on its whole sightings, else all
        if one >= 5:
            return "pet" if 2 * e["bs1"] >= one else "player"
        if body >= 5:
            return "pet" if 2 * e["bs"] >= body else "player"
        return "unsure"                                      # no body could be read (under the play area, at the UI)


class Tracker:
    def __init__(self, ground: Ground, view: View, mob_tags: dict, cover: float = 1.0, use_width: bool = True):
        self.g, self.view, self.mob_tags, self.cover, self.use_width = ground, view, mob_tags, cover, use_width
        self.live, self.done = [], []
        self.next_id = 1
        self.me = None                   # our tag's last place on the map (cx, top, t)
        self.prev_C = None
        self.frames = []                 # per frame: None (blind) or [(track or "ours" / "log", raw tags, x, y, w, h)]
        self.stats = Counter()

    # -- one frame
    def step(self, n, t, C, own, tags, fit, bodies, dt):
        if C is None:                                       # blind: nothing begins or ends
            self.frames.append(None)
            return
        cx0, cy0 = C
        moved = self.prev_C is not None and (self.prev_C[0] != cx0 or self.prev_C[1] != cy0)
        self.prev_C = C
        rec, boxes, cand = [], [], []
        ox = None
        if own is not None:
            ox, oy, ow, oh = own[0], own[1], own[2], own[3]
            self.me = (ox + ow / 2.0 + cx0, oy + cy0, t)
        elif self.me is not None and t - self.me[2] < 2.0:  # our tag not found by its own finder: where it was
            ow, oh = 74, 17
            ox, oy = self.me[0] - ow / 2.0 - cx0, self.me[1] - cy0
        for (x, y, w, h), body in zip(tags, bodies):
            if ox is not None:
                gate = 0.0 if own is not None else G0 + VY * (t - self.me[2])
                if y < oy + oh - 4 + gate and y + h > oy + 4 - gate and \
                        min(x + w, ox + ow + gate) - max(x, ox - gate) >= 0.4 * min(w, ow):
                    rec.append(("ours" if own is not None else "ours*", 1, x, y, w, h))
                    if own is None:
                        self.me = (x + w / 2.0 + cx0, y + cy0, self.me[2])
                        continue
                    for a, b in ((x, ox), (ox + ow, x + w)):   # what sticks out of our tag: a neighbour's piece
                        if b - a >= 10:
                            d = Det(int(a), y, int(b - a), h)
                            d.nobirth = True
                            cand.append(d)
                    continue
            boxes.append((x, y, w, h, body))
        for d in join_rows(boxes):
            k = log_row(d.y)                                 # a log line: on a row of the log, right-aligned - or a
            d.logrow = k is not None and d.x + d.w / 2 >= LOG_X0   # piece of one: on a row, nothing standing on it
            if k is not None and (LOG_RIGHT[0] <= d.x + d.w <= LOG_RIGHT[1] or (d.logrow and d.blob == 0)):
                rec.append(("log", d.raw, d.x, d.y, d.w, d.h))
                continue
            cand.append(d)
        for d in cand:
            d.to_map(cx0, cy0)
            d.cut = d.joined or d.nobirth or bool(self.view.why(d.x, d.y, d.x + d.w, d.y + d.h))
        self._evidence(cand, fit)
        self._associate(cand, n, t, dt, cx0, cy0, moved)
        for d in cand:
            if not d.nobirth:
                rec.append((d.tr, d.raw, d.x, d.y, d.w, d.h, d.body))
        self.frames.append(rec)

    def _evidence(self, dets, fit):
        if not dets:
            return
        node, off, under, rope, rdx = self.g.place([d.cx for d in dets], [d.T for d in dets])
        for i, d in enumerate(dets):
            d.off = None if np.isnan(off[i]) else float(off[i])
            c = d.x + d.w / 2.0
            for ty, anim, fx, fy, op in fit or ():
                mt = self.mob_tags.get(ty)
                if mt is not None and abs(d.y - fy - mt[3]) <= 1 and abs(c - fx - mt[2]) <= 4 \
                        and abs(d.w - mt[0]) <= W_TOL:
                    d.mob = True
                    break
            d.mobbox = any(abs(d.w - mt[0]) <= 1 and abs(d.h - mt[1]) <= 1 for mt in self.mob_tags.values())
            d.npc = any(abs(d.cx - nx) < 40 and abs(d.T - ny) < 40 for nx, ny in self.g.npcs)
        for d in dets:                                       # 12..45 px over another tag, their x overlapping, and no
            d.above = d.blob < BODY_TALL and any(            # tall body over it: a pattern on that tag's owner
                e is not d and 12 <= e.y - d.y <= 45 and min(d.x + d.w, e.x + e.w) - max(d.x, e.x) >= 0.5 * d.w
                for e in dets)

    def _associate(self, dets, n, t, dt, cx0, cy0, moved):
        live = self.live
        pairs = []
        for a, tr in enumerate(live):
            u = tr.unseen
            px = tr.px = tr.x + tr.vx * min(u, 0.5)          # where it would be by now, walking on as it did
            pl, pr = px - tr.w / 2.0, px + tr.w / 2.0
            gx, gy, ge = G0 + VX * u, G0 + VY * u, G0 + 60.0 * u
            for b, d in enumerate(dets):
                ey = min(abs(d.T - tr.y), abs(d.T + d.h - tr.y - tr.h))
                if ey > gy:
                    continue
                dw = d.w - tr.w
                if not self.use_width:                       # position alone: the box's centre
                    ex = abs(d.cx - px)
                    if ex > gx:
                        continue
                    c = ex + ey
                elif abs(dw) <= W_TOL and tr.known:          # its own width: the whole tag
                    ex = abs(d.cx - px)
                    if tr.merged:
                        ex = min(ex, abs(d.L - pl), abs(d.R - pr))
                    if ex > gx:
                        continue
                    c = ex + ey
                else:                                        # a piece of it / a wider box it is part of: by an edge
                    ex = min(abs(d.L - pl), abs(d.R - pr))
                    if dw < 0 and pl - G0 <= d.L and d.R <= pr + G0:
                        ex = min(ex, G0 / 2.0)               # a piece inside its box
                    if ex > ge:
                        continue
                    c = ex + ey + (4.0 * abs(dw) if tr.merged else 8.0)
                pairs.append((c, a, b))
        pairs.sort()
        ua, ub = {}, {}
        for c, a, b in pairs:
            if a in ua or b in ub:
                continue
            ua[a], ub[b] = b, a
        for a, b in ua.items():
            self._update(live[a], dets[b], n, t, moved)
        if self.use_width:
            self._together(dets, ua, ub, n, t, moved)
        for a, tr in enumerate(live):                        # not seen on this frame
            if a in ua or tr.into is not None:
                continue
            tr.unseen += dt
            sx, sy = tr.px - tr.w / 2.0 - cx0, tr.y - cy0
            why = self.view.why(sx, sy, sx + tr.w, sy + tr.h)
            if why:
                tr.end = "edge:" + why
            elif tr.unseen > self.cover:
                tr.end = "lost"
            if tr.end:
                tr.end_n, tr.end_xy = n, (sx, sy)
        for b, d in enumerate(dets):
            if b in ub or d.nobirth:
                continue
            tr = Track(self.next_id, d, t, n)
            self.next_id += 1
            tr.born = "edge" if self.view.why(d.x, d.y, d.x + d.w, d.y + d.h, 2 * EDGE) else "in view"
            self._update(tr, d, n, t, moved, new=True)
            live.append(tr)
        if self.use_width:                                   # a young track that now shows the width of an older
            for y in live:                                   # one still covered, inside its gate: the same tag coming
                if y.into is not None or y.end or y.n != n or y.clean > 2 * CONFIRM or not y.known \
                        or y.hist[-1][KIND] != 0:            # back (out from behind something, piece by piece)
                    continue
                for o in live:
                    if o is y or o.into is not None or o.end or o.unseen == 0.0 or o.clean < CONFIRM or o.id > y.id \
                            or o.t >= y.t0 or abs(o.w - y.w) > W_TOL:
                        continue
                    if abs(y.x - o.px) <= G0 + VX * o.unseen and abs(y.y - o.y) <= G0 + VY * o.unseen:
                        self._absorb(o, y, "back")
                        break
        keep = []
        for tr in live:
            if tr.into is not None:
                continue
            if tr.end:
                self.done.append(tr)
            else:
                keep.append(tr)
        self.live = keep

    def _together(self, dets, ua, ub, n, t, moved):
        """A track left without a tag whose place is inside a wider box another track took: two tags run together
        (the box is narrower than the two side by side: tags.find_tags joins text at most 7 px apart) - or the two
        were pieces of one tag (it is not narrower). And a tag left without a track: a piece of a tag a track took."""
        live = self.live
        for a, tr in enumerate(live):
            if a in ua or tr.unseen > 0.1:
                continue
            pl, pr = tr.px - tr.w / 2.0, tr.px + tr.w / 2.0
            for b, o in list(ub.items()):
                d, other = dets[b], live[o]
                if other.into is not None or (other.clean >= CONFIRM and d.w <= other.w + W_TOL):
                    continue                                 # the other's tag alone: this one is not in it
                if d.w > tr.wlast + W_TOL and d.L - G0 <= pl and pr <= d.R + G0 and \
                        min(abs(d.T - tr.y), abs(d.T + d.h - tr.y - tr.h)) <= G0:
                    if d.w >= tr.wlast + other.wlast - 4 and not (tr.clean >= CONFIRM and other.clean >= CONFIRM):
                        old, new = (other, tr) if other.id < tr.id else (tr, other)
                        self._absorb(old, new, "piece")
                        if new is other:                     # the older one goes on with the box
                            self._update(old, d, n, t, moved)
                            ub[b] = a
                    else:
                        self._update(tr, d, n, t, moved, shared=True)
                        other.merged = True
                    ua[a] = b
                    break
        for b, d in enumerate(dets):
            if b in ub:
                continue
            for a, tr in enumerate(live):
                if a in ua and tr.n == n and tr.into is None and tr.x - tr.w / 2.0 - G0 <= d.L and \
                        d.R <= tr.x + tr.w / 2.0 + G0 and d.w < tr.w - W_TOL and \
                        min(abs(d.T - tr.y), abs(d.T + d.h - tr.y - tr.h)) <= 4:
                    d.tr = tr
                    ub[b] = a
                    break

    def _absorb(self, old, new, why):
        """`new` turned out to be `old` (a piece of its tag / the tag coming back): old takes its sightings."""
        new.into = old
        new.end = why
        self.stats["absorbed: " + why] += 1
        seen = {}
        for h in old.hist + [h[:KIND] + (1,) + h[KIND + 1:] if why == "piece" else h for h in new.hist]:
            k = seen.get(h[N])                               # one sighting a frame: the whole one, else the wider
            if k is None or (h[KIND], -h[W]) < (k[KIND], -k[W]):
                seen[h[N]] = h
        old.hist = [seen[k] for k in sorted(seen)]
        old.seen = len(old.hist)
        for k, v in new.ev.items():
            old.ev[k] += v
        if why == "back":
            old.wc.update(new.wc)
            old.hc.update(new.hc)
            old.rest.update(new.rest)
            old.clean += new.clean
            old.x, old.y, old.t, old.n, old.unseen, old.vx = new.x, new.y, new.t, new.n, 0.0, new.vx
            old.sx, old.sy, old.wlast, old.merged = new.sx, new.sy, new.wlast, new.merged
        self.done.append(new)

    def _update(self, tr, d, n, t, moved, shared=False, new=False):
        whole = not d.cut and not shared
        if whole:                                            # its own width: the commonest whole one
            c = tr.wc[d.w] = tr.wc[d.w] + 1
            if not tr.known or c > tr.wc[tr.w]:
                tr.w, tr.known = d.w, True
            c = tr.hc[d.h] = tr.hc[d.h] + 1
            if c > tr.hc[tr.h] or tr.hc[tr.h] == 0:
                tr.h = d.h
        elif not tr.known and not shared and d.w > tr.w:
            tr.w = d.w                                       # nothing whole seen yet: at least this wide
        full = abs(d.w - tr.w) <= W_TOL and not shared
        py = tr.y
        if full or new:
            x = d.cx
        else:                                                # a piece, or a wider box: the edge that kept its place
            pl, pr = tr.px - tr.w / 2.0, tr.px + tr.w / 2.0
            el, er = abs(d.L - pl), abs(d.R - pr)
            if min(el, er) <= G0:
                x = d.L + tr.w / 2.0 if el <= er else d.R - tr.w / 2.0
            elif d.w > tr.w:
                x = min(max(tr.px, d.L + tr.w / 2.0), d.R - tr.w / 2.0)
            else:
                x = tr.px
        y = d.T if new or abs(d.T - tr.y) <= abs(d.T + d.h - tr.y - tr.h) else d.T + d.h - tr.h
        if not shared:
            d.tr = tr
            tr.wlast = d.w
        gap = tr.unseen
        tr.x, tr.y, tr.unseen = x, y, 0.0
        tr.seen += 1
        tr.merged = shared
        tr.shared += shared
        tr.clean += whole and full
        e = tr.ev
        if d.mob:
            e["mob"] += 1
        if d.mobbox:
            e["mobbox"] += 1
        if d.npc:
            e["npc"] += 1
        if d.above:
            e["above"] += 1
        if d.logrow:
            e["logrow"] += 1
        if d.blob == 0:
            e["b0"] += 1                                     # nothing stands on it
        elif d.body > 0:
            k = "bs" if d.body < BODY_TALL else "bt"
            e[k] += 1
            if whole and full:                               # the tag whole and alone: its centre is its owner's
                e[k + "1"] += 1
        h = tr.hist
        if moved and tr.sx is not None and tr.n == n - 1 and not shared:
            tr.scr[1] += 1
            tr.scr[0] += d.x == tr.sx and d.y == tr.sy
            tr.mapst[1] += 1
            tr.mapst[0] += x == h[-1][X] and y == h[-1][Y]
        tr.sx, tr.sy = d.x, d.y
        if full and whole and not new and gap == 0.0 and y == py and d.off is not None and abs(d.off) <= 30:
            tr.rest[int(round(d.off))] += 1
        h.append((n, t, x, y, d.w, d.h, 0 if full and whole else 1, d.off, d.x, d.y, d.body))
        k = h[-6] if len(h) >= 6 else h[0]                   # its sideways speed over the last 5 frames
        tr.vx = max(-300.0, min(300.0, (x - k[X]) / (t - k[T]))) if 0.03 < t - k[T] <= 0.15 else 0.0
        tr.t, tr.n = t, n

    def finish(self):
        for tr in self.live:
            tr.end = "capture end"
            self.done.append(tr)
        self.live = []
        self.done.sort(key=lambda tr: tr.id)
        return [tr for tr in self.done if tr.into is None]


def run(F, cover=1.0, use_width=True, minimap=MINIMAP_DEFAULT, timed=False):
    """-> (the tracker, its tracks, the ground, the mob tags learned, ms per frame when timed)."""
    rows = F["rows"]
    g = Ground(F["map"])
    mt = learn_mob_tags(rows)
    trk = Tracker(g, View(minimap), mt, cover, use_width)
    ms = []
    last_t = None
    for n, t, C, own, tags, fit, bodies in rows:
        dt = 0.0 if last_t is None else max(0.0, t - last_t)
        last_t = t
        a = time.perf_counter()
        trk.step(n, t, C, own, tags, fit, bodies, dt)
        if timed:
            ms.append(1000 * (time.perf_counter() - a))
    return trk, trk.finish(), g, mt, ms


def final(tr):
    while tr.into is not None:
        tr = tr.into
    return tr


def name_vote(tracks) -> dict:
    """An option, not in the classes above: one name = one width, so the bodies seen over a width's tracks of the
    whole stay vote the NAME's class (pet when 30 % of them or more are small). -> {width: (class, small, tall,
    tracks)} for the widths with 50 bodies or more; a track of another class than its name's would flip."""
    pool = defaultdict(lambda: [0, 0, 0])
    for tr in tracks:
        if tr.cls() in ("player", "pet"):
            p = pool[tr.w]
            p[0] += tr.ev["bs1"]
            p[1] += tr.ev["bt1"]
            p[2] += 1
    return {w: ("pet" if s >= 0.3 * (s + t) else "player", s, t, k) for w, (s, t, k) in pool.items() if s + t >= 50}


# ------------------------------------------------------------------------------------------------ the numbers
def n1_classes(trk, rows) -> dict:
    """1. Tags per frame by class."""
    per = {c: [] for c in CLASSES}
    cache = {}
    tot = Counter()
    for rec in trk.frames:
        if rec is None:
            continue
        c = Counter()
        for who, raw, *_rest in rec:
            if isinstance(who, str):
                k = "ours" if who.startswith("ours") else who
            elif who is None:
                k = "none"
            else:
                f = final(who)
                k = cache.get(f.id)
                if k is None:
                    k = cache[f.id] = f.cls()
            c[k] += raw
        for k in CLASSES:
            per[k].append(c[k])
        tot.update(c)
    all_ = sum(tot.values())
    out = {"tags": all_, "frames": len(per["ours"]), "blind": sum(1 for r in trk.frames if r is None),
           "ours_by_list_only": sum(1 for rec in trk.frames if rec for who, *_ in rec if who == "ours*")}
    print(f"1. TAGS: {all_} on {out['frames']} frames with a camera ({out['blind']} blind); all classes together per "
          f"frame p50 / p99 / max {pct(np.sum([per[k] for k in CLASSES], axis=0), (50, 99, 100))}")
    for k in CLASSES:
        v = per[k]
        out[k] = {"tags": tot[k], "share": round(tot[k] / max(1, all_), 4), "p50_p99_max": pct(v, (50, 99, 100)),
                  "frames_with": int(np.count_nonzero(v))}
        print(f"   {k:8} {tot[k]:7d} tags ({100 * tot[k] / max(1, all_):5.1f} %); per frame p50 / p99 / max "
              f"{pct(v, (50, 99, 100))}; on {np.count_nonzero(v)} frames")
    print(f"   our tag found only by the list (FrameFacts.tag None, a list tag where ours was): {out['ours_by_list_only']} frames")
    return out


def gaps_of(tr, cam):
    """The track's gaps: [(first missing frame's index in rows, frames with a camera, seconds, sighting before)]."""
    out = []
    h = tr.hist
    for a, b in zip(h, h[1:]):
        if b[N] - a[N] > 1:
            k = int(cam[1][b[N]] - cam[1][a[N]] - 1) if cam is not None else b[N] - a[N] - 1
            if k > 0:
                out.append((a[N] + 1, k, (b[T] - a[T]) * k / (b[N] - a[N]), a, b))
    return out


def n2_tracks(tracks, rows, cover) -> dict:
    """2. Player tracks: how many, how long, how many at once, found share, gaps."""
    ns = np.array([r[0] for r in rows])
    ok = np.array([r[2] is not None for r in rows])
    cum = np.zeros(int(ns.max()) + 2)
    cum[ns[ok] + 1] = 1
    cum = np.cumsum(cum)                                    # cum[n + 1] = frames with a camera up to n
    cam = (ns, cum[1:])
    pl = [tr for tr in tracks if tr.cls() == "player"]
    life = [tr.hist[-1][T] - tr.t0 for tr in pl]
    at = np.zeros(int(ns.max()) + 2)
    for tr in pl:
        at[tr.n0] += 1
        at[tr.hist[-1][N] + 1] -= 1
    at = np.cumsum(at)[ns[ok]]
    found, whole, g_all, long_ = [], [], [], []
    tot_f = tot_s = tot_w = 0
    for tr in pl:
        fr = int(cam[1][tr.hist[-1][N]] - cam[1][tr.n0] + 1)
        tot_f += fr
        tot_s += tr.seen
        tot_w += sum(1 for h in tr.hist if h[KIND] == 0)
        found.append(tr.seen / fr)
        whole.append(sum(1 for h in tr.hist if h[KIND] == 0) / fr)
        for g in gaps_of(tr, cam):
            g_all.append(g)
            if g[2] > 0.3:
                long_.append((tr, g))
    gs = np.array([g[2] for g in g_all])
    gf = np.array([g[1] for g in g_all])
    hist = {"1 frame": int((gf == 1).sum()), "<= 0.1 s": int(((gf > 1) & (gs <= 0.1)).sum()),
            "<= 0.3 s": int(((gs > 0.1) & (gs <= 0.3)).sum()), "<= 1 s": int(((gs > 0.3) & (gs <= 1.0)).sum()),
            "longer": int((gs > 1.0).sum())}
    miss = {"1 frame": int(gf[gf == 1].sum()), "<= 0.1 s": int(gf[(gf > 1) & (gs <= 0.1)].sum()),
            "<= 0.3 s": int(gf[(gs > 0.1) & (gs <= 0.3)].sum()), "<= 1 s": int(gf[(gs > 0.3) & (gs <= 1.0)].sum()),
            "longer": int(gf[gs > 1.0].sum())}
    ends = Counter(tr.end.split(":")[0] for tr in pl)
    born = Counter(tr.born for tr in pl)
    out = {"tracks": len(pl), "life_s": pct(life, (10, 25, 50, 75, 90, 100)), "life_sum_s": round(float(np.sum(life)), 1),
           "at_once": pct(at, (50, 99, 100)), "frames_with_a_player": round(float(np.mean(at > 0)), 4),
           "player_frames": tot_f, "found": round(tot_s / max(1, tot_f), 4), "whole": round(tot_w / max(1, tot_f), 4),
           "found_per_track": pct(found, (10, 50, 90)), "gaps": hist, "gap_frames": miss, "ends": dict(ends),
           "born": dict(born)}
    print(f"2. PLAYER TRACKS: {len(pl)}; life s p10 / p25 / p50 / p75 / p90 / max {out['life_s']} (sum {out['life_sum_s']} s); "
          f"lives < 1 s {sum(1 for v in life if v < 1)}, 1-5 s {sum(1 for v in life if 1 <= v < 5)}, 5-30 s "
          f"{sum(1 for v in life if 5 <= v < 30)}, >= 30 s {sum(1 for v in life if v >= 30)}")
    print(f"   in view at once p50 / p99 / max {out['at_once']}; frames with at least one {100 * out['frames_with_a_player']:.1f} %")
    print(f"   inside a track's life: {tot_f} player-frames, the tag found on {100 * out['found']:.1f} % (whole, alone and "
          f"its own width on {100 * out['whole']:.1f} %); per track p10 / p50 / p90 {out['found_per_track']}")
    print(f"   gaps (count; frames missed): " + "; ".join(f"{k}: {hist[k]} ({miss[k]})" for k in hist))
    print(f"   born {dict(born)}; ended {dict(ends)}")
    return out, pl, cam, long_


def n3_identity(trk, tracks, pl, g, rows, cam) -> dict:
    """3. Identity: tracks close to each other, widths kept, births / ends in view."""
    # (a) one width for life
    keep = []
    for tr in pl:
        tot = sum(tr.wc.values())
        if tot:
            keep.append(sum(v for w, v in tr.wc.items() if abs(w - tr.w) <= W_TOL) / tot)
    keep = np.array(keep)
    # (b) pairs within 40 px (feet = centre x, top y): by frame
    pos = defaultdict(dict)                                  # n -> {track id: (x, y, kind)}
    for tr in pl:
        for h in tr.hist:
            pos[h[N]][tr.id] = (h[X], h[Y], h[KIND])
    by_id = {tr.id: tr for tr in pl}
    near = defaultdict(list)                                 # (a, b) -> [n]
    for n, d in pos.items():
        if len(d) < 2:
            continue
        ids = sorted(d)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if (d[a][0] - d[b][0]) ** 2 + (d[a][1] - d[b][1]) ** 2 <= 1600:
                    near[(a, b)].append(n)
    enc = []                                                 # encounters: runs of near frames, a break < 30 frames joins
    for (a, b), fr in near.items():
        fr.sort()
        s = p = fr[0]
        k = 1
        for n in fr[1:] + [None]:
            if n is not None and n - p <= 30:
                p = n
                k += 1
                continue
            enc.append((a, b, s, p, k))
            if n is not None:
                s = p = n
                k = 1
    swaps, same_w, sharedf = [], 0, 0
    for a, b, s, e, k in enc:
        ta, tb = by_id[a], by_id[b]
        if abs(ta.w - tb.w) <= W_TOL:
            same_w += 1

        def mode(tr, lo, hi):
            c = Counter(h[W] for h in tr.hist if lo <= h[N] <= hi and h[KIND] == 0)
            return c.most_common(1)[0][0] if c else None
        wa0, wb0 = mode(ta, s - 180, s - 1), mode(tb, s - 180, s - 1)
        wa1, wb1 = mode(ta, e + 1, e + 180), mode(tb, e + 1, e + 180)
        if None not in (wa0, wb0, wa1, wb1) and abs(wa0 - wb0) > W_TOL and abs(wa0 - wb1) <= W_TOL and abs(wb0 - wa1) <= W_TOL:
            swaps.append((a, b, s, e, wa0, wb0))
        sharedf += sum(1 for h in ta.hist if s <= h[N] <= e and h[KIND] == 1) > 0
    # (c) a width change inside a track's life (whole sightings: the first third against the last third)
    changed = []
    for tr in pl:
        ws = [h[W] for h in tr.hist if h[KIND] == 0]
        if len(ws) < 60:
            continue
        k = len(ws) // 3
        m0, m1 = Counter(ws[:k]).most_common(1)[0], Counter(ws[-k:]).most_common(1)[0]
        if abs(m0[0] - m1[0]) > W_TOL and m0[1] >= 0.6 * k and m1[1] >= 0.6 * k:
            changed.append((tr.id, tr.n0, m0[0], m1[0]))
    # (d) births and ends in view: why
    lost = [tr for tr in pl if tr.end == "lost"]
    inview = [tr for tr in pl if tr.born == "in view"]
    why_b, why_e = Counter(), Counter()
    b_rows, e_rows = [], []
    ended = sorted(pl, key=lambda tr: tr.hist[-1][T])
    for tr in inview:
        h0 = tr.hist[0]
        why = None
        if tr.n0 == rows[0][0] or (cam is not None and cam[1][tr.n0] <= 3):
            why = "there when the camera was first found"
        if why is None:
            for o in ended:
                if o is tr or o.end not in ("lost",) or abs(o.w - tr.w) > W_TOL:
                    continue
                dt = h0[T] - o.hist[-1][T]
                if 0 < dt <= 10.0 and abs(o.hist[-1][X] - h0[X]) <= 300 and abs(o.hist[-1][Y] - h0[Y]) <= 300:
                    why = "the same width lost near here <= 10 s ago"
                    break
        if why is None:
            for o in pl:
                if o is not tr and o.n0 < tr.n0 <= o.hist[-1][N]:
                    k = next((h for h in o.hist if h[N] >= tr.n0), None)
                    if k is not None and abs(k[Y] - h0[Y]) <= 12 and abs(k[X] - h0[X]) <= (o.w + tr.w) / 2.0 + 30:
                        why = "beside another player's tag (they ran together)"
                        break
        if why is None and any(abs(h0[X] - px) <= 60 and abs(h0[Y] - py) <= 80 for px, py, _ in g.portals):
            why = "at a portal"
        why = why or "other"
        why_b[why] += 1
        b_rows.append((tr, why))
    for tr in lost:
        h1 = tr.hist[-1]
        why = None
        for o in pl:
            if o is tr or abs(o.w - tr.w) > W_TOL or o.born != "in view":
                continue
            dt = o.hist[0][T] - h1[T]
            if 0 < dt <= 10.0 and abs(o.hist[0][X] - h1[X]) <= 300 and abs(o.hist[0][Y] - h1[Y]) <= 300:
                why = "the same width is back near here <= 10 s later (a new id)"
                break
        if why is None:
            for o in pl:
                if o is not tr and o.n0 <= h1[N] < o.hist[-1][N]:
                    k = next((h for h in o.hist if h[N] >= h1[N]), None)
                    if k is not None and abs(k[Y] - h1[Y]) <= 12 and abs(k[X] - h1[X]) <= (o.w + tr.w) / 2.0 + 30:
                        why = "beside another player's tag (they ran together)"
                        break
        if why is None and any(abs(h1[X] - px) <= 60 and abs(h1[Y] - py) <= 80 for px, py, _ in g.portals):
            why = "at a portal"
        why = why or "other"
        why_e[why] += 1
        e_rows.append((tr, why))
    out = {"one_width": {">= 95 %": int((keep >= 0.95).sum()), ">= 80 %": int((keep >= 0.8).sum()),
                         ">= 50 %": int((keep >= 0.5).sum()), "tracks": len(keep),
                         "whole_sightings_at_own_width": round(float(np.average(keep, weights=[sum(tr.wc.values()) for tr in pl if sum(tr.wc.values())])), 4) if len(keep) else None},
           "pairs_within_40": {"frames": sum(len(v) for v in near.values()), "pairs": len(near), "encounters": len(enc),
                               "same_width": same_w, "swaps": len(swaps)},
           "width_changed_inside": changed, "born_in_view": dict(why_b), "lost_in_view": dict(why_e)}
    print(f"3. IDENTITY: of {len(keep)} player tracks, whole sightings at the track's own width (+-{W_TOL}): >= 95 % on "
          f"{out['one_width']['>= 95 %']} tracks, >= 80 % on {out['one_width']['>= 80 %']}, >= 50 % on {out['one_width']['>= 50 %']}; "
          f"pooled {out['one_width']['whole_sightings_at_own_width']}")
    print(f"   two player tracks within 40 px: {out['pairs_within_40']['frames']} frames, {len(near)} pairs, {len(enc)} "
          f"encounters ({same_w} between tracks of one width); ids swapped (each leaves with the other's width): {len(swaps)} {swaps[:6]}")
    print(f"   tracks whose width changes inside their life (first third against last third): {len(changed)} {changed[:8]}")
    print(f"   born in view {len(inview)}: {dict(why_b)}")
    print(f"   lost in view {len(lost)}: {dict(why_e)}")
    return out, b_rows, e_rows


def n5_place(pl, g, rows) -> dict:
    """5. Placement of every whole player sighting by the one rule; the walking plateau."""
    xs, ys, key = [], [], []
    for i, tr in enumerate(pl):
        for j, h in enumerate(tr.hist):
            if h[KIND] == 0:
                xs.append(h[X])
                ys.append(h[Y] - 1.0)                        # the feet: the tag's top - 1
                key.append((i, j))
    out = {"sightings": len(xs)}
    if not xs:
        print("5. PLACEMENT: no whole player sightings")
        return out
    xs, ys = np.array(xs), np.array(ys)
    node = np.empty(len(xs), int)
    off = np.empty(len(xs))
    rope = np.empty(len(xs), int)
    rdx = np.empty(len(xs))
    for a in range(0, len(xs), 20000):
        nd, of, un, rp, rx = g.place(xs[a:a + 20000], ys[a:a + 20000])
        node[a:a + 20000], off[a:a + 20000], rope[a:a + 20000], rdx[a:a + 20000] = nd, of, rp, rx
    # vertical motion: the off of the same track's previous frame
    prev = np.full(len(xs), np.nan)
    at = {k: i for i, k in enumerate(key)}
    nn = np.array([pl[i].hist[j][N] for i, j in key])
    for idx, (i, j) in enumerate(key):
        if j and pl[i].hist[j - 1][N] == nn[idx] - 1 and (i, j - 1) in at:
            prev[idx] = off[at[(i, j - 1)]]
    near = np.abs(off) <= STAND_TOL
    still = np.isnan(prev) | (np.abs(off - prev) <= 1.0)
    stand = near & still
    on_rope = (rope >= 0) & ~stand
    air = ~stand & ~on_rope
    n = len(xs)
    out.update({"stand": round(float(stand.mean()), 4), "air": round(float(air.mean()), 4),
                "rope": round(float(on_rope.mean()), 4), "stand_no_prev_frame": int((near & np.isnan(prev)).sum()),
                "passing_a_surface": int((near & ~still).sum()),
                "stand_off0": round(float((off[stand] == 0).mean()), 4) if stand.any() else None,
                "stand_off_le1": round(float((np.abs(off[stand]) <= 1).mean()), 4) if stand.any() else None,
                "stand_off": dict(sorted(Counter(int(round(v)) for v in off[stand]).items())),
                "rope_dx": dict(sorted(Counter(int(round(v)) for v in rdx[on_rope]).items()))})
    print(f"5. PLACEMENT of {n} whole player sightings (feet = the tag's centre x, its top y - 1): stand "
          f"{100 * stand.mean():.1f} %, air {100 * air.mean():.1f} %, rope {100 * on_rope.mean():.1f} %; within "
          f"{STAND_TOL:.0f} px of a surface but moving against it (a jump passing it): {int((near & ~still).sum())}")
    if stand.any():
        print(f"   standing: off 0 on {100 * out['stand_off0']:.1f} %, |off| <= 1 on {100 * out['stand_off_le1']:.1f} %; off {out['stand_off']}")
    print(f"   on a rope: feet x - rope x {out['rope_dx']}")
    # the walking plateau: quarter-second windows, standing on one node all along, whole sightings on every frame
    v, per = [], defaultdict(list)
    for i, tr in enumerate(pl):
        h = tr.hist
        j = 0
        while j + 15 < len(h):
            a, b = h[j], h[j + 15]
            if b[N] - a[N] == 15 and all((i, k) in at and stand[at[(i, k)]] for k in range(j, j + 16)) and \
                    len({node[at[(i, k)]] for k in range(j, j + 16)}) == 1:
                s = (b[X] - a[X]) / (b[T] - a[T])
                d = [h[k + 1][X] - h[k][X] for k in range(j, j + 15)]
                if min(d) >= 0 or max(d) <= 0:               # one way all along
                    v.append(abs(s))
                    per[i].append(abs(s))
                j += 15
            else:
                j += 1
    v = np.array(v)
    walk = v[v >= 100]
    out["windows"] = len(v)
    out["walking_windows"] = len(walk)
    out["walk_px_s"] = pct(walk, (5, 25, 50, 75, 95))
    tr_p = sorted((round(float(np.median([s for s in sp if s >= 100])), 1), len([s for s in sp if s >= 100]), pl[i].w)
                  for i, sp in per.items() if len([s for s in sp if s >= 100]) >= 8)
    out["walk_per_track"] = tr_p
    print(f"   speed: {len(v)} quarter-second standing windows, {len(walk)} walking (>= 100 px/s): p5 / p25 / p50 / p75 / p95 "
          f"{out['walk_px_s']} px/s; still (< 5 px/s) {int((v < 5).sum())}")
    by_w = defaultdict(list)
    for med, k, w in tr_p:
        by_w[w].append(med)
    print("   the plateau per tag width (median of each track's walking windows, tracks with >= 8): "
          + "; ".join(f"w {w}: {np.median(m):.0f} px/s ({len(m)} tracks, {min(m):.0f}-{max(m):.0f})" for w, m in sorted(by_w.items())))
    return out


def ours_speed(rows, g) -> list:
    """Our own walking plateau by the same windows (the control: 152-157 px/s on the design capture)."""
    pts = [(n, t, own[0] + own[2] / 2.0 + C[0], own[1] + C[1] - 1.0) for n, t, C, own, *_ in rows
           if C is not None and own is not None]
    if len(pts) < 32:
        return None
    xs, ys = np.array([p[2] for p in pts]), np.array([p[3] for p in pts])
    off = np.empty(len(xs))
    node = np.empty(len(xs), int)
    for a in range(0, len(xs), 20000):
        nd, of, *_ = g.place(xs[a:a + 20000], ys[a:a + 20000])
        node[a:a + 20000], off[a:a + 20000] = nd, of
    stand = np.abs(off) <= STAND_TOL
    v = []
    j = 0
    while j + 15 < len(pts):
        a, b = pts[j], pts[j + 15]
        if b[0] - a[0] == 15 and stand[j:j + 16].all() and len(set(node[j:j + 16])) == 1:
            d = np.diff(xs[j:j + 16])
            if d.min() >= 0 or d.max() <= 0:
                v.append(abs((b[2] - a[2]) / (b[1] - a[1])))
            j += 15
        else:
            j += 1
    v = np.array(v)
    return pct(v[v >= 100], (5, 25, 50, 75, 95)) + [int((v >= 100).sum())]


def n7_covers(F, minimap, covers=(0.3, 1.0, 2.0)) -> dict:
    """7. What the cover time does: tracks, lost in view, the same width back near there with a new id."""
    out = {}
    print("7. COVER: seconds -> player tracks; lost in view; of those the same width is back within 300 px and 10 s "
          "(a new id for the same tag); gaps bridged (0.3-1 s, > 1 s)")
    for cv in covers:
        trk, tracks, g, mt, _ = run(F, cv, True, minimap)
        pl = [tr for tr in tracks if tr.cls() == "player"]
        lost = [tr for tr in pl if tr.end == "lost"]
        back = 0
        dts = []
        for tr in lost:
            h1 = tr.hist[-1]
            best = None
            for o in pl:
                if o is tr or abs(o.w - tr.w) > W_TOL or o.born != "in view":
                    continue
                dt = o.hist[0][T] - h1[T]
                if 0 < dt <= 10.0 and abs(o.hist[0][X] - h1[X]) <= 300 and abs(o.hist[0][Y] - h1[Y]) <= 300:
                    best = dt if best is None else min(best, dt)
            if best is not None:
                back += 1
                dts.append(best)
        gl = [g_[2] for tr in pl for g_ in gaps_of(tr, None)]
        out[cv] = {"tracks": len(pl), "lost_in_view": len(lost), "back_new_id": back,
                   "back_after_s": pct(dts, (25, 50, 75, 100)),
                   "gaps_03_1": sum(1 for v in gl if 0.3 < v <= 1.0), "gaps_over_1": sum(1 for v in gl if v > 1.0),
                   "all_tracks": len(tracks)}
        print(f"   {cv:3.1f} s -> {len(pl):4d} player tracks; lost in view {len(lost):4d}; back with a new id {back:4d} "
              f"(after p25 / p50 / p75 / max {pct(dts, (25, 50, 75, 100))} s); gaps bridged 0.3-1 s "
              f"{out[cv]['gaps_03_1']}, > 1 s {out[cv]['gaps_over_1']}")
    return out


# ------------------------------------------------------------------------------------------------ the sheets
def sheet(cap, moments, path, cols=5, cw=230, ch=170, zoom=2, keep=False):
    """A contact sheet: moments = [(frame n, x, y, w, h on screen, text)] -> crops around each box, the box drawn;
    in frame order unless `keep`."""
    import cv2
    import frames as rec
    c = rec.clip(str(cap), False, "proto_players")
    cells = []
    for k, (n, x, y, w, h, text) in enumerate(moments if keep else sorted(moments, key=lambda m: m[0])):
        img = rec.read(c.run, rec.name_of(n))
        if img is None:
            img = np.zeros((SH, SW, 3), np.uint8)
        cx, cy = int(x + w / 2), int(y + h / 2)
        x0 = min(max(0, cx - cw // 2), img.shape[1] - cw)
        y0 = min(max(0, cy - ch + 45), img.shape[0] - ch)
        crop = img[y0:y0 + ch, x0:x0 + cw].copy()
        crop = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
        cv2.rectangle(crop, (int(x - x0) * zoom - 2, int(y - y0) * zoom - 2),
                      (int(x - x0 + w) * zoom + 1, int(y - y0 + h) * zoom + 1), (0, 255, 255), 1)
        for i, line in enumerate((f"#{k} n{n}", text)):
            cv2.putText(crop, line, (4, 15 + 16 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
            cv2.putText(crop, line, (4, 15 + 16 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cells.append(crop)
    if not cells:
        return None
    while len(cells) % cols:
        cells.append(np.zeros_like(cells[0]))
    img = np.vstack([np.hstack(cells[i:i + cols]) for i in range(0, len(cells), cols)])
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    return path


def sheets(cap, trk, tracks, seed=1) -> dict:
    """4. The by-eye sheets: 40 random player-track moments, 20 of each other class. -> the moments chosen."""
    rnd = random.Random(seed)
    by = defaultdict(list)                                   # class -> [(n, x, y, w, h, text)]
    cls_of = {}
    rows_n = None
    for i, rec in enumerate(trk.frames):
        if rec is None:
            continue
        for who, raw, x, y, w, h, *body in rec:
            if isinstance(who, str):
                k, tid = ("ours" if who.startswith("ours") else who), 0
            elif who is None:
                k, tid = "none", 0
            else:
                f = final(who)
                if f.id not in cls_of:
                    cls_of[f.id] = f.cls()
                k, tid = cls_of[f.id], f.id
            by[k].append((i, x, y, w, h, tid, body[0] if body else -1))
    out = {}
    name = cap.replace("#", "_")
    for k, v in by.items():
        want = 40 if k == "player" else 20
        pick = rnd.sample(v, min(want, len(v)))
        mom = [(trk.n_of[i], x, y, w, h, f"{k} id{tid} {w}x{h} b{b}") for i, x, y, w, h, tid, b in pick]
        out[k] = sorted(mom)
        for part in range(0, len(mom), 20):
            p = sheet(cap, sorted(mom)[part:part + 20], out_dir() / f"{name}_{k}_{part // 20 + 1}.png")
            print(f"   sheet {p}")
    # one moment from each of 40 random player tracks (the short ones get looked at too)
    pl = [tr for tr in tracks if tr.cls() == "player"]
    mom = []
    for tr in rnd.sample(pl, min(40, len(pl))):
        h = rnd.choice(tr.hist)
        mom.append((h[N], h[SX], h[SY], h[W], h[H], f"player id{tr.id} {h[W]}x{h[H]} life {tr.hist[-1][T] - tr.t0:.1f}s"))
    out["player_by_track"] = sorted(mom)
    for part in range(0, len(mom), 20):
        p = sheet(cap, sorted(mom)[part:part + 20], out_dir() / f"{name}_player-by-track_{part // 20 + 1}.png")
        print(f"   sheet {p}")
    # the option "class by name": 20 moments of the tracks it would turn each way
    names = name_vote(tracks)
    for a, b in (("player", "pet"), ("pet", "player")):
        v = [(tr, h) for tr in tracks if tr.cls() == a and names.get(tr.w, (a,))[0] == b for h in tr.hist]
        mom = [(h[N], h[SX], h[SY], h[W], h[H], f"{a}>{b} by name id{tr.id} w{tr.w} b{h[BODY]}")
               for tr, h in rnd.sample(v, min(20, len(v)))]
        out[f"name_{a}_to_{b}"] = sorted(mom)
        if mom:
            print(f"   sheet {sheet(cap, sorted(mom), out_dir() / f'{name}_name-{a}-to-{b}.png')}")
    (out_dir() / f"{name}_sheets.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def moment_sheets(cap, trk, pl, long_, b_rows, e_rows, rows, seed=2):
    """By eye, why: 24 long gaps inside player tracks (last sighting / mid-gap / first sighting again, the place
    the tag should be boxed), 12 births in view and 12 losses in view with no reason found (the frame before + the
    first / the last + 10 frames later)."""
    rnd = random.Random(seed)
    name = cap.replace("#", "_")
    cam = {r[0]: r[2] for r in rows}
    out = {}

    def at(tr, x, y, n):
        C = cam.get(n)
        return None if C is None else (int(x - tr.w / 2.0 - C[0]), int(y - C[1]), tr.w, tr.h)

    mom = []
    pick = rnd.sample(long_, min(24, len(long_)))
    out["gaps"] = []
    for k, (tr, (n0, miss, sec, a, b)) in enumerate(sorted(pick, key=lambda p: p[1][0])):
        mid = (a[N] + b[N]) // 2
        px, py = (a[X] + b[X]) / 2.0, (a[Y] + b[Y]) / 2.0
        out["gaps"].append({"gap": k, "track": tr.id, "w": tr.w, "from": a[N], "to": b[N], "s": round(sec, 2)})
        for lab, n, box in (("last", a[N], (a[SX], a[SY], a[W], a[H])), ("gap", mid, at(tr, px, py, mid)),
                            ("again", b[N], (b[SX], b[SY], b[W], b[H]))):
            if box is not None:
                mom.append((n, *box, f"gap{k:02d} {lab} id{tr.id} w{tr.w} {sec:.2f}s"))
    for part in range(0, len(mom), 24):
        print(f"   sheet {sheet(cap, mom[part:part + 24], out_dir() / f'{name}_gaps_{part // 24 + 1}.png', cols=6, cw=190, ch=130, keep=True)}")
    for what, lst in (("born", [r for r in b_rows if r[1] == "other"]), ("lost", [r for r in e_rows if r[1] == "other"])):
        mom = []
        out[what] = []
        for k, (tr, why) in enumerate(sorted(rnd.sample(lst, min(12, len(lst))), key=lambda r: r[0].n0)):
            if what == "born":
                h = tr.hist[0]
                frames = ((h[N] - 1, "before"), (h[N], "first"))
            else:
                h = tr.hist[-1]
                frames = ((h[N], "last"), (h[N] + 10, "+10"))
            out[what].append({"k": k, "track": tr.id, "w": tr.w, "n": h[N]})
            for n, lab in frames:
                box = at(tr, h[X], h[Y], n)
                if box is not None:
                    mom.append((n, *box, f"{what}{k:02d} {lab} id{tr.id} w{tr.w} life {tr.hist[-1][T] - tr.t0:.1f}s"))
        print(f"   sheet {sheet(cap, mom, out_dir() / f'{name}_{what}-in-view.png', cols=6, cw=190, ch=130, keep=True)}")
    (out_dir() / f"{name}_moments.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def frame_sheets(cap, trk, rows, k=21, seed=3):
    """Whole frames with every tag boxed by class (for counting, by eye, the players the tags did not give):
    player green, pet cyan, ours white, mob red, log grey, anything else magenta."""
    import cv2
    import frames as rec
    rnd = random.Random(seed)
    c = rec.clip(str(cap), False, "proto_players")
    col = {"player": (0, 255, 0), "pet": (255, 255, 0), "ours": (255, 255, 255), "mob": (0, 0, 255), "log": (150, 150, 150)}
    idx = sorted(rnd.sample([i for i, r in enumerate(trk.frames) if r is not None], k))
    name = cap.replace("#", "_")
    out, cells = [], []
    for i in idx:
        n = rows[i][0]
        img = rec.read(c.run, rec.name_of(n))
        counts = Counter()
        for who, raw, x, y, w, h, *_ in trk.frames[i]:
            cl = ("ours" if who.startswith("ours") else who) if isinstance(who, str) else "none" if who is None else final(who).cls()
            counts[cl] += 1
            cv2.rectangle(img, (x - 2, y - 2), (x + w + 1, y + h + 1), col.get(cl, (255, 0, 255)), 2)
            cv2.putText(img, cl if isinstance(who, str) or who is None else f"{cl} {final(who).id}", (x, y + h + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col.get(cl, (255, 0, 255)), 1)
        cv2.putText(img, f"n{n}  {dict(counts)}", (300, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cells.append(cv2.resize(img[:PLAY_H + 68], None, fx=0.75, fy=0.75, interpolation=cv2.INTER_AREA))
        out.append({"n": n, "classes": dict(counts)})
    for part in range(0, len(cells), 3):
        p = out_dir() / f"{name}_frames_{part // 3 + 1}.png"
        cv2.imwrite(str(p), np.vstack(cells[part:part + 3]))
        print(f"   sheet {p}")
    (out_dir() / f"{name}_frames.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def table(tracks, only=None):
    print(f"   {'id':>5} {'class':8} {'n0':>6} {'life s':>6} {'seen':>5} {'share':>5} {'w':>4} {'w%':>4} {'h':>3} "
          f"{'rest off':18} {'ev':44} {'scr':9} {'born':8} {'end':12} x range, y range")
    for tr in tracks:
        if tr.seen < MIN_SEEN or (only and tr.cls() not in only):
            continue
        frames = tr.hist[-1][N] - tr.hist[0][N] + 1
        wn = sum(v for w, v in tr.wc.items() if abs(w - tr.w) <= W_TOL)
        xs = [h[X] for h in tr.hist]
        ys = [h[Y] for h in tr.hist]
        print(f"   {tr.id:5d} {tr.cls():8} {tr.n0:6d} {tr.hist[-1][T] - tr.t0:6.1f} {tr.seen:5d} {tr.seen / frames:5.2f} "
              f"{tr.w:4d} {100 * wn / max(1, sum(tr.wc.values())):4.0f} {tr.h:3d} {str(tr.rest.most_common(2)):18} "
              f"{str(dict(tr.ev)):44} {str(tr.scr):9} {tr.born:8} {tr.end:12} "
              f"{min(xs):.0f}..{max(xs):.0f}, {min(ys):.0f}..{max(ys):.0f}")


def report(cap, a) -> dict:
    F = frames_of(cap)
    rows = F["rows"]
    mm = F["minimap"]
    if a.time:
        try:
            from maplebrain.procperf import prefer_performance
            print("   pinned:", prefer_performance())
        except Exception as e:                              # noqa: BLE001
            print("   not pinned:", e)
    trk, tracks, g, mt, ms = run(F, a.cover, not a.no_width, mm, timed=a.time)
    trk.n_of = [r[0] for r in rows]
    t0, t1 = rows[0][1], rows[-1][1]
    print(f"== {cap}: {g.name} ({F['map']}), {len(rows)} frames, {t1 - t0:.0f} s; minimap {mm}; cover {a.cover} s; "
          f"{'width + position' if not a.no_width else 'position alone'}")
    print(f"   mobs' own tags learned (kind: box w, h, centre x - feet x, top y - feet y, sightings, share of the tags "
          f"near that kind's feet): {mt}")
    out = {"cap": cap, "map": F["map"], "name": g.name, "frames": len(rows), "seconds": round(t1 - t0, 1),
           "minimap": mm, "cover": a.cover, "mob_tags": {str(k): v for k, v in mt.items()}}
    out["classes"] = n1_classes(trk, rows)
    by_cls = Counter(tr.cls() for tr in tracks)
    out["tracks_by_class"] = dict(by_cls)
    print(f"   tracks by class: {dict(by_cls)}; {dict(trk.stats)}")
    names = name_vote(tracks)
    flip = [tr for tr in tracks if tr.cls() in ("player", "pet") and tr.w in names and names[tr.w][0] != tr.cls()]
    out["name_vote"] = {"names": {str(w): v for w, v in sorted(names.items())},
                        "player_to_pet": [(tr.id, tr.w, tr.seen) for tr in flip if tr.cls() == "player"],
                        "pet_to_player": [(tr.id, tr.w, tr.seen) for tr in flip if tr.cls() == "pet"]}
    print(f"   option - the class by NAME (one width = one name, its tracks' bodies pooled over the stay): "
          f"{sum(1 for v in names.values() if v[0] == 'pet')} pet names {sorted(w for w, v in names.items() if v[0] == 'pet')}, "
          f"{sum(1 for v in names.values() if v[0] == 'player')} player names; it would turn "
          f"{len(out['name_vote']['player_to_pet'])} player tracks ({sum(v[2] for v in out['name_vote']['player_to_pet'])} sightings) "
          f"into pets and {len(out['name_vote']['pet_to_player'])} pet tracks "
          f"({sum(v[2] for v in out['name_vote']['pet_to_player'])} sightings) into players")
    out["tracks"], pl, cam, long_ = n2_tracks(tracks, rows, a.cover)
    out["identity"], b_rows, e_rows = n3_identity(trk, tracks, pl, g, rows, cam)
    out["placement"] = n5_place(pl, g, rows)
    out["placement"]["ours_walk_px_s"] = ours_speed(rows, g)
    print(f"   ours by the same windows: p5 / p25 / p50 / p75 / p95, windows {out['placement']['ours_walk_px_s']}")
    if ms:
        out["ms"] = pct(ms, (50, 90, 99, 100))
        print(f"6. COST: {len(ms)} frames, ms per frame p50 / p90 / p99 / max {out['ms']} (the classes, the association, "
              f"the placement of every candidate; body_over not in it)")
    if a.covers:
        out["covers"] = n7_covers(F, mm)
    if a.tracks:
        table(tracks, set(a.only.split(",")) if a.only else None)
    if a.sheets:
        print("4. SHEETS")
        sheets(cap, trk, tracks)
    return out, (trk, tracks, g, pl, cam, long_, b_rows, e_rows, rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--cover", type=float, default=1.0)
    ap.add_argument("--covers", action="store_true")
    ap.add_argument("--no-width", action="store_true")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--tracks", action="store_true")
    ap.add_argument("--only", default="", help="--tracks: only these classes (comma separated)")
    ap.add_argument("--time", action="store_true")
    a = ap.parse_args()
    import cache
    caps = cache.SOUND if a.sound else a.caps
    res = {}
    for cap in caps:
        res[cap] = report(cap, a)[0]
    name = "sound" if a.sound else caps[0].replace("#", "_") if len(caps) == 1 else "several"
    p = out_dir() / f"report_{name}{'_nowidth' if a.no_width else ''}.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"-> {p}")


if __name__ == "__main__":
    main()
