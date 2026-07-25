---
id: architecture-structure
domain: spec
tags:
  - architecture
  - structure
  - deployment
related:
  - technical-specification
  - db-schema
  - db-indexes
  - packages-list
  - local-https-mkcert
---

## Purpose

Source-tree layout and Docker deployment topology for phase 1. Two long-lived processes
(web + bot) share one Django project and one PostgreSQL database.

## Source Structure

```
src/
├── backend/                       # Django project
│   ├── config/                    # settings.py, urls.py, asgi.py, wsgi.py
│   ├── apps/                      # INSTALLED_APPS = ['apps.xxx']
│   │   ├── core/                  # shared utils, abstract models, managers, signals
│   │   ├── users/                 # users, telegram binding (telegram_id)
│   │   ├── ads/                   # ads, images, statuses
│   │   ├── categories/            # mptt tree (django-mptt>=0.18.0, single source of truth)
│   │   ├── locations/             # cities / regions
│   │   ├── moderation/            # moderation logs, criteria, statuses
│   │   ├── search/                # PostgreSQL FTS (search_vector, GIN, russian) — no haystack/whoosh
│   │   └── api/                   # DRF API — DEFERRED to post-MVP (phase 1 = HTMX MPA)
│   └── manage.py
├── telegram_bot/                  # separate entrypoint; runs django.setup() + shared ORM
│   ├── states.py                  # AdCreateState FSM states (aiogram 3.x)
│   ├── handlers/                  # aiogram 3.x handlers (login, ad_create)
│   ├── schemas/                   # pydantic v2 DTOs for bot message payloads (rule 11)
│   ├── services/                  # business logic (media.py for photo handling)
│   ├── config.py
│   └── main.py
├── scraping_service/              # DEFERRED to phase 2 (decision B). Separate Telethon userbot process.
├── templates/                     # global templates (base.html, includes/)
├── static/                        # global static assets
├── media/                         # Phase 1 storage: local MEDIA_ROOT (Docker volume) behind nginx.
│                                 #   Django FileSystemStorage via STORAGES. Bot downloads Telegram
│                                 #   photos here; served via <img src>. NOT Telegram CDN.
├── tests/                         # pytest, split per app
├── docs/
├── docker/
│   └── Dockerfile                 # python:3.14-slim + uv; non-root USER; collectstatic
├── .env.example
├── docker-compose.yml             # services: db + web + bot + nginx
└── pyproject.toml
```

## Deployment (Docker, phase 1)

`docker-compose.yml` services:

| Service | Image / Command | Notes |
|---------|----------------|-------|
| `db` | `postgres:18-alpine` + volume + healthcheck (`pg_isready`) | — |
| `web` | Django + gunicorn (sync WSGI) from `docker/Dockerfile`; `gunicorn config.wsgi:application --bind 0.0.0.0:8000` | Mounts `media_volume`; `env_file: .env`; `depends_on migrate` (completed successfully); port 8000 NOT published. |
| `bot` | Same image; `python -m telegram_bot.main` | Mounts `media_volume`; `depends_on migrate`; `restart: unless-stopped`. |
| `nginx` | `nginx:alpine`; ports 80/443 | Mounts `media_volume` (ro); `proxy_pass → web:8000`; serves `/media/`; TLS. Static files served via whitenoise proxy. |

Volumes: `postgres_data`, `media_volume`. Static files baked into image via whitenoise; nginx serves `/media/` only.

### Rules
- **nginx is REQUIRED in phase 1:** whitenoise does NOT serve user-uploaded media; local MEDIA_ROOT needs nginx. Plus TLS termination (HTTPS mandatory: login deep-link tokens, Secure cookies). Web service is not exposed.
- **Dockerfile:** `python:3.14-slim` + `uv` (pin `uv>=0.11.28`); non-root user; `RUN uv run python manage.py collectstatic --noinput`.
- **Django settings:** `USE_X_FORWARDED_HOST=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `SECURE_SSL_REDIRECT=True`.
- **/media/ security:** nginx blocks script execution (`location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`); `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`, default `application/octet-stream`, `Content-Disposition: inline`; media keys are UUID v4 (unguessable, non-sequential).
- **PgBouncer (recommended):** shared external pool in transaction mode between web+bot; each process holds `CONN_MAX_AGE=0`. With psycopg3 + PgBouncer tx mode set `OPTIONS={"prepare_threshold": None}`.
- **Migrations (zone C5/D7):** run exactly ONCE before web and bot start (dedicated step / ordering guard) so the two processes don't migrate concurrently. Domain writes (`ads`/`LoginToken`) go in ONE Django transaction.
- **Secrets:** `.env` (`BOT_TOKEN`, DB, `SECRET_KEY`) via `env_file: .env`. `API_ID`/`API_HASH` (MTProto/userbot) are NOT needed in phase 1 and removed from `.env`.

### Scheduler Configuration (Phase 4)

**Docker production mode:** Use `entrypoint-scheduler.sh` with the `scheduler` profile in `docker-compose.prod.yml`:

```bash
# Start scheduler alongside web and bot
# Scheduler runs all sweep commands hourly
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile scheduler up -d
```

The scheduler runs all sweep commands hourly: `archive_sweep`, `delete_sweep`, `consent_hard_delete`, `sweep_drafts`, `cleanup_login_tokens`, `purge_failed_ads`, `purge_rejected_ads`.

**Systemd alternative (bare metal):**

```ini
# /etc/systemd/system/mko-bazuna-scheduler.service
[Unit]
Description=Mko Bazuna lifecycle sweep scheduler
After=postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/mko-bazuna
ExecStart=/opt/venv/bin/python manage.py shell -c "
import time, sys, subprocess;
commands = ['archive_sweep', 'delete_sweep', 'consent_hard_delete', 'sweep_drafts', 'cleanup_login_tokens', 'purge_failed_ads', 'purge_rejected_ads'];
while True:
    for cmd in commands: subprocess.run([sys.executable, 'manage.py', cmd]);
    time.sleep(3600)
"
Restart=always

[Install]
WantedBy=multi-user.target
```

**Cron alternative (bare metal):**

```cron
# /etc/cron.d/mko-bazuna-sweeps
0  * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py archive_sweep
5  * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py delete_sweep
10 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py consent_hard_delete
15 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py sweep_drafts
20 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py cleanup_login_tokens
25 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py purge_failed_ads
30 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py purge_rejected_ads
```

### Scheduled-job concurrency (advisory locks)

All seven sweep commands — and the once-only `migrate` step — run against the same
shared PostgreSQL database as the live web and bot processes. To prevent concurrent
sweeps (or a sweep and a migration) from colliding on the same rows, every command
acquires a **transaction-scoped PostgreSQL advisory lock**
(`apps.core.utils.advisory_lock`, `pg_advisory_xact_lock`) before doing its work. The
lock is released automatically on transaction commit/rollback, so it is safe under
PgBouncer transaction pooling. `migrate` instead uses a **session-scoped** lock
(`pg_advisory_lock`) because it runs before PgBouncer is attached.

Lock IDs are fixed and allocated centrally in the `AdvisoryLockId` IntEnum
(`apps.core.enums`) so they never collide:

| Lock ID | Held by |
|---------|---------|
| 1 | `archive_sweep` |
| 2 | `delete_sweep` |
| 3 | `consent_hard_delete` |
| 4 | `sweep_drafts` |
| 5 | `cleanup_login_tokens` |
| 6 | `purge_failed_ads` |
| 7 | `purge_rejected_ads` |
| 100 | `migrate` (session-scoped, pre-PgBouncer) |
| 101 | `create_admin_user` (session-scoped, for idempotent admin creation) |

Every command is idempotent, supports `--dry-run`, and logs via `logger` (no
`print`). The scheduler service is gated by `profiles: ["scheduler"]` so it does not
start — and does not crash on missing commands — before the command modules exist.

### NGINX Hardening (Zone R8)

The production nginx configuration (`docker/nginx/nginx.conf`) implements:

- **Security headers (all responses):** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'`
- **Script execution blocked:** `location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }` in `/media/` location
- **MIME whitelist:** Only `image/jpeg` served for `/media/` uploads; default `application/octet-stream`
- **Media behavior:** `Content-Disposition: inline` for all media responses
- **Rate limiting:**
  - `/login/`: 10 req/s burst 20 (`login_limit` zone)
  - `/search/`: 20 req/s burst 40 (`search_limit` zone)
- **TLS termination:** Certificates mounted at `/etc/nginx/certs/` (configurable via `TLS_CERT_PATH` env var). For local development with HTTPS, see [Local HTTPS with mkcert](../../ops/local-https-mkcert.md).

## Audit Zone References

Architecture-level audit zones resolved here (full reasoning distributed across the spec/DB docs):

- **C5 / C7** — async/sync boundary, per-process pool, PgBouncer, migrations run exactly once (see Migrations rule). Price index added only after EXPLAIN ANALYZE at 500k rows (see [db-indexes.md](../02-database/db-indexes.md)).
- **D7 / D9 / D10** — FSM has a separate migration owner; category cache is app-level; web is a sync WSGI process (see Source Structure).
- **R8** — `/media/` security (nosniff, whitelist `image/jpeg`, inline) and storage-key anonymity rules live in [db-schema.md](../02-database/db-schema.md).