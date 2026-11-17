"""tools/data/corpus.py (PLAN-data.md sections 4-5): a recording is cut into its maps by what the minimap names
frame by frame, filed in the manifest, and handed to tools as segments - hold-out ones only on purpose.
The cut is tested on scripted names (which frame names which map); `add` end to end on a small real recording of
the Ant Tunnel IV fixture frames (needs the GPU encoder: skipped without it)."""
import importlib.util
import json
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "data"))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import corpus  # noqa: E402
import frames as fr  # noqa: E402

from test_video import _frames, needs_encoder  # noqa: E402

ANT4, DARK, LINE1, KERNING, BOOTH, PERION = 10005063, 10005064, 10003061, 10003000, 10003060, 10004000
HOLD_A, HOLD_B = [m for m in range(10001000, 10001200) if zlib.crc32(str(m).encode()) % 4 == 0][:2]   # by the rule


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An empty corpus folder."""
    monkeypatch.setenv("MAPLE_CORPUS", str(tmp_path / "corpus"))
    fr._VIDEOS.clear()
    return tmp_path / "corpus"


class Names:
    """Scripted recogniser: row index -> map id / None, from runs [(map, how many frames), ...] at 60 fps."""

    def __init__(self, *runs):
        self.maps = [m for m, k in runs for _ in range(k)]
        self.rows = [(i, f"{i:06d}.png", i / 60) for i in range(len(self.maps))]
        self.seen, self.luma = {}, {}

    def __call__(self, i):
        self.seen[i] = self.maps[i]
        return self.maps[i]

    def cut(self):
        ident = type("Ident", (), {"canvases": {ANT4: 1, DARK: 1, LINE1: 1, KERNING: 1, PERION: 1}})()
        segs, cuts, _ = corpus.cut(Path("."), self.rows, ident, say=lambda s: None, name=self)
        return [(s["i"][0], s["i"][1], s["map"], s["how"]) for s in segs], [(c["what"], c["a"], c["b"]) for c in cuts]


def test_a_map_change_is_cut_at_the_loading_frames_between_the_two_maps():
    """Ant Tunnel IV for 5 s, 30 frames nothing names (the loading screen), Dark Cave: each map ends / starts at
    its own last / first named frame, the loading frames belong to neither."""
    n = Names((ANT4, 300), (None, 30), (DARK, 300))
    segs, cuts = n.cut()
    assert segs == [(0, 299, ANT4, "minimap"), (330, 629, DARK, "minimap")]
    assert cuts == [("loading", 300, 329)]
    assert len(n.seen) < 120                                 # one look a second + the second around the cut


def test_a_change_with_no_unnamed_frame_between_is_cut_between_the_two_frames():
    segs, cuts = Names((ANT4, 200), (DARK, 200)).cut()
    assert segs == [(0, 199, ANT4, "minimap"), (200, 399, DARK, "minimap")] and cuts[0][0] == "direct"


def test_a_short_stretch_without_a_name_keeps_the_map():
    """The minimap covered for a second (a window over it): the same map, one segment."""
    segs, cuts = Names((ANT4, 300), (None, 70), (ANT4, 300)).cut()
    assert segs == [(0, 669, ANT4, "minimap")] and cuts == []


def test_a_long_stretch_without_a_name_inside_one_map_is_its_own_unknown_segment():
    """Perion -> the weapon store (no minimap: 35 such maps) -> Perion looks like Perion with a hole. Longer than
    a loading screen = its own segment, never called Perion; which shop it was can't be told: unknown."""
    segs, cuts = Names((PERION, 300), (None, 400), (PERION, 300)).cut()
    assert segs == [(0, 299, PERION, "minimap"), (300, 699, None, None), (700, 999, PERION, "minimap")]
    assert cuts == [("unknown", 300, 699)]


def test_a_never_named_stretch_between_two_maps_is_named_by_the_portals_when_only_one_map_connects_them():
    """Kerning City -> (5 s nothing named) -> Line 1 <Area 1>: they do not connect directly, and the only map
    without a minimap between them is the Subway Ticketing Booth."""
    assert corpus.between(KERNING, LINE1, {BOOTH}) == BOOTH
    segs, cuts = Names((KERNING, 300), (None, 300), (LINE1, 300)).cut()
    assert segs == [(0, 299, KERNING, "minimap"), (300, 599, BOOTH, "portals"), (600, 899, LINE1, "minimap")]
    assert cuts == [("portals", 300, 599)]


def test_two_maps_that_connect_directly_leave_a_long_unnamed_stretch_unknown():
    """Ant Tunnel IV and Dark Cave share a portal: 5 unnamed seconds between them are a closed minimap on one of
    them or the other - not guessed."""
    assert corpus.between(ANT4, DARK, {BOOTH}) is None
    segs, cuts = Names((ANT4, 300), (None, 300), (DARK, 300)).cut()
    assert segs[1] == (300, 599, None, None) and cuts == [("unknown", 300, 599)]


def test_one_look_naming_another_map_on_a_single_frame_changes_nothing():
    """A new map counts only when the next two frames name it too (a half-drawn minimap during a change)."""
    segs, cuts = Names((ANT4, 120), (DARK, 1), (ANT4, 239)).cut()
    assert segs == [(0, 359, ANT4, "minimap")] and cuts == []


def test_a_map_named_for_under_a_second_is_no_visit():
    """... and only when the look a second later names it too: 20 frames of another name between two maps (a
    minimap drawn wrong while the map loads) belong to the loading frames, not to a third map."""
    segs, cuts = Names((ANT4, 120), (PERION, 20), (None, 10), (DARK, 240)).cut()
    assert segs == [(0, 119, ANT4, "minimap"), (150, 389, DARK, "minimap")] and cuts == [("loading", 120, 149)]
    segs, _ = Names((ANT4, 120), (PERION, 150), (DARK, 240)).cut()           # 2.5 s of it: a map crossed
    assert [s[2] for s in segs] == [ANT4, PERION, DARK]


def test_unnamed_start_and_end():
    """A long unnamed start / end is unknown; a short one (the recording began or ended mid-load) is left out."""
    segs, cuts = Names((None, 400), (ANT4, 300), (None, 20)).cut()
    assert segs == [(0, 399, None, None), (400, 699, ANT4, "minimap")]
    assert cuts == [("unknown", 0, 399), ("end", 700, 719)]
    segs, _ = Names((None, 900)).cut()
    assert segs == [(0, 899, None, None)]


class _Ident:
    """Scripted recogniser for the Namer: frame = its row index; `sure` rows are named, the others only show the
    map's picture when looked at with a window measured elsewhere (`fits`)."""
    min_score, lead = 0.5, 0.05

    def __init__(self, sure: dict, picture: dict):
        self.sure, self.picture = sure, picture              # row -> map; row -> {map: score} inside a given window

    def identify(self, frames):
        return type("M", (), {"map_id": self.sure.get(frames[0])})()

    def fits(self, frame, win):
        return {k: (s, 0, 0) for k, s in self.picture.get(frame, {}).items()}


def test_a_frame_the_recogniser_cannot_measure_is_held_by_the_window_of_the_frame_beside_it(monkeypatch):
    """A mob drawn over the minimap's frame: no window measured, but the map's picture is still where the last
    measured window was -> the same map. Only as the clear winner, only the map named beside it."""
    monkeypatch.setattr(fr, "read", lambda run, name: int(name[:6]))
    rows = [(i, f"{i:06d}.png", i / 60) for i in range(8)]
    ident = _Ident({0: ANT4, 1: ANT4, 7: ANT4},
                   {2: {ANT4: 0.9, DARK: 0.3},               # still Ant Tunnel IV there: held
                    3: {ANT4: 0.62, DARK: 0.60},             # two maps alike: not held
                    4: {DARK: 0.9, ANT4: 0.2},               # another map wins with the stale window: never named so
                    5: {ANT4: 0.4},                          # under the recogniser's bar
                    6: {}})                                  # no minimap picture at all (a shop)
    name = corpus.Namer(Path("."), rows, ident, window=lambda f: "window")
    name.luma = type("L", (dict,), {"__setitem__": lambda *a: None})()
    monkeypatch.setattr(corpus, "round", lambda *a: 0.0, raising=False)
    got = []
    for i in range(8):
        try:
            got.append(name(i))
        except TypeError:                                    # (the scripted frame is not a picture: no brightness)
            got.append(name.seen.get(i))
    assert got[:3] == [ANT4, ANT4, ANT4] and got[3:7] == [None, None, None, None] and name.held == 1


def test_hold_out_maps_are_picked_by_the_rule_and_the_first_seven_stay_dev(home):
    assert all(corpus.group_of(m) == "dev" for m in corpus.DEV_FIRST)
    assert zlib.crc32(b"10005064") % 4 == 0                  # Dark Cave would be hold-out by the rule: it was used
    new = [m for m in range(10001000, 10001200) if m not in corpus.DEV_FIRST]
    hold = [m for m in new if corpus.group_of(m) == "holdout"]
    assert hold == [m for m in new if zlib.crc32(str(m).encode()) % 4 == 0] and 30 < len(hold) < 70
    assert corpus.group_of(None) is None


def _manifest(home, *lines):
    home.mkdir(parents=True, exist_ok=True)
    corpus._save([{"recording": s.split("#")[0], "k": int(s.split("#")[1]), "seg": s, "map": m, "group": g,
                   "name": "x", "frames": [0, 9]} for s, m, g in lines])


def test_a_tool_is_refused_a_hold_out_segment_unless_asked_and_each_use_is_logged(home):
    _manifest(home, ("walk_1#0", ANT4, "dev"), ("walk_1#1", HOLD_A, "holdout"))
    (home / "recordings" / "walk_1").mkdir(parents=True)
    assert fr.clip("walk_1#0", tool="t").map_id == ANT4
    with pytest.raises(SystemExit, match="HOLD-OUT"):
        fr.clip("walk_1#1", tool="t")
    assert not (home / "holdout_uses.jsonl").exists()
    c = fr.clip("walk_1#1", holdout=True, tool="replay/run.py")
    assert c.seg["map"] == HOLD_A and c.out == home / "work" / "walk_1#1" and c.run == home / "recordings" / "walk_1"
    (use,) = [json.loads(l) for l in (home / "holdout_uses.jsonl").read_text().splitlines()]
    assert use["tool"] == "replay/run.py" and use["seg"] == "walk_1#1" and use["map"] == HOLD_A
    with pytest.raises(SystemExit, match="corpus recording of 2 maps"):          # the folder itself: which map?
        fr.clip(home / "recordings" / "walk_1")
    with pytest.raises(SystemExit, match="not a run folder"):
        fr.clip("walk_9#0")


def test_a_map_moves_to_dev_only_before_it_was_used_as_hold_out(home):
    _manifest(home, ("walk_1#0", HOLD_A, "holdout"), ("walk_1#1", HOLD_B, "holdout"))
    (home / "recordings" / "walk_1").mkdir(parents=True)
    assert corpus.group_of(HOLD_A) == corpus.group_of(HOLD_B) == "holdout"
    fr.clip("walk_1#1", holdout=True, tool="t")
    corpus.to_dev([HOLD_A], say=lambda s: None)
    assert corpus.group_of(HOLD_A) == "dev" and corpus.segment("walk_1#0")["group"] == "dev"
    with pytest.raises(SystemExit, match="already used as a hold-out"):
        corpus.to_dev([HOLD_B])
    assert corpus.segment("walk_1#1")["group"] == "holdout"


def _recording(run: Path, frames: list, keys: list = (), close: bool = True):
    """A `record`-style recording: the frames as video at 60 fps, the player's key presses."""
    from maplebrain.runtime.video import VideoWriter
    vw = VideoWriter(run, note={"by": "record"})
    for i, f in enumerate(frames):
        vw.put(f, i, i / 60, wait=True)
    if close:
        vw.close()
    (run / "keys.jsonl").write_text("".join(json.dumps({"t": t, "key": k, "down": True}) + "\n" for t, k in keys))
    return vw


@needs_encoder
def test_add_files_a_recording_by_its_minimap_and_tools_read_its_frames(home, tmp_path, capsys):
    """Check + cut + manifest + move, on 3 s of Ant Tunnel IV: named from the minimap alone (no log, no --map),
    dev (one of the first seven), fought on (attack presses), the marker key counted; then a tool takes the
    segment and gets the recorded pixels."""
    frames = _frames(180)
    run = tmp_path / "incoming" / "20261118_101500_1"
    _recording(run, frames, keys=[(0.5, "q"), (1.0, "c"), (1.2, "x"), (2.0, "f12"), (9.0, "q")])
    (line,) = corpus.add(run, say=lambda s: None)
    assert line["seg"] == "20261118_101500_1#0" and line["map"] == ANT4 and line["how"] == "minimap"
    assert line["name"] == "Ant Tunnel IV" and line["group"] == "dev" and line["frames"] == [0, 179]
    assert line["attacks"] == 2 and line["first_attack"] == 0.5 and line["kind"] == "visited"
    assert line["marks"] == [2.0] and line["by"] == "record" and line["minutes"] == round(179 / 60 / 60, 2)
    assert not run.exists() and corpus.load() == [line]
    dest = home / "recordings" / "20261118_101500_1"
    with pytest.raises(PermissionError):
        open(dest / "frames_0000.mkv", "ab")                 # the corpus is read-only
    c = fr.clip("20261118_101500_1#0", tool="test")
    rows = c.frames()
    assert len(rows) == 180 and rows[0] == (0, "000000.png", 0.0)
    assert np.array_equal(c.read("000179.png"), frames[179]) and np.array_equal(c.read("000000.png"), frames[0])
    assert fr.clip(dest, tool="test").map_id == ANT4         # the folder of a one-map recording works too
    with pytest.raises(corpus.Problem, match="in the corpus already"):
        corpus.add(dest)
    corpus.report()
    said = capsys.readouterr().out
    assert "1 recording(s), 1 segment(s)" in said and "Dungeon / Ant Tunnel IV" in said
    if (ROOT / "assets" / "scene").exists():                 # (the coverage is counted from the scene models)
        assert "mob types: 2 of 51 on clean maps" in said and "background sets: 1 of 13" in said
        assert "not seen yet on a clean map" in said and "Stirge (lv 20): " in said
    fr.video(dest).close()
    for f in dest.iterdir():
        f.chmod(0o666)                                       # (so pytest can clear its folder)


@needs_encoder
def test_add_dry_writes_nothing(home, tmp_path):
    run = tmp_path / "incoming" / "20261118_101500_2"
    _recording(run, _frames(70))
    (line,) = corpus.add(run, dry=True, say=lambda s: None)
    assert line["map"] == ANT4 and line["kind"] == "crossed" and line["attacks"] == 0
    assert run.exists() and corpus.load() == [] and not (home / "recordings").exists()
    fr.video(run).close()


@needs_encoder
def test_a_recording_cut_short_is_repaired_and_filed_with_the_frames_it_holds(home, tmp_path):
    """The recorder killed: video.json was never closed and frames.jsonl lists frames that never reached the file.
    `add` takes what the file holds - the first frames, in order."""
    frames = _frames(100)
    run = tmp_path / "incoming" / "20261118_101500_3"
    vw = _recording(run, frames, close=False)
    for i in range(100, 130):                                # listed, never written: the queue at the kill
        vw._index.write(json.dumps({"n": i, "t": i / 60}) + "\n")
    vw.close()
    meta = json.loads((run / "video.json").read_text())
    meta.update(closed=False, frames=None)                   # as the kill leaves it
    (run / "video.json").write_text(json.dumps(meta))
    said = []
    (line,) = corpus.add(run, say=said.append)
    assert line["frames"] == [0, 99] and line["n_frames"] == 100
    assert any("the last 30 never reached the file" in s for s in said)
    dest = home / "recordings" / "20261118_101500_3"
    assert json.loads((dest / "video.json").read_text())["cut"] is True
    v = fr.video(dest)
    assert len(v) == 100 and np.array_equal(v.frame(99), frames[99]) and np.array_equal(v.frame(40), frames[40])
    v.close()
    for f in dest.iterdir():
        f.chmod(0o666)


@needs_encoder
def test_an_old_png_recording_is_copied_in_as_video_and_left_as_it_is(home, tmp_path):
    """Frames saved every 3rd tick as PNG + ticks.jsonl + a log naming the map: every video frame is compared with
    its PNG, the whole recording is one dev segment of the log's map, the PNG folder is untouched."""
    frames = _frames(24)
    run = tmp_path / "runs" / "20261116_154819_1"
    (run / "frames").mkdir(parents=True)
    with open(run / "ticks.jsonl", "w") as f:
        for k in range(1, 73):
            name = f"{k:06d}.png" if k % 3 == 0 else None
            if name:
                cv2.imwrite(str(run / "frames" / name), frames[k // 3 - 1])
            f.write(json.dumps({"n": k, "frame": name, "obs": {"t": k / 30}, "timings": {}}) + "\n")
    (run / "log.txt").write_text("map 10005063 Dungeon / Ant Tunnel IV\n")
    (run / "keys.jsonl").write_text(json.dumps({"t": 1.0, "key": "q", "down": True}) + "\n")
    (run / "xshift.txt").write_text("0")
    (line,) = corpus.add(run, say=lambda s: None)
    assert line["map"] == ANT4 and line["how"] == "log" and line["group"] == "dev" and line["by"] == "import"
    assert line["frames"] == [3, 72] and line["n_frames"] == 24 and line["attacks"] == 1 and line["date"] == "2026-11-16"
    assert len(list((run / "frames").glob("*.png"))) == 24                # the PNG recording is as it was
    dest = home / "recordings" / "20261116_154819_1"
    assert (dest / "ticks.jsonl").exists() and (dest / "log.txt").exists() and not (dest / "frames").exists()
    c = fr.clip("20261116_154819_1#0", tool="test")
    assert [n for n, _, _ in c.frames()] == list(range(3, 73, 3))
    assert np.array_equal(c.read("000072.png"), frames[23])
    assert [k["n"] for k in c.sight()] == list(range(3, 73, 3))           # its own ticks: what perception saw
    fr.video(dest).close()
    for f in dest.iterdir():
        f.chmod(0o666)


def test_presses_of_a_bot_hunt_come_from_its_ticks(tmp_path):
    """A hunt has no keys.jsonl (those are the player's keys): the attack key going down in the held keys."""
    held = [[], ["q"], ["q"], [], ["left"], ["c", "left"], [], ["q"]]
    (tmp_path / "ticks.jsonl").write_text("".join(
        json.dumps({"n": i + 1, "obs": {"t": i / 10}, "timings": {"held": h}}) + "\n" for i, h in enumerate(held)))
    attack, marks = corpus.presses(tmp_path)
    assert attack == [0.1, 0.5, 0.7] and marks == []
