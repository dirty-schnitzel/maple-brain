"""The recording corpus (PLAN-data.md sections 4-5; the layout: the user, 2026-11-18): every recording filed by
map with nobody looking at it - the one bank perception, the live map, tracking and later training are tested on.

    python tools/data/corpus.py add RUN [RUN ...] [--dry] [--full] [--keep]     file a recording (a `record` walk, a
                                                                                --video hunt, an old PNG recording)
    python tools/data/corpus.py add --dev MAP [MAP ...]                         move a map to the dev group
    python tools/data/corpus.py list [--stays]                                  what the corpus holds, what is covered
    python tools/data/corpus.py verify [--frames] [STAY ...]                    are the files what was filed?

The corpus is a folder (maplebrain/config.py CORPUS: F:\\dev\\maple-corpus for now, E: later; the environment variable
MAPLE_CORPUS or --corpus DIR names another - nothing in it holds a drive letter, so the folder moves as it is):
  README.txt             this layout, in the bank itself
  index.txt              `list`'s report, rewritten by every `add`
  incoming/              where `python -m maplebrain record` writes; `add` empties it
  maps/<map name> (<map id>)/<stay>/      THE FOOTAGE: one folder per stay = one visit to one map
  maps/_unknown/<stay>/                   stretches nobody could name (a shop has no minimap; the minimap closed)
  holdout/<map name> (<map id>)/<stay>/   the same for the hold-out maps (below): apart, nothing opens them by accident
  sessions/SESSION/      one per recording; SESSION = its folder name as recorded (20261118_143205_1): session.json
                         (the facts of the day, runtime/session.py), log.txt, notes.txt, the whole keys.jsonl and
                         frames.jsonl, route.txt (its stays in order), cuts/ (a sheet per cut)
  manifest.jsonl         one line per stay (`_line`): the index tools read; the same line is the stay's stay.json
  groups.json            the maps moved to dev by hand
  holdout_uses.jsonl     every time a tool opened a hold-out stay
  labels/SESSION#K/      a stay's by-eye labels (nobody can make them again)
  work/SESSION#K/        what tools write for a stay (replays): safe to delete; work/cuts/SESSION = a dry run's sheets

**A stay** has a permanent id, `SESSION#K` (K = its number in the session): what labels, gates and tools use. Its
folder is named for people: <date>_<time it began>_<mode>_<length>_s<K>, e.g. 2026-11-18_1432_farming_12m05s_s03.
The mode (`mode_of`): `farming` (FARM_ATTACKS or more attack presses), `traveling` (crossed), `town` (TOWN_S or
longer on a map without mobs), `idle` (IDLE_S or longer without fighting), `scene-NAME` (`record --scene NAME`),
`bot` (a bot hunt). Nothing but people reads a name, so a better rule can rename folders without breaking a label.
In the folder:
  <map name>_<stay>_000.mkv ...  its frames, lossless, 5-minute files (runtime/video.py)
  frames.jsonl   one line per frame: n = its number in the session, t = the session's clock, cur / b = the mouse,
                 h = its fingerprint (the first 16 hex digits of the sha256 of its pixels, as stored); "drop" =
                 listed by the recorder but never in the video
  keys.jsonl     the session's key lines inside the stay's time
  stay.json      its manifest line          video.json   the stream (the reader's)
  sheet.jpg, preview.mp4   nine frames across it; a small ordinary video for watching (the lossless files do not
                 play in every player). For people: no tool reads them.
  ticks.jsonl, log.txt     a hunt / an observe run (one map by construction) brings its own files along
A stay's files begin with the frames nobody could name before it - its loading screen (`arrive` of them): every
frame of a session is in exactly one stay. Tools get the frames ON the map (`frames`).

`add RUN` does, in order:
 1. **checks** the recording: every chunk file reads (its first and last frame; --full: every frame), the video
    holds the frames frames.jsonl lists, the picture is the native 1366x768. A recording that was cut (the recorder
    killed) is repaired without re-encoding: the last chunk rewritten as a finished file (a stream copy), the frame
    count taken from the files.
 2. **cuts it into maps** with the bot's own map recogniser (nav/identify.py: the on-screen minimap against every
    map's): one look a second. A look names a new map only if the next two frames and the look a second later
    name it too. A frame where the recogniser finds no minimap window is looked at once more with the window
    measured on the nearest named frame (`Namer`): it can confirm that frame's map, never name another. Where the name
    changes, the frames between the two looks are named one by one: the old map ends at its last named frame, the
    new one starts at its first, the frames between them (the loading screen) belong to neither. Looks that can't
    tell (minimap closed, covered, moved) keep the map - unless the unnamed stretch lasts longer than KEEP_S: 35 of
    the client's 336 maps (shops, salons, job halls) have no minimap, so "town -> shop -> town" looks like a town
    with a hole; a longer hole is its own stay. Such a stretch is named by the portals when exactly one map
    without a minimap connects the maps before and after it and they do not connect directly; else it stays
    "unknown": kept, listed, out of the per-map numbers. Never a guessed name. A recording with a log that names
    its map (a hunt, an observe run: perception is tied to one map) is one stay on that map; the minimap is still
    looked at and must not name another.
 3. per stay, from keys.jsonl: the attack presses and the time of the first, the presses of the marker key
    (Keys.note) - and from them the mode.
 4. **files every stay**: its frames read from the recording in order, written losslessly into the stay's folder,
    read back and compared frame by frame (the fingerprints). Then the session's small files, the manifest lines,
    index.txt. Only when every frame of the recording is proven to be in a stay is the original removed - and
    only an original inside incoming/ (--keep: not even that; a folder elsewhere, like a PNG recording under
    runs/, is never touched).
A sheet per cut (the frames before, between and after it, the minimap corner 1:1) goes to sessions/SESSION/cuts/
(--dry: work/cuts/SESSION/): looked at by eye once (gate f). `--dry` stops before step 4.

**Groups.** A map new to the corpus is `holdout` when crc32(its id as text) % 4 == 0 (about every 4th map), with
every later recording of it; the 7 maps used before the corpus (DEV_FIRST) and the maps of `add --dev` are `dev`.
Nobody tunes on hold-out maps: tools take stays through tools/perc/frames.py `clip`, which refuses a hold-out
stay without --holdout and logs each use here (`allow`).
"""
import argparse
import bisect
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
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
FARM_ATTACKS = 5        # this many attack presses during a stay = the map was farmed (fewer: a mob in the way)
TOWN_S = 60.0           # this long on a map without mobs = a stop in town, not a crossing
IDLE_S = 180.0          # this long on a map with mobs without fighting = standing around, not a crossing
WITH_FRAMES = ("xshift.txt",)                                # goes wherever a recording's frames go
ONE_MAP_FILES = ("ticks.jsonl", "log.txt", "notes.txt")      # a one-stay recording's own files: into its stay
LABEL_FILES = ("labels.json", "labels/cams.json", "labels/patches.json")     # its by-eye labels: into labels/
SESSION_FILES = ("session.json", "log.txt", "notes.txt", "keys.jsonl", "frames.jsonl", "video.json")
LOCKED = ("frames.jsonl", "keys.jsonl", "ticks.jsonl")       # read-only in a stay's folder, with its video files
V = 2                   # the manifest line's version (1 = the first layout: whole recordings under recordings/)


class Problem(Exception):
    """Why a recording can't be filed."""


# ---------------------------------------------------------------------------------------------- the corpus folder
def root() -> Path:
    from maplebrain.config import corpus_root
    return corpus_root()


def load() -> list:
    """The manifest's lines, in file order."""
    p = root() / "manifest.jsonl"
    if not p.exists():
        return []
    lines = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if any(l.get("v") != V for l in lines):
        raise Problem(f"{root()} is laid out the old way (whole recordings under recordings/): file its recordings "
                      "again into an empty corpus folder")
    return lines


def _save(lines: list) -> None:
    p = root() / "manifest.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".jsonl.new")
    tmp.write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
    os.replace(tmp, p)


def stay_dir(seg: dict) -> Path:
    """The folder of a stay (its manifest line): the frames, never written to."""
    return root() / seg["path"]


def work_dir(seg: str) -> Path:
    d = root() / "work" / seg
    d.mkdir(parents=True, exist_ok=True)
    return d


def labels_dir(seg: str) -> Path:
    """Where the by-eye labels of stay `seg` are kept (made by the tool that writes the first)."""
    return root() / "labels" / seg


def segment(seg: str) -> dict | None:
    return next((l for l in load() if l["seg"] == seg), None)


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
    """A tool opens the stay `seg`: refused (SystemExit) when it is on a hold-out map and --holdout was not given;
    a use with it is written to holdout_uses.jsonl."""
    if seg.get("group") != "holdout":
        return
    if not holdout:
        raise SystemExit(f"{seg['seg']} (map {seg['map']} {seg.get('name')}) is a HOLD-OUT stay: nobody tunes on "
                         "it, it runs only at gates - pass --holdout to use it (the use is logged)")
    with open(root() / "holdout_uses.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"when": datetime.now().isoformat(timespec="seconds"), "tool": tool, "seg": seg["seg"],
                            "map": seg["map"], "argv": sys.argv[1:]}) + "\n")


def _write_stay(line: dict) -> None:
    """The stay's own copy of its manifest line."""
    p = stay_dir(line) / "stay.json"
    if p.exists():
        os.chmod(p, stat.S_IWRITE)
    p.write_text(json.dumps(line, indent=1), encoding="utf-8")


def to_dev(maps: list, say=print) -> None:
    """`add --dev MAP`: the map's stays (and every later one) are dev, its folder moves from holdout/ to maps/.
    Refused once a tool used it as hold-out."""
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
                old = stay_dir(l)
                l["group"], l["path"], n = "dev", "maps/" + l["path"].split("/", 1)[1], n + 1
                if old.exists():
                    stay_dir(l).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old), str(stay_dir(l)))
                    _write_stay(l)
                    if not any(old.parent.iterdir()):
                        old.parent.rmdir()
        say(f"map {m} {map_name(m)} -> dev ({n} stay(s) in the corpus, and every later recording of it)")
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


# ------------------------------------------------------------------------------- step 3: the keys of each stay
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


# --------------------------------------------------------------------------- step 4: the stays and their names
def safe(text, limit: int = 60) -> str:
    """A map's name as a folder / file name: without what Windows (or a file pattern) refuses - Line 1 <Area 1>
    -> Line 1 Area 1."""
    s = re.sub(r'[<>:"/\\|?*%\x00-\x1f]', "", str(text))
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:limit].rstrip(" .") or "map"


def map_folder(map_id: int | None) -> str:
    return "_unknown" if map_id is None else f"{safe(map_json(map_id).get('name') or 'map')} ({map_id})"


def mode_of(scene, bot: bool, attacks: int, seconds: float, mobs: bool | None) -> str:
    """What a stay was (module docstring). `mobs`: does the map have mobs (None: an unknown map)."""
    if scene:
        return "scene-" + (re.sub(r"[^a-z0-9]+", "-", str(scene).lower()).strip("-") or "x")
    if bot:
        return "bot"
    if attacks >= FARM_ATTACKS:
        return "farming"
    if mobs is False and seconds >= TOWN_S:
        return "town"
    return "idle" if seconds >= IDLE_S else "traveling"


def length(seconds: float) -> str:
    return f"{int(seconds) // 60}m{int(seconds) % 60:02d}s"


def stay_name(began: datetime, mode: str, seconds: float, k: int) -> str:
    return f"{began:%Y-%m-%d_%H%M}_{mode}_{length(seconds)}_s{k:02d}"


def began_at(run: Path, facts: dict, meta: dict) -> datetime:
    """The wall clock at t = 0 of a recording: session.json's (the recorder wrote it), else the time in the
    folder's name (<YYYYmmdd_HHMMSS>_k: every run folder is named so), else the video's / the folder's own."""
    if facts.get("epoch"):
        return datetime.fromtimestamp(facts["epoch"])
    try:
        return datetime.strptime(run.name[:15], "%Y%m%d_%H%M%S")
    except ValueError:
        pass
    if meta.get("started") and meta.get("by") not in ("import", "png"):
        return datetime.fromisoformat(meta["started"])
    return datetime.fromtimestamp(run.stat().st_mtime)


def bounds(segs: list, n: int) -> list:
    """Per stay the rows its FILES hold, (first, last): from the row after the stay before it - the frames nobody
    could name in between, its loading screen - to its own last row; the last stay also takes what follows it.
    Every row of the recording is in exactly one stay."""
    out, nxt = [], 0
    for k, s in enumerate(segs):
        if s["i"][0] < nxt or s["i"][1] < s["i"][0]:
            raise Problem(f"the cut is out of order at stay {k}: rows {s['i']} after row {nxt - 1}")
        last = n - 1 if k == len(segs) - 1 else s["i"][1]
        out.append((nxt, last))
        nxt = last + 1
    return out


def _keys(run: Path) -> list:
    """[(the key event, its line as recorded)] of keys.jsonl, in order."""
    p = run / "keys.jsonl"
    if not p.exists():
        return []
    return [(json.loads(raw), raw) for raw in p.read_text(encoding="utf-8").splitlines() if raw.strip()]


def _held(keys: list, t: float) -> list:
    """The keys held down at time `t` (pressed before it and not yet released): a stay can begin mid-press."""
    down = set()
    for k, _ in keys:
        if k.get("t", 0.0) >= t:
            break
        (down.add if k.get("down") else down.discard)(k.get("key"))
    return sorted(x for x in down if x)


def _line(ses: str, k: int, s: dict, bound: tuple, rows: list, attack: list, marks: list, keys: list,
          start: datetime, facts: dict, by: str | None, dev: set) -> dict:
    """One manifest line: stay `k` of session `ses` (the fields filing adds: n_file is checked, files, bytes)."""
    a, b = s["i"]
    fa, fb = bound
    t0, t1 = rows[a][2], rows[b][2]
    hits = [x for x in attack if t0 <= x <= t1]
    m = s["map"]
    mj = map_json(m) if m is not None else {}
    group = group_of(m, dev)
    mode = mode_of(facts.get("scene"), by == "bot", len(hits), t1 - t0, bool(mj.get("mobs")) if mj else None)
    began = start + timedelta(seconds=t0)
    stay = stay_name(began, mode, t1 - t0, k)
    return {"v": V, "seg": f"{ses}#{k}", "session": ses, "k": k, "stay": stay,
            "path": f"{'holdout' if group == 'holdout' else 'maps'}/{map_folder(m)}/{stay}",
            "map": m, "name": mj.get("name"), "street": mj.get("streetName"), "how": s["how"], "group": group,
            "mode": mode, "scene": facts.get("scene"), "by": by,
            "frames": [rows[a][0], rows[b][0]],              # the frames ON the map (frames.jsonl "n"), inclusive
            "n_frames": b - a + 1,
            "file_frames": [rows[fa][0], rows[fb][0]],       # the frames in its files: + the loading screen before
            "n_file": fb - fa + 1, "arrive": a - fa,
            "t": [round(t0, 2), round(t1, 2)], "minutes": round((t1 - t0) / 60, 2),
            "began": began.isoformat(timespec="seconds"), "date": f"{began:%Y-%m-%d}",
            "attacks": len(hits), "first_attack": round(hits[0], 2) if hits else None,
            "marks": [round(x, 2) for x in marks if t0 <= x <= t1], "held": _held(keys, rows[fa][2]),
            "client": facts.get("client") or client_build(), "code": (facts.get("code") or {}).get("commit"),
            "added": datetime.now().isoformat(timespec="seconds")}


# ------------------------------------------------------------------------------------------ step 4: the filing
def fingerprint(frame: np.ndarray) -> str:
    """A frame's fingerprint: the first 16 hex digits of the sha256 of its pixels (BGR, row by row, as stored)."""
    return hashlib.sha256(memoryview(np.ascontiguousarray(frame)).cast("B")).hexdigest()[:16]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while part := f.read(1 << 22):
            h.update(part)
    return h.hexdigest()


def _remove(path: Path) -> None:
    """A folder gone, read-only files included."""
    def retry(fn, p, _):
        os.chmod(p, stat.S_IWRITE)
        fn(p)
    shutil.rmtree(path, onerror=retry)


def _sheet(tiles: list, line: dict, path: Path) -> None:
    """sheet.jpg: nine frames across the stay, each with its time into the stay and its frame number."""
    cells = []
    for n, t, small in tiles:
        s = t - line["t"][0]
        cv2.rectangle(small, (0, 0), (454, 16), (0, 0, 0), -1)
        cv2.putText(small, f"{int(s) // 60}:{int(s) % 60:02d}  frame {n}", (4, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (255, 255, 255), 1)
        cells.append(small)
    cells += [np.zeros((256, 455, 3), np.uint8)] * (9 - len(cells))
    grid = np.vstack([np.hstack(cells[r:r + 3]) for r in (0, 3, 6)])
    top = np.zeros((24, grid.shape[1], 3), np.uint8)
    cv2.putText(top, f"{map_name(line['map'])} ({line['map']})   {line['stay']}   {line['seg']}"[:150], (6, 17),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    ok, buf = cv2.imencode(".jpg", np.vstack([top, grid]), [cv2.IMWRITE_JPEG_QUALITY, 85])
    if ok:
        buf.tofile(str(path))


def file_stay(src: Path, rows: list, line: dict, bound: tuple, index: list, keys: list, one_map: bool,
              say=print) -> dict:
    """One stay into its folder (module docstring): the rows `bound` of the recording `src` read in order and
    written as lossless video, each frame's fingerprint taken from the pixels as read; then its small files.
    `index`: the recorder's own lines per frame (frames.jsonl; [] when the recording has none), `keys`: `_keys`.
    Fills in `line` (files, bytes) and returns it. The proof is `read_back`, which the caller runs before it
    trusts the stay. Raises Problem; the caller removes what was made."""
    from maplebrain.runtime.video import VideoWriter
    dest = stay_dir(line)
    if dest.exists():
        raise Problem(f"{dest} exists already")
    dest.mkdir(parents=True)
    fa, fb = bound
    stem = f"{safe(line['name']) if line['map'] is not None else 'unknown'}_{line['stay']}"
    on, n_on = fa + line["arrive"], line["n_frames"]
    picks = {on + round(j * (n_on - 1) / 8) for j in range(9)}
    extra = {r["n"]: r for r in index}
    vw = VideoWriter(dest, pattern=stem + "_%03d.mkv", note={"by": "corpus", "seg": line["seg"]})
    prints, tiles = [], []
    try:
        for i in range(fa, fb + 1):
            n, name, t = rows[i]
            f = fr.read(src, name, shift=0)                  # as stored: the column fix (xshift.txt) goes along
            if f is None or f.shape != (768, 1366, 3):
                raise Problem(f"frame {name} of {src.name} does not read as a 1366x768 picture")
            f = np.ascontiguousarray(f)
            prints.append(fingerprint(f))
            if i in picks:
                tiles.append((n, t, cv2.resize(f, (455, 256), interpolation=cv2.INTER_AREA)))
            r = extra.get(n) or {}
            if not vw.put(f, n, t, r.get("cur"), wait=True, buttons=r.get("b", 0)):
                raise Problem(f"the encoder stopped at frame {name}: {vw.error}")
    finally:
        meta = vw.close()
    if meta["error"] or meta["frames"] != len(prints):
        raise Problem(f"the encoder: {meta['error']} ({meta['frames']} of {len(prints)} frames written)")
    # frames.jsonl: the recorder's line of every frame in the stay's range + its fingerprint; a frame the recorder
    # listed but the video never held (dropped; the tail of a recording that was cut) is marked "drop"
    lo, hi = rows[fa][0], rows[fb][0]
    have = {rows[i][0]: (rows[i][2], prints[i - fa]) for i in range(fa, fb + 1)}
    listed = [r for r in index if lo <= r["n"] <= hi] or [{"n": n, "t": round(t, 4)} for n, (t, _) in have.items()]
    with open(dest / "frames.jsonl", "w", encoding="utf-8") as f:
        for r in listed:
            r = {k: x for k, x in r.items() if k != "drop"}
            r.update({"h": have[r["n"]][1]} if r["n"] in have else {"drop": True})
            f.write(json.dumps(r) + "\n")
    t_lo, t_hi = rows[fa][2], rows[fb][2]
    if keys:
        (dest / "keys.jsonl").write_text("".join(raw + "\n" for k, raw in keys if t_lo <= k.get("t", -1) <= t_hi),
                                         encoding="utf-8")
    for rel in WITH_FRAMES + (ONE_MAP_FILES if one_map else ()):
        if (src / rel).is_file():
            shutil.copy2(src / rel, dest / rel)
    if one_map:
        for rel in LABEL_FILES:                              # by-eye labels: kept beside the corpus' other labels
            if (src / rel).is_file():
                to = labels_dir(line["seg"]) / rel
                to.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / rel, to)
    _sheet(tiles, line, dest / "sheet.jpg")
    log = dest / "ffmpeg.log"
    if log.exists() and not log.read_text(encoding="utf-8", errors="replace").strip():
        log.unlink()
    files = sorted(dest.glob("*.mkv"))
    line["files"] = [{"name": p.name, "bytes": p.stat().st_size, "sha256": _sha(p)} for p in files]
    line["bytes"] = sum(f["bytes"] for f in line["files"])
    _write_stay(line)
    for p in dest.iterdir():
        if p.suffix == ".mkv" or p.name in LOCKED:
            os.chmod(p, stat.S_IREAD)
    return line


def read_back(dest: Path) -> str | None:
    """The proof a stay was filed right: every frame of its files decoded again and compared with the fingerprint
    frames.jsonl holds for it (taken from the original's pixels as they were read). -> why not, or None."""
    want = [r["h"] for r in map(json.loads, open(dest / "frames.jsonl", encoding="utf-8")) if not r.get("drop")]
    v = fr.Video(dest)
    try:
        bad = sum(1 for i, h in enumerate(want) if (g := v.frame(i)) is None or fingerprint(g) != h)
        count = len(v)
    finally:
        v.close()
    return f"{bad} of {len(want)} frames read back differently ({count} in the files)" if bad or count != len(want) \
        else None


def preview(dest: Path, line: dict, speed: float = 1.0):
    """preview.mp4: the stay at half size, 30 frames a second, lossy - for watching (many players can't show the
    lossless files). Made by a second ffmpeg while the filing goes on -> the process (None: it did not start).
    `speed`: how many video frames one real 60th of a second is (an old recording kept every 3rd tick's frame)."""
    names = [f["name"] for f in line["files"]]
    (dest / "preview.txt").write_text("".join("file '" + n.replace("'", "'\\''") + "'\n" for n in names),
                                      encoding="utf-8")
    slow = f"setpts={1 / speed:.3f}*PTS," if speed < 0.8 else ""
    try:
        return subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                                 "-i", "preview.txt", "-vf", f"{slow}fps=30,scale=684:384:flags=area",    # (even sizes)
                                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
                                 "-an", "preview.mp4"], cwd=dest, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError:
        return None


def _previewed(dest: Path, proc) -> bool:
    """Wait for a stay's preview; a failed one is removed (it is a convenience, never a reason not to file)."""
    code = proc.wait() if proc is not None else 1
    (dest / "preview.txt").unlink(missing_ok=True)
    if code != 0:
        (dest / "preview.mp4").unlink(missing_ok=True)
    return code == 0


def route(ses: str, start: datetime, lines: list) -> str:
    """route.txt: the session's stays in order - where the walk went."""
    out = [f"{ses}: began {start:%Y-%m-%d %H:%M:%S}, {len(lines)} stay(s), "
           f"{sum(l['minutes'] for l in lines):.1f} minutes on maps", ""]
    for l in lines:
        out.append(f"{l['seg']:>24s}  {l['began'][11:]}  {length(l['t'][1] - l['t'][0]):>7s}  {l['mode']:12s} "
                   f"{map_name(l['map'])}" + (f" ({l['map']})" if l["map"] is not None else "")
                   + f"   -> {l['path']}")
    return "\n".join(out) + "\n"


def file_session(run: Path, ses: str, facts: dict, lines: list, start: datetime, cuts_out: Path) -> Path:
    """sessions/SESSION: the recording's small files, session.json, route.txt, the cut sheets."""
    d = root() / "sessions" / ses
    d.mkdir(parents=True)
    for p in [run / rel for rel in SESSION_FILES] + sorted(run.glob("lie_*.png")):
        if p.is_file():
            shutil.copy2(p, d / p.name)
            os.chmod(d / p.name, stat.S_IWRITE)
    if not (d / "session.json").exists():                    # recorded before the recorder wrote one
        (d / "session.json").write_text(json.dumps(
            {"v": 1, "by": lines[0]["by"], "scene": None, "started": start.isoformat(timespec="seconds"),
             "source": str(run).replace("\\", "/"),
             "note": "written when the recording was filed: it was made before the recorder wrote session.json"},
            indent=1), encoding="utf-8")
    (d / "route.txt").write_text(route(ses, start, lines), encoding="utf-8")
    if cuts_out.exists():
        shutil.move(str(cuts_out), str(d / "cuts"))
    return d


def add(run: Path, dry: bool = False, full: bool = False, keep: bool = False, say=print) -> list:
    """File one recording (module docstring). Returns its manifest lines (written unless `dry`)."""
    import time
    from maplebrain.nav.identify import MapIdentifier
    run = Path(run).resolve()
    ses = run.name
    if any(l["session"] == ses for l in load()):
        raise Problem(f"{ses} is in the corpus already")
    if not dry and (root() / "sessions" / ses).exists():
        raise Problem(f"{root() / 'sessions' / ses} exists, but the manifest has no stay of it: remove it first")
    say(f"{ses}:")
    png = not (run / "video.json").exists()
    meta = {"by": "png"} if png else check(run, full, say)
    rows = fr.saved(run)
    if not rows:
        raise Problem(f"no saved frames in {run}")
    if any(not name.endswith(".png") for _, name, _ in rows):
        raise Problem("JPEG frames are lossy: only PNG recordings and videos enter the corpus")
    facts = json.loads((run / "session.json").read_text(encoding="utf-8")) if (run / "session.json").exists() else {}
    start = began_at(run, facts, meta)
    ident = MapIdentifier.load(MCW)
    segs, cuts, namer = cut(run, rows, ident, say)
    logged = fr._log_map(run)
    if logged is not None:                                   # a hunt / an observe run: one map, and its log names it
        other = sorted({s["map"] for s in segs if s["map"] not in (None, logged)})
        if other:
            raise Problem(f"the log says map {logged} {map_name(logged)}, the minimap names {other}: look at "
                          f"{root() / 'work' / 'cuts' / ses}")
        segs = [{"i": [0, len(rows) - 1], "map": logged, "how": "log"}]
    attack, marks = presses(run)
    keys = _keys(run)
    ticks = (run / "ticks.jsonl").exists()
    by = ("record" if (facts.get("by") or meta.get("by")) == "record" else
          "bot" if ticks and not (run / "keys.jsonl").exists() else "observe" if ticks else meta.get("by"))
    dev = dev_maps()
    bnds = bounds(segs, len(rows))
    lines = [_line(ses, k, s, b, rows, attack, marks, keys, start, facts, by, dev)
             for k, (s, b) in enumerate(zip(segs, bnds))]
    out = root() / "work" / "cuts" / ses
    if out.exists():
        _remove(out)                                         # (an earlier dry run's)
    for k, c in enumerate(cuts):
        sheet(run, rows, c, namer, out / f"cut_{k:03d}_{rows[max(c['a'] - 1, 0)][0]:06d}.png")
    out.mkdir(parents=True, exist_ok=True)
    (out / "cuts.json").write_text(json.dumps(
        [dict(c, frames=[rows[min(c["a"], len(rows) - 1)][0], rows[max(c["b"], 0)][0]],
              luma={rows[i][0]: namer.luma[i] for i in sorted(namer.luma)
                    if c["a"] - 30 <= i <= c["b"] + 30}) for c in cuts], indent=1), encoding="utf-8")
    looked = Counter("named" if m is not None else "no name" for m in namer.seen.values())
    if getattr(namer, "held", 0):
        looked["of them by the window measured on a frame beside it"] = namer.held
    say(f"  cut: {len(namer.seen)} frames looked at ({dict(looked)}), {len(cuts)} cut(s)"
        + (f"; sheets in {out}" if cuts and dry else ""))
    for c in cuts:
        say(f"    frames {rows[min(c['a'], len(rows) - 1)][0]}..{rows[max(c['b'], 0)][0]} ({c['s']:.2f} s): "
            f"{map_name(c['from']) if c['from'] else 'start'} -> {map_name(c['to']) if c['to'] else 'end'}: "
            f"{c['what']}")
    for l in lines:
        say(f"  {l['seg']:24s} frames {l['frames'][0]:>6}..{l['frames'][1]:<6} {l['minutes']:6.2f} min  "
            f"{l['group'] or '-':7s} {l['mode']:10s} {l['attacks']:4d} attacks  -> {l['path']}"
            + (f"  [{l['how']}]" if l["how"] != "minimap" else "")
            + (f"  marks {len(l['marks'])}" if l["marks"] else ""))
    if dry:
        say("  --dry: nothing filed")
        return lines
    # ---- step 4: every stay into its folder, proven frame by frame; only then the manifest and the original
    dts = sorted(b[2] - a[2] for a, b in zip(rows, rows[1:]))
    speed = min(1.0, (1 / 60) / max(dts[len(dts) // 2], 1e-4)) if dts else 1.0
    index = [json.loads(l) for l in open(run / "frames.jsonl", encoding="utf-8") if l.strip()] \
        if (run / "frames.jsonl").exists() else []
    for l in lines:                                          # (before anything is made: nothing of another stay's
        for d in (stay_dir(l), labels_dir(l["seg"])):        # is ever taken for this recording's)
            if d.exists():
                raise Problem(f"{d} exists already")
    made, shown, proofs, t0 = [], [], [], time.perf_counter()
    reader = ThreadPoolExecutor(1)                           # a stay is read back while the next one is written
    try:
        for l, b in zip(lines, bnds):
            made += [stay_dir(l), labels_dir(l["seg"])]
            file_stay(run, rows, l, b, index, keys, len(lines) == 1, say)
            proofs.append((l, reader.submit(read_back, stay_dir(l))))
            if shown and shown[-1][1] is not None:
                shown[-1][1].wait()                          # (one preview at a time beside the encoder)
            shown.append((stay_dir(l), preview(stay_dir(l), l, speed)))
        for l, proof in proofs:
            why = proof.result()
            if why:
                raise Problem(f"{l['seg']}: {why}")
        if sum(l["n_file"] for l in lines) != len(rows):
            raise Problem(f"{sum(l['n_file'] for l in lines)} frames filed, the recording holds {len(rows)}")
        made.append(root() / "sessions" / ses)
        file_session(run, ses, facts, lines, start, out)
        _save(load() + lines)
    except BaseException:                                    # nothing half-filed is left: the recording is as it was
        reader.shutdown(wait=True, cancel_futures=True)
        for d, p in shown:
            if p is not None and p.poll() is None:
                p.kill()
                p.wait()
        for d in made:
            if d.exists():
                _remove(d)
        raise
    reader.shutdown()
    n_prev = sum(_previewed(d, p) for d, p in shown)
    took = time.perf_counter() - t0
    secs = rows[-1][2] - rows[0][2]
    say(f"  filed: {len(lines)} stay(s), {len(rows)} frames, every one read back identical; "
        f"{sum(l['bytes'] for l in lines) / 1e9:.2f} GB; {n_prev} preview(s); took {took:.0f} s"
        + (f" = {took / secs:.2f} s per recorded second" if secs > 1 else ""))
    for v in [fr._VIDEOS.pop(k) for k in list(fr._VIDEOS)]:  # (let go of the recording's files)
        if v is not None:
            v.close()
    namer.ident = None
    if not keep and run.parent == (root() / "incoming").resolve():
        _remove(run)
        say("  the original in incoming/ is removed: every frame of it is in a stay")
    else:
        say(f"  the original stays as it is: {run}")
    write_index()
    return lines


def write_index() -> None:
    """README.txt (the layout) and index.txt (`list`'s report) in the corpus folder itself."""
    said = []
    report(say=said.append)
    (root() / "index.txt").write_text("\n".join(said) + "\n", encoding="utf-8")
    (root() / "README.txt").write_text(
        "The maplebrain recording corpus. Made and read by tools/data/corpus.py of the maple-work repo; what follows "
        "is that file's own description.\n\n" + __doc__, encoding="utf-8")


# ----------------------------------------------------------------------------------------------------- list
def report(stays: bool = False, say=print) -> None:
    """What the corpus holds (PLAN-data.md section 4): per map its stays, minutes and attack presses; the mob
    types and background sets covered out of those the game has; for each one not seen yet, the maps it lives on."""
    import map_cover
    lines = load()
    if not lines:
        say(f"{root()}: empty")
        return
    known = [l for l in lines if l["map"] is not None]
    say(f"{root()}: {len({l['session'] for l in lines})} session(s), {len(lines)} stay(s), "
        f"{sum(l['minutes'] for l in lines):.1f} minutes, {sum(l.get('bytes', 0) for l in lines) / 1e9:.1f} GB")
    per = defaultdict(list)
    for l in known:
        per[l["map"]].append(l)

    def fought(l):
        return l["mode"] == "bot" or l["attacks"] >= FARM_ATTACKS

    say(f"\n{'map':>9}  {'name':44s} {'group':7s} {'stays':>5} {'farming':>7} {'bot':>4} {'travel':>6} "
        f"{'minutes':>7} {'attacks':>7} {'marks':>5}")
    for m, ls in sorted(per.items(), key=lambda kv: -sum(l["minutes"] for l in kv[1])):
        say(f"{m:>9}  {map_name(m)[:44]:44s} {ls[0]['group']:7s} {len(ls):5d} "
            f"{sum(l['mode'] == 'farming' for l in ls):7d} {sum(l['mode'] == 'bot' for l in ls):4d} "
            f"{sum(l['mode'] == 'traveling' for l in ls):6d} {sum(l['minutes'] for l in ls):7.1f} "
            f"{sum(l['attacks'] for l in ls):7d} {sum(len(l['marks']) for l in ls):5d}")
    unk = [l for l in lines if l["map"] is None]
    if unk:
        say(f"\nunknown stretches (kept, out of the per-map numbers): {len(unk)}, "
            f"{sum(l['minutes'] for l in unk):.1f} minutes")
        for l in unk:
            say(f"  {l['seg']}: frames {l['frames'][0]}..{l['frames'][1]}, {l['minutes']:.2f} min -> {l['path']}")
    if stays:
        say("\nstays (the id tools take; its folder):")
        for l in lines:
            say(f"  {l['seg']:24s} {l['minutes']:6.2f} min {l['group'] or '-':7s} {l['mode']:10s} "
                f"{l['attacks']:4d} attacks  {l['path']}")
    # coverage: from the client data (map_cover: a mob type counts on a map with 3+ spawn points of it)
    maps, mobs = map_cover.load()
    if not maps:
        say("")
        say("coverage: needs the scene models (python -m maplebrain assets scene)")
        return
    clean = [m for m in maps.values() if m["clean"]]
    all_items = set().union(*[map_cover.items(m) for m in maps.values()])
    clean_items = set().union(*[map_cover.items(m) for m in clean])
    stayed = {m for m, ls in per.items() if any(fought(l) for l in ls)}
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


# --------------------------------------------------------------------------------------------------- verify
def verify(ids: list = (), frames: bool = False, say=print) -> int:
    """Are the stays' files what was filed? Every video file against its checksum in the manifest; `frames`: every
    frame decoded and compared with its fingerprint in frames.jsonl too (after a move to another drive: the proof
    nothing changed). Returns how many stays are not as filed."""
    lines = [l for l in load() if not ids or l["seg"] in ids]
    missing = sorted(set(ids) - {l["seg"] for l in lines})
    if missing:
        raise Problem(f"no such stay: {', '.join(missing)}")
    bad = n_files = n_frames = 0
    for l in lines:
        d, why = stay_dir(l), []
        for f in l.get("files", []):
            p = d / f["name"]
            n_files += 1
            if not p.is_file():
                why.append(f"{f['name']} is missing")
            elif p.stat().st_size != f["bytes"] or _sha(p) != f["sha256"]:
                why.append(f"{f['name']} is not the file that was filed")
        if frames and not why:
            n_frames += l["n_file"]
            diff = read_back(d)
            if diff:
                why.append(diff)
        if why:
            bad += 1
            say(f"  {l['seg']} ({l['path']}): " + "; ".join(why))
    say(f"verify: {len(lines)} stay(s), {n_files} video file(s)" + (f", {n_frames} frames decoded" if frames else "")
        + (f": {bad} NOT as filed" if bad else ": all as filed"))
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", type=Path, default=None, help="the corpus folder (default: config.CORPUS)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="file recordings: check, cut into maps, every stay into its map's folder")
    a.add_argument("runs", type=Path, nargs="*")
    a.add_argument("--dry", action="store_true", help="check + cut + the cut sheets, nothing filed")
    a.add_argument("--full", action="store_true", help="the check decodes every frame (minutes per hour recorded)")
    a.add_argument("--keep", action="store_true", help="leave the original in incoming/ (default: removed once every "
                   "frame of it is proven to be in a stay)")
    a.add_argument("--dev", type=int, nargs="+", default=None, metavar="MAP",
                   help="move these maps to the dev group (before their first gate)")
    ls = sub.add_parser("list", help="what the corpus holds and what is covered")
    ls.add_argument("--stays", "--segments", action="store_true", help="every stay too (the ids tools take)")
    ve = sub.add_parser("verify", help="are the files what was filed (after a move to another drive)?")
    ve.add_argument("stays", nargs="*", help="stay ids SESSION#K (default: every stay)")
    ve.add_argument("--frames", action="store_true", help="decode every frame and compare its fingerprint too")
    args = ap.parse_args(argv)
    if args.corpus:
        os.environ["MAPLE_CORPUS"] = str(args.corpus)
    try:
        if args.cmd == "verify":
            return 1 if verify(args.stays, args.frames) else 0
        if args.cmd == "add":
            if not args.runs and not args.dev:
                ap.error("add: a recording folder, or --dev MAP")
            if args.dev:
                to_dev(args.dev)
            bad = 0
            for run in args.runs:
                try:
                    add(run, args.dry, args.full, args.keep)
                except Problem as e:
                    bad += 1
                    print(f"  NOT ADDED: {e}")
            if args.runs and not args.dry:
                print()
                report()
            return 1 if bad else 0
        report(args.stays)
    except Problem as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
