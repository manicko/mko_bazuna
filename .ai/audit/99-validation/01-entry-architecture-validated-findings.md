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
`basedpyright src/` — 10 errors (not 8 as originally reported; see ENT-005 validation note);
`ruff check src/` — clean.

## Validation Methodology

Each finding was validated by:
1. Reading the actual source file at the referenced location.
2. Running `makemigrations --check --dry-run` to confirm migration drift (ENT-004).
3. Running `basedpyright src/` to confirm type errors (ENT-005).
4. Running `grep` across `src/backend/` for reverse imports (ENT-002).
5. Checking `docker-compose.yml`, `docker-compose.prod.yml`, `Makefile`, and `entrypoint-scheduler.sh` for deployment configuration (ENT-003, ENT-006).
6. Cross-referencing other audit phase findings for conflicts and dependency chains.

**Path note:** The findings file uses `src/backend/src/telegram_bot/...` path prefixes for some
bot-layer files. The actual paths are `src/telegram_bot/...` (the `src` directory is on PYTHONPATH
alongside `src/backend`). File names and line numbers in the findings are accurate; only the directory
prefix is slightly off (`src/backend/src/` should be `src/`). This does not affect validation conclusions.

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

**Evidence:**
Reproduced directly:
`LoginToken.objects.filter(token_hash=x).update(telegram_id=1, returning=True)` ->
FieldDoesNotExist: LoginToken has no field named returning
at `src/telegram_bot/handlers/login.py:128`. `inspect.signature(QuerySet.update)` = `(self, **kwargs)`;
returning is not in the parameter list. `LoginToken` model fields confirmed via
`apps/users/models.py:117-156`: no `returning` field exists.

Source verified at `src/telegram_bot/handlers/login.py:119-130`:
```python
# Atomic UPDATE claim with RETURNING — single query, no TOCTOU
with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
    login_token = (
        LoginToken.objects.filter(
            token_hash=token_hash,
            telegram_id__isnull=True,
            consumed_at__isnull=True,
            expires_at__gt=now,
        )
        .update(telegram_id=telegram_id, returning=True)
        .first()
    )
```

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The bug is confirmed in source code at line 128-129. Django's `QuerySet.update(**kwargs)`
> treats `returning=True` as a field assignment for a non-existent field `returning`, raising
> `FieldDoesNotExist`. Furthermore, `update()` returns an `int`, so `.first()` would raise
> `AttributeError` even without the `returning` kwarg. The `LoginToken` model (verified at
> `src/backend/apps/users/models.py:117-156`) has fields `token_hash`, `telegram_id`, `created_at`,
> `expires_at`, `consumed_at` — no `returning` field. The recommendation to replace this pattern with
> `SELECT ... FOR UPDATE` + `UPDATE` + `SELECT` inside `transaction.atomic()` (or raw SQL
> `UPDATE ... RETURNING`) is technically correct and aligns with Django 5.2 capabilities. The file
> path in the finding (`src/backend/src/...`) is a minor annotation error; the actual path is
> `src/telegram_bot/handlers/login.py`.
> - **See also:** ENT-005 (both `ad_copy.py:35` and `login.py:128` are in
> `telegram_bot/handlers/`; the `# pyright: ignore` on `transaction.atomic()` at line 120 masks
> context-manager typing, NOT the real bug on line 128 which has no type-ignore annotation)

**Recommendation:** Replace the `update(returning=True).first()` pattern with raw SQL via
`connection.cursor()` executing `UPDATE login_tokens SET telegram_id=%s WHERE token_hash=%s AND
telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now() RETURNING *` inside the
existing `transaction.atomic()` block. This directly restores the intended single-query atomic
claim (no TOCTOU), matches the established pattern for PostgreSQL-specific operations
in `apps/core/utils/advisory_lock.py` (uses `cursor.execute` for `pg_advisory_xact_lock`) and
`apps/core/views.py:15-16` (health check), and aligns with the two-phase UPDATE documented in
`docs/02-database/db-schema.md:84-85`. Raw SQL is preferred over the ORM `SELECT ... FOR UPDATE`
approach because the schema documentation defines the claim as a single atomic UPDATE with
RETURNING, and the project already uses raw cursors for PostgreSQL-specific operations. No new
dependency required. Effort: medium.

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

**Evidence:**
grep for `from telegram_bot` in `src/backend/` — 9 matches across 2 services,
5 management commands, and 3 test modules. `apps/media/services/` contains only `hash_service.py`
and `thumbnails.py` — the `delete_photo` / `generate_storage_key` / `strip_photo_exif` functions are
absent from the proper media service module. Management commands run in the scheduler/web process
(via `entrypoint-scheduler.sh`), not the bot process, yet import from `telegram_bot.services`.

Source verified — 6 production import sites confirmed:
```
apps/users/services/deletion.py:17            -> from telegram_bot.services.media import delete_photo
apps/core/management/commands/delete_sweep.py:19         -> from telegram_bot.services.media import delete_photo
apps/core/management/commands/consent_hard_delete.py:21  -> from telegram_bot.services.media import delete_photo
apps/core/management/commands/purge_rejected_ads.py:19   -> from telegram_bot.services.media import delete_photo
apps/core/management/commands/sweep_drafts.py:18         -> from telegram_bot.services.media import delete_photo
apps/core/management/commands/purge_failed_ads.py:18     -> from telegram_bot.services.media import delete_photo
```

3 test modules also affected:
```
apps/ads/tests/test_media_security.py:26     -> from telegram_bot.services.media import delete_photo, generate_storage_key, strip_photo_exif
apps/media/tests/test_backfill_thumbnails.py:119 -> from telegram_bot.services.media import generate_storage_key
apps/core/tests/test_contact.py:8            -> from telegram_bot.handlers.contact import CONTACT_PATTERN
```

`apps/media/services/` confirmed to contain only `__init__.py`, `hash_service.py`, `thumbnails.py`.
`telegram_bot/services/media.py` confirmed to contain all 5 functions: `validate_jpeg_bytes`,
`validate_photo`, `generate_storage_key`, `delete_photo`, `strip_photo_exif`.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All 6 production reverse imports confirmed. All 5 media utility functions confirmed
> present in `telegram_bot/services/media.py` and absent from `apps/media/services/`. The layer
> violation is real — backend scheduler commands (running in the web/scheduler container via
> `entrypoint-scheduler.sh`) depend on the bot transport-layer namespace. Minor scope clarification:
> `test_contact.py:8` imports `CONTACT_PATTERN` from `telegram_bot.handlers.contact` (not
> `telegram_bot.services.media`), but this is still a legitimate reverse import of a bot-layer
> constant into backend test code.
> - **See also:** ENT-006 (send_alerts also resides in `apps/search/management/commands/` and uses
> advisory_lock from `apps/core.utils`, which also uses parents[3] path resolution in ENT-007)

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

**Evidence:**
`grep -rn "LocMemCache" src/backend/config/settings/base.py` -> `base.py:217`.
`grep -rn "cache.get|cache.set" src/backend/apps/analytics/services/seller_stats.py` -> lines 45, 49.
`docker-compose.yml` defines separate `web` and `bot` services (distinct processes). No shared cache
backend (Redis/Memcached) is configured or wired into compose.

Source verified:
- `src/backend/config/settings/base.py:215-218`:
  ```python
  CACHES = {
      "default": {
          "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
      }
  }
  ```
- `src/backend/apps/analytics/services/seller_stats.py:42-49`: uses `cache.get(cache_key)` and
  `cache.set(cache_key, result, CACHE_TTL)`.
- `docker-compose.yml:123-174`: `web` service runs `gunicorn ... --workers 3`; `bot` service runs
  `python -m telegram_bot.main`. Separate OS processes with no shared cache service.
- `docker-compose.prod.yml:36-60`: `scheduler` service runs `entrypoint-scheduler.sh`. No Redis or
  Memcached service defined in any compose file.
- grep for `redis|memcache|Redis|Memcached` across all `docker-compose*.yml` files: **0 matches**.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** `LocMemCache` confirmed as the sole cache backend. `docker-compose.yml` confirms 2+
> independent processes: gunicorn web (3 workers = 3 separate LocMemCache instances) and aiogram bot
> (1 process = 1 separate LocMemCache instance). No Redis, Memcached, or any shared cache backend is
> defined in any docker-compose file. The `seller_stats` service uses `cache.get`/`cache.set` with
> per-seller keys, which will never be shared across processes. The recommendation to use Redis
> (`django-redis`) or Memcached (`django-pylibmc`) as a shared backend is architecturally correct and
> essential for cache consistency at this project scale (2+ independent processes).
> - **See also:** —

**Recommendation:** Replace `LocMemCache` with Redis via `django-redis` in
`config/settings/base.py` (add `django-redis` to `pyproject.toml`) and add a `redis` service
to `docker-compose[.prod].yml`, wired into `web`, `bot`, and `scheduler` via `REDIS_URL`.
Select Redis over Memcached because two cache services already call `cache.delete_pattern`:
`apps/lookups/services/cache_service.py:76` and
`apps/categories/services/lookup_resolution.py:111`, both guarded by
`hasattr(cache, delete_pattern)`; this is a Redis-specific `django-redis` API that Memcached
does not support without workarounds. `src/telegram_bot/main.py:37` also future-references
`RedisStorage` for FSM persistence, and the spec-index lists Redis as anticipated
infrastructure (deferred to post-MVP). Effort: medium.

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
applies migration files that exist (0001-0004), leaving the database schema out of sync with the
current model definitions. The `migrate_locked` runner surfaces this as a "models-have-changes"
warning during execution. Deploying the current code without a generated migration risks silent schema
mismatches, runtime `OperationalError`s on changed fields, or data truncation if the field
alterations affect column types.

**Evidence:**
`manage.py makemigrations --check --dry-run` output:
`Migrations for 'ads': 0005_alter_ad_category_name_alter_ad_description_and_more ~ Alter field
category_name on ad ~ Alter field description on ad ~ Alter field title on ad`.
`git ls-files apps/ads/migrations/` -> only `0001_initial.py` through `0004_*.py` (no `0005`).
`manage.py migrate --noinput` on a fresh DB applied `ads 0001-0004` only.

Source verified — `makemigrations --check --dry-run ads` executed during validation:
```
EXIT_CODE: 1
STDOUT: Migrations for 'ads':
  src\backend\apps\ads\migrations\0005_alter_ad_category_name_alter_ad_description_and_more.py
    ~ Alter field category_name on ad
    ~ Alter field description on ad
    ~ Alter field title on ad
```

Root cause confirmed — drift is in `help_text` attributes:
- Model (`models.py:42-47`): `title` help_text = "Ad title in Russian (translated from seller input)"
  vs Migration 0004: `title` help_text = "Ad title in Russian. NULL during draft phase."
- Model (`models.py:60-64`): `description` help_text = "Ad description in Russian (translated from seller input)"
  vs Migration 0004: `description` help_text = "Ad description in Russian. NULL during draft phase."
- Model (`models.py:124-130`): `category_name` help_text = "Denormalized Russian category name; trigger-synced. NULL during draft phase."
  vs Migration 0004: `category_name` help_text = "Denormalized category name; trigger-synced. NULL during draft phase."

Migration files confirmed via glob: only `0001_initial.py`, `0002_initial.py`,
`0003_ad_i18n_fields.py`, `0004_ad_draft_nullable_fields.py` exist — no `0005`.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The `makemigrations --check --dry-run ads` command exits with code 1 and outputs exactly
> the migration name (`0005_alter_ad_category_name_alter_ad_description_and_more`) and field
> alterations (category_name, description, title) described in the finding. Only migrations 0001-0004
> exist in the repository. The root cause is confirmed: `help_text` strings on `title`, `description`,
> and `category_name` fields were updated in the model but never captured in a migration. The
> `migrate_locked.py` runner (line 26-30) correctly surfaces this as a warning. The recommendation
> to run `manage.py makemigrations ads` and add a CI gate for `makemigrations --check --dry-run` is
> correct and mandatory.
> - **See also:** ENT-007 (migrate_locked.py surfaces the drift warning; its path resolution
> via parents[3] must remain intact for migrate to work)

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

**Evidence:**
`uv run basedpyright src/` — 8 errors, 0 warnings:
- `telegram_bot/handlers/ad_copy.py:35:25` — `"strip" is not a known attribute of "None"`
- `apps/ads/models.py:472:29` — `No overloads for "join" match`
- `apps/categories/catalog/builder.py:74:10` — `reportGeneralTypeIssues` (`__enter__`/`__exit__`)
- `apps/categories/services/lookup_resolution.py:59:16, 64:16` — `list[SlugField]` not assignable to
  `list[str]`
- `apps/lookups/models.py:40:16, 89:16` — `CharField`/`SlugField` not assignable to `str`

Source verified — `basedpyright src/` re-run during validation (10 errors, 0 warnings, 0 notes):
```
telegram_bot/handlers/ad_copy.py:35:25 - error: "strip" is not a known attribute of "None" (reportOptionalMemberAccess)
apps/ads/models.py:472:29 - error: No overloads for "join" match the provided arguments (reportCallIssue)
apps/categories/catalog/builder.py:74:10 - error: ... does not correctly implement __enter__ (reportGeneralTypeIssues)
apps/categories/catalog/builder.py:74:10 - error: ... does not correctly implement __exit__ (reportGeneralTypeIssues)
apps/categories/services/lookup_resolution.py:59:16 - error: Type "list[SlugField]" is not assignable to return type "list[str]" (reportReturnType)
apps/categories/services/lookup_resolution.py:64:16 - error: Type "list[SlugField]" is not assignable to return type "list[str]" (reportReturnType)
apps/lookups/models.py:40:16 - error: Type "CharField" is not assignable to return type "str" (reportReturnType)
apps/lookups/models.py:89:16 - error: Type "SlugField" is not assignable to return type "str" (reportReturnType)
telegram_bot/handlers/alerts.py:69:32 - error: "__getitem__" method not defined on type "TextField" (reportIndexIssue)
telegram_bot/handlers/contact.py:143:42 - error: Type "BigIntegerField | None" is not assignable to declared type "int | None" (reportAssignmentType)
10 errors, 0 warnings, 0 notes
```

> **Validation Note:**
> - **Action:** validated (with accuracy correction)
> - **Detail:** The finding reports 8 errors but `basedpyright src/` actually reports **10 errors**.
> All 8 listed errors are confirmed valid and present in the output. However, 2 additional errors are
> **not listed** in the finding: `telegram_bot/handlers/alerts.py:69:32` (`reportIndexIssue` —
> `query_display[:30]` indexed on a value typed as `TextField` descriptor) and
> `telegram_bot/handlers/contact.py:143:42` (`reportAssignmentType` — `seller.telegram_id` typed as
> `BigIntegerField | None` assigned to `int | None`). Additionally, `builder.py:74` is listed as 1 error
> in the finding but basedpyright reports it as 2 separate errors (`__enter__` and `__exit__`).
> The finding's count of 8 includes both builder.py errors (1 entry -> 2 actual errors) but omits
> the 2 additional errors in `alerts.py` and `contact.py`. The core assertion (basedpyright reports
> type errors) is correct, and the `ad_copy.py:35` None-guard remains the highest operational risk
> (actual `AttributeError` crash). The recommendation to fix all errors and add basedpyright to CI
> remains valid and should include the 2 unlisted errors.
> - **See also:** ENT-001 (ad_copy.py:35 None-guard is an actual runtime crash, not just a typing issue;
> the `# pyright: ignore` at login.py:120 masks context-manager typing rather than real bugs)

**Recommendation:** (1) Add a `None` guard before `.strip()` at `ad_copy.py:35`. (2) For ORM
return-type errors, wrap field returns in `str()` casts (e.g. `str(self.slug)`,
`str(self.code)`, `str(item.slug)`, `str(self.image)`) matching the established pattern in
`locations/models.py:54,57` and `categories/models.py:62,65` `__str__` methods, which
already wrap `CharField`/`SlugField` returns in `str()`. Prefer `str()` over `field.value`
(not a standard Django model API) and over `pyright: ignore` directives, which mask the
underlying descriptor-vs-Python-type mismatch rather than resolving it. Applies to
`lookups/models.py:40,89`, `lookup_resolution.py:59,64`, `ads/models.py:472`, `alerts.py:69`,
and `contact.py:143`. (3) Investigate `builder.py:74` context-manager protocol mismatch. (4)
Fix `alerts.py:69` index on TextField descriptor. (5) Fix `contact.py:143` type assignment
mismatch. Consider adding `basedpyright` to CI as a gate. Effort: medium.

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

**Evidence:**
`grep -rn "send_alerts" docker/ docker-compose*.yml Makefile` -> 0 matches in
deployment files. `grep -rn "send_alerts" src/backend/apps/search/management/commands/` -> the command
exists at `send_alerts.py:26-29`. `docker/entrypoint-scheduler.sh:28-37` lists the 7 hourly commands
(explicitly excluding `send_alerts`). `test_alert_query.py:380,388,403` test the command.

Source verified:
- `src/backend/apps/search/management/commands/send_alerts.py:1-4`: docstring says
  "Runs once daily via cron."
- `docker/entrypoint-scheduler.sh:26-40`: 7 commands in `while True:` loop with
  `time.sleep(3600)` — none is `send_alerts`.
- `docker-compose.yml:123-174` (`web`), `docker-compose.yml:147-174` (`bot`): no cron container.
- `docker-compose.prod.yml:36-60` (`scheduler`): runs `entrypoint-scheduler.sh`, no `send_alerts`.
- `Makefile`: no `alerts` or `send_alerts` target (verified by reading full Makefile, 196 lines).
- `test_alert_query.py:380, 388, 403`: confirmed `call_command("send_alerts", "--dry-run")`.
- grep for `send_alerts` across `docker/`, `docker-compose*.yml`, and `Makefile`: **0 matches**.

> **Validation Note:**
> - **Action:** validated (with supplementary discovery)
> - **Detail:** The orphan finding is confirmed — `send_alerts` is fully implemented (179 lines) but
> absent from all scheduler/cron/Makefile wiring. **Supplementary discovery:** the command also cannot
> run even if wired — `send_alerts.py:13` imports
> `from aiogram.exceptions import TelegramBadRequest, TelegramForbidden`, but aiogram 3.x renamed
> `TelegramForbidden` to `TelegramForbiddenError`. This `ImportError` was confirmed via coverage output
> (`cov_tmp.txt:39-43`) and is independently flagged as Phase 08 finding SRH-003. The command is
> tested (3 tests in `test_alert_query.py:380,388,403`) but all fail with this ImportError. The
> finding's severity (LOW) understates the issue — the command is not just unwired, it is completely
> non-functional due to the import crash.
> - **Cross-phase dependency:** ENT-006 (wire into scheduler) depends on SRH-003 (Phase 08) fix
> (correct the `TelegramForbidden` -> `TelegramForbiddenError` import) as a prerequisite. Wiring
> `send_alerts` into `entrypoint-scheduler.sh` before fixing SRH-003 would add a broken command
> to the hourly loop.
> - **See also:** SRH-003 (`.ai/audit/08-search-fts/findings.md:95`)

**Recommendation:** Wire `send_alerts` into the scheduler as a daily job at 08:00 UTC (per
`docs/97-plans/phase-02-detailed-plan-1.md:317`). Add a daily loop to
`docker/entrypoint-scheduler.sh` with `subprocess.run([sys.executable, "src/backend/manage.py",
"send_alerts"])` and `time.sleep(86400)`, or add a cron entry following the bare-metal cron
pattern in `docs/01-spec/architecture-structure.md:205-214`. Select "wire" over "remove"
because saved search alerts are an active Phase 2 feature: US-B11 in
`docs/04-user-stories/buyer-stories.md:64-65`, listed in `docs/01-spec/spec-index.md:165` with
`AlertQueryService` and `SavedSearchNotification` tables in
`docs/02-database/db-schema.md:376-387`; the command is fully implemented (179 lines, tested
with 3 tests) and `AdvisoryLockId.ALERT_DELIVERY_TASK=9` is allocated and documented at
`docs/01-spec/architecture-structure.md:240`. A daily loop (not the hourly sweep loop, which
runs every 3600s) is needed because phase-2 plan specifies a 08:00 UTC daily schedule.
**Do not wire before fixing SRH-003** (`TelegramForbidden` -> `TelegramForbiddenError`
import), or the command will crash on import even when invoked. Effort: small (excluding
SRH-003 prerequisite).

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

**Evidence:**
`migrate_locked.py:25`:
`manage_py = Path(__file__).resolve().parents[3] / "manage.py"`. The module is at
`apps/core/utils/migrate_locked.py`; `parents[0]` = `utils`, `parents[1]` = `core`, `parents[2]` =
`apps`, `parents[3]` = `src/backend` -> `manage.py`. Any structural change breaks this chain.
Runtime test confirmed: `migrate_locked.main()` ran successfully (lock acquired/released, exited 0),
but this only works because the current path depth happens to be exactly 3.

Source verified:
```python
# src/backend/apps/core/utils/migrate_locked.py:25
manage_py = Path(__file__).resolve().parents[3] / "manage.py"
```

Path depth confirmed:
- File: `src/backend/apps/core/utils/migrate_locked.py`
- `parents[0]` = `utils`, `parents[1]` = `core`, `parents[2]` = `apps`, `parents[3]` = `src/backend`
- `manage.py` confirmed at `src/backend/manage.py` (verified via `Test-Path`).
- The path currently resolves correctly, but only by coincidence of the exact 4-level nesting.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The fragile path resolution is confirmed at `migrate_locked.py:25`. The code currently
> works because `parents[3]` resolves to `src/backend/` where `manage.py` exists. However, the
> recommendation to use `settings.BASE_DIR` is more appropriate than the misspelled
> `django.core.management.utilsgetprojectsettings` cited in the finding. The correct approach is
> `settings.BASE_DIR / "manage.py"` (since `BASE_DIR` is already computed in `base.py:16` as
> `Path(__file__).resolve().parent.parent.parent.parent`). This would be simpler and more robust than
> any path arithmetic. Adding a `Path.exists()` assertion as a minimum safeguard is also recommended.
> - **See also:** ENT-004 (migrate_locked.py surfaces the models-have-changes warning from the
> missing ads 0005 migration)

**Recommendation:** Use `settings.BASE_DIR / "manage.py"` (available in the Django settings module
already loaded via `django.setup()`) instead of hardcoded `parents[3]` depth. At minimum, add an
assertion that the resolved path exists. Effort: trivial.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 2 |

## Mandatory Fixes
- **ENT-004** — Generate the missing `ads` 0005 migration (`manage.py makemigrations ads`) and add a CI
  gate for `makemigrations --check --dry-run`. Must precede any deployment to ensure schema sync.
- **ENT-001** — Fix `LoginToken.objects.filter(...).update(returning=True).first()` in
  `src/telegram_bot/handlers/login.py:128-129`. Every `/start login_<token>` flow crashes.
- **SRH-003 (Phase 08) + ENT-006** — Fix the `TelegramForbidden` -> `TelegramForbiddenError` import
  in `send_alerts.py` (SRH-003), then wire `send_alerts` into the scheduler loop (ENT-006). Do not
  wire before fixing the import.

## Advisory Recommendations
- **ENT-002** — Move media utilities from `telegram_bot/services/media.py` to
  `apps/media/services/` and rewire 6 production + 3 test imports. Eliminates reverse-layer dependency.
- **ENT-003** — Replace `LocMemCache` with shared Redis (`django-redis`) in `base.py`
  and `docker-compose[.prod].yml`.
- **ENT-005** — Fix all 10 `basedpyright` errors (None-guard in `ad_copy.py:35`, ORM return-type
  mismatches in `ads/models.py:472`, `lookups/models.py:40,89`, `lookup_resolution.py:59,64`,
  `alerts.py:69` and `contact.py:143` (these 2 are unlisted in the original finding), context-manager
  protocol at `builder.py:74`). Add `basedpyright` to CI as a gate.
- **ENT-007** — Replace fragile `parents[3]` path resolution in `migrate_locked.py` with
  `settings.BASE_DIR / "manage.py"`.

## Doc Updates Needed
(None — all findings include in-source code evidence and file/line references. Minor path prefix
annotation corrections noted in ENT-001 validation note: `src/backend/src/` should be `src/`.)

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 5 | ENT-001, ENT-002, ENT-003, ENT-004, ENT-007 |
| Validated (with note) | 2 | ENT-005 (accuracy: 10 errors not 8; 2 unlisted), ENT-006 (supplementary ImportError crash; cross-phase dependency) |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

(None — all 7 findings are validated as real issues with confirmed evidence in source code,
runtime checks, or deployment configuration.)

### Merged Findings

(None — no findings share a root cause warranting consolidation across IDs.)

### Reclassified Findings

(None — all findings retain their originally assigned types.)

### Cross-Phase Conflicts & Dependencies

| From Finding | To Finding (Phase) | Relationship | Action Needed |
|---|---|---|---|
| ENT-006 | SRH-003 (Phase 08) | Dependency (prerequisite) | Fix SRH-003 (`TelegramForbidden` -> `TelegramForbiddenError`) before wiring ENT-006 into scheduler |

**No conflicts detected.** All findings across Phase 01 are internally consistent and do not conflict
with findings in other phases. ENT-006 and SRH-003 are complementary (different aspects of the same
broken `send_alerts` command), not conflicting. ENT-005's error count (10 vs 8) is a completeness
issue, not a conflict with any other finding.

### Rollout Safety Assessment

| Finding | Risk | Dependencies | Rollout Order |
|---|---|---|---|
| ENT-004 | Low (schema only — help_text change, no column type change) | None | 1st — schema sync must precede deployment |
| ENT-001 | High (active crash on every login-token claim) | None | 2nd — critical login flow |
| SRH-003 -> ENT-006 | Medium (broken command) | SRH-003 before ENT-006 | 3rd — fix import, then wire scheduler |
| ENT-002 | Medium (many affected files, no runtime impact) | None | 4th — refactoring, safe with re-export shim |
| ENT-003 | Low (infrastructure change) | Requires Redis service in compose | 5th — infra change, backward-compatible |
| ENT-005 | Low (type fixes, no runtime impact) | None | 6th — type fixes only |
| ENT-007 | None (path fix, no runtime impact) | None | 7th — trivial, low risk |

- **Circular dependencies:** None detected.
- **Hidden dependencies:** ENT-006 depends on SRH-003 (both Phase 01 and Phase 08 address
  `send_alerts.py` — the command must be importable before it can be scheduled).
- **Unsafe ordering:** Wiring `send_alerts` into the scheduler (ENT-006) before fixing the import
  crash (SRH-003) would inject a broken command into the hourly loop.
- **Backward compatibility:** ENT-002's module move can use a re-export shim during transition.
  ENT-004's migration is AlterField on `help_text` only (no column type change) — safe and additive.

### Warnings

- **ENT-001:** The `# pyright: ignore[reportGeneralTypeIssues]` annotation at `login.py:120` masks
  `transaction.atomic()` context-manager typing, NOT the real bug at line 128 (`update(returning=True)`).
  The actual crash site has no type-ignore annotation, meaning basedpyright does not flag ENT-001.
  Relying on a type checker alone would miss this runtime crash.
- **ENT-005:** `basedpyright src/` reports 10 errors (not 8 as stated in the finding). The 2 unlisted
  errors in `alerts.py:69` and `contact.py:143` are equally low-risk Django-ORM typing mismatches
  but should be included in any CI gate.
- **ENT-006:** The command's docstring (line 4: "Runs once daily via cron") is doubly misleading — the
  command neither runs via cron nor is it functional due to the `TelegramForbidden` ImportError.
  Two separate findings (ENT-006 Phase 01, SRH-003 Phase 08) address different aspects of the same
  broken command.

### Required Fixes
1. **ENT-004:** Generate `ads` 0005 migration immediately — deployment without it risks schema mismatch
   (confirmed via `makemigrations --check --dry-run`).
2. **ENT-001:** Fix the `update(returning=True).first()` crash — every `/start login_<token>` flow fails.
3. **SRH-003 + ENT-006:** Fix the `TelegramForbidden` import in `send_alerts.py` before wiring it into
   the scheduler, or remove the dead code path.

### Advisory Recommendations
1. **ENT-002:** Move media utilities to `apps/media/services/` to eliminate reverse-layer imports.
2. **ENT-003:** Add a shared Redis cache backend to `docker-compose[.prod].yml`.
3. **ENT-005:** Fix all 10 basedpyright errors and add basedpyright to CI.
4. **ENT-007:** Replace `parents[3]` with `settings.BASE_DIR` in `migrate_locked.py`.
