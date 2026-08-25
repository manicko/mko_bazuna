---
id: i18n-translation-pipeline-gap-analysis
domain: agent
tags:
  - i18n
  - translation
  - pipeline
  - docker
related:
  - architecture
  - rules
  - references
---

# i18n Translation Pipeline — Gap Analysis & Recommendations

**Date:** 2026-08-24
**Project:** Mko Bazuna (Django 5.2 LTS, HTMX MPA, Docker, PostgreSQL 18)
**Confidence:** HIGH (all findings verified against source code)

---

## 1. Current State (Operational as of August 2026)

The static i18n pipeline is **fully operational**. The runtime infrastructure, locale
catalogs, and the new automated completeness checks are all in place.

### 1.1 Runtime pipeline (operational)

| Component | File | Status |
|---|---|---|
| Custom middleware (single authority) | `apps/core/middleware/language.py` | ✅ `translation.activate(lang)` called; `request.LANGUAGE_CODE` set; cookie + `lang` param support |
| `USE_I18N = True` | `config/settings/base.py:56` | ✅ |
| `LANGUAGES` (ru/bs/en) | `config/settings/base.py:57-61` | ✅ |
| `LANGUAGE_CODE = "ru"` | `config/settings/base.py:55` | ✅ |
| `LOCALE_PATHS` | `config/settings/base.py:62` | ✅ → `src/backend/locale/` |
| `compilemessages` in Dockerfile builder | `docker/Dockerfile:78` | ✅ Compiles `.mo` at image build |
| `compilemessages` in entrypoint | `docker/entrypoint.sh:73-87` | ✅ Compiles for dev bind-mounts |
| `compilemessages` in test entrypoint | `docker/entrypoint-test.sh:37` | ✅ Compiles for test bind-mounts |
| Makefile targets | `Makefile:146-150` | ✅ `makemessages` and `compilemessages` targets |
| `i18n` context processor | `config/settings/base.py:138` | ✅ `django.template.context_processors.i18n` |
| Template context processor | `apps/core/context_processors.py` | ✅ Exposes `LANGUAGE_CODE`, `LANGUAGES`, `catalog_js_labels` |
| JSON-based ad content i18n | `apps/ads/models.py` (`get_title`/`get_description`) | ✅ `title_i18n` JSONB → fallback chain |
| JSON-based lookup i18n | `apps/lookups/models.py` (`LookupItem.get_name`) | ✅ `name_i18n` JSONB |
| `feature_tag` template filter | DB-based i18n for feature tags | ✅ Uses `get_lookup_name` (separate from gettext) |

### 1.2 Python-side gettext (introduced)

`gettext`/`gettext_lazy` is now imported and used in production Python for the
first time, covering 15 user-facing strings across 6 files:

| File | Strings | Variant |
|---|---|---|
| `apps/core/context_processors.py` | `"Entire country"` + 5 JS labels | `gettext` (runtime) |
| `apps/core/enums.py` | `TimeRange` labels (3) | `gettext_lazy` |
| `apps/ads/views/dashboard.py` | `status_labels` dict (5) | `gettext_lazy` |
| `apps/ads/views/edit.py` | error + 3 × `HttpResponseForbidden` | `gettext` (runtime) |
| `apps/ads/views/delete.py` | `HttpResponseForbidden` (1) | `gettext` (runtime) |
| `apps/ads/views/listings.py` | `HttpResponseForbidden` (1) | `gettext` (runtime) |

`Http404(...)` messages are intentionally left untranslated — Django's default 404
handler does not render them to users in production.

### 1.3 Catalog completeness

All `.po` files for `ru`, `en`, and `bs` have been extracted via `makemessages`
and populated with complete `msgstr` values:

- **`ru`** (primary): 0 empty `msgstr` — every msgid is translated.
- **`bs`** (secondary): 0 empty `msgstr` — every msgid is translated.
- **`en`** (secondary): `msgstr` left empty per Django convention (msgid is English).

### 1.4 Automated completeness checks (new CI gate)

A new test module enforces the multilingual Definition of Done on every fast-gate
run as part of CI:

| Test | Checks | Location |
|---|---|---|
| `test_no_hardcoded_visible_text` | Scans public/seller-facing templates for visible text not wrapped in `{% trans %}` | `apps/ads/tests/test_i18n_completeness.py` |
| `test_extraction_completeness` | Every `{% trans %}` / `{{ _("...") }}` msgid exists in all 3 `.po` files | same |
| `test_no_empty_msgstr` | `ru` and `bs` have 0 empty `msgstr` for non-header entries | same (reuses existing parser) |
| `test_mo_compiled` | `.mo` files exist for all 3 locales | same (reuses existing parser) |

**Implementation details:**
- All four tests are marked `@pytest.mark.unit` (fast gate, no database).
- No new third-party dependencies: reuses the existing custom `_parse_po_entries`
  parser (no `polib`).
- Template-text scanning uses stdlib `re` regex — strips skip tags (`<script>`,
  `<style>`, `<head>`, `<code>`, etc.), HTML comments, Django comments
  (`{# ... #}` and `{% comment %}...{% endcomment %}`), and all trans-wrapped
  blocks (inline `{% trans "..." %}`, block `{% trans %}...{% endtrans %}`,
  `{% blocktrans %}...{% endblocktrans %}`, and `{{ _("...") }}` gettext calls)
  before scanning for remaining bare text nodes via `>([^<]+)<`.
- Non-translatable tokens (ISO currency codes EUR/RSD/BAM) and pure-punctuation
  or digit-only text nodes are skipped.
- Scan scope is limited to public/seller-facing templates (excludes `admin/`
  staff subtree, `analytics/moderation_dashboard.html`, and
  `components/feature_tag.html` which uses DB-based i18n).

### 1.5 CI integration

A dedicated `i18n` job was added to `.github/workflows/ci.yml`, running parallel
to the existing `build`, `test`, `lint`, `typecheck`, and `lint-templates` jobs.
It runs `compilemessages` before invoking the completeness test suite, ensuring
`.mo` files (gitignored) are present in CI.

---

## 2. What was broken (now fixed)

| Gap | Fix |
|---|---|
| All `msgstr` values empty | `ru` and `bs` msgstr populated; `en` follows Django convention |
| Hardcoded visible strings in templates | All public/seller-facing templates wrapped in `{% trans %}`; `{% load i18n %}` added where missing |
| No `gettext` in Python | 15 strings wrapped with `gettext`/`gettext_lazy` across 6 files |
| No automated completeness checking | `test_i18n_completeness.py` with 4 guard tests + dedicated CI job |
| Inline JS labels hardcoded in Cyrillic | 5 labels in `header_catalog.html` now sourced from pre-translated context variables (`catalog_js_labels`) |

---

## 3. Recommended Workflow

```
1. Tag strings in templates/Python with {% trans %} / {% blocktrans %} / gettext_lazy()
2. make makemessages                              → refreshes all .po files
3. Edit .po files: fill msgstr values for each language (ru/bs non-empty; en empty)
4. make compilemessages                         → generates .mo files
5. At runtime: translation.activate(lang) + gettext() reads .mo catalogs under LOCALE_PATHS
6. Verify: make test (includes test_i18n_completeness.py)
```

Key facts:
- `makemessages` scans **all** template directories from `TEMPLATES` config
  (both `DIRS` and `APP_DIRS`), so included partials are extracted.
- `compilemessages` requires the `msgfmt` binary from the `gettext` package —
  installed in both the Dockerfile builder and runtime/entrypoint stages.
- `.mo` files are **not** in version control (`.gitignore` line 55) — they are
  build-time artifacts compiled from `.po`.
- The CI `i18n` job runs `compilemessages` before `pytest` to ensure `.mo` files
  are available for the completeness and rendering tests.

## 4. Template-linting note

`djlint` (`make lint-templates`) is a style/syntax linter — it cannot detect
hardcoded visible text. Translation completeness is enforced by the
`test_i18n_completeness.py` test suite, not by djlint. The custom `H901` rule
(multi-line `{# ... #}` comment detection) remains the only translation-aware
djlint rule.
