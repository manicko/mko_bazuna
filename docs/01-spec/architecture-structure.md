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

## Audit Zone References

Architecture-level audit zones resolved here (full reasoning distributed across the spec/DB docs):

- **C5 / C7** — async/sync boundary, per-process pool, PgBouncer, migrations run exactly once (see Migrations rule). Price index added only after EXPLAIN ANALYZE at 500k rows (see [db-indexes.md](../02-database/db-indexes.md)).
- **D7 / D9 / D10** — FSM has a separate migration owner; category cache is app-level; web is a sync WSGI process (see Source Structure).
- **R8** — `/media/` security (nosniff, whitelist `image/jpeg`, inline) and storage-key anonymity rules live in [db-schema.md](../02-database/db-schema.md).