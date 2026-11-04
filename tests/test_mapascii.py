from maplebot.perception.mapascii import render

M = {"footholds": {"1": {"x1": 0, "y1": 100, "x2": 300, "y2": 100},
                   "2": {"x1": 300, "y1": 100, "x2": 300, "y2": 200},
                   "3": {"x1": 100, "y1": 40, "x2": 200, "y2": 0}},
     "ladderRopes": [{"x": 150, "y1": 20, "y2": 100, "isLadder": True}],
     "portals": [{"x": 10, "y": 100, "toMap": 5}, {"x": 20, "y": 100, "toMap": 999999999}],
     "mobs": [{"x": 250, "y": 100}]}


def test_render_draws_floors_walls_slopes_ladders_portals_and_marks():
    out = render(M, marks=[("@", 60, 100)], screen=(0, 150), width=31)
    rows = out.splitlines()
    assert any("=" * 25 in r for r in rows)
    assert any("#" in r for r in rows) and any("/" in r for r in rows) and any("H" in r for r in rows)
    assert sum(r.count("O") for r in rows) == 1                 # spawn-point portals ('sp', no map) aren't drawn
    floor = next(i for i, r in enumerate(rows) if "=" * 25 in r)
    assert "@" in rows[floor - 1] and "." in rows[floor - 1]   # marks sit just above their feet
    assert rows[-2].startswith("[") and "]" in rows[-2]
