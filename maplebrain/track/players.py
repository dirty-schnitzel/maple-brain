"""Other players from their name tags (PLAN-tracker.md design 6, measurement 7; docs/state_model.md "Every other
player"). The reference is the prototype tools/perc/track/proto_players.py: its rules and constants (config.Track) are
ported, not redesigned. The placement is the graph's one rule (track/graph.py); "what stands on a tag" comes from the
evidence (track/evidence.py `columns`: the kept replay's bitmaps or the fit's own tensors). Nothing here knows the
brain.

Per frame, `update(facts, evidence, ours)`: FrameFacts' tags (tags.find_tags: a row of light glyphs on a darkened box),
the fit's mobs, D's blobs (`patches`), the camera, and OUR tag as track/us.py found it -> the tag list SORTED (one
class per tag of the list: `tag_class`), the player records (track/state.Player) and this frame's events.
  1. Each tag -> ours (over our tag; what sticks out of it is a neighbour's piece) / a line of the message log (fixed
     on the SCREEN, right-aligned) / a candidate. Candidates on one row put together (a ladder's rail cuts a tag in
     two), each with its evidence: under a seen mob's feet at its kind's own tag box (the mob's "Lv. N name" tag),
     near an NPC of map.json, 12-45 px over another tag (a pattern on a character's clothes), and what STANDS on it:
     the body's height over its centre (a character ~70 px, a pet ~40; `columns`) and how far D's blob reaches over
     it (0: text drawn over the world).
  2. Candidates follow tracks in MAP coordinates (one tag's life = one id), nearest first: a tag of the track's own
     width (its name: constant for one name) by its centre, a narrower or wider box by the edge that kept its place.
     TWO TAGS SIDE BY SIDE (find_tags joins text at most 7 px apart) are split by the widths already known: the box
     goes to one track, the other track is placed inside it by its own width at the edge that kept its place (and
     both are drawn there for the mob tracker's covers); a box as wide as both, when they are not both sure, is two
     pieces of one tag. A young track that now shows the width of an older one still covered nearby is that one back.
  3. A track's CLASS is voted over its sightings so far, every frame (the prototype voted over the whole life in
     hindsight): mob / pattern / npc / text (nothing stands on it, or it stays put on the screen while the camera
     moves) / pet (a short body) / player (a tall body) / unsure (no body readable) / short (under tag_min_seen
     sightings). Pets are sorted out, not tracked (the user, 2026-11-24, question 4): their class stays, so a later
     step can track them without re-sorting.
  4. A track not found is kept up to player_cover_s (2 s: the user, question 5) while its place is in view, and ends
     at once when its place is at the screen's edge or under the UI. A blind frame changes nothing.
  5. A player's feet = the tag's centre x, its top y - 1, placed by the one rule (stand / air / rope: it climbs).
Mob kinds' own tag boxes are LEARNED while running (the prototype learned them over the whole capture first): the
commonest (w, h, dx, dy) of the tags 0-4 px under a seen mob's feet, known after mob_tag_n near it (once known, the
commonest is looked at again every 30th sighting).
Events: player_new (a track's class first becomes player), player_left (a player's track ends; how: lost in view /
at the edge / under the UI).
"""
from collections import Counter, defaultdict

import numpy as np

from ..config import Track
from .graph import NONE, PLACES
from .state import Player

SW, SH, PLAY_H = 1366, 768, 700
KIND_WHOLE, KIND_PART = 0, 1
CLASSES = ("ours", "log", "mob", "npc", "text", "pet", "pattern", "player", "unsure", "short", "none")


def sorted_boxes(ours, drawn, c: Track) -> dict:
    """The mob tracker's cover boxes from the sorted tag list (screen px x0, y0, x1, y1): "us" = our body around our
    tag (track/us.py's box), "player" = every other character and pet at its own width (Players.drawn). A pet is
    named a player's cover: the cover names have no pet (state.COVERS) and it is a player's thing over the mob."""
    us = []
    if ours is not None:
        x, y, w, h = ours[:4]
        mx = x + w / 2
        us.append((mx + c.us_box[0], y + c.us_box[1], mx + c.us_box[2], y + c.us_box[3]))
    return {"us": us, "player": [b[1:] for b in drawn]}


class Det:
    """One tag of a frame (pieces on one row put together): its box on screen and on the map, its evidence, the
    list's tags it is made of (`raws`)."""
    __slots__ = ("x", "y", "w", "h", "L", "R", "T", "cx", "cut", "joined", "nobirth", "logrow", "off", "mob", "npc",
                 "above", "tr", "raw", "body", "blob", "mobbox", "raws")

    def __init__(self, x, y, w, h, body=(-1, -1), raws=()):
        self.x, self.y, self.w, self.h, self.raw = x, y, w, h, 1
        self.body, self.blob = body                      # the body's height over it, D's blob over it
        self.cut = self.joined = self.nobirth = self.logrow = self.mob = self.npc = self.above = self.mobbox = False
        self.off, self.tr = None, None
        self.raws = list(raws)

    def to_map(self, cx0, cy0):
        self.L, self.R, self.T, self.cx = self.x + cx0, self.x + self.w + cx0, self.y + cy0, self.x + self.w / 2.0 + cx0


class _Track:
    __slots__ = ("id", "x", "y", "w", "h", "wc", "hc", "t", "n", "t0", "n0", "unseen", "seen", "ev", "hist", "born",
                 "end", "sx", "sy", "scr", "merged", "wlast", "clean", "into", "vx", "px", "known", "shared", "place",
                 "node", "from_node", "off", "vy", "was_player", "cls_now")

    def __init__(self, tid, d, t, n):
        self.id = tid
        self.x, self.y, self.w, self.h = d.cx, d.T, d.w, d.h
        self.vx, self.vy, self.px = 0.0, 0.0, d.cx
        self.wc, self.hc = Counter(), Counter()
        self.known = False               # its own width was seen (a whole sighting); until then w = the widest piece
        self.t = self.t0 = t
        self.n = self.n0 = n
        self.unseen = 0.0                # seconds of frames with a camera since it was last seen
        self.seen = 0
        self.clean = 0                   # sightings whole, alone and of its own width
        self.shared = 0                  # sightings inside a box another track took
        self.ev = Counter()              # evidence counts: mob, mobbox, npc, above, logrow, b0 / bs / bt (+1: whole)
        self.hist = []                   # (n, t, x, y, w, h, whole 0 / part 1)
        self.born = self.end = ""
        self.sx = self.sy = None         # its last box corner on screen
        self.scr = [0, 0]                # frames the camera moved: [its screen place stayed, all]
        self.merged = False              # its last sighting was inside a box shared with another track
        self.wlast = d.w
        self.into = None                 # the track this one turned out to be a piece / the re-appearance of
        self.place, self.node, self.from_node, self.off = 1, NONE, NONE, float("nan")
        self.was_player = False
        self.cls_now = "short"

    def cls(self, c: Track) -> str:
        """Its class by what was seen of it so far (the prototype's Track.cls)."""
        s, e = self.seen, self.ev
        if s < c.tag_min_seen or self.clean < c.tag_confirm:
            return "short"
        if 2 * e["mob"] >= s or (e["mob"] >= 3 and 2 * e["mobbox"] >= s):
            return "mob"                                     # under a seen mob's feet / a mob tag's box, seen so 3 times
        if 2 * e["above"] >= s:
            return "pattern"
        if 2 * e["npc"] >= s:
            return "npc"
        if (e["b0"] >= 3 and e["b0"] >= e["bs"] + e["bt"]) or (self.scr[1] >= 5 and self.scr[0] >= 0.8 * self.scr[1]):
            return "text"                                    # nothing stands on it / it stays put on the screen
        one, body = e["bs1"] + e["bt1"], e["bs"] + e["bt"]   # the body's height: on its whole sightings, else all
        if one >= 5:
            return "pet" if 2 * e["bs1"] >= one else "player"
        if body >= 5:
            return "pet" if 2 * e["bs"] >= body else "player"
        return "unsure"                                      # no body could be read (under the play area, at the UI)


def col_body(over, world, inside, top, c: Track) -> int:
    """proto_players.col_body from `columns`' counts for one tag (rows over its top, bottom row last): the height of
    what stands on it - read upward from the tag's top until a break of more than body_gap rows. 0: nothing over its
    centre; -1: cannot be told (the tag under the play area, or less than 60 % of those columns are world)."""
    rows = inside > 0
    nr = int(rows.sum())
    if nr < 20 or (inside.max() if nr else 0) < 8 or top > PLAY_H + 6 or world.sum() < 0.6 * inside.sum():
        return -1
    r0 = int(np.argmax(rows))                            # the first row inside (rows inside are one run)
    hs = np.flatnonzero(over[r0:r0 + nr] >= 4)           # the rows with something drawn, upward from the bottom:
    if not len(hs) or nr - 1 - hs[-1] > c.body_gap:      # the run up to the first break of more than body_gap rows
        return 0
    bad = np.flatnonzero(np.diff(hs) - 1 > c.body_gap)
    top_i = r0 + int(hs[bad[-1] + 1] if len(bad) else hs[0])
    return int(len(over) - top_i)


class Players:
    """`graph`: the map's track/graph.Graph; `ui`: the screen rectangles the tag finder cannot see (the minimap window
    as measured + hud.UI_RECTS' others); `npcs`: map.json's NPCs [(x, y)]. `keep` True: ended tracks are kept
    (`done`) and every frame's sorting (`frames`) for the tools."""

    def __init__(self, graph, cfg: Track | None = None, ui=None, npcs=(), keep: bool = False, mob_tags=None):
        from ..perception import hud
        self.g, self.cfg, self.keep = graph, cfg or Track(), keep
        self.ui = list(ui) if ui is not None else list(hud.UI_RECTS)
        self.npcs = list(npcs)
        self.live, self.done = [], []
        self.next_id = 1
        self.prev_C = None
        self.t = None
        self.n = 0
        self.stats = Counter()
        self.fixed_mob_tags = mob_tags                   # a tool may hand the prototype's hindsight boxes
        self._mt_count = defaultdict(Counter)            # kind -> Counter((w, h, 2 dx, dy))
        self._mt_n = Counter()                           # kind -> its sightings counted
        self.mob_tags = dict(mob_tags or {})             # kind -> (w, h, dx, dy)
        self.tag_class: list = []                        # this frame: the class of each tag of facts.tags
        self.tag_track: list = []                        # ... its track id (0: none)
        self.records: list = []
        self.frames = []                                 # keep: per frame (n, tag_class, tag_track)
        self.drawn = []                                  # this frame: (class, screen box x0, y0, x1, y1) of each
        self._ev = []                                    # track seen, at its own width

    # ------------------------------------------------------------------ one frame
    def update(self, facts, evidence=None, ours=None, n=None, ui=None) -> list:
        """`ours`: our tag on the screen as track/us.py found it - (x, y, w, h, list index or None) or None; `ui`: the
        UI rectangles now (the minimap window as measured; None: as before). -> this frame's events."""
        c = self.cfg
        if ui is not None:
            self.ui = list(ui)
        t, C = facts.t, facts.scene_cam
        self.n = self.n + 1 if n is None else n
        n = self.n
        self._ev = []
        tags = [tuple(int(v) for v in tg[:4]) for tg in facts.tags or []]
        self.tag_class, self.tag_track = ["none"] * len(tags), [0] * len(tags)
        self.drawn = []
        if C is None:                                       # blind: nothing begins or ends
            self.records = self._records(t, blind=True)
            if self.keep:
                self.frames.append((n, None, None))
            return self._ev
        dt = 0.0 if self.t is None else max(0.0, t - self.t)
        self.t = t
        cx0, cy0 = C
        moved = self.prev_C is not None and (self.prev_C[0] != cx0 or self.prev_C[1] != cy0)
        self.prev_C = C
        if self.fixed_mob_tags is None:
            self._learn(tags, facts.fit)
        boxes, cand = [], []
        for i, (x, y, w, h) in enumerate(tags):
            if ours is not None:
                ox, oy, ow, oh, li = ours
                if li is not None:                           # the list's own tag that track/us.py took as ours
                    if i == li:
                        self.tag_class[i] = "ours"
                        continue
                elif y < oy + oh - 4 and y + h > oy + 4 and min(x + w, ox + ow) - max(x, ox) >= 0.4 * min(w, ow):
                    self.tag_class[i] = "ours"
                    for a, b in ((x, ox), (ox + ow, x + w)):   # what sticks out of our tag: a neighbour's piece
                        if b - a >= 10:
                            d = Det(int(a), y, int(b - a), h, raws=(i,))
                            d.nobirth = True
                            cand.append(d)
                    continue
            boxes.append((x, y, w, h, i))
        bodies = self._bodies(boxes, facts.patches, evidence)
        r0, pitch, nrows, rlo, rhi, x0log = c.log_rows
        for d in self._join(boxes, bodies):
            k, r = divmod(r0 + 1 - d.y, pitch)                # a log line: on a row of the log, right-aligned - or a
            onrow = 0 <= k < nrows and r <= 2                 # piece of one: on a row, nothing standing on it
            d.logrow = onrow and d.x + d.w / 2 >= x0log
            if onrow and (rlo <= d.x + d.w <= rhi or (d.logrow and d.blob == 0)):
                for i in d.raws:
                    self.tag_class[i] = "log"
                continue
            cand.append(d)
        for d in cand:
            d.to_map(cx0, cy0)
            d.cut = d.joined or d.nobirth or bool(self._why(d.x, d.y, d.x + d.w, d.y + d.h))
        self._evidence(cand, facts.fit)
        self._associate(cand, n, t, dt, cx0, cy0, moved)
        for tr in self.live:
            tr.cls_now = tr.cls(c)
        for d in cand:
            if d.tr is None:
                continue
            f = self._final(d.tr)
            for i in d.raws:
                if self.tag_class[i] == "none":
                    self.tag_class[i], self.tag_track[i] = f.cls_now, f.id
        self._place(t, cx0, cy0)
        self.records = self._records(t)
        if self.keep:
            self.frames.append((n, list(self.tag_class), list(self.tag_track)))
        return self._ev

    # ------------------------------------------------------------------ the tags' evidence
    def _learn(self, tags, fit):
        """Mob kinds' own tag boxes: the commonest (w, h, 2 dx, dy) of the tags within 60 px of a seen mob's feet and
        0..4 px under them (proto_players.learn_mob_tags, counted as the frames come)."""
        if not fit or not tags:
            return
        c = self.cfg
        for x, y, w, h in tags:
            cx2 = 2 * x + w
            for m in fit:
                fx, fy = m["feet"]
                if abs(cx2 - 2 * fx) <= 120 and 0 <= y - fy <= 4:
                    cc = self._mt_count[m["type"]]
                    cc[(w, h, int(round(cx2 - 2 * fx)), int(round(y - fy)))] += 1
                    k = self._mt_n[m["type"]] = self._mt_n[m["type"]] + 1
                    if m["type"] in self.mob_tags and k % 30:
                        continue                        # known: the mode looked at again every 30th sighting
                    (w0, h0, dx2, dy), _ = cc.most_common(1)[0]
                    near = sum(v for (w2, h2, d2, y2), v in cc.items() if abs(w2 - w0) <= 1 and abs(h2 - h0) <= 1
                               and abs(d2 - dx2) <= 4 and abs(y2 - dy) <= 1)
                    if near >= c.mob_tag_n:
                        self.mob_tags[m["type"]] = (w0, h0, dx2 / 2.0, dy)

    def _bodies(self, boxes, patches, evidence) -> list:
        """Per box: (the body's height over it from the evidence, D's blob over it) - proto_players' col_body and
        blob_over."""
        c = self.cfg
        out = [(-1, self._blob(b[:4], patches)) for b in boxes]
        if not boxes or evidence is None or not getattr(evidence, "ready", False):
            return out
        cx = np.array([x + w // 2 for x, y, w, h, i in boxes])
        top = np.array([y for x, y, w, h, i in boxes])
        over, world, inside = evidence.columns(cx, top, c.body_reach, c.body_half)
        return [(col_body(over[k], world[k], inside[k], int(top[k]), c), out[k][1]) for k in range(len(boxes))]

    def _blob(self, tag, patches) -> int:
        """proto_players.blob_over: how far the tallest of D's blobs that lies over the tag's centre and comes down to
        it reaches over its top. 0: nothing; -1: cannot be told (no D, the tag under the play area or near its top, or
        the place over it is UI)."""
        x, y, w, h = tag
        cx, best = x + w / 2.0, 0
        for px, py, pw, ph, *_ in patches or ():
            if px <= cx <= px + pw and py < y <= py + ph + 12 and y - py > best:
                best = y - py
        if best < self.cfg.body_tall:
            if patches is None or y > PLAY_H + 12 or y < 85:
                return -1
            for a, b, cc, d in self.ui:
                if cx - 10 < cc and cx + 10 > a and y - 85 < d and y > b:
                    return -1
        return int(best)

    def _join(self, boxes, bodies) -> list:
        """Boxes on one row (tops or bottoms within 2 px) whose gap is at most tag_join px -> one Det."""
        J = self.cfg.tag_join
        out = []
        for (x, y, w, h, i), body in sorted(zip(boxes, bodies), key=lambda p: p[0][:4]):
            for d in out:
                if x - (d.x + d.w) <= J and x + w >= d.x - J and (abs(y - d.y) <= 2 or abs(y + h - d.y - d.h) <= 2):
                    x1, y1 = max(d.x + d.w, x + w), max(d.y + d.h, y + h)
                    d.x, d.y = min(d.x, x), min(d.y, y)
                    d.w, d.h = x1 - d.x, y1 - d.y
                    d.raw += 1
                    d.body, d.blob = -1, max(d.blob, body[1])   # the pieces' centres are not the tag's
                    d.joined = True
                    d.raws.append(i)
                    break
            else:
                out.append(Det(x, y, w, h, body, (i,)))
        return out

    def _why(self, x0, y0, x1, y1, m=None) -> str:
        """"screen" / "ui" when the screen box is within m px of the screen's border / of a UI rectangle, else ""."""
        m = self.cfg.tag_edge if m is None else m
        if x0 < m or y0 < m or x1 > SW - m or y1 > SH - m:
            return "screen"
        for a, b, c, d in self.ui:
            if x0 < c + m and x1 > a - m and y0 < d + m and y1 > b - m:
                return "ui"
        return ""

    def _evidence(self, dets, fit):
        c = self.cfg
        if not dets:
            return
        mts = list(self.mob_tags.values())
        for d in dets:
            cxs = d.x + d.w / 2.0
            for m in fit or ():
                mt = self.mob_tags.get(m["type"])
                fx, fy = m["feet"]
                if mt is not None and abs(d.y - fy - mt[3]) <= 1 and abs(cxs - fx - mt[2]) <= 4 \
                        and abs(d.w - mt[0]) <= c.tag_w_tol:
                    d.mob = True
                    break
            d.mobbox = any(abs(d.w - mt[0]) <= 1 and abs(d.h - mt[1]) <= 1 for mt in mts)
            d.npc = any(abs(d.cx - nx) < 40 and abs(d.T - ny) < 40 for nx, ny in self.npcs)
        for d in dets:                                       # 12..45 px over another tag, their x overlapping, and no
            d.above = d.blob < c.body_tall and any(          # tall body over it: a pattern on that tag's owner
                e is not d and 12 <= e.y - d.y <= 45 and min(d.x + d.w, e.x + e.w) - max(d.x, e.x) >= 0.5 * d.w
                for e in dets)

    # ------------------------------------------------------------------ tracks
    def _associate(self, dets, n, t, dt, cx0, cy0, moved):
        c = self.cfg
        G0, WT = c.tag_gate, c.tag_w_tol
        live = self.live
        pairs = []
        for a, tr in enumerate(live):
            u = tr.unseen
            px = tr.px = tr.x + tr.vx * min(u, 0.5)          # where it would be by now, walking on as it did
            pl, pr = px - tr.w / 2.0, px + tr.w / 2.0
            gx, gy, ge = G0 + c.tag_vx * u, G0 + c.tag_vy * u, G0 + 60.0 * u
            for b, d in enumerate(dets):
                ey = min(abs(d.T - tr.y), abs(d.T + d.h - tr.y - tr.h))
                if ey > gy:
                    continue
                dw = d.w - tr.w
                if abs(dw) <= WT and tr.known:               # its own width: the whole tag
                    ex = abs(d.cx - px)
                    if tr.merged:
                        ex = min(ex, abs(d.L - pl), abs(d.R - pr))
                    if ex > gx:
                        continue
                    cost = ex + ey
                else:                                        # a piece of it / a wider box it is part of: by an edge
                    ex = min(abs(d.L - pl), abs(d.R - pr))
                    if dw < 0 and pl - G0 <= d.L and d.R <= pr + G0:
                        ex = min(ex, G0 / 2.0)               # a piece inside its box
                    if ex > ge:
                        continue
                    cost = ex + ey + (4.0 * abs(dw) if tr.merged else 8.0)
                pairs.append((cost, a, b))
        pairs.sort()
        ua, ub = {}, {}
        for cost, a, b in pairs:
            if a in ua or b in ub:
                continue
            ua[a], ub[b] = b, a
        for a, b in ua.items():
            self._update(live[a], dets[b], n, t, moved)
        self._together(dets, ua, ub, n, t, moved)
        for a, tr in enumerate(live):                        # not seen on this frame
            if a in ua or tr.into is not None:
                continue
            tr.unseen += dt
            sx, sy = tr.px - tr.w / 2.0 - cx0, tr.y - cy0
            why = self._why(sx, sy, sx + tr.w, sy + tr.h)
            if why:
                tr.end = "edge:" + why
            elif tr.unseen > c.player_cover_s:
                tr.end = "lost"
        for b, d in enumerate(dets):
            if b in ub or d.nobirth:
                continue
            tr = _Track(self.next_id, d, t, n)
            self.next_id += 1
            tr.born = "edge" if self._why(d.x, d.y, d.x + d.w, d.y + d.h, 2 * c.tag_edge) else "in view"
            self._update(tr, d, n, t, moved, new=True)
            live.append(tr)
        for y in live:                                       # a young track that now shows the width of an older
            if y.into is not None or y.end or y.n != n or y.clean > 2 * c.tag_confirm or not y.known \
                    or y.hist[-1][6] != KIND_WHOLE:          # one still covered, inside its gate: the same tag coming
                continue                                     # back (out from behind something, piece by piece)
            for o in live:
                if o is y or o.into is not None or o.end or o.unseen == 0.0 or o.clean < c.tag_confirm or o.id > y.id \
                        or o.t >= y.t0 or abs(o.w - y.w) > WT:
                    continue
                if abs(y.x - o.px) <= G0 + c.tag_vx * o.unseen and abs(y.y - o.y) <= G0 + c.tag_vy * o.unseen:
                    self._absorb(o, y, "back")
                    break
        keep = []
        for tr in live:
            if tr.into is not None:
                continue
            if tr.end:
                self._ended(tr, t)
            else:
                keep.append(tr)
        self.live = keep

    def _together(self, dets, ua, ub, n, t, moved):
        """A track left without a tag whose place is inside a wider box another track took: two tags run together
        (the box narrower than the two side by side) - split by the widths known: it is placed inside the box by its
        own width - or the two were pieces of one tag (the box as wide as both, not both sure). And a tag left
        without a track: a piece of a tag a track took."""
        c = self.cfg
        G0, WT = c.tag_gate, c.tag_w_tol
        live = self.live
        for a, tr in enumerate(live):
            if a in ua or tr.unseen > 0.1:
                continue
            pl, pr = tr.px - tr.w / 2.0, tr.px + tr.w / 2.0
            for b, o in list(ub.items()):
                d, other = dets[b], live[o]
                if other.into is not None or (other.clean >= c.tag_confirm and d.w <= other.w + WT):
                    continue                                 # the other's tag alone: this one is not in it
                if d.w > tr.wlast + WT and d.L - G0 <= pl and pr <= d.R + G0 and \
                        min(abs(d.T - tr.y), abs(d.T + d.h - tr.y - tr.h)) <= G0:
                    if d.w >= tr.wlast + other.wlast - 4 and not (tr.clean >= c.tag_confirm and other.clean >= c.tag_confirm):
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
                        d.R <= tr.x + tr.w / 2.0 + G0 and d.w < tr.w - WT and \
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
        for h in old.hist + [h[:6] + (KIND_PART,) if why == "piece" else h for h in new.hist]:
            k = seen.get(h[0])                               # one sighting a frame: the whole one, else the wider
            if k is None or (h[6], -h[4]) < (k[6], -k[4]):
                seen[h[0]] = h
        old.hist = [seen[k] for k in sorted(seen)]
        old.seen = len(old.hist)
        for k, v in new.ev.items():
            old.ev[k] += v
        if why == "back":
            old.wc.update(new.wc)
            old.hc.update(new.hc)
            old.clean += new.clean
            old.x, old.y, old.t, old.n, old.unseen, old.vx = new.x, new.y, new.t, new.n, 0.0, new.vx
            old.sx, old.sy, old.wlast, old.merged = new.sx, new.sy, new.wlast, new.merged
            old.place, old.node, old.from_node, old.off, old.vy = new.place, new.node, new.from_node, new.off, new.vy
        if self.keep:
            self.done.append(new)

    def _update(self, tr, d, n, t, moved, shared=False, new=False):
        c = self.cfg
        G0, WT = c.tag_gate, c.tag_w_tol
        whole = not d.cut and not shared
        if whole:                                            # its own width: the commonest whole one
            k = tr.wc[d.w] = tr.wc[d.w] + 1
            if not tr.known or k > tr.wc[tr.w]:
                tr.w, tr.known = d.w, True
            k = tr.hc[d.h] = tr.hc[d.h] + 1
            if k > tr.hc[tr.h] or tr.hc[tr.h] == 0:
                tr.h = d.h
        elif not tr.known and not shared and d.w > tr.w:
            tr.w = d.w                                       # nothing whole seen yet: at least this wide
        full = abs(d.w - tr.w) <= WT and not shared
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
        tr.vy = (y - tr.y) / max(1e-6, t - tr.t) if not new and tr.n == n - 1 and t > tr.t else 0.0
        tr.x, tr.y, tr.unseen = x, y, 0.0
        tr.seen += 1
        tr.merged = shared
        tr.shared += shared
        tr.clean += whole and full
        e = tr.ev
        for k, v in (("mob", d.mob), ("mobbox", d.mobbox), ("npc", d.npc), ("above", d.above), ("logrow", d.logrow)):
            if v:
                e[k] += 1
        if d.blob == 0:
            e["b0"] += 1                                     # nothing stands on it
        elif d.body > 0:
            k = "bs" if d.body < c.body_tall else "bt"
            e[k] += 1
            if whole and full:                               # the tag whole and alone: its centre is its owner's
                e[k + "1"] += 1
        h = tr.hist
        if moved and tr.sx is not None and tr.n == n - 1 and not shared:
            tr.scr[1] += 1
            tr.scr[0] += d.x == tr.sx and d.y == tr.sy
        tr.sx, tr.sy = d.x, d.y
        h.append((n, t, x, y, d.w, d.h, KIND_WHOLE if full and whole else KIND_PART))
        k = h[-6] if len(h) >= 6 else h[0]                   # its sideways speed over the last 5 frames
        tr.vx = max(-300.0, min(300.0, (x - k[2]) / (t - k[1]))) if 0.03 < t - k[1] <= 0.15 else 0.0
        tr.t, tr.n = t, n

    @staticmethod
    def _final(tr):
        while tr.into is not None:
            tr = tr.into
        return tr

    def _ended(self, tr, t):
        if tr.was_player:
            self._ev.append({"ev": "player_left", "t": t, "id": tr.id, "how": tr.end})
        if self.keep:
            self.done.append(tr)

    # ------------------------------------------------------------------ placement and the records
    def _place(self, t, cx0, cy0):
        """Every track seen on this frame: its feet (the tag's centre x, top y - 1) by the graph's one rule with its
        step since the last frame; the boxes drawn (for the mob tracker's covers)."""
        c = self.cfg
        seen = [tr for tr in self.live if tr.n == self.n and tr.into is None]
        if not seen:
            return
        xs = np.array([tr.x for tr in seen], np.float64)
        ys = np.array([tr.y - 1.0 for tr in seen], np.float64)
        prev = [tr.hist[-2] if len(tr.hist) >= 2 and tr.hist[-2][0] == self.n - 1 else None for tr in seen]
        dx = np.array([0.0 if p is None else tr.x - p[2] for tr, p in zip(seen, prev)])
        dy = np.array([0.0 if p is None else tr.y - p[3] for tr, p in zip(seen, prev)])
        last = np.array([tr.node for tr in seen], np.int64)
        lfrom = np.array([tr.from_node for tr in seen], np.int64)
        P = self.g.place(xs, ys, dx, dy, last, lfrom, climb=np.ones(len(seen), bool))
        for q, tr in enumerate(seen):
            tr.place, tr.node, tr.from_node, tr.off = int(P.place[q]), int(P.node[q]), int(P.from_node[q]), float(P.off[q])
            cls = tr.cls_now
            if cls == "player" and not tr.was_player:
                tr.was_player = True
                self._ev.append({"ev": "player_new", "t": t, "id": tr.id, "w": tr.w})
            if cls in ("player", "pet"):
                bx = c.player_box if cls == "player" else c.pet_box
                mx, my = tr.x - cx0, tr.y - cy0
                self.drawn.append((cls, mx + bx[0], my + bx[1], mx + bx[2], my + bx[3]))

    def _records(self, t, blind=False) -> list:
        """The players of the state: the live tracks whose class is player now."""
        out = []
        C = self.prev_C or (0.0, 0.0)
        for tr in self.live:
            if tr.into is not None or tr.cls_now != "player":
                continue
            seen = tr.n == self.n and not blind
            out.append(Player(tr.id, tr.x, tr.y - 1.0, tr.x - C[0], tr.y - 1.0 - C[1], tr.w, PLACES[tr.place], tr.node,
                              tr.from_node, tr.off, tr.vx, tr.vy, seen,
                              "blind" if blind else "none" if seen else "unseen", tr.unseen, tr.t0))
        return out

    def finish(self) -> list:
        """A tool's end of the capture: every live track ends ("capture end") -> every track (ids in order), the
        pieces and re-appearances taken into their tracks left out."""
        for tr in self.live:
            tr.end = "capture end"
            self.done.append(tr)
        self.live = []
        self.done.sort(key=lambda tr: tr.id)
        return [tr for tr in self.done if tr.into is None]
