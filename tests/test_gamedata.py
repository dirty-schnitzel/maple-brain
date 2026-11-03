"""assets/mcw built from the client export (maplebot/gamedata.py): a tiny fake export in the exporter's XML + PNG
layout, then the real assets (the client's own data, built 2026-11-03)."""
import base64
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebot import gamedata
from maplebot.nav.localize import MinimapLocator
from maplebot.nav.navmap import NavMap
from maplebot.perception.sprites import SpriteDetector

MCW = Path(__file__).resolve().parents[1] / "assets" / "mcw"

MAP42 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<imgdir name="000000042.img">
 <imgdir name="info">
  <float name="mobRate" value="1.0"/><int name="town" value="0"/><int name="returnMap" value="60"/>
  <int name="VRTop" value="-1045"/><int name="VRLeft" value="-299"/><int name="VRBottom" value="585"/>
  <int name="VRRight" value="2909"/>
 </imgdir>
 <imgdir name="life">
  <imgdir name="0"><string name="type" value="m"/><string name="id" value="0000002"/><int name="x" value="100"/>
   <int name="y" value="49"/><int name="fh" value="1"/><int name="cy" value="100"/><int name="rx0" value="0"/>
   <int name="rx1" value="400"/></imgdir>
  <imgdir name="1"><string name="type" value="m"/><string name="id" value="0000003"/><int name="x" value="300"/>
   <int name="y" value="51"/><int name="fh" value="2"/><int name="cy" value="100"/><int name="rx0" value="0"/>
   <int name="rx1" value="400"/><int name="hide" value="1"/><int name="mobTime" value="300"/></imgdir>
  <imgdir name="2"><string name="type" value="n"/><string name="id" value="2000"/><int name="x" value="50"/>
   <int name="y" value="100"/><int name="fh" value="1"/><int name="cy" value="100"/><int name="rx0" value="40"/>
   <int name="rx1" value="60"/><int name="f" value="1"/></imgdir>
 </imgdir>
 <imgdir name="foothold">
  <imgdir name="1">
   <imgdir name="7">
    <imgdir name="1"><int name="x1" value="0"/><int name="y1" value="100"/><int name="x2" value="200"/>
     <int name="y2" value="100"/><int name="prev" value="0"/><int name="next" value="2"/><int name="piece" value="0"/></imgdir>
    <imgdir name="2"><int name="x1" value="200"/><int name="y1" value="100"/><int name="x2" value="400"/>
     <int name="y2" value="100"/><int name="prev" value="1"/><int name="next" value="0"/><int name="piece" value="0"/></imgdir>
   </imgdir>
  </imgdir>
  <imgdir name="3">
   <imgdir name="9">
    <imgdir name="5"><int name="x1" value="100"/><int name="y1" value="-50"/><int name="x2" value="300"/>
     <int name="y2" value="-50"/><int name="prev" value="0"/><int name="next" value="0"/><int name="piece" value="0"/>
     <int name="forbidFallDown" value="1"/></imgdir>
   </imgdir>
  </imgdir>
 </imgdir>
 <imgdir name="ladderRope">
  <imgdir name="1"><int name="l" value="1"/><int name="uf" value="1"/><int name="x" value="150"/>
   <int name="y1" value="-50"/><int name="y2" value="90"/><int name="page" value="2"/><int name="piece" value="0"/></imgdir>
  <imgdir name="2"><int name="l" value="0"/><int name="uf" value="1"/><int name="x" value="250"/>
   <int name="y1" value="-50"/><int name="y2" value="90"/><int name="page" value="2"/><int name="piece" value="0"/></imgdir>
 </imgdir>
 <imgdir name="miniMap">
  <canvas name="canvas" width="1" height="1">
   <string name="_outlink" value="Map/Map/Map0/_Canvas/000000042.img/miniMap/canvas"/>
  </canvas>
  <int name="width" value="3208"/><int name="height" value="1630"/><int name="centerX" value="299"/>
  <int name="centerY" value="1045"/><int name="mag" value="4"/>
 </imgdir>
 <imgdir name="portal">
  <imgdir name="0"><string name="pn" value="sp"/><int name="pt" value="0"/><int name="x" value="1"/>
   <int name="y" value="90"/><int name="tm" value="999999999"/><string name="tn" value=""/></imgdir>
  <imgdir name="1"><string name="pn" value="east00"/><int name="pt" value="2"/><int name="x" value="390"/>
   <int name="y" value="90"/><int name="tm" value="41"/><string name="tn" value="west00"/></imgdir>
 </imgdir>
</imgdir>
"""


def canvas(name, w, h, ox, oy, delay=None):
    d = f'<int name="delay" value="{delay}"/>' if delay else ""
    return (f'<canvas name="{name}" width="{w}" height="{h}"><vector name="origin" x="{ox}" y="{oy}"/>'
            f'<vector name="lt" x="{-ox}" y="{-oy}"/><vector name="rb" x="{w - ox}" y="0"/>{d}'
            f'<string name="_hash" value="ab"/></canvas>')


SNAIL = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<imgdir name="0000002.img">
 <imgdir name="info"><int name="level" value="1"/><int name="maxHP" value="45"/><int name="speed" value="-65"/>
  <int name="pushed" value="1"/><float name="fs" value="10.0"/></imgdir>
 <imgdir name="move"><int name="zigzag" value="1"/>{canvas(0, 6, 4, 3, 4, 180)}<uol name="1" value="../stand/0"/>
  {canvas(2, 6, 5, 3, 5, 180)}</imgdir>
 <imgdir name="stand">{canvas(0, 5, 4, 2, 4)}{canvas(3, 5, 3, 2, 3)}</imgdir>
</imgdir>
"""

BLUE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<imgdir name="0000003.img"><imgdir name="info"><int name="level" value="2"/><string name="link" value="0000002"/>
</imgdir></imgdir>
"""

NAMES_MAP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<imgdir name="Map.img"><imgdir name="MapleIsland"><imgdir name="000000042">
 <string name="streetName" value="Maple Road"/><string name="mapName" value="Snail Hunting Ground III"/>
</imgdir></imgdir></imgdir>
"""

NAMES_MOB = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<imgdir name="Mob.img"><imgdir name="2"><string name="name" value="Snail"/></imgdir>
<imgdir name="3"><string name="name" value="Blue Snail"/></imgdir></imgdir>
"""


def png(path: Path, w: int, h: int, colour) -> bytes:
    im = np.zeros((h, w, 4), np.uint8)
    im[...] = (*colour, 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", im)[1].tofile(str(path))
    return path.read_bytes()


@pytest.fixture
def export(tmp_path):
    e = tmp_path / "export"
    for rel, text in (("Map/Map0/000000042.img.xml", MAP42), ("Mob/0000002.img.xml", SNAIL),
                      ("Mob/0000003.img.xml", BLUE), ("String/Map.img.xml", NAMES_MAP),
                      ("String/Mob.img.xml", NAMES_MOB)):
        (e / rel).parent.mkdir(parents=True, exist_ok=True)
        (e / rel).write_text(text, encoding="utf-8")
    (e / "Mob/pack_ignore.txt.xml").write_text("<imgdir/>", encoding="utf-8")       # the pack has one: not a mob
    png(e / "Map/minimap/000000042.png", 20, 10, (10, 20, 30))
    for name, w, h, c in (("move_0", 6, 4, (0, 0, 250)), ("move_2", 6, 5, (0, 0, 240)), ("stand_0", 5, 4, (0, 0, 230)),
                          ("stand_3", 5, 3, (0, 0, 220))):   # saturated red: the detector needs a hue
        png(e / f"Mob/png/0000002/{name}.png", w, h, c)
    return e


@pytest.fixture
def built(export, tmp_path):
    root = tmp_path / "mcw"
    gamedata.build(export, root, log=lambda *_: None)
    return root


def mapj(root, i=42):
    return json.loads((root / f"maps/{i}/map.json").read_text(encoding="utf-8"))


def mobj(root, i):
    return json.loads((root / f"mobs/{i}/mob.json").read_text(encoding="utf-8"))


def test_map_json_has_what_the_bot_reads(built):
    m = mapj(built)
    assert (m["id"], m["name"], m["streetName"]) == (42, "Snail Hunting Ground III", "Maple Road")
    assert set(m["footholds"]) == {"1", "2", "5"}
    assert m["footholds"]["5"] == {"id": 5, "x1": 100, "y1": -50, "x2": 300, "y2": -50, "prev": 0, "next": 0,
                                   "piece": 0, "forbidFallDown": 1, "layerId": 3, "groupId": 9}
    assert [(r["x"], r["y1"], r["y2"], r["isLadder"]) for r in m["ladderRopes"]] == [(150, -50, 90, True),
                                                                                      (250, -50, 90, False)]
    assert m["vrBounds"] == {"left": -299, "top": -1045, "right": 2909, "bottom": 585}
    assert (m["mobRate"], m["isTown"], m["returnMap"]) == (1.0, False, 60)


def test_spawn_y_is_the_ground_under_it(built):
    """life's `cy` (the foothold under the spawn) is the spawn's y, as the bot has always read it; the client's
    `y` (where the sprite is first drawn) is kept as spriteY. rx0/rx1 = the mob's walk area."""
    mobs = mapj(built)["mobs"]
    assert [(v["id"], v["x"], v["y"], v["spriteY"], v["hidden"]) for v in mobs] == [(2, 100, 100, 49, False),
                                                                                   (3, 300, 100, 51, True)]
    assert (mobs[0]["walkAreaX1"], mobs[0]["walkAreaX2"], mobs[0]["footholdId"]) == (0, 400, 1)
    assert (mobs[0]["mobTime"], mobs[1]["mobTime"]) == (0, 300)
    assert [(n["id"], n["flip"]) for n in mapj(built)["npcs"]] == [(2000, True)]


def test_portals_all_kept(built):
    """maplestory.io dropped every portal with a destination (502 of them came back as null)."""
    assert [(p["portalName"], p["type"], p["toMap"], p["toName"]) for p in mapj(built)["portals"]] == [
        ("sp", 0, 999999999, ""), ("east00", 2, 41, "west00")]


def test_minimap_picture_and_fields(built, export):
    mm = mapj(built)["miniMap"]
    pic = (export / "Map/minimap/000000042.png").read_bytes()
    assert (mm["centerX"], mm["centerY"], mm["width"], mm["height"], mm["magnification"]) == (299, 1045, 3208, 1630, 4)
    assert base64.b64decode(mm["canvas"]) == pic
    assert (built / "maps/42/minimap.png").read_bytes() == pic


def test_mob_frames_resolve_links_and_renumber(built, export):
    """move/1 is a UOL to stand/0 (the client reuses the picture); stand's frames are numbered 0, 3 in the client:
    files are 0..count-1 in play order, the client's number stays in mob.json."""
    m = mobj(built, 2)
    assert (m["id"], m["name"], m["link"]) == (2, "Snail", None)
    assert m["framebooks"] == {"move": 3, "stand": 2}
    assert sorted(p.name for p in (built / "mobs/2").glob("*.png")) == [
        "move_0.png", "move_1.png", "move_2.png", "stand_0.png", "stand_1.png"]
    src = export / "Mob/png/0000002"
    assert (built / "mobs/2/move_1.png").read_bytes() == (src / "stand_0.png").read_bytes()
    assert (built / "mobs/2/stand_1.png").read_bytes() == (src / "stand_3.png").read_bytes()
    f = m["frames"]
    assert f["move"][1] == {"n": 1, "file": "move_1.png", "size": [5, 4], "origin": [2, 4], "lt": [-2, -4],
                            "rb": [3, 0], "head": None, "delay": None, "same": "stand_0.png"}
    assert (f["move"][0]["origin"], f["move"][0]["delay"]) == ([3, 4], 180)
    assert (f["stand"][1]["n"], f["stand"][1]["file"]) == (3, "stand_1.png")
    assert m["info"] == {"level": 1, "maxHP": 45, "speed": -65, "pushed": 1, "fs": 10.0}


def test_linked_mob_is_drawn_with_the_linked_mobs_frames(built):
    m = mobj(built, 3)
    assert (m["name"], m["link"], m["info"]["level"]) == ("Blue Snail", 2, 2)
    assert m["framebooks"] == {"move": 3, "stand": 2}
    assert (built / "mobs/3/move_2.png").read_bytes() == (built / "mobs/2/move_2.png").read_bytes()


def test_manifest(built):
    man = gamedata.load_manifest(built)
    assert set(man["mobs"]) == {"2", "3"}
    assert man["maps"]["42"] == {"name": "Snail Hunting Ground III", "street": "Maple Road", "mobs": [2, 3],
                                 "footholds": 3, "ladderRopes": 2, "minimap": True}
    assert man["mobs"]["3"]["link"] == 2 and man["mobs"]["2"]["frames"] == 5
    assert gamedata.have_map(42, built) and not gamedata.have_map(41, built)


def test_the_bot_loads_a_built_map(built):
    """What the runner does with --map: sprites, platforms, minimap locator."""
    det = SpriteDetector.for_map(42, built)
    assert [m.name for m in det.mobs] == ["Snail", "Blue Snail"]
    nav = NavMap.for_map(42, built)
    assert len(nav.platforms) == 2 and len(nav.ropes) == 2
    assert nav.spawns == [(100.0, 100.0)]                   # the hidden spawn is left out
    loc = MinimapLocator.for_map(42, built)
    assert loc.canvas.shape == (10, 20, 3) and loc.scale == 16


def test_rebuild_reports_changes_and_drops_stale_files(export, built):
    """After a game patch: re-export, rebuild - changes.txt says what to look at again; nothing old lingers."""
    assert (built / "changes.txt").read_text(encoding="utf-8").splitlines()[1] == "first build (nothing to compare with)"
    (built / "maps/42/render.png").write_bytes(b"old")                  # a file the new build doesn't make
    x = export / "Mob/0000002.img.xml"
    x.write_text(x.read_text(encoding="utf-8").replace('"maxHP" value="45"', '"maxHP" value="50"'), encoding="utf-8")
    png(export / "Map/minimap/000000042.png", 20, 10, (99, 20, 30))
    gamedata.build(export, built, log=lambda *_: None)
    report = (built / "changes.txt").read_text(encoding="utf-8").splitlines()[1:]
    assert report == ["map 42 Snail Hunting Ground III: miniMap; pictures minimap.png, render.png",
                      "mob 2 Snail: maxHP 45 -> 50"]
    assert not (built / "maps/42/render.png").exists()
    assert not built.with_name("mcw.new").exists() and not built.with_name("mcw.old").exists()
    gamedata.build(export, built, log=lambda *_: None)
    assert (built / "changes.txt").read_text(encoding="utf-8").splitlines()[1:] == ["no changes"]


def test_no_export_leaves_the_assets_alone(tmp_path, built):
    with pytest.raises(FileNotFoundError, match="export.ps1"):
        gamedata.build(tmp_path / "nothing", built, log=lambda *_: None)
    assert gamedata.have_map(42, built)


@pytest.mark.skipif(not (MCW / "manifest.json").exists(), reason="needs assets/mcw")
def test_real_assets_come_from_the_client():
    man = gamedata.load_manifest(MCW)
    assert "client" in man["source"]
    assert len(man["maps"]) >= 336 and len(man["mobs"]) >= 117
    snail = mobj(MCW, 2)
    assert snail["info"]["speed"] == -65 and snail["framebooks"] == {"move": 5, "stand": 1, "hit1": 1, "die1": 9}
    # what maplestory.io never had: where the feet are in each picture, the body box, how long a frame shows
    f = snail["frames"]["move"][0]
    assert (f["size"], f["origin"], f["lt"], f["rb"], f["delay"]) == ([37, 26], [18, 26], [-18, -26], [19, 0], 180)
    m = mapj(MCW, 42)
    assert m["name"] == "Snail Hunting Ground III" and len(m["mobs"]) == 42
    assert all(p["portalName"] for p in m["portals"])
