# Peek (plan session, PLAN-loot.md): how the client stores what a drop shows - Item\{Etc, Consume, Install, Special}
# images, Character\<slot> equips (info/icon, info/iconRaw), String names. Prints structure only, writes nothing.
# Run: $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\loot\peek_items.ps1
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\cwdata\load.ps1"

function Open-Bms($p) {
  $f = [MapleLib.WzLib.WzFile]::new($p, [MapleLib.WzLib.WzMapleVersion]::BMS)
  $st = $f.ParseWzFile($null)
  if ("$st" -ne 'Success') { throw "$p : $st" }
  $f
}

function Show-Prop($p, [int]$depth, [string]$ind = '') {
  foreach ($c in $p.WzProperties) {
    $t = $c.GetType().Name -replace '^Wz', '' -replace 'Property$', ''
    $v = ''
    if ($c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty]) {
      $v = "$($c.PngProperty.Width)x$($c.PngProperty.Height) fmt $($c.PngProperty.Format)"
    } elseif ($c -isnot [MapleLib.WzLib.WzProperties.WzSubProperty]) { $v = "$($c.WzValue)" }
    "$ind$($c.Name) [$t] $v"
    if ($depth -gt 0 -and ($c -is [MapleLib.WzLib.WzProperties.WzSubProperty] -or $c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty])) {
      Show-Prop $c ($depth - 1) "$ind  "
    }
  }
}

foreach ($kind in 'Etc', 'Consume', 'Install', 'Special', 'Cash') {
  "=== Item\$kind"
  foreach ($w in Get-ChildItem "$D\Item\$kind" -Filter "$($kind)_*.wz") {
    $f = Open-Bms $w.FullName
    $imgs = @($f.WzDirectory.WzImages)
    "  $($w.Name): $($imgs.Count) images: $(($imgs | % Name) -join ' ')"
    $n = 0
    foreach ($img in $imgs) { $n += @($img.WzProperties).Count }
    "  items in them: $n"
  }
}

"=== Item\Etc 0400.img, first item, depth 3"
$f = Open-Bms "$D\Item\Etc\Etc_000.wz"
$img = $f.WzDirectory.WzImages | ? Name -eq '0400.img'
$first = @($img.WzProperties)[0]
"item $($first.Name)"
Show-Prop $first 3 '  '

"=== Item\Consume 0200.img, first item, depth 3"
$f = Open-Bms "$D\Item\Consume\Consume_000.wz"
$img = $f.WzDirectory.WzImages | ? Name -eq '0200.img'
$first = @($img.WzProperties)[0]
"item $($first.Name)"
Show-Prop $first 3 '  '

"=== Item\Special: every image, depth 4"
$f = Open-Bms "$D\Item\Special\Special_000.wz"
foreach ($img in $f.WzDirectory.WzImages) {
  "image $($img.Name)"
  Show-Prop $img 4 '  '
}

"=== Character\Weapon: first image, info depth 2"
$f = Open-Bms "$D\Character\Weapon\Weapon_000.wz"
$imgs = @($f.WzDirectory.WzImages)
"  $($imgs.Count) images"
$img = $imgs[0]
"image $($img.Name)"
Show-Prop ($img.GetFromPath('info')) 2 '  '

"=== Character slots"
foreach ($d in Get-ChildItem "$D\Character" -Directory) {
  $n = 0
  foreach ($w in Get-ChildItem $d.FullName -Filter "$($d.Name)_*.wz") { $n += @((Open-Bms $w.FullName).WzDirectory.WzImages).Count }
  "  $($d.Name): $n images"
}

"=== String images"
foreach ($s in Get-ChildItem "$D\String" -Filter '*_000.wz' -Recurse) {
  foreach ($i in (Open-Bms $s.FullName).WzDirectory.WzImages) { "  $($i.Name): $(@($i.WzProperties).Count) top props" }
}
