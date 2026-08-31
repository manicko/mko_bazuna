# Spec 16 — Header Search Clear Button: Remove Dual X, Make Single Clear Button Large & Obvious

| Field | Value |
|---|---|
| Spec ID | 16 |
| Title | Header search bar must show a single, large, obvious clear button (not the native browser X) that clears the search query and reloads, following the OLX two-tier pattern |
| Status | Analyses — pending PO confirmation of assumed defaults |
| Related problem input | `.ai/problems/Problem_01.md` (bug #2: "Если после первого поиска нажал крестик — ничего не происходит") |
| Source of truth (live impl) | `src/backend/templates/components/header_catalog.html:134-151` |
| Existing test baseline | `src/backend/apps/search/tests/test_autocomplete_template.py:75-81` (`test_search_clear_button_is_wired_to_history_back`) |
| Research source | `.ai/research/olx-search-journeys.md` (Section 16 — verified live via Playwright on `olx.kz`, 2026-08-29) |
| Stack context | Django 5.2 LTS (HTMX MPA, gunicorn WSGI) + aiogram bot · Tailwind CSS v4 · PostgreSQL 18 · vanilla inline JS (no framework) |

---

## 1. Problem statement

When a buyer is on the search results page (`/search/?q=…`) with an active query, the header search input — a `<input type="search">` — renders **two overlapping "X" buttons** that behave differently, causing user confusion:

1. **Native browser clear-X** — Chrome/Edge/Safari render a built-in clear button on `type="search"` inputs whenever the field has text. Clicking it **clears only the input field value** (client-side); it does **not** submit a new search, so the URL still carries `?q=…` and the results stay the same.

2. **Custom `data-search-clear` button** — rendered server-side only when `{% if query %}` is truthy (`header_catalog.html:145-151`), it is only 20×20 px (`w-5 h-5`), positioned at `absolute right-3 top-1/2`, and wired to `onclick="window.history.back()"`.

**Symptom:** Two X buttons side by side, one tiny (custom) and one large (native). The tiny one does `history.back()` (unreliable — may leave the site or land on an unrelated page) while the large one does nothing visible. Buyer is left unsure how to actually clear the search.

### Code-verified evidence

**`header_catalog.html:134-151` (current):**
```html
<input type="search" id="search-input" name="q" value="{{ query|default:'' }}" ...>
{% if query %}
    <button type="button" data-search-clear
            class="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center text-gray-400 hover:text-gray-600"
            aria-label="{% trans "Clear search" %}"
            onclick="window.history.back()">&times;</button>
{% endif %}
```

**Grep confirms `window.history.back()` is wired only to the clear button in the header** (the other two `history.back()` references are unrelated: `detail.html:180` is a "Back to listings" link, `test_detail_render.py` asserts that link — neither is the search clear button).

**Search URL structure:** `search/urls.py:12` → `GET /search/?q=…&category=…&city=…`. The search view (`search.py`) reads `q` via `request.GET.get("q")`; an empty `q` falls through to the unfiltered ad list.

---

## 2. Confirmed requirements

| # | Requirement | Source / evidence |
|---|---|---|
| R1 | The native browser clear-X must **not** render on the search input. Only one clear control may appear. | User complaint: "2 X buttons — one large (native), one small (custom)" |
| R2 | The clear button must be **large and obvious** — at least a 44×44 px touch target (matching the project's existing 44 px minimum — `header_catalog.html:47,63,83,106`), positioned at the right edge of the input. | User complaint: "small" / "misleading"; AGENTS.md Touch Target Guidelines (44 px minimum) |
| R3 | Clicking the clear button must **clear the search query and reload results** (navigate to the current search URL without the `q` parameter), preserving category/city/sort/filter params if present. | PO decision (Q1=A): follows OLX `clear-btn` pattern; deterministic, not history-dependent |
| R4 | The clear button must be visible whenever the input contains text — both on the search results page (server `query` truthy) and while typing on any other page (client-side input value non-empty). | PO decision (Q3=B): dual behavior — clear+reload if a query is committed, clear-input-only if just typing |
| R5 | The existing results-page "Clear all filters" link (`ad_list.html:69-74`) is the **second tier** of the two-tier pattern: it clears all filters (price, purpose, features, condition) but **preserves the search query** and sort, then re-renders. This must remain unchanged. | OLX research Section 16; PO decision (Q4: follow OLX) — the link already matches |
| R6 | All user-visible strings must be wrapped in `{% trans %}` / `{% blocktrans %}` and Python strings in `gettext` / `gettext_lazy`. `msgstr` must be non-empty for `ru` and `bs`; `en` may be empty. Run `make makemessages` then `make compilemessages`. Must pass `test_i18n_completeness.py`. | AGENTS.md rule #16 |
| R7 | Template must be djlint-clean. | AGENTS.md lint rules |

---

## 3. Conceptual development tasks

Each task is independent and can be owned/planned separately.

### T1 — Suppress the native browser clear-X

- **Purpose:** Eliminate the large native browser X so only the custom button renders.
- **Concrete change (`header_catalog.html`):**
  - Add a CSS rule to hide `::-webkit-search-cancel-button` on `#search-input`:
    ```css
    #search-input::-webkit-search-cancel-button {
        -webkit-appearance: none;
        appearance: none;
    }
    ```
  - Alternatively (or additionally), consider switching `type="search"` → `type="text"` for cross-browser consistency (Firefox does not render a native X on `type="search"` anyway, but `type="search"` has minor accessibility/behavior differences). **Decision needed:** keep `type="search"` + CSS, or switch to `type="text"`. *(See Open Questions.)*
- **Expected outcome:** No native clear-X appears in any browser; only the custom button is visible.
- **Dependencies:** None.
- **Test impact:** `test_autocomplete_template.py` does not assert on `type="search"` — safe. But AC-1 (below) will assert `::-webkit-search-cancel-button` suppression is present in the template.

### T2 — Replace the server-conditional small button with a persistent large button

- **Purpose:** Render a single, large, obvious clear button that is always in the DOM, with visibility controlled by JS when the input has text.
- **Concrete change (`header_catalog.html:145-151`):**
  - Remove the `{% if query %}` wrapper — the button is always rendered but hidden by default.
  - Change the button class from `w-5 h-5` (20×20) to at least `w-6 h-6 min-w-[44px] min-h-[44px]` (24×24 icon in a 44×44 touch target) — consistent with all other interactive elements in this template (`header_catalog.html:47,63,83,106`).
  - Keep `data-search-clear` attribute (tests may reference it).
  - Set `aria-label="{% trans "Clear search" %}"` (already present).
  - Remove `onclick="window.history.back()"` — replace with a delegated JS handler (T3).
- **Expected outcome:** A single, 44×44 px clear button at the right edge of the search input, present in the DOM at all times, visible only when the input has text.
- **Dependencies:** T1 (suppression must be in place).
- **Test impact:** `test_search_clear_button_is_wired_to_history_back` (L75-81) must be updated — it currently asserts `window.history.back()` is present. The new assertion should verify the button exists with `data-search-clear` and that `window.history.back()` is **absent**, replaced by the new handler.

### T3 — Implement the dual-behavior JS handler for the clear button

- **Purpose:** When the input has text, clicking the button either (a) clears the input text only (if on a non-search page or query not yet committed), or (b) clears the query and reloads without `q=` (if on a search results page with a committed query).
- **Concrete change (`header_catalog.html` inline `<script>` block, L213-577):**
  - Add a JS handler bound to `[data-search-clear]`:
    ```js
    // Show/hide clear button based on input value
    function updateClearButton() {
        var clearBtn = document.querySelector('[data-search-clear]');
        if (!clearBtn) return;
        if (searchInput && searchInput.value.length > 0) {
            clearBtn.classList.remove('hidden');
        } else {
            clearBtn.classList.add('hidden');
        }
    }
    searchInput.addEventListener('input', updateClearButton);
    // Also check on page load (for pre-filled query from server)
    updateClearButton();
    ```
  - On click: check if the current URL's `q` param equals the current input value (i.e., a search has been committed). If so, remove `q` from the URL and navigate. If not (user is just typing), clear the input value.
    ```js
    clearBtn.addEventListener('click', function (e) {
        e.preventDefault();
        if (window.location.searchParams && window.location.searchParams.get('q')) {
            // Committed search: clear query param and reload
            var url = new URL(window.location.href);
            url.searchParams.delete('q');
            window.location.href = url.toString();
        } else {
            // Just typing: clear input only
            searchInput.value = '';
            updateClearButton();
        }
    });
    ```
- **Expected outcome:** Single behavior — button is visible when input has text; clicking it clears the query and navigates to `/search/` (without `q`) when a search was committed; otherwise just clears the input text.
- **Dependencies:** T2 (button must exist in DOM).
- **Test impact:** `test_search_clear_button_is_wired_to_history_back` must be replaced with a test asserting the new handler logic (no `history.back()`, presence of `searchParams.delete('q')` or equivalent).

### T4 — Update existing test

- **Purpose:** Align `test_autocomplete_template.py:75-81` with the new spec.
- **Concrete change:** Rename and rewrite `test_search_clear_button_is_wired_to_history_back` → `test_search_clear_button_cleares_query_param`. Assert:
  - `data-search-clear` is present (always rendered, not server-conditional)
  - `window.history.back()` is **not** present in the template
  - The clear button is sized as a 44×44 touch target (`min-w-[44px]` / `min-h-[44px]` or equivalent)
  - New JS handler uses `searchParams.delete('q')` or `URL` manipulation (deterministic clear, not history-dependent)
- **Dependencies:** T1–T3.

### T5 — Suppress native clear-X CSS (if switching `type="search"` → `type="text"`)

- **Purpose:** If the decision in T1 is to switch to `type="text"`, the `type` attribute must be updated everywhere the search input is declared (only one place: `header_catalog.html:134`).
- **Dependencies:** T1 decision.

---

## 4. Product Owner decisions

All decisions were presented to the PO and confirmed:

| # | Decision | Options | Confirmed choice | Rationale |
|---|---|---|---|---|
| PO-1 | Clear button behavior on results page | (A) Navigate to `/search/` without `q` (clear query, preserve filters) · (B) Navigate to `/` (full reset) · (C) Keep `history.back()` | **(A)** | Deterministic, not history-dependent; matches OLX `clear-btn` — clears query only, preserves other filters |
| PO-2 | Suppress native browser clear-X? | Yes / No | **Yes** | User explicitly complained about dual X buttons; native X only clears input text (confusing) |
| PO-3 | Button visibility | (A) Only on results page (server `{% if query %}`) · (B) Whenever input has text (client-side JS) | **(B)** | Follows Avito/OLX where the input X is always controllable; user should be able to clear typed text on any page |
| PO-4 | Two-tier clear pattern for "Clear all filters" | Keep current `ad_list.html:69-74` (preserves query, drops all filters) · Change to also drop query · Remove entirely | **Keep current** | Matches OLX "Сбросить фильтры" exactly; preserves query, resets filters |

---

## 5. Research summary

A delegated Researcher agent investigated OLX.kz and Avito.ru live (via Playwright, 2026-08-29). Findings published to `.ai/research/olx-search-journeys.md`.

### OLX.kz — two-tier clear pattern (HIGH confidence)

Source: `olx-search-journeys.md` Section 16 — verified live via browser interaction.

| Action | Element | Effect |
|---|---|---|
| **Clear query only** | Small "Clear" (X) button inside the query input | Clears the query text in the search input and re-searches, **preserving** all other filters |
| **Reset all filters** | "Сбросить фильтры" button at bottom of filter sidebar | Clears **ALL** filter parameters and resets the category scope to `/list/q-{query}/` (drops filters, **keeps** query) |
| **Clear individual filter** | Small "Clear" buttons on price inputs | Removes that single price bound |

**Key URL behavior:** OLX uses path-based query encoding (`/list/q-{query}/` or `/{category}/q-{query}/?...`). Clearing the query removes the `q-{query}/` segment, reverting to `/list/` or `/{category}/`. Mko Bazuna uses query-param encoding (`/search/?q=…`) — the equivalent is removing the `q=` param from the URL.

### Avito.ru — no dedicated "clear all filters" button observed

Source: researcher agent's live investigation.

- Searched for "Сбросить" (reset) text on Avito.ru results page → **not found** (`hasСбросить: false`).
- Found "очист" (likely "очистить" = "clear") at HTML position 116399 — investigation pending at agent completion.
- Avito appears to rely on individual filter removal (X on each active filter chip) rather than a single "clear all" button. No standalone "clear all" control was observed on the results page.
- **Decision:** Follow OLX.kz pattern (closer market analog, explicit two-tier clear confirmed). Avito's pattern is less discoverable.

### Relevance to Mko Bazuna

OLX's two-tier pattern maps directly to our current architecture:
1. **Header search input X** (new, large, single button) = OLX's "Clear query only" → clears `q` param, preserves `category`/`city`/`sort`/filters
2. **Results page "Clear all filters"** (exists, `ad_list.html:69-74`) = OLX's "Сбросить фильтры" → drops all filter params, preserves `q` + `sort`

The current code already implements tier 2 correctly. Only tier 1 (the header clear button) needs fixing.

---

## 6. Assumptions

- **A1.** The native browser clear-X on `<input type="search">` is the cause of the "large X" the user sees. This is standard browser behavior for `type="search"` in Chrome/Edge (WebKit/Blink). Firefox does not render a native X. The fix must suppress it in WebKit/Blink.
- **A2.** The `query` template variable (set by `search.py:255`) is the source of truth for whether a search is committed. When `query` is truthy, the page is a search results page with `?q=…` in the URL.
- **A3.** The header search form (`header_catalog.html:127-157`) already carries hidden `category` and `city` inputs when those context vars are set (`L131-132`), so clearing the query via URL param removal will naturally preserve them.
- **A4.** The results-page "Clear all filters" link (`ad_list.html:69-74`) already matches the OLX pattern and does not need changes.
- **A5.** No backend changes are required — this is a pure template + inline-JS fix. The search view (`search.py`) already handles an empty `q` correctly (falls through to unsorted/faceted listing).

---

## 7. Constraints

- **C1.** Touch targets must be ≥44×44 px (AGENTS.md Touch Target Guidelines; `header_catalog.html` already enforces this for all other buttons).
- **C2.** No `window.history.back()` — the behavior must be deterministic (navigate to the clear URL), not history-dependent.
- **C3.** No new frontend framework or library — the header uses vanilla inline JS (HTMX 2.0.10 is present but `hx-on` is not available; existing pattern is inline `<script>`).
- **C4.** i18n: all new/changed user-visible strings must use `{% trans %}` (AGENTS.md rule #16); must pass `test_i18n_completeness.py`.
- **C5.** Templates must be djlint-clean.

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Switching `type="search"` → `type="text"` breaks an existing test assertions | Low | Low | Grep confirms no test asserts `type="search"` on the header input. AC-1 will explicitly cover it. |
| Users on homepage type a query, then want to clear it but the button only appears when text is present — if JS fails, button stays hidden | Low | Medium | Button is in the DOM always; if JS fails, input retains native `type="search"` X in WebKit as a graceful degradation. |
| Clearing `q` param while preserving `category`/`city` shows unexpected results (e.g., all ads in a category when user expected site-wide) | Low | Low | This is the intended Avito/OLX behavior — clear query, keep context |
| Existing test `test_search_clear_button_is_wired_to_history_back` breaks | High (it will definitely break) | None (test must be updated) | T4 explicitly updates this test. The test is a source-of-truth assertion, so updating it is correct per AGENTS.md rule #2 ("fix or remove the tests"). |

---

## 9. Open questions (resolved)

| # | Question | Status |
|---|---|---|
| Q1 | What should the clear button do on the search results page? | **Resolved (PO confirmed):** Navigate to `/search/` without `q=` — clear query, preserve category/city/filters |
| Q2 | Suppress native browser clear-X? | **Resolved (PO confirmed):** Yes |
| Q3 | Button visibility scope? | **Resolved (PO confirmed):** Show whenever input has text (client-side JS), dual behavior |
| Q4 | "Clear all filters" on results page should it also clear query? | **Resolved (PO confirmed):** No — keep as-is (OLX pattern: drops filters, preserves query) |
| Q5 | Keep `type="search"` + CSS suppression, or switch to `type="text"`? | **Assumed default:** Keep `type="search"` + CSS `::-webkit-search-cancel-button { display: none }`. `type="text"` is the no-rebuild alternative if CSS approach has cross-browser gaps. *(PO to confirm.)* |

---

## 10. Out of scope

- Changing the results-page "Clear all filters" link (`ad_list.html:69-74`) — it already matches OLX and needs no change.
- Backend search view changes (`search.py`) — empty `q` is already handled.
- The "Back to listings" link in `detail.html:180` (`javascript:history.back()`) — unrelated, not part of this issue.
- Autocomplete "recent history" clear buttons within the dropdown — separate concern.

---

## 11. Definition of Ready (for implementation)

1. ✅ PO-1, PO-2, PO-3, PO-4 confirmed (above).
2. ✅ Root cause and exact lines to change in `header_catalog.html:134-151` are identified and documented here (Section 1).
3. ✅ The stale research doc (`.ai/research/search-journeys-spec.md` Section 5, Bug #2) claims "no explicit wired clear button exists" — this is **incorrect** per current code (a `data-search-clear` button with `window.history.back()` exists at L145-151, tested at `test_autocomplete_template.py:75-81`). The research doc must be updated during implementation.
4. ✅ `test_autocomplete_template.py::test_search_clear_button_is_wired_to_history_back` baseline is green on `main` (fast gate: `make test -k search_clear`).
5. ✅ Test update (T4) is defined and scoped.
6. ✅ Research (this spec's §5) is reviewed and HIGH confidence for OLX; Avito's pattern is documented for reference.

---

## 12. Acceptance criteria (proposed test additions)

Updates to `src/backend/apps/search/tests/test_autocomplete_template.py`:

- **AC1** — The search input must use `type="search"` with CSS suppression of the native cancel button, OR switch to `type="text"`. Assert the suppression rule (`::-webkit-search-cancel-button` with `-webkit-appearance: none`) is present in the template, OR that the input is `type="text"`.
- **AC2** — The `data-search-clear` button must be rendered **always** (not wrapped in `{% if query %}`). Assert `data-search-clear` appears once in `_HEADER_CATALOG_CONTENT`.
- **AC3** — The clear button must NOT use `window.history.back()`. Assert `"window.history.back()"` is **not** present in `_HEADER_CATALOG_CONTENT` (this also kills the old test `test_search_clear_button_is_wired_to_history_back` — rename it).
- **AC4** — The clear button must have a 44×44 px touch target. Assert `"min-w-[44px]"` or equivalent (`w-6 h-6` + `min-w-[44px]` `min-h-[44px]`) is present on the `[data-search-clear]` button.
- **AC5** — The clear button's JS handler must remove the `q` query parameter from the URL and navigate (not `history.back()`). Assert `"searchParams.delete('q')"` or `"URLSearchParams"` or `new URL(` is present in the inline `<script>` block.
- **AC6** — The button must be hidden by default and shown via JS when input has text. Assert `"hidden"` class is present on the button and that an input event handler toggles visibility (`updateClearButton` or equivalent function name).
- **AC7** — The i18n `aria-label` must use `{% trans %}`: assert `'{% trans "Clear search" %}'` is present in the button markup.
