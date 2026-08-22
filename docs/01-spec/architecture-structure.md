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

Source-tree layout and Docker deployment topology for phases 1 and 2. Two long-lived processes
(web + bot) share one Django project and one PostgreSQL database.

## Source Structure

```
src/
├── backend/                       # Django project
│   ├── config/                    # settings.py, urls.py, asgi.py, wsgi.py
│   ├── apps/                      # INSTALLED_APPS = ['apps.xxx']
│   │   ├── core/                  # shared utils, abstract models, managers, signals
│   │   │   ├── management/commands/  # sweep commands (archive, delete, consent, drafts, tokens, purge)
│   │   │   ├── middleware/           # language locale + preferred city (LanguagePreMiddleware, PreferredCityMiddleware)
│   │   │   ├── services/             # contact service
│   │   │   ├── templatetags/         # contact_tags, localized_content
│   │   │   ├── tests/                # sweep command tests, context processor tests
│   │   │   ├── utils/                # advisory_lock, cache, migrate_locked, sanitize
│   │   │   ├── context_processors.py
│   │   │   ├── enums.py
│   │   │   ├── urls.py
│   │   │   └── views.py
│   │   ├── users/                 # users, telegram binding (telegram_id)
│   │   │   ├── migrations/
│   │   │   ├── services/             # account_state, deletion
│   │   │   ├── tests/
│   │   │   ├── views/                # consent views
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   └── urls.py
│   │   ├── ads/                   # ads, images, statuses
│   │   │   ├── migrations/
│   │   │   ├── tests/
│   │   │   ├── views/                # dashboard, delete, edit, listings
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   └── urls.py
│   │   ├── categories/            # mptt tree (django-mptt>=0.18.0, single source of truth)
│   │   │   ├── catalog/              # categories.yaml + builder.py (plan16)
│   │   │   ├── migrations/
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   ├── services/             # lookup_resolution (CategoryLookupResolver)
│   │   │   ├── views.py              # category_submenu — GET /categories/<slug>/submenu/ (cached HTML fragment, tree-version invalidation)
│   │   │   └── urls.py
│   │   ├── lookups/               # universal lookup system (LookupGroup, LookupItem) — plan16
│   │   │   ├── migrations/
│   │   │   ├── services/             # cache_service (LookupCacheService)
│   │   │   ├── enums.py
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   └── models.py
│   │   ├── locations/             # cities / regions
│   │   │   ├── migrations/
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   └── urls.py
│   │   ├── moderation/            # moderation logs, criteria, statuses
│   │   │   ├── migrations/
│   │   │   ├── services/             # auto_moderation, moderation_log, priority_calculator
│   │   │   ├── tests/
│   │   │   ├── views/                # review
│   │   │   ├── admin.py
│   │   │   ├── admin_actions.py
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   ├── signals.py
│   │   │   ├── tests.py
│   │   │   └── urls.py
│   │   ├── seed/                  # dev-only demo data generation (no models)
│   │   │   ├── config/               # seed.default.json
│   │   │   ├── fixtures/             # categories.json, cities.json, ads_templates.json, word_lists.json, images/
│   │   │   ├── generators/           # UserGenerator, AdGenerator, ImageGenerator, AnalyticsGenerator
│   │   │   ├── management/commands/  # seed.py
│   │   │   ├── services/             # SeedService orchestrator
│   │   │   └── tests/                # test_seed.py
│   │   ├── search/                # PostgreSQL FTS (per-language search_vector_ru/bs/en, GIN, ru/bs/en configs) — no haystack/whoosh
│   │   │   ├── migrations/
│   │   │   ├── services/             # alert_query, entity_suggestions, popular_search, rate_limit, search_history
│   │   │   ├── tests/
│   │   │   ├── views/                # autocomplete, search
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   ├── tests.py
│   │   │   └── urls.py
│   │   ├── cabinet/               # user cabinet hub (favorites, saved searches, history, settings)
│   │   ├── analytics/             # analytics events, daily rollups, trust & moderation analytics
│   │   │   ├── management/commands/  # rollup_daily_metrics, show_metrics
│   │   │   ├── migrations/
│   │   │   ├── services/             # moderation_analytics, seller_stats, trust_analytics
│   │   │   ├── tests/
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   └── models.py
  │   │   ├── media/                 # thumbnail generation, image processing (Pillow)
  │   │   │   ├── management/commands/
  │   │   │   ├── services/             # thumbnails, hash_service (FileHashService — plan16)
  │   │   │   ├── tests/
  │   │   │   └── apps.py
│   │   ├── trust/                 # trust scoring, seller verification, trust badges
│   │   │   ├── migrations/
│   │   │   ├── services/             # trust_calculator
│   │   │   ├── templatetags/         # trust_tags
│   │   │   ├── tests/
│   │   │   ├── apps.py
│   │   │   └── models.py
│   │   └── api/                   # DRF API — DEFERRED to post-MVP (phase 1 = HTMX MPA)
│   │       ├── serializers/
│   │       └── views/
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

## Middleware & context processors

Request-time enrichment injected before view rendering. Middleware lives in
`apps/core/middleware/`; context processors in `apps/core/context_processors.py`
(`header_context`) and `apps/users/context_processors.py` (`consent_state`).

### Middleware

| Middleware | Location | Purpose |
|---|---|---|
| `LanguagePreMiddleware` | `apps/core/middleware/` | Reads `lang_pref` cookie / `?lang=X`; sets `request.LANGUAGE_CODE`. |
| `PreferredCityMiddleware` | `apps/core/middleware/preferred_city.py` | Resolves `request.preferred_city` (effective city slug or `None`) as the default city filter. Priority: authenticated `User.preferred_city` FK (wins) → validated `preferred_city` cookie → `None`. Stale cookies deleted in `process_response`. Cookie name is the module constant `PREFERRED_CITY_COOKIE_NAME` (mirrors `LanguagePreMiddleware`, not a `StrEnum`). |
| `CategoryMiddleware` | `apps/core/middleware/` | Category context for listings (plan 16). |

Registration order: `PreferredCityMiddleware` runs **after** `AuthenticationMiddleware`
(it reads `request.user`) and **before** category/locale middleware, so views see the
resolved `request.preferred_city` as a default filter. Writes never happen here — the
cookie/DB is written only by `set_preferred_city` (`apps/search/views/preferred_city.py`).

### Context processors

| Processor | Module | Variables | Consumed by |
|---|---|---|---|
| `header_context` | `apps/core/context_processors.py` | `bot_username`, `root_categories`, `preferred_city_display`, `cities`, `favorites_count` | Catalog header (`header_catalog.html`) |
| `consent_state` | `apps/users/context_processors.py` | `consent_shown`, `consent_analytics`, `consent_preferences` | Consent banner + script gating (11 templates) |
| `plausible_host` | `apps/core/context_processors.py` | `PLAUSIBLE_HOST` | Gated Plausible snippet (`{% if consent_analytics and PLAUSIBLE_HOST %}`) |
| `language` | `apps/core/context_processors.py` | `LANGUAGE_CODE` | All templates |

`favorites_count` is `None` for anonymous visitors (outline heart, no count); for
authenticated sellers it is their favorite count. The header heart badge refreshes via
the `favorite:toggled` custom event → `GET cabinet:favorites_count` (HTMX `outerHTML` swap);
see [ui-patterns.md](ui-patterns.md).

## Deployment (Docker, phase 1)

`docker-compose.yml` services:

| Service | Image / Command | Notes |
|---------|----------------|-------|
| `db` | `postgres:18-alpine` + volume + healthcheck (`pg_isready`) | — |
| `web` | Django + gunicorn (sync WSGI) from `docker/Dockerfile`; `gunicorn config.wsgi:application --bind 0.0.0.0:8000` | Mounts `media_volume`; `env_file: .env`; `depends_on migrate` (completed successfully); port 8000 NOT published. |
| `bot` | Same image; `python -m telegram_bot.main` | Mounts `media_volume`; `depends_on migrate`; `restart: unless-stopped`. |
| `migrate` | Same image; one-shot migration | Runs `entrypoint.sh` with `migrate` command; session-scoped advisory lock ID 100. |
| `create_admin` | Same image; one-shot admin creation | Runs `entrypoint-create-admin.sh`; session-scoped advisory lock ID 101. Idempotent. |
| `seed` | Same image; one-shot demo data | Runs `entrypoint-seed.sh`; gated by `profiles: ["seed"]`. Populates DB with demo data. Session-scoped advisory lock ID 110. |
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
| 8 | `rollup_daily_metrics` |
| 9 | `alert_delivery_task` |
| 10 | `queue_processing` |
| 100 | `migrate` (session-scoped, pre-PgBouncer) |
| 101 | `create_admin_user` (session-scoped, for idempotent admin creation) |
| 102 | `backfill_thumbnails` |
| 110 | `seed` (session-scoped, prevents concurrent seed operations) |

Every command is idempotent, supports `--dry-run`, and logs via `logger` (no
`print`). The scheduler service is gated by `profiles: ["scheduler"]` so it does not
start — and does not crash on missing commands — before the command modules exist.

### NGINX Hardening (Zone R8)

The production nginx configuration (`docker/nginx/nginx.conf`) implements:

- **Security headers (all responses):** `Strict-Transport-Security` (HSTS, production only), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`
- **Content-Security-Policy (Report-Only, Phase 1):** `Content-Security-Policy-Report-Only` is applied server-level so every response inherits it. Because nginx `add_header` inheritance drops inherited headers when a `location` block defines its own, it is re-declared in the `/static/` and `/protected-media/` blocks. The policy is content-appropriate (allows `script-src ... 'unsafe-inline'` and `style-src ... 'unsafe-inline'` to accommodate current templates). Report-Only mode means violations are collected but NOT enforced — zero rollout risk. Violation reports are POSTed to the Django endpoint at `/csp-report/` (`apps.core.views.csp_report`), which logs them for monitoring.
- **Phase 2 (deferred):** Refactor templates to eliminate `'unsafe-inline'`, then switch `Content-Security-Policy-Report-Only` to an enforcing `Content-Security-Policy` with a stricter, content-appropriate policy.
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
- **Moderation POST-only enforcement (Finding 01):** Moderation review views (`approve_ad`, `reject_ad`, `ban_user` in `apps/moderation/views/review.py`) enforce POST-only via Django's `@require_POST` decorator, preventing state changes via GET requests (CSRF protection). The `approve_ad` view was previously missing this guard; now all three mutation views enforce POST-only.