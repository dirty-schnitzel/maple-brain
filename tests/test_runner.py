import pytest
"""The live loop end-to-end with a fake screen + keyboard fed by recorded frames (no game, no real keys). Hunts run
the real hunt loop (runtime/hunt_v2.py, BrainV2 on Ant Tunnel IV's NavMap) with a stand-in Perceiver (`FakeSight`:
the scene camera found or not per tick, the Lie Detector seen by the real detector on the frame); observe runs the
real Perceiver without a map."""
import json
from pathlib import Path
from types import SimpleNamespace

import cv2

import maplebrain.runtime.hunt_v2 as hunt_v2
import maplebrain.runtime.runner as runner
from maplebrain.config import Config
from maplebrain.keyboard import FocusLost
from maplebrain.nav.navmap import NavMap
from maplebrain.perception.perceiver import Observation

START, STOP = Config().keys.start, Config().keys.stop

FX = Path(__file__).parent / "fixtures"
ANT4 = 10005063
NAV = NavMap.for_map(ANT4, Path(__file__).resolve().parents[1] / "assets" / "mcw", Config().nav)
_P = max(NAV.platforms.values(), key=lambda p: p.right - p.left)            # we stand on the longest platform
ME_MAP = ((_P.left + _P.right) / 2, _P.y_at((_P.left + _P.right) / 2))


class FakeKeyboard:
    def __init__(self, hwnd, focus_script=None):
        self.events, self.held, self.calls = [], set(), 0
        FakeKeyboard.last = self
        self.focus_script = focus_script or (lambda n: True)

    def focused(self):
        self.calls += 1
        return self.focus_script(self.calls)

    def down(self, k):
        if not self.focused():
            self.release_all()
            raise FocusLost()
        self.events.append(("down", k))
        self.held.add(k)

    def up(self, k):
        self.events.append(("up", k))
        self.held.discard(k)

    def send(self, k, up):
        self.events.append(("up" if up else "down", k))
        (self.held.discard if up else self.held.add)(k)

    def tap(self, k, down_s=0.08, gap_s=0.03):
        self.down(k)
        self.up(k)

    def release_all(self):
        self.events.append(("release_all", None))
        self.held.clear()


class FakeScreen:
    kind, note = "fake", ""

    def __init__(self, hwnd):
        self.frames = [cv2.imread(str(FX / "look_snails" / f"f{i:03d}.png")) for i in (87, 88, 89, 90)]
        self.i = 0

    def grab(self):
        self.i += 1
        return self.frames[self.i % len(self.frames)]

    def cursor(self):
        return None

    def calibrate(self):
        self.calibrated = getattr(self, "calibrated", 0) + 1
        return (0, 1366)

    def close(self):
        pass


class FakeSight:
    """Perceiver stand-in for hunts: us on Ant Tunnel IV's longest platform, no mobs, the scene camera found except on
    the ticks `lost(n)` names; the Lie Detector by the real detector (rig.lie) on each frame."""
    lost = staticmethod(lambda n: False)

    def __init__(self, cfg, self_tag, kit, lie_detector=None, locator=None):
        self.lie, self.n, self.parts, self.facts = lie_detector, 0, {}, None

    def observe(self, frame, t, cursor=None):
        self.n += 1
        found = not FakeSight.lost(self.n)
        return Observation(t=t, me=(683.0, 400.0), lie_detector=bool(self.lie.seen(frame)), map_pos=ME_MAP,
                           me_map=ME_MAP if found else None, scene_cam=(0.0, 0.0) if found else None,
                           cam=(0.0, 0.0) if found else None, cam_src="exact" if found else None)


def _clean_map(rig, say=None, frames=3, save_to=None):
    """runner._init_map stand-in: Ant Tunnel IV with a clean scene (the MapKit's parts the loop reads)."""
    rig.kit = SimpleNamespace(map_id=ANT4, clean=True, why="", mobs={})
    rig.locator = SimpleNamespace(navmap=NAV, origin=None)
    rig.cfg.perception.map_id = ANT4
    return True


@pytest.fixture
def hunting(monkeypatch):
    monkeypatch.setattr(runner, "_init_map", _clean_map)
    monkeypatch.setattr(hunt_v2, "Perceiver", FakeSight)
    monkeypatch.setattr(FakeSight, "lost", staticmethod(lambda n: False))
    return FakeSight


def _run(tmp_path, monkeypatch, focus_script=None, seconds=1.5, screen=None):
    holder = {}

    def make_kb(hwnd, *_):
        holder["kb"] = FakeKeyboard(hwnd, focus_script)
        return holder["kb"]

    monkeypatch.setattr(runner, "find_window", lambda: 1)
    monkeypatch.setattr(runner, "Keyboard", make_kb)
    monkeypatch.setattr(runner, "Screen", screen or FakeScreen)
    monkeypatch.setattr(runner, "alarm", lambda: None)
    monkeypatch.setattr(runner, "foreground_title", lambda: "Some Other Window ✳")
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    monkeypatch.setattr(hunt_v2.time, "sleep", lambda s: None)
    monkeypatch.setattr(runner, "ASSETS", FX)
    monkeypatch.setattr(runner, "bring_to_front", lambda hwnd: True)
    code = runner.run(tmp_path / "run", seconds, Config())
    return code, holder["kb"], tmp_path / "run"


def _ticks(out):
    return [json.loads(line) for line in (out / "ticks.jsonl").read_text(encoding="utf-8").splitlines()]


def test_loop_runs_records_and_releases_everything(tmp_path, monkeypatch, hunting):
    code, kb, out = _run(tmp_path, monkeypatch)
    assert code == 0
    assert kb.events[-1] == ("release_all", None) and not kb.held
    ticks = _ticks(out)
    assert len(ticks) > 5 and all("obs" in t and "v2" in t["timings"] for t in ticks)
    assert list((out / "frames").glob("*.jpg"))


def test_focus_loss_mid_run_releases_keys_and_resumes(tmp_path, monkeypatch, hunting):
    code, kb, out = _run(tmp_path, monkeypatch, focus_script=lambda n: not (40 <= n < 46))
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert "PAUSED" in log and "resumed" in log
    assert ("release_all", None) in kb.events and not kb.held


def test_a_lost_scene_camera_pauses_the_hunt_until_it_is_found(tmp_path, monkeypatch, hunting):
    """The user's call 2026-11-17: the scene camera lost mid-hunt -> keys released, no presses until it is found,
    logged both ways (no camera = no mobs and no exact position)."""
    hunting.lost = staticmethod(lambda n: 20 <= n < 30)
    code, kb, out = _run(tmp_path, monkeypatch, seconds=3.0)
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert code == 0 and "PAUSED: scene camera lost" in log and "scene camera found again after" in log
    assert "scene camera: paused 1 time(s)" in log
    ticks = _ticks(out)
    paused = [t for t in ticks if t["timings"]["paused"]]
    assert len(paused) == 10 and all(t["timings"]["held"] == [] for t in paused)
    assert any(t["timings"]["held"] for t in ticks[:19])                # it was walking before (released at the loss)


def test_a_hunt_waits_for_the_scene_camera_at_the_start(tmp_path, monkeypatch, hunting):
    hunting.lost = staticmethod(lambda n: n <= 3)
    code, kb, out = _run(tmp_path, monkeypatch)
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert "PAUSED: scene camera not found yet" in log and "scene camera found again after" in log


def test_no_hunt_without_a_clean_scene_or_a_native_window(tmp_path, monkeypatch):
    """The user's call 2026-11-17: maps without a clean scene (since PLAN-moving-scenery.md step 5: backgrounds the
    model does not follow, e.g. the subway's deeper lines) or a non-native window -> the hunt refuses to start, with
    a clear message."""
    def unclean(rig, say=None, frames=3, save_to=None):
        _clean_map(rig)
        rig.kit.clean, rig.kit.why = False, "moving / animated backgrounds (not covered by the scene model yet)"
        return True
    monkeypatch.setattr(runner, "_init_map", unclean)
    monkeypatch.setattr(runner, "_map_name", lambda map_id: "Perion / Street Corner")
    code, kb, out = _run(tmp_path, monkeypatch)
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert code == 2 and "NOT STARTED: map 10005063 Perion / Street Corner has no clean scene (moving" in log
    assert not (out / "ticks.jsonl").read_text(encoding="utf-8")
    rig = SimpleNamespace(kit=SimpleNamespace(map_id=ANT4, clean=True, why=""), locator=SimpleNamespace(navmap=NAV),
                          screen=SimpleNamespace(cols=(0, 1920), box={"height": 1080}))
    assert "not the native 1366x768 window" in runner.refuse(rig)
    rig.screen = SimpleNamespace(cols=(0, 1366), box={"height": 768})
    assert runner.refuse(rig) is None


class LieScreen(FakeScreen):
    """Recorded snails, then the Lie Detector mini-game from grab 30 on, until the user has answered it."""
    answered = False

    def __init__(self, hwnd):
        super().__init__(hwnd)
        self.lie = cv2.imread(str(FX / "lie_detector_game.jpg"))
        self.none = cv2.imread(str(FX / "lie_detector_none.jpg"))
        LieScreen.answered = False

    def grab(self):
        self.i += 1
        if LieScreen.answered:
            return self.none
        return self.lie if self.i >= 30 else self.frames[self.i % len(self.frames)]


def test_lie_detector_stops_the_run_releases_keys_and_sounds_the_siren(tmp_path, monkeypatch, hunting):
    sirens = []

    def fake_siren(still_there, max_s=120.0):
        while still_there():                                             # beeps while it's on screen
            sirens.append(1)
            if len(sirens) == 3:
                LieScreen.answered = True                                # the user answers it
    monkeypatch.setattr(runner, "lie_alarm", fake_siren)
    code, kb, out = _run(tmp_path, monkeypatch, seconds=30, screen=LieScreen)
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert code == 2 and "LIE DETECTOR on screen -> keys released" in log and "lie detector window gone" in log
    assert "STOPPED: lie detector" in log
    assert len(sirens) == 3                                              # sounded until it was gone
    assert kb.events[-1] == ("release_all", None) and not kb.held


# ---------------------------------------------------------------- serve: F7 starts a hunt, F8 stops it
class ScriptedKeys:
    """Fake key state: `script(name, n)` -> is the key down at the n-th poll of that key."""

    def __init__(self, script):
        self.script, self.n = script, {}

    def __call__(self, vk):
        name = {v: k for k, v in runner.VK.items()}[vk]
        self.n[name] = self.n.get(name, 0) + 1
        return self.script(name, self.n[name])


def _serve(tmp_path, monkeypatch, script, focus_script=None, max_hunts=2, observe=False, screen=None,
           keys=(START, STOP)):
    holder = {}

    def make_kb(hwnd, *_):
        holder["kb"] = FakeKeyboard(hwnd, focus_script)
        return holder["kb"]

    monkeypatch.setattr(runner, "find_window", lambda: 1)
    monkeypatch.setattr(runner, "Keyboard", make_kb)
    monkeypatch.setattr(runner, "Screen", screen or FakeScreen)
    monkeypatch.setattr(runner, "alarm", lambda: None)
    monkeypatch.setattr(runner, "chirp", lambda up: None)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    monkeypatch.setattr(runner, "ASSETS", FX)
    hk = runner.Hotkeys(list(keys), key_down=ScriptedKeys(script))
    code = runner.serve(tmp_path / "manual", Config(), hotkeys=hk, max_hunts=max_hunts, observe=observe)
    return code, holder["kb"], tmp_path / "manual"


# ---------------------------------------------------------------- serve: modes (F10) and platform marks (F9)
MARK, MODE = Config().keys.mark, Config().keys.mode


def _quit_at(n_quit, presses):
    """A key script: `presses` = {key: [poll numbers it is down at]}; the start key's poll n_quit = Ctrl+C."""
    def script(name, n):
        if name == START and n >= n_quit:
            raise KeyboardInterrupt
        return n in presses.get(name, ())
    return script


def test_serve_platform_mode_without_marks_starts_no_hunt(tmp_path, monkeypatch, capsys):
    script = _quit_at(40, {MODE: [3], START: [10]})
    code, kb, out = _serve(tmp_path, monkeypatch, script, keys=(START, STOP, MARK, MODE))
    said = capsys.readouterr().out
    assert code == 0 and "mode: platform" in said and "no platform marked on this map" in said
    assert not out.exists() or not any(p.is_dir() for p in out.iterdir())          # no hunt folder


def test_serve_marks_toggle_only_in_platform_mode_and_bind_the_hunt(tmp_path, monkeypatch, capsys, hunting):
    monkeypatch.setattr(runner, "_platform_here",
                        lambda rig, say, frame=None: (rig.cfg.perception.map_id, 273, "273 (y 198)"))
    monkeypatch.setattr(runner, "_map_name", lambda map_id: "Line 1")
    # F9 in auto mode (refused), F10 -> platform, F9 marks, F9 unmarks, F9 marks again, F7: a hunt on 273, F8
    script = _quit_at(60, {MARK: [3, 12, 16, 20], MODE: [8], START: [30], STOP: [10]})
    code, kb, out = _serve(tmp_path, monkeypatch, script, keys=(START, STOP, MARK, MODE))
    said = capsys.readouterr().out
    assert code == 0
    assert "platform marks are for platform mode" in said
    assert said.count("s marked 273") == 2 and said.count("s unmarked 273") == 1
    (hunt,) = [p for p in out.iterdir() if p.is_dir()]
    assert "marked platforms 273" in (hunt / "log.txt").read_text(encoding="utf-8")


def test_mark_reads_the_platform_from_the_frame_at_the_press_not_after_the_map_load(monkeypatch, capsys):
    """Live 2026-11-15 (runs/v2/20261115_013124_1): the first F9 on Ant Tunnel IV loaded the map for 20.6 s; the
    platform was read after it (the user had walked on, so the wrong one got marked) and the 2nd F9 meanwhile was
    never polled. The press's frame decides; a slow mark says an F9 meanwhile was missed."""
    from maplebrain.runtime.marks import Marks
    grabs = iter(["at press", "after load"])
    rig = SimpleNamespace(cfg=Config(), kb=SimpleNamespace(focused=lambda: True),
                          screen=SimpleNamespace(calibrate=lambda: None, grab=lambda: next(grabs)))
    clock = iter([0.0, 20.6])
    monkeypatch.setattr(runner.time, "perf_counter", lambda: next(clock))
    monkeypatch.setattr(runner, "_init_map", lambda rig, say, frames=3, save_to=None: rig.screen.grab() and True)
    seen = []
    monkeypatch.setattr(runner, "_platform_here", lambda rig, say, frame=None: seen.append(frame) or (1, 273, "273"))
    monkeypatch.setattr(runner, "_map_name", lambda map_id: "Line 1")
    monkeypatch.setattr(runner, "chirp", lambda up: None)
    marks = Marks()
    marks.next_mode()
    runner._mark_here(rig, marks, print, Path("."))
    assert seen == ["at press"] and marks.area(1) == {273}
    assert "was NOT seen - press it again" in capsys.readouterr().out


def test_marks_are_kept_per_map_and_modes_cycle():
    from maplebrain.runtime.marks import Marks
    m = Marks()
    assert m.mode == "auto" and m.next_mode() == "platform" and m.next_mode() == "auto"
    assert m.toggle(1, 273) and m.toggle(1, 79) and m.toggle(2, 5)
    assert not m.toggle(1, 273)
    assert m.area(1) == {79} and m.area(2) == {5} and m.area(3) == frozenset()


def test_serve_f7_starts_a_hunt_f8_stops_it_and_f7_starts_another(tmp_path, monkeypatch, hunting):
    # F7 down at polls 3-4 and 30-31; F8 down at its polls 20-21 and 45-46 (polled once per tick while hunting)
    script = lambda name, n: (3 <= n <= 4 or 30 <= n <= 31) if name == START else (20 <= n <= 21 or 45 <= n <= 46)  # noqa: E731
    code, kb, out = _serve(tmp_path, monkeypatch, script)
    assert code == 0
    hunts = sorted(out.iterdir())
    assert len(hunts) == 2
    for h in hunts:
        log = (h / "log.txt").read_text(encoding="utf-8")
        assert f"stopped by {STOP.upper()}" in log
        ticks = (h / "ticks.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(ticks) > 5
        assert not (h / "frames").exists()                                   # manual hunts: no frames by default
    assert kb.events[-1] == ("release_all", None) and not kb.held


def test_serve_observe_records_but_never_touches_a_key(tmp_path, monkeypatch):
    """Jump measurements (session 11): the player plays while serve records. Not even a release - the keyboard's
    release_all sends key-ups for arrows/shift/attack and would cut the player's own jump. No map here: it records
    without mobs and says so."""
    script = lambda name, n: (name == START and 3 <= n <= 4) or (name == STOP and 20 <= n <= 21)  # noqa: E731
    code, kb, out = _serve(tmp_path, monkeypatch, script, max_hunts=1, observe=True)
    assert code == 0
    (hunt,) = list(out.iterdir())
    ticks = (hunt / "ticks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ticks) > 5 and all('"actions": []' in t and '"mode": "OBSERVE"' in t for t in ticks)
    assert "no camera, no mobs" in (hunt / "log.txt").read_text(encoding="utf-8")
    assert kb.events == []


def test_serve_holding_f7_starts_only_one_hunt(tmp_path, monkeypatch, hunting):
    script = lambda name, n: (name == START and n >= 2) or (name == STOP and n == 15)  # noqa: E731
    _, _, out = _serve(tmp_path, monkeypatch, script, max_hunts=1)
    assert len(list(out.iterdir())) == 1


def test_serve_ignores_f7_when_the_game_is_not_focused(tmp_path, monkeypatch, hunting):
    # unfocused for the first presses: F7 at polls 3-4 is ignored; the one at 40-41 (focused by then) starts
    script = lambda name, n: (3 <= n <= 4 or 40 <= n <= 41) if name == START else n == 20  # noqa: E731
    focus = lambda n: n > 1                     # focused() is asked on each F7 press: the 1st is unfocused  # noqa: E731
    _, kb, out = _serve(tmp_path, monkeypatch, script, focus_script=focus, max_hunts=1)
    hunts = list(out.iterdir())
    assert len(hunts) == 1


def test_serve_measures_the_game_picture_at_every_start(tmp_path, monkeypatch, hunting):
    """The console is in front when serve starts: measuring then squeezed the whole desktop into the frame
    (2026-11-01: every hunt read HP 56 % / EXP 37 % from the wrong pixels and never saw the name tag)."""
    made = []

    class CountingScreen(FakeScreen):
        def __init__(self, hwnd):
            super().__init__(hwnd)
            made.append(self)
    script = lambda name, n: (3 <= n <= 4 or 30 <= n <= 31) if name == START else (20 <= n <= 21 or 45 <= n <= 46)  # noqa: E731
    _serve(tmp_path, monkeypatch, script, screen=CountingScreen)
    assert len(made) == 1 and made[0].calibrated == 2


def test_cli_parses():
    """pkg_sight2 never started: a flag edit broke __main__.py and no test imported it."""
    import maplebrain.__main__ as cli
    for cmd in ("run", "serve", "goto"):
        with pytest.raises(SystemExit) as e:
            cli.main([cmd, "--help"])
        assert e.value.code == 0
    with pytest.raises(SystemExit) as e:                                  # the old perception's switches are gone
        cli.main(["serve", "--brain", "v2"])
    assert e.value.code == 2


# ---------------------------------------------------------------- F7 init: which map are we on?
class StubIdent:
    """MapIdentifier stand-in: answers one map id (None = can't tell) per identify() call."""
    canvases = {1: None}

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def identify(self, frames):
        from maplebrain.nav.identify import MapMatch
        self.calls.append(len(frames))
        a = self.answers.pop(0)
        if a is None:
            return MapMatch(None, 0.2, 10004053, 0.18, why="two maps look alike", fits=[(0.2, 10004050)])
        return MapMatch(a, 0.9, 10004053, 0.6, (6, 72), fits=[(0.9, a)])


def _serve_ident(tmp_path, monkeypatch, capsys, answers, script, max_hunts):
    import maplebrain.nav.identify as identify
    stub, loaded = StubIdent(answers), []
    monkeypatch.setattr(identify.MapIdentifier, "load", classmethod(lambda cls, root, **kw: stub))
    monkeypatch.setattr(runner, "_load_map", lambda rig, mid, say: loaded.append(mid) or True)
    code, kb, out = _serve(tmp_path, monkeypatch, script, max_hunts=max_hunts)
    return code, out, stub, loaded, capsys.readouterr().out


def test_f7_recognises_the_map_and_loads_it_before_hunting(tmp_path, monkeypatch, capsys):
    script = lambda name, n: (name == START and 3 <= n <= 4) or (name == STOP and 20 <= n <= 21)  # noqa: E731
    code, out, stub, loaded, console = _serve_ident(tmp_path, monkeypatch, capsys, [10004050], script, 1)
    assert code == 0 and loaded == [10004050]
    assert stub.calls == [3]                                     # a few frames, averaged
    assert "map is recognised from the minimap" in console and "map recognised: 10004050" in console
    assert len(list(out.iterdir())) == 1


def test_f7_does_not_hunt_when_the_map_cant_be_told(tmp_path, monkeypatch, capsys):
    """Wrong sprites / footholds are worse than none: no hunt, say why; the next F7 tries again."""
    script = lambda name, n: (3 <= n <= 4 or 30 <= n <= 31) if name == START else (45 <= n <= 46)  # noqa: E731
    code, out, stub, loaded, console = _serve_ident(tmp_path, monkeypatch, capsys, [None, 42], script, 1)
    assert "frame saved:" in console
    assert "can't tell which map this is: two maps look alike" in console and "not started" in console
    assert loaded == [42] and len([p for p in out.iterdir() if p.is_dir()]) == 1     # only the second F7 hunted
    assert len(list(out.glob("unknown_map_*.png"))) == 1         # the frame of the F7 that failed, to look at later


def test_each_f7_checks_the_map_again(tmp_path, monkeypatch, capsys):
    """The player may walk to another map between hunts."""
    script = lambda name, n: (3 <= n <= 4 or 30 <= n <= 31) if name == START else (20 <= n <= 21 or 45 <= n <= 46)  # noqa: E731
    _, out, stub, loaded, _ = _serve_ident(tmp_path, monkeypatch, capsys, [42, 50], script, 2)
    assert loaded == [42, 50] and len(list(out.iterdir())) == 2


def test_map_given_with_option_skips_recognition(tmp_path, monkeypatch, capsys):
    import maplebrain.nav.identify as identify
    monkeypatch.setattr(identify.MapIdentifier, "load", classmethod(lambda cls, root, **kw: pytest.fail("no ident")))
    loaded = []
    monkeypatch.setattr(runner, "_load_map", lambda rig, mid, say: loaded.append(mid) or True)
    holder = {}
    monkeypatch.setattr(runner, "find_window", lambda: 1)
    monkeypatch.setattr(runner, "Keyboard", lambda hwnd, *_: holder.setdefault("kb", FakeKeyboard(hwnd)))
    monkeypatch.setattr(runner, "Screen", FakeScreen)
    monkeypatch.setattr(runner, "chirp", lambda up: None)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    monkeypatch.setattr(runner, "ASSETS", FX)
    cfg = Config()
    cfg.perception.map_id = 42
    script = lambda name, n: (name == START and 3 <= n <= 4) or (name == STOP and 20 <= n <= 21)  # noqa: E731
    hk = runner.Hotkeys([START, STOP], key_down=ScriptedKeys(script))
    runner.serve(tmp_path / "manual", cfg, hotkeys=hk, max_hunts=1)
    assert loaded == [42] and "map fixed by --map: 42" in capsys.readouterr().out


class IdleLieScreen(FakeScreen):
    """The Lie Detector is up from the start - before any F7 (it came between hunts)."""
    answered = False

    def __init__(self, hwnd):
        super().__init__(hwnd)
        self.lie = cv2.imread(str(FX / "lie_detector_game.jpg"))
        self.none = cv2.imread(str(FX / "lie_detector_none.jpg"))

    def grab(self):
        return self.none if IdleLieScreen.answered else self.lie


def test_serve_watches_for_the_lie_detector_between_hunts(tmp_path, monkeypatch):
    sirens = []

    def fake_siren(still_there, max_s=120.0):
        while still_there():
            sirens.append(1)
            if len(sirens) == 2:
                IdleLieScreen.answered = True
    monkeypatch.setattr(runner, "lie_alarm", fake_siren)
    IdleLieScreen.answered = False
    clock = iter(range(0, 10 ** 6))
    monkeypatch.setattr(runner.time, "perf_counter", lambda: next(clock) * 0.1)   # idle polls 0.1 s apart
    script = lambda name, n: (name == START and n >= 400) or (name == STOP and 5 <= n <= 6)  # noqa: E731
    _, _, out = _serve(tmp_path, monkeypatch, script, max_hunts=1, screen=IdleLieScreen)
    assert len(sirens) == 2 and len(list(out.glob("lie_idle_*.png"))) == 1


def test_load_map_not_in_assets_says_rebuild_and_never_goes_online(tmp_path, monkeypatch):
    """No more download on a missing map (maplestory.io is gone, 2026-11-03): say so, don't hunt."""
    (tmp_path / "mcw").mkdir()
    monkeypatch.setattr(runner, "ASSETS", tmp_path)
    said = []
    rig = SimpleNamespace(cfg=Config(), maps=None)
    assert runner._load_map(rig, 999, said.append) is False
    assert "isn't in assets/mcw" in said[0] and "assets build" in said[0]
    assert rig.cfg.perception.map_id is None


def test_load_map_from_the_real_assets(monkeypatch):
    if not (runner.ASSETS / "mcw" / "maps" / "42" / "map.json").exists():
        pytest.skip("needs assets/mcw")
    said = []
    rig = SimpleNamespace(cfg=Config(), maps=None)
    assert runner._load_map(rig, 42, said.append) is True
    assert any(s.startswith("map 42 Maple Road / Snail Hunting Ground III: mobs Snail (2), Blue Snail (3), "
                            "Red Snail (5)") for s in said), said
    assert rig.cfg.perception.map_id == 42 and rig.kit.map_id == 42 and sorted(rig.kit.mobs) == [2, 3, 5]
