# Makefile.ps1 — PowerShell equivalent for Mko Bazuna Docker workflow
# Windows/WSL2 primary development path - provides parity to Makefile targets

# Show help
function Show-Help {
    Write-Host "Mko Bazuna - Development Commands" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\Makefile.ps1 <target>"
    Write-Host ""
    Write-Host "Targets:"
    Write-Host "  up             Start development environment (web on :8000, hot-reload)"
    Write-Host "  down           Stop and remove containers"
    Write-Host "  test           Run pytest in test container (ephemeral PostgreSQL)"
    Write-Host "  lint           Run ruff linter inside web container"
    Write-Host "  typecheck      Run basedpyright type checker inside web container"
    Write-Host "  shell          Open bash shell in web container"
    Write-Host "  migrate        Run database migrations (one-shot, advisory-locked)"
    Write-Host "  makemigrations Create Django migrations from model changes"
    Write-Host "  logs           Follow logs from all services"
    Write-Host "  backup         Create PostgreSQL backup with 7-day rotation"
    Write-Host "  restore        Restore database from backup file"
    Write-Host "  prune-backups  Manually prune backups older than 7 days"
}

# Start development environment
function Invoke-Up {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml up -d
}

# Stop and remove containers
function Invoke-Down {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml down
}

# Run tests in test container (ephemeral PostgreSQL)
function Invoke-Test {
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test
}

# Run linter inside web container
function Invoke-Lint {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/
}

# Run type checker inside web container
function Invoke-Typecheck {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run basedpyright src/
}

# Open shell in web container
function Invoke-Shell {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web /bin/bash
}

# Run migrations (one-shot service)
function Invoke-Migrate {
    docker compose run --rm migrate
}

# Create migrations from model changes
function Invoke-Makemigrations {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemigrations
}

# Follow logs from all services
function Invoke-Logs {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml logs -f
}

# Create database backup with timestamp and 7-day rotation
function Invoke-Backup {
    $backupsDir = "./backups"
    if (-not (Test-Path $backupsDir)) {
        New-Item -ItemType Directory -Path $backupsDir | Out-Null
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = "$backupsDir\dump_$timestamp.dump"

    docker compose exec -T db pg_dump -U $env:POSTGRES_USER -d $env:POSTGRES_DB -F c > $backupFile
    Write-Host "Backup created: $backupFile" -ForegroundColor Green

    # Prune backups older than 7 days
    $oldBackups = Get-ChildItem -Path $backupsDir -Filter "dump_*.dump" | Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-7) }
    foreach ($file in $oldBackups) {
        Remove-Item $file.FullName -Force
        Write-Host "Pruned old backup: $($file.Name)" -ForegroundColor Yellow
    }
}

# Restore database from backup file
function Invoke-Restore {
    param(
        [Parameter(Mandatory=$true)]
        [string]$BackupFile
    )

    if (-not (Test-Path $BackupFile)) {
        Write-Host "Error: Backup file not found: $BackupFile" -ForegroundColor Red
        exit 1
    }

    docker compose exec -T db pg_restore -U $env:POSTGRES_USER -d $env:POSTGRES_DB --clean --if-exists $BackupFile
}

# Manual prune of old backups
function Invoke-PruneBackups {
    $backupsDir = "./backups"
    if (-not (Test-Path $backupsDir)) {
        Write-Host "No backups directory found" -ForegroundColor Yellow
        return
    }

    $oldBackups = Get-ChildItem -Path $backupsDir -Filter "dump_*.dump" | Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-7) }
    foreach ($file in $oldBackups) {
        Remove-Item $file.FullName -Force
        Write-Host "Pruned old backup: $($file.Name)" -ForegroundColor Yellow
    }
    Write-Host "Old backups (7+ days) pruned" -ForegroundColor Green
}

# Main entry point
param(
    [Parameter(Position=0)]
    [string]$Target = "help"
)

switch ($Target.ToLower()) {
    "help" { Show-Help }
    "up" { Invoke-Up }
    "down" { Invoke-Down }
    "test" { Invoke-Test }
    "lint" { Invoke-Lint }
    "typecheck" { Invoke-Typecheck }
    "shell" { Invoke-Shell }
    "migrate" { Invoke-Migrate }
    "makemigrations" { Invoke-Makemigrations }
    "logs" { Invoke-Logs }
    "backup" { Invoke-Backup }
    "restore" { Invoke-Restore }
    "prune-backups" { Invoke-PruneBackups }
    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Show-Help
        exit 1
    }
}