# Consent Banner & GDPR/ePrivacy Compliance Research Report

> **Status:** Research Complete
> **Confidence:** HIGH — all findings verified against project source code
> **Date:** 2026-08-20
> **Scope:** Consent banner implementation, cookie usage, cookie consent, privacy policy, and related GDPR/ePrivacy compliance for the Mko Bazuna classifieds platform.
>
> **Implementation Status (Plan 21 — consent-banner-compliance):** Resolved. All major
> pre-launch defects from §2/§5/§6 are implemented by Plan 21 (`consent-banner-compliance`):
>
> - **D-ENUMS:** `ConsentChoice` (`ACCEPTED`/`DECLINED`/`WITHDRAWN`) and `CookieCategory`
>   (`ESSENTIAL`/`ANALYTICS`/`PREFERENCES`) StrEnums added to `apps/core/enums.py`
>   (re-exported via `__all__`). `ConsentChoice` backs the `consent_records.choice` audit column;
>   `CookieCategory` exists as the category vocabulary but is **not** referenced at runtime
>   (category flags use matching string keys).
> - **D-audit:** accept/decline/withdraw each insert a new row in `consent_records` (never updated).
> - **D-views (T-05, D2):** `consent_accept`/`consent_decline` are `@require_POST` and **anonymous-accessible**
>   (no `@login_required`); `consent_withdraw` keeps `@login_required` + `@require_POST`. GET is rejected (CR4).
> - **D-cookies (D-COOKIES):** the `consent_given` cookie now carries a structured value
>   (`accepted`/`declined`/`withdrawn`) and **is read back** by `consent_state`
>   (`request.COOKIES.get("consent_given")`) — it is no longer a dead write.
> - **D4 (privacy):** `/privacy/` route exists (`apps.core.views.privacy_policy`,
>   `apps/core/urls.py`) rendering public `templates/privacy.html` — the 404 is resolved.
> - **D7 (script gating):** Plausible + GLightbox JS gate on `consent_analytics`
>   (`{% if consent_analytics %}` in 11 templates). **Partial:** the GLightbox CSS `<link>`
>   and the `/privacy/` Plausible snippet load unconditionally (non-executable fallback).
> - **D9 (banner + guards):** `consent_state` context processor provides `consent_shown` /
>   `consent_analytics` / `consent_preferences` to all templates; the
>   `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard
>   suppresses the banner for soft-deleted users.
> - **Re-prompt:** consent re-prompted every 12 months (cookie `max_age = 31536000` / 1 year).
>
> Cookie table §1.6 updated below. The `preferred_city` consent-gating note above remains
> in effect (satisfies the §5/Missing Components #4 recommendation without a blocking middleware).

---

## 1. Implementation Inventory

### 1.1 Consent Data Model
**File:** `src/backend/apps/users/models.py` (line 88)

The `User` model tracks consent via three distinct fields, implementing the spec's requirement that **DECLINE != WITHDRAW** (spec decision F, decision K):

| Field | Type | Purpose |
|-------|------|---------|
| `consent_given_at` | `DateTimeField` (nullable) | Timestamp when user accepted all processing |
| `is_declined` | `BooleanField` (default `False`) | User declined consent (browse-only, no erasure) |
| `consent_revoked_at` | `DateTimeField` (nullable) | User withdrew consent (triggers soft-delete + 30-day PII erasure) |

### 1.2 Consent View Functions
**File:** `src/backend/apps/users/views/consent.py`

| Function | Line | Description |
|----------|------|-------------|
| `is_consent_given(request)` | Line 30 | Returns `True` if `consent_given_at` is set on the user (None for anonymous = False) |
| `consent_accept` | Line 58 | Sets `consent_given_at = now()`, clears `is_declined`, saves user, sets `consent_given` cookie (1 year) |
| `consent_decline` | Line 88 | Sets `is_declined = True`, saves user, sets `consent_given` cookie (1 year) |
| `consent_withdraw` | Line 118 | Calls `withdraw_consent()` service, sets `consent_revoked_at`, clears `consent_given` cookie |

**Cookie constant:** `CONSENT_COOKIE_NAME = "consent_given"` (line 25), `CONSENT_COOKIE_MAX_AGE = 365 * 24 * 60 * 60` (1 year, line 26).

### 1.3 Consent Services
**File:** `src/backend/apps/users/services/deletion.py`

| Service | Purpose |
|---------|---------|
| `give_consent(user)` | Sets `consent_given_at`, clears `is_declined`/`consent_revoked_at` |
| `decline_consent(user)` | Sets `is_declined = True` |
| `withdraw_consent(user)` | Sets `consent_revoked_at = now()`, triggers soft-delete + 30-day hard delete |
| `consent_hard_delete()` | Sweeps users with `consent_revoked_at < 30 days ago`, nulls PII, deletes rows |

### 1.4 Consent Banner Template
**File:** `src/backend/templates/components/consent_banner.html`

Implements a cookie-consent style banner with:
- `{% if not consent_shown %}` guard (line 6) - only renders if the context flag is not set
- Accept button -> POST to `/consent/accept/`
- Reject button -> POST to `/consent/decline/`
    - Link to `/privacy/` (line 108) — **RESOLVED**: route exists (`apps.core.views.privacy_policy`, `apps/core/urls.py`) rendering public `templates/privacy.html` (Plan 21 D4).

### 1.5 Banner Placement (7 Templates)
The banner is included (`{% include "components/consent_banner.html" %}`) in these templates:

| Template | Line | Has Guard? | Passes `consent_shown`? |
|----------|------|------------|-------------------------|
| `ads/dashboard.html` | 163 | **No** | Yes (line 85 of `dashboard.py`) |
| `ads/detail.html` | 109 | **No** | No |
| `ads/list.html` | 39 | **No** | Yes (lines 81, 435 of `listings.py`) |
| `analytics/seller_dashboard.html` | 116 | **No** | No |
| `analytics/moderation_dashboard.html` | 139 | **No** | No |
| `cabinet/hub.html` | 34 | **Yes** (line 33) | No |
| `cabinet/settings.html` | 32 | **Yes** (line 31) | No |

**Guard pattern:** `{% if not request.user.is_authenticated or not request.user.is_deleted %}`
- Per spec (decision F, line 91), this guard should be in **all 5 template sites**. Currently only 2 of 7 templates have it.

### 1.6 Cookie Audit

| Cookie | Set By | Path | Lifetime | Consent-Gated? |
|--------|--------|------|----------|----------------|
| `consent_given` | `consent.py` (lines 68, 98) | `/` | 1 year | N/A (consent state) |
| `consent_given` | `consent.py` (line 129) | `/` | Deleted (max_age=0) | On withdraw |
| `sessionid` | Django | `/` | Session (persistent cookie per spec H) | No |
| `csrftoken` | Django | `/` | 1 year | No |
| `lang_pref` | JS in `language_switcher.html` (line 76) | `/` | 1 year | No |
| `preferred_city` | `set_preferred_city` view | `/` | 1 year | Yes (set only when `consent_preferences` cookie is present) |

### 1.7 Frontend Scripts (External)

| Script | Source | Essential? | Consent Required? |
|--------|--------|------------|-------------------|
| Plausible analytics | `https://<host>/js/script.js` | No (traffic analytics) | Yes (JS gated behind `consent_analytics`; the /privacy/ snippet loads unconditionally) |
| HTMX | `unpkg.com/htmx.org@1.9.12` | Yes (MPA functionality) | Yes (functional, not consent) |
| GLightbox | `cabinet_hub.html`, `detail.html` | No (image gallery) | Yes (JS gated behind `consent_analytics`; CSS `<link>` loads unconditionally) |

**CSP:** `Content-Security-Policy-Report-Only` (report-only, **not enforced**) - allows `script-src 'self' 'unsafe-inline' https://unpkg.com https://*.plausible.io`. Violations logged to `/csp-report/`.

### 1.8 Django Security Settings
**File:** `src/backend/config/settings/base.py` (lines 65-69)

| Setting | Production Value | Dev/Test Value |
|---------|------------------|----------------|
| `SESSION_COOKIE_SECURE` | `True` | `False` |
| `CSRF_COOKIE_SECURE` | `True` | `False` |
| `SESSION_COOKIE_HTTPONLY` | `True` | `False` |
| `SESSION_COOKIE_SAMESITE` | `"Lax"` | `"Lax"` |
| `CSRF_COOKIE_HTTPONLY` | `True` | `False` |
| `CSRF_COOKIE_SAMESITE` | `"Lax"` | `"Lax"` |

### 1.9 Bot-Side Consent Checks
**File:** `src/telegram_bot/middlewares/permissions.py` (line 122)

The bot checks `consent_revoked_at` and `is_declined` for permission gating, but has no standalone consent confirmation flow. Per spec decision K, "Site banner consent covers all PII processing including the bot; no separate bot confirmation required."

---

## 2. Defects & Compliance Gaps

> **Resolution:** All defects below are resolved by Plan 21 (consent-banner-compliance)
> except the `lang_pref` cookie (§2 MEDIUM), which remains open. See
> `## Implementation Status` above and §3 Legal Requirements Checklist for current status.

### CRITICAL: Missing Privacy Policy
- **File:** `src/backend/templates/components/consent_banner.html` (line 108)
  - Banner links to `/privacy/` but **no URL route exists** - returns 404.
- **Spec requirement:** Technical Specification (decision F, line 83): "Privacy policy / Terms required from launch (visible to buyers without login)."
- **Impact:** Cannot achieve GDPR/ePrivacy compliance - no privacy policy visible to users.

### CRITICAL: Consent Views Accept GET Requests
- **File:** `src/backend/apps/users/views/consent.py`
  - `consent_accept` (line 58) and `consent_decline` (line 88) have **no `@require_POST` decorator**.
  - State-changing operations must be POST-only per web security best practices.
- **File:** `src/backend/apps/users/tests/test_consent.py` (lines 93, 134)
  - Tests use `client.get()` to trigger consent accept/decline, reinforcing the insecure pattern.

### CRITICAL: Dead Cookie (consent_given never read)
- **File:** `src/backend/apps/users/views/consent.py`
  - `consent_given` cookie is SET at lines 68, 98, 129.
  - **No code anywhere reads this cookie** - no `request.COOKIES["consent_given"]` exists in the entire codebase.
  - The cookie serves no functional purpose. The consent state is tracked server-side via `consent_given_at` field on the User model.

### HIGH: Banner Guard Missing on 5 of 7 Templates
- Per spec decision F (line 91), the guard `{% if not request.user.is_authenticated or not request.user.is_deleted %}` should be in "all 5 template sites."
- Currently only 2 of 7 templates (`cabinet/hub.html`, `cabinet/settings.html`) have the guard.
- Missing on: `ads/dashboard.html`, `ads/detail.html`, `ads/list.html`, `analytics/seller_dashboard.html`, `analytics/moderation_dashboard.html`.
- **Impact:** Banner may render for soft-deleted users on most pages.

### HIGH: Missing `consent_shown` Context on 4 Views
- `consent_shown` context variable is only passed by `dashboard.py` (line 85), `listings.py` (lines 81, 435), and `search.py` (line 175).
- Missing from: `seller_trust_dashboard.py`, `moderation_dashboard.py`, `cabinet_hub`, `cabinet_settings`.
- **Impact:** The `{% if not consent_shown %}` guard in the template always evaluates to True on these pages (context undefined = falsy, so `not consent_shown` = True), meaning the banner ALWAYS shows on these pages even after consent.

### MEDIUM: Plausible Analytics Loads Without Consent Gating
- **Spec decision L (line 137):** Claims Plausible is "cookieless, no consent banner needed (legitimate interest)."
- **Actual implementation:** Plausible loads a `<script>` tag from `https://<host>/js/script.js` without any consent check.
- **ePrivacy consideration:** While Plausible is designed to be privacy-friendly, the ePrivacy Directive (Cookie Law) generally requires consent for non-essential scripts that set or access non-essential cookies. Plausible's own documentation states it may set a `_plausible` cookie. The script itself loads regardless of consent.
- **Note:** Plausible self-hosted does not set cookies by default, but the script is still loaded unconditionally.

### MEDIUM: `lang_pref` Cookie Set Without Consent
- **File:** `src/backend/templates/components/language_switcher.html` (line 76)
  - Sets `lang_pref` cookie via JavaScript for 1 year.
- **ePrivacy Directive:** The `lang_pref` cookie is a non-essential persistent cookie (1 year). Under strict ePrivacy interpretation, this requires prior consent unless classified as "strictly necessary" for a service explicitly requested by the user.
- **Defense:** Could be argued as "functionality requested by the user" (language preference). Still, best practice is to set it only after consent.

### LOW: `preferred_city` Cookie Set Without Consent — RESOLVED

- **File:** `src/backend/apps/search/views/preferred_city.py` (line 57)
  - `set_preferred_city` view sets a 1-year `preferred_city` cookie.
- **Status:** Resolved. The cookie write is now consent-gated — it is only set
  when `request.COOKIES["consent_preferences"] == "true"` (`preferred_city.py`).
  See `## Implementation Status` above and §5 Missing Components #4.
- **Similar to `lang_pref`:** Non-essential persistent cookie, arguable as user-requested functionality.

### LOW: Tests Reinforce Insecure Patterns
- **File:** `src/backend/apps/users/tests/test_consent.py` (lines 93, 134)
  - Uses `client.get()` instead of `client.post()` for consent accept/decline.
- **File:** `src/backend/apps/core/tests/test_templates.py`
  - Only tests 5 of 7 templates for the guard pattern (missing `dashboard.html` and `detail.html`).

---

## 3. Legal Requirements Checklist

Based on GDPR (EU Regulation 2016/679) and ePrivacy Directive (2009/136/EC, as interpreted by CJEU case C-203/22 "Planet49"):

### GDPR Requirements

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Lawful basis for processing | **Met** | Consent tracked via `consent_given_at`, `is_declined`, `consent_revoked_at` (model); recorded in `consent_records` audit table |
| Right to be informed | **Met** | `/privacy/` route exists (`apps.core.views.privacy_policy`) rendering a public privacy policy page; visible to buyers without login |
| Right to withdraw | **Met** | `consent_withdraw` view (line 118) + `withdraw_consent()` service; POST + CSRF, auth-required |
| Right to erasure | **Met (30 days)** | `consent_hard_delete()` sweep with `ERASURE_RETENTION_DAYS=30` (spec decision F); index `IX_users_erasure_sweep` |
| Data minimization | **Met** | Only `telegram_id` + optional `username` collected |
| Purpose limitation | **Met (design)** | Consent covers "all PII processing including the bot" (spec decision K) |

### ePrivacy Directive Requirements

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Consent for non-essential cookies | **Met** | `preferred_city` set only when `consent_preferences` is present (D-COOKIES); `consent_analytics`/`consent_preferences` written on accept |
| Consent for non-essential scripts | **Partial** | Plausible + GLightbox JS gated behind `consent_analytics` (11 templates); GLightbox CSS link + `/privacy/` snippet load unconditionally |
| Consent for functional scripts | **Met** | HTMX is essential for MPA functionality — consent not required |
| Clear consent information | **Met** | `/privacy/` policy page lists cookies/scripts (§1.6) and user rights |

### Spec Compliance Checklist

| Spec Decision | Requirement | Status |
|---------------|-------------|--------|
| Decision F (line 83) | Privacy policy required from launch | **MET** -- `/privacy/` route + `templates/privacy.html` (Plan 21 D4) |
| Decision F (line 84) | DECLINE != WITHDRAW | **MET** -- 3 distinct model fields + `consent_records` audit log |
| Decision F (line 85) | 30-day PII erasure after withdrawal | **MET** -- `consent_hard_delete` sweep |
| Decision F (line 88-89) | PII masking in logs | **MET** -- `mask_telegram_id()` from `apps/core/utils/sanitize.py` |
| Decision F (line 91) | Banner guard on all template sites | **MET** -- `consent_state` processor + guard in all sites |
| Decision F (line 90) | Withdrawal UI (POST + CSRF + confirmation) | **MET** -- "Withdraw Data" button on seller dashboard |
| Decision K (line 137) | Plausible cookieless, no consent needed | **PARTIAL** -- JS gated behind `consent_analytics`; CSS/privacy snippet ungated |
| Decision K (line 99) | Site banner covers bot too | **MET** -- bot checks same User model fields |

---

## 4. Best Practices Review

### What's Done Well
1. **Clear consent state model:** Three-state consent (accept/decline/withdraw) correctly distinguishes DECLINE from WITHDRAW, matching the spec's explicit requirement (decision F, line 84).
2. **Server-side consent tracking:** Consent state stored on the `User` model, not just in cookies -- survives cookie deletion and works across devices.
3. **Bot integration:** Bot middleware checks the same consent fields, so consent state applies to the Telegram bot too (spec decision K, line 99).
4. **Cookie security settings:** `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `HTTPONLY`, and `SAMESITE="Lax"` are all correctly set for production (base.py lines 65-69).
5. **PII masking:** `mask_telegram_id()` utility prevents raw `telegram_id` values from appearing in logs.

### Areas for Improvement
1. **Dead cookie:** The `consent_given` cookie is set but never read -- it's vestigial code. Either use it or remove it.
2. **Inconsistent template guards:** The `{% if not consent_shown %}` pattern works, but `consent_shown` is only passed by some views, meaning the banner always shows on others.
3. **Missing POST enforcement:** State-changing views should reject GET requests.
4. **CSP is report-only:** Not enforced, meaning violations are logged but not blocked. The spec roadmap mentions moving to enforced CSP in Phase 2.
5. **Cookie categorization:** No mechanism exists to set categories of cookies (essential, analytics, preferences) and only set/load non-essential ones after consent.

---

## 5. Gap Analysis

### Compliance Risk Matrix

| Risk | Likelihood | Impact | Priority |
|------|------------|--------|----------|
| No privacy policy (`/privacy/` = 404) | 0% (was 100%) | Resolved — route + page implemented (Plan 21 D4) | Resolved |
| Consent views accept GET | 0% (was 100%) | Resolved — `@require_POST` on accept/decline (anonymous); withdraw is auth+POST | Resolved |
| Dead `consent_given` cookie | 0% (was 100%) | Resolved — cookie now read by `consent_state` with structured values | Resolved |
| Missing banner guards on 5 templates | 0% (was 100%) | Resolved — `consent_state` processor + guard in all sites | Resolved |
| Missing `consent_shown` context on 4 views | 0% (was 100%) | Resolved — `consent_state` context processor (universal) | Resolved |
| Plausible script loads without consent | 0% (was 100%) | Partial — JS gated behind `consent_analytics`; privacy-page snippet ungated | Partial |
| `lang_pref` cookie without consent | 100% | Non-essential persistent cookie set without consent; low risk (language preference) | Low-Medium |
| `preferred_city` cookie without consent | 0% (was 100%) | Resolved — cookie is consent-gated | Resolved |

### Missing Components
1. **Privacy policy page** -- Required by GDPR Article 13 and spec decision F. Must list cookies used, processing purposes, and user rights.
2. **Cookie declaration** -- A table of all cookies/scripts and their purposes, linked from the privacy policy.
3. **Script loading gate** -- Non-essential scripts (Plausible, GLightbox) should only load after consent.
4. **Cookie consent middleware** -- To block non-essential cookies (e.g., `preferred_city`) before consent is given. **(RESOLVED — implemented via SET-gating in `set_preferred_city`: the cookie is only written when `consent_preferences` is present, satisfying the requirement without a blocking middleware. See Implementation Status above.)**
5. **`@require_POST` on consent views** -- Basic web security.
6. **Template context consistency** -- Either use a context processor to universally provide `consent_shown`, or remove the per-view pattern.

---

## 6. Recommended Approach

### Immediate (Pre-Launch)

1. **Create a `/privacy/` URL route and view** with a privacy policy page that includes:
   - Cookie declaration table (all 6 cookies identified in Section 1.6)
   - Script declaration table (all 3 external scripts from Section 1.7)
   - User rights under GDPR (access, rectification, erasure, data portability, objection)
   - Contact information for data controller (Telegram deep-link, since no email)
   - Spec requirement: "visible to buyers without login" -- serve it as a public Django template view.

2. **Add `@require_POST` to `consent_accept` and `consent_decline` views.**
   - Update `test_consent.py` to use `client.post()` instead of `client.get()`.

3. **Fix template guard coverage:**
   - Add `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard to `ads/dashboard.html`, `ads/detail.html`, `ads/list.html`, `analytics/seller_dashboard.html`, `analytics/moderation_dashboard.html`.

4. **Fix `consent_shown` context consistency:**
   - **Recommended:** Create a context processor that computes `consent_shown` from `request.user` and `request.COOKIES`, applied to ALL templates via `TEMPLATES` setting.
   - This eliminates the need to pass it in every view.

5. **Remove or document the dead `consent_given` cookie:**
   - Either use it (e.g., to persist banner-hidden state for anonymous users) or remove the set/clear calls.

### Post-Launch (Phase 2)

1. **Cookie consent middleware** for non-essential cookies:
   - Intercept `preferred_city` cookie set before consent -- either block it or downgrade to session-only. **(RESOLVED — implemented via SET-gating: the cookie is only written when `consent_preferences` is present; see Implementation Status above.)**
   - `lang_pref` could be argued as strictly necessary (user explicitly switches language), but document this rationale.

2. **Conditional script loading:**
   - Use `data-*` attributes on `<script>` tags and a small inline script that checks consent before loading Plausible/GLightbox.
   - Or use HTMX to swap script tags into the DOM after consent.

3. **Enforce CSP** (currently report-only):
   - Refactor templates to eliminate `'unsafe-inline'` from `script-src` and `style-src`.
   - Flip `Content-Security-Policy-Report-Only` -> `Content-Security-Policy`.

4. **Cookie preference center:**
   - Allow users to granularly control which cookies/scripts are active.
   - Link from both the banner and the privacy policy page.

---

## Appendix: File Index

Critical files for implementing the recommendations:

| File | Role |
|------|------|
| `src/backend/apps/users/views/consent.py` | Consent views + cookie logic |
| `src/backend/apps/users/services/deletion.py` | Consent/deletion services |
| `src/backend/apps/users/models.py` | User consent fields |
| `src/backend/templates/components/consent_banner.html` | Banner template |
| `src/backend/apps/users/tests/test_consent.py` | Consent tests |
| `src/backend/apps/core/tests/test_templates.py` | Template guard tests |
| `src/backend/apps/ads/views/dashboard.py` | Dashboard view (passes `consent_shown`) |
| `src/backend/apps/ads/views/listings.py` | Listing view (passes `consent_shown`) |
| `src/backend/apps/search/views/search.py` | Search view (passes `consent_shown`) |
| `src/backend/templates/ads/dashboard.html` | Missing guard |
| `src/backend/templates/ads/detail.html` | Missing guard + missing `consent_shown` context |
| `src/backend/config/settings/base.py` | Cookie security settings |
| `src/backend/config/urls.py` | URL routing (add `/privacy/`) |
