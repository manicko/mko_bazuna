---
name: 01-entry-architecture
phase: entry-architecture
template: .ai/audit/templates/audit-findings.md
status: complete
validated: yes
validator: validator
validated_date: 2026-09-05
---

# Phase 01 Audit Findings — Entry Points & Process Architecture (Validated)

**Executor:** audit-executor
**Validator:** validator
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** yes

**Scope:** Top-down structural survey of the dual-process Django system (web WSGI gunicorn + bot aiogram polling) sharing one PostgreSQL database via one Django project.

This file is the self-contained validated report. The reader does not need to consult the original findings file (`.ai/audit/01-entry-architecture/findings.md`).

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

## Cross-Finding Analysis

### Dependency Chains

| Finding | Depends on | Depends on by | Notes |
|---------|-----------|---------------|-------|
| ENT-001 | — | ENT-007 (indirectly) | Both are layer-separation violations but with different root causes. ENT-001 is a dependency-direction reversal (backend imports bot); ENT-007 is logic-placement (view contains domain logic). Not merge candidates. |
| ENT-002 | — | — | Independent: compose-level ordering fix. |
| ENT-003 | — | — | Independent: advisory-lock scope fix. Related to ENT-002 by shared root theme (Migration-Once Guarantee) but different mechanisms (compose `depends_on` vs. lock scope). Not merge candidates. |
| ENT-004 | — | — | Independent: bot signal handler registration. |
| ENT-005 | — | — | Independent: bot healthcheck replacement. |
| ENT-006 | — | — | Independent: dead directory removal. |
| ENT-007 | — | — | Independent: view → service extraction. |

### Conflicts Detected

No cross-phase conflicts detected (single phase analyzed).

---

## Findings

### ENT-001: Reverse dependency — backend service/management layer imports from bot transport layer

| Field | Value |
|-------|-------|
| **ID** | ENT-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/users/services/deletion.py, src/backend/apps/core/management/commands/{delete_sweep,purge_deleted_ads,purge_rejected_ads,purge_failed_ads,consent_hard_delete,sweep_drafts}.py |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** The backend service/core layer (low-level domain services and management commands) imports delete_photo from telegram_bot/services/media.py — the bot transport layer. The delete_photo function (media.py:85-123) is a generic filesystem utility using only settings.MEDIA_ROOT and os.remove — no Telegram-specific logic. Despite this, it lives inside the bot package and 7 production backend modules depend on it. This reverses the intended dependency direction: the entry/transport layer should be imported only by higher layers, never by the service/core layer. Phase spec dimension (d) requires: Entry imports only service/core, never the reverse.

**Evidence:**
- src/backend/apps/core/management/commands/delete_sweep.py:19 — `from telegram_bot.services.media import delete_photo`
- src/backend/apps/users/services/deletion.py:32 — `from telegram_bot.services.media import delete_photo`
- Seven production modules import delete_photo from telegram_bot.services.media:
  - apps/users/services/deletion.py:32
  - apps/core/management/commands/delete_sweep.py:19
  - apps/core/management/commands/purge_deleted_ads.py:20
  - apps/core/management/commands/purge_failed_ads.py:18
  - apps/core/management/commands/purge_rejected_ads.py:19
  - apps/core/management/commands/consent_hard_delete.py:21
  - apps/core/management/commands/sweep_drafts.py:18
- The function delete_photo (telegram_bot/services/media.py:85-123) performs `os.path.join(settings.MEDIA_ROOT, storage_key)` then `os.remove(path)`. No Telegram imports, no bot-specific behavior. Top-level imports are `io, logging, time, uuid, PIL, os, django.conf.settings` — none Telegram-specific.

**Validator's Verification:**
- Grep for `from telegram_bot.services.media import` across `src/backend/` confirmed all 7 production import sites at the exact line numbers cited. Three additional test-only modules import `generate_storage_key` (not `delete_photo`) from the same module; these are test files, not production.
- Read media.py:85-123 confirms `delete_photo` uses only `os.path.join` + `os.remove`; no Telegram/aiogram imports in the module header.
- Read deletion.py:32 confirms the import and line 159 shows the call site within business logic.

**Evidence Quality:** High — all line references verified exact.

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
| **Validation Status** | **VALIDATED** |

**Description:** The scheduler service in docker-compose.prod.yml depends only on db (service_healthy) and redis (service_healthy) — NOT on the migrate or load_catalog one-shot services. The scheduler runs hourly management commands (archive_sweep, delete_sweep, consent_hard_delete, sweep_drafts, cleanup_login_tokens, purge_failed_ads, purge_rejected_ads, purge_deleted_ads) that all touch the database. If the scheduler container starts before migrations are applied (e.g., fresh deployment, cold start, or DB restore), these commands will fail with table-does-not-exist errors. The web and bot services correctly depend on load_catalog which depends on migrate (service_completed_successfully); the scheduler omits this dependency entirely.

**Evidence:**
- docker-compose.prod.yml:56-60 — scheduler depends_on: db (service_healthy), redis (service_healthy)
- docker-compose.yml:142-144 — web depends_on: load_catalog (service_completed_successfully)
- docker-compose.yml:169-171 — bot depends_on: load_catalog (service_completed_successfully)
- docker-compose.yml:36-38 — migrate service: depends_on db (service_healthy)
- docker-compose.yml:60-62 — load_catalog depends_on: migrate (service_completed_successfully)
- entrypoint-scheduler.sh:28-48 — scheduler runs archive_sweep, delete_sweep, etc. via subprocess.run on hourly loop
- The scheduler is a long-lived process in prod (docker-compose.prod.yml:38) not covered by the architecture doc's two-process model

**Validator's Verification:**
- Read docker-compose.prod.yml (full file): scheduler service at lines 38-63, `depends_on` at lines 56-60 lists only `db` (condition: service_healthy) and `redis` (condition: service_healthy). No migrate or load_catalog dependency.
- Read docker-compose.yml (full file): confirmed web (lines 142-144) and bot (lines 169-171) both depend on `load_catalog: condition: service_completed_successfully`. Confirmed no `scheduler` service exists in the base file.
- Read entrypoint-scheduler.sh: confirmed hourly loop (lines 44-48) runs 8 DB-touching commands via `subprocess.run(..., check=False)`.
- Cross-referenced spec: spec-index.md (lines 52-58) and architecture.md (line 20) describe a "two-process model" (web + bot) with "Migrations run exactly once before web+bot start." The scheduler is documented in architecture-structure.md (lines 217-299) as a "Phase 4" feature but is NOT included in the two-process migration-once guarantee. The scheduler is already implemented in docker-compose.prod.yml (gated by `profiles: ["scheduler"]`), making it a live long-lived process that bypasses the migrate guarantee.

**Evidence Quality Issues:**
- Line reference "docker-compose.prod.yml:100" in original evidence is stale — the scheduler service is at lines 38-63, not 100 (line 100 is in the pgbouncer service).
- The recommendation mentions adding the dependency to "both docker-compose.yml and docker-compose.prod.yml" — the scheduler service only exists in docker-compose.prod.yml, not the base docker-compose.yml.
- The claim "not mentioned in the architecture doc's two-process model" is accurate for the two-process framing (spec-index.md:52-55, architecture.md:20) but the scheduler IS documented separately in the spec as Phase 4 (architecture-structure.md:217). Nuance: the code is ahead of the two-process model.

**Recommendation:** Add `depends_on: load_catalog (condition: service_completed_successfully)` to the scheduler service in docker-compose.prod.yml, matching the dependency chain used by web and bot. This ensures the scheduler cannot start until schema migrations and catalog loading are complete. Effort: trivial. Priority: recommended.

---

### ENT-003: Post-migration setup commands run outside advisory lock

| Field | Value |
|-------|-------|
| **ID** | ENT-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker-compose.yml (migrate service, line 35), src/backend/apps/core/utils/migrate_locked.py |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** The migrate one-shot service in docker-compose.yml:35 chains three operations with `&&`: (1) migrate_locked.main() which acquires session-scoped advisory lock ID 100 (src/backend/apps/core/utils/migrate_locked.py:33), (2) setup_search_triggers, and (3) load_exchange_rates. Only the first step is protected by the advisory lock. After main() returns, the lock is released (advisory_lock context manager:56-62), and the two subsequent commands execute unlocked. If two migrate containers start concurrently (e.g., container restart race or orchestration retry), the lock serializes the migrate step, but both containers then run setup_search_triggers and load_exchange_rates in parallel without coordination. This violates the phase spec (b) Migration-Once Guarantee: Advisory lock held — the lock does not cover the full one-shot setup sequence.

**Evidence:**
- docker-compose.yml:35 — command chains: `migrate_locked.main()` && `manage.py setup_search_triggers` && `manage.py load_exchange_rates`
- src/backend/apps/core/utils/migrate_locked.py:33 — `with advisory_lock(AdvisoryLockId.MIGRATE, session=True):` only wraps `subprocess.run([manage.py, migrate])`
- src/backend/apps/core/utils/advisory_lock.py:56-62 — session-scoped lock released in finally after yield returns; lock exits before setup_search_triggers runs
- setup_search_triggers (apps/ads/management/commands/setup_search_triggers.py:114) uses CREATE OR REPLACE FUNCTION + DROP IF EXISTS — idempotent but not concurrency-safe for DDL
- load_exchange_rates (apps/currencies/management/commands/load_exchange_rates.py) updates ExchangeRate rows without advisory lock

**Validator's Verification:**
- Read docker-compose.yml line 35 (full migrate command): confirmed shell-chain of three `&&`-separated commands. `migrate_locked.main()` (Python entrypoint) wraps only `subprocess.run([sys.executable, str(manage_py), "migrate", "--noinput", "--run-syncdb"])` inside `with advisory_lock(AdvisoryLockId.MIGRATE, session=True):`.
- Read migrate_locked.py:33-37: confirmed the `with advisory_lock(...)` block contains only the migrate subprocess call. `main()` returns immediately after `return result.returncode`, exiting the `with` block and releasing the lock before control returns to the shell `&&`.
- Read advisory_lock.py:56-62: confirmed the session-scoped lock (`pg_advisory_lock` / `pg_advisory_unlock`) is released in the `finally` block (line 61) right after `yield` (line 59). The lock is held only for the duration of the `with` body.
- Read setup_search_triggers.py:1-131: confirmed `handle()` (line 114) executes raw DDL via `connection.cursor()` at lines 121-123. The SQL uses `CREATE OR REPLACE FUNCTION` (lines 35, 72) and `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER` (lines 83-86, 91-94). DDL in PostgreSQL implicitly commits; concurrent DDL can cause lock contention or catalog-state races.
- Confirmed `load_exchange_rates.py` exists at `apps/currencies/management/commands/load_exchange_rates.py`.

**Evidence Quality:** High — all code paths and line references verified exact.

**Recommendation:** Move `setup_search_triggers` and `load_exchange_rates` into `migrate_locked.main()` so all three one-shot setup steps run inside the single `with advisory_lock(AdvisoryLockId.MIGRATE, session=True):` block (Approach B — reuses the existing purpose-built locked runner; approach A of a new entrypoint would duplicate its lock logic). The two added steps MUST be invoked as `subprocess.run([sys.executable, str(manage_py), command])` mirroring the existing migrate subprocess, so the lock stays held by this parent process whose `connection.cursor()` session acquired `pg_advisory_lock(100)`; do NOT use `call_command()` in-process — with CONN_MAX_AGE=0, `close_old_connections()` can tear down the parent connection mid-block and release the session-scoped lock prematurely (the autocommit-release hazard documented in `advisory_lock.py`). Concrete changes: (1) `src/backend/apps/core/utils/migrate_locked.py` — replace the single migrate `subprocess.run` with a sequence that also runs `manage.py setup_search_triggers` and `manage.py load_exchange_rates` inside the lock, returning the first non-zero exit code (or 0); (2) `docker-compose.yml` migrate `command` (line 35) — collapse to `python -c 'from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())'`, dropping the `&& ... setup_search_triggers && ... load_exchange_rates` shell chain; (3) `docker/entrypoint-test.sh` lines 21-23 — leave unchanged (runs the same three steps in order with the lock unused; single-container test has no concurrency to guard). Effort: small. Priority: recommended.

---

### ENT-004: No graceful shutdown handler for bot process — no Django ORM cleanup on SIGTERM

| Field | Value |
|-------|-------|
| **ID** | ENT-004 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/main.py |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** The bot entrypoint (telegram_bot/main.py:65) calls dp.run_polling(bot) with no on_startup or on_shutdown callbacks registered. While aiogram 3.x's run_polling internally installs SIGTERM/SIGINT handlers that stop polling and close the Bot HTTP session, there is no Django-specific cleanup: no close_old_connections() or connections.close() registered for shutdown. The bot performs ORM operations via sync_to_async (verified: all .objects. calls in handlers are wrapped in @sync_to_async). With CONN_MAX_AGE=0 (Django default when DATABASE_URL path in base.py:172-175 doesn't set it), connections close after each query, so no persistent leak. However, pending sync_to_async DB transactions in the thread pool are not drained during the shutdown window — a SIGTERM arriving mid-transaction interrupts the worker thread, relying entirely on PostgreSQL/Django rollback behavior rather than an explicit drain. The phase spec dimension (f) requires: Graceful shutdown — both processes handle interrupt/signal and release resources.

**Evidence:**
- src/telegram_bot/main.py:65 — dp.run_polling(bot) with no on_shutdown registration
- src/telegram_bot/main.py:39-43 — Dispatcher(storage=MemoryStorage()) with no startup/shutdown hooks
- src/backend/config/settings/base.py:172-175 — DATABASE_URL path sets OPTIONS prepare_threshold but no CONN_MAX_AGE (defaults to 0)
- No signal handlers or on_shutdown callbacks found in telegram_bot/ (grep for on_shutdown, signal_handler, SIGTERM: 0 results in production code)
- aiogram 3.x run_polling does handle signals internally (closes Bot session) but does not call Django cleanup

**Validator's Verification:**
- Read main.py (full file, 69 lines): line 65 is `dp.run_polling(bot)`. No `on_shutdown` or `on_startup` registration anywhere. `Dispatcher(storage=MemoryStorage())` at line 40 has no signal hooks. No `dp.shutdown.register(...)` or similar.
- Grep for `on_shutdown|signal_handler|SIGTERM|on_startup|shutdown\.register|signals\.register` across `src/telegram_bot/` returned **zero matches** in production code.
- Read base.py:169-191: in the `DATABASE_URL` branch (lines 170-175), `DATABASES = {"default": env.db()}` is called without setting `CONN_MAX_AGE`, so it defaults to Django's default of 0. The `else` branch (line 186) explicitly sets `CONN_MAX_AGE: 0`. Read prod.py (full file, 51 lines): no `CONN_MAX_AGE` override. Confirmed CONN_MAX_AGE=0 in all deployment configurations.
- Grep for `@sync_to_async|\.objects\.|close_old_connections|connections\.close` across `src/telegram_bot/` confirmed: all `.objects.` calls in production handlers (login.py, language.py, alerts.py, ad_create.py, contact.py, permissions.py) are wrapped in `@sync_to_async`. The only `connections.close_all()` reference is in test code (tests/conftest.py:213), not production main.py.

**Evidence Quality:** High — all claims verified against source. Line references accurate.

**Recommendation:** Register a shutdown callback via `dp.shutdown.register` (Approach A — the canonical aiogram 3.x API; wrapping `run_polling` — approach B — is unnecessary and duplicates built-in behavior). Verified from the aiogram 3.x source: `run_polling(handle_signals=True)` (the default at main.py:65) already installs SIGTERM/SIGINT handlers that set the stop signal, then in `start_polling`'s `finally` block call `emit_shutdown()` (firing all registered `dp.shutdown` callbacks) followed by `bot.session.close()` — so wrapping `run_polling` adds nothing and is not the supported hook surface. Concrete changes in `src/telegram_bot/main.py`: (1) add `from django.db import connections, close_old_connections` at the top-level import block (after the aiogram imports at lines 13-16); (2) add `async def _on_shutdown(*args: object, **kwargs: object) -> None:` calling `connections.close_all()` then `close_old_connections()`; (3) register it before `dp.run_polling(bot)` at line 65 as `dp.shutdown.register(_on_shutdown)`. A graceful shutdown timeout should NOT be added: the verified aiogram 3.x API exposes no drain-timeout parameter (`close_bot_session_timeout` does not exist; the only related flag is the boolean `close_bot_session=True`), and with CONN_MAX_AGE=0 (explicit in base.py:186 else-branch; no override in prod.py:51/dev.py:44 so Django defaults to 0) every DB query opens and closes its own connection — there is no persistent connection to leak, and in-flight `sync_to_async` DB work is short and atomic (`transaction.atomic()` in login.py:166 and 174), so PostgreSQL rolls back any interrupted transaction and data integrity is preserved. Rely on aiogram's built-in signal handling + bot session close, and on docker-compose `restart: unless-stopped` for process recovery. Effort: small. Priority: recommended.

---

### ENT-005: Bot Docker healthcheck only verifies PID liveness, not readiness

| Field | Value |
|-------|-------|
| **ID** | ENT-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | docker-compose.yml (bot healthcheck, line 189) |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Description:** The bot container healthcheck in docker-compose.yml:189-194 is `kill -0 1` — a pure process-liveness check that only verifies PID 1 is still running. It does not verify that the bot has successfully connected to Telegram, that the Django ORM is functional, or that polling is actually receiving updates. A bot stuck in a retry loop, a zombie process, or a bot whose polling failed silently would pass this healthcheck. The web process has a proper HTTP healthcheck (Dockerfile:154-155) that curls /health/ which performs a SELECT 1 against PostgreSQL (apps/core/views.py:43-50). The bot has no equivalent readiness probe. Phase spec R2 requires: DB connectivity check precedes request/handler handling; the bot's entrypoint (docker/entrypoint.sh:90-91) does wait_for_db before starting, but the runtime healthcheck provides no ongoing readiness verification.

**Evidence:**
- docker-compose.yml:189-194 — healthcheck test: `kill -0 1 2>/dev/null || exit 1`
- docker/entrypoint.sh:33-49 — wait_for_db runs psycopg.connect before exec (boot-time check only)
- Dockerfile:154-155 — web HEALTHCHECK curls `/health/` (HTTP endpoint with DB check)
- src/backend/apps/core/views.py:35-50 — health_check() does SELECT 1 via connection.cursor()
- src/backend/apps/core/urls.py:9 — `path("health/", views.health_check, name="health")`
- No bot-side HTTP health endpoint or DB connectivity check in healthcheck

**Validator's Verification:**
- Read docker-compose.yml lines 189-194: confirmed bot healthcheck is `kill -0 1 2>/dev/null || exit 1` (PID liveness only).
- Read Dockerfile lines 154-155: confirmed web HEALTHCHECK is `curl -f http://localhost:8000/health/ || exit 1`.
- Read apps/core/views.py:35-50: confirmed `health_check()` performs `connection.cursor()` + `cursor.execute("SELECT 1")` (lines 43-44), returning 503 if DB fails. Read apps/core/urls.py:9: confirmed URL route `"health/"` → `views.health_check` (note: the check uses path `health/` not `health_check`, but the view function is named `health_check`).
- Read entrypoint.sh:33-49: confirmed `wait_for_db()` (lines 33-49) runs `psycopg.connect('$DATABASE_URL')` at boot time only — no ongoing readiness check in the Docker healthcheck.
- Confirmed the bot runs `python -m telegram_bot.main` (docker-compose.yml:168) which does not serve HTTP. The bot inherits the Dockerfile HEALTHCHECK (curl to port 8000) but docker-compose.yml overrides it with the PID-only check because the bot has no HTTP server.

**Evidence Quality Issues:**
- The original evidence references "docker/entrypoint.sh:90-91" for wait_for_db — the actual `wait_for_db` call in entrypoint.sh is at line 90 (within the `if [ "${BASH_SOURCE[0]}" = "$0" ]` block at line 87, `wait_for_db` is called at line 90). This is accurate.

**Recommendation:** Adopt Approach A (file-based liveness marker) and reject Approach B (webhooks). Verification confirms the bot is a pure long-polling client: `dp.run_polling(bot)` at main.py:65, and a recursive grep for `set_webhook|webhook|WEBHOOK|Webhook` across `src/` returns zero matches — this matches the documented two-process model in architecture.md (line 20: "Two processes, one DB: Web gunicorn WSGI + Telegram bot ... Migrations run exactly once before web+bot start," with the bot as a polling client). Switching to webhooks would require adding an HTTP server to the bot, configuring a public HTTPS URL + `bot.set_webhook()`, and nginx routing — a disproportionate architectural change that breaks the established polling model. Concrete changes for Approach A: (1) `src/telegram_bot/main.py` — register `dp.startup.register(_on_startup)` (the callback already logs "Bot starting with FSM…" at line 63) to write a timestamped marker file at `settings.BOT_LIVENESS_FILE` (new setting defaulting to `/tmp/mko_bazuna_bot_alive`) once `run_polling` enters its loop; this fires only after `Bot(token)` succeeds and the dispatcher is wired, so a missing marker after `start_period` means the bot never reached a polling state (bad token / startup crash); (2) register `dp.shutdown.register(_on_shutdown)` (the same shutdown callback recommended in ENT-004) to remove the marker on graceful exit; (3) add a `TelegramMiddleware` registered via `dp.message.middleware(...)` (mirroring `AccountStateMiddleware` at main.py:43) that `touch`-updates the marker file mtime on each received update, yielding a "last update received" freshness signal for retry-loop detection; (4) `docker-compose.yml` bot `healthcheck` (lines 189-194) — replace `kill -0 1` with `/app/docker/healthcheck-bot.sh` that: (a) `kill -0 1` (process liveness), (b) `[ -f "$BOT_LIVENESS_FILE" ]` (readiness: bot reached polling), and (c) when `BOT_HEALTH_STALE_SECONDS` is set, verify the marker mtime is within that window to flag a bot stuck in a Telegram retry loop. The freshness check is opt-in (unset => existence-only) to avoid false-negatives on a healthy but idle bot that legitimately receives no messages for hours. Effort: medium. Priority: recommended.

---

### ENT-006: Empty telegram_bot/bot/ directory tree — orphan package structure

| Field | Value |
|-------|-------|
| **ID** | ENT-006 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/bot/ (filters, handlers, states subdirs) |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Description:** The directory tree src/telegram_bot/bot/ contains three empty subdirectories (filters/, handlers/, states/) with no files — not even __init__.py. These are not importable Python packages (no __init__.py) and contain zero code. The actual bot handlers live in telegram_bot/handlers/ (top-level), middleware in telegram_bot/middlewares/, and states in telegram_bot/states.py. This empty bot/ subtree is dead structure that can mislead future developers into thinking there is an alternative handler registration path at telegram_bot.bot.handlers (mirroring the real telegram_bot/handlers/), causing confusion about where bot logic actually resides. Phase spec Dead-Code / Orphan-Entry Detection requires reporting entry branches with no wiring.

**Evidence:**
- src/telegram_bot/bot/ exists (created 2026-01-23) with subdirs: filters/, handlers/, states/
- All three subdirectories are completely empty (no __init__.py, no .py files)
- telegram_bot/handlers/__init__.py:3-7 — routers registered from .login, .ad_create, .alerts, .ad_copy, .language
- telegram_bot/main.py:46-58 — dp.include_router() registers from telegram_bot/handlers/ (not bot/handlers/)
- telegram_bot/states.py — exists at top level, not in bot/states/

**Validator's Verification:**
- Filesystem `Get-ChildItem -Recurse` on `src/telegram_bot/bot/filters`, `src/telegram_bot/bot/handlers`, and `src/telegram_bot/bot/states` returned **no output** — all three directories are completely empty (zero files, zero subdirectories, no `__init__.py`).
- Read main.py:46-58: confirmed `dp.include_router()` registers routers from `telegram_bot/handlers/` (top-level imports: login_router, ad_create_router, alerts_router, ad_copy_router, language_router). No import from `telegram_bot.bot.handlers`.
- Confirmed `telegram_bot/states.py` exists at the top level (not inside `bot/`).

**Evidence Quality:** High — directory emptiness verified via filesystem enumeration.

**Recommendation:** Remove the empty telegram_bot/bot/filters/, telegram_bot/bot/handlers/, and telegram_bot/bot/ directories. If this tree was scaffolding for a planned refactor, document its intended purpose. Effort: trivial. Priority: recommended.

---

### ENT-007: Business logic embedded in web entry views — unsynchronized analytics side-effects

| Field | Value |
|-------|-------|
| **ID** | ENT-007 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/ads/views/listings.py (ad_detail, media_gate), src/backend/apps/search/views/search.py |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** Web entry-layer views contain domain/business logic that belongs in the service/core layer per phase spec dimension (c) Entry-Handler Thinness: No business logic in entry — No domain rules/sanitization/statey logic in views/handlers. Specifically:

1. apps/ads/views/listings.py:69-73 — ad_detail() calls AnalyticsEvent.objects.create() inline (AD_VIEWED event). This is an unsynchronized side-effect: not wrapped in try/except, so a DB error during analytics recording causes the entire ad detail page to return HTTP 500. The spec check (c) lists: No ORM loops in entry — No query loops or bulk persistence in the entry layer. Creating a DB record in a view is persistence-in-entry.

2. apps/ads/views/listings.py:80-85 — Feature adequacy validation (filtering ad.features by resolved slugs) is performed inline in the view rather than delegated to a service. While CategoryLookupResolver.get_resolved_feature_codes is called (delegated), the filtering and display-feature assembly remain in the view.

3. apps/search/views/search.py (367 lines) — The search() function contains extensive orchestration logic: per-language FTS vector selection, category subtree filtering, price-range parsing, fuzzy category detection (get_close_matches, line 13), pagination, and inline AnalyticsEvent recording. While some logic is delegated to services (CategoryLookupResolver, suggest_city, increment_popular_search, record_search_history), the bulk of the control flow remains in the view function.

**Evidence:**
- src/backend/apps/ads/views/listings.py:69-73 — AnalyticsEvent.objects.create(event_type=AD_VIEWED, ...) with no try/except
- src/backend/apps/ads/views/listings.py:80-85 — feature filtering inline: `[f for f in ad.features.all() if f.slug in resolved_feature_slugs]`
- src/backend/apps/search/views/search.py:37-304 — search() function (267 lines) with mixed concerns; file total 367 lines
- src/backend/apps/search/views/search.py:230-233 — AnalyticsEvent.objects.create (SEARCH_PERFORMED) with no try/except, inline in the view
- src/backend/apps/search/views/search.py:10-31 — imports from service modules (sanitize, popular_search, search_history, lookup_resolution, city_suggestions) showing partial delegation
- Phase spec (c): Thin handlers — Entry handlers parse → delegate → respond only

**Validator's Verification:**
- Read listings.py:69-73: confirmed `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.AD_VIEWED, user_id=ad.user_id, ad_id=ad.id)` with no try/except wrapping. A DB error here raises uncaught, returning HTTP 500.
- Read listings.py:80-85: confirmed inline feature filtering `[f for f in ad.features.all() if f.slug in resolved_feature_slugs]` — the resolver is called (line 81) but the filtering/assembly is in the view.
- Read search.py (full file, 367 lines): confirmed the `search()` function spans lines 37-304 (267 lines of body). The file is 367 lines total (37 lines of docstring/imports/helpers before search() and 63 lines of helper functions after). The function contains FTS vector selection (lines 187-189), category subtree filtering (lines 69-78), price-range parsing (lines 95-120), fuzzy category detection (lines 192-193, using `_fuzzy_category_match` at line 324), pagination (lines 256-263), and inline AnalyticsEvent recording (lines 230-233, no try/except).
- Read search.py:230-233: confirmed `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.SEARCH_PERFORMED, ...)` inline with no try/except, inside the `if query:` block (line 183).
- Read search.py:10-31: confirmed imports from 5 service modules: `apps.core.utils.sanitize` (line 25), `apps.search.services.popular_search` (line 26), `apps.search.services.search_history` (line 27), `apps.categories.services.lookup_resolution` (line 28), `apps.locations.services.city_suggestions` (line 29). The finding cites "6 service modules" — actual count is 5 (minor discrepancy).

**Evidence Quality Issues:**
- The finding states "apps/search/views/search.py (367 lines) — The search() function contains extensive orchestration logic." The file is 367 lines total; the `search()` function itself spans lines 37-304 (267 lines). The "367-line" reference conflates file length with function length. The substance (extensive orchestration in the view) is correct.
- The finding cites "imports from 6 service modules" (search.py:10-31). Actual count is 5 service modules (minor discrepancy).

**Recommendation:** Extract the analytics-event recording from ad_detail/search into a dedicated service call (e.g., apps/analytics/services/record_event.py) wrapped in its own try/except so analytics failures never break the primary view. Move feature-filtering logic into a service function (e.g., apps/ads/services/ad_display.py). Split the search() view by extracting query-building and filter-parsing logic into apps/search/services/. Effort: medium. Priority: recommended.

---

## Cross-Finding Analysis — Rollout Safety

### Circular Dependencies
No circular dependencies detected. ENT-001 is a one-directional reversal (backend → bot) that can be resolved by moving the utility downward (into backend shared services) without creating new cycles.

### Hidden Dependency Chains
- **ENT-001 → ENT-007 (shared concern):** Both address layer separation. Moving `delete_photo` out of `telegram_bot/services/media.py` (ENT-001) would also affect the test files that import `generate_storage_key` from the same module. The fix for ENT-001 must update test imports alongside production imports.
- **ENT-002 → ENT-003 (shared theme):** Both concern the Migration-Once Guarantee. ENT-002 fixes compose-level ordering (scheduler waits for load_catalog); ENT-003 fixes lock scope (post-migration steps inside the lock). These are complementary fixes — applying both is strictly safer. Neither depends on the other's outcome.

### Unsafe Rollout Ordering
- **ENT-001 must precede any refactoring of `telegram_bot/services/media.py`.** If media.py is restructured before the 7 import sites are moved, those modules break. The fix is atomic: move the function, update all import sites in one deployment.
- **ENT-003 lock-scope change must be tested with concurrent `migrate` container starts** to verify the lock serializes all three steps, not just migrate.

### Fragile Insertion Points
- ENT-004's shutdown callback registration (aiogram `dp.shutdown.register`) is a stable, documented API — not fragile.
- ENT-005's healthcheck replacement depends on the bot's I/O model (polling vs. webhook). A heartbeat-file approach is the least invasive and avoids architectural coupling.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 7 | ENT-001, ENT-002, ENT-003, ENT-004, ENT-005, ENT-006, ENT-007 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Findings by Severity

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | - |
| HIGH | 1 | ENT-001 |
| MEDIUM | 3 | ENT-002, ENT-003, ENT-007 |
| LOW | 3 | ENT-004, ENT-005, ENT-006 |
| **Total** | **7** | |

### Evidence Quality Assessment

| ID | Evidence Quality | Notes |
|----|------------------|-------|
| ENT-001 | **High** | All 7 import sites + function source verified at exact line numbers. |
| ENT-002 | **Medium** | Core claim confirmed (scheduler missing `load_catalog` dep), but original line reference `:100` is stale (scheduler at line 38); scheduler exists only in prod compose, not base; scheduler is documented in spec as Phase 4 but excluded from the two-process migration guarantee. |
| ENT-003 | **High** | Full call chain verified: shell `&&` chain, migrate_locked.py lock scope, advisory_lock.py release semantics, setup_search_triggers DDL, load_exchange_rates existence. |
| ENT-004 | **High** | main.py, base.py, prod.py, and grep all confirmed. Supporting claim about sync_to_async verified (all production handler `.objects.` calls wrapped). CONN_MAX_AGE=0 confirmed in both settings branches. |
| ENT-005 | **High** | Healthcheck, Dockerfile, view, URL routing, and entrypoint all verified. Bot's lack of HTTP server confirmed (explains why PID-only check is used). |
| ENT-006 | **High** | Filesystem enumeration confirmed all three subdirectories are empty. |
| ENT-007 | **Medium** | Core claims verified (inline AnalyticsEvent without try/except, inline feature filtering, orchestration in view). Minor inaccuracies: "367-line search() function" conflates file length (367) with function length (267 lines, lines 37-304); "6 service modules" should be 5. |

### Rejected Findings

None.

### Merged Findings

None.

### Reclassified Findings

None.

---

## Rollout Recommendations (Priority Order)

1. **ENT-001 (HIGH) — Move `delete_photo` to backend shared services.** Atomic change: relocate function + update 7 production import sites + 3 test import sites. Eliminates dependency-direction violation. No runtime risk.
2. **ENT-003 (MEDIUM) — Extend advisory lock to cover all post-migration setup.** Move `setup_search_triggers` and `load_exchange_rates` inside the `advisory_lock` block in `migrate_locked.main()`. Complements ENT-002.
3. **ENT-002 (MEDIUM) — Add `load_catalog` dependency to scheduler.** Trivial compose change; must coordinate with ENT-003 so the scheduler starts after the full lock-protected setup sequence.
4. **ENT-007 (MEDIUM) — Extract view-domain logic to services.** Non-atomic: can be done incrementally (analytics → service first, then feature filtering, then search view splitting).
5. **ENT-004 (LOW) — Register bot shutdown cleanup.** Register `dp.shutdown.register` callback calling `connections.close_all()`. Low risk; complementary to aiogram's internal signal handling.
6. **ENT-005 (LOW) — Replace bot PID-only healthcheck.** Implement a file-based liveness-marker readiness probe (on_startup writes marker, on_shutdown removes it, middleware refreshes per update). Medium effort due to bot's non-HTTP, long-polling architecture.
7. **ENT-006 (LOW) — Remove empty `telegram_bot/bot/` tree.** Trivial; zero runtime risk.
