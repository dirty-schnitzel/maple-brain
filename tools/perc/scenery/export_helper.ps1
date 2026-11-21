# PLAN-moving-scenery.md, the planner's helper (until export.ps1 does it: the plan's step 1): the raw bytes of the
# Back / Obj / Tile canvases whose pixel format MapleLib gives no bitmap for (1537) -> $Out\raw1537.tsv, and
# MapHelper.img's weather pictures (the 7 clouds) and portal pictures -> $Out\MapHelper\...png.
# Reads the COPY of the client's Data folder only (load.ps1's $D), writes nothing outside -Out.
# Run: $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\perc\scenery\export_helper.ps1
param([string]$Out = 'F:\dev\maple-corpus\work\scenery')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\cwdata\load.ps1"
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
  $dir = ($parts[0..($k - 1)] -join '\')
  if (-not $script:canvasDirs.ContainsKey($dir)) {
    $imgs = @{}
    foreach ($w in Get-ChildItem "$D\$dir" -Filter "$($parts[$k - 1])_*.wz") {
      foreach ($i in (Open-Bms $w.FullName).WzDirectory.WzImages) { $imgs[$i.Name] = $i }
    }
    $script:canvasDirs[$dir] = $imgs
  }
  $img = $script:canvasDirs[$dir][$parts[$k]]
  $img.GetFromPath(($parts[($k + 1)..($parts.Count - 1)] -join '/'))
}
function Resolve-Canvas($c, $img) {
  for ($hop = 0; $hop -lt 8; $hop++) {
    $in = $c.GetProperty('_inlink'); $o = $c.GetProperty('_outlink')
    if ($in) { $c = $img.GetFromPath($in.Value) }
    elseif ($o) { $c = Get-OutlinkTarget $o.Value }
    else { return $c }
  }
}
function Raw-Bytes($c) {
  $png = $c.PngProperty
  $raw = $png.GetCompressedBytes($false)
  $z = [IO.Compression.DeflateStream]::new([IO.MemoryStream]::new($raw, 2, $raw.Length - 2), [IO.Compression.CompressionMode]::Decompress)
  $o = [IO.MemoryStream]::new(); $z.CopyTo($o); , $o.ToArray()
}
# 1. every canvas of the Back / Obj / Tile sets: its pixel format; the raw bytes of the 1537 ones
$fmt = @{}
$rows = [Collections.Generic.List[string]]::new()
function Walk($prop, $img, [string]$path) {
  foreach ($c in $prop.WzProperties) {
    if ($c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty]) {
      $t = Resolve-Canvas $c $img
      if (-not $t) { continue }
      $f = [int]$t.PngProperty.Format
      $script:fmt[$f] = 1 + [int]$script:fmt[$f]
      if ($f -notin 1, 2, 513, 1026, 2050, 257) {
        $b = Raw-Bytes $t
        $hex = ($b[0..([Math]::Min(47, $b.Length - 1))] | % { $_.ToString('X2') }) -join ' '
        $rows.Add("$f`t$($img.Name)/$path/$($c.Name)`t$($t.PngProperty.Width)x$($t.PngProperty.Height)`t$($b.Length)`t$hex")
      }
    } elseif ($c -is [MapleLib.WzLib.WzProperties.WzSubProperty]) { Walk $c $img "$path/$($c.Name)" }
  }
}
foreach ($kind in 'Back', 'Obj', 'Tile') {
  foreach ($w in Get-ChildItem "$D\Map\$kind" -Filter "$($kind)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) { Walk $img $img ''; $img.UnparseImage() }
  }
}
"formats: " + (($fmt.GetEnumerator() | sort Name | % { "$($_.Name): $($_.Value)" }) -join ', ')
$rows | Set-Content -Encoding utf8 "$Out\raw1537.tsv"
"other-format canvases: $($rows.Count) -> $Out\raw1537.tsv"
# 2. MapHelper.img: weather/cloud pictures (+ the portal pictures) as PNG
$mh = (Open-Bms "$D\Map\Map_000.wz").WzDirectory.WzImages | ? Name -eq 'MapHelper.img'
function Export-Tree($prop, $img, [string]$base) {
  foreach ($c in $prop.WzProperties) {
    if ($c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty]) {
      $t = Resolve-Canvas $c $img
      $bmp = $t.GetBitmap()
      if ($bmp) {
        New-Item -ItemType Directory -Force $base | Out-Null
        $bmp.Save("$base\$($c.Name).png", [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose(); $script:n++
      } else { "no bitmap: $base/$($c.Name) format $([int]$t.PngProperty.Format)" }
    } elseif ($c -is [MapleLib.WzLib.WzProperties.WzSubProperty]) { Export-Tree $c $img "$base\$($c.Name)" }
  }
}
$script:n = 0
Export-Tree $mh.GetFromPath('weather') $mh "$Out\MapHelper\weather"
Export-Tree $mh.GetFromPath('portal') $mh "$Out\MapHelper\portal"
"MapHelper pictures: $script:n"
