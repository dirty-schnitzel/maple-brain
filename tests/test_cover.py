import numpy as np

from maplebrain.cover import Cover, _paste, build_cover


class _Parts:
    """Fake Obj/Tile pictures: every object is a 20 x 10 opaque block, origin (10, 10)."""
    def frames(self, kind, name, path):
        return [(np.ones((10, 20), bool), (10, 10))]


M = {"footholds": {"1": {"x1": 0, "y1": 100, "x2": 400, "y2": 100, "layerId": 0},
                   "2": {"x1": 0, "y1": 200, "x2": 400, "y2": 200, "layerId": 2}}}


def test_objects_on_higher_layers_cover_lower_mob_layers_only():
    img = {"1": {"obj": {"0": {"oS": "s", "l0": "a", "l1": "b", "l2": "c", "x": 100, "y": 100}}},
           "3": {"obj": {"0": {"oS": "s", "l0": "a", "l1": "b", "l2": "c", "x": 300, "y": 200}}}}
    meta, masks = build_cover(img, M, _Parts())
    assert meta["layers"] == [0, 2]
    cov = Cover(meta, masks, M["footholds"])
    C = (0, 0)
    v0, v2 = cov.visible(0, C), cov.visible(2, C)
    assert not v0[95, 100] and not v0[195, 300]                # layer 0 mobs: behind both objects
    assert v2[95, 100] and not v2[195, 300]                    # layer 2 mobs: in front of the layer-1 one
    assert cov.layer(1) == 0 and cov.layer(2) == 2
    assert cov.visible_share(0, C, (90, 90, 20, 10)) == 0.0


def test_paste_clips_at_the_edges():
    m = np.zeros((10, 10), bool)
    _paste(m, np.ones((4, 4), bool), -2, 8, 0, 0)
    assert m.sum() == 2 * 2
