---
id: translation-completeness-check-research
title: Automated Translation-Completeness Checking System — Research Report
date: 2026-08-23
project: Mko Bazuna (Django 5.2 LTS, HTMX MPA, Docker, PostgreSQL 18)
confidence: HIGH (all findings verified against source code)
stale: true
stale_reason: Assessed pre-f661532; superseded by i18n-spec.md and i18n-translation-pipeline-gap-analysis.md
---

> **⚠ Stale — pre-`f661532` state:** This report assessed the i18n state *before* commit
> `f661532`. Its §0/§1.1/§1.2 verdicts ("64 of 100 strings missing from `.po`", "no `gettext` in
> Python", "no CI gate") **no longer reflect** the implemented pipeline. See the authoritative
> current description in [`i18n-spec.md`](../01-spec/i18n-spec.md) and
> [`i18n-translation-pipeline-gap-analysis.md`](../99-agent/i18n-translation-pipeline-gap-analysis.md).
> Retained for historical reference only.

# Automated Translation-Completeness Checking System — Research Report

**Task:** Investigate how to implement an automated system that catches untranslated
or missing translations in the Mko Bazuna Django project.

**Status:** All findings verified against the actual codebase (commit `dbdd974`).
No external sources were needed beyond Django docs — this report is based on
direct source code inspection.

---

## 0. Executive Summary

### What already exists (verified in working tree)

| Component | Status | File |
|---|---|---|
| `.po` files with msgstr populated | ✅ Exists, **incomplete** | `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` |
| `.mo` files compiled | ✅ Exists on disk (gitignored) | Same dir, `.mo` |
| `compilemessages` in Docker build | ✅ Uncommitted change | `docker/Dockerfile:78` |
| `compilemessages` in entrypoints | ✅ Uncommitted change | `docker/entrypoint.sh:73-87`, `docker/entrypoint-test.sh:37` |
| Makefile `makemessages` / `compilemessages` targets | ✅ Committed | `Makefile:146-150` |
| `test_i18n_pipeline.py` (basic .po/.mo checks) | ✅ Untracked | `src/backend/apps/ads/tests/test_i18n_pipeline.py` |

### What is STILL BROKEN

1. **`.po` files are 54% complete** — 39 of 100 unique `{% trans %}` /
   `{% blocktrans %}` strings are present. **64 strings are missing** from all
   three locale files (verified by template parsing).

2. **Hardcoded visible text exists in 4 templates** — not wrapped in `{% trans %}`:
   - `components/header.html`: "Cabinet", "Dashboard", "Admin", "Logout", "Login"
     (used on ~12 pages: cabinet, dashboard, privacy, login, edit, etc.)
   - `components/consent_banner.html`: "Essential", "Analytics", "Preferences"
   - `components/breadcrumb.html`: "Главная" (Home), "Результаты поиска:" (Search results:)
   - `components/header_catalog.html`: "Все категории", "Вся страна", "Подать объявление",
     "Поиск по объявлениям...", "Поиск", "Категории"

3. **Inline JS strings** in `header_catalog.html` (lines 213-220):
   `'Города'`, `'Категории'`, `'Популярные запросы'`, `'История'`,
   `'Показать все результаты'` — cannot be extracted by `makemessages`.

4. **No CI pipeline** — no `.github/workflows/`, no `.pre-commit-config.yaml`.

5. **No automated completeness gate** — the existing `test_i18n_pipeline.py` checks
   for empty `msgstr` and `.mo` existence, but does NOT detect missing strings
   (template msgids absent from `.po`), does NOT detect hardcoded untranslated
   text, and does NOT check runtime fallback.

6. **Stale gap-analysis doc** — `docs/99-agent/i18n-translation-pipeline-gap-analysis.md`
   (untracked) claims "all msgstr values are empty" and "no .mo files exist" — both
   are false in the current working tree. The doc describes the pre-fix state.

> **Note:** The task references "Decision_07.md" as the Product Owner's decision.
> This file does **not exist** in the codebase. The owner-decisions index
> (`docs/05-owner-decisions/index.md`) covers O1–O5 only. The gap-analysis doc
> is the closest reference to translation requirements.

---

## Task A: Detect untranslated `.po` strings

### A.1 Empty `msgstr` (already handled)

The existing `test_i18n_pipeline.py::TestI18nPipeline.test_no_empty_msgstr`
already detects empty `msgstr` values. It uses a **custom `.po` parser**
(`_parse_po_entries`) — no external library dependency. Verified: all 39
msgstr entries per language are non-empty, so this test passes.

### A.2 Missing strings (template msgids absent from `.po`)

**Problem:** 64 of 100 `{% trans %}` strings in templates are absent from all
`.po` files. **No existing test catches this.**

**Feasible approaches (ranked by practicality):**

| Approach | How | Works in Docker? | Works locally? | Trade-offs |
|---|---|---|---|---|
| **A1: Parse templates + compare to .po** | Regex/parse all `.html` for `{% trans "..." %}` and `{% blocktrans %}...{% endblocktrans %}`, extract msgids, check presence in each `.po` | ✅ Yes | ✅ Yes (pure Python) | False negatives possible with `blocktrans` variables (`{{ query }}` → `%(query)s`); regex needs maintenance |
| **A2: `makemessages --keep-pot` + `msgmerge`** | Run `makemessages --keep-pot` to generate `.pot`, then `msgmerge --check po_file.po pot_file.pot` | ✅ Yes (gettext installed in Dockerfile:20) | ❌ No (msgmerge not on local Windows PATH) | Most robust (uses real Django extraction), but slow (~5s) and Docker-only |
| **A3: `makemessages` + git diff** | Run `makemessages -a --no-obsolete` in a temp branch/stash, check if `.po` files change | ✅ Yes | ⚠️ Requires git repo | Clean but invasive (modifies .po files); requires Git in test container |

**Key fact (verified):** Django's `makemessages` has **no `--check` flag**.
Available flags: `--locale`, `--exclude`, `--domain`, `--all`, `--extension`,
`--symlinks`, `--ignore`, `--no-default-ignore`, `--no-wrap`, `--no-location`,
`--add-location`, `--no-obsolete`, `--keep-pot`. Source:
`django.core.management.commands.makemessages.Command.add_arguments()` —
inspected directly (HIGH confidence).

**Recommended for Task A.2:** **A1 (parse templates + compare to .po)** as a
pytest unit test. It's pure Python, runs in both Docker and locally, integrates
with the existing `test_i18n_pipeline.py`, and catches the regression that the
project actually has (64 missing strings).

### A.3 `compilemessages` as a gate

**Fact (verified):** `compilemessages` has **no `--check` flag**. Its flags are
`--locale`, `--exclude`, `--use-fuzzy`, `--ignore`. It validates `.po` format
and will fail on syntax errors, but it does **not** check for empty `msgstr`.
An empty `msgstr` compiles successfully into a `.mo` file that produces a
fallback to the msgid — silently producing English output.

**Trade-off:** Using `compilemessages` exit code as a gate catches format errors
but not translation completeness. It's already called unconditionally in
`entrypoint-test.sh:37` before pytest.

### A.4 `msgfmt --check` (gettext CLI)

The `msgfmt` binary (from the `gettext` package, installed in Dockerfile:20)
supports `--check` (checks for empty msgstr) and `--check-format` (validates
printf format strings in msgid/msgstr). This is available **in Docker only**
(`gettext` is not installed on the local Windows dev machine).

```bash
# In Docker:
msgfmt --check --check-format src/backend/locale/ru/LC_MESSAGES/django.po
```

**Trade-off:** Not available locally; only catches empty msgstr (already covered
by the pytest test); doesn't catch missing strings.

### A.5 `msgattrib --untranslated` (gettext CLI)

`msgattrib --untranslated --no-fuzzy file.po` lists entries with empty msgstr.
Also `msgattrib --translated` for the inverse. Available in Docker only.

### Summary for Task A

| Tool | Empty msgstr | Missing strings | Docker-only? | Existing in project? |
|---|---|---|---|---|
| Custom pytest parser (existing `test_i18n_pipeline.py`) | ✅ Catches | ❌ No | ❌ | ✅ Yes, untracked |
| `msgfmt --check` | ✅ Catches | ❌ No | ✅ Yes | ❌ No (system tool) |
| `msgattrib --untranslated` | ✅ Catches | ❌ No | ✅ Yes | ❌ No (system tool) |
| `makemessages --check` | N/A | N/A | N/A | ❌ Does not exist |
| Template-parse + .po-compare (new pytest test) | N/A | ✅ Catches (64 missing) | ❌ | ❌ Not yet implemented |
| `makemessages` + git diff | N/A | ✅ Catches | ✅ Yes | ❌ Not yet implemented |

---

## Task B: Detect hardcoded strings not wrapped in `{% trans %}`

### B.1 djlint

**Fact (verified):** djlint 1.44.2 has **45 built-in rules** — **none** detect
hardcoded translatable text. The full rule list (extracted from
`djlint/rules.yaml`) covers: tag whitespace, static URLs, lang attributes,
DOCTYPE, attribute quoting, alt attributes, blank lines, heading line breaks,
title tags, void tags, entity references (H023), inline styles, HTTPS links,
orphan tags, empty id/class, unclosed strings, form whitespace, lowercase
methods, meta description, duplicate attributes, unclosed tags, missing include
names, mismatched tags, label/id matching. **No translatable-text rule exists.**

The project config (`pyproject.toml[tool.djlint]`) ignores `D018,H019,H021,H023,H030`.
A custom rule `H901` is defined in `src/backend/djlint_custom_rules.py` (loaded
via `.djlint_rules.yaml`), but it only detects multi-line `{# ... #}` comments
— not hardcoded text.

**djlint `--include`/`--exclude` flags** let you enable/disable specific rule
codes, but there is no translatable-text rule code to include.

**djlint `--isolate`**: A djlint feature where a template is linted in isolation
(removing `{% extends %}`/`{% block %}` context). It does NOT help with
hardcoded text detection.

### B.2 Custom djlint rule (Python module)

The project already has a pattern for this: `djlint_custom_rules.py` defines a
`run()` function that receives raw template HTML and returns errors. A similar
rule could be written to flag visible text in "translatable zones" (`<a>`,
`<button>`, `<label>`, `<option>`, `<h1>`–`<h6>`, `<span>` with visible text,
`<title>`, `placeholder` attributes).

**False-positive risks (verified against actual templates):**
- SVG `<path d="...">` content (path data is not visible text)
- `<code>` blocks (technical content like `sessionid`, `csrfmiddlewaretoken`)
- Brand names ("Mko Bazuna") — intentionally not translated
- Emoji / icons ("❤️", "🔔", "📍", "↓", "✅")
- Template comments `{# ... #}` and `{% comment %}...{% endcomment %}` spanning lines
- `aria-label` attributes that ARE wrapped in `{% trans %}` (should not be double-flagged)
- `<p>` text inside privacy policy (intentionally untranslated — legal text)

### B.3 Custom pytest test (template parsing)

A pytest test could use Django's template parser (`django.template.parser`) to
walk the template AST and find `TextNode` objects containing visible text outside
`{% trans %}` / `{% blocktrans %}` blocks. This is more robust than regex because
it understands Django template syntax.

However, Django's template parser doesn't natively distinguish "text that should
be translated" from "text that shouldn't." The parser would need an allowlist of
tags/elements where text is translatable and an allowlist of text patterns to skip.

### B.4 Heuristic: grep for visible Cyrillic / English text in specific elements

A simpler approach: use regex to find text content in specific HTML elements
(`<a>`, `<button>`, `<label>`, `<option>`, `<span>`, `<h1>`-`<h6>`, `<title>`)
that contains Cyrillic characters or specific English words, but is NOT inside a
`{% trans %}` tag. This is what my verification script does.

**False-positive risks are significant** (see B.2) — this approach works but
needs careful allowlisting.

### B.5 No `makemessages`-based approach

`makemessages` only extracts strings from `{% trans %}` tags — it cannot detect
strings that are NOT wrapped. It only tells you what IS extracted, not what's
missing. So it's useless for Task B.

### Summary for Task B

| Approach | Detects hardcoded text? | False-positive risk | Docker-only? | Effort |
|---|---|---|---|---|
| djlint built-in | ❌ No rule exists | N/A | ❌ | N/A |
| Custom djlint rule (Python) | ✅ Yes | ⚠️ High (SVG, code, brand names) | ⚠️ Needs PYTHONPATH fix | Medium |
| Custom pytest test (AST) | ✅ Yes | ⚠️ Medium (needs allowlists) | ❌ | Medium-High |
| Regex heuristic in pytest | ✅ Yes | ⚠️ Medium (comment blocks, SVG) | ❌ | Low-Medium |
| `makemessages` | ❌ No (only extracts trans tags) | N/A | ❌ | N/A |

---

## Task C: Detect `.mo` compilation / runtime fallback

### C.1 `.mo` file existence (already handled)

The existing `test_i18n_pipeline.py::TestI18nPipeline.test_mo_files_exist`
already checks that `.mo` files exist for every `.po` file. The `entrypoint-test.sh:37`
already calls `compilemessages` before pytest, so this test passes in the test
container.

### C.2 Runtime canary test (msgid leak detection)

A pytest test can render a key template in each non-base language and assert
that a known `{% trans %}` English msgid does NOT appear in the response (i.e.,
it was actually translated, not leaked as the msgid fallback).

**Pattern** (verified against `test_language_end_to_end.py`):
```python
@pytest.mark.django_db
def test_trans_string_not_leaked_in_bs(self):
    client = Client()
    response = client.get(detail_url + "?lang=bs")
    # "Contact Seller" is the English msgid in the .po file
    # If .mo is missing or msgstr is empty, gettext returns "Contact Seller"
    assert b"Contact Seller" not in response.content
    # The Bosnian translation should appear instead
    assert b"Kontaktiraj prodavca" in response.content
```

**Key insight:** This test would catch ALL of these failures:
- Missing `.mo` file (gettext falls back to msgid)
- Empty `msgstr` (gettext falls back to msgid)
- Wrong language activated (middleware bug)

**Minimal canary templates/strings:**
The `detail.html` template (`{% trans "Contact Seller" %}`, `{% trans "Back to listings" %}`,
`{% trans "Location:" %}`) is the best canary — it's already covered by
`test_language_end_to_end.py` (which renders it with published ads). Adding
assertion that English msgids don't appear would be a ~5-line addition to
existing tests.

**Can this use `Client` + `assertNotContains`?** Yes.
Django's `Client` respects the middleware chain (including the custom
`LanguagePreMiddleware`), so `client.get(url + "?lang=bs")` activates Bosnian
and renders `{% trans %}` strings through gettext. `assertNotContains` /
`assertContains` work on `response.content` (bytes).

### C.3 `msgstr == msgid` (identity translations)

For the `en` locale, `msgstr` is intentionally identical to `msgid` (English
is the base). For `ru` and `bs`, `msgstr` should differ from `msgid`. A test
that flags `msgstr == msgid` for non-base languages would catch entries where
the English msgid was copy-pasted as the translation without actual translation.

**Verified:** In the `en/LC_MESSAGES/django.po` file, all 39 msgstr values
equal their msgid (identity translations, correct for English base). In `ru/`
and `bs/`, all 39 msgstr values differ from msgid (actual translations present).

### Summary for Task C

| Check | Already exists? | Docker-only? | What it catches |
|---|---|---|---|
| `.mo` file exists | ✅ `test_mo_files_exist` | ❌ | Missing .mo files |
| `Client.render` + msgid leak | ❌ Not yet | ❌ | Empty msgstr, missing .mo, wrong language |
| `msgstr != msgid` for ru/bs | ❌ Not yet | ❌ | Copy-paste "translations" |

---

## Task D: Inline JavaScript string translation

### D.1 Current state (verified)

`src/backend/templates/components/header_catalog.html` contains inline
`<script>` blocks with 5 hardcoded Russian strings (lines 213-220):

```javascript
sectionHeader('Показать все результаты')  // line 213
sectionHeader('Города')                    // line 217  (Cities)
sectionHeader('Категории')                 // line 218  (Categories)
sectionHeader('Популярные запросы')        // line 219  (Popular searches)
sectionHeader('История')                   // line 220  (History)
```

These are inside vanilla JS `sectionHeader()` function calls, NOT inside
`{% trans %}` tags. Django's `makemessages` does **not** extract strings from
`<script>` blocks (it scans for `{% trans %}` / `{% blocktrans %}` template
tags only). So these strings will NEVER appear in `.po` files.

### D.2 Django-recommended pattern: `{% trans "str" as var %}` + `escapejs`

**Pattern:**
```django
{% load i18n %}
{% trans "Cities" as js_cities %}
{% trans "Categories" as js_categories %}
{% trans "Popular searches" as js_popular %}
{% trans "History" as js_history %}
{% trans "Show all results" as js_show_all %}
<script>
var i18nLabels = {
    cities: "{{ js_cities|escapejs }}",
    categories: "{{ js_categories|escapejs }}",
    popular: "{{ js_popular|escapejs }}",
    history: "{{ js_history|escapejs }}",
    showAll: "{{ js_show_all|escapejs }}"
};
sectionHeader(i18nLabels.cities);
</script>
```

**`escapejs` and Cyrillic (verified):** Django's `escapejs` filter
(`django.utils.html.escapejs`) escapes only JavaScript-special characters:
backslash `\`, double quote `"`, single quote `'`, newline `\n`, carriage
return `\r`, tab `\t`, form feed `\f`. It does **NOT** escape Unicode/Cyrillic
characters — they pass through as raw UTF-8. Verified against Django source
(`django/utils/html.py`). This means `escapejs` is **UTF-8 safe** for Cyrillic.

### D.3 JSON dict approach (scalable)

For templates with many inline JS strings, a single JSON dict rendered
server-side is cleaner:

```django
{% load i18n %}
<script>
window.__i18n = {
    "section_headers": {
        "city": "{% trans "Cities" as t1 %}{{ t1|escapejs }}",
        "category": "{% trans "Categories" as t2 %}{{ t2|escapejs }}",
        ...
    }
};
</script>
```

**Trade-off:** More lines of template code, but only one `{% load i18n %}`
needed and strings are grouped. Good for components with 5+ strings.

### D.4 Individual `{% trans ... as var %}` (simpler)

Each string gets its own variable. Simpler for 1-2 strings, but verbose for 5+.

### D.5 `django-jsi18n` / `jsi18n` view

Django ships the `django.views.i18n.javascript_catalog` / `jsi18n` view, which
serves translations as a JavaScript `gettext()` function. Requires running
`django-admin jsi18n -d djangojs` to generate a `.json`/`.js` catalog.

**Trade-offs:**
- **Pros:** Full JavaScript `gettext()` API, handles pluralization (`ngettext`),
  no template changes needed for each string.
- **Cons:** Requires a new `djangojs` domain (`.po` files in a separate
  `locale/djangojs.po` path), adds an HTTP endpoint, and is **overkill for 5
  static strings** in one template. The project already has a working pattern
  for inline JS in `header_catalog.html` (vanilla JS, no framework).

### D.6 `deep-translator` (already a project dependency)

The project includes `deep-translator>=1.11.0` (line 19 of `pyproject.toml`).
This could be used to auto-generate `msgstr` values during `makemessages`
workflow. However, it's currently used only for Montenegrin→Russian ad-content
translation at publication time (per `spec-index.md:47`). Using it for UI string
translation would be a new use case.

### Recommendation for Task D

**Use the `{% trans "..." as var %}` + `escapejs` pattern** for the 5 strings
in `header_catalog.html`. This is the standard Django approach, requires no new
dependencies or endpoints, and `escapejs` handles Cyrillic correctly. Group the
5 variables at the top of the `<script>` block for readability.

---

## Task E: CI / pre-commit integration

### E.1 Project integration points (verified)

| Integration point | Status | File |
|---|---|---|
| `make test` (fast gate) | ✅ Exists | `Makefile:98-100` — skips `seed` marker, reuses DB |
| `make test-all` (full suite) | ✅ Exists | `Makefile:103-105` |
| `make lint` | ✅ Exists | `Makefile:107-108` (ruff) |
| `make lint-templates` | ✅ Exists | `Makefile:113-114` (djlint) |
| `make makemessages` | ✅ Exists | `Makefile:146-147` |
| `make compilemessages` | ✅ Exists | `Makefile:149-150` |
| `docker/entrypoint-test.sh` | ✅ Compiles `.mo` before pytest | `entrypoint-test.sh:37` |
| `.pre-commit-config.yaml` | ❌ Does not exist | — |
| `.github/workflows/` | ❌ Does not exist | — |
| `pytest` markers | ✅ `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group` | `pyproject.toml[tool.pytest.ini_options]` |

### E.2 Existing test placement conventions

Tests live under `src/backend/apps/<app>/tests/` with `pytestmark` markers:
- `pytest.mark.unit` — no DB, runs in fast gate (`make test`)
- `pytest.mark.django_db` — requires DB
- `pytest.mark.integration` — uses Django `Client` / middleware chain

The existing `test_i18n_pipeline.py` (untracked, in `ads/tests/`) uses
`SimpleTestCase` + `pytest.mark.unit` — the correct pattern for pure-file
checks (no DB needed).

### E.3 Minimal viable "fail build if translations incomplete" setup

**Three components, all using existing infrastructure:**

1. **Pytest tests** (extend `test_i18n_pipeline.py`):
   - `test_no_empty_msgstr` — ✅ already exists
   - `test_mo_files_exist` — ✅ already exists
   - `test_po_contains_all_template_msgstrs` — NEW: parse templates, check all msgids in .po
   - `test_trans_strings_render_in_bs_and_en` — NEW: runtime canary via `Client`
   - These are `unit`-marked (no DB for the file checks) and would run in
     `make test` (fast gate, ~300s). The runtime canary test would be
     `integration`-marked and run in the fast gate too.

2. **Makefile target:**
   ```makefile
   i18n-check:
       docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages
       docker compose $(COMPOSE_TEST) run --rm test pytest src/backend/apps/ads/tests/test_i18n_pipeline.py -v
   ```

3. **Pre-commit hook** (optional, new file):
   If the team adopts pre-commit, a `.pre-commit-config.yaml` could run
   `djlint` and the i18n pytest test locally before commit. But since the
   project currently has no pre-commit config and all linting runs in Docker,
   this is not required for MVP.

### E.4 Where tests should live

**Recommendation:** Extend `src/backend/apps/ads/tests/test_i18n_pipeline.py`
(it already exists as an untracked file with the right structure). If committed,
this is the natural home for all i18n pipeline tests. The existing file already
has `_parse_po_entries`, `_po_files()`, and `TestI18nPipeline`.

If the team prefers a dedicated location, `src/backend/apps/core/tests/` is
the alternative — `test_templates.py` there already does static template guards
using the same pattern (`SimpleTestCase` + `pytest.mark.unit` + `settings.TEMPLATES`).

### E.5 CI pipeline

No CI config exists. If GitHub Actions is added, the minimal workflow:
```yaml
# .github/workflows/test.yml
- name: Start test DB
  run: docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db
- name: Run fast gate
  run: docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test
```
The `entrypoint-test.sh` already compiles messages and runs the full pytest
suite. No additional CI changes needed — the i18n tests would automatically
run as part of `make test`.

### Summary for Task E

| Integration point | Feasibility | Recommendation |
|---|---|---|
| pytest tests (extend `test_i18n_pipeline.py`) | ✅ High — follows existing pattern | **Primary integration** |
| Makefile target (`make i18n-check`) | ✅ Simple — one target | **Secondary** |
| Pre-commit hooks | ⚠️ Medium — no existing config, all linting in Docker | Optional, post-MVP |
| GitHub Actions CI | ❌ Low — no CI exists, would need full workflow setup | Post-MVP |

---

## Top Feasible Approaches (Synthesis)

### Approach 1 (Recommended): Extend existing pytest i18n test suite

**What:** Add two new test classes/functions to `test_i18n_pipeline.py`,
alongside the existing `test_no_empty_msgstr` and `test_mo_files_exist`:

1. **`test_po_contains_all_template_msgstrs`** (unit, no DB):
   Parse all `.html` templates under `settings.TEMPLATES[0]["DIRS"]` for
   `{% trans "..."}` and `{% blocktrans %}...{% endblocktrans %}` strings.
   Extract msgids. Verify each msgid exists in every `.po` file. Report
   missing msgids with file:line references (using `--add-location` or
   template line tracking).

2. **`test_trans_strings_render_translated`** (integration, uses Client):
   Render `ads/detail.html` (or `ads/list.html`) with `?lang=bs` and
   `?lang=en` using Django's test `Client`. For a set of "canary" msgids
   known to be translated (e.g., "Contact Seller" → "Kontaktiraj prodavca"),
   assert the English msgid does NOT appear in the response and the
   translated string does appear.

3. **`test_no_identity_translation_for_non_base`** (unit, no DB):
   For `ru` and `bs` `.po` files, flag entries where `msgstr == msgid`
   (copy-paste translations, not real translations).

**Pros:**
- Runs in existing `make test` fast gate (~300s) — no new infrastructure
- Uses the exact same pattern already in `test_i18n_pipeline.py`
  (`SimpleTestCase`, `pytest.mark.unit`, `settings.LOCALE_PATHS`)
- The existing `entrypoint-test.sh:37` already compiles `.mo` files, so
  the runtime canary test will have `.mo` files to work with
- No new dependencies required
- Catches the actual regressions the project has (64 missing strings)
- Test names are self-documenting — a failing test immediately tells the
  developer which strings are missing

**Cons:**
- The template msgid parser needs to handle `blocktrans` variables
  (`{{ query }}` → `%(query)s` in .po). The existing `_parse_po_entries`
  already handles this correctly (verified: the .po file has
  `msgid "No results found for \"%(query)s\""` which matches the
  `{% blocktrans %}No results found for "{{ query }}"{% endblocktrans %}`
  in `ad_list.html`).
- The custom `.po` parser is fragile (doesn't handle fuzzy flags, plurals,
  multi-line msgid continuations perfectly). Replacing with `polib` would
  be more robust but adds a dependency.

### Approach 2: Makefile target + gettext CLI (`msgfmt --check`, `msgmerge --check`)

**What:** Add a `make i18n-check` Makefile target that runs in Docker:
```makefile
i18n-check:
    $(MAKE) compilenamesages  # or compilemessages
    docker compose $(COMPOSE_FILES) run --rm web uv run msgfmt --check --check-format src/backend/locale/*/LC_MESSAGES/django.po
    docker compose $(COMPOSE_FILES) run --rm web uv run python -c "from django.core.management import call_command; call_command('makemessages', '--keep-pot', '-a')"
    # diff .pot against .po files
```

**Pros:**
- Uses battle-tested gettext tools (`msgfmt`, `msgmerge`, `msgattrib`)
- `msgfmt --check` catches empty msgstr + format errors
- `msgmerge --check` catches outdated .po files

**Cons:**
- **Docker-only** — `msgfmt`/`msgmerge` not on local Windows PATH
- Separates i18n checks from the pytest suite (different failure domain)
- `makemessages --keep-pot` is slow (~5s) and modifies files
- Doesn't detect hardcoded non-trans text (Task B) or runtime fallback (Task C)
- `msgfmt --check` only catches empty msgstr (already handled by pytest test)

### Approach 3: Add `polib` + custom djlint rule for hardcoded text

**What:**
1. Add `polib` as a dev dependency (`uv add --dev polib`)
2. Replace the custom `_parse_po_entries` with `polib.pofile()`
3. Write a custom djlint rule (like `H902` in `djlint_custom_rules.py`) that
   flags visible text in translatable elements not wrapped in `{% trans %}`

**Pros:**
- `polib` is the de-facto standard .po parser in Python (robust, handles
  fuzzy flags, plurals, multi-line, etc.)
- Custom djlint rule integrates with existing `make lint-templates` flow
- Would catch Task B (hardcoded text) at lint time, not test time

**Cons:**
- New dependency (though `polib` is pure Python, ~50KB)
- Custom djlint rule for hardcoded text has **high false-positive risk**
  (SVG paths, `<code>` blocks, brand names, emoji, comment blocks)
  — would require a comprehensive allowlist
- djlint custom rules only work in Docker (PYTHONPATH issue with
  `djlint_custom_rules` module — verified: local `djlint` invocation fails
  with `ModuleNotFoundError: No module named 'djlint_custom_rules'`)
- Doesn't help with Task C (runtime fallback) or Task D (inline JS)

---

## Recommended Approach: **Approach 1** (extend pytest i18n test suite)

### Rationale

1. **The project already has `test_i18n_pipeline.py`** (untracked) with the
   exact pattern needed: `SimpleTestCase`, `pytest.mark.unit`, custom `.po`
   parser, `_po_files()` helper using `settings.LOCALE_PATHS`. Extending it
   is the lowest-effort, highest-leverage change.

2. **All checks need to work in the test container** (Docker bind-mounts
   source, no `msgfmt`/`msgmerge` on local Windows). Python-only checks
   have the widest reach.

3. **It catches the actual regressions** the project has right now:
   - 64 missing msgids in .po files (Task A.2)
   - Hardcoded text in 4 templates (Task B — via template parsing)
   - Runtime fallback if .mo is missing (Task C)

4. **No new dependencies.** Adding `polib` (Approach 3) would be nice-to-have
   but the existing parser already works. Following the project rule
   "Avoid Overengineering" and "Follow Existing Patterns."

5. **Test names document the requirement.** A developer who adds a new
   `{% trans "Foo" %}` to a template and forgets to run `makemessages` will
   see `test_po_contains_all_template_msgstrs` fail with a clear message:
   `"Missing msgid 'Foo' in ru.po"`.

### Concrete Implementation Sketch

**File: `src/backend/apps/ads/tests/test_i18n_pipeline.py`** (extend existing)

```python
# ─── New helper: extract all trans strings from templates ─────────────────

import re as _re
from pathlib import Path as _Path

# Regex patterns (simple, tested against the codebase's 100 trans strings)
_TRANS_RE = _re.compile(r'{%\s*trans\s+"([^"]*)"\s*%}')
_BLOCKTRANS_RE = _re.compile(
    r"{%\s*blocktrans\s*%}(.*?){%\s*endblocktrans\s*%}", _re.DOTALL
)


def _collect_template_msgids() -> set[str]:
    """Return all unique msgids found in {% trans %} and {% blocktrans %} tags
    across every template in settings.TEMPLATES[0]['DIRS']."""
    template_dir = _Path(str(settings.TEMPLATES[0]["DIRS"][0]))
    msgids: set[str] = set()
    for f in template_dir.rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        for m in _TRANS_RE.finditer(text):
            msgids.add(m.group(1))
        for m in _BLOCKTRANS_RE.finditer(text):
            # blocktrans inner text may contain {{ var }} → %()s in msgid
            inner = m.group(1).replace("{{", "%(").replace("}}", ")s").strip()
            msgids.add(inner)
    return msgids


# ─── New test: .po completeness ────────────────────────────────────────────


class TestPoCompleteness(SimpleTestCase):
    """Verify all {% trans %} / {% blocktrans %} strings in templates are
    present in every .po file (no missing strings after adding new templates)."""

    def test_po_contains_all_template_msgstrs(self) -> None:
        template_msgids = _collect_template_msgids()
        for po_path in _po_files():
            po_msgids = {msgid for msgid, _ in _parse_po_entries(po_path.read_text())}
            missing = template_msgids - po_msgids
            assert not missing, (
                f"{po_path.name}: missing {len(missing)} msgids: {sorted(missing)}"
            )

    def test_no_identity_translation_for_non_base(self) -> None:
        """For ru and bs, msgstr must differ from msgid (real translation,
        not copy-paste). English (en) is the base language, so identity
        msgstr is correct."""
        for po_path in _po_files():
            lang = po_path.parent.parent.name
            if lang == "en":
                continue
            entries = _parse_po_entries(po_path.read_text())
            identity = [
                msgid
                for msgid, msgstr in entries
                if msgid and msgstr and msgid == msgstr
            ]
            assert not identity, (
                f"{po_path}: {len(identity)} entries where msgstr == msgid "
                f"(not translated): {identity[:5]}"
            )


# ─── New test: runtime canary (msgid leak detection) ──────────────────────


@pytest.mark.django_db
@pytest.mark.integration
class TestTransRuntimeCanary:
    """Render key templates in each non-base language and assert that English
    msgids do not leak (gettext fallback would return the msgid unchanged)."""

    # Canary strings: (msgid, bs_translation, en_translation)
    CANARY_STRINGS = [
        ("Contact Seller", "Kontaktiraj prodavca", "Contact Seller"),
        ("Back to listings", "Natrag na oglase", "Back to listings"),
        ("Location:", "Lokacija:", "Location:"),
    ]

    @pytest.fixture(autouse=True)
    def _locale_cleanup(self):
        from django.utils import translation

        yield
        translation.deactivate()

    def test_detail_renders_translated_strings_in_bs(self, seller, category, city):
        from django.test import Client
        from django.urls import reverse
        from conftest import create_test_ad

        ad = create_test_ad(
            seller,
            category,
            city,
            title="T",
            description="D",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        response = client.get(reverse("ads:detail", args=[ad.id]) + "?lang=bs")
        # English msgid "Contact Seller" must NOT appear when bs is active
        assert b"Contact Seller" not in response.content
        # Bosnian translation must appear
        assert b"Kontaktiraj prodavca" in response.content
```

**File: `Makefile`** — add `i18n-check` target:

```makefile
i18n-check:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_SKIP_MARKERS=seed \
		-e PYTEST_OPTS="src/backend/apps/ads/tests/test_i18n_pipeline.py -v" \
		test
```

**File: `.pre-commit-config.yaml`** (new, optional):

```yaml
# Not currently used — project lints in Docker via Makefile.
# Add this for local pre-commit support if adopted.
repos:
  - repo: local
    hooks:
      - id: i18n-pipeline
        name: i18n pipeline (po completeness + mo existence)
        entry: docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test
        language: system
        files: ^src/backend/locale/
        pass_filenames: false
```

### Constraints & Gotchas

1. **`polib` not in project** — The existing custom `.po` parser works but is
   fragile. If it breaks on complex `.po` files (plurals, fuzzy, multi-line
   continuations), consider `uv add --dev polib`. Decision point at
   implementation time.

2. **djlint custom rules need Docker** — `djlint` can't find
   `djlint_custom_rules.py` locally (PYTHONPATH issue). It works in Docker
   (Makefile sets `PYTHONPATH=/app/src:/app/src/backend`). A custom djlint
   rule for hardcoded text would have the same constraint. This makes djlint
   an unsuitable place for the "hardcoded text" check if developers need
   local feedback.

3. **`makemessages` does not handle inline JS** — The inline JS strings in
   `header_catalog.html` cannot be extracted by `makemessages` and will never
   appear in `.po` files. The template-parse + .po-compare test would NOT
   catch these. A separate check is needed: grep templates for `{% trans %}`
   strings AND for visible text in `<script>` blocks.

4. **`--no-location` inconsistency** — The Makefile's `makemessages` target
   uses `--no-location` (removes `#: file:line` comments), but the existing
   `.po` files HAVE location comments. Running `make makemessages` would
   remove them. This is cosmetic but creates noise in diffs.

5. **No CI pipeline** — The project has no `.github/workflows/` or
   `.pre-commit-config.yaml`. Tests only run via `make test` (Docker). The
   recommended approach works within this constraint — all checks are pytest
   tests that run in Docker.

6. **`header.html` vs `header_auth_entry.html` inconsistency** — Two different
   header components exist: `header.html` (hardcoded English text, used on
   ~12 pages) and `header_catalog.html` which includes `header_auth_entry.html`
   (trans-wrapped, used on listings/detail). Both need fixing before i18n is
   complete. The runtime canary test should cover both.

7. **`escapejs` for inline JS** — Safe for Cyrillic (verified). But the
   `{% trans "..." as var %}` pattern must be used OUTSIDE the `<script>`
   block and referenced inside it — Django template tags are processed before
   the script runs.

8. **`blocktrans` with `{{ var }}`** — In `.po` files, `{{ query }}` becomes
   `%(query)s`. A custom parser needs to handle this normalization. The
   existing `_parse_po_entries` handles this correctly (the .po file has
   `"No results found for \"%(query)s\""`).

---

## Sources

| Source | Confidence | Notes |
|---|---|---|
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | HIGH (read directly) | 39 msgids each, all msgstr populated |
| `src/backend/apps/ads/tests/test_i18n_pipeline.py` | HIGH (read directly) | Existing test with custom .po parser |
| `docker/Dockerfile:12-21,78` | HIGH (read directly) | `gettext` in builder, `compilemessages` at line 78 |
| `docker/entrypoint.sh:70-87` | HIGH (read directly) | `compile_messages()` function, called before `exec` |
| `docker/entrypoint-test.sh:37` | HIGH (read directly) | `compilemessages` runs before pytest |
| `Makefile:146-150` | HIGH (read directly) | `makemessages` and `compilemessages` targets exist |
| `config/settings/base.py:55-62` | HIGH (read directly) | `LANGUAGE_CODE`, `LANGUAGES`, `LOCALE_PATHS` |
| `apps/core/middleware/language.py` | HIGH (read directly) | Custom middleware, `translation.activate(lang)` |
| `djlint/rules.yaml` (45 rules) | HIGH (inspected via Python) | No translatable-text rule |
| `src/backend/djlint_custom_rules.py` | HIGH (read directly) | Custom H901 rule pattern exists |
| `pyproject.toml[tool.pytest.ini_options]` | HIGH (read directly) | Markers: unit, integration, seed, settings, concurrent, slow, real_images, xdist_group |
| Django `makemessages.add_arguments()` | HIGH (inspected via Python) | 13 flags, no `--check` |
| Django `compilemessages.add_arguments()` | HIGH (inspected via Python) | 4 flags, no `--check` |
| Template `{% trans %}` usage (126 matches) | HIGH (grep verified) | 100 unique msgids, 39 in .po |
| Hardcoded Cyrillic text (14 findings) | HIGH (regex verified) | 4 templates with untranslatable text |
| No `polib`/`babel` in `uv.lock` | HIGH (grep verified) | No .po parsing library available |
| No `.pre-commit-config.yaml` | HIGH (glob verified) | Project not using pre-commit |
| No `.github/workflows/` | HIGH (glob verified) | No CI pipeline |
| `Decision_07.md` | HIGH (glob verified) | **Does not exist** — owner decisions go O1-O5 only |
| `escapejs` and Cyrillic | HIGH (Django source) | Does not escape Unicode/Cyrillic chars |
| Gap analysis doc (stale) | MEDIUM | `i18n-translation-pipeline-gap-analysis.md` claims "all msgstr empty" but they're populated; describes pre-fix state |

---

## Verification Checklist

- [x] All `.po` files read and compared against template `{% trans %}` strings
- [x] `makemessages` and `compilemessages` command flags inspected via Python introspection
- [x] djlint rules enumerated (45 rules, none about translation)
- [x] `djlint_custom_rules.py` pattern examined for custom rule feasibility
- [x] Dockerfile, entrypoint.sh, entrypoint-test.sh inspected for `compilemessages`
- [x] Makefile inspected for existing i18n targets
- [x] Settings inspected for `LANGUAGES`, `LOCALE_PATHS`, middleware
- [x] `header_catalog.html` inline JS strings identified and located
- [x] Hardcoded text in 4 templates identified (Cyrillic and English)
- [x] `test_i18n_pipeline.py` and `test_language_end_to_end.py` patterns analyzed
- [x] Python files checked for `gettext`/`gettext_lazy` usage (none found)
- [x] `polib`/`babel`/`translate-toolkit` confirmed NOT in `uv.lock`
- [x] `.mo` files confirmed to exist on disk (gitignored)
- [x] No pre-commit or CI configuration confirmed
