# Implementation Plan — Header Search Clear Button (Spec 16)

**Source spec:** `.ai/problems/16_search-clear-ux_spec.md`
**Scope:** Pure template + inline-JS + test + documentation fix. No backend, schema, or migration changes.
**Status:** COMPLETED — all tasks verified green (djlint clean, 1154 tests pass, i18n 5 pass, smoke checks pass)

---

## 1. Overview

The header search bar in `header_catalog.html` renders two overlapping "X" buttons:
1. A **native browser clear-X** (large, Chrome/Edge/Safari) that only clears the input field without navigating.
2. A **custom `data-search-clear` button** (tiny 20×20 px, server-conditional on `{% if query %}`) wired to `window.history.back()` — unreliable and history-dependent.

The fix consolidates these into a single large (44×44 px) clear button with a deterministic dual-behavior JS handler: clears the `q` URL param and reloads on the search results page, but only clears the input text while typing on other pages.

---

## 2. Decision Gates

| Gate | Question | Options | Resolved Choice | Rationale |
|---|---|---|---|---|
| **Q5** | Suppress native X via CSS on `type="search"`, or switch to `type="text"`? | (A) Keep `type="search"` + CSS `::-webkit-search-cancel-button { -webkit-appearance: none; appearance: none; }` · (B) Switch to `type="text"` | **(A) — Assumed default** | `type="search"` preserves semantics; only WebKit/Blink render the native X (Firefox doesn't); CSS suppression is standard and verified-safe by grep (no test asserts `type="search"`) |

> If (A) fails cross-browser validation during implementation, fall back to (B) — but this requires re-verifying `test_search_input_has_htmx_autocomplete_attributes` does not assert on `type`.

No other gates remain open — PO-1 through PO-4 are all confirmed in the spec.

---

## 3. Execution DAG

```
task_001  ──► task_002 ──► task_003
  CSS          Button       JS handler
  suppress     markup       (dual-behavior)
                  │
                  ▼
    ┌───────────┬───────────┬───────────┐
    │           │           │           │
task_004     task_005     task_006
(test)      (i18n)      (doc)
    │           │           │
    └───────────┴───────────┘
                  │
                  ▼
               task_007
              (verify)
```

### Parallel execution groups

| Group | Tasks | Can run in parallel? | Trigger |
|---|---|---|---|
| 1 | `task_001` | — (only task) | Start of implementation |
| 2 | `task_002` | — (only task) | After task_001 |
| 3 | `task_003` | — (only task) | After task_002 |
| 4 | `task_004`, `task_005`, `task_006` | **Yes** | After task_003 (doc/i18n need full template; test needs all template changes) |
| 5 | `task_007` | — (only task) | After group 4 |

### Rationale for grouping

- Tasks 1→2→3 are sequential because each builds on the previous: CSS suppression (standalone), then button markup (removes broken `onclick`), then JS handler (binds to the new button).
- Tasks 4, 5, 6 are independent of each other but all depend on the template being fully modified. They can run in parallel after task_003.
- Task 007 (verification) is the gated checkpoint before completion.

---

## 4. Task Specifications

---

### task_001 — Suppress native browser clear-X

```yaml
id: task_001
type: implementation
priority: high
depends_on: []
source_reference:
  source_file: .ai/problems/16_search-clear-ux_spec.md
  source_section: "T1 — Suppress the native browser clear-X; Q5 (Section 9); AC1"
```

**Description:**
Add a CSS rule to suppress the browser's native `::-webkit-search-cancel-button` on the search input, ensuring only the custom clear button renders (R1: single clear control only).

**Affected module:**
- `src/backend/templates/components/header_catalog.html`

**Semantic target:**
- `#search-input` — the `<input type="search" id="search-input" name="q">` element in the header search form (`data-search-form`).

**Change — `header_catalog.html` (insert new `<style>` block before the existing `<script>` block):**
```css
<style>
    #search-input::-webkit-search-cancel-button {
        -webkit-appearance: none;
        appearance: none;
    }
</style>
```

**Risk:** Low — CSS-only addition, no functional behavior change. Suppressed element is purely cosmetic (browser-provided widget).

**Acceptance criteria:**
- AC1: `::-webkit-search-cancel-button` with `-webkit-appearance: none` (or `appearance: none`) is present in `_HEADER_CATALOG_CONTENT`.
- `type="search"` is retained on `#search-input` (Q5 assumed default A).
- djlint-clean (no new violations; `<style>` block is valid in body context per existing H021 ignore).

**Verification (inline):**
- `grep '::-webkit-search-cancel-button' src/backend/templates/components/header_catalog.html` confirms the rule exists.

---

### task_002 — Replace small conditional button with persistent large button

```yaml
id: task_002
type: implementation
priority: high
depends_on: [task_001]
source_reference:
  source_file: .ai/problems/16_search-clear-ux_spec.md
  source_section: "T2 — Replace the server-conditional small button with a persistent large button; AC2–AC4, AC7"
```

**Description:**
Remove the `{% if query %}` server-side conditional wrapper so the clear button is always rendered in the DOM. Increase the touch target to 44×44 px (matching all other interactive elements in this template). Remove the unreliable `onclick="window.history.back()"` handler. Add the `hidden` class so the button starts invisible (JS in task_003 will toggle visibility).

**Affected module:**
- `src/backend/templates/components/header_catalog.html`

**Semantic target:**
- The `[data-search-clear]` button currently wrapped in `{% if query %} … {% endif %}` (the button that renders `&times;` as its content).

**Changes — `header_catalog.html` (replace the `{% if query %}…{% endif %}` button block):**

1. **Remove** the `{% if query %}` and `{% endif %}` wrapper tags.
2. **Replace** the button class attribute:
   - Old: `class="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center text-gray-400 hover:text-gray-600"`
   - New: `class="absolute right-3 top-1/2 -translate-y-1/2 w-6 h-6 min-w-[44px] min-h-[44px] flex items-center justify-center text-gray-400 hover:text-gray-600 hidden"`
3. **Remove** `onclick="window.history.back()"` attribute entirely.
4. **Keep** `type="button"`, `data-search-clear`, `aria-label="{% trans "Clear search" %}"`, and `&times;` content.

**Rationale for class changes:**
- `w-6 h-6` → 24×24 px icon (increased from 20×20).
- `min-w-[44px] min-h-[44px]` → enforces the 44×44 px minimum touch target (C1).
- `hidden` → button starts hidden; JS shows it when input has text (AC6).

**Risk:** Low — removes a broken handler (`window.history.back()`); no test asserts `type="search"` or the old button class.

**Existing test impact:**
- `test_search_clear_button_is_wired_to_history_back` (lines 75-81 of `test_autocomplete_template.py`) currently asserts `window.history.back()` IS present and `data-search-clear` IS present. This will break — addressed by task_004.

**Acceptance criteria:**
- AC2: `data-search-clear` appears exactly once in `_HEADER_CATALOG_CONTENT` (not inside `{% if query %}`).
- AC3: `window.history.back()` is NOT present in `_HEADER_CATALOG_CONTENT`.
- AC4: `min-w-[44px]` or equivalent 44-px touch-target class is present on the `[data-search-clear]` button.
- AC7: `{% trans "Clear search" %}` is present on the button's `aria-label`.

---

### task_003 — Implement dual-behavior JS handler

```yaml
id: task_003
type: implementation
priority: high
depends_on: [task_002]
source_reference:
  source_file: .ai/problems/16_search-clear-ux_spec.md
  source_section: "T3 — Implement the dual-behavior JS handler; PO-1 (Q1=A); AC5, AC6"
```

**Description:**
Add vanilla JS (no framework — C3) inside the existing IIFE `<script>` block to: (a) show/hide the clear button based on input value, and (b) handle the click with dual behavior — navigate to the current URL without `q` when a search is committed, or just clear the input text when typing.

**Affected module:**
- `src/backend/templates/components/header_catalog.html` (inline `<script>` block, IIFE starting with `(function () {`)

**Semantic target:**
- The inline `<script>` block that already defines `searchInput` (`document.getElementById('search-input')`) inside the `if (dropdown && searchInput)` guard.

**Change — insert after the `searchInput` assignment (inside the `if (dropdown && searchInput)` block):**

```javascript
/* ── Clear button: show/hide + dual-behavior click ─────────────── */
var clearBtn = document.querySelector('[data-search-clear]');

function updateClearButton() {
    if (!clearBtn) return;
    if (searchInput.value.length > 0) {
        clearBtn.classList.remove('hidden');
    } else {
        clearBtn.classList.add('hidden');
    }
}

searchInput.addEventListener('input', updateClearButton);
updateClearButton();  // initial state for server-rendered pre-filled query

if (clearBtn) {
    clearBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var params = new URLSearchParams(window.location.search);
        if (params.has('q') && params.get('q') === searchInput.value) {
            // Committed search: remove q param, preserve category/city/sort/filters
            params.delete('q');
            var url = new URL(window.location.href);
            url.search = params.toString();
            window.location.href = url.toString();
        } else {
            // Just typing: clear input only
            searchInput.value = '';
            updateClearButton();
        }
    });
}
```

**Behavioral contract:**
- **Show/hide:** Button is `hidden` by default; `updateClearButton()` removes `hidden` when `searchInput.value.length > 0`, adds it back when empty. Called on `input` event and once on page load (for server-pre-filled query).
- **Click:** Checks if the URL's `q` param matches the current input value (i.e., a search was actually submitted). If so, deletes `q` from the URL via `URLSearchParams` and navigates (PO-1=A: preserve category/city/sort/filters, deterministic not history-dependent). If the input was just typed but not submitted, clears the input field only.

**Risk:** Low — follows the existing inline-JS pattern (no `hx-on`, no new library — C3). All DOM references (`searchInput`, `dropdown`) are already defined and guarded in the same scope.

**Acceptance criteria:**
- AC5: `searchParams.delete('q')` or `URLSearchParams` or `new URL(` is present in the inline `<script>` block.
- AC6: `hidden` class is present on the button (from task_002) and an `input` event handler toggles visibility (function named `updateClearButton` or equivalent).
- AC3 (reinforced): no `window.history.back()` in the handler — click uses URL param manipulation instead.

---

### task_004 — Update existing test for new clear-button behavior

```yaml
id: task_004
type: test
priority: high
depends_on: [task_001, task_002, task_003]
source_reference:
  source_file: .ai/problems/16_search-clear-ux_spec.md
  source_section: "T4 — Update existing test; AC1–AC7"
```

**Description:**
Rename and rewrite `test_search_clear_button_is_wired_to_history_back` to `test_search_clear_button_cleares_query_param`, and add new test functions covering all seven acceptance criteria. The test reads the template source directly (no database needed) and performs string assertions on `_HEADER_CATALOG_CONTENT`.

**Affected module:**
- `src/backend/apps/search/tests/test_autocomplete_template.py`

**Semantic target:**
- The test function `test_search_clear_button_is_wired_to_history_back` (lines 75–81).

**Changes:**

1. **Replace** `test_search_clear_button_is_wired_to_history_back`:
   ```python
   def test_search_clear_button_cleares_query_param() -> None:
       """The clear-search button is always rendered (not server-conditional),
       is a 44×44 px touch target, does not use window.history.back(),
       and uses URLSearchParams to delete the q param (Spec 16, PO-1=A)."""
       # AC2: button is always present, not wrapped in {% if query %}
       assert "data-search-clear" in _HEADER_CATALOG_CONTENT
       assert "{% if query" not in _HEADER_CATALOG_CONTENT  # no server-conditional
       # AC3: no history.back()
       assert "window.history.back()" not in _HEADER_CATALOG_CONTENT
       # AC4: 44×44 px touch target
       assert "min-w-[44px]" in _HEADER_CATALOG_CONTENT
       assert "min-h-[44px]" in _HEADER_CATALOG_CONTENT
       # AC7: aria-label uses {% trans %}
       assert '{% trans "Clear search" %}' in _HEADER_CATALOG_CONTENT
   ```

2. **Add** `test_search_input_native_clear_button_suppressed` (AC1):
   ```python
   def test_search_input_native_clear_button_suppressed() -> None:
       """The native WebKit/Safari cancel button is suppressed so only the
       custom clear button renders (Spec 16, R1, Q5 assumed default A)."""
       assert "::-webkit-search-cancel-button" in _HEADER_CATALOG_CONTENT
       assert "-webkit-appearance" in _HEADER_CATALOG_CONTENT
       assert "appearance: none" in _HEADER_CATALOG_CONTENT
   ```

3. **Add** `test_clear_button_has_dual_behavior_js_handler` (AC5, AC6):
   ```python
   def test_clear_button_has_dual_behavior_js_handler() -> None:
       """The clear button JS shows/hides based on input value and uses
       URLSearchParams to delete q on committed search, not history.back()."""
       # AC6: hidden class + input event handler
       assert "hidden" in _HEADER_CATALOG_CONTENT  # button starts hidden
       assert "searchInput.addEventListener('input'" in _HEADER_CATALOG_CONTENT or \
              "addEventListener('input'" in _HEADER_CATALOG_CONTENT
       # AC5: URLSearchParams / searchParams.delete('q') for deterministic clear
       assert "URLSearchParams" in _HEADER_CATALOG_CONTENT or \
              "new URL(" in _HEADER_CATALOG_CONTENT
       assert "searchParams.delete('q')" in _HEADER_CATALOG_CONTENT or \
              "params.delete('q')" in _HEADER_CATALOG_CONTENT
   ```

**Risk:** Low — test-only change. The existing test asserts the OLD (broken) behavior; per AGENTS.md rule #2, updating the test to assert correct behavior is the right action.

**Acceptance criteria:**
- All three test functions pass.
- `window.history.back()` is NOT asserted as present anywhere in the test file.
- Fast gate `make test -k search_clear` passes.

---

## 5. Supporting Tasks (Parallel)

These three tasks are independent of each other and can run in parallel after task_003 completes.

---

### task_005 — i18n extraction + compilation

```yaml
id: task_005
type: i18n
priority: medium
depends_on: [task_001, task_002, task_003]
source_reference:
  source_file: .ai/problems/16_search-clear-ux_spec.md
  source_section: "R6, C4, AGENTS.md rule #16"
```

**Description:**
Run `makemessages` to extract any new translatable strings from the template, then `compilemessages` to compile `.mo` files. Verify i18n completeness.

**Rationale:** The `{% trans "Clear search" %}` string already exists in the current template and is already in the `.po` files. No NEW translatable strings are being introduced (the `&times;` icon content and JS strings are not user-visible translatable text). However, per AGENTS.md rule #16 and R6, the extraction + compilation + completeness verification must be run before commit.

**Changes:** None expected in `.po`/`.mo` files (no new `{% trans %}` or `{{ _("") }}` strings introduced). This task is primarily verification.

**Commands:**
```bash
make makemessages
make compilemessages
```

**Verification:**
- `test_i18n_completeness.py::test_no_empty_msgstr` passes for `ru` and `bs`.
- `test_i18n_completeness.py::test_extraction_completeness` passes (all msgids present across locales).
- `test_i18n_completeness.py::test_mo_compiled` — `.mo` files exist.

**Risk:** Low — no new strings, extraction is a no-op. Compilation refreshes `.mo` timestamps.

---

### task_006 — Update stale research document

```yaml
id: task_006
type: documentation
priority: low
depends_on: [task_001, task_002, task_003]
source_reference:
  source_file: .ai/problems/16_search-clear-ux_spec.md
  source_section: "Definition of Ready #3"
```

**Description:**
Update the stale Bug #2 entry in the research document to reflect the current (post-fix) state.

**Affected file:**
- `.ai/research/search-journeys-spec.md`, Section 5 "Bug Fixes Required", Bug #2

**Semantic target:**
- The Bug #2 bullet point in the `| Bug | Required Fix | Priority |` table:
  > **#2 — Clear (X) button does nothing:** The search input is `<input type="search">` — browsers render a native clear-X that only clears the field without navigating. **No explicit wired clear button exists.** Needs an explicit control that returns to pre-search state.

**Change:**
```markdown
| **#2 — Clear (X) button does nothing** | **RESOLVED (Spec 16):** Replaced dual X buttons with a single 44×44 px `data-search-clear` button. Native WebKit/Safari cancel button suppressed via CSS (`::-webkit-search-cancel-button`). Button is always rendered (not `{% if query %}`-conditional), hidden by default, shown via JS when input has text. Click handler uses `URLSearchParams.delete('q')` for deterministic clear (preserves category/city/sort/filters) — replaces the old `window.history.back()` which was unreliable. | Resolved |
```

**Risk:** None — documentation-only change.

---

## 6. Verification Task

```yaml
id: task_007
type: verification
priority: high
depends_on: [task_004, task_005, task_006]
verifies: [task_001, task_002, task_003, task_004, task_005]
```

**Description:**
Gated checkpoint verifying all template changes, test updates, i18n, and lint pass together.

**Verification steps:**
1. **djlint** — template is clean:
   ```bash
   uv run djlint src/backend/templates/components/header_catalog.html
   ```
2. **Fast gate tests** (template + i18n, no DB needed):
   ```bash
   docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml \
     run --rm -e PYTEST_OPTS="-k 'search_clear or autocomplete_template or i18n'" test
   ```
3. **Full fast gate** (broader regression):
   ```bash
   make test
   ```
4. **Smoke check** — confirm no broken references:
   ```bash
   grep -n "window.history.back()" src/backend/templates/components/header_catalog.html
   # Expected: no output (asserts AC3)
   grep -n "data-search-clear" src/backend/templates/components/header_catalog.html
   # Expected: exactly one match
   ```

**Pass criteria:**
- djlint reports zero errors on `header_catalog.html`.
- `test_search_clear_button_cleares_query_param` passes (replaces old `test_search_clear_button_is_wired_to_history_back`).
- `test_search_input_native_clear_button_suppressed` passes (AC1).
- `test_clear_button_has_dual_behavior_js_handler` passes (AC5, AC6).
- `test_i18n_completeness.py` all 4 guard tests pass.
- `make test` (fast gate) is fully green.
- `grep` smoke check: `window.history.back()` absent, `data-search-clear` present exactly once.

**Failure action:** Return the failed task to `pending` for rework; verify no regression in unrelated `test_autocomplete_template.py` tests.

**Rollback:** Revert `header_catalog.html` to the `{% if query %}` + `onclick="window.history.back()"` block and restore the old test function. No data migration or schema rollback needed.

---

## 7. Acceptance Criteria Coverage Matrix

| AC | What it asserts | Task implemented | Test task |
|---|---|---|---|
| AC1 | Native cancel button suppressed via CSS, or `type="text"` | task_001 | task_004 |
| AC2 | `data-search-clear` always rendered (not in `{% if query %}`) | task_002 | task_004 |
| AC3 | `window.history.back()` NOT in template content | task_002 (remove), task_003 (replace) | task_004 |
| AC4 | 44×44 px touch target (`min-w-[44px]` / `min-h-[44px]`) | task_002 | task_004 |
| AC5 | JS handler uses `URLSearchParams` / `new URL(` + `searchParams.delete('q')` | task_003 | task_004 |
| AC6 | Button starts `hidden`, JS toggles via `input` event | task_002 (class), task_003 (logic) | task_004 |
| AC7 | Button `aria-label` uses `{% trans "Clear search" %}` | task_002 (retain) | task_004 |

---

## 8. Constraints Checklist

| Constraint | How satisfied | Verification |
|---|---|---|
| C1: ≥44×44 px touch target | `min-w-[44px] min-h-[44px]` on button | AC4 / task_004 |
| C2: No `window.history.back()` | Removed in task_002, replaced by URL manipulation in task_003 | AC3 / task_004 |
| C3: No new frontend framework | Vanilla inline JS in existing `<script>` block | code review / task_007 |
| C4: i18n `{% trans %}` / `gettext` | `aria-label` already uses `{% trans "Clear search" %}`; no new strings | task_005 / i18n tests |
| C5: djlint-clean | Template runs through djlint after changes | task_007 |

---

## 9. Out of Scope (not in this plan)

- `ad_list.html` "Clear all filters" link (`src/backend/templates/ads/partials/ad_list.html`) — already matches OLX two-tier pattern, no change (R5).
- Backend `search.py` — empty `q` already falls through to unfiltered listing (A5).
- `detail.html` "Back to listings" link (`javascript:history.back()`) — unrelated, not the search clear button.
- Autocomplete "recent history" clear buttons within the dropdown — separate concern.

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CSS `::-webkit-search-cancel-button` doesn't suppress in some WebKit build | Low | Low | AC1 assertion verifies the rule is present in template; visual QA on Safari/Chrome recommended |
| Button hidden by default with no JS → invisible clear button | Low | Medium | `updateClearButton()` called on page load + input event (AC6); graceful degradation: native X still works in WebKit if CSS suppression fails |
| Removing `{% if query %}` changes layout when no query | Low | Low | Button has `hidden` class by default; `updateClearButton()` hides it when input is empty — visually identical to before |
| Existing `test_search_clear_button_is_wired_to_history_back` breaks | High (expected) | None | task_004 replaces it with correct assertions; AGENTS.md rule #2 supports updating tests |
| i18n test flags new hardcoded text in `<style>` block | Low | Low | `test_no_hardcoded_visible_text` strips `<style>` tags; CSS rule is not translatable text |

---

## 11. Implementation Sequence (Recap)

```
1. task_001  — Add CSS suppression rule for ::-webkit-search-cancel-button
2. task_002  — Remove {% if query %}, resize button to 44×44, remove onclick, add hidden
3. task_003  — Add updateClearButton() + dual-behavior click handler in inline <script>
4. ─ Parallel ─
   4a. task_004 — Rename/rewrite test, add AC1–AC7 assertion functions
   4b. task_005 — makemessages + compilemessages + i18n verification
   4c. task_006 — Update stale Bug #2 in search-journeys-spec.md
5. task_007  — Verification: djlint + fast gate + smoke checks
```
