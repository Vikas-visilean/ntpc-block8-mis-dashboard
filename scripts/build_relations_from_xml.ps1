# Build <project>_relations.json from an MS Project XML (MSPDI) export.
# Same contract and rules as scripts/build_relations_from_mpp.py (which needs mpxj/Java):
#   [predecessorUid, successorUid, type, lagDays]; links off a summary task are expanded
#   to the leaves beneath it; duplicates dropped. MSP Unique ID == VisiLean externalId.
param([string]$Xml, [string]$Out, [string]$Tasks = "")
$ErrorActionPreference = "Stop"
$doc = New-Object System.Xml.XmlDocument
$doc.Load($Xml)
function Txt($el, $tag) { $c = $el.Item($tag); if ($null -eq $c) { return $null } else { return $c.InnerText } }
$mpd = Txt $doc.DocumentElement "MinutesPerDay"; $minPerDay = if ($mpd) { [double]$mpd } else { 480.0 }
$TYPE = @{ "0"="FF"; "1"="FS"; "2"="SF"; "3"="SS" }

$list = $doc.GetElementsByTagName("Task")
$name = @{}; $summary = @{}; $outline = @{}; $byOutline = @{}
$rels = New-Object System.Collections.Generic.List[object]
for ($i = 0; $i -lt $list.Count; $i++) {
  $t = $list.Item($i)
  $u = Txt $t "UID"; if ($null -eq $u -or $u -eq "") { continue }
  $uid = [int]$u
  $name[$uid] = [string](Txt $t "Name")
  if ((Txt $t "Summary") -eq "1") { $summary[$uid] = $true }
  $on = Txt $t "OutlineNumber"; if ($on) { $outline[$uid] = $on; $byOutline[$on] = $uid }
  $links = $t.GetElementsByTagName("PredecessorLink")
  for ($j = 0; $j -lt $links.Count; $j++) {
    $pl = $links.Item($j)
    $pu = [int](Txt $pl "PredecessorUID")
    $ty = $TYPE[[string](Txt $pl "Type")]; if (-not $ty) { $ty = "FS" }
    $lagTxt = Txt $pl "LinkLag"; $lag = 0.0
    if ($lagTxt) { $lag = [math]::Round(([double]$lagTxt) / (10.0 * $minPerDay), 2) }   # tenths of minutes -> days
    $rels.Add(@($pu, $uid, $ty, $lag))
  }
}
Write-Host ("tasks: {0} ({1} summary) | links: {2}" -f $name.Count, $summary.Count, $rels.Count)

# parent from OutlineNumber prefix ("1.2.3" -> "1.2")
$child = @{}
foreach ($kv in $outline.GetEnumerator()) {
  $o = $kv.Value; $k = $o.LastIndexOf(".")
  if ($k -gt 0) { $par = $byOutline[$o.Substring(0, $k)]
    if ($null -ne $par) { if (-not $child.ContainsKey($par)) { $child[$par] = New-Object System.Collections.Generic.List[int] }; $child[$par].Add($kv.Key) } }
}
$script:leafmemo = @{}; $script:child = $child
function Leaves([int]$u) {
  if ($script:leafmemo.ContainsKey($u)) { return $script:leafmemo[$u] }
  $script:leafmemo[$u] = @($u)                       # cycle guard
  if ($script:child.ContainsKey($u)) { $out = @(); foreach ($c in $script:child[$u]) { $out += Leaves $c } } else { $out = @($u) }
  $script:leafmemo[$u] = $out; return $out
}
$seen = @{}; $expanded = New-Object System.Collections.Generic.List[string]
foreach ($r in $rels) {
  $pu = $r[0]; $su = $r[1]; $code = $r[2]; $lag = $r[3]
  $A = if ($summary.ContainsKey($pu)) { Leaves $pu } else { @($pu) }
  $B = if ($summary.ContainsKey($su)) { Leaves $su } else { @($su) }
  foreach ($a in $A) { foreach ($b in $B) {
    if ($a -eq $b) { continue }
    $key = "$a|$b|$code|$lag"; if ($seen.ContainsKey($key)) { continue }; $seen[$key] = 1
    $expanded.Add(('[{0},{1},"{2}",{3}]' -f $a, $b, $code, $lag.ToString([Globalization.CultureInfo]::InvariantCulture)))
  } }
}
Write-Host ("links after expanding summary endpoints: {0}" -f $expanded.Count)
[IO.File]::WriteAllText($Out, "[" + ($expanded -join ",") + "]")
Write-Host ("-> {0} ({1} bytes)" -f $Out, (Get-Item $Out).Length)

if ($Tasks -and (Test-Path $Tasks)) {
  $vl = Get-Content $Tasks -Raw | ConvertFrom-Json
  $leafExt = @{}; $nLeaves = 0
  foreach ($x in $vl) { if (-not $x.parent) { $nLeaves++; if ("$($x.externalId)" -ne "") { $leafExt[[int]$x.externalId] = 1 } } }
  $inXml = 0; foreach ($e in $leafExt.Keys) { if ($name.ContainsKey($e)) { $inXml++ } }
  $both = 0; $touch = @{}
  foreach ($s in $expanded) { $m = [regex]::Match($s, '^\[(\d+),(\d+),'); $a = [int]$m.Groups[1].Value; $b = [int]$m.Groups[2].Value
    if ($leafExt.ContainsKey($a) -and $leafExt.ContainsKey($b)) { $both++; $touch[$a] = 1; $touch[$b] = 1 } }
  Write-Host ("VisiLean leaves: {0} | with externalId: {1} | found in XML: {2}" -f $nLeaves, $leafExt.Count, $inXml)
  Write-Host ("links with both ends on the dashboard: {0} | leaves in the logic network: {1} ({2}%)" -f $both, $touch.Count, [math]::Round(100.0 * $touch.Count / [math]::Max(1, $leafExt.Count), 1))
  $mism = 0; $n = 0; $ex = @()
  foreach ($x in $vl) { if (-not $x.parent -and "$($x.externalId)" -ne "") { $e = [int]$x.externalId; if ($name.ContainsKey($e)) { $n++; if ($name[$e].Trim() -ne ([string]$x.taskName).Trim()) { $mism++; if ($ex.Count -lt 3) { $ex += ("{0}: xml='{1}' vl='{2}'" -f $e, $name[$e], $x.taskName) } } } } }
  Write-Host ("name check on shared ids: {0} compared, {1} differ" -f $n, $mism); $ex | ForEach-Object { Write-Host ("   e.g. " + $_) }
}
