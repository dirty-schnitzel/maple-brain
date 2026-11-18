# Peek (plan session, PLAN-loot.md): the String images that hold item names. Prints only.
# Run: $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\loot\peek_strings.ps1
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\cwdata\load.ps1"
function Open-Bms($p) {
  $f = [MapleLib.WzLib.WzFile]::new($p, [MapleLib.WzLib.WzMapleVersion]::BMS)
  $st = $f.ParseWzFile($null)
  if ("$st" -ne 'Success') { throw "$p : $st" }
  $f
}
foreach ($s in Get-ChildItem "$D\String" -Filter '*_000.wz' -Recurse) {
  "file $($s.FullName)"
  $f = Open-Bms $s.FullName
  foreach ($i in $f.WzDirectory.WzImages) {
    $n = 0
    try { $n = @($i.WzProperties).Count } catch { $n = -1 }
    "  $($i.Name): $n top props"
  }
}
$f = Open-Bms "$D\String\String_000.wz"
foreach ($name in 'Etc.img', 'Consume.img', 'Eqp.img', 'Ins.img') {
  $img = $f.WzDirectory.WzImages | ? Name -eq $name
  if (-not $img) { "no $name"; continue }
  "=== $name"
  $k = 0
  foreach ($p in $img.WzProperties) {
    $line = "  $($p.Name)"
    foreach ($q in $p.WzProperties) {
      if ($q -is [MapleLib.WzLib.WzProperties.WzSubProperty]) {
        $line += " | $($q.Name): $(@($q.WzProperties).Count) children"
        $c = @($q.WzProperties)[0]
        if ($c) { $line += " e.g. $($c.Name) -> $(($c.WzProperties | % { "$($_.Name)=$($_.WzValue)" }) -join '; ')" }
      } else { $line += " | $($q.Name)=$($q.WzValue)" }
    }
    $line.Substring(0, [Math]::Min(400, $line.Length))
    $k++
    if ($k -ge 6) { break }
  }
}
