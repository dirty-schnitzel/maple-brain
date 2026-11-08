"""Bot speed regression: the brain-v2 tick replayed on tests/fixtures/perf_ant4 (tools/perf/bench.py) must not get
slower than this machine's baseline (tests/perf_baseline.json). Every pytest run ends with the numbers (conftest.py).

Fails when the tick median is > 25 % (+2 ms) over the baseline, or one part's median > 50 % (+3 ms) over it. The bench
runs in its OWN process, like the bot (inside pytest, after the other GPU tests, it measured ~17 % slow); the game
running at the same time competes for the GPU, so a failing first try is measured once more and the faster counts.
Standalone repeats agree within ~5 %. After a deliberate change: `python tools/perf/bench.py --baseline`.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("perf_bench", ROOT / "tools" / "perf" / "bench.py")
bench_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench_mod)

RESULT = {}                                       # read by conftest.pytest_terminal_summary
TICK_SLACK, PART_SLACK = (1.25, 2.0), (1.5, 3.0)


def _slower(r, base) -> list:
    bad = []
    if r["tick"]["p50"] > base["tick"]["p50"] * TICK_SLACK[0] + TICK_SLACK[1]:
        bad.append(f"tick {r['tick']['p50']} ms vs {base['tick']['p50']}")
    for k, v in base.items():
        if isinstance(v, dict) and k.startswith("p.") and k in r:
            if r[k]["p50"] > v["p50"] * PART_SLACK[0] + PART_SLACK[1]:
                bad.append(f"{k[2:]} {r[k]['p50']} ms vs {v['p50']}")
    return bad


def _bench() -> dict:
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "perf" / "bench.py"), "--json"], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_bot_speed_has_not_dropped():
    if not torch.cuda.is_available():
        pytest.skip("no CUDA: the bot's mob detection runs on the GPU")
    frames = bench_mod.fixture_frames()
    if not frames:
        pytest.skip("no tests/fixtures/perf_ant4")
    base = json.loads(bench_mod.BASELINE.read_text()) if bench_mod.BASELINE.exists() else None
    r = _bench()
    if base is not None and base.get("machine") == r["machine"] and _slower(r, base):
        r2 = _bench()                                 # once more: the game / another program may have had the GPU
        r = min(r, r2, key=lambda x: x["tick"]["p50"])
    RESULT.update(r=r, base=base)
    if base is None or base.get("machine") != r["machine"]:
        pytest.skip(f"no baseline for this machine ({r['machine']}): python tools/perf/bench.py --baseline")
    bad = _slower(r, base)
    assert not bad, "the bot got SLOWER: " + "; ".join(bad) + "\n" + bench_mod.report(r, base)
