"""tools/nav/map_graph.py's 8-bit art (pixel_art): rings for platforms, 1 px lines for moves, half blocks."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "nav"))

from map_graph import BANNER, banner_file, map_positions, pixel_art, pixel_art_map  # noqa: E402

ROWS = [[1], [2, 3]]                                     # one platform on top, two below it


def test_pixel_art_draws_rings_and_lines():
    assert pixel_art(ROWS, [(1, 2), (1, 3)]) == [
        "        █▀█",
        "     ▄▄▀▀▀▀▀▄▄",
        " █▀█▀         ▀█▀█",
        " ▀▀▀           ▀▀▀",
    ]


def test_pixel_art_a_two_way_move_is_one_line():
    assert pixel_art(ROWS, [(1, 2), (2, 1), (1, 3)]) == pixel_art(ROWS, [(1, 2), (1, 3)])


def test_banner_file_is_the_short_map_name():
    assert banner_file("Henesys Hunting Ground I") == BANNER / "Henesys HG1.txt"
    assert banner_file("Kerning City Construction Site") == BANNER / "Kerning CS.txt"
    assert banner_file("Ant Tunnel IV") == BANNER / "Ant Tunnel 4.txt"
    assert banner_file("Line 1 <Area 1>") == BANNER / "Line 1 Area 1.txt"  # what Windows refuses is dropped


def test_pixel_art_without_moves_is_rings_only():
    assert pixel_art(ROWS, []) == ["        █▀█", "        ▀▀▀", " █▀█           █▀█", " ▀▀▀           ▀▀▀"]


def test_map_positions_keep_levels_order_and_distances():
    # three platforms on one floor (y 500), one above the middle one (y 300); a map 2800 px wide
    boxes = {1: (0, 400, 500), 2: (1000, 1400, 500), 3: (2400, 2800, 500), 4: (1100, 1300, 300)}
    pos, span, width, height = map_positions(boxes, top=150)
    assert pos[1][1] == pos[2][1] == pos[3][1] > pos[4][1]            # the same level stays level, up stays up
    assert pos[1][0] < pos[2][0] < pos[3][0]                          # the order along the map
    assert pos[4][0] == pos[2][0]                                     # straight above stays straight above
    s = (pos[3][0] - pos[1][0]) / 2400                                # one scale for x and y
    assert abs((pos[2][0] - pos[1][0]) - 1000 * s) < 1e-9 and abs((pos[2][1] - pos[4][1]) - 200 * s) < 1e-9
    assert span[2] == (pos[2][0] - 200 * s, pos[2][0] + 200 * s) and width == 1500 and height == 200 * s


def test_map_positions_never_enlarge_a_small_map():
    pos, _, width, _ = map_positions({1: (0, 100, 0), 2: (300, 400, 0)}, top=0)
    assert pos[2][0] - pos[1][0] == 300 and width == 1500


def test_pixel_art_map_keeps_levels_and_order():
    # two platforms on one floor at the map's two ends, one above the left one
    art = pixel_art_map({1: (0, 200, 400), 2: (2600, 2800, 400), 3: (0, 200, 200)}, [(1, 2), (1, 3)])
    assert art == [                                     # the upper one on top, the floor's two at its two ends
        " █▀█",
        " ███                                   ▄▄▄",
        " █▄█" + "▀" * 35 + "█▄█",
    ]
