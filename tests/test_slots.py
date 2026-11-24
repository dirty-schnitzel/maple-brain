"""The hotkey reader (perception/slots.py) and the amounts tracked in track/us.py (PLAN-tracker step 7).
Fixtures: tests/fixtures/slots/*.png = the bar's 151 x 114 px (its corner at frame (933, 588)) cut losslessly from
two captures of the bank: line1_100 = 20261121_000219_2#0 frame 100, quick_* = 20261124_093410_1#0 (the quickslot
footage: a skill on Ctrl, the cursor and tooltips over the bar)."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebrain.perception import slots as S
from maplebrain.track.us import Slots, Us

FX = Path(__file__).parent / "fixtures" / "slots"


def frame_of(name: str) -> np.ndarray:
    """A native 1366 x 768 frame, black, with the fixture's bar in its place."""
    bar = cv2.imread(str(FX / f"{name}.png"))
    f = np.zeros((768, 1366, 3), np.uint8)
    f[S.BY:S.BY + bar.shape[0], S.BX:S.BX + bar.shape[1]] = bar
    return f


def said(p, r) -> str | None:
    if not r.exact:
        return None
    if r.kind == "empty":
        return "empty"
    return p.name(r.cls) + ("" if r.amount is None else f" {r.amount}")


@pytest.fixture(scope="module")
def p():
    return S.pack()


@pytest.mark.parametrize("rows", [2, 3])
def test_every_client_picture_reads_back_as_itself(rows):
    """Every item / skill / action picture drawn into a cell the way the client does (keycap, content, an amount, a
    key label) is read back as itself - or as a picture identical under the label or digits (`alts`); every key
    label on an empty keycap reads as its key. The gate's self-test."""
    p = S.Pack(rows)
    rng = np.random.default_rng(7)
    K = len(p.cells)
    wrong = []
    for cls in range(len(p.content)):
        k, li = int(rng.integers(K)), int(rng.integers(len(p.lab_key)))
        digs, amount = [], None
        if p.member(cls)["kind"] == "item":
            amount = int(rng.choice([0, 1, 9, 47, 100, 288, 1111]))
            x = 0
            for ch in str(amount):
                digs.append((int(ch), x))
                x += p.dg_w[int(ch)]
        r, _ = p.read_cell(p.expect(k, cls, digs, li), k)
        if cls not in (r.cls,) + r.alts or r.amount != amount or r.key != p.lab_key[li]:
            wrong.append((cls, r))
    assert wrong == []
    for li in range(len(p.lab_key)):
        r, _ = p.read_cell(p.expect(0, -1, [], li), 0)
        assert (r.kind, r.key) == ("empty", p.lab_key[li])
    assert ["0", "o"] in [[p.lab_key[i]] + a for i, a in enumerate(p.lab_also) if a]   # one picture, two keys


def test_the_bars_of_two_captures(p):
    want = {"line1_100": ["JUMP", "Pet Food 100", "empty", "The Green Relaxer", "empty", "Meat 200", "Lemon 130",
                          "Red Potion 276"],
            "quick_100": ["JUMP", "Orange Potion 1", "empty", "The Green Relaxer", "Power Strike", "Meat 178",
                          "Lemon 57", "Red Potion 288"]}
    for name, w in want.items():
        reads = S.read_slots(frame_of(name), p)
        assert [r.key for r in reads] == list(S.DEFAULT_KEYS[2])
        assert [said(p, r) for r in reads] == w
    ctrl = S.read_slots(frame_of("quick_100"), p)[4]
    assert (ctrl.kind, ctrl.id) == ("skill", 1001001)
    assert S.bar_rows(frame_of("line1_100")) == 2


def test_an_amount_of_0_and_what_lies_over_the_bar(p):
    """The last Orange Potion used: its picture stays with "0". The cursor over a cell, an item dragged over the bar,
    a skill's tooltip: those cells are not readable (never another item); the rest are read."""
    reads = S.read_slots(frame_of("quick_3460_cursor"), p)
    assert said(p, reads[1]) == "Orange Potion 0"
    assert not reads[0].exact and reads[0].key is None                      # the cursor over Shift
    assert [said(p, r) for r in reads[1:]] == ["Orange Potion 0", "empty", "The Green Relaxer", "Power Strike",
                                               "Meat 176", "Lemon 56", "Red Potion 279"]
    assert [r.exact for r in S.read_slots(frame_of("quick_3940_tooltip"), p)] == [False] * 8
    drag = S.read_slots(frame_of("quick_3560_drag"), p)
    assert [i for i, r in enumerate(drag) if r.exact] == [0, 4]             # Shift and Ctrl only
    assert [said(p, drag[i]) for i in (0, 4)] == ["JUMP", "Power Strike"]


def test_the_reader_reads_a_cell_again_only_when_it_changed(p):
    rd = S.SlotReader(p)
    seq = ["quick_100", "quick_100", "quick_3460_cursor", "quick_3940_tooltip", "quick_100", "quick_3830_cursor"]
    for i, name in enumerate(seq):
        f = frame_of(name)
        before = rd.reads
        now = rd.update(f)
        scratch = S.read_slots(f, p)
        assert [(r.key, r.kind, r.id, r.amount) for r in now] == [(r.key, r.kind, r.id, r.amount) for r in scratch]
        if i == 1:
            assert rd.reads == before                                       # the same frame: nothing read
    assert rd.reads < 8 * len(seq)


def test_a_label_alone_is_no_proof():
    """Something over the right part of the Shift cell (the cursor did it in the quickslot footage, frame 3456):
    "Shift" no longer fits, but "S" - its first letter, the same pixels - does. The cell is not readable and has no
    key; the facts keep filing it under "shift"; once uncovered it reads as Shift again (a label taken from that
    read as the next read's hint kept the cell unreadable for the rest of the footage)."""
    p = S.pack()
    rd = S.SlotReader(p)
    f = frame_of("line1_100")
    rd.update(f)
    x, y = p.cells[0]
    g = f.copy()
    g[y:y + S.CELL, x + 12:x + S.CELL] = 0
    lab = p._label(S._key32(g[y:y + S.CELL, x:x + S.CELL]), None)
    assert p.lab_key[lab] == "s"                                            # the trap is real
    r = rd.update(g)[0]
    assert not r.exact and r.key is None
    assert list(rd.facts()) == list(S.DEFAULT_KEYS[2])
    assert rd.facts()["shift"] is None
    r = rd.update(f)[0]
    assert (r.key, r.kind, r.id) == ("shift", "action", 53)


def test_facts_name_every_key():
    rd = S.SlotReader()
    rd.update(frame_of("quick_100"))
    assert rd.facts() == {"shift": ["action", 53, None], "insert": ["item", 2000001, 1], "home": ["empty", None, None],
                          "pageup": ["item", 3010000, None], "ctrl": ["skill", 1001001, None],
                          "delete": ["item", 2010003, 178], "end": ["item", 2010005, 57],
                          "pagedown": ["item", 2000000, 288]}


def test_us_tracks_the_amounts():
    """A step of the same item = an event with `d`; an unreadable key keeps its last reading (seen False); another
    content = an event without `d`; a key appears when first read."""
    s = Slots()
    assert s.update({"end": ["item", 2010005, 57], "home": None}, 1.0) == []
    assert "home" not in s.keys and s.keys["end"].amount == 57
    assert s.update({"end": None}, 1.1) == []
    assert s.keys["end"].seen is False and s.keys["end"].amount == 57 and s.keys["end"].seen_t == 1.0
    ev = s.update({"end": ["item", 2010005, 56]}, 1.2)
    assert ev == [{"ev": "slot", "t": 1.2, "key": "end", "was": ["item", 2010005, 57], "now": ["item", 2010005, 56],
                   "d": -1}]
    ev = s.update({"end": ["empty", None, None]}, 2.0)
    assert ev[0]["d"] is None and ev[0]["now"] == ["empty", None, None]
    st = s.state()["end"]
    assert st == {"kind": "empty", "id": None, "amount": None, "seen": True, "seen_t": 2.0, "since": 2.0}


def test_us_reads_the_frame_facts():
    from maplebrain.perception.facts import FrameFacts
    us = Us()
    us.update(FrameFacts(t=0.5, slots={"pagedown": ["item", 2000000, 288]}))
    ev = us.update(FrameFacts(t=0.6, slots={"pagedown": ["item", 2000000, 287]}))
    assert [e["d"] for e in ev] == [-1]
    assert us.state()["slots"]["pagedown"]["amount"] == 287


def test_the_perceiver_fills_facts_slots():
    from maplebrain.config import Config
    from maplebrain.perception.perceiver import Perceiver
    root = Path(__file__).resolve().parents[1]
    per = Perceiver(Config(), np.load(root / "assets" / "self_tag_gray.npy"))
    per.observe(frame_of("line1_100"), 0.0)
    assert per.facts.slots["delete"] == ["item", 2010003, 200]
    assert len(per.facts.slots) == 8
    per.observe(frame_of("quick_3940_tooltip"), 0.1)
    assert per.facts.slots == {k: None for k in S.DEFAULT_KEYS[2]}
