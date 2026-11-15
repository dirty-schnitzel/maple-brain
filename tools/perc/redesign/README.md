Experiments behind PLAN-perception.md (2026-11-16). Offline, Ant Tunnel IV recordings. Run with the venv python from
the repo root; they write their outputs next to themselves (ant4_render.png is 49 MB: don't commit outputs).

    prof_tick.py   [--frames DIR --n N --dt S --sync] [--mode parts|cprofile|cuda]   E0: the tick per part / function
    exp_score.py                      E1: NCC vs colour-inlier scores on REAL / LOST / GHOST / NEG sets -> exp_score.json
    exp_render.py  build | check RUN  E2: render tiles + objects from the client export, register on frames
    exp_bg.py                         E3 + E4: "explained by scenery", opacity; lost mobs: covered or misplaced
    exp_absent.py                     E5: scenery visible in a track's body box = absent
