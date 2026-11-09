import json

from maplebrain.runtime.keylog import KeyLogger, KeyState, key_name


def test_names_match_the_bots_key_names():
    assert key_name(0x39, False, 0x20) == "space"
    assert key_name(0x2A, False, 0xA0) == "shift"
    assert key_name(0x4B, True, 0x25) == "left"          # arrow block
    assert key_name(0x4B, False, 0x64) == "kp_4"         # numpad 4: same scan code, not extended
    assert key_name(0x2C, False, 0x5A) == "z"
    assert key_name(0x7F, False, 0xAB) == "vkab"         # unknown -> the virtual key code


def test_only_transitions_are_recorded():
    s = KeyState()
    assert s.feed("left", up=False, focused=True)
    assert not s.feed("left", up=False, focused=True)    # auto-repeat
    assert s.feed("left", up=True, focused=True)
    assert not s.feed("left", up=True, focused=True)     # up without a recorded down


def test_keys_pressed_into_another_window_are_not_recorded_but_ups_always_are():
    s = KeyState()
    assert not s.feed("a", up=False, focused=False)
    assert not s.feed("a", up=True, focused=False)
    assert s.feed("space", up=False, focused=True)
    assert s.feed("space", up=True, focused=False)       # released after alt-tab: still closed in the log


def test_hook_installs_and_stop_closes_held_keys(tmp_path):
    clock = iter([10.5, 11.0]).__next__
    kl = KeyLogger(tmp_path / "keys.jsonl", t0=10.0, clock=clock).start()
    assert kl.error is None
    kl.state.feed("right", up=False, focused=True)       # as if the hook had seen it go down
    kl._record("right", up=False, injected=False, lag_ms=0)
    kl.stop()
    lines = [json.loads(x) for x in (tmp_path / "keys.jsonl").read_text().splitlines()]
    assert lines == [{"t": 0.5, "key": "right", "down": True},
                     {"t": 1.0, "key": "right", "down": False, "end": True}]
