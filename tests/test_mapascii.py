from maplebrain.perception.mapascii import render

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


def test_marked_platforms_are_drawn_with_stars():
    out = render(M, marked=[(0, 100, 300, 100)], width=31)
    assert any("*" * 25 in r for r in out.splitlines()) and not any("=" * 25 in r for r in out.splitlines())


def test_livemap_shows_the_platforms_marked_in_the_hunts_log(tmp_path):
    from maplebrain.livemap import View
    run = tmp_path / "20261109_120000_1"
    run.mkdir()
    (run / "log.txt").write_text("map 10003061 Victoria Road / Line 1 <Area 1>\nmarked platforms 79\n", encoding="utf-8")
    v = View(10003061, 160)
    assert "*" in v.frame({"n": 1, "obs": {"t": 0.0}}, run)
    plain = tmp_path / "20261109_120500_2"
    plain.mkdir()
    (plain / "log.txt").write_text("map 10003061 Victoria Road / Line 1 <Area 1>\n", encoding="utf-8")
    assert "*" not in v.frame({"n": 1, "obs": {"t": 0.0}}, plain).split("\n", 2)[2]
