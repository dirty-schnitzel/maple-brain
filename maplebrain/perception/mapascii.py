"""The whole map as text, for checking the tracker by eye (the user, 2026-11-04).

    print(render(map_json, marks=[("@", x, y), ("P3>", x, y)], screen=(x0, x1)))

Everything is in map coordinates and drawn from map.json alone: footholds (flat `=`, slopes `/` `\\`, walls `#`),
ropes `|`, ladders `H`, portals `O`, spawn points `.`; marks (us, tracks) sit on the row above their feet. The
whole map edge to edge (vrBounds + every foothold), scaled to `width` columns; rows ~2x taller than columns, like
console characters.
"""
import math

NO_MAP = 999999999


def _bounds(m: dict) -> tuple:
    fh = list((m.get("footholds") or {}).values())
    xs = [v for f in fh for v in (f["x1"], f["x2"])] or [0]
    ys = [v for f in fh for v in (f["y1"], f["y2"])] or [0]
    vr = m.get("vrBounds") or {}
    x0, x1 = min(xs + [vr.get("left", min(xs))]), max(xs + [vr.get("right", max(xs))])
    y0, y1 = min(ys + [vr.get("top", min(ys))]), max(ys + [vr.get("bottom", max(ys))])
    return x0, y0, x1, y1


class Canvas:
    def __init__(self, m: dict, width: int = 160, aspect: float = 2.0):
        self.x0, self.y0, x1, y1 = _bounds(m)
        self.sx = max(1e-6, (x1 - self.x0) / (width - 1))      # map px per column
        self.sy = self.sx * aspect                              # map px per row
        self.w, self.h = width, int((y1 - self.y0) / self.sy) + 2
        self.g = [[" "] * self.w for _ in range(self.h)]

    def cell(self, x, y):
        return int(round((x - self.x0) / self.sx)), int(round((y - self.y0) / self.sy))

    def put(self, x, y, s, dy=0):
        c, r = self.cell(x, y)
        r += dy
        if 0 <= r < self.h:
            for i, ch in enumerate(s):
                if 0 <= c + i < self.w:
                    self.g[r][c + i] = ch

    def seg(self, x1, y1, x2, y2, ch):
        n = max(1, int(math.hypot((x2 - x1) / self.sx, (y2 - y1) / self.sy) * 2))
        for i in range(n + 1):
            t = i / n
            c, r = self.cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            if 0 <= r < self.h and 0 <= c < self.w:
                self.g[r][c] = ch

    def text(self) -> str:
        rows = ["".join(row).rstrip() for row in self.g]
        while len(rows) > 1 and not rows[0]:          # empty sky over the highest foothold (vrBounds top)
            rows.pop(0)
        return "\n".join(rows)


def _slope_char(f) -> str:
    dx, dy = f["x2"] - f["x1"], f["y2"] - f["y1"]
    if dx == 0:
        return "#"
    k = dy / dx                                     # screen y grows downwards: going right and up = '/'
    return "=" if abs(k) < 0.25 else ("/" if k < 0 else "\\")


def render(m: dict, marks=(), screen=None, width: int = 160, spawns: bool = True, ruler: bool = True) -> str:
    """`marks`: [(text, map x, feet y)], drawn last in order (later ones on top). `screen`: (x0, x1) map x span of
    what's on screen right now -> `[` `]` on the ruler."""
    cv = Canvas(m, width)
    for r in m.get("ladderRopes") or []:
        cv.seg(r["x"], r["y1"], r["x"], r["y2"], "H" if r.get("isLadder") else "|")
    fh = list((m.get("footholds") or {}).values())
    for f in sorted(fh, key=lambda f: f["x1"] == f["x2"], reverse=True):   # walls first, floors over them
        cv.seg(f["x1"], f["y1"], f["x2"], f["y2"], _slope_char(f))
    if spawns:
        for s in m.get("mobs") or []:
            if not s.get("hidden"):
                cv.put(s["x"], s["y"], ".", dy=-1)
    for p in m.get("portals") or []:
        if p.get("toMap", NO_MAP) != NO_MAP:
            cv.put(p["x"], p["y"], "O", dy=-1)
    taken = set()                                   # cells other marks already use: stack upwards instead
    for text, x, y in sorted(marks, key=lambda m: m[0] != "@"):
        c, r = cv.cell(x, y)
        for dy in (-1, -2, -3, -4):
            cells = {(r + dy, c + i) for i in range(len(text))}
            if not cells & taken:
                break
        taken |= cells
        cv.put(x, y, text, dy=dy)
    lines = [cv.text()]
    if ruler:
        rule = [" "] * cv.w
        lab = [" "] * cv.w
        step = 10
        for c in range(0, cv.w, step):
            rule[c] = "+"
            s = str(int(cv.x0 + c * cv.sx))
            for i, ch in enumerate(s):
                if c + i < cv.w:
                    lab[c + i] = ch
        if screen is not None:
            a, b = cv.cell(screen[0], 0)[0], cv.cell(screen[1], 0)[0]
            for c in range(max(0, a), min(cv.w, b + 1)):
                rule[c] = "-"
            if 0 <= a < cv.w:
                rule[a] = "["
            if 0 <= b < cv.w:
                rule[b] = "]"
        lines += ["".join(rule).rstrip(), "".join(lab).rstrip()]
    return "\n".join(lines)


def header(m: dict) -> str:
    x0, y0, x1, y1 = _bounds(m)
    return (f"{m.get('id')} {m.get('streetName', '')} - {m.get('name', '')}   x {x0}..{x1}  y {y0}..{y1}\n"
            "legend: = floor  / \\ slope  # wall  | rope  H ladder  O portal  . spawn  @ us  "
            "Xn> mob track (< > facing, ? unseen, x dying, ^ air)  p pet")
