"""Local copy of MapleStory Classic World game data (maps, mob sprites) from the maplestory.io API.

Downloaded once with `python -m maplebot assets update MAP_ID ...`; the bot itself only reads the local files.
Layout under assets/mcw/ (see assets/README.md):
    manifest.json                  source, region/version, what was fetched when
    maps/<id>/map.json             raw API map (footholds, ladderRopes, mobs, portals, miniMap, vrBounds)
    maps/<id>/minimap.png          the miniMap canvas, decoded
    maps/<id>/render.png           whole-map picture (only with --render)
    mobs/<id>/mob.json             raw API mob (stats, framebooks)
    mobs/<id>/<anim>_<n>.png       one animation frame, RGBA, facing left (as the game stores it)
"""
import base64
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

API = "https://maplestory.io/api"
REGION, VERSION = "MCW", "1"   # MapleStory Classic World; its ids differ from GMS (Snail = 2, not 100100)
ROOT = Path(__file__).resolve().parents[1] / "assets" / "mcw"

Getter = Callable[[str], bytes]


def http_get(url: str, tries: int = 4) -> bytes:
    """GET with retry and a growing back-off (plain download, no need for humanized timing)."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "maplebot-assets/1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
        time.sleep(1.5 * 2 ** i)
    raise RuntimeError("unreachable")


def _url(path: str) -> str:
    return f"{API}/{REGION}/{VERSION}/{path}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_manifest(root: Path = ROOT) -> dict:
    p = root / "manifest.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"source": API, "region": REGION, "version": VERSION, "maps": {}, "mobs": {}}


def save_manifest(m: dict, root: Path = ROOT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")


def fetch_mob(mob_id: int, root: Path = ROOT, get: Getter = http_get, force: bool = False,
              workers: int = 8) -> dict:
    """mob.json + every frame of every animation. Returns the manifest entry."""
    d = root / "mobs" / str(mob_id)
    d.mkdir(parents=True, exist_ok=True)
    info = json.loads(get(_url(f"mob/{mob_id}")))
    (d / "mob.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    jobs = [(anim, n) for anim, count in (info.get("framebooks") or {}).items() for n in range(count)]

    def one(job):
        anim, n = job
        p = d / f"{anim}_{n}.png"
        if force or not p.exists():
            p.write_bytes(get(_url(f"mob/{mob_id}/render/{anim}/{n}")))
        return p.name

    with ThreadPoolExecutor(workers) as ex:
        files = sorted(ex.map(one, jobs))
    return {"name": info.get("name"), "level": (info.get("meta") or {}).get("level"),
            "framebooks": info.get("framebooks") or {}, "frames": len(files), "fetched": _now()}


def fetch_map(map_id: int, root: Path = ROOT, get: Getter = http_get, force: bool = False,
              render: bool = False, log=print) -> dict:
    """map.json, minimap.png, optionally render.png, and every mob that spawns there. Updates manifest.json."""
    man = load_manifest(root)
    d = root / "maps" / str(map_id)
    d.mkdir(parents=True, exist_ok=True)
    m = json.loads(get(_url(f"map/{map_id}")))
    (d / "map.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    canvas = (m.get("miniMap") or {}).get("canvas")
    if canvas:
        (d / "minimap.png").write_bytes(base64.b64decode(canvas))
    if render and (force or not (d / "render.png").exists()):
        (d / "render.png").write_bytes(get(_url(f"map/{map_id}/render")))
    mob_ids = sorted({int(x["id"]) for x in m.get("mobs") or []})
    for mid in mob_ids:
        if not force and str(mid) in man["mobs"]:
            log(f"  mob {mid} {man['mobs'][str(mid)]['name']}: have it")
            continue
        man["mobs"][str(mid)] = e = fetch_mob(mid, root, get, force)
        log(f"  mob {mid} {e['name']}: {e['frames']} frames")
    man["maps"][str(map_id)] = {
        "name": m.get("name"), "street": m.get("streetName"), "mobs": mob_ids,
        "footholds": len(m.get("footholds") or {}), "ladderRopes": len(m.get("ladderRopes") or []),
        "render": (d / "render.png").exists(), "fetched": _now()}
    save_manifest(man, root)
    log(f"map {map_id} {m.get('streetName')} / {m.get('name')}: {len(mob_ids)} mob types -> {d}")
    return man["maps"][str(map_id)]


def list_maps(get: Getter = http_get) -> list[dict]:
    """Every Classic World map: [{id, name, streetName}] (347 on 2026-11-01)."""
    return json.loads(get(_url("map")))


def fetch_all(root: Path = ROOT, get: Getter = http_get, force: bool = False, log=print) -> dict:
    """The whole game once: every map (map.json + minimap), then every mob (sprites). Resumable: maps already
    complete on disk are skipped unless `force`; a map that fails is logged and skipped (run it again later).
    Returns {"fetched": n, "skipped": n, "failed": {id: error}}."""
    maps = list_maps(get)
    done = {"fetched": 0, "skipped": 0, "failed": {}}
    for i, e in enumerate(maps, 1):
        mid = int(e["id"])
        if not force and have_map(mid, root):
            done["skipped"] += 1
            continue
        try:
            fetch_map(mid, root, get, force, log=lambda m: log(f"[{i}/{len(maps)}] {m}"))
            done["fetched"] += 1
        except Exception as ex:                                   # noqa: BLE001 - 404, timeout ...: keep going
            done["failed"][mid] = repr(ex)
            log(f"[{i}/{len(maps)}] map {mid} {e.get('name')}: FAILED {ex!r}")
    log(f"all maps: {done['fetched']} fetched, {done['skipped']} already there, {len(done['failed'])} failed")
    # then every mob of the game, also those no map spawns (event/quest/boss mobs)
    man = load_manifest(root)
    mobs = json.loads(get(_url("mob")))
    todo = [int(e["id"]) for e in mobs if force or not (root / "mobs" / str(int(e["id"])) / "mob.json").exists()]
    for i, mid in enumerate(todo, 1):
        try:
            man["mobs"][str(mid)] = e = fetch_mob(mid, root, get, force)
            log(f"[mob {i}/{len(todo)}] {mid} {e['name']}: {e['frames']} frames")
        except Exception as ex:                                   # noqa: BLE001
            done["failed"][f"mob {mid}"] = repr(ex)
            log(f"[mob {i}/{len(todo)}] {mid}: FAILED {ex!r}")
        if i % 20 == 0:
            save_manifest(man, root)
    save_manifest(man, root)
    log(f"all mobs: {len(mobs)} in the game, {len(todo)} fetched now, "
        f"{sum(1 for k in done['failed'] if str(k).startswith('mob'))} failed")
    return done


def have_map(map_id: int, root: Path = ROOT) -> bool:
    """map.json and every mob that spawns there are on disk."""
    mj = root / "maps" / str(map_id) / "map.json"
    if not mj.exists():
        return False
    m = json.loads(mj.read_text(encoding="utf-8"))
    return all((root / "mobs" / str(int(x["id"])) / "mob.json").exists() for x in m.get("mobs") or [])


def ensure_map(map_id: int, root: Path = ROOT, get: Getter = http_get, log=print) -> bool:
    """Download the map (and its mobs) the first time it's used, so any map works with just --map <id>.
    True = downloaded now, False = already there."""
    if have_map(map_id, root):
        return False
    log(f"map {map_id} isn't downloaded yet -> fetching it and its mobs from maplestory.io (once)")
    man = load_manifest(root)                      # a mob listed but missing on disk: fetch it again
    man["mobs"] = {k: v for k, v in man["mobs"].items() if (root / "mobs" / k / "mob.json").exists()}
    save_manifest(man, root)
    fetch_map(map_id, root, get, log=log)
    return True
