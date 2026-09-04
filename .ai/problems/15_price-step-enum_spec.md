# Specification: Price Filter Input Step — Change to 1 Unit & Extract as Enum

**Status:** Final — incorporating PO decisions (Q1–Q2, assumed defaults) and research findings  
**Version:** 1.0  
**Date:** 2026-09-04  
**Source Problem:** `.ai/problems/Problem_07.md` (RU)  
**Target Files:** `apps/core/enums.py`, `apps/core/context_processors.py`, `config/settings/base.py`, `templates/ads/partials/filter_form.html`, `docs/01-spec/filter-ui.md`

---

## 1. Problem Statement

The price filter inputs in the catalog/search filter form (`filter_form.html`) render HTML `step="0.01"`, causing the browser's increment/decrement spinner arrows to change the min/max price values by 0.01 (one cent). The Product Owner requests:

1. **Change the increment to 1 unit** — clicking the arrows should step by 1, not 0.01.
2. **Extract the step value into a configurable Enum** — so the step can be easily adjusted in one place going forward, following the project's "all fixed values must use Enum or StrEnum" rule (#10).

The filter operates on `price_normalized_eur` (EUR-equivalent values), so a step of 1 means 1 EUR unit per spinner click — appropriate for buyer price-range discovery.

---

## 2. Facts (Verified)

### 2.1 Current Step Attribute Locations

| File | Line(s) | Input `name` | Context | Current `step` |
|---|---|---|---|---|
| `templates/ads/partials/filter_form.html` | 54 | `min_price` | **Catalog/search filter** (buyer discovery on `/` and `/search/`) | `"0.01"` |
| `templates/ads/partials/filter_form.html` | 64 | `max_price` | **Catalog/search filter** (buyer discovery on `/` and `/search/`) | `"0.01"` |
| `templates/ads/edit.html` | 54 | `price_amount` | **Seller ad-edit** (entering original price in EUR/RSD/BAM) | `"0.01"` |
| `templates/search/partials/save_search_modal.html` | 54, 63 | `min_price`, `max_price` | Saved-search alert modal | *(absent — HTML default = step 1)* |
| `templates/cabinet/saved_search_edit.html` | 62, 70 | `min_price`, `max_price` | Cabinet saved-search edit | *(absent — HTML default = step 1)* |

### 2.2 Data Model

- `Ad.price_amount` — `DecimalField(max_digits=10, decimal_places=2)` (supports cent-level precision; sellers can enter 99.99 BAM).
- `Ad.price_normalized_eur` — `DecimalField(max_digits=12, decimal_places=4)`, null=True (EUR-equivalent used for filtering/sorting).
- `SavedSearch.min_price` / `max_price` — `PositiveIntegerField` (whole numbers only; already consistent with step=1).

**Critical finding:** The HTML `step` attribute is a **client-side UI-only** constraint. Server-side parsing in both `listings.py` and `search.py` uses `int()` / `Decimal()` which accept any numeric string regardless of the HTML `step` value. Changing the step has **zero effect on server-side logic, database queries, or price normalization**.

However, changing `edit.html` from `step="0.01"` to `step="1"` would cause **client-side HTML5 validation** to reject fractional prices (e.g., 99.99) at the browser level — even though the server-side `Decimal()` parser would accept them. This is a real product behavior risk.

### 2.3 Enum Landscape

- **All value-bearing enums in the codebase are `StrEnum`** (`apps/core/enums.py`, `apps/currencies/enums.py`, `apps/lookups/enums.py`).
- `IntEnum` is used only for `AdvisoryLockId` (advisory lock IDs, never rendered in templates).
- **No `Enum` classes with `Decimal` or `float` values exist** anywhere in the codebase.
- A plain `Enum` with `Decimal` values would **not** render correctly in Django templates: `str(member)` returns `"ClassName.MEMBER"`, not the value. Must use `{{ price_step.value }}` or a filter to unwrap.
- `StrEnum` renders correctly both as `{{ price_step }}` (returns value) and `{{ price_step.value }}` (explicit).

### 2.4 Template Constant Exposure

- Three mechanisms exist for getting data into templates: context processors, custom template tags, and per-view context dicts.
- **View context dicts** are used for view-specific values (e.g., `AdSort.DATE_NEW` used as `current_sort` default in `listings.py` and `search.py`).
- **Context processors** are used for site-wide config (`site_name`, `bot_username`, `PLAUSIBLE_HOST`, language, header data).
- **No pattern exists** for a custom template tag that renders an enum value as an HTML attribute. No template currently uses an enum value in `step`, `min`, `max`, `value`, or `limit` attributes.
- The `step="0.01"` is currently **hardcoded** in the template — no context variable, no templatetag, no enum.

### 2.5 Tests

- **Zero tests** assert on the `step` attribute in rendered HTML. Searched all `*test*.py` files for `"step="`, `"step='"`, `"step=\"0.01"`, and `"0\.01.*step"` — all returned 0 matches.
- `test_catalog_filters.py::test_price_inputs_use_default_filter` (lines 730–741) reads `filter_form.html` source and asserts on `value="{{ min_price|default:'' }}"` — does **not** check the `step` attribute.
- No test will break when `step` changes from `"0.01"` to `"1"`.

### 2.6 i18n Impact

- The `step` attribute is a **numeric HTML attribute**, not user-visible translatable text. It does not participate in `{% trans %}` / `{% blocktrans %}` or Python `gettext`. Changing it has **zero** impact on `.po` / `.mo` message catalogs or `test_i18n_completeness.py`.
- **No `makemessages` / `compilemessages` needed.**

### 2.7 Documentation

- `docs/01-spec/filter-ui.md` section "Price Range Filter" (lines 348–367) states: "Inputs use `min="0"` (`step="0.01"`), so zero is a valid bound — a range of `0–100` includes Free ads."

---

## 3. Product Owner Decisions

| Q | Question | Decision | Rationale |
|---|---|---|---|
| Q1 | **Scope of step change:** Should step=1 apply to the filter form only, or also to `edit.html` and saved-search modals? | **(A) Filter form only** | The problem says "filter price fields." The edit page is for seller data entry of original prices (DecimalField with 2 decimal places — supports 99.99 BAM). Changing its step would cause browser client-side validation to reject fractional prices. Saved-search modals already default to step=1 (no explicit `step` attribute). |
| Q2 | **Enum structure:** Single value or multiple presets? | **(A) Single value** | The problem says "this setting" (singular). Only one step (1) is needed now. Multiple unused presets would be YAGNI. The Enum provides the structure for future adjustment — changing the value is a one-line edit. |

> *Note: Q1 and Q2 were presented to the PO with recommended options A and A respectively. Assumed defaults per research findings. Can be revised if PO disagrees.*

---

## 4. Open Questions

The following questions were identified during analysis and presented to the Product Owner with recommended options. Tentative answers are assumed per PO decisions (Section 3). These should be confirmed before implementation begins.

| # | Question | Tentative Answer | Pending PO Confirmation |
|---|---|---|---|
| OQ-1 | Should `step="0.01"` on `edit.html` (seller price input) also be changed to 1? | **No** — the edit page supports fractional prices (e.g., 99.99 BAM) via `DecimalField(max_digits=10, decimal_places=2)`; changing its step would cause client-side validation to reject non-integer input. | ✅ A assumed (Q1) |
| OQ-2 | Should the Enum support multiple step presets (UNIT, TEN, HUNDRED) or currency-specific steps? | **No** — a single `PriceStep.DEFAULT = "1"` is sufficient; the filter is always EUR-equivalent, and extra presets would be YAGNI. | ✅ A assumed (Q2) |
| OQ-3 | Should `save_search_modal.html` and `saved_search_edit.html` receive an explicit `step` attribute for consistency? | **No** — these templates already default to HTML's native `step=1`; adding an explicit attribute would be redundant. | ✅ A assumed |

---

## 5. Business Rules

| Rule ID | Rule |
|---------|------|
| R-PS-01 | The catalog/search price filter inputs (`min_price`, `max_price` in `filter_form.html`) must use `step="1"` (1 EUR unit per spinner click). |
| R-PS-02 | The step value must be defined as a `StrEnum` member in `apps/core/enums.py` — never a hardcoded string literal in a template (rule #10). |
| R-PS-03 | The Enum must be exposed to templates via a context processor, not hardcoded in individual views, since `filter_form.html` is rendered from multiple view contexts (`listings()` and `search()`). |
| R-PS-04 | The `edit.html` seller price input **must not** use the new Enum step — it must retain `step="0.01"` to allow fractional price entry (e.g., 99.99 BAM). |
| R-PS-05 | The `SavedSearch` alert modals (`save_search_modal.html`, `saved_search_edit.html`) already default to HTML's native step=1 — no change needed. |
| R-PS-06 | Changing the step has no server-side effect: price filter parsing uses `int()` (for DB queries) and `Decimal()` (for display), both of which accept any numeric string regardless of the HTML `step` attribute. |

---

## 6. Conceptual Development Tasks

### T1 — Define the `PriceStep` Enum

- **Purpose:** Create a `StrEnum` for the price input step value, following the codebase convention where all value-bearing enums use `StrEnum`.
- **Expected outcome:** A new `PriceStep` class in `apps/core/enums.py` with a single member. The enum must be registered in `__all__`.
- **Dependencies:** None.
- **Details:**
  - Enum: `class PriceStep(StrEnum)` with member `DEFAULT = "1"`.
  - Rationale for `StrEnum` over `IntEnum`: `StrEnum` is the codebase convention for value-bearing enums. While `IntEnum(value=1)` would work for an integer step, the existing 0.01 step (which may need reverting or adjusting in the future) is non-integer, so `StrEnum` with a string value is more flexible and consistent. `StrEnum` renders correctly as `{{ price_step.value }}` in Django templates.
  - The `StrEnum` value `"1"` is the string representation that HTML's `step` attribute expects. No Decimal conversion is needed at the template level — the step is purely a client-side UI concern.

### T2 — Create a context processor for `price_step`

- **Purpose:** Expose the `PriceStep` enum value to all templates, since `filter_form.html` is included from both `listings()` (catalog) and `search()` (search results) views.
- **Expected outcome:** A new `price_step()` function in `apps/core/context_processors.py` that returns `{"price_step": PriceStep.DEFAULT}`.
- **Dependencies:** T1 (Enum must exist).
- **Details:**
  - Pattern follows existing context processors (`plausible_host`, `language`, `site_config`) — simple dict return, no DB queries.
  - Registered in `config/settings/base.py` under `TEMPLATES.OPTIONS.context_processors`.
  - Template uses `step="{{ price_step.value }}"` to render the step value explicitly.

### T3 — Update `filter_form.html` template

- **Purpose:** Replace the hardcoded `step="0.01"` with `step="{{ price_step.value }}"` using the enum from the context processor.
- **Expected outcome:** Both `min_price` and `max_price` inputs in `filter_form.html` use the configurable `price_step` value instead of a hardcoded string.
- **Dependencies:** T2 (context processor must be registered).
- **Details:**
  - Line 54: `step="0.01"` → `step="{{ price_step.value }}"`
  - Line 64: `step="0.01"` → `step="{{ price_step.value }}"`
  - No i18n impact (numeric attribute, not translatable text).
  - `edit.html` is **not** modified (R-PS-04).

### T4 — Update documentation

- **Purpose:** Update `docs/01-spec/filter-ui.md` to reflect the new step value and Enum configuration.
- **Expected outcome:** The "Price Range Filter" section documents `step` as configurable via `PriceStep` enum, with the current value being 1.
- **Dependencies:** T1–T3 (definition and usage must be complete).
- **Details:**
  - Update line 350: "Inputs use `min="0"` (`step="0.01"`)" → "Inputs use `min="0"` with `step="{{ price_step.value }}"` (currently `PriceStep.DEFAULT = "1"`)"
  - Note the Enum source (`apps/core/enums.py`) and exposure mechanism (context processor).

### T5 — Add test coverage

- **Purpose:** Add a test that verifies the rendered filter form uses step="1" (or the enum value) for price inputs.
- **Expected outcome:** A test in `test_catalog_filters.py` (or a new test file) that asserts the step attribute is present with the correct value in rendered/filtered output.
- **Dependencies:** T3 (template change must be complete).
- **Details:**
  - Existing test `test_price_inputs_use_default_filter` (line 730) checks `value="{{ min_price|default:'' }}"`. A new test should check `step="{{ price_step.value }}"` in the template source, or assert `step="1"` in rendered HTML.
  - Pattern: static template-source assertion (like `test_sort_dropdown_is_not_gated_on_query` at line 721).

---

## 7. Technical Requirements

### 7.1 Enum Definition

**File:** `apps/core/enums.py`

```python
class PriceStep(StrEnum):
    """HTML input ``step`` attribute for price filter inputs.

    Controls the increment/decrement of the spinner arrows on price
    input fields in the catalog/search filter form (filter_form.html).
    The filter operates on price_normalized_eur (EUR-equivalent),
    so a step of 1 means 1 EUR unit per click.

    To change the increment in the future, edit the value below.
    """

    DEFAULT = "1"
```

Add `"PriceStep"` to `__all__`.

**Type rationale:** `StrEnum` (not `IntEnum`, not plain `Enum`):
- `StrEnum` is the codebase convention for all value-bearing enums.
- Renders correctly in Django templates as both `{{ price_step }}` and `{{ price_step.value }}`.
- Supports future decimal steps (e.g., `"0.5"`) without type changes — `IntEnum` can only hold integers.
- A plain `Enum` with `Decimal` values would NOT render correctly in templates (str returns `"ClassName.MEMBER"`), requiring a custom template filter for every usage — unnecessary friction.

### 7.2 Context Processor

**File:** `apps/core/context_processors.py`

```python
def price_step(request) -> dict[str, StrEnum]:
    """Expose the HTML price-input step to all templates.

    Returns the ``PriceStep.DEFAULT`` enum member so templates can
    render ``step="{{ price_step.value }}"`` instead of hardcoding
    a numeric string.
    """
    from apps.core.enums import PriceStep

    return {"price_step": PriceStep.DEFAULT}
```

**File:** `config/settings/base.py` (line 147–156, add to `context_processors` list):

```python
"context_processors": [
    ...
    "apps.core.context_processors.price_step",
],
```

### 7.3 Template Changes

**File:** `templates/ads/partials/filter_form.html`

| Line | Current | New |
|------|---------|-----|
| 54 | `step="0.01"` | `step="{{ price_step.value }}"` |
| 64 | `step="0.01"` | `step="{{ price_step.value }}"` |

**File:** `templates/ads/edit.html` — **NO CHANGE** (retains `step="0.01"` for seller fractional-price entry).

### 7.4 Files NOT Changed

| File | Reason |
|------|--------|
| `templates/ads/edit.html` line 54 | Seller price input; needs fractional prices (e.g., 99.99 BAM). Step stays `0.01`. |
| `templates/search/partials/save_search_modal.html` | No explicit `step` — HTML defaults to `step=1`. Already consistent. |
| `templates/cabinet/saved_search_edit.html` | No explicit `step` — HTML defaults to `step=1`. Already consistent. |
| All Python view files | Server-side price parsing uses `int()` / `Decimal()` which are agnostic to HTML step. No code changes needed. |
| `.po` / `.mo` files | `step` is a numeric attribute, not translatable text. No i18n changes. |
| Database schema | No schema or migration changes. The Enum is front-end-only. |

---

## 8. Acceptance Criteria

- [ ] `PriceStep` StrEnum with `DEFAULT = "1"` exists in `apps/core/enums.py` and is exported in `__all__`.
- [ ] `price_step` context processor exists in `apps/core/context_processors.py` and is registered in `config/settings/base.py`.
- [ ] `filter_form.html` uses `step="{{ price_step.value }}"` for both `min_price` (line 54) and `max_price` (line 64) inputs — no hardcoded `step="0.01"`.
- [ ] `edit.html` retains `step="0.01"` for the seller's `price_amount` input.
- [ ] A test asserts the step value is `"1"` (or uses `{{ price_step.value }}`) in the rendered filter form.
- [ ] No existing tests break (verified: zero tests assert on the `step` attribute).
- [ ] `make test` (fast gate) passes.
- [ ] `docs/01-spec/filter-ui.md` updated to reference the Enum and current value of 1.
- [ ] Lint passes: `uv run ruff check <changed files>`.
- [ ] Typecheck passes: `uv run basedpyright <changed files>`.
- [ ] Template lint passes: `uv run djlint src/backend/templates/`.

---

## 9. Assumptions

1. **Scope is the filter form only (Q1=A):** The problem says "filter price fields" (`filter_form.html`). The edit page (`edit.html`) is a seller data-entry form that must support fractional prices (e.g., 99.99 BAM) — its `step="0.01"` is retained intentionally.
2. **Single-value Enum (Q2=A):** One Enum member (`PriceStep.DEFAULT = "1"`) suffices. The Enum provides the centralized, configurable structure the PO wants; multiple presets are unnecessary (YAGNI per rule #5).
3. **EUR-equivalent step:** The filter operates on `price_normalized_eur`, so a step of 1 means 1 EUR unit. No currency-specific step logic is needed for the filter.
4. **Saved-search modals already correct:** `save_search_modal.html` and `saved_search_edit.html` have no explicit `step` attribute, so they already default to HTML's integer step of 1. No change needed.
5. **StrEnum chosen over IntEnum:** While the value `1` is an integer, the codebase convention is `StrEnum` for all value-bearing enums, and `StrEnum` supports future decimal steps without type changes.
6. **No server-side impact:** The HTML `step` attribute is client-side only. Server-side price parsing uses `int()` / `Decimal()` which accept any numeric string regardless of step.
7. **No DB migration:** The Enum is front-end-only (template attribute). No schema or migration changes are required.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Edit page fractional prices rejected client-side | N/A (not changed) | N/A | `edit.html` retains `step="0.01"` per R-PS-04 — no risk introduced |
| Enum doesn't render in template | Low | Low | `StrEnum` renders as its string value; verify with `{{ price_step.value }}` pattern |
| Context processor not registered | Low | Medium | Add to `config/settings/base.py` `context_processors` list; test verifies rendering |
| Template test reads stale source | Low | Low | Test reads `filter_form.html` source at test time (like `test_price_inputs_use_default_filter`) |
| Future decimal step needs IntEnum → StrEnum migration | Low | Low | `StrEnum` already supports string values like `"0.5"`; no migration needed |

---

## 11. Out of Scope

- **`edit.html` step change** — The seller's price input must keep `step="0.01"` for fractional prices (R-PS-04). Out of scope per Q1=A.
- **Saved-search modal step** — Already defaults to step=1 (no explicit attribute). No change needed.
- **Server-side price validation** — The HTML step is client-side only; server parsing is agnostic. No backend changes.
- **Database/schema changes** — The Enum is a front-end template concern. No migration.
- **i18n changes** — `step` is a numeric attribute, not translatable text. No `makemessages` / `compilemessages` required.
- **Currency-specific steps** — The filter always operates in EUR-equivalent terms. No per-currency step logic.

---

## 12. Definition of Ready

The specification is ready for implementation when:

1. ✅ The `PriceStep` StrEnum is defined with `DEFAULT = "1"` in `apps/core/enums.py`.
2. ✅ The `price_step` context processor is created and registered in settings.
3. ✅ `filter_form.html` uses `step="{{ price_step.value }}"` for both price inputs.
4. ✅ `edit.html` is explicitly left unchanged (step="0.01" retained).
5. ✅ A test verifies the step value in rendered filter form HTML.
6. ✅ `docs/01-spec/filter-ui.md` is updated.
7. ✅ All existing tests continue to pass (no test asserted on `step` previously).
8. ✅ Lint, typecheck, and template lint pass on changed files.

---

*End of specification — ready for implementation planning.*
