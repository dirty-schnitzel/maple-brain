# Plan session (PLAN-loot.md): the item pictures export_items.ps1 does NOT take - every canvas of Item\Special
# (0900 beyond the mesos, 0910, 0911, MaplePoint) and info/iconRaw + info/icon of Item\Cash and Item\Pet - to name an
# unknown drop seen on a recording. Writes <Out>\<kind>_<image>_<path with _>.png (flat folder).
# Run (R2R off): $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\loot\export_extra.ps1
param([string]$Out = 'C:\Users\Yoav\dev\cw-data\export\ItemExtra')
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
    $in = $c.GetProperty('_inlink'); $ol = $c.GetProperty('_outlink')
    if ($in) { $c = $img.GetFromPath($in.Value) }
    elseif ($ol) { $c = Get-OutlinkTarget $ol.Value }
    else { return $c.GetBitmap() }
    if (-not $c) { throw "broken link in $($img.Name)" }
  }
  throw "link loop in $($img.Name)"
}
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force $Out | Out-Null
$script:n = 0; $script:bad = 0
function Save-All($prop, $img, [string]$name, [int]$depth) {
  foreach ($c in $prop.WzProperties) {
    if ($c.Name -match '[\/:*?"<>|]') { continue }
    if ($c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty]) {
      try { $b = Get-Bitmap $c $img; if ($b) { $b.Save("$Out\$($name)_$($c.Name).png", [Drawing.Imaging.ImageFormat]::Png); $b.Dispose(); $script:n++ } }
      catch { $script:bad++ }
    } elseif ($c -is [MapleLib.WzLib.WzProperties.WzSubProperty] -and $depth -gt 0) {
      Save-All $c $img "$($name)_$($c.Name)" ($depth - 1)
    }
  }
}
foreach ($img in (Open-Bms "$D\Item\Special\Special_000.wz").WzDirectory.WzImages) {
  Save-All $img $img "Special_$($img.Name -replace '\.img$', '')" 4
}
"Special: $script:n pictures"
foreach ($kind in 'Cash', 'Pet') {
  $n0 = $script:n
  foreach ($w in Get-ChildItem "$D\Item\$kind" -Filter "$($kind)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      $base = $img.Name -replace '\.img$', ''
      if ($kind -eq 'Pet') {
        $info = $img.GetFromPath('info')
        if ($info) { Save-All $info $img "Pet_$base" 0 }
      } else {
        foreach ($it in $img.WzProperties) {
          $info = $it.GetFromPath('info')
          if ($info) { Save-All $info $img "Cash_$($it.Name)" 0 }
        }
      }
      $img.UnparseImage()
    }
  }
  "$kind : $($script:n - $n0) pictures"
}
"failed: $script:bad -> $Out"
