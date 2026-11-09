# assets

| Path | What |
|---|---|
| `self_tag.npy`, `self_tag_gray.npy` | our own name tag (JenkinsJob), cropped from live frames |
| `mcw/` | MapleStory **Classic World** game data: maps and mob sprites, built from the game's client files (below) |

## `mcw/`: Classic World maps and mobs - from the game's own client files

**Single source of game data: the Classic World client** (since 2026-11-03; before that a maplestory.io copy, which
had dropped every portal with a destination, resolved some frame links wrongly and had older HP for 4 mobs). The
bot only reads these files at run time; it never goes online. The data and pictures belong to Nexon: local use only.

```
mcw/manifest.json           source (client export), build time; per map / mob: name, counts
mcw/changes.txt             what the last build changed vs the one before (after a game patch: what to re-check)
mcw/maps/<id>/map.json      footholds (by id: x1,y1,x2,y2, prev/next, layerId, groupId, flags), ladderRopes
                            (x, y1, y2, isLadder), mobs (spawns: id, x, y = ground under it, walkAreaX1/X2 = rx0/rx1,
                            footholdId, hidden, mobTime), npcs, portals, miniMap (centerX/Y, width, height,
                            magnification, canvas = minimap.png as base64), vrBounds, info (the client's, as is)
mcw/maps/<id>/minimap.png   the minimap picture (301 of 336 maps have one)
mcw/mobs/<id>/mob.json      info (stats as the client names them: level, maxHP, speed %, pushed, fs, flags ...),
                            link (drawn with another mob's frames), framebooks (anim -> count), frames: per frame
                            origin (the mob's feet, in the PNG), lt/rb (body box) and head relative to the feet,
                            delay (ms), n (the client's frame number), same (a reused picture: stand_0 = move_0)
mcw/mobs/<id>/<anim>_<n>.png  one frame, RGBA, facing LEFT (flip for right): the client's canvas as is, n = 0..count-1
```

Ids are the client's without the zero padding: map `000000042` -> 42, mob `0000002` -> 2 (Snail 2, Blue Snail 3,
Red Snail 5; maps 40/41/42 = Snail Hunting Ground I/II/III). Names come from the client's `String` data.

**Measured (2026-11-01):** sprites appear 1:1 in our normalized 1366x768 frames (best fit on live snails: height
x1.00, width x0.98, 1 px). The live Snail matches `hit1_0.png` exactly.

## How it's made

1. **Copy** the game's `Data` folder (`C:\Nexon\Library\maplestorycw\appdata\Data`) to `C:\Users\Yoav\dev\cw-data\Data`.
   Never open the install itself (integrity check).
2. **Export** with HaRepacker's MapleLib (`C:\Users\Yoav\dev\harepacker-11.1.0\lib`, see `tools/cwdata/`), ~10 s:
   ```powershell
   $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\cwdata\export.ps1
   ```
   -> `C:\Users\Yoav\dev\cw-data\export`: every map and mob as XML, every minimap and mob frame as PNG (links
   resolved). Key `WzMapleVersion.BMS`; mobs are in the encrypted pack `Packs\Mob_00000.ms`.
3. **Build** (~7 s): `..\auto-maple\.venv\Scripts\python -m maplebrain assets build` -> `assets/mcw`, rebuilt from
   scratch next to the old one and swapped in; prints and writes `changes.txt`.
4. `..\auto-maple\.venv\Scripts\python -m pytest`, then commit `assets/mcw` (it's in git: the diff shows the patch).

## After a game patch

Reading the client doesn't make a patch free: the data is only as new as the last export, and a patch can change
what the bot was tuned on. Do steps 1-4, then **read `changes.txt`** (and `git diff --stat assets/mcw`):
- **maps added / changed**: footholds or ropes moved -> navmap / jump tests (`test_navmap`, `test_jump`) may need new
  numbers; a changed minimap picture -> map recognition (`test_identify`) and the minimap locator.
- **mobs changed**: new frames -> sprite detection (hues, scores; `test_sprites` on recorded frames); stats (speed,
  maxHP, pushed) -> anything tuned on them.
- If the export itself fails: HaRepacker may need an update for a new client format/version (report the error).
- Then a short live run on the farming map before longer sessions.

Drops (loot) need no assets: they're found by how they bob on the ground (`maplebrain/perception/drops.py`).
