# Specification: Test Language Standardization — Deterministic i18n in the Test Suite

**Status:** Draft — incorporates Researcher findings (Task-1 architecture audit, Task-2 best-practices audit). PO decisions Q1–Q4 carry analyst-recommended defaults confirmed by research; PO sign-off requested on the specific mechanism choices.  
**Version:** 1.0  
**Date:** 2026-09-04  
**Source Problem:** `.ai/problems/Problem_06.md` (RU)  

---

## 1. Problem Statement

Agents repeatedly encounter test failures caused by ambiguous language configuration. Tests that assert on English `msgid` strings (e.g., `"Clear all filters"`, `"Page navigation"`, `"Previous image"`) fail because the rendered output is in Russian (`"Очистить все фильтры"`), and the agent cannot determine whether the failure is their code or an architectural test issue. The root cause is threefold:

1. **`test.py` inherits `LANGUAGE_CODE = "ru"` from `base.py` and does not override it** — Russian is the default language for all test requests, but English is the `msgid` language, so English-text assertions require explicit language switching.
2. **No standardized language mechanism exists for tests** — three different approaches coexist: `translation.activate("ru")` (called before `client.get()`, where it is redundant because the middleware overrides it), `Accept-Language` HTTP headers, and `?lang=X` query parameters. No single approach is documented or enforced.
3. **No autouse cleanup for thread-local translation state** — tests that call `translation.activate()` or that leave the middleware-activated thread-local at a non-default language ("en" or "bs") leak state to subsequent tests on the same xdist worker, creating latent flakiness.

### Concrete failure scenario

```python
def test_clear_all_button_rendered(self, seller, category, city):
    create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    client = Client()
    response = client.get("/?features=delivery", headers={"HX-Request": "true"})
    # FAILS: no ?lang= or Accept-Language header → middleware defaults to "ru"
    # → {% trans "Clear all filters" %} renders as "Очистить все фильтры"
    assert "Clear all filters" in response.content.decode()
```

The agent sees this failure and cannot tell whether they broke the template, the view, or simply hit the language default.

---

## 2. Facts (Verified by Code Analysis + Researcher Audit)

### 2.1 Settings layer

| Setting | `base.py` | `test.py` | `dev.py` |
|---|---|---|---|
| `LANGUAGE_CODE` | `"ru"` (line 67) | Inherits `"ru"` (no override) | Inherits `"ru"` (no override) |
| `USE_I18N` | `True` (line 68) | Inherits | Inherits |
| `LANGUAGES` | `ru`, `bs`, `en` (lines 69–73) | Inherits | Inherits |
| `LOCALE_PATHS` | `BASE_DIR / "backend" / "locale"` (line 74) | Inherits | Inherits |

`test.py` overrides only: `DEBUG`, SSL/secure-cookie settings, `DATABASES["default"]["NAME"]`, `STORAGES` (StaticFilesStorage), `PASSWORD_HASHERS` (MD5), `CACHES` (LocMemCache), and `MIGRATION_MODULES` (DisableMigrations). **No language override anywhere.**

### 2.2 Middleware: `LanguagePreMiddleware`

**File:** `src/backend/apps/core/middleware/language.py` (148 lines)

The middleware **replaces** Django's `LocaleMiddleware` (which is absent from `MIDDLEWARE`, line 132). Its resolution priority is documented in the module docstring and implemented in `process_request` (lines 57–74):

| Priority | Signal source | Resolution code |
|---|---|---|
| 1 | `?lang=X` query parameter | `request.GET.get("lang")` → `_apply_lang_param()` (lines 96–118) |
| 2 | `lang_pref` cookie | `request.COOKIES.get("lang_pref")` → `_set_language_code()` (line 66) |
| 3 | `Accept-Language` HTTP header | `_parse_accept_language()` (lines 131–143) → `_set_language_code()` (line 71) |
| 4 | Default | `LanguageLocale.RUSSIAN.value` → `_set_language_code()` (line 74) |

**Critical behavior** (line 128): `translation.activate(lang)` is called **unconditionally** on every request in `_set_language_code()` (lines 120–129). This means:

- **Any `translation.activate()` called by a test before `client.get()` is overridden** by the middleware during request processing.
- After `client.get()` returns, the thread-local active language is whatever the middleware resolved — **not** what the test pre-activated.
- `request.LANGUAGE_CODE` is synced to `translation.get_language()` (line 129).

The middleware name constant and cookie configuration are:
- `LANGUAGE_COOKIE_NAME = "lang_pref"` (line 34)
- `LANGUAGE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60` (1 year, line 35)

### 2.3 Three language mechanisms (verified by researcher)

1. **`settings.LANGUAGE_CODE` ("ru")** — the static fallback/floor. Used by `translation.get_language()` when no language is activated (thread-local is unset).
2. **Thread-local activated language** — set by `translation.activate(lang)`, read by `{% trans %}`, `{% get_current_language %}`, `translation.get_language()`, and Django's `i18n` context processor.
3. **`request.LANGUAGE_CODE`** — set per-request by the middleware; exposed to templates via the custom `language` context processor (`apps/core/context_processors.py` line 24: `getattr(request, "LANGUAGE_CODE", "ru")`), which overrides Django's `i18n` context processor's `LANGUAGE_CODE`.

### 2.4 The "why `translation.activate()` before `client.get()` is ineffective" proof

Django's test `Client` runs the **full middleware stack** on each request. `LanguagePreMiddleware.process_request` (invoked during `client.get()`) calls `translation.activate(resolved_lang)` per request signals. Since no `?lang=`, `lang_pref` cookie, or `Accept-Language` header is sent, the middleware resolves to `"ru"` (line 74), **overriding** any `translation.activate("ru")` the test called beforehand. The pre-activation is therefore:
- **Redundant** for integration tests (middleware re-sets the same value)
- **Misleading** (suggests the test controls the language, when it doesn't)
- **Leaky** (if the test sets a *different* language like "en", that state persists after the request since `activate()` before `client.get()` is overridden by the middleware, but the middleware-set state is never cleaned up)

### 2.5 Complete inventory of language-handling patterns (verified, file:line cited)

| Pattern | Files | Thread-local cleanup? |
|---|---|---|
| `translation.activate("ru")` before `client.get()` + no cleanup | `test_auth_nav.py` (L80,93,105,113,124,140,150,161,173); `test_breadcrumbs_render.py` (L102,112,139,152); `test_preferred_city.py` (L132,150,180); `test_preferred_city_readback.py` (L230,245,265,298,313) | NO — leaks "ru" (coincidentally safe) |
| `Accept-Language: en` header in `client.get()` | `test_catalog_filters.py` (L790,843,862,881,905,920) | NO — leaks "en" (latent risk) |
| `?lang=en` / `?lang=bs` in `client.get()` | `test_catalog_filters.py` (L810); `test_gallery_markup.py` (L79); `test_i18n_category_city.py` (L69,92,139); `test_language_end_to_end.py` (L111,131,154,165,173,188); `test_submenu.py` (L68,75,90,92,98); `test_moderation_views.py` (L245,253) | NO — leaks resolved language (latent risk) |
| `translation.activate()` + autouse `translation.deactivate()` | `test_context_processors.py` (L21–26, L87,108,136,169,191,201,210,223); `test_language_end_to_end.py` (L45–49); `test_language_middleware.py` (L43–49) | YES — proper cleanup |
| No language setup (rely on middleware default "ru") | `test_favorites.py`, `test_saved_search_create.py`, `test_detail_render.py`, `test_detail_context.py`, `test_ad_detail_queries.py`, `test_ad_localization.py`, `test_privacy.py`, `test_templates.py`, `test_i18n_completeness.py`, `test_i18n_pipeline.py`, `test_autocomplete.py`, `test_autocomplete_template.py` | N/A — no activation, no leak |
| Static template file analysis (no rendering) | `test_catalog_filters.py` (L638–741), `test_templates.py` (L104–145), `test_i18n_completeness.py` | N/A |
| `translation.override()` context manager | **Not used anywhere** in the test suite | N/A |
| `translation.deactivate_all()` (NullTranslations baseline) | **Not used anywhere** | N/A |

### 2.6 Thread-local leakage assessment (verified)

**Category 1 — Leaks "ru" (LOW risk, coincidentally safe):** `translation.activate("ru")` in 21 methods across 4 files, no `deactivate()`. Leaves thread-local at "ru" (the project default). A subsequent test making `client.get()` is safe (middleware re-resolves). A subsequent test calling `translation.get_language()` directly without a request would see "ru" — which is the default, so no behavioral impact. **This is still a violation** — the thread-local should be cleaned up.

**Category 2 — Leaks "en" (MEDIUM risk, latent):** `Accept-Language: en` and `?lang=en` in `test_catalog_filters.py` (6 methods), `test_gallery_markup.py` (1 helper), `test_i18n_category_city.py` (2 methods). Leaves thread-local at "en". If a subsequent test on the same xdist worker calls `translation.get_language()` directly without a request, it sees "en" instead of "ru" → **wrong result**. Currently masked because:
- pytest-xdist (`-n auto`) isolates workers, but intra-worker sequential execution still leaks.
- No existing test reads `translation.get_language()` after a leaked "en" test without first making its own `client.get()` or `translation.activate()`.

**Category 3 — Leaks "bs" (LOW risk, latent):** `?lang=bs` in `test_i18n_category_city.py`, `test_submenu.py`, `test_moderation_views.py`. Same mechanism as Category 2.

**Files WITH proper cleanup (3 files):** `test_context_processors.py` (autouse `_activate_russian` fixture, L21–26), `test_language_end_to_end.py` (autouse `_locale_cleanup`, L45–49), `test_language_middleware.py` (`middleware` fixture teardown, L49).

### 2.7 The `LanguageLocale` StrEnum (canonical locale list)

**File:** `src/backend/apps/core/enums.py` (lines 188–239)

```python
class LanguageLocale(StrEnum):
    RUSSIAN = "ru"
    BOSNIAN = "bs"
    ENGLISH = "en"
```

- `LanguageLocale.values()` returns `["ru", "bs", "en"]` (lines 196–198).
- `LanguageLocale.from_code("en-US")` → `ENGLISH` (lines 201–220).
- Per project rule #10 (StrEnum for all constants), test parametrization across languages should use `LanguageLocale.values()`, not bare string literals.

### 2.8 `test.py` does not compile `.mo` files

File `.mo` files are **not** in version control (`.gitignore` line 55 per the agent rules doc). `compilemessages` is run in the Docker entrypoint before pytest. The `test_i18n_completeness.py::test_mo_compiled` test (line 298) and `test_i18n_pipeline.py::test_mo_files_exist` (line 113) enforce this in CI. This means **test assertions on translated text require `.mo` files to be compiled** — which the test runner handles, but new developers running tests locally without `compilemessages` would see empty msgstr (msgid fallback).

---

## 3. Confirmed Requirements

| ID | Requirement | Source |
|---|---|---|
| CR-1 | Test settings must establish a deterministic default language for the test environment. | Problem_06 §1–2 |
| CR-2 | Tests asserting on English `msgid` strings must not fail due to Russian default rendering. | Problem_06 §3 (the "Clear all filters" / "Очищить все фильтры" failure) |
| CR-3 | Thread-local translation state must not leak between tests (autouse cleanup). | Project rule #2 (production code is king; tests must be reliable) + AGENTS.md testing conventions |
| CR-4 | Integration tests (using Django `Client`) must set language via the middleware's documented priority order (`?lang=X` > cookie > `Accept-Language` > default), NOT via `translation.activate()` before the request (which the middleware overrides). | Researcher Task-2 §3.1 — `translation.activate()` before `client.get()` is overridden by `LanguagePreMiddleware.process_request` |
| CR-5 | Unit tests (not using `Client`/middleware) must use `translation.override(lang)` context manager for any locale switching — automatic cleanup, no manual teardown required. | Django docs (refer/utils — `translation.override()`) |
| CR-6 | `translation.activate("ru")` calls that are redundant with the middleware (i.e., called before `client.get()` with no language signals) must be removed from integration tests. | Researcher Task-1 §4 (redundant activation pattern) |
| CR-7 | Tests that assert `translation.get_language()` after a `client.get()` request must do so within the test body (before teardown), and the assertion must reflect the middleware-set value. | Researcher Task-2 §2.5 |
| CR-8 | Parametrized multi-language tests must use `LanguageLocale.values()` (the StrEnum), not bare string literals. | Project rule #10 (StrEnum for all constants) |
| CR-9 | The standardization must be additive (an autouse fixture in root `conftest.py`) — it cannot break existing tests' assertions during their own execution (cleanup runs only in teardown). | Researcher Task-2 §4 (Approach A — LOW risk) |

---

## 4. Conceptual Development Tasks

### Task T1 — Set deterministic default language in test settings

- **Purpose:** Override `LANGUAGE_CODE` in `test.py` so that tests have a deterministic default that matches the `msgid` (English), making English-text assertions pass without extra setup.
- **Expected outcome:** `test.py` sets `LANGUAGE_CODE = "en"`. Tests that don't specify a language get English (msgid) output by default.
- **Changes:** Add `LANGUAGE_CODE = "en"` to `src/backend/config/settings/test.py`.
- **Dependencies:** None.
- **Affected files:** `src/backend/config/settings/test.py`.
- **Test impact:** Tests currently relying on the default Russian output (e.g., `test_i18n_category_city.py::test_detail_defaults_to_ru` which asserts "Транспорт" in content when no language signal is sent) will **fail** — they must be updated to explicitly set Russian. This is the correct behavior: tests should be explicit about expected language.

### Task T2 — Add autouse thread-local translation cleanup to root conftest

- **Purpose:** Eliminate all thread-local translation state leakage between tests.
- **Expected outcome:** An autouse, function-scoped fixture in `src/backend/conftest.py` calls `translation.deactivate()` in teardown, restoring `settings.LANGUAGE_CODE` as the active thread-local language.
- **Changes:** Add the fixture + import to `src/backend/conftest.py`:
  ```python
  from django.utils import translation

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
- **Dependencies:** None.
- **Affected files:** `src/backend/conftest.py`.
- **Test impact:** None during test execution (cleanup runs in teardown only). Eliminates Categories 1–3 leakage from §2.6.

### Task T3 — Remove local language cleanup fixtures (superseded)

- **Purpose:** Remove the per-file autouse cleanup fixtures that are now superseded by the shared fixture in T2, eliminating duplication.
- **Expected outcome:** No local `translation.deactivate()` teardown fixtures remain; all cleanup is centralized.
- **Changes:**
  - `test_language_end_to_end.py`: Remove `_locale_cleanup` autouse fixture (lines 45–49).
  - `test_language_middleware.py`: Remove `translation.deactivate()` from the `middleware` fixture teardown (line 49). The shared fixture handles it.
  - `test_context_processors.py`: Remove the `_activate_russian` autouse fixture (lines 21–26). The shared fixture's `deactivate()` in teardown restores to default; tests that need "ru" activation can use `translation.activate("ru")` directly (unit tests that call functions directly, bypassing middleware).
- **Dependencies:** T2.
- **Affected files:** `test_language_end_to_end.py`, `test_language_middleware.py`, `test_context_processors.py`.
- **Test impact:** The per-file fixtures were redundant with T2's shared fixture for teardown. The `_activate_russian` fixture in `test_context_processors.py` also *activates* "ru" before each test — removing it means tests must activate "ru" themselves if they call functions directly without a Client. These tests assert on Russian strings ("Вся страна"), so they need "ru" active. **This requires adding `translation.activate("ru")` to each test that calls `header_context()` directly.** (See T4 for the migration pattern.)

### Task T4 — Remove redundant `translation.activate("ru")` in integration tests

- **Purpose:** Remove the `translation.activate("ru")` calls in integration tests that use `Client` — these are redundant (the middleware resolves the language) and misleading (suggests the test controls the language before the middleware runs).
- **Expected outcome:** Integration tests that assert on Russian text must set the language via the middleware's priority order (`?lang=ru` or `Accept-Language: ru`), making the language signal explicit in the request.
- **Changes:** For each `translation.activate("ru")` call in a test that subsequently calls `client.get()`:
  - If the test asserts on Russian text → add `?lang=ru` to the request URL or `Accept-Language: ru` header.
  - If the test asserts on English text (msgid) → add `?lang=en` or `Accept-Language: en` header.
  - If the test asserts on non-translatable content (status codes, HTML structure, URLs) → remove the activation entirely (no language signal needed; default applies).
- **Files to update:**
  - `test_auth_nav.py` — 9 `translation.activate("ru")` calls (L80,93,105,113,124,140,150,161,173); tests assert on Russian strings ("Разместить объявление", ">Войти<", "Выйти", "Удалить данные", "Моё избранное")
  - `test_breadcrumbs_render.py` — 4 calls (L102,112,139,152); asserts on Russian strings
  - `test_preferred_city.py` — 3 calls (L132,150,180); asserts on Russian strings
  - `test_preferred_city_readback.py` — 5 calls (L230,245,265,298,313); asserts on Russian strings
  - `test_context_processors.py` — 8 inline calls (L87,108,136,169,191,201,210,223); these call functions directly (no middleware), so `translation.activate("ru")` IS effective — but should use `translation.override("ru")` instead (T5) for automatic cleanup.
- **Dependencies:** T2, T3.
- **Affected files:** `test_auth_nav.py`, `test_breadcrumbs_render.py`, `test_preferred_city.py`, `test_preferred_city_readback.py`, `test_context_processors.py`.
- **Test impact:** Tests must explicitly declare their expected language via `?lang=` or `Accept-Language` header. Tests asserting on English msgids that previously relied on... actually, currently `test_auth_nav.py` etc. use `translation.activate("ru")` redundantly. After T1 (default = "en"), these tests need `?lang=ru` to get Russian output.

### Task T5 — Replace `translation.activate()` with `translation.override()` in unit tests

- **Purpose:** Use the Django-recommended `translation.override()` context manager in unit tests that bypass the middleware (direct function calls, isolated template rendering), instead of `translation.activate()` + manual `deactivate()`.
- **Expected outcome:** Automatic cleanup, no manual teardown needed for locale-switching in unit tests.
- **Changes:** Replace `translation.activate("ru")` calls with `with translation.override("ru"):` blocks in:
  - `test_context_processors.py` (calls `header_context()` directly, no middleware)
  - `test_templates.py` (`query_replace` tag tests — though these don't currently activate language)
- **Dependencies:** None.
- **Affected files:** `test_context_processors.py`, `test_templates.py`.
- **Test impact:** `translation.override()` restores the *previous* language on exit (not necessarily `settings.LANGUAGE_CODE`), which is more correct for nested locale switching. The shared `deactivate()` fixture in T2 is still needed for middleware-driven tests.

### Task T6 — Standardize the integration-test helper pattern

- **Purpose:** Provide a reusable helper for tests that need to assert on English msgid text through the Django `Client`, so they don't each need to remember to add `Accept-Language: en` or `?lang=en`.
- **Expected outcome:** A documented helper or convention for English-assertion integration tests.
- **Changes:** Add a comment-level convention to the root `conftest.py` or project rules:
  - **Preferred:** `Accept-Language` header (e.g., `headers={"Accept-Language": "en"}`) — tests the middleware's Accept-Language path, doesn't modify the URL under test.
  - **Acceptable alternative:** `?lang=en` in the URL — tests the middleware's `?lang=` priority path.
  - Document: `translation.activate()` before `client.get()` is a no-op for the rendered output (middleware overrides it).
- **Dependencies:** T1, T2.
- **Affected files:** `src/backend/conftest.py` (documentation comment), `docs/99-agent/rules.md` (testing conventions section).
- **Test impact:** None (documentation/convention only).

### Task T7 — Update existing tests affected by the new default language

- **Purpose:** Fix the tests that will break when `test.py` sets `LANGUAGE_CODE = "en"` (T1), because they currently rely on the implicit Russian default.
- **Expected outcome:** All tests pass with the new test settings.
- **Changes:** Identify all tests that:
  1. Assert on Russian text through `client.get()` without explicitly setting a language signal → add `?lang=ru` or `Accept-Language: ru`.
  2. Assert `translation.get_language() == "ru"` after a `client.get()` with no language signal → add `?lang=ru` or `Accept-Language: ru`.
  3. Assert on Russian text through direct function calls (not Client) → these use `translation.activate("ru")` or `translation.override("ru")` — no change needed for language (but may need T5 migration).

  **Key file:** `test_i18n_category_city.py::test_detail_defaults_to_ru` (line 101) — asserts "Транспорт" and "Тестград" in content. After T1, the default would be English, so this test would fail. Must add `?lang=ru` to the request.

  **Key file:** `test_catalog_filters.py` — several tests assert on English text ("Page navigation", "Clear all filters", "Price:") with `Accept-Language: en` already set (lines 790, 843, 862, 881, 905, 920). These are **already correct**. Static template tests (lines 638–741) read raw template files, so language doesn't apply.

  **Key file:** `test_saved_search_create.py::test_create_saved_search_with_filters_and_language` (line 63) — asserts `ss.language == "ru"`. The view reads `request.LANGUAGE_CODE` which the middleware sets from the default "ru". After T1, the middleware's default is still "ru" (from `LanguageLocale.RUSSIAN.value` in the middleware, line 74 — not from `settings.LANGUAGE_CODE`). **This test is safe** — the middleware hardcodes the "ru" default, not `settings.LANGUAGE_CODE`.

- **Dependencies:** T1, T2, T4.
- **Affected files:** `test_i18n_category_city.py` and any test that asserts on Russian rendered text without a language signal.
- **Test impact:** Tests that previously worked by coincidence (middleware default "ru") must become explicit.

### Task T8 — Update project documentation

- **Purpose:** Document the standardized language-testing approach in the project rules.
- **Expected outcome:** The AGENTS.md testing conventions and rules.md include a clear "i18n / Language Testing" subsection.
- **Changes:** Add to `docs/99-agent/rules.md` under "Testing Conventions":
  - The default test language is English (`LANGUAGE_CODE = "en"` in `test.py`) — matches `msgid`.
  - Integration tests through `Client`: use `?lang=X` or `Accept-Language` header to set language. Never call `translation.activate()` before `client.get()` (middleware overrides it).
  - Unit tests bypassing the middleware: use `translation.override(lang)` context manager for automatic cleanup.
  - Thread-local cleanup is handled by an autouse `translation.deactivate()` fixture in root `conftest.py` — do NOT add per-file `deactivate()` calls.
  - Parametrize multi-language tests with `LanguageLocale.values()`.
- **Dependencies:** T1–T7.
- **Affected files:** `docs/99-agent/rules.md`.

---

## 5. Product Owner Decisions

| Q | Question | Options | Recommended choice | Rationale (backed by research) | Status |
|---|---|---|---|---|---|
| Q1 | Default test `LANGUAGE_CODE` | A: `"en"` (matches msgid) · B: `"ru"` (matches production default) · C: `"en"` + autouse Russian fixture | **A: `"en"`** | English = msgid string. Tests asserting on English UI text pass by default. Tests needing Russian must be explicit. Reduces surprise. Researcher Task-1 §2.2 confirms `LANGUAGE_CODE` is the fallback floor; setting it to "en" makes the test environment's default match the translatable string source. | Applied (recommended) |
| Q2 | Integration test language signal | A: `Accept-Language` header · B: `?lang=X` query param · C: `translation.activate()` | **A: `Accept-Language` header** | Most realistic HTTP behavior; tests the middleware's Accept-Language path; doesn't pollute the URL under test. Researcher Task-2 §3.1: `translation.activate()` before `client.get()` is overridden by `LanguagePreMiddleware.process_request` (line 128), making it a no-op for rendered content. `Accept-Language` header is the correct mechanism for driving the middleware. `query_replace` tests in `test_catalog_filters.py` already use `Accept-Language: en` with a comment explaining why (L787–790). | Applied (recommended) |
| Q3 | Thread-local cleanup | A: Autouse fixture in root `conftest.py` · B: Per-test `deactivate()` · C: No cleanup | **A: Autouse fixture in root `conftest.py`** | Single fixture eliminates all 30+ leaks. Follows Django's documented `tearDown` recommendation. Researcher Task-2 §2.2: verified that the current per-file cleanup is inconsistent (3 files clean, 4 files leaky). Root conftest is the canonical fixture location per AGENTS.md (`/Users/om/.kilo`... no, `src/backend/conftest.py`). | Applied (recommended) |
| Q4 | Unit test language control | A: Split — `translation.override()` for unit tests (bypass middleware), `?lang=`/header for integration tests (through middleware) · B: Unified `translation.activate()` everywhere · C: Unified `Accept-Language` everywhere | **A: Split strategy** | Each mechanism is the correct tool for its context. `translation.override()` provides automatic cleanup for unit tests that render templates directly (no middleware to override it). `Accept-Language`/`?lang=` drives the middleware for integration tests. Researcher Task-2 §3.3: this separation is the Django-recommended pattern — `translation.override()` when middleware is absent, request signals when it's present. | Applied (recommended) |

### Decision consequence map

- **Q1=A + T1**: `test.py` sets `LANGUAGE_CODE = "en"`. Tests asserting Russian text through `client.get()` without a language signal break → fixed by T7.
- **Q2=A + T4+T6**: Integration tests use `Accept-Language: en` for English assertions, `?lang=ru` for Russian assertions. Redundant `translation.activate("ru")` calls removed.
- **Q3=A + T2**: Root conftest gets autouse `deactivate()` fixture. Per-file cleanup fixtures removed (T3).
- **Q4=A + T4+T5**: Unit tests use `translation.override()`. Integration tests use request signals.

---

## 6. Research Summary

### Researcher Task-1: Current architecture audit (HIGH confidence)

1. **`LANGUAGE_CODE` in settings is the fallback floor, not the active language**, when `LocaleMiddleware` is absent. The middleware's `translation.activate()` per-request overrides it. This was confirmed by reading `base.py` (L67), `test.py` (no override), and `language.py` (L128: `translation.activate(lang)` unconditional).

2. **Three language mechanisms exist**: `settings.LANGUAGE_CODE` (static), thread-local `translation.activate()` (mutable, per-thread), `request.LANGUAGE_CODE` (per-request, set by middleware). They interact in a non-obvious way: `translation.activate()` before `client.get()` is overridden by the middleware.

3. **Thread-local leakage is real and categorized**:
   - 21 `translation.activate("ru")` calls in integration tests without cleanup → leaks "ru" (LOW risk, coincidentally safe)
   - 7 `Accept-Language: en` / `?lang=en` signals without cleanup → leaks "en" (MEDIUM risk, latent)
   - 5 `?lang=bs` signals without cleanup → leaks "bs" (LOW risk, latent)
   - 3 files have proper `translation.deactivate()` cleanup → no leak

4. **29 test files were inventoried** (see §2.5) — every file:line citation is from actual source code reading, not estimation.

5. **The root cause is architectural**: there is no single standard. The test settings don't define a deterministic default, there's no centralized cleanup fixture, and the `translation.activate()` pattern is misunderstood (agents think it controls the Client's rendered language, but it doesn't).

### Researcher Task-2: Best practices and approach evaluation (HIGH confidence)

1. **Django's documented testing patterns** (from Django docs `topics/testing/tools` and `ref/utils`):
   - `translation.override(lang)` context manager — for tests WITHOUT `LocaleMiddleware` (the Django-recommended approach, automatic cleanup)
   - Request signals (`Accept-Language` header, `lang_pref` cookie) — for tests WITH `LocaleMiddleware` (the correct approach when middleware is present)
   - `tearDown`: `translation.activate(settings.LANGUAGE_CODE)` — Django's own cleanup recommendation

2. **Three approaches evaluated and ranked**:

   | Rank | Approach | Risk | Effort |
   |---|---|---|---|
   | **1 (Recommended)** | Autouse `deactivate()` fixture in root conftest + `?lang=`/header for integration tests + `translation.override()` for unit tests | LOW | LOW |
   | 2 | `translation.override()` context manager wrapper + parametrize across languages | MEDIUM | MEDIUM-HIGH |
   | 3 | `deactivate_all()` baseline + `override_settings(LANGUAGE_CODE=en)` | HIGH | HIGH |

3. **Approach A (recommended)** is superior because:
   - A single fixture eliminates all 30+ leaks with zero changes to test logic
   - The `override()` vs. `?lang=`/header split aligns with Django's documentation
   - Incremental adoption: fixture first (immediate safety), then remove local fixtures, then remove redundant calls

4. **The `translation.override()` context manager** is superior to `translation.activate()` + manual `deactivate()` because it provides automatic rollback (even on exceptions), saves and restores the *previous* language (not just the setting default), and is the Django-recommended pattern.

5. **Critical insight**: In this project, since `LanguagePreMiddleware` always calls `translation.activate()`, tests that assert `translation.get_language()` after `client.get()` are valid — they verify the middleware's output. But the assertion must happen *within the test body*, before teardown runs the shared `deactivate()`.

---

## 7. Assumptions

1. **`LanguagePreMiddleware` is correct and should not change.** It always activates a language per request; the fix is in test infrastructure, not middleware logic.
2. **Russian (`ru`) is the production default** (matches `LANGUAGE_CODE = "ru"` in base.py and `LanguageLocale.RUSSIAN.value` in the middleware's fallback, line 74). The middleware hardcodes "ru" as the default, NOT `settings.LANGUAGE_CODE` — so changing `test.py`'s `LANGUAGE_CODE` to "en" affects only the pre-request fallback, not the middleware's resolution of requests with no language signals.
3. **English (`en`) is the msgid language** — `{% trans "Clear all filters" %}` renders "Clear all filters" when the active language is "en" (because the `en` locale's `msgstr` is empty per the i18n rule: "en may be empty (msgid is English)").
4. **The middleware's hardcoded "ru" default (line 74) is independent of `settings.LANGUAGE_CODE`** — confirmed by reading `language.py`: the fallback is `LanguageLocale.RUSSIAN.value`, a StrEnum constant, not `settings.LANGUAGE_CODE`.
5. **Tests asserting `translation.get_language()` after `client.get()`** (like `test_language_end_to_end.py` L118, 136, 147, 159, 191, 193) must do so within the test body — the autouse `deactivate()` fixture only runs in teardown, so these assertions are safe.
6. **pytest-xdist (`-n auto`) is used** — but intra-worker sequential execution means thread-local state still leaks between tests on the same worker. The autouse fixture is needed regardless of xdist.
7. **`.mo` files are compiled** in the test entrypoint (`compilemessages` runs before pytest in Docker) — so translated content is available for assertions. The `test_i18n_completeness.py::test_mo_compiled` gate enforces this.
8. **The bot test suite (`src/telegram_bot/tests/`) does not currently assert on translated UI text** — it's a Telegram bot, not a web UI. No language fixture changes are needed there.

---

## 8. Constraints

| # | Constraint | How satisfied |
|---|---|---|
| C1 | `LANGUAGE_CODE` change in `test.py` must not affect production settings | `test.py` is test-only; `base.py` unchanged. The middleware's "ru" default (hardcoded) is unaffected. |
| C2 | Autouse `deactivate()` fixture must not break tests that assert `translation.get_language()` after requests | The fixture runs in teardown (after all test assertions). Tests asserting `get_language()` do so in the test body. Verified by researcher. |
| C3 | Existing tests asserting on Russian text through `client.get()` without a language signal will break (after T1) | T7 explicitly identifies and updates these tests. The break is intentional — tests must be explicit about expected language. |
| C4 | `translation.activate()` before `client.get()` is a no-op for rendered content | T4 removes these calls; documentation (T6) warns against them. Verified by researcher Task-2 §3.1. |
| C5 | StrEnum for all language constants | `LanguageLocale` StrEnum used for parametrization. No bare string literals for language codes in new tests. |
| C6 | English-only code/comments/docstrings | All new code comments in English per project rule #1. |
| C7 | No `print()` statements | Use `logger` if needed (none expected in test infrastructure). |
| C8 | Tests run in Docker PostgreSQL (port 5433) | `make test`, `make test-all`, `make test-recreate` — no local `uv run pytest`. |
| C9 | Production code is king | The fix is test infrastructure only — no production code changes. Tests are updated to assert correct behavior, not distorted to match broken behavior. |
| C10 | i18n pipeline gate must pass | `test_i18n_completeness.py` (4 tests) and `test_i18n_pipeline.py` (5 tests) must remain green. No new msgids introduced. |

---

## 9. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Tests asserting on Russian text without explicit language signal break** after T1 sets default to "en". | High | Medium | T7 identifies and fixes all such tests. The break is intentional — tests must declare expected language. |
| R2 | **Thread-local "en" leak from `Accept-Language: en` tests** causes a subsequent test's `translation.get_language()` assertion to see "en". | Medium (currently latent) | High (intermittent failure) | T2 (autouse `deactivate()` fixture) eliminates the leak. Safe. |
| R3 | **Removing `translation.activate("ru")` from `test_context_processors.py`** breaks tests that call `header_context()` directly — the function reads `request.LANGUAGE_CODE` (fallback "ru" per context processor L24) but also calls `city.get_name(locale)` which uses the thread-local. | Low | Medium | T5 migrates these to `translation.override("ru")` context manager, which provides automatic cleanup and correct thread-local state for the direct function call. |
| R4 | **Agent confusion if documentation is incomplete** — agents might still use `translation.activate()` before `client.get()` after the standard is in place. | Medium | Medium | T6 documents the convention in root `conftest.py` and `rules.md`. The `_reset_translation_state` fixture name in `conftest.py` serves as a visible reminder. |
| R5 | **`test_saved_search_create.py::test_create_saved_search_with_filters_and_language`** asserts `ss.language == "ru"` — the middleware hardcodes "ru" as default (not `LANGUAGE_CODE`), so this test is safe after T1. But a future change to use `settings.LANGUAGE_CODE` as the default would break it. | Low | Low | Assumption §4 documents that the middleware uses `LanguageLocale.RUSSIAN.value`, not `settings.LANGUAGE_CODE`. |
| R6 | **xdist worker isolation gives false confidence** — tests pass with `-n auto` but fail without xdist (sequential, same thread, leaked state). | Low | Medium | T2 (autouse `deactivate()`) fixes this regardless of xdist. |
| R7 | **Tests using `translation.override()` restore the *previous* language, not `settings.LANGUAGE_CODE`** — this could differ from the old `translation.deactivate()` behavior (which restores to `settings.LANGUAGE_CODE`). | Low | Low | The shared `deactivate()` fixture (T2) handles the global reset. `translation.override()` is only used within test-local scopes (unit tests), so the restoration target doesn't matter globally. |

---

## 10. Open Questions

1. **Should the default test language remain "ru" or switch to "en"?** (Q1) — Researcher recommends "en" (matches msgid). The alternative ("ru") requires every English-assertion test to explicitly signal English. The "en" default means tests asserting on msgid strings work out-of-the-box, which is the least surprising behavior. **PO should confirm Q1=A.**

2. **Should `test.py` also set `LANGUAGE_CODE` via `override_settings` at session scope, or as a plain setting?** A plain setting change is simpler and sufficient. `override_settings` would add unnecessary complexity. **Assumed plain setting (A).**

3. **Should the bot test suite (`src/telegram_bot/tests/`) also get the autouse fixture?** The bot conftest at `src/telegram_bot/tests/conftest.py` is separate from the root `src/backend/conftest.py` (discovery hierarchy issue — bot tests live outside `src/backend/`). Currently no bot tests assert on translated UI text. **Assumed: no change needed; if bot UI tests are added later, a similar fixture should be added to the bot conftest.**

4. **Should the `translation.override()` + `translation.override("en")` pattern be used for ALL unit tests, or only those that need a specific locale?** Currently no unit tests use `translation.activate()` except `test_context_processors.py`. **Assumed: only where locale-specific rendering is needed (i.e., `test_context_processors.py` and any future template-rendering unit tests).**

---

## 11. Out of Scope

- **Production middleware logic** (`LanguagePreMiddleware`, `context_processors/language`, the translation system itself) — all correct, verified by `test_language_middleware.py` and `test_language_end_to_end.py`.
- **Locale `.po`/`.mo` extraction or compilation** — the i18n pipeline (`makemessages`/`compilemessages`) is working; `test_i18n_completeness.py` and `test_i18n_pipeline.py` enforce it.
- **DB-based i18n** (`get_lookup_name`, `get_city_name`, `get_category_name` with `name_i18n` fields) — these use locale parameters from the template context, not the thread-local translation system; tests already handle them via `?lang=` query params.
- **Bot test language handling** — bot tests don't assert on translated UI text currently; no changes needed.
- **Production settings** (`base.py`, `dev.py`) — `LANGUAGE_CODE` stays "ru" in production.
- **New language features** — only standardizing the existing 3 languages (ru, bs, en).
- **Template string changes** — no new translatable strings; no `.po`/`.mo` updates required (unless T1/T7 changes which test assertions run, which doesn't affect the catalogs).

---

## 12. Definition of Ready

This specification is ready for implementation planning when all of the following hold:

1. ✅ The problem is bounded to **test infrastructure** — no production code changes required (middleware, context processors, settings base — all correct).
2. ✅ Root causes are verified with file:line citations for every claim (Researcher Task-1).
3. ✅ Thread-local leakage is categorized with risk levels and affected files (Researcher Task-1 §3, §5).
4. ✅ The four PO decisions (Q1–Q4) have recommended defaults backed by Django documentation (Researcher Task-2 §1).
5. ✅ The preferred approach (Approach A) is ranked #1 with explicit rationale (Researcher Task-2 §5).
6. ✅ All 8 conceptual tasks have clear purpose, expected outcome, and dependencies.
7. ✅ Constraints (test-only changes, StrEnum, i18n gate, Docker test env) are documented.
8. ✅ Risks (especially the intentional test breakage from T1) have mitigations.
9. ✅ Out-of-scope items are explicit.
10. ✅ The test-impact analysis identifies which tests break (T7) and why.

### Implementation readiness checklist

- [ ] Q1=A confirmed: `test.py` sets `LANGUAGE_CODE = "en"`
- [ ] Q2=A confirmed: Integration tests use `Accept-Language` header standard
- [ ] Q3=A confirmed: Autouse `deactivate()` fixture in root `conftest.py`
- [ ] Q4=A confirmed: Split strategy (`override()` for unit, signals for integration)
- [ ] T2 implemented: autouse fixture added to `src/backend/conftest.py`
- [ ] T1 implemented: `LANGUAGE_CODE = "en"` in `test.py`
- [ ] T3 implemented: local cleanup fixtures removed
- [ ] T4 implemented: redundant `translation.activate("ru")` removed from integration tests
- [ ] T5 implemented: `translation.override()` in unit tests (test_context_processors.py)
- [ ] T7 implemented: all Russian-text assertion tests updated with explicit language signals
- [ ] T8 implemented: documentation updated in `rules.md`
- [ ] `make test` (fast gate) passes
- [ ] `test_i18n_completeness.py` and `test_i18n_pipeline.py` pass
- [ ] `test_language_middleware.py` and `test_language_end_to_end.py` pass

---

## 13. Affected-Artifact Index

| Artifact | Role | Change? |
|---|---|---|
| `src/backend/config/settings/test.py` | Test settings (LANGUAGE_CODE override) | **Yes** — add `LANGUAGE_CODE = "en"` |
| `src/backend/conftest.py` | Root test config (shared fixtures) | **Yes** — add autouse `_reset_translation_state` fixture + import |
| `src/backend/config/settings/base.py` | Production base settings | No |
| `src/backend/config/settings/dev.py` | Dev settings | No |
| `src/backend/apps/core/middleware/language.py` | `LanguagePreMiddleware` | No (correct, test-only fix) |
| `src/backend/apps/core/context_processors.py` | `language()` context processor | No |
| `src/backend/apps/core/enums.py` | `LanguageLocale` StrEnum | No (reference) |
| `src/backend/apps/core/tests/test_language_middleware.py` | Middleware unit tests | Remove local `deactivate()` (T3); keep `translation.activate()` for direct tests → migrate to `override()` |
| `src/backend/apps/core/tests/test_language_end_to_end.py` | E2E middleware tests | Remove `_locale_cleanup` autouse fixture (T3); keep assertions (safe within test body) |
| `src/backend/apps/core/tests/test_context_processors.py` | Unit tests calling functions directly | Migrate `translation.activate("ru")` → `translation.override("ru")` (T5); remove `_activate_russian` fixture (T3) |
| `src/backend/apps/ads/tests/test_catalog_filters.py` | Integration tests (filter UI) | No change needed — already uses `Accept-Language: en` and `?lang=en` for English assertions |
| `src/backend/apps/ads/tests/test_gallery_markup.py` | Integration tests (gallery) | No change needed — already uses `?lang=en` |
| `src/backend/apps/ads/tests/test_i18n_category_city.py` | i18n integration tests | Fix `test_detail_defaults_to_ru` (L101) — add `?lang=ru` to request after T1 |
| `src/backend/apps/ads/tests/test_auth_nav.py` | Integration tests (auth nav) | Remove 9 `translation.activate("ru")` (T4); add `?lang=ru` to requests asserting Russian text |
| `src/backend/apps/ads/tests/test_breadcrumbs_render.py` | Integration tests (breadcrumbs) | Remove 4 `translation.activate("ru")` (T4); add `?lang=ru` |
| `src/backend/apps/search/tests/test_preferred_city.py` | Integration tests (preferred city) | Remove 3 `translation.activate("ru")` (T4); add `?lang=ru` |
| `src/backend/apps/search/tests/test_preferred_city_readback.py` | Integration tests (preferred city) | Remove 5 `translation.activate("ru")` (T4); add `?lang=ru` |
| `src/backend/apps/search/tests/test_saved_search_create.py` | Integration tests (saved search) | No change — asserts model field `language`, middleware hardcodes "ru" default |
| `src/backend/apps/ads/tests/test_favorites.py` | Integration tests (favorites) | No change — asserts Russian strings with no language signal (after T1, these would get English) → **needs `?lang=ru`** (T7) |
| `src/backend/apps/ads/tests/test_favorites.py` (check) | | Verify Russian string assertions |
| `docs/99-agent/rules.md` | Project testing conventions | **Yes** — add i18n testing standard (T8) |
| `src/backend/locale/{ru,en,bs}/LC_MESSAGES/django.po` | Translation catalogs | No (no new msgids) |
| `src/telegram_bot/tests/conftest.py` | Bot test config | No (no UI text assertions in bot tests) |

---

## 14. Acceptance Criteria

| # | Given | When | Then |
|---|---|---|---|
| A1 | `test.py` with `LANGUAGE_CODE = "en"` | A test makes `client.get("/")` with no language signal | The middleware resolves to "ru" (hardcoded default, L74 of `language.py`), so Russian is still the rendered language for requests without signals. `settings.LANGUAGE_CODE` only affects the pre-request fallback (thread-local unset). |
| A2 | Any test that calls `translation.activate("ru")` and forgets cleanup | Test completes | Thread-local is "en" (the `deactivate()` restores `settings.LANGUAGE_CODE`), not "ru" — proving the cleanup fixture works. |
| A3 | `test_catalog_filters.py` with `Accept-Language: en` | Request renders | English msgid text ("Clear all filters", "Page navigation") appears in rendered output. |
| A4 | Root `conftest.py` with autouse fixture | Any test runs | `translation.deactivate()` is called in teardown — no thread-local leak between tests. |
| A5 | `test_language_end_to_end.py` after T3 | Test asserts `translation.get_language() == "en"` after `client.get("...?lang=en")` | Assertion passes (within test body, before teardown) — the middleware-set "en" is visible. |
| A6 | `test_i18n_category_city.py::test_detail_defaults_to_ru` after T1+T7 | Request goes to detail page with `?lang=ru` | "Транспорт" and "Тестград" appear in Russian output. |
| A7 | `make test-recreate` then `make test` | Full fast gate | All tests pass, including i18n tests. |
| A8 | `test_i18n_completeness.py` | Runs | All 4 guard tests pass (no new violations). |
| A9 | `test_i18n_pipeline.py` | Runs | All 5 tests pass. |
| A10 | `test_auth_nav.py` after T4 | Test asserts Russian strings | `?lang=ru` added to request, Russian text renders correctly. |

---

## 15. Implementation Order

| Step | Task | Rationale |
|---|---|---|
| 1 | T2 (autouse fixture in conftest) | Immediate safety — prevents all future leaks. No test breakage. |
| 2 | T5 (translation.override in unit tests) | Safe, isolated change. No test breakage. |
| 3 | T1 (LANGUAGE_CODE = "en" in test.py) | Triggers test breakage in T7-affected tests. Must be paired with T7. |
| 4 | T7 (update affected tests) | Fix tests that break after T1. Identifies all tests asserting Russian text without language signals. |
| 5 | T4 (remove redundant activate calls) | Replace `translation.activate("ru")` in integration tests with explicit `?lang=ru` on the request. |
| 6 | T3 (remove local cleanup fixtures) | Centralized fixture supersedes per-file fixtures. |
| 7 | T6 (document convention) | Add documentation to conftest.py comments and rules.md. |
| 8 | T8 (update rules.md) | Final documentation update. |
