# Specification: Clear-All Button Alignment with Filter-Chip Row

**Status:** Draft — incorporates Researcher audit (test-constraint matrix + HTMX/ Tailwind verification). PO decisions Q1–Q3 carry recommended defaults per the analyst; PO sign-off requested on the *button-vs-link* and *touch-target sizing* options.
**Version:** 1.0
**Date:** 2026-09-04
**Source Problem:** `.ai/problems/Problem_05.md` (RU: *«Сейчас кнопка Clear all filters расположена не в одном ряду с chips... нужно разместить в одном ряду, причем сделать первой в этом ряду и проверить, чтобы остальные инструменты и тесты не были нарушены»*)
**Author:** Senior Product Analyst (spec cycle)
**Stack context:** Django 5.2 LTS · HTMX 2.0.10 (pinned via SRI) · Tailwind CSS · PostgreSQL 18 · gunicorn WSGI + aiogram bot (shared ORM)

---

## 1. Problem Statement

The **Clear all filters** control on the catalog listing/search results page is rendered in a **separate visual row** from the active filter chips. The owner requests that the control be moved **into the same row as the chips** and made **the first element in that row** (i.e., leftmost in DOM/reading order, before all chips), while guaranteeing that **existing tests and tooling are not broken**.

### Current behavior (verified)

`src/backend/templates/ads/partials/ad_list.html`:

- **L33** – chips-block guard: `{% if current_listing_purpose or current_features or current_condition or active_price_min or active_price_max %}` (the gate is already correct — it includes price; see Spec 05 T1).
- **L34** – chips row opens: `<div class="flex flex-wrap gap-2 mb-4">`.
- **L35–79** – price / purpose / condition / feature chips (each inside its own `{% if %}` / `{% for %}`).
- **L80** – `</div>` closes the chips row.
- **L81** – an HTML comment: `<!-- Clear all filters: resets all query params (...); category/city are path params, naturally preserved. -->`.
- **L82–87** – the clear-all `<a>` link (with `href`, `hx-get`, `hx-push-url="true"`, `hx-target="#ad-list"`, `hx-swap="innerHTML"`). This is currently a **sibling positioned AFTER `</div>`** — i.e., a *second* wrapped row — even though it lives inside the same `{% if %}` (L33/L88).
- **L88** – `{% endif %}` closes the chips-block.

Concretely: the chips sit in the first flex-wrap row; the clear-all `<a>` is a text link on its own line below the chips (second row), because it is emitted after the `</div>` that closes the `flex flex-wrap` container.

### Desired behavior

The clear-all control must be **inside the chips-row `<div>`** (the same `flex flex-wrap` container) and must be the **first child** of that container, so that in LTR reading order it appears leftmost and the chips flow alongside/after it (wrapping naturally when the row overflows). All existing behavioral guarantees (HTMX partial swap + `hx-push-url`, reset semantics, q-preservation on search page, visibility gating, i18n) must be preserved, and all existing tests must continue to pass (see Constraints §8 and Research §6).

### Root cause

Layout regression-by-placement: the clear-all link and the chip container share the same `{% if %}` guard but **not the same flex container**. The clear-all was placed after the chips `</div>` (whether intentionally as a "second row" or as an oversight in Spec 05 T2/T7) so it never sits in the same flex-wrap flow. No backend/view change is required — this is a template-structure + styling concern.

> **Note (Spec 05 relationship):** Spec 05 (`05_filter-regression_spec.md`, source `Problem_04.md`) already fixed the *visibility* gating (clear-all now hidden when no chips) and converted the price summary to a removable chip. The current Problem_05 is a **narrow, subsequent** layout fix on top of that work — it does **not** re-open Spec 05's behavioral rules. The chips-block `{% if %}` already includes `active_price_min`/`active_price_max` (Spec 05 T1 done) and the price range already renders as a `&times;`-removable chip (Spec 05 T3 done); both are assumed as given baseline.

---

## 2. Facts (Verified by Code Analysis)

### 2.1 Template structure (nesting-depth map)

Source of truth: `src/backend/templates/ads/partials/ad_list.html` (207 lines). Verified depth map over the chips-block `{% if %}` (opens L33, closes L88):

```
L33  {% if ... %}                       → depth 1 (chips-block gate)
L34  <div class="flex flex-wrap gap-2 mb-4">  → depth 1 (HTML wrapper)
L35  {% if active_price_min or ... %}   → depth 2 (price chip gate)
L45  {% endif %}                        → depth 1
L46  {% for p in resolved_purposes %}   → depth 2 (purpose loop)
L47  {% if p.slug == current_listing_purpose %} → depth 3 (purpose match)
L57  {% endif %}                        → depth 2
L58  {% endfor %}                       → depth 1
     [condition chip block L59–71: depth 2→3→2→1, identical pattern]
L72  {% for f in resolved_features %}   → depth 2
L73  {% if f.slug in current_features %} → depth 3
L76  <a href ... hx-get ... ...>        → depth 3 (single-line, all inside one <a>)
L77  {% endif %}                        → depth 2
L79  {% endfor %}                       → depth 1
L80  </div>                             → depth 1 (HTML close of chips row)
L81  <!-- Clear all filters: ... -->     → depth 1 (HTML comment; persists in rendered HTML)
L82–87  <a href ... hx-get ...>         → depth 1 (clear-all, sibling AFTER </div>)
L88  {% endif %}                        → depth 0 (exit chips-block)
```

Key structural facts:
- The clear-all `<a>` is inside the chips-block `{% if %}` (depth 1 throughout L81–87) — so it is already **conditionally visible** and gated by the same chips-block condition. ✅ (Spec 05 T2 done.)
- The clear-all `<a>` is **outside** the chips-row `<div>` (the `</div>` at L80 closes the flex container before the `<a>` is emitted) — hence the separate-row rendering. **This is the defect to fix.**
- The HTML comment at L81 **persists into rendered HTML** (`<!-- ... -->` is not stripped by Django at render time). Because its text contains the literal phrase `Clear all filters`, the rendered-output helper `_extract_clear_all_hx_get` (`test_catalog_filters.py` L821–831) calls `content.index("Clear all filters")` which **matches the comment first** (L81 renders before the `<a>` text at L87). The helper therefore returns the **last chip's** `hx-get` URL, not the clear-all URL. The two behavioral tests that use it (`test_clear_all_preserves_search_query`, `test_clear_all_omits_query_on_listings`) pass only because the last-chip URL carries the same `q=` / no-`q=` signature as the clear-all URL on those specific inputs. **This is a latent test-targeting bug; relocating the clear-all into the row as the first child must also neutralize the comment (see §4 / Task T2).**

### 2.2 Filter reset semantics (unchanged by this change)

Confirmed against `ad_list.html` L82–87 and `docs/01-spec/filter-ui.md` L403–433:
- Clear-all is an HTMX link (`hx-get` with `hx-push-url="true"`, `hx-target="#ad-list"`, `hx-swap="innerHTML"`).
- It resets **all** query params (`sort`, `min_price`/`max_price`, `listing_purpose`, `listing_condition`, `features`, `page`) to `?page=1`, emitting only `&lang=` (and `&q=` only on the search page, via `{% if query %}`).
- Category/city encoded as URL **path** params are naturally preserved (not query params).

### 2.3 Chip-row styling (baseline)

`ad_list.html` L34: `<div class="flex flex-wrap gap-2 mb-4">` (no `items-` alignment). Chips are `inline-flex items-center px-3 py-1 ... rounded-full text-sm` (L36, L48, L61, L74) — pill-shaped, ~24–28 px tall. Clear-all `<a>` is `text-sm text-blue-600 hover:underline` (L87) — a plain text link, ~20 px tall, **not** meeting the project's 44 px touch-target rule.

### 2.4 HTMX version / support matrix

HTMX 2.0.10 pinned via SRI at `ads/detail.html` L22–24 and `ads/list.html` L17–19 (`htmx.org@2.0.10/dist/htmx.min.js` with `integrity="sha384-..."` + `crossorigin="anonymous"`). HTMX is always loaded before any inline script (`defer`), so `hx-get` on a `<button>` fires reliably. The project already uses `<button type="button">` with vanilla inline handlers elsewhere (e.g., `filter_form.html` L70, L106) and `hx-get` on `<form>` (L5) and `<a>` (everywhere in `ad_list.html`).

### 2.5 Touch-target rule (project constraint)

`AGENTS.md` Touch Target Guidelines (44 px minimum) is documented in:
- `docs/01-spec/ui-patterns.md` L504–513 ("Buttons → 44px height").
- `docs/06-design-system/components.md` L167–168 ("Category expand buttons: `p-3 min-w-[44px] min-h-[44px]`").
- Enforced by test: `src/backend/apps/search/tests/test_autocomplete_template.py` L85–86 asserts `min-w-[44px]` / `min-h-[44px]` on header interactive elements.
- Currently **not** enforced on `ad_list.html` (the existing clear-all `<a>` is a ~20 px text link).

### 2.6 Test surface (exhaustive)

All clear-all / chip-row constraints live in **one file**: `src/backend/apps/ads/tests/test_catalog_filters.py`. Verified by recursive grep across `src/` for `clear.*filter`, `Clear all filters`, `hx-get`, and `ad_list` — **no other test file** references the clear-all element (the autocomplete test targets `header_catalog.html`; coverage confirmed). The constraining tests are enumerated in §6 (Test-Impact Checklist) and verified PASS/FAIL-by-design in the Researcher matrix.

---

## 3. Confirmed Requirements

| ID | Requirement | Source |
|---|---|---|
| CR-1 | The clear-all control must be the **first child** of the chips-row `<div class="flex flex-wrap ...">` (the same flex container as the chips), so it renders leftmost in the same row and chips flow after it. | Problem_05 («в одном ряду… первой в этом ряду») |
| CR-2 | The clear-all control must remain **conditionally visible** (same `{% if %}` gate, L33) — it renders only when at least one chip (purpose, condition, features, or price) is active, and disappears when no chip is active. | Spec 05 CR-1/CR-2; existing `test_clear_all_hidden_when_no_filters_active` (L912) |
| CR-3 | Reset semantics are **unchanged**: clear-all resets all query params to `?page=1`, preserving only `lang` and (on `/search/?q=…`) the search query `q`; category/city path params preserved naturally. | Spec 05 CR-3/CR-4; `filter-ui.md` L414–433 |
| CR-4 | The clear-all control must keep `hx-push-url="true"` + `hx-target="#ad-list"` + `hx-swap="innerHTML"` so clearing re-renders the results region and updates browser history (not a full-page reload). | Spec 05 CR-3; R-FR-02; `test_clear_all_filters_static_guard` (L672) / `test_chip_link_has_push_url_in_rendered_output` (L760) |
| CR-5 | All clear-all user-visible text stays wrapped in `{% trans "Clear all filters" %}`; the msgid already exists and is translated in `ru`, `en`, `bs` locales (`.po` L397/381/397). | `docs/99-agent/rules.md` i18n pipeline §90–96; `test_i18n_completeness.py` test_extraction_completeness |
| CR-6 | The chips row must not be broken by the relocation: `href` + `hx-get` attribute counts in `ad_list.html` source remain at **10 `hx-get=`** and **10 `hx-push-url="true"`** (4 chips + clear-all + 5 pagination). | `test_all_htmx_links_have_push_url` (L648) — MUST stay 10 |
| CR-7 | The rendered clear-all URL must be the one actually targeted by `_extract_clear_all_hx_get` (i.e., the HTML comment must no longer shadow it). | Latent bug §2.1; `test_clear_all_preserves_search_query` (L833), `test_clear_all_omits_query_on_listings` (L851) |

---

## 4. Conceptual Development Tasks

Each task is independent and can be owned/planned separately unless a dependency is stated.

### Task T1 — Move clear-all into the chips-row `<div>` as first child (layout)

- **Purpose:** Place the clear-all control inside the same flex container as the chips and make it the first child, so it occupies the same wrapped row as the chips (leftmost) instead of a separate row.
- **Concrete change:** In `src/backend/templates/ads/partials/ad_list.html`, cut the clear-all `<a>` (L82–87) **together with** the L81 HTML comment, and paste it as the **first child** immediately after L34 (`<div class="flex flex-wrap gap-2 mb-4">`), before the price chip block (L35). The `{% endif %}`/structure otherwise remains identical; clear-all stays inside the chips-block `{% if %}` (L33) — unchanged gating.
- **Expected outcome:** The clear-all control renders in the same `flex flex-wrap` row as the chips, leftmost, with chips wrapping to its right/after.
- **Dependencies:** None (structural move only).
- **Affected files:** `templates/ads/partials/ad_list.html`.
- **Test impact:** Must keep `test_clear_all_filters_static_guard` green (clear-all still after the `{% if %}` at L33; `hx-push-url="true"` still within 6 preceding source lines of the `{% trans %}` tag; depth counter still ends `> 0`). See §6 checklist.

### Task T2 — Neutralize the L81 HTML comment (latent test-targeting fix)

- **Purpose:** Prevent the `<!-- Clear all filters: ... -->` HTML comment from shadowing the clear-all element in rendered-output tests (`_extract_clear_all_hx_get` matches the comment's text first), which currently makes those tests assert on a *chip* URL rather than the clear-all URL.
- **Concrete change:** Delete the HTML comment at L81, **or** convert it to a Django template comment `{# Clear all filters: resets all query params (...) #}` (Django comments are stripped at render time, so they never reach `response.content`). Recommended: convert to `{# #}` to preserve the explanatory note for maintainers without re-introducing the rendered-output collision.
- **Expected outcome:** `content.index("Clear all filters")` in rendered output finds the clear-all element's text, so `_extract_clear_all_hx_get` returns the **clear-all** URL (behavior the tests were already meant to verify).
- **Dependencies:** T1 (the comment moves/relocates with the clear-all element).
- **Affected files:** `templates/ads/partials/ad_list.html`; verify against `test_i18n_completeness.py::test_no_hardcoded_visible_text` (Django comments `{# #}` are stripped by the scan regex at L175, so i18n scanning is unaffected).
- **Test impact:** `test_clear_all_preserves_search_query` (L833) and `test_clear_all_omits_query_on_listings` (L851) now genuinely assert the clear-all URL (stronger correctness). Both remain green per the Researcher matrix (Test 4/5).

### Task T3 — Element-type decision (PO decision; recommended default applied)

- **Purpose:** Decide whether the clear-all control remains an `<a>` text link or is converted to a `<button type="button">` (the owner's word «кнопка» = "button").
- **Option A (RECOMMENDED, default):** `<button type="button" hx-get="?page=1{% if query %}&q={{ query|urlencode }}{% endif %}{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}" hx-push-url="true" hx-target="#ad-list" hx-swap="innerHTML">{% trans "Clear all filters" %}</button>`. Semantically correct for a JS-triggered (HTMX) action; matches the project's existing `<button type="button">` precedent (`filter_form.html` L70, L106; `list.html` L27); enables the 44 px touch target (T4) that the current `<a>` lacks.
- **Option B (override):** keep the existing `<a class="text-sm text-blue-600 hover:underline">` element as-is and only relocate it (T1). Preserves a no-JS `href` fallback (progressive enhancement) but leaves a ~20 px touch target.
- **Expected outcome:** A single clear-all control, first in the chips row; `hx-get`/`hx-push-url`/`hx-target`/`hx-swap` attributes preserved exactly so CR-6 (counts = 10 / 10) holds.
- **Dependencies:** T1.
- **Affected files:** `templates/ads/partials/ad_list.html`.
- **PO decision:** Q1 (see §7). If A is chosen, also apply T4 (touch target) and T5 (row alignment + button styling). If B is chosen, T4/T5 are optional.
- **Test impact:** Converting `<a>`→`<button>` keeps `hx-get=` and `hx-push-url="true"` attributes (count unchanged at 10/10). The rendered-output URL extraction still finds the clear-all `hx-get` immediately preceding the `{% trans %}` text. Verified PASS in Researcher Test 1/3/4/6.

### Task T4 — Touch-target + styling (applied only if PO-Q1 = A)

- **Purpose:** Make the clear-all button compliant with the project's 44 px touch-target rule and visually consistent as an action control in the chip row.
- **Concrete change:** Apply a compact secondary-button style (exact Tailwind classes chosen by the implementer; recommended baseline: `px-2 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[44px] flex items-center`). Use `rounded-lg` (button radius) — **not** `rounded-full` (chip radius), because the clear-all is an action control, not a badge/pill; chips intentionally stay `rounded-full`.
- **Expected outcome:** Clear-all is a 44 px touch target, visually distinct from chips but aligned in the same row.
- **Dependencies:** T1 + (PO-Q1 = A).
- **Affected files:** `templates/ads/partials/ad_list.html`.
- **Test impact:** None (no test enforces 44 px on `ad_list.html`; i18n scan strips CSS classes). Optional follow-up: a new unit test can assert `min-h-[44px]` on the clear-all element for regression coverage.

### Task T5 — Row baseline alignment (recommended, low-risk)

- **Purpose:** Keep the new clear-all button vertically flush with the chips so the row reads as one aligned line rather than a misaligned stack.
- **Concrete change:** Add `items-center` to the chips-row container: `<div class="flex flex-wrap gap-2 mb-4 items-center">` (was `flex flex-wrap gap-2 mb-4`). With a 44 px button and ~24 px chips, `items-center` centers the chips on the button's cross-axis so they share a common visual baseline.
- **Expected outcome:** Chips and clear-all align cleanly; wrapping behavior (`flex-wrap`) is unchanged.
- **Dependencies:** T1 (or T4 if button chosen).
- **Affected files:** `templates/ads/partials/ad_list.html`.
- **Test impact:** None. djlint must remain clean (`uv run djlint src/backend/templates/`).

### Task T6 — Verify tests + i18n (Definition-of-Done gate)

- **Purpose:** Confirm no existing test or tool is violated by the relocation/change.
- **Concrete change:** Run the fast gate and i18n gates.
  1. `make test-recreate` (fresh schema; only because template-only changes must still render against real DB-backed views — reuses the named-volume schema otherwise) then `make test` (fast gate).
  2. Specifically assert in `test_catalog_filters.py`: `test_all_htmx_links_have_push_url` (10/10), `test_clear_all_filters_static_guard` (position + depth + 6-line window), `test_clear_all_preserves_search_query` (q=test preserved), `test_clear_all_omits_query_on_listings` (no q=), `test_clear_all_visible_when_only_price_filter_active`, `test_clear_all_hidden_when_no_filters_active`, `test_lang_param_in_all_htmx_urls` (all 10 values carry `LANGUAGE_CODE`), `test_chip_link_has_push_url_in_rendered_output`, `test_form_renders_path_only_hx_get`.
  3. `make makemessages` then `make compilemessages`; `test_i18n_completeness.py` all four guards pass.
- **Expected outcome:** Fast gate + i18n gate green; clear-all genuinely asserted (not via a shadowed comment).
- **Dependencies:** T1–T5.
- **Affected files:** `src/backend/apps/ads/tests/test_catalog_filters.py` (no edits expected — tests should pass as-is; if the implementer's formatting of the `<button>`/`<a>` drifts the 6-line window in T1's test, the test file is the place to adjust the assertion, but per AGENTS.md rule #2 the *production template* must conform, not the test).
- **Test impact:** None (verify-only).

---

## 5. Problem-to-Task Mapping

| Problem aspect | Task(s) |
|---|---|
| Clear-all in a separate row (needs to share the chips row) | T1 |
| HTML comment shadows clear-all in rendered tests (latent) | T2 |
| "кнопка" = button semantics (element-type choice) | T3 |
| 44 px touch-target compliance | T4 |
| Row baseline alignment of button + chips | T5 |
| Tests + i18n not violated | T6 |

---

## 6. Research Summary

A delegated Researcher agent audited `ad_list.html` (L32–88), `filter_form.html`, `test_catalog_filters.py` (L624–927), `test_i18n_completeness.py` (L145–244), and `test_autocomplete_template.py`, and verified HTMX 2.0.10 + Tailwind conventions. Findings (HIGH confidence, every file:line verified):

1. **Structure:** clear-all `<a>` (L82–87) is inside the chips-block `{% if %}` but **after** the chips `</div>` (L80) — confirming the separate-row defect. The L81 HTML comment `<!-- Clear all filters: ... -->` survives into `response.content` and is matched first by `content.index("Clear all filters")` — a **latent test-targeting bug** (the behavioral clear-all URL tests currently assert on the last chip's URL, passing only by q-signature coincidence).

2. **Test-constraint matrix (all verified):**
   - `test_all_htmx_links_have_push_url` (L648): asserts exactly `hx-get=` == 10 and `hx-push-url="true"` == 10 in the **template source**. Moving the clear-all within the row, or `<a>`→`<button>`, changes **neither** count (the clear-all still contributes one of each). → PASSES both options.
   - `test_clear_all_filters_static_guard` (L672): (a) `clear_idx > chips_if_idx`, (b) `hx-push-url="true"` ∈ `lines[clear_idx-6 : clear_idx+1]`, (c) depth loop `range(chips_if_idx+1, clear_idx)` ends `depth > 0`. Relocating clear-all to first child keeps it after L33's `{% if %}`, keeps `hx-push-url` within the 6-line window (it sits 2–3 lines above the `{% trans %}` tag), and the depth loop crosses only the `<div>` + `<a>/<button>` opener lines (no unbalanced `{% if %}`/`{% for %}`). The inline `{% if query %}`/`{% endif %}` URL pairs on the href/hx-get lines cancel (each +1, each −1 per line). → PASSES both options.
   - `_extract_clear_all_hx_get` (L821) + `test_clear_all_preserves_search_query` (L833) / `test_clear_all_omits_query_on_listings` (L851): these read **rendered** output. They PASS only once T2 neutralizes the L81 comment (otherwise they assert a chip URL, not the clear-all URL). With the comment gone and clear-all first in the row, `content.index("Clear all filters")` matches the clear-all element, and `hx_gets[-1]` is the clear-all's own `hx-get` (which precedes its `{% trans %}` text on the element tag). → PASSES after T2.
   - Visibility tests (L896 visible-with-price, L912 hidden-with-no-filters): clear-all stays inside the chips-block `{% if %}` (gated on purpose/condition/features/price). Moving it as the first child of the same div does not change gating. → PASSES both options.
   - `test_lang_param_in_all_htmx_urls` (L659): all 10 `hx-get` URLs carry `LANGUAGE_CODE`; the clear-all URL is unchanged. → PASSES both options.

3. **HTMX `<button>` semantics — SUPPORTED.** The canonical HTMX docs example is `<button hx-get="/example">Get Some HTML</button>`; `hx-get` acts on any element. `<button type="button" hx-get="..." hx-push-url="true" hx-target="#ad-list" hx-swap="innerHTML">` performs an identical AJAX GET + pushState + partial swap vs. the `<a>` variant. `form`/`name` attributes are **not** required (`hx-get` carries the URL; `type="button"` prevents form submission). HTMX 2.0.10 is SRI-pinned and always loaded (`defer`) before inline scripts. → Option A is technically safe.

4. **Tailwind layout recommendation:**
   - Add `items-center` to the chips-row `<div>` (currently `flex flex-wrap gap-2 mb-4`) so the clear-all control and the shorter pill-chips share a common cross-axis baseline (`items-center`).
   - Use `rounded-lg` (button radius) for the clear-all — **not** `rounded-full`. Chips are deliberately pill-shaped badges; the clear-all is an action control. This matches sibling controls: pagination buttons (`ad_list.html` L154/160/171/180/186 → `rounded-lg`), the "Apply filters" submit (`filter_form.html` L107 → `rounded-lg`). Using `rounded-full` would visually fuse the clear-all with chip siblings and mis-signify it as a dismissible badge.
   - Add `min-h-[44px]` (and `flex items-center` for internal vertical centering) to satisfy the 44 px touch-target rule the current text-link clear-all violates.

5. **`query_replace` / URL construction:** out of scope — untouched by this change.

**Approaches considered (ranked):**

| Approach | What | Adopt | Why not the others |
|---|---|---|---|
| **A.** Move `<a>` as-is to first child of chips `<div>` | Minimal template relocation; keep text-link styling | ✅ **Default if PO chooses link (Option B)** | Smallest diff; zero behavioral risk; tests pass per matrix. Does not add 44 px target. |
| **B.** Convert to `<button type="button">` + relocate as first child | Semantic element; 44 px target; project `<button type="button">` precedent | ✅ **Recommended default (Option A in T3)** | Matches owner's «кнопка»; enables touch-target compliance; HTMX-verified equivalent. Slight loss of no-JS `href` fallback (acceptable: HTMX always loaded; all other in-page controls here are already HTMX-driven). |
| **C.** Chip-shaped (`<span class="rounded-full">`) clear-all | Make the clear-all a pill like its chip siblings | ❌ rejected | Mis-signifies an action as a dismissible badge; breaks the button-vs-chip affordance grammar; the user said «кнопка», not «чип». |

---

## 7. Product Owner Decisions

| Q | Question | Options | Recommended choice | Rationale | Status |
|---|---|---|---|---|---|
| Q1 | What element should "Clear all filters" be? | **A:** `<button type="button" hx-get …>` (semantic button; 44 px target possible) · **B:** keep `<a>` text-link (relocate only; preserves no-JS `href` fallback) | **A** | Owner calls it «кнопка»; matches project `<button type="button">` precedent (filter_form.html L70/L106, list.html L27); HTMX-verified equivalent; enables 44 px compliance. | Default applied — **PO may override to B** |
| Q2 | How should the clear-all look in the chip row? | **A:** secondary button (`rounded-lg`, `min-h-[44px]`, border) — action control · **B:** plain text link styling (`text-sm text-blue-600 hover:underline`, as today) · **C:** pill chip (`rounded-full`) to match chip siblings | **A** if Q1=A · **B** if Q1=B | Chips are dismissible badge-pills; clear-all is an action → `rounded-lg` keeps the grammar correct and matches sibling pagination/apply buttons. | Default applied — derived from Q1 |
| Q3 | Should the row baseline-align the (taller) button with the (shorter) chips? | **A:** add `items-center` to the row `<div>` · **B:** leave row unaligned | **A** | Without it, a 44 px button leaves the ~24 px chips top-aligned, looking ragged on wrap. Low-risk Tailwind addition. | Default applied (assumption) |
| Q4 | Must the L81 `<!-- Clear all filters: ... -->` HTML comment be removed/converted? | **A:** convert to `{# … #}` Django comment (stripped at render; preserves docs) · **B:** delete outright | **A** | Removing is required to fix the latent test-targeting bug (§2.1); converting to `{# #}` preserves the maintainer note. i18n scan strips `{# #}` (verified at `test_i18n_completeness.py` L175). | Required (not optional) — applied |

> **Decision note:** Q1/Q2/Q3 carry analyst-recommended defaults so the spec is implementation-ready without a blocking PO sync (per spec Definition of Done: "ready for implementation planning without additional business analysis"). The single genuine override the PO may want is **Q1=B** (keep the `<a>` text-link and only relocate it) if retaining a no-JS `href` fallback is preferred over the 44 px button. If Q1=B is chosen, Q2 resolves to B and T4 (touch-target) is downgraded from required to optional.

---

## 8. Assumptions

1. **Spec 05 baseline holds.** The chips-block `{% if %}` already includes `active_price_min or active_price_max` and the price range already renders as a `&times;`-removable chip. Spec 05's visibility gating and price-chip conversion are implemented; Problem_05 builds on top of them and does not revert them.
2. **"First in the row" = first DOM child** of the chips-row `<div>`, i.e., leftmost in LTR and the anchor before which chips flow/wrap. `flex flex-wrap` places the first child at the start of the first line; no `order=` reordering is needed.
3. **Clear-all is always shown whenever the chip row is shown** (i.e., whenever the chips-block `{% if %}` is true). There is no separate visibility toggle — the clear-all and the chips share the same gate. (If the PO later wants the clear-all visible even with zero chips, that is a separate feature, out of scope here.)
4. **Category/city are path params** on the listings page (preserved naturally by clear-all's `?page=1&lang=` reset) per `filter-ui.md` L435–438. (This change does not touch URL architecture.)
5. **No backend/view change is needed.** `query`, `current_category`, `current_city`, `current_sort`, `current_listing_purpose`, `current_features`, `current_condition`, `active_price_min`, `active_price_max`, `min_price`, `max_price` are all already exposed to the template by the listings/search views (verified present in context by Spec 05 T1/T3 evidence).
6. **HTMX is always available.** Per `ads/list.html` L17–19 / `ads/detail.html` L22–24, HTMX 2.0.10 is SRI-loaded with `defer` on the catalog/detail pages. The clear-all being HTMX-driven (no full-page fallback required) is consistent with every other control in `ad_list.html`.

---

## 9. Constraints

| # | Constraint | How satisfied |
|---|---|---|
| C1 | `hx-get=` count in `ad_list.html` source stays **10** (4 chips + clear-all + 5 pagination) | Clear-all keeps exactly one `hx-get=`; moving/converting element type doesn't add or remove attributes. (T6 verifies.) |
| C2 | `hx-push-url="true"` count stays **10**; clear-all retains `hx-push-url` + `hx-target="#ad-list"` + `hx-swap="innerHTML"` | Attributes preserved verbatim on relocation/conversion. |
| C3 | Clear-all remains inside the chips-block `{% if %}` (L33) — `test_clear_all_filters_static_guard` position/depth/window | T1 keeps clear-all as first child of the chips-row div, which is inside the `{% if %}`; depth loop ends `> 0`. |
| C4 | `q` preserved on `/search/?q=…`; `q` absent on listings (`/`) | Clear-all URL template (`href`/`hx-get`) unchanged (`{% if query %}&q=…{% endif %}`); T2 ensures the rendered-output test actually targets this URL. |
| C5 | i18n: `{% trans "Clear all filters" %}` intact; msgid present in `ru`/`en`/`bs` `.po` files | No new msgid; `make makemessages` + `make compilemessages`; `test_i18n_completeness.py` green. |
| C6 | Templates djlint-clean | `uv run djlint src/backend/templates/` after edit. |
| C7 | Tests encode correct behavior; production template conforms (AGENTS.md rule #2) | If the implementer's formatting drifts the 6-line window in `test_clear_all_filters_static_guard`, adjust the template (not loosen the test). |
| C8 | 44 px touch-target for the clear-all (if Q1=A) | `min-h-[44px]` + `flex items-center` on the button. |
| C9 | Vanilla JS / HTMX only; no new frontend framework | No JS added (HTMX attributes only). |
| C10 | Test environment = Docker PostgreSQL on port 5433; `make test` (fast gate) / `make test-recreate` | All verification via `make test`; no local `uv run pytest`. |

---

## 10. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Latent test-targeting bug masked by the L81 comment.** If T2 is skipped, `content.index("Clear all filters")` matches the comment first, so the clear-all URL tests silently assert on a chip URL. Moving clear-all without removing the comment could flip which chip URL is asserted. | High (already latent) | Medium | T2 makes comment removal/conversion **required**; T6 re-runs the URL-preservation tests and they must assert the clear-all URL. |
| R2 | `test_clear_all_filters_static_guard` 6-line window (`lines[clear_idx-6:clear_idx+1]`) drifts if the implementer spreads the clear-all element's attributes over >6 lines above the `{% trans %}` tag. | Medium | Medium | Keep `hx-push-url="true"` within 3 lines of the `{% trans %}` tag (place URL/`href` attrs on ≤2 lines above it); T6 asserts the test green. |
| R3 | Converting `<a>`→`<button>` changes `href` (navigation fallback) to none; if HTMX fails to load, clear-all becomes a no-op button. | Low | Low | HTMX is SRI-pinned + `defer` on every catalog/detail page; all peer controls are already HTMX-driven. No-JS degradation is pre-existing for this page. |
| R4 | A 44 px button in a row of ~24 px pill-chips looks visually heavy / misaligned without `items-center`. | Medium | Low | T5 adds `items-center`; T4 uses `rounded-lg` (not `rounded-full`) to keep clear-all from masquerading as a chip. |
| R5 | Future "clear-all visible even with no chips" feature request conflicts with current gating. | Low | Low | Assumption §3 documents current intent; any change is a new feature, not this fix. |

---

## 11. Open Questions (for PO confirmation)

1. **Q1 element-type override.** Does the PO accept `<button type="button">` (recommended), or prefer to keep the `<a>` text-link and only relocate it (Option B — retains no-JS `href` fallback)? *Recommended default: A; flagged for confirmation.*
2. **Q3 touch-target strictness.** If the PO overrides Q1 to B (keep `<a>`), should `min-h-[44px]` still be added to the `<a>` (links accept `min-h` in Tailwind)? *Recommended: yes, to satisfy the design-system 44 px rule regardless of element type.*
3. **Comment policy.** Does the team prefer the L81 comment converted to `{# #}` (keep docs) or deleted outright? *Recommended: convert to `{# #}`* (preserves maintainer context; i18n scan strips it).
4. **Button label wording.** "Clear all filters" is the existing, translated msgid — no change. (Listed only to confirm no copy change is intended.)

---

## 12. Out of Scope

- **Reset semantics / URL architecture** (Spec 05 / `filter-ui.md` L403–433): clear-all URL, q-preservation, path-param preservation — all unchanged.
- **Price chip conversion** (Spec 05 T3): already done; not re-opened.
- **City/category coexistence / header-JS navigation** (Spec 05 T5, Spec 07): orthogonal to the chip-row layout.
- **Language-switcher staleness** (Spec 05 T6): orthogonal.
- **Backend/view/filter-logic changes**: the listings/search views, `query_replace`, sort, and PostgreSQL FTS are all untouched.
- **Production data / migrations**: template-only change; no schema change.
- **Mobile filter drawer** (`filter_form.html` slide-up panel): the clear-all lives on the catalog results row (`ad_list.html`), not the drawer.

---

## 13. Definition of Ready (for implementation planning)

This specification is ready to hand off to implementation when all of the following hold:

1. ✅ The defect is bounded to template structure + styling (no backend/view change) — verified §2.1.
2. ✅ The exact lines to change are cited (`ad_list.html` L34, L80–88; the L81 comment).
3. ✅ The chips-block `{% if %}` gating is confirmed intact after relocation (clear-all stays first child of the chips-row `<div>`, inside the `{% if %}`).
4. ✅ All constraining tests are enumerated with PASS/FAIL-by-design under each option (Researcher matrix §6; verified §2.6).
5. ✅ The latent L81-comment test-targeting bug is identified and its fix (T2) is a required task.
6. ✅ HTMX `<button>` equivalence is verified against the pinned 2.0.10 and project precedent.
7. ✅ PO decisions Q1–Q4 are recorded with recommended defaults (§7).
8. ✅ Constraints (10/10 count, 44 px, i18n, djlint, test-in-Docker) are documented.
9. ✅ Risks (esp. R1 the comment shadow) and mitigations are documented.
10. ✅ The Definition-of-Ready test checklist (§6) is explicit and runnable: `make test-recreate` then `make test` + `test_i18n_completeness.py`.
11. ✅ Out-of-scope items (reset semantics, URL architecture, price chip, city/category, language-switch) are explicit to prevent scope creep.

---

## 14. Affected-Artifact Index

| Artifact | Role | Change? |
|---|---|---|
| `src/backend/templates/ads/partials/ad_list.html` (L33–88) | Chips-block `{% if %}`, chips-row `<div>`, chips, clear-all `<a>` | **Yes** — relocate clear-all to first child of `<div>` (L34); neutralize L81 comment (T2) |
| `src/backend/apps/ads/tests/test_catalog_filters.py` (L624–927) | All clear-all / chip-row test guards | No (verify only; T6) — T3→T6 |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` (L145–244) | No-hardcoded-text / msgid-completeness gates | No (verify only) — T6 |
| `src/backend/apps/search/tests/test_autocomplete_template.py` | Header/city/search-clear — **not** clear-all | No (out of scope) |
| `docs/01-spec/filter-ui.md` (L403–433) | Clear-all reset semantics | No (unchanged semantics) |
| `src/backend/templates/components/header_catalog.html` | Header clear button (Plan 17) — different control | No (out of scope) |
| HTMX (pinned 2.0.10) | `ads/detail.html` L22–24, `ads/list.html` L17–19 | Reference only — no change |
| Locale `.po`/`.mo` (`ru`/`en`/`bs`) | `django.po` L397/381/397 ("Clear all filters") | No new msgid — `makemessages`/`compilemessages` for DoD |

---

## 15. Acceptance Criteria

| # | Given | When | Then |
|---|---|---|---|
| A1 | Buyer on `/?features=delivery` (HX request) | renders `ad_list.html` | The "Clear all filters" control is the **first element** inside the same `flex flex-wrap` row as the feature chip(s), i.e. rendered before any chip `<span>` in source order. |
| A2 | Buyer on `/` with no filters | renders `ad_list.html` | The chips-block `{% if %}` is false → neither chips nor clear-all render (`"Clear all filters" not in content`, `"&times;" not in content`). |
| A3 | Buyer on `/?min_price=100&max_price=500` | renders | Both the price chip and the clear-all control render in the same row; clear-all is first. |
| A4 | Buyer on `/search/?q=test&min_price=100` | the clear-all URL in rendered output (extracted by targeting the clear-all element, not a comment) | contains `q=test` (search-query preserved). |
| A5 | Buyer on `/?min_price=100` | the clear-all URL in rendered output | contains no `q=` (listings page, `query` is None). |
| A6 | Source `ad_list.html` | linted | exactly 10 `hx-get=` and 10 `hx-push-url="true"` lines (unchanged). |
| A7 | Source `ad_list.html` | scanned by i18n | `{% trans "Clear all filters" %}` intact; no hardcoded visible text; `test_no_hardcoded_visible_text` + `test_extraction_completeness` + `test_no_empty_msgstr` + `test_mo_compiled` pass. |
| A8 | (If Q1=A) the clear-all control | inspected | is a `<button type="button">` with `min-h-[44px]` (≥44 px touch target), `rounded-lg` (not `rounded-full`). |
| A9 | (If Q1=A) buyer clicks clear-all | on `/?features=delivery&listing_purpose=sell` | HTMX `hx-get` fires with `hx-push-url="true"`, target `#ad-list`, swaps results to `?page=1&lang=…`, URL updates, chips + clear-all disappear. |
| A10 | Full suite | `make test-recreate` then `make test` | all `test_catalog_filters.py` and `test_i18n_completeness.py` tests green. |

---

## 16. Implementation Notes (for the implementer)

- **Line-budget anchor:** `test_clear_all_filters_static_guard` reads `lines[clear_idx-6 : clear_idx+1]` for `hx-push-url="true"`. Keep the clear-all element's `hx-push-url="true"` attribute within **3 lines** of its `{% trans "Clear all filters" %}` tag (the URL/`hx-*` attributes occupy the lines immediately above the trans tag) so the 6-line look-back always captures it.
- **Depth anchor:** do **not** start any `{% if %}` / `{% for %}` between the chips-row `<div>` (L34) and the clear-all element without closing it on the same construct; the test's depth counter starts at 1 (inside the chips `{% if %}`) and must end `> 0` at the clear-all trans tag. Inline `{% if query %}…{% endif %}` URL pairs on the same line are fine (they cancel).
- **Comment:** convert `<!-- Clear all filters: resets ... -->` (L81) to `{# Clear all filters: resets all query params (...); category/city are path params, naturally preserved. #}` — or delete it. A Django comment is stripped at render time and by the i18n scan, so neither `test_no_hardcoded_visible_text` nor `_extract_clear_all_hx_get` will be affected.
- **Element shape:** if Q1=A, the clear-all **must not** be `rounded-full` (that is the chip grammar); use `rounded-lg`. Chips keep `rounded-full`.
- **No URL logic change:** the clear-all `hx-get`/`href` URL string (`?page=1{% if query %}&q={{ query|urlencode }}{% endif %}{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}`) is copied verbatim from the current `<a>` (L82–83) onto the new element.
- **djlint:** keep attributes aligned and indentation at 4 spaces (AGENTS.md: 4-space indentation, never tabs).
