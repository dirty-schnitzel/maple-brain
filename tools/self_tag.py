"""Capture a character's name tag for the bot's self-finder (perception/selfpos.py) - 2026-11-10, DirtySchntzl.

The bot finds itself by matching its own name tag (dark box + white name). A new character = a new tag. Stand
somewhere the tag is clear (not on / in front of a ladder or rope, no other player overlapping), the HUD (bottom
left: level, job, name) visible, then:

    python tools\\self_tag.py DirtySchntzl [--window vmware] [--seconds 3]

Only reads the screen (no key is sent). Our name is printed in the HUD too, in the same font and size as the tag:
that line of the HUD is the template that finds our tag on screen (best match, high-passed like the bot's own
finder, so the background behind the see-through tag box doesn't matter). The tag box around those letters is cut
from each frame over --seconds and the per-pixel median taken (walking a little while it grabs makes the
background drop out). The result is checked - it must match itself well on every frame and nothing else on screen
may come close (config.Perception.self_min_score) - and only then saved: assets/tags/NAME.npy (grey, like
assets/self_tag_gray.npy), NAME.png to look at, NAME_pick.png = the frame with the box drawn.
Use it with `--char NAME` on run / serve / goto.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from maplebrain.capture import Screen, find_window  # noqa: E402
from maplebrain.config import WINDOWS, Perception  # noqa: E402
from maplebrain.perception.hud import ui_mask  # noqa: E402
from maplebrain.perception.selfpos import _hp, _match, find_self  # noqa: E402

# The HUD's name line (bottom left, under the job): letters in rows 748-760 from x ~368, measured on JenkinsJob's
# recordings and DirtySchntzl live (2026-11-10). The template = those letters + 2 px all round.
HUD_ROWS, HUD_X0, HUD_X1 = (748, 761), 360, 495
# The tag box around the name's letters: ~7 px each side, 17 px tall (JenkinsJob's template: 74 x 17 for a 60 px
# name; on 29 recorded frames the letters sat 6 (+-2) px right of / 2 px above that template's box corner).
MARGIN_X, BOX_H, LETTERS_DY = 7, 17, 2


def hud_name(frame):
    """(template: the HUD name's letters high-passed, the name's width px) or None (no HUD name readable)."""
    band = frame[HUD_ROWS[0]:HUD_ROWS[1], HUD_X0:HUD_X1]
    lo, hi = band.min(axis=2).astype(int), band.max(axis=2).astype(int)
    cols = np.where(((lo > 165) & (hi - lo < 45)).any(axis=0))[0]
    if not len(cols):
        return None
    x0, x1 = HUD_X0 + int(cols.min()), HUD_X0 + int(cols.max()) + 1
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return _hp(g[HUD_ROWS[0] - 2:HUD_ROWS[1] + 2, x0 - 2:x1 + 2]), x1 - x0


def pick_tag(frame, min_score=0.5, gap=0.15):
    """(x, y, w, h) of our tag: where the HUD's name matches best on screen (HUD / chat blanked), if it is clearly
    the best spot. 2026-11-10 live: 0.83 (Split Road) / 0.74 (Lith Harbor, bright clouds behind) / 0.60 (a chain
    through the tag), next best spot 0.31-0.42; another player's tag doesn't come close. None = not sure. The
    gap to the next best spot is what makes it sure; main's check rejects a tag spoiled by what's behind it."""
    hud = hud_name(frame)
    if hud is None:
        return None
    tpl, width = hud
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g[ui_mask(frame.shape) == 0] = 0
    r = _match(_hp(g), tpl)
    _, score, _, (lx, ly) = cv2.minMaxLoc(r)
    r[max(0, ly - 15):ly + 15, max(0, lx - 40):lx + 40] = -1
    if score < min_score or float(r.max()) > score - gap:
        return None
    x, y = lx + 2 - MARGIN_X, ly + 2 - LETTERS_DY          # +2: the template's own padding
    return (x, y, width + 2 * MARGIN_X, BOX_H)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="the character's name (the file name: assets/tags/NAME.npy)")
    ap.add_argument("--window", choices=WINDOWS, default="maplestory")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--box", default=None, help="x,y,w,h of the tag in the 1366x768 frame (when the finder picks "
                    "the wrong tag); the character must stand still then")
    a = ap.parse_args()
    hwnd = find_window(a.window)
    if not hwnd:
        print("game window not found")
        return 1
    screen = Screen(hwnd)
    screen.calibrate()
    frames, end = [], time.perf_counter() + a.seconds
    while time.perf_counter() < end:
        f = screen.grab()
        if f is not None:
            frames.append(f.copy())
        time.sleep(0.1)
    screen.close()
    fixed = tuple(int(v) for v in a.box.split(",")) if a.box else None
    boxes = [(f, fixed or pick_tag(f)) for f in frames]
    boxes = [(f, b) for f, b in boxes if b is not None]
    if not boxes:
        print(f"no tag matching the HUD's name found in {len(frames)} frames - stand clear of ladders / ropes / "
              "other players, HUD name visible (or give --box x,y,w,h)")
        return 1
    size = boxes[0][1][2:]                              # the name's width doesn't change: one size
    crops = []
    for f, (x, y, w, h) in boxes:
        c = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)[max(0, y):y + h, max(0, x):x + w]
        if (w, h) == tuple(size) and c.shape == (h, w):
            crops.append(c)
    if not crops:
        print("the tag is cut by the screen's edge - walk away from the map's end and run it again")
        return 1
    tag = np.median(np.stack(crops), axis=0).astype(np.uint8)
    out = ROOT / "assets" / "tags"
    out.mkdir(parents=True, exist_ok=True)
    f, (x, y, w, h) = boxes[-1]
    pick = f.copy()
    cv2.rectangle(pick, (x - 1, y - 1), (x + w, y + h), (0, 0, 255), 1)
    cv2.imwrite(str(out / f"{a.name}_pick.png"), pick)
    print(f"picked the tag at x {x} y {y} ({w}x{h}), {tag.shape[1]}x{tag.shape[0]} from {len(crops)} of "
          f"{len(frames)} frames: see {out / (a.name + '_pick.png')}")

    # check: matches itself everywhere, nothing else on screen comes close
    p, own, rival = Perception(), [], []
    t = _hp(tag.astype(np.float32))
    for f, (x, y, w, h) in boxes:
        hit = find_self(f, tag, min_score=-1, edges=False)
        own.append(hit[4] if hit else 0.0)
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g[ui_mask(f.shape) == 0] = 0
        r = _match(_hp(g), t)
        r[max(0, y - 20):y + 20, max(0, x - 40):x + 40] = -1               # blank our own tag's spot
        rival.append(float(r.max()))
    print(f"own tag score: min {min(own):.2f}, median {np.median(own):.2f} (bot needs >= {p.self_min_score}); "
          f"best other spot on screen: {max(rival):.2f} (must stay well below {p.self_min_score})")
    if min(own) < 0.8 or max(rival) >= p.self_min_score - 0.05:
        print("NOT GOOD ENOUGH, nothing saved - stand somewhere clearer (or walk a little while it grabs) and run "
              "it again")
        return 1
    np.save(out / f"{a.name}.npy", tag)                 # only a tag that passed the check is ever saved
    cv2.imwrite(str(out / f"{a.name}.png"), cv2.resize(tag, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST))
    print(f"ok - saved {out / (a.name + '.npy')}; start the bot with --char {a.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
