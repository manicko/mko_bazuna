<#
.SYNOPSIS
    Verification gate for the dev nginx `/media/` rate-limit configuration.

.DESCRIPTION
    A read-only PowerShell 7+ gate. It never remediates and never brings the
    nginx container up: starting nginx is an operator action (the dev stack
    gates the service behind the `use-nginx` compose profile).

    The gate does two things:

      1. Static parse (always runs, read-only) of `docker/nginx/nginx.dev.conf`:
         the `limit_req_zone` census (count and names), the `location /media/`
         block's `limit_req` directive verbatim, the `limit_req_status` value,
         and a qualitative warning when the file mixes bare-LF lines with CRLF.
         No line counts are ever pinned: a count assertion drifts on the next
         conf edit. The qualitative CRLF hazard is carried instead because CRLF
         silently no-ops `$`-anchored regexes in this and adjacent tooling.

      2. Container-state detection and, only when the nginx container of the
         dev compose project is *already running*, live burst and settle probes
         against the TLS endpoint with the dev certificate.

    Read-only guarantee: this script edits no nginx conf, compose file, `.env`,
    or database row. The container-state detection is scoped to the
    `mko-bazuna-dev` compose project; an unscoped `docker ps` would pick up
    unrelated containers from other projects and is deliberately avoided.

.IMPORTANT: 429 AMBIGUITY ON THE DEV STACK
    `/media/` is limited twice: nginx's `limit_req zone=browse_limit burst=40
    nodelay` in `docker/nginx/nginx.dev.conf`, and the application-level
    `RateLimitBudget.MEDIA_GATE` limiter (60 requests / 60 s) in
    `apps/ads/views/listings.py::media_gate`. Both return HTTP 429, so a bare
    429 is ambiguous. The burst probe therefore sends `NGINX_BURST + 5`
    requests (default 45) and keeps the total *strictly* below the application
    window (60), so any 429 it observes is attributable to nginx's `burst=40`
    rejection and not to the application limiter. Do not raise `NGINX_BURST` to
    or above 60 or the probe loses its attribution.

.EXIT CODES (distinct per outcome; the gate reports, a human decides)
    0   PASS       - container running; static parse consistent; both probes
                     behaved as documented.
    1   CONFIG     - the static parse failed, or the `/media/` block or the
                     4-zone census is not as documented. Conf invalid.
    2   STOPPED    - the nginx container exists in the dev project but is not
                     running (exited/stopped/created). Its stopped exit code is
                     reported. Distinct from ABSENT and CONFIG.
    3   ABSENT     - no nginx container exists in the dev project. Distinct
                     from STOPPED and CONFIG.
    4   PROBE FAIL - container running, static parse consistent, but a live
                     probe did not behave as documented (the limit is not
                     enforcing, or a probe could not be attributed).

.PARAMETER Conf
    Path to the dev nginx configuration to parse. Default:
    docker/nginx/nginx.dev.conf (relative to the repository root, inferred
    from this script's location).

.PARAMETER Url
    Base URL of the TLS endpoint. Default: https://localhost. The dev
    certificate is self-signed, so curl.exe is invoked with `-k`.

.PARAMETER Help
    Print this help and exit 0.

.ENVIRONMENT
    NGINX_BURST          Concurrent `/media/` requests used by the burst probe.
                         Default: 45 (documented burst is 40; the extra 5 must
                         overshoot it while the total stays under the
                         application window of 60).
    NGINX_SETTLE         Seconds to wait for the nginx leaky bucket to drain
                         before the settle probe. Default: 15.
    NGINX_POLL_ATTEMPTS  Readiness poll attempts before giving up. Default: 15.
    NGINX_POLL_INTERVAL  Seconds between readiness poll attempts. Default: 1.
    Each override uses the project idiom
    `$x = if ($env:X) { $env:X } else { "default" }` (same shape as
    Makefile.ps1::Invoke-Profile) and its effective value is printed.

.EXAMPLE
    pwsh -File scripts/verify-nginx-media-limits.ps1
    pwsh -File scripts/verify-nginx-media-limits.ps1 -Conf docker/nginx/nginx.dev.conf

.NOTES
    The gate is safe to run while the container is down: it reports and exits
    non-zero without attempting recovery. It never runs `docker compose up`,
    `start`, or `run`.
#>

[CmdletBinding()]
param(
    [string]$Conf = "",
    [string]$Url = "https://localhost",
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Exit-code contract (see the help block above).
$ExitPass = 0
$ExitConfig = 1
$ExitStopped = 2
$ExitAbsent = 3
$ExitProbeFail = 4

# Compose project that owns the dev nginx container. Every docker call below is
# scoped to it so unrelated projects' containers are never observed.
$DevProject = "mko-bazuna-dev"

if ($Help) {
    Get-Help -Full $PSCommandPath
    exit $ExitPass
}

# ---------------------------------------------------------------------------
# Environment overrides (project idiom: Makefile.ps1::Invoke-Profile).
# ---------------------------------------------------------------------------
$BurstRaw = if ($env:NGINX_BURST) { $env:NGINX_BURST } else { "45" }
$SettleRaw = if ($env:NGINX_SETTLE) { $env:NGINX_SETTLE } else { "15" }
$PollAttemptsRaw = if ($env:NGINX_POLL_ATTEMPTS) { $env:NGINX_POLL_ATTEMPTS } else { "15" }
$PollIntervalRaw = if ($env:NGINX_POLL_INTERVAL) { $env:NGINX_POLL_INTERVAL } else { "1" }

function ConvertTo-PositiveInt {
    param(
        [string]$Value,
        [string]$Name,
        [int]$Minimum
    )
    $parsed = 0
    if (-not [int]::TryParse($Value, [ref]$parsed) -or $parsed -lt $Minimum) {
        Write-Host "[CONFIG] $Name must be an integer >= $Minimum; got '$Value'."
        exit $ExitConfig
    }
    return $parsed
}

$Burst = ConvertTo-PositiveInt -Value $BurstRaw -Name "NGINX_BURST" -Minimum 1
$Settle = ConvertTo-PositiveInt -Value $SettleRaw -Name "NGINX_SETTLE" -Minimum 0
$PollAttempts = ConvertTo-PositiveInt -Value $PollAttemptsRaw -Name "NGINX_POLL_ATTEMPTS" -Minimum 1
$PollInterval = ConvertTo-PositiveInt -Value $PollIntervalRaw -Name "NGINX_POLL_INTERVAL" -Minimum 1

# ---------------------------------------------------------------------------
# Paths.
# ---------------------------------------------------------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Conf)) {
    $ConfPath = Join-Path $RepoRoot "docker/nginx/nginx.dev.conf"
} elseif ([System.IO.Path]::IsPathRooted($Conf)) {
    $ConfPath = $Conf
} else {
    $ConfPath = Join-Path $RepoRoot $Conf
}
$CertsDir = Join-Path $RepoRoot "docker/nginx/certs"

Write-Host "============================================================"
Write-Host " dev nginx /media/ rate-limit verification gate"
Write-Host "============================================================"
Write-Host "conf        : $ConfPath"
Write-Host "url         : $Url"
Write-Host "project     : $DevProject"
Write-Host "NGINX_BURST         effective = $Burst  (default 45)"
Write-Host "NGINX_SETTLE        effective = $Settle  (default 15)"
Write-Host "NGINX_POLL_ATTEMPTS effective = $PollAttempts  (default 15)"
Write-Host "NGINX_POLL_INTERVAL effective = $PollInterval  (default 1)"
Write-Host ""

# ---------------------------------------------------------------------------
# Static parse (always runs, read-only).
# ---------------------------------------------------------------------------
Write-Host "--- Static parse ---"

if (-not (Test-Path -LiteralPath $ConfPath -PathType Leaf)) {
    Write-Host "[CONFIG] conf file not found: $ConfPath"
    exit $ExitConfig
}

try {
    $confText = [System.IO.File]::ReadAllText($ConfPath)
} catch {
    Write-Host "[CONFIG] conf file is unreadable: $ConfPath"
    Write-Host "         $($_.Exception.Message)"
    exit $ExitConfig
}

$lines = $confText -split "`n"

# limit_req_zone census. Mirrors tests/test_nginx_config.py::_limit_req_zones:
# `limit_req_zone <key> zone=<name>:...`. The census is load-bearing: it is the
# `len(zones) == 4` positive equality that fails if a zone is added, deleted, or
# renamed.
$zoneNames = @()
foreach ($line in $lines) {
    $m = [regex]::Match($line, "limit_req_zone\s+\S+\s+zone=([A-Za-z0-9_]+):")
    if ($m.Success) {
        $zoneNames += $m.Groups[1].Value
    }
}

# The `/media/` prefix location block. `_iter_location_blocks` in the test suite
# uses an anchored `re.match(r"\s*location\b", line)`, so a `#` comment can never
# match a block header. `/media/` shadows nothing: it is a prefix location, not an
# anchor. The genuinely shadowable anchors in this conf are `= /metrics` (4
# sites), `/protected-media/` (1), and `location /health/ {` (1), because a prefix
# such as `/media/` can precede them in some regex matchers. This gate is
# read-only regardless, but the correct mechanism is stated here rather than the
# rolled-back "`/media/` shadows a block" claim.
$mediaBlockLines = @()
$inMedia = $false
$braceDepth = 0
foreach ($line in $lines) {
    if (-not $inMedia) {
        if ($line -match '^\s*location\s+(?:[~*^=]*\s*)?/media/\s*\{') {
            $inMedia = $true
            $braceDepth = 1
            $mediaBlockLines += $line
            continue
        }
    } else {
        $mediaBlockLines += $line
        foreach ($ch in $line.ToCharArray()) {
            if ($ch -eq '{') { $braceDepth++ }
            elseif ($ch -eq '}') { $braceDepth-- }
        }
        if ($braceDepth -le 0) { break }
    }
}

$mediaBlockText = $mediaBlockLines -join "`n"
$mediaLimitReq = ""
$mediaLimitMatch = [regex]::Match($mediaBlockText, "limit_req\s+[^;]+;")
if ($mediaLimitMatch.Success) {
    $mediaLimitReq = $mediaLimitMatch.Value.Trim()
}

# limit_req_status at http{} scope.
$limitReqStatus = ""
$statusMatch = [regex]::Match($confText, "limit_req_status\s+[^;]+;")
if ($statusMatch.Success) {
    $limitReqStatus = $statusMatch.Value.Trim()
}

Write-Host "limit_req_zone census : $($zoneNames.Count) zone(s)"
foreach ($zone in $zoneNames) {
    Write-Host "  - $zone"
}
if ($mediaLimitReq) {
    Write-Host "location /media/      : $mediaLimitReq"
} else {
    Write-Host "location /media/      : <not found>"
}
if ($limitReqStatus) {
    Write-Host "limit_req_status      : $limitReqStatus"
} else {
    Write-Host "limit_req_status      : <not found>"
}

# Qualititative CRLF hazard. Counts are deliberately never printed or asserted:
# they drift on the next conf edit. The hazard is that a file mixing CRLF with
# bare LF makes `$`-anchored regexes no-op on the bare-LF lines.
$hasCrlf = $confText.Contains("`r`n")
$hasBareLf = [regex]::IsMatch($confText, "(?<!\r)\n")
if ($hasCrlf -and $hasBareLf) {
    Write-Host "line endings          : WARNING - file mixes bare-LF lines with CRLF."
    Write-Host "                        CRLF can silently no-op `$`-anchored regexes on"
    Write-Host "                        the bare-LF lines in this and adjacent tooling."
} elseif ($hasCrlf) {
    Write-Host "line endings          : CRLF throughout (no bare-LF hazard observed)."
} else {
    Write-Host "line endings          : LF only."
}

# Validate the documented shape. Failure here is outcome CONFIG (exit 1).
$configErrors = @()
if ($zoneNames.Count -ne 4) {
    $configErrors += "expected exactly 4 limit_req zones, found $($zoneNames.Count): $($zoneNames -join ', ')"
}
if (-not ($zoneNames -contains "browse_limit")) {
    $configErrors += "browse_limit zone is not declared"
}
if (-not $mediaBlockLines) {
    $configErrors += "location /media/ block not found"
}
if ($mediaLimitReq -notmatch "zone=browse_limit") {
    $configErrors += "location /media/ does not carry 'limit_req zone=browse_limit'"
}
if ($mediaLimitReq -notmatch "burst=40") {
    $configErrors += "location /media/ does not carry the documented 'burst=40'"
}
if ($mediaLimitReq -notmatch "nodelay") {
    $configErrors += "location /media/ limit_req does not use 'nodelay'"
}
if ($limitReqStatus -notmatch "429") {
    $configErrors += "limit_req_status is not 429"
}
if ($configErrors.Count -gt 0) {
    Write-Host ""
    Write-Host "[CONFIG] dev nginx /media/ configuration is not as documented:"
    foreach ($e in $configErrors) {
        Write-Host "  - $e"
    }
    Write-Host "[CONFIG] exit=$ExitConfig (conf invalid). No remediation attempted."
    exit $ExitConfig
}
Write-Host "[PASS] static parse consistent with documentation."

# ---------------------------------------------------------------------------
# Container-state detection (scoped to the dev compose project).
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- Container state ---"

$psOutput = & docker ps -a --filter "label=com.docker.compose.project=$DevProject" --filter "label=com.docker.compose.service=nginx" --format "{{.Names}}|{{.State}}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[CONFIG] could not query docker for project '$DevProject' (is docker running?)."
    exit $ExitConfig
}

$containerName = ""
$containerState = ""
if ($psOutput) {
    $firstLine = @($psOutput)[0]
    $parts = $firstLine -split "\|"
    $containerName = $parts[0]
    if ($parts.Count -gt 1) { $containerState = $parts[1] }
}

if ([string]::IsNullOrWhiteSpace($containerName)) {
    Write-Host "[ABSENT] no nginx container exists in project '$DevProject'."
    Write-Host "[ABSENT] exit=$ExitAbsent. Nothing to probe; a human decides."
    exit $ExitAbsent
}

Write-Host "container : $containerName"
Write-Host "state     : $containerState"

$runningStates = @("running")
if ($runningStates -notcontains $containerState) {
    $inspect = & docker inspect $containerName --format "{{.State.ExitCode}}" 2>$null
    $stoppedExit = if ($inspect) { (@($inspect)[0]).Trim() } else { "unknown" }
    Write-Host "[STOPPED] container '$containerName' is present but not running (state=$containerState)."
    Write-Host "[STOPPED] stopped exit code: $stoppedExit"
    Write-Host "[STOPPED] exit=$ExitStopped. The gate does not start the container;"
    Write-Host "[STOPPED] bringing nginx up is an operator action ('use-nginx' profile)."
    exit $ExitStopped
}

# ---------------------------------------------------------------------------
# Live probes (only when the container is already running).
# ---------------------------------------------------------------------------
Write-Host "[RUNNING] container '$containerName' is up; proceeding to live probes."

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    Write-Host "[PROBE FAIL] curl.exe not found on PATH; cannot run live probes."
    exit $ExitProbeFail
}
$certPath = Join-Path $CertsDir "fullchain.pem"
if (-not (Test-Path -LiteralPath $certPath -PathType Leaf)) {
    Write-Host "[PROBE FAIL] dev certificate not found: $certPath"
    exit $ExitProbeFail
}

# Concrete posted media key so the request reaches nginx's limit_req before any
# Django routing decision. The limit is keyed on $binary_remote_addr, so the
# path need not resolve; the probe measures refusal, not payload delivery.
$mediaPath = "$Url/media/seed/verify-nginx-media-limits-gate.jpg"

function Test-EndpointReady {
    for ($i = 1; $i -le $PollAttempts; $i++) {
        & curl.exe -k -s -o NUL -m 3 -w "%{http_code}" $mediaPath *> $null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
        Start-Sleep -Seconds $PollInterval
    }
    return $false
}

Write-Host ""
Write-Host "--- Readiness ---"
if (-not (Test-EndpointReady)) {
    Write-Host "[PROBE FAIL] endpoint not reachable after $PollAttempts attempt(s) at ${PollInterval}s."
    Write-Host "[PROBE FAIL] exit=$ExitProbeFail."
    exit $ExitProbeFail
}
Write-Host "[OK] endpoint reachable."

# Burst probe: send more concurrent requests than the documented burst (40).
# Keep the total strictly below the application window (60) so any observed 429
# is attributable to nginx's burst=40, not to RateLimitBudget.MEDIA_GATE.
if ($Burst -ge 60) {
    Write-Host ""
    Write-Host "[PROBE FAIL] NGINX_BURST=$Burst is >= the application window (60)."
    Write-Host "[PROBE FAIL] A 429 would be ambiguous between nginx and the media_gate"
    Write-Host "[PROBE FAIL] application limiter. Keep NGINX_BURST < 60."
    exit $ExitProbeFail
}

Write-Host ""
Write-Host "--- Burst probe ---"
Write-Host "issuing $Burst concurrent /media/ requests (documented burst=40)"

$burstCodes = New-Object System.Collections.Generic.List[string]
for ($i = 1; $i -le $Burst; $i++) {
    $uri = "$Url/media/seed/verify-nginx-media-limits-gate-$i.jpg"
    $burstCodes.Add((& curl.exe -k -s -o NUL -m 5 -w "%{http_code}" $uri)) | Out-Null
}
$burst429 = @($burstCodes | Where-Object { $_ -eq "429" }).Count
Write-Host "429 responses : $burst429 of $Burst"
if ($burst429 -eq 0) {
    Write-Host "[PROBE FAIL] no 429 observed; the nginx burst limit is not enforcing."
    exit $ExitProbeFail
}
Write-Host "[OK] excess requests refused with 429 (attributable to nginx burst=40;"
Write-Host "     total $Burst < application window 60, so media_gate cannot have 429'd)."

# Settle probe: let the nginx leaky bucket drain, then issue a count at or below
# the burst and expect success (no 429).
Write-Host ""
Write-Host "--- Settle probe ---"
Write-Host "waiting ${Settle}s for the nginx leaky bucket to drain (nodelay window)"
Start-Sleep -Seconds $Settle

$settleCount = 40
Write-Host "issuing $settleCount /media/ requests (at the documented burst, after settle)"
$settleCodes = New-Object System.Collections.Generic.List[string]
for ($i = 1; $i -le $settleCount; $i++) {
    $uri = "$Url/media/seed/verify-nginx-media-limits-settle-$i.jpg"
    $settleCodes.Add((& curl.exe -k -s -o NUL -m 5 -w "%{http_code}" $uri)) | Out-Null
}
$settle429 = @($settleCodes | Where-Object { $_ -eq "429" }).Count
Write-Host "429 responses : $settle429 of $settleCount"
if ($settle429 -gt 0) {
    Write-Host "[PROBE FAIL] settle probe was refused; the bucket did not drain in ${Settle}s."
    exit $ExitProbeFail
}
Write-Host "[OK] settle probe succeeded; the burst limit is enforcing, not merely configured."

Write-Host ""
Write-Host "============================================================"
Write-Host "[PASS] exit=$ExitPass. dev nginx /media/ limit is enforcing."
Write-Host "============================================================"
exit $ExitPass
