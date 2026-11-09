"""Build the README's pictures from a recorded run (frames + ticks.jsonl), names and chat hidden.

usage: make_images.py [RUN_DIR] [T0] [T1]   (default: runs/v2/press1 87.5 95 = two kills on Ant Tunnel IV)
  -> docs/img/vision.gif  (the bot's view of a fight: tracks, target, reach, HUD read)
     docs/img/play.gif    (the same seconds as the game shows them)
     docs/img/screen.png  (one full frame with what the bot reads called out)
     docs/img/livemap.txt (the console map at one tick, for the README's code block)
The GIFs hide only our own name tag (other players' names stay, the user's choice); screen.png hides every
name tag, the chat box and the HUD's character name."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebrain.perception.hud import ui_mask  # noqa: E402
from maplebrain.perception.tags import find_tags  # noqa: E402

OUT = ROOT / "docs" / "img"
CHAT = (284, 612, 850, 712)          # chat box incl. its input line (1366x768 frame)
HUD_NAME = (360, 734, 495, 768)      # "Spearman / <name>" in the status bar
REACH = (24, 139)                    # polearm sure reach, px in front (log: "sure reach 24..139")

# BGR
LIVE, WEAK, LOST, DYING, TARGET, US = (80, 220, 80), (0, 200, 255), (60, 60, 255), (170, 170, 170), (255, 80, 255), (255, 210, 60)


def pixelate(img, x0, y0, x1, y1, block=6):
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(img.shape[1], x1), min(img.shape[0], y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    roi = img[y0:y1, x0:x1]
    small = cv2.resize(roi, (max(1, (x1 - x0) // block), max(1, (y1 - y0) // block)), interpolation=cv2.INTER_AREA)
    img[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)


def loose_tags(img):
    """Name-tag-like boxes, looser than the bot's find_tags (a missed name here is a name on a public page):
    a line of >= 3 pale glyphs. A tag touching a sprite or a rope above it joins that blob, so tall blobs are cut
    at near-empty rows and each slice is tested on its own. It also hides some bright effects; better than one
    missed name."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    txt = (((hsv[..., 2] > 100) & (hsv[..., 1] < 80)).astype(np.uint8)) & ui_mask(img.shape)
    line = cv2.dilate(txt, np.ones((1, 7), np.uint8))      # join a line's glyphs, not the sprite above it
    n, _, st, _ = cv2.connectedComponentsWithStats(line)
    v = hsv[..., 2].astype(np.float32)
    out = []

    def test(x, y, w, h):
        if not (6 <= h <= 22 and 14 <= w <= 180):
            return False
        sub = txt[y:y + h, x:x + w]
        if not 0.06 <= sub.mean() <= 0.75:
            return False
        _, _, g_st, _ = cv2.connectedComponentsWithStats(sub)
        if len([g for g in g_st[1:] if g[4] >= 3 and g[3] <= 15 and g[2] <= 14]) < 3:
            return False
        box = v[y:y + h, x:x + w][sub == 0]
        return box.size > 0 and box.mean() < 150

    for i in range(1, n):
        x, y, w, h, _ = (int(c) for c in st[i])
        if test(x, y, w, h):
            out.append((x, y, w, h))
            continue
        if h <= 22 or w < 14 or h > 400:
            continue
        rows = txt[y:y + h, x:x + w].sum(axis=1)
        full = rows > max(5, 0.08 * w)
        r = 0
        while r < h:                                        # each run of text-ish rows = a candidate line
            if not full[r]:
                r += 1
                continue
            e = r
            while e < h and full[e]:
                e += 1
            if 6 <= e - r <= 16:
                cols = np.flatnonzero(txt[y + r:y + e, x:x + w].sum(axis=0))
                if cols.size and test(x + int(cols[0]), y + r, int(cols[-1] - cols[0]) + 1, e - r):
                    out.append((x + int(cols[0]), y + r, int(cols[-1] - cols[0]) + 1, e - r))
            r = e
    return out


def tag_boxes(img, tick):
    """Name tags on this frame in MAP coordinates (screen + camera), so neighbour frames can reuse them."""
    cam = tick["obs"].get("cam") or (0, 0)
    return [(x + cam[0], y + cam[1], w, h) for x, y, w, h in find_tags(img) + loose_tags(img)]


def anonymize(img, tick, tags=(), only_ours=False):
    """Pixelate name tags (`tags`: map-coordinate boxes found on this frame AND its neighbours, so a tag the
    finders miss for a frame still gets hidden; ours also from the self position), the chat box and the HUD name.
    only_ours: hide only OUR name (tags found right under us + the self-position box); other players' stay."""
    cam = tick["obs"].get("cam") or (0, 0)
    s = tick["timings"].get("self") or {}
    for x, y, w, h in tags:
        x, y = int(x - cam[0]), int(y - cam[1])
        if only_ours:
            if s.get("x") is None:
                continue
            mx, my = s["x"] - cam[0], s["y"] - cam[1]
            if not (abs(x + w / 2 - mx) <= 110 and -15 <= y - my <= 50):
                continue
        pixelate(img, x - 12, y - 5, x + w + 12, y + h + 5)
    if s.get("x") is not None and tick["obs"].get("cam"):
        mx, my = int(s["x"] - cam[0]), int(s["y"] - cam[1])
        pixelate(img, mx - 75, my + 1, mx + 75, my + 24)
    x0, y0, x1, y1 = CHAT
    img[y0:y1, x0:x1] = (cv2.GaussianBlur(img[y0:y1, x0:x1], (0, 0), 9) * 0.45).astype(np.uint8)
    pixelate(img, *HUD_NAME)
    return img


def mob_box(mob_id, cache={}):
    if mob_id not in cache:
        try:
            m = json.loads((ROOT / "assets/mcw/mobs" / str(mob_id) / "mob.json").read_text(encoding="utf-8"))
            f = m["frames"]["stand"][0]
            cache[mob_id] = (m.get("name") or m["info"].get("name") or str(mob_id), f["lt"], f["rb"])
        except Exception:                                   # noqa: BLE001
            cache[mob_id] = (str(mob_id), [-30, -55], [30, 0])
    return cache[mob_id]


def text(img, s, org, color=(255, 255, 255), scale=0.5, bg=(20, 20, 20)):
    (w, h), _ = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    x, y = org
    cv2.rectangle(img, (x - 3, y - h - 4), (x + w + 3, y + 4), bg, -1)
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def overlay(img, tick, hud=True):
    """What the bot believes on this tick, drawn on the frame."""
    o, v = tick["obs"], tick["timings"].get("v2") or {}
    s, cam = tick["timings"].get("self") or {}, o.get("cam")
    if not cam:
        return img
    f = v.get("facing") or 0
    if s.get("x") is not None:
        mx, my = int(s["x"] - cam[0]), int(s["y"] - cam[1])
        if f:
            a, b = mx + f * REACH[0], mx + f * REACH[1]
            band = img.copy()
            cv2.rectangle(band, (min(a, b), my - 62), (max(a, b), my + 2), US, -1)
            img[:] = cv2.addWeighted(band, 0.22, img, 0.78, 0)
            cv2.rectangle(img, (min(a, b), my - 62), (max(a, b), my + 2), US, 1, cv2.LINE_AA)
            cv2.arrowedLine(img, (mx, my - 80), (mx + 34 * f, my - 80), US, 2, cv2.LINE_AA, tipLength=0.4)
        cv2.circle(img, (mx, my), 5, US, -1, cv2.LINE_AA)
    for m in o.get("mobs") or []:
        if m.get("kind") != "mob" or m["state"] == "tentative":
            continue
        name, lt, rb = mob_box(m["mob"])
        fx, fy = int(m["x"] - cam[0]), int(m["y"] - cam[1])
        p0, p1 = (fx + lt[0], fy + lt[1]), (fx + rb[0], fy + rb[1])
        if CHAT[0] < fx < CHAT[2] and fy > CHAT[1]:
            continue                                        # under the (blurred) chat box
        if m["state"] == "dying":
            col, why = DYING, "dying"
        elif m["src"] == "none" or (m.get("unseen") or 0) > 0.05:
            col, why = LOST, f"unseen {m.get('unseen', 0):.1f}s"
        elif (m.get("score") or 0) >= 0.7:
            col, why = LIVE, f"{m['score']:.2f}"
        else:
            col, why = WEAK, f"weak {m.get('score') or 0:.2f}"
        is_t = m["id"] == v.get("target")
        cv2.rectangle(img, p0, p1, TARGET if is_t else col, 3 if is_t else 2, cv2.LINE_AA)
        text(img, f"{'TARGET ' if is_t else ''}{name} #{m['id']} {why}", (p0[0], p0[1] - 6),
             TARGET if is_t else col, 0.42)
    if not hud:
        return img
    hp = f"HP {o.get('hp_now')}/{o.get('hp_max')}" if o.get("hp_now") else "HP ?"
    mp = f"MP {o.get('mp_now')}/{o.get('mp_max')}" if o.get("mp_now") else "MP ?"
    mode = tick.get("mode") or v.get("mode") or "?"
    text(img, f"{mode}   {hp}   {mp}   weapon {v.get('weapon') or '-'}   keys {'+'.join(tick['timings'].get('held', [])) or '-'}",
         (14, 30), (255, 255, 255), 0.6)
    return img


def crop_box(ticks, w=880, h=495, shape=(605, 1366)):
    """A fixed crop centred on where we stood (median) during the window, above the chat box."""
    xs, ys = [], []
    for t in ticks:
        s, cam = t["timings"].get("self") or {}, t["obs"].get("cam")
        if s.get("x") is not None and cam:
            xs.append(s["x"] - cam[0]), ys.append(s["y"] - cam[1])
    cx, cy = (np.median(xs), np.median(ys) - 70) if xs else (shape[1] / 2, shape[0] / 2)
    x0 = int(min(max(0, cx - w / 2), shape[1] - w))
    y0 = int(min(max(0, cy - h / 2), shape[0] - h))
    return x0, y0, x0 + w, y0 + h


def save_gif(frames, times, path, width=640):
    pil = []
    for f in frames:
        f = cv2.resize(f, (width, int(f.shape[0] * width / f.shape[1])), interpolation=cv2.INTER_AREA)
        pil.append(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    dur = [max(60, int(1000 * (b - a))) for a, b in zip(times, times[1:])] + [900]
    pal = [p.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for p in pil]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=dur, loop=0, optimize=True, disposal=1)
    print(f"{path.relative_to(ROOT)}: {len(pal)} frames, {path.stat().st_size / 1e6:.1f} MB")


def screen(run, tick, tags=()):
    """One full frame, anonymized, with call-outs for what the bot reads."""
    img = cv2.imread(str(run / "frames" / tick["frame"]))
    img = overlay(anonymize(img, tick, tags or tag_boxes(img, tick)), tick, hud=False)
    o = tick["obs"]
    notes = [((4, 2, 232, 196), "minimap -> which map (301 known) + where we are", (240, 215)),
             ((497, 732, 722, 752), "HP / MP digits -> potions, HP stop", (497, 726 - 20)),
             ((722, 732, 842, 752), "EXP points -> kills & EXP/hour", (735, 726 - 46))]
    for (x0, y0, x1, y1), s, org in notes:
        cv2.rectangle(img, (x0, y0), (x1, y1), (0, 230, 255), 2, cv2.LINE_AA)
        text(img, s, org, (0, 230, 255), 0.55)
    return img


def main(run=ROOT / "runs/v2/press1", t0=87.5, t1=95.0):
    run = Path(run)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in open(run / "ticks.jsonl", encoding="utf-8")]
    win = [r for r in rows if r.get("frame") and t0 <= r["obs"]["t"] <= t1]
    box = crop_box(win)
    win = [r for r in win if (run / "frames" / r["frame"]).exists()]
    imgs = [cv2.imread(str(run / "frames" / r["frame"])) for r in win]
    found = [tag_boxes(img, r) for img, r in zip(imgs, win)]
    near = [sum(found[max(0, i - 2):i + 3], []) for i in range(len(win))]
    plain, seen, times = [], [], []
    for img, r, tags in zip(imgs, win, near):
        img = anonymize(img, r, tags, only_ours=True)        # the GIFs: only our own name is hidden
        plain.append(img[box[1]:box[3], box[0]:box[2]].copy())
        seen.append(overlay(img.copy(), r)[box[1]:box[3], box[0]:box[2]])
        times.append(r["obs"]["t"])
    # the HUD line sits at the frame's top-left; redraw it inside the crop
    for i, r in enumerate(win[:len(seen)]):
        strip = seen[i]
        strip[:44] = (strip[:44] * 0.35).astype(np.uint8)
        o, v = r["obs"], r["timings"].get("v2") or {}
        text(strip, f"{r.get('mode') or '?'}  HP {o.get('hp_now')}/{o.get('hp_max')}  MP {o.get('mp_now')}/{o.get('mp_max')}"
             f"  weapon {v.get('weapon') or '-'}  keys {'+'.join(r['timings'].get('held', [])) or '-'}",
             (12, 28), (255, 255, 255), 0.6, bg=(0, 0, 0))
    save_gif(seen, times, OUT / "vision.gif")
    save_gif(plain, times, OUT / "play.gif")
    # the screen shot: the tick in the window with the most live mobs on screen
    best = max(win, key=lambda r: sum(1 for m in r["obs"].get("mobs") or [] if m.get("kind") == "mob"
                                      and m["state"] == "live"))
    cv2.imwrite(str(OUT / "screen.png"), screen(run, best, near[win.index(best)]))   # all names hidden here
    print(f"docs/img/screen.png: t={best['obs']['t']:.2f}")
    from maplebrain.livemap import View
    view = View(10005063, 118)
    (OUT / "livemap.txt").write_text(view.frame(best, run), encoding="utf-8")
    print("docs/img/livemap.txt")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(*([Path(a[0])] if a else []), *(float(x) for x in a[1:3]))
