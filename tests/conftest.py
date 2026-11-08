import pytest

from maplebot.config import Perception


@pytest.fixture(autouse=True)
def loot_on(monkeypatch, request):
    """Looting is OFF by default since session 13 (a pet picks up). The existing tests cover the loot code, so
    they run with it on; mark a test `@pytest.mark.loot_off` to get the real default."""
    if request.node.get_closest_marker("loot_off") is None:
        init = Perception.__init__

        def init_loot_on(self, *a, **kw):
            init(self, *a, **kw)
            if "loot" not in kw:
                self.loot = True
        monkeypatch.setattr(Perception, "__init__", init_loot_on)


def pytest_configure(config):
    config.addinivalue_line("markers", "loot_off: run with the default Perception.loot = False")


def pytest_terminal_summary(terminalreporter):
    """Every run ends with the bot's speed (tests/test_perf.py), so a change shows up at once."""
    import sys
    mod = sys.modules.get("test_perf") or sys.modules.get("tests.test_perf")
    res = getattr(mod, "RESULT", None) if mod else None
    if not res:
        return
    r, base = res["r"], res.get("base")
    line = mod.bench_mod.report(r, base if base and base.get("machine") == r["machine"] else None)
    if base and base.get("machine") == r["machine"]:
        d = (base["tick"]["p50"] - r["tick"]["p50"]) / base["tick"]["p50"]
        if d > 0.15:
            line += f"  -> {d:.0%} FASTER than the baseline: python tools/perf/bench.py --baseline"
        elif d < -0.10:
            line += f"  -> {-d:.0%} slower than the baseline"
    terminalreporter.write_sep("-", "bot speed")
    terminalreporter.write_line(line)
