"""brain v3 migration gate, quick form (PLAN-v3.md steps 1-2: behaviour must stay IDENTICAL): seeds 1-2 x 60 s of the
sim hunt vs tests/fixtures/v3_gate.json (recorded on dev 02a639a before any v3 change). The full gate (seeds 1-8 x
180 s + agree.py) is `python tools/v3/gate.py`; re-record only on purpose (`--record`), never to hide a mismatch."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _gate():
    spec = importlib.util.spec_from_file_location("v3_gate", ROOT / "tools" / "v3" / "gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_brain_behaves_exactly_as_the_baseline():
    gate = _gate()
    got = gate.fingerprint(*gate.QUICK, with_agree=False)
    bad = gate.compare(json.loads(gate.FIXTURE.read_text(encoding="utf-8")), got)
    assert not bad, "\n".join(bad)
