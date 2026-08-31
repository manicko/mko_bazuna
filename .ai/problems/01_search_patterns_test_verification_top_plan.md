# Search Test Plan

## Purpose

This document defines the verification plan for Mko Bazuna's search functionality. It decomposes search-related user journeys into 11 test blocks, each independently assignable to a Test Engineer for detailed test implementation. The plan is derived from the three research documents in `.ai/research/` (`search-journeys-our-architecture.md`, `search-journeys-spec.md`, `search-journeys-validation.md`) and the Bug Status analysis in `Problem_01.md`.

The six core user-journey scenarios from the research are:
1. Homepage → enter search query → search results
2. Homepage → select category → apply filters → enter search query → results
3. Homepage → enter query → apply filters → results
4. Category page → enter search query → results
5. Category page → apply filters → results
6. Product/ad detail → initiate a new search → results

Plus 8 cross-cutting behaviors: Autocomplete, Preferred City, Language Switching, Search History, Saved Search Modal, Analytics Events, HTMX Contract, and Sorting.

## How to Use

- Each block can be implemented as a separate task by a dedicated Test Engineer.
- The **Journey → Block Mapping Table** (below) ensures full coverage traceability from each journey group to its owning test block.
- Validator recommendations from Block 3 are integrated inline as sub-items or notes within the relevant blocks.
- Blocks are ordered from foundational interaction primitives (entry points) to end-to-end flows (saved-search alerts), reflecting logical dependency flow, not a strict implementation sequence.

**Legend:** `G<N>` = Journey Group number (1–14, as identified by the Researcher). `S<n>.<step>` = Scenario step from the research documents.

---

## Journey → Block Mapping Table

| Journey Group | Journey Group Name | Covered Block(s) |
|---|---|---|
| G1 | Search Entry Points & Landing States | Block 1 |
| G2 | Autocomplete Suggestions | Block 2 |
| G3 | Header Search Submission (q-only, context drop) | Block 3 |
| G4 | FTS Results, Relevance Ordering & Side Effects | Block 3, Block 4 |
| G5 | Category Browsing & Context Scoping | Block 4 |
| G6 | Filter Application | Block 5 |
| G7 | Sorting & Price Ordering | Block 6 |
| G8 | Filter Chips & Removal | Block 5 |
| G9 | Clear All Filters | Block 5 |
| G10 | URL State, Pagination & Back/Forward | Block 7 |
| G11 | Preferred City & Did-You-Mean | Block 8 |
| G12 | Language Switching & Per-Language FTS | Block 9 |
| G13 | Search History | Block 10 |
| G14 | Saved Search Modal & Alerts | Block 11 |

---

## Block 1: Entry Points & Landing States

**Scope:** Initial rendering and default state of the page when reached via any entry point (direct navigation to homepage, category link, city link, or ad detail link). Verifies the header structure, empty-search state, and that the search bar is present on every surface.

**Covered journeys:** G1 — S1.1 (homepage landing), S2.1–S2.2 (category entry + dropdown), S4.1 (category page landing), S5.1 (category + filters landing), S6.1 (ad detail landing).

**Key variations:**
- Homepage `/` — renders all published ads (24-card grid, newest-first), header with city badge, All-Categories dropdown, empty search bar.
- Category entry `/category/<slug>/` — breadcrumb trail, constrained filter option sets via `CategoryLookupResolver`.
- City entry `/city/<slug>/` — city pre-selected, results scoped to that city.
- Ad detail `/<ad_id>/` — header search bar present, "Back to listings" link present, Telegram contact deep-link rendered.
- Shared header — search form contains only `name="q"` + `csrfmiddlewaretoken` (no hidden category/city/filter inputs).

**Dependencies:** None.

---

## Block 2: Autocomplete Suggestions

**Scope:** Real-time suggestion dropdown triggered on query input. Covers the autocomplete API endpoint, response shape, source merging/dedup, click outcomes, and keyboard navigation.

**Covered journeys:** G2 — S1.2 (focus), S1.3 (type → refine), S2.1 (category dropdown entry), S4.3 (click category suggestion).

**Key variations:**
- **Django client tests:** `GET /api/search/autocomplete?q=<text>` returns `{"query", "suggestions[]}`; each suggestion has `text`, `source`, `type`. Empty/short query returns empty suggestions. Sanitization: quotes/backslashes stripped, 2–100 char range. Rate limit: 30 req/min/IP → 31st returns 429.
- **Django client tests:** Sources merged and deduped by `text`, capped at 10: `user_history` (auth DB / anon session), `category` + `city` (prefix `istartswith`, localized via `get_name(locale)`), `popular_search` (`hit_count >= 10`).
- **Playwright sub-tests (Validator rec.):**
  - Click outcomes: city suggestion → POST `/api/preferred-city/` + full-page nav to `/city/<slug>/`; category suggestion → full-page nav to `/category/<slug>/`; text suggestion → populate input + form submit to `/search/?q=<t>`; "Show all results" link → `/search/?q=<t>`.
  - Keyboard navigation: `ArrowDown`/`ArrowUp` cycles suggestions, `Enter` selects the highlighted suggestion, `Escape` dismisses the dropdown.

**Dependencies:** Block 1 (landing state is the baseline for autocomplete context).

---

## Block 3: Search Submission & FTS Results

**Scope:** Full-page search submission via the header form, PostgreSQL FTS query execution, relevance-ordered result rendering, and side effects (search/popular history recording, analytics). Also covers the context-drop behavior.

**Covered journeys:** G3, G4 — S1.4 (homepage → query → results), S2.4 (category → query → context dropped), S3.1–S3.2 (query → filters), S4.2 (category → query), S6.2 (detail → query).

**Key variations:**
- **Context-drop test (Validator rec.):** Header form submit from `/category/<slug>/` yields `/search/?q=<t>` with **no** `category` param — category/city/filters are dropped because the header form only sends `q`.
- FTS relevance ordering: results ranked by `ts_rank`, ordered `-rank, -published_at, -id` (`search.py:180-182`).
- Single-word fuzzy category match: one-word query matching a category slug/name/difflib(0.8) constrains results to that category subtree (`search.py:167-174`).
- Multi-word query: no category constraint, site-wide FTS only.
- Side effects after non-empty `q`: `SEARCH_PERFORMED` analytics event, `increment_popular_search`, `record_search_history` (auth DB / anon session).
- **FTS-hidden-sort gap test (Validator rec.):** `/search/?q=term&sort=price_asc` — the `sort` param is **ignored** when `q` is present; results are relevance-ordered, not price-ordered.

**Dependencies:** Block 2 (autocomplete provides query terms); Block 4 (category browsing shares FTS result rendering).

> **Shared ownership note:** The "context drop" behavior (header search drops category/city) is described by both G3 and G5. It is implemented/tested under Block 3 but verified for consistency under Block 4.

---

## Block 4: Category Browsing & Context Scoping

**Scope:** Search within a category context, ensuring the category filter is applied as a scope, the URL path carries the category, breadcrumbs render correctly, and context-scoping logic (preserve on path, drop on header submit) behaves as implemented.

**Covered journeys:** G5 — S2.2 (category selection), S4.1 (category page landing), S5.1 (category filter landing), S2.4 / S4.2 / S6.2 (context drop on header submit), S4.3b (no category control on `/search/`).

**Key variations:**
- Category entry via `/category/<slug>/` path — category preserved in URL path, descendant subtree filter applied.
- Category-constrained filter option sets: purposes/conditions/features resolved per category via `CategoryLookupResolver` ancestor-walk.
- Breadcrumb rendering reflects the active category ancestor chain.
- **Context-drop verification (shared with Block 3):** Header search from a category page produces `/search/?q=<t>` with no category context; the only way to re-scope on `/search/` is via autocomplete category suggestion or single-word fuzzy match.
- Gap coverage: No category control exists in `filter_form.html` on `/search/?q=` — category scoping is only possible via URL path or autocomplete.

**Dependencies:** Block 3 (FTS results rendering); Block 5 (filter controls).

---

## Block 5: Filter Controls, Chips & Management

**Scope:** Filter application (purpose, condition, features, price range), active filter chip display, per-chip removal, and "Clear all filters" — all via HTMX partial updates. (Renamed from "Filtering Controls & Management" per Validator recommendation.)

**Covered journeys:** G6, G8, G9 — S2.3 (apply filters), S3.2 (apply filters with query), S3.3 (remove chip), S3.4 (clear all), S5.2 (apply filters with sort), S5.3 (remove chip), S5.3b (clear all on category page), S2.3 / S5.1 (constrained option sets).

**Key variations:**
- **Behavioral Clear-All test (Validator rec.):** "Clear all filters" URL retains `q` + `sort` only and drops `listing_purpose`, `condition`, `features`, `min_price`, `max_price`, `city`, `category`. Page resets to 1.
- **Chip-removal URL-content tests (Validator rec.):** Removing one chip (e.g., a feature) retains all other filters (`listing_purpose`, `city`, other features) in both URL and result set.
- Purpose single-select dropdown: category-constrained options or full lookup set when no category active.
- Features multi-select checkboxes with AND semantics (all selected features required; `request.GET.getlist` + `.distinct()`).
- EUR-normalized price range: `min_price`/`max_price` filter on `price_normalized_eur`; non-integer values silently ignored.
- Filter application via HTMX: `hx-get` to `request.path`, target `#ad-list`, `hx-push-url="true"`, form re-renders to prevent stale state.
- **Filter+sort combination test (Validator rec.):** `listing_purpose=sell&features=delivery&sort=price_asc` — all filters and sort applied coherently together.

**Dependencies:** Block 3 (results rendering); Block 4 (category scoping as a filter); Block 7 (HTMX push-url).

---

## Block 6: Sorting & Price Ordering

**Scope:** Sort dropdown behavior, price-based ordering with NULLS LAST, and the interaction between sort and FTS (the hidden-sort gap).

**Covered journeys:** G7 — S1.1 (default `date_desc` on homepage), S5.2 (`sort=price_desc` on category page).

**Key variations:**
- **FTS-hidden-sort gap test (Validator rec.):** On `/search/?q=<term>`, the sort dropdown is hidden (`{% if not query %}`) and `sort=` is ignored — results always ordered by `-rank, -published_at, -id`. Verify `?q=term&sort=price_asc` does not produce price ordering.
- Non-FTS sort: `?sort=date_desc` (default), `date_asc`, `price_asc`, `price_desc` honored on `/`, `/category/<slug>/`, `/city/<slug>/`.
- Price sort: `price_normalized_eur` ASC/DESC with `NULLS LAST` (ads with no price shown last).
- Sort persistence: every pagination link and chip-removal link re-emits the current `sort` so it survives paging and filter changes.
- Invalid `sort` value: falls through to default `date_desc` ordering.

**Dependencies:** Block 3 (FTS results); Block 5 (filters); Block 7 (URL state).

---

## Block 7: URL State, Pagination & Navigation

**Scope:** URL parameter encoding and parsing, pagination behavior, and browser Back/Forward navigation restoration after HTMX push-url updates.

**Covered journeys:** G10 — S1.5 (pagination after search), S3.2 / S5.2 (page reset on filter change), S5.3b (page 1 on clear-all), S6.3 (Back restores detail page).

**Key variations:**
- **Playwright Back/Forward sub-tests (Validator rec.):**
  - Navigate page 1 → page 2 → Back → page 1 state restored.
  - Navigate page 1 → apply filter → go to page 2 → Back → filtered page 1 restored.
  - HTMX `hx-push-url` correctly updates browser history entries (no stale snapshots, no duplicate entries).
- URL params: `q`, `sort`, `page`, `min_price`, `max_price`, `listing_purpose`, `condition`, repeated `features=<slug>` all correctly encoded and parseable.
- HTMX contract: non-HTMX request renders full `ads/list.html`; `HX-Request: true` renders fragment `ads/partials/ad_list.html` only.
- Pagination: 24 ads per page; `page` param validation (invalid → page 1, out-of-range → last page); all links carry the full active param set.
- Deep-linking: visiting a paginated, filtered URL directly renders the correct results.

**Dependencies:** Block 3 (results), Block 5 (filters), Block 6 (sort).

---

## Block 8: Preferred City & Did-You-Mean

**Scope:** City preference persistence (cookie/DB via middleware), automatic city-filtering on search, and the "Did-You-Mean" correction suggestion when an invalid city is supplied.

**Covered journeys:** G11 — S2.2 (preferred city on category page), S2.4 / S4.2 / S6.2 (preferred city re-applied on search), S5.1 (preferred city default on listings).

**Key variations:**
- Preferred city set via `POST /api/preferred-city/` (sets cookie for guests with consent; sets `User.preferred_city` FK for auth users).
- Preferred city override: explicit `?city=<slug>` or `/city/<slug>/` path takes precedence over stored preference.
- Preferred city clear: `POST /api/preferred-city/ action=clear` deletes cookie + nulls DB for auth; search reverts to country-wide.
- Did-you-mean on listings: invalid `?city=` or `/city/<slug>/` path triggers `difflib` suggestion (cutoff 0.6) with a banner linking to the corrected `ads:listings_city` URL.
- Did-you-mean on search (gap): invalid `?city=` on `/search/` echoes the slug only (no fuzzy match) — flagged as a known implementation gap.

**Dependencies:** Block 3 (results), Block 7 (URL state).

---

## Block 9: Language Switching & Per-Language FTS

**Scope:** Language toggle behavior, per-language search vector selection, and i18n completeness verification.

**Covered journeys:** G12 — S1.4, S2.4, S3.1, S4.2, S6.2 (all FTS scenarios when language is switched).

**Key variations:**
- **Per-language search-view test (Validator rec.):** `/?lang=bs&q=<term>` → results sourced from `search_vector_bs` (Bosnian, `simple` config), not the default Russian vector. `/?lang=en&q=<term>` → `search_vector_en` (`english` config).
- Language priority: `?lang=X` query param → `lang_pref` cookie → `Accept-Language` → default `ru`.
- `?lang=` writes `lang_pref` cookie (1-year, `SameSite=Lax`); session `django_language` for auth users.
- Language toggle preserves current `q` and filter params; only `lang` changes.
- i18n completeness: `test_i18n_completeness.py` passes after any new translatable strings added in search templates or Python code (project rule #16). Run `makemessages` + `compilemessages` before commit.

**Dependencies:** Block 3 (FTS results); Block 7 (URL state).

---

## Block 10: Search History

**Scope:** Search query persistence in user history, history retrieval/display, and history-based autocomplete suggestions.

**Covered journeys:** G13 — S1.4, S3.1, S4.2, S6.2 (recording after FTS), S1.2–S1.3, S3 (display in autocomplete).

**Key variations:**
- Successful search with `q=<term>` recorded: auth → `SearchHistory` DB row (deduped by `query_normalized`, capped at 50); anon → `session['search_history']` (deduped, capped at 50).
- Anonymous history lives in the Django session table (keyed by `sessionid` cookie) — not a standalone cookie — explaining the "cookie level" perception in Problem_01.md bug #1.
- Search history page (`/cabinet/search-history/`) lists prior queries with timestamps, most recent first (auth only).
- Clicking a history entry re-runs the search → `/search/?q=<query>`.
- History entries appear in autocomplete dropdown as `user_history` suggestions (limit 5).
- Clear history: `POST /cabinet/search-history/clear/` wipes all rows for the user (auth only).
- Popular-search gate: `hit_count >= 10` required for popular suggestions — on low-traffic instances the popular section is empty by design (related to Problem_01.md bug #1).

**Dependencies:** Block 3 (search submission triggers history save); Block 2 (autocomplete displays history).

---

## Block 11: Saved Search Modal & Alerts

**Scope:** Saved search creation via modal dialog, alert persistence, and notification delivery mechanism.

**Covered journeys:** G14 — S1.4 (modal available on `/search/`), S3.2, S5.2 (filter context captured by modal).

**Key variations:**
- "Save search" modal visible on `/search/` when `request.user.is_authenticated and cities` in context (`list.html:23-32`).
- Modal pre-fills current query + filters (`query`, `city_id`, `category_id`, `min_price`, `max_price`, `language=request.LANGUAGE_CODE`).
- `POST /save-search/` creates a `SavedSearch` row with `is_active=True`; unauth → redirect to login.
- Saved searches listed at `/cabinet/saved-searches/` with toggle/edit/delete actions.
- Alert delivery: matching new ads trigger notification (bot message or email per user preference) — unit-tested via Django client (no Playwright needed for core matching logic).
- Alert frequency respected: daily/weekly cadence per saved search; idempotent via notification dedup.

**Dependencies:** Block 3 (search context), Block 5 (filters), Block 10 (history as related persistence concept).

---

## Open Product Decisions (affect test scope)

These are documented in the research docs but require a product call before final test assertions can be written. They are **noted here** so the test engineer knows which assertions are "current behavior" vs. "pending decision":

1. **Sort on FTS results** — Currently hidden/ignored (`filter_form.html:103`, `search.py:178-182`). Spec implies it should be available. Tests for Block 6 assert the **current** behavior (sort ignored when `q` present); update if product decides otherwise.
2. **Clear-X button** — Currently a native browser clear-X that does nothing (Bug #2). Tests do not yet cover a wired clear control; revisit after fix.
3. **Header-search context preservation** — Currently drops category/city/filters (documented gap). Tests for Block 3 assert the **current** drop behavior; update if product decides to preserve context.
4. **Autocomplete popular gate** — `min_hit_count=10` makes popular empty on low-traffic instances (Bug #1). Tests for Block 2 assert the gate rule as-is.
