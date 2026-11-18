# Plan session (PLAN-loot.md): image names in the client's other folders (where could a capsule-like drop live?).
# Run: $env:DOTNET_ReadyToRun=0; pwsh -NoProfile -File tools\loot\peek_dirs.ps1
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\cwdata\load.ps1"
function Open-Bms($p) {
  $f = [MapleLib.WzLib.WzFile]::new($p, [MapleLib.WzLib.WzMapleVersion]::BMS)
  $st = $f.ParseWzFile($null)
  if ("$st" -ne 'Success') { throw "$p : $st" }
  $f
}
foreach ($sub in 'Etc', 'Effect', 'Reactor', 'Morph', 'UI', 'Base', 'Quest', 'TamingMob') {
  foreach ($w in Get-ChildItem "$D\$sub" -Filter '*_0*.wz' -Recurse -ErrorAction SilentlyContinue) {
    try {
      $f = Open-Bms $w.FullName
      $names = @($f.WzDirectory.WzImages | % Name)
      "$($w.FullName.Substring($D.Length + 1)): $($names.Count) images: $(($names | Select-Object -First 60) -join ' ')"
    } catch { "$($w.Name): $_" }
  }
}
Get-ChildItem "$D\Packs" | % { "Packs\$($_.Name) $([int]($_.Length / 1MB)) MB" }
