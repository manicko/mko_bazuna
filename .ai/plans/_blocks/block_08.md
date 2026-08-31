# Block 8: Preferred City & Did-You-Mean

## Block Summary

This block covers the hybrid preferred-city persistence layer (consent-gated 1-year cookie for guests, `User.preferred_city` DB FK for authenticated buyers, with login reconciliation and consent-revoke cleanup), the override precedence rule (explicit `?city=` / `/city/<slug>/` path wins over the stored preference used only as a fallback default), and the "Did-You-Mean" fuzzy city correction on listings. One implementation gap remains: the search view (`search.py:76-81`) echoes an invalid `?city=` slug as the suggestion without fuzzy matching, whereas the listings view calls `_suggest_city()` (`listings.py:483-506`) with a `difflib` cutoff of 0.6.

**Source:** `.ai/research/search-journeys-our-architecture.md:146`, `.ai/research/search-journeys-spec.md:218`, `.ai/problems/01_search_patterns_test_verification_top_plan.md:176-189`
**Top plan:** `.ai/problems/01_search_patterns_test_verification_top_plan.md` — Block 8 (G11)

---

## Findings Table

| # | Variation | Implementation Location | Coverage Status | Existing Test (file:line) | Test-Engineer Task | Risk |
|---|-----------|------------------------|-----------------|---------------------------|-------------------|------|
| V1 | Preferred-city POST — `POST /api/preferred-city/` with valid slug sets a consent-gated cookie (1-yr, `HttpOnly`, `SameSite=Lax`) for guests; writes `User.preferred_city` FK for authenticated buyers; 400 on unknown/missing slug; 405 on GET. | `search/views/preferred_city.py:25-87`; route `search/urls.py:15`; consent gate `preferred_city.py:77-85`; DB write `preferred_city.py:64-69` | EXISTS | `search/tests/test_preferred_city.py:59-123` (`TestPreferredCityView`) | None — fully covered. Confirm cookie attribute assertions (max-age=`PREFERRED_CITY_COOKIE_MAX_AGE`, `httponly=True`, `samesite="Lax"`) trace to `preferred_city.py:78-85`. | LOW |
| V2 | Override precedence — explicit `?city=` query param or `/city/<slug>/` path always wins; the preferred city (DB > cookie > None) is the fallback default only when no explicit city is in the URL. | `ads/views/listings.py:286-319` (path `city_slug` → query `?city=` → preferred fallback chain); `search/views/search.py:73-74` (`explicit_city or getattr(request, "preferred_city", None)`) | EXISTS | `search/tests/test_preferred_city_readback.py:81-131` (`TestSearchPreferredCityReadback`); `:137-166` (`TestListingsPreferredCityReadback`) | Confirm precedence matrix is asserted for each tier. Minor edge gap: combined path `city_slug` + `?city=` query-param precedence on listings is untested (path always wins because `if city_slug:` at `listings.py:292` precedes the `elif` at `:301`). Add a case: `GET /city/budva/?city=podgorica` → results scoped to Budva, `current_city == "budva"`. | LOW |
| V3 | Clear/reset — `POST action=clear` or present-but-empty `slug=""` deletes the cookie and nulls `User.preferred_city` for authenticated buyers. Consent-revocation path: `_set_consent_cookies` deletes the cookie when `preferences=False` (consent.py:94-97). Login reconciliation: `_reconcile_preferred_city_on_login` backfills the DB from a guest's cookie on login (consent.py:318-349). | `preferred_city.py:42-58` (clear logic); `consent.py:94-97` (revoke clears cookie); `consent.py:318-349` (login backfill) | EXISTS | `search/tests/test_preferred_city.py:157-231` (`TestReset`); `users/tests/test_login.py:363-415` (login backfill) | `TestReset` (157-231) and login backfill (test_login.py:363-415) are covered. **Test gap:** consent-revoke clearing the `preferred_city` cookie (`consent.py:94-97`) is NOT explicitly asserted — `test_consent.py:258-265` (`test_withdraw_sets_withdrawn_cookie`) checks only the `consent_given` cookie, not `preferred_city`. Add assertion: after `POST /consent/withdraw/`, `response.cookies["preferred_city"]` is absent/deleted. | MEDIUM-LOW |
| V4 | Did-you-mean on listings — invalid `?city=` query param or `/city/<slug>/` path triggers `_suggest_city()` (`difflib.get_close_matches`, cutoff 0.6) and renders a "Did you mean:" banner (`ad_list.html:26-32`) linking to the corrected `ads:listings_city` URL. | `ads/views/listings.py:483-506` (`_suggest_city`); call sites `listings.py:299` (path) and `:308` (query); banner `templates/ads/partials/ad_list.html:26-32` | EXISTS | `search/tests/test_preferred_city_readback.py:169-179` (`test_invalid_query_param_suggests_only`) | Confirm coverage asserts: (a) invalid slug → no city filter applied (all ads shown), (b) `suggested_city` is a fuzzy match (not the raw slug), (c) banner link targets `{% url 'ads:listings_city' suggested_city %}` (ad_list.html:29). Document the known difflib limitation: transposition typos (e.g. "budav") may not be caught at cutoff 0.6. | LOW |
| V5 | **Did-you-mean on search (GAP)** — invalid `?city=` on `/search/` sets `suggested_city = current_city` (search.py:81), echoing the raw invalid slug with no fuzzy match. The shared banner (`ad_list.html:26-32`) then links to `{% url 'ads:listings_city' <invalid-slug> %}`, sending the buyer to a listings page for a non-existent city. No test covers an invalid `?city=` on `/search/`. | `search/views/search.py:74-81` (gap at line 81: `suggested_city = current_city`); shared banner `ad_list.html:26-32` (line 29 links the raw slug) | **GAP** | None | **PREREQUISITE IMPLEMENTATION:** replace `suggested_city = current_city` at `search.py:81` with `suggested_city = _suggest_city(current_city)`, reusing the helper at `listings.py:483-506` (may require extraction to a shared module — e.g. `apps/locations/utils.py` — to avoid a cross-app import from `ads.views.listings`). **Then test:** `GET /search/?q=<term>&city=budv` (with a `podgorica`-scoped ad and a `budva`-scoped ad) → assert `response.context["suggested_city"]` equals `"budva"` (fuzzy match, not `"budv"`), assert the rendered banner link (`ad_list.html:29`) points to `/city/budva/` (corrected), and assert no city filter is applied (both ads returned, `current_city == "budv"`). | HIGH |

---

## Priority: **HIGH**

V5 (did-you-mean on search) is a confirmed implementation gap carrying HIGH risk: a buyer typing an invalid city slug on the search page sees a "Did you mean:" banner that links to a **non-existent** city URL (`/city/budv/`), producing a confusing dead-end instead of a corrected suggestion. This violates the did-you-mean contract documented in `search-patterns.md:146` and the US-B7 user story (`docs/04-user-stories/buyer-stories.md:36,51`), and diverges from the listings view (V4) which correctly applies fuzzy matching. The fix is a one-line change (`search.py:81`) plus a shared helper reuse decision and test coverage.

V3 carries MEDIUM-LOW risk: the implementation exists and is tested for the clear path and login backfill, but the consent-revoke cookie-clearing path (`consent.py:94-97`) lacks an explicit assertion, which risks a silent ePrivacy-compliance regression if the revoke flow is refactored.

V1, V2, and V4 are LOW risk: implementations exist and are covered by integration tests with precise assertions on context keys, cookie attributes, and result scoping.

---

## Dependencies (Blocks 3 & 7)

| Depends On | Block / Surface | Rationale |
|------------|-----------------|-----------|
| Block 3 (Search Submission & FTS Results) | `.ai/plans/_blocks/block_03.md` | V2 and V5 depend on the `search()` view (`search.py`) which renders results through the shared partial `ads/partials/ad_list.html:26-32` (the did-you-mean banner). V5's fix lives inside `search.py` itself. |
| Block 7 (URL State, Pagination & Navigation) | `.ai/plans/_blocks/block_07.md` | The `?city=` query-parameter contract (explicit city in URL) is a URL-state concern owned by Block 7. V2's override precedence and V5's invalid-slug handling both hinge on `?city=` being correctly parsed and echoed/preserved in pagination and chip-removal URLs (`ad_list.html:41-42`, `:142-171`). |
| City data model + middleware (intra-block surface, not a numbered Block) | `apps/locations/models.py` (City); `apps/core/middleware/preferred_city.py:33-79` | V1, V3, V4 all depend on the `City` model (slug lookup) and `PreferredCityMiddleware` resolving `request.preferred_city`. V5 reuses the `_suggest_city` helper (`listings.py:483-506`) which queries `City.objects.values_list("slug", flat=True)`. |

**V5 sequencing:** The fix at `search.py:81` and its tests can proceed once Block 7's `?city=` URL-state contract is stable (no ordering dependency on test implementation, only on the param being parsed). V5 is independent of V1-V3 implementation but shares the `ad_list.html` banner template, so a template change there would affect both V4 and V5 test assertions.

---

## Validator Recommendations

### V1 — Preferred-city POST cookie attributes
- Assert `response.cookies["preferred_city"]["max-age"]` equals `PREFERRED_CITY_COOKIE_MAX_AGE` (imported from `apps.core.middleware.preferred_city`), `["httponly"]` is `True`, and `["samesite"]` is `"Lax"` — matching `preferred_city.py:78-85`.
- Confirm the `secure` flag mirrors `request.is_secure()` (`preferred_city.py:84`) by testing over both HTTP and HTTPS (Django test Client `secure=True`).

### V2 — Override precedence matrix
- For each tier, assert `response.context["current_city"]`:
  1. Path `city_slug` set (with or without `?city=` query) → path wins.
  2. No path, `?city=<valid>` → query wins, scoped to that city.
  3. Auth user with `User.preferred_city` set, no explicit URL city → DB value.
  4. Anonymous with valid `preferred_city` cookie, no explicit URL city → cookie value.
  5. Neither → `current_city is None`, country-wide results.
- Reuse the `buyer`/`podgorica`/`budva` fixtures and `create_test_ad` helper from `conftest.py`.

### V3 — Consent-revoke cookie clearing (the gap)
- `POST /consent/withdraw/` with an authenticated user who has a `preferred_city` cookie set in the request → assert `response.cookies["preferred_city"].value == ""` (scheduled for deletion), confirming `consent.py:94-97` fires.
- Also test `POST /consent/decline/` with `preferences=false` → assert preferred_city cookie deleted (the `not preferences` branch at `consent.py:96`).

### V4 — Listings did-you-mean
- `GET /city/budav/` (transposition of "budva") → assert `suggested_city is None` (difflib 0.6 cutoff misses transpositions). Document as known limitation, not a bug.
- `GET /city/budava/` (extra char) → assert `suggested_city == "budva"` and banner link points to `/city/budva/`. Confirms the stale report claim of a 301 redirect is false (see Verification Corrections).

### V5 — Search did-you-mean (gap fix)
- **Fix prerequisite:** At `search.py:76-81`, the `except City.DoesNotExist:` branch must call `_suggest_city(current_city)` instead of assigning `suggested_city = current_city`. Decide whether to (a) import the private `_suggest_city` from `apps.ads.views.listings` or (b) extract it to `apps/locations/utils.py` for clean cross-module reuse. Either choice must be reflected in the test's import assertions.
- **Test assertions** (`TestSearchSuggestedCity` class in a new `test_search_didyoumean.py` or appended to `test_preferred_city_readback.py`):
  - `GET /search/?q=Велосипед&city=budv` → `response.context["suggested_city"] == "budva"` (fuzzy match), not `"budv"`.
  - Banner link in `response.content` contains `href="/city/budva/"` (corrected slug, see `ad_list.html:29`).
  - `response.context["current_city"] == "budv"` (the raw invalid slug, echoed for URL preservation) and `page_obj` is unscoped by city (all published ads returned).
  - Negative case: `GET /search/?q=Велосипед&city=nowhere` → `suggested_city is None` (no close match), banner absent.

---

## Verification Corrections

### Stale report: `/city/budava/` → 301 redirect (CONFIRMED STALE)

The verification report `.ai/problems/01_search_patterns_verification.md:189-193` claims:

> `/city/budava/` → HTTP 301 → `/city/budva/?lang=ru` ✅ (extra character typo caught)

This is **stale**. No redirect exists anywhere in the current source. The listings view (`listings.py:292-299`) handles an invalid `city_slug` by setting `suggested_city = _suggest_city(city_slug)` and falling through to render the page (200) with the did-you-mean banner — `listings.py` does not issue any 301/302. The spec (`search-patterns.md:146`) and canonical tests (`test_preferred_city_readback.py:169-179`) both confirm the banner behavior, not a redirect.

The `/lang/ru` suffix in the claimed redirect is also inconsistent with the current implementation (language is switched via `?lang=` query param or `lang_pref` cookie per Block 9, not via URL path prefixing).

**Action:** Correct the verification report at `.ai/problems/01_search_patterns_verification.md:192` to reflect the banner behavior. The "did-you-mean detail" at lines 191-193 should be updated: `/city/budava/` → 200 with banner suggesting "budva"; `/city/budav/` → 200 with banner suggesting `None` (difflib 0.6 misses transposition).
