# Block 2: Autocomplete Suggestions — Implementation Plan

## Block Summary

Real-time autocomplete dropdown served by `GET /api/search/autocomplete?q=<text>`
(`search:autocomplete`), combining `user_history`, `category`+`city` entities,
and `popular_search` into a deduplicated JSON response capped at 10, plus the
HTMX-wired dropdown with click-outcomes and keyboard navigation in
`components/header_catalog.html`. Three verified gaps exist: (1) the `type`
field is only present on category/city suggestions (not user_history or
popular_search), (2) entity prefix-filtering uses the Russian `name` column
exclusively and is not locale-aware, and (3) keyboard Arrow/Escape/Enter handlers
are bound to the search input only and do not select a highlighted suggestion,
nor do they cycle after focus leaves the input.

## Findings Table

| # | Variation | Impl Location | Coverage | Existing Test | Test-Engineer Task | Risk |
|---|-----------|---------------|----------|---------------|---------------------|------|
| 1 | Response shape: endpoint returns `{"query","suggestions[]"}`, each suggestion has `text` + `source` | `autocomplete.py:89-91` | EXISTS | `test_autocomplete.py:101-140` (asserts `text`/`source`) | No action needed — response envelope + text/source keys covered. | Low |
| 2 | **Gap**: plan claims every suggestion has `text`, `source`, `type`, but `type` is absent on `user_history` (`autocomplete.py:66-69`) and `popular_search` (`popular_search.py:73-79`). Only category/city entity suggestions carry `type` (`entity_suggestions.py:71-90`). Frontend render works around this via `s.type === section \|\| s.source === section` (`header_catalog.html:217-218`). | `autocomplete.py:66-69`; `popular_search.py:73-79` | GAP | None | Write a test asserting the **actual** contract: every suggestion has `text` + `source`; `type` + `slug` + `category_path` are present **only** on category/city (source=category/city). Verify the plan's documented shape does not match reality and flag for spec correction. | Medium |
| 3 | Empty or too-short query (`< 2` chars) returns empty suggestions with HTTP 200 | `sanitize.py:41` (`len < 2` → `""`) → `autocomplete.py:54-55` | EXISTS | `test_autocomplete.py:142-156` | No action needed — both no-`q` and 1-char cases covered. | Low |
| 4 | **Gap**: Long query (`> 100` chars) returns empty — `len > 100` → `""` (`sanitize.py:41`) | `sanitize.py:41` | GAP | None | Add endpoint test: `q` with 101 characters returns `{"suggestions":[],"query":""}`; 100 chars is accepted (returns 200). | Medium |
| 5 | **Gap**: Sanitization strips `[;'\"\\]` and strips whitespace — `sanitize.py:43` | `sanitize.py:39-43` | GAP | None (indirect only: `test_autocomplete.py:243-250` asserts empty results for `'; DROP TABLE--` but does **not** verify the stripped query text) | Add a **unit test** on `sanitize_autocomplete_query` asserting exact output for: quotes/backslashes/semicolon stripped, whitespace trimmed, 1-char → empty, 101-char → empty, normal text preserved. | Medium |
| 6 | Rate limit: 30 req/min/IP → 429 with `{"error":"rate_limit"}` | `rate_limit.py:17,53`; `autocomplete.py:57-58` | EXISTS | `test_autocomplete.py:158-175`; `test_autocomplete.py:559-575` | No action needed — both endpoint-level (429 + body) and service-level (returns False after 30th) covered. | Low |
| 7 | `user_history` source: auth → DB (`SearchHistory`), anon → Django session | `autocomplete.py:63-69` (auth path via `get_user_search_history`); `search_history.py:112-116` (anon session path) | EXISTS | `test_autocomplete.py:101-120` (auth); `test_autocomplete.py:226-241` (anon session); `test_autocomplete.py:387-406` (service) | No action needed — both auth DB and anon session paths return history as free-text strings. | Low |
| 8 | `category`+`city` entity suggestions: prefix `istartswith` on `name` field, `is_active=True` filter on categories, `limit=5` per type | `entity_suggestions.py:61-69` | EXISTS | `test_autocomplete.py:423-434` (category prefix match, excludes inactive); `test_autocomplete.py:442-446` (city match); `test_autocomplete.py:453-463` (structure: text/source/type/slug/category_path) | No action needed — prefix matching, active-filter, and slug exposure covered. | Low |
| 9 | **Gap**: Entity **filtering** is NOT locale-aware — `name__istartswith` (`entity_suggestions.py:62,68`) filters the Russian `name` column only; display is localized via `get_name(locale)` (`entity_suggestions.py:73,84`). Non-Cyrillic prefixes at non-RU locales (`?lang=bs`/`en`, typing "Prev" or "Transport") match nothing because the filter never touches `name_i18n`. The three existing locale tests (`test_autocomplete.py:496-548`) all query with **Cyrillic** prefixes that match the Russian `name` — they verify display localization only, not filtering. | `entity_suggestions.py:53-54,62,68,73,84` | GAP | `test_autocomplete.py:496-548` (display only) | Add tests asserting the **current** (buggy) behavior: querying with a Latin/Bosnian prefix at `lang=bs` returns **no** entity matches because `name__istartswith` is Cyrillic-only. Flag for product decision — either (a) document as known gap, or (b) fix `get_entity_suggestions` to filter against the locale-appropriate name. The `search.py:273-317` fuzzy-category-match already does locale-aware matching via `get_name(locale.value)` — this is the reference pattern. | High |
| 10 | `popular_search` source: prefix match on `query_normalized`, `hit_count >= 10` gate, ordered by `-hit_count`, `limit=5` | `popular_search.py:64-79` (`startswith` + `hit_count__gte=10`) | EXISTS | `test_autocomplete.py:287-317` | No action needed — prefix match, min-hit gate, ordering, and empty-prefix cases covered at service level. Add endpoint-level assertion that popular suggestions appear with correct `source` in merged response. | Low |
| 11 | **Gap**: Merge/dedup by `text` preserving insertion order, capped at `_MAX_SUGGESTIONS=10` (`autocomplete.py:80-90`) | `autocomplete.py:80-91` | PARTIAL | `test_autocomplete.py:177-198` (dedup only — seeds 3 sources with same text, no overflow) | Add endpoint test: seed 15+ unique suggestions across all sources, assert response contains exactly 10, and that user_history entries appear first (highest priority). Verify dedup preserves first occurrence (user_history wins over category/popular when text collides). | Medium |
| 12 | Search-view recording: `increment_popular_search` + `record_search_history` called on `/search/?q=` | `search.py:190-197` | EXISTS | `test_autocomplete.py:586-641` | No action needed — popular-search increment, auth history, and anon session history recording all covered via `TestSearchViewRecordsAutocompleteData`. | Low |
| 13 | Template wiring: `hx-get`, `hx-trigger="input delay:300ms"`, `hx-target="#autocomplete-dropdown"`, `hx-swap="none"`, `#autocomplete-dropdown` `<ul>` | `header_catalog.html:117-129` | EXISTS | `test_autocomplete_template.py:55-64` (string assertions) | No action needed — HTMX attributes and dropdown element verified via template string tests. | Low |
| 14 | **Gap**: Click outcome — city suggestion → fire-and-forget `POST /api/preferred-city/` + full-page nav to `/city/<slug>/` | `header_catalog.html:269-274` (fetch with no `.then()`/`.catch()`, immediate `window.location.href`) | GAP | None | **Playwright** test: click a city suggestion, assert `fetch` POST was attempted (intercept), assert full-page navigation to `/city/<slug>/`. Verify POST is fire-and-forget (nav proceeds regardless of POST response). | Medium |
| 15 | Click outcome — category suggestion → full-page nav to `/category/<slug>/` | `header_catalog.html:275-277` | GAP | None | **Playwright** test: click category suggestion, assert navigation to `/category/<slug>/`. | Medium |
| 16 | Click outcome — text suggestion → populate input + form submit to `/search/?q=<t>` | `header_catalog.html:278-282` | GAP | None | **Playwright** test: click a popular/user_history suggestion, assert input is populated with `text` and form submits to `/search/?q=<t>`. | Medium |
| 17 | Click outcome — "Show all results" link → `/search/?q=<query>` | `header_catalog.html:214-216` | GAP | None | **Playwright** test: click "Show all results", assert navigation to `/search/?q=<encoded-query>`. | Medium |
| 18 | **Gap**: Keyboard nav — `ArrowDown`/`ArrowUp` cycles suggestions, `Enter` selects highlighted suggestion, `Escape` dismisses | `header_catalog.html:285-305` (listener on `searchInput` only) | GAP | None | **Playwright** tests: (a) type query → ArrowDown cycles through items → Enter selects the focused item (for city → nav, for category → nav, for text → submit). (b) Escape dismisses dropdown. (c) **Documented bug**: after one ArrowDown, focus moves to an `<a>` element; because the listener is on `searchInput` not `document`, further ArrowDown/Up/Enter keystrokes are not captured. Enter while input has focus submits the form with raw input text (never selects a suggestion). | High |

## Priority

**High** — Block 2 is foundational to the search user journey (G2 covers the
primary entry path: focus search bar → type → refine via suggestions). Findings
#9 (locale-aware filtering) and #18 (keyboard Enter/cycling breaks) are
user-facing regressions that directly block non-Russian users and break the
expected autocomplete UX. The plan explicitly calls out keyboard nav and
locale-aware matching as key variations, and their absence is a functional gap,
not a test-coverage gap.

## Dependencies

- **Block 1** (landing state baseline): autocomplete renders on every surface
  via the shared `header_catalog.html` include (`header_catalog.html:114-132`).
  Block 1 verifies the search bar is present and the header form contains only
  `q` + CSRF (`top_plan.md:60`) — the autocomplete `hx-get` attaches to that
  same `search-input`. The city/city-dropdown and category-dropdown context
  (`preferred_city_display`, `cities`, `root_categories`) is shared header
  state that Block 1 establishes.
- No other Block dependencies. Block 2 is a leaf-level interaction primitive;
  Block 10 (Search History) depends on Block 2 for `user_history` suggestion
  display, but Block 2's tests do not depend on Block 10's implementation.

## Validator Recommendations

### Django client tests (server-side response assertions)
- Use `django.test.Client` against `GET /api/search/autocomplete?q=...` as
  already established in `test_autocomplete.py`. Tests tagged
  `django_db, slow, integration` (matching the module's `pytestmark` at
  `test_autocomplete.py:34`).
- Clear the rate-limit cache between tests (`cache.clear()`) — the existing
  `_reset_rate_limit` fixture at `test_autocomplete.py:91-99` already handles
  this; replicate the pattern for any new endpoint test.
- For sanitization, add **direct unit tests** on `sanitize_autocomplete_query`
  (`sanitize.py:39`) rather than only endpoint-level indirect tests. This is a
  pure function with no DB dependency — use `pytest.mark.unit`.
- For the 10-cap, seed 15+ rows across `PopularSearch`, `SearchHistory`,
  `Category`, and `City` in a single test and assert `len(suggestions) == 10`.

### Entity locale-aware filtering gap (#9)
Two sub-questions to resolve **before** writing assertions:
1. **Current behavior** (bug): `name__istartswith` filters on the Russian
   `name` column (`entity_suggestions.py:62,68`), so a non-Cyrillic prefix at
   `lang=bs`/`en` returns zero entities. Test this as "documented bug" first.
2. **Desired behavior** (spec): the Validation doc claims filtering matches
   `get_name(locale)`. If product confirms, the fix is to filter on a
   locale-resolved field — but `name` is a plain `CharField`, not a
   translatable field queryable by `istartswith` on `name_i18n`. The
   `_fuzzy_category_match` in `search.py:308-317` shows the only viable
   pattern today (iterate all active categories, call `get_name(locale)`).
   A Playwright-based test for the non-RU path should be deferred until the
   implementation approach is decided.

### Playwright sub-tests (client-side interaction)
- **No committed Playwright/e2e suite exists** (no `playwright.config.*`, no
  `pytest-playwright` dependency — confirmed via grep). Establishing Playwright
  is a prerequisite for variations #14–#18 and is a cross-cutting infrastructure
  concern outside Block 2's scope. Recommend the planner coordinate with the
  Playwright setup task before assigning keyboard/click tests.
- For keyboard-nav testing (#18): the core regression is that the `keydown`
  listener is on `searchInput` (`header_catalog.html:285`), not `document`.
  After `ArrowDown` focuses an `<a>` (line 294), subsequent keys are orphaned.
  A Playwright test should verify: (a) one ArrowDown then Enter selects the
  first suggestion, (b) two ArrowDowns then Enter selects the second (this will
  **fail** against current code — the expected failure documents the bug).
  Escape dismissal (`header_catalog.html:287`) should also be verified.
- For click-outcome tests (#14–#17): intercept the `fetch` call in #14 (city
  POST) using Playwright route interception to confirm the POST fires even
  though the page navigates away immediately (`header_catalog.html:273-274`).

### i18n
No new translatable strings are introduced in autocomplete suggestions (suggestion `text` values come from the database, not template literals). The JS labels (`show_all_results`, `cities`, `categories`, `popular_queries`, `history`) are already injected via `catalog_js_labels` (`context_processors.py:78-86`) and are not asserted in tests. No `makemessages`/`compilemessages` impact from Block 2 tests.
