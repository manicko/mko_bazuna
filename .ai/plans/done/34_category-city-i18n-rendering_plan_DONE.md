---
id: 34_category-city-i18n-rendering
spec: .ai/problems/09_category-city-i18n_rendering_spec.md
domain: implementation-plan
spec_status: Approved
priority: High
status: Ready for implementation (after RQ1–RQ3 research)
date: 2026-08-24
stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX 1.9.12 · vanilla JS · aiogram 3.x
source_spec: ".ai/problems/09_category-city-i18n_rendering_spec.md"
---

# Plan 34 — Category & City Names Not Rendered in Selected Language

Transformation of **Spec 09** (`09_category-city-i18n_rendering_spec.md`, Approved) into a
dependency-aware implementation DAG.

> **Root cause:** `Category.get_name()` and `City.get_name()` default to `locale="ru"`.
> Twenty-four template call sites invoke `{{ obj.get_name }}` (no argument), so the
> default Russian is always used regardless of the selected UI language. The same issue
> affects the autocomplete entity-suggestions service (raw `.name` + `get_name()` without
> locale), the submenu fragment cache (no language in the key), the Telegram alert message
> builder, and the admin moderation review page.

> **Fix strategy:** Mirror the existing `get_lookup_name` template-filter pattern — add
> `get_category_name:LANGUAGE_CODE` and `get_city_name:LANGUAGE_CODE` filters — and
> propagate `LANGUAGE_CODE` through every data path that renders Category/City names.

The spec's seven conceptual tasks (§5) plus the PO decisions (§7) are reorganized below into
sixteen tasks (3 research + 8 implementation/test + 2 verification) optimized for
**dependency safety, parallel execution, and independent reviewability**.

---

## 1. Statement of Scope

**In scope:**

- *Template tags* — add two filters (`get_category_name`, `get_city_name`) to
  `apps/core/templatetags/localized_content.py`, mirroring the existing `get_lookup_name`.
- *Templates* — replace 24 `{{ obj.get_name }}` call sites across 9 templates with the new
  filters, including adding `{% load localized_content %}` where missing and removing
  redundant `|default:` clauses.
- *Autocomplete service* — add an optional `locale` parameter to `get_entity_suggestions`
  and `_category_path`; thread `request.LANGUAGE_CODE` from the autocomplete view.
- *Submenu cache* — add the active locale to the `category_submenu` fragment-cache key.
- *Admin moderation UI* — localize `review.html` category/city names via the new filters;
  add a language selector that leverages the existing `LanguagePreMiddleware`.
- *Telegram alerts* — add a `User.telegram_language` field (Option A, per RQ3); localize
  `build_alert_message` in `immediate_alerts.py`.
- *Tests* — extend `test_i18n_completeness.py` to flag bare `{{ obj.get_name }}` calls;
  add regression tests for web UI, submenu cache, admin UI, and Telegram alert payloads.
- *Verification* — `make test` fast gate + `ruff check` + `basedpyright` on changed files.

**Explicitly out of scope (per Spec §12):**

- `.po`/`.mo` regeneration — no new user-visible message strings are added; the
  translations already exist in the `name_i18n` JSONField (F2/F3).
- LookupItem localization — already correct via `get_lookup_name` (F5).
- Bot-side FSM ad-creation dialog — Russian-only per Spec §12.
- `SearchView` fuzzy matching — already locale-aware (F7); must not be broken (REQ-09.8).
- Template string **extraction** (the `{{ obj.get_name }}` pattern is a method call, not a
  gettext msgid — Spec §12 Task 1).

---

## 2. Research Findings (RQ1–RQ3)

Three open questions from Spec §11 are resolved below. RQ1 and RQ2 were answered by
direct code analysis; RQ3 was resolved by the Researcher agent (confirmed Option A).

| # | Question | Finding | Source |
|---|----------|---------|--------|
| **RQ1** | Does frontend JS filter autocomplete suggestions by `text`/`label`? (R3 risk) | **No.** The dropdown JS in `header_catalog.html` (`render()` function) filters by `s.type === section \|\| s.source === section` — never by text content. Navigation uses `s.slug` (`/city/<slug>/`, `/category/<slug>/`); `text` is used only for display (`escapeHtml(s.text)`). **Conclusion: translating entity suggestion labels is safe.** | `templates/components/header_catalog.html:216-237` |
| **RQ2** | Are there callers of `get_entity_suggestions` besides `autocomplete.py:72`? (R4 risk) | **Yes — 11 test callers.** Grep across the repo: 1 production caller (`autocomplete.py:72`) + 11 test callers in `test_autocomplete.py` (lines 424, 431, 437, 443, 449, 450, 454, 468, 478, 483, 490), all invoking `get_entity_suggestions(prefix)` without locale. **Conclusion: the `locale` parameter must be optional with a `"ru"` default for backward compatibility.** | `apps/search/tests/test_autocomplete.py` |
| **RQ3** | How to persist the Telegram user's language preference? (A6, Open Q3) | **Option A: `User.telegram_language` CharField.** The `User` model has no language field. Precedent: `User.preferred_city` (direct field). The alert delivery path already `select_related("user")`, so the field is a free attribute access. A separate `BotUserPreference` model is over-engineering (YAGNI) — the `trust` app's `OneToOneField` models are multi-field bounded contexts, not a valid precedent for a single value. **Field spec:** non-nullable `CharField(max_length=5, choices=[(loc.value, loc.value) for loc in LanguageLocale], default=LanguageLocale.RUSSIAN.value)`, backfilled to `"ru"`. | `apps/users/models.py`; Researcher agent (ses_fcaa667b5ffe9uICsBsMfmE91w) |

> **Gate for risky tasks:** T-02 (entity suggestions) is blocked until RQ1+RQ2 complete (the
> JS-safety and caller-audit findings inform the `locale`-param design). T-06 (Telegram
> field) and T-07 (immediate_alerts) are blocked until RQ3 completes (field design).
> Implementation may proceed only after research recommends **Go**.

---

## 3. Execution DAG

```mermaid
flowchart TD
    subgraph G0 ["G0 — parallel, no prerequisites"]
        RQ1[RQ1: Research frontend JS<br/>filtering behavior]
        RQ2[RQ2: Research all callers<br/>of get_entity_suggestions]
        RQ3[RQ3: Research Telegram<br/>language persistence → Option A]
        T01[T-01: Add get_category_name<br/>+ get_city_name filters]
        T03[T-03: Add language<br/>to submenu cache key]
    end

    subgraph G1 ["G1 — after G0 findings"]
        T02[T-02: Entity suggestions<br/>locale param + caller]
        T04[T-04: Replace 24 get_name<br/>call sites in 9 templates]
        T05[T-05: Admin UI localization<br/>+ language selector]
        T06[T-06: Add User.telegram_language<br/>field + migration + bot menu]
    end

    subgraph G2 ["G2 — after G1"]
        T07[T-07: Localize immediate_alerts.py<br/>alert messages]
        T08[T-08: Regression test — web UI<br/>+ submenu + admin]
        T09[T-09: Update entity suggestions<br/>tests for locale]
        T10[T-10: Update i18n completeness<br/>test to flag .get_name]
        T11[T-11: Regression test —<br/>Telegram alert payloads]
    end

    subgraph G3 ["G3 — verification gates"]
        T12[T-12: Verify web UI i18n fix<br/>(make test + lint + typecheck)]
        T13[T-13: Verify admin + Telegram<br/>alerts i18n]
    end

    RQ1 --> T02
    RQ2 --> T02
    RQ3 --> T06
    RQ3 --> T07
    T01 --> T04
    T01 --> T05
    T01 --> T10
    T03 --> T08
    T03 --> T12
    T04 --> T08
    T04 --> T10
    T05 --> T08
    T02 --> T09
    T06 --> T07
    T07 --> T11
    T04 --> T12
    T02 --> T12
    T08 --> T12
    T09 --> T12
    T10 --> T12
    T06 --> T13
    T07 --> T13
    T05 --> T13
    T08 --> T13
    T11 --> T13
```

**Parallel groups:**

- **G0** `{RQ1, RQ2, RQ3, T-01, T-03}` — three research questions run alongside two independent
  implementation tasks. T-01 (filters) and T-03 (cache key) touch disjoint files from
  everything else.
- **G1** `{T-02, T-04, T-05, T-06}` — all unblocked by G0; each depends on different G0
  outputs (T-02 on research, T-04/T-05 on filters, T-06 on RQ3 recommendation).
- **G2** `{T-07, T-08, T-09, T-10, T-11}` — dependent implementation and test tasks; T-07
  on Telegram field, tests on their respective implementation tasks.
- **G3** `{T-12, T-13}` — final verification gates; T-12 covers the web UI path, T-13
  covers admin + Telegram.

**Critical path:** `RQ1+RQ2 → T-02 → T-09 → T-12` (entity suggestions → their tests → verify)
and `T-01 → T-04 → T-08 → T-12` (filters → templates → regression → verify).

---

## 4. Risk Assessment

| Task | Risk | Why it is risky | Mitigation |
|------|------|-----------------|------------|
| RQ1 | — | Research, no code change | Confirms JS-safety finding before T-02 |
| RQ2 | — | Research, no code change | Confirms caller audit; informs `locale` param default |
| RQ3 | — | Research, no code change | Researcher confirmed Option A (direct field) |
| T-01 (filters) | **Low** | Additive code; follows existing `get_lookup_name` pattern | None needed — mirror existing filter |
| T-02 (entity suggestions) | **Medium** | R4: adding `locale` param could break callers; 11 test callers found (RQ2) | Make `locale` optional with default `"ru"` — backward compatible |
| T-03 (cache key) | **Medium** | R2: thundering herd on cache miss; shared cache key format | Acceptable per A5 (TTL 300s; one miss per key/locale) |
| T-04 (templates) | **Medium** | R1: removing `\|default` could break None-safety | Filter handles None internally; keep `\|default:"—"` for visual placeholders |
| T-05 (admin) | **Medium** | Behavior change for staff-only views; new language selector UI | Reuse existing `LanguagePreMiddleware` (`?lang=` links); no new backend logic |
| T-06 (Telegram pref) | **High** | Schema migration (new `User.telegram_language` field) | Simple `AddField` migration; backfill with `"ru"`; researcher confirmed low risk |
| T-07 (immediate_alerts) | **High** | Alert delivery path (idempotent `on_commit` → daemon thread) | Idempotent delivery unaffected; tests cover payload structure |
| T-08 (regression tests) | Low | Test-only | — |
| T-09 (entity tests) | Low | Test-only | — |
| T-10 (i18n test) | Low | Test-only; extends existing guard | Scan is additive (new test method); scoped to `.get_name` regex |
| T-11 (Telegram test) | Low | Test-only | — |
| T-12 (verify web) | — | Verification gate | `make test` + `ruff` + `basedpyright` |
| T-13 (verify admin+telegram) | — | Verification gate | `make test` for moderation + telegram test suites |

**Shared-config / startup / schema risk:** T-06 introduces a schema migration. No other
tasks change shared configuration, build, deployment, startup behavior, or test
infrastructure. The submenu cache-key change (T-03) is a format change, not a config key —
old entries simply become unreachable (TTL 300s expiry).

---

## 5. Task Index

| ID | Title | Type | Priority | Risk | Blocked by |
|----|-------|------|----------|------|------------|
| **RQ1** | Research: frontend JS autocomplete filtering behavior | research | High | — | — |
| **RQ2** | Research: audit all callers of `get_entity_suggestions` | research | Medium | — | — |
| **RQ3** | Research: Telegram user-language preference persistence | research | High | — | — |
| **T-01** | Add `get_category_name` + `get_city_name` template filters | implementation | High | Low | — |
| **T-02** | Add `locale` param to entity suggestions + update caller | implementation | High | Medium | RQ1, RQ2 |
| **T-03** | Add language dimension to submenu cache key | implementation | Medium | Medium | — |
| **T-04** | Replace 24 `get_name` call sites in 9 templates | implementation | High | Medium | T-01 |
| **T-05** | Admin moderation UI localization + language selector | implementation | High | Medium | T-01 |
| **T-06** | Add `User.telegram_language` field + migration + bot menu | implementation | High | High | RQ3 |
| **T-07** | Localize `immediate_alerts.py` alert messages | implementation | High | High | T-06, RQ3 |
| **T-08** | Regression test — web UI + submenu + admin localization | test | High | Low | T-03, T-04, T-05 |
| **T-09** | Update entity suggestions tests for locale-awareness | test | Medium | Low | T-02 |
| **T-10** | Update i18n completeness test to flag `{{ obj.get_name }}` | test | High | Low | T-04 |
| **T-11** | Regression test — Telegram alert payload localization | test | Medium | Low | T-07 |
| **T-12** | Verify: web UI i18n fix (`make test` + lint + typecheck) | verification | High | — | T-01,T-02,T-03,T-04,T-08,T-09,T-10 |
| **T-13** | Verify: admin + Telegram alerts i18n | verification | High | — | T-05,T-06,T-07,T-08,T-11 |

---

## 6. Task Specifications

> Format follows `.ai/tasks/templates/task_template.yaml`. `depends_on` / `blocked_by`
> lists the IDs a task cannot start without. Semantic anchors (functions, classes,
> template files) are used — never line numbers.

---

### RQ1 — Research: Frontend JS autocomplete client-side filtering

| Field | Value |
|-------|-------|
| ID | RQ1 |
| Title | Research: does frontend JS filter autocomplete by `text`/`label`? |
| Type | research |
| Priority | High |
| Risk | — (no code change) |
| Blocked by | — |
| Source | Spec §11 Open Q1 (R3 risk) |

**description**

Investigate whether the JavaScript in `header_catalog.html` / `save_search_modal.html`
performs client-side filtering of autocomplete suggestions against the `label`/`text` field.
If it does, translating entity suggestion labels to BS/EN could break the matching UX
(R3). The finding gates T-02 (entity suggestions locale).

**goals**
- Determine whether any client-side JS filters, sorts, or matches on the `text` field of
  autocomplete suggestions.
- If no client-side text filtering exists, confirm translating `text` is safe.
- If filtering exists, recommend a mitigation (e.g., keep `text` in the request language
  or add a separate `match_text` field).

**files**
- `templates/components/header_catalog.html` — targets: the `render(json)` function and
  the `dropdown.addEventListener('click', ...)` handler.
- `templates/search/partials/save_search_modal.html` — targets: any inline JS that
  filters on suggestion text.

**changes**
- action: none (research finding recorded in this plan §2)

**acceptance_criteria**
- Confirmation that frontend JS filters by `type`/`source` (not `text`), or a documented
  mitigation if text filtering is found.

---

### RQ2 — Research: Audit all callers of `get_entity_suggestions`

| Field | Value |
|-------|-------|
| ID | RQ2 |
| Title | Research: audit all callers of `get_entity_suggestions` across the codebase |
| Type | research |
| Priority | Medium |
| Risk | — (no code change) |
| Blocked by | — |
| Source | Spec §11 Open Q2 (R4 risk) |

**description**

Grep the entire codebase (production + tests) for all invocations of
`get_entity_suggestions`. The spec's F4 claims only `autocomplete.py:72` calls it, but
preliminary analysis suggests test files also call it directly. The finding determines
whether adding a `locale` parameter is safe or requires updating existing callers.

**goals**
- Enumerate every caller of `get_entity_suggestions` (production + test).
- Confirm whether existing callers pass only `(prefix)` or also `(prefix, limit)`.
- Recommend whether `locale` should be an optional parameter (backward-compatible) or
  required (requires updating all callers).

**files**
- `apps/search/services/entity_suggestions.py` — the function definition.
- `apps/search/views/autocomplete.py` — the production caller.
- `apps/search/tests/test_autocomplete.py` — test callers.

**changes**
- action: none (research finding recorded in this plan §2)

**acceptance_criteria**
- Complete caller list. Recommendation: `locale` must be optional with default `"ru"`.

---

### RQ3 — Research: Telegram user-language preference persistence

| Field | Value |
|-------|-------|
| ID | RQ3 |
| Title | Research: how to persist Telegram user's preferred interface language |
| Type | research |
| Priority | High |
| Risk | — (no code change) |
| Blocked by | — |
| Source | Spec §11 Open Q3 (A6, PO Decision §7.1) |

**description**

The `User` model (`apps/users/models.py`) has no language preference field. Determine the
best persistence approach for the Telegram bot user's preferred language (RU/BS/EN):
Option A (new `User.telegram_language` CharField) or Option B (separate
`BotUserPreference` 1:1 model). The finding gates T-06 (Telegram language preference
feature) and T-07 (immediate_alerts localization).

**goals**
- Catalog current `User` fields and any existing language/state patterns.
- Compare Option A vs Option B for this Django+aiogram stack (schema complexity, query
  overhead in the alert delivery path, `select_related` implications, migration risk).
- Recommend one option with field type, null/blank/default strategy, and migration
  approach.
- Identify how the bot handler would read/write the preference (sync_to_async patterns).

**files**
- `apps/users/models.py` — `User` model.
- `apps/search/services/immediate_alerts.py` — alert delivery path (already
  `select_related("user")`).
- `src/telegram_bot/handlers/login.py` — user lookup pattern (`@sync_to_async`).
- `src/telegram_bot/handlers/ad_create.py` — existing `@sync_to_async` write pattern.
- `apps/core/enums.py` — `LanguageLocale` enum (RU="ru", BS="bs", EN="en").

**changes**
- action: none (research finding recorded in this plan §2)

**acceptance_criteria**
- Clear recommendation with justification. **Result: Option A confirmed** —
  `User.telegram_language` CharField, non-nullable, `default=LanguageLocale.RUSSIAN.value`.

---

### T-01 — Add `get_category_name` and `get_city_name` template filters

| Field | Value |
|-------|-------|
| ID | T-01 |
| Title | Add `get_category_name` and `get_city_name` template filters |
| Type | implementation |
| Priority | High |
| Risk | Low |
| Blocked by | — |
| Source | Spec §5 Task 1 (PO Decision §7.3: two named filters) |

**description**

Add two new template filters to `apps/core/templatetags/localized_content.py`, mirroring
the existing `get_lookup_name` filter (which delegates to `LookupItem.get_name(locale)`).
Each filter calls the corresponding model's `get_name(locale)` method, which already
implements the fallback chain: requested locale → `ru` → raw `name` (F1, REQ-09.3).

The filters must handle `None` objects internally (returning `""`) to replace the
`|default:` None-safety that currently guards some call sites (R1). This means
`{{ ad.city|get_city_name:LANGUAGE_CODE }}` is safe even when `ad.city` is `None`.

**goals**
- `get_category_name(category, locale="ru")` → `category.get_name(locale=locale)`,
  returns `""` if `category is None`.
- `get_city_name(city, locale="ru")` → `city.get_name(locale=locale)`, returns `""` if
  `city is None`.
- Both follow the exact docstring/style convention of `get_lookup_name`.
- `StrEnum` (`LanguageLocale`) is not needed here — the filters accept a plain `str` locale
  (same as `get_title`/`get_description`/`get_lookup_name` already do).

**files**
- `apps/core/templatetags/localized_content.py`
  - targets: `register` (the `template.Library()` instance), end of file after
    `get_lookup_name`.
  - semantic_anchors:
    - `insert_after: def get_lookup_name` — place the two new filters immediately after
      the existing `get_lookup_name` filter (grouping all localized-content filters).
    - The new filters mirror `get_lookup_name`'s delegation to `obj.get_name(locale=locale)`.

**changes**
- action: `add_code` — add `get_category_name` and `get_city_name` filter functions after
  `get_lookup_name`, each with a None-guard:
  ```python
  @register.filter
  def get_category_name(category, locale: str = "ru") -> str:
      if category is None:
          return ""
      return category.get_name(locale=locale)

  @register.filter
  def get_city_name(city, locale: str = "ru") -> str:
      if city is None:
          return ""
      return city.get_name(locale=locale)
  ```

**acceptance_criteria**
- Two new filters registered and callable as `{{ obj|get_category_name:LANGUAGE_CODE }}`
  and `{{ obj|get_city_name:LANGUAGE_CODE }}`.
- Both return `""` for `None` input (replacing the `|default:` None-safety).
- Both delegate to `get_name(locale=locale)` (preserving the locale→ru→name fallback).
- `ruff check` / `ruff format --check` pass on the file.

---

### T-02 — Add `locale` parameter to entity suggestions + update caller

| Field | Value |
|-------|-------|
| ID | T-02 |
| Title | Add `locale` param to `get_entity_suggestions` + `_category_path`; update autocomplete caller |
| Type | implementation |
| Priority | High |
| Risk | Medium (R4: backward compatibility of existing callers) |
| Blocked by | RQ1, RQ2 |
| Source | Spec §5 Task 3 |

**description**

Add an optional `locale: str = "ru"` parameter to `get_entity_suggestions` and the
internal `_category_path` helper in `apps/search/services/entity_suggestions.py`. Replace
raw `cat.name` / `city.name` with `cat.get_name(locale)` / `city.get_name(locale)`. Pass
`locale` through to `_category_path`.

The parameter is **optional with default `"ru"`** (per RQ2: 11 test callers invoke
`get_entity_suggestions(prefix)` without locale — a required parameter would break them).

Update the sole production caller in `autocomplete.py` to pass
`request.LANGUAGE_CODE`.

**goals**
- `get_entity_suggestions(prefix, limit=5, locale="ru")` — new optional param.
- `_category_path(category, locale="ru")` — passes `locale` to each ancestor's
  `get_name(locale)`.
- Category suggestions use `cat.get_name(locale)` instead of `cat.name`.
- City suggestions use `city.get_name(locale)` instead of `city.name`.
- `autocomplete.py` passes `request.LANGUAGE_CODE` to `get_entity_suggestions`.

**files**
- `apps/search/services/entity_suggestions.py`
  - targets: `get_entity_suggestions` (function signature + body), `_category_path`
    (function signature + `get_name()` call on line 31).
  - semantic_anchors:
    - `replace_signature: def get_entity_suggestions` — add `locale: str = "ru"`.
    - `replace_signature: def _category_path` — add `locale: str = "ru"`.
    - `replace_in_body` — replace `item.get_name()` with `item.get_name(locale)`.
    - `replace_in_body` — replace `"text": cat.name` with `"text": cat.get_name(locale)`.
    - `replace_in_body` — replace `"text": city.name` with `"text": city.get_name(locale)`.
- `apps/search/views/autocomplete.py`
  - targets: `autocomplete` function, the `get_entity_suggestions(query)` call.
  - semantic_anchors:
    - `replace_in_body: entity_suggestions = get_entity_suggestions(query)` →
      `get_entity_suggestions(query, locale=request.LANGUAGE_CODE or "ru")`.

**changes**
- action: `replace_signature` — add `locale: str = "ru"` to both functions.
- action: `replace_in_body` — thread `locale` through `get_name()` calls and replace
  raw `.name` access.
- action: `replace_in_body` — update `autocomplete.py` caller to pass
  `request.LANGUAGE_CODE`.

**acceptance_criteria**
- `get_entity_suggestions("тран")` (no locale) returns Russian names (default `"ru"`).
- `get_entity_suggestions("тран", locale="en")` returns English names from
  `name_i18n`.
- `autocomplete.py` passes the request's `LANGUAGE_CODE` to the service.
- Existing `test_autocomplete.py` tests pass unchanged (backward-compatible default).
- `ruff check` / `basedpyright` pass.

---

### T-03 — Add language dimension to submenu cache key

| Field | Value |
|-------|-------|
| ID | T-03 |
| Title | Include active locale in the category_submenu fragment-cache key |
| Type | implementation |
| Priority | Medium |
| Risk | Medium (R2: brief thundering herd on cache miss) |
| Blocked by | — |
| Source | Spec §5 Task 4 (REQ-09.5) |

**description**

The `category_submenu` view caches rendered HTML under the key
`category:submenu:<tree_version>:<slug>` with no language component, causing cross-language
cache bleed (a Russian-rendered submenu is served to a Bosnian user — R5/F9).

Change the cache key to include the active locale:
`category:submenu:<tree_version>:<slug>:<locale>`.

The `LANGUAGE_CODE` is available on the request (set by `LanguagePreMiddleware` at
`core/middleware/language.py`).

**goals**
- Cache key includes `request.LANGUAGE_CODE` (or a normalized locale).
- Old cache entries (without locale) become unreachable — TTL is 300s, so stale entries
  expire within 5 minutes (A5).
- No structural changes to `SUBMENU_CACHE_TTL`, `get_tree_version()`, or `bump_tree_version()`.

**files**
- `apps/categories/views.py`
  - targets: `category_submenu` function, the `cache_key` assignment.
  - semantic_anchors:
    - `replace_in_body: cache_key = f"category:submenu:{get_tree_version()}:{category.slug}"`
      → `cache_key = f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"`.
- `apps/categories/cache.py`
  - targets: docstring reference to the cache key format (line 5 of module docstring).
  - semantic_anchors:
    - `replace_in_body` — update the docstring comment `category:submenu:<tree_version>:<slug>`
      to `category:submenu:<tree_version>:<slug>:<locale>`.

**changes**
- action: `replace_in_body` — add `:{locale}` segment to the cache key in `views.py`.
- action: `replace_in_body` — update the docstring in `cache.py` to reflect the new key
  format.

**acceptance_criteria**
- Cache key includes the locale segment.
- Different languages produce different cache keys (verified by T-08 regression test).
- `categories/cache.py` and `categories/views.py` unchanged in structure (only the key
  string and its docstring).
- `ruff check` / `basedpyright` pass.

---

### T-04 — Replace 24 `get_name` call sites in 9 templates with new filters

| Field | Value |
|-------|-------|
| ID | T-04 |
| Title | Replace all `{{ obj.get_name }}` call sites with `get_category_name`/`get_city_name` filters |
| Type | implementation |
| Priority | High |
| Risk | Medium (R1: None-safety when removing `|default`) |
| Blocked by | T-01 |
| Source | Spec §5 Task 2; Spec §6 Affected Assets |

**description**

Replace all 24 `{{ obj.get_name }}` call sites across 9 template files with the new
`{{ obj|get_category_name:LANGUAGE_CODE }}` (for Category objects) or
`{{ obj|get_city_name:LANGUAGE_CODE }}` (for City objects) filters from T-01.

For call sites wrapped in `|default:obj.name` (data-fallback pattern), remove `|default`
entirely — the filter's `get_name()` fallback chain (locale→ru→name) handles it.

For call sites wrapped in `|default:"—"` (visual placeholder pattern), keep the
`|default:"—"` after the filter: `{{ obj|get_city_name:LANGUAGE_CODE|default:"—" }}`.

**goals**
- All 24 call sites converted (see table below for exact mapping).
- `{% load localized_content %}` added to all templates that lack it (7 of 9).
- No `|default:obj.name` redundancy remains.
- `|default:"—"` visual placeholders preserved where applicable.

**call site mapping:**

| Template | Object type | Current | Replacement |
|----------|-------------|---------|-------------|
| `components/header_catalog.html:65` | City (`city`) | `{{ city.get_name }}` | `{{ city\|get_city_name:LANGUAGE_CODE }}` |
| `components/header_catalog.html:78` | Category (`current_cat`) | `{{ current_cat.get_name }}` | `{{ current_cat\|get_category_name:LANGUAGE_CODE }}` |
| `components/header_catalog.html:92` | Category (`cat`) | `{{ cat.get_name }}` | `{{ cat\|get_category_name:LANGUAGE_CODE }}` |
| `components/header_catalog.html:98` | Category (`cat`) | `aria-label="{% trans "Expand" %} {{ cat.get_name }}"` | `aria-label="{% trans "Expand" %} {{ cat\|get_category_name:LANGUAGE_CODE }}"` |
| `components/header_catalog.html:159` | Category (`cat`) | `{{ cat.get_name }}` | `{{ cat\|get_category_name:LANGUAGE_CODE }}` |
| `components/header_catalog.html:165` | Category (`cat`) | `aria-label="{% trans "Expand" %} {{ cat.get_name }}"` | `aria-label="{% trans "Expand" %} {{ cat\|get_category_name:LANGUAGE_CODE }}"` |
| `components/breadcrumb.html:16` | Category (`ancestors.0`) | `{{ ancestors.0.get_name }}` | `{{ ancestors.0\|get_category_name:LANGUAGE_CODE }}` |
| `components/breadcrumb.html:21` | Category (`last_ancestor`) | `{{ last_ancestor.get_name }}` | `{{ last_ancestor\|get_category_name:LANGUAGE_CODE }}` |
| `components/breadcrumb.html:24` | Category (`breadcrumb_category`) | `{{ breadcrumb_category.get_name }}` | `{{ breadcrumb_category\|get_category_name:LANGUAGE_CODE }}` |
| `components/breadcrumb.html:27` | Category (`cat`) | `{{ cat.get_name }}` | `{{ cat\|get_category_name:LANGUAGE_CODE }}` |
| `components/breadcrumb.html:30` | Category (`breadcrumb_category`) | `{{ breadcrumb_category.get_name }}` | `{{ breadcrumb_category\|get_category_name:LANGUAGE_CODE }}` |
| `ads/partials/ad_list.html:114` | City (`ad.city`) | `{{ ad.city.get_name\|default:ad.city.name }}` | `{{ ad.city\|get_city_name:LANGUAGE_CODE }}` |
| `ads/partials/ad_list.html:115` | Category (`ad.category`) | `{{ ad.category.get_name\|default:ad.category.name }}` | `{{ ad.category\|get_category_name:LANGUAGE_CODE }}` |
| `ads/detail.html:74` | City (`ad.city`) | `{{ ad.city.get_name\|default:ad.city.name }}` | `{{ ad.city\|get_city_name:LANGUAGE_CODE }}` |
| `ads/detail.html:78` | Category (`ad.category`) | `{{ ad.category.get_name\|default:ad.category.name }}` | `{{ ad.category\|get_category_name:LANGUAGE_CODE }}` |
| `categories/partials/mega_submenu.html:14` | Category (`child`) | `{{ child.get_name }}` | `{{ child\|get_category_name:LANGUAGE_CODE }}` |
| `categories/partials/mega_submenu.html:22` | Category (`child`) | `aria-label="{% trans "Expand" %} {{ child.get_name }}"` | `aria-label="{% trans "Expand" %} {{ child\|get_category_name:LANGUAGE_CODE }}"` |
| `cabinet/saved_search_edit.html:38` | City (`city`) | `{{ city.get_name }}` | `{{ city\|get_city_name:LANGUAGE_CODE }}` |
| `cabinet/saved_search_edit.html:49` | Category (`category`) | `{{ category.get_name }}` | `{{ category\|get_category_name:LANGUAGE_CODE }}` |
| `search/partials/save_search_modal.html:33` | City (`city`) | `{{ city.get_name }}` | `{{ city\|get_city_name:LANGUAGE_CODE }}` |
| `search/partials/save_search_modal.html:47` | Category (`category`) | `{{ category.get_name }}` | `{{ category\|get_category_name:LANGUAGE_CODE }}` |
| `cabinet/partials/saved_search_row.html:17` | City (`ss.city`) | `{{ ss.city.get_name\|default:"—" }}` | `{{ ss.city\|get_city_name:LANGUAGE_CODE\|default:"—" }}` |
| `cabinet/partials/saved_search_row.html:18` | Category (`ss.category`) | `{{ ss.category.get_name\|default:"—" }}` | `{{ ss.category\|get_category_name:LANGUAGE_CODE\|default:"—" }}` |
| `admin/moderation/review.html:50` | Category (`ad.category`) | `{{ ad.category.get_name\|default:ad.category.name }}` | `{{ ad.category\|get_category_name:LANGUAGE_CODE }}` |
| `admin/moderation/review.html:54` | City (`ad.city`) | `{{ ad.city.name }}` (raw Russian) | `{{ ad.city\|get_city_name:LANGUAGE_CODE }}` |

**templates needing `{% load localized_content %}` added:**
1. `components/header_catalog.html`
2. `components/breadcrumb.html`
3. `categories/partials/mega_submenu.html`
4. `cabinet/saved_search_edit.html`
5. `search/partials/save_search_modal.html`
6. `cabinet/partials/saved_search_row.html`
7. `admin/moderation/review.html`

(Already have it: `ads/partials/ad_list.html`, `ads/detail.html`)

**files**
- `templates/components/header_catalog.html` — 6 call sites (1 City, 5 Category);
  add `{% load localized_content %}`.
- `templates/components/breadcrumb.html` — 5 call sites (all Category);
  add `{% load localized_content %}`.
- `templates/categories/partials/mega_submenu.html` — 2 call sites (all Category);
  add `{% load localized_content %}`.
- `templates/ads/partials/ad_list.html` — 2 call sites (1 City, 1 Category);
  already has `{% load localized_content %}`.
- `templates/ads/detail.html` — 2 call sites (1 City, 1 Category);
  already has `{% load localized_content %}`.
- `templates/cabinet/saved_search_edit.html` — 2 call sites (1 City, 1 Category);
  add `{% load localized_content %}`.
- `templates/search/partials/save_search_modal.html` — 2 call sites (1 City, 1 Category);
  add `{% load localized_content %}`.
- `templates/cabinet/partials/saved_search_row.html` — 2 call sites (1 City, 1 Category);
  add `{% load localized_content %}`.
- `templates/admin/moderation/review.html` — 2 call sites (1 Category, 1 City raw);
  add `{% load localized_content %}`.

**changes**
- action: `add_import` (Django template `{% load %}` tag) — add `{% load localized_content %}`
  to the 7 templates listed above (after their existing `{% load i18n %}` line).
- action: `replace_value` — replace each `{{ obj.get_name }}` invocation per the mapping table
  above.
- action: `replace_value` — replace `{{ ad.city.name }}` (raw) in `review.html:54`.

**acceptance_criteria**
- All 24 call sites use `get_category_name:LANGUAGE_CODE` or
  `get_city_name:LANGUAGE_CODE` — zero remaining `{{ *.get_name }}` method calls in
  templates (verified by T-10).
- All 9 templates have `{% load localized_content %}`.
- `|default:obj.name` data-fallback clauses removed; `|default:"—"` visual
  placeholders preserved after the filter.
- Default-language (Russian) rendering unchanged (existing tests that assert on
  Russian names still pass).
- `make lint-templates` (djlint) passes on all 9 files.

---

### T-05 — Admin moderation UI localization + language selector

| Field | Value |
|-------|-------|
| ID | T-05 |
| Title | Localize admin review.html category/city names + add language selector |
| Type | implementation |
| Priority | High |
| Risk | Medium (behavior change for staff-only views) |
| Blocked by | T-01 |
| Source | Spec §5 Task 2 (review.html call sites) + PO Decision §7.2 (REQ-09.7) |

**description**

The `review.html` template is already covered by T-04 for its 2 `get_name` call sites
(lines 50, 54). This task adds the **language selector UI** to the admin panel per
REQ-09.7, so moderators can choose their preferred language (RU/BS/EN) and see localized
category/city names.

The `LanguagePreMiddleware` already handles `?lang=X` globally (including admin views)
and persists the preference via the `lang_pref` cookie + session for authenticated users.
`LANGUAGE_CODE` is already exposed in every template via the `language` context processor.
No new backend logic is needed — the selector is a UI widget with `?lang=` links.

**goals**
- Add a language selector (RU/BS/EN links or dropdown) to the admin UI.
- Links use `?lang=X` (preserving the current path) — handled by the existing middleware.
- `LANGUAGE_CODE` is available in `review.html` (already true via context processor).
- The selector appears on both `review.html` and `queue.html` (the two admin templates).

**files**
- `templates/admin/moderation/review.html`
  - targets: the `<header>` block (line 18-24), which contains the "Mko Bazuna Admin" heading.
  - semantic_anchors:
    - `insert_after: <h1 class="text-2xl font-bold text-gray-800">` (the admin heading) —
      add a language selector block after the heading.
- `templates/admin/moderation/queue.html`
  - targets: extends `admin/base_site.html`; the `{% block content %}` header area.
  - semantic_anchors:
    - `insert_after: <h1>{% trans "Moderation Queue" %}</h1>` — add a language selector
      after the heading.

**changes**
- action: `insert_sibling` — insert a language selector block in `review.html`'s header
  and `queue.html`'s content block. The selector uses `?lang=` links:
  ```html
  <div class="flex gap-2">
      <a href="?lang=ru" class="...">RU</a>
      <a href="?lang=bs" class="...">BS</a>
      <a href="?lang=en" class="...">EN</a>
  </div>
  ```
  (Styled consistently with the existing Tailwind classes.)

**acceptance_criteria**
- Language selector present on both `review.html` and `queue.html`.
- Clicking a language link reloads the page in that language (via `?lang=` → middleware).
- `review.html` category/city names render via `{{ ad.category|get_category_name:LANGUAGE_CODE }}`
  and `{{ ad.city|get_city_name:LANGUAGE_CODE }}` (T-04 covers the filter substitution).
- T-08 regression test verifies admin renders BS/EN names when `?lang=bs`/`en`.

---

### T-06 — Add `User.telegram_language` field + migration + bot menu handler

| Field | Value |
|-------|-------|
| ID | T-06 |
| Title | Add `User.telegram_language` field, migration, and bot language-selection menu |
| Type | implementation |
| Priority | High |
| Risk | High (schema migration) |
| Blocked by | RQ3 |
| Source | PO Decision §7.1 (REQ-09.6); Spec §12 Out-of-Scope note acknowledges this as "a separate feature task" that T-07 depends on |

**description**

This is the "separate feature task" referenced in Spec §12. T-07 (`immediate_alerts.py`
localization) cannot be implemented until the user's language preference exists. Per RQ3,
**Option A** is confirmed: add a `telegram_language` CharField directly on the `User`
model.

The field is non-nullable with `default=LanguageLocale.RUSSIAN.value` (matching the web
middleware's fallback). The migration backfills all existing rows with `"ru"`.

Additionally, add a Telegram bot handler that presents a 3-button inline keyboard (RU/BS/EN)
and persists the user's selection via `@sync_to_async` (mirroring `ad_create.py` and
`login.py` write patterns).

**goals**
- `User.telegram_language` CharField, `max_length=5`, `choices` from `LanguageLocale`,
  `default="ru"`, non-nullable.
- Django migration (`0004_user_telegram_language.py`) — simple `AddField`, backfilling `"ru"`.
- Bot `/language` command (or inline keyboard) that shows RU/BS/EN buttons and writes
  the selection to `user.telegram_language`.
- No N+1 in the alert delivery path: `find_matching_saved_searches` already does
  `select_related("user")`, so `saved_search.user.telegram_language` is a free attribute
  access.

**files**
- `apps/users/models.py`
  - targets: `User` class.
  - semantic_anchors:
    - `insert_after: preferred_city = models.ForeignKey(...)` (or after `telegram_premium`
      field, grouping bot-related fields) — add the `telegram_language` field.
    - `replace_signature: USERNAME_FIELD = "username"` — not changed; field added above
      `USERNAME_FIELD`.
- `apps/users/migrations/0004_user_telegram_language.py` (new)
  - targets: `Migration` class, `operations` list.
  - semantic_anchors:
    - `AddField(model_name="user", name="telegram_language", ...)`.
- `src/telegram_bot/handlers/` (new or existing handler file, e.g., `settings.py` or a new
  `language.py`)
  - targets: a new router or handler function that responds to a `/language` command or
    inline keyboard callback.
  - semantic_anchors:
    - `register: router.message(Command("language"))` — show 3-button inline keyboard.
    - `register: router.callback_query(F.data.startswith("lang:"))` — persist selection.
- `src/telegram_bot/main.py`
  - targets: router inclusion (if a new handler file is created).
  - semantic_anchors:
    - `include_router(language_router)` or similar.

**changes**
- action: `add_field` — add `telegram_language` to `User`.
- action: `add_file` — create migration `0004_user_telegram_language.py`.
- action: `add_file` — create bot language-selection handler.
- action: `add_import` — register the new router in `telegram_bot/main.py`.

**acceptance_criteria**
- `User.telegram_language` field exists, non-nullable, defaults to `"ru"`.
- Migration applies cleanly (`python manage.py makemigrations --check --dry-run` shows
  no missing migrations).
- Bot language menu presents RU/BS/EN buttons; selection persists to the user row.
- `find_matching_saved_searches` query plan unchanged (no new `select_related` needed).
- `ruff check` / `basedpyright` pass.

---

### T-07 — Localize `immediate_alerts.py` alert messages

| Field | Value |
|-------|-------|
| ID | T-07 |
| Title | Use user's language preference in `build_alert_message` |
| Type | implementation |
| Priority | High |
| Risk | High (alert delivery path) |
| Blocked by | T-06, RQ3 |
| Source | Spec §5 (immediate_alerts.py:104), REQ-09.6, PO Decision §7.1 |

**description**

The `build_alert_message` function in `apps/search/services/immediate_alerts.py` currently
hardcodes `"ru"`:
- Line 103: `title = ad.get_title("ru") or "Объявление"`
- Line 104: `city_name = ad.city.get_name() if ad.city else "—"`

Both should use the Telegram user's persisted language preference (`saved_search.user.telegram_language`,
added by T-06). The `build_alert_message` function already receives `saved_search` (which
has `.user`), so the locale is accessible without additional queries.

**goals**
- `title` uses `ad.get_title(user_language)` instead of `ad.get_title("ru")`.
- `city_name` uses `ad.city.get_name(user_language)` instead of `ad.city.get_name()`
  (default `"ru"`).
- The `user_language` is read from `saved_search.user.telegram_language` with a `"ru"`
  fallback if the field is empty/None (defensive).

**files**
- `apps/search/services/immediate_alerts.py`
  - targets: `build_alert_message` function, lines 103–104.
  - semantic_anchors:
    - `replace_in_body: title = ad.get_title("ru") or "Объявление"` →
      `user_locale = getattr(saved_search.user, "telegram_language", None) or "ru"` then
      `title = ad.get_title(user_locale) or "Объявление"`.
    - `replace_in_body: city_name = ad.city.get_name() if ad.city else "—"` →
      `city_name = ad.city.get_name(user_locale) if ad.city else "—"`.

**changes**
- action: `replace_in_body` — read `saved_search.user.telegram_language` with `"ru"`
  fallback; pass it to both `ad.get_title()` and `ad.city.get_name()`.

**acceptance_criteria**
- `build_alert_message` uses the user's language preference for both title and city name.
- Falls back to `"ru"` if the preference is not set (defensive).
- No new DB queries (user is already `select_related`'d).
- T-11 regression test verifies BS/EN payload content.
- `ruff check` / `basedpyright` pass.

---

### T-08 — Regression test: web UI + submenu + admin category/city localization

| Field | Value |
|-------|-------|
| ID | T-08 |
| Title | Add regression tests for localized category/city rendering (web + submenu + admin) |
| Type | test |
| Priority | High |
| Risk | Low |
| Blocked by | T-03, T-04, T-05 |
| Source | Spec §5 Task 5 |

**description**

Add regression tests that load pages with `HTTP_ACCEPT_LANGUAGE="bs"` (and `?lang=en`)
and assert that category and city names render in Bosnian/English (not Russian). This
directly validates the root-cause fix: filters that previously hardcoded `"ru"` now use
`LANGUAGE_CODE`.

The existing `test_language_end_to_end.py` tests ad title/description localization but
uses Category/City WITHOUT `name_i18n` — so it cannot catch the category/city bug. The
new tests must create entities WITH `name_i18n` translations.

**goals**
- Web UI: load the ad detail page (or listing page) with `?lang=bs` and assert Bosnian
  city/category names appear (and Russian names do not).
- Submenu: load `category_submenu` in `ru` and `en`; assert different rendered HTML
  (cache key varies by language — R5).
- Admin: load the moderation review page with `?lang=en` and assert English
  category/city names appear.
- Use distinct, non-overlapping translation strings per locale (e.g.,
  `name_i18n={"ru": "Транспорт", "bs": "Prijevoz", "en": "Transport"}`) so assertions
  cannot pass by coincidence.
- Follow the existing `test_language_end_to_end.py` fixture pattern (autouse locale
  cleanup, staticfiles storage override).

**files**
- `apps/categories/tests/test_i18n_category_city.py` (new) — or
  `apps/ads/tests/test_category_city_i18n.py`
  - targets: a `TestCategoryCityI18n` class with test methods for web UI, submenu, and
    admin rendering.
  - semantic_anchors:
    - `add_top_level: @pytest.fixture autouse _locale_cleanup()` — mirrors
      `test_language_end_to_end.py` pattern.
    - `add_top_level: @pytest.fixture def localized_ad()` — creates Category + City with
      `name_i18n` containing distinct ru/bs/en translations and a published Ad.
    - Test methods: `test_detail_page_bs_renders_bosnian_names`,
      `test_detail_page_en_renders_english_names`,
      `test_submenu_cache_varies_by_language`,
      `test_admin_review_renders_localized_names`.

**changes**
- action: `add_file` — new test file with the test class and fixtures.

**acceptance_criteria**
- `make test` fast gate passes (excluding the new tests until implementation is done;
  once T-04/T-05 are merged, the tests pass).
- Web UI test: `?lang=bs` shows Bosnian names; `?lang=en` shows English names.
- Submenu test: `ru` vs `en` requests return different HTML for the same category.
- Admin test: `?lang=en` shows English category/city names on the review page.
- Existing `test_language_end_to_end.py` tests still pass (no regression).

---

### T-09 — Update entity suggestions tests for locale-awareness

| Field | Value |
|-------|-------|
| ID | T-09 |
| Title | Add locale-aware entity suggestions tests |
| Type | test |
| Priority | Medium |
| Risk | Low |
| Blocked by | T-02 |
| Source | Spec §5 Task 5 (extend regression test); R4 risk mitigation |

**description**

Extend `test_autocomplete.py` to verify that `get_entity_suggestions` returns
locale-aware names when `locale` is passed. The existing tests use categories/cities
without `name_i18n` (falling back to Russian `name`), so they cannot detect the bug. New
test cases must create entities with `name_i18n` and assert locale-aware output.

The existing 11 test calls to `get_entity_suggestions(prefix)` (without locale) must
continue to pass — the default `locale="ru"` preserves backward compatibility.

**goals**
- New test: `get_entity_suggestions("тран", locale="en")` returns English names from
  `name_i18n`.
- New test: `get_entity_suggestions("тран", locale="bs")` returns Bosnian names.
- New test: autocomplete endpoint (`/api/search/autocomplete`) with
  `HTTP_ACCEPT_LANGUAGE="bs"` returns Bosnian entity suggestion labels.
- Existing tests (no locale arg) still pass — default `"ru"` behavior unchanged.
- Category path also respects locale: `_category_path(cat, locale="en")` returns English
  ancestor names.

**files**
- `apps/search/tests/test_autocomplete.py`
  - targets: `TestEntitySuggestionsService` class.
  - semantic_anchors:
    - `add_top_level: @pytest.fixture def localized_category()` — Category with
      `name_i18n={"ru": "Транспорт", "bs": "Prijevoz", "en": "Transport"}`.
    - `add_top_level: @pytest.fixture def localized_city()` — City with `name_i18n`.
    - `add_method` to `TestEntitySuggestionsService` — `test_locale_aware_category_suggestions`,
      `test_locale_aware_city_suggestions`, `test_category_path_respects_locale`.

**changes**
- action: `add_method` — add locale-aware test methods and fixtures.
- action: `replace_in_body` (optional) — update `test_autocomplete_returns_suggestions`
  if it asserts on `text` field (to handle the possibility that entity suggestions now
  return localized text by default for the request locale).

**acceptance_criteria**
- Locale-aware tests pass: `get_entity_suggestions` with `locale="en"` returns English
  names from `name_i18n`.
- Existing tests pass unchanged.
- Autocomplete endpoint test with `HTTP_ACCEPT_LANGUAGE="bs"` returns Bosnian labels.
- `ruff check` passes.

---

### T-10 — Update i18n completeness test to flag `{{ obj.get_name }}`

| Field | Value |
|-------|-------|
| ID | T-10 |
| Title | Extend `test_i18n_completeness.py` to detect bare `{{ obj.get_name }}` calls |
| Type | test |
| Priority | High |
| Risk | Low |
| Blocked by | T-04 |
| Source | Spec §5 Task 6 (PO Decision §7.4: Option A — extend detection, exclude `get_lookup_name`) |

**description**

Add a new test method to `TestI18nCompleteness` in `ads/tests/test_i18n_completeness.py`
that scans all templates for `{{ ...get_name }}` patterns (method calls without a locale
argument) and flags them as violations. The existing `get_lookup_name` filter
(`{{ obj|get_lookup_name:LANGUAGE_CODE }}`) is a **filter**, not a method call, so it is
naturally excluded — the regex targets `\.get_name` inside `{{ }}` blocks.

The `LookupItem` model also has a `get_name` method (F1 reference), but it is only ever
invoked via the `get_lookup_name` filter — no template calls `lookup_item.get_name`
directly. The guard prevents future regressions.

**goals**
- New test method `test_no_bare_get_name_calls` — scans templates for
  `{{ X.get_name }}` or `{{ X.get_name|default:... }}` patterns.
- Excludes `get_lookup_name` (filter usage, different syntax).
- Fails on any remaining `{{ *.get_name }}` method call in templates.
- Marked `@pytest.mark.unit` (fast gate, no DB).

**files**
- `apps/ads/tests/test_i18n_completeness.py`
  - targets: `TestI18nCompleteness` class, `_collect_template_files()` function.
  - semantic_anchors:
    - `add_method: TestI18nCompleteness.test_no_bare_get_name_calls` — the new guard test.
    - The regex: `re.compile(r'\{\{[^}]*\.get_name[^}]*\}\}')` — matches method calls
      inside `{{ }}` but NOT filter usage `{{ X|get_lookup_name:... }}`.

**changes**
- action: `add_method` — add `test_no_bare_get_name_calls` to the test class.

**acceptance_criteria**
- New test passes (zero `{{ *.get_name }}` method calls remain in templates after T-04).
- New test would fail if a `{{ obj.get_name }}` call is reintroduced (regression guard).
- `get_lookup_name` filter usage is NOT flagged.
- `ruff check` passes.
- `make test` fast gate includes this test.

---

### T-11 — Regression test: Telegram alert payload localization

| Field | Value |
|-------|-------|
| ID | T-11 |
| Title | Add regression test for Telegram alert message localization |
| Type | test |
| Priority | Medium |
| Risk | Low |
| Blocked by | T-07 |
| Source | Spec §5 Task 5 (Telegram alert payloads); PO Decision §7.1 (REQ-09.6) |

**description**

Add a test that verifies `build_alert_message` produces localized output (Bosnian/English)
when the user's `telegram_language` preference is set accordingly. The test should
create a user with `telegram_language="bs"`, a Category/City with `name_i18n`, and a
published Ad, then assert the alert message contains Bosnian names (not Russian).

**goals**
- `build_alert_message(ad, saved_search)` with `saved_search.user.telegram_language="bs"`
  produces a message containing Bosnian city/category names.
- Same with `"en"` produces English names.
- The title also respects the locale: `ad.get_title("bs")` returns the BS title.

**files**
- `apps/search/tests/test_immediate_alerts_i18n.py` (new) — or extend
  `apps/search/tests/test_alert_query.py` if there's an existing tests file for
  `immediate_alerts`.
  - targets: a `TestImmediateAlertI18n` class.
  - semantic_anchors:
    - `add_top_level: @pytest.fixture def localized_alert_fixture()` — creates User
      (with `telegram_language`), Category/City (with `name_i18n`), Ad, and SavedSearch.
    - Test methods: `test_alert_message_bs_localized`, `test_alert_message_en_localized`,
      `test_alert_falls_back_to_ru_when_no_preference`.

**changes**
- action: `add_file` — new test file with the test class and fixtures.

**acceptance_criteria**
- `build_alert_message` output contains the correct locale's city/category names.
- Fallback to `"ru"` when `telegram_language` is not set.
- `make test` fast gate passes (or at least the new test runs and passes).
- `ruff check` passes.

---

### T-12 — Verify: web UI i18n fix

| Field | Value |
|-------|-------|
| ID | T-12 |
| Title | Verify web UI i18n fix: `make test` + lint + typecheck |
| Type | verification |
| Priority | High |
| Risk | — |
| Blocked by | T-01, T-02, T-03, T-04, T-08, T-09, T-10 |
| Source | Spec §9 Definition of Done (items 2, 5, 6, 7) |

**description**

Final automated gate for the web UI i18n fix. Runs the full fast-test suite (which
includes the new regression tests and the updated i18n completeness test), Python lint,
template lint, and type checking on all changed files.

**verification_steps**
- test: `make test` (fast gate: skips `seed` marker; includes T-08, T-09, T-10 tests and
  existing tests — no regressions in `test_language_end_to_end.py`,
  `test_submenu.py`, `test_autocomplete.py`, `test_context_processors.py`).
- lint: `uv run ruff check src/backend/apps/core/templatetags/localized_content.py src/backend/apps/search/services/entity_suggestions.py src/backend/apps/search/views/autocomplete.py src/backend/apps/categories/views.py src/backend/apps/categories/cache.py`
- typecheck: `uv run basedpyright src/backend/apps/core/templatetags/localized_content.py src/backend/apps/search/services/entity_suggestions.py src/backend/apps/search/views/autocomplete.py src/backend/apps/categories/views.py src/backend/apps/categories/cache.py`
- lint-templates: `make lint-templates` (djlint with H901; ensures no unwrapped text, no
  missing `{% load %}` tags).
- i18n_guard: `test_no_bare_get_name_calls` passes (zero `{{ *.get_name }}` in templates).

**pass_criteria**
- `make test` green (0 failures; no regressions in existing tests).
- `ruff check` / `ruff format --check` clean.
- `basedpyright` clean on all changed files.
- `make lint-templates` clean on all 9 edited templates.
- i18n completeness test (`test_no_bare_get_name_calls`) fails on regression.

**failure_action:** return the failing task among {T-01, T-02, T-03, T-04} to rework.

---

### T-13 — Verify: admin + Telegram alerts i18n

| Field | Value |
|-------|-------|
| ID | T-13 |
| Title | Verify admin UI + Telegram alerts i18n |
| Type | verification |
| Priority | High |
| Risk | — |
| Blocked by | T-05, T-06, T-07, T-08, T-11 |
| Source | Spec §9 Definition of Done (item 4: admin UI and Telegram alert payloads verified) |

**description**

Final verification gate for the admin UI localization and Telegram alert localization.
Runs the relevant test suites and confirms both paths render localized names.

**verification_steps**
- test: `make test` for `apps/moderation/tests/` and `apps/search/tests/test_immediate_alerts_i18n.py`
  (and `apps/search/tests/test_alert_query.py` if affected by T-07).
- test: `make test` for the bot test suite (`src/telegram_bot/tests/`) if the language
  menu handler (T-06) has bot-side tests.
- lint: `uv run ruff check src/backend/apps/moderation/ src/backend/apps/search/services/immediate_alerts.py src/backend/apps/users/models.py src/telegram_bot/handlers/`
- typecheck: `uv run basedpyright <the same files>`
- migration_check: `python manage.py makemigrations --check --dry-run` (no pending
  migrations after T-06's migration is applied).
- i18n_guard: `test_no_bare_get_name_calls` passes for `review.html`.

**pass_criteria**
- Moderation tests green (staff access + review page rendering).
- Telegram alert i18n tests pass (T-11).
- Bot language menu tests pass (if applicable from T-06).
- `makemigrations --check` reports no missing migrations.
- `ruff check` / `basedpyright` clean.

**failure_action:** return the failing task among {T-05, T-06, T-07, T-11} to rework.

---

## 7. Execution DAG (summary)

```
G0 (parallel, no prerequisites)
 ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐
 │ RQ1    │ │ RQ2    │ │ RQ3    │ │ T-01 │ │ T-03 │
 │ JS     │ │ callers│ │ telegram│ │ filt │ │ cache│
 │ resea  │ │ audit  │ │ pref   │ │ ers  │ │ key  │
 │ rch    │ │ resea  │ │ resea  │ │      │ │      │
 └────┬───┘ └────┬───┘ └────┬───┘ └──┬───┘ └──┬───┘
      │          │          │        │        │
      └──────────┴──────────┘        │        │
      RQ1+RQ2 → T-02                 │        │
                                     │        │
G1 (after G0)                      T-01 →     │
 ┌────────┐ ┌──────┐ ┌──────┐ ┌──────┐      T-03 →
 │ T-02   │ │ T-04 │ │ T-05 │ │ T-06 │
 │ entity │ │ tmpl │ │ admin│ │ tele │
 │ sugg   │ │ sites│ │ UI   │ │ pref │
 └───┬────┘ └──┬───┘ └──┬───┘ └──┬───┘
     │         │        │        │
     │         │        │        │
     │   T-01──┘        │        │
     │                  │        │
G2                        T-06 → T-07
 ┌────────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
 │ T-07  │ │ T-08 │ │ T-09 │ │ T-10 │ │ T-11 │
 │ alerts│ │ regr │ │ ent  │ │ i18n │ │ tele │
 │       │ │ test │ │ test │ │ test │ │ test │
 └───┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
     │         │        │        │        │
     └─────────┴────────┴────────┴────────┘
      T-07 → T-11
      T-04 → T-10
      T-02 → T-09

G3 (verification gates — all paths converge)
 ┌──────────────────────┐  ┌──────────────────────┐
 │ T-12: Verify web UI  │  │ T-13: Verify admin   │
 │ i18n fix             │  │ + Telegram alerts    │
 └──────────────────────┘  └──────────────────────┘
      (T-01,T-02,T-03,T-04,T-08,T-09,T-10)
      (T-05,T-06,T-07,T-08,T-11)
```

**G0:** `RQ1 ∥ RQ2 ∥ RQ3 ∥ T-01 ∥ T-03` — maximum parallelism: three research
questions alongside two independent, low-risk implementation tasks.

**G1:** `T-02 ∥ T-04 ∥ T-05 ∥ T-06` — each depends on different G0 outputs
(research for T-02/T-06, filters for T-04/T-05).

**G2:** `T-07 ∥ T-08 ∥ T-09 ∥ T-10 ∥ T-11` — dependent implementation (T-07 on
Telegram field + research) and test tasks; tests depend on their respective implementation
tasks.

**G3:** `T-12 ∥ T-13` — final verification gates; T-12 covers the web UI path, T-13
covers admin + Telegram.

---

## 8. Overall Acceptance Criteria (Spec §9 / Spec §14 DoD)

The Category/City i18n fix is complete when **all** hold:

1. **AC-1** — All 24 template call sites use `get_category_name:LANGUAGE_CODE` or
   `get_city_name:LANGUAGE_CODE` filters (T-04). Zero `{{ *.get_name }}` method calls
   remain in templates (guarded by T-10).
2. **AC-2** — `get_entity_suggestions` accepts an optional `locale` parameter; the
   autocomplete endpoint passes `request.LANGUAGE_CODE`; suggestions return localized
   names (T-02). Existing callers/tests unaffected (backward-compatible default).
3. **AC-3** — The `category_submenu` cache key includes the locale; no cross-language
   cache bleed (T-03).
4. **AC-4** — Admin moderation UI (`review.html`) renders localized category/city names
   via the new filters; a language selector (RU/BS/EN) is available (T-05).
5. **AC-5** — Telegram alert messages (`build_alert_message`) use the user's
   `telegram_language` preference (T-07); the preference is persisted via
   `User.telegram_language` + bot language menu (T-06).
6. **AC-6** — Regression tests pass: category/city names render in BS/EN when
   `?lang=bs`/`en` or `Accept-Language` is set; submenu cache varies by language; admin
   UI and Telegram alert payloads verified (T-08, T-11).
7. **AC-7** — `make test` (fast gate) passes with no regressions.
8. **AC-8** — `test_i18n_completeness.py` passes with the new `{{ obj.get_name }}`
   violation check (T-10).
9. **AC-9** — `uv run ruff check` and `uv run basedpyright` pass on all changed files.
10. **AC-10** — This spec is marked `Status: Complete` in the spec index.

**DoD mapping:** AC-1↔Spec §14.1, AC-2↔§14.2, AC-3↔§14.3, AC-4↔§14.3+§7.2, AC-5↔§14.3+§7.1,
AC-6↔§14.4, AC-7↔§14.5, AC-8↔§14.6, AC-9↔§14.7, AC-10↔§14.8.

---

## 9. Implementation Notes

1. **No schema changes for the core web fix.** T-01 through T-05 are template/ORM logic
   changes only — no DB migrations. Only T-06 (Telegram language preference) introduces a
   schema migration.

2. **Filter None-safety.** The new `get_category_name` and `get_city_name` filters must
   guard against `None` input (return `""`), replacing the `|default:` clauses that
   currently protect `{{ obj.city.get_name|default:obj.city.name }}` and
   `{{ obj.city.get_name|default:"—" }}`. The `get_name()` method's fallback chain
   (locale→ru→name) handles data-level fallback; the filter handles object-level None.

3. **Backward compatibility of `get_entity_suggestions`.** The `locale` parameter must
   be optional (`locale: str = "ru"`) because 11 existing test callers invoke
   `get_entity_suggestions(prefix)` without it (RQ2). Making it required would break
   `test_autocomplete.py`.

4. **Admin language selector.** The `LanguagePreMiddleware` already handles `?lang=`
   globally and persists via cookie + session. The admin selector is a UI-only widget —
   no new middleware or context processor changes needed. `LANGUAGE_CODE` is already
   available in all templates via the existing `language` context processor.

5. **Telegram field naming.** Per RQ3, the field is `User.telegram_language`
   (not `bot_language` or `preferred_language`), matching the PO decision §7.1 and the
   existing `User.telegram_id` / `User.telegram_premium` naming convention.

6. **Bot process isolation.** The Telegram bot (`src/telegram_bot/`) runs `django.setup()`
   and shares the ORM. The new `User.telegram_language` field is accessible from the bot
   via `sync_to_async` ORM calls, same as all other bot data access.

7. **Seed data.** The `categories.yaml` and `cities.json` seed data already contains
   complete `name_i18n` translations (F2). The catalog builder persists them to the
   `name_i18n` JSONField (F3). No seed data changes needed.

8. **Spec index.** Spec 09 is already linked from `docs/01-spec/spec-index.md` (Spec
   §5 Task 7). AC-10 requires updating the status from "Draft" to "Approved" / "Complete".
