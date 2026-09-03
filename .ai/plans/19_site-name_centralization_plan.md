# Implementation Plan: Site Name Centralization (Problem 03)

**Source spec:** `.ai/problems/03_site-name_centralization_spec.md` (§15 priority order)
**Status:** Ready for execution
**Total task specs:** 11 (T1–T11, one dedicated verification task)
**Environment:** Windows · `uv` · PostgreSQL 18 in Docker · test DB on port 5433

---

## 1. Overview

Replaces 22 hardcoded user-facing occurrences of `"Mko Bazuna"` with a single
admin-configurable `SiteConfig` singleton (`name` CharField, default `"Bazuna"`).
The value is surfaced to **web templates** via a new `site_config` context
processor and to the **Telegram bot** via a shared `get_site_name()` /
`get_site_name_async()` service that reads the same DB row and shares one Redis
cache (prod) / LocMemCache (test) between the web and bot processes.

The internal project/package name `mko_bazuna` is **not** changed (Q4=B). No
third-party packages are introduced. The solution follows the established
`ModerationCriteria` singleton pattern (same app layer, same
cache-invalidate-on-`post_save` approach).

---

## 2. Path Mapping (spec shorthand → actual repo paths)

| Spec shorthand | Actual path |
|---|---|
| `apps/core/models.py` | `src/backend/apps/core/models.py` |
| `apps/core/admin.py` | `src/backend/apps/core/admin.py` |
| `apps/core/signals.py` | `src/backend/apps/core/signals.py` |
| `apps/core/apps.py` | `src/backend/apps/core/apps.py` |
| `apps/core/context_processors.py` | `src/backend/apps/core/context_processors.py` |
| `apps/core/utils/cache.py` | `src/backend/apps/core/utils/cache.py` |
| `apps/core/services/site_config.py` | `src/backend/apps/core/services/site_config.py` |
| `apps/core/services/__init__.py` | `src/backend/apps/core/services/__init__.py` |
| `apps/core/migrations/0001_initial.py` | `src/backend/apps/core/migrations/0001_initial.py` |
| `apps/core/migrations/0002_seed_default.py` | `src/backend/apps/core/migrations/0002_seed_default.py` |
| `config/settings/base.py` | `src/backend/config/settings/base.py` |
| `templates/...` | `src/backend/templates/...` |
| `telegram_bot/handlers/login.py` | `src/telegram_bot/handlers/login.py` |
| `telegram_bot/handlers/ad_create.py` | `src/telegram_bot/handlers/ad_create.py` |
| locale `.po` / `.mo` | `src/backend/locale/{ru,en,bs}/LC_MESSAGES/` |

---

## 3. Architecture & Key Findings

### 3.1 Existing singleton pattern (reference implementation)

`ModerationCriteria` (`apps/moderation/models.py:81-85`) uses `get_or_create(pk=1)`
at access time — **no data migration seeds it**. Its cache invalidation signal
(`apps/moderation/signals.py:23-31`) calls `_invalidate_criteria_cache()` which
wraps `invalidate_criteria_cache()` from `apps/core/utils/cache.py:44-53`. The
admin (`apps/moderation/admin.py:46-51`) sets `has_add_permission=False` and
`has_delete_permission=False`.

### 3.2 Migration convention finding (research result)

**No migration file anywhere in `src/backend/apps/*/migrations/` uses
`migrations.RunPython` to seed data.** The only `RunPython`-adjacent code is a
stale conftest comment (`currencies/tests/conftest.py:6`) and a docstring
(`currencies/management/commands/load_exchange_rates.py:4`). Seed data for the
currencies app is loaded via the `load_exchange_rates` management command
called from `src/backend/conftest.py:61` (`_restore_test_schema_post_db_setup`),
not a migration.

**Decision:** The spec (§12.1, §3.5) **explicitly mandates** a
`0002_seed_default.py` `RunPython` data migration seeding
`SiteConfig.objects.get_or_create(pk=1, defaults={"name": "Bazuna"})`. This
deviates from the project's lazy-`get_or_create` convention but is **safe,
idempotent, and necessary**: without it the admin shows an empty singleton
changelist with `has_add_permission=False` (no way to add the row manually) until
the first web request triggers `get_singleton()`. The lazy `get_or_create` in
`get_singleton()` remains the test-time fallback (see §3.3). The plan follows the
spec's explicit directive.

### 3.3 Test environment behavior

- `config/settings/test.py:71-79` sets `MIGRATION_MODULES = DisableMigrations()`
  — all migrations (including `0002_seed_default.py`) are **skipped**; tables
  for new models are created via syncdb (model introspection).
- `src/backend/conftest.py:40-62` autouse fixture `_restore_test_schema_post_db_setup`
  runs `migrate --run-syncdb` (creates tables for unmigrated apps),
  `load_exchange_rates` (seeds currencies), and `setup_search_triggers`
  (re-creates FTS trigger DDL). No entry is needed here because `get_singleton()`
  creates the `SiteConfig` row lazily on first access.
- **Cache** is `LocMemCache` in tests (`test.py:47-51`), Redis in prod
  (`base.py:254-262`). Cache invalidation via `post_save` signal works in both.
- `apps/core` is currently a **non-migrated app** (`migrations/` contains only
  `__init__.py`). Adding `0001_initial.py` makes it migrated for dev/prod while
  `DisableMigrations` keeps test behavior unchanged (syncdb still creates the
  table).

### 3.4 `.po` / msgid state (verified)

- `"Mko Bazuna"` msgid exists in all 3 `.po` files → becomes `#~` (obsolete) after
  template changes. The `test_i18n_completeness.py` parser (line 38-76) skips
  `#~`-prefixed entries, so obsoletion is safe.
- `"Login to Mko Bazuna"` msgid exists → becomes `#~`; replaced by new
  `"Login to {{ site_name }}"` msgid needing ru/bs `msgstr`.
- `"Admin"` msgid **already exists** in all 3 `.po` files
  (ru: `"Админ"`, bs: `"Admin"`, en: `""`). The `{% trans "Admin" %}` in
  `review.html` therefore introduces **no new msgid** — no translation work needed.
- Privacy `blocktrans` msgids (L740-744, L749-752 in ru `.po`) change because the
  literal `"Mko Bazuna"` inside them is replaced by `{{ site_name }}`. The old
  msgids become `#~`; new msgids need ru/bs `msgstr` (substitute
  `{{ site_name }}` for `"Mko Bazuna"` in the existing translations).
- `.mo` files exist for all 3 locales (git-ignored but pre-built on disk).

### 3.5 Bot greeting (verified)

- `telegram_bot/handlers/login.py:47-49` — no-args `/start` greeting:
  `"Welcome! To login, use a deep-link: /start login_<your_token>"`
- `telegram_bot/handlers/ad_create.py:122-125` — `/post` start:
  `"Creating new ad. Please select a category.\nSend a keyword to search, or use /cancel to abort."`
- Bot tests (`test_login.py`, `test_ad_create.py`) do **not** assert on these
  exact greeting strings — they test `handle_login_orm` and `process_preview`
  respectively. New tests are required; existing tests need no greeting-text edits.
- Bot imports services via `from apps.core.services.<module> import <func>`
  (e.g., `ad_create.py:40`). New import:
  `from apps.core.services.site_config import get_site_name_async`.

### 3.6 No existing test breakage from template changes

Grep across `src/**/*.py` confirms **no test** asserts on `"Mko Bazuna"` text,
`<title>` content, or `"Login to Mko Bazuna"` in rendered output. Template
rendering tests (`test_auth_nav.py`, `test_privacy.py`) use Django's `Client`
which runs context processors automatically, so `site_name` is injected with no
test-fixture changes. The `test_i18n_completeness.py::test_no_hardcoded_visible_text`
skips `<title>` (`_SKIP_TAGS` at L123-134) and strips `{{ ... }}` variables
(L219), so `{{ site_name }}` introduces no violations.

## 3.7 Deviation / Ambiguity Register

| ID | Source | Issue | Plan Resolution | Status |
|---|---|---|---|---|
| D1 | Spec §2 Q3 ("Admin Panel") vs §3.1 E instances 21–22 ("Admin") | Spec §2 Q3 says `"Mko Bazuna Admin"` → `{% trans "Admin Panel" %} + {{ site_name }}` suffix. But §3.1 E explicitly shows `- Mko Bazuna Admin → - {{ site_name }} {% trans "Admin" %}` in both the `<title>` (L81) and `<a>` (L82) rows. | Use `{% trans "Admin" %}` (NOT "Admin Panel"), matching §3.1 E instances 21–22, §9.3 acceptance criteria (L419, L420), the plan's T8 task (L509), and codebase reality. | **Resolved — documented** |
| D2 | Spec §13 ("New msgid") | Spec §13 L532–538 and the "Additional risk" block claim `{% trans "Admin" %}` is a **new** msgid requiring `ru`/`bs` fill. Audit + Researcher confirmed the msgid `"Admin"` **already exists** in all 3 `.po` files: ru=`"Админ"` (L695), bs=`"Admin"` (L695), en=`""` (L692). | No translation work needed for `"Admin"`. Plan §3.4 (L103–105) and T8 (L509) already state this correctly. | **Resolved — spec error** |
| D3 | User task brief | User referenced `04_seed-coverage-test_spec.md` (unrelated — seed-coverage test reliability). The correct source spec is `03_site-name_centralization_spec.md`, cited in plan header (L3). | No action — plan already targets the correct spec. | **No-op** |
| D4 | `test_i18n_completeness.py` stale docstring | `test_i18n_completeness.py:4` docstring reads "Four guard tests" and lists 4 of 5 test names. The file actually has 5 tests (the omitted one is `test_no_raw_get_name_in_templates` at L281). | Not a plan error — noted here as an **implementor action item** for the docstring update. | **Implementor note** |

---

## 4. Risk Register

| Risk | Task | Severity | Mitigation |
|---|---|---|---|
| New `RunPython` data migration deviates from project convention (no prior precedent) | T1 | Low | Idempotent `get_or_create(pk=1, defaults={"name": "Bazuna"})`; safe under DisableMigrations (skipped in tests); `get_singleton()` lazy-create is the fallback. Documented in §3.2. |
| `apps/core` transitions from non-migrated → migrated app | T1 | Low | `DisableMigrations` in test settings means syncdb still creates the table; no test-DB behavior change. Dev/prod `migrate` applies the new migration. |
| Context processor adds a per-request `get_site_name()` call (cached, 1h TTL) | T3 | Low | Cache hit on all requests after first; `LocMemCache` in tests is trivially fast. Matches existing `header_context` DB-query pattern. |
| `post_save` signal fires on `get_or_create` during lazy singleton creation | T1 | Low | `get_or_create` only calls `save()` (and thus `post_save`) on **create**, not on get. The signal handler (`invalidate_site_config`) does a cache `delete` — a no-op when nothing is cached. |
| New msgids unfilled in `ru`/`bs` → `test_no_empty_msgstr` failure | T9 | High | T9 is the dedicated i18n gate; CI fails before merge. Exact msgstr values are specified in §7.2. |
| Bot greeting tests need new assertions | T10 | Low | Existing tests don't assert greeting text; T10 adds focused tests with `get_site_name` mocked. |
| Admin review.html `{% trans "Admin" %}` — already exists in `.po` | T8 | None | Verified in §3.4 — msgid `"Admin"` present in ru/bs/en with non-empty ru/bs. |
| `test_no_raw_get_name_in_templates` regression | T9 | Low | No raw `.get_name` introduced; `{{ site_name }}` is a context variable, not a model method call. |

---

## 5. Execution DAG

```
T1  (model + migration + signals + admin + apps + cache constants)
  │
  ▼
T2  (service: get_site_name, get_site_name_async)
  │
  ├──► T3  (web context processor + settings registration)
  │        │
  │        ├──► T5  (templates: components — header, header_catalog, footer)
  │        ├──► T6  (templates: auth + privacy — login_issue, privacy)
  │        ├──► T7  (templates: 14 title tags across 12 files)
  │        └──► T8  (templates: admin review page)
  │
  └──► T4  (bot greeting injection — login.py, ad_create.py)
        │
        │  (T5–T8 template changes + T4 bot changes complete)
        ▼
T9  (i18n pipeline: makemessages → fill .po → compilemessages)
  │  depends on T5, T6, T7, T8
  │
T10 (test updates + new tests)
  │  depends on T4 (bot), T5–T8 (templates), T2 (service), T3 (context processor)
  │
T11 (final verification — make test fast gate + i18n full suite)
     depends on T1, T9, T10
```

### 5.1 Dependency edges

| Task | blocked_by | Parallel-safe |
|---|---|---|
| T1 | — | root (must be first; all else depends on the model) |
| T2 | T1 | no (needs cache constants + model from T1) |
| T3 | T2 | no (needs service) |
| T4 | T2 | **yes** — independent of T3; can run in parallel with T3 |
| T5 | T3 | **yes** — different files from T6/T7/T8 |
| T6 | T3 | **yes** — different files from T5/T7/T8 |
| T7 | T3 | **yes** — different files from T5/T6/T8 |
| T8 | T3 | **yes** — different files from T5/T6/T7 |
| T9 | T5, T6, T7, T8 | no (makemessages must scan all changed templates) |
| T10 | T2, T3, T4, T5, T6, T7, T8 | no (tests assert on changed code) |
| T11 | T1, T9, T10 | no (final integration gate) |

### 5.2 Execution order (topological)

1. **T1** → 2. **T2** → {3a. **T3**, 3b. **T4** in parallel} → {4a. **T5**, 4b. **T6**, 4c. **T7**, 4d. **T8** in parallel} → **T9** → **T10** → **T11**

---

## 6. Task Specifications

---

### T1 — Core model layer: `SiteConfig` singleton, migrations, signals, admin

**Risk:** medium (schema change + new migration in a previously non-migrated app)
**Depends on:** none (root)
**Parallel-safe:** no

**Description:** Creates the `SiteConfig` singleton model modeled on
`ModerationCriteria` (`get_or_create(pk=1)`), the cache constants mirroring
`CRITERIA_CACHE_*`, the `post_save` cache-invalidation signal (registered in
`apps.py` `ready()`), the singleton admin, and both migrations
(`0001_initial` schema + `0002_seed_default` idempotent `RunPython` seed).

**Files:**
- `src/backend/apps/core/models.py` — **create** — `class SiteConfig` with
  `name = CharField(max_length=255, default="Bazuna")`, `Meta.db_table = "site_config"`,
  `__str__`, `get_singleton()` classmethod (`get_or_create(pk=1)`).
- `src/backend/apps/core/utils/cache.py` — **modify** — append
  `SITE_CONFIG_CACHE_KEY = "site_config:v1"`, `SITE_CONFIG_CACHE_TTL = 3600`,
  `get_cached_site_config()`, `set_cached_site_config(value)`, `invalidate_site_config()`
  (mirrors `get_cached_criteria`/`set_cached_criteria`/`invalidate_criteria_cache`).
- `src/backend/apps/core/signals.py` — **create** — `@receiver(post_save, sender=SiteConfig)`
  calling `invalidate_site_config()` with a `logger.info` line.
- `src/backend/apps/core/apps.py` — **modify** — add `ready()` to `CoreConfig`
  that does `import apps.core.signals` (mirrors `ModerationConfig.ready()` at
  `apps/moderation/apps.py:16-19`).
- `src/backend/apps/core/admin.py` — **create** — `SiteConfigAdmin` with
  `list_display = ["name"]`, `readonly_fields = []`, `has_add_permission → False`,
  `has_delete_permission → False` (mirrors `ModerationCriteriaAdmin` at
  `apps/moderation/admin.py:46-51`).
- `src/backend/apps/core/migrations/0001_initial.py` — **create** —
  `migrations.CreateModel` for `SiteConfig` (field: `name` CharField default
  `"Bazuna"`, `max_length=255`). No dependencies on other apps.
- `src/backend/apps/core/migrations/0002_seed_default.py` — **create** —
  `migrations.RunPython(seed_site_config, reverse_code=migrations.RunPython.noop)`
  where `seed_site_config` does `SiteConfig.objects.get_or_create(pk=1, defaults={"name": "Bazuna"})`.

**Semantic anchors:** `class SiteConfig`, `def get_singleton`,
`def ready`, `class SiteConfigAdmin`, `def has_add_permission`,
`def has_delete_permission`, `def invalidate_site_config`,
`SITE_CONFIG_CACHE_KEY`, `SITE_CONFIG_CACHE_TTL`.

**Acceptance criteria:**
- [ ] `SiteConfig` model exists with `name` CharField (default `"Bazuna"`, max 255).
- [ ] `get_singleton()` returns `pk=1` row via `get_or_create`.
- [ ] `apps.py` `CoreConfig.ready()` imports `apps.core.signals`.
- [ ] `SiteConfigAdmin` registered with `has_add_permission=False`, `has_delete_permission=False`.
- [ ] `0001_initial.py` creates the `site_config` table.
- [ ] `0002_seed_default.py` seeds `pk=1, name="Bazuna"` idempotently.

**Verification (inline):**
- `uv run ruff check src/backend/apps/core/`
- `uv run python -c "import django; django.setup(); from apps.core.models import SiteConfig; f=[x for x in SiteConfig._meta.get_fields() if x.name=='name'][0]; print(f.default)"` → `Bazuna`
- `uv run python src/backend/manage.py makemigrations core --check --dry-run` → no pending changes (migration matches model).

---

### T2 — Core service layer: `get_site_name` + `get_site_name_async`

**Risk:** low (new module, no shared-config changes)
**Depends on:** T1 (model + cache constants/helpers)
**Parallel-safe:** no (needs T1's cache helpers and model)

**Description:** Creates the `site_config` service that orchestrates cache +
model access with a defensive fallback. Mirrors the
`ModerationCriteria` service pattern (`_get_cached_criteria` in
`auto_moderation.py:30-78`) but simpler (single string vs dict).

**Files:**
- `src/backend/apps/core/services/site_config.py` — **create**:
  ```python
  def get_site_name() -> str:
      """Return the admin-configured site name (cached, 1h TTL).
      Falls back to 'Bazuna' if the DB or cache is unavailable (R-SN-05)."""
      from apps.core.utils.cache import (
          SITE_CONFIG_CACHE_KEY, SITE_CONFIG_CACHE_TTL,
          get_cached_site_config, set_cached_site_config,
      )
      from apps.core.models import SiteConfig

      cached = get_cached_site_config()         # cache.get(SITE_CONFIG_CACHE_KEY)
      if cached:
          return cached
      try:
          obj = SiteConfig.get_singleton()
          set_cached_site_config(obj.name)     # cache.set(key, name, TTL)
          return obj.name
      except Exception:
          logger.warning("SiteConfig unavailable; falling back to 'Bazuna'")
          return "Bazuna"

  async def get_site_name_async() -> str:
      """Async wrapper for bot handlers — runs get_site_name in a thread."""
      return await sync_to_async(get_site_name)()
  ```
  Imports: `logging`, `from asgiref.sync import sync_to_async`.
- `src/backend/apps/core/services/__init__.py` — **modify** — add
  `from .site_config import get_site_name, get_site_name_async` to the
  re-export block (mirrors the existing `from .contact import ...` /
  `from .translation import translate_text` pattern at `services/__init__.py:3-9`).

**Semantic anchors:** `def get_site_name`, `def get_site_name_async`,
`get_cached_site_config`, `set_cached_site_config`.

**Acceptance criteria:**
- [ ] `get_site_name() -> str` exists in `apps.core.services.site_config`.
- [ ] Returns cached value on cache hit; falls back to `"Bazuna"` on DB/cache error.
- [ ] `get_site_name_async() -> str` wraps `get_site_name` in `sync_to_async`.
- [ ] `get_site_name` / `get_site_name_async` re-exported in `services/__init__.py`.

**Verification (inline):**
- `uv run ruff check src/backend/apps/core/services/site_config.py`
- `uv run basedpyright src/backend/apps/core/services/site_config.py`
- Unit: `get_site_name() == "Bazuna"` (no DB rows pre-seeded; `get_or_create` creates
  the default row).

---

### T3 — Web context processor: inject `site_name` into all templates

**Risk:** low (adds a new context processor alongside existing ones)
**Depends on:** T2 (service must exist)
**Parallel-safe:** no (depends on T2)

**Description:** Adds a dedicated `site_config` context processor (single
responsibility — isolated from `header_context` per spec §5 architecture decision)
and registers it in the TEMPLATES setting.

**Files:**
- `src/backend/apps/core/context_processors.py` — **modify** — append:
  ```python
  def site_config(request) -> dict:
      """Inject the admin-configured site name into every template context."""
      from apps.core.services.site_config import get_site_name
      return {"site_name": get_site_name()}
  ```
  (Mirrors the lazy-import-inside-function pattern of `header_context` at
  `context_processors.py:49-50`.)
- `src/backend/config/settings/base.py` — **modify** — add
  `"apps.core.context_processors.site_config"` to the
  `TEMPLATES[0]["OPTIONS"]["context_processors"]` list (insert after
  `header_context` at `base.py:153`).

**Semantic anchors:** `def site_config` (in `context_processors`),
`TEMPLATES` context_processors list, `"apps.core.context_processors.site_config"`.

**Acceptance criteria:**
- [ ] `site_config` function returns `{"site_name": ...}`.
- [ ] Registered in `base.py` TEMPLATES context_processors.
- [ ] `header_context` is NOT modified (separate concern).

**Verification (inline):**
- `uv run ruff check src/backend/apps/core/context_processors.py`
- Render a template via Django `Client` and assert `"Bazuna"` appears in the
  rendered header (e.g., `Client().get("/").content` contains `Bazuna`).

---

### T4 — Bot greeting injection (parallel with T3)

**Risk:** medium (shared ORM, async context, two-process model)
**Depends on:** T2 (service must exist with `get_site_name_async`)
**Parallel-safe:** yes — independent of T3; can run concurrently with T3

**Description:** Injects the site name into the two bot entry-point greetings,
establishing the pattern that bot-visible config originates from the admin DB.

**Files:**
- `src/telegram_bot/handlers/login.py` — **modify**:
  - Add import `from apps.core.services.site_config import get_site_name_async`
    (alongside existing `apps.core.enums` import at L20).
  - No-args branch (L47-49): replace
    `"Welcome! To login, use a deep-link: /start login_<your_token>"` with
    `f"Welcome to {await get_site_name_async()}! To login, use a deep-link: /start login_<your_token>"`.
- `src/telegram_bot/handlers/ad_create.py` — **modify**:
  - Add import `from apps.core.services.site_config import get_site_name_async`
    (alongside existing `from apps.core.services.translation import translate_text`
    at L40).
  - `/post` handler `cmd_post` (L122-125): prepend site name to the start message
    → `f"Welcome to {await get_site_name_async()}! Creating new ad. Please select a category.\n"`
    + `"Send a keyword to search, or use /cancel to abort."`.

**Semantic anchors:** `handle_login_deep_link` (no-args branch), `cmd_post`,
`await get_site_name_async()`, import of `get_site_name_async`.

**Acceptance criteria:**
- [ ] Bot `/start` no-args greeting: `"Welcome to {site_name}! To login, use a deep-link: /start login_<your_token>"`.
- [ ] Bot `/post` start message: `"Welcome to {site_name}! Creating new ad. Please select a category.\nSend a keyword to search, or use /cancel to abort."`.
- [ ] Both fetch via `await get_site_name_async()` (runs in thread via `sync_to_async`).

**Verification (inline):**
- `uv run ruff check src/telegram_bot/handlers/login.py src/telegram_bot/handlers/ad_create.py`
- `uv run basedpyright src/telegram_bot/handlers/login.py src/telegram_bot/handlers/ad_create.py`

---

### T5 — Templates: component replacements (3 instances)

**Risk:** low (template-only, `{{ site_name }}` variable)
**Depends on:** T3 (context processor must provide `site_name`)
**Parallel-safe:** yes — distinct files from T6/T7/T8

**Description:** Replace `{% trans "Mko Bazuna" %}` with `{{ site_name }}` in
the three shared components.

| File | Semantic anchor | Change |
|---|---|---|
| `src/backend/templates/components/header.html` | `<a href="{% url 'ads:listings' %}">{% trans "Mko Bazuna" %}</a>` (L6) | → `{{ site_name }}` |
| `src/backend/templates/components/header_catalog.html` | `<a href="/">{% trans "Mko Bazuna" %}</a>` (L26) | → `{{ site_name }}` |
| `src/backend/templates/components/footer.html` | `<p>&copy; 2026 {% trans "Mko Bazuna" %}</p>` (L5) | → `{{ site_name }}` |

**Acceptance criteria:**
- [ ] All 3 `{% trans "Mko Bazuna" %}` → `{{ site_name }}`.

**Verification (inline):**
- `uv run python -c "import re; ... no 'Mko Bazuna' in {% trans %} form in these 3 files"`
- Render `header.html` / `footer.html` and assert site name renders (test client
  provides `site_name` from T3 context processor).

---

### T6 — Templates: auth + privacy blocktrans (5 instances)

**Risk:** low-medium (blocktrans rewrites with variable interpolation)
**Depends on:** T3
**Parallel-safe:** yes — distinct files from T5/T7/T8

**Description:** Converts title-tag substitutions and `{% trans %}`/`{% blocktrans %}`
wrappers to use `{{ site_name }}`. These introduce **new msgids** that
`makemessages` will extract (handled by T9).

| File | Line | Semantic anchor | Change |
|---|---|---|---|
| `users/login_issue.html` | 9 | `<title>{% trans "Login" %} - Mko Bazuna</title>` | `Mko Bazuna` → `{{ site_name }}` |
| `users/login_issue.html` | 16 | `{% trans "Login to Mko Bazuna" %}` | → `{% blocktrans with site_name=site_name %}Login to {{ site_name }}{% endblocktrans %}` |
| `privacy.html` | 9 | `<title>{% trans "Privacy Policy" %} - Mko Bazuna</title>` | `Mko Bazuna` → `{{ site_name }}` |
| `privacy.html` | 22 | `{% blocktrans %}This policy explains how Mko Bazuna collects...{% endblocktrans %}` | add `with site_name=site_name`, replace `Mko Bazuna` → `{{ site_name }}` |
| `privacy.html` | 29 | `{% trans "The data controller for this service is the operator of the Mko Bazuna classifieds board. You can contact us over Telegram at" %}` | → `{% blocktrans with site_name=site_name %}The data controller...{{ site_name }}...{% endblocktrans %}` |

**New msgids (for T9):**
1. `"Login to {{ site_name }}"`
2. `"This policy explains how {{ site_name }} collects, processes, and protects your data, including the cookies we set and the third parties we share data with.\n            Last updated: August 2026."`
3. `"The data controller for this service is the operator of the {{ site_name }} classifieds board. You can contact us over Telegram at"`

**Acceptance criteria:**
- [ ] login_issue L9 title uses `{{ site_name }}`.
- [ ] login_issue L16 uses `{% blocktrans with site_name=site_name %}Login to {{ site_name }}{% endblocktrans %}`.
- [ ] privacy L9 title uses `{{ site_name }}`.
- [ ] privacy L22 uses `blocktrans with site_name=site_name` + `{{ site_name }}`.
- [ ] privacy L29 trans → `blocktrans with site_name=site_name` + `{{ site_name }}`.

**Verification (inline):**
- `uv run ruff check` (no-op for templates, but lint-adjacent)
- Grep confirms no remaining user-facing `"Mko Bazuna"` in these 2 files (comment
  lines containing "Mko Bazuna" are exempt per Q4=B).

---

### T7 — Templates: 14 title tags → `{{ site_name }}` (12 files)

**Risk:** low (title tags are exempt from i18n scan)
**Depends on:** T3
**Parallel-safe:** yes — distinct files from T5/T6/T8

**Description:** Replace raw `"Mko Bazuna"` in `<title>` tags across 12 files
(instances 9–20 from the spec inventory). All follow the consistent pattern
` - Mko Bazuna</title>` → ` - {{ site_name }}</title>`. Title tags are in
`_SKIP_TAGS` (`test_i18n_completeness.py:132`) so no i18n test impact.

| File | Semantic anchor (title line) |
|---|---|
| `analytics/seller_dashboard.html` | `<title>{% trans "Trust Dashboard" %} - Mko Bazuna</title>` |
| `analytics/moderation_dashboard.html` | `<title>{% trans "Moderation Analytics" %} - Mko Bazuna</title>` |
| `cabinet/favorites.html` | `<title>{% trans "Favorites" %} - Mko Bazuna</title>` |
| `cabinet/settings.html` | `<title>{% trans "Settings" %} - Mko Bazuna</title>` |
| `cabinet/hub.html` | `<title>{% trans "Cabinet" %} - Mko Bazuna</title>` |
| `cabinet/search_history.html` | `<title>{% trans "Search history" %} - Mko Bazuna</title>` |
| `cabinet/saved_searches.html` | `<title>{% trans "Saved searches" %} - Mko Bazuna</title>` |
| `cabinet/saved_search_edit.html` | `<title>{% trans "Edit saved search" %} - Mko Bazuna</title>` |
| `ads/detail.html` | `<title>{{ ad\|get_title:LANGUAGE_CODE }} - Mko Bazuna</title>` |
| `ads/list.html` | `<title>{% if query %}...{% endif %} - Mko Bazuna</title>` |
| `ads/dashboard.html` | `<title>Dashboard - Mko Bazuna</title>` |
| `ads/edit.html` | `<title>{% trans "Edit Ad" %} - Mko Bazuna</title>` |

**Acceptance criteria:**
- [ ] All 12 title tags use `{{ site_name }}` instead of `Mko Bazuna`.

**Verification (inline):**
- `uv run python -m pytest src/backend/apps/core/tests/test_templates.py -m unit`
  (consent-banner guard test still passes — unrelated lines unchanged).
- Grep confirms no `"Mko Bazuna"` remains in any `<title>` of these 12 files.

---

### T8 — Templates: admin review page (2 instances)

**Risk:** low (admin template excluded from i18n scan; `"Admin"` msgid pre-exists)
**Depends on:** T3
**Parallel-safe:** yes — distinct file from T5/T6/T7

**Description:** Per Q3=A, `review.html` switches from the hardcoded
`"Mko Bazuna Admin"` suffix to `{{ site_name }}` + `{% trans "Admin" %}`. The
`"Admin"` msgid already exists in all 3 `.po` files (verified §3.4), so no new
translations are needed.

| File | Line | Semantic anchor | Change |
|---|---|---|---|
| `admin/moderation/review.html` | 11 | `<title>{% trans "Moderate Ad" %} {{ ad.id }} - Mko Bazuna Admin</title>` | `- Mko Bazuna Admin` → `- {{ site_name }} {% trans "Admin" %}` |
| `admin/moderation/review.html` | 23 | `<a href="/admin/">Mko Bazuna Admin</a>` | → `<a href="/admin/">{{ site_name }} {% trans "Admin" %}</a>` |

**Acceptance criteria:**
- [ ] review.html L11 title: `- {{ site_name }} {% trans "Admin" %}`.
- [ ] review.html L23 link: `{{ site_name }} {% trans "Admin" %}`.
- [ ] The moderation review view (`apps/moderation/views/review.py:46`) uses
  `render()` which applies all context processors, so `site_name` is available.

**Verification (inline):**
- `uv run python -m pytest src/backend/apps/ads/tests/test_i18n_completeness.py::test_no_raw_get_name_in_templates -m unit` (unchanged).
- Staff user renders `/admin/moderation/review/<id>/` and `site_name` appears.

---

### T9 — i18n pipeline (makemessages → fill → compilemessages)

**Risk:** high (CI gate — `test_no_empty_msgstr` blocks merge)
**Depends on:** T5, T6, T7, T8 (all template changes must precede extraction)
**Parallel-safe:** no

**Description:** Runs the project's i18n pipeline (Makefile targets at
`Makefile:167-176`) to extract the 3 new msgids from T6, mark the 4 old msgids
(`"Mko Bazuna"`, `"Login to Mko Bazuna"`, 2 privacy blocktrans strings) as `#~`
obsolete, manually fill `ru`/`bs` `msgstr`, and compile `.mo` files.

**New msgids to fill (ru/bs non-empty; en exempt — msgid is English):**

| New msgid | ru msgstr | bs msgstr |
|---|---|---|
| `"Login to {{ site_name }}"` | `"Вход в {{ site_name }}"` | `"Prijava na {{ site_name }}"` |
| privacy blocktrans L22 (with `{{ site_name }}` substituted for "Mko Bazuna") | existing ru translation with "Mko Bazuna"→"{{ site_name }}" | existing bs translation with "Mko Bazuna"→"{{ site_name }}" |
| data-controller blocktrans L29 (with `{{ site_name }}`) | existing ru translation with "Mko Bazuna"→"{{ site_name }}" | existing bs translation with "Mko Bazuna"→"{{ site_name }}" |

**"Admin" msgid:** already filled (ru=`"Админ"`, bs=`"Admin"`) — no action.

> **Note on extraction mechanics:** `make makemessages` runs
> `manage.py makemessages -l ru -l bs -l en --no-location` inside the dev-compose
> `web` container (`Makefile:168`). It requires the dev DB container to be up
> (`make up`). This is a **shell/runtime step**, not a code edit. In CI, the
> test entrypoint (`docker/entrypoint-test.sh`) runs `compilemessages` before
> pytest (`Dockerfile` / entrypoint ordering), so `.mo` must be current.

**Steps:**
1. `make makemessages` — extracts 3 new msgids, obsoletes 4 old msgids (`#~`).
2. Edit `src/backend/locale/{ru,en,bs}/LC_MESSAGES/django.po`: fill non-empty
   `msgstr` for the 3 new msgids in `ru` and `bs` (substitute
   `{{ site_name }}` for `"Mko Bazuna"` in existing privacy translations).
3. `make compilemessages` — regenerates `.mo` for all 3 locales.
4. Run `test_i18n_completeness.py` (5 tests) + `test_i18n_pipeline.py` (5 tests).

**Acceptance criteria:**
- [ ] 3 new msgids present with non-empty `ru`/`bs` `msgstr` (en may be empty).
- [ ] 4 old msgids marked `#~` (obsolete, skipped by parser).
- [ ] `"Admin"` msgid already present (no new translation).
- [ ] `make compilemessages` succeeds.
- [ ] `test_i18n_completeness.py` — all 5 tests pass.
- [ ] `test_i18n_pipeline.py` — all 5 tests pass.

**Verification (inline):**
- `docker compose --project-name mko-bazuna-dev ... run --rm web uv run python src/backend/manage.py compilemessages --locale ru --locale bs --locale en`
- `docker compose --project-name mko-bazuna-test ... run --rm -e PYTEST_OPTS="apps/ads/tests/test_i18n_completeness.py apps/ads/tests/test_i18n_pipeline.py" test`

---

### T10 — Test updates & new tests

**Risk:** low-medium (test-only changes, no production logic)
**Depends on:** T2 (service), T3 (context processor), T4 (bot), T5–T8 (templates)
**Parallel-safe:** no (exercises all changed code paths)

**Description:** Validates that `site_name` flows correctly to web templates
and bot messages, and that cache invalidation works on admin save.

**New test additions:**

1. **Context processor test** — `src/backend/apps/core/tests/test_context_processors.py`:
   Add a `TestSiteConfigContextProcessor` class (or add to existing file):
   - `test_site_config_returns_site_name_dict`: `site_config(request)` returns
     `{"site_name": "Bazuna"}` (uses `django_db` marker; `get_or_create` seeds
     the row).
   - `test_site_config_reflects_admin_change`: mock `get_site_name` → returns
     `"NewBigProject"`; assert `site_config(request) == {"site_name": "NewBigProject"}`.

2. **Bot greeting test** — `src/telegram_bot/tests/test_login.py` (or a new
   `test_site_name_injection.py`):
   - `test_start_no_args_greeting_includes_site_name`: calls
     `handle_login_deep_link` with a message containing only `/start` (no args),
     mocks `get_site_name_async` → `"Bazuna"`, asserts the answer contains
     `"Welcome to Bazuna!"`.
   - `test_post_start_message_includes_site_name`: calls `cmd_post`, mocks
     `get_site_name_async` → `"Bazuna"`, asserts the answer contains
     `"Welcome to Bazuna! Creating new ad"`.

3. **Cache invalidation test** — `src/backend/apps/core/tests/` (new
   `test_site_config.py` or add to existing):
   - `test_get_site_name_cached_then_invalidated`: call `get_site_name()` twice
     (second is cache hit); `SiteConfig` save → calls `invalidate_site_config`;
     third call re-reads from DB.
   - `test_get_site_name_fallback_on_db_error`: mock
     `SiteConfig.get_singleton` to raise → `get_site_name()` returns `"Bazuna"`
     (R-SN-05).

4. **Template rendering test** — `src/backend/apps/ads/tests/test_auth_nav.py`
   (or a new test): assert the rendered header/footer contains the site name
   on a public page (uses `Client` which runs context processors).

**No existing-test edits required** — grep confirmed no test asserts on
`"Mko Bazuna"` or exact title text (§3.6). The Django test `Client` automatically
provides `site_name` from the registered context processor.

**Acceptance criteria:**
- [ ] `test_site_config_returns_site_name_dict` passes.
- [ ] `test_start_no_args_greeting_includes_site_name` passes.
- [ ] `test_post_start_message_includes_site_name` passes.
- [ ] `test_get_site_name_cached_then_invalidated` passes.
- [ ] `test_get_site_name_fallback_on_db_error` passes.
- [ ] Existing template/render tests still pass (no regressions).

**Verification (inline):**
- `make test PYTEST_OPTS="-k 'site_config or site_name or context_processor or start_no_args or post_start'"`
- `make test PYTEST_OPTS="-k 'test_auth_nav or test_privacy'"` (regression check).

---

### T11 — Final verification (dedicated gate)

**Risk:** low (verification task)
**Depends on:** T1, T9, T10 (and transitively T2–T8)
**Parallel-safe:** no

**Description:** Runs the full fast-gate test suite plus the i18n completeness
suite to confirm no regressions and a clean i18n state.

**Verification steps:**
1. **Lint:** `uv run ruff check src/backend/apps/core/ src/telegram_bot/handlers/`
2. **Typecheck:** `uv run basedpyright src/backend/apps/core/ src/telegram_bot/handlers/`
3. **DB migration check:** `uv run python -c "import django; django.setup(); from django.core.management import call_command; call_command('makemigrations', '--check', '--dry-run', 'core')"` → no pending migrations.
4. **Fast gate:** `make test` (skips `seed` marker, ~1 min, reuses DB).
5. **i18n gate:** `make test PYTEST_OPTS="-k 'i18n'" ` — runs both
   `test_i18n_completeness.py` (5 tests) and `test_i18n_pipeline.py` (5 tests).
6. **Regression spot-checks:** `make test PYTEST_OPTS="-k 'test_auth_nav or test_privacy or test_ad_create or test_context_processors'"`.

**Pass criteria:**
- [ ] Lint clean on all changed paths.
- [ ] Typecheck clean on all changed paths.
- [ ] `makemigrations --check --dry-run core` → no pending changes.
- [ ] `make test` fast gate → 0 failures.
- [ ] All i18n completeness + pipeline tests pass.
- [ ] `test_no_raw_get_name_in_templates` passes (no regression).

---

## 7. Implementation Sequencing Summary

### 7.1 Critical ordering constraints

1. **T1 → T2**: the service layer cannot exist without the model + cache constants.
2. **T2 → {T3, T4}**: context processor and bot injection both import `get_site_name`/`get_site_name_async`.
3. **T3 → {T5, T6, T7, T8}**: templates depend on `site_name` being in context
   (the context processor). These four template tasks are **parallel-safe** (distinct
   files) and should be reviewed/executed concurrently.
4. **T9 after {T5,T6,T7,T8}**: `makemessages` must scan the final template state to
   extract correct msgids. Running it before all template edits produces stale
   `.po` files.
5. **T10 after {T4, T5-T8}**: tests exercise bot greeting text and template
   rendering, both of which must be complete.
6. **T11 last**: the final gate requires migrations committed (T1), `.mo`
   compiled (T9), and all new tests passing (T10).

### 7.2 Parallel execution groups

| Group | Tasks | Prerequisite |
|---|---|---|
| Phase 1 | T1 | — |
| Phase 2 | T2 | T1 |
| Phase 3 | T3, T4 (parallel) | T2 |
| Phase 4 | T5, T6, T7, T8 (parallel) | T3 |
| Phase 5 | T9 | T5, T6, T7, T8 |
| Phase 6 | T10 | T2, T3, T4, T5, T6, T7, T8 |
| Phase 7 | T11 | T1, T9, T10 |

### 7.3 Deployment order (prod)

1. Apply DB migration: `migrate` (creates `site_config` table + seeds `"Bazuna"`).
2. Deploy code: model, service, context processor, templates, bot handlers.
3. `make compilemessages` (build `.mo` from updated `.po`).
4. Restart web + bot processes (cache TTL 1h; signals invalidate on admin save).

---

## 8. Verification Strategy Summary

| Method | Scope | Owner task |
|---|---|---|
| `uv run ruff check` | Lint all changed files | Every task |
| `uv run basedpyright` | Type-check changed Python | T1, T2, T4, T10, T11 |
| `makemigrations --check --dry-run core` | Migration/schema drift | T1, T11 |
| `make test` | Fast gate (skips `seed`, ~1 min) | T10, T11 |
| `make test-recreate` | Fresh schema (`--create-db`) | T1 (model creation confirmed) |
| `test_i18n_completeness.py` | 5 i18n guard tests | T9, T11 |
| `test_i18n_pipeline.py` | 5 i18n pipeline tests | T9, T11 |
| Template render via `Client` | `site_name` appears in rendered HTML | T3, T10, T11 |
| Bot handler unit test | greeting includes `site_name` | T4, T10 |

### 8.1 Test environment reminder

Tests run inside Docker (`make test` / `make test-recreate`). The test DB
container must be running on port 5433:
```powershell
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db
```
Never run `uv run pytest` locally (DB unreachable on `localhost:5432`);
always route through the `test` Compose service. `.mo` files must be rebuilt
(`make compilemessages`) before the i18n tests run — the CI entrypoint
(`docker/entrypoint-test.sh`) does this automatically, but local runs require it.

---

## 9. Acceptance Criteria Cross-Reference

| Spec § | Acceptance criterion | Task(s) that satisfy |
|---|---|---|
| 9.1 `SiteConfig` model + singleton + cache + admin + data migration | T1 | T1 |
| 9.2 `get_site_name()` + context processor + registration + `get_site_name_async` | T2, T3 | T2, T3 |
| 9.3 22 template replacements (3+1+2+14+2) | T5, T6, T7, T8 | T5, T6, T7, T8 |
| 9.4 Bot `/start` + `/post` site name | T4 | T4 |
| 9.5 i18n pipeline (3 new msgids + 4 obsoleted) | T9 | T9 |
| 9.6 Admin runtime verification (cache invalidation) | T2, T10 | T10 |
| 9.7 No regressions (`test_no_raw_get_name_in_templates`, `make test`) | T11 | T11 |

---

## 10. Out of Scope (per spec §14 — do not touch)

- Per-language site names (Q1=B: single string).
- Internal project name `mko_bazuna` in docstrings, Dockerfile, Makefile, package metadata (Q4=B).
- `django.contrib.sites` framework.
- Third-party config packages (`django-constance`, `django-solo`, etc.).
- Bot message localization (bot messages remain English-only; only site name is injected).
- Ad creation FSM, moderation logic, or search functionality.
- Template comments / `.po` headers containing "Mko Bazuna" (non-user-facing).

---

*This plan reorders the spec's §15 priority list into a dependency-safe execution
DAG. The spec's conceptual task order (model → service → templates → bot → i18n
→ tests → verify) is preserved at the phase level but parallelized within phases
where files are independent.*
