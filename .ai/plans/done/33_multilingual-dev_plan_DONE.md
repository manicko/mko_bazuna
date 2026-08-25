---
id: 33_multilingual-dev
spec: .ai/problems/08_multilingual-dev_spec.md
domain: implementation-plan
spec_status: PENDING_PO_ANSWERS
priority: High
status: Ready for implementation (after T-00 decision gate)
date: 2026-08-24
stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX 1.9.12 · vanilla JS · Tailwind CSS v4
decision_gate: T-00 (resolve Q1–Q8 + scan-mechanism)
---

# Plan 33 — Multilingual Development Definition of Done

Transformation of **Spec 08** (`.ai/problems/08_multilingual-dev_spec.md`, pending PO answers to Q1–Q8) into a
dependency-aware implementation DAG.

> **Spec status:** `PENDING_PO_ANSWERS` — implementation begins after **T-00** confirms the Q1–Q8 decisions using
> the recommended defaults baked in below. Two tasks (`T-02` Python-side, `T-07` doc update) are deliberately
> **independent of the gate** and can start immediately, since the spec prescribes them unambiguously regardless
> of the PO answers.

> **Root constraint:** `gettext`/`gettext_lazy` is imported in **zero** production Python files today (Spec §2.10).
> Task 2 introduces i18n to production Python for the first time — a runtime behaviour change for a context
> processor, an enum's `.choices()`, two view contexts, and four `HttpResponseForbidden` bodies. These are
> behaviour-changing, so verification (`T-09`) must confirm rendered output is still correct under `lang=ru`.

The spec's eight conceptual tasks (§8) are reorganized below into ten implementation-sequenced tasks optimized for
**file-edit isolation, dependency safety, and independent reviewability**, with one decision gate and two
verification gates.

---

## 1. Statement of Scope

Ten tasks (1 decision gate + 7 implementation + 2 verification), regrouping the spec's conceptual Task 1–8 so that
work is sequenced by **real dependencies** (extraction depends on string wrapping; tests depend on a compiled
catalog; CI depends on tests) rather than by the spec's conceptual numbering.

**In scope (files):**

- *Templates, public/seller-facing* — `components/header_catalog.html`, `components/header.html`,
  `components/consent_banner.html`, `components/breadcrumb.html`, `components/badges/{pro,trusted,verified}_badge.html`,
  `users/login_issue.html`, `ads/dashboard.html`, `ads/edit.html`, `analytics/seller_dashboard.html`.
- *Python production code* — `apps/core/context_processors.py`, `apps/core/enums.py` (`TimeRange`),
  `apps/ads/views/{dashboard,edit,delete}.py`, `apps/ads/views/listings.py`.
- *Catalog artifacts* — `src/backend/locale/{ru,en,bs}/LC_MESSAGES/django.po` (committed); `.mo` are gitignored
  build artifacts (refreshed by `makemessages`/`compilemessages`).
- *Test infra* — new `apps/ads/tests/test_i18n_completeness.py`; update `test_auth_nav.py`,
  `test_breadcrumbs_render.py`, `test_preferred_city.py`, `test_context_processors.py`.
- *CI* — `.github/workflows/ci.yml` (add dedicated `i18n` job).
- *Docs* — `docs/99-agent/i18n-translation-pipeline-gap-analysis.md`; `.kilo/rules/commands.md`; `.kilo/rules/project.md`.
- *Helper* — `apps/core/services/translation_service.py` (invoke for ru/bs bootstrap).

**Explicitly out of scope (per resolved Q1–Q8 defaults):**

- Staff/admin templates — `admin/moderation/queue.html`, `admin/moderation/review.html`,
  `analytics/moderation_dashboard.html` (Q1 = exclude staff-only).
- `templates/privacy.html` — static legal page, kept English-only (Q2 = C, exclude from DoD).
- Telegram bot (`src/telegram_bot/`) — Russian-only, web-only DoD (Q3 = bot out of scope).
- `components/feature_tag.html` — uses DB-based i18n (`get_lookup_name` + `LookupItem.name_i18n`),
  not gettext, already handled (Spec §2.8). Excluded from completeness scan.
- `Http404(...)` messages — not user-facing in production (Spec §3.3 note). Not translated.

---

## 2. Resolved Decisions (Decision Gate T-00)

The spec's §6 lists eight open questions with **recommended defaults**. The plan is built on these defaults so
that, absent PO override, implementation is deterministic. `T-00` records/confirms them.

| Question | Recommended default | Effect on tasks |
|---|---|---|
| Q1: Admin/analytics scope | Exclude staff-only templates (`admin/moderation/*`, `analytics/moderation_dashboard.html`); badges + `analytics/seller_dashboard.html` included | Scopes `T-01` |
| Q2: `privacy.html` | C — exclude from DoD | Scopes `T-01` |
| Q3: Bot i18n | Out of scope (web-only) | No bot changes |
| Q4: .po parser | B — reuse custom `_parse_po_entries` (no new dependency) | `T-04` |
| Q5: `en` msgstr | A — leave empty (Django convention; msgid is English) | `T-03` |
| Q6: Inline JS in `header_catalog.html` | A — pass translated labels as view/context variables | `T-01` (header_catalog JS block) |
| Q7: CI placement | A — dedicated `i18n` CI job | `T-05` |
| Q8: Translation process | C — auto-translation (deep-translator) first pass, then human review of `ru` | `T-03` |
| Q9 (gate-added): template-scan mechanism | B — stdlib `html.parser` walk (no new dep; accurate visible-text isolation) | `T-04` |

---

## 3. Execution DAG

```mermaid
flowchart TD
    subgraph G0 ["G0 — parallel, gate-independent"]
        T00[T-00 Decision gate<br/>Q1–Q8 + Q9]
        T02[T-02 Python-side gettext<br/>§3.3 (15 strings)]
        T07[T-07 Update gap-analysis doc]
    end

    subgraph G1 ["G1 — after T-00"]
        T01[T-01 Wrap template strings<br/>§3.1 + §3.2 public/seller]
        T08[T-08 Add i18n cheatsheet<br/>commands.md + project.md]
    end

    subgraph G2 ["G2 — after T-00 + T-01 + T-02"]
        T03[T-03 Extract + populate .po<br/>+ compile .mo]
    end

    subgraph G3 ["G3 — after T-03 + T-00 (parallel)"]
        T04[T-04 Completeness tests<br/>test_i18n_completeness.py]
        T06[T-06 Update existing tests<br/>translation.activate('ru')]
    end

    subgraph G4 ["G4 — after T-04 + T-00"]
        T05[T-05 Add i18n CI job<br/>ci.yml]
    end

    subgraph G5 ["G5 — after T-01 + T-02 + T-03"]
        T10[T-10 Manual multilingual<br/>spot-check ?lang=ru/en/bs]
    end

    subgraph G6 ["G6 — final gate"]
        T09[T-09 Automated verification<br/>make test + lint + lint-templates]
    end

    T00 --> T01 & T03 & T04 & T05 & T08
    T01 --> T03
    T02 --> T03
    T03 --> T04 & T06 & T10
    T04 --> T05
    T05 --> T09
    T01 & T02 & T03 --> T09
    T06 --> T09
```

**Parallel groups:**
- **G0:** `{T-00, T-02, T-07}` — T-00 is a decision gate; T-02 and T-07 are prescriptive and unblocked by any PO answer.
- **G1:** `{T-01, T-08}` — both depend on T-00; T-01 (templates) and T-08 (cheatsheet) touch disjoint file sets.
- **G2:** `{T-03}` — extraction cannot run until *all* string wrapping (T-01) and Python gettext (T-02) are committed; depends on T-03's own gate T-00 for the translation process (Q8).
- **G3:** `{T-04, T-06}` — completeness tests and existing-test updates both need the compiled catalog (T-03); they touch disjoint files and run in parallel.
- **G4:** `{T-05}` — CI job depends on the test file (T-04).
- **G5:** `{T-10}` — manual spot-check needs compiled `ru`/`en`/`bs` `.mo` plus the wrapped templates/Python (T-01, T-02, T-03).
- **G6:** `{T-09}` — final automated gate over everything.

**Critical path:** `T-00 → T-01 → T-03 → T-04 → T-05 → T-09` (with `T-02` running alongside `T-00`/`T-01`).

---

## 4. Risk Assessment

| Task | Risk | Why it is risky | Mitigation |
|------|------|-----------------|------------|
| T-01 (templates) | Medium | Changes rendered output of ~9 public/seller templates; existing tests assert on Russian text (Spec §3.5) | T-06 updates those tests; T-09 gate |
| T-02 (Python gettext) | Medium–High | **First-time** `gettext`/`gettext_lazy` in production Python; changes context processor output, enum `.choices()` labels, view contexts, and 403 response bodies at runtime | `.mo` compiled in entrypoints (Spec §2.2); T-06 covers context-processor test |
| T-03 (.po/.mo) | Medium | Mutates committed `.po` catalog; `.mo` are gitignored → must compile before tests/CI | Commit only `.po`; CI + test entrypoint run `compilemessages` (see T-05) |
| T-04 (completeness tests) | Medium | New CI gate; `test_no_hardcoded_visible_text` false-positive risk on badges/scripts | T-00 Q9 (stdlib `html.parser`); curated known-OK exclusions (Spec §5.2); scope excludes admin/analytics + `feature_tag.html` |
| T-05 (CI) | Medium | Edits shared `.github/workflows/ci.yml`; gate runs on every PR | Additive `i18n` job only; no change to existing jobs; requires `compilemessages` step before `pytest` |
| T-06 (test updates) | Low | Edits 4 test files | Surgical: add `translation.activate("ru")`; assert on translated output |
| T-02 runtime (3.3.3) | Medium | `status_labels` dict consumed by `dashboard.html:76` via `get_item` filter; wrong key breaks rendering | Preserve dict keys; wrap values in `gettext_lazy` |

**Shared-config / startup / schema risk:** none. No migrations, no schema changes, no settings changes, no startup path changes. The middleware (`LanguagePreMiddleware`) and context processor already exist and operate (Spec §2.2).

---

## 5. Task Index

| ID | Title | Type | Priority | Risk | Blocked by |
|----|-------|------|----------|------|------------|
| T-00 | Decision gate: resolve Q1–Q8 + scan mechanism (Q9) | decision | High | — | — |
| T-01 | Wrap hardcoded visible strings in public/seller-facing templates | implementation | High | Medium | T-00 |
| T-02 | Introduce gettext/gettext_lazy in Python (§3.3, 15 strings) | implementation | High | Medium–High | — |
| T-03 | Extract messages, populate .po, compile .mo | implementation | High | Medium | T-00, T-01, T-02 |
| T-04 | Implement automated completeness tests | implementation | High | Medium | T-00, T-03 |
| T-05 | Add dedicated `i18n` CI job | implementation | Medium | Medium | T-00, T-04 |
| T-06 | Update existing tests asserting on hardcoded Russian text | implementation | Medium | Low | T-01, T-02, T-03 |
| T-07 | Update stale gap-analysis doc | documentation | Low | Low | — |
| T-08 | Add i18n DoD cheatsheet to developer rules | documentation | Medium | Low | T-00 |
| T-09 | Verification: `make test` + lint + lint-templates | verification | High | — | T-01, T-02, T-03, T-04, T-05, T-06 |
| T-10 | Manual multilingual spot-check (`?lang=ru/en/bs`) | verification | Medium | — | T-01, T-02, T-03 |

---

## 6. Current State (verified facts, per Spec §2)

| Concern | Current state | Evidence |
|---------|---------------|----------|
| Languages | `ru` (primary), `en`, `bs` (secondary) | `apps/core/enums.py` `LanguageLocale` (Spec §2.1) |
| Runtime pipeline | Operational: middleware activates lang from `?lang=`/cookie; context processor exposes `LANGUAGE_CODE`/`LANGUAGES` | `apps/core/middleware/language.py` `LanguagePreMiddleware`; `apps/core/context_processors.py:21` |
| Locale files | `src/backend/locale/{ru,en,bs}/LC_MESSAGES/django.po` exist; 39 entries (38 + header); **all non-header `msgstr` empty**; identical msgids across locales | Spec §2.3 |
| `.mo` compilation | Runs at Docker build (`Dockerfile:78`) and runtime entrypoints (`entrypoint.sh:73-87`, `entrypoint-test.sh:37`) | Spec §2.2 |
| `.mo` in VCS | Gitignored (`gitignore:55`) — build artifact | Spec §2.3 |
| `gettext` in production | **Not imported anywhere** in `src/backend/` production Python | Spec §2.10 |
| Python UI strings | 15 genuine user-facing (1 Cyrillic + 14 English), per AST audit | Spec §3.3 |
| Hardcoded template strings | 62+ unique strings not in `.po` — either unwrapped `{% trans %}` or templates lacking `{% load i18n %}` | Spec §2.3, §3 |
| Existing i18n tests | 5 tests in `apps/ads/tests/test_i18n_pipeline.py`, `@pytest.mark.unit`, custom `_parse_po_entries` parser (lines 31-73), `polib` not a dependency | Spec §2.4 |
| CI | 5 jobs: `build`, `test`, `lint`, `typecheck`, `lint-templates`; **no i18n job** | Spec §2.5 |
| pytest markers | `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group` — **no `i18n` marker** | Spec §2.5 |
| Makefile | `makemessages` / `compilemessages` targets at `Makefile:146-150` | Spec §2.2 |
| DB-based i18n | `components/feature_tag.html` uses `get_lookup_name` + `LookupItem.name_i18n` — separate path, in scope | Spec §2.8 |
| Tests asserting on Russian UI text | `test_auth_nav.py` (l.81,92), `test_breadcrumbs_render.py` (l.65), `test_preferred_city.py` (l.139,147,180), `test_context_processors.py` (l.72,110) | Spec §3.5 |

---

## 7. Task Specifications

> Format follows `.ai/tasks/templates/task_template.yaml`. `depends_on` lists the IDs a task cannot start
> without. `source_reference` cites the spec sections that fix the task's requirements.

---

### T-00 — Decision gate: resolve i18n DoD open questions (Q1–Q8) + scan mechanism (Q9)

| Field | Value |
|-------|-------|
| ID | T-00 |
| Title | Decision gate: confirm Q1–Q8 answers + template-scan mechanism before implementation |
| Type | decision / research |
| Priority | High |
| Risk | — (no code change) |
| Blocked by | — |
| Source | Spec §6 (Q1–Q8) + Spec §5.1 (approach) |

**description**

The spec is `PENDING_PO_ANSWERS` until Q1–Q8 are confirmed. This gate records the recommended-default
decisions (§2 above) so downstream tasks have a deterministic basis. It does **not** block the two prescriptive,
unaffected tasks (`T-02`, `T-07`). Once confirmed (Go / Go-with-changes), implementation may proceed.

**goals**
- Q1 confirmed: staff/admin templates excluded; badges + `seller_dashboard.html` included.
- Q2 confirmed: `privacy.html` excluded.
- Q3 confirmed: bot out of scope.
- Q4 confirmed: custom `_parse_po_entries` parser reused (no `polib` dependency).
- Q5 confirmed: `en` msgstr left empty (Django convention).
- Q6 confirmed: `header_catalog.html` inline JS labels passed as view/context variables.
- Q7 confirmed: dedicated `i18n` CI job.
- Q8 confirmed: deep-translator auto-populate ru/bs, then human-review `ru`.
- Q9 confirmed: template-text scanning via stdlib `html.parser` (no new dependency).

**files**
- path: (none — decision record)

**changes**
- action: none (gate resolution recorded in this plan §2)

**acceptance_criteria**
- All nine decisions above are confirmed/approved.
- Each decision-dependent task references its gating question(s).

**blocks:** T-01 (Q1, Q2, Q6), T-03 (Q8), T-04 (Q4, Q9), T-05 (Q7), T-08 (all).

---

### T-01 — Wrap hardcoded visible strings in public/seller-facing templates

| Field | Value |
|-------|-------|
| ID | T-01 |
| Title | Wrap hardcoded visible strings in `{% trans %}` / `{% blocktrans %}`; add `{% load i18n %}` where missing |
| Type | implementation |
| Priority | High |
| Risk | Medium |
| Blocked by | T-00 |
| Source | Spec §3.1 (templates loading i18n but with remaining text) + §3.2 (templates missing i18n entirely) |

**description**

Convert every user-visible string in the in-scope templates into a gettext msgid, following the checklist in
Spec §3.5 (buttons, links, titles, placeholders, tooltips, error/success, filter/sort, pagination, empty
states, modal text, auth text, system messages). Wrap each in `{% trans "..." %}` (or `{% blocktrans %}`
for strings containing variables). Add `{% load i18n %}` to templates that lack it. Do **not** wrap machine
values (`value`/`name` attributes, currency codes `EUR`/`RSD`/`BAM`), brand names (`Mko Bazuna`), or
non-visible structural/HTML. `components/feature_tag.html` is excluded (DB-based i18n, Spec §2.8).

`header_catalog.html`'s five inline-JS labels (Spec §3.1.1, Q6=A) must be injected as **pre-translated
context variables** from the view/context that renders the shared layout, then read by the JS block — not
hardcoded Cyrillic string literals.

**goals**
- Every in-scope user-visible string is wrapped in `{% trans %}` / `{% blocktrans %}`.
- Every in-scope template that lacks `{% load i18n %}` gains it.
- No machine-value attributes, brand names, or currency codes are wrapped.
- `feature_tag.html` is left untouched (DB i18n).
- `header_catalog.html` JS labels come from translated context variables (Q6=A).

**files**

- `components/header_catalog.html`
  - targets: 6 visible Russian strings (Spec §3.1.1 L32/59/79/119/130/146) → msgids `"Submit an ad"`, `"Entire country"`, `"All categories"`, `"Search ads..."`, `"Search"`, `"Categories"`; inline-JS labels (Spec §3.1.1 L213/217-220) → `"Show all results"`, `"Cities"`, `"Categories"`, `"Popular queries"`, `"History"` via context vars.
  - Already has `{% load i18n %}` at L8.
  - semantic_anchors: the search-submit button text, the "Entire country"/"All categories" span labels, the search input `placeholder`, the mobile panel header; the inline `<script>` block that builds the autocomplete dropdown labels.
- `components/header.html`
  - targets: 5 English nav links (Spec §3.1.2 L11/12/14/18/21) → `"Cabinet"`, `"Dashboard"`, `"Admin"`, `"Logout"`, `"Login"`.
  - Already has `{% load i18n %}` at L2.
  - semantic_anchors: the `<a>` link texts in the auth/user menu.
- `components/consent_banner.html`
  - targets: 3 checkbox labels (Spec §3.1.3 L27/30/33) → `"Essential"`, `"Analytics"`, `"Preferences"`.
  - Already has `{% load i18n %}` at L3.
  - semantic_anchors: the `<label>` texts inside the consent preferences; leave `value="accepted\|declined"` and `value="1.0"` unwrapped.
- `components/breadcrumb.html`
  - targets: `Главная`, `Результаты поиска:` → `"Home"`, `"Search results:"`; add `{% load i18n %}`.
- `components/badges/pro_badge.html`, `trusted_badge.html`, `verified_badge.html`
  - targets: visible badge text (`Pro`/`Trusted`/`Verified`) → wrap; `aria-label="… seller"` → PO decision (non-visible); add `{% load i18n %}`.
- `users/login_issue.html`
  - targets: all visible auth text (`Login`, `Login to Mko Bazuna`, `Tap the button…`, etc.); full audit + add `{% load i18n %}`.
- `ads/dashboard.html`
  - targets: `Your Ads`, `Views`, `Contacts`, `Published`, `Edit`, `Archive`, etc.; `TimeRange` labels already come from enum (covered by T-02); add `{% load i18n %}`.
- `ads/edit.html`
  - targets: `Edit Ad`, `Title`, `Description`, `Price`, `Save Changes`, etc.; add `{% load i18n %}`.
- `analytics/seller_dashboard.html`
  - targets: `Your Trust Profile`, `Total Views (30d)`, etc.; seller-facing; add `{% load i18n %}`.

**changes**
- action: add_trans_tags — add `{% load i18n %}` where missing; wrap each in-scope visible string in `{% trans "..." %}`.
- action: refactor_js_labels — for `header_catalog.html`, replace hardcoded JS-label literals with references to translated context variables (Q6=A).

**acceptance_criteria**
- Every listed visible string in the in-scope templates is wrapped in `{% trans %}` / `{% blocktrans %}`.
- `breadcrumb.html`, all 3 badge templates, `login_issue.html`, `dashboard.html`, `edit.html`, `seller_dashboard.html` now contain `{% load i18n %}`.
- `header_catalog.html` inline JS reads its dropdown labels from translated context variables (no Cyrillic literals in the `<script>`).
- `djlint` (`make lint-templates`) still passes on all edited templates.

---

### T-02 — Introduce gettext/gettext_lazy in Python (§3.3, 15 strings)

| Field | Value |
|-------|-------|
| ID | T-02 |
| Title | Wrap 15 user-facing Python strings in gettext/gettext_lazy |
| Type | implementation |
| Priority | High |
| Risk | Medium–High (first-time gettext in production Python; runtime behaviour change) |
| Blocked by | — |
| Source | Spec §3.3 (§3.3.1–3.3.5) |

**description**

This is the **first** introduction of `gettext`/`gettext_lazy` into the production Python codebase (Spec §2.10).
Each hard-coded user-facing literal in §3.3 becomes a msgid, wrapped with the correct lazy/runtime variant:
`gettext` for request-time evaluation (context processor, inline error, `HttpResponseForbidden` bodies);
`gettext_lazy` for deferred evaluation (enum `.choices()` labels, module-level `status_labels` dict whose
values are rendered lazily through the template). `Http404(...)` messages are left as-is — not user-facing
(Spec §3.3 note).

**goals**
- 15 user-facing strings become translatable msgids; no `Http404` messages touched.
- Correct lazy/runtime variant at each call site (so lazy objects aren't forced at import time).

**files**

- `apps/core/context_processors.py`
  - targets: the `preferred_city_display = "Вся страна"` assignment (§3.3.1 L46).
  - semantic_anchors: insert `from django.utils.translation import gettext as _` import; replace the literal with `_("Entire country")`.
- `apps/core/enums.py`
  - targets: `TimeRange` enum labels `"All Time"`, `"30 Days"`, `"7 Days"` in `choices()` (§3.3.2 L133-136).
  - semantic_anchors: add `gettext_lazy as _` import to the file's existing `django.utils.translation` imports; wrap the three label strings in the `TimeRange` definition.
- `apps/ads/views/dashboard.py`
  - targets: the `status_labels` dict (§3.3.3 L77-83) — `"Published"`, `"On Moderation"`, `"Failed Moderation"`, `"Archived"`, `"Rejected"`.
  - semantic_anchors: convert the dict values to module-level `gettext_lazy` constants (or wrap in-place keeping the dict keys intact for `dashboard.html`'s `{{ status_labels|get_item:status }}`).
- `apps/ads/views/edit.py`
  - targets: inline error `"Ad failed moderation checks"` (§3.3.4 L170); `HttpResponseForbidden` bodies at L105, L243, L274 (§3.3.5).
  - semantic_anchors: add `gettext as _` import; wrap each literal string at its call site.
- `apps/ads/views/delete.py`
  - targets: `HttpResponseForbidden("You do not have permission to delete this ad.")` (§3.3.5 L44).
- `apps/ads/views/listings.py`
  - targets: `HttpResponseForbidden("Access denied")` (§3.3.5 L187).

**changes**
- action: add_import — `from django.utils.translation import gettext as _` (runtime) in `context_processors.py`, `edit.py`, `delete.py`, `listings.py`; `gettext_lazy as _` in `enums.py` and `dashboard.py`.
- action: replace_value — wrap each of the 15 literal strings at its call site.

**acceptance_criteria**
- `src/backend/` production files now import `gettext`/`gettext_lazy` (at least the 6 files listed).
- The 15 strings are wrapped; `Http404(...)` messages unchanged.
- `TimeRange.choices()` still returns the same member/value pairs (only the human label becomes lazy-translatable).
- `status_labels` dict still resolves via `{{ status_labels|get_item:status }}` in `dashboard.html`.
- `ruff check` / `ruff format --check` pass.

---

### T-03 — Extract messages, populate .po, compile .mo

| Field | Value |
|-------|-------|
| ID | T-03 |
| Title | `makemessages` → auto-translate ru/bs → review → `compilemessages` |
| Type | implementation |
| Priority | High |
| Risk | Medium (mutates committed `.po`; `.mo` gitignored so must compile before tests/CI) |
| Blocked by | T-00 (Q8 process), T-01, T-02 |
| Source | Spec §2.2 (pipeline), §2.3 (catalog state), §2.4 (Makefile/cmds), Spec Task 3 |

**description**

Produce the translated catalog that backs every wrapped msgid. Order matters: (1) all template/Python
wrapping must be committed first (T-01, T-02) so `makemessages` extracts the complete set; (2) auto-populate
`ru`/`bs` `msgstr` via the deep-translator service (Q8=C); (3) human-review the `ru` `msgstr` for accuracy
(primary language); (4) compile `.mo`. Per Q5, `en` `msgstr` is left empty (msgid is English).

**goals**
- `django.po` for all 3 locales contains every msgid introduced by T-01/T-02 (no missing entries).
- `ru` and `bs` have **0** empty `msgstr` (Spec §4.2).
- `en` `msgstr` left empty per Django convention (Q5).
- `.mo` files compiled and present on disk for the test run.

**files**
- `src/backend/locale/ru/LC_MESSAGES/django.po`, `…/en/…`, `…/bs/…` — targets: msgid set; `msgstr` populated for ru/bs.
- `apps/core/services/translation_service.py` — invoke to bootstrap ru/bs `msgstr`.
- `Makefile:146-150` — targets: `makemessages` / `compilemessages` (referenced, not edited).

**changes**
- action: run_makemessages — `python manage.py makemessages -l ru -l en -l bs` (refreshes all `.po`).
- action: run_translation_service — populate `ru`/`bs` `msgstr` via `translation_service.py` (Q8=C first pass).
- action: review — human-correct the `ru` `msgstr` (primary language accuracy).
- action: run_compilemessages — `python manage.py compilemessages` (generates `.mo`).
- action: commit — commit updated `django.po` files for all 3 locales; **do not** commit `.mo` (gitignored).

**acceptance_criteria**
- `makemessages` reports the new msgids extracted from T-01/T-02 templates+Python.
- `ru` and `bs` `django.po` have 0 empty `msgstr` for non-header entries.
- `en` `django.po` `msgstr` empty per convention.
- `compilemessages` succeeds with no errors; `.mo` files exist on disk.
- `.gitignore` still excludes `*.mo` (no `.mo` staged in commit).

---

### T-04 — Implement automated completeness tests

| Field | Value |
|-------|-------|
| ID | T-04 |
| Title | Add `test_i18n_completeness.py` with 4 guard tests (templates + .po) |
| Type | implementation |
| Priority | High |
| Risk | Medium (new CI gate; false-positive risk in hardcoded-text scanner) |
| Blocked by | T-00 (Q4 parser, Q9 scan mechanism), T-03 |
| Source | Spec §5 (Automated Checking System) |

**description**

Add the CI gate that enforces the multilingual DoD on every fast-gate run. Follow the existing
`test_i18n_pipeline.py` pattern: `@pytest.mark.unit`, `SimpleTestCase`, custom parser (Q4=B — **no `polib`
dependency**), `settings.LOCALE_PATHS`-driven `.po` discovery. The two `.po` guards (`test_no_empty_msgstr`,
`test_mo_compiled`) mirror the existing tests; the two template guards (`test_no_hardcoded_visible_text`,
`test_extraction_completeness`) are new.

For `test_no_hardcoded_visible_text`, isolate genuine visible text from attributes/scripts/comments using the
stdlib `html.parser` (Q9=B — no new dependency). Curate the known-OK exclusion list from Spec §5.2 and scope
the scan to public/seller-facing templates only (exclude `admin/` staff subtree, `analytics/moderation_dashboard.html`,
and `components/feature_tag.html` which uses DB-based i18n).

Per Spec §5 detection-scope limitation, **Python-side** hardcoded strings are **not** auto-detected (review
gated via §4.6); `test_extraction_completeness` therefore covers template `{% trans %}` / `{{ _("...") }}`
msgids only.

**goals**
- 4 tests as specified in Spec §5.2, all `@pytest.mark.unit`.
- No new third-party dependencies (reuse custom `.po` parser; use stdlib `html.parser`).
- Hardcoded-text scanner targets only public/seller-facing templates; known-OK exclusions applied.
- Extraction-completeness check is template-scoped (Python-side is review-gated).

**files**
- `apps/ads/tests/test_i18n_completeness.py` (new)
  - targets: `test_no_hardcoded_visible_text`, `test_extraction_completeness`, `test_no_empty_msgstr`,
    `test_mo_compiled`.
  - semantic_anchors: import `_parse_po_entries` / `_po_files` from `apps.ads.tests.test_i18n_pipeline` (Q4=B) OR a shared helper module if one is introduced; define the known-OK exclusion predicate; define the template-scan visitor class.
- `apps/ads/tests/test_i18n_pipeline.py` (referenced, not edited unless a shared helper is extracted)

**changes**
- action: add_file — `test_i18n_completeness.py` with the four tests + a stdlib `html.parser`-based visible-text
  extractor and the curated exclusion list (Spec §5.2).
- action: reuse_parser — import `_parse_po_entries` and `_po_files` from `test_i18n_pipeline` (no `polib`).

**acceptance_criteria**
- File exists; all 4 tests marked `@pytest.mark.unit`; no `polib`/`beautifulsoup4` dependency added.
- `test_no_empty_msgstr` fails if any `ru`/`bs` non-header `msgstr` is empty.
- `test_mo_compiled` fails if a `.po` has no compiled `.mo`.
- `test_no_hardcoded_visible_text` passes on the current (now-wrapped) templates and would fail on a
  regression (e.g., re-introducing `<button>Save</button>`).
- `test_extraction_completeness` passes: every template msgid exists in all 3 `.po` files.

---

### T-05 — Add dedicated `i18n` CI job

| Field | Value |
|-------|-------|
| ID | T-05 |
| Title | Add `i18n` job to `.github/workflows/ci.yml` that compiles `.mo` then runs completeness tests |
| Type | implementation |
| Priority | Medium |
| Risk | Medium (edits shared CI config; runs on every PR) |
| Blocked by | T-00 (Q7 placement), T-04 |
| Source | Spec §5.3 (Option A) |

**description**

Add a dedicated `i18n` job (Q7=A) parallel to the existing 5 jobs. Because `.mo` files are gitignored (Spec
§2.3), the job **must** run `python manage.py compilemessages` before `pytest`, otherwise `test_mo_compiled`
and the rendered-`{% trans %}` assertions would fail in CI. The job installs only what's needed
(`uv sync`), compiles, then runs the completeness suite with `--create-db` (per the spec's Option A snippet,
but augmented with the compilemessages step the snippet omits).

**goals**
- `i18n` job is additive (no change to `build`/`test`/`lint`/`typecheck`/`lint-templates`).
- `compilemessages` runs before `pytest`.
- Completeness tests run as part of the fast gate (not nightly/seed).

**files**
- `.github/workflows/ci.yml`
  - targets: a new `i18n` job keyed off the existing job skeleton.
  - semantic_anchors: insert new job after the `lint-templates` job block; within it, add a `compilemessages`
    step before the `pytest` step.

**changes**
- action: add_key — add an `i18n:` job to the workflow YAML.
- action: insert_in_body — within the job, add `run: python manage.py compilemessages` before
  `run: uv run pytest src/backend/apps/ads/tests/test_i18n_completeness.py --create-db`.

**acceptance_criteria**
- `.github/workflows/ci.yml` gains an `i18n` job and none of the existing 5 jobs are modified.
- The `i18n` job runs `compilemessages` then the completeness tests.
- The job has no `seed`/nightly gating (fast gate).

---

### T-06 — Update existing tests asserting on hardcoded Russian text

| Field | Value |
|-------|-------|
| ID | T-06 |
| Title | Make string-asserting tests robust to language (activate `ru`) |
| Type | implementation |
| Priority | Medium |
| Risk | Low |
| Blocked by | T-01, T-02, T-03 |
| Source | Spec §3.5 (tests asserting on hardcoded strings) |

**description**

Four test files assert on Russian text that is now produced by `{% trans %}` + the compiled `ru` catalog (Spec §4.4.1). They must explicitly activate the `ru` language so they assert on the *translated* output rather than on a fallback/`msgid`, and must keep passing after the wrapping + compilation.

**goals**
- Each listed test sets the active language to `ru` before rendering/asserting.
- All four files' affected tests pass under `make test`.

**files**
- `apps/ads/tests/test_auth_nav.py` — targets: tests at L81, L92 asserting `"Подать объявление"`.
- `apps/ads/tests/test_breadcrumbs_render.py` — targets: test at L65 asserting `"Главная"`.
- `apps/ads/tests/test_preferred_city.py` — targets: tests at L139, L147, L180 asserting `"Вся страна"`.
- `apps/ads/tests/test_context_processors.py` — targets: tests at L72, L110 asserting `"Вся страна"`.
  - semantic_anchors: within each affected test, add `from django.utils.translation import override` (or `translation.activate("ru")` / `@override_settings(LANGUAGE_CODE="ru")`) at the start.

**changes**
- action: refactor — add explicit `ru` language activation to the affected test functions; keep the existing Russian assertions (they now validate the real `ru` translation path).

**acceptance_criteria**
- All four files still assert the expected Russian UI strings.
- Each affected test explicitly sets language to `ru`.
- `make test` (fast gate) is green for these modules.

---

### T-07 — Update stale i18n gap-analysis doc

| Field | Value |
|-------|-------|
| ID | T-07 |
| Title | Refresh `docs/99-agent/i18n-translation-pipeline-gap-analysis.md` to current state |
| Type | documentation |
| Priority | Low |
| Risk | Low |
| Blocked by | — |
| Source | Spec §4.5.2 |

**description**

The doc predates the now-operational pipeline (Spec §2.2). Rewrite it to describe the live runtime
pipeline, the catalog state, and the new completeness checks (Spec §4.3), so it no longer misrepresents
the project as "incomplete" on the pipeline itself.

**goals**
- Doc reflects the operational `LanguagePreMiddleware` + context processor + `compilemessages` flow.
- Doc references the new `test_i18n_completeness.py` CI gate and its scope/exclusions.

**files**
- `docs/99-agent/i18n-translation-pipeline-gap-analysis.md`
  - targets: the "current state" / "gap" sections that describe the pipeline as non-operational.
  - semantic_anchors: replace the gap narrative with the operational-pipeline summary from Spec §2.2 and §5.

**changes**
- action: replace_doc — rewrite the gap-analysis sections to reflect Spec §2 (operational pipeline) + §5 (checks).

**acceptance_criteria**
- Doc no longer claims the runtime i18n pipeline is non-functional.
- Doc lists the 4 completeness guards and their scope/exclusions.

---

### T-08 — Add i18n DoD cheatsheet to developer rules

| Field | Value |
|-------|-------|
| ID | T-08 |
| Title | Add i18n Definition-of-Done entry to `commands.md` and `project.md` |
| Type | documentation |
| Priority | Medium |
| Risk | Low |
| Blocked by | T-00 (incorporates confirmed defaults) |
| Source | Spec §4.5.1, §4.6 (PR review checklist) |

**description**

Add a concise, reviewable i18n DoD reminder to the two developer-rules files so the checklist travels with
the rules, per the Definition of Done (Spec §4.5.1).

**goals**
- `commands.md` gains an i18n DoD command/quick-reference entry (makemessages, compilemessages,
  run completeness tests, languages).
- `project.md` gains the i18n PR-review checklist (Spec §4.6).
- Both point at `test_i18n_completeness.py` as the CI gate.

**files**
- `.kilo/rules/commands.md` — targets: add an `i18n` subsection near the test/lint commands.
- `.kilo/rules/project.md` — targets: add an i18n rule item referencing the DoD (§4.1–4.4) and PR checklist (§4.6).

**changes**
- action: add_key / insert — append the i18n DoD entry to each file.

**acceptance_criteria**
- Both files contain an i18n DoD reference with: languages (ru/en/bs), `makemessages`/`compilemessages`
  commands, the completeness-test path, and the ru/bs-msgstr-non-empty rule.
- `project.md` includes the Spec §4.6 PR-review checklist verbatim (or close paraphrase).

---

### T-09 — Verification: fast gate + lint + lint-templates

| Field | Value |
|-------|-------|
| ID | T-09 |
| Title | Verify: `make test` + `make lint` + `make lint-templates` + i18n CI job |
| Type | verification |
| Priority | High |
| Risk | — |
| Blocked by | T-01, T-02, T-03, T-04, T-05, T-06 |
| Source | Spec §9 (Verification Criteria) |

**description**

Final automated gate. Runs the fast test suite (which includes the new `test_i18n_completeness.py` and the
updated existing tests), Python lint/format, template lint, and the i18n CI job locally to prove the DoD is
met end-to-end.

**verification_steps**
- test: `make test` (fast gate, skips `seed`; includes `test_i18n_completeness.py`, `test_i18n_pipeline.py`,
  `test_auth_nav.py`, `test_breadcrumbs_render.py`, `test_preferred_city.py`, `test_context_processors.py`).
- lint: `uv run ruff check src/backend && uv run ruff format --check src/backend`.
- lint-templates: `make lint-templates` (djlint with H901; H901/H030/etc. ignores preserved).
- ci_smoke: run the `i18n` CI job's steps locally — `python manage.py compilemessages` then
  `uv run pytest src/backend/apps/ads/tests/test_i18n_completeness.py --create-db`.
- i18n_guards: assert `ru`/`bs` `.po` have 0 empty `msgstr`; `.mo` compiled.

**pass_criteria**
- `make test` green (0 failures in all listed modules).
- `ruff check` / `ruff format --check` clean.
- `make lint-templates` clean.
- i18n CI smoke passes (compilemessages + completeness tests).
- No regression in the HTMX/static-assertion tests (`test_catalog_filters.py`, `test_listings_sort.py`).

**failure_action:** return the failing task among {T-01..T-06} to rework.

---

### T-10 — Manual multilingual spot-check

| Field | Value |
|-------|-------|
| ID | T-10 |
| Title | Manual: verify `?lang=ru/en/bs` renders correct language with no en→ru fallback |
| Type | verification |
| Priority | Medium |
| Risk | — |
| Blocked by | T-01, T-02, T-03 |
| Source | Spec §9.5 |

**description**

Human spot-check of rendered output across all three languages, the only way to confirm `msgstr` accuracy
and absence of Russian fallback in `en`/`bs` mode (automated checks cannot validate *translation quality*).

**verification_steps**
- smoke_check: start dev server with compiled `ru`/`en`/`bs` `.mo`; load a public listing page with `?lang=ru`, `?lang=en`, `?lang=bs` and a seller dashboard page with each.
- For each `lang`, confirm public-facing visible text (header nav, search placeholder, submit button,
  breadcrumbs, badges, consent banner, login page, dashboard labels, edit-form labels) renders in that
  language and **no** Russian Cyrillic leaks into `en`/`bs` mode.

**pass_criteria**
- `ru`: all public/seller-facing visible text shows Russian.
- `en`: all such text shows English (no Russian fallback).
- `bs`: all such text shows Bosnian (no Russian fallback).
- 403 pages (`HttpResponseForbidden` bodies from T-02) render translated in each language.

**failure_action:** return the affected task among {T-01, T-02, T-03} to rework (e.g., missing `msgstr`
or a string that wasn't wrapped).

---

## 8. Overall Acceptance Criteria (Spec §9)

The multilingual DoD is met when **all** hold:

1. **AC-1** — `make test` (fast gate) passes, including the new `test_i18n_completeness.py`.
2. **AC-2** — `make lint` passes (ruff) with no i18n regressions.
3. **AC-3** — `make lint-templates` passes (djlint, H901 enforced).
4. **AC-4** — The dedicated `i18n` CI job passes on a clean branch.
5. **AC-5** — Manual `?lang=ru/en/bs` spot-check shows correct language, no Russian fallback in `en`/`bs`.
6. **AC-6** — `ru`/`bs` `.po` have 0 untranslated entries; `en` follows Django convention (empty `msgstr`).
7. **AC-7** — No hardcoded visible strings remain in public/seller-facing templates
   (`test_no_hardcoded_visible_text` green).

**DoD mapping:** AC-1↔§4.4.2, AC-2↔§4.4.2, AC-3↔§4.4.2, AC-4↔§4.3, AC-5↔§9.5, AC-6↔§4.2, AC-7↔§4.1+§5.2.

---

## 9. Execution DAG (summary)

```
G0 (parallel, gate-independent)
 ┌────────┐ ┌────────┐ ┌────────┐
 │ T-00   │ │ T-02   │ │ T-07   │
 │ gate   │ │ Python │ │ doc    │
 └───┬────┘ └────┬───┘ └────────┘
     │            │            (T-02 feeds extraction)
     ▼            ▼
G1 (after T-00) ──► T-01 (templates)  T-08 (cheatsheet)   [parallel, disjoint files]
     │                        │
     └────────────────────────┘
                     │
            G2: T-03 (extract + compile .mo)
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
G3: T-04 (completeness tests)   T-06 (update existing tests)   [parallel]
        │
        ▼
G4: T-05 (CI job)
        │
        ▼
        G5: T-10 (manual spot-check)     [can overlap G3/G4; needs only T-01,T-02,T-03]
        │
        ▼
G6: T-09 (final automated verification — make test + lint + lint-templates + CI smoke)
     (depends on T-01,T-02,T-03,T-04,T-05,T-06)
```

**G0:** `T-00` (decision gate) ∥ `T-02` (Python gettext) ∥ `T-07` (doc) — maximum parallelism at start.
**G1:** `T-01` ∥ `T-08` — both unblocked by T-00; disjoint files.
**G2:** `T-03` — extraction waits on all string wrapping (T-01 + T-02) + gate (T-00 Q8).
**G3:** `T-04` ∥ `T-06` — complement each other; disjoint test files; both fed by T-03.
**G4:** `T-05` — CI job waits on the test file (T-04) + gate (T-00 Q7).
**G5:** `T-10` — manual, needs compiled catalog + wrapped output (T-01, T-02, T-03).
**G6:** `T-09` — final gate over all implementation.
