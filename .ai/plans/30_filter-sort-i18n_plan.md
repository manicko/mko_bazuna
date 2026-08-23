---
id: 30_filter-sort-i18n
spec: .ai/problems/29_filter-sort-i18n_spec.md
domain: implementation-plan
spec_status: APPROVED
priority: High
status: Ready for implementation
date: 2026-08-23
stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX MPA · aiogram 3.x · Pydantic v2
---

# Plan 30 — Filter Sort & I18n Pipeline

Transformation of **Spec_29** (`.ai/problems/29_filter-sort-i18n_spec.md`, APPROVED) into a
dependency-aware implementation DAG.

> **Spec-staleness finding:** The spec's §4 "Current State" describes a **pre-Spec_26** state.
> Codebase verification proves Spec_26 (catalog filters & sorting) is **already fully
> implemented** — indexes exist, both view filters are present, NULLS LAST + relevance tiebreaker
> are deployed, option resolution is in place, seed data is populated, chips and pagination URL
> preservation are live, and `format_price` is used. The spec's conceptual task list (T1–T22)
> overlaps heavily with spec 26's already-deployed work, but its **actual remaining gaps** cluster
> into four themes: (1) an incomplete i18n pipeline, (2) sort-UI separation, (3) OLX-style
> dropdown facets, and (4) feature display on list/detail cards.

Spec_29's 22 conceptual tasks are reorganized below into implementation-sequenced, parallelizable
tasks. Key reorganizations:

- **T1–T3 (i18n pipeline) → M-1, M-2, M-3** (build + source + Dockerfile/entrypoint). The i18n
  pipeline has three independent pillars (gettext in Docker builder, makemessages source refresh,
  compilemessages + Makefile targets) that can be built in parallel once their dependency on the
  template tasks is respected.
- **T5/T6 (sort extraction + auto-submit) → S-1, S-2, S-3** (new fragment + remove from form + include).
  Sort lives between `purpose` and apply in `filter_form.html`; it must move before features
  dropdown work to avoid conflicting edits in the same partial.
- **T8/T9 (OLX dropdowns + price inputs) → D-1, D-2**. Features checkboxes become a
  `<details>`/`<summary>` dropdown; price filter gains visible text inputs. Both edit
  `filter_form.html` — sequenced against S-2.
- **T10/T11/T13/T15/T16/T17 (features model + display) → T-03..T-06** (views prefetch → list
  display → detail display → category adequacy → tests). The `AdFeature` model already exists
  (Spec_26 deployed it); only display + prefetch + adequacy remain.
- **T22 (i18n verification tests) → T-13.** A focused test task validating the extraction/compile
  cycle and locale file freshness.

---

## 1. Statement of Scope

Ten implementation tasks (3 build-infra, 3 template/UI, 1 views, 1 prefetch, 1 adequacy, 1 test,
1 verification), two test tasks, touching: the `ads` app (4 views, `ad_list.html`,
`detail.html`, `filter_form.html`), the i18n toolchain (3 `.po` files, Dockerfile, 3 entrypoint
scripts, Makefile), and test modules (`test_detail_context.py`, `test_ad_detail_queries.py`).

**Changes:**
1. **Build infra (M-1, M-2, M-3)** — add gettext to Docker builder stage + `compilemessages` in
   builder, `entrypoint.sh`, `entrypoint-test.sh`; add `makemessages`/`compilemessages` Makefile targets.
2. **Sort extraction (S-1, S-2, S-3)** — create `filter_sort.html` fragment, remove sort `<select>`
   from `filter_form.html`, include fragment in `list.html`.
3. **Features dropdown (D-1)** — convert inline checkbox list in `filter_form.html` to collapsible
   `<details>`/`<summary>` (zero-JS, no Alpine dependency).
4. **Price inputs (D-2)** — add visible `min_price`/`max_price` text inputs to `filter_form.html`.
5. **Prefetch features (T-03)** — add `"features"` to `prefetch_related` in `listings.py`,
   `search.py`, `favorites.py`, and detail view.
6. **List display (T-04)** — add feature tags on list cards in `ad_list.html` via
   `components/feature_tag.html`.
7. **Detail display (T-05)** — add feature tags on `detail.html` via `components/feature_tag.html`.
8. **Category adequacy (T-06)** — validate displayed features belong to the ad's category on
   detail page.
9. **Template display tests (T-13)** — add test asserting `component_tag` filter works.
10. **Test updates (T-11, T-12)** — update prefetch assertion in `test_detail_context.py`, bump
    `_QUERY_BOUND` in `test_ad_detail_queries.py`, add i18n extraction test.
11. **Verification (T-14)** — full suite + lint + typecheck + `compilemessages --check` + AC walkthrough.

**In scope (files):**
- `src/backend/locale/{en,bs,ru}/LC_MESSAGES/django.po` — refresh msgids, fill translations
- `src/backend/templates/ads/partials/filter_form.html` — remove sort, add features dropdown, add price inputs
- `src/backend/templates/ads/partials/filter_sort.html` (new) — extracted sort `<select>`
- `src/backend/templates/components/feature_tag.html` (new) — feature tag component
- `src/backend/templates/ads/partials/ad_list.html` — include sort fragment, feature tags on cards
- `src/backend/templates/ads/detail.html` — feature tags
- `src/backend/apps/ads/views/listings.py` — prefetch `"features"` + detail view prefetch
- `src/backend/apps/search/views/search.py` — prefetch `"features"`
- `src/backend/apps/cabinet/views/favorites.py` — prefetch `"features"`
- `src/backend/apps/ads/templatetags/global_tags.py` — `component_tag` filter (T-13 dependency)
- `docker/Dockerfile` — gettext in builder + compilemessages
- `docker/entrypoint.sh` — compilemessages
- `docker/entrypoint-test.sh` — compilemessages
- `Makefile` — makemessages/compilemessages targets
- `src/backend/apps/ads/tests/test_detail_context.py` — update prefetch assertion (T-11)
- `src/backend/apps/ads/tests/test_ad_detail_queries.py` — bump `_QUERY_BOUND` (T-12)
- `src/backend/apps/ads/tests/test_i18n_pipeline.py` (new) — extraction/compile cycle test (T-13)

**Out of scope:** numeric attribute filters (area, rooms, year, mileage, brand), keyset
pagination, faceted counts, dynamic dependent filters, `pg_trgm`, `Ad`-model column additions,
numeric range slider UIs, any further currency work, and any bot-side i18n (bot runs in single
locale).

---

## 2. Execution DAG

```
M-1  (gettext in Docker builder + compilemessages)            [infra]
M-2  (makemessages/compilemessages Makefile targets)         [infra]
M-3  (compilemessages in entrypoint.sh + entrypoint-test.sh) [infra]

S-1  (create filter_sort.html fragment)                       [template]
  │
  ├─ S-2  (remove sort select from filter_form.html)          [template, blocked by S-1]
  │    │
  │    └─ D-1  (features dropdown in filter_form.html)        [template, blocked by S-2]
  │         │
  │         └─ D-2  (price inputs in filter_form.html)        [template, blocked by D-1]
  │
  └─ S-3  (include filter_sort.html in list.html)             [template, blocked by S-1]

T-03 (prefetch "features" in 4 views)                          [views, blocked by S-2]
  │
  ├─ T-04 (feature tags on list cards: ad_list.html)          [template, blocked by T-03]
  ├─ T-05 (feature tags on detail: detail.html)              [template, blocked by T-03]
  ├─ T-06 (category adequacy validation)                     [view, blocked by T-03]
  └─ T-13 (component_tag test)                               [test, blocked by T-04, T-05]

T-11 (update test_detail_context.py prefetch assertion)       [test, blocked by T-03]
T-12 (bump _QUERY_BOUND in test_ad_detail_queries.py)        [test, blocked by T-03]

M-1, M-2, M-3 ──┐
S-3 ────────────┤
T-04, T-05 ─────┤
T-11, T-12 ─�────┤── T-14 (full verification: suite + lint + typecheck + compilemessages --check)
T-13 ────────────┤
D-1, D-2 ────────┘
```

**Critical path:** S-1 → S-2 → D-1 → D-2 → T-03 → T-04/T-05/T-06 → T-14
**Parallel groups:**
- G0: {M-1, M-2, M-3} (all independent — can build in parallel)
- G1: {S-1} (single — no parallel split possible, other tasks depend on it)
- G2: {S-3} alongside {S-2} (S-3 depends only on S-1, S-2 depends on S-1; both edit different files)
- G3: {D-1, D-2} — wait, D-2 blocked by D-1 (same file, same partial). Actually D-1 and D-2 both
  edit `filter_form.html`. D-2 (price inputs) is in a different region than D-1 (features dropdown),
  but they share the same file. Per dependency rules, sequence them: S-2 → D-1 → D-2.
  Correction: G2 = {S-2, S-3} (different files), then G3 = {D-1}, then G4 = {D-2}.
- G5: {T-03} (all 4 views, different files — but single task aggregates the prefetch change)
- G6: {T-04, T-05, T-06, T-11, T-12, T-13} (all depend on T-03 or template work; independent of each other
  where files don't overlap)
- G7: {T-14}

---

## 3. Task Index

| ID | Title | Stage | Priority | Risk | Blocked by |
|----|-------|-------|----------|------|-----------|
| M-1 | gettext in Docker builder + compilemessages | 0 | Medium | Low | — |
| M-2 | Makefile: makemessages + compilemessages targets | 0 | Medium | Low | — |
| M-3 | compilemessages in entrypoint.sh + entrypoint-test.sh | 0 | Medium | Low | M-1 |
| S-1 | Extract sort `<select>` into `filter_sort.html` fragment | 1 | Low | Low | — |
| S-2 | Remove sort select from `filter_form.html` | 1 | Low | Low | S-1 |
| S-3 | Include `filter_sort.html` in `list.html` | 1 | Low | Low | S-1 |
| D-1 | Features as collapsible `<details>`/`<summary>` dropdown | 2 | Medium | Low | S-2 |
| D-2 | Add visible `min_price`/`max_price` text inputs | 2 | Low | Low | D-1 |
| T-03 | Prefetch `"features"` in 4 detail/list views | 3 | Medium | Medium | S-2 |
| T-04 | Feature tags on list cards (`ad_list.html` + `component_tag.html`) | 3 | Low | Low | T-03, S-3 |
| T-05 | Feature tags on detail page (`detail.html`) | 3 | Low | Low | T-03 |
| T-06 | Category adequacy validation on detail | 3 | Low | Low | T-03 |
| T-11 | Update `test_detail_context.py` prefetch assertion | 4 | Low | Low | T-03 |
| T-12 | Bump `_QUERY_BOUND` in `test_ad_detail_queries.py` | 4 | Low | Low | T-03 |
| T-13 | `component_tag` filter + i18n pipeline test | 4 | Low | Low | T-04, T-05 |
| T-14 | Full verification: suite + lint + typecheck + compilemessages --check | 5 | High | High | all |

---

## 4. Current-State vs. Gaps (verified)

| Concern | State | Evidence |
|---------|-------|----------|
| Spec_26 filters (purpose, features) | **Already implemented** | `listings.py` line 55 `listing_purpose__in` clause; `search.py` has same; `filter_form.html` has purpose dropdown; seed data populated |
| Sort relevance tiebreaker + NULLS LAST | **Already implemented** | `listings.py` `order_by("-rank", "-published_at", "-id")`; `search.py` same; price sorts use `NULLS LAST` |
| i18n `.po` files — msgstr filled | **Not done** — all `msgstr ""` | `django.po` ×3, 24 total msgids, zero translations filled |
| i18n `.mo` files | **Missing** | No `.mo` files in `src/backend/locale/{en,bs,ru}/LC_MESSAGES/` |
| `compilemessages` in Docker | **Not wired** | Dockerfile has `gettext` only in runtime stage; builder stage has no gettext, no compile step |
| `compilemessages` in entrypoints | **Absent** | `entrypoint.sh`, `entrypoint-test.sh`, `entrypoint-bot.sh` — zero mentions of compilemessages |
| Makefile i18n targets | **Absent** | No `makemessages` or `compilemessages` target in Makefile |
| POT-Creation-Date / msgstrs up to date | **Stale** | POT-Creation-Date 2026-07-27; missing strings from `filter_form.html` and current `list.html`/`ad_list.html` |
| Sort `<select>` embedded in `filter_form.html` | **Yes** — between purpose and apply | `filter_form.html` line 30 `Sort by` `<select>` |
| `filter_sort.html` fragment | **Does not exist** | grep returns zero results |
| HTMX auto-submit on sort change | **Absent** | Sort `<select>` has no `hx-` attributes |
| Features as inline checkboxes | **Yes** (not dropdown) | `filter_form.html` renders `feature.id` as `<input type="checkbox">` in a `flex-wrap` div |
| Features as `<details>`/`<summary>` dropdown | **Absent** | No `<details>` in `filter_form.html` |
| Price filter visible inputs | **Absent** | `filter_form.html` price uses `<input type="hidden">` only (lines 14–15) |
| `AdFeature` model | **Already implemented** | `apps/ads/models.py` — `AdFeature` class, `sort_order` field, `Meta.indexes`, `IX_ad_features_feature_id` index |
| `"features"` in `prefetch_related` | **Absent** | All 4 views (`ad_detail()`, `listings()`, `search()`, `favorites_list()`) have `prefetch_related=("images", "user__trust_score")` or none — no `"features"` |
| `components/feature_tag.html` | **Does not exist** | grep returns zero |
| Feature tags on list cards | **Absent** | `ad_list.html` renders no features |
| Feature tags on detail | **Absent** | `detail.html` renders no features |
| Category adequacy check on detail | **Absent** | `ad_detail()` has no feature-category validation |
| Alpine.js in project | **Not a dependency** | grep `alpine`/`Alpine`/`x-data`/`@click` in `templates/` returns zero; `.venv` has no Alpine.js package |
| `component_tag` template filter | **Absent** | grep returns zero — needed for T-13 test |

---

## 5. Risk & Rollout Notes

- **i18n pipeline (M-1..M-3) is infrastructure risk, not schema risk.** Adding gettext to the
  builder stage and wiring compilemessages into entrypoints is low-risk but critical — without it,
  translations never compile and `.mo` files are absent at runtime. The three tasks are independent
  (different files: Dockerfile, entrypoint.sh, Makefile) and can build in parallel; only M-3
  depends on M-1 (the builder must have gettext to compile).
- **`filter_form.html` contention (S-2 → D-1 → D-2).** Three tasks edit the same partial. They
  must sequence strictly: remove sort first (changes line numbers), then features dropdown (new
  region), then price inputs (different region). Reordering risks edit conflicts.
- **Views prefetch (T-03) affects query-count tests.** `test_ad_detail_queries.py` has
  `_QUERY_BOUND = 15` and `test_detail_context.py` asserts `prefetch_related` is called with exactly
  `("images", "user__trust_score")`. Both must be updated; the detail test's N+1 assertion in
  `test_ad_detail_queries.py` likely needs the bound bumped to 16 (one extra prefetch_related load
  for features on detail page).
- **Zero-JS decision for features dropdown.** Alpine.js is not installed in `.venv` and not loaded
  in any template. Per spec §I-3 decision criteria, use native `<details>`/`<summary>` — no
  JavaScript dependency introduced.
- **Sort auto-submit (HTMX).** The sort `<select>` in the new `filter_sort.html` fragment must use
  `hx-get`/`hx-push-url` to auto-submit on change, matching the existing filter-form pattern
  already deployed in Spec_26.
- **`component_tag` filter for T-13.** A small template-tag helper (`component_tag`) is needed to
  render `components/feature_tag.html` with a context dict. If one already exists in
  `global_tags.py`, reuse it; if not, create it — this is part of T-13, not a separate task.
- **No migration needed.** The `AdFeature` model and all related indexes (`IX_ad_features_feature_id`,
  `IX_ads_pub_purpose`) are already deployed by Spec_26. No schema changes are required for spec 29.

---

## 6. Overall Acceptance Criteria

1. All 24 `msgstr` in the 3 `.po` files are filled with correct translations; `.mo` files exist in
   `src/backend/locale/{en,bs,ru}/LC_MESSAGES/`.
2. `compilemessages` runs in the Docker builder stage, `entrypoint.sh`, and `entrypoint-test.sh`;
   `makemessages`/`compilemessages` targets exist in the Makefile.
3. Sort `<select>` extracted to `filter_sort.html` with HTMX auto-submit; removed from
   `filter_form.html`; included in `list.html`.
4. Features rendered as a collapsible `<details>`/`<summary>` dropdown in `filter_form.html`;
   visible `min_price`/`max_price` text inputs added.
5. `"features"` in `prefetch_related` of all 4 catalog/detail views (listings, search, favorites,
   detail).
6. Feature tags rendered on list cards (`ad_list.html`) and detail page (`detail.html`) via
   `components/feature_tag.html`.
7. Category adequacy validation on detail page (features displayed belong to the ad's category).
8. `test_detail_context.py` prefetch assertion updated to include `"features"`; `_QUERY_BOUND`
   bumped in `test_ad_detail_queries.py`.
9. `component_tag` template filter exists and tested; i18n extraction/compile test passes.
10. Full suite passes with `--create-db`; `compilemessages --check` passes; lint + typecheck clean.

---

## 7. Task Specifications

---

## M-1 — gettext in Docker builder + compilemessages in builder stage

| Field | Value |
|-------|-------|
| **ID** | M-1 |
| **Title** | Add gettext to Docker builder stage and run compilemessages |
| **Type** | Build / infrastructure |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | — |
| **source_reference** | spec §I-1, §3.3, Dockerfile builder stage |

**description**
The Docker `Dockerfile` currently installs `gettext` only in the runtime stage, not the
multi-stage builder. Without gettext in the builder, `compilemessages` cannot run during image
assembly, so no `.mo` files are produced. Add `gettext` to the builder stage's package list and
add a `RUN` step executing `python src/backend/manage.py compilemessages` after the app code and
translations are copied into the builder.

**goals**
- `.mo` files compiled at image build time (not runtime).
- No runtime `apt-get` dependency on gettext in the lean runtime image.

**files**
- path: `docker/Dockerfile`

**changes**
- action: edit — add `gettext` to the builder stage's `RUN apt-get install` list.
- action: edit — add `RUN python src/backend/manage.py compilemessages` after code copy in builder.

**acceptance_criteria**
- Builder stage installs `gettext`.
- Builder runs `compilemessages` producing `.mo` files under `locale/`.
- `makemigrations --check` still clean (no incidental model changes).
- Runtime image does not require gettext.

---

## M-2 — Makefile: makemessages + compilemessages targets

| Field | Value |
|-------|-------|
| **ID** | M-2 |
| **Title** | Add `makemessages` and `compilemessages` targets to Makefile |
| **Type** | Tooling |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | — |
| **source_reference** | spec §I-2 |

**description**
The Makefile has no i18n targets. Add `makemessages` (runs `django-admin makemessages` for all
configured languages, excluding `.venv`/`node_modules`/media) and `compilemessages` (runs
`django-admin compilemessages` with `.po` freshness). These targets let developers refresh
msgids after template changes and compile `.mo` locally for the test DB.

**goals**
- Developer can run `make makemessages` + `make compilemessages` for i18n workflow.
- Targets respect existing project conventions (see Makefile patterns).

**files**
- path: `Makefile`

**changes**
- action: edit — append `makemessages:` target running `cd src/backend && django-admin makemessages -l en -l bs -l ru --no-location`.
- action: edit — append `compilemessages:` target running `cd src/backend && django-admin compilemessages`.

**acceptance_criteria**
- `make makemessages` produces updated `.po` files with correct msgids.
- `make compilemessages` produces `.mo` files in all `LC_MESSAGES/` dirs.
- Targets use the existing project's Python entry (`uv run` or `django-admin` per Makefile convention).

---

## M-3 — compilemessages in entrypoint.sh + entrypoint-test.sh

| Field | Value |
|-------|-------|
| **ID** | M-3 |
| **Title** | Run compilemessages in container entrypoints |
| **Type** | Infrastructure |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | M-1 |
| **source_reference** | spec §I-4, §I-5 |

**description**
Neither `entrypoint.sh` nor `entrypoint-test.sh` runs `compilemessages` before starting Django.
Add a `python manage.py compilemessages` call in both entrypoints (after DB readiness check, before
`gunicorn`/`pytest`), mirroring the existing `collectstatic` pattern. This ensures `.mo` files
are fresh at deploy even if the image was built without the builder compile step.

**goals**
- Production runtime compiles messages on every container start.
- Test container compiles messages before pytest.

**files**
- path: `docker/entrypoint.sh`
- path: `docker/entrypoint-test.sh`

**changes**
- action: edit — add `python manage.py compilemessages` to `entrypoint.sh` before gunicorn start.
- action: edit — add `python manage.py compilemessages` to `entrypoint-test.sh` before pytest.

**acceptance_criteria**
- `entrypoint.sh` compiles messages; no error if gettext missing (graceful fallback).
- `entrypoint-test.sh` compiles messages; test DB has `.mo` files available for `activate`.

---

## S-1 — Extract sort `<select>` into `filter_sort.html` fragment

| Field | Value |
|-------|-------|
| **ID** | S-1 |
| **Title** | Create `templates/ads/partials/filter_sort.html` with extracted sort select |
| **Type** | Template (new file) |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | — |
| **source_reference** | spec §4.1 (sort currently embedded in filter_form at line 30) |

**description**
The sort `<select>` currently lives inline inside `filter_form.html` between the `purpose`
dropdown and the apply button. Extract it into a new partial template
`templates/ads/partials/filter_sort.html` that renders the same `<select name="sort">` with
`AdSort` options, and adds HTMX auto-submit attributes (`hx-get`, `hx-push-url`) matching the
existing filter-form pattern from Spec_26 so changing the sort instantly re-submits the form via
GET and updates the URL without a separate "Apply" click.

**goals**
- Sort control isolated in its own partial (separation of concerns, project rule 7).
- HTMX auto-submit on sort change (no JS).
- Preserves current sort param from view context.

**files**
- path: `src/backend/templates/ads/partials/filter_sort.html` (new)

**changes**
- action: add_file — `filter_sort.html` containing `<select name="sort" hx-get="{% url 'ads:listings' %}" hx-push-url="true" hx-trigger="change">` with `{% for val, label in sort_choices %}` `<option value="{{ val }}" {% if val == current_sort %}selected{% endif %}>{{ label }}</option>` `{% endfor %}`.
- action: no_code — reference existing `AdSort` enum from `components/enums.py` for option values; receive `current_sort` and `sort_choices` from view context.

**acceptance_criteria**
- New `filter_sort.html` partial renders the sort `<select>` with HTMX auto-submit.
- Sort options match `AdSort` enum values.
- `current_sort` from context is reflected in the selected option.

---

## S-2 — Remove sort select from `filter_form.html`

| Field | Value |
|-------|-------|
| **ID** | S-2 |
| **Title** | Remove the inline sort `<select>` from `filter_form.html` |
| **Type** | Template edit |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | S-1 |
| **source_reference** | spec §4.1 |

**description**
Remove the sort `<select>` block (and its surrounding label/div) from `filter_form.html`. The
sort control is now served by `filter_sort.html` (S-1). This edit must happen after S-1 to avoid
a window where sort is missing from the UI.

**goals**
- No duplicate sort controls.
- `filter_form.html` no longer contains the sort `<select>`.

**files**
- path: `src/backend/templates/ads/partials/filter_form.html`

**changes**
- action: delete_in_body — remove the `<select>` + label for sort from `filter_form.html`.

**acceptance_criteria**
- `filter_form.html` has zero `<select name="sort">` elements.
- No layout disruption (the surrounding purpose/apply structure remains intact).

---

## S-3 — Include `filter_sort.html` in `list.html`

| Field | Value |
|-------|-------|
| **ID** | S-3 |
| **Title** | Add `{% include 'ads/partials/filter_sort.html' %}` to `list.html` |
| **Type** | Template edit |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | S-1 |
| **source_reference** | spec §4.2 (sort should appear near top of list page, before filter form) |

**description**
Include the new `filter_sort.html` partial in `list.html` at the position where the sort control
previously appeared (before the filter form, after the results count). Pass `current_sort` and
`sort_choices` from the `listings()` view context if not already present.

**goals**
- Sort control visible on the listings page in its expected position.
- No visual regression in page layout.

**files**
- path: `src/backend/templates/ads/list.html`
- path: `src/backend/apps/ads/views/listings.py` (if `current_sort`/`sort_choices` not in context)

**changes**
- action: edit — add `{% include 'ads/partials/filter_sort.html' with current_sort=... %}` at the sort position in `list.html`.
- action: edit — (if needed) add `current_sort` and `sort_choices` to `listings()` context.

**acceptance_criteria**
- Listings page renders the sort `<select>` via the included partial.
- Changing sort triggers HTMX GET and updates URL.

---

## D-1 — Features as collapsible `<details>`/`<summary>` dropdown

| Field | Value |
|-------|-------|
| **ID** | D-1 |
| **Title** | Convert inline feature checkboxes to `<details>`/`<summary>` dropdown in `filter_form.html` |
| **Type** | Template edit |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | S-2 |
| **source_reference** | spec §4.3 (OLX-style dropdown facet) |

**description**
Currently, features in `filter_form.html` render as a flat `flex-wrap` div of `<input type="checkbox">`
elements with no grouping. Convert this into a collapsible dropdown using native `<details>` and
`<summary>` elements (zero-JS — no Alpine.js, confirmed absent from project). The dropdown label
displays the feature group name; on expand, checkboxes for that group's features appear. Group
features by `AdFeature.group` (or `category` FK) if available, otherwise render all in a single
dropdown labeled "Features".

**goals**
- Features presented as a collapsible dropdown (OLX-style).
- No JavaScript dependency (native `<details>`/`<summary>`).
- Checkbox values and `name="features"` attribute preserved for form submission.

**files**
- path: `src/backend/templates/ads/partials/filter_form.html`

**changes**
- action: replace_in_body — wrap feature checkboxes in `<details><summary>Features</summary>...<input type="checkbox" name="features" ...>...</details>` structure.

**acceptance_criteria**
- No `flex-wrap` div of bare checkboxes remains in `filter_form.html`.
- Features render inside a `<details>`/`<summary>` dropdown.
- Form submission with `name="features"` unchanged.
- Page works without JavaScript enabled.

---

## D-2 — Add visible `min_price`/`max_price` text inputs

| Field | Value |
|-------|-------|
| **ID** | D-2 |
| **Title** | Add visible price-range inputs to `filter_form.html` |
| **Type** | Template edit |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | D-1 |
| **source_reference** | spec §4.4 (price currently hidden inputs only, lines 14–15) |

**description**
The price filter in `filter_form.html` currently uses two `<input type="hidden">` elements for
`min_price` and `max_price` (lines 14–15), meaning the buyer cannot set a price range. Replace
these with visible `<input type="number">` elements labeled "Min price" and "Max price",
using the `format_price`-aware EUR scale (per Spec_26, price sort/filter operates on
`price_normalized_eur`). Inputs use `name="min_price"` / `name="max_price"`, are empty by default,
and include `step="0.01"` and `min="0"`.

**goals**
- Buyer can see and edit price-range filters.
- Input names unchanged for view compatibility.
- No hidden-only inputs remain.

**files**
- path: `src/backend/templates/ads/partials/filter_form.html`

**changes**
- action: replace_in_body — replace `<input type="hidden" name="min_price" ...>` and `<input type="hidden" name="max_price" ...>` with visible `<input type="number">` elements with labels.

**acceptance_criteria**
- `filter_form.html` has visible `<input type="number" name="min_price">` and `<input type="number" name="max_price">`.
- No `<input type="hidden" name="min_price">` or `<input type="hidden" name="max_price">`.
- Inputs render with `step="0.01"`, `min="0"`.

---

## T-03 — Prefetch `"features"` in 4 catalog/detail views

| Field | Value |
|-------|-------|
| **ID** | T-03 |
| **Title** | Add `"features"` to `prefetch_related` in listings, search, favorites, detail |
| **Type** | View refactor |
| **Priority** | Medium |
| **Risk** | Medium (N+1 + query-count test impact) |
| **Blocked by** | S-2 |
| **source_reference** | spec §6.1, §6.5; test_detail_context.py prefetch assertion; AdFeature model already exists |

**description**
Four views currently `prefetch_related` only `images` (and in some cases `user__trust_score`).
Add `"features"` to each so the template can render feature tags without triggering an extra query
per ad (N+1). The `AdFeature` model and its `Ad.features` M2M are already deployed by Spec_26;
this task only extends the prefetch.

- `apps/ads/views/listings.py` `listings()` — currently `prefetch_related("images", "user__trust_score")` → add `"features"`.
- `apps/ads/views/listings.py` `ad_detail()` — currently `prefetch_related(...)` → add `"features"`.
- `apps/search/views/search.py` `search()` — currently `prefetch_related("images", "user__trust_score")` → add `"features"`.
- `apps/cabinet/views/favorites.py` `favorites_list()` — currently `prefetch_related("images", "user__trust_score")` → add `"features"`.

**goals**
- All catalog-detail and list views prefetch `features` in one query.
- No N+1 when templates access `ad.features.all`.

**files**
- path: `src/backend/apps/ads/views/listings.py`
- path: `src/backend/apps/search/views/search.py`
- path: `src/backend/apps/cabinet/views/favorites.py`

**changes**
- action: edit — add `"features"` to each `prefetch_related(...)` call.

**acceptance_criteria**
- `grep -rn "prefetch_related" src/backend/apps/ads/views/listings.py src/backend/apps/search/views/search.py src/backend/apps/cabinet/views/favorites.py` shows `"features"` in all four views.
- No per-row query when accessing `ad.features.all` in templates.

---

## T-04 — Feature tags on list cards (`ad_list.html` + `feature_tag.html`)

| Field | Value |
|-------|-------|
| **ID** | T-04 |
| **Title** | Render feature tags on list cards via `components/feature_tag.html` |
| **Type** | Template (new component + edit) |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-03, S-3 |
| **source_reference** | spec §6.3 (list cards show features) |

**description**
Create `templates/components/feature_tag.html` — a small macro-style partial rendering a single
`AdFeature` as a `<span>` tag with `data-feature-id` and the feature's display name. Then include
it in `ad_list.html` inside each ad card, iterating `ad.features.all` to render tags beneath the
ad title. Use Django's `{% include %}` with `only` for isolation.

**goals**
- List cards show feature tags.
- Reusable component partial for feature tags.
- No N+1 (features prefetched by T-03).

**files**
- path: `src/backend/templates/components/feature_tag.html` (new)
- path: `src/backend/templates/ads/partials/ad_list.html`

**changes**
- action: add_file — `feature_tag.html`: `<span class="feature-tag" data-feature-id="{{ feature.id }}">{{ feature.name }}</span>`.
- action: edit — in `ad_list.html`, inside the ad card loop, add `{% for feature in ad.features.all %}{% include 'components/feature_tag.html' with feature=feature only %}{% endfor %}`.

**acceptance_criteria**
- `components/feature_tag.html` exists and renders a feature as a tagged `<span>`.
- `ad_list.html` iterates `ad.features.all` and includes `feature_tag.html`.
- Tags appear beneath the ad title on list cards.

---

## T-05 — Feature tags on detail page (`detail.html`)

| Field | Value |
|-------|-------|
| **ID** | T-05 |
| **Title** | Render feature tags on the ad detail page |
| **Type** | Template edit |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-03 |
| **source_reference** | spec §6.4 (detail page shows features) |

**description**
Include `components/feature_tag.html` in `detail.html`, iterating `ad.features.all` to render
feature tags. Position them in the ad meta section (near price/category), matching the list card
layout. Uses the same partial created in T-04.

**goals**
- Detail page shows the same feature tags as list cards.
- Consistent rendering via shared component.

**files**
- path: `src/backend/templates/ads/detail.html`

**changes**
- action: edit — add `{% for feature in ad.features.all %}{% include 'components/feature_tag.html' with feature=feature only %}{% endfor %}` in the meta section.

**acceptance_criteria**
- `detail.html` renders feature tags via `components/feature_tag.html`.
- Tags positioned in the ad meta section.

---

## T-06 — Category adequacy validation on detail page

| Field | Value |
|-------|-------|
| **ID** | T-06 |
| **Title** | Validate displayed features belong to the ad's category |
| **Type** | View refactor |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-03 |
| **source_reference** | spec §8.1 (category-aware feature adequacy) |

**description**
The `ad_detail()` view should filter the prefetched `ad.features` so only features whose associated
category matches (or is a parent of) the ad's `category` are displayed. This prevents showing a
feature tag from one category on an ad in a different category (e.g., "mileage" on a real-estate
ad). Implement as a view-level filter: `ad.features.filter(category=ad.category)` (or a precomputed
set) passed to the template as `display_features`, rather than filtering in the template. The
`AdFeature` model has a `category` FK (verified in models).

**goals**
- Detail page only shows feature tags relevant to the ad's category.
- No template-level category filtering logic (separation of concerns).

**files**
- path: `src/backend/apps/ads/views/listings.py` (wherever `ad_detail()` lives)

**changes**
- action: edit — compute `display_features = ad.features.filter(category=ad.category)` (or equivalent) and pass to template context; update `detail.html` to iterate `display_features` instead of `ad.features.all`.

**acceptance_criteria**
- Detail template iterates `display_features`, not `ad.features.all` directly.
- Features from a different category are excluded.

---

## T-11 — Update `test_detail_context.py` prefetch assertion

| Field | Value |
|-------|-------|
| **ID** | T-11 |
| **Title** | Add `"features"` to expected `prefetch_related` assertion |
| **Type** | Test update |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-03 |
| **source_reference** | `test_detail_context.py` asserts `prefetch_related` called with exactly `("images", "user__trust_score")` |

**description**
`test_detail_context.py` contains an assertion that the detail view calls `prefetch_related` with
exactly `("images", "user__trust_score")`. After T-03 adds `"features"` to the prefetch, this
assertion must be updated to `("images", "user__trust_score", "features")` — otherwise the test
fails on a tuple-length mismatch.

**goals**
- Test assertion matches the new prefetch list.
- Tests stay green after T-03.

**files**
- path: `src/backend/apps/ads/tests/test_detail_context.py`

**changes**
- action: edit — change the expected `prefetch_related` tuple to include `"features"`.

**acceptance_criteria**
- `test_detail_context.py` passes with the updated assertion.
- `pytest` for this module is green.

---

## T-12 — Bump `_QUERY_BOUND` in `test_ad_detail_queries.py`

| Field | Value |
|-------|-------|
| **ID** | T-12 |
| **Title** | Increase `_QUERY_BOUND` to accommodate features prefetch |
| **Type** | Test update |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-03 |
| **source_reference** | `test_ad_detail_queries.py` has `_QUERY_BOUND = 15` |

**description**
`test_ad_detail_queries.py` asserts that the detail page uses at most `_QUERY_BOUND = 15` queries.
Adding `"features"` to `prefetch_related` (T-03) adds exactly one additional prefetch query (the
features M2M join), so the detail page will execute 16 queries. Bump `_QUERY_BOUND` from 15 to 16.

**goals**
- Query-count test reflects the new prefetch.
- Detail page still well within reasonable query budget.

**files**
- path: `src/backend/apps/ads/tests/test_ad_detail_queries.py`

**changes**
- action: edit — change `_QUERY_BOUND = 15` to `_QUERY_BOUND = 16`.

**acceptance_criteria**
- `test_ad_detail_queries.py` passes with `_QUERY_BOUND = 16`.
- No query-count regression beyond the one expected additional prefetch.

---

## T-13 — `component_tag` filter + i18n pipeline test

| Field | Value |
|-------|-------|
| **ID** | T-13 |
| **Title** | Add `component_tag` template filter + test extraction/compile cycle |
| **Type** | Feature (template tag) + Test |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-04, T-05 |
| **source_reference** | spec §5.2 (component-based feature display); i18n spec §3 |

**description**
Part A: The `feature_tag.html` component (T-04) needs a small template-tag helper to be rendered
with a context dict. Check `apps/ads/templatetags/global_tags.py` for an existing `component_tag`
filter; if absent, add one that wraps `{% include %}` with a `feature` context variable. This
keeps the include DRY and testable.

Part B: Create `test_i18n_pipeline.py` asserting that `.po` files have all `msgstr` filled (no
empty translations remain) and that `compilemessages` succeeds without warnings. This is a
regression guard for the i18n pipeline tasks (M-1–M-3).

**goals**
- `component_tag` filter exists and renders `feature_tag.html` with context.
- Test guards against empty `msgstr` and broken compile.

**files**
- path: `src/backend/apps/ads/templatetags/global_tags.py` (add or reuse `component_tag`)
- path: `src/backend/apps/ads/tests/test_i18n_pipeline.py` (new)

**changes**
- action: add_or_reuse — `component_tag` filter in `global_tags.py` if not already present.
- action: add_test — `test_i18n_pipeline.py`: (1) scan all 3 `django.po` files, assert no `msgstr ""`
  after a `msgid` line; (2) run `compilemessages` via subprocess and assert exit code 0.

**acceptance_criteria**
- `component_tag` filter importable and renders feature tag.
- `test_i18n_pipeline.py` passes: all 24 msgids have non-empty `msgstr`; `compilemessages` exits 0.

---

## T-14 — Full verification

| Field | Value |
|-------|-------|
| **ID** | T-14 |
| **Title** | Full suite + lint + typecheck + compilemessages --check + AC walkthrough |
| **Type** | Verification |
| **Priority** | High |
| **Risk** | High |
| **Blocked by** | all prior |

**description**
Final verification gate: run the complete test suite (`make test`), lint (`uv run ruff check .`),
typecheck (`uv run basedpyright src/backend src/telegram_bot`), and `compilemessages --check`
to confirm `.po`/`.mo` consistency. Walk every acceptance criterion from section 6 to confirm
completeness.

**goals**
- No regressions from any task in this plan.
- i18n pipeline produces compiled `.mo` files.
- All AC items verified.

**files**
- path: (no code files — verification step)

**changes**
- action: no_code — run commands, record results.

**acceptance_criteria**
- `make test` passes (fast suite, skips nightly `seed`).
- `uv run ruff check .` clean.
- `uv run basedpyright src/backend` clean (or baseline-known warnings only).
- `python manage.py compilemessages --check` exits 0.
- All 10 acceptance criteria from §6 confirmed.

---
