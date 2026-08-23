# 08 — Multilingual Development Definition of Done

## 1. Purpose

Convert Decision_07 into a development specification: translation is part of the Definition of Done, hardcoded strings are audited and fixed, automated translation checking is added to CI, and i18n reminders are added to developer cheatsheets.

## 2. Context (Verified Facts)

### 2.1 Languages

Three languages are declared via `LanguageLocale` enum (`src/backend/apps/core/enums.py:184`):

| Enum member | Value | Role |
|---|---|---|
| `RU` | `"ru"` | Main / primary language |
| `EN` | `"en"` | Secondary |
| `BS` | `"bs"` | Secondary |

Decision_07 states: **"ru — главный, en и bs — вторичные"** (ru is main, en and bs are secondary).

### 2.2 Runtime Pipeline (Already Operational)

The i18n pipeline is functional:

- **Middleware** (`apps/core/middleware/language.py`): `LanguagePreMiddleware` reads a `lang` query parameter or cookie, validates it against `LanguageLocale`, sets `request.LANGUAGE_CODE`, and activates the translation via `translation.activate()`. Falls back to `"ru"` if invalid or absent.
- **Context processor** (`apps/core/context_processors.py:21`): exposes `LANGUAGE_CODE` and `LANGUAGES` to all templates.
- **Django gettext infrastructure**: templates use `{% load i18n %}` and `{% trans %}` / `{{ _("...") }}`. Python code uses `gettext_lazy`.
- **Locale directories**: `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.{po,mo}`.
- **Compile at build**: `docker/Dockerfile:78` runs `python manage.py compilemessages`.
- **Compile at runtime**: `docker/entrypoint.sh:73-87` and `docker/entrypoint-test.sh:37` run `compilemessages`.
- **Makefile targets**: `makemessages` and `compilemessages` at `Makefile:146-150`.
- **Auto-translation service** (`src/backend/apps/core/services/translation_service.py`): uses `deep-translator` (Google Translate API) to bootstrap .po msgstr values. This is a helper tool, not part of the runtime request path.

### 2.3 Current Catalog State (Gap)

The .po catalog is incomplete:

- **39 msgid entries** across all 3 locales (38 translatable strings + 1 header entry).
- The 38 non-header entries have **empty `msgstr`** values — translations have not been authored.
- All 3 locales (ru, en, bs) have identical 39 msgids (same strings extracted, none translated).
- **62+ unique strings** in templates are NOT in .po files — they are either:
  - Hardcoded visible text not wrapped in `{% trans %}` (will produce new msgids after extraction), OR
  - Strings in templates that lack `{% load i18n %}` entirely.
- `.mo` files are compiled on disk but are **`.gitignore`'d** (line 55 of .gitignore), so they are build-time artifacts.

### 2.4 Existing Automated Tests (`test_i18n_pipeline.py`)

Five tests exist in `src/backend/apps/ads/tests/test_i18n_pipeline.py`, all marked `@pytest.mark.unit`:

**Part A — i18n pipeline (3 tests):**
1. `test_po_files_exist_for_all_languages` — checks .po exists for every configured language.
2. `test_no_empty_msgstr` — fails if any non-header .po entry has empty `msgstr`.
3. `test_mo_files_exist` — checks corresponding `.mo` file exists for each `.po`.

**Part B — component_tag filter (2 tests):**
4. `test_component_tag_renders_feature_name` — checks `component_tag` renders localized name.
5. `test_component_tag_includes_feature_id` — checks `data-feature-id` attribute.

**Key implementation note**: These tests use a **custom `_parse_po_entries` parser** (lines 31-73), NOT the `polib` library. `polib` is **not** declared as a dependency in `pyproject.toml`.

**These tests do NOT check:**
- Extraction completeness (whether all `{% trans %}` strings are in .po).
- Hardcoded visible text in templates.
- Whether msgstr values are actually translated (not just non-empty).

### 2.5 CI Environment

- `.github/workflows/ci.yml` has **5 jobs**: `build`, `test`, `lint`, `typecheck`, `lint-templates`.
- **No dedicated i18n job.** Translation completeness is not enforced in CI.
- `make lint-templates` runs `djlint` only (no translation-aware lint rule).
- Test markers (from `pyproject.toml:163-172`): `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group`. **No `i18n` marker** — completeness tests use the `unit` marker.
- The `seed` marker gates nightly tests (~300s+); `make test` skips these via `PYTEST_SKIP_MARKERS=seed`.

### 2.6 Template Linting (djlint)

- djlint v1.44+ is configured in `pyproject.toml:225-227` with `profile = "django"`.
- Built-in rules `D018, H019, H021, H023, H030` are ignored.
- Custom rule `H901` (multi-line `{# ... #}` comment detection) is enforced via `djlint_custom_rules.py`.
- **djlint cannot detect hardcoded visible text** — it is a style/syntax linter, not a translation-completeness checker.

### 2.7 Django `makemessages` Capabilities

- Django's `makemessages` has **no `--check` flag** (verified for Django 5.2).
- `polib` is **not** a project dependency. The existing test uses a custom parser instead.

### 2.8 Database-Based i18n (Alternative Mechanism)

`components/feature_tag.html` already has `{% load i18n %}` and uses a **database-based i18n mechanism**: the `get_lookup_name` template filter (`src/backend/apps/lookup_tags/`) reads from a `LookupItem.name_i18n` JSON field keyed by language code (`{"ru": "...", "en": "..."}`). This is a separate i18n path from gettext and is **already fully handled** — not in scope for this spec.

### 2.9 Test Fixtures

From `src/backend/conftest.py`:

- `seller` → `User(telegram_id=900000001, chat_id=900000001)`
- `user` → `User(telegram_id=900000002, chat_id=900000002)`
- `category` → `Category(name="Транспорт", slug="transport")`
- `city` → `City(country_code="ME", name="Тестград", region="Central", slug="test-grad")`

## 3. Hardcoded String Inventory (Audit Results)

### 3.1 Templates Already Loading i18n But With Remaining Hardcoded Text

#### 3.1.1 `components/header_catalog.html` (partial i18n)

Already has `{% load i18n %}` (line 8). Already wraps some strings in `{% trans %}` (lines 17, 46, 99, 147, 166). **6 hardcoded visible Russian strings + 5 inline JS strings remain**:

| Line | Current Text | Proposed msgid | Proposed msgstr (ru) |
|---|---|---|---|
| 32 | `+ Подать объявление` | `"Submit an ad"` | `"Подать объявление"` |
| 59 | `Вся страна` | `"Entire country"` | `"Вся страна"` |
| 79 | `Все категории` | `"All categories"` | `"Все категории"` |
| 119 | `placeholder="Поиск по объявлениям..."` | `"Search ads..."` | `"Поиск по объявлениям..."` |
| 130 | `Поиск` (hidden submit button) | `"Search"` | `"Поиск"` |
| 146 | `Категории` (mobile panel header) | `"Categories"` | `"Категории"` |

**Inline JS strings (lines 213, 217-220)** — dynamically rendered into autocomplete dropdown:

| Line | Current Text | Proposed msgid |
|---|---|---|
| 213 | `Показать все результаты` | `"Show all results"` |
| 217 | `Города` | `"Cities"` |
| 218 | `Категории` | `"Categories"` |
| 219 | `Популярные запросы` | `"Popular queries"` |
| 220 | `История` | `"History"` |

These JS strings must be passed as pre-translated template variables from the view context, or injected via Django template syntax inside the JS block (e.g., `var labelCities = "{% trans 'Cities' %}";`).

#### 3.1.2 `components/header.html` (partial i18n)

Already has `{% load i18n %}` (line 2). **5 hardcoded English visible strings**:

| Line | Current Text | Proposed msgid |
|---|---|---|
| 11 | `Cabinet` | `"Cabinet"` |
| 12 | `Dashboard` | `"Dashboard"` |
| 14 | `Admin` | `"Admin"` |
| 18 | `Logout` | `"Logout"` |
| 21 | `Login` | `"Login"` |

#### 3.1.3 `components/consent_banner.html` (partial i18n)

Already has `{% load i18n %}` (line 3). Already wraps some descriptive text in `{% trans %}` (lines 14-16). **3 hardcoded checkbox labels remain**:

| Line | Current Text | Proposed msgid |
|---|---|---|
| 27 | `Essential` (checkbox label) | `"Essential"` |
| 30 | `Analytics` (checkbox label) | `"Analytics"` |
| 33 | `Preferences` (checkbox label) | `"Preferences"` |

Note: `value` attributes (`"accepted"`, `"declined"`, `"1.0"`) are machine values, NOT user-visible — should NOT be wrapped in `{% trans %}`.

### 3.2 Templates Missing i18n Entirely (12 templates)

These templates lack `{% load i18n %}` and need it added plus all visible strings wrapped in `{% trans %}`:

| Template | Visible Text Type | Scope Question |
|---|---|---|
| `components/breadcrumb.html` | `Главная`, `Результаты поиска:` (hardcoded Russian) | Public-facing — **must translate** |
| `components/feature_tag.html` | Uses DB-based i18n via `get_lookup_name` | Already handled — **not in scope** |
| `components/badges/pro_badge.html` | `Pro` (visible), `aria-label="Pro seller"` | Badge label + aria — review |
| `components/badges/trusted_badge.html` | `Trusted` (visible), `aria-label="Trusted seller"` | Badge label + aria — review |
| `components/badges/verified_badge.html` | `Verified` (visible), `aria-label="Verified seller"` | Badge label + aria — review |
| `users/login_issue.html` | `Login`, `Login to Mko Bazuna`, `Tap the button...`, etc. | Public-facing — **must translate** |
| `ads/dashboard.html` | `Your Ads`, `Views`, `Contacts`, `Published`, `Edit`, `Archive`, etc. | Seller-facing — **must translate** |
| `ads/edit.html` | `Edit Ad`, `Title`, `Description`, `Price`, `Save Changes`, etc. | Seller-facing — **must translate** |
| `analytics/moderation_dashboard.html` | `Moderation Statistics`, `Pending Review Queue`, etc. | Staff-only — **PO decision** |
| `analytics/seller_dashboard.html` | `Your Trust Profile`, `Total Views (30d)`, etc. | Seller-facing — **must translate** |
| `admin/moderation/queue.html` | `Moderation Queue`, `All`, `High`, `Medium`, `Low` | Staff-only admin — **PO decision** |
| `admin/moderation/review.html` | `Moderation Actions`, `Approve`, `Reject`, `Ban User` | Staff-only admin — **PO decision** |

### 3.3 Python-Side Hardcoded Strings

#### 3.3.1 `apps/core/context_processors.py:46`

```python
preferred_city_display = "Вся страна"
```

This hardcoded Russian string is passed to templates as `preferred_city_display` and rendered in `header_catalog.html` line 48 (`<span data-preferred-city-label>{{ preferred_city_display }}</span>`). Must be changed to:

```python
from django.utils.translation import gettext as _
preferred_city_display = _("Entire country")
```

(`gettext` for runtime context processors, not `gettext_lazy`.)

#### 3.3.2 `apps/core/enums.py:133-136`

`TimeRange.choices()` returns hardcoded English labels that flow into `dashboard.html` line 62 (`{{ label }}`):

| Enum member | Current label | Proposed msgid |
|---|---|---|
| `ALL_TIME` | `"All Time"` | `"All Time"` |
| `THIRTY_DAYS` | `"30 Days"` | `"30 Days"` |
| `SEVEN_DAYS` | `"7 Days"` | `"7 Days"` |

These must use `gettext_lazy` so the labels become translatable.

### 3.4 Tests Asserting on Hardcoded Strings (To Update)

The following test files assert on the **current Russian text** that will move into `{% trans %}` blocks. After wrapping, the rendered output will still show Russian text if the ru `msgstr` is populated correctly — but these tests must explicitly set the test language to be robust:

| File | Lines | Current assertion |
|---|---|---|
| `test_auth_nav.py` | 81, 92 | `"Подать объявление" in content` |
| `test_breadcrumbs_render.py` | 65 | `"Главная" in nav` |
| `test_preferred_city.py` | 139, 147, 180 | `"Вся страна" in content` |
| `test_context_processors.py` | 72, 110 | `"Вся страна"` |

## 4. Definition of Done (Multilingual)

A feature/ticket is **complete** when ALL of the following are true:

### 4.1 String Extraction (Mandatory)

1. All user-visible strings in templates are wrapped in `{% trans %}` or `{% blocktrans %}`.
2. All user-visible strings in Python code use `gettext` / `gettext_lazy` (not hardcoded literals).
3. Every `msgid` referenced by `{% trans %}` or `{{ _("...") }}` in templates and Python code has a corresponding entry in the committed `.po` files for all 3 locales.
4. Every `msgid` in the `.po` files has a **non-empty `msgstr`** for the `ru` locale (the primary language). `en` msgstr may be empty (msgids are English). `bs` msgstr must be non-empty.

### 4.2 Translation Completeness (Mandatory)

1. The `ru` `.po` file has **0 untranslated** entries (verified by automated check).
2. The `bs` `.po` file has **0 untranslated** entries (verified by automated check).
3. The `en` `.po` file follows Django convention: `msgstr` mirrors `msgid` (can be empty or identical).
4. `python manage.py compilemessages` succeeds with no errors.

### 4.3 Automated Checking (Mandatory — CI Gate)

An automated check must verify:

1. Hardcoded visible text in templates (strings not wrapped in `{% trans %}`) — except for known-OK cases (JS, machine-value attributes, structural HTML).
2. Extraction completeness — every `{% trans %}` / `{{ _("...") }}` msgid exists in all `.po` files.
3. Empty `msgstr` values for `ru` and `bs` locales.
4. `.mo` compilation succeeded.

The check runs in CI as part of the fast gate — it must NOT be a nightly/seed test.

### 4.4 Test Updates (Mandatory)

1. All tests that assert on translated strings explicitly set the desired language via `translation.activate("ru")`.
2. All tests pass under the fast gate (`make test`).

### 4.5 Documentation (Mandatory)

1. A cheatsheet entry for i18n DoD is added to `.kilo/rules/commands.md` and `.kilo/rules/project.md`.
2. The stale doc `docs/99-agent/i18n-translation-pipeline-gap-analysis.md` is updated to reflect the current operational state.

## 5. Automated Checking System (Specification)

### 5.1 Approach

**Test-based approach using a `.po` parser** (selected per research in `docs/99-agent/translation-completeness-check-research.md`). The existing `test_i18n_pipeline.py` already demonstrates a custom parser approach (`_parse_po_entries`). The new tests should follow the same pattern for consistency.

#### Why not other approaches:

- **Django `makemessages --check`**: Does not exist (verified for Django 5.2).
- **`django-extended-makemessages`**: Not a project dependency; adds a new dependency.
- **djlint custom rule**: Cannot reliably detect hardcoded visible text (distinguishes visible text from attribute values, script content, structural elements — high false-positive rate).
- **`polib`**: Pure-Python library for reading/writing .po files. Not currently a dependency. The existing test uses a custom parser. **PO decision required** (see Q4 below): use `polib` (add dependency) or reuse the existing custom parser pattern.

### 5.2 Implementation Requirements

The automated check must be implemented as **pytest tests** in a new file:

**File**: `src/backend/apps/ads/tests/test_i18n_completeness.py`

**Tests required:**

| Test | Description | Pass condition |
|---|---|---|
| `test_no_hardcoded_visible_text` | Scan all templates for visible text not wrapped in `{% trans %}` | No hardcoded visible text found (excluding known-OK cases) |
| `test_extraction_completeness` | Verify every `{% trans %}` msgid in templates/Python has a `.po` entry | No missing msgids in any locale |
| `test_no_empty_msgstr` | Reuse existing pattern from `test_i18n_pipeline.py` | ru and bs have 0 empty msgstr |
| `test_mo_compiled` | Check `.mo` files exist | `.mo` files exist for all 3 locales |

**Marker**: `@pytest.mark.unit` (runs in fast gate, no database needed). Same pattern as existing `test_i18n_pipeline.py`.

**Known-OK exclusions for hardcoded text detection:**
- Text inside `{# ... #}` comments.
- Text inside `<script>` / `<style>` blocks (JS string literals must be addressed separately).
- HTML tag names, attribute names, CSS class names.
- `value` / `name` attributes (machine values, not user-visible).
- `aria-label`, `role` attributes that are already English (standard WAI-ARIA).
- Brand names (`Mko Bazuna`, `Mko Bazuna Admin`).
- Currency codes (`EUR`, `RSD`, `BAM`).
- The `feature_tag.html` template (uses database-based i18n, not gettext).

### 5.3 CI Integration

**Option A — Dedicated i18n job** (recommended):

```yaml
  i18n:
    name: i18n Translation Completeness
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-extras
      - run: uv run pytest src/backend/apps/ads/tests/test_i18n_completeness.py --create-db
```

**Option B — Extend existing `lint` job**: Add the completeness tests to the existing `lint` job in CI.

## 6. Open Questions for Product Owner

### Q1: Admin and analytics template scope
Four templates that lack i18n are **staff-only or internal-facing**:

- `admin/moderation/queue.html` — Django admin custom template, moderation queue
- `admin/moderation/review.html` — Django admin custom template, ad review detail
- `analytics/moderation_dashboard.html` — moderation analytics dashboard
- `analytics/seller_dashboard.html` — seller trust dashboard

Should these be included in the i18n DoD, or excluded as internal tools? (Badge components `pro_badge`, `trusted_badge`, `verified_badge` are seller-facing and should likely be included.)

### Q2: Legal page translation scope
`src/backend/templates/privacy.html` is a static legal page in English with no i18n. Should it:
- **(A)** Be wrapped in `{% trans %}` and translated (ru/bs) as part of i18n DoD?
- **(B)** Remain English-only (legal disclaimer in original English)?
- **(C)** Be excluded from the DoD scope?

**Risk**: Legal content translated by machine (deep-translator) without certification could have compliance implications.

### Q3: Bot interface i18n scope
Decision_07 says "веб-сайт" (web site). The **Telegram bot** (`src/telegram_bot/`) sends messages entirely in Russian with no i18n infrastructure. Should the i18n Definition of Done extend to bot message templates?

### Q4: .po parser library
Should the new `test_i18n_completeness.py` use:
- **(A)** `polib` — add as a dev dependency (`uv add --dev polib`), cleaner API?
- **(B)** The existing custom `_parse_po_entries` parser pattern (from `test_i18n_pipeline.py`) — no new dependency?

### Q5: en msgstr convention
Django convention is that `msgid` is in English and `msgstr` for `en` is often left empty. Should we:
- **(A)** Leave `en` msgstr empty (Django default)
- **(B)** Populate `en` msgstr with a copy of msgid (explicit)?

### Q6: Inline JS string handling
`header_catalog.html` has 5 inline JavaScript strings (lines 213, 217-220) that are dynamically injected into the autocomplete dropdown. The options are:
- **(A)** Pass pre-translated strings from the view as context variables, then reference them in JS.
- **(B)** Use Django template syntax inside the JS block (e.g., `var labelCities = "{% trans 'Cities' %}"`).
- **(C)** Mark these as out-of-scope for i18n.

**Recommendation**: Option (A) — pass translated labels as a JSON context variable from the view.

### Q7: CI job placement
Should the i18n completeness tests run as:
- **(A)** A dedicated `i18n` CI job (cleaner, parallelizable)
- **(B)** Part of the existing `lint` or `test` job (simpler, fewer jobs)

### Q8: Auto-translation process
The `translation_service.py` (deep-translator → Google Translate) can bootstrap msgstr values. Should:
- **(A)** Auto-translation be run once to populate ru and bs msgstr, then human-reviewed?
- **(B)** ru msgstr be hand-authored (Russian is the main language, should be accurate), and bs msgstr use auto-translation?
- **(C)** Both ru and bs use auto-translation as a first pass, then human review?

## 7. Assumptions

1. **English msgids**: `msgid` values are in English (Django convention). Russian msgstr provides the UI text.
2. **ru is primary**: ru .po must have complete, non-empty msgstr. en .po may have empty msgstr. bs .po must have non-empty msgstr.
3. **Bot out of scope**: The i18n DoD applies to the web site (templates + Python context processors + enums). The Telegram bot remains Russian-only for this spec.
4. **Auto-translation is bootstrap**: `translation_service.py` and `deep-translator` are tools for initial .po population, not runtime dependencies.
5. **`country_code="ME"` test fixture**: The `city` fixture uses Montenegro. This is test data and does not affect i18n DoD.
6. **`.mo` files are build artifacts**: `.mo` files are `.gitignore`'d and compiled at Docker build / container entrypoint. CI must compile them before running tests.
7. **Fast gate coverage**: i18n completeness tests must pass in `make test` (~300s), not in `make test-all` only.
8. **Database-based i18n is separate**: `feature_tag.html` uses `LookupItem.name_i18n` JSON field via `get_lookup_name` filter — this is a different i18n mechanism and is already handled. Not in scope for gettext DoD.
9. **Badge aria-labels**: `aria-label="Pro seller"` etc. in badge templates are English and standards-compliant. Whether they need translation is a PO decision, but they are non-visible (screen readers only).

## 8. Implementation Tasks

### Task 1: Audit and Fix Hardcoded Template Strings
- **Scope**: Templates in §3.1 and §3.2
- **Action**: Wrap every user-visible string in `{% trans %}` or `{% blocktrans %}`. Add `{% load i18n %}` where missing.
- **Deliverables**:
  - `components/header_catalog.html` — 6 visible + 5 JS strings
  - `components/header.html` — 5 strings
  - `components/consent_banner.html` — 3 strings
  - `components/breadcrumb.html` — 2 strings + add `{% load i18n %}`
  - `components/badges/{pro,trusted,verified}_badge.html` — visible label + aria-label (pending Q1)
  - `users/login_issue.html` — full audit + wrap + add `{% load i18n %}`
  - `ads/dashboard.html` — full audit + wrap + add `{% load i18n %}`
  - `ads/edit.html` — full audit + wrap + add `{% load i18n %}`
  - `analytics/seller_dashboard.html` — full audit + wrap + add `{% load i18n %}`
  - `analytics/moderation_dashboard.html` — full audit (pending Q1 — admin scope)
  - `admin/moderation/queue.html` — full audit (pending Q1 — admin scope)
  - `admin/moderation/review.html` — full audit (pending Q1 — admin scope)
  - `privacy.html` — pending Q2
- **Dependencies**: Must complete before extraction.

### Task 2: Audit and Fix Python-Side Hardcoded Strings
- **Files**:
  - `apps/core/context_processors.py:46` — `"Вся страна"` → `gettext("Entire country")`
  - `apps/core/enums.py:133-136` — `TimeRange.choices()` labels → `gettext_lazy`
- **Action**: Import `gettext` / `gettext_lazy`, wrap all hardcoded user-facing literals.

### Task 3: Extract Messages and Populate .po Files
- **Action**: Run `python manage.py makemessages -l ru -l en -l bs` to refresh all .po files with newly-extracted strings.
- **Action**: Run `translation_service.py` to auto-populate ru and bs msgstr (per Q8 answer).
- **Action**: Hand-review and correct ru msgstr (main language accuracy).
- **Action**: Run `python manage.py compilemessages` to generate .mo files.

### Task 4: Implement Automated Completeness Tests
- **File**: `src/backend/apps/ads/tests/test_i18n_completeness.py`
- **Tests**: 4 test functions per §5.2 (pending Q4 for polib vs. custom parser).
- **Marker**: `@pytest.mark.unit` (runs in fast gate).
- **Note**: Can reuse `_parse_po_entries` from `test_i18n_pipeline.py` or create a shared helper.

### Task 5: Add i18n Tests to CI
- **File**: `.github/workflows/ci.yml`
- **Action**: Add i18n job per §5.3 (Option A recommended, pending Q7).
- **OR**: Add `test_i18n_completeness.py` to existing `lint` or `test` job.

### Task 6: Update Existing Tests Asserting on Hardcoded Strings
- **Files**: `test_auth_nav.py`, `test_breadcrumbs_render.py`, `test_preferred_city.py`, `test_context_processors.py`
- **Action**: Add explicit `translation.activate("ru")` in test setup. Assert on translated output.

### Task 7: Update Stale Documentation
- **File**: `docs/99-agent/i18n-translation-pipeline-gap-analysis.md`
- **Action**: Update to reflect current operational pipeline (§2.2) and new completeness checks.

### Task 8: Add Cheatsheet Entries to Developer Rules
- **Files**: `.kilo/rules/commands.md`, `.kilo/rules/project.md`
- **Action**: Add i18n DoD reminder with checklist and test file location.

## 9. Verification Criteria

The spec is successfully implemented when:

1. **`make test`** passes (fast gate, ~300s) including new `test_i18n_completeness.py` tests.
2. **`make lint`** passes (ruff check + format) with no i18n regressions.
3. **`make lint-templates`** passes (djlint) with H901 enforced.
4. **CI i18n job** (or lint job) passes on a clean main branch.
5. **Manual spot-check**: Loading the site with `?lang=ru`, `?lang=en`, `?lang=bs` renders all public-facing visible text in the correct language (no Russian fallbacks in en/bs mode).
6. **`.po` files**: ru and bs have 0 untranslated entries; en follows convention.
7. **No hardcoded visible strings** remain in public-facing templates (per `test_no_hardcoded_visible_text`).

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Extraction completeness check is complex (requires running `makemessages` or parsing templates for `{% trans %}` usage) | Start with msgstr emptiness + no-hardcoded-text checks; extraction completeness can be a follow-up test |
| Inline JS strings break translation | Pass translated labels as context variables from view (recommended approach in Q6) |
| Existing tests break when strings move to `{% trans %}` | Update tests per Task 7 with explicit `translation.activate("ru")` |
| False positives in hardcoded-text detection (badge templates, admin templates) | Curate known-OK exclusion list; scope detection to public-facing templates only |
| `polib` dependency adds build weight | Default to reusing existing `_parse_po_entries` pattern (no new dependency) unless PO prefers `polib` |
| Admin templates (staff-only) may not need translation | Scope the DoD to public + seller-facing templates; admin templates gated by Q1 |

## 11. References

- **Source decision**: `.ai/problems/Decision_07.md`
- **Spec format reference**: `.ai/problems/07_filter-sort-ui_consolidation_spec.md`
- **Research (completeness checking)**: `docs/99-agent/translation-completeness-check-research.md`
- **Research (DoD process)**: `docs/99-agent/i18n-definition-of-done-research.md`
- **Stale analysis**: `docs/99-agent/i18n-translation-pipeline-gap-analysis.md`
- **Enum**: `src/backend/apps/core/enums.py:184` (`LanguageLocale`)
- **TimeRange enum**: `src/backend/apps/core/enums.py:125-137`
- **Middleware**: `src/backend/apps/core/middleware/language.py` (`LanguagePreMiddleware`)
- **Context processor**: `src/backend/apps/core/context_processors.py` (hardcoded Russian at line 46)
- **Translation service**: `src/backend/apps/core/services/translation_service.py` (uses `deep-translator`)
- **Existing tests**: `src/backend/apps/ads/tests/test_i18n_pipeline.py` (custom parser, 5 tests, `@pytest.mark.unit`)
- **Test fixtures**: `src/backend/conftest.py`
- **CI**: `.github/workflows/ci.yml` (5 jobs: build, test, lint, typecheck, lint-templates)
- **Makefile**: `Makefile:146-150` (makemessages/compilemessages targets)
- **Dockerfile**: `docker/Dockerfile:78` (compilemessages at build)
- **Entrypoints**: `docker/entrypoint.sh:73-87`, `docker/entrypoint-test.sh:37`
- **pyproject.toml**: pytest markers, djlint config, dependency list
- **.gitignore**: `.mo` files are gitignored (line 55)
- **Database-based i18n**: `components/feature_tag.html` uses `get_lookup_name` filter (already handled, not in scope)

---

*Status: Pending PO answers to Q1–Q8 before implementation begins. Recommended defaults: Q1=exclude admin templates (staff-only), Q2=C (exclude from DoD), Q3=bot out of scope, Q4=B (reuse custom parser, no new dep), Q5=A (empty msgstr for en), Q6=A (context variables), Q7=A (dedicated CI job), Q8=C (auto-translation first pass then human review).*