---
id: architecture-structure
domain: wiki
tags:
  - architecture
  - structure
  - deployment
related:
  - technical-specification
  - db-structure
  - packages
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
│   │   ├── locations/              # cities / regions
│   │   ├── moderation/             # moderation logs, criteria, statuses
│   │   ├── search/                # PostgreSQL FTS (search_vector, GIN, russian) — no haystack/whoosh
│   │   └── api/                   # DRF API — DEFERRED to post-MVP (phase 1 = HTMX MPA)
│   └── manage.py
├── telegram_bot/                  # separate entrypoint; runs django.setup() + shared ORM
│   ├── bot/                       # aiogram 3.x handlers, FSM, middlewares (Bot API, NOT userbot)
│   ├── parsers/                   # DEFERRED to phase 2 (group monitoring, decision B)
│   ├── services/                  # business logic (create_ad_from_message, etc.)
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
| `web` | Django + gunicorn (sync WSGI) from `docker/Dockerfile`; `gunicorn config.wsgi:application --bind 0.0.0.0:8000` | Mounts `media_volume`; `env_file: .env`; `depends_on db` (healthy); port 8000 NOT published. |
| `bot` | Same image; `python -m telegram_bot.main` | Mounts `media_volume`; `depends_on db`; `restart: unless-stopped`. |
| `nginx` | `nginx:alpine`; ports 80/443 | Mounts `static_volume` (ro) + `media_volume` (ro); `proxy_pass → web:8000`; serves `/static/` + `/media/`; TLS. |

Volumes: `postgres_data`, `media_volume`, `static_volume`.

### Rules
- **nginx is REQUIRED in phase 1:** whitenoise does NOT serve user-uploaded media; local MEDIA_ROOT needs nginx. Plus TLS termination (HTTPS mandatory: login deep-link tokens, Secure cookies). Web service is not exposed.
- **Dockerfile:** `python:3.14-slim` + `uv` (pin `uv>=0.11.28`); non-root user; `RUN uv run python manage.py collectstatic --noinput`.
- **Django settings:** `USE_X_FORWARDED_HOST=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `SECURE_SSL_REDIRECT=True`.
- **/media/ security (zone R8):** nginx blocks script execution (`location ~* /media/.*\.(php|py|cgi)$ { deny all; }`); `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`, default `application/octet-stream`; `Content-Disposition: inline`; media keys are UUID v4 (unguessable).
- **PgBouncer (recommended, zone C5):** shared external pool in transaction mode between web+bot; each process keeps `CONN_MAX_AGE=0`. With psycopg3 + PgBouncer tx mode set `OPTIONS={"prepare_threshold": None}`.
- **Migrations (zone C5/D7):** run exactly ONCE before web and bot start (dedicated step / ordering guard) so the two processes don't migrate concurrently. Domain writes (`ads`/`LoginToken`) go in ONE Django transaction. The aiogram FSM has NO built-in PG storage — the step-by-step dialog is persisted as an `Ad` row with status `DRAFT` via the shared ORM. "FSM clear" = `DRAFT → ON_MODERATION` in one transaction.
- **Secrets:** `.env` (`BOT_TOKEN`, DB, `SECRET_KEY`) via `env_file: .env`. `API_ID`/`API_HASH` (MTProto/userbot) are NOT needed in phase 1 and removed from `.env`.
Стой, их могли переименовать твои агенты. Изучи сессии задание было не переписывать имеющиеся файлы, а создать новые сохранив старые. Изучи прошлые весрии гитТак