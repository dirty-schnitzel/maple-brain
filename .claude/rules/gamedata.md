---
paths:
  - "assets/**"
  - "maplebrain/gamedata.py"
  - "tools/cwdata/**"
  - "docs/game_rules.md"
---
# Game data and game rules: standing rules

- **The client's own files are the only game-data source** (since 2026-11-03). The old web API
  (maplestory.io) had bugs and is gone: never bring it back. What the files hold: `assets/README.md`.
- **The steps after a game patch:** `assets/README.md`. In short: the copy of the client's Data folder at
  `C:\Users\Yoav\dev\cw-data\Data` (never open the install itself) -> `$env:DOTNET_ReadyToRun=0; pwsh -NoProfile
  -File tools\cwdata\export.ps1` -> `python -m maplebrain assets build` -> `python -m maplebrain assets scene`
  (every map: `assets/scene` is not in git, a partial build goes unnoticed) -> read `changes.txt`, run pytest.
- **Export gotchas:** the key is `WzMapleVersion.BMS` (GMS / EMS report success and give garbled names); pwsh
  needs `DOTNET_ReadyToRun=0` or it crashes; call MapleLib from PowerShell, don't compile C# against it.
- **Game rules** (how we and the mobs move, hits, spawning, drops, EXP) come from v83 code - HeavenClient for
  the client's side, Cosmic for the server's - and are written up in `docs/game_rules.md` with their sources.
  Where no source has a rule, the doc says NOT FOUND: don't fill the gap with a guess, and don't make "measure
  it from footage first" a precondition (the user, 2026-11-20). Both sources are AGPL-3.0: rules in our own
  words, a constant or one line quoted at most.
- No further work on server data (respawn, aggro, drop lifetime, EXP) until a job needs it (the user, 2026-11-21).
- The character's own numbers (damage range, speed, jump) are in no game file: they are config.
