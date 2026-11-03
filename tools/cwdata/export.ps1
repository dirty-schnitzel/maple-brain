# Export Classic World's own client data for maplebot (the single source of game data; see assets/README.md).
# Reads a COPY of the game's Data folder ($D in load.ps1), never the install. Writes to -Out:
#   Map\*.img.xml                    Map.wz's top images (Physics, ...)
#   Map\Map<N>\<9-digit id>.img.xml  every map (footholds, ladderRope, life, portal, miniMap, info)
#   Map\minimap\<9-digit id>.png     every map's miniMap canvas, links resolved
#   Mob\<7-digit id>.img.xml         every mob (info + per-frame origin/lt/rb/head/delay)
#   Mob\png\<7-digit id>\<anim>_<n>.png  every frame of every animation, links resolved, as stored (facing left)
#   String\Map.img.xml, Mob.img.xml  names
# Run (R2R off, see load.ps1): $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\cwdata\export.ps1
param([string]$Out = 'C:\Users\Yoav\dev\cw-data\export')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\load.ps1"

function Open-Bms($p) {
  $f = [MapleLib.WzLib.WzFile]::new($p, [MapleLib.WzLib.WzMapleVersion]::BMS)
  $st = $f.ParseWzFile($null)
  if ("$st" -ne 'Success') { throw "$p : $st" }
  $f
}

# _outlink 'Map/Map/Map0/_Canvas/000000042.img/miniMap/canvas' -> Data\Map\Map\Map0\_Canvas\_Canvas_*.wz, image, path
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

# A canvas' own pixels, following _inlink (same image) and _outlink (a _Canvas file) links
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

$xml = [MapleLib.WzLib.Serializer.WzClassicXmlSerializer]::new(1, [MapleLib.WzLib.Serializer.LineBreak]::Unix, $false)
function Save-Xml($img, $path) {
  New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
  $xml.SerializeImage($img, $path)
}

foreach ($sub in 'Map', 'Mob', 'String') {                 # a clean export every time (nothing stale after a patch)
  if (Test-Path "$Out\$sub") { Remove-Item -Recurse -Force "$Out\$sub" } }
$fails = [Collections.Generic.List[string]]::new()
$t0 = Get-Date

# Map.wz top images (Physics.img = the player's movement constants)
foreach ($i in (Open-Bms "$D\Map\Map_000.wz").WzDirectory.WzImages) { Save-Xml $i "$Out\Map\$($i.Name).xml" }

# every map + its minimap picture
$nMap = 0; $nMini = 0
foreach ($dir in Get-ChildItem "$D\Map\Map" -Directory -Filter 'Map?') {
  foreach ($w in Get-ChildItem $dir.FullName -Filter "$($dir.Name)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      Save-Xml $img "$Out\Map\$($dir.Name)\$($img.Name).xml"; $nMap++
      $c = $img.GetFromPath('miniMap/canvas')
      if ($c) {
        try { Save-Png (Get-Bitmap $c $img) "$Out\Map\minimap\$($img.Name -replace '\.img$', '').png"; $nMini++ }
        catch { $fails.Add("minimap $($img.Name): $_") }
      }
      $img.UnparseImage()
    }
  }
}
"maps: $nMap ($nMini minimaps)"

# every mob + every frame
$nMob = 0; $nPng = 0
$ms = Open-Ms "$D\Packs\Mob_00000.ms"
foreach ($img in $ms.WzDirectory.WzImages) {
  Save-Xml $img "$Out\Mob\$($img.Name).xml"; $nMob++
  $id = $img.Name -replace '\.img$', ''
  foreach ($anim in $img.WzProperties) {
    if ($anim.Name -eq 'info' -or $anim -isnot [MapleLib.WzLib.WzProperties.WzSubProperty]) { continue }
    foreach ($c in $anim.WzProperties) {
      if ($c -isnot [MapleLib.WzLib.WzProperties.WzCanvasProperty] -or $c.Name -notmatch '^\d+$') { continue }
      try { Save-Png (Get-Bitmap $c $img) "$Out\Mob\png\$id\$($anim.Name)_$($c.Name).png"; $nPng++ }
      catch { $fails.Add("mob $id $($anim.Name)/$($c.Name): $_") }
    }
  }
}
"mobs: $nMob ($nPng frames)"

# names
foreach ($s in Get-ChildItem "$D\String" -Filter '*_000.wz' -Recurse) {
  foreach ($i in (Open-Bms $s.FullName).WzDirectory.WzImages | ? Name -in 'Mob.img', 'Map.img') { Save-Xml $i "$Out\String\$($i.Name).xml" }
}

"failed: $($fails.Count)"; $fails | % { "  $_" }
"done in $([int]((Get-Date) - $t0).TotalSeconds) s -> $Out"
if ($fails.Count) { exit 1 }
