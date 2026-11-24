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
    items/items.npz             what a drop shows (PLAN-loot.md): every DISTINCT item picture (info/iconRaw of every
                                Etc / Use / Setup item and equip + the 16 meso frames), BGRA, packed (`load_items`)
    items/items.json            id -> name, kind, w, h, origin, `g` (its picture in items.npz), `same` (the picture
                                class's id: the meso's if a meso frame shows it, else the lowest id), `weak`, `link`
    slots/pack.npz, pack.json   the hotkey reader's pictures (perception/slots.py, PLAN-tracker step 7): the
                                quickslot bar, its key labels and digits, every item / skill / action picture as a
                                cell shows it, with their ids, names and specs (the export's Slots\\)
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

import numpy as np

ROOT =Path(__file__).resolve().parents[1] / "assets" / "mcw"
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


# ------------------------------------------------------------------ items (what a drop shows; PLAN-loot.md)
MESO_NAMES = {9000000: "Meso (bronze)", 9000001: "Meso (gold)", 9000002: "Meso (bundle)", 9000003: "Meso (sack)"}
WEAK_FEATURES = 16      # a picture with fewer usable features than this cannot reach the vote's candidate bar
WEAK_PLACES = 64        # usable feature = its key occurs in <= this many places of all pictures (Voter max_entries)


def _key24(bgr):
    return bgr[..., 0].astype(np.int64) | (bgr[..., 1].astype(np.int64) << 8) | (bgr[..., 2].astype(np.int64) << 16)


def item_features(pics: list) -> tuple:
    """The vote's material per picture (perception/vote.py Voter's rule): features = 2x2 blocks of opaque pixels
    (alpha 255) that are not one flat colour; usable = its colour key occurs in <= WEAK_PLACES places over all `pics`.
    -> (n_feat, kept) int arrays."""
    cols = np.unique(np.concatenate([_key24(p[..., :3])[p[..., 3] == 255] for p in pics]))
    r = len(cols) + 1
    keys, owner = [], []
    for g, p in enumerate(pics):
        ids = np.where(p[..., 3] == 255, np.searchsorted(cols, _key24(p[..., :3])) + 1, 0).astype(np.int64)
        a, b, c, d = ids[:-1, :-1], ids[:-1, 1:], ids[1:, :-1], ids[1:, 1:]
        ok = (a > 0) & (b > 0) & (c > 0) & (d > 0) & ~((a == b) & (a == c) & (a == d))
        keys.append(((a[ok] * r + b[ok]) * r + c[ok]) * r + d[ok])
        owner.append(np.full(int(ok.sum()), g))
    k, own = np.concatenate(keys), np.concatenate(owner)
    _, inv, cnt = np.unique(k, return_inverse=True, return_counts=True)
    return (np.bincount(own, minlength=len(pics)),
            np.bincount(own[cnt[inv] <= WEAK_PLACES], minlength=len(pics)))


def _item_pictures(export: Path) -> tuple:
    """Item/items.json + png of the export -> ([(id, frame, BGRA, (ox, oy), delay)] mesos first, then items by id,
    the export's items.json)."""
    import cv2
    d = Path(export) / "Item"
    meta = json.loads((d / "items.json").read_text(encoding="utf-8-sig"))
    out = []
    for sid in sorted(meta, key=lambda s: (meta[s]["kind"] != "Meso", int(s))):
        e = meta[sid]
        files = ([(f"{sid}_raw_{k}.png", fr[2:4], fr[4]) for k, fr in enumerate(e["frames"])] if e["kind"] == "Meso"
                 else [(f"{sid}_raw.png", e["raw"][2:4], 0)])
        for k, (fn, org, delay) in enumerate(files):
            pic = cv2.imread(str(d / "png" / fn), cv2.IMREAD_UNCHANGED)
            if pic is None:
                raise FileNotFoundError(f"item {sid}: no picture {d / 'png' / fn}")
            if pic.ndim == 2:
                pic = cv2.cvtColor(pic, cv2.COLOR_GRAY2BGRA)
            elif pic.shape[2] == 3:
                pic = cv2.cvtColor(pic, cv2.COLOR_BGR2BGRA)
            out.append((int(sid), k, np.ascontiguousarray(pic), tuple(org), int(delay)))
    return out, meta


def item_classes(entries: list) -> tuple:
    """Pixel-identical pictures are ONE class (a drop of such a picture can't be told apart by sight). `entries`:
    [(id, frame, BGRA, ...)]. The class's id = the meso's if a meso frame is in it (mesos are what drops most), else
    the lowest id; the class's picture = that member's. Independent of the input order.
    -> ([(class id, frame, BGRA, member index)] in a fixed order: mesos, then by class id), {entry index: class index}."""
    rank = lambda e: (e[0] < 9000000, e[0], e[1])                    # noqa: E731  mesos first, then the lowest id
    groups = {}
    for i, e in enumerate(entries):
        groups.setdefault((e[2].shape, e[2].tobytes()), []).append(i)
    reps = sorted((min(ix, key=lambda i: rank(entries[i])), ix) for ix in groups.values())
    reps.sort(key=lambda r: rank(entries[r[0]]))
    classes, of = [], {}
    for c, (rep, ix) in enumerate(reps):
        e = entries[rep]
        classes.append((e[0], e[1], e[2], rep))
        for i in ix:
            of[i] = c
    return classes, of


def build_items(export: Path, out: Path, log=print) -> dict:
    """Item pictures of the export -> out/items.npz (every distinct picture, BGRA, packed) + out/items.json.
    Returns a summary (counts, the weak pictures' names)."""
    entries, meta = _item_pictures(export)
    classes, of = item_classes(entries)
    pics = [c[2] for c in classes]
    n_feat, kept = item_features(pics)
    weak = kept < WEAK_FEATURES
    # a cash-shop (NX) item never drops: a picture is `cash` when every id showing it is one (the finder skips it)
    cash = np.ones(len(pics), bool)
    for i, e in enumerate(entries):
        if not (meta.get(f"{e[0]:08d}") or {}).get("cash"):
            cash[of[i]] = False
    out.mkdir(parents=True, exist_ok=True)
    hw = np.array([p.shape[:2] for p in pics], np.int32)
    size = hw[:, 0].astype(np.int64) * hw[:, 1]
    np.savez_compressed(out / "items.npz", pix=np.concatenate([p.reshape(-1, 4) for p in pics]),
                        start=np.concatenate([[0], np.cumsum(size)[:-1]]).astype(np.int64), hw=hw,
                        org=np.array([entries[c[3]][3] for c in classes], np.int32),
                        item=np.array([c[0] for c in classes], np.int32), f=np.array([c[1] for c in classes], np.int16),
                        delay=np.array([entries[c[3]][4] for c in classes], np.int16),
                        n_feat=n_feat.astype(np.int32), kept=kept.astype(np.int32), weak=weak, cash=cash)
    items = {}
    for i, (iid, k, pic, org, delay) in enumerate(entries):
        g = of[i]
        if k == 0:
            e = meta[f"{iid:08d}"]
            items[str(iid)] = {"name": MESO_NAMES.get(iid, e.get("name")), "kind": e["kind"], "w": int(pic.shape[1]),
                               "h": int(pic.shape[0]), "o": list(org), "g": g, "same": classes[g][0],
                               **({"same_f": classes[g][1]} if classes[g][1] else {}), "weak": bool(weak[g]),
                               **({"link": int(e["link"])} if e.get("link") else {}),
                               **({"cash": True} if e.get("cash") else {})}
            if e["kind"] == "Meso":
                items[str(iid)]["frames"] = []
        if iid >= 9000000 and meta[f"{iid:08d}"]["kind"] == "Meso":
            items[str(iid)]["frames"].append({"g": g, "w": int(pic.shape[1]), "h": int(pic.shape[0]), "o": list(org),
                                              "delay": delay})
    n_link = sum("link" in e for e in items.values())
    doc = {"source": "Classic World client: info/iconRaw of every Etc / Consume / Install item and equip + the meso "
                     "frames (tools/cwdata/export.ps1 -> assets build)",
           "pictures": len(pics), "ids": len(items), "linked": n_link, "weak_count": int(weak.sum()),
           "cash_ids": sum(1 for e in items.values() if e.get("cash")), "cash_pictures": int(cash.sum()),
           "searched": int((~weak & ~cash).sum()), "weak_rule": f"< {WEAK_FEATURES} features "
           f"(2x2 opaque blocks, not one flat colour) whose key occurs in <= {WEAK_PLACES} places over all pictures",
           "items": items}
    (out / "items.json").write_text(json.dumps(doc, indent=0, ensure_ascii=False), encoding="utf-8")
    n_pic = sum(len(e["frames"]) if e["kind"] == "Meso" else 1 for e in items.values())
    weak_names = sorted({(classes[g][0], items[str(classes[g][0])]["name"] or str(classes[g][0]))
                         for g in np.flatnonzero(weak)})
    log(f"items: {len(items)} ids ({n_link} by a link), {n_pic} pictures -> {len(pics)} distinct, "
        f"{int(weak.sum())} weak, {int(cash.sum())} cash-only (never drop) -> {doc['searched']} searched")
    return {"ids": len(items), "linked": n_link, "pictures": n_pic, "distinct": len(pics), "weak": weak_names,
            "cash": int(cash.sum()), "searched": doc["searched"]}


class ItemPictures:
    """assets/mcw/items as built: `pics[g]` BGRA uint8 (h, w, 4) of distinct picture g; `item[g]` its class id,
    `f[g]` meso frame, `org[g]` the file origin, `delay[g]`, `weak[g]`, `cash[g]` (every id showing it is a cash-shop
    item: never drops), `kept[g]` / `n_feat[g]` (usable / all features); `meta` = items.json's items (str id ->
    {name, kind, w, h, o, g, same, weak, link?, cash?, frames?}). The finder searches ~weak & ~cash."""

    def __init__(self, root: Path | None = None):
        d = Path(root or ROOT) / "items"
        z = np.load(d / "items.npz")
        pix, start, hw = z["pix"], z["start"], z["hw"]
        self.pics = [pix[s:s + h * w].reshape(h, w, 4) for s, (h, w) in zip(start, hw)]
        for k in ("item", "f", "org", "delay", "weak", "kept", "n_feat"):
            setattr(self, k, z[k])
        self.cash = z["cash"] if "cash" in z.files else np.zeros(len(self.pics), bool)
        self.doc = json.loads((d / "items.json").read_text(encoding="utf-8"))
        self.meta = self.doc["items"]

    def __len__(self):
        return len(self.pics)

    def name(self, iid) -> str:
        e = self.meta.get(str(int(iid))) or {}
        return e.get("name") or str(int(iid))

    def kind(self, iid) -> str:
        return (self.meta.get(str(int(iid))) or {}).get("kind", "?")

    def members(self, g: int) -> list:
        """Every id whose picture is g (mesos: by any frame)."""
        return sorted(int(i) for i, e in self.meta.items()
                      if e.get("g") == g or any(fr["g"] == g for fr in e.get("frames") or []))


def load_items(root: Path | None = None) -> ItemPictures:
    return ItemPictures(root)


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
    if (export / "Item" / "items.json").exists():
        s = build_items(export, new / "items", log)
        man["items"] = {**{k: s[k] for k in ("ids", "linked", "pictures", "distinct", "cash", "searched")},
                        "weak": len(s["weak"])}
    else:
        log("no Item in the export (old export.ps1?): items not built - drops (PLAN-loot.md) need them")
    if (export / "Slots" / "item" / "items.json").exists():
        from .perception.slots import build_pack
        man["slots"] = build_pack(export / "Slots", new / "slots", log)
    else:
        log("no Slots in the export (old export.ps1?): the hotkey reader's pack not built (tools/cwdata/"
            "export_slots.ps1)")
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
    out += _item_changes(old, new)
    out += _slot_changes(old, new)
    return out or ["no changes"]


def _slot_changes(old: Path, new: Path) -> list[str]:
    """One line: the hotkey reader's pack (slots/) - its pictures, labels, digits or members changed."""
    have = [(r / "slots" / "pack.npz").exists() for r in (old, new)]
    if not any(have):
        return []
    if not all(have):
        return ["slots: " + ("first build" if have[1] else "removed")]
    za, zb = (np.load(r / "slots" / "pack.npz") for r in (old, new))
    ja, jb = (json.loads((r / "slots" / "pack.json").read_text(encoding="utf-8")) for r in (old, new))
    what = [k for k in ("panels", "digit", "digit_w", "label", "content")
            if za[k].shape != zb[k].shape or not np.array_equal(za[k], zb[k])]
    what += [k for k in ("labels", "members") if ja.get(k) != jb.get(k)]
    return [f"slots: {', '.join(what)} changed ({ja['counts']} -> {jb['counts']})"] if what else []


def _item_changes(old: Path, new: Path) -> list[str]:
    """One line: item ids added / removed, ids whose picture changed (pixels) or whose name changed."""
    have = [(r / "items" / "items.npz").exists() for r in (old, new)]
    if not any(have):
        return []
    if not all(have):
        return ["items: " + ("first build" if have[1] else "removed")]
    a, b = ItemPictures(old), ItemPictures(new)

    def pic(x, e):
        return [x.pics[fr["g"]].tobytes() for fr in e["frames"]] if e.get("frames") else x.pics[e["g"]].tobytes()

    ia, ib = set(a.meta), set(b.meta)
    common = sorted(ia & ib, key=int)
    pix = [i for i in common if pic(a, a.meta[i]) != pic(b, b.meta[i])]
    nam = [i for i in common if a.meta[i].get("name") != b.meta[i].get("name")]
    parts = [f"{lbl} {len(s)} ({' '.join(sorted(s, key=int)[:8])}{' ...' if len(s) > 8 else ''})"
             for lbl, s in (("added", ib - ia), ("removed", ia - ib), ("picture changed", pix), ("renamed", nam)) if s]
    return [f"items: {'; '.join(parts)}"] if parts else []


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
