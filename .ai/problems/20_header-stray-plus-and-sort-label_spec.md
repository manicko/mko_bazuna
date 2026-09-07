# Spec_20 — Fix stray `+` in catalog header CTA and stack the Sort filter label above its control

| Field | Value |
|---|---|
| **Problem source** | `.ai/problems/Problem_04.md` (UI bugs: catalog header `+` text node; Sort label side-by-side in filter form) |
| **Status** | ✅ Spec complete (PO decisions: 1-А, 2-А, 3-А) |
| **Researcher task** | `ses_f842b7940ffeX3byxNnrH57Bf4` (completed — see R1–R6) |
| **Related specs** | Spec_19 (`19_search-term-preservation-on-category-switch...`) |
| **Affected files** | `src/backend/templates/components/header_catalog.html` (line 34) `src/backend/templates/ads/partials/filter_form.html` (lines 112–133) |
| **Risk** | Low |

---

## 1. Problem statement

Two UI defects, reported together in `Problem_04.md`:

1. **Stray `+` text node** — A literal `+` is rendered to the right of (i.e. outside) the "Submit an ad" CTA button in the catalog header.
2. **Sort label side-by-side** — The "Sort" filter label is laid out next to its `<select>` (left of control) instead of above it, breaking consistency with every other filter field in the same form.

---

## 2. Scope

### In scope (files to edit)

| File | Lines | Defect |
|---|---|---|
| `src/backend/templates/components/header_catalog.html` | 34 | Stray `+` (Bug 1) |
| `src/backend/templates/ads/partials/filter_form.html` | 112–133 | Sort label/side-by-side (Bug 2) |

### Out of scope

- No changes to `{% telegram_deep_link %}` tag implementation (`telegram_tags.py`). Per R3, the tag exposes no `label`/`icon` kwarg, but **no PO answer requires adding one**.
- No restoration of `data-place-ad` / `rel="noopener"` (dropped in `5a1f936a`). R1 confirms `data-place-ad` is dormant (no JS handler, per audit `block-c-deep-link-tag-migration.md:197`); not required for either defect.
- No i18n work — no new translatable strings introduced (see Section 7).
- No test authoring required — existing tests are preserved (see Section 6).

---

## 3. Root cause

### Bug 1 — Stray `+`

- **Current (buggy) markup** — `header_catalog.html:34`:
  ```django
  {% telegram_deep_link "create_ad" classes="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700" target="_blank" %}+
  ```
  The `+` sits **after `%}`** as a sibling text node; the `{% telegram_deep_link %}` tag renders its own `<a>…</a>` button, so the `+` is emitted *after* the button, appearing as stray text to its right.

- **Origin** — Commit `5a1f936a` ("feat(contact-us): migrate to SiteConfig-backed telegram_deep_link tag") replaced an inline:
  ```django
  <a … data-place-ad>+ {% trans "Submit an ad" %}</a>
  ```
  with the tag call. The migration **moved the `+` outside** the button (it was *inside* the `<a>` previously as the label prefix `+ Submit an ad`), and simultaneously **dropped** `data-place-ad` and `rel="noopener"`.

- **Intent** — R1 confirms the `+` was an intentional "+ prefix" affordance (common "add new" convention) on the CTA label. Post-migration the tag emits the label from its own `_LABELS[CREATE_AD]` (`telegram_tags.py:63-68,149`); the `+` was stranded outside the `<a>` and is no longer part of the visible label.

### Bug 2 — Sort label side-by-side

- **Current (buggy) markup** — `filter_form.html:112–133`:
  ```django
  <div class="flex items-end gap-2">
      <label class="block text-sm font-medium text-gray-700 mb-1">{% trans "Sort" %}</label>
      <select name="sort" id="id_sort">…</select>
  </div>
  ```
  The flex-row wrapper overrides the label's `block`+`mb-1`, placing label **left of** the `<select>` (bottom-aligned via `items-end`).

- **Contrast with sibling filters** — Every other filter in `filter_form.html` uses a plain `<div>` wrapper with a stacked label-above layout:
  - Purpose (`:15-28`), Condition (`:32-46`), Min price (`:48-57`), Max price (`:58-67`), Features (`:68-103`) — all `<label class="block … mb-1">` immediately above the control, no flex wrapper.

- **Include path** — `filter_form.html` is included from exactly one site: `ads/partials/ad_list.html:14` (`{% include "ads/partials/filter_form.html" %}`), which renders the listings view (`/` and `/category/<slug>/`) **and** the search view (`/search/`).

---

## 4. Research findings

### R1 — Origin & intent of the stray `+`
- Verified via `git blame` + `git show 5a1f936a` against the working tree.
- Before: `+` **inside** the `<a>` (`+ {% trans "Submit an ad" %}`).
- After: `+` stranded **after `%}`** (sibling text node).
- Same commit dropped `data-place-ad` + `rel="noopener"`.

### R2 — Repo-wide scan for `+` near the create_ad CTA
- `+` as a prefix/icon appears **only** at `header_catalog.html:34`.
- No design-system `+`/FAB convention (see `docs/01-spec/design-system.md:111-124` — Button variants: Primary/Secondary/Disabled/Danger/Success/Icon; **no** "+"-prefix variant).
- Locale `.po` never contained `+`; it was a literal never extracted.

### R3 — Feasibility of keeping `+` inside the button via the tag
- Tag signature (`telegram_tags.py:94-101`): only `command`, `classes`, `target` — no `label`/`icon`/`attrs` passthrough.
- Label is sourced internally from `_LABELS[CREATE_AD]` (`:63-68,149`) and used for both `aria-label` and visible text (`:164-176`).
- To keep `+` inside the button, the tag must be extended (trivial plain-text `label=` kwarg; moderate SVG `icon=` kwarg). Not selected — PO chose removal.

### R4 — Scope of the Sort label
- `{% trans "Sort" %}` + `<select name="sort"` appear in **one** template only: `filter_form.html:112-133`.

### R5 — Test impact
- No test asserts on `+` literal, `flex items-end`/`gap-2`, `data-place-ad`, or `rel="noopener"`.
- Tests asserting on the create_ad tag render (`test_rtl_obfuscation.py:200`) call the tag directly, not `header_catalog.html` — unaffected.
- Tests asserting on rendered sort output (`test_catalog_filters.py`, `test_listings_sort.py`, `TestSortOnSearchResults`) assert on **ordering/context/`<select name="sort"` substring** — unaffected by wrapper-class change.

### R6 — Best practices: filter/sort label placement
- **Top-aligned label-above** is the dominant, most-accessible, most-mobile-friendly layout and is the **consistency norm within this form** (Baymard; Carbon `Dropdown` "Default style = label outside and above").
- Side-by-side (label left of control) is acceptable **only** for a standalone inline sort in a compact toolbar — not for a field inside a multi-field label-above form (Baymard: "It's best if you can stick just one approach per form").
- Recommendation (carried forward): move "Sort" label above the `<select>` to match the sibling filters.

---

## 5. Requirements / decisions

| # | Requirement | Decision | Rationale |
|---|---|---|---|
| D1 | Stray `+` rendered outside the "Submit an ad" CTA | **Remove** the `+` entirely. Do **not** restore "Submit an ad" text or any `+`/icon into the button. | PO answer 1=А (removal). R1/R2: `+` was an undocumented inline artifact; no design-system plus convention exists. Tag has no icon kwarg; restoring would couple a literal into the template. |
| D2 | Sort label side-by-side with its `<select>` | **Stack** the label above the `<select>`; adopt the same `block` + `mb-1` label + plain-`<div>` wrapper pattern used by every other filter in `filter_form.html`. | PO answer 2=А (label-above). R6: consistency + accessibility; R4: single site, single include. |
| D3 | Preserve button behavior | **Keep** `target="_blank"` (preserved by tag). Do **not** restore `data-place-ad` or `rel="noopener"`. | PO answer 3=А (removal only, no restoration). R1: `data-place-ad` is dormant (no JS handler). |
| D4 | Tag / interface changes | **None.** Do not modify `telegram_tags.py` or add `label`/`icon` kwargs. | No PO answer requires extending the tag; out of scope. |

---

## 6. Out of scope (explicitly)

- No new i18n strings (`{% trans "Sort" %}` and "Submit an ad" already translated; `+` was never translatable).
- No new tests required — R5 confirms no existing test is broken, and none is needed to lock these layout/artifact fixes.
- No migration, schema, or settings changes.
- No changes to `telegram_tags.py`, `data-place-ad`, `rel="noopener"`, or any Python code.

---

## 7. Acceptance criteria

- **AC1** — `header_catalog.html:34`: the line must compile and render the create_ad CTA button with **no stray `+` text node** after the tag.
- **AC2** — `filter_form.html`: the "Sort" field's wrapper must be a `block` layout with the `<label class="block text-sm font-medium text-gray-700 mb-1">{% trans "Sort" %}</label>` rendered **above** `<select name="sort">…</select>` (same pattern as purpose `:15-28`, condition `:32-46`, min/max price `:48-67`). The `flex items-end gap-2` wrapper must be removed.
- **AC3** — Lint passes: `uv run ruff check` (N/A — templates only) and `uv run djlint src/backend/templates/components/header_catalog.html src/backend/templates/ads/partials/filter_form.html` is clean.
- **AC4** — i18n completeness: `test_i18n_completeness.py` passes unchanged (no new/missing `msgstr`s; R1 confirms `+` was never in `.po`).
- **AC5** — Tests pass: `make test` fast gate (and targeted) — specifically `test_autocomplete_template.py::test_bot_username_comes_from_context`, `test_rtl_obfuscation.py::test_telegram_deep_link_create_ad_omits_bot_username_rtl`, and `test_catalog_filters.py::TestSortOnSearchResults::test_sort_dropdown_visible_on_search_results` remain green (R5: none assert on the changed markup).
- **AC6** — No regression in button behavior: CTA opens the bot deep link in a new tab (`target="_blank"` preserved by the tag).

---

## 8. Verification plan

1. Inspect rendered HTML diff of `header_catalog.html` → confirm `+` absent from output outside `<a>`.
2. Inspect rendered HTML of `filter_form.html` (via listings `/) and search `/search/`) → confirm Sort label above select, no `flex items-end`/`gap-2`.
3. `uv run djlint src/backend/templates/components/header_catalog.html src/backend/templates/ads/partials/filter_form.html` → clean.
4. `make test` fast gate → green; specifically re-run the AC5 tests above.
5. `test_i18n_completeness.py` → green.

---

## 9. Assumptions

- A1: Removing the `+` visually is acceptable (it was an undocumented literal; no design-system plus/FAB requirement).
- A2: Label-above for Sort matches the prevailing filter-form convention and is the accessible, mobile-friendly default.
- A3: `data-place-ad` and `rel="noopener"` are not required for the CTA's function (dormant JS hook per audit `block-c:197`).

## 10. Open questions

- (none) — PO answers resolved all ambiguity (Q1–Q3 = А).

---

## 11. Decision log

| Date (UTC) | Decision | Owner | Basis |
|---|---|---|---|
| 2026-09-07T12:29 | PO answers: 1-А (remove `+`), 2-А (label-above), 3-А (remove only) | PO / user | User reply to Q1–Q3 |
| 2026-09-07T12:34 | Accept R1–R6 findings; spec complete | Analyst | Researcher task `ses_f842b7940ffeX3byxNnrH57Bf4` (completed) |
