"""Turns key actions into keyboard input. Hold re-sends key-down each tick (like keyboard auto-repeat)."""
import time

from ..brain.actions import Hold, Release, Tap
from ..keyboard import Keyboard

MOVE_KEYS = ("left", "right", "up", "down")


class Executor:
    def __init__(self, kb: Keyboard):
        self.kb = kb
        self.held: str | None = None
        self.last_move = 0.0              # when we last moved: the camera keeps sliding a moment afterwards

    def run(self, action) -> None:
        if isinstance(action, Hold):
            if self.held and self.held != action.key:
                self.release()
            self.kb.down(action.key)
            self.held = action.key
            if action.key in MOVE_KEYS:
                self.last_move = time.perf_counter()
        elif isinstance(action, Release):
            self.release()
        elif isinstance(action, Tap):
            if action.key in MOVE_KEYS or self.held not in MOVE_KEYS:
                self.release()                  # (a pickup tap while walking keeps the walk key down)
            self.kb.tap(action.key, down_s=action.secs)
            if action.key in MOVE_KEYS:
                self.last_move = time.perf_counter()

    def release(self) -> None:
        if self.held:
            if self.held in MOVE_KEYS:
                self.last_move = time.perf_counter()
            self.kb.up(self.held)
            self.held = None

    def release_all(self) -> None:
        self.held = None
        self.kb.release_all()
