"""serve's hunting MODE and PLATFORM MARKS (brain v3 step 3, Platform mode; the user 2026-11-09).

    F10  next mode, only while no hunt runs: auto (brain v2's hunt anywhere) -> platform -> auto (path mode later)
    F9   platform mode, only while no hunt runs: mark / unmark the platform we stand on (map recognised first)
    F7   platform mode: hunts only on this map's marked platforms (goal HuntArea); none marked -> no hunt

Marks are kept per map until serve ends (nothing saved to disk): back on a map, its marks are back. A hunt is bound to
the marks taken before its F7.
"""
MODES = ("auto", "platform")


class Marks:
    def __init__(self):
        self.mode = MODES[0]
        self.by_map = {}                                  # map id -> set of platform ids

    def next_mode(self) -> str:
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        return self.mode

    def toggle(self, map_id: int, pid: int) -> bool:
        """True = now marked, False = unmarked."""
        s = self.by_map.setdefault(map_id, set())
        if pid in s:
            s.remove(pid)
            return False
        s.add(pid)
        return True

    def area(self, map_id) -> frozenset:
        return frozenset(self.by_map.get(map_id, ()))
