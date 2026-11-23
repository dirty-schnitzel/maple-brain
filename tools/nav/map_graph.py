"""Draw one map's platform graph (nav/navmap.py) as an abstract directed graph PNG.

Node = a platform (its foothold id), all the same size. Rows = heights (top row = highest; a floor that spans most
of the map gets a row of its own), evenly spaced, left to right as in the map - not the real places.
Edge = one move that touches no third platform (ropes in between are fine), coloured by its group:
  drop       drop through / walk off an edge (down)
  jump       a jump (up, or across)
  rope_up    a rope or ladder to a higher platform
  rope_down  a rope or ladder to a lower one
  rope_leap  a rope, then a jump off it
  walk       two surfaces that meet
Number = NavMap.route's seconds from the MIDDLE of the source platform: on a wide floor that is mostly walking
(a real route starts from where we stand). Walk speed is Nav.walk_speed, a placeholder (config.py).
Platforms nothing leads to (scenery, or a way up navmap does not model) are left out and named under the picture.

  python tools/nav/map_graph.py MAP [--platforms N] [--seed S] [--hide drop,jump] [--8bit] [--out PNG]

MAP = a map id or a name ("Line 1 <Area 1>", or a part of one that names a single map).
--platforms N keeps N platforms, picked arbitrarily: grown from a random platform along the edges (either
direction), so the piece hangs together; --seed makes the pick repeatable. Edges between the kept ones are the
full map's direct moves. --hide leaves those edge groups out (the platforms stay).
--8bit draws the same pick as one-colour 8-bit text art (rings = platforms, lines = moves, no numbers):
printed, and saved as a .txt.
"""
import argparse
import heapq
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from maplebrain.nav.navmap import NavMap  # noqa: E402

ASSETS = ROOT / "assets" / "mcw"
GROUPS = ("drop", "jump", "rope_up", "rope_down", "rope_leap", "walk")
COLOUR = {"drop": (52, 110, 200), "jump": (40, 150, 80), "rope_up": (220, 120, 20),
          "rope_down": (150, 100, 50), "rope_leap": (150, 70, 180), "walk": (120, 120, 120)}
LEGEND = {"drop": "drop / walk off", "jump": "jump", "rope_up": "rope / ladder up", "rope_down": "rope / ladder down",
          "rope_leap": "rope + jump off it", "walk": "walk across"}


def find_map(spec: str, assets: Path = ASSETS) -> int:
    """A map id from an id or a name: an exact name (any case) wins, else the one name that contains it."""
    if spec.isdigit():
        return int(spec)
    names = {}
    for f in (assets / "maps").glob("*/map.json"):
        names[int(f.parent.name)] = json.loads(f.read_text(encoding="utf-8"))["name"]
    exact = [i for i, n in names.items() if n.lower() == spec.lower()]
    part = [i for i, n in names.items() if spec.lower() in n.lower()]
    hits = exact or part
    if len(hits) != 1:
        raise SystemExit(f"'{spec}': {len(hits)} maps match" +
                         ("".join(f"\n  {i} {names[i]}" for i in sorted(hits)[:20]) if hits else ""))
    return hits[0]


def ymid(nm: NavMap, pid: int) -> float:
    p = nm.platforms[pid]
    return p.y_at((p.left + p.right) / 2)


def group(nm: NavMap, src: int, dst: int, kinds: list) -> str:
    if "leap" in kinds:
        return "rope_leap"
    if kinds[0] in ("grab", "descend"):
        return "rope_up" if ymid(nm, dst) < ymid(nm, src) else "rope_down"
    if kinds[0] in ("drop", "fall"):
        return "drop"
    return kinds[0]                                      # jump, walk


def platform_edges(nm: NavMap) -> dict:
    """(src, dst) -> (seconds, group): the cheapest move from src's middle to dst touching no third platform."""
    out = {}
    for a in nm.platforms.values():
        mid = (a.left + a.right) / 2
        for b in nm.platforms.values():
            if b is a:
                continue
            avoid = [k for k in nm.links if not nm.is_rope(k.dst) and k.dst not in (a.id, b.id)]
            r = nm.route(a.id, mid, b.id, avoid=avoid, with_cost=True)
            if r is not None:
                path, c = r
                out[(a.id, b.id)] = (round(c, 1), group(nm, a.id, b.id, [k.kind for k in path]))
    return out


def pick(edges: dict, nodes: list, n: int, seed) -> list:
    """n of nodes, grown from a random one along the edges (either direction) in a random order."""
    if n >= len(nodes):
        return sorted(nodes)
    rnd = random.Random(seed)
    nbr = {i: set() for i in nodes}
    for a, b in edges:
        nbr[a].add(b)
        nbr[b].add(a)
    kept, frontier = set(), []
    while len(kept) < n:
        if not frontier:                                 # start (or a disconnected rest): a random new platform
            frontier = [rnd.choice(sorted(set(nodes) - kept))]
        i = frontier.pop(rnd.randrange(len(frontier)))
        if i in kept:
            continue
        kept.add(i)
        frontier += sorted(nbr[i] - kept)
    return sorted(kept)


def graph(map_id: int, n: int | None = None, seed=None, hide=(), assets: Path = ASSETS):
    """(name, navmap, kept platforms, edges shown, platforms left out as unreachable, reachable count)."""
    nm = NavMap.for_map(map_id, assets)
    name = json.loads((assets / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))["name"]
    E = platform_edges(nm)
    reach = {b for _, b in E}
    E = {k: v for k, v in E.items() if k[0] in reach and k[1] in reach}
    nodes = pick(E, sorted(reach), n or len(reach), seed)
    keep = set(nodes)
    shown = {k: v for k, v in E.items() if k[0] in keep and k[1] in keep and v[1] not in hide}
    return name, nm, nodes, shown, sorted(set(nm.platforms) - reach), len(reach)


def layout(nm: NavMap, nodes: list) -> list:
    """Rows of platform ids, top to bottom: heights within 20 px share a row; a floor gets a row of its own."""
    span = max(p.right for p in nm.platforms.values()) - min(p.left for p in nm.platforms.values())
    wide = lambda i: nm.platforms[i].right - nm.platforms[i].left > 0.6 * span
    rows, last = [], None
    for i in sorted(nodes, key=lambda i: ymid(nm, i)):
        y = ymid(nm, i)
        if last is None or y - last > 20 or wide(i) or wide(rows[-1][-1]):
            rows.append([])
        rows[-1].append(i)
        last = y
    for row in rows:
        row.sort(key=lambda i: nm.platforms[i].left)
    return rows


def pixel_art(rows: list, edges, gap: int = 14, row_h: int = 4) -> list:
    """The graph as 8-bit text art: a platform = a 3 x 3 ring, a move = a 1 px line (both directions as one).

    rows = layout()'s rows of platform ids; edges = (src, dst) pairs. Pixels: rows `row_h` apart, a row's
    platforms `gap` apart and centred, as in the PNG. Two pixel rows per text line, in half blocks.
    """
    width = (max(map(len, rows)) - 1) * gap + 5
    height = (len(rows) - 1) * row_h + 3
    pos = {i: (round((width - 1) / 2 + (j - (len(row) - 1) / 2) * gap), 1 + r * row_h)
           for r, row in enumerate(rows) for j, i in enumerate(row)}
    g = [[False] * width for _ in range(height + height % 2)]
    for a, b in {tuple(sorted(e)) for e in edges}:
        (x0, y0), (x1, y1) = pos[a], pos[b]
        n = max(abs(x1 - x0), abs(y1 - y0))
        for k in range(n + 1):
            g[round(y0 + (y1 - y0) * k / n)][round(x0 + (x1 - x0) * k / n)] = True
    for x, y in pos.values():
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                g[y + dy][x + dx] = bool(dx or dy)       # the ring, hollow in the middle
    half = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}
    return ["".join(half[g[y][x], g[y + 1][x]] for x in range(width)).rstrip() for y in range(0, len(g), 2)]


def draw_8bit(map_id: int, out: Path, n: int | None = None, seed=None, hide=()) -> str:
    """pixel_art of the same pick as draw(), with a caption; written to `out` (UTF-8) and returned."""
    name, nm, nodes, E, _, _ = graph(map_id, n, seed, hide)
    art = "\n".join(pixel_art(layout(nm, nodes), E) + [f" maplebrain · {name}"]) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(art, encoding="utf-8")
    return art


def _font(size, bold=False):
    try:
        return ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _curve(a, b, bend):
    (x1, y1), (x2, y2) = a, b
    L = math.hypot(x2 - x1, y2 - y1)
    nx, ny = (y2 - y1) / L, -(x2 - x1) / L
    cx, cy = (x1 + x2) / 2 + nx * bend, (y1 + y2) / 2 + ny * bend
    return [((1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t * t * x2,
             (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t * t * y2) for t in (k / 60 for k in range(61))]


def draw(map_id: int, out: Path, n: int | None = None, seed=None, hide=()) -> Path:
    name, nm, nodes, E, dropped, n_reach = graph(map_id, n, seed, hide)
    rows = layout(nm, nodes)
    ROWH, GAP, R, TOP = 135, 300, 30, 150
    W = max(1500, max(map(len, rows)) * GAP + 100)
    H = TOP + ROWH * (len(rows) - 1) + 230
    pos = {i: (W / 2 + (j - (len(row) - 1) / 2) * GAP, TOP + r * ROWH)
           for r, row in enumerate(rows) for j, i in enumerate(row)}
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    labels = []
    for (a, b), (c, g) in sorted(E.items(), key=lambda kv: -kv[1][0]):
        pa, pb = pos[a], pos[b]
        L = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        bend = min(max(0.15 * L, 30), 45) if (b, a) in E else min(0.06 * L, 25)
        pts = [p for p in _curve(pa, pb, bend) if math.dist(p, pa) > R and math.dist(p, pb) > R + 2]
        col = COLOUR[g]
        d.line(pts, fill=col, width=2)
        (ex, ey), (fx, fy) = pts[-2], pts[-1]
        ang = math.atan2(fy - ey, fx - ex)
        tip = (fx + 3 * math.cos(ang), fy + 3 * math.sin(ang))
        d.polygon([tip, (tip[0] - 13 * math.cos(ang - 0.38), tip[1] - 13 * math.sin(ang - 0.38)),
                   (tip[0] - 13 * math.cos(ang + 0.38), tip[1] - 13 * math.sin(ang + 0.38))], fill=col)
        labels.append((pts[len(pts) // 2], f"{c:g}", col))
    f = _font(14, True)
    for (x, y), s, col in labels:
        w, h = d.textbbox((0, 0), s, font=f)[2:]
        d.rounded_rectangle([x - w / 2 - 3, y - h / 2 - 3, x + w / 2 + 3, y + h / 2 + 3], 4, fill="white", outline=col)
        d.text((x - w / 2, y - h / 2 - 1), s, font=f, fill=col)
    f = _font(17, True)
    for i, (x, y) in pos.items():
        d.ellipse([x - R, y - R, x + R, y + R], fill=(245, 245, 245), outline=(30, 30, 30), width=3)
        w, h = d.textbbox((0, 0), str(i), font=f)[2:]
        d.text((x - w / 2, y - h / 2 - 2), str(i), font=f, fill=(20, 20, 20))
    total = f"{len(nodes)} of {n_reach}" if len(nodes) < n_reach else len(nodes)
    d.text((40, 30), f"{name}  (map {map_id})", font=_font(30, True), fill=(20, 20, 20))
    sub = f"{total} platforms, {len(E)} directed edges" + (f", seed {seed}" if len(nodes) < n_reach else "") + \
          (f"; hidden: {', '.join(hide)}" if hide else "") + ". Node = platform (its foothold id); rows = height."
    d.text((40, 72), sub, font=_font(15), fill=(70, 70, 70))
    d.text((40, 94), "Edge = one move that touches no third platform (ropes in between are OK); number = "
           "NavMap.route seconds from the middle of the source platform.", font=_font(15), fill=(70, 70, 70))
    lx, used = 40, {g for _, g in E.values()}
    for g in GROUPS:
        if g in used:
            d.line([(lx, H - 40), (lx + 40, H - 40)], fill=COLOUR[g], width=4)
            d.text((lx + 50, H - 50), LEGEND[g], font=_font(16), fill=COLOUR[g])
            lx += 240
    if dropped:
        d.text((40, H - 85), "left out, nothing leads there: " + ", ".join(map(str, dropped)), font=_font(14),
               fill=(120, 120, 120))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("map", help="a map id or name")
    ap.add_argument("--platforms", type=int, help="keep this many platforms, picked arbitrarily")
    ap.add_argument("--seed", type=int, help="makes the --platforms pick repeatable (default: random)")
    ap.add_argument("--hide", default="", help="edge groups to leave out, comma separated: " + ", ".join(GROUPS))
    ap.add_argument("--8bit", dest="eightbit", action="store_true",
                    help="8-bit text art instead of the PNG: printed, and saved as a .txt")
    ap.add_argument("--out", type=Path, help="the PNG or .txt (default runs/map_graph/<map id>.png / .txt)")
    a = ap.parse_args(argv)
    hide = tuple(h.strip() for h in a.hide.split(",") if h.strip())
    bad = [h for h in hide if h not in GROUPS]
    if bad:
        ap.error(f"unknown group(s) {bad}: the groups are {', '.join(GROUPS)}")
    map_id = find_map(a.map)
    seed = a.seed if a.seed is not None else (random.randrange(10_000) if a.platforms else None)
    out = a.out or ROOT / "runs" / "map_graph" / (f"{map_id}" + (f"_{a.platforms}p_s{seed}" if a.platforms else "")
                                                  + (f"_no-{'-'.join(hide)}" if hide else "")
                                                  + (".txt" if a.eightbit else ".png"))
    if a.eightbit:
        sys.stdout.reconfigure(encoding="utf-8")
        print(draw_8bit(map_id, out, a.platforms, seed, hide) + str(out))
    else:
        print(draw(map_id, out, a.platforms, seed, hide))


if __name__ == "__main__":
    main()
