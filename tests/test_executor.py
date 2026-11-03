"""Actions -> key events."""
from maplebot.brain.actions import Hold, Release, Tap
from maplebot.runtime.executor import Executor


class Keys:
    def __init__(self):
        self.events = []

    def down(self, k):
        self.events.append(("down", k))

    def up(self, k):
        self.events.append(("up", k))

    def tap(self, k, down_s=0.08):
        self.events += [("down", k), ("up", k)]

    def release_all(self):
        self.events.append(("release_all", None))


def test_pickup_tap_while_walking_keeps_the_walk_key_down():
    kb = Keys()
    ex = Executor(kb)
    ex.run(Hold("right"))
    ex.run(Tap("z", 0.06))
    assert ("up", "right") not in kb.events and ex.held == "right"


def test_a_turn_tap_still_lets_go_of_the_walk_key():
    kb = Keys()
    ex = Executor(kb)
    ex.run(Hold("right"))
    ex.run(Tap("left", 0.035))
    assert kb.events.index(("up", "right")) < kb.events.index(("down", "left"))


def test_a_tap_while_attacking_lets_go_of_attack():
    kb = Keys()
    ex = Executor(kb)
    ex.run(Hold("space"))
    ex.run(Tap("z", 0.06))
    assert ("up", "space") in kb.events
    ex.run(Release())
