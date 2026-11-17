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
