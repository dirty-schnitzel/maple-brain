"""`python -m maplebrain record [OUT]`: the user plays, everything the game shows is recorded (PLAN-data.md
sections 4-5). Nothing is pressed, and **no perception runs**: the bot's perception is tied to one map, a walk
crosses many, and the corpus replays perception offline anyway.

**A walk is cut into its maps while it is recorded** (the user, 2026-11-19): the game shows a black loading
screen between two maps, always, and a black frame costs nothing to notice (video.is_dark, every frame). At the
DARK_RUN-th black frame in a row the video starts a new piece (video.py), so no video file holds two maps.
**The stop key files the recording**: tools/data/corpus.py add runs in its own process (below normal priority,
its words in CORPUS/work/filing/RECORDING.log and, once it is done, here) - it names every piece's map with a few
looks at the minimap and MOVES the files into their maps' folders; the next recording can start at once.

Stays loaded like `serve`: the start key (F7) starts a recording, the stop key (F8) ends it, Ctrl+C in the console
quits. Each recording is its own folder OUT/<date_time>_<k>:
  frames_0000.mkv ...   every frame the capture hands out, lossless (runtime/video.py): a new file at every
                        loading screen and after 5 minutes
  frames.jsonl          per frame: its number (from 0), its time, the mouse (where it is in the frame, which
                        buttons are held), "d" on a loading screen's dark frames, "cut" where a piece begins;
                        "drop" when it is not in the video
  session.json          the facts of the day, written by the recorder (runtime/session.py): the config (which key
                        does what, the weapon), the code's commit, the client data's build, the wall clock at t = 0
  keys.jsonl            the player's keys with their times (runtime/keylog.py, the same clock) - whatever is typed
                        while the game is focused, chat included: start a recording only after logging in
  log.txt               what happened, and the numbers at the end (frames a second, dropped frames, GB a minute)
  notes.txt             optional, written by the user afterwards: one line per press of the marker key (Keys.note),
                        "2:10 kill-stolen by a mage, moved to the bottom" (the key itself is in keys.jsonl)

Only while the game window is focused, at its native 1366x768 and where the capture is aimed (runtime/window.py):
otherwise the recording pauses (said in the log, a gap in the times) - another window's picture never gets in.
The Lie Detector is looked for once a second on its own thread (the siren, as `watch`), between recordings too; a
frame of it is saved. The loop itself only grabs and queues: it never waits for the encoder, the disk or a look.
"""
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from ..capture import H, W, Screen, find_window
from ..config import Config
from ..humanize import Humanizer
from ..keyboard import FocusLost, Keyboard, foreground_title
from . import session, window
from .runner import ASSETS, Hotkeys, _picture, chirp, lie_alarm
from .video import DARK_RUN, VideoWriter, is_dark

MIN_FREE_GB = 30            # no recording starts on a drive with less room than this (an hour is 20-40 GB)
STOP_FREE_GB = 5            # ... and a running one ends before the drive is full
QUIT = "stopped by Ctrl+C"


def free_gb(path: Path) -> float:
    """Free room on the drive holding `path` (its nearest existing parent), GB."""
    p = Path(path).resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free / 1e9


class LieWatch:
    """A look for the Lie Detector at most once every `every_s`, on its own thread: `offer` hands it the newest
    frame and returns at once. Seen -> the frame saved, the siren until its window is gone (judged on the frames
    still being offered)."""

    def __init__(self, lie, say, out: Path, every_s: float = 1.0, alarm=None):
        self.lie, self.say, self.out, self.every_s = lie, say, Path(out), every_s
        self.alarm = alarm or lie_alarm
        self.seen = 0
        self._frame, self._next = None, 0.0
        self._wake, self._stop = threading.Event(), False
        self._thread = threading.Thread(target=self._run, name="lie-watch", daemon=True)
        self._thread.start()

    def offer(self, frame, now: float | None = None) -> None:
        now = time.perf_counter() if now is None else now
        if now >= self._next:
            self._next = now + self.every_s
            self._frame = frame
            self._wake.set()

    def _run(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            if self._stop:
                return
            frame = self._frame
            try:
                if frame is None or not self.lie.seen(frame):
                    continue
                self.seen += 1
                import cv2
                self.out.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(self.out / f"lie_{datetime.now():%H%M%S}_{self.seen}.png"), frame)
                self.say("LIE DETECTOR on screen -> siren until its window is gone (the recording goes on)")
                self.alarm(lambda: self._frame is not None and self.lie.seen(self._frame))
                self.say("lie detector window gone")
            except Exception as e:                           # noqa: BLE001 - a failed look must not end the watch
                self.say(f"lie detector look failed: {type(e).__name__}: {e}")

    def close(self) -> None:
        self._stop = True
        self._wake.set()
        self._thread.join(5.0)


def file_later(out: Path, say=print):
    """The recording `out` (CORPUS/incoming/NAME) files itself: `corpus.py add` in its own process, below normal
    priority, out of reach of the console's Ctrl+C; what it says goes to CORPUS/work/filing/NAME.log and, when it
    is done, through `say`. -> the process (None: `out` is not in a corpus' incoming folder - said, not filed)."""
    out = Path(out)
    tool = Path(__file__).resolve().parents[2] / "tools" / "data" / "corpus.py"
    if out.parent.name != "incoming" or not tool.exists():
        say(f"not filed by itself (not in a corpus' incoming folder): python tools/data/corpus.py add {out}")
        return None
    root = out.parent.parent
    log = root / "work" / "filing" / f"{out.name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
             | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with open(log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen([sys.executable, "-u", str(tool), "--corpus", str(root), "add", "--brief", str(out)],
                                stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, cwd=str(tool.parents[2]),
                                creationflags=flags)
    say(f"filing {out.name} in the background (its words: {log})")

    def report():
        code = proc.wait()
        try:
            said = [x.rstrip() for x in log.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
        except OSError:
            said = []
        keep = [x for x in said if "#" in x.split("frames")[0] or "filed" in x or "NOT" in x or "Lie Detector" in x]
        for x in keep or said[-5:]:
            say(f"filing {out.name}: {x.strip()}")
        if code != 0:
            say(f"filing {out.name}: NOT FILED - it stays in {out.parent}; tell Claude (the whole of it: {log})")

    threading.Thread(target=report, name="filing", daemon=True).start()
    return proc


def _native(screen) -> str | None:
    """Why the picture can't be recorded as it is, or None: the video is the game's own 1366x768 pixels."""
    box, cols = getattr(screen, "box", None), getattr(screen, "cols", None)
    if box and cols and (cols[1] - cols[0], box["height"]) != (W, H):
        return (f"the game picture is {cols[1] - cols[0]}x{box['height']}, not the native {W}x{H} window: set the "
                "game windowed at exactly 1366x768 (display scale 100 %)")
    return None


def _gaps(dt: list) -> str:
    """'frame gaps p50 16.7 / p99 17.4 / max 33.1 ms, 2 over 25 ms' from the times between grabbed frames."""
    if not dt:
        return "frame gaps: none"
    s = sorted(dt)
    late = sum(d > 0.025 for d in dt)
    return (f"time between frames p50 {1000 * s[len(s) // 2]:.1f} / p99 {1000 * s[int(0.99 * (len(s) - 1))]:.1f} / "
            f"max {1000 * s[-1]:.1f} ms; {late} over 25 ms (a frame and a half)")


def record_one(out: Path, cfg: Config, kb, screen, lie, hz, until, where: str = "", facts: dict | None = None,
               mouse=None) -> str:
    """One recording into `out` until `until()` gives a reason. Returns the status (the reason / why it was
    aborted). `where`: the log's words about the captured picture. `facts`: session.json's content known before
    the start (session.facts). `mouse()`: the mouse buttons held, asked once per frame (session.buttons)."""
    mouse = mouse or session.buttons
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "log.txt", "w", buffering=1, encoding="utf-8")
    t0, epoch = time.perf_counter(), time.time()             # the same moment on both clocks
    session.write(out, facts, epoch, capture={"picture": where})

    def say(msg):
        line = f"{time.perf_counter() - t0:7.2f}s {msg}"
        print(line.encode("ascii", "replace").decode(), flush=True)
        log.write(line + "\n")

    say(f"recording -> {out} ({where}); {free_gb(out):.0f} GB free on the drive")
    from .keylog import KeyLogger
    vw = VideoWriter(out, note={"by": "record", "pieces": True})
    keylog = KeyLogger(out / "keys.jsonl", t0, focused=kb.focused).start()        # the same clock as frames.jsonl
    say("recording your keys -> keys.jsonl" + (f" - FAILED: {keylog.error}" if keylog.error else "")
        + f"; marker key {cfg.keys.note.upper()} (optional: one line per press in notes.txt afterwards)")
    watch = LieWatch(lie, say, out)
    status, n, active, dt, last, next_room = "ok", 0, 0.0, [], None, 0.0
    black, loads = 0, 0                                      # dark frames in a row; loading screens so far
    try:
        while (reason := until()) is None:
            try:
                if not kb.focused():
                    raise FocusLost()
                window.guard(screen)
                frame = screen.grab()
                now = time.perf_counter()
                if not kb.focused():
                    raise FocusLost()
                window.guard(screen)                 # aimed before and after: the frame is the whole game picture
                dark = is_dark(frame)
                black = black + 1 if dark else 0
                cut = black == DARK_RUN                      # a loading screen: the next map's files begin here
                loads += cut
                vw.put(frame, n, now - t0, screen.cursor(), buttons=mouse(), cut=cut, dark=dark)
                n += 1
                if last is not None:
                    dt.append(now - last)
                    active += now - last
                last = now
                watch.offer(frame, now)
                if vw.error:
                    status = f"aborted: {vw.error}"
                    break
                if now >= next_room:                 # (a cheap look every 10 s: never fill the drive)
                    next_room = now + 10.0
                    if free_gb(out) < STOP_FREE_GB:
                        status = f"stopped: under {STOP_FREE_GB} GB free on the drive"
                        break
            except FocusLost as e:
                say(window.pause_line(e, foreground_title).replace("; keys released", "; recording paused"))
                last, black = None, 0                # (the pause is not a frame gap)
                if window.wait_back(screen, kb.focused, hz, say, lambda: until() is None, e):
                    say("resumed")
        else:
            status = reason
    except KeyboardInterrupt:                        # Ctrl+C in the console: this recording ends like any other
        status = QUIT
    except Exception as e:                           # noqa: BLE001 - report anything; the video is closed below
        status = f"aborted: {type(e).__name__}: {e}"
        log.write(traceback.format_exc())
    finally:
        keylog.stop()
        watch.close()
        vw.close()
    marks = 0
    try:
        import json
        with open(out / "keys.jsonl", encoding="utf-8") as f:
            marks = sum(1 for k in map(json.loads, f) if k.get("down") and k.get("key") == cfg.keys.note)
    except (OSError, ValueError):
        pass
    say(status)
    say(f"keys: {keylog.n} recorded, hook lag max {keylog.lag_max} ms; marks ({cfg.keys.note.upper()}): {marks}"
        + (f", error: {keylog.error}" if keylog.error else ""))
    say(f"frames: {n} grabbed in {active:.1f} s of recording = {n / max(active, 1e-6):.1f} a second; "
        f"{vw.written} in the video, {vw.dropped} dropped")
    say(_gaps(dt))
    say(vw.summary(active))
    say(f"loading screens: {loads} (the video starts a new file at each: {loads + 1} piece(s))")
    if watch.seen:
        say(f"lie detector seen {watch.seen} time(s)")
    log.close()
    return status


def record(out_root: Path, cfg: Config, hotkeys: Hotkeys | None = None, poll_s: float = 0.03,
           max_recordings: int | None = None, labels=(), file: bool = True) -> int:
    """Stay loaded: cfg.keys.start starts a recording, cfg.keys.stop ends it; Ctrl+C in the console quits.
    `labels`: the words the player gave these recordings (`--label exploration`: what they set out to do), kept
    in each recording's session.json and, once it is filed, in the names of its captures. `max_recordings`: for
    tests."""
    out_root = Path(out_root)
    t0 = time.perf_counter()

    def say(msg):
        print(f"{time.perf_counter() - t0:7.2f}s {msg}".encode("ascii", "replace").decode(), flush=True)

    hwnd = find_window()
    if not hwnd:
        say("MapleStory window not found")
        return 1
    try:
        out_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        say(f"can't make {out_root}: {e}")
        return 1
    hz = Humanizer(cfg.humanize.jitter, cfg.humanize.seed, cfg.humanize.drift)
    kb = Keyboard(hwnd, hz, cfg.humanize, cfg.keys)          # only asked "is the game focused?": no key is ever sent
    screen = Screen(hwnd)
    say(f"capture: {screen.kind}{' (' + screen.note + ')' if screen.note else ''}")
    facts = session.facts(cfg, "record", ASSETS, labels, {"kind": screen.kind, "note": screen.note})
    from ..perception.liedetector import LieDetector
    lie = LieDetector.load(ASSETS, background=False)
    start_key, stop_key = cfg.keys.start, cfg.keys.stop
    hk = hotkeys or Hotkeys([start_key, stop_key])
    say(f"ready: {start_key.upper()} = start recording (you play, nothing is pressed; your keys are recorded), "
        f"{stop_key.upper()} = stop, Ctrl+C here = quit. Recordings -> {out_root} ({free_gb(out_root):.0f} GB free). "
        "The minimap open in its usual place; the Lie Detector is watched between recordings too"
        + (f". Labels: {', '.join(labels)}" if labels else ""))
    idle = LieWatch(lie, say, out_root)
    aim = window.Aim(screen, say)
    done, next_look = 0, 0.0

    def until():
        return f"stopped by {stop_key.upper()}" if hk.pressed(stop_key) else None

    try:
        while max_recordings is None or done < max_recordings:
            if not hk.pressed(start_key):
                if time.perf_counter() >= next_look:          # idle: only the Lie Detector look, once a second
                    next_look = time.perf_counter() + idle.every_s
                    frame = screen.grab() if aim.ok() else None      # (window moved: re-aimed once it rests)
                    if frame is not None and aim.ok():
                        idle.offer(frame)
                time.sleep(poll_s)
                continue
            if not kb.focused():
                say(f"{start_key.upper()} ignored: the game isn't the focused window")
                continue
            cols = screen.calibrate()                         # the game is in front now: measure where it is
            why = _native(screen)
            room = free_gb(out_root)
            if why is None and room < MIN_FREE_GB:
                why = f"only {room:.0f} GB free on the drive of {out_root} (a recording needs {MIN_FREE_GB}+)"
            if why is not None:
                chirp(False)
                say(f"not started: {why}")
                continue
            done += 1
            out = out_root / f"{datetime.now():%Y%m%d_%H%M%S}_{done}"
            chirp(True)
            status = record_one(out, cfg, kb, screen, lie, hz, until, _picture(screen, cols), facts)
            chirp(False)
            say(f"recording #{done} ended: {status} -> {out}; {start_key.upper()} to start another")
            if file and not status.startswith("aborted"):
                file_later(out, say)
            else:
                say(f"not filed: python tools/data/corpus.py add {out}")
            if status == QUIT:
                break
    except KeyboardInterrupt:
        say("quit")
    finally:
        idle.close()
        screen.close()
    return 0
