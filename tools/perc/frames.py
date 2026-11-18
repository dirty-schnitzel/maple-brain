"""Reading a recording's frames: PNG files or the lossless video, the capture's column error undone; and what a
tool works on (`clip`): a run folder, or a segment of the recording corpus.

**Frames.** `read(run, name)` returns the picture of frame `name` ("000123.png", as ticks.jsonl's "frame"):
the file RUN/frames/<name> if it exists, else frame `name` of the recording's video (PLAN-data.md section 5:
RUN/frames_0000.mkv ... written by maplebrain/runtime/video.py, bit-identical to the PNG it replaces). The video
holds the frames RUN/frames.jsonl lists, in that order (lines with "drop" are not in it); the k-th of them is frame
k % chunk of chunk file k // chunk (chunk = 18,000 frames = 5 minutes; video.json says it). `Video.frame` reads
forward when the wanted frame is near (decoding runs at ~400 frames a second) and jumps otherwise (~0.25 s).
Tools that open RUN/frames/*.png themselves get the files from `python tools/data/unpack.py RUN [names]`.

**The column error.** 2026-11-16: until the fix in `capture.game_columns`, a dark left edge column at calibration
made the native crop (1, 1367): the whole picture 1 px LEFT of its place and the last column from outside the
window. Recordings hit (Ant Tunnel IV 20261116_012059_1, Dangerous Steam 20261116_084844_2) carry a file
RUN/xshift.txt holding `1`; `read` moves their picture back (column 0 is then unknown: a copy of column 1).

**Clips.** `clip(arg)` is what the ported tools (replay/run.py, label_eval.py, labels/, synth/) take: `arg` = a run
folder (as always: its frames, its map from log.txt, outputs written into it), or a STAY of the recording corpus
(tools/data/corpus.py: one stay on one map of a recorded session, filed as its own folder under the map's): its id
`SESSION#K` (the permanent name: labels and gates use it) or its folder. A stay's folder is never written to:
what a tool makes goes to CORPUS\\work\\SESSION#K (re-creatable), by-eye labels to CORPUS\\labels\\SESSION#K (kept).
A stay on a hold-out map is refused unless the tool was given --holdout, and every such use is logged
(PLAN-data.md section 4).

    python tools/perc/frames.py RUN [RUN ...]     measure each recording's shift with the scene model (needs
                                                  `assets scene`), write / remove RUN/xshift.txt
"""
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

NEAR = 100          # a wanted frame at most this far ahead is reached by reading on (a jump costs about as much)


def xshift(run: Path) -> int:
    f = Path(run) / "xshift.txt"
    return int(f.read_text().strip()) if f.exists() else 0


def unshift(frame: np.ndarray, s: int) -> np.ndarray:
    """The picture moved `s` px right (to its place); the first `s` columns repeat the first known one."""
    if not s:
        return frame
    out = np.empty_like(frame)
    out[:, s:] = frame[:, :-s]
    out[:, :s] = frame[:, :1]
    return out


def number(name: str) -> int:
    """'000123.png' -> 123: a frame's number (the tick of a hunt, the frame count of a `record` recording)."""
    return int(Path(name).stem)


def name_of(n: int) -> str:
    return f"{n:06d}.png"


class Video:
    """The video of a recording: which frames it holds (frames.jsonl) and their pictures (the chunk files)."""

    def __init__(self, run: Path):
        self.run = Path(run)
        meta = json.loads((self.run / "video.json").read_text(encoding="utf-8"))
        self.meta, self.chunk = meta, int(meta["chunk"])
        self.counts = meta.get("counts")                 # frames per chunk file when they are not all `chunk`
        self.n, self.t, self.dropped = [], [], 0         # per video frame: its number, its time
        with open(self.run / "frames.jsonl", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("drop"):
                    self.dropped += 1
                else:
                    self.n.append(r["n"])
                    self.t.append(r["t"])
        if meta.get("frames") is not None and meta["frames"] < len(self.n):
            del self.n[meta["frames"]:], self.t[meta["frames"]:]      # a cut recording: the queued tail never got in
        self.at = {n: i for i, n in enumerate(self.n)}
        self._cap, self._k, self._pos = None, None, 0

    def __len__(self) -> int:
        return len(self.n)

    def index(self, name: str) -> int | None:
        try:
            return self.at.get(number(name))
        except ValueError:
            return None

    def where(self, i: int) -> tuple:
        """Video frame i -> (chunk file number, frame inside it)."""
        if self.counts:
            for k, c in enumerate(self.counts):
                if i < c:
                    return k, i
                i -= c
            raise IndexError("past the last chunk")
        return divmod(i, self.chunk)

    def file(self, k: int) -> Path:
        return self.run / (self.meta.get("pattern", "frames_%04d.mkv") % k)

    def frame(self, i: int) -> np.ndarray | None:
        """The picture of video frame `i` (BGR, as captured), or None when the file doesn't hold it."""
        if not 0 <= i < len(self.n):
            return None
        k, off = self.where(i)
        if k != self._k:
            self.close()
            self._cap, self._k, self._pos = cv2.VideoCapture(str(self.file(k)), cv2.CAP_FFMPEG), k, 0
        cap = self._cap
        if off < self._pos or off - self._pos > NEAR:
            cap.set(cv2.CAP_PROP_POS_FRAMES, off)
            self._pos = off
        while self._pos < off:
            if not cap.grab():
                self._k = None                           # (the next read reopens the chunk)
                return None
            self._pos += 1
        ok, f = cap.read()
        self._pos += 1
        if not ok:
            self._k = None
            return None
        return f

    def read(self, name: str) -> np.ndarray | None:
        i = self.index(name)
        return None if i is None else self.frame(i)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._cap, self._k = None, None


_VIDEOS = {}


def video(run: Path) -> Video | None:
    """The recording's video (opened once per process), or None when it has none."""
    key = str(Path(run).resolve())
    if key not in _VIDEOS:
        run = Path(run)
        _VIDEOS[key] = Video(run) if (run / "video.json").exists() and (run / "frames.jsonl").exists() else None
    return _VIDEOS[key]


def has(run: Path, name: str) -> bool:
    """Is frame `name` of the recording on disk (as a PNG / JPEG file or in its video)?"""
    if (Path(run) / "frames" / name).exists():
        return True
    v = video(run)
    return v is not None and v.index(name) is not None


def read(run: Path, name: str, shift: int | None = None) -> np.ndarray | None:
    f = Path(run) / "frames" / name
    frame = cv2.imread(str(f)) if f.exists() else None
    if frame is None:
        v = video(run)
        frame = v.read(name) if v is not None else None
    if frame is None:
        return None
    return unshift(frame, xshift(run) if shift is None else shift)


def map_of(run: Path) -> int:
    stay = Path(run) / "stay.json"                       # a corpus stay knows its map (a walk has no log)
    if stay.exists():
        m = json.loads(stay.read_text(encoding="utf-8")).get("map")
        if m is not None:
            return int(m)
    log = (Path(run) / "log.txt").read_text(encoding="utf-8", errors="replace")
    return int((re.search(r"map recognised: (\d+)", log) or re.search(r"\bmap (\d+) ", log)).group(1))


def saved(run: Path) -> list:
    """[(n, frame name, t)] of the recording's frames that are on disk, in order: the ticks of ticks.jsonl whose
    frame was saved (a hunt, an observe run), else the video's frames (a `record` recording has no ticks)."""
    run = Path(run)
    out = []
    if (run / "ticks.jsonl").exists():
        with open(run / "ticks.jsonl", encoding="utf-8") as f:
            for line in f:
                k = json.loads(line)
                if k.get("frame") and has(run, k["frame"]):
                    out.append((k["n"], k["frame"], k["obs"]["t"]))
        return out
    v = video(run)
    return [(n, name_of(n), t) for n, t in zip(v.n, v.t)] if v is not None else []


@dataclass
class Clip:
    """What a tool works on: the frames of one map, where they are and where the tool may write."""
    run: Path                       # the folder with the frames (a run, or a corpus stay): ticks.jsonl /
                                    # frames.jsonl, keys.jsonl
    out: Path                       # what a tool makes and can make again (replay/): `run`, or the stay's work
                                    # folder CORPUS/work/SESSION#K
    map_id: int | None = None       # the stay's map / the run log's (None: not known)
    seg: dict | None = None         # the manifest line of a corpus stay (None: a plain run folder)
    keep: Path | None = None        # by-eye work nobody can make again (labels.json, labels/): `run`, or
                                    # CORPUS/labels/SESSION#K

    def __post_init__(self):
        if self.keep is None:
            self.keep = self.out

    @property
    def name(self) -> str:
        return self.seg["seg"] if self.seg else self.run.name

    def frames(self, t0: float = 0.0, t1: float = 1e9, every: int = 1) -> list:
        """[(n, frame name, t)] in order: the segment's frames, or every saved frame of the run; t0 <= t <= t1."""
        rows = saved(self.run)
        if self.seg:
            a, b = self.seg["frames"]
            rows = [r for r in rows if a <= r[0] <= b]
        return [r for r in rows if t0 <= r[2] <= t1][::every]

    def read(self, name: str) -> np.ndarray | None:
        return read(self.run, name)

    def find(self, rel: str) -> Path:
        """An input a tool reads (labels.json, labels/cams.json, a replay): among the kept by-eye work, else among
        the tool outputs, else in the frames' own folder; where it would be written when it is nowhere yet."""
        home = self.keep if rel.split("/")[0] in ("labels.json", "labels") else self.out
        return next((d / rel for d in (self.keep, self.out, self.run) if (d / rel).exists()), home / rel)

    def sight(self, tracks: str = "replay/work.jsonl") -> list:
        """What perception saw on each frame of the clip, in order: [{"n", "frame", "t", "cam", "me", "mobs",
        "rope"}] - from the recording's own ticks.jsonl (a hunt, an observe run), else from a replay of the clip
        (`tracks`, tools/perc/replay/run.py: a `record` walk ran no perception)."""
        want = {n for n, _, _ in self.frames()}
        out = []
        if (self.run / "ticks.jsonl").exists():
            with open(self.run / "ticks.jsonl", encoding="utf-8") as f:
                for line in f:
                    k = json.loads(line)
                    if k["n"] in want:
                        o = k["obs"]
                        out.append({"n": k["n"], "frame": k["frame"], "t": o["t"], "cam": o.get("cam"),
                                    "me": o.get("me"), "mobs": o.get("mobs") or [], "rope": o.get("rope")})
            return out
        p = self.find(tracks)
        if not p.exists():
            raise SystemExit(f"{self.name} has no ticks.jsonl (a `record` recording runs no perception) and no "
                             f"{p}: python tools/perc/replay/run.py {self.name} first")
        with open(p, encoding="utf-8") as f:
            for line in f:
                k = json.loads(line)
                if k["n"] in want:
                    out.append({"n": k["n"], "frame": k["frame"], "t": k["t"], "cam": k.get("cam"),
                                "me": k.get("me"), "mobs": k.get("mobs") or [], "rope": k.get("rope")})
        return out


def _log_map(run: Path) -> int | None:
    try:
        return map_of(run)
    except (OSError, AttributeError):
        return None


def clip(arg, holdout: bool = False, tool: str = "") -> Clip:
    """`arg` -> Clip: a run folder, or a stay of the corpus - its id `SESSION#K` or its folder. Raises SystemExit
    with the reason when it is neither, or a hold-out stay asked for without `holdout` (a use WITH it is logged in
    the corpus, by `tool`)."""
    sys.path.insert(0, str(ROOT / "tools" / "data"))
    import corpus
    p = Path(arg)
    if p.is_dir():
        if not (p / "stay.json").exists():
            return Clip(p, p, _log_map(p))
        sid = json.loads((p / "stay.json").read_text(encoding="utf-8"))["seg"]
        seg = corpus.segment(sid)                        # (the manifest's line: its group is the current one)
        if seg is None:
            raise SystemExit(f"{p} says it is stay {sid}, but the corpus' manifest has no such stay")
    else:
        seg = corpus.segment(str(arg))
        if seg is None:
            raise SystemExit(f"{arg}: not a run folder and not a corpus stay (python tools/data/corpus.py list "
                             "--stays)")
    corpus.allow(seg, holdout, tool or Path(sys.argv[0]).name)
    return Clip(corpus.stay_dir(seg), corpus.work_dir(seg["seg"]), seg["map"], seg, corpus.labels_dir(seg["seg"]))


def measure(run: Path, n: int = 20) -> int:
    """How many of the frame's last columns are not the game's (0 = the capture was right): per column the share
    of opaque tile / object pixels the scene explains at the registered camera - a column from outside the window
    explains ~0 %."""
    import torch
    from maplebrain.scene import PLAY_H, Scene
    scene = Scene.load(map_of(run))
    ticks = [json.loads(l) for l in open(Path(run) / "ticks.jsonl", encoding="utf-8")]
    ticks = [k for k in ticks if k.get("frame") and k["obs"].get("cam")]
    ticks = [ticks[int(i * (len(ticks) - 1) / max(1, n - 1))] for i in range(min(n, len(ticks)))]
    ok, tot = np.zeros(1366), np.zeros(1366)
    for k in ticks:
        frame = read(run, k["frame"], shift=0)
        ft = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(scene.dev)
        reg = scene.locate(ft, seed=k["obs"]["cam"])
        if reg is None:
            continue
        e, _ = scene.expected(reg[0])
        solid = scene._crop(reg[0], 1366, PLAY_H)[..., 3] > 250
        ok += (((ft.float() - e).abs().amax(dim=2) <= 4) & solid).sum(0).cpu().numpy()
        tot += solid.sum(0).cpu().numpy()
    share = ok / np.maximum(1, tot)
    mid = float(np.median(share[100:1266]))
    s = 0
    while s < 4 and tot[1365 - s] > 200 and share[1365 - s] < 0.3 * mid:
        s += 1
    return s


if __name__ == "__main__":
    for a in sys.argv[1:]:
        run = Path(a)
        s = measure(run)
        f = run / "xshift.txt"
        if s:
            f.write_text(str(s))
        elif f.exists():
            f.unlink()
        print(f"{run}: the picture is {s} px left of its place" + (" -> xshift.txt" if s else " (capture right)"))
