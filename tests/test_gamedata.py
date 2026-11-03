import base64
import json

import pytest

from maplebot import gamedata

PNG = b"\x89PNG fake"


class FakeApi:
    def __init__(self):
        self.calls = []
        self.maps = {42: {"name": "Snail Hunting Ground III", "streetName": "Maple Road",
                          "mobs": [{"id": 2}, {"id": 3}, {"id": 2}],
                          "footholds": {"1": {}, "2": {}}, "ladderRopes": [{}],
                          "miniMap": {"canvas": base64.b64encode(b"MINI").decode()}},
                     41: {"name": "Snail Hunting Ground II", "streetName": "Maple Road",
                          "mobs": [{"id": 2}], "footholds": {}, "ladderRopes": [], "miniMap": {}}}
        self.mobs = {2: {"name": "Snail", "meta": {"level": 1}, "framebooks": {"move": 2, "stand": 1}},
                     3: {"name": "Blue Snail", "meta": {"level": 2}, "framebooks": {"hit1": 1}}}

    def __call__(self, url):
        self.calls.append(url)
        path = url.split("/MCW/1/")[1].split("/")
        if path[0] == "map":
            return PNG if len(path) > 2 else json.dumps(self.maps[int(path[1])]).encode()
        if path[0] == "mob":
            return PNG if len(path) > 2 else json.dumps(self.mobs[int(path[1])]).encode()
        raise AssertionError(url)


@pytest.fixture
def api():
    return FakeApi()


def test_fetch_map_saves_map_minimap_and_every_mob_frame(tmp_path, api):
    gamedata.fetch_map(42, tmp_path, api, log=lambda *_: None)
    assert json.loads((tmp_path / "maps/42/map.json").read_text(encoding="utf-8"))["name"] == "Snail Hunting Ground III"
    assert (tmp_path / "maps/42/minimap.png").read_bytes() == b"MINI"
    assert not (tmp_path / "maps/42/render.png").exists()
    assert sorted(p.name for p in (tmp_path / "mobs/2").glob("*.png")) == ["move_0.png", "move_1.png", "stand_0.png"]
    assert [p.name for p in (tmp_path / "mobs/3").glob("*.png")] == ["hit1_0.png"]
    man = gamedata.load_manifest(tmp_path)
    assert man["region"] == "MCW" and man["version"] == "1"
    assert man["maps"]["42"]["mobs"] == [2, 3]
    assert man["maps"]["42"]["footholds"] == 2 and man["maps"]["42"]["ladderRopes"] == 1
    assert man["mobs"]["2"]["name"] == "Snail" and man["mobs"]["2"]["frames"] == 3


def test_second_map_reuses_mobs_already_downloaded(tmp_path, api):
    gamedata.fetch_map(42, tmp_path, api, log=lambda *_: None)
    api.calls.clear()
    gamedata.fetch_map(41, tmp_path, api, log=lambda *_: None)
    assert api.calls == [gamedata._url("map/41")]
    assert set(gamedata.load_manifest(tmp_path)["maps"]) == {"41", "42"}


def test_force_downloads_again(tmp_path, api):
    gamedata.fetch_map(41, tmp_path, api, log=lambda *_: None)
    api.calls.clear()
    gamedata.fetch_map(41, tmp_path, api, force=True, render=True, log=lambda *_: None)
    assert gamedata._url("map/41/render") in api.calls
    assert len([c for c in api.calls if "/render/" in c]) == 3


def test_ensure_map_downloads_a_new_map_once(tmp_path, api):
    """Any map works with just --map <id>: the first run fetches it, later runs don't touch the network."""
    assert gamedata.ensure_map(42, tmp_path, api, log=lambda *_: None) is True
    n = len(api.calls)
    assert gamedata.have_map(42, tmp_path)
    assert gamedata.ensure_map(42, tmp_path, api, log=lambda *_: None) is False
    assert len(api.calls) == n


def test_ensure_map_fetches_again_when_a_mob_is_missing(tmp_path, api):
    gamedata.ensure_map(42, tmp_path, api, log=lambda *_: None)
    (tmp_path / "mobs/3/mob.json").unlink()
    assert not gamedata.have_map(42, tmp_path)
    assert gamedata.ensure_map(42, tmp_path, api, log=lambda *_: None) is True
    assert gamedata.have_map(42, tmp_path)
