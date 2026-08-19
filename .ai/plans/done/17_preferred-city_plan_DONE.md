---
id: 17_preferred-city
domain: implementation-plan
source_spec: .ai/problems/18_preferred-city_spec.md
status: DONE
date: 2026-08-19
completed: 2026-08-20
---

# Plan 17 — Preferred-City: Hybrid Persistence & Catalog City Selector

Transform of **Spec_018** (`.ai/problems/18_preferred-city_spec.md`, IMPLEMENTATION-READY)
into a dependency-aware implementation DAG.

## 1. Statement of scope

Implement the hybrid preferred-city model (Decision_018 revised):

- `User.preferred_city` nullable FK → `locations.City` (one migration) for authenticated buyers
- `preferred_city` cookie (1-year, HttpOnly) as the guest fallback
- `PreferredCityMiddleware` (structural twin of `LanguagePreMiddleware`) that resolves the
  *effective* preferred city each request (DB wins for auth, cookie for anon) and cleans stale cookies
- Read-back into `search()` and `listings()` as a **default** (never a hard) city filter
- Login-time reconciliation of guest cookie → account preference
- Header city button (`📍 <City> ▾`) with a Montenegro-city dropdown on catalog/detail pages

This plan does **not** change the documented boundaries; the spec's concept list (T-01…T-08)
is reorganized below into implementation-sequenced, parallelizable tasks.

## 2. Planning decisions (resolved here, not new requirements)

> These decisions keep tasks atomic and dependency-safe; each is grounded in the spec, not invented.

- **D-P1 — Shared cookie constants live in the middleware module.** Following the
  `LanguagePreMiddleware` structural twin, `PreferredCityMiddleware` module defines
  `PREFERRED_CITY_COOKIE_NAME` and `PREFERRED_CITY_COOKIE_MAX_AGE` (1 year). The write endpoint
  (`preferred_city.py`) and login hook (`consent.py`) import them — no third constants module.
  Grounds: Spec §7.3 / §5.2 (module-level constant precedent at `language.py:34-35`).
- **D-P2 — Header badge does not change the effective filter.** The header badge displays the
  *persisted preference* (`request.preferred_city`), the same value the views use as a default.
  An explicit URL/`?city=` never rewrites the badge preference (AC-3). View context
  `current_city` (T-04/T-05) reflects the transient active filter and is orthogonal to the badge.
- **D-P3 — Shared `header_context` is the single source for the header.**
  `apps/core/context_processors.py:header_context` exposes `preferred_city_display` and `cities`
  to every template that includes `header_catalog.html` (list **and** detail). This is consistent
  with `header_context`'s existing role (it already supplies `root_categories` DB query for the
  header) and resolves the pre-existing `cities`-on-detail gap without a per-view `ad_detail` change
  (Spec §5.2 / §10 / §13). Grounded in the spec's §13 note ("optionally expose resolved preferred
  city to header") and §8.5 (`preferred_city_display`, `cities`).
- **D-P4 — No research gate required.** Spec §5 already resolved the storage / middleware / UI
  approach with two rejected alternatives documented. Middleware enrichment is adopted, mirroring
  an existing in-repo pattern. Colocated with the spec's validation; no new external research.

## 3. Risk assessment & gates

| Task | Risk trigger | Severity | Gate |
|---|---|---|---|
| **T-01** | DB schema change + new migration | High | No research gate (fully specified: nullable FK, SET_NULL, `related_name="+"`, single `0003_user_preferred_city`). Verification = `makemigrations --check` + migration applies on test DB. |
| **T-02** | Startup behavior + shared config (`MIDDLEWARE`) + new `request` attribute contract | High | No research gate (mirrors `LanguagePreMiddleware`, registered immediately after it). Verification = unit tests (`SimpleTestCase`, twin of `test_language_middleware.py`) + middleware-ordering smoke. |
| **T-03** | Evolving a live public endpoint (max_age 30d→1yr + DB write) | Medium | No research gate. Verification = update existing `test_preferred_city.py` + new auth DB-write tests. |
| **T-06** | Auth/session flow (`consent.py`) | Medium-High | No research gate (insert point is the existing `auth_login(request, user)` call, consent.py:285). Verification = login-sync tests. |
| **T-04 / T-05** | Public view filter behavior changes | Medium | Verification = integration tests (precedence, explicit-override, stale fallthrough). |
| **T-07** | UI surface on shared header | Low-Medium | Verification = header render test (AC-8) + manual smoke. |
| **FINAL-VERIFY** | Cross-cutting precedence / stale-cookie / logout / migration count | — | Full regression + AC walkthrough. |

## 4. Execution DAG

```
T-01 (schema + migration)
   │
   └──► T-02 (PreferredCityMiddleware + registration)
   │        │
   │        ├──► T-03 (write endpoint: 1yr + DB)        ┐
   │        ├──► T-04 (search() default filter)          │
   │        ├──► T-05 (listings() default filter)        ├── parallel batch
   │        ├──► T-06 (login sync hook)                  │   (after T-02)
   │        └──► T-07 (header city button + ctx proc)    ┘
   │                          │
   └──────────────────────────┴──► FINAL-VERIFY (regression + AC walkthrough)
```

- **Level 1:** T-01 (foundation).
- **Level 2:** T-02 (depends T-01). Defines `request.preferred_city` semantic contract consumed below.
- **Level 3 (parallel):** T-03, T-04, T-05, T-06, T-07 — each depends on T-01 + T-02, touches a
  disjoint module (endpoint / search / listings / consent / header+ctxproc), so they execute in
  parallel.
- **Level 4:** FINAL-VERIFY (depends all).

---

## Task Specifications

---

### T-01 — Add `User.preferred_city` FK (schema + migration)

**Priority:** high
**Depends on:** —
**Risk:** High (schema change, migration)

**Files:**
- `src/backend/apps/users/models.py` — target class `User`
- `src/backend/apps/users/migrations/0003_user_preferred_city.py` (generated)

**Semantic anchors:**
- Add `preferred_city` field to `User` (Django `AbstractUser`) using the existing field block
  convention (position alongside the other account-state fields; order is not semantic).
- No `UserProfile` model is created.

**Changes:**
- Add to `User`:
  ```python
  preferred_city = models.ForeignKey(
      "locations.City",
      null=True,
      blank=True,
      on_delete=models.SET_NULL,
      related_name="+",
      help_text="Buyer's preferred city for default catalog/search filtering (nullable; SET_NULL on city removal)",
  )
  ```
- Generate exactly one migration `0003_user_preferred_city` via `makemigrations users`.

**Acceptance criteria:**
- `User.preferred_city` is a nullable FK to `locations.City`, `on_delete=SET_NULL`, `related_name="+"`.
- `apps/users/migrations/0003_user_preferred_city.py` exists and contains only the FK addition
  (no data migration, no default).
- `makemigrations --check` reports zero new migrations after this task.
- Migration applies cleanly on the test DB; existing rows unaffected (nullable).
- `ruff check` and `basedpyright` pass on `apps/users/models.py`.
- No `UserProfile` model introduced anywhere in `apps/users/`.

---

### T-02 — `PreferredCityMiddleware` + registration

**Priority:** high
**Depends on:** T-01
**Risk:** High (MIDDLEWARE shared config, startup, new request-contract)

**Files:**
- `src/backend/apps/core/middleware/preferred_city.py` (new)
- `src/backend/config/settings/base.py` — `MIDDLEWARE` list
- `src/backend/apps/core/tests/test_preferred_city_middleware.py` (new; twin of `test_language_middleware.py`)

**Semantic anchors:**
- New class `PreferredCityMiddleware(MiddlewareMixin)` — mirrors `LanguagePreMiddleware`
  (`LanguagePreMiddleware` in `language.py` is the structural twin; follow its method layout).
- Register in `MIDDLEWARE` immediately **after** `apps.core.middleware.language.LanguagePreMiddleware`
  (base.py MIDDLEWARE list; `AuthenticationMiddleware` already ran above it).

**Changes (module-level constants):**
- `PREFERRED_CITY_COOKIE_NAME = "preferred_city"`
- `PREFERRED_CITY_COOKIE_MAX_AGE = 365 * 24 * 60 * 60`  (1 year)

**Changes (class):**
- `process_request`:
  - If `request.user.is_authenticated` and `request.user.preferred_city_id` is set →
    `request.preferred_city = request.user.preferred_city.slug` (DB wins; do not consult cookie).
  - Else → read `request.COOKIES.get(PREFERRED_CITY_COOKIE_NAME)`; if present and
    `City.objects.filter(slug=cookie_slug).exists()` → `request.preferred_city = cookie_slug`;
    otherwise `request.preferred_city = None` (record stale intent for cleanup).
- `process_response`:
  - If the cookie slug was validated-as-missing (stale) → `response.delete_cookie(PREFERRED_CITY_COOKIE_NAME)`.
  - No cookie write here (writes happen only in the explicit selection endpoint, T-03).
- Guard reads defensively (e.g. `getattr(request, "user", None)` / `hasattr`) consistent with the
  `language.py` session/user-ordering guard, so ordering is robust.

**Acceptance criteria:**
- `request.preferred_city` is a `str | None` slug for anonymous users (cookie) and authenticated users
  (DB-first).
- Middleware unit tests mirror `test_language_middleware.py` (`SimpleTestCase`, custom `HttpRequest`
  helper) covering: db-wins-over-cookie (AC-1), cookie-default-for-anon (AC-2), absent→None,
  stale-cookie→None + deletion intent (AC-4), no crash when `request.user` absent (ordering guard).
- `MIDDLEWARE` registers `PreferredCityMiddleware` immediately after `LanguagePreMiddleware`.
- `ruff check` / `basedpyright` pass.

---

### T-03 — Extend preferred-city write endpoint (1-year + DB persist)

**Priority:** high
**Depends on:** T-01, T-02
**Risk:** Medium (evolves live endpoint contract)

**Files:**
- `src/backend/apps/search/views/preferred_city.py` — function `set_preferred_city`
- `src/backend/apps/search/tests/test_preferred_city.py`

**Semantic anchors:**
- Replace the local `PREFERRED_CITY_COOKIE_MAX_AGE = 30 * 24 * 60 * 60` and the hardcoded
  `"preferred_city"` string with imports of `PREFERRED_CITY_COOKIE_NAME` / `PREFERRED_CITY_COOKIE_MAX_AGE`
  from `apps.core.middleware.preferred_city` (D-P1).
- In `set_preferred_city`, after a successful `City` validation, additionally persist
  `request.user.preferred_city` for authenticated users (R-11).

**Changes:**
- Import the two shared constants.
- `response.set_cookie(PREFERRED_CITY_COOKIE_NAME, slug, max_age=PREFERRED_CITY_COOKIE_MAX_AGE, httponly=True, samesite="Lax", secure=request.is_secure())`.
- If `request.user.is_authenticated`:
  ```python
  request.user.preferred_city = city
  request.user.save(update_fields=["preferred_city"])
  ```
  (resolve `city` instance from the validated slug; guard `DoesNotExist`),
  still returning `{"ok": true}` (200) regardless of auth state.
- Update the module docstring: cookie is HttpOnly, 1-year; DB write for authenticated buyers.

**Acceptance criteria:**
- POST with valid slug sets cookie value, `max-age=31536000`, `HttpOnly`, `SameSite=Lax`, `Secure` when `is_secure()`.
- POST with valid slug for an authenticated user persists `User.preferred_city` and returns 200.
- POST with valid slug for an anonymous user sets cookie only, returns 200.
- POST unknown/missing slug → 400 `{"error": "invalid_city"}`; GET → 405 (unchanged).
- `test_preferred_city.py` updated to assert the 1-year max-age and extended with an authenticated DB-write test.
- No behavioral regression for guests.

---

### T-04 — `search()` read-back as default city filter

**Priority:** high
**Depends on:** T-02
**Risk:** Medium (public view filter behavior)

**Files:**
- `src/backend/apps/search/views/search.py` — function `search`
- `src/backend/apps/search/tests/test_preferred_city.py` (extend) or a new focused integration test

**Semantic anchors:**
- The city-filter block reads `request.GET.get("city")` into `current_city`. Replace the "no explicit
  city" path to fall back to `request.preferred_city` (the middleware-resolved slug) as a **default**
  (R-05); explicit `?city=` always wins.
- Keep the existing `except City.DoesNotExist` branch as the second line of defense (R-10).

**Changes:**
- Compute:
  ```python
  explicit_city = request.GET.get("city")
  current_city = explicit_city or getattr(request, "preferred_city", None)
  ```
  Apply the same existing filter/`DoesNotExist` handling for `current_city`. Preserve the
  `suggested_city` did-you-mean behavior for explicit-but-unknown slugs unchanged.

**Acceptance criteria:**
- `/search/?q=...` with a resolved preferred city filters results to that city (AC-1, AC-2).
- `/search/?q=...&city=budva` filters to **budva**, ignoring preferred city (AC-3); does not rewrite the preference.
- Stale preferred city (unknown slug) → no city filter (all cities) (R-10 / AC-4).
- Context `current_city` reflects the effective filter value.
- Integration tests mirror `test_preferred_city.py` (`Client` + `pytest.mark.django_db`): db-wins,
  cookie-default, explicit-override, stale-fallthrough.

---

### T-05 — `listings()` read-back as default city filter

**Priority:** high
**Depends on:** T-02
**Risk:** Medium (public view filter behavior)

**Files:**
- `src/backend/apps/ads/views/listings.py` — function `listings`
- integration tests (colocated with existing listings tests; add to the search preferred-city test file or an ads test file following the `Client` pattern)

**Semantic anchors:**
- The city-filter block keys off `city_slug` (URL path) and `request.GET.get("city")`. Add a fallback
  to `request.preferred_city` (middleware slug) **only when neither the URL path `city_slug` nor the
  `?city=` param is present** (R-06, D-4/D-5). Keep the `except City.DoesNotExist` / did-you-mean
  path intact for explicit slugs.
- Context: `current_city` must reflect the effective active city so the filter badge/display is
  correct (R-06). `cities` for the header dropdown is supplied by the shared `header_context`
  (D-P3 / T-07); do **not** duplicate a `cities` queryset in `listings()` context.

**Changes:**
- Introduce an effective city slug resolved as `city_slug or request.GET.get("city") or getattr(request, "preferred_city", None)` for the *filtering* path, while keeping explicit (unknown) slugs flowing to the did-you-mean branch.
- Set `current_city` in context to the effective city slug (not only the URL slug).

**Acceptance criteria:**
- `/` and `/category/<slug>/` (no city, no `?city=`) filter to the preferred city when set (AC-2).
- `/city/<slug>/` path overrides preferred city (AC-3).
- Context `current_city` reflects the effective filter.
- Explicit unknown slug still shows did-you-mean suggestions; stale preferred city → no filter (AC-4).
- Integration tests cover path-override, default-fallback, and explicit-`?city=`-override.

---

### T-06 — Login reconciliation hook (guest cookie → account preference)

**Priority:** medium
**Depends on:** T-01, T-02
**Risk:** Medium-High (touches auth/session flow)

**Files:**
- `src/backend/apps/users/views/consent.py` — function `login_status` (call site `auth_login(request, user)`)
- login-sync tests (extend `apps/users/tests/test_account_state.py` or `test_login.py` per existing login-test patterns)

**Semantic anchors:**
- Insert reconciliation **immediately after** the `auth_login(request, user)` call in `login_status`
  (before the function returns 200), for the just-authenticated `user`.

**Changes:**
- Read `cookie_slug = request.COOKIES.get(PREFERRED_CITY_COOKIE_NAME)` (import the constant from
  `apps.core.middleware.preferred_city`).
- Validate the cookie slug against `City` (`City.objects.filter(slug=cookie_slug).exists()`); invalid → skip.
- If `user.preferred_city_id is None` and cookie is valid → `user.preferred_city = City(slug=cookie_slug)`;
  `user.save(update_fields=["preferred_city"])` (guest→registered migration, AC-6 / D-13 backfill direction).
- If `user.preferred_city_id` is already set → DB wins; **do not** overwrite DB from cookie
  (D-4/D-13). Cookie is **retained** (never deleted) as the anonymous fallback (R-09 / D-8).
- Log the reconciliation via the module `logger`.

**Acceptance criteria:**
- Guest with `preferred_city=podgorica` cookie + `User.preferred_city = NULL` logs in → DB backfilled to Podgorica, cookie retained (AC-6).
- User with existing `User.preferred_city = Podgorica` + cookie `budva` logs in → DB stays Podgorica (not overwritten).
- No exception when no cookie present; no behavior change to token consumption / session establishment.

---

### T-07 — Header city button + dropdown (shared context + template + JS)

**Priority:** medium
**Depends on:** T-02
**Risk:** Low-Medium (UI surface on shared header)

**Files:**
- `src/backend/apps/core/context_processors.py` — function `header_context`
- `src/backend/templates/components/header_catalog.html`
- header render test (e.g. `apps/core/tests/test_context_processors.py` + a template render assertion)

**Semantic anchors:**
- Extend `header_context` to add `preferred_city_display` and `cities` (D-P3), so every
  `header_catalog.html` include (list + detail) has both — reusing the existing
  `Category.objects.root_nodes()` pattern for a small DB query.
- In `header_catalog.html`, add the city button into the search/top row (vanilla JS toggle with
  `data-*` attributes per Spec_014 §7.1 — no `hx-on`, HTMX 1.9.12). Reuse the existing autocomplete
  click-handler pattern and `getCsrf()` (`{% url 'search:preferred_city' %}`).

**Changes (context processor):**
- `preferred_city_display`: from `request.preferred_city` slug → localized city name via
  `City.get_name()`; when `None`, the country-wide label (default "Вся страна" — Q-2 recommended
  default). Import `City` locally like `Category`.
- `cities`: `list(City.objects.order_by("name"))` (Montenegro cities for the dropdown).

**Changes (template):**
- Render `📍 <preferred_city_display> ▾` button with a dropdown listing `cities` (localized names).
- Dropdown item click: `POST /api/preferred-city/` (slug) using the existing fetch + `X-CSRFToken`
  pattern, then `window.location.href = '/city/<slug>/'`.
- Vanilla toggle open/close + click-outside + Escape; all styling via Tailwind utility classes
  (no custom CSS — Spec_007).

**Acceptance criteria:**
- Any catalog/detail page renders the button with the effective preferred city (localized) or the
  country-wide label when unset (AC-8).
- Dropdown lists Montenegro cities; selecting a city persists (endpoint) and navigates to `/city/<slug>/`.
- `BOT_USERNAME` is not referenced directly in the template (still via `bot_username` context).
- Header render test asserts presence of the badge and city list; `header_context` unit test asserts
  `preferred_city_display` / `cities` keys for a slug, a None, and a stale slug.

---

### FINAL-VERIFY — End-to-end regression + acceptance-criteria walkthrough

**Priority:** high
**Depends on:** T-01, T-02, T-03, T-04, T-05, T-06, T-07
**Risk:** — (verification only; no production code changes)

**Purpose:** Dedicated multi-stage verification for a schema + auth + cross-cutting middleware feature.

**Verification steps (test DB up: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db`; run via the `test` Compose service per `.ai/context/commands.md`):**
1. **Migrations:** `makemigrations --check` clean; exactly one `users.0003_user_preferred_city`; `migrate` applies on the test DB (AC-9).
2. **Unit:** run `test_preferred_city_middleware.py`, `test_context_processors.py`, `test_language_middleware.py` (regression guard for the twin).
3. **Integration:** preferred-city write (T-03), search/listings read-back (T-04/T-05), login sync (T-06).
4. **Full regression:** run the `apps.search`, `apps.ads`, `apps.users`, `apps.core` test suites to confirm no collateral from schema/middleware/endpoint/context changes.
5. **AC walkthrough:** AC-1 (db-wins), AC-2 (guest cookie), AC-3 (explicit override, no rewrite), AC-4 (stale cookie cleared), AC-5 (selection persists auth+guest), AC-6 (login migrates), AC-7 (logout retains cookie), AC-8 (button renders), AC-9 (single migration, no `UserProfile`), AC-10 (`preferred_city` ≠ `SavedSearch.city` — confirm saved-search alert scope unchanged).
6. **Lint/type:** `ruff check` and `basedpyright` across the touched trees.
7. **Out-of-scope guard:** no bot-process change, no `UserProfile`, no `makemigrations --check` deltas beyond the one migration.

**Exit criteria:** all tests green, all AC-1…AC-10 satisfied, static checks clean.

---

## Notes for implementors

- Use semantic anchors only; never line numbers.
- All comments/log/docstrings/errors in English (project rule 1).
- `StrEnum` for domain constants; cookie name stays a module-level constant (Spec §7.3).
- `cities` in the dropdown is a ~30-row Montenegro list — a single small query is acceptable, matching
  the existing `header_context` precedent.
- The header badge is populated server-side (cookie is HttpOnly); never read `document.cookie`.
- Fire-and-forget fetch race (Spec §5.2 / §12) is out of scope — do not add `await`.
