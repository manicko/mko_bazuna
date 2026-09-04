# Specification: Site Name Centralization

**Status:** Final — incorporating PO decisions (Q1–Q5) and technical research findings  
**Version:** 1.0  
**Date:** 2026-09-02  
**Source Problem:** `.ai/problems/Problem_02.md` (RU)  
**Target Files:** `apps/core/models.py`, `apps/core/services/`, `apps/core/context_processors.py`, `apps/core/admin.py`, `apps/core/signals.py`, `apps/core/migrations/`, `config/settings/base.py`, `templates/components/header.html`, `templates/components/header_catalog.html`, `templates/components/footer.html`, `templates/users/login_issue.html`, `templates/privacy.html`, `templates/ads/list.html`, `templates/ads/detail.html`, `templates/ads/dashboard.html`, `templates/ads/edit.html`, `templates/cabinet/*.html` (6 files), `templates/analytics/seller_dashboard.html`, `templates/analytics/moderation_dashboard.html`, `templates/admin/moderation/review.html`, `telegram_bot/handlers/login.py`, locale/`.po`/`.mo` files (ru, bs, en)

---

## 1. Problem Summary

The brand name "Mko Bazuna" is hardcoded across 22 locations on the site (component templates, `<title>` tags, privacy policy text, login heading, and the moderator review page). The project name must remain `mko_bazuna` (internal), but users must see an admin-configurable site name — defaulting to "Bazuna" today, changeable to any value (e.g., "newbigproject") via the Django admin.

No mechanism currently exists for a runtime-editable site name. Additionally, the Telegram bot has no site branding in its user-facing messages; per Q5, the bot greeting must surface the same admin-configured name to establish the pattern that all bot-visible configuration flows from the admin.

---

## 2. PO Decisions

| Q | Answer | Implication |
|---|---|---|
| Q1 | **B** | Single site name string for all languages (not per-language). The value is independent of locale; `ru`/`bs`/`en` visitors all see the same admin-set name. |
| Q2 | **A** | Replace ALL 22 user-facing instances of "Mko Bazuna" with the dynamic `{{ site_name }}` variable. This includes `<title>` tags, `{% trans %}` blocks, `blocktrans` blocks, and admin review-page text. |
| Q3 | **A** | Admin/moderator review page (`admin/moderation/review.html`) uses `{{ site_name }}` dynamically — "Mko Bazuna Admin" becomes `{% trans "Admin Panel" %}` + `{{ site_name }}`-based suffix rendered via template variable. |
| Q4 | **B** | Update only user-facing occurrences. Non-user-facing strings (Python docstrings, template comments, `.po` headers, README, Makefile, Dockerfile, package names) are **NOT** changed — the internal project name remains `mko_bazuna`. |
| Q5 | **Add to bot** | The bot greeting (`/start` handler, no-args branch) and ad-creation start (`/post` command) must incorporate the site name. A shared `get_site_name()` service function provides the value from the DB, establishing the pattern that all bot-visible configuration originates from admin-editable admin data. |

---

## 3. Facts (Verified)

### 3.1 Occurrence Inventory — 22 Instances

**A. `{% trans "Mko Bazuna" %}` component instances (3)**

| # | File | Line | Current | Replacement |
|---|------|------|---------|-------------|
| 1 | `templates/components/header.html` | 6 | `<a href="...">{%% trans "Mko Bazuna" %}</a>` | `<a href="...">{{ site_name }}</a>` |
| 2 | `templates/components/header_catalog.html` | 26 | `<a href="...">{%% trans "Mko Bazuna" %}</a>` | `<a href="...">{{ site_name }}</a>` |
| 3 | `templates/components/footer.html` | 5 | `<p>&copy; 2026 {%% trans "Mko Bazuna" %}</p>` | `<p>&copy; 2026 {{ site_name }}</p>` |

**B. `{% trans "Login to Mko Bazuna" %}` heading (1)**

| # | File | Line | Current | Replacement |
|---|------|------|---------|-------------|
| 4 | `templates/users/login_issue.html` | 16 | `<h1>...{%% trans "Login to Mko Bazuna" %}</h1>` | `{% blocktrans with site_name=site_name %}Login to {{ site_name }}{% endblocktrans %}` |

**C. privacy.html embedded-in-text instances (2)**

| # | File | Line | Current | Replacement |
|---|------|------|---------|-------------|
| 5 | `templates/privacy.html` | 22 | `{% blocktrans %}This policy explains how Mko Bazuna collects...{% endblocktrans %}` | `{% blocktrans with site_name=site_name %}This policy explains how {{ site_name }} collects...{% endblocktrans %}` |
| 6 | `templates/privacy.html` | 29 | `{% trans "The data controller for this service is the operator of the Mko Bazuna classifieds board..." %}` | `{% blocktrans with site_name=site_name %}The data controller for this service is the operator of the {{ site_name }} classifieds board. You can contact us over Telegram at{% endblocktrans %}` |

**D. Hardcoded "Mko Bazuna" inside `<title>` tags (14)**

These are raw text (not `{% trans %}`-wrapped), so they produced no `.po` msgid. The i18n completeness test skips `<title>` content (`_SKIP_TAGS` includes `"title"`). Replacement is `{{ site_name }}` interpolation.

| # | File | Line | Current |
|---|------|------|---------|
| 7 | `templates/users/login_issue.html` | 9 | `<title>{% trans "Login" %} - Mko Bazuna</title>` |
| 8 | `templates/privacy.html` | 9 | `<title>{% trans "Privacy Policy" %} - Mko Bazuna</title>` |
| 9 | `templates/analytics/seller_dashboard.html` | 13 | `<title>{% trans "Trust Dashboard" %} - Mko Bazuna</title>` |
| 10 | `templates/analytics/moderation_dashboard.html` | 12 | `<title>{% trans "Moderation Analytics" %} - Mko Bazuna</title>` |
| 11 | `templates/cabinet/favorites.html` | 11 | `<title>{% trans "Favorites" %} - Mko Bazuna</title>` |
| 12 | `templates/cabinet/settings.html` | 10 | `<title>{% trans "Settings" %} - Mko Bazuna</title>` |
| 13 | `templates/cabinet/hub.html` | 9 | `<title>{% trans "Cabinet" %} - Mko Bazuna</title>` |
| 14 | `templates/cabinet/search_history.html` | 10 | `<title>{% trans "Search history" %} - Mko Bazuna</title>` |
| 15 | `templates/cabinet/saved_searches.html` | 10 | `<title>{% trans "Saved searches" %} - Mko Bazuna</title>` |
| 16 | `templates/cabinet/saved_search_edit.html` | 11 | `<title>{% trans "Edit saved search" %} - Mko Bazuna</title>` |
| 17 | `templates/ads/detail.html` | 13 | `<title>{{ ad\|get_title:LANGUAGE_CODE }} - Mko Bazuna</title>` |
| 18 | `templates/ads/list.html` | 10 | `<title>{% if query %}...{% endif %} - Mko Bazuna</title>` |
| 19 | `templates/ads/dashboard.html` | 12 | `<title>Dashboard - Mko Bazuna</title>` |
| 20 | `templates/ads/edit.html` | 9 | `<title>{% trans "Edit Ad" %} - Mko Bazuna</title>` |

**E. Admin/moderator review-page instances (2)**

| # | File | Line | Current | Replacement |
|---|------|------|---------|-------------|
| 21 | `templates/admin/moderation/review.html` | 11 | `<title>{% trans "Moderate Ad" %} {{ ad.id }} - Mko Bazuna Admin</title>` | `<title>{% trans "Moderate Ad" %} {{ ad.id }} - {{ site_name }} {% trans "Admin" %}</title>` |
| 22 | `templates/admin/moderation/review.html` | 23 | `<a href="/admin/">Mko Bazuna Admin</a>` | `<a href="/admin/">{{ site_name }} {% trans "Admin" %}</a>` |

> Note: `admin/moderation/review.html` is **excluded** from the i18n completeness test scan (`exclude_subpaths` includes `"admin/"`). Per Q3=A it still receives `{{ site_name }}` for consistency and runtime configurability.

### 3.2 Existing Patterns

**A. Singleton model pattern (`ModerationCriteria`):**
- File: `apps/moderation/models.py` L11-85
- `get_or_create(pk=1)` classmethod `get_singleton()`
- Cache: 5-minute TTL via `apps/core/utils/cache.py` (`CRITERIA_CACHE_KEY = "moderation_criteria:v1"`, `CRITERIA_CACHE_TTL = 300`)
- Invalidation: `post_save` receiver in `apps/moderation/signals.py` L23-31 calls `_invalidate_criteria_cache()`
- Admin: `apps/moderation/admin.py` — `has_add_permission` returns `False`, `has_delete_permission` returns `False`, `save_model()` tracks `updated_by`

**B. DB-backed i18n pattern (`LookupItem`):**
- File: `apps/lookups/models.py` L43-96
- `name_i18n = JSONField(null=True, blank=True)` with `{"ru": str, "bs": str, "en": str}` structure
- `get_name(locale)` fallback chain: locale → "ru" → slug
- Cache: `apps/lookups/services/cache_service.py` — 1-hour TTL (`CACHE_TTL = 3600`), signal-based invalidation

**C. Context processor pattern:**
- File: `apps/core/context_processors.py` — `header_context()` injects `bot_username`, `root_categories`, `cities`, etc. via DB queries at request time
- Registered in `config/settings/base.py` L146-155 as `"apps.core.context_processors.header_context"`
- Templates access context variables directly: `{{ bot_username }}`, `{{ LANGUAGE_CODE }}`

**D. Bot service pattern:**
- Bot imports from `apps.core.services` (e.g., `from apps.core.services.translation import translate_text` at `telegram_bot/handlers/ad_create.py` L40)
- DB access via `asgiref.sync.sync_to_async` wrappers (every helper function in `ad_create.py` L865+)
- Bot `/start` handler: `telegram_bot/handlers/login.py` L31-100 — no-args branch sends greeting at L47-49: `"Welcome! To login, use a deep-link: /start login_<your_token>"`
- Bot `/post` handler: `telegram_bot/handlers/ad_create.py` L100-125 — starts flow with `"Creating new ad. Please select a category."`

**E. Cache backend:**
- Production/test: Redis via `django-redis` (`config/settings/base.py` L254-262)
- Dev: overrides to `LocMemCache`
- `cache.delete_pattern` available on Redis backend (used in `LookupCacheService.invalidate_all()` at `cache_service.py` L79-80)

### 3.3 i18n Pipeline

- `make makemessages` runs with `--no-location` (no `--no-obsolete`); obsolete msgids are marked `#~` (`config/Makefile` L167-168)
- `make compilemessages` runs before pytest in CI (Docker entrypoint `docker/entrypoint-test.sh`)
- `.mo` files are git-ignored (`.gitignore` L55)
- `test_i18n_completeness.py` (4 tests, all `@pytest.mark.unit`, no DB):
  - `test_no_hardcoded_visible_text` — scans templates excluding `admin/`, `analytics/moderation_dashboard.html`, `components/feature_tag.html`; skips `_SKIP_TAGS` (script, style, head, title, input, etc.)
  - `test_extraction_completeness` — all msgids present in all 3 `.po` files
  - `test_no_empty_msgstr` — `ru`/`bs` must have non-empty `msgstr`; `en` exempt
  - `test_mo_compiled` — `.mo` exists for every `.po`
- The `_parse_po_entries` parser does NOT parse `#~`-prefixed obsolete entries (lines starting with `#~ msgid` are skipped because `stripped.startswith("msgid ")` fails after the `#~ ` prefix)

### 3.4 .po File State for "Mko Bazuna" Msgids

The msgid `"Mko Bazuna"` currently exists in all 3 `.po` files:
- `ru` (L682): `msgstr "Mko Bazuna"`
- `en` (L679): `msgstr ""` (empty — msgid is English)
- `bs` (L682): `msgstr "Mko Bazuna"`

The msgid `"Login to Mko Bazuna"` also exists:
- `ru` (L939): `msgstr "Вход в Mko Bazuna"`
- `en` (L936): `msgstr ""`
- `bs` (L938): `msgstr "Prijava na Mko Bazuna"`

The privacy.html blocktrans strings (lines 22, 29) have corresponding msgids with "Mko Bazuna" embedded as substring:
- `ru` (L744): full Russian translation of the paragraph
- `en` (L744 area): `msgstr ""`
- `bs` (L744): full Bosnian translation

### 3.5 Application / Module Layout

| Path | Current State | Action |
|------|--------------|--------|
| `apps/core/models.py` | **Does not exist** | Create with `SiteConfig` model |
| `apps/core/admin.py` | **Does not exist** | Create with singleton admin |
| `apps/core/signals.py` | **Does not exist** | Create `post_save` invalidation signal |
| `apps/core/migrations/` | Empty `__init__.py` only | Create `0001_initial.py` + `0002_siteseed.py` (or combined) |
| `apps/core/services/` | Has `translation.py` + `contact.py` | Add `site_config.py` |
| `apps/core/apps.py` | `CoreConfig` (no signal import) | Add `import apps.core.signals` in `ready()` |
| `apps/core/context_processors.py` | `header_context()` exists | Add `site_name` key OR new context processor |
| `config/settings/base.py` L146-155 | Context processors registered | Register new `site_config` context processor |
| `telegram_bot/handlers/login.py` | `/start` handler with greeting | Inject site name into no-args greeting |
| `telegram_bot/handlers/ad_create.py` | `/post` handler | Inject site name into start message |

---

## 4. Assumptions

1. **Dev-only environment:** No production data to migrate. Migrations are created fresh for the test DB container. Data migration to seed the default site name can run safely.
2. **No `django.contrib.sites`:** The project does not use Django's built-in sites framework (`INSTALLED_APPS` at `base.py` L94-123`). A custom `SiteConfig` singleton is the correct approach — not a reuse of `django.contrib.sites`.
3. **Single string, not per-language:** Per Q1=B, the site name is one string displayed identically in all locales. No `name_i18n` JSONField is needed; a plain `CharField` is sufficient and avoids unnecessary complexity.
4. **Bot and web share the same DB:** The two-process model (web gunicorn + bot aiogram) share one PostgreSQL database and one Django project. Both can read the `SiteConfig` singleton directly via the ORM. Cache invalidation propagates across processes via Redis (shared cache backend).
5. **Cache TTL of 1 hour** matches the existing `LookupCacheService` pattern — acceptable because site name changes are infrequent (admin action) and 1-hour staleness is tolerable. Signal invalidation provides immediate refresh on save.
6. **Admin will seed once:** The data migration creates `SiteConfig(pk=1, name="Bazuna")` if it doesn't exist; admin edits thereafter via Django admin.

---

## 5. Architecture Decision

**Chosen: Option A — Custom `SiteConfig` singleton model in `apps/core`**

This follows the established `ModerationCriteria` singleton pattern (same app layer, same caching/invalidation approach) rather than reusing `LookupItem` (semantic abuse — `LookupItem` is catalogue reference data, not site configuration) or introducing third-party packages (`django-sites`, `django-constance` — unnecessary dependency for one string).

| Aspect | Decision |
|--------|----------|
| Model location | `apps/core/models.py` (new file) |
| Model pattern | Singleton: `pk=1`, `get_or_create(pk=1)` via `get_singleton()` classmethod |
| Field | `name = models.CharField(max_length=255, default="Bazuna")` (single string, NOT per-language) |
| Cache | Django cache, key `"site_config:v1"`, TTL 3600s (1 hour) — matches `LookupCacheService` |
| Invalidation | `post_save` receiver on `SiteConfig` calls cache delete — matches `ModerationCriteria` signal pattern |
| Service layer | `apps/core/services/site_config.py` with `get_site_name() -> str` (cached, sync) and `get_site_name_async() -> str` (sync_to_async wrapper for bot) |
| Web injection | New context processor `apps.core.context_processors.site_config` returning `{"site_name": get_site_name()}`, registered in `base.py` TEMPLATES |
| Bot injection | `telegram_bot/handlers/login.py` and `ad_create.py` call `get_site_name_async()` within `sync_to_async` wrappers |
| Admin | `apps/core/admin.py` — `SiteConfigAdmin` with `has_add_permission=False`, `has_delete_permission=False`, `list_display=["name"]` |
| Migration | `apps/core/migrations/0001_initial.py` (model + migration in one step per dev workflow); data migration seeds default "Bazuna" |

### Why not `name_i18n` JSONField?

Although the codebase uses `name_i18n` for catalogue data (`LookupItem`, `Category`, `City`), the PO explicitly chose Q1=B (single string for all languages). A `CharField` is simpler, avoids the `get_name(locale)` fallback machinery, and matches the user's stated requirement that "today Bazuna, tomorrow NewBigProject" — a single value visible identically to all visitors. If per-language site names are needed later, the field can be upgraded to `name_i18n` without changing the service/context-processor interface.

### Why not extend `header_context`?

`header_context` already performs DB queries (categories, cities) per request. While `site_name` could be added there, a dedicated `site_config` context processor isolates the singleton concern, follows the single-responsibility principle, and is easier to test/mocks independently. The bot service function is shared (not duplicated in the context processor).

---

## 6. Data Model

### 6.1 `SiteConfig` Singleton

**File:** `apps/core/models.py` (new)

```python
class SiteConfig(models.Model):
    """
    Site configuration singleton. Exactly one row (pk=1) exists.
    Edited by admin via Django admin. The ``name`` field is the
    user-visible site/brand name displayed site-wide and in the
    Telegram bot.
    """
    name = models.CharField(
        max_length=255,
        default="Bazuna",
        help_text="User-visible site name (displayed in header, footer, title tags, and bot)",
    )

    class Meta:
        db_table = "site_config"

    def __str__(self) -> str:
        return f"SiteConfig(name={self.name})"

    @classmethod
    def get_singleton(cls) -> SiteConfig:
        """Get the singleton instance, creating it if necessary."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```

### 6.2 Cache Keys

**File:** `apps/core/utils/cache.py` (add to existing module)

```
SITE_CONFIG_CACHE_KEY = "site_config:v1"
SITE_CONFIG_CACHE_TTL = 3600  # 1 hour — matches LookupCacheService
```

Follow existing `CRITERIA_CACHE_*` pattern: `get_cached_site_config()`, `set_cached_site_config()`, `invalidate_site_config()`.

### 6.3 Service Layer

**File:** `apps/core/services/site_config.py` (new)

```python
def get_site_name() -> str:
    """Return the admin-configured site name (cached, 1h TTL)."""
    # 1. Check cache by SITE_CONFIG_CACHE_KEY
    # 2. If miss: SiteConfig.get_singleton() → cache set → return name
    # 3. If DB error: return fallback "Bazuna" (never break request)
```

Bot-side async wrapper using `sync_to_async`:

```python
async def get_site_name_async() -> str:
    """Async wrapper for bot handlers (runs get_site_name in thread)."""
    return await sync_to_async(get_site_name)()
```

---

## 7. Implementation Tasks

### Task 1: Create `SiteConfig` model and migration

**File:** `apps/core/models.py` (create)  
**File:** `apps/core/signals.py` (create)  
**File:** `apps/core/apps.py` (modify — add signal import in `ready()`)  
**File:** `apps/core/admin.py` (create)  
**File:** `apps/core/migrations/0001_initial.py` (create)  
**File:** `apps/core/migrations/0002_seed_default.py` (create — data migration to seed `SiteConfig(name="Bazuna")`)

Steps:
- Define `SiteConfig` model with `name` CharField (default "Bazuna")
- Implement `get_singleton()` classmethod (same pattern as `ModerationCriteria`)
- Create `post_save` signal receiver in `apps/core/signals.py` that calls `invalidate_site_config()`
- Register signal in `apps/core/apps.py` `ready()` via `import apps.core.signals`
- Register `SiteConfigAdmin` in `apps/core/admin.py` with singleton constraints
- Generate migration `0001_initial.py` for the model
- Generate data migration `0002_seed_default.py` using `RunPython` to `get_or_create(pk=1, defaults={"name": "Bazuna"})` — idempotent, safe for fresh DB and existing deployments

### Task 2: Create site config service

**File:** `apps/core/services/site_config.py` (create)

Steps:
- `get_site_name()` — cached sync function, 1h TTL, returns `SiteConfig.get_singleton().name` with cache
- Fallback to `"Bazuna"` if DB query fails (defensive — never breaks web or bot)
- `invalidate_site_config()` — cache delete helper
- Add `get_cached_site_config()`, `set_cached_site_config()` to `apps/core/utils/cache.py`
- `get_site_name_async()` — `sync_to_async` wrapper for bot

### Task 3: Register context processor

**File:** `config/settings/base.py` (modify)  
**File:** `apps/core/context_processors.py` (modify — add `site_config` function)

Steps:
- Add `site_config` function to `apps/core/context_processors.py` returning `{"site_name": get_site_name()}`
- Register `"apps.core.context_processors.site_config"` in `TEMPLATES[0]["OPTIONS"]["context_processors"]` (base.py L146-155)
- Verify `header_context` is not duplicated (keep separate context processor)

### Task 4: Replace all 22 template instances

Replace "Mko Bazuna" with `{{ site_name }}` / `{{ site_name|... }}` / `blocktrans` variables:

| # | File | Line | Change |
|---|------|------|--------|
| 1 | `templates/components/header.html` | 6 | `{% trans "Mko Bazuna" %}` → `{{ site_name }}` |
| 2 | `templates/components/header_catalog.html` | 26 | `{% trans "Mko Bazuna" %}` → `{{ site_name }}` |
| 3 | `templates/components/footer.html` | 5 | `{% trans "Mko Bazuna" %}` → `{{ site_name }}` |
| 4 | `templates/users/login_issue.html` | 16 | `{% trans "Login to Mko Bazuna" %}` → `{% blocktrans with site_name=site_name %}Login to {{ site_name }}{% endblocktrans %}` |
| 5 | `templates/privacy.html` | 22 | blocktrans: add `with site_name=site_name`, replace "Mko Bazuna" → `{{ site_name }}` |
| 6 | `templates/privacy.html` | 29 | trans → blocktrans with variable: replace "Mko Bazuna" → `{{ site_name }}` |
| 7-20 | 14 title tags | various | `Mko Bazuna` → `{{ site_name }}` (raw text replacement) |
| 21 | `templates/admin/moderation/review.html` | 11 | `- Mko Bazuna Admin` in title → `- {{ site_name }} {% trans "Admin" %}` |
| 22 | `templates/admin/moderation/review.html` | 23 | `Mko Bazuna Admin` → `{{ site_name }} {% trans "Admin" %}` |

For the 14 title tags (instances 7-20), the pattern is consistent: ` - Mko Bazuna</title>` → ` - {{ site_name }}</title>`. The title tag is exempt from the i18n test scan, and `{{ site_name }}` is stripped by the test's regex, so no test impact.

### Task 5: Inject site name into bot

**File:** `telegram_bot/handlers/login.py` (modify)  
**File:** `telegram_bot/handlers/ad_create.py` (modify)

Steps:
- In `login.py` `handle_login_deep_link()` no-args branch (L47-49): prepend greeting with site name: `"Welcome to {site_name}! To login, use a deep-link: /start login_<your_token>"` — fetch via `await get_site_name_async()` inside `sync_to_async`
- In `ad_create.py` `cmd_post()` (L122-125): prepend site name to the "Creating new ad" message: `"Welcome to {site_name}! Creating new ad. Please select a category..."` — fetch via `await get_site_name_async()`

### Task 6: Update `.po` files — new and obsoleted msgids

**Files:** `src/backend/locale/{ru,en,bs}/LC_MESSAGES/django.po`

**Obsoleted msgids** (will be auto-marked `#~` by `make makemessages`):
- `"Mko Bazuna"` (was trans-wrapped in header, footer, header_catalog)
- `"Login to Mko Bazuna"` (was trans-wrapped in login_issue.html)
- `"This policy explains how Mko Bazuna collects, processes, and protects your data..."` (blocktrans in privacy.html:22)
- `"The data controller for this service is the operator of the Mko Bazuna classifieds board. You can contact us over Telegram at"` (trans in privacy.html:29)

These obsoleted entries are NOT parsed by `test_i18n_completeness.py`'s `_parse_po_entries` (lines starting with `#~` are skipped), so they will not cause test failures.

**New msgids** (created by `make makemessages` after template changes):
1. `"Login to {{ site_name }}"` (from login_issue.html blocktrans)
2. `"This policy explains how {{ site_name }} collects, processes, and protects your data, including cookies we set and third parties we share data with.\n            Last updated: August 2026."` (privacy.html:22 blocktrans)
3. `"The data controller for this service is the operator of the {{ site_name }} classifieds board. You can contact us over Telegram at"` (privacy.html:29 blocktrans)

**Manual fill required** (CRITICAL — `test_no_empty_msgstr` checks ru/bs):
| New msgid | ru msgstr | bs msgstr | en msgstr |
|-----------|-----------|-----------|-----------|
| `"Login to {{ site_name }}"` | `"Вход в {{ site_name }}"` | `"Prijava na {{ site_name }}"` | `""` (exempt) |
| privacy blocktrans (msg 2) | Replace "Mko Bazuna" → "{{ site_name }}" in existing Russian translation | Replace "Mko Bazuna" → "{{ site_name }}" in existing Bosnian translation | `""` |
| data controller blocktrans (msg 3) | Replace "Mko Bazuna" → "{{ site_name }}" in existing Russian translation | Replace "Mko Bazuna" → "{{ site_name }}" in existing Bosnian translation | `""` |

**Pipeline:** `make makemessages` → manually fill new msgstrs → `make compilemessages`

### Task 7: Run i18n pipeline + completeness test

Steps:
1. `make makemessages` — extracts new msgids, obsoletes old ones (`#~`)
2. Edit `django.po` files: fill `ru`/`bs` msgstr for the 3 new msgids (substituting `{{ site_name }}` for "Mko Bazuna" in privacy translations)
3. `make compilemessages` — generates `.mo` files
4. Run `test_i18n_completeness.py` (4 tests) — all must pass

### Task 8: Create data migration / update seed

**File:** `apps/core/migrations/0002_seed_default.py` (or combined with `0001_initial.py`)

Steps:
- Idempotent `RunPython` that does `SiteConfig.objects.get_or_create(pk=1, defaults={"name": "Bazuna"})`
- If singleton already exists (e.g., from a prior deploy), name is unchanged (admin may have already set it)

---

## 8. Business Rules

| Rule ID | Rule |
|---------|------|
| R-SN-01 | The site name is a single, locale-independent string stored in `SiteConfig.name`. All visitors (ru, bs, en) see the same value. |
| R-SN-02 | The default value is "Bazuna". Admin can change it at any time via Django admin. |
| R-SN-03 | Template rendering must never hardcode "Mko Bazuna" or "Bazuna" — all 22 instances use `{{ site_name }}` (or `blocktrans` with `site_name` variable). |
| R-SN-04 | The site config value is cached for 1 hour. Cache is invalidated immediately on admin save via `post_save` signal. |
| R-SN-05 | If the `SiteConfig` singleton or cache is unavailable, `get_site_name()` falls back to `"Bazuna"` — the site and bot never break. |
| R-SN-06 | The internal project/package name remains `mko_bazuna` in all code, docstrings, Dockerfile, Makefile, and package metadata. Only user-visible text changes. |
| R-SN-07 | The Telegram bot surfaces the site name in its `/start` (no-args greeting) and `/post` (ad creation start) messages, using the same DB-backed `get_site_name()` service. |

---

## 9. Acceptance Criteria

### 9.1 Site Name Configuration

- [ ] `SiteConfig` model exists in `apps/core/models.py` with `name` CharField (default "Bazuna")
- [ ] Singleton pattern: `SiteConfig.get_singleton()` returns the `pk=1` row, creating it if absent
- [ ] Cache: 1-hour TTL, invalidated on `post_save` via `apps/core/signals.py`
- [ ] Admin: `SiteConfigAdmin` registered with `has_add_permission=False`, `has_delete_permission=False`
- [ ] Data migration seeds `SiteConfig(pk=1, name="Bazuna")` if not existing

### 9.2 Context Processor / Service

- [ ] `get_site_name()` service function exists in `apps/core/services/site_config.py`
- [ ] Context processor `apps.core.context_processors.site_config` injects `site_name` into all templates
- [ ] Context processor registered in `config/settings/base.py` TEMPLATES
- [ ] `get_site_name_async()` available for bot use via `sync_to_async`

### 9.3 Template Replacements (22 instances)

- [ ] `{% trans "Mko Bazuna" %}` → `{{ site_name }}` in header.html, header_catalog.html, footer.html (3)
- [ ] `{% trans "Login to Mko Bazuna" %}` → `{% blocktrans with site_name=site_name %}Login to {{ site_name }}{% endblocktrans %}` (1)
- [ ] privacy.html:22 blocktrans → `{{ site_name }}` variable (1)
- [ ] privacy.html:29 trans → blocktrans with `{{ site_name }}` variable (1)
- [ ] 14 `<title>` tags: hardcoded "Mko Bazuna" → `{{ site_name }}` (14)
- [ ] review.html:11 title → `{{ site_name }}` + `{% trans "Admin" %}` (1)
- [ ] review.html:23 body link → `{{ site_name }}` + `{% trans "Admin" %}` (1)

### 9.4 Bot Integration

- [ ] Bot `/start` no-args greeting includes site name: `"Welcome to {site_name}! To login, use a deep-link: /start login_<your_token>"`
- [ ] Bot `/post` start message includes site name: `"Welcome to {site_name}! Creating new ad. Please select a category..."`

### 9.5 i18n Pipeline

- [ ] `make makessages` extracts 3 new msgids and obsoletes 4 old msgids (marked `#~`)
- [ ] New msgids have filled `msgstr` in `ru` and `bs` (empty in `en` is acceptable)
- [ ] `make compilemessages` succeeds (no errors)
- [ ] `test_i18n_completeness.py` — all 4 tests pass:
  - `test_no_hardcoded_visible_text`
  - `test_extraction_completeness`
  - `test_no_empty_msgstr`
  - `test_mo_compiled`

### 9.6 Admin Runtime Verification

- [ ] Django admin `SiteConfig` edit page shows single `name` field
- [ ] Saving a new name (e.g., "NewBigProject") immediately propagates to all templates on next request (cache invalidated)
- [ ] Saving a new name immediately propagates to bot messages on next call (shared Redis cache)

### 9.7 No Regressions

- [ ] `test_no_raw_get_name_in_templates` still passes (no raw `.get_name` calls introduced)
- [ ] All existing tests pass (fast gate: `make test`)

---

## 10. Definition of Done (i18n)

Per project rule #16 and `docs/01-spec/i18n-spec.md` §Development & CI Integration:

1. All new/modified user-visible strings wrapped in `{% trans %}` / `{% blocktrans %}` / `gettext`
2. New msgids extracted into all three `.po` files (ru, bs, en) via `make makemessages`
3. `ru` and `bs` `msgstr` non-empty for all new msgids (manually filled); `en` may be empty
4. `make compilemessages` succeeds — `.mo` files generated for all locales
5. `test_i18n_completeness.py` — all 4 tests pass on fast gate
6. Obsoleted msgids (old "Mko Bazuna" variants) are `#~`-prefixed and safely ignored by the parser

The `{{ site_name }}` variable is exempt from `test_no_empty_msgstr` (it's not a msgid — it's a context variable). The `site_config` context processor name and the `SiteConfig` model field are internal strings (not user-visible), so they are NOT wrapped in gettext.

---

## 11. Test-by-Test Impact Analysis

| Test | Impact | Action Required |
|------|--------|-----------------|
| `test_no_hardcoded_visible_text` | **Pass** (no change needed) | `{{ site_name }}` in title tags is stripped (title in `_SKIP_TAGS`). `blocktrans with site_name=site_name` blocks are removed before text-node scanning. The variable `{{ site_name }}` is stripped by `re.sub(r"{{.*?}}", "", cleaned)`. |
| `test_extraction_completeness` | **New msgids** (3) must exist in all 3 `.po` | `make makemessages` adds them; must verify all 3 locales present |
| `test_no_empty_msgstr` | **CRITICAL FAIL** if new msgids unfilled in ru/bs | Must manually fill 3 new msgids with `ru` + `bs` translations before test run |
| `test_mo_compiled` | **FAIL** if `.mo` not rebuilt | Must run `make compilemessages` after filling `.po` |
| `test_no_raw_get_name_in_templates` | **Pass** (no raw `.get_name` introduced) | N/A |
| Existing template/render tests | **Potential impact** — title tags now contain `{{ site_name }}` variable | Template tests that assert exact title text must be updated to expect dynamic value; the `context_processors` fixture must provide `site_name` in test requests (or mock `get_site_name`) |
| Bot handler tests | **Impact** — `/start` and `/post` messages now include site name | Bot tests asserting exact greeting text must be updated; `get_site_name_async` should be mockable |
| i18n pipeline test (`test_i18n_pipeline.py`) | **Pass** (if pipeline steps followed) | Run `compilemessages` before test |

### Test fixture updates needed

- Any test that renders templates with `RequestFactory` or asserts on `<title>` content must have `site_name` in context. Either:
  - Add `site_name` mock to existing template context in tests, OR
  - Ensure test requests pass through the context processor (the test client does this automatically)
- Bot tests: mock `get_site_name` / `get_site_name_async` to return `"Bazuna"` (or any stub) so greeting assertions can match

---

## 12. Migration Strategy

### 12.1 Database Migration

1. Create `apps/core/models.py` with `SiteConfig` model
2. `python manage.py makemigrations core` → generates `apps/core/migrations/0001_initial.py`
3. Add data migration `apps/core/migrations/0002_seed_default.py`:
   ```python
   def seed_site_config(apps, schema_editor):
       SiteConfig = apps.get_model("core", "SiteConfig")
       SiteConfig.objects.get_or_create(pk=1, defaults={"name": "Bazuna"})
   ```
4. Migration runs once before web + bot start (per two-process startup: `migrate` service first)

### 12.2 .po/.mo Pipeline

1. Make all template changes (Tasks 4, 5)
2. `make makemessages` → extracts 3 new msgids, marks 4 old msgids as `#~` obsolete
3. Manually edit `django.po` files: fill `ru`/`bs` msgstr for the 3 new msgids
4. `make compilemessages` → generates `.mo` files for all locales
5. Run `test_i18n_completeness.py` → verify pass

### 12.3 Deployment Order

1. Apply DB migration (creates `site_config` table, seeds default "Bazuna")
2. Deploy code changes (model, service, context processor, templates, bot handlers)
3. Run `make compilemessages` (build `.mo` from updated `.po`)
4. Restart web + bot processes (cache TTL 1h; signals invalidate on admin save thereafter)

---

## 13. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Cache staleness after admin save | Low | Medium | `post_save` signal deletes cache key immediately; TTL is fallback only |
| Fallback "Bazuna" masks admin error | Low | Low | Fallback only triggers on DB/cache failure; logged via `logger.warning` |
| Bot greeting text assertions break in tests | High | Low | Mock `get_site_name` in bot tests; update expected strings |
| Template tests fail on missing `site_name` context | Medium | Medium | Ensure context processor is active in test settings; or add `site_name` to test context |
| New msgids unfilled in `.po` → `test_no_empty_msgstr` fail | High | High | Pre-filled in spec; CI gate catches before merge |
| Privacy policy blocktrans msgid change | Medium | Low | Old msgid becomes `#~` (skipped by parser); new msgid matches old translation minus "Mko Bazuna" → "{{ site_name }}" |
| Title tag `{{ site_name }}` causes XSS | Low | Low | Django autoescapes `{{ }}` by default; `site_name` is a plain CharField from admin |
| Admin review.html "Mko Bazuna Admin" → `{{ site_name }}` + "Admin" | Low | Low | review.html excluded from i18n test; but new `{% trans "Admin" %}` msgid needs filling |

### Additional risk: New `{% trans "Admin" %}` msgid

The review.html change introduces `{% trans "Admin" %}` (instance 21, 22). This is a NEW msgid that did not exist before. It must be added to all 3 `.po` files with filled translations:
| msgid | ru | bs | en |
|-------|-----|-----|-----|
| `"Admin"` | `"Админ"` | `"Admin"` | `""` |

This is covered by the `make makemessages` → fill → `compilemessages` pipeline.

---

## 14. Out of Scope

- Per-language site names (Q1=B explicitly chose single string)
- Changing internal project name `mko_bazuna` (package names, Dockerfile, Makefile, docstrings, README) — per Q4=B
- `django.contrib.sites` framework adoption
- Third-party config packages (`django-constance`, `django-solo`, etc.)
- Bot message localization (translating bot messages to bs/en) — bot messages are currently English-only; only site name injection is in scope
- Any changes to the ad creation FSM flow, moderation logic, or search functionality

---

## 15. Implementation Priority

1. **Model + migration** — `SiteConfig` singleton, cache utils, signals, admin, data migration
2. **Service + context processor** — `get_site_name()`, `get_site_name_async()`, context processor registration
3. **Template replacements** — all 22 instances (batch by file)
4. **Bot integration** — inject site name into `/start` greeting and `/post` message
5. **i18n pipeline** — `makemessages` → fill 3 new msgids (+ 1 "Admin") → `compilemessages` → run `test_i18n_completeness.py`
6. **Test updates** — update bot greeting assertions, template tests with `site_name` context
7. **Verification** — `make test` (fast gate)

---

## 16. Research References

- `apps/moderation/models.py` L11-85 — `ModerationCriteria` singleton pattern (model + `get_singleton()`)
- `apps/moderation/services/auto_moderation.py` L27-91 — cache get/set/invalidate pattern (`CRITERIA_CACHE_KEY`, `CRITERIA_CACHE_TTL = 300`)
- `apps/moderation/signals.py` L23-31 — `post_save` signal receiver pattern for cache invalidation
- `apps/moderation/admin.py` L29-57 — singleton admin with `has_add_permission=False` / `has_delete_permission=False`
- `apps/lookups/services/cache_service.py` L1-92 — 1-hour TTL cache + `invalidate_all()` / `delete_pattern`
- `apps/core/utils/cache.py` L1-53 — cache key/TTL/get/set/invalidate helper structure
- `apps/core/context_processors.py` L27-87 — `header_context()` DB-query context processor pattern
- `config/settings/base.py` L94-123 — `INSTALLED_APPS` (no `django.contrib.sites`)
- `config/settings/base.py` L146-155 — TEMPLATES context_processors registration
- `config/settings/base.py` L254-262 — Redis cache backend (shared web + bot)
- `telegram_bot/handlers/login.py` L31-100 — `/start` handler with no-args greeting
- `telegram_bot/handlers/ad_create.py` L100-125 — `/post` handler with start message
- `apps/ads/tests/test_i18n_completeness.py` L38-76 — `_parse_po_entries` parser (skips `#~` entries)
- `apps/ads/tests/test_i18n_completeness.py` L87-107 — `_collect_template_files` with `exclude_subpaths`
- `apps/ads/tests/test_i18n_completeness.py` L123-134 — `_SKIP_TAGS` (includes "title")
- `docs/01-spec/i18n-spec.md` §i18n-strategy — split content (gettext for UI, `name_i18n` for catalogue)
- `docs/01-spec/i18n-spec.md` §Development & CI Integration — makemessages/compilemessages CI flow

---

*End of specification — ready for implementation planning.*
