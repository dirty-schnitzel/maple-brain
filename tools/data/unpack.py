"""PNG files out of a recording's video, for the tools that open RUN/frames/*.png themselves (PLAN-data.md
section 5: only the validation tools read the video directly, through tools/perc/frames.py).

    python tools/data/unpack.py RUN                        every frame of the video -> RUN/frames/NNNNNN.png
    python tools/data/unpack.py RUN 120 000450.png 600-660 these frames: numbers, names, ranges (inclusive)
    python tools/data/unpack.py RUN --every 3              every 3rd frame (as the old recordings saved them)
    python tools/data/unpack.py RUN ... --out DIR          into DIR instead (a corpus recording is never written to)

RUN = a run folder or a corpus segment RECORDING#K (then: the segment's frames; --out, or the segment's work
folder). The files are the captured pixels as they are in the video: a recording's 1 px column error (xshift.txt)
is NOT undone in them, exactly like the PNG files of the old recordings - frames.read undoes it for both.
A frame whose PNG already exists is skipped.
"""
import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as fr  # noqa: E402


def wanted(args: list, have: list) -> list:
    """The frame numbers `args` name (numbers, NNNNNN.png names, A-B ranges), in the video's order; [] -> all."""
    if not args:
        return list(have)
    want = set()
    for a in args:
        if "-" in a and not a.endswith(".png"):
            lo, hi = (int(x) for x in a.split("-", 1))
            want |= {n for n in have if lo <= n <= hi}
        else:
            want.add(fr.number(a))
    missing = sorted(want - set(have))
    if missing:
        raise SystemExit(f"not in the video: {missing[:10]}{' ...' if len(missing) > 10 else ''}")
    return [n for n in have if n in want]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run")
    ap.add_argument("frames", nargs="*", help="numbers, names or A-B ranges (default: every frame)")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--holdout", action="store_true", help="RUN is a hold-out segment of the corpus (logged)")
    a = ap.parse_args(argv)
    c = fr.clip(a.run, a.holdout, "unpack.py")
    v = fr.video(c.run)
    if v is None:
        raise SystemExit(f"{c.run} has no video (video.json + frames.jsonl)")
    have = [n for n, _, _ in c.frames()] if c.seg else list(v.n)
    out = a.out or ((c.out if c.seg else c.run) / "frames")
    out.mkdir(parents=True, exist_ok=True)
    done = skipped = 0
    for n in wanted(a.frames, have)[::a.every]:
        path = out / fr.name_of(n)
        if path.exists():
            skipped += 1
            continue
        f = v.frame(v.at[n])
        if f is None:
            raise SystemExit(f"frame {n} does not read from the video")
        cv2.imwrite(str(path), f, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        done += 1
    print(f"{done} PNG files -> {out}" + (f" ({skipped} were there already)" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
