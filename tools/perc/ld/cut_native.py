"""Native 1:1 Lie Detector title templates, cut from the client's own windows (PLAN-perception.md step 2.8).

The client draws the small gold "LIE DETECTOR" title into two windows (AntiMacro.img lieDetectorStandBy/back = the
"N sec until the Lie Detector mini-game starts" panel, lieDetector/back1 = the mini-game) and a larger yellow-green
one into the sound kind (soundLieDetector/stanby/backgrnd, not seen live yet). The title bar is see-through (alpha
170-187 around the letters; letters 204-255), so the scenery behind changes the picture a little: each candidate
(crop x backing grey) is graded over real native scenery, not over one backing.

Graded on the GPU (liedetector.GpuLieLook = cv2's scores):
  synthetic  each window alpha-blended onto native frames at random places (what the client draws at native)
  real       the saved Lie Detector frames (runs/*/lie*.png; FHD captures resized to 1366x768 as capture.normalize
             does - stretched pictures, so these are a floor, not the native score)
  false      the best score on every native PNG frame of the 2026-11-16 recordings (no Lie Detector in them)

    python tools/perc/ld/cut_native.py                 grade the candidates
    python tools/perc/ld/cut_native.py --write         write the chosen ones (CHOICE) to assets/ + tests/fixtures/

2026-11-16, 8641 native frames, 150 synthetic per window (the full table: HANDOFF "Step 2 state" 2.8):
  candidate         false max | synthetic min / p5: standby, game, sound | real (stretched) >= 0.75, best
  game m1 96        0.496     | 0.970 0.981 | 0.978 0.988 | -           | 36 / 90, 0.942   <- lie_detector_title
  sound m2 96       0.434     | -           | -           | 0.995 0.998 | (none seen yet)  <- lie_detector_sound
  today's panel     0.671     | 0.677 0.762 | 0.767 0.779 | -           | 35 / 90, 0.915
  today's game      0.651     | 0.780 0.882 | 0.886 0.898 | -           | 36 / 90, 0.976
Darker backings and tighter crops score higher over real scenery (m1 = the letters + 1-2 px).

Needs the client export (tools/cwdata/export.ps1, section "the Lie Detector's windows").
"""
import argparse
import glob
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
UI = Path(r"C:\Users\Yoav\dev\cw-data\export\UI\png\AntiMacro")
WINDOWS = {"standby": ("lieDetectorStandBy/back.png", (105, 8)),     # letters' top-left in the window
           "game": ("lieDetector/back1.png", (188, 8)),
           "sound": ("soundLieDetector/stanby/backgrnd.png", (14, 12))}
GOLD = (63, 5)                                    # the gold letters: 63 x 5 px (rows 8..12); sound: 80 x 9
SOUND = (80, 9)
# crops around the letters: (left, top, right, bottom) margins
CROPS = {"m4": (6, 4, 5, 3), "m2": (2, 2, 2, 2), "m1": (1, 1, 1, 2)}
BACKS = (0, 96, 160, 255)
CHOICE = {"lie_detector_title.npy": ("game", "m1", 96), "lie_detector_sound.npy": ("sound", "m2", 96)}


def rgba(name):
    return cv2.imread(str(UI / WINDOWS[name][0]), cv2.IMREAD_UNCHANGED)


def blend(bg, fg, x, y):
    """fg (h, w, 4) over bg at (x, y), rounded - the client's alpha blend (to +-1)."""
    out = bg.copy()
    h, w = fg.shape[:2]
    a = fg[..., 3:4].astype(np.float32) / 255
    out[y:y + h, x:x + w] = np.round(fg[..., :3] * a + bg[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)
    return out


def cut(name, crop, back):
    im = rgba(name)
    (lx, ly), (w, h) = WINDOWS[name][1], (SOUND if name == "sound" else GOLD)
    l, t, r, b = CROPS[crop]
    x0, y0 = lx - l, max(0, ly - t)
    piece = im[y0:ly + h + b, x0:lx + w + r]
    flat = np.full(piece.shape[:2] + (3,), back, np.uint8)
    return cv2.cvtColor(blend(flat, piece, 0, 0), cv2.COLOR_BGR2GRAY), (x0, y0)


def native_frames(step=1):
    out = []
    for d in sorted(glob.glob(str(ROOT / "runs" / "play" / "20261116_*" / "frames"))):
        out += sorted(glob.glob(d + "/*.png"))[::step]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=1, help="every n-th native frame for the false scores")
    ap.add_argument("--synth", type=int, default=150, help="native frames to paste each window onto")
    ap.add_argument("--write", action="store_true", help="write CHOICE's templates (no grading)")
    a = ap.parse_args()
    if a.write:
        for n, k in CHOICE.items():
            for d in (ROOT / "assets", ROOT / "tests" / "fixtures"):
                np.save(d / n, cut(*k)[0])
            print("wrote", n, k, cut(*k)[0].shape)
        return
    import torch
    from maplebrain.perception.liedetector import NAMES, GpuLieLook
    dev = torch.device("cuda")
    cands = {}
    for name in ("standby", "game", "sound"):
        if name == "standby":
            continue                                   # the same letters as "game" (stripes differ by <= 17 levels)
        for crop in CROPS:
            for back in BACKS:
                cands[(name, crop, back)] = cut(name, crop, back)[0]
    old = {n: np.load(ROOT / "assets" / n) for n in NAMES}
    keys = list(cands) + list(old)
    tpls = [cands[k] if k in cands else old[k] for k in keys]
    look = GpuLieLook(tpls, dev)

    def scores(img):
        u8 = torch.from_numpy(np.ascontiguousarray(img)).to(dev)
        r = look.looks(u8)
        return {keys[j]: (s, loc) for s, loc, j in r}

    rng = np.random.default_rng(7)
    frames = native_frames(a.step)
    print(f"{len(cands)} candidates + {len(old)} of today's; {len(frames)} native frames")
    false = {k: 0.0 for k in keys}
    synth = {k: {w: [] for w in WINDOWS} for k in keys}
    pick = set(rng.choice(len(frames), size=min(a.synth, len(frames)), replace=False).tolist())
    wins = {w: rgba(w) for w in WINDOWS}
    for i, p in enumerate(frames):
        img = cv2.imread(p)
        for k, (s, _) in scores(img).items():
            false[k] = max(false[k], s)
        if i in pick:
            for w, fg in wins.items():
                x = int(rng.integers(0, img.shape[1] - fg.shape[1]))
                y = int(rng.integers(0, img.shape[0] - fg.shape[0]))
                for k, (s, _) in scores(blend(img, fg, x, y)).items():
                    synth[k][w].append(s)
        if i % 500 == 0:
            print(f"  {i}/{len(frames)}", flush=True)
    real = {k: [] for k in keys}
    for p in sorted(glob.glob(str(ROOT / "runs" / "*" / "lie*.png"))):
        img = cv2.imread(p)
        if img.shape[:2] != (768, 1366):
            img = cv2.resize(img, (1366, 768), interpolation=cv2.INTER_AREA)
        for k, (s, _) in scores(img).items():
            real[k].append(s)

    def q(v, f):
        return f"{f(v):.3f}" if v else "  -  "
    print("\ncandidate                    false max | synthetic min / p5 / p50 per window (standby, game, sound)"
          " | real: n >= 0.75, best")
    for k in keys:
        cols = " | ".join(f"{q(synth[k][w], min)} {q(synth[k][w], lambda v: np.percentile(v, 5))} "
                          f"{q(synth[k][w], np.median)}" for w in WINDOWS)
        print(f"{str(k):28s} {false[k]:.3f}    | {cols} | {sum(s >= 0.75 for s in real[k])} / {len(real[k])}, "
              f"{max(real[k]):.3f}")


if __name__ == "__main__":
    main()
