---
id: 23_preferred-city-reset
domain: implementation-plan
source_spec: .ai/problems/23_preferred-city-reset_spec.md
spec_status: Approved-for-implementation-planning
priority: High
status: DONE
date: 2026-08-20
completed: 2026-08-20
---

# Plan 23 — Preferred-City: Reset to "Whole Country" + `?city=` Consistency

Transformation of **Spec_23** (`.ai/problems/23_preferred-city-reset_spec.md`) into a
dependency-aware implementation DAG. This plan extends the **already-shipped** Spec_018
hybrid-persistence model (Plan 17, DONE) — the FK, `PreferredCityMiddleware`, the write
endpoint, `search()`/`listings()` read-back, the header dropdown, the context processor,
and the login sync are all in production. The only gaps are the **missing reset surface**
and the **`listings()` `?city=` filter bug** (the `elif` branch performs did-you-mean
only and never filters), plus their tests.

> Spec_23's conceptual tasks T1–T7 are reorganized below into implementation-sequenced,
> parallelizable tasks. Mapping: Spec_23 **T1→T-01, T2→T-02, T3→T-03, T4→T-04, T5→T-05,
> T6→T-06, T7→T-07**. T-04 and T-06 must land alongside T-03 (they lock in the corrected
> behaviour); T-02 and T-05 must land alongside T-01 (the UI and regression for the clear
> action). Per D-4, **T-01 + T-02 + T-03 ship in one changeset**.

## 1. Statement of scope

Implement the two coupled deliverables of Spec_23:

1. **Reset surface** — a discoverable way to clear the preferred city from **both**
   persistence layers (cookie + `User.preferred_city = NULL`), exposed in the existing
   header dropdown as a head item labelled `"Вся страна"`, invoking clear via
   `POST /api/preferred-city/` (Decision D-2: empty-slug / `action=clear`, not DELETE).
2. **`?city=` consistency** — on `/`, `?city=<valid>` becomes a **real filter** (mirroring
   `search()`), and only an *invalid* slug produces the did-you-mean banner; this removes
   the page-1/page-2 divergence.

In scope: `apps/search/views/preferred_city.py` (`set_preferred_city`),
`apps/ads/views/listings.py` (`listings`), `templates/components/header_catalog.html`,
and the four test files called out below.

Out of scope (untouched, per Spec_23 §4): the Spec_018 priority order, the valid-slug
cookie attributes, `SavedSearch.city` (independent FK), the future user-cabinet
profile page (D-13 reverse-sync is a noted follow-up), and — critically — **no schema,
migration, shared-config, or startup change** (C-2).

## 2. Current-state vs. gaps (verified)

| Concern | State | Evidence |
|---|---|---|
| `User.preferred_city` FK | Done | `users/models.py`, migration `0003_user_preferred_city` |
| `PreferredCityMiddleware` + constants | Done | `core/middleware/preferred_city.py` |
| Write endpoint (valid slug) | Done | `search/views/preferred_city.py` `set_preferred_city` |
| `set_preferred_city` **rejects empty slug with 400** | **Gap (T-01)** | `preferred_city.py` — empty/missing slug → `400 invalid_city`; cannot clear today |
| `search()` `?city=` filter | Done | `search.py` — explicit > preferred > None |
| `listings()` `?city=` = did-you-mean only | **Gap (T-03)** | `listings.py` `elif request.GET.get("city"):` sets `suggested_city` but never filters |
| `listings()` preferred-city fallback | Done | `listings.py` `else:` branch |
| Header dropdown + badge | Done | `header_catalog.html`, `context_processors.py:header_context` |
| Dropdown has **no** "whole country" item | **Gap (T-02)** | `header_catalog.html` `{% for city in cities %}` has no static head entry |
| Clear click handler | **Gap (T-02)** | `header_catalog.html` `[data-preferred-city-panel]` handler only matches `[data-city-option]` |
| Login sync cookie→DB | Done | `users/views/consent.py` `_reconcile_preferred_city_on_login` |
| Lock-in test asserts old did-you-mean behaviour | **Gap (T-04)** | `search/tests/test_preferred_city_readback.py` `test_explicit_query_param_prevents_preferred_default` |
| Reset regression coverage | **Gap (T-05)** | none |
| Pagination-divergence coverage | **Gap (T-06)** | none |
| AC-7 / AC-10 test gaps | **Gap (T-07)** | `users/tests/test_logout.py`, `search/tests/` |

## 3. Planning decisions (resolved here, not new requirements)

- **D-P1 — Clear-signal contract.** The clear intent is signaled by **`action=clear`** in the
  POST body, OR a *present-but-empty* `slug` (`"slug" in request.POST` and
  `request.POST.get("slug", "").strip() == ""`). A **missing** `slug` key (the
  `POST {}` case covered by the existing `test_post_with_missing_slug_returns_400`) is
  **not** a clear signal and stays `400 invalid_city`. This preserves every existing test
  (missing→400, unknown→400, valid→set) while adding clear. The dropdown clear button
  posts `FormData` with `action=clear` (slug omitted) for robustness. *Grounds: Spec_018
  §5 / Spec_23 D-2; the existing 400-contract tests.*
- **D-P2 — `delete_cookie` path parity.** `T-01` calls `response.delete_cookie(
  PREFERRED_CITY_COOKIE_NAME)` using the same constant the writer sets (default `path="/"`),
  matching the middleware's own stale-cookie deletion pattern at
  `core/middleware/preferred_city.py` `process_response`. R-3 mitigation is verified in T-05.
- **D-P3 — Reset label = badge label.** The `"Вся страна"` literal is the project's existing
  i18n pattern for the "no preference" badge (it is a hardcoded literal in
  `context_processors.py:header_context`, not a `gettext` msgid — the `.po` files contain no
  such string). Per A-1, the dropdown head-item reuses this exact literal for
  self-consistency (dropdown is the inverse of the badge). No `.po` change.
- **D-P4 — No research gate.** Every architectural fork is resolved in Spec_23 (D-1–D-4);
  no external libraries, no schema/shared-config/startup change, and
  `HttpResponse.delete_cookie` is standard Django. Researcher-agent invocation is not
  warranted (proportional to this low-scrutiny, well-understood change set).
- **D-P5 — T-05 target is not a new file.** Spec_23 T5 annotates `search/tests/test_preferred_city.py`
  as "(new)", but that file **already exists** with `TestPreferredCityView` + `TestHeaderCityBadge`.
  T-05 **appends** a `TestReset` class (reusing the `city`/`buyer` fixtures) rather than creating it.

## 4. Risk assessment & gates

| Task | Risk trigger | Severity | Gate |
|---|---|---|---|
| **T-01** | Evolves a live public endpoint's input contract (now accepts clear) | Medium-Low | None (contract-preserving: missing/invalid still 400). Verification = T-05 + existing tests green. |
| **T-02** | Shared header template + JS branch on catalog & detail pages | Low-Medium | None (UI only). Verification = header render assertion in T-02 + T-05 badge check. |
| **T-03** | Public view filter behavior change on `/` | Medium | None (documented bug fix, R-2 accepted). Verification = T-04 (rewrite) + T-06 (pagination) + regression. |
| **T-04 / T-06** | Lock in corrected behaviour | Low | None. Must ship with T-03 (T-03 breaks old test until T-04 lands — coupled). |
| **T-05** | New regression coverage for reset flow | Low | None. |
| **T-07** | Adds coverage for unchanged behaviour | Low | None (out of critical path; explicit follow-up). |
| FINAL-VERIFY | Cross-cutting regression + AC walkthrough | — | Dedicated multi-stage verification (verification task, no prod change). |

**Release gate (D-4 / R-1):** `T-01 + T-02 + T-03` are a single atomic release unit. Shipping
`T-03` alone re-opens the "can't reach whole country" defect (R-1); shipping `T-01 + T-02`
alone leaves the page-1/page-2 divergence. A code-review gate confirms all three land in one
changeset; no subset is releasable.

## 5. Execution DAG

```
Level 1  (parallel — disjoint modules)
  ├─ T-01  set_preferred_city: clear support        [apps/search/views/preferred_city.py]
  ├─ T-03  listings() ?city= → real filter          [apps/ads/views/listings.py]
  └─ T-07  AC-7/AC-10 follow-up tests               [apps/users/tests/test_logout.py, apps/search/tests/]

Level 2  (parallel — depend on Level 1; touch disjoint files)
  ├─ T-02  dropdown "Вся страна" head-item + clear handler   depends_on: T-01  [templates/components/header_catalog.html]
  ├─ T-04  rewrite lock-in test (asserts new ?city= filter)   depends_on: T-03  [apps/search/tests/test_preferred_city_readback.py]
  ├─ T-05  reset regression test (clear endpoint + all-cities) depends_on: T-01  [apps/search/tests/test_preferred_city.py]
  └─ T-06  pagination-divergence regression test             depends_on: T-03  [apps/search/tests/test_preferred_city_readback.py]

Level 3  (verification — no production code)
  └─ FINAL-VERIFY  regression + AC walkthrough     depends_on: T-01,T-02,T-03,T-04,T-05,T-06
```

- **T-01 and T-03** share no modules → parallel.
- **T-02** shares the click-handler target with T-01 (POSTs `action=clear`) → depends T-01.
- **T-04 / T-06** assert T-03's new filter semantics → depend T-03 and are released with it.
- **T-05** exercises T-01's clear endpoint end-to-end → depends T-01.
- **T-07** tests already-correct behaviour → independent, low priority.
- **FINAL-VERIFY** is gated on the entire critical path; T-07 is optional here.

---

## Task Specifications

---

### T-01 — Extend `set_preferred_city` to support "clear"

**Priority:** high
**Depends on:** — (Level 1)
**Risk:** Medium-Low (endpoint input-contract extension; backward-compatible)
**Release coupling:** ships with T-02 + T-03 (D-4 release gate).

**Files:**
- `src/backend/apps/search/views/preferred_city.py` — target function `set_preferred_city`

**Semantic anchors:**
- Function `set_preferred_city(request)`. The clear-intent guard is inserted **before** the
  existing `slug = (request.POST.get("slug") or "").strip()` validation line.
- Constants already imported: `PREFERRED_CITY_COOKIE_NAME`, `PREFERRED_CITY_COOKIE_MAX_AGE`
  (from `apps.core.middleware.preferred_city`). `delete_cookie` is the response method;
  the writer already omits `path=` so Django defaults to `path="/"` (matches `delete_cookie`'s default → R-3 satisfied).
- Auth guard reuses the existing `request.user.is_authenticated` check already present in the
  valid-slug branch (no new auth plumbing).

**Changes:**
- At the top of `set_preferred_city`, before the validation guard, add:
  ```python
  # "Clear preferred city" intent (D-2). Accepts either an explicit ``action=clear``
  # or a present-but-empty ``slug`` (POST slug=""). A *missing* slug key is still
  # invalid input -> 400 below (preserves test_post_with_missing_slug_returns_400).
  if request.POST.get("action") == "clear" or (
      "slug" in request.POST and not request.POST.get("slug", "").strip()
  ):
      response = JsonResponse({"ok": True})
      response.delete_cookie(PREFERRED_CITY_COOKIE_NAME)
      if request.user.is_authenticated:
          request.user.preferred_city = None
          request.user.save(update_fields=["preferred_city"])
      logger.info("Cleared preferred_city for user=%s", getattr(request.user, "id", None))
      return response
  ```
- No change to the existing valid-slug path (cookie `set_cookie` + DB write) or the 400
  branch for missing/invalid slugs.

**Acceptance criteria:**
- `POST /api/preferred-city/ {action: clear}` (anonymous) → `200 {"ok": true}`,
  `response.cookies["preferred_city"].value == ""` (cookie scheduled for deletion, mirroring
  the middleware stale test pattern).
- Same call (authenticated, `User.preferred_city` previously set) → `200`, and after
  `refresh_from_db()` `user.preferred_city_id is None`.
- `POST /api/preferred-city/ {}` (missing slug, no action) → still `400 invalid_city`
  (existing `test_post_with_missing_slug_returns_400` preserved).
- `POST /api/preferred-city/ {slug: nowhere}` → still `400` (existing test preserved).
- `GET /api/preferred-city/` → still `405` (unchanged).
- `ruff check` + `basedpyright` pass on `apps/search/views/preferred_city.py`.

---

### T-02 — Add "Вся страна" head-item + clear click handler

**Priority:** high
**Depends on:** T-01 (Level 2)
**Risk:** Low-Medium (shared header template + vanilla JS on list & detail pages)
**Release coupling:** ships with T-01 + T-03 (D-4 release gate).

**Files:**
- `src/backend/templates/components/header_catalog.html`

`src/backend/apps/core/context_processors.py` — **no change** (`header_context` already
exposes `preferred_city_display` and `cities`; the badge label `"Вся страна"` is already
served when the preference is unset, per D-P3).

**Semantic anchors:**
- The preferred-city dropdown panel `[data-preferred-city-panel]` and its inner
  `<ul class="py-1 ...">` that currently loops `{% for city in cities %}`
  (header_catalog.html, preferred-city panel block). Insert ONE static head `<li>`
  **before** the `{% for %}` loop.
- The `cityPanel.addEventListener('click', ...)` handler in the IIFE's "Preferred-city
  dropdown" section (the block whose selector is `[data-city-option]`). Add a branch
  for `[data-city-clear]`.
- The `cityGetCsrf()` helper already in scope for the click handler.

**Changes:**
- Insert a head item (label is the `"Вся страна"` literal to match the badge — D-P3):
  ```html
  <li data-city-clear>
      <button type="button" data-city-clear
              class="block w-full text-left px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 min-h-[44px]">
          Вся страна
      </button>
  </li>
  ```
  placed as the **first** `<li>` inside the panel `<ul>`, immediately before
  `{% for city in cities %}`.
- In the `cityPanel` click handler, add a `[data-city-clear]` branch (before the
  `[data-city-option]` handling) that POSTs `action=clear` to the existing
  `{% url 'search:preferred_city' %}` endpoint and then navigates to `/`:
  ```js
  var clearItem = e.target.closest('[data-city-clear]');
  if (clearItem) {
      e.preventDefault();
      var fd = new FormData();
      fd.append('action', 'clear');
      fetch('{% url "search:preferred_city" %}', {
          method: 'POST', body: fd, headers: { 'X-CSRFToken': cityGetCsrf() }
      });
      window.location.href = '/';
      return;
  }
  ```

**Acceptance criteria:**
- Header renders a first dropdown item `Вся страна` with `data-city-clear`.
- Clicking it POSTs `action=clear` to `/api/preferred-city/` and navigates to `/`.
- When no preference is set, the badge reads `Вся страна` (already true via
  `header_context`; assert present — AC-8).
- No existing dropdown/toggle/escape/click-outside behaviour regressed.
- No production-logic regression (no server change in T-02 itself).

---

### T-03 — Unify `listings()` `?city=` on a real filter

**Priority:** high
**Depends on:** — (Level 1)
**Risk:** Medium (public browse behavior change on `/`)
**Release coupling:** ships with T-01 + T-02 (D-4); T-04 + T-06 are its paired test rewrites and must land with it.

**Files:**
- `src/backend/apps/ads/views/listings.py` — function `listings`

**Semantic anchors:**
- The city-filter block in `listings()` whose first branch is `if city_slug:` and whose
  second branch is `elif request.GET.get("city"):`. **Only the `elif` branch changes.**
  The `if city_slug:` (URL path) branch and the `else:` (preferred-city default) branch are
  **unchanged**.
- The leading comment above that block currently describes `?city=` as "did-you-mean only"
  and must be updated to reflect unified filter semantics.
- Helper `_suggest_city(slug)` (lower block of `listings.py`) is reused unchanged for the
  did-you-mean fallback on invalid slug.

**Changes:**
- Replace the body of the `elif request.GET.get("city"):` branch so a **valid** slug filters
  (mirroring `search.py`'s `current_city` resolution) and an **invalid** slug falls through to
  did-you-mean only:
  ```python
  elif request.GET.get("city"):
      effective_city = request.GET["city"]
      try:
          city = City.objects.get(slug=effective_city)
          ads = ads.filter(city_id=city.id)
      except City.DoesNotExist:
          # Invalid slug: did-you-mean banner, no filter (F-6).
          suggested_city = _suggest_city(effective_city)
  ```
- Update the block comment to state: explicit `?city=` is a real filter (F-5); only an
  invalid slug yields a suggestion (F-6).
- `current_city` context already reads `effective_city` (line ~425), so it now reflects the
  real filter — no context change needed.

**Acceptance criteria:**
- `/?city=budva` returns **only** Budva ads, `current_city == "budva"`,
  `suggested_city is None` (F-5; AC-3).
- `/?city=nonexistent` → no filter (all ads) + `suggested_city` set to the did-you-mean
  suggestion (F-6; AC-3).
- `/city/<slug>/`, the preferred-city default, stale-cookie fallthrough, and pagination
  behaviour are unchanged in shape (verified by T-06).
- Existing `test_default_fallback_to_preferred_city`, `test_path_city_overrides_preferred`,
  and the DB-wins/cookie/stale tests in `test_preferred_city_readback.py` remain green
  except the one rewritten by T-04.

---

### T-04 — Rewrite the lock-in test for unified `?city=` semantics

**Priority:** high
**Depends on:** T-03 (Level 2)
**Risk:** Low
**Release coupling:** lands with T-03 (the old test asserts the bug being removed).

**Files:**
- `src/backend/apps/search/tests/test_preferred_city_readback.py` — target class
  `TestListingsPreferredCityReadback`

**Semantic anchors:**
- Rename/replace the method `test_explicit_query_param_prevents_preferred_default`
  (the `TestListingsPreferredCityReadback` method that currently asserts `?city=budva`
  returns both ads + `suggested_city == "budva"` + `current_city is None`).
- Reuse fixtures `seller`, `category`, `podgorica`, `budva`, `podgorica_ad`, `budva_ad`
  and helpers `_result_ids` already in the file.

**Changes:**
- Replace the method with `test_explicit_query_param_filters_to_city`:
  - `GET /?city=budva` → `_result_ids(response) == [budva_ad.id]`
  - `response.context["current_city"] == "budva"`
  - `response.context["suggested_city"] is None`

**Acceptance criteria:**
- The old assertion (both ads / did-you-mean-only) is removed; the new assertions match
  `search()` semantics (F-5).
- Module's other tests still green.

---

### T-05 — Add reset regression test (append `TestReset` to existing file)

**Priority:** high
**Depends on:** T-01 (Level 2)
**Risk:** Low
**Note:** Spec_23 annotates `search/tests/test_preferred_city.py` as "(new)", but the file
**already exists** (D-P5). Append a `TestReset` class.

**Files:**
- `src/backend/apps/search/tests/test_preferred_city.py`

**Semantic anchors:**
- Append class `TestReset` to the existing module. Reuse the existing `city` (podgorica)
  and `buyer` fixtures; add a `budva` `City` fixture plus a `_published_ad` helper and an
  ad in each city (mirror the fixture/helper pattern already in
  `test_preferred_city_readback.py` so helpers are consistent across the two files).

**Changes:**
- `test_clear_deletes_cookie_and_returns_all_cities_anonymous`:
  POST `{"action": "clear"}` → `200`, `response.cookies["preferred_city"].value == ""`.
  Then a fresh `GET /` returns both-city ads and the badge renders `Вся страна`.
- `test_clear_nulls_fk_and_returns_all_cities_authenticated`:
  `buyer.preferred_city = podgorica`; POST `{"action": "clear"}` → `200`;
  `buyer.refresh_from_db()` → `preferred_city_id is None`. Fresh `GET /` → all-cities.
  (Badge `Вся страна` assertion optional here.)
- `test_clear_with_empty_slug_equivalent_to_action_clear` (optional, documents D-P1):
  POST `{"slug": ""}` → same clear effect.

**Acceptance criteria:**
- Both anonymous (cookie deleted) and authenticated (FK NULL) clear paths asserted (F-1,
  F-4, AC-5*, AC-NEW-1).
- After clear, `GET /` returns all-cities ads (no city filter) and the badge label is
  `Вся страна` (AC-8).
- `delete_cookie` is observable in the test response (R-3 verified here).

---

### T-06 — Add pagination-divergence regression test

**Priority:** high
**Depends on:** T-03 (Level 2)
**Risk:** Low
**Release coupling:** lands with T-03.

**Files:**
- `src/backend/apps/search/tests/test_preferred_city_readback.py` — target class
  `TestListingsPreferredCityReadback` (the file already owns `listings()` `?city=` assertions).

**Semantic anchors:**
- Append `test_pagination_with_explicit_city_matches_page_one` to
  `TestListingsPreferredCityReadback`. Reuse `_result_ids` and the city/ad fixtures.

**Changes:**
- With `preferred_city` cookie = `budva`, assert:
  `GET /?page=2&city=budva` → results are Budva-filtered (same filter as page 1), and
  `current_city == "budva"` (i.e. page 2 does **not** diverge to all-ads) (AC-NEW-2, T-06).
- Also assert `GET /?page=2` (no `?city=`) falls back to the preferred city (page 2 stays
  Budva-filtered) — guards the default path across pages.

**Acceptance criteria:**
- Page 2 with `?city=<preferred>` returns the same city-filtered set, not all ads
  (divergence eliminated).

---

### T-07 — Follow-up coverage for unchanged AC-7 / AC-10 (low priority)

**Priority:** low
**Depends on:** — (independent; tests existing correct behaviour)
**Risk:** Low
**Status:** explicit follow-up, **not** on the FINAL-VERIFY critical path.

**Files:**
- `src/backend/apps/users/tests/test_logout.py` — assert logout does **not** delete the
  `preferred_city` cookie (cookie retained as the anonymous fallback; AC-7).
- `src/backend/apps/search/tests/` (new small test or append) — assert
  `User.preferred_city` and `SavedSearch.city` are independent FKs that may hold
  different cities with no shared constraint (AC-10). `SavedSearch.city` is at
  `search/models.py` `class SavedSearch`; `User.preferred_city` is the unrelated FK —
  confirm assignment of one does not affect the other.

**Acceptance criteria:**
- Logout response does not delete `preferred_city` (cookie retained). AC-7.
- Setting `User.preferred_city` does not touch `SavedSearch.city` and vice-versa; both
  persist independently. AC-10.

---

### FINAL-VERIFY — Regression + acceptance-criteria walkthrough

**Priority:** high
**Depends on:** T-01, T-02, T-03, T-04, T-05, T-06
**Risk:** — (verification only)

**Purpose:** Dedicated multi-stage verification for a cross-cutting browse-surface +
endpoint + UI change set.

**Verification steps** (test DB up per `.ai/context/commands.md`; run via the `test`
Compose service — never `uv run pytest` locally):

1. **Migrations / schema guard:** `makemigrations --check` reports no new migrations
   (C-2: no schema change here — the FK was added in Plan 17). Exactly zero deltas.
2. **Unit (no DB):** `test_preferred_city_middleware.py` — DB-wins / cookie-default /
   stale-clearance / ordering-guard unchanged and green.
3. **Endpoint (T-01 + T-05):** `test_preferred_city.py` — existing cookie/DB-write
   tests still pass + new `TestReset` (anonymous cookie delete, authenticated FK NULL,
   all-cities after reset, badge `Вся страна`).
4. **View filter (T-03 + T-04 + T-06):** `test_preferred_city_readback.py` — rewritten
   `?city=` filter test + pagination-divergence test + all prior readback tests green.
5. **Header (T-02):** `TestHeaderCityBadge` asserts the `Вся страна` head-item is present
   and the badge renders the country-wide label when unset.
6. **AC walkthrough:**
   - AC-1 DB-wins over cookie (unchanged) — readback tests.
   - AC-2 guest cookie all-cities→default still works.
   - AC-3 (extended) `/?city=<valid>` filters on `/` **and** `/search/`; `/?city=<invalid>`
     → did-you-mean, no filter (T-03/T-04).
   - AC-4 stale cookie still cleared by middleware (unchanged).
   - AC-5\* POST clear deletes cookie + NULLs FK for auth users (T-01/T-05).
   - AC-6 login migrates guest cookie→DB (unchanged) — login tests.
   - AC-7 logout retains cookie (T-07, optional).
   - AC-8 badge renders `Вся страна` when cleared (T-02/T-05).
   - AC-9 no `UserProfile` model introduced (unchanged).
   - AC-10 `preferred_city` ≠ `SavedSearch.city` independence (T-07, optional).
   - AC-NEW-1 after reset `GET /` returns all-cities (T-05).
   - AC-NEW-2 `?page=2&city=<preferred>` == page-1 city filter (T-06).
7. **Full regression:** run `apps.search`, `apps.ads`, `apps.users`, `apps.core` test suites
   to confirm no collateral from the view/endpoint/template changes.
8. **Static checks:** `ruff check` + `basedpyright` across the touched trees
   (`apps/search/views/preferred_city.py`, `apps/ads/views/listings.py`,
   `apps/search/tests/`, `apps/core/tests/`).
9. **Out-of-scope guard:** no `apps.telegram_bot` change, no `UserProfile`, no migration
   deltas, no `SavedSearch.city` change.

**Exit criteria:** all tests green, AC-1…AC-10 + AC-NEW-1/2 satisfied, static checks clean,
no schema/shared-config/startup drift.

---

## Notes for implementors

- Semantic anchors only — never line numbers (the spec's `file:line` index in
  `.ai/problems/23_preferred-city-reset_spec.md` appendix is for locating, not for the
  edit itself).
- All comments/log/docstrings/errors in English (project rule 1).
- No `StrEnum` change required here (D-P1 clear-signal is a request-body field, not a
  domain enum); the `PREFERRED_CITY_COOKIE_NAME` stays a module constant (C-3).
- `delete_cookie` uses the shared constant and default `path="/"` — matches the writer's
  default path (R-3). Verified in T-05.
- After `T-01` clears, `request.preferred_city` resolves to `None` (cookie gone,
  FK NULL); `header_context` then serves `"Вся страна"` server-side — the badge updates
  on the next full page load without any client cookie read.
- D-4 coupling is a **release** gate, not a build/code dependency: T-01, T-02, T-03 may be
  authored in parallel (disjoint files) but **must commit together**. Review gate checks
  the coupling; do not ship `T-03` without `T-02`.
- T-07 is intentionally deferred off the critical path; it only closes test gaps for
  behaviour that is already correct (AC-7, AC-10) and may be picked up in a follow-up.
