param(
    [Parameter(Mandatory = $true)]
    [string]$RunUrl
)

$ErrorActionPreference = "Stop"

# ============================================================
# Configuration
# ============================================================

$Owner = "manicko"
$Repo  = "mko_bazuna"

# .env находится ВНЕ проекта:
# C:\Users\<username>\.github-actions\.env
$EnvFile = Join-Path $HOME ".github-actions\.env"

# Логи сохраняем в проекте
$OutputRoot = Join-Path $PSScriptRoot "..\.ai\actions-logs"
$LatestDir  = Join-Path $OutputRoot "latest"

# ============================================================
# Read .env
# ============================================================

if (-not (Test-Path $EnvFile)) {
    throw @"
GitHub token file not found:

$EnvFile

Create this file with:

GITHUB_ACTIONS_LOG_TOKEN=github_pat_xxxxxxxxxxxxxxxxx
"@
}

$Token = $null

foreach ($Line in Get-Content $EnvFile) {

    $Line = $Line.Trim()

    # Ignore empty lines and comments
    if ([string]::IsNullOrWhiteSpace($Line)) {
        continue
    }

    if ($Line.StartsWith("#")) {
        continue
    }

    if ($Line -match '^GITHUB_ACTIONS_LOG_TOKEN\s*=\s*(.*)$') {

        $Token = $Matches[1].Trim()

        # Remove optional quotes
        if (
            ($Token.StartsWith('"') -and $Token.EndsWith('"')) -or
            ($Token.StartsWith("'") -and $Token.EndsWith("'"))
        ) {
            $Token = $Token.Substring(1, $Token.Length - 2)
        }

        break
    }
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    throw @"
GITHUB_ACTIONS_LOG_TOKEN was not found in:

$EnvFile

Expected format:

GITHUB_ACTIONS_LOG_TOKEN=github_pat_xxxxxxxxxxxxxxxxx
"@
}

# ============================================================
# Extract Run ID from GitHub URL
#
# Example:
# https://github.com/manicko/mko_bazuna/actions/runs/123456789
# ============================================================

if ($RunUrl -notmatch "/actions/runs/(\d+)") {
    throw "Could not extract GitHub Actions run ID from URL: $RunUrl"
}

$RunId = $Matches[1]

Write-Host "Run ID: $RunId"

# ============================================================
# Prepare output directory
# ============================================================

if (Test-Path $LatestDir) {
    Remove-Item $LatestDir -Recurse -Force
}

New-Item `
    -ItemType Directory `
    -Path $LatestDir `
    -Force |
    Out-Null

# ============================================================
# GitHub API headers
# ============================================================

$Headers = @{
    "Accept"               = "application/vnd.github+json"
    "Authorization"       = "Bearer $Token"
    "X-GitHub-Api-Version" = "2022-11-28"
}

function Invoke-GitHubApi {
    param(
        [string]$Uri
    )

    return Invoke-RestMethod `
        -Uri $Uri `
        -Headers $Headers `
        -Method Get
}

# ============================================================
# Get workflow run
# ============================================================

Write-Host "Getting workflow run..."

$RunApiUrl = "https://api.github.com/repos/$Owner/$Repo/actions/runs/$RunId"

$Run = Invoke-GitHubApi $RunApiUrl

# Save run metadata
$Run |
    ConvertTo-Json -Depth 20 |
    Set-Content `
        -Path (Join-Path $LatestDir "run.json") `
        -Encoding UTF8

# ============================================================
# Get jobs
# ============================================================

Write-Host "Getting jobs..."

$JobsApiUrl =
    "https://api.github.com/repos/$Owner/$Repo/actions/runs/$RunId/jobs?per_page=100"

$JobsResponse = Invoke-GitHubApi $JobsApiUrl

$Jobs = @($JobsResponse.jobs)

if ($Jobs.Count -eq 0) {
    throw "No jobs found for run $RunId"
}

# ============================================================
# Find failed jobs
# ============================================================

$FailedJobs = @(
    $Jobs | Where-Object {
        $_.conclusion -eq "failure" -or
        $_.conclusion -eq "cancelled" -or
        $_.conclusion -eq "timed_out"
    }
)

if ($FailedJobs.Count -eq 0) {

    Write-Host ""
    Write-Host "No failed jobs found."
    Write-Host ""

    $Jobs |
        Select-Object name, status, conclusion |
        Format-Table -AutoSize

    exit 0
}

Write-Host ""
Write-Host "Failed jobs: $($FailedJobs.Count)"

# ============================================================
# Download logs
# ============================================================

$Summary = @()

foreach ($Job in $FailedJobs) {

    $JobId   = $Job.id
    $JobName = $Job.name

    Write-Host ""
    Write-Host "Downloading: $JobName ($JobId)"

    # Make job name safe for Windows filename
    $SafeName = $JobName -replace '[\\/:*?"<>|]', '_'

    $LogPath = Join-Path $LatestDir "$SafeName.log"

    $LogApiUrl =
        "https://api.github.com/repos/$Owner/$Repo/actions/jobs/$JobId/logs"

    try {

        $Response = Invoke-WebRequest `
            -Uri $LogApiUrl `
            -Headers $Headers `
            -Method Get `
            -MaximumRedirection 10 `
            -UseBasicParsing

        $Response.Content |
            Set-Content `
                -Path $LogPath `
                -Encoding UTF8

        Write-Host "Saved: $LogPath"

        $Summary += [PSCustomObject]@{
            Job        = $JobName
            JobId      = $JobId
            Conclusion = $Job.conclusion
            Log        = "$SafeName.log"
        }
    }
    catch {

        Write-Warning "Failed to download log for $JobName"
        Write-Warning $_.Exception.Message

        $Summary += [PSCustomObject]@{
            Job        = $JobName
            JobId      = $JobId
            Conclusion = $Job.conclusion
            Log        = "FAILED TO DOWNLOAD"
        }
    }
}

# ============================================================
# Create summary.md
# ============================================================

$SummaryPath = Join-Path $LatestDir "summary.md"

$Lines = @()

$Lines += "# GitHub Actions failure"
$Lines += ""
$Lines += "**Repository:** $Owner/$Repo"
$Lines += "**Run ID:** $RunId"
$Lines += "**Workflow:** $($Run.name)"
$Lines += "**Branch:** $($Run.head_branch)"
$Lines += "**Commit:** $($Run.head_sha)"
$Lines += "**Status:** $($Run.status)"
$Lines += "**Conclusion:** $($Run.conclusion)"
$Lines += ""
$Lines += "## Failed jobs"
$Lines += ""

foreach ($Item in $Summary) {

    $Lines += "### $($Item.Job)"
    $Lines += ""
    $Lines += "- Job ID: $($Item.JobId)"
    $Lines += "- Conclusion: $($Item.Conclusion)"
    $Lines += "- Log: ``$($Item.Log)``"
    $Lines += ""
}

$Lines |
    Set-Content `
        -Path $SummaryPath `
        -Encoding UTF8

# ============================================================
# Done
# ============================================================

Write-Host ""
Write-Host "========================================"
Write-Host "GitHub Actions logs downloaded"
Write-Host "========================================"
Write-Host ""
Write-Host "Run:      $RunId"
Write-Host "Workflow: $($Run.name)"
Write-Host "Output:   $LatestDir"
Write-Host ""
Write-Host "Files:"

Get-ChildItem $LatestDir |
    Select-Object Name, Length |
    Format-Table -AutoSize