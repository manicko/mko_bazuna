# Research Report — Preferred-City: Implementation Audit, Reset Affordance & `?city=` Consistency

**Research task:** verify implementation-readiness of Spec_018 (`.ai/problems/18_preferred-city_spec.md`) for the Product Analyst's final specification.
**Scope:** Spec_018 R-01..R-11 / T-01..T-08 / AC-1..AC-10, reported issue `Decision_023.md` (city is a hard filter; cannot reset to whole country), the `?city=` read-back inconsistency, cookie-write + login-sync verification.
**Sources:** direct source reads in `src/backend/` + live DOM on `http://localhost:8000/` (2026-08-20) + web research. The stale report `16_preferential-city_readback_report.md` (§1.3/§6.7) is superseded by the now-implemented middleware.
**Key finding (summary):** The Spec_018 hybrid implementation is **substantially complete and shipped** — middleware, FK, cookie/DB write, view read-back, login sync, header button and tests all exist. The **only true spec gap** is a missing *reset* affordance (no "whole country" entry, no clear endpoint) → this is the root cause of `Decision_023`. A secondary **latent bug** is `?city=` inconsistency between `listings()` and `search()` plus a pagination divergence. Cookie-write (R-05) and login sync (T-06) are verified correct.

---

## 0. Executive summary

| Area | Verdict | Evidence |
|---|---|---|
| T-01..T-06 (model, middleware, write, view read-back, login sync) | **Implemented** | see §1 audit table |
| T-07 (header city button) | **Implemented** | `header_catalog.html:46-71`; badge via `context_processors.py:24-60` |
| T-08 (tests) | **Implemented** (3 gaps) | §1 AC table |
| Decision_023 "hard filter / can't reset" | **CONFIRMED spec gap** | no reset endpoint or dropdown entry; §4 |
| `?city=` consistency | **latent bug** + pagination divergence | §3 |
| Cookie-write attrs (R-05) | **Verified correct** | §5 |
| Login sync (T-06) | **Implemented & correct** | §5 |

> Confidence: **HIGH** on implementation status (file:line reads); **HIGH** on the reset-gap root cause (confirmed by live DOM); **MEDIUM** on the `?city=` recommendation (a spec-level design call, since Spec_018 AC-3 is silent on `/?city=` at the root).

---

## 1. AUDIT — implementation vs Spec_018 (file:line evidence)

### 1.1 Requirements R-01..R-11

| Req | Status | Satisfies (file:line) | Deviation / note |
|---|---|---|---|
| R-01 User.preferred_city FK | **Implemented** | `apps/users/models.py:73-80` — FK→`locations.City`, `null=True, blank=True`, `on_delete=SET_NULL`, `related_name="+"` | full match to spec |
| R-02 One migration | **Implemented** | `apps/users/migrations/0003_user_preferred_city.py:14-19` — single `AddField`, nullable → no default value | matches R-02; `makemigrations --check` yields exactly one new migration |
| R-03 Cookie attributes | **Implemented** | name constant `core/middleware/preferred_city.py:29`; `max_age=PREFERRED_CITY_COOKIE_MAX_AGE` (`=365*24*60*60`, line 30); `httponly=True` `preferred_city.py:60`; `samesite="Lax"` `preferred_city.py:62`; `secure=request.is_secure()` `preferred_city.py:63`; `path="/"` via Django default (not explicit, line 57-64) | path not set explicitly (Django defaults to `/`) — functionally correct, minor |
| R-04 Middleware resolves effective city | **Implemented** | `core/middleware/preferred_city.py:47-73` (`process_request` sets `request.preferred_city`); `process_response:75-79` deletes stale cookie; registered `config/settings/base.py:120` | spec text says "base.py:119" but LanguagePre is at 119 and PreferredCity at 120 — line ref is stale by 1; ordering `LanguagePre→PreferredCity` is correct |
| R-05 Search defaults to preferred | **Implemented** | `apps/search/views/search.py:71-72` — `current_city = explicit_city or getattr(request, "preferred_city", None)` | explicit `?city=` wins over preferred (AC-3) ✓ |
| R-06 Listings defaults to preferred | **Implemented** | `apps/ads/views/listings.py:301-327`; else-branch 317-327 reads `getattr(request, "preferred_city", None)`; context `current_city=effective_city` `listings.py:425` | full match (see §3 for `?city=` caveat) |
| R-07 Header city button | **Implemented** | `templates/components/header_catalog.html:46-71` (button + dropdown); badge `{{ preferred_city_display }}` line 53; click→persist+navigate lines 464-474; context `header_context` `apps/core/context_processors.py:24-60` | ⚠️ dropdown has **no "whole country" reset entry** (confirmed live DOM below) |
| R-08 Login migrates guest pref | **Implemented** | `apps/users/views/consent.py:321-324` (`auth_login`→`_reconcile_preferred_city_on_login`); backfill DB from cookie when `preferred_city_id is None` `consent.py:221-239`; cookie retained (no deletion) | reverse DB→cookie overwrite per D-13 §4 is **not** enforced (see note) |
| R-09 Logout keeps cookie | **Implemented** | `apps/users/views/logout.py:23` — `logout(request)` flushes session only; **no** `delete_cookie` | matches R-09 |
| R-10 Stale-cookie tolerance | **Implemented** | middleware validates+deletes: `preferred_city.py:64-73` (sets `_preferred_city_stale_cookie` 51,71; deletes in `process_response` 75-79); views `except City.DoesNotExist` at `search.py:78`, `listings.py:311,325` | defence in depth ✓ |
| R-11 Write persists DB for auth | **Implemented** | `apps/search/views/preferred_city.py:47-54` — `if request.user.is_authenticated: user.preferred_city = city; user.save(...)` | matches R-11 |

**R-04 middleware ordering — detailed check (task point 1).** `config/settings/base.py:112-123`:
```
113 SecurityMiddleware  114 WhiteNoise  115 SessionMiddleware  116 CommonMiddleware
117 CsrfViewMiddleware  118 AuthenticationMiddleware  119 LanguagePreMiddleware
120 PreferredCityMiddleware  121 MessageMiddleware  122 XFrameOptionsMiddleware
```
- `LanguagePre` (119) → `PreferredCity` (120): immediately after, as Spec_018 §7.4 requires ✓.
- `PreferredCity` is **after** `AuthenticationMiddleware` (118) — required, because the DB-wins branch reads `request.user.preferred_city` (`preferred_city.py:55-61`) ✓.
- It sits **after** `SessionMiddleware` (115). This is harmless: the middleware reads only `request.user` + `request.COOKIES` (both populated regardless of session order); it never touches `request.session`.
- No compression middleware exists in the stack (no `django.middleware.gzip`), so "before Compression" is moot.
- `request.preferred_city` is consumed by views (rendered **after** the full middleware chain) and by the global context processor `header_context` (`context_processors.py:47`), which runs during template rendering — i.e. after `process_request`. Enrichment is therefore available everywhere it's needed ✓.

### 1.2 Development tasks T-01..T-08

| Task | Status | Evidence |
|---|---|---|
| T-01 Add `preferred_city` FK | Implemented | `users/models.py:73-80`; `users/migrations/0003_user_preferred_city.py` |
| T-02 Add `PreferredCityMiddleware` | Implemented | `core/middleware/preferred_city.py`; `base.py:120` |
| T-03 Extend cookie-write endpoint | Implemented | `search/views/preferred_city.py` (DB write 47-54; shared constants imported from middleware 16-19) |
| T-04 Search read-back | Implemented | `search.py:71-72` |
| T-05 Listings read-back | Implemented | `listings.py:301-327` (else-branch 317-327) |
| T-06 Login sync hook | Implemented | `consent.py:208-239`, wired `consent.py:321-324` |
| T-07 Header city button | Implemented | `header_catalog.html:46-71,435-475`; `context_processors.py:24-60` |
| T-08 Tests | Implemented (3 gaps) | `core/tests/test_preferred_city_middleware.py` (6); `search/tests/test_preferred_city_readback.py` (7); `search/tests/test_preferred_city.py` (8); `users/tests/test_login.py::TestLoginPreferredCitySync` (3) |

### 1.3 Acceptance criteria AC-1..AC-10

| AC | Status | Evidence (impl + test) | Gap? |
|---|---|---|---|
| AC-1 DB wins over cookie | Implemented + tested | `search.py:71-72`; `test_preferred_city_readback.py:128-144` (DB=budva? no—DB podgorica wins); `test_preferred_city_middleware.py:51-60` | — |
| AC-2 Guest cookie default | Implemented + tested | `search.py:72`; `test_preferred_city_readback.py:108-116` (search), `:171-179` (listings) | — |
| AC-3 Explicit city overrides | Implemented + tested (2 of 3 cited URLs) | `/city/budva/` lists path-filter `listings.py:306-310` + test `:161-169`; `/search/?q=x&city=budva` `search.py:71-77` + test `:118-126` | `/?city=budva` (root) is NOT a filter — did-you-mean only (see §3) |
| AC-4 Stale cookie cleared | Implemented + tested | middleware `:64-79`; `test_preferred_city_readback.py:146-155`; `test_preferred_city_middleware.py:100-127` | — |
| AC-5 Select persists auth+guest | Implemented + tested | `preferred_city.py:42-64`; `test_preferred_city.py:48-73` | — |
| AC-6 Login migrates guest pref | Implemented + tested | `consent.py:208-239`; `test_login.py:255-282` | — |
| AC-7 Logout retains cookie | Implemented, **NOT tested** | `logout.py:23` (session-only); `test_logout.py` asserts session flush + redirect but **never** asserts the `preferred_city` cookie survives logout | ⚠️ test gap |
| AC-8 Header badge renders | Implemented + tested | `header_catalog.html:53`; `context_processors.py:46-60`; `test_preferred_city.py:100-119` | — |
| AC-9 No UserProfile model | Implemented | only `User`+`LoginToken` in `users/models.py`; single migration `0003` | — |
| AC-10 preferred_city ≠ SavedSearch.city | Correct by construction, **not tested** | `search/models.py:63` (`SavedSearch.city` FK, independent); browsing views (`search.py:71`, `listings.py:301`) use `preferred_city`/params, never `SavedSearch.city` | ⚠️ no AC-10 test exists |

---

## 2. Decision_023 root cause — CONFIRMED SPEC GAP (hard filter, cannot reset)

`Decision_023.md` (ru): *"city acts as a HARD filter; can't reset to whole country; verify Spec_018 logic actually executes."*

Verified against live DOM + source:

1. **The Spec_018 priority logic IS executed.** `PreferredCityMiddleware` (`core/middleware/preferred_city.py:47-73`) resolves the effective preferred city (DB-first for auth, cookie fallback for anon), and both `search()` (`search.py:71-72`) and `listings()` (`listings.py:317-327`) apply it as a *default* filter. Explicit city in path/`?city=` always wins. This matches Spec_018 §4 and §5.2. → The "is it actually executed?" question: **yes**.

2. **But there is no affordance to clear it.**
   - No "whole country" entry in the header dropdown. Live DOM (`localhost:8000/`, dropdown `[data-preferred-city-panel]` opened) lists exactly 15 cities — **Бар, Беране, Биело-Поле, Будва, Даниловград, Котор, Мойковац, Никшич, Плевля, Подгорица, Рожае, Тиват, Улцинь, Херцег-Нови, Цетине** — and **no "Вся страна / All" option**. Source: `header_catalog.html:61-68` iterates `{% for city in cities %}` only, with no static "all" entry.
   - The cookie-write endpoint `POST /api/preferred-city/` (`search/views/preferred_city.py:42-44`) only *accepts* a valid slug; empty/missing/unknown → `400 invalid_city`. There is **no** `DELETE` and no `action=clear`. So a buyer cannot POST to clear a preference.
   - The click handler (`header_catalog.html:464-474`) only handles `[data-city-option]` (specific cities); no handler for a "clear" action.

3. **The badge already shows the "unset" state** (`preferred_city_display = "Вся страна"` at `context_processors.py:46`; confirmed on live DOM: badge reads "Вся страна" with no cookie). So the UX language for "no preference = whole country" already exists — there's simply no control that *sets* it.

**Conclusion:** The "hard filter / can't reset" perception is **not** a logic bug in the read-back (the middleware priority is correct); it is a **missing reset surface**. Once a city is selected, every catalog/search page re-applies it, and the only escape is the undocumented `/?city=<anything>` did-you-mean path (which, see §3, is itself broken for valid slugs). This is the exact "SPEC GAP: no UI/endpoint clears preferred_city" cited in the analyst brief.

---

## 3. `?city=` CONSISTENCY — the latent inconsistency + a pagination bug

### 3.1 Observed behaviour (file:line)

| Path | `search.py` | `listings.py` |
|---|---|---|
| `?city=<valid>` (e.g. `budva`) | **FILTERS** to that city (`search.py:71-77`) | **did-you-mean ONLY — no filter → ALL ads** (`listings.py:315-316`: `elif request.GET.get("city"): suggested_city = _suggest_city(...)`) |
| `?city=<invalid>` | did-you-mean banner, no filter (`search.py:78-79`) | did-you-mean banner, no filter (`listings.py:315-316`) |
| no `?city=`, cookie=`podgorica` | preferred-city default filter (`search.py:72`) | preferred-city default filter, `else` branch (`listings.py:317-327`) |

So `/search/?q=x&city=budva` → Budva ads, but `/?city=budva` → **all ads** (with a "Did you mean budva?" banner). This is the inconsistency flagged in `16_preferential-city_readback_report.md` §1.3/§6.7.

### 3.2 The lock-in test

`search/tests/test_preferred_city_readback.py:181-191` `test_explicit_query_param_prevents_preferred_default`:
```python
client.cookies["preferred_city"] = "podgorica"
response = client.get("/?city=budva")
assert set(_result_ids(response)) == {podgorica_ad.id, budva_ad.id}   # BOTH ads → no filter
assert response.context["suggested_city"] == "budva"
assert response.context["current_city"] is None
```
This test **locks in** the did-you-mean-only behaviour for a **valid** slug on the root listing. It is the contract: `/?city=<valid>` on `listings()` does not filter.

### 3.3 The downstream pagination bug this causes

`ad_list.html:74-101` build pagination links as `?page=…&city={{ current_city }}`. On the root with a preferred city, `listings.py:425` sets `current_city = effective_city = "podgorica"`, so page-2 is `/?page=2&city=podgorica`. That re-enters the `elif request.GET.get("city")` branch (`listings.py:315`) → **did-you-mean only → ALL ads**. Result: **page 1 shows only Podgorica ads, page 2 shows all-country ads** — a real divergence, no test guards it.

### 3.4 Recommended single rule

> **`?city=<valid-slug>` is always a real list filter; `?city=<invalid/unknown-slug>` is did-you-mean only (no filter + suggestion banner).** Unify `listings()` on `search()`'s already-correct contract.

Rationale:
- Search has no city path param, so `?city=` **must** be a filter there — it's the only mechanism. Listings is the outlier.
- The "did-you-mean only for a *valid* slug" is what produces the surprise ("I asked for Budva, why do I see the whole country?") and the pagination divergence above.
- This is a strict improvement: a valid `?city=` behaves identically on `/search/` and `/`.

**Impact on existing code/tests:**
- `listings.py:315-316` (`elif request.GET.get("city")`) must resolve the slug and **filter on valid** (mirror `search.py:71-77`), falling back to `_suggest_city` only on `City.DoesNotExist`.
- `test_explicit_query_param_prevents_preferred_default` (`test_preferred_city_readback.py:181`) **must change**: under the new rule `/?city=budva` returns `[budva_ad.id]`, `current_city == "budva"`, `suggested_city is None`. Rename to `test_explicit_query_param_filters_to_city`. Per the repo's "Production Code is King" rule, fix the test to match the corrected business logic.

**Important coupling:** making valid `?city=` a filter **removes the only undocumented escape from a stuck preferred city**. Therefore this rule **must ship together with the reset affordance (§4/§6 recommendation)** — otherwise users with a preferred city can no longer reach "all ads" at all. Do not ship the `?city=` change alone.

---

## 4. CITY-RESET AFFORDANCE — patterns from leading classifieds

Evidence: `.ai/research/16_preferred-city_readback_report.md` §3.1 (live DOM 2026-08-19) + web research + live DOM on `localhost:8000` (2026-08-20) + a live Russian classified-style example (Proshoper).

### Pattern 1 — "All" as the first/ default option in the selector (OLX.ua, Mobile.bg)
- **OLX.ua**: the city is a combobox embedded in the hero search form whose placeholder is "All Ukraine" — country-wide is the *default* selectable value (§3.1 live DOM). Picking a city narrows; re-picking "All Ukraine" clears.
- **Mobile.bg**: region `<select>` in the filter sidebar whose first option is "всички" (All) (`listings.py` analogue: a reset-is-default design).
- **UX position**: inside the selector itself, as the head option. Most discoverable because it's where the user already looks to pick a city.

### Pattern 2 — Clearable active-filter chip with ✕ (Avito.ru)
- **Avito.ru**: while a city is active it appears as a small removable chip in the filter bar (e.g. "Город: Пермь ✕"); clicking ✕ removes the filter and returns to country-wide. The header button still shows the city, but the *reset* lives on the filter bar.
- **UX position**: filter-summary bar, adjacent to results. Good once a filter is active, but invisible until you've filtered.

### Pattern 3 — Dedicated "clear/reset" link or button (Proshoper, Avito "Очистить")
- Observed live (search, 2026-08-20): Proshoper renders an explicit **"Отменить выбор города"** ("Cancel city selection") link that navigates to the country-wide root `/`. Avito's filter bar also has an "Очистить все" (clear all) affordance.
- **UX position**: a distinct, labelled control — highest explicit discoverability, slightly more header chrome.

### Other observed (for contrast)
- **Otomoto.pl / SS.com**: no persistent city selector at all (Otomoto uses homepage city *links* with radius; SS.com is Latvian-single-country). Not applicable to Mko Bazuna's city model.
- **Carousell** (per research): location picker with "All areas" type reset and per-filter ✕ chips.

### Best-fit recommendation for Mko Bazuna (header dropdown)

> **Adopt Pattern 1: add a "Вся страна" (Whole country) entry as the FIRST item in the existing header city dropdown, and wire it to a clear action.**

Why it's the best fit for the *current* `header_catalog.html` design:
- The dropdown already exists (`header_catalog.html:46-71`) and already lists cities via `{% for city in cities %}`. Adding one static head entry is a ~4-line template change, no new UI surface.
- The badge already uses the label **"Вся страна"** for the unset state (`context_processors.py:46`; confirmed live: badge reads "Вся страна" with no cookie). The reset entry therefore mirrors the badge — the dropdown becomes the inverse of the badge, which is self-consistent and learnable.
- Pattern 1 is the most discoverable (always visible on dropdown open) and matches the OLX/Mobile.bg "All is the default" convention that the spec's research (§5.1) already endorsed for small markets.
- It avoids the header-chrome cost of Pattern 3 (a separate "clear" button) and the "invisible until filtered" problem of Pattern 2.

**Implementation sketch** (for the Analyst's final spec):
- `header_catalog.html` — insert a head `<li>` before the `{% for city in cities %}` loop: a button `[data-city-clear]` labelled "Вся страна" (localized), styled as a reset option.
- New clear path: `POST /api/preferred-city/` with `slug=""` (or a dedicated `action=clear`) → deletes the `preferred_city` cookie (`response.delete_cookie`), and for authenticated users sets `User.preferred_city = None` (`user.save(update_fields=["preferred_city"])`); then navigate to `/`.
- The click handler (`header_catalog.html:464-474`) gains a branch for `[data-city-clear]`.
- Context processor continues to render the badge from `request.preferred_city` (now `None` → "Вся страна").

---

## 5. COOKIE-WRITE ENDPOINT (R-05) + LOGIN SYNC (T-06) — verification

### 5.1 Cookie-write endpoint `POST /api/preferred-city/` (name `search:preferred_city`)
`apps/search/views/preferred_city.py` (`set_preferred_city`):
- **400 on empty/invalid slug** ✓ — line 42-44: `if not slug or not City.objects.filter(slug=slug).exists(): return JsonResponse({"error":"invalid_city"}, status=400)`.
- **1-year max-age** ✓ — `max_age=PREFERRED_CITY_COOKIE_MAX_AGE` (line 60); constant `= 365 * 24 * 60 * 60` (`core/middleware/preferred_city.py:30` = 31,536,000 s = 365 d). [Spec_016's 30-day value is gone.]
- **HttpOnly** ✓ — `httponly=True` (line 61).
- **SameSite=Lax** ✓ — `samesite="Lax"` (line 62).
- **Secure (prod only)** ✓ — `secure=request.is_secure()` (line 63); dev `request.is_secure()==False` so cookie is not Secure in dev (matches `16_…_report` §6.5).
- **path=/** ✓ — not passed to `set_cookie`; Django default is `"/"` (satisfies spec R-03 `path=/`).
- **Cookie name is a shared module constant** ✓ — `PREFERRED_CITY_COOKIE_NAME` (`core/middleware/preferred_city.py:29`), imported by the view (line 16-19) and by `consent.py` (line 32). Follows the `LANGUAGE_COOKIE_NAME`/`CONSENT_COOKIE_NAME` convention; **not** a StrEnum (correct per Spec_018 §7.3).
- **DB write for auth** ✓ — `if request.user.is_authenticated: user.preferred_city = city; user.save(update_fields=["preferred_city"])` (lines 47-54).
- **405 on GET** ✓ — `@require_POST` (line 25); `test_preferred_city.py:92-94` confirms.
- Tests: `test_preferred_city.py:48-90` (5 tests) cover all of the above. ✓

### 5.2 Login sync — `consent.py` (T-06 / AC-6)
`login_status()` (`consent.py:321-324`): after `auth_login(request, user)` → `_reconcile_preferred_city_on_login(request, user)`.
Function (`consent.py:208-239`):
1. `if user.preferred_city_id is not None: return` → **DB preference is never overwritten by the cookie** ✓ (D-13 "DB wins").
2. Else: read `cookie_slug = request.COOKIES.get(PREFERRED_CITY_COOKIE_NAME)` (line 225); if valid → `user.preferred_city = City.objects.get(slug=cookie_slug); user.save(update_fields=["preferred_city"])` (lines 230-231).
3. **Cookie is retained** (no `delete_cookie`) — serves the next anonymous session (D-8/D-9) ✓.
4. **`?city=` param is never touched by the sync** ✓ — it only reconciles cookie↔DB. An explicit `?city=` is a per-request view-level override (`search.py:71`, `listings.py:306/317`), never persisted to DB by the login flow. So the sync does **not** overwrite an explicit `?city=` param, satisfying task point 4.

**Tests:** `test_login.py::TestLoginPreferredCitySync` (3 tests, lines 243-307): backfills from cookie (255), does-not-overwrite existing DB pref (273), no-cookie-no-crash (294). All pass per the file.

**Minor deviations to flag to the analyst:**
- **D-13 reverse direction not enforced.** Spec D-13 / T-06 §8.3 says "if DB set → overwrite cookie from DB" (bidirectional). The implementation only does the **cookie→DB** backfill; when `user.preferred_city_id is not None` it returns early **without** rewriting the cookie to match the DB (`consent.py:221-223`). Spec §8.3 explicitly accepts this ("cookie already = user.preferred_city.slug from last click; no overwrite needed"). **Gap only if the DB preference can ever be set without a matching cookie** (e.g., a future user-cabinet profile page). Today's only setter (`POST /api/preferred-city/`) writes cookie+DB together, so they stay in sync in practice. **Recommendation:** add a one-line "resync cookie from DB" in the `elif` branch now, to honour D-13 and stay safe for the future cabinet page — low effort, removes the ambiguity.
- **AC-7 (logout retains cookie) is untested.** `test_logout.py` covers session flush + redirect + 405/403 but never asserts the `preferred_city` cookie survives logout. Recommend adding `assert response.cookies["preferred_city"]...` (or `client.cookies["preferred_city"]`) is intact — trivial to add.
- **AC-10 (preferred_city ≠ SavedSearch.city independence) is untested.** Behaviour is correct by construction (`SavedSearch.city` `search/models.py:63` is a separate FK only used by alert jobs; browsing uses `preferred_city`/params). No test asserts "changing User.preferred_city does not re-scope an existing SavedSearch alert." Recommend a small regression test.

---

## 6. Recommendations (single answer per asked item)

### (a) Reset affordance — **header dropdown "Вся страна" head-item + clear endpoint**
Add "Вся страна" as the **first** item of the existing city dropdown in `header_catalog.html` (`data-city-clear`), wired to clear both persistence layers and navigate to `/`. Matches OLX/Mobile.bg "All is the default" + mirrors the existing badge label. (See §4.) Do **not** use a separate header button or a footer link — the dropdown already exists and the badge label already says "Вся страна", so a head-item is the least-churn, most-consistent option.

### (b) `?city=` rule — **`?city=<valid>` always filters (unify listings on search); invalid slug → did-you-mean**
- Listings `elif request.GET.get("city")` (`listings.py:315-316`) must filter on a valid slug exactly like `search.py:71-77`, and did-you-mean only on `City.DoesNotExist`.
- Update `test_explicit_query_param_prevents_preferred_default` (`test_preferred_city_readback.py:181`) → rename to `test_explicit_query_param_filters_to_city`, assert `/?city=budva` returns `[budva_ad.id]`, `current_city == "budva"`, `suggested_city is None`.
- **This MUST ship with recommendation (a):** the reset affordance is what lets a user reach "whole country" once `/?city=<valid>` stops being a (broken) escape hatch. Ship (a) and (b) together; a standalone `?city=` change would regress `Decision_023`.

### Priority ordering for the Analyst
1. **Reset affordance (a)** — fixes `Decision_023` (the actual reported bug). Highest priority.
2. `?city=` consistency (b) — fixes the latent inconsistency + pagination divergence. Second.
3. Test gaps (AC-7, AC-10) + D-13 reverse-sync line-3 — small follow-ups.

---

## Appendix — file:line evidence index

- User FK: `apps/users/models.py:73-80`; migration `apps/users/migrations/0003_user_preferred_city.py:14-19`, `users/migrations/0002_alter_user_telegram_id_null.py`
- Middleware: `apps/core/middleware/preferred_city.py:29-30` (constants), `:47-73` (resolve), `:75-79` (clear); registered `config/settings/base.py:119-120`
- Cookie write: `apps/search/views/preferred_city.py:42-64`; tests `apps/search/tests/test_preferred_city.py:48-90`
- Search read-back: `apps/search/views/search.py:69-79`; tests `apps/search/tests/test_preferred_city_readback.py:108-155`
- Listings read-back: `apps/ads/views/listings.py:301-327` (filter branches), `:425` (context `current_city`); tests `apps/search/tests/test_preferred_city_readback.py:158-191`
- Listings root URL: `apps/ads/urls.py:25-27` (`""`→listings, `city/<slug:city_slug>/`→listings_city)
- Header button + dropdown: `templates/components/header_catalog.html:46-71` (markup), `:435-475` (click handler)
- Header context (badge + cities): `apps/core/context_processors.py:24-60` (global, `base.py:140`)
- Login sync: `apps/users/views/consent.py:321-324` (call site), `:208-239` (`_reconcile_preferred_city_on_login`); tests `apps/users/tests/test_login.py:243-307`
- Logout retains cookie: `apps/users/views/logout.py:23` (session-only); tests `apps/users/tests/test_logout.py` (no cookie-retention assertion)
- SavedSearch.city independence: `apps/search/models.py:49,63`
- `?city=` did-you-mean-only lock-in test: `apps/search/tests/test_preferred_city_readback.py:181-191`
- Pagination link construction: `templates/ads/partials/ad_list.html:74-101`
- City model (slug unique, no is_active): `apps/locations/models.py:36-39`; `apps/locations/urls.py` (empty — no "all" route)
- Live DOM confirmation (2026-08-20 @ 12:20+02:00): city dropdown = 15 cities only (no "Вся страна"); badge reads "Вся страна" with no cookie — screenshot `header_city_dropdown_open.png`, snapshot file `header_city_dropdown_open.md`.

---

*Report compiled from file:line reads in `src/backend/` (Django 5.2.16 + Python 3.14), live DOM inspection of `http://localhost:8000/` via Playwright (2026-08-20T12:20+02:00), and web research. No runtime state was mutated (only a client-side CSS dropdown toggle was opened; no navigation/form submission/cookie write occurred).*
