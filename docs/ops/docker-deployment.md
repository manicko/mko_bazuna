---
id: docker-deployment
domain: ops
tags:
  - deployment
  - docker
  - operations
  - infrastructure
related:
  - restore
  - architecture-structure
  - technical-specification
---

## Purpose

Documentation for deploying and operating the Mko Bazuna platform using Docker. Covers local development setup, production deployment, environment configuration, and routine operational procedures.

## Main Concepts

- **Two-process architecture:** Web (gunicorn WSGI) and bot (aiogram) share one Django project and PostgreSQL database
- **Migrations run exactly once** before both services start
- **Media storage:** Local `MEDIA_ROOT` volume served via nginx
- **TLS termination:** Handled by nginx; HTTPS mandatory for login deep-links and secure cookies

## Local Development Setup

### Prerequisites

- Docker + Docker Compose
- Python 3.14+ with `uv` package manager
- A Telegram bot token from @BotFather

### Quick Start

```bash
# Copy environment template and configure
cp .env.example .env

# Edit .env and set your values:
# - BOT_TOKEN: Your Telegram bot token
# - DJANGO_SECRET_KEY: Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
# - POSTGRES_PASSWORD: Database password

# Start development environment
docker compose -f docker-compose.yml -f docker-compose.dev.override.yml up -d

# Apply migrations
docker compose run --rm migrate
```

### Development Services

| Service | Port | Description |
|---------|------|-------------|
| `web` | 8000 | Django development server (hot-reload enabled) |
| `bot` | — | Telegram bot (logs to stdout) |
| `db` | 5432 | PostgreSQL 18 |
| `nginx` | 80/443 | Optional; use `profiles: ["use-nginx"]` to enable |

### Production-like Development

```bash
# Run without nginx (direct web access on port 8000)
docker compose -f docker-compose.yml -f docker-compose.dev.override.yml up -d

# Or run with nginx (requires TLS certificates for HTTPS)
docker compose -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up -d
```

## Production Deployment

### Docker Compose Production

```bash
# Build images
docker compose build

# Start production services
docker compose up -d

# Apply migrations (run once)
docker compose run --rm migrate
```

### Production Services

| Service | Image/Command | Notes |
|---------|---------------|-------|
| `db` | `postgres:18-alpine` | Persistent volume `postgres_data` |
| `migrate` | Build image, runs migrations | One-shot service with advisory lock |
| `create_admin` | Build image, creates admin user | One-shot service, idempotent |
| `web` | Build image, gunicorn | Port 8000 not published; nginx proxies |
| `bot` | Build image, `python -m telegram_bot.main` | Restarts on failure |
| `nginx` | `nginx:alpine` | Ports 80/443; TLS termination |

### TLS Configuration

Mount TLS certificates at `/etc/nginx/certs/` in the nginx container:

```bash
# Using Let's Encrypt certificates
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production override file (`docker-compose.prod.yml`) includes:
- HTTPS listener on port 443
- HTTP to HTTPS redirect on port 80
- TLS certificate paths configurable via `TLS_CERT_PATH`

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `DJANGO_SECRET_KEY` | Yes | Django secret key for signing |
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `POSTGRES_USER` | Yes | Database username |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `BOT_USERNAME` | Yes | Telegram bot username (without @) |
| `TLS_CERT_PATH` | No | Path to TLS certs (default: `/etc/nginx/certs/`) |
| `PLAUSIBLE_HOST` | No | Analytics host for traffic tracking |
| `ADMIN_USERNAME` | No | Admin username (default: admin) |
| `ADMIN_PASSWORD` | No* | Admin password; required for auto-creation |
| `ADMIN_TELEGRAM_ID` | No | Placeholder telegram_id (default: -1) |

*Required for automatic admin creation via `create_admin` service. Can be created manually if not set.

## Makefile Commands

The project includes a Makefile for common operations:

| Target | Description |
|--------|-------------|
| `make up` | Start dev environment with hot-reload |
| `make down` | Stop and remove containers |
| `make build` | Rebuild Docker images without cache |
| `make restart` | Restart the web service |
| `make test` | Run tests |
| `make lint` | Run ruff linter |
| `make typecheck` | Run basedpyright type checker |
| `make migrate` | Apply database migrations |
| `make create-admin` | Create admin user manually |
| `make makemigrations` | Create new migrations |
| `make shell` | Open shell in web container |
| `make db-shell` | Open psql in database |
| `make logs` | Follow container logs |
| `make backup` | Create database backup |
| `make restore BACKUP_FILE=...` | Restore from backup |

## Scheduled Jobs

### Hourly Sweeps

The platform runs several periodic cleanup tasks:

| Task | Purpose | Schedule |
|------|---------|----------|
| `archive_sweep` | Archive ads older than 2 months | Hourly |
| `delete_sweep` | Hard-delete ads older than 4 months | Hourly |
| `consent_hard_delete` | Erase PII after 30-day withdrawal | Hourly |
| `sweep_drafts` | Delete abandoned DRAFT ads | Hourly |
| `cleanup_login_tokens` | Remove expired login tokens | Hourly |
| `purge_failed_ads` | Delete failed moderation ads (7 days) | Hourly |
| `purge_rejected_ads` | Delete rejected ads (90 days) | Hourly |

### Running Sweeps

```bash
# Run manually
docker compose run --rm web python src/backend/manage.py archive_sweep

# Or via systemd (bare metal)
# /etc/systemd/system/mko-bazuna-scheduler.service
```

## Nginx Configuration

The nginx configuration (`docker/nginx/nginx.conf`) includes:

### Rate Limiting

| Endpoint | Rate Limit | Burst |
|----------|------------|-------|
| `/login/` | 10 req/s | 20 |
| `/search/` | 20 req/s | 40 |

### Security Headers

All responses include:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'`

### Media Access Control

The `/protected-media/` location serves media files only after Django validates ad status:

```nginx
location /protected-media/ {
    internal;
    alias /media_volume/;
    # ... security headers ...
}
```

### Media Security

- Script execution blocked: `.php`, `.py`, `.cgi`, `.pl`, `.sh` files return 403
- Only `image/jpeg` served for uploads
- `Content-Disposition: inline` for all media
- Storage keys are UUID v4 (unguessable, non-sequential)

## Database Operations

### Backup

```bash
# Using Makefile
make backup

# Manual
docker compose exec -T db pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -F c > backups/dump_$(date +%Y%m%d_%H%M%S).dump
```

### Restore

```bash
make restore BACKUP_FILE=./backups/dump_20250719_143022.dump
```

### Migration Management

```bash
# Apply migrations
docker compose run --rm migrate

# Create new migrations
docker compose run --rm web uv run python src/backend/manage.py makemigrations

# Check for missing migrations
docker compose run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run
```

### Admin User Setup

The `create_admin` service creates an admin user for Django admin site access.
Note that the User model uses `telegram_id` as the `USERNAME_FIELD`, so
admin authentication uses this field instead of the username.

#### Automatic Creation

The `create_admin` service runs after migrations complete and creates an admin
user if `ADMIN_PASSWORD` is set in the environment:

```bash
# Admin user is auto-created on `docker compose up -d` if ADMIN_PASSWORD is set
# Verify: docker compose logs create_admin
```

#### Manual Creation

If `ADMIN_PASSWORD` is not set, create the admin user manually:

```bash
# Create admin user
docker compose run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password your_secure_password \
    --telegram-id -1
```

### Admin Login

The Django admin login form shows "Telegram ID" as the username field.
Enter the `ADMIN_TELEGRAM_ID` value (default: `-1`) as the username.

## Monitoring & Logging

### Container Health

- **Web:** Exits on crash; `restart: unless-stopped` restarts automatically
- **Bot:** Healthcheck verifies process is running; logs emitted via stdout
- **Database:** Healthcheck via `pg_isready`

### Log Access

```bash
# Follow all logs
docker compose logs -f

# Specific service
docker compose logs -f bot

# Filter by pattern
docker compose logs | grep "ERROR"
```

### Viewing Metrics

```bash
# Show analytics metrics via admin CLI
docker compose run --rm web uv run python src/backend/manage.py show_metrics
```

## Troubleshooting

### Database Connection Issues

```bash
# Check database health
docker compose ps db

# Connect directly
docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB

# Verify migrations
docker compose run --rm migrate
```

### Bot Not Responding

```bash
# Check bot logs
docker compose logs bot

# Verify bot token
docker compose exec bot env | grep BOT_TOKEN

# Check for Django setup errors
docker compose exec bot python -c "import django; django.setup(); print('OK')"
```

### Media Files Not Loading

```bash
# Check media volume
docker compose exec web ls -la /app/media

# Verify file ownership
docker compose exec web ls -la /app/media/root

# Check nginx logs
docker compose logs nginx
```

### Migration Conflicts

```bash
# Check for unapplied migrations
docker compose run --rm web uv run python src/backend/manage.py showmigrations

# Check for missing migrations
docker compose run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run
```

## Related Documentation

- [Database Restore Runbook](restore.md)
- [Architecture Structure](docs/01-spec/architecture-structure.md)
- [Technical Specification](docs/01-spec/technical-specification.md)
- [DB Schema](docs/02-database/db-schema.md)