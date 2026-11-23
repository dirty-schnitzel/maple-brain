"""Draw one map's platform graph (nav/navmap.py) as an abstract directed graph PNG.

Node = a platform (its foothold id), all the same size. Rows = heights (top row = highest; a floor that spans most
of the map gets a row of its own), evenly spaced, left to right as in the map - not the real places.
--layout map instead puts each node at its platform's middle on the map, one scale for both axes (equal heights
stay level, the order and the relative distances are kept), over a grey bar = the platform's extent.
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

  python tools/nav/map_graph.py MAP [--platforms N] [--seed S] [--hide drop,jump] [--layout rows|map] [--8bit | --banner] [--out PNG]
  python tools/nav/map_graph.py --random 10 --hide drops --8bit --platforms 5 --layout map

MAP = a map id or a name ("Line 1 <Area 1>", or a part of one that names a single map).
--platforms N keeps N platforms, picked arbitrarily: grown from a random platform along the edges (either
direction), so the piece hangs together; --seed makes the pick repeatable. Edges between the kept ones are the
full map's direct moves. --hide leaves those edge groups out (the platforms stay; plurals such as "drops" work).
--random N draws N random maps (at least 5 platforms, or --platforms, and an edge left) with the other options,
each with its own seed; with --8bit all the pictures are printed together at the end.
--8bit draws the same pick as one-colour 8-bit text art (rings = platforms, lines = moves, no numbers):
printed with a caption, and the art alone saved as a .txt. --banner does the same into the session banner's
folder, .claude/skills/draw-map/8bit/<map name>.txt: the maple-banner mod shows a random file of it at session
start, titled by its file name.
"""
import argparse
import heapq
import json
import math
import random
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from maplebrain.nav.navmap import NavMap  # noqa: E402

ASSETS = ROOT / "assets" / "mcw"
BANNER = ROOT / ".claude" / "skills" / "draw-map" / "8bit"  # the maple-banner mod picks one at session start
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
    name = map_name(map_id, assets)
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
    return _pixels(pos, edges, width, height)


def pixel_art_map(boxes: dict, edges, width: int = 42, height: int = 32) -> list:
    """pixel_art with the platforms placed as on the map (map_positions, boxes = {id: (left, right, y)}), scaled
    into about `width` x `height` pixels; close platforms' rings may touch."""
    pos, _, w, h = map_positions(boxes, top=1, width=width, max_h=height, margin=1)
    pos = {i: (round(x), round(y)) for i, (x, y) in pos.items()}
    return _pixels(pos, edges, w + 1, max(y for _, y in pos.values()) + 2)


def _pixels(pos: dict, edges, width: int, height: int) -> list:
    """Rings at `pos` (pixel x, y), 1 px lines between them, as half-block text lines."""
    g = [[False] * width for _ in range(height + height % 2)]
    for a, b in {tuple(sorted(e)) for e in edges}:
        (x0, y0), (x1, y1) = pos[a], pos[b]
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for k in range(n + 1):
            g[round(y0 + (y1 - y0) * k / n)][round(x0 + (x1 - x0) * k / n)] = True
    for x, y in pos.values():
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                g[y + dy][x + dx] = bool(dx or dy)       # the ring, hollow in the middle
    half = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}
    return ["".join(half[g[y][x], g[y + 1][x]] for x in range(width)).rstrip() for y in range(0, len(g), 2)]


def map_name(map_id: int, assets: Path = ASSETS) -> str:
    return json.loads((assets / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))["name"]


SHORT = {"Hunting Ground": "HG", "Construction Site": "CS", "City": ""}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def short_name(name: str) -> str:
    """A map's name for the banner: phrases of SHORT abbreviated, a last Roman numeral as a digit, glued to an
    abbreviation ("Henesys Hunting Ground I" -> "Henesys HG1"), and without what Windows refuses in a file name."""
    for long, short in SHORT.items():
        name = re.sub(rf"\b{long}\b", short, name)
    words = re.sub(r'[<>:"/\\|?*]', " ", name).split()
    if len(words) > 1 and words[-1] in ROMAN:
        digit = str(ROMAN[words.pop()])
        words[-1] += digit if words[-1] in SHORT.values() else " " + digit
    return " ".join(words)


def banner_file(name: str) -> Path:
    """The session banner's picture of a map: BANNER/<short name>.txt (the banner's title is the file name)."""
    return BANNER / f"{short_name(name)}.txt"


def draw_8bit(map_id: int, out: Path, n: int | None = None, seed=None, hide=(), mode: str = "rows") -> str:
    """pixel_art (or pixel_art_map) of the same pick as draw(): the art alone written to `out` (UTF-8, the session
    banner's format: .claude/skills/draw-map/8bit/<map name>.txt), returned with a caption under it."""
    name, nm, nodes, E, _, _ = graph(map_id, n, seed, hide)
    if mode == "map":
        boxes = {i: (nm.platforms[i].left, nm.platforms[i].right, ymid(nm, i)) for i in nodes}
        rows = pixel_art_map(boxes, E)
    else:
        rows = pixel_art(layout(nm, nodes), E)
    art = "\n".join(rows) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(art, encoding="utf-8", newline="\n")
    return art + f" neuromaple · {name}\n"


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


def map_positions(boxes: dict, top: float, width: int = 1500, max_h: int = 1600, margin: int = 80):
    """--layout map: each platform where it is on the map, one scale for both axes (never above 1:1), so equal
    heights stay level, the left-to-right order and the relative distances are kept.

    boxes = {id: (left, right, y)} in map px; -> ({id: (x, y)} = the platform's middle, {id: (x_left, x_right)},
    the picture's width, the drawing's height)."""
    x0 = min(l for l, _, _ in boxes.values())
    x1 = max(r for _, r, _ in boxes.values())
    y0 = min(y for _, _, y in boxes.values())
    y1 = max(y for _, _, y in boxes.values())
    s = min(1.0, (width - 2 * margin) / max(x1 - x0, 1), max_h / max(y1 - y0, 1))
    pos = {i: (margin + ((l + r) / 2 - x0) * s, top + (y - y0) * s) for i, (l, r, y) in boxes.items()}
    span = {i: (margin + (l - x0) * s, margin + (r - x0) * s) for i, (l, r, _) in boxes.items()}
    return pos, span, max(width, round((x1 - x0) * s) + 2 * margin), (y1 - y0) * s


def draw(map_id: int, out: Path, n: int | None = None, seed=None, hide=(), mode: str = "rows") -> Path:
    name, nm, nodes, E, dropped, n_reach = graph(map_id, n, seed, hide)
    R, TOP, span = 30, 150, {}
    if mode == "map":
        R = 17                                            # real places can be close: smaller nodes
        boxes = {i: (nm.platforms[i].left, nm.platforms[i].right, ymid(nm, i)) for i in nodes}
        pos, span, W, h = map_positions(boxes, TOP)
        H = round(TOP + h + 230)
    else:
        rows = layout(nm, nodes)
        ROWH, GAP = 135, 300
        W = max(1500, max(map(len, rows)) * GAP + 100)
        H = TOP + ROWH * (len(rows) - 1) + 230
        pos = {i: (W / 2 + (j - (len(row) - 1) / 2) * GAP, TOP + r * ROWH)
               for r, row in enumerate(rows) for j, i in enumerate(row)}
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    for i, (xl, xr) in span.items():                   # map layout: the platform's real extent behind its node
        d.line([(xl, pos[i][1]), (xr, pos[i][1])], fill=(205, 205, 205), width=8)
    labels = []
    for (a, b), (c, g) in sorted(E.items(), key=lambda kv: -kv[1][0]):
        pa, pb = pos[a], pos[b]
        L = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        bend = min(max(0.15 * L, 30), 45) if (b, a) in E else min(0.06 * L, 25)
        if L == 0:                                        # map layout: two platforms with one middle
            continue
        curve = _curve(pa, pb, bend)
        pts = [p for p in curve if math.dist(p, pa) > R and math.dist(p, pb) > R + 2]
        if len(pts) < 2:                                  # map layout: nodes that touch - the whole curve
            pts = curve
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
    f = _font(12 if mode == "map" else 17, True)
    for i, (x, y) in pos.items():
        d.ellipse([x - R, y - R, x + R, y + R], fill=(245, 245, 245), outline=(30, 30, 30), width=3)
        w, h = d.textbbox((0, 0), str(i), font=f)[2:]
        d.text((x - w / 2, y - h / 2 - 2), str(i), font=f, fill=(20, 20, 20))
    total = f"{len(nodes)} of {n_reach}" if len(nodes) < n_reach else len(nodes)
    d.text((40, 30), f"{name}  (map {map_id})", font=_font(30, True), fill=(20, 20, 20))
    sub = f"{total} platforms, {len(E)} directed edges" + (f", seed {seed}" if len(nodes) < n_reach else "") + \
          (f"; hidden: {', '.join(hide)}" if hide else "") + ". Node = platform (its foothold id); " + \
          ("placed as on the map, to scale; grey bar = the platform's extent." if mode == "map" else "rows = height.")
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


ALIAS = {"drops": "drop", "walk_off": "drop", "walkoff": "drop", "jumps": "jump", "walks": "walk",
         "ropes_up": "rope_up", "ropes_down": "rope_down", "rope_leaps": "rope_leap", "leap": "rope_leap"}


def random_maps(count: int, n: int | None, hide=(), assets: Path = ASSETS):
    """`count` random map ids whose graph has at least max(n, 5) platforms and an edge left after `hide`."""
    ids = sorted(int(p.parent.name) for p in (assets / "maps").glob("*/map.json"))
    random.shuffle(ids)
    for mid in ids:
        if count == 0:
            return
        try:
            _, _, _, E, _, n_reach = graph(mid, n, random.randrange(10_000), hide, assets)
        except Exception:                                 # no navmap (towns' insides, cut scenes)
            continue
        if n_reach >= max(n or 0, 5) and E:
            count -= 1
            yield mid


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("map", nargs="?", help="a map id or name (none with --random)")
    ap.add_argument("--random", type=int, metavar="N",
                    help="N random maps instead of MAP, each with its own seed; with --8bit every art is printed "
                         "again at the end")
    ap.add_argument("--platforms", type=int, help="keep this many platforms, picked arbitrarily")
    ap.add_argument("--seed", type=int, help="makes the --platforms pick repeatable (default: random)")
    ap.add_argument("--hide", default="", help="edge groups to leave out, comma separated: " + ", ".join(GROUPS))
    ap.add_argument("--8bit", dest="eightbit", action="store_true",
                    help="8-bit text art instead of the PNG: printed, and saved as a .txt")
    ap.add_argument("--banner", action="store_true",
                    help="--8bit, saved into the session banner's folder as <map name>.txt (replaces that map's)")
    ap.add_argument("--layout", choices=("rows", "map"), default="rows",
                    help="the PNG's node places: rows (by height, evenly spaced; the default) or map (as on the map, "
                         "to scale)")
    ap.add_argument("--out", type=Path, help="the PNG or .txt (default runs/map_graph/<map id>.png / .txt)")
    a = ap.parse_args(argv)
    hide = tuple(dict.fromkeys(ALIAS.get(h.strip().replace(" ", "_").replace("-", "_"), h.strip())
                               for h in a.hide.split(",") if h.strip()))
    bad = [h for h in hide if h not in GROUPS]
    if bad:
        ap.error(f"unknown group(s) {bad}: the groups are {', '.join(GROUPS)}")
    if (a.map is None) == (a.random is None):
        ap.error("give a MAP or --random N")
    if a.random is not None and (a.seed is not None or a.out or a.banner):
        ap.error("--random picks its own maps and seeds: no --seed, --out or --banner")
    a.eightbit = a.eightbit or a.banner
    if a.eightbit:
        sys.stdout.reconfigure(encoding="utf-8")
    arts = []
    for map_id in random_maps(a.random, a.platforms, hide) if a.random else [find_map(a.map)]:
        seed = a.seed if a.seed is not None else (random.randrange(10_000) if a.platforms else None)
        out = a.out or (banner_file(map_name(map_id)) if a.banner else
                        ROOT / "runs" / "map_graph" / (f"{map_id}" + (f"_{a.platforms}p_s{seed}" if a.platforms else "")
                                                       + (f"_no-{'-'.join(hide)}" if hide else "")
                                                       + ("_map" if a.layout == "map" else "")
                                                       + (".txt" if a.eightbit else ".png")))
        if a.eightbit:
            art = draw_8bit(map_id, out, a.platforms, seed, hide, a.layout)
            arts.append(f"--- {map_id}" + (f", seed {seed}" if seed is not None else "") + f"\n{art}")
            print(art + str(out))
        else:
            print(draw(map_id, out, a.platforms, seed, hide, a.layout))
    if a.random and arts:
        print("\n========== the 8-bit pictures ==========\n" + "\n".join(arts))


if __name__ == "__main__":
    main()
