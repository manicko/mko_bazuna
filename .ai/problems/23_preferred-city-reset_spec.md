# Spec 23 — Preferred City: Reset to "Whole Country" + `?city=` Consistency

> **Status:** Approved for implementation planning  
> **Source request:** `.ai/problems/Decision_023.md`  
> **Spec verified against:** `.ai/problems/18_preferred-city_spec.md` (R-01..R-11, T-01..T-08, AC-1..AC-10)  
> **Research basis:** `.ai/research/23_preferred-city_gap_and_reset_report.md`  
> **Priority:** High — fixes the reported "hard filter / can't reset" defect.

---

## 1. Problem Statement (verified)

Buyers who select a preferred city are **stuck on that one city** and cannot return to a
"whole country" (all-cities) view. Per `Decision_023.md`, the perception is that the city
acts as a hard filter. Research ([report §2](23_preferred-city_gap_and_reset_report.md#2-decision_023-root-cause))
confirms this is **not a logic bug** in the priority resolution — the Spec_018
"preferred = default, not hard constraint" logic executes correctly. The true defect is a
**missing reset surface**: there is no UI control or endpoint that clears the preferred city.

A coupled latent bug reinforces the perception: a **valid** `?city=<slug>` on the root listing
(`/?city=budva`) silently returns **all** ads (treated as "did-you-mean only"), which is
inconsistent with `/search/?city=budva` (real filter) and produces a **page-1 vs page-2
divergence** (report §3).

---

## 2. Background — Current State

Spec_018 (priority: **explicit param > `User.preferred_city` > cookie > all-cities**) is
**implemented and shipped**. Verified with file:line evidence (report §1):

- `User.preferred_city` FK — `users/models.py:73-80`, migration `0003_user_preferred_city.py`.
- `PreferredCityMiddleware` resolves `request.preferred_city` (DB>cookie>None) —
  `core/middleware/preferred_city.py:47-73`, registered `base.py:120` after `AuthenticationMiddleware`.
- Cookie/DBA write: `POST /api/preferred-city/` — `search/views/preferred_city.py:42-64`
  (HttpOnly, 1-yr, SameSite=Lax, Secure in prod, 400 on invalid slug).
- Read-back: `search.py:71-72`, `listings.py:301-327` (else-branch `317-327`).
- Login sync cookie→DB — `users/views/consent.py:208-239`, wired `321-324`.
- Header city button + badge — `templates/components/header_catalog.html:46-71`,
  badge label `"Вся страна"` when unset — `core/context_processors.py:46`.
- **The dropdown contains 15 cities and NO "whole country" entry** (confirmed live DOM,
  `header_catalog.html:61-68` iterates only `{% for city in cities %}`).
- Cookie/DBA write endpoint **rejects empty slug with 400** (`preferred_city.py:42-44`) — it
  cannot clear a preference.

**Conclusion:** the priority logic works; the gap is the absence of a "clear preference"
control/endpoint.

---

## 3. Objectives

1. **Restore "whole country" navigability** — give buyers a discoverable, single-step way to
   clear their preferred city so catalog/search return to all-cities results. (Fixes `Decision_023`.)
2. **Make `?city=<valid>` behave consistently** across `/` (listings) and `/search/` — it must
   always be a real list filter; only an *invalid* slug produces a did-you-mean banner.
3. **Eliminate the pagination divergence** (page 1 shows city-filtered ads, page 2 shows all ads).
4. Ship (1) and (2) **together** — making `?city=<valid>` a strict filter removes the only
   undocumented escape from a stuck city, so the reset affordance is mandatory alongside it
   (report §3.4).

---

## 4. Scope

### In scope
- A persistent reset (clears cookie **and**, for auth users, `User.preferred_city = None`).
- A header UI control for the reset (the dropdown).
- Aligning `listings()` `?city=` handling with `search()`'s filter semantics.
- Updating the test that locks in the old did-you-mean behaviour.

### Out of scope (do NOT touch)
- Changing the Spec_018 priority order (explicit param > DB > cookie > all-cities) — it is correct.
- The cookie/DBA write endpoint's existing *valid-slug* path (HttpOnly/1-yr/SameSite attributes stay).
- `SavedSearch.city` (independent alerting FK, `search/models.py:63`) — unrelated.
- The future user-cabinet profile page (may set `User.preferred_city` directly); D-13 reverse-sync
  is **noted** as a follow-up item, not this spec's deliverable.

---

## 5. Requirements

### Functional

| ID | Requirement | Rationale |
|----|-------------|-----------|
| F-1 | A reset clears **both** persistence layers: `response.delete_cookie(preferred_city)` **and**, for authenticated users, `user.preferred_city = None` (`user.save(update_fields=["preferred_city"])`). | Cookie-only clear leaves a stale DB preference that re-writes the cookie on the next request via middleware; DB-only clear leaves the cookie re-seeding the preference. Both must clear. |
| F-2 | After reset, the buyer is navigated to `/` (root) and sees **all-cities** ads. | The badge reads "Вся страна" when `preferred_city is None`; navigation to `/` is the canonical "whole country" entry. |
| F-3 | The reset is exposed in the **existing** header city dropdown as a head entry labelled "Вся страна" (localized). | The dropdown already lists cities; the badge already uses this exact label — the dropdown becomes the inverse of the badge (self-consistent, learnable). |
| F-4 | Reset is available to **both** anonymous (cookie) and authenticated (cookie+DB) users. | Anonymous must clear the cookie; authenticated must additionally NULL the FK. |
| F-5 | `?city=<valid_slug>` on **both** `/` and `/search/` is a **real list filter** (equivalent to `city/<slug>/`). | `search.py:71-77` already filters; `listings.py` must match. |
| F-6 | `?city=<invalid_or_unknown_slug>` produces a **did-you-mean banner** and **no filter** (all ads), on both `/` and `/search/`. | Preserved existing behaviour for typos/autocorrect. |
| F-7 | `?city=` **never** writes to `User.preferred_city` or the cookie — it is a per-request view-level override. | Explicitly stated in research (report §5.2); confirmed the login sync does not touch `?city=`. |

### Non-functional

| ID | Requirement |
|----|-------------|
| N-1 | Cookie write endpoint remains `POST`-only, returns `400` on invalid input, keeps HttpOnly + 1-yr + SameSite=Lax + Secure(in prod) + path `/`. |
| N-2 | No additional HTTP requests beyond current behaviour on normal flows (reset is one additional endpoint, opt-in). |
| N-3 | Localization: the reset label follows the project's existing i18n pattern for the badge ("Вся страна" ↔ EN "Whole country"). |

---

## 6. Design Decisions (PO)

| # | Decision | Chosen | Rationale |
|---|----------|--------|-----------|
| D-1 | Where to expose the reset control | **Header city dropdown head-item** | The dropdown already exists (`header_catalog.html:46-71`); one static head `<li>` is minimal churn. Most discoverable (always visible on open) — matches OLX/Mobile.bg Pattern 1 (report §4), endorsed for small markets. |
| D-2 | How the clear action is invoked | **POST `slug=""` (action=clear)** to the existing `POST /api/preferred-city/` endpoint, not a `DELETE`. | Reuses the single cookie/DBA write endpoint + `@require_POST` + 405 guard already present. `DELETE` would add a second route/code path for the same persistence surfaces. |
| D-3 | `?city=` semantics on `/?` | **`?city=<valid>` = filter** (unify on `search.py`). | Consistent across the two browse surfaces; removes the page-1/page-2 divergence. Lock-in test must be rewritten (Production Code is King — tests follow corrected business logic). |
| D-4 | Coupled rollout of F-3/F-5 | **Ship together** in one change set. | Shipping them decoupled regenerates the reported bug: once valid `?city=` stops being a (broken) all-ads escape, the reset affordance becomes the only path back to whole country. |

---

## 7. Conceptual Development Tasks (independent, implementation-ready)

> Ordered by dependency; T1 + T2 must ship together (see D-4).

| Task | Description | Touches |
|------|-------------|---------|
| T1 | **Extend cookie/DBA write endpoint to support "clear".** In `search/views/preferred_city.py`, detect the clear intent (e.g. `slug` empty/`"clear"` or `action=clear`), then: `response.delete_cookie(PREFERRED_CITY_COOKIE_NAME)`; if auth → `user.preferred_city = None; user.save(update_fields=["preferred_city"])`; return the same shape as the existing success response; navigate client-side to `/`. | `search/views/preferred_city.py` (`set_preferred_city`) |
| T2 | **Add "Вся страна" head-item to the header dropdown** and a click handler branch for `[data-city-clear]` that POSTs to the clear action, then navigates to `/`. Reuses the dropdown already in `header_catalog.html:46-71` and the badge label at `context_processors.py:46`. | `templates/components/header_catalog.html` |
| T3 | **Unify `listings()` `?city=` on `search()`'s filter semantics.** In `ads/views/listings.py:315-316`, resolve the slug: on `City.DoesNotExist` → did-you-mean banner, else **filter** to that city (mirror `search.py:71-77`). Remove the "valid slug = all ads" branch. | `ads/views/listings.py` |
| T4 | **Fix the lock-in test.** Rewrite `test_explicit_query_param_prevents_preferred_default` (`search/tests/test_preferred_city_readback.py:181-191`) → `test_explicit_query_param_filters_to_city`: assert `/?city=budva` returns only Budva ads, `current_city == "budva"`, `suggested_city is None`. | `search/tests/test_preferred_city_readback.py` |
| T5 | **Add a regression test for the reset.** POST clear → assert the `preferred_city` cookie is deleted (anonymous) **and** `User.preferred_city` is `NULL` (authenticated); then a fresh `GET /` returns all-cities results; badge renders "Вся страна". | `search/tests/test_preferred_city.py` (new) |
| T6 | **Add a pagination-divergence regression test.** With a preferred city set, assert `?page=2&city=<preferred>` on `/` still returns city-filtered ads (not all ads) under the new rule. | `ads/tests/` or `search/tests/` |
| T7 | **Test-gaps follow-ups (low priority).** Assert logout retains the cookie (AC-7); assert `preferred_city` ≠ `SavedSearch.city` independence (AC-10). | `users/tests/test_logout.py`, `search/tests/` |

---

## 8. Constraints

- **C-1** Django 5.2 LTS / Python 3.14 / HTMX 1.9.12 / PostgreSQL 18 — no version changes.
- **C-2** Bot and web share the ORM; migrations run once before both start. No schema change in this spec
  (T1–T7 are views, templates, endpoint logic, and tests only). The `User.preferred_city` FK already exists.
- **C-3** `preferred_city` cookie name is a shared *constant* (not a `StrEnum`) —
  `core/middleware/preferred_city.py:29` — per Spec_018 §7.3. Do not convert.
- **C-4** Two processes (web WSGI sync + bot aiogram) share the DB. Cookie-clear is a **response-level**
  action in the web process; DB-clear is atomic on `User.save(update_fields=["preferred_city"])` — no
  cross-process coordination needed.
- **C-5** Production Code is King: tests serve the corrected business logic; rewrite tests that assert
  the old did-you-mean-for-valid-slug behaviour, do not weaken production code to fit tests.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| R-1 Shipping the `?city=` consistency (T3) **without** the reset affordance (T1+T2) re-creates the "can't reach whole country" bug. | High — direct regression of `Decision_023`. | T1+T2+T3 ship in one change set; code-review gate checks the coupling. |
| R-2 Anonymous users who currently rely on `/?city=<valid>` returning all ads lose that escape. | Medium — behaviour change for existing (undocumented) traffic. | Acceptable: it is a *bug* (page-1/page-2 divergence). Communicate via changelog; reset (T2) is the new escape. |
| R-3 Cookie-clear via `delete_cookie` may leave a stale cookie if `path`/`domain` mismatch on write. | Low | `delete_cookie` uses the same constant name; the writer already sets `path="/"` (Django default). Verify in T5. |
| R-4 Test-gaps AC-7/AC-10 remain. | Low | Captured as T7 follow-up, explicitly out of the critical path of this spec. |

---

## 10. Assumptions

- A-1 The existing "Вся страна" badge label (when preference is unset) is the canonical localization
  for "all cities" and should be reused for the reset control label.
- A-2 The cookie/DBA write endpoint is the correct single place to add the "clear" action
  (the click handler already POSTs there for valid slugs).
- A-3 No future user-cabinet profile page will be added in this change set (D-13 reverse-sync is a
  separate, noted follow-up).

---

## 11. Open Questions (none blocking)

None. All ambiguity resolved by research. D-13 reverse-sync (DB→cookie overwrite on login) is
explicitly deferred (T7/Spec_016 follow-up), not a blocker for this spec.

---

## 12. Acceptance Criteria

> Mapping to Spec_018 AC + new behaviour.

| AC | Pass condition |
|----|----------------|
| AC-1 | DB preference wins over cookie (unchanged) — `search.py:71-72`; `test_preferred_city_readback.py:128-144`. |
| AC-2 | Guest cookie still produces the all-cities→default-filter behaviour (unchanged). |
| AC-3 (extended) | `/?city=<valid_slug>` **filters** on both `/` and `/search/`; `/?city=<invalid>` → did-you-mean banner, no filter. (T3+T4.) |
| AC-4 | Stale cookie still cleared by middleware (unchanged) — `preferred_city.py:64-79`. |
| AC-5* | POST `/api/preferred-city/` with clear intent deletes the cookie + NULLs the FK for auth users; returns success. (T1.) |
| AC-6 | Login still migrates guest cookie→DB (unchanged) — `consent.py:208-239`. |
| AC-7* | Logout retains the cookie (unchanged behaviour, new test required). (T7.) |
| AC-8 | Header badge renders "Вся страна" when preference is cleared (T2+T5). |
| AC-9 | No `UserProfile` model (unchanged — `users/models.py`). |
| AC-10* | `User.preferred_city` stays independent from `SavedSearch.city` (unchanged behaviour, new test required). (T7.) |
| AC-NEW-1 | After reset on `/` with a previously-set preferred city, `GET /` returns all-cities ads. (T5.) |
| AC-NEW-2 | Pagination on `/?page=2&city=<preferred>` returns the **same city filter** as page 1 (no divergence). (T6.) |

`AC-5*`, `AC-7*`, `AC-10*` denote criteria with either new behaviour (AC-5*) or test gaps to close
(AC-7, AC-10 — see T7).

---

## Appendix A — file:line Evidence Index

- Reset surface (current absence): `templates/components/header_catalog.html:46-71` (dropdown, cities only), `:61-68` (no static "all" entry), `:464-474` (click handler, `data-city-option` only).
- Clear-target endpoint: `apps/search/views/preferred_city.py:42-64` (400 on empty slug — cannot clear today).
- Listings `?city=` did-you-mean-only branch: `apps/ads/views/listings.py:315-316`; else-branch preferred read-back `317-327`; `current_city` context `425`.
- Search `?city=` filter: `apps/search/views/search.py:69-79`.
- Lock-in test: `apps/search/tests/test_preferred_city_readback.py:181-191`.
- Pagination links: `templates/ads/partials/ad_list.html:74-101`.
- Cookie/DBA write tests: `apps/search/tests/test_preferred_city.py:48-90`.
- Login sync: `apps/users/views/consent.py:208-239`, `321-324`; tests `apps/users/tests/test_login.py:243-307`.
- Middleware + cookie constants: `apps/core/middleware/preferred_city.py:29-30,47-73,75-79`; registered `config/settings/base.py:119-120`.
- Badge/context: `apps/core/context_processors.py:24-60` (global) + `core/24` in `base.py`.
- City model (slug unique, no "all" route): `apps/locations/models.py:36-39`; `apps/locations/urls.py` (empty).

## Appendix B — Spec Index Cross-refs

- This spec supersedes the "latent inconsistency" noted in `.ai/research/16_preferential-city_readback_report.md` §1.3/§6.7 (now resolved by T3).
- Aligns with `.ai/research/23_preferred-city_gap_and_reset_report.md` §6 recommendations (a) + (b).
