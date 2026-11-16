"""Is the capture still aimed at the game window? Shared by every loop that grabs (run / serve / goto / watch).

`Screen.calibrate()` aims the capture at the window's client box once (start of a hunt). The window can be dragged,
resized, minimized or closed afterwards; `Screen.check()` (~1 microsecond) says so. Rules:
  * a hunt asks before AND after every grab (`guard`, like the two focus checks): a frame is used only if the box
    was the aimed one on both sides, so no half-moved picture reaches the tracker or the recording;
  * not aimed -> `WindowLost`, a `FocusLost`: the loop's pause path (keys released);
  * `wait_back` ends the pause: game focused + client area 1366x768 + the box read the same twice in a row (a drag
    takes ~1 s: re-aiming at a window still moving would aim wrong again) -> `calibrate()` + a log line with the
    old and the new box;
  * a client area that is not 1366x768 (resized, minimized, window gone) is never re-aimed at: said in the log,
    paused until it is 1366x768 again.
Loops without keys (serve between hunts, watch) use `Aim.ok()` at each look: False = skip this look.
A fake screen without `check` (tests) is always aimed.
"""
import time

from ..capture import H, W
from ..keyboard import FocusLost


class WindowLost(FocusLost):
    """The capture is not aimed at the game window (moved / wrong size / gone): pause like 'not focused'."""

    def __init__(self, state: str, why: str):
        super().__init__(why)
        self.state, self.why = state, why


def fmt(box) -> str:
    return "none" if not box else f"({box['left']}, {box['top']}) {box['width']}x{box['height']}"


def _why(state: str, aimed, box) -> str:
    if state == "moved":
        return f"game window moved: capture aimed at {fmt(aimed)}, window now at {fmt(box)}"
    if state == "gone":
        return "game window gone (closed?)"
    if box["width"] <= 0 or box["height"] <= 0:
        return f"game window minimized (client area {box['width']}x{box['height']}, not {W}x{H})"
    return f"game window resized: client area {box['width']}x{box['height']}, not {W}x{H} - not re-aimed"


def guard(screen) -> None:
    """Raise WindowLost unless the capture is aimed at the window right now."""
    check = getattr(screen, "check", None)
    if check is None:
        return
    state, box = check()
    if state != "ok":
        raise WindowLost(state, _why(state, screen.box, box))


def pause_line(e: FocusLost, foreground_title) -> str:
    why = e.why if isinstance(e, WindowLost) else f"game not focused (foreground: '{foreground_title()}')"
    return f"PAUSED: {why}; keys released"


class Aim:
    """`ok()` at each look: True = the capture is aimed at the window (re-aimed just now if it had moved and has
    come to rest). Says a wrong size / a gone window once, and when the window is back."""

    def __init__(self, screen, say, said: str | None = None):
        self.screen, self.say = screen, say
        self.said = said                # the wrong state already in the log
        self.last = None                # the moved box seen at the last look: the same again = at rest

    def ok(self) -> bool:
        check = getattr(self.screen, "check", None)
        if check is None:
            return True
        state, box = check()
        if state == "ok":
            if self.said in ("size", "gone"):
                self.say(f"game window back at {fmt(box)}: the capture is aimed at it")
            self.said = self.last = None
            return True
        if state == "moved":
            if self.said in ("size", "gone"):
                self.say(f"game window back at {W}x{H}, at another place")
                self.said = "moved"
            if box != self.last:        # first sight, or still being dragged: look again
                self.last = box
                return False
            old = self.screen.box
            self.screen.calibrate()
            self.last = self.said = None
            self.say(f"capture re-aimed: game window moved {fmt(old)} -> {fmt(self.screen.box)}")
            return self.screen.check()[0] == "ok"
        self.last = None
        if self.said != state:
            self.said = state
            self.say(_why(state, self.screen.box, box))
        return False


def wait_back(screen, focused, hz, say, alive, e: FocusLost | None = None) -> bool:
    """The pause: wait (varied ~0.2 s looks) until the game is focused and the capture aimed at it - re-aimed when
    the window moved - or `alive()` says the hunt is over. True = go on."""
    aim = Aim(screen, say, said=getattr(e, "state", None))
    while alive():
        time.sleep(hz.vary(0.2))
        if focused() and aim.ok():
            return True
    return False
