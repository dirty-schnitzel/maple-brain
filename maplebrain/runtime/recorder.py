"""Writes a replayable run: full-res frames (every Nth), one JSON line per tick (observation + actions + events).
Frames are JPEG-encoded on a worker thread (every frame at 23 fps would cost the bot ~10 ms a tick otherwise); if
the writer falls behind, a frame is dropped and the tick says `"frame": null`.
`video` (--video, PLAN-data.md section 5): EVERY tick's frame goes into the run's lossless video instead
(runtime/video.py: frames_0000.mkv ... + frames.jsonl); the tick's "frame" stays the name "000123.png" = the tick,
which tools/perc/frames.py reads from the video - old readers and labels keep working. No JPEG files then; with
--frames-png the PNG files of every Nth tick are written beside it (the same names, the same pixels)."""
import json
import queue
import threading
from dataclasses import asdict
from pathlib import Path

import cv2


class Recorder:
    def __init__(self, out: Path, every: int = 3, backlog: int = 48, png: bool = False, video: bool = False):
        """`every`: save every Nth frame (plus every Track/Stop/Forget); 0 = no frames (log + ticks only).
        `png`: lossless frames (--frames-png; ~1.1 MB and ~40 ms of the writer thread each) instead of JPEG 92,
        which moves 4 of 5 sprite pixels by more than 4 levels (measured 2026-11-16): for reference recordings.
        `video`: every frame into the lossless video; frame files only with `png` (never JPEG beside a video)."""
        self.ext = "png" if png else "jpg"
        self.out = Path(out)
        if video and not png:
            every = 0
        (self.out / "frames").mkdir(parents=True, exist_ok=True) if every else self.out.mkdir(parents=True, exist_ok=True)
        self.ticks = open(self.out / "ticks.jsonl", "w", buffering=1, encoding="utf-8")
        self.log = open(self.out / "log.txt", "w", buffering=1, encoding="utf-8")
        self.every, self.n = every, 0
        self.dropped = 0
        self._q = queue.Queue(maxsize=backlog) if every else None
        self._writer = None
        if every:
            self._writer = threading.Thread(target=self._write_frames, daemon=True)
            self._writer.start()
        self.video = None
        if video:
            from .video import VideoWriter
            self.video = VideoWriter(self.out, note={"by": "hunt"})
        self._t0 = self._t1 = None                       # obs.t of the first / last tick: the video's GB a minute

    def _write_frames(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            path, frame = item
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1] if path.suffix == ".png"
                        else [cv2.IMWRITE_JPEG_QUALITY, 92])

    def say(self, line: str) -> None:
        print(line.encode("ascii", "replace").decode())
        self.log.write(line + "\n")

    def tick(self, frame, obs, actions, mode, timings, facts=None) -> None:
        """One line of ticks.jsonl; `facts`: the Perceiver's FrameFacts of this frame (perception/facts.py: what the
        frame showed, before any memory) -> "facts", read back with FrameFacts.from_dict."""
        self.n += 1
        frame_file = None
        if self.every and (self.n % self.every == 0 or any(type(a).__name__ in ("Track", "Stop", "Forget") for a in actions)):
            name = f"{self.n:06d}.{self.ext}"
            try:
                self._q.put_nowait((self.out / "frames" / name, frame.copy()))
                frame_file = name
            except queue.Full:
                self.dropped += 1
        if self.video is not None:                       # the frame's own buffer: nothing writes to it after this
            self._t0, self._t1 = (obs.t if self._t0 is None else self._t0), obs.t
            if self.video.put(frame, self.n, obs.t):
                frame_file = f"{self.n:06d}.png"
            elif frame_file is None:
                self.dropped += 1
        rec = {"n": self.n, "frame": frame_file, "mode": mode, "obs": asdict(obs), "timings": timings,
               "actions": [f"{type(a).__name__}{'(' + ','.join(str(v) for v in a.__dict__.values()) + ')' if a.__dict__ else ''}"
                           for a in actions]}
        if facts is not None:
            rec["facts"] = facts.as_dict()
        self.ticks.write(json.dumps(rec, default=str) + "\n")

    def close(self) -> None:
        if self._writer is not None:
            self._q.put(None)
            self._writer.join(timeout=30)
        if self.video is not None:
            self.video.close()
            self.say(self.video.summary((self._t1 - self._t0) if self._t0 is not None else None))
        if self.dropped:
            self.say(f"recorder: {self.dropped} frames dropped (the writer fell behind)")
        self.ticks.close()
        self.log.close()
