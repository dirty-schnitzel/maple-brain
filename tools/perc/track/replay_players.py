"""PLAN-tracker step 4b: OTHER PLAYERS AND US FROM A KEPT REPLAY - maplebrain/track/players.py and us.py (with
track/graph.py's placement and the bitmap evidence's `columns`) over every frame of a capture's kept replay (dump.py),
our keys from the capture's keys.jsonl; graded against the prototype (proto_players.py), the labels (L5, L1's us),
nav/selfstate.SelfTracker and the 2 s players' cover.

    python tools/perc/track/replay_players.py run CAP [CAP ...] | --sound [--port] [--jobs N]
    python tools/perc/track/replay_players.py port CAP            the port against the prototype (needs `run --port`)
    python tools/perc/track/replay_players.py l5 [--final]        L5: classes, players found, the node (2 captures)
    python tools/perc/track/replay_players.py cover [CAP]         the 2 s cover: tracks, the same tag back as a new id
    python tools/perc/track/replay_players.py us [--sound]        L1's us, our feet known, SelfState on the same frames
    python tools/perc/track/replay_players.py heights             the body heights of L5's pets and standing players
    python tools/perc/track/replay_players.py ms [--sound]        players + us ms a frame (the decode apart)
    python tools/perc/track/replay_players.py time CAP [--n 3000] the live Perceiver: part us_players p50 / p90

Every command takes `--tag T`: the run's files are OUT/<cap>[_port]_T.pkl (step 4b try 3: `t4b3`; try 2's untagged).
`run --cfg k=v ...`: a variant with config.Track's values changed (step 4b try 4: rule A or B alone).
`run` writes OUT/<cap>[_port].pkl (OUT = CORPUS/work/track-plan/step4b): per frame the sorted tag list (class and track
per tag of FrameFacts.tags, the track's place / node when seen), our state, SelfState's (SelfTracker over the same
frames: obs.me_map, obs.map_pos and the keys held), the ms; per track its final class and life (`tracks`). `--port`:
the prototype's own inputs - its hindsight mob-tag boxes (learn_mob_tags over the whole capture) and its ours* rule
(every tag overlapping our last place within 2 s is ours, no width) - so its tracks can be compared one for one.
"""
import argparse
import json
import pickle
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import cache  # noqa: E402
import dump  # noqa: E402
from load import ASSETS, keys as key_log, map_of, name_of  # noqa: E402

OUT = Path(r"F:\dev\maple-corpus\work\track-plan\step4b")
LABELS = Path(r"F:\dev\maple-corpus\labels")
L5_CAPS = [cache.DESIGN, "20261120_235747_1#0"]


class Facts:
    """The fields of FrameFacts us / players read, from a kept replay's row."""
    __slots__ = ("t", "scene_cam", "fit", "tags", "drops", "tag", "patches", "slots", "hp", "mp", "exp_points")

    def __init__(self, r, tags=None):
        f = r["facts"]
        self.t, self.scene_cam = r["t"], r["C"]
        self.fit, self.drops, self.tag = f.get("fit"), f.get("drops"), f.get("tag")
        self.tags = f.get("tags") if tags is None else tags
        self.patches = f.get("patches")
        self.slots = (f.get("slots") or {}) if (f.get("v") or 0) >= 7 else {}     # v1-v6: two keys' "holds something"
        self.hp, self.mp, self.exp_points = f.get("hp"), f.get("mp"), f.get("exp_points")


class LazyBits:
    """track/evidence.Bitmaps on the kept replay's packed bitmaps, unpacked on the first question (its time apart)."""

    def __init__(self, sh, wo):
        self.sh, self.wo, self.ready, self.dec, self._b = sh, wo, sh is not None, 0.0, None

    def _bits(self):
        from maplebrain.track.evidence import Bitmaps
        if self._b is None:
            a = time.perf_counter()
            self._b = Bitmaps(dump.bits(self.sh), dump.bits(self.wo))
            self.dec = time.perf_counter() - a
        return self._b

    def count(self, groups):
        return self._bits().count(groups)

    def columns(self, cx, top, reach, half):
        return self._bits().columns(cx, top, reach, half)

    def ask_columns(self, cx, top, reach, half):
        from maplebrain.track.evidence import Answer
        return Answer(self.columns(cx, top, reach, half))


def minimap_ui(cap):
    """The UI rectangles the tag finder did not see on this capture: the minimap window measured as proto_players
    does (its slim cache's value when it has one), + hud.UI_RECTS' others."""
    from maplebrain.perception import hud
    import proto_players as PP
    p = PP.out_dir() / "slim" / f"{cap}.pkl"
    mm = pickle.loads(p.read_bytes())["minimap"] if p.exists() else PP.minimap_rect(cap)
    return [tuple(mm)] + list(hud.UI_RECTS[1:]), tuple(mm)


class ProtoOurs:
    """The prototype's ours* rule (proto_players.Tracker.step), for `--port`: -> (ours box or None, the list indices it
    takes as ours when our own tag is missing)."""

    def __init__(self):
        self.me = None

    def __call__(self, t, C, own, tags):
        cx0, cy0 = C
        if own is not None:
            self.me = (own[0] + own[2] / 2.0 + cx0, own[1] + cy0, t)
            return (int(own[0]), int(own[1]), int(own[2]), int(own[3]), None), []
        if self.me is None or t - self.me[2] >= 2.0:
            return None, []
        ow, oh = 74, 17
        ox, oy = self.me[0] - ow / 2.0 - cx0, self.me[1] - cy0
        gate = 16.0 + 800.0 * (t - self.me[2])
        out = []
        for i, (x, y, w, h) in enumerate(tags):
            if y < oy + oh - 4 + gate and y + h > oy + 4 - gate and \
                    min(x + w, ox + ow + gate) - max(x, ox - gate) >= 0.4 * min(w, ow):
                out.append(i)
                self.me = (x + w / 2.0 + cx0, y + cy0, self.me[2])     # (the frame's gate stays where it was)
        return None, out


TAG = ""                                         # --tag: the run's outputs as <cap>_<tag>.pkl (try 2's stay as they are)
CFG = {}                                         # --cfg k=v ...: config.Track's values changed for a variant's run


def out_path(cap, port=False, tag=None) -> Path:
    tag = TAG if tag is None else tag
    return OUT / (cap.replace("#", "_") + ("_port" if port else "") + (f"_{tag}" if tag else "") + ".pkl")


def run(cap, port=False) -> dict:
    from maplebrain.config import Config, Track
    from maplebrain.nav.navmap import NavMap
    from maplebrain.nav.selfstate import SelfTracker
    from maplebrain.track.graph import PLACES, Graph
    from maplebrain.track.players import Players
    from maplebrain.track.us import Us
    import proto_players as PP
    mid = map_of(cap)
    mj = json.loads((ASSETS / "maps" / str(mid) / "map.json").read_text(encoding="utf-8"))
    cfg = Track(**CFG)
    g = Graph(mj, track=cfg, edges=False)
    ui, mm = minimap_ui(cap)
    mob_tags = None
    if port:
        F = PP.frames_of(cap)
        mob_tags = {k: v[:4] for k, v in PP.learn_mob_tags(F["rows"]).items()}
    pl = Players(g, cfg, ui=ui, npcs=g.npcs, keep=True, mob_tags=mob_tags)
    us = Us(g, cfg)
    proto_ours = ProtoOurs() if port else None
    st = SelfTracker(NavMap.for_map(mid, ASSETS, Config().nav))
    ks = sorted(key_log(cap), key=lambda k: k["t"])
    ki, held = 0, set()
    d = dump.out_dir(cap)
    frames, ms, ms_us = [], [], []
    for kch in range(dump.meta(cap)["chunks"]):
        rs = pickle.loads((d / f"rows_{kch:03d}.pkl").read_bytes())
        bs = pickle.loads((d / f"bits_{kch:03d}.pkl").read_bytes())
        for r, (n, sh, wo) in zip(rs, bs):
            assert n == r["n"]
            t = r["t"]
            evs = []
            while ki < len(ks) and ks[ki]["t"] <= t:
                evs.append(ks[ki])
                held.add(ks[ki]["key"]) if ks[ki]["down"] else held.discard(ks[ki]["key"])
                ki += 1
            f = Facts(r)
            ev = LazyBits(sh, wo)
            a = time.perf_counter()
            us.update(f, evs)
            b = time.perf_counter()
            ours = us.box
            if port:
                tags = [tuple(x[:4]) for x in f.tags or []]
                if r["C"] is not None:
                    ours, drop = proto_ours(t, r["C"], f.tag, tags)
                    if drop:                                # the prototype's ours*: those tags are not candidates
                        f = Facts(r, [x for i, x in enumerate(f.tags or []) if i not in drop])
            c0 = time.perf_counter()
            pl.update(f, ev, ours=ours, n=n)
            c1 = time.perf_counter()
            ms.append(1000 * ((b - a) + (c1 - c0)) - 1000 * ev.dec)
            ms_us.append(1000 * (b - a))
            live = {tr.id: tr for tr in pl.live}
            tplace = []
            for tid in pl.tag_track:
                tr = live.get(tid)
                tplace.append(None if tr is None or tr.n != n else (PLACES[tr.place], tr.node))
            ss = st.update(t, me_map=r.get("me_map"), map_pos=r.get("map_pos"), held=set(held))
            p = us.place
            frames.append({"n": n, "t": t, "C": r["C"] is not None, "cls": pl.tag_class, "trk": pl.tag_track,
                           "tplace": tplace, "tags": [tuple(x[:4]) for x in f.tags or []],
                           "us": None if p.x is None else (us.seen, us.tag.src, round(p.x, 1), round(p.y, 1),
                                                           PLACES[p.place], p.node, p.why, round(p.vx), round(p.vy)),
                           "self": None if ss is None else (round(ss.t, 4) == round(t, 4), ss.src, ss.state, ss.platform,
                                                            ss.rope, round(ss.x, 1), round(ss.y, 1)),
                           "players": [(m.id, round(m.x, 1), round(m.y, 1), m.place, m.node, m.seen) for m in pl.records]})
    tracks = pl.finish()
    trs = [{"id": tr.id, "cls": tr.cls(cfg), "w": tr.w, "h": tr.h, "n0": tr.n0, "t0": tr.t0, "end": tr.end,
            "born": tr.born, "seen": tr.seen, "first": tr.hist[0][:4], "last": tr.hist[-1][:4], "ev": dict(tr.ev),
            "hb1": tr.hb1.copy(), "hb": tr.hb.copy(), "bseq": list(tr.bseq), "known_n": tr.known_n,
            "hist": [(h[0], round(h[2], 1), round(h[3], 1), h[4], h[5], h[6]) for h in tr.hist]} for tr in tracks]
    return {"cap": cap, "map": mid, "port": port, "frames": frames, "tracks": trs, "ms": np.array(ms),
            "ms_us": np.array(ms_us), "stats": dict(pl.stats), "us_stats": dict(us.tag.stats), "minimap": mm,
            "mob_tags": dict(pl.mob_tags)}


def cmd_run(caps, port):
    OUT.mkdir(parents=True, exist_ok=True)
    for cap in caps:
        a = time.perf_counter()
        res = run(cap, port)
        p = out_path(cap, port)
        p.write_bytes(pickle.dumps(res, protocol=pickle.HIGHEST_PROTOCOL))
        ms = res["ms"]
        print(f"{name_of(cap)} ({cap}): {len(res['frames'])} frames, {len(res['tracks'])} tracks "
              f"{dict(Counter(t['cls'] for t in res['tracks']))}; ms p50 / p90 / p99 "
              f"{np.percentile(ms, [50, 90, 99]).round(3).tolist()}; {time.perf_counter() - a:.0f} s -> {p}", flush=True)


def load(cap, port=False, tag=None) -> dict:
    return pickle.loads(out_path(cap, port, tag).read_bytes())


# ---------------------------------------------------------------------------------------------- the port
def cmd_port(cap):
    """The real code with the prototype's inputs (`run --port`) against proto_players.run (cover 2 s): the tracks one
    for one (id, final class, first and last sighting), the body per tag (columns against the slim cache's)."""
    import proto_players as PP
    res = load(cap, True)
    F = PP.frames_of(cap)
    trk, tracks, g, mt, _ = PP.run(F, cover=2.0, minimap=F["minimap"])     # as its report (measurement 7)
    from maplebrain.config import Track
    c = Track()
    a = {t["id"]: t for t in res["tracks"]}
    b = {tr.id: tr for tr in tracks}
    same, diff = 0, []
    for i in sorted(set(a) | set(b)):
        x, y = a.get(i), b.get(i)
        eq = x is not None and y is not None and x["cls"] == y.cls() and x["n0"] == y.n0 and \
            x["last"][0] == y.hist[-1][0] and abs(x["last"][2] - y.hist[-1][2]) < 1e-6 and x["end"] == y.end
        same += eq
        if not eq and len(diff) < 15:
            diff.append((i, x and (x["cls"], x["n0"], x["last"][:3], x["end"]),
                         y and (y.cls(), y.n0, y.hist[-1][:3], y.end)))
    print(f"PORT {cap}: tracks equal (id, class, first frame, last sighting, end) {same} of {len(set(a) | set(b))}")
    for x in diff:
        print("   ", x)
    cls_a = Counter(t["cls"] for t in res["tracks"])
    cls_b = Counter(tr.cls() for tr in tracks)
    print(f"   classes: real {dict(cls_a)}\n            proto {dict(cls_b)}")
    # the body per tag: the slim cache's col_body against the real code's columns (the bitmaps)
    from maplebrain.track.players import col_body
    d = dump.out_dir(cap)
    n_eq = n_all = 0
    bad = []
    rows = {r[0]: r for r in F["rows"]}
    for kch in range(dump.meta(cap)["chunks"]):
        rs = pickle.loads((d / f"rows_{kch:03d}.pkl").read_bytes())
        bs = pickle.loads((d / f"bits_{kch:03d}.pkl").read_bytes())
        for r, (n, sh, wo) in zip(rs, bs):
            tags = rows[n][4]
            if not tags or sh is None:
                continue
            ev = LazyBits(sh, wo)
            cx = np.array([x + w // 2 for x, y, w, h in tags])
            top = np.array([y for x, y, w, h in tags])
            o, w_, i_ = ev.columns(cx, top, c.body_reach, c.body_half)
            for k, (x, y, w, h) in enumerate(tags):
                mine = col_body(o[k], w_[k], i_[k], int(y), c)
                n_all += 1
                n_eq += mine == rows[n][6][k][0]
                if mine != rows[n][6][k][0] and len(bad) < 10:
                    bad.append((n, (x, y, w, h), mine, rows[n][6][k][0]))
    print(f"   the body over a tag (col_body): equal on {n_eq} of {n_all} tags {bad}")


# ---------------------------------------------------------------------------------------------- L5
def cmd_l5(final=False, port=False):
    """L5 (2 captures, 200 frames): each labelled tag's class against the real tracker's sorting on that frame (the
    class voted so far: live; `final`: its track's class at the track's end, in hindsight - as the prototype's sheets
    the cases were picked from). Players found, non-players called players, pet <-> player, the node of standing
    players. A tag on a track seen under 6 times (`short`) is NOT YET KNOWN (the user, step 4b try 2, answer 1): not a
    miss, counted apart, with the delay until a track's class is known (frames from its first sighting, p50 / p90).
    So is a tag on a track with fewer than 5 alone body readings (`unsure`: the user, step 4b try 3, answer 1); the
    tracks that stay `unsure` their whole life are counted with why (`unsure_why`)."""
    conf = Counter()
    nodes = [0, 0]
    rows_miss = []
    for cap in L5_CAPS:
        res = load(cap, port)
        by = {f["n"]: f for f in res["frames"]}
        fin = {t["id"]: t["cls"] for t in res["tracks"]}
        lab = json.loads((LABELS / cap / "labels" / "L5.json").read_text(encoding="utf-8"))
        for n, fr in lab["frames"].items():
            f = by[int(n)]
            idx = {tuple(b): i for i, b in enumerate(f["tags"])}
            for e in fr["tags"]:
                i = idx.get(tuple(e["box"]))
                got = "missing" if i is None else f["cls"][i]
                if final and i is not None and f["trk"][i]:
                    got = fin.get(f["trk"][i], got)
                want = e["class"]
                conf[(want, got)] += 1
                if want == "player" or got == "player":
                    if want != got:
                        rows_miss.append((cap, int(n), fr.get("case"), tuple(e["box"]), want, got))
                if want == "player" and e.get("place") == "stand" and got == "player" and i is not None:
                    tp = f["tplace"][i]
                    nodes[0] += 1
                    ok = tp is not None and tp[0] == "stand" and tp[1] == e.get("node")
                    nodes[1] += ok
                    if not ok:
                        rows_miss.append((cap, int(n), fr.get("case"), tuple(e["box"]), "node", e.get("node"), tp))
    labs = sorted({a for a, _ in conf})
    gots = sorted({b for _, b in conf})
    print("L5 confusion (label -> the tracker):")
    for a in labs:
        print(f"   {a:7s} " + ", ".join(f"{b} {conf[(a, b)]}" for b in gots if conf[(a, b)]))
    pl = sum(v for (a, b), v in conf.items() if a == "player")
    found = conf[("player", "player")]
    non = sum(v for (a, b), v in conf.items() if a not in ("player", "?"))
    non_pl = sum(v for (a, b), v in conf.items() if a not in ("player", "?") and b == "player")
    pp = pl + sum(v for (a, b), v in conf.items() if a == "pet")
    swap = conf[("pet", "player")] + conf[("player", "pet")]
    NYK = ("short", "unsure")
    unk = {k: sum(v for (a, b), v in conf.items() if b == k) for k in NYK}
    unk_pl = {k: conf[("player", k)] for k in NYK}
    pl -= sum(unk_pl.values())
    non -= sum(v for (a, b), v in conf.items() if a not in ("player", "?") and b in NYK)
    swap_out = sum(unk_pl.values()) + sum(conf[("pet", k)] for k in NYK)
    pp -= swap_out
    print(f"not yet known, left out of the rows: a track seen under 6 times {unk['short']} labelled tags "
          f"({unk_pl['short']} players); under 5 alone body readings (`unsure`) {unk['unsure']} ({unk_pl['unsure']} "
          f"players)")
    dl, dpp = [], []
    for cap in L5_CAPS:
        for t in load(cap, port)["tracks"]:
            if t["known_n"] is not None and t["cls"] in ("player", "pet"):
                dl.append(t["known_n"] - t["n0"])
                k = pp_n(t)
                if k is not None:
                    dpp.append(k - t["n0"])
    if dl:
        print(f"the delay until a player's / pet's class is known: frames from its first sighting p50 / p90 / p99 "
              f"{np.percentile(dl, [50, 90, 99]).round(1).tolist()} (out of `short`, as try 3; {len(dl)} tracks; 60 "
              f"frames a second); until it is pet / player (out of `unsure` too) "
              f"{np.percentile(dpp, [50, 90, 99]).round(1).tolist()} ({len(dpp)} tracks)")
    unsure_why(port)
    print(f"players found {found} of {pl} = {100 * found / max(1, pl):.1f} % (>= 95)")
    print(f"non-players called players {non_pl} of {non} = {100 * non_pl / max(1, non):.2f} % (<= 1)")
    print(f"a pet called a player or a player called a pet {swap} of {pp} = {100 * swap / max(1, pp):.2f} % (<= 5)")
    print(f"the node of standing players {nodes[1]} of {nodes[0]} = {100 * nodes[1] / max(1, nodes[0]):.1f} % (>= 95)")
    for x in rows_miss:
        print("   ", x)


def pp_n(t):
    """The frame a track (final class pet / player) was first more than `unsure`: its 5th alone body reading (bseq's
    whole-and-alone sightings with a body over 0) once out of `short` (known_n) - exact unless a mob / text vote came
    between."""
    k = 0
    for n, b, w, cut in t["bseq"]:
        if b > 0 and w:
            k += 1
            if k >= 5:
                return max(n, t["known_n"])
    return None


def unsure_why(port=False):
    """The tracks whose class at their end is `unsure` (fewer than 5 alone body readings over their whole life), on
    L5's two captures: how many, and why. Each by its first cause: never alone (every sighting cut - the screen's edge,
    the UI, a joined piece - or crowded); alone, but the body over it never read (-1: under the minimap / UI / the
    play area's bottom, or 0: nothing over its centre); 1-4 readings over a short life (seen under 1 s); 1-4 over a
    longer one, mostly crowded. With the sightings' make-up: cut / crowded / alone, of the alone ones read / -1 / 0 /
    not asked (body_every)."""
    why, life, mk = Counter(), [], Counter()
    for cap in L5_CAPS:
        for t in load(cap, port)["tracks"]:
            if t["cls"] != "unsure":
                continue
            bs = t["bseq"]
            alone = [b for n, b, w, cut in bs if w]
            mk["cut"] += sum(1 for n, b, w, cut in bs if cut)
            mk["crowded"] += sum(1 for n, b, w, cut in bs if not cut and not w)
            mk["alone, read"] += sum(1 for b in alone if b > 0)
            mk["alone, -1"] += sum(1 for b in alone if b == -1)
            mk["alone, 0"] += sum(1 for b in alone if b == 0)
            mk["alone, not asked"] += sum(1 for b in alone if b == -2)
            k = sum(1 for b in alone if b > 0)
            if not alone:
                w = "never alone: every sighting cut or crowded"
            elif k == 0:
                w = "alone, the body never read (-1 / 0)"
            elif t["seen"] < 60:
                w = "1-4 readings, seen under 1 s"
            else:
                w = "1-4 readings, seen 1 s or more (mostly cut / crowded)"
            why[w] += 1
            life.append(t["seen"])
    print(f"tracks `unsure` their whole life (L5's 2 captures): {sum(why.values())}; sightings p50 / p90 "
          f"{np.percentile(life, [50, 90]).round().tolist() if life else None}")
    for k, v in why.most_common():
        print(f"   {v:4d}  {k}")
    print(f"   their sightings: {dict(mk)}")


# ---------------------------------------------------------------------------------------------- the cover
def cmd_cover(cap):
    """proto_players.n7_covers on the real tracks (final class): player tracks, lost in view, of those the same width
    back within 300 px and 10 s under a new id."""
    res = load(cap)
    pl = [t for t in res["tracks"] if t["cls"] == "player"]
    lost = [t for t in pl if t["end"] == "lost"]
    back, dts = 0, []
    for tr in lost:
        h1 = tr["last"]
        best = None
        for o in pl:
            if o is tr or abs(o["w"] - tr["w"]) > 1 or o["born"] != "in view":
                continue
            dt = o["first"][1] - h1[1]
            if 0 < dt <= 10.0 and abs(o["first"][2] - h1[2]) <= 300 and abs(o["first"][3] - h1[3]) <= 300:
                best = dt if best is None else min(best, dt)
        if best is not None:
            back += 1
            dts.append(best)
    print(f"COVER 2 s ({cap}): {len(pl)} player tracks; lost in view {len(lost)}; the same width back as a new id "
          f"{back} = {100 * back / max(1, len(pl)):.1f} % of player tracks (<= 10.4 %: 29 of 280, the user, step 4b "
          f"try 3 answer 3); after s p50 {np.median(dts) if dts else None}")
    print(f"   all tracks by class {dict(Counter(t['cls'] for t in res['tracks']))}; ends "
          f"{dict(Counter(t['end'].split(':')[0] for t in pl))}")


# ---------------------------------------------------------------------------------------------- us
def cmd_us(caps):
    """L1's us (13 captures): place (stand / air / rope) and the node; our feet known; SelfState against us on the
    frames both placed us from our own tag (every difference listed by kind)."""
    n_l1, ok_pl, n_nd, ok_nd, miss = 0, 0, 0, 0, []
    for cap in caps:
        p = LABELS / cap / "labels" / "L1.json"
        if not p.exists():
            continue
        res = load(cap)
        by = {f["n"]: f for f in res["frames"]}
        lab = json.loads(p.read_text(encoding="utf-8"))
        for n, fr in lab["frames"].items():
            u = fr.get("us")
            if not u or u["place"] not in ("stand", "air", "rope"):
                continue
            f = by[int(n)]
            n_l1 += 1
            got = f["us"]
            if got is None or not got[0]:
                miss.append((cap, int(n), fr.get("case"), "no feet", u["place"], u["node"]))
                continue
            ok = got[4] == u["place"]
            ok_pl += ok
            if not ok:
                miss.append((cap, int(n), fr.get("case"), "place", u["place"], u["node"], got[4], got[5], got[6]))
            if ok and u["place"] in ("stand", "rope"):
                n_nd += 1
                ok_nd += got[5] == u["node"]
                if got[5] != u["node"]:
                    miss.append((cap, int(n), fr.get("case"), "node", u["place"], u["node"], got[5]))
    print(f"L1 us: the place {ok_pl} of {n_l1} = {100 * ok_pl / max(1, n_l1):.2f} % (>= 99); the node {ok_nd} of {n_nd} "
          f"= {100 * ok_nd / max(1, n_nd):.2f} %")
    for x in miss:
        print("   ", x)
    for cap in caps:
        res = load(cap)
        fr = [f for f in res["frames"] if f["C"]]
        known = sum(1 for f in fr if f["us"] is not None and f["us"][0])
        tag = sum(1 for f in fr if f["us"] is not None and f["us"][0] and f["us"][1] == "tag")
        print(f"{name_of(cap)} ({cap}): our feet known {known} of {len(fr)} frames with a camera = "
              f"{100 * known / max(1, len(fr)):.2f} % (>= 97.5; our own tag {100 * tag / max(1, len(fr)):.2f} %, the "
              f"tag list +{100 * (known - tag) / max(1, len(fr)):.2f}); {res['us_stats']}")
    # SelfState on the 30-minute capture
    cap = cache.DESIGN
    res = load(cap)
    name = {"stand": "ground", "air": "air", "rope": "rope"}
    same, n, kinds, ex = 0, 0, Counter(), {}
    apart = Counter()
    for f in res["frames"]:
        u, s = f["us"], f["self"]
        if not f["C"] or u is None or not u[0] or u[1] != "tag":
            apart["us not from our own tag this frame"] += 1
            continue
        if s is None or not s[0] or s[1] != "tag":
            apart["SelfState not from the tag this frame"] += 1
            continue
        n += 1
        eq = name[u[4]] == s[2]
        same += eq
        if not eq:
            k = (u[4], u[6], s[2])
            kinds[k] += 1
            ex.setdefault(k, []).append(f["n"])
    print(f"SelfState ({cap}): the same place on {same} of {n} frames = {100 * same / max(1, n):.2f} % (>= 99); "
          f"apart: {dict(apart)}")
    print("   every difference (us place, the rule, SelfState): frames, first frames")
    for k, v in kinds.most_common():
        print(f"     {k}: {v}  {ex[k][:8]}")


def pct_s(v, ps=(0, 1, 5, 50, 95, 100)):
    v = np.asarray(v, float)
    return "n 0" if not len(v) else f"n {len(v)}: " + " / ".join(f"{np.percentile(v, q):.0f}" for q in ps)


def hpct(hist, q):
    """The q-th percentile of a height histogram (counts per px), or None."""
    n = int(hist.sum())
    if not n:
        return None
    return int(np.searchsorted(np.cumsum(hist), q / 100.0 * n, side="left"))


def cmd_heights():
    """Answer 3 (PLAN-tracker step 4b, try 2): the body over the tag of every L5-labelled pet and standing player -
    (a) on the labelled frame, (b) over its track's whole stay (whole, alone sightings: the heights a track is judged
    by), (c) per track, high percentiles; and which player sightings read short (under 55 px): at the screen's edge /
    the UI (cut), inside a shared or joined box, in the air or on a rope, the rest (looked at by eye)."""
    lab_tr = {"pet": {}, "player": {}}                  # class -> {(cap, track id): [labelled frames]}
    frame_h = {"pet": [], "player": []}
    other = Counter()                                   # labelled tags on a track of another name (width)
    for cap in L5_CAPS:
        res = load(cap)
        by = {f["n"]: f for f in res["frames"]}
        tracks = {t["id"]: t for t in res["tracks"]}
        lab = json.loads((LABELS / cap / "labels" / "L5.json").read_text(encoding="utf-8"))
        for n, fr in lab["frames"].items():
            n = int(n)
            f = by[n]
            idx = {tuple(b): i for i, b in enumerate(f["tags"])}
            for e in fr["tags"]:
                k = e["class"]
                if k not in ("pet", "player") or (k == "player" and e.get("place") != "stand"):
                    continue
                i = idx.get(tuple(e["box"]))
                tid = None if i is None else f["trk"][i]
                if not tid or tid not in tracks:
                    continue
                if abs(e["box"][2] - tracks[tid]["w"]) > 1:     # the tag is not the track's name: another
                    other[k] += 1                                # character's track took it on that frame
                    continue
                lab_tr[k].setdefault((cap, tid), []).append(n)
                b = [x for x in tracks[tid]["bseq"] if x[0] == n]
                if b and b[0][1] > 0:
                    frame_h[k].append(b[0][1])
        for k in lab_tr:
            for (c, tid), ns in lab_tr[k].items():
                if c == cap:
                    lab_tr[k][(c, tid)] = (ns, tracks[tid], {h[0]: h for h in tracks[tid]["hist"]},
                                           {f["n"]: f for f in res["frames"] if any(t == tid for t in f["trk"])})
    print("ANSWER 3 - the body over the tag (px), min / p1 / p5 / p50 / p95 / max; only labelled tags of their track's "
          f"own width (its name) - left out, the tag on a track of another name that frame: {dict(other)}")
    for k in ("pet", "player"):
        print(f"  (a) labelled {k}s{' (standing)' if k == 'player' else ''}, on the labelled frame: {pct_s(frame_h[k])}")
    for k in ("pet", "player"):
        whole = [b for (ns, tr, hh, ff) in lab_tr[k].values() for (n, b, w, cut) in tr["bseq"] if b > 0 and w]
        allb = [b for (ns, tr, hh, ff) in lab_tr[k].values() for (n, b, w, cut) in tr["bseq"] if b > 0]
        print(f"  (b) their {len(lab_tr[k])} tracks over the stay - whole, alone: {pct_s(whole)}; every reading: {pct_s(allb)}")
    for q in (75, 90, 95):
        for k in ("pet", "player"):
            v = [hpct(tr["hb1"], q) if tr["hb1"].sum() >= 5 else hpct(tr["hb"], q)
                 for (ns, tr, hh, ff) in lab_tr[k].values()]
            v = [x for x in v if x is not None]
            print(f"  (c) per track, p{q} of its heights ({k}s): {pct_s(v)}  {sorted(v)[:6] if k == 'player' else sorted(v)[-6:]}")
    # why players read short: every sighting of a labelled standing player's track under 55 px
    why = Counter()
    short = []
    for (cap, tid), (ns, tr, hh, ff) in lab_tr["player"].items():
        for n, b, w, cut in tr["bseq"]:
            if b <= 0 or b >= 55:
                continue
            f = ff.get(n)
            pl = None
            if f is not None:
                for i, t in enumerate(f["trk"]):
                    if t == tid and f["tplace"][i] is not None:
                        pl = f["tplace"][i][0]
            k = "cut (screen edge / UI)" if cut else "air / rope" if pl in ("air", "rope") else \
                "a shared / joined box" if not w else "whole, standing"
            why[k] += 1
            short.append((cap, tid, n, b, k))
    tot = sum(1 for (ns, tr, hh, ff) in lab_tr["player"].values() for x in tr["bseq"] if x[1] > 0)
    print(f"  player sightings under 55 px: {sum(why.values())} of {tot} with a body read: {dict(why)}")
    out = OUT / "heights_short.json"
    out.write_text(json.dumps(short), encoding="utf-8")
    print(f"  -> {out}")


def cmd_ms(caps):
    a = np.concatenate([load(c)["ms"] for c in caps])
    b = np.concatenate([load(c)["ms_us"] for c in caps])
    print(f"players + us ms a frame (CPU bitmaps, the decode apart), {len(a)} frames: p50 / p90 / p99 "
          f"{np.percentile(a, [50, 90, 99]).round(3).tolist()} (p50 <= 0.1); us alone p50 / p90 "
          f"{np.percentile(b, [50, 90]).round(3).tolist()}")


def cmd_time(cap, n):
    """The live Perceiver over the capture's first n frames (its video): part `us_players` (us + players + the sorted
    boxes: the GPU evidence's columns) and `track`."""
    sys.path.insert(0, str(ROOT / "tools" / "perc"))
    sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
    import frames as rec
    import run as replay
    from maplebrain.procperf import prefer_performance
    print(prefer_performance())
    c = dump.clip_of(cap)
    fr = c.frames(0.0, 1e9)[:n]
    per = replay.bench_module().build(c.map_id)[0]
    up, tr, ob, trips = [], [], [], []
    ev = getattr(per, "evidence", None)
    for j, (nn, name, t) in enumerate(fr):
        img = rec.read(c.run, name)
        k0 = getattr(ev, "trips", 0)
        a = time.perf_counter()
        per.observe(img, t)
        e = time.perf_counter()
        if j >= 30:
            up.append(per.parts.get("us_players", 0.0))
            tr.append(per.parts.get("track", 0.0))
            ob.append(1000 * (e - a))
            trips.append(getattr(ev, "trips", 0) - k0)
    up, tr, ob = np.array(up), np.array(tr), np.array(ob)
    print(f"{cap}: {len(up)} frames; us_players p50 / p90 / p99 {np.percentile(up, [50, 90, 99]).round(2).tolist()} "
          f"(p50 <= 0.1; the part is kept to 0.1 ms); track p50 / p90 {np.percentile(tr, [50, 90]).round(2).tolist()}; "
          f"observe p50 {np.median(ob):.2f}; the evidence's transfers back a frame {dict(Counter(trips))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--port", action="store_true")
    ap.add_argument("--final", action="store_true", help="l5: the track's class at its end (hindsight)")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--tag", default="", help="outputs as <cap>_<tag>.pkl")
    ap.add_argument("--cfg", nargs="*", default=[], help="run: config.Track values for a variant, k=v (ints)")
    a = ap.parse_args()
    global TAG
    TAG = a.tag
    CFG.update({k: int(v) for k, v in (x.split("=", 1) for x in a.cfg)})
    caps = cache.SOUND if a.sound else a.caps
    if a.cmd == "run":
        if a.jobs > 1:
            procs, todo = [], list(caps)
            while todo or procs:
                while todo and len(procs) < a.jobs:
                    cap = todo.pop(0)
                    procs.append(subprocess.Popen([sys.executable, str(Path(__file__)), "run", cap, "--tag", a.tag]
                                                  + (["--port"] if a.port else [])
                                                  + (["--cfg", *a.cfg] if a.cfg else []), cwd=ROOT))
                procs = [p for p in procs if p.poll() is None]
                time.sleep(1)
            return
        cmd_run(caps, a.port)
    elif a.cmd == "port":
        cmd_port(caps[0])
    elif a.cmd == "l5":
        cmd_l5(a.final, a.port)
    elif a.cmd == "cover":
        cmd_cover(caps[0] if caps else cache.DESIGN)
    elif a.cmd == "us":
        cmd_us(caps or cache.SOUND)
    elif a.cmd == "heights":
        cmd_heights()
    elif a.cmd == "ms":
        cmd_ms(caps or cache.SOUND)
    elif a.cmd == "time":
        cmd_time(caps[0], a.n)
    else:
        raise SystemExit(f"unknown command {a.cmd}")


if __name__ == "__main__":
    main()
