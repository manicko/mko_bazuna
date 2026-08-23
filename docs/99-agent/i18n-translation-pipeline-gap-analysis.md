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

**Date:** 2026-08-23
**Project:** Mko Bazuna (Django 5.2 LTS, HTMX MPA, Docker, PostgreSQL 18)
**Confidence:** HIGH (all findings verified against source code)

> **Status: This analysis is outdated (pre-August 2026).** The pipeline
> infrastructure described in §1.2 as broken has since been fixed. See the
> updated Current State below. For the full multilingual Definition of Done,
> refer to `.ai/problems/08_multilingual-dev_spec.md`.

---

## 1. Current State (Updated — August 2026)

### 1.1 What works

The **static UI string** translation pipeline infrastructure is now complete
and operational — the original Gaps 1, 4, and 5 have been fixed:

| Component | File | Status |
|---|---|---|
| Custom middleware (single authority) | `src/backend/apps/core/middleware/language.py` | ✅ `translation.activate(lang)` called; `request.LANGUAGE_CODE` set; cookie + `lang` param support |
| `USE_I18N = True` | `config/settings/base.py:56` | ✅ |
| `LANGUAGES` (ru/bs/en) | `config/settings/base.py:57-61` | ✅ |
| `LANGUAGE_CODE = "ru"` | `config/settings/base.py:55` | ✅ |
| `LOCALE_PATHS` | `config/settings/base.py:62` | ✅ → `src/backend/locale/` |
| `compilemessages` in Dockerfile builder | `docker/Dockerfile:78` | ✅ Added — compiles `.mo` at image build |
| `compilemessages` in entrypoint | `docker/entrypoint.sh:73-87` | ✅ Added — compiles for dev bind-mounts |
| `compilemessages` in test entrypoint | `docker/entrypoint-test.sh:37` | ✅ Added — compiles for test bind-mounts |
| Makefile targets | `Makefile:146-150` | ✅ `makemessages` and `compilemessages` targets added |
| `i18n` context processor | `config/settings/base.py:138` | ✅ `django.template.context_processors.i18n` |
| JSON-based ad content i18n | `apps/ads/models.py` (`get_title`/`get_description`) | ✅ `title_i18n` JSONB → fallback chain |
| JSON-based lookup i18n | `apps/lookups/models.py` (`LookupItem.get_name`) | ✅ `name_i18n` JSONB |
| `feature_tag` template filter | DB-based i18n for feature tags | ✅ Already uses `get_lookup_name` |

The end-to-end language tests confirm that **ad content** and **lookup data**
(categories, cities, features) switch correctly between ru, bs, and en. The
`header_catalog.html` template already has `{% load i18n %}` and wraps several
strings in `{% trans %}` (e.g., `{% trans "Categories" %}`,
`{% trans "Preferred city" %}`, `{% trans "Expand" %}`, `{% trans "Close" %}`).

### 1.2 What is still broken

#### Gap 1: All `msgstr` values are still empty

The three `.po` files (`src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`)
contain **39 msgid entries** (38 translatable + 1 header), but **every `msgstr`
is empty** (`msgstr ""`). Even with `.mo` files compiled, `gettext()` returns
the msgid (English) for all languages. No actual translation has been authored.

#### Gap 2: Hardcoded visible strings in templates

Many user-visible strings in templates are **not wrapped in `{% trans %}`**:

- `header_catalog.html` — 6 hardcoded Russian strings + 5 inline JS labels
- `header.html` — 5 hardcoded English labels (Cabinet, Dashboard, Admin, Logout, Login)
- `breadcrumb.html` — 2 hardcoded Russian strings + missing `{% load i18n %}`
- `consent_banner.html` — 3 hardcoded checkbox labels (Essential, Analytics, Preferences)
- `dashboard.html`, `edit.html`, `login_issue.html` — multiple English strings, no `{% load i18n %}`
- 12 templates total lack `{% load i18n %}` entirely

These strings are **not in the `.po` files** because `makemessages` only extracts
wrapped `{% trans %}` / `{{ _("...") }}` strings. After wrapping them, a fresh
`makemessages` run will add ~62 new msgids to the catalogs.

#### Gap 3: No automated translation-completeness checking

The existing `test_i18n_pipeline.py` (5 tests, all `@pytest.mark.unit`) checks:
- `.po` files exist for all languages
- No empty `msgstr` (currently **fails** because all msgstr are empty)
- `.mo` files exist

It does **NOT** check:
- Hardcoded visible text in templates
- Extraction completeness (whether all `{% trans %}` strings have `.po` entries)
- Cross-language msgstr consistency

There is no CI job for i18n. The `lint` and `test` jobs do not run translation
completeness checks.

---

## 2. Best Practices for Django i18n in Dockerized HTMX MPA

Verified against [Django docs](https://docs.djangoproject.com/en/6.0/topics/i18n/translation/) and community best practices (datamade, Lokalise, i18nagent):

### 2.1 Standard workflow

```
1. Tag strings in templates/Python with {% trans %} / {% blocktrans %} / gettext_lazy()
2. django-admin makemessages -l ru -l bs -l en   →  updates .po files
3. Edit .po files: fill msgstr values for each language
4. django-admin compilemessages                →  generates .mo files
5. At runtime: translation.activate(lang) + gettext() reads .mo catalogs
```

Key facts verified:
- `makemessages` scans **all** template directories from `TEMPLATES` config (both `DIRS` and `APP_DIRS`), so included partials are extracted.
- `compilemessages` requires the `msgfmt` binary from the `gettext` package — installed in both Dockerfile builder and runtime stages.
- `translation.activate(lang)` in the middleware correctly sets the thread-local active language. When `{% trans %}` renders, Django's `gettext()` looks up the msgid in the active language's `.mo` file via `LOCALE_PATHS`.
- `.mo` files should **not** be in version control (standard practice; already `.gitignore`d). They are build/deploy artifacts compiled from `.po`.

### 2.2 Docker integration pattern

| Environment | Bind-mount? | Compile point |
|---|---|---|
| Production (web/bot) | No — source COPY'd into image | **Dockerfile build stage** |
| Development | Yes — `.:/app` bind mount | **entrypoint.sh** |
| Test | Yes — `.:/app` bind mount | **entrypoint-test.sh** |

Rationale: bind mounts override the image's filesystem, so `.mo` files baked into the image are invisible in dev/test. Compiling in the entrypoint covers all cases.

### 2.3 Why `.mo` compilation is safe and fast

- `compilemessages` is idempotent and fast (< 1s for 3 languages).
- Running it in the entrypoint on every container start adds negligible overhead.
- For production, compiling in the Dockerfile layer means it runs once at image build time.

---

## 3. Feasible Approaches

### Approach A (Recommended): Complete the standard Django i18n pipeline

**What it does:**
1. Wrap all user-visible strings in `{% trans %}` / `gettext_lazy()`.
2. Run `makemessages -l ru -l bs -l en` to extract ALL strings.
3. Fill in `msgstr` values for Russian, Bosnian, and English.
4. Compile `.mo` files (already done at build/entrypoint).
5. Add automated completeness checking to CI.

**Pros:**
- Uses the **standard Django i18n toolchain** — the pipeline infrastructure is now in place.
- Handles **all** static UI strings, not just existing ones — future-proof.
- `.po` files under version control, `.mo` files compiled at build — the standard Django pattern.
- No custom infrastructure or new models required.
- Well-understood by Django developers.
- Translation tools (Poedit, Lokalise, Rosetta) all understand `.po` files.

**Cons:**
- `.po` files must be maintained when templates change (requires re-running `makemessages`).
- Translations must be authored (or machine-translated + reviewed) for each `msgstr`.

### Approach B: Move static UI labels into JSON-based translation tables

**What it does:** Create a new model (e.g., `UITranslation`) with a JSONB `translations` field, populate it with the UI labels, and render via a new template tag (mirroring the existing `get_lookup_name` pattern).

**Pros:**
- Bypasses `.po`/`.mo` entirely for UI strings.
- Translations editable via Django Admin without code deploy.
- Consistent with the existing `name_i18n` JSONB pattern for lookup items.

**Cons:**
- **Over-engineered** for static UI labels — requires a new model, migration, admin, seeder, template tag, and DB row management.
- **Does not fix the existing pipeline** — all `{% trans %}` strings would still be untranslated. The `.po` files and middleware infrastructure would remain incomplete.
- Creates a **second parallel i18n system** (JSON-based for some strings, gettext for others), which is confusing.
- Requires a database round-trip per render (vs. gettext's in-memory catalog lookup).

### Approach C (Hybrid): Manually add strings to .po, don't fix completeness

**What it does:** Add missing `msgid` entries to the `.po` files manually, fill in translations, but don't add automated completeness checking.

**Cons:**
- **No automated guard** — hardcoded strings will reappear in future templates without detection.
- Doesn't fix the pipeline for future strings or other templates.
- Partial solution that leaves the infrastructure unenforced.

### Recommendation

**Choose Approach A.** The standard Django i18n pipeline is the correct fix.
The infrastructure is already in place — just needs the final pieces
(`.po` completion + automated completeness checking). Refer to
`.ai/problems/08_multilingual-dev_spec.md` for the full implementation plan.

---

## 4. Build / Entrypoint Status (Already Done)

| File | Change | Status |
|---|---|---|
| `docker/Dockerfile` (builder stage) | Add `gettext` to apt install; add `RUN ... compilemessages` | ✅ Done (line 78) |
| `docker/entrypoint.sh` | Add `compile_messages()` function + call before `exec "$@"` | ✅ Done (lines 73-87) |
| `docker/entrypoint-test.sh` | Add `compilemessages` call before pytest | ✅ Done (line 37) |
| `Makefile` | Add `makemessages` and `compilemessages` targets | ✅ Done (lines 146-150) |
| `*.po` files (3 languages) | Populate `msgstr` for all msgids | ⏳ Pending |

---

## 5. Recommended Implementation Sequence

1. **Wrap all user-visible strings** in `{% trans %}` / `gettext_lazy()` across all templates and Python files. (See `.ai/problems/08_multilingual-dev_spec.md` §3 for the full inventory.)
2. **Re-extract strings** — run `make makemessages` to regenerate all `.po` files with every `{% trans %}` string.
3. **Fill translations** — populate `msgstr` for `ru`, `bs`, `en` for all entries.
4. **Verify** — run `make test` and confirm that `{% trans "..." %}` renders correctly in each language.
5. **Add automated completeness checking** — new `test_i18n_completeness.py` tests (per spec §5) + CI job.

---

## 6. Key Technical Detail

The `LanguagePreMiddleware` is **already correct** — it calls `translation.activate(lang)`, which sets the thread-local active language. At template render time, Django's `{% trans "string" %}` calls `gettext("string")`, which looks up the string in the active language's `.mo` file under `LOCALE_PATHS`. **If a `.mo` file exists and contains the translation, it works. If no `.mo` file exists, `gettext` returns the msgid unchanged (English).**

This is why the JSON-based `name_i18n` translations (lookup items) work today — they don't use gettext at all; they use a custom `get_name(locale)` method that reads from the JSONB field. The `{% trans %}` strings don't work yet because while `.mo` files are compiled, the `.po` catalogs have empty `msgstr` values and many strings are not yet wrapped in `{% trans %}`.
