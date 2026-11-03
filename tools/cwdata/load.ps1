$L = 'C:\Users\Yoav\dev\harepacker-11.1.0\lib'
$D = 'C:\Users\Yoav\dev\cw-data\Data'
Add-Type -TypeDefinition @'
using System; using System.IO; using System.Reflection;
public static class Resolver { public static void Init(string lib) {
  AppDomain.CurrentDomain.AssemblyResolve += (s, e) => { var f = Path.Combine(lib, new AssemblyName(e.Name).Name + ".dll"); return File.Exists(f) ? Assembly.LoadFrom(f) : null; }; } }
'@
[Resolver]::Init($L)
$null = [Reflection.Assembly]::LoadFrom("$L\MapleLib.dll")
function Open-Wz($path) {
  foreach ($v in 'GMS','EMS','BMS','CLASSIC') {
    try { $f = [MapleLib.WzLib.WzFile]::new($path, [MapleLib.WzLib.WzMapleVersion]$v); $st = $f.ParseWzFile($null)
      $n = $f.WzDirectory.WzImages.Count + $f.WzDirectory.WzDirectories.Count
      [Console]::Error.WriteLine("$(Split-Path $path -Leaf) $v -> $st ($n items)")
      if ("$st" -eq 'Success' -and $n -gt 0) { return $f } } catch { [Console]::Error.WriteLine("$v : $_") } }
}
function Open-Ms($path) {
  $fs = [IO.File]::OpenRead($path)
  $ms = [MapleLib.WzLib.MSFile.WzMsFile]::new($fs, (Split-Path $path -Leaf), $path, $true, $false)
  $ms.ReadEntries(); [Console]::Error.WriteLine("$(Split-Path $path -Leaf): $($ms.Entries.Count) entries")
  $ms.LoadAsWzFile()
}
function List-Dir($d, $depth) {
  foreach ($s in $d.WzDirectories) { "$($s.FullPath)/"; if ($depth -gt 0) { List-Dir $s ($depth - 1) } }
  foreach ($i in $d.WzImages) { $i.FullPath }
}
function Save-Xml($img, $out) {
  New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
  [MapleLib.WzLib.Serializer.WzClassicXmlSerializer]::new(1, [MapleLib.WzLib.Serializer.LineBreak]::Unix, $false).SerializeImage($img, $out)
}
