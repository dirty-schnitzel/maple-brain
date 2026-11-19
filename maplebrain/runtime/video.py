"""The game picture as lossless video (PLAN-data.md section 5): every frame handed over goes, bit for bit, into
chunk files RUN/frames_0000.mkv, frames_0001.mkv, ... - `record` (the user's walk) and `--video` on run / serve.

One ffmpeg process (HEVC lossless on the GPU's video encoder: 4-6x smaller than PNG, 3.4 ms of CPU a frame, the
same pixels back - tools/data/codec_bench.py) fed through its stdin by one writer thread. The loop that grabs frames
never waits: `put` only queues the frame (its own buffer, no copy - the capture hands out a fresh array per frame
and nothing writes to it afterwards); a full queue DROPS the frame and says so in frames.jsonl.

**Pieces** (the user, 2026-11-19: "cut at the timestamps to have only single-map frames inside"): `put(cut=True)`
starts a new piece with that frame - the encoder gets no more frames and finishes its files by itself, a new
encoder takes the next ones, its files go on counting. `record` cuts at every loading screen (`is_dark`: the game
fades to a black picture between two maps, always), so a chunk file never holds two maps and filing a walk is
moving files, not writing them again (tools/data/corpus.py).

Files in RUN:
  frames_%04d.mkv   chunks of CHUNK frames (5 minutes at 60 fps): a crash costs the tail of one chunk, and a long
                    walk is not one 60 GB file. A keyframe every GOP frames (2 s): a jump lands on the exact frame.
                    A piece ends its chunk early: the files hold `counts` frames each (video.json).
  frames.jsonl      one line per frame handed over, in order: {"n": its number, "t": seconds on the recording's
                    clock, "cur": [x, y] the mouse (left out when outside the picture), "d": 1 (a dark frame: part
                    of a loading screen), "cut": 1 (a piece begins with this frame), "drop": true (left out when
                    the frame is in the video)}. The k-th line without "drop" = the k-th frame of the video.
  video.json        the stream (size, fps, frames per chunk, the encoder command) and, once closed, the totals
                    and `counts`: the frames in each chunk file.
  ffmpeg.log        whatever the encoder said (errors only).

Killed mid-recording: the bot's process killed -> ffmpeg sees its stdin close and finishes the chunk by itself (the
frames still queued are lost: frames.jsonl then has a few more lines than the video has frames, all at the end);
ffmpeg itself killed -> the last ~0.5 s is lost and the last chunk needs `ffmpeg -i x.mkv -c copy fixed.mkv` before
jumping in it is exact (tools/data/video_safety.py; tools/data/corpus.py add does both checks).
"""
import json
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

W, H = 1366, 768
FPS, GOP, CHUNK_S = 60, 120, 300
PATTERN = "frames_%04d.mkv"
BACKLOG = 120                    # frames the queue holds (2 s, ~375 MB at most) before a frame is dropped
DARK, DARK_RUN = 1.0, 4          # a loading screen: this many frames in a row darker than this. Measured on 14 of
                                 # the user's map changes (2026-11-19): 6-26 frames at 0.0-0.9 each, the picture
                                 # fades with the status bar - no frame of play is that dark (the bar alone is ~4)


def is_dark(frame) -> bool:
    """Is this frame part of a loading screen? Every 16th pixel: ~15 microseconds, cheap enough for every frame."""
    return float(frame[::16, ::16].mean()) < DARK


def name_of(n: int) -> str:
    """The name tools know a frame by: ticks.jsonl's "frame" of tick n, the PNG file `unpack` writes."""
    return f"{n:06d}.png"


def encoder_cmd(out: Path, w: int = W, h: int = H, fps: int = FPS, gop: int = GOP, chunk: int = FPS * CHUNK_S,
                ffmpeg: str = "ffmpeg", pattern: str = PATTERN, start: int = 0) -> list:
    """The ffmpeg command: raw BGR frames on stdin -> lossless HEVC chunks of `chunk` frames in `out`, named
    `pattern` (one %0Nd: the chunk's number, from `start`)."""
    if chunk % gop:
        raise ValueError(f"a chunk ({chunk} frames) must be whole keyframe intervals ({gop})")
    if pattern.count("%") != 1:
        raise ValueError(f"the chunk file name needs exactly one %0Nd, got {pattern!r}")
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
            "-c:v", "hevc_nvenc", "-tune", "lossless", "-preset", "p4", "-pix_fmt", "gbrp",
            "-g", str(gop), "-forced-idr", "1",
            "-f", "segment", "-segment_time", f"{chunk / fps:g}", "-reset_timestamps", "1",
            "-segment_start_number", str(start), str(Path(out) / pattern)]


def chunk_glob(pattern: str) -> str:
    """'frames_%04d.mkv' -> 'frames_*.mkv' (as a glob: its special characters in the name taken literally)."""
    import glob
    import re
    head, tail = re.split(r"%0?\d*d", pattern, maxsplit=1)
    return glob.escape(head) + "*" + glob.escape(tail)


class VideoWriter:
    def __init__(self, out: Path, w: int = W, h: int = H, fps: int = FPS, gop: int = GOP,
                 chunk: int = FPS * CHUNK_S, backlog: int = BACKLOG, ffmpeg: str = "ffmpeg", note: dict | None = None,
                 pattern: str = PATTERN):
        """Starts the encoder (it waits for the first frame). `chunk`: frames per chunk file (tests use small ones).
        `note`: extra facts for video.json (what recorded this, the frame rate the frames really came at)."""
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.shape, self.fps, self.chunk = (h, w, 3), fps, chunk
        self.written, self.dropped, self.queue_max = 0, 0, 0
        self.puts, self.put_s, self.put_max = 0, 0.0, 0.0    # what `put` costs the loop that calls it
        self.error = None                        # why the encoder stopped taking frames (every later frame drops)
        self.pattern = pattern
        self.counts, self._fed = [], 0           # frames in each finished chunk file; frames the encoder has now
        self._old, self._cut = [], False         # encoders finishing an earlier piece; a cut waiting for a frame
        self._args = (w, h, fps, gop, chunk, ffmpeg, pattern)
        self.meta = {"v": 1, "w": w, "h": h, "fps": fps, "gop": gop, "chunk": chunk, "pattern": pattern,
                     "started": datetime.now().isoformat(timespec="seconds"), **(note or {}), "closed": False}
        self.cmd = encoder_cmd(self.out, w, h, fps, gop, chunk, ffmpeg, pattern)
        self.meta["cmd"] = self.cmd[1:-1]
        self._index = open(self.out / "frames.jsonl", "w", buffering=1, encoding="utf-8")
        self._err = open(self.out / "ffmpeg.log", "w", encoding="utf-8")
        self._write_meta()
        self.proc = self._encoder(0)
        self._q = queue.Queue(maxsize=backlog)
        self._thread = threading.Thread(target=self._feed, name="video", daemon=True)
        self._thread.start()

    def _write_meta(self) -> None:
        (self.out / "video.json").write_text(json.dumps(self.meta, indent=1), encoding="utf-8")

    def _encoder(self, start: int):
        """An encoder whose first chunk file is number `start`. Its own process group: Ctrl+C in the console must
        reach python only - ffmpeg ends when its stdin closes, after the frames it was given."""
        cmd = encoder_cmd(self.out, *self._args, start=start)
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._err,
                                bufsize=0, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))

    def _count(self) -> None:
        """The chunk files the encoder makes of the frames it was given: whole chunks, then the rest."""
        full, rest = divmod(self._fed, self.chunk)
        self.counts += [self.chunk] * full + ([rest] if rest else [])
        self._fed = 0

    def _roll(self) -> None:
        """A new piece (the writer's thread): the encoder's stdin is closed - it finishes its last file by
        itself - and a new one starts at the next file number. The frames of the moment wait in the queue (2 s of
        room): the old encoder gets up to a second to end first, so two rarely run at once."""
        old = self.proc
        old.stdin.close()
        self._count()
        try:
            old.wait(1.0)
        except subprocess.TimeoutExpired:
            pass
        self._old.append(old)
        self.proc = self._encoder(len(self.counts))

    def _feed(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            frame, cut = item
            try:
                if cut and self._fed:
                    self._roll()
                pipe = self.proc.stdin
                data = memoryview(frame).cast("B")
                while len(data):                               # (a raw pipe may take less than asked)
                    data = data[pipe.write(data):]
                self.written += 1
                self._fed += 1
            except (OSError, ValueError) as e:                 # the encoder is gone (its reason: ffmpeg.log)
                self.error = f"the encoder stopped ({type(e).__name__}: {e})"
                return

    def put(self, frame, n: int, t: float, cursor=None, wait: bool = False, buttons: int = 0, cut: bool = False,
            dark: bool = False) -> bool:
        """Queue frame number `n` (seen at `t` s) for the video; never waits. False = dropped (the queue is full or
        the encoder stopped): frames.jsonl says so and the video goes on without it. `wait` (copying a recording,
        nothing live): a full queue is waited for instead. `cursor` / `buttons`: the mouse at this frame (its place
        in frame pixels; the buttons held as bits, runtime/session.py BUTTONS). `cut`: a new piece begins with
        this frame (with the next one in the video when this one is dropped); `dark`: it is a loading screen's."""
        t_in = time.perf_counter()
        ok = self.error is None and frame.shape == self.shape and frame.flags.c_contiguous
        cut = cut or self._cut
        while ok:
            try:
                self._q.put((frame, cut), timeout=0.5) if wait else self._q.put_nowait((frame, cut))
                break
            except queue.Full:
                ok = wait and self.error is None and self._thread.is_alive()
        if ok:
            size = self._q.qsize()
            if size > self.queue_max:
                self.queue_max = size
        else:
            self.dropped += 1
        self._cut = cut and not ok
        cur = f', "cur": [{cursor[0]:.0f}, {cursor[1]:.0f}]' if cursor is not None else ""
        held = f', "b": {buttons}' if buttons else ""
        mark = (', "d": 1' if dark else "") + (', "cut": 1' if cut and ok else "")
        drop = "" if ok else ', "drop": true'
        self._index.write(f'{{"n": {n}, "t": {t:.4f}{cur}{held}{mark}{drop}}}\n')
        took = time.perf_counter() - t_in
        self.puts, self.put_s, self.put_max = self.puts + 1, self.put_s + took, max(self.put_max, took)
        return ok

    def files(self) -> list:
        return sorted(self.out.glob(chunk_glob(self.pattern)))

    def bytes(self) -> int:
        return sum(p.stat().st_size for p in self.files())

    def close(self, wait_s: float = 120.0) -> dict:
        """Queued frames -> the encoder, its stdin closed, wait for it to finish the last chunk. Returns the totals
        (also in video.json)."""
        end = time.perf_counter() + wait_s
        while self._thread.is_alive():
            try:
                self._q.put_nowait(None)
                break
            except queue.Full:
                if time.perf_counter() > end:
                    break
                time.sleep(0.01)
        self._thread.join(max(0.0, end - time.perf_counter()))
        if self._thread.is_alive():
            self.error = self.error or "the writer did not finish in time"
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self._count()
        code = 0
        for proc in [*self._old, self.proc]:                 # (the encoders of earlier pieces ended long ago)
            try:
                code = proc.wait(max(1.0, end - time.perf_counter())) or code
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait() or code
                self.error = self.error or "ffmpeg did not finish in time (killed)"
        self._index.close()
        self._err.close()
        said = (self.out / "ffmpeg.log").read_text(encoding="utf-8", errors="replace").strip()
        if code != 0:
            self.error = self.error or f"ffmpeg ended with code {code}"
        if self.error and said:
            self.error += ": " + said[-300:]
        self.meta.update(closed=True, frames=self.written, dropped=self.dropped, queue_max=self.queue_max,
                         put_ms=[round(1000 * self.put_s / max(self.puts, 1), 4), round(1000 * self.put_max, 3)],
                         bytes=self.bytes(), chunks=len(self.files()), counts=self.counts,
                         ended=datetime.now().isoformat(timespec="seconds"), error=self.error)
        self._write_meta()
        return self.meta

    def summary(self, seconds: float | None = None) -> str:
        """The log's line once closed: frames, chunks, size (+ GB a minute over `seconds` of recording)."""
        m = self.meta
        gb = m.get("bytes", 0) / 1e9
        rate = f" = {60 * gb / seconds:.2f} GB a minute" if seconds and seconds > 1 else ""
        return (f"video: {m.get('frames', self.written)} frames in {m.get('chunks', 0)} chunk file(s), {gb:.2f} GB"
                f"{rate}; dropped {self.dropped}; queue at most {self.queue_max} of {self._q.maxsize}; handing a "
                f"frame over cost the loop {1000 * self.put_s / max(self.puts, 1):.3f} ms on average, "
                f"{1000 * self.put_max:.2f} ms at most" + (f"; ERROR: {self.error}" if self.error else ""))
