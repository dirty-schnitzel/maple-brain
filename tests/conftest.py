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
