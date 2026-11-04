"""Live console map (the user, 2026-11-04): the whole map with us and every tracked mob, redrawn in place every
~0.3 s, to set beside the game window.

  python -m maplebot livemap [DIR]            follow the newest hunt under DIR (default runs/manual; serve makes
                                              one folder per F7) or DIR itself if it holds ticks.jsonl
  python -m maplebot livemap RUN --replay     play a recorded run's ticks back at real speed (--speed 2 = faster)

Reads ticks.jsonl as the bot writes it (obs.mobs / obs.cam: needs --gpu). The map comes from the run's log.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from .perception.mapascii import header, render
from .perception.world import letters

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"
MAP_RE = re.compile(r"\bmap (?:recognised: )?(\d{6,})\b")


def _newest(d: Path) -> Path | None:
    if (d / "ticks.jsonl").exists():
        return d
    runs = [p for p in d.iterdir() if (p / "ticks.jsonl").exists()] if d.is_dir() else []
    return max(runs, key=lambda p: (p / "ticks.jsonl").stat().st_mtime, default=None)


def _map_of(run: Path) -> int | None:
    """The map of a hunt: the last map id its log names - serve loads a map once, so later hunts' logs don't say it:
    then the newest earlier hunt's log next to it that does."""
    logs = [run / "log.txt"] + sorted((p / "log.txt" for p in run.parent.iterdir() if p.is_dir() and p != run),
                                      key=lambda f: f.stat().st_mtime if f.exists() else 0, reverse=True)
    for log in logs:
        if log.exists():
            ids = MAP_RE.findall(log.read_text(encoding="utf-8", errors="replace"))
            if ids:
                return int(ids[-1])
    return None


class View:
    def __init__(self, map_id: int, width: int):
        self.map_id, self.width = map_id, width
        self.mj = json.loads((ASSETS / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in self.mj.get("mobs") or []})
        names = {}
        for i in ids:
            f = ASSETS / "mobs" / str(i) / "mob.json"
            names[i] = json.loads(f.read_text(encoding="utf-8")).get("name", str(i)) if f.exists() else str(i)
        self.names, self.let = names, letters(names)

    def frame(self, tick: dict, run: Path) -> str:
        o = tick.get("obs") or {}
        C, me = o.get("cam"), o.get("me")
        marks = []
        for m in o.get("mobs") or []:
            if m["state"] == "tentative":
                continue
            if m.get("kind") == "pet":
                marks.append(("p", m["x"], m["y"]))
                continue
            s = f"{self.let.get(m['mob'], 'M')}{m['id']}{'<' if m['facing'] == 'left' else '>'}"
            s += "x" if m["state"] == "dying" else "^" if m.get("air") else "?" if m["unseen"] > 0.05 else ""
            marks.append((s, m["x"], m["y"]))
        if me and C:
            marks.append(("@", me[0] + C[0], me[1] + C[1]))
        elif o.get("map_pos"):
            marks.append(("@", *o["map_pos"]))
        scr = (C[0], C[0] + 1366) if C else None
        live = [m for m in o.get("mobs") or [] if m["state"] != "tentative"]
        lines = [header(self.mj),
                 f"{run.name}  tick {tick.get('n')}  t={o.get('t', 0):.1f}s  mode {tick.get('mode')}  "
                 f"HP {o.get('hp_now')}/{o.get('hp_max')}  mobs {len(live)}  "
                 f"({', '.join(f'{self.names.get(i, i)} {c}' for i, c in self.let.items())})",
                 render(self.mj, marks=marks, screen=scr, width=self.width)]
        if not o.get("cam") and not o.get("mobs"):
            lines.append("(no tracks in this run: start the bot with --gpu)")
        return "\n".join(lines)


def _draw(text: str, first: bool):
    out = ("\x1b[2J" if first else "") + "\x1b[H" + "\n".join(l + "\x1b[K" for l in text.split("\n")) + "\x1b[J"
    sys.stdout.write(out)
    sys.stdout.flush()


def _width(w):
    if w:
        return w
    try:
        return max(80, os.get_terminal_size().columns - 1)
    except OSError:
        return 160


def follow(d: Path, every: float = 0.3, width: int | None = None, map_id: int | None = None) -> int:
    os.system("")                                   # Windows: turn on ANSI cursor codes
    run, f, view, last, first, said = None, None, None, None, True, None
    try:
        while True:
            new = _newest(d)
            if new is not None and new != run:      # a new hunt (serve: F7) -> follow that one
                run, last = new, None
                if f:
                    f.close()
                f = open(run / "ticks.jsonl", encoding="utf-8")
                view = None
            if f is not None:
                for line in f.readlines():
                    if line.endswith("\n"):
                        try:
                            last = json.loads(line)
                        except json.JSONDecodeError:
                            pass
                mid = map_id or _map_of(run)
                if mid and (view is None or view.map_id != mid):
                    view = View(mid, _width(width))
                if view is not None and last is not None:
                    _draw(view.frame(last, run), first)
                    first = False
                elif first:
                    msg = (f"waiting for {run} ..." if mid else
                           f"{run}: no map id in its log or any earlier hunt's - start livemap with --map ID")
                    if msg != said:
                        print(msg)
                        said = msg
            elif first and said is None:
                said = f"waiting for a hunt under {d} ..."
                print(said)
            time.sleep(every)
    except KeyboardInterrupt:
        return 0


def replay(run: Path, speed: float = 1.0, every: float = 0.3, width: int | None = None, t0: float = 0,
           map_id: int | None = None) -> int:
    os.system("")
    mid = map_id or _map_of(run)
    if mid is None:
        print(f"no map in {run / 'log.txt'}")
        return 2
    view, first, shown = View(mid, _width(width)), True, None
    start = None
    offline = {}                                    # tools/perc/track_run.py output (runs recorded before the
    if (run / "tracks.jsonl").exists():             # tracker was in the bot)
        offline = {r["n"]: r for r in map(json.loads, open(run / "tracks.jsonl", encoding="utf-8"))}
    try:
        for line in open(run / "ticks.jsonl", encoding="utf-8"):
            k = json.loads(line)
            r = offline.get(k["n"])
            if r is not None and not k["obs"].get("mobs"):
                k["obs"]["mobs"], k["obs"]["cam"] = r["tracks"], r["C"]
            t = k["obs"]["t"]
            if t < t0:
                continue
            if start is None:
                start = (time.perf_counter(), t)
            if shown is not None and t - shown < every * speed:
                continue
            wait = start[0] + (t - start[1]) / speed - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            _draw(view.frame(k, run), first)
            first, shown = False, t
    except KeyboardInterrupt:
        pass
    return 0
