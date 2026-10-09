$ErrorActionPreference = 'SilentlyContinue'
$url = 'http://127.0.0.1:8000/?sort=date_desc'
$html = curl -s $url
$urls = [System.Collections.Generic.List[string]]::new()
foreach ($m in [regex]::Matches($html, 'src="(/media/[^"]+)"')) { $urls.Add($m.Groups[1].Value) }
Write-Host "unique media urls on listing page: $($urls.Count)"

for ($round = 0; $round -lt 4; $round++) {
  $codes = @()
  foreach ($u in $urls) {
    $full = "http://127.0.0.1:8000$u"
    $c = (curl -s -o nul -w '%{http_code}' $full)
    $codes += $c
  }
  $g = $codes | Group-Object -NoElement
  $summary = ($g | ForEach-Object { "$($_.Count) x HTTP $($_.Name)" }) -join ', '
  Write-Host "round $($round+1) ($($urls.Count) requests): $summary"
}
