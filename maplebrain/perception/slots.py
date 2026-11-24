"""The hotkey reader (PLAN-tracker step 7; the reference: tools/perc/track/proto_slots.py, measurement 8): for every
key of the quickslot bar at the bottom right of the game window, what is on it (an item, a skill, a key-binding
action, nothing) and the item's amount, read EXACTLY from the frame. What a key holds over time (the amounts' steps)
is tracked in maplebrain/track/us.py; this module only says what one frame shows (FrameFacts `slots`).

WHAT THE CLIENT DRAWS (measured 2026-11-23 on frames of 2026-11-16 .. 11-23; every picture is the client's own,
tools/cwdata/export_slots.ps1 -> `assets build` -> assets/mcw/slots; nothing here is a guess unless it says ASSUMED):
  - The bar = UI/QuickSlot.img `layer:backgrnd` (151 x 114, 2 rows of 4 keycaps; `layer:3row_background` has 3 rows -
    never seen in footage), its corner at frame (933, 588) in the native 1366x768 window. A slot's cell is 32 x 32 px:
    column c at panel x 7 + 35 c; the 2 rows at panel y 41 and 75 (QuickSlot.img `2ndRowOffset` = 34).
  - A cell is drawn in this order, each layer laid over the last with plain alpha, rounded
    (c * a + d * (255 - a) + 127) // 255 - the frame's pixels equal this composite EXACTLY:
      1. the keycap (the panel picture);
      2. the content, its picture's origin at the cell's (0, 32): an item = its `info/icon` (the picture WITH the
         shadow - not `iconRaw`, which is what lies on the ground), a key-binding action = UI/KeyBindings.img
         `icon/<id>` (32 x 32, "JUMP" ...), a skill = Skill `skill/<id>/icon`. Clipped to the cell (seen on the left
         edge: The Green Relaxer's column at x = -1 is not drawn);
      3. an item's amount: UI/Basic.img `ItemNo/<digit>` glyphs (8 x 11, the "1" 5 x 11; alpha 0 or 255 only), the
         first at the cell's (0, 20), each next one right after the last, no gap. An item that shows no amount
         (a chair) has none; an item whose last one was used keeps its picture and shows "0";
      4. the key's label: UI/QuickSlot.img `key/<scan code>` at the cell's (2, 2), opaque letters over everything.
    Nothing else was drawn on a slot when its key was pressed (no flash on `end` / `delete`).
  - Which key a slot belongs to is the label's picture, never its position (the client has a dialog that assigns the
    bar's keys: UI/KeyBindings.img `quickslot/button:slot0..11`). Two keys share one label picture: "O" (scan 24) is
    drawn with the "0"'s (scan 11) - such a label reads as its first key, `Pack.lab_also` names the others.

HOW THE READER WORKS: per cell, (1) the label = the key picture whose opaque pixels all equal the frame; (2) the
amount = digit glyphs matched left to right from (0, 20), every opaque pixel equal; (3) the content = looked up by
the bytes of the cell's rows 15..19 (no label or digit ever lies there) among the composites of every item / skill /
action picture over the keycap, then (4) VERIFIED: keycap + content + digits + label composed must equal all 1024
pixels of the cell. A read is exact or it is nothing (`kind` None: covered by the cursor, a tooltip, a window, the
fade of a map change, or not the bar) - never a nearest match. `SlotReader` keeps each cell's last pixels and reads a
cell again only when they changed.

Game data in the pack: items by id with the client's names and what using one does (the item's `spec`: hp, mp ...),
skills, actions by the id of their picture (ACTIONS: the words ON the pictures). Several items can share one picture
(Red Potion 2000000 and 2000007): the reader gives the lowest id of the usable kinds, `Pack.same(kind, id)` the rest.
"""
import json
import time
from pathlib import Path
from typing import NamedTuple

import numpy as np

PACK_DIR = Path(__file__).resolve().parents[2] / "assets" / "mcw" / "slots"

# ---- geometry (frame px, the native 1366x768 window) -------------------------------------------------------------
BX, BY = 933, 588                      # the panel picture's corner in the frame (measured: 9,564 opaque px placed)
CELL = 32                              # a slot's cell
COL0, PITCH_X = 7, 35                  # panel x of column 0, the columns' pitch
ROWS = {2: (41, 75), 3: (7, 41, 75)}   # panel y of the rows: the 2-row bar, the 3-row one (never seen in footage)
LABEL_AT = (2, 2)                      # the key label's corner in the cell
LABEL_H, LABEL_W = 13, 34              # the largest label picture this reader allows ("Pup" is 13 tall)
DIGITS_AT = (0, 20)                    # the first amount digit's corner in the cell
DIGIT_H, DIGIT_W = 11, 8
FP_ROWS = slice(15, 20)                # the cell rows no label (rows 2..14) and no digit (rows 20..30) covers
SIG_GAP = 3                            # the bar's own pixels this far from every cell = "the bar is shown" signature
SIG_BOTTOM = 107                       # ... above this panel row: from it down the status bar's shadow lies over the
                                       # bar (measured: 155 of the 438 opaque border px differ there on a clean frame)

# scan code of UI/QuickSlot.img key/<code> -> the key's name as maplebrain names keys (keyboard.SCAN / EXTENDED,
# runtime/keylog.py)
KEY_NAMES = {1: "esc", 12: "-", 13: "=", 26: "[", 27: "]", 29: "ctrl", 39: ";", 40: "'", 41: "`", 42: "shift",
             43: "\\", 51: ",", 52: ".", 56: "alt", 57: "space", 70: "scrolllock", 71: "home", 73: "pageup",
             79: "end", 81: "pagedown", 82: "insert", 83: "delete", 87: "f11", 88: "f12"}
for _i, _c in enumerate("1234567890"):
    KEY_NAMES[2 + _i] = _c
for _row, _start in (("qwertyuiop", 16), ("asdfghjkl", 30), ("zxcvbnm", 44)):
    for _i, _c in enumerate(_row):
        KEY_NAMES[_start + _i] = _c
for _i in range(10):
    KEY_NAMES[59 + _i] = f"f{_i + 1}"
# the bar's keys by position, used ONLY to name a slot whose label was never read (the layout of every capture in the
# bank, 2026-11-16..24)
DEFAULT_KEYS = {2: ("shift", "insert", "home", "pageup", "ctrl", "delete", "end", "pagedown"),
                3: tuple(f"slot{i}" for i in range(12))}
# UI/KeyBindings.img icon/<id>: the words on each picture (read by eye from the export; the ids are the client's)
ACTIONS = {0: "EQUIPMENT", 1: "ITEM", 2: "ABILITY", 3: "SKILL", 4: "BUDDY", 5: "WORLD MAP", 6: "MAPLE CHAT",
           7: "MINI MAP", 8: "QUEST", 9: "SET KEY", 10: "TO ALL", 11: "WHISPER", 12: "TO PARTY", 13: "TO BUDDY",
           14: "SHORT CUT", 15: "QUICK SLOT", 16: "CHAT+", 19: "PARTY", 22: "CASH SHOP", 45: "CHANNEL", 46: "MENU",
           47: "SCREEN SHOT", 48: "PICTURE MODE", 50: "PICK UP", 51: "SIT", 52: "ATTACK", 53: "JUMP",
           54: "NPC CHAT", 55: "CRAFTING", 58: "MAILBOX", 100: "face 1", 101: "face 2", 102: "face 3",
           103: "face 4", 104: "face 5", 105: "face 6", 106: "face 7", 202: "MUTE", 204: "KEYS1", 205: "KEYS2",
           206: "KEYS3", 300: "MOVE LEFT", 301: "MOVE RIGHT", 302: "MOVE UP", 303: "MOVE DOWN", 400: "OK",
           401: "CANCEL"}
KIND_ORDER = ("Consume", "Cash", "Install", "Etc", "Pet")       # an item's kinds a key can hold come first


# ---- the pack: built by `assets build` from the export ------------------------------------------------------------
def _png(p: Path) -> np.ndarray:
    import cv2
    a = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if a is None:
        raise FileNotFoundError(f"unreadable picture {p}")
    if a.ndim == 2:
        a = cv2.cvtColor(a, cv2.COLOR_GRAY2BGRA)
    if a.shape[2] == 3:
        a = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])
    return a


def place(pic: np.ndarray, ox: int, oy: int) -> np.ndarray:
    """A picture in a slot's cell (32 x 32 BGRA): its origin at the cell's (0, 32), clipped to the cell."""
    out = np.zeros((CELL, CELL, 4), np.uint8)
    h, w = pic.shape[:2]
    x0, y0 = -ox, CELL - oy
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(w, CELL - x0), min(h, CELL - y0)
    if sx1 > sx0 and sy1 > sy0:
        out[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] = pic[sy0:sy1, sx0:sx1]
    return out


def build_pack(src: Path, out: Path, log=print) -> dict:
    """The export's Slots folder (tools/cwdata/export_slots.ps1) -> out/pack.npz (the bar's two panels, the digit
    glyphs, the key labels, every distinct content picture placed in a cell, BGRA) + out/pack.json (per label its key
    and the other keys drawn with the same picture; per content picture its members: kind, id, name, the item's spec /
    flags or the skill's job). Returns the counts."""
    src, out = Path(src), Path(out)
    q = src / "ui" / "png" / "QuickSlot"
    panels = np.stack([_png(q / "layer_backgrnd.png"), _png(q / "layer_3row_background.png")])
    digit = np.zeros((10, DIGIT_H, DIGIT_W, 4), np.uint8)
    digit_w = np.zeros(10, np.int32)
    for d in range(10):
        g = _png(src / "ui" / "png" / "ItemNo" / f"{d}.png")
        if g.shape[0] != DIGIT_H or g.shape[1] > DIGIT_W or set(np.unique(g[..., 3])) - {0, 255}:
            raise ValueError(f"ItemNo/{d}: {g.shape}, alpha {np.unique(g[..., 3])} - not the glyphs this reader knows")
        digit[d, :, :g.shape[1]] = g
        digit_w[d] = g.shape[1]
    labels, lab_meta = [], []
    for p in sorted((q / "key").glob("*.png"), key=lambda p: (not p.stem.isdigit(),
                                                              int(p.stem) if p.stem.isdigit() else 0, p.stem)):
        g = _png(p)
        h, w = g.shape[:2]
        if h > LABEL_H or w > LABEL_W:
            raise ValueError(f"key label {p.name}: {w} x {h} - larger than this reader allows for")
        a = np.zeros((LABEL_H, LABEL_W, 4), np.uint8)
        a[:h, :w] = g
        a[a[..., 3] == 0] = 0                                  # (the colour under alpha 0 is never drawn)
        code = int(p.stem) if p.stem.isdigit() else None
        key = KEY_NAMES.get(code, p.stem.lower())
        twin = next((m for m, b in zip(lab_meta, labels) if np.array_equal(a, b)), None)
        if twin is not None:                                   # one picture for two keys (the client's key/24 "O"
            twin["also"].append(key)                           # is drawn as key/11 "0")
            continue
        labels.append(a)
        lab_meta.append({"code": p.stem, "key": key, "w": w, "h": h, "also": []})
    members, classes, index = [], [], {}

    def add(kind, cid, name, pic, ox, oy, extra=None):
        c = place(pic, ox, oy)
        if not (c[..., 3] > 0).any():
            return False
        c[c[..., 3] == 0] = 0
        b = c.tobytes()
        j = index.get(b)
        if j is None:
            j = index[b] = len(classes)
            classes.append(c)
            members.append([])
        members[j].append({"kind": kind, "id": cid, "name": name, **(extra or {})})
        return True

    items = json.loads((src / "item" / "items.json").read_text(encoding="utf-8-sig"))
    order = {k: i for i, k in enumerate(KIND_ORDER)}
    n_item = n_blank = 0
    for iid, e in sorted(items.items(), key=lambda kv: (order.get(kv[1]["kind"], 99), int(kv[0]))):
        w, h, ox, oy = e["icon"]
        extra = {"group": e["kind"], **{f: e[f] for f in ("spec", "slotMax", "timeLimited", "accountSharable", "cash",
                                                          "recoveryHP", "recoveryMP") if f in e}}
        ok = add("item", int(iid), e.get("name"), _png(src / "item" / f"{iid}.png"), ox, oy, extra)
        n_item += ok
        n_blank += not ok
    skills = json.loads((src / "skill" / "skills.json").read_text(encoding="utf-8-sig"))
    n_skill = 0
    for sid, e in sorted(skills.items(), key=lambda kv: int(kv[0])):
        for field, suffix, kind in (("icon", "", "skill"), ("iconDisabled", "_d", "skill_disabled"),
                                    ("iconMouseOver", "_m", "skill_mouseover")):
            if field in e:
                w, h, ox, oy = e[field]
                n_skill += add(kind, int(sid), e.get("name"), _png(src / "skill" / f"{sid}{suffix}.png"), ox, oy,
                               {"job": e.get("job")})
    n_act = 0
    for p in sorted((src / "ui" / "png" / "action").glob("*.png"), key=lambda p: int(p.stem)):
        pic = _png(p)
        n_act += add("action", int(p.stem), ACTIONS.get(int(p.stem), f"action {p.stem}"), pic, 0, pic.shape[0])
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "pack.npz", panels=panels, digit=digit, digit_w=digit_w, label=np.stack(labels),
                        content=np.stack(classes))
    shared = sum(1 for m in members if len({(x["kind"], x["id"]) for x in m}) > 1)
    counts = {"items": n_item, "items_blank_in_cell": n_blank, "skill_pictures": n_skill, "actions": n_act,
              "classes": len(classes), "shared": shared, "labels": len(labels)}
    meta = {"source": "Classic World client: UI QuickSlot / Basic ItemNo / KeyBindings icon, every item's info/icon, "
                      "every skill's icons (tools/cwdata/export_slots.ps1 -> assets build)",
            "labels": lab_meta, "members": members, "counts": counts}
    (out / "pack.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"slots: {len(classes)} distinct pictures ({n_item} items, {n_skill} skill pictures, {n_act} actions; "
        f"{n_blank} items show nothing in a cell; {shared} shared by more than one id), {len(labels)} key labels "
        f"(one picture for several keys: {[[m['key']] + m['also'] for m in lab_meta if m['also']]})")
    return counts


# ---- the reader ----------------------------------------------------------------------------------------------------
class Read(NamedTuple):
    """One slot on one frame. `kind`: "item" / "skill" / "skill_disabled" / "skill_mouseover" / "action" / "empty",
    or None = not readable on this frame (`why` says what was missing; `key`, `id`, `amount` are None then: a label
    that fits a cell whose rest does not is no proof - the white letters of "S" fit any white window). `key`: the
    key on the slot's label. `id`: the item's / skill's / action's id. `amount`: the number drawn on an item (None:
    none drawn). `cls`: the content picture's index in the pack (-1: empty or
    unread). `alts`: the other pictures (pack indices, -1 = the bare keycap) that explain the cell's pixels just as
    exactly - they differ from `cls` only where the label or the digits lie (seen in the self-test only)."""
    key: str | None
    kind: str | None
    id: int | None
    amount: int | None
    cls: int = -1
    why: str = ""
    alts: tuple = ()

    @property
    def exact(self) -> bool:
        return self.kind is not None

    def fact(self) -> list | None:
        """[kind, id, amount] (FrameFacts `slots`), None when not readable."""
        return None if self.kind is None else [self.kind, self.id, self.amount]


NO_LABEL = "no key label"
NO_CONTENT = "the label is there, the rest is no client picture"
NO_MATCH = "the label is there, pixels lie over the slot"


def _key32(bgr: np.ndarray) -> np.ndarray:
    """(..., 3) uint8 pixels -> (...) uint32, one number per pixel (so a comparison is one operation)."""
    buf = np.zeros((*bgr.shape[:-1], 4), np.uint8)
    buf[..., :3] = bgr
    return buf.view(np.uint32)[..., 0]


def over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """BGRA `src` laid over BGR `dst` the way the client does it (measured: exact on every pixel)."""
    a = src[..., 3:4].astype(np.uint32)
    return ((src[..., :3].astype(np.uint32) * a + dst.astype(np.uint32) * (255 - a) + 127) // 255).astype(np.uint8)


class Hint(NamedTuple):
    label: int | None
    cls: int


class Pack:
    """The pictures + everything derived from them once: per cell the keycap, per content its composite's
    fingerprint, per label / digit the pixels that must match. `root`: the folder of pack.npz / pack.json."""

    def __init__(self, rows: int = 2, root: Path | None = None):
        root = Path(root or PACK_DIR)
        if not (root / "pack.npz").exists():
            raise FileNotFoundError(f"{root / 'pack.npz'} is missing: python -m maplebrain assets build")
        z = np.load(root / "pack.npz")
        self.meta = json.loads((root / "pack.json").read_text(encoding="utf-8"))
        self.rows = rows
        self.panel = z["panels"][0 if rows == 2 else 1]
        self.content = z["content"]                              # (N, 32, 32, 4)
        self.members = self.meta["members"]
        self.pcells = [(COL0 + PITCH_X * c, y) for y in ROWS[rows] for c in range(4)]      # in the panel picture
        self.cells = [(BX + x, BY + y) for x, y in self.pcells]                              # in the frame
        self.default_keys = DEFAULT_KEYS[rows]
        self.bg = [np.ascontiguousarray(self.panel[y:y + CELL, x:x + CELL, :3]) for x, y in self.pcells]
        # the cell pixels where the panel is not fully opaque (4 corner px of the 4 corner cells, alpha 253 / 254):
        # the world shows through by one grey level - never compared
        self.unsure = [self.panel[y:y + CELL, x:x + CELL, 3] != 255 for x, y in self.pcells]
        self.has_unsure = [bool(u.any()) for u in self.unsure]
        # the labels, clipped to the cell: region = the cell's rows 2..14, columns 2..31
        lx, ly = LABEL_AT
        lw = CELL - lx
        lab = z["label"][:, :, :lw]                               # (n, 13, 30, 4)
        self.lab32 = _key32(lab[..., :3])
        self.lab_tr = lab[..., 3] != 255                          # where the label is not opaque: anything fits
        self.lab_n = (~self.lab_tr).reshape(len(lab), -1).sum(1)
        self.lab_idx = [np.flatnonzero(~t.ravel()) for t in self.lab_tr]
        self.lab_val = [self.lab32[i].ravel()[ix] for i, ix in enumerate(self.lab_idx)]
        self.lab_key = [m["key"] for m in self.meta["labels"]]
        self.lab_also = [m.get("also", []) for m in self.meta["labels"]]
        self.lab_reg = (slice(ly, ly + LABEL_H), slice(lx, lx + lw))
        self.lab_layer = []                                       # per label: what laying it over a cell changes
        for a in lab:
            layer = np.zeros((CELL, CELL, 4), np.uint8)
            layer[self.lab_reg] = a
            al = layer[..., 3].ravel()
            io = np.flatnonzero(al == 255)
            isemi = np.flatnonzero((al > 0) & (al < 255))
            col = layer[..., :3].reshape(-1, 3)
            a_s = al[isemi].astype(np.uint32)[:, None]
            self.lab_layer.append((io, col[io].copy(), isemi, col[isemi].astype(np.uint32) * a_s + 127, 255 - a_s))
        dg = z["digit"]
        self.dg_col = np.ascontiguousarray(dg[..., :3])           # (10, 11, 8, 3)
        self.dg_opq = dg[..., 3] == 255
        self.dg32 = _key32(dg[..., :3])
        self.dg_tr = ~self.dg_opq
        self.dg_w = [int(w) for w in z["digit_w"]]
        # the fingerprints: rows FP_ROWS of every content's composite over the keycap -> its classes. The keycap's
        # rows there are the same in every cell (checked here), so one table serves all cells
        fp_bg = self.bg[0][FP_ROWS]
        self.one_table = all(np.array_equal(b[FP_ROWS], fp_bg) for b in self.bg)
        self._tables = {}
        self._comp = {}                                           # (cell, cls) -> the keycap + content composite
        self._sig = None

    def table(self, k: int) -> dict:
        key = 0 if self.one_table else k
        t = self._tables.get(key)
        if t is None:
            t = {}
            comp = over(self.bg[k][FP_ROWS][None], self.content[:, FP_ROWS])        # (N, 5, 32, 3)
            for j in range(len(comp)):
                t.setdefault(comp[j].tobytes(), []).append(j)
            t.setdefault(np.ascontiguousarray(self.bg[k][FP_ROWS]).tobytes(), []).insert(0, -1)   # the bare keycap
            self._tables[key] = t
        return t

    def composite(self, k: int, cls: int) -> np.ndarray:
        c = self._comp.get((k, cls))
        if c is None:
            c = self.bg[k] if cls < 0 else over(self.bg[k], self.content[cls])
            if len(self._comp) > 512:
                self._comp.clear()
            self._comp[(k, cls)] = c
        return c

    # -- names
    def member(self, cls: int) -> dict:
        return self.members[cls][0]

    def name(self, cls: int) -> str:
        if cls < 0:
            return "empty"
        m = self.member(cls)
        return m.get("name") or f"{m['kind']} {m['id']}"

    def same(self, kind: str, cid: int) -> list:
        """Every (kind, id, name) that shows the same picture as this one."""
        for ms in self.members:
            if any(m["kind"] == kind and m["id"] == cid for m in ms):
                return [(m["kind"], m["id"], m.get("name")) for m in ms]
        return []

    def info(self, kind: str, cid: int) -> dict:
        """The pack's entry of (kind, id): name, the item's group / spec / slotMax ..., the skill's job ({}: none)."""
        for ms in self.members:
            for m in ms:
                if m["kind"] == kind and m["id"] == cid:
                    return m
        return {}

    # -- the bar itself
    def signature(self):
        """(ys, xs, colours) in the frame: the bar's own opaque pixels at least SIG_GAP px from every cell - what
        shows that the bar is there and nothing lies over it as a whole."""
        if self._sig is None:
            m = self.panel[..., 3] == 255
            for x, y in self.pcells:
                m[max(0, y - SIG_GAP):y + CELL + SIG_GAP, max(0, x - SIG_GAP):x + CELL + SIG_GAP] = False
            m[SIG_BOTTOM:] = False
            ys, xs = np.nonzero(m)
            self._sig = (ys + BY, xs + BX, self.panel[ys, xs, :3].copy())
        return self._sig

    def bar_share(self, frame: np.ndarray) -> float:
        """The share of the bar's signature pixels the frame shows exactly (1.0 = the bar is there, uncovered)."""
        ys, xs, col = self.signature()
        return float((frame[ys, xs] == col).all(axis=1).mean())

    # -- one cell
    def _label(self, c32: np.ndarray, hint: int | None) -> int | None:
        """The key label on the cell (`c32`: its pixels as numbers): the label picture with the most opaque pixels
        of those whose opaque pixels all equal the frame ("F10" before "F1", "Hm" before "H")."""
        reg = c32[self.lab_reg]
        if hint is not None and np.array_equal(reg.ravel()[self.lab_idx[hint]], self.lab_val[hint]):
            return hint
        ok = ((reg[None] == self.lab32) | self.lab_tr).reshape(len(self.lab_n), -1).all(1)
        fit = np.flatnonzero(ok)
        return int(fit[np.argmax(self.lab_n[fit])]) if len(fit) else None

    def _digits(self, c32: np.ndarray) -> list:
        """The amount's digits, left to right from DIGITS_AT: [(digit, x)]; every opaque pixel of each glyph equal."""
        out, x = [], DIGITS_AT[0]
        y = DIGITS_AT[1]
        while x < CELL:
            reg = c32[y:y + DIGIT_H, x:x + DIGIT_W]
            w = reg.shape[1]
            ok = ((reg[None] == self.dg32[:, :, :w]) | self.dg_tr[:, :, :w]).reshape(10, -1).all(1)
            d = next((int(d) for d in np.flatnonzero(ok) if self.dg_w[d] <= w), None)
            if d is None:
                break
            out.append((d, x))
            x += self.dg_w[d]
        return out

    def expect(self, k: int, cls: int, digs: list, li: int) -> np.ndarray:
        """What cell k must show: the keycap, the content, the digits, the label - composed as the client does."""
        e = self.composite(k, cls).copy()
        y = DIGITS_AT[1]
        for d, x in digs:
            w = min(self.dg_w[d], CELL - x)
            m = self.dg_opq[d][:, :w]
            e[y:y + DIGIT_H, x:x + w][m] = self.dg_col[d][:, :w][m]
        io, co, isemi, ca, na = self.lab_layer[li]
        ef = e.reshape(-1, 3)
        if len(isemi):
            ef[isemi] = (ca + ef[isemi].astype(np.uint32) * na) // 255
        ef[io] = co
        return e

    def read_cell(self, crop: np.ndarray, k: int, hint: Hint | None = None) -> tuple:
        """Cell k's 32 x 32 px -> (Read, the label's index or None). Exact, or kind None."""
        c32 = _key32(crop)
        li = self._label(c32, hint.label if hint else None)
        if li is None:
            return Read(None, None, None, None, -1, NO_LABEL), None
        digs = self._digits(c32)
        cands = self.table(k).get(crop[FP_ROWS].tobytes(), ())
        unsure = self.unsure[k] if self.has_unsure[k] else None
        fits = []
        for cls in cands:
            if cls < 0 and digs:
                continue                                           # digits on a bare keycap: no state we know
            e = self.expect(k, cls, digs, li)
            if np.array_equal(e, crop) if unsure is None else not ((e != crop).any(axis=2) & ~unsure).any():
                fits.append(cls)
        if not fits:
            return Read(None, None, None, None, -1, NO_MATCH if cands else NO_CONTENT), li
        cls = hint.cls if hint is not None and hint.cls in fits else fits[0]
        alts = tuple(c for c in fits if c != cls)
        if cls < 0:
            return Read(self.lab_key[li], "empty", None, None, -1, "", alts), li
        m = self.member(cls)
        amount = int("".join(str(d) for d, _ in digs)) if digs else None
        return Read(self.lab_key[li], m["kind"], m["id"], amount, cls, "", alts), li


_PACKS = {}


def pack(rows: int = 2) -> Pack:
    """The pack of assets/mcw/slots, loaded once per process."""
    if rows not in _PACKS:
        _PACKS[rows] = Pack(rows)
    return _PACKS[rows]


def bar_rows(frame: np.ndarray, share: float = 0.95) -> int | None:
    """Which bar the frame shows: 3 (the client's 3-row picture: 12 slots - never seen in footage), 2 (the 8 slots of
    every capture), or None (hidden, covered, faded). By the bar's own signature pixels; the 3-row one is asked first
    (the 2-row signature is nearly a part of it)."""
    for rows in (3, 2):
        if pack(rows).bar_share(frame) >= share:
            return rows
    return None


def read_slots(frame: np.ndarray, p: Pack | None = None) -> list:
    """One frame (BGR, 1366 x 768 native) -> the Read of every cell, each from scratch (no memory)."""
    p = p or pack()
    return [p.read_cell(frame[y:y + CELL, x:x + CELL], k)[0] for k, (x, y) in enumerate(p.cells)]


class SlotReader:
    """The live reader: `update(frame)` per frame -> the Read of every cell on THIS frame (exact or not). A cell is
    read again only when its pixels changed (an unchanged frame costs one look at the bytes of the cells' rows);
    the label and the content last read are its hints. Not thread-safe: one thread calls it (the Perceiver's HUD
    reader). `facts()` -> FrameFacts `slots`."""

    def __init__(self, p: Pack | None = None):
        self.p = p or pack()
        n = len(self.p.cells)
        self.crop = [None] * n               # the cell's pixels at its last look
        self.now = [Read(None, None, None, None, -1, NO_LABEL)] * n      # the Read of those pixels
        self.label = [None] * n              # the label's index last read on the cell
        self.cls = [-2] * n                  # the content last read exactly
        self.reads = self.frames = self.looks = 0
        self.ms = 0.0                        # the last update's ms
        self._last = None
        # the frame parts whose bytes say "nothing changed": per row of cells the strip from its first cell to its
        # last (gaps included) cut into slices that hold no see-through corner pixel, + the strip ends' sure pixels
        self._slices, gy, gx = [], [], []
        for r in range(n // 4):
            x0, y0 = self.p.cells[4 * r]
            x1 = self.p.cells[4 * r + 3][0] + CELL
            px, py = self.p.pcells[4 * r]
            sure = self.p.panel[py:py + CELL, px:px + (x1 - x0), 3] == 255
            rows_ok = sure.all(axis=1)
            cols_ok = sure[~rows_ok].all(axis=0) if not rows_ok.all() else np.ones(x1 - x0, bool)
            c0, c1 = int(np.argmax(cols_ok)), int(len(cols_ok) - np.argmax(cols_ok[::-1]))
            assert cols_ok[c0:c1].all()
            for a, b in _runs(np.flatnonzero(rows_ok)):
                self._slices.append((slice(y0 + a, y0 + b + 1), slice(x0, x1)))
            for a, b in _runs(np.flatnonzero(~rows_ok)):
                self._slices.append((slice(y0 + a, y0 + b + 1), slice(x0 + c0, x0 + c1)))
            rest = sure & ~rows_ok[:, None]
            rest[:, c0:c1] = False
            ys, xs = np.nonzero(rest)
            gy += list(ys + y0)
            gx += list(xs + x0)
        self._gy, self._gx = np.array(gy, np.intp), np.array(gx, np.intp)

    def _same(self, frame: np.ndarray) -> bool:
        """Are all the cells' sure pixels byte-identical to the last frame's?"""
        sig = [frame[sl].tobytes() for sl in self._slices]
        sig.append(frame[self._gy, self._gx].tobytes())
        if sig == self._last:
            return True
        self._last = sig
        return False

    def update(self, frame: np.ndarray) -> list:
        t0 = time.perf_counter()
        p = self.p
        self.frames += 1
        if not self._same(frame):
            self.looks += 1
            for k, (x, y) in enumerate(p.cells):
                crop = frame[y:y + CELL, x:x + CELL]
                last = self.crop[k]
                if last is not None:
                    if np.array_equal(crop, last):
                        continue
                    if p.has_unsure[k] and not ((crop != last).any(axis=2) & ~p.unsure[k]).any():
                        self.crop[k] = crop.copy()                 # only a see-through corner pixel moved
                        continue
                self.reads += 1
                r, li = p.read_cell(crop, k, Hint(self.label[k], self.cls[k]))
                self.crop[k] = crop.copy()
                self.now[k] = r
                if r.exact:                                        # (a label alone is no proof: white letters fit
                    self.label[k], self.cls[k] = li, r.cls         # any white window over the cell)
        self.ms = 1000 * (time.perf_counter() - t0)
        return list(self.now)

    def key_of(self, k: int) -> str:
        """Cell k's key: its label as last read, else the key its place has in every capture (DEFAULT_KEYS)."""
        li = self.label[k]
        return self.p.lab_key[li] if li is not None else self.p.default_keys[k]

    def facts(self) -> dict:
        """{key: [kind, id, amount] or None (not readable on this frame)} for every cell of the bar."""
        return {self.key_of(k): r.fact() for k, r in enumerate(self.now)}


def _runs(ix) -> list:
    """Sorted indices -> [(first, last)] of consecutive runs."""
    out = []
    for i in (int(v) for v in ix):
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [tuple(r) for r in out]
