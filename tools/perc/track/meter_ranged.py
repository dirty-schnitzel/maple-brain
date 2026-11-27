"""PLAN-tracker step 5a, try 2 - REPORT ONLY (no gate; the user's answer 4 under "Step 5a, 2026-11-26"): does a ranged
class change the HP meter? The real reader (replay_meters.py `read`), the whole-screen finder (proto_meter.py `scan`)
and the mob tracker's rows (replay_mobs.py run --meters --tag T) of one capture, with ITS attack keys given here (a
class's keys belong in step 6's profile, not in config.Keys). Nothing in maplebrain/ is read but through those files.

    python tools/perc/track/meter_ranged.py report CAP --attack space [--buffs 1,2] [--tag t5a2]
    python tools/perc/track/meter_ranged.py report 20261118_232410_1#3 --attack q,w,e      the spearman, same map
    python tools/perc/track/meter_ranged.py sheet CAP --attack space [--n 30] [--seed 1]   30 random + every cut meter
    python tools/perc/track/meter_ranged.py odd CAP --attack space [--buffs 1,2]           new meters outside the
                                                                    window, meters under the buffs, Zombie tracks

`report`: (1) the place rule (proto_meter `ties`: meter-frames of chains tied at least once, tied to exactly one seen
mob); (2) every NEW meter (proto_meter `new_meters`) against the attack key-downs: the delay from the nearest key-down
and, on the clean cases (exactly one key-down in the 1.3 s before), the delay against the distance from us (the kept
replay's `me`: our tag's middle) to the mob (its screen feet); the new meters with no key-down inside try 1's window
(0.20-0.80 s); (3) the scan's meters on frames within BUFF_S of a buff key-down: found by the real reader and their fill
read, against the other frames; (4) the reader's meters naming a Zombie Mushroom sighting: per track, its poses and its
map-x span (a scenery ghost: no hit / die pose and no motion); (5) the tracker's meter stats. Sheets go to
CORPUS/work/track-plan/meter/ranged/.
"""
import argparse
import json
import pickle
import random
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2]))
import dump  # noqa: E402
import load  # noqa: E402
import proto_meter as PM  # noqa: E402
import replay_meters as RM  # noqa: E402

WIN = (0.20, 0.80)                      # try 1's window (MWIN q / w): key-down -> a NEW meter
BUFF_S = 1.5                            # a buff's effect, s after its key-down (looked at on the sheet)
HOLD_S = 0.5                            # an attack key down this long is HELD (it repeats); a tap is <= 0.19 s
ZOMBIE = "Zombie Mushroom"


def out_dir() -> Path:
    d = PM.meter_dir() / "ranged"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup(attack: list, tag: str):
    """proto_meter's Cap reads the tracker rows of `tag` and the key-downs of `attack` (its module globals)."""
    PM.TAG = tag
    PM.SKILLS = tuple(attack)
    PM.MWIN = {k: PM.MWIN.get(k, WIN) for k in attack}


def key_downs(cap, keys) -> list:
    run = load.run_path(cap)
    return [(k["t"], k["key"]) for k in map(json.loads, open(run / "keys.jsonl", encoding="utf-8"))
            if k.get("down") and k["key"] in keys]


def key_holds(cap, keys) -> list:
    """[(down t, up t, key)] of the attack keys: a key held keeps attacking with no new key-down (the assassin's
    space held 2.76 s: two new meters inside it, 0.8 s apart)."""
    run = load.run_path(cap)
    out, cur = [], {}
    for k in map(json.loads, open(run / "keys.jsonl", encoding="utf-8")):
        if k["key"] not in keys:
            continue
        if k.get("down"):
            cur.setdefault(k["key"], k["t"])
        elif k["key"] in cur:
            out.append((cur.pop(k["key"]), k["t"], k["key"]))
    return out + [(t, 1e9, key) for key, t in cur.items()]


def same_box(a, b, tol=2) -> bool:
    """A scan meter (proto_meter row) and a reader meter (x0, y0, fill, cols, cand) at one box."""
    x0, y0, _, _ = PM.box_of(a)
    return abs(b[0] - x0) <= tol and abs(b[1] - y0) <= tol


class Data:
    def __init__(self, cap, attack, tag):
        setup(attack, tag)
        self.cap = cap
        self.c = PM.Cap(cap)
        self.R = RM.Run(cap, tag)
        self.R.keys = [(t, k) for t, k in key_downs(cap, attack)]
        self.me = {r["n"]: r.get("me") for n, r in self.R.kept.items()}
        self.kinds = load.Map(load.map_of(cap)).mobs

    def kind_name(self, k):
        return (self.kinds.get(k) or {}).get("name", str(k))


# ------------------------------------------------------------------ report
def place_rule(D) -> str:
    cnt = Counter()
    for ch in PM.mchains(D.c):
        if len(ch) < 3 or max(m[2] for _, _, m in ch) < 6:
            continue
        ws = [PM.why_untied(D.c, n, m) for n, _, m in ch]
        if "tied" not in ws:
            cnt["chains never tied"] += 1
            continue
        cnt.update(ws)
    tot = sum(v for k, v in cnt.items() if not k.startswith("chains"))
    s = ", ".join(f"{k} {v} ({100 * v / tot:.1f} %)" for k, v in cnt.most_common() if not k.startswith("chains"))
    return (f"  place rule: meter-frames of chains tied at least once {tot}; {s}; chains never tied "
            f"{cnt['chains never tied']}")


def new_rows(D) -> list:
    """Every NEW meter: its first frame, the tied track at its start, the key-downs in the 1.3 s before, our x and
    the mob's screen feet on that frame."""
    out = []
    holds = key_holds(D.cap, PM.SKILLS)
    for chn, tid in PM.new_meters(D.c, PM.mchains(D.c)):
        n0, t0, m0 = chn[0]
        ks = sorted((round(t0 - kt, 3), k) for kt, k in D.c.keys if 0.0 <= t0 - kt <= 1.3)
        held = [(round(t0 - a, 3), k) for a, b, k in holds         # a hold (>= HOLD_S down; taps <= 0.19 s) going on
                if b - a >= HOLD_S and t0 - a > WIN[0] and b >= t0 - WIN[0]]
        mob = None
        if tid is not None:
            for n, _, _ in chn[:30]:
                mob = next((m for m in D.c.seen(n) if m["id"] == tid), None)
                if mob is not None:
                    break
        me = D.me.get(n0)
        out.append({"n0": n0, "t0": t0, "box": PM.box_of(m0), "tid": tid, "keys": ks, "len": len(chn), "held": held,
                    "kind": None if mob is None else mob["mob"], "mx": None if mob is None else mob["sx"],
                    "my": None if mob is None else mob["sy"], "me": me,
                    "dist": None if mob is None or me is None else abs(mob["sx"] - me[0]),
                    "dy": None if mob is None or me is None else mob["sy"] - me[1]})
    return out


def delay_report(rows) -> list:
    L = []
    near = [r["keys"][0][0] for r in rows if r["keys"]]
    inwin = [r for r in rows if any(WIN[0] <= lag <= WIN[1] for lag, _ in r["keys"])]
    held = [r for r in rows if r not in inwin and r["held"]]
    nokey = [r for r in rows if not r["keys"]]
    L.append(f"  new meters {len(rows)}: a key-down within 1.3 s before {len(near)}, none {len(nokey)}; one inside "
             f"try 1's window {WIN[0]:.2f}-{WIN[1]:.2f} s: {len(inwin)} ({100 * len(inwin) / max(1, len(rows)):.1f} %); "
             f"else while an attack key was held (pressed more than {WIN[0]:.2f} s before): {len(held)}")
    L.append(f"  the nearest key-down -> the meter, s p0/5/50/95/100 {PM.pct(near, (0, 5, 50, 95, 100), 3)} "
             f"(n {len(near)})")
    clean = [r for r in rows if len(r["keys"]) == 1 and r["dist"] is not None and not r["held"]]
    lag = np.array([r["keys"][0][0] for r in clean])
    dist = np.array([r["dist"] for r in clean], float)
    L.append(f"  clean (exactly one key-down in the 1.3 s before, no key held, the mob known): n {len(clean)}; lag "
             f"p0/5/50/95/100 "
             f"{PM.pct(lag, (0, 5, 50, 95, 100), 3)}; the distance us -> mob, px p0/50/100 "
             f"{PM.pct(dist, (0, 50, 100), 0)}")
    for lo, hi in ((0, 100), (100, 200), (200, 300), (300, 400), (400, 2000)):
        sel = (dist >= lo) & (dist < hi)
        if sel.any():
            L.append(f"    distance {lo:4d}-{hi if hi < 2000 else '':4} px: n {int(sel.sum()):3d}, lag p0/50/100 "
                     f"{PM.pct(lag[sel], (0, 50, 100), 3)}")
    if len(clean) >= 3 and np.ptp(dist) > 50:
        b, a = np.polyfit(dist, lag, 1)
        r = np.corrcoef(dist, lag)[0, 1]
        L.append(f"    lag = {a:.3f} s + {1000 * b:.3f} ms a px (r {r:.2f})"
                 + (f": {1 / b:.0f} px/s" if b > 1e-5 else ""))
    every = [(lag_, r["dist"]) for r in rows if r["dist"] is not None for lag_, _ in r["keys"][:1]]
    if every:
        e = np.array(every, float)
        L.append(f"  every new meter with a key-down and its mob (the nearest key-down): n {len(e)}; distance p50 / "
                 f"p90 / max {PM.pct(e[:, 1], (50, 90, 100), 0)} px")
    out = [r for r in rows if r not in inwin]
    L.append(f"  NOT inside try 1's window: {len(out)}")
    for r in out:
        L.append(f"    n {r['n0']} t {r['t0']:.3f} box {r['box']} track {r['tid']} kind {r['kind']} dist {r['dist']} "
                 f"keys {r['keys']} held {r['held']} chain {r['len']} frames")
    return L


def buff_report(D, buffs) -> list:
    if not buffs:
        return []
    bt = np.array(sorted(t for t, _ in key_downs(D.cap, buffs)))
    cnt = {True: Counter(), False: Counter()}
    for n, ms in D.c.meters.items():
        t = D.c.t_of[n]
        j = np.searchsorted(bt, t)
        inb = bool(j > 0 and t - bt[j - 1] <= BUFF_S)
        got = D.R.meters.get(n, [])
        for m in ms:
            if not m[7] or m[2] < 6:
                continue
            if not PM.tie(D.c, n, m):
                continue                                    # a real meter over a seen mob (the place rule)
            cnt[inb]["meters"] += 1
            g = next((g for g in got if same_box(m, g)), None)
            cnt[inb]["found"] += g is not None
            cnt[inb]["fill read"] += g is not None and g[2] is not None
            cnt[inb]["fill read, scan"] += m[10] is not None
    L = [f"  buffs {','.join(buffs)}: {len(bt)} key-downs; frames within {BUFF_S} s after one:"]
    for k, name in ((True, "under a buff"), (False, "the other frames")):
        c = cnt[k]
        L.append(f"    {name}: meters tied by the place rule {c['meters']}; found by the reader {c['found']} "
                 f"({100 * c['found'] / max(1, c['meters']):.1f} %), its fill read {c['fill read']} "
                 f"({100 * c['fill read'] / max(1, c['meters']):.1f} %); the scan's fill read {c['fill read, scan']}")
    return L


def zombie_rows(D) -> dict:
    """Per track named alone by a reader meter whose one candidate is a Zombie Mushroom sighting: frames, poses,
    the map-x span of its life, taught frames."""
    pose_of = {}
    for (n, i), (p, _) in D.c.pose.items():
        pose_of.setdefault(i, []).append(p)
    life = {}
    for r in D.R.rows.values():
        for m in r["mobs"]:
            life.setdefault(m["id"], []).append(m["x"])
    out = {}
    for n, ms in D.R.meters.items():
        fit = D.R.kept[n]["facts"].get("fit") or []
        for g in ms:
            if len(g[4]) != 1 or g[4][0] >= len(fit):
                continue
            if D.kind_name(fit[g[4][0]]["type"]) != ZOMBIE:
                continue
            tr = D.R.track_of(n, g[4][0])
            key = tr["id"] if tr is not None else ("no track", n)
            o = out.setdefault(key, {"frames": [], "taught": 0})
            o["frames"].append(n)
            o["taught"] += D.R.taught(n, g) is not None
    for k, o in out.items():
        if isinstance(k, tuple):
            continue
        ps = pose_of.get(k, [])
        xs = life.get(k, [])
        o["poses"] = Counter(p.rpartition("_")[0] for p in ps)
        o["span"] = (max(xs) - min(xs)) if xs else None
        o["hitdie"] = sum(v for a, v in o["poses"].items() if a.startswith(("hit", "die")))
    return out


def zombie_report(D) -> list:
    z = zombie_rows(D)
    tracks = {k: o for k, o in z.items() if not isinstance(k, tuple)}
    odd = {k: o for k, o in tracks.items() if o["hitdie"] == 0 or (o["span"] is not None and o["span"] < 4)}
    L = [f"  Zombie Mushroom sightings named alone by a reader meter: {sum(len(o['frames']) for o in z.values())} "
         f"meter-frames on {len(tracks)} tracks (+ {len(z) - len(tracks)} frames whose sighting has no track); "
         f"taught {sum(o['taught'] for o in tracks.values())}"]
    L.append(f"    tracks with no hit / die pose or a map-x span under 4 px (a scenery ghost?): {len(odd)}")
    for k, o in sorted(odd.items()):
        L.append(f"      track {k}: {len(o['frames'])} meter-frames {o['frames'][0]}..{o['frames'][-1]}, poses "
                 f"{dict(o['poses'])}, span {o['span']}")
    return L


def tracker_report(D) -> str:
    st = {k: v for k, v in D.R.stats.items() if k.startswith("meter: ")}
    return "  the tracker: " + ", ".join(f"{k[7:]} {v}" for k, v in sorted(st.items()))


def reader_report(D) -> str:
    ms = [g for v in D.R.meters.values() for g in v]
    return (f"  the reader: {len(ms)} meters on {len(D.R.meters)} frames; fill read {sum(g[2] is not None for g in ms)}"
            f" ({100 * sum(g[2] is not None for g in ms) / max(1, len(ms)):.1f} %); candidates one "
            f"{sum(len(g[4]) == 1 for g in ms)}, two+ {sum(len(g[4]) > 1 for g in ms)}, none "
            f"{sum(not g[4] for g in ms)}; whole (48 columns) {sum(g[3] >= 48 for g in ms)}")


def cmd_report(cap, attack, buffs, tag):
    D = Data(cap, attack, tag)
    print(f"{cap} ({load.name_of(cap)}): attack {attack}, buffs {buffs}, tracker rows {tag}")
    print(f"  key-downs: {dict(Counter(k for _, k in key_downs(cap, attack + buffs)))}; frames {len(D.c.ns)}")
    print(place_rule(D))
    print(reader_report(D))
    print(tracker_report(D))
    rows = new_rows(D)
    (out_dir() / f"new_{cap}.pkl").write_bytes(pickle.dumps(rows))
    print("\n".join(delay_report(rows)))
    print("\n".join(buff_report(D, buffs)))
    print("\n".join(zombie_report(D)))


# ------------------------------------------------------------------ sheets (judged by eye)
def meter_tile(D, n, m, title_extra=""):
    """A scan meter on frame n: the crop around it, its box (yellow), the reader's verdict in the title, the track it
    taught (cyan +, its id) and the other seen mobs (white +)."""
    img = PM.read_frame(D.cap, n)
    x0, y0, x1, y1 = PM.box_of(m)
    got = next((g for g in D.R.meters.get(n, []) if same_box(m, g)), None)
    if got is None:
        verdict = "reader: NOT FOUND"
        tt = None
    else:
        tt = D.R.taught(n, got)
        verdict = (f"reader fill {'-' if got[2] is None else f'{got[2]:.2f}'} cand {list(got[4])} -> "
                   + (f"taught track {tt['id']}" if tt is not None else "taught none"))
    marks = []
    for tr in D.c.seen(n):
        col = (255, 255, 0) if tt is not None and tr["id"] == tt["id"] else (255, 255, 255)
        marks.append((tr["sx"], tr["sy"], str(tr["id"]), col))
    cx = min(max((x0 + x1) // 2, 0), 1366)
    t = PM.tile(img, cx, y0 + 45, 220, 140, 3, marks, f"n{n} scan fill {'-' if m[10] is None else f'{m[10]:.2f}'} "
                f"cols {m[2]} | {verdict} {title_extra}")
    z = 3
    ox, oy = int(cx - 110), int(y0 + 45 - 70)
    for px, py in ((x0, y0), (x1 - 1, y0), (x0, y1 - 1), (x1 - 1, y1 - 1)):
        X, Y = int((px - ox) * z), int((py - oy) * z) + 22
        cv2.circle(t, (X, Y), 4, (0, 255, 255), 1)
    return t


def write_sheets(name, tiles, per=12, cols=3) -> list:
    out = []
    for i in range(0, len(tiles), per):
        p = out_dir() / f"{name}_{i // per}.png"
        cv2.imwrite(str(p), PM.grid(tiles[i:i + per], cols))
        out.append(p)
    return out


def cmd_sheet(cap, attack, tag, k, seed):
    D = Data(cap, attack, tag)
    every = [(n, m) for n, ms in D.c.meters.items() for m in ms if m[7] and m[2] >= 6]
    random.seed(seed)
    pick = sorted(random.sample(every, min(k, len(every))))
    for p in write_sheets(f"random_{cap}", [meter_tile(D, n, m) for n, m in pick]):
        print(p)
    cut = [(n, m) for n, m in every if PM.box_of(m)[0] < 0 or PM.box_of(m)[2] > 1366]
    runs, last = [], {}
    for n, m in sorted(cut, key=lambda a: a[0]):              # one tile per run of a cut meter (its middle frame)
        side = PM.box_of(m)[0] < 0
        if runs and runs[-1][0] == side and n - runs[-1][-1][0] <= 6:
            runs[-1].append((n, m))
        else:
            runs.append([side, (n, m)])
    tiles = []
    for r in runs:
        fr = r[1:]
        n, m = fr[len(fr) // 2]
        tiles.append(meter_tile(D, n, m, f"(cut {len(fr)} frames)"))
    print(f"cut by the screen's side: {len(cut)} meter-frames in {len(runs)} runs")
    for p in write_sheets(f"cut_{cap}", tiles):
        print(p)
    (out_dir() / f"sheet_{cap}.json").write_text(json.dumps({"random": [(n, list(map(float, m[:2]))) for n, m in pick],
                                                             "cut": [(r[0], [n for n, _ in r[1:]]) for r in runs]}),
                                                 encoding="utf-8")


def cmd_odd(cap, attack, buffs, tag):
    """Sheets of: the new meters outside try 1's window (their first frames, -10 / 0 / +10); frames with a meter
    within BUFF_S after a buff key-down; one frame per Zombie track flagged by zombie_report."""
    D = Data(cap, attack, tag)
    rows = pickle.loads((out_dir() / f"new_{cap}.pkl").read_bytes())
    tiles = []
    for r in rows:
        if any(WIN[0] <= lag <= WIN[1] for lag, _ in r["keys"]):
            continue
        for o in (-10, 0, 10):
            n = r["n0"] + o
            img = PM.read_frame(D.cap, n)
            if img is None:
                continue
            x0, y0, x1, _ = r["box"]
            marks = [(tr["sx"], tr["sy"], str(tr["id"]), (255, 255, 0)) for tr in D.c.seen(n)]
            if r["me"] is not None:
                marks.append((r["me"][0], r["me"][1], "us", (0, 0, 255)))
            cx = (x0 + x1) // 2
            tiles.append(PM.tile(img, cx, y0 + 45, 300, 160, 2, marks,
                                 f"n{n} ({o:+d}) new meter track {r['tid']} keys {r['keys'][:3]} dist {r['dist']}"))
    for p in write_sheets(f"outside_{cap}", tiles, per=12, cols=3):
        print(p)
    if buffs:
        bt = sorted(t for t, _ in key_downs(cap, buffs))
        tiles = []
        for b in bt:
            ns = [n for n in D.c.ns if 0 <= D.c.t_of[n] - b <= BUFF_S and D.c.meters.get(n)]
            for n in ns[:: max(1, len(ns) // 3)][:3]:
                for m in [m for m in D.c.meters[n] if m[7] and m[2] >= 6][:1]:
                    tiles.append(meter_tile(D, n, m, f"buff +{D.c.t_of[n] - b:.2f} s"))
            if not ns:                                          # no meter: our character under the effect
                n = next((n for n in D.c.ns if D.c.t_of[n] - b >= 0.3), None)
                me = D.me.get(n) if n is not None else None
                if n is not None and me is not None:
                    tiles.append(PM.tile(PM.read_frame(cap, n), int(me[0]), int(me[1]) - 40, 220, 140, 3, [],
                                         f"n{n} buff +0.3 s, no meter (the effect on us)"))
        for p in write_sheets(f"buffs_{cap}", tiles):
            print(p)
    z = zombie_rows(D)
    tiles = []
    for k, o in sorted((k, o) for k, o in z.items() if not isinstance(k, tuple)):
        if not (o["hitdie"] == 0 or (o["span"] is not None and o["span"] < 4)):
            continue
        n = o["frames"][len(o["frames"]) // 2]
        m = next((m for m in D.c.meters.get(n, []) if m[7]), None)
        if m is not None:
            tiles.append(meter_tile(D, n, m, f"Zombie track {k}"))
    for p in write_sheets(f"zombie_{cap}", tiles):
        print(p)


# ------------------------------------------------------------------ our own name tag (another character)
def tag_path(cap) -> Path:
    from maplebrain.config import CORPUS
    return Path(CORPUS) / "work" / cap / "self_tag_gray.npy"


def cmd_tag(cap, seed_n, box, step=15):
    """The perception finds US by a picture of our own name tag (assets/self_tag_gray.npy: the warrior's, the median
    of 488 aligned tags, 17 x 74, the glyphs from row 4 / column 6). Another character needs its own: from one seed
    crop (`box` on frame `seed_n`, cut with the same margins), matched (perception/selfpos.find_self, score >= 0.8)
    on every `step`-th frame; the per-pixel median of the aligned crops drops the scenery behind the see-through box.
    Kept beside the capture's kept replay (CORPUS/work/<cap>/self_tag_gray.npy) - not in assets/: dump.py --self-tag."""
    import frames as fr
    from maplebrain.perception.selfpos import _hp, _match, find_self
    x, y, w, h = box
    run = load.run_path(cap)
    v = fr.video(run)
    img = PM.read_frame(cap, seed_n)
    seed = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[y:y + h, x:x + w].copy()
    crops, scores = [], []
    for i in range(0, len(v), step):
        f = v.frame(i)
        if f is None:
            continue
        m = find_self(f, seed, min_score=0.8, edges=False)
        if m is None:
            continue
        mx, my = int(m[0]), int(m[1])
        if mx < 0 or my < 0 or mx + w > f.shape[1] or my + h > f.shape[0]:
            continue
        crops.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)[my:my + h, mx:mx + w])
        scores.append(m[4])
    tpl = np.median(np.stack(crops), axis=0).astype(np.uint8)
    p = tag_path(cap)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.save(p, tpl)
    print(f"{cap}: the seed matched on {len(crops)} of {len(range(0, len(v), step))} frames (score p5/50 "
          f"{PM.pct(scores, (5, 50), 2)}) -> the median of the crops {tpl.shape} -> {p}")
    best, second = [], []                       # the median picture: our tag's score, the best other place's
    for i in range(7, len(v), step * 4):
        f = v.frame(i)
        if f is None:
            continue
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        from maplebrain.perception.hud import ui_mask
        g[ui_mask(f.shape, None) == 0] = 0
        r = _match(_hp(g), _hp(tpl.astype(np.float32)))
        _, s, _, loc = cv2.minMaxLoc(r)
        best.append(s)
        r[max(0, loc[1] - 12):loc[1] + 12, max(0, loc[0] - 40):loc[0] + 40] = -1
        second.append(cv2.minMaxLoc(r)[1])
    print(f"  the median picture over {len(best)} frames: best score p5/50 {PM.pct(best, (5, 50), 2)}, found (>= 0.66) "
          f"{sum(s >= 0.66 for s in best)}; the best OTHER place p50/95/max {PM.pct(second, (50, 95, 100), 2)}")
    big = cv2.resize(np.vstack([np.load(ROOT_ASSETS / "self_tag_gray.npy")[:, :w], tpl]), None, fx=8, fy=8,
                     interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(str(out_dir() / f"self_tag_{cap}.png"), big)


ROOT_ASSETS = HERE.parents[2] / "assets"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("report", "sheet", "odd", "tag"))
    ap.add_argument("cap")
    ap.add_argument("--attack", default="", help="the class's attack keys, comma-separated (e.g. space; q,w,e)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seed-frame", type=int, default=0, help="tag: the frame of the seed crop")
    ap.add_argument("--seed-box", default="", help="tag: x,y,w,h of our tag on that frame (17 high, glyphs from "
                                                   "row 4 / column 6 as the warrior's picture)")
    ap.add_argument("--buffs", default="", help="the buff keys, comma-separated (e.g. 1,2)")
    ap.add_argument("--tag", default="t5a2")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    attack = [k for k in a.attack.split(",") if k]
    buffs = [k for k in a.buffs.split(",") if k]
    if a.cmd == "tag":
        cmd_tag(a.cap, a.seed_frame, tuple(int(v) for v in a.seed_box.split(",")))
    elif a.cmd == "report":
        cmd_report(a.cap, attack, buffs, a.tag)
    elif a.cmd == "sheet":
        cmd_sheet(a.cap, attack, a.tag, a.n, a.seed)
    else:
        cmd_odd(a.cap, attack, buffs, a.tag)


if __name__ == "__main__":
    main()
