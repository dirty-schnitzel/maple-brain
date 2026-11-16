Experiments behind PLAN-perception.md (2026-11-16). Offline, Ant Tunnel IV recordings. Run with the venv python from
the repo root; they write their outputs next to themselves (ant4_render.png is 49 MB: don't commit outputs).

    prof_tick.py   [--frames DIR --n N --dt S --sync] [--mode parts|cprofile|cuda]   E0: the tick per part / function
    exp_score.py                      E1: NCC vs colour-inlier scores on REAL / LOST / GHOST / NEG sets -> exp_score.json
    exp_render.py  build | check RUN  E2: render tiles + objects from the client export, register on frames
    exp_bg.py                         E3 + E4: "explained by scenery", opacity; lost mobs: covered or misplaced
    exp_absent.py                     E5: scenery visible in a track's body box = absent
    exp_back.py RUN [N]               E7: parallax backs under the render: the client's constants (WOFF 682, HOFF 468,
                                      integer division toward zero), share of the picture explained (PNG run)
                                      (682 = that recording's 1 px capture error; E8: 683)
    exp_backfit.py fit RUN | solve RUN..   E8: each background layer's position measured on 7 maps -> one arithmetic:
                                      off + trunc(r * (C + off) / 100), off 683 / 468: 736 of 736 (x), 587 of 587 (y)

E9 (2026-11-17, behind PLAN-fit-speed.md: the fit's candidate search by exact-colour voting):
    exp_exact.py                      E9a: frame colour = sprite colour exactly (98.57 % of opaque pixels, the rest
                                      covered); palettes (Horny 77 colours, Zombie 134, Stirge 14, Bubbling 60)
    exp_fade_exact.py real | synth    E9b: real fades are I = B + o (s - B) to the level, one o per mob; the per-pixel
                                      "some colour at some opacity" test is NOT selective (kept as the dead end)
    exp_tint.py N,TYPE,X,Y ...        E9c: frozen mobs = sprite x (B 255, G 168, R 10) / 255, exactly
    exp_vote.py table MAP | synth OUT | labels RUN | tracks RUN REPLAY
                                      E9: palette ids -> 2x2 features -> votes -> exclusive votes (+ fades by
                                      un-blending at the residue's alpha): candidates vs truth / labels / tracks, ms
