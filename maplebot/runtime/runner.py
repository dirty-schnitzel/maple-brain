"""The live loop: capture -> perceive -> brain -> execute, with focus/HP safety and recording.

Two ways to drive it:
  * run   - one timed hunt (3 s countdown, game brought to front, stops at the time limit)
  * serve - stays loaded and idle; F7 starts a hunt, F8 stops it (keys released), as often as you like

Safety that does not depend on the brain:
  * keys are only sent while the game has focus; a frame grabbed while focus was leaving is discarded
  * focus lost -> every key released, paused until the game is back
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

from ..brain.actions import Forget, Learn, Look, Stop, Track, Untrack
from ..brain.brain import Brain
from ..capture import Screen, find_window
from ..config import Config
from ..humanize import Humanizer
from ..keyboard import FocusLost, Keyboard, bring_to_front, foreground_title
from ..perception.perceiver import Perceiver
from .keys import KeyDriver, LegacyExecutor
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
    sprites: object
    lie: object
    self_tag: np.ndarray
    locator: object = None          # nav.localize.MinimapLocator (with a map): our map position / platform
    ident: object = None            # nav.identify.MapIdentifier: no --map -> the map is recognised on every start
    maps: dict = None               # map id -> (sprites, locator), loaded once per process


def _map_name(map_id: int) -> str:
    from ..gamedata import load_manifest
    e = load_manifest(ASSETS / "mcw")["maps"].get(str(map_id)) or {}
    return f"{e.get('street') or '?'} / {e.get('name') or '?'}"


def _load_map(rig: "Rig", map_id: int, say) -> bool:
    """Make `map_id` the hunt's map: sprites + locator (cached), cfg.perception.map_id. False if assets/mcw doesn't
    have it (every map of the client is there; a new one after a patch needs `assets build`)."""
    cfg = rig.cfg
    if rig.maps is None:
        rig.maps = {}
    if map_id not in rig.maps:
        from ..gamedata import have_map
        from ..nav.localize import MinimapLocator
        from ..nav.navmap import NavMap
        from ..perception.sprites import SpriteDetector
        if not have_map(map_id, ASSETS / "mcw"):
            say(f"map {map_id} isn't in assets/mcw (wrong id? new map after a game patch: re-export the client "
                "and run `assets build`, see assets/README.md)")
            return False
        sprites = SpriteDetector.for_map(map_id, ASSETS / "mcw", min_score=cfg.perception.sprite_score)
        if cfg.perception.gpu:
            from ..perception.gpu_sprites import GpuBand, GpuSpriteDetector
            g = GpuSpriteDetector.for_map(map_id, ASSETS / "mcw", min_score=cfg.perception.sprite_score)
            import numpy as np
            g.find(np.zeros((768, 1366, 3), np.uint8))              # warm-up (~2 s, first CUDA call)
            say(f"GPU mob detection on {g.dev}: {g.K} sprite frames, whole screen; tracker search warm-up "
                f"{g.warm_near(occluded=True):.1f}s")
            sprites = GpuBand(g, sprites)
        navmap = NavMap.for_map(map_id, ASSETS / "mcw", cfg.nav)
        if cfg.perception.gpu:                                     # the tracker (passive: logs obs.mobs only)
            import json
            mj = json.loads((ASSETS / "mcw" / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
            from ..cover import Cover
            sprites.track_ctx = (navmap, mj, {
                i: json.loads((ASSETS / "mcw" / "mobs" / str(i) / "mob.json").read_text(encoding="utf-8"))
                for i in g.mob_ids}, None, Cover.for_map(map_id, ASSETS / "mcw"))
        locator = MinimapLocator.for_map(map_id, ASSETS / "mcw", cfg.nav, navmap)
        rig.maps[map_id] = (sprites, locator)
        say(f"map {map_id} {_map_name(map_id)}: sprites for "
            + (", ".join(f"{m.name} ({m.mob_id})" for m in sprites.mobs) or "nothing (no mobs here)")
            + f"; {len(navmap.platforms)} platforms, {len(navmap.ropes)} ropes, {len(navmap.links)} links")
    rig.sprites, rig.locator = rig.maps[map_id]
    cfg.perception.map_id = map_id
    return True


def _init_map(rig: "Rig", say, frames: int = 3) -> bool:
    """Start of a hunt (game in front, capture calibrated): which map are we on? --map given -> that one. Otherwise
    the minimap is matched against every map's (a few frames ~0.25 s apart) and that map is loaded. False = can't
    tell: don't hunt (wrong sprites / footholds are worse than none)."""
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
    kb = Keyboard(hwnd, hz, cfg.humanize)
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
            say("no --map and no minimaps on disk (`assets build`): mobs are only known by HP bars, motion "
                "and the learned library")
    return rig


class _NoKeys:
    """Executor stand-in for observe mode: the player is at the keys - never press, never release anything
    (Keyboard.release_all sends key-ups for the arrows/shift/space: it would cut the player's own jumps)."""
    last_move = 0.0

    def run(self, action):
        pass

    def release(self):
        pass

    def release_all(self):
        pass


def _hunt(rig: Rig, rec: Recorder, t0: float, until, observe: bool = False) -> str:
    """Hunt until `until()` returns a reason (time limit, F8 ...) or the brain stops; returns the status.
    Every key is released at the end, whatever happened. `observe`: perceive and record only - no brain, no keys
    (the player plays; e.g. jump measurements). A Lie Detector still sounds the siren."""
    cfg, hz, kb, screen = rig.cfg, rig.hz, rig.kb, rig.screen

    def say(msg):
        rec.say(f"{time.perf_counter() - t0:7.2f}s {msg}")

    drops = None
    if rig.sprites is not None and cfg.perception.loot_by_sight:
        from ..perception.drops import DropSpotter
        drops = DropSpotter()
    if rig.locator is not None:
        rig.locator.origin = None       # the screen crop is re-measured per hunt: the canvas may sit a fraction off
    perceiver = Perceiver(cfg, rig.self_tag, rig.sprites, lie_detector=rig.lie, drops=drops, locator=rig.locator)
    brain = Brain(cfg, hz=hz, navmap=rig.locator.navmap if rig.locator is not None else None)
    if brain.navmap is not None and cfg.nav.seek_spawns:          # per map, per hunt (the map recognised at F7)
        c = brain.navmap.spawn_center()
        say(f"spawns: {len(brain.navmap.spawns)} points, densest around map x {c:.0f} - idle walks head there"
            if c is not None else "spawns: none on this map - idle walks patrol as before")
    driver = None
    if observe:
        ex = _NoKeys()
    else:                                       # the keys on their own thread: no tap blocks the loop
        driver = KeyDriver(kb.send, kb.focused, hz, cfg.humanize).start()
        ex = LegacyExecutor(driver, kb.release_all)
    keylog = None
    if observe:                         # the player's own keys -> keys.jsonl, same clock as ticks (obs.t)
        from .keylog import KeyLogger
        keylog = KeyLogger(rec.out / "keys.jsonl", t0, focused=kb.focused).start()
        say(f"recording your keys -> keys.jsonl" + (f" - FAILED: {keylog.error}" if keylog.error else ""))
    status, start, frames_n = "ok", time.perf_counter(), 0
    try:
        while (reason := until()) is None:
            try:
                tick0 = time.perf_counter()
                if not kb.focused():
                    raise FocusLost()
                frame = screen.grab()
                if not kb.focused():
                    raise FocusLost()
                frames_n += 1
                tg = time.perf_counter()
                obs = perceiver.observe(frame, time.perf_counter() - t0, screen.cursor())
                tp = time.perf_counter()
                actions = [] if observe else brain.step(obs)
                if observe and obs.lie_detector:
                    say("LIE DETECTOR on screen -> siren until its window is gone")
                    lie_alarm(lambda: rig.lie.seen(screen.grab()))
                    say("lie detector window gone")
                if any(isinstance(a, Look) for a in actions):            # still look, then decide again
                    ex.release()
                    wait = hz.vary(cfg.perception.settle_s) - (time.perf_counter() - ex.last_move)
                    if wait > 0:                                         # camera still sliding: a look now is wasted
                        time.sleep(wait)
                        frame = screen.grab()
                    look = [frame]
                    for _ in range(cfg.perception.look_frames - 1):
                        time.sleep(hz.vary(cfg.perception.look_gap_s))
                        look.append(screen.grab())
                    if not kb.focused():
                        raise FocusLost()
                    obs = perceiver.look(look, obs, screen.cursor())
                    obs.t = time.perf_counter() - t0
                    frame = look[-1]
                    actions = [a for a in actions if not isinstance(a, Look)] + brain.step(obs)
                for line in brain.events:
                    rec.say(line)
                stop = next((a for a in actions if isinstance(a, Stop)), None)
                for a in actions:
                    if isinstance(a, Track):
                        perceiver.track(frame, a.box)
                    elif isinstance(a, Untrack):
                        perceiver.untrack()
                    elif isinstance(a, Learn):
                        perceiver.learn_target()
                    elif isinstance(a, Forget):
                        perceiver.forget_target(frame)
                    elif not isinstance(a, (Stop, Look)):
                        ex.run(a)
                perceiver.target_proven = bool(brain.target and brain.target.proven)
                timings = {"grab_ms": round(1000 * (tg - tick0)), "perceive_ms": round(1000 * (tp - tg)),
                           "total_ms": round(1000 * (time.perf_counter() - tick0))}
                if hasattr(rig.sprites, "all_hits"):            # --gpu: the whole screen's mobs + GPU time
                    timings["gpu_ms"] = round(rig.sprites.last_ms, 1)
                    timings["gpu_mobs"] = [[h.mob_id, *map(int, h.feet), h.pose.anim, h.score]
                                           for h in rig.sprites.all_hits]
                rec.tick(frame, obs, actions, brain.mode, timings)
                if stop:
                    ex.release_all()
                    status = f"STOPPED: {stop.reason}"
                    if obs.lie_detector:
                        say("LIE DETECTOR on screen -> keys released, siren until its window is gone")
                        lie_alarm(lambda: rig.lie.seen(screen.grab()))
                        say("lie detector window gone")
                    else:
                        alarm()
                    break
            except FocusLost:
                ex.release_all()
                say(f"PAUSED: game not focused (foreground: '{foreground_title()}'); keys released")
                while not kb.focused() and until() is None:
                    time.sleep(hz.vary(0.2))
                if kb.focused():
                    say("resumed")
                    brain.mode, brain.target, brain.held = "SEEK", None, None
                    perceiver.untrack()
                    time.sleep(hz.vary(1.0))
        else:
            if reason != "time":
                status = reason
    except Exception as e:                       # noqa: BLE001 - report anything, keys are released below
        status = f"aborted: {type(e).__name__}: {e}"
        rec.log.write(traceback.format_exc())
    finally:
        ex.release_all()
        if driver is not None:
            driver.stop()
            say(f"keys: {driver.sent} key events sent")
        if keylog is not None:
            keylog.stop()
            say(f"keys: {keylog.n} recorded, hook lag max {keylog.lag_max} ms"
                + (f", error: {keylog.error}" if keylog.error else ""))
    elapsed = time.perf_counter() - start
    stats = dict(brain.stats, frames=frames_n, fps=round(frames_n / max(elapsed, 1e-6), 1),
                 library=len(perceiver.library))
    say(status)
    say("stats " + json.dumps(stats))
    return status


def run(out: Path, seconds: float, cfg: Config, focus: bool = True, frames_every: int = 3) -> int:
    rec = Recorder(out, every=frames_every)
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
        say(f"game picture at x {rig.screen.calibrate()} ({rig.screen.kind})")       # measured with the game in front
        if not _init_map(rig, say):
            return 1
        end = time.perf_counter() + seconds
        status = _hunt(rig, rec, t0, lambda: "time" if time.perf_counter() >= end else None)
    finally:
        rig.screen.close()
        rec.close()
    return 0 if status == "ok" else 2


def serve(out_root: Path, cfg: Config, start_key: str = "f7", stop_key: str = "f8", frames: int = 0,
          hotkeys: Hotkeys | None = None, poll_s: float = 0.03, max_hunts: int | None = None,
          observe: bool = False) -> int:
    """Stay loaded: `start_key` starts a hunt, `stop_key` stops it; Ctrl+C in the console quits. Each hunt is
    recorded in its own folder under `out_root` (log + ticks; every `frames`-th frame, 0 = none; True = 3). `max_hunts`: for tests.
    `observe`: F7 starts a recording only - the player plays, the bot never touches a key."""
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    def say(msg):
        print(f"{time.perf_counter() - t0:7.2f}s {msg}".encode("ascii", "replace").decode(), flush=True)

    rig = _setup(cfg, say, focus=False)
    if rig is None:
        return 1
    hk = hotkeys or Hotkeys([start_key, stop_key])
    what = "start recording (observe: the bot presses no keys, yours are recorded)" if observe else "start hunting"
    say(f"ready: {start_key.upper()} = {what}, {stop_key.upper()} = stop, Ctrl+C here = quit "
        "(the Lie Detector is watched between hunts too)")
    hunts, next_look, n_lie = 0, 0.0, 0
    try:
        while max_hunts is None or hunts < max_hunts:
            if not hk.pressed(start_key):
                # idle between hunts: still watch for the Lie Detector (session 9: one came up seconds after a
                # hunt ended and nothing was looking). Only looks - no key is sent.
                if time.perf_counter() >= next_look:
                    next_look = time.perf_counter() + rig.lie.every_s
                    frame = rig.screen.grab()
                    if frame is not None and rig.lie.seen(frame):
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
            if not _init_map(rig, say):
                chirp(False)
                say(f"not started - {start_key.upper()} to try again")
                continue
            hunts += 1
            out = out_root / f"{datetime.now():%Y%m%d_%H%M%S}_{hunts}"
            rec = Recorder(out, every=int(frames) * 3 if frames is True else int(frames))
            say(f"hunt #{hunts} started -> {out} (map {rig.cfg.perception.map_id}, game picture at x {cols}, "
                f"{rig.screen.kind})")
            rec.log.write(f"map {rig.cfg.perception.map_id} {_map_name(rig.cfg.perception.map_id)}\n")  # livemap
            chirp(True)
            try:
                status = _hunt(rig, rec, time.perf_counter(),
                               lambda: f"stopped by {stop_key.upper()}" if hk.pressed(stop_key) else None, observe)
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


def watch(out: Path, seconds: float, every_s: float = 0.3) -> int:
    """Lie Detector watch with no hunt (session 9: one came up seconds after acc3's time limit, while the bot was
    gone and Claude analysed between runs - nothing looked at the screen). Grabs the game picture every ~0.3 s
    (mss, so a hunt's dxcam in another process is untouched), siren while the window is up, saves the frame.
    The game must be visible on the monitor (a window on top of it hides the panel)."""
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
    screen = Screen(hwnd)
    screen.close()
    screen.cam = None                                  # mss only
    lie = LieDetector.load(ASSETS)
    say(f"watching for the Lie Detector (game picture x {screen.cols}), {seconds:.0f}s")
    t_end, n = time.perf_counter() + seconds, 0
    try:
        while time.perf_counter() < t_end:
            frame = screen.grab()
            score, loc = lie.score(frame)
            if score >= lie.min_score:
                n += 1
                cv2.imwrite(str(out / f"lie_{datetime.now():%H%M%S}_{n}.png"), frame)
                say(f"LIE DETECTOR on screen (score {score:.2f} at {loc}) -> siren until it's gone")
                lie_alarm(lambda: lie.seen(screen.grab()))
                say("Lie Detector window gone")
            time.sleep(every_s)
    except KeyboardInterrupt:
        pass
    finally:
        screen.close()
        say(f"watch ended ({n} Lie Detector(s))")
    return 0
