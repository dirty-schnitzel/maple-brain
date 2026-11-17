"""assets/mcw/items (PLAN-loot.md S2): every item picture loads, the picture classes follow their rule and are stable.
Needs only assets/mcw (in git); skipped when the items are not built."""
import numpy as np
import pytest

from maplebrain import gamedata

ROOT = gamedata.ROOT


@pytest.fixture(scope="module")
def items():
    if not (ROOT / "items" / "items.npz").exists():
        pytest.skip("assets/mcw/items not built (assets build with an export that has Item/)")
    return gamedata.load_items()


def test_every_picture_loads(items):
    assert len(items) == items.doc["pictures"] == len(items.item) == len(items.weak)
    for g, p in enumerate(items.pics):
        assert p.dtype == np.uint8 and p.ndim == 3 and p.shape[2] == 4 and min(p.shape[:2]) >= 1, g
    for sid, e in items.meta.items():
        for fr in e.get("frames") or [e]:
            assert items.pics[fr["g"]].shape[:2] == (fr["h"], fr["w"]), sid


def test_pictures_are_distinct(items):
    keys = {(p.shape, p.tobytes()) for p in items.pics}
    assert len(keys) == len(items.pics)


def test_class_rule(items):
    """A class's id = the meso's when a meso frame shows the picture, else the lowest id showing it; every id's
    `same` is its picture's class id."""
    for g in range(len(items)):
        mem = items.members(g)
        assert mem, g
        mesos = [i for i in mem if items.kind(i) == "Meso"]
        assert items.item[g] == (mesos[0] if mesos else min(mem)), (g, mem)
    for sid, e in items.meta.items():
        if e["kind"] != "Meso":
            assert e["same"] == items.item[e["g"]] and e.get("same_f", 0) == items.f[e["g"]], sid


def test_classes_stable_under_order():
    """item_classes gives the same classes whatever order the pictures come in."""
    rng = np.random.default_rng(3)
    a = rng.integers(0, 255, (3, 4, 4), dtype=np.uint8)
    b = a.copy()
    b[0, 0, 0] ^= 1
    entries = [(4000005, 0, a, (0, 0), 0), (9000001, 2, a.copy(), (0, 0), 0), (2000000, 0, b, (0, 0), 0),
               (4000001, 0, a.copy(), (0, 0), 0), (1002000, 0, b.copy(), (0, 0), 0)]
    want = None
    for _ in range(6):
        order = rng.permutation(len(entries))
        cls, of = gamedata.item_classes([entries[i] for i in order])
        got = sorted((c[0], c[1], tuple(sorted(entries[order[i]][0] for i, k in of.items() if k == ci)))
                     for ci, c in enumerate(cls))
        want = want or got
        assert got == want
    assert want == [(1002000, 0, (1002000, 2000000)), (9000001, 2, (4000001, 4000005, 9000001))]


def test_known_facts(items):
    """Mesos: 4 sizes x 4 frames; links resolved (scroll families borrow a picture); weak = see-through ones."""
    for n in range(4):
        e = items.meta[str(9000000 + n)]
        assert e["kind"] == "Meso" and len(e["frames"]) == 4
    linked = [e for e in items.meta.values() if e.get("link")]
    assert len(linked) >= 250
    for e in linked:
        t = items.meta.get(str(e["link"]))
        assert t is not None and t["g"] == e["g"], e
    assert int(items.weak.sum()) == items.doc["weak_count"]
    assert all(items.kept[items.weak] < gamedata.WEAK_FEATURES)
