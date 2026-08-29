# Makefile.ps1 — PowerShell equivalent for Mko Bazuna Docker workflow
# Windows/WSL2 primary development path - provides parity to Makefile targets
#
# NOTE: `param()` MUST be the first executable statement in the script (before any
# function or variable assignment) so this file runs under Windows PowerShell 5.1,
# not only PowerShell 7+.

param(
    [Parameter(Position=0)]
    [string]$Target = "help"
)

# Isolated Compose project names: dev and test run in separate projects so their
# `db` containers, networks, and named volumes never collide.
$DevProject = "mko-bazuna-dev"
$TestProject = "mko-bazuna-test"

# Load environment variables from .env file
$envContent = Get-Content -Path ".env" -ErrorAction SilentlyContinue
if ($envContent) {
    foreach ($line in $envContent) {
        if ($line -match "^([^#=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            # Use env: drive cmdlets (PS 5.1-compatible) instead of $env:$name, which
            # is a PowerShell 7+ only syntax and fails to parse under Windows PowerShell.
            $current = Get-Item -Path "env:$name" -ErrorAction SilentlyContinue
            if (-not $current -or -not $current.Value) {
                Set-Item -Path "env:$name" -Value $value
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
    Write-Host "  up             Start dev environment (web on :8000, hot-reload) + test DB on :5433"
    Write-Host "  down           Stop and remove containers"
    Write-Host "  build          Rebuild Docker images without cache"
    Write-Host "  test           Run fast test gate: skips nightly 'seed' suite (~90s vs ~35min full); auto-starts test DB"
    Write-Host "  test-all       Run complete suite (includes nightly 'seed' tests, ~35min)"
    Write-Host "  test-db        Start test PostgreSQL (long-running, enables reuse-db)"
    Write-Host "  test-down      Stop test environment (preserves DB for reuse-db)"
    Write-Host "  test-logs      Follow test environment logs"
    Write-Host "  test-clean-db  Drop stale test databases (test_mko_bazuna + gw* shards)"
    Write-Host "  test-recreate  Drop and rebuild test DB schema (--no-reuse-db)"
    Write-Host "  lint           Run ruff linter inside web container"
    Write-Host "  typecheck      Run basedpyright type checker inside web container"
    Write-Host "  shell          Open bash shell in web container"
    Write-Host "  migrate        Run database migrations (one-shot, advisory-locked)"
    Write-Host "  consolidate        Consolidate migrations (threshold: `$CONSOLIDATE_THRESHOLD)"
    Write-Host "  consolidate-force  Consolidate all migrations unconditionally"
    Write-Host "  makemigrations Create Django migrations from model changes"
    Write-Host "  create-admin   Create admin user manually"
    Write-Host "  load-catalog   Load categories.yaml into DB (one-shot)"
    Write-Host "  seed-photos-validate  Cross-check photo_manifest.json against fixture files"
    Write-Host "  seed-photos-cleanup   Clean stale manifest entries for missing fixture files"
    Write-Host "  seed-photos-download  Download seed photos from Unsplash/Pexels to fixtures"
    Write-Host "  logs           Follow logs from all services"
    Write-Host "  backup         Create PostgreSQL backup with 7-day rotation"
    Write-Host "  restore        Restore database from backup file"
    Write-Host "  prune-backups  Manually prune backups older than 7 days"
    Write-Host "  clean          Stop containers and remove volumes"
    Write-Host "  fullclean      Full reset: stop dev+test, wipe volumes, prune images/networks/build cache"
}

# Start development environment
function Invoke-Up {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml rm -sf migrate load_catalog create_admin seed
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml up -d
    # Also start the long-running test PostgreSQL (host :5433) so the test
    # environment's DB is ready for `test`/`test-db` immediately. Idempotent.
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
}

# Rebuild images without cache (equiv. to: make build)
function Invoke-Build {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml build --no-cache
}

# Stop and remove containers
function Invoke-Down {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down
}

# Start only the long-running test PostgreSQL (port 5433)
function Invoke-TestDb {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
}

# Stop and remove the test environment (preserves the DB volume for --reuse-db)
function Invoke-TestDown {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml down
}

# Follow test environment logs
function Invoke-TestLogs {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml logs -f
}

# Drop stale test databases (test_mko_bazuna + gw* shards) from the persistent
# test PostgreSQL volume. Uses psql format() to generate DROP DATABASE statements
# and executes each via `psql -c` (psql \gexec is not available for piped input
# in PowerShell the same way as bash). Run before Invoke-TestRecreate to handle
# stuck connections from crashed xdist workers.
function Invoke-TestCleanDb {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
    # Terminate active connections to test databases (exclude this session)
    docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T db psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid();"
    # Generate DROP DATABASE IF EXISTS ... WITH (FORCE); statements and execute each
    docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T db psql -U postgres -d postgres -t -A -c "SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname) FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'" | ForEach-Object {
        $stmt = $_.Trim()
        if ($stmt) {
            docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T db psql -U postgres -d postgres -c $stmt
        }
    }
    Write-Host "Stale test databases dropped." -ForegroundColor Green
}

# Drop and rebuild the test DB schema (ignores the --reuse-db cache).
# The entrypoint-test.sh pipeline (uv sync + wait + migrate + pytest) still runs;
# only pytest's caching flags are overridden via PYTEST_OPTS.
function Invoke-TestRecreate {
    # Pre-flight: drop stale test_mko_bazuna + gw* databases (handles stuck
    # connections from crashed xdist workers before pytest spawns new ones).
    Invoke-TestCleanDb
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm --env "PYTEST_OPTS=--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
}

# Run the fast test gate in the test container (auto-starts the test DB if not
# running). Excludes the nightly `seed` suite (~1,054s of ~1,350s) so a full dev
# iteration runs in ~300s. For the complete suite use `test-all`; for a fresh schema
# use `test-recreate`.
function Invoke-Test {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    # Ensure the long-running test DB is up (idempotent) so --reuse-db can persist.
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
    # PYTEST_SKIP_MARKERS=seed appends -m "not (seed)" in entrypoint-test.sh.
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm --env "PYTEST_SKIP_MARKERS=seed" test
}

# Run the COMPLETE test suite (includes the nightly `seed` suite, ~35min). Use
# this only when a change touches seeding or image generation code paths.
function Invoke-TestAll {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test
}

# Run linter inside web container
function Invoke-Lint {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/
}

# Run type checker inside web container
function Invoke-Typecheck {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run basedpyright src/
}

# Open shell in web container
function Invoke-Shell {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web /bin/bash
}

# Run migrations (one-shot service)
function Invoke-Migrate {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker run --rm migrate
}

# Create migrations from model changes
function Invoke-Makemigrations {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemigrations
}

# Load categories.yaml into DB (one-shot)
function Invoke-LoadCatalog {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm load_catalog
}

# Create admin user manually
function Invoke-CreateAdmin {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    # PS 5.1-compatible defaults (the `||` operator is PowerShell 7+ only).
    $adminUser = if ($env:ADMIN_USERNAME) { $env:ADMIN_USERNAME } else { "admin" }
    $adminTg = if ($env:ADMIN_TELEGRAM_ID) { $env:ADMIN_TELEGRAM_ID } else { "-1" }
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py create_admin_user `
        --username $adminUser `
        --password $env:ADMIN_PASSWORD `
        --telegram-id $adminTg
}

# Follow logs from all services
function Invoke-Logs {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml logs -f
}

# Create database backup with 7-day rotation
function Invoke-Backup {
    $env:COMPOSE_PROJECT_NAME = $DevProject
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

    $env:COMPOSE_PROJECT_NAME = $DevProject
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
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down -v --remove-orphans
    if (Test-Path "./backups") {
        Remove-Item "./backups/*.dump" -Force -ErrorAction SilentlyContinue
    }
}

# Full environment reset: stop both dev and test projects (wiping volumes),
# then remove dangling containers, networks, volumes, unused images, and the
# build cache. Recommended after stale containers or uv layer issues.
# See docs/ops/docker-deployment.md "Full environment reset".
function Invoke-FullClean {
    Write-Host "Stopping dev environment (wiping volumes)..." -ForegroundColor Cyan
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down -v --remove-orphans

    Write-Host "Stopping test environment (wiping volumes)..." -ForegroundColor Cyan
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml down -v --remove-orphans

    Write-Host "Removing dangling containers, networks, and volumes..." -ForegroundColor Yellow
    docker system prune -f --volumes

    Write-Host "Removing all unused images..." -ForegroundColor Yellow
    docker image prune -a -f

    Write-Host "Clearing build cache (important for uv layer issues)..." -ForegroundColor Yellow
    docker builder prune -a -f

    Write-Host "Full clean completed. Run 'build' and 'up' to restart." -ForegroundColor Green
}

# Consolidate migrations (threshold-based)
function Invoke-Consolidate {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    uv run python scripts/consolidate_migrations.py --threshold $CONSOLIDATE_THRESHOLD
    Invoke-Makemigrations
    Invoke-Migrate
}

# Consolidate all migrations unconditionally
function Invoke-ConsolidateForce {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    uv run python scripts/consolidate_migrations.py --force
    Invoke-Makemigrations
    Invoke-Migrate
}

# Validate seed photo manifest against files on disk
function Invoke-SeedPhotosValidate {
    uv run python scripts/download_seed_photos.py --validate
}

# Clean stale manifest entries for missing fixture files
function Invoke-SeedPhotosCleanup {
    uv run python scripts/download_seed_photos.py --validate --fix=cleanup
}

# Download seed photos from Unsplash/Pexels to fixtures/images/
function Invoke-SeedPhotosDownload {
    uv run python scripts/download_seed_photos.py @args
}

# Main entry point
switch ($Target.ToLower()) {
    "help" { Show-Help }
    "up" { Invoke-Up }
    "down" { Invoke-Down }
    "build" { Invoke-Build }
    "test-db" { Invoke-TestDb }
    "test-down" { Invoke-TestDown }
    "test-logs" { Invoke-TestLogs }
    "test-clean-db" { Invoke-TestCleanDb }
    "test-recreate" { Invoke-TestRecreate }
    "test" { Invoke-Test }
    "test-all" { Invoke-TestAll }
    "lint" { Invoke-Lint }
    "typecheck" { Invoke-Typecheck }
    "shell" { Invoke-Shell }
    "migrate" { Invoke-Migrate }
    "makemigrations" { Invoke-Makemigrations }
    "create-admin" { Invoke-CreateAdmin }
    "load-catalog" { Invoke-LoadCatalog }
    "seed-photos-validate" { Invoke-SeedPhotosValidate }
    "seed-photos-cleanup" { Invoke-SeedPhotosCleanup }
    "seed-photos-download" { Invoke-SeedPhotosDownload }
    "consolidate" { Invoke-Consolidate }
    "consolidate-force" { Invoke-ConsolidateForce }
    "logs" { Invoke-Logs }
    "backup" { Invoke-Backup }
    "restore" { Invoke-Restore }
    "prune-backups" { Invoke-PruneBackups }
    "clean" { Invoke-Clean }
    "fullclean" { Invoke-FullClean }
    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
