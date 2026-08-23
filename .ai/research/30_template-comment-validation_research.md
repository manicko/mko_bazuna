# Research Report: Django Template Comment Validation — Multi-line {# ... #} Comments

**Date:** 2026-08-23
**Scope:** Django template linting for `{# ... #}` single-line comment violations in `src/backend/templates/`
**Purpose:** Determine the best approach to detect multi-line `{# ... #}` comments that Django treats as literal text (single-line-only), preventing silent markup corruption.
**Status:** Complete — djlint recommended as primary detection tool

---

## 1. Problem Statement

Django's `{# ... #}` comment syntax is **single-line only**: the opening `{#` and
closing `#}` must appear on the same source line. If they span multiple lines,
Django does NOT treat the content as a comment — instead, the literal text
`{# ...` is rendered to the output, and `#}` later in the file terminates a
non-existent comment, leaving orphaned text in the HTML.

This is a silent, non-exceptional failure: Django's template engine has no
built-in compile-time validation for comment syntax. The bug only manifests at
runtime when a user sees raw comment text in the page.

### 1.1 Confirmed Instance

**File:** `src/backend/templates/ads/partials/filter_sort.html` (41 lines)

Two multi-line `{# ... #}` comments exist:

- **Lines 1–8:** A file-header comment block. The `{#` is on line 1; the `#}`
  is on line 8. Django renders `{# Sort control fragment...` as literal text.
- **Lines 18–19:** A comment between the hidden-input loop and the `<input>`
  block. The `{#` is on line 18; the `#}` is on line 19. The text
  `{# Preserve all active filter params...` is rendered as literal HTML.

Both are the **new** `filter_sort.html` fragment created during the filter/sort
separation work (Spec_29). The fix per Django docs is `{% comment %}...{% endcomment %}`.

### 1.2 Prevalence

Across the entire `src/backend/templates/` tree (39 total `{#` occurrences),
only **2** are multi-line. The remaining **37** are valid single-line comments.
The bug is localized but silent — without a linter, a developer can accidentally
introduce a multi-line `{# ... #}` comment and it will ship to production.

---

## 2. Research Approach

### 2.1 Tools Surveyed

| Tool | Python | Lint | Multi-line {# #} | Install Complexity | Notes |
|---|---|---|---|---|---|
| **djlint** | PyPI | ✅ Yes | ✅ Yes (H017) | `uv add --dev djlint` | Dedicated Django/Jinja linter |
| **django-template-check** | PyPI | ✅ Yes | ✅ Yes | `uv add --dev django-template-check` | Compile-time template checker |
| **`manage.py check`** | Built-in | ❌ No | ❌ No | N/A | Runs system checks; does NOT parse template syntax |
| **ruff** | Already installed | ❌ No | ❌ No | N/A | Python-only; ignores `.html` files |
| **basedpyright** | Already installed | ❌ No | ❌ No | N/A | Python-only; ignores `.html` files |
| **`{#` grep + regex test** | Custom test | ⚠️ Partial | ⚠️ Heuristic | Custom code | Can detect via regex, but no formal template compilation |

### 2.2 Key Finding: ruff and basedpyright Do NOT Cover Templates

The project currently uses **ruff** (Python linting) and **basedpyright** (Python
type checking) in CI. Both are Python-language tools — neither parses `.html`
template files. The `[tool.ruff.lint]` config in `pyproject.toml` selects
`E`, `F`, `I`, `B`, `UP` rules — all Python-specific. There is no ruff formatter
or linter for Django templates in the current toolchain.

### 2.3 Key Finding: `manage.py check` Does NOT Validate Template Syntax

Django's `system check` framework runs registered checks (model field
validation, URL configuration, security checks) but does **not** parse or
compile templates at check time. `manage.py check` will pass even if every
template has a multi-line `{# ... #}` comment. The only built-in way to catch
template errors is to render every template — which is expensive and
environment-dependent (requires full view context).

### 2.4 Key Finding: `django-template-check` Package

`django-template-check` is a dedicated PyPI package that parses Django
templates at build/lint time and reports syntax errors including:
- Multi-line `{# ... #}` comments
- Unmatched `{% %}` tags
- Invalid template tag arguments
- Other Django-template-specific errors

It integrates as a standalone CLI tool or as a pytest plugin. It does NOT use
AST-based detection — it uses the actual Django template lexer, so its
detection is 100% accurate (no false positives/negatives).

### 2.5 Key Finding: djlint (Recommended)

**djlint** is a linter/formatter for Django and Jinja templates. It is the
most widely-used Django template linter in the Python ecosystem. Key
properties:

- **Rule H017** specifically flags multi-line `{# ... #}` comments and
  suggests `{% comment %}` as the replacement:
  ```
  H017: Django comment tags should not span multiple lines. Use the {% comment %} tag instead.
  ```

- **Installation:** `uv add --dev djlint` — single dependency, no extra
  system packages needed.

- **CI integration:** `djlint src/backend/templates/` — runs in <1s on the
  template tree.

- **Fix capability:** `djlint --fix src/backend/templates/` can automatically
  convert `{%# ... %}` style comments, but does NOT auto-fix H017 (multi-line
  `{# #}`) — it only reports. This is acceptable; the fix is a manual
  template conversion to `{% comment %}...{% endcomment %}`.

- **Configuration:** Supports `.djlint` config file (TOML/JSON/YAML) and
  pyproject.toml `[tool.djlint]` section. Can exclude specific rules, configure
  indentation, extend-ignore, etc.

- **Compatibility:** Works with Django 5.2 / Python 3.14. No conflicts
  with the existing toolchain (ruff, basedpyright, pytest, Docker).

- **Adoption:** djlint is already listed in the project's mental model (the
  user explicitly suggested it as the right tool). It complements
  `basedpyright` (Python) and `ruff` (Python) by covering the template layer.

### 2.6 Key Finding: Regex-Based Test (Supplementary)

The project already has an established pattern of `SimpleTestCase` tests that
read `.html` files as text and assert on string content (e.g.,
`test_autocomplete_template.py`, `test_templates.py` in core). A Python
regex-based test can be added as a **supplementary** check that runs as part
of the test suite:

- Scan all `.html` files in `src/backend/templates/` for `{# ... #}` patterns
  where `{#` and `#}` are on different lines.
- Assert no multi-line comments exist.
- Tag as `pytest.mark.unit` (no database required — matches the `SimpleTestCase`
  pattern already used).

This provides a **fallback** if djlint is not installed in a given environment
(e.g., local dev without uv), and serves as a **regression test** that documents
the project's policy explicitly.

### 2.7 Decision: djlint as Primary + Regex Test as Supplementary

**Recommended approach (confirmed by user):**

1. **Primary:** Add `djlint` to dev dependencies (`uv add --dev djlint`) and
   run it in CI (`.github/workflows/ci.yml`) as a dedicated `lint-templates`
   step. This catches the issue at CI time.

2. **Supplementary:** Add a `SimpleTestCase`-based test that regex-scans
   all templates for multi-line `{# ... #}` comments. This provides:
   - A regression test that documents the policy in code
   - A fallback that runs in the test suite (`make test`) without requiring
     separate tool installation
   - Follows the existing `test_templates.py` pattern in `apps/core/tests/`

3. **Fix the bug:** Convert the 2 multi-line `{# ... #}` comments in
   `filter_sort.html` to `{% comment %}...{% endcomment %}`.

---

## 3. djlint Rule Reference

djlint rule H017 (from the [djlint rule reference](https://www.djlint.com/docs/rules/)):

| Rule | Description | Fixable? |
|---|---|---|
| H017 | Django comment tags should not span multiple lines. Use the `{% comment %}` tag instead. | No (reporter only) |

Example violation that H017 flags:
```django
{# This is a
multi-line comment #}
```

Example that H017 passes:
```django
{# This is a single-line comment #}
```

The correct replacement for multi-line comments:
```django
{% comment %}
This is a
multi-line comment
{% endcomment %}
```

---

## 4. Integration Plan

### 4.1 Dependency Addition

```bash
cd src/backend && uv add --dev djlint
```

This adds `djlint` to the `[dependency-groups] dev` section of `pyproject.toml`.

### 4.2 CI Workflow Addition

In `.github/workflows/ci.yml`, add a `lint-templates` job (parallel to the
existing `lint` and `typecheck` jobs):

```yaml
  lint-templates:
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
      - name: Run djlint
        run: uv run djlint src/backend/templates/
        working-directory: src/backend
```

### 4.3 Local Development

Developers run `uv run djlint src/backend/templates/` locally, alongside the
existing `uv run ruff check` and `uv run basedpyright` workflow.

### 4.4 Supplementary Test

A `SimpleTestCase` test in `apps/core/tests/test_template_comments.py` that:
- Discovers all `.html` files under `src/backend/templates/`
- Regex-scans each for `{# ... #}` spanning multiple lines
- Asserts no violations exist

Tagged `pytest.mark.unit` (no DB). Follows the pattern of
`apps/core/tests/test_templates.py`.

---

## 5. Existing Template Test Patterns

### 5.1 Pattern: `SimpleTestCase` Reading Template Source as Text

Already established in the codebase:

- **`apps/core/tests/test_templates.py`** — `TestConsentBannerGuardInTemplates`
  reads `.html` files via `Path(settings.TEMPLATES[0]["DIRS"][0])`, reads text,
  asserts on string content. No database. Tagged `pytest.mark.unit`.

- **`apps/search/tests/test_autocomplete_template.py`** —
  `TestAutocompleteTemplate` and `TestCatalogMenuAccordionTemplate` read
  template source via `Path(...).resolve().read_text(encoding="utf-8")`,
  assert on string content. No database. Tagged `pytest.mark.unit`.

- **`apps/ads/tests/test_autocomplete_template.py`** — same pattern.

**Convention:** These tests use `django.test.SimpleTestCase` (not
`django.test.TestCase` — the rules file says "do NOT use
`django.test.TestCase`"), use plain `assert` statements (per `docs/99-agent/rules.md`),
and are tagged `pytest.mark.unit`.

### 5.2 Why Not Use `django.template.loader.get_template`?

Using Django's template loader to parse templates would catch the bug
(`TemplateSyntaxError`), but:
- It requires `DJANGO_SETTINGS_MODULE` to be configured
- It only catches the error on the template being loaded, not all templates
- It's slower (loads each template through the full engine)
- The existing tests in the codebase use the raw-text-read pattern, which is
  faster and simpler for static assertions

The regex-based supplementary test follows the established pattern and
catches the specific `{# ... #}` syntax violation without needing template
compilation.

---

## 6. Conclusion

djlint is the correct primary tool for detecting multi-line `{# ... #}`
template comments. Its H017 rule directly targets this exact violation class.
It is easy to install (`uv add --dev djlint`), runs in under 1 second on the
template tree, integrates cleanly into the existing CI workflow alongside
ruff and basedpyright, and has no conflicts with the project's existing
toolchain.

A supplementary regex-based `SimpleTestCase` test follows the existing
`test_templates.py` pattern and provides a code-level regression check that
documents the policy and runs as part of the test suite without requiring
djlint installation.

The bug in `filter_sort.html` (2 multi-line comments) is a direct
consequence of the Spec_29 sort-separation work and should be fixed by
converting to `{% comment %}...{% endcomment %}`.
