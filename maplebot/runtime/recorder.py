"""Writes a replayable run: full-res frames (every Nth), one JSON line per tick (observation + actions + events)."""
import json
from dataclasses import asdict
from pathlib import Path

import cv2


class Recorder:
    def __init__(self, out: Path, every: int = 3):
        """`every`: save every Nth frame (plus every Track/Stop/Forget); 0 = no frames (log + ticks only)."""
        self.out = Path(out)
        (self.out / "frames").mkdir(parents=True, exist_ok=True) if every else self.out.mkdir(parents=True, exist_ok=True)
        self.ticks = open(self.out / "ticks.jsonl", "w", buffering=1, encoding="utf-8")
        self.log = open(self.out / "log.txt", "w", buffering=1, encoding="utf-8")
        self.every, self.n = every, 0

    def say(self, line: str) -> None:
        print(line.encode("ascii", "replace").decode())
        self.log.write(line + "\n")

    def tick(self, frame, obs, actions, mode, timings) -> None:
        self.n += 1
        frame_file = None
        if self.every and (self.n % self.every == 0 or any(type(a).__name__ in ("Track", "Stop", "Forget") for a in actions)):
            frame_file = f"{self.n:06d}.jpg"
            cv2.imwrite(str(self.out / "frames" / frame_file), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rec = {"n": self.n, "frame": frame_file, "mode": mode, "obs": asdict(obs), "timings": timings,
               "actions": [f"{type(a).__name__}{'(' + ','.join(str(v) for v in a.__dict__.values()) + ')' if a.__dict__ else ''}"
                           for a in actions]}
        self.ticks.write(json.dumps(rec, default=str) + "\n")

    def close(self) -> None:
        self.ticks.close()
        self.log.close()
