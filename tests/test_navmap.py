"""Map geometry on Perion Street Corner (10004040), from its real map.json (assets/mcw/maps/10004040).
Ids are each platform's leftmost foothold: 54 = the ground floor (y 1905-2145), 71 = the long upper floor on the
left (y ~1570-1640), small 136 px platforms 148 (517-653, y 1785) / 186 (607-743, 1725) / 162 (787-923, 1725) /
174 (-203..-67, 1845)."""
from pathlib import Path

import pytest

from maplebot.config import Nav
from maplebot.nav.navmap import NavMap

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"


@pytest.fixture(scope="module")
def perion():
    return NavMap.for_map(10004040, ASSETS)


def kinds(route):
    return [(k.kind, k.dst) for k in route]


def test_ground_floor_is_one_platform_closed_at_the_map_edges(perion):
    g = perion.platforms[54]
    assert (g.left, g.right) == (-1373, 2543)
    assert not g.open_left and not g.open_right            # the map ends there: never "walk off"
    assert g.y_at(-1000) == 2025 and g.y_at(0) == 2145      # the dip in the middle
    assert g.y_at(-585) == pytest.approx(2055)              # down the slope (-630,2025)-(-540,2085)


def test_small_platform_ends_are_open_despite_the_stub_walls_under_them(perion):
    """Every small platform has 15 px walls hanging *below* its ends (517,1785-1800): we can walk off."""
    p = perion.platforms[148]
    assert (p.left, p.right, p.y_at(600)) == (517, 653, 1785)
    assert p.open_left and p.open_right


def test_platform_at_picks_the_surface_under_our_feet(perion):
    assert perion.platform_at(-144, 1840).id == 174          # perion5's start, on the small platform
    assert perion.platform_at(-144, 2140).id == 54           # same x, ground floor
    assert perion.platform_at(-144, 1990) is None            # in between: in the air / on a rope


def test_drop_lands_on_the_first_floor_below(perion):
    links = {(k.kind, k.dst) for k in perion.links_from(71) if k.lo <= -144 <= k.hi}
    assert ("drop", 174) in links and ("drop", 54) not in links   # the small platform is in the way
    assert perion.below(0, 1570).id == 54


def test_jump_straight_up_onto_a_platform_60px_above(perion):
    up = [k for k in perion.links_from(148) if k.kind == "jump" and k.dir == 0 and k.dst == 186]
    assert up and up[0].lo <= 630 <= up[0].hi                 # 148 and 186 overlap on 607-653


def test_no_jump_from_the_ground_floor_everything_is_180px_up(perion):
    assert not [k for k in perion.links_from(54) if k.kind == "jump"]


def test_walking_jump_across_a_44px_gap(perion):
    """186 (607-743) and 162 (787-923) at the same height: jump right from 186's right part."""
    across = [k for k in perion.links_from(186) if k.kind == "jump" and k.dst == 162]
    assert across and all(k.dir == 1 for k in across)


def test_walking_off_an_edge_is_a_fall_to_the_floor_below(perion):
    falls = {(k.dir, k.dst) for k in perion.links_from(148) if k.kind == "fall"}
    assert falls == {(-1, 54), (1, 54)}


def rope(m, x):
    return next(m.rope_id(i) for i, r in enumerate(m.ropes) if r.x == x)


def test_ropes_from_the_ground(perion):
    """Rope x -124 (y 1847-2100) hangs 45 px over the ground and ends at platform 174's surface (1845):
    grab it from the ground, exit at the top onto 174; from 174 climb down it and let go onto the ground."""
    r = rope(perion, -124)
    assert perion.is_rope(r) and perion.rope(r).x == -124
    grab = [k for k in perion.links_from(54) if k.kind == "grab" and k.dst == r]
    assert grab and grab[0].lo <= -124 <= grab[-1].hi
    assert [(k.kind, k.dst) for k in perion.links_from(r) if k.kind in ("exit", "let_go")] == \
        [("exit", 174), ("let_go", 54)]
    assert any(k.kind == "descend" and k.dst == r for k in perion.links_from(174))
    assert perion.rope_at(470, 1900).x == 470                # recorded runs: our dot sat on this rope


def test_rope_moves_seen_live_are_links(perion):
    """runs/jump/20261101_234718_2: the user went rope to rope across the middle of Perion, jumped from platforms
    onto ropes beside them and off ropes onto platforms (pos = take-off: x on a platform, y on a rope; minimap
    16 px steps). -492 -> -355 and -25 -> 151 were two leaps each (0.1 s on -422 / 54 in between)."""
    R = lambda x: rope(perion, x)  # noqa: E731
    seen = [(54, R(-980), -1048), (R(-492), R(-422), 1776), (R(-422), R(-355), 1800), (R(-355), R(-275), 1856),
            (R(-275), 174, 1840), (174, R(-25), -104), (R(-25), R(54), 1744), (R(54), R(151), 1760),
            (R(151), R(252), 1792), (R(252), R(362), 1824), (R(362), R(470), 1872), (R(470), 148, 1776),
            (162, R(920), 904), (R(920), 54, 1664), (54, R(1808), 1768), (R(1808), 152, 1680), (R(-980), 199, 1664)]
    for a, b, p in seen:
        assert [k for k in perion.links_from(a) if k.dst == b and k.lo - 24 <= p <= k.hi + 24], (a, b, p)


def test_every_platform_and_rope_is_reachable_from_the_ground(perion):
    seen, todo = {54}, [54]
    while todo:
        for k in perion.links_from(todo.pop()):
            if k.dst not in seen:
                seen.add(k.dst)
                todo.append(k.dst)
    assert set(perion.platforms) <= seen
    usable = {perion.rope_id(i) for i, r in enumerate(perion.ropes)} & seen
    assert len(usable) >= 20                                 # most of the 28 ropes, incl. the middle ones


def test_route_up_the_small_platform_stair(perion):
    r = perion.route(148, 600, 162)
    assert kinds(r) == [("jump", 186), ("jump", 162)]
    assert r[0].dir in (0, 1) and r[1].dir == 1             # straight up or a walking jump right: both land


def test_route_from_ground_climbs_a_rope(perion):
    r = perion.route(54, 1500, 83)
    assert r[0].kind == "grab" and r[-1].kind == "exit" and r[-1].dst == 83


def test_route_across_the_middle_ropes_like_the_user(perion):
    """174 -> 148: grab -25 beside the platform, leap rope to rope to 470, leap off onto 148."""
    r = perion.route(174, -150, 148)
    assert r[0].kind == "grab" and r[-1].kind == "leap" and r[-1].dst == 148
    assert all(k.kind == "leap" for k in r[1:])


def test_route_from_a_rope(perion):
    r = perion.route(rope(perion, -124), 1950, 174)
    assert kinds(r) == [("exit", 174)]


def test_route_down_is_a_single_drop(perion):
    assert kinds(perion.route(71, 0, 54)) == [("drop", 54)]
    assert perion.route(54, 0, 54) == []


def test_lower_jump_height_removes_the_60px_jumps():
    m = NavMap.for_map(10004040, ASSETS, Nav(jump_height=50))
    assert not [k for k in m.links_from(148) if k.kind == "jump" and k.dst == 186]


def tiny(footholds, ropes=()):
    fh = {}
    for i, (x1, y1, x2, y2, prev, nxt) in enumerate(footholds, 1):
        fh[str(i)] = {"id": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "prev": prev, "next": nxt, "groupId": 0}
    return NavMap.from_json({"footholds": fh, "ladderRopes": [dict(r) for r in ropes]})


def test_a_wall_rising_above_the_surface_closes_that_end():
    """Floor 0-100 at y 500 with a wall going up at x 100; a second floor 300-400 far right defines the map edge."""
    m = tiny([(0, 500, 100, 500, 0, 2), (100, 500, 100, 400, 1, 0), (300, 500, 400, 500, 0, 0)])
    a = m.platforms[1]
    assert not a.open_left                                   # map edge
    assert not a.open_right                                  # the wall
    assert m.platforms[3].open_left


def test_a_ceiling_segment_is_not_a_floor():
    m = tiny([(0, 500, 100, 500, 0, 0), (100, 450, 0, 450, 0, 0)])   # x1 > x2: underside
    assert list(m.platforms) == [1]


def test_walking_jumps_seen_live_are_links(perion):
    """runs/jump/20261101_234718_2: the user's jumps between platforms (x = take-off on the minimap, 16 px steps).
    Left out as ambiguous: '130 -> 191' at x -968 (130 and 199 overlap there only 19 px apart - most likely 199, then
    off its right edge onto 191) and '113 -> 127' at -760 (ledges 113/121/124/127 stacked 20-35 px apart)."""
    seen = [(191, 199, -856), (199, 130, -920), (191, 4, -856), (4, 191, -776), (130, 128, -936),
            (124, 113, -792), (148, 186, 568), (186, 162, 728)]
    for a, b, x in seen:
        assert [k for k in perion.links_from(a) if k.dst == b and k.lo - 20 <= x <= k.hi + 20], (a, b, x)
