# Problem Spec 09: Category and City Names Not Rendered in Selected Language

**Spec ID:** 09  
**Created:** 2026-08-24  
**Status:** Approved (PO decisions collected)  
**Source:** Spec_08 section 3.5 incorrectly claims Category/City i18n is already covered. Runtime investigation proves otherwise.  
**Spec index:** [docs/01-spec/spec-index.md](docs/01-spec/spec-index.md)

---

## 1. Problem Statement

Category names and city names appear in **Russian** in the UI regardless of the selected interface language, even though the source data (`categories.yaml`, `cities.json`) contains complete `name_i18n` translations for `ru`, `bs`, and `en`, and the data is correctly loaded into the database `name_i18n` JSONField.

**User-visible symptom:** A user selecting Bosnian (`bs`) or English (`en`) from the language switcher still sees categories and cities in Cyrillic Russian throughout the catalog, breadcrumbs, search results, and save-search forms.

---

## 2. Confirmed Facts

| # | Fact | Evidence (file:line) |
|---|------|---------------------|
| F1 | `Category` and `City` models each have `name_i18n` JSONField and a `get_name(locale="ru")` method with fallback chain: requested locale → `ru` → `name` (raw). | `categories/models.py:53-67`, `locations/models.py:45-59` |
| F2 | Seed data contains full translations: `categories.yaml` has `name_i18n: {ru, bs, en}` for all categories; `cities.json` has `name_i18n` for all 15 cities. | `categories/catalog/categories.yaml`, `seed/fixtures/cities.json` |
| F3 | The catalog builder persists `name_i18n` to the database. | `categories/catalog/builder.py:213` |
| F4 | `LANGUAGE_CODE` is available in every template via context processor; request has `LANGUAGE_CODE` set by middleware. | `core/middleware/language.py`, `core/context_processors.py:22-24` |
| F5 | There is an established template-filter pattern for DB-based i18n: `get_lookup_name:LANGUAGE_CODE`. | `core/templatetags/localized_content.py` |
| F6 | 24 call sites across 9 template files invoke `{{ obj.get_name }}` (no argument) on Category/City objects. | See Section 6 (Affected Assets) |
| F7 | `SearchView` correctly passes locale: `category.get_name(locale.value)` for fuzzy matching. | `search/views/search.py:259,275,294,298` |
| F8 | The autocomplete (entity suggestions) path uses raw `cat.name`/`city.name` and `get_name()` without locale. | `search/services/entity_suggestions.py:31,68,79` |
| F9 | The `category_submenu` view caches rendered HTML keyed by `category:submenu:<tree_version>:<slug>` with no language component. | `categories/views.py:45`, `categories/cache.py:19,45` |
| F10 | `.po` files: `ru` and `bs` are fully translated; `en` `msgstr` is empty by convention (msgid is English). | `.po` files in `locales/` |
| F11 | Existing i18n completeness test (`test_i18n_completeness.py`) scans for hardcoded strings via regex; it treats `{{ city.get_name }}` as dynamic and cannot catch the missing-locale bug. | `ads/tests/test_i18n_completeness.py` |

---

## 3. Root Cause

**Root cause:** The `get_name()` method on `Category` and `City` models defaults to `locale="ru"`. Every template call site invokes `{{ obj.get_name }}` — i.e., `get_name()` with no argument — so Django resolves the call without any locale, and the default `ru` is always used.

There is no template filter or tag that passes `LANGUAGE_CODE` to `get_name()`. The correct pattern (`get_lookup_name:LANGUAGE_CODE`) exists for `LookupItem` but was never replicated for `Category` and `City`.

Additionally:
- **Autocomplete** (`entity_suggestions.py`) constructs suggestion dicts using raw `.name` fields (Russian) and `get_name()` without locale — separate data path, same root issue.
- **Submenu caching** (`categories/views.py`) stores rendered HTML with no language in the cache key, causing cross-language bleed (a Russian-rendered submenu cached under a key is served to a Bosnian user).

---

## 4. Confirmed Requirements

| Req ID | Requirement | Source |
|--------|-------------|--------|
| REQ-09.1 | Category names must be rendered in the user's selected interface language (RU/BS/EN). | Implied by Spec_08 §3.1, §3.2 (UI localization requirement) |
| REQ-09.2 | City names must be rendered in the user's selected interface language (RU/BS/EN). | Implied by Spec_08 §3.1, §3.2 |
| REQ-09.3 | If a translation for the selected language is missing, fall back to RU, then to the raw `name` field. | Existing `get_name()` fallback chain (F1) — must be preserved |
| REQ-09.4 | Autocomplete/search suggestions must return city and category names in the user's selected language. | Consistent UI behavior |
| REQ-09.5 | Cached rendered HTML (submenu) must be language-specific — no cross-language cache bleed. | Correctness |
| REQ-09.6 | The bot (Telegram) side — `immediate_alerts.py:104` `ad.city.get_name()` — must localize city/category names. A language-selection menu (RU/BS/EN) will be added to the Telegram bot; the user's selected language is stored per-user and used in all bot notifications. | PO Decision §7.1 |
| REQ-09.7 | Admin moderation UI (`review.html`) must show localized names. A language selector in the admin panel lets moderators choose their preferred language (RU/BS/EN), passed as `LANGUAGE_CODE` to template context. | PO Decision §7.2 |
| REQ-09.8 | No regression in search fuzzy-matching performance (SearchView already passes locale correctly). | F7 — must not be broken |

---

## 5. Conceptual Tasks

### Task 1: Add template filters `get_category_name` and `get_city_name`
- Create `get_category_name:LANGUAGE_CODE` and `get_city_name:LANGUAGE_CODE` filters in `core/templatetags/localized_content.py`, mirroring the existing `get_lookup_name` filter.
- Each filter calls `obj.get_name(locale)` where `locale` is the template tag's argument (the current `LANGUAGE_CODE`).
- **Files:** `core/templatetags/localized_content.py`

### Task 2: Update all 24 template call sites
- Replace `{{ obj.get_name }}` with `{{ obj|get_category_name:LANGUAGE_CODE }}` (for Category objects) or `{{ obj|get_city_name:LANGUAGE_CODE }}` (for City objects) across all 9 templates listed in Section 6.
- Handle the `|default:` fallback pattern where present (e.g., `{{ ad.city.get_name|default:ad.city.name }}` → `{{ ad.city|get_city_name:LANGUAGE_CODE }}`; the filter handles its own fallback, so `|default` is no longer needed).
- **Files:** see Section 6.

### Task 3: Add language dimension to entity suggestions
- Add `locale` parameter to `get_entity_suggestions(prefix, limit, locale)`.
- Use `cat.get_name(locale)` and `city.get_name(locale)` instead of raw `cat.name`/`city.name`.
- Update caller `autocomplete.py:72` to pass `request.LANGUAGE_CODE`.
- **Files:** `search/services/entity_suggestions.py`, `search/views/autocomplete.py`

### Task 4: Add language to submenu cache key
- Modify `categories/views.py:45` cache key to include `LANGUAGE_CODE`: `category:submenu:<tree_version>:<slug>:<locale>`.
- **Files:** `categories/views.py`, `categories/cache.py`

### Task 5: Add regression test
- Write a test that loads the page with `HTTP_ACCEPT_LANGUAGE="bs"` and asserts category/city names are in Bosnian (not Russian).
- Write a test that verifies the submenu cache key varies by language (or simply that different languages return different rendered HTML).
- Extend regression test to cover admin UI (BS/EN rendering) and Telegram alert payloads.
- **Files:** new test file under `categories/tests/` or `ads/tests/`

### Task 6: Update i18n completeness test
- Extend `test_i18n_completeness.py` to also detect `{{ obj.get_name }}` patterns on Category/City objects and flag them as violations, with an exclusion for `get_lookup_name` (LookupItem i18n is already correct).
- **Files:** `ads/tests/test_i18n_completeness.py`

### Task 7: Update spec index
- Spec_09 linked from `docs/01-spec/spec-index.md` under "Known Problems / Bug Specs". ✅ (already done)
- **Files:** `docs/01-spec/spec-index.md`

---

## 6. Affected Assets

### Templates calling `.get_name` without locale (24 sites)

| Template | Line(s) | Object | Current |
|----------|---------|--------|---------|
| `components/header_catalog.html` | 65 | `city` | `{{ city.get_name }}` |
| `components/header_catalog.html` | 78 | `current_cat` | `{{ current_cat.get_name }}` |
| `components/header_catalog.html` | 92 | `cat` | `{{ cat.get_name }}` |
| `components/header_catalog.html` | 98 | `cat` | `{{ cat.get_name }}` |
| `components/header_catalog.html` | 159 | `cat` | `{{ cat.get_name }}` |
| `components/header_catalog.html` | 165 | `cat` | `{{ cat.get_name }}` |
| `components/breadcrumb.html` | 16 | `ancestor` | `{{ ancestor.get_name }}` |
| `components/breadcrumb.html` | 21 | `cat` | `{{ cat.get_name }}` |
| `components/breadcrumb.html` | 24 | `cat` | `{{ cat.get_name }}` |
| `components/breadcrumb.html` | 27 | `ancestor` | `{{ ancestor.get_name }}` |
| `components/breadcrumb.html` | 30 | `cat` | `{{ cat.get_name }}` |
| `ads/partials/ad_list.html` | 114 | `ad.city` | `{{ ad.city.get_name\|default:ad.city.name }}` |
| `ads/partials/ad_list.html` | 115 | `ad.category` | `{{ ad.category.get_name\|default:ad.category.name }}` |
| `ads/detail.html` | 74 | `ad.city` | `{{ ad.city.get_name\|default:ad.city.name }}` |
| `ads/detail.html` | 78 | `ad.category` | `{{ ad.category.get_name\|default:ad.category.name }}` |
| `categories/partials/mega_submenu.html` | 14 | `child` | `{{ child.get_name }}` |
| `categories/partials/mega_submenu.html` | 22 | `cat` | `{{ cat.get_name }}` |
| `cabinet/saved_search_edit.html` | 38 | `city` | `{{ city.get_name }}` |
| `cabinet/saved_search_edit.html` | 49 | `category` | `{{ category.get_name }}` |
| `search/partials/save_search_modal.html` | 33 | `city` | `{{ city.get_name }}` |
| `search/partials/save_search_modal.html` | 47 | `category` | `{{ category.get_name }}` |
| `cabinet/partials/saved_search_row.html` | 17 | `ss.city` | `{{ ss.city.get_name\|default:"—" }}` |
| `cabinet/partials/saved_search_row.html` | 18 | `ss.category` | `{{ ss.category.get_name\|default:"—" }}` |
| `admin/moderation/review.html` | 50 | `ad.category` | `{{ ad.category.get_name\|default:ad.category.name }}` |
| `admin/moderation/review.html` | 54 | `ad.city.name` | `{{ ad.city.name }}` (raw Russian) |

### Python files needing changes

| File | Line(s) | Issue |
|------|---------|-------|
| `search/services/entity_suggestions.py` | 31, 68, 79 | `get_name()` without locale; uses `cat.name`/`city.name` |
| `search/views/autocomplete.py` | 72 | Calls `get_entity_suggestions(query)` without locale |
| `categories/views.py` | 45 | Cache key omits language |
| `ads/telegram/immediate_alerts.py` | 104 | `ad.city.get_name()` without locale — **PO DECIDED: localize** |
| `categories/catalog/builder.py` | — | No change needed; already saves `name_i18n` ✅ |

### Model files (read-only reference)

| File | Line | Method |
|------|------|--------|
| `categories/models.py` | 53-67 | `Category.get_name(self, locale="ru")` |
| `locations/models.py` | 45-59 | `City.get_name(self, locale="ru")` |

### Template tag file

| File | Purpose |
|------|---------|
| `core/templatetags/localized_content.py` | Contains existing `get_lookup_name` filter — pattern to mirror |

---

## 7. PO Decisions (Collected)

**Decision Date:** 2026-08-24

1. **Telegram alerts (REQ-09.6):** DECIDED — **Option B: Localize Telegram alerts.** Add a language-selection menu (3 languages: RU/BS/EN) in the Telegram bot so users can pick their preferred interface language. The selected language is stored per-user and used in all bot notifications including `immediate_alerts.py:104`. This means Task 1/2 fix applies to the Telegram alert template/payload too, not just web templates.

2. **Admin moderation UI (REQ-09.7):** DECIDED — **Option A with language selector: Localize admin UI** using the new `get_category_name`/`get_city_name` filters. Additionally, provide a language selector in the admin panel so moderators can choose their preferred language (RU/BS/EN), and that language is passed as `LANGUAGE_CODE` to the template context.

3. **Template filter naming:** DECIDED — **Option A: Two named filters** — `get_category_name:LANGUAGE_CODE` and `get_city_name:LANGUAGE_CODE`. Mirrors the existing `get_lookup_name` pattern and follows Single Responsibility principle.

4. **i18n test enhancement (Task 6):** DECIDED — **Option A: Extend** `test_i18n_completeness.py` to flag `{{ obj.get_name }}` calls on Category/City objects as violations, with an exclusion for the existing `get_lookup_name` filter (LookupItem i18n is already correct).

> **Implementation impact:** Task 1 (add filters) and Task 2 (update templates) are now unblocked. Task 5 (regression test) should cover BS/EN rendering in admin UI and Telegram alert payloads.

---

## 8. Assumptions

| # | Assumption | Basis |
|---|------------|-------|
| A1 | `LANGUAGE_CODE` in templates reflects the user's currently selected language. | `core/middleware/language.py`, `core/context_processors.py:22-24` |
| A2 | The `get_name(locale)` fallback chain (locale → ru → name) is correct and should be reused, not replaced. | F1 |
| A3 | Adding a template filter that calls `get_name` is acceptable performance-wise (the method does only a dict lookup on a cached `name_i18n` field). | No DB hit inside `get_name`; F2 |
| A4 | The search page fuzzy-matching already works correctly and should not be broken. | F7 (`search.py:259,275,294,298`) |
| A5 | The `category_submenu` cache is per-render, so adding locale to the cache key is safe and will not break cache-hit rates meaningfully (3 languages × existing keys). | `categories/cache.py:SUBMENU_CACHE_TTL=300` |
| A6 | The Telegram bot user-language preference feature (language menu) is a separate effort that can be tracked as its own task; the i18n fix for `immediate_alerts` depends on it. | PO Decision §7.1 |

---

## 9. Constraints

| # | Constraint | Source |
|---|-----------|--------|
| C1 | Use `StrEnum` for fixed values — `LanguageLocale` enum already exists in `core/enums.py:187-219` (RU="ru", BS="bs", EN="en"). | AGENTS.md principle #10 |
| C2 | Templates must be i18n-compliant: wrap user-visible strings in `{% trans %}` / `{% blocktrans %}`. Template filters returning translated values are exempt from `{% trans %}` wrapping. | AGENTS.md principle #16 |
| C3 | All changes require DB migrations only if schema changes — this fix is template/ORM logic only, no schema changes expected. | N/A |
| C4 | Tests require Docker PostgreSQL on port 5433; never run `uv run pytest` locally. | `.kilo/rules/commands.md` |
| C5 | Fast gate: `make test` skips `seed` marker tests (~300s saved). | `.kilo/rules/commands.md` |

---

## 10. Risks

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | Breaking the `|default` pattern in templates that rely on it for None-safety. | Template filter handles None internally (check `obj is None`); `|default` becomes redundant and is removed. |
| R2 | Cache key change causing a brief thundering herd on cache miss. | Acceptable — cache TTL is 300s; miss only affects one request per key/locale. |
| R3 | Autocomplete returning translated names could change search matching behavior if the frontend does client-side filtering against the returned text. | Verify frontend JS: does it filter on `label` or `value`? (Research needed.) |
| R4 | Adding `locale` param to `get_entity_suggestions` could break existing callers/tests. | Audit all callers of `get_entity_suggestions` — only `autocomplete.py:72` calls it. |
| R5 | The submenu HTML is rendered server-side and cached; if the cache key change is missed on any code path, stale Russian HTML bleeds into BS/EN. | Add a test that fetches the submenu in two languages and asserts different output. |

---

## 11. Open Questions

1. **Research (delegated to Researcher):** Does the frontend JavaScript in `save_search_modal.html` / `header_catalog.html` perform client-side filtering against the `label` field of autocomplete suggestions? If so, translating suggestion labels could break the matching UX. Confirm before changing `entity_suggestions.py`.
2. **Research:** Are there any other callers of `get_entity_suggestions` besides `autocomplete.py:72`? (Preliminary grep shows only one.)
3. **Implementation:** How is the Telegram user-language preference persisted? New `User.telegram_language` field? Separate `BotUserPreference` model? (Depends on existing user model — research needed.)

---

## 12. Out of Scope

- **Spec_08 §3.4 (template string extraction):** The `{{ obj.get_name }}` pattern is not a translatable string in `.po` extraction — it's a method call. The fix is logic, not extraction.
- **`.po`/`.mo` file regeneration:** No new user-visible strings are being added (the translations already exist in `name_i18n` in the DB). No `makemessages`/`compilemessages` needed unless templates add new strings.
- **LookupItem localization:** Already works correctly via `get_lookup_name:LANGUAGE_CODE`. No changes needed.
- **Backend API:** This project uses HTMX MPA (WSGI gunicorn), not a separate JSON API. No API-level i18n needed.
- **Bot-side FSM flows:** The Telegram bot ad-creation dialog is Russian-only; no localization needed there.
- **Telegram language menu implementation (REQ-09.6, Task 5):** The language-selection menu itself in the bot is a separate feature task; this spec covers the i18n fix for `immediate_alerts.py`, and depends on the language-preference feature being available.

---

## 13. Definition of Ready

A task is ready to be implemented when:
1. ✅ Root cause is identified and confirmed (Section 3).
2. ✅ All affected files are enumerated (Section 6).
3. ✅ PO decisions collected (Section 7) — **all 4 decided**.
4. ⬜ Research on frontend autocomplete filtering behavior (Open Q1) is complete.
5. ⬜ Research on Telegram user-language preference persistence (Open Q3) is complete.
6. ⬜ Existing test baseline is green (`make test` fast gate passes).

---

## 14. Definition of Done

A task is done when:
1. All 24 template call sites use the new `get_category_name:LANGUAGE_CODE` or `get_city_name:LANGUAGE_CODE` filter.
2. Autocomplete returns locale-aware city/category names.
3. Submenu cache key includes language and no cross-language bleed occurs.
4. Regression test passes: categories and cities render in BS/EN when `HTTP_ACCEPT_LANGUAGE` is set; admin UI and Telegram alert payloads also verified.
5. `make test` (fast gate) passes with no regressions.
6. `test_i18n_completeness.py` passes with the new `{{ obj.get_name }}` violation checks.
7. `uv run ruff check` and `uv run basedpyright` pass on all changed files.
8. This spec is marked `Status: Complete` and linked from the spec index.
