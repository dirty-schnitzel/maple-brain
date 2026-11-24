"""Tracker plan, Part 2, experiment: THE EVENTS of the state model (docs/state_model.md section 4) as measured
rules - `cast`, `mob_hit`, `mob_died` (by us / another / unknown) and the HUD's `hp` / `mp` / `exp` steps with
their causes. A prototype: nothing here is built into maplebrain/.

    python tools/perc/track/proto_events.py [CAP] [--refresh] [--only 1,2,...]

CAP = a capture of the kept replay (default: the 30-minute Line 1 capture, cache.DESIGN). Inputs, no GPU:
  - the kept replay (dump.py), read one chunk file at a time and kept slim: per frame the clock, the camera, our
    feet on the map, the HUD's HP / MP / EXP, the name tags (cached in CORPUS/work/track-plan/events/);
  - our keys (keys.jsonl, the same clock);
  - the truth chains (cache.py: one chain = one mob's life) as the stand-in for the tracker's mob tracks;
  - static game data: assets/mcw (mob.json, attacks.json through brain/reach.py) and the raw skill export.
It prints one block per question (0 the HUD's steps, 1 cast, 2 mob_hit, 3 mob_died against EXP, 4 hits per kill,
5 knockback, 6 hp losses, 7 what breaks the rules); `--only 1,3` prints those.

THE PROPOSED RULES are the plain functions `hud_steps`, `casts`, `landing_window`, `in_reach`, `hit_by`,
`died_by`, `hurt_by`, `step_causes`; their numbers are the constants below, each measured by this file on the
capture (the block that measures it is named beside it). What they rest on, all measured here:
  - The HUD's MP / HP are the CLIENT's numbers: a cast takes its cost off by itself (seen 0.03-0.28 s after the
    key-down, flat), the server's own values come ~0.5 s after what caused them (a kill's EXP, a potion, a hurt).
    A server value that lands between a cast and the server's knowing of it shows the cost BACK (+12 +3 = "+15")
    and the server's own subtraction follows ("-12" again): one cast, three steps.
  - A swing starts at the key-down when no swing is running: what a mob shows is locked to the key-down (0.50 s
    for a stab, 0.56 s for a swing), not to the MP step.
  - A mob that dies shows the die pose at the later of our hit's landing and the server's word (the EXP step);
    when the word is late it stands in the hit pose first (0-0.2 s).
"""
import json
import pickle
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
import cache  # noqa: E402
import dump  # noqa: E402
import load  # noqa: E402
from oracle import FACE, I, POSE, SEEN, T, X, Y  # noqa: E402

SKILL_XML = Path(r"C:\Users\Yoav\dev\cw-data\export\Skill")

# ------------------------------------------------------------------ the profile (state_model.md section 6)
# What the user's keys do today (the data model's profile file; `maplebrain/config.py` Keys knows q, c, z, end,
# delete, shift). A skill's level is the one whose cost the HUD's step shows (block 1).
PROFILE = {
    "q": {"skill": 1001001, "name": "Power Strike", "level": 20},
    "w": {"skill": 1001002, "name": "Slash Blast", "level": 19},
    "e": {"skill": 1301005, "name": "Rush", "level": 1},
}
POTIONS = {"end": ("mp", 150), "delete": ("hp", 198)}      # measured (block 0); Item.wz `spec` is not exported
RECOVERY = {"hp": 10, "mp": 3}      # the recovery tick's size, one every ~10 s (measured; game_rules.md I: NOT FOUND)
WEAPON = "poleArm"                  # config.Combat.weapon (attacks.json: the same boxes as a spear)

# ------------------------------------------------------------------ the rules' numbers (measured here)
MP_SHOWN = (0.0, 0.30)              # key-down -> the client's own MP step: 0.03 .. 0.28 s, flat (block 1)
SERVER_BY = 0.75                    # what caused it -> the server's value on the HUD, at the latest (blocks 0, 1)
POTION_LAG = (0.20, 0.75)           # potion key-down -> its step (block 0)
LAND = {"q": (0.45, 0.72), "w": (0.45, 0.95), "e": (0.03, 0.90)}   # key-down -> a hit / die pose begins (block 2)
EXP_DIE = (-0.33, 0.07)             # EXP step - the die pose began (block 3)
BUSY = {"q": 0.84, "w": 0.84, "e": 0.43}    # a key-down this soon after a cast's is inside its swing: ignored
SWING = {"q": (0.844, 0.900), "w": (0.844, 0.900), "e": (0.450, 0.450)}   # the swing's length: a stab, a swing
#   = attacks.json stance_ms 750 / 800 x (10 + attackSpeed 8) / 16 (brain/reach.py); block 1 measures 0.85 / 0.92
DIE_CUM = (0.0, 0.150, 0.333, 0.516)        # a Bubbling's die1 frames begin this long after the pose began (seen)
SAME_BLOW = 0.25                    # a hit pose that turns into the die pose within this = the killing blow itself
DIE_MIN = 5                         # die-pose sightings in a row that make a death in the middle of a truth chain
TOUCH = 0.75                        # a hurt: the mob's body was over ours within this before the HP step (block 6)
SAFE_S = 2.3                        # after a hurt no mob hurts us for 2 s (game_rules.md B3) + the server's lag
MOB_TAG = (87, 20)                  # a Bubbling's own name tag (w, h), shown under it after a hit of OURS (block 2)
NEAR = (250.0, 70.0)                # "near us" for counting what is in no window of ours: |dx|, |dy| px


@dataclass
class Skill:
    key: str
    id: int
    name: str
    mp: int
    hp: int = 0
    mobs: int = 1
    range: int = 100                # percent of the box's far edge
    box: tuple | None = None        # its own (ltx, lty, rbx, rby) facing left, or None: the weapon's stances
    cooltime: float = 0.0


def skills() -> dict:
    """key -> Skill, the numbers from the client's Skill.img export at the profile's level (game_rules.md F6)."""
    import xml.etree.ElementTree as ET
    out = {}
    for key, p in PROFILE.items():
        f = SKILL_XML / f"{p['skill'] // 10000}.img.xml"
        sk = next(e for e in ET.parse(f).getroot().iter("imgdir") if e.get("name") == str(p["skill"]))
        lv = {}
        for part in ("common", "level"):
            node = next((c for c in sk if c.get("name") == part), None)
            if node is None:
                continue
            src = node if part == "common" else next(c for c in node if c.get("name") == str(p["level"]))
            for x in src:
                lv[x.get("name")] = x.get("value") if x.get("value") is not None else (int(x.get("x")), int(x.get("y")))
        box = (*lv["lt"], *lv["rb"]) if "lt" in lv else None
        out[key] = Skill(key, p["skill"], p["name"], int(lv.get("mpCon", 0)), int(lv.get("hpCon", 0)),
                         int(lv.get("mobCount", 1)), int(lv.get("range", 100)), box, float(lv.get("cooltime", 0)))
    return out


# ------------------------------------------------------------------ loading
def events_dir() -> Path:
    from maplebrain.config import CORPUS
    d = Path(CORPUS) / "work" / "track-plan" / "events"
    d.mkdir(parents=True, exist_ok=True)
    return d


def frames(cap, refresh: bool = False) -> dict:
    """The kept replay's rows, slim: arrays n, t, cx, cy (camera), mx, my (our feet on the map; nan = tag not
    found), hp, mp, exp, and per frame the name tags' screen boxes + our own. One chunk file in memory at a time."""
    p = events_dir() / f"slim_{cap.replace('#', '_')}.pkl"
    if p.exists() and not refresh:
        return pickle.loads(p.read_bytes())
    d, m = dump.out_dir(cap), dump.meta(cap)
    cols = {k: [] for k in ("n", "t", "cx", "cy", "mx", "my", "hp", "hpmax", "mp", "mpmax", "exp")}
    tags, tag = [], []
    for k in range(m["chunks"]):
        for r in pickle.loads((d / f"rows_{k:03d}.pkl").read_bytes()):
            f = r["facts"]
            C, me, hp, mp, e = r["C"], r["me_map"], f.get("hp"), f.get("mp"), f.get("exp_points")
            for name, v in (("n", r["n"]), ("t", r["t"]), ("cx", C[0] if C else np.nan), ("cy", C[1] if C else np.nan),
                            ("mx", me[0] if me else np.nan), ("my", me[1] if me else np.nan),
                            ("hp", hp[0] if hp else -1), ("hpmax", hp[1] if hp else -1),
                            ("mp", mp[0] if mp else -1), ("mpmax", mp[1] if mp else -1), ("exp", -1 if e is None else e)):
                cols[name].append(v)
            tags.append([tuple(int(v) for v in b[:4]) for b in (f.get("tags") or [])])
            tg = f.get("tag")
            tag.append(tuple(int(v) for v in tg[:4]) if tg else None)
    out = {k: np.array(v) for k, v in cols.items()}
    out["tags"], out["tag"], out["map"] = tags, tag, m["map"]
    p.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    return out


def anim_of(pose: str) -> str:
    return pose.rsplit("_", 1)[0]


@dataclass
class Life:
    """One mob's life (a truth chain): its sightings as arrays."""
    id: int
    kind: int
    i: np.ndarray                   # frame index of each sighting
    t: np.ndarray
    x: np.ndarray                   # feet, map px
    y: np.ndarray
    anim: list                      # 'move' / 'stand' / 'jump' / 'hit1' / 'die1'
    frame: np.ndarray               # the pose's frame number
    face: np.ndarray                # -1 left / +1 right
    seen: np.ndarray                # the share of its pixels the fit saw
    start: str
    end: str
    false_die: int = 0              # die-pose sightings that a living pose followed
    evs: list = field(default_factory=list)

    def at(self, i: int, slack: int = 15):
        """(x, y) at frame i: the sighting on it, else between its neighbours when both are within `slack` frames
        (a mob covered for a moment), else the nearest one within 3 frames, else None."""
        k = int(np.searchsorted(self.i, i))
        n = len(self.i)
        if k < n and self.i[k] == i:
            return float(self.x[k]), float(self.y[k])
        if 0 < k < n and i - self.i[k - 1] <= slack and self.i[k] - i <= slack:
            a = (i - self.i[k - 1]) / (self.i[k] - self.i[k - 1])
            return float(self.x[k - 1] + a * (self.x[k] - self.x[k - 1])), float(self.y[k - 1] + a * (self.y[k] - self.y[k - 1]))
        if k < n and self.i[k] - i <= 3:
            return float(self.x[k]), float(self.y[k])
        if k > 0 and i - self.i[k - 1] <= 3:
            return float(self.x[k - 1]), float(self.y[k - 1])
        return None

    def k_at(self, i: int) -> int:
        """The index of the sighting nearest frame i."""
        k = min(int(np.searchsorted(self.i, i)), len(self.i) - 1)
        return k - 1 if k > 0 and i - self.i[k - 1] < self.i[k] - i else k


@dataclass
class Ev:
    """A mob's hit pose or die pose beginning."""
    kind: str                       # 'hit' / 'die'
    life: Life
    t: float                        # when the pose began (the best estimate) ...
    t_lo: float                     # ... and not before this (== t: it was seen to begin)
    i: int                          # frame index of its first sighting
    k: int                          # that sighting's index in the life
    x: float
    y: float
    how: str = "seen"               # seen / counted back (die: from the first die frame change seen) / first sighting
    dur: float = 0.0                # how long the pose was seen
    n: int = 0                      # ... on how many frames
    blow: bool = True               # False = a hit pose that is the killing blow's own first frames (SAME_BLOW)
    after_hit: bool = False         # (die) the die pose came out of a hit pose
    who: str = ""                   # the rule's verdict: us / unknown / another
    cast: object = None
    exp: int = 0                    # (die) the EXP step it can have paid (`match_exp`), 0 = none
    exp_t: float | None = None
    exp_sure: bool = False          # ... and no other death can have paid that step
    exp_raw: tuple | None = None    # (step, deaths the step needs, candidate deaths): the time-only cross-check

    @property
    def exact(self) -> bool:
        return self.t - self.t_lo < 0.03


def lives(cap) -> list:
    """The capture's mob lives with their events read off the pose stream (`Life.evs`, in time order).
    A truth chain is one life, except: a die run of DIE_MIN sightings or more in the MIDDLE of a chain ends a life
    there (the chain went on with another mob standing on the same spot); a shorter one is pose noise (one or two
    frames of `die1_2` between walking frames) and counts as a living pose.
    hit = every run of the hit pose before the death: t = its first sighting, t_lo = the sighting before it (the
          frame before: seen to begin);
    die = the die run the life ends in: t = when the die pose began - its first sighting when the mob was seen
          on the frame before in a living pose, else counted back from the first die frame change seen (DIE_CUM),
          else the first sighting with t_lo = the last living sighting."""
    out = []
    for c in cache.chains(cap):
        pts = [q for p in c["parts"] for q in p["pts"]]
        an = [anim_of(q[POSE]) for q in pts]
        n, cuts, noise, k = len(pts), [], 0, 0
        while k < n:
            if an[k] != "die1":
                k += 1
                continue
            j = k
            while j + 1 < n and an[j + 1] == "die1":
                j += 1
            if j + 1 < n:                                # a die run in the middle of the chain
                if j - k + 1 >= DIE_MIN:
                    cuts.append(j + 1)
                else:
                    noise += j - k + 1
                    for m in range(k, j + 1):
                        an[m] = an[k - 1] if k and an[k - 1] != "hit1" else "move"
            k = j + 1
        for a, b in zip([0] + cuts, cuts + [n]):
            seg = pts[a:b]
            L = Life(len(out), c["type"], np.array([q[I] for q in seg]), np.array([q[T] for q in seg]),
                     np.array([q[X] for q in seg], float), np.array([q[Y] for q in seg], float), an[a:b],
                     np.array([int(q[POSE].rsplit("_", 1)[1]) for q in seg]),
                     np.array([1 if q[FACE] == "right" else -1 for q in seg]), np.array([q[SEEN] for q in seg], float),
                     c["start"] if a == 0 else "split", c["end"] if b == n else "died")
            L.false_die, noise = noise, 0
            _events(L)
            out.append(L)
    return out


def _events(L: Life) -> None:
    an, n = L.anim, len(L.i)
    k0 = None                                            # the death: the die run at the life's end
    if an[-1] == "die1":
        k0 = n - 1
        while k0 > 0 and an[k0 - 1] == "die1":
            k0 -= 1
    die = None
    if k0 is not None:
        t_lo = float(L.t[k0 - 1]) if k0 else float(L.t[k0]) - 1.0
        t0, how = float(L.t[k0]), "first sighting"
        if k0 > 0 and L.i[k0 - 1] == L.i[k0] - 1 and L.frame[k0] == 0:
            how, t_lo = "seen", t0
        else:
            for k in range(k0 + 1, n):
                if L.i[k] == L.i[k - 1] + 1 and L.frame[k] == L.frame[k - 1] + 1:
                    t0 = max(t_lo, float(L.t[k] - DIE_CUM[L.frame[k]]))
                    how, t_lo = "counted back", t0
                    break
        die = Ev("die", L, t0, t_lo, int(L.i[k0]), k0, float(L.x[k0]), float(L.y[k0]), how,
                 dur=float(L.t[-1] - L.t[k0]), after_hit=k0 > 0 and an[k0 - 1] == "hit1", n=n - k0)
    k, stop = 0, n if k0 is None else k0
    while k < stop:
        if an[k] != "hit1":
            k += 1
            continue
        j = k
        while j + 1 < stop and an[j + 1] == "hit1":
            j += 1
        seen_begin = k > 0 and L.i[k - 1] == L.i[k] - 1
        e = Ev("hit", L, float(L.t[k]), float(L.t[k]) if seen_begin else (float(L.t[k - 1]) if k else float(L.t[k]) - 1.0),
               int(L.i[k]), k, float(L.x[k]), float(L.y[k]), "seen" if seen_begin else "first sighting",
               dur=float(L.t[j] - L.t[k]), n=j - k + 1)
        if die is not None and j + 1 == k0 and die.t - e.t <= SAME_BLOW:
            e.blow = False
        L.evs.append(e)
        k = j + 1
    if die is not None:
        L.evs.append(die)


# ------------------------------------------------------------------ rule: the HUD's steps
def hud_steps(fr: dict) -> list:
    """Every change of a HUD number between two frames: [(frame index, t, stat, delta)] in time order."""
    out = []
    for stat in ("hp", "mp", "exp"):
        v = fr[stat]
        for i in np.nonzero(np.diff(v) != 0)[0] + 1:
            if v[i] >= 0 and v[i - 1] >= 0:
                out.append((int(i), float(fr["t"][i]), stat, int(v[i] - v[i - 1])))
    out.sort()
    return out


# ------------------------------------------------------------------ rule: cast
@dataclass
class Cast:
    key: str
    t: float                        # when the swing began: the key-down that started it
    how: str                        # key (its own key-down, the client's step seen) / held (the key still down
                                    # at the last swing's end) / server (only the server's step was seen)
    t_mp: float                     # the MP step that confirmed it
    i: int = 0                      # frame index at t
    me: tuple | None = None         # our feet at t
    facing: int = 0                 # the belief at t: -1 / +1 / 0
    shown_back: float | None = None  # a server value showed the cost back at this time ...
    again: float | None = None      # ... and the server's own subtraction followed at this time
    t_hi: float = 0.0               # the latest key-down that may have started it instead (= t when there is none)
    evs: list = field(default_factory=list)        # filled by `attribute`: what it hit


def casts(keys: list, steps: list, sk: dict, mp_at=None, place_at=None) -> tuple:
    """Our casts from our keys + the HUD's steps. -> (casts, causes, presses): causes = {index in `steps`: why}
    for the MP steps this rule explains; presses = [(t, key, what)] for every key-down of a skill key, what =
    cast / in swing (inside the BUSY time of the cast before: the game ignores it) / no mp (the HUD's MP under
    the cost) / rope (we hang on one: no attack there, game_rules.md F1) / cooldown / none (nothing followed).
    `mp_at(t)` = the HUD's MP at t, `place_at(t)` = 'stand' / 'air' / 'rope' (both optional).

    Walked in time order. A key-down that is none of the above is a MAYBE. A step of exactly -cost(key)
    (or -cost + a recovery tick / a potion's rise, shown in one repaint: "-9"):
      1. the last cast's cost was shown back by a server value and not subtracted again yet -> the server's
         subtraction of that SAME cast;
      2. else the first MAYBE of that key within MP_SHOWN before the step started the swing - or, further back
         (up to SERVER_BY), the first MAYBE that has a server value shown between it and the step (the client's
         own step was painted over; this one is the server's). `t_hi` = the last MAYBE that fits as well when
         the first came within the longest swing of the cast before (a stab is over at 0.844 s, a swing at 0.900:
         it may have been ignored);
      3. else, the key still down since the last cast of it and that swing just over: the next swing of a HELD key.
    A rise of cost + (0, a recovery tick or a potion) within SERVER_BY of a cast = the server's value showing the
    cost back."""
    rises = {0} | {v for st, v in RECOVERY.items() if st == "mp"} | {v for st, v in POTIONS.values() if st == "mp"}
    combos = {r - s.mp: (k, r) for k, s in sk.items() for r in sorted(rises, reverse=True)}     # the step -> (key, extra)
    ev = [(k["t"], 0 if k["down"] else 1, "down" if k["down"] else "up", k["key"]) for k in keys if k["key"] in sk]
    ev += [(t, 2, "step", n) for n, (i, t, stat, d) in enumerate(steps)]
    ev.sort()
    out, causes, pr = [], {}, []
    down = {k: None for k in sk}
    maybe = []                       # [t, key, index in pr, weak]
    marks = []                       # times a server value was shown (any step that is no cast's own)
    last, busy, soft = None, -1e9, -1e9
    last_of = {}                     # key -> its last cast

    def confirm(m, key, how, ts, t=None):
        nonlocal last, busy, soft, maybe
        c = Cast(key, m[0] if m else t, how, ts)
        c.t_hi = c.t
        if m and m[3]:                                   # a weak first: the last maybe that fits as well
            c.t_hi = max([x[0] for x in maybe if x[1] == key and c.t <= x[0] <= ts - 0.02] or [c.t])
        out.append(c)
        last, busy, soft = c, c.t + BUSY[key], c.t + SWING[key][1] + 0.02
        last_of[key] = c
        keep = []
        for x in maybe:
            if m is not None and x[2] == m[2]:
                pr[x[2]][2] = "cast"
            elif x[0] < c.t:
                pr[x[2]][2] = "none"
            elif x[0] < busy or x[0] <= ts:
                pr[x[2]][2] = "in swing"
            else:
                x[3] = x[0] < soft
                keep.append(x)
        maybe = keep
        return c

    for t, _, kind, x in ev:
        if kind == "up":
            down[x] = None
            continue
        if kind == "down":
            down[x] = t
            lk = last_of.get(x)
            if t < busy:
                what = "in swing"
            elif mp_at is not None and max(mp_at(t - 0.02), mp_at(t + 0.05)) < sk[x].mp:
                what = "no mp"
            elif place_at is not None and place_at(t) == "rope":
                what = "rope"
            elif lk is not None and sk[x].cooltime and t - lk.t < sk[x].cooltime - 0.06:
                what = "cooldown"
            else:
                what = "none"
            pr.append([t, x, what])
            if what == "none":
                maybe.append([t, x, len(pr) - 1, t < soft])
            continue
        i, ts, stat, d = steps[x]
        maybe = [m for m in maybe if ts - m[0] <= SERVER_BY]
        combo = combos.get(d) if stat == "mp" else None
        if combo is not None and combo[1] and not any(m[1] == combo[0] and m[0] >= ts - MP_SHOWN[1] for m in maybe):
            combo = None                                 # (cost + a server's rise in one repaint needs a fresh MAYBE)
        if combo is None:
            if stat == "mp" and d > 0 and last is not None and last.shown_back is None and ts - last.t <= SERVER_BY \
                    and (d - sk[last.key].mp) in rises:
                last.shown_back = ts
                causes[x] = f"cast {last.key} shown back by a server value" + (f" (+{d - sk[last.key].mp})" if d > sk[last.key].mp else "")
            if not (stat == "hp" and d < 0 and last is not None and -d == sk[last.key].hp and ts == last.t_mp):
                marks.append(ts)                         # (a cast's own HP cost is the client's, not a server value)
            continue
        key, extra = combo
        if extra:
            marks.append(ts)
        if not extra and last is not None and last.key == key and last.shown_back is not None and last.again is None \
                and ts - last.t <= SERVER_BY + 0.15:
            last.again = ts
            causes[x] = f"cast {key} subtracted again by the server"
            marks.append(ts)
            continue
        new = [m for m in maybe if m[1] == key and m[0] >= ts - MP_SHOWN[1]]
        old = [m for m in maybe if m[1] == key and m[0] < ts - MP_SHOWN[1] and any(m[0] < s < ts for s in marks[-12:])]
        if old or new:
            confirm((old or new)[0], key, "server" if old else "key", ts)
            causes[x] = f"cast {key}" + (" (the server's step: the client's was painted over)" if old else "") +                 (f" {extra:+d} of the server's in the same repaint" if extra else "")
        elif last is not None and last.key == key and down[key] is not None and down[key] <= busy \
                and last.t + SWING[key][0] - 0.03 <= ts <= last.t + SWING[key][1] + MP_SHOWN[1]:
            confirm(None, key, "held", ts, last.t + sum(SWING[key]) / 2)
            causes[x] = f"cast {key} (held key)"
        else:
            marks.append(ts)
    return out, causes, [tuple(q) for q in pr]


def facing_at(keys: list) -> tuple:
    """Our facing as a belief from the walk keys: (times, facing after each) = the side of the last left / right
    key-down (block 2 checks it against the side the reacting mob is on)."""
    ts, fs = [], []
    for k in keys:
        if k["down"] and k["key"] in ("left", "right"):
            ts.append(k["t"])
            fs.append(-1 if k["key"] == "left" else 1)
    return np.array(ts), np.array(fs)


# ------------------------------------------------------------------ rule: the landing window, reach
def landing_window(c: Cast) -> tuple:
    """The seconds in which what this cast hit shows its hit pose or its die pose: LAND after the key-down (to
    the last key-down that may have started it)."""
    lo, hi = LAND[c.key]
    return c.t + lo, c.t_hi + hi


class Reaches:
    """Each skill's reach against a mob kind, front-positive px from our feet (brain/reach.py's boxes: the
    weapon's stances; a skill's `range` percent stretches the far edge, a skill's own box replaces the stances)."""

    def __init__(self, sk: dict):
        from maplebrain.brain.reach import Reach, body, boxes_vs
        self.sk, self.r, self.body, self.boxes_vs, self.cache = sk, Reach(WEAPON), body, boxes_vs, {}

    def box(self, key: str, kind: int):
        if (key, kind) not in self.cache:
            mob = json.loads((self.r.root / "mobs" / str(kind) / "mob.json").read_text(encoding="utf-8"))
            s = self.sk[key]
            st = [s.box] if s.box else self.r.stances
            st = [(ltx * s.range / 100, lty, rbx, rby) for ltx, lty, rbx, rby in st]
            self.cache[(key, kind)] = self.boxes_vs(st, self.body(mob))[1]       # "maybe": any stance reaches
        return self.cache[(key, kind)]


def in_reach(rc: Reaches, c: Cast, life: Life, pad: float = 25.0) -> str | None:
    """Was this mob in the cast's reach at the key-down (v83: the targets are chosen at the press, F2)? ->
    'front' (on the side we believe we face, or facing unknown), 'back' (in the box mirrored: the belief may be
    wrong), '?' (our place or the mob's not known then), None. `pad` px on every side: the mob walks on until
    the hit lands and Rush carries us forward."""
    if c.me is None:
        return "?"
    p = life.at(c.i)
    if p is None:
        return "?"
    b = rc.box(c.key, life.kind)
    dx, dy = p[0] - c.me[0], p[1] - c.me[1]
    if not b.ylo - pad <= dy <= b.yhi + pad:
        return None
    if c.facing == 0:
        return "front" if b.lo - pad <= abs(dx) <= b.hi + pad else None
    if b.lo - pad <= dx * c.facing <= b.hi + pad:
        return "front"
    return "back" if b.lo - pad <= -dx * c.facing <= b.hi + pad else None


# ------------------------------------------------------------------ rules: whose hit, whose kill, who hurt us
def hit_by(e: Ev, cs: list, ct: np.ndarray, rc: Reaches) -> tuple:
    """Whose blow a hit pose / die pose is: ('us', cast) when it began inside the landing window of a cast of
    ours with the mob in that skill's reach in front of us; ('unknown', cast) when the time fits a cast but the
    mob was in reach only behind us or a place was not known; else ('another', None)."""
    maybe = None
    for j in range(int(np.searchsorted(ct, e.t_lo - 1.5)), len(cs)):
        c = cs[j]
        if c.t > e.t:
            break
        a, b = landing_window(c)
        if e.t_lo <= b and e.t >= a:
            r = in_reach(rc, c, e.life)
            if r == "front":
                return "us", c
            if r in ("back", "?"):
                maybe = c
    return ("unknown", maybe) if maybe is not None else ("another", None)


def died_by(e: Ev, full: int) -> str:
    """The proposed rule for `mob_died`, from the window verdict (`e.who`) and the EXP step the death can have
    paid (`e.exp`, set by `match_exp`; `full` = the mob kind's EXP):
      us      = the die pose began in a landing window of ours with the mob in reach AND an EXP step came with it
                (any size: a kill of ours always pays); or, outside every window, an EXP step of the mob's WHOLE
                EXP that no other death can have paid (we did all its damage, so the last hit was ours: the death
                was not seen well enough for the window - covered, at the screen's edge, a cast not recognised);
      unknown = the window's 'unknown' with an EXP step; outside every window an EXP step of a part of it (we
                damaged it, who finished it is not known) or one that several deaths can have paid;
      another = no EXP step - also inside a window of ours: another player's blow fell first."""
    if not full:                                         # a mob kind that pays no EXP: the window alone
        return e.who
    if not e.exp:
        return "another"
    if e.who == "us" or (e.exp_sure and e.exp % full == 0):
        return "us"
    return "unknown"


def attribute(lv: list, cs: list, rc: Reaches) -> list:
    """Every mob event with the window rule's verdict; each cast gets the events it claimed. -> events by time."""
    ct = np.array([c.t for c in cs])
    evs = sorted((e for L in lv for e in L.evs), key=lambda e: e.t)
    for e in evs:
        e.who, e.cast = hit_by(e, cs, ct, rc)
        if e.who == "us":
            e.cast.evs.append(e)
    return evs


def match_exp(evs: list, steps: list, full: int) -> list:
    """Each EXP step and the deaths that can have paid it: those whose die pose began EXP_DIE around the step
    (time only). The step needs ceil(step / full) deaths; with no more candidates than that it is theirs for sure.
    Per death: `exp_raw` = (step, needed, candidates) of its nearest step - the cross-check, untouched by the
    window rule; `exp`, `exp_sure` = what it keeps once the window verdicts settle a step several deaths share
    (the candidates in a window of ours take it; when they are too few every candidate keeps it, unsure).
    -> [(step, [candidate deaths], needed)]."""
    deaths = [e for e in evs if e.kind == "die"]
    dt = np.array([e.t for e in deaths])
    out, best = [], {}
    for st in steps:
        if st[2] != "exp" or st[3] <= 0:
            continue
        te, need = st[1], -(-st[3] // full)
        a, b = int(np.searchsorted(dt, te - EXP_DIE[1] - 1.5)), int(np.searchsorted(dt, te - EXP_DIE[0] + 1.5))
        cand = [deaths[k] for k in range(a, b) if deaths[k].t >= te - EXP_DIE[1] and deaths[k].t_lo <= te - EXP_DIE[0]]
        out.append((st, cand, need))
        for e in cand:
            lag = abs(te - e.t + 0.05)
            if id(e) not in best or lag < best[id(e)][0]:
                best[id(e)] = (lag, te)
                e.exp_raw = (st[3], need, len(cand))
    for st, cand, need in out:
        ours = [e for e in cand if e.who == "us"]
        for e in cand:
            if best[id(e)][1] != st[1]:
                continue
            sure = len(cand) <= need
            if sure or e.who == "us" or len(ours) < need:
                e.exp, e.exp_t, e.exp_sure = st[3], st[1], sure
    return out


class Touch:
    """Per frame: the mobs whose body box (mob.json frame lt / rb at its feet, mirrored when it faces right) is
    over our box (our feet x, from 50 px above our feet to our feet: game_rules.md B1), +- `tol` px."""

    def __init__(self, fr: dict, lv: list, mob: dict, tol: float = 4.0):
        n = len(fr["t"])
        self.ids = [None] * n                            # None: our place not known on that frame
        by = {}
        for L in lv:
            for i in range(int(L.i[0]), int(L.i[-1]) + 1):
                by.setdefault(i, []).append(L)
        fb = mob["frames"]
        mx, my = fr["mx"], fr["my"]
        for i in range(n):
            x, y = mx[i], my[i]
            if np.isnan(x):
                continue
            hit = []
            for L in by.get(i, ()):
                k = int(np.searchsorted(L.i, i))
                if L.i[k] != i:
                    if k == 0 or L.i[k] - L.i[k - 1] > 30:
                        continue
                    a = (i - L.i[k - 1]) / (L.i[k] - L.i[k - 1])
                    px, py = L.x[k - 1] + a * (L.x[k] - L.x[k - 1]), L.y[k - 1] + a * (L.y[k] - L.y[k - 1])
                    k = k - 1 if a < 0.5 else k
                else:
                    px, py = L.x[k], L.y[k]
                if abs(px - x) > 60 or abs(py - y) > 130:
                    continue
                fs = fb.get(L.anim[k]) or []
                f = fs[int(L.frame[k])] if int(L.frame[k]) < len(fs) else None
                if not f or not f.get("lt"):
                    continue                             # a dying mob has no body box: it does not touch
                lt, rb = f["lt"], f["rb"]
                x0, x1 = (lt[0], rb[0]) if L.face[k] < 0 else (-rb[0], -lt[0])
                if px + x0 - tol <= x <= px + x1 + tol and py + lt[1] - tol <= y and py + rb[1] + tol >= y - 50:
                    hit.append(L.id)
            self.ids[i] = hit
        self.has = np.array([bool(v) for v in self.ids])
        ep, i = [], 0                                    # touch episodes: (first frame, last frame, {life ids})
        while i < n:
            if not self.has[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and (self.has[j + 1] or self.has[j + 1:j + 5].any()):
                j += 1
            ep.append((i, j, {v for k in range(i, j + 1) for v in (self.ids[k] or ())}))
            i = j + 1
        self.episodes = ep
        self.ep_t0 = np.array([fr["t"][a] for a, _, _ in ep])
        self.ep_t1 = np.array([fr["t"][b] for _, b, _ in ep])


def hurt_by(touch: Touch, t_step: float) -> list:
    """The mobs that can have hurt us at an HP loss shown at `t_step`: those whose body was over ours within
    TOUCH before it; the touch that began last comes first. [] = none seen."""
    ks = np.nonzero((touch.ep_t0 <= t_step) & (touch.ep_t1 >= t_step - TOUCH))[0]
    out = []
    for k in ks[::-1]:
        out += [v for v in sorted(touch.episodes[k][2]) if v not in out]
    return out


def step_causes(steps: list, cs: list, mp_causes: dict, keys: list, sk: dict, full: int) -> dict:
    """Why each HUD step happened: {index in `steps`: (cause, the real change)}. The real change differs from
    the step when a server value showed a cast's cost back (a hurt of 37 seen as -22 after Slash Blast's -15).
    Causes: cast KEY / cast KEY shown back ... / cast KEY subtracted again ... (from `casts`; the same for a
    skill's HP cost), recovery, potion KEY, hurt, kill we damaged (EXP: `full` x n, or a part of it), other."""
    out = {}
    pk = {key: np.array([k["t"] for k in keys if k["down"] and k["key"] == key]) for key in POTIONS}
    hp_cast = {round(c.t_mp, 4): c for c in cs if sk[c.key].hp}
    hp_steps = [(n, s) for n, s in enumerate(steps) if s[2] == "hp"]
    pend = None                                          # [the cast whose HP cost may be shown back, state]

    def plain(stat, t, d):
        if d == RECOVERY[stat]:
            return "recovery"
        for key, (st, amount) in POTIONS.items():
            if st == stat and d > 2 * RECOVERY[stat] and ((pk[key] >= t - POTION_LAG[1]) & (pk[key] <= t - POTION_LAG[0])).any():
                rest = d - amount
                return f"potion {key}" + ("" if rest == 0 else " + recovery" if rest == RECOVERY[stat] else f" ({rest:+d})")
        return "hurt" if stat == "hp" and d < 0 else "other"

    for n, (i, t, stat, d) in enumerate(steps):
        if stat == "exp":
            out[n] = ("kill we damaged" + ("" if d % full == 0 else " (a part)") if d > 0 else "other", d)
        elif stat == "mp":
            out[n] = (mp_causes[n] if n in mp_causes else plain(stat, t, d), d)
    for idx, (n, (i, t, stat, d)) in enumerate(hp_steps):
        c = hp_cast.get(round(t, 4))
        if c is not None and d == -sk[c.key].hp:
            out[n], pend = (f"cast {c.key}", d), [c, 0]
            continue
        if pend is not None and t - pend[0].t <= SERVER_BY + 0.15:
            cost = sk[pend[0].key].hp
            if pend[1] == 1 and d == -cost:
                out[n], pend = (f"cast {pend[0].key} subtracted again by the server", 0), None
                continue
            nxt = hp_steps[idx + 1][1] if idx + 1 < len(hp_steps) else None
            if pend[1] == 0 and nxt is not None and nxt[3] == -cost and nxt[1] - pend[0].t <= SERVER_BY + 0.15 \
                    and round(nxt[1], 4) not in hp_cast:
                pend[1] = 1
                out[n] = (plain(stat, t, d - cost) + f" (cast {pend[0].key} shown back)", d - cost)
                continue
        out[n] = (plain(stat, t, d), d)
    return out


# ------------------------------------------------------------------ everything loaded once
class World:
    def __init__(self, cap, refresh=False):
        a = time.perf_counter()
        self.cap = cap
        self.fr = frames(cap, refresh)
        self.keys = load.keys(cap)
        self.lives = lives(cap)
        self.sk = skills()
        self.rc = Reaches(self.sk)
        self.t = self.fr["t"]
        self.steps = hud_steps(self.fr)
        self.nav = load.Map(self.fr["map"]).nav
        self.casts, self.mp_causes, self.presses = casts(self.keys, self.steps, self.sk, self.mp_at, self.place_at)
        self.ct = np.array([c.t for c in self.casts])
        ft, ff = facing_at(self.keys)
        for c in self.casts:
            c.i = min(len(self.t) - 1, int(np.searchsorted(self.t, c.t)))
            c.me = self.me_at(c.i)
            j = int(np.searchsorted(ft, c.t)) - 1
            c.facing = int(ff[j]) if j >= 0 else 0
        self.mob = json.loads((ROOT / "assets" / "mcw" / "mobs" / str(self.lives[0].kind) / "mob.json").read_text(encoding="utf-8"))
        self.full_exp = int(self.mob["info"]["exp"])
        self.evs = attribute(self.lives, self.casts, self.rc)
        self.exp_match = match_exp(self.evs, self.steps, self.full_exp)
        self.causes = step_causes(self.steps, self.casts, self.mp_causes, self.keys, self.sk, self.full_exp)
        self._touch, self._static = None, None
        self.load_s = time.perf_counter() - a

    @property
    def touch(self) -> Touch:
        if self._touch is None:
            self._touch = Touch(self.fr, self.lives, self.mob)
        return self._touch

    def idx(self, t) -> int:
        return min(len(self.t) - 1, int(np.searchsorted(self.t, t)))

    def mp_at(self, t):
        return int(self.fr["mp"][self.idx(t)])

    def place_at(self, t) -> str:
        """Where we are at t: 'stand' (feet on a surface), 'rope' (no surface within 8 px, on a rope's x and
        still in x over the last 0.15 s), 'air', '?' (our tag not found). The model's placement rule in small."""
        i = self.idx(t)
        x, y = self.fr["mx"][i], self.fr["my"][i]
        if np.isnan(x):
            return "?"
        off = min((abs(yp - (y - 1)) for _, yp in self.nav.surfaces(x)), default=99)
        if off <= 2:
            return "stand"
        xs = self.fr["mx"][max(0, self.idx(t - 0.15)):i + 1]
        if off > 8 and np.nanmax(xs) - np.nanmin(xs) <= 1 and \
                any(abs(r.x - x) <= 12 and r.top - 12 <= y <= r.bottom + 12 for r in self.nav.ropes):
            return "rope"
        return "air"

    def me_at(self, i, slack=15):
        mx, my = self.fr["mx"], self.fr["my"]
        if not np.isnan(mx[i]):
            return float(mx[i]), float(my[i])
        for d in range(1, slack + 1):
            for j in (i - d, i + d):
                if 0 <= j < len(mx) and not np.isnan(mx[j]):
                    return float(mx[j]), float(my[j])
        return None

    def frame_no(self, t) -> int:
        return int(self.fr["n"][self.idx(t)])

    def players(self, i) -> list:
        """The other players' feet on the map on frame i, from the name tags (centre x, top y - 1). The tag list
        also holds ours, mobs' own tags, guild names (a second line 22 px under a player's tag: the same x) and
        text that never moves (NPC names): out go the tag at our feet, a tag of MOB_TAG's size or under a mob's
        feet, and a tag on a spot that holds one for more than 50 s of the capture."""
        cx, cy = self.fr["cx"][i], self.fr["cy"][i]
        if np.isnan(cx):
            return []
        if self._static is None:
            n = Counter()
            for j in range(len(self.t)):
                if not np.isnan(self.fr["cx"][j]):
                    for b in self.fr["tags"][j]:
                        n[(int(b[0] + b[2] / 2 + self.fr["cx"][j]) // 8, int(b[1] + self.fr["cy"][j]) // 8, b[2])] += 1
            self._static = {k for k, v in n.items() if v > 3000}
        me = self.me_at(i)
        feet = [L.at(i, slack=0) for L in lives_at(self, i)]
        out = []
        for b in self.fr["tags"][i]:
            x, y = b[0] + b[2] / 2 + cx, b[1] - 1 + cy
            if me is not None and abs(x - me[0]) <= 12 and abs(y - me[1]) <= 12:
                continue
            if abs(b[2] - MOB_TAG[0]) <= 2 and b[3] >= MOB_TAG[1] - 1:
                continue
            if any(f is not None and -30 <= x - f[0] <= 6 and -4 <= y - f[1] <= 10 for f in feet):
                continue
            if (int(x) // 8, int(y + 1) // 8, b[2]) in self._static:
                continue
            out.append((x, y))
        return out

    def mob_tag(self, L: Life, i: int) -> bool | None:
        """Is the mob's own name tag under its feet on frame i (None: the mob is not seen on it)?"""
        k = int(np.searchsorted(L.i, i))
        if k >= len(L.i) or L.i[k] != i or np.isnan(self.fr["cx"][i]):
            return None
        for b in self.fr["tags"][i]:
            if abs(b[2] - MOB_TAG[0]) <= 2 and b[3] >= MOB_TAG[1] - 1:
                px, py = b[0] + b[2] / 2 + self.fr["cx"][i], b[1] - 1 + self.fr["cy"][i]
                if -24 <= px - L.x[k] <= 0 and -4 <= py - L.y[k] <= 10:
                    return True
        return False


# ------------------------------------------------------------------ printing
def pct(v, ps=(5, 50, 95), nd=3):
    v = np.asarray(v, float)
    v = v[~np.isnan(v)]
    return [round(float(np.percentile(v, p)), nd) for p in ps] if len(v) else None


def hist(v, lo, hi, step) -> str:
    v = np.asarray(v, float)
    h = np.histogram(v, bins=np.arange(lo, hi + step / 2, step))[0]
    return f"[{lo:g}..{hi:g} by {step:g}] " + " ".join(str(int(x)) for x in h) + \
        (f"  (under {int((v < lo).sum())}, over {int((v >= hi).sum())})" if len(v) and ((v < lo) | (v >= hi)).any() else "")


def table(c: Counter) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))


def block0(w: World):
    print("\n== 0. THE HUD's STEPS AND THEIR CAUSES (`step_causes`)")
    for stat in ("mp", "hp", "exp"):
        c = Counter()
        for n, s in enumerate(w.steps):
            if s[2] == stat:
                cause = w.causes[n][0]
                c[cause if cause not in ("other", "hurt") else f"{cause} {s[3]:+d}" if cause == "other" else "hurt"] += 1
        print(f"  {stat}: {sum(c.values())} steps: {table(c)}")
    hurts = [w.causes[n][1] for n, s in enumerate(w.steps) if s[2] == "hp" and w.causes[n][0].startswith("hurt")]
    print(f"  hurts: {len(hurts)}, sizes p5/50/95 {pct([-h for h in hurts], nd=0)}")
    for key, (stat, amount) in POTIONS.items():
        kd = np.array([k["t"] for k in w.keys if k["down"] and k["key"] == key])
        st = np.array([s[1] for n, s in enumerate(w.steps) if s[2] == stat and w.causes[n][0].startswith(f"potion {key}")])
        lag = [a - kd[np.searchsorted(kd, a) - 1] for a in st]
        print(f"  potion {key}: {len(kd)} key-downs, {len(st)} steps; key-down -> step s p5/50/95 {pct(lag)}  {hist(lag, 0.2, 0.8, 0.05)}")
    for stat in ("hp", "mp"):
        tt = np.array([s[1] for n, s in enumerate(w.steps) if s[2] == stat and w.causes[n][0] == "recovery"])
        print(f"  recovery {stat} +{RECOVERY[stat]}: {len(tt)} ticks, gaps s p5/50/95 {pct(np.diff(tt), nd=2)}")
    kill = [e.exp_t - e.cast.t for e in w.evs if e.kind == "die" and e.who == "us" and e.exp_sure and e.cast.t_hi == e.cast.t
            and e.cast.key in ("q", "w")]
    print(f"  the server's lag (cause -> the HUD's step): a kill's EXP after the q / w key-down p5/50/95 {pct(kill)} s (n {len(kill)}); "
          f"a potion after its key: above; a hurt after the touch began: block 6; a cast's cost: its own step is the client's (block 1)")


def block1(w: World):
    print("\n== 1. CAST (`casts`): a skill key's key-down confirmed by its MP step")
    pr, cs, sk = w.presses, w.casts, w.sk
    for key in sk:
        c = Counter(p[2] for p in pr if p[1] == key)
        n = sum(c.values())
        print(f"  {key} {sk[key].name} (MP {sk[key].mp}" + (f", HP {sk[key].hp}" if sk[key].hp else "") + f"): {n} key-downs -> {table(c)}"
              f"  | followed by their step: {c['cast']} = {c['cast'] / max(1, n):.0%}")
    print(f"  casts: {table(Counter(f'{c.key} {c.how}' for c in cs))}   (held = no key-down of its own: the key still "
          f"down at the swing's end; server = the client's step never showed)")
    for key in sk:
        lag = [c.t_mp - c.t for c in cs if c.key == key and c.how == "key"]
        print(f"  {key}: key-down -> the MP step, s p5/50/95 {pct(lag)} (n {len(lag)})  {hist(lag, 0, 0.32, 0.02)}")
    back = [c for c in cs if c.shown_back is not None]
    print(f"  the server's value: a cast's cost shown back {len(back)} times, {pct([c.shown_back - c.t for c in back])} s after the "
          f"key-down; subtracted again {sum(1 for c in back if c.again)} times, {pct([c.again - c.t for c in back if c.again])} s after "
          f"the key-down; server-only casts' step {pct([c.t_mp - c.t for c in cs if c.how == 'server'])} s after it")
    # what the presses that cast nothing have in common
    ct = w.ct
    since = {k: [] for k in ("in swing", "none", "no mp", "rope", "cooldown")}
    for t, key, what in pr:
        if what == "cast":
            continue
        j = int(np.searchsorted(ct, t)) - 1
        since[what].append((t - ct[j] if j >= 0 else 99.0, key, cs[j].key if j >= 0 else None, t))
    v = [s[0] for s in since["in swing"]]
    print(f"  in swing ({len(v)}): since the cast's key-down, s {hist(v, 0, 0.9, 0.1)}")
    place = Counter((what, w.place_at(t)) for t, key, what in pr)
    print("  where we were at the key-down: " + "; ".join(
        f"{what}: " + ", ".join(f"{pl} {place[(what, pl)]}" for pl in ("stand", "air", "rope", "?") if place[(what, pl)])
        for what in ("cast", "in swing", "no mp", "rope", "cooldown", "none")))
    print(f"  none ({len(since['none'])}): " + ", ".join(f"{key}@{t:.1f} (frame {w.frame_no(t)}, {w.place_at(t)}, {s:.2f} s after {lk})"
                                                         for s, key, lk, t in since["none"][:16]))
    e_air = [(what, w.place_at(t)) for t, key, what in pr if key == "e"]
    print(f"  e (Rush) key-downs in the air: {sum(1 for a in e_air if a[1] == 'air')}, of them cast "
          f"{sum(1 for a in e_air if a == ('cast', 'air'))}; q in the air: cast {place[('cast', 'air')] - sum(1 for a in e_air if a == ('cast', 'air'))}")
    cd = [s[0] for s in since["cooldown"]]
    ee = [b.t - a.t for a, b in zip([c for c in cs if c.key == 'e'], [c for c in cs if c.key == 'e'][1:])]
    print(f"  e cooldown ({sk['e'].cooltime:g} s in Skill.img): {len(cd)} key-downs {pct(cd, (0, 50, 100), 2)} s after the last e cast "
          f"did nothing; the shortest gaps between two e casts {np.round(np.sort(ee)[:3], 2).tolist()} s")
    # the swing's length
    lands = {}
    for n, c in enumerate(cs):
        if c.key in ("q", "w") and c.how == "key" and c.t_hi == c.t:
            ex = [e.t - c.t for e in c.evs if e.how == "seen" and e.t - c.t < 0.65 and
                  (e.kind == "hit" or (not e.after_hit and e.exp_t is not None and e.exp_t < e.t - 0.03))]
            if ex:
                lands[n] = min(ex)
    v = np.array(list(lands.values()))
    print(f"  the hit lands = a hit pose seen to begin, or a die pose the EXP step came before (else it waits for the server), "
          f"since a q / w key-down (n {len(v)}): {hist(v, 0.44, 0.64, 0.01)}")
    stab, swing = v[v < 0.53], v[v >= 0.53]
    print(f"     two heaps: a stab {len(stab)} casts, p50 {np.median(stab):.3f} s; a swing {len(swing)} casts, p50 {np.median(swing):.3f} s"
          f"  (attacks.json: the trail starts 400 / 450 ms into a stab / swing x 1.125 = 0.450 / 0.506 s; + ~0.05 s key -> screen)")
    gaps = {"stab": [], "swing": [], "not known": []}
    for n in range(len(cs) - 1):
        a, b = cs[n], cs[n + 1]
        if a.key in ("q", "w") and a.how == "key" and b.how == "key" and a.t_hi == a.t:
            gaps["not known" if n not in lands else "stab" if lands[n] < 0.53 else "swing"].append(b.t - a.t)
    for st, g in gaps.items():
        g = np.sort(np.array(g))
        print(f"     gap to the next cast's key-down after a {st} ({len(g)}, {int((g < 1.3).sum())} under 1.3 s): the shortest "
              f"{np.round(g[:6], 3).tolist()}  {hist(g[g < 1.3], 0.80, 1.30, 0.05)}")
    from maplebrain.brain.reach import Reach
    r = Reach(WEAPON)
    print(f"     brain/reach.py for {WEAPON} (attackSpeed {r.attack_speed}): swing_s {r.swing_s:.3f} s = the swing stance; a stab = "
          f"{0.75 * (10 + r.attack_speed) / 16:.3f} s. Measured: a new cast {min(gaps['stab']):.3f} s after a stab, {min(gaps['swing']):.3f} s after a swing")
    # the chosen key-down against the first reaction
    kd = {k: np.array([x["t"] for x in w.keys if x["down"] and x["key"] == k]) for k in sk}
    res, weak = Counter(), Counter()
    for c in cs:
        if c.key != "q":
            continue
        ex = sorted(e.t for e in c.evs if e.exact and not e.after_hit)
        if not ex:
            res["no reaction seen to begin"] += 1
            continue
        lag = ex[0] - c.t
        alt = [k for k in kd["q"] if abs(k - c.t) > 1e-6 and abs(k - c.t) < 0.35 and 0.47 <= ex[0] - k <= 0.60]
        r_ = "fits (0.47-0.60 s)" if 0.47 <= lag <= 0.60 else "another key-down fits" if alt else "no key-down fits"
        res[r_] += 1
        if c.t_hi > c.t:
            weak[r_] += 1
    print(f"  the q cast's key-down against the mob's first reaction: {table(res)}; of them with a second candidate "
          f"key-down (t_hi): {table(weak)}")


def block2(w: World):
    print("\n== 2. MOB_HIT BY US (`landing_window`, `in_reach`, `hit_by`)")
    cs, sk, evs = w.casts, w.sk, w.evs
    for key in sk:
        b = w.rc.box(key, w.lives[0].kind)
        print(f"  {key}: window {LAND[key][0]:.2f}..{LAND[key][1]:.2f} s after the key-down; reach vs a Bubbling {b.lo:.0f}..{b.hi:.0f} px in "
              f"front, {b.ylo:.0f}..{b.yhi:.0f} px in y (mob feet - ours), + 25 px; up to {sk[key].mobs} mobs")
    # reactions around every cast, in reach, any time: the lag's shape
    for key in sk:
        ex_k, ex_mp, rough = [], [], []
        for c in cs:
            if c.key != key:
                continue
            for e in evs_between(evs, c.t - 0.2, c.t + 1.4):
                if in_reach(w.rc, c, e.life) == "front":
                    (ex_k if e.exact else rough).append(e.t - c.t)
                    if e.exact:
                        ex_mp.append(e.t - c.t_mp)
        ex_k = np.array(ex_k)
        inw = ex_k[(ex_k >= LAND[key][0]) & (ex_k <= LAND[key][1])]
        print(f"  {key}: hit / die poses seen to begin on mobs in reach, since the key-down ({len(ex_k)}): {hist(ex_k, -0.2, 1.4, 0.05)}")
        print(f"       inside the window: n {len(inw)}, s p5/50/95 {pct(inw)}; since the MP step: p5/50/95 "
              f"{pct([v for v in ex_mp if LAND[key][0] - 0.3 <= v <= LAND[key][1]])}")
        if key == "q":
            print(f"       fine, 0.40..0.80 by 0.02: {hist(ex_k, 0.40, 0.80, 0.02)}")
            a = [e.t - c.t for c in cs if c.key == key for e in c.evs if e.kind == "die" and e.how == "seen" and not e.after_hit]
            b = [e.t - c.t for c in cs if c.key == key for e in c.evs if e.kind == "die" and e.after_hit and e.exact]
            h = [e.t - c.t for c in cs if c.key == key for e in c.evs if e.kind == "hit" and e.exact]
            print(f"       by kind: hit pose p5/50/95 {pct(h)} (n {len(h)}); die pose straight from a living pose {pct(a)} (n {len(a)}); "
                  f"die pose out of a hit pose {pct(b)} (n {len(b)})")
    # per cast: mobs that reacted
    for key in sk:
        per, none_reach, none_empty = Counter(), 0, 0
        for c in cs:
            if c.key != key:
                continue
            n = len({e.life.id for e in c.evs})
            per[n] += 1
            if n == 0:
                near = sum(1 for L in lives_at(w, c.i) if in_reach(w.rc, c, L) == "front")
                none_reach += near > 0
                none_empty += near == 0
        tot = sum(per.values())
        print(f"  {key}: mobs reacting per cast ({tot} casts): " + ", ".join(f"{k}: {per[k]}" for k in sorted(per)) +
              f"  | none: {per[0]} = {per[0] / max(1, tot):.0%} ({none_empty} with no mob in reach at the key-down, {none_reach} with one)")
    over = [(c, len({e.life.id for e in c.evs})) for c in cs if len({e.life.id for e in c.evs}) > sk[c.key].mobs]
    print(f"  casts claiming more mobs than the skill's count: {len(over)}" +
          "".join(f"; {c.key} at {c.t:.2f} (frame {w.frame_no(c.t)}): {n}" for c, n in over[:6]))
    # the facing belief
    side = Counter()
    for e in evs:
        if e.who != "another" and e.cast is not None:
            side[in_reach(w.rc, e.cast, e.life)] += 1
    print(f"  the facing belief (the last left / right key-down): events in a window with the mob in the box in front {side['front']}, "
          f"only in the mirrored box (behind us) {side['back']}, a place not known {side['?']}")
    # hits in no window of ours
    hits = [e for e in evs if e.kind == "hit" and e.blow]
    print(f"  hit poses (not the killing blow's own): {len(hits)}: {table(Counter(e.who for e in hits))}")
    for kind, lst in (("hit poses", hits), ("deaths", [e for e in evs if e.kind == "die"])):
        c = Counter()
        ex = []
        for e in lst:
            if e.who != "another":
                continue
            me = w.me_at(e.i)
            near_us = me is not None and abs(e.x - me[0]) <= NEAR[0] and abs(e.y - me[1]) <= NEAR[1]
            pl = [p for p in w.players(e.i) if abs(p[0] - e.x) <= NEAR[0] and abs(p[1] - e.y) <= 100]
            c[("near us" if near_us else "farther") + (", a player's tag within 250 px" if pl else ", no player's tag near")] += 1
            if near_us and len(ex) < 6:
                ex.append(f"frame {w.frame_no(e.t)} ({e.x - me[0]:+.0f} px)")
        print(f"  {kind} in NO window of ours ({sum(c.values())}): {table(c)}" + (f"; near us e.g. {', '.join(ex)}" if ex else ""))
    # control: the windows moved in time - what the real rule calls another's, caught by a moved window
    n_other = sum(1 for e in evs if e.who == "another")
    caught = []
    for shift in (-7.0, -5.0, -3.0, 3.0, 5.0, 7.0):
        ct2 = w.ct + shift
        n = 0
        for e in evs:
            if e.who != "another":
                continue
            for j in range(int(np.searchsorted(ct2, e.t_lo - 1.5)), len(cs)):
                c = cs[j]
                if ct2[j] > e.t:
                    break
                lo, hi = LAND[c.key]
                if e.t_lo <= c.t_hi + shift + hi and e.t >= ct2[j] + lo:
                    i2 = w.idx(ct2[j])
                    me, p = w.me_at(i2), e.life.at(i2)
                    if me is not None and p is not None:
                        b = w.rc.box(c.key, e.life.kind)
                        dx, dy = (p[0] - me[0]) * (c.facing or 1), p[1] - me[1]
                        if b.lo - 25 <= dx <= b.hi + 25 and b.ylo - 25 <= dy <= b.yhi + 25:
                            n += 1
                            break
        caught.append(n)
    print(f"  control: every window moved by -7, -5, -3, +3, +5, +7 s (our place then): of the {n_other} events that are another's, "
          f"{caught} fall in a moved window with the mob in reach -> about {np.mean(caught):.1f} of the "
          f"{sum(1 for e in evs if e.who == 'us')} 'us' verdicts are another's by chance")
    # the mob's own name tag
    c = Counter()
    lag = []
    for e in hits:
        L = e.life
        m = (L.t >= e.t - 0.03) & (L.t <= e.t + 1.0)
        tg = [w.mob_tag(L, int(i)) for i in L.i[m]]
        before = any(w.mob_tag(L, int(i)) for i in L.i[(L.t >= e.t - 0.5) & (L.t < e.t - 0.03)])
        if before:
            continue
        c[(e.who, "tag" if any(tg) else "no tag")] += 1
        if any(tg) and e.who == "us":
            lag.append(L.t[m][[bool(v) for v in tg]][0] - e.t)
    print(f"  a second witness - the mob's own name tag ({MOB_TAG[0]} x {MOB_TAG[1]} px under its feet) within 1 s of a hit pose "
          f"(none in the 0.5 s before): by us {c[('us', 'tag')]} of {c[('us', 'tag')] + c[('us', 'no tag')]}, unknown "
          f"{c[('unknown', 'tag')]} of {c[('unknown', 'tag')] + c[('unknown', 'no tag')]}, another "
          f"{c[('another', 'tag')]} of {c[('another', 'tag')] + c[('another', 'no tag')]}; it shows {pct(lag)} s after the pose (p5/50/95)")


def evs_between(evs: list, t0: float, t1: float) -> list:
    return [e for e in evs if t0 <= e.t <= t1] if len(evs) < 200 else _between(evs, t0, t1)


_EVT = {}


def _between(evs, t0, t1):
    key = id(evs)
    if key not in _EVT:
        _EVT[key] = np.array([e.t for e in evs])
    a, b = np.searchsorted(_EVT[key], t0), np.searchsorted(_EVT[key], t1, side="right")
    return evs[a:b]


_LIVES_AT = {}


def lives_at(w: World, i: int) -> list:
    """The lives that span frame i."""
    if id(w) not in _LIVES_AT:
        _LIVES_AT[id(w)] = (np.array([L.i[0] for L in w.lives]), np.array([L.i[-1] for L in w.lives]))
    a, b = _LIVES_AT[id(w)]
    return [w.lives[k] for k in np.nonzero((a <= i) & (b >= i))[0]]


def block3(w: World):
    print("\n== 3. MOB_DIED BY US AGAINST THE EXP STEPS (`match_exp`, `died_by`)")
    full, evs = w.full_exp, w.evs
    deaths = [e for e in evs if e.kind == "die"]
    print(f"  deaths (lives ending in a die pose): {len(deaths)}; the die pose's begin: {table(Counter(e.how for e in deaths))}; "
          f"lives with die-pose sightings that a living pose followed (pose noise): {sum(1 for L in w.lives if L.false_die)}")
    n_c, lag = Counter(), []
    for st, cand, need in w.exp_match:
        kind = f"+{full}" if st[3] == full else f"+{st[3]}" + (f" (= {need} x {full})" if st[3] % full == 0 else " (a part)")
        n_c[(kind, "too few" if len(cand) < need else "exactly" if len(cand) == need else "more")] += 1
        if len(cand) == need:
            lag += [st[1] - e.t for e in cand if e.exact]
    for k in sorted({k[0] for k in n_c}, key=lambda s: (len(s), s)):
        tot = sum(v for (a, b), v in n_c.items() if a == k)
        print(f"  EXP steps {k}: {tot}; deaths whose die pose began {EXP_DIE[0]:+.2f}..{EXP_DIE[1]:+.2f} s around the step: "
              f"exactly as many as it pays for {n_c[(k, 'exactly')]}, more {n_c[(k, 'more')]}, too few {n_c[(k, 'too few')]}")
    print(f"  EXP step - the die pose began (a step with exactly its deaths, the begin exact, n {len(lag)}): p5/50/95 {pct(lag)}  "
          f"{hist(lag, -0.5, 0.3, 0.05)}")
    wide = []
    dt = np.array([e.t for e in deaths])
    for st in w.steps:
        if st[2] == "exp" and st[3] > 0:
            wide += [st[1] - deaths[k].t for k in np.nonzero(np.abs(dt - st[1]) < 2.0)[0] if deaths[k].exact]
    print(f"     every exact death within 2 s of every EXP step (what lies beyond the window's edges): {hist(wide, -1.0, 1.0, 0.1)}")
    few = [(st, cand, need) for st, cand, need in w.exp_match if len(cand) < need]
    print(f"  EXP steps with too few deaths ({len(few)}): " + "; ".join(
        f"+{st[3]} frame {w.frame_no(st[1])} ({len(cand)} of {need})" for st, cand, need in few[:10]))
    # the cross-check: the window rule against the EXP step, by time only
    def col(e):
        if e.exp_raw is None:
            return "no EXP step"
        amount, need, n = e.exp_raw
        return "a part" if amount % full else f"+{full}, its only death" if n <= need else f"+{full}, shared"
    cols = (f"+{full}, its only death", f"+{full}, shared", "a part", "no EXP step")
    conf = Counter((e.who, col(e)) for e in deaths)
    print("  the window rule (rows) against the EXP step the death can have paid (columns; 'shared' = more deaths than the step pays for):")
    print("       " + " " * 9 + "".join(f"{c:>24}" for c in cols))
    for who in ("us", "unknown", "another"):
        print("       " + f"{who:<9}" + "".join(f"{conf[(who, c)]:>24}" for c in cols))
    shared = [(st, cand, need) for st, cand, need in w.exp_match if len(cand) > need]
    res = Counter()
    for st, cand, need in shared:
        ours = sum(1 for e in cand if e.who == "us")
        res["exactly the needed ones are in a window of ours" if ours == need else "more are" if ours > need else "fewer are"] += 1
    print(f"  shared steps ({len(shared)}): {table(res)}")
    a = [e for e in deaths if e.who == "us" and e.exp_raw is None]
    b = [e for e in deaths if e.who != "us" and col(e) == cols[0]]
    print(f"  in our window, no EXP step ({len(a)}): " + "; ".join(why_no_exp(w, e) for e in a[:12]))
    print(f"  the only death of a +{full}, not in our window ({len(b)}): " + "; ".join(why_not_ours(w, e) for e in b[:16]))
    part = [(st, cand) for st, cand, need in w.exp_match if st[3] % full]
    print(f"  EXP of a part ({len(part)}): " + "; ".join(
        f"+{st[3]} frame {w.frame_no(st[1])}: " + (", ".join(
            f"death window {e.who}, hits on it before: {table(Counter(h.who for h in e.life.evs if h.kind == 'hit' and h.blow)) or 'none seen'}"
            for e in cand) or "no death seen") for st, cand in part))
    final = Counter(died_by(e, full) for e in deaths)
    print(f"  `died_by`: {table(final)} of {len(deaths)} deaths -> kills (mob_died by us): {final['us']}; EXP steps' deaths paid for: "
          f"{sum(need for st, cand, need in w.exp_match)}")
    me_near = Counter()
    for e in deaths:
        me = w.me_at(e.i)
        me_near[(died_by(e, full), "near us" if me is not None and abs(e.x - me[0]) <= NEAR[0] and abs(e.y - me[1]) <= NEAR[1] else "farther")] += 1
    print(f"     by distance at the death (near = within {NEAR[0]:.0f} x {NEAR[1]:.0f} px of us): " +
          ", ".join(f"{k[0]} {k[1]} {v}" for k, v in sorted(me_near.items())))
    unk = [e for e in deaths if died_by(e, full) == "unknown"]
    print(f"     unknown ({len(unk)}): " + "; ".join(f"frame {w.frame_no(e.t)} (window {e.who}, EXP {'+' + str(e.exp) if e.exp else 'none'}, {e.how})" for e in unk[:12]))


def why_no_exp(w: World, e: Ev) -> str:
    near = [s for s in w.steps if s[2] == "exp" and abs(s[1] - e.t) < 1.2]
    return (f"frame {w.frame_no(e.t)} ({e.how}, {e.cast.key} +{e.t - e.cast.t:.2f} s" +
            (f", EXP steps at {', '.join(f'{s[1] - e.t:+.2f}' for s in near)} s" if near else ", no EXP step within 1.2 s") + ")")


def why_not_ours(w: World, e: Ev) -> str:
    j = int(np.searchsorted(w.ct, e.t)) - 1
    c = w.casts[j] if j >= 0 else None
    me = w.me_at(e.i)
    if c is None or me is None:
        return f"frame {w.frame_no(e.t)} (no cast / our place not known)"
    p = e.life.at(c.i)
    return (f"frame {w.frame_no(e.t)} ({e.how}, {e.who}; last cast {c.key} {e.t - c.t:.2f} s before, mob " +
            (f"{(p[0] - c.me[0]) * (c.facing or 1):+.0f} px in front, {p[1] - c.me[1]:+.0f} in y then" if p and c.me else "not seen then") + ")")


def block4(w: World):
    info = w.mob["info"]
    print(f"\n== 4. HITS PER KILL (a Bubbling: maxHP {info.get('maxHP')}; Skill.img damage at these levels: Power Strike 260 %, Slash "
          f"Blast 124 %, Rush 60 %)")
    full = w.full_exp
    per, seqs, whole, whole_seq = Counter(), Counter(), Counter(), Counter()
    for L in w.lives:
        d = L.evs[-1] if L.evs and L.evs[-1].kind == "die" else None
        if d is None or died_by(d, full) != "us":
            continue
        hs = [h for h in L.evs if h.kind == "hit" and h.blow]
        ours = []                                        # the casts of ours that hit it before the killing one
        for h in hs:
            if h.who == "us" and h.cast is not d.cast and h.cast not in ours:
                ours.append(h.cast)
        other = sum(1 for h in hs if h.who != "us" and h.dur >= 0.1)
        seq = "+".join([c.key for c in ours] + [d.cast.key if d.cast is not None else "?"])
        per[(1 + len(ours), "+ hit poses not ours" if other else "")] += 1
        seqs[seq + (" (+ hit poses not ours)" if other else "")] += 1
        if L.start == "fade-in" and not other and d.cast is not None:
            whole[1 + len(ours)] += 1
            whole_seq[seq] += 1
    tot = sum(per.values())
    print(f"  lives we killed (`died_by` us): {tot}; casts of ours that hit it (hit poses in our windows + the killing blow): " +
          ", ".join(f"{k[0]}{' (' + k[1] + ')' if k[1] else ''}: {v}" for k, v in sorted(per.items())))
    print(f"     by the keys, in order (the last one killed; ? = the kill known from the EXP step only): {table(seqs)}")
    print(f"     lives seen from their fade-in with no hit pose of another's ({sum(whole.values())}) - the clean sample: " +
          ", ".join(f"{n} hit{'s' if n > 1 else ''}: {v} ({v / max(1, sum(whole.values())):.0%})" for n, v in sorted(whole.items())) +
          f"; by keys: {table(whole_seq)}")
    c = Counter()
    for cst in w.casts:
        for L in {e.life.id: e.life for e in cst.evs}.values():
            died = any(e.kind == "die" for e in cst.evs if e.life is L)
            c[(cst.key, "died" if died else "lived")] += 1
    print("  per mob a cast reached: " + "; ".join(
        f"{key}: died {c[(key, 'died')]}, lived {c[(key, 'lived')]}" +
        (f" ({c[(key, 'died')] / (c[(key, 'died')] + c[(key, 'lived')]):.0%} die at once)" if c[(key, 'died')] + c[(key, 'lived')] else "")
        for key in w.sk))


def block5(w: World):
    print("\n== 5. KNOCKBACK AT A HIT (the mob's x over the time after its hit pose began; + = away from us)")
    info = w.mob["info"]
    print(f"  a Bubbling: pushed {info.get('pushed')} (a hit line of at least this much damage throws it: game_rules.md D1; "
          f"v83-HC: ~27 px in 0.248 s + ~4 px coasting, the mob turns to the attacker)")
    groups = [("us with q / w", lambda e: e.who == "us" and e.cast.key in ("q", "w")),
              ("us with e (Rush carries the mobs along)", lambda e: e.who == "us" and e.cast.key == "e"),
              ("another", lambda e: e.who == "another")]
    for name, sel in groups:
        rows = {0.1: [], 0.2: [], 0.3: [], 0.6: [], 1.0: []}
        face, durs = Counter(), []
        for e in w.evs:
            if e.kind != "hit" or not e.blow or not e.exact or e.dur < 0.1 or not sel(e):
                continue
            L = e.life
            me = e.cast.me if e.cast is not None else w.me_at(e.i)
            if me is None:
                continue
            side = 1 if e.x >= me[0] else -1
            for tau in rows:
                p = L.at(w.idx(e.t + tau), slack=4)
                if p is not None and e.t + tau <= L.t[-1]:
                    rows[tau].append((p[0] - e.x) * side)
            if e.k + 3 < len(L.i):
                face["faces us" if L.face[e.k + 3] == -side else "faces away"] += 1
            if e.dur > 0.3:
                durs.append(e.dur)
        print(f"  hits by {name} (the hit pose seen to begin, the mob still seen 0.3 s later: {len(rows[0.3])}):")
        for tau, v in rows.items():
            if v:
                print(f"     after {tau:.1f} s: px p5/25/50/75/95 {pct(v, (5, 25, 50, 75, 95), 0)}" +
                      (f"  {hist(v, -60, 100, 10)}" if tau == 0.3 else ""))
        if not name.startswith("another"):
            print(f"     the mob's facing 3 frames into the hit pose: {table(face)}")
        print(f"     the hit pose lasts (runs over 0.3 s): p5/50/95 {pct(durs)} s (mob.json hit1: {w.mob['frames']['hit1'][0]['delay']} ms; "
              f"v83-HC's hit stance: 0.248 s)")


def block6(w: World):
    print("\n== 6. HP LOSSES (`hurt_by`): which mob hurt us")
    tc, t = w.touch, w.t
    known = sum(1 for v in tc.ids if v is not None)
    print(f"  frames with a mob's body box over ours: {int(tc.has.sum())} of {known} ({tc.has.sum() / known:.1%}); touch episodes {len(tc.episodes)}")
    hurts = [(n, s) for n, s in enumerate(w.steps) if s[2] == "hp" and w.causes[n][0].startswith("hurt")]
    cnt, lag0, lag1, unsure = Counter(), [], [], []
    for n, (i, ts, stat, d) in hurts:
        ids = hurt_by(tc, ts)
        cnt["none" if not ids else "one mob" if len(ids) == 1 else "several mobs"] += 1
        ks = np.nonzero((tc.ep_t0 <= ts) & (tc.ep_t1 >= ts - TOUCH))[0]
        if len(ks):
            lag0.append(ts - tc.ep_t0[ks[-1]])
            lag1.append(max(0.0, ts - tc.ep_t1[ks[-1]]))
        if len(ids) != 1 and len(unsure) < 6:
            unsure.append(f"frame {int(w.fr['n'][i])} ({len(ids)})")
    print(f"  hurts (HP losses that are no cast's cost): {len(hurts)}; mobs whose body was over ours within {TOUCH} s before the step: "
          f"{table(cnt)}" + (f"; e.g. {', '.join(unsure)}" if unsure else ""))
    print(f"  HP step - the touch began: s p5/25/50/75/95 {pct(lag0, (5, 25, 50, 75, 95))}  {hist(lag0, 0, 1.0, 0.1)}")
    print(f"  HP step - the body was last over ours: p5/50/95 {pct(lag1)} (we are thrown clear before the number moves)")
    ht = np.array([s[1] for _, s in hurts])
    c = Counter()
    for a, b, ids in tc.episodes:
        k = int(np.searchsorted(ht, t[a]))
        since = t[a] - ht[k - 1] if k > 0 else 99.0
        nxt = ht[k] - t[a] if k < len(ht) else 99.0
        c[("in the safe time" if since < SAFE_S else "outside the safe time", "a hurt within 0.8 s" if nxt <= 0.8 else "no hurt")] += 1
    print(f"  the other way - touch episodes ({len(tc.episodes)}): " + ", ".join(f"{k[0]}, {k[1]}: {v}" for k, v in sorted(c.items())) +
          f"  (safe time = {SAFE_S} s after a hurt: v83's 2 s + the server's lag)")
    # the hurt's size against the client data
    sizes = [-w.causes[n][1] for n, _ in hurts]
    pa = w.mob["info"].get("PADamage")
    print(f"  sizes: {pct(sizes, (0, 5, 50, 95, 100), 0)} (min/p5/p50/p95/max); the mob's PADamage {pa}: v83 draws {0.8 * pa:.0f}..{pa} before our defence")


def block7(w: World):
    print("\n== 7. WHAT BREAKS THE RULES")
    full, evs = w.full_exp, w.evs
    deaths = [e for e in evs if e.kind == "die"]
    hits = [e for e in evs if e.kind == "hit"]
    # (a) a death with no hit pose
    c = Counter()
    for e in deaths:
        if e.who != "us":
            continue
        own = [h for h in e.life.evs if h.kind == "hit" and not h.blow]
        c["a hit pose first (0-0.25 s)" if own else "straight into the die pose" if e.how == "seen" else
          "the begin not seen (covered): " + e.how] += 1
    print(f"  (a) our killing blows ({sum(c.values())}): {table(c)}")
    gap = [e.t - h.t for e in deaths for h in e.life.evs if h.kind == "hit" and not h.blow]
    print(f"      the hit pose before the die pose lasts: p5/50/95 {pct(gap)} s  {hist(gap, 0, 0.25, 0.025)}")
    late = [e for e in deaths if not e.exact]
    f0 = Counter(int(e.life.frame[e.k]) for e in deaths if e.how != "seen")
    print(f"  (b) deaths whose die pose was first seen late: by its first frame seen: " + ", ".join(f"die1_{k}: {v}" for k, v in sorted(f0.items())) +
          f"; begin not recoverable (window = an interval): {len(late)}, the interval p50/p95 {pct([e.t - e.t_lo for e in late], (50, 95))} s")
    covered = [e.t - e.life.t[e.k - 1] for e in deaths if e.k > 0 and e.how != "seen"]
    print(f"      the mob was not seen for p50/p95/max {pct(covered, (50, 95, 100))} s before that first die sighting (effect, numbers, us over it)")
    # (c) pose noise
    short = [h for h in hits if h.blow and h.dur < 0.1]
    nxt = Counter()
    for h in short:
        L = h.life
        j = h.k
        while j + 1 < len(L.i) and L.anim[j + 1] == "hit1":
            j += 1
        nxt[L.anim[j + 1] if j + 1 < len(L.i) else "the life ends"] += 1
    vis = [float(h.life.seen[h.k]) for h in short]
    print(f"  (c) hit poses seen for under 0.1 s that no die pose follows ({len(short)}: {table(Counter(h.who for h in short))}); after them: "
          f"{table(nxt)}; the share of the mob seen then p50 {np.median(vis):.2f}" if short else "  (c) no short hit poses")
    longer = [h for h in hits if h.blow and h.dur >= 0.1]
    print(f"      hit poses of 0.1 s or more: {len(longer)}, lasting {hist([h.dur for h in longer], 0.1, 1.1, 0.1)}; over 0.65 s "
          f"(hit again while in the pose: one event for two hits): {sum(1 for h in longer if h.dur > 0.65)}")
    print(f"      lives with die-pose sightings in the middle of a life: {sum(1 for L in w.lives if L.false_die)} "
          f"({sum(L.false_die for L in w.lives)} sightings)")
    # (d) two players on one mob
    part = [(st, cand) for st, cand, need in w.exp_match if st[3] % full]
    print(f"  (d) two players on one mob: {len(part)} EXP steps that are a part of {full}: " +
          "; ".join(f"+{st[3]} frame {w.frame_no(st[1])}" + (f" (the death: window {cand[0].who})" if cand else " (no death seen)") for st, cand in part))
    both = Counter()
    for L in w.lives:
        hs = [h for h in L.evs if h.kind == "hit" and h.blow and h.dur >= 0.1]
        d = L.evs[-1] if L.evs and L.evs[-1].kind == "die" else None
        whos = {h.who for h in hs} | ({d.who} if d else set())
        if "us" in whos and "another" in whos:
            both["hit by us and by another"] += 1
            if d is not None:
                both[f"  of them died: window {d.who}, EXP {'+' + str(d.exp) if d.exp else 'none'}"] += 1
    print(f"      lives with events of ours AND of another's: {table(both) or 0}")
    # (e) one event, two casts
    two = 0
    for e in evs:
        n = 0
        for j in range(int(np.searchsorted(w.ct, e.t_lo - 1.5)), len(w.casts)):
            c2 = w.casts[j]
            if c2.t > e.t:
                break
            a, b = landing_window(c2)
            if e.t_lo <= b and e.t >= a and in_reach(w.rc, c2, e.life) == "front":
                n += 1
        two += n > 1
    print(f"  (e) events inside two of our windows at once (the first cast gets them): {two}")
    # (f) a death of ours by window that pays no EXP / EXP with no death: block 3
    ours_far = [e for e in deaths if e.who != "us" and e.exp and e.exp % full == 0]
    print(f"  (f) kills the window missed but the whole EXP shows ({len(ours_far)}): the die pose's begin "
          f"{table(Counter(e.how for e in ours_far))}; window verdict {table(Counter(e.who for e in ours_far))}")
    weak = [c for c in w.casts if c.t_hi > c.t]
    print(f"  (g) casts whose start has two candidate key-downs: {len(weak)} of {len(w.casts)} (their window is "
          f"{pct([c.t_hi - c.t for c in weak], (50,))[0] if weak else 0} s wider)")


BLOCKS = {0: block0, 1: block1, 2: block2, 3: block3, 4: block4, 5: block5, 6: block6, 7: block7}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = None
    if "--only" in sys.argv:
        only = {int(v) for v in sys.argv[sys.argv.index("--only") + 1].split(",")}
        args = [a for a in args if not a.replace(",", "").isdigit()]
    cap = args[0] if args else cache.DESIGN
    w = World(cap, "--refresh" in sys.argv)
    print(f"== {cap}: {len(w.t)} frames ({w.t[-1] - w.t[0]:.0f} s), {len(w.keys)} key events, {len(w.lives)} mob lives "
          f"({sum(1 for e in w.evs if e.kind == 'die')} end in a die pose), {sum(1 for e in w.evs if e.kind == 'hit')} hit-pose runs; "
          f"loaded in {w.load_s:.1f} s")
    print("   skills (Skill.img at the profile's level): " + "; ".join(
        f"{k} = {s.name}: MP {s.mp}" + (f" HP {s.hp}" if s.hp else "") + f", {s.mobs} mob{'s' if s.mobs > 1 else ''}"
        + (f", range {s.range} %" if s.range != 100 else "") + (f", box {s.box}" if s.box else "")
        + (f", cooldown {s.cooltime:g} s" if s.cooltime else "") for k, s in w.sk.items()))
    for n, fn in BLOCKS.items():
        if only is None or n in only:
            fn(w)


if __name__ == "__main__":
    main()
