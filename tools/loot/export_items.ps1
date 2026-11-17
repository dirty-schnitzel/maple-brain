# Export what a DROP shows from the client's own files (plan session prototype for PLAN-loot.md; the plan moves this
# into tools\cwdata\export.ps1 + `assets build`). Reads the COPY of the game's Data folder ($D in load.ps1). Writes:
#   <Out>\png\<8-digit id>_raw.png, <id>_icon.png      info/iconRaw + info/icon of every Etc / Consume / Install item
#                                                      and every equip (Character\<slot>\<id>.img), links resolved
#   <Out>\png\0900000<n>_raw_<f>.png                   the meso pictures: Item\Special\0900.img, 4 sizes x 4 frames
#   <Out>\items.json   id -> {kind, name, raw: [w, h, ox, oy], icon: [w, h, ox, oy], frames: [[w, h, ox, oy, delay]..]}
# Run (R2R off): $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\loot\export_items.ps1
param([string]$Out = 'C:\Users\Yoav\dev\cw-data\export\Item')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\cwdata\load.ps1"

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
# one canvas -> its png; returns [w, h, ox, oy] (the origin is the placeholder's own: the link holds only pixels)
function Save-Canvas($c, $img, [string]$path) {
  $bmp = Get-Bitmap $c $img
  if (-not $bmp) { throw "no bitmap" }
  $o = $c.GetProperty('origin')
  $r = @([int]$bmp.Width, [int]$bmp.Height, [int]$o.X.Value, [int]$o.Y.Value)
  $bmp.Save($path, [Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  , $r
}

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force "$Out\png" | Out-Null
$items = [ordered]@{}
$fails = [Collections.Generic.List[string]]::new()
$t0 = Get-Date

# names
$names = @{}
$sf = Open-Bms "$D\String\String_000.wz"
foreach ($name in 'Consume.img', 'Ins.img') {
  foreach ($p in ($sf.WzDirectory.WzImages | ? Name -eq $name).WzProperties) {
    $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } }
}
foreach ($grp in ($sf.WzDirectory.WzImages | ? Name -eq 'Etc.img').WzProperties) {
  foreach ($p in $grp.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } }
foreach ($top in ($sf.WzDirectory.WzImages | ? Name -eq 'Eqp.img').WzProperties) {
  foreach ($slot in $top.WzProperties) {
    foreach ($p in $slot.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } } }
"names: $($names.Count)"

function Add-Item([string]$kind, [string]$id, $info, $img) {
  $e = [ordered]@{ kind = $kind; name = $names[[int]$id] }
  foreach ($k in 'iconRaw', 'icon') {
    $c = $info.GetFromPath($k)
    if ($c -isnot [MapleLib.WzLib.WzProperties.WzCanvasProperty]) { continue }
    $tag = if ($k -eq 'iconRaw') { 'raw' } else { 'icon' }
    try { $e[$tag] = Save-Canvas $c $img "$Out\png\$($id)_$tag.png" }
    catch { $fails.Add("$kind $id $k : $_") }
  }
  if ($e.Contains('raw') -or $e.Contains('icon')) { $items[$id] = $e }
}

# Etc / Consume / Install: <kind>\<4-digit>.img\<8-digit id>\info\{icon, iconRaw}
foreach ($kind in 'Etc', 'Consume', 'Install') {
  $n0 = $items.Count
  foreach ($w in Get-ChildItem "$D\Item\$kind" -Filter "$($kind)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      foreach ($it in $img.WzProperties) {
        $info = $it.GetFromPath('info')
        if ($info) { Add-Item $kind $it.Name $info $img }
      }
    }
  }
  "$kind : $($items.Count - $n0) items"
}

# mesos: Special\0900.img\0900000<n>\iconRaw\<f>
$sp = (Open-Bms "$D\Item\Special\Special_000.wz").WzDirectory.WzImages | ? Name -eq '0900.img'
foreach ($it in $sp.WzProperties) {
  $raw = $it.GetFromPath('iconRaw')
  if (-not $raw) { continue }
  $fr = @()
  foreach ($c in $raw.WzProperties) {
    if ($c -isnot [MapleLib.WzLib.WzProperties.WzCanvasProperty]) { continue }
    try {
      $r = Save-Canvas $c $sp "$Out\png\$($it.Name)_raw_$($c.Name).png"
      $dl = $c.GetProperty('delay')                       # ($d would be $D: PowerShell names ignore case)
      $fr += , @($r[0], $r[1], $r[2], $r[3], $(if ($dl) { [int]$dl.Value } else { 0 }))
    } catch { $fails.Add("Special $($it.Name) $($c.Name): $_") }
  }
  $items[$it.Name] = [ordered]@{ kind = 'Special'; name = $null; frames = $fr }
}
"Special 0900: $(@($sp.WzProperties).Count) entries"

# equips: Character\<slot>\<8-digit id>.img\info\{icon, iconRaw}
foreach ($slot in 'Accessory', 'Cap', 'Cape', 'Coat', 'Glove', 'Longcoat', 'Pants', 'Ring', 'Shield', 'Shoes', 'Weapon') {
  $n0 = $items.Count
  foreach ($w in Get-ChildItem "$D\Character\$slot" -Filter "$($slot)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      $info = $img.GetFromPath('info')
      if ($info) { Add-Item $slot ($img.Name -replace '\.img$', '') $info $img }
      $img.UnparseImage()
    }
  }
  "$slot : $($items.Count - $n0) items"
}

$items | ConvertTo-Json -Depth 6 -Compress | Set-Content -Encoding utf8 "$Out\items.json"
"items: $($items.Count), failed: $($fails.Count)"; $fails | Select-Object -First 20 | % { "  $_" }
"done in $([int]((Get-Date) - $t0).TotalSeconds) s -> $Out"
