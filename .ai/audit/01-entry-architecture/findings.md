# Phase 01 Audit Findings — Entry Points & Process Architecture

**Executor:** audit-executor
**Template:** `.ai/audit/templates/audit-findings.md`
**Phase Spec:** `.kilo/commands/audit/phases/01-audit-entry-architecture.md`
**Status:** complete
**Validated:** yes

Runtime verification performed host-side with the project `.venv` (Python 3.14 / Django 5.2.16) under
`DJANGO_SETTINGS_MODULE=config.settings.dev PYTHONPATH=src/backend;src`. Evidence collected:
`django.setup()` + import of `config.wsgi` and `telegram_bot.main` (no circular imports, no import-time
ORM side-effects); `manage.py migrate --noinput` applied `ads 0001-0004` on a fresh `mko_bazuna` DB;
`migrate_locked.main()` acquired/released advisory lock 100 and exited 0 with a model-drift warning;
`basedpyright src/` — 8 errors; `ruff check src/` — clean.

## Findings

### ENT-001: Login-token claim crashes: `QuerySet.update(returning=True)` raises `FieldDoesNotExist`

| Field | Value |
|-------|-------|
| **ID** | ENT-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | `src/telegram_bot/handlers/login.py:115-130` |
| **Classification** | mandatory |

**Description:** The bot login handler (executed in the async bot loop, wrapped in `sync_to_async`)
attempts an atomic claim-and-RETURNING on `LoginToken` via
`LoginToken.objects.filter(...).update(telegram_id=..., returning=True).first()`. Django 5.2's
`QuerySet.update(**kwargs)` interprets every keyword as a field assignment — there is no
`returning` parameter on `update()`. `LoginToken` (model: `apps/users/models.py:117`) has fields
`token_hash`, `telegram_id`, `created_at`, `expires_at`, `consumed_at` — none named `returning`.
The call raises `FieldDoesNotExist: LoginToken has no field named returning` before any SQL is
executed. Additionally, even if `returning=True` were removed, `update()` returns an int (rows
affected), so the chained `.first()` would raise `AttributeError: int object has no attribute first`.
The intent — PostgreSQL UPDATE-RETURNING for a single-query atomic claim — is not achievable through
the Django ORM `update()` API.

**Evidence:** Reproduced directly:
`LoginToken.objects.filter(token_hash=x).update(telegram_id=1, returning=True)`
FieldDoesNotExist: LoginToken has no field named return
at `src/telegram_bot/handlers/login.py:128`. `inspect.signature(QuerySet.update)` = `(self, **kwargs)`;
returning is not in the parameter list. `LoginToken` model fields confirmed via
`apps/users/models.py:117-156`: no `returning` field exists.

**Recommendation:** Replace the `update(returning=True).first()` pattern with a correct atomic claim:
`SELECT ... FOR UPDATE` + `UPDATE` + `SELECT` inside `transaction.atomic()` (or raw SQL with
`UPDATE ... RETURNING`), returning the claimed row. This is a correctness bug — every `/start
login_<token>` flow crashes. Effort: medium.

---

### ENT-002: Reverse imports: backend service/core imports from bot transport layer

| Field | Value |
|-------|-------|
| **ID** | ENT-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `apps/users/services/deletion.py:17`, `apps/core/management/commands/{purge_failed_ads,delete_sweep,purge_rejected_ads,sweep_drafts,consent_hard_delete}.py:18-21`, `apps/ads/tests/test_media_security.py:26`, `apps/media/tests/test_backfill_thumbnails.py:119`, `apps/core/tests/test_contact.py:8` |
| **Classification** | mandatory |

**Description:** The backend service/core layer imports media-utility functions from
`telegram_bot/services/media.py` (the bot transport-layer namespace). Six production import sites
exist: `apps/users/services/deletion.py` (line 17: `delete_photo`) and five
`apps/core/management/commands/*.py` files (each importing `delete_photo` from the bot layer). These
functions — `delete_photo`, `generate_storage_key`, `strip_photo_exif`, `validate_photo`,
`validate_jpeg_bytes` — are generic media-processing utilities with no telebot-specific logic; they
correctly belong in `apps/media/services/` (which already contains `hash_service.py` and
`thumbnails.py`). The reverse import creates a dependency where the web/scheduler process code
depends on the bot module layout, violating the documented layer direction (entry to service/core,
never reverse) and coupling the two processes package structure.

**Evidence:** `grep -rn from-telegram_bot src/backend/apps/` 9 matches across 2 services,
5 management commands, and 3 test modules. `apps/media/services/` contains only `hash_service.py`
and `thumbnails.py` — the `delete_photo` / `generate_storage_key` / `strip_photo_exif` functions are
absent from the proper media service module. Management commands run in the scheduler/web process
(via `entrypoint-scheduler.sh`), not the bot process, yet import from `telegram_bot.services`.

**Recommendation:** Move `delete_photo`, `generate_storage_key`, `strip_photo_exif`,
`validate_photo`, and `validate_jpeg_bytes` to `apps/media/services/`, update all backend imports to
reference the new location, and remove the `telegram_bot.services.media` module (or keep a thin
re-export for backward compat during a transition window). Effort: medium.

---

### ENT-003: `LocMemCache` used as default cache in a multi-process deployment

| Field | Value |
|-------|-------|
| **ID** | ENT-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `config/settings/base.py:215-218`, `apps/analytics/services/seller_stats.py:42-49`, `docker-compose.yml` (web + bot services) |
| **Classification** | advisory |

**Description:** The default cache backend is `django.core.cache.backends.locmem.LocMemCache`
(`base.py:215-218`), which stores entries in **process-local memory**. The deployment runs two
long-lived processes — gunicorn (web) and aiogram (bot) — as separate OS processes with separate
memory spaces. Anything cached by the web process is invisible to the bot process and vice versa,
and within gunicorn, each worker has its own independent cache (no sharing). The consumer
`analytics/services/seller_stats.py:42-49` caches seller statistics keyed by
`seller_stats:{user_id}:{time_range}` — if the bot populates that cache, a web request for the same
seller hits a cold cache and recomputes; conversely, web-warm cache is invisible to the bot.

**Evidence:** `grep -rn "LocMemCache" src/backend/config/settings/base.py` ? `base.py:217`.
`grep -rn "cache.get\|cache.set" src/backend/apps/analytics/services/seller_stats.py` ? lines 45, 49.
`docker-compose.yml` defines separate `web` and `bot` services (distinct processes). No shared cache
backend (Redis/Memcached) is configured or wired into compose.

**Recommendation:** Configure a shared external cache (Redis via `django-redis` or Memcached via
`django-pylibmc`) in `base.py` and add the service to `docker-compose[.prod].yml`. This ensures
cache consistency across the web and bot processes. Effort: medium.

---

### ENT-004: Model definitions have drifted from migration files (pending `ads` 0005)

| Field | Value |
|-------|-------|
| **ID** | ENT-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `apps/ads/models.py` (fields `category_name`, `description`, `title`), `apps/ads/migrations/0004_*` (last applied), `apps/core/utils/migrate_locked.py:26-30` |
| **Classification** | mandatory |

**Description:** `makemigrations --check --dry-run` detects pending model changes in the `ads` app
that are not yet captured in a migration file: altering `category_name`, `description`, and `title`
fields on `Ad`. The existing migration chain stops at `0004`; no `0005` migration file exists in the
repository. Consequently, the "migration-once guarantee" is compromised: `manage.py migrate` only
applies migration files that exist (0001–0004), leaving the database schema out of sync with the
current model definitions. The `migrate_locked` runner surfaces this as a "models-have-changes"
warning during execution. Deploying the current code without a generated migration risks silent schema
mismatches, runtime `OperationalError`s on changed fields, or data truncation if the field
alterations affect column types.

**Evidence:** `manage.py makemigrations --check --dry-run` output:
`Migrations for 'ads': 0005_alter_ad_category_name_alter_ad_description_and_more ~ Alter field
category_name on ad ~ Alter field description on ad ~ Alter field title on ad`.
`git ls-files apps/ads/migrations/` ? only `0001_initial.py` … `0004_*.py` (no `0005`).
`manage.py migrate --noinput` on a fresh DB applied `ads 0001-0004` only.

**Recommendation:** Run `manage.py makemigrations ads` to generate the `0005` migration, review the
field alterations, and commit. Ensure CI runs `makemigrations --check --dry-run` as a gate to
prevent future drift. Effort: trivial (generation) + small (review).

---

### ENT-005: `basedpyright` reports 8 type errors across production modules

| Field | Value |
|-------|-------|
| **ID** | ENT-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `telegram_bot/handlers/ad_copy.py:35`, `apps/ads/models.py:472`, `apps/categories/catalog/builder.py:74`, `apps/categories/services/lookup_resolution.py:59,64`, `apps/lookups/models.py:40,89` |
| **Classification** | advisory |

**Description:** `basedpyright src/` reports 8 errors across 5 production modules. The most
operationally risky is `ad_copy.py:35` (`reportOptionalMemberAccess`): `.strip()` is called on a
value typed as `str | None` without a `None` guard — if the value is `None` at runtime, the
handler crashes with `AttributeError`. The remaining 7 are Django-ORM typing mismatches: model
fields (`CharField`, `SlugField`) are typed as descriptors, not their underlying Python types
(`str`), so returning them from typed methods yields type errors. `categories/catalog/builder.py:74`
reports that an object used as a context manager does not correctly implement `__enter__`/`__exit__`
(`reportGeneralTypeIssues`), which could indicate a real protocol mismatch at runtime.

**Evidence:** `uv run basedpyright src/` ? 8 errors, 0 warnings:
- `telegram_bot/handlers/ad_copy.py:35:25` — `"strip" is not a known attribute of "None"`
- `apps/ads/models.py:472:29` — `No overloads for "join" match`
- `apps/categories/catalog/builder.py:74:10` — `reportGeneralTypeIssues` (`__enter__`/`__exit__`)
- `apps/categories/services/lookup_resolution.py:59:16, 64:16` — `list[SlugField]` not assignable to
  `list[str]`
- `apps/lookups/models.py:40:16, 89:16` — `CharField`/`SlugField` not assignable to `str`

**Recommendation:** (1) Add a `None` guard before `.strip()` at `ad_copy.py:35`. (2) For ORM
return-type errors, either annotate return types to match Django field descriptors or use
`field.value` / `str(field)` casts where returning raw Python values. (3) Investigate
`builder.py:74` context-manager protocol mismatch. Consider adding `basedpyright` to CI as a gate.
Effort: medium.

---
### ENT-006: `send_alerts` management command is orphaned — no scheduler/cron wiring

| Field | Value |
|-------|-------|
| **ID** | ENT-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `apps/search/management/commands/send_alerts.py:1-7` (docstring claims "Runs once daily via cron"), `docker/entrypoint-scheduler.sh:21-40` (7 commands, none = `send_alerts`), `docker-compose.prod.yml` (no cron), `Makefile` |
| **Classification** | advisory |

**Description:** `send_alerts` is a complete management command (179 lines, fully implemented with
advisory lock `AdvisoryLockId.ALERT_DELIVERY_TASK`, dry-run mode, and async message delivery via
`asyncio.run`). Its docstring states "Runs once daily via cron." However, no cron job or scheduler
entry calls this command. The `entrypoint-scheduler.sh` runs exactly 7 commands in its hourly loop —
`archive_sweep`, `delete_sweep`, `consent_hard_delete`, `sweep_drafts`, `cleanup_login_tokens`,
`purge_failed_ads`, `purge_rejected_ads` — none of which is `send_alerts`. `docker-compose.prod.yml`
defines no cron service. The `Makefile` has no `alerts` target. The command is tested
(`test_alert_query.py` calls `call_command("send_alerts", "--dry-run")`) but never executes in
production. Per the dead-code policy, since documentation (the docstring) specifies it should exist
and be scheduled, this is future-proofing that was never completed — an orphan entry point, not dead
code — but the gap between documented intent and actual wiring is a latent operational failure.

**Evidence:** `grep -rn "send_alerts" docker/ docker-compose*.yml Makefile` ? 0 matches in
deployment files. `grep -rn "send_alerts" src/backend/apps/search/management/commands/` ? the command
exists at `send_alerts.py:26-29`. `docker/entrypoint-scheduler.sh:28-37` lists the 7 hourly commands
(explicitly excluding `send_alerts`). `test_alert_query.py:380,388,403` test the command.

**Recommendation:** Either wire `send_alerts` into the scheduler loop (add it to
`entrypoint-scheduler.sh` with an appropriate daily interval, or add a cron container/profile), or
remove the misleading docstring claim and the test stubs if the feature is deferred. Effort: small.

---

### ENT-007: `migrate_locked.py` path resolution via `parents[3]` is fragile

| Field | Value |
|-------|-------|
| **ID** | ENT-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `apps/core/utils/migrate_locked.py:25` |
| **Classification** | advisory |

**Description:** The one-shot migration runner resolves `manage.py` via
`Path(__file__).resolve().parents[3] / "manage.py"` — a hardcoded depth assumption. The file is
expected at exactly `apps/core/utils/migrate_locked.py` relative to `manage.py` at the project root
(`src/backend/manage.py`). If the module is relocated, the directory structure changes, or the file
is invoked from a different working directory (e.g., inside Docker where paths differ), the
computed path will silently point to a non-existent or wrong `manage.py`. The advisory-lock
mechanism itself (session lock ID 100 via `AdvisoryLockId.MIGRATE`) works correctly — it acquires
before `subprocess.run` and releases in the `with` block on both success and failure — but the
fragile path resolution is a latent failure mode that only surfaces at deploy time.

**Evidence:** `migrate_locked.py:25`:
`manage_py = Path(__file__).resolve().parents[3] / "manage.py"`. The module is at
`apps/core/utils/migrate_locked.py`; `parents[0]` = `utils`, `parents[1]` = `core`, `parents[2]` =
`apps`, `parents[3]` = `src/backend/` ? `manage.py`. Any structural change breaks this chain.
Runtime test confirmed: `migrate_locked.main()` ran successfully (lock acquired/released, exited 0),
but this only works because the current path depth happens to be exactly 3.

**Recommendation:** Use Django's `django.core.management.utilsgetprojectsettings` or resolve
`manage.py` via `sys.modules["django.conf"].settings` / `settings.BASE_DIR` instead of a hardcoded
parent depth. At minimum, add an assertion that the resolved path exists. Effort: trivial.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 2 |

## Mandatory Fixes
- **ENT-001** — Fix `LoginToken.objects.filter(...).update(returning=True).first()` in
  `telegram_bot/handlers/login.py:128`. This crashes every login-token claim. Replace with
  `select_for_update()` + `UPDATE` + `SELECT` in a transaction, or raw SQL `UPDATE … RETURNING`.
- **ENT-002** — Move media utilities (`delete_photo`, `generate_storage_key`,
  `strip_photo_exif`, etc.) from `telegram_bot/services/media.py` to `apps/media/services/`
  and rewire all backend imports. Eliminates reverse-layer dependency.
- **ENT-004** — Generate the missing `ads` 0005 migration
  (`manage.py makemigrations ads`) and add a CI gate for `makemigrations --check --dry-run`.

## Advisory Recommendations
- **ENT-003** — Replace `LocMemCache` with a shared Redis/Memcached backend so web and bot
  processes share cache entries.
- **ENT-005** — Fix the 8 `basedpyright` errors (None-guard in `ad_copy.py:35`, ORM
  return-type annotations, `builder.py:74` context-manager protocol).
- **ENT-006** — Wire `send_alerts` into the scheduler loop or remove the misleading
  "runs via cron" docstring and unused tests.
- **ENT-007** — Replace fragile `parents[3]` path resolution in `migrate_locked.py` with
  settings-based `BASE_DIR` resolution.

## Doc Updates Needed
(None — all findings include in-source code evidence and file/line references.)


