# Consent Banner & GDPR/ePrivacy Compliance Research Report

> **Status:** Research Complete
> **Confidence:** HIGH — all findings verified against project source code
> **Date:** 2026-08-20
> **Scope:** Consent banner implementation, cookie usage, cookie consent, privacy policy, and related GDPR/ePrivacy compliance for the Mko Bazuna classifieds platform.

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
- Link to `/privacy/` (line 108) - **returns 404, no route exists**

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
| `preferred_city` | `set_preferred_city` view | `/` | 1 year | No |

### 1.7 Frontend Scripts (External)

| Script | Source | Essential? | Consent Required? |
|--------|--------|------------|-------------------|
| Plausible analytics | `https://<host>/js/script.js` | No (traffic analytics) | Yes (1st-party, non-essential) |
| HTMX | `unpkg.com/htmx.org@1.9.12` | Yes (MPA functionality) | Yes (functional, not consent) |
| GLightbox | `cabinet_hub.html`, `detail.html` | No (image gallery) | Yes (non-essential) |

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

### LOW: `preferred_city` Cookie Set Without Consent
- **File:** `src/backend/apps/search/views/preferred_city.py` (line 57)
  - `set_preferred_city` view sets a 1-year `preferred_city` cookie.
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
| Lawful basis for processing | **Partially met** | Consent tracked via `consent_given_at`, `is_declined`, `consent_revoked_at` (model, line 88) |
| Right to be informed | **Not met** | No privacy policy page (`/privacy/` returns 404) |
| Right to withdraw | **Met** | `consent_withdraw` view (line 118) + `withdraw_consent()` service |
| Right to erasure | **Met (30 days)** | `consent_hard_delete()` sweep with `ERASURE_RETENTION_DAYS=30` (spec decision F, line 85) |
| Data minimization | **Met** | Only `telegram_id` + optional `username` collected (spec decision F, line 81) |
| Purpose limitation | **Met (design)** | Consent covers "all PII processing including the bot" (spec decision K, line 99) |

### ePrivacy Directive Requirements

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Consent for non-essential cookies | **Not met** | `lang_pref` (1-year) and `preferred_city` (1-year) cookies set without consent |
| Consent for non-essential scripts | **Not met** | Plausible analytics script loads unconditionally |
| Consent for functional scripts | **Met** | HTMX is essential for MPA functionality - consent not required |
| Clear consent information | **Not met** | No privacy policy to inform users which cookies/scripts are used |

### Spec Compliance Checklist

| Spec Decision | Requirement | Status |
|---------------|-------------|--------|
| Decision F (line 83) | Privacy policy required from launch | **NOT MET** -- `/privacy/` returns 404 |
| Decision F (line 84) | DECLINE != WITHDRAW | **MET** -- 3 distinct model fields |
| Decision F (line 85) | 30-day PII erasure after withdrawal | **MET** -- `consent_hard_delete` sweep |
| Decision F (line 88-89) | PII masking in logs | **Met** -- `mask_telegram_id()` from `apps/core/utils/sanitize.py` |
| Decision F (line 91) | Banner guard on all template sites | **PARTIAL** -- 2 of 7 templates have the guard |
| Decision F (line 90) | Withdrawal UI (POST + CSRF + confirmation) | **MET** -- "Withdraw Data" button on seller dashboard |
| Decision K (line 137) | Plausible cookieless, no consent needed | **Questionable** -- script loads unconditionally; Plausible may set cookies |
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
| No privacy policy (`/privacy/` = 404) | 100% | Non-compliance with GDPR Article 13 (right to be informed) + ePrivacy | **CRITICAL** |
| Consent views accept GET | 100% | CSRF vulnerability, non-idempotent state changes | **CRITICAL** |
| Dead `consent_given` cookie | 100% | Code confusion, maintenance burden, no functional impact | Medium |
| Missing banner guards on 5 templates | 100% | Banner shows for deleted users on most pages | **HIGH** |
| Missing `consent_shown` context on 4 views | 100% | Banner always shows regardless of prior consent | **HIGH** |
| Plausible script loads without consent | 100% | Potential ePrivacy violation if Plausible sets cookies | Medium |
| `lang_pref`/`preferred_city` cookies without consent | 100% | Potential ePrivacy violation (non-essential persistent cookies) | Low-Medium |

### Missing Components
1. **Privacy policy page** -- Required by GDPR Article 13 and spec decision F. Must list cookies used, processing purposes, and user rights.
2. **Cookie declaration** -- A table of all cookies/scripts and their purposes, linked from the privacy policy.
3. **Script loading gate** -- Non-essential scripts (Plausible, GLightbox) should only load after consent.
4. **Cookie consent middleware** -- To block non-essential cookies (e.g., `preferred_city`) before consent is given.
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
   - Intercept `preferred_city` cookie set before consent -- either block it or downgrade to session-only.
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
