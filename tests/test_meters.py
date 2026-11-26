"""The HP meter (PLAN-tracker step 5a): perception/meters.py finds the meters over the mobs we hit and reads each one's
green share, on frames drawn exactly as the client draws one (measured on the recordings: tools/perc/track/
proto_meter.py); track/mobs.py ties a meter to its track (`hp`, `hp_t`) - only a meter that names one sighting, read,
over no other mob. Its numbers on footage: the step's gate (PLAN-tracker "Step 5a")."""
from types import SimpleNamespace

import numpy as np

from maplebrain.perception.meters import MeterReader, offsets
from test_track_mobs import a_tracker, ev, mob

H, W = 768, 1366
MOBS = {1: {"frames": {"stand": [{"lt": [-20, -40], "rb": [20, 0]}],
                       "move": [{"lt": [-30, -52], "rb": [10, 0]}],
                       "die1": [{}]}}}          # a die frame without a body box: no meter is looked for


def frame():
    return np.full((H, W, 3), 128, np.uint8)


def draw(f, x0, y0, green, lost_r=220):
    """A meter as the client draws it: the 52 x 10 box at (x0, y0), `green` px of 46 green from the inside's left,
    the rest lost (red R = lost_r; 0 = faded to black). Clipped to the frame."""
    box = np.zeros((10, 52, 3), np.uint8)
    box[1, 1:51] = box[8, 1:51] = 255
    box[1:9, 1] = box[1:9, 50] = 255
    box[3:6, 3:3 + green] = (0, 255, 0)
    box[3:6, 3 + green:49] = (0, 0, lost_r)
    box[6, 3:3 + green] = (0, 0, 170)
    box[6, 3 + green:49] = (0, 0, int(lost_r * 0.71))
    ys, xs = slice(max(0, y0), min(H, y0 + 10)), slice(max(0, x0), min(W, x0 + 52))
    f[ys, xs] = box[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0]
    return f


def fit(*mobs):
    return [{"type": 1, "pose": p, "facing": fc, "feet": [x, y]} for x, y, p, fc in mobs]


def test_the_box_is_centred_on_the_pose_frames_body_box_30_px_over_it():
    off = offsets(MOBS)
    assert off[(1, "stand_0", "left")] == (-26, -70)
    assert off[(1, "move_0", "left")] == (-10 - 26, -52 - 30)         # lt / rb (-30, 10): its middle -10
    assert off[(1, "move_0", "right")] == (10 - 26, -52 - 30)         # mirrored: (-10, 30), its middle +10
    assert (1, "die1_0", "left") not in off


def test_a_meter_over_a_hit_mob_is_found_and_read():
    f = draw(frame(), 574, 330, 26)
    got = MeterReader(MOBS).read(f, fit((600, 400, "stand_0", "left")))
    assert got == [(574, 330, round(26 / 46, 4), 48, (0,))]


def test_the_lost_part_faded_to_black_is_read_as_lost():
    f = draw(frame(), 574, 330, 3, lost_r=0)                          # damage older than 2 s: black, not red
    assert MeterReader(MOBS).read(f, fit((600, 400, "stand_0", "left")))[0][2] == round(3 / 46, 4)


def test_full_and_empty():
    rd = MeterReader(MOBS)
    assert rd.read(draw(frame(), 574, 330, 46), fit((600, 400, "stand_0", "left")))[0][2] == 1.0
    assert rd.read(draw(frame(), 574, 330, 0), fit((600, 400, "stand_0", "left")))[0][2] == 0.0


def test_only_a_band_around_the_mobs_is_looked_at():
    f = draw(frame(), 574, 330, 20)
    draw(f, 900, 100, 20)                                             # no fit mob under it: never looked at
    got = MeterReader(MOBS).read(f, fit((600, 400, "stand_0", "left")))
    assert [g[:2] for g in got] == [(574, 330)]
    assert MeterReader(MOBS).read(f, []) == []


def test_off_its_place_within_the_band_found_but_names_no_mob():
    f = draw(frame(), 574, 338, 20)                                   # 8 px low: the fit's pose frame one off
    got = MeterReader(MOBS).read(f, fit((600, 400, "stand_0", "left")))
    assert [(g[0], g[1], g[4]) for g in got] == [(574, 338, ())]


def test_facing_right_mirrors_the_body_box():
    f = draw(frame(), 600 + 10 - 26, 400 - 82, 30)
    rd = MeterReader(MOBS)
    assert rd.read(f, fit((600, 400, "move_0", "right")))[0][4] == (0,)
    assert [g[4] for g in rd.read(f, fit((600, 400, "move_0", "left")))] == [()]  # 20 px from the left-facing
                                                                                # place: in its band, not named


def test_cut_by_the_screens_side_read_from_its_right_end():
    f = draw(frame(), -10, 330, 30)                                   # the box's left 10 px off the screen
    got = MeterReader(MOBS).read(f, fit((16, 400, "stand_0", "left")))
    assert [(g[0], g[1], g[2]) for g in got] == [(-10, 330, round(30 / 46, 4))]


def test_the_green_end_drawn_over_gives_no_fill():
    f = draw(frame(), 574, 330, 20)
    f[330:340, 574 + 3 + 17:574 + 3 + 24] = (40, 90, 160)             # something over the green's end (a digit)
    got = MeterReader(MOBS).read(f, fit((600, 400, "stand_0", "left")))
    assert [(g[0], g[1], g[2]) for g in got] == [(574, 330, None)]


def test_a_white_box_without_the_black_lines_is_no_meter():
    f = frame()
    f[330:340, 574:626] = 255                                        # a name tag's / window's white box
    f[332:338, 577:623] = (0, 255, 0)
    assert MeterReader(MOBS).read(f, fit((600, 400, "stand_0", "left"))) == []


def test_two_mobs_at_one_place_both_named():
    f = draw(frame(), 574, 330, 20)
    got = MeterReader(MOBS).read(f, fit((600, 400, "stand_0", "left"), (601, 400, "stand_0", "left")))
    assert len(got) == 1 and got[0][4] == (0, 1)


# ------------------------------------------------------------------ the tracker ties a meter to its track
def mfacts(t, sights=(), meters=None):
    return SimpleNamespace(t=t, scene_cam=(0, 0), tags=[], drops=[], tag=None, meters=meters,
                           fit=[{"type": k, "feet": [x, y], "pose": p, "facing": "left", "opacity": o, "n_seen": n}
                                for k, x, y, p, o, n in sights])


def test_a_meter_teaches_its_one_mob_and_the_hp_is_kept():
    trk = a_tracker()
    trk.update(mfacts(0.0, [mob(600)]), ev(False, True))
    assert trk.mobs()[0].hp is None and trk.mobs()[0].hp_t is None    # never read
    trk.update(mfacts(0.1, [mob(601)], meters=[(575, 0, 0.5, 48, (0,))]), ev(False, True))
    assert (trk.mobs()[0].hp, trk.mobs()[0].hp_t) == (0.5, 0.1)
    trk.update(mfacts(0.2, [mob(602)]), ev(False, True))             # no meter read: kept
    trk.update(mfacts(0.3, []), ev(False, True))                      # remembered: kept
    assert (trk.mobs()[0].hp, trk.mobs()[0].hp_t) == (0.5, 0.1)


def test_a_meter_teaches_the_track_of_the_sighting_it_names():
    trk = a_tracker()
    trk.update(mfacts(0.0, [mob(400), mob(800)]), ev(False, True))
    trk.update(mfacts(0.1, [mob(800), mob(400)], meters=[(0, 0, 0.25, 48, (1,))]), ev(False, True))
    hp = {round(m.x): m.hp for m in trk.mobs()}
    assert hp == {400: 0.25, 800: None}


def test_a_meter_naming_two_sightings_teaches_nothing():
    trk = a_tracker()
    trk.update(mfacts(0.0, [mob(400), mob(800)]), ev(False, True))
    trk.update(mfacts(0.1, [mob(400), mob(800)], meters=[(0, 0, 0.25, 48, (0, 1))]), ev(False, True))
    assert [m.hp for m in trk.mobs()] == [None, None]


def test_a_meter_over_two_overlapping_mobs_teaches_nothing():
    trk = a_tracker()
    trk.update(mfacts(0.0, [mob(600), mob(630)]), ev(False, True))
    trk.update(mfacts(0.1, [mob(600), mob(630)], meters=[(0, 0, 0.4, 48, (0,))]), ev(False, True))
    assert [m.hp for m in trk.mobs()] == [None, None]                 # the bodies meet (40 px wide, 30 apart)


def test_a_remembered_mob_that_can_be_under_it_blocks_the_teaching():
    trk = a_tracker()
    trk.update(mfacts(0.0, [mob(600), mob(560)]), ev(False, True))
    trk.update(mfacts(0.1, [mob(600)]), ev(False, True))              # the one at 560 drawn over: remembered
    trk.update(mfacts(0.2, [mob(600)], meters=[(0, 0, 0.4, 48, (0,))]), ev(False, True))
    by_x = {round(m.x_seen): m for m in trk.mobs()}
    assert not by_x[560].seen and by_x[600].hp is None


def test_a_meter_whose_fill_was_not_read_teaches_nothing():
    trk = a_tracker()
    trk.update(mfacts(0.0, [mob(600)]), ev(False, True))
    trk.update(mfacts(0.1, [mob(600)], meters=[(0, 0, None, 30, (0,))]), ev(False, True))
    assert trk.mobs()[0].hp is None
