# Plan session (PLAN-loot.md): the Etc / Consume / Install items export_items.ps1 gave no picture - what is at
# info/icon and info/iconRaw there (a UOL link? nothing?). Prints only.
# Run: $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\loot\peek_missing.ps1
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\cwdata\load.ps1"
function Open-Bms($p) {
  $f = [MapleLib.WzLib.WzFile]::new($p, [MapleLib.WzLib.WzMapleVersion]::BMS)
  $st = $f.ParseWzFile($null)
  if ("$st" -ne 'Success') { throw "$p : $st" }
  $f
}
$names = @{}
$sf = Open-Bms "$D\String\String_000.wz"
foreach ($name in 'Consume.img', 'Ins.img') {
  foreach ($p in ($sf.WzDirectory.WzImages | ? Name -eq $name).WzProperties) {
    $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } }
}
foreach ($grp in ($sf.WzDirectory.WzImages | ? Name -eq 'Etc.img').WzProperties) {
  foreach ($p in $grp.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } }
foreach ($kind in 'Etc', 'Consume', 'Install') {
  $types = @{}; $shown = 0
  foreach ($w in Get-ChildItem "$D\Item\$kind" -Filter "$($kind)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      foreach ($it in $img.WzProperties) {
        $info = $it.GetFromPath('info')
        $raw = if ($info) { $info.GetFromPath('iconRaw') } else { $null }
        $t = if (-not $info) { 'no info' } elseif (-not $raw) { 'no iconRaw' } else { $raw.GetType().Name }
        if (-not $types.ContainsKey($t)) { $types[$t] = 0 }
        $types[$t]++
        if ($t -ne 'WzCanvasProperty' -and $shown -lt 14) {
          $v = if ($raw) { "$($raw.WzValue)" } else { '' }
          "  $kind $($it.Name) '$($names[[int]$it.Name])' iconRaw: $t $v | info children: $(if ($info) { ($info.WzProperties | % Name) -join ',' })"
          $shown++
        }
      }
    }
  }
  "$kind : $(($types.GetEnumerator() | % { "$($_.Key) $($_.Value)" }) -join '; ')"
}
