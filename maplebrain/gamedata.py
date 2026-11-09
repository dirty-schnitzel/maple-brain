"""MapleStory Classic World game data, built from the game's own client files: the bot's single source of game data.

`tools/cwdata/export.ps1` exports a copy of the client's Data folder with HaRepacker's MapleLib to XML + PNG;
`python -m maplebrain assets build` turns that export into what the bot reads at run time (see assets/README.md):
    manifest.json               where it came from, when it was built; per map / mob: name and counts
    changes.txt                 what the last build changed vs the one before (after a game patch: what to re-check)
    maps/<id>/map.json          footholds, ladderRopes, mobs (spawns), npcs, portals, miniMap (+ canvas as base64),
                                vrBounds, info (the client's map info, as is)
    maps/<id>/minimap.png       the miniMap canvas
    mobs/<id>/mob.json          info (stats, the client's names), framebooks (anim -> frame count), frames (per frame:
                                origin = the mob's feet in the PNG, lt/rb body box and head relative to the feet, delay ms;
                                `same`: a frame the client reuses, e.g. stand_0 is move_0)
    mobs/<id>/<anim>_<n>.png    one animation frame, RGBA, facing left: the client's canvas as is
    attacks.json                per weapon type (Character Afterimage): attack stance -> [ltx, lty, rbx, rby], the
                                area a swing hits, relative to our feet, FACING LEFT (x < 0 = in front); brain-v2 reach.
                                Also stance_ms (the body's attack stances, ms at speed 6), speeds (weapon type ->
                                {attackSpeed: count}) and items (weapon id -> [type, attackSpeed]): swing lengths
Ids are the client's without the zero padding (map 000000042 -> 42, mob 0000002 -> 2). map.json's field names
(footholds / ladderRopes / mobs / miniMap ...) are the ones the bot has always read (the layout of the maplestory.io
copy this replaced on 2026-11-03).
"""
import base64
import json
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "assets" / "mcw"
EXPORT = Path(r"C:\Users\Yoav\dev\cw-data\export")       # tools/cwdata/export.ps1's default output


# ------------------------------------------------------------------ the exporter's XML (WzClassicXmlSerializer)
def _node(e: ET.Element):
    tag = e.tag
    if tag in ("imgdir", "canvas", "extended"):
        d = {c.get("name"): _node(c) for c in e}
        if tag == "canvas":
            d["_size"] = [int(e.get("width")), int(e.get("height"))]
        return d
    if tag in ("int", "short", "long"):
        return int(e.get("value"))
    if tag in ("float", "double"):
        return float(e.get("value"))
    if tag == "string":
        return e.get("value")
    if tag == "vector":
        return [int(e.get("x")), int(e.get("y"))]
    if tag == "uol":
        return {"_uol": e.get("value")}
    return None                                         # null, sound: nothing the bot needs


def load_xml(path: Path) -> dict:
    """One exported .img.xml -> nested dicts (canvases: their properties + `_size`; pixels are separate PNGs)."""
    return _node(ET.parse(path).getroot())


def _int_keys(d: dict) -> list:
    return sorted((k for k in d if k.lstrip("-").isdigit()), key=int)


# ------------------------------------------------------------------ attack boxes (brain-v2 reach)
def build_attacks(export: Path) -> dict:
    """Afterimage/<weapon>.img.xml -> {weapon: {stance: [ltx, lty, rbx, rby]}} (facing left, relative to our feet).
    The client keeps one box set per weapon level bracket (0-10); they're identical for every weapon checked
    (2026-11-05), so bracket 0 is stored and any bracket that differs is reported in `differs`."""
    out, differs = {}, []
    for p in sorted((Path(export) / "Afterimage").glob("*.img.xml")):
        w = p.name.split(".")[0]
        img = load_xml(p)
        boxes = {}
        for lvl in _int_keys(img):
            for st, v in img[lvl].items():
                if isinstance(v, dict) and "lt" in v and "rb" in v:
                    b = [*v["lt"], *v["rb"]]
                    if st not in boxes:
                        boxes[st] = b
                    elif boxes[st] != b and f"{w}/{st}" not in differs:
                        differs.append(f"{w}/{st}")
        if boxes:
            out[w] = boxes
    return {"weapons": out, "differs": differs, **build_swings(export)}


def build_swings(export: Path) -> dict:
    """Character/00002000.img.xml (the body) -> stance_ms {attack stance: its frames' delays summed, ms, at attack
    speed 6}; Character/weapons.json -> speeds {weapon type: {attackSpeed: how many weapons}} and items {item id:
    [type, attackSpeed]}. A swing lasts stance_ms x (10 + attackSpeed) / 16 (brain/reach.py; live check:
    runs/probe/sauna1, polearm speed 8: 0.89-0.92 s vs 0.90)."""
    body_p, weap_p = Path(export) / "Character" / "00002000.img.xml", Path(export) / "Character" / "weapons.json"
    if not body_p.exists() or not weap_p.exists():
        return {}
    stances = set()
    for p in (Path(export) / "Afterimage").glob("*.img.xml"):
        img = load_xml(p)
        stances |= {st for lvl in _int_keys(img) for st, v in img[lvl].items() if isinstance(v, dict) and "lt" in v}
    body = load_xml(body_p)
    stance_ms = {st: sum(int(f.get("delay", 0)) for k, f in body[st].items() if k.isdigit() and isinstance(f, dict))
                 for st in sorted(stances) if isinstance(body.get(st), dict)}
    items, speeds = {}, {}
    for wid, w in json.loads(weap_p.read_text(encoding="utf-8-sig")).items():
        items[wid] = [w["afterImage"], int(w["attackSpeed"])]
        n = speeds.setdefault(w["afterImage"], {})
        n[str(w["attackSpeed"])] = n.get(str(w["attackSpeed"]), 0) + 1
    return {"stance_ms": stance_ms, "speeds": speeds, "items": items}


# ------------------------------------------------------------------ maps
def map_names(string_map: dict) -> dict:
    """String/Map.img ({region: {padded id: {streetName, mapName}}}) -> {id: (street, name)}."""
    out = {}
    for region in string_map.values():
        for k, v in (region or {}).items():
            if k.isdigit() and isinstance(v, dict):
                out[int(k)] = (v.get("streetName"), v.get("mapName"))
    return out


def _footholds(img: dict) -> dict:
    fh = {}
    for layer, groups in (img.get("foothold") or {}).items():
        for group, segs in (groups or {}).items():
            for fid, f in (segs or {}).items():
                if fid in fh:
                    raise ValueError(f"foothold {fid} twice (layers {fh[fid]['layerId']} and {layer})")
                fh[fid] = {"id": int(fid), **f, "layerId": int(layer), "groupId": int(group)}
    return {k: fh[k] for k in sorted(fh, key=int)}


def _life(img: dict) -> tuple[list, list]:
    """life -> (mobs, npcs). y = the foothold's height under the spawn (`cy`; the client's `y` is where the sprite
    is first drawn); walkAreaX1/X2 = rx0/rx1, the x range the mob may wander."""
    named = {"id", "x", "y", "cy", "fh", "rx0", "rx1", "hide", "f", "mobTime", "type"}
    mobs, npcs = [], []
    life = img.get("life") or {}
    for k in _int_keys(life):
        v = life[k]
        e = {"index": int(k), "id": int(v["id"]), "x": v["x"], "y": v.get("cy", v["y"]), "spriteY": v["y"],
             "footholdId": v.get("fh"), "walkAreaX1": v.get("rx0"), "walkAreaX2": v.get("rx1"),
             "hidden": bool(v.get("hide", 0)), "flip": bool(v.get("f", 0)), "mobTime": v.get("mobTime", 0),
             **{kk: vv for kk, vv in v.items() if kk not in named}}
        {"m": mobs, "n": npcs}.get(v.get("type"), []).append(e)
    return mobs, npcs


def _portals(img: dict) -> list:
    named = {"pn", "pt", "x", "y", "tm", "tn"}
    p = img.get("portal") or {}
    return [{"index": int(k), "portalName": v.get("pn"), "type": v.get("pt"), "x": v.get("x"), "y": v.get("y"),
             "toMap": v.get("tm"), "toName": v.get("tn"), **{kk: vv for kk, vv in v.items() if kk not in named}}
            for k, v in ((k, p[k]) for k in _int_keys(p))]


def _ropes(img: dict) -> list:
    r = img.get("ladderRope") or {}
    return [{"index": int(k), "x": v["x"], "y1": v["y1"], "y2": v["y2"], "isLadder": bool(v.get("l", 0)),
             **{kk: vv for kk, vv in v.items() if kk not in ("x", "y1", "y2", "l")}}
            for k, v in ((k, r[k]) for k in _int_keys(r))]


def map_json(img: dict, map_id: int, names: dict, minimap_png: bytes | None) -> dict:
    """One exported map image -> map.json."""
    info = img.get("info") or {}
    street, name = names.get(map_id, (None, None))
    mobs, npcs = _life(img)
    m = {"id": map_id, "name": name, "streetName": street,
         "mobRate": info.get("mobRate"), "isTown": bool(info.get("town", 0)), "returnMap": info.get("returnMap"),
         "footholds": _footholds(img), "ladderRopes": _ropes(img), "mobs": mobs, "npcs": npcs,
         "portals": _portals(img)}
    mm = img.get("miniMap")
    if mm:
        m["miniMap"] = {"centerX": mm.get("centerX"), "centerY": mm.get("centerY"), "width": mm.get("width"),
                        "height": mm.get("height"), "magnification": mm.get("mag")}
        if minimap_png:
            m["miniMap"]["canvas"] = base64.b64encode(minimap_png).decode("ascii")
    if "VRLeft" in info:
        m["vrBounds"] = {"left": info["VRLeft"], "top": info["VRTop"], "right": info["VRRight"],
                         "bottom": info["VRBottom"]}
    m["info"] = info
    return m


# ------------------------------------------------------------------ mobs
def _resolve(img: dict, anim: str, node) -> tuple | None:
    """A UOL frame -> (anim, n, canvas props) of the frame it points at. The path is relative to the anim holding the
    link: '0' = frame 0 of the same anim, '../move/0' = move's frame 0. Chains are followed; None if it leads nowhere."""
    for _ in range(8):
        if not (isinstance(node, dict) and "_uol" in node):
            return None
        path = [anim]
        for part in node["_uol"].split("/"):
            path = path[:-1] if part == ".." else path + [part]
        if len(path) != 2 or not path[1].isdigit():
            return None
        anim, node = path[0], (img.get(path[0]) or {}).get(path[1])
        if isinstance(node, dict) and "_size" in node:
            return anim, int(path[1]), node
    return None


def _anims(img: dict) -> dict:
    """{anim: [(n, source anim, source n, canvas props)]}: every node of numbered canvases (frames), in the client's
    order. UOL frames ('stand/0' -> '../move/0') resolved to the frame they point at."""
    out = {}
    for anim, v in img.items():
        if anim == "info" or not isinstance(v, dict) or "_uol" in v:
            continue
        frames = []
        for k in _int_keys(v):
            c = v[k]
            if isinstance(c, dict) and "_uol" in c:
                r = _resolve(img, anim, c)
                if r is not None:
                    frames.append((int(k), r[0], r[1], r[2]))
            elif isinstance(c, dict) and "_size" in c:
                frames.append((int(k), anim, int(k), c))
        if frames:
            out[anim] = frames
    return out


def build_mob(img: dict, mob_id: int, name: str | None, png_dir: Path, out_dir: Path, linked: dict | None = None,
              linked_png_dir: Path | None = None) -> dict:
    """mob.json + trimmed frame PNGs into out_dir. A mob whose info has `link` (and no frames of its own) is drawn
    with the linked mob's frames, as the game does. Returns the manifest entry."""
    info = img.get("info") or {}
    anims = _anims(img)
    if not anims and linked is not None:
        anims, png_dir = _anims(linked), linked_png_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    frames, books = {}, {}
    for anim, fr in anims.items():
        books[anim] = len(fr)
        for i, (n, src_anim, src_n, c) in enumerate(fr):   # files 0..count-1 in play order (client numbers can skip)
            src = png_dir / f"{src_anim}_{src_n}.png"
            if not src.exists():
                raise FileNotFoundError(f"mob {mob_id}: no frame picture {src}")
            shutil.copyfile(src, out_dir / f"{anim}_{i}.png")         # the client's canvas as is (not trimmed)
            frames.setdefault(anim, []).append(
                {"n": n, "file": f"{anim}_{i}.png", "size": c["_size"], "origin": c.get("origin"), "lt": c.get("lt"),
                 "rb": c.get("rb"), "head": c.get("head"), "delay": c.get("delay"),
                 **({"same": f"{src_anim}_{src_n}.png"} if (src_anim, src_n) != (anim, n) else {}),
                 **{k: v for k, v in c.items() if k not in ("origin", "lt", "rb", "head", "delay", "_size", "_hash")
                    and not isinstance(v, dict)}})
    m = {"id": mob_id, "name": name, "link": int(info["link"]) if info.get("link") else None,
         "info": info, "framebooks": books, "frames": frames}
    (out_dir / "mob.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    return {"name": name, "level": info.get("level"), "framebooks": books,
            "frames": sum(books.values()), "link": m["link"]}


# ------------------------------------------------------------------ everything
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_manifest(root: Path = ROOT) -> dict:
    p = root / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"maps": {}, "mobs": {}}


def build(export: Path = EXPORT, root: Path = ROOT, log=print) -> dict:
    """The whole game from a client export into `root` (rebuilt from scratch next to it, then swapped in: never a
    half-built or stale mix). Returns the manifest."""
    export, root = Path(export), Path(root)
    for need in ("Map", "Mob", "String/Map.img.xml", "String/Mob.img.xml"):
        if not (export / need).exists():
            raise FileNotFoundError(f"{export / need} missing - run tools/cwdata/export.ps1 first")
    new = root.with_name(root.name + ".new")
    if new.exists():
        shutil.rmtree(new)
    man = {"source": "Classic World client files, exported by tools/cwdata/export.ps1", "export": str(export),
           "built": _now(), "maps": {}, "mobs": {}}
    names = map_names(load_xml(export / "String" / "Map.img.xml"))
    mob_names = {int(k): v.get("name") for k, v in load_xml(export / "String" / "Mob.img.xml").items()
                 if k.isdigit() and isinstance(v, dict)}

    mob_xml = {int(p.name.split(".")[0]): p for p in (export / "Mob").glob("*.img.xml")}
    imgs = {}

    def mob_img(i):
        if i not in imgs:
            imgs[i] = load_xml(mob_xml[i])
        return imgs[i]

    for i in sorted(mob_xml):
        img = mob_img(i)
        link = (img.get("info") or {}).get("link")
        linked = mob_img(int(link)) if link and int(link) in mob_xml else None
        man["mobs"][str(i)] = build_mob(img, i, mob_names.get(i), export / "Mob" / "png" / f"{i:07d}",
                                        new / "mobs" / str(i), linked,
                                        export / "Mob" / "png" / f"{int(link):07d}" if link else None)
    log(f"mobs: {len(man['mobs'])}, {sum(e['frames'] for e in man['mobs'].values())} frames")

    from .cover import _Parts, build_cover, write_cover
    parts, n_cover = _Parts(export, load_xml), 0
    for p in sorted((export / "Map").glob("Map?/*.img.xml")):
        mid = int(p.name.split(".")[0])
        mini = export / "Map" / "minimap" / f"{p.name.split('.')[0]}.png"
        img = load_xml(p)
        m = map_json(img, mid, names, mini.read_bytes() if mini.exists() else None)
        d = new / "maps" / str(mid)
        d.mkdir(parents=True, exist_ok=True)
        meta, masks = build_cover(img, m, parts)             # what's drawn in front of mobs (cover.py)
        if meta:
            m["cover"] = meta
            write_cover(d, masks)
            n_cover += bool(masks)
        (d / "map.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        if mini.exists():
            shutil.copyfile(mini, d / "minimap.png")
        mob_ids = sorted({x["id"] for x in m["mobs"]})
        missing = [x for x in mob_ids if str(x) not in man["mobs"]]
        if missing:
            log(f"map {mid}: spawns mobs {missing} that aren't in the client's Mob data")
        man["maps"][str(mid)] = {"name": m["name"], "street": m["streetName"], "mobs": mob_ids,
                                 "footholds": len(m["footholds"]), "ladderRopes": len(m["ladderRopes"]),
                                 "minimap": mini.exists()}
    log(f"maps: {len(man['maps'])}, {sum(e['minimap'] for e in man['maps'].values())} with a minimap, "
        f"{n_cover} with cover masks")

    if (export / "Afterimage").exists():
        att = build_attacks(export)
        (new / "attacks.json").write_text(json.dumps(att, indent=1, sort_keys=True), encoding="utf-8")
        log(f"attack boxes: {len(att['weapons'])} weapon types" + (f", level brackets differ: {att['differs']}"
                                                                     if att["differs"] else ""))
    else:
        log("no Afterimage in the export (old export.ps1?): attacks.json not built - brain-v2 reach needs it")
    (new / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True), encoding="utf-8")
    report = changes(root, new)
    head = f"assets/mcw rebuilt {man['built']} from {export}: changes vs the previous build"
    (new / "changes.txt").write_text("\n".join([head, *report, ""]), encoding="utf-8")
    for line in report[:40]:
        log(f"  {line}")
    if len(report) > 40:
        log(f"  ... {len(report) - 40} more lines in changes.txt")
    old = root.with_name(root.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if root.exists():
        _rename(root, old)
    try:
        _rename(new, root)
    except OSError:
        if old.exists():
            _rename(old, root)                       # put the previous assets back
        raise
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    log(f"built {root} from {export}")
    return man


def _differs(a: Path, b: Path) -> bool:
    return not (a.exists() and b.exists() and a.read_bytes() == b.read_bytes())


def changes(old: Path, new: Path) -> list[str]:
    """What a rebuild changes, one line per map / mob (after a game patch: the list of things to look at again).
    Maps: which parts of map.json differ (footholds, mobs, miniMap ...) and the minimap picture; mobs: info values
    old -> new, framebooks, which frame pictures differ."""
    if not (old / "manifest.json").exists():
        return ["first build (nothing to compare with)"]
    out = []
    for kind, fname in (("maps", "map.json"), ("mobs", "mob.json")):
        a = {p.parent.name for p in (old / kind).glob(f"*/{fname}")}
        b = {p.parent.name for p in (new / kind).glob(f"*/{fname}")}
        for label, ids in (("added", b - a), ("removed", a - b)):
            if ids:
                out.append(f"{kind} {label}: {' '.join(sorted(ids, key=int))}")
        for i in sorted(a & b, key=int):
            ja, jb = (json.loads((r / kind / i / fname).read_text(encoding="utf-8")) for r in (old, new))
            what = []
            for k in sorted(set(ja) | set(jb)):
                if ja.get(k) == jb.get(k) or (kind == "mobs" and k == "frames"):
                    continue
                if kind == "mobs" and k == "info":
                    ia, ib = ja.get(k) or {}, jb.get(k) or {}
                    what += [f"{f} {ia.get(f)} -> {ib.get(f)}" for f in sorted(set(ia) | set(ib)) if ia.get(f) != ib.get(f)]
                else:
                    what.append(k)
            if kind == "mobs" and ja.get("frames") != jb.get("frames") and ja.get("framebooks") == jb.get("framebooks"):
                what.append("frame origins/boxes/delays")
            pics = sorted({p.name for r in (old, new) for p in (r / kind / i).glob("*.png")})
            pics = [n for n in pics if _differs(old / kind / i / n, new / kind / i / n)]
            if pics:
                what.append(f"pictures {', '.join(pics[:4])}" + (f" (+{len(pics) - 4})" if len(pics) > 4 else ""))
            if what:
                out.append(f"{kind[:-1]} {i} {jb.get('name') or ''}: {'; '.join(what)}")
    return out or ["no changes"]


def _rename(src: Path, dst: Path, tries: int = 20) -> None:
    """Windows: a folder full of just-written files is often briefly locked (virus scan, indexer) -> retry."""
    for i in range(tries):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.5)


def have_map(map_id: int, root: Path = ROOT) -> bool:
    """map.json and every mob that spawns there are in the assets."""
    mj = root / "maps" / str(map_id) / "map.json"
    if not mj.exists():
        return False
    m = json.loads(mj.read_text(encoding="utf-8"))
    return all((root / "mobs" / str(int(x["id"])) / "mob.json").exists() for x in m.get("mobs") or [])
