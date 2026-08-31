---
id: i18n-definition-of-done-research
domain: agent
tags:
  - i18n
  - translation
  - definition-of-done
  - ci
  - pre-commit
  - research
related:
  - architecture
  - rules
  - references
  - i18n-translation-pipeline-gap-analysis
stale: true
stale_reason: Assessed pre-f661532; superseded by i18n-spec.md as the authoritative current description
---

> **Status — pre-implementation research (2026-08-23):** This report assesses the i18n state
> *before* commit `f661532`. Its findings (the §1.1 current-state table, §1.2 "What is broken",
> and the §9 bottom-line recommendations) described the gaps that `f661532` subsequently
> **implemented** — namely the `i18n` CI job, Python-side `gettext` usage, `.po` extraction
> completeness, the guard tests in `test_i18n_completeness.py`, and wrapping of the hardcoded
> template strings. As a result the §1.1 verdicts reading "CI has an i18n gate = No",
> "Python `gettext_lazy` usage = None", and "64 of 100 strings missing from `.po`" are
> **no longer true**. This note is retained for the Definition-of-Done checklist (§5) and the
> workflow recommendations (§6), which remain valid. For the authoritative, current
> implementation architecture see [`../01-spec/i18n-spec.md`](../01-spec/i18n-spec.md).

# Research Report: Multilingual i18n Definition of Done

**Date:** 2026-08-23  
**Project:** Mko Bazuna — Django 5.2 LTS, HTMX MPA, Docker, PostgreSQL 18  
**Languages:** `ru` (base/content), `bs`, `en`  
**Status:** Complete  
**Confidence:** HIGH — all findings verified against the actual codebase and official documentation.

---

## 0. Executive Summary

| Finding | Verdict | Confidence |
|---|---|---|
| The i18n **runtime pipeline** is wired up (compilemessages in Dockerfile + both entrypoints; Makefile targets exist; `.mo` compiled; `.po` msgstr filled) | ✅ Already done (the 2026-08-23 gap-analysis doc is **stale**) | HIGH |
| `.po` files are **complete** | ❌ False — the catalog has 38 `msgid` entries but templates define **100** unique `{% trans %}`/`{% translate %}` strings; **64 of those 100 have no matching `msgid`** (the remaining 36 are present; 2 msgids are `{% blocktrans %}`/obsolete entries) | HIGH |
| Hardcoded (un-wrapped) Russian strings exist | ❌ Yes — 7 visible labels + 5 inline-JS strings in `header_catalog.html` | HIGH |
| Django's built-in `makemessages --check` flag exists | ❌ **No** — it is a `django-extended-makemessages` feature, package NOT installed | HIGH |
| djlint H023 detects untranslated text | ❌ **No** — H023 = "Do not use entity references"; there is **no** built-in djlint rule for translatable text | HIGH |
| `.mo` files are committed to git | ❌ No — `.gitignore` ignores `*.mo` (correct: build artifact) | HIGH |
| Python-side `gettext_lazy` usage | ❌ None — 100 % of UI translation is via template `{% trans %}` tags | HIGH |
| An empty-msgstr gate already exists in tests | ✅ Yes — `test_i18n_pipeline.py::test_no_empty_msgstr` | HIGH |
| CI has an i18n gate | ❌ No — `ci.yml` has no i18n step | HIGH |
| Pre-commit hooks exist | ❌ No — no `.pre-commit-config.yaml` | HIGH |

**Bottom line:** The build/compile machinery is finished, but (a) the `.po` catalog is missing 64 strings, (b) 7 hardcoded Russian labels bypass gettext entirely, and (c) no automated gate enforces extraction-completeness or hardcoded-text detection. The single existing test (`test_no_empty_msgstr`) catches empty translations but NOT missing strings.

---

## 1. Codebase Verification: Actual i18n State

### 1.1 What already works (verified)

| Component | Location | Status |
|---|---|---|
| `USE_I18N = True`, `LANGUAGES` (ru/bs/en), `LOCALE_PATHS` | `config/settings/base.py:55-62` | ✅ |
| Custom language middleware (activates via `translation.activate()`) | `apps/core/middleware/language.py:128` | ✅ |
| `{% load i18n %}` in templates + `{% trans %}` / `{% blocktrans %}` usage | 24 templates | ✅ |
| `compilemessages` in **Dockerfile builder stage** | `docker/Dockerfile:78` | ✅ |
| `compile_messages()` in **entrypoint.sh** (web/bot, non-fatal fallback) | `docker/entrypoint.sh:70-87` | ✅ |
| `compilemessages` in **entrypoint-test.sh** (before pytest) | `docker/entrypoint-test.sh:37` | ✅ |
| `makemessages` + `compilemessages` **Makefile targets** | `Makefile:146-150` | ✅ |
| `.mo` files are **git-ignored** | `.gitignore:55` (`*.mo`) | ✅ |
| `LANGUAGES`, `name_i18n` JSONB, `get_name(locale)` for lookup/category/city data | settings + models | ✅ |

> **Note:** The file `docs/99-agent/i18n-translation-pipeline-gap-analysis.md` describes `compilemessages` as "absent from all entrypoints" and `.po` msgstr as "all empty." That description is **stale** — all three items above are already implemented and the `.po` files contain non-empty `msgstr` values (e.g. `ru`: `msgstr "Фото"`, `bs`: `msgstr "Foto"`, `en`: `msgstr "Photo"`). The gap-analysis doc should be updated or archived.

### 1.2 What is broken / incomplete (verified)

#### Gap A — 64 of 100 translatable strings are **not extracted** into `.po`

Running `makemessages` would add 64 new `msgid` entries. Verified by diffing unique `{% trans "..." %}` strings in templates (100) against `msgid` entries in `ru.po` (38). Of those 38 msgids, 36 match template strings and 2 are `{% blocktrans %}`/obsolete entries not captured by the `{% trans %}` regex:

| Missing from .po (sample) | Template |
|---|---|
| `Cabinet`, `My ads`, `Settings`, `Saved searches`, `Search history`, `Favorites` | `components/cabinet_nav.html`, `components/header_auth_entry.html` |
| `Login`, `Account`, `Account menu`, `Admin`, `Logout` | `components/header_auth_entry.html` |
| `Privacy Policy`, `Cookie settings` | `components/footer.html` |
| `Accept`, `Reject non-essential`, `Manage`, + 5 long cookie-consent strings | `components/consent_banner.html` |
| `My favorites`, `Login to save favorites` | `components/header_favorites_badge.html` |
| `Add to favorites`, `Remove from favorites` | `components/favorite_heart.html` |
| `Categories`, `Close`, `Preferred city`, `Expand` | `components/header_catalog.html` |
| `Min price (EUR)`, `Max price (EUR)` | `search/partials/save_search_modal.html`, `cabinet/saved_search_edit.html` |
| `Edit saved search`, `Save alert`, `Save search alert` | `cabinet/saved_search_edit.html`, save_search_modal |
| `On`, `Off`, `City:`, `Category:`, `Price:`, `Disable`, `Enable`, `Edit`, `Delete` | `cabinet/partials/saved_search_row.html` |
| `No favorites yet`, `No saved searches yet`, `No search history` | cabinet templates |
| `Open image` | `ads/detail.html` |

The `generate_po.py` script (`scripts/generate_po.py`) contains only 26 manually-curated `ENTRIES` — it is a **seed/bootstrap** helper, not a replacement for `makemessages`. The `.po` files were apparently hand-seeded with that subset and never re-extracted.

#### Gap B — **Hardcoded Russian strings** bypass `{% trans %}` entirely

These are in `components/header_catalog.html` (verified by reading lines 32-179):

| Line | Hardcoded Russian | Should be |
|---|---|---|
| 32 | `+ Подать объявление` | `{% trans "Submit an ad" %}` |
| 59 | `Вся страна` | `{% trans "Entire country" %}` |
| 79 | `Все категории` | `{% trans "All categories" %}` |
| 119 | `placeholder="Поиск по объявлениям..."` | `placeholder="{% trans "Search ads..." %}"` |
| 130 | `Поиск` (hidden submit button) | `{% trans "Search" %}` |
| 146 | `Категории` (mobile panel header) | `{% trans "Categories" %}` |

Additionally, **inline JavaScript** in the same template (lines 217-220) contains hardcoded Russian section headers that are assembled as DOM text — these cannot be extracted by `makemessages` at all:

| Line(s) | Hardcoded Russian JS string |
|---|---|
| 213 | `Показать все результаты` ("Show all results") |
| 217 | `Города` ("Cities") |
| 218 | `Категории` ("Categories") |
| 219 | `Популярные запросы` ("Popular searches") |
| 220 | `История` ("History") |

These JS strings are built via `sectionHeader('Города')` inside a `<script>` block — `makemessages` does not scan `.js` inside `.html` for the `django` domain (only `--domain djangojs` would, and it is not configured). The DoD must require these to be exposed as server-rendered template variables (e.g. `data-i18n-*` attributes) rather than inline string literals.

#### Gap C — No completeness or extraction-freshness gate exists

| Gate | Present? | Evidence |
|---|---|---|
| `.po` ↔ `.py`/`.html` extraction freshness (`makemessages --check`) | ❌ No | `django-extended-makemessages` not installed; `ci.yml` has no i18n step |
| Empty `msgstr` detection | ✅ Yes (partial) | `test_i18n_pipeline.py::test_no_empty_msgstr` — **but only for strings already in `.po`**; does not detect missing strings |
| Hardcoded-visible-text detection (missing `{% trans %}`) | ❌ No | No such djlint rule exists; no custom linter |
| `compilemessages` succeeds | ✅ Yes | `entrypoint-test.sh:37` runs it; `test_i18n_pipeline.py::test_mo_files_exist` checks |
| Pre-commit hooks | ❌ No | No `.pre-commit-config.yaml` anywhere in repo |

### 1.3 Existing i18n test (already implemented)

`src/backend/apps/ads/tests/test_i18n_pipeline.py` contains three unit tests (tag `pytest.mark.unit`):

1. `test_po_files_exist_for_all_languages` — `.po` exists for every code in `settings.LANGUAGES`
2. `test_no_empty_msgstr` — parses `.po`, asserts no non-header `msgid` has an empty `msgstr`
3. `test_mo_files_exist` — `.mo` exists next to each `.po`

Plus Part B tests the `component_tag` template filter.

**Limitation:** These tests verify *translation quality* (non-empty msgstr, `.mo` existence) but do **not** verify *extraction completeness* (that every `{% trans %}` in templates has a corresponding `msgid`). A developer can add a new `{% trans "Foo" %}` tag, forget to run `makemessages`, and all three tests still pass.

---

## 2. Task A — Industry-Standard i18n Definition of Done Patterns

### 2.1 Standard "gates" that prevent merging untranslated strings

Surveyed sources (TranslateBot CI guide, django-extended-makemessages, mondeja/pre-commit-po-hooks, revel-backend ADR-0011, openlibrary PR #8900):

**Gate 1 — Extraction freshness (are all `{% trans %}` strings in `.po`?)**

The standard approach mirrors `makemigrations --check`:

```bash
# Standard Django (no --check flag on makemessages):
python manage.py makemessages -l ru -l bs -l en --no-location --no-obsolete
git diff --exit-code -- locale/
```

Django's `makemessages` always updates `POT-Creation-Date`, producing a diff even when strings are unchanged. The standard workaround (confirmed by Stack Overflow answer [4] and the Django ticket referenced there) is to strip the header line before diffing:

```bash
# Strip POT-Creation-Date to avoid spurious diffs (gettext reflows differently across versions too)
python manage.py makemessages -l ru -l bs -l en --no-location --no-obsolete
git diff --ignore-matching-lines='POT-Creation-Date' --exit-code -- locale/
```

**Better approach** (revel-backend `check_translations.py` [source 1]): re-run `makemessages`, snapshot the `.po` files in memory, restore them, then compare `msgid` *sets* (not raw text). This is version-independent — immune to gettext reordering or POT-Creation-Date churn. The comparison detects:
- **Missing keys** — code has `{% trans %}` strings not in the catalog (FAIL)
- **Stale keys** — catalog has msgids no longer in code (WARN, not FAIL — prune with `--no-obsolete`)

**Gate 2 — Translation completeness (are all `msgstr` non-empty and not fuzzy?)**

Two independent mechanisms:
- `msgfmt --check` / `msgfmt --statistics` (GNU gettext) — reports untranslated/fuzzy counts per file.
- `django-extended-makemessages --no-untranslated` — exits non-zero if any `msgstr ""` exists.
- `pre-commit-po-hooks` (third-party pre-commit hooks): `untranslated-messages`, `fuzzy-messages`, `obsolete-messages`, `standard-metadata`.
- Custom Python parser (as the project already does in `test_i18n_pipeline.py`).

**Gate 3 — Compilation succeeds (`compilemessages` exit code)**

`compilemessages` (wrapping `msgfmt`) exits non-zero if:
- A `.po` file has a syntax error (unclosed quote, bad escaping).
- A `python-format` / `python-brace-format` flagged entry has mismatched format specifiers between `msgid` and `msgstr` (e.g., `msgid "10% discount"` / `msgstr "Rabatt"` — format spec count mismatch — verified in Django ticket #11240 and #27221).

**It does NOT exit non-zero on empty `msgstr`** — an empty msgstr compiles fine and simply causes `gettext()` to return the `msgid` unchanged at runtime. → A separate completeness gate (Gate 2) is required.

### 2.2 Common integration points

| Layer | Mechanism | Notes |
|---|---|---|
| **Pre-commit** | `pre-commit` local hook running `makemessages` + `git diff --exit-code` or `pre-commit-po-hooks` | Catches at commit time; requires gettext installed in dev env |
| **CI** | Dedicated `i18n` job in GitHub Actions, parallel to `lint`/`typecheck` | Runs `makemessages --check` (or script-based set comparison) + `compilemessages` + empty-msgstr scan |
| **pytest** | Unit test (SimpleTestCase) scanning `.po` + templates as text | Already used by this project (`test_i18n_pipeline.py`); no gettext binary needed in test runner since .mo compiled by entrypoint |
| **PR review checklist** | Human gate: "ran `make makemessages`, filled msgstr for bs+en" | Complements automated gates; catches intent-level issues |

### 2.3 "Translation debt" tracking

Sources: TranslateBot [3], revel-backend ADR-0011 [6]. The emerging pattern is **not** to track "translation debt" as a separate backlog item, but to make translation non-blocking-yet-visible within the same PR cycle:

1. **At PR time:** CI fails if a new `{% trans %}` string is missing from `.po` (extraction freshness gate). The developer must run `make makemessages`, add the `msgid`, and provide `msgstr` for `bs` + `en` (and `ru` if msgid isn't already Russian).
2. **At merge time:** All gates green.
3. **No deferred debt:** Because the extraction check is automated, there is no window where a string ships untranslated — the developer is forced to supply translations during development, not after.

---

## 3. Task B — Django `makemessages --check`: Correction & Clarification

> **The task brief refers to "Django's built-in `--check` flag on `makemessages`. This does NOT exist.**

This is the single most important correction in this report.

### 3.1 What Django's built-in `makemessages` actually supports (Django 5.2)

Source: Django source code (`django/core/management/commands/makemessages.py`, main branch) [2] and Django 5.2 docs [3, 7].

The `add_arguments()` method of `makemessages` defines these options — **none** of which is `--check`:

`--locale`/`-l`, `--exclude`/`-x`, `--domain`/`-d`, `--all`/`-a`, `--extension`/`-e`, `--ignore`/`-i`, `--no-default-ignore`, `--no-wrap`, `--no-location`, `--add-location`, `--no-obsolete`, `--keep-pot`, `--symlinks`, `--verbosity`, `--settings`, etc.

### 3.2 Where `--check` actually comes from: `django-extended-makemessages`

Source: PyPI page [1, 2] and GitHub README (searched).

`django-extended-makemessages` is a **third-party** package by Michał Pokusiński that monkey-patches `makemessages` into a new command `extendedmakemessages`. Its `--check` option:

> "Allows you to verify that all translations are properly extracted and included in the `.po` files. It works similarly to `makemigrations --check`, but for translations. If any `.po` file would be added or changed, the command will fail. In more verbose mode, it will also display the unified diff of the changes that would be made."

It also provides:
- `--no-untranslated` — exits non-zero if any `msgstr ""` exists.
- `--show-untranslated` — counts untranslated messages.
- `--dry-run` — restores `.po` to original state after running.
- `--compile` — runs `compilemessages` after extraction.

**This package is NOT installed** — `uv.lock` contains zero references to `django-extended-makemessages`, and `pyproject.toml` `[project.dependencies]` does not list it.

### 3.3 What Django's standard `makemessages` does NOT do (gaps a `--check` would need to fill)

| Capability | Django built-in | `extendedmakemessages --check` |
|---|---|---|
| Detect new `{% trans %}` strings not yet in `.po` | ❌ No | ✅ Yes (re-extracts, diffs) |
| Detect empty `msgstr` | ❌ No (compilemessages doesn't either) | ✅ Yes (`--no-untranslated`) |
| Exit non-zero on `.po` staleness | ❌ No | ✅ Yes |
| Detect fuzzy entries | ❌ No | ✅ Yes (`--no-untranslated` covers fuzzy) |
| Auto-compile `.mo` | ❌ No | ✅ Yes (`--compile`) |

### 3.4 Recommendation for this project

Two options, neither requires installing a new dependency:

**Option A (no new dependency) — script-based freshness + msgstr check:**
```bash
# Extraction-freshness gate (run in CI / pre-commit):
# Strip POT-Creation-Date to avoid version-churn noise, diff msgid sets.
python manage.py makemessages -l ru -l bs -l en --no-location --no-obsolete
git diff --ignore-matching-lines=POT-Creation-Date --exit-code -- locale/
```
Plus reuse the existing `test_no_empty_msgstr` test for the empty-msgstr gate.

**Option B (new dev dependency) — `django-extended-makemessages`:**
Add `uv add --dev django-extended-makemessages`, then:
```bash
python manage.py extendedmakemessages \
    -l ru -l bs -l en --check --no-untranslated --keep-header
```
The `--keep-header` flag is critical — it prevents `POT-Creation-Date` churn (the exact problem described in the Stack Overflow answer [4] and the revel-backend ADR [6]).

**Recommended:** Option B is cleaner and is the most common community recommendation, but it adds a dependency and changes the extraction command from `makemessages` to `extendedmakemessages` (a cognitive load for contributors). Option A uses zero new dependencies and the existing Makefile target. The report recommends **Option A** for the short term (no new deps, fits existing `make makemessages` target) and notes Option B as an enhancement if the team wants stricter single-command gates.

### 3.5 Important caveat on `--check` for `makemessages`: timestamp noise

Django's `makemessages` writes `POT-Creation-Date: 2026-08-23 00:00+0200` into every `.po` header. Running it twice on unchanged source still produces a diff (the timestamp changes). Any `--check`-style gate MUST suppress this with:
- `--ignore-matching-lines=POT-Creation-Date` in `git diff`, OR
- `--keep-header` (only in `extendedmakemessages`), OR
- A programmatic set-comparison (as `check_translations.py` [source 1] does — compares `msgid` sets, not raw text).

---

## 4. Task C — Hardcoded String Detection in Django Templates

### 4.1 djlint H023 is NOT about translatable text (correction)

> **The task brief describes H023 as "Translatable text". This is incorrect.**

Verified from three sources:
- djlint docs [1]: `H023 | Do not use entity references.`
- djlint `rules.yaml` source [2]:
  ```yaml
  - rule:
      name: H023
      message: Do not use entity references.
      flags: re.I
      patterns:
      - "&(?!(lt|gt|amp|quot|nbsp|ensp|emsp|thinsp|shy))[#0-9a-z]{,30};"
  ```
- Changelog [3]: "Added rule H023 to find entity references."

H023 flags HTML entity references like `&mdash;`, `&hellip;` (it allows only `<`, `>`, `&`, `"`, `nbsp`, `ensp`, `emsp`, `thinsp`, `shy`). The project's `pyproject.toml` correctly ignores H023 for entity-reference noise in `ad_list.html`, `breadcrumb.html`, etc.

### 4.2 There is NO built-in djlint rule for untranslated/hardcoded text

A thorough survey of the djlint rule reference [1] (rules H001–H029, T001–T030, C001–C0xx, P0xx) finds **zero** rule that detects visible template text not wrapped in `{% trans %}`. djlint is an HTML/Django-template *structure and style* linter; it does not perform gettext-awareness.

The project already uses a **custom djlint rule** (`H901` in `.djlint_rules.yaml`) for multi-line `{# ... #}` comments — demonstrating the mechanism exists to add custom rules.

### 4.3 Approaches for hardcoded-string detection

| Approach | How it works | Pros | Cons | Recommendation |
|---|---|---|---|---|
| **Custom djlint rule** | Regex like `>[^{<]*[А-Яа-яЁё][^<{]*<` matching Cyrillic text between tags | Integrates with `make lint-templates` | High false-positive risk (SVG text, code, aria-labels that legitimately contain text) | ⚠️ Harder — use only for Cyrillic-specific detection |
| **Custom Python AST/regex linter** (pytest SimpleTestCase) | Parse `.html` text, find visible-text nodes outside `{% trans %}` | Full control, zero deps, runs in `make test` | Must write a template-text extractor; same false-positive risk | ✅ **Recommended** — matches existing `test_templates.py` pattern |
| **`django-template-check`** package | Uses Django's own lexer to parse templates | 100 % accurate (Django parser) | New dep; focused on syntax errors, not i18n | Consider for syntax validation |
| **`manage.py check`** | Django system checks | No extra deps | Does NOT parse templates | ❌ Not useful for this |

### 4.4 False-positive risk analysis (per task brief)

A hardcoded-string detector MUST handle:
1. **SVG content** — `<path>` SVG icons have no visible text, but `<text>` elements in an SVG logo would false-positive. Mitigation: skip SVG subtrees.
2. **`aria-label` attributes** — these ARE translatable (e.g. `{% trans "Close" %}` appears in `aria-label`). The detector should NOT flag text already inside `{% trans %}` or `{% blocktrans %}`.
3. **`placeholder` attributes** — `placeholder="Поиск по объявлениям..."` in `header_catalog.html:119` IS a missing-translatable bug. The detector SHOULD flag these.
4. **`<script>` / `<style>` blocks** — text here is not user-visible. Mitigation: skip `<script>`/`<style>` content.
5. **Code examples / placeholders** — e.g. `{{ query }}` output is data, not a hardcoded label. Mitigation: skip content of `{{ }}` interpolations.

### 4.5 Practical recommendation: Cyrillic-only detector

Since the base language is Russian and the known hardcoded strings are all Cyrillic, a targeted detector is more precise than a generic "English-looking text outside trans tags" heuristic (which has massive FP on English UI text). A rule like:

> "Flag any Cyrillic text (а–я, А–Я, ё, Ё) that appears directly in template HTML **outside** of `{% trans %}` / `{% blocktrans %}` / `{{ variable }}` / `<script>` / `placeholder="..."`-already-wrapped contexts."

This catches exactly the `header_catalog.html` bugs (`Подать объявление`, `Вся страна`, `Все категории`, `Категории`, `Поиск`) while ignoring legitimate English `{% trans %}` strings.

---

## 5. Task D — Concrete Definition of Done for Multilingual Features

A feature is **i18n-complete** when ALL of the following hold. Items 1–7 are automatable (CI/pre-commit/test); item 8 is a human checklist step.

### DoD Checklist — Multilingual

| # | Gate | How to verify (automated) | Who enforces |
|---|---|---|---|
| **D1** | Every new **visible** UI string is wrapped in `{% trans "..." %}` or `{% blocktrans %}` | Custom linter rule (Cyrillic-text-outside-trans) or `django-template-check` | CI + pre-commit + pytest |
| **D2** | Every new `{% trans %}` string is **extracted** into all 3 `.po` files | `makemessages` re-extraction + `msgid`-set comparison (no missing keys) | CI + pre-commit |
| **D3** | Every `msgstr` for `bs` and `en` is **non-empty** (for `ru`, `msgstr == msgid` is acceptable since `msgid` is Russian) | Existing `test_no_empty_msgstr` test (extend to skip `ru` msgid-equals-msgstr) | pytest |
| **D4** | No `fuzzy` flag remains on new/updated entries | Extend `test_no_empty_msgstr` → `test_no_fuzzy_or_empty_msgstr` | pytest |
| **D5** | `compilemessages` **succeeds** (no `python-format` mismatch errors) | `compilemessages` exit code 0 (already in entrypoint + test) | CI + pytest |
| **D6** | Inline-JS text strings are passed as **server-side template variables** (not inline literals) | Manual review + linter rule (no Cyrillic in `<script>` blocks) | Code review + linter |
| **D7** | JSON-based lookup data (`name_i18n`) populated for all 3 languages | Model validation / seed data check (e.g., `Category.name_i18n` has `ru`/`bs`/`en` keys) | Model + seed tests |
| **D8** | `.po` files committed; `.mo` files **not** committed (git-ignored) | `.gitignore` has `*.mo`; no `.mo` in `git ls-files` | CI (git diff) + `.gitignore` |

> **Nuance on D3 for `ru`:** The base language's `.po` has `msgid` in Russian. By gettext convention, an empty `msgstr` in the base-language catalog means "use the msgid as-is" — which renders correctly since `msgid` IS Russian. So for `ru`, `msgstr ""` is actually *correct* and should NOT be flagged. The existing test (`test_no_empty_msgstr`) currently flags ALL empty msgstr including Russian base language — this should be relaxed: **only `bs` and `en` require non-empty `msgstr`**; `ru` can have `msgstr == msgid` or even empty.

### DoD Checklist — Human (PR review)

| # | Step | Notes |
|---|---|---|
| **H1** | Developer ran `make makemessages` and reviewed the diff to confirm all new `{% trans %}` strings were picked up | |
| **H2** | Developer provided `msgstr` for `bs` and `en` (and verified `ru` renders the Russian msgid) | |
| **H3** | Developer did NOT commit `.mo` files (they are git-ignored) | |
| **H4** | Inline JS strings were refactored to server-side data attributes if they contain visible text | |
| **H5** | `name_i18n` / per-language ad fields populated if new lookup data was introduced | |

---

## 6. Task E — Integration with the Existing Workflow

### 6.1 Existing toolchain map

| Concern | File / Command | Current state |
|---|---|---|
| `makemessages` | `Makefile:146` | ✅ Exists: `makemessages -l ru -l bs -l en --no-location` |
| `compilemessages` | `Makefile:149` | ✅ Exists |
| Template lint | `Makefile:113` → `djlint` | ✅ Runs `djlint src/backend/templates/` |
| Python lint | `Makefile:107` → `ruff check` | ✅ |
| Typecheck | `Makefile:110` → `basedpyright` | ✅ |
| Tests | `Makefile:98` → Docker pytest | ✅ |
| Pre-commit | (none) | ❌ No `.pre-commit-config.yaml` |
| CI | `.github/workflows/ci.yml` | ✅ 5 jobs (build, test, lint, typecheck, lint-templates) — **no i18n job** |
| i18n test | `test_i18n_pipeline.py` | ✅ 3 tests (existential check) |

### 6.2 Recommended integration points

#### 6.2.1 Makefile — new `i18n-check` target

```makefile
# ====================== i18n ======================
i18n-check:
	@# 1. Re-extract and fail if .po files are stale (extraction completeness)
	@echo "Checking translation extraction freshness..."
	@docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location --no-obsolete
	@git diff --ignore-matching-lines=POT-Creation-Date --exit-code -- src/backend/locale/ || { \
		echo "ERROR: .po files are out of date. Run 'make makemessages' and commit the updated .po files."; \
		echo "Hint: new {% trans %} strings were found that are missing from the .po catalogs."; \
		exit 1; \
	}
	@# 2. Verify compilemessages succeeds (format-specifier integrity)
	@echo "Checking compilemessages..."
	@docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages
	@echo "✓ i18n checks passed"
```

> **Note:** The freshness check uses `git diff --ignore-matching-lines=POT-Creation-Date` to suppress the timestamp churn that Django's `makemessages` always introduces (verified via Stack Overflow [4] and the Django source). The existing `test_no_empty_msgstr` test covers the empty-msgstr gate (D3); no Makefile change needed for that.

#### 6.2.2 CI (`.github/workflows/ci.yml`) — add `i18n` job

```yaml
  i18n:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --frozen --no-install-project --group dev
        working-directory: src/backend
      - name: Install gettext
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends gettext
      - name: Check extraction freshness
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
          PYTHONPATH: ${{ github.workspace }}/src:${{ github.workspace }}/src/backend
        run: |
          uv run python manage.py makemessages -l ru -l bs -l en --no-location --no-obsolete
          git diff --ignore-matching-lines=POT-Creation-Date --exit-code -- src/backend/locale/ || {
            echo "::error::.po files are out of date — new {% trans %} strings not extracted"
            exit 1
          }
      - name: Compile messages
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
          PYTHONPATH: ${{ github.workspace }}/src:${{ github.workspace }}/src/backend
        run: uv run python manage.py compilemessages
```

This mirrors the TranslateBot CI pattern [3] and the revel-backend ADR [6]: install `gettext`, re-extract, diff with timestamp suppression.

#### 6.2.3 Pre-commit — `.pre-commit-config.yaml` (new file)

The project has **no** pre-commit setup. A minimal config covering i18n + existing linters:

```yaml
repos:
  - repo: https://github.com/codespell-project/codespell
    rev: v2.4.0
    hooks:
      - id: codespell
  - repo: local
    hooks:
      - id: i18n-freshness
        name: i18n (makemessages freshness)
        entry: bash -c 'uv run --directory src/backend python manage.py makemessages -l ru -l bs -l en --no-location --no-obsolete && git diff --ignore-matching-lines=POT-Creation-Date --exit-code -- src/backend/locale/'
        language: system
        files: \.(html|py)$
        pass_filenames: false
        require_serial: true
      - id: makemessages
        name: i18n (extract)
        entry: uv run --directory src/backend python manage.py makemessages -l ru -l bs -l en --no-location --no-obsolete
        language: system
        files: \.(html|py)$
        pass_filenames: false
        require_serial: true
```

> **Pre-commit is optional / enhancement.** The CI job + pytest gate already enforce DoD. Pre-commit shifts the failure left to commit time (better DX). The `require_serial: true` prevents concurrent `makemessages` runs corrupting `.po` files.

#### 6.2.4 `test_no_empty_msgstr` — strengthen the existing test

Current test (`test_i18n_pipeline.py:98`) flags ALL empty `msgstr`. Per D3 nuance, it should:
- For `ru`: allow `msgstr == msgid` (Russian msgid means translation is the string itself).
- For `bs` / `en`: require non-empty `msgstr`.
- Also detect `fuzzy` flags (currently not checked).

```python
def test_no_empty_or_fuzzy_msgstr(self) -> None:
    """Every non-header msgid has a non-empty, non-fuzzy msgstr —
    except ru where msgstr may equal msgid (base language)."""
    for po_path in _po_files():
        lang = po_path.parent.parent.name
        text = po_path.read_text(encoding="utf-8")
        for msgid, msgstr, is_fuzzy in _parse_po_with_fuzzy(text):
            if not msgid:
                continue
            if lang == "ru" and msgstr == msgid:
                continue  # base language: msgid IS the translation
            assert msgstr.strip(), f"{po_path.name}: empty msgstr for {msgid!r}"
            assert not is_fuzzy, f"{po_path.name}: fuzzy flag on {msgid!r}"
```

#### 6.2.5 Extraction-completeness test (new) — closes the existing gap

The current `test_i18n_pipeline.py` does NOT verify that every template `{% trans %}` string has a `msgid` in `.po`. Add:

```python
class TestExtractionCompleteness(SimpleTestCase):
    """Every {% trans %} string in templates must appear as a msgid in every .po."""

    def test_all_trans_strings_extracted(self) -> None:
        template_strings = _extract_trans_msgids_from_templates()  # regex scan .html
        for po_path in _po_files():
            po_msgids = {
                msgid for msgid, _, _ in _parse_po_with_fuzzy(po_path.read_text())
            }
            missing = template_strings - po_msgids
            assert not missing, f"{po_path}: not extracted: {missing}"
```

#### 6.2.6 Hardcoded-text linter (new) — closes Gap B

Add a `SimpleTestCase` test (or djlint custom rule) that flags Cyrillic text in visible template positions outside `{% trans %}`. See §4.3 and §4.5 for the false-positive handling strategy.

### 6.3 What NOT to change (constraints)

- Do **not** add `compilemessages` to the Makefile `test` target directly — it already runs in `entrypoint-test.sh:37`. Adding it again would be redundant and would require `gettext` on the developer's host (currently gettext is only inside Docker). The `.mo` files are compiled inside the test container by the entrypoint.
- Do **not** commit `.mo` files. `.gitignore` already ignores `*.mo`. The existing `.mo` files on disk are ephemeral build artifacts (confirmed: `git ls-files` shows zero tracked `.mo` files).
- Do **not** use `makemessages --check` (non-existent in Django). Use the `git diff` approach or add `django-extended-makemessages` if the team accepts a new dev dependency.
- Do **not** flag `ru` empty `msgstr` as a failure — the base language may legitimately leave `msgstr ""` (Django falls back to `msgid`).

---

## 7. Constraints, False-Positive Risks, and Gotchas

| # | Gotcha | Detail | Mitigation |
|---|---|---|---|
| G1 | **`POT-Creation-Date` churn** | `makemessages` updates this header on every run, even when strings are unchanged | Strip with `git diff --ignore-matching-lines=POT-Creation-Date` or use `--keep-header` (extended-makemessages) |
| G2 | **gettext version drift** | Different gettext versions reorder `.po` lines and reflow differently | Compare `msgid` **sets**, not raw diff text (revel-backend pattern [1]) |
| G3 | **`--no-obsolete` only works if ≥1 translatable string exists** | Django ticket: `makemessages --no-obsolete` is a no-op if the source files have zero gettext calls (Stack Overflow [4]) | N/A for this project — templates always have ≥1 `{% trans %}` |
| G4 | **Empty `msgstr` compiles fine** | `compilemessages` does NOT fail on empty msgstr — gettext returns the `msgid` | Need a separate `msgstr` completeness gate (test or `--no-untranslated`) |
| G5 | **`fuzzy` entries are skipped by `compilemessages`** | A `fuzzy`-flagged msgstr is NOT compiled into `.mo` — gettext silently falls back to msgid | Detect `fuzzy` in the completeness gate |
| G6 | **Inline JS strings can't be extracted** | `makemessages -d django` ignores `<script>` JS content | Refactor visible JS strings to `data-*` attributes populated server-side (D6) |
| G7 | **`placeholder="..."` attributes** | These are translatable but easy to miss in a linter | Include `placeholder` in the hardcoded-text scan |
| G8 | **`aria-label` with inline Cyrillic** | Visible to screen readers — must be `{% trans %}` | The Cyrillic detector flags these correctly |
| G9 | **`.mo` must exist at runtime** | In Docker, bind-mounts override image files — `compilemessages` must run in entrypoint (✅ already done) | No action needed; entrypoint.sh:75, entrypoint-test.sh:37 |
| G10 | **`ru` base-language msgstr** | For Russian, `msgid` is already the Russian string — `msgstr ""` is valid | Relax the empty-msgstr test for `ru`; only enforce non-empty for `bs`/`en` |
| G11 | **`{% trans %}` vs `{% translate %}`** | Both are valid (aliases registered together in Django [7, 8]); `trans` is not deprecated | Allow both; do NOT flag `trans` as deprecated (djlint issue #770 [5] is a feature request, not a deprecation) |
| G12 | **`blocktrans` with variables** | `{% blocktrans %}No results for "{{ query }}"{% endblocktrans %}` generates a complex `msgid` with `%(query)s` | The set-comparison gate handles this correctly (extracts msgid, compares to catalog) |

---

## 8. Sources (with confidence levels)

### High confidence — official documentation
- [7] Django 5.2 translation docs — `makemessages`/`compilemessages` workflow, `msgstr` semantics, `compilemessages` only fails on format-specifier mismatches. **Confidence: HIGH.**
- [2] Django source `makemessages.py` (main branch) — confirms the exact `add_arguments` list; `--check` is **not** among them. **Confidence: HIGH.**
- [8] Django source `django/templatetags/i18n.py` — confirms `trans` and `translate` are aliased tags. **Confidence: HIGH.**

### High confidence — third-party tooling docs
- [1] `django-extended-makemessages` PyPI + README — documents `--check`, `--no-untranslated`, `--keep-header`, `--compile`. **Confidence: HIGH.**
- [3] TranslateBot CI guide — `check_translations` command + CI workflow pattern (install gettext, run check, exit 1 on failure). **Confidence: HIGH.**
- [4] Stack Overflow: "Detecting changes to Django translations (PO) files in CI" — `git diff --ignore-matching-lines=POT-Creation-Date` pattern. **Confidence: HIGH.**
- [1b] djlint docs — H023 rule table. **Confidence: HIGH.**
- [2b] djlint `rules.yaml` source — H023 regex pattern (entity references). **Confidence: HIGH.**
- [6] revel-backend ADR-0011 — static QA gate comparing msgid sets, restoring .po snapshot. **Confidence: HIGH.**
- [5] mondeja/pre-commit-po-hooks — `untranslated-messages`, `fuzzy-messages` pre-commit hooks. **Confidence: HIGH.**
- [9] openlibrary PR #8900 — pre-commit hook running POT extraction on `.py`/`.html` changes, using `symmetric_difference`. **Confidence: HIGH.**

### Verified against the actual codebase (HIGH confidence)
- `Makefile:146-150` — `makemessages` and `compilemessages` targets exist.
- `docker/Dockerfile:78` — `compilemessages` in builder stage.
- `docker/entrypoint.sh:70-87` — `compile_messages()` function + call.
- `docker/entrypoint-test.sh:37` — `compilemessages` before pytest.
- `.gitignore:55` — `*.mo` ignored; `git ls-files` confirms zero tracked `.mo` files.
- `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — 38 `msgid` entries (verified by counting). Of those, 36 match template strings; 2 are `{% blocktrans %}`/obsolete entries not captured by the `{% trans %}` regex.
- 100 unique `{% trans %} "..."}` strings across 24 templates (verified by programmatic scan); **64** are missing from all `.po` files (36 present + 2 non-`{% trans %}` msgids = 38 total catalog entries).
- `header_catalog.html:32,59,79,119,130,146` — hardcoded Cyrillic labels (verified by reading source).
- `header_catalog.html:213-220` — 5 hardcoded Cyrillic inline-JS strings (verified by reading source).
- `test_i18n_pipeline.py` — existing 3-test gate (verified by reading source).
- `.github/workflows/ci.yml` — 5 jobs, no i18n job (verified by reading source).
- `pyproject.toml:208` — `djlint` is a dev dependency; `[tool.djlint]` ignores `H023` (entity references).
- `pyproject.toml` `[project.dependencies]` — `django-extended-makemessages` NOT listed.
- `scripts/generate_po.py` — manual 26-entry `ENTRIES` list (bootstrap helper, not `makemessages`).
- `config/settings/base.py:55-62` — `LANGUAGE_CODE`, `USE_I18N`, `LANGUAGES`, `LOCALE_PATHS`.

### Medium confidence
- [5b] The djlint issue #770 feature request confirming there is no built-in translatable-text rule — the maintainer's suggested workaround (custom rule) implies none exists. **Confidence: MEDIUM** (inferred from absence + maintainer response).

---

## 9. Consolidated Recommendations

1. **Re-extract `.po` files immediately.** Run `make makemessages` to pull in the 64 missing strings, then translate `msgstr` for `bs`/`en`. This is the single highest-impact fix — 64 strings currently render as English msgids in Bosnian/English mode.

2. **Wrap all hardcoded Cyrillic in `header_catalog.html`** (lines 32, 59, 79, 119, 130, 146) in `{% trans %}`, and refactor the 5 inline-JS Cyrillic strings (lines 213, 217-220) to `data-i18n-*` attributes populated server-side.

3. **Add the `i18n` job to `ci.yml`** (§6.2.2) and the `i18n-check` Makefile target (§6.2.1). Wire the emptiness gate into the existing `test_i18n_pipeline.py` (§6.2.4).

4. **Add an extraction-completeness test** (§6.2.5) to `test_i18n_pipeline.py` — this closes the gap where new `{% trans %}` strings pass all tests but are never extracted.

5. **Add a hardcoded-text detector** (§6.2.6 / §4.5) as a `SimpleTestCase` test — targets Cyrillic text outside `{% trans %}` in visible/template-HTML positions, skipping SVG, `<script>`, and `<style>` subtrees.

6. **Strengthen the existing `test_no_empty_msgstr`** to also check for `fuzzy` flags and to exempt `ru` (base language).

7. **Do NOT install `django-extended-makemessages`** initially — the `git diff --ignore-matching-lines` approach works with the existing `makemessages` target and no new dependencies. Revisit if the team wants `--check`/`--compile` convenience.

8. **Do NOT commit `.mo` files** — `.gitignore` already excludes them; they are compiled by the Docker image builder + entrypoints (§1.1, verified).

9. **Add the i18n DoD checklist** (§5) to `docs/99-agent/rules.md` and the `.kilo/rules/project.md` / `.kilo/rules/commands.md` "cheat sheet" as requested by `Decision_07.md`.

10. **Archive or rewrite** `docs/99-agent/i18n-translation-pipeline-gap-analysis.md` and `.ai/plans/30_filter-sort-i18n_plan.md` §4 — both describe a pre-2026-08-22 state where the pipeline was unwired; the pipeline is now wired (verified at `git commit dbdd974`, 2026-08-23). Their gap analysis should be updated to reflect: **stale `.po` catalog (64 missing strings) + hardcoded text (7 labels + 5 JS strings)** as the true north star.
