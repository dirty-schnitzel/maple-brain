"""Livemap v2 prototype (PLAN-livemap.md, 2026-11-17): the whole map as a PICTURE with the data model drawn on it.

Evidence for the plan and the reference to productionize - not the product (nothing in maplebrain/ reads it).
Run from the repo root with the venv python; pictures go to runs/tmp_livemap/ (runs/ is not committed).

    proto.py base MAP ...            the whole-map picture of each MAP from the scene model, on the CPU: time + PNG
    proto.py shot ROWS N [--view V]  one row of a replay (tools/perc/replay: RUN/replay/*.jsonl) or of a ticks.jsonl
                                     drawn: V = map (whole map, default) | cam (the bot's screen at 1:1, over the
                                     recorded frame if the run has it)
    proto.py cuts ROWS               a sheet of our character cut from the rows where we stand alone (pick by eye)
    proto.py cut ROWS N --facing F   our character cut out of row N's recorded frame (frame - expected scene) ->
                                     player.png + player.json (origin = the feet, facing)
    proto.py bench ROWS [--view V]   draw + JPEG time per row
    proto.py play ROWS [--speed S]   the rows at real speed as a PAGE (http://127.0.0.1:8765/, MJPEG): no window of
                                     ours, so nothing can take the keyboard focus from the game (and this venv's
                                     cv2 is headless: cv2.imshow / namedWindow do not exist)

Draw time needs numpy + cv2 only; torch is used ONCE per map (the scene model on the CPU) to make the base picture.
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / "assets" / "mcw"
OUT = ROOT / "runs" / "tmp_livemap"
PLAYER = Path(__file__).resolve().parent / "player.png"         # our character (cut 2026-11-17, see `cut`)
W, H, PLAY_H = 1366, 768, 700


# ------------------------------------------------------------------ the base picture (once per map)
def base_picture(map_id: int):
    """(bgr uint8 (h, w, 3), (x0, y0)) of the whole map: tiles + objects over the background layers as ONE camera
    with the map's size would see them (the scene model's expected(), CPU). Map (x, y) is pixel (x - x0, y - y0)."""
    from maplebrain.scene import Scene
    sc = Scene.load(map_id, device="cpu")
    out, _ = sc.expected((sc.x0, sc.y0), sc.meta["w"], sc.meta["h"], pre=False)
    return np.clip(out.numpy() + 0.5, 0, 255).astype(np.uint8), (sc.x0, sc.y0)


def lines_picture(map_id: int):
    """The fallback without a scene: footholds and ropes as lines on a dark picture (map.json only)."""
    m = json.loads((ASSETS / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
    fh = list((m.get("footholds") or {}).values())
    xs = [v for f in fh for v in (f["x1"], f["x2"])]
    ys = [v for f in fh for v in (f["y1"], f["y2"])]
    x0, y0 = min(xs) - 200, min(ys) - 200
    img = np.full((max(ys) + 200 - y0, max(xs) + 200 - x0, 3), 32, np.uint8)
    for f in fh:
        cv2.line(img, (f["x1"] - x0, f["y1"] - y0), (f["x2"] - x0, f["y2"] - y0), (200, 200, 200), 2)
    for r in m.get("ladderRopes") or []:
        cv2.line(img, (r["x"] - x0, r["y1"] - y0), (r["x"] - x0, r["y2"] - y0), (60, 160, 220), 2)
    return img, (x0, y0)


# ------------------------------------------------------------------ sprites
class Sprites:
    """Mob frames from assets/mcw/mobs (RGBA, facing left) at one scale, cached per (mob, anim, n, facing) as
    (premultiplied bgr float32, 1 - alpha, origin x, origin y)."""

    def __init__(self, scale: float = 1.0):
        self.scale, self.info, self.link, self.cache = scale, {}, {}, {}

    def book(self, mob: int, anim: str) -> list:
        if mob not in self.info:
            f = ASSETS / "mobs" / str(mob) / "mob.json"
            m = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            self.info[mob], self.link[mob] = m.get("frames") or {}, m.get("link")
        b = self.info[mob]
        return b.get(anim) or b.get("stand") or b.get("move") or b.get("fly") or []

    def picture(self, mob: int, f: dict):
        """A frame's RGBA picture, following the client's links as perception/vote.py `_pic` does: a 1x1 placeholder
        (221 of 2154 frames) -> its `_inlink` frame ("anim/i") of the same mob, then the linked mob's files."""
        names = [f["file"]]
        anim, _, i = str(f.get("_inlink") or "").partition("/")
        tgt = self.info[mob].get(anim) or []
        if i.isdigit() and int(i) < len(tgt):
            names.append(tgt[int(i)]["file"])
        for d in (mob, self.link.get(mob)):
            for nm in names if d is not None else []:
                im = cv2.imread(str(ASSETS / "mobs" / str(d) / nm), cv2.IMREAD_UNCHANGED)
                if im is not None and im.ndim == 3 and im.shape[2] == 4 and min(im.shape[:2]) > 1:
                    return im
        return None

    def frame_at(self, mob: int, anim: str, t: float) -> int:
        """Which frame of the animation shows at time t (the client's delays, looped)."""
        delays = [int(f.get("delay") or 100) for f in self.book(mob, anim)]   # mob.json: int, "200" or None
        if not delays:
            return 0
        ms = (t * 1000) % sum(delays)
        for i, d in enumerate(delays):
            ms -= d
            if ms < 0:
                return i
        return 0

    def get(self, mob: int, anim: str, n: int, facing: str):
        key = (mob, anim, n, facing)
        if key not in self.cache:
            book = self.book(mob, anim)
            pic = None
            if book:
                f = book[min(n, len(book) - 1)]
                im = self.picture(mob, f)
                if im is not None:
                    pic = prep(im, f["origin"], facing == "right", self.scale)
            self.cache[key] = pic
        return self.cache[key]


def prep(rgba, origin, flip: bool, scale: float):
    """An RGBA picture -> (premultiplied bgr float32, 1 - alpha (h, w, 1), ox, oy) at `scale`."""
    ox, oy = origin
    if flip:
        rgba, ox = rgba[:, ::-1], rgba.shape[1] - ox
    pm = rgba[..., :3].astype(np.float32) * (rgba[..., 3:4].astype(np.float32) / 255.0)
    a = rgba[..., 3].astype(np.float32) / 255.0
    if scale != 1.0:
        size = (max(1, round(rgba.shape[1] * scale)), max(1, round(rgba.shape[0] * scale)))
        pm, a = cv2.resize(pm, size, interpolation=cv2.INTER_AREA), cv2.resize(a, size, interpolation=cv2.INTER_AREA)
        ox, oy = ox * scale, oy * scale
    return np.ascontiguousarray(pm), np.ascontiguousarray(1.0 - a)[..., None], ox, oy


def blit(img, pic, x: float, y: float, opacity: float = 1.0) -> None:
    """Draw a prepared picture with its origin at pixel (x, y) of `img` (uint8 bgr), clipped."""
    if pic is None:
        return
    pm, inv, ox, oy = pic
    h, w = pm.shape[:2]
    px, py = int(round(x - ox)), int(round(y - oy))
    x0, y0, x1, y1 = max(0, px), max(0, py), min(img.shape[1], px + w), min(img.shape[0], py + h)
    if x1 <= x0 or y1 <= y0:
        return
    s, k = pm[y0 - py:y1 - py, x0 - px:x1 - px], inv[y0 - py:y1 - py, x0 - px:x1 - px]
    dst = img[y0:y1, x0:x1]
    if opacity < 1.0:
        s, k = s * opacity, 1.0 - (1.0 - k) * opacity
    dst[:] = (s + dst * k + 0.5).astype(np.uint8)


# ------------------------------------------------------------------ rows (one record of the data model)
def norm(row: dict) -> dict:
    """A ticks.jsonl record or a replay row -> {t, cam, me, mobs, tags, own_tag, frame} (map coordinates; tags on
    screen)."""
    o = row.get("obs") or row
    facts = row.get("facts") or {}
    return {"t": o.get("t", 0.0), "cam": o.get("cam"), "me": o.get("me_map") or o.get("map_pos"),
            "mobs": o.get("mobs") or [], "tags": facts.get("tags") or [], "own_tag": facts.get("tag"),
            "frame": row.get("frame"), "n": row.get("n")}


def read_rows(path: Path) -> list:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def run_of(path: Path) -> Path:
    return path.parent.parent if path.parent.name == "replay" else path.parent


def map_of(path: Path) -> int:
    return int((run_of(path) / "log.txt").read_text(encoding="utf-8", errors="replace").split()[1])


# ------------------------------------------------------------------ the view
class View:
    def __init__(self, map_id: int, view: str = "map", fit=(1500, 900), player: Path | None = PLAYER,
                 boost: float = 1.8, margin: int = 60):
        """Both views of one map. `view`: "map" (the whole map, scaled to `fit` = largest width, height) or "cam"
        (the bot's screen 1:1) - settable any time (`self.view`); `boost`: sprites drawn that much bigger than the
        whole-map view's scale (never over 1:1); `margin`: px of map kept around vrBounds in the whole-map view."""
        t = time.perf_counter()
        try:
            self.base, (self.bx, self.by) = base_picture(map_id)
        except FileNotFoundError:
            self.base, (self.bx, self.by) = lines_picture(map_id)
        self.base_ms = (time.perf_counter() - t) * 1000
        self.view, self.boost = view, boost
        vr = json.loads((ASSETS / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8")).get("vrBounds") or {}
        h, w = self.base.shape[:2]                               # the whole map = vrBounds + a margin, not the pad
        a = max(0, vr.get("left", self.bx) - margin - self.bx)
        b = max(0, vr.get("top", self.by) - margin - self.by)
        c = min(w, vr.get("right", self.bx + w) + margin - self.bx)
        d = min(h, vr.get("bottom", self.by + h) + margin - self.by)
        if c - a < 200 or d - b < 200:
            a, b, c, d = 0, 0, w, h
        self.mx, self.my = self.bx + a, self.by + b              # the whole-map view's top-left on the map
        self.ms = min(1.0, fit[0] / (c - a), fit[1] / (d - b))   # ... and its scale
        self.small = cv2.resize(self.base[b:d, a:c], (round((c - a) * self.ms), round((d - b) * self.ms)),
                                interpolation=cv2.INTER_AREA)
        self.sets = {}                                           # scale -> (Sprites, our character's pictures)
        self.player_file = player if player is not None and Path(player).exists() else None
        self.me_x, self.me_face = None, "left"

    def _set(self, scale: float):
        if scale not in self.sets:
            pl = None
            if self.player_file is not None:
                im = cv2.imread(str(self.player_file), cv2.IMREAD_UNCHANGED)
                meta = json.loads(Path(self.player_file).with_suffix(".json").read_text(encoding="utf-8"))
                pl = {f: prep(im, meta["origin"], f != meta["facing"], scale) for f in ("left", "right")}
            self.sets[scale] = (Sprites(scale), pl)
        return self.sets[scale]

    def draw(self, r: dict):
        cam = r["cam"]
        if self.view == "cam":                                   # the bot's screen: a crop of the base at the camera
            img = np.zeros((PLAY_H, W, 3), np.uint8)
            if cam is None:
                return img
            s, ss, ox, oy = 1.0, 1.0, int(cam[0]), int(cam[1])
            ax, ay = ox - self.bx, oy - self.by
            x0, y0, x1, y1 = max(0, ax), max(0, ay), min(self.base.shape[1], ax + W), min(self.base.shape[0], ay + PLAY_H)
            if x1 > x0 and y1 > y0:
                img[y0 - ay:y1 - ay, x0 - ax:x1 - ax] = self.base[y0:y1, x0:x1]
        else:
            img, s, ox, oy = self.small.copy(), self.ms, self.mx, self.my
            ss = min(1.0, s * self.boost)
        sprites, player = self._set(ss)

        def px(x, y):                                            # map -> this picture
            return (x - ox) * s, (y - oy) * s

        for m in sorted(r["mobs"], key=lambda m: m["y"]):
            if m.get("state") == "tentative" or m.get("kind") == "pet":
                continue
            anim = m.get("anim") or "stand"
            n = sprites.frame_at(m["mob"], anim, r["t"] + m["id"] * 0.37)
            x, y = px(m["x"], m["y"])
            unseen = m.get("unseen", 0) > 0.3                    # coasting: believed, not seen right now
            blit(img, sprites.get(m["mob"], anim, n, m.get("facing", "left")), x, y,
                 (0.45 if unseen else 1.0) * (0.7 if m.get("state") == "dying" else 1.0))
            if unseen:
                cv2.putText(img, "?", (int(x) - 4, int(y - 60 * ss)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                            cv2.LINE_AA)
        for tg in r["tags"]:                                     # other characters: a tag is centred under the feet
            if cam is None or (r["own_tag"] and abs(tg[0] - r["own_tag"][0]) < 8 and abs(tg[1] - r["own_tag"][1]) < 8):
                continue
            x, y = px(tg[0] + tg[2] / 2 + cam[0], tg[1] - 2 + cam[1])
            self.person(img, player, ss, x, y, "left", (200, 200, 200), 0.6)
        if r["me"] is not None:
            if self.me_x is not None and abs(r["me"][0] - self.me_x) >= 2:
                self.me_face = "right" if r["me"][0] > self.me_x else "left"
            self.me_x = r["me"][0]
            x, y = px(*r["me"])
            self.person(img, player, ss, x, y, self.me_face, (80, 255, 255), 1.0)
            if self.view != "cam":                               # where we are, at a glance
                hx, hy = int(x), int(y - 78 * ss)
                cv2.fillPoly(img, [np.array([(hx - 5, hy - 8), (hx + 5, hy - 8), (hx, hy)])], (80, 255, 255), cv2.LINE_AA)
        if self.view != "cam" and cam is not None:               # what the game shows right now
            a, b = px(cam[0], cam[1]), px(cam[0] + W, cam[1] + H)
            cv2.rectangle(img, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (255, 255, 255), 1, cv2.LINE_AA)
        return img

    @staticmethod
    def person(img, player, ss, x, y, facing, colour, opacity):
        if player is not None:
            blit(img, player[facing], x, y, opacity)
        else:                                                    # no sprite: a marker of a character's size
            cv2.rectangle(img, (int(x - 14 * ss), int(y - 62 * ss)), (int(x + 14 * ss), int(y)), colour, -1)


# ------------------------------------------------------------------ the page (no window: nothing can take the focus)
PAGE = (b'<!doctype html><title>livemap</title><body style="margin:0;background:#111;color:#ccc;font:14px sans-serif">'
        b'<div style="padding:4px"><a style="color:#8cf" href="/view/map">whole map</a> | '
        b'<a style="color:#8cf" href="/view/cam">the bot\'s screen</a></div>'
        b'<img src="/stream" style="max-width:100%"></body>')


def serve_page(view: View, frames, host: str = "127.0.0.1", port: int = 8765, quality: int = 85) -> list:
    """Serve `frames` (an iterator of drawn pictures, paced by the caller) as a page: / = the page, /stream = MJPEG
    (multipart JPEG: any browser shows it in an <img>), /view/map and /view/cam switch the view. -> JPEG ms."""
    latest = {"jpg": None, "n": 0}
    new = threading.Condition()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/view/"):
                view.view = "cam" if self.path.endswith("cam") else "map"
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                seen = -1
                try:
                    while True:
                        with new:
                            new.wait_for(lambda: latest["n"] != seen, timeout=5)
                            seen, jpg = latest["n"], latest["jpg"]
                        if jpg is not None:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                             + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                except OSError:                                  # the browser went away
                    pass
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(PAGE)

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"livemap: http://{host}:{port}/", flush=True)
    enc = []
    try:
        for img in frames:
            t = time.perf_counter()
            jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
            enc.append((time.perf_counter() - t) * 1000)
            with new:
                latest["jpg"], latest["n"] = jpg, latest["n"] + 1
                new.notify_all()
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    return enc


# ------------------------------------------------------------------ our character, cut from a recorded frame
def cut_player(run: Path, r: dict, sc, tol: int = 4):
    """(RGBA cut, origin (x, y) = the feet inside it) of our character on row r's recorded frame: the biggest blob
    of our body box that the scene `sc` (a CPU Scene) does not explain; the name tag's place under the feet is left
    out. None if there is no blob."""
    frame = cv2.imread(str(run / "frames" / r["frame"]))
    exp, _ = sc.expected(r["cam"], W, PLAY_H, pre=False)
    d = np.abs(frame[:PLAY_H].astype(np.float32) - exp.numpy()).max(axis=2) > tol
    fx, fy = int(r["me"][0] - r["cam"][0]), int(r["me"][1] - r["cam"][1])
    x0, y0, x1, y1 = max(0, fx - 85), max(0, fy - 95), min(W, fx + 70), min(PLAY_H, fy + 20)
    box = d[y0:y1, x0:x1].astype(np.uint8)
    box[fy + 3 - y0:, max(0, fx - 60 - x0):fx + 60 - x0] = 0     # the name tag (centred under the feet)
    n, lab, st, _ = cv2.connectedComponentsWithStats(box, connectivity=8)
    if n < 2:
        return None
    keep = np.zeros_like(box)
    keep[lab == 1 + int(np.argmax(st[1:, 4]))] = 255             # the biggest blob = the body
    cnt, _ = cv2.findContours(keep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(keep, cnt, -1, 255, -1)                     # holes inside the outline belong to it
    ys, xs = np.nonzero(keep)
    a, b, c, e = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    rgba = np.dstack([frame[y0 + b:y0 + e, x0 + a:x0 + c], keep[b:e, a:c]])
    return rgba, (int(fx - (x0 + a)), int(fy - (y0 + b)))


def on_pink(rgba, k: int = 3):
    big = cv2.resize(rgba, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
    al = big[..., 3:4] / 255.0
    return (big[..., :3] * al + np.array((255, 0, 255)) * (1 - al)).astype(np.uint8)


def standing(rows: list, still: int = 5, clear: int = 140) -> list:
    """Rows where we have not moved for `still` rows and no mob is within `clear` px: our character alone."""
    out = []
    for i in range(still, len(rows)):
        r = rows[i]
        if not r["me"] or not r["cam"] or not r["frame"]:
            continue
        if any(not p["me"] or p["me"] != r["me"] for p in rows[i - still:i]):
            continue
        if min((abs(m["x"] - r["me"][0]) + abs(m["y"] - r["me"][1]) for m in r["mobs"]), default=9999) >= clear:
            out.append(r)
    return out


# ------------------------------------------------------------------ commands
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("base")
    b.add_argument("maps", type=int, nargs="+")
    for name in ("shot", "cut", "cuts", "bench", "play"):
        p = sub.add_parser(name)
        p.add_argument("rows", type=Path)
        if name in ("shot", "cut"):
            p.add_argument("n", type=int)
        p.add_argument("--view", default="map")
        p.add_argument("--player", type=Path, default=PLAYER)
        p.add_argument("--speed", type=float, default=1.0)
        p.add_argument("--boost", type=float, default=1.8)
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--facing", default="left", help="cut: which way the character looks on that frame")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd == "base":
        for mid in a.maps:
            t = time.perf_counter()
            img, _ = base_picture(mid)
            ms = (time.perf_counter() - t) * 1000
            cv2.imwrite(str(OUT / f"base_{mid}.png"), img)
            cv2.imwrite(str(OUT / f"base_{mid}_small.png"), cv2.resize(img, None, fx=0.35, fy=0.35,
                                                                       interpolation=cv2.INTER_AREA))
            print(f"map {mid}: {img.shape[1]}x{img.shape[0]} in {ms:.0f} ms")
        return
    rows = [norm(x) for x in read_rows(a.rows)]
    mid, run = map_of(a.rows), run_of(a.rows)
    if a.cmd in ("cut", "cuts"):
        from maplebrain.scene import Scene
        sc = Scene.load(mid, device="cpu")
        if a.cmd == "cuts":                                      # a sheet of the narrowest cuts: pick one by eye
            got = []
            for r in standing(rows):
                c = cut_player(run, r, sc)
                if c is not None and c[0].shape[0] >= 55:
                    got.append((c[0].shape[1], r["n"], c[0]))
            got.sort(key=lambda g: g[0])
            tiles = []
            for _, n_, rgba in got[:12]:
                t = np.full((330, 480, 3), (255, 0, 255), np.uint8)
                im = on_pink(rgba)[:300, :480]
                t[30:30 + im.shape[0], :im.shape[1]] = im
                cv2.putText(t, f"n={n_} {rgba.shape[1]}x{rgba.shape[0]}", (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                tiles.append(t)
            if tiles:
                while len(tiles) % 4:
                    tiles.append(np.full_like(tiles[0], 255))
                cv2.imwrite(str(OUT / f"cuts_{mid}.png"), np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]))
            print(f"{len(got)} cuts, widths {[g[0] for g in got[:12]]} -> {OUT / f'cuts_{mid}.png'}")
            return
        r = next(x for x in rows if x["n"] == a.n)
        rgba, origin = cut_player(run, r, sc)
        cv2.imwrite(str(OUT / "player.png"), rgba)
        (OUT / "player.json").write_text(json.dumps({"origin": list(origin), "facing": a.facing,
                                                     "from": f"{run.name} n={a.n}"}), encoding="utf-8")
        cv2.imwrite(str(OUT / "player_x4.png"), on_pink(rgba, 4))
        print(f"{OUT / 'player.png'} {rgba.shape[1]}x{rgba.shape[0]}, origin {origin}, facing {a.facing}")
        return
    view = View(mid, a.view, player=a.player, boost=a.boost)
    print(f"map {mid}: base {view.base.shape[1]}x{view.base.shape[0]} in {view.base_ms:.0f} ms, "
          f"whole-map view {view.small.shape[1]}x{view.small.shape[0]} (scale {view.ms:.3f})")
    if a.cmd == "shot":
        for p in (x for x in rows if a.n - 40 <= x["n"] < a.n):  # our facing comes from our last steps
            view.draw(p)
        r = next(x for x in rows if x["n"] == a.n)
        img = view.draw(r)
        if a.view == "cam" and r["frame"] and (run / "frames" / r["frame"]).exists():
            img = np.vstack([img, cv2.imread(str(run / "frames" / r["frame"]))[:PLAY_H]])
        out = OUT / f"shot_{mid}_{a.n}_{a.view}.png"
        cv2.imwrite(str(out), img)
        print(out)
    elif a.cmd == "bench":
        ms, enc = [], []
        for r in rows:
            t = time.perf_counter()
            img = view.draw(r)
            ms.append((time.perf_counter() - t) * 1000)
            if len(enc) < 300:
                t = time.perf_counter()
                cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                enc.append((time.perf_counter() - t) * 1000)
        print(f"{len(ms)} rows ({a.view}): draw p50 {np.percentile(ms, 50):.2f} ms, p90 {np.percentile(ms, 90):.2f}, "
              f"max {max(ms):.1f}; JPEG p50 {np.percentile(enc, 50):.1f} ms, p90 {np.percentile(enc, 90):.1f}")
    elif a.cmd == "play":
        def frames(every=1 / 15):                                # the rows at real speed, ~15 pictures a second
            start, shown = None, -1.0
            for r in rows:
                if start is None:
                    start = (time.perf_counter(), r["t"])
                if r["t"] - shown < every * a.speed:
                    continue
                wait = start[0] + (r["t"] - start[1]) / a.speed - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)
                shown = r["t"]
                yield view.draw(r)
        enc = serve_page(view, frames(), port=a.port)
        print(f"{len(enc)} pictures, JPEG p50 {np.percentile(enc, 50):.1f} ms")


if __name__ == "__main__":
    main()
