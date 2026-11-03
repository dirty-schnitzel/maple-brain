"""What the brain can ask for. The executor turns key actions into input; the runner handles perception ones."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Hold:          # keep a key down (re-sent every tick like keyboard auto-repeat); releases any other held key
    key: str


@dataclass(frozen=True)
class Release:       # release whatever is held
    pass


@dataclass(frozen=True)
class Tap:           # press and release; blocks for `secs`
    key: str
    secs: float


@dataclass(frozen=True)
class Look:          # take a still motion look this tick, then ask the brain again
    pass


@dataclass(frozen=True)
class Track:         # start following this box as the target
    box: tuple


@dataclass(frozen=True)
class Untrack:
    pass


@dataclass(frozen=True)
class Learn:         # the target is a confirmed mob: remember its appearance
    pass


@dataclass(frozen=True)
class Forget:        # the target turned out not to be a mob: forget anything that looks like it
    pass


@dataclass(frozen=True)
class Stop:          # stop the run (safety)
    reason: str
