# Export Classic World's own client data for maplebrain (the single source of game data; see assets/README.md).
# Reads a COPY of the game's Data folder ($D in load.ps1), never the install. Writes to -Out:
#   Map\*.img.xml                    Map.wz's top images (Physics, ...)
#   Map\Map<N>\<9-digit id>.img.xml  every map (footholds, ladderRope, life, portal, miniMap, info)
#   Map\minimap\<9-digit id>.png     every map's miniMap canvas, links resolved
#   Mob\<7-digit id>.img.xml         every mob (info + per-frame origin/lt/rb/head/delay)
#   Mob\png\<7-digit id>\<anim>_<n>.png  every frame of every animation, links resolved, as stored (facing left)
#   Afterimage\<weapon>.img.xml     attack boxes per weapon type (lt/rb per stance); Skill\<job>.img.xml skills
#   String\Map.img.xml, Mob.img.xml  names
#   Item\png\<8-digit id>_raw.png, Item\items.json  what a drop shows (item pictures; the section below)
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

# Pixel format 1537 (MapleLib 11.1 gives no bitmap): RGB565, one stored pixel per 16x16 block - flat colour tiles
# (back_dryRock/back/0 = Perion's sky, back_midForest/back/0). zlib stream -> (w/16) x (h/16) pixels, 2 bytes each.
function Get-BlockBitmap($c) {
  $png = $c.PngProperty
  if ([int]$png.Format -ne 1537) { throw "no bitmap, pixel format $($png.Format)" }
  $raw = $png.GetCompressedBytes($false)
  $z = [IO.Compression.DeflateStream]::new([IO.MemoryStream]::new($raw, 2, $raw.Length - 2), [IO.Compression.CompressionMode]::Decompress)
  $o = [IO.MemoryStream]::new(); $z.CopyTo($o); $b = $o.ToArray()
  $bw = [int][Math]::Ceiling($png.Width / 16); $bh = [int][Math]::Ceiling($png.Height / 16)
  if ($b.Length -lt 2 * $bw * $bh) { throw "format 1537: $($b.Length) bytes for $($png.Width)x$($png.Height)" }
  $bmp = [Drawing.Bitmap]::new([int]$png.Width, [int]$png.Height, [Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [Drawing.Graphics]::FromImage($bmp)
  for ($y = 0; $y -lt $bh; $y++) { for ($x = 0; $x -lt $bw; $x++) {
    $v = $b[2 * ($y * $bw + $x)] -bor ($b[2 * ($y * $bw + $x) + 1] -shl 8)
    $r5 = ($v -shr 11) -band 31; $g6 = ($v -shr 5) -band 63; $b5 = $v -band 31
    $col = [Drawing.Color]::FromArgb(255, ($r5 -shl 3) -bor ($r5 -shr 2), ($g6 -shl 2) -bor ($g6 -shr 4), ($b5 -shl 3) -bor ($b5 -shr 2))
    $br = [Drawing.SolidBrush]::new($col); $g.FillRectangle($br, 16 * $x, 16 * $y, 16, 16); $br.Dispose()
  } }
  $g.Dispose()
  $bmp
}

# A canvas' own pixels, following _inlink (same image) and _outlink (a _Canvas file) links
function Get-Bitmap($c, $img) {
  for ($hop = 0; $hop -lt 8; $hop++) {
    $in = $c.GetProperty('_inlink'); $out = $c.GetProperty('_outlink')
    if ($in) { $c = $img.GetFromPath($in.Value) }
    elseif ($out) { $c = Get-OutlinkTarget $out.Value }
    else { $b = $c.GetBitmap(); if (-not $b) { $b = Get-BlockBitmap $c }; return $b }
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

# map objects + tiles (what's drawn in front of mobs: the cover masks, perception/cover.py)
#   Map\Obj\<set>.img.xml + Map\Obj\png\<set>\<l0>\<l1>\<l2>\<n>.png   (origin / z / delay in the xml)
#   Map\Tile\<set>.img.xml + Map\Tile\png\<set>\<u>\<no>.png
function Export-Canvases($prop, $img, [string]$base) {
  foreach ($c in $prop.WzProperties) {
    if ($c.Name -match '[\/:*?"<>|]') { continue }            # not a file name (a clock font's ':'), never scenery
    if ($c -is [MapleLib.WzLib.WzProperties.WzCanvasProperty]) {
      try { Save-Png (Get-Bitmap $c $img) "$base\$($c.Name).png"; $script:nPart++ }
      catch { $fails.Add("$($img.Name) $base/$($c.Name): $_") }
    } elseif ($c -is [MapleLib.WzLib.WzProperties.WzSubProperty]) {
      Export-Canvases $c $img "$base\$($c.Name.Trim())"        # 'emphasis ' (AntiMacro): Windows drops the space
    }
  }
}
# every image of the .wz files matching $glob: its xml + every canvas in it, links resolved. $only: image names.
function Export-Sets([string]$glob, [string]$dest, [string[]]$only = $null) {
  $script:nPart = 0; $nSet = 0
  foreach ($w in Get-ChildItem (Split-Path $glob) -Filter (Split-Path $glob -Leaf)) {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      if ($only -and $img.Name -notin $only) { continue }
      Save-Xml $img "$dest\$($img.Name).xml"; $nSet++
      Export-Canvases $img $img "$dest\png\$($img.Name -replace '\.img$', '')"
      $img.UnparseImage()
    }
  }
  "$(Split-Path $dest -Leaf): $nSet sets ($script:nPart pictures)"
}
#   Map\Back\<set>.img.xml + Map\Back\png\<set>\back\<no>.png, ani\<no>\<n>.png: the backgrounds (the scene model,
#   PLAN-perception.md step 1: tiles + objects + backs = what the frame shows where nothing moves)
foreach ($kind in 'Obj', 'Tile', 'Back') { Export-Sets "$D\Map\$kind\$($kind)_*.wz" "$Out\Map\$kind" }

# for the scene model's later steps (PLAN-perception.md step 5: occluders, effects):
#   Npc\<id>.img.xml + Npc\png\<id>\<anim>\<n>.png, Pet\<id>.img.xml + Pet\png\..., Effect\BasicEff.img.xml + png
foreach ($sub in 'Npc', 'Pet', 'Effect') { if (Test-Path "$Out\$sub") { Remove-Item -Recurse -Force "$Out\$sub" } }
Export-Sets "$D\Npc\Npc_*.wz" "$Out\Npc"
Export-Sets "$D\Item\Pet\Pet_*.wz" "$Out\Pet"
Export-Sets "$D\Effect\Effect_*.wz" "$Out\Effect" @('BasicEff.img')

# the Lie Detector's windows (PLAN-perception.md step 2.8: native title templates, perception/liedetector.py)
#   UI\AntiMacro.img.xml + UI\png\AntiMacro\..., UI\LieDetector.img.xml + UI\png\LieDetector\...
if (Test-Path "$Out\UI") { Remove-Item -Recurse -Force "$Out\UI" }
Export-Sets "$D\UI\UI_*.wz" "$Out\UI" @('AntiMacro.img', 'LieDetector.img')

# what a DROP shows (PLAN-loot.md S1): the picture the client draws for an item lying on the ground = info/iconRaw,
# 1:1 and opaque (info/icon = the same + a shadow, drawn in windows only: not exported)
#   Item\png\<8-digit id>_raw.png      every Etc / Consume / Install item + every equip (Character\<slot>\<id>.img)
#   Item\png\0900000<n>_raw_<f>.png    the meso pictures (Item\Special\0900.img: 4 sizes x 4 frames)
#   Item\items.json  id -> {kind, name, raw: [w, h, ox, oy], link: the item whose picture it borrows} (mesos: frames
#                    [[w, h, ox, oy, delay]..], delay 0 = none in the file); names from String Etc / Consume / Ins / Eqp
# 257 items' iconRaw is a UOL (WzUOLProperty) to another item's (scroll families): followed to the target canvas.
if (Test-Path "$Out\Item") { Remove-Item -Recurse -Force "$Out\Item" }
New-Item -ItemType Directory -Force "$Out\Item\png" | Out-Null
$names = @{}
$sf = Open-Bms "$D\String\String_000.wz"
foreach ($name in 'Consume.img', 'Ins.img') {
  foreach ($p in ($sf.WzDirectory.WzImages | ? Name -eq $name).WzProperties) {
    $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } }
foreach ($grp in ($sf.WzDirectory.WzImages | ? Name -eq 'Etc.img').WzProperties) {
  foreach ($p in $grp.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } }
foreach ($top in ($sf.WzDirectory.WzImages | ? Name -eq 'Eqp.img').WzProperties) {
  foreach ($slot in $top.WzProperties) {
    foreach ($p in $slot.WzProperties) { $n = $p.GetFromPath('name'); if ($n) { $names[[int]$p.Name] = "$($n.Value)" } } } }
$items = [ordered]@{}
$nLink = 0; $nNoRaw = 0
# one iconRaw -> its png + [w, h, ox, oy]; a UOL is followed to the canvas it names (its origin comes with it)
function Add-Raw([string]$kind, [string]$id, $info, $img) {
  $c = $info.GetFromPath('iconRaw')
  if (-not $c) { $script:nNoRaw++; return }
  $e = [ordered]@{ kind = $kind; name = $names[[int]$id] }
  $uol = ''
  for ($hop = 0; $c -is [MapleLib.WzLib.WzProperties.WzUOLProperty] -and $hop -lt 8; $hop++) {
    $uol = "$($c.Value)"; $par = $c.Parent; $c = $c.LinkValue
    if (-not $c) { $c = $par.GetFromPath($uol) }               # 'icon' (a sibling): LinkValue gives null
    if ($c -and $c.Parent -and $c.Parent.Parent) { $e['link'] = ($c.Parent.Parent.Name -replace '\.img$', '') }
  }
  if ($c -isnot [MapleLib.WzLib.WzProperties.WzCanvasProperty]) { $fails.Add("item $kind $id : iconRaw -> '$uol' not a canvas"); return }
  if ($e.Contains('link')) { $script:nLink++ }
  try {
    $bmp = Get-Bitmap $c $img
    $o = $c.GetProperty('origin')
    $e['raw'] = @([int]$bmp.Width, [int]$bmp.Height, [int]$o.X.Value, [int]$o.Y.Value)
    Save-Png $bmp "$Out\Item\png\$($id)_raw.png"
    $items[$id] = $e
  } catch {                       # a link to a canvas the client doesn't have (01702302, a nameless cash weapon:
    if ("$_" -like 'broken link*') { $script:skipped.Add("$kind $id") }      # iconRaw -> info/icon, no icon)
    else { $fails.Add("item $kind $id : $_") }
  }
}
$skipped = [Collections.Generic.List[string]]::new()
foreach ($kind in 'Etc', 'Consume', 'Install') {             # <kind>\<4-digit>.img\<8-digit id>\info\iconRaw
  $n0 = $items.Count
  foreach ($w in Get-ChildItem "$D\Item\$kind" -Filter "$($kind)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      foreach ($it in $img.WzProperties) { $info = $it.GetFromPath('info'); if ($info) { Add-Raw $kind $it.Name $info $img } }
      $img.UnparseImage()
    }
  }
  "items $kind : $($items.Count - $n0)"
}
$sp = (Open-Bms "$D\Item\Special\Special_000.wz").WzDirectory.WzImages | ? Name -eq '0900.img'
foreach ($it in $sp.WzProperties) {                          # mesos: 0900.img\0900000<n>\iconRaw\<f>
  if ($it.Name -notin '09000000', '09000001', '09000002', '09000003') { continue }   # the 4 sizes; 09000004-7 = a
  $raw = $it.GetFromPath('iconRaw')                          # face coin, red glowing coins, a bronze copy: not mesos
  if (-not $raw) { continue }
  $fr = @()
  foreach ($c in $raw.WzProperties) {
    if ($c -isnot [MapleLib.WzLib.WzProperties.WzCanvasProperty]) { continue }
    try {
      $bmp = Get-Bitmap $c $sp
      $o = $c.GetProperty('origin'); $dl = $c.GetProperty('delay')
      $fr += , @([int]$bmp.Width, [int]$bmp.Height, [int]$o.X.Value, [int]$o.Y.Value, $(if ($dl) { [int]$dl.Value } else { 0 }))
      Save-Png $bmp "$Out\Item\png\$($it.Name)_raw_$($c.Name).png"
    } catch { $fails.Add("meso $($it.Name) $($c.Name): $_") }
  }
  if ($fr.Count) { $items[$it.Name] = [ordered]@{ kind = 'Meso'; name = $null; frames = $fr } }
}
foreach ($slot in 'Accessory', 'Cap', 'Cape', 'Coat', 'Glove', 'Longcoat', 'Pants', 'Ring', 'Shield', 'Shoes', 'Weapon') {
  $n0 = $items.Count                                         # equips: Character\<slot>\<8-digit id>.img\info\iconRaw
  foreach ($w in Get-ChildItem "$D\Character\$slot" -Filter "$($slot)_*.wz") {
    foreach ($img in (Open-Bms $w.FullName).WzDirectory.WzImages) {
      $info = $img.GetFromPath('info')
      if ($info) { Add-Raw $slot ($img.Name -replace '\.img$', '') $info $img }
      $img.UnparseImage()
    }
  }
  "items $slot : $($items.Count - $n0)"
}
$items | ConvertTo-Json -Depth 6 -Compress | Set-Content -Encoding utf8 "$Out\Item\items.json"
"items: $($items.Count) ($nLink by a link, $nNoRaw without iconRaw; skipped, iconRaw links to a canvas the client " +
  "lacks: $($skipped.Count) $($skipped -join ', '))"

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

# attack boxes (brain-v2 reach): Character\Afterimage (per weapon type: lt/rb per attack stance) + the 1st-job skills
foreach ($sub in 'Afterimage', 'Skill') { if (Test-Path "$Out\$sub") { Remove-Item -Recurse -Force "$Out\$sub" } }
foreach ($i in (Open-Bms "$D\Character\Afterimage\Afterimage_000.wz").WzDirectory.WzImages) { Save-Xml $i "$Out\Afterimage\$($i.Name).xml" }
foreach ($i in (Open-Ms "$D\Packs\Skill_00000.ms").WzDirectory.WzImages | ? Name -in '000.img', '100.img', '200.img', '300.img', '400.img') {
  Save-Xml $i "$Out\Skill\$($i.Name).xml" }
"attack boxes: $((Get-ChildItem "$Out\Afterimage").Count) weapon types"

# swing lengths (brain-v2 weapon): the body's attack stance frame delays + every weapon's afterImage type and attackSpeed
foreach ($sub in 'Character') { if (Test-Path "$Out\$sub") { Remove-Item -Recurse -Force "$Out\$sub" } }
foreach ($i in (Open-Bms "$D\Character\Character_000.wz").WzDirectory.WzImages | ? Name -eq '00002000.img') {
  Save-Xml $i "$Out\Character\$($i.Name).xml" }
$weapons = [ordered]@{}
foreach ($w in Get-ChildItem "$D\Character\Weapon" -Filter 'Weapon_*.wz') {
  foreach ($i in (Open-Bms $w.FullName).WzDirectory.WzImages) {
    $t = $i.GetFromPath('info/afterImage'); $s = $i.GetFromPath('info/attackSpeed')
    if ($t -and $s) { $weapons[$i.Name.Split('.')[0]] = @{ afterImage = "$($t.Value)"; attackSpeed = [int]"$($s.Value)" } }
  }
}
$weapons | ConvertTo-Json | Set-Content -Encoding utf8 "$Out\Character\weapons.json"
"swing data: body stances + $($weapons.Count) weapons"

# names
foreach ($s in Get-ChildItem "$D\String" -Filter '*_000.wz' -Recurse) {
  foreach ($i in (Open-Bms $s.FullName).WzDirectory.WzImages | ? Name -in 'Mob.img', 'Map.img') { Save-Xml $i "$Out\String\$($i.Name).xml" }
}

"failed: $($fails.Count)"; $fails | % { "  $_" }
"done in $([int]((Get-Date) - $t0).TotalSeconds) s -> $Out"
if ($fails.Count) { exit 1 }
