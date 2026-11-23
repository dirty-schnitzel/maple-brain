"""tools/nav/map_graph.py's 8-bit art (pixel_art): rings for platforms, 1 px lines for moves, half blocks."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "nav"))

from map_graph import pixel_art  # noqa: E402

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


def test_pixel_art_without_moves_is_rings_only():
    assert pixel_art(ROWS, []) == ["        █▀█", "        ▀▀▀", " █▀█           █▀█", " ▀▀▀           ▀▀▀"]
