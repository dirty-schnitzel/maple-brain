"""How late is a recording's picture against its logged mouse? Measured on the bank's Lie Detector sections.

In the mouse game ("follow the fading figure") the client draws the mouse as a green crosshair, so every frame
of the lossless video shows where the game had the mouse when it drew that frame. frames.jsonl's "cur" is asked
from Windows right after the frame was grabbed (capture.cursor), so it is the mouse NOW - later than the picture.
This tool finds the crosshair in every frame of the mouse game and the shift, in frames, at which the logged
path fits the drawn one.

    python tools/perc/ld/cursor_delay.py                      every section of CORPUS/lie
    python tools/perc/ld/cursor_delay.py SECTION [SECTION ...]  these (a folder name in lie/, or a folder)
    python tools/perc/ld/cursor_delay.py --corpus DIR         another bank (default: config.CORPUS / MAPLE_CORPUS)

Measured 2026-11-28, both sections of the bank (both the follow kind; the crosshair found on every frame of the
game, 977 of 977 and 761 of 761):

    2026-11-28 The Murky Swamp II      the picture = the logged cursor of 2 frames (33 ms) earlier:
                                       error p50 0.00 px, p90 2.00, p99 4.74; crosshair - cursor (+0, +0) px
    2026-11-18 The Cave of Evil Eye I  the same 2 frames: p50 0.00, p90 2.00, p99 3.96; crosshair - cursor
                                       (+30, +30) px
    (at 0 frames: p50 3.16, p90 7.2-7.6; at 1: 1.41 / 3.61; at 3: 2.0-2.2 / 5.10; of the frames only one
    shift fits, 143 and 135 say 2, 7 and 7 say 1)

What it means for a tool that relates the mouse to what is on screen (how far the player trails the figure):
read the mouse from the picture, or pair frame i with the "cur" of frame i - 2; frame i's own "cur" is 33 ms
early, ~4 px at the usual 2 px a frame. NOT FIXED in the recorder or the bank (the user, 2026-11-28: when more
footage is in to base it on - the 2 frames are two captures of one kind, on one machine). Not explained: the
crosshair's place against the mouse differs between the two captures (the hand cursor's tip is on "cur" in both,
so it is the client's drawing, not our log).

The mouse game's frames are found by the crosshair itself: the announcement panel before it shows example
pictures with crosshairs of their own, which never move; the game is the stretch where the found crosshair
moves frame after frame. Other kinds of Lie Detector (a click on a picture) draw the hand cursor: not read here.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))

NEAR = 110                    # px around the logged mouse in which the crosshair is looked for
RING = (22, 40)               # the crosshair's box, px a side (it is ~30 across)
RING_AREA = 150               # its green pixels, at least
SHIFTS = range(0, 6)          # frames
DENSE = (30, 10)              # the game: at least 10 frames with a moved crosshair within 30 frames either side


def green_centre(img: np.ndarray, cx: int, cy: int) -> tuple | None:
    """The middle of the bright-green crosshair nearest to (cx, cy) in a BGR frame, or None."""
    import cv2
    h, w = img.shape[:2]
    x0, y0 = max(0, cx - NEAR), max(0, cy - NEAR)
    crop = img[y0:min(h, cy + NEAR), x0:min(w, cx + NEAR)].astype(np.int16)
    if crop.size == 0:
        return None
    b, g, r = crop[..., 0], crop[..., 1], crop[..., 2]
    mask = ((g > 190) & (g - r > 70) & (g - b > 120)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for k in range(1, n):
        left, top, bw, bh, area = (int(v) for v in stats[k, :5])
        if area >= RING_AREA and RING[0] <= bw <= RING[1] and RING[0] <= bh <= RING[1]:
            x, y = x0 + left + bw / 2.0, y0 + top + bh / 2.0          # the box's middle: the ring is symmetric
            d = (x - cx) ** 2 + (y - cy) ** 2
            if best is None or d < best[0]:
                best = (d, x, y)
    return None if best is None else (best[1], best[2])


def game_stretch(drawn: list) -> tuple | None:
    """(first, last) frame of the mouse game: where the found crosshair moves frame after frame (a crosshair in
    the announcement panel's pictures stands still, or flips between two of them a few times)."""
    live = np.zeros(len(drawn) + 1, dtype=np.int64)
    for i in range(1, len(drawn)):
        live[i + 1] = live[i] + bool(drawn[i] and drawn[i - 1] and drawn[i] != drawn[i - 1])
    span, need = DENSE
    dense = [i for i in range(1, len(drawn)) if live[i + 1] - live[i]
             and live[min(len(drawn), i + span + 1)] - live[max(0, i - span)] >= need]
    return (dense[0], dense[-1]) if dense else None


def measure(cur: list, drawn: list, shifts=SHIFTS) -> dict | None:
    """The fit of the logged mouse (`cur`, per frame, None when outside the picture) to the drawn crosshair
    (`drawn`, per frame, None when not found) at each shift: the picture of frame i against the log of frame
    i - shift. Only frames where the mouse moved count. Per shift: the crosshair's place against the mouse (the
    median difference) and what is left after it (px: p50, p90, p99). `best` = the shift with the smallest p90;
    `votes` = per shift, the frames it alone fits (under 1.5 px, the next shift over 1 px worse)."""
    lo = max(shifts)
    moving = [i for i in range(lo, len(cur)) if drawn[i] and cur[i] and cur[i - 1] and cur[i] != cur[i - 1]
              and all(cur[i - k] for k in shifts)]
    if len(moving) < 20:
        return None
    out, per_frame = {"n": len(moving), "shifts": {}}, []
    for k in shifts:
        d = np.array([(drawn[i][0] - cur[i - k][0], drawn[i][1] - cur[i - k][1]) for i in moving], dtype=np.float64)
        off = np.median(d, axis=0)
        e = np.hypot(d[:, 0] - off[0], d[:, 1] - off[1])
        per_frame.append(e)
        out["shifts"][k] = {"offset": (float(off[0]), float(off[1])), "p50": float(np.percentile(e, 50)),
                            "p90": float(np.percentile(e, 90)), "p99": float(np.percentile(e, 99))}
    out["best"] = min(out["shifts"], key=lambda k: (out["shifts"][k]["p90"], out["shifts"][k]["p50"]))
    e = np.array(per_frame)                                             # shifts x frames
    order = np.sort(e, axis=0)
    clear = (order[0] < 1.5) & (order[1] - order[0] > 1.0)
    win = np.argmin(e, axis=0)
    ks = list(shifts)
    out["votes"] = {ks[j]: int(np.sum(clear & (win == j))) for j in range(len(ks)) if np.any(clear & (win == j))}
    return out


def section(d: Path) -> dict:
    """One Lie Detector section (a folder with video.json, frames.jsonl and its video): `measure` on its mouse game."""
    import frames as fr
    vid = fr.Video(d)
    rows = [r for r in (json.loads(l) for l in open(d / "frames.jsonl", encoding="utf-8") if l.strip())
            if not r.get("drop")][:len(vid)]
    cur = [tuple(r["cur"]) if r.get("cur") else None for r in rows]
    drawn = [None] * len(rows)
    for i, c in enumerate(cur):
        if c is None:
            continue
        img = vid.frame(i)
        if img is None:
            break
        drawn[i] = green_centre(img, int(round(c[0])), int(round(c[1])))
    vid.close()
    res = {"frames": len(rows), "dropped": vid.dropped}
    span = game_stretch(drawn)
    if span is None:
        return res
    a, b = span
    dt = float(np.median(np.diff([r["t"] for r in rows[a:b + 1]])))
    res.update(game=(a, b), seconds=rows[b]["t"] - rows[a]["t"], frame_ms=dt * 1000,
               found=sum(1 for i in range(a, b + 1) if drawn[i]),
               fit=measure(cur[a:b + 1], drawn[a:b + 1]))
    return res


def report(name: str, res: dict, say=print) -> None:
    say(name)
    if "game" not in res:
        say(f"  no mouse game found in its {res['frames']} frames (no moving green crosshair)")
        return
    a, b = res["game"]
    say(f"  the mouse game: frames {a}..{b} of the section ({res['seconds']:.1f} s), the crosshair found on "
        f"{res['found']} of {b - a + 1}; {res['dropped']} frames dropped in the recording")
    fit = res["fit"]
    if fit is None:
        say("  the mouse moved on too few frames to measure")
        return
    for k, s in fit["shifts"].items():
        say(f"  the picture against the logged mouse of {k} frames earlier: error px p50 {s['p50']:5.2f} "
            f"p90 {s['p90']:5.2f} p99 {s['p99']:6.2f}; crosshair - mouse ({s['offset'][0]:+.0f}, {s['offset'][1]:+.0f})")
    k = fit["best"]
    say(f"  -> the picture shows the logged mouse of {k} frames ({k * res['frame_ms']:.0f} ms) earlier "
        f"({fit['n']} moving frames; frames only one shift fits: {fit['votes']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sections", nargs="*", help="folder names in CORPUS/lie, or folders (default: every section)")
    ap.add_argument("--corpus", type=Path, default=None, help="the corpus folder (default: config.CORPUS)")
    a = ap.parse_args(argv)
    if a.corpus:
        os.environ["MAPLE_CORPUS"] = str(a.corpus)
    from maplebrain.config import corpus_root
    lie = corpus_root() / "lie"
    dirs = [Path(s) if Path(s).is_dir() else lie / s for s in a.sections] or sorted(p.parent for p in lie.glob("*/video.json"))
    if not dirs:
        print(f"no Lie Detector sections in {lie}")
        return 1
    for d in dirs:
        if not (d / "video.json").exists():
            print(f"{d}: not a section (no video.json)")
            continue
        report(d.name, section(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
