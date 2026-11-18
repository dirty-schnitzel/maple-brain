"""The lossless video (PLAN-data.md section 5, gate a): frames written by runtime/video.py come back from
tools/perc/frames.py bit for bit - in order, by name, on jumps, across chunk borders - and a dropped frame is told
apart. Needs ffmpeg with the GPU's HEVC encoder (skipped without it)."""
import importlib.util
import json
import shutil
import subprocess
import threading
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebrain.perception.perceiver import Observation
from maplebrain.runtime import video
from maplebrain.runtime.recorder import Recorder

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("frames", ROOT / "tools" / "perc" / "frames.py")
fr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fr)


def _encoder() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=black:s=1366x768:r=60", "-frames:v", "2", "-c:v", "hevc_nvenc", "-tune",
                            "lossless", "-pix_fmt", "gbrp", "-f", "null", "-"], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


needs_encoder = pytest.mark.skipif(not _encoder(), reason="no ffmpeg with hevc_nvenc (the GPU's lossless encoder)")


def _frames(n: int) -> list:
    """`n` different native frames: the Ant Tunnel IV fixture's, each also moved a little (a moving camera)."""
    base = [cv2.imread(str(p)) for p in sorted((ROOT / "tests" / "fixtures" / "perf_ant4").glob("*.webp"))[:12]]
    return [np.ascontiguousarray(np.roll(base[i % len(base)], (i // len(base)) * 3, axis=1)) for i in range(n)]


@needs_encoder
def test_video_frames_are_the_png_pixels_exactly_across_chunk_borders(tmp_path):
    """Gate (a): 150 frames in chunks of 60 (keyframes every 30) = 3 chunk files; every frame equals the PNG of
    the same frame - read in order, by name, on jumps back and forth over the borders."""
    frames = _frames(150)
    vw = video.VideoWriter(tmp_path, gop=30, chunk=60, backlog=200)
    for i, f in enumerate(frames):
        assert vw.put(f, i + 1, i / 60, cursor=(10.4, 20.6) if i == 3 else None,       # numbered like ticks: from 1
                      buttons=2 if i == 4 else 0)
    meta = vw.close()
    assert meta["closed"] and meta["frames"] == 150 and meta["dropped"] == 0 and meta["error"] is None
    assert sorted(p.name for p in tmp_path.glob("frames_*.mkv")) == [f"frames_{k:04d}.mkv" for k in range(3)]
    rows = [json.loads(l) for l in (tmp_path / "frames.jsonl").read_text().splitlines()]
    assert [r["n"] for r in rows] == list(range(1, 151)) and rows[3]["cur"] == [10, 21] and "cur" not in rows[0]
    assert rows[4]["b"] == 2 and "b" not in rows[3]           # the mouse buttons held, only when one is
    (tmp_path / "png").mkdir()
    for i in (0, 59, 60, 61, 119, 120, 149):                 # the PNG of the same frame (what --frames-png wrote)
        cv2.imwrite(str(tmp_path / "png" / f"{i}.png"), frames[i], [cv2.IMWRITE_PNG_COMPRESSION, 1])
        assert np.array_equal(fr.read(tmp_path, f"{i + 1:06d}.png"), cv2.imread(str(tmp_path / "png" / f"{i}.png")))
    v = fr.video(tmp_path)
    assert len(v) == 150 and all(np.array_equal(v.frame(i), frames[i]) for i in range(150))        # in order
    for i in (149, 0, 60, 59, 121, 30, 119, 120, 7, 61):                                           # jumps
        assert np.array_equal(v.frame(i), frames[i]), i
    assert fr.read(tmp_path, "000151.png") is None and not fr.has(tmp_path, "000000.png")
    assert fr.saved(tmp_path)[:2] == [(1, "000001.png", 0.0), (2, "000002.png", round(1 / 60, 4))]
    v.close()


class _Held(video.VideoWriter):
    """A writer whose thread waits for `go`: the queue fills up."""
    go = threading.Event()

    def _feed(self):
        self.go.wait(20)
        super()._feed()


@needs_encoder
def test_a_full_queue_drops_the_frame_says_so_and_the_names_still_fit(tmp_path):
    """The loop never waits: with the queue full `put` returns False at once, frames.jsonl marks the frame, and the
    reader gives every kept frame under its own number."""
    frames = _frames(6)
    _Held.go.clear()
    vw = _Held(tmp_path, gop=30, chunk=60, backlog=2)
    took = [vw.put(f, i, i / 60) for i, f in enumerate(frames)]
    assert took == [True, True, False, False, False, False] and vw.dropped == 4
    _Held.go.set()
    assert vw.put(frames[5], 6, 0.1, wait=True)              # (copying a recording waits instead)
    meta = vw.close()
    assert meta["frames"] == 3 and meta["dropped"] == 4
    rows = [json.loads(l) for l in (tmp_path / "frames.jsonl").read_text().splitlines()]
    assert [r.get("drop", False) for r in rows] == [False, False, True, True, True, True, False]
    assert np.array_equal(fr.read(tmp_path, "000001.png"), frames[1])
    assert np.array_equal(fr.read(tmp_path, "000006.png"), frames[5])
    assert fr.read(tmp_path, "000003.png") is None and fr.video(tmp_path).dropped == 4
    fr.video(tmp_path).close()


@needs_encoder
def test_a_hunt_with_video_keeps_the_tick_names_and_writes_no_frame_files(tmp_path):
    """--video on run / serve: every tick's frame is in the video under the name ticks.jsonl gives it."""
    frames = _frames(4)
    rec = Recorder(tmp_path, every=3, video=True)
    for i, f in enumerate(frames):
        rec.tick(f, Observation(t=i / 60), [], "HUNT", {})
    rec.close()
    ticks = [json.loads(l) for l in (tmp_path / "ticks.jsonl").read_text().splitlines()]
    assert [k["frame"] for k in ticks] == ["000001.png", "000002.png", "000003.png", "000004.png"]
    assert not (tmp_path / "frames").exists()
    assert all(np.array_equal(fr.read(tmp_path, k["frame"]), f) for k, f in zip(ticks, frames))
    assert [n for n, _, _ in fr.saved(tmp_path)] == [1, 2, 3, 4]
    assert "video: 4 frames in 1 chunk file(s)" in (tmp_path / "log.txt").read_text()
    fr.video(tmp_path).close()


@needs_encoder
def test_video_with_png_frames_holds_the_same_pixels(tmp_path):
    """--video --frames-png: the PNG files of every Nth tick beside the video, the same names, the same pixels."""
    frames = _frames(3)
    rec = Recorder(tmp_path, every=3, png=True, video=True)
    for i, f in enumerate(frames):
        rec.tick(f, Observation(t=i / 60), [], "HUNT", {})
    rec.close()
    assert [p.name for p in (tmp_path / "frames").iterdir()] == ["000003.png"]
    png = cv2.imread(str(tmp_path / "frames" / "000003.png"))
    assert np.array_equal(png, frames[2]) and np.array_equal(fr.video(tmp_path).read("000003.png"), png)
    fr.video(tmp_path).close()


def test_chunks_must_be_whole_keyframe_intervals(tmp_path):
    with pytest.raises(ValueError):
        video.encoder_cmd(tmp_path, gop=120, chunk=18001)
    cmd = video.encoder_cmd(tmp_path)
    assert cmd[cmd.index("-segment_time") + 1] == "300" and cmd[cmd.index("-g") + 1] == "120"
    assert cmd[cmd.index("-c:v") + 1:cmd.index("-c:v") + 4] == ["hevc_nvenc", "-tune", "lossless"]
