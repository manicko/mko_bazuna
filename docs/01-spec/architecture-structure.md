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
│   ├── config/                    # settings/ package (base, dev, test, prod, oneshot, secret_validation), urls.py, asgi.py, wsgi.py
│   ├── apps/                      # INSTALLED_APPS = ['apps.xxx']
│   │   ├── core/                  # shared utils, abstract models, managers, signals
│   │   │   ├── management/commands/  # sweep commands (archive, delete, consent, drafts, tokens, purge)
│   │   │   ├── middleware/           # city resolution + locale + preferred city (CityResolutionMiddleware, LanguagePreMiddleware, PreferredCityMiddleware)
│   │   │   ├── migrations/
│   │   │   ├── services/             # contact, site_config, analytics (record_event — QLT-003), translation
│   │   │   ├── templatetags/         # contact_tags, localized_content, dict_tags (query_replace), telegram_tags (telegram_deep_link, rtl_obfuscate)
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
│   │   │   ├── services/             # submission (submit_ad, SubmitAdInput — QLT-001), images, copy_service
│   │   │   ├── tests/
│   │   │   ├── templatetags/
│   │   │   ├── views/                # dashboard, delete, edit, listings
│   │   │   ├── management/
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
│   │   │   ├── schemas.py            # AutocompleteSuggestion Pydantic DTO (replaces dict[str, Any] — QLT-002)
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
│   ├── lifecycle.py               # bot startup/shutdown hooks (writes liveness marker, drops pending updates, closes sessions)
│   ├── states.py                  # AdCreateState FSM states (aiogram 3.x)
│   ├── handlers/                  # aiogram 3.x handlers (login, ad_create, contact)
│   ├── schemas/                   # pydantic v2 DTOs for bot message payloads (rule 11)
│   ├── middlewares/               # LanguageMiddleware (per-user locale, FQ-001), AccountStateMiddleware, DatabaseConnectionMiddleware, UpdateIdDedupMiddleware
│   ├── services/                  # business logic (ad_data/ package — ORM helpers, media I/O, translation, feature helpers, keyboard builders (QLT-006); rate_limit.py)
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
| `CityResolutionMiddleware` | `apps/core/middleware/city_resolution.py` | Resolves `request.current_city` — the explicit URL-encoded city slug (`/city/<slug>/` path or `?city=` query) or `None`. Set before every view; drives the catalog header badge and the listing/search filter. No DB lookup; slugs passed through for view-level validation. |
| `PreferredCityMiddleware` | `apps/core/middleware/preferred_city.py` | Resolves `request.preferred_city` (effective city slug or `None`) as the default city filter. Priority: authenticated `User.preferred_city` FK (wins) → validated `preferred_city` cookie → `None`. Stale cookies deleted in `process_response`. Cookie name is the module constant `PREFERRED_CITY_COOKIE_NAME` (mirrors `LanguagePreMiddleware`, not a `StrEnum`). |
| `CategoryMiddleware` | `apps/core/middleware/` | Category context for listings (plan 16). |

Registration order: `CityResolutionMiddleware` runs **after** `AuthenticationMiddleware` and
**before** `PreferredCityMiddleware`, so views see `request.current_city` (the explicit URL
city) resolved before `request.preferred_city` (the persisted default). `PreferredCityMiddleware`
runs **after** `AuthenticationMiddleware` (it reads `request.user`). Writes never happen in
middleware — the cookie/DB is written only by `set_preferred_city` (`apps/search/views/preferred_city.py`),
whose persistence POST is now **awaited** client-side before navigation, and whose cookie
deletion mirrors `set_cookie` attributes (Secure/HttpOnly/SameSite=Lax on HTTPS).

### Context processors

| Processor | Module | Variables | Consumed by |
|---|---|---|---|
| `header_context` | `apps/core/context_processors.py` | `root_categories`, `preferred_city_display`, `cities`, `favorites_count`, `catalog_js_labels` | Catalog header (`header_catalog.html`) — Note: `bot_username` is **not** injected here; it is resolved at template-render time via the `telegram_deep_link` tag (`apps/core/templatetags/telegram_tags.py`) which calls `get_bot_username()` internally. See [contact-us.md](../01-spec/contact-us.md). |
| `consent_state` | `apps/users/context_processors.py` | `consent_shown`, `consent_analytics`, `consent_preferences` | Consent banner + script gating (11 templates) |
| `plausible_host` | `apps/core/context_processors.py` | `PLAUSIBLE_HOST` | Gated Plausible snippet (`{% if consent_analytics and PLAUSIBLE_HOST %}`) |
| `language` | `apps/core/context_processors.py` | `LANGUAGE_CODE` | All templates |
| `site_config` | `apps/core/context_processors.py` | `site_name` | Admin-edited brand name surfaced in page `<title>` tags, header/footer brand links, auth & privacy `blocktrans`, and the admin review page — replaces 22 hardcoded `"Mko Bazuna"` occurrences. See [db-schema.md](../02-database/db-schema.md#site_config). |

`favorites_count` is `None` for anonymous visitors (outline heart, no count); for
authenticated sellers it is their favorite count. The header heart badge refreshes via
the `favorite:toggled` custom event → `GET cabinet:favorites_count` (HTMX `outerHTML` swap);
see [ui-patterns.md](ui-patterns.md).

## Deployment (Docker, phase 1)

`docker-compose.yml` services:

| Service | Image / Command | Notes |
|---------|----------------|-------|
| `db` | `postgres:18-alpine` + volume + healthcheck (`pg_isready`) | — |
| `web` | Django + gunicorn (sync WSGI) from `docker/Dockerfile`; `gunicorn config.wsgi:application` | Gunicorn reads runtime settings from `gunicorn.conf.py` (auto-discovered at the project root, copied to `/app` in the image; CWD is `/app`). The `--bind 0.0.0.0:8000` flag and other server settings (workers, timeout, max_requests, graceful_timeout, loglevel, accesslog/errorlog, preload_app) now live in that file. Mounts `media_volume`; `env_file: .env`; `depends_on load_catalog` (completed successfully); port 8000 NOT published. |
| `bot` | Same image; `python -m telegram_bot.main` | Mounts `media_volume`; `depends_on load_catalog` (completed successfully); `restart: unless-stopped`. Dual liveness markers: file-based (`docker/healthcheck-bot.sh` checking PID + `/tmp/mko_bazuna_bot_alive` marker freshness via `BOT_HEALTH_STALE_SECONDS`, the primary bot alert) and Redis-based `bot:liveness` key (written by `LivenessMiddleware` in `telegram_bot/lifecycle.py`, read by the web `/health/ready/` readiness probe via `BOT_HEALTH_CHECK_ENABLED`, which defaults off so the Redis key is an informational/alert dimension rather than a web readiness gate by default). |
| `migrate` | Same image; one-shot migration | Runs `python src/backend/manage.py bootstrap_reference_data` — delegates to `migrate_locked.main`, which executes all three required steps (`migrate --run-syncdb`, `setup_search_triggers`, `load_exchange_rates`) plus an optional `backfill_translations` step (included when `RUN_TRANSLATION_BACKFILL=true`) inside a session-scoped advisory lock (ID 100). |
| `create_admin` | Same image; one-shot admin creation | Runs `entrypoint-create-admin.sh`; session-scoped advisory lock ID 101. Idempotent. |
| `seed` | Same image; one-shot demo data | Runs `entrypoint-seed.sh`; gated by `profiles: ["seed"]`. Populates DB with demo data. Session-scoped advisory lock ID 110. |
| `nginx` | `nginx:alpine`; ports 80/443 | Mounts `media_volume` (ro); `proxy_pass → web:8000`; serves `/media/`; TLS. Static files served via whitenoise proxy. |

Volumes: `postgres_data`, `media_volume`. Static files baked into image via whitenoise; nginx serves `/media/` only.

### Rules
- **nginx is REQUIRED in phase 1:** whitenoise does NOT serve user-uploaded media; local MEDIA_ROOT needs nginx. Plus TLS termination (HTTPS mandatory: login deep-link tokens, Secure cookies). Web service is not exposed.
- **Dockerfile:** `python:3.14-slim` + `uv` (pin `uv>=0.11.28`); non-root user; `RUN uv run python manage.py collectstatic --noinput`.
- **Django settings:** `USE_X_FORWARDED_HOST=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `SECURE_SSL_REDIRECT=True`.
- **/media/ security:** nginx blocks script execution (`location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`); `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`, default `application/octet-stream`, `Content-Disposition: inline`; media keys are UUID v4 (unguessable, non-sequential).
  - **`media_gate` cache security:** the Django `/media/<key>` view sets `Cache-Control: no-store` on 200 responses in production (`DEBUG=False`), so ad photos are never cached by browser or CDN; `Vary: Cookie` (via `@vary_on_headers`) ensures shared caches never merge auth-state-dependent responses; 403/404 carry no `Cache-Control`. Prevents stale cached photos of deleted/withdrawn ads after status transitions (spec §6/§7).
- **PgBouncer (recommended):** shared external pool in transaction mode between web+bot; each process holds `CONN_MAX_AGE=0`. With psycopg3 + PgBouncer tx mode set `OPTIONS={"prepare_threshold": None, "options": "-c lock_timeout=10s"}` — `prepare_threshold=None` for async safety, `options` for the connection-level lock bound (03-DB-004). **Prerequisite (two parts):** the `options` startup parameter is only *accepted* when the pooler lists it in `ignore_startup_parameters` (unprefixed `IGNORE_STARTUP_PARAMETERS=options,extra_float_digits` in `docker-compose.prod.yml` — the entrypoint reads the bare name, not `PGBOUNCER_*`), otherwise PgBouncer refuses every client. But listing it is not enough: the pooler then **discards** the whole `options` parameter, so pooled `SHOW lock_timeout` returns `0` (unbounded) and the bound is silently void; `track_extra_parameters` does not substitute on 1.25.2. The bound survives a pooler only via a **server-side** default (`ALTER DATABASE mko_bazuna SET lock_timeout = '10s'` / `postgresql.conf`), which is **not shipped here** — it is phase 12's decision. Enabling the profile before that default is in place is therefore **blocked**: it trades a loud refusal for silent unbounded lock waits. Latent today (the profile is not in the deployed path).
- **Migrations (zone C5/D7):** run exactly ONCE before web and bot start (dedicated step / ordering guard) so the two processes don't migrate concurrently. Domain writes (`ads`/`LoginToken`) go in ONE Django transaction.
- **Secrets:** `.env` (`BOT_TOKEN`, DB, `SECRET_KEY`) via `env_file: .env`. `API_ID`/`API_HASH` (MTProto/userbot) are NOT needed in phase 1 and removed from `.env`.

### Scheduler Configuration (Phase 4)

**Docker production mode:** Use `entrypoint-scheduler.sh` with the `scheduler` profile in `docker-compose.prod.yml`:

```bash
# Start scheduler alongside web and bot
# Scheduler runs all sweep commands hourly
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile scheduler up -d
```

The scheduler runs 9 hourly sweep commands (`archive_sweep`, `delete_sweep`,
`consent_hard_delete`, `sweep_drafts`, `sweep_orphaned_media`, `cleanup_login_tokens`,
`purge_failed_ads`, `purge_rejected_ads`, `purge_deleted_ads`) plus 3 daily commands
(`send_alerts`, `rollup_daily_metrics`, `purge_consent_records` — all fire at 08:00 UTC on the
first hourly tick at or after that hour) via the extracted module `apps.core.utils.scheduler`
(`python -m apps.core.utils.scheduler`), invoked by `entrypoint-scheduler.sh`.
The scheduler depends on `load_catalog` completing successfully (via `depends_on: condition: service_completed_successfully` in `docker-compose.yml`/`docker-compose.prod.yml`). Each dispatched command is bounded by `SCHEDULER_COMMAND_TIMEOUT` (default `1800s`); a command that times out is logged and skipped so the cycle continues (ENT-001).

The three daily commands are gated on a **durable** marker, not process memory. The date lives
in the `scheduler_daily_state` singleton (see `apps/core/services/scheduler_daily_state.py`
and [`db-schema`](../02-database/db-schema.md#scheduler_daily_state-singleton)); `run_scheduler` reads
it before the loop, and `run_one_cycle` writes it only when every daily command exits `0`
with no stop request. A restart does not re-fire the set, a failed set is retried on the
next tick, and the marker is **fail-open** (a marker problem causes a re-run, never a
silent skip). Because the marker is written **only when all three exit `0`**, each daily command's
exit code is load-bearing for the other two: `send_alerts` is not idempotent, so a daily command
that fails for a routine reason would re-run the alert delivery hourly. Every daily command
therefore returns `0` on all non-exceptional outcomes (`purge_consent_records` returns `0` for an
empty eligible set and for `--dry-run`).

**Systemd alternative (bare metal):**

```ini
# /etc/systemd/system/mko-bazuna-scheduler.service
[Unit]
Description=Mko Bazuna lifecycle sweep scheduler
After=postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/mko-bazuna/src/backend
# The scheduler loop lives in apps/core/utils/scheduler.py and is invoked via
# the module entry point, mirroring the Docker entrypoint-scheduler.sh.
ExecStart=/opt/venv/bin/python -m apps.core.utils.scheduler
# Graceful shutdown: the scheduler installs SIGTERM/SIGINT handlers that set a
# stop flag. The inter-cycle wait is interruptible (backed by the stop event), a
# stop during a cycle short-circuits the commands not yet started, and the
# in-flight command is never interrupted. The loop then breaks at its next
# top-of-loop check and closes Django DB connections in a finally teardown
# (ENT-002).
# systemd's default KillSignal=SIGTERM is therefore handled cleanly on stop.
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
20 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py sweep_orphaned_media
25 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py cleanup_login_tokens
30 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py purge_failed_ads
35 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py purge_rejected_ads
40 * * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py purge_deleted_ads
# Daily commands at 08:00 UTC
0 8  * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py send_alerts
5 8  * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py rollup_daily_metrics
10 8 * * * www-data cd /opt/mko-bazuna && /opt/venv/bin/python manage.py purge_consent_records
```

**Note (cron alternative):** the bare-metal `cron` block above fires all three daily commands
directly.
Under cron there is no scheduler marker in the loop, so a retried or manually re-invoked
`send_alerts` is protected only by `uq_saved_search_ad` plus `find_matching_ads`' `NOT EXISTS`
(it re-collects only pairs whose delivery receipt is still absent) but **not** by a run-level
marker. Do not invoke `send_alerts` more than once per day under cron.

**Alert dedup invariant (03-DB-007).** The daily `send_alerts` `NOT EXISTS` filters on
**delivered** state (`delivered_at IS NOT NULL`), not on row existence, so a failed digest is
retried on the next run rather than suppressed forever. The near-real-time publish-time path is
**separately gated** by `IMMEDIATE_ALERTS_ENABLED` and is deduplicated by the same delivery-state
contract: a pair delivered by either path is never delivered again by the other.

That contract is **sequential**, not concurrent: two paths racing on the same pair can both send
before either receipt commits. The duplicate is **detected, not prevented** —
`notification_delivery.mark_delivered` issues one conditional `UPDATE` in autocommit (no
`transaction.atomic()`, no advisory lock) and returns `False` when a competing call already
recorded the receipt. **`mark_delivered` returning `False` in production logs is the escalation
signal** that the concurrent case is real.

### Scheduled-job concurrency (advisory locks)

All nine hourly sweep commands (plus the two daily commands and the once-only `migrate`
step) — run against the same shared PostgreSQL database as the live web and bot
processes. To prevent concurrent sweeps (or a sweep and a migration) from colliding on
the same rows, every command acquires a PostgreSQL advisory lock
(`apps.core.utils.advisory_lock`) before doing its work. The default is
**transaction-scoped** (`pg_advisory_xact_lock`), released automatically on transaction
commit/rollback and therefore safe under PgBouncer transaction pooling.

**Two commands are the exception (03-DB-008).** `archive_sweep` and
`recompute_normalized_prices` commit **per batch** (500 rows), so a transaction-scoped
lock would be dropped by the first batch `COMMIT` and lose mutual exclusion between
batches. Both therefore take a **session-scoped** lock (`pg_advisory_lock`,
`session=True`) once for the whole run. That is **not** PgBouncer transaction-mode
safe, which is the second reason the `pgbouncer` profile is blocked — see
[`docker-deployment.md`](../ops/docker-deployment.md#lock-timeouts-canceling-statement-due-to-lock-timeout).
Every other sweep keeps the transaction-scoped shape.

The `migrate` step instead uses a **session-scoped** lock
(`pg_advisory_lock`, via `apps.core.utils.migrate_locked.main` running under `AdvisoryLockId.MIGRATE`)
because it runs before PgBouncer is attached. Inside that session lock, `migrate_locked`
runs all three required post-migration setup steps (plus an optional env-gated `backfill_translations`
step) as an atomic sequence: `migrate --run-syncdb`, `setup_search_triggers`, and `load_exchange_rates`
(replacing the previous `&&`-chained shell command that released the lock between steps).

Lock IDs are fixed and allocated centrally in the `AdvisoryLockId` IntEnum
(`apps.core.enums`) so they never collide:

| Lock ID | Held by |
|---------|---------|
| 1 | `archive_sweep` (session-scoped, per-batch commits) |
| 2 | `delete_sweep` |
| 3 | `consent_hard_delete` |
| 4 | `sweep_drafts` |
| 5 | `cleanup_login_tokens` |
| 6 | `purge_failed_ads` |
| 7 | `purge_rejected_ads` |
| 8 | `rollup_daily_metrics` |
| 9 | `alert_delivery_task` |
| 11 | `purge_deleted_ads` |
| 12 | `recompute_normalized_prices` (session-scoped, per-batch commits) |
| 13 | `repair_bot_username` (one-shot repair of `SiteConfig.bot_username`; see [`contact-us.md`](contact-us.md)) |
| 14 | `purge_consent_records` (daily `ConsentRecord` retention sweep — **anonymises, never deletes**; see [`db-retention.md`](../02-database/db-retention.md#purge_consent_records-06-pii-116)) |
| 100 | `migrate_locked.main` (session-scoped, runs migrate + setup_search_triggers + load_exchange_rates; optional `backfill_translations` when `RUN_TRANSLATION_BACKFILL=true`) |
| 101 | `create_admin_user` (session-scoped, for idempotent admin creation) |
| 102 | `backfill_thumbnails` |
| 103 | `sweep_orphaned_media` (hourly orphan-file reconciliation) |
| 104 | `catalog_load` (one-shot, gates web/bot startup) |
| 110 | `seed` (session-scoped, prevents concurrent seed operations) |
| 111 | `test_schema_setup` (xdist fixture, resets test DB) |

> **Note:** Lock ID 10 is intentionally unused/reserved; it was formerly `QUEUE_PROCESSING` and was removed in DB-007. **IDs below 100 are reserved for scheduled jobs** and IDs 15–99 remain free for future ones; take the next free id and re-read `src/backend/apps/core/enums.py` immediately before editing, because nothing in the suite catches an id collision across two phases.

Every command is idempotent, supports `--dry-run`, and logs via `logger` (no
`print`). The scheduler service is gated by `profiles: ["scheduler"]` so it does not
start — and does not crash on missing commands — before the command modules exist.

### NGINX Hardening (Zone R8)

The production nginx configuration (`docker/nginx/nginx.conf`) implements:

- **Security headers (all responses):** `Strict-Transport-Security` (HSTS, production only), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- **Content-Security-Policy (Report-Only, Phase 1):** `Content-Security-Policy-Report-Only` is applied server-level so every response inherits it. Because nginx `add_header` inheritance drops inherited headers when a `location` block defines its own, all security headers are re-declared in the `/static/` and `/protected-media/` blocks (including `Referrer-Policy` and `Permissions-Policy`). The policy is content-appropriate (allows `script-src ... 'unsafe-inline'` and `style-src ... 'unsafe-inline'` to accommodate current templates). Report-Only mode means violations are collected but NOT enforced — zero rollout risk. Violation reports are POSTed to the Django endpoint at `/csp-report/` (`apps.core.views.csp_report`), which logs them for monitoring.
- **Phase 2 (deferred):** Refactor templates to eliminate `'unsafe-inline'`, then switch `Content-Security-Policy-Report-Only` to an enforcing `Content-Security-Policy` with a stricter, content-appropriate policy.
- **Script execution blocked:** `location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }` in `/media/` location
- **MIME whitelist:** Only `image/jpeg` served for `/media/` uploads; default `application/octet-stream`
- **Media behavior:** `Content-Disposition: inline` for all media responses
- **Rate limiting:**
  - `/login/`: 10 req/s burst 20 (`login_limit` zone)
  - `/search/`: 20 req/s burst 40 (`search_limit` zone)
  - `/contact/` (deep-link page render, Spec 18): per-IP cap of 5 renders per 10 min — see [contact-us.md](../01-spec/contact-us.md#rate-limiting-dual-layer) for the full dual-layer table including bot-side limits.
  - **Bot-side** (`/start contact_us`): per-Telegram-user rate limit of 5 per 10 min via `check_contact_start_rate_limit` in `telegram_bot/services/rate_limit.py`; excess returns a cooldown message (Spec 18 CR-10).
  - **Bot-side** (photo upload): per-seller rate limit of 10 uploads per 60 s via `check_upload_rate_limit` in `telegram_bot/services/rate_limit.py`; excess returns a "Uploading too fast, please wait a moment." cooldown message.
- **TLS termination:** Certificates mounted at `/etc/nginx/certs/` (configurable via `TLS_CERT_PATH` env var). For local development with HTTPS, see [Local HTTPS with mkcert](../../ops/local-https-mkcert.md).

## Audit Zone References

Architecture-level audit zones resolved here (full reasoning distributed across the spec/DB docs):

- **C5 / C7** — async/sync boundary, per-process pool, PgBouncer, migrations run exactly once (see Migrations rule). Price index added only after EXPLAIN ANALYZE at 500k rows (see [db-indexes.md](../02-database/db-indexes.md)).
- **D7 / D9 / D10** — FSM has a separate migration owner; category cache is app-level; web is a sync WSGI process (see Source Structure).
- **R8** — `/media/` security (nosniff, whitelist `image/jpeg`, inline) and storage-key anonymity rules live in [db-schema.md](../02-database/db-schema.md).
- **Moderation POST-only enforcement (Finding 01):** Moderation review views (`approve_ad`, `reject_ad`, `ban_user` in `apps/moderation/views/review.py`) enforce POST-only via Django's `@require_POST` decorator, preventing state changes via GET requests (CSRF protection). The `approve_ad` view was previously missing this guard; now all three mutation views enforce POST-only. The same `@require_POST` guard was extended to ad state-change views — `ad_archive` and `ad_reactivate` (`apps/ads/views/edit.py`), and `ad_delete` (`apps/ads/views/delete.py`) — to prevent ad status/ownership mutations via GET requests.