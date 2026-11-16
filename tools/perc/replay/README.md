Tracker replay (PLAN-perception.md step 0): the gate "replay same or better" for every perception change.
Run with the venv python from the repo root; outputs go to RUN/replay/ (runs/ is not committed).

    run.py RUN                      the working tree's Perceiver over RUN's saved frames -> RUN/replay/work.jsonl
    run.py RUN --old REF [--only perception/world.py,...]     the same with maplebrain's code from a git ref
    compare.py RUN A B              tracks of A vs B: real / weak tracks, track-frames found, camera
    compare.py RUN --live B         the live run's own tracks (ticks.jsonl) vs a replay

Before committing a change:  run.py RUN --old HEAD;  run.py RUN;  compare.py RUN HEAD work
Reference runs: runs/v2/press1 (mob score 0.70), runs/v2/air1/fix3 (0.65; --t1 168: paused after), and the NATIVE
1366x768 PNG recording runs/play/20261116_012059_1 (the user playing, 342 s, 3858 frames, ~2.7 min per replay).

Proven 2026-11-16 (press1, fix3):
- same code twice, and working tree vs `--old HEAD`: the same tracks on 100 % of the frames; scores differ by
  <= 0.005 on up to half the frames, a position by 1 px about once in 5000 track-frames (GPU run-to-run noise).
- press1 at --mob-score 0.65: 163 real tracks = the number of the 2026-11-09 replay (HANDOFF, edge ghosts).
- vs the live run on the same frames: our tag equal on 1488 of 1489 frames, the minimap position within 1-2 px;
  89-90 % of the real track-frames are found either way (the replay sees every 3rd tick: later births, camera
  catching up after fast scrolls; press1 was also recorded BEFORE the edge-ghost fix).
- the native run (3858 frames), same code twice: the same tracks on 99.2 % of the frames, 2-5 of 18,170 real
  track-frames differ (a noise-sized score crossing a threshold). So the gate for "must not change the tracks" is
  track-frames found >= 99.9 % both ways, not 100 % of frames. cudnn.deterministic does not remove the noise
  (tried; gpu_sprites turns cudnn.benchmark on).
- native vs the live tracks: 90.6 % / 92.6 % of real track-frames found; weak tracks 11 (live 26).

## The gate (since 2026-11-16, the user: short clips of many maps, no double replays)

    python tools/perc/replay/gate.py --quick        every sub-step: 3 clips (ant4, line1, transfer), ~3 min
    python tools/perc/replay/gate.py                before a commit that changes tracking: all 7 clips, ~7 min
    python tools/perc/replay/gate.py --list         the clips and what is cached

Clips = ~1 min of each clean native PNG recording (Ant Tunnel IV x2, Dangerous Steam, Line 1, Transfer Area, Dark
Cave) + 1 min FHD JPEG (fix3: the scene camera fails, today's camera). Replays are cached as
RUN/replay/fp_<fingerprint>_<clip>.jsonl; the fingerprint = git ids of maplebrain/, assets/ (tracked) and the replay
tools, so the working tree's replay of one sub-step IS the base of the next (each code state replayed once). Equal
fingerprints = nothing to replay (docs, tools, code off the live path: pytest + the speed line are the gate).
`run.py --old` swaps only code, NOT assets: a base whose assets differ must be cached first (`--base-only` with the
base's assets checked out) - the gate refuses otherwise. 2026-11-16 the tag-template gate run the old way compared
the NEW template with itself (void): found that way.
Per clip: real / weak tracks, track-frames found both ways, sighted the same, mob feet within 2 px of their platform
(the camera's exactness), our tag found, camera source. SAME = >= 99.9 % both ways everywhere; CHANGED = judge it.
New clips: the user records ~1 min on a clean map (`serve runs\play --observe --gpu --tracker --frames-png`) ->
add it to gate.CLIPS.
