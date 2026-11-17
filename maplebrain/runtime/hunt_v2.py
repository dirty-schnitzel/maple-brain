"""The live loop of a hunt (`run` / `serve`): capture -> perceive (the scene camera, the fit's mobs + the tracker,
our exact position) -> BrainV2 -> KeyDriver. Same safety as every hunt: Lie Detector -> keys up + siren + stop, HP
stop, game not focused / game window moved or not 1366x768 (runtime/window.py) -> keys up, pause. Starts only where
the scene camera can work (runner.refuse: a clean map, the native window). The scene camera not found on a tick
(lost mid-hunt, or not found yet at the start) -> every key released, no brain step, until it is found again (logged
both ways; HANDOFF TODO: handle it properly as cases come up live). ticks.jsonl as usual, with timings.self (our
state), timings.v2 (mode, target, travel) and timings.held.
"""
import json
import time
import traceback

from ..brain.brain_v2 import BrainV2
from ..keyboard import FocusLost, foreground_title
from . import window
from ..nav.selfstate import SelfTracker
from ..perception.perceiver import Perceiver
from .exp_meter import ExpMeter
from .keys import KeyDriver


def hunt_v2(rig, rec, t0: float, until, area=None) -> str:
    """`area`: platform mode's marked platform ids (serve, F9): the brain hunts only on them (goal HuntArea)."""
    from .runner import alarm, lie_alarm, refuse
    cfg, kb, screen, hz = rig.cfg, rig.kb, rig.screen, rig.hz

    def say(msg):
        rec.say(f"{time.perf_counter() - t0:7.2f}s {msg}")

    why = refuse(rig)
    if why is not None:
        say(f"NOT STARTED: {why}")
        return "not started: " + why.split(":")[0]
    nav = rig.locator.navmap
    rig.locator.origin = None
    perceiver = Perceiver(cfg, rig.self_tag, rig.kit, lie_detector=rig.lie, locator=rig.locator)
    me = SelfTracker(nav, cfg.nav)
    brain = BrainV2(cfg, nav, hz, log=say, area=area)
    if area:
        say("platform mode: hunting only on the marked platforms " + ", ".join(
            describe_platform(nav, p) for p in sorted(area) if p in nav.platforms))
    exp = ExpMeter()
    first_mob = next(iter(sorted(rig.kit.mobs)), None)
    s0, m0 = brain.reach.vs(first_mob)
    say(f"brain v2 (combat): weapon {cfg.combat.weapon} (attack speed {brain.reach.attack_speed}, swing "
        f"{brain.reach.swing_s:.2f} s), sure reach {s0.lo:.0f}..{s0.hi:.0f} px in front "
        f"(maybe {m0.lo:.0f}..{m0.hi:.0f}), attack {cfg.keys.attack} / plain {cfg.keys.basic_attack}")
    driver = KeyDriver(kb.send, kb.focused, hz, cfg.humanize).start()
    status, start, frames_n = "ok", time.perf_counter(), 0
    speed = []                                   # (tick ms, perceiver parts) per tick: the speed line at the end
    lost_t, lost_n, n_lost = 0.0, 0, 0           # the scene camera: lost since (s), ticks so far, pauses
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
                t = tg - t0
                obs = perceiver.observe(frame, t, screen.cursor())
                tp = time.perf_counter()
                if line := exp.update(t, obs.exp_points):
                    say(line)
                s = me.update(t, obs.me_map, obs.map_pos, driver.want)
                if obs.lie_detector:
                    driver.release_all()
                    say("LIE DETECTOR on screen -> keys released, siren until its window is gone")
                    lie_alarm(lambda: rig.lie.seen(screen.grab()))
                    say("lie detector window gone")
                    status = "STOPPED: lie detector"
                    break
                stop = None
                if obs.scene_cam is None:            # no camera, no mobs: no presses until it is found again
                    if lost_n == 0:
                        driver.release_all()
                        lost_t, n_lost = t, n_lost + 1
                        say("PAUSED: scene camera " + ("not found yet" if frames_n == 1 else "lost")
                            + " -> keys released, no presses until it is found")
                    lost_n += 1
                else:
                    if lost_n:
                        say(f"scene camera found again after {t - lost_t:.2f} s ({lost_n} ticks) -> resumed")
                        brain.reset(driver)
                        lost_n = 0
                    stop = brain.step(t, obs, s, driver)
                tb = time.perf_counter()
                timings = {"grab_ms": round(1000 * (tg - tick0)), "perceive_ms": round(1000 * (tp - tg)),
                           "brain_ms": round(1000 * (tb - tp), 1), "total_ms": round(1000 * (tb - tick0)),
                           "self": s.as_dict() if s is not None else None, "held": sorted(driver.want),
                           "v2": brain.snapshot(), "paused": "scene camera" if lost_n else None}
                if getattr(perceiver, "parts", None):
                    timings["parts"] = perceiver.parts
                speed.append((1000 * (tb - tick0), dict(getattr(perceiver, "parts", None) or {})))
                rec.tick(frame, obs, [], brain.mode, timings, facts=getattr(perceiver, "facts", None))
                if stop:
                    driver.release_all()
                    status = f"STOPPED: {stop}"
                    alarm()
                    break
            except FocusLost as e:
                driver.release_all()
                say(window.pause_line(e, foreground_title))
                paused = time.perf_counter()
                back = window.wait_back(screen, kb.focused, hz, say, lambda: until() is None, e)
                exp.pause(time.perf_counter() - paused)
                if back:
                    say("resumed")
                    brain.reset(driver)
                    time.sleep(hz.vary(1.0))
        else:
            if reason != "time":
                status = reason
    except Exception as e:                       # noqa: BLE001 - report anything, keys are released below
        status = f"aborted: {type(e).__name__}: {e}"
        rec.log.write(traceback.format_exc())
    finally:
        driver.release_all()
        driver.stop()
        rig.kb.release_all()
        say(f"keys: {driver.sent} key events sent")
    elapsed = time.perf_counter() - start
    st = brain.stats
    say(status)
    say(exp.summary())
    say(f"kills (last hit) {st['kills']} = {60 * st['kills'] / max(elapsed, 1):.1f}/min; swings {st['swings']} "
        f"({st['swings'] / max(st['kills'], 1):.1f} per kill); targets {st['targets']}, trips {st['trips']}, "
        f"turns {st['turns']}")
    say(f"scene camera: paused {n_lost} time(s)" + (f", still lost at the end ({lost_n} ticks)" if lost_n else ""))
    say(brain.reach.check(first_mob))
    say("reach learned (dx band: hits/n) " + json.dumps({k: list(v) for k, v in brain.reach.learned().items()}))
    say("stats " + json.dumps(dict(st, frames=frames_n, fps=round(frames_n / max(elapsed, 1e-6), 1))))
    say(speed_line(speed))
    return status


def describe_platform(nav, pid) -> str:
    """'273 (y 198, x -305..3185)' - how logs name a platform for the user."""
    p = nav.platforms[pid]
    return f"{pid} (y {p.segs[0].y1:.0f}, x {p.left:.0f}..{p.right:.0f})"


def speed_line(speed) -> str:
    """'speed: tick p50 / p90 ms, parts p50' over the hunt's ticks - compare with tools/perf/bench.py (the replay
    regression test's numbers; live adds the capture and the game's own GPU load)."""
    if not speed:
        return "speed: no ticks"
    ticks = sorted(t for t, _ in speed)
    names = {k for _, p in speed for k in p}
    med = {k: sorted(p.get(k, 0.0) for _, p in speed)[len(speed) // 2] for k in names}
    parts = ", ".join(f"{k} {v:.1f}" for k, v in sorted(med.items(), key=lambda kv: -kv[1]) if v >= 0.05)
    p50, p90 = ticks[len(ticks) // 2], ticks[int(0.9 * (len(ticks) - 1))]
    return f"speed: tick p50 {p50:.0f} ms ({1000 / p50:.1f} fps), p90 {p90:.0f} ms; perceive parts p50 [{parts}]"
