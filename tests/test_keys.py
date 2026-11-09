"""KeyDriver (brain-v2 executor): driven by pump(now) with a fake clock - no thread, no real keys."""
from maplebrain.brain.actions import Hold, Release, Tap
from maplebrain.config import Humanize
from maplebrain.humanize import Humanizer
from maplebrain.runtime.keys import KeyDriver, LegacyExecutor


class Rig:
    def __init__(self, jitter=0.25, seed=1):
        self.t = 0.0
        self.events = []                  # (t, key, "down"|"up")
        self.focus = True
        h = Humanize(seed=seed)
        self.d = KeyDriver(self.send, lambda: self.focus, Humanizer(jitter, seed), h, clock=lambda: self.t)

    def send(self, key, up):
        self.events.append((round(self.t, 3), key, "up" if up else "down"))

    def run(self, until, step=0.001):
        while self.t < until:
            self.d.pump(self.t)
            self.t = round(self.t + step, 6)

    def downs(self, key):
        return [t for t, k, e in self.events if k == key and e == "down"]

    def ups(self, key):
        return [t for t, k, e in self.events if k == key and e == "up"]


def test_several_keys_held_at_once():
    r = Rig()
    r.d.hold({"right", "shift"})
    r.run(0.1)
    assert r.d.held() == {"right", "shift"}
    r.d.hold({"right"})
    r.run(0.2)
    assert r.d.held() == {"right"} and r.ups("shift")


def test_keys_changed_together_never_change_at_the_same_instant():
    same = 0
    for seed in range(20):
        r = Rig(seed=seed)
        r.d.hold({"left", "space"})
        r.run(0.1)
        a, b = r.downs("left")[0], r.downs("space")[0]
        same += a == b
        assert 0.005 <= a <= 0.031 and 0.005 <= b <= 0.031          # the reaction pause
    assert same <= 2


def test_tap_does_not_block_and_has_a_varied_length():
    lengths = []
    for seed in range(10):
        r = Rig(seed=seed)
        assert r.d.tap("space", 0.13)
        r.run(0.5)
        (d,), (u,) = r.downs("space"), r.ups("space")
        lengths.append(round(u - d, 3))
    assert all(0.09 <= x <= 0.17 for x in lengths) and len(set(lengths)) > 5


def test_tap_while_walking_keeps_walking():
    r = Rig()
    r.d.hold({"left"})
    r.run(0.05)
    r.d.tap("space", 0.13)
    r.run(0.5)
    assert r.ups("left") == [] and r.ups("space")


def test_a_second_tap_of_the_same_key_is_dropped_while_one_waits_and_bursts_dont_overlap():
    r = Rig()
    assert r.d.tap("z", 0.09)
    assert not r.d.tap("z", 0.09)          # asked again next tick: no pile-up
    r.run(0.4)
    assert r.d.tap("z", 0.09)              # after it: fine
    r.run(0.8)
    d, u = r.downs("z"), r.ups("z")
    assert len(d) == 2 and u[0] < d[1]


def test_a_tap_of_a_held_key_is_ignored():
    r = Rig()
    r.d.hold({"space"})
    assert not r.d.tap("space", 0.13)


def test_holding_a_key_mid_tap_keeps_it_down():
    r = Rig()
    r.d.tap("right", 0.3)
    r.run(0.1)
    r.d.hold({"right"})
    r.run(1.0)
    assert r.d.held() == {"right"} and r.ups("right") == []


def test_auto_repeat_only_the_last_pressed_key_after_a_delay():
    r = Rig(jitter=0)
    r.d.hold({"left"})
    r.run(0.1)
    r.d.hold({"left", "up"})
    r.run(1.0)
    left, up = r.downs("left"), r.downs("up")
    assert len(left) == 1                                    # repeats moved to 'up', the newer key
    assert up[1] - up[0] >= 0.5 and 0.02 < up[2] - up[1] < 0.05


def test_focus_lost_releases_everything_and_drops_wishes():
    r = Rig()
    r.d.hold({"right"})
    r.d.tap("space", 0.13)
    r.run(0.02)
    r.focus = False
    r.run(0.1)
    assert r.d.held() == set() and r.d.lost_focus and not r.d.busy()
    r.focus = True
    r.run(0.3)
    assert r.d.held() == set()                               # nothing comes back by itself


def test_release_all_is_immediate():
    r = Rig()
    r.d.hold({"right", "up"})
    r.run(0.1)
    r.d.release_all()
    assert r.d.held() == set() and sorted(k for t, k, e in r.events if e == "up") == ["right", "up"]


def test_legacy_executor_keeps_the_old_meaning_without_blocking():
    r = Rig()
    ex = LegacyExecutor(r.d)
    ex.run(Hold("right"))
    r.run(0.05)
    ex.run(Tap("z", 0.06))                                   # pickup while walking: still walking
    r.run(0.2)
    assert "right" in r.d.held() and r.downs("z")
    ex.run(Tap("left", 0.035))                               # a turn: lets go of the walk key
    r.run(0.4)
    assert r.ups("right")[0] < 0.4 and "right" not in r.d.held() and r.downs("left")
    ex.run(Hold("space"))
    ex.run(Release())
    r.run(0.6)
    assert r.d.held() == set() and ex.held is None


def test_real_thread_runs_and_stops():
    import time
    sent = []
    d = KeyDriver(lambda k, up: sent.append((k, up)), lambda: True, Humanizer(0.25, 3), Humanize()).start()
    d.tap("space", 0.03)
    time.sleep(0.15)
    d.stop()
    assert ("space", False) in sent and ("space", True) in sent
