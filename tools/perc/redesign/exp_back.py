"""E7: the parallax backgrounds. Compose the map's `back` layers under the tile / object render for a frame's exact
camera and compare with the frame: which constants does the Classic World client use, how much of the picture is
explained?
    python exp_back.py RUN [N]        (needs exp_render.py build first; RUN = a PNG recording at native 1366x768)

Model (HeavenClient MapBackgrounds, tiled types; the client's own integer arithmetic): the picture's origin is at
    screen x = bx + WOFF + trunc(rx * (Cx + WOFF) / 100)      (y alike with ry, HOFF),  repeated every cx / cy px
with C = the camera (map = screen + C). RESULT 2026-11-16: WOFF 682, HOFF 468, division toward zero - all 65 layer
positions of 13 frames (fitted one by one, +-2 px) match exactly.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from maplebrain.gamedata import EXPORT, load_xml  # noqa: E402
from maplebrain.perception import hud  # noqa: E402

HERE = Path(__file__).parent
MAP = 10005063
W, H, PLAY_H = 1366, 768, 600


def load_backs(map_id=MAP):
    img = load_xml(next((EXPORT / "Map").glob(f"Map?/{map_id:09d}.img.xml")))
    out = []
    for k in sorted((img.get("back") or {}), key=lambda s: int(s) if s.isdigit() else 1e9):
        b = img["back"][k]
        if not isinstance(b, dict) or not b.get("bS"):
            continue
        kind = "ani" if b.get("ani") else "back"
        meta = (load_xml(EXPORT / "Map" / "Back" / f"{b['bS']}.img.xml").get(kind) or {}).get(str(b["no"]))
        f = EXPORT / "Map" / "Back" / "png" / b["bS"] / kind / f"{b['no']}.png"
        pic = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if pic is None or not isinstance(meta, dict):
            print("  back", k, b["bS"], b["no"], "has no picture (animated?)")
            continue
        out.append(dict(b, pic=pic, origin=tuple(meta.get("origin") or (0, 0)), k=k))
    return out


def compose(backs, C, woff, hoff, w=W, h=PLAY_H, formula="heaven"):
    """The backgrounds for camera C: (bgr float, known mask)."""
    out = np.zeros((h, w, 3), np.float32)
    known = np.zeros((h, w), bool)
    for b in backs:
        pic = b["pic"]
        ph, pw = pic.shape[:2]
        cx, cy = b.get("cx") or pw, b.get("cy") or ph
        typ = b.get("type", 0)
        # the client's integer arithmetic (fitted 2026-11-16: 65 of 65 layer positions): division toward zero
        sx = b["x"] + woff + int(b["rx"] * (C[0] + woff) / 100) - b["origin"][0]
        sy = b["y"] + hoff + int(b["ry"] * (C[1] + hoff) / 100) - b["origin"][1]
        xs = range(sx % cx - cx, w, cx) if typ in (1, 3, 4, 6, 7) else [sx]
        ys = range(sy % cy - cy, h, cy) if typ in (2, 3, 5, 6, 7) else [sy]
        a_layer = b.get("a", 255) / 255.0
        for y in ys:
            for x in xs:
                x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + pw), min(h, y + ph)
                if x1 <= x0 or y1 <= y0:
                    continue
                src = pic[y0 - y:y1 - y, x0 - x:x1 - x]
                a = (src[..., 3:4].astype(np.float32) / 255.0) * a_layer
                out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + src[..., :3] * a
                known[y0:y1, x0:x1] |= a[..., 0] > 0.99
    return out, known


def compose_sub(backs, C, woff, hoff, w=W, h=PLAY_H):
    """Like compose, but each layer drawn at its exact (fractional) position with bilinear filtering, as a GPU
    draws a textured quad that isn't on the pixel grid."""
    out = np.zeros((h, w, 3), np.float32)
    known = np.zeros((h, w), bool)
    for b in backs:
        pic = b["pic"].astype(np.float32)
        ph, pw = pic.shape[:2]
        cx, cy = b.get("cx") or pw, b.get("cy") or ph
        typ = b.get("type", 0)
        fx = b["x"] + b["rx"] * (C[0] + woff) / 100 + woff - b["origin"][0]
        fy = b["y"] + b["ry"] * (C[1] + hoff) / 100 + hoff - b["origin"][1]
        sx, sy = int(np.floor(fx)), int(np.floor(fy))
        wrap = cv2.BORDER_WRAP if (cx == pw and cy == ph and typ == 3) else cv2.BORDER_CONSTANT
        pm = pic.copy()
        pm[..., :3] *= pm[..., 3:4] / 255.0                              # premultiplied: filtering mixes colours right
        M = np.float32([[1, 0, fx - sx], [0, 1, fy - sy]])
        if wrap == cv2.BORDER_WRAP:
            sh = cv2.warpAffine(pm, M, (pw, ph), flags=cv2.INTER_LINEAR, borderMode=wrap)
        else:
            sh = cv2.warpAffine(pm, M, (pw + 1, ph + 1), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        qh, qw = sh.shape[:2]
        xs = range(sx % cx - cx, w, cx) if typ in (1, 3, 4, 6, 7) else [sx]
        ys = range(sy % cy - cy, h, cy) if typ in (2, 3, 5, 6, 7) else [sy]
        a_layer = b.get("a", 255) / 255.0
        for y in ys:
            for x in xs:
                x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + qw), min(h, y + qh)
                if x1 <= x0 or y1 <= y0:
                    continue
                src = sh[y0 - y:y1 - y, x0 - x:x1 - x]
                a = src[..., 3:4] / 255.0 * a_layer
                out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + src[..., :3] * a_layer
                known[y0:y1, x0:x1] |= a[..., 0] > 0.99
    return out, known


def register(frame, R, meta, cam, S=24):
    """Exact camera from the tile / object render: the offset around `cam` with the most render pixels within 4."""
    ax, ay = int(round(cam[0])) - meta["x0"], int(round(cam[1])) - meta["y0"]
    fy0, fy1, fx0, fx1 = 120, 560, 250, 1150
    rt = np.ascontiguousarray(R[ay + fy0:ay + fy1, ax + fx0:ax + fx1])
    mask = np.repeat((rt[..., 3:4] > 250).astype(np.uint8) * 255, 3, 2)
    if mask[..., 0].mean() < 10:
        return None
    area = np.ascontiguousarray(frame[fy0 - S:fy1 + S, fx0 - S:fx1 + S])
    r = np.nan_to_num(cv2.matchTemplate(area, np.ascontiguousarray(rt[..., :3]), cv2.TM_CCORR_NORMED, mask=mask), nan=-1)
    _, sc, _, (lx, ly) = cv2.minMaxLoc(r)
    return (int(round(cam[0])) - (lx - S), int(round(cam[1])) - (ly - S)), float(sc)


def ui_mask():
    m = np.ones((PLAY_H, W), bool)
    for x0, y0, x1, y1 in hud.UI_RECTS:
        m[y0:min(y1, PLAY_H), x0:x1] = False
    return m


def main():
    run = ROOT / sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    R = cv2.imread(str(HERE / "ant4_render.png"), cv2.IMREAD_UNCHANGED)
    meta = json.loads((HERE / "ant4_render.json").read_text())
    backs = load_backs()
    L = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
    L = [l for l in L if l.get("frame") and l["obs"].get("cam")]
    L = L[::max(1, len(L) // n)][:n]
    ui = ui_mask()
    frames = []
    for l in L:
        f = cv2.imread(str(run / "frames" / l["frame"]))
        reg = register(f, R, meta, l["obs"]["cam"])
        if reg is None or reg[1] < 0.8:
            continue
        C = reg[0]
        sc = R[C[1] - meta["y0"]:C[1] - meta["y0"] + PLAY_H, C[0] - meta["x0"]:C[0] - meta["x0"] + W]
        frames.append((l["frame"], f[:PLAY_H], C, sc))
    print(f"{len(frames)} frames registered; camera x {min(c[2][0] for c in frames)}..{max(c[2][0] for c in frames)}, "
          f"y {min(c[2][1] for c in frames)}..{max(c[2][1] for c in frames)}")

    def score(woff, hoff, tol=4, keep=None):
        tot = ok = 0
        for name, f, C, sc in frames:
            bg, known = compose(backs, C, woff, hoff)
            free = ui & (sc[..., 3] < 5) & known                       # background-only pixels (no tile / object)
            d = np.abs(bg - f.astype(np.float32)).max(axis=2)
            tot += int(free.sum())
            ok += int(((d <= tol) & free).sum())
            if keep is not None:
                keep.append((name, f, C, sc, bg, known, d))
        return ok / max(1, tot)

    cands = [(682, 468), (683, 384), (400, 300)]
    res = sorted(((score(wo, ho), wo, ho) for wo, ho in cands), reverse=True)
    for s, wo, ho in res:
        print(f"  WOFF {wo:4d} HOFF {ho:4d}: background pixels within +-4: {100 * s:.1f} %")
    _, wo, ho = res[0]
    best = (score(wo, ho), wo, ho)
    for step in (1,):                                                    # local search around the best candidate
        improved = True
        while improved:
            improved = False
            for dw, dh in ((step, 0), (-step, 0), (0, step), (0, -step)):
                s = score(best[1] + dw, best[2] + dh)
                if s > best[0] + 1e-4:
                    best, improved = (s, best[1] + dw, best[2] + dh), True
    print(f"fitted: WOFF {best[1]} HOFF {best[2]}: {100 * best[0]:.1f} % of background pixels within +-4")
    keep = []
    score(best[1], best[2], keep=keep)
    tot = expl = dyn = 0
    for name, f, C, sc, bg, known, d in keep:
        a = sc[..., 3:4].astype(np.float32) / 255.0
        exp = bg * (1 - a) + sc[..., :3] * a
        dd = np.abs(exp - f.astype(np.float32)).max(axis=2)
        kn = ui & (known | (sc[..., 3] > 250))
        tot += int(ui.sum())
        expl += int(((dd <= 4) & kn).sum())
        dyn += int((ui & ~kn).sum())
    print(f"whole play area (UI off): {100 * expl / tot:.1f} % of pixels within +-4 of backs + tiles + objects; "
          f"{100 * dyn / tot:.1f} % have no known scenery")
    name, f, C, sc, bg, known, d = keep[len(keep) // 2]
    a = sc[..., 3:4].astype(np.float32) / 255.0
    exp = (bg * (1 - a) + sc[..., :3] * a).astype(np.uint8)
    dd = np.abs(exp.astype(np.int16) - f.astype(np.int16)).max(axis=2)
    res_img = f.copy()
    res_img[dd <= 4] = 0
    cv2.imwrite(str(HERE / "back_residual.png"), np.vstack([f, exp, res_img]))
    print("picture (frame / expected / what is left):", HERE / "back_residual.png", name, "C", C)


if __name__ == "__main__":
    main()
