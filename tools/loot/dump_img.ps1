# Plan session (PLAN-loot.md): dump ONE client image - its xml + every canvas (links resolved) - to look at it.
# Run: $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\loot\dump_img.ps1 -Wz Effect\Effect_000.wz -Img DropItemEff.img
param([string]$Wz, [string]$Img, [string]$Out = 'C:\Users\Yoav\dev\cw-data\export\Peek')
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
  $im = $script:canvasDirs[$dir][$parts[$k]]
  if (-not $im) { throw "_outlink $link : no image" }
  $im.GetFromPath(($parts[($k + 1)..($parts.Count - 1)] -join '/'))
}
function Get-Bitmap($c, $im) {
  for ($hop = 0; $hop -lt 8; $hop++) {
    $in = $c.GetProperty('_inlink'); $ol = $c.GetProperty('_outlink')
    if ($in) { $c = $im.GetFromPath($in.Value) }
    elseif ($ol) { $c = Get-OutlinkTarget $ol.Value }
    else { return $c.GetBitmap() }
    if (-not $c) { throw "broken link" }
  }
  throw "link loop"
}
$image = (Open-Bms "$D\$Wz").WzDirectory.WzImages | ? Name -eq $Img
if (-not $image) { throw "no $Img in $Wz" }
$base = "$Out\$($Img -replace '\.img$', '')"
if (Test-Path $base) { Remove-Item -Recurse -Force $base }
New-Item -ItemType Directory -Force $base | Out-Null
[MapleLib.WzLib.Serializer.WzClassicXmlSerializer]::new(1, [MapleLib.WzLib.Serializer.LineBreak]::Unix, $false).SerializeImage($image, "$base.xml")
$script:n = 0
function Save-All($prop, [string]$name) {
  foreach ($c in $prop.WzProperties) {
    if ($c.Name -match '[\/:*?"<>|]') { continue }
    if ($c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty]) {
      try { $b = Get-Bitmap $c $image; if ($b) { $b.Save("$base\$($name)_$($c.Name).png", [Drawing.Imaging.ImageFormat]::Png); $b.Dispose(); $script:n++ } } catch { "  fail $name/$($c.Name): $_" }
    } elseif ($c -is [MapleLib.WzLib.WzProperties.WzSubProperty]) { Save-All $c "$($name)_$($c.Name)" }
  }
}
Save-All $image 'x'
"$Img : $script:n pictures -> $base (+ .xml)"
