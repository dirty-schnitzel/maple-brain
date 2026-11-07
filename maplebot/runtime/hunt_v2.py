"""The live loop for brain-v2 (`run` / `serve` with `--brain v2`, implies --gpu): capture -> perceive (tracks + our
exact position) -> BrainV2 -> KeyDriver. Same safety as every hunt: Lie Detector -> keys up + siren + stop, HP stop,
game not focused -> keys up, pause. ticks.jsonl as usual, with timings.self (our state), timings.v2 (mode, target,
travel) and timings.held.
"""
import json
import time
import traceback

from ..brain.brain_v2 import BrainV2
from ..keyboard import FocusLost, foreground_title
from ..nav.selfstate import SelfTracker
from ..perception.perceiver import Perceiver
from .exp_meter import ExpMeter
from .keys import KeyDriver


def hunt_v2(rig, rec, t0: float, until) -> str:
    from .runner import alarm, lie_alarm
    cfg, kb, screen, hz = rig.cfg, rig.kb, rig.screen, rig.hz

    def say(msg):
        rec.say(f"{time.perf_counter() - t0:7.2f}s {msg}")

    if rig.locator is None or rig.locator.navmap is None:
        say("brain v2 needs the map (navmap): not started")
        return "no map"
    if not hasattr(rig.sprites, "track_ctx"):
        say("brain v2 needs the tracker (--gpu): not started")
        return "no tracker"
    nav = rig.locator.navmap
    rig.locator.origin = None
    perceiver = Perceiver(cfg, rig.self_tag, rig.sprites, lie_detector=rig.lie, locator=rig.locator)
    me = SelfTracker(nav, cfg.nav)
    brain = BrainV2(cfg, nav, hz, log=say)
    exp = ExpMeter()
    s0, m0 = brain.reach.vs(next(iter(m.mob_id for m in rig.sprites.mobs), None))
    say(f"brain v2 (combat): weapon {cfg.combat.weapon}, sure reach {s0.lo:.0f}..{s0.hi:.0f} px in front "
        f"(maybe {m0.lo:.0f}..{m0.hi:.0f}), attack {cfg.keys.attack} / plain {cfg.keys.basic_attack}")
    driver = KeyDriver(kb.send, kb.focused, hz, cfg.humanize).start()
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
                stop = brain.step(t, obs, s, driver)
                tb = time.perf_counter()
                timings = {"grab_ms": round(1000 * (tg - tick0)), "perceive_ms": round(1000 * (tp - tg)),
                           "brain_ms": round(1000 * (tb - tp), 1), "total_ms": round(1000 * (tb - tick0)),
                           "self": s.as_dict() if s is not None else None, "held": sorted(driver.want),
                           "v2": brain.snapshot()}
                if getattr(perceiver, "parts", None):
                    timings["parts"] = perceiver.parts
                if hasattr(rig.sprites, "all_hits"):
                    timings["gpu_ms"] = round(rig.sprites.last_ms, 1)
                rec.tick(frame, obs, [], brain.mode, timings)
                if stop:
                    driver.release_all()
                    status = f"STOPPED: {stop}"
                    alarm()
                    break
            except FocusLost:
                driver.release_all()
                say(f"PAUSED: game not focused (foreground: '{foreground_title()}'); keys released")
                paused = time.perf_counter()
                while not kb.focused() and until() is None:
                    time.sleep(hz.vary(0.2))
                exp.pause(time.perf_counter() - paused)
                if kb.focused():
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
    say(brain.reach.check(next(iter(m.mob_id for m in rig.sprites.mobs), None)))
    say("reach learned (dx band: hits/n) " + json.dumps({k: list(v) for k, v in brain.reach.learned().items()}))
    say("stats " + json.dumps(dict(st, frames=frames_n, fps=round(frames_n / max(elapsed, 1e-6), 1))))
    return status
