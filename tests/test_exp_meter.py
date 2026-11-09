import pytest

from maplebrain.runtime.exp_meter import LEVEL_UP_READS, ExpMeter


def test_total_is_current_minus_start_and_a_misread_that_comes_back_adds_nothing():
    m = ExpMeter()
    for i, p in enumerate([27386, 27336, 27236, 27336, 27386, 27400]):
        m.update(float(i), p)
    assert m.total == 14


def test_level_up_keeps_what_was_gained_and_goes_on_from_the_new_number():
    m = ExpMeter()
    m.update(0.0, 63000)
    m.update(1.0, 63661)
    for i in range(LEVEL_UP_READS):
        m.update(2.0 + i, 6)
    m.update(10.0, 106)
    assert m.total == 661 + 100 and m.level_ups == 1


def test_a_short_low_misread_is_not_a_level_up():
    m = ExpMeter()
    m.update(0.0, 27000)
    for i in range(LEVEL_UP_READS - 1):
        m.update(1.0 + i, 2700)
    m.update(9.0, 27010)
    assert m.total == 10 and m.level_ups == 0


def test_unreadable_at_the_start_waits_for_the_first_number():
    m = ExpMeter()
    m.update(0.0, None)
    assert m.summary() == "session EXP: never read"
    m.update(100.0, 500)
    m.update(136.0, 510)
    assert m.elapsed == 36 and m.per_hour() == pytest.approx(1000)


def test_logs_once_per_window_with_session_and_last_5_min_rates():
    m = ExpMeter()
    lines = []
    for s in range(0, 601):                     # 100 EXP/min for 5 min, then 200 EXP/min
        pts = 1000 + (s * 100 // 60 if s <= 300 else 500 + (s - 300) * 200 // 60)
        if line := m.update(float(s), pts):
            lines.append(line)
    assert lines == ["EXP 500 this session = 6,000/hour; last 5 min 6,000/hour",
                     "EXP 1,500 this session = 9,000/hour; last 5 min 12,000/hour"]


def test_focus_pause_is_not_session_time():
    m = ExpMeter()
    m.update(0.0, 100)
    m.update(100.0, 200)
    m.pause(1000.0)
    m.update(1100.0, 200)
    assert m.elapsed == 100
