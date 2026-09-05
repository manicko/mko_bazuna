---
name: 01-entry-architecture
phase: entry-architecture
template: .ai/audit/templates/audit-findings.md
status: complete
validated: no
---

# Phase 01 Audit Findings — Entry Points & Process Architecture

**Executor:** audit-executor
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** no

**Scope:** Top-down structural survey of the dual-process Django system (web WSGI gunicorn + bot aiogram polling) sharing one PostgreSQL database via one Django project.

---

## Runtime Verification Evidence

| Check | Result | Notes |
|-------|--------|-------|
| R1 — Import verification (WSGI) | PASS | `import config.wsgi` succeeds with env vars; no import-time DB/network side effects |
| R1 — Import verification (bot) | PASS | `import telegram_bot.main` succeeds; `django.setup()` at main.py:11 precedes `from telegram_bot.middlewares` at main.py:15 |
| R3 — Linter (ruff) | PASS | `ruff check src/` → 0 errors |
| R3 — Type checker (basedpyright) | PASS | basedpyright on telegram_bot handlers → 0 errors, 0 warnings |
| R4 — Test suite | PASS | Core tests + bot tests pass (test_login, test_create_draft_ad, test_privacy, test_csp_report, test_migrations, test_advisory_lock_ids) |
| R5 — Migration guard | PARTIAL | Advisory lock ID 100 protects `migrate` inside `migrate_locked.main()`; post-migration steps in compose command run outside lock (see ENT-003) |

---

## Findings


### ENT-001: Reverse dependency � backend service/management layer imports from bot transport layer

| Field | Value |
|-------|-------|
| **ID** | ENT-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/users/services/deletion.py, src/backend/apps/core/management/commands/{delete_sweep,purge_deleted_ads,purge_rejected_ads,purge_failed_ads,consent_hard_delete,sweep_drafts}.py |
| **Classification** | mandatory |

**Description:** The backend service/core layer (low-level domain services and management commands) imports delete_photo from telegram_bot/services/media.py � the bot transport layer. The delete_photo function (media.py:85-123) is a generic filesystem utility using only settings.MEDIA_ROOT and os.remove � no Telegram-specific logic. Despite this, it lives inside the bot package and 7 production backend modules depend on it. This reverses the intended dependency direction: the entry/transport layer should be imported only by higher layers, never by the service/core layer. Phase spec dimension (d) requires: Entry imports only service/core, never the reverse.

**Evidence:**
- src/backend/apps/core/management/commands/delete_sweep.py:19 � from telegram_bot.services.media import delete_photo
- src/backend/apps/users/services/deletion.py:32 � from telegram_bot.services.media import delete_photo
Seven production modules import delete_photo from telegram_bot.services.media:
- apps/users/services/deletion.py
- apps/core/management/commands/delete_sweep.py
- apps/core/management/commands/purge_deleted_ads.py
- apps/core/management/commands/purge_rejected_ads.py
- apps/core/management/commands/purge_failed_ads.py
- apps/core/management/commands/consent_hard_delete.py
- apps/core/management/commands/sweep_drafts.py
The function delete_photo (telegram_bot/services/media.py:85-123) performs os.path.join(settings.MEDIA_ROOT, storage_key) then os.remove(path). No Telegram imports, no bot-specific behavior.

**Recommendation:** Move delete_photo (and ideally the entire media filesystem utility surface) into a shared backend service module such as apps/media/services/filesystem.py or apps/core/services/media.py. Update all 7 import sites to reference the new location. This eliminates the reversed dependency, making the backend service layer independent of the bot transport layer. Effort: small. Priority: recommended.

---

### ENT-002: Scheduler process (prod compose) does not depend on migration completion

| Field | Value |
|-------|-------|
| **ID** | ENT-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker-compose.prod.yml (scheduler service), docker/entrypoint-scheduler.sh |
| **Classification** | mandatory |

**Description:** The scheduler service in docker-compose.prod.yml depends only on db (service_healthy) and redis (service_healthy) � NOT on the migrate or load_catalog one-shot services. The scheduler runs hourly management commands (archive_sweep, delete_sweep, consent_hard_delete, sweep_drafts, cleanup_login_tokens, purge_failed_ads, purge_rejected_ads, purge_deleted_ads) that all touch the database. If the scheduler container starts before migrations are applied (e.g., fresh deployment, cold start, or DB restore), these commands will fail with table-does-not-exist errors. The web and bot services correctly depend on load_catalog which depends on migrate (service_completed_successfully); the scheduler omits this dependency entirely.

**Evidence:**
- docker-compose.prod.yml:44-45 � scheduler depends_on: db (service_healthy), redis (service_healthy)
- docker-compose.prod.yml:36-37 � web depends_on: load_catalog (service_completed_successfully)
- docker-compose.prod.yml:56-58 � bot (base compose) depends_on: load_catalog (service_completed_successfully)
- docker-compose.yml:36-38 � migrate service: depends_on db (service_healthy)
- docker-compose.yml:61-62 � load_catalog depends_on: migrate (service_completed_successfully)
- entrypoint-scheduler.sh:47-65 � scheduler runs archive_sweep, delete_sweep, etc. via subprocess.run on hourly loop
- The scheduler is a NEW long-lived process in prod (docker-compose.prod.yml:100) not mentioned in the architecture doc's two-process model

**Recommendation:** Add depends_on: load_catalog (condition: service_completed_successfully) to the scheduler service in both docker-compose.yml and docker-compose.prod.yml, matching the dependency chain used by web and bot. This ensures the scheduler cannot start until schema migrations and catalog loading are complete. Effort: trivial. Priority: recommended.

---

### ENT-003: Post-migration setup commands run outside advisory lock

| Field | Value |
|-------|-------|
| **ID** | ENT-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker-compose.yml (migrate service, line 35), src/backend/apps/core/utils/migrate_locked.py |
| **Classification** | mandatory |

**Description:** The migrate one-shot service in docker-compose.yml:35 chains three operations with &&: (1) migrate_locked.main() which acquires session-scoped advisory lock ID 100 (src/backend/apps/core/utils/migrate_locked.py:33), (2) setup_search_triggers, and (3) load_exchange_rates. Only the first step is protected by the advisory lock. After main() returns, the lock is released (advisory_lock context manager:61-62), and the two subsequent commands execute unlocked. If two migrate containers start concurrently (e.g., container restart race or orchestration retry), the lock serializes the migrate step, but both containers then run setup_search_triggers and load_exchange_rates in parallel without coordination. This violates the phase spec (b) Migration-Once Guarantee: Advisory lock held � the lock does not cover the full one-shot setup sequence.

**Evidence:**
- docker-compose.yml:35 � command chains: migrate_locked.main() && manage.py setup_search_triggers && manage.py load_exchange_rates
- src/backend/apps/core/utils/migrate_locked.py:33 � with advisory_lock(AdvisoryLockId.MIGRATE, session=True): only wraps subprocess.run([manage.py, migrate])
- src/backend/apps/core/utils/advisory_lock.py:56-62 � session-scoped lock released in finally after yield returns; lock exits before setup_search_triggers runs
- setup_search_triggers (apps/ads/management/commands/setup_search_triggers.py:114) uses CREATE OR REPLACE FUNCTION + DROP IF EXISTS � idempotent but not concurrency-safe for DDL
- load_exchange_rates (apps/currencies/) updates ExchangeRate rows without advisory lock

**Recommendation:** Wrap the entire three-step sequence (migrate + setup_search_triggers + load_exchange_rates) inside the advisory lock in a single Python entrypoint, rather than chaining with && in the shell command. Alternatively, move setup_search_triggers and load_exchange_rates into migrate_locked.main() so they execute within the with advisory_lock(...) block. Effort: small. Priority: recommended.

---

### ENT-004: No graceful shutdown handler for bot process � no Django ORM cleanup on SIGTERM

| Field | Value |
|-------|-------|
| **ID** | ENT-004 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/main.py |
| **Classification** | mandatory |

**Description:** The bot entrypoint (telegram_bot/main.py:65) calls dp.run_polling(bot) with no on_startup or on_shutdown callbacks registered. While aiogram 3.x's run_polling internally installs SIGTERM/SIGINT handlers that stop polling and close the Bot HTTP session, there is no Django-specific cleanup: no close_old_connections() or connections.close() registered for shutdown. The bot performs ORM operations via sync_to_async (verified: all .objects. calls in handlers are wrapped in @sync_to_async). With CONN_MAX_AGE=0 (Django default when DATABASE_URL path in base.py:172-175 doesn't set it), connections close after each query, so no persistent leak. However, pending sync_to_async DB transactions in the thread pool are not drained during the shutdown window � a SIGTERM arriving mid-transaction interrupts the worker thread, relying entirely on PostgreSQL/Django rollback behavior rather than an explicit drain. The phase spec dimension (f) requires: Graceful shutdown � both processes handle interrupt/signal and release resources.

**Evidence:**
- src/telegram_bot/main.py:65 � dp.run_polling(bot) with no on_shutdown registration
- src/telegram_bot/main.py:39-43 � Dispatcher(storage=MemoryStorage()) with no startup/shutdown hooks
- src/backend/config/settings/base.py:172-175 � DATABASE_URL path sets OPTIONS prepare_threshold but no CONN_MAX_AGE (defaults to 0)
- No signal handlers or on_shutdown callbacks found in telegram_bot/ (grep for on_shutdown, signal_handler, SIGTERM: 0 results in production code)
- aiogram 3.x run_polling does handle signals internally (closes Bot session) but does not call Django cleanup

**Recommendation:** Register an on_shutdown callback via dp.shutdown.register or wrap run_polling with explicit Django cleanup: call django.db.connections.close_all() and close_old_connections() on shutdown. Consider adding a graceful shutdown timeout so in-flight sync_to_async operations complete before the process exits. Effort: small. Priority: recommended.

---

### ENT-005: Bot Docker healthcheck only verifies PID liveness, not readiness

| Field | Value |
|-------|-------|
| **ID** | ENT-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | docker-compose.yml (bot healthcheck, line 190) |
| **Classification** | advisory |

**Description:** The bot container healthcheck in docker-compose.yml:189-194 is kill -0 1 � a pure process-liveness check that only verifies PID 1 is still running. It does not verify that the bot has successfully connected to Telegram, that the Django ORM is functional, or that polling is actually receiving updates. A bot stuck in a retry loop, a zombie process, or a bot whose polling failed silently would pass this healthcheck. The web process has a proper HTTP healthcheck (Dockerfile:154-155) that curls /health/ which performs a SELECT 1 against PostgreSQL (apps/core/views.py:43-50). The bot has no equivalent readiness probe. Phase spec R2 requires: DB connectivity check precedes request/handler handling; the bot's entrypoint (docker/entrypoint.sh:90-91) does wait_for_db before starting, but the runtime healthcheck provides no ongoing readiness verification.

**Evidence:**
- docker-compose.yml:189-194 � healthcheck test: kill -0 1 (PID liveness only)
- docker/entrypoint.sh:33-49 � wait_for_db runs psutil/psycopg.connect before exec (boot-time check only)
- Dockerfile:154-155 � web HEALTHCHECK curls /health/ (HTTP endpoint with DB check)
- src/backend/apps/core/views.py:35-50 � health() does SELECT 1 via connection.cursor()
- No bot-side HTTP health endpoint or DB connectivity check in healthcheck

**Recommendation:** Replace the kill -0 healthcheck with a readiness probe that verifies the bot process is actually polling. Since the bot is a Telegram long-polling client (not an HTTP server), a practical approach is a wrapper script that checks the bot process is alive AND that it has recently received Telegram updates (e.g., via a heartbeat log line or a file-based liveness marker updated by an on_startup/on_shutdown callback). Alternatively, use webhooks instead of polling and expose an HTTP health endpoint. Effort: medium. Priority: recommended.

---

### ENT-006: Empty telegram_bot/bot/ directory tree � orphan package structure

| Field | Value |
|-------|-------|
| **ID** | ENT-006 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/bot/ (filters, handlers, states subdirs) |
| **Classification** | advisory |

**Description:** The directory tree src/telegram_bot/bot/ contains three empty subdirectories (filters/, handlers/, states/) with no files � not even __init__.py. These are not importable Python packages (no __init__.py) and contain zero code. The actual bot handlers live in telegram_bot/handlers/ (top-level), middleware in telegram_bot/middlewares/, and states in telegram_bot/states.py. This empty bot/ subtree is dead structure that can mislead future developers into thinking there is an alternative handler registration path at telegram_bot.bot.handlers (mirroring the real telegram_bot/handlers/), causing confusion about where bot logic actually resides. Phase spec Dead-Code / Orphan-Entry Detection requires reporting entry branches with no wiring.

**Evidence:**
- src/telegram_bot/bot/ exists (created 2026-01-23) with subdirs: filters/, handlers/, states/
- All three subdirectories are completely empty (no __init__.py, no .py files)
- telegram_bot/handlers/__init__.py:3-7 � routers registered from .login, .ad_create, .alerts, .ad_copy, .language
- telegram_bot/main.py:46-58 � dp.include_router() registers from telegram_bot/handlers/ (not bot/handlers/)
- telegram_bot/states.py � exists at top level, not in bot/states/

**Recommendation:** Remove the empty telegram_bot/bot/filters/, telegram_bot/bot/handlers/, and telegram_bot/bot/ directories. If this tree was scaffolding for a planned refactor, document its intended purpose. Effort: trivial. Priority: recommended.

---

### ENT-007: Business logic embedded in web entry views - unsynchronized analytics side-effects

| Field | Value |
|-------|-------|
| **ID** | ENT-007 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/ads/views/listings.py (ad_detail, media_gate), src/backend/apps/search/views/search.py |
| **Classification** | advisory |

**Description:** Web entry-layer views contain domain/business logic that belongs in the service/core layer per phase spec dimension (c) Entry-Handler Thinness: No business logic in entry - No domain rules/sanitization/statey logic in views/handlers. Specifically:

1. apps/ads/views/listings.py:69-73 - ad_detail() calls AnalyticsEvent.objects.create() inline (AD_VIEWED event). This is an unsynchronized side-effect: not wrapped in try/except, so a DB error during analytics recording causes the entire ad detail page to return HTTP 500. The spec check (c) lists: No ORM loops in entry - No query loops or bulk persistence in the entry layer. Creating a DB record in a view is persistence-in-entry.

2. apps/ads/views/listings.py:80-85 - Feature adequacy validation (filtering ad.features by resolved slugs) is performed inline in the view rather than delegated to a service. While CategoryLookupResolver.get_resolved_feature_codes is called (delegated), the filtering and display-feature assembly remain in the view.

3. apps/search/views/search.py (367 lines) - The search() function contains extensive orchestration logic: per-language FTS vector selection, category subtree filtering, price-range parsing, fuzzy category detection (get_close_matches, line 13), pagination, and inline AnalyticsEvent recording. While some logic is delegated to services (CategoryLookupResolver, suggest_city, increment_popular_search, record_search_history), the bulk of the control flow remains in the view function.

**Evidence:**
- src/backend/apps/ads/views/listings.py:69-73 - AnalyticsEvent.objects.create(event_type=AD_VIEWED, ...) with no try/except
- src/backend/apps/ads/views/listings.py:80-85 - feature filtering inline: [f for f in ad.features.all() if f.slug in resolved_feature_slugs]
- src/backend/apps/search/views/search.py:37-367 - single 367-line search() function with mixed concerns
- src/backend/apps/search/views/search.py:10-31 - imports from 6 service modules showing partial delegation but still 367 lines of inline orchestration
- Phase spec (c): Thin handlers - Entry handlers parse -> delegate -> respond only

**Recommendation:** Extract the analytics-event recording from ad_detail/search into a dedicated service call (e.g., apps/analytics/services/record_event.py) wrapped in its own try/except so analytics failures never break the primary view. Move feature-filtering logic into a service function (e.g., apps/ads/services/ad_display.py). Split the 367-line search() view by extracting query-building and filter-parsing logic into apps/search/services/. Effort: medium. Priority: recommended.

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | - |
| HIGH | 1 | ENT-001 |
| MEDIUM | 3 | ENT-002, ENT-003, ENT-007 |
| LOW | 3 | ENT-004, ENT-005, ENT-006 |
| **Total** | **7** | |

### Mandatory Fixes

- **ENT-001 (HIGH):** Move delete_photo from telegram_bot.services.media to a backend shared service module (apps/media/services/); update 7 import sites in apps/core/management/commands/ and apps/users/services/.
- **ENT-002 (MEDIUM):** Add depends_on: load_catalog (service_completed_successfully) to the scheduler service in docker-compose.yml and docker-compose.prod.yml.
- **ENT-003 (MEDIUM):** Move setup_search_triggers and load_exchange_rates inside the advisory lock in migrate_locked.main() or a single Python entrypoint; remove the shell && chain.

### Advisory Recommendations

- **ENT-004 (LOW):** Register on_shutdown callback in bot main.py to call django.db.connections.close_all() and drain sync_to_async operations before exit.
- **ENT-005 (LOW):** Replace bot healthcheck kill -0 with a readiness probe (heartbeat file, webhook mode, or HTTP wrapper).
- **ENT-006 (LOW):** Remove empty telegram_bot/bot/{filters,handlers,states}/ directories.
- **ENT-007 (MEDIUM):** Extract analytics recording and feature validation from web views into service-layer functions; split the 367-line search() view.

### Runtime Verification Status

| Check | Status |
|-------|--------|
| R1 - Import verification (WSGI + bot) | PASS |
| R2 - Process boot test | N/A (Docker runtime; entrypoint.sh verified statically) |
| R3 - Linter + type checker | PASS |
| R4 - Test suite | PASS (core + bot subsets) |
| R5 - Migration guard verification | PARTIAL (lock covers migrate only; ENT-003) |
| R6 - Process isolation | PASS (FSM in MemoryStorage; durable state in Ad DRAFT rows) |
