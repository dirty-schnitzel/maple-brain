"""The live loop: capture -> perceive -> brain -> execute, with focus/HP safety and recording.

Two ways to drive it:
  * run   - one timed hunt (3 s countdown, game brought to front, stops at the time limit)
  * serve - stays loaded and idle; F7 starts a hunt, F8 stops it (keys released), as often as you like.
            Between hunts F10 = next mode (auto / platform), F9 = mark / unmark the platform we stand on (platform
            mode: the hunt stays on the marked platforms; runtime/marks.py)

Safety that does not depend on the brain:
  * keys are only sent while the game has focus; a frame grabbed while focus was leaving is discarded
  * focus lost -> every key released, paused until the game is back
  * the game window moved -> paused the same way until it rests, then the capture is re-aimed; not 1366x768 any
    more (resized, minimized, gone) -> paused until it is (runtime/window.py)
  * no clean scene model for the map / not a native 1366x768 window -> the hunt doesn't start (`refuse`)
  * the scene camera not found mid-hunt -> every key released, no presses until it is found again (hunt_v2)
  * Stop (HP) -> release, alarm beep, end the hunt
  * Stop (Lie Detector) -> release, keep sounding a siren until its window is gone (the user answers it), end
  * every key released when a hunt ends, whatever happened
"""
import ctypes
import json
import time
import traceback
import winsound
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from ..capture import H as SCREEN_H, W as SCREEN_W, Screen, find_window
from ..config import Config
from ..humanize import Humanizer
from ..keyboard import FocusLost, Keyboard, bring_to_front, foreground_title
from ..perception.perceiver import MapKit, Perceiver
from . import window
from .marks import Marks
from .recorder import Recorder

ASSETS = Path(__file__).resolve().parents[2] / "assets"
VK = {f"f{i}": 0x6F + i for i in range(1, 13)}          # F1 = 0x70 ... F12 = 0x7B


def alarm():
    for _ in range(3):
        winsound.Beep(1200, 250)
        winsound.Beep(800, 250)


def chirp(up: bool):
    """Short confirmation that a hotkey was taken: rising = started, falling = stopped."""
    for f in ((700, 1100) if up else (1100, 700)):
        winsound.Beep(f, 90)


def lie_alarm(still_there, max_s: float = 120.0):
    """A siren distinct from the HP alarm, repeated while the Lie Detector is on screen (at most `max_s`)."""
    t_end = time.perf_counter() + max_s
    while True:
        for f in (1500, 1000, 1500, 1000):
            winsound.Beep(f, 180)
        try:
            gone = not still_there()
        except Exception:                        # noqa: BLE001 - can't look: assume it's still there
            gone = False
        if gone or time.perf_counter() >= t_end:
            return


def _key_down(vk: int) -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


class Hotkeys:
    """Edge-triggered global key polling: `pressed(name)` is True once per press. Works while the game has focus
    (the key still reaches the game too)."""

    def __init__(self, names, key_down=_key_down):
        self.key_down = key_down
        self.vk = {n: VK[n] for n in names}
        self.was = {n: self.key_down(v) for n, v in self.vk.items()}      # a key already down doesn't count

    def pressed(self, name) -> bool:
        if name not in self.vk:                           # not watched (tests that script only F7 / F8)
            return False
        now = self.key_down(self.vk[name])
        hit = now and not self.was[name]
        self.was[name] = now
        return hit


@dataclass
class Rig:
    """Everything a hunt needs that is loaded once."""
    cfg: Config
    hz: Humanizer
    kb: object
    screen: object
    kit: object                     # perception.perceiver.MapKit of the hunt's map (None: no map loaded)
    lie: object
    self_tag: np.ndarray
    locator: object = None          # nav.localize.MinimapLocator (with a map): our map position / platform
    ident: object = None            # nav.identify.MapIdentifier: no --map -> the map is recognised on every start
    maps: dict = None               # map id -> (kit, locator), loaded once per process
    drops: object = None            # perception.drops.DropFinder: built once per process with the first clean map


def _map_name(map_id: int) -> str:
    from ..gamedata import load_manifest
    e = load_manifest(ASSETS / "mcw")["maps"].get(str(map_id)) or {}
    return f"{e.get('street') or '?'} / {e.get('name') or '?'}"


def _load_scene(map_id: int):
    """The scene model for the scene camera (PLAN-perception.md steps 1-2) -> (Scene, "") or (None, why): no
    `assets scene` for the map, or moving / animated backgrounds (not covered yet: Perion's clouds)."""
    from ..scene import Scene
    if not Scene.have(map_id):
        return None, f"no scene model (python -m maplebrain assets scene {map_id})"
    scene = Scene.load(map_id)
    if not scene.clean:
        return None, "moving / animated backgrounds (not covered by the scene model yet)"
    return scene, ""


def _load_map(rig: "Rig", map_id: int, say) -> bool:
    """Make `map_id` the hunt's map: its MapKit (navmap, mob data, scene model + the fit on clean maps) + locator
    (cached), cfg.perception.map_id. False if assets/mcw doesn't have it (every map of the client is there; a new
    one after a patch needs `assets build`). A map without a clean scene loads too (map recognition, platform
    marks, observe recordings), but no hunt starts there (`refuse`)."""
    cfg = rig.cfg
    if rig.maps is None:
        rig.maps = {}
    if map_id not in rig.maps:
        from ..gamedata import have_map
        from ..nav.localize import MinimapLocator
        from ..nav.navmap import NavMap
        if not have_map(map_id, ASSETS / "mcw"):
            say(f"map {map_id} isn't in assets/mcw (wrong id? new map after a game patch: re-export the client "
                "and run `assets build`, see assets/README.md)")
            return False
        mcw = ASSETS / "mcw"
        mj = json.loads((mcw / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in mj.get("mobs") or []})
        mobs = {i: json.loads((mcw / "mobs" / str(i) / "mob.json").read_text(encoding="utf-8"))
                for i in ids if (mcw / "mobs" / str(i) / "mob.json").exists()}
        navmap = NavMap.for_map(map_id, mcw, cfg.nav)
        kit = MapKit(map_id, navmap, mobs)
        try:
            import torch
            kit.dev = "cuda" if torch.cuda.is_available() else None
        except ImportError:
            kit.dev = None
        scene, why = _load_scene(map_id) if kit.dev is not None else (None, "no CUDA GPU (torch)")
        if scene is not None:
            from ..cover import Cover
            from ..perception.fit import Fitter
            torch.backends.cudnn.benchmark = True                  # (as the deleted GPU detector set it)
            t = time.perf_counter()
            kit.scene, kit.fitter = scene, Fitter(scene, map_id, mcw)
            kit.fitter.warm()
            kit.cover = Cover.for_map(map_id, mcw)
            groups = sum(it[0] == "group" for g in scene.groups.values() for it in g)
            say(f"scene camera + fit: {kit.fitter.G} poses, {groups} pre-composed background groups of "
                f"{len(scene.backs)} layers; built in {time.perf_counter() - t:.2f} s")
            if cfg.perception.drops:                    # drops (PLAN-loot.md, in shadow): one finder per process
                if getattr(rig, "drops", None) is None:
                    from ..perception.drops import DropFinder
                    t = time.perf_counter()
                    rig.drops = DropFinder(device=kit.dev)
                    rig.drops.warm()
                    say(f"{rig.drops.describe()}; graph captured, {time.perf_counter() - t:.2f} s in all")
                kit.drops = rig.drops
        else:
            kit.why = why
            say(f"map {map_id}: {why} -> no scene camera: hunts are refused here (observe records without mobs)")
        locator = MinimapLocator.for_map(map_id, mcw, cfg.nav, navmap)
        rig.maps[map_id] = (kit, locator)
        say(f"map {map_id} {_map_name(map_id)}: mobs "
            + (", ".join(f"{n} ({i})" for i, n in kit.names.items()) or "none")
            + f"; {len(navmap.platforms)} platforms, {len(navmap.ropes)} ropes, {len(navmap.links)} links")
    rig.kit, rig.locator = rig.maps[map_id]
    cfg.perception.map_id = map_id
    return True


def refuse(rig: "Rig") -> str | None:
    """Why a hunt (or a goto) can't start here, or None. It needs the scene camera + the fit (the only mob
    perception there is): a loaded map with a clean scene model, and the game window at its native 1366x768 (the
    scene model is pixel-exact; a resampled picture never registers)."""
    kit = rig.kit
    if kit is None or rig.locator is None or rig.locator.navmap is None:
        return "no map loaded (the map wasn't recognised: open the minimap, or pass --map)"
    if not kit.clean:
        return (f"map {kit.map_id} {_map_name(kit.map_id)} has no clean scene ({kit.why}): the hunt needs the scene "
                "camera - only clean maps are hunted for now")
    box, cols = getattr(rig.screen, "box", None), getattr(rig.screen, "cols", None)
    if box and cols and (cols[1] - cols[0], box["height"]) != (SCREEN_W, SCREEN_H):
        return (f"the game picture is {cols[1] - cols[0]}x{box['height']}, not the native {SCREEN_W}x{SCREEN_H} "
                "window: set the game windowed at exactly 1366x768 (display scale 100 %)")
    return None


def _init_map(rig: "Rig", say, frames: int = 3, save_to: Path | None = None) -> bool:
    """Start of a hunt (game in front, capture calibrated): which map are we on? --map given -> that one. Otherwise
    the minimap is matched against every map's (a few frames ~0.25 s apart) and that map is loaded. False = can't
    tell: don't hunt (wrong sprites / footholds are worse than none); the frame goes to `save_to`, a failed start
    records nothing else to look at afterwards."""
    if rig.ident is None:
        return True
    shots = [rig.screen.grab()]
    for _ in range(frames - 1):
        time.sleep(rig.hz.vary(0.25))
        shots.append(rig.screen.grab())
    t = time.perf_counter()
    m = rig.ident.identify(shots)
    took = time.perf_counter() - t
    if m.map_id is None:
        near = f"; best {m.fits[0][1]} {_map_name(m.fits[0][1])} {m.fits[0][0]:.2f}" if m.fits else ""
        alt = f", {m.runner_up} {_map_name(m.runner_up)} {m.runner_score:.2f}" if m.runner_up is not None else ""
        say(f"can't tell which map this is: {m.why}{near}{alt} - open the minimap (uncovered) or pass --map")
        if save_to is not None:
            import cv2
            save_to.mkdir(parents=True, exist_ok=True)
            path = save_to / f"unknown_map_{datetime.now():%Y%m%d_%H%M%S}.png"
            cv2.imwrite(str(path), shots[-1])
            say(f"frame saved: {path}")
        return False
    if m.map_id != rig.cfg.perception.map_id:
        alt = f" (next: {m.runner_up} {_map_name(m.runner_up)} {m.runner_score:.2f})" if m.runner_up is not None else ""
        say(f"map recognised: {m.map_id} {_map_name(m.map_id)}, score {m.score:.2f}{alt}{', ' + m.why if m.why else ''}, {took * 1000:.0f} ms")
    return _load_map(rig, m.map_id, say)


def _setup(cfg: Config, say, focus: bool):
    hwnd = find_window()
    if not hwnd:
        say("MapleStory window not found")
        return None
    hz = Humanizer(cfg.humanize.jitter, cfg.humanize.seed, cfg.humanize.drift)
    kb = Keyboard(hwnd, hz, cfg.humanize, cfg.keys)
    if focus and not kb.focused():
        say("switching to the game in 3s - hands off the keyboard and mouse")
        time.sleep(3)
        say("game is in front" if bring_to_front(hwnd) else "couldn't bring the game to front - switch to it yourself")
    screen = Screen(hwnd)
    say(f"capture: {screen.kind}{' (' + screen.note + ')' if screen.note else ''}")
    from ..perception.liedetector import LieDetector
    rig = Rig(cfg, hz, kb, screen, None, LieDetector.load(ASSETS), np.load(ASSETS / "self_tag_gray.npy"))
    if cfg.perception.map_id is not None:
        if not _load_map(rig, cfg.perception.map_id, say):
            return None
        say(f"map fixed by --map: {cfg.perception.map_id}")
    else:
        from ..nav.identify import MapIdentifier
        rig.ident = MapIdentifier.load(ASSETS / "mcw")
        if rig.ident.canvases:
            say(f"no --map: the map is recognised from the minimap at every start ({len(rig.ident.canvases)} maps)")
        else:
            rig.ident = None
            say("no --map and no minimaps on disk (`assets build`): no map - hunts are refused, observe records "
                "without mobs")
    return rig


def _hunt(rig: Rig, rec: Recorder, t0: float, until, observe: bool = False, area=None) -> str:
    """A hunt (runtime/hunt_v2.py; `area`: platform mode's marked platforms) or, `observe`, a recording: perceive
    and record only until `until()` returns a reason - no brain, no key ever sent or released (the player plays;
    Keyboard.release_all would send key-ups for the arrows / shift / attack and cut the player's own jumps), the
    player's keys -> keys.jsonl. A Lie Detector still sounds the siren. Returns the status."""
    if not observe:
        from .hunt_v2 import hunt_v2
        return hunt_v2(rig, rec, t0, until, area=area)
    cfg, kb, screen = rig.cfg, rig.kb, rig.screen

    def say(msg):
        rec.say(f"{time.perf_counter() - t0:7.2f}s {msg}")

    if rig.locator is not None:
        rig.locator.origin = None       # the screen crop is re-measured per hunt: the canvas may sit a fraction off
    why = refuse(rig)
    if why is not None:
        say(f"observe: {why} -> recording frames, HUD, our tag and the minimap; no camera, no mobs")
    perceiver = Perceiver(cfg, rig.self_tag, rig.kit, lie_detector=rig.lie, locator=rig.locator)
    from .keylog import KeyLogger
    keylog = KeyLogger(rec.out / "keys.jsonl", t0, focused=kb.focused).start()   # same clock as ticks (obs.t)
    say(f"recording your keys -> keys.jsonl" + (f" - FAILED: {keylog.error}" if keylog.error else ""))
    status, start, frames_n = "ok", time.perf_counter(), 0
    try:
        while (reason := until()) is None:
            try:
                tick0 = time.perf_counter()
                if not kb.focused():
                    raise FocusLost()
                window.guard(screen)
                frame = screen.grab()
                if not kb.focused():
                    raise FocusLost()
                window.guard(screen)                 # aimed before and after: the frame is the whole game picture
                frames_n += 1
                tg = time.perf_counter()
                obs = perceiver.observe(frame, time.perf_counter() - t0, screen.cursor())
                tp = time.perf_counter()
                if obs.lie_detector:
                    say("LIE DETECTOR on screen -> siren until its window is gone")
                    lie_alarm(lambda: rig.lie.seen(screen.grab()))
                    say("lie detector window gone")
                timings = {"grab_ms": round(1000 * (tg - tick0)), "perceive_ms": round(1000 * (tp - tg)),
                           "total_ms": round(1000 * (time.perf_counter() - tick0))}
                parts = getattr(perceiver, "parts", None)
                if parts:                                       # where perceive_ms went (rest = after the last part)
                    timings["parts"] = {**parts, "rest": round(1000 * (tp - tg) - sum(parts.values()), 1)}
                rec.tick(frame, obs, [], "OBSERVE", timings, facts=perceiver.facts)
            except FocusLost as e:
                say(window.pause_line(e, foreground_title))
                if window.wait_back(screen, kb.focused, rig.hz, say, lambda: until() is None, e):
                    say("resumed")
        else:
            if reason != "time":
                status = reason
    except Exception as e:                       # noqa: BLE001 - report anything
        status = f"aborted: {type(e).__name__}: {e}"
        rec.log.write(traceback.format_exc())
    finally:
        keylog.stop()
        say(f"keys: {keylog.n} recorded, hook lag max {keylog.lag_max} ms"
            + (f", error: {keylog.error}" if keylog.error else ""))
    elapsed = time.perf_counter() - start
    say(status)
    say("stats " + json.dumps({"frames": frames_n, "fps": round(frames_n / max(elapsed, 1e-6), 1)}))
    return status


def _picture(screen, cols=None) -> str:
    """The log line about the captured picture (capture.picture); `cols` from a calibrate() just done."""
    from ..capture import picture
    box = getattr(screen, "box", None)
    return picture(cols if cols is not None else screen.cols, box["height"] if box else None, screen.kind)


def run(out: Path, seconds: float, cfg: Config, focus: bool = True, frames_every: int = 3,
        frames_png: bool = False) -> int:
    rec = Recorder(out, every=frames_every, png=frames_png)
    t0 = time.perf_counter()

    def say(msg):
        rec.say(f"{time.perf_counter() - t0:7.2f}s {msg}")

    rig = _setup(cfg, say, focus)
    if rig is None:
        rec.close()
        return 1
    try:
        say("waiting up to 180s for MapleStory to be the foreground window...")
        deadline = time.time() + 180
        while not rig.kb.focused():
            if time.time() > deadline:
                say("timed out waiting for the game")
                return 1
            time.sleep(rig.hz.vary(0.2))
        time.sleep(rig.hz.vary(1.0))
        say(_picture(rig.screen, rig.screen.calibrate()))                # measured with the game in front
        if not _init_map(rig, say, save_to=out):
            return 1
        if focus and not rig.kb.focused():           # loading a map takes ~25 s (GPU warm-up): focus may have
            say(f"game lost focus while loading (foreground: '{foreground_title()}') - bringing it back")   # moved
            bring_to_front(rig.kb.hwnd)
            time.sleep(rig.hz.vary(0.5))
        end = time.perf_counter() + seconds
        status = _hunt(rig, rec, t0, lambda: "time" if time.perf_counter() >= end else None)
    finally:
        rig.screen.close()
        rec.close()
    return 0 if status == "ok" else 2


def _platform_here(rig: Rig, say, frame=None):
    """Between hunts (F9): (map id, platform id, its description) we stood on in `frame` (grabbed at the press; the
    first F9 on a map loads it, ~20 s live, and we may have walked on by then), from the minimap - the map
    recognised first (as at F7).
    None (said why) when it can't tell: the minimap is covered / closed, we're on a rope or in the air."""
    from ..perception import hud
    loc = rig.locator
    if loc is None or loc.navmap is None:
        say("no map loaded: can't tell the platform")
        return None
    loc.origin, loc.lost = None, False                    # measure the minimap window afresh, as a hunt does
    if frame is None:
        frame = rig.screen.grab()
    if frame is None or not loc.calibrate(frame):
        say("minimap not found (closed / covered?): can't tell the platform")
        return None
    loc.follow(frame)
    w = loc.where(hud.minimap_dot(frame, loc.dot_box()))
    if w is None or w.platform is None:
        say("not standing on a platform (rope / air / no minimap dot): stand on it and try again")
        return None
    from .hunt_v2 import describe_platform
    return rig.cfg.perception.map_id, w.platform, describe_platform(loc.navmap, w.platform)


def _mark_here(rig: Rig, marks: Marks, say, out_root: Path):
    """F9 between hunts: mark / unmark the platform we stand on (platform mode only)."""
    key = rig.cfg.keys.mark.upper()
    if marks.mode != "platform":
        say(f"{key}: platform marks are for platform mode ({rig.cfg.keys.mode.upper()} to switch)")
        return
    if not rig.kb.focused():
        say(f"{key} ignored: the game isn't the focused window")
        return
    t = time.perf_counter()
    rig.screen.calibrate()
    pressed_at = rig.screen.grab()                        # where we stand NOW, before the (slow) map load
    if not _init_map(rig, say, frames=1, save_to=out_root):
        chirp(False)
        return
    here = _platform_here(rig, say, pressed_at)
    if here is None:
        chirp(False)
        return
    map_id, pid, label = here
    on = marks.toggle(map_id, pid)
    area = marks.area(map_id)
    took = time.perf_counter() - t
    say(f"{'marked' if on else 'unmarked'} {label}; marked on {_map_name(map_id)}: "
        + (", ".join(map(str, sorted(area))) or "none")
        + (f" (took {took:.0f} s loading the map: an {key} pressed meanwhile was NOT seen - press it again)"
           if took > 2 else ""))
    chirp(on)


def serve(out_root: Path, cfg: Config, frames: int = 0,
          hotkeys: Hotkeys | None = None, poll_s: float = 0.03, max_hunts: int | None = None,
          observe: bool = False, frames_png: bool = False) -> int:
    """Stay loaded: cfg.keys.start starts a hunt, cfg.keys.stop stops it; Ctrl+C in the console quits. Each hunt is
    recorded in its own folder under `out_root` (log + ticks; every `frames`-th frame, 0 = none; True = 3). `frames_png`:
    lossless frames. `max_hunts`: for tests.
    `observe`: the start key starts a recording only - the player plays, the bot never touches a key."""
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    def say(msg):
        print(f"{time.perf_counter() - t0:7.2f}s {msg}".encode("ascii", "replace").decode(), flush=True)

    rig = _setup(cfg, say, focus=False)
    if rig is None:
        return 1
    start_key, stop_key, mark_key, mode_key = cfg.keys.start, cfg.keys.stop, cfg.keys.mark, cfg.keys.mode
    hk = hotkeys or Hotkeys([start_key, stop_key, mark_key, mode_key])
    what = "start recording (observe: the bot presses no keys, yours are recorded)" if observe else "start hunting"
    say(f"ready: {start_key.upper()} = {what}, {stop_key.upper()} = stop, Ctrl+C here = quit "
        "(the Lie Detector is watched between hunts too)")
    marks = Marks()
    if not observe:
        say(f"mode: {marks.mode} - {mode_key.upper()} = next mode (auto / platform), {mark_key.upper()} = mark / "
            "unmark the platform you stand on (platform mode, between hunts)")
    hunts, next_look, n_lie = 0, 0.0, 0
    aim = window.Aim(rig.screen, say)                    # between hunts: is the capture still on the window?

    def until():
        if hk.pressed(stop_key):
            return f"stopped by {stop_key.upper()}"
        for k in (mark_key, mode_key):
            if hk.pressed(k):
                say(f"{k.upper()} ignored: a hunt is running ({stop_key.upper()} first)")
        return None

    try:
        while max_hunts is None or hunts < max_hunts:
            if not observe and hk.pressed(mode_key):
                say(f"mode: {marks.next_mode()}" + (f" - {mark_key.upper()} on each platform to hunt on"
                                                     if marks.mode == "platform" else ""))
                chirp(marks.mode == "platform")
            if not observe and hk.pressed(mark_key):
                _mark_here(rig, marks, say, out_root)
            if not hk.pressed(start_key):
                # idle between hunts: still watch for the Lie Detector (session 9: one came up seconds after a
                # hunt ended and nothing was looking). Only looks - no key is sent.
                if time.perf_counter() >= next_look:
                    next_look = time.perf_counter() + rig.lie.every_s
                    frame = rig.screen.grab() if aim.ok() else None      # window moved: re-aimed once it rests
                    if frame is not None and aim.ok() and rig.lie.seen(frame):
                        n_lie += 1
                        import cv2
                        cv2.imwrite(str(out_root / f"lie_idle_{datetime.now():%H%M%S}_{n_lie}.png"), frame)
                        say("LIE DETECTOR on screen (idle, between hunts) -> siren until its window is gone")
                        lie_alarm(lambda: rig.lie.seen(rig.screen.grab()))
                        say("lie detector window gone")
                time.sleep(poll_s)
                continue
            if not rig.kb.focused():
                say(f"{start_key.upper()} ignored: the game isn't the focused window")
                continue
            cols = rig.screen.calibrate()                    # the game is in front now: measure where it is
            if not _init_map(rig, say, save_to=out_root):
                chirp(False)
                say(f"not started - {start_key.upper()} to try again")
                continue
            area = None
            if not observe and marks.mode == "platform":
                area = marks.area(rig.cfg.perception.map_id)
                if not area:
                    chirp(False)
                    say(f"platform mode: no platform marked on this map - {mark_key.upper()} on at least one first "
                        "(not started)")
                    continue
            hunts += 1
            out = out_root / f"{datetime.now():%Y%m%d_%H%M%S}_{hunts}"
            rec = Recorder(out, every=int(frames) * 3 if frames is True else int(frames), png=frames_png)
            say(f"hunt #{hunts} started -> {out} (map {rig.cfg.perception.map_id}, {_picture(rig.screen, cols)})")
            rec.log.write(f"map {rig.cfg.perception.map_id} {_map_name(rig.cfg.perception.map_id)}\n")  # livemap
            if area:
                rec.log.write(f"marked platforms {','.join(map(str, sorted(area)))}\n")             # livemap
            chirp(True)
            try:
                status = _hunt(rig, rec, time.perf_counter(), until, observe, area=area)
            finally:
                rec.close()
            chirp(False)
            say(f"hunt #{hunts} ended: {status} - {start_key.upper()} to start again")
    except KeyboardInterrupt:
        say("quit")
    finally:
        if not observe:
            rig.kb.release_all()
        rig.screen.close()
    return 0


def watch(out: Path, seconds: float, every_s: float = 1.0, gpu: bool = False) -> int:
    """Lie Detector watch with no hunt (session 9: one came up seconds after acc3's time limit, while the bot was
    gone and Claude analysed between runs - nothing looked at the screen). Grabs the game picture every ~`every_s`
    (mss, so a hunt's dxcam in another process is untouched), siren while the window is up, saves the frame.
    The game must be visible on the monitor (a window on top of it hides the panel). Once a second since 2026-11-16
    (was 0.3 s; PLAN-perception.md step 2.8: the Lie Detector gives 10+ s). `gpu`: the match on CUDA
    (liedetector.GpuLieLook, the same scores) instead of the CPU."""
    import cv2
    from ..perception.liedetector import LieDetector
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "log.txt", "a", encoding="utf-8")

    def say(msg):
        line = f"{datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    hwnd = find_window()
    if not hwnd:
        say("MapleStory window not found")
        return 1
    screen = Screen(hwnd, dxcam=False)                 # mss only
    aim = window.Aim(screen, say)                      # the window moved -> re-aimed; not 1366x768 / gone -> said
    lie = LieDetector.load(ASSETS)
    score = lie.score
    if gpu:
        import torch
        lie.use_gpu(torch.device("cuda"))
        score = lambda f: lie.gpu.look(torch.from_numpy(np.ascontiguousarray(f)).to(lie.gpu.dev))   # noqa: E731
    say(f"watching for the Lie Detector (game picture x {screen.cols}), {seconds:.0f}s, a look every {every_s:g} s "
        f"on the {'GPU' if gpu else 'CPU'}")
    t_end, n = time.perf_counter() + seconds, 0
    try:
        while time.perf_counter() < t_end:
            frame = screen.grab() if aim.ok() else None
            if frame is None or not aim.ok():          # not aimed (before or after the grab): no look this time
                time.sleep(every_s)
                continue
            s, loc = score(frame)
            if s >= lie.min_score:
                n += 1
                cv2.imwrite(str(out / f"lie_{datetime.now():%H%M%S}_{n}.png"), frame)
                say(f"LIE DETECTOR on screen (score {s:.2f} at {loc}) -> siren until it's gone")
                lie_alarm(lambda: lie.seen(screen.grab()))
                say("Lie Detector window gone")
            time.sleep(every_s)
    except KeyboardInterrupt:
        pass
    finally:
        screen.close()
        say(f"watch ended ({n} Lie Detector(s))")
    return 0
