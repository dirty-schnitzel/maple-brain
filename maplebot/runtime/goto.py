"""`python -m maplebot goto OUT [--to PLATFORM [X]] [--seconds S]` - brain-v2 movement, live (M1 step 4).

No fighting: our position (nav/selfstate on the tracker's camera, so --gpu is implied) -> Travel along NavMap routes
-> KeyDriver. `--to`: one trip, then stop. Without it: a TOUR of random goals (platforms reachable from where we
are, a random x on each) until --seconds, with a short varied pause between trips. Logged per move (kind, ok,
secs vs expected, why) + per trip; ticks.jsonl as usual, with timings.self (our state) and timings.travel.
Safety as in a hunt: Lie Detector -> keys up + siren, HP under --hp-stop -> stop, game not focused -> pause.
"""
import collections
import json
import random
import time
from pathlib import Path

from ..brain.moves import node_of
from ..brain.travel import Travel
from ..keyboard import FocusLost
from ..nav.selfstate import SelfTracker
from ..perception.perceiver import Perceiver
from .keys import KeyDriver
from .recorder import Recorder
from .runner import _init_map, _setup, alarm, lie_alarm


def goto(out: Path, cfg, seconds: float = 180.0, to=None, focus: bool = True, frames_every: int = 3,
         seed: int | None = None) -> int:
    rec = Recorder(out, every=frames_every)
    t0 = time.perf_counter()

    def say(msg):
        rec.say(f"{time.perf_counter() - t0:7.2f}s {msg}")

    cfg.perception.gpu = True                     # our exact position needs the tracker's camera
    rig = _setup(cfg, say, focus)
    if rig is None:
        rec.close()
        return 1
    status = "ok"
    try:
        deadline = time.time() + 180
        while not rig.kb.focused():
            if time.time() > deadline:
                say("timed out waiting for the game")
                return 1
            time.sleep(rig.hz.vary(0.2))
        time.sleep(rig.hz.vary(1.0))
        say(f"game picture at x {rig.screen.calibrate()} ({rig.screen.kind})")
        if not _init_map(rig, say):
            return 1
        status = _tour(rig, rec, t0, say, seconds, to, seed)
    finally:
        rig.screen.close()
        rec.close()
    return 0 if status == "ok" else 2


def _goal(nav, s, rng, to):
    if to is not None:
        p, x = to
        return p, (x if x is not None else (nav.platforms[p].left + nav.platforms[p].right) / 2)
    here = node_of(s)
    big = [p for p in nav.platforms.values() if p.right - p.left >= 40 and p.id != here]
    for _ in range(60):
        p = rng.choice(big)
        x = rng.uniform(p.left + 12, p.right - 12)
        if nav.route(here, s.y if nav.is_rope(here) else s.x, p.id, x) is not None:
            return p.id, x
    return None


def _tour(rig, rec, t0, say, seconds, to, seed) -> str:
    cfg, kb, screen, hz = rig.cfg, rig.kb, rig.screen, rig.hz
    nav = rig.locator.navmap
    rig.locator.origin = None
    perceiver = Perceiver(cfg, rig.self_tag, rig.sprites, lie_detector=rig.lie, locator=rig.locator)
    me = SelfTracker(nav, cfg.nav)
    driver = KeyDriver(kb.send, kb.focused, hz, cfg.humanize).start()
    keymap = {"jump": cfg.keys.jump}
    rng = random.Random(seed)
    tr, trip_t0, pause_until = None, None, 0.0
    trips = collections.Counter()
    kinds = collections.defaultdict(lambda: [0, 0, [], []])
    end = time.perf_counter() + seconds
    status, n_logged, potion_t = "ok", 0, 0.0
    try:
        while time.perf_counter() < end:
            try:
                tick0 = time.perf_counter()
                if not kb.focused():
                    raise FocusLost()
                frame = screen.grab()
                tg = time.perf_counter()
                t = tg - t0
                obs = perceiver.observe(frame, t, screen.cursor())
                tp = time.perf_counter()
                s = me.update(t, obs.me_map, obs.map_pos)
                if obs.lie_detector:
                    driver.release_all()
                    say("LIE DETECTOR on screen -> keys released, siren until it's gone")
                    lie_alarm(lambda: rig.lie.seen(screen.grab()))
                    status = "STOPPED: lie detector"
                    break
                if obs.hp_now is not None and obs.hp < cfg.safety.hp_potion_at and obs.hp_potions                         and t >= potion_t:                # bumped by mobs on the way: drink like in a hunt
                    driver.tap(cfg.keys.hp_potion, 0.08)
                    potion_t = t + hz.between(1.5, 3.0)
                    say(f"HP {obs.hp:.0%} -> HP potion ({cfg.keys.hp_potion})")
                if obs.hp_now is not None and obs.hp < cfg.safety.hp_stop and not obs.hp_potions:
                    driver.release_all()
                    status = f"STOPPED: HP {obs.hp:.0%}"
                    alarm()
                    break
                if tr is None and s is not None and t >= pause_until and s.state == "ground":
                    g = _goal(nav, s, rng, to)
                    if g is None:
                        say(f"no reachable goal from {node_of(s)}")
                        status = "no goal"
                        break
                    tr = Travel(nav, g[0], g[1], hz, keymap)
                    trip_t0 = t
                    n_logged = 0
                    say(f"trip: {node_of(s)} x {s.x:.0f} -> {g[0]} x {g[1]:.0f}")
                st = tr.step(t, s, driver) if tr is not None else None
                if tr is not None:
                    for kind, ok, secs, exp, why in tr.log[n_logged:]:
                        k = kinds[kind]
                        k[0] += 1
                        k[1] += ok
                        k[2].append(secs)
                        k[3].append(exp)
                        say(f"  {kind} {'ok' if ok else 'FAILED (' + str(why) + ')'} {secs:.2f}s "
                            f"(expected {exp:.2f}); now {node_of(s)} x {s.x:.0f} y {s.y:.0f}")
                    n_logged = len(tr.log)
                    for e in tr.events[getattr(tr, "_said", 0):]:
                        if e[1] != "failed":
                            say(f"  {e[1]} {e[2]}")
                    tr._said = len(tr.events)
                    if st != "run":
                        trips[st] += 1
                        say(f"trip {st}{' (' + tr.reason + ')' if tr.reason else ''} in {t - trip_t0:.1f}s, "
                            f"{tr.replans} re-plans")
                        tr = None
                        driver.hold(set())
                        if to is not None:
                            break
                        pause_until = t + hz.between(0.2, 1.4)
                timings = {"grab_ms": round(1000 * (tg - tick0)), "perceive_ms": round(1000 * (tp - tg)),
                           "total_ms": round(1000 * (time.perf_counter() - tick0)),
                           "self": s.as_dict() if s is not None else None, "held": sorted(driver.want),
                           "travel": ({"dst": tr.dst, "move": tr.move.kind if tr.move else None,
                                       "phase": tr.move.phase if tr.move else None} if tr is not None else None)}
                if getattr(perceiver, "parts", None):
                    timings["parts"] = perceiver.parts
                rec.tick(frame, obs, [], "TRAVEL" if tr is not None else "IDLE", timings)
            except FocusLost:
                driver.release_all()
                say("PAUSED: game not focused; keys released")
                while not kb.focused() and time.perf_counter() < end:
                    time.sleep(hz.vary(0.2))
                say("resumed")
                tr = None
                time.sleep(hz.vary(1.0))
    except Exception as e:                         # noqa: BLE001 - report it; keys are released below
        import traceback
        status = f"aborted: {type(e).__name__}: {e}"
        rec.log.write(traceback.format_exc())
    finally:
        driver.release_all()
        driver.stop()
        rig.kb.release_all()
    say(status)
    say(f"trips {dict(trips)}")
    for kind, (n, ok, secs, exp) in sorted(kinds.items()):
        secs, exp = sorted(secs), sorted(exp)
        say(f"  {kind:8s} {ok}/{n} ok first try, median {secs[len(secs) // 2]:.2f}s (expected {exp[len(exp) // 2]:.2f})")
    say("stats " + json.dumps({"trips": dict(trips), "moves": {k: v[:2] for k, v in kinds.items()}}))
    return status
