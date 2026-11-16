"""maplebrain/procperf.py: the bot's process on the performance cores (2026-11-16: in the background beside the
game it ran on the efficiency cores, tick 42-46 ms instead of 29)."""
import sys

import pytest

from maplebrain import procperf as pp


def test_the_mask_is_the_highest_efficiency_class_only():
    cpus = [(i, 1) for i in range(16)] + [(i, 0) for i in range(16, 20)]        # this machine: 16 P threads + 4 E
    assert pp.performance_mask(cpus) == 0xFFFF
    assert pp.performance_mask([(i, 0) for i in range(8)]) == 0xFF               # one kind of core: all of them
    assert pp.performance_mask([(0, 0), (1, 2), (2, 1), (3, 2)]) == 0b1010
    assert pp.performance_mask([]) == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_cpu_classes_lists_this_machines_processors():
    import os
    cpus = pp.cpu_classes()
    assert 0 < len(cpus) <= (os.cpu_count() or 64) and pp.performance_mask(cpus) != 0
