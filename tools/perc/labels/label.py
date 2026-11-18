"""By-eye judgments of the label sheets (patches.py) -> RUN/labels.json v2 (PLAN-perception.md step 3.0a).

    python tools/perc/labels/label.py RUN JUDGED.jsonl

JUDGED.jsonl (in git, tools/perc/labels/<run>_judged.jsonl), one line per sheet looked at:
    {"n": 78, "t": "a21 b19 c21 d19e en f19p g21 h19", "add": [[1210, 745, 19, "x"]], "unsure": [[670, 340]]}
"t": one token per track letter on the sheet (the recording's tracks, patches.json):
    <letter><type>[classes][@x,y]  a real mob of that type (19 Horny, 21 Zombie Mushroom ...) at the track's feet,
                                   or at @x,y (screen feet) when the marker is off it
    <letter>n                      nothing there (a false track)
    <letter>?                      can't tell (covered by something opaque, too small, ...): neither found nor false
"add": mobs no track marks: [x, y, type, classes] (screen feet; y may be under the play area for a mob at its edge).
"unsure": spots that may be a mob (a faint shape, ...): [x, y] - tracks there count neither way.
Classes (letters, any number; none = clear): e effect / damage number over it, p a player / pet / name tag / our
body over it, s scenery drawn in front, u UI (chat, minimap, HUD) over it, f see-through (fading in / out),
d dying (death animation), x at the screen edge (part of it off screen), h hit pose.
Every mob of the frame is judged: a real mob neither tracked nor added is a labelling error.

labels.json v2: {"v": 2, "run", "frames": {n: {"mobs": [{"feet": [x, y], "type": id, "cls": "ep"}],
"unsure": [[x, y]], "false": [[x, y]]}}} ("false" = the recording's tracks judged empty: for checking only).
"""
import argparse
import json
import re
from pathlib import Path

CLASSES = {"e": "effect", "p": "player", "s": "scenery", "u": "ui", "f": "fade", "d": "dying", "x": "edge", "h": "hit"}
TOKEN = re.compile(r"^([a-z])(n|\?|(\d+)([epsufdxh]*)(?:@(-?\d+),(-?\d+))?)$")


def parse(rec: dict, tracks: list) -> dict:
    letters = "abcdefghijklmnopqrstuvwxyz"
    mobs, unsure, false, seen = [], [list(u) for u in rec.get("unsure") or []], [], set()
    for tok in (rec.get("t") or "").split():
        m = TOKEN.match(tok)
        if not m:
            raise ValueError(f"n{rec['n']}: bad token {tok!r}")
        i = letters.index(m.group(1))
        if i >= len(tracks):
            raise ValueError(f"n{rec['n']}: {tok!r} but only {len(tracks)} tracks")
        seen.add(i)
        _, _, sx, sy = tracks[i][:4]
        if m.group(2) == "n":
            false.append([sx, sy])
        elif m.group(2) == "?":
            unsure.append([sx, sy])
        else:
            x, y = (int(m.group(5)), int(m.group(6))) if m.group(5) else (sx, sy)
            mobs.append({"feet": [x, y], "type": int(m.group(3)), "cls": m.group(4)})
    if len(seen) != len(tracks):
        raise ValueError(f"n{rec['n']}: tracks not judged: {sorted(set(range(len(tracks))) - seen)}")
    for x, y, typ, cls in rec.get("add") or []:
        if set(cls) - set(CLASSES):
            raise ValueError(f"n{rec['n']}: bad classes {cls!r}")
        mobs.append({"feet": [x, y], "type": typ, "cls": cls})
    return {"mobs": mobs, "unsure": unsure, "false": false}


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import frames as rec
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="a run folder, or a corpus segment RECORDING#K (its labels go to its work folder)")
    ap.add_argument("judged", type=Path)
    ap.add_argument("--holdout", action="store_true", help="RUN is a hold-out segment of the corpus: only at gates (the use is logged)")
    a = ap.parse_args()
    c = rec.clip(a.run, a.holdout, "labels/label.py")
    pj = json.loads(c.find("labels/patches.json").read_text())
    frames = {}
    for line in open(a.judged, encoding="utf-8"):
        if line.strip():
            rec = json.loads(line)
            frames[str(rec["n"])] = parse(rec, pj[str(rec["n"])]["tracks"])
    out = {"v": 2, "run": str(a.run).replace("\\", "/"), "frames": frames}
    c.keep.mkdir(parents=True, exist_ok=True)
    (c.keep / "labels.json").write_text(json.dumps(out, indent=0))
    n = sum(len(f["mobs"]) for f in frames.values())
    by = {}
    for f in frames.values():
        for m in f["mobs"]:
            for c in m["cls"] or "c":
                by[c] = by.get(c, 0) + 1
    print(f"{len(frames)} frames, {n} mobs, {sum(len(f['false']) for f in frames.values())} tracks judged empty, "
          f"{sum(len(f['unsure']) for f in frames.values())} unsure; classes {by} -> {c.keep / 'labels.json'}")


if __name__ == "__main__":
    main()
