. "$PSScriptRoot\load.ps1"
$O = 'C:\Users\Yoav\dev\cw-data\export'
function Open-Bms($p) { $f = [MapleLib.WzLib.WzFile]::new($p, [MapleLib.WzLib.WzMapleVersion]::BMS); $st = $f.ParseWzFile($null); [Console]::Error.WriteLine("$p $st"); $f }
$n = 0
$f = Open-Bms "$D\Map\Map_000.wz"
foreach ($i in $f.WzDirectory.WzImages) { Save-Xml $i "$O\Map\$($i.Name).xml"; $n++ }
$f = Open-Bms "$D\Map\Map\Map0\Map0_000.wz"
"Map0 imgs: $($f.WzDirectory.WzImages.Count)"
foreach ($id in '000000042','010004040','010004050','010001070') { $i = $f.WzDirectory.WzImages | ? Name -eq "$id.img"; if ($i) { Save-Xml $i "$O\Map\Map0\$id.img.xml"; $n++ } else { "missing $id" } }
$m = Open-Ms "$D\Packs\Mob_00000.ms"
foreach ($i in $m.WzDirectory.WzImages) { Save-Xml $i "$O\Mob\$($i.Name).xml"; $n++ }
foreach ($s in Get-ChildItem "$D\String" -Filter *_000.wz -Recurse) { $f = Open-Bms $s.FullName; "String: " + (($f.WzDirectory.WzImages | % Name) -join ' ')
  foreach ($i in $f.WzDirectory.WzImages | ? Name -in 'Mob.img','Map.img') { Save-Xml $i "$O\String\$($i.Name).xml"; $n++ } }
"exported $n images"
