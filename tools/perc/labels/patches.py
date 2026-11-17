"""Label sheets for by-eye labels (PLAN-perception.md step 3.0a): what the scene does NOT explain, numbered.

    python tools/perc/labels/patches.py RUN PICK.json [--only N,N] [--crop-zoom 2]

RUN = a run folder or a corpus segment RECORDING#K (tools/perc/frames.py `clip`: frames from PNG files or the
video; a segment's outputs go to its work folder, RUN/ below = that folder). The tracker's camera / tracks come
from the recording's ticks.jsonl, or - a `record` walk has none - from a replay of the segment (--tracks).

The candidates come from D = frame - expected scene (scene.py), never from a mob detector, so the labels stay
independent of what they grade. Per picked frame:
- the camera: followed over EVERY saved frame of the run (Scene.locate from the frame before, the recording's tracker
  camera as the seed), cached in RUN/labels/cams.json;
- D: play-area pixels off the expected scene by more than --tol (4: native PNG) on known scenery; patches = its
  3x3 cores grown 6 px, connected, >= 60 px; unknown scenery (animated objects) drawn purple;
- RUN/labels/sheets/NNNNNN.png: the frame with every patch boxed + numbered, footholds green | every patch cropped
  (the frame's own pixels, --crop-zoom x, screen x / y ticks every 20 px, footholds) - what a person labels from;
- RUN/labels/patches.json: {frame n: {"C": camera, "patches": [[x, y, w, h, area]], "unknown": share}}.
Labels go to RUN/labels.json (v2, labelfmt.py) by tools/perc/labels/label.py.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as rec  # noqa: E402

GREEN, BOX, UNK = (0, 220, 0), (0, 0, 255), (160, 0, 160)
map_of = rec.map_of             # (tools/perc/dcheck.py imports it from here)


def follow(c, sight: list, scene, tol: int, ui_t) -> dict:
    """Saved frame name -> camera (x, y) or None, every saved frame of the clip registered from the one before
    (`sight`: Clip.sight rows, their tracker camera = the seed)."""
    import torch
    cache = c.find("labels/cams.json")
    if cache.exists():
        return json.loads(cache.read_text())
    cache = c.out / "labels" / "cams.json"
    prev, last, cams = None, None, {}
    for k in sight:
        if not k.get("frame") or not k.get("cam"):
            continue
        f = c.read(k["frame"])
        if f is None:
            continue
        ft = torch.from_numpy(np.ascontiguousarray(f[:700])).to(scene.dev)
        reg = scene.locate(ft, C_guess=prev, seed=k["cam"], tol=tol, mask=ui_t, min_share=0.2, last_share=last)
        prev, last = (reg[0], reg[1]) if reg is not None else (prev, None)
        cams[k["frame"]] = list(reg[0]) if reg is not None else None
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(cams))
    return cams


def patches(bad: np.ndarray, min_area: int = 60) -> list:
    """[(x, y, w, h, area)] of the unexplained pixels' blobs (3x3 cores grown 6 px), biggest first."""
    core = cv2.erode(bad.astype(np.uint8), np.ones((3, 3), np.uint8))
    blob = cv2.dilate(core, np.ones((13, 13), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
    out = [tuple(int(v) for v in st[i]) for i in range(1, n) if st[i][4] >= min_area]
    return sorted(out, key=lambda b: -b[4])


def footholds(mj: dict, C, img, ox=0, oy=0, z=1):
    for f in mj["footholds"].values():
        p1 = (int((f["x1"] - C[0] - ox) * z), int((f["y1"] - C[1] - oy) * z))
        p2 = (int((f["x2"] - C[0] - ox) * z), int((f["y2"] - C[1] - oy) * z))
        cv2.line(img, p1, p2, GREEN, 1)


def crop_tile(frame, mj, C, b, k, z, margin=24, box=True):
    x, y, w, h = b[:4]
    x0, y0 = max(0, x - margin), max(0, y - margin)
    x1, y1 = min(frame.shape[1], x + w + margin), min(700, y + h + margin)
    c = cv2.resize(frame[y0:y1, x0:x1], None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)
    footholds(mj, C, c, x0, y0, z)
    if box:
        cv2.rectangle(c, ((x - x0) * z, (y - y0) * z), ((x + w - x0) * z - 1, (y + h - y0) * z - 1), BOX, 1)
    else:                                                       # a track's tile: its feet marker in the middle
        mark(c, x + w // 2, y + h - 26, "", (255, 255, 0), z, x0, y0)   # (sx, sy): see sheet()
    pad = np.full((c.shape[0] + 34, c.shape[1] + 44, 3), 30, np.uint8)        # room for the ticks
    pad[18:18 + c.shape[0], 40:40 + c.shape[1]] = c
    for sx in range((x0 + 19) // 20 * 20, x1, 20):
        u = 40 + (sx - x0) * z
        cv2.line(pad, (u, 12), (u, 17), (255, 255, 255), 1)
        if sx % 40 == 0:
            cv2.putText(pad, str(sx), (u - 12, 10), cv2.FONT_HERSHEY_PLAIN, 0.8, (255, 255, 255), 1)
    for sy in range((y0 + 19) // 20 * 20, y1, 20):
        v = 18 + (sy - y0) * z
        cv2.line(pad, (34, v), (39, v), (255, 255, 255), 1)
        if sy % 40 == 0:
            cv2.putText(pad, str(sy), (0, v + 4), cv2.FONT_HERSHEY_PLAIN, 0.8, (255, 255, 255), 1)
    cv2.putText(pad, str(k), (4, pad.shape[0] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return pad


def shelf(tiles, width):
    """Tiles packed left to right in rows of at most `width` px."""
    rows, row, w = [], [], 0
    for t in tiles:
        if row and w + t.shape[1] > width:
            rows.append(row)
            row, w = [], 0
        row.append(t)
        w += t.shape[1] + 6
    if row:
        rows.append(row)
    out = []
    for r in rows:
        h = max(t.shape[0] for t in r)
        line = np.full((h + 6, width, 3), 15, np.uint8)
        u = 0
        for t in r:
            tw = min(t.shape[1], width - u)
            line[:t.shape[0], u:u + tw] = t[:, :tw]
            u += t.shape[1] + 6
        out.append(line)
    return np.vstack(out) if out else np.zeros((0, width, 3), np.uint8)


LETTERS = "abcdefghijklmnopqrstuvwxyz"


def mark(img, x, y, letter, colour, z=1.0, ox=0, oy=0):
    u, v = int((x - ox) * z), int((y - oy) * z)
    cv2.drawMarker(img, (u, v), colour, cv2.MARKER_TILTED_CROSS, 10, 2)
    cv2.putText(img, letter, (u + 6, v + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
    cv2.putText(img, letter, (u + 6, v + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)


def track_colour(m):
    return {"live": (255, 255, 0), "hidden": (255, 160, 0), "dying": (0, 160, 255), "tentative": (180, 180, 180)}.get(
        m["state"], (255, 0, 255))


def sheet(frame, mj, C, ps, unk, tracks, p, z=2):
    """Top: the frame (0.75x) with patches (red, numbered) + the recording's tracks (letters at their feet: cyan live,
    orange hidden, blue dying, grey tentative). Then one 2x tile per track (feet at the marker) and one per patch
    with no track on it (a possible miss)."""
    top = frame[:700].copy()
    top[unk] = (top[unk] * 0.5 + np.array(UNK) * 0.5).astype(np.uint8)
    footholds(mj, C, top)
    for k, (x, y, w, h, _) in enumerate(ps):
        cv2.rectangle(top, (x, y), (x + w - 1, y + h - 1), BOX, 1)
        cv2.putText(top, str(k), (x, max(12, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    for i, m in enumerate(tracks):
        mark(top, m["sx"], m["sy"], LETTERS[i], track_colour(m))
    cv2.putText(top, f"n{p['n']} t{p['t']} {','.join(p['why'])}", (8, 690), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (255, 255, 255), 2)
    top = cv2.resize(top, None, fx=0.75, fy=0.75, interpolation=cv2.INTER_AREA)
    tiles = []
    for i, m in enumerate(tracks):
        x0, y0 = int(m["sx"]) - 90, int(m["sy"]) - 115
        t = crop_tile(frame, mj, C, (x0 + 24, y0 + 24, 132, 117, 0), f"{LETTERS[i]} {m['mob']} {m['state'][:4]} "
                      f"{m['src']} {m['score']}", z, box=False)
        tiles.append(t)
    for k, b in enumerate(ps):
        x, y, w, h = b[:4]
        if any(x - 30 <= m["sx"] <= x + w + 30 and y - 30 <= m["sy"] <= y + h + 60 for m in tracks):
            continue
        if w * h > 400 * 300:
            continue
        tiles.append(crop_tile(frame, mj, C, b, f"#{k}", z if w * h < 200 * 150 else 1))
    base = np.zeros((top.shape[0], 1366, 3), np.uint8)
    base[:, :top.shape[1]] = top
    return np.vstack([base, shelf(tiles, 1366)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("pick", type=Path)
    ap.add_argument("--tol", type=int, default=4)
    ap.add_argument("--only", default=None)
    ap.add_argument("--crop-zoom", type=int, default=2)
    ap.add_argument("--tracks", default="replay/work.jsonl", help="a recording without ticks.jsonl: this replay of it")
    ap.add_argument("--holdout", action="store_true", help="RUN is a hold-out segment of the corpus: only at gates (the use is logged)")
    a = ap.parse_args()
    import torch
    from maplebrain.perception import hud
    from maplebrain.scene import Scene
    c = rec.clip(a.run, a.holdout, "labels/patches.py")
    map_id = c.map_id
    scene = Scene.load(map_id)
    mj = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
    ui = np.ones((700, 1366), bool)
    for x0, y0, x1, y1 in hud.UI_RECTS:
        ui[y0:min(y1, 700), x0:x1] = False
    ui_t = torch.from_numpy(ui).to(scene.dev)
    sight = c.sight(a.tracks)
    cams = follow(c, sight, scene, a.tol, ui_t)
    print(f"camera on {sum(v is not None for v in cams.values())} of {len(cams)} saved frames")
    ticks = {k["frame"]: k["mobs"] for k in sight if k.get("frame")}
    pick = json.loads(a.pick.read_text(encoding="utf-8"))["frames"]
    if a.only:
        want = {int(v) for v in a.only.split(",")}
        pick = [p for p in pick if p["n"] in want]
    out = c.out / "labels"
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    pj = out / "patches.json"
    allp = json.loads(pj.read_text()) if pj.exists() else {}
    for p in pick:
        C = cams.get(p["frame"])
        frame = c.read(p["frame"])
        if C is None or frame is None:
            print(f"  {p['frame']}: no camera / frame")
            continue
        ft = torch.from_numpy(np.ascontiguousarray(frame[:700])).to(scene.dev)
        exp, known = scene.expected(C)
        d = (ft.float() - exp).abs().amax(dim=2)
        bad = (((d > a.tol) & known).cpu().numpy() & ui)
        unk = (~known).cpu().numpy() & ui
        ps = patches(bad)
        allp[str(p["n"])] = {"frame": p["frame"], "C": C, "patches": [list(b) for b in ps],
                            "unknown": round(float(unk.mean()), 4)}
        tracks = [m for m in ticks.get(p["frame"], []) if m["state"] != "offscreen"
                  and -40 <= m["sx"] < 1406 and m["sy"] < 760]
        allp[str(p["n"])]["tracks"] = [[m["id"], m["mob"], m["sx"], m["sy"], m["state"], m["src"], m["score"]]
                                       for m in tracks]
        cv2.imwrite(str(out / "sheets" / f"{p['n']:06d}.png"), sheet(frame, mj, C, ps, unk, tracks, p))
    pj.write_text(json.dumps(allp))
    n = [len(v["patches"]) for v in allp.values()]
    print(f"{len(allp)} frames, patches per frame p50 {np.median(n):.0f} max {max(n)}; sheets in {out / 'sheets'}")


if __name__ == "__main__":
    main()
