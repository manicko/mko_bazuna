# Fix Matrix — Phase 01: Entry Architecture

## Summary

This matrix consolidates the 7 findings from `.ai/audit/99-validation/01-entry-architecture-validated.md` into a single planning document: implementation actions, selected solutions, test requirements, documentation updates, test-only ripple effects, and a rollout ordering. Planning/documentation only — no implementation.

**Validated report:** `.ai/audit/99-validation/01-entry-architecture-validated.md`

---

## Per-Finding Breakdown

### ENT-001 — Media service misplaced: `telegram_bot/services/media.py` should belong to `apps/media`

**Selected solution:** Move `media.py` → `apps/media/services/filesystem.py`; update all importers.

**Implementation actions:**

| # | File | Action |
|---|------|--------|
| 1 | `src/backend/apps/media/services/filesystem.py` | **Create** — relocate contents of `media.py` (functions: `validate_jpeg_bytes`, `validate_photo`, `generate_storage_key`, `delete_photo`, `strip_photo_exif`) |
| 2 | `src/backend/apps/media/services/__init__.py` | **Update** — export all functions from `filesystem` module |
| 3 | `src/telegram_bot/services/__init__.py` | **Update** — remove `media` re-export (or replace with re-export from new location for transition period) |
| 4 | `src/telegram_bot/services/media.py` | **Delete** after all importers updated |
| 5 | `src/telegram_bot/handlers/ad_create.py` | **Update** — import from `apps.media.services.filesystem` (line 56-60, imports: `generate_storage_key`, `validate_photo`, `strip_photo_exif`, `delete_photo`) |
| 6 | `src/backend/apps/users/services/deletion.py` | **Update** — import `delete_photo` from `apps.media.services.filesystem` (line 32) |
| 7 | `src/backend/apps/core/management/commands/delete_sweep.py` | **Update** — import `delete_photo` (line 19) |
| 8 | `src/backend/apps/core/management/commands/consent_hard_delete.py` | **Update** — import `delete_photo` (line 21) |
| 9 | `src/backend/apps/core/management/commands/purge_deleted_ads.py` | **Update** — import `delete_photo` (line 20) |
| 10 | `src/backend/apps/core/management/commands/purge_rejected_ads.py` | **Update** — import `delete_photo` (line 19) |
| 11 | `src/backend/apps/core/management/commands/purge_failed_ads.py` | **Update** — import `delete_photo` (line 18) |
| 12 | `src/backend/apps/core/management/commands/sweep_drafts.py` | **Update** — import `delete_photo` (line 18) |
| 13 | `src/backend/apps/media/tests/test_media.py` | **Move** → `src/backend/apps/media/tests/test_filesystem.py` + update internal patch targets |
| 14 | `src/backend/apps/ads/tests/test_media_security.py` | **Update** — import from `apps.media.services.filesystem` (line 26) |
| 15 | `src/backend/apps/media/tests/test_thumbnail_integration.py` | **Update** — import from `apps.media.services.filesystem` (line 43) |
| 16 | `src/backend/apps/media/tests/test_backfill_thumbnails.py` | **Update** — import from `apps.media.services.filesystem` (line 29) |

**Tests required:**

| # | Test file | Action |
|---|-----------|--------|
| 1 | `src/telegram_bot/tests/test_media.py` → `src/backend/apps/media/tests/test_filesystem.py` | **Move** — update internal patch targets from `telegram_bot.services.media.*` to `apps.media.services.filesystem.*` (patches at lines 230, 239, 252, 255, 268, 271, 283, 286) |
| 2 | `src/backend/apps/media/tests/conftest.py` | **Verify** — check if fixtures needed for moved test (currently `telegram_bot/tests/conftest.py` provides `isolated_media_root`) |

**Monkeypatch-at-importer sites (NO CHANGE NEEDED — patches target importer namespace, not media.py):**

| # | Test file | Lines | Patched symbol | Rationale |
|---|-----------|-------|----------------|-----------|
| 1 | `src/backend/apps/core/tests/test_sweep_commands.py` | 554, 595 | `apps.core.management.commands.purge_deleted_ads.delete_photo` and `apps.core.management.commands.delete_sweep.delete_photo` | Patches `delete_photo` as imported into the *command module's namespace*. After moving `delete_photo` to `apps.media.services.filesystem`, the command module will import `delete_photo` from the new location. The patched name still exists in the importer module. **NO CHANGE needed.** |
| 2 | `src/backend/apps/users/tests/test_deletion.py` | 275, 334 | `apps.users.services.deletion.delete_photo` | Same pattern — patches `delete_photo` as imported into `deletion.py`'s namespace. **NO CHANGE needed.** |

**Docs required:**

| # | Doc file | Line/Section | Action |
|---|----------|--------------|--------|
| 1 | `docs/STRUCT.md` | line 59 | **Update** — `telegram_bot/services/media.py` → `apps/media/services/filesystem.py` |
| 2 | `docs/01-spec/architecture-structure.md` | line 136 | **Update** — media.py location |
| 3 | `docs/01-spec/technical-specification.md` | line 88 | **Update** — `delete_photo` reference |
| 4 | `docs/02-database/db-retention.md` | line 102 | **Update** — `delete_photo` module path |
| 5 | `docs/97-plans/phase-01-detailed.md` | line 206 | **Update** — media.py in bot tree → apps/media tree |
| 6 | `docs/97-plans/phase-01-detailed-testing.md` | line 17, line 323 | **Update** — `test_media.py` path + test location reference |
| 7 | `docs/97-plans/phase-02-detailed-plan-1.md` | line 140 | **Update** — media service location |

**Test-only ripple:** Moving `test_media.py` across the conftest boundary from `telegram_bot/tests/` to `apps/media/tests/` changes fixture availability. The test patches internal module references (`telegram_bot.services.media.settings`, `telegram_bot.services.media.os.remove`, `telegram_bot.services.media.time.sleep`) — these MUST be updated to `apps.media.services.filesystem.*` when the file is moved. The other monkeypatch targets in `test_sweep_commands.py` and `test_deletion.py` patch the *importer's namespace* (e.g., `apps.users.services.deletion.delete_photo`) and need NO changes — they will continue to work because the `delete_photo` name exists in the importer module regardless of its source.

---

### ENT-002 — Scheduler service missing `load_catalog` dependency in production

**Selected solution:** Add `load_catalog` and `migrate` to `depends_on` in scheduler service in `docker-compose.prod.yml`.

**Root cause analysis:** The scheduler service in `docker-compose.prod.yml` (lines 38-63) only declares `depends_on: db, redis`. It does NOT wait for `load_catalog` (which loads city/category data the scheduler's sweep commands may reference) or `migrate` (which creates tables). The base `docker-compose.yml` bot and web services properly depend on `load_catalog` (lines 88, 116, 143, 170), but the prod override of `scheduler` drops this dependency.

**Implementation actions:**

| # | File | Action |
|---|------|--------|
| 1 | `docker-compose.prod.yml` | **Update** — scheduler service (lines 56-60): add `load_catalog` and `migrate` to `depends_on` with `condition: service_completed_successfully` |

**Tests required:** None (infra/config change; no unit test needed).

**Docs required:**

| # | Doc file | Line/Section | Action |
|---|----------|--------------|--------|
| 1 | `docs/01-spec/architecture-structure.md` | ~lines 217-299 | **Update** — scheduler service definition |
| 2 | `docs/01-spec/architecture-structure.md` | ~lines 200-201 | **Update** — bot service / scheduler dependency notes |
| 3 | `docs/99-agent/architecture.md` | line 57 | **Update** — scheduler description |
| 4 | `docs/ops/docker-deployment.md` | lines 512-526 | **Update** — scheduler section |
| 5 | `docs/97-plans/phase-01-detailed-deployment.md` | line 62 | **Update** — scheduler dep reference |

**Test-only ripple:** None.

---

### ENT-003 — Migration-once guarantee not enforced at compose level (Approach B)

**Selected solution:** Move `setup_search_triggers` + `load_exchange_rates` into `migrate_locked.main()` as `subprocess.run` under the advisory lock; collapse compose migrate command to single `python -c`.

**Root cause analysis:** The `docker-compose.yml` migrate service (line 35) chains three commands with `&&`: `migrate_locked.main()` → `setup_search_triggers` → `load_exchange_rates`. These run outside the advisory lock, so a concurrent container start could cause race conditions. Moving the last two commands inside `migrate_locked.main()` ensures all post-migration setup happens under the lock.

**Critical correction:** `entrypoint-test.sh` (lines 21-23) calls `manage.py migrate --run-syncdb`, `load_exchange_rates`, and `setup_search_triggers` **directly and separately** — it does NOT call `migrate_locked.main()`. Therefore:
- **No env guard is needed** in `migrate_locked.py` — the test entrypoint never invokes it.
- The `docker-compose.test.yml` `migrate` service overrides environment only (lines 31-40), keeping the production command from `docker-compose.yml`. However, the `test` service (the one actually run via `make test`) uses `entrypoint-test.sh`, which bypasses `migrate_locked` entirely.
- The `migrate` service with the collapsed command is used in the production test flow only if explicitly invoked via `docker compose --profile` — but the standard `make test` path goes through `entrypoint-test.sh`.

**Implementation actions:**

| # | File | Action |
|---|------|--------|
| 1 | `src/backend/apps/core/utils/migrate_locked.py` | **Update** — add `subprocess.run` calls for `setup_search_triggers` + `load_exchange_rates` after `migrate --run-syncdb` completes under lock |
| 2 | `docker-compose.yml` | **Update** — collapse multi-line migrate command (line 35) to single `python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"` |

**Tests required:**

| # | Test file | Action |
|---|-----------|--------|
| 1 | `src/backend/apps/core/tests/test_migrations.py` | **Verify** — no changes needed; `migrate_locked.main()` is not called directly in tests (entrypoint-test.sh uses `manage.py migrate --run-syncdb`) |
| 2 | `src/backend/apps/core/tests/test_sweep_lock_structure.py` | **Verify** — tests lock structure, not the subprocess calls |

**Docs required:**

| # | Doc file | Line/Section | Action |
|---|----------|--------------|--------|
| 1 | `docs/ops/migration-workflow.md` | lines 67-93 | **Update** — old command → new single `python -c` |
| 2 | `docs/ops/migration-workflow.md` | line 96 | **Update** — `advisory_lock` reference + subprocess note |
| 3 | `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md` | lines 80, 118, 133, 139, 177-182 | **Update** — migrate_locked.py subprocess approach (clarify entrypoint-test.sh uses direct manage.py calls, not migrate_locked) |
| 4 | `docs/99-agent/architecture.md` | line 28 | **Update** — "migrations run exactly once" → subprocess approach |
| 5 | `docs/97-plans/phase-01-detailed-deployment.md` | lines 171-179 | **Update** — migrate command collapse |

**Test-only ripple:** `entrypoint-test.sh` lines 21-23 call `manage.py migrate --run-syncdb`, `load_exchange_rates`, and `setup_search_triggers` **directly** — NOT through `migrate_locked.main()`. The test entrypoint is unchanged: no env guard is needed because `migrate_locked` is never invoked during tests. The `subprocess.run` calls inside `migrate_locked.main()` only execute in the production `migrate` container.

---

### ENT-004 — Bot process doesn't close DB connections on shutdown

**Selected solution:** `dp.shutdown.register(_on_shutdown)` calling `connections.close_all()` + `close_old_connections()` in `main.py`.

**Root cause analysis:** `main.py` (lines 1-71) has no shutdown handlers. When the bot process receives SIGTERM (e.g., container stop), Django DB connections may leak. No `_on_shutdown` function or `dp.shutdown.register()` call exists.

**Implementation actions:**

| # | File | Action |
|---|------|--------|
| 1 | `src/telegram_bot/main.py` | **Update** — add `_on_shutdown` function calling `connections.close_all()` + `close_old_connections()`; register via `dp.shutdown.register(_on_shutdown)` before `dp.run_polling(bot)` |

**Tests required:**

| # | Test file | Action |
|---|-----------|--------|
| 1 | `src/telegram_bot/tests/conftest.py` | **Update** — `dp` fixture must register `_on_shutdown` to mirror production (ENT-004) and ENT-005's startup hook (if ENT-005 is in same sprint) |

**Docs required:**

| # | Doc file | Line/Section | Action |
|---|----------|--------------|--------|
| 1 | `docs/99-agent/architecture.md` | line 20 | **Update** — two-process model bot lifecycle |
| 2 | `docs/01-spec/architecture-structure.md` | ~lines 200-201 | **Update** — bot service lifecycle |
| 3 | `docs/ops/docker-deployment.md` | ~line 793 | **Update** — bot shutdown note (cross-ref ENT-005) |

**Test-only ripple:** The `dp` fixture in `src/telegram_bot/tests/conftest.py` must mirror the shutdown registration to keep bot lifecycle tests representative.

---

### ENT-005 — Bot healthcheck depends on DB connection

**Selected solution:** `BOT_LIVENESS_FILE` setting; shared `lifecycle.py` with startup/shutdown hooks + `LivenessMiddleware`; `docker/healthcheck-bot.sh`; replace compose bot healthcheck. Depends on ENT-004 (edits same `main.py` + shared `lifecycle.py`).

**Research corrections (applied):**
1. **Settings directory is `config/settings/` (`base.py`), NOT `apps/core/settings/`** — verified by filesystem enumeration. `apps/core/settings/` does not exist.
2. **Use `dp.update.middleware()` not `dp.message.middleware()`** — `dp.message.middleware()` only fires on Updates containing messages, missing callback_query/inline_query; `dp.update.middleware()` fires on ALL update types and matches the codebase's existing pattern (`UpdateIdDedupMiddleware`).

**Root cause analysis:** The bot service healthcheck in `docker-compose.yml` (lines 189-194) currently uses `kill -0 1` which only checks the process is alive — it doesn't verify DB connectivity but is misleadingly labeled as a healthcheck. ENT-005 proposes a file-based liveness marker that proves the bot has successfully started (connected to DB, registered routers) rather than just having a running process.

**Implementation actions:**

| # | File | Action |
|---|------|--------|
| 1 | `src/telegram_bot/lifecycle.py` | **Create** — `_on_startup` (touch marker), `_on_shutdown` (remove marker + `connections.close_all()` + `close_old_connections()`), `LivenessMiddleware` (touch marker mtime per update) |
| 2 | `src/telegram_bot/main.py` | **Update** — `from telegram_bot.lifecycle import _on_startup, _on_shutdown, LivenessMiddleware`; register `dp.startup.register(_on_startup)`, `dp.shutdown.register(_on_shutdown)` (ENT-004), add `dp.update.middleware(LivenessMiddleware())` — **depends on ENT-004** |
| 3 | `src/backend/config/settings/base.py` | **Update** — add `BOT_LIVENESS_FILE` setting (default `/tmp/mko_bazuna_bot_alive`) |
| 4 | `docker/healthcheck-bot.sh` | **Create** — check PID alive → marker exists (readiness) → optional mtime freshness (`BOT_HEALTH_STALE_SECONDS`) |
| 5 | `docker-compose.yml` | **Update** — bot healthcheck (lines 189-194): replace `kill -0` with `docker/healthcheck-bot.sh` |

**Tests required:**

| # | Test file | Action |
|---|-----------|--------|
| 1 | `src/telegram_bot/tests/conftest.py` | **Update** — mirror ENT-005 startup hook in `dp` fixture |
| 2 | `src/telegram_bot/tests/test_bot_liveness.py` | **Create** — verify marker file created on startup, touched on update, removed on shutdown |

**Docs required:**

| # | Doc file | Line/Section | Action |
|---|----------|--------------|--------|
| 1 | `docs/ops/docker-deployment.md` | line 793 | **Update** — bot healthcheck → file-based |
| 2 | `docs/97-plans/phase-01-detailed-deployment.md` | lines ~187-191 | **Update** — health check section |
| 3 | `docs/01-spec/architecture-structure.md` | ~lines 200-201 | **Update** — bot healthcheck note |

**Test-only ripple:** Direct consequence of ENT-004: the `dp` fixture must register both `_on_shutdown` (ENT-004) and the startup/liveness hooks (ENT-005). Sequential dependency — ENT-005 cannot be tested without ENT-004's shutdown registration in the same conftest.

---

### ENT-006 — Empty bot directories (`filters`, `handlers`, `states`)

**Selected solution:** VERIFY RESOLVED — remove empty directories.

**Verification:** `glob src/telegram_bot/bot/**/*` returned **zero files** — the empty `bot/` tree does NOT exist in the codebase. Confirmed `telegram_bot/handlers/` (top-level, populated) is the real handler directory. This finding is **already resolved** — no action needed. Only docs cross-check required.

**Implementation actions:** None (production code).

| # | File/Dir | Action |
|---|----------|--------|
| — | — | **Already resolved** — `telegram_bot/bot/` does not exist (verified by glob)

**Tests required:** None — no tests reference this directory.

**Docs required:**

| # | Doc file | Line/Section | Action |
|---|----------|--------------|--------|
| 1 | `docs/STRUCT.md` | lines 41-44 | **Verify** — remove any stale references to empty dirs |

**Test-only ripple:** None.

---

### ENT-007 — AnalyticsEvent creation inline in views (`listings.py`, `search.py`)

**Selected solution:** Phased extraction. **Recorder location: `apps/core/services/analytics.py` (QLT-003 canonical)** — NOT `apps/analytics/services/event_recording.py` (which does not exist and would conflict with QLT-003's canonical designation). Phase 1 (analytics service) is the highest-priority, lowest-risk increment; Phases 2–3 follow.

**Research decision:** The QLT-003 audit designates `apps/core/services/analytics.py` as the canonical `record_event` location (sibling to `contact.py`, which already calls `AnalyticsEvent.objects.create`). Two recorders writing the same table from divergent paths is a maintainability hazard. Since `apps/core/services/analytics.py` does not yet exist (QLT-003 not yet implemented), ENT-007 **creates it**; QLT-003 can later refactor the other sites to delegate to it without conflict.

**`record_event` design (QLT-003 constraints applied):**
- `transaction` transparent — NO `transaction.atomic()` (QLT-003 CRITICAL: a self-contained atomic would create a nested savepoint that commits analytics writes while rolling back outer state on moderation failure).
- `try/except Exception` around `AnalyticsEvent.objects.create` — analytics failure → log via `logger.exception`, return `None`; view continues rendering (fixes the HTTP-500 vulnerability).
- Lazy `%s` logging (rule #12).
- Signature: `record_event(event_type: AnalyticsEventType, user_id: int | None = None, *, ad_id: int | None = None, source: AdSource | None = None) -> AnalyticsEvent | None`
- **Query budget:** success path = 1 INSERT, 0 SELECT (same as inline `create`). `try/except` adds 0 queries. `_QUERY_BOUND = 16` preserved.

**Implementation actions:**

| # | File | Action | Phase |
|---|------|--------|-------|
| 1 | `src/backend/apps/core/services/analytics.py` | **Create** — `record_event(...)` (see signature above) | Phase 1 |
| 2 | `src/backend/apps/ads/views/listings.py` | **Update** — replace inline `AnalyticsEvent.objects.create(AD_VIEWED, ...)` (line 74) with `record_event(AnalyticsEventType.AD_VIEWED, user_id=ad.user_id, ad_id=ad.id)`; remove `AnalyticsEvent` import | Phase 1 |
| 3 | `src/backend/apps/search/views/search.py` | **Update** — replace inline `AnalyticsEvent.objects.create(SEARCH_PERFORMED, ...)` (line 230) with `record_event(...)`; remove `AnalyticsEvent` import | Phase 1 |
| 4 | `src/backend/apps/ads/services/ad_display.py` | **Create** — `resolved_display_features(ad)` (extract feature filtering, listings.py:80-85) | Phase 2 |
| 5 | `src/backend/apps/ads/services/__init__.py` | **Create** — export `resolved_display_features` | Phase 2 |
| 6 | `src/backend/apps/search/services/filters.py` | **Create** — `parse_price_min`, `parse_price_max`, `parse_active_price_range` | Phase 3 |
| 7 | `src/backend/apps/search/services/query_builder.py` | **Create** — `build_search_queryset(...)` (extract FTS vector + sort + category/city/price filtering orchestration) | Phase 3 |
| 8 | `src/backend/apps/search/services/__init__.py` | **Update** — export `build_search_queryset`, `parse_price_*` | Phase 3 |

**Tests required:**

| # | Test file | Action | Phase |
|---|-----------|--------|-------|
| 1 | `src/backend/apps/ads/tests/test_detail_context.py` | **Update** — mock target: `patch("apps.ads.views.listings.AnalyticsEvent")` → `patch("apps.ads.views.listings.record_event")` (lines 47, 84); usage `mock_ae.objects.create.return_value = None` → `mock_re.return_value = None` (lines 55, 91) | Phase 1 |
| 2 | `src/backend/apps/ads/tests/test_ad_detail_queries.py` | **Verify** — `_QUERY_BOUND = 16` must still pass (1 INSERT from `record_event`, 0 SELECT) | Phase 1 |
| 3 | `src/backend/apps/search/tests/test_search_view.py` | **Verify** — no `@patch` on `AnalyticsEvent`; integration test uses real DB | Phase 1 |
| 4 | `src/backend/apps/search/tests/test_autocomplete.py` | **Verify** — `test_search_records_analytics_event` checks DB row existence; `record_event` still creates it | Phase 1 |
| 5 | `src/backend/apps/core/tests/test_analytics_service.py` | **Create** — test `record_event` creates event on success, returns `None` + logs on failure | Phase 1 |
| 6 | `src/backend/apps/search/tests/test_query_builder.py` | **Create** — test `parse_price_*` (pure); verify `build_search_queryset` produces same filters | Phase 3 |

**Tests required:**

| # | Test file | Action |
|---|-----------|--------|
| 1 | `src/backend/apps/ads/tests/test_detail_context.py` | **Update** — mock target: `apps.ads.views.listings.AnalyticsEvent` → `apps.ads.views.listings.record_event` (line 47: `patch("apps.ads.views.listings.AnalyticsEvent")` → `patch("apps.ads.views.listings.record_event")`) |
| 2 | `src/backend/apps/ads/tests/test_ad_detail_queries.py` | **Verify** — `_QUERY_BOUND = 16` includes "1 INSERT (AnalyticsEvent)" — must still pass after service extraction (no extra queries introduced) |
| 3 | `src/backend/apps/search/tests/test_search_view.py` | **Verify** — check if `test_search_records_analytics_event` patches `AnalyticsEvent` directly; update mock target to `record_event` if so |
| 4 | `src/backend/apps/search/tests/test_autocomplete.py` | **Verify** — `test_search_records_analytics_event` — same mock target check |
| 5 | `src/backend/apps/analytics/tests/test_event_recording.py` | **Create** — test `record_event` service |
| 6 | `src/backend/apps/search/tests/test_query_builder.py` | **Create** — test `parse_price_*` / `build_search_queryset` if logic is non-trivial |

**Docs required:**

| # | Doc file | Line/Section | Action |
|---|----------|--------------|--------|
| 1 | `docs/01-spec/technical-specification.md` | lines ~163-205 | **Update** — AnalyticsEvent → service layer |
| 2 | `docs/STRUCT.md` | — | **Verify** — no direct references to inline AnalyticsEvent in views (update if present) |

**Test-only ripple:**
- `test_detail_context.py` mock target MUST change: `apps.ads.views.listings.AnalyticsEvent` → `apps.ads.views.listings.record_event` (or the actual symbol name used in the import). After the change, `listings.py` imports `record_event` from `apps.analytics.services`, so the patch target becomes `apps.ads.views.listings.record_event`.
- `test_ad_detail_queries.py::_QUERY_BOUND = 16` — the service extraction must not introduce an extra DB query. `record_event(...)` must call `AnalyticsEvent.objects.create(...)` in a single query (no change in query count).
- `test_search_view.py` and `test_autocomplete.py` may patch `AnalyticsEvent` directly — verify and update mock targets to `record_event` if they do.

---

## Test-Only Ripple Effects (Consolidated)

| Effect | Affected test files | Resolution |
|--------|---------------------|------------|
| Internal patch targets in `test_media.py` | `src/telegram_bot/tests/test_media.py` → `src/backend/apps/media/tests/test_filesystem.py` | Update `telegram_bot.services.media.*` → `apps.media.services.filesystem.*` (8 patch strings at lines 230, 239, 252, 255, 268, 271, 283, 286) |
| Import path change in media tests | `test_media_security.py`, `test_thumbnail_integration.py`, `test_backfill_thumbnails.py` | Update imports from `telegram_bot.services.media` → `apps.media.services.filesystem` |
| Mock target change: `AnalyticsEvent` → `record_event` | `test_detail_context.py`, `test_search_view.py`, `test_autocomplete.py` | Update `@patch` targets to `record_event` in the view module namespace |
| Query count guard: `_QUERY_BOUND = 16` | `test_ad_detail_queries.py` | Verify `record_event` makes exactly 1 INSERT — no extra queries |
| Monkeypatch targets at importer namespace | `test_sweep_commands.py`, `test_deletion.py` | **NO CHANGE** — already patch `apps.core.management.commands.<cmd>.delete_photo` and `apps.users.services.deletion.delete_photo` (importer namespace, not media.py) |
| `dp` fixture must mirror production lifecycle | `telegram_bot/tests/conftest.py` | Register `_on_shutdown` (ENT-004) + liveness hooks (ENT-005) |
| Test entrypoint bypasses migrate_locked | `entrypoint-test.sh` | No env guard needed — calls `manage.py migrate --run-syncdb` directly, never invokes `migrate_locked.main()` |

---

## Rollout / Ordering Matrix

**Critical path dependencies:**

```
ENT-004 (shutdown hook)
    └── ENT-005 (liveness hooks)  [must come after, edits same file + lifecycle.py]

ENT-006 (verify already resolved)
    └── no action needed

ENT-001 (media move)
    ├── test_media.py move + internal patch target updates
    ├── 8 importer updates (handlers, services, management commands, tests)
    └── monkeypatch targets in sweep_commands/deletion = NO CHANGE (importer namespace)

ENT-003 (migrate_locked subprocess)
    └── entrypoint-test.sh does NOT call migrate_locked → no env guard

ENT-002 (scheduler depends_on)
    └── docker-compose.prod.yml only

ENT-007 (view thinning)
    └── mock target updates in test_detail_context.py
```

**Sequential ordering (recommended):**

| Step | Finding | Rationale |
|------|---------|-----------|
| 1 | ENT-006 | Verify resolved first — no work needed, confirms `telegram_bot/bot/` is gone |
| 2 | ENT-001 | Largest surface area: 8 importer updates + 4 test file updates + move + internal patch targets. Do early to validate import chain before other changes. |
| 3 | ENT-004 | Bot lifecycle foundation — `_on_shutdown` registration in `main.py` + conftest `dp` fixture |
| 4 | ENT-005 | Depends on ENT-004 (same file + shared `lifecycle.py`); conftest must register both hooks |
| 5 | ENT-003 | Migration infra — collapse compose command + add subprocess calls in `migrate_locked.py`; no test entrypoint impact |
| 6 | ENT-007 | View thinning — create 5 service files + update 2 views + update mock targets in tests |
| 7 | ENT-002 | Compose scheduler dep — trivial config-only change |
| 8 | Docs | Update all docs as final step |

**Blocking concerns:**

1. **ENT-001 + internal patch targets in `test_media.py`:** The test file patches `telegram_bot.services.media.*` internal calls. When moved to `apps/media/services/filesystem.py` and renamed to `test_filesystem.py`, all 8 patch strings MUST be updated to `apps.media.services.filesystem.*`. Without this, the moved test will fail.
2. **ENT-001 + importer updates:** All 8 importers (handlers, services, management commands, tests) must be updated in the same change-set. If `media.py` is deleted while any importer still references it, imports will fail.
3. **ENT-003 + entrypoint-test.sh:** The test entrypoint calls `manage.py migrate --run-syncdb` directly and never invokes `migrate_locked.main()`, so no env guard is needed. This was confirmed in `entrypoint-test.sh` lines 21-23.
4. **ENT-004 + ENT-005:** Both edit `main.py` and touch the conftest `dp` fixture. ENT-005 depends on ENT-004 (same file, sequential edits). The conftest must register both hooks.
5. **ENT-007 + mock target in `test_detail_context.py`:** Line 47 patches `apps.ads.views.listings.AnalyticsEvent`. After the change, `listings.py` imports `record_event`, so the patch target MUST become `apps.ads.views.listings.record_event` or the test will silently pass without exercising the mock.
6. **ENT-007 + query count:** `test_ad_detail_queries.py::_QUERY_BOUND = 16` must still pass — `record_event` must not add queries.

---

## Environment Context

- **Python:** 3.14 · **Django:** 5.2 LTS · **PostgreSQL:** 18 · **Test DB:** Docker (`mko-bazuna-test`, port 5433)
- **Test entrypoint:** `docker/entrypoint-test.sh` — calls `manage.py migrate --run-syncdb`, `load_exchange_rates`, `setup_search_triggers` directly (NOT via `migrate_locked.main()`), then pytest
- **Default pytest flags:** `--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`
- **Conftest boundaries:** `src/backend/conftest.py` (backend fixtures) vs `src/telegram_bot/tests/conftest.py` (async `user`, `dp` fixture)
- **Monkeypatch pattern:** Tests patch symbols at the *importer's namespace* (e.g., `apps.users.services.deletion.delete_photo`), NOT at the source module — this means importer-side monkeypatch targets survive source module moves.
