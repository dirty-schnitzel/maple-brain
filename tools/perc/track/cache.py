"""Tracker plan, Part 2: the truth kept on disk, so every prototype loads it in seconds instead of rebuilding it.

    python tools/perc/track/cache.py CAP [CAP ...] [--force]

Writes CORPUS/work/SESSION#K/track/chains.pkl = oracle.chains(load.ticks(CAP)) (the hindsight truth: one chain per
mob life). Reading it back: `cache.chains(cap)`; `cache.SOUND` = the 13 captures perception is sound on
(REPORT-track-before.md section 3), `cache.DESIGN` = the 30-minute Line 1 capture.
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load import out_path, ticks  # noqa: E402
from oracle import chains as build  # noqa: E402

DESIGN = "20261121_000219_2#0"
SOUND = [DESIGN, "20261120_235747_1#0", "20261118_232410_1#0", "20261118_232410_1#1", "20261118_232410_1#2",
         "20261118_232410_1#3", "20261118_232410_1#4", "20261118_232410_1#5", "20261118_232410_1#7",
         "20261118_232410_1#9", "20261118_232410_1#12", "20261118_232410_1#13", "20261119_204522_1#4"]


def path(cap) -> Path:
    import dump
    return out_path(cap) / dump.KEPT / "chains.pkl"         # the kept replay's own folder (dump.KEPT)


def chains(cap, tk=None, force: bool = False) -> list:
    """The capture's truth chains (oracle.chains), from disk when kept. Point columns: oracle.I, T, X, Y, POSE,
    FACE, O, TINT, SEEN, COV, NS, SX, SY; I indexes load.ticks(cap)."""
    p = path(cap)
    if p.exists() and not force:
        return pickle.loads(p.read_bytes())
    ch = build(tk if tk is not None else ticks(cap))
    p.write_bytes(pickle.dumps(ch, protocol=pickle.HIGHEST_PROTOCOL))
    return ch


def main():
    force = "--force" in sys.argv
    for cap in [a for a in sys.argv[1:] if not a.startswith("--")]:
        a = time.perf_counter()
        tk = ticks(cap)
        b = time.perf_counter()
        ch = chains(cap, tk, force)
        print(f"{cap}: {len(tk)} ticks loaded in {b - a:.0f} s, {len(ch)} chains in {time.perf_counter() - b:.0f} s "
              f"-> {path(cap)} ({path(cap).stat().st_size / 1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
