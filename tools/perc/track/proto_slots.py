"""Tracker plan, an experiment (a PROTOTYPE: nothing in maplebrain/ imports it): THE QUICKSLOT READER - for every
key of the quickslot bar at the bottom right of the game window, what is on it (an item, a skill, a key-binding
action, nothing) and the item's amount, read EXACTLY from the frame and followed over time (a potion drunk = the
amount on its key steps by -1).

    python tools/perc/track/proto_slots.py build [--export DIR]      the client's pictures -> the template pack
    python tools/perc/track/proto_slots.py run CAP [--every N]       read every frame of a capture + its self-checks
    python tools/perc/track/proto_slots.py report CAP                the self-checks again, from the kept reads
    python tools/perc/track/proto_slots.py sheet OUT.png CAP@n[@note] [CAP@n ...]    a contact sheet: the bar x4 +
                                                                     what a from-scratch read says, per moment
    python tools/perc/track/proto_slots.py bench [CAP]               CPU ms: a full read, the unchanged-frame path
    python tools/perc/track/proto_slots.py selftest                  every client picture drawn into a cell, read back

CAP = a capture of the bank (its id SESSION#K, tools/perc/frames.py `clip`) or a run folder. CPU only, no model.
Everything written goes to CORPUS/work/track-plan/slots/ (re-creatable): pack.npz + pack.json (the templates),
<cap>/reads.npz + events.json + report.txt, sheets.

WHAT THE CLIENT DRAWS (measured 2026-11-23 on frames of 2026-11-16 .. 11-23; every picture is the client's own,
from the export of `build`; nothing here is a guess unless it says ASSUMED):
  - The bar = UI/QuickSlot.img `layer:backgrnd` (151 x 114, 2 rows of 4 keycaps; `layer:3row_background` has 3 rows -
    never seen in footage), its corner at frame (933, 588) in the native 1366x768 window. A slot's cell is 32 x 32 px:
    column c at panel x 7 + 35 c; the 2 rows at panel y 41 and 75 (QuickSlot.img `2ndRowOffset` = 34).
  - A cell is drawn in this order, each layer laid over the last with plain alpha, rounded
    (c * a + d * (255 - a) + 127) // 255 - the frame's pixels equal this composite EXACTLY:
      1. the keycap (the panel picture);
      2. the content, its picture's origin at the cell's (0, 32): an item = its `info/icon` (the picture WITH the
         shadow - not `iconRaw`, which is what lies on the ground), a key-binding action = UI/KeyBindings.img
         `icon/<id>` (32 x 32, "JUMP" ...), a skill = Skill `skill/<id>/icon` (ASSUMED: no skill was on a key in any
         footage). Clipped to the cell (seen on the left edge: The Green Relaxer's column at x = -1 is not drawn);
      3. an item's amount: UI/Basic.img `ItemNo/<digit>` glyphs (8 x 11, the "1" 5 x 11; alpha 0 or 255 only), the
         first at the cell's (0, 20), each next one right after the last, no gap. An item that shows no amount
         (a chair) has none; an item whose last one was used keeps its picture and shows "0";
      4. the key's label: UI/QuickSlot.img `key/<scan code>` at the cell's (2, 2), opaque letters over everything.
    Nothing else was drawn on a slot when its key was pressed (no flash on `end` / `delete`).
  - Which key a slot belongs to is the label's picture, never its position (the client has a dialog that assigns the
    bar's keys: UI/KeyBindings.img `quickslot/button:slot0..11`).

HOW THE READER WORKS: per cell, (1) the label = the key picture whose opaque pixels all equal the frame; (2) the
amount = digit glyphs matched left to right from (0, 20), every opaque pixel equal; (3) the content = looked up by
the bytes of the cell's rows 15..19 (no label or digit ever lies there) among the composites of every item / skill /
action picture over the keycap, then (4) VERIFIED: keycap + content + digits + label composed must equal all 1024
pixels of the cell. A read is exact or it is nothing (`kind` None: covered by the cursor, a tooltip, a window, the
fade of a map change, or not the bar) - never a nearest match. `SlotTracker` keeps each cell's last pixels and reads
a cell again only when they changed; while a cell is unreadable its last exact reading is held.

Game data in the pack: items by id with the client's names (String Consume / Ins / Cash / Etc / Pet / Eqp) and what
using one does (the item's `spec`: hp, mp ...), skills (String Skill), actions by the id of their picture (the names
in ACTIONS are the words ON the pictures). Several items can share one picture (Red Potion 2000000 and 2000007): the
reader gives the lowest id of the usable kinds, `Pack.same(kind, id)` the others.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))

from maplebrain.config import CORPUS  # noqa: E402

OUT = Path(os.environ.get("MAPLE_CORPUS") or CORPUS) / "work" / "track-plan" / "slots"
PACK, PACK_JSON = OUT / "pack.npz", OUT / "pack.json"

# ---- geometry (frame px, the native 1366x768 window) -------------------------------------------------------------
BX, BY = 933, 588                      # the panel picture's corner in the frame (measured: 9,564 opaque px placed)
CELL = 32                              # a slot's cell
COL0, PITCH_X = 7, 35                  # panel x of column 0, the columns' pitch
ROWS = {2: (41, 75), 3: (7, 41, 75)}   # panel y of the rows: the 2-row bar, the 3-row one (never seen in footage)
LABEL_AT = (2, 2)                      # the key label's corner in the cell
LABEL_H = 13                           # the tallest label ("Pup"): labels cover the cell's rows 2..14 at most
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
# the bar's keys by position, used ONLY to name a slot whose label cannot be read on that frame (the layout of every
# capture in the bank, 2026-11-16..23)
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


# ---- the client's pictures: the export (PowerShell + HaRepacker's MapleLib, as tools/cwdata/export.ps1) -----------
EXPORT_PS1 = r'''# The client pictures a quickslot is drawn from (reads the COPY of the game's Data folder, never the install):
#   <Out>\ui\QuickSlot.img.xml + ui\png\QuickSlot\...   the bar's background, the key labels, cooldown shade + digits
#   <Out>\ui\png\ItemNo\<d>.png                         the item amount's digits (Basic.img/ItemNo)
#   <Out>\ui\png\action\<id>.png                        the key-binding actions (KeyBindings.img/icon: JUMP, ATTACK ...)
#   <Out>\ui\png\ItemIcon\..., ui\png\SkillIcon\...     marks the client may draw over an icon
#   <Out>\item\<8-digit id>.png + item\items.json       every item's info/icon (the picture WITH its shadow), its
#                                                       spec (what using it does: hp, mp ...) and a few info flags
#   <Out>\skill\<7-digit id>.png, _d.png, _m.png + skill\skills.json   every skill's icon, iconDisabled, iconMouseOver
param([Parameter(Mandatory)][string]$Out, [Parameter(Mandatory)][string]$Load)
$ErrorActionPreference = 'Stop'
. $Load

function Open-Bms($p) {
  $f = [MapleLib.WzLib.WzFile]::new($p, [MapleLib.WzLib.WzMapleVersion]::BMS)
  $st = $f.ParseWzFile($null)
  if ("$st" -ne 'Success') { throw "$p : $st" }
  $f
}
$script:canvasDirs = @{}
function Get-OutlinkTarget([string]$link) {
  $parts = $link -split '/'
  $k = [Array]::FindIndex($parts, [Predicate[string]] { param($s) $s.EndsWith('.img') })
  if ($k -lt 1) { throw "bad _outlink $link" }
  $dir = ($parts[0..($k - 1)] -join '\')
  if (-not $script:canvasDirs.ContainsKey($dir)) {
    $imgs = @{}
    foreach ($w in Get-ChildItem "$D\$dir" -Filter "$($parts[$k - 1])_*.wz") {
      foreach ($i in (Open-Bms $w.FullName).WzDirectory.WzImages) { $imgs[$i.Name] = $i }
    }
    $script:canvasDirs[$dir] = $imgs
  }
  $img = $script:canvasDirs[$dir][$parts[$k]]
  if (-not $img) { throw "_outlink $link : no image $($parts[$k]) in $D\$dir" }
  $img.GetFromPath(($parts[($k + 1)..($parts.Count - 1)] -join '/'))
}
function Get-Bitmap($c, $img) {
  for ($hop = 0; $hop -lt 8; $hop++) {
    $in = $c.GetProperty('_inlink'); $out = $c.GetProperty('_outlink')
    if ($in) { $c = $img.GetFromPath($in.Value) }
    elseif ($out) { $c = Get-OutlinkTarget $out.Value }
    else { return $c.GetBitmap() }
    if (-not $c) { throw "broken link in $($img.Name)" }
  }
  throw "link loop in $($img.Name)"
}
function Save-Png($bmp, $path) {
  New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
  $bmp.Save($path, [Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
}
$fails = [Collections.Generic.List[string]]::new()
$script:nPart = 0
function Export-Canvases($prop, $img, [string]$base) {
  foreach ($c in $prop.WzProperties) {
    $nm = ($c.Name -replace '[\/:*?"<>|]', '_').Trim()
    if ($c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty]) {
      try { Save-Png (Get-Bitmap $c $img) "$base\$nm.png"; $script:nPart++ }
      catch { $fails.Add("$($img.Name) $base/$($c.Name): $_") }
    } elseif ($c -is [MapleLib.WzLib.WzProperties.WzSubProperty]) {
      Export-Canvases $c $img "$base\$nm"
    }
  }
}
$t0 = Get-Date
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force $Out | Out-Null

# --- the UI pictures
$ui = Open-Bms "$D\UI\UI_000.wz"
foreach ($img in $ui.WzDirectory.WzImages) {
  switch ($img.Name) {
    'QuickSlot.img' { Save-Xml $img "$Out\ui\QuickSlot.img.xml"; Export-Canvases $img $img "$Out\ui\png\QuickSlot" }
    'Basic.img' { Export-Canvases $img.GetFromPath('ItemNo') $img "$Out\ui\png\ItemNo" }
    'KeyBindings.img' { Export-Canvases $img.GetFromPath('icon') $img "$Out\ui\png\action" }
    'ItemIcon.img' { Save-Xml $img "$Out\ui\ItemIcon.img.xml"; Export-Canvases $img $img "$Out\ui\png\ItemIcon" }
    'SkillIcon.img' { Save-Xml $img "$Out\ui\SkillIcon.img.xml"; Export-Canvases $img $img "$Out\ui\png\SkillIcon" }
  }
}
"ui: $script:nPart pictures"

# --- names
$names = @{}; $skillNames = @{}
$sf = Open-Bms "$D\String\String_000.wz"
foreach ($name in 'Consume.img', 'Ins.img', 'Cash.img', 'Pet.img') {
  $si = $sf.WzDirectory.WzImages | ? Name -eq $name
  if (-not $si) { continue }
  foreach ($p in $si.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } }
foreach ($grp in ($sf.WzDirectory.WzImages | ? Name -eq 'Etc.img').WzProperties) {
  foreach ($p in $grp.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } }
foreach ($top in ($sf.WzDirectory.WzImages | ? Name -eq 'Eqp.img').WzProperties) {
  foreach ($slot in $top.WzProperties) {
    foreach ($p in $slot.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } } }
foreach ($p in ($sf.WzDirectory.WzImages | ? Name -eq 'Skill.img').WzProperties) {
  $n = $p.GetFromPath('name'); if ($n) { $skillNames["$($p.Name)"] = "$($n.Value)" } }

# --- items: info/icon (+ spec and a few info flags)
$items = [ordered]@{}
$script:nNoIcon = 0
function Add-Icon([string]$kind, [string]$id, $info, $img, $spec) {
  $c = $info.GetFromPath('icon')
  if (-not $c) { $script:nNoIcon++; return }
  $e = [ordered]@{ kind = $kind; name = $names[[int]$id] }
  foreach ($flag in 'cash', 'slotMax', 'timeLimited', 'accountSharable', 'recoveryHP', 'recoveryMP') {
    $cf = $info.GetFromPath($flag)
    if ($cf) { try { $e[$flag] = [int]"$($cf.Value)" } catch {} }
  }
  if ($spec) {
    $sp = [ordered]@{}
    foreach ($q in $spec.WzProperties) {
      if ($q.Name -match '^\d+$') { continue }                  # (pet food: the list of pets it feeds)
      if ($q -is [MapleLib.WzLib.WzProperties.WzIntProperty] -or $q -is [MapleLib.WzLib.WzProperties.WzShortProperty] -or
          $q -is [MapleLib.WzLib.WzProperties.WzStringProperty]) { try { $sp[$q.Name] = [int]"$($q.Value)" } catch {} }
    }
    if ($sp.Count) { $e['spec'] = $sp }
  }
  $uol = ''
  for ($hop = 0; $c -is [MapleLib.WzLib.WzProperties.WzUOLProperty] -and $hop -lt 8; $hop++) {
    $uol = "$($c.Value)"; $par = $c.Parent; $c = $c.LinkValue
    if (-not $c) { $c = $par.GetFromPath($uol) }
    if ($c -and $c.Parent -and $c.Parent.Parent) { $e['link'] = ($c.Parent.Parent.Name -replace '\.img$', '') }
  }
  if ($c -isnot [MapleLib.WzLib.WzProperties.WzCanvasProperty]) { $fails.Add("item $kind $id : icon -> '$uol' not a canvas"); return }
  try {
    $bmp = Get-Bitmap $c $img
    $o = $c.GetProperty('origin')
    $e['icon'] = @([int]$bmp.Width, [int]$bmp.Height, [int]$o.X.Value, [int]$o.Y.Value)
    Save-Png $bmp "$Out\item\$id.png"
    $items[$id] = $e
  } catch {
    if ("$_" -like 'broken link*') { $script:skipped.Add("$kind $id") } else { $fails.Add("item $kind $id : $_") }
  }
}
$skipped = [Collections.Generic.List[string]]::new()
foreach ($kind in 'Consume', 'Install', 'Etc', 'Cash') {
  $n0 = $items.Count
  foreach ($w in Get-ChildItem "$D\Item\$kind" -Filter "$($kind)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      foreach ($it in $img.WzProperties) {
        $info = $it.GetFromPath('info'); if ($info) { Add-Icon $kind $it.Name $info $img $it.GetFromPath('spec') } }
      $img.UnparseImage()
    }
  }
  "items $kind : $($items.Count - $n0)"
}
$n0 = $items.Count
foreach ($w in Get-ChildItem "$D\Item\Pet" -Filter 'Pet_*.wz') {
  foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
    $info = $img.GetFromPath('info')
    if ($info) { Add-Icon 'Pet' ($img.Name -replace '\.img$', '').PadLeft(8, '0') $info $img $null }
    $img.UnparseImage()
  }
}
"items Pet : $($items.Count - $n0)"
foreach ($slot in 'Accessory', 'Cap', 'Cape', 'Coat', 'Glove', 'Longcoat', 'Pants', 'Ring', 'Shield', 'Shoes', 'Weapon') {
  $n0 = $items.Count
  foreach ($w in Get-ChildItem "$D\Character\$slot" -Filter "$($slot)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      $info = $img.GetFromPath('info')
      if ($info) { Add-Icon $slot ($img.Name -replace '\.img$', '') $info $img $null }
      $img.UnparseImage()
    }
  }
  "items $slot : $($items.Count - $n0)"
}
New-Item -ItemType Directory -Force "$Out\item" | Out-Null
$items | ConvertTo-Json -Depth 6 -Compress | Set-Content -Encoding utf8 "$Out\item\items.json"
"items: $($items.Count) ($script:nNoIcon without info/icon; skipped (a link to a canvas the client lacks): $($skipped.Count) $($skipped -join ', '))"

# --- skills: icon, iconDisabled, iconMouseOver of every skill of every job
$skills = [ordered]@{}
$ms = Open-Ms "$D\Packs\Skill_00000.ms"
foreach ($img in $ms.WzDirectory.WzImages) {
  $sk = $img.GetFromPath('skill')
  if (-not $sk) { continue }
  foreach ($s in $sk.WzProperties) {
    $e = [ordered]@{ name = $skillNames["$($s.Name)"]; job = ($img.Name -replace '\.img$', '') }
    foreach ($pair in @(@('icon', ''), @('iconDisabled', '_d'), @('iconMouseOver', '_m'))) {
      $c = $s.GetFromPath($pair[0])
      if (-not $c) { continue }
      for ($hop = 0; $c -is [MapleLib.WzLib.WzProperties.WzUOLProperty] -and $hop -lt 8; $hop++) { $c = $c.LinkValue }
      if ($c -isnot [MapleLib.WzLib.WzProperties.WzCanvasProperty]) { continue }
      try {
        $bmp = Get-Bitmap $c $img
        $o = $c.GetProperty('origin')
        $e[$pair[0]] = @([int]$bmp.Width, [int]$bmp.Height, [int]$o.X.Value, [int]$o.Y.Value)
        Save-Png $bmp "$Out\skill\$($s.Name)$($pair[1]).png"
      } catch { $fails.Add("skill $($s.Name) $($pair[0]): $_") }
    }
    $skills["$($s.Name)"] = $e
  }
}
New-Item -ItemType Directory -Force "$Out\skill" | Out-Null
$skills | ConvertTo-Json -Depth 6 -Compress | Set-Content -Encoding utf8 "$Out\skill\skills.json"
"skills: $($skills.Count)"

"failed: $($fails.Count)"; $fails | Select-Object -First 40 | % { "  $_" }
"done in $([int]((Get-Date) - $t0).TotalSeconds) s -> $Out"
if ($fails.Count) { exit 1 }
'''


def export(out: Path) -> None:
    """The client's pictures -> `out` (EXPORT_PS1; ~25 s). Needs pwsh and HaRepacker's lib (tools/cwdata/load.ps1)."""
    with tempfile.TemporaryDirectory() as d:
        ps1 = Path(d) / "export_slots.ps1"
        ps1.write_text(EXPORT_PS1, encoding="utf-8")
        r = subprocess.run(["pwsh", "-NoProfile", "-File", str(ps1), "-Out", str(out), "-Load",
                            str(ROOT / "tools" / "cwdata" / "load.ps1")],
                           env={**os.environ, "DOTNET_ReadyToRun": "0"}, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    lines = [x for x in r.stdout.splitlines() if x.strip()]
    print("\n".join("  " + x for x in lines[-24:]))
    if r.returncode != 0:
        raise SystemExit(f"the export failed ({r.returncode}): {r.stderr[-2000:]}")


def _png(p: Path) -> np.ndarray:
    a = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if a is None:
        raise SystemExit(f"unreadable picture {p}")
    if a.ndim == 2:
        a = cv2.cvtColor(a, cv2.COLOR_GRAY2BGRA)
    if a.shape[2] == 3:
        a = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])
    return a


def _place(pic: np.ndarray, ox: int, oy: int) -> np.ndarray:
    """A picture in a slot's cell (32 x 32 BGRA): its origin at the cell's (0, 32), clipped to the cell."""
    out = np.zeros((CELL, CELL, 4), np.uint8)
    h, w = pic.shape[:2]
    x0, y0 = -ox, CELL - oy
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(w, CELL - x0), min(h, CELL - y0)
    if sx1 > sx0 and sy1 > sy0:
        out[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] = pic[sy0:sy1, sx0:sx1]
    return out


def build(exp: Path | None) -> None:
    """The template pack from the client's pictures: OUT/pack.npz + pack.json."""
    tmp = None
    if exp is None:
        tmp = tempfile.TemporaryDirectory()
        exp = Path(tmp.name) / "client"
        export(exp)
    q = exp / "ui" / "png" / "QuickSlot"
    panels = np.stack([_png(q / "layer_backgrnd.png"), _png(q / "layer_3row_background.png")])
    digit = np.zeros((10, DIGIT_H, DIGIT_W, 4), np.uint8)
    digit_w = np.zeros(10, np.int32)
    for d in range(10):
        g = _png(exp / "ui" / "png" / "ItemNo" / f"{d}.png")
        if g.shape[0] != DIGIT_H or g.shape[1] > DIGIT_W or set(np.unique(g[..., 3])) - {0, 255}:
            raise SystemExit(f"ItemNo/{d}: {g.shape}, alpha {np.unique(g[..., 3])} - not the glyphs this reader knows")
        digit[d, :, :g.shape[1]] = g
        digit_w[d] = g.shape[1]
    labels, lab_meta = [], []
    for p in sorted((q / "key").glob("*.png"), key=lambda p: (not p.stem.isdigit(), int(p.stem) if p.stem.isdigit() else 0, p.stem)):
        g = _png(p)
        h, w = g.shape[:2]
        if h > LABEL_H or w > 34:
            raise SystemExit(f"key label {p.name}: {w} x {h} - larger than this reader allows for")
        a = np.zeros((LABEL_H, 34, 4), np.uint8)
        a[:h, :w] = g
        code = int(p.stem) if p.stem.isdigit() else None
        key = KEY_NAMES.get(code, p.stem.lower())
        twin = next((m for m, b in zip(lab_meta, labels) if np.array_equal(a, b)), None)
        if twin is not None:                                   # one picture for two keys (the client's key/24 "O"
            twin["also"].append(key)                           # is a link to key/11 "0")
            continue
        labels.append(a)
        lab_meta.append({"code": p.stem, "key": key, "w": w, "h": h, "also": []})
    # the contents: every picture a slot can show, placed in the cell; identical placements = one class
    members, classes, index = [], [], {}

    def add(kind, cid, name, pic, ox, oy, extra=None):
        c = _place(pic, ox, oy)
        if not (c[..., 3] > 0).any():
            return False
        j = index.get(c.tobytes())
        if j is None:
            j = index[c.tobytes()] = len(classes)
            classes.append(c)
            members.append([])
        members[j].append({"kind": kind, "id": cid, "name": name, **(extra or {})})
        return True

    items = json.loads((exp / "item" / "items.json").read_text(encoding="utf-8-sig"))
    order = {k: i for i, k in enumerate(KIND_ORDER)}
    n_item = n_blank = 0
    for iid, e in sorted(items.items(), key=lambda kv: (order.get(kv[1]["kind"], 99), int(kv[0]))):
        w, h, ox, oy = e["icon"]
        extra = {"group": e["kind"], **{f: e[f] for f in ("spec", "slotMax", "timeLimited", "accountSharable", "cash",
                                                          "recoveryHP", "recoveryMP") if f in e}}
        ok = add("item", int(iid), e.get("name"), _png(exp / "item" / f"{iid}.png"), ox, oy, extra)
        n_item += ok
        n_blank += not ok
    skills = json.loads((exp / "skill" / "skills.json").read_text(encoding="utf-8-sig"))
    n_skill = 0
    for sid, e in sorted(skills.items(), key=lambda kv: int(kv[0])):
        for field, suffix, kind in (("icon", "", "skill"), ("iconDisabled", "_d", "skill_disabled"),
                                    ("iconMouseOver", "_m", "skill_mouseover")):
            if field in e:
                w, h, ox, oy = e[field]
                n_skill += add(kind, int(sid), e.get("name"), _png(exp / "skill" / f"{sid}{suffix}.png"), ox, oy,
                               {"job": e.get("job")})
    n_act = 0
    for p in sorted((exp / "ui" / "png" / "action").glob("*.png"), key=lambda p: int(p.stem)):
        pic = _png(p)
        n_act += add("action", int(p.stem), ACTIONS.get(int(p.stem), f"action {p.stem}"), pic, 0, pic.shape[0])
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PACK, panels=panels, digit=digit, digit_w=digit_w, label=np.stack(labels),
                        content=np.stack(classes))
    meta = {"made": time.strftime("%Y-%m-%dT%H:%M:%S"), "labels": lab_meta, "members": members,
            "counts": {"items": n_item, "items_blank_in_cell": n_blank, "skill_pictures": n_skill, "actions": n_act,
                       "classes": len(classes)}}
    PACK_JSON.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    shared = sum(1 for m in members if len({(x["kind"], x["id"]) for x in m}) > 1)
    print(f"pack: {len(classes)} distinct pictures ({n_item} items, {n_skill} skill pictures, {n_act} actions; "
          f"{n_blank} items show nothing in the cell; {shared} pictures are shared by more than one id), "
          f"{len(labels)} key labels (one picture for several keys: "
          f"{[[m['key']] + m['also'] for m in lab_meta if m['also']]}) -> {PACK} ({PACK.stat().st_size / 1e6:.1f} MB)")
    if tmp is not None:
        tmp.cleanup()


# ---- the reader ----------------------------------------------------------------------------------------------------
class Read(NamedTuple):
    """One slot on one frame. `kind`: "item" / "skill" / "skill_disabled" / "skill_mouseover" / "action" / "empty",
    or None = not readable on this frame (`why` says what was missing; `key`, `id`, `amount` are None then).
    `key`: the key on the slot's label. `id`: the item's / skill's / action's id. `amount`: the number drawn on an
    item (None: none drawn). `cls`: the content picture's index in the pack (-1: empty or unread). `alts`: the
    other pictures (pack indices, -1 = the bare keycap) that explain the cell's pixels just as exactly - they
    differ from `cls` only where the label or the digits lie (seen in the self-test only, never in footage)."""
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


class Pack:
    """The templates + everything derived from them once: per cell the keycap, per content its composite's
    fingerprint, per label / digit the pixels that must match."""

    def __init__(self, rows: int = 2):
        if not PACK.exists():
            raise SystemExit(f"{PACK} is missing: python tools/perc/track/proto_slots.py build")
        z = np.load(PACK)
        self.meta = json.loads(PACK_JSON.read_text(encoding="utf-8"))
        self.rows = rows
        self.panel = z["panels"][0 if rows == 2 else 1]
        self.content = z["content"]                              # (N, 32, 32, 4)
        self.members = self.meta["members"]
        self.pcells = [(COL0 + PITCH_X * c, y) for y in ROWS[rows] for c in range(4)]      # in the panel picture
        self.cells = [(BX + x, BY + y) for x, y in self.pcells]                              # in the frame
        self.bg = [np.ascontiguousarray(self.panel[y:y + CELL, x:x + CELL, :3]) for x, y in self.pcells]
        # the cell pixels where the panel is not fully opaque (4 corner px of the 4 corner cells, alpha 253 / 254):
        # the world shows through by one grey level - never compared
        self.unsure = [self.panel[y:y + CELL, x:x + CELL, 3] != 255 for x, y in self.pcells]
        self.has_unsure = [bool(u.any()) for u in self.unsure]
        # the labels, clipped to the cell: region = the cell's rows 2..14, columns 2..31
        lx, ly = LABEL_AT
        lw = CELL - lx
        lab = z["label"][:, :, :lw]                               # (n, 13, 30, 4)
        self.lab32 = _key32(lab[..., :3])                         # a pixel's colour as one number
        self.lab_tr = lab[..., 3] != 255                          # where the label is not opaque: anything fits
        self.lab_n = (~self.lab_tr).reshape(len(lab), -1).sum(1)
        self.lab_idx = [np.flatnonzero(~t.ravel()) for t in self.lab_tr]
        self.lab_val = [self.lab32[i].ravel()[ix] for i, ix in enumerate(self.lab_idx)]
        self.lab_key = [m["key"] for m in self.meta["labels"]]
        self.lab_also = [m.get("also", []) for m in self.meta["labels"]]     # other keys drawn with the same picture
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
        # the digits
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

    # -- tables
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
        """What the cell must show: the keycap, the content, the digits, the label - composed as the client does."""
        e = self.composite(k, cls).copy()
        y = DIGITS_AT[1]
        for d, x in digs:
            w = self.dg_w[d]
            m = self.dg_opq[d][:, :w]
            e[y:y + DIGIT_H, x:x + w][m] = self.dg_col[d][:, :w][m]
        io, co, isemi, ca, na = self.lab_layer[li]
        ef = e.reshape(-1, 3)
        if len(isemi):
            ef[isemi] = (ca + ef[isemi].astype(np.uint32) * na) // 255
        ef[io] = co
        return e

    def read_cell(self, crop: np.ndarray, k: int, hint: "Hint | None" = None) -> tuple:
        """The cell's 32 x 32 px -> (Read, the label's index or None). Exact, or kind None."""
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


class Hint(NamedTuple):
    label: int | None
    cls: int


_PACKS = {}


def pack(rows: int = 2) -> Pack:
    if rows not in _PACKS:
        _PACKS[rows] = Pack(rows)
    return _PACKS[rows]


def bar_rows(frame: np.ndarray, share: float = 0.95) -> int | None:
    """Which bar the frame shows: 3 (the client's 3-row picture: 12 slots - never seen in footage, tested only on a
    frame the picture was pasted into), 2 (the 8 slots of every capture), or None (hidden, covered, faded). By the
    bar's own signature pixels; the 3-row one is asked first (the 2-row signature is nearly a part of it)."""
    for rows in (3, 2):
        if pack(rows).bar_share(frame) >= share:
            return rows
    return None


def read_slots(frame: np.ndarray, rows: int = 2) -> dict:
    """One frame (BGR, 1366 x 768 native) -> {key: (kind, id, amount)} for the bar's slots, each read from scratch.
    kind None = that slot is not readable on this frame (id and amount None too); it is then filed under the key
    its place usually has (DEFAULT_KEYS) - the label was not verified. `rows`: 2, or 3 when bar_rows says so."""
    p = pack(rows)
    out = {}
    for k, (x, y) in enumerate(p.cells):
        r, _ = p.read_cell(frame[y:y + CELL, x:x + CELL], k)
        out[r.key or DEFAULT_KEYS[p.rows][k]] = (r.kind, r.id, r.amount)
    return out


class SlotTracker:
    """The live design: `update(frame, t)` per frame. A cell is read again only when its pixels changed; while it is
    unreadable (covered) its last exact reading is HELD. `events` = every change of an exact reading:
    {"t", "n", "cell", "key", "was": [kind, id, amount], "now": [...], "d": the amount's step (None: another change)}.
    The unchanged frame costs one look at the bytes of the cells' rows (`_same`); only when they differ is each cell
    compared, and only a cell whose pixels changed is read."""

    def __init__(self, p: Pack | None = None):
        self.p = p or pack()
        n = len(self.p.cells)
        self.crop = [None] * n               # the cell's pixels at its last look
        self.now = [None] * n                # the Read of those pixels (exact or not)
        self.held = [None] * n               # the last exact Read
        self.label = [None] * n
        self.events = []
        self.reads = self.frames = self.looks = 0
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
            for a, b, _ in _runs([int(i) for i in np.flatnonzero(rows_ok)]):
                self._slices.append((slice(y0 + a, y0 + b + 1), slice(x0, x1)))
            for a, b, _ in _runs([int(i) for i in np.flatnonzero(~rows_ok)]):
                self._slices.append((slice(y0 + a, y0 + b + 1), slice(x0 + c0, x0 + c1)))
            rest = sure & ~rows_ok[:, None]
            rest[:, c0:c1] = False
            ys, xs = np.nonzero(rest)
            gy += list(ys + y0)
            gx += list(xs + x0)
        self._gy, self._gx = np.array(gy), np.array(gx)

    def _same(self, frame: np.ndarray) -> bool:
        """Are all the cells' sure pixels byte-identical to the last frame's?"""
        sig = [frame[sl].tobytes() for sl in self._slices]
        sig.append(frame[self._gy, self._gx].tobytes())
        if sig == self._last:
            return True
        self._last = sig
        return False

    def update(self, frame: np.ndarray, t: float = 0.0, n: int = 0) -> list:
        """-> the slots' Reads: the last exact one of each (None before the first); `self.now[k].exact` says whether
        cell k is readable on THIS frame."""
        p = self.p
        self.frames += 1
        if self._same(frame):
            return list(self.held)
        self.looks += 1
        for k, (x, y) in enumerate(p.cells):
            crop = frame[y:y + CELL, x:x + CELL]
            last = self.crop[k]
            if last is not None:
                if np.array_equal(crop, last):
                    continue
                if p.has_unsure[k] and not ((crop != last).any(axis=2) & ~p.unsure[k]).any():
                    self.crop[k] = crop.copy()                     # only a see-through corner pixel moved
                    continue
            self.reads += 1
            held = self.held[k]
            r, li = p.read_cell(crop, k, Hint(self.label[k], held.cls if held else -2))
            self.crop[k] = crop.copy()
            self.now[k] = r
            if r.exact:
                self.label[k] = li
                if held is not None and held[:4] != r[:4]:
                    same = (held.kind, held.id) == (r.kind, r.id) and held.amount is not None and r.amount is not None
                    self.events.append({"t": round(float(t), 4), "n": int(n), "cell": k, "key": r.key,
                                        "was": [held.kind, held.id, held.amount], "now": [r.kind, r.id, r.amount],
                                        "d": r.amount - held.amount if same else None})
                self.held[k] = r
        return list(self.held)


# ---- a capture ------------------------------------------------------------------------------------------------------
def cap_dir(cap: str) -> Path:
    return OUT / str(cap).replace("#", "_").replace("\\", "_").replace("/", "_").replace(":", "")


def run(cap: str, every: int = 1, audit: int = 499) -> None:
    """Every frame (or every `every`-th) of a capture through SlotTracker, + the HUD's HP / MP of the same frames
    (maplebrain.perception.hud.HudText: the live reader, CPU) -> cap_dir/reads.npz + events.json. Every `audit`-th
    frame, and every frame on which a reading changed, is also read from scratch (read_slots) and compared."""
    import frames as rec
    from maplebrain.perception import hud
    c = rec.clip(cap, False, "proto_slots")
    fr = c.frames()[::every]
    p = Pack()
    tr = SlotTracker(p)
    ht = hud.HudText()
    N, K = len(fr), len(p.cells)
    exact = np.zeros((N, K), bool)
    cls = np.full((N, K), -2, np.int32)
    amount = np.full((N, K), -1, np.int32)
    hp = np.full((N, 2), -1, np.int32)
    mp = np.full((N, 2), -1, np.int32)
    bar = np.ones(N, np.float32)
    whys = {}
    t_read = t_dec = 0.0
    n_audit = bad_audit = 0
    t0 = time.perf_counter()
    for i, (n, name, t) in enumerate(fr):
        a = time.perf_counter()
        img = rec.read(c.run, name)
        b = time.perf_counter()
        if img is None:
            raise SystemExit(f"{cap}: frame {name} unreadable")
        n_ev = len(tr.events)
        tr.update(img, t, n)
        e = time.perf_counter()
        t_dec += b - a
        t_read += e - b
        for k in range(K):
            r = tr.now[k]
            exact[i, k] = r.exact
            if r.exact:
                cls[i, k] = r.cls
                amount[i, k] = -1 if r.amount is None else r.amount
            else:
                whys.setdefault((k, r.why), []).append(n)
        if not exact[i].all():
            bar[i] = p.bar_share(img)
        if i % audit == 0 or len(tr.events) != n_ev:
            n_audit += 1
            for k, (x, y) in enumerate(p.cells):
                r, _ = p.read_cell(img[y:y + CELL, x:x + CELL], k)
                o = tr.now[k]
                if (r.key, r.amount, r.exact) != (o.key, o.amount, o.exact) or o.cls not in (r.cls,) + r.alts:
                    bad_audit += 1
                    print(f"  AUDIT frame {n} cell {k}: from scratch {r} != the tracker's {tr.now[k]}")
        h, m, _ = ht.read(img)
        if h:
            hp[i] = h
        if m:
            mp[i] = m
        if i % 20000 == 0 and i:
            print(f"  {cap}: {i} / {N} frames, {time.perf_counter() - t0:.0f} s", flush=True)
    d = cap_dir(cap)
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "reads.npz", n=np.array([f[0] for f in fr]), t=np.array([f[2] for f in fr]), exact=exact,
                        cls=cls, amount=amount, hp=hp, mp=mp, bar=bar)
    info = {"cap": c.name, "map": c.map_id, "frames": N, "every": every, "cells": K,
            "labels": [None if li is None else p.lab_key[li] for li in tr.label],
            "events": tr.events, "reads": tr.reads, "decode_s": round(t_dec, 1), "tracker_s": round(t_read, 3),
            "tracker_us_per_frame": round(1e6 * t_read / max(1, N), 2), "audit": [n_audit, bad_audit],
            "unreadable": [{"cell": k, "why": w, "frames": ns} for (k, w), ns in sorted(whys.items())]}
    (d / "events.json").write_text(json.dumps(info), encoding="utf-8")
    print(f"{cap}: {N} frames; decode {t_dec:.0f} s, the tracker {t_read:.2f} s = {1e6 * t_read / max(1, N):.1f} us a "
          f"frame ({tr.reads} cell reads) -> {d}")
    report(cap)


def _runs(ns: list) -> list:
    """Frame numbers -> [(first, last, count)] of consecutive runs."""
    out = []
    for n in ns:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
            out[-1][2] += 1
        else:
            out.append([n, n, 1])
    return [tuple(r) for r in out]


def _pct(v, q):
    return float(np.percentile(np.asarray(v, float), q)) if len(v) else float("nan")


def report(cap: str, window: float = 1.5, pair_s: float = 0.5) -> None:
    """The self-checks of a capture read by `run`, printed and kept as cap_dir/report.txt.
    A press = a key-down of the key log (auto-repeat is not logged: a long hold is one press). A "potion key" = a
    slot whose item's `spec` (the client's data) gives HP or MP. Three independent checks:
      A. every potion-sized rise of the HUD's HP / MP (>= 60 % of the smallest spec on the bar, between two frames)
         against the amount's -1 steps: each rise must have exactly one step within `pair_s`, and each step a rise;
      B. every potion press with no other potion press within `window` s before or after it ("alone"): one -1 step
         on its key and a rise of its stat within `window` s; the lags come from these presses only;
      C. the presses that are NOT alone, as bursts: presses, steps and rises counted per burst."""
    import frames as rec
    d = cap_dir(cap)
    z = np.load(d / "reads.npz")
    info = json.loads((d / "events.json").read_text(encoding="utf-8"))
    p = Pack()
    n, t, exact, cls, amount, hp, mp = z["n"], z["t"], z["exact"], z["cls"], z["amount"], z["hp"], z["mp"]
    N, K = exact.shape
    c = rec.clip(cap, False, "proto_slots")
    kp = c.run / "keys.jsonl"
    keys = [json.loads(x) for x in open(kp, encoding="utf-8")] if kp.exists() else []
    L = []
    w = L.append
    w(f"== {info['cap']} (map {info.get('map')}): {N} frames (every {info['every']}), t {t[0]:.2f} .. {t[-1]:.2f} s; "
      f"the tracker {info['tracker_us_per_frame']} us a frame, {info['reads']} cell reads in all; "
      f"from-scratch audit: {info['audit'][0]} frames, {info['audit'][1]} differences")
    w(f"   HUD read on {100 * float((hp[:, 0] >= 0).mean()):.2f} % (HP) / {100 * float((mp[:, 0] >= 0).mean()):.2f} % (MP) of frames")
    # 1. what each key holds over time + the read rate
    w("-- what each key holds (exact reads)")
    for k in range(K):
        key = info["labels"][k] or f"(cell {k}: label never read)"
        ex = exact[:, k]
        kinds, last = [], None
        for i in np.flatnonzero(ex):
            st = (int(cls[i, k]), int(amount[i, k]))
            if st == last:
                continue
            last = st
            if not kinds or kinds[-1][1] != st[0]:
                kinds.append([i, st[0], st[1], st[1], 1, st[1], st[1]])
            else:
                kd = kinds[-1]
                kd[3], kd[4], kd[5], kd[6] = st[1], kd[4] + 1, min(kd[5], st[1]), max(kd[6], st[1])
        txt = "; ".join(
            f"from frame {int(n[i])}: " + ("empty" if cl < 0 else f"{p.member(cl)['kind']} {p.member(cl)['id']} "
                                           f"'{p.name(cl)}'" + ("" if a0 < 0 else f" amount {a0} -> {a1} ({cnt} "
                                                                f"values in a row, min {lo}, max {hi})"))
            for i, cl, a0, a1, cnt, lo, hi in kinds) or "never read"
        w(f"   {key:9s} exact on {int(ex.sum())} / {N} frames ({100 * ex.mean():.4f} %): {txt}")
        for i, cl, *_ in kinds:
            if cl >= 0 and len(p.members[cl]) > 1:
                w("             (the same picture: " + ", ".join(f"{m['kind']} {m['id']} '{m.get('name')}'" for m in p.members[cl]) + ")")
            if cl >= 0 and p.member(cl).get("spec"):
                w(f"             (the client's data for {p.member(cl)['id']}: spec {p.member(cl)['spec']})")
    # 2. the unreadable frames
    w("-- frames on which a cell was NOT readable (its last exact reading is held)")
    if not info["unreadable"]:
        w("   none")
    for u in info["unreadable"]:
        rs = _runs(u["frames"])
        key = info["labels"][u["cell"]] or f"cell {u['cell']}"
        w(f"   {key:9s} {u['why']}: {len(u['frames'])} frames in {len(rs)} runs: " +
          ", ".join(f"{a}..{b}" if b > a else f"{a}" for a, b, _ in rs[:12]) + (" ..." if len(rs) > 12 else ""))
    allbad = np.flatnonzero(~exact.all(axis=1))
    if len(allbad):
        rs = _runs([int(x) for x in allbad])
        w(f"   in all {len(allbad)} frames in {len(rs)} runs with at least one unreadable cell (the longest "
          f"{max(r[2] for r in rs)} frames in a row); the bar's own signature on them: min "
          f"{100 * float(z['bar'][allbad].min()):.0f} %, median {100 * float(np.median(z['bar'][allbad])):.0f} %")
    # 3. the changes
    ev = info["events"]
    steps = [e for e in ev if e["d"] is not None]
    other = [e for e in ev if e["d"] is None]
    w(f"-- changes of an exact reading: {len(ev)} ({len(steps)} amount steps, {len(other)} other)")
    for e in other:
        w(f"   frame {e['n']} t {e['t']:.2f} {e['key']}: {e['was']} -> {e['now']}")
    for key in sorted({e["key"] for e in steps}):
        cnt = Counter(e["d"] for e in steps if e["key"] == key)
        w(f"   {key}: steps " + ", ".join(f"{dd:+d} x{cc}" for dd, cc in sorted(cnt.items())))
    # the potion keys: per cell, the held content's spec at any time
    held_cls = np.full((N, K), -1, np.int64)
    for k in range(K):
        idx = np.where(exact[:, k], np.arange(N), -1)
        np.maximum.accumulate(idx, out=idx)
        held_cls[:, k] = np.where(idx >= 0, cls[np.maximum(idx, 0), k], -1)

    def cls_at(k: int, tt: float) -> int:
        return int(held_cls[min(int(np.searchsorted(t, tt)), N - 1), k])

    def spec_at(k: int, tt: float) -> dict:
        cl = cls_at(k, tt)
        sp = (p.member(cl).get("spec") or {}) if cl >= 0 else {}
        return {s: sp[s] for s in ("hp", "mp") if sp.get(s)}

    lab = info["labels"]
    downs_of, ups_of = {}, {}
    for kr in keys:
        (downs_of if kr["down"] else ups_of).setdefault(kr["key"], []).append(kr["t"])
    for key in [x for x in lab if x and downs_of.get(x)]:
        if not any(spec_at(lab.index(key), tt) for tt in downs_of[key]):
            w(f"-- key `{key}`: {len(downs_of[key])} presses in the key log - no HP / MP item on it, nothing to check")
    presses = sorted((tt, key) for key in lab if key for tt in downs_of.get(key, []) if spec_at(lab.index(key), tt))
    all_specs = {}
    for k in range(K):
        for cl in {int(x) for x in np.unique(held_cls[:, k]) if x >= 0}:
            for s_, v in (p.member(cl).get("spec") or {}).items():
                if s_ in ("hp", "mp") and v:
                    all_specs.setdefault(s_, set()).add(v)
    # A. the HUD's potion-sized rises against the -1 steps
    rises = []
    for stat, arr in (("hp", hp), ("mp", mp)):
        if stat not in all_specs:
            continue
        thr = 0.6 * min(all_specs[stat])
        v = arr[:, 0].astype(np.int64)
        dv = np.diff(v)
        dv[(v[1:] < 0) | (v[:-1] < 0)] = 0
        for j in np.flatnonzero(dv >= thr):
            rises.append({"stat": stat, "t": float(t[j + 1]), "n": int(n[j + 1]), "dv": int(dv[j]), "to": int(v[j + 1]),
                          "max": int(arr[j + 1, 1])})
    rises.sort(key=lambda r: r["t"])
    minus = [e for e in steps if e["d"] < 0]
    for e in minus:
        e["stats"] = spec_at(e["cell"], e["t"])
    paired, used_s = [], set()
    for r in rises:
        cand = [i for i, e in enumerate(minus)                     # (both in time order: the earliest fits)
                if i not in used_s and r["stat"] in e["stats"] and abs(e["t"] - r["t"]) <= pair_s]
        if cand:
            i = cand[0]
            used_s.add(i)
            r["step"] = minus[i]
            minus[i]["rise"] = r
            paired.append(r)
    w(f"-- A. the HUD against the amounts: {len(rises)} potion-sized rises of HP / MP between two frames ("
      + (", ".join(f"{st.upper()} +{dv} x{cc}" for (st, dv), cc in
                   sorted(Counter((r['stat'], r['dv']) for r in rises).items(), key=lambda kv: -kv[1])) or "none")
      + f"); {len(minus)} steps of -1 or less ("
      + (", ".join(f"{k_} x{c_}" for k_, c_ in sorted(Counter(e['key'] for e in minus).items())) or "none") + ")")
    w(f"   a rise WITH its -1 step on a key of that stat within {pair_s} s: {len(paired)} of {len(rises)} rises; steps "
      f"with their rise: {len(used_s)} of {len(minus)}")
    if paired:
        dl = [r["step"]["t"] - r["t"] for r in paired]
        w(f"   the step comes after the HUD's rise by: p50 {1000 * _pct(dl, 50):.0f} ms, p90 {1000 * _pct(dl, 90):.0f} ms, "
          f"min {1000 * min(dl):.0f}, max {1000 * max(dl):.0f} ms")
        per = Counter((r["step"]["key"], p.name(cls_at(r["step"]["cell"], r["t"])), r["stat"], r["dv"]) for r in paired)
        for (key, nm, st, dv), cc in sorted(per.items(), key=lambda kv: (kv[0][0], -kv[1])):
            w(f"      {key} ({nm}): {st.upper()} +{dv} x{cc}")
    for r in rises:
        if "step" not in r:
            w(f"   A RISE WITH NO STEP: frame {r['n']} t {r['t']:.2f} {r['stat'].upper()} +{r['dv']} (to {r['to']} of {r['max']})")
    for e in minus:
        if "rise" not in e:
            w(f"   a step with no rise: frame {e['n']} t {e['t']:.2f} {e['key']} {e['was'][2]} -> {e['now'][2]}"
              + ("" if e["stats"] else " (the item gives no HP / MP)"))
    # B / C. the presses
    claimed = set()
    if presses:
        w(f"-- B. potion presses in the key log: {len(presses)} ("
          + ", ".join(f"{k_} x{c_}" for k_, c_ in sorted(Counter(k_ for _, k_ in presses).items())) + ")")
        tp = np.array([x[0] for x in presses])
        alone = [i for i in range(len(presses))
                 if (i == 0 or tp[i] - tp[i - 1] > window) and (i == len(tp) - 1 or tp[i + 1] - tp[i] > window)]
        ok = hud_ok = 0
        lag_s, lag_h, bad = {}, {}, []
        for i in alone:
            t0, key = presses[i]
            k = lab.index(key)
            mine = [e for e in steps if e["key"] == key and t0 <= e["t"] <= t0 + window]
            claimed.update(id(e) for e in mine)
            rr = [r for r in rises if r["stat"] in spec_at(k, t0) and t0 <= r["t"] <= t0 + window]
            one = len(mine) == 1 and mine[0]["d"] == -1
            ok += one
            hud_ok += one and len(rr) == 1
            if one:
                lag_s.setdefault(key, []).append(mine[0]["t"] - t0)
            if one and len(rr) == 1:
                lag_h.setdefault(key, []).append(rr[0]["t"] - t0)
            else:
                held = next((u - t0 for u in ups_of.get(key, []) if u >= t0), None)
                i_at = min(int(np.searchsorted(t, t0)), N - 1)
                bad.append(f"      {key} at t {t0:.3f} (frame {int(n[i_at])}, held {'?' if held is None else f'{held:.3f}'} s): "
                           f"steps {[e['d'] for e in mine]} at frames {[e['n'] for e in mine]}; HUD rises "
                           f"{[(r['stat'], r['dv'], r['n']) for r in rr]}; amount at the press {int(amount[i_at, k])}, "
                           f"the cell readable then: {bool(exact[i_at, k])}; HP {hp[i_at].tolist()} MP {mp[i_at].tolist()}")
        w(f"   alone (no other potion press within {window} s before or after): {len(alone)}; of them one -1 step on "
          f"the key within {window} s: {ok}; that step AND one rise of the item's stat: {hud_ok}")
        for key in sorted(lag_s):
            ls, lh = lag_s[key], lag_h.get(key, [])
            w(f"      {key}: key-down -> the step p50 {1000 * _pct(ls, 50):.0f} ms, p90 {1000 * _pct(ls, 90):.0f} ms, min "
              f"{1000 * min(ls):.0f}, max {1000 * max(ls):.0f} ms (n {len(ls)})" +
              (f"; key-down -> the HUD's rise p50 {1000 * _pct(lh, 50):.0f} ms, p90 {1000 * _pct(lh, 90):.0f} ms" if lh else ""))
        allk = [x for v in lag_s.values() for x in v]
        if allk:
            w(f"      all keys: key-down -> the step p50 {1000 * _pct(allk, 50):.0f} ms, p90 {1000 * _pct(allk, 90):.0f} ms, "
              f"min {1000 * min(allk):.0f}, max {1000 * max(allk):.0f} ms (n {len(allk)})")
        if bad:
            w(f"   the {len(bad)} presses alone that are NOT (one -1 step + one rise):")
            L.extend(bad)
        # C. bursts
        alone_set = set(alone)
        groups = []
        for i in range(len(presses)):
            if i in alone_set:
                continue
            if groups and tp[i] - tp[groups[-1][-1]] <= window:
                groups[-1].append(i)
            else:
                groups.append([i])
        n_p = sum(len(g) for g in groups)
        tot_s = tot_r = 0
        lines = []
        for g in groups:
            a, b = tp[g[0]], tp[g[-1]] + window
            gk = Counter(presses[i][1] for i in g)
            ss = [e for e in steps if e["d"] < 0 and a <= e["t"] <= b and e["key"] in gk]
            claimed.update(id(e) for e in ss)
            stats = {s_ for i in g for s_ in spec_at(lab.index(presses[i][1]), presses[i][0])}
            rr = [r for r in rises if r["stat"] in stats and a <= r["t"] <= b]
            sk = Counter(e["key"] for e in ss)
            tot_s += len(ss)
            tot_r += len(rr)
            if any(sk.get(k_, 0) != c_ for k_, c_ in gk.items()):
                i_at = min(int(np.searchsorted(t, a)), N - 1)
                lines.append(f"      t {a:.2f} (frame {int(n[i_at])}): presses " +
                             ", ".join(f"{presses[i][1]}@+{tp[i] - a:.2f}" for i in g) + "; steps " +
                             (", ".join(f"{e['key']}{e['d']:+d}@+{e['t'] - a:.2f}" for e in ss) or "none") + "; rises " +
                             (", ".join(f"{r['stat'].upper()}+{r['dv']}@+{r['t'] - a:.2f}" for r in rr) or "none"))
        w(f"-- C. the other {n_p} presses, in {len(groups)} bursts (presses <= {window} s apart): {tot_s} steps of -1, "
          f"{tot_r} rises; bursts in which a key has fewer or more steps than presses: {len(lines)}")
        L.extend(lines)
    # steps no press explains
    free = [e for e in steps if id(e) not in claimed]
    w(f"-- amount steps outside every press window ({window} s after a press of that key): {len(free)}")
    cnt = Counter((e["key"], e["d"]) for e in free)
    for (key, dd), cc in sorted(cnt.items()):
        w(f"   {key} {dd:+d}: x{cc}")
    for e in free[:80]:
        r = e.get("rise")
        w(f"      frame {e['n']} t {e['t']:.2f} {e['key']}: {e['was'][2]} -> {e['now'][2]}"
          + (f"   (with the HUD's {r['stat'].upper()} +{r['dv']})" if r else ""))
    # an amount that changes and comes straight back
    flick = []
    for key in sorted({e["key"] for e in steps}):
        ks = [e for e in steps if e["key"] == key]
        for a, b in zip(ks, ks[1:]):
            if b["now"][2] == a["was"][2] and b["t"] - a["t"] <= 2.0:
                flick.append((a, b))
    w(f"-- an amount that changed and came straight back within 2 s: {len(flick)}")
    for a, b in flick:
        w(f"      {a['key']}: {a['was'][2]} -> {a['now'][2]} at frame {a['n']} (t {a['t']:.2f}), back at frame {b['n']} "
          f"(t {b['t']:.2f}, {1000 * (b['t'] - a['t']):.0f} ms later)")
    text = "\n".join(L)
    (d / "report.txt").write_text(text + "\n", encoding="utf-8")
    print(text)


# ---- a contact sheet -------------------------------------------------------------------------------------------------
def sheet_row(p: Pack, img: np.ndarray, head: str, note: str = "") -> np.ndarray:
    """The bar's crop x4 with what a from-scratch read of this frame says beside it."""
    x0, y0, x1, y1 = BX - 6, BY + 28, BX + 157, BY + 118
    crop = cv2.resize(img[y0:y1, x0:x1], None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    pane = np.full((crop.shape[0], 800, 3), 24, np.uint8)
    cv2.putText(pane, f"{head}   bar signature {100 * p.bar_share(img):.0f} %", (8, 22), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (0, 255, 255), 1, cv2.LINE_AA)
    if note:
        cv2.putText(pane, note, (8, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 200, 255), 1, cv2.LINE_AA)
    for k, (x, y) in enumerate(p.cells):
        r, _ = p.read_cell(img[y:y + CELL, x:x + CELL], k)
        if r.kind is None:
            txt, col = f"({DEFAULT_KEYS[p.rows][k]}): NOT READ - {r.why}", (80, 80, 255)
        elif r.kind == "empty":
            txt, col = f"{r.key}: empty", (200, 200, 200)
        else:
            txt = f"{r.key}: {r.kind} {r.id} '{p.name(r.cls)}'" + ("" if r.amount is None else f"   amount {r.amount}")
            col = (120, 255, 120)
        cv2.putText(pane, txt, (8, 78 + 34 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1, cv2.LINE_AA)
    row = np.hstack([crop, pane])
    return np.vstack([row, np.full((6, row.shape[1], 3), 90, np.uint8)])


def sheet(out: Path, moments: list) -> Path:
    """moments: ["CAP@n" or "CAP@n@note", ...] -> one PNG, a row per moment."""
    import frames as rec
    p = Pack()
    rows = []
    for mo in moments:
        cap, n, *note = mo.split("@", 2)
        c = rec.clip(cap, False, "proto_slots")
        img = rec.read(c.run, rec.name_of(int(n)))
        if img is None:
            print(f"{cap}: frame {n} unreadable")
            continue
        rows.append(sheet_row(p, img, f"{c.name}  frame {n}", note[0] if note else ""))
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack(rows))
    print(f"{len(rows)} moments -> {out}")
    return out


# ---- the reader against the client's own pictures (no footage) --------------------------------------------------------
def selftest(seed: int = 1) -> None:
    """Every content picture of the pack drawn into a cell the way the client does (keycap + content + a random
    amount + a key label) and read back: it must come back as itself. Says how many pictures cannot be told apart
    on the bar (two ids, one look), and whether any picture is mistaken for another, any amount or label misread.
    Run for the 2-row bar and (its cells taken from the client's 3-row picture: never seen in footage) the 3-row one."""
    rng = np.random.default_rng(seed)
    for rows in (2, 3):
        p = Pack(rows)
        K = len(p.cells)
        usual = [i for i, k in enumerate(p.lab_key) if k in DEFAULT_KEYS[2]]
        n = wrong = unsure_pic = n_lab = bad_lab = twin_lab = 0
        for cls in range(len(p.content)):
            k = int(rng.integers(K))
            li = int(rng.choice(usual)) if rng.random() < 0.7 else int(rng.integers(len(p.lab_key)))
            m = p.member(cls)
            amount = None
            digs = []
            if m["kind"] == "item" and rng.random() < 0.8:
                amount = int(rng.choice([0, 1, 7, 10, 11, 99, 100, 111, 200, 999, 1000, 1111, 4321, int(rng.integers(0, 2000))]))
                x = DIGITS_AT[0]
                for ch in str(amount):
                    digs.append((int(ch), x))
                    x += p.dg_w[int(ch)]
                if x > CELL:                                   # (does not fit the cell: no state this reader knows)
                    amount, digs = None, []
            crop = p.expect(k, cls, digs, li)
            r, _ = p.read_cell(crop, k)
            n += 1
            unsure_pic += bool(r.alts)                          # another picture fits these pixels as well
            if cls not in (r.cls,) + r.alts or r.amount != amount or r.key != p.lab_key[li]:
                wrong += 1
                print(f"  rows {rows}: class {cls} {m['kind']} {m['id']} '{m.get('name')}' amount {amount} label "
                      f"{p.lab_key[li]} read as {r}")
        same_look = 0
        for k in range(K):
            seen = {}
            for cls in range(len(p.content)):
                b = p.composite(k, cls).tobytes()
                same_look += b in seen
                seen[b] = cls
            if k == 0:
                first = same_look
        for li in range(len(p.lab_key)):                        # every key label on an empty keycap
            k = int(rng.integers(K))
            r, _ = p.read_cell(p.expect(k, -1, [], li), k)
            n_lab += 1
            bad_lab += not (r.kind == "empty" and r.key == p.lab_key[li])
            twin_lab += bool(p.lab_also[li])
        print(f"{rows}-row bar: {n} pictures drawn with an amount and a label and read back: {wrong} wrong; on "
              f"{unsure_pic} of them another picture fits the same pixels (they differ only under the label or the "
              f"digits drawn here: `alts`); {first} pictures look exactly like another one once laid over the keycap "
              f"(cell 0); {n_lab} key labels on an empty keycap: {bad_lab} wrong, {twin_lab} of the labels stand for "
              f"more than one key")


# ---- speed -----------------------------------------------------------------------------------------------------------
def bench(cap: str = "20261120_235747_1#0", n_frames: int = 600) -> None:
    import frames as rec
    c = rec.clip(cap, False, "proto_slots")
    imgs = [rec.read(c.run, name) for _, name, _ in c.frames()[:n_frames]]
    t0 = time.perf_counter()
    p = Pack()
    for k in range(len(p.cells)):
        p.table(k)
    t_load = time.perf_counter() - t0
    f0 = imgs[0]
    _PACKS[2] = p
    read_slots(f0)
    reps = 500
    a = time.perf_counter()
    for _ in range(reps):
        read_slots(f0)
    full = (time.perf_counter() - a) / reps
    tr = SlotTracker(p)
    tr.update(f0)
    a = time.perf_counter()
    for _ in range(5000):
        tr.update(f0)
    same = (time.perf_counter() - a) / 5000
    # one cell's amount changes (the usual event): the cell re-read with its hint
    k = next((k for k in range(len(p.cells)) if tr.held[k] and tr.held[k].amount is not None), 0)
    x, y = p.cells[k]
    crop = f0[y:y + CELL, x:x + CELL]
    hint = Hint(tr.label[k], tr.held[k].cls)
    a = time.perf_counter()
    for _ in range(2000):
        p.read_cell(crop, k, hint)
    one = (time.perf_counter() - a) / 2000
    tr = SlotTracker(p)
    a = time.perf_counter()
    for im in imgs:
        tr.update(im)
    seq = (time.perf_counter() - a) / len(imgs)
    print(f"loading the pack + its lookup table: {1000 * t_load:.0f} ms (once)")
    print(f"a full read of {len(p.cells)} slots from scratch (read_slots): {1000 * full:.3f} ms")
    print(f"one changed cell re-read (label hint, digits, lookup, full verify): {1e6 * one:.1f} us")
    print(f"an unchanged frame (SlotTracker.update, {len(p.cells)} cells compared): {1e6 * same:.1f} us")
    print(f"{len(imgs)} consecutive frames of {cap} through SlotTracker: {1e6 * seq:.1f} us a frame, {tr.reads} cell reads")
    print("read_slots(first frame):", read_slots(f0))


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    if a[0] == "build":
        build(Path(a[a.index("--export") + 1]) if "--export" in a else None)
    elif a[0] == "run":
        run(a[1], int(a[a.index("--every") + 1]) if "--every" in a else 1)
    elif a[0] == "report":
        report(a[1])
    elif a[0] == "sheet":
        sheet(Path(a[1]), a[2:])
    elif a[0] == "bench":
        bench(*a[1:2])
    elif a[0] == "selftest":
        selftest()
    else:
        raise SystemExit(f"unknown command {a[0]} (build / run / report / sheet / bench / selftest)")


if __name__ == "__main__":
    main()
