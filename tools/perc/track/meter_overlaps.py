"""PLAN-tracker step 5a, close, PART 2 - REPORT ONLY (nothing built into maplebrain/): the user's idea "could we use the
meters to help when mobs overlap?", measured on the real tracker's rows (replay_mobs.py run --sound --meters --tag
t5a3) against the hindsight truth (oracle.py's chains, the fair counts of proto_mobs.py `sticky` / `why_switch`).

    python tools/perc/track/meter_overlaps.py ids     [--tag t5a3] [CAP ...]   a. the id errors and the meters
    python tools/perc/track/meter_overlaps.py hidden  [--tag t5a3] [CAP ...]   b. meters with no seen mob under them
    python tools/perc/track/meter_overlaps.py deaths  [--tag t5a3] [CAP ...]   c. deaths while two mobs overlap
    python tools/perc/track/meter_overlaps.py all     [--tag t5a3]             a-c + the picture sheet
    python tools/perc/track/meter_overlaps.py ties    [--tag t5a3]             Part 1's check: the readings the old
                                                                               guard refused, two narrower rules, L9

a. IDS. Every fair id switch (`why_switch`'s loop: a truth mob A leaves its track O for another track N) is one error,
   sorted by what became of O - "crossing" (O still there, near and seen: on the other mob B; the truth changed mob /
   cannot say), "the track changed mob", "life split" (O ended), "O remembered / far" - and whether it came at the end
   of a cover (a gap of the truth's chain). The error's time = 1 s before the last frame A was on O to 1 s after the
   switch. "A meter involved": a meter the reader tied to A's or B's sighting in that time, or a meter memory (`hp`)
   on O or N. "The meters alone decide": O's and N's meter memories on the frame before the switch differ (one has
   one and the other not, or the fills differ by more than 3 points) and A's first meter state after the switch
   (within 1 s: a read fill, or "none" = seen on 3+ frames with no meter in its band) matches exactly one of them
   (both none, or within 3 points); for a crossing B's state after must not match the same one. Matching O = the
   meter sides with the truth (the tracker's switch was wrong); matching N = with the tracker (the truth's link was
   wrong: the truth swaps two mobs of a kind at crossings).
b. HIDDEN. The whole-screen finder's meters (proto_meter.py `scan`, a white end seen) followed by place (`mchains`);
   a meter-frame with no seen mob under it = proto_meter's `why_untied` "no seen mob" on the t5a3 tracks. Its
   stretches are episodes; per episode the remembered tracks that can be there (confirmed, not seen, its possible
   set - or its x - within the kind's body half width of the meter's implied feet, the feet within 20 px of the
   meter's implied body top), how long, and where the track reappears against the meter's place (x = the box's
   centre less the body box's middle, the body's top = the box's top + 30) and against the set (its middle, its
   width).
c. DEATHS. Every death the tracker put (a track's first row "dying") while another track's body overlaps it (x ranges
   meet, feet within 40 px); the meter that went at the killing hit = a meter chain (whole-screen finder) whose last
   frame is 0.6 s before to 0.1 s after the die pose, its box near the two, and no new meter chain starts at its place
   within 1 s (else it was only drawn over: damage digits); its owner = the track it was last tied to (`tie`, 3 / 2
   px). Agree / differ / the meter never tied / no meter went (killed in one hit: no meter).

TIES (step 5a, close, Part 1 - the guard dropped): every taught reading (a row whose hp_t is its frame's t) against its
   track's own last reading - continues it (within 3 points), first, lower, RISES (a mob's HP never rises) - split by
   whether the old guard (replay_meters.blockers: an unseen track under it) would have refused it, and whether its fill
   equals an unseen track's memory; frames where 2+ meters name one sighting; two narrower rules over the 13 captures
   and on L9's 83 read meters: R1 "the hidden one's fill" (refuse when an unseen track under it holds the fill and the
   seen track's own memory does not), R2 "HP never rises" (refuse a reading > 3 points over the track's last).

Outputs: CORPUS/work/track-plan/meter/overlaps_<tag>.txt (the report) and overlaps_<tag>_<k>.png (the sheet).
"""
import argparse
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import cache  # noqa: E402
import load  # noqa: E402
import proto_meter as PM  # noqa: E402
import proto_mobs as P  # noqa: E402
import replay_meters as RM  # noqa: E402
import score as S  # noqa: E402
from oracle import FACE  # noqa: E402

STEP3 = Path(r"F:\dev\maple-corpus\work\track-plan\step3")
WIN = 1.0                       # s: the error's time is widened by this either side
GONE_S = 1.0                    # s: a meter whose place shows a new meter within this was only drawn over
SAME = 0.03                     # the fills of one mob: within 3 points
FACE_I = {"left": -1, "right": 1}


def out_dir() -> Path:
    return PM.meter_dir()


class Cap:
    """One capture: the truth (chains), the t5a3 rows, the reader's meters (the Perceiver's band), the whole-screen
    finder's meters (scan), the tracker's ends."""

    def __init__(self, cap: str, tag: str):
        self.cap = cap
        self.tk = load.ticks(cap)
        self.n2i = {k["n"]: i for i, k in enumerate(self.tk)}
        self.ch = cache.chains(cap, self.tk)
        self.cis = S.index(self.tk, self.ch)
        d = pickle.loads((STEP3 / f"{cap.replace('#', '_')}_{tag}.pkl").read_bytes())
        self.row_at = {self.n2i[r["n"]]: r for r in d["rows"] if r["n"] in self.n2i}
        self.rows = {r["n"]: r for r in d["rows"]}
        self.ended = d["ended"]
        self.pose = {(n, i): (p, fc) for i, _, n, _, _, _, p, fc in d["feet"]}
        self.meters = RM.read_back(cap)                       # the reader: {n: [(x0, y0, fill, cols, cand)]}
        sc = PM.scanned(cap)                                  # the whole-screen finder
        self.smeters = {n: [m for m in ms if m[7]] for _, n, _, ms in sc if ms}
        self.t_of = {n: t for _, n, t, _ in sc}
        self.ns = [n for _, n, _, _ in sc]
        self.ri = sorted(self.row_at)

    # --- the truth's points -> the fit's sighting index on that tick
    def _q(self, i, pt):
        fit = self.tk[i]["fit"] or []
        for q, f in enumerate(fit):
            if int(f["feet"][0]) == int(pt[S.SX]) and int(f["feet"][1]) == int(pt[S.SY]):
                return q
        return None

    def expect_of(self, i, pt, typ):
        """A truth point's expected meter box (x0, y0) by the place rule, from its own pose."""
        return PM.expect(typ, pt[S.POSE], 1 if pt[FACE] in ("right", 1) else -1, pt[S.SX], pt[S.SY])

    def state(self, i, pt, typ):
        """The meter state of a truth point: ('fill', v) a read meter naming it alone; ('unread',) / ('shared',) /
        ('near',) a meter there but not its own read one; ('none',) no meter in its band; (None,) not seen."""
        if pt is None:
            return (None,)
        q = self._q(i, pt)
        if q is None:
            return (None,)
        ms = self.meters.get(self.tk[i]["n"], ())
        for m in ms:
            if m[4] == (q,):
                return ("fill", m[2]) if m[2] is not None else ("unread",)
        for m in ms:
            if q in m[4]:
                return ("shared",)
        e = self.expect_of(i, pt, typ)
        for m in ms:
            if e is None or (abs(m[0] - e[0]) <= 30 and abs(m[1] - e[1]) <= 20):
                return ("near",)
        return ("none",)

    def seen_tracks(self, n):
        r = self.rows.get(n)
        return [m for m in (r["mobs"] if r else []) if m["src"] == "acq" and m["state"] != "tentative"]

    def seen(self, n):
        return self.seen_tracks(n)

    def pm(self):
        """proto_meter's Cap API (mchains / why_untied / tie) on the whole-screen finder's meters and t5a3's tracks."""
        from types import SimpleNamespace
        if not hasattr(self, "_pm"):
            self._pm = SimpleNamespace(meters=self.smeters, ns=self.ns, t_of=self.t_of, seen=self.seen_tracks,
                                       pose=self.pose)
        return self._pm

    def prev_row(self, i, tid):
        """The track's row dict on the latest tick before i where it exists (None: none)."""
        k = np.searchsorted(self.ri, i) - 1
        while k >= 0 and i - self.ri[k] <= 600:
            for m in self.row_at[self.ri[k]]["mobs"]:
                if m["id"] == tid:
                    return m
            k -= 1
        return None


def half_w(kind: int) -> float:
    PM.GEO.frame(kind, "stand_0")
    fr = PM.GEO.k[kind]["frames"]
    f = next((fr[a][0] for a in ("stand", "move", "fly") if fr.get(a) and fr[a][0].get("lt")), None)
    return 0.0 if f is None else (f["rb"][0] - f["lt"][0]) / 2


def body(kind: int, facing: int):
    """The kind's stand / move / fly frame: (middle of lt..rb mirrored by facing, lt y)."""
    PM.GEO.frame(kind, "stand_0")
    fr = PM.GEO.k[kind]["frames"]
    f = next((fr[a][0] for a in ("stand", "move", "fly") if fr.get(a) and fr[a][0].get("lt")), None)
    if f is None:
        return 0, -40
    lt, rb = f["lt"][0], f["rb"][0]
    if facing == 1:
        lt, rb = -rb, -lt
    return (lt + rb) // 2, f["lt"][1]


def match(h, st) -> bool:
    """A track's meter memory h (None or 0..1) against a state ('fill', v) / ('none',)."""
    if st[0] == "none":
        return h is None
    if st[0] == "fill":
        return h is not None and abs(h - st[1]) <= SAME
    return False


def differ(a, b) -> bool:
    return (a is None) != (b is None) or (a is not None and abs(a - b) > SAME)


def first_state(c: Cap, ci, typ, i0, t1, forward=True, min_none=3):
    """A truth chain's first (forward) / last (backward) decisive meter state in its points from tick i0 to time t1:
    a read fill at once; "none" only after min_none frames of none in a row."""
    idx = sorted(k for k in ci["pts"] if (k >= i0 if forward else k <= i0))
    if not forward:
        idx = idx[::-1]
    nn = 0
    for k in idx:
        t = c.tk[k]["t"]
        if (forward and t > t1) or (not forward and t < t1):
            break
        st = c.state(k, ci["pts"][k], typ)
        if st[0] == "fill":
            return st, k
        if st[0] == "none":
            nn += 1
            if nn >= min_none:
                return ("none",), k
        elif st[0] is not None:
            nn = 0
    return ("?",), None


# ------------------------------------------------------------------ a. ids
def switches(c: Cap) -> list:
    """Every fair id switch (proto_mobs.why_switch's loop, the same `cands`), with what the meters say."""
    out = []
    near = {}
    for kc, ci in enumerate(c.cis):
        for i, q in ci["pts"].items():
            near.setdefault(i, []).append((q[S.X], q[S.Y], kc, ci["c"]["type"]))
    for kc, ci in enumerate(c.cis):
        typ, cur, last_i = ci["c"]["type"], None, None
        gap_of = {b: a for a, b in ci["gaps"]}
        for i in sorted(ci["pts"]):
            q = ci["pts"][i]
            if S.anim_of(q[S.POSE]).startswith("die") or i not in c.row_at:
                continue
            cs = P.cands(c.row_at[i]["mobs"], typ, q[S.X], q[S.Y])
            if not cs:
                continue
            if cur is not None and cur not in cs:
                new = min(cs, key=cs.get)
                out.append(one_switch(c, kc, ci, typ, i, last_i, cur, new, gap_of, near))
                cur = new
            elif cur is None:
                cur = min(cs, key=cs.get)
            last_i = i
    return out


def rises(c: Cap, sws: list) -> list:
    """A track's taught hp rising by more than 3 points (a mob's HP never rises: no healing) - the track changed mob,
    or a meter was tied to the wrong one. -> [(cap, id, n, hp before, hp after, a fair switch of it within 2 s)]."""
    last, out = {}, []
    sw = defaultdict(list)
    for x in sws:
        if x["cap"] == c.cap:
            sw[x["old"]].append(x["t"])
            sw[x["new"]].append(x["t"])
    for n in sorted(c.rows):
        for m in c.rows[n]["mobs"]:
            h, ht = m.get("hp"), m.get("hp_t")
            if h is None or ht is None:
                continue
            p = last.get(m["id"])
            if p is not None and ht != p[1]:
                if h > p[0] + SAME:
                    t = c.rows[n]["t"]
                    out.append((c.cap, m["id"], n, p[0], h, any(abs(t - ts) <= 2.0 for ts in sw[m["id"]])))
            last[m["id"]] = (h, ht)
    return out


def kind_of(why: str) -> str:
    if "the track changed mob" in why:
        return "the track changed mob"
    if why.startswith("old track still there, near, seen"):
        return "crossing: the truth changed mob" if "truth changed mob" in why else "crossing: cannot say"
    if why.startswith("old track ended"):
        return "life split (the old track ended)"
    return "old track remembered / far"


def why_of(c: Cap, ci, typ, i, cur, q) -> str:
    """proto_mobs.why_switch's label, the same rules."""
    old = next((x for x in c.row_at[i]["mobs"] if x["id"] == cur), None)
    if old is None:
        e = c.ended.get(cur)
        return "old track ended: " + (e[1] if e else "tentative / ?") + (" (in the air)" if e and e[4] else "")
    d = abs(old["x"] - q[S.X]) + abs(old["y"] - q[S.Y])
    w = (f"old track still there, {'near' if d <= 60 else 'far'}, {'seen' if old['src'] != 'none' else 'remembered'}"
         f"{', other kind' if old['mob'] != typ else ''}")
    if d <= 60 and old["src"] != "none" and "facing" in old:
        win = [j for j in range(i - 40, i + 1) if j in ci["pts"] and j in c.row_at]
        cf = [ci["pts"][j][5] for j in win]
        tf = [m["facing"] for j in win for m in c.row_at[j]["mobs"] if m["id"] == cur and m["src"] != "none"]
        c_fl = sum(1 for a, b in zip(cf, cf[1:]) if a != b)
        t_fl = sum(1 for a, b in zip(tf, tf[1:]) if a != b)
        w += (": the truth's mob turned round, the track did not (the truth changed mob)" if c_fl and not t_fl else
              ": the track turned round, the truth's mob did not (the track changed mob)" if t_fl and not c_fl else
              ": both or neither turned round (cannot say)")
    return w


def chain_under(c: Cap, i, m, typ, not_kc) -> int:
    """The truth chain of this kind nearest a track's place on tick i, within 24 px (None)."""
    if m is None:
        return None
    best = None
    for kc, ci in enumerate(c.cis):
        if kc == not_kc or ci["c"]["type"] != typ or not (ci["i0"] <= i <= ci["i1"]):
            continue
        p = S.pos_at(ci, i)
        if p is None:
            continue
        d = abs(p[0] - m["x"]) + abs(p[1] - m["y"])
        if abs(p[0] - m["x"]) <= 24 and abs(p[1] - m["y"]) <= 24 and (best is None or d < best[0]):
            best = (d, kc)
    return None if best is None else best[1]


def one_switch(c: Cap, kc, ci, typ, i, last_i, cur, new, gap_of, near) -> dict:
    q = ci["pts"][i]
    why = why_of(c, ci, typ, i, cur, q)
    crowd = any(k2 != kc and ty == typ and abs(x - q[S.X]) <= 60 and abs(y - q[S.Y]) <= 45
                for x, y, k2, ty in near.get(i, []) + near.get(last_i, []))
    t0, t1 = c.tk[last_i]["t"], c.tk[i]["t"]
    o_row = c.prev_row(i, cur)
    n_row = c.prev_row(i, new)
    o_hp = None if o_row is None else o_row.get("hp")
    n_hp = None if n_row is None else n_row.get("hp")
    old_now = next((x for x in c.row_at[i]["mobs"] if x["id"] == cur), None)
    b = chain_under(c, i, old_now, typ, kc) if old_now is not None else None
    if b is None and n_row is not None:
        j = max((k for k in c.ri if k < i), default=None)
        b = chain_under(c, j, n_row, typ, kc) if j is not None else None
    # a meter involved in the error's time (A's or B's sighting named by a reader meter), or a memory on O / N
    inv = o_hp is not None or n_hp is not None
    for kk in ([kc] + ([b] if b is not None else [])):
        cj = c.cis[kk]
        for k in cj["pts"]:
            if t0 - WIN <= c.tk[k]["t"] <= t1 + WIN and c.state(k, cj["pts"][k], typ)[0] in ("fill", "unread",
                                                                                              "shared"):
                inv = True
                break
        if inv:
            break
    a_after, a_k = first_state(c, ci, typ, i, t1 + WIN)
    a_before, _ = first_state(c, ci, typ, last_i, t0 - WIN, forward=False)
    b_after = b_before = ("?",)
    if b is not None:
        cb = c.cis[b]
        b_after, _ = first_state(c, cb, typ, i, t1 + WIN)
        b_before, _ = first_state(c, cb, typ, last_i, t0 - WIN, forward=False)
    side = None
    if differ(o_hp, n_hp) and a_after[0] in ("fill", "none"):
        mo, mn = match(o_hp, a_after), match(n_hp, a_after)
        if mo != mn:
            side = "old" if mo else "new"
            if b is not None and b_after[0] in ("fill", "none"):        # B must not match the same track
                if (match(o_hp, b_after) if side == "old" else match(n_hp, b_after)):
                    side = None
    return {"cap": c.cap, "kc": kc, "type": typ, "i": i, "last_i": last_i, "n": c.tk[i]["n"],
            "n_last": c.tk[last_i]["n"], "t": round(t1, 2), "dt": round(t1 - t0, 3), "old": cur, "new": new,
            "why": why, "kind": kind_of(why), "cover": i in gap_of, "crowd": crowd, "b": b, "o_hp": o_hp,
            "n_hp": n_hp, "a_after": a_after, "a_k": a_k, "a_before": a_before, "b_after": b_after,
            "b_before": b_before, "involved": inv, "side": side}


def ids_report(sws: list) -> list:
    L = [f"a. IDS: {len(sws)} fair id switches (the extra ids of the fair count) on the t5a3 rows"]

    def line(name, xs):
        inv = sum(x["involved"] for x in xs)
        dec = [x for x in xs if x["side"]]
        old = sum(x["side"] == "old" for x in dec)
        rd = sum(x["a_after"][0] == "fill" for x in dec)
        return (f"  {name:44s} {len(xs):5d} | a meter involved {inv:4d} ({100 * inv / max(1, len(xs)):5.1f} %) | "
                f"the meters alone decide {len(dec):4d} ({100 * len(dec) / max(1, len(xs)):5.1f} %): with the truth "
                f"{old}, with the tracker {len(dec) - old}; by a read fill {rd}, by 'no meter' {len(dec) - rd}")
    L.append("  by kind of error:")
    for k in ("crossing: the truth changed mob", "crossing: cannot say", "the track changed mob",
              "life split (the old track ended)", "old track remembered / far"):
        xs = [x for x in sws if x["kind"] == k]
        L.append(line(k, xs))
        for cov in (True, False):
            ys = [x for x in xs if x["cover"] == cov]
            if ys:
                L.append(line("   ... " + ("at a cover's end" if cov else "in view"), ys))
    L.append(line("ALL", sws))
    L.append(line("ALL, not beside another mob of its kind", [x for x in sws if not x["crowd"]]))
    L.append("  by capture:")
    for cap in sorted({x["cap"] for x in sws}):
        L.append(line(load.name_of(cap)[:44], [x for x in sws if x["cap"] == cap]))
    # why not decided, where a meter was involved
    nd = Counter()
    for x in sws:
        if x["involved"] and not x["side"]:
            if not differ(x["o_hp"], x["n_hp"]):
                nd["the two tracks' meter memories alike" + (" (both none)" if x["o_hp"] is None else " (both read, "
                                                                                                       "within 3)")] += 1
            elif x["a_after"][0] not in ("fill", "none"):
                nd["A's meter after the switch not read (" + str(x["a_after"][0]) + ")"] += 1
            else:
                nd["A's meter after matches neither (a hit between) or both / B the same"] += 1
    L.append("  a meter involved but not decided: " + ", ".join(f"{k} {v}" for k, v in nd.most_common()))
    L.append("  the user's rule on the TWO MOBS of a crossing (A and B, their own meters before the switch: one has "
             "one and the other not, or > 3 points apart):")
    cr = [x for x in sws if x["kind"].startswith("crossing") or x["kind"] == "the track changed mob"]
    told = [x for x in cr if x["a_before"][0] in ("fill", "none") and x["b_before"][0] in ("fill", "none") and
            differ(x["a_before"][1] if x["a_before"][0] == "fill" else None,
                   x["b_before"][1] if x["b_before"][0] == "fill" else None)]
    L.append(f"    crossings with B found {sum(x['b'] is not None for x in cr)} of {len(cr)}; both states known before "
             f"{sum(x['a_before'][0] in ('fill', 'none') and x['b_before'][0] in ('fill', 'none') for x in cr)}; "
             f"A and B told apart by their meters before {len(told)}")
    return L


# ------------------------------------------------------------------ b. hidden hit mobs
def hidden(c: Cap) -> list:
    """Episodes of a meter (whole-screen finder, followed by place) with no seen mob under it."""
    chains = PM.mchains(c.pm())
    out = []
    for chn in chains:
        flags = [(n, t, m, PM.why_untied(c.pm(), n, m) == "no seen mob") for n, t, m in chn]
        k = 0
        while k < len(flags):
            if not flags[k][3]:
                k += 1
                continue
            j = k
            while j + 1 < len(flags) and flags[j + 1][3]:
                j += 1
            out.append(episode(c, chn, flags, k, j))
            k = j + 1
    return out


def can_be(c: Cap, n, m, u) -> bool:
    """A remembered track u (row dict) can be the mob under meter m on frame n: its set (or x) within the kind's half
    width of the meter's implied feet x, its feet within 20 px of the meter's implied body top."""
    C = c.tk[c.n2i[n]]["C"]
    if C is None:
        return False
    x0, y0, _, _ = PM.box_of(m)
    mid, lty = body(u["mob"], FACE_I.get(u["facing"], -1))
    fx = x0 - PM.RULE_DX - mid + C[0]                     # the implied feet x (map)
    top = y0 - PM.RULE_DY                                 # the implied body top (screen)
    if abs((u["sy"] + lty) - top) > 20:
        return False
    hw = half_w(u["mob"])
    lo, hi = (u["can"][0], u["can"][1]) if u.get("can") else (u["x"], u["x"])
    return lo - hw <= fx <= hi + hw


def under(c: Cap, n, m) -> str:
    """What the tracker has under a meter no remembered track can own (the nearest track within 60 px across whose
    feet are 0-220 px under the box)."""
    x0, y0, _, _ = PM.box_of(m)
    r = c.rows.get(n)
    best = None
    for u in (r["mobs"] if r else []):
        dx, dy = abs(u["sx"] - (x0 + 26)), u["sy"] - y0
        if dx <= 60 and 0 <= dy <= 220 and (best is None or dx < best[0]):
            best = (dx, u)
    if best is None:
        return "no track near (the fit missed it, or its body is off the play area)"
    u = best[1]
    if u["state"] == "tentative":
        return "a tentative track"
    if u["state"] == "dying":
        return "a dying track"
    if u["src"] == "acq":
        return "a seen track, its box off the rule (> 40 / 60 px)"
    return "a remembered track, not where the meter puts it"


def implied_x(c: Cap, n, m, kind, facing) -> float:
    C = c.tk[c.n2i[n]]["C"]
    x0, _, _, _ = PM.box_of(m)
    mid, _ = body(kind, facing)
    return x0 - PM.RULE_DX - mid + C[0]


def episode(c: Cap, chn, flags, k, j) -> dict:
    n0, t0 = flags[k][0], flags[k][1]
    n1, t1, m1 = flags[j][0], flags[j][1], flags[j][2]
    cands, what = Counter(), Counter()
    frames_with = 0
    for n, t, m, _ in flags[k:j + 1]:
        r = c.rows.get(n)
        if r is None:
            continue
        us = [u for u in r["mobs"] if u["src"] == "none" and u["state"] in ("hidden", "offscreen") and can_be(c, n, m, u)]
        frames_with += bool(us)
        cands.update(u["id"] for u in us)
        if not us:
            what.update([under(c, n, m)])
    e = {"cap": c.cap, "n0": n0, "n1": n1, "t0": t0, "s": round(t1 - t0 + 1 / 60, 3), "frames": j - k + 1,
         "frames_with": frames_with, "cands": dict(cands), "end": None,
         "what": what.most_common(1)[0][0] if what else None}
    # how it ended: the meter's next frame in its chain tied to a seen track, or the meter went
    nxt = flags[j + 1] if j + 1 < len(flags) else None
    if nxt is None:
        e["end"] = "the meter went (or left view)"
    else:
        tr = PM.tie(c.pm(), nxt[0], nxt[2])
        e["end"] = "a seen mob under it again" + ("" if tr else " (not tied by the rule)")
        e["end_id"] = tr["id"] if tr else None
    if cands:
        uid = cands.most_common(1)[0][0]
        e["uid"] = uid
        last = next((u for u in c.rows[n1]["mobs"] if u["id"] == uid), None) if n1 in c.rows else None
        if last is None:                                  # not on the last frame: the latest frame it was a candidate
            for n, t, m, _ in flags[k:j + 1][::-1]:
                last = next((u for u in c.rows.get(n, {"mobs": []})["mobs"] if u["id"] == uid), None)
                if last is not None:
                    n1, m1 = n, m
                    break
        fx = implied_x(c, n1, m1, last["mob"], FACE_I.get(last["facing"], -1))
        e["meter_x"], e["set"] = fx, last.get("can")
        e["mem_x"] = last["x"]
        # where the track is next seen
        i1 = c.n2i[n1]
        for kk in c.ri[int(np.searchsorted(c.ri, i1, side="right")):]:
            if c.tk[kk]["t"] - c.tk[i1]["t"] > 4.5:
                break
            u = next((x for x in c.row_at[kk]["mobs"] if x["id"] == uid), None)
            if u is None:
                e["after"] = "ended unseen"
                break
            if u["src"] == "acq":
                e["after"] = "seen again"
                e["re_x"], e["re_s"] = u["x"], round(c.tk[kk]["t"] - c.tk[i1]["t"], 3)
                break
        e.setdefault("after", "not seen within 4.5 s")
    return e


def hidden_report(eps: list) -> list:
    fr = sum(e["frames"] for e in eps)
    L = [f"b. HIDDEN HIT MOBS: {len(eps)} episodes of a meter with no seen mob under it, {fr} meter-frames"]
    w = [e for e in eps if e["cands"]]
    L.append(f"  a remembered track can be there on some frame: {len(w)} episodes ({sum(e['frames'] for e in w)} frames; "
             f"its frames with one {sum(e['frames_with'] for e in w)}); none can: {len(eps) - len(w)} "
             f"({fr - sum(e['frames'] for e in w)} frames)")
    for name, xs in (("with a remembered track", w), ("with none", [e for e in eps if not e["cands"]])):
        s = np.array([e["s"] for e in xs]) if xs else np.array([0.0])
        L.append(f"    {name}: how long s p50 / p90 / max {S.pct(s, (50, 90, 100))}; >= 0.25 s "
                 f"{int((s >= 0.25).sum())}; ended: " + ", ".join(f"{k} {v}" for k, v in
                                                                 Counter(e["end"] for e in xs).most_common()))
    L.append("    with none, what the tracker has under it: " + ", ".join(
        f"{k} {v}" for k, v in Counter(e["what"] for e in eps if not e["cands"]).most_common()))
    two = [e for e in w if len(e["cands"]) > 1]
    L.append(f"    two or more remembered tracks can be there: {len(two)} episodes")
    ag = [e for e in w if e.get("after") == "seen again"]
    L.append(f"  the remembered track afterwards: " + ", ".join(f"{k} {v}" for k, v in
                                                            Counter(e.get("after") for e in w).most_common()))
    if ag:
        dm = np.array([abs(e["meter_x"] - e["re_x"]) for e in ag])
        ds = np.array([abs(e["mem_x"] - e["re_x"]) for e in ag])
        wd = np.array([(e["set"][1] - e["set"][0]) if e["set"] else 0.0 for e in ag])
        ins = np.array([(e["set"][0] - 4 <= e["re_x"] <= e["set"][1] + 4) if e["set"] else abs(ds_) <= 4
                        for e, ds_ in zip(ag, ds)])
        L.append(f"  seen again ({len(ag)}): |meter's x - where it reappears| px p50 / p90 / max {S.pct(dm, (50, 90, 100))}; "
                 f"|the set's middle - there| {S.pct(ds, (50, 90, 100))}; the set's width {S.pct(wd, (50, 90, 100))}; "
                 f"reappears inside its set {int(ins.sum())} of {len(ag)}")
        L.append(f"    the meter closer than the set's middle by more than 4 px: {int((dm + 4 < ds).sum())}; farther: "
                 f"{int((dm > ds + 4).sum())}; the meter within 8 px {int((dm <= 8).sum())}; the meter outside the "
                 f"set's width / 2 + 8 of the set's middle never (the meter is inside the set by `can_be`)")
        rs = np.array([e["re_s"] for e in ag])
        L.append(f"    seen again after s p50 / p90 / max {S.pct(rs, (50, 90, 100))}")
    by = Counter()
    for e in eps:
        by[load.name_of(e["cap"])[:40]] += 1
    L.append("  by capture (episodes): " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
    return L


# ------------------------------------------------------------------ c. deaths while two mobs overlap
def final_deaths(c: Cap) -> tuple:
    """The tracker's deaths: per track whose end is a death (`ended` "died ..."), the first row of its last dying
    stretch -> {id: (n, row)}; and the number of dying stretches taken back (a living pose next)."""
    runs, prev = {}, {}
    for n in sorted(c.rows):
        for m in c.rows[n]["mobs"]:
            if m["state"] == "dying":
                if prev.get(m["id"]) != "dying":
                    runs.setdefault(m["id"], []).append((n, m))
            prev[m["id"]] = m["state"]
    out, back = {}, 0
    for tid, rs in runs.items():
        e = c.ended.get(tid)
        died = e is not None and e[1].startswith("died")
        back += len(rs) - (1 if died else 0)
        if died:
            out[tid] = rs[-1]
    return out, back


def owner_fate(c: Cap, o, t, deaths) -> str:
    """What became of the track a meter that went was tied to, against a death at time t."""
    if o in deaths:
        od = c.tk[c.n2i[deaths[o][0]]]["t"]
        if abs(od - t) <= 1.0:
            return "the owner died too (within 1 s)"
    seen = meter = 0
    i0 = c.n2i.get(min((n for n in c.rows if c.tk[c.n2i[n]]["t"] >= t), default=None, key=lambda n: n))
    for i in range(i0 or 0, len(c.tk)):
        if c.tk[i]["t"] > t + 1.0:
            break
        r = c.row_at.get(i)
        u = next((m for m in (r["mobs"] if r else []) if m["id"] == o), None)
        if u is None or u["src"] != "acq":
            continue
        seen += 1
        fit = c.tk[i]["fit"] or []
        for m in c.meters.get(c.tk[i]["n"], ()):
            if len(m[4]) == 1 and m[4][0] < len(fit):
                fx, fy = fit[m[4][0]]["feet"]
                if abs(fx - u["sx"]) <= 3 and abs(fy - u["sy"]) <= 20:
                    meter += 1
                    break
    if meter:
        return "the owner lives on WITH a meter (the meter that went was another's: the tie named the wrong one)"
    if seen >= 10:
        return "the owner lives on, seen, no meter tied"
    return "the owner not seen again within 1 s"


def deaths(c: Cap) -> list:
    first, _ = final_deaths(c)
    chains = PM.mchains(c.pm())
    starts = [(chn[0][1], PM.box_of(chn[0][2])) for chn in chains]
    ends = []
    for chn in chains:
        tid = None
        for n, t, m in chn[::-1]:
            tr = PM.tie(c.pm(), n, m)
            if tr is not None:
                tid = tr["id"]
                break
        t1, b1 = chn[-1][1], PM.box_of(chn[-1][2])
        # a meter only drawn over (damage digits, another meter) for more than mchains' gap comes back as a new
        # chain at its place: that is not a meter that went
        back = any(t1 < ts <= t1 + GONE_S and abs(bs[0] - b1[0]) <= 30 and abs(bs[1] - b1[1]) <= 20 for ts, bs in starts)
        if not back:
            ends.append((chn[-1][0], t1, chn[-1][2], tid, chn))
    out = []
    for tid, (n, m) in first.items():
        t = c.tk[c.n2i[n]]["t"] if n in c.n2i else c.t_of.get(n)
        hw = half_w(m["mob"])
        ov = []
        for u in c.rows[n]["mobs"]:
            if u["id"] == tid or u["state"] == "tentative":
                continue
            hu = half_w(u["mob"])
            lo, hi = (u["can"][0], u["can"][1]) if u.get("can") else (u["x"], u["x"])
            if lo - hu <= m["x"] + hw and hi + hu >= m["x"] - hw and abs(u["y"] - m["y"]) <= 40:
                ov.append(u)
        if not ov:
            continue
        near = [e for e in ends if t - 0.6 <= e[1] <= t + 0.1 and abs(PM.box_of(e[2])[0] + 26 - m["sx"]) <= 80
                and -220 <= PM.box_of(e[2])[1] - m["sy"] <= 0]
        owners = [e[3] for e in near]
        if not near:
            verdict = "no meter went near"
        elif tid in owners:
            verdict = "agree"
        elif all(o is None for o in owners):
            verdict = "the meter never tied"
        else:
            verdict = "DIFFER"
        fate = [owner_fate(c, o, t, first) for o in set(owners) if o is not None] if verdict == "DIFFER" else []
        out.append({"cap": c.cap, "n": n, "t": t, "id": tid, "kind": m["mob"], "sx": m["sx"], "sy": m["sy"], "fate": fate,
                    "over": [(u["id"], u["state"], u["src"]) for u in ov], "owners": owners, "verdict": verdict,
                    "meters": [(e[0], PM.box_of(e[2])[:2], e[3]) for e in near]})
    return out


def deaths_report(ds: list) -> list:
    L = [f"c. DEATHS WHILE TWO MOBS OVERLAP: {len(ds)} final deaths the tracker put with another track's body over it "
         f"(deaths taken back not counted: {deaths_report.back})"]
    L.append("  " + ", ".join(f"{k} {v}" for k, v in Counter(d["verdict"] for d in ds).most_common()))
    sub = Counter((d["verdict"], "the other seen" if any(s == "acq" for _, _, s in d["over"]) else "the other unseen")
                  for d in ds)
    L.append("  by the other track: " + ", ".join(f"{a} / {b} {v}" for (a, b), v in sorted(sub.items())))
    for d in ds:
        if d["verdict"] == "DIFFER":
            L.append(f"    DIFFER {load.name_of(d['cap'])[:30]} n {d['n']} t {d['t']:.2f}: death on {d['id']} "
                     f"(kind {d['kind']}); over it {d['over']}; the meters that went {d['meters']}; {d['fate']}")
    L.append("  the differences by the owner's fate: " + ", ".join(
        f"{k} {v}" for k, v in Counter(f for d in ds for f in d["fate"]).most_common()))
    return L


# ------------------------------------------------------------------ the sheet
def _img(c: Cap, n: int):
    """Frame n with the whole-screen finder's meters boxed (magenta)."""
    import cv2
    img = PM.read_frame(c.cap, n).copy()
    for m in c.smeters.get(n, []):
        x0, y0, x1, y1 = PM.box_of(m)
        cv2.rectangle(img, (x0 - 1, y0 - 1), (x1, y1), (255, 0, 255), 1)
    return img


def _hp(h) -> str:
    return "-" if h is None else f"{h:.2f}"


def sheet(caps_obj: dict, sws, eps, ds, tag, limit=30) -> list:
    """The cases where the meter would have decided, one row of three frames each (meters boxed magenta): c - a death
    the meter contradicts (its owner lives on, seen, with no meter); b - hidden mobs the meter places closer than the
    set's middle (6 at most); a - id switches the meters decide, those that side with the truth (the tracker wrong)
    first, then those that side with the tracker, read fills first."""
    import cv2
    cs = [("c", d) for d in ds if d["verdict"] == "DIFFER" and any("no meter tied" in f for f in d["fate"])]
    cs += [("b", e) for e in eps if e.get("after") == "seen again" and
           abs(e["meter_x"] - e["re_x"]) + 4 < abs(e["mem_x"] - e["re_x"])][:6]
    a = sorted([x for x in sws if x["side"]], key=lambda x: (x["side"] != "old", x["a_after"][0] != "fill", x["t"]))
    cs += [("a", x) for x in a[:max(0, limit - len(cs))]]
    W, H, Z = 170, 120, 3
    rows, lines = [], []
    for kk, (what, x) in enumerate(cs):
        c = caps_obj[x["cap"]]
        tl = []
        if what == "a":
            for nn, lab in ((x["n_last"], "before"), (x["n"], "switch"),
                            (c.tk[x["a_k"]]["n"] if x["a_k"] is not None else x["n"], "A's meter after")):
                r = c.rows.get(nn, {"mobs": []})
                marks = []
                for j, m in enumerate(m for m in r["mobs"] if m["id"] in (x["old"], x["new"])):
                    name = "O" if m["id"] == x["old"] else "N"
                    marks.append((m["sx"], m["sy"] - 12 * j, f"{name}{m['id']} {_hp(m['hp'])}{'' if m['src'] == 'acq' else ' unseen'}",
                                  (0, 255, 255) if name == "O" else (0, 140, 255)))
                q = c.cis[x["kc"]]["pts"].get(c.n2i.get(nn))
                if q is not None:
                    marks.append((q[S.SX], q[S.SY] + 10, "A", (0, 0, 255)))
                cx, cy = (q[S.SX], q[S.SY] - 45) if q is not None else (marks[0][0], marks[0][1] - 45) if marks else (683, 350)
                tl.append(PM.tile(_img(c, nn), int(cx), int(cy), W, H, Z, marks, f"{kk} a {lab} n{nn}"))
            lines.append(f"  {kk} a {load.name_of(x['cap'])[:28]} n {x['n']}: {x['kind']}{', at a cover end' if x['cover'] else ''}; "
                         f"O {x['old']} hp {_hp(x['o_hp'])}, N {x['new']} hp {_hp(x['n_hp'])}; A's meter after {x['a_after']}, "
                         f"B's {x['b_after']} -> the meter sides with {'the truth (the tracker wrong)' if x['side'] == 'old' else 'the tracker'}")
        elif what == "b":
            uid = x.get("uid")
            for nn, lab in ((x["n0"], "meter, no mob seen"), (x["n1"], "last such frame"), (None, "seen again")):
                if nn is None:
                    i1 = c.n2i[x["n1"]]
                    nn = next((c.tk[k]["n"] for k in c.ri[int(np.searchsorted(c.ri, i1, side="right")):]
                               if any(m["id"] == uid and m["src"] == "acq" for m in c.row_at[k]["mobs"])), x["n1"])
                r = c.rows.get(nn, {"mobs": []})
                marks = [(m["sx"], m["sy"], f"{m['id']}{'' if m['src'] == 'acq' else ' unseen'}",
                          (0, 140, 255) if m["id"] == uid else (0, 255, 255)) for m in r["mobs"]
                         if m["state"] != "tentative" and (m["id"] == uid or m["src"] == "acq")]
                C = c.tk[c.n2i[nn]]["C"]
                cx = (x["meter_x"] - C[0]) if C is not None else 683
                cy = next((m["sy"] for m in r["mobs"] if m["id"] == uid), 400) - 45
                if C is not None:
                    marks.append((x["meter_x"] - C[0], cy + 60, "meter", (255, 0, 255)))
                tl.append(PM.tile(_img(c, nn), int(cx), int(cy), W, H, Z, marks, f"{kk} b {lab} n{nn}"))
            lines.append(f"  {kk} b {load.name_of(x['cap'])[:28]} n {x['n0']}-{x['n1']}: {x['s']} s with no seen mob under the "
                         f"meter; track {uid} remembered at x {x['mem_x']:.0f}, its set {x['set']}; the meter puts it at "
                         f"{x['meter_x']:.0f}; seen again at {x['re_x']:.0f} after {x['re_s']} s")
        else:
            nm = x["meters"][0][0] if x["meters"] else x["n"]
            for nn, lab in ((nm, "the meter's last"), (x["n"], "the death"), (x["n"] + 20, "death +0.33 s")):
                r = c.rows.get(nn, {"mobs": []})
                ids = [x["id"]] + [o for o in x["owners"] if o is not None]
                marks = [(m["sx"], m["sy"] - 12 * j, f"{m['id']} {m['state'][:4]} {_hp(m['hp'])}",
                          (0, 0, 255) if m["id"] == x["id"] else (0, 255, 0))
                         for j, m in enumerate(m for m in r["mobs"] if m["id"] in ids)]
                tl.append(PM.tile(_img(c, nn), int(x["sx"]), int(x["sy"]) - 45, W, H, Z, marks, f"{kk} c {lab} n{nn}"))
            lines.append(f"  {kk} c {load.name_of(x['cap'])[:28]} n {x['n']}: the death on {x['id']} (red); the meter that "
                         f"went was tied to {x['owners']} (green), which lives on with no meter")
        rows.append(tl)
    paths = []
    for s in range(0, len(rows), 5):
        p = out_dir() / f"overlaps_{tag}_{s // 5}.png"
        cv2.imwrite(str(p), PM.grid([t for r in rows[s:s + 5] for t in r], 3))
        paths.append(p)
    return lines + [f"  sheet: {p}" for p in paths]


def ties(tag: str) -> list:
    import json
    tot, two, R1R2 = Counter(), Counter(), Counter()
    runs = {}
    for cap in cache.SOUND:
        R = RM.Run(cap, tag)
        runs[cap] = R
        last = {}
        R.v = {}
        for n in sorted(R.rows):
            r = R.rows[n]
            for m in r["mobs"]:
                if m["hp_t"] is None:
                    continue
                if abs(m["hp_t"] - r["t"]) < 1e-6:
                    prev = last.get(m["id"])
                    bl = RM.blockers(R, n, m)
                    hid = any(u.get("hp") is not None and abs(u["hp"] - m["hp"]) <= SAME for u in bl)
                    k = "under the old guard" if bl else "no unseen track under it"
                    tot[k] += 1
                    cls = ("first reading" if prev is None else "continues its own" if abs(m["hp"] - prev) <= SAME
                           else "lower" if m["hp"] < prev else "RISES")
                    tot[f"{k}: {cls}" + (" (= an unseen one's memory)" if hid and cls in ("lower", "RISES") else "")] += 1
                    own = prev is not None and abs(prev - m["hp"]) <= SAME
                    r1, r2 = (not own) and hid, prev is not None and m["hp"] > prev + SAME
                    R.v[(n, m["id"])] = (r1, r2, bool(bl))
                    R1R2["taught"] += 1
                    R1R2["R1 refuses"] += r1
                    R1R2["R2 refuses"] += r2
                    R1R2["R1 or R2"] += r1 or r2
                last[m["id"]] = m["hp"]
        for n, lst in R.meters.items():
            one = Counter(m[4][0] for m in lst if len(m[4]) == 1)
            for q, k in one.items():
                if k > 1:
                    two["sightings named by 2+ meters"] += 1
                    f = sorted(m[2] for m in lst if m[4] == (q,) and m[2] is not None)
                    two["... with two read fills > 3 points apart"] += len(f) > 1 and f[-1] - f[0] > SAME
    L = ["TIES (Part 1: the guard dropped) - every taught reading against its track's own last one:"]
    L += [f"  {k}: {tot[k]}" for k in sorted(tot)]
    L.append("  " + ", ".join(f"{k} {v}" for k, v in two.items()))
    L.append("  two narrower rules over the 13 captures: " + ", ".join(f"{k} {v}" for k, v in R1R2.items()))
    cases = json.loads((RM.L9_DIR / "cases.json").read_text(encoding="utf-8"))
    J = RM.judged("a")
    l9 = Counter()
    for k, case in enumerate(cases):
        j = J.get(k)
        if not j or not j.get("meters"):
            continue
        R = runs[case["cap"]]
        n = case["n"]
        for lab in j["meters"]:
            x0, info = RM.label_box(case, lab)
            if info is None or lab.get("mob") in (None, "?", "none"):
                continue
            bx, by = info["band"]
            g = next((g for g in R.meters.get(n, []) if bx - 4 <= g[0] <= bx + 26 and by - 6 <= g[1] <= by + 12 and
                      (x0 is None or abs(g[0] - x0) <= 2)), None)
            tt = R.taught(n, g) if g is not None else None
            if tt is not None and tt["id"] == info["track"]:
                r1, r2, gd = R.v.get((n, tt["id"]), (False, False, False))
                l9["read, tied right"] += 1
                l9["R1 refuses"] += r1
                l9["R2 refuses"] += r2
                l9["the old guard refuses"] += gd
                if r1 or r2:
                    L.append(f"    L9 case {k} {case['cap']} n {n}: track {tt['id']} fill {g[2]} refused by"
                             f"{' R1' if r1 else ''}{' R2' if r2 else ''} (tied right by eye)")
    L.append("  L9's read meters tied right (t5a3): " + ", ".join(f"{k} {v}" for k, v in l9.items()))
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("ids", "hidden", "deaths", "all", "ties"))
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--tag", default="t5a3")
    a = ap.parse_args()
    if a.cmd == "ties":
        print("\n".join(ties(a.tag)))
        return
    caps = a.caps or list(cache.SOUND)
    sws, eps, ds, objs = [], [], [], {}
    for cap in caps:
        c = Cap(cap, a.tag)
        objs[cap] = c
        if a.cmd in ("ids", "all"):
            mine = switches(c)
            sws += mine
            main.rises = getattr(main, "rises", []) + rises(c, mine)
        if a.cmd in ("hidden", "all"):
            eps += hidden(c)
        if a.cmd in ("deaths", "all"):
            ds += deaths(c)
            deaths_report.back = getattr(deaths_report, "back", 0) + final_deaths(c)[1]
        print(f"{cap}: switches {len(sws)}, hidden episodes {len(eps)}, overlapped deaths {len(ds)}", flush=True)
    L = []
    if sws:
        L += ids_report(sws)
        rs = main.rises
        L.append(f"  a track's taught hp RISING by more than 3 points (a mob's HP never rises): {len(rs)} times on "
                 f"{len({(r[0], r[1]) for r in rs})} tracks; with a fair switch of that track within 2 s: "
                 f"{sum(r[5] for r in rs)}; by capture: " + ", ".join(
                     f"{load.name_of(k)[:24]} {v}" for k, v in sorted(Counter(r[0] for r in rs).items())))
    if eps:
        L += hidden_report(eps)
    if ds or a.cmd in ("deaths", "all"):
        L += deaths_report(ds)
    if a.cmd == "all":
        L += ["", "THE SHEET (cases where the meter would have decided):"] + sheet(objs, sws, eps, ds, a.tag)
        (out_dir() / f"overlaps_{a.tag}.pkl").write_bytes(pickle.dumps({"ids": sws, "hidden": eps, "deaths": ds}))
    txt = "\n".join(L)
    print(txt)
    if a.cmd == "all":
        (out_dir() / f"overlaps_{a.tag}.txt").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
