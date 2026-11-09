"""brain v3 world model (PLAN-v3.md step 1: objects over today's parts): Mob, Spawn, Map, Character, World."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from maplebrain.brain.v3.model import Character, Map, Mob, World
from maplebrain.nav.navmap import NavMap
from maplebrain.nav.selfstate import SelfState

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"


@pytest.fixture(scope="module")
def line1():
    return NavMap.for_map(10003061, ASSETS)


def test_mob_types_a_track_dict_with_the_brains_old_defaults():
    m = Mob({"id": 7, "mob": 14, "state": "hit", "x": 10.5, "y": 198.0, "vx": None, "platform": 273})
    assert (m.id, m.type, m.kind, m.state, m.platform) == (7, 14, "mob", "hit", 273)
    assert m.sx is None and m.sy is None and m.vx == 0.0 and m.unseen == 0 and m.src is None
    assert m.live and not m.dying
    assert Mob({"id": 1, "state": "dying", "x": 0, "y": 0}).dying


def test_map_spawns_know_their_platform_in_navmap_order(line1):
    mp = Map(line1)
    assert [(s.x, s.y) for s in mp.spawns] == list(line1.spawns)
    on = [s for s in mp.spawns if s.platform is not None]
    assert on and all(line1.platform_at(s.x, s.y, tol=12).id == s.platform for s in on)
    assert mp.platform(273) is line1.platforms[273] and mp.platform(-12345) is None


def test_route_seconds_cached_for_a_second_and_none_in_the_air(line1):
    mp = Map(line1)
    s = SelfState(0, 1400, 198, "tag", "ground", 273)
    c = mp.route_seconds(0.0, s, 79, 1700)
    assert c is not None and c > 0
    assert len(mp._routes) == 1 and mp.route_seconds(0.5, s, 79, 1700) == c and len(mp._routes) == 1
    assert mp.route_seconds(0.0, SelfState(0, 1400, 150, "tag", "air"), 79, 1700) is None


def test_character_is_selfstate_facing_and_hud():
    s = SelfState(0, 1400, 198, "tag", "ground", 273, vx=12.0)
    obs = SimpleNamespace(me=(683, 400), hp=0.5, mp=0.2, hp_now=500, mp_now=80, hp_potions=True, mp_potions=False)
    me = Character.of(s, -1, obs)
    assert (me.x, me.y, me.state, me.platform, me.vx, me.node, me.facing) == (1400, 198, "ground", 273, 12.0, 273, -1)
    assert (me.screen, me.hp_now, me.mp_now, me.mp_potions) == ((683, 400), 500, 80, False)


def test_world_update_wraps_every_track_and_reads_our_keys(line1):
    w = World(line1)
    obs = SimpleNamespace(me=None, mobs=[{"id": 1, "state": "live", "x": 1, "y": 2},
                                         {"id": 2, "state": "dying", "x": 3, "y": 4, "kind": "pet"}])
    w.update(1.0, obs, SelfState(1.0, 1400, 198, "tag", "ground", 273), SimpleNamespace(want={"left"}))
    assert [m.id for m in w.mobs] == [1, 2] and w.now == 1.0
    assert w.me.facing == -1 and w.me.platform == 273
