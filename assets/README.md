# assets

| Path | What |
|---|---|
| `self_tag.npy`, `self_tag_gray.npy` | our own name tag (JenkinsJob), cropped from live frames |
| `mcw/` | MapleStory **Classic World** game data: maps and mob sprites (below) |

## `mcw/`: Classic World maps and mobs

The bot only reads these files at run time; it never calls the internet. They are a local copy of
the game data served by **maplestory.io** (region `MCW`, version `1`), which extracts it from the game files.
The images and data belong to Nexon. They're for local use only; don't redistribute them.

```
mcw/manifest.json           source, region/version, and for every map and mob: name, counts, fetch time (UTC)
mcw/maps/<id>/map.json      footholds (floor/wall segments, map coordinates), ladderRopes, mob spawns,
                            portals, miniMap (centerX/Y, magnification, canvas), vrBounds
mcw/maps/<id>/minimap.png   the minimap picture
mcw/maps/<id>/render.png    whole-map picture (only fetched with --render)
mcw/mobs/<id>/mob.json      stats + framebooks (animation name -> frame count)
mcw/mobs/<id>/<anim>_<n>.png  one animation frame, RGBA, facing LEFT (flip for right)
```

Classic World uses **its own ids**, not the GMS ones:

| Map id | Name | Mobs |
|---|---|---|
| 40 | Snail Hunting Ground I | Snail |
| 41 | Snail Hunting Ground II | Snail, Blue Snail |
| **42** | **Snail Hunting Ground III** (where JenkinsJob farms) | Snail, Blue Snail, Red Snail |

Mob ids: 2 Snail, 3 Blue Snail, 5 Red Snail. Full lists: `https://maplestory.io/api/MCW/1/map`,
`.../MCW/1/mob`. The minimap window's title shows the map you're on.

**Measured (2026-11-01):** sprites appear 1:1 in our normalized 1366x768 frames (best fit on live snails:
height x1.00, width x0.98, which is 1 px, within JPEG/resize blur). The live Snail matches `hit1_0.png`
exactly. The API gives no frame origins (anchor points); a sprite's box is its trimmed image.

## Everything is downloaded (2026-11-02)

`assets update --all` fetched **every map (335 of the API's 347; the 12 "Up and Up" event maps answer 404) and all
118 mobs**: ~45 MB. The bot recognises the map it's on from the minimap (`maplebot/nav/identify.py`) against
these `minimap.png` files, so `--map` is optional. Run `assets update --all` again after a game patch (resumable:
complete maps are skipped; add `--force` to re-download).

## Updating

`run` / `serve` with `--map <id>` download a map (and its mobs) **by themselves the first time** it's used. Drops
(loot) need no assets at all: they're found by how they bob on the ground (`maplebot/perception/drops.py`).

From `C:\Users\Yoav\dev\maple-work`:

```powershell
..\auto-maple\.venv\Scripts\python -m maplebot assets update 42            # add a map (and its mobs)
..\auto-maple\.venv\Scripts\python -m maplebot assets update 40 41 42      # several maps
..\auto-maple\.venv\Scripts\python -m maplebot assets update 42 --force    # re-download what's there
..\auto-maple\.venv\Scripts\python -m maplebot assets update 42 --render   # + whole-map picture (~1 MB)
```

- Mobs that are already in `manifest.json` are skipped, unless you pass `--force`.
- The files are rewritten in place. To keep the old copy, copy `mcw/` aside first, then diff
  `manifest.json` and look at the frames that changed.
- Downloading every map: get the ids from `https://maplestory.io/api/MCW/1/map` (347 maps on
  2026-11-01) and pass them all. Estimate without `--render`: ~40 MB (map 42's map.json is 108 KB,
  its 3 mobs' frames 78 KB in total).

**When to update:** after a game patch changes a mob's look or a map's layout (sprite matches score badly
on a mob whose HP bar we can see; footholds don't line up with the screen), or when farming a new map.

**If maplestory.io changes or disappears:**
1. Check `https://maplestory.io/api/wz`: the region `MCW` with a new version number means the
   game got patched. Change `VERSION` in `maplebot/gamedata.py`, then run `update --force`.
2. If the API is gone: extract from the game's own files with HaRepacker-resurrected or WzComparerR2
   (check that they support Classic World's file format), then write the same layout as above.
3. Last resort: crop mobs from recorded frames in `runs/`. The HP bar marks where each mob is, which
   is how `MobLibrary` learns looks today.
