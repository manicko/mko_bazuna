# Makefile.ps1 — PowerShell equivalent for Mko Bazuna Docker workflow
# Windows/WSL2 primary development path - provides parity to Makefile targets

# Load environment variables from .env file
$envContent = Get-Content -Path ".env" -ErrorAction SilentlyContinue
if ($envContent) {
    foreach ($line in $envContent) {
        if ($line -match "^([^#=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if (-not $env:$name) {
                $env:$name = $value
            }
        }
    }
}

# Default threshold for consolidation
$CONSOLIDATE_THRESHOLD = 8

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
    Write-Host "  consolidate        Consolidate migrations (threshold: `$CONSOLIDATE_THRESHOLD)"
    Write-Host "  consolidate-force  Consolidate all migrations unconditionally"
    Write-Host "  makemigrations Create Django migrations from model changes"
    Write-Host "  create-admin   Create admin user manually"
    Write-Host "  load-catalog   Load categories.yaml into DB (one-shot)"
    Write-Host "  logs           Follow logs from all services"
    Write-Host "  backup         Create PostgreSQL backup with 7-day rotation"
    Write-Host "  restore        Restore database from backup file"
    Write-Host "  prune-backups  Manually prune backups older than 7 days"
    Write-Host "  clean          Stop containers and remove volumes"
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

# Load categories.yaml into DB (one-shot)
function Invoke-LoadCatalog {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm load_catalog
}

# Create admin user manually
function Invoke-CreateAdmin {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py create_admin_user `
        --username ($env:ADMIN_USERNAME || "admin") `
        --password $env:ADMIN_PASSWORD `
        --telegram-id ($env:ADMIN_TELEGRAM_ID || "-1")
}

# Follow logs from all services
function Invoke-Logs {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml logs -f
}

# Create database backup with 7-day rotation
function Invoke-Backup {
    $backupsDir = "./backups"
    if (-not (Test-Path $backupsDir)) {
        New-Item -ItemType Directory -Path $backupsDir | Out-Null
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = "$backupsDir\dump_$timestamp.dump"

    $pgUser = $env:POSTGRES_USER
    $pgDb = $env:POSTGRES_DB

    if (-not $pgUser -or -not $pgDb) {
        Write-Host "Error: POSTGRES_USER and POSTGRES_DB must be set in .env or environment" -ForegroundColor Red
        exit 1
    }

    docker compose exec -T db pg_dump -U $pgUser -d $pgDb -F c > $backupFile
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

    $pgUser = $env:POSTGRES_USER
    $pgDb = $env:POSTGRES_DB

    if (-not $pgUser -or -not $pgDb) {
        Write-Host "Error: POSTGRES_USER and POSTGRES_DB must be set in .env or environment" -ForegroundColor Red
        exit 1
    }

    docker compose exec -T db pg_restore -U $pgUser -d $pgDb --clean --if-exists $BackupFile
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

# Clean - stop containers and remove volumes
function Invoke-Clean {
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml down -v --remove-orphans
    if (Test-Path "./backups") {
        Remove-Item "./backups/*.dump" -Force -ErrorAction SilentlyContinue
    }
}

# Consolidate migrations (threshold-based)
function Invoke-Consolidate {
    uv run python scripts/consolidate_migrations.py --threshold $CONSOLIDATE_THRESHOLD
    Invoke-Makemigrations
    Invoke-Migrate
}

# Consolidate all migrations unconditionally
function Invoke-ConsolidateForce {
    uv run python scripts/consolidate_migrations.py --force
    Invoke-Makemigrations
    Invoke-Migrate
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
    "create-admin" { Invoke-CreateAdmin }
    "load-catalog" { Invoke-LoadCatalog }
    "consolidate" { Invoke-Consolidate }
    "consolidate-force" { Invoke-ConsolidateForce }
    "logs" { Invoke-Logs }
    "backup" { Invoke-Backup }
    "restore" { Invoke-Restore }
    "prune-backups" { Invoke-PruneBackups }
    "clean" { Invoke-Clean }
    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Show-Help
        exit 1
    }
}