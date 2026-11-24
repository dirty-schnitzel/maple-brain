# The client pictures a quickslot is drawn from (PLAN-tracker step 7; maplebrain/perception/slots.py's docstring says
# what the client draws). Reads the COPY of the game's Data folder ($D in load.ps1), never the install. Writes
# <Out>\Slots\ only (cleaned first):
#   ui\QuickSlot.img.xml + ui\png\QuickSlot\...   the bar's background, the key labels, cooldown shade + digits
#   ui\png\ItemNo\<d>.png                         the item amount's digits (Basic.img/ItemNo)
#   ui\png\action\<id>.png                        the key-binding actions (KeyBindings.img/icon: JUMP, ATTACK ...)
#   ui\png\ItemIcon\..., ui\png\SkillIcon\...     marks the client may draw over an icon
#   item\<8-digit id>.png + item\items.json       every item's info/icon (the picture WITH its shadow), its spec
#                                                 (what using it does: hp, mp ...) and a few info flags
#   skill\<id>.png, _d.png, _m.png + skill\skills.json   every skill's icon, iconDisabled, iconMouseOver
# Called by export.ps1 at its end; alone (after a patch, or to refresh only this part), ~25 s:
#   $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\cwdata\export_slots.ps1
# then `python -m maplebrain assets build` -> assets/mcw/slots (the reader's picture pack).
param([string]$Out = 'C:\Users\Yoav\dev\cw-data\export')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\load.ps1"
$Out = Join-Path $Out 'Slots'

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
"slots ui: $script:nPart pictures"

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
  "slots items $kind : $($items.Count - $n0)"
}
$n0 = $items.Count
foreach ($w in Get-ChildItem "$D\Item\Pet" -Filter 'Pet_*.wz') {
  foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
    $info = $img.GetFromPath('info')
    if ($info) { Add-Icon 'Pet' ($img.Name -replace '\.img$', '').PadLeft(8, '0') $info $img $null }
    $img.UnparseImage()
  }
}
"slots items Pet : $($items.Count - $n0)"
foreach ($slot in 'Accessory', 'Cap', 'Cape', 'Coat', 'Glove', 'Longcoat', 'Pants', 'Ring', 'Shield', 'Shoes', 'Weapon') {
  $n0 = $items.Count
  foreach ($w in Get-ChildItem "$D\Character\$slot" -Filter "$($slot)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      $info = $img.GetFromPath('info')
      if ($info) { Add-Icon $slot ($img.Name -replace '\.img$', '') $info $img $null }
      $img.UnparseImage()
    }
  }
  "slots items $slot : $($items.Count - $n0)"
}
New-Item -ItemType Directory -Force "$Out\item" | Out-Null
$items | ConvertTo-Json -Depth 6 -Compress | Set-Content -Encoding utf8 "$Out\item\items.json"
"slots items: $($items.Count) ($script:nNoIcon without info/icon; skipped (a link to a canvas the client lacks): $($skipped.Count) $($skipped -join ', '))"

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
"slots skills: $($skills.Count)"

"slots failed: $($fails.Count)"; $fails | Select-Object -First 40 | % { "  $_" }
"slots done in $([int]((Get-Date) - $t0).TotalSeconds) s -> $Out"
if ($fails.Count) { exit 1 }
