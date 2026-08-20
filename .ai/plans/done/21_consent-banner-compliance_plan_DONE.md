---
id: 21_consent-banner-compliance-plan
domain: implementation-plan
source_spec: .ai/problems/21_consent-banner-compliance_spec.md
spec_status: Approved-for-implementation-planning
priority: High
status: PLANNED
date: 2026-08-20
---

# Plan 21 — Consent Banner & GDPR/ePrivacy Compliance Redress

Transformation of **Spec 21** (`.ai/problems/21_consent-banner-compliance_spec.md`) into a
dependency-aware implementation DAG. The spec identifies 9 defects (D1–D9) across consent
views, cookie handling, context processors, banner UX, analytics script loading, and audit
logging, organized into 10 conceptual tasks (T1–T10). This plan reorganizes them into
implementation-sequenced tasks with explicit dependencies, risk gates, and verification.

> Spec 21's conceptual tasks T1–T10 are mapped below into implementation-sequenced tasks.
> Mapping: **T1→T-01, T2→T-02, T3→T-03, T4→T-04, T5→T-05, T6→T-06, T7→T-07, T8→T-08,
> T9→T-09, T10→T-10**. T-03 must precede T-04 (context processor reads correct DB state).
> T-02 must precede T-05 and T-06 (views must accept anonymous POST before cookie-based
> anonymous consent and granular categories can be built on top). T-07 must precede T-06
> (ConsentRecord model must exist before views create records). T-10 is deferred to the
> end. See execution DAG in §5.

## 1. Statement of scope

Implement GDPR/ePrivacy compliance for the consent banner across 9 defects:

| # | Defect | Fix |
|---|--------|-----|
| D1 | `/privacy/` returns 404 | Create public privacy policy page |
| D2 | Accept/decline views accept GET (CSRF risk) | Add `@require_POST` |
| D3 | `consent_given` cookie is write-only | Read cookie in context processor for anonymous state |
| D4 | Banner hidden for anonymous users | Show banner to anonymous; set cookie for anonymous consent |
| D5 | `consent_shown` missing on 4 of 7 views | Context processor provides it globally; remove per-view passing |
| D6 | `give_consent()` doesn't clear decline state | Clear `is_declined`, restore `ads_auto_publish` |
| D7 | Plausible/GLightbox scripts load unconditionally | Server-side template-gated loading |
| D8 | No server-side consent audit log | `ConsentRecord` model + migration + admin |
| D9 | Generic banner text | Granular categories (Essential/Analytics/Preferences) |

**In scope:** `apps/users/views/consent.py`, `apps/users/services/deletion.py`,
`apps/core/context_processors.py` (new `apps/users/context_processors.py`),
`config/urls.py`, `config/settings/base.py`, `templates/components/consent_banner.html`,
`templates/privacy.html` (new), `apps/core/views.py`, all 9 templates with Plausible + 1
template with GLightbox, and test files.

**Out of scope:** Bot-side consent prompt (PO-07 — web banner covers bot), full CMP
integration, DSAR portal, multi-language consent text beyond RU/bs/en.

## 2. Current-state vs. gaps (verified)

| Concern | State | Evidence |
|---|---|---|
| `/privacy/` route exists | **Gap (T-01)** | `config/urls.py` — no `/privacy/` path; `consent_banner.html:13` links to it |
| `consent_accept` has `@require_POST` | **Gap (T-02)** | `consent.py:50-51` — has `@login_required` but NOT `@require_POST` |
| `consent_decline` has `@require_POST` | **Gap (T-02)** | `consent.py:79-80` — has `@login_required` but NOT `@require_POST` |
| `consent_withdraw` has `@require_POST` | OK | `consent.py:109-110` — has both `@login_required` and `@require_POST` |
| `consent_given` cookie read anywhere | **Gap (D3, T-04/T-05)** | Cookie set in 3 places (lines 68-74, 98-104, 129-135) but never read; `is_consent_given()` (line 140-159) checks only DB |
| `is_consent_given` returns True for anonymous | **Gap (D4, T-05)** | `consent.py:153-155` — anonymous → True (banner hidden) |
| `consent_shown` passed by all views | **Gap (D5, T-04)** | Only 3 views pass it: `dashboard.py:85`, `listings.py:81,435`, `search.py:175`; 4 views missing it (cabinet hub, settings, seller_dashboard, moderation_dashboard) |
| `give_consent` clears decline state | **Gap (D6, T-03)** | `deletion.py:224-247` — only sets `consent_given_at`; does NOT clear `is_declined` or restore `ads_auto_publish` |
| Plausible script gated by consent | **Gap (D7, T-06b)** | 9 templates: `ads/list.html`, `ads/detail.html`, `ads/dashboard.html`, `ads/edit.html`, `analytics/seller_dashboard.html`, `analytics/moderation_dashboard.html`, `cabinet/hub.html`, `cabinet/favorites.html`, `cabinet/saved_searches.html`, `cabinet/search_history.html`, `cabinet/saved_search_edit.html`, `cabinet/settings.html` — all use `{% if PLAUSIBLE_HOST %}` with no consent gate |
| GLightbox script gated | **Gap (D7, T-06b)** | `ads/detail.html:112-124` — loads unconditionally |
| `ConsentRecord` model exists | **Gap (D8, T-07)** | No consent audit model; no `consent_records` table |
| Banner text lists cookies/third parties | **Gap (D9, T-06a)** | `consent_banner.html:9-11` — generic text, no cookie table or third-party listing |
| `consent_given` cookie has `secure=True` | **Gap (minor)** | `consent.py:68-74` — has `httponly=True`, `samesite="Lax"`, but no `secure=True` |
| `lang_pref` cookie consent-gated | **Gap (T-06c)** | `language_switcher.html:58-77` — JS sets `lang_pref` unconditionally |
| `preferred_city` cookie consent-gated | **Gap (T-06c)** | `preferred_city.py:57-64` — sets cookie unconditionally |
| Banner guard on all 7 templates | OK | All 7 templates have `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard (correcting researcher's report) |
| Pydantic at consent boundary | **Gap (D-PYDANTIC)** | Pydantic v2.13.4 available transitively via aiogram, but NOT listed as direct dependency in `pyproject.toml` |

## 3. Planning decisions (resolved here, not new requirements)

- **D-COOKIES — Structured consent cookie.** The `consent_given` cookie value changes
  from `"true"`/`"declined"`/`"withdrawn"` to `"accepted"`/`"declined"`/`"withdrawn"`
  (matching `ConsentChoice` StrEnum). Two additional category cookies are introduced:
  `consent_analytics` (`"true"`/`"false"`) and `consent_preferences` (`"true"`/`"false"`).
  All three use `max_age=12 months`, `httponly=True`, `samesite="Lax"`, `secure=True`.
  The context processor reads all three for anonymous users. *Grounds: Spec §5 Task 5/6,
  PO-05 (12-month expiry), constraint 9.2 (StrEnum).*

- **D-PYDANTIC — Add pydantic as direct dependency.** Pydantic v2.13.4 is available
  transitively (via `aiogram`) but is not listed as a direct dependency. Per constraint
  C-9.2 ("Pydantic at boundaries — Consent form submission should validate via Pydantic
  DTO"), `uv add pydantic` must be run before T-06 (which introduces granular category
  form parsing). For T-01–T-05 (simple accept/decline via form POST), Django's built-in
  CSRF + `request.POST` suffices; Pydantic is used starting T-06.
  *Grounds: project rule 10, constraint C-9.2, PO-04 (granular categories in T-06).*

- **D-SCRIPT — Server-side template gating for scripts.** The spec (Task 6c) suggests
  "a small inline script that checks cookies before injecting `<script>` tags." However,
  the HTMX MPA architecture does full-page reloads on consent actions, and the context
  processor can read consent cookies server-side. **Decision: use server-side Django
  template conditionals** (`{% if consent_analytics and PLAUSIBLE_HOST %}`) instead of
  inline JS. This is simpler, more secure, and follows the existing
  `{% if PLAUSIBLE_HOST %}` pattern. No inline JS required for script gating.
  *Grounds: Spec §5 Task 5 ("non-essential scripts not loaded before consent");
  architecture constraint C-3 (HTMX MPA, full-page reloads); existing template pattern
  for `PLAUSIBLE_HOST`.*

- **D-CONTEXT — Context processor owns consent logic.** The new
  `apps/users/context_processors.py:consent_state` function implements all consent-state
  logic (reading DB for authenticated, cookies for anonymous). The existing
  `is_consent_given(request)` function in `consent.py` becomes **deprecated** — the
  context processor replaces its role. T-04 removes per-view `consent_shown` passing by
  3 views and stops importing `is_consent_given` from `apps.users.views.consent`. Tests
  that patched `is_consent_given` at its old location (test_listings_context.py,
  test_detail_context.py) must update their patch targets.
  *Grounds: Spec §5 Task 4; Architecture §4 (context processors pattern).*

- **D-RECORDS — ConsentRecord creation in views, not services.** `ConsentRecord` rows
  are created in the consent views (HTTP entry point), not in the service layer
  (`give_consent`/`decline_consent`). This preserves separation of concerns: services
  mutate domain state (User model), views handle HTTP + audit logging. A
  `record_consent_action(...)` service helper is added to `apps/users/services/` for
  the model creation logic.
  *Grounds: project rule 3 (separation of concerns), Spec §4.3 (audit log records
  timestamp, IP, UA — HTTP-layer data).*

- **D-T08 — T-08 is defense-in-depth.** Cookie `max_age=12 months` (T-05) inherently
  causes browser-side cookie expiry after 12 months, automatically re-showing the
  banner. T-08 adds an explicit server-side timestamp check in the context processor
  as defense-in-depth (handles tampered future-expiry cookies). T-08 is **optional**
  for compliance but recommended for robustness.
  *Grounds: Spec §5 Task 5 ("cookie persists for 12 months") + Task 8
  ("context processor checks if cookie is older than 12 months").*

- **D-T09 — Preference center as footer component.** The "Cookie settings" footer link
  reopens the consent banner. Since the banner is server-rendered (not a modal), the
  footer link navigates to the current page with a `?ref=preferences` parameter that
  the context processor reads to force-show the banner. Alternatively, a small inline
  script scrolls to and highlights the banner. This avoids a new JS modal component.
  *Grounds: Spec §5 Task 9; PR-07; minimal-JS constraint.*

- **D-ENUMS — Consent enums in `apps/core/enums.py`.** Following the existing pattern
  (`AdStatus`, `AnalyticsEventType`, etc. all live in `apps/core/enums.py`),
  `ConsentChoice(StrEnum)` and `CookieCategory(StrEnum)` are added there and re-exported
  via `apps.core.enums.__all__`.
  *Grounds: project rule 10, constraint C-9.1 (StrEnum), existing convention.*

- **D-NO-RESEARCH — No researcher-agent gate.** All architectural forks are resolved
  internally (cookie format, script gating approach, Pydantic dependency, record
  creation location). No external libraries are introduced; no schema migration
  complexity beyond a single new model. Researcher-agent invocation is not warranted
  (proportional to this well-understood compliance change set).

## 4. Risk assessment & gates

| Task | Risk trigger | Severity | Gate |
|---|---|---|---|
| **T-01** | New public URL on the browsing surface | Low | None. Verification = HTTP 200, no login required. |
| **T-02** | Adds `@require_POST` to consent accept/decline; existing GET tests break | Low-Medium | Existing `test_consent.py` must update GET→POST. Code-review gate confirms no GET-based consent actions remain. |
| **T-03** | Service-layer change to `give_consent`; affects accept-after-decline flow | Medium | `test_deletion.py` (if exists) or service tests verify `is_declined=False`, `ads_auto_publish=True` after accept. Regression on normal accept flow. |
| **T-04** | Context processor changes how `consent_shown` is provided; 3 views stop passing it; tests patching `is_consent_given` break | Medium | Test patches must be repointed to the context processor function. Regression: all templates still receive `consent_shown`. |
| **T-05** | Removes `@login_required` from consent views; anonymous users can now set cookies; cookie format changes | Medium-High | `test_consent.py` updated for anonymous POST. New tests for anonymous consent. `secure=True` must not break test client (it doesn't — browser flag only). |
| **T-06** | Restructures consent flow (categories, structured cookies, script gating); 10 templates change | High | Template-guard test extended. Script-gating test verifies scripts absent before consent, present after. Pydantic DTO validation tested. |
| **T-07** | New model + migration; two-process startup (web + bot) must apply migration | Low | `makemigrations --check` confirms exactly one new migration. Migration applied before both processes start (existing constraint C-1). |
| **T-08** | Re-prompt logic in context processor | Low | Test: consent cookie timestamp > 12 months → banner shown. |
| **T-09** | Footer link on all pages | Low | Footer present on all templates. Cookie-settings link reopens banner. |
| **T-10** | Test suite alignment | Low | All consent-related tests green. |
| **FINAL-VERIFY** | Cross-cutting regression across browsing + consent + tests | — | Dedicated multi-stage verification. |

**Release gate (D-2):** T-02 + T-05 must ship together — adding `@require_POST` while
views still require login means anonymous users get 401/405 instead of consent; removing
`@login_required` without `@require_POST` means anonymous consent via GET (CSRF). Both
changes are on the same views (`consent_accept`, `consent_decline`); review gate confirms
both land in one changeset.

**Security gate (D-3):** After T-05, anonymous consent sets cookies only (no DB mutation).
Review gate confirms no DB writes occur for unauthenticated requests on consent views.

**Cookie-format gate (D-COOKIES):** The context processor (T-04) must handle BOTH the
old cookie format (`"true"`) and new format (`"accepted"`) during the transition window,
since existing returning users may have old cookies. This is verified in T-05's tests.

## 5. Execution DAG

```
Level 1  (parallel — independent, disjoint modules)
  ├─ T-01  Create /privacy/ page              [apps/core/views.py, templates/privacy.html, apps/core/urls.py]
  ├─ T-02  @require_POST + remove @login_required   [apps/users/views/consent.py]
  ├─ T-03  Fix give_consent()                   [apps/users/services/deletion.py]
  └─ T-07  ConsentRecord model + migration     [apps/users/models.py, apps/core/enums.py, apps/users/services/, apps/users/admin.py]

Level 2  (parallel — depend on Level 1; disjoint files)
  ├─ T-04  Consent context processor             [apps/users/context_processors.py, config/settings/base.py]
  │         depends_on: T-03
  ├─ T-06a Update banner text (granular UI)      [templates/components/consent_banner.html]
  │         depends_on: T-02
  └─ T-07b Pydantic DTO + consent recording svc  [apps/users/schemas.py, apps/users/services/consent_record.py, pyproject.toml]
          depends_on: T-07

Level 3  (parallel — depend on Level 2)
  ├─ T-05  Anonymous consent + 12-month cookie   [apps/users/views/consent.py, apps/users/context_processors.py]
  │         depends_on: T-02, T-04
  ├─ T-06b Script gating (Plausible, GLightbox)   [10 template files]
  │         depends_on: T-02, T-05, T-04
  └─ T-06c Preference-cookie gating             [templates/components/language_switcher.html, apps/search/views/preferred_city.py]
          depends_on: T-02, T-05, T-04

Level 4  (depend on Level 3)
  ├─ T-08  12-month re-prompt (defense-in-depth) [apps/users/context_processors.py]
  │         depends_on: T-04, T-05
  ├─ T-09  Cookie preference center (footer)      [templates/components/footer.html (or base), apps/core/views.py]
  │         depends_on: T-04, T-05
  └─ T-06d ConsentRecord creation in views       [apps/users/views/consent.py]
          depends_on: T-02, T-05, T-07, T-07b

Level 5  (depend on Level 4)
  └─ T-10  Test alignment + new coverage          [5 test files]

Level 6  (verification — no prod code)
  └─ FINAL-VERIFY  regression + acceptance-criteria walkthrough
          depends_on: T-01, T-02, T-03, T-04, T-05, T-06a–d, T-07, T-07b, T-08, T-09, T-10
```

- **T-01, T-02, T-03, T-07** share no modules → parallel.
- **T-04** shares no files with T-01/T-02/T-03/T-07 → parallel at Level 2. Depends on T-03
  (context processor logic must match corrected `give_consent` DB state).
- **T-06a** (banner template) is independent of T-04 but depends on T-02 (views must
  accept the new category form data). Ships parallel with T-04 at Level 2.
- **T-07b** (Pydantic DTO + consent recording service) depends on T-07 (model must exist)
  and is used by T-06d. Ships at Level 2.
- **T-05** depends on T-02 (views accept anonymous) and T-04 (context processor reads
  cookies). Modifies consent views + context processor.
- **T-06b/T-06c** depend on T-05 (anonymous state available) and T-04 (context processor
  provides category flags). Touch template files only (no conflict with view changes).
- **T-08** extends the context processor's expiry check; depends on T-04, T-05.
- **T-09** adds a footer link; depends on T-04/T-05 (banner visibility logic stable).
- **T-06d** wires ConsentRecord creation into the consent views; depends on T-07b (service
  exists) and T-05 (anonymous + authenticated state handled).
- **T-10** is gated on the full critical path.
- **FINAL-VERIFY** is gated on everything; it is a verification-only task.

---

## Task Specifications

---

### T-01 — Create `/privacy/` Public Policy Page

**Priority:** high | **Depends on:** — (Level 1) | **Risk:** Low

**Files:**
- `src/backend/apps/core/views.py` — new function `privacy_policy`
- `src/backend/templates/privacy.html` — new template
- `src/backend/apps/core/urls.py` — add route `path("privacy/", views.privacy_policy, name="privacy")`

**Semantic anchors:**
- `apps/core/urls.py` `urlpatterns` list — append the privacy route.
- `apps/core/views.py` — add `def privacy_policy(request: HttpRequest) -> HttpResponse`
  that renders `templates/privacy.html` with no auth requirement.
- Template `templates/privacy.html` — extend base layout, contain a cookie declaration
  table matching §4.4, third-party disclosures (Telegram, Google Translate, Plausible),
  processing purposes, legal bases, user rights, controller contact (Telegram deep-link),
  and 30-day erasure policy.

**Changes:**
1. Add `privacy_policy` view to `apps/core/views.py` — no decorator (public, unauthenticated).
2. Add route to `apps/core/urls.py`.
3. Create `templates/privacy.html` with content from Spec §5 Task 1 acceptance criteria.

**Acceptance criteria:**
- `GET /privacy/` returns HTTP 200.
- No login required (anonymous accessible).
- Page contains a cookie table listing all 5 cookies from §4.4 (`sessionid`,
  `csrftoken`, `consent_given`, `lang_pref`, `preferred_city`) with Purpose / Essential /
  Consent-Gated columns.
- Page lists third-party disclosures: Telegram (login + contact deep-links), Google
  Translate (ad text), Plausible (analytics).
- `ruff check` + `basedpyright` pass.

---

### T-02 — Harden Consent Views (POST-only + anonymous access)

**Priority:** high | **Depends on:** — (Level 1) | **Risk:** Low-Medium

**Files:**
- `src/backend/apps/users/views/consent.py` — decorators on `consent_accept`, `consent_decline`
- `src/backend/apps/users/tests/test_consent.py` — update GET→POST

**Semantic anchors:**
- `consent_accept` function (line 50-51) — add `@require_POST` decorator (after `@login_required`).
- `consent_decline` function (line 79-80) — add `@require_POST` decorator (after `@login_required`).
- `consent_withdraw` (line 109) — already has `@require_POST`; no change needed.
- `@require_POST` is already imported at `consent.py:30`.

**Changes:**
1. Add `@require_post` to `consent_accept` and `consent_decline` (stacked with
   existing `@login_required`).
2. Update `test_consent.py`:
   - `test_accept_requires_authentication`: change `client.get()` → `client.post()`.
     With `@login_required` + `@require_POST`, anonymous POST → 302 (redirect to login).
   - `test_accept_sets_consent_given_at`: change `client.get()` → `client.post()`.
   - `test_accept_sets_consent_cookie`: change `client.get()` → `client.post()`.
   - Same pattern for `test_decline_*`.
3. `test_withdraw_*` tests already use `client.post()` — no change.

**Acceptance criteria:**
- `GET /consent/accept/` → 405 Method Not Allowed.
- `GET /consent/decline/` → 405 Method Not Allowed.
- `POST /consent/accept/` (authenticated) → 302 redirect to `/dashboard/` (unchanged).
- `POST /consent/decline/` (authenticated) → 302 redirect to `/dashboard/` (unchanged).
- `ruff check` + `basedpyright` pass on `consent.py`.

---

### T-03 — Fix `give_consent()` to Clear Decline State

**Priority:** high | **Depends on:** — (Level 1) | **Risk:** Medium

**Files:**
- `src/backend/apps/users/services/deletion.py` — `give_consent` function (lines 224-247)

**Semantic anchors:**
- Function `give_consent(user)` — the single `user.save(update_fields=[...])` call at
  `deletion.py:245`. Expand the `update_fields` list and add the clearing assignments
  before the save.

**Changes:**
1. In `give_consent`, before the `user.save()` call, add:
   ```python
   user.is_declined = False
   user.ads_auto_publish = True
   user.consent_revoked_at = None
   ```
2. Expand `update_fields` to: `["consent_given_at", "is_declined", "ads_auto_publish",
   "consent_revoked_at"]`.
3. Update the docstring to document the clearing behavior.

**Acceptance criteria:**
- After `give_consent(user)` following a `decline_consent(user)`:
  - `user.is_declined == False`
  - `user.ads_auto_publish == True`
  - `user.consent_given_at is not None`
  - `user.consent_revoked_at is None` (was already None for decline, but restored if
    previously withdrawn)
- Single `update_fields` save (no N+1).
- Existing `test_deletion.py` (if present) or service tests pass.

---

### T-04 — Consent Context Processor

**Priority:** high | **Depends on:** T-03 (Level 2) | **Risk:** Medium

**Files:**
- `src/backend/apps/users/context_processors.py` — **new file**
- `src/backend/config/settings/base.py` — add to `TEMPLATES[0]["OPTIONS"]["context_processors"]`
- `src/backend/apps/ads/views/dashboard.py` — remove `consent_shown` + import
- `src/backend/apps/ads/views/listings.py` — remove `consent_shown` + import (2 locations: lines 81, 435)
- `src/backend/apps/search/views/search.py` — remove `consent_shown` + import

**Semantic anchors:**
- `config/settings/base.py` `TEMPLATES[0]["OPTIONS"]["context_processors"]` list (line 133-141)
  — append `"apps.users.context_processors.consent_state"`.
- `dashboard.py` import `from apps.users.views.consent import is_consent_given` (line 12) and
  context key `"consent_shown"` (line 85).
- `listings.py` same import + context key at lines 81 and 435.
- `search.py` same import (line 18) + context key (line 175).

**Changes:**
1. Create `apps/users/context_processors.py` with function `consent_state(request)`:
   ```python
   def consent_state(request):
       user = request.user
       cookie = request.COOKIES.get("consent_given", "")
       
       # Authenticated: check DB state
       if user.is_authenticated:
           consent_shown = (
               user.consent_given_at is not None
               or user.is_declined
               or user.consent_revoked_at is not None
           )
           consent_analytics = user.consent_given_at is not None
           consent_preferences = user.consent_given_at is not None
       else:
           # Anonymous: check cookie (backward-compatible: "true" or "accepted")
           acted = cookie in ("true", "accepted", "declined", "withdrawn")
           consent_shown = acted
           consent_analytics = cookie == "accepted"
           consent_preferences = cookie == "accepted"
       
       # Soft-deleted users: banner already guarded in templates; consent_shown = True
       if user.is_authenticated and user.is_deleted:
           consent_shown = True
       
       return {
           "consent_shown": consent_shown,
           "consent_analytics": consent_analytics,
           "consent_preferences": consent_preferences,
       }
   ```
   Note: handles both old cookie format (`"true"`) and new (`"accepted"`) per D-COOKIES.
2. Register in `config/settings/base.py` TEMPLATES context_processors.
3. Remove `consent_shown` from context dict and remove `is_consent_given` import in
   `dashboard.py`, `listings.py`, `search.py`.
4. Delete or deprecate `is_consent_given` in `consent.py` (note: `consent_withdraw` view
   still imports nothing from it; check for other importers first via grep).

**Acceptance criteria:**
- All templates listed in `test_templates.py` `_TEMPLATES_WITH_BANNER` receive
  `consent_shown` without per-view passing.
- `dashboard.py`, `listings.py`, `search.py` no longer import `is_consent_given`.
- Context processor provides `consent_shown`, `consent_analytics`, `consent_preferences`.
- Authenticated user with `consent_given_at` set → `consent_shown=True`.
- Authenticated user with no consent state → `consent_shown=False`.
- Anonymous with `consent_given=accepted` cookie → `consent_shown=True`.
- Anonymous without cookie → `consent_shown=False` (banner shown — D4 fix).
- `ruff check` + `basedpyright` pass.

---

### T-05 — Universal Banner: Anonymous Consent + 12-Month Cookie

**Priority:** high | **Depends on:** T-02, T-04 (Level 3) | **Risk:** Medium-High

**Files:**
- `src/backend/apps/users/views/consent.py` — `consent_accept`, `consent_decline`, `consent_withdraw`

**Semantic anchors:**
- `consent_accept` (line 50-76) — remove `@login_required`, add anonymous branch,
  update cookie value from `"true"` to `"accepted"`, add `secure=True`, extend to
  set category cookies.
- `consent_decline` (line 79-106) — same treatment with cookie value `"declined"`.
- `consent_withdraw` (line 109-137) — add `secure=True`, update cookie value.
  (Already has `@require_POST`; `@login_required` is correct — withdrawal requires auth.)
- `CONSENT_COOKIE_MAX_AGE` (line 47) — change from `365 * 24 * 60 * 60` to a named constant
  `CONSENT_COOKIE_MAX_AGE_DAYS = 365` with a clarifying comment, or keep the value but
  add explicit 12-month note.

**Changes:**
1. Remove `@login_required` from `consent_accept` and `consent_decline`.
2. For `consent_accept`:
   - If authenticated: call `give_consent(user)` (T-03 fix), set cookie `consent_given=accepted`
     with `max_age=CONSENT_COOKIE_MAX_AGE, httponly=True, samesite="Lax", secure=True`,
     set `consent_analytics=true` and `consent_preferences=true` cookies.
   - If anonymous: only set cookies (no DB write). `consent_given=accepted`,
     `consent_analytics=true`, `consent_preferences=true`.
   - Redirect to "/" for anonymous, "/dashboard/" for authenticated.
3. For `consent_decline`:
   - If authenticated: call `decline_consent(user)`, set `consent_given=declined` cookie
     with `consent_analytics=false`, `consent_preferences=true` (preferences are
     still allowed — only analytics is declined per PO-02).
   - If anonymous: only set cookies.
   - Redirect to "/" for anonymous, "/dashboard/" for authenticated.
4. For `consent_withdraw`: keep `@login_required` (withdrawal is account-level),
   add `secure=True`, update cookie to `consent_revoked_at` context.
5. Add `secure=True` to all `set_cookie` calls.

**Note on `consent_withdraw` + `@login_required`:** Withdrawal is an account deletion
action — it requires a User object. Anonymous users cannot withdraw. `@login_required`
stays; `@require_POST` already exists. This is correct per PO-02 (decline = cookie
rejection only; withdraw = account deletion).

**Acceptance criteria:**
- Anonymous `POST /consent/accept/` → 302 to `/`, sets `consent_given=accepted` +
  `consent_analytics=true` + `consent_preferences=true` cookies (all `secure=True`).
- Anonymous `POST /consent/decline/` → 302 to `/`, sets `consent_given=declined` +
  `consent_analytics=false` + `consent_preferences=true` cookies.
- Authenticated accept → calls `give_consent` (with D6 fix), redirects to `/dashboard/`.
- All cookies have `max_age=31536000` (365 days = 12 months).
- After accepting, `GET /` does not show the consent banner (cookie read by context processor).
- `ruff check` + `basedpyright` pass.

---

### T-06a — Update Banner Text with Granular Categories

**Priority:** medium | **Depends on:** T-02 (Level 2) | **Risk:** Low

**Files:**
- `src/backend/templates/components/consent_banner.html`

**Semantic anchors:**
- The `<p>` text block (lines 8-11) — replace with granular category description.
- The `Accept` / `Decline (Browse-only)` buttons (lines 18-35) — add category checkboxes
  and an "Accept all" / "Reject all" option.
- The `/privacy/` link (line 13) — keep.

**Changes:**
1. Replace the generic paragraph with a list of 3 categories:
   - **Essential** (always on) — session, CSRF cookies.
   - **Analytics** (Plausible) — traffic analytics.
   - **Preferences** (lang/city) — language and city selection.
2. Replace the two-button layout with:
   - Three checkboxes for categories (Essential disabled+checked, Analytics + Preferences
     toggleable).
   - "Accept all" button (POST with all categories=true).
   - "Reject non-essential" button (POST with analytics=false, preferences=true or false
     per PO-02 — preferences retained since they're needed for basic UX).
   - "Manage" button (opens expanded view — see T-09 for preference center).
3. Form fields: `choice` (accepted/declined), `analytics` (true/false),
   `preferences` (true/false), `consent_version` (hidden field).

**Acceptance criteria:**
- Banner shows 3 category labels with descriptions.
- "Accept all" and "Reject non-essential" buttons at equal visual prominence.
- `/privacy/` link present.
- `ruff check` (template syntax via Django check) passes.

---

### T-06b — Script Gating (Plausible + GLightbox)

**Priority:** medium | **Depends on:** T-02, T-05, T-04 (Level 3) | **Risk:** Medium

**Files:**
- 9 templates with Plausible: `ads/list.html`, `ads/detail.html`, `ads/dashboard.html`,
  `ads/edit.html`, `analytics/seller_dashboard.html`, `analytics/moderation_dashboard.html`,
  `cabinet/hub.html`, `cabinet/favorites.html`, `cabinet/saved_searches.html`,
  `cabinet/search_history.html`, `cabinet/saved_search_edit.html`, `cabinet/settings.html`
- 1 template with GLightbox: `ads/detail.html`

Wait — recount: grep found 12 Plausible occurrences (including admin template) +
1 GLightbox in `ads/detail.html`.

**Semantic anchors:**
- Each template's `<head>` block containing `{% if PLAUSIBLE_HOST %}<script defer ...` —
  replace with `{% if consent_analytics and PLAUSIBLE_HOST %}<script defer ...`.
- `ads/detail.html` GLightbox script block (lines 112-124) — wrap in
  `{% if consent_analytics %}`.

> **Note on GLightbox:** GLightbox is a gallery UI enhancement for ad images. Per D-SCRIPT,
> it is gated behind `consent_analytics` (treated as non-essential). Users without consent
> can still view images via direct links (the `<a href>` remains in the HTML).

**Changes:**
1. In each of the 12 templates, change:
   `{% if PLAUSIBLE_HOST %}` → `{% if consent_analytics and PLAUSIBLE_HOST %}`
2. In `ads/detail.html`, wrap the GLightbox `<script>` and initialization block in
   `{% if consent_analytics %}`.

**Acceptance criteria:**
- Before consent (anonymous, no cookie): Plausible and GLightbox scripts NOT in response HTML.
- After consent (`consent_given=accepted` cookie): scripts present.
- `consent_analytics` provided by context processor (from T-04).
- No JS errors when scripts are absent (GLightbox init block is fully wrapped).

---

### T-06c — Preference-Cookie Gating (lang_pref, preferred_city)

**Priority:** medium | **Depends on:** T-02, T-05, T-04 (Level 3) | **Risk:** Low-Medium

**Files:**
- `src/backend/templates/components/language_switcher.html` — JS `setCookie` call (line 112)
- `src/backend/apps/search/views/preferred_city.py` — `set_preferred_city` cookie setting (line 57-64)

**Semantic anchors:**
- `language_switcher.html` `setCookie(COOKIE_NAME, ...)` call (line 112) — guard behind
  `{% if consent_preferences %}`.
- `preferred_city.py` `response.set_cookie(PREFERRED_CITY_COOKIE_NAME, ...)` (line 57) —
  guard behind checking consent.

**Changes:**
1. In `language_switcher.html`: wrap the `setCookie` call (or the entire JS cookie-setting
   logic) in a `{% if consent_preferences %}` template conditional. If the user hasn't
   consented to preferences, the lang_pref cookie is not set (language falls back to
   the `?lang=X` URL parameter / browser default).
2. In `preferred_city.py`: before `response.set_cookie(PREFERRED_CITY_COOKIE_NAME, ...)`,
   check if `consent_preferences` is granted. If not, skip the cookie (the city preference
   is ephemeral via URL param only). For authenticated users with `preferred_city` FK,
   the DB value still works without the cookie.

**Acceptance criteria:**
- Without `consent_preferences` cookie: `lang_pref` cookie is NOT set on language switch.
- With `consent_preferences`: `lang_pref` is set as before.
- Without `consent_preferences`: `preferred_city` cookie is NOT set, but authenticated
  users' DB preference still works.
- No JS errors when cookie setting is skipped.

---

### T-06d — ConsentRecord Creation in Views

**Priority:** medium | **Depends on:** T-02, T-05, T-07, T-07b (Level 4) | **Risk:** Low

**Files:**
- `src/backend/apps/users/views/consent.py` — `consent_accept`, `consent_decline`, `consent_withdraw`

**Semantic anchors:**
- Each view's point where the service call + cookie set occurs — insert
  `record_consent_action(...)` call after the service call, before the redirect.

**Changes:**
1. Import `record_consent_action` from `apps.users.services.consent_record`.
2. In `consent_accept`: after `give_consent(user)` (auth) or cookie-only path (anon),
   call `record_consent_action(user=user, choice=ConsentChoice.ACCEPTED,
   categories={"analytics": True, "preferences": True}, request=request)`.
3. In `consent_decline`: after `decline_consent(user)`, call
   `record_consent_action(user=user, choice=ConsentChoice.DECLINED,
   categories={"analytics": False, "preferences": True}, request=request)`.
4. In `consent_withdraw`: after `withdraw_consent(user)`, call
   `record_consent_action(user=user, choice=ConsentChoice.WITHDRAWN,
   categories={"analytics": False, "preferences": False}, request=request)`.

**Acceptance criteria:**
- Each consent action (accept/decline/withdraw) creates exactly one `ConsentRecord`.
- Record contains: user (or null for anonymous), timestamp, consent_version, choice,
  categories, anonymized IP, truncated UA.
- `ruff check` + `basedpyright` pass.

---

### T-07 — ConsentRecord Model + Migration + Admin

**Priority:** high | **Depends on:** — (Level 1) | **Risk:** Low

**Files:**
- `src/backend/apps/users/models.py` — add `ConsentRecord` model
- `src/backend/apps/core/enums.py` — add `ConsentChoice(StrEnum)`, `CookieCategory(StrEnum)`
- `src/backend/apps/users/migrations/` — auto-generated migration
- `src/backend/apps/users/admin.py` — register `ConsentRecord` (if admin exists)
- `src/backend/apps/users/services/__init__.py` + `src/backend/apps/users/services/consent_record.py` — `record_consent_action` helper

**Semantic anchors:**
- `apps/core/enums.py` `__all__` list — append `"ConsentChoice"`, `"CookieCategory"`.
- `apps/users/models.py` — append `ConsentRecord` class after `LoginToken`.
- `apps/users/services/__init__.py` — export `record_consent_action`.

**Changes:**
1. Add to `apps/core/enums.py`:
   ```python
   class ConsentChoice(StrEnum):
       ACCEPTED = "accepted"
       DECLINED = "declined"
       WITHDRAWN = "withdrawn"

   class CookieCategory(StrEnum):
       ESSENTIAL = "essential"
       ANALYTICS = "analytics"
       PREFERENCES = "preferences"
   ```
2. Add to `apps/users/models.py`:
   ```python
   class ConsentRecord(models.Model):
       user = models.ForeignKey(
           "users.User", null=True, blank=True,
           on_delete=models.SET_NULL, related_name="consent_records",
       )
       session_key = models.CharField(max_length=40, null=True, blank=True)
       consent_given_at = models.DateTimeField(auto_now_add=True)
       consent_version = models.CharField(max_length=20)
       choice = models.CharField(max_length=20, choices=ConsentChoice.choices())
       categories = models.JSONField(default=dict)
       ip_address = models.GenericIPAddressField(null=True, blank=True)
       user_agent = models.TextField(blank=True, max_length=500)

       class Meta:
           db_table = "consent_records"
           ordering = ["-consent_given_at"]
   ```
3. Register in admin (if `apps/users/admin.py` exists; otherwise create).
4. Create `apps/users/services/consent_record.py`:
   ```python
   def record_consent_action(user, choice, categories, request):
       """Create a ConsentRecord for GDPR Article 7(1) audit trail."""
       # Anonymize IP: zero out last octet for IPv4
       ip = request.META.get("REMOTE_ADDR", "") or None
       if ip and "." in ip:
           ip = ".".join(ip.split(".")[:-1] + ["0"])
       return ConsentRecord.objects.create(
           user=user if user and user.is_authenticated else None,
           session_key=request.session.session_key,
           consent_version="1.0",
           choice=choice,
           categories=categories,
           ip_address=ip,
           user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:500],
       )
   ```
5. Export from `apps/users/services/__init__.py`.

**Acceptance criteria:**
- `makemigrations` produces exactly one new migration (no drift on `--check`).
- Model has `user` (nullable FK), `consent_version`, `choice` (StrEnum), `categories`
  (JSONB), `ip_address` (anonymized), `user_agent` (truncated 500 chars).
- `record_consent_action(...)` callable creates a row with all fields.
- Admin lists `ConsentRecord` with read-only fields.
- `ruff check` + `basedpyright` pass.

---

### T-07b — Pydantic DTO + Consent Recording Service

**Priority:** medium | **Depends on:** T-07 (Level 2) | **Risk:** Low

**Files:**
- `pyproject.toml` — add `pydantic` as direct dependency
- `src/backend/apps/users/schemas.py` — **new file** (Pydantic DTO)
- `src/backend/apps/users/services/consent_record.py` — `record_consent_action` (see T-07)

**Semantic anchors:**
- `pyproject.toml` `[project] dependencies` list (line 10-28) — append `"pydantic>=2"`.
- `apps/users/schemas.py` — new module for consent form validation.

**Changes:**
1. Run `uv add pydantic` (adds to `pyproject.toml` + `uv.lock`).
2. Create `apps/users/schemas.py`:
   ```python
   from pydantic import BaseModel, Field
   from apps.core.enums import ConsentChoice

   class ConsentSubmission(BaseModel):
       """Pydantic DTO for consent form submission validation (TR-06 / constraint C-9.2)."""
       choice: ConsentChoice
       analytics: bool = False
       preferences: bool = False
       consent_version: str = Field(default="1.0", max_length=20)
   ```
3. The consent views will use this DTO in T-06d to validate POST data.

**Acceptance criteria:**
- `pydantic>=2` listed as direct dependency in `pyproject.toml`.
- `ConsentSubmission` model validates `choice` against `ConsentChoice` enum.
- Invalid `choice` value → `pydantic.ValidationError`.

---

### T-08 — Consent Re-Prompting (12-Month Rollover)

**Priority:** medium | **Depends on:** T-04, T-05 (Level 4) | **Risk:** Low

**Files:**
- `src/backend/apps/users/context_processors.py` — `consent_state` function

**Semantic anchors:**
- `consent_state` function — the section that reads the `consent_given` cookie for
  anonymous users (the `cookie in ("accepted", "true", "declined", "withdrawn")` check).

**Changes:**
1. Add a `consent_timestamp` cookie that stores the Unix timestamp of when consent was given.
   Set it alongside `consent_given` in T-05's view changes (retroactively update T-05).
2. In `consent_state`, for authenticated users: check if `consent_given_at` is older than
   12 months (365 days). If so, `consent_shown = False` (banner reappears).
3. For anonymous users: check `consent_timestamp` cookie. If older than 12 months,
   `consent_shown = False`. If no timestamp, fall back to `consent_given` cookie presence.

**Acceptance criteria:**
- Consent given > 12 months ago → banner reappears (`consent_shown = False`).
- Consent given < 12 months ago → banner hidden (`consent_shown = True`).
- Existing 12-month cookie `max_age` (T-05) provides browser-side expiry as primary
  mechanism; T-08's server-side check is defense-in-depth (D-T08).

---

### T-09 — Cookie Preference Center (Footer Link)

**Priority:** low | **Depends on:** T-04, T-05 (Level 4) | **Risk:** Low

**Files:**
- `src/backend/templates/components/footer.html` (or base template if no footer component)
- `src/backend/apps/core/views.py` or `apps/users/views/consent.py`

**Semantic anchors:**
- Footer template — add a "Cookie settings" link.
- `consent_state` context processor — add a `show_banner_override` flag triggered by
  `?ref=preferences` URL parameter.

**Changes:**
1. Locate or create `templates/components/footer.html` (check base template for include).
2. Add a "Cookie settings" link to the footer that points to the current page URL with
   `?ref=preferences` appended.
3. In `consent_state` context processor, check `request.GET.get("ref") == "preferences"`:
   if true, force `consent_shown = False` (banner always shows when user explicitly
   requests it).
4. The banner's "Manage" button (from T-06a) links the same way.

**Acceptance criteria:**
- Footer "Cookie settings" link present on all pages (verify via `test_templates.py`).
- Clicking it shows the consent banner (for users who previously consented).
- `ruff check` + `basedpyright` pass.

---

### T-10 — Tests & Fix Test Defects

**Priority:** high | **Depends on:** T-01, T-02, T-03, T-04, T-05, T-06d, T-07 (Level 5)
**Risk:** Low

**Files:**
- `src/backend/apps/users/tests/test_consent.py` — update GET→POST, add anonymous tests
- `src/backend/apps/core/tests/test_templates.py` — add 2 missing templates (cabinet/hub, settings)
- `src/backend/apps/ads/tests/test_listings_context.py` — repoint `is_consent_given` patches
- `src/backend/apps/ads/tests/test_detail_context.py` — repoint `is_consent_given` patches
- `src/backend/apps/users/tests/test_deletion.py` (if exists) — add accept-after-decline test
- New: `src/backend/apps/users/tests/test_consent_context.py` — context processor tests

**Semantic anchors:**
- `test_consent.py` — `TestConsentAcceptView`, `TestConsentDeclineView`, `TestConsentWithdrawView`
  classes; `test_accept_requires_authentication`, `test_accept_sets_consent_given_at`, etc.
- `test_templates.py` `_TEMPLATES_WITH_BANNER` list (line 23-29) — add
  `"cabinet/hub.html"` and `"cabinet/settings.html"`.
- `test_listings_context.py` — patches `apps.users.views.consent.is_consent_given` (line ~129);
  repoint to `apps.users.context_processors.is_consent_given` or test the new behavior.
- `test_detail_context.py` — same pattern.

**Changes:**
1. `test_consent.py`:
   - All accept/decline tests: `client.get()` → `client.post()`.
   - `test_accept_requires_authentication`: anonymous POST → now 302 to `/` (not login),
     because `@login_required` is removed. Update assertion.
   - Add `test_anonymous_accept_sets_cookie` — POST accept as anonymous → cookie set, no
     DB write.
   - Add `test_anonymous_decline_sets_cookie` — same for decline.
   - Add `test_cookie_has_secure_flag` — `response.cookies["consent_given"]["secure"]` is True.
   - Add `test_accept_after_decline_restores_publishing` — decline then accept, assert
     `is_declined=False`, `ads_auto_publish=True`.
   - Update cookie value assertions: `"true"` → `"accepted"`.
2. `test_templates.py`:
   - Add `"cabinet/hub.html"` and `"cabinet/settings.html"` to `_TEMPLATES_WITH_BANNER`.
   - Update assertion count from 5 to 7.
3. `test_listings_context.py` + `test_detail_context.py`:
   - Repatch from `apps.users.views.consent.is_consent_given` to the context processor
     function or test via cookie simulation.
4. New `test_consent_context.py`:
   - Context processor returns `consent_shown=False` for anonymous without cookie.
   - Returns `consent_shown=True` for anonymous with `consent_given=accepted`.
   - Returns `consent_analytics=False` before consent (script gating test hook).
   - Returns `consent_analytics=True` after consent.
5. New `test_consent_records.py`:
   - Accept → `ConsentRecord` row created with `choice="accepted"`.
   - Decline → `ConsentRecord` row with `choice="declined"`.
   - Withdraw → `ConsentRecord` row with `choice="withdrawn"`.
   - Anonymous consent → `user_id` is null, `session_key` set.
6. New `test_script_gating.py`:
   - Before consent: Plausible/GLightbox scripts absent from response HTML.
   - After consent: scripts present.

**Acceptance criteria:**
- All consent-related test files pass.
- `test_templates.py` checks 7 templates (was 5).
- Anonymous consent via POST works (cookie set, no DB write).
- Accept-after-decline restores `ads_auto_publish=True`.
- Cookie has `secure=True`.
- Script gating verified (scripts absent before consent, present after).

---

### FINAL-VERIFY — Regression + Acceptance-Criteria Walkthrough

**Priority:** high | **Depends on:** T-01, T-02, T-03, T-04, T-05, T-06a, T-06b, T-06c,
T-06d, T-07, T-07b, T-08, T-09, T-10 | **Risk:** — (verification only)

**Purpose:** Dedicated multi-stage verification for a cross-cutting change set touching
views, services, context processors, models, templates, and tests.

**Verification steps** (test DB up per `.ai/context/commands.md`; run via the `test`
Compose service — never `uv run pytest` locally):

1. **Migrations guard:** `makemigrations --check` confirms exactly one new migration
   (T-07's `ConsentRecord`). No other schema drift.
2. **Privacy page:** `GET /privacy/` → 200, accessible without login, contains cookie
   table from §4.4. (AC-1, TR-01)
3. **POST-only views:** `GET /consent/accept/` → 405, `GET /consent/decline/` → 405.
   `POST /consent/withdraw/` → 405 for unauthenticated (still @login_required). (AC-2, D2)
4. **Anonymous consent:** `POST /consent/accept/` (anonymous) → 302, sets
   `consent_given=accepted` + `consent_analytics=true` + `consent_preferences=true`
   cookies with `secure=True`. `GET /` afterward → banner NOT shown. (TR-06, D4)
5. **Accept-after-decline:** `decline_consent` then `give_consent` →
   `is_declined=False`, `ads_auto_publish=True`, `consent_given_at` set. (TR-05, D6)
6. **Context processor:** Anonymous without cookie → `consent_shown=False`.
   Authenticated with `consent_given_at` → `consent_shown=True`. (D3, D5)
7. **Script gating:** Before consent, `ads/detail.html` response has NO
   `plausible.io` or `glightbox` script tags. After consent, they're present. (TR-08, D7)
8. **Preference-cookie gating:** Without `consent_preferences`, `lang_pref` cookie is
   NOT set on language switch. (Q8)
9. **ConsentRecord:** Each accept/decline/withdraw creates a row with correct
   `choice`, `categories`, `ip_address` (anonymized), `user_agent` (truncated).
   Anonymous → `user_id` null, `session_key` set. (TR-09, D8)
10. **12-month re-prompt:** ConsentRecord with `consent_given_at > 12 months ago` →
    banner reappears. (TR-10)
11. **Template guard:** All 7 templates in `_TEMPLATES_WITH_BANNER` guard the banner.
    Footer has "Cookie settings" link. (PR-07)
12. **Banner text:** Contains "Essential", "Analytics", "Preferences" categories with
    descriptions. (D9, TR-07)
13. **Cookie format:** `consent_given=accepted` (not `"true"`), plus
    `consent_analytics` and `consent_preferences` cookies. All with
    `max_age=31536000`, `httponly=True`, `samesite="Lax"`, `secure=True`. (D-COOKIES)
14. **Full regression:** Run `apps.users`, `apps.ads`, `apps.core`, `apps.search`,
    `apps.cabinet`, `apps.analytics` test suites — no collateral damage.
15. **Static checks:** `ruff check` + `basedpyright` across all touched trees.

**Exit criteria:** All tests green, all 9 defects (D1–D9) resolved, TR-01–TR-10 satisfied,
PO-01–PO-09 defaults implemented, static checks clean, no schema drift beyond
`ConsentRecord` migration.

---

## Notes for implementors

- **Semantic anchors only** — never line numbers. The spec's `file:line` references are
  for locating only.
- **All comments/logs/docstrings/errors in English** (project rule 1).
- **StrEnum for all constants** (project rule 10): `ConsentChoice`, `CookieCategory` go in
  `apps/core/enums.py`, not inline strings.
- **Pydantic at boundaries** (constraint C-9.2): `ConsentSubmission` DTO in
  `apps/users/schemas.py` validates form data starting T-06d. Run `uv add pydantic`
  before T-07b.
- **Cookie format is a planning decision** (D-COOKIES): `consent_given` values change
  from `"true"` to `"accepted"`. The context processor handles backward compatibility
  with the old `"true"` value during the transition.
- **Anonymous consent is cookie-only**: no DB writes for unauthenticated requests
  (security gate D-3). `ConsentRecord.user_id` is nullable for this case; `session_key`
  is used for identification.
- **Two-process model** (constraint C-1): consent state is in the DB (`User` model) or
  cookies — both are shared across web (gunicorn) and bot (aiogram) processes. No
  cache or in-memory state.
- **`consent_withdraw` keeps `@login_required`**: withdrawal is account deletion
  (requires User object). `@require_POST` already present. No change needed beyond
  Secure cookie flag and ConsentRecord creation.
- **Migration**: T-07's `ConsentRecord` migration is the only schema change. It must
  apply before both web and bot processes start (existing C-1 constraint — migrations
  run once at startup).
- **D-T08 defense-in-depth**: 12-month cookie `max_age` (T-05) is the primary re-prompt
  mechanism. T-08 adds server-side timestamp verification for tampered cookies. T-08
  is recommended but optional for compliance.
- **D-SCRIPT**: Server-side template gating (`{% if consent_analytics %}`) replaces the
  spec's suggested inline-JS approach. This works because the HTMX MPA does full-page
  reloads on consent actions, and the context processor reads cookies server-side.
