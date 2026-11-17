"""The game picture as lossless video (PLAN-data.md section 5): every frame handed over goes, bit for bit, into
chunk files RUN/frames_0000.mkv, frames_0001.mkv, ... - `record` (the user's walk) and `--video` on run / serve.

One ffmpeg process (HEVC lossless on the GPU's video encoder: 4-6x smaller than PNG, 3.4 ms of CPU a frame, the
same pixels back - tools/data/codec_bench.py) fed through its stdin by one writer thread. The loop that grabs frames
never waits: `put` only queues the frame (its own buffer, no copy - the capture hands out a fresh array per frame
and nothing writes to it afterwards); a full queue DROPS the frame and says so in frames.jsonl.

Files in RUN:
  frames_%04d.mkv   chunks of CHUNK frames (5 minutes at 60 fps): a crash costs the tail of one chunk, and a long
                    walk is not one 60 GB file. A keyframe every GOP frames (2 s): a jump lands on the exact frame.
  frames.jsonl      one line per frame handed over, in order: {"n": its number, "t": seconds on the recording's
                    clock, "cur": [x, y] the mouse (left out when outside the picture), "drop": true (left out
                    when the frame is in the video)}. The k-th line without "drop" = the k-th frame of the video.
  video.json        the stream (size, fps, frames per chunk, the encoder command) and, once closed, the totals.
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


def name_of(n: int) -> str:
    """The name tools know a frame by: ticks.jsonl's "frame" of tick n, the PNG file `unpack` writes."""
    return f"{n:06d}.png"


def encoder_cmd(out: Path, w: int = W, h: int = H, fps: int = FPS, gop: int = GOP, chunk: int = FPS * CHUNK_S,
                ffmpeg: str = "ffmpeg") -> list:
    """The ffmpeg command: raw BGR frames on stdin -> lossless HEVC chunks of `chunk` frames in `out`."""
    if chunk % gop:
        raise ValueError(f"a chunk ({chunk} frames) must be whole keyframe intervals ({gop})")
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
            "-c:v", "hevc_nvenc", "-tune", "lossless", "-preset", "p4", "-pix_fmt", "gbrp",
            "-g", str(gop), "-forced-idr", "1",
            "-f", "segment", "-segment_time", f"{chunk / fps:g}", "-reset_timestamps", "1",
            str(Path(out) / PATTERN)]


class VideoWriter:
    def __init__(self, out: Path, w: int = W, h: int = H, fps: int = FPS, gop: int = GOP,
                 chunk: int = FPS * CHUNK_S, backlog: int = BACKLOG, ffmpeg: str = "ffmpeg", note: dict | None = None):
        """Starts the encoder (it waits for the first frame). `chunk`: frames per chunk file (tests use small ones).
        `note`: extra facts for video.json (what recorded this, the frame rate the frames really came at)."""
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.shape, self.fps, self.chunk = (h, w, 3), fps, chunk
        self.written, self.dropped, self.queue_max = 0, 0, 0
        self.puts, self.put_s, self.put_max = 0, 0.0, 0.0    # what `put` costs the loop that calls it
        self.error = None                        # why the encoder stopped taking frames (every later frame drops)
        self.meta = {"v": 1, "w": w, "h": h, "fps": fps, "gop": gop, "chunk": chunk, "pattern": PATTERN,
                     "started": datetime.now().isoformat(timespec="seconds"), **(note or {}), "closed": False}
        self.cmd = encoder_cmd(self.out, w, h, fps, gop, chunk, ffmpeg)
        self.meta["cmd"] = self.cmd[1:-1]
        self._index = open(self.out / "frames.jsonl", "w", buffering=1, encoding="utf-8")
        self._err = open(self.out / "ffmpeg.log", "w", encoding="utf-8")
        self._write_meta()
        # its own process group: Ctrl+C in the console must reach python only - ffmpeg ends when its stdin closes,
        # after the queued frames
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._err,
                                     bufsize=0, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        self._q = queue.Queue(maxsize=backlog)
        self._thread = threading.Thread(target=self._feed, name="video", daemon=True)
        self._thread.start()

    def _write_meta(self) -> None:
        (self.out / "video.json").write_text(json.dumps(self.meta, indent=1), encoding="utf-8")

    def _feed(self) -> None:
        pipe = self.proc.stdin
        while True:
            frame = self._q.get()
            if frame is None:
                return
            try:
                data = memoryview(frame).cast("B")
                while len(data):                               # (a raw pipe may take less than asked)
                    data = data[pipe.write(data):]
                self.written += 1
            except (OSError, ValueError) as e:                 # the encoder is gone (its reason: ffmpeg.log)
                self.error = f"the encoder stopped ({type(e).__name__}: {e})"
                return

    def put(self, frame, n: int, t: float, cursor=None, wait: bool = False) -> bool:
        """Queue frame number `n` (seen at `t` s) for the video; never waits. False = dropped (the queue is full or
        the encoder stopped): frames.jsonl says so and the video goes on without it. `wait` (copying a recording,
        nothing live): a full queue is waited for instead."""
        t_in = time.perf_counter()
        ok = self.error is None and frame.shape == self.shape and frame.flags.c_contiguous
        while ok:
            try:
                self._q.put(frame, timeout=0.5) if wait else self._q.put_nowait(frame)
                break
            except queue.Full:
                ok = wait and self.error is None and self._thread.is_alive()
        if ok:
            size = self._q.qsize()
            if size > self.queue_max:
                self.queue_max = size
        else:
            self.dropped += 1
        cur = f', "cur": [{cursor[0]:.0f}, {cursor[1]:.0f}]' if cursor is not None else ""
        drop = "" if ok else ', "drop": true'
        self._index.write(f'{{"n": {n}, "t": {t:.4f}{cur}{drop}}}\n')
        took = time.perf_counter() - t_in
        self.puts, self.put_s, self.put_max = self.puts + 1, self.put_s + took, max(self.put_max, took)
        return ok

    def bytes(self) -> int:
        return sum(p.stat().st_size for p in self.out.glob("frames_*.mkv"))

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
        try:
            code = self.proc.wait(max(1.0, end - time.perf_counter()))
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = self.proc.wait()
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
                         bytes=self.bytes(), chunks=len(list(self.out.glob("frames_*.mkv"))),
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
