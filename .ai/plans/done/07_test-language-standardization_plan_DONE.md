# Implementation Plan: Test Language Standardization (Spec 07)

**Source spec:** `.ai/problems/07_test-language-standardization_spec.md`
**Status:** Ready for execution
**Total task specs:** 9 (T1–T5, T7, T8, T9, T6)
**Environment:** Windows · `uv` · PostgreSQL 18 in Docker · test DB on port 5433

---

## 1. Overview

Eliminates ambiguous test-language configuration in the Mko Bazuna test suite.
Three interlocking changes:

1. **Option C (middleware + context processor)**: Change the test-language
   fallback from the hardcoded `"ru"` to `settings.LANGUAGE_CODE`, so that
   setting `LANGUAGE_CODE = "en"` in `test.py` actually makes English the
   default rendering for integration tests. (The spec's T1 + A1 were
   contradictory — A1 states the middleware still resolves to "ru" even with
   `LANGUAGE_CODE = "en"`, because `LanguagePreMiddleware` hardcodes
   `LanguageLocale.RUSSIAN.value` at `language.py:74`. The Validator confirmed
   Option C is the architecturally sound resolution.)

2. **Centralized thread-local cleanup**: Autouse `translation.deactivate()`
   fixture in root `conftest.py` eliminates all thread-local leakage.

3. **Explicit language signals in tests**: Replace redundant
   `translation.activate("ru")` calls in integration tests with
   `?lang=ru` or `Accept-Language` headers; migrate unit tests to
   `translation.override()` context manager.

---

## 2. Key Divergence from Spec (Validator Correction)

| Spec § | Spec says | Plan deviation | Rationale |
|---|---|---|---|
| §11 Out of Scope | Do NOT change middleware logic | T1b changes the middleware fallback | Spec's T1 + A1 are contradictory; Option C is the only way to achieve T1's stated goal |
| §2.3 | Context processor fallback is `"ru"` | T1b changes `context_processors.language()` fallback to `settings.LANGUAGE_CODE` | Consistency — same root cause |
| §2.2 | Middleware hardcodes "ru" default at L74 | T1b makes L74 use `settings.LANGUAGE_CODE` | `settings.LANGUAGE_CODE` is the canonical default, per Q1=A |
| §3.1 E22 | `test_saved_search_create.py` is safe (middleware hardcodes "ru") | T9: this test now breaks (middleware defaults to `LANGUAGE_CODE` = "en" in test) | Option C changes the default resolution |

---

## 3. Path Mapping (spec shorthand → actual repo paths)

| Spec shorthand | Actual path |
|---|---|
| `conftest.py` | `src/backend/conftest.py` |
| `config/settings/test.py` | `src/backend/config/settings/test.py` |
| `config/settings/base.py` | `src/backend/config/settings/base.py` |
| `middleware/language.py` | `src/backend/apps/core/middleware/language.py` |
| `context_processors.py` | `src/backend/apps/core/context_processors.py` |
| `enums.py` | `src/backend/apps/core/enums.py` |
| `test_language_middleware.py` | `src/backend/apps/core/tests/test_language_middleware.py` |
| `test_language_end_to_end.py` | `src/backend/apps/core/tests/test_language_end_to_end.py` |
| `test_context_processors.py` | `src/backend/apps/core/tests/test_context_processors.py` |
| `test_i18n_category_city.py` | `src/backend/apps/ads/tests/test_i18n_category_city.py` |
| `test_auth_nav.py` | `src/backend/apps/ads/tests/test_auth_nav.py` |
| `test_breadcrumbs_render.py` | `src/backend/apps/ads/tests/test_breadcrumbs_render.py` |
| `test_favorites.py` | `src/backend/apps/ads/tests/test_favorites.py` |
| `test_saved_search_create.py` | `src/backend/apps/search/tests/test_saved_search_create.py` |
| `test_preferred_city.py` | `src/backend/apps/search/tests/test_preferred_city.py` |
| `test_preferred_city_readback.py` | `src/backend/apps/search/tests/test_preferred_city_readback.py` |
| `test_favorites_badge.py` | `src/backend/apps/cabinet/tests/test_favorites_badge.py` |
| `test_cabinet_sections.py` | `src/backend/apps/cabinet/tests/test_cabinet_sections.py` |
| `test_dashboard_stats.py` | `src/backend/apps/ads/tests/test_dashboard_stats.py` |
| `docs/99-agent/rules.md` | `docs/99-agent/rules.md` |

---

## 4. Execution DAG

```
T2  (autouse deactivate fixture in conftest.py)
  │
  ├──► T1b (middleware + context processor: hardcoded "ru" → settings.LANGUAGE_CODE)
  │     │
  │     ├──► T9  (update middleware + context processor tests for new default)
  │     └──► T1  (LANGUAGE_CODE = "en" in test.py)
  │           │
  │           └──► T7  (update tests with Russian UI assertions: add ?lang=ru)
  │
  T5  (translation.activate → translation.override in unit tests)
    │
    └──► T3  (remove local cleanup fixtures)
            │
            └──► T4  (remove redundant activate("ru") in integration tests)
                    │
                    └──► T6  (document convention in conftest + rules.md)
                            │
                            └──► T8  (update rules.md testing conventions)
                                    │
                                    └──► T10 (final verification)
```

### Dependency edges

| Task | blocked_by | Parallel-safe |
|---|---|---|
| T1b | — (production code change; safe with prod LANGUAGE_CODE="ru") | yes — can run parallel with T2 |
| T2 | — | yes — can run parallel with T1b |
| T1 | T1b (needs middleware to respect LANGUAGE_CODE first) | no |
| T9 | T1b (middleware test updates) | yes — can run parallel with T1 |
| T7 | T1, T1b (default changes) | yes — different test files |
| T5 | — | yes — different files from T7 |
| T3 | T2 (shared fixture must exist first) | no |
| T4 | T2, T3 (fixture + per-file fixture removal) | yes — different test files |
| T6 | T4 | no |
| T8 | T6 | no |
| T10 | all above | no |

### Execution order (topological)

1. **T2** (autouse fixture) — immediate safety, zero breakage
2. **{T1b, T5}** in parallel — middleware change + unit test migration
3. **T1, T9** in parallel — test settings + middleware test updates
4. **{T7, T3}** in parallel — Russian-asserting tests fix + remove local fixtures
5. **T4** — remove redundant activate calls in integration tests
6. **T6, T8** — documentation
7. **T10** — final verification

---

## 5. Task Specifications

### T1 — Set `LANGUAGE_CODE = "en"` in test settings

**Risk:** none (test-only)
**Depends on:** T1b (middleware must respect `LANGUAGE_CODE`)
**Parallel-safe:** yes (with T9)

**Description:** Add `LANGUAGE_CODE = "en"` to `src/backend/config/settings/test.py`,
making English the default for the test environment. This matches the `msgid`
language — tests asserting on English UI text pass without extra setup.

**Files:**
- `src/backend/config/settings/test.py` — add `LANGUAGE_CODE = "en"` after the
  existing imports, before `DEBUG = True` (or after the `from .base import *`
  block, near other test overrides).

**Changes:**
```python
# English is the msgid source language — tests asserting on English UI text
# (e.g. "Clear all filters", "Page navigation") pass without extra language
# setup. Tests needing Russian must set ?lang=ru explicitly (see conftest.py
# autouse _reset_translation_state fixture).
LANGUAGE_CODE = "en"
```

**Acceptance criteria:**
- [ ] `test.py` sets `LANGUAGE_CODE = "en"`
- [ ] `base.py` still has `LANGUAGE_CODE = "ru"` (production unchanged)

**Verification:**
- `uv run ruff check src/backend/config/settings/test.py`
- `uv run python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test'); import django; django.setup(); from django.conf import settings; print(settings.LANGUAGE_CODE)"` → `en`

---

### T1b — Middleware + context processor: hardcoded "ru" → `settings.LANGUAGE_CODE` (Option C)

**Risk:** low-medium (production code change, but `base.py` has `LANGUAGE_CODE = "ru"`)
**Depends on:** none
**Parallel-safe:** yes (with T2, T5)

**Description:** Changes the language resolution fallback from hardcoded
`LanguageLocale.RUSSIAN.value` ("ru") to `settings.LANGUAGE_CODE`. In production
this is a no-op (both are "ru"). In tests, after T1 sets `LANGUAGE_CODE = "en"`,
the default becomes "en".

**Files (3 files, 5 edit points):**

1. `src/backend/apps/core/middleware/language.py`
   - L5: docstring priority line: `> ``ru``` → `> ``settings.LANGUAGE_CODE```
   - L50: class docstring "Default to Russian (``ru``)" → "Default to ``settings.LANGUAGE_CODE``"
   - L57-74: Add `from django.conf import settings` import at top
   - L74: `self._set_language_code(request, LanguageLocale.RUSSIAN.value)` → `self._set_language_code(request, settings.LANGUAGE_CODE)`
   - L104: `self._set_language_code(request, LanguageLocale.RUSSIAN.value)` → `self._set_language_code(request, settings.LANGUAGE_CODE)` (invalid lang param fallback)

2. `src/backend/apps/core/context_processors.py`
   - L24: `getattr(request, "LANGUAGE_CODE", "ru")` → `getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)`
   - L73: `locale = getattr(request, "LANGUAGE_CODE", "ru") or "ru"` → `locale = getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE) or settings.LANGUAGE_CODE`

**Note:** `context_processors.py` already imports `from django.conf import settings` (L9).
**Note:** `language.py` needs `from django.conf import settings` added to imports.

**Acceptance criteria:**
- [ ] Middleware L74 uses `settings.LANGUAGE_CODE` (not hardcoded "ru")
- [ ] Middleware L104 (invalid lang fallback) uses `settings.LANGUAGE_CODE`
- [ ] Context processor L24 uses `settings.LANGUAGE_CODE` as fallback
- [ ] Context processor L73 uses `settings.LANGUAGE_CODE` as fallback
- [ ] Docstrings updated to reflect configurable default

**Verification:**
- `uv run ruff check src/backend/apps/core/middleware/language.py src/backend/apps/core/context_processors.py`
- `uv run basedpyright src/backend/apps/core/middleware/language.py`
- Production behavior: `LANGUAGE_CODE = "ru"` in base.py → middleware still defaults to "ru"

---

### T2 — Autouse thread-local translation cleanup in root conftest

**Risk:** none (additive, teardown only)
**Depends on:** none
**Parallel-safe:** yes

**Description:** Add an autouse, function-scoped fixture to `src/backend/conftest.py`
that calls `translation.deactivate()` in teardown, eliminating all thread-local
translation state leakage between tests on the same xdist worker.

**Files:**
- `src/backend/conftest.py` — add import + fixture

**Changes:**
```python
from django.utils import translation  # add to imports

@pytest.fixture(autouse=True)
def _reset_translation_state():
    """Reset thread-local translation state after each test.

    LanguagePreMiddleware calls translation.activate() per-request, leaving
    thread-local state after the response. Without cleanup, this leaks to
    subsequent tests on the same xdist worker. Following Django's documented
    tearDown recommendation (activate(settings.LANGUAGE_CODE)).
    """
    yield
    translation.deactivate()
```

**Acceptance criteria:**
- [ ] Autouse fixture added to `src/backend/conftest.py`
- [ ] Calls `translation.deactivate()` in teardown (after yield)
- [ ] Import of `translation` added

**Verification:**
- `uv run ruff check src/backend/conftest.py`
- No test behavior changes during execution (cleanup only runs in teardown)

---

### T9 — Update middleware + context processor tests for Option C default

**Risk:** low (test assertions reflect new behavior)
**Depends on:** T1b (middleware + context processor changed)
**Parallel-safe:** yes (with T1)

**Description:** Update tests that assert `"ru"` as the fallback/default
to assert the new behavior: the default follows `settings.LANGUAGE_CODE`
(which is "en" in test, "ru" in production).

**Files (5 files, ~12 edit points):**

1. `src/backend/apps/core/tests/test_language_middleware.py`
   - L5-6 docstring: `> default to Russian` → `> default to settings.LANGUAGE_CODE`
   - `test_invalid_lang_param_defaults_to_russian` → rename to
     `test_invalid_lang_param_defaults_to_language_code`; L91 assertion `"ru"` → `"en"`
   - `test_accept_language_unsupported_falls_back` → rename to
     `test_accept_language_unsupported_falls_back_to_language_code`; L145 `"ru"` → `"en"`
   - `test_accept_language_empty_string` → rename to
     `test_accept_language_empty_string_falls_back_to_language_code`; L152 `"ru"` → `"en"`
   - `test_default_to_russian` → rename to `test_default_to_language_code`; L162 `"ru"` → `"en"`
   - `test_thread_local_matches_request_language_code` (L252-258): two cases
     change `"ru"` → `"en"`:
     - `(None, None, "fr-FR,fr;q=0.9", "ru")` → `"en"`
     - `({}, None, None, "ru")` → `"en"`
   - `test_invalid_lang_still_syncs_to_russian` → rename to
     `test_invalid_lang_still_syncs_to_language_code`; L276 `"ru"` → `"en"`

2. `src/backend/apps/core/tests/test_language_end_to_end.py`
   - L45-49: Remove the `_locale_cleanup` autouse fixture (superseded by T2/T3's
     shared conftest fixture)
   - `test_default_no_signal_renders_russian` (L138) → rename to
     `test_default_no_signal_renders_english`; assertions:
     - L143: `TITLE_RU` in content → `TITLE_EN` in content
     - L144: `DESC_RU` in content → `DESC_EN` in content
     - L147: `translation.get_language() == "ru"` → `"en"`
   - `test_invalid_lang_falls_back_to_russian_and_does_not_persist` (L149) → rename to
     `test_invalid_lang_falls_back_to_english_and_does_not_persist`; assertions:
     - L156: `TITLE_RU` in content → `TITLE_EN` in content
     - L159: `translation.get_language() == "ru"` → `"en"`

3. `src/backend/apps/core/tests/test_context_processors.py`
   - `test_language_defaults_to_russian_when_not_set` (L51-55) → rename to
     `test_language_defaults_to_settings_language_code_when_not_set`;
     assertion L55: `{"LANGUAGE_CODE": "ru"}` → `{"LANGUAGE_CODE": "en"}`
   - `test_language_handles_explicit_russian` (L58-63) — no change needed (explicit "ru" still works)
   - Remove `_activate_russian` autouse fixture (L21-26) — T3 handles cleanup
   - Migrate `translation.activate("ru")` calls (L87, 108, 136, 169, 191, 201, 210, 223)
     to `translation.override("ru")` context managers (T5)

**Acceptance criteria:**
- [ ] All middleware tests with "ru" default assertions now assert "en" (or settings.LANGUAGE_CODE)
- [ ] All e2e tests with Russian-default assertions now assert English by default
- [ ] Context processor tests use `translation.override("ru")` instead of `translation.activate("ru")`
- [ ] Context processor default test asserts `settings.LANGUAGE_CODE` ("en")

**Verification:**
- `make test PYTEST_OPTS="-k 'test_language_middleware or test_language_end_to_end or test_context_processors'"`

---

### T3 — Remove local language cleanup fixtures (superseded by T2)

**Risk:** none (centralized fixture replaces per-file fixtures)
**Depends on:** T2
**Parallel-safe:** no

**Description:** Remove per-file autouse cleanup fixtures now that the shared
fixture in T2 handles teardown globally.

**Files:**

1. `src/backend/apps/core/tests/test_context_processors.py`
   - Remove `_activate_russian` autouse fixture (L21-26) entirely
   - **Migration:** Tests that call `header_context()` directly rely on the
     activated thread-local language for `_()` calls and `city.get_name(locale)`.
     With `_activate_russian` removed and T5's `translation.override("ru")`
     migration applied, each test wraps its `header_context(request)` call in
     `with translation.override("ru"):`. The shared conftest `deactivate()`
     fixture handles teardown.

2. `src/backend/apps/core/tests/test_language_end_to_end.py`
   - Remove `_locale_cleanup` autouse fixture (L45-49)

3. `src/backend/apps/core/tests/test_language_middleware.py`
   - Remove `translation.deactivate()` from the `middleware` fixture teardown (L49)
     — the shared conftest fixture handles it.

**Acceptance criteria:**
- [ ] No per-file `translation.deactivate()` in test teardown
- [ ] No per-file `_activate_russian` / `_locale_cleanup` autouse fixtures
- [ ] `translation.override("ru")` used for unit tests that need Russian

**Verification:**
- `make test PYTEST_OPTS="-k 'test_context_processors'" `

---

### T5 — Replace `translation.activate()` with `translation.override()` in unit tests

**Risk:** low (context manager is the Django-recommended pattern)
**Depends on:** none (independent of other tasks)
**Parallel-safe:** yes

**Description:** Migrate `translation.activate("ru")` calls in unit tests
(that bypass the middleware) to `translation.override("ru")` context manager
for automatic cleanup and correct previous-language restoration.

**Files:**

1. `src/backend/apps/core/tests/test_context_processors.py`
   - L87: `translation.activate("ru")` → wrap subsequent code in
     `with translation.override("ru"):`, closing the `with` block at the end
     of the assertion. Since the autouse `_activate_russian` fixture is removed
     (T3), each test that needs Russian must use `translation.override("ru")`.
   - L108, 136, 169, 191, 201, 210, 223: same pattern

   **Pattern for each test:**
   Before (e.g. `test_country_wide_label_when_no_preference`):
   ```python
   translation.activate("ru")
   result = _call_header_context(request)
   assert result["context"]["preferred_city_display"] == "Вся страна"
   ```
   After:
   ```python
   with translation.override("ru"):
       result = _call_header_context(request)
   assert result["context"]["preferred_city_display"] == "Вся страна"
       assert "cities" in result["context"]
   ```

   Wait — `header_context()` calls `_("Entire country")` which uses the
   thread-local translation. The `translation.override()` context manager
   sets the thread-local for the duration of the `with` block. So the
   `header_context` call MUST be inside the `with` block. The assertions on
   the result can be outside (the result is already computed).

   ```python
   with translation.override("ru"):
       result = _call_header_context(request)
   assert result["context"]["preferred_city_display"] == "Вся страна"
   assert "cities" in result["context"]
   ```

2. `src/backend/apps/core/tests/test_language_middleware.py`
   - The `middleware` fixture uses `yield mw` then `translation.deactivate()`.
     Per T3, the `deactivate()` is removed (shared conftest handles it).
     Tests that assert `translation.get_language()` after
     `middleware.process_request(request)` are safe — assertions run in the
     test body before teardown.

**Acceptance criteria:**
- [ ] All `translation.activate("ru")` in unit tests replaced with
      `translation.override("ru")` context managers
- [ ] No manual `translation.deactivate()` in unit test fixtures

**Verification:**
- `make test PYTEST_OPTS="-k 'test_context_processors'"`

---

### T7 — Update tests with Russian UI assertions to use explicit `?lang=ru`

**Risk:** low (tests become explicit about expected language)
**Depends on:** T1 (default is "en"), T1b (middleware respects LANGUAGE_CODE)
**Parallel-safe:** yes (different test files)

**Description:** Tests that assert on Russian UI text through `client.get()`
without an explicit language signal will now get English (the new default).
Fix by adding `?lang=ru` to the request URL or `Accept-Language: ru` header.

Per Q2=A, prefer `Accept-Language` header for integration tests (tests the
middleware's Accept-Language path, doesn't pollute URL under test). However,
where the URL already has query params, `?lang=ru` is simpler. Use judgment per test.

**Files (9 files):**

1. `src/backend/apps/ads/tests/test_i18n_category_city.py`
   - `test_detail_defaults_to_ru` (L101-120): Rename to
     `test_detail_defaults_to_en` and update assertions:
   - L116: `client.get(reverse("ads:detail", args=[ad.id]))` → unchanged (default is now "en")
   - L119: `assert "Транспорт" in content` → `assert "Transport" in content`
   - L120: `assert "Тестград" in content` → `assert "Testgrad" in content`
   - **Also add** `test_detail_renders_ru_names`: new test with `?lang=ru` asserting
     Russian names render.

2. `src/backend/apps/ads/tests/test_favorites.py`
   - L80: `resp = client.post(f"/favorite/{ad.id}/")` →
     `resp = client.post(f"/favorite/{ad.id}/?lang=ru")` (asserts Russian "Войти для сохранения")
   - L194: `resp = client.get("/cabinet/favorites/")` →
     `resp = client.get("/cabinet/favorites/?lang=ru")` (asserts Russian "Пока нет избранного")

   Actually, per Q2=A, prefer Accept-Language header. But the POST to
   /favorite/ is an HTMX fragment endpoint — Accept-Language works fine.
   Let me use `?lang=ru` for simplicity since these are fragment-rendering tests
   and the URL doesn't carry other params.

3. `src/backend/apps/cabinet/tests/test_favorites_badge.py`
   - L38: `resp = Client().get("/cabinet/favorites/count/")` →
     `headers={"Accept-Language": "ru"}` or `?lang=ru`
   - L42: `assert 'aria-label="Войдите, чтобы сохранять избранное"' in content` (needs ?lang=ru)
   - L44: `assert "Войдите, чтобы сохранять избранное" in content` (needs ?lang=ru)
   - L70: `resp = client.get("/cabinet/favorites/count/")` →
     `headers={"Accept-Language": "ru"}` (needs ?lang=ru for L73)
   - L73: `assert 'aria-label="Моё избранное"' in content` (needs ?lang=ru)

4. `src/backend/apps/cabinet/tests/test_cabinet_sections.py`
   - L63: `resp = _login(buyer).get("/cabinet/settings/")` →
     `resp = _login(buyer).get("/cabinet/settings/?lang=ru")` (asserts Russian "Настройки")
   - L167: `resp = client.get("/cabinet/search-history/")` →
     `resp = client.get("/cabinet/search-history/?lang=ru")` (asserts Russian "Нет истории поиска")

5. `src/backend/apps/ads/tests/test_dashboard_stats.py`
   - L274: `response = dashboard_client.get("/dashboard/")` →
     `response = dashboard_client.get("/dashboard/?lang=ru")` (asserts Russian in L284-296)
   - L281: `response = dashboard_client.get("/dashboard/")` →
     `response = dashboard_client.get("/dashboard/?lang=ru")`
   - L290: `response = dashboard_client.get("/dashboard/")` →
     `response = dashboard_client.get("/dashboard/?lang=ru")`

6. `src/backend/apps/search/tests/test_saved_search_create.py`
   - L63: `assert ss.language == "ru"` → `assert ss.language == "en"`
     (The middleware now defaults to settings.LANGUAGE_CODE = "en" in test;
     the view reads request.LANGUAGE_CODE which is "en" for no-signal requests.
     Comment L63: "# test default LANGUAGE_CODE" → update to reflect new default)

7. `src/backend/apps/search/tests/test_preferred_city.py`
   - L132: `translation.activate("ru")` before `client.get("/")` →
     replace with `?lang=ru` on the GET request (L135). Remove the activate call.
   - L150: same pattern (L150 activate, L151 GET)
   - L180: same pattern (L180 activate, L181 GET)

8. `src/backend/apps/search/tests/test_preferred_city_readback.py`
   - L230: `translation.activate("ru")` before `client.get("/city/budva/")` (L234) →
     replace with `?lang=ru` on the GET request. Remove activate call.
   - L245: same pattern (L245 activate, L247 GET)
   - L265: same pattern (L265 activate, L270 GET)
   - L298: `translation.activate("ru")` before `client.get(reverse(...))` (L300) →
     replace with `?lang=ru`. Remove activate call.
   - L313: same pattern

9. `src/backend/apps/ads/tests/test_auth_nav.py`
   - Remove all 9 `translation.activate("ru")` calls (L80, 93, 105, 113, 124, 140, 150, 161, 173)
   - Replace with `Accept-Language: ru` header on the `client.get()` call, OR `?lang=ru`
     in the URL. Per Q2=A, prefer `Accept-Language` header.

   For each method in `TestAnonymousHeader` and `TestAuthenticatedHeader`:
   - L79-81: `translation.activate("ru")` + `client.get("/")` → `client.get("/", headers={"Accept-Language": "ru"})`
   - L92-93: same pattern with `reverse("ads:detail", args=[published_ad.id])`
   - L104-105: same with `/login/issue/`
   - L112-113: same with `/dashboard/`
   - L123-124: same with `reverse("ads:dashboard")`
   - L139-140: same with `reverse("ads:dashboard")`
   - L149-150: same with `reverse("ads:dashboard")`
   - L160-161: same with `reverse("ads:dashboard")`
   - L172-173: same with `/`

   Also remove the unused `from django.utils import translation` import (L22)
   if no longer used.

10. `src/backend/apps/ads/tests/test_breadcrumbs_render.py`
    - Remove 4 `translation.activate("ru")` calls (L102, 112, 139, 152)
    - Replace with `Accept-Language: ru` header on `client.get()`

    For each test:
    - L102: `translation.activate("ru")` + `client.get("/category/business/")` →
      `client.get("/category/business/", headers={"Accept-Language": "ru"})`
    - L112: same pattern with `/category/business-commercial-real-estate/`
    - L139: same pattern with `reverse("ads:detail", args=[ad.id])`
    - L152: same pattern with `/`

    Also remove the unused `from django.utils import translation` import (L25).

**Acceptance criteria:**
- [ ] All tests asserting on Russian UI text through `client.get()` have explicit `?lang=ru` or `Accept-Language: ru`
- [ ] `test_detail_defaults_to_ru` → renamed + asserts English by default
- [ ] `ss.language == "ru"` → `ss.language == "en"`
- [ ] No `translation.activate("ru")` remains in integration tests (only in unit tests using `translation.override`)
- [ ] `from django.utils import translation` import removed from files that no longer use it

**Verification:**
- `make test PYTEST_OPTS="-k 'test_favorites or test_auth_nav or test_breadcrumbs or test_preferred_city or test_cabinet_section or test_dashboard_stats or test_i18n_category_city or test_saved_search'"`

---

### T4 — Remove redundant `translation.activate("ru")` in integration tests

**Note:** This task overlaps heavily with T7. T7 handles the test-impact fixes
(Russian UI assertions need explicit language). T4 is the "remove the redundant
calls" part — for tests that assert on non-translatable content (status codes,
URLs, HTML structure), the `translation.activate("ru")` is simply removed
with no replacement (no language signal needed; default applies).

**Risk:** low
**Depends on:** T2, T3
**Parallel-safe:** yes

**Description:** In integration tests, `translation.activate("ru")` before
`client.get()` is redundant because the middleware overrides it. For tests
that don't assert on translated text, the call is removed entirely. For tests
that assert on Russian text, `?lang=ru` or `Accept-Language` is added (T7).

**Files:** Already covered by T7's file list. This task is the "remove
redundant calls where no language assertion exists" subset.

After T7 completes, verify no `translation.activate("ru")` remains in any
integration test file. Unit tests should use `translation.override("ru")`.

**Acceptance criteria:**
- [ ] No `translation.activate("ru")` in integration test files (replaced by
      `?lang=ru` or `Accept-Language` header, or removed if unnecessary)
- [ ] `from django.utils import translation` imports removed where unused

**Verification:**
- `cd src/backend && uv run grep -r 'translation.activate' apps/` (should only
  appear in unit tests, not integration tests)

---

### T6 — Document standardized convention in conftest.py

**Risk:** none (documentation only)
**Depends on:** T1, T2, T4
**Parallel-safe:** no

**Description:** Add a documentation comment to `src/backend/conftest.py`
describing the language testing standard, so agents see it before writing tests.

**Files:**
- `src/backend/conftest.py` — add a comment block above the autouse fixture

**Changes:**
```python
# ---------------------------------------------------------------------------
# i18n testing standard (Spec 07)
#
# Default test language is English (LANGUAGE_CODE = "en" in test.py), matching
# the msgid source language. Tests asserting on English UI text pass without
# extra setup.
#
# Integration tests (Client-based): drive the language via the middleware's
# priority order — ?lang=ru or Accept-Language: ru header. NEVER call
# translation.activate() before client.get() — LanguagePreMiddleware overrides
# it during request processing (no effect on rendered output).
#
# Unit tests (no middleware): use translation.override(lang) context manager
# for automatic cleanup.
#
# Thread-local cleanup: the autouse _reset_translation_state fixture below calls
# translation.deactivate() in teardown, eliminating all inter-test leakage.
# Do NOT add per-file deactivate() calls.
# ---------------------------------------------------------------------------
```

**Acceptance criteria:**
- [ ] Comment block added to `conftest.py` documenting the standard
- [ ] References the autouse fixture by name for visibility

**Verification:** Read the file back — comment present and accurate.

---

### T8 — Update project documentation (rules.md)

**Risk:** none (documentation only)
**Depends on:** T6
**Parallel-safe:** no

**Description:** Add an "i18n / Language Testing" subsection to the Testing
Conventions section of `docs/99-agent/rules.md`.

**Files:**
- `docs/99-agent/rules.md`

**Changes:** Add a new subsection after the existing Testing Conventions
section:

```markdown
### i18n / Language Testing

The test environment uses English as the default language
(`LANGUAGE_CODE = "en"` in `config/settings/test.py`), matching the msgid
source language. This means tests asserting on English UI strings (e.g.
`"Clear all filters"`, `"Page navigation"`) pass without explicit language
setup.

**Integration tests (using Django `Client`):**

- Set the language via the middleware's documented priority order:
  `?lang=X` query parameter or `Accept-Language` HTTP header.
- **Never** call `translation.activate()` before `client.get()` — the
  `LanguagePreMiddleware` overrides it during request processing, making
  the pre-activation a no-op for rendered content. Use `?lang=ru` or
  `Accept-Language: ru` to get Russian output.
- For URLs with no other query params, `?lang=ru` is convenient. Where the
  URL carries meaningful query params, prefer `Accept-Language` header to
  avoid polluting the URL under test.

**Unit tests (no middleware, direct function calls):**

- Use the `translation.override(lang)` context manager for any
  locale-specific rendering. It provides automatic rollback (even on
  exceptions) and restores the *previous* language on exit.

**Thread-local cleanup:**

- An autouse `translation.deactivate()` fixture in `src/backend/conftest.py`
  eliminates all thread-local translation state leakage between tests. Do
  **not** add per-file `deactivate()` calls — they are now redundant.

**Parametrized multi-language tests:**

- Use `LanguageLocale.values()` (the StrEnum), not bare string literals,
  per project rule #10.
```

**Acceptance criteria:**
- [ ] "i18n / Language Testing" subsection added to `rules.md`
- [ ] Documents the English default, request-signal approach, `translation.override()` for unit tests, and the autouse cleanup fixture

**Verification:** Read the file back — content is present and accurate.

---

## 6. Implementation Sequencing Summary

### 6.1 Critical ordering constraints

1. **T2 before everything else** — the autouse `deactivate()` fixture must exist
   before any test changes to guarantee no leakage during the migration.
2. **T1b before T1** — the middleware must respect `settings.LANGUAGE_CODE`
   before `test.py` sets it to `"en"`, otherwise T1 is a no-op (the middleware
   still hardcodes "ru").
3. **T1 + T1b before T7/T9** — the default only becomes "en" when both are
   applied; tests can only be updated after the new behavior is in place.
4. **T3 before T4** — local cleanup fixtures must be removed first; the shared
   conftest fixture must be the sole cleanup mechanism.
5. **T5 can run in parallel with T1b/T1** — unit test migration is independent.
6. **T9 (middleware test updates) after T1b** — tests assert the new default.
7. **T6/T8 last** — documentation must match the final implementation.

### 6.2 Parallel execution groups

| Group | Tasks | Notes |
|---|---|---|
| Phase 1 | T2 | Autouse fixture (zero risk) |
| Phase 2 | T1b, T5 | Middleware change + unit test migration (parallel) |
| Phase 3 | T1, T9 | Test settings + middleware test updates (parallel) |
| Phase 4 | T7, T3 | Russian-asserting test fixes + remove local fixtures (parallel) |
| Phase 5 | T4 | Remove remaining redundant activate calls |
| Phase 6 | T6, T8 | Documentation |
| Phase 7 | T10 | Final verification |

---

## 7. Verification Strategy

| Method | Scope | Task |
|---|---|---|
| `uv run ruff check` | Lint all changed files | Every task |
| `uv run basedpyright` | Type-check changed Python | T1b, T9, T10 |
| `make test` | Fast gate (skips `seed`, ~1 min) | T10 |
| `make test PYTEST_OPTS="-k 'language or i18n or context_processor or favorites or auth_nav or breadcrumbs or preferred_city or saved_search or cabinet or dashboard_stats'"` | Affected test modules | T7, T9, T10 |
| `test_i18n_completeness.py` | 5 i18n guard tests | T10 |
| `test_i18n_pipeline.py` | 5 i18n pipeline tests | T10 |

### 7.1 Test environment reminder

Tests run inside Docker (`make test` / `make test-recreate`). The test DB
container must be running on port 5433:
```powershell
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db
```
Never run `uv run pytest` locally (DB unreachable on `localhost:5432`);
always route through the `test` Compose service. `.mo` files are compiled
in the Docker entrypoint before pytest.

---

## 8. Out of Scope

- No new translatable strings (`.po`/`.mo` unchanged) — all changes are
  in test infrastructure and test assertions, plus the middleware/context
  processor fallback mechanism.
- No production behavior change: `base.py` keeps `LANGUAGE_CODE = "ru"`,
  so the middleware still defaults to Russian in production.
- No schema/migration changes.
- No changes to the Telegram bot test suite (bot tests don't assert on
  translated UI text).

---

## 9. Acceptance Criteria Cross-Reference

| Spec § | Acceptance criterion | Task(s) |
|---|---|---|
| T1 | `test.py` sets `LANGUAGE_CODE = "en"` | T1 |
| T1b | Middleware + context processor use `settings.LANGUAGE_CODE` as fallback | T1b |
| T2 | Autouse `deactivate()` fixture in root conftest | T2 |
| T7 | All Russian UI tests have explicit `?lang=ru` / `Accept-Language` | T7 |
| T9 | Middleware tests reflect `settings.LANGUAGE_CODE` default | T9 |
| T3 | No per-file cleanup fixtures remain | T3 |
| T5 | Unit tests use `translation.override()`, not `activate()` | T5 |
| T4 | No redundant `translation.activate("ru")` in integration tests | T4 |
| T8 | Documentation updated in `rules.md` | T8 |
| T10 | `make test` fast gate passes | T10 |
