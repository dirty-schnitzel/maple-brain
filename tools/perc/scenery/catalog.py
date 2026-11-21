"""What the client files say moves, per map (PLAN-moving-scenery.md, measurement 1). No GPU, no footage.

    python tools/perc/scenery/catalog.py              every map with a scene: the table by kind -> OUT/catalog.json,
                                                      OUT/back_props.json (the background pictures' own properties)
    python tools/perc/scenery/catalog.py MAP [MAP..]  one map's background entries and special objects, as the files
                                                      have them

Read per map (the client export, tools/cwdata/export.ps1):
  back entries      type (0 plain, 1-3 tiled, 4 / 6 = moving sideways: `rx` is then a speed, 5 / 7 = moving up-down),
                    ani, front, rx / ry / cx / cy, a, f
  back pictures     the canvas' own properties: blend (1 = ADDED to what is under it), moveType / moveW / moveH / moveP
                    (a picture that bobs), a0 / a1, delay
  objects           several frames (animated), moveType, blend
  info.cloud        1 = the client draws its weather clouds (MapHelper.img/weather/cloud/0..6) over the field
  the two pictures of pixel format 1537 (a flat colour, export.ps1 decodes them wrong until the plan's step 1)"""
import json
import sys
from collections import Counter, defaultdict

import msl
from maplebrain.gamedata import load_xml

ASSETS = msl.ROOT / "assets" / "mcw"
SCENE = msl.ROOT / "assets" / "scene"
F1537 = {("back_midForest", "back", "0"), ("back_dryRock", "back", "0")}
KEYS = ("moveType", "moveW", "moveH", "moveP", "moveR", "a0", "a1", "delay", "blend")
_sets = {}


def _set(kind, name):
    key = (kind, name)
    if key not in _sets:
        p = msl.EXPORT / "Map" / kind / f"{name}.img.xml"
        _sets[key] = load_xml(p) if p.exists() else None
    return _sets[key]


def _frames(node):
    """(the canvases of a node, its own non-numbered properties)."""
    if not isinstance(node, dict):
        return [], {}
    if "_size" in node:
        return [node], {}
    fr = [v for _, v in sorted((int(k), v) for k, v in node.items() if k.isdigit() and isinstance(v, dict) and "_size" in v)]
    return fr, {k: v for k, v in node.items() if not k.isdigit()}


def _props(fr, extra):
    out = {}
    for f in fr:
        for k in KEYS:
            if k in f:
                out.setdefault(k, []).append(f[k])
    out = {k: (v[0] if len(set(map(str, v))) == 1 else v) for k, v in out.items()}
    if "blend" in extra:
        out["blend"] = extra["blend"]
    return out


def back_props() -> dict:
    """"<set>/<back|ani>/<no>" -> {frames, blend, moveType, ...} of every background picture that has any."""
    out = {}
    for p in sorted((msl.EXPORT / "Map" / "Back").glob("*.img.xml")):
        d = load_xml(p)
        for kind in ("back", "ani"):
            for no, c in (d.get(kind) or {}).items():
                fr, extra = _frames(c)
                pr = _props(fr, extra)
                if pr:
                    out[f"{p.name.split('.')[0]}/{kind}/{no}"] = {"frames": len(fr), **pr}
    return out


def describe(mid) -> dict:
    src = next((msl.EXPORT / "Map").glob(f"Map?/{int(mid):09d}.img.xml"))
    img = load_xml(src)
    out = {"cloud": int((img.get("info") or {}).get("cloud", 0) or 0), "backs": [], "objs": []}
    for k in sorted((img.get("back") or {}), key=lambda s: int(s) if str(s).isdigit() else 10 ** 9):
        b = img["back"][k]
        if not isinstance(b, dict) or not b.get("bS"):
            continue
        kind = "ani" if b.get("ani") else "back"
        fr, extra = _frames(((_set("Back", b["bS"]) or {}).get(kind) or {}).get(str(b.get("no", 0))))
        out["backs"].append({**{x: b.get(x) for x in ("bS", "no", "type", "front", "x", "y", "rx", "ry", "cx", "cy", "a", "f")},
                             "k": k, "kind": kind, "frames": len(fr), "props": _props(fr, extra)})
    for L in range(8):
        for o in ((img.get(str(L)) or {}).get("obj") or {}).values():
            if not isinstance(o, dict) or not o.get("oS"):
                continue
            node = _set("Obj", o["oS"])
            for part in (o.get("l0"), o.get("l1"), o.get("l2")):
                node = node.get(str(part)) if isinstance(node, dict) else None
            fr, extra = _frames(node)
            pr = _props(fr, extra)
            if len(fr) > 1 or pr:
                out["objs"].append({"L": L, "oS": o["oS"], "l": f"{o.get('l0')}/{o.get('l1')}/{o.get('l2')}", "frames": len(fr), "props": pr})
    return out


def kinds(d) -> dict:
    b = d["backs"]
    return {"cloud": bool(d["cloud"]), "type4": sum(x["type"] == 4 for x in b), "type6": sum(x["type"] == 6 for x in b),
            "type57": sum(x["type"] in (5, 7) for x in b), "ani_back": sum(x["kind"] == "ani" for x in b),
            "bob_back": sum("moveType" in x["props"] for x in b), "additive": sum(bool(x["props"].get("blend")) for x in b),
            "front_moving": sum(bool(x["front"]) and (x["type"] in (4, 5, 6, 7) or x["kind"] == "ani") for x in b),
            "f1537": sum((x["bS"], x["kind"], str(x["no"])) in F1537 for x in b),
            "anim_obj": sum(o["frames"] > 1 for o in d["objs"]), "move_obj": sum("moveType" in o["props"] for o in d["objs"]),
            "speeds": sorted({x["rx"] for x in b if x["type"] in (4, 6)}), "set": Counter(x["bS"] for x in b).most_common(1)[0][0] if b else ""}


def main():
    man = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    name = lambda m: f"{(man['maps'].get(str(m)) or {}).get('street', '')} / {(man['maps'].get(str(m)) or {}).get('name', '')}"
    if sys.argv[1:]:
        for mid in map(int, sys.argv[1:]):
            d = describe(mid)
            print(f"\n=== {mid} {name(mid)}; info.cloud {d['cloud']}")
            for b in d["backs"]:
                print(f"  back {b['k']:>2} {b['bS']}/{b['kind']}/{b['no']} type {b['type']} front {b['front']} x {b['x']} y {b['y']} rx {b['rx']} "
                      f"ry {b['ry']} cx {b['cx']} cy {b['cy']} a {b['a']} f {b['f']} frames {b['frames']} {b['props'] or ''}")
            for (L, oS, l, n, pr), c in sorted(Counter((o["L"], o["oS"], o["l"], o["frames"], json.dumps(o["props"])) for o in d["objs"]).items()):
                print(f"  obj L{L} {oS}/{l} x{c} frames {n} {pr}")
        return
    (msl.OUT / "back_props.json").write_text(json.dumps(back_props(), indent=0), encoding="utf-8")
    ids = sorted(int(p.name) for p in SCENE.iterdir() if p.name.isdigit() and (p / "scene.json").exists())
    rows, groups = {}, defaultdict(list)
    for mid in ids:
        k = kinds(describe(mid))
        meta = json.loads((SCENE / str(mid) / "scene.json").read_text(encoding="utf-8"))
        k["clean_today"] = all(b["known"] for b in meta["backs"])
        k["name"] = name(mid)
        rows[mid] = k
        key = [s for s, on in (("weather clouds", k["cloud"]), ("backs moving sideways (type 4)", k["type4"]),
                               ("backs moving sideways, tiled both ways (type 6)", k["type6"]),
                               ("backs that bob (moveType)", k["bob_back"]), ("animated backs", k["ani_back"])) if on]
        groups[" + ".join(key) or "nothing moves in the backs"].append(mid)
    (msl.OUT / "catalog.json").write_text(json.dumps(rows, indent=0), encoding="utf-8")
    print(f"{len(ids)} maps with a scene; clean today: {sum(r['clean_today'] for r in rows.values())}")
    for g, ms in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        r = [rows[m] for m in ms]
        print(f"{len(ms):4d} maps: {g}   [additive backs {sum(bool(x['additive']) for x in r)}, the mis-decoded flat picture "
              f"{sum(bool(x['f1537']) for x in r)}, animated objects {sum(bool(x['anim_obj']) for x in r)}, objects that move "
              f"{sum(bool(x['move_obj']) for x in r)}, a moving FRONT back {sum(bool(x['front_moving']) for x in r)}]")
        if len(ms) <= 8:
            for m in ms:
                print(f"         {m} {rows[m]['name']}")
    sp = defaultdict(Counter)
    for r in rows.values():
        for v in r["speeds"]:
            sp[r["set"]][v] += 1
    print("speeds (rx) of the moving backs per background set:", {k: dict(sorted(v.items())) for k, v in sorted(sp.items())})
    print("->", msl.OUT / "catalog.json", "and back_props.json")


if __name__ == "__main__":
    main()
