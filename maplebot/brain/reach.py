"""brain-v2 WHEN TO HIT: where our swing reaches, per weapon type (client data) and per mob (its body box), plus what
the live swings teach (learned reach).

Client data (assets/mcw/attacks.json, from Character Afterimage): each attack stance's box relative to our feet,
facing left. A swing picks one of the weapon's stances at random (spear / polearm: stabT1/T2, swingT2, swingP1/P2 -
the same boxes for both, checked 2026-11-05), so a mob is SURELY hit only where every stance's box overlaps its body,
and MAYBE hit where any one does. The mob's body box (mob.json lt/rb, median over stand/move frames) widens both.
Spear vs Bubbling: sure 27..137 px in front (dx = mob feet - our feet, in front > 0), maybe -2..159.
The user's farming recording agrees: swings hit 70-90 % of the mobs 0..140 px in front, ~30 % past 160
(tools/combat/reach.py).

Learned: every swing logs (dx, dy) of the mobs in front and whether each reacted (hit / dying) 0.25..1.0 s later;
`learned()` = the hit-rate by distance band. Disagreement with the data is reported (`check()`), not acted on yet.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2] / "assets" / "mcw"
FINISHERS = ("F",)                   # stances ending in F (swingPF, stabTF): skill finishers, not a plain swing
SWING_LAND_S = 0.45                  # press -> the hit lands (the tracker shows it ~0.6 s after the press, farming)


@dataclass
class Box:
    """Reach against one mob type, in front-positive px: a mob whose feet are at dx (in front > 0), dy (y down,
    mob feet - our feet) is hit if lo <= dx <= hi and ylo <= dy <= yhi."""
    lo: float
    hi: float
    ylo: float
    yhi: float

    def has(self, dx: float, dy: float, margin: float = 0.0) -> bool:
        return self.lo + margin <= dx <= self.hi - margin and self.ylo <= dy <= self.yhi


def _stances(boxes: dict) -> list:
    return [b for st, b in boxes.items() if not st.endswith(FINISHERS) and not st.startswith("prone")]


def body(mob: dict) -> tuple:
    """A mob's body box (lt x, lt y, rb x, rb y), facing left, median over its stand / move frames."""
    fr = [f for a in ("stand", "move") for f in (mob.get("frames") or {}).get(a, []) if f.get("lt") and f.get("rb")]
    if not fr:
        return (-25, -40, 25, 0)
    return tuple(median(f[k][i] for f in fr) for k, i in (("lt", 0), ("lt", 1), ("rb", 0), ("rb", 1)))


def boxes_vs(stances: list, mob_box: tuple) -> tuple:
    """(sure, maybe) Box of these stance boxes against a mob body. The attack box (facing left) [ltx, rbx] becomes
    [-rbx, -ltx] in front; the mob's body (symmetric enough: we use its half-widths) widens it on both sides."""
    hw_l, hw_r = -mob_box[0], mob_box[2]               # the mob's half-widths (facing left); either side may face us
    hw = (hw_l + hw_r) / 2
    h = -mob_box[1]                                     # body height above its feet
    los, his, ylos, yhis = [], [], [], []
    for ltx, lty, rbx, rby in stances:
        los.append(-rbx - hw)
        his.append(-ltx + hw)
        ylos.append(lty)                                # mob feet above the box top: its body hangs into the box
        yhis.append(rby + h)                            # mob feet below: its top must still reach the box bottom
    sure = Box(max(los), min(his), max(ylos), min(yhis))
    maybe = Box(min(los), max(his), min(ylos), max(yhis))
    return sure, maybe


class Reach:
    def __init__(self, weapon: str = "spear", root: Path = ROOT, attacks: dict | None = None):
        self.root = Path(root)
        att = attacks if attacks is not None else json.loads((self.root / "attacks.json").read_text(encoding="utf-8"))
        weapons = att["weapons"]
        if weapon not in weapons:
            raise KeyError(f"weapon type {weapon!r} not in attacks.json ({', '.join(sorted(weapons))})")
        self.weapon = weapon
        self.stances = _stances(weapons[weapon])
        self.cache = {}
        self.swings = []                                # (t, [(track id, dx, dy)]) waiting for an outcome
        self.samples = []                               # (dx, dy, hit)

    def vs(self, mob_id: int | None, mob: dict | None = None) -> tuple:
        """(sure, maybe) Boxes against this mob type."""
        if mob_id not in self.cache:
            if mob is None and mob_id is not None:
                p = self.root / "mobs" / str(mob_id) / "mob.json"
                mob = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            self.cache[mob_id] = boxes_vs(self.stances, body(mob or {}))
        return self.cache[mob_id]

    # -- learning from live swings
    def swing(self, t: float, near: list):
        """A swing at t; `near` = [(track id, dx, dy)] of the live mobs within ~200 px in front at the press."""
        self.swings.append((t, near))

    def outcome(self, t: float, state_of) -> list:
        """Settle swings older than 1 s: `state_of(id, t0, t1)` -> states the track had in [t0, t1]. Returns the new
        samples (dx, dy, hit)."""
        new = []
        while self.swings and t - self.swings[0][0] > 1.0:
            t0, near = self.swings.pop(0)
            for tid, dx, dy in near:
                hit = any(s in ("hit", "dying") for s in state_of(tid, t0 + 0.25, t0 + 1.0))
                new.append((round(dx), round(dy), hit))
        self.samples += new
        return new

    def learned(self, band: int = 30) -> dict:
        """Hit-rate per dx band (same level, |dy| <= 30): {band start: (hits, n)}."""
        out = {}
        for dx, dy, hit in self.samples:
            if abs(dy) <= 30:
                b = int(dx // band * band)
                h, n = out.get(b, (0, 0))
                out[b] = (h + hit, n + 1)
        return dict(sorted(out.items()))

    def check(self, mob_id: int | None) -> str:
        """One line: the data's sure range vs where live swings actually hit."""
        sure, maybe = self.vs(mob_id)
        hits = sorted(dx for dx, dy, h in self.samples if h and abs(dy) <= 30)
        if len(hits) < 10:
            return f"reach {self.weapon}: data sure {sure.lo:.0f}..{sure.hi:.0f} px; {len(hits)} live hits so far"
        p = lambda q: hits[min(len(hits) - 1, int(q * len(hits)))]
        flag = "  <- live hits reach past the data" if p(0.9) > maybe.hi else ""
        return (f"reach {self.weapon}: data sure {sure.lo:.0f}..{sure.hi:.0f} maybe {maybe.lo:.0f}..{maybe.hi:.0f}; "
                f"live hits p10 {p(0.1)} p50 {p(0.5)} p90 {p(0.9)} (n {len(hits)}){flag}")
