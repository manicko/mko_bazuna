# Mko Bazuna — i18n Implementation Plan

## Overview

Multi-language support for ads (Russian, Bosnian, English) with separate column storage, PostgreSQL FTS per language, and Django gettext for UI strings.

---

## Phase 1: Foundation (HIGH Priority)

### Task 1.1: Create LanguageLocale StrEnum
**Target:** `src/backend/apps/core/enums.py`

**Changes:**
- Add `LanguageLocale` StrEnum with `RUSSIAN = "ru"`, `BOSNIAN = "bs"`, `ENGLISH = "en"` values
- Add `fts_config` property returning appropriate PostgreSQL text search configuration:
  - `ru` → `"russian"`
  - `bs` → `"simple"` (PG18 has no native Bosnian config)
  - `en` → `"english"`

**Dependencies:** None

---

### Task 1.2: Database Migration - Language Columns for Ads
**Target:** `src/backend/apps/ads/migrations/0004_ad_i18n_columns.py`

**Changes:**
- Add `title_en` (CharField, max_length=200, blank=True, null=True)
- Add `description_en` (TextField, blank=True, null=True)
- Add `title_bs` (CharField, max_length=200, blank=True, null=True)
- Add `description_bs` (TextField, blank=True, null=True)
- Add `original_language` (CharField, max_length=5, blank=True, null=True)

**Dependencies:** Task 1.1

---

### Task 1.3: Update Ad Model with Localized Getters
**Target:** `src/backend/apps/ads/models.py` (Ad class)

**Changes:**
- Rename existing `title` and `description` to `title_ru` and `description_ru` (via migration)
- Add properties/methods:
  - `get_title(locale: str) -> str`: Return localized title with fallback chain (locale → ru → first available)
  - `get_description(locale: str) -> str`: Return localized description with fallback chain

**Dependencies:** Task 1.2

---

### Task 1.4: Update Search Vector Trigger for Multi-Language
**Target:** `src/backend/apps/ads/migrations/0005_multi_lang_search_vector.py`

**Changes:**
- Modify `ads_search_vector_fn()` to include all language variants using `RunSQL` operation that REPLACES the existing function
- Handle case where function already exists
- New search_vector configuration includes all six language columns:
  ```sql
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title_ru,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description_ru,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(NEW.title_bs,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(NEW.description_bs,'')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.title_en,'')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.description_en,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(v_cat,'')), 'C');
  ```

**Dependencies:** Task 1.2, Task 1.3

---

### Task 1.5: Language Pre-Processing Middleware
**Target:** `src/backend/apps/core/middleware/language.py` (new file)

**Changes:**
- Create `LanguagePreMiddleware` that runs BEFORE Django's `LocaleMiddleware`
- Priority order: `?lang=X` > cookie > `Accept-Language` header > default to `ru`
- On `?lang=X`: set `request.session[LANGUAGE_SESSION_KEY]` and `lang_pref` cookie
- Django's `LocaleMiddleware` then reads session/cookie to set `request.LANGUAGE_CODE`
- Cookie: `lang_pref`, max age 1 year
- Session language for authenticated users (no GET override)

**Dependencies:** Task 1.1

---

### Task 1.6: Add LanguagePreMiddleware to Django Settings
**Target:** `src/backend/config/settings/base.py`

**Changes:**
- Add `apps.core.middleware.language.LanguagePreMiddleware` to `MIDDLEWARE` list (before `django.middleware.locale.LocaleMiddleware`)
- Ensure `django.middleware.locale.LocaleMiddleware` is present in the list (after `SessionMiddleware`)

**Dependencies:** Task 1.5

---

### Task 1.7: Language Context Processor
**Target:** `src/backend/apps/core/context_processors.py`

**Changes:**
- Add `language` function to expose `request.LANGUAGE_CODE` to templates
- Return `{"LANGUAGE_CODE": request.LANGUAGE_CODE}`

**Dependencies:** Task 1.5

---

### Task 1.8: Enhance Bot Translation Service
**Target:** `src/telegram_bot/handlers/ad_create.py` (translation functions)

**Changes:**
- Refactor `translate_to_russian()` but keep it available for backward compatibility
- Add `translate_all_languages(text: str, target_locales: list[str]) -> dict[str, str]` function
- Detect source language using `source="auto"`
- Translate to all active site languages (`ru`, `bs`, `en`) in parallel (using asyncio.gather)
- Store original language in `original_language` field
- Update `update_ad_and_moderate()` to handle multi-language content (Russian as base)

**Dependencies:** Task 1.1, Task 1.2, Task 1.3

---

## Phase 2: UI Localization (MEDIUM Priority)

### Task 2.1: Create Locale Directory Structure
**Target:** `src/backend/locale/`

**Changes:**
- Create `locale/ru/LC_MESSAGES/`, `locale/bs/LC_MESSAGES/`, `locale/en/LC_MESSAGES/`
- Create `django.po` and compile `django.mo` for each language

**Dependencies:** None

---

### Task 2.2: Configure Django i18n Settings
**Target:** `src/backend/config/settings/base.py`

**Changes:**
- Set `LANGUAGE_CODE = "ru"` (default)
- Set `USE_I18N = True`
- Define `LANGUAGES` list with supported languages (`("ru", "Russian"), ("bs", "Bosnian"), ("en", "English")`)
- Add `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]`

**Dependencies:** Task 1.1

---

### Task 2.3: Language Switcher UI Component
**Target:** `src/backend/templates/components/language_switcher.html` (new file)

**Changes:**
- Create dropdown with flags/icons for ru, bs, en
- Links with `?lang=X` parameter
- JavaScript to set `lang_pref` cookie on selection

**HTML template:**
```html
<div class="relative inline-block" id="lang-switcher">
    <button type="button" class="flex items-center gap-1 px-3 py-1 text-sm rounded hover:bg-gray-100">
        <span>{{ current_lang|upper }}</span>
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
    </button>
    <div class="absolute right-0 mt-1 w-32 bg-white border rounded-md shadow-lg hidden">
        <a href="?lang=ru" class="block px-4 py-2 text-sm hover:bg-gray-100" data-lang="ru">Русский</a>
        <a href="?lang=bs" class="block px-4 py-2 text-sm hover:bg-gray-100" data-lang="bs">Боснийский</a>
        <a href="?lang=en" class="block px-4 py-2 text-sm hover:bg-gray-100" data-lang="en">English</a>
    </div>
</div>
```

**Dependencies:** Task 1.6, Task 1.7

---

### Task 2.4: Integrate Language Switcher in Header
**Target:** `src/backend/templates/ads/list.html`, `src/backend/templates/ads/detail.html`

**Changes:**
- Include language switcher component in header
- Add JavaScript for cookie setting on language change

**Dependencies:** Task 2.3

---

### Task 2.5: Update Templates for Localized Content
**Target:** `src/backend/templates/ads/partials/ad_list.html`, `src/backend/templates/ads/detail.html`

**Changes:**
- Use `{{ ad.get_title(request.LANGUAGE_CODE) }}` instead of `{{ ad.title }}`
- Use `{{ ad.get_description(request.LANGUAGE_CODE) }}` instead of `{{ ad.description }}`
- Use `{{ ad.category.get_name(request.LANGUAGE_CODE) }}` (already implemented)
- Use `{{ ad.city.get_name(request.LANGUAGE_CODE) }}` (already implemented)

**Dependencies:** Task 1.3, Task 1.7

---

### Task 2.6: Extract UI Strings to gettext
**Target:** All template files in `src/backend/templates/`

**Changes:**
- Wrap UI strings with `{% trans %}` tags:
  - "Search ads..." → `{% trans "Search ads..." %}`
  - "Search" button → `{% trans "Search" %}`
  - "Contact Seller" → `{% trans "Contact Seller" %}`
  - All other user-facing strings

**Dependencies:** Task 2.1

---

### Task 2.7: Update Category/City get_name for all locales
**Target:** `src/backend/apps/categories/models.py`, `src/backend/apps/locations/models.py`

**Changes:**
- Update `name_i18n` help_text to include English:
  - `help_text="i18n names: {'ru': <str>, 'bs': <str>, 'en': <str>}; NULL falls back to name"`
- Ensure `get_name()` handles all three locales (ru, bs, en)
- Update existing `name_i18n` entries for Categories and Cities where needed

**Dependencies:** Task 1.1

---

## Phase 3: Multi-Language Search (MEDIUM Priority)

### Task 3.1: Update Query Translator Service
**Target:** `src/backend/apps/search/services/query_translator.py`

**Changes:**
- Keep existing `translate_query_bs_to_ru()` function signature unchanged (for backward compatibility)
- Add new `translate_query()` function with signature: `translate_query(text: str, source_locale: str, target_locale: str) -> str`
- Add language detection for queries (extend beyond Bosnian)
- Update existing search functionality to use new `translate_query()` for target language (Russian)

**Dependencies:** Task 1.1

---

### Task 3.2: Update Search View for Language-Aware Search
**Target:** `src/backend/apps/search/views/search.py`

**Changes:**
- Detect query language or use `request.LANGUAGE_CODE`
- Translate query to target search language using new `translate_query()` 
- Use appropriate search_vector with matching FTS config for query language
- For cross-language search (optional): search all language vectors

**Dependencies:** Task 1.7, Task 3.1

---

## Phase 4: Backfill Existing Ads (LOW Priority)

### Task 4.1: Data Migration Backfill Script
**Target:** `src/backend/apps/ads/migrations/0006_backfill_translations.py`

**Changes:**
- Create data migration that translates existing ads to `en` and `bs`
- Use Google Translate API for bulk translation
- Skip ads where translations already exist

**Dependencies:** Task 1.2, Task 1.4

---

## Task Dependencies Graph (DAG)

```
Phase 1:
  Task 1.1 (LanguageLocale enum)
       ↓
  Task 1.2 (DB migration - i18n columns)
       ↓
  Task 1.3 (Ad model getters) ←→ Task 1.4 (search vector trigger)
       ↓
  Task 1.5 (Language middleware) → Task 1.6 (settings) → Task 1.7 (context processor)
       ↓
  Task 1.8 (bot translation enhancement)

Phase 2:
  Task 2.1 (locale structure) ←→ Task 2.2 (i18n settings)
       ↓
  Task 2.3 (language switcher UI) → Task 2.4 (header integration)
       ↓
  Task 2.5 (template updates) ← uses → Task 1.7 (context processor)
  Task 2.6 (gettext extraction)
  Task 2.7 (category/city i18n)

Phase 3:
  Task 3.1 (query translator update)
       ↓
  Task 3.2 (search view update) ← uses → Task 1.7 (context processor)

Phase 4:
  Task 4.1 (backfill - independent)
```

---

## Risk Assessment & Mitigations

| Risk | Mitigation |
|------|------------|
| Translation API failures | Reuse existing `TranslationCircuitBreaker` pattern; fallback to original text |
| PostgreSQL text search config for Bosnian | Use `simple` config (no morphology) instead of missing `bosnian` |
| Performance impact of multi-language search | Single combined GIN index; weights balance relevance |
| Data migration for existing ads | Backfill via Google Translate API with batch processing |
| Cookie size limits | Single `lang_pref` cookie (5 chars), negligible impact |
| LanguageMiddleware + custom middleware priority | Test with multiple scenarios to ensure ?lang=X takes precedence |

---

## Verification Checklist

- [ ] `LanguageLocale` enum properly defined with fts_config property
- [ ] DB migration adds i18n columns without data loss
- [ ] Ad model getters return correct fallbacks
- [ ] Search vector trigger replaced and includes all languages
- [ ] LanguagePreMiddleware sets cookie/session before LocaleMiddleware runs
- [ ] LangaugeMiddleware added to Django settings (before LocaleMiddleware)
- [ ] Context processor exposes language to templates
- [ ] Bot translates to all languages on ad creation
- [ ] Language switcher UI sets cookie and navigates correctly
- [ ] Templates display localized content
- [ ] gettext files created for all three languages
- [ ] Search translates and uses correct FTS config
- [ ] Category/City name_i18n updated to include English
- [ ] Existing ads backfilled with English/Bosnian translations