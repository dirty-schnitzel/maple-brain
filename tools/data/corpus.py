"""The recording corpus (PLAN-data.md sections 4-5): recordings filed by map with nobody looking at them.

    python tools/data/corpus.py add RUN [RUN ...] [--dry] [--full]     file a recording (a `record` walk, a --video
                                                                       hunt, or an old PNG recording: copied in as video)
    python tools/data/corpus.py add --dev MAP [MAP ...]                move a map to the dev group (before its first gate)
    python tools/data/corpus.py list [--segments]                      what the corpus holds, what is covered

The corpus is a folder (E:\\maple-corpus; the environment variable MAPLE_CORPUS or --corpus DIR names another):
  incoming/              where `python -m maplebrain record` writes
  recordings/NAME/       the recordings, as recorded (frames_*.mkv, frames.jsonl, keys.jsonl, ...); files read-only
  manifest.jsonl         one line per SEGMENT = one stay on one map inside one recording (the fields: `_line`)
  groups.json            the maps moved to dev by hand
  holdout_uses.jsonl     every time a tool opened a hold-out segment
  work/SEG/              what tools write for a segment (replays, labels); work/cuts/NAME/ = the cut sheets

`add RUN` does, in order:
 1. **checks** the recording: every chunk file reads (its first and last frame; --full: every frame), the video
    holds the frames frames.jsonl lists, the picture is the native 1366x768. A recording that was cut (the recorder
    killed) is repaired without re-encoding: the last chunk rewritten as a finished file (a stream copy), the frame
    count taken from the files. An old PNG recording is first copied into the corpus as video and every frame
    compared with its PNG (the PNG folder is left as it is).
 2. **cuts it into maps** with the bot's own map recogniser (nav/identify.py: the on-screen minimap against every
    map's): one look a second. A look names a new map only if the next two frames and the look a second later
    name it too. A frame where the recogniser finds no minimap window is looked at once more with the window
    measured on the nearest named frame (`Namer`): it can confirm that frame's map, never name another. Where the name
    changes, the frames between the two looks are named one by one: the old map ends at its last named frame, the
    new one starts at its first, the frames between them (the loading screen) belong to neither. Looks that can't
    tell (minimap closed, covered, moved) keep the map - unless the unnamed stretch lasts longer than KEEP_S: 35 of
    the client's 336 maps (shops, salons, job halls) have no minimap, so "town -> shop -> town" looks like a town
    with a hole; a longer hole is its own segment. Such a stretch is named by the portals when exactly one map
    without a minimap connects the maps before and after it and they do not connect directly; else it stays
    "unknown": kept, listed, out of the per-map numbers. Never a guessed name.
 3. per segment, from keys.jsonl: the attack presses and the time of the first (none = the map was only
    crossed), the presses of the marker key (Keys.note).
 4. writes the manifest lines and moves the recording to recordings/. Nothing is re-encoded.
A sheet per cut (the frames before, between and after it, the minimap corner 1:1) goes to work/cuts/NAME/:
looked at by eye once (gate f), never needed afterwards. `--dry` stops before step 4.

**Groups.** A map new to the corpus is `holdout` when crc32(its id as text) % 4 == 0 (about every 4th map), with
every later recording of it; the 7 maps used before the corpus (DEV_FIRST) and the maps of `add --dev` are `dev`.
Nobody tunes on hold-out maps: tools take segments through tools/perc/frames.py `clip`, which refuses a hold-out
segment without --holdout and logs each use here (`allow`).
"""
import argparse
import bisect
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(Path(__file__).parent))
import frames as fr  # noqa: E402

MCW = ROOT / "assets" / "mcw"
DEV_FIRST = (10003061, 10003062, 10004040, 10004041, 10005063, 10005064, 10005065)   # recorded before the corpus
KEEP_S = 2.0            # an unnamed stretch up to this long is a loading screen / a covered minimap, not a map visit
CONFIRM = 2             # a look naming a new map counts when this many following frames name it too - and the
                        # look a second later: no map is visited for under a second, a half-drawn minimap is
NO_MAP = 999999999      # a portal's toMap when it leads nowhere
KEEP_FILES = ("ticks.jsonl", "log.txt", "keys.jsonl", "xshift.txt", "notes.txt", "labels.json", "labels/cams.json",
              "labels/patches.json")           # what an old PNG recording brings along into the corpus


class Problem(Exception):
    """Why a recording can't be filed."""


# ---------------------------------------------------------------------------------------------- the corpus folder
def root() -> Path:
    return Path(os.environ.get("MAPLE_CORPUS") or r"E:\maple-corpus")


def load() -> list:
    """The manifest's lines, in file order."""
    p = root() / "manifest.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _save(lines: list) -> None:
    p = root() / "manifest.jsonl"
    tmp = p.with_suffix(".jsonl.new")
    tmp.write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
    os.replace(tmp, p)


def recording_dir(name: str) -> Path:
    return root() / "recordings" / name


def work_dir(seg: str) -> Path:
    d = root() / "work" / seg
    d.mkdir(parents=True, exist_ok=True)
    return d


def segment(seg: str) -> dict | None:
    return next((l for l in load() if l["seg"] == seg), None)


def segments_of(path: Path) -> list:
    """The manifest lines of the recording whose folder is `path` ([] when it is not a corpus recording)."""
    try:
        p = Path(path).resolve()
        if p.parent != (root() / "recordings").resolve():
            return []
    except OSError:
        return []
    return [l for l in load() if l["recording"] == p.name]


def dev_maps() -> set:
    p = root() / "groups.json"
    extra = json.loads(p.read_text(encoding="utf-8")).get("dev", []) if p.exists() else []
    return set(DEV_FIRST) | set(extra)


def group_of(map_id: int | None, dev: set | None = None) -> str | None:
    """dev / holdout by the rule (module docstring); None for an unknown stretch."""
    if map_id is None:
        return None
    if map_id in (dev_maps() if dev is None else dev):
        return "dev"
    return "holdout" if zlib.crc32(str(map_id).encode()) % 4 == 0 else "dev"


def allow(seg: dict, holdout: bool, tool: str) -> None:
    """A tool opens `seg`: refused (SystemExit) when it is a hold-out segment and --holdout was not given; a use
    with it is written to holdout_uses.jsonl."""
    if seg.get("group") != "holdout":
        return
    if not holdout:
        raise SystemExit(f"{seg['seg']} (map {seg['map']} {seg.get('name')}) is a HOLD-OUT segment: nobody tunes on "
                         "it, it runs only at gates - pass --holdout to use it (the use is logged)")
    with open(root() / "holdout_uses.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"when": datetime.now().isoformat(timespec="seconds"), "tool": tool, "seg": seg["seg"],
                            "map": seg["map"], "argv": sys.argv[1:]}) + "\n")


def to_dev(maps: list, say=print) -> None:
    """`add --dev MAP`: the map's segments (and every later one) are dev. Refused once a tool used it as hold-out."""
    p = root() / "groups.json"
    used = set()
    if (root() / "holdout_uses.jsonl").exists():
        used = {json.loads(l)["map"] for l in open(root() / "holdout_uses.jsonl", encoding="utf-8") if l.strip()}
    cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"dev": []}
    lines = load()
    for m in maps:
        if m in used:
            raise SystemExit(f"map {m} was already used as a hold-out map (holdout_uses.jsonl): it stays hold-out")
        if group_of(m) == "dev":
            say(f"map {m} {map_name(m)} is dev already")
            continue
        cur["dev"] = sorted(set(cur["dev"]) | {m})
        n = 0
        for l in lines:
            if l["map"] == m:
                l["group"], n = "dev", n + 1
        say(f"map {m} {map_name(m)} -> dev ({n} segment(s) in the corpus, and every later recording of it)")
    root().mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cur), encoding="utf-8")
    _save(lines)


# ------------------------------------------------------------------------------------------------- the game's data
_MAPS = {}


def map_json(map_id: int) -> dict:
    if map_id not in _MAPS:
        p = MCW / "maps" / str(map_id) / "map.json"
        _MAPS[map_id] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _MAPS[map_id]


def map_name(map_id: int | None) -> str:
    if map_id is None:
        return "unknown"
    m = map_json(map_id)
    return f"{m.get('streetName') or '?'} / {m.get('name') or '?'}"


def portals_out(map_id: int) -> set:
    return {p["toMap"] for p in map_json(map_id).get("portals") or []
            if p.get("toMap") not in (None, NO_MAP, map_id)}


def client_build() -> str:
    """Which client data the names came from: when assets/mcw was built from the client export."""
    from maplebrain.gamedata import load_manifest
    return load_manifest(MCW).get("built") or "?"


def between(p: int, q: int, nameless: set) -> int | None:
    """The one map without a minimap that connects map `p` to map `q`, when they do not connect directly."""
    if p == q or q in portals_out(p):
        return None
    cand = [x for x in portals_out(p) if x in nameless and q in portals_out(x)]
    return cand[0] if len(cand) == 1 else None


# ------------------------------------------------------------------------------------------ step 1: the check
def _packets(path: Path, fps: int = 60) -> tuple | None:
    """(frames in a chunk file, how many of them from its start without a hole in their times), from its packets
    (no decoding); None when ffprobe can't read it. The two differ only in a chunk whose ENCODER was killed: the
    encoder writes a frame that later ones lean on ahead of the frames shown before it, so the file can end with a
    frame whose predecessors never arrived (gate d, 2026-11-17: the last frame of the file was the picture of 4
    frames later). Only the frames before the hole are the recording's."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        at = sorted(round(float(x.split(",")[0]) * fps) for x in r.stdout.split())
    except ValueError:
        return None
    if r.returncode != 0 or not at:
        return None
    whole = next((k for k, v in enumerate(at) if v != at[0] + k), len(at))
    return len(at), whole


def _finish(path: Path, say) -> None:
    """A chunk whose writer was killed -> a finished file (a stream copy, nothing re-encoded): jumps are exact
    only then (tools/data/video_safety.py)."""
    fixed = path.with_name(path.stem + ".fixed.mkv")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-c", "copy",
                        str(fixed)], capture_output=True, text=True)
    if r.returncode != 0 or not fixed.exists():
        raise Problem(f"{path.name} can't be repaired: {r.stderr.strip()[-200:]}")
    os.chmod(path, stat.S_IWRITE)
    os.replace(fixed, path)
    say(f"  {path.name}: rewritten as a finished file (stream copy)")


def _ends(path: Path, count: int, shape: tuple, more: bool = False) -> str | None:
    """The cheap read check of a chunk: its first frame, its last (`count` - 1) and nothing after it (`more`: a
    cut chunk may hold frames after it). -> why not."""
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    try:
        ok, f = cap.read()
        if not ok:
            return "the first frame does not read"
        if f.shape != shape:
            return f"frames are {f.shape[1]}x{f.shape[0]}, not {shape[1]}x{shape[0]}"
        if count > 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, count - 1)
            if not cap.read()[0]:
                return f"frame {count - 1} (the last) does not read"
        if cap.read()[0] and not more:
            return f"holds more than the {count} frames expected"
    finally:
        cap.release()
    return None


def check(run: Path, full: bool = False, say=print) -> dict:
    """Step 1 on a video recording. Returns video.json's content (updated on disk when the recording was cut).
    Raises Problem."""
    run = Path(run)
    for need in ("video.json", "frames.jsonl"):
        if not (run / need).exists():
            raise Problem(f"no {need} in {run}")
    meta = json.loads((run / "video.json").read_text(encoding="utf-8"))
    if (meta["w"], meta["h"]) != (1366, 768):
        raise Problem(f"the video is {meta['w']}x{meta['h']}, not the native 1366x768")
    rows = [json.loads(l) for l in open(run / "frames.jsonl", encoding="utf-8")]
    listed = sum(1 for r in rows if not r.get("drop"))
    chunk = meta["chunk"]
    files = sorted(run.glob("frames_*.mkv"))
    if not files:
        raise Problem("no chunk files")
    if [f.name for f in files] != [meta["pattern"] % k for k in range(len(files))]:
        raise Problem(f"chunk files are not frames_0000 .. frames_{len(files) - 1:04d}")
    cut = not meta.get("closed") or meta.get("error")
    if cut:                                                  # the recorder was killed: trust the files
        say(f"  not closed by the recorder ({meta.get('error') or 'killed'}): repairing the last chunk")
        _finish(files[-1], say)
        counted = _packets(files[-1], meta["fps"])
        if counted is None:
            raise Problem(f"{files[-1].name} does not read after the repair")
        last = counted[1]
        if counted[0] != last:
            say(f"  {files[-1].name}: {counted[0] - last} frame(s) after a hole at its end (the encoder was killed): "
                "left out")
        total = chunk * (len(files) - 1) + last
        if total > listed:
            raise Problem(f"the video holds {total} frames, frames.jsonl lists only {listed}")
        say(f"  the video holds {total} of the {listed} frames listed: the last {listed - total} never reached the "
            "file")
        meta.update(frames=total, closed=True, cut=True, error=None, bytes=sum(f.stat().st_size for f in files),
                    chunks=len(files))
        (run / "video.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    total = meta["frames"]
    if not cut and total != listed:
        raise Problem(f"the video holds {total} frames, frames.jsonl lists {listed}")
    if len(files) != max(1, math.ceil(total / chunk)):
        raise Problem(f"{len(files)} chunk files for {total} frames of {chunk} a chunk")
    shape = (meta["h"], meta["w"], 3)
    for k, f in enumerate(files):
        count = chunk if k < len(files) - 1 else total - chunk * (len(files) - 1)
        tail = k == len(files) - 1 and meta.get("cut")          # (a cut chunk may hold frames after a hole: not read)
        why = _ends(f, count, shape, more=bool(tail))
        if why is None and full:
            n = _packets(f, meta["fps"])
            cap, got = cv2.VideoCapture(str(f), cv2.CAP_FFMPEG), 0
            while cap.grab():
                got += 1
            cap.release()
            if n is None or n[1] != count or got < count or (got != count and not tail):
                why = f"{n} packets (all, whole), {got} frames decode, {count} expected"
        if why:
            raise Problem(f"{f.name}: {why}")
    fr._VIDEOS.pop(str(run.resolve()), None)                 # (reopen with the checked frame count)
    say(f"  check: {len(files)} chunk file(s), {total} frames, {listed - total} listed but not in the video, "
        f"{len(rows) - listed} dropped while recording; 1366x768" + ("; every frame decoded" if full else ""))
    return meta


def import_png(run: Path, dest: Path, say=print) -> None:
    """An old PNG recording -> `dest` as video: its saved frames in order (bit-exact: every frame read back and
    compared with its PNG) + its small files. The PNG folder is not touched."""
    from maplebrain.runtime.video import VideoWriter
    rows = fr.saved(run)
    if not rows:
        raise Problem(f"no saved frames in {run}")
    if any(not n.endswith(".png") for _, n, _ in rows):
        raise Problem("JPEG frames are lossy: only PNG recordings enter the corpus")
    dest.mkdir(parents=True)
    dt = sorted(b[2] - a[2] for a, b in zip(rows, rows[1:]))
    vw = VideoWriter(dest, note={"by": "import", "source": str(run).replace("\\", "/"),
                                 "real_fps": round(1 / dt[len(dt) // 2], 1) if dt else None})
    for n, name, t in rows:
        f = cv2.imread(str(run / "frames" / name))
        if f is None or f.shape != (768, 1366, 3):
            vw.close()
            raise Problem(f"{name}: not a 1366x768 picture")
        vw.put(f, n, t, wait=True)
    meta = vw.close()
    if meta["error"] or meta["frames"] != len(rows):
        raise Problem(f"the encoder: {meta['error']} ({meta['frames']} of {len(rows)} frames)")
    for rel in KEEP_FILES:                                   # the recording's own files and its by-eye labels
        if (run / rel).is_file():
            (dest / rel).parent.mkdir(exist_ok=True)
            shutil.copy2(run / rel, dest / rel)
    v = fr.Video(dest)
    bad = 0
    for i, (n, name, t) in enumerate(rows):
        a, b = v.frame(i), cv2.imread(str(run / "frames" / name))
        bad += a is None or not np.array_equal(a, b)
    v.close()
    if bad:
        raise Problem(f"{bad} of {len(rows)} video frames differ from their PNG")
    say(f"  copied as video: {len(rows)} frames, every one identical to its PNG; {meta['bytes'] / 1e9:.2f} GB "
        f"(the PNG files: {sum((run / 'frames' / n).stat().st_size for _, n, _ in rows) / 1e9:.2f} GB)")


# ------------------------------------------------------------------------------------------ step 2: the cut
class Namer:
    """Frame index -> the map its minimap shows (None: can't tell), each frame looked at once.

    The recogniser measures the minimap window on every frame, and now and then it can't for a second or two
    while the minimap is in plain sight (a mob or a player drawn over the window's frame: 77 such frames in three
    of the 2026-11-16 recordings). So a frame it can't name is looked at once more with the window as measured on
    the nearest frame it DID name: if that frame's map is still the clear winner there (the recogniser's own bars:
    score and lead), the frame shows that map (`held`). This only ever confirms the map already named next to it,
    never names a new one - on the 737 frames of the dragged-window recording the stale window's best match is
    some other map (0.6-0.76) and nothing is confirmed. No minimap at all (a shop) confirms nothing either."""

    def __init__(self, run: Path, rows: list, ident, window=None):
        from maplebrain.nav.localize import find_window
        self.run, self.rows, self.ident = run, rows, ident
        self.window = window or find_window
        self.seen, self.luma = {}, {}
        self.wins, self.order = {}, []                       # row -> (map, its minimap window); the rows, sorted
        self.held = 0

    def _near(self, i: int):
        """(map, window) of the named frame nearest to row i, or None."""
        k = bisect.bisect_left(self.order, i)
        best = min(self.order[max(k - 1, 0):k + 1], key=lambda j: abs(j - i), default=None)
        return None if best is None else self.wins[best]

    def _hold(self, f, i: int) -> int | None:
        near = self._near(i)
        if near is None or near[1] is None:
            return None
        p, win = near
        ranked = sorted(((v[0], k) for k, v in self.ident.fits(f, win).items()), reverse=True)
        if not ranked or ranked[0][1] != p or ranked[0][0] < self.ident.min_score:
            return None
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < self.ident.lead:
            return None
        self.held += 1
        return p

    def __call__(self, i: int) -> int | None:
        if i not in self.seen:
            f = fr.read(self.run, self.rows[i][1])
            m = self.ident.identify([f]).map_id if f is not None else None
            if m is not None:
                self.wins[i] = (m, self.window(f))
                bisect.insort(self.order, i)
            elif f is not None:
                m = self._hold(f, i)
            self.seen[i] = m
            self.luma[i] = round(float(f[:700:8, ::8].mean()), 1) if f is not None else None
        return self.seen[i]

    def again(self, i: int) -> None:
        """Row i was looked at before any frame was named (the recording's start): look again when asked."""
        if self.seen.get(i, 0) is None:
            del self.seen[i]


def cut(run: Path, rows: list, ident, say=print, name=None) -> tuple:
    """The recording's frames `rows` [(n, name, t)] cut into maps (module docstring, step 2). Row indexes below.
    -> (segments in order [{"i": [first, last], "map": id or None, "how": "minimap" / "portals" / None}],
        cuts [{"a", "b": the unnamed rows between (b < a: none), "from", "to": maps, "s": seconds, "what"}],
        the Namer: every frame looked at). `name`: row index -> map id / None instead of the Namer (tests)."""
    name = name or Namer(run, rows, ident)
    t = [r[2] for r in rows]
    N = len(rows)
    dts = sorted(b - a for a, b in zip(t, t[1:]))
    stride = max(1, round(1 / max(dts[len(dts) // 2], 1e-3))) if dts else 1     # frames in a second
    idx = list(range(0, N, stride))
    if idx[-1] != N - 1:
        idx.append(N - 1)
    named, cur = [], None                                    # the looks that name a map: (row, map)
    for k, i in enumerate(idx):
        m = name(i)
        if m is not None and m != cur:                       # a new map: only if the next frames say so too,
            after = [*range(i + 1, i + 1 + CONFIRM), i + stride]         # and the look a second later
            if not all(name(j) == m for j in after if j < N):
                m = None
        if m is not None:
            cur = m
            named.append((i, m))
        if k % 300 == 299:
            say(f"  ... {k + 1} of {len(idx)} looks")
    if not named:
        return [{"i": [0, N - 1], "map": None, "how": None}], [], name
    for i in idx:                                            # the looks before the first name: once more, now that
        if i >= named[0][0]:                                 # a measured window is known
            break
        getattr(name, "again", lambda i: None)(i)
    nameless = {int(p.name) for p in (MCW / "maps").iterdir() if p.is_dir() and int(p.name) not in ident.canvases}
    segs, cuts = [], []

    def hole(a: int, b: int, p, q) -> bool:
        """Rows a..b carry no name, between map p and map q (None: the recording's start / end). Short -> a
        loading screen / a covered minimap: False. Long -> its own segment (named by the portals or unknown): True."""
        s = t[min(b + 1, N - 1)] - t[max(a - 1, 0)]
        long = s > KEEP_S
        x = between(p, q, nameless) if long and p is not None and q is not None else None
        if not long:
            what = "start" if p is None else "end" if q is None else "loading" if p != q else "covered"
        else:
            what = "portals" if x is not None else "unknown"
        cuts.append({"a": a, "b": b, "from": p, "to": q, "s": round(s, 2), "what": what, "map": x})
        if long:
            segs.append({"i": [a, b], "map": x, "how": "portals" if x is not None else None})
        return long

    start, m0 = named[0]
    while start > 0 and name(start - 1) == m0:               # back to the first frame that names the first map
        start -= 1
    if start > 0:
        hole(0, start - 1, None, m0)
    for (a, p), (b, q) in zip(named, named[1:]):
        if p == q and (b - a <= stride or t[b] - t[a] <= KEEP_S):
            continue                                         # the same map a look later, or a short hole in it
        lo, hi = a, b
        while lo + 1 < b and name(lo + 1) == p:              # the last frame of p's run after look a
            lo += 1
        while hi - 1 > lo and name(hi - 1) == q:             # the first frame of q's run before look b
            hi -= 1
        if hi == lo + 1:                                     # no unnamed frame between
            if p == q:
                continue
            segs.append({"i": [start, lo], "map": p, "how": "minimap"})
            cuts.append({"a": hi, "b": lo, "from": p, "to": q, "s": 0.0, "what": "direct", "map": None})
        else:
            if p == q and t[hi] - t[lo] <= KEEP_S:
                continue                                     # a short hole inside one map: the segment goes on
            segs.append({"i": [start, lo], "map": p, "how": "minimap"})
            hole(lo + 1, hi - 1, p, q)
        start = hi
    last, p = named[-1]
    while last + 1 < N and name(last + 1) == p:
        last += 1
    segs.append({"i": [start, last], "map": p, "how": "minimap"})
    if last < N - 1:
        hole(last + 1, N - 1, p, None)
    return segs, cuts, name


def sheet(run: Path, rows: list, c: dict, name: Namer, path: Path) -> None:
    """The picture of one cut for the by-eye check: the 3 frames before it, 3 across the unnamed frames, the 3
    after it (each with its frame number and the name the recogniser gave it), and the minimap corner of the frame
    before and the frame after at full size."""
    a, b, N = c["a"], c["b"], len(rows)
    before = [i for i in (a - 3, a - 2, a - 1) if 0 <= i < N]
    after = [i for i in (b + 1, b + 2, b + 3) if 0 <= i < N]
    mid = sorted({a, (a + b) // 2, b}) if b >= a else []

    def tile(i):
        f = fr.read(run, rows[i][1])
        m = name(i)
        small = cv2.resize(f, (455, 256), interpolation=cv2.INTER_AREA)
        label = f"frame {rows[i][0]}  t {rows[i][2]:.2f}  {m if m is not None else 'no name'}"
        cv2.rectangle(small, (0, 0), (454, 16), (0, 0, 0), -1)
        cv2.putText(small, label, (4, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        return small, f

    def row(ids):
        tiles = [tile(i)[0] for i in ids]
        while len(tiles) < 3:
            tiles.append(np.zeros((256, 455, 3), np.uint8))
        return np.hstack(tiles)

    grid = np.vstack([row(before), row(mid), row(after)])
    corner = np.zeros((768, 420, 3), np.uint8)
    for k, ids in enumerate((before[-1:], after[:1])):
        if ids:
            corner[k * 384:k * 384 + 380] = tile(ids[0])[1][:380, :420]
            cv2.putText(corner, f"frame {rows[ids[0]][0]}: {map_name(name(ids[0]))}"[:60], (4, k * 384 + 376),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.hstack([grid, corner]))


# ---------------------------------------------------------------------------- step 3: the keys of each segment
def presses(run: Path) -> tuple:
    """([attack press times], [marker key press times]) of the recording, on the frames' clock: the player's keys
    (keys.jsonl), or - a bot hunt has none - the bot's own presses from ticks.jsonl: a new swing in timings.v2
    (brain v2 presses once per swing; the hunts of 2026-11-17: 75 and 45, the logs' own counts), or for older
    brains the attack key going down in the held keys."""
    from maplebrain.config import Keys
    attack, marks = [], []
    keys = {Keys.attack, Keys.basic_attack}
    if (run / "keys.jsonl").exists():
        for l in open(run / "keys.jsonl", encoding="utf-8"):
            k = json.loads(l)
            if k.get("down") and k.get("key") in keys:
                attack.append(k["t"])
            elif k.get("down") and k.get("key") == Keys.note:
                marks.append(k["t"])
    elif (run / "ticks.jsonl").exists():
        was, swing = False, None
        for l in open(run / "ticks.jsonl", encoding="utf-8"):
            k = json.loads(l)
            tm = k.get("timings") or {}
            held = bool(keys & set(tm.get("held") or []))
            now = (tm.get("v2") or {}).get("swing")
            if (held and not was) or (now is not None and now != swing):
                attack.append(k["obs"]["t"])
            was, swing = held, now
    return attack, marks


def _line(rec: str, k: int, s: dict, rows: list, attack: list, marks: list, meta: dict, dev: set) -> dict:
    """One manifest line: segment `k` of recording `rec`."""
    a, b = s["i"]
    t0, t1 = rows[a][2], rows[b][2]
    hits = [x for x in attack if t0 <= x <= t1]
    m = s["map"]
    mj = map_json(m) if m is not None else {}
    return {"seg": f"{rec}#{k}", "recording": rec, "k": k,
            "frames": [rows[a][0], rows[b][0]],              # frame numbers (frames.jsonl "n"), inclusive
            "n_frames": b - a + 1, "t": [round(t0, 2), round(t1, 2)], "minutes": round((t1 - t0) / 60, 2),
            "map": m, "name": mj.get("name"), "street": mj.get("streetName"), "how": s["how"],
            "group": group_of(m, dev),
            "attacks": len(hits), "first_attack": round(hits[0], 2) if hits else None,
            "kind": "visited" if hits else "crossed",
            "marks": [round(x, 2) for x in marks if t0 <= x <= t1],
            "date": (meta.get("started") or "")[:10], "by": meta.get("by"), "client": client_build(),
            "added": datetime.now().isoformat(timespec="seconds")}


# ------------------------------------------------------------------------------------------------------ add
def _readonly(d: Path) -> None:
    for f in d.iterdir():
        if f.is_file() and (f.suffix == ".mkv" or f.name in ("frames.jsonl", "keys.jsonl", "ticks.jsonl")):
            os.chmod(f, stat.S_IREAD)


def add(run: Path, dry: bool = False, full: bool = False, say=print) -> list:
    """File one recording (module docstring). Returns its manifest lines (written unless `dry`)."""
    from maplebrain.nav.identify import MapIdentifier
    run = Path(run).resolve()
    name = run.name
    if any(l["recording"] == name for l in load()):
        raise Problem(f"{name} is in the corpus already")
    say(f"{name}:")
    png = not (run / "video.json").exists()
    dest = recording_dir(name)
    if png and not dry:                                      # an old PNG recording: a copy as video, then as any
        if dest.exists():
            raise Problem(f"{dest} exists but is not in the manifest: remove it first")
        try:
            import_png(run, dest, say)
        except Problem:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        src = dest
    else:
        src = run
    meta = {"by": "png", "started": datetime.fromtimestamp((run / "log.txt").stat().st_mtime).isoformat()} \
        if png and dry else check(src, full, say)
    if png:
        meta["started"] = datetime.strptime(name[:15], "%Y%m%d_%H%M%S").isoformat() if name[:8].isdigit() \
            else meta.get("started")
    rows = fr.saved(src)
    ident = MapIdentifier.load(MCW)
    segs, cuts, namer = cut(src, rows, ident, say)
    logged = fr._log_map(src)
    if logged is not None:                                   # a hunt / an observe run: one map, and its log names it
        other = sorted({s["map"] for s in segs if s["map"] not in (None, logged)})
        if other:
            raise Problem(f"the log says map {logged} {map_name(logged)}, the minimap names {other}: look at "
                          f"{root() / 'work' / 'cuts' / name}")
        segs = [{"i": [0, len(rows) - 1], "map": logged, "how": "log"}]
    attack, marks = presses(src)
    dev = dev_maps()
    lines = [_line(name, k, s, rows, attack, marks, meta, dev) for k, s in enumerate(segs)]
    out = root() / "work" / "cuts" / name
    for k, c in enumerate(cuts):
        sheet(src, rows, c, namer, out / f"cut_{k:03d}_{rows[max(c['a'] - 1, 0)][0]:06d}.png")
    if cuts or not dry:
        out.mkdir(parents=True, exist_ok=True)
        (out / "cuts.json").write_text(json.dumps(
            [dict(c, frames=[rows[min(c["a"], len(rows) - 1)][0], rows[max(c["b"], 0)][0]],
                  luma={rows[i][0]: namer.luma[i] for i in sorted(namer.luma)
                        if c["a"] - 30 <= i <= c["b"] + 30}) for c in cuts], indent=1), encoding="utf-8")
    looked = Counter("named" if m is not None else "no name" for m in namer.seen.values())
    if getattr(namer, "held", 0):
        looked["of them by the window measured on a frame beside it"] = namer.held
    say(f"  cut: {len(namer.seen)} frames looked at ({dict(looked)}), {len(cuts)} cut(s)"
        + (f"; sheets in {out}" if cuts else ""))
    for c in cuts:
        say(f"    frames {rows[min(c['a'], len(rows) - 1)][0]}..{rows[max(c['b'], 0)][0]} ({c['s']:.2f} s): "
            f"{map_name(c['from']) if c['from'] else 'start'} -> {map_name(c['to']) if c['to'] else 'end'}: "
            f"{c['what']}")
    for l in lines:
        say(f"  {l['seg']:24s} frames {l['frames'][0]:>6}..{l['frames'][1]:<6} {l['minutes']:6.2f} min  "
            f"{l['group'] or '-':7s} {l['kind']:7s} {l['attacks']:4d} attacks  "
            f"{str(l['map'] or ''):>9} {map_name(l['map'])}" + (f"  [{l['how']}]" if l["how"] != "minimap" else "")
            + (f"  marks {len(l['marks'])}" if l["marks"] else ""))
    if dry:
        say("  --dry: nothing written")
        return lines
    fr._VIDEOS.pop(str(src.resolve()), None)                 # (let go of the chunk file before it moves)
    for v in list(fr._VIDEOS.values()):
        if v is not None:
            v.close()
    namer.ident = None
    if src != dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    _readonly(dest)
    _save(load() + lines)
    say(f"  filed: {dest} ({sum(f.stat().st_size for f in dest.glob('frames_*.mkv')) / 1e9:.2f} GB), "
        f"{len(lines)} segment(s) in the manifest")
    return lines


# ----------------------------------------------------------------------------------------------------- list
def report(segments: bool = False, say=print) -> None:
    """What the corpus holds (PLAN-data.md section 4): per map its minutes and attack presses; the mob types and
    background sets covered out of those the game has; for each one not seen yet, the maps it lives on."""
    import map_cover
    lines = load()
    if not lines:
        say(f"{root()}: empty")
        return
    recs = sorted({l["recording"] for l in lines})
    gb = sum(f.stat().st_size for r in recs for f in recording_dir(r).glob("frames_*.mkv")) / 1e9
    known = [l for l in lines if l["map"] is not None]
    say(f"{root()}: {len(recs)} recording(s), {len(lines)} segment(s), {sum(l['minutes'] for l in lines):.1f} "
        f"minutes, {gb:.1f} GB")
    per = defaultdict(list)
    for l in known:
        per[l["map"]].append(l)
    say(f"\n{'map':>9}  {'name':44s} {'group':7s} {'stays':>5} {'crossed':>7} {'minutes':>7} {'attacks':>7} {'marks':>5}")
    for m, ls in sorted(per.items(), key=lambda kv: -sum(l["minutes"] for l in kv[1])):
        say(f"{m:>9}  {map_name(m)[:44]:44s} {ls[0]['group']:7s} {len(ls):5d} "
            f"{sum(l['kind'] == 'crossed' for l in ls):7d} {sum(l['minutes'] for l in ls):7.1f} "
            f"{sum(l['attacks'] for l in ls):7d} {sum(len(l['marks']) for l in ls):5d}")
    unk = [l for l in lines if l["map"] is None]
    if unk:
        say(f"\nunknown stretches (kept, out of the per-map numbers): {len(unk)}, "
            f"{sum(l['minutes'] for l in unk):.1f} minutes")
        for l in unk:
            say(f"  {l['seg']}: frames {l['frames'][0]}..{l['frames'][1]}, {l['minutes']:.2f} min")
    if segments:
        say("\nsegments:")
        for l in lines:
            say(f"  {l['seg']:24s} {l['date']} frames {l['frames'][0]:>6}..{l['frames'][1]:<6} {l['minutes']:6.2f} min "
                f"{l['group'] or '-':7s} {l['kind']:7s} {l['attacks']:4d} attacks  {map_name(l['map'])}")
    # coverage: from the client data (map_cover: a mob type counts on a map with 3+ spawn points of it)
    maps, mobs = map_cover.load()
    if not maps:
        say("")
        say("coverage: needs the scene models (python -m maplebrain assets scene)")
        return
    clean = [m for m in maps.values() if m["clean"]]
    all_items = set().union(*[map_cover.items(m) for m in maps.values()])
    clean_items = set().union(*[map_cover.items(m) for m in clean])
    stayed = {m for m, ls in per.items() if any(l["kind"] == "visited" for l in ls)}
    got = set().union(*[map_cover.items(maps[m]) for m in stayed if m in maps]) if stayed else set()
    passed = (set().union(*[map_cover.items(maps[m]) for m in per if m in maps]) if per else set()) - got

    def n(s, kind):
        return len({x for x in s if x[0] == kind})

    say(f"\ncoverage ({len(per)} maps: {len(stayed)} fought on, {len(per) - len(stayed)} only crossed; "
        f"{sum(group_of(m) == 'holdout' for m in per)} hold-out):")
    for kind, label in (("mob", "mob types"), ("set", "background sets")):
        say(f"  {label}: {n(got & clean_items, kind)} of {n(clean_items, kind)} on clean maps (the ones perception "
            f"hunts on), {n(got, kind)} of {n(all_items, kind)} in all"
            + (f"; {n(passed, kind)} more on maps only crossed" if n(passed, kind) else ""))
    missing = sorted(clean_items - got, key=lambda x: (x[0], str(mobs[x[1]]["name"]) if x[0] == "mob" else x[1]))
    if missing:
        say("  not seen yet on a clean map -> the clean maps it lives on:")
        for kind, i in missing:
            where = sorted((m for m in clean if (kind, i) in map_cover.items(m)), key=lambda m: -m["spawns"])
            label = (f"{mobs[i]['name']} (lv {mobs[i]['info'].get('level', '?')})" if kind == "mob"
                     else f"background set {i}")
            say(f"    {label}: " + "; ".join(f"{m['name']} ({m['id']})" for m in where[:4])
                + (f" + {len(where) - 4} more" if len(where) > 4 else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", type=Path, default=None, help="the corpus folder (default: E:\\maple-corpus)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="file recordings: check, cut into maps, manifest lines, move to recordings/")
    a.add_argument("runs", type=Path, nargs="*")
    a.add_argument("--dry", action="store_true", help="check + cut + the cut sheets, nothing written or moved")
    a.add_argument("--full", action="store_true", help="the check decodes every frame (minutes per hour recorded)")
    a.add_argument("--dev", type=int, nargs="+", default=None, metavar="MAP",
                   help="move these maps to the dev group (before their first gate)")
    ls = sub.add_parser("list", help="what the corpus holds and what is covered")
    ls.add_argument("--segments", action="store_true", help="every segment too (the names tools take)")
    args = ap.parse_args(argv)
    if args.corpus:
        os.environ["MAPLE_CORPUS"] = str(args.corpus)
    if args.cmd == "add":
        if not args.runs and not args.dev:
            ap.error("add: a recording folder, or --dev MAP")
        if args.dev:
            to_dev(args.dev)
        bad = 0
        for run in args.runs:
            try:
                add(run, args.dry, args.full)
            except Problem as e:
                bad += 1
                print(f"  NOT ADDED: {e}")
        if args.runs and not args.dry:
            print()
            report()
        return 1 if bad else 0
    report(args.segments)
    return 0


if __name__ == "__main__":
    sys.exit(main())
