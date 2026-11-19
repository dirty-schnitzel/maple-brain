"""tools/data/corpus.py (PLAN-data.md sections 4-5): a recording is cut into its maps by what the minimap names
frame by frame; every stay on a map is filed in that map's folder (its frames written again losslessly and read
back identical) and handed to tools by its id - hold-out ones only on purpose.
The cut is tested on scripted names (which frame names which map); `add` end to end on small real recordings of
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
REAL_HOLD = next((int(p.name) for p in sorted((ROOT / "assets" / "mcw" / "maps").glob("1000*")) if p.is_dir()
                  and zlib.crc32(p.name.encode()) % 4 == 0 and int(p.name) not in corpus.DEV_FIRST), HOLD_A)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An empty corpus folder."""
    monkeypatch.setenv("MAPLE_CORPUS", str(tmp_path / "corpus"))
    fr._VIDEOS.clear()
    yield tmp_path / "corpus"
    for v in [fr._VIDEOS.pop(k) for k in list(fr._VIDEOS)]:
        if v is not None:
            v.close()
    for f in tmp_path.rglob("*"):                            # (filed footage is read-only: let pytest clear it)
        if f.is_file():
            f.chmod(0o666)


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
    """Stays as the manifest and their folders know them: (id, map, group)."""
    rows = []
    for s, m, g in lines:
        top = "holdout" if g == "holdout" else "maps"
        rows.append({"v": corpus.V, "session": s.split("#")[0], "k": int(s.split("#")[1]), "seg": s, "map": m,
                     "group": g, "name": "x", "frames": [0, 9], "path": f"{top}/x ({m})/stay_{s.split('#')[1]}"})
        (home / rows[-1]["path"]).mkdir(parents=True)
        (home / rows[-1]["path"] / "stay.json").write_text(json.dumps(rows[-1]))
    corpus._save(rows)
    return rows


def test_a_tool_is_refused_a_hold_out_stay_unless_asked_and_each_use_is_logged(home):
    a, b = _manifest(home, ("walk_1#0", ANT4, "dev"), ("walk_1#1", HOLD_A, "holdout"))
    assert fr.clip("walk_1#0", tool="t").map_id == ANT4
    for arg in ("walk_1#1", home / b["path"]):               # by its id or by its folder: refused alike
        with pytest.raises(SystemExit, match="HOLD-OUT"):
            fr.clip(arg, tool="t")
    assert not (home / "holdout_uses.jsonl").exists()
    c = fr.clip("walk_1#1", holdout=True, tool="replay/run.py")
    assert c.seg["map"] == HOLD_A and c.run == home / b["path"]
    assert c.out == home / "work" / "walk_1#1" and c.keep == home / "labels" / "walk_1#1"      # never its folder
    (use,) = [json.loads(l) for l in (home / "holdout_uses.jsonl").read_text().splitlines()]
    assert use["tool"] == "replay/run.py" and use["seg"] == "walk_1#1" and use["map"] == HOLD_A
    assert fr.clip(home / a["path"], tool="t").seg["seg"] == "walk_1#0"          # a dev stay by its folder
    assert fr.map_of(home / a["path"]) == ANT4               # a stay's folder knows its map (a walk has no log)
    with pytest.raises(SystemExit, match="not a run folder"):
        fr.clip("walk_9#0")


def test_labels_are_kept_apart_from_what_tools_can_make_again(home):
    """By-eye labels of a stay live in labels/SESSION#K, tool output in work/SESSION#K (safe to delete); a plain
    run folder keeps both in itself, as always."""
    (a,) = _manifest(home, ("walk_1#0", ANT4, "dev"))
    c = fr.clip("walk_1#0", tool="t")
    assert c.find("labels.json") == home / "labels" / "walk_1#0" / "labels.json"            # where it will be
    assert c.find("replay/work.jsonl") == home / "work" / "walk_1#0" / "replay" / "work.jsonl"
    (c.run / "labels").mkdir()
    (c.run / "labels" / "cams.json").write_text("{}")        # (an old recording's, were it left in the folder)
    assert c.find("labels/cams.json") == c.run / "labels" / "cams.json"
    plain = home / "some_run"
    plain.mkdir()
    p = fr.clip(plain)
    assert p.keep == p.out == p.run == plain and p.find("labels.json") == plain / "labels.json"


def test_a_map_moves_to_dev_only_before_it_was_used_as_hold_out(home):
    a, b = _manifest(home, ("walk_1#0", HOLD_A, "holdout"), ("walk_1#1", HOLD_B, "holdout"))
    assert corpus.group_of(HOLD_A) == corpus.group_of(HOLD_B) == "holdout"
    fr.clip("walk_1#1", holdout=True, tool="t")
    corpus.to_dev([HOLD_A], say=lambda s: None)
    now = corpus.segment("walk_1#0")
    assert corpus.group_of(HOLD_A) == "dev" and now["group"] == "dev" and now["path"].startswith("maps/")
    assert (home / now["path"] / "stay.json").exists() and not (home / a["path"]).exists()   # the folder moved
    assert json.loads((home / now["path"] / "stay.json").read_text())["group"] == "dev"
    assert fr.clip("walk_1#0", tool="t").run == home / now["path"]
    with pytest.raises(SystemExit, match="already used as a hold-out"):
        corpus.to_dev([HOLD_B])
    assert corpus.segment("walk_1#1")["group"] == "holdout" and (home / b["path"]).exists()


def test_a_stay_is_named_for_people():
    """<date>_<time it began>_<its labels>_<length>_s<its number>: the labels the player gave the recording
    (record --label), then the one the tool works out; the map's folder without what Windows refuses."""
    from datetime import datetime
    assert corpus.stay_name(datetime(2026, 11, 18, 14, 32, 5), ["farming"], 725.4, 3) == "2026-11-18_1432_farming_12m05s_s03"
    assert corpus.stay_name(datetime(2026, 11, 18, 15, 2), ["traveling"], 21.9, 7) == "2026-11-18_1502_traveling_0m21s_s07"
    assert corpus.map_folder(LINE1) == "Line 1 Area 1 (10003061)" and corpus.map_folder(None) == "_unknown"
    assert corpus.safe('a<b>:c"/\\|?*% d. ') == "abc d"
    mode = corpus.play_label                                 # the label the tool gives a stay itself
    assert mode(False, corpus.FARM_ATTACKS, 30, True) == "farming"             # fought
    assert mode(False, corpus.FARM_ATTACKS - 1, 30, True) == "traveling"        # a mob in the way is not farming
    assert mode(False, 0, 90, False) == "town" and mode(False, 0, 20, False) == "traveling"
    assert mode(False, 0, 400, True) == "idle" and mode(False, 0, 400, None) == "idle"
    assert mode(True, 0, 30, True) == "bot"                                     # a bot hunt, whatever it pressed
    # the player's labels are more words in the name, beside farming / traveling: as typed -> parts of a name
    given = corpus.given_labels
    assert given({"labels": ["Expiry test!", "exploration", "expiry-test", " "]}) == ["expiry-test", "exploration"]
    assert given({"scene": "exploration"}) == ["exploration"] and given({"scene": None}) == [] == given({})
    assert corpus.stay_name(datetime(2026, 11, 18, 23, 24), ["exploration", "traveling"], 40, 3) == \
        "2026-11-18_2324_exploration_traveling_0m40s_s03"


def test_every_frame_of_a_session_is_in_exactly_one_stay():
    """A stay's files begin with the frames nobody could name before it (its loading screen); the last stay also
    takes what follows it."""
    segs = [{"i": [0, 99]}, {"i": [130, 400]}, {"i": [401, 500]}, {"i": [520, 600]}]
    assert corpus.bounds(segs, 640) == [(0, 99), (100, 400), (401, 500), (501, 639)]
    assert corpus.bounds([{"i": [5, 9]}], 10) == [(0, 9)]
    with pytest.raises(corpus.Problem, match="out of order"):
        corpus.bounds([{"i": [0, 99]}, {"i": [50, 120]}], 121)


def _recording(run: Path, frames: list, keys: list = (), close: bool = True):
    """A `record`-style recording: the frames as video at 60 fps, the player's keys [(t, key) or (t, key, down)]."""
    from maplebrain.runtime.video import VideoWriter
    vw = VideoWriter(run, note={"by": "record"})
    for i, f in enumerate(frames):
        vw.put(f, i, i / 60, cursor=(100 + i, 50), wait=True, buttons=1 if i == 5 else 0)
    if close:
        vw.close()
    (run / "keys.jsonl").write_text("".join(
        json.dumps({"t": k[0], "key": k[1], "down": k[2] if len(k) > 2 else True}) + "\n" for k in keys))
    return vw


@needs_encoder
def test_add_files_a_recording_under_its_map_and_tools_read_its_frames(home, capsys):
    """Check + cut + file, on 3 s of Ant Tunnel IV: named from the minimap alone (no log, no --map), dev (one of
    the first seven), farmed (5 attack presses), the marker key counted. Its frames are written into the map's
    folder and read back identical; the original in incoming/ is gone; a tool takes the stay by its id."""
    frames = _frames(180)
    run = home / "incoming" / "20261118_101500_1"
    _recording(run, frames, keys=[(0.5, "q"), (0.7, "q"), (1.0, "c"), (1.2, "x"), (1.5, "q"), (1.8, "q"),
                                  (2.0, "f12"), (9.0, "q")])
    (run / "session.json").write_text(json.dumps({"v": 2, "by": "record", "labels": [], "epoch": 1795000500.0,
                                                  "client": "build-x", "code": {"commit": "abc123"}}))
    (line,) = corpus.add(run, say=lambda s: None)
    from datetime import datetime
    began = datetime.fromtimestamp(1795000500.0)             # (the recorder's clock, not the folder's name)
    stay = f"{began:%Y-%m-%d_%H%M}_farming_0m02s_s00"
    assert line["seg"] == "20261118_101500_1#0" and line["map"] == ANT4 and line["how"] == "minimap"
    assert line["name"] == "Ant Tunnel IV" and line["group"] == "dev" and line["frames"] == [0, 179]
    assert line["attacks"] == 5 and line["first_attack"] == 0.5 and line["labels"] == ["farming"] and line["by"] == "record"
    assert line["marks"] == [2.0] and line["minutes"] == round(179 / 60 / 60, 2) and line["arrive"] == 0
    assert line["stay"] == stay and line["path"] == f"maps/Ant Tunnel IV (10005063)/{stay}"
    assert line["client"] == "build-x" and line["code"] == "abc123"
    assert not run.exists() and corpus.load() == [line]      # the original is gone only now: every frame is filed
    dest = home / line["path"]
    video = dest / f"Ant Tunnel IV_{stay}_000.mkv"           # a file that says what it is, wherever it is copied
    assert [f["name"] for f in line["files"]] == [video.name] and line["bytes"] == video.stat().st_size
    assert json.loads((dest / "stay.json").read_text()) == line
    assert (dest / "sheet.jpg").stat().st_size > 10000 and (dest / "preview.mp4").stat().st_size > 1000
    rows = [json.loads(l) for l in (dest / "frames.jsonl").read_text().splitlines()]
    assert len(rows) == 180 and rows[5] == {"n": 5, "t": round(5 / 60, 4), "cur": [105, 50], "b": 1,
                                            "h": corpus.fingerprint(frames[5])}
    assert [json.loads(l)["key"] for l in (dest / "keys.jsonl").read_text().splitlines()] == \
        ["q", "q", "c", "x", "q", "q", "f12"]                # the keys inside the stay's time (9.0 s is after it)
    with pytest.raises(PermissionError):
        open(video, "ab")                                    # the footage is read-only
    ses = home / "sessions" / "20261118_101500_1"
    assert json.loads((ses / "session.json").read_text())["client"] == "build-x"
    assert stay in (ses / "route.txt").read_text() and (ses / "frames.jsonl").exists() and (ses / "cuts").is_dir()
    assert "Ant Tunnel IV" in (home / "index.txt").read_text() and "maps/<map name>" in (home / "README.txt").read_text()
    for arg in ("20261118_101500_1#0", dest):                # a tool takes it by its id or by its folder
        c = fr.clip(arg, tool="test")
        got = c.frames()
        assert len(got) == 180 and got[0] == (0, "000000.png", 0.0) and c.map_id == ANT4
        assert np.array_equal(c.read("000179.png"), frames[179]) and np.array_equal(c.read("000000.png"), frames[0])
    fr.video(dest).close()
    _recording(run, frames[:10])
    with pytest.raises(corpus.Problem, match="in the corpus already"):
        corpus.add(run)
    corpus.report(stays=True)
    said = capsys.readouterr().out
    assert "1 session(s), 1 stay(s)" in said and "Dungeon / Ant Tunnel IV" in said and line["path"] in said
    if (ROOT / "assets" / "scene").exists():                 # (the coverage is counted from the scene models)
        assert "mob types: 2 of 51 on clean maps" in said and "background sets: 1 of 13" in said
        assert "not seen yet on a clean map" in said and "Stirge (lv 20): " in said
    # verify: the files are what was filed - until one byte of one changes
    assert corpus.verify(say=lambda s: None) == 0 and corpus.verify(frames=True, say=lambda s: None) == 0
    video.chmod(0o666)
    with open(video, "r+b") as f:
        f.seek(video.stat().st_size // 2)
        byte = f.read(1)
        f.seek(-1, 1)
        f.write(bytes([byte[0] ^ 0xFF]))
    told = []
    assert corpus.verify(say=told.append) == 1 and "is not the file that was filed" in told[0]


@needs_encoder
def test_add_dry_files_nothing_and_a_recording_outside_incoming_is_never_removed(home, tmp_path):
    run = tmp_path / "elsewhere" / "20261118_101500_2"
    _recording(run, _frames(70))
    (line,) = corpus.add(run, dry=True, say=lambda s: None)
    assert line["map"] == ANT4 and line["labels"] == ["traveling"] and line["attacks"] == 0
    assert run.exists() and corpus.load() == [] and not (home / "maps").exists() and not (home / "sessions").exists()
    said = []
    (line,) = corpus.add(run, say=said.append)               # for real: filed, and the original left where it was
    assert (run / "frames_0000.mkv").exists() and any("the original stays as it is" in s for s in said)
    assert (home / line["path"] / "stay.json").exists()
    fr._VIDEOS.clear()


class _Cut:
    """A scripted cut (the fixture frames all show one map): `cut`'s result and its Namer."""
    held = 0

    def __init__(self, segs, cuts):
        self.segs, self.cuts, self.seen, self.luma = segs, cuts, {}, {}

    def __call__(self, i):
        self.seen[i] = self.luma[i] = 1
        return next((s["map"] for s in self.segs if s["i"][0] <= i <= s["i"][1]), None)

    def cut(self, run, rows, ident, say=print, name=None):
        return self.segs, self.cuts, self


@needs_encoder
def test_a_walk_through_two_maps_is_filed_as_two_stays_each_under_its_map(home, monkeypatch):
    """1 s on Ant Tunnel IV, 20 loading frames, 1.7 s on a map new to the corpus that the rule holds out: two
    folders, the hold-out one under holdout/. The loading frames open the second stay's files, so every frame of
    the walk is in exactly one stay - and only then the original is removed."""
    frames = _frames(180)
    run = home / "incoming" / "20261118_101500_4"
    _recording(run, frames, keys=[(0.2, "left"), (0.5, "q"), (0.6, "q", False), (2.0, "left", False), (2.5, "q")])
    script = _Cut([{"i": [0, 59], "map": ANT4, "how": "minimap"}, {"i": [80, 179], "map": REAL_HOLD, "how": "minimap"}],
                  [{"a": 60, "b": 79, "from": ANT4, "to": REAL_HOLD, "s": 0.35, "what": "loading", "map": None}])
    monkeypatch.setattr(corpus, "cut", script.cut)
    a, b = corpus.add(run, say=lambda s: None)
    assert a["path"].startswith("maps/Ant Tunnel IV (10005063)/") and a["stay"].endswith("_s00")
    assert b["path"].startswith(f"holdout/{corpus.map_folder(REAL_HOLD)}/") and b["stay"].endswith("_s01")
    assert (a["frames"], a["file_frames"], a["n_file"], a["arrive"]) == ([0, 59], [0, 59], 60, 0)
    assert (b["frames"], b["file_frames"], b["n_file"], b["arrive"]) == ([80, 179], [60, 179], 120, 20)
    assert a["n_file"] + b["n_file"] == 180 and not run.exists()
    assert b["held"] == ["left"] and a["held"] == []         # walked into the second map with the key held down
    keys_b = [json.loads(l) for l in (home / b["path"] / "keys.jsonl").read_text().splitlines()]
    assert [(k["key"], k["down"]) for k in keys_b] == [("left", False), ("q", True)]
    with pytest.raises(SystemExit, match="HOLD-OUT"):
        fr.clip(b["seg"], tool="t")
    c = fr.clip(b["seg"], holdout=True, tool="t")
    rows = c.frames()                                        # a tool gets the frames ON the map ...
    assert len(rows) == 100 and rows[0][0] == 80 and np.array_equal(c.read("000080.png"), frames[80])
    v = fr.Video(home / b["path"])                           # ... the files hold the loading screen before them too
    assert len(v) == 120 and np.array_equal(v.frame(0), frames[60]) and np.array_equal(v.frame(119), frames[179])
    v.close()
    route = (home / "sessions" / "20261118_101500_4" / "route.txt").read_text()
    assert a["stay"] in route and b["stay"] in route and route.index(a["stay"]) < route.index(b["stay"])
    assert list((home / "sessions" / "20261118_101500_4" / "cuts").glob("cut_000_*.png"))    # the cut's sheet
    assert corpus.verify(frames=True, say=lambda s: None) == 0
    fr._VIDEOS.clear()


@needs_encoder
def test_a_filing_that_fails_leaves_nothing_half_filed_and_the_recording_as_it_was(home, monkeypatch):
    frames = _frames(120)
    run = home / "incoming" / "20261118_101500_5"
    _recording(run, frames)
    script = _Cut([{"i": [0, 59], "map": ANT4, "how": "minimap"}, {"i": [60, 119], "map": DARK, "how": "minimap"}], [])
    monkeypatch.setattr(corpus, "cut", script.cut)
    real = corpus.fingerprint
    seen = []

    def broken(frame):                                       # the second stay reads back differently
        seen.append(1)
        return real(frame) if len(seen) <= 150 else "0" * 16

    monkeypatch.setattr(corpus, "fingerprint", broken)
    with pytest.raises(corpus.Problem, match="read back differently"):
        corpus.add(run, say=lambda s: None)
    assert corpus.load() == [] and (run / "frames_0000.mkv").exists()
    assert not list((home / "maps").rglob("*.mkv")) and not (home / "sessions").exists()
    fr._VIDEOS.clear()


@needs_encoder
def test_a_recording_cut_short_is_repaired_and_filed_with_the_frames_it_holds(home):
    """The recorder killed: video.json was never closed and frames.jsonl lists frames that never reached the file.
    `add` takes what the file holds - the first frames, in order."""
    frames = _frames(100)
    run = home / "incoming" / "20261118_101500_3"
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
    assert json.loads((home / "sessions" / "20261118_101500_3" / "video.json").read_text())["cut"] is True
    v = fr.Video(home / line["path"])
    assert len(v) == 100 and np.array_equal(v.frame(99), frames[99]) and np.array_equal(v.frame(40), frames[40])
    v.close()
    fr._VIDEOS.clear()


@needs_encoder
def test_an_old_png_recording_is_filed_as_one_stay_and_left_as_it_is(home, tmp_path):
    """Frames saved every 3rd tick as PNG + ticks.jsonl + a log naming the map: one stay on the log's map, every
    filed frame its PNG's pixels, its own ticks / log beside the frames, its by-eye labels under labels/. The PNG
    folder is untouched (it is not in incoming/)."""
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
    (run / "labels.json").write_text('{"v": 2}')
    (line,) = corpus.add(run, say=lambda s: None)
    assert line["map"] == ANT4 and line["how"] == "log" and line["group"] == "dev" and line["by"] == "observe"
    assert line["frames"] == [3, 72] and line["n_frames"] == 24 and line["attacks"] == 1
    assert line["date"] == "2026-11-16" and line["stay"] == "2026-11-16_1548_traveling_0m02s_s00"
    assert len(list((run / "frames").glob("*.png"))) == 24                # the PNG recording is as it was
    dest = home / line["path"]
    assert (dest / "ticks.jsonl").exists() and (dest / "log.txt").exists() and (dest / "xshift.txt").exists()
    assert not (dest / "frames").exists() and not (dest / "labels.json").exists()
    c = fr.clip("20261116_154819_1#0", tool="test")
    assert c.find("labels.json") == home / "labels" / "20261116_154819_1#0" / "labels.json" and c.find("labels.json").exists()
    assert [n for n, _, _ in c.frames()] == list(range(3, 73, 3))
    assert np.array_equal(c.read("000072.png"), frames[23])
    assert [k["n"] for k in c.sight()] == list(range(3, 73, 3))           # its own ticks: what perception saw
    fr._VIDEOS.clear()


def test_presses_of_a_bot_hunt_come_from_its_ticks(tmp_path):
    """A hunt has no keys.jsonl (those are the player's keys): the attack key going down in the held keys."""
    held = [[], ["q"], ["q"], [], ["left"], ["c", "left"], [], ["q"]]
    (tmp_path / "ticks.jsonl").write_text("".join(
        json.dumps({"n": i + 1, "obs": {"t": i / 10}, "timings": {"held": h}}) + "\n" for i, h in enumerate(held)))
    attack, marks = corpus.presses(tmp_path)
    assert attack == [0.1, 0.5, 0.7] and marks == []


def test_attack_presses_are_counted_with_the_recordings_own_keys(tmp_path):
    """Which key is the attack can change: a recording's session.json says which it was that day."""
    from maplebrain.config import Keys
    (tmp_path / "keys.jsonl").write_text("".join(
        json.dumps({"t": t, "key": k, "down": True}) + "\n"
        for t, k in [(0.1, "a"), (0.2, Keys.attack), (0.3, "f11"), (0.4, "a")]))
    assert corpus.presses(tmp_path, {"attack": "a", "basic_attack": "b", "note": "f11"}) == ([0.1, 0.4], [0.3])
    assert corpus.presses(tmp_path) == ([0.2], [])           # (without them: today's keys)


@needs_encoder
def test_a_lie_detector_met_while_recording_is_copied_to_lie_with_the_keys_and_the_mouse(home, monkeypatch):
    """3 s of Ant Tunnel IV with the Lie Detector's title on frames 50..130: `add` copies those frames and a
    little before and after into lie/, with the keys pressed and the mouse inside that time. The stay under maps/
    still holds every frame."""
    from maplebrain.perception.liedetector import NAMES
    title = np.load(ROOT / "assets" / NAMES[0])
    frames = [f.copy() for f in _frames(180)]
    for f in frames[50:131]:
        f[300:300 + title.shape[0], 600:600 + title.shape[1]] = title[..., None]
    monkeypatch.setattr(corpus, "LIE_PAD_S", 0.25)
    run = home / "incoming" / "20261118_101500_7"
    _recording(run, frames, keys=[(0.1, "q"), (0.7, "left"), (1.0, "1"), (1.2, "left", False), (2.9, "q")])
    said = []
    (line,) = corpus.add(run, say=said.append)
    ((info, d),) = corpus.lie_dirs()
    assert info["id"] == "20261118_101500_7@ld1" and info["stays"] == [line["seg"]] and info["map"] == ANT4
    assert info["seen_frames"] == [50, 130] and info["frames"] == [35, 145] and info["n_frames"] == 111
    assert info["key_presses"] == 2 and info["held"] == ["q"] and d.name.endswith("_Ant Tunnel IV_0m01s_ld1")
    rows = [json.loads(l) for l in (d / "frames.jsonl").read_text().splitlines()]
    assert rows[0]["n"] == 35 and rows[0]["cur"] == [135, 50] and rows[0]["h"] == corpus.fingerprint(frames[35])
    assert [json.loads(l)["key"] for l in (d / "keys.jsonl").read_text().splitlines()] == ["left", "1", "left"]
    v = fr.Video(d)
    assert len(v) == 111 and np.array_equal(v.frame(0), frames[35]) and np.array_equal(v.frame(110), frames[145])
    v.close()
    assert (d / "sheet.jpg").exists() and any("@ld1" in s for s in said)
    assert json.loads((home / "sessions" / "20261118_101500_7" / "lie.json").read_text())["sections"] == [info["id"]]
    assert line["n_file"] == 180 and corpus.lie_sections(say=said.append) == []          # looked through already
    told = []
    assert corpus.verify(frames=True, say=told.append) == 0 and "1 Lie Detector section(s)" in told[-1]
    (again,) = corpus.lie_sections(["20261118_101500_7"], again=True, say=said.append)
    assert again["frames"] == [35, 145] and len(corpus.lie_dirs()) == 1
    fr._VIDEOS.clear()


def _bar(level: str, job: str = "Spearman") -> np.ndarray:
    """A frame with the status bar's level digits and class line drawn from hud_glyphs.json."""
    g = json.loads(corpus.GLYPHS.read_text())
    pic = lambda text: np.array([[c == "#" for c in row] for row in text.split("/")])     # noqa: E731
    f = np.zeros((768, 1366, 3), np.uint8)
    for k, d in enumerate(level):
        m = pic(next(t for t, v in g["digits"].items() if v == d))
        box = f[744:757, 329 + 12 * k:329 + 12 * k + m.shape[1]]
        box[:] = (30, 120, 240)                              # orange (BGR)
        box[m] = 255
    m = pic(next(t for t, v in g["jobs"].items() if v == job))
    f[737:750, 370:370 + m.shape[1]][m] = 230
    return f


def test_the_class_and_level_are_read_off_the_status_bar():
    """The digits and the class line are compared with the pictures hud_glyphs.json holds; a stay's level is the
    one at its start, `level_to` the one it ends on; a frame without the bar (a loading screen) is passed over."""
    assert corpus.char_of(_bar("31")) == ("Spearman", 31) and corpus.char_of(_bar("133")) == ("Spearman", 133)
    blank = np.zeros((768, 1366, 3), np.uint8)
    assert corpus.char_of(blank) == (None, None)
    odd = _bar("31")
    odd[745, 331] = 255                                      # a digit drawn another way: not known, never guessed
    assert corpus.char_of(odd) == ("Spearman", None)
    frames = {0: blank, 30: _bar("31"), 60: _bar("31"), 90: _bar("33")}
    got = corpus.char_fields(frames.get, 0, 90)
    assert got == {"job": "Spearman", "level": 31, "level_to": 33}
    assert corpus.who(dict(got)) == "Spearman lv 31-33" and corpus.who({}) == ""
    assert corpus.char_fields(frames.get, 30, 60) == {"job": "Spearman", "level": 31}
