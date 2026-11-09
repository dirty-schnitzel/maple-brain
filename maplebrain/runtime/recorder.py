"""Writes a replayable run: full-res frames (every Nth), one JSON line per tick (observation + actions + events).
Frames are JPEG-encoded on a worker thread (every frame at 23 fps would cost the bot ~10 ms a tick otherwise); if
the writer falls behind, a frame is dropped and the tick says `"frame": null`."""
import json
import queue
import threading
from dataclasses import asdict
from pathlib import Path

import cv2


class Recorder:
    def __init__(self, out: Path, every: int = 3, backlog: int = 48):
        """`every`: save every Nth frame (plus every Track/Stop/Forget); 0 = no frames (log + ticks only)."""
        self.out = Path(out)
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

    def _write_frames(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            path, frame = item
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])

    def say(self, line: str) -> None:
        print(line.encode("ascii", "replace").decode())
        self.log.write(line + "\n")

    def tick(self, frame, obs, actions, mode, timings) -> None:
        self.n += 1
        frame_file = None
        if self.every and (self.n % self.every == 0 or any(type(a).__name__ in ("Track", "Stop", "Forget") for a in actions)):
            name = f"{self.n:06d}.jpg"
            try:
                self._q.put_nowait((self.out / "frames" / name, frame.copy()))
                frame_file = name
            except queue.Full:
                self.dropped += 1
        rec = {"n": self.n, "frame": frame_file, "mode": mode, "obs": asdict(obs), "timings": timings,
               "actions": [f"{type(a).__name__}{'(' + ','.join(str(v) for v in a.__dict__.values()) + ')' if a.__dict__ else ''}"
                           for a in actions]}
        self.ticks.write(json.dumps(rec, default=str) + "\n")

    def close(self) -> None:
        if self._writer is not None:
            self._q.put(None)
            self._writer.join(timeout=30)
            if self.dropped:
                self.say(f"recorder: {self.dropped} frames dropped (the writer fell behind)")
        self.ticks.close()
        self.log.close()
